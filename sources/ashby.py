"""
Ashby connector.

Implements JobSource against Ashby's public Job Postings API:
    GET https://api.ashbyhq.com/posting-api/job-board/{job_board_name}
    response: {"apiVersion": "1", "jobs": [{"title", "location",
               "department", "team", "isRemote", "workplaceType",
               "descriptionPlain", "publishedAt", "employmentType",
               "jobUrl", "applyUrl"}, ...]}
No authentication required for read access.

Like Greenhouse/Lever, this fetches every open posting for a known
company slug rather than searching by keyword. search_terms/countries
are ignored; companies come from the ATS watchlist.

Reference: https://developers.ashbyhq.com/docs/public-job-posting-api
"""
from __future__ import annotations

from datetime import date, datetime

import requests

from models.job import Job
from sources.ats_watchlist import AtsTarget
from sources.base import JobSource
from sources.http_utils import fetch_json_with_retry
from utils.logger import get_logger

logger = get_logger(__name__)

_URL_TEMPLATE = "https://api.ashbyhq.com/posting-api/job-board/{job_board_name}"
_TIMEOUT_SECONDS = 10


class AshbySource(JobSource):
    """ATS-direct source backed by Ashby's public Job Postings API."""

    name = "ashby"

    def __init__(self, targets: tuple[AtsTarget, ...], session: requests.Session | None = None) -> None:
        if not targets:
            raise ValueError("AshbySource requires at least one watchlist target")
        self._targets = targets
        self._session = session or requests.Session()

    def fetch_jobs(self, search_terms: tuple[str, ...], countries: tuple[str, ...]) -> list[Job]:
        """Fetch every open posting for each watchlisted company. Ignores
        search_terms/countries - relevance filtering happens downstream
        in core/job_filter.py."""
        jobs: list[Job] = []
        for target in self._targets:
            raw_postings = self._fetch_board(target.slug)
            for raw_posting in raw_postings:
                job = self._normalize(raw_posting, target.company_name)
                if job is not None:
                    jobs.append(job)
        return jobs

    def _fetch_board(self, job_board_name: str) -> list[dict]:
        url = f"{_URL_TEMPLATE.format(job_board_name=job_board_name)}?includeCompensation=true"
        data = fetch_json_with_retry(
            self._session, "GET", url, source_name="Ashby", timeout=_TIMEOUT_SECONDS
        )
        return data.get("jobs", []) if isinstance(data, dict) else []

    def _normalize(self, raw_posting: dict, company_name: str) -> Job | None:
        try:
            title = (raw_posting.get("title") or "").strip()
            job_url = (raw_posting.get("jobUrl") or raw_posting.get("applyUrl") or "").strip()
            if not title or not job_url:
                logger.warning("Skipping Ashby posting missing required fields: %r", raw_posting)
                return None

            location = (raw_posting.get("location") or "").strip()

            return Job(
                company=company_name,
                job_title=title,
                location=location,
                country="Unknown",
                source=self.name,
                job_url=job_url,
                posted_date=self._parse_date(raw_posting.get("publishedAt")),
                description=(raw_posting.get("descriptionPlain") or "").strip(),
                salary=self._extract_salary(raw_posting),
            )
        except Exception as exc:  # defensive: one bad record shouldn't break the batch
            logger.warning("Failed to normalize Ashby posting %r: %s", raw_posting, exc)
            return None

    @staticmethod
    def _extract_salary(raw_posting: dict) -> str | None:
        """Ashby includes a per-posting 'compensation' object only when
        requested via includeCompensation=true, and only when the
        employer chose to publish it - commonly present for US roles
        (state pay-transparency laws), often absent internationally.
        compensationTierSummary is already a formatted display string,
        e.g. '$81K - $87K - Offers Equity' - pass it through as-is
        rather than re-parsing it into numeric fields."""
        compensation = raw_posting.get("compensation") or {}
        summary = compensation.get("compensationTierSummary")
        return summary.strip() if isinstance(summary, str) and summary.strip() else None

    @staticmethod
    def _parse_date(raw_value: str | None) -> date | None:
        """Ashby's publishedAt is ISO-8601 with milliseconds and offset,
        e.g. '2021-04-30T16:21:55.393+00:00'."""
        if not raw_value:
            return None
        try:
            return datetime.fromisoformat(raw_value).date()
        except ValueError:
            logger.warning("Could not parse Ashby date value: %r", raw_value)
            return None
