"""Scoring transform + coverage tests (ARCHITECTURE §8.9)."""
import pytest

from vocallens.detection import RuleMeasurement
from vocallens.schemas import DetectionFamily
from vocallens.scoring import compute_scores


def _m(dimension, rule_id, R, valid=True):
    fam = {
        "pace": DetectionFamily.PACE,
        "pause_management": DetectionFamily.PAUSE,
        "vocal_variation": DetectionFamily.PITCH_VARIATION,
        "energy_control": DetectionFamily.ENERGY_DYNAMICS,
    }[dimension]
    return RuleMeasurement(rule_id, dimension, fam, "p0", "f", "u", 1.0, 1.0, 0.0, 0.5, R, valid)


def _score_of(scores, name):
    return next(d for d in scores.dimensions if d.name == name)


def test_piecewise_anchors(scoring_config):
    cases = {0.0: 100.0, 1.0: 70.0, 3.0: 0.0, 2.0: 35.0}
    for R, expected in cases.items():
        s = compute_scores([_m("pace", "pace_word_rate", R)], scoring_config)
        assert pytest.approx(_score_of(s, "pace").score, abs=1e-6) == expected


def test_clamp_above_domain(scoring_config):
    s = compute_scores([_m("pace", "pace_word_rate", 10.0)], scoring_config)
    assert _score_of(s, "pace").score == 0.0


def test_missing_dimension_unavailable_not_zero(scoring_config):
    s = compute_scores([_m("pace", "pace_word_rate", 0.0)], scoring_config)
    vv = _score_of(s, "vocal_variation")
    assert vv.valid is False
    assert vv.score is None


def test_invalid_measurements_excluded(scoring_config):
    s = compute_scores([_m("pace", "pace_word_rate", 1.0, valid=False)], scoring_config)
    assert _score_of(s, "pace").valid is False


def test_overall_requires_three_valid_dims(scoring_config):
    two = [_m("pace", "pace_word_rate", 0.0), _m("pause_management", "pause_duration", 0.0)]
    s = compute_scores(two, scoring_config)
    assert s.valid_dimension_count == 2
    assert s.overall_available is False
    assert s.overall_score is None


def test_overall_with_renormalization(scoring_config):
    three = [
        _m("pace", "pace_word_rate", 0.0),           # 100
        _m("pause_management", "pause_duration", 1.0),  # 70
        _m("vocal_variation", "pitch_variation_iqr", 3.0),  # 0
    ]
    s = compute_scores(three, scoring_config)
    assert s.overall_available is True
    # Weights pace .30, pause .30, vocal .20 -> renorm sum .80
    expected = (0.30 * 100 + 0.30 * 70 + 0.20 * 0) / 0.80
    assert pytest.approx(s.overall_score, abs=1e-6) == expected


def test_median_aggregation_over_multiple_rules(scoring_config):
    # Two valid pace measurements R=1 and R=3 -> median 2 -> score 35.
    s = compute_scores(
        [_m("pace", "pace_word_rate", 1.0), _m("pace", "pace_phrase_duration", 3.0)],
        scoring_config,
    )
    assert pytest.approx(_score_of(s, "pace").score, abs=1e-6) == 35.0
