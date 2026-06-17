import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { RunsList } from "./pages/RunsList";
import { RunDetail } from "./pages/RunDetail";
import { Deploys } from "./pages/Deploys";
import { Trades } from "./pages/Trades";
import { Ideas } from "./pages/Ideas";
import { api } from "./api";

const NAV: { to: string; label: string }[] = [
  { to: "/runs", label: "Runs" },
  { to: "/deploys", label: "Deploys" },
  { to: "/trades", label: "Trades" },
  { to: "/ideas", label: "Ideas" },
];

export function App() {
  return (
    <div className="app">
      <aside className="rail">
        <div className="rail-brand">
          Doomberg
          <small>Observability</small>
        </div>
        <nav className="rail-nav">
          {NAV.map((n) => (
            <NavLink key={n.to} to={n.to} className={({ isActive }) => `rail-link ${isActive ? "active" : ""}`}>
              {n.label}
            </NavLink>
          ))}
        </nav>
        <div className="rail-foot">
          api {api.apiBase}
          <br />
          tenant {api.tenantId.slice(0, 8)}…
        </div>
      </aside>
      <main className="main">
        <Routes>
          <Route path="/" element={<Navigate to="/runs" replace />} />
          <Route path="/runs" element={<RunsList />} />
          <Route path="/runs/:id" element={<RunDetail />} />
          <Route path="/deploys" element={<Deploys />} />
          <Route path="/trades" element={<Trades />} />
          <Route path="/ideas" element={<Ideas />} />
          <Route path="*" element={<div className="page"><div className="empty">Not found.</div></div>} />
        </Routes>
      </main>
    </div>
  );
}
