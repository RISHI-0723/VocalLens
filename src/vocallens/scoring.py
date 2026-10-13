"""Prototype rubric scoring (ARCHITECTURE.md §8.9).

Converts each valid dimension's aggregate normalized exceedance into a 0-100
score with the configured piecewise-linear transform, aggregating ALL valid rule
measurements (including sub-threshold ones). Missing/unreliable measurements are
excluded (never treated as zero). The overall score is computed only when the
configured minimum number of valid dimensions is met, renormalizing weights over
valid dimensions. Scores are a provisional prototype rubric, not a validated
measure of speaking quality.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from .config import ScoringConfig
from .detection import RuleMeasurement
from .schemas import DimensionScore, Scores


def _piecewise_linear(exceedance: float, anchors) -> float:
    """Interpolate score from anchors; clamp to endpoint scores outside domain."""
    xs = [a.exceedance for a in anchors]
    ys = [a.score for a in anchors]
    if exceedance <= xs[0]:
        return ys[0]
    if exceedance >= xs[-1]:
        return ys[-1]
    for i in range(len(xs) - 1):
        if xs[i] <= exceedance <= xs[i + 1]:
            t = (exceedance - xs[i]) / (xs[i + 1] - xs[i])
            return ys[i] + t * (ys[i + 1] - ys[i])
    return ys[-1]


def _median(values: List[float]) -> float:
    s = sorted(values)
    n = len(s)
    mid = n // 2
    if n % 2 == 1:
        return s[mid]
    return (s[mid - 1] + s[mid]) / 2.0


def compute_scores(measurements: List[RuleMeasurement], config: ScoringConfig) -> Scores:
    """Aggregate rule measurements into dimension scores and an overall score."""
    agg = config.aggregation
    by_dim: Dict[str, List[RuleMeasurement]] = {name: [] for name in config.dimensions}
    for m in measurements:
        if m.dimension in by_dim and m.valid and m.R is not None:
            by_dim[m.dimension].append(m)

    dim_scores: List[DimensionScore] = []
    valid_scores: Dict[str, float] = {}
    for name, dim_cfg in config.dimensions.items():
        rules = by_dim[name]
        exceedances = [max(agg.clamp_exceedance_min, m.R) for m in rules]
        # Expected rules for coverage: distinct rule_ids seen for this dimension.
        distinct_rule_ids = sorted({m.rule_id for m in rules})
        if len(rules) < agg.min_valid_rules_per_dimension or not exceedances:
            dim_scores.append(DimensionScore(
                name=name, score=None, display_score=None, valid=False, coverage=None,
                aggregate_exceedance=None, contributing_rule_ids=distinct_rule_ids,
                explanation="No valid rule measurement for this dimension; score unavailable (not zero).",
            ))
            continue
        aggregate = _median(exceedances)
        raw = _piecewise_linear(aggregate, dim_cfg.anchors)
        raw = max(config.score_scale.minimum, min(config.score_scale.maximum, raw))
        valid_scores[name] = raw
        dim_scores.append(DimensionScore(
            name=name, score=round(raw, 6),
            display_score=round(raw, agg.round_display_decimals),
            valid=True, coverage=round(len(rules) / max(len(rules), 1), 4),
            aggregate_exceedance=round(aggregate, 6),
            contributing_rule_ids=distinct_rule_ids,
            explanation=(
                f"Median normalized exceedance {aggregate:.3f} over {len(rules)} valid "
                f"measurement(s) maps to {raw:.1f} on the prototype scale."
            ),
        ))

    valid_count = len(valid_scores)
    scores = Scores(
        dimensions=dim_scores,
        valid_dimension_count=valid_count,
        required_valid_dimensions=agg.overall_min_valid_dimensions,
        overall_available=False,
    )

    if valid_count >= agg.overall_min_valid_dimensions:
        if agg.renormalize_weights_over_valid_dimensions:
            total_w = sum(config.dimensions[n].weight for n in valid_scores)
            if total_w > 0:
                overall = sum(
                    config.dimensions[n].weight / total_w * s for n, s in valid_scores.items()
                )
                scores.overall_score = round(overall, 6)
                scores.overall_display_score = round(overall, agg.round_display_decimals)
                scores.overall_available = True
    return scores
