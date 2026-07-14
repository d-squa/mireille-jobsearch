"""Unit tests for sources/ats_watchlist.py."""
import json

import pytest

from sources.ats_watchlist import AtsTarget, AtsWatchlistError, load_ats_watchlist


class TestLoadAtsWatchlist:
    def test_loads_valid_watchlist(self, tmp_path) -> None:
        path = tmp_path / "watchlist.json"
        path.write_text(
            json.dumps(
                {
                    "greenhouse": [{"slug": "acme", "company_name": "Acme Corp"}],
                    "lever": [],
                    "ashby": [{"slug": "beta", "company_name": "Beta Inc"}],
                }
            )
        )
        result = load_ats_watchlist(path)

        assert result["greenhouse"] == (AtsTarget(slug="acme", company_name="Acme Corp"),)
        assert result["lever"] == ()
        assert result["ashby"] == (AtsTarget(slug="beta", company_name="Beta Inc"),)

    def test_missing_platform_key_returns_empty_tuple(self, tmp_path) -> None:
        path = tmp_path / "watchlist.json"
        path.write_text(json.dumps({"greenhouse": [{"slug": "acme", "company_name": "Acme Corp"}]}))

        result = load_ats_watchlist(path)

        assert result["lever"] == ()
        assert result["ashby"] == ()

    def test_ignores_underscore_metadata_key(self, tmp_path) -> None:
        path = tmp_path / "watchlist.json"
        path.write_text(json.dumps({"_comment": "instructions", "greenhouse": [], "lever": [], "ashby": []}))

        result = load_ats_watchlist(path)

        assert result["greenhouse"] == ()

    def test_missing_file_raises(self, tmp_path) -> None:
        with pytest.raises(AtsWatchlistError, match="Could not read"):
            load_ats_watchlist(tmp_path / "does_not_exist.json")

    def test_invalid_json_raises(self, tmp_path) -> None:
        path = tmp_path / "watchlist.json"
        path.write_text("{not valid json")
        with pytest.raises(AtsWatchlistError, match="not valid JSON"):
            load_ats_watchlist(path)

    def test_entry_missing_slug_raises(self, tmp_path) -> None:
        path = tmp_path / "watchlist.json"
        path.write_text(json.dumps({"greenhouse": [{"company_name": "Acme Corp"}]}))
        with pytest.raises(AtsWatchlistError, match="slug"):
            load_ats_watchlist(path)

    def test_entry_missing_company_name_raises(self, tmp_path) -> None:
        path = tmp_path / "watchlist.json"
        path.write_text(json.dumps({"greenhouse": [{"slug": "acme"}]}))
        with pytest.raises(AtsWatchlistError, match="company_name"):
            load_ats_watchlist(path)

    def test_platform_value_not_a_list_raises(self, tmp_path) -> None:
        path = tmp_path / "watchlist.json"
        path.write_text(json.dumps({"greenhouse": "not-a-list"}))
        with pytest.raises(AtsWatchlistError, match="must be a list"):
            load_ats_watchlist(path)

    def test_real_project_watchlist_file_loads_successfully(self) -> None:
        # Guards against the shipped config/ats_watchlist.json ever
        # becoming invalid without a test catching it.
        from pathlib import Path

        real_path = Path(__file__).parent.parent / "config" / "ats_watchlist.json"
        result = load_ats_watchlist(real_path)
        assert set(result.keys()) == {"greenhouse", "lever", "ashby"}
