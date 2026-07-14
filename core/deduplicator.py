"""
Deduplicator.

Wraps storage/database.py's jobs_seen ledger with an in-memory set for
the current run. This matters because a single run can legitimately
see the same job twice - e.g. the same posting turning up for both
"paid media" and "PPC" search terms, or once per country query if a
remote role is tagged in multiple locations. Without the in-run cache,
each of those would trigger a redundant DB write; with it, only the
first sighting per run touches the database.

The persistent, cross-run guarantee ("never insert the same job
twice, ever") still lives in storage/database.py's UNIQUE constraints -
this class is a performance/clarity layer on top, not a replacement.
"""
from __future__ import annotations

from models.job import Job
from storage.database import Database


class Deduplicator:
    """Tracks which jobs have already been seen, this run and across
    all previous runs."""

    def __init__(self, database: Database) -> None:
        self._database = database
        self._seen_this_run: set[str] = set()

    def is_new(self, job: Job) -> bool:
        """Return True if this is the first time this job has ever been
        seen (this run or any prior run), and record it as seen.

        Returns False for any repeat - whether the repeat is within
        this run or from a previous day's run.
        """
        job_hash = job.dedup_hash()

        if job_hash in self._seen_this_run:
            return False

        self._seen_this_run.add(job_hash)

        if self._database.has_seen(job_hash):
            return False

        self._database.mark_seen(job)
        return True
