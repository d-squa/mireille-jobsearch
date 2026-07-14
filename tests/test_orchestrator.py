"""Tests for pipeline/orchestrator.py.

Uses simple in-test fake JobSource implementations rather than mocking
Jooble/Adzuna specifically - the orchestrator should work identically
regardless of which JobSource implementation it's given.
"""
from datetime import date

import pytest

from core.job_filter import ExcludeFilter, JobFilter
from core.scoring import ScoringEngine
from exceptions import SourceError
from models.job import Job
from pipeline.orchestrator import Orchestrator
from sources.base import JobSource
from storage.database import Database

CANONICAL_TITLES_AND_SCORES = {
    "Paid Media Manager": 100,
    "Media Buyer": 90,
    "Campaign Manager": 70,
    "Digital Marketing Manager": 60,
}


def _job(**overrides: object) -> Job:
    defaults: dict[str, object] = dict(
        company="Acme Real Estate",
        job_title="Paid Media Manager",
        location="Doha, Qatar",
        country="Qatar",
        source="fake",
        job_url="https://example.com/jobs/1",
        posted_date=date(2026, 7, 1),
        description="desc",
    )
    defaults.update(overrides)
    return Job(**defaults)  # type: ignore[arg-type]


class FakeSource(JobSource):
    """A JobSource that returns a fixed list of jobs, for testing."""

    def __init__(self, name: str, jobs: list[Job] | None = None, error: Exception | None = None) -> None:
        self.name = name
        self._jobs = jobs or []
        self._error = error

    def fetch_jobs(self, search_terms: tuple[str, ...], countries: tuple[str, ...]) -> list[Job]:
        if self._error is not None:
            raise self._error
        return self._jobs


@pytest.fixture
def database() -> Database:
    db = Database(":memory:")
    db.initialize_schema()
    yield db
    db.close()


@pytest.fixture
def job_filter() -> JobFilter:
    return JobFilter(canonical_titles=tuple(CANONICAL_TITLES_AND_SCORES.keys()), threshold=82)


@pytest.fixture
def scoring_engine() -> ScoringEngine:
    return ScoringEngine(CANONICAL_TITLES_AND_SCORES)


def _make_orchestrator(
    sources: list[JobSource],
    database: Database,
    job_filter: JobFilter,
    scoring_engine: ScoringEngine,
    min_score: int = 50,
    exclude_filter: ExcludeFilter | None = None,
) -> Orchestrator:
    return Orchestrator(
        sources=sources,
        database=database,
        job_filter=job_filter,
        scoring_engine=scoring_engine,
        search_terms=("paid media",),
        search_countries=("gb",),
        min_score=min_score,
        exclude_filter=exclude_filter,
    )


class TestOrchestratorHappyPath:
    def test_matching_job_above_threshold_is_inserted(
        self, database: Database, job_filter: JobFilter, scoring_engine: ScoringEngine
    ) -> None:
        source = FakeSource("fake", jobs=[_job(job_title="Paid Media Manager")])
        orchestrator = _make_orchestrator([source], database, job_filter, scoring_engine)

        stats = orchestrator.run()

        assert stats.jobs_checked == 1
        assert stats.jobs_matched == 1
        assert stats.jobs_inserted == 1
        assert stats.jobs_ignored == 0
        assert stats.jobs_duplicate == 0
        assert len(database.get_unexported_leads()) == 1

    def test_non_matching_title_is_ignored(
        self, database: Database, job_filter: JobFilter, scoring_engine: ScoringEngine
    ) -> None:
        source = FakeSource("fake", jobs=[_job(job_title="Software Engineer")])
        orchestrator = _make_orchestrator([source], database, job_filter, scoring_engine)

        stats = orchestrator.run()

        assert stats.jobs_checked == 1
        assert stats.jobs_matched == 0
        assert stats.jobs_ignored == 1
        assert stats.jobs_inserted == 0

    def test_matching_title_below_min_score_is_ignored_not_inserted(
        self, database: Database, job_filter: JobFilter, scoring_engine: ScoringEngine
    ) -> None:
        # Digital Marketing Manager scores 60 - set min_score above that.
        source = FakeSource("fake", jobs=[_job(job_title="Digital Marketing Manager")])
        orchestrator = _make_orchestrator(
            [source], database, job_filter, scoring_engine, min_score=75
        )

        stats = orchestrator.run()

        assert stats.jobs_ignored == 1
        assert stats.jobs_inserted == 0

    def test_company_upserted_only_for_inserted_leads(
        self, database: Database, job_filter: JobFilter, scoring_engine: ScoringEngine
    ) -> None:
        matching = _job(job_title="Paid Media Manager", company="Good Co")
        non_matching = _job(job_title="Software Engineer", company="Bad Co", job_url="https://x.com/2")
        source = FakeSource("fake", jobs=[matching, non_matching])
        orchestrator = _make_orchestrator([source], database, job_filter, scoring_engine)

        orchestrator.run()

        assert database.get_company("Good Co") is not None
        assert database.get_company("Bad Co") is None


class TestOrchestratorDedup:
    def test_duplicate_job_across_two_sources_counted_once(
        self, database: Database, job_filter: JobFilter, scoring_engine: ScoringEngine
    ) -> None:
        job = _job(job_title="Paid Media Manager")
        source_a = FakeSource("source_a", jobs=[job])
        source_b = FakeSource("source_b", jobs=[job])  # same job, different source object
        orchestrator = _make_orchestrator([source_a, source_b], database, job_filter, scoring_engine)

        stats = orchestrator.run()

        assert stats.jobs_checked == 2  # both fetches counted
        assert stats.jobs_inserted == 1  # only inserted once
        assert stats.jobs_duplicate == 1

    def test_rerun_does_not_reinsert_same_lead(
        self, database: Database, job_filter: JobFilter, scoring_engine: ScoringEngine
    ) -> None:
        job = _job(job_title="Paid Media Manager")
        source = FakeSource("fake", jobs=[job])
        orchestrator = _make_orchestrator([source], database, job_filter, scoring_engine)

        first_stats = orchestrator.run()
        second_stats = orchestrator.run()

        assert first_stats.jobs_inserted == 1
        assert second_stats.jobs_inserted == 0
        assert second_stats.jobs_duplicate == 1
        assert len(database.get_unexported_leads()) == 1


class TestOrchestratorErrorIsolation:
    def test_one_failing_source_does_not_block_others(
        self, database: Database, job_filter: JobFilter, scoring_engine: ScoringEngine
    ) -> None:
        failing_source = FakeSource("broken_source", error=SourceError("API down"))
        working_source = FakeSource("working_source", jobs=[_job(job_title="Media Buyer")])
        orchestrator = _make_orchestrator(
            [failing_source, working_source], database, job_filter, scoring_engine
        )

        stats = orchestrator.run()

        assert stats.jobs_inserted == 1
        assert len(stats.errors) == 1
        assert "broken_source" in stats.errors[0]

    def test_unexpected_exception_in_source_is_caught_too(
        self, database: Database, job_filter: JobFilter, scoring_engine: ScoringEngine
    ) -> None:
        failing_source = FakeSource("crashy_source", error=RuntimeError("bug in connector"))
        working_source = FakeSource("working_source", jobs=[_job(job_title="Media Buyer")])
        orchestrator = _make_orchestrator(
            [failing_source, working_source], database, job_filter, scoring_engine
        )

        stats = orchestrator.run()

        assert stats.jobs_inserted == 1
        assert len(stats.errors) == 1
        assert "crashy_source" in stats.errors[0]

    def test_all_sources_failing_still_returns_stats_without_raising(
        self, database: Database, job_filter: JobFilter, scoring_engine: ScoringEngine
    ) -> None:
        source = FakeSource("broken", error=SourceError("down"))
        orchestrator = _make_orchestrator([source], database, job_filter, scoring_engine)

        stats = orchestrator.run()

        assert stats.jobs_checked == 0
        assert len(stats.errors) == 1


class TestOrchestratorRunStats:
    def test_stats_summary_reflects_mixed_batch(
        self, database: Database, job_filter: JobFilter, scoring_engine: ScoringEngine
    ) -> None:
        jobs = [
            _job(job_title="Paid Media Manager", job_url="https://x.com/1"),  # matched, inserted
            _job(job_title="Software Engineer", job_url="https://x.com/2"),  # ignored
            _job(job_title="Paid Media Manager", job_url="https://x.com/1"),  # duplicate
        ]
        source = FakeSource("fake", jobs=jobs)
        orchestrator = _make_orchestrator([source], database, job_filter, scoring_engine)

        stats = orchestrator.run()

        assert stats.jobs_checked == 3
        assert stats.jobs_inserted == 1
        assert stats.jobs_ignored == 1
        assert stats.jobs_duplicate == 1
        assert stats.duration_seconds >= 0


class TestOrchestratorExcludeFilter:
    def test_excluded_title_is_not_inserted(
        self, database: Database, job_filter: JobFilter, scoring_engine: ScoringEngine
    ) -> None:
        source = FakeSource("fake", jobs=[_job(job_title="Paid Media Manager Intern")])
        exclude_filter = ExcludeFilter(("Intern",))
        orchestrator = _make_orchestrator(
            [source], database, job_filter, scoring_engine, exclude_filter=exclude_filter
        )

        stats = orchestrator.run()

        assert stats.jobs_excluded == 1
        assert stats.jobs_matched == 0
        assert stats.jobs_inserted == 0
        assert len(database.get_unexported_leads()) == 0

    def test_excluded_job_takes_priority_over_a_title_that_would_otherwise_match(
        self, database: Database, job_filter: JobFilter, scoring_engine: ScoringEngine
    ) -> None:
        # "Paid Media Manager" would normally match and score 100 -
        # exclusion must short-circuit before that ever happens.
        source = FakeSource("fake", jobs=[_job(job_title="Paid Media Manager - Unpaid Internship")])
        exclude_filter = ExcludeFilter(("Unpaid",))
        orchestrator = _make_orchestrator(
            [source], database, job_filter, scoring_engine, exclude_filter=exclude_filter
        )

        stats = orchestrator.run()

        assert stats.jobs_excluded == 1
        assert stats.jobs_inserted == 0

    def test_non_excluded_titles_still_process_normally(
        self, database: Database, job_filter: JobFilter, scoring_engine: ScoringEngine
    ) -> None:
        source = FakeSource("fake", jobs=[_job(job_title="Paid Media Manager")])
        exclude_filter = ExcludeFilter(("Intern", "Volunteer"))
        orchestrator = _make_orchestrator(
            [source], database, job_filter, scoring_engine, exclude_filter=exclude_filter
        )

        stats = orchestrator.run()

        assert stats.jobs_excluded == 0
        assert stats.jobs_inserted == 1

    def test_no_exclude_filter_configured_behaves_identically_to_before(
        self, database: Database, job_filter: JobFilter, scoring_engine: ScoringEngine
    ) -> None:
        source = FakeSource("fake", jobs=[_job(job_title="Paid Media Manager")])
        orchestrator = _make_orchestrator([source], database, job_filter, scoring_engine)

        stats = orchestrator.run()

        assert stats.jobs_excluded == 0
        assert stats.jobs_inserted == 1

    def test_excluded_and_duplicate_counted_separately(
        self, database: Database, job_filter: JobFilter, scoring_engine: ScoringEngine
    ) -> None:
        jobs = [
            _job(job_title="Marketing Intern", job_url="https://x.com/1"),
            _job(job_title="Paid Media Manager", job_url="https://x.com/2"),
            _job(job_title="Paid Media Manager", job_url="https://x.com/2"),  # duplicate
        ]
        source = FakeSource("fake", jobs=jobs)
        exclude_filter = ExcludeFilter(("Intern",))
        orchestrator = _make_orchestrator(
            [source], database, job_filter, scoring_engine, exclude_filter=exclude_filter
        )

        stats = orchestrator.run()

        assert stats.jobs_excluded == 1
        assert stats.jobs_duplicate == 1
        assert stats.jobs_inserted == 1
