import { useState } from "react";
import {
  CartesianGrid, Line, LineChart, ReferenceArea, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import type { AnalysisResult, Detection, FeatureSeries } from "../types";

const VIEWS = [
  { key: "rms_dbfs", label: "Energy (RMS dBFS)" },
  { key: "f0_hz", label: "Pitch (F0 Hz)" },
];

function seriesFor(list: FeatureSeries[], role: string, key: string): FeatureSeries | undefined {
  return list.find((s) => s.name === `${role}_${key}`);
}

function toData(s?: FeatureSeries) {
  if (!s) return [];
  const out: { t: number; v: number }[] = [];
  for (let i = 0; i < s.times.length; i++) {
    const v = s.values[i];
    if (v !== null && v !== undefined) out.push({ t: Number(s.times[i].toFixed(3)), v });
  }
  return out;
}

function Chart({
  title, data, color, unit, hi,
}: {
  title: string; data: { t: number; v: number }[]; color: string; unit: string;
  hi?: { x1: number; x2: number } | null;
}) {
  return (
    <div className="card">
      <div className="k" style={{ marginBottom: 8 }}>{title}</div>
      {data.length === 0 ? (
        <div className="muted small">No valid measurements available for this recording.</div>
      ) : (
        <ResponsiveContainer width="100%" height={200}>
          <LineChart data={data} margin={{ top: 5, right: 10, bottom: 5, left: -10 }}>
            <CartesianGrid stroke="#2a333f" strokeDasharray="3 3" />
            <XAxis dataKey="t" stroke="#9aa7b4" fontSize={11} tickFormatter={(t) => `${t}s`} />
            <YAxis stroke="#9aa7b4" fontSize={11} width={46}
              label={{ value: unit, angle: -90, position: "insideLeft", fill: "#9aa7b4", fontSize: 11 }} />
            <Tooltip contentStyle={{ background: "#161b22", border: "1px solid #2a333f", color: "#e6edf3" }} />
            {hi && <ReferenceArea x1={hi.x1} x2={hi.x2} strokeOpacity={0} fill="#f59e0b" fillOpacity={0.15} />}
            <Line type="monotone" dataKey="v" stroke={color} dot={false} strokeWidth={1.6} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}

export default function FeatureCharts({
  result, selected,
}: {
  result: AnalysisResult; selected: Detection | null;
}) {
  const [view, setView] = useState("rms_dbfs");
  const refS = seriesFor(result.reference_features, "reference", view);
  const parS = seriesFor(result.participant_features, "participant", view);
  const unit = refS?.unit ?? parS?.unit ?? "";
  const refHi = selected ? { x1: selected.reference_start, x2: selected.reference_end } : null;
  const parHi = selected ? { x1: selected.participant_start, x2: selected.participant_end } : null;

  // Scalar comparison table (unavailable stays unavailable, never 0).
  const refMap = new Map(result.reference_scalar_features.map((f) => [f.name, f]));
  const parMap = new Map(result.participant_scalar_features.map((f) => [f.name, f]));
  const names = result.reference_scalar_features.map((f) => f.name);

  return (
    <div>
      <div className="row" style={{ marginBottom: 10 }}>
        <div style={{ minWidth: 220 }}>
          <label>Feature view</label>
          <select value={view} onChange={(e) => setView(e.target.value)}>
            {VIEWS.map((v) => <option key={v.key} value={v.key}>{v.label}</option>)}
          </select>
        </div>
        <div className="small muted" style={{ alignSelf: "end" }}>
          Reference and participant use <strong>separate clocks</strong>; charts are not time-synchronized.
          {selected && " Amber band = selected detection interval."}
        </div>
      </div>
      <div className="grid cols-2">
        <Chart title="Reference" data={toData(refS)} color="#38bdf8" unit={unit} hi={refHi} />
        <Chart title="Participant" data={toData(parS)} color="#f59e0b" unit={unit} hi={parHi} />
      </div>
      <div className="card" style={{ marginTop: 12 }}>
        <div className="k" style={{ marginBottom: 8 }}>Scalar features</div>
        <table>
          <thead><tr><th>feature</th><th>unit</th><th>reference</th><th>participant</th></tr></thead>
          <tbody>
            {names.map((n) => {
              const rf = refMap.get(n); const pf = parMap.get(n);
              return (
                <tr key={n}>
                  <td>{n}</td>
                  <td className="muted">{rf?.unit}</td>
                  <td>{rf && rf.valid ? rf.value : "Unavailable"}</td>
                  <td>{pf && pf.valid ? pf.value : "Unavailable"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
