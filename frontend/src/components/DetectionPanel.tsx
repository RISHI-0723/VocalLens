import type { Detection } from "../types";
import { SeverityBadge, fmt } from "./ui";

interface Props {
  detections: Detection[];
  selectedId: string | null;
  onSelect: (d: Detection) => void;
}

export default function DetectionPanel({ detections, selectedId, onSelect }: Props) {
  if (!detections.length) {
    return (
      <div className="banner ok">
        No candidate deviations crossed the configured thresholds. This does not prove the
        deliveries are identical.
      </div>
    );
  }
  return (
    <div>
      {detections.map((d) => (
        <div
          key={d.detection_id}
          className={`det ${selectedId === d.detection_id ? "selected" : ""}`}
          onClick={() => onSelect(d)}
        >
          <div className="hd">
            <strong>{d.family.replace(/_/g, " ")}</strong>
            <SeverityBadge severity={d.severity} />
          </div>
          <div className="small muted">
            {fmt(d.participant_start)}–{fmt(d.participant_end)} s (participant) · rule <code>{d.rule_id}</code>
          </div>
          <div className="kv" style={{ marginTop: 6 }}>
            participant {fmt(d.participant_value, 3)} {d.unit} · reference {fmt(d.reference_value, 3)} {d.unit} ·
            Δ {fmt(d.delta, 3)} {d.unit}
          </div>
          <div className="kv">
            threshold {fmt(d.threshold, 2)} {d.unit} · R={fmt(d.display_exceedance, 2)} · evidence quality{" "}
            {d.quality.Q === null ? "unavailable" : `${fmt(d.quality.Q, 2)} (${d.quality.label})`}
          </div>
          {selectedId === d.detection_id && (
            <div style={{ marginTop: 8 }}>
              <div>{d.explanation}</div>
              <div className="small muted" style={{ marginTop: 4 }}>⚠️ {d.caveat}</div>
              {d.quality.Q !== null && (
                <div className="small muted kv" style={{ marginTop: 4 }}>
                  A={fmt(d.quality.A, 2)} F={fmt(d.quality.F, 2)} S={fmt(d.quality.S, 2)} M={fmt(d.quality.M, 2)} ·
                  signal {d.quality.signal_state}
                </div>
              )}
              {d.merged_rule_ids.length > 0 && (
                <div className="small muted">also matched: {d.merged_rule_ids.join(", ")}</div>
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
