---
name: Panel CSV/PDF export
description: How client-side quant-panel export works and why html2canvas-pro is required under Tailwind v4.
---

# Panel CSV/PDF export

Client-side export of quant panels lives in `artifacts/terminal/src/lib/panelExport.ts`
and is wired into the panel toolbar in `PanelContainer.tsx` (Download icon → CSV / PDF menu),
gated by `EXPORTABLE_PANEL_TYPES`.

## Must use html2canvas-pro, not html2canvas
**Rule:** for DOM-snapshot/PDF capture in the terminal artifact, import `html2canvas-pro`, never `html2canvas`.
**Why:** the terminal is on Tailwind v4, whose theme tokens (border, muted, etc.) resolve to
`oklch(...)`. Stock html2canvas throws "unsupported color function 'oklch'" and the export fails.
`html2canvas-pro` is a drop-in fork that parses oklch/lab/lch.
**How to apply:** PDF export = html2canvas-pro (capture element) + jsPDF (place PNG on A4, black bg).
Both are dynamically `import()`ed so they code-split out of the main bundle.

## CSV shape
`buildPanelCsv(type, data)` emits a single sectioned CSV string (header rows + blank-line
separated tables) directly from each panel's typed data — no backend involved. Add a new panel
type by writing a `*Rows` builder + a `case` and adding the type to `EXPORTABLE_PANEL_TYPES`.

## Stale shared-types gotcha
The shared data types (`PortfolioRiskData`, etc.) come from `@workspace/api-client-react`.
Its `package.json` exports point at `src/index.ts` (so Vite/runtime is always fresh), but tsc
project references consume the built `lib/api-client-react/dist/*.d.ts`. If a new file imports a
type that tsc claims "has no exported member" while existing files don't, the dist declarations
are stale — rebuild with `tsc -p lib/api-client-react/tsconfig.json`.
