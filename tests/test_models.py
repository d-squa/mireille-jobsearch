"""Unit tests for models/job.py and models/run_stats.py."""
from datetime import date

from models.job import Job
from models.run_stats import RunStats


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


class TestJobDedupHash:
    def test_hash_is_deterministic(self) -> None:
        job = _job()
        assert job.dedup_hash() == job.dedup_hash()

    def test_hash_ignores_case_and_whitespace(self) -> None:
        job_a = _job(job_title="Paid Media Manager", company="Acme Real Estate")
        job_b = _job(job_title="  paid   media manager  ", company="ACME REAL ESTATE")
        assert job_a.dedup_hash() == job_b.dedup_hash()

    def test_hash_differs_by_source(self) -> None:
        job_a = _job(source="jooble")
        job_b = _job(source="adzuna")
        assert job_a.dedup_hash() != job_b.dedup_hash()

    def test_hash_differs_by_location(self) -> None:
        job_a = _job(location="Doha, Qatar")
        job_b = _job(location="Dubai, UAE")
        assert job_a.dedup_hash() != job_b.dedup_hash()


class TestRunStats:
    def test_summary_contains_all_counters(self) -> None:
        stats = RunStats(
            jobs_checked=100,
            jobs_matched=20,
            jobs_excluded=3,
            jobs_ignored=80,
            jobs_duplicate=5,
            jobs_inserted=15,
        )
        stats.record_error("source X timed out")
        stats.finish()
        summary = stats.summary()
        assert "Jobs checked: 100" in summary
        assert "Matched: 20" in summary
        assert "Excluded: 3" in summary
        assert "Ignored: 80" in summary
        assert "Duplicates: 5" in summary
        assert "Inserted: 15" in summary
        assert "Errors: 1" in summary

    def test_duration_increases_over_time(self) -> None:
        stats = RunStats()
        stats.finish()
        assert stats.duration_seconds >= 0
