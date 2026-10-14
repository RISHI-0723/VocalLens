// Types mirroring the FastAPI responses, which in turn carry the engine's own
// AnalysisResult JSON schema (schema_version 1). Unavailable values are null.

export interface SampleVariant {
  variant: string;
  recording_id: string;
  role: string;
  intended_flaw_family: string;
  intended_severity: string;
}
export interface SamplePassage {
  passage_id: string;
  transcript: string;
  reference_id: string | null;
  split: string;
  variants: SampleVariant[];
}

export interface Quality {
  A: number | null;
  F: number | null;
  S: number | null;
  M: number | null;
  Q: number | null;
  label: string;
  signal_state: string;
  warnings: { code: string; message: string }[];
}
export interface Detection {
  detection_id: string;
  family: string;
  rule_id: string;
  event_group_id: string | null;
  merged_rule_ids: string[];
  participant_start: number;
  participant_end: number;
  reference_start: number;
  reference_end: number;
  matched_reference_text: string | null;
  feature_name: string;
  participant_value: number | null;
  reference_value: number | null;
  delta: number | null;
  unit: string;
  threshold: number;
  normalized_exceedance: number;
  display_exceedance: number;
  severity: string;
  quality: Quality;
  explanation: string;
  caveat: string;
}
export interface DimensionScore {
  name: string;
  score: number | null;
  display_score: number | null;
  valid: boolean;
  aggregate_exceedance: number | null;
  explanation: string;
}
export interface Scores {
  dimensions: DimensionScore[];
  overall_score: number | null;
  overall_display_score: number | null;
  valid_dimension_count: number;
  required_valid_dimensions: number;
  overall_available: boolean;
  note: string | null;
}
export interface FeatureSeries {
  name: string;
  unit: string;
  times: number[];
  values: (number | null)[];
  valid_mask: boolean[];
}
export interface ScalarFeature {
  name: string;
  value: number | null;
  unit: string;
  valid: boolean;
  coverage?: number | null;
}
export interface Alignment {
  role: string;
  backend: string;
  status: string;
  coverage: number | null;
  aligned_token_count: number;
  expected_token_count: number;
}
export interface AudioMeta {
  role: string;
  duration_seconds: number;
  channels: number;
  original_sample_rate_hz: number;
  analysis_sample_rate_hz: number;
  filename: string | null;
}
export interface Warning {
  code: string;
  message: string;
}
export interface AnalysisResult {
  schema_version: number;
  sample_id: string;
  status: "complete" | "partial" | "failed" | string;
  failure_reason: string | null;
  warnings: Warning[];
  transcript_original: string;
  reference_audio: AudioMeta | null;
  participant_audio: AudioMeta | null;
  reference_alignment: Alignment | null;
  participant_alignment: Alignment | null;
  reference_features: FeatureSeries[];
  participant_features: FeatureSeries[];
  reference_scalar_features: ScalarFeature[];
  participant_scalar_features: ScalarFeature[];
  detections: Detection[];
  scores: Scores;
}
export interface AnalyzeResponse {
  analysis_id: string;
  mode: string;
  provenance: Record<string, unknown>;
  result: AnalysisResult;
}

export interface EvaluationFamily {
  tp: number;
  fp: number;
  fn: number;
  precision: number | null;
  recall: number | null;
  f1: number | null;
}
export interface EvaluationReport {
  available: boolean;
  reason?: string;
  split?: string;
  num_cases?: number;
  is_synthetic_pilot?: boolean;
  note?: string;
  per_family?: Record<string, EvaluationFamily>;
  runtime_by_stage?: Record<string, { mean_s: number; max_s: number; n: number }>;
  cases?: Record<string, unknown>[];
  source_file?: string;
}
export interface Config {
  analysis_config_hash: string;
  scoring_config_hash: string;
  language: string;
  thresholds: Record<string, { value: number; unit: string }>;
  scoring_dimensions: Record<string, { weight: number }>;
  severity_bands: { low_upper_ratio: number; moderate_upper_ratio: number };
  overall_min_valid_dimensions: number;
}
