"""
Adzuna connector.

Implements JobSource against Adzuna's REST API:
    GET https://api.adzuna.com/v1/api/jobs/{country}/search/{page}
    params: app_id, app_key, what (keywords), results_per_page
    response: {"results": [{"title", "company": {"display_name"},
               "location": {"display_name"}, "created", "redirect_url",
               "description", "id"}, ...]}

Unlike Jooble's location (free text) or Reed (no country param at
all), Adzuna's country is a required URL path segment validated
against a fixed list of ~20 supported countries (mainly US/UK/EU/
Australia/Canada/India - notably NOT Gulf/MENA, confirmed during
Milestone 2 research). Querying an unsupported country returns a real
HTTP 404. Each (search_term, country) pair is requested and error-
isolated independently here, so one unsupported country in
SEARCH_COUNTRIES doesn't abort results from the countries that do
work - this matters in practice since the default config includes
"ae", which Adzuna doesn't support.

Reference: https://developer.adzuna.com/docs/search
"""
from __future__ import annotations

from datetime import date, datetime

import requests

from exceptions import SourceError
from models.job import Job
from sources.base import JobSource
from sources.http_utils import fetch_json_with_retry
from utils.logger import get_logger

logger = get_logger(__name__)

_URL_TEMPLATE = "https://api.adzuna.com/v1/api/jobs/{country}/search/1"
_TIMEOUT_SECONDS = 10
_RESULTS_PER_PAGE = 50

# Friendly display names for the country codes this project searches
# by default. Falls back to the raw code (uppercased) for anything not
# listed here rather than failing - this is a display nicety, not
# something that should ever block a job from being recorded.
_COUNTRY_NAMES = {
    "gb": "United Kingdom",
    "us": "United States",
    "de": "Germany",
    "fr": "France",
    "nl": "Netherlands",
    "ca": "Canada",
    "au": "Australia",
    "in": "India",
}


class AdzunaSource(JobSource):
    """Discovery source backed by the Adzuna job search API."""

    name = "adzuna"

    def __init__(self, app_id: str, app_key: str, session: requests.Session | None = None) -> None:
        if not app_id or not app_key:
            raise ValueError("AdzunaSource requires non-empty app_id and app_key")
        self._app_id = app_id
        self._app_key = app_key
        self._session = session or requests.Session()

    def fetch_jobs(self, search_terms: tuple[str, ...], countries: tuple[str, ...]) -> list[Job]:
        """Fetch jobs for every (search_term, country) combination.

        A country Adzuna doesn't support is logged and skipped, not
        fatal to the whole fetch - see module docstring for why this
        isolation matters specifically for Adzuna.
        """
        if not countries:
            logger.warning("AdzunaSource requires at least one country; defaulting to 'gb'")
            countries = ("gb",)

        jobs: list[Job] = []
        for country in countries:
            for term in search_terms:
                try:
                    raw_jobs = self._search(term, country)
                except SourceError as exc:
                    logger.warning(
                        "Adzuna search failed for country=%r term=%r, skipping: %s",
                        country,
                        term,
                        exc,
                    )
                    continue
                for raw_job in raw_jobs:
                    job = self._normalize(raw_job, country)
                    if job is not None:
                        jobs.append(job)
        return jobs

    def _search(self, keywords: str, country: str) -> list[dict]:
        url = _URL_TEMPLATE.format(country=country)
        params = {
            "app_id": self._app_id,
            "app_key": self._app_key,
            "what": keywords,
            "results_per_page": str(_RESULTS_PER_PAGE),
            "content-type": "application/json",
        }
        data = fetch_json_with_retry(
            self._session, "GET", url, source_name="Adzuna", timeout=_TIMEOUT_SECONDS, params=params
        )
        return data.get("results", []) if isinstance(data, dict) else []

    def _normalize(self, raw_job: dict, country_code: str) -> Job | None:
        try:
            company = ((raw_job.get("company") or {}).get("display_name") or "").strip()
            title = (raw_job.get("title") or "").strip()
            job_url = (raw_job.get("redirect_url") or "").strip()

            if not company or not title or not job_url:
                logger.warning("Skipping Adzuna job missing required fields: %r", raw_job)
                return None

            location = ((raw_job.get("location") or {}).get("display_name") or "").strip()

            return Job(
                company=company,
                job_title=title,
                location=location,
                country=_COUNTRY_NAMES.get(country_code, country_code.upper()),
                source=self.name,
                job_url=job_url,
                posted_date=self._parse_date(raw_job.get("created")),
                description=(raw_job.get("description") or "").strip(),
                salary=self._format_salary(raw_job.get("salary_min"), raw_job.get("salary_max")),
            )
        except Exception as exc:  # defensive: one bad record shouldn't break the batch
            logger.warning("Failed to normalize Adzuna job %r: %s", raw_job, exc)
            return None

    @staticmethod
    def _format_salary(minimum: object, maximum: object) -> str | None:
        """Adzuna gives numeric salary_min/salary_max, currency implied
        by country rather than stated explicitly in the response. Kept
        as a plain number rather than guessing a currency symbol per
        country - safer than silently mislabeling e.g. a German salary
        with a £ sign."""
        min_val = minimum if isinstance(minimum, (int, float)) and minimum > 0 else None
        max_val = maximum if isinstance(maximum, (int, float)) and maximum > 0 else None
        if min_val and max_val:
            return f"{min_val:,.0f} - {max_val:,.0f}"
        if min_val:
            return f"{min_val:,.0f}+"
        if max_val:
            return f"Up to {max_val:,.0f}"
        return None

    @staticmethod
    def _parse_date(raw_value: str | None) -> date | None:
        """Adzuna's created field is ISO-8601 with a Z suffix, e.g.
        '2013-11-08T18:07:39Z'."""
        if not raw_value:
            return None
        try:
            return datetime.fromisoformat(raw_value.replace("Z", "+00:00")).date()
        except ValueError:
            logger.warning("Could not parse Adzuna date value: %r", raw_value)
            return None
