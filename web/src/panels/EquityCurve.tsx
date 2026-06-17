// Dependency-free equity curve: a single SVG polyline + an optional drawdown shade.
// Keeps the bundle light (no chart lib) while matching the v1 terminal look.

interface Point {
  d: string;
  v: number;
}

export function EquityCurve({ points, height = 200 }: { points: Point[]; height?: number }) {
  if (!points || points.length < 2) {
    return <div className="empty">No equity data.</div>;
  }
  const W = 800;
  const H = height;
  const pad = { t: 8, r: 8, b: 18, l: 48 };
  const xs = points.map((_, i) => i);
  const vs = points.map((p) => p.v);
  const minV = Math.min(...vs);
  const maxV = Math.max(...vs);
  const spanV = maxV - minV || 1;
  const minX = 0;
  const maxX = xs.length - 1 || 1;

  const px = (i: number) => pad.l + ((i - minX) / (maxX - minX)) * (W - pad.l - pad.r);
  const py = (v: number) => pad.t + (1 - (v - minV) / spanV) * (H - pad.t - pad.b);

  const line = points.map((p, i) => `${i === 0 ? "M" : "L"}${px(i).toFixed(1)},${py(p.v).toFixed(1)}`).join(" ");
  const area = `${line} L${px(maxX).toFixed(1)},${py(minV).toFixed(1)} L${px(minX).toFixed(1)},${py(minV).toFixed(1)} Z`;

  const last = points[points.length - 1].v;
  const first = points[0].v;
  const up = last >= first;
  const stroke = up ? "var(--pos)" : "var(--neg)";

  const yTicks = [maxV, minV + spanV / 2, minV];
  const fmt = (v: number) => (Math.abs(v) >= 1000 ? `${(v / 1000).toFixed(1)}k` : v.toFixed(2));

  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" height={H} preserveAspectRatio="none" role="img" aria-label="equity curve">
      <defs>
        <linearGradient id="eqGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={stroke} stopOpacity={0.22} />
          <stop offset="100%" stopColor={stroke} stopOpacity={0.02} />
        </linearGradient>
      </defs>
      {yTicks.map((v, i) => (
        <g key={i}>
          <line x1={pad.l} x2={W - pad.r} y1={py(v)} y2={py(v)} stroke="#1a1a1a" strokeWidth={1} />
          <text x={pad.l - 6} y={py(v) + 3} fontSize={9} fill="#555" textAnchor="end" fontFamily="var(--font-mono)">
            {fmt(v)}
          </text>
        </g>
      ))}
      <path d={area} fill="url(#eqGrad)" stroke="none" />
      <path d={line} fill="none" stroke={stroke} strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
      <text x={pad.l} y={H - 4} fontSize={9} fill="#555" fontFamily="var(--font-mono)">
        {points[0].d}
      </text>
      <text x={W - pad.r} y={H - 4} fontSize={9} fill="#555" textAnchor="end" fontFamily="var(--font-mono)">
        {points[points.length - 1].d}
      </text>
    </svg>
  );
}
