"""
Standalone smoke test for the Adzuna connector.

Not part of the automated test suite (no network access there). Run
this locally, or via GitHub Actions workflow_dispatch, to confirm your
real credentials and the live Adzuna API behave as expected:

    python scripts/smoke_test_adzuna.py
"""
from __future__ import annotations

from config import get_settings
from sources.adzuna import AdzunaSource


def main() -> None:
    settings = get_settings()
    if not settings.sources.adzuna_enabled:
        print("ADZUNA_APP_ID / ADZUNA_APP_KEY not set in .env - nothing to test.")
        return

    source = AdzunaSource(
        app_id=settings.sources.adzuna_app_id, app_key=settings.sources.adzuna_app_key
    )
    jobs = source.fetch_jobs(search_terms=("paid media manager",), countries=("gb",))

    print(f"Fetched {len(jobs)} job(s) from Adzuna.\n")
    for job in jobs[:5]:
        print(f"- {job.job_title} @ {job.company} ({job.location}) -> {job.job_url}")


if __name__ == "__main__":
    main()
