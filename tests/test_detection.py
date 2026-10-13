"""Detection severity, exceedance, and grouping tests (ARCHITECTURE §8.6)."""
import pytest

from vocallens.detection import _group_detections, _iou, _severity
from vocallens.schemas import (
    Detection,
    DetectionFamily,
    QualityComponents,
    Severity,
    SignalState,
)


def test_severity_boundaries(analysis_config):
    assert _severity(0.99, analysis_config) == Severity.UNAVAILABLE
    assert _severity(1.00, analysis_config) == Severity.LOW
    assert _severity(1.49, analysis_config) == Severity.LOW
    assert _severity(1.50, analysis_config) == Severity.MODERATE
    assert _severity(2.49, analysis_config) == Severity.MODERATE
    assert _severity(2.50, analysis_config) == Severity.HIGH
    assert _severity(9.9, analysis_config) == Severity.HIGH


def test_iou_basic():
    assert _iou(0, 1, 0, 1) == 1.0
    assert _iou(0, 1, 2, 3) == 0.0
    assert pytest.approx(_iou(0, 2, 1, 3), abs=1e-6) == 1 / 3


def _det(rule, family, start, end, R, phrase="p0"):
    return Detection(
        detection_id=f"{phrase}_{rule}", family=family, rule_id=rule,
        participant_start=start, participant_end=end, reference_start=start, reference_end=end,
        matched_phrase_id=phrase, feature_name="f", participant_value=1.0, reference_value=0.0,
        delta=1.0, unit="u", threshold=0.5, normalized_exceedance=R, display_exceedance=R,
        severity=Severity.HIGH, quality=QualityComponents(signal_state=SignalState.OK),
        explanation="", caveat="",
    )


def test_same_family_merge_preserves_rule_ids(analysis_config):
    d1 = _det("pace_word_rate", DetectionFamily.PACE, 0.0, 2.0, 3.0)
    d2 = _det("pace_phrase_duration", DetectionFamily.PACE, 0.0, 2.0, 2.0)
    merged = _group_detections([d1, d2], analysis_config)
    assert len(merged) == 1
    assert "pace_phrase_duration" in merged[0].merged_rule_ids
    # Primary keeps the higher exceedance rule.
    assert merged[0].rule_id == "pace_word_rate"


def test_cross_family_event_group(analysis_config):
    d1 = _det("pace_word_rate", DetectionFamily.PACE, 0.0, 2.0, 3.0)
    d2 = _det("pause_duration", DetectionFamily.PAUSE, 0.0, 2.0, 2.0)
    merged = _group_detections([d1, d2], analysis_config)
    assert len(merged) == 2
    assert all(d.event_group_id == "group_p0" for d in merged)


def test_standalone_detection_has_no_group(analysis_config):
    d1 = _det("pace_word_rate", DetectionFamily.PACE, 0.0, 2.0, 3.0)
    merged = _group_detections([d1], analysis_config)
    assert merged[0].event_group_id is None
