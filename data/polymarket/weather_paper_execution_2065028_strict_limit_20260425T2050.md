# Paper strict-limit refresh — 2065028 — 20260425T2050

- Mode: paper-only; no real order.
- Market: Will the highest temperature in Hong Kong be 30°C or higher on April 26?
- Side/limit: NO <= 0.978
- HKO latest: 23°C at 2026-04-26T02:02:00+08:00
- Official daily extract: pending/unavailable
- Orderbook: stale saved snapshot from earlier execution; re-poll required before any fresh simulated/live action.
- Eligibility: YES paper simulation only
- Simulated fill on saved snapshot: 5.0 USDC @ avg 0.977 for 5.117707 shares.

Risk controls:
- `paper_only`
- `real_order_placed_false`
- `refuse_fill_above_0.978`
- `no_normal_size`
- `official_resolution_pending`
- `orderbook_snapshot_stale_repoll_before_any_real_or_new_paper_fill`
