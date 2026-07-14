"""
Application configuration.

Loads settings from a .env file (via python-dotenv) into a single,
typed, immutable Settings object. Fails fast on startup if required
values are missing or malformed, rather than letting the pipeline
fail halfway through a run.

Usage:
    from config import get_settings
    settings = get_settings()
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv


class ConfigError(Exception):
    """Raised when required configuration is missing or invalid."""


@dataclass(frozen=True)
class DiscoverySourceConfig:
    """Credentials for a single discovery source. Empty fields mean
    the source is not configured and will be skipped at runtime."""

    jooble_api_key: str = ""
    adzuna_app_id: str = ""
    adzuna_app_key: str = ""
    reed_api_key: str = ""

    @property
    def jooble_enabled(self) -> bool:
        return bool(self.jooble_api_key)

    @property
    def adzuna_enabled(self) -> bool:
        return bool(self.adzuna_app_id and self.adzuna_app_key)

    @property
    def reed_enabled(self) -> bool:
        return bool(self.reed_api_key)


@dataclass(frozen=True)
class Settings:
    """Immutable application settings, populated once at startup."""

    # Discovery sources
    sources: DiscoverySourceConfig

    # Search
    search_terms: tuple[str, ...]
    search_countries: tuple[str, ...]
    exclude_terms: tuple[str, ...]

    # Filtering
    title_scores_file: Path
    fuzzy_match_threshold: int

    # ATS direct sources (optional)
    ats_watchlist_file: Path | None

    # Scoring
    min_score: int

    # Storage
    database_path: Path

    # Google Sheets
    google_sheet_id: str
    google_service_account_file: Path

    # Logging
    log_level: str
    log_file: Path


def _split_csv(value: str) -> tuple[str, ...]:
    """Split a comma-separated env value into a clean tuple of strings."""
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _require(env: dict[str, str], key: str) -> str:
    """Fetch a required env var or raise a clear ConfigError."""
    value = env.get(key, "").strip()
    if not value:
        raise ConfigError(
            f"Missing required environment variable: {key}. "
            f"Check your .env file against .env.example."
        )
    return value


def _load_settings(env_file: str | None = None) -> Settings:
    """Build a Settings object from environment variables.

    Args:
        env_file: Optional explicit path to a .env file. Defaults to
            the standard `.env` lookup performed by python-dotenv.

    Raises:
        ConfigError: if required configuration is missing or invalid.
    """
    load_dotenv(dotenv_path=env_file, override=False)
    env = dict(os.environ)

    sources = DiscoverySourceConfig(
        jooble_api_key=env.get("JOOBLE_API_KEY", "").strip(),
        adzuna_app_id=env.get("ADZUNA_APP_ID", "").strip(),
        adzuna_app_key=env.get("ADZUNA_APP_KEY", "").strip(),
        reed_api_key=env.get("REED_API_KEY", "").strip(),
    )

    if not sources.jooble_enabled and not sources.adzuna_enabled and not sources.reed_enabled:
        raise ConfigError(
            "No discovery source is configured. Set at least one of "
            "JOOBLE_API_KEY, (ADZUNA_APP_ID and ADZUNA_APP_KEY), or REED_API_KEY in .env."
        )

    search_terms = _split_csv(env.get("SEARCH_TERMS", ""))
    if not search_terms:
        raise ConfigError("SEARCH_TERMS must contain at least one term.")

    search_countries = _split_csv(env.get("SEARCH_COUNTRIES", ""))
    exclude_terms = _split_csv(env.get("EXCLUDE_TERMS", ""))

    title_scores_file = Path(_require(env, "TITLE_SCORES_FILE"))
    if not title_scores_file.exists():
        raise ConfigError(
            f"TITLE_SCORES_FILE does not exist: {title_scores_file}. "
            f"Create it or check the path in .env."
        )

    try:
        fuzzy_match_threshold = int(env.get("FUZZY_MATCH_THRESHOLD", "").strip())
    except ValueError as exc:
        raise ConfigError("FUZZY_MATCH_THRESHOLD must be an integer.") from exc
    if not 0 <= fuzzy_match_threshold <= 100:
        raise ConfigError("FUZZY_MATCH_THRESHOLD must be between 0 and 100.")

    ats_watchlist_raw = env.get("ATS_WATCHLIST_FILE", "").strip()
    ats_watchlist_file: Path | None = None
    if ats_watchlist_raw:
        ats_watchlist_file = Path(ats_watchlist_raw)
        if not ats_watchlist_file.exists():
            raise ConfigError(
                f"ATS_WATCHLIST_FILE is set but does not exist: {ats_watchlist_file}. "
                f"Leave it blank to skip ATS-direct sources, or fix the path."
            )

    try:
        min_score = int(env.get("MIN_SCORE", "").strip())
    except ValueError as exc:
        raise ConfigError("MIN_SCORE must be an integer.") from exc

    database_path = Path(_require(env, "DATABASE_PATH"))

    # Google Sheet ID is required for export, but we don't fail startup
    # on it being blank yet, since export is a later milestone. We DO
    # fail if it's set but obviously malformed (contains whitespace/URL).
    google_sheet_id = env.get("GOOGLE_SHEET_ID", "").strip()
    if google_sheet_id and (" " in google_sheet_id or "/" in google_sheet_id):
        raise ConfigError(
            "GOOGLE_SHEET_ID looks like a URL or contains spaces. "
            "Use only the sheet ID segment from the Google Sheets URL."
        )

    google_service_account_file = Path(
        env.get("GOOGLE_SERVICE_ACCOUNT_FILE", "./credentials/service_account.json").strip()
    )
    if google_sheet_id and not google_service_account_file.exists():
        raise ConfigError(
            f"GOOGLE_SHEET_ID is set but GOOGLE_SERVICE_ACCOUNT_FILE does not exist: "
            f"{google_service_account_file}. Export needs valid service account credentials."
        )

    log_level = env.get("LOG_LEVEL", "INFO").strip().upper()
    valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR"}
    if log_level not in valid_levels:
        raise ConfigError(f"LOG_LEVEL must be one of {sorted(valid_levels)}, got {log_level!r}.")

    log_file = Path(env.get("LOG_FILE", "./logs/lead_discovery.log").strip())

    return Settings(
        sources=sources,
        search_terms=search_terms,
        search_countries=search_countries,
        exclude_terms=exclude_terms,
        title_scores_file=title_scores_file,
        fuzzy_match_threshold=fuzzy_match_threshold,
        ats_watchlist_file=ats_watchlist_file,
        min_score=min_score,
        database_path=database_path,
        google_sheet_id=google_sheet_id,
        google_service_account_file=google_service_account_file,
        log_level=log_level,
        log_file=log_file,
    )


@lru_cache(maxsize=1)
def get_settings(env_file: str | None = None) -> Settings:
    """Return the cached application Settings, loading them on first call.

    Cached with lru_cache so the .env file is parsed once per process.
    Tests that need fresh settings should call get_settings.cache_clear()
    first.
    """
    return _load_settings(env_file)
