"""VocalLens FastAPI backend.

A thin, typed HTTP layer over the existing Python engine. Every analysis is
produced by `vocallens.pipeline.analyze_pair`; exports reuse
`vocallens.export.{to_json, to_detections_csv}`. Nothing scientific is
reimplemented here. Alignment stays optional: synthetic sample pairs use the
`provided` ground-truth backend; uploads default to `unavailable` so opening the
dashboard never triggers a model download.

Run:  uvicorn api.main:app --port 8000
"""
from __future__ import annotations

import csv as _csv
import json
import os
import sys
import tempfile
import uuid
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from vocallens import __version__ as ENGINE_VERSION  # noqa: E402
from vocallens.config import load_analysis_config, load_scoring_config  # noqa: E402
from vocallens.export import to_detections_csv, to_json  # noqa: E402
from vocallens.pipeline import analyze_pair  # noqa: E402
from vocallens.schemas import AnalysisRequest, AnalysisResult  # noqa: E402

DATA = REPO_ROOT / "data"
ANN = DATA / "annotations"
EVAL_DIR = REPO_ROOT / "reports" / "evaluation"
MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # documented 50 MB cap (matches analysis.yaml)
ALLOWED_AUDIO_SUFFIXES = {".wav", ".mp3", ".flac", ".ogg"}

app = FastAPI(title="VocalLens API", version=ENGINE_VERSION)

# CORS. In dev this defaults to the Vite dev server and a couple of common
# local ports (never "*"). In production set VOCALLENS_CORS_ORIGINS to the exact
# deployed frontend origin(s), comma-separated. Optionally set
# VOCALLENS_CORS_ORIGIN_REGEX to also allow that project's Vercel *preview*
# deployments (e.g. "https://.*\\.vercel\\.app").
_cors = os.environ.get(
    "VOCALLENS_CORS_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173,http://localhost:3000",
).split(",")
_cors_regex = os.environ.get("VOCALLENS_CORS_ORIGIN_REGEX", "").strip() or None
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip().rstrip("/") for o in _cors if o.strip()],
    allow_origin_regex=_cors_regex,
    allow_methods=["GET", "POST"], allow_headers=["*"],
)

# Bounded in-memory cache of recent results (for export endpoints). No DB.
_RESULTS: "OrderedDict[str, AnalysisResult]" = OrderedDict()
_CACHE_MAX = 32


def _cache(result: AnalysisResult) -> str:
    aid = uuid.uuid4().hex[:12]
    _RESULTS[aid] = result
    while len(_RESULTS) > _CACHE_MAX:
        _RESULTS.popitem(last=False)
    return aid


def _manifest_rows() -> List[Dict[str, str]]:
    path = DATA / "manifest.csv"
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as fh:
        return list(_csv.DictReader(fh))


def _ann(recording_id: str) -> Dict[str, Any]:
    return json.loads((ANN / f"{recording_id}.json").read_text(encoding="utf-8"))


def _result_dict(result: AnalysisResult) -> Dict[str, Any]:
    """The engine's own validated JSON (safe floats/None), as a dict."""
    return json.loads(to_json(result))


# --------------------------------------------------------------------------- #
# Response models (thin wrappers; `result` carries the engine's own schema)
# --------------------------------------------------------------------------- #
class Health(BaseModel):
    status: str
    engine: str
    engine_version: str


class SampleVariant(BaseModel):
    variant: str
    recording_id: str
    role: str
    intended_flaw_family: str
    intended_severity: str


class SamplePassage(BaseModel):
    passage_id: str
    transcript: str
    reference_id: Optional[str]
    split: str
    variants: List[SampleVariant]


class AnalyzeResponse(BaseModel):
    analysis_id: str
    mode: str
    provenance: Dict[str, Any]
    result: Dict[str, Any]


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #
@app.get("/api/health", response_model=Health)
def health() -> Health:
    return Health(status="ok", engine="vocallens", engine_version=ENGINE_VERSION)


@app.get("/api/dataset/samples", response_model=List[SamplePassage])
def dataset_samples() -> List[SamplePassage]:
    rows = _manifest_rows()
    by_passage: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
    for r in rows:
        p = by_passage.setdefault(r["passage_id"], {"ref": None, "split": r["split"], "variants": []})
        p["variants"].append(SampleVariant(
            variant=r["variant"], recording_id=r["recording_id"], role=r["role"],
            intended_flaw_family=r["intended_flaw_family"], intended_severity=r["intended_severity"]))
        if r["variant"] == "reference":
            p["ref"] = r["recording_id"]
    out: List[SamplePassage] = []
    for pid, p in by_passage.items():
        transcript = ""
        if p["ref"]:
            try:
                transcript = _ann(p["ref"]).get("transcript", "")
            except Exception:
                transcript = ""
        out.append(SamplePassage(passage_id=pid, transcript=transcript, reference_id=p["ref"],
                                  split=p["split"], variants=p["variants"]))
    return out


@app.get("/api/dataset/audio/{recording_id}")
def dataset_audio(recording_id: str) -> FileResponse:
    # Serve a synthetic sample's audio, validated strictly against the manifest
    # (no arbitrary filesystem access via the path parameter).
    rows = {r["recording_id"]: r for r in _manifest_rows()}
    row = rows.get(recording_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Unknown recording_id.")
    path = (DATA / row["relative_path"]).resolve()
    samples_root = (DATA / "samples").resolve()
    if samples_root not in path.parents or not path.exists():
        raise HTTPException(status_code=404, detail="Audio not available.")
    return FileResponse(str(path), media_type="audio/wav", filename=f"{recording_id}.wav")


@app.get("/api/config")
def config() -> Dict[str, Any]:
    a = load_analysis_config()
    s = load_scoring_config()
    thresholds = {k: {"value": v.value, "unit": v.unit} for k, v in a.detection.thresholds.items()}
    dims = {name: {"weight": d.weight} for name, d in s.dimensions.items()}
    return {
        "analysis_config_hash": a.config_hash,
        "scoring_config_hash": s.config_hash,
        "language": a.language,
        "thresholds": thresholds,
        "scoring_dimensions": dims,
        "severity_bands": {
            "low_upper_ratio": a.detection.severity_low_upper_ratio,
            "moderate_upper_ratio": a.detection.severity_moderate_upper_ratio,
        },
        "overall_min_valid_dimensions": s.aggregation.overall_min_valid_dimensions,
    }


def _run_sample(passage_id: str, variant: str) -> AnalysisResult:
    rows = _manifest_rows()
    by_key = {(r["passage_id"], r["variant"]): r for r in rows}
    ref = by_key.get((passage_id, "reference"))
    par = by_key.get((passage_id, variant))
    if ref is None or par is None:
        raise HTTPException(status_code=404, detail="Unknown passage_id or variant.")
    ref_ann, par_ann = _ann(ref["recording_id"]), _ann(par["recording_id"])
    req = AnalysisRequest(
        reference_audio=str(DATA / ref["relative_path"]),
        participant_audio=str(DATA / par["relative_path"]),
        transcript=ref_ann["transcript"], sample_id=par["recording_id"],
        alignment_backend="provided",
        reference_provided_words=ref_ann["word_timings"],
        participant_provided_words=par_ann["word_timings"])
    return analyze_pair(req)


class SampleAnalyzeRequest(BaseModel):
    passage_id: str
    variant: str


@app.post("/api/analyze/sample", response_model=AnalyzeResponse)
def analyze_sample(body: SampleAnalyzeRequest) -> AnalyzeResponse:
    result = _run_sample(body.passage_id, body.variant)
    aid = _cache(result)
    rows = {(r["passage_id"], r["variant"]): r for r in _manifest_rows()}
    par = rows.get((body.passage_id, body.variant), {})
    prov = {
        "mode": "synthetic_sample", "passage_id": body.passage_id, "variant": body.variant,
        "recording_id": par.get("recording_id"), "is_synthetic": True,
        "intended_flaw_family": par.get("intended_flaw_family"),
        "intended_severity": par.get("intended_severity"),
        "license": par.get("license"), "note": "Synthetic tonal fixture with ground-truth alignment.",
    }
    return AnalyzeResponse(analysis_id=aid, mode="synthetic_sample", provenance=prov,
                           result=_result_dict(result))


@app.post("/api/analyze/upload", response_model=AnalyzeResponse)
def analyze_upload(
    reference: UploadFile = File(...),
    participant: UploadFile = File(...),
    transcript: str = Form(...),
    alignment_backend: str = Form("unavailable"),
) -> AnalyzeResponse:
    if alignment_backend not in {"unavailable", "whisperx"}:
        raise HTTPException(status_code=400, detail="alignment_backend must be 'unavailable' or 'whisperx'.")
    if not (transcript or "").strip():
        raise HTTPException(status_code=400, detail="A transcript is required to map words to audio.")
    tmp_paths: List[str] = []
    try:
        saved = {}
        for role, up in (("reference", reference), ("participant", participant)):
            suffix = Path(up.filename or "").suffix.lower()
            if suffix not in ALLOWED_AUDIO_SUFFIXES:
                raise HTTPException(status_code=400,
                                    detail=f"Unsupported audio type for {role}: {suffix or 'unknown'}.")
            data = up.file.read()
            if len(data) > MAX_UPLOAD_BYTES:
                raise HTTPException(status_code=413, detail="Uploaded file exceeds the 50 MB limit.")
            fd, p = tempfile.mkstemp(suffix=suffix)
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
            tmp_paths.append(p)
            saved[role] = p
        req = AnalysisRequest(
            reference_audio=saved["reference"], participant_audio=saved["participant"],
            transcript=transcript, sample_id="upload", alignment_backend=alignment_backend)
        result = analyze_pair(req)
        aid = _cache(result)
        prov = {"mode": "upload", "is_synthetic": False,
                "alignment_backend": alignment_backend,
                "note": "User-uploaded audio. Provenance/consent is the uploader's responsibility."}
        return AnalyzeResponse(analysis_id=aid, mode="upload", provenance=prov,
                               result=_result_dict(result))
    finally:
        for p in tmp_paths:
            try:
                os.remove(p)
            except OSError:
                pass


@app.get("/api/evaluation")
def evaluation(split: str = "test") -> Dict[str, Any]:
    if not EVAL_DIR.exists():
        return {"available": False, "reason": "No evaluation artifacts found. Run scripts/run_evaluation.py."}
    latest = EVAL_DIR / f"evaluation_{split}_latest.json"
    if not latest.exists():
        candidates = sorted(EVAL_DIR.glob(f"evaluation_{split}_*.json"))
        if not candidates:
            return {"available": False, "reason": f"No evaluation report for split '{split}'."}
        latest = candidates[-1]
    report = json.loads(latest.read_text(encoding="utf-8"))
    report["available"] = True
    report["source_file"] = latest.name
    return report


@app.get("/api/analysis/{analysis_id}/export.json")
def export_json(analysis_id: str) -> Response:
    result = _RESULTS.get(analysis_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Unknown or expired analysis_id.")
    return Response(content=to_json(result), media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="{result.sample_id}_analysis.json"'})


@app.get("/api/analysis/{analysis_id}/export.csv")
def export_csv(analysis_id: str) -> Response:
    result = _RESULTS.get(analysis_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Unknown or expired analysis_id.")
    return Response(content=to_detections_csv(result), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{result.sample_id}_detections.csv"'})


@app.exception_handler(Exception)
async def _unhandled(_request, exc):  # pragma: no cover - safety net
    # Never leak stack traces / internal paths to clients.
    return JSONResponse(status_code=500, content={"detail": "Internal analysis error."})
