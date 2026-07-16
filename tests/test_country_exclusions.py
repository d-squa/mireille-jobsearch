"""Unit tests for sources/country_exclusions.py."""
import json

import pytest

from sources.country_exclusions import CountryExclusionsError, load_country_exclusions


class TestLoadCountryExclusions:
    def test_loads_valid_file(self, tmp_path) -> None:
        path = tmp_path / "exclusions.json"
        path.write_text(json.dumps({"adzuna": ["ae", "sa"], "jooble": []}))

        result = load_country_exclusions(path)

        assert result["adzuna"] == ("ae", "sa")
        assert result["jooble"] == ()

    def test_ignores_underscore_metadata_key(self, tmp_path) -> None:
        path = tmp_path / "exclusions.json"
        path.write_text(json.dumps({"_comment": "notes", "adzuna": ["ae"]}))

        result = load_country_exclusions(path)

        assert "_comment" not in result
        assert result["adzuna"] == ("ae",)

    def test_normalizes_case_and_whitespace(self, tmp_path) -> None:
        path = tmp_path / "exclusions.json"
        path.write_text(json.dumps({"adzuna": [" AE ", "Sa"]}))

        result = load_country_exclusions(path)

        assert result["adzuna"] == ("ae", "sa")

    def test_blank_entries_are_dropped(self, tmp_path) -> None:
        path = tmp_path / "exclusions.json"
        path.write_text(json.dumps({"adzuna": ["ae", "", "  "]}))

        result = load_country_exclusions(path)

        assert result["adzuna"] == ("ae",)

    def test_missing_file_raises(self, tmp_path) -> None:
        with pytest.raises(CountryExclusionsError, match="Could not read"):
            load_country_exclusions(tmp_path / "does_not_exist.json")

    def test_invalid_json_raises(self, tmp_path) -> None:
        path = tmp_path / "exclusions.json"
        path.write_text("{not valid json")
        with pytest.raises(CountryExclusionsError, match="not valid JSON"):
            load_country_exclusions(path)

    def test_non_list_value_raises(self, tmp_path) -> None:
        path = tmp_path / "exclusions.json"
        path.write_text(json.dumps({"adzuna": "ae"}))
        with pytest.raises(CountryExclusionsError, match="must be a list"):
            load_country_exclusions(path)

    def test_non_string_list_item_raises(self, tmp_path) -> None:
        path = tmp_path / "exclusions.json"
        path.write_text(json.dumps({"adzuna": ["ae", 123]}))
        with pytest.raises(CountryExclusionsError, match="must be a list"):
            load_country_exclusions(path)

    def test_missing_source_key_not_present_in_result(self, tmp_path) -> None:
        path = tmp_path / "exclusions.json"
        path.write_text(json.dumps({"adzuna": ["ae"]}))

        result = load_country_exclusions(path)

        assert "jooble" not in result  # caller uses .get(name, ()) to handle this

    def test_real_project_file_loads_successfully(self) -> None:
        from pathlib import Path

        real_path = Path(__file__).parent.parent / "config" / "country_exclusions.json"
        result = load_country_exclusions(real_path)
        assert "adzuna" in result
        assert "ae" in result["adzuna"]
