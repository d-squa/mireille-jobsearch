"""
Work mode classification.

Labels a job Remote / Hybrid / Onsite. Two sources of truth:

1. Structured API fields, when a source actually provides them (Lever's
   workplaceType, Ashby's workplaceType/isRemote) - handled directly in
   those connectors, not here.
2. Simple keyword matching over title/location/description, for every
   source that doesn't expose it structurally (Jooble, Reed, Adzuna,
   Greenhouse) - that's what this module does.

Deliberately simple substring matching per the brief ("if it contains
remote, label it remote"), not NLP or fuzzy inference. "Hybrid" is
checked first since it's the most specific signal and a posting
mentioning both "hybrid" and "remote" (e.g. "Hybrid/Remote options")
is more accurately described as hybrid.
"""
from __future__ import annotations

_HYBRID_KEYWORDS = ("hybrid",)
_REMOTE_KEYWORDS = ("remote", "work from home", "wfh")
_ONSITE_KEYWORDS = ("onsite", "on-site", "on site", "in office", "in-office")


def classify_work_mode(*texts: str | None) -> str | None:
    """Infer work mode from any number of free-text fields (title,
    location, description - in whatever order/combination the caller
    has available).

    Returns "Hybrid", "Remote", "Onsite", or None if none of the
    keyword sets appear anywhere in the combined text - deliberately
    not defaulting to "Onsite" just because nothing else matched,
    since silence isn't evidence.
    """
    combined = " ".join(text for text in texts if text).lower()
    if not combined:
        return None

    if any(keyword in combined for keyword in _HYBRID_KEYWORDS):
        return "Hybrid"
    if any(keyword in combined for keyword in _REMOTE_KEYWORDS):
        return "Remote"
    if any(keyword in combined for keyword in _ONSITE_KEYWORDS):
        return "Onsite"
    return None
