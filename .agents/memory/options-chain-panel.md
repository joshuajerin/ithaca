---
name: Options chain panel
description: How the options_chain panel is generated and rendered (calls/puts ladder with expiry selector).
---
- options_chain returns ALL expiries (1W..1Y) in one payload; the frontend `OptionsChainPanel` holds the selected expiry + strike pagination client-side. Backend `selectedExpiry`/`expiry` param only sets the default tab.
- Quotes are synthetic but grounded: IV from `_iv_smile`, mid from `_bs_price`, then `_opt_quote` derives bid/ask (spread widens with |moneyness|), a deterministic `last` (FNV-1a `_det_hash` so it's stable per symbol/strike/expiry), and volume/OI (gaussian peak at ATM, volume heavier near-dated, OI grows with tenor).
- Strike ladder: `_strike_step(S)` picks a nice increment (0.5..100) ~2.5% of spot, centered on rounded ATM, 17 strikes. Real underlying price comes from `repo.get_company` (live), so asOf/source freshness contract applies.
- **Why:** matches the existing IV-surface expiry ladder so the two panels stay consistent; full-payload-per-expiry avoids round-trips when switching tabs.
- Routing: keyword heuristic `wants_chain` is checked BEFORE `wants_iv_surface`/`wants_options` in the derivatives block so "options chain"/"calls and puts"/"all strikes" don't get swallowed by strategy/surface intents. `_extract_expiry` maps free text (1M, weekly, etc.) to a label.
