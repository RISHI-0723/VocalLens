"""Forced-alignment adapter (ARCHITECTURE.md §5, §8.3).

Backends:
- ``whisperx``: the canonical primary forced aligner. Attempted only if the
  package is importable; wrapped in a time budget. On import/model/timeout
  failure it returns an explicit ``unavailable``/``timed_out`` state — it never
  fabricates word timestamps.
- ``provided``: ground-truth word boundaries supplied with the request. Used for
  synthetic fixtures whose word timings are KNOWN BY CONSTRUCTION. This is not
  forced alignment and is labeled as such in the result (``backend="provided"``).

Forced alignment maps supplied words to audio; it does not verify transcript
correctness. Missing words are never given invented timestamps.
"""
from __future__ import annotations

import math
import time
from typing import Dict, List, Optional

from .config import AnalysisConfig
from .region_mapping import levenshtein_align
from .schemas import (
    AlignmentResultModel,
    AlignmentStatus,
    Token,
    Warning,
    WordTiming,
)


def _decode_audio_16k(audio_path: str, role: str, config: AnalysisConfig):
    """Decode a recording to a mono float32 array at the analysis rate.

    Reuses the project's own soundfile/librosa decoder (``audio_io.load_audio``)
    so forced alignment runs on the SAME analysis copy the features use and does
    NOT depend on an external ``ffmpeg`` binary. ``whisperx.load_audio`` shells
    out to ffmpeg, which is frequently absent; avoiding it makes the WhisperX
    path runnable wherever the core dependencies are installed.
    """
    from .audio_io import load_audio

    return load_audio(audio_path, role, config).samples


def _validate_words(
    words: List[WordTiming], duration: Optional[float]
) -> tuple[List[WordTiming], List[Warning]]:
    """Drop invalid timings (non-finite, start>end, out of bounds); warn on fixes."""
    valid: List[WordTiming] = []
    warnings: List[Warning] = []
    last_start = -math.inf
    for w in words:
        if not (math.isfinite(w.start) and math.isfinite(w.end)):
            warnings.append(Warning(code="alignment_nonfinite", message=f"Dropped non-finite timing for '{w.text}'."))
            continue
        if w.start > w.end:
            warnings.append(Warning(code="alignment_bad_interval", message=f"Dropped start>end for '{w.text}'."))
            continue
        if w.start < -1e-6:
            warnings.append(Warning(code="alignment_negative", message=f"Dropped negative start for '{w.text}'."))
            continue
        if duration is not None and w.start > duration + 1e-3:
            warnings.append(Warning(code="alignment_out_of_bounds", message=f"Dropped out-of-bounds timing for '{w.text}'."))
            continue
        if w.start + 1e-6 < last_start:
            warnings.append(Warning(code="alignment_order", message=f"Non-monotonic start near '{w.text}'."))
        last_start = w.start
        valid.append(w)
    return valid, warnings


def _coverage(aligned: int, expected: int) -> Optional[float]:
    if expected <= 0:
        return None
    return round(aligned / expected, 4)


def _status_from_coverage(coverage: Optional[float], min_cov: float) -> AlignmentStatus:
    if coverage is None or coverage <= 0:
        return AlignmentStatus.UNAVAILABLE
    if coverage >= min_cov:
        return AlignmentStatus.COMPLETE
    return AlignmentStatus.PARTIAL


def align_provided(
    role: str,
    tokens: List[Token],
    provided_words: List[Dict],
    config: AnalysisConfig,
    duration: Optional[float],
    language: str,
) -> AlignmentResultModel:
    """Build an alignment from caller-supplied ground-truth word boundaries."""
    raw = [
        WordTiming(
            token_index=-1,
            text=str(w["text"]),
            start=float(w["start"]),
            end=float(w["end"]),
            score=w.get("score"),
        )
        for w in provided_words
    ]
    valid, warnings = _validate_words(raw, duration)
    # Associate with expected tokens by sequence alignment on normalized text.
    expected = [t.text for t in tokens]
    from .transcript import normalize_token

    hypo = [normalize_token(w.text) for w in valid]
    _, ops = levenshtein_align(expected, hypo)
    aligned = 0
    for op in ops:
        if op.kind == "match":
            valid[op.hypo_index].token_index = tokens[op.expected_index].index
            aligned += 1
    coverage = _coverage(aligned, len(expected))
    status = _status_from_coverage(coverage, config.alignment.min_aligned_token_coverage)
    warnings.append(
        Warning(
            code="alignment_provided",
            message=(
                "Word boundaries were supplied as ground truth (synthetic fixture), "
                "not produced by forced alignment."
            ),
        )
    )
    return AlignmentResultModel(
        role=role,
        backend="provided",
        model="ground_truth_provided",
        language=language,
        status=status,
        words=valid,
        aligned_token_count=aligned,
        expected_token_count=len(expected),
        coverage=coverage,
        warnings=warnings,
        duration_seconds=duration,
    )


def whisperx_available() -> bool:
    try:
        import whisperx  # noqa: F401

        return True
    except Exception:
        return False


def align_whisperx(
    role: str,
    audio_path: str,
    tokens: List[Token],
    transcript_text: str,
    config: AnalysisConfig,
    duration: Optional[float],
    language: str,
) -> AlignmentResultModel:
    """Attempt WhisperX forced alignment within the configured timeout.

    Returns an explicit ``unavailable``/``timed_out``/``failed`` state on any
    error. Never fabricates timings.
    """
    start_t = time.time()
    budget = config.performance.alignment_timeout_seconds
    try:
        import whisperx  # type: ignore

        # Load the alignment model for the language and run alignment of the
        # supplied transcript to the audio. WhisperX align() needs a transcript
        # segment list; we provide the full transcript as a single segment.
        device = "cpu"
        model_a, metadata = whisperx.load_align_model(language_code=language.split("-")[0], device=device)
        if time.time() - start_t > budget:
            raise TimeoutError("alignment model load exceeded budget")
        # Decode with the project's own ffmpeg-free decoder at the analysis rate
        # rather than whisperx.load_audio() (which requires an ffmpeg binary).
        sr = config.audio.analysis_sample_rate_hz
        audio = _decode_audio_16k(audio_path, role, config)
        seg = [{"start": 0.0, "end": float(duration or len(audio) / float(sr)), "text": transcript_text}]
        result = whisperx.align(seg, model_a, metadata, audio, device, return_char_alignments=False)
        words_raw = []
        for segment in result.get("segments", []):
            for w in segment.get("words", []):
                if "start" in w and "end" in w:
                    words_raw.append(
                        WordTiming(token_index=-1, text=str(w.get("word", "")).strip(), start=float(w["start"]), end=float(w["end"]), score=w.get("score"))
                    )
        valid, warnings = _validate_words(words_raw, duration)
        from .transcript import normalize_token

        expected = [t.text for t in tokens]
        hypo = [normalize_token(w.text) for w in valid]
        _, ops = levenshtein_align(expected, hypo)
        aligned = 0
        for op in ops:
            if op.kind == "match":
                valid[op.hypo_index].token_index = tokens[op.expected_index].index
                aligned += 1
        coverage = _coverage(aligned, len(expected))
        status = _status_from_coverage(coverage, config.alignment.min_aligned_token_coverage)
        return AlignmentResultModel(
            role=role,
            backend="whisperx",
            model=getattr(metadata, "get", lambda *_: None)("model") if isinstance(metadata, dict) else "whisperx_align",
            language=language,
            status=status,
            words=valid,
            aligned_token_count=aligned,
            expected_token_count=len(expected),
            coverage=coverage,
            warnings=warnings,
            duration_seconds=duration,
        )
    except TimeoutError as exc:
        return AlignmentResultModel(
            role=role, backend="whisperx", language=language, status=AlignmentStatus.TIMED_OUT,
            expected_token_count=len(tokens), failure_reason=str(exc),
            warnings=[Warning(code="alignment_timeout", message=str(exc))],
            duration_seconds=duration,
        )
    except Exception as exc:  # import error, model download failure, runtime error
        return AlignmentResultModel(
            role=role, backend="whisperx", language=language, status=AlignmentStatus.UNAVAILABLE,
            expected_token_count=len(tokens), failure_reason=f"{type(exc).__name__}: {exc}",
            warnings=[Warning(code="alignment_unavailable", message=f"WhisperX alignment unavailable: {exc}")],
            duration_seconds=duration,
        )


def align(
    role: str,
    audio_path: str,
    tokens: List[Token],
    transcript_text: str,
    config: AnalysisConfig,
    duration: Optional[float],
    language: str,
    backend: str = "auto",
    provided_words: Optional[List[Dict]] = None,
) -> AlignmentResultModel:
    """Dispatch to the selected alignment backend.

    ``auto`` prefers caller-provided ground-truth timings, then WhisperX, then an
    explicit ``unavailable`` state. It never fabricates timestamps.
    """
    if backend == "provided" or (backend == "auto" and provided_words):
        if not provided_words:
            return AlignmentResultModel(
                role=role, backend="provided", language=language, status=AlignmentStatus.UNAVAILABLE,
                expected_token_count=len(tokens), failure_reason="no provided_words supplied",
                warnings=[Warning(code="alignment_unavailable", message="No provided word boundaries.")],
                duration_seconds=duration,
            )
        return align_provided(role, tokens, provided_words, config, duration, language)

    if backend == "whisperx" or (backend == "auto" and whisperx_available()):
        return align_whisperx(role, audio_path, tokens, transcript_text, config, duration, language)

    # No usable backend.
    return AlignmentResultModel(
        role=role, backend="unavailable", language=language, status=AlignmentStatus.UNAVAILABLE,
        expected_token_count=len(tokens),
        failure_reason="No alignment backend available (WhisperX not installed and no provided words).",
        warnings=[Warning(
            code="alignment_unavailable",
            message=("Word alignment is unavailable for this recording. Time-grounded "
                     "comparisons cannot be shown for unmapped regions."),
        )],
        duration_seconds=duration,
    )
