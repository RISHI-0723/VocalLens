import type {
  AnalyzeResponse,
  Config,
  EvaluationReport,
  SamplePassage,
} from "../types";

// Empty base in dev => the Vite proxy forwards /api to the backend.
const BASE = (import.meta.env.VITE_API_BASE as string | undefined) || "";

async function getJSON<T>(path: string): Promise<T> {
  const r = await fetch(`${BASE}${path}`);
  if (!r.ok) throw new Error(await safeDetail(r, `GET ${path} failed (${r.status})`));
  return (await r.json()) as T;
}

async function safeDetail(r: Response, fallback: string): Promise<string> {
  try {
    const j = await r.json();
    return (j && (j.detail as string)) || fallback;
  } catch {
    return fallback;
  }
}

export const api = {
  health: () => getJSON<{ status: string; engine: string; engine_version: string }>("/api/health"),
  samples: () => getJSON<SamplePassage[]>("/api/dataset/samples"),
  config: () => getJSON<Config>("/api/config"),
  evaluation: (split = "test") => getJSON<EvaluationReport>(`/api/evaluation?split=${encodeURIComponent(split)}`),

  async analyzeSample(passage_id: string, variant: string): Promise<AnalyzeResponse> {
    const r = await fetch(`${BASE}/api/analyze/sample`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ passage_id, variant }),
    });
    if (!r.ok) throw new Error(await safeDetail(r, `Analysis failed (${r.status})`));
    return (await r.json()) as AnalyzeResponse;
  },

  async analyzeUpload(fd: FormData): Promise<AnalyzeResponse> {
    const r = await fetch(`${BASE}/api/analyze/upload`, { method: "POST", body: fd });
    if (!r.ok) throw new Error(await safeDetail(r, `Analysis failed (${r.status})`));
    return (await r.json()) as AnalyzeResponse;
  },

  exportUrl: (analysisId: string, kind: "json" | "csv") =>
    `${BASE}/api/analysis/${analysisId}/export.${kind}`,
};
