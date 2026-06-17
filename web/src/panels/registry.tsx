import type { ComponentType } from "react";
import { BacktestPanel } from "./BacktestPanel";
import { JsonPanel } from "./JsonPanel";

// STATIC panelType -> renderer registry. SECURITY INVARIANT: this is a fixed lookup table.
// There is NO eval, NO sucrase, NO dynamic import of agent-authored code (the v1 RCE lesson).
// An unknown panelType falls back to the generic JSON/table renderer.
export interface PanelProps {
  data: unknown;
}

const REGISTRY: Record<string, ComponentType<PanelProps>> = {
  backtest: BacktestPanel,
  "backtest.run": BacktestPanel,
  json: JsonPanel,
  table: JsonPanel,
};

export function resolvePanel(panelType: string | undefined): ComponentType<PanelProps> {
  if (panelType && Object.prototype.hasOwnProperty.call(REGISTRY, panelType)) {
    return REGISTRY[panelType];
  }
  return JsonPanel;
}

export function Panel({ panelType, data }: { panelType?: string; data: unknown }) {
  const Renderer = resolvePanel(panelType);
  return <Renderer data={data} />;
}
