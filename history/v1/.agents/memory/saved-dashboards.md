---
name: Saved dashboard layouts (persistence)
description: How named dashboard layouts are saved/restored across sessions in the terminal.
---

# Saved dashboard layouts

Users save the on-screen dashboard under a name and restore it later.

- **Store**: `app/dashboard_store.py` — DB-first (`CREATE TABLE IF NOT EXISTS
  saved_dashboards`, runtime-created like `strategy_store`, NO drizzle push) +
  in-mem dict fallback. `panels` is a jsonb column holding the FULL panel list
  (panels carry all rendered data inline, so restore recomputes nothing).
- **Save dedups by name** (case-insensitive): reusing a name overwrites that
  layout's panels/summary, so the saved list never fills with duplicates.
- **Endpoints** (`main.py`): GET/POST `/dashboards`, GET/DELETE
  `/dashboards/{id}`. Restore mints a FRESH session id and loads panels into
  `state.set_dashboard(sid, panels)` so the user can keep refining from there;
  returns a normal `DashboardSpec` with `intent:"build"`.
- **Save payload comes from the CLIENT** (`SaveDashboardRequest{name, summary,
  panels}`), not from server session memory — `activeDashboard` on screen is the
  source of truth and is decoupled from the in-memory session store.
- **Panel.status enum is `ok|loading|error`** (NOT "ready") — a save will 422 if
  you send "ready".
- **Frontend**: `SavedDashboardsModal.tsx` (header "Dashboards" button in
  `Terminal.tsx`). `useListSavedDashboards()` is generated as a react-query hook
  whose options require `queryKey`; to fetch on open, call `list.refetch()` in a
  `useEffect([open])` rather than passing `{query:{enabled}}` (that fails tsc).
