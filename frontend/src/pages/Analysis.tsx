import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../services/api";
import type { AnalyzeResponse, Detection, SamplePassage } from "../types";
import SummaryCards from "../components/SummaryCards";
import DetectionPanel from "../components/DetectionPanel";
import FeatureCharts from "../components/FeatureCharts";
import AudioPair from "../components/AudioPair";
import { Banner } from "../components/ui";

const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) || "";

export default function AnalysisPage() {
  const [mode, setMode] = useState<"sample" | "upload">("sample");
  const [samples, setSamples] = useState<SamplePassage[]>([]);
  const [passageId, setPassageId] = useState("");
  const [variant, setVariant] = useState("");
  const [loadErr, setLoadErr] = useState<string | null>(null);

  const [refFile, setRefFile] = useState<File | null>(null);
  const [parFile, setParFile] = useState<File | null>(null);
  const [transcript, setTranscript] = useState("");

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resp, setResp] = useState<AnalyzeResponse | null>(null);
  const [selected, setSelected] = useState<Detection | null>(null);
  const inFlight = useRef(false);

  useEffect(() => {
    api.samples()
      .then((s) => {
        setSamples(s);
        const withRef = s.find((p) => p.reference_id);
        if (withRef) {
          setPassageId(withRef.passage_id);
          const firstVar = withRef.variants.find((v) => v.variant !== "reference");
          if (firstVar) setVariant(firstVar.variant);
        }
      })
      .catch((e) => setLoadErr(String(e.message || e)));
  }, []);

  const passage = useMemo(() => samples.find((p) => p.passage_id === passageId), [samples, passageId]);
  const variantRow = passage?.variants.find((v) => v.variant === variant);

  const objUrls = useRef<string[]>([]);
  useEffect(() => () => objUrls.current.forEach((u) => URL.revokeObjectURL(u)), []);

  async function runAnalysis() {
    if (inFlight.current) return;
    inFlight.current = true;
    setLoading(true);
    setError(null);
    setSelected(null);
    try {
      let r: AnalyzeResponse;
      if (mode === "sample") {
        if (!passageId || !variant) throw new Error("Select a passage and a participant variant.");
        r = await api.analyzeSample(passageId, variant);
      } else {
        if (!refFile || !parFile) throw new Error("Upload both reference and participant audio.");
        if (!transcript.trim()) throw new Error("Enter the shared transcript.");
        const fd = new FormData();
        fd.append("reference", refFile);
        fd.append("participant", parFile);
        fd.append("transcript", transcript);
        fd.append("alignment_backend", "unavailable");
        r = await api.analyzeUpload(fd);
      }
      setResp(r);
    } catch (e: any) {
      setError(String(e.message || e)); // selections are preserved (state untouched)
    } finally {
      setLoading(false);
      inFlight.current = false;
    }
  }

  // Audio URLs for playback.
  let refUrl: string | null = null;
  let parUrl: string | null = null;
  if (resp) {
    if (resp.mode === "synthetic_sample" && passage?.reference_id && variantRow) {
      refUrl = `${API_BASE}/api/dataset/audio/${passage.reference_id}`;
      parUrl = `${API_BASE}/api/dataset/audio/${variantRow.recording_id}`;
    } else if (resp.mode === "upload") {
      if (refFile) { refUrl = URL.createObjectURL(refFile); objUrls.current.push(refUrl); }
      if (parFile) { parUrl = URL.createObjectURL(parFile); objUrls.current.push(parUrl); }
    }
  }

  const result = resp?.result ?? null;

  return (
    <div className="grid" style={{ gap: 16 }}>
      <section className="hero">
        <h1>Compare a delivery against its reference — with the evidence.</h1>
        <p>
          VocalLens aligns two recordings of the same English text, localizes measurable differences in
          pace, pauses, pitch variation and energy, and shows each candidate deviation with its timestamps,
          values and a plain-language explanation. It does not judge ability, intent, or confidence.
        </p>
      </section>

      <div className="panel">
        <h2>Analysis workspace</h2>
        <div className="row" style={{ marginBottom: 12 }}>
          <button className={mode === "sample" ? "" : "secondary"} onClick={() => setMode("sample")}>
            Synthetic sample pair
          </button>
          <button className={mode === "upload" ? "" : "secondary"} onClick={() => setMode("upload")}>
            Upload recordings
          </button>
        </div>

        {loadErr && <Banner kind="error">Could not load dataset samples: {loadErr}. Is the API running?</Banner>}

        {mode === "sample" ? (
          <>
            <Banner kind="info">
              DEMO: synthetic tonal fixtures with ground-truth alignment. Not natural speech.
            </Banner>
            <div className="grid cols-2">
              <div>
                <label>Passage</label>
                <select value={passageId} onChange={(e) => { setPassageId(e.target.value); setResp(null); }}>
                  {samples.map((p) => <option key={p.passage_id} value={p.passage_id}>{p.passage_id} ({p.split})</option>)}
                </select>
              </div>
              <div>
                <label>Participant variant</label>
                <select value={variant} onChange={(e) => { setVariant(e.target.value); setResp(null); }}>
                  {passage?.variants.filter((v) => v.variant !== "reference").map((v) => (
                    <option key={v.variant} value={v.variant}>
                      {v.variant} — {v.intended_flaw_family}/{v.intended_severity}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            <div style={{ marginTop: 10 }}>
              <label>Shared transcript</label>
              <textarea value={passage?.transcript ?? ""} readOnly />
            </div>
          </>
        ) : (
          <div className="grid cols-2">
            <div>
              <label>Reference audio (wav/mp3/flac/ogg)</label>
              <input type="file" accept=".wav,.mp3,.flac,.ogg" onChange={(e) => setRefFile(e.target.files?.[0] ?? null)} />
            </div>
            <div>
              <label>Participant audio</label>
              <input type="file" accept=".wav,.mp3,.flac,.ogg" onChange={(e) => setParFile(e.target.files?.[0] ?? null)} />
            </div>
            <div style={{ gridColumn: "1 / -1" }}>
              <label>Shared transcript (required)</label>
              <textarea value={transcript} onChange={(e) => setTranscript(e.target.value)}
                placeholder="Enter the exact words spoken in both recordings…" />
              <div className="small muted">Without the optional WhisperX backend, alignment is unavailable and
                time-grounded comparisons are limited (shown honestly).</div>
            </div>
          </div>
        )}

        <div className="row" style={{ marginTop: 14 }}>
          <button onClick={runAnalysis} disabled={loading}>
            {loading ? <><span className="spinner" /> Analyzing…</> : "Run analysis"}
          </button>
          {resp && <span className="small muted">analysis_id: <code>{resp.analysis_id}</code></span>}
        </div>
        {error && <div style={{ marginTop: 10 }}><Banner kind="error">{error}</Banner></div>}
      </div>

      {result && (
        <>
          {result.status === "failed" && (
            <Banner kind="error">Analysis failed: {result.failure_reason || "see warnings below."}</Banner>
          )}
          {result.status === "partial" && (
            <Banner kind="warn">Partial result — some stages were unavailable (e.g. alignment). Evidence is limited.</Banner>
          )}
          <SummaryCards result={result} />

          {result.warnings.length > 0 && (
            <div className="panel">
              <h3>Warnings ({result.warnings.length})</h3>
              {result.warnings.map((w, i) => (
                <div key={i} className="small"><code>{w.code}</code> — {w.message}</div>
              ))}
            </div>
          )}

          <div className="panel">
            <h3>Audio</h3>
            <AudioPair referenceUrl={refUrl} participantUrl={parUrl} selected={selected} />
          </div>

          <div className="grid cols-2">
            <div className="panel">
              <h3>Candidate deviations</h3>
              <DetectionPanel detections={result.detections} selectedId={selected?.detection_id ?? null}
                onSelect={(d) => setSelected(selected?.detection_id === d.detection_id ? null : d)} />
            </div>
            <div className="panel">
              <h3>Feature evidence</h3>
              <FeatureCharts result={result} selected={selected} />
            </div>
          </div>

          {result.status !== "failed" && resp && (
            <div className="panel">
              <h3>Export</h3>
              <div className="row">
                <a className="secondary" style={{ textDecoration: "none" }} href={api.exportUrl(resp.analysis_id, "json")}>
                  <button className="secondary">Download analysis JSON</button>
                </a>
                <a className="secondary" style={{ textDecoration: "none" }} href={api.exportUrl(resp.analysis_id, "csv")}>
                  <button className="secondary">Download detections CSV</button>
                </a>
                <span className="small muted">Generated from the actual API result (schema v{result.schema_version}).</span>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
