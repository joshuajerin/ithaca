import { Navigate, Route, Routes } from "react-router-dom";
import Landing from "./Landing";
import LegalPage from "./legal/LegalPage";
import { LEGAL_DOCS } from "./legal/registry";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      {LEGAL_DOCS.map((doc) => (
        <Route key={doc.slug} path={`/${doc.slug}`} element={<LegalPage slug={doc.slug} />} />
      ))}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
