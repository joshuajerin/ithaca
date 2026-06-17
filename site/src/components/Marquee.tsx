import { Reveal } from "./ui";

// Sourced-like-the-desks providers (from the data-sourcing strategy).
const SOURCES = [
  "Databento · direct feeds",
  "Sharadar · point-in-time",
  "Alpaca · SIP paper-live",
  "SEC EDGAR",
  "FRED / ALFRED",
  "IEX DEEP · order book",
  "Nasdaq TotalView-ITCH",
  "NYSE Pillar / XDP",
  "Cboe PITCH",
  "OPRA options",
];

function Row() {
  return (
    <div className="flex shrink-0 items-center gap-10 pr-10">
      {SOURCES.map((s) => (
        <span
          key={s}
          className="flex items-center gap-3 whitespace-nowrap font-mono text-[0.82rem] uppercase tracking-[0.12em] text-faint"
        >
          <span className="h-1.5 w-1.5 rounded-full bg-olive/50" />
          {s}
        </span>
      ))}
    </div>
  );
}

export default function Marquee() {
  return (
    <section className="border-y border-line bg-cream/40 py-7">
      <div className="mx-auto max-w-[1200px] px-5">
        <Reveal className="mb-5 text-center">
          <p className="eyebrow text-faint">
            Real data, sourced the way the desks do it
          </p>
        </Reveal>
        <div className="mask-fade-x relative flex overflow-hidden">
          <div className="animate-marquee flex">
            <Row />
            <Row />
          </div>
        </div>
      </div>
    </section>
  );
}
