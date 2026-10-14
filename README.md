# VocalLens

**Evidence-grounded contrastive speech-delivery analysis (prototype).**
IIT Mandi Multimodal AI Hackathon — Track C: Contrastive Speech Analytics &
Temporal Flaw Grounding.

VocalLens compares a **participant** recording with a **reference** recording of
the *same English text*, localizes measurable delivery differences in time, and
explains each one with the measured evidence behind it. Every reported deviation
traces to a feature, a time region, a baseline comparison, a configured rule, and
an explicit quality assessment.

> It is a comparison/coaching prototype — **not** a judge of ability, intent,
> confidence, or emotion. A difference may be intentional or stylistic.

## Track C problem

Given two recordings of the same passage, surface *where* and *how* the
participant's delivery deviates from the reference, grounded in time and backed by
measured features — without fabricating timestamps when alignment is unavailable,
and without overclaiming that a measured acoustic difference proves a rhetorical
flaw.

## Architecture

VocalLens is one Python analysis engine with two interchangeable front ends:

```
            ┌──────────────────────────┐        ┌──────────────────────────┐
            │  React + Vite + TS UI     │        │  Streamlit UI (fallback)  │
            │  frontend/  (port 5173)   │        │  app/streamlit_app.py     │
            └────────────┬─────────────┘        └────────────┬─────────────┘
                 HTTP /api (JSON)                   in-process import
                         │                                   │
            ┌────────────▼─────────────┐                     │
            │  FastAPI adapter          │                     │
            │  api/main.py (port 8000)  │                     │
            └────────────┬─────────────┘                     │
                         │          calls analyze_pair()      │
            ┌────────────▼─────────────────────────────────────▼─────────┐
            │  Python analysis engine — src/vocallens/                    │
            │  pipeline.analyze_pair(AnalysisRequest) -> AnalysisResult   │
            │  (audio_io · transcript · alignment · region_mapping ·      │
            │   features · detection · quality · explanations · scoring · │
            │   export)                                                   │
            └─────────────────────────────┬───────────────────────────────┘
                                           │
                        configs/ (analysis.yaml, scoring.yaml)
                        data/    (synthetic pilot dataset + annotations)
```

- **The engine owns all science.** Alignment, features, detection, severity,
  evidence quality, and scoring live in `src/vocallens/` and are produced by the
  single pipeline contract `analyze_pair`.
- **FastAPI is a thin adapter.** `api/main.py` validates requests, calls
  `analyze_pair`, and serializes with the engine's own `vocallens.export`
  functions. It reimplements no scientific logic.
- **The React frontend is presentation only.** It calls the API over HTTP and
  renders the result; the Streamlit app is an alternative front end that imports
  the engine in-process.

Data flow: UI selects a sample (or uploads two files + transcript) → FastAPI
builds an `AnalysisRequest` → `analyze_pair` returns a validated `AnalysisResult`
→ the UI renders summary, detections, feature charts, warnings, and export links.

## Prerequisites

- **Python 3.11** (developed and tested on 3.11.9). The core pipeline, tests,
  and dashboard need no secrets or network access.
- **Node.js ≥ 18** and npm (for the React frontend; Vite 5 requires Node 18+).

## Run it (two terminals)

### Terminal 1 — backend (FastAPI)

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate   |   macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt -r requirements-api.txt

# Build the synthetic pilot dataset the API serves (first run only):
python scripts/build_dataset_manifest.py

# Start the API on http://localhost:8000
uvicorn api.main:app --port 8000
```

Run `uvicorn` from the **repository root** (the module path is `api.main`). Check
it with `http://localhost:8000/api/health`.

### Terminal 2 — frontend (React + Vite)

```bash
cd frontend
npm install
npm run dev            # http://localhost:5173
```

### Frontend → backend configuration

The frontend reaches the backend through a **Vite dev proxy**: in development the
browser calls `/api/...` and `vite.config.ts` forwards those requests to
`http://localhost:8000`, so no CORS and no extra configuration are needed as long
as the backend runs on port 8000.

For a deployed/non-default backend, set `VITE_API_BASE` to the API origin (see
`frontend/.env.example`); the service layer in `frontend/src/services/api.ts`
prepends it to every request. Leave it empty to use the dev proxy.

### Streamlit fallback (no Node required)

```bash
pip install -r requirements.txt
python scripts/build_dataset_manifest.py
streamlit run app/streamlit_app.py
```

The Streamlit app imports `analyze_pair` directly and produces the same analysis
as the API path.

## API endpoints

All responses are JSON unless noted. Base URL `http://localhost:8000`.

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Liveness + engine version. |
| GET | `/api/dataset/samples` | List pilot passages, their shared transcript, reference id, split, and variants. |
| GET | `/api/dataset/audio/{recording_id}` | Serve a synthetic sample's WAV (validated against the manifest; no arbitrary paths). |
| GET | `/api/config` | Config hashes, language, detection thresholds, scoring dimensions, severity bands. |
| POST | `/api/analyze/sample` | Analyze a pilot `{passage_id, variant}` pair using ground-truth (`provided`) alignment. |
| POST | `/api/analyze/upload` | Analyze two uploaded recordings + shared transcript (multipart; alignment defaults to `unavailable`). |
| GET | `/api/evaluation?split=test` | Latest held-out evaluation report, or an honest unavailable state. |
| GET | `/api/analysis/{analysis_id}/export.json` | Download the versioned JSON for a cached analysis. |
| GET | `/api/analysis/{analysis_id}/export.csv` | Download the detections CSV for a cached analysis. |

Uploads are capped at **50 MB** per file, restricted to `.wav/.mp3/.flac/.ogg`,
written to OS temp files, and deleted in a `finally` block after analysis.
Results are held in a bounded in-memory cache (last 32) so the export endpoints
can serve them; there is no database.

## Using the app

1. Open `http://localhost:5173` → **Analysis** workspace.
2. **Synthetic sample pair:** pick a passage and a participant variant (the shared
   transcript is shown read-only), or switch to **Upload recordings** and provide
   reference + participant audio and the exact shared transcript.
3. Click **Run analysis**.
4. Inspect **summary cards**, **candidate deviations** (click one to highlight its
   time region and feature evidence), **feature charts**, and **warnings**. Each
   recording keeps its own time axis; timestamps come from the engine.
5. **Export** the analysis as JSON or detections CSV from the Export panel.
6. **Evaluation** and **About** pages show the held-out pilot metrics (or an honest
   empty state) and the project's scope and limitations.

## Dataset

- **Location:** ships **in this repository** under `data/` (36 recordings,
  `manifest.csv`, per-recording annotations, and the dataset card
  `data/README.md`); ≈ 4.4 MB, fully regenerable with
  `python scripts/build_dataset_manifest.py`.
- **Composition:** **100% synthetic** tonal fixtures — 6 passages × 6 variants
  (`reference`, `pace_fast`, `pace_slow`, `long_pause`, `monotone`,
  `energy_drop`), CC0-1.0, `provenance=vocallens.synthesis`,
  `consent=not_applicable`.
- **Flaw families:** pace, pause, pitch_variation, energy_dynamics.
- **Severity coverage:** per-variant intended flaw family and severity are in
  `manifest.csv` / `annotations/`; the held-out split is passage `p06`.
- **Splits (by passage, no leakage):** train = p01–p04, val = p05, test = p06.
- **Validate:** `python scripts/validate_dataset.py`.
- **Limitation:** synthetic only — no licensed/consented real-speaker audio, so it
  does **not** demonstrate generalization to natural speech. The Track C
  real-speaker baseline requirement is **not yet satisfied**; adding such
  baselines is the top outstanding dataset task. See `data/README.md`.
- **Public link status:** _pending_ — no Git remote is configured. Once published,
  the repository URL (with `data/`) is the dataset location; no separate public
  URL is claimed here.

## Tests, evaluation, and build commands

```bash
# Python engine + API tests (run from repo root):
python -m pytest -q

# Dataset validation (Gate A):
python scripts/validate_dataset.py

# Held-out evaluation — writes actual metrics to reports/evaluation/:
python scripts/run_evaluation.py --split test

# Frontend production build (type-check + bundle):
cd frontend && npm run build
```

## Status: implemented vs. tested vs. future

**Implemented and tested**
- Single-pipeline engine (`analyze_pair`) with features, detection, severity,
  evidence quality, and prototype scoring; versioned JSON/CSV export.
- FastAPI adapter with health, dataset, config, sample/upload analysis,
  evaluation, and export endpoints — covered by `tests/test_api.py`
  (fastapi `TestClient`, no live server needed).
- React + Vite + TypeScript frontend; production build (`npm run build`,
  `tsc --noEmit && vite build`) passes.
- Dataset validation and held-out evaluation produce real metrics on the
  synthetic pilot.
- Streamlit fallback UI over the same pipeline.

**Verified at the HTTP/build level, not yet in a browser click-through**
- End-to-end browser workflow (sample → analyze → export) — see
  "Known limitations" for the current verification status.

**Future work**
- Licensed/consented **real-speaker** baselines and natural-speech evaluation.
- Validated (tuned) scoring thresholds on held-out real data.
- Verified WhisperX real-speech **alignment accuracy** (the dependencies, model
  load, and adapter work; accuracy on real speech is unverified).

## Known limitations

- **Synthetic-only data.** Metrics are feasibility evidence on tonal fixtures, not
  proof of generalization to real speech. Scoring thresholds are untuned.
- **Alignment accuracy unverified on real speech.** WhisperX
  (`requirements-align.txt`) installs, the align model loads, and the adapter
  decodes, but real-speech alignment *accuracy* is **NOT VERIFIED** (no licensed
  real speech). Uploads default to the `unavailable` alignment state and never
  fabricate timestamps. See `reports/alignment_feasibility.md`.
- **Prototype scores**, not an objective measure of speaking quality.

## The one pipeline contract

```python
from vocallens.pipeline import analyze_pair
from vocallens.schemas import AnalysisRequest
result = analyze_pair(AnalysisRequest(reference_audio=..., participant_audio=..., transcript=...))
```

The React frontend (via FastAPI), the Streamlit app, the evaluation script, and
the exporters all call `analyze_pair`. No front end reimplements alignment,
detection, explanation, or scoring.

## Repository layout

```
api/           FastAPI adapter (main.py) over the engine
frontend/      React + Vite + TypeScript UI (src/, vite.config.ts, package.json)
app/           streamlit_app.py (fallback UI)
src/vocallens/ analysis engine (pipeline + modules)
configs/       analysis.yaml, scoring.yaml (validated on load)
data/          synthetic pilot dataset + manifest + annotations + dataset card
scripts/       build_dataset_manifest.py, validate_dataset.py, run_evaluation.py
tests/         pytest suite (engine + failure paths + test_api.py)
reports/       alignment_feasibility.md, evaluation/ (generated metrics)
docs/          technical_report.md, demo_script.md
```

## Documentation

- Architecture & contracts: [`ARCHITECTURE.md`](ARCHITECTURE.md) (API boundary: §15)
- Build/workflow discipline: [`CLAUDE.md`](CLAUDE.md)
- UX spec: [`DESIGN.md`](DESIGN.md)
- Technical report: [`docs/technical_report.md`](docs/technical_report.md)
- Demo script: [`docs/demo_script.md`](docs/demo_script.md)
- Dataset card: [`data/README.md`](data/README.md)
- Alignment feasibility: [`reports/alignment_feasibility.md`](reports/alignment_feasibility.md)
