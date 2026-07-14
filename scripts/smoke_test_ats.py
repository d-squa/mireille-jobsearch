"""
Standalone smoke test for the ATS connectors (Greenhouse, Lever, Ashby).

Not part of the automated test suite (no network access there). Add
real company slugs to config/ats_watchlist.json first, then run this
locally to confirm the connectors work against live data:

    python scripts/smoke_test_ats.py
"""
from __future__ import annotations

from config import get_settings
from sources.ashby import AshbySource
from sources.ats_watchlist import load_ats_watchlist
from sources.greenhouse import GreenhouseSource
from sources.lever import LeverSource


def main() -> None:
    settings = get_settings()
    if settings.ats_watchlist_file is None:
        print("ATS_WATCHLIST_FILE is not set in .env - nothing to test.")
        return

    watchlist = load_ats_watchlist(settings.ats_watchlist_file)

    if watchlist["greenhouse"]:
        jobs = GreenhouseSource(targets=watchlist["greenhouse"]).fetch_jobs(
            search_terms=(), countries=()
        )
        print(f"Greenhouse: fetched {len(jobs)} job(s)")
        for job in jobs[:3]:
            print(f"  - {job.job_title} @ {job.company} -> {job.job_url}")
    else:
        print("Greenhouse: no targets configured, skipped.")

    if watchlist["lever"]:
        jobs = LeverSource(targets=watchlist["lever"]).fetch_jobs(search_terms=(), countries=())
        print(f"Lever: fetched {len(jobs)} job(s)")
        for job in jobs[:3]:
            print(f"  - {job.job_title} @ {job.company} -> {job.job_url}")
    else:
        print("Lever: no targets configured, skipped.")

    if watchlist["ashby"]:
        jobs = AshbySource(targets=watchlist["ashby"]).fetch_jobs(search_terms=(), countries=())
        print(f"Ashby: fetched {len(jobs)} job(s)")
        for job in jobs[:3]:
            print(f"  - {job.job_title} @ {job.company} -> {job.job_url}")
    else:
        print("Ashby: no targets configured, skipped.")


if __name__ == "__main__":
    main()
