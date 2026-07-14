"""
Standalone smoke test for the Jooble connector.

Not part of the automated test suite (no network access there).
Run this locally, once, to confirm your real API key and the live
Jooble API behave the way the connector expects:

    python scripts/smoke_test_jooble.py
"""
from __future__ import annotations

from config import get_settings
from sources.jooble import JoobleSource


def main() -> None:
    settings = get_settings()
    if not settings.sources.jooble_enabled:
        print("JOOBLE_API_KEY is not set in .env - nothing to test.")
        return

    source = JoobleSource(api_key=settings.sources.jooble_api_key)
    jobs = source.fetch_jobs(search_terms=("paid media manager",), countries=("gb",))

    print(f"Fetched {len(jobs)} job(s) from Jooble.\n")
    for job in jobs[:5]:
        print(f"- {job.job_title} @ {job.company} ({job.location}) -> {job.job_url}")


if __name__ == "__main__":
    main()
