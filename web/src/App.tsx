import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { Dashboard } from "./pages/Dashboard";
import { SessionsList } from "./pages/SessionsList";
import { SessionDetail } from "./pages/SessionDetail";
import { NewSession } from "./pages/NewSession";
import { Docs } from "./pages/Docs";
import { RunsList } from "./pages/RunsList";
import { RunDetail } from "./pages/RunDetail";
import { Ideas } from "./pages/Ideas";
import { Settings } from "./pages/Settings";
import { AuthPage } from "./pages/AuthPage";
import { AgentLink } from "./pages/AgentLink";
import { Welcome } from "./pages/Welcome";
import { useAuth } from "./auth/AuthContext";
import { DoombergMark } from "./auth/icons";
import { api } from "./api";

const NAV: { to: string; label: string; cta?: boolean }[] = [
  { to: "/new-session", label: "New Session", cta: true },
  { to: "/welcome", label: "Welcome" },
  { to: "/dashboard", label: "Dashboard" },
  { to: "/sessions", label: "Sessions" },
  { to: "/runs", label: "Runs" },
  { to: "/ideas", label: "Ideas" },
  { to: "/docs", label: "Docs" },
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

  // No Clerk session -> show the auth gate.
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
          <DoombergMark size={22} />
          <div>
            Doomberg
            <small>Observability</small>
          </div>
        </div>
        <nav className="rail-nav">
          {NAV.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              className={({ isActive }) => `rail-link ${n.cta ? "rail-cta" : ""} ${isActive ? "active" : ""}`}
            >
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
          <Route path="/" element={<Navigate to="/welcome" replace />} />
          <Route path="/welcome" element={<Welcome />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/new-session" element={<NewSession />} />
          <Route path="/sessions" element={<SessionsList />} />
          <Route path="/sessions/:id" element={<SessionDetail />} />
          <Route path="/docs" element={<Docs />} />
          <Route path="/runs" element={<RunsList />} />
          <Route path="/runs/:id" element={<RunDetail />} />
          <Route path="/ideas" element={<Ideas />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/agent-link" element={<AgentLink />} />
          <Route path="*" element={<div className="page"><div className="empty">Not found.</div></div>} />
        </Routes>
      </main>
    </div>
  );
}
