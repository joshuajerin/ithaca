import { SectionHeader } from "./ui";
import IsometricStack from "./IsometricStack";

export default function HowItWorks() {
  return (
    <section id="how" className="relative overflow-hidden bg-paper py-24 lg:py-32">
      {/* center guide line, echoing the hero */}
      <div className="pointer-events-none absolute left-1/2 top-0 h-full w-px -translate-x-1/2 bg-gradient-to-b from-transparent via-line to-transparent" />

      <div className="relative mx-auto max-w-[1200px] px-5">
        <SectionHeader
          eyebrow="How it works"
          title={
            <>
              Three layers.
              <br />
              One platform.
            </>
          }
          copy="Your agent runs the workflow. Doomberg runs the tools, the execution, and the recording — research, deployment, and oversight in one trusted place."
        />

        <div className="mt-16 lg:mt-24">
          <IsometricStack />
        </div>

        {/* compact legend under the stack, mirrors the slabs top → bottom */}
        <div className="mx-auto mt-16 grid max-w-[920px] grid-cols-1 gap-px overflow-hidden rounded-2xl border border-line bg-line sm:grid-cols-3">
          {[
            ["Tools layer", "Vetted MCP tools your agent discovers and calls — typed I/O, provenance on every result."],
            ["Execution layer", "Declarative specs validated as data, backtested and paper-traded on trusted infra."],
            ["Observability layer", "Every call recorded to a replayable, audited event log — the glass box."],
          ].map(([t, b]) => (
            <div key={t} className="bg-paper p-6">
              <h3 className="text-lg text-ink">{t}</h3>
              <p className="mt-2 text-[0.92rem] leading-relaxed text-muted">{b}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
