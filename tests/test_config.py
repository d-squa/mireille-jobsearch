"""Unit tests for config.py - fail-fast validation behaviour."""
import pytest

from config import ConfigError, _load_settings


def _write_env(tmp_path, overrides=None):
    base = {
        "JOOBLE_API_KEY": "test-key",
        "ADZUNA_APP_ID": "",
        "ADZUNA_APP_KEY": "",
        "SEARCH_TERMS": "paid media,media buyer",
        "SEARCH_COUNTRIES": "gb,us",
        "TITLE_SCORES_FILE": str(tmp_path / "title_scores.json"),
        "FUZZY_MATCH_THRESHOLD": "82",
        "ATS_WATCHLIST_FILE": "",
        "MIN_SCORE": "50",
        "DATABASE_PATH": "./data/test.db",
        "GOOGLE_SHEET_ID": "",
        "GOOGLE_SERVICE_ACCOUNT_FILE": "./credentials/sa.json",
        "LOG_LEVEL": "INFO",
        "LOG_FILE": "./logs/test.log",
    }
    if overrides:
        base.update(overrides)
    env_path = tmp_path / ".env"
    env_path.write_text("\n".join(f"{k}={v}" for k, v in base.items()))

    title_scores_path = tmp_path / "title_scores.json"
    if not title_scores_path.exists():
        title_scores_path.write_text('{"Paid Media Manager": 100}')

    return env_path


def test_valid_config_loads(tmp_path):
    env_path = _write_env(tmp_path)
    settings = _load_settings(str(env_path))
    assert settings.sources.jooble_enabled is True
    assert settings.sources.adzuna_enabled is False
    assert settings.min_score == 50
    assert settings.search_terms == ("paid media", "media buyer")


def test_no_discovery_source_configured_raises(tmp_path, monkeypatch):
    monkeypatch.delenv("JOOBLE_API_KEY", raising=False)
    monkeypatch.delenv("ADZUNA_APP_ID", raising=False)
    monkeypatch.delenv("ADZUNA_APP_KEY", raising=False)
    env_path = _write_env(tmp_path, {"JOOBLE_API_KEY": ""})
    with pytest.raises(ConfigError, match="No discovery source"):
        _load_settings(str(env_path))


def test_missing_search_terms_raises(tmp_path, monkeypatch):
    monkeypatch.delenv("SEARCH_TERMS", raising=False)
    env_path = _write_env(tmp_path, {"SEARCH_TERMS": ""})
    with pytest.raises(ConfigError, match="SEARCH_TERMS"):
        _load_settings(str(env_path))


def test_invalid_min_score_raises(tmp_path, monkeypatch):
    monkeypatch.delenv("MIN_SCORE", raising=False)
    env_path = _write_env(tmp_path, {"MIN_SCORE": "not-a-number"})
    with pytest.raises(ConfigError, match="MIN_SCORE"):
        _load_settings(str(env_path))


def test_malformed_sheet_id_raises(tmp_path, monkeypatch):
    monkeypatch.delenv("GOOGLE_SHEET_ID", raising=False)
    env_path = _write_env(
        tmp_path, {"GOOGLE_SHEET_ID": "https://docs.google.com/spreadsheets/d/abc123"}
    )
    with pytest.raises(ConfigError, match="GOOGLE_SHEET_ID"):
        _load_settings(str(env_path))


def test_exclude_terms_defaults_to_empty_when_not_set(tmp_path, monkeypatch):
    monkeypatch.delenv("EXCLUDE_TERMS", raising=False)
    env_path = _write_env(tmp_path)
    settings = _load_settings(str(env_path))
    assert settings.exclude_terms == ()


def test_exclude_terms_parsed_from_csv(tmp_path, monkeypatch):
    monkeypatch.delenv("EXCLUDE_TERMS", raising=False)
    env_path = _write_env(tmp_path, {"EXCLUDE_TERMS": "Intern, Volunteer,Unpaid"})
    settings = _load_settings(str(env_path))
    assert settings.exclude_terms == ("Intern", "Volunteer", "Unpaid")


def test_missing_title_scores_file_raises(tmp_path, monkeypatch):
    monkeypatch.delenv("TITLE_SCORES_FILE", raising=False)
    env_path = _write_env(
        tmp_path, {"TITLE_SCORES_FILE": str(tmp_path / "does_not_exist.json")}
    )
    with pytest.raises(ConfigError, match="TITLE_SCORES_FILE"):
        _load_settings(str(env_path))


def test_fuzzy_threshold_out_of_range_raises(tmp_path, monkeypatch):
    monkeypatch.delenv("FUZZY_MATCH_THRESHOLD", raising=False)
    env_path = _write_env(tmp_path, {"FUZZY_MATCH_THRESHOLD": "150"})
    with pytest.raises(ConfigError, match="FUZZY_MATCH_THRESHOLD"):
        _load_settings(str(env_path))


def test_fuzzy_threshold_not_integer_raises(tmp_path, monkeypatch):
    monkeypatch.delenv("FUZZY_MATCH_THRESHOLD", raising=False)
    env_path = _write_env(tmp_path, {"FUZZY_MATCH_THRESHOLD": "high"})
    with pytest.raises(ConfigError, match="FUZZY_MATCH_THRESHOLD"):
        _load_settings(str(env_path))


def test_missing_service_account_file_raises_when_sheet_id_set(tmp_path, monkeypatch):
    monkeypatch.delenv("GOOGLE_SHEET_ID", raising=False)
    monkeypatch.delenv("GOOGLE_SERVICE_ACCOUNT_FILE", raising=False)
    env_path = _write_env(
        tmp_path,
        {
            "GOOGLE_SHEET_ID": "abc123def456",
            "GOOGLE_SERVICE_ACCOUNT_FILE": str(tmp_path / "does_not_exist.json"),
        },
    )
    with pytest.raises(ConfigError, match="GOOGLE_SERVICE_ACCOUNT_FILE"):
        _load_settings(str(env_path))


def test_missing_ats_watchlist_file_raises_when_set(tmp_path, monkeypatch):
    monkeypatch.delenv("ATS_WATCHLIST_FILE", raising=False)
    env_path = _write_env(
        tmp_path, {"ATS_WATCHLIST_FILE": str(tmp_path / "does_not_exist.json")}
    )
    with pytest.raises(ConfigError, match="ATS_WATCHLIST_FILE"):
        _load_settings(str(env_path))


def test_blank_ats_watchlist_file_is_valid(tmp_path, monkeypatch):
    monkeypatch.delenv("ATS_WATCHLIST_FILE", raising=False)
    env_path = _write_env(tmp_path, {"ATS_WATCHLIST_FILE": ""})
    settings = _load_settings(str(env_path))
    assert settings.ats_watchlist_file is None


def test_invalid_log_level_raises(tmp_path, monkeypatch):
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    env_path = _write_env(tmp_path, {"LOG_LEVEL": "VERBOSE"})
    with pytest.raises(ConfigError, match="LOG_LEVEL"):
        _load_settings(str(env_path))
