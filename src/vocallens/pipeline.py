"""The single public analysis entry point (ARCHITECTURE.md §6, §8).

``analyze_pair`` is the one pipeline the dashboard, evaluation script, and
exporters all call. It returns a validated :class:`AnalysisResult` with explicit
``complete`` / ``partial`` / ``failed`` status, never fabricating alignment,
features, or scores when a stage cannot be completed.
"""
from __future__ import annotations

import datetime as _dt
import platform
import sys
import time
from typing import Dict, List, Optional, Tuple

import numpy as np

from . import SCHEMA_VERSION, __version__
from .alignment import align
from .audio_io import AudioData, AudioValidationError, load_audio
from .config import (
    AnalysisConfig,
    ScoringConfig,
    load_analysis_config,
    load_scoring_config,
)
from .detection import evaluate_phrases
from .explanations import annotate
from .features import (
    FrameFeatures,
    compute_frame_features,
    detect_pauses,
    median_iqr,
    pitch_variability_iqr_semitones,
    recording_energy_stats,
    syllable_rate,
    word_rate,
)
from .region_mapping import _token_timing_map, map_regions
from .scoring import compute_scores
from .schemas import (
    AlignmentResultModel,
    AlignmentStatus,
    AnalysisRequest,
    AnalysisResult,
    AnalysisStatus,
    FeatureSeries,
    Provenance,
    ScalarFeature,
    StageTimings,
    Warning,
)
from .transcript import normalize_transcript


def _pkg_versions() -> Dict[str, str]:
    import importlib.metadata as m

    out: Dict[str, str] = {}
    for p in ("numpy", "scipy", "librosa", "soundfile", "pydantic", "plotly", "pronouncing"):
        try:
            out[p] = m.version(p)
        except Exception:
            out[p] = "unavailable"
    try:
        out["whisperx"] = m.version("whisperx")
    except Exception:
        out["whisperx"] = "not_installed"
    return out


def _nan_to_none(values: np.ndarray) -> List[Optional[float]]:
    return [None if not np.isfinite(v) else round(float(v), 4) for v in values]


def _feature_series(role: str, ff: FrameFeatures) -> List[FeatureSeries]:
    times = [round(float(t), 4) for t in ff.times]
    return [
        FeatureSeries(
            name=f"{role}_rms_dbfs", unit="dBFS", times=times,
            values=_nan_to_none(ff.rms_dbfs),
            valid_mask=[bool(x) for x in ff.speech_mask],
            settings={"noise_floor_dbfs": round(ff.noise_floor_dbfs, 2),
                      "noise_floor_reliable": ff.noise_floor_reliable},
        ),
        FeatureSeries(
            name=f"{role}_f0_hz", unit="Hz", times=times,
            values=_nan_to_none(ff.f0_hz),
            valid_mask=[bool(x) for x in ff.voiced_mask],
            settings={},
        ),
    ]


def _scalar_features(
    role: str, ff: FrameFeatures, pauses, config: AnalysisConfig, words: List[str], duration: float
) -> List[ScalarFeature]:
    med_hz, iqr_semis, vcov, pvalid = pitch_variability_iqr_semitones(
        ff.f0_hz, ff.voiced_mask, config, int(ff.speech_mask.sum()))
    emed, eiqr, scov = recording_energy_stats(ff, config)
    wr = word_rate(len(words), duration)
    srate, scov_syll = syllable_rate(words, duration, config)
    total_pause = round(sum(b - a for a, b in pauses), 4)
    feats = [
        ScalarFeature(name="median_f0_hz", value=(round(med_hz, 2) if med_hz else None),
                      unit="Hz", valid=med_hz is not None, coverage=round(vcov, 4)),
        ScalarFeature(name="pitch_iqr_semitones", value=(round(iqr_semis, 3) if iqr_semis is not None else None),
                      unit="semitones", valid=pvalid, coverage=round(vcov, 4)),
        ScalarFeature(name="word_rate", value=(round(wr, 3) if wr else None),
                      unit="words_per_second", valid=wr is not None),
        ScalarFeature(name="syllable_rate", value=(round(srate, 3) if srate else None),
                      unit="syllables_per_second", valid=srate is not None, coverage=round(scov_syll, 4)),
        ScalarFeature(name="speech_median_dbfs", value=(round(emed, 2) if emed is not None else None),
                      unit="dBFS", valid=emed is not None, coverage=round(scov, 4)),
        ScalarFeature(name="speech_iqr_db", value=(round(eiqr, 2) if eiqr is not None else None),
                      unit="dB", valid=eiqr is not None),
        ScalarFeature(name="total_pause_seconds", value=total_pause, unit="seconds", valid=True),
        ScalarFeature(name="pause_count", value=float(len(pauses)), unit="count", valid=True),
    ]
    return feats


def analyze_pair(
    request: AnalysisRequest,
    analysis_config: Optional[AnalysisConfig] = None,
    scoring_config: Optional[ScoringConfig] = None,
) -> AnalysisResult:
    """Analyze participant delivery against a reference for shared text."""
    t0 = time.perf_counter()
    timings: Dict[str, float] = {}
    config = analysis_config or load_analysis_config()
    score_cfg = scoring_config or load_scoring_config()

    result = AnalysisResult(
        schema_version=SCHEMA_VERSION, sample_id=request.sample_id,
        status=AnalysisStatus.FAILED, transcript_original=request.transcript,
    )
    result.provenance = Provenance(
        software_version=__version__, python_version=platform.python_version(),
        schema_version=SCHEMA_VERSION,
        analysis_config_hash=config.config_hash, scoring_config_hash=score_cfg.config_hash,
        package_versions=_pkg_versions(),
        created_utc=_dt.datetime.now(_dt.timezone.utc).isoformat(),
    )

    # --- Validate + decode ---
    stage = time.perf_counter()
    try:
        if not request.transcript or not request.transcript.strip():
            raise AudioValidationError(
                "empty_transcript",
                "Enter the shared transcript. The aligner needs the words to map them to audio.")
        ref_audio = load_audio(request.reference_audio, "reference", config)
        par_audio = load_audio(request.participant_audio, "participant", config)
    except AudioValidationError as exc:
        result.warnings.append(Warning(code=exc.code, message=exc.message))
        result.failure_reason = exc.message
        timings["validate_decode"] = time.perf_counter() - stage
        result.stage_timings = StageTimings(timings_seconds={k: round(v, 4) for k, v in timings.items()})
        return result
    timings["validate_decode"] = time.perf_counter() - stage
    result.reference_audio = ref_audio.metadata()
    result.participant_audio = par_audio.metadata()
    for a in (ref_audio, par_audio):
        result.warnings.extend(a.warnings)

    # --- Transcript ---
    original, tokens = normalize_transcript(request.transcript)
    result.tokens = tokens

    # --- Alignment (independent per recording) ---
    stage = time.perf_counter()
    ref_align = align("reference", request.reference_audio, tokens, original, config,
                      ref_audio.duration_seconds, request.language,
                      backend=request.alignment_backend, provided_words=request.reference_provided_words)
    par_align = align("participant", request.participant_audio, tokens, original, config,
                      par_audio.duration_seconds, request.language,
                      backend=request.alignment_backend, provided_words=request.participant_provided_words)
    timings["alignment"] = time.perf_counter() - stage
    result.reference_alignment = ref_align
    result.participant_alignment = par_align
    result.provenance.alignment_backend = ref_align.backend
    result.provenance.alignment_model = ref_align.model
    for al in (ref_align, par_align):
        for w in al.warnings:
            result.warnings.append(w)

    # --- Region mapping ---
    stage = time.perf_counter()
    region = map_regions(tokens, original, ref_align, par_align, config)
    timings["region_mapping"] = time.perf_counter() - stage
    result.region_mapping = region
    result.warnings.extend(region.warnings)

    # --- Features ---
    stage = time.perf_counter()
    ref_ff = compute_frame_features(ref_audio, config)
    par_ff = compute_frame_features(par_audio, config)
    ref_pauses = detect_pauses(ref_ff.times, ref_ff.rms_dbfs, ref_ff.noise_floor_dbfs, config)
    par_pauses = detect_pauses(par_ff.times, par_ff.rms_dbfs, par_ff.noise_floor_dbfs, config)
    timings["features"] = time.perf_counter() - stage

    result.reference_features = _feature_series("reference", ref_ff)
    result.participant_features = _feature_series("participant", par_ff)
    result.reference_scalar_features = _scalar_features(
        "reference", ref_ff, ref_pauses, config, [t.text for t in tokens], ref_audio.duration_seconds)
    result.participant_scalar_features = _scalar_features(
        "participant", par_ff, par_pauses, config, [t.text for t in tokens], par_audio.duration_seconds)

    # --- Detection + scoring (only when regions are mappable) ---
    stage = time.perf_counter()
    detections = []
    measurements = []
    if region.status != "unavailable" and region.phrases:
        ref_map, _ = _token_timing_map([t.text for t in tokens], ref_align)
        par_map, _ = _token_timing_map([t.text for t in tokens], par_align)
        measurements, detections = evaluate_phrases(
            region.phrases, ref_ff, par_ff, ref_pauses, par_pauses, ref_map, par_map,
            ref_audio, par_audio, ref_align, par_align, config)
        detections = [annotate(d) for d in detections]
    timings["detection"] = time.perf_counter() - stage

    detections.sort(key=lambda d: (d.participant_start, -d.normalized_exceedance))
    result.detections = detections

    stage = time.perf_counter()
    result.scores = compute_scores(measurements, score_cfg)
    timings["scoring"] = time.perf_counter() - stage

    # --- Status ---
    result.status = _overall_status(ref_align, par_align, region, detections, measurements)
    timings["total"] = time.perf_counter() - t0
    result.stage_timings = StageTimings(timings_seconds={k: round(v, 4) for k, v in timings.items()})
    return result


def _overall_status(ref_align, par_align, region, detections, measurements) -> AnalysisStatus:
    complete_aligns = {AlignmentStatus.COMPLETE}
    if ref_align.status in complete_aligns and par_align.status in complete_aligns and region.status == "complete":
        return AnalysisStatus.COMPLETE
    if (ref_align.status in (AlignmentStatus.UNAVAILABLE, AlignmentStatus.FAILED)
            and par_align.status in (AlignmentStatus.UNAVAILABLE, AlignmentStatus.FAILED)
            and not measurements):
        # Nothing could be grounded at all.
        return AnalysisStatus.PARTIAL
    return AnalysisStatus.PARTIAL
