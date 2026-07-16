"""
Country exclusions loading.

Loads a per-source list of country codes to skip from a small JSON
file (config/country_exclusions.json), so a country confirmed to
always fail for a given API can be added without any code change -
edit the file, commit, done. Countries are compared case-insensitively
against whatever's configured in SEARCH_COUNTRIES.
"""
from __future__ import annotations

import json
from pathlib import Path

from utils.logger import get_logger

logger = get_logger(__name__)


class CountryExclusionsError(Exception):
    """Raised when the country exclusions file is missing or malformed."""


def load_country_exclusions(path: Path) -> dict[str, tuple[str, ...]]:
    """Load the country exclusions file into a dict of source name ->
    tuple of lowercase country codes to skip for that source.

    A source with no key present, or an empty list, simply gets an
    empty tuple - callers treat that as "exclude nothing."

    Raises:
        CountryExclusionsError: if the file is missing, isn't valid
            JSON, or a source's value isn't a list of strings.
    """
    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise CountryExclusionsError(f"Could not read {path}: {exc}") from exc

    try:
        raw_data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise CountryExclusionsError(f"{path} is not valid JSON: {exc}") from exc

    result: dict[str, tuple[str, ...]] = {}
    for key, value in raw_data.items():
        if key.startswith("_"):
            continue  # "_comment" and similar metadata keys
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise CountryExclusionsError(
                f"{path}: {key!r} must be a list of country code strings, got {value!r}."
            )
        codes = tuple(code.strip().lower() for code in value if code.strip())
        result[key] = codes
        if codes:
            logger.info("Loaded %d country exclusion(s) for %s: %s", len(codes), key, ", ".join(codes))

    return result
