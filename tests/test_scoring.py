"""Unit tests for core/scoring.py."""
import json

import pytest

from core.scoring import ScoringConfigError, ScoringEngine


class TestScoringEngineFromDict:
    def test_score_returns_configured_value(self) -> None:
        engine = ScoringEngine({"Paid Media Manager": 100, "Campaign Manager": 70})
        assert engine.score("Paid Media Manager") == 100
        assert engine.score("Campaign Manager") == 70

    def test_score_unrecognized_title_returns_zero(self) -> None:
        engine = ScoringEngine({"Paid Media Manager": 100})
        assert engine.score("Nonexistent Title") == 0

    def test_canonical_titles_returns_all_keys(self) -> None:
        engine = ScoringEngine({"Paid Media Manager": 100, "Campaign Manager": 70})
        assert set(engine.canonical_titles) == {"Paid Media Manager", "Campaign Manager"}

    def test_meets_threshold_true_when_score_at_or_above_min(self) -> None:
        engine = ScoringEngine({"X": 50})
        assert engine.meets_threshold(score=50, min_score=50) is True
        assert engine.meets_threshold(score=60, min_score=50) is True

    def test_meets_threshold_false_when_score_below_min(self) -> None:
        engine = ScoringEngine({"X": 50})
        assert engine.meets_threshold(score=49, min_score=50) is False


class TestScoringEngineFromFile:
    def test_loads_valid_file(self, tmp_path) -> None:
        path = tmp_path / "title_scores.json"
        path.write_text(json.dumps({"Paid Media Manager": 100, "Campaign Manager": 70}))
        engine = ScoringEngine.from_file(path)
        assert engine.score("Paid Media Manager") == 100

    def test_ignores_underscore_prefixed_metadata_keys(self, tmp_path) -> None:
        path = tmp_path / "title_scores.json"
        path.write_text(json.dumps({"_comment": "some note", "Paid Media Manager": 100}))
        engine = ScoringEngine.from_file(path)
        assert "_comment" not in engine.canonical_titles
        assert engine.score("Paid Media Manager") == 100

    def test_missing_file_raises_scoring_config_error(self, tmp_path) -> None:
        path = tmp_path / "does_not_exist.json"
        with pytest.raises(ScoringConfigError, match="Could not read"):
            ScoringEngine.from_file(path)

    def test_invalid_json_raises_scoring_config_error(self, tmp_path) -> None:
        path = tmp_path / "title_scores.json"
        path.write_text("{not valid json")
        with pytest.raises(ScoringConfigError, match="not valid JSON"):
            ScoringEngine.from_file(path)

    def test_non_integer_score_raises_scoring_config_error(self, tmp_path) -> None:
        path = tmp_path / "title_scores.json"
        path.write_text(json.dumps({"Paid Media Manager": "high"}))
        with pytest.raises(ScoringConfigError, match="must be an integer"):
            ScoringEngine.from_file(path)

    def test_out_of_range_score_raises_scoring_config_error(self, tmp_path) -> None:
        path = tmp_path / "title_scores.json"
        path.write_text(json.dumps({"Paid Media Manager": 150}))
        with pytest.raises(ScoringConfigError, match="between 0 and 100"):
            ScoringEngine.from_file(path)

    def test_empty_title_map_raises_scoring_config_error(self, tmp_path) -> None:
        path = tmp_path / "title_scores.json"
        path.write_text(json.dumps({"_comment": "only metadata, no titles"}))
        with pytest.raises(ScoringConfigError, match="no scored titles"):
            ScoringEngine.from_file(path)

    def test_real_project_title_scores_file_loads_successfully(self) -> None:
        # Guards against the actual shipped config/title_scores.json
        # ever becoming invalid without a test catching it.
        from pathlib import Path

        real_path = Path(__file__).parent.parent / "config" / "title_scores.json"
        engine = ScoringEngine.from_file(real_path)
        assert engine.score("Paid Media Manager") == 100
        assert len(engine.canonical_titles) >= 10
