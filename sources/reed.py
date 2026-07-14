"""
Reed.co.uk connector.

Implements JobSource against Reed's official Jobseeker Search API:
    GET https://www.reed.co.uk/api/1.0/search?keywords=...&resultsToTake=...
    Auth: HTTP Basic, API key as username, blank password
    response: {"results": [{"jobId", "employerName", "jobTitle",
               "locationName", "jobDescription", "date", "jobUrl"}],
               "totalResults": N}

Reed is UK-only - there's no country parameter to scope by, so this
connector ignores `countries` entirely and always searches nationwide.
Unlike Jooble, Reed's `keywords` field doesn't have documented OR
semantics for comma-separated terms, so one request is made per search
term rather than combining them - safer than guessing at undocumented
behavior, and still well within the free tier's 1,000 requests/day.

Reference: https://www.reed.co.uk/developers/Jobseeker
"""
from __future__ import annotations

from datetime import date, datetime

import requests

from models.job import Job
from sources.base import JobSource
from sources.http_utils import fetch_json_with_retry
from utils.logger import get_logger

logger = get_logger(__name__)

_URL = "https://www.reed.co.uk/api/1.0/search"
_TIMEOUT_SECONDS = 10
_RESULTS_PER_TERM = 100


class ReedSource(JobSource):
    """Discovery source backed by the Reed.co.uk Jobseeker Search API.
    UK coverage only."""

    name = "reed"

    def __init__(self, api_key: str, session: requests.Session | None = None) -> None:
        if not api_key:
            raise ValueError("ReedSource requires a non-empty api_key")
        self._api_key = api_key
        self._session = session or requests.Session()

    def fetch_jobs(self, search_terms: tuple[str, ...], countries: tuple[str, ...]) -> list[Job]:
        """Fetch jobs for each search term. `countries` is ignored -
        Reed has no country scoping, it's UK-only by nature."""
        jobs: list[Job] = []
        for term in search_terms:
            raw_jobs = self._search(term)
            for raw_job in raw_jobs:
                job = self._normalize(raw_job)
                if job is not None:
                    jobs.append(job)
        return jobs

    def _search(self, keywords: str) -> list[dict]:
        params = {"keywords": keywords, "resultsToTake": str(_RESULTS_PER_TERM)}
        data = fetch_json_with_retry(
            self._session,
            "GET",
            _URL,
            source_name="Reed",
            timeout=_TIMEOUT_SECONDS,
            params=params,
            auth=(self._api_key, ""),
        )
        return data.get("results", []) if isinstance(data, dict) else []

    def _normalize(self, raw_job: dict) -> Job | None:
        try:
            company = (raw_job.get("employerName") or "").strip()
            title = (raw_job.get("jobTitle") or "").strip()
            job_url = (raw_job.get("jobUrl") or "").strip()

            if not company or not title or not job_url:
                logger.warning("Skipping Reed job missing required fields: %r", raw_job)
                return None

            return Job(
                company=company,
                job_title=title,
                location=(raw_job.get("locationName") or "").strip(),
                country="United Kingdom",  # Reed is UK-only, unlike Unknown for global sources
                source=self.name,
                job_url=job_url,
                posted_date=self._parse_date(raw_job.get("date")),
                description=(raw_job.get("jobDescription") or "").strip(),
                salary=self._format_salary(raw_job.get("minimumSalary"), raw_job.get("maximumSalary")),
            )
        except Exception as exc:  # defensive: one bad record shouldn't break the batch
            logger.warning("Failed to normalize Reed job %r: %s", raw_job, exc)
            return None

    @staticmethod
    def _format_salary(minimum: object, maximum: object) -> str | None:
        """Reed gives numeric minimumSalary/maximumSalary in GBP, often
        0 or missing when unspecified. Format as a display string,
        returning None rather than a misleading '£0' when both are
        absent or zero."""
        min_val = minimum if isinstance(minimum, (int, float)) and minimum > 0 else None
        max_val = maximum if isinstance(maximum, (int, float)) and maximum > 0 else None
        if min_val and max_val:
            return f"£{min_val:,.0f} - £{max_val:,.0f}"
        if min_val:
            return f"£{min_val:,.0f}+"
        if max_val:
            return f"Up to £{max_val:,.0f}"
        return None

    @staticmethod
    def _parse_date(raw_value: str | None) -> date | None:
        """Reed dates are UK format: 'dd/mm/yyyy', e.g. '10/07/2026'."""
        if not raw_value:
            return None
        try:
            return datetime.strptime(raw_value, "%d/%m/%Y").date()
        except ValueError:
            logger.warning("Could not parse Reed date value: %r", raw_value)
            return None
