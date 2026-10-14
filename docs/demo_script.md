# VocalLens — Demo Script (React + FastAPI)

A 6–7 minute walkthrough of the working prototype, within the hackathon's
required **3–10 minute** window. Every step uses UI that exists in the React app
(`frontend/src/`) served by the FastAPI backend (`api/main.py`), and data that
ships in the repo. Numbers quoted are from the measured held-out evaluation
(`reports/evaluation/evaluation_test_latest.json`) and are deterministic across
runs.

> **Say this up front (honesty framing):** *"This runs on a **synthetic tonal
> pilot dataset**, clearly labeled in the app. It is feasibility evidence for the
> pipeline, not a claim about real human speakers. Where a measurement is missing
> or a flaw does not cross threshold, the app says so — it never fabricates."*

A Streamlit fallback (`app/streamlit_app.py`) renders the same analysis; this
script demonstrates the **primary React + FastAPI** front end.

---

## 0. Setup (before recording — not shown on camera)

Two terminals, from the repository root:

```bash
# Terminal 1 — backend
pip install -r requirements.txt -r requirements-api.txt
python scripts/build_dataset_manifest.py        # builds the 36-recording pilot
python scripts/validate_dataset.py              # dataset gate → PASS
python -m pytest -q                              # 80 tests pass
python scripts/run_evaluation.py --split test    # populates the Evaluation page
uvicorn api.main:app --port 8000                 # API on http://localhost:8000

# Terminal 2 — frontend
cd frontend && npm install && npm run dev        # UI on http://localhost:5173
```

Open `http://localhost:5173`. The top bar shows the brand **"VocalLens —
Contrastive Speech Analytics · Track C"** and nav links **Analysis · Evaluation
· About**. Confirm `http://localhost:8000/api/health` returns `status: ok`.

---

## 1. Frame the problem — ~0:00–0:30

> "VocalLens compares a participant's delivery against a reference recording of
> the *same words*, finds measurable differences, pins each to a time region, and
> explains it with the evidence behind it. It is a coaching/comparison tool — it
> reports deltas, it does not judge ability, confidence, or intent."

**On screen:** the **Analysis** page (the app redirects `/` → `/analysis`).

## 2. Dataset construction + limitations — ~0:30–1:30

Open the **About** page and talk through it; or narrate over the dataset card:

> "The dataset is 36 recordings — 6 passages × 6 variants: one reference plus
> five controlled variants (pace_fast, pace_slow, long_pause, monotone,
> energy_drop). Every variant shares the reference's exact transcript. Flaw
> intervals and word timings are ground truth from the generating transform, not
> inferred. Split is by passage with no leakage: train p01–p04, val p05, **held-out
> test p06**. It is **100% synthetic tonal fixtures** — CC0, no human speech — so
> it's feasibility evidence, not a claim about real speakers. The real-speaker
> baseline is the top outstanding gap, and we say so in the app and README."

## 3. Run an analysis on a synthetic pair — ~1:30–3:30

Back on **Analysis**. Input mode is **"Synthetic sample pair"** (the blue banner
reads *"DEMO: synthetic tonal fixtures with ground-truth alignment. Not natural
speech."*).

1. **Passage:** select **p06 (test)** — the held-out passage.
2. **Participant variant:** select **pace_fast — pace/…**.
3. Note the **Shared transcript** box is read-only (same text for both recordings).
4. Click **Run analysis** (button shows a spinner + "Analyzing…"; the
   `analysis_id` appears next to it when done).

Walk the result:
- **Summary cards:** prototype score ≈ **79**, status **complete**, alignment
  **ref/participant coverage 1.0** (the `provided` ground-truth backend). Call the
  score "a rubric score, labeled provisional — not a validated quality measure."
- **Candidate deviations:** the **pace** family fires. Click the card to select it.
- **Feature evidence** updates for the selection; the **Audio** panel exposes the
  reference and participant players on **separate clocks** (manual seek — the app
  does not claim auto-synced playback).

## 4. Temporal grounding, evidence, and grouping — ~3:30–5:00

Re-run with variant **long_pause** (same passage **p06**):
- A **pause** detection fires with its **participant time window**. Click it and
  read the evidence in the card: participant vs. reference value, the **delta**,
  the **rule id + threshold**, the **normalized exceedance R**, the **severity
  badge**, and the **evidence-quality Q** (with A/F/S/M components).
- Point out **two families grouped** (pause + pace): the inserted pause also
  perturbs local word rate — labeled **association, not causation**. Held-out best
  temporal IoU for the intended pause is **0.374**.

Then re-run **monotone** (p06) to show pitch grounding:
- A **pitch_variation** detection fires via the **whole-utterance** semitone-IQR
  rule. Participant semitone-IQR ≈ **0.03** vs reference ≈ **2.84**. Held-out
  pitch_variation **P/R/F1 = 1.0**, temporal **IoU 0.967**. The **Pitch (F0)**
  chart shows the flattened contour. Say: "structural detection rule, *not*
  threshold tuning on the test split."

## 5. Honesty + evaluation metrics (incl. a failure) — ~5:00–6:00

First, the honest non-detection. Re-run **energy_drop** (p06):
- **No energy_dynamics detection fires.** The app shows *"no candidate deviations
  crossed the configured thresholds"* and notes this **does not prove** the
  deliveries are identical; the **Energy (dBFS)** chart still shows the quieter
  second half. Reason: the within-recording `z_rel` energy metric is **by design
  invariant to global loudness** (avoids gain/mic-distance confounds), so a
  uniform amplitude drop barely moves it. "We did **not** tune thresholds on the
  held-out set to mask this."

Then open the **Evaluation** page:
- Yellow note: synthetic feasibility pilot, thresholds not tuned.
- **Per-family table:** pace F1 **0.80** (P 0.667 / R 1.0), pause **1.0**,
  pitch_variation **1.0**; **energy_dynamics recall 0.0**, precision/F1 shown as
  **N/A**, not a fabricated 0 (the page states this explicitly).
- **Runtime by stage** and **Per-case detail** (incl. `reference_self` scoring
  **100** with zero detections — the no-false-positive sanity check).

> "These are real measured numbers from `run_evaluation.py`, not mockups."

## 6. Exports + reproducibility + repo — ~6:00–7:00

- Back on **Analysis**, under **Export**, click **Download analysis JSON** and
  **Download detections CSV**. Open the JSON to show **schema version**, **config
  hashes**, **model/software versions**, **per-stage timings**, and full feature
  series — the same object the evaluation script and exporters consume.
- Stop the backend briefly to show the UI's honest **"Is the API running?"**
  connection error, then restart it to show recovery (optional, ~10 s).
- Close on repo organization: one engine (`src/vocallens/`, `analyze_pair`), thin
  FastAPI adapter, React UI, Streamlit fallback, validated dataset, 80 tests, and
  the technical report. Reiterate: synthetic pilot; real-speaker baseline and
  real-speech alignment accuracy are the disclosed next steps.

---

## Exact UI-interaction checklist (for the recording)

1. Load `http://localhost:5173` → lands on **Analysis**.
2. Confirm sample list populated (Passage dropdown has p01–p06).
3. Select **p06 (test)** + **pace_fast** → **Run analysis** → results render.
4. Click the **pace** detection card → Feature evidence + Audio update.
5. Switch variant to **long_pause** → **Run analysis** → show pause + grouped pace.
6. Switch variant to **monotone** → **Run analysis** → show pitch_variation + F0 chart.
7. Switch variant to **energy_drop** → **Run analysis** → show the honest no-detection state.
8. **Download analysis JSON** and **detections CSV**; open one file on camera.
9. Open **Evaluation** → per-family table + per-case detail.
10. Open **About** → methods, config hashes, limitations.
11. (Optional) kill/restart the backend to show the API-error + recovery states.

## Backup / Q&A pointers

- **"Is the transcript checked?"** No — forced alignment maps supplied words to
  audio; it does not verify correctness. Reference and participant are aligned
  independently.
- **"Why no WhisperX in the demo?"** It is an optional extra
  (`requirements-align.txt`) because it pulls a large stack (torch, etc.) — **not**
  a version conflict. It coexists with the dashboard and the model loads; the
  adapter decodes without ffmpeg. The demo uses the synthetic fixtures'
  ground-truth alignment for reliability. See `reports/alignment_feasibility.md`.
- **"Can I upload my own audio?"** Yes — the **Upload recordings** mode accepts
  wav/mp3/flac/ogg + a transcript (≤ 50 MB/file). Without WhisperX, alignment is
  marked **unavailable** and time-grounded comparisons are limited (shown
  honestly), not faked.
- **"Is the score meaningful?"** It is a provisional prototype rubric
  (`configs/scoring.yaml`), not a validated quality measure; thresholds are not
  tuned on held-out data.
