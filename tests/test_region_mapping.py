"""Region-mapping and mismatch-ratio tests (ARCHITECTURE §8.4)."""
import pytest

from vocallens.alignment import align
from vocallens.region_mapping import levenshtein_align, map_regions
from vocallens.schemas import AlignmentStatus
from vocallens.transcript import normalize_transcript


def _provided(toks, dt, start=0.0):
    t = start
    out = []
    for tk in toks:
        out.append({"text": tk.original, "start": t, "end": t + dt})
        t += dt
    return out


def test_levenshtein_identical():
    dist, ops = levenshtein_align(["a", "b", "c"], ["a", "b", "c"])
    assert dist == 0
    assert all(o.kind == "match" for o in ops)


def test_levenshtein_insertion_deletion():
    dist, ops = levenshtein_align(["a", "b", "c"], ["a", "x", "b", "c"])
    assert dist == 1
    assert any(o.kind == "insert" for o in ops)


def test_mapping_complete_when_sequences_match(analysis_config):
    orig, toks = normalize_transcript("the quick brown fox jumps over")
    ref = align("reference", "", toks, orig, analysis_config, 10, "en-US", "provided", _provided(toks, 0.3))
    par = align("participant", "", toks, orig, analysis_config, 12, "en-US", "provided", _provided(toks, 0.4))
    rm = map_regions(toks, orig, ref, par, analysis_config)
    assert rm.status == "complete"
    assert rm.mismatch_ratio == 0.0
    assert all(p.eligible for p in rm.phrases)


def test_mapping_unavailable_without_alignment(analysis_config):
    orig, toks = normalize_transcript("hello world")
    ref = align("reference", "", toks, orig, analysis_config, 2, "en-US", "unavailable")
    par = align("participant", "", toks, orig, analysis_config, 2, "en-US", "unavailable")
    rm = map_regions(toks, orig, ref, par, analysis_config)
    assert rm.status == "unavailable"


def test_mapping_partial_above_mismatch_threshold(analysis_config):
    orig, toks = normalize_transcript("one two three four five")
    # Participant alignment drops/!changes several words -> high mismatch.
    ref = align("reference", "", toks, orig, analysis_config, 5, "en-US", "provided", _provided(toks, 0.3))
    bad = [{"text": w, "start": i * 0.3, "end": i * 0.3 + 0.3} for i, w in enumerate(["aaa", "bbb", "ccc", "four", "five"])]
    par = align("participant", "", toks, orig, analysis_config, 5, "en-US", "provided", bad)
    rm = map_regions(toks, orig, ref, par, analysis_config)
    assert rm.mismatch_ratio > analysis_config.alignment.max_transcript_mismatch_ratio
    assert rm.status == "partial"


def test_phrase_segmentation_splits_sentences(analysis_config):
    orig, toks = normalize_transcript("First sentence here. Second sentence now.")
    ref = align("reference", "", toks, orig, analysis_config, 10, "en-US", "provided", _provided(toks, 0.3))
    par = align("participant", "", toks, orig, analysis_config, 10, "en-US", "provided", _provided(toks, 0.3))
    rm = map_regions(toks, orig, ref, par, analysis_config)
    # At least two phrases from the two sentences.
    assert len(rm.phrases) >= 2
