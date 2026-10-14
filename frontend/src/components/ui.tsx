import type { ReactNode } from "react";

export function fmt(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "Unavailable";
  return Number(v).toFixed(digits);
}

export function SeverityBadge({ severity }: { severity: string }) {
  const cls =
    severity === "high" ? "high" : severity === "moderate" ? "moderate" : severity === "low" ? "low" : "unavailable";
  const label = severity.charAt(0).toUpperCase() + severity.slice(1);
  return <span className={`badge ${cls}`}>{label}</span>;
}

export function StatusBadge({ status }: { status: string }) {
  const cls = status === "complete" ? "ok" : status === "failed" ? "high" : "moderate";
  return <span className={`badge ${cls}`}>{status}</span>;
}

export function Banner({ kind, children }: { kind: "info" | "warn" | "error" | "ok"; children: ReactNode }) {
  return <div className={`banner ${kind}`}>{children}</div>;
}
