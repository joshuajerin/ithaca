import Nav from "./components/Nav";
import Hero from "./components/Hero";
import Marquee from "./components/Marquee";
import HowItWorks from "./components/HowItWorks";
import FeatureSections from "./components/FeatureSections";
import Trust from "./components/Trust";
import BackedBy from "./components/BackedBy";
import CTA from "./components/CTA";
import Footer from "./components/Footer";

export default function App() {
  return (
    <div className="relative min-h-screen bg-paper">
      <Nav />
      <main>
        <Hero />
        <Marquee />
        <HowItWorks />
        <FeatureSections />
        <Trust />
        <BackedBy />
        <CTA />
      </main>
      <Footer />
    </div>
  );
}
