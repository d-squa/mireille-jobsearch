"""Unit tests for sources/greenhouse.py, sources/lever.py, sources/ashby.py.
All HTTP calls are mocked - no live requests to any ATS platform."""
from datetime import date
from unittest.mock import MagicMock

import pytest
import requests

from exceptions import SourceError
from sources.ashby import AshbySource
from sources.ats_watchlist import AtsTarget
from sources.greenhouse import GreenhouseSource
from sources.lever import LeverSource
from tests.fixtures.ats_responses import (
    ASHBY_EMPTY_RESPONSE,
    ASHBY_VALID_RESPONSE,
    GREENHOUSE_EMPTY_RESPONSE,
    GREENHOUSE_VALID_RESPONSE,
    LEVER_EMPTY_RESPONSE,
    LEVER_VALID_RESPONSE,
)

ACME_TARGETS = (AtsTarget(slug="acme", company_name="Acme Corp"),)


def _mock_session(json_payload, status_code: int = 200) -> MagicMock:
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


class TestGreenhouseSource:
    def test_requires_at_least_one_target(self) -> None:
        with pytest.raises(ValueError, match="at least one"):
            GreenhouseSource(targets=())

    def test_returns_normalized_jobs_and_skips_incomplete(self) -> None:
        session = _mock_session(GREENHOUSE_VALID_RESPONSE)
        source = GreenhouseSource(targets=ACME_TARGETS, session=session)

        jobs = source.fetch_jobs(search_terms=(), countries=())

        assert len(jobs) == 2  # third entry missing absolute_url, skipped
        assert jobs[0].company == "Acme Corp"
        assert jobs[0].job_title == "Paid Media Manager"
        assert jobs[0].location == "Dubai, UAE"
        assert jobs[0].source == "greenhouse"
        assert jobs[0].posted_date == date(2026, 7, 5)

    def test_strips_html_from_description(self) -> None:
        session = _mock_session(GREENHOUSE_VALID_RESPONSE)
        source = GreenhouseSource(targets=ACME_TARGETS, session=session)

        jobs = source.fetch_jobs(search_terms=(), countries=())

        assert "<" not in jobs[0].description
        assert "growth team" in jobs[0].description

    def test_salary_always_none_greenhouse_api_never_exposes_it(self) -> None:
        session = _mock_session(GREENHOUSE_VALID_RESPONSE)
        source = GreenhouseSource(targets=ACME_TARGETS, session=session)

        jobs = source.fetch_jobs(search_terms=(), countries=())

        assert all(job.salary is None for job in jobs)

    def test_empty_board_returns_empty_list(self) -> None:
        session = _mock_session(GREENHOUSE_EMPTY_RESPONSE)
        source = GreenhouseSource(targets=ACME_TARGETS, session=session)

        assert source.fetch_jobs(search_terms=(), countries=()) == []

    def test_ignores_search_terms_and_countries(self) -> None:
        # These params exist only to satisfy the JobSource interface -
        # Greenhouse has no keyword search, it returns everything.
        session = _mock_session(GREENHOUSE_EMPTY_RESPONSE)
        source = GreenhouseSource(targets=ACME_TARGETS, session=session)

        source.fetch_jobs(search_terms=("anything",), countries=("gb", "us"))

        assert session.request.call_count == 1  # one call per target, not per country

    def test_queries_once_per_target(self) -> None:
        two_targets = (
            AtsTarget(slug="acme", company_name="Acme Corp"),
            AtsTarget(slug="beta", company_name="Beta Inc"),
        )
        session = _mock_session(GREENHOUSE_EMPTY_RESPONSE)
        source = GreenhouseSource(targets=two_targets, session=session)

        source.fetch_jobs(search_terms=(), countries=())

        assert session.request.call_count == 2

    def test_raises_source_error_after_retries_exhausted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        session = MagicMock()
        session.request.side_effect = requests.ConnectionError("network down")
        source = GreenhouseSource(targets=ACME_TARGETS, session=session)
        monkeypatch.setattr("sources.http_utils.time.sleep", lambda _: None)

        with pytest.raises(SourceError, match="Greenhouse"):
            source.fetch_jobs(search_terms=(), countries=())


class TestLeverSource:
    def test_requires_at_least_one_target(self) -> None:
        with pytest.raises(ValueError, match="at least one"):
            LeverSource(targets=())

    def test_returns_normalized_jobs_and_skips_incomplete(self) -> None:
        session = _mock_session(LEVER_VALID_RESPONSE)
        source = LeverSource(targets=ACME_TARGETS, session=session)

        jobs = source.fetch_jobs(search_terms=(), countries=())

        assert len(jobs) == 2  # third entry missing text/title, skipped
        assert jobs[0].company == "Acme Corp"
        assert jobs[0].job_title == "Media Buyer"
        assert jobs[0].location == "London"
        assert jobs[0].source == "lever"

    def test_handles_bare_array_response_shape(self) -> None:
        # Lever's response is a raw JSON array, not wrapped in an object -
        # this is the detail most likely to be implemented wrong.
        session = _mock_session(LEVER_EMPTY_RESPONSE)
        source = LeverSource(targets=ACME_TARGETS, session=session)

        assert source.fetch_jobs(search_terms=(), countries=()) == []

    def test_parses_epoch_millisecond_created_at(self) -> None:
        session = _mock_session(LEVER_VALID_RESPONSE)
        source = LeverSource(targets=ACME_TARGETS, session=session)

        jobs = source.fetch_jobs(search_terms=(), countries=())

        assert jobs[0].posted_date is not None
        assert isinstance(jobs[0].posted_date, date)

    def test_falls_back_to_apply_url_when_hosted_url_missing(self) -> None:
        response = [
            {
                "id": "x",
                "text": "Campaign Manager",
                "hostedUrl": "",
                "applyUrl": "https://jobs.lever.co/acme/x/apply",
                "categories": {"location": "Paris"},
                "createdAt": 1783036800000,
                "descriptionPlain": "desc",
            }
        ]
        session = _mock_session(response)
        source = LeverSource(targets=ACME_TARGETS, session=session)

        jobs = source.fetch_jobs(search_terms=(), countries=())

        assert jobs[0].job_url == "https://jobs.lever.co/acme/x/apply"

    def test_salary_always_none_lever_public_api_never_exposes_it(self) -> None:
        session = _mock_session(LEVER_VALID_RESPONSE)
        source = LeverSource(targets=ACME_TARGETS, session=session)

        jobs = source.fetch_jobs(search_terms=(), countries=())

        assert all(job.salary is None for job in jobs)


class TestAshbySource:
    def test_requires_at_least_one_target(self) -> None:
        with pytest.raises(ValueError, match="at least one"):
            AshbySource(targets=())

    def test_returns_normalized_jobs_and_skips_incomplete(self) -> None:
        session = _mock_session(ASHBY_VALID_RESPONSE)
        source = AshbySource(targets=ACME_TARGETS, session=session)

        jobs = source.fetch_jobs(search_terms=(), countries=())

        assert len(jobs) == 2  # third entry missing title, skipped
        assert jobs[0].company == "Acme Corp"
        assert jobs[0].job_title == "Performance Marketing Manager"
        assert jobs[0].location == "Doha, Qatar"
        assert jobs[0].source == "ashby"
        assert jobs[0].posted_date == date(2026, 7, 6)

    def test_empty_board_returns_empty_list(self) -> None:
        session = _mock_session(ASHBY_EMPTY_RESPONSE)
        source = AshbySource(targets=ACME_TARGETS, session=session)

        assert source.fetch_jobs(search_terms=(), countries=()) == []

    def test_parses_iso_date_with_milliseconds_and_offset(self) -> None:
        session = _mock_session(ASHBY_VALID_RESPONSE)
        source = AshbySource(targets=ACME_TARGETS, session=session)

        jobs = source.fetch_jobs(search_terms=(), countries=())

        assert jobs[1].posted_date == date(2026, 7, 5)

    def test_requests_include_compensation_param(self) -> None:
        session = _mock_session(ASHBY_EMPTY_RESPONSE)
        source = AshbySource(targets=ACME_TARGETS, session=session)

        source.fetch_jobs(search_terms=(), countries=())

        args, _ = session.request.call_args
        assert "includeCompensation=true" in args[1]

    def test_extracts_compensation_tier_summary_as_salary(self) -> None:
        session = _mock_session(ASHBY_VALID_RESPONSE)
        source = AshbySource(targets=ACME_TARGETS, session=session)

        jobs = source.fetch_jobs(search_terms=(), countries=())

        assert jobs[0].salary == "$81K - $87K - Offers Bonus"

    def test_missing_compensation_object_gives_none_salary(self) -> None:
        session = _mock_session(ASHBY_VALID_RESPONSE)
        source = AshbySource(targets=ACME_TARGETS, session=session)

        jobs = source.fetch_jobs(search_terms=(), countries=())

        # Second fixture job (Product Designer) has no compensation key
        # at all - common for international roles per Ashby's own docs.
        assert jobs[1].salary is None
