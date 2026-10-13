"""Evidence-quality formula tests (ARCHITECTURE §8.7)."""
import pytest

from vocallens.quality import compute_quality
from vocallens.schemas import QualityLabel, SignalState


def test_quality_full_components(analysis_config):
    qc = compute_quality(1.0, 1.0, 1.0, 1.0, SignalState.OK, analysis_config)
    assert qc.Q == 1.0
    assert qc.label == QualityLabel.HIGH


def test_quality_weighted_sum(analysis_config):
    # 0.35*0.8 + 0.30*0.6 + 0.20*0.5 + 0.15*0.4 = 0.62
    qc = compute_quality(0.8, 0.6, 0.5, 0.4, SignalState.LIMITED, analysis_config)
    assert pytest.approx(qc.Q, abs=1e-6) == 0.62
    assert qc.label == QualityLabel.MEDIUM


def test_quality_low_label(analysis_config):
    qc = compute_quality(0.4, 0.4, 0.5, 0.4, SignalState.LIMITED, analysis_config)
    assert qc.Q < analysis_config.quality.medium_threshold
    assert qc.label == QualityLabel.LOW


def test_missing_component_is_unavailable_not_zero(analysis_config):
    qc = compute_quality(None, 1.0, 1.0, 1.0, SignalState.OK, analysis_config)
    assert qc.Q is None
    assert qc.label == QualityLabel.UNAVAILABLE


def test_invalid_signal_unavailable(analysis_config):
    qc = compute_quality(1.0, 1.0, 0.0, 1.0, SignalState.INVALID, analysis_config)
    assert qc.Q is None
    assert qc.label == QualityLabel.UNAVAILABLE


def test_label_boundaries(analysis_config):
    high = compute_quality(1, 1, 1, 1, SignalState.OK, analysis_config)  # Q=1.0
    assert high.label == QualityLabel.HIGH
    # Exactly at the high threshold -> High.
    qc = compute_quality(0.8, 0.8, 0.8, 0.8, SignalState.OK, analysis_config)  # Q=0.8
    assert qc.Q == 0.8 and qc.label == QualityLabel.HIGH
