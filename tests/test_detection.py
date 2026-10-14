"""Detection severity, exceedance, and grouping tests (ARCHITECTURE §8.6)."""
import numpy as np
import pytest

from vocallens.audio_io import AudioData
from vocallens.detection import _group_detections, _iou, _severity, evaluate_phrases
from vocallens.features import FrameFeatures
from vocallens.schemas import (
    AlignmentResultModel,
    AlignmentStatus,
    Detection,
    DetectionFamily,
    MappedPhrase,
    QualityComponents,
    Severity,
    SignalState,
    WordTiming,
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


# --------------------------------------------------------------------------- #
# Utterance-level pitch variation (ARCHITECTURE §8.6 "Pitch-variation intervals")
# --------------------------------------------------------------------------- #
def _frame_features(f0_hz_values, n=300, sr=16000, hop=160):
    """Minimal all-voiced, constant-energy FrameFeatures with a given F0 pattern."""
    times = np.arange(n) * (hop / sr)
    f0 = np.asarray(f0_hz_values, dtype=float)
    mask = np.ones(n, dtype=bool)
    return FrameFeatures(
        times=times, rms_dbfs=np.full(n, -20.0), f0_hz=f0,
        voiced_mask=mask, speech_mask=mask, noise_floor_dbfs=-60.0,
        noise_floor_reliable=True, sr=sr, hop=hop,
    )


def _audio():
    return AudioData(
        role="r", samples=np.zeros(48000, dtype=np.float32), analysis_sr=16000,
        original_sr=16000, channels=1, duration_seconds=3.0, peak_amplitude=0.3,
        clipping_detected=False, clipping_fraction=0.0, channel_rms_imbalance_db=None,
        filename="x", warnings=[],
    )


def _alignment(words):
    return AlignmentResultModel(
        role="r", backend="provided", language="en-US", status=AlignmentStatus.COMPLETE,
        words=words, aligned_token_count=len(words), expected_token_count=len(words),
        coverage=1.0, warnings=[], duration_seconds=3.0,
    )


def _pitch_setup(ref_f0, par_f0):
    n = 300
    ref_ff = _frame_features(ref_f0(np.arange(n)))
    par_ff = _frame_features(par_f0(np.arange(n)))
    words = [WordTiming(token_index=0, text="a", start=0.0, end=1.4),
             WordTiming(token_index=1, text="b", start=1.5, end=2.99)]
    ref_map = {0: words[0], 1: words[1]}
    par_map = {0: words[0], 1: words[1]}
    phrase = MappedPhrase(
        phrase_id="phrase_00", token_indices=[0, 1], text="a b",
        reference_start=0.0, reference_end=2.99, participant_start=0.0, participant_end=2.99,
        matched_fraction=1.0, eligible=True,
    )
    return [phrase], ref_ff, par_ff, ref_map, par_map, _alignment(words), _alignment(words)


def test_utterance_pitch_rule_detects_monotone(analysis_config):
    """A flattened (monotone) participant pitch must emit a pitch_variation
    detection via the whole-utterance semitone-IQR rule.

    Regression guard: per-phrase pitch comparison alone missed monotone delivery
    (recall 0.0 on the held-out pilot); the utterance-level rule restores it.
    """
    phrases, ref_ff, par_ff, ref_map, par_map, ref_al, par_al = _pitch_setup(
        ref_f0=lambda i: 120.0 + 100.0 * (i % 2),   # varied F0 -> high semitone IQR
        par_f0=lambda i: np.full_like(i, 150.0, dtype=float),  # constant -> ~0 IQR
    )
    _, dets = evaluate_phrases(
        phrases, ref_ff, par_ff, [], [], ref_map, par_map,
        _audio(), _audio(), ref_al, par_al, analysis_config)
    pitch = [d for d in dets if d.family == DetectionFamily.PITCH_VARIATION]
    assert any(d.rule_id == "pitch_variation_iqr_utterance" for d in pitch)


def test_utterance_pitch_rule_no_false_positive_when_identical(analysis_config):
    """Identical pitch on both recordings must NOT emit a pitch_variation flag."""
    phrases, ref_ff, par_ff, ref_map, par_map, ref_al, par_al = _pitch_setup(
        ref_f0=lambda i: 120.0 + 100.0 * (i % 2),
        par_f0=lambda i: 120.0 + 100.0 * (i % 2),
    )
    _, dets = evaluate_phrases(
        phrases, ref_ff, par_ff, [], [], ref_map, par_map,
        _audio(), _audio(), ref_al, par_al, analysis_config)
    assert not any(d.family == DetectionFamily.PITCH_VARIATION for d in dets)
