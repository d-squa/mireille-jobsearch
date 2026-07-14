"""
Contact model (stub).

Not used until the enrichment milestone (contact discovery / decision-
maker identification). Defined now so enrichment/contacts.py has a
concrete return type to build against later, without pulling any
enrichment logic into this milestone.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Contact:
    """A prospective decision-maker at a lead company. Not yet populated
    by any implemented module."""

    name: str
    title: str
    company: str
    email: str | None = None
    linkedin_url: str | None = None
