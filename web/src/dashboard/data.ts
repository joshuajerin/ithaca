import type { DashboardRiskResponse, DashboardSummaryResponse, RunRow } from "../types";
import type { PerformancePnlData } from "./panels/PerformancePnlPanel";
import type { PortfolioRiskData } from "./panels/PortfolioRiskPanel";

function finite(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function performanceFromEvidence(
  curve: Array<{ d: string; v: number }>,
  stats: Record<string, number>,
  stale = false,
): PerformancePnlData | null {
  const valid = curve.filter(
    (point) => typeof point.d === "string" && Number.isFinite(point.v),
  );
  if (valid.length < 2) return null;

  const first = valid[0].v;
  if (first === 0) return null;
  let peak = first;
  const series = valid.map((point) => {
    peak = Math.max(peak, point.v);
    return {
      date: point.d,
      book: ((point.v - first) / Math.abs(first)) * 100,
      drawdown: peak === 0 ? 0 : ((point.v - peak) / Math.abs(peak)) * 100,
    };
  });

  return {
    portfolioName: "Portfolio",
    rangeLabel: "Recorded window",
    windowPoints: valid.length,
    series,
    stats: {
      totalReturn: finite(stats.totalReturn) ?? series.at(-1)?.book,
      cagr: finite(stats.cagr),
      vol: finite(stats.vol),
      sharpe: finite(stats.sharpe),
      sortino: finite(stats.sortino),
      maxDD: finite(stats.maxDD) ?? Math.min(...series.map((point) => point.drawdown)),
      hitRate: finite(stats.winRate),
    },
    stale,
  };
}

export function performanceFromDashboard(
  response: DashboardSummaryResponse | null,
): PerformancePnlData | null {
  const evidence = response?.data.latest_backtest;
  if (!evidence || !["ready", "stale"].includes(response.status)) return null;
  return performanceFromEvidence(evidence.equity_curve, evidence.stats, response.status === "stale");
}

export function performanceFromRuns(runs: RunRow[]): PerformancePnlData | null {
  const sorted = [...runs].sort((a, b) =>
    String(b.updated_at ?? b.created_at ?? "").localeCompare(
      String(a.updated_at ?? a.created_at ?? ""),
    ),
  );
  for (const run of sorted) {
    const result = run.result && typeof run.result === "object"
      ? (run.result as Record<string, unknown>)
      : {};
    const nested = result.data && typeof result.data === "object"
      ? (result.data as Record<string, unknown>)
      : result;
    const curve = Array.isArray(nested.equityCurve)
      ? nested.equityCurve as Array<{ d: string; v: number }>
      : [];
    const stats = nested.stats && typeof nested.stats === "object"
      ? nested.stats as Record<string, number>
      : {};
    const adapted = performanceFromEvidence(curve, stats);
    if (adapted) return adapted;
  }
  return null;
}

export function riskFromDashboard(
  response: DashboardRiskResponse | null,
): PortfolioRiskData | null {
  if (!response || !["ready", "stale"].includes(response.status)) return null;
  const metrics = response.data.backtest?.metrics ?? {};
  const book = response.data.paper_exposure;
  const holdings = Object.entries(book?.weights ?? {})
    .map(([symbol, weight]) => ({ symbol, weight }))
    .sort((a, b) => Math.abs(b.weight) - Math.abs(a.weight));
  const normalizedMetrics = Object.fromEntries(
    Object.entries(metrics).filter((entry): entry is [string, number] =>
      typeof entry[1] === "number" && Number.isFinite(entry[1]),
    ),
  );
  if (!book && Object.keys(normalizedMetrics).length === 0) return null;
  return {
    metrics: normalizedMetrics,
    holdings,
    capital: book?.capital ?? null,
    gross: book?.gross ?? null,
    cash: book?.cash ?? null,
    asOf: response.as_of,
    stale: response.status === "stale",
  };
}
