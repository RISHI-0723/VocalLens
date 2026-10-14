"""Integration tests for analyze_pair (ARCHITECTURE §11 integration)."""
import numpy as np
import pytest
import soundfile as sf

from vocallens.schemas import AnalysisRequest, AnalysisStatus
from vocallens.synthesis import SR, generate_variant
from vocallens.transcript import normalize_transcript

PASSAGE = "The morning light moved across the quiet room"


def _write_variant(tmp_path, variant, name):
    words = [t.original for t in normalize_transcript(PASSAGE)[1]]
    rec = generate_variant(words, variant, seed=42)
    path = tmp_path / f"{name}.wav"
    sf.write(str(path), rec.samples, SR, subtype="PCM_16")
    return str(path), rec.word_timings


def _request(tmp_path, variant, **kw):
    ref_path, ref_w = _write_variant(tmp_path, "reference", "ref")
    par_path, par_w = _write_variant(tmp_path, variant, "par")
    return AnalysisRequest(
        reference_audio=ref_path, participant_audio=par_path, transcript=PASSAGE,
        sample_id=variant, alignment_backend="provided",
        reference_provided_words=ref_w, participant_provided_words=par_w, **kw)


def test_complete_pair_detects_pace(tmp_path, analysis_config, scoring_config):
    from vocallens.pipeline import analyze_pair

    r = analyze_pair(_request(tmp_path, "pace_fast"), analysis_config, scoring_config)
    assert r.status == AnalysisStatus.COMPLETE
    assert any(d.family.value == "pace" for d in r.detections)
    # Every detection is temporally grounded and traces to a rule + values.
    for d in r.detections:
        assert d.participant_end > d.participant_start
        assert d.threshold > 0
        assert d.explanation and str(d.participant_value) in d.explanation


def test_long_pause_detects_pause(tmp_path, analysis_config, scoring_config):
    from vocallens.pipeline import analyze_pair

    r = analyze_pair(_request(tmp_path, "long_pause"), analysis_config, scoring_config)
    assert any(d.family.value == "pause" for d in r.detections)


def test_self_comparison_no_detections(tmp_path, analysis_config, scoring_config):
    from vocallens.pipeline import analyze_pair

    r = analyze_pair(_request(tmp_path, "reference"), analysis_config, scoring_config)
    assert r.detections == []
    assert r.status == AnalysisStatus.COMPLETE


def test_empty_transcript_fails(tmp_path, analysis_config, scoring_config):
    from vocallens.pipeline import analyze_pair

    req = _request(tmp_path, "reference")
    req.transcript = "   "
    r = analyze_pair(req, analysis_config, scoring_config)
    assert r.status == AnalysisStatus.FAILED
    assert any(w.code == "empty_transcript" for w in r.warnings)


def test_too_short_clip_fails(tmp_path, analysis_config, scoring_config):
    from vocallens.pipeline import analyze_pair

    short = tmp_path / "short.wav"
    sf.write(str(short), np.zeros(int(0.2 * SR), dtype=np.float32), SR)
    req = _request(tmp_path, "reference")
    req.participant_audio = str(short)
    r = analyze_pair(req, analysis_config, scoring_config)
    assert r.status == AnalysisStatus.FAILED
    assert r.failure_reason


def test_corrupt_audio_fails_honestly(tmp_path, analysis_config, scoring_config):
    from vocallens.pipeline import analyze_pair

    # A non-audio file with a .wav extension must fail decode with an honest
    # structured error, not a crash or fabricated result.
    bad = tmp_path / "corrupt.wav"
    bad.write_bytes(b"this is not a RIFF/WAVE file" * 50)
    req = _request(tmp_path, "reference")
    req.participant_audio = str(bad)
    r = analyze_pair(req, analysis_config, scoring_config)
    assert r.status == AnalysisStatus.FAILED
    assert any(w.code == "decode_failed" for w in r.warnings)
    assert r.detections == []


def test_alignment_unavailable_is_partial_no_fabrication(tmp_path, analysis_config, scoring_config):
    from vocallens.pipeline import analyze_pair

    req = _request(tmp_path, "pace_fast")
    req.alignment_backend = "unavailable"
    req.reference_provided_words = None
    req.participant_provided_words = None
    r = analyze_pair(req, analysis_config, scoring_config)
    assert r.status == AnalysisStatus.PARTIAL
    assert r.region_mapping.status == "unavailable"
    assert r.detections == []
    # Features are still computed even without alignment.
    assert r.participant_features


def test_different_durations_handled(tmp_path, analysis_config, scoring_config):
    from vocallens.pipeline import analyze_pair

    r = analyze_pair(_request(tmp_path, "pace_slow"), analysis_config, scoring_config)
    assert r.reference_audio.duration_seconds != r.participant_audio.duration_seconds
    assert r.status in (AnalysisStatus.COMPLETE, AnalysisStatus.PARTIAL)


def test_repeated_requests_are_deterministic(tmp_path, analysis_config, scoring_config):
    from vocallens.pipeline import analyze_pair

    req = _request(tmp_path, "long_pause")
    a = analyze_pair(req, analysis_config, scoring_config)
    b = analyze_pair(req, analysis_config, scoring_config)
    assert [d.detection_id for d in a.detections] == [d.detection_id for d in b.detections]
    assert a.scores.overall_score == b.scores.overall_score
