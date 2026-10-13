"""Deterministic dataset validation (CLAUDE.md §8, Gate A).

Checks required manifest fields, missing audio/annotation files, invalid labels,
duplicate recording IDs, malformed timestamps, inconsistent transcripts, and
train/val/test leakage by passage. Exit code 0 = valid, 1 = problems found.

Run:  python scripts/validate_dataset.py
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Dict, List

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from vocallens.transcript import normalize_transcript  # noqa: E402

DATA = REPO_ROOT / "data"
MANIFEST = DATA / "manifest.csv"
ANNOTATIONS = DATA / "annotations"

REQUIRED_FIELDS = [
    "recording_id", "passage_id", "role", "speaker_id", "variant", "relative_path",
    "transcript_id", "transcript_hash", "intended_flaw_family", "intended_severity",
    "recording_method", "review_status", "license", "consent", "provenance", "split",
]
VALID_ROLES = {"reference", "participant"}
VALID_FAMILIES = {"none", "pace", "pause", "pitch_variation", "energy_dynamics"}
VALID_SEVERITY = {"none", "low", "moderate", "high"}
VALID_SPLITS = {"train", "val", "test"}


def _transcript_hash(text: str) -> str:
    import hashlib

    _, tokens = normalize_transcript(text)
    return hashlib.sha256(" ".join(t.text for t in tokens).encode("utf-8")).hexdigest()[:16]


def validate() -> List[str]:
    errors: List[str] = []
    if not MANIFEST.exists():
        return [f"manifest not found: {MANIFEST}"]

    with MANIFEST.open("r", encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        return ["manifest is empty"]

    # Required fields present.
    for field in REQUIRED_FIELDS:
        if field not in rows[0]:
            errors.append(f"missing required manifest column: {field}")
    if errors:
        return errors

    seen_ids = set()
    passage_to_splits: Dict[str, set] = {}
    transcript_by_passage: Dict[str, str] = {}

    for i, row in enumerate(rows):
        rid = row["recording_id"]
        if rid in seen_ids:
            errors.append(f"duplicate recording_id: {rid}")
        seen_ids.add(rid)

        if row["role"] not in VALID_ROLES:
            errors.append(f"{rid}: invalid role '{row['role']}'")
        if row["intended_flaw_family"] not in VALID_FAMILIES:
            errors.append(f"{rid}: invalid flaw family '{row['intended_flaw_family']}'")
        if row["intended_severity"] not in VALID_SEVERITY:
            errors.append(f"{rid}: invalid severity '{row['intended_severity']}'")
        if row["split"] not in VALID_SPLITS:
            errors.append(f"{rid}: invalid split '{row['split']}'")

        # Audio file present.
        wav = DATA / row["relative_path"]
        if not wav.exists():
            errors.append(f"{rid}: audio file missing: {row['relative_path']}")

        # Annotation present + well formed.
        ann_path = ANNOTATIONS / f"{rid}.json"
        if not ann_path.exists():
            errors.append(f"{rid}: annotation missing: {ann_path.name}")
        else:
            ann = json.loads(ann_path.read_text(encoding="utf-8"))
            last_end = -1.0
            for w in ann.get("word_timings", []):
                s, e = w.get("start"), w.get("end")
                if s is None or e is None or s > e or s < 0:
                    errors.append(f"{rid}: malformed word timing {w}")
                    continue
                if s + 1e-6 < last_end - 1e-6:
                    errors.append(f"{rid}: non-monotonic word timings near '{w.get('text')}'")
                last_end = e
            for fl in ann.get("flaw_intervals", []):
                if fl.get("start") is None or fl.get("end") is None or fl["start"] > fl["end"]:
                    errors.append(f"{rid}: malformed flaw interval {fl}")
                if fl.get("family") not in VALID_FAMILIES:
                    errors.append(f"{rid}: invalid flaw family in annotation {fl.get('family')}")
            # Transcript hash consistency.
            if _transcript_hash(ann.get("transcript", "")) != row["transcript_hash"]:
                errors.append(f"{rid}: transcript hash mismatch between manifest and annotation")

        # Transcript consistency within a passage.
        pid = row["passage_id"]
        if pid in transcript_by_passage:
            if transcript_by_passage[pid] != row["transcript_hash"]:
                errors.append(f"passage {pid}: inconsistent transcript hashes across recordings")
        else:
            transcript_by_passage[pid] = row["transcript_hash"]

        passage_to_splits.setdefault(pid, set()).add(row["split"])

    # Leakage: a passage must live in exactly one split.
    for pid, splits in passage_to_splits.items():
        if len(splits) > 1:
            errors.append(f"split leakage: passage {pid} appears in splits {sorted(splits)}")

    return errors


def main() -> int:
    errors = validate()
    if errors:
        print(f"DATASET VALIDATION: FAIL ({len(errors)} problem(s))")
        for e in errors:
            print("  -", e)
        return 1
    with MANIFEST.open("r", encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    splits: Dict[str, int] = {}
    for r in rows:
        splits[r["split"]] = splits.get(r["split"], 0) + 1
    print(f"DATASET VALIDATION: PASS - {len(rows)} recordings, splits {splits}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
