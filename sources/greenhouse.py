"""
Greenhouse connector.

Implements JobSource against Greenhouse's public Job Board API:
    GET https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true
    response: {"jobs": [{"id", "title", "updated_at", "location": {"name"},
               "absolute_url", "content"}], "meta": {"total": N}}
No authentication required for read access.

Unlike Jooble/Adzuna, this is not a keyword search - it fetches every
open job for a known company slug. search_terms and countries are
ignored; the companies to poll come from the ATS watchlist
(config/ats_watchlist.json) instead. Title relevance filtering still
happens downstream in core/job_filter.py, same as any other source.

Reference: https://developers.greenhouse.io/job-board.html
"""
from __future__ import annotations

import re
from datetime import date, datetime

import requests

from models.job import Job
from sources.ats_watchlist import AtsTarget
from sources.base import JobSource
from sources.http_utils import fetch_json_with_retry
from utils.logger import get_logger

logger = get_logger(__name__)

_URL_TEMPLATE = "https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs"
_TIMEOUT_SECONDS = 10
_HTML_TAG_PATTERN = re.compile(r"<[^>]+>")


def _strip_html(html: str) -> str:
    """Lightweight HTML-to-text conversion for job descriptions.
    Not a full sanitizer - just enough to store a readable description
    without pulling in a heavy HTML parsing dependency."""
    text = _HTML_TAG_PATTERN.sub(" ", html)
    return " ".join(text.split())


class GreenhouseSource(JobSource):
    """ATS-direct source backed by Greenhouse's public Job Board API."""

    name = "greenhouse"

    def __init__(self, targets: tuple[AtsTarget, ...], session: requests.Session | None = None) -> None:
        if not targets:
            raise ValueError("GreenhouseSource requires at least one watchlist target")
        self._targets = targets
        self._session = session or requests.Session()

    def fetch_jobs(self, search_terms: tuple[str, ...], countries: tuple[str, ...]) -> list[Job]:
        """Fetch every open job for each watchlisted company. Ignores
        search_terms/countries - Greenhouse has no keyword search;
        relevance filtering happens downstream in core/job_filter.py."""
        jobs: list[Job] = []
        for target in self._targets:
            raw_jobs = self._fetch_board(target.slug)
            for raw_job in raw_jobs:
                job = self._normalize(raw_job, target.company_name)
                if job is not None:
                    jobs.append(job)
        return jobs

    def _fetch_board(self, board_token: str) -> list[dict]:
        url = _URL_TEMPLATE.format(board_token=board_token) + "?content=true"
        data = fetch_json_with_retry(
            self._session, "GET", url, source_name="Greenhouse", timeout=_TIMEOUT_SECONDS
        )
        return data.get("jobs", []) if isinstance(data, dict) else []

    def _normalize(self, raw_job: dict, company_name: str) -> Job | None:
        try:
            title = (raw_job.get("title") or "").strip()
            job_url = (raw_job.get("absolute_url") or "").strip()
            if not title or not job_url:
                logger.warning("Skipping Greenhouse job missing required fields: %r", raw_job)
                return None

            location = ((raw_job.get("location") or {}).get("name") or "").strip()
            raw_description = raw_job.get("content") or ""

            return Job(
                company=company_name,
                job_title=title,
                location=location,
                country="Unknown",
                source=self.name,
                job_url=job_url,
                posted_date=self._parse_date(raw_job.get("updated_at")),
                description=_strip_html(raw_description),
                # Greenhouse's public Job Board API never exposes salary
                # data, regardless of query params - unlike Ashby, there's
                # no opt-in flag for it. Job.salary stays None here.
            )
        except Exception as exc:  # defensive: one bad record shouldn't break the batch
            logger.warning("Failed to normalize Greenhouse job %r: %s", raw_job, exc)
            return None

    @staticmethod
    def _parse_date(raw_value: str | None) -> date | None:
        """Parse Greenhouse's ISO-8601 updated_at, e.g. '2013-07-02T19:39:23Z'
        or with a numeric UTC offset."""
        if not raw_value:
            return None
        try:
            return datetime.fromisoformat(raw_value.replace("Z", "+00:00")).date()
        except ValueError:
            logger.warning("Could not parse Greenhouse date value: %r", raw_value)
            return None
