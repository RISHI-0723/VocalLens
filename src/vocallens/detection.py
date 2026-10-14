"""Candidate deviation detection and temporal grounding (ARCHITECTURE.md §8.6).

For every eligible mapped phrase, each rule is evaluated over the recording's own
mapped interval. Every valid rule measurement (including sub-threshold ones) is
recorded for scoring; a detection is emitted only when R = D/T >= 1. Detections
carry traceable evidence: values, delta, unit, threshold, normalized exceedance,
severity, and evidence quality. Same-family overlapping detections on a phrase
merge (preserving rule IDs); cross-family detections on the same phrase share an
``event_group_id``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

from .config import AnalysisConfig
from .features import (
    FrameFeatures,
    pitch_variability_iqr_semitones,
    recording_energy_stats,
    region_indices,
    relative_energy_zrel,
    signal_state_for_region,
    word_rate,
    worst_of,
)
from .quality import compute_quality
from .schemas import (
    AlignmentResultModel,
    Detection,
    DetectionFamily,
    MappedPhrase,
    QualityComponents,
    RegionMappingModel,
    Severity,
    SignalState,
    WordTiming,
)

# Rule -> (family, scoring dimension)
RULE_FAMILY = {
    "pace_word_rate": (DetectionFamily.PACE, "pace"),
    "pace_phrase_duration": (DetectionFamily.PACE, "pace"),
    "pause_duration": (DetectionFamily.PAUSE, "pause_management"),
    "pitch_variation_iqr": (DetectionFamily.PITCH_VARIATION, "vocal_variation"),
    "pitch_variation_iqr_utterance": (DetectionFamily.PITCH_VARIATION, "vocal_variation"),
    "energy_dynamics_zrel": (DetectionFamily.ENERGY_DYNAMICS, "energy_control"),
}


@dataclass
class RuleMeasurement:
    """One valid rule evaluation on one phrase (basis for scoring + detections)."""

    rule_id: str
    dimension: str
    family: DetectionFamily
    phrase_id: str
    feature_name: str
    unit: str
    participant_value: Optional[float]
    reference_value: Optional[float]
    delta: Optional[float]
    threshold: float
    R: Optional[float]  # uncapped normalized exceedance, clamped at min 0
    valid: bool
    par_start: Optional[float] = None
    par_end: Optional[float] = None
    ref_start: Optional[float] = None
    ref_end: Optional[float] = None


def _pause_duration_in_region(ff: FrameFeatures, pauses: List[Tuple[float, float]], start: float, end: float) -> float:
    total = 0.0
    for a, b in pauses:
        lo, hi = max(a, start), min(b, end)
        if hi > lo:
            total += hi - lo
    return total


def _severity(R: float, config: AnalysisConfig) -> Severity:
    if R < 1.0:
        return Severity.UNAVAILABLE  # not a detection
    if R < config.detection.severity_low_upper_ratio:
        return Severity.LOW
    if R < config.detection.severity_moderate_upper_ratio:
        return Severity.MODERATE
    return Severity.HIGH


def _count_tokens(idxs: List[int], tmap: Dict[int, WordTiming]) -> int:
    return sum(1 for i in idxs if i in tmap)


def evaluate_phrases(
    phrases: List[MappedPhrase],
    ref_ff: FrameFeatures,
    par_ff: FrameFeatures,
    ref_pauses: List[Tuple[float, float]],
    par_pauses: List[Tuple[float, float]],
    ref_map: Dict[int, WordTiming],
    par_map: Dict[int, WordTiming],
    ref_audio,
    par_audio,
    ref_alignment: AlignmentResultModel,
    par_alignment: AlignmentResultModel,
    config: AnalysisConfig,
) -> Tuple[List[RuleMeasurement], List[Detection]]:
    """Return (all valid rule measurements, emitted+grouped detections)."""
    thresholds = config.detection.thresholds
    measurements: List[RuleMeasurement] = []
    candidate_detections: List[Detection] = []

    # Recording-level energy stats for z_rel standardization.
    ref_emed, ref_eiqr, _ = recording_energy_stats(ref_ff, config)
    par_emed, par_eiqr, _ = recording_energy_stats(par_ff, config)

    for phrase in phrases:
        if not phrase.eligible:
            continue
        rs, re = phrase.reference_start, phrase.reference_end
        ps, pe = phrase.participant_start, phrase.participant_end
        if None in (rs, re, ps, pe):
            continue
        ref_idx = region_indices(ref_ff.times, rs, re)
        par_idx = region_indices(par_ff.times, ps, pe)
        ref_dur = re - rs
        par_dur = pe - ps

        # Per-phrase evidence-quality context (shared across families on phrase).
        A = None
        if ref_alignment.coverage is not None and par_alignment.coverage is not None:
            A = (ref_alignment.coverage + par_alignment.coverage) / 2.0
        M = phrase.matched_fraction
        F_ref = float(np.mean(ref_ff.speech_mask[ref_idx])) if ref_idx.size else 0.0
        F_par = float(np.mean(par_ff.speech_mask[par_idx])) if par_idx.size else 0.0
        F = (F_ref + F_par) / 2.0
        ref_state, ref_S, ref_sw = signal_state_for_region(ref_audio, ref_ff, ref_idx, config)
        par_state, par_S, par_sw = signal_state_for_region(par_audio, par_ff, par_idx, config)
        region_state = worst_of(ref_state, par_state)
        S = min(ref_S, par_S)
        sig_warnings = ref_sw + par_sw

        def qc() -> QualityComponents:
            return compute_quality(A, F, S, M, region_state, config, extra_warnings=list(sig_warnings))

        # --- Pace: word rate ---
        ref_words = _count_tokens(phrase.token_indices, ref_map)
        par_words = _count_tokens(phrase.token_indices, par_map)
        r_wr = word_rate(ref_words, ref_dur)
        p_wr = word_rate(par_words, par_dur)
        _add_rule(
            measurements, candidate_detections, "pace_word_rate", phrase,
            p_wr, r_wr, thresholds["pace_word_rate"].value, "words_per_second",
            "word_rate", ps, pe, rs, re, config, qc,
            "Aligned words per second differs from the reference in this phrase.",
        )

        # --- Pace: phrase duration ---
        _add_rule(
            measurements, candidate_detections, "pace_phrase_duration", phrase,
            par_dur, ref_dur, thresholds["pace_phrase_duration"].value, "seconds",
            "phrase_duration", ps, pe, rs, re, config, qc,
            "Phrase duration differs from the reference.",
        )

        # --- Pause duration within the phrase ---
        r_pause = _pause_duration_in_region(ref_ff, ref_pauses, rs, re)
        p_pause = _pause_duration_in_region(par_ff, par_pauses, ps, pe)
        _add_rule(
            measurements, candidate_detections, "pause_duration", phrase,
            p_pause, r_pause, thresholds["pause_duration"].value, "seconds",
            "pause_duration", ps, pe, rs, re, config, qc,
            "Total detected pause within the matched phrase differs from the reference.",
        )

        # --- Pitch variation (semitone IQR) ---
        r_speech_n = int(ref_ff.speech_mask[ref_idx].sum())
        p_speech_n = int(par_ff.speech_mask[par_idx].sum())
        r_med, r_iqr, r_vcov, r_valid = pitch_variability_iqr_semitones(
            ref_ff.f0_hz[ref_idx], ref_ff.voiced_mask[ref_idx], config, r_speech_n)
        p_med, p_iqr, p_vcov, p_valid = pitch_variability_iqr_semitones(
            par_ff.f0_hz[par_idx], par_ff.voiced_mask[par_idx], config, p_speech_n)
        if r_valid and p_valid:
            _add_rule(
                measurements, candidate_detections, "pitch_variation_iqr", phrase,
                p_iqr, r_iqr, thresholds["pitch_variation_iqr"].value, "semitones",
                "pitch_iqr_semitones", ps, pe, rs, re, config, qc,
                "Pitch variability (semitone IQR) differs from the reference.",
            )
        else:
            measurements.append(RuleMeasurement(
                "pitch_variation_iqr", "vocal_variation", DetectionFamily.PITCH_VARIATION,
                phrase.phrase_id, "pitch_iqr_semitones", "semitones", p_iqr, r_iqr, None,
                thresholds["pitch_variation_iqr"].value, None, valid=False))

        # --- Energy dynamics (standardized relative energy) ---
        if None not in (ref_emed, ref_eiqr, par_emed, par_eiqr) and ref_idx.size and par_idx.size:
            ref_phrase_med = float(np.median(ref_ff.rms_dbfs[ref_idx][ref_ff.speech_mask[ref_idx]])) if ref_ff.speech_mask[ref_idx].any() else None
            par_phrase_med = float(np.median(par_ff.rms_dbfs[par_idx][par_ff.speech_mask[par_idx]])) if par_ff.speech_mask[par_idx].any() else None
            if ref_phrase_med is not None and par_phrase_med is not None:
                r_z = relative_energy_zrel(ref_phrase_med, ref_emed, ref_eiqr, config)
                p_z = relative_energy_zrel(par_phrase_med, par_emed, par_eiqr, config)
                _add_rule(
                    measurements, candidate_detections, "energy_dynamics_zrel", phrase,
                    p_z, r_z, thresholds["energy_dynamics_zrel"].value, "zscore",
                    "relative_energy_zrel", ps, pe, rs, re, config, qc,
                    "Standardized relative phrase energy differs from the reference.",
                )

    # --- Utterance-level pitch variation (ARCHITECTURE §8.6 "Pitch-variation
    # intervals"): monotone delivery reduces pitch range across the whole
    # utterance, which a short per-phrase window dilutes. Compare whole-recording
    # semitone-IQR, grounded over the union of eligible mapped phrase regions.
    eligible = [p for p in phrases if p.eligible
                and None not in (p.reference_start, p.reference_end,
                                 p.participant_start, p.participant_end)]
    if eligible:
        u_rs = min(p.reference_start for p in eligible)
        u_re = max(p.reference_end for p in eligible)
        u_ps = min(p.participant_start for p in eligible)
        u_pe = max(p.participant_end for p in eligible)

        _, r_iqr_u, _, _ = pitch_variability_iqr_semitones(
            ref_ff.f0_hz, ref_ff.voiced_mask, config, int(ref_ff.speech_mask.sum()))
        _, p_iqr_u, _, _ = pitch_variability_iqr_semitones(
            par_ff.f0_hz, par_ff.voiced_mask, config, int(par_ff.speech_mask.sum()))

        ref_u_idx = region_indices(ref_ff.times, u_rs, u_re)
        par_u_idx = region_indices(par_ff.times, u_ps, u_pe)
        A_u = None
        if ref_alignment.coverage is not None and par_alignment.coverage is not None:
            A_u = (ref_alignment.coverage + par_alignment.coverage) / 2.0
        F_u = ((float(np.mean(ref_ff.speech_mask[ref_u_idx])) if ref_u_idx.size else 0.0)
               + (float(np.mean(par_ff.speech_mask[par_u_idx])) if par_u_idx.size else 0.0)) / 2.0
        M_u = float(np.mean([p.matched_fraction for p in eligible]))
        ref_state_u, ref_S_u, ref_sw_u = signal_state_for_region(ref_audio, ref_ff, ref_u_idx, config)
        par_state_u, par_S_u, par_sw_u = signal_state_for_region(par_audio, par_ff, par_u_idx, config)
        state_u = worst_of(ref_state_u, par_state_u)
        S_u = min(ref_S_u, par_S_u)
        sw_u = ref_sw_u + par_sw_u

        def qc_u() -> QualityComponents:
            return compute_quality(A_u, F_u, S_u, M_u, state_u, config, extra_warnings=list(sw_u))

        utterance_phrase = MappedPhrase(
            phrase_id="utterance",
            token_indices=[i for p in eligible for i in p.token_indices],
            text="(whole compared utterance)",
            reference_start=u_rs, reference_end=u_re,
            participant_start=u_ps, participant_end=u_pe,
            matched_fraction=round(M_u, 4), eligible=True,
        )
        _add_rule(
            measurements, candidate_detections, "pitch_variation_iqr_utterance", utterance_phrase,
            p_iqr_u, r_iqr_u, thresholds["pitch_variation_iqr"].value, "semitones",
            "pitch_iqr_semitones", u_ps, u_pe, u_rs, u_re, config, qc_u,
            "Pitch variability (semitone IQR) over the whole compared utterance differs "
            "from the reference, consistent with reduced or increased pitch range.",
        )

    detections = _group_detections(candidate_detections, config)
    return measurements, detections


def _add_rule(
    measurements: List[RuleMeasurement],
    detections: List[Detection],
    rule_id: str,
    phrase: MappedPhrase,
    p_val: Optional[float],
    r_val: Optional[float],
    threshold: float,
    unit: str,
    feature_name: str,
    ps: float, pe: float, rs: float, re: float,
    config: AnalysisConfig,
    qc_factory,
    explanation_stub: str,
) -> None:
    family, dimension = RULE_FAMILY[rule_id]
    if p_val is None or r_val is None:
        measurements.append(RuleMeasurement(
            rule_id, dimension, family, phrase.phrase_id, feature_name, unit,
            p_val, r_val, None, threshold, None, valid=False,
            par_start=ps, par_end=pe, ref_start=rs, ref_end=re))
        return
    D = abs(p_val - r_val)
    R = max(0.0, D / threshold)
    measurements.append(RuleMeasurement(
        rule_id, dimension, family, phrase.phrase_id, feature_name, unit,
        p_val, r_val, p_val - r_val, threshold, R, valid=True,
        par_start=ps, par_end=pe, ref_start=rs, ref_end=re))

    if R < 1.0:
        return  # valid measurement but sub-threshold: no detection

    severity = _severity(R, config)
    cap = config.detection.display_exceedance_cap
    quality = qc_factory()
    detection = Detection(
        detection_id=f"{phrase.phrase_id}_{rule_id}",
        family=family, rule_id=rule_id,
        participant_start=round(ps, 4), participant_end=round(pe, 4),
        reference_start=round(rs, 4), reference_end=round(re, 4),
        matched_phrase_id=phrase.phrase_id, matched_reference_text=phrase.text,
        feature_name=feature_name,
        participant_value=round(p_val, 4), reference_value=round(r_val, 4),
        delta=round(p_val - r_val, 4), unit=unit,
        threshold=threshold, normalized_exceedance=round(R, 4),
        display_exceedance=round(min(R, cap), 4), severity=severity,
        quality=quality, explanation="", caveat="",
    )
    detections.append(detection)


def _iou(a0: float, a1: float, b0: float, b1: float) -> float:
    inter = max(0.0, min(a1, b1) - max(a0, b0))
    union = (a1 - a0) + (b1 - b0) - inter
    return inter / union if union > 0 else 0.0


def _group_detections(candidates: List[Detection], config: AnalysisConfig) -> List[Detection]:
    """Merge same-family overlapping detections; tag cross-family event groups."""
    # Merge within family on the same phrase when IoU >= configured threshold.
    merged: List[Detection] = []
    by_key: Dict[Tuple[str, str], List[Detection]] = {}
    for d in candidates:
        by_key.setdefault((d.family.value, d.matched_phrase_id or ""), []).append(d)

    for group in by_key.values():
        group.sort(key=lambda d: d.normalized_exceedance, reverse=True)
        used = [False] * len(group)
        for i, d in enumerate(group):
            if used[i]:
                continue
            primary = d
            for j in range(i + 1, len(group)):
                if used[j]:
                    continue
                o = group[j]
                if _iou(primary.participant_start, primary.participant_end,
                        o.participant_start, o.participant_end) >= config.detection.same_family_merge_iou:
                    used[j] = True
                    if o.rule_id not in primary.merged_rule_ids:
                        primary.merged_rule_ids.append(o.rule_id)
            used[i] = True
            merged.append(primary)

    # Cross-family grouping: detections on the same phrase from different families.
    phrase_families: Dict[str, set] = {}
    for d in merged:
        phrase_families.setdefault(d.matched_phrase_id or "", set()).add(d.family.value)
    for d in merged:
        pid = d.matched_phrase_id or ""
        if len(phrase_families.get(pid, set())) >= 2:
            d.event_group_id = f"group_{pid}"
    return merged
