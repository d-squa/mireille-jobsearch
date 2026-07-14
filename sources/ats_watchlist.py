"""
ATS watchlist loading.

Greenhouse, Lever, and Ashby are all polled per-company via a known
board slug - there's no keyword search across companies. This module
loads that slug list from a small JSON file (config/ats_watchlist.json)
so new companies can be added without touching code.

Each entry pairs a slug with a company_name, because ATS responses
don't include the company's display name - you already have to know
it, since you're querying by slug in the URL.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from utils.logger import get_logger

logger = get_logger(__name__)

_SUPPORTED_PLATFORMS = ("greenhouse", "lever", "ashby")


class AtsWatchlistError(Exception):
    """Raised when the ATS watchlist file is missing or malformed."""


@dataclass(frozen=True)
class AtsTarget:
    """A single company to poll on a given ATS platform."""

    slug: str
    company_name: str


def load_ats_watchlist(path: Path) -> dict[str, tuple[AtsTarget, ...]]:
    """Load the ATS watchlist file into per-platform tuples of AtsTarget.

    Returns a dict with keys "greenhouse", "lever", "ashby", each
    mapping to a (possibly empty) tuple of AtsTarget. A platform with
    no entries configured simply gets an empty tuple - callers use
    that to decide whether to build a connector for it at all.

    Raises:
        AtsWatchlistError: if the file is missing, isn't valid JSON,
            or an entry is missing "slug"/"company_name".
    """
    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise AtsWatchlistError(f"Could not read ATS watchlist file {path}: {exc}") from exc

    try:
        raw_data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise AtsWatchlistError(f"ATS watchlist file {path} is not valid JSON: {exc}") from exc

    result: dict[str, tuple[AtsTarget, ...]] = {}
    for platform in _SUPPORTED_PLATFORMS:
        entries = raw_data.get(platform, [])
        if not isinstance(entries, list):
            raise AtsWatchlistError(
                f"ATS watchlist file {path}: {platform!r} must be a list, got {type(entries).__name__}."
            )

        targets: list[AtsTarget] = []
        for entry in entries:
            slug = str(entry.get("slug", "")).strip()
            company_name = str(entry.get("company_name", "")).strip()
            if not slug or not company_name:
                raise AtsWatchlistError(
                    f"ATS watchlist file {path}: each {platform!r} entry needs a non-empty "
                    f"'slug' and 'company_name', got {entry!r}."
                )
            targets.append(AtsTarget(slug=slug, company_name=company_name))

        result[platform] = tuple(targets)
        logger.info("Loaded %d %s watchlist target(s) from %s", len(targets), platform, path)

    return result
