"""Config loading/validation tests (CLAUDE.md §3)."""
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from vocallens.config import load_analysis_config, load_scoring_config

REPO_ROOT = Path(__file__).resolve().parents[1]
ANALYSIS = REPO_ROOT / "configs" / "analysis.yaml"
SCORING = REPO_ROOT / "configs" / "scoring.yaml"


def _base(path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _write(tmp_path, data, name):
    p = tmp_path / name
    p.write_text(yaml.safe_dump(data), encoding="utf-8")
    return p


def test_default_configs_load():
    a = load_analysis_config()
    s = load_scoring_config()
    assert a.audio.analysis_sample_rate_hz == 16000
    assert set(s.dimensions) == {"pace", "pause_management", "vocal_variation", "energy_control"}
    assert a.config_hash and s.config_hash


def test_unknown_key_rejected(tmp_path):
    base = _base(ANALYSIS)
    base["unexpected_setting"] = 1
    with pytest.raises(ValidationError):
        load_analysis_config(_write(tmp_path, base, "analysis.yaml"))


def test_zero_threshold_rejected(tmp_path):
    base = _base(ANALYSIS)
    base["detection"]["thresholds"]["pace_word_rate"]["value"] = 0.0
    with pytest.raises(ValidationError):
        load_analysis_config(_write(tmp_path, base, "analysis.yaml"))


def test_quality_weights_must_sum_to_one(tmp_path):
    base = _base(ANALYSIS)
    base["quality"]["alignment_weight"] = 0.9
    with pytest.raises(ValidationError):
        load_analysis_config(_write(tmp_path, base, "analysis.yaml"))


def test_scoring_anchors_must_increase(tmp_path):
    base = _base(SCORING)
    base["dimensions"]["pace"]["anchors"] = [
        {"exceedance": 1.0, "score": 70.0},
        {"exceedance": 0.0, "score": 100.0},
    ]
    with pytest.raises(ValidationError):
        load_scoring_config(_write(tmp_path, base, "scoring.yaml"))


def test_overall_min_valid_dimensions_satisfiable(tmp_path):
    base = _base(SCORING)
    base["aggregation"]["overall_min_valid_dimensions"] = 99
    with pytest.raises(ValidationError):
        load_scoring_config(_write(tmp_path, base, "scoring.yaml"))
