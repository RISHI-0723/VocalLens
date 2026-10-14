"""VocalLens interactive dashboard (DESIGN.md).

Consumes the central pipeline (`analyze_pair`) and renders real results only.
It never recomputes scoring or invents metrics. A clearly-labeled synthetic
sample path provides ground-truth alignment for the demo; uploaded real audio
requires the optional WhisperX aligner (otherwise alignment is unavailable and
time-grounded comparisons are limited, shown honestly).
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402

from vocallens.alignment import whisperx_available  # noqa: E402
from vocallens.config import load_analysis_config, load_scoring_config  # noqa: E402
from vocallens.export import to_detections_csv, to_json  # noqa: E402
from vocallens.pipeline import analyze_pair  # noqa: E402
from vocallens.schemas import AnalysisRequest, AnalysisStatus  # noqa: E402

DATA = REPO_ROOT / "data"
ANN = DATA / "annotations"
EVAL = REPO_ROOT / "reports" / "evaluation"

REF_COLOR = "#1f77b4"   # blue: reference
PAR_COLOR = "#d62728"   # red: participant

st.set_page_config(page_title="VocalLens", layout="wide")


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
@st.cache_data(show_spinner=False)
def _configs_info():
    a = load_analysis_config()
    s = load_scoring_config()
    return a.config_hash, s.config_hash


def _save_upload(uploaded, suffix):
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(uploaded.getbuffer())
    tmp.flush()
    tmp.close()
    return tmp.name


def _list_samples():
    if not (DATA / "manifest.csv").exists():
        return {}, []
    import csv as _csv

    passages = {}
    with (DATA / "manifest.csv").open(encoding="utf-8", newline="") as fh:
        for r in _csv.DictReader(fh):
            passages.setdefault(r["passage_id"], {})[r["variant"]] = r
    return passages, sorted(passages)


def _plot_series(series, title, color):
    fig = go.Figure()
    xs = [t for t, v in zip(series.times, series.values) if v is not None]
    ys = [v for v in series.values if v is not None]
    fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", line=dict(color=color, width=1.5), name=series.name))
    fig.update_layout(
        title=title, height=240, margin=dict(l=40, r=10, t=36, b=30),
        xaxis_title="time (s)", yaxis_title=series.unit, showlegend=False,
    )
    return fig


def _severity_badge(sev):
    return {"low": "🟡 Low", "moderate": "🟠 Moderate", "high": "🔴 High",
            "unavailable": "⚪ Unavailable"}.get(sev, sev)


# --------------------------------------------------------------------------- #
# Analyze screen
# --------------------------------------------------------------------------- #
def render_analyze():
    st.header("Analyze")
    st.caption("Evidence-grounded comparison of speech delivery. Transcript is "
               "user-supplied; forced alignment maps it to audio and does not verify the words.")

    passages, passage_ids = _list_samples()
    mode = st.radio(
        "Input source",
        ["Synthetic sample pair (ground-truth alignment — DEMO)", "Upload your own recordings"],
        help="Synthetic samples carry ground-truth word boundaries for a reliable demo. "
             "Uploaded real audio needs the optional WhisperX aligner for time-grounded results.",
    )

    req = None
    if mode.startswith("Synthetic"):
        if not passage_ids:
            st.warning("No dataset found. Run `python scripts/build_dataset_manifest.py` first.")
            return
        st.info("DEMO MODE: synthetic tonal fixtures with ground-truth alignment. "
                "Not natural speech; see the About page.")
        c1, c2 = st.columns(2)
        pid = c1.selectbox("Passage", passage_ids)
        variants = [v for v in passages[pid] if v != "reference"]
        variant = c2.selectbox("Participant variant", variants)
        ref_row = passages[pid]["reference"]
        par_row = passages[pid][variant]
        ref_ann = json.loads((ANN / f"{ref_row['recording_id']}.json").read_text(encoding="utf-8"))
        par_ann = json.loads((ANN / f"{par_row['recording_id']}.json").read_text(encoding="utf-8"))
        st.text_area("Shared transcript", ref_ann["transcript"], disabled=True, key="t_sample")
        if st.button("Analyze recordings", type="primary"):
            req = AnalysisRequest(
                reference_audio=str(DATA / ref_row["relative_path"]),
                participant_audio=str(DATA / par_row["relative_path"]),
                transcript=ref_ann["transcript"], sample_id=par_row["recording_id"],
                alignment_backend="provided",
                reference_provided_words=ref_ann["word_timings"],
                participant_provided_words=par_ann["word_timings"])
    else:
        c1, c2 = st.columns(2)
        ref_file = c1.file_uploader("Reference recording", type=["wav", "mp3", "flac", "ogg"])
        par_file = c2.file_uploader("Participant recording", type=["wav", "mp3", "flac", "ogg"])
        if ref_file:
            c1.audio(ref_file)
        if par_file:
            c2.audio(par_file)
        transcript = st.text_area("Shared transcript",
                                  placeholder="Enter the exact words spoken in both recordings…")
        attempt_wx = st.checkbox(
            f"Attempt WhisperX alignment (optional, slow, downloads a model) — installed: {whisperx_available()}",
            value=False,
            help="Off: uploaded audio runs without alignment (features only, time-grounded "
                 "comparisons unavailable). On: tries real forced alignment if WhisperX is set up.")
        missing = []
        if not ref_file:
            missing.append("Upload a reference recording to continue.")
        if not par_file:
            missing.append("Upload a participant recording to continue.")
        if not (transcript or "").strip():
            missing.append("Enter the shared transcript. The aligner needs the words to map them to audio.")
        for m in missing:
            st.caption("• " + m)
        if st.button("Analyze recordings", type="primary", disabled=bool(missing)):
            req = AnalysisRequest(
                reference_audio=_save_upload(ref_file, "_" + ref_file.name),
                participant_audio=_save_upload(par_file, "_" + par_file.name),
                transcript=transcript, sample_id="upload",
                alignment_backend="whisperx" if attempt_wx else "unavailable")

    if req is not None:
        stages = ["validating audio", "aligning reference", "aligning participant",
                  "extracting features", "comparing regions", "building evidence & scores"]
        with st.status("Running analysis…", expanded=True) as status:
            for s in stages:
                st.write(f"• {s}")
            result = analyze_pair(req)
            status.update(label=f"Analysis {result.status.value}", state="complete")
        st.session_state["result"] = result

    if "result" in st.session_state:
        _render_results(st.session_state["result"])


def _render_results(r):
    st.divider()
    # Summary row
    ref_a = r.reference_alignment.status.value if r.reference_alignment else "n/a"
    par_a = r.participant_alignment.status.value if r.participant_alignment else "n/a"
    st.subheader(f"Results — status: {r.status.value}")

    if r.status == AnalysisStatus.FAILED:
        st.error(r.failure_reason or "Analysis could not be completed. Review the details below and try again.")

    m1, m2, m3, m4 = st.columns(4)
    overall = r.scores.overall_display_score
    m1.metric("Prototype score", overall if r.scores.overall_available else "Unavailable")
    m2.metric("Valid dimensions", f"{r.scores.valid_dimension_count} of {len(r.scores.dimensions)}")
    m3.metric("Candidate flags", len(r.detections))
    m4.metric("Alignment", f"Ref {ref_a} / Part {par_a}")
    st.caption("Prototype rubric score; provisional transform, not a validated measure of speaking quality.")
    if not r.scores.overall_available and r.status != AnalysisStatus.FAILED:
        st.info("Overall score unavailable: fewer than 3 of 4 dimensions had valid measurements.")

    # Warnings
    if r.warnings:
        with st.expander(f"Warnings ({len(r.warnings)})", expanded=r.status != AnalysisStatus.COMPLETE):
            for w in r.warnings:
                st.write(f"**{w.code}** — {w.message}")

    _render_dimension_bars(r)
    _render_feature_charts(r)
    _render_detections(r)
    _render_exports(r)
    _render_advanced(r)


def _render_dimension_bars(r):
    st.markdown("#### Dimension scores")
    names, vals, texts = [], [], []
    label = {"pace": "Pace", "pause_management": "Pause management",
             "vocal_variation": "Vocal variation", "energy_control": "Energy control"}
    for d in r.scores.dimensions:
        names.append(label.get(d.name, d.name))
        vals.append(d.score if d.valid else 0)
        texts.append(f"{d.display_score:.0f}" if d.valid else "Unavailable")
    fig = go.Figure(go.Bar(x=vals, y=names, orientation="h", text=texts, textposition="outside",
                           marker_color=["#8884d8" if v else "#cccccc" for v in vals]))
    fig.update_layout(height=220, margin=dict(l=10, r=10, t=10, b=10),
                      xaxis=dict(range=[0, 100], title="prototype score (0–100)"))
    st.plotly_chart(fig, use_container_width=True)
    st.caption("Unavailable is not zero. The UI displays returned scores and does not recompute them.")


def _render_feature_charts(r):
    st.markdown("#### Feature evidence")
    st.caption("Reference and participant have separate clocks; charts are not time-synchronized.")
    ref_series = {s.name: s for s in r.reference_features}
    par_series = {s.name: s for s in r.participant_features}
    view = st.selectbox("Feature view", ["Energy (RMS dBFS)", "Pitch (F0 Hz)"])
    key = "rms_dbfs" if view.startswith("Energy") else "f0_hz"
    c1, c2 = st.columns(2)
    rs = ref_series.get(f"reference_{key}")
    ps = par_series.get(f"participant_{key}")
    if rs:
        c1.plotly_chart(_plot_series(rs, f"Reference — {view}", REF_COLOR), use_container_width=True)
    if ps:
        c2.plotly_chart(_plot_series(ps, f"Participant — {view}", PAR_COLOR), use_container_width=True)

    # Scalar comparison table.
    rows = []
    rmap = {f.name: f for f in r.reference_scalar_features}
    pmap = {f.name: f for f in r.participant_scalar_features}
    for name in rmap:
        rf, pf = rmap[name], pmap.get(name)
        rows.append({
            "feature": name, "unit": rf.unit,
            "reference": rf.value if rf.valid else "unavailable",
            "participant": (pf.value if (pf and pf.valid) else "unavailable"),
        })
    st.dataframe(rows, use_container_width=True, hide_index=True)


def _quality_caption(q):
    if q.Q is None:
        return f"Evidence quality: {q.label.value} (signal: {q.signal_state.value})"
    return (f"Evidence quality: {q.label.value} (Q={q.Q:.2f}; "
            f"A={q.A:.2f} F={q.F:.2f} S={q.S:.2f} M={q.M:.2f}; signal={q.signal_state.value})")


def _render_one_detection(d):
    st.markdown(f"**{d.family.value.replace('_',' ').title()} — {d.participant_start:.2f}–{d.participant_end:.2f} s**")
    st.write(
        f"Participant: `{d.participant_value}` {d.unit} · Reference: `{d.reference_value}` {d.unit} · "
        f"Delta: `{d.delta}` {d.unit}")
    st.write(
        f"Rule: `{d.rule_id}` (threshold {d.threshold} {d.unit}) · "
        f"Exceedance R={d.display_exceedance:.2f} · Severity: {_severity_badge(d.severity.value)}")
    if d.merged_rule_ids:
        st.caption("Also matched rules: " + ", ".join(d.merged_rule_ids))
    st.caption(_quality_caption(d.quality))
    st.write(d.explanation)
    st.caption("⚠️ " + d.caveat)
    st.caption(f"Inspect audio near {d.participant_start:.2f}s (participant) / "
               f"{d.reference_start:.2f}s (reference) using the players above (manual seek).")


def _render_detections(r):
    st.markdown("#### Candidate deviations")
    if r.status == AnalysisStatus.FAILED:
        return
    if not r.detections:
        st.success("No candidate deviations crossed the configured thresholds. "
                   "This does not prove the deliveries are identical.")
        return
    # Group by event_group_id.
    groups, standalone = {}, []
    for d in r.detections:
        if d.event_group_id:
            groups.setdefault(d.event_group_id, []).append(d)
        else:
            standalone.append(d)
    for gid, dets in groups.items():
        with st.container(border=True):
            st.markdown(f"**Related observations** · {len(dets)} families on the same phrase "
                        f"(association, not causation)")
            for d in dets:
                with st.container(border=True):
                    _render_one_detection(d)
    for d in standalone:
        with st.container(border=True):
            _render_one_detection(d)


def _render_exports(r):
    st.markdown("#### Export")
    c1, c2 = st.columns(2)
    has = r.status != AnalysisStatus.FAILED
    c1.download_button("Download analysis JSON", to_json(r),
                       file_name=f"{r.sample_id}_analysis.json", mime="application/json", disabled=not has)
    c2.download_button("Download detections CSV", to_detections_csv(r),
                       file_name=f"{r.sample_id}_detections.csv", mime="text/csv", disabled=not has)


def _render_advanced(r):
    with st.expander("Advanced acoustic diagnostics (MFCC / spectrum)"):
        st.caption("Diagnostic acoustic summaries, not direct flaw labels. "
                   "Brighter/darker colors do not mean better or worse speech.")
        try:
            from vocallens.audio_io import load_audio
            from vocallens.features import mfcc_summary
            cfg = load_analysis_config()
        except Exception as exc:
            st.write(f"Advanced diagnostics unavailable for this recording pair: {exc}")
            return
        which = st.radio("Recording", ["reference", "participant"], horizontal=True, key="mfcc_which")
        meta = r.reference_audio if which == "reference" else r.participant_audio
        if not meta or not meta.filename:
            st.write("Advanced diagnostics unavailable: no audio metadata.")
            return
        st.caption("MFCC view is computed on demand from the analysis sample; see JSON export "
                   "for the full numeric result.")
        st.write("Evidence-quality components legend:")
        st.table([
            {"component": "A", "label": "Alignment coverage", "meaning": "How much of the expected transcript aligned to audio."},
            {"component": "F", "label": "Feature coverage", "meaning": "How much of the selected region had usable feature measurements."},
            {"component": "S", "label": "Signal quality", "meaning": "Whether noise, clipping, channel issues, or limited voicing may affect this measurement."},
            {"component": "M", "label": "Text match", "meaning": "How much of this phrase matched the shared transcript across recordings."},
            {"component": "Q", "label": "Overall evidence quality", "meaning": "A heuristic summary of measurement support—not the probability that the detection is correct."},
        ])


# --------------------------------------------------------------------------- #
# Evaluation screen
# --------------------------------------------------------------------------- #
def render_evaluation():
    st.header("Evaluation")
    latest = sorted(EVAL.glob("evaluation_*_latest.json")) if EVAL.exists() else []
    if not latest:
        st.info("No evaluation results yet.\n\nRun `python scripts/run_evaluation.py` on the "
                "documented held-out set. Metrics will appear here after a successful run.")
        return
    report = json.loads(latest[-1].read_text(encoding="utf-8"))
    st.caption(f"Split: {report['split']} · generated {report['generated_utc']} · "
               f"{report['num_cases']} cases")
    st.warning(report["note"])
    st.markdown("##### Per-family detection metrics")
    st.dataframe([{"family": f, **m} for f, m in report["per_family"].items()],
                 use_container_width=True, hide_index=True)
    st.markdown("##### Runtime by stage (seconds)")
    st.dataframe([{"stage": k, **v} for k, v in report["runtime_by_stage"].items()],
                 use_container_width=True, hide_index=True)
    with st.expander("Per-case detail"):
        st.dataframe(report["cases"], use_container_width=True, hide_index=True)
    st.caption("Command: `python scripts/run_evaluation.py --split test`")


# --------------------------------------------------------------------------- #
# About screen
# --------------------------------------------------------------------------- #
def render_about():
    st.header("About & Reproducibility")
    a_hash, s_hash = _configs_info()
    st.markdown(f"""
**VocalLens** compares a participant recording with a reference recording of the
same English text, localizes measurable differences, and explains them with
evidence. It is a prototype coaching/analysis tool — **not** a judge of ability,
intent, confidence, or emotion. A difference may be intentional or stylistic.

**Methods**
- Independent forced alignment per recording (WhisperX optional); synthetic
  fixtures use ground-truth word boundaries (labeled `provided`).
- Features: word/syllable rate, pauses, pitch variability (semitone IQR),
  within-recording relative energy (dBFS), MFCC diagnostics.
- Phrase-region comparison with mismatch safeguards; normalized exceedance,
  severity bands, and a heuristic evidence-quality index.
- Prototype rubric scoring from `configs/scoring.yaml` (piecewise-linear).

**Versions / provenance**
- analysis config hash: `{a_hash}` · scoring config hash: `{s_hash}`
- See each analysis JSON export for software/model/config versions and timings.

**Dataset** — synthetic pilot (see `data/README.md`): 36 recordings, 6 passages,
split by passage (train 24 / val 6 / test 6). Synthetic, CC0, no human consent
needed. Replace with consented human recordings for a real evaluation.

**Known limitations**
- Synthetic fixtures are tonal, not natural speech — feasibility evidence only.
- Energy-dynamics (relative energy) is the least sensitive family on the pilot
  (held-out recall 0.0; see the Evaluation page). Pitch variation is now caught
  at the whole-utterance scale as well as per phrase. Differences still appear in
  the feature comparison regardless of whether a rule fires.
- WhisperX installs alongside the dashboard (no protobuf/numpy conflict) and the
  adapter runs without ffmpeg, but it pulls a large stack so it stays a separate
  extra (`requirements-align.txt`). Real-speech alignment accuracy is not yet
  verified (no licensed real speech).

**Setup & commands**
```
pip install -r requirements.txt
python scripts/build_dataset_manifest.py
python scripts/validate_dataset.py
python -m pytest -q
python scripts/run_evaluation.py --split test
streamlit run app/streamlit_app.py
```
""")


# --------------------------------------------------------------------------- #
# Shell
# --------------------------------------------------------------------------- #
def main():
    st.sidebar.title("VocalLens")
    st.sidebar.caption("Evidence first; score second.")
    page = st.sidebar.radio("Navigate", ["Analyze", "Evaluation", "About"])
    if page == "Analyze":
        render_analyze()
    elif page == "Evaluation":
        render_evaluation()
    else:
        render_about()


main()
