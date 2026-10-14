import { useEffect, useState } from "react";
import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import AnalysisPage from "./pages/Analysis";
import EvaluationPage from "./pages/Evaluation";
import AboutPage from "./pages/About";
import { api } from "./services/api";

type Health = "checking" | "online" | "offline";

function BackendStatus({ state }: { state: Health }) {
  const label = state === "online" ? "API online" : state === "offline" ? "API offline" : "Checking API…";
  return (
    <span className={`status status-${state}`} title={label} aria-live="polite">
      <span className="dot" aria-hidden="true" />
      {label}
    </span>
  );
}

export default function App() {
  const [health, setHealth] = useState<Health>("checking");

  useEffect(() => {
    let alive = true;
    const ping = () =>
      api
        .health()
        .then(() => alive && setHealth("online"))
        .catch(() => alive && setHealth("offline"));
    ping();
    const id = window.setInterval(ping, 30000);
    return () => {
      alive = false;
      window.clearInterval(id);
    };
  }, []);

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">◱</span>
          <span className="brand-name">VocalLens</span>
          <small>Contrastive Speech Analytics</small>
        </div>
        <nav className="nav" aria-label="Primary">
          <NavLink to="/analysis" className={({ isActive }) => (isActive ? "active" : "")}>
            Analysis
          </NavLink>
          <NavLink to="/evaluation" className={({ isActive }) => (isActive ? "active" : "")}>
            Evaluation
          </NavLink>
          <NavLink to="/about" className={({ isActive }) => (isActive ? "active" : "")}>
            About
          </NavLink>
        </nav>
        <BackendStatus state={health} />
      </header>

      {health === "offline" && (
        <div className="offline-bar" role="status">
          Can’t reach the analysis backend. It may be starting up (free-tier cold start can take ~30–50s) —
          this page will reconnect automatically.
        </div>
      )}

      <main className="container">
        <Routes>
          <Route path="/" element={<Navigate to="/analysis" replace />} />
          <Route path="/analysis" element={<AnalysisPage />} />
          <Route path="/evaluation" element={<EvaluationPage />} />
          <Route path="/about" element={<AboutPage />} />
          <Route path="*" element={<Navigate to="/analysis" replace />} />
        </Routes>
      </main>

      <footer className="footer">
        <span>
          VocalLens — evidence-grounded speech-delivery prototype. Synthetic dataset; a difference from the
          reference is not automatically a flaw.
        </span>
        <a href="https://github.com/RISHI-0723/VocalLens" target="_blank" rel="noreferrer">
          Source on GitHub
        </a>
      </footer>
    </div>
  );
}
