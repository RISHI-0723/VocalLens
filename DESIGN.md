# VocalLens — Product and Dashboard Design

**Product:** VocalLens  
**Primary user:** Hackathon evaluator, speaker, coach, or researcher comparing a reference recording with a participant recording.  
**Experience goal:** Make delivery differences understandable, inspectable, and honest about uncertainty.  
**Design principle:** Evidence first; score second.

---

## 1. Product Promise

VocalLens answers:
1. Where does the participant's delivery differ from the reference?
2. What measured evidence supports the observation?
3. How large is the difference, and which rule flagged it?
4. How reliable is the evidence?
5. What should the user inspect or listen to next?

It is a prototype coaching/analysis tool, not an objective judge of character, intent, confidence, emotion, intelligence, or ability. A difference may be intentional or stylistic.

**Core flow:** Upload → align → compare → inspect → export.

---

## 2. Information Architecture

Three main app areas:
- **Analyze:** upload two recordings, enter shared transcript, run analysis, inspect evidence.
- **Evaluation:** show metrics only after a real evaluation run.
- **About & Reproducibility:** methods, rubric, dataset, versions, limitations, and setup.

Keep the main task on one page.

---

## 3. Wireframes

These are layout wireframes, not pixel-perfect mockups. Implement this hierarchy, then tune using screenshots of the running app.

### Analyze — before running

```text
┌─────────────────────────────────────────────────────────────────────────┐
│ VocalLens                                      Analyze | Evaluation | ? │
│ Evidence-grounded comparison of speech delivery                         │
├─────────────────────────────────────────────────────────────────────────┤
│ INPUTS                                                                   │
│ ┌─────────────────────────────┐  ┌────────────────────────────────────┐ │
│ │ REFERENCE RECORDING         │  │ PARTICIPANT RECORDING              │ │
│ │ [ Choose audio file ]       │  │ [ Choose audio file ]              │ │
│ │ Filename · duration · SR    │  │ Filename · duration · SR           │ │
│ │ [ native audio player ]     │  │ [ native audio player ]            │ │
│ └─────────────────────────────┘  └────────────────────────────────────┘ │
│ Shared transcript                                                        │
│ ┌─────────────────────────────────────────────────────────────────────┐ │
│ │ Enter the exact words spoken in both recordings...                  │ │
│ └─────────────────────────────────────────────────────────────────────┘ │
│ [ Analyze recordings ]  Transcript is user-supplied; alignment can fail │
├─────────────────────────────────────────────────────────────────────────┤
│ Results appear here after analysis                                       │
└─────────────────────────────────────────────────────────────────────────┘
```

### Analyze — after running

```text
┌─────────────────────────────────────────────────────────────────────────┐
│ RESULTS   Status: Partial / Complete       Alignment: Ref ✓  Participant !│
│ ┌────────────────┐ ┌────────────────┐ ┌────────────────┐ ┌─────────────┐│
│ │ Prototype score│ │ Valid dimensions│ │ Candidate flags│ │ Quality     ││
│ │ illustrative   │ │ 3 of 4          │ │ illustrative   │ │ Medium      ││
│ └────────────────┘ └────────────────┘ └────────────────┘ └─────────────┘│
│ Warnings: participant alignment partial; interpretation limited          │
├─────────────────────────────────────────────────────────────────────────┤
│ FEATURE EVIDENCE                                                         │
│ [Matched phrase selector] [Pace] [Pauses] [Pitch] [Energy]               │
│ ┌─────────────────────────────────────────────────────────────────────┐ │
│ │ Reference phrase/time plot       Participant phrase/time plot       │ │
│ │ (separate clocks; labeled units; detected interval marked)           │ │
│ └─────────────────────────────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────────────────────────┤
│ CANDIDATE DEVIATIONS                                                     │
│ ┌─────────────────────────────────────────────────────────────────────┐ │
│ │ Longer pause · timestamp · severity · evidence quality               │ │
│ │ Participant value | Reference value | Delta | Rule                    │ │
│ │ Evidence-based explanation and caveat                                 │ │
│ └─────────────────────────────────────────────────────────────────────┘ │
│ [Download analysis JSON] [Download detections CSV]                       │
└─────────────────────────────────────────────────────────────────────────┘
```

All wireframe values are placeholders. Never seed them as actual app data.

### Evaluation — empty state

```text
┌─────────────────────────────────────────────────────────────────────────┐
│ EVALUATION                                                               │
│                     No evaluation results yet                            │
│ Run scripts/run_evaluation.py on the documented held-out set.            │
│ Metrics will appear here after a successful run.                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Analyze Screen Specification

### Inputs
- Two labeled upload areas: **Reference recording** and **Participant recording**.
- After validation, show filename, duration, original sample rate, and native audio player; never show private filesystem paths.
- Required **Shared transcript** text area. Explain that the user supplies the transcript and forced alignment maps it to audio; it does not verify the words.
- English (`en-US`) is the MVP language. Expose other languages only after the full path is tested for them.
- Primary action: **Analyze recordings**. Disable until required inputs are valid.

### Exact input/error copy

| Condition | Message |
|---|---|
| Reference missing | “Upload a reference recording to continue.” |
| Participant missing | “Upload a participant recording to continue.” |
| Empty transcript | “Enter the shared transcript. The aligner needs the words to map them to audio.” |
| Unsupported/corrupt file | “This audio file could not be decoded. Try a WAV or supported MP3 file.” |
| Clip too short | “This clip is shorter than the configured minimum. Upload a longer recording.” |
| Clip too long | “This clip exceeds the configured duration limit. Trim it and try again.” |
| Alignment partial | “Only part of the transcript aligned. Results are limited to mapped regions.” |
| Alignment unavailable | “Word alignment is unavailable for this recording. Time-grounded comparisons cannot be shown for unmapped regions.” |
| No detections | “No candidate deviations crossed the configured thresholds. This does not prove the deliveries are identical.” |
| Analysis failed | “Analysis could not be completed. Review the details below and try again.” |
| Score unavailable | “Overall score unavailable: fewer than 3 of 4 dimensions had valid measurements.” |
| Alignment timed out | “Alignment took too long and was stopped. Try a shorter clip or continue with the available partial results.” |

Messages must reflect actual pipeline states.

### Processing and long-running analysis

Show stage labels: validating audio, aligning reference, aligning participant, extracting features, comparing regions, building evidence/scores. Show a percentage only if it reflects actual progress.

Set an explicit alignment timeout from `analysis.yaml`. At timeout, cancel/terminate the aligner subprocess where supported, mark that attempt timed out, preserve other valid results, and display the timeout message. Do not imply the entire application has hung.

The MVP may not support cancellation of the entire Streamlit run. If a reliable cancel control is not available, state that analysis can be stopped by using the app's Stop control/restarting the run; do not render a decorative Cancel button that does nothing. First-run model loading may take longer and should be disclosed before analysis.

### Results summary
Show:
- Overall prototype rubric score or **Unavailable**
- Valid dimensions, e.g. `3 of 4`
- Candidate deviation count
- Reference and participant alignment status

Show warnings directly beneath the summary. Partial alignment must be visible before the user interprets a score.

### Dimension scores
Use **four horizontal bars**, not a radar chart: Pace, Pause management, Vocal variation, Energy control. Each row shows a score on the scoring contract's 0–100 prototype scale or `Unavailable`, coverage/validity, and detail text. The transform is defined in `ARCHITECTURE.md` §8.9 and the starter `configs/scoring.yaml`; the UI displays returned scores and must not recompute them. Unavailable is not zero. Show the overall score and minimum-valid-dimensions rule separately. Include a nearby caption: “Prototype rubric score; provisional transform, not a validated measure of speaking quality.”

### Feature charts
Use Plotly with labels/units. Reference and participant recordings have separate clocks; never overlay raw timestamps as if synchronized.

Views:
- Word/phrase rate and duration
- Pause intervals/duration
- Median F0 and pitch-variability IQR in semitones
- Relative phrase energy dynamics
- Optional MFCC/spectral diagnostics under an advanced section

**Advanced diagnostics wireframe:** place a collapsed “Advanced acoustic diagnostics (MFCC / spectrum)” section below the primary feature charts. When expanded, show (1) a labeled MFCC coefficient-by-time heatmap with time in seconds and coefficient index, (2) a reference/participant toggle rather than an overlaid raw-time comparison, and (3) a short note that these are diagnostic acoustic summaries, not direct flaw labels. If coefficients or a compatible view are unavailable, show “Advanced diagnostics unavailable for this recording pair” and the returned reason. Do not use unlabeled heatmaps or imply that brighter/darker colors mean better speech.

**Tooltip glossary copy:**
- **Pitch variability (semitone IQR):** “Shows the spread of the speaker’s voiced pitch in the selected phrase. A larger value means pitch varied across a wider range; it does not by itself mean the delivery was better or worse.”
- **Relative energy:** “Shows how this phrase’s measured energy compares with the same recording’s typical speech level. It reduces some recording-gain differences but cannot fully correct for microphone distance or room effects.”
- **Word rate:** “Aligned words per second in this phrase. Transcript and alignment errors can affect the estimate.”
- **Pause duration:** “Time detected as low-energy silence under the configured detector. Background noise and quiet speech can affect the boundary.”

Keep charts readable at laptop and projector sizes. Avoid dense, unlabeled heatmaps in the default view.

### Detection card

Each card contains family/title, participant interval, matched reference region/time, participant/reference values and delta, units, rule threshold, normalized exceedance, severity, evidence-quality label/score, main quality factors, explanation, and caveat. If detections share an `event_group_id`, render them in a visually bounded **Related observations** cluster with one shared event heading and one sub-card per family. Keep each sub-card's interval, rule, severity, evidence quality, and review action distinct; the cluster is an association, not proof of causation. If no group ID is returned, render a standalone card.

Example copy (illustrative only):

> **Longer pause than reference — timestamp**  
> Participant: 1.20 s · Reference: 0.35 s · Difference: +0.85 s  
> **Rule:** configured pause-difference threshold exceeded. **Severity:** Moderate. **Evidence quality:** High.  
> This may affect phrase continuity under this rubric; intentional emphasis is still possible.

Never label a person “bad,” “unconfident,” or a “failure.” If selecting a card cannot reliably seek audio, show timestamps and manual-seeking instructions. Never claim auto-seeking unless tested.

### Evidence-quality user-facing legend

Display the quality label with a short explanation and expandable factors. The following wording is canonical:

| Component | Plain-language label | User-facing meaning |
|---|---|---|
| `A` | Alignment coverage | “How much of the expected transcript aligned to audio.” |
| `F` | Feature coverage | “How much of the selected region had usable feature measurements.” |
| `S` | Signal quality | “Whether noise, clipping, channel issues, or limited voicing may affect this measurement.” |
| `M` | Text match | “How much of this phrase matched the shared transcript across recordings.” |
| `Q` | Overall evidence quality | “A heuristic summary of measurement support—not the probability that the detection is correct.” |

Signal-state labels and scores are defined in `ARCHITECTURE.md` §8.7 and `configs/analysis.yaml`. The UI must render the returned codes/values and use the wording above; it must not invent its own thresholds or recalculate quality.

### Exports
- **Download analysis JSON:** complete versioned result, metadata, warnings, alignments, mapping, features, detections, scores, quality components, provenance, timings.
- **Download detections CSV:** one row per grouped detection with IDs, family, participant interval, reference region, feature, values, delta, units, threshold, normalized exceedance, severity, quality, explanation, warnings, review status.

Disable downloads before analysis exists. Preserve partial status/warnings in exports.

---

## 5. Evaluation Screen

### Empty state
**No evaluation results yet.**  
Run `scripts/run_evaluation.py` on the documented held-out set to generate metrics. This page will populate after a successful run.

### Populated state
Show dataset version/count; evaluation timestamp; software/config version; per-family precision/recall/F1 where supported; temporal overlap/boundary error; alignment coverage/failure rate; runtime by stage and tested hardware; representative errors.

Include exact command and report path. If a metric cannot be computed, show **Unavailable** with a reason. Never seed the page with demo metrics.

---

## 6. About and Reproducibility

Expose methods and limitations, feature units, rubric/config version, aligner/model/language/status, actual dataset counts, annotation/provenance/license/consent/split, software versions, known limitations, and setup/test/evaluation/app commands.

If provenance or version metadata is missing, show the explicit state copy **“Provenance metadata unavailable for this result. Re-run analysis with the current pipeline to capture software, model, and config versions.”** If only some fields are missing, show the available fields and label each missing value **“Not recorded”**; never infer a version from the current environment and attach it to an older result.

Keep technical details available without overwhelming the primary workflow.

---

## 7. Visual System and Responsive Rules

### Layout and breakpoints
- Maximum content width: **1440 px**, centered.
- Below **768 px**: stack uploads and summary metrics; use single-column cards and charts sized to viewport.
- **768–1023 px**: show upload cards side-by-side when each remains usable; otherwise stack.
- **1024 px and above**: allow two-column chart/evidence arrangement only when both columns remain readable.
- Keep primary action and warnings near the relevant inputs/results.
- Use consistent spacing: 4, 8, 12, 16, and 24 px.

### Type scale

| Role | Size | Weight | Use |
|---|---:|---|---|
| Page title | 28 px | 700 | Page heading |
| Section heading | 20 px | 650/700 | Inputs, Evidence, Deviations |
| Card heading | 16 px | 600 | Detection/panel label |
| Body | 14–16 px | 400 | Instructions and explanations |
| Metadata/caption | 12 px minimum | 400/500 | Filename, units, helper text |
| Key numeric value | 24 px | 700 | Summary metrics |
| Chart labels | 12–14 px | 500 | Axes, ticks, legend |

Use the system sans-serif stack and tabular numerals for numeric values where supported. Essential caveats must not use tiny text.

### Color and contrast
- Neutral background and high-contrast primary text.
- Distinct stable series colors for Reference and Participant.
- Amber/caution for candidate deviations; red for actual errors.
- Neutral gray plus text for unavailable values.
- Pair color with labels, icons, line styles, or symbols.
- Meet **WCAG 2.2 AA**: at least **4.5:1** for normal text and **3:1** for large text and essential graphical objects/UI boundaries. Verify actual rendered colors.
- Never communicate meaning by color alone.

### Projector and screen-share readability
Use a laptop-width/16:9 viewport for demo testing. Keep selected detection, timestamp, key values, and explanation visible without scrolling where practical. Avoid tiny legends and long code blocks. Inspect a screen-share/projector view before recording.

---

## 8. Interaction, Keyboard, and State Design

### Keyboard/focus strategy
Streamlit controls provide much of the tab behavior, but the implementation cannot assume arbitrary focus-order control. Follow these practical requirements:
- Put controls in logical DOM/render order: heading → reference upload → participant upload → transcript → analyze action → results → exports.
- Use native labeled controls and buttons; do not create clickable text or color-only controls.
- Do not add custom keyboard shortcuts in the MVP.
- Test keyboard-only navigation in the running app: Tab/Shift+Tab order, visible focus, activation with Enter/Space, and whether errors are perceivable without a pointer.
- If a Streamlit component's focus behavior cannot be changed, document the limitation and avoid wrapping it in a misleading custom control. Keep all essential information available as ordinary text.

### States
Input: no files, one file missing, unsupported/corrupt audio, empty transcript, valid inputs.  
Processing: model loading, in progress, partial alignment, alignment unavailable, recoverable feature warning, fatal error, alignment timeout.  
Result: detections, no detections, partial result, score unavailable, evaluation empty, export unavailable.

“No detections” must never look like “analysis failed.”

### Playback
Use Streamlit's native audio player. Show each detection timestamp and manual-seeking instruction. If a custom synchronized player is later implemented, verify across supported browsers and retain the timestamp fallback.

---

## 9. Accessibility, Privacy, and Trust

- Explicit labels, logical focus order, keyboard testing, and visible focus.
- Labels/symbols alongside color.
- Readable charts/tables and WCAG AA contrast.
- Plain-language missing-data and quality explanations.
- Appropriate rounding and units; avoid false precision.
- Explain that the rubric is provisional and delivery differences can be intentional.
- Do not infer sensitive traits or psychological diagnoses.
- Retain uploaded audio only as long as necessary and do not publish without consent/rights.

---

## 10. Demo Storyboard (3–10 Minutes)

1. **Problem and goal (30–60 s):** compare same text and locate measurable differences.
2. **Inputs and dataset (45–90 s):** show transcript, recordings, manifest, actual counts and provenance.
3. **Run analysis (30–90 s):** show real processing stages and alignment status.
4. **Inspect one detection (60–120 s):** timestamp, matched phrase, values, delta, threshold, severity, quality, explanation.
5. **Show features (45–90 s):** compare two families and explain unavailable values.
6. **Export/evaluation (45–90 s):** download JSON/CSV; show metrics only if genuinely generated.
7. **Limitations (30–60 s):** small dataset, provisional rubric, alignment and acoustic confounds.

Use real output. Never insert fabricated metrics, detections, or dataset counts.

---

## 11. Product Acceptance Checklist

- [ ] Inputs and validation messages work.
- [ ] Processing and timeout statuses reflect actual behavior.
- [ ] Alignment status/warnings are visible.
- [ ] Matched regions and separate clocks are clear.
- [ ] Charts show units and readable legends.
- [ ] Four dimension scores use horizontal bars; unavailable is not zero.
- [ ] Detections show interval, values, delta, threshold, severity, quality, explanation, caveat.
- [ ] Evidence-quality component labels use the canonical glossary.
- [ ] Empty, no-detection, partial, timeout, and failure states are distinct.
- [ ] JSON/CSV exports match the versioned schema.
- [ ] UI consumes the central pipeline result.
- [ ] Keyboard navigation, visible focus, WCAG AA contrast, and projector readability are checked.
- [ ] Privacy, provenance, and limitations are visible.
- [ ] Demo uses real outputs.
