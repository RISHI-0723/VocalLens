"""Run a small held-out evaluation and save ACTUAL measured results.

Pairs each flawed variant in the chosen split with its passage reference, runs
the real pipeline (provided ground-truth alignment for the synthetic fixtures),
and measures per-family detection precision/recall/F1, temporal overlap (IoU)
against intended flaw intervals, alignment coverage, and stage runtime.

This is a SMALL PILOT on SYNTHETIC fixtures — feasibility evidence only, not
evidence of generalization to real speech. Thresholds are NOT tuned here.

Run:  python scripts/run_evaluation.py [--split test]
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from vocallens.pipeline import analyze_pair  # noqa: E402
from vocallens.schemas import AnalysisRequest  # noqa: E402

DATA = REPO_ROOT / "data"
ANN = DATA / "annotations"
OUT = REPO_ROOT / "reports" / "evaluation"


def _iou(a0, a1, b0, b1):
    inter = max(0.0, min(a1, b1) - max(a0, b0))
    union = (a1 - a0) + (b1 - b0) - inter
    return inter / union if union > 0 else 0.0


def _load_ann(rid):
    return json.loads((ANN / f"{rid}.json").read_text(encoding="utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="test")
    args = ap.parse_args()

    with (DATA / "manifest.csv").open(encoding="utf-8", newline="") as fh:
        rows = [r for r in csv.DictReader(fh) if r["split"] == args.split]
    if not rows:
        print(f"No recordings in split '{args.split}'. Build the dataset first.")
        return 1

    # Map passage -> reference recording and participant variants.
    by_passage = defaultdict(list)
    references = {}
    for r in rows:
        if r["variant"] == "reference":
            references[r["passage_id"]] = r
        else:
            by_passage[r["passage_id"]].append(r)

    cases = []
    fam_tp = defaultdict(int)
    fam_fp = defaultdict(int)
    fam_fn = defaultdict(int)
    stage_times = defaultdict(list)

    for pid, variants in by_passage.items():
        ref = references.get(pid)
        if not ref:
            continue
        ref_ann = _load_ann(ref["recording_id"])
        for v in variants:
            v_ann = _load_ann(v["recording_id"])
            req = AnalysisRequest(
                reference_audio=str(DATA / ref["relative_path"]),
                participant_audio=str(DATA / v["relative_path"]),
                transcript=v_ann["transcript"], sample_id=v["recording_id"],
                alignment_backend="provided",
                reference_provided_words=ref_ann["word_timings"],
                participant_provided_words=v_ann["word_timings"])
            res = analyze_pair(req)
            for k, t in res.stage_timings.timings_seconds.items():
                stage_times[k].append(t)

            intended = v["intended_flaw_family"]
            detected_fams = {d.family.value for d in res.detections}
            # Temporal overlap for detections matching the intended family.
            best_iou = 0.0
            for d in res.detections:
                if d.family.value == intended:
                    for fl in v_ann["flaw_intervals"]:
                        best_iou = max(best_iou, _iou(d.participant_start, d.participant_end,
                                                      fl["start"], fl["end"]))

            if intended in detected_fams:
                fam_tp[intended] += 1
            else:
                fam_fn[intended] += 1
            for f in detected_fams:
                if f != intended:
                    fam_fp[f] += 1

            cases.append({
                "recording_id": v["recording_id"], "intended_family": intended,
                "detected_families": sorted(detected_fams),
                "num_detections": len(res.detections),
                "best_temporal_iou_for_intended": round(best_iou, 3),
                "status": res.status.value,
                "ref_alignment_coverage": res.reference_alignment.coverage,
                "par_alignment_coverage": res.participant_alignment.coverage,
                "overall_score": res.scores.overall_display_score,
            })

        # Reference-vs-itself: any detection is a false positive.
        ref_ann = _load_ann(ref["recording_id"])
        req = AnalysisRequest(
            reference_audio=str(DATA / ref["relative_path"]),
            participant_audio=str(DATA / ref["relative_path"]),
            transcript=ref_ann["transcript"], sample_id=ref["recording_id"] + "_self",
            alignment_backend="provided",
            reference_provided_words=ref_ann["word_timings"],
            participant_provided_words=ref_ann["word_timings"])
        res = analyze_pair(req)
        for d in res.detections:
            fam_fp[d.family.value] += 1
        cases.append({
            "recording_id": ref["recording_id"] + "_self", "intended_family": "none",
            "detected_families": sorted({d.family.value for d in res.detections}),
            "num_detections": len(res.detections), "best_temporal_iou_for_intended": None,
            "status": res.status.value,
            "ref_alignment_coverage": res.reference_alignment.coverage,
            "par_alignment_coverage": res.participant_alignment.coverage,
            "overall_score": res.scores.overall_display_score,
        })

    families = ["pace", "pause", "pitch_variation", "energy_dynamics"]
    per_family = {}
    for f in families:
        tp, fp, fn = fam_tp[f], fam_fp[f], fam_fn[f]
        prec = tp / (tp + fp) if (tp + fp) else None
        rec = tp / (tp + fn) if (tp + fn) else None
        f1 = (2 * prec * rec / (prec + rec)) if (prec and rec) else None
        per_family[f] = {"tp": tp, "fp": fp, "fn": fn,
                         "precision": round(prec, 3) if prec is not None else None,
                         "recall": round(rec, 3) if rec is not None else None,
                         "f1": round(f1, 3) if f1 is not None else None}

    runtime = {k: {"mean_s": round(sum(v) / len(v), 4), "max_s": round(max(v), 4), "n": len(v)}
               for k, v in stage_times.items()}

    report = {
        "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "split": args.split,
        "is_synthetic_pilot": True,
        "note": ("Feasibility pilot on synthetic tonal fixtures; NOT evidence of "
                 "generalization to real speech. Thresholds were not tuned on this set."),
        "num_cases": len(cases),
        "per_family": per_family,
        "runtime_by_stage": runtime,
        "cases": cases,
    }

    OUT.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = OUT / f"evaluation_{args.split}_{stamp}.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    latest = OUT / f"evaluation_{args.split}_latest.json"
    latest.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"Evaluation ({args.split}): {len(cases)} cases")
    for f, m in per_family.items():
        print(f"  {f:16s} P={m['precision']} R={m['recall']} F1={m['f1']} (tp={m['tp']} fp={m['fp']} fn={m['fn']})")
    print(f"Report: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
