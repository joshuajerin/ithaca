import type React from "react";

// Vite eagerly imports every AI-generated panel component in this directory.
// Each module's filename (minus extension) is the panel `type`, and each must
// have a default-exported React component accepting `{ data }`.
// When the Build Feature flow writes a new <panel_type>.tsx here, Vite's dev
// server picks it up via HMR and this map updates — no manual wiring needed.
const modules = import.meta.glob<{ default: React.ComponentType<{ data: any }> }>(
  "./*.tsx",
  { eager: true },
);

export type GeneratedComponent = React.ComponentType<{ data: any }>;

const registry: Record<string, GeneratedComponent> = {};

for (const [path, mod] of Object.entries(modules)) {
  const match = path.match(/\.\/(.+)\.tsx$/);
  if (!match) continue;
  const panelType = match[1];
  if (mod && mod.default) {
    registry[panelType] = mod.default;
  }
}

export function getGeneratedComponent(panelType: string): GeneratedComponent | undefined {
  return registry[panelType];
}

export function hasGeneratedComponent(panelType: string): boolean {
  return panelType in registry;
}
