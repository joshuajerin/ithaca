import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { RunsList } from "./pages/RunsList";
import { RunDetail } from "./pages/RunDetail";
import { Deploys } from "./pages/Deploys";
import { Trades } from "./pages/Trades";
import { Ideas } from "./pages/Ideas";
import { Settings } from "./pages/Settings";
import { AuthPage } from "./pages/AuthPage";
import { useAuth } from "./auth/AuthContext";
import { api } from "./api";

const NAV: { to: string; label: string }[] = [
  { to: "/runs", label: "Runs" },
  { to: "/deploys", label: "Deploys" },
  { to: "/trades", label: "Trades" },
  { to: "/ideas", label: "Ideas" },
  { to: "/settings", label: "Settings" },
];

function LogoutIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
      <path d="M16 17l5-5-5-5M21 12H9" />
    </svg>
  );
}

export function App() {
  const { user, signOut } = useAuth();

  // No session → the auth gate (Google / GitHub / demo) stands in for the app.
  if (!user) return <AuthPage />;

  const initials = user.name
    .split(" ")
    .map((s) => s[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();

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

        <div className="rail-user">
          <div className="rail-user-av">
            {user.avatarUrl ? <img src={user.avatarUrl} alt="" /> : <span>{initials}</span>}
          </div>
          <div className="rail-user-meta">
            <div className="rail-user-name">{user.name}</div>
            <div className="rail-user-sub">{user.provider}</div>
          </div>
          <button className="rail-signout" onClick={signOut} title="Sign out" aria-label="Sign out">
            <LogoutIcon />
          </button>
        </div>

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
          <Route path="/settings" element={<Settings />} />
          <Route path="*" element={<div className="page"><div className="empty">Not found.</div></div>} />
        </Routes>
      </main>
    </div>
  );
}
