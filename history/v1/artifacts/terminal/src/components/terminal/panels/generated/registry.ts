import type React from "react";
import ReactDefault from "react";

// AI-generated panel components are resolved through TWO paths:
//
// 1. STATIC (build-time): Vite eagerly imports every `*.tsx` already present in
//    this directory when the app is built/dev-served. Each module's filename
//    (minus extension) is the panel `type`, with a default-exported component
//    accepting `{ data }`. In the dev server, HMR also picks up freshly written
//    files here — so panels authored at runtime appear without a reload.
//
// 2. RUNTIME (production): A built/deployed app has no HMR and no way to bundle a
//    `.tsx` that was written after the build. For those, we fetch the component
//    source from the backend (`GET /api/generated-panels`), transpile the TSX in
//    the browser with sucrase, and evaluate it into a React component — no
//    dev-server dependency. Results are cached so each panel compiles once.
//
// Either way, `DynamicPanel` falls back to the generic JSON renderer if a
// component is missing or fails to load/compile, so a panel never blanks/crashes.
//
// `import.meta.glob` is a Vite compile-time macro: in a real build/dev it is
// replaced with a static object literal of the matched modules. Outside Vite
// (e.g. the Node test runner that exercises the runtime compile path) the call
// has no implementation and throws, so we guard it and fall back to an empty
// static registry — which is exactly the state a production runtime is in for a
// panel authored after the build.
let modules: Record<string, { default: React.ComponentType<{ data: any }> }> = {};
try {
  modules = import.meta.glob<{ default: React.ComponentType<{ data: any }> }>(
    "./*.tsx",
    { eager: true },
  );
} catch {
  modules = {};
}

export type GeneratedComponent = React.ComponentType<{ data: any }>;

const staticRegistry: Record<string, GeneratedComponent> = {};

for (const [path, mod] of Object.entries(modules)) {
  const match = path.match(/\.\/(.+)\.tsx$/);
  if (!match) continue;
  const panelType = match[1];
  if (mod && mod.default) {
    staticRegistry[panelType] = mod.default;
  }
}

// Components compiled at runtime from fetched source (keyed by panel type).
const runtimeRegistry: Record<string, GeneratedComponent> = {};
// In-flight compile promises, so concurrent requests for the same type share work.
const pending: Record<string, Promise<GeneratedComponent | undefined>> = {};

export function getGeneratedComponent(panelType: string): GeneratedComponent | undefined {
  return staticRegistry[panelType] ?? runtimeRegistry[panelType];
}

export function hasGeneratedComponent(panelType: string): boolean {
  return panelType in staticRegistry || panelType in runtimeRegistry;
}

// Transpile a generated TSX module source into a live React component. The
// generated contract only allows `import React from "react"`, which we satisfy
// with a require shim; any other import is rejected so evaluation stays bounded.
async function compileComponent(source: string): Promise<GeneratedComponent> {
  // Load the in-browser TSX compiler on demand so it stays out of the initial
  // bundle — most sessions never build a custom panel, so the ~MB sucrase chunk
  // is only fetched the first time a runtime panel actually needs compiling.
  const { transform } = await import("sucrase");
  const { code } = transform(source, {
    transforms: ["typescript", "jsx", "imports"],
    production: true,
  });

  const moduleObj: { exports: any } = { exports: {} };
  const requireShim = (name: string) => {
    if (name === "react") return ReactDefault;
    throw new Error(`Generated panel may not import "${name}"`);
  };

  // eslint-disable-next-line no-new-func
  const factory = new Function("require", "module", "exports", code);
  factory(requireShim, moduleObj, moduleObj.exports);

  const Component = moduleObj.exports?.default;
  if (typeof Component !== "function") {
    throw new Error("Generated panel has no default-exported component");
  }
  return Component as GeneratedComponent;
}

// Fetch + compile a single generated panel by type. Resolves to the component, or
// undefined if it doesn't exist on the backend or fails to compile. Never throws.
export async function loadGeneratedComponent(
  panelType: string,
): Promise<GeneratedComponent | undefined> {
  const existing = getGeneratedComponent(panelType);
  if (existing) return existing;
  if (panelType in pending) return pending[panelType];

  const task = (async () => {
    try {
      const res = await fetch("/api/generated-panels");
      if (!res.ok) return undefined;
      const payload = (await res.json()) as {
        panels?: { panelType: string; source: string }[];
      };
      const entry = payload.panels?.find((p) => p.panelType === panelType);
      if (!entry?.source) return undefined;
      const Component = await compileComponent(entry.source);
      runtimeRegistry[panelType] = Component;
      return Component;
    } catch (err) {
      console.error(`Failed to load generated panel "${panelType}" at runtime:`, err);
      return undefined;
    } finally {
      delete pending[panelType];
    }
  })();

  pending[panelType] = task;
  return task;
}
