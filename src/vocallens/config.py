"""Configuration loading and validation for VocalLens.

Configs are validated on load; invalid or unknown values are rejected rather
than silently ignored (CLAUDE.md §3). The canonical values live in
``configs/analysis.yaml`` and ``configs/scoring.yaml`` (ARCHITECTURE.md §8.9/§9).
Numerical constants must come from here, never be duplicated in code.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Dict, List, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# Repo root = two levels up from this file (src/vocallens/config.py).
REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = REPO_ROOT / "configs"
DEFAULT_ANALYSIS_CONFIG = CONFIG_DIR / "analysis.yaml"
DEFAULT_SCORING_CONFIG = CONFIG_DIR / "scoring.yaml"


class _Strict(BaseModel):
    """Base model that forbids unknown keys so stray config settings are errors."""

    model_config = ConfigDict(extra="forbid")


# --------------------------------------------------------------------------- #
# analysis.yaml
# --------------------------------------------------------------------------- #
class AudioConfig(_Strict):
    analysis_sample_rate_hz: int = Field(gt=0)
    mono_policy: Literal["mean_channels"]
    max_upload_mb: float = Field(gt=0)
    min_duration_seconds: float = Field(gt=0)
    max_duration_seconds: float = Field(gt=0)
    clipping_peak_threshold: float = Field(gt=0, le=1.0)

    @model_validator(mode="after")
    def _check_durations(self) -> "AudioConfig":
        if self.max_duration_seconds <= self.min_duration_seconds:
            raise ValueError("audio.max_duration_seconds must exceed min_duration_seconds")
        return self


class SnrThresholds(_Strict):
    minor_warning_below: float
    limited_below: float
    poor_below: float

    @model_validator(mode="after")
    def _ordered(self) -> "SnrThresholds":
        if not (self.minor_warning_below > self.limited_below > self.poor_below):
            raise ValueError("SNR cutoffs must be strictly decreasing: minor > limited > poor")
        return self


class ClippingThresholds(_Strict):
    minor_warning_at_or_above: float = Field(ge=0)
    limited_at_or_above: float = Field(ge=0)
    poor_at_or_above: float = Field(ge=0)

    @model_validator(mode="after")
    def _ordered(self) -> "ClippingThresholds":
        if not (self.minor_warning_at_or_above < self.limited_at_or_above < self.poor_at_or_above):
            raise ValueError("clipping cutoffs must be strictly increasing")
        return self


class ChannelImbalanceThresholds(_Strict):
    minor_warning_at_or_above: float = Field(ge=0)
    limited_at_or_above: float = Field(ge=0)

    @model_validator(mode="after")
    def _ordered(self) -> "ChannelImbalanceThresholds":
        if self.minor_warning_at_or_above >= self.limited_at_or_above:
            raise ValueError("channel imbalance: minor cutoff must be below limited cutoff")
        return self


class SignalQualityConfig(_Strict):
    estimated_snr_db: SnrThresholds
    clipping_fraction: ClippingThresholds
    channel_rms_imbalance_db: ChannelImbalanceThresholds
    poor_speech_coverage_fraction_of_minimum: float = Field(gt=0, le=1.0)


class FramingConfig(_Strict):
    frame_length_ms: float = Field(gt=0)
    hop_length_ms: float = Field(gt=0)
    rms_floor_dbfs: float = Field(lt=0)

    @model_validator(mode="after")
    def _hop_le_frame(self) -> "FramingConfig":
        if self.hop_length_ms > self.frame_length_ms:
            raise ValueError("framing.hop_length_ms must not exceed frame_length_ms")
        return self


class PauseDetectionConfig(_Strict):
    noise_floor_percentile: float = Field(ge=0, le=100)
    noise_floor_relative_margin_db: float = Field(ge=0)
    absolute_silence_ceiling_dbfs: float = Field(lt=0)
    min_pause_duration_ms: float = Field(gt=0)
    merge_gap_ms: float = Field(ge=0)
    min_noise_frames: int = Field(gt=0)


class AlignmentConfig(_Strict):
    primary: str
    fallback: str
    feasibility_time_budget_minutes: float = Field(gt=0)
    min_aligned_token_coverage: float = Field(ge=0, le=1.0)
    max_transcript_mismatch_ratio: float = Field(ge=0, le=1.0)


class FeaturesConfig(_Strict):
    min_voiced_frame_coverage: float = Field(ge=0, le=1.0)
    min_speech_frame_coverage: float = Field(ge=0, le=1.0)
    energy_iqr_floor_db: float = Field(gt=0)
    pitch_variability_metric: Literal["iqr_semitones"]
    syllable_counter: Literal["pronouncing_cmudict"]


class RuleThreshold(_Strict):
    unit: str
    value: float


class DetectionConfig(_Strict):
    same_family_merge_iou: float = Field(ge=0, le=1.0)
    merge_gap_ms: float = Field(ge=0)
    severity_low_upper_ratio: float = Field(gt=1.0)
    severity_moderate_upper_ratio: float = Field(gt=1.0)
    threshold_epsilon: float = Field(gt=0)
    display_exceedance_cap: float = Field(gt=0)
    thresholds: Dict[str, RuleThreshold]

    @model_validator(mode="after")
    def _check(self) -> "DetectionConfig":
        if self.severity_moderate_upper_ratio <= self.severity_low_upper_ratio:
            raise ValueError("severity_moderate_upper_ratio must exceed severity_low_upper_ratio")
        for name, thr in self.thresholds.items():
            # T must be finite and strictly greater than epsilon (ARCHITECTURE §8.6).
            if not (thr.value > self.threshold_epsilon):
                raise ValueError(
                    f"detection threshold '{name}' value {thr.value} must be > threshold_epsilon "
                    f"{self.threshold_epsilon}"
                )
        return self


class SignalStateScores(_Strict):
    signal_ok: float
    signal_minor_warning: float
    signal_limited: float
    signal_poor: float
    signal_invalid: float


class QualityConfig(_Strict):
    high_threshold: float = Field(ge=0, le=1.0)
    medium_threshold: float = Field(ge=0, le=1.0)
    alignment_weight: float = Field(ge=0)
    feature_coverage_weight: float = Field(ge=0)
    signal_quality_weight: float = Field(ge=0)
    mapping_weight: float = Field(ge=0)
    signal_state_scores: SignalStateScores
    signal_warning_codes: List[str]

    @model_validator(mode="after")
    def _check(self) -> "QualityConfig":
        if self.medium_threshold >= self.high_threshold:
            raise ValueError("quality.medium_threshold must be below high_threshold")
        total = (
            self.alignment_weight
            + self.feature_coverage_weight
            + self.signal_quality_weight
            + self.mapping_weight
        )
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"quality A/F/S/M weights must sum to 1.0 (got {total})")
        return self


class PerformanceConfig(_Strict):
    report_stage_timings: bool
    alignment_timeout_seconds: float = Field(gt=0)


class AnalysisConfig(_Strict):
    schema_version: int
    language: str
    audio: AudioConfig
    signal_quality: SignalQualityConfig
    framing: FramingConfig
    pause_detection: PauseDetectionConfig
    alignment: AlignmentConfig
    features: FeaturesConfig
    detection: DetectionConfig
    quality: QualityConfig
    performance: PerformanceConfig

    # Raw dict + hash retained for provenance (config hash in AnalysisResult).
    _raw: Dict[str, Any] = {}
    _config_hash: str = ""

    @property
    def config_hash(self) -> str:
        return self._config_hash


# --------------------------------------------------------------------------- #
# scoring.yaml
# --------------------------------------------------------------------------- #
class ScoreScale(_Strict):
    minimum: float
    maximum: float

    @model_validator(mode="after")
    def _ordered(self) -> "ScoreScale":
        if self.maximum <= self.minimum:
            raise ValueError("score_scale.maximum must exceed minimum")
        return self


class Anchor(_Strict):
    exceedance: float = Field(ge=0)
    score: float


class DimensionScoreConfig(_Strict):
    weight: float = Field(ge=0)
    transform: Literal["piecewise_linear"]
    input: Literal["aggregate_normalized_exceedance"]
    anchors: List[Anchor]

    @model_validator(mode="after")
    def _check_anchors(self) -> "DimensionScoreConfig":
        if len(self.anchors) < 2:
            raise ValueError("each dimension needs at least two anchors")
        exc = [a.exceedance for a in self.anchors]
        sc = [a.score for a in self.anchors]
        if any(exc[i] >= exc[i + 1] for i in range(len(exc) - 1)):
            raise ValueError("anchor exceedance values must be strictly increasing")
        if any(sc[i] < sc[i + 1] for i in range(len(sc) - 1)):
            raise ValueError("anchor scores must be non-increasing with exceedance")
        return self


class ScoringAggregation(_Strict):
    dimension_exceedance: Literal["median_valid_rule_exceedance"]
    clamp_exceedance_min: float = Field(ge=0)
    missing_rule_policy: Literal["exclude"]
    min_valid_rules_per_dimension: int = Field(ge=1)
    overall_min_valid_dimensions: int = Field(ge=1)
    renormalize_weights_over_valid_dimensions: bool
    round_display_decimals: int = Field(ge=0)


class ScoringConfig(_Strict):
    schema_version: int
    score_scale: ScoreScale
    dimensions: Dict[str, DimensionScoreConfig]
    aggregation: ScoringAggregation

    _raw: Dict[str, Any] = {}
    _config_hash: str = ""

    @property
    def config_hash(self) -> str:
        return self._config_hash

    @model_validator(mode="after")
    def _check(self) -> "ScoringConfig":
        if self.aggregation.overall_min_valid_dimensions > len(self.dimensions):
            raise ValueError(
                "overall_min_valid_dimensions exceeds the number of configured dimensions "
                "(requirement is unsatisfiable)"
            )
        for name, dim in self.dimensions.items():
            for a in dim.anchors:
                if not (self.score_scale.minimum <= a.score <= self.score_scale.maximum):
                    raise ValueError(
                        f"dimension '{name}' anchor score {a.score} outside score_scale"
                    )
        return self


# --------------------------------------------------------------------------- #
# Loaders
# --------------------------------------------------------------------------- #
def _hash_mapping(data: Dict[str, Any]) -> str:
    """Stable content hash of a config mapping (sorted keys)."""
    blob = yaml.safe_dump(data, sort_keys=True).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


def _read_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"Config {path} must be a mapping at top level")
    return data


def load_analysis_config(path: str | Path | None = None) -> AnalysisConfig:
    """Load and validate ``analysis.yaml``. Raises on invalid/unknown values."""
    p = Path(path) if path is not None else DEFAULT_ANALYSIS_CONFIG
    raw = _read_yaml(p)
    cfg = AnalysisConfig.model_validate(raw)
    object.__setattr__(cfg, "_raw", raw)
    object.__setattr__(cfg, "_config_hash", _hash_mapping(raw))
    return cfg


def load_scoring_config(path: str | Path | None = None) -> ScoringConfig:
    """Load and validate ``scoring.yaml``. Raises on invalid/unknown values."""
    p = Path(path) if path is not None else DEFAULT_SCORING_CONFIG
    raw = _read_yaml(p)
    cfg = ScoringConfig.model_validate(raw)
    object.__setattr__(cfg, "_raw", raw)
    object.__setattr__(cfg, "_config_hash", _hash_mapping(raw))
    return cfg
