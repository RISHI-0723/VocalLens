"""Evidence quality (ARCHITECTURE.md §8.7).

``evidence_quality`` is a transparent heuristic index, NOT a calibrated
probability that a detection is correct. Components A/F/S/M are combined with the
configured weights. If alignment/mapping is unavailable or the signal is invalid,
Q is unavailable rather than a reassuring number; missing components are never
replaced with zero.
"""
from __future__ import annotations

from typing import List, Optional

from .config import AnalysisConfig
from .schemas import QualityComponents, QualityLabel, SignalState, Warning


def _label(q: Optional[float], config: AnalysisConfig) -> QualityLabel:
    if q is None:
        return QualityLabel.UNAVAILABLE
    if q >= config.quality.high_threshold:
        return QualityLabel.HIGH
    if q >= config.quality.medium_threshold:
        return QualityLabel.MEDIUM
    return QualityLabel.LOW


def compute_quality(
    A: Optional[float],
    F: Optional[float],
    S: Optional[float],
    M: Optional[float],
    signal_state: SignalState,
    config: AnalysisConfig,
    extra_warnings: Optional[List[Warning]] = None,
) -> QualityComponents:
    """Combine evidence-quality components into Q with a label.

    Q is unavailable when any component is missing or the signal is invalid; we
    do not substitute zero for a missing component (ARCHITECTURE §8.7).
    """
    warnings: List[Warning] = list(extra_warnings or [])
    qc = QualityComponents(A=A, F=F, S=S, M=M, signal_state=signal_state, warnings=warnings)

    if signal_state == SignalState.INVALID:
        warnings.append(Warning(code="quality_unavailable", message="Signal invalid; evidence quality unavailable."))
        qc.Q = None
        qc.label = QualityLabel.UNAVAILABLE
        return qc

    if any(c is None for c in (A, F, S, M)):
        warnings.append(Warning(
            code="quality_partial",
            message="One or more evidence-quality components unavailable; Q not computed.",
        ))
        qc.Q = None
        qc.label = QualityLabel.UNAVAILABLE
        return qc

    w = config.quality
    q = (
        w.alignment_weight * A
        + w.feature_coverage_weight * F
        + w.signal_quality_weight * S
        + w.mapping_weight * M
    )
    q = max(0.0, min(1.0, q))
    qc.Q = round(q, 4)
    qc.label = _label(q, config)
    return qc
