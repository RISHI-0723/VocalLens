"""Alignment adapter tests (ARCHITECTURE §8.3) — provided + unavailable paths."""
from vocallens.alignment import align, align_provided
from vocallens.schemas import AlignmentStatus
from vocallens.transcript import normalize_transcript


def _words(toks, dt=0.3):
    t = 0.0
    out = []
    for tk in toks:
        out.append({"text": tk.original, "start": t, "end": t + dt})
        t += dt
    return out


def test_provided_backend_full_coverage(analysis_config):
    orig, toks = normalize_transcript("one two three four")
    a = align("reference", "", toks, orig, analysis_config, 10, "en-US", "provided", _words(toks))
    assert a.backend == "provided"
    assert a.status == AlignmentStatus.COMPLETE
    assert a.coverage == 1.0
    assert any(w.code == "alignment_provided" for w in a.warnings)


def test_provided_partial_coverage(analysis_config):
    orig, toks = normalize_transcript("one two three four five")
    # Only two words provided -> coverage 0.4 < 0.8 -> partial.
    partial = [{"text": "one", "start": 0.0, "end": 0.3}, {"text": "two", "start": 0.3, "end": 0.6}]
    a = align("participant", "", toks, orig, analysis_config, 10, "en-US", "provided", partial)
    assert a.status == AlignmentStatus.PARTIAL
    assert a.coverage < analysis_config.alignment.min_aligned_token_coverage


def test_unavailable_backend_no_fabrication(analysis_config):
    orig, toks = normalize_transcript("hello world")
    a = align("reference", "", toks, orig, analysis_config, 2, "en-US", "unavailable")
    assert a.status == AlignmentStatus.UNAVAILABLE
    assert a.words == []  # no fabricated timestamps


def test_provided_without_words_is_unavailable(analysis_config):
    orig, toks = normalize_transcript("hello world")
    a = align("reference", "", toks, orig, analysis_config, 2, "en-US", "provided", None)
    assert a.status == AlignmentStatus.UNAVAILABLE


def test_invalid_timestamps_dropped(analysis_config):
    orig, toks = normalize_transcript("alpha beta")
    bad = [
        {"text": "alpha", "start": 0.0, "end": 0.3},
        {"text": "beta", "start": 0.6, "end": 0.4},  # start > end -> dropped
    ]
    a = align_provided("reference", toks, bad, analysis_config, 10, "en-US")
    assert a.aligned_token_count == 1
    assert any(w.code == "alignment_bad_interval" for w in a.warnings)
