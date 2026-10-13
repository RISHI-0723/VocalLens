# CLAUDE.md — VocalLens Build Instructions

This file governs implementation workflow and coding discipline. `ARCHITECTURE.md` is canonical for algorithms, contracts, and scientific definitions; `DESIGN.md` is canonical for the user experience. If the documents conflict, follow the resolution procedure in §2 and reconcile the documents before implementing the disputed behavior.

---

## 1. Mission

Build VocalLens: a reproducible prototype comparing a participant's delivery with a reference recording of the same English text, identifying measurable candidate deviations, localizing them, and explaining them with evidence.

Prioritize temporal grounding, data quality, testability, and honest limitations over a flashy but unsupported demo.

## 2. Read, Precedence, and Conflict Resolution

Before coding:

1. Read `ARCHITECTURE.md` and `DESIGN.md`.
2. Inspect the repository, Python version, dependencies, files, and Git status.
3. Preserve existing work; never overwrite/delete files without inspection.
4. Summarize current state, gaps, risks, and next bounded task.

**Source-of-truth precedence:**
- Algorithm, data contract, threshold, score, and quality-label semantics → `ARCHITECTURE.md`.
- Layout, interaction, visual language, accessibility, and user-facing copy → `DESIGN.md`.
- Phase order, coding process, tests, Git/CI, and completion reporting → this file.

**If a conflict crosses domains** (for example, a backend severity bucket versus its UI label), stop before coding the disputed behavior. Identify the exact conflicting sections, propose one reconciled rule, update the canonical document for that rule's domain and add a reference in the other document, then resume. Do not silently choose a third interpretation. If the user must decide a product/science tradeoff, ask one concise question and continue unrelated work only.

**If implementation reality requires changing `analyze_pair()` or `AnalysisResult`:** stop downstream implementation; write a short contract-change proposal containing the observed blocker, old/new field or behavior, migration impact, tests to update, and whether results remain backward-compatible. Update the architecture contract first, then this file and the design only where affected, plus schemas, fixtures, exporters, and tests in the same change. Add a schema-version/migration note when serialized results change. Do not quietly patch callers around a broken contract.

**Unattended build fallback:** if a user decision is genuinely required and the user is unavailable, do not guess on an irreversible product/science tradeoff. Record `BLOCKED_USER_DECISION` with the exact question and alternatives, continue only work independent of that choice, and make any reversible implementation behind a clearly named config/feature flag only when the canonical spec already authorizes that default. Otherwise leave the disputed behavior unimplemented.

## 3. Fixed Initial Stack

- Python 3.11.
- NumPy, SciPy, librosa for audio/features.
- WhisperX alignment first, subject to feasibility testing.
- Montreal Forced Aligner (MFA) only if a compatible acoustic model and pronunciation dictionary are installed.
- Streamlit and Plotly for dashboard.
- pytest for tests.
- YAML for configuration.
- Typed dataclasses or Pydantic for schemas.
- `pronouncing`/CMU Pronouncing Dictionary for English syllable estimates; aligned word rate remains primary.

Target language is **English (`en-US`) for the MVP**. Do not claim multilingual support. Pin package versions only after installing and testing a clean environment.

### Configuration responsibilities
- `configs/analysis.yaml`: preprocessing, sample rate, framing, pauses, alignment/mapping thresholds, feature coverage, energy/pitch settings, severity grouping, evidence-quality weights, and runtime settings.
- `configs/scoring.yaml`: rubric dimension weights, piecewise score transforms, valid-data rules, and overall-score coverage behavior. Its starter block and semantics are defined in `ARCHITECTURE.md` §8.9.

Validate configs on load. Reject invalid or unsupported values; never silently ignore a setting.

## 4. Scientific Definitions — Refer to Architecture

Do **not** restate numerical constants or formulas here. Implement the canonical definitions in `ARCHITECTURE.md`:
- §5–6: stack, language, alignment feasibility, and preprocessing.
- §8.4: transcript-region mapping and mismatch safeguards.
- §8.5: feature definitions, pause/rate/pitch/energy methods.
- §8.6: detection, normalization, severity, and grouping.
- §8.7: evidence-quality formula and signal-state mapping.
- §8.9: rubric and valid-dimension requirements.
- §9: YAML configuration contract.

If a value must change, change it in the canonical architecture and its config/test together; do not edit a duplicated summary here.

## 5. Non-Negotiable Rules

1. Forced alignment maps supplied words to audio; it does not verify transcript correctness.
2. Align reference and participant independently.
3. Compare mapped phrase regions, not identical absolute seconds by default.
4. Never fabricate timestamps when alignment fails.
5. A difference from the reference is not automatically poor delivery.
6. Do not claim an acoustic delta proves intent, confidence, emotion, audience impact, or causation.
7. MFCCs are diagnostics/visualizations, not standalone proof of rhetorical flaws.
8. Missing/unreliable measurements are `null`/unavailable, never zero.
9. Scores are prototype rubric scores, not objective speaking quality.
10. Use actual measured dataset counts, metrics, timings, and test results only.

## 6. One Pipeline Contract

Implement:

```python
def analyze_pair(request: AnalysisRequest) -> AnalysisResult:
    """Analyze participant delivery against a reference for shared text."""
```

The app, evaluation script, and exporters must call the same pipeline. Do not duplicate features, detection, explanations, or scoring in Streamlit.

The validated result includes schema version, sample ID, status, warnings, audio metadata, tokens, separate alignments/statuses, region mapping, timestamped feature series and units, detections with values/deltas/rules/severity/quality, dimension scores and coverage, overall score or `null`, provenance/config/model versions, and stage timings.

## 7. Exactly Three Implementation Phases

Work sequentially. Do not start a later phase until the current exit gate passes unless the user explicitly changes priorities. If blocked, report it and propose the smallest safe workaround.

### Phase 1 — Dataset, alignment feasibility, contracts
- Inspect repository/environment and Git status.
- Establish manifest, English labels, provenance, and split.
- Implement transcript normalization and region mapping.
- Test WhisperX on three short clips within the architecture's stated time budget; assess MFA only if compatible assets exist.
- Define schemas and validate both YAML configs.
- Add tests for mapping, mismatch boundaries, config validation, and schemas.

**Exit report:** actual data count; aligner/model/language tested; outcomes; commands; test results; blockers. File creation alone does not pass the gate.

### Phase 2 — Analysis engine
- Implement input validation, decoding, mono policy, and analysis-rate copy.
- Implement alignment adapter with explicit partial/unavailable paths.
- Implement timing, pause, pitch, energy, and spectral features.
- Implement mapped-region comparison, detection, grouping, severity, quality, explanations, and scoring.
- Implement versioned JSON/CSV exports.
- Test normal, short, silent, noisy, clipped, mismatched, partial, and failed cases.
- Run a small held-out evaluation and save actual results.

**Exit report:** behavior; test results; held-out count; measured metrics; alignment coverage; limitations; blockers.

### Phase 3 — Dashboard and submission
- Build Streamlit around `analyze_pair()`.
- Display uploads, transcript, separate reference/participant context, plots, detection evidence, quality, and warnings.
- Provide timestamps/manual seeking. Do not claim native audio auto-seeking unless implemented and tested.
- Add JSON/CSV downloads.
- Show honest evaluation empty state until metrics exist.
- Finish README, technical report, dataset link, and demo script.
- **Required verification:** run documented setup, tests, and app smoke test in a fresh virtual environment or clean container. If environment constraints make this impossible, report the exact missing prerequisite and mark the gate `BLOCKED`, not PASS.

**Exit report:** exact launch command; tested workflow; actual exports; evaluation state; demo status; known issues; final Git status.

## 8. Dataset and Evaluation Discipline

Initial target: six short English passages, one reference plus approximately four variants each (~30 recordings), two or more speakers where feasible, four flaw families, and 6–10 held-out annotated cases. These are targets only; publish actual counts.

- Use only licensed/consented audio.
- Include IDs, transcript reference, labels/severity, recording method, review status, provenance, split, and quality notes.
- Human-review controlled variants.
- Split by passage where feasible.
- Report inter-annotator agreement only when multiple annotators actually labeled the same cases.
- Report per-family metrics, temporal error/overlap, alignment coverage, failure modes, and runtime where supported.
- Treat small pilot results as feasibility evidence, not proof of generalization.

## 9. Engineering Standards

- Use small modules, type hints, and concise public-interface docstrings.
- Validate paths, formats, durations, dimensions, and numerical values.
- Catch expected errors and return actionable messages; do not broadly swallow exceptions.
- Avoid hidden magic numbers; use the designated config.
- Test important formulas, unit conversions, threshold boundaries, and missing-data paths.
- Do not commit `.env`, keys, private recordings, model caches, or large generated files.
- Check model size, license, language support, and environment cost before download.
- Keep dependencies minimal and pinned after verification.
- Do not refactor unrelated code or delete tests to make a check pass.
- No happy-path placeholder unless clearly surfaced as unavailable.

## 10. Git, CI, and Verification

Before claiming completion:
1. Run focused tests.
2. Run the full suite.
3. Run import/compile checks and app command where relevant.
4. Inspect `git diff` and `git status`.
5. Check generated files/private data are not accidentally included.
6. Report exact commands and actual pass/fail counts.

Use coherent commits when requested or expected by the repo workflow. Never force-push, rewrite history, or commit/push without authorization. CI should use supported Python and pinned dependencies, run without private data/secrets, and include lint/type checks if configured.

## 11. Time Triage

Prioritize:
1. Dataset manifest, labels/provenance, alignment feasibility.
2. Region mapping and timestamped evidence.
3. Timing/pause features and quality checks.
4. Pitch/energy features and confound warnings.
5. Detection rules, severity, quality, scoring.
6. Tests and actual held-out evaluation.
7. Dashboard, exports, documentation, demo.

If alignment blocks progress, preserve the adapter and explicit unavailable state, document the blocker, and continue independently testable work. Do not fake alignment.

## 12. Dashboard Constraints

Follow `DESIGN.md`. Use Streamlit-native components first. Keep recording-specific time axes distinct. Use accessible labels and contrast; do not rely on color alone. Distinguish no detections from failed analysis. Do not show fake metrics or claim playback synchronization that has not been verified.

## 13. Completion Response Format

After each phase, report:
1. **Implemented**
2. **Files created/changed**
3. **Commands executed**
4. **Tests and actual results**
5. **Known limitations/blockers**
6. **Phase gate:** PASS or FAIL, with reasons
7. **Next phase:** what may begin next

Never claim a command ran, a test passed, a file exists, or a metric was achieved unless verified in the current work.
