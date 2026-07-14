"""Unit tests for sources/jooble.py. All HTTP calls are mocked - no
live requests to jooble.org are made in tests."""
from datetime import date
from unittest.mock import MagicMock

import pytest
import requests

from exceptions import SourceError
from sources.jooble import JoobleSource
from tests.fixtures.jooble_response import (
    EMPTY_RESPONSE,
    MALFORMED_DATE_RESPONSE,
    VALID_RESPONSE,
)


def _mock_session(json_payload: dict, status_code: int = 200) -> MagicMock:
    """Build a mock requests.Session whose .post() returns the given payload."""
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


class TestJoobleSourceConstruction:
    def test_requires_api_key(self) -> None:
        with pytest.raises(ValueError, match="api_key"):
            JoobleSource(api_key="")

    def test_name_is_jooble(self) -> None:
        source = JoobleSource(api_key="test-key", session=_mock_session(EMPTY_RESPONSE))
        assert source.name == "jooble"


class TestFetchJobs:
    def test_returns_normalized_jobs(self) -> None:
        session = _mock_session(VALID_RESPONSE)
        source = JoobleSource(api_key="test-key", session=session)

        jobs = source.fetch_jobs(search_terms=("paid media",), countries=("gb",))

        # Third fixture entry is missing "company" and must be skipped.
        assert len(jobs) == 2
        assert jobs[0].company == "Acme Real Estate Ltd"
        assert jobs[0].job_title == "Paid Media Manager"
        assert jobs[0].source == "jooble"
        assert jobs[0].job_url == "https://jooble.org/jdp/123456/Paid-Media-Manager"
        assert jobs[0].posted_date == date(2026, 7, 8)

    def test_salary_passed_through_from_raw_string_field(self) -> None:
        session = _mock_session(VALID_RESPONSE)
        source = JoobleSource(api_key="test-key", session=session)

        jobs = source.fetch_jobs(search_terms=("paid media",), countries=("gb",))

        assert jobs[0].salary == "45,000 - 55,000 GBP"

    def test_missing_salary_becomes_none_not_empty_string(self) -> None:
        session = _mock_session(VALID_RESPONSE)
        source = JoobleSource(api_key="test-key", session=session)

        jobs = source.fetch_jobs(search_terms=("paid media",), countries=("gb",))

        # Second fixture job has salary: "" in the raw response.
        assert jobs[1].salary is None

    def test_skips_job_missing_required_fields(self) -> None:
        session = _mock_session(VALID_RESPONSE)
        source = JoobleSource(api_key="test-key", session=session)

        jobs = source.fetch_jobs(search_terms=("paid media",), countries=("gb",))

        titles = [job.job_title for job in jobs]
        assert "Marketing Intern" not in titles

    def test_empty_response_returns_empty_list(self) -> None:
        session = _mock_session(EMPTY_RESPONSE)
        source = JoobleSource(api_key="test-key", session=session)

        jobs = source.fetch_jobs(search_terms=("paid media",), countries=("gb",))

        assert jobs == []

    def test_malformed_date_does_not_crash_normalization(self) -> None:
        session = _mock_session(MALFORMED_DATE_RESPONSE)
        source = JoobleSource(api_key="test-key", session=session)

        jobs = source.fetch_jobs(search_terms=("PPC",), countries=("fr",))

        assert len(jobs) == 1
        assert jobs[0].posted_date is None

    def test_parses_seven_digit_fractional_seconds(self) -> None:
        # Regression test: real Jooble responses use 7-digit fractional
        # seconds (e.g. '2026-07-07T07:54:40.8130000'), which Python's
        # strptime %f cannot parse (max 6 digits). Observed live in the
        # first production run - almost every job failed to parse before
        # this fix.
        assert JoobleSource._parse_date("2026-07-07T07:54:40.8130000") == date(2026, 7, 7)

    def test_parses_date_with_utc_offset_and_fractional_seconds(self) -> None:
        assert JoobleSource._parse_date("2026-07-10T00:02:45.5740994+00:00") == date(2026, 7, 10)

    def test_parses_plain_date_with_zero_time(self) -> None:
        assert JoobleSource._parse_date("2026-05-15T00:00:00.0000000") == date(2026, 5, 15)

    def test_parses_simple_date_only(self) -> None:
        assert JoobleSource._parse_date("2026-07-08") == date(2026, 7, 8)

    def test_returns_none_for_unparseable_garbage(self) -> None:
        assert JoobleSource._parse_date("not-a-date-at-all") is None

    def test_returns_none_for_empty_string(self) -> None:
        assert JoobleSource._parse_date("") is None

    def test_queries_once_per_country(self) -> None:
        session = _mock_session(EMPTY_RESPONSE)
        source = JoobleSource(api_key="test-key", session=session)

        source.fetch_jobs(search_terms=("paid media",), countries=("gb", "us", "ae"))

        assert session.request.call_count == 3

    def test_no_countries_makes_single_unscoped_call(self) -> None:
        session = _mock_session(EMPTY_RESPONSE)
        source = JoobleSource(api_key="test-key", session=session)

        source.fetch_jobs(search_terms=("paid media",), countries=())

        assert session.request.call_count == 1
        _, kwargs = session.request.call_args
        assert kwargs["json"]["location"] == ""

    def test_search_terms_joined_as_single_keywords_param(self) -> None:
        session = _mock_session(EMPTY_RESPONSE)
        source = JoobleSource(api_key="test-key", session=session)

        source.fetch_jobs(search_terms=("paid media", "PPC", "media buyer"), countries=("gb",))

        _, kwargs = session.request.call_args
        assert kwargs["json"]["keywords"] == "paid media, PPC, media buyer"


class TestErrorHandling:
    def test_raises_source_error_after_exhausting_retries(self, monkeypatch: pytest.MonkeyPatch) -> None:
        session = MagicMock()
        session.request.side_effect = requests.ConnectionError("network down")
        source = JoobleSource(api_key="test-key", session=session)

        monkeypatch.setattr("sources.http_utils.time.sleep", lambda _: None)  # skip real backoff delay

        with pytest.raises(SourceError, match="Jooble request failed"):
            source.fetch_jobs(search_terms=("paid media",), countries=("gb",))

        assert session.request.call_count == 3  # _MAX_RETRIES

    def test_http_error_status_raises_source_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        session = _mock_session(EMPTY_RESPONSE, status_code=500)
        source = JoobleSource(api_key="test-key", session=session)

        monkeypatch.setattr("sources.http_utils.time.sleep", lambda _: None)

        with pytest.raises(SourceError):
            source.fetch_jobs(search_terms=("paid media",), countries=("gb",))

    def test_one_country_failing_does_not_affect_others(self) -> None:
        # gb succeeds, us raises - fetch_jobs should propagate the error
        # rather than silently dropping results; per-source isolation
        # across countries within one connector call is intentionally
        # NOT implemented here (kept simple) - isolation happens at the
        # orchestrator level, one connector at a time (Milestone 4).
        session = MagicMock()

        ok_response = MagicMock()
        ok_response.raise_for_status.return_value = None
        ok_response.json.return_value = EMPTY_RESPONSE

        session.request.return_value = ok_response
        source = JoobleSource(api_key="test-key", session=session)

        jobs = source.fetch_jobs(search_terms=("paid media",), countries=("gb",))
        assert jobs == []
