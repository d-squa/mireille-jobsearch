"""
Job title filter.

Decides whether a raw job title (as posted, with all its real-world
noise - seniority prefixes, location suffixes, parenthetical notes)
counts as one of the configured target roles. Matching, not scoring:
core/scoring.py decides how valuable a matched title is.

Uses fuzzy matching (rapidfuzz) rather than exact string comparison,
since real postings rarely match the canonical title verbatim - e.g.
"Senior Paid Media Manager (Hybrid)" or "Paid Media Manager - EMEA"
should both match the canonical "Paid Media Manager".
"""
from __future__ import annotations

import re

from rapidfuzz import fuzz, process

from utils.logger import get_logger

logger = get_logger(__name__)

# Seniority / scope qualifiers stripped before matching. Deliberately
# does not include words that change the *role* itself (e.g. "Head of
# Paid Social" is arguably a different, more senior role than "Paid
# Social Manager" - but for lead-scoring purposes we still want it to
# match, since it's still a paid-media decision-maker at that company).
_SENIORITY_PATTERN = re.compile(
    r"\b(senior|sr\.?|junior|jr\.?|lead|principal|head of|director of|"
    r"vp of|vp|chief|global|regional|associate)\b",
    re.IGNORECASE,
)
_PARENTHETICAL_PATTERN = re.compile(r"\([^)]*\)")
_TRAILING_QUALIFIER_PATTERN = re.compile(r"\s*[-–|]\s*.+$")
_WHITESPACE_PATTERN = re.compile(r"\s+")


def normalize_title(raw_title: str) -> str:
    """Strip common real-world noise from a raw job title before matching.

    Removes parenthetical notes ("(Hybrid)"), trailing dash/pipe-separated
    qualifiers ("- EMEA", "| Remote"), and seniority/scope prefixes
    ("Senior", "Head of", "VP"). Collapses whitespace.
    """
    text = raw_title.strip()
    text = _PARENTHETICAL_PATTERN.sub("", text)
    text = _TRAILING_QUALIFIER_PATTERN.sub("", text)
    text = _SENIORITY_PATTERN.sub("", text)
    text = _WHITESPACE_PATTERN.sub(" ", text).strip()
    return text


class ExcludeFilter:
    """Excludes jobs whose title contains any configured exclude term.

    Simple case-insensitive substring matching, deliberately not fuzzy
    like JobFilter.match() - exclude terms are blocklist words
    ("Intern", "Volunteer", "Unpaid"), not role variants that need
    tolerance for phrasing differences. Substring matching is more
    predictable here: no risk of an exclude term fuzzy-matching
    something it shouldn't.
    """

    def __init__(self, exclude_terms: tuple[str, ...]) -> None:
        self._exclude_terms = tuple(term.lower() for term in exclude_terms if term.strip())

    def is_excluded(self, job_title: str) -> bool:
        """Return True if the raw job title contains any exclude term."""
        if not self._exclude_terms:
            return False
        normalized_title = job_title.lower()
        return any(term in normalized_title for term in self._exclude_terms)


class JobFilter:
    """Fuzzy-matches raw job titles against a configured list of
    canonical target titles."""

    def __init__(self, canonical_titles: tuple[str, ...], threshold: int = 82) -> None:
        if not canonical_titles:
            raise ValueError("JobFilter requires at least one canonical title")
        if not 0 <= threshold <= 100:
            raise ValueError("threshold must be between 0 and 100")
        self._canonical_titles = canonical_titles
        self._threshold = threshold

    def match(self, raw_title: str) -> str | None:
        """Return the best-matching canonical title if it clears the
        configured confidence threshold, otherwise None.
        """
        normalized = normalize_title(raw_title)
        if not normalized:
            return None

        # token_sort_ratio (not WRatio) deliberately: WRatio's partial-
        # match bias scores short unrelated titles like "Marketing Intern"
        # dangerously close to "Performance Marketing Manager" because it
        # rewards one string being a near-substring of the other.
        # token_sort_ratio compares full sorted-token strings, which
        # keeps unrelated short titles well below threshold.
        result = process.extractOne(
            normalized,
            self._canonical_titles,
            scorer=fuzz.token_sort_ratio,
            score_cutoff=self._threshold,
        )
        if result is None:
            return None

        matched_title, match_score, _ = result
        logger.debug(
            "Matched raw title %r -> %r (normalized=%r, score=%.1f)",
            raw_title,
            matched_title,
            normalized,
            match_score,
        )
        return matched_title
