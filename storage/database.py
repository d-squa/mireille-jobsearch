"""
SQLite storage layer.

Owns three tables:
    companies  - the watchlist, populated as a byproduct of discovery
    jobs_seen  - append-only dedup ledger; every job ever encountered,
                 matched or not, keyed by Job.dedup_hash()
    leads      - qualified, scored jobs that passed the filter and
                 threshold; this is what gets exported to Sheets

The dedup guarantee lives here: insert_lead() and mark_seen() both use
INSERT OR IGNORE against a UNIQUE constraint on the hash, so a job seen
on day 1 can never be written twice, even across process restarts.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterator

from models.company import Company
from models.job import Job

_SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    discovered_via TEXT NOT NULL,
    discovered_at TEXT NOT NULL,
    greenhouse_slug TEXT,
    lever_slug TEXT,
    ashby_slug TEXT,
    active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS jobs_seen (
    job_hash TEXT PRIMARY KEY,
    company TEXT NOT NULL,
    job_title TEXT NOT NULL,
    source TEXT NOT NULL,
    first_seen_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_hash TEXT NOT NULL UNIQUE REFERENCES jobs_seen(job_hash),
    score INTEGER NOT NULL,
    company TEXT NOT NULL,
    job_title TEXT NOT NULL,
    salary TEXT,
    work_mode TEXT,
    location TEXT NOT NULL,
    country TEXT NOT NULL,
    source TEXT NOT NULL,
    job_url TEXT NOT NULL,
    posted_date TEXT,
    found_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'New',
    exported_at TEXT
);
"""


class Database:
    """Thin wrapper around a SQLite connection for the Lead Discovery Engine.

    Usage:
        db = Database(Path("./data/lead_discovery.db"))
        db.initialize_schema()
        ...
        db.close()

    Or as a context manager:
        with Database(path) as db:
            db.initialize_schema()
    """

    def __init__(self, database_path: Path | str) -> None:
        self._path = str(database_path)
        if self._path != ":memory:":
            Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")

    def initialize_schema(self) -> None:
        """Create tables if they don't already exist, and apply any
        pending lightweight migrations. Safe to call every run."""
        self._conn.executescript(_SCHEMA)
        self._conn.commit()
        self._migrate_add_columns()

    def _migrate_add_columns(self) -> None:
        """Add the salary and work_mode columns to an existing leads
        table that predates them.

        CREATE TABLE IF NOT EXISTS is a no-op on a table that already
        exists, so a schema change alone doesn't reach databases
        created before these columns existed - including the one
        already committed to the repo with real leads in it. This
        makes the migration self-healing: harmless on a fresh database
        (columns are already there, so this just hits "duplicate
        column name" and is ignored) and effective on an existing one.
        """
        for column in ("salary", "work_mode"):
            try:
                self._conn.execute(f"ALTER TABLE leads ADD COLUMN {column} TEXT")
                self._conn.commit()
            except sqlite3.OperationalError as exc:
                if "duplicate column name" not in str(exc).lower():
                    raise

    # --- jobs_seen (dedup ledger) -------------------------------------

    def has_seen(self, job_hash: str) -> bool:
        """Return True if this job hash has already been recorded."""
        cursor = self._conn.execute(
            "SELECT 1 FROM jobs_seen WHERE job_hash = ? LIMIT 1", (job_hash,)
        )
        return cursor.fetchone() is not None

    def mark_seen(self, job: Job) -> bool:
        """Record a job hash in the dedup ledger.

        Returns True if this was a new record, False if it already
        existed (i.e. this call was a no-op duplicate).
        """
        cursor = self._conn.execute(
            """
            INSERT OR IGNORE INTO jobs_seen (job_hash, company, job_title, source, first_seen_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (job.dedup_hash(), job.company, job.job_title, job.source, datetime.now(timezone.utc).isoformat()),
        )
        self._conn.commit()
        return cursor.rowcount > 0

    # --- leads ----------------------------------------------------------

    def insert_lead(self, job: Job, score: int) -> bool:
        """Insert a qualified, scored job into the leads table.

        Returns True if inserted, False if a lead with this job_hash
        already existed (duplicate-safe by construction).
        """
        cursor = self._conn.execute(
            """
            INSERT OR IGNORE INTO leads (
                job_hash, score, company, job_title, salary, work_mode, location, country,
                source, job_url, posted_date, found_at, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'New')
            """,
            (
                job.dedup_hash(),
                score,
                job.company,
                job.job_title,
                job.salary,
                job.work_mode,
                job.location,
                job.country,
                job.source,
                job.job_url,
                job.posted_date.isoformat() if job.posted_date else None,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        self._conn.commit()
        return cursor.rowcount > 0

    def get_unexported_leads(self) -> list[sqlite3.Row]:
        """Return all leads that haven't been exported to Google Sheets yet."""
        cursor = self._conn.execute(
            "SELECT * FROM leads WHERE exported_at IS NULL ORDER BY score DESC"
        )
        return cursor.fetchall()

    def mark_exported(self, job_hashes: list[str]) -> None:
        """Stamp exported_at on the given leads after a successful Sheets write."""
        if not job_hashes:
            return
        now = datetime.now(timezone.utc).isoformat()
        self._conn.executemany(
            "UPDATE leads SET exported_at = ? WHERE job_hash = ?",
            [(now, job_hash) for job_hash in job_hashes],
        )
        self._conn.commit()

    def reset_exported_status(self, job_hashes: list[str] | None = None) -> int:
        """Clear exported_at so the given leads (or all leads, if
        job_hashes is None) are treated as unexported again and get
        re-sent to Google Sheets on the next run.

        Intended for recovering from a manually-cleared or corrupted
        sheet: the leads themselves are never lost (they stay in this
        database regardless of what happens to the sheet), only the
        "was this sent" flag needs resetting.

        Returns the number of rows updated.
        """
        if job_hashes is None:
            cursor = self._conn.execute(
                "UPDATE leads SET exported_at = NULL WHERE exported_at IS NOT NULL"
            )
        else:
            if not job_hashes:
                return 0
            placeholders = ",".join("?" * len(job_hashes))
            cursor = self._conn.execute(
                f"UPDATE leads SET exported_at = NULL WHERE job_hash IN ({placeholders})",
                job_hashes,
            )
        self._conn.commit()
        return cursor.rowcount

    # --- companies --------------------------------------------------------

    def upsert_company(self, company: Company) -> None:
        """Insert a newly discovered company, or leave an existing one
        untouched (first discovery wins; slugs are updated separately
        once confirmed in a later milestone)."""
        self._conn.execute(
            """
            INSERT INTO companies (name, discovered_via, discovered_at, active)
            VALUES (?, ?, ?, 1)
            ON CONFLICT(name) DO NOTHING
            """,
            (company.name, company.discovered_via, company.discovered_at.isoformat()),
        )
        self._conn.commit()

    def get_company(self, name: str) -> sqlite3.Row | None:
        cursor = self._conn.execute("SELECT * FROM companies WHERE name = ?", (name,))
        return cursor.fetchone()

    # --- lifecycle ----------------------------------------------------------

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "Database":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
