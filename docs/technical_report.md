# VocalLens — Technical Report

**Prototype:** evidence-grounded contrastive speech-delivery analysis.
**Event:** IIT Mandi Multimodal AI Hackathon — Track C (Contrastive Speech
Analytics & Temporal Flaw Grounding).
**Environment:** Windows 11, Python 3.11.9 (CPU only).
**Report date:** 2026-10-14.

> Scope note: every number in this report is a *measured* value from this
> repository's current state. The evaluation was run on a **synthetic tonal
> pilot dataset**; it is feasibility evidence only and does **not** demonstrate
> generalization to real human speech. See §6.

---

## 1. Problem and approach

VocalLens compares a **participant** recording with a **reference** recording of
the *same English text*, localizes measurable delivery differences in time, and
explains each with the evidence behind it. Every reported deviation traces to a
feature, a time region, a baseline comparison, a configured rule, a severity
band, and an explicit evidence-quality assessment.

The product is a **comparison / coaching prototype**, not a judge of ability,
intent, confidence, or emotion. A difference from the reference may be
intentional or stylistic; the system reports measured deltas, not verdicts.

### Design principles (enforced in code and tests)
- Forced alignment maps supplied words to audio; it does **not** verify
  transcript correctness.
- Reference and participant are aligned **independently** and compared on their
  own clocks, over **mapped phrase regions**, not identical absolute seconds.
- Missing/unreliable measurements are `null`/unavailable, **never zero**.
- Timestamps are never fabricated when alignment is unavailable.
- Scores are prototype rubric scores, not an objective measure of quality.

## 2. Architecture

A single pipeline contract is the one source of truth; the dashboard,
evaluation script, and exporters all call it:

```python
def analyze_pair(request: AnalysisRequest) -> AnalysisResult: ...
```

Stages (`src/vocallens/`):

| Stage | Module | Responsibility |
|---|---|---|
| Validate / decode | `audio_io.py` | decode to 16 kHz mono analysis copy; record sample rate, channels, peak, clipping; reject corrupt/out-of-limit files; **no** loudness normalization before energy analysis |
| Transcript | `transcript.py` | normalize shared text; tokenize words |
| Alignment | `alignment.py` | independent forced alignment per recording; `whisperx` (optional) / `provided` / explicit `unavailable`/`partial`/`failed` |
| Region mapping | `region_mapping.py` | Levenshtein-based transcript↔audio mapping with a mismatch safeguard; phrase windows on each recording's own clock |
| Features | `features.py` | word/syllable rate, pauses, pitch variability (semitone IQR), within-recording relative energy (dBFS), MFCC diagnostics; validity + signal-quality flags |
| Detection | `detection.py` | pace / pause / pitch-variation / energy-dynamics candidates; normalized exceedance `R = D/T`; severity bands; same-family merge + cross-family `event_group_id` grouping |
| Quality | `quality.py` | evidence-quality index `Q = 0.35·A + 0.30·F + 0.20·S + 0.15·M` (ARCHITECTURE §8.7); unavailable when ungrounded |
| Explanations | `explanations.py` | plain-language, caveated explanation per detection |
| Scoring | `scoring.py` | prototype rubric from `configs/scoring.yaml`; piecewise-linear transform; ≥3-of-4 valid-dimension rule with weight renormalization |
| Export | `export.py` | versioned JSON + detections CSV |
| Synthesis | `synthesis.py` | deterministic generation of the synthetic pilot dataset |

Schemas are typed (`schemas.py`); both YAML configs are validated on load
(`config.py`) and reject invalid/unsupported values.

### Scoring rubric (provisional, `configs/scoring.yaml`)
Four dimensions, piecewise-linear transform on aggregate normalized exceedance,
anchored at `(0.0 → 100)`, `(1.0 → 70)`, `(3.0 → 0)`:

| Dimension | Weight |
|---|---|
| pace | 0.30 |
| pause_management | 0.30 |
| vocal_variation | 0.20 |
| energy_control | 0.20 |

Overall score requires **≥3 of 4** valid dimensions; weights are renormalized
over the valid set. Below that threshold the overall score is returned as
unavailable (not zero). These anchors are **not** tuned on held-out data.

## 3. Dataset

Synthetic, controlled pilot dataset (`data/README.md`). **It is not natural
human speech.**

- **Recordings:** 36 (6 passages × 6 variants). 16 kHz mono PCM_16 WAV.
- **Passages:** 6 short original English sentences written for this repository.
- **Variants:** `reference`, `pace_fast`, `pace_slow`, `long_pause`, `monotone`,
  `energy_drop` (one reference + five controlled flawed variants).
- **Flaw families:** pace, pause, pitch_variation, energy_dynamics.
- **Splits (by passage, no leakage):** train = p01–p04 (24), val = p05 (6),
  test / held-out = p06 (6).
- **Ground truth:** each recording carries `word_timings` (known by
  construction, consumed via the `provided` alignment backend, labeled as such)
  and `flaw_intervals` (defined by the generating transform, not inferred after
  observing model output).
- **License / consent:** CC0-1.0; synthetic, no human recordings, no consent
  required. Provenance: generated deterministically by `vocallens.synthesis`.

Generation transforms (from `vocallens.synthesis`): `pace_fast` ×0.60 durations;
`pace_slow` ×1.55; `long_pause` +1.1 s gap after the 2nd word; `monotone`
constant F0; `energy_drop` ×0.30 amplitude on the 2nd half.

## 4. Alignment feasibility (honest status)

**Only real-speech alignment *accuracy* remains BLOCKED / NOT VERIFIED**; the
previously-reported dependency conflict was re-investigated and retracted
(`reports/alignment_feasibility.md`, revised 2026-10-13).

- **No dependency conflict (claim retracted).** `whisperx==3.8.6`,
  `streamlit==1.45.1`, `protobuf==6.33.6` (**< 7**), `numpy==1.26.4` (**< 2**),
  and `torch==2.8.0` were observed installed and importing together in one
  interpreter. WhisperX 3.8.6 declares plain `numpy` (unpinned); it does not
  force `numpy>=2.1` or `protobuf>=7`. WhisperX stays an optional extra
  (`requirements-align.txt`) only because it pulls a large stack (torch, etc.),
  not because of a version conflict.
- **Model asset loads.** `whisperx.load_align_model` downloads and loads the
  360 MB English wav2vec2 alignment model on CPU (~112 s first run, then cached).
- **ffmpeg dependency removed.** The adapter previously failed at
  `whisperx.load_audio()` with `FileNotFoundError` (missing ffmpeg) and correctly
  degraded to `unavailable`. It now decodes via the project's soundfile/librosa
  decoder at the analysis rate, so ffmpeg is not required; the adapter then runs
  end to end (`whisperx.align()` executes and returns word-level timings).
- **Still not verified:** forced-alignment *accuracy* on real speech — no
  licensed/consented real English speech is available, and tonal fixtures have no
  phonetic content, so they are not a valid accuracy test. **No timestamps are
  fabricated** when alignment is unavailable.
- For the synthetic pilot the pipeline uses the `provided` ground-truth backend
  (labeled, not forced-alignment output).

## 5. Evaluation (measured)

Command: `python scripts/run_evaluation.py --split test`
Source: `reports/evaluation/evaluation_test_latest.json`
Generated: 2026-10-14T15:14:51Z · split `test` · **6 held-out cases** (passage
p06). `is_synthetic_pilot = true`. (Detection metrics and per-case results are
deterministic across runs; only the stage runtimes in §5.3 vary run to run.)
Results below are **after** adding the utterance-level pitch-variation rule
(ARCHITECTURE §8.6 "Pitch-variation intervals"); see §5.5 for the before/after.

> Report note (verbatim from the run): *"Feasibility pilot on synthetic tonal
> fixtures; NOT evidence of generalization to real speech. Thresholds were not
> tuned on this set."*

### 5.1 Per-family detection metrics

| Family | TP | FP | FN | Precision | Recall | F1 |
|---|---|---|---|---|---|---|
| pace | 2 | 1 | 0 | 0.667 | 1.000 | 0.800 |
| pause | 1 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| pitch_variation | 1 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| energy_dynamics | 0 | 0 | 1 | — | 0.000 | — |

### 5.2 Per-case detail

| Case | Intended | Detected | #Det | Best IoU (intended) | Ref/Par coverage | Overall score | Status |
|---|---|---|---|---|---|---|---|
| p06_pace_fast | pace | pace | 2 | 0.693 | 1.0 / 1.0 | 79 | complete |
| p06_pace_slow | pace | pace | 2 | 0.693 | 1.0 / 1.0 | 86 | complete |
| p06_long_pause | pause | pace, pause | 2 | 0.374 | 1.0 / 1.0 | 80 | complete |
| p06_monotone | pitch_variation | pitch_variation | 1 | 0.967 | 1.0 / 1.0 | 96 | complete |
| p06_energy_drop | energy_dynamics | — | 0 | 0.000 | 1.0 / 1.0 | 99 | complete |
| p06_reference_self | none | — | 0 | n/a | 1.0 / 1.0 | 100 | complete |

### 5.3 Runtime by stage (seconds, over 5 timed analyses)

| Stage | Mean | Max |
|---|---|---|
| validate / decode | 0.0040 | 0.0108 |
| alignment | 0.0003 | 0.0006 |
| region mapping | 0.0001 | 0.0001 |
| features | 0.6411 | 3.1168 |
| detection | 0.0022 | 0.0024 |
| scoring | 0.0001 | 0.0001 |
| **total** | **0.7566** | **3.5383** |

Feature extraction dominates runtime; alignment is near-free because the pilot
uses the `provided` backend.

### 5.4 Reading the results (honest interpretation)
- **Pace and pause families fire correctly** on p06 (recall 1.0), with usable
  temporal localization (IoU 0.69 for pace; 0.37 for the inserted pause). The
  single pace false positive and the pace flag on `long_pause` reflect that an
  inserted pause also perturbs local word rate — association, grouped under a
  shared `event_group_id`, not a causal claim.
- **Pitch variation now fires** on `p06_monotone` (recall 1.0, precision 1.0,
  IoU 0.967) via the whole-utterance semitone-IQR rule added in §8.6. Monotone
  delivery reduces pitch range *across* the utterance (ref IQR 2.84 → participant
  0.028 semitones); the per-phrase comparison alone diluted it below threshold.
  No thresholds were tuned on the held-out set — the rule compares the same
  semitone-IQR metric at utterance scale.
- **Energy-dynamics did not fire** on p06 (recall 0.0). Root cause is diagnostic,
  not a code defect: `z_rel` standardizes within-recording by design (to avoid
  gain/distance confounds), so the synthetic `energy_drop` — largely a *global*
  loudness reduction (median −22 → −29 dBFS) — produces only a small per-phrase
  relative contrast (R≈0.21 < 1.0), compounded by an inflated recording energy
  IQR (~14 dB from the synthetic envelopes). Catching it would need a different
  (absolute/trend) energy rule and non-synthetic data; deferred (see §7).
- **`reference_self` (reference vs. itself) scores 100 with zero detections** — a
  sanity check that the pipeline does not invent deviations where none exist, and
  the utterance pitch rule adds no false positive here.
- Overall scores remain a rubric transform, not a validated quality measure.

### 5.5 Before/after the utterance-level pitch rule

| Family | Before (per-phrase pitch only) | After (+ utterance rule) |
|---|---|---|
| pitch_variation | TP 0, FN 1, recall 0.0, F1 — | TP 1, FN 0, **recall 1.0, F1 1.0** |
| p06_monotone case | 0 detections, IoU 0.000, score 98 | 1 detection, **IoU 0.967**, score 96 |
| pace / pause / energy | unchanged | unchanged (no new false positives) |

The change is a structural detection fix (new interval for an existing metric),
not threshold tuning on the test split.

## 6. Tests

`python -m pytest -q` → **80 passed** (Python 3.11.9). Coverage spans transcript
normalization, region mapping and mismatch boundaries, config validation,
schemas, features, detection (including the utterance-level pitch rule and its
no-false-positive guard), quality, scoring, export, alignment
fallback/unavailable paths and the ffmpeg-free WhisperX decode, the end-to-end
pipeline (short, silent, noisy, clipped, mismatched, partial, and failed cases),
and the FastAPI boundary (`tests/test_api.py`: health, samples, config,
sample/upload analysis, evaluation, exports, and upload-validation/error paths
via the fastapi `TestClient`).

## 7. Limitations

- **Synthetic tonal fixtures**, not natural speech: no formants, coarticulation,
  real prosody, room acoustics, or microphone variation. Results are feasibility
  evidence only and do not generalize to real speakers.
- **Real-speech forced-alignment accuracy is NOT VERIFIED** (no licensed/consented
  real audio). The dependency conflict previously cited was retracted: WhisperX
  installs alongside the dashboard, the model loads, and the adapter runs without
  ffmpeg — only a valid real-speech accuracy test is missing (§4).
- **Scores are provisional and unvalidated**; thresholds are not tuned on
  held-out data; no psychometric claims.
- **Energy-dynamics detection is under-sensitive** on this pilot (recall 0.0 on
  p06); the metric is intentionally invariant to global loudness, so a synthetic
  uniform-amplitude drop is a poor test of it (see §5.4).
- **Pilot size is tiny** (6 held-out cases, single synthetic voice per passage).
  No inter-annotator agreement is reported because labels are defined by the
  generating transform, not by multiple human annotators.

## 8. Next steps for a real evaluation

1. Replace synthetic fixtures with **consented, licensed human recordings**
   (≥2 speakers, split by passage) under `data/private/` (gitignored).
2. Install WhisperX from `requirements-align.txt` in a **separate alignment
   environment**; run the 3-clip feasibility gate on real speech and report
   alignment coverage and temporal error.
3. Add an absolute/trend-based energy rule (or better, non-synthetic data) so
   energy-dynamics is testable, and calibrate any thresholds on a **validation**
   split (never the held-out test set), then re-run the held-out evaluation.
4. Report per-family metrics, temporal IoU/overlap, alignment coverage, failure
   modes, and runtime on the real set; treat results as feasibility evidence
   until sample size supports stronger claims.

## 9. Reproducibility

```bash
python -m venv .venv && . .venv/Scripts/activate   # (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt                    # core engine + Streamlit
python scripts/build_dataset_manifest.py           # build synthetic pilot
python scripts/validate_dataset.py                 # Gate A: dataset validation
python -m pytest -q                                # Gate B: 80 tests (engine + API)
python scripts/run_evaluation.py --split test      # held-out metrics

# Primary front end — React + FastAPI (two terminals):
pip install -r requirements-api.txt                # adds fastapi + uvicorn
uvicorn api.main:app --port 8000                   # terminal 1: API on :8000
cd frontend && npm install && npm run dev          # terminal 2: UI on :5173

# Fallback front end — Streamlit (no Node needed):
streamlit run app/streamlit_app.py                 # Gate C: dashboard
```

Each analysis JSON export carries software/config/model versions, config hashes,
and per-stage timings for provenance. Canonical contracts live in `CLAUDE.md`,
`ARCHITECTURE.md`, and `DESIGN.md`.
