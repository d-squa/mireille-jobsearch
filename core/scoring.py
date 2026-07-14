"""
Scoring engine.

Loads a canonical title -> score mapping from a JSON file (see
config/title_scores.json) and scores jobs already matched to a
canonical title by core/job_filter.py. Scoring is deliberately kept
separate from title matching: job_filter.py decides *whether* a raw
title counts as one of the configured roles; scoring.py decides *how
valuable* that role is as a lead.
"""
from __future__ import annotations

import json
from pathlib import Path

from utils.logger import get_logger

logger = get_logger(__name__)


class ScoringConfigError(Exception):
    """Raised when the title_scores.json file is missing, malformed,
    or contains invalid score values."""


class ScoringEngine:
    """Scores a canonical job title using a configurable title->score map."""

    def __init__(self, title_scores: dict[str, int]) -> None:
        self._title_scores = title_scores

    @classmethod
    def from_file(cls, path: Path) -> "ScoringEngine":
        """Load a ScoringEngine from a title_scores.json file.

        Raises:
            ScoringConfigError: if the file is missing, isn't valid
                JSON, or contains a non-integer / out-of-range score.
        """
        try:
            raw_text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ScoringConfigError(f"Could not read title scores file {path}: {exc}") from exc

        try:
            raw_data = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise ScoringConfigError(f"Title scores file {path} is not valid JSON: {exc}") from exc

        title_scores: dict[str, int] = {}
        for title, score in raw_data.items():
            if title.startswith("_"):
                continue  # allow "_comment" and similar metadata keys
            if not isinstance(score, int) or isinstance(score, bool):
                raise ScoringConfigError(
                    f"Score for {title!r} must be an integer, got {score!r}."
                )
            if not 0 <= score <= 100:
                raise ScoringConfigError(
                    f"Score for {title!r} must be between 0 and 100, got {score}."
                )
            title_scores[title] = score

        if not title_scores:
            raise ScoringConfigError(f"Title scores file {path} contains no scored titles.")

        logger.info("Loaded %d scored titles from %s", len(title_scores), path)
        return cls(title_scores)

    @property
    def canonical_titles(self) -> tuple[str, ...]:
        """All configured canonical titles, used by job_filter.py as
        the fuzzy-matching candidate list."""
        return tuple(self._title_scores.keys())

    def score(self, canonical_title: str) -> int:
        """Return the configured score for an already-matched canonical
        title. Returns 0 for an unrecognized title rather than raising,
        since that indicates a caller bug (matching against a title not
        in this engine's list) rather than a data problem."""
        score = self._title_scores.get(canonical_title)
        if score is None:
            logger.warning(
                "score() called with unrecognized canonical title: %r", canonical_title
            )
            return 0
        return score

    def meets_threshold(self, score: int, min_score: int) -> bool:
        """Whether a score clears the configured minimum to become a lead."""
        return score >= min_score
