import { BrowserRouter, Routes, Route } from "react-router-dom";
import Nav from "./components/Nav";
import Hero from "./components/Hero";
import Marquee from "./components/Marquee";
import FeatureSections from "./components/FeatureSections";
import Trust from "./components/Trust";
import CTA from "./components/CTA";
import Footer from "./components/Footer";
import TermsPage from "./pages/legal/TermsPage";
import PrivacyPage from "./pages/legal/PrivacyPage";
import DisclosuresPage from "./pages/legal/DisclosuresPage";
import DataSourcesPage from "./pages/legal/DataSourcesPage";

function Home() {
  return (
    <div className="relative min-h-screen bg-paper">
      <Nav />
      <main>
        <Hero />
        <Marquee />
        <FeatureSections />
        <Trust />
        <CTA />
      </main>
      <Footer />
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/legal/terms" element={<TermsPage />} />
        <Route path="/legal/privacy" element={<PrivacyPage />} />
        <Route path="/legal/disclosures" element={<DisclosuresPage />} />
        <Route path="/legal/data-sources" element={<DataSourcesPage />} />
      </Routes>
    </BrowserRouter>
  );
}
