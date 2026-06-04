import React, { useState } from "react";
import { ScrollArea } from "@/components/ui/scroll-area";

interface SCNode {
  id: string;
  name: string;
  symbol?: string | null;
  role: string;
  exposure: number;
  country: string;
}

interface SCEdge {
  source: string;
  target: string;
  weight: number;
}

interface SCTableRow {
  name: string;
  symbol?: string | null;
  role: string;
  exposure: number;
  country: string;
  category: string;
}

interface SupplyChainData {
  symbol: string;
  name: string;
  nodes: SCNode[];
  edges: SCEdge[];
  table: SCTableRow[];
}

const ROLE_COLOR: Record<string, string> = {
  subject: "#ffffff",
  supplier: "#60a5fa",
  customer: "#34d399",
};

const ROLE_BORDER: Record<string, string> = {
  subject: "border-white",
  supplier: "border-blue-400",
  customer: "border-emerald-400",
};

const ROLE_TEXT: Record<string, string> = {
  subject: "text-white",
  supplier: "text-blue-400",
  customer: "text-emerald-400",
};

function SupplyChainSVG({ nodes, edges, subjectId }: { nodes: SCNode[]; edges: SCEdge[]; subjectId: string }) {
  const [hovered, setHovered] = useState<string | null>(null);
  const W = 560, H = 280;
  const cx = W / 2, cy = H / 2;

  const suppliers = nodes.filter(n => n.role === "supplier");
  const customers = nodes.filter(n => n.role === "customer");
  const subject = nodes.find(n => n.role === "subject");

  const posMap: Record<string, { x: number; y: number }> = {};
  posMap[subjectId] = { x: cx, y: cy };

  const spreadY = (items: SCNode[], xPos: number) => {
    const count = items.length;
    items.forEach((n, i) => {
      const spacing = Math.min(52, (H - 40) / Math.max(count, 1));
      const totalHeight = spacing * (count - 1);
      const startY = cy - totalHeight / 2;
      posMap[n.id] = { x: xPos, y: startY + i * spacing };
    });
  };

  spreadY(suppliers, 80);
  spreadY(customers, W - 80);

  const getRadius = (n: SCNode) => n.role === "subject" ? 22 : 8 + (n.exposure / 100) * 10;

  return (
    <svg width="100%" viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ maxHeight: 200 }}>
      {edges.map((e, i) => {
        const s = posMap[e.source];
        const t = posMap[e.target];
        if (!s || !t) return null;
        const isHov = hovered === e.source || hovered === e.target;
        const opacity = hovered ? (isHov ? 0.9 : 0.15) : 0.4;
        const stroke = nodes.find(n => n.id === e.source)?.role === "supplier" ? "#60a5fa" : "#34d399";
        return (
          <line
            key={i}
            x1={s.x} y1={s.y} x2={t.x} y2={t.y}
            stroke={stroke}
            strokeWidth={0.5 + (e.weight / 100) * 2.5}
            strokeOpacity={opacity}
            strokeDasharray={e.source === subjectId || e.target === subjectId ? "none" : "4 2"}
          />
        );
      })}
      {nodes.map(n => {
        const pos = posMap[n.id];
        if (!pos) return null;
        const r = getRadius(n);
        const color = ROLE_COLOR[n.role] || "#888";
        const isHov = hovered === n.id;
        const opacity = hovered ? (isHov ? 1 : 0.3) : 0.85;
        const isLeft = pos.x < cx;
        const labelX = n.role === "subject" ? pos.x : (isLeft ? pos.x - r - 5 : pos.x + r + 5);
        const anchor = n.role === "subject" ? "middle" : (isLeft ? "end" : "start");
        return (
          <g
            key={n.id}
            onMouseEnter={() => setHovered(n.id)}
            onMouseLeave={() => setHovered(null)}
            style={{ cursor: "pointer" }}
          >
            <circle
              cx={pos.x} cy={pos.y} r={r}
              fill={color}
              fillOpacity={opacity * (n.role === "subject" ? 0.2 : 0.15)}
              stroke={color}
              strokeOpacity={opacity}
              strokeWidth={n.role === "subject" ? 2 : 1}
            />
            <text
              x={labelX}
              y={pos.y + (n.role === "subject" ? r + 14 : 3.5)}
              textAnchor={anchor}
              fontSize={n.role === "subject" ? 11 : 9}
              fill={color}
              fillOpacity={opacity}
              fontWeight={n.role === "subject" ? "bold" : "normal"}
            >
              {n.role === "subject" ? n.symbol || n.name : n.name.split(" ")[0]}
            </text>
            {isHov && n.role !== "subject" && (
              <text
                x={labelX}
                y={pos.y + (isLeft ? 3.5 : 3.5) + 11}
                textAnchor={anchor}
                fontSize={8}
                fill="#888"
                fillOpacity={0.9}
              >
                {n.exposure}% exposure
              </text>
            )}
          </g>
        );
      })}
      <text x={85} y={18} fontSize={8} fill="#60a5fa" fillOpacity={0.7} textAnchor="middle">SUPPLIERS</text>
      <text x={W - 85} y={18} fontSize={8} fill="#34d399" fillOpacity={0.7} textAnchor="middle">CUSTOMERS</text>
    </svg>
  );
}

export function SupplyChainPanel({ data }: { data: SupplyChainData }) {
  const [tab, setTab] = useState<"graph" | "table">("graph");
  const suppliers = data.table.filter(r => r.role === "supplier").sort((a, b) => b.exposure - a.exposure);
  const customers = data.table.filter(r => r.role === "customer").sort((a, b) => b.exposure - a.exposure);

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-baseline justify-between mb-3 shrink-0">
        <div>
          <span className="text-xs font-bold uppercase">{data.symbol}</span>
          <span className="text-[10px] text-muted-foreground ml-2 uppercase">{data.name} Supply Chain</span>
        </div>
        <div className="flex gap-1">
          {(["graph", "table"] as const).map(t => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`text-[10px] uppercase tracking-widest px-2 py-0.5 border transition-colors ${tab === t ? "border-white text-white bg-white/10" : "border-border text-muted-foreground hover:border-gray-500"}`}
            >
              {t}
            </button>
          ))}
        </div>
      </div>

      <div className="flex gap-2 mb-2 shrink-0">
        <span className="flex items-center gap-1 text-[9px] text-blue-400"><span className="w-2 h-2 rounded-full bg-blue-400/60 inline-block" />Supplier</span>
        <span className="flex items-center gap-1 text-[9px] text-emerald-400"><span className="w-2 h-2 rounded-full bg-emerald-400/60 inline-block" />Customer</span>
        <span className="flex items-center gap-1 text-[9px] text-white"><span className="w-2 h-2 rounded-full bg-white/60 inline-block" />Subject</span>
      </div>

      {tab === "graph" ? (
        <div className="flex-1 min-h-0 flex flex-col">
          <SupplyChainSVG nodes={data.nodes} edges={data.edges} subjectId={data.symbol} />
          <div className="mt-2 grid grid-cols-2 gap-2 text-[9px] shrink-0">
            <div>
              <div className="text-blue-400 uppercase tracking-wider mb-1 font-bold">Top Suppliers</div>
              {suppliers.slice(0, 3).map((r, i) => (
                <div key={i} className="flex justify-between text-muted-foreground hover:text-white transition-colors py-0.5">
                  <span className="truncate max-w-[120px]">{r.name}</span>
                  <span className="text-blue-400 font-mono ml-1">{r.exposure}%</span>
                </div>
              ))}
            </div>
            <div>
              <div className="text-emerald-400 uppercase tracking-wider mb-1 font-bold">Top Customers</div>
              {customers.slice(0, 3).map((r, i) => (
                <div key={i} className="flex justify-between text-muted-foreground hover:text-white transition-colors py-0.5">
                  <span className="truncate max-w-[120px]">{r.name}</span>
                  <span className="text-emerald-400 font-mono ml-1">{r.exposure}%</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      ) : (
        <ScrollArea className="flex-1 min-h-0">
          <table className="w-full text-xs border-collapse">
            <thead>
              <tr className="border-b border-border">
                <th className="text-left text-[10px] text-muted-foreground uppercase py-1.5 pr-2">Name</th>
                <th className="text-left text-[10px] text-muted-foreground uppercase py-1.5 pr-2">Role</th>
                <th className="text-left text-[10px] text-muted-foreground uppercase py-1.5 pr-2">Category</th>
                <th className="text-right text-[10px] text-muted-foreground uppercase py-1.5">Exposure</th>
              </tr>
            </thead>
            <tbody>
              {data.table.map((row, i) => (
                <tr key={i} className="border-b border-border/30 hover:bg-white/5 transition-colors">
                  <td className="py-1.5 pr-2">
                    <span className="font-bold">{row.name}</span>
                    {row.symbol && <span className="text-muted-foreground ml-1">{row.symbol}</span>}
                  </td>
                  <td className={`py-1.5 pr-2 text-[10px] uppercase font-bold ${ROLE_TEXT[row.role] || "text-muted-foreground"}`}>
                    {row.role}
                  </td>
                  <td className="py-1.5 pr-2 text-muted-foreground text-[10px]">{row.category}</td>
                  <td className={`py-1.5 text-right font-mono font-bold ${ROLE_TEXT[row.role] || "text-white"}`}>
                    {row.exposure}%
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </ScrollArea>
      )}
    </div>
  );
}
