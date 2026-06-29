import { Navigate, Route, Routes } from "react-router-dom";
import { Dashboard } from "./pages/Dashboard";
import { SessionsList } from "./pages/SessionsList";
import { SessionDetail } from "./pages/SessionDetail";
import { Deployments } from "./pages/Deployments";
import { DeploymentDetail } from "./pages/DeploymentDetail";
import { Settings } from "./pages/Settings";
import { AuthPage } from "./pages/AuthPage";
import { AgentLink } from "./pages/AgentLink";
import { useAuth } from "./auth/AuthContext";

export function App() {
  const { user } = useAuth();

  if (!user) return <AuthPage />;

  return (
    <div className="app app-no-rail">
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

          {/* Legacy redirects — old bookmarks go to the right place */}
          <Route path="/runs" element={<Navigate to="/deployments" replace />} />
          <Route path="/runs/:id" element={<Navigate to="/deployments" replace />} />
          <Route path="/deploys" element={<Navigate to="/deployments" replace />} />
          <Route path="/trades" element={<Navigate to="/dashboard" replace />} />
          <Route path="/docs" element={<Navigate to="/settings" replace />} />
          <Route path="/agent-link" element={<AgentLink />} />
          <Route path="/session-detail/:id" element={<SessionDetail />} />

          <Route path="*" element={<div className="page"><div className="empty">Not found.</div></div>} />
        </Routes>
      </main>
    </div>
  );
}
