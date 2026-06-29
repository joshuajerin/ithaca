import { LayoutDashboard, LogOut, Rocket, ScrollText } from "lucide-react";
import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { Dashboard } from "./pages/Dashboard";
import { SessionsList } from "./pages/SessionsList";
import { SessionDetail } from "./pages/SessionDetail";
import { Deployments } from "./pages/Deployments";
import { DeploymentDetail } from "./pages/DeploymentDetail";
import { Settings } from "./pages/Settings";
import { AuthPage } from "./pages/AuthPage";
import { AgentLink } from "./pages/AgentLink";
import { useAuth } from "./auth/AuthContext";
import { DoombergMark } from "./auth/icons";

const navItems = [
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { to: "/sessions", label: "Sessions", icon: ScrollText },
  { to: "/deployments", label: "Deployments", icon: Rocket },
] as const;

export function App() {
  const { user, manageAccount, signOut } = useAuth();

  if (!user) return <AuthPage />;

  return (
    <div className="app">
      <aside className="rail" aria-label="Primary navigation">
        <div className="rail-brand" aria-label="Ithaca">
          <DoombergMark size={26} />
        </div>

        <nav className="rail-nav">
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink key={item.to} to={item.to} className="rail-link">
                <Icon aria-hidden="true" />
                <span>{item.label}</span>
              </NavLink>
            );
          })}
        </nav>

        <div className="rail-user">
          <button className="rail-user-email" type="button" onClick={manageAccount} title={user.email}>
            {user.email || "Account"}
          </button>
          <button className="rail-signout" type="button" onClick={signOut} aria-label="Sign out">
            <LogOut aria-hidden="true" />
          </button>
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

          <Route path="/agent-link" element={<AgentLink />} />
          <Route path="/session-detail/:id" element={<SessionDetail />} />

          <Route path="*" element={<div className="page"><div className="empty">Not found.</div></div>} />
        </Routes>
      </main>
    </div>
  );
}
