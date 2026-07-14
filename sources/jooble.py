"""
Jooble connector.

Implements JobSource against Jooble's REST API:
    POST https://jooble.org/api/{api_key}
    body: {"keywords": "...", "location": "...", "page": "1"}
    response: {"totalCount": int, "jobs": [{"title", "location",
               "snippet", "salary", "source", "type", "link",
               "company", "updated", "id"}, ...]}

Reference: https://help.jooble.org/en/support/solutions/articles/60001448238
"""
from __future__ import annotations

import re
from datetime import date

import requests

from exceptions import SourceError
from models.job import Job
from sources.base import JobSource
from sources.http_utils import fetch_json_with_retry
from utils.logger import get_logger

logger = get_logger(__name__)

_BASE_URL = "https://jooble.org/api/{api_key}"
_TIMEOUT_SECONDS = 10
_LEADING_DATE_PATTERN = re.compile(r"^(\d{4}-\d{2}-\d{2})")


class JoobleSource(JobSource):
    """Discovery source backed by the Jooble job search API."""

    name = "jooble"

    def __init__(self, api_key: str, session: requests.Session | None = None) -> None:
        if not api_key:
            raise ValueError("JoobleSource requires a non-empty api_key")
        self._api_key = api_key
        self._session = session or requests.Session()
        self._url = _BASE_URL.format(api_key=api_key)

    def fetch_jobs(self, search_terms: tuple[str, ...], countries: tuple[str, ...]) -> list[Job]:
        """Fetch jobs for all search terms, once per country.

        Jooble's `keywords` field accepts a comma-separated list treated
        as a single search, so all search_terms are sent together in
        one request per country rather than one request per term - this
        keeps request volume low against the free-tier quota.
        """
        keywords = ", ".join(search_terms)
        # If no countries are configured, do a single unscoped search.
        locations: tuple[str, ...] = countries or ("",)

        jobs: list[Job] = []
        for location in locations:
            raw_jobs = self._search(keywords=keywords, location=location)
            for raw_job in raw_jobs:
                job = self._normalize(raw_job)
                if job is not None:
                    jobs.append(job)
        return jobs

    def _search(self, keywords: str, location: str) -> list[dict]:
        """POST a single search request with retry/backoff. Raises
        SourceError if all attempts fail."""
        payload = {"keywords": keywords, "location": location, "page": "1"}
        data = fetch_json_with_retry(
            self._session,
            "POST",
            self._url,
            source_name="Jooble",
            json=payload,
            timeout=_TIMEOUT_SECONDS,
        )
        return data.get("jobs", []) if isinstance(data, dict) else []

    def _normalize(self, raw_job: dict) -> Job | None:
        """Convert a raw Jooble job dict into a Job. Returns None and
        logs a warning if required fields are missing, rather than
        raising - one malformed entry shouldn't drop the whole batch."""
        try:
            company = (raw_job.get("company") or "").strip()
            title = (raw_job.get("title") or "").strip()
            job_url = (raw_job.get("link") or "").strip()

            if not company or not title or not job_url:
                logger.warning("Skipping Jooble job missing required fields: %r", raw_job)
                return None

            return Job(
                company=company,
                job_title=title,
                location=(raw_job.get("location") or "").strip(),
                country="Unknown",  # resolved later by core/location parsing
                source=self.name,
                job_url=job_url,
                posted_date=self._parse_date(raw_job.get("updated")),
                description=(raw_job.get("snippet") or "").strip(),
                salary=(raw_job.get("salary") or "").strip() or None,
            )
        except Exception as exc:  # defensive: never let one bad record break the batch
            logger.warning("Failed to normalize Jooble job %r: %s", raw_job, exc)
            return None

    @staticmethod
    def _parse_date(raw_value: str | None) -> date | None:
        """Best-effort parse of Jooble's 'updated' timestamp string.

        Jooble's timestamp precision is inconsistent in practice - plain
        dates, full datetimes, and datetimes with fractional seconds of
        varying digit counts (including 7-digit fractions, which
        strptime's %f cannot parse - it only supports up to 6). Since
        Job.posted_date only needs date precision, sidestep the whole
        problem by extracting just the leading YYYY-MM-DD rather than
        trying to parse every timestamp variant Jooble might send.
        """
        if not raw_value:
            return None
        match = _LEADING_DATE_PATTERN.match(raw_value)
        if not match:
            logger.warning("Could not parse Jooble date value: %r", raw_value)
            return None
        try:
            return date.fromisoformat(match.group(1))
        except ValueError:
            logger.warning("Could not parse Jooble date value: %r", raw_value)
            return None
