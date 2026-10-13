"""Typed data contracts for VocalLens (ARCHITECTURE.md §7).

These Pydantic models define ``AnalysisRequest`` and the validated
``AnalysisResult`` returned by :func:`vocallens.pipeline.analyze_pair`. They are
the single source of truth for serialization; the dashboard, evaluation script,
and exporters all consume these objects.

Conventions:
- Timestamps are in **seconds**.
- Missing/unreliable measurements are ``None`` (unavailable), never ``0``.
- Every feature value carries a unit and validity information.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from . import SCHEMA_VERSION


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --------------------------------------------------------------------------- #
# Enumerations
# --------------------------------------------------------------------------- #
class AnalysisStatus(str, Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    FAILED = "failed"


class AlignmentStatus(str, Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"
    TIMED_OUT = "timed_out"
    FAILED = "failed"


class Severity(str, Enum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    UNAVAILABLE = "unavailable"


class QualityLabel(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNAVAILABLE = "unavailable"


class SignalState(str, Enum):
    OK = "signal_ok"
    MINOR_WARNING = "signal_minor_warning"
    LIMITED = "signal_limited"
    POOR = "signal_poor"
    INVALID = "signal_invalid"


class DetectionFamily(str, Enum):
    PACE = "pace"
    PAUSE = "pause"
    PITCH_VARIATION = "pitch_variation"
    ENERGY_DYNAMICS = "energy_dynamics"


class ReviewStatus(str, Enum):
    AUTOMATIC = "automatic"
    HUMAN_REVIEWED = "human_reviewed"


# --------------------------------------------------------------------------- #
# Shared value objects
# --------------------------------------------------------------------------- #
class Warning(_Model):
    code: str
    message: str


class AudioMetadata(_Model):
    role: str  # "reference" | "participant"
    original_sample_rate_hz: Optional[int] = None
    channels: Optional[int] = None
    duration_seconds: Optional[float] = None
    peak_amplitude: Optional[float] = None
    clipping_detected: Optional[bool] = None
    clipping_fraction: Optional[float] = None
    analysis_sample_rate_hz: Optional[int] = None
    filename: Optional[str] = None  # display-only; never a private absolute path


class Token(_Model):
    index: int
    text: str  # normalized token
    original: str  # original surface form
    char_start: Optional[int] = None
    char_end: Optional[int] = None


class WordTiming(_Model):
    token_index: int
    text: str
    start: float
    end: float
    score: Optional[float] = None  # aligner confidence if provided


class AlignmentResultModel(_Model):
    role: str
    backend: str  # e.g. "whisperx", "provided", "unavailable"
    model: Optional[str] = None
    language: str
    status: AlignmentStatus
    words: List[WordTiming] = Field(default_factory=list)
    aligned_token_count: int = 0
    expected_token_count: int = 0
    coverage: Optional[float] = None  # aligned_token_count / expected_token_count
    warnings: List[Warning] = Field(default_factory=list)
    failure_reason: Optional[str] = None
    duration_seconds: Optional[float] = None


class MappedPhrase(_Model):
    """A phrase window mapped across both recordings for comparison."""

    phrase_id: str
    token_indices: List[int]
    text: str
    reference_start: Optional[float] = None
    reference_end: Optional[float] = None
    participant_start: Optional[float] = None
    participant_end: Optional[float] = None
    matched_fraction: float  # fraction of expected tokens matched & aligned
    eligible: bool  # >= configured min for comparison


class RegionMappingModel(_Model):
    status: str  # "complete" | "partial" | "unavailable"
    mismatch_ratio: Optional[float] = None
    edit_distance: Optional[int] = None
    matched_tokens: int = 0
    missing_tokens: int = 0
    inserted_tokens: int = 0
    unmapped_tokens: int = 0
    phrases: List[MappedPhrase] = Field(default_factory=list)
    warnings: List[Warning] = Field(default_factory=list)


class FeatureSeries(_Model):
    """A timestamped feature series for one recording."""

    name: str
    unit: str
    times: List[float] = Field(default_factory=list)
    values: List[Optional[float]] = Field(default_factory=list)
    valid_mask: List[bool] = Field(default_factory=list)
    settings: Dict[str, Any] = Field(default_factory=dict)


class ScalarFeature(_Model):
    name: str
    value: Optional[float]
    unit: str
    valid: bool
    coverage: Optional[float] = None
    warnings: List[Warning] = Field(default_factory=list)


class QualityComponents(_Model):
    """Evidence-quality components (ARCHITECTURE.md §8.7)."""

    A: Optional[float] = None  # alignment coverage
    F: Optional[float] = None  # feature coverage
    S: Optional[float] = None  # signal-quality component score
    M: Optional[float] = None  # text match
    signal_state: SignalState = SignalState.INVALID
    Q: Optional[float] = None
    label: QualityLabel = QualityLabel.UNAVAILABLE
    warnings: List[Warning] = Field(default_factory=list)


class Detection(_Model):
    """A single candidate deviation (ARCHITECTURE.md §7 detection record)."""

    detection_id: str
    family: DetectionFamily
    rule_id: str
    event_group_id: Optional[str] = None
    merged_rule_ids: List[str] = Field(default_factory=list)

    participant_start: float
    participant_end: float
    reference_start: Optional[float] = None
    reference_end: Optional[float] = None
    matched_phrase_id: Optional[str] = None
    matched_reference_text: Optional[str] = None

    feature_name: str
    participant_value: Optional[float]
    reference_value: Optional[float]
    delta: Optional[float]
    unit: str

    threshold: float
    normalized_exceedance: float  # R = D / T (uncapped; for audit/severity)
    display_exceedance: float  # capped at configured maximum
    severity: Severity

    quality: QualityComponents
    explanation: str
    caveat: str
    review_status: ReviewStatus = ReviewStatus.AUTOMATIC


class DimensionScore(_Model):
    name: str
    score: Optional[float]  # unrounded; None = unavailable (never 0 for missing)
    display_score: Optional[float] = None  # rounded for display
    valid: bool
    coverage: Optional[float] = None  # valid rules / expected rules
    aggregate_exceedance: Optional[float] = None
    contributing_rule_ids: List[str] = Field(default_factory=list)
    explanation: str = ""


class Scores(_Model):
    dimensions: List[DimensionScore] = Field(default_factory=list)
    overall_score: Optional[float] = None  # unrounded
    overall_display_score: Optional[float] = None
    valid_dimension_count: int = 0
    required_valid_dimensions: int = 0
    overall_available: bool = False
    label: str = "prototype rubric score"
    note: str = (
        "Prototype rubric score; provisional transform, not a validated measure "
        "of speaking quality."
    )


class Provenance(_Model):
    software_version: Optional[str] = None
    python_version: Optional[str] = None
    schema_version: int = SCHEMA_VERSION
    analysis_config_hash: Optional[str] = None
    scoring_config_hash: Optional[str] = None
    alignment_backend: Optional[str] = None
    alignment_model: Optional[str] = None
    package_versions: Dict[str, str] = Field(default_factory=dict)
    created_utc: Optional[str] = None


class StageTimings(_Model):
    timings_seconds: Dict[str, float] = Field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Request and result
# --------------------------------------------------------------------------- #
class AnalysisRequest(_Model):
    """Input to :func:`analyze_pair`.

    Audio may be a filesystem path (str) OR provided alignment can be supplied
    for synthetic fixtures with known word boundaries via ``*_provided_words``.
    """

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    reference_audio: str
    participant_audio: str
    transcript: str
    language: str = "en-US"
    sample_id: str = "sample"
    metadata: Dict[str, Any] = Field(default_factory=dict)

    # Optional ground-truth/oracle word timings for synthetic fixtures. These are
    # word boundaries KNOWN BY CONSTRUCTION, not forced-alignment output; when
    # present they route through the alignment "provided" backend and are clearly
    # labeled as such. Each entry: {"text", "start", "end"}.
    reference_provided_words: Optional[List[Dict[str, Any]]] = None
    participant_provided_words: Optional[List[Dict[str, Any]]] = None
    # Force a particular alignment backend ("whisperx", "provided", "auto").
    alignment_backend: str = "auto"


class AnalysisResult(_Model):
    schema_version: int = SCHEMA_VERSION
    sample_id: str
    status: AnalysisStatus

    warnings: List[Warning] = Field(default_factory=list)
    transcript_original: str = ""
    tokens: List[Token] = Field(default_factory=list)

    reference_audio: Optional[AudioMetadata] = None
    participant_audio: Optional[AudioMetadata] = None

    reference_alignment: Optional[AlignmentResultModel] = None
    participant_alignment: Optional[AlignmentResultModel] = None
    region_mapping: Optional[RegionMappingModel] = None

    reference_features: List[FeatureSeries] = Field(default_factory=list)
    participant_features: List[FeatureSeries] = Field(default_factory=list)
    reference_scalar_features: List[ScalarFeature] = Field(default_factory=list)
    participant_scalar_features: List[ScalarFeature] = Field(default_factory=list)

    detections: List[Detection] = Field(default_factory=list)
    scores: Scores = Field(default_factory=Scores)

    provenance: Provenance = Field(default_factory=Provenance)
    stage_timings: StageTimings = Field(default_factory=StageTimings)

    failure_reason: Optional[str] = None

    def to_json(self, indent: int = 2) -> str:
        return self.model_dump_json(indent=indent)

    @classmethod
    def from_json(cls, data: str) -> "AnalysisResult":
        return cls.model_validate_json(data)
