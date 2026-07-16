"""Unit tests for storage/database.py using an in-memory SQLite DB."""
import sqlite3
from datetime import date, datetime

import pytest

from models.company import Company
from models.job import Job
from storage.database import Database


@pytest.fixture
def db() -> Database:
    database = Database(":memory:")
    database.initialize_schema()
    yield database
    database.close()


def _sample_job(**overrides: object) -> Job:
    defaults: dict[str, object] = dict(
        company="Acme Real Estate",
        job_title="Paid Media Manager",
        location="Doha, Qatar",
        country="Qatar",
        source="jooble",
        job_url="https://example.com/jobs/123",
        posted_date=date(2026, 7, 1),
        description="Great opportunity for a paid media manager.",
    )
    defaults.update(overrides)
    return Job(**defaults)  # type: ignore[arg-type]


class TestSchema:
    def test_initialize_schema_creates_tables(self, db: Database) -> None:
        cursor = db._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = {row["name"] for row in cursor.fetchall()}
        assert {"companies", "jobs_seen", "leads"}.issubset(tables)

    def test_initialize_schema_is_idempotent(self, db: Database) -> None:
        # Calling twice must not raise or duplicate anything.
        db.initialize_schema()
        db.initialize_schema()

    def test_salary_migration_adds_column_to_pre_existing_file_database(self, tmp_path) -> None:
        db_path = tmp_path / "legacy.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            """
            CREATE TABLE leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_hash TEXT NOT NULL UNIQUE,
                score INTEGER NOT NULL,
                company TEXT NOT NULL,
                job_title TEXT NOT NULL,
                location TEXT NOT NULL,
                country TEXT NOT NULL,
                source TEXT NOT NULL,
                job_url TEXT NOT NULL,
                posted_date TEXT,
                found_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'New',
                exported_at TEXT
            )
            """
        )
        conn.execute(
            "INSERT INTO leads (job_hash, score, company, job_title, location, "
            "country, source, job_url, found_at) VALUES "
            "('abc123', 90, 'Old Co', 'Old Title', 'Somewhere', 'Unknown', "
            "'jooble', 'https://x.com', '2026-01-01T00:00:00')"
        )
        conn.commit()
        conn.close()

        db = Database(db_path)
        db.initialize_schema()  # must not raise, and must add the missing column

        cursor = db._conn.execute("SELECT * FROM leads WHERE job_hash = 'abc123'")
        row = cursor.fetchone()
        assert row["company"] == "Old Co"  # pre-existing data survived
        assert row["salary"] is None  # new column, backfilled as NULL

        # And new inserts with salary now work correctly on this
        # migrated database.
        new_job = _sample_job(job_url="https://x.com/new", salary="£50,000 - £60,000")
        db.mark_seen(new_job)
        assert db.insert_lead(new_job, score=95) is True
        db.close()

    def test_work_mode_migration_from_database_that_already_has_salary(self, tmp_path) -> None:
        # The exact real-world state: a database that already went
        # through the salary migration (has that column) but predates
        # work_mode. Confirms the migration loop handles a database
        # that's missing only ONE of the two columns, not just "zero
        # columns" or "both columns".
        db_path = tmp_path / "post_salary_legacy.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            """
            CREATE TABLE leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_hash TEXT NOT NULL UNIQUE,
                score INTEGER NOT NULL,
                company TEXT NOT NULL,
                job_title TEXT NOT NULL,
                salary TEXT,
                location TEXT NOT NULL,
                country TEXT NOT NULL,
                source TEXT NOT NULL,
                job_url TEXT NOT NULL,
                posted_date TEXT,
                found_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'New',
                exported_at TEXT
            )
            """
        )
        conn.execute(
            "INSERT INTO leads (job_hash, score, company, job_title, salary, location, "
            "country, source, job_url, found_at) VALUES "
            "('def456', 90, 'Real Co', 'Real Title', '£50,000', 'Somewhere', 'Unknown', "
            "'jooble', 'https://y.com', '2026-01-01T00:00:00')"
        )
        conn.commit()
        conn.close()

        db = Database(db_path)
        db.initialize_schema()

        cursor = db._conn.execute("SELECT * FROM leads WHERE job_hash = 'def456'")
        row = cursor.fetchone()
        assert row["company"] == "Real Co"  # pre-existing data survived
        assert row["salary"] == "£50,000"  # pre-existing salary data survived
        assert row["work_mode"] is None  # new column, backfilled as NULL
        db.close()


class TestJobsSeenDedup:
    def test_mark_seen_first_time_returns_true(self, db: Database) -> None:
        job = _sample_job()
        assert db.mark_seen(job) is True
        assert db.has_seen(job.dedup_hash()) is True

    def test_mark_seen_duplicate_returns_false(self, db: Database) -> None:
        job = _sample_job()
        db.mark_seen(job)
        assert db.mark_seen(job) is False

    def test_has_seen_false_for_unknown_hash(self, db: Database) -> None:
        assert db.has_seen("nonexistent-hash") is False

    def test_different_jobs_produce_different_hashes(self, db: Database) -> None:
        job_a = _sample_job(job_title="Paid Media Manager")
        job_b = _sample_job(job_title="Media Buyer")
        assert job_a.dedup_hash() != job_b.dedup_hash()

    def test_same_job_different_url_same_hash(self, db: Database) -> None:
        # Dedup key deliberately ignores job_url, since ATS platforms
        # sometimes reissue the same posting under a new URL.
        job_a = _sample_job(job_url="https://example.com/jobs/123")
        job_b = _sample_job(job_url="https://example.com/jobs/999-edited")
        assert job_a.dedup_hash() == job_b.dedup_hash()


class TestLeads:
    def test_insert_lead_succeeds(self, db: Database) -> None:
        job = _sample_job()
        db.mark_seen(job)
        assert db.insert_lead(job, score=100) is True

    def test_insert_lead_duplicate_returns_false(self, db: Database) -> None:
        job = _sample_job()
        db.mark_seen(job)
        db.insert_lead(job, score=100)
        assert db.insert_lead(job, score=100) is False

    def test_get_unexported_leads_returns_new_lead(self, db: Database) -> None:
        job = _sample_job()
        db.mark_seen(job)
        db.insert_lead(job, score=90)
        unexported = db.get_unexported_leads()
        assert len(unexported) == 1
        assert unexported[0]["company"] == "Acme Real Estate"
        assert unexported[0]["status"] == "New"

    def test_mark_exported_excludes_from_unexported(self, db: Database) -> None:
        job = _sample_job()
        db.mark_seen(job)
        db.insert_lead(job, score=90)
        db.mark_exported([job.dedup_hash()])
        assert db.get_unexported_leads() == []

    def test_reset_exported_status_all_leads(self, db: Database) -> None:
        job_a = _sample_job(job_title="Paid Media Manager", job_url="https://x.com/1")
        job_b = _sample_job(job_title="Media Buyer", job_url="https://x.com/2")
        for job in (job_a, job_b):
            db.mark_seen(job)
            db.insert_lead(job, score=90)
        db.mark_exported([job_a.dedup_hash(), job_b.dedup_hash()])
        assert db.get_unexported_leads() == []

        updated_count = db.reset_exported_status()

        assert updated_count == 2
        assert len(db.get_unexported_leads()) == 2

    def test_reset_exported_status_specific_hashes_only(self, db: Database) -> None:
        job_a = _sample_job(job_title="Paid Media Manager", job_url="https://x.com/1")
        job_b = _sample_job(job_title="Media Buyer", job_url="https://x.com/2")
        for job in (job_a, job_b):
            db.mark_seen(job)
            db.insert_lead(job, score=90)
        db.mark_exported([job_a.dedup_hash(), job_b.dedup_hash()])

        updated_count = db.reset_exported_status([job_a.dedup_hash()])

        assert updated_count == 1
        unexported = db.get_unexported_leads()
        assert len(unexported) == 1
        assert unexported[0]["job_hash"] == job_a.dedup_hash()

    def test_reset_exported_status_empty_list_is_a_no_op(self, db: Database) -> None:
        job = _sample_job()
        db.mark_seen(job)
        db.insert_lead(job, score=90)
        db.mark_exported([job.dedup_hash()])

        updated_count = db.reset_exported_status([])

        assert updated_count == 0
        assert db.get_unexported_leads() == []

    def test_reset_exported_status_on_already_unexported_leads_updates_zero(self, db: Database) -> None:
        job = _sample_job()
        db.mark_seen(job)
        db.insert_lead(job, score=90)
        # Never exported - reset should find nothing to update.
        updated_count = db.reset_exported_status()
        assert updated_count == 0

    def test_leads_ordered_by_score_descending(self, db: Database) -> None:
        low = _sample_job(job_title="Campaign Manager", job_url="https://x.com/1")
        high = _sample_job(job_title="Paid Media Manager", job_url="https://x.com/2")
        db.mark_seen(low)
        db.insert_lead(low, score=70)
        db.mark_seen(high)
        db.insert_lead(high, score=100)
        leads = db.get_unexported_leads()
        assert [lead["score"] for lead in leads] == [100, 70]


class TestCompanies:
    def test_upsert_company_inserts_new(self, db: Database) -> None:
        company = Company(
            name="Acme Real Estate",
            discovered_via="jooble",
            discovered_at=datetime(2026, 7, 1, 9, 0, 0),
        )
        db.upsert_company(company)
        row = db.get_company("Acme Real Estate")
        assert row is not None
        assert row["discovered_via"] == "jooble"

    def test_upsert_company_does_not_duplicate(self, db: Database) -> None:
        company = Company(
            name="Acme Real Estate",
            discovered_via="jooble",
            discovered_at=datetime(2026, 7, 1, 9, 0, 0),
        )
        db.upsert_company(company)
        db.upsert_company(company)
        cursor = db._conn.execute(
            "SELECT COUNT(*) as cnt FROM companies WHERE name = ?", ("Acme Real Estate",)
        )
        assert cursor.fetchone()["cnt"] == 1

    def test_get_company_returns_none_when_missing(self, db: Database) -> None:
        assert db.get_company("Nonexistent Co") is None
