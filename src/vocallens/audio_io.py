"""Audio ingestion and preprocessing (ARCHITECTURE.md §6).

Decodes to floating-point mono, resamples an analysis copy to the configured rate
(16 kHz default), preserves original metadata, and records peak/clipping/channel
information. The waveform is NOT loudness- or peak-normalized before energy
analysis. Corrupt audio and out-of-limit durations are rejected with actionable
messages.
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import numpy as np

from .config import AnalysisConfig
from .schemas import AudioMetadata, Warning


class AudioValidationError(ValueError):
    """Raised for unreadable/out-of-limit audio; carries a user-facing message."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class AudioData:
    """Preprocessed audio for analysis plus preserved source metadata."""

    role: str
    samples: np.ndarray  # float32 mono at analysis_sr (NOT normalized)
    analysis_sr: int
    original_sr: int
    channels: int
    duration_seconds: float
    peak_amplitude: float
    clipping_detected: bool
    clipping_fraction: float
    channel_rms_imbalance_db: Optional[float]
    filename: Optional[str]
    warnings: List[Warning] = field(default_factory=list)

    def metadata(self) -> AudioMetadata:
        return AudioMetadata(
            role=self.role,
            original_sample_rate_hz=self.original_sr,
            channels=self.channels,
            duration_seconds=round(self.duration_seconds, 4),
            peak_amplitude=round(float(self.peak_amplitude), 6),
            clipping_detected=self.clipping_detected,
            clipping_fraction=round(self.clipping_fraction, 6),
            analysis_sample_rate_hz=self.analysis_sr,
            filename=self.filename,
        )


def _rms_db(x: np.ndarray) -> float:
    if x.size == 0:
        return -math.inf
    rms = float(np.sqrt(np.mean(np.square(x, dtype=np.float64))))
    if rms <= 0:
        return -math.inf
    return 20.0 * math.log10(rms)


def load_audio(
    path: str | Path,
    role: str,
    config: AnalysisConfig,
    display_name: Optional[str] = None,
) -> AudioData:
    """Load, validate, and preprocess one recording per ARCHITECTURE §6."""
    import soundfile as sf

    p = Path(path)
    if not p.exists():
        raise AudioValidationError("file_missing", f"Audio file not found: {p.name}")

    size_mb = os.path.getsize(p) / (1024 * 1024)
    if size_mb > config.audio.max_upload_mb:
        raise AudioValidationError(
            "file_too_large",
            f"File exceeds the configured {config.audio.max_upload_mb} MB limit.",
        )

    try:
        data, sr = sf.read(str(p), always_2d=True, dtype="float32")
    except Exception as exc:
        raise AudioValidationError(
            "decode_failed",
            "This audio file could not be decoded. Try a WAV or supported MP3 file.",
        ) from exc

    if data.size == 0:
        raise AudioValidationError("empty_audio", "The audio file contains no samples.")
    if not np.all(np.isfinite(data)):
        raise AudioValidationError("nonfinite_samples", "The audio contains non-finite samples.")

    channels = data.shape[1]
    warnings: List[Warning] = []

    # Channel RMS imbalance (before downmix) for the signal-quality check.
    channel_imbalance_db: Optional[float] = None
    if channels >= 2:
        ch_db = [_rms_db(data[:, c]) for c in range(channels)]
        finite = [d for d in ch_db if math.isfinite(d)]
        if len(finite) >= 2:
            channel_imbalance_db = abs(max(finite) - min(finite))
            if channel_imbalance_db >= config.signal_quality.channel_rms_imbalance_db.minor_warning_at_or_above:
                warnings.append(Warning(
                    code="channel_imbalance",
                    message=f"Channel RMS imbalance {channel_imbalance_db:.1f} dB before downmix.",
                ))

    # Downmix to mono by channel averaging (documented policy).
    mono = np.mean(data, axis=1).astype(np.float32)

    peak = float(np.max(np.abs(mono))) if mono.size else 0.0
    clip_thr = config.audio.clipping_peak_threshold
    clip_mask = np.abs(mono) >= clip_thr
    clipping_fraction = float(np.mean(clip_mask)) if mono.size else 0.0
    clipping_detected = bool(clipping_fraction > 0)
    if clipping_detected:
        warnings.append(Warning(
            code="clipping_detected",
            message=f"Clipping detected in {clipping_fraction*100:.2f}% of samples.",
        ))

    duration = mono.shape[0] / float(sr)
    if duration < config.audio.min_duration_seconds:
        raise AudioValidationError(
            "too_short",
            "This clip is shorter than the configured minimum. Upload a longer recording.",
        )
    if duration > config.audio.max_duration_seconds:
        raise AudioValidationError(
            "too_long",
            "This clip exceeds the configured duration limit. Trim it and try again.",
        )

    # Resample the analysis copy (do not touch original on disk).
    target_sr = config.audio.analysis_sample_rate_hz
    if sr != target_sr:
        import librosa

        mono_rs = librosa.resample(mono, orig_sr=sr, target_sr=target_sr).astype(np.float32)
    else:
        mono_rs = mono

    return AudioData(
        role=role,
        samples=mono_rs,
        analysis_sr=target_sr,
        original_sr=int(sr),
        channels=int(channels),
        duration_seconds=duration,
        peak_amplitude=peak,
        clipping_detected=clipping_detected,
        clipping_fraction=clipping_fraction,
        channel_rms_imbalance_db=channel_imbalance_db,
        filename=display_name if display_name is not None else p.name,
        warnings=warnings,
    )
