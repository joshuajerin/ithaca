# Dashboard Analyst Ratings Widget Plan

## Goal

Implement the old Doomberg-style `AnalystRatingsPanel` as a real subwidget on the authenticated `/dashboard` page.

The target visual is the screenshot-approved compact terminal panel: black card, serif symbol and consensus header, price target strip, rating distribution bars, and recent analyst upgrade/downgrade rows.

## Current-state findings

- `web/src/App.tsx` routes authenticated users to `/dashboard` through `web/src/pages/Dashboard.tsx`; no route changes are needed.
- `web/src/pages/Dashboard.tsx` currently renders a hand-built terminal dashboard with sections for price chart, session tape, generic subwidgets, news flow, options/trade flow, and deployment activity.
- `web/src/pages/Dashboard.tsx` already depends on class names like `terminal-grid`, `terminal-panel`, `price-panel`, `terminal-panel-head`, `price-chart`, `range-row`, `mini-grid`, `news-flow`, and `mini-table`.
- `web/src/index.css` currently has no `terminal-*`, `price-panel`, `mini-grid`, `news-flow`, or related rules. That means the existing dashboard markup does not yet have the visual system needed for the old Doomberg widget look.
- The archived source for the old analyst widget is `history/v1/artifacts/terminal/src/components/terminal/panels/AnalystRatingsPanel.tsx`.
- The old panel source depends on v1-only pieces: Tailwind utility classes, `ScrollArea` from the archived shadcn UI folder, and `lucide-react` icons.
- The current web app dependencies in `web/package.json` do not include `lucide-react`, `framer-motion`, `recharts`, Tailwind, or the archived `@workspace/api-client-react` package. Porting the widget should avoid adding those dependencies for this narrow dashboard change.
- The old `PanelContainer` registry in `history/v1/artifacts/terminal/src/components/terminal/PanelContainer.tsx` maps `analyst_ratings` to `AnalystRatingsPanel`, but the current v2 web app does not use that registry.

## Target design

Add a v2-local analyst ratings card that preserves the old v1 visual and data shape without importing the whole v1 terminal stack.

The dashboard should contain a dedicated `AnalystRatingsWidget` inside the existing `/dashboard` grid. It should use local typed sample data for now, matching the screenshot:

- `symbol`: `NVDA`
- `name`: `NVIDIA Corporation`
- `consensus`: `Strong Buy`, `46 analysts`, `4.62/5`
- price target metrics: current, target, range, implied upside
- distribution rows: Strong Buy, Buy, Hold, Sell, Strong Sell
- recent changes: Morgan Stanley, Goldman Sachs, UBS

The component should be self-contained in the dashboard page or a small local dashboard widget file. Since the current app has no dashboard widget folder yet, the minimal implementation is:

- define local data and helper functions in `web/src/pages/Dashboard.tsx`
- render `AnalystRatingsWidget` as another `terminal-panel`
- add CSS classes in `web/src/index.css` for the old dark terminal widget styling

## Concrete sequence of changes

1. Update `web/src/pages/Dashboard.tsx`.
   - Add typed data interfaces for distribution, consensus, price target, rating changes, and the analyst ratings widget data.
   - Add `ANALYST_RATINGS` sample data using the screenshot-approved NVDA values.
   - Add an `AnalystRatingsWidget` component.
   - Add small helper functions:
     - `fmtUsd(n)` for prices
     - `ratingPct(value, total)` for bar widths
     - `actionArrow(action)` for text arrows instead of adding `lucide-react`
   - Insert the widget into the `terminal-grid`, preferably near the price chart and news/flow widgets so it reads like a market terminal board.

2. Update `web/src/index.css`.
   - Add missing dashboard terminal styles for the current dashboard classes:
     - `.terminal-page`
     - `.terminal-topbar`
     - `.terminal-actions`
     - `.ticker-chip`
     - `.terminal-grid`
     - `.terminal-panel`
     - `.terminal-panel-head`
     - `.price-panel`
     - `.price-shell`
     - `.price-symbol`
     - `.price-quote`
     - `.price-last`
     - `.price-change`
     - `.price-chart`
     - `.range-row`
     - `.mini-grid`
     - `.mini`
     - `.subwidget-stack`
     - `.subwidget`
     - `.news-flow`
     - `.news-row`
     - `.mini-table`
     - `.terminal-list-row`
     - `.terminal-row-title`
   - Add analyst-specific styles:
     - `.analyst-panel`
     - `.analyst-head`
     - `.analyst-symbol`
     - `.analyst-name`
     - `.analyst-consensus`
     - `.analyst-grade`
     - `.analyst-meta`
     - `.analyst-strip`
     - `.analyst-metric`
     - `.analyst-section`
     - `.analyst-section-title`
     - `.rating-row`
     - `.rating-bar`
     - `.rating-fill`
     - `.rating-count`
     - `.change-row`
     - `.change-arrow`
     - `.change-firm`
     - `.change-action`
     - `.change-date`
   - Keep the dark widget self-contained inside `.terminal-panel` so the rest of the app can remain the warm light shell.
   - Add mobile behavior under the existing `@media (max-width: 920px)` block so the analyst strip and change rows do not overflow.

3. Leave routing and API code unchanged.
   - No backend change is needed for this implementation because the user asked to implement the dashboard UI panel, not live analyst data ingestion.
   - A later pass can wire `AnalystRatingsWidget` to real MCP/tool output or REST data.

## Interfaces and data flow affected

- No external API contract changes.
- No REST or MCP endpoints change.
- `/dashboard` remains the only affected route.
- Data for the analyst widget starts as local static dashboard data in the web app.
- Future data flow can replace the local `ANALYST_RATINGS` constant with a REST/MCP-derived panel payload matching the archived v1 `AnalystRatingsData` shape.

## Risks and edge cases

- The current dashboard already contains unstyled terminal class names. Adding the analyst widget without the missing CSS would make the page look inconsistent, so the CSS pass is required.
- The old v1 widget used Tailwind and `lucide-react`; directly copying it would fail in the current app without new dependencies. The implementation should port the markup and visual result, not import the v1 file directly.
- The current app has a warm light shell. A fully black analyst card needs careful scoping so it feels like a Doomberg terminal module rather than a dark-mode page takeover.
- Text overflow risk is highest in the price range value, long firm names, and `Neutral to Buy` action label. CSS should use grid constraints, `min-width: 0`, and truncation where needed.
- The screenshot uses sample market data, not live analyst data. The UI should make no claim that it is live unless real data is later wired.

## Verification

After implementation, run:

```bash
pnpm --filter @doomberg/web typecheck
pnpm --filter @doomberg/web build
```

For visual verification, run the local app:

```bash
DOOMBERG_DB=./doomberg.db uv run --package doomberg-rest-gateway uvicorn doomberg_rest.app:create_app --factory --host 127.0.0.1 --port 8000
pnpm --filter @doomberg/web dev -- --host 127.0.0.1 --port 5173
```

Then inspect `/dashboard` at desktop and mobile widths and confirm:

- the analyst card visually matches the approved screenshot direction
- the card is visible in the dashboard grid
- no text overlaps inside the analyst card
- existing dashboard widgets still render
- the side nav and `/dashboard` route still work
