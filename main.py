"""
ActiPlan Lead Discovery Engine - entrypoint.

Wires configuration, sources, filtering, scoring, and storage into
the orchestrator and runs one full pipeline pass. Google Sheets export
is not yet wired in here (Milestone 6) - this run ends at persisting
qualified leads to SQLite.

Run:
    python main.py
"""
from __future__ import annotations

import sys

from config import ConfigError, Settings, get_settings
from core.job_filter import ExcludeFilter, JobFilter
from core.scoring import ScoringConfigError, ScoringEngine
from pipeline.orchestrator import Orchestrator
from sources.adzuna import AdzunaSource
from sources.ashby import AshbySource
from sources.ats_watchlist import AtsWatchlistError, load_ats_watchlist
from sources.base import JobSource
from sources.greenhouse import GreenhouseSource
from sources.jooble import JoobleSource
from sources.lever import LeverSource
from sources.reed import ReedSource
from storage.database import Database
from storage.google_sheet import GoogleSheetError, GoogleSheetExporter
from utils.logger import configure_logging, get_logger


def _build_sources(settings: Settings) -> list[JobSource]:
    """Instantiate every configured, enabled discovery and ATS source.

    A source with no credentials/watchlist entries configured is simply
    omitted here, not an error - config.py already guarantees at least
    one Tier 1 discovery source is enabled before the app can start;
    Tier 2 ATS sources are optional on top of that.
    """
    sources: list[JobSource] = []
    if settings.sources.jooble_enabled:
        sources.append(JoobleSource(api_key=settings.sources.jooble_api_key))
    if settings.sources.reed_enabled:
        sources.append(ReedSource(api_key=settings.sources.reed_api_key))
    if settings.sources.adzuna_enabled:
        sources.append(
            AdzunaSource(
                app_id=settings.sources.adzuna_app_id, app_key=settings.sources.adzuna_app_key
            )
        )

    if settings.ats_watchlist_file is not None:
        try:
            watchlist = load_ats_watchlist(settings.ats_watchlist_file)
        except AtsWatchlistError as exc:
            get_logger(__name__).error("Failed to load ATS watchlist, skipping ATS sources: %s", exc)
            watchlist = {"greenhouse": (), "lever": (), "ashby": ()}

        if watchlist["greenhouse"]:
            sources.append(GreenhouseSource(targets=watchlist["greenhouse"]))
        if watchlist["lever"]:
            sources.append(LeverSource(targets=watchlist["lever"]))
        if watchlist["ashby"]:
            sources.append(AshbySource(targets=watchlist["ashby"]))

    return sources


def _export_leads(settings: Settings, database: Database) -> None:
    """Export any unexported leads to Google Sheets. Non-fatal: a
    failure here is logged and the run still exits cleanly - leads
    stay marked unexported in the DB and are retried next run."""
    logger = get_logger(__name__)

    if not settings.google_sheet_id:
        logger.info("GOOGLE_SHEET_ID not set, skipping Google Sheets export.")
        return

    unexported = database.get_unexported_leads()
    if not unexported:
        logger.info("No unexported leads to send to Google Sheets.")
        return

    try:
        exporter = GoogleSheetExporter(
            sheet_id=settings.google_sheet_id,
            service_account_file=settings.google_service_account_file,
        )
        exported_hashes = exporter.export_leads(unexported)
        database.mark_exported(exported_hashes)
        logger.info("Exported %d lead(s) to Google Sheets.", len(exported_hashes))
    except GoogleSheetError as exc:
        logger.error("Google Sheets export failed, leads remain unexported: %s", exc)
    except Exception as exc:  # noqa: BLE001 - defensive: export must never
        # crash the run, same principle as per-source isolation in the
        # orchestrator. Anything not already wrapped as GoogleSheetError
        # still needs to be caught here rather than propagate.
        logger.exception("Unexpected error during Google Sheets export, leads remain unexported: %s", exc)


def main() -> int:
    """Application entrypoint. Returns a process exit code."""
    try:
        settings = get_settings()
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1

    configure_logging(settings.log_level, settings.log_file)
    logger = get_logger(__name__)

    logger.info("ActiPlan Lead Discovery Engine starting up")
    logger.info(
        "Discovery sources enabled: jooble=%s adzuna=%s reed=%s",
        settings.sources.jooble_enabled,
        settings.sources.adzuna_enabled,
        settings.sources.reed_enabled,
    )

    try:
        scoring_engine = ScoringEngine.from_file(settings.title_scores_file)
    except ScoringConfigError as exc:
        logger.error("Failed to load scoring configuration: %s", exc)
        return 1

    job_filter = JobFilter(
        canonical_titles=scoring_engine.canonical_titles,
        threshold=settings.fuzzy_match_threshold,
    )
    exclude_filter = ExcludeFilter(settings.exclude_terms)
    if settings.exclude_terms:
        logger.info("Exclude terms active: %s", ", ".join(settings.exclude_terms))
    sources = _build_sources(settings)

    with Database(settings.database_path) as database:
        database.initialize_schema()

        orchestrator = Orchestrator(
            sources=sources,
            database=database,
            job_filter=job_filter,
            scoring_engine=scoring_engine,
            search_terms=settings.search_terms,
            search_countries=settings.search_countries,
            min_score=settings.min_score,
            exclude_filter=exclude_filter,
        )
        stats = orchestrator.run()
        _export_leads(settings, database)

    if stats.errors:
        logger.warning("Run completed with %d error(s) - see log above for details.", len(stats.errors))

    return 0


if __name__ == "__main__":
    sys.exit(main())
