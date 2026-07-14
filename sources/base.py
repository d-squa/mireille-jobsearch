"""
JobSource interface.

Every connector - discovery sources like Jooble/Adzuna, or future ATS
sources like Greenhouse/Lever/Ashby - implements this one interface.
The orchestrator never knows or cares which kind of source it's
talking to; it just calls fetch_jobs() and gets back a list[Job] in
the common shape defined in models/job.py.

Kept as a single ABC rather than splitting into DiscoverySource/
AtsSource subclasses for now - that split adds no value until Milestone
5 actually introduces an ATS connector with a meaningfully different
constructor shape (slug-based vs keyword-based). Revisit then.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from models.job import Job


class JobSource(ABC):
    """Abstract base for all job source connectors."""

    #: Short, stable identifier written into Job.source and used in
    #: logs (e.g. "jooble", "adzuna", "greenhouse").
    name: str

    @abstractmethod
    def fetch_jobs(self, search_terms: tuple[str, ...], countries: tuple[str, ...]) -> list[Job]:
        """Fetch and normalize jobs matching the given search terms.

        Args:
            search_terms: Keywords to search for, e.g. ("paid media", "PPC").
            countries: ISO country codes to search within. Sources that
                don't support country scoping may ignore this.

        Returns:
            A list of normalized Job objects. Never raises for
            individual malformed entries in the raw response - those
            are skipped and logged. Raises SourceError for connection
            failures, non-2xx responses, or unparseable payloads.
        """
        raise NotImplementedError
