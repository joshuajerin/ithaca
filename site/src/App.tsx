import { Navigate, Route, Routes } from "react-router-dom";
import Landing from "./Landing";
import LegalPage from "./legal/LegalPage";
import { LEGAL_DOCS } from "./legal/registry";

export type AuthMode = "clerk" | "signed-out";

export default function App({ authMode }: { authMode: AuthMode }) {
  return (
    <Routes>
      <Route path="/" element={<Landing authMode={authMode} />} />
      {LEGAL_DOCS.map((doc) => (
        <Route key={doc.slug} path={`/${doc.slug}`} element={<LegalPage slug={doc.slug} />} />
      ))}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
