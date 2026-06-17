import { motion } from 'framer-motion';

export function DashboardMockup({ highlightRefine = false }: { highlightRefine?: boolean }) {
  return (
    <motion.div
      className="absolute inset-0 px-12 pt-20 pb-10 flex flex-col gap-5 z-10"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.5 }}
    >
      <div className="flex justify-between items-end px-1">
        <div className="flex flex-col gap-1">
          <span
            className="font-body uppercase text-white/45 text-[10px] font-medium"
            style={{ letterSpacing: '0.14em' }}
          >
            Live Analysis
          </span>
          <h2 className="font-display text-3xl text-white leading-none">
            NVDA · Supply Chain Risk
          </h2>
        </div>
        <div className="flex items-center gap-2">
          <motion.span
            className="w-2 h-2 rounded-full bg-white"
            animate={{ opacity: [1, 0.3, 1] }}
            transition={{ duration: 1.6, repeat: Infinity }}
          />
          <span
            className="font-body uppercase text-white/50 text-[10px]"
            style={{ letterSpacing: '0.2em' }}
          >
            Live Data
          </span>
        </div>
      </div>

      <div className="flex-1 grid grid-cols-12 grid-rows-3 gap-5">
        <Panel colSpan={8} rowSpan={2} title="Supply Chain Exposure" delay={0.15}>
          <div className="w-full h-full border border-white/5 bg-[#0a0a0a] flex items-center justify-center">
            <svg viewBox="0 0 400 200" className="w-full h-full opacity-70">
              <path
                d="M50 140 Q 150 60, 250 150 T 350 90"
                fill="none"
                stroke="white"
                strokeWidth="2"
                strokeDasharray="4 4"
              />
              <circle cx="50" cy="140" r="4" fill="white" />
              <circle cx="250" cy="150" r="6" fill="white" />
              <circle cx="350" cy="90" r="4" fill="white" />
            </svg>
          </div>
        </Panel>

        <Panel colSpan={4} rowSpan={1} title="Sentiment Trend" delay={0.3}>
          <div className="flex items-end h-full gap-2 px-2 pb-1">
            {[40, 60, 45, 80, 50, 90, 75, 100].map((h, i) => (
              <motion.div
                key={i}
                className="w-full bg-white/25 origin-bottom"
                style={{ height: `${h}%` }}
                initial={{ scaleY: 0 }}
                animate={{ scaleY: 1 }}
                transition={{ delay: 0.6 + i * 0.05, duration: 0.4 }}
              />
            ))}
          </div>
        </Panel>

        <Panel colSpan={4} rowSpan={2} title="Factor Analysis" delay={0.45}>
          <div className="flex flex-col gap-4 justify-center h-full px-1">
            {[
              { f: 'Value', v: '+0.42', w: 72 },
              { f: 'Momentum', v: '+0.88', w: 90 },
              { f: 'Quality', v: '+0.31', w: 55 },
              { f: 'Volatility', v: '-0.54', w: 44 },
            ].map((row, i) => (
              <div key={i} className="flex flex-col gap-1">
                <div className="flex justify-between text-[11px] text-white/60 font-body uppercase tracking-wider">
                  <span>{row.f}</span>
                  <span className="tabular-nums">{row.v}</span>
                </div>
                <div className="h-1 bg-white/10 w-full overflow-hidden">
                  <motion.div
                    className="h-full bg-white origin-left"
                    style={{ width: `${row.w}%` }}
                    initial={{ scaleX: 0 }}
                    animate={{ scaleX: 1 }}
                    transition={{ delay: 0.8 + i * 0.1, duration: 0.6 }}
                  />
                </div>
              </div>
            ))}
          </div>
        </Panel>

        <Panel
          colSpan={4}
          rowSpan={1}
          title="Monte Carlo Sim"
          delay={0.6}
          highlight={highlightRefine}
        >
          <div className="w-full h-full flex items-center justify-center">
            <svg viewBox="0 0 200 100" className="w-full h-full opacity-80">
              {[...Array(8)].map((_, i) => (
                <motion.path
                  key={i}
                  d={`M0 50 Q 50 ${50 + (i - 4) * 10}, 100 ${50 + (i - 4) * 15} T 200 ${50 + (i - 4) * 24}`}
                  fill="none"
                  stroke="rgba(255,255,255,0.28)"
                  strokeWidth="1"
                  initial={{ pathLength: 0 }}
                  animate={{ pathLength: 1 }}
                  transition={{ delay: 0.9 + i * 0.05, duration: 1.2 }}
                />
              ))}
              <path d="M0 50 Q 50 40, 100 30 T 200 12" fill="none" stroke="white" strokeWidth="2" />
            </svg>
          </div>
        </Panel>

        <Panel colSpan={4} rowSpan={1} title="Implied Vol Surface" delay={0.75}>
          <div className="w-full h-full border border-white/5 bg-[radial-gradient(ellipse_at_center,rgba(255,255,255,0.12),transparent_70%)]" />
        </Panel>
      </div>
    </motion.div>
  );
}

function Panel({
  colSpan,
  rowSpan,
  title,
  children,
  delay,
  highlight = false,
}: {
  colSpan: number;
  rowSpan: number;
  title: string;
  children: React.ReactNode;
  delay: number;
  highlight?: boolean;
}) {
  return (
    <motion.div
      className={`bg-[#080808] border p-4 flex flex-col relative overflow-hidden transition-shadow duration-500 ${
        highlight
          ? 'border-white shadow-[0_0_0_1px_rgba(255,255,255,0.8),0_0_36px_rgba(255,255,255,0.45)]'
          : 'border-[#262626]'
      }`}
      style={{ gridColumn: `span ${colSpan}`, gridRow: `span ${rowSpan}` }}
      initial={{ opacity: 0, y: 14, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ delay, duration: 0.55, ease: [0.16, 1, 0.3, 1] }}
    >
      <div className="flex flex-col gap-0.5 mb-3 relative z-10">
        <span
          className="font-body text-[8.5px] uppercase text-white/45 font-medium"
          style={{ letterSpacing: '0.14em' }}
        >
          Analytics
        </span>
        <h3 className="font-display text-lg text-white leading-none">{title}</h3>
      </div>
      <div className="flex-1 relative z-10 min-h-0">{children}</div>
    </motion.div>
  );
}
