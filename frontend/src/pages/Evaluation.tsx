import { useEffect, useState } from "react";
import { api } from "../services/api";
import type { EvaluationReport } from "../types";
import { Banner, fmt } from "../components/ui";

export default function EvaluationPage() {
  const [report, setReport] = useState<EvaluationReport | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api.evaluation("test").then(setReport).catch((e) => setErr(String(e.message || e)));
  }, []);

  if (err) return <div className="panel"><Banner kind="error">Could not load evaluation: {err}</Banner></div>;
  if (!report) return <div className="panel"><span className="spinner" /> Loading evaluation…</div>;
  if (!report.available) {
    return (
      <div className="panel">
        <h2>Evaluation</h2>
        <Banner kind="warn">{report.reason || "No evaluation artifacts yet."} Run
          <code> python scripts/run_evaluation.py --split test</code> then reload.</Banner>
      </div>
    );
  }

  const families = report.per_family ? Object.entries(report.per_family) : [];
  const stages = report.runtime_by_stage ? Object.entries(report.runtime_by_stage) : [];

  return (
    <div className="grid" style={{ gap: 16 }}>
      <div className="panel">
        <h2>Evaluation</h2>
        <div className="small muted">
          split <strong>{report.split}</strong> · {report.num_cases} cases · source <code>{report.source_file}</code>
        </div>
        {report.is_synthetic_pilot && <div style={{ marginTop: 10 }}><Banner kind="warn">{report.note}</Banner></div>}
      </div>

      <div className="panel">
        <h3>Per-family detection metrics</h3>
        <table>
          <thead><tr><th>family</th><th>TP</th><th>FP</th><th>FN</th><th>precision</th><th>recall</th><th>F1</th></tr></thead>
          <tbody>
            {families.map(([name, m]) => (
              <tr key={name}>
                <td>{name}</td><td>{m.tp}</td><td>{m.fp}</td><td>{m.fn}</td>
                <td>{m.precision === null ? "N/A" : fmt(m.precision, 3)}</td>
                <td>{m.recall === null ? "N/A" : fmt(m.recall, 3)}</td>
                <td>{m.f1 === null ? "N/A" : fmt(m.f1, 3)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="small muted" style={{ marginTop: 6 }}>
          Undefined precision/F1 (no positives) render as <strong>N/A</strong>, not 0.
        </div>
      </div>

      {stages.length > 0 && (
        <div className="panel">
          <h3>Runtime by stage (s)</h3>
          <table>
            <thead><tr><th>stage</th><th>mean</th><th>max</th><th>n</th></tr></thead>
            <tbody>
              {stages.map(([k, v]) => (
                <tr key={k}><td>{k}</td><td>{fmt(v.mean_s, 4)}</td><td>{fmt(v.max_s, 4)}</td><td>{v.n}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {report.cases && (
        <div className="panel">
          <h3>Per-case detail</h3>
          <table>
            <thead>
              <tr>{Object.keys(report.cases[0] || {}).map((k) => <th key={k}>{k}</th>)}</tr>
            </thead>
            <tbody>
              {report.cases.map((c, i) => (
                <tr key={i}>{Object.keys(report.cases![0]).map((k) => <td key={k}>{String((c as any)[k])}</td>)}</tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
