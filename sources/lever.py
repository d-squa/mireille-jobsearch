"""
Lever connector.

Implements JobSource against Lever's public Postings API:
    GET https://api.lever.co/v0/postings/{company}?mode=json
    response: a plain JSON array (not wrapped in an object) of
    postings: [{"id", "text", "hostedUrl", "applyUrl",
                "categories": {"team", "location", "commitment"},
                "createdAt" (epoch ms), "descriptionPlain",
                "workplaceType"}, ...]
No authentication required for read access.

Like Greenhouse, this fetches every open posting for a known company
slug rather than searching by keyword. search_terms/countries are
ignored; companies come from the ATS watchlist.

Reference: https://github.com/lever/postings-api
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import requests

from core.work_mode import classify_work_mode
from models.job import Job
from sources.ats_watchlist import AtsTarget
from sources.base import JobSource
from sources.http_utils import fetch_json_with_retry
from utils.logger import get_logger

logger = get_logger(__name__)

_URL_TEMPLATE = "https://api.lever.co/v0/postings/{company}?mode=json"
_TIMEOUT_SECONDS = 10

# Lever's real values, confirmed via their API - maps directly to our
# three labels rather than needing text inference.
_WORKPLACE_TYPE_MAP = {"remote": "Remote", "hybrid": "Hybrid", "on-site": "Onsite", "onsite": "Onsite"}


class LeverSource(JobSource):
    """ATS-direct source backed by Lever's public Postings API."""

    name = "lever"

    def __init__(self, targets: tuple[AtsTarget, ...], session: requests.Session | None = None) -> None:
        if not targets:
            raise ValueError("LeverSource requires at least one watchlist target")
        self._targets = targets
        self._session = session or requests.Session()

    def fetch_jobs(self, search_terms: tuple[str, ...], countries: tuple[str, ...]) -> list[Job]:
        """Fetch every open posting for each watchlisted company. Ignores
        search_terms/countries - relevance filtering happens downstream
        in core/job_filter.py."""
        jobs: list[Job] = []
        for target in self._targets:
            raw_postings = self._fetch_postings(target.slug)
            for raw_posting in raw_postings:
                job = self._normalize(raw_posting, target.company_name)
                if job is not None:
                    jobs.append(job)
        return jobs

    def _fetch_postings(self, company_slug: str) -> list[dict]:
        url = _URL_TEMPLATE.format(company=company_slug)
        data = fetch_json_with_retry(
            self._session, "GET", url, source_name="Lever", timeout=_TIMEOUT_SECONDS
        )
        # Lever returns a bare array, unlike Jooble/Greenhouse/Ashby's
        # object-wrapped responses.
        return data if isinstance(data, list) else []

    def _normalize(self, raw_posting: dict, company_name: str) -> Job | None:
        try:
            title = (raw_posting.get("text") or "").strip()
            job_url = (raw_posting.get("hostedUrl") or raw_posting.get("applyUrl") or "").strip()
            if not title or not job_url:
                logger.warning("Skipping Lever posting missing required fields: %r", raw_posting)
                return None

            categories = raw_posting.get("categories") or {}
            location = (categories.get("location") or "").strip()

            return Job(
                company=company_name,
                job_title=title,
                location=location,
                country="Unknown",
                source=self.name,
                job_url=job_url,
                posted_date=self._parse_created_at(raw_posting.get("createdAt")),
                description=(raw_posting.get("descriptionPlain") or "").strip(),
                # Lever's public Postings API doesn't expose salary/
                # compensation data. Job.salary stays None here.
                work_mode=self._extract_work_mode(raw_posting, title, location),
            )
        except Exception as exc:  # defensive: one bad record shouldn't break the batch
            logger.warning("Failed to normalize Lever posting %r: %s", raw_posting, exc)
            return None

    @staticmethod
    def _extract_work_mode(raw_posting: dict, title: str, location: str) -> str | None:
        """Lever provides a real structured workplaceType field
        ('on-site', 'remote', 'hybrid') - use it directly rather than
        guessing from text. Falls back to keyword matching only if
        that field is missing or an unrecognized value."""
        raw_type = (raw_posting.get("workplaceType") or "").strip().lower()
        mapped = _WORKPLACE_TYPE_MAP.get(raw_type)
        if mapped is not None:
            return mapped
        description = raw_posting.get("descriptionPlain") or ""
        return classify_work_mode(title, location, description)

    @staticmethod
    def _parse_created_at(raw_value: object) -> date | None:
        """Lever's createdAt is a millisecond epoch timestamp (int)."""
        if raw_value is None:
            return None
        try:
            return datetime.fromtimestamp(int(raw_value) / 1000, tz=timezone.utc).date()
        except (TypeError, ValueError, OverflowError):
            logger.warning("Could not parse Lever createdAt value: %r", raw_value)
            return None
