"""
Pipeline orchestrator.

Runs the full daily sequence: fetch jobs from every configured source,
dedupe, exclude by blocklisted terms, filter by title, score, and
persist qualified leads. One
failing source is logged and skipped rather than aborting the whole
run - this matters because this runs unattended, once a day, and a
single flaky API shouldn't block leads from every other source.

Google Sheets export is intentionally NOT called here yet (Milestone 6);
this orchestrator's job ends at persisting leads to SQLite.
"""
from __future__ import annotations

from datetime import datetime, timezone

from core.deduplicator import Deduplicator
from core.job_filter import ExcludeFilter, JobFilter
from core.scoring import ScoringEngine
from exceptions import SourceError
from models.company import Company
from models.job import Job
from models.run_stats import RunStats
from sources.base import JobSource
from storage.database import Database
from utils.logger import get_logger

logger = get_logger(__name__)


class Orchestrator:
    """Coordinates a single end-to-end pipeline run across all sources."""

    def __init__(
        self,
        sources: list[JobSource],
        database: Database,
        job_filter: JobFilter,
        scoring_engine: ScoringEngine,
        search_terms: tuple[str, ...],
        search_countries: tuple[str, ...],
        min_score: int,
        exclude_filter: ExcludeFilter | None = None,
    ) -> None:
        self._sources = sources
        self._database = database
        self._job_filter = job_filter
        self._scoring_engine = scoring_engine
        self._search_terms = search_terms
        self._search_countries = search_countries
        self._min_score = min_score
        self._exclude_filter = exclude_filter or ExcludeFilter(())
        self._deduplicator = Deduplicator(database)

    def run(self) -> RunStats:
        """Execute one full pipeline run and return the accumulated stats."""
        stats = RunStats()
        logger.info("Pipeline run starting: %d source(s) configured", len(self._sources))

        for source in self._sources:
            self._run_source(source, stats)

        stats.finish()
        logger.info(stats.summary())
        if stats.errors:
            for error in stats.errors:
                logger.error("Run error: %s", error)

        return stats

    def _run_source(self, source: JobSource, stats: RunStats) -> None:
        """Fetch and process all jobs from a single source. Any failure
        here is recorded in stats and does not propagate - the run
        continues with the next source."""
        try:
            jobs = source.fetch_jobs(
                search_terms=self._search_terms, countries=self._search_countries
            )
        except SourceError as exc:
            message = f"{source.name}: {exc}"
            logger.error("Source failed, skipping: %s", message)
            stats.record_error(message)
            return
        except Exception as exc:  # noqa: BLE001 - defensive: a connector
            # bug shouldn't be able to take down the whole daily run.
            message = f"{source.name}: unexpected error: {exc}"
            logger.exception("Source raised an unexpected exception, skipping: %s", source.name)
            stats.record_error(message)
            return

        logger.info("Fetched %d job(s) from %s", len(jobs), source.name)

        for job in jobs:
            stats.jobs_checked += 1
            self._process_job(job, stats)

    def _process_job(self, job: Job, stats: RunStats) -> None:
        """Run a single job through dedupe -> exclude -> filter -> score -> persist."""
        if not self._deduplicator.is_new(job):
            stats.jobs_duplicate += 1
            return

        if self._exclude_filter.is_excluded(job.job_title):
            stats.jobs_excluded += 1
            return

        matched_title = self._job_filter.match(job.job_title)
        if matched_title is None:
            stats.jobs_ignored += 1
            return

        score = self._scoring_engine.score(matched_title)
        if not self._scoring_engine.meets_threshold(score, self._min_score):
            stats.jobs_ignored += 1
            return

        stats.jobs_matched += 1

        inserted = self._database.insert_lead(job, score)
        if inserted:
            stats.jobs_inserted += 1
            self._database.upsert_company(
                Company(
                    name=job.company,
                    discovered_via=job.source,
                    discovered_at=datetime.now(timezone.utc),
                )
            )
