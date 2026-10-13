"""Export schema tests (ARCHITECTURE §8.10)."""
import csv
import io

import soundfile as sf

from vocallens.export import CSV_COLUMNS, to_detections_csv, to_json
from vocallens.schemas import AnalysisRequest, AnalysisResult
from vocallens.synthesis import SR, generate_variant
from vocallens.transcript import normalize_transcript

PASSAGE = "The morning light moved across the quiet room"


def _run(tmp_path, analysis_config, scoring_config, variant):
    from vocallens.pipeline import analyze_pair

    words = [t.original for t in normalize_transcript(PASSAGE)[1]]
    ref = generate_variant(words, "reference", 7)
    par = generate_variant(words, variant, 7)
    rp, pp = tmp_path / "r.wav", tmp_path / "p.wav"
    sf.write(str(rp), ref.samples, SR, subtype="PCM_16")
    sf.write(str(pp), par.samples, SR, subtype="PCM_16")
    req = AnalysisRequest(
        reference_audio=str(rp), participant_audio=str(pp), transcript=PASSAGE,
        sample_id=variant, alignment_backend="provided",
        reference_provided_words=ref.word_timings, participant_provided_words=par.word_timings)
    return analyze_pair(req, analysis_config, scoring_config)


def test_json_roundtrip(tmp_path, analysis_config, scoring_config):
    r = _run(tmp_path, analysis_config, scoring_config, "long_pause")
    js = to_json(r)
    back = AnalysisResult.from_json(js)
    assert back.sample_id == r.sample_id
    assert len(back.detections) == len(r.detections)
    assert back.schema_version == r.schema_version


def test_csv_columns_and_rows(tmp_path, analysis_config, scoring_config):
    r = _run(tmp_path, analysis_config, scoring_config, "long_pause")
    csv_text = to_detections_csv(r)
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    assert list(rows[0].keys()) == CSV_COLUMNS if rows else True
    assert len(rows) == len(r.detections)
    for row in rows:
        assert row["schema_version"] == str(r.schema_version)
        assert row["severity"] in {"low", "moderate", "high"}


def test_unavailable_values_blank_not_zero(tmp_path, analysis_config, scoring_config):
    # Overall score may be unavailable; ensure JSON keeps null, not 0.
    r = _run(tmp_path, analysis_config, scoring_config, "reference")
    js = to_json(r)
    assert '"overall_score":null' in js.replace(" ", "") or r.scores.overall_score is not None
