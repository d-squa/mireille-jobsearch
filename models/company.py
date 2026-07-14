"""
Company model.

Represents a company discovered via the daily job search results.
Populated automatically as a byproduct of Tier 1 discovery sources
(Jooble, Adzuna); ATS slug fields are filled in later, manually or
semi-automatically, once a company is confirmed to use Greenhouse,
Lever, or Ashby (Milestone 5+).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Company:
    """A company identified as a potential lead.

    Attributes:
        name: Company name as it appeared in the source posting.
        discovered_via: Source identifier that first surfaced this
            company, e.g. "jooble", "adzuna".
        discovered_at: Timestamp the company was first seen.
        greenhouse_slug: Greenhouse board slug, if known. None until
            confirmed (Milestone 5+).
        lever_slug: Lever board slug, if known.
        ashby_slug: Ashby board slug, if known.
        active: Whether this company should still be polled/considered.
    """

    name: str
    discovered_via: str
    discovered_at: datetime
    greenhouse_slug: str | None = None
    lever_slug: str | None = None
    ashby_slug: str | None = None
    active: bool = True
