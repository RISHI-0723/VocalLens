"""Comparable text-region mapping (ARCHITECTURE.md §8.4).

Maps the shared transcript onto each recording's independent alignment, computes
a mismatch ratio with safeguards, and builds phrase windows that carry a time
interval on each recording's own clock. Never compares identical absolute
timestamps by default; comparisons happen over mapped phrase regions.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from .config import AnalysisConfig
from .schemas import (
    AlignmentResultModel,
    AlignmentStatus,
    MappedPhrase,
    RegionMappingModel,
    Token,
    Warning,
    WordTiming,
)

_SENTENCE_END = re.compile(r"[.!?;]")


@dataclass
class _Op:
    kind: str  # "match", "sub", "delete" (expected only), "insert" (hypo only)
    expected_index: Optional[int]
    hypo_index: Optional[int]


def levenshtein_align(expected: List[str], hypo: List[str]) -> Tuple[int, List[_Op]]:
    """Token-level edit distance with backtrace.

    Returns (edit_distance, ops). ``delete`` = expected token missing from hypo;
    ``insert`` = hypo token not in expected; ``sub`` counts as a mismatch.
    """
    n, m = len(expected), len(hypo)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        dp[i][0] = i
    for j in range(1, m + 1):
        dp[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            cost = 0 if expected[i - 1] == hypo[j - 1] else 1
            dp[i][j] = min(
                dp[i - 1][j] + 1,  # delete expected
                dp[i][j - 1] + 1,  # insert hypo
                dp[i - 1][j - 1] + cost,  # match/sub
            )
    # Backtrace
    ops: List[_Op] = []
    i, j = n, m
    while i > 0 or j > 0:
        if i > 0 and j > 0 and dp[i][j] == dp[i - 1][j - 1] + (0 if expected[i - 1] == hypo[j - 1] else 1):
            kind = "match" if expected[i - 1] == hypo[j - 1] else "sub"
            ops.append(_Op(kind, i - 1, j - 1))
            i -= 1
            j -= 1
        elif i > 0 and dp[i][j] == dp[i - 1][j] + 1:
            ops.append(_Op("delete", i - 1, None))
            i -= 1
        else:
            ops.append(_Op("insert", None, j - 1))
            j -= 1
    ops.reverse()
    return dp[n][m], ops


def _segment_phrases(
    transcript_text: str, tokens: List[Token], max_len: int, min_len: int
) -> List[List[int]]:
    """Group transcript token indices into phrase windows using punctuation.

    Sentence-ending punctuation in the original text marks boundaries; long
    segments are split into windows of at most ``max_len`` tokens.
    """
    # Boundary char positions (end of a sentence) in the original text.
    boundaries = [m.end() for m in _SENTENCE_END.finditer(transcript_text)]
    segments: List[List[int]] = []
    current: List[int] = []
    b_idx = 0
    for tok in tokens:
        # If this token starts past the next sentence boundary, the previous
        # segment ends before it. Advance past any boundaries it clears.
        while (
            b_idx < len(boundaries)
            and tok.char_start is not None
            and tok.char_start >= boundaries[b_idx]
        ):
            if current:
                segments.append(current)
                current = []
            b_idx += 1
        current.append(tok.index)
    if current:
        segments.append(current)

    # Split overlong segments; merge tiny tail segments into the previous one.
    windows: List[List[int]] = []
    for seg in segments:
        for k in range(0, len(seg), max_len):
            windows.append(seg[k : k + max_len])
    merged: List[List[int]] = []
    for w in windows:
        if merged and len(w) < min_len:
            merged[-1].extend(w)
        else:
            merged.append(w)
    return [w for w in merged if w]


def _token_timing_map(
    expected_tokens: List[str], alignment: AlignmentResultModel
) -> Tuple[Dict[int, WordTiming], int]:
    """Map expected transcript token indices -> aligned WordTiming for one recording.

    Returns (mapping, edit_distance). The aligner's word list is matched against
    the expected transcript tokens via Levenshtein so dropped/extra aligner words
    are handled without fabricating timings.
    """
    # Normalize the aligner token sequence with the same rules as the transcript
    # (ARCHITECTURE §8.4 step 1) before edit-distance comparison.
    from .transcript import normalize_token

    hypo = [normalize_token(w.text) for w in alignment.words]
    if not hypo:
        return {}, len(expected_tokens)
    dist, ops = levenshtein_align(expected_tokens, hypo)
    mapping: Dict[int, WordTiming] = {}
    for op in ops:
        if op.kind == "match":
            mapping[op.expected_index] = alignment.words[op.hypo_index]
    return mapping, dist


def map_regions(
    tokens: List[Token],
    transcript_text: str,
    reference_alignment: AlignmentResultModel,
    participant_alignment: AlignmentResultModel,
    config: AnalysisConfig,
    max_phrase_len: int = 5,
    min_phrase_len: int = 2,
) -> RegionMappingModel:
    """Build the cross-recording region mapping with mismatch safeguards."""
    expected = [t.text for t in tokens]
    n_expected = len(expected)
    warnings: List[Warning] = []

    if n_expected == 0:
        return RegionMappingModel(status="unavailable", warnings=[
            Warning(code="empty_transcript", message="No transcript tokens to map.")
        ])

    # If either recording has no alignment, mapping is unavailable.
    aligners_ok = []
    for algn in (reference_alignment, participant_alignment):
        aligners_ok.append(
            algn is not None
            and algn.status in (AlignmentStatus.COMPLETE, AlignmentStatus.PARTIAL)
            and len(algn.words) > 0
        )
    if not all(aligners_ok):
        return RegionMappingModel(
            status="unavailable",
            warnings=[
                Warning(
                    code="alignment_unavailable",
                    message="Region mapping requires word alignment for both recordings.",
                )
            ],
        )

    ref_map, ref_dist = _token_timing_map(expected, reference_alignment)
    par_map, par_dist = _token_timing_map(expected, participant_alignment)

    # Mismatch ratio: use the worse (larger) of the two recordings' edit distances
    # against the shared transcript. edit_distance / larger normalized token count.
    ref_ratio = ref_dist / max(n_expected, len(reference_alignment.words))
    par_ratio = par_dist / max(n_expected, len(participant_alignment.words))
    mismatch_ratio = max(ref_ratio, par_ratio)
    edit_distance = max(ref_dist, par_dist)

    status = "complete"
    if mismatch_ratio > config.alignment.max_transcript_mismatch_ratio:
        status = "partial"
        warnings.append(
            Warning(
                code="transcript_mismatch_high",
                message=(
                    f"Transcript mismatch ratio {mismatch_ratio:.2f} exceeds "
                    f"{config.alignment.max_transcript_mismatch_ratio:.2f}; regions that "
                    "cannot be mapped confidently are not compared."
                ),
            )
        )

    min_cov = config.alignment.min_aligned_token_coverage
    phrase_windows = _segment_phrases(transcript_text, tokens, max_phrase_len, min_phrase_len)

    phrases: List[MappedPhrase] = []
    matched_total = 0
    for p_i, idxs in enumerate(phrase_windows):
        ref_hits = [i for i in idxs if i in ref_map]
        par_hits = [i for i in idxs if i in par_map]
        ref_frac = len(ref_hits) / len(idxs)
        par_frac = len(par_hits) / len(idxs)
        matched_fraction = min(ref_frac, par_frac)
        matched_total += sum(1 for i in idxs if i in ref_map and i in par_map)
        eligible = (ref_frac >= min_cov and par_frac >= min_cov) and status != "unavailable"

        ref_start = ref_end = par_start = par_end = None
        if ref_hits:
            ref_start = min(ref_map[i].start for i in ref_hits)
            ref_end = max(ref_map[i].end for i in ref_hits)
        if par_hits:
            par_start = min(par_map[i].start for i in par_hits)
            par_end = max(par_map[i].end for i in par_hits)

        phrase_text = " ".join(tokens[i].original for i in idxs)
        phrases.append(
            MappedPhrase(
                phrase_id=f"phrase_{p_i:02d}",
                token_indices=idxs,
                text=phrase_text,
                reference_start=ref_start,
                reference_end=ref_end,
                participant_start=par_start,
                participant_end=par_end,
                matched_fraction=round(matched_fraction, 4),
                eligible=eligible,
            )
        )

    eligible_count = sum(1 for p in phrases if p.eligible)
    if eligible_count == 0:
        warnings.append(
            Warning(
                code="no_eligible_phrases",
                message="No phrase met the configured matched-and-aligned coverage for comparison.",
            )
        )

    return RegionMappingModel(
        status=status,
        mismatch_ratio=round(mismatch_ratio, 4),
        edit_distance=edit_distance,
        matched_tokens=matched_total,
        missing_tokens=n_expected - len(ref_map),
        inserted_tokens=max(len(reference_alignment.words) - len(ref_map), 0),
        unmapped_tokens=n_expected - matched_total,
        phrases=phrases,
        warnings=warnings,
    )
