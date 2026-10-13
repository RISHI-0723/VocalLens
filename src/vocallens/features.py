"""Acoustic feature extraction (ARCHITECTURE.md §8.5).

Frame-level RMS/dBFS, pause detection, F0 and semitone-IQR pitch variability,
within-recording relative energy, word/syllable rate, plus signal-quality
assessment (§8.7) and MFCC diagnostics. Units and validity travel with every
value; missing/unreliable values are ``None``, never ``0``. Waveforms are not
loudness-normalized before energy analysis.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np

from .audio_io import AudioData
from .config import AnalysisConfig
from .schemas import SignalState, Warning

_NEG_INF_DB = -200.0


@dataclass
class FrameFeatures:
    """Per-frame series shared by region-level computations."""

    times: np.ndarray            # frame center times (s)
    rms_dbfs: np.ndarray         # RMS in dBFS per frame
    f0_hz: np.ndarray            # F0 (Hz); NaN where unvoiced
    voiced_mask: np.ndarray      # bool, voiced frames
    speech_mask: np.ndarray      # bool, non-silent speech frames
    noise_floor_dbfs: float
    noise_floor_reliable: bool
    sr: int
    hop: int


def _frame_params(config: AnalysisConfig, sr: int) -> Tuple[int, int]:
    frame = int(round(config.framing.frame_length_ms / 1000.0 * sr))
    hop = int(round(config.framing.hop_length_ms / 1000.0 * sr))
    return max(1, frame), max(1, hop)


def frame_rms_dbfs(samples: np.ndarray, sr: int, config: AnalysisConfig) -> Tuple[np.ndarray, np.ndarray]:
    """Frame RMS as dBFS (0 dBFS = full-scale 1.0). Returns (times, rms_dbfs)."""
    import librosa

    frame, hop = _frame_params(config, sr)
    if samples.shape[0] < frame:
        samples = np.pad(samples, (0, frame - samples.shape[0]))
    rms = librosa.feature.rms(y=samples, frame_length=frame, hop_length=hop, center=True)[0]
    floor = config.framing.rms_floor_dbfs
    with np.errstate(divide="ignore"):
        db = 20.0 * np.log10(np.maximum(rms, 1e-12))
    db = np.maximum(db, floor)
    times = librosa.frames_to_time(np.arange(len(db)), sr=sr, hop_length=hop)
    return times, db


def estimate_noise_floor(rms_dbfs: np.ndarray, config: AnalysisConfig) -> Tuple[float, bool]:
    """Noise floor from low-energy frames (configured percentile)."""
    if rms_dbfs.size < config.pause_detection.min_noise_frames:
        return config.pause_detection.absolute_silence_ceiling_dbfs, False
    nf = float(np.percentile(rms_dbfs, config.pause_detection.noise_floor_percentile))
    # Reliable only if there is meaningful spread between noise and speech energy.
    spread = float(np.percentile(rms_dbfs, 90) - nf)
    reliable = spread >= 6.0
    return nf, reliable


def _silence_threshold(noise_floor: float, config: AnalysisConfig) -> float:
    """Combine the absolute ceiling with the noise-floor-relative margin.

    A frame is silence if it is below BOTH the absolute ceiling and the
    (noise_floor + margin) line, i.e. below the stricter (lower) of the two is
    too permissive; we require below the absolute ceiling AND below noise+margin.
    The effective silence threshold is the lower (quieter) of the two lines so
    that only genuinely low-energy frames count as silence.
    """
    relative_line = noise_floor + config.pause_detection.noise_floor_relative_margin_db
    return min(config.pause_detection.absolute_silence_ceiling_dbfs, relative_line)


def detect_pauses(
    times: np.ndarray, rms_dbfs: np.ndarray, noise_floor: float, config: AnalysisConfig
) -> List[Tuple[float, float]]:
    """Detect silence intervals, merge small gaps, drop short pauses."""
    if times.size == 0:
        return []
    thr = _silence_threshold(noise_floor, config)
    silent = rms_dbfs < thr
    hop_s = config.framing.hop_length_ms / 1000.0
    merge_gap = config.pause_detection.merge_gap_ms / 1000.0
    min_dur = config.pause_detection.min_pause_duration_ms / 1000.0

    # Build raw silent intervals from the boolean mask.
    intervals: List[List[float]] = []
    in_sil = False
    start = 0.0
    for i, s in enumerate(silent):
        if s and not in_sil:
            in_sil = True
            start = times[i]
        elif not s and in_sil:
            in_sil = False
            intervals.append([start, times[i]])
    if in_sil:
        intervals.append([start, times[-1] + hop_s])

    # Merge intervals separated by <= merge_gap.
    merged: List[List[float]] = []
    for iv in intervals:
        if merged and iv[0] - merged[-1][1] <= merge_gap:
            merged[-1][1] = iv[1]
        else:
            merged.append(iv)
    return [(a, b) for a, b in merged if (b - a) >= min_dur]


_F0_MIN = 65.0
_F0_MAX = 400.0
_VOICED_ZCR_MAX = 0.15  # frames with higher zero-crossing rate are treated unvoiced


def estimate_f0(samples: np.ndarray, sr: int, config: AnalysisConfig) -> Tuple[np.ndarray, np.ndarray]:
    """F0 via librosa.yin with a zero-crossing-rate voicing gate.

    ``yin`` is ~1-2 orders of magnitude faster than ``pyin`` and keeps feature
    extraction within the documented time budget. Because ``yin`` always returns
    a pitch estimate, voicing is gated by a low zero-crossing-rate heuristic plus
    the plausible F0 range; unvoiced frames are set to NaN. Returns
    (f0_hz with NaN unvoiced, voiced_mask). This is a transparent prototype
    heuristic, not a validated voicing detector.
    """
    import librosa

    frame, hop = _frame_params(config, sr)
    win = max(frame * 2, 1024)
    if samples.shape[0] < win:
        samples = np.pad(samples, (0, win - samples.shape[0]))
    try:
        f0 = librosa.yin(samples, fmin=_F0_MIN, fmax=_F0_MAX, sr=sr, frame_length=win, hop_length=hop, center=True)
        zcr = librosa.feature.zero_crossing_rate(samples, frame_length=win, hop_length=hop, center=True)[0]
    except Exception:
        return np.array([]), np.array([], dtype=bool)
    n = min(len(f0), len(zcr))
    f0 = f0[:n]
    zcr = zcr[:n]
    voiced = np.isfinite(f0) & (f0 > _F0_MIN * 1.01) & (f0 < _F0_MAX * 0.99) & (zcr < _VOICED_ZCR_MAX)
    f0 = np.where(voiced, f0, np.nan)
    return f0, voiced.astype(bool)


def compute_frame_features(audio: AudioData, config: AnalysisConfig) -> FrameFeatures:
    """Compute and cache all per-frame series for one recording."""
    sr = audio.analysis_sr
    _, hop = _frame_params(config, sr)
    times, db = frame_rms_dbfs(audio.samples, sr, config)
    nf, reliable = estimate_noise_floor(db, config)
    thr = _silence_threshold(nf, config)
    speech_mask = db >= thr
    f0, voiced = estimate_f0(audio.samples, sr, config)
    # Align lengths (pyin can differ by a frame).
    n = len(times)
    if len(f0) != n:
        f0 = _resize(f0, n, fill=np.nan)
        voiced = _resize(voiced.astype(float), n, fill=0.0).astype(bool)
    voiced = voiced & speech_mask
    return FrameFeatures(
        times=times, rms_dbfs=db, f0_hz=f0, voiced_mask=voiced, speech_mask=speech_mask,
        noise_floor_dbfs=nf, noise_floor_reliable=reliable, sr=sr, hop=hop,
    )


def _resize(arr: np.ndarray, n: int, fill: float) -> np.ndarray:
    if len(arr) == n:
        return arr
    out = np.full(n, fill, dtype=float)
    k = min(len(arr), n)
    out[:k] = arr[:k]
    return out


# --------------------------------------------------------------------------- #
# Region-level helpers
# --------------------------------------------------------------------------- #
def region_indices(times: np.ndarray, start: float, end: float) -> np.ndarray:
    return np.where((times >= start) & (times <= end))[0]


def median_iqr(values: np.ndarray) -> Tuple[Optional[float], Optional[float]]:
    v = values[np.isfinite(values)]
    if v.size == 0:
        return None, None
    med = float(np.median(v))
    iqr = float(np.percentile(v, 75) - np.percentile(v, 25))
    return med, iqr


def hz_to_semitones(f0_hz: np.ndarray) -> np.ndarray:
    """12 * log2(F0 / 1 Hz). The 1 Hz reference is a constant; it cancels in IQR."""
    v = f0_hz[np.isfinite(f0_hz) & (f0_hz > 0)]
    return 12.0 * np.log2(v / 1.0)


def pitch_variability_iqr_semitones(
    f0_hz: np.ndarray, voiced_mask: np.ndarray, config: AnalysisConfig, n_region: int
) -> Tuple[Optional[float], Optional[float], float, bool]:
    """Return (median_f0_hz, iqr_semitones, voiced_coverage, valid)."""
    voiced_vals = f0_hz[voiced_mask]
    voiced_vals = voiced_vals[np.isfinite(voiced_vals) & (voiced_vals > 0)]
    coverage = (voiced_vals.size / n_region) if n_region > 0 else 0.0
    if voiced_vals.size == 0 or coverage < config.features.min_voiced_frame_coverage:
        median_hz = float(np.median(voiced_vals)) if voiced_vals.size else None
        return median_hz, None, coverage, False
    semis = 12.0 * np.log2(voiced_vals / 1.0)
    iqr = float(np.percentile(semis, 75) - np.percentile(semis, 25))
    median_hz = float(np.median(voiced_vals))
    return median_hz, iqr, coverage, True


def relative_energy_zrel(
    phrase_median_dbfs: float, rec_median_dbfs: float, rec_iqr_dbfs: float, config: AnalysisConfig
) -> float:
    """Standardized within-recording relative energy (ARCHITECTURE §8.5)."""
    denom = max(rec_iqr_dbfs, config.features.energy_iqr_floor_db)
    return (phrase_median_dbfs - rec_median_dbfs) / denom


def recording_energy_stats(ff: FrameFeatures, config: AnalysisConfig) -> Tuple[Optional[float], Optional[float], float]:
    """Median/IQR of RMS dBFS over valid speech frames + speech coverage."""
    speech = ff.rms_dbfs[ff.speech_mask]
    coverage = (speech.size / ff.rms_dbfs.size) if ff.rms_dbfs.size else 0.0
    if speech.size == 0:
        return None, None, coverage
    med, iqr = median_iqr(speech)
    return med, iqr, coverage


def word_rate(words_in_region: int, duration: float) -> Optional[float]:
    if duration <= 0 or words_in_region <= 0:
        return None
    return words_in_region / duration


def syllable_count(word: str) -> Optional[int]:
    """CMU-dictionary syllable count (vowel-stress digits). None if OOV."""
    import pronouncing

    phones = pronouncing.phones_for_word(word.lower())
    if not phones:
        return None
    return pronouncing.syllable_count(phones[0])


def syllable_rate(
    words: List[str], duration: float, config: AnalysisConfig
) -> Tuple[Optional[float], float]:
    """English syllable rate with OOV coverage. Returns (rate, coverage)."""
    if duration <= 0 or not words:
        return None, 0.0
    counts = [syllable_count(w) for w in words]
    in_vocab = [c for c in counts if c is not None]
    coverage = len(in_vocab) / len(words)
    if coverage < config.features.min_voiced_frame_coverage or not in_vocab:
        # Reuse min coverage threshold conservatively; mark unavailable if low.
        return None, coverage
    total_syll = sum(in_vocab)
    return (total_syll / duration), coverage


# --------------------------------------------------------------------------- #
# Signal quality (ARCHITECTURE §8.7)
# --------------------------------------------------------------------------- #
def estimate_region_snr_db(
    ff: FrameFeatures, idx: np.ndarray, config: AnalysisConfig
) -> Optional[float]:
    """Region speech level minus noise floor. None if noise floor unreliable."""
    if not ff.noise_floor_reliable or idx.size == 0:
        return None
    region_db = ff.rms_dbfs[idx]
    speech = region_db[region_db >= _silence_threshold(ff.noise_floor_dbfs, config)]
    if speech.size == 0:
        return None
    speech_level = float(np.percentile(speech, 75))
    return speech_level - ff.noise_floor_dbfs


def signal_state_for_region(
    audio: AudioData, ff: FrameFeatures, idx: np.ndarray, config: AnalysisConfig,
    voiced_coverage: Optional[float] = None,
) -> Tuple[SignalState, float, List[Warning]]:
    """Worst-applicable signal state for a compared region (+ S score)."""
    warnings: List[Warning] = []
    sq = config.signal_quality
    states: List[SignalState] = []

    # Invalid first.
    if idx.size == 0 or not np.all(np.isfinite(ff.rms_dbfs[idx])):
        warnings.append(Warning(code="signal_invalid", message="Region has no valid frames."))
        return SignalState.INVALID, config.quality.signal_state_scores.signal_invalid, warnings

    # Clipping fraction (region).
    frame, hop = _frame_params(config, audio.analysis_sr)
    clip = audio.clipping_fraction
    if clip >= sq.clipping_fraction.poor_at_or_above:
        states.append(SignalState.POOR)
        warnings.append(Warning(code="signal_poor", message=f"Clipping fraction {clip:.3f} >= poor cutoff."))
    elif clip >= sq.clipping_fraction.limited_at_or_above:
        states.append(SignalState.LIMITED)
        warnings.append(Warning(code="signal_limited", message=f"Clipping fraction {clip:.3f} >= limited cutoff."))
    elif clip >= sq.clipping_fraction.minor_warning_at_or_above:
        states.append(SignalState.MINOR_WARNING)
        warnings.append(Warning(code="signal_minor_warning", message=f"Clipping fraction {clip:.3f} >= minor cutoff."))

    # SNR.
    snr = estimate_region_snr_db(ff, idx, config)
    if snr is None:
        warnings.append(Warning(code="snr_unavailable", message="Noise floor not reliable; SNR not estimated."))
    else:
        if snr < sq.estimated_snr_db.poor_below:
            states.append(SignalState.POOR)
            warnings.append(Warning(code="signal_poor", message=f"Estimated SNR {snr:.1f} dB < poor cutoff."))
        elif snr < sq.estimated_snr_db.limited_below:
            states.append(SignalState.LIMITED)
            warnings.append(Warning(code="signal_limited", message=f"Estimated SNR {snr:.1f} dB < limited cutoff."))
        elif snr < sq.estimated_snr_db.minor_warning_below:
            states.append(SignalState.MINOR_WARNING)
            warnings.append(Warning(code="signal_minor_warning", message=f"Estimated SNR {snr:.1f} dB < minor cutoff."))

    # Channel imbalance.
    imb = audio.channel_rms_imbalance_db
    if imb is not None:
        if imb >= sq.channel_rms_imbalance_db.limited_at_or_above:
            states.append(SignalState.LIMITED)
        elif imb >= sq.channel_rms_imbalance_db.minor_warning_at_or_above:
            states.append(SignalState.MINOR_WARNING)

    # Speech-frame coverage in region.
    region_speech = ff.speech_mask[idx]
    speech_cov = float(np.mean(region_speech)) if region_speech.size else 0.0
    min_speech = config.features.min_speech_frame_coverage
    if speech_cov < min_speech * sq.poor_speech_coverage_fraction_of_minimum:
        states.append(SignalState.POOR)
        warnings.append(Warning(code="signal_poor", message=f"Speech coverage {speech_cov:.2f} far below minimum."))
    # Voiced coverage below minimum -> at least limited (feature still computable).
    if voiced_coverage is not None and voiced_coverage < config.features.min_voiced_frame_coverage:
        states.append(SignalState.LIMITED)

    worst = _worst_state(states)
    score = getattr(config.quality.signal_state_scores, worst.value)
    return worst, score, warnings


_STATE_ORDER = [
    SignalState.OK, SignalState.MINOR_WARNING, SignalState.LIMITED,
    SignalState.POOR, SignalState.INVALID,
]


def _worst_state(states: List[SignalState]) -> SignalState:
    if not states:
        return SignalState.OK
    return max(states, key=lambda s: _STATE_ORDER.index(s))


def worst_of(a: SignalState, b: SignalState) -> SignalState:
    return _worst_state([a, b])


# --------------------------------------------------------------------------- #
# MFCC diagnostics (visualization only)
# --------------------------------------------------------------------------- #
def mfcc_summary(audio: AudioData, config: AnalysisConfig, n_mfcc: int = 13) -> dict:
    """MFCC coefficient-by-time matrix for the advanced diagnostics view."""
    import librosa

    sr = audio.analysis_sr
    frame, hop = _frame_params(config, sr)
    try:
        mf = librosa.feature.mfcc(y=audio.samples, sr=sr, n_mfcc=n_mfcc, n_fft=max(frame, 512), hop_length=hop)
    except Exception as exc:
        return {"available": False, "reason": f"MFCC unavailable: {exc}"}
    times = librosa.frames_to_time(np.arange(mf.shape[1]), sr=sr, hop_length=hop)
    return {
        "available": True,
        "n_mfcc": n_mfcc,
        "times": [round(float(t), 4) for t in times],
        "coefficients": mf.astype(float).round(4).tolist(),
        "note": "Diagnostic acoustic summary, not a direct flaw label.",
    }
