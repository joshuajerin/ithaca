import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { Dashboard } from "./pages/Dashboard";
import { SessionsList } from "./pages/SessionsList";
import { SessionDetail } from "./pages/SessionDetail";
import { Deployments } from "./pages/Deployments";
import { DeploymentDetail } from "./pages/DeploymentDetail";
import { Settings } from "./pages/Settings";
import { Docs } from "./pages/Docs";
import { AuthPage } from "./pages/AuthPage";
import { AgentLink } from "./pages/AgentLink";
// Legacy routes kept so existing bookmarks don't 404
import { RunsList } from "./pages/RunsList";
import { RunDetail } from "./pages/RunDetail";
import { Deploys } from "./pages/Deploys";
import { Trades } from "./pages/Trades";
import { useAuth } from "./auth/AuthContext";
import { DoombergMark } from "./auth/icons";
import { LEGAL_LINKS, legalUrl } from "./lib/legal";

type IconProps = { className?: string };

function IconDashboard() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="3" y="3" width="7" height="7" rx="1.5" /><rect x="14" y="3" width="7" height="7" rx="1.5" />
      <rect x="3" y="14" width="7" height="7" rx="1.5" /><rect x="14" y="14" width="7" height="7" rx="1.5" />
    </svg>
  );
}

function IconSessions() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M12 3l9 5-9 5-9-5 9-5z" /><path d="M3 13l9 5 9-5" /><path d="M3 18l9 5 9-5" opacity="0.5" />
    </svg>
  );
}

function IconDeployments() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M12 2.5l7.5 4.3v8.4L12 19.5l-7.5-4.3V6.8L12 2.5z" /><path d="M4.8 7l7.2 4.2L19.2 7" /><path d="M12 11.2V19.5" />
    </svg>
  );
}

function IconDocs() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8l-5-5z" /><path d="M14 3v5h5" />
      <path d="M9 13h6M9 17h6" />
    </svg>
  );
}

const NAV: { to: string; label: string; Icon: (p: IconProps) => JSX.Element }[] = [
  { to: "/dashboard",   label: "Dashboard",   Icon: IconDashboard },
  { to: "/sessions",    label: "Sessions",    Icon: IconSessions },
  { to: "/deployments", label: "Deployments", Icon: IconDeployments },
];

function LogoutIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
      <path d="M16 17l5-5-5-5M21 12H9" />
    </svg>
  );
}

function SettingsIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
    </svg>
  );
}

export function App() {
  const { user, signOut } = useAuth();

  if (!user) return <AuthPage />;

  const initials = user.name
    .split(" ")
    .map((s: string) => s[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();

  return (
    <div className="app">
      <aside className="rail">
        <div className="rail-brand">
          <DoombergMark size={26} />
        </div>

        {/* Equal spacer — pushes primary nav to vertical center */}
        <div style={{ flex: 1 }} />

        {/* Primary 3-screen nav — centered icon + label */}
        <nav className="rail-nav">
          {NAV.map(({ to, label, Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) => `rail-link${isActive ? " active" : ""}`}
            >
              <Icon />
              {label}
            </NavLink>
          ))}
        </nav>

        {/* Equal spacer — pushes util links to bottom */}
        <div style={{ flex: 1 }} />

        {/* Docs (external) + Settings — left-aligned util links */}
        <nav className="rail-nav-util">
          <a
            href="https://ithaca.mintlify.app"
            target="_blank"
            rel="noopener noreferrer"
            className="rail-link"
          >
            <IconDocs />
            Docs
          </a>
          <NavLink to="/settings" className={({ isActive }) => `rail-link${isActive ? " active" : ""}`}>
            <SettingsIcon />
            Settings
          </NavLink>
        </nav>

        {/* User chip */}
        <div className="rail-user">
          <div className="rail-user-av">
            {user.avatarUrl ? <img src={user.avatarUrl} alt="" /> : <span>{initials}</span>}
          </div>
          <div className="rail-user-meta">
            <div className="rail-user-name">{user.name}</div>
            <div className="rail-user-sub">{user.email || "signed in"}</div>
          </div>
          <button className="rail-signout" onClick={signOut} title="Sign out" aria-label="Sign out">
            <LogoutIcon />
          </button>
        </div>

        <div className="rail-foot">
          <div className="rail-legal">
            {LEGAL_LINKS.map((l, i) => (
              <span key={l.slug}>
                {i > 0 && <span className="rail-legal-sep"> · </span>}
                <a href={legalUrl(l.slug)} target="_blank" rel="noopener noreferrer">{l.label}</a>
              </span>
            ))}
          </div>
        </div>
      </aside>

      <main className="main">
        <Routes>
          {/* Default */}
          <Route path="/" element={<Navigate to="/dashboard" replace />} />

          {/* Primary screens */}
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/sessions" element={<SessionsList />} />
          <Route path="/sessions/:id" element={<SessionsList />} />
          <Route path="/deployments" element={<Deployments />} />
          <Route path="/deployments/:id" element={<DeploymentDetail />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/docs" element={<Docs />} />

          {/* Legacy routes — preserved so existing bookmarks don't 404 */}
          <Route path="/runs" element={<RunsList />} />
          <Route path="/runs/:id" element={<RunDetail />} />
          <Route path="/deploys" element={<Deploys />} />
          <Route path="/trades" element={<Trades />} />
          <Route path="/agent-link" element={<AgentLink />} />
          <Route path="/session-detail/:id" element={<SessionDetail />} />

          <Route path="*" element={<div className="page"><div className="empty">Not found.</div></div>} />
        </Routes>
      </main>
    </div>
  );
}
