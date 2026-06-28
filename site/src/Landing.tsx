import Nav from "./components/Nav";
import Hero from "./components/Hero";
import Marquee from "./components/Marquee";
// import HowItWorks from "./components/HowItWorks"; // layers moved into Hero (right side)
import FeatureSections from "./components/FeatureSections";
import Trust from "./components/Trust";
import CTA from "./components/CTA";
import Footer from "./components/Footer";

export default function Landing() {
  return (
    <div className="relative min-h-screen bg-paper">
      <Nav />
      <main>
        <Hero />
        <Marquee />
        {/* <HowItWorks /> — layers animation moved into the Hero (right side) */}
        <FeatureSections />
        <Trust />
        <CTA />
      </main>
      <Footer />
    </div>
  );
}
