import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import AnalysisPage from "./pages/Analysis";
import EvaluationPage from "./pages/Evaluation";
import AboutPage from "./pages/About";

export default function App() {
  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          VocalLens <small>Contrastive Speech Analytics · Track C</small>
        </div>
        <nav className="nav">
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
      </header>
      <main className="container">
        <Routes>
          <Route path="/" element={<Navigate to="/analysis" replace />} />
          <Route path="/analysis" element={<AnalysisPage />} />
          <Route path="/evaluation" element={<EvaluationPage />} />
          <Route path="/about" element={<AboutPage />} />
          <Route path="*" element={<Navigate to="/analysis" replace />} />
        </Routes>
      </main>
    </div>
  );
}
