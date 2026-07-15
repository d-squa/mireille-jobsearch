"""Unit tests for sources/adzuna.py. All HTTP calls are mocked - no
live requests to api.adzuna.com are made in tests."""
from datetime import date
from unittest.mock import MagicMock

import pytest
import requests

from sources.adzuna import AdzunaSource
from tests.fixtures.adzuna_response import EMPTY_RESPONSE, VALID_RESPONSE


def _mock_response(json_payload: dict, status_code: int = 200) -> MagicMock:
    mock_response = MagicMock()
    mock_response.status_code = status_code
    mock_response.json.return_value = json_payload
    if status_code >= 400:
        mock_response.raise_for_status.side_effect = requests.HTTPError(f"{status_code} error")
    else:
        mock_response.raise_for_status.return_value = None
    return mock_response


class TestAdzunaSourceConstruction:
    def test_requires_app_id_and_app_key(self) -> None:
        with pytest.raises(ValueError, match="app_id"):
            AdzunaSource(app_id="", app_key="key")
        with pytest.raises(ValueError, match="app_id"):
            AdzunaSource(app_id="id", app_key="")

    def test_name_is_adzuna(self) -> None:
        session = MagicMock()
        session.request.return_value = _mock_response(EMPTY_RESPONSE)
        source = AdzunaSource(app_id="id", app_key="key", session=session)
        assert source.name == "adzuna"


class TestFetchJobs:
    def test_returns_normalized_jobs_and_skips_incomplete(self) -> None:
        session = MagicMock()
        session.request.return_value = _mock_response(VALID_RESPONSE)
        source = AdzunaSource(app_id="id", app_key="key", session=session)

        jobs = source.fetch_jobs(search_terms=("paid media",), countries=("gb",))

        assert len(jobs) == 2  # third entry missing company name, skipped
        assert jobs[0].company == "Acme Digital Ltd"
        assert jobs[0].job_title == "Paid Media Manager"
        assert jobs[0].location == "Manchester, Greater Manchester"
        assert jobs[0].country == "United Kingdom"
        assert jobs[0].source == "adzuna"
        assert jobs[0].posted_date == date(2026, 7, 8)

    def test_one_request_per_term_per_country(self) -> None:
        session = MagicMock()
        session.request.return_value = _mock_response(EMPTY_RESPONSE)
        source = AdzunaSource(app_id="id", app_key="key", session=session)

        source.fetch_jobs(search_terms=("paid media", "PPC"), countries=("gb", "us"))

        assert session.request.call_count == 4  # 2 terms x 2 countries

    def test_missing_countries_defaults_to_gb(self) -> None:
        session = MagicMock()
        session.request.return_value = _mock_response(EMPTY_RESPONSE)
        source = AdzunaSource(app_id="id", app_key="key", session=session)

        source.fetch_jobs(search_terms=("paid media",), countries=())

        assert session.request.call_count == 1
        args, _ = session.request.call_args
        assert "/gb/" in args[1]

    def test_unknown_country_code_falls_back_to_uppercased_code(self) -> None:
        response = {
            "results": [
                {
                    "id": "1",
                    "title": "Media Buyer",
                    "company": {"display_name": "Some Co"},
                    "location": {"display_name": "Somewhere"},
                    "created": "2026-07-01T00:00:00Z",
                    "redirect_url": "https://example.com/1",
                    "description": "desc",
                }
            ]
        }
        session = MagicMock()
        session.request.return_value = _mock_response(response)
        source = AdzunaSource(app_id="id", app_key="key", session=session)

        jobs = source.fetch_jobs(search_terms=("media buyer",), countries=("zz",))

        assert jobs[0].country == "ZZ"


class TestSalaryFormatting:
    def test_min_and_max_present(self) -> None:
        assert AdzunaSource._format_salary(40000, 48000) == "40,000 - 48,000"

    def test_only_min_present(self) -> None:
        assert AdzunaSource._format_salary(40000, None) == "40,000+"

    def test_only_max_present(self) -> None:
        assert AdzunaSource._format_salary(None, 48000) == "Up to 48,000"

    def test_both_none_returns_none(self) -> None:
        assert AdzunaSource._format_salary(None, None) is None

    def test_no_currency_symbol_since_currency_varies_by_country(self) -> None:
        # Deliberately no £/$/€ prefix - Adzuna doesn't state currency
        # explicitly and guessing one per country risks mislabeling.
        result = AdzunaSource._format_salary(40000, 48000)
        assert "£" not in result and "$" not in result and "€" not in result

    def test_end_to_end_from_fixture(self) -> None:
        session = MagicMock()
        session.request.return_value = _mock_response(VALID_RESPONSE)
        source = AdzunaSource(app_id="id", app_key="key", session=session)

        jobs = source.fetch_jobs(search_terms=("paid media",), countries=("gb",))

        assert jobs[0].salary == "40,000 - 48,000"


class TestKnownUnsupportedCountryBlocklist:
    def test_blocklisted_country_never_makes_a_request(self) -> None:
        session = MagicMock()
        session.request.return_value = _mock_response(VALID_RESPONSE)
        source = AdzunaSource(app_id="id", app_key="key", session=session)

        source.fetch_jobs(search_terms=("paid media",), countries=("ae",))

        session.request.assert_not_called()

    def test_mixing_blocklisted_and_supported_only_requests_supported(self) -> None:
        session = MagicMock()
        session.request.return_value = _mock_response(VALID_RESPONSE)
        source = AdzunaSource(app_id="id", app_key="key", session=session)

        jobs = source.fetch_jobs(search_terms=("paid media",), countries=("ae", "gb", "sa"))

        assert session.request.call_count == 1  # only gb, both ae and sa skipped
        assert len(jobs) == 2
        assert all(job.country == "United Kingdom" for job in jobs)

    def test_all_gulf_countries_blocklisted_returns_empty_with_zero_requests(self) -> None:
        session = MagicMock()
        source = AdzunaSource(app_id="id", app_key="key", session=session)

        jobs = source.fetch_jobs(
            search_terms=("paid media",), countries=("ae", "sa", "kw", "lb", "qa", "bh", "om")
        )

        assert jobs == []
        session.request.assert_not_called()


class TestUnsupportedCountryIsolation:
    def test_unexpected_404_on_a_non_blocklisted_country_does_not_block_others(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Tests the remaining safety net: a country NOT in the
        # blocklist (so a real request is attempted) that still 404s
        # for some other reason must not lose results from countries
        # that do work. Uses a fake code ("zz") rather than "ae" since
        # "ae" is now skipped before any request happens at all - this
        # test needs a request to actually occur and fail.
        monkeypatch.setattr("sources.http_utils.time.sleep", lambda _: None)

        def request_side_effect(method, url, **kwargs):
            if "/zz/" in url:
                return _mock_response({}, status_code=404)
            return _mock_response(VALID_RESPONSE)

        session = MagicMock()
        session.request.side_effect = request_side_effect
        source = AdzunaSource(app_id="id", app_key="key", session=session)

        jobs = source.fetch_jobs(search_terms=("paid media",), countries=("zz", "gb"))

        # gb results still came through despite zz failing
        assert len(jobs) == 2
        assert all(job.country == "United Kingdom" for job in jobs)

    def test_all_countries_failing_returns_empty_list_not_exception(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("sources.http_utils.time.sleep", lambda _: None)
        session = MagicMock()
        session.request.return_value = _mock_response({}, status_code=404)
        source = AdzunaSource(app_id="id", app_key="key", session=session)

        jobs = source.fetch_jobs(search_terms=("paid media",), countries=("zz", "yy"))

        assert jobs == []


class TestErrorHandling:
    def test_connection_error_is_caught_internally_not_propagated(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        session = MagicMock()
        session.request.side_effect = requests.ConnectionError("network down")
        source = AdzunaSource(app_id="id", app_key="key", session=session)
        monkeypatch.setattr("sources.http_utils.time.sleep", lambda _: None)

        # Should NOT raise - per-country/term errors are caught inside
        # fetch_jobs and logged, not propagated to the orchestrator.
        jobs = source.fetch_jobs(search_terms=("paid media",), countries=("gb",))
        assert jobs == []
