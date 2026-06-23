// @ts-nocheck
import type {
  PortfolioRiskData,
  BacktestData,
  CorrelationMatrixData,
  FactorAnalysisData,
} from "@workspace/api-client-react";

type Row = (string | number | null | undefined)[];

function csvCell(value: string | number | null | undefined): string {
  if (value === null || value === undefined) return "";
  const s = String(value);
  if (/[",\n]/.test(s)) {
    return `"${s.replace(/"/g, '""')}"`;
  }
  return s;
}

function rowsToCsv(rows: Row[]): string {
  return rows.map((r) => r.map(csvCell).join(",")).join("\n");
}

function slugify(s: string): string {
  return s
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 60) || "panel";
}

function triggerDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export const EXPORTABLE_PANEL_TYPES = new Set([
  "portfolio_risk",
  "backtest",
  "correlation_matrix",
  "factor_analysis",
]);

function portfolioRiskRows(d: PortfolioRiskData): Row[] {
  const rows: Row[] = [];
  rows.push(["Portfolio Risk", d.portfolioName]);
  rows.push([]);
  rows.push(["Summary"]);
  rows.push(["Metric", "Value"]);
  rows.push(["1-Day 95% VaR (%)", -d.summary.var95]);
  if (d.summary.cvar95 !== undefined && d.summary.cvar95 !== null) {
    rows.push(["1-Day 95% CVaR (%)", -d.summary.cvar95]);
  }
  rows.push(["Tracking Error (%)", d.summary.trackingError]);
  rows.push(["Portfolio Beta", d.summary.beta]);
  rows.push([]);
  rows.push(["Factor Exposures"]);
  rows.push(["Factor", "Exposure"]);
  d.factorExposures.forEach((f) => rows.push([f.factor, f.exposure]));
  rows.push([]);
  rows.push(["P&L Distribution (VaR Histogram)"]);
  rows.push(["Bin (%)", "Count"]);
  d.varHistogram.forEach((b) => rows.push([b.bin, b.count]));
  rows.push([]);
  rows.push(["Holdings"]);
  d.symbols.forEach((s) => rows.push([s]));
  return rows;
}

function backtestRows(d: BacktestData): Row[] {
  const rows: Row[] = [];
  rows.push(["Backtest", `${d.strategy} · ${d.symbol}`]);
  rows.push([]);
  rows.push(["Statistics"]);
  rows.push(["Metric", "Value"]);
  rows.push(["Sharpe", d.stats.sharpe]);
  rows.push(["Sortino", d.stats.sortino]);
  rows.push(["CAGR (%)", d.stats.cagr]);
  rows.push(["Max Drawdown (%)", d.stats.maxDD]);
  rows.push(["Win Rate (%)", d.stats.winRate]);
  if (d.stats.totalReturn !== undefined && d.stats.totalReturn !== null) rows.push(["Total Return (%)", d.stats.totalReturn]);
  if (d.stats.vol !== undefined && d.stats.vol !== null) rows.push(["Volatility (%)", d.stats.vol]);
  if (d.stats.turnover !== undefined && d.stats.turnover !== null) rows.push(["Turnover", d.stats.turnover]);
  if (d.stats.var95 !== undefined && d.stats.var95 !== null) rows.push(["VaR 95 (%)", d.stats.var95]);
  if (d.stats.cvar95 !== undefined && d.stats.cvar95 !== null) rows.push(["CVaR 95 (%)", d.stats.cvar95]);
  rows.push([]);
  rows.push(["Equity Curve (rebased 100)"]);
  rows.push(["Date", "Strategy", "Benchmark"]);
  d.curve.forEach((p) => rows.push([p.t, p.strategy, p.benchmark]));
  rows.push([]);
  rows.push(["Drawdown"]);
  rows.push(["Date", "Drawdown (%)"]);
  d.drawdown.forEach((p) => rows.push([p.t, p.dd]));
  if (d.tradeLog && d.tradeLog.length) {
    rows.push([]);
    rows.push(["Trade Log"]);
    rows.push(["Date", "Action", "Price", "From Pos", "To Pos", "P&L (pts)", "P&L (%)"]);
    d.tradeLog.forEach((t) =>
      rows.push([t.t, t.action, t.price, t.fromPos, t.toPos, t.pnl, t.pnlPct]),
    );
  }
  return rows;
}

function correlationRows(d: CorrelationMatrixData): Row[] {
  const rows: Row[] = [];
  rows.push(["Correlation Matrix", `${d.window}D window`]);
  rows.push([]);
  rows.push(["Pairwise Correlations"]);
  rows.push(["", ...d.symbols]);
  d.symbols.forEach((sym, i) => {
    rows.push([sym, ...d.matrix[i]]);
  });
  rows.push([]);
  rows.push(["Beta & Hedge Ratio"]);
  rows.push(["Symbol", "Beta", "Hedge Ratio"]);
  d.betas.forEach((b) => rows.push([b.symbol, b.beta, b.hedgeRatio]));
  return rows;
}

function factorAnalysisRows(d: FactorAnalysisData): Row[] {
  const rows: Row[] = [];
  rows.push(["Factor Analysis", `${d.name} (${d.symbol})`]);
  rows.push([]);
  rows.push(["Factor Loadings"]);
  rows.push(["Factor", "Loading", "t-Stat", "Contribution (%)"]);
  d.loadings.forEach((l) => rows.push([l.factor, l.loading, l.tStat, l.contribution]));
  rows.push([]);
  rows.push(["Monthly Attribution (%)"]);
  rows.push(["Month", "Momentum", "Value", "Size", "Quality", "Residual"]);
  d.monthlyAttribution.forEach((m) =>
    rows.push([m.month, m.momentum, m.value, m.size, m.quality, m.residual]),
  );
  return rows;
}

export function buildPanelCsv(type: string, data: unknown): string | null {
  switch (type) {
    case "portfolio_risk":
      return rowsToCsv(portfolioRiskRows(data as PortfolioRiskData));
    case "backtest":
      return rowsToCsv(backtestRows(data as BacktestData));
    case "correlation_matrix":
      return rowsToCsv(correlationRows(data as CorrelationMatrixData));
    case "factor_analysis":
      return rowsToCsv(factorAnalysisRows(data as FactorAnalysisData));
    default:
      return null;
  }
}

export function exportPanelCsv(type: string, title: string, data: unknown): boolean {
  const csv = buildPanelCsv(type, data);
  if (csv === null) return false;
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  triggerDownload(blob, `${slugify(title)}.csv`);
  return true;
}

export async function exportPanelPdf(element: HTMLElement, title: string): Promise<void> {
  const [{ default: html2canvas }, { jsPDF }] = await Promise.all([
    import("html2canvas-pro"),
    import("jspdf"),
  ]);

  const canvas = await html2canvas(element, {
    backgroundColor: "#000000",
    scale: 2,
    logging: false,
    useCORS: true,
  });

  const imgData = canvas.toDataURL("image/png");
  const orientation = canvas.width >= canvas.height ? "landscape" : "portrait";
  const pdf = new jsPDF({ orientation, unit: "pt", format: "a4" });

  const pageW = pdf.internal.pageSize.getWidth();
  const pageH = pdf.internal.pageSize.getHeight();
  const margin = 24;
  const maxW = pageW - margin * 2;
  const maxH = pageH - margin * 2;

  const ratio = Math.min(maxW / canvas.width, maxH / canvas.height);
  const drawW = canvas.width * ratio;
  const drawH = canvas.height * ratio;
  const x = (pageW - drawW) / 2;
  const y = (pageH - drawH) / 2;

  pdf.setFillColor(0, 0, 0);
  pdf.rect(0, 0, pageW, pageH, "F");
  pdf.addImage(imgData, "PNG", x, y, drawW, drawH);
  pdf.save(`${slugify(title)}.pdf`);
}
