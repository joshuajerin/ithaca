import { LayoutDashboard, LogOut, Rocket, ScrollText } from "lucide-react";
import { lazy, Suspense } from "react";
import { NavLink, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { AuthPage } from "./pages/AuthPage";
import { useAuth } from "./auth/AuthContext";
import { DoombergMark } from "./auth/icons";

const Dashboard = lazy(() => import("./pages/Dashboard").then((module) => ({ default: module.Dashboard })));
const SessionsList = lazy(() => import("./pages/SessionsList").then((module) => ({ default: module.SessionsList })));
const SessionDetail = lazy(() => import("./pages/SessionDetail").then((module) => ({ default: module.SessionDetail })));
const Backtests = lazy(() => import("./pages/Backtests").then((module) => ({ default: module.Backtests })));
const DeploymentDetail = lazy(() => import("./pages/DeploymentDetail").then((module) => ({ default: module.DeploymentDetail })));
const Settings = lazy(() => import("./pages/Settings").then((module) => ({ default: module.Settings })));
const AgentLink = lazy(() => import("./pages/AgentLink").then((module) => ({ default: module.AgentLink })));

const navItems = [
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { to: "/sessions", label: "Sessions", icon: ScrollText },
  { to: "/backtests", label: "Backtests", icon: Rocket },
] as const;

function RouteLoading() {
  return <div className="page"><div className="empty">Loading page…</div></div>;
}

export function App() {
  const { user, manageAccount, signOut } = useAuth();
  const location = useLocation();

  if (!user) return <AuthPage />;

  if (location.pathname === "/agent-link") {
    return (
      <Suspense fallback={<RouteLoading />}>
        <Routes>
          <Route path="/agent-link" element={<AgentLink />} />
          <Route path="*" element={<Navigate to="/agent-link" replace />} />
        </Routes>
      </Suspense>
    );
  }

  return (
    <div className="app">
      <aside className="rail" aria-label="Primary navigation">
        <div className="rail-brand" aria-label="Doomberg">
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
        <Suspense fallback={<RouteLoading />}>
          <Routes>
            {/* Default */}
            <Route path="/" element={<Navigate to="/dashboard" replace />} />

            {/* Primary screens */}
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/sessions" element={<SessionsList />} />
            <Route path="/sessions/:id" element={<SessionsList />} />
            <Route path="/backtests" element={<Backtests />} />
            <Route path="/backtests/:id" element={<DeploymentDetail />} />
            <Route path="/deployments" element={<Navigate to="/backtests" replace />} />
            <Route path="/deployments/:id" element={<DeploymentDetail />} />
            <Route path="/settings" element={<Settings />} />

            <Route path="/agent-link" element={<AgentLink />} />
            <Route path="/session-detail/:id" element={<SessionDetail />} />

            <Route path="*" element={<div className="page"><div className="empty">Not found.</div></div>} />
          </Routes>
        </Suspense>
      </main>
    </div>
  );
}
