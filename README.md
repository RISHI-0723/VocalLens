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

## Quick start

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate   |   macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt

python scripts/build_dataset_manifest.py   # build the synthetic pilot dataset
python scripts/validate_dataset.py         # Gate A: dataset validation
python -m pytest -q                        # Gate B: engine tests
python scripts/run_evaluation.py --split test   # held-out evaluation (real metrics)
streamlit run app/streamlit_app.py         # Gate C: dashboard
```

Python **3.11** is the supported version. No secrets or network access are
required for the core pipeline, tests, or dashboard.

## What it does

- **Audio ingestion** — decode to 16 kHz mono analysis copy, record sample rate,
  channels, peak, clipping; reject corrupt/out-of-limit files (no loudness
  normalization before energy analysis).
- **Alignment** — independent forced alignment per recording. WhisperX is the
  optional real aligner (`requirements-align.txt`); synthetic fixtures use
  ground-truth word boundaries labeled `provided`. Unavailable alignment yields
  an explicit state — **timestamps are never fabricated**.
- **Region mapping** — Levenshtein-based transcript↔audio mapping with a mismatch
  safeguard (partial above 0.20) and phrase windows compared on each recording's
  own clock.
- **Features** — word/syllable rate, pauses, pitch variability (semitone IQR),
  within-recording relative energy (dBFS), MFCC diagnostics; with signal-quality
  and validity flags. Missing values stay unavailable, never zero.
- **Detection** — pace / pause / pitch-variation / energy-dynamics candidate
  deviations with normalized exceedance `R = D/T`, severity bands, same-family
  merging and cross-family `event_group_id` grouping.
- **Evidence quality** — heuristic index `Q = 0.35A + 0.30F + 0.20S + 0.15M`
  (ARCHITECTURE §8.7), unavailable when ungrounded.
- **Scoring** — prototype rubric (`configs/scoring.yaml`), piecewise-linear
  transform, ≥3-of-4 valid-dimension rule with weight renormalization.
- **Dashboard & exports** — Streamlit UI consuming the single pipeline; versioned
  JSON + detections CSV.

## The one pipeline contract

```python
from vocallens.pipeline import analyze_pair
from vocallens.schemas import AnalysisRequest
result = analyze_pair(AnalysisRequest(reference_audio=..., participant_audio=..., transcript=...))
```

The dashboard, evaluation script, and exporters all call `analyze_pair`. The UI
does not reimplement alignment, detection, explanation, or scoring.

## Repository layout

```
configs/      analysis.yaml, scoring.yaml  (canonical, validated on load)
data/         synthetic pilot dataset + manifest + annotations + dataset card
src/vocallens/ pipeline and modules (schemas, audio_io, transcript, alignment,
               region_mapping, features, detection, quality, explanations,
               scoring, export, synthesis)
app/          streamlit_app.py
scripts/      build_dataset_manifest.py, validate_dataset.py, run_evaluation.py
tests/        pytest suite (unit + integration + failure paths)
reports/      alignment_feasibility.md, evaluation/ (generated)
docs/         technical_report.md, demo_script.md
```

## Honesty notes

- The pilot dataset is **synthetic tonal fixtures** (clearly labeled), used for
  controlled feasibility/engineering tests. It is not natural speech and does not
  demonstrate generalization. See `data/README.md`.
- WhisperX real-speech feasibility is **BLOCKED** (no licensed real speech in this
  environment; dependency conflict with the dashboard). See
  `reports/alignment_feasibility.md`.
- Scores are a **provisional prototype rubric**, not a validated measure of
  speaking quality. Thresholds are not tuned on held-out data.

See `CLAUDE.md`, `ARCHITECTURE.md`, and `DESIGN.md` for the canonical contracts.
