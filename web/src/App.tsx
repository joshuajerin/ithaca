import { LayoutDashboard, LogOut, Rocket, ScrollText } from "lucide-react";
import { NavLink, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { useState, type FormEvent } from "react";
import { api } from "./api";
import { Dashboard } from "./pages/Dashboard";
import { SessionsList } from "./pages/SessionsList";
import { SessionDetail } from "./pages/SessionDetail";
import { Backtests } from "./pages/Backtests";
import { DeploymentDetail } from "./pages/DeploymentDetail";
import { Settings } from "./pages/Settings";
import { AuthPage } from "./pages/AuthPage";
import { AgentLink } from "./pages/AgentLink";
import { useAuth } from "./auth/AuthContext";
import { DoombergMark } from "./auth/icons";

const navItems = [
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { to: "/sessions", label: "Sessions", icon: ScrollText },
  { to: "/backtests", label: "Backtests", icon: Rocket },
] as const;

const MAX_FEEDBACK_LENGTH = 5000;

export function App() {
  const { user, manageAccount, signOut } = useAuth();
  const location = useLocation();
  const [feedbackOpen, setFeedbackOpen] = useState(false);
  const [feedback, setFeedback] = useState("");
  const [feedbackError, setFeedbackError] = useState<string | null>(null);
  const [feedbackSubmitting, setFeedbackSubmitting] = useState(false);
  const [feedbackSent, setFeedbackSent] = useState(false);

  function closeFeedback() {
    setFeedbackOpen(false);
    setFeedback("");
    setFeedbackError(null);
    setFeedbackSent(false);
  }

  async function submitFeedback(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const message = feedback.trim();
    if (!message || feedbackSubmitting) return;
    setFeedbackSubmitting(true);
    setFeedbackError(null);
    try {
      await api.submitFeedback(message);
      setFeedbackSent(true);
      setFeedback("");
    } catch (error) {
      setFeedbackError(error instanceof Error ? error.message : String(error));
    } finally {
      setFeedbackSubmitting(false);
    }
  }

  if (!user) return <AuthPage />;

  if (location.pathname === "/agent-link") {
    return (
      <Routes>
        <Route path="/agent-link" element={<AgentLink />} />
        <Route path="*" element={<Navigate to="/agent-link" replace />} />
      </Routes>
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

        <div className="rail-feedback">
          <button type="button" onClick={() => setFeedbackOpen(true)}>Feedback</button>
        </div>
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
          <Route path="/backtests" element={<Backtests />} />
          <Route path="/backtests/:id" element={<DeploymentDetail />} />
          <Route path="/deployments" element={<Navigate to="/backtests" replace />} />
          <Route path="/deployments/:id" element={<DeploymentDetail />} />
          <Route path="/settings" element={<Settings />} />

          <Route path="/agent-link" element={<AgentLink />} />
          <Route path="/session-detail/:id" element={<SessionDetail />} />

          <Route path="*" element={<div className="page"><div className="empty">Not found.</div></div>} />
        </Routes>
      </main>

      {feedbackOpen && (
        <div className="feedback-backdrop" role="presentation" onMouseDown={closeFeedback}>
          <section
            className="feedback-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="feedback-title"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <div className="feedback-dialog-head">
              <div>
                <h2 id="feedback-title">Feedback</h2>
                <p>Send a bug report or feature request directly to Doomberg.</p>
              </div>
              <button type="button" className="btn" onClick={closeFeedback}>Close</button>
            </div>
            {feedbackSent ? (
              <div className="feedback-success">
                <strong>Feedback submitted.</strong>
                <span>Thank you. It has been saved for review.</span>
                <button type="button" className="btn primary" onClick={closeFeedback}>Done</button>
              </div>
            ) : (
              <form className="feedback-form" onSubmit={submitFeedback}>
                <textarea
                  value={feedback}
                  onChange={(event) => setFeedback(event.target.value)}
                  placeholder="What bugs or features would you like to see?"
                  maxLength={MAX_FEEDBACK_LENGTH}
                  autoFocus
                />
                {feedbackError && <div className="banner">{feedbackError}</div>}
                <div className="feedback-form-foot">
                  <span>{feedback.length}/{MAX_FEEDBACK_LENGTH}</span>
                  <button className="btn primary" type="submit" disabled={!feedback.trim() || feedbackSubmitting}>
                    {feedbackSubmitting ? "Submitting…" : "Submit"}
                  </button>
                </div>
              </form>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
