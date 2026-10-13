"""Versioned exports (ARCHITECTURE.md §8.10).

JSON carries the complete analysis + provenance. The detections CSV has one row
per grouped detection with stable field names and a schema version. Partial
status and warnings are preserved in both.
"""
from __future__ import annotations

import csv
import io
from typing import List

from .schemas import AnalysisResult, Detection

CSV_COLUMNS = [
    "schema_version", "sample_id", "detection_id", "family", "rule_id",
    "merged_rule_ids", "event_group_id",
    "participant_start", "participant_end", "reference_start", "reference_end",
    "matched_phrase_id", "matched_reference_text",
    "feature_name", "participant_value", "reference_value", "delta", "unit",
    "threshold", "normalized_exceedance", "display_exceedance", "severity",
    "evidence_quality_score", "evidence_quality_label",
    "quality_A", "quality_F", "quality_S", "quality_M", "signal_state",
    "explanation", "caveat", "review_status",
]


def to_json(result: AnalysisResult, indent: int = 2) -> str:
    return result.to_json(indent=indent)


def _detection_row(result: AnalysisResult, d: Detection) -> dict:
    q = d.quality
    return {
        "schema_version": result.schema_version,
        "sample_id": result.sample_id,
        "detection_id": d.detection_id,
        "family": d.family.value,
        "rule_id": d.rule_id,
        "merged_rule_ids": "|".join(d.merged_rule_ids),
        "event_group_id": d.event_group_id or "",
        "participant_start": d.participant_start,
        "participant_end": d.participant_end,
        "reference_start": d.reference_start,
        "reference_end": d.reference_end,
        "matched_phrase_id": d.matched_phrase_id or "",
        "matched_reference_text": d.matched_reference_text or "",
        "feature_name": d.feature_name,
        "participant_value": d.participant_value,
        "reference_value": d.reference_value,
        "delta": d.delta,
        "unit": d.unit,
        "threshold": d.threshold,
        "normalized_exceedance": d.normalized_exceedance,
        "display_exceedance": d.display_exceedance,
        "severity": d.severity.value,
        "evidence_quality_score": "" if q.Q is None else q.Q,
        "evidence_quality_label": q.label.value,
        "quality_A": "" if q.A is None else round(q.A, 4),
        "quality_F": "" if q.F is None else round(q.F, 4),
        "quality_S": "" if q.S is None else round(q.S, 4),
        "quality_M": "" if q.M is None else round(q.M, 4),
        "signal_state": q.signal_state.value,
        "explanation": d.explanation,
        "caveat": d.caveat,
        "review_status": d.review_status.value,
    }


def to_detections_csv(result: AnalysisResult) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=CSV_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for d in result.detections:
        writer.writerow(_detection_row(result, d))
    return buf.getvalue()
