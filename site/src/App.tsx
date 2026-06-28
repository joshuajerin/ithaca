import Nav from "./components/Nav";
import Hero from "./components/Hero";
import FoundersMarquee from "./components/FoundersMarquee";
import FeatureSections from "./components/FeatureSections";
import Trust from "./components/Trust";
import CTA from "./components/CTA";
import Footer from "./components/Footer";

export type AuthMode = "clerk" | "signed-out";

export default function App({ authMode }: { authMode: AuthMode }) {
  return (
    <div className="relative min-h-screen bg-paper">
      <Nav authMode={authMode} />
      <main>
        <Hero />
        <FoundersMarquee />
        <FeatureSections />
        <Trust />
        <CTA />
      </main>
      <Footer />
    </div>
  );
}
