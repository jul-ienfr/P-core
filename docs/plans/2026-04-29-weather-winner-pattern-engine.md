# Weather Winner Pattern Engine — Implementation Plan

> **For Hermes:** Use subagent-driven-development / phase-plan-executor style discipline to implement this plan phase by phase. Strict TDD, subprocess CLI checks, paper-only guards everywhere.

**Goal:** Turn current Polymarket météo account-learning artifacts into a robust paper-only engine that learns winning-account patterns from broad historical data, validates capturability with orderbook context, models real abstentions, and outputs explainable paper candidates only when independent evidence aligns.

**Architecture:** Keep domain-specific Polymarket météo logic in `weather_pm`; reuse `prediction_core` only for generic paper/evaluation concepts; keep `panoptique` as observer/evidence surface if needed. Do not create a new repo. Do not introduce live order authority.

**Tech Stack:** Python under `/home/jul/P-core/python/src`, pytest, JSON artifacts first, optional Parquet readers behind guarded adapters if dependencies are available. CLI must be verified through `python -m weather_pm.cli` subprocess with `PYTHONPATH=python/src`.

---

## Non-negotiable constraints

- `paper_only = true` and `live_order_allowed = false` on every produced artifact and compact CLI stdout.
- No wallet secrets, no signing, no real order placement, no cancellation.
- Backfill/read-only APIs only.
- Unknown data stays `null` / `available=false`; never infer unavailable orderbook/weather values.
- Every new CLI command gets at least one subprocess test.
- Every phase uses RED → GREEN → VERIFY.
- Keep commits small and scoped.
- Preserve existing WIP unless intentionally completing it.

---

## Contexte vérifié — repo actuel

Verified on 2026-04-29 in `/home/jul/P-core`:

- Existing plan: `docs/plans/2026-04-28-polymarket-weather-shadow-profiles-references.md`.
- Existing current WIP:
  - `python/src/weather_pm/account_learning.py`
  - `python/src/weather_pm/cli.py`
  - `python/tests/test_weather_account_pattern_learning.py`
- Existing CLI surfaces include:
  - `backfill-account-trades`
  - `import-account-trades`
  - `account-learning-backfill`
  - `account-trades-backfill`
  - `account-trades-import`
  - `shadow-profiles-report`
  - `shadow-profile-report`
  - `shadow-paper-runner`
  - `market-metadata-resolution`
  - `account-trade-resolution`
  - `shadow-profile-evaluator`
  - `shadow-profile-exposure-preview`
  - WIP `account-pattern-learning-digest`
- Existing useful modules include:
  - `python/src/weather_pm/account_learning.py`
  - `python/src/weather_pm/account_trades.py`
  - `python/src/weather_pm/market_parser.py`
  - `python/src/weather_pm/shadow_profiles.py`
  - `python/src/weather_pm/shadow_paper_runner.py`
  - `python/src/weather_pm/live_observer.py`
  - `python/src/weather_pm/polymarket_client.py`
  - `python/src/weather_pm/forecast_client.py`
  - `python/src/weather_pm/history_client.py`
  - `python/src/weather_pm/source_routing.py`
  - `python/src/weather_pm/station_binding.py`
- Plan-proposed modules that do **not** currently exist under exact names:
  - `account_trade_import.py`
  - `weather_market_classifier.py`
  - `shadow_dataset.py`
  - `account_profile.py`
  - `account_pattern_extractor.py`
  - `orderbook_context_import.py`
  - `orderbook_features.py`
  - `weather_context.py`
  - `forecast_context.py`
  - `panoptique/shadow_profiles.py`
  - `panoptique/weather_observer.py`
- Existing artifacts show current baseline:
  - `public_account_trades_backfill_top80.json`: 80 accounts, 7,822 raw trades.
  - `weather_account_trades_top80.json`: 7,397 weather trades.
  - `trade_no_trade_dataset_top80.json`: 400 examples = 95 trades + 305 no-trades.
  - `account_trade_resolution_top80_plus_all_closed_slug_backfill_terminal_orderbook.json`: 4,279 resolved / 7,397 trades; 2,154 wins / 2,125 losses.
  - `account_cross_profile_learning_map_20260429T1535Z.json`: 79 accounts, 7,397 all trades, 4,279 resolved trades.
  - `true_pattern_discovery_robustness_20260429T1545Z.json`: 710 scanned patterns, 51 robust winning patterns.
  - `paper_account_pattern_live_radar_20260429T170730Z.json`: 120 candidates, but watch/conflict only; no paper probe authorized.

Bottom line: do not restart architecture. Extend current `account_learning` / `shadow_paper_runner` pipeline with the missing high-leverage data layers.

---

## Target product outcome

A paper-only `Weather Winner Pattern Engine` that can answer, with evidence:

1. Which accounts are genuinely winning after resolved outcomes?
2. Which account-pattern slices are robust out-of-sample, not concentrated one-offs?
3. Were historical trades realistically capturable after spread/depth/slippage?
4. Which similar markets did winning accounts avoid?
5. Which weather source/forecast information was available at decision time?
6. Which current markets match robust historical patterns and pass independent orderbook/source gates?
7. Why did the system skip everything else?

---

## Phase 0 — Finish and validate current WIP digest

**Objective:** Land the existing `account-pattern-learning-digest` work before building on it.

**Files:**
- Modify: `python/src/weather_pm/account_learning.py`
- Modify: `python/src/weather_pm/cli.py`
- Test: `python/tests/test_weather_account_pattern_learning.py`

### Task 0.1 — Run current WIP test and inspect failure

Run:

```bash
cd /home/jul/P-core
PYTHONPATH=python/src python3 -m pytest python/tests/test_weather_account_pattern_learning.py -q
```

Expected:
- If PASS, continue to Task 0.2.
- If FAIL, fix only this WIP surface until it passes.

### Task 0.2 — Verify CLI help exposes the command

Run:

```bash
cd /home/jul/P-core
PYTHONPATH=python/src python3 -m weather_pm.cli --help | grep -F "account-pattern-learning-digest"
```

Expected: command appears.

### Task 0.3 — Regression safety for paper-only compact stdout

Add assertions to `test_weather_account_pattern_learning.py` if missing:

```python
assert result["summary"]["paper_only"] is True
assert result["summary"]["live_order_allowed"] is False
```

Run targeted test again.

### Task 0.4 — Verify diff and commit WIP

Run:

```bash
git diff --check
git diff -- python/src/weather_pm/account_learning.py python/src/weather_pm/cli.py python/tests/test_weather_account_pattern_learning.py | cat
PYTHONPATH=python/src python3 -m pytest python/tests/test_weather_account_pattern_learning.py -q
```

Commit:

```bash
git add python/src/weather_pm/account_learning.py python/src/weather_pm/cli.py python/tests/test_weather_account_pattern_learning.py
git commit -m "feat(weather_pm): add account pattern learning digest"
```

---

## Phase 1 — Historical data source manifest and coverage audit

**Objective:** Create a canonical read-only source manifest and coverage report so future backfills are measurable.

**Files:**
- Create: `python/src/weather_pm/account_data_sources.py`
- Create: `python/tests/test_weather_account_data_sources.py`
- Modify: `python/src/weather_pm/cli.py`

### Task 1.1 — Test canonical source manifest

Create test requiring a paper-only manifest with the planned sources:

```python
def test_account_data_source_manifest_lists_historical_sources():
    from weather_pm.account_data_sources import build_account_data_source_manifest

    payload = build_account_data_source_manifest()

    assert payload["paper_only"] is True
    assert payload["live_order_allowed"] is False
    source_ids = {row["source_id"] for row in payload["sources"]}
    assert "polymarket_data_api_trades" in source_ids
    assert "sii_wangzj_polymarket_data_hf" in source_ids
    assert "pmxt_l2_archive" in source_ids
    assert "telonex_full_depth_snapshots" in source_ids
    assert "gamma_closed_markets" in source_ids
```

Run and expect import failure.

### Task 1.2 — Implement minimal manifest module

Implement `build_account_data_source_manifest()` with sources:

- `polymarket_data_api_trades`: already used; limited recent/backfill per account.
- `sii_wangzj_polymarket_data_hf`: massive trades/users/markets/orderfilled parquet.
- `sii_wangzj_polymarket_data_github`: ETL/schema reference only.
- `pmxt_l2_archive`: historical L2/orderbook candidate.
- `telonex_full_depth_snapshots`: optional historical full-depth candidate.
- `gamma_closed_markets`: market metadata/resolution source.
- `polymarket_clob_current_book`: live/current book only, not historical.
- `official_weather_sources`: source/station/forecast context.

Each row fields:

```python
source_id, role, priority, status, read_only, paper_only, live_order_allowed, expected_fields, limitations
```

### Task 1.3 — Add CLI `account-data-source-manifest`

CLI output compact:

```json
{
  "paper_only": true,
  "live_order_allowed": false,
  "sources": 8,
  "high_priority_sources": ["sii_wangzj_polymarket_data_hf", "pmxt_l2_archive", "gamma_closed_markets"]
}
```

Subprocess test:

```python
result = subprocess.run([... "account-data-source-manifest"], ...)
payload = json.loads(result.stdout)
assert payload["paper_only"] is True
assert payload["sources"] >= 7
```

---

## Phase 2 — Hugging Face / parquet schema adapter, sample-first

**Objective:** Add a guarded adapter for `SII-WANGZJ/Polymarket_data` without downloading the full dataset by default.

**Files:**
- Create: `python/src/weather_pm/hf_polymarket_dataset.py`
- Create: `python/tests/test_weather_hf_polymarket_dataset.py`
- Modify: `python/src/weather_pm/cli.py`

### Task 2.1 — Test schema normalization from fixture rows

Use local fixture rows, not network:

```python
def test_normalize_hf_trade_row_preserves_unknowns():
    from weather_pm.hf_polymarket_dataset import normalize_hf_trade_row

    row = {
        "proxyWallet": "0xabc",
        "market": "Will Paris have a high temperature between 21-22°C on May 4?",
        "conditionId": "cond1",
        "asset": "token1",
        "price": 0.21,
        "size": 125,
        "timestamp": "2026-04-01T12:35:00Z",
    }
    out = normalize_hf_trade_row(row)
    assert out["wallet"] == "0xabc"
    assert out["condition_id"] == "cond1"
    assert out["token_id"] == "token1"
    assert out["market_id"] is None
    assert out["paper_only"] is True
    assert out["live_order_allowed"] is False
```

### Task 2.2 — Implement normalizer

Map common HF/schema aliases:

- wallet: `wallet`, `user`, `proxyWallet`, `proxy_wallet`
- market title/question: `title`, `question`, `market`, `marketTitle`
- identifiers: `market_id`, `marketId`, `conditionId`, `condition_id`, `asset`, `token_id`, `tokenId`
- trade fields: `price`, `size`, `amount`, `timestamp`, `createdAt`, `tx_hash`, `transactionHash`, `block_number`, `maker_taker`

Never synthesize missing IDs.

### Task 2.3 — Add local parquet reader if dependencies exist

Function:

```python
def iter_hf_dataset_rows(path: str | Path, *, limit: int | None = None) -> Iterator[dict[str, Any]]
```

Rules:
- If `.json`/`.jsonl`, read with stdlib.
- If `.parquet`, try pandas/pyarrow; raise clear `RuntimeError` if missing dependency.
- Support `limit`.

### Task 2.4 — Add CLI `hf-account-trades-sample`

Arguments:

```text
--input PATH
--wallet WALLET repeatable optional
--wallets-json optional
--output-json PATH
--limit INT default 1000
```

Output full artifact with normalized rows. Compact stdout:

```json
{"paper_only": true, "live_order_allowed": false, "rows_scanned": 1000, "matched_trades": 12, "output_json": "..."}
```

Subprocess fixture test with JSONL input.

---

## Phase 3 — Resolution coverage booster

**Objective:** Improve historical trade resolution coverage from current ~58% toward >85% using multiple matching keys and explicit unresolved reasons.

**Files:**
- Create or extend: `python/src/weather_pm/account_resolution_coverage.py`
- Create: `python/tests/test_weather_account_resolution_coverage.py`
- Modify if better existing seam: `python/src/weather_pm/shadow_paper_runner.py`
- Modify: `python/src/weather_pm/cli.py`

### Task 3.1 — Test multi-key resolution match

Fixture trade has `market_id`, `condition_id`, `token_id`, `slug`, title alias. Resolution payload has only slug/condition. Test returns `resolved=true` with `match_key="condition_id"` or strongest available key.

### Task 3.2 — Implement resolution matcher

Priority order:

1. `token_id`
2. `condition_id`
3. `market_id`
4. normalized `slug`
5. normalized question/title
6. event slug + outcome side if unique

Return fields:

```json
resolved, outcome, winning_side, pnl, match_key, unresolved_reason
```

### Task 3.3 — Add coverage report

Function:

```python
build_resolution_coverage_report(trades_payload, resolutions_payload)
```

Summary:

- trades
- resolved
- unresolved
- resolved_pct
- match_key_counts
- unresolved_reason_counts
- paper_only/live_order_allowed

### Task 3.4 — Add CLI `account-resolution-coverage`

Subprocess test using fixtures. Compact stdout must include `resolved_pct` and guardrails.

---

## Phase 4 — Historical orderbook context adapter

**Objective:** Add a small, testable orderbook-context layer that can consume PMXT/Telonex-like snapshots and mark capturability; do not depend on full external stack initially.

**Files:**
- Create: `python/src/weather_pm/orderbook_context.py`
- Create: `python/tests/test_weather_orderbook_context.py`
- Modify: `python/src/weather_pm/cli.py`

### Task 4.1 — Test nearest snapshot selection

Given trade timestamp `12:35` and snapshots at `12:30`, `12:40`, choose nearest within max staleness.

Expected output fields:

```json
orderbook_context_available: true
snapshot_timestamp: "..."
staleness_seconds: 300
best_bid, best_ask, mid, spread
```

### Task 4.2 — Test missing/stale context is explicit

If nearest snapshot is too old:

```json
orderbook_context_available: false
missing_reason: "no_snapshot_within_max_staleness"
```

### Task 4.3 — Implement feature computation

For side-specific book:

- best_bid
- best_ask
- mid
- spread
- depth_near_touch
- available_size_at_or_better_price
- estimated_slippage_for_5_usdc
- estimated_slippage_for_20_usdc
- imbalance if both sides present
- microprice if possible

### Task 4.4 — Add CLI `enrich-trades-orderbook-context`

Arguments:

```text
--trades-json
--orderbook-snapshots-json
--output-json
--max-staleness-seconds default 3600
```

Compact stdout:

```json
{"paper_only": true, "live_order_allowed": false, "trades": 20, "with_orderbook_context": 17, "missing_orderbook_context": 3}
```

### Task 4.5 — External source spike note

Add a Markdown section to the output artifact `limitations` listing:

- PMXT hourly L2 archive candidate.
- Telonex full-depth candidate.
- `evan-kolberg/prediction-market-backtesting` is donor/reference, not framework replacement.

---

## Phase 5 — Capturability scoring

**Objective:** Convert orderbook context into a clear `capturable | maybe | not_capturable | unknown` label.

**Files:**
- Create: `python/src/weather_pm/capturability.py`
- Create: `python/tests/test_weather_capturability.py`
- Modify: `python/src/weather_pm/cli.py` or integrate into Phase 4 CLI output

### Task 5.1 — Test capturable trade

A trade with best ask <= trade price + tolerance, spread <= threshold, enough depth gets:

```json
capturability: "capturable"
```

### Task 5.2 — Test impossible stale/anomaly

A trade with no book or massive spread gets:

```json
capturability: "unknown" or "not_capturable"
reason: "missing_orderbook_context" / "spread_too_wide"
```

### Task 5.3 — Implement scoring

Inputs:

- trade side
- trade price
- size/usdc
- best bid/ask
- spread
- depth
- max tolerated slippage

Outputs:

```json
capturability
capturable_score
estimated_entry_price
estimated_slippage_bps
capturability_reasons
```

No order recommendation; this is evidence only.

---

## Phase 6 — Real trade/no-trade dataset v2

**Objective:** Replace weak no-trade examples with observable same-window alternatives.

**Files:**
- Create: `python/src/weather_pm/decision_dataset.py`
- Create: `python/tests/test_weather_decision_dataset.py`
- Modify: `python/src/weather_pm/cli.py`

### Task 6.1 — Test positive trade examples

Given weather trades, output examples with:

```json
label: "trade"
account, wallet, market_id, timestamp_bucket, city, market_type, side, price
```

### Task 6.2 — Test no-trade only from observable active market

Given active market snapshot in same city/date/type/time bucket, where account has no trade, output:

```json
label: "no_trade"
reason: "similar_surface_no_account_trade"
observable: true
```

Reject no-trades where `observable=false` or missing active timestamp.

### Task 6.3 — Add ratio caps

Avoid flooding negatives. Default max `no_trade_per_trade=5` per account/surface bucket.

### Task 6.4 — Add CLI `build-account-decision-dataset`

Arguments:

```text
--trades-json
--markets-snapshots-json
--output-json
--bucket-minutes default 60
--no-trade-per-trade default 5
```

Summary:

- accounts
- trade_examples
- no_trade_examples
- observable_markets_considered
- skipped_unobservable
- paper_only/live_order_allowed

---

## Phase 7 — Historical weather/source context

**Objective:** Attach source/forecast-at-time evidence without mixing future-known resolution into decision-time features.

**Files:**
- Create: `python/src/weather_pm/weather_decision_context.py`
- Create: `python/tests/test_weather_decision_context.py`
- Modify: `python/src/weather_pm/cli.py`

### Task 7.1 — Test forecast-at-time separation

Fixture has:

- forecast timestamp before trade
- observation after resolution
- resolution value

Expected:

```json
forecast_value_at_decision: ...
observation_value: ...
resolution_value: ...
decision_context_leakage_allowed: false
```

### Task 7.2 — Implement source routing fields

Reuse existing source/station modules where possible. Output:

- resolution_source
- station_id
- station_name
- forecast_timestamp
- forecast_value
- forecast_age_minutes
- distance_to_threshold
- distance_to_bin_center
- official_source_available
- weather_context_available
- missing_reason

### Task 7.3 — Add CLI `enrich-decision-weather-context`

Arguments:

```text
--decision-dataset-json
--forecast-snapshots-json
--resolution-sources-json optional
--output-json
```

Compact stdout includes count with weather context.

---

## Phase 8 — Pattern engine v2: robust, capturable, abstention-aware

**Objective:** Learn account/archetype patterns using resolved outcomes, capturability, abstentions, and weather context.

**Files:**
- Create: `python/src/weather_pm/winner_pattern_engine.py`
- Create: `python/tests/test_weather_winner_pattern_engine.py`
- Modify: `python/src/weather_pm/cli.py`

### Task 8.1 — Test robust positive slice

Given examples with positive out-of-sample PnL, enough trades, capturable contexts, output pattern:

```json
pattern_status: "robust_candidate"
```

### Task 8.2 — Test anti-pattern slice

Negative PnL / bad capturability outputs:

```json
pattern_status: "anti_pattern"
block_live_radar: true
```

### Task 8.3 — Test suspect concentration downgrade

If top account/wallet contributes >80% PnL or tiny sample:

```json
pattern_status: "research_only"
reason: "concentrated_or_small_sample"
```

### Task 8.4 — Implement archetype labels

Initial archetypes:

- `threshold_harvester`
- `exact_bin_anomaly_hunter`
- `late_certainty_compounder`
- `surface_grid_trader`
- `abstention_filter`
- `unclear`

### Task 8.5 — Add CLI `winner-pattern-engine`

Arguments:

```text
--decision-context-json
--resolved-trades-json
--output-json
--output-md optional
--min-resolved-trades default 5
--max-top1-pnl-share default 0.8
```

Output:

- robust patterns
- anti-patterns
- research-only patterns
- account summaries
- feature importance counters
- operator next actions

---

## Phase 9 — Paper candidate gate v2

**Objective:** Current markets become paper candidates only when robust account patterns + source/weather + current orderbook + anti-pattern guards align.

**Files:**
- Create or extend: `python/src/weather_pm/paper_candidate_gate.py`
- Create: `python/tests/test_weather_paper_candidate_gate.py`
- Modify likely: `python/src/weather_pm/shadow_paper_runner.py`
- Modify: `python/src/weather_pm/cli.py`

### Task 9.1 — Test robust match but missing book stays watch-only

Expected:

```json
decision: "watch_only"
reason: "missing_current_orderbook"
paper_probe_authorized: false
```

### Task 9.2 — Test anti-pattern conflict blocks

Expected:

```json
decision: "blocked"
reason: "anti_pattern_conflict"
```

### Task 9.3 — Test fully aligned tiny paper candidate

Only when all gates pass:

```json
decision: "paper_candidate"
paper_notional_cap_usdc <= 5
live_order_allowed: false
```

### Task 9.4 — Add CLI `winner-pattern-paper-candidates`

Inputs:

```text
--winner-patterns-json
--current-markets-json
--current-orderbooks-json
--current-weather-context-json
--output-json
--output-md optional
```

Output must preserve skip reasons for every considered market.

---

## Phase 10 — Operator report and dashboard-ready artifact

**Objective:** Produce one concise operator artifact that says what improved, what is known, what is missing, and what is safe to watch/paper.

**Files:**
- Create: `python/src/weather_pm/winner_pattern_report.py`
- Create: `python/tests/test_weather_winner_pattern_report.py`
- Modify: `python/src/weather_pm/cli.py`

### Task 10.1 — Test report summarizes coverage

Expected Markdown sections:

- `# Weather Winner Pattern Engine`
- `Safety`
- `Coverage`
- `Robust patterns`
- `Anti-patterns`
- `Capturability gaps`
- `Paper candidates / watch-only`
- `Next data gaps`

### Task 10.2 — Add CLI `winner-pattern-report`

Inputs all major artifacts; output JSON + MD.

Compact stdout:

```json
{"paper_only": true, "live_order_allowed": false, "robust_patterns": N, "paper_candidates": M, "watch_only": K, "output_md": "..."}
```

---

## Phase 11 — Live observer integration, bounded and TrueNAS-safe

**Objective:** Use live observer only to fill missing non-reconstructable variables: orderbook exact, abstentions, forecast-at-time, full surface snapshots.

**Files:**
- Extend existing live observer modules only after audit:
  - `python/src/weather_pm/live_observer.py`
  - `python/src/weather_pm/live_storage.py`
  - existing tests around live observer storage
- Add tests if needed.

### Task 11.1 — Audit existing live observer storage

Before editing, read:

- `python/src/weather_pm/live_observer.py`
- `python/src/weather_pm/live_storage.py`
- `python/tests/test_panoptique_live_observer_storage.py` if relevant

### Task 11.2 — Add winner-pattern watchlist mode

Mode should capture only:

- current orderbook compact snapshots for matched surfaces;
- full book only around account trade / large movement / candidate trigger;
- forecast snapshots;
- market surface snapshots;
- observed account trades.

### Task 11.3 — TrueNAS guard

Before writing under `/mnt/truenas`, verify it is a real mountpoint. If not, fail loudly and write nothing.

### Task 11.4 — Rotation/compression metadata

Every live artifact must include:

```json
retention_policy, compressed, source, captured_at, paper_only, live_order_allowed
```

---

## Phase 12 — End-to-end replay command

**Objective:** Add a single orchestrating command for local artifacts that runs the pipeline without network by default.

**Files:**
- Create: `python/src/weather_pm/winner_pattern_pipeline.py`
- Create: `python/tests/test_weather_winner_pattern_pipeline.py`
- Modify: `python/src/weather_pm/cli.py`

### Task 12.1 — Fixture-only pipeline test

Given small fixtures for trades, resolutions, orderbook snapshots, active markets, weather snapshots:

Command:

```bash
PYTHONPATH=python/src python3 -m weather_pm.cli winner-pattern-pipeline \
  --trades-json fixtures/trades.json \
  --resolutions-json fixtures/resolutions.json \
  --orderbook-snapshots-json fixtures/orderbooks.json \
  --market-snapshots-json fixtures/markets.json \
  --forecast-snapshots-json fixtures/forecasts.json \
  --output-dir /tmp/run
```

Expected files:

- `resolution_coverage.json`
- `orderbook_context.json`
- `decision_dataset.json`
- `weather_context.json`
- `winner_patterns.json`
- `paper_candidates.json`
- `operator_report.md`

### Task 12.2 — No-network default

Pipeline must not call remote APIs unless explicit `--allow-network` is provided. First implementation can reject `--allow-network` as not yet supported.

---

## Final validation commands

Run from `/home/jul/P-core`:

```bash
git status --short

git diff --check

PYTHONPATH=python/src python3 -m pytest \
  python/tests/test_weather_account_pattern_learning.py \
  python/tests/test_weather_account_data_sources.py \
  python/tests/test_weather_hf_polymarket_dataset.py \
  python/tests/test_weather_account_resolution_coverage.py \
  python/tests/test_weather_orderbook_context.py \
  python/tests/test_weather_capturability.py \
  python/tests/test_weather_decision_dataset.py \
  python/tests/test_weather_decision_context.py \
  python/tests/test_weather_winner_pattern_engine.py \
  python/tests/test_weather_paper_candidate_gate.py \
  python/tests/test_weather_winner_pattern_report.py \
  python/tests/test_weather_winner_pattern_pipeline.py -q

PYTHONPATH=python/src python3 -m pytest python/tests/test_weather_shadow_paper_runner.py -q

python3 -m py_compile \
  python/src/weather_pm/account_learning.py \
  python/src/weather_pm/account_data_sources.py \
  python/src/weather_pm/hf_polymarket_dataset.py \
  python/src/weather_pm/account_resolution_coverage.py \
  python/src/weather_pm/orderbook_context.py \
  python/src/weather_pm/capturability.py \
  python/src/weather_pm/decision_dataset.py \
  python/src/weather_pm/weather_decision_context.py \
  python/src/weather_pm/winner_pattern_engine.py \
  python/src/weather_pm/paper_candidate_gate.py \
  python/src/weather_pm/winner_pattern_report.py \
  python/src/weather_pm/winner_pattern_pipeline.py
```

Security grep:

```bash
grep -RInE "private_key|wallet_secret|signing|place_order|cancel_order|live_order_allowed.*true" \
  python/src/weather_pm python/src/panoptique python/src/prediction_core || true
```

Expected: no new live-order authority introduced. If grep matches existing safe text/tests, inspect and document.

---

## Success metrics

Near-term target after implementation:

- Resolution coverage report exists and shows exact unresolved reasons.
- At least a fixture/sample path enriches trades with historical orderbook context.
- Decision dataset v2 has observable no-trades, not synthetic guesses.
- Winner patterns are split into robust / anti-pattern / research-only.
- Paper candidate gate emits mostly skip/watch-only with explicit reasons.
- Any actual paper candidate requires:
  - robust out-of-sample pattern;
  - no anti-pattern conflict;
  - current orderbook capturable;
  - weather/source context fresh;
  - tiny paper cap;
  - `live_order_allowed=false`.

Stretch target after connecting real data sources:

- Historical resolved coverage moves from ~58% toward >85%.
- Orderbook context exists for at least 20–100 historical trades first, then expands.
- HF/parquet backfill expands beyond data-api last-100-trades limits.

---

## Recommended execution order

1. Phase 0 — finish current digest WIP.
2. Phase 1 — manifest/coverage audit.
3. Phase 3 — resolution coverage booster.
4. Phase 4 + 5 — orderbook context and capturability.
5. Phase 6 — true no-trade dataset v2.
6. Phase 8 — winner pattern engine v2.
7. Phase 9 — paper candidate gate.
8. Phase 2 and 7 can run in parallel once core contracts are stable.
9. Phase 11 live observer only after offline/replay contracts work.
10. Phase 12 end-to-end fixture pipeline last.

Reason: immediate leverage comes from resolving/capturing existing artifacts, not from waiting on giant external downloads.
