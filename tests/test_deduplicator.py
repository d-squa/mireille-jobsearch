"""Unit tests for core/deduplicator.py."""
from datetime import date

import pytest

from core.deduplicator import Deduplicator
from models.job import Job
from storage.database import Database


@pytest.fixture
def database() -> Database:
    db = Database(":memory:")
    db.initialize_schema()
    yield db
    db.close()


def _job(**overrides: object) -> Job:
    defaults: dict[str, object] = dict(
        company="Acme Real Estate",
        job_title="Paid Media Manager",
        location="Doha, Qatar",
        country="Qatar",
        source="jooble",
        job_url="https://example.com/jobs/123",
        posted_date=date(2026, 7, 1),
        description="desc",
    )
    defaults.update(overrides)
    return Job(**defaults)  # type: ignore[arg-type]


class TestDeduplicator:
    def test_first_sighting_is_new(self, database: Database) -> None:
        dedup = Deduplicator(database)
        assert dedup.is_new(_job()) is True

    def test_repeat_within_same_run_is_not_new(self, database: Database) -> None:
        dedup = Deduplicator(database)
        job = _job()
        dedup.is_new(job)
        assert dedup.is_new(job) is False

    def test_repeat_within_same_run_uses_in_memory_cache_not_extra_db_write(
        self, database: Database
    ) -> None:
        dedup = Deduplicator(database)
        job = _job()
        dedup.is_new(job)
        dedup.is_new(job)
        dedup.is_new(job)
        cursor = database._conn.execute("SELECT COUNT(*) as cnt FROM jobs_seen")
        assert cursor.fetchone()["cnt"] == 1

    def test_job_seen_in_previous_run_is_not_new(self, database: Database) -> None:
        job = _job()
        # Simulate a previous run already having recorded this job.
        database.mark_seen(job)

        dedup = Deduplicator(database)
        assert dedup.is_new(job) is False

    def test_different_jobs_are_both_new(self, database: Database) -> None:
        dedup = Deduplicator(database)
        job_a = _job(job_title="Paid Media Manager")
        job_b = _job(job_title="Media Buyer")
        assert dedup.is_new(job_a) is True
        assert dedup.is_new(job_b) is True
