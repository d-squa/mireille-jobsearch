"""
Standalone smoke test for the Reed connector.

Not part of the automated test suite (no network access there). Run
this locally, or via GitHub Actions workflow_dispatch, to confirm your
real API key and the live Reed API behave as expected:

    python scripts/smoke_test_reed.py
"""
from __future__ import annotations

from config import get_settings
from sources.reed import ReedSource


def main() -> None:
    settings = get_settings()
    if not settings.sources.reed_enabled:
        print("REED_API_KEY is not set in .env - nothing to test.")
        return

    source = ReedSource(api_key=settings.sources.reed_api_key)
    jobs = source.fetch_jobs(search_terms=("paid media manager",), countries=())

    print(f"Fetched {len(jobs)} job(s) from Reed.\n")
    for job in jobs[:5]:
        print(f"- {job.job_title} @ {job.company} ({job.location}) -> {job.job_url}")


if __name__ == "__main__":
    main()
