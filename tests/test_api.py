"""FastAPI backend tests — thin HTTP layer over the existing engine.

These exercise the API boundary only; the scientific behavior is covered by the
engine tests. Requires fastapi + starlette TestClient (already installed).
"""
import io
import sys
import wave
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

fastapi_testclient = pytest.importorskip("fastapi.testclient")
from fastapi.testclient import TestClient  # noqa: E402

from api.main import app  # noqa: E402

client = TestClient(app)


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert r.json()["engine"] == "vocallens"


def test_dataset_samples_lists_passages():
    r = client.get("/api/dataset/samples")
    assert r.status_code == 200
    data = r.json()
    assert len(data) >= 1
    p = data[0]
    assert p["reference_id"] and p["transcript"]
    assert any(v["variant"] == "reference" for v in p["variants"])


def test_config_has_hashes_and_thresholds():
    r = client.get("/api/config")
    assert r.status_code == 200
    body = r.json()
    assert body["analysis_config_hash"] and body["scoring_config_hash"]
    assert "pitch_variation_iqr" in body["thresholds"]


def test_analyze_sample_monotone_detects_pitch():
    r = client.post("/api/analyze/sample", json={"passage_id": "p06", "variant": "monotone"})
    assert r.status_code == 200
    body = r.json()
    assert body["provenance"]["is_synthetic"] is True
    res = body["result"]
    assert res["status"] in {"complete", "partial"}
    assert any(d["family"] == "pitch_variation" for d in res["detections"])
    # Export round-trip for the cached analysis.
    aid = body["analysis_id"]
    j = client.get(f"/api/analysis/{aid}/export.json")
    assert j.status_code == 200 and j.json()["schema_version"]
    c = client.get(f"/api/analysis/{aid}/export.csv")
    assert c.status_code == 200 and "detection_id" in c.text.splitlines()[0]


def test_analyze_sample_reference_self_no_detections():
    r = client.post("/api/analyze/sample", json={"passage_id": "p06", "variant": "reference"})
    assert r.status_code == 200
    assert r.json()["result"]["detections"] == []


def test_analyze_unknown_sample_404():
    r = client.post("/api/analyze/sample", json={"passage_id": "nope", "variant": "ghost"})
    assert r.status_code == 404


def test_analyze_upload_missing_transcript_400():
    files = {"reference": ("ref.wav", b"RIFF....", "audio/wav"),
             "participant": ("par.wav", b"RIFF....", "audio/wav")}
    r = client.post("/api/analyze/upload", files=files, data={"transcript": "  "})
    assert r.status_code == 400


def _wav_bytes(seconds=2.0, sr=16000):
    t = np.arange(int(seconds * sr)) / sr
    y = (0.2 * np.sin(2 * np.pi * 150 * t)).astype(np.float32)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes((y * 32767).astype("<i2").tobytes())
    return buf.getvalue()


def test_analyze_upload_corrupt_audio_fails_honestly():
    files = {"reference": ("ref.wav", _wav_bytes(), "audio/wav"),
             "participant": ("par.wav", b"not a wav file" * 20, "audio/wav")}
    r = client.post("/api/analyze/upload", files=files,
                    data={"transcript": "hello world", "alignment_backend": "unavailable"})
    assert r.status_code == 200  # engine returns a structured failed result, not an HTTP crash
    res = r.json()["result"]
    assert res["status"] == "failed"
    assert any(w["code"] == "decode_failed" for w in res["warnings"])


def test_analyze_upload_unsupported_type_400():
    files = {"reference": ("ref.txt", b"x", "text/plain"),
             "participant": ("par.wav", _wav_bytes(), "audio/wav")}
    r = client.post("/api/analyze/upload", files=files, data={"transcript": "hello world"})
    assert r.status_code == 400


def test_evaluation_endpoint():
    r = client.get("/api/evaluation?split=test")
    assert r.status_code == 200
    body = r.json()
    # Either real artifacts are present, or an honest unavailable state.
    assert "available" in body
    if body["available"]:
        assert "per_family" in body and body["num_cases"] >= 1


def test_export_unknown_id_404():
    assert client.get("/api/analysis/deadbeef/export.json").status_code == 404


def test_dataset_audio_served_and_validated():
    # A real sample recording is served as audio/wav.
    samples = client.get("/api/dataset/samples").json()
    rid = samples[0]["reference_id"]
    r = client.get(f"/api/dataset/audio/{rid}")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("audio/")
    # Unknown / path-traversal-style ids are rejected, not served.
    assert client.get("/api/dataset/audio/not_a_real_id").status_code == 404
    assert client.get("/api/dataset/audio/..%2f..%2fsecret").status_code in (404, 400)
