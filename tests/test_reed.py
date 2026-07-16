"""Unit tests for sources/reed.py. All HTTP calls are mocked - no
live requests to reed.co.uk are made in tests."""
from datetime import date
from unittest.mock import MagicMock

import pytest
import requests

from exceptions import SourceError
from sources.reed import ReedSource
from tests.fixtures.reed_response import EMPTY_RESPONSE, MALFORMED_DATE_RESPONSE, VALID_RESPONSE


def _mock_session(json_payload: dict, status_code: int = 200) -> MagicMock:
    mock_response = MagicMock()
    mock_response.status_code = status_code
    mock_response.json.return_value = json_payload
    if status_code >= 400:
        mock_response.raise_for_status.side_effect = requests.HTTPError(f"{status_code} error")
    else:
        mock_response.raise_for_status.return_value = None

    session = MagicMock()
    session.request.return_value = mock_response
    return session


class TestReedSourceConstruction:
    def test_requires_api_key(self) -> None:
        with pytest.raises(ValueError, match="api_key"):
            ReedSource(api_key="")

    def test_name_is_reed(self) -> None:
        source = ReedSource(api_key="test-key", session=_mock_session(EMPTY_RESPONSE))
        assert source.name == "reed"


class TestFetchJobs:
    def test_returns_normalized_jobs_and_skips_incomplete(self) -> None:
        session = _mock_session(VALID_RESPONSE)
        source = ReedSource(api_key="test-key", session=session)

        jobs = source.fetch_jobs(search_terms=("paid media",), countries=())

        assert len(jobs) == 2  # third entry missing employerName, skipped
        assert jobs[0].company == "Acme Media Group"
        assert jobs[0].job_title == "Paid Media Manager"
        assert jobs[0].location == "Manchester"
        assert jobs[0].country == "United Kingdom"
        assert jobs[0].source == "reed"
        assert jobs[0].posted_date == date(2026, 7, 10)

    def test_ignores_countries_parameter(self) -> None:
        # Reed has no country scoping - it's UK-only by nature.
        session = _mock_session(EMPTY_RESPONSE)
        source = ReedSource(api_key="test-key", session=session)

        source.fetch_jobs(search_terms=("paid media",), countries=("gb", "us", "ae"))

        assert session.request.call_count == 1  # one call per term, not per country

    def test_one_request_per_search_term(self) -> None:
        session = _mock_session(EMPTY_RESPONSE)
        source = ReedSource(api_key="test-key", session=session)

        source.fetch_jobs(search_terms=("paid media", "PPC", "media buyer"), countries=())

        assert session.request.call_count == 3

    def test_uses_http_basic_auth_with_blank_password(self) -> None:
        session = _mock_session(EMPTY_RESPONSE)
        source = ReedSource(api_key="my-secret-key", session=session)

        source.fetch_jobs(search_terms=("paid media",), countries=())

        _, kwargs = session.request.call_args
        assert kwargs["auth"] == ("my-secret-key", "")

    def test_empty_response_returns_empty_list(self) -> None:
        session = _mock_session(EMPTY_RESPONSE)
        source = ReedSource(api_key="test-key", session=session)

        assert source.fetch_jobs(search_terms=("paid media",), countries=()) == []

    def test_malformed_date_does_not_crash_normalization(self) -> None:
        session = _mock_session(MALFORMED_DATE_RESPONSE)
        source = ReedSource(api_key="test-key", session=session)

        jobs = source.fetch_jobs(search_terms=("media buyer",), countries=())

        assert len(jobs) == 1
        assert jobs[0].posted_date is None

    def test_parses_uk_date_format(self) -> None:
        assert ReedSource._parse_date("10/07/2026") == date(2026, 7, 10)

    def test_work_mode_inferred_from_job_title(self) -> None:
        response = {
            "results": [
                {
                    "jobId": 1,
                    "employerName": "Acme Co",
                    "jobTitle": "Paid Media Manager (Hybrid)",
                    "locationName": "Manchester",
                    "jobDescription": "desc",
                    "date": "10/07/2026",
                    "jobUrl": "https://reed.co.uk/jobs/1",
                }
            ],
            "totalResults": 1,
        }
        session = _mock_session(response)
        source = ReedSource(api_key="test-key", session=session)

        jobs = source.fetch_jobs(search_terms=("paid media",), countries=())

        assert jobs[0].work_mode == "Hybrid"

    def test_work_mode_none_when_no_keyword_present(self) -> None:
        session = _mock_session(VALID_RESPONSE)
        source = ReedSource(api_key="test-key", session=session)

        jobs = source.fetch_jobs(search_terms=("paid media",), countries=())

        assert jobs[0].work_mode is None


class TestSalaryFormatting:
    def test_min_and_max_present(self) -> None:
        assert ReedSource._format_salary(40000, 48000) == "£40,000 - £48,000"

    def test_only_min_present(self) -> None:
        assert ReedSource._format_salary(40000, None) == "£40,000+"

    def test_only_max_present(self) -> None:
        assert ReedSource._format_salary(None, 48000) == "Up to £48,000"

    def test_both_zero_returns_none_not_misleading_zero(self) -> None:
        # Reed uses 0 to mean "unspecified", not "£0 salary" - must not
        # produce a misleading "£0 - £0" in the sheet.
        assert ReedSource._format_salary(0, 0) is None

    def test_both_none_returns_none(self) -> None:
        assert ReedSource._format_salary(None, None) is None

    def test_end_to_end_from_fixture(self) -> None:
        session = _mock_session(VALID_RESPONSE)
        source = ReedSource(api_key="test-key", session=session)

        jobs = source.fetch_jobs(search_terms=("paid media",), countries=())

        assert jobs[0].salary == "£40,000 - £48,000"


class TestErrorHandling:
    def test_raises_source_error_after_exhausting_retries(self, monkeypatch: pytest.MonkeyPatch) -> None:
        session = MagicMock()
        session.request.side_effect = requests.ConnectionError("network down")
        source = ReedSource(api_key="test-key", session=session)
        monkeypatch.setattr("sources.http_utils.time.sleep", lambda _: None)

        with pytest.raises(SourceError, match="Reed"):
            source.fetch_jobs(search_terms=("paid media",), countries=())
