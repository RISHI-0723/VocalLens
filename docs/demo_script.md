# VocalLens — Demo Script

A ~5-minute walkthrough of the working prototype. Every step below uses features
that exist in `app/streamlit_app.py` and data that ships in the repo. Numbers
quoted are from the measured held-out evaluation
(`reports/evaluation/evaluation_test_latest.json`).

> Honesty framing to say out loud up front: *"This runs on a **synthetic tonal
> pilot dataset**, clearly labeled in the app. It is feasibility evidence for the
> pipeline, not a claim about real human speakers."*

---

## 0. Setup (before the demo)

```bash
pip install -r requirements.txt
python scripts/build_dataset_manifest.py      # builds the 36-recording pilot
python scripts/validate_dataset.py            # dataset gate
python -m pytest -q                           # 63 tests
python scripts/run_evaluation.py --split test # populates the Evaluation page
streamlit run app/streamlit_app.py            # launches the dashboard
```

The app opens with a sidebar: **Analyze · Evaluation · About**.

---

## 1. Frame the problem (~30s)

> "VocalLens compares a participant's delivery against a reference recording of
> the *same words*, finds measurable differences, pins them to a point in time,
> and explains each one with the evidence behind it. It is a coaching tool — it
> reports deltas, it does not judge ability, confidence, or intent."

Point to the sidebar caption: **"Evidence first; score second."**

## 2. Run an analysis — a pace flaw (~90s)

On the **Analyze** page:
1. Keep input source on **"Synthetic sample pair (ground-truth alignment —
   DEMO)."** Note the on-screen DEMO-MODE banner that says these are synthetic
   fixtures, not natural speech.
2. Passage: **p06** ("*Numbers alone rarely tell the whole story.*").
3. Participant variant: **pace_fast**.
4. Click **Analyze recordings** and let the staged progress run
   (validating → aligning ref → aligning participant → features → regions →
   evidence & scores).

Talk through the results row:
- **Prototype score ≈ 79** for this case — "a rubric score, flagged in the UI as
  provisional, not a validated measure."
- **Alignment: Ref complete / Part complete** (coverage 1.0 via the `provided`
  ground-truth backend).
- **Candidate flags:** the pace family fires. Open the detection card and show
  the evidence: participant vs. reference word-rate values, the delta, the
  **rule id + threshold**, the **normalized exceedance R**, the **severity
  badge**, and the **evidence-quality** line (`Q` with its A/F/S/M components).
- Read the plain-language explanation and the **⚠️ caveat** ("a difference may be
  intentional or stylistic").

> Key line: *"Nothing here is a black box — every flag names its feature, its
> time window, its baseline, its rule, and how well-grounded the measurement is."*

## 3. Temporal grounding + grouping — the pause case (~60s)

Re-run with variant **long_pause** (same passage p06):
- Point out the detection's **participant time window** and the note to inspect
  the audio near that timestamp (manual seek — the app does **not** claim
  auto-synced playback).
- Show that **two families** appear grouped under **"Related observations"**: the
  inserted pause also perturbs local pace. The UI labels this *association, not
  causation*. In the evaluation, this case has best temporal IoU **0.374** for
  the intended pause.

## 4. Feature evidence + separate clocks (~30s)

Scroll to **Feature evidence**:
- Toggle between **Energy (RMS dBFS)** and **Pitch (F0 Hz)**.
- Note the caption: reference and participant are drawn on **separate clocks**
  and are **not time-synchronized** — a deliberate correctness choice.
- Show the scalar comparison table; where a measurement is missing it reads
  **"unavailable,"** never 0.

## 5. Honesty about what did *not* fire (~45s)

This is the most credible part of the demo — show it deliberately.

Re-run with variant **monotone** (reduced pitch variation):
- At current thresholds this does **not** cross the detection threshold on the
  synthetic pilot (held-out recall 0.0 for pitch_variation / energy_dynamics).
- The app does **not** fabricate a flag: it shows *"No candidate deviations
  crossed the configured thresholds"* and notes this **does not prove** the
  deliveries are identical. The pitch feature chart still shows the flattened F0.

> "We report this openly. Pitch and energy detection are under-sensitive on these
> synthetic cases, and we did **not** tune thresholds on the held-out set to hide
> it."

## 6. Exports (~20s)

Under **Export**, download the **analysis JSON** and **detections CSV**. Open the
JSON to show schema version, config hashes, model/software versions, per-stage
timings, and full feature series — the same object the evaluation script and
exporters consume.

## 7. Evaluation page — real metrics (~45s)

Switch to **Evaluation**:
- Point to the yellow note: synthetic feasibility pilot, thresholds not tuned.
- **Per-family table:** pace F1 **0.80** (P 0.667 / R 1.0), pause F1 **1.0**,
  pitch_variation and energy_dynamics recall **0.0**.
- **Runtime by stage:** total mean **1.30 s** / max **6.09 s** per pair; feature
  extraction dominates; alignment is near-free with the provided backend.
- Expand **Per-case detail** to show IoU and per-case scores, including
  `reference_self` scoring **100** with zero detections (the no-false-positive
  sanity check).

> "These are real measured numbers from `run_evaluation.py`, not mockups."

## 8. About / reproducibility (~20s)

Open **About**: methods summary, config hashes, dataset card pointer, known
limitations, and the exact setup commands. Close on the limitations:

> "Synthetic pilot; WhisperX real-speech alignment is BLOCKED on data and a
> dependency conflict with the dashboard; scores are provisional. The next step
> is consented human recordings and a separate alignment environment."

---

## Backup / Q&A pointers

- **"Is the transcript checked?"** No — forced alignment maps supplied words to
  audio; it does not verify correctness. Reference and participant are aligned
  independently.
- **"Why no WhisperX in the demo?"** WhisperX needs `protobuf>=7`, which
  conflicts with Streamlit's `protobuf<7`; it installs from
  `requirements-align.txt` in a separate environment. See
  `reports/alignment_feasibility.md`.
- **"Can I upload my own audio?"** Yes — the second input mode accepts
  wav/mp3/flac/ogg + a transcript. Without WhisperX, alignment is marked
  unavailable and time-grounded comparisons are limited (shown honestly), not
  faked.
- **"Is the score meaningful?"** It is a provisional prototype rubric
  (`configs/scoring.yaml`), not a validated quality measure; thresholds are not
  tuned on held-out data.
