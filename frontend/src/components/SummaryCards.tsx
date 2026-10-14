import type { AnalysisResult } from "../types";
import { StatusBadge } from "./ui";

export default function SummaryCards({ result }: { result: AnalysisResult }) {
  const { scores, detections } = result;
  // Most significant detected family = highest normalized exceedance.
  let topFamily = "None";
  if (detections.length) {
    const top = [...detections].sort((a, b) => b.normalized_exceedance - a.normalized_exceedance)[0];
    topFamily = top.family.replace(/_/g, " ");
  }
  const overall =
    scores.overall_available && scores.overall_display_score !== null
      ? String(scores.overall_display_score)
      : "Unavailable";
  const refA = result.reference_alignment?.status ?? "n/a";
  const parA = result.participant_alignment?.status ?? "n/a";
  return (
    <div className="grid cols-4">
      <div className="card">
        <div className="k">Prototype score</div>
        <div className="v">{overall}</div>
        <div className="small muted">provisional rubric</div>
      </div>
      <div className="card">
        <div className="k">Candidate flags</div>
        <div className="v">{detections.length}</div>
        <div className="small muted">{scores.valid_dimension_count} of {scores.dimensions.length} dims valid</div>
      </div>
      <div className="card">
        <div className="k">Top category</div>
        <div className="v" style={{ fontSize: 20 }}>{topFamily}</div>
        <div className="small muted">by normalized exceedance</div>
      </div>
      <div className="card">
        <div className="k">Status</div>
        <div className="v" style={{ fontSize: 20 }}><StatusBadge status={result.status} /></div>
        <div className="small muted">align: ref {refA} / part {parA}</div>
      </div>
    </div>
  );
}
