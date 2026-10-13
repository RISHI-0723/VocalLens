"""Synthetic speech-like fixture generation (clearly labeled synthetic).

IMPORTANT HONESTY NOTE
----------------------
These are **synthetic, formant-free tonal fixtures**, not natural human speech.
They exist so the feature/detection/scoring pipeline can be exercised and
verified with *controlled perturbations whose word boundaries and flaw intervals
are known by construction* — exactly the controlled-engineering test the spec
calls for (ARCHITECTURE §10, CLAUDE.md §1.2 / §5F). Word timings produced here
are ground truth (not forced-alignment output) and are routed through the
alignment ``provided`` backend. They must never be presented as evidence of
performance on real speakers.

Each word is a short voiced tone (fundamental + harmonics) with a raised-cosine
amplitude envelope; inter-word gaps are near-silence. Controlled transforms
produce variants with intended flaws: altered pace, an inserted long pause,
reduced pitch variation (monotone), or an energy drop over a span.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

SR = 16000
_BASE_F0 = 130.0  # Hz, baseline voiced pitch
_BASE_WORD_DUR = 0.34  # seconds
_BASE_GAP = 0.10  # seconds between words
_BASE_AMP = 0.28  # linear peak amplitude (well below clipping)


@dataclass
class SynthWord:
    text: str
    duration: float
    f0: float
    amp: float
    gap_after: float


@dataclass
class SynthRecording:
    role: str
    variant: str
    samples: np.ndarray
    sr: int
    word_timings: List[Dict]  # {"text","start","end"} ground truth
    flaw_intervals: List[Dict]  # {"family","start","end","note"}
    transform_note: str


def _voiced_tone(duration: float, f0: float, amp: float, sr: int, rng: np.random.Generator) -> np.ndarray:
    n = max(1, int(round(duration * sr)))
    t = np.arange(n) / sr
    # Fundamental + a few harmonics for a voice-like spectrum.
    sig = np.zeros(n, dtype=np.float64)
    for k, rel in enumerate([1.0, 0.5, 0.33, 0.25], start=1):
        sig += rel * np.sin(2 * math.pi * f0 * k * t)
    sig /= np.max(np.abs(sig)) + 1e-9
    # Raised-cosine (Hann) envelope so word edges are smooth (voiced region).
    env = np.hanning(n) if n > 1 else np.ones(1)
    sig *= env
    sig *= amp
    # A touch of low-level noise so frames are not perfectly silent.
    sig += rng.normal(0, 1e-4, n)
    return sig.astype(np.float64)


def _gap(duration: float, sr: int, rng: np.random.Generator) -> np.ndarray:
    n = max(0, int(round(duration * sr)))
    # Near-silence noise floor (~ -70 dBFS) so pause detection has a floor.
    return rng.normal(0, 10 ** (-70 / 20), n).astype(np.float64)


def synth_recording(
    role: str, variant: str, words: List[SynthWord], transform_note: str, seed: int, sr: int = SR,
    flaw_intervals: Optional[List[Dict]] = None,
) -> SynthRecording:
    rng = np.random.default_rng(seed)
    segments: List[np.ndarray] = []
    timings: List[Dict] = []
    t = 0.0
    for w in words:
        tone = _voiced_tone(w.duration, w.f0, w.amp, sr, rng)
        start = t
        segments.append(tone)
        t += len(tone) / sr
        timings.append({"text": w.text, "start": round(start, 4), "end": round(t, 4)})
        gap = _gap(w.gap_after, sr, rng)
        segments.append(gap)
        t += len(gap) / sr
    samples = np.concatenate(segments).astype(np.float32) if segments else np.zeros(1, np.float32)
    return SynthRecording(
        role=role, variant=variant, samples=samples, sr=sr, word_timings=timings,
        flaw_intervals=flaw_intervals or [], transform_note=transform_note,
    )


def _base_words(words: List[str], seed: int, f0_spread: float = 14.0) -> List[SynthWord]:
    """Baseline reference words with natural per-word pitch variation."""
    rng = np.random.default_rng(seed)
    out: List[SynthWord] = []
    for i, w in enumerate(words):
        # Deterministic pitch contour: sinusoidal + jitter -> non-trivial IQR.
        f0 = _BASE_F0 + f0_spread * math.sin(i * 0.9) + rng.normal(0, 2.0)
        dur = _BASE_WORD_DUR + rng.normal(0, 0.02)
        out.append(SynthWord(w, max(0.12, dur), max(70.0, f0), _BASE_AMP, _BASE_GAP))
    return out


def generate_variant(passage_words: List[str], variant: str, seed: int) -> SynthRecording:
    """Generate one recording (reference or a controlled flawed variant)."""
    base = _base_words(passage_words, seed)
    note = ""
    flaws: List[Dict] = []

    if variant == "reference":
        return synth_recording("reference", variant, base, "baseline reference", seed)

    if variant == "pace_fast":
        factor = 0.6
        w = [SynthWord(x.text, x.duration * factor, x.f0, x.amp, x.gap_after * factor) for x in base]
        note = f"all word+gap durations scaled by {factor} (faster pace)"
        # Whole recording is the flaw region for pace.
        total = sum(x.duration + x.gap_after for x in w)
        flaws = [{"family": "pace", "start": 0.0, "end": round(total, 4), "note": "faster than reference"}]
        return synth_recording("participant", variant, w, note, seed, flaw_intervals=flaws)

    if variant == "pace_slow":
        factor = 1.55
        w = [SynthWord(x.text, x.duration * factor, x.f0, x.amp, x.gap_after * factor) for x in base]
        note = f"all word+gap durations scaled by {factor} (slower pace)"
        total = sum(x.duration + x.gap_after for x in w)
        flaws = [{"family": "pace", "start": 0.0, "end": round(total, 4), "note": "slower than reference"}]
        return synth_recording("participant", variant, w, note, seed, flaw_intervals=flaws)

    if variant == "long_pause":
        w = [SynthWord(x.text, x.duration, x.f0, x.amp, x.gap_after) for x in base]
        # Insert a long pause after the 2nd word (if present).
        idx = min(1, len(w) - 1)
        extra = 1.1
        w[idx] = SynthWord(w[idx].text, w[idx].duration, w[idx].f0, w[idx].amp, w[idx].gap_after + extra)
        # Compute the flaw interval start/end for the inserted pause.
        t = 0.0
        for j, x in enumerate(w):
            t += x.duration
            if j == idx:
                pause_start = t
                pause_end = t + x.gap_after
                flaws = [{"family": "pause", "start": round(pause_start, 4), "end": round(pause_end, 4),
                          "note": f"inserted {extra:.1f}s pause after word {idx}"}]
            t += x.gap_after
        note = f"inserted {extra}s pause after word index {idx}"
        return synth_recording("participant", variant, w, note, seed, flaw_intervals=flaws)

    if variant == "monotone":
        # Collapse pitch variation to near-constant F0 (low semitone IQR).
        w = [SynthWord(x.text, x.duration, _BASE_F0, x.amp, x.gap_after) for x in base]
        note = "pitch flattened to a near-constant F0 (monotone)"
        total = sum(x.duration + x.gap_after for x in w)
        flaws = [{"family": "pitch_variation", "start": 0.0, "end": round(total, 4), "note": "reduced pitch variation"}]
        return synth_recording("participant", variant, w, note, seed, flaw_intervals=flaws)

    if variant == "energy_drop":
        w = list(base)
        # Drop amplitude on the second half of the passage.
        half = len(w) // 2
        w = [
            SynthWord(x.text, x.duration, x.f0, x.amp * (0.3 if i >= half else 1.0), x.gap_after)
            for i, x in enumerate(base)
        ]
        # Flaw interval = span of the quieter words.
        t = 0.0
        span_start = None
        for i, x in enumerate(base):
            if i == half:
                span_start = t
            t += x.duration + x.gap_after
        flaws = [{"family": "energy_dynamics", "start": round(span_start or 0.0, 4), "end": round(t, 4),
                  "note": "amplitude reduced on second half (lower relative energy)"}]
        note = "amplitude x0.3 on second half of passage (energy drop)"
        return synth_recording("participant", variant, w, note, seed, flaw_intervals=flaws)

    raise ValueError(f"unknown variant: {variant}")


VARIANTS = ["reference", "pace_fast", "pace_slow", "long_pause", "monotone", "energy_drop"]
