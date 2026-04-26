# Polymarket Dynamic Position Sizing Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Add a high-performance dynamic sizing system for Polymarket weather trading that imitates the most robust profitable-wallet pattern: many small grid/surface entries, strict correlation caps, and continuous add/hold/reduce decisions.

**Architecture:** Extend the existing Python weather/Polymarket stack instead of rebuilding it. Keep the current `edge_sizing`, `entry_policy`, `strategy_shortlist`, paper watchlist, and wallet-intel layers, then add a dedicated sizing engine that combines model edge, execution quality, wallet-style priors, and correlated exposure. Real execution stays disabled unless explicitly enabled later; outputs remain paper/operator decisions.

**Tech Stack:** Python 3, `src/` layout under `/home/jul/prediction_core/python`, pytest, existing modules `weather_pm.edge_sizing`, `weather_pm.wallet_intel`, `weather_pm.strategy_shortlist`, `prediction_core.decision.entry_policy`.

---

## Contexte vérifié

- Active repo: `/home/jul/prediction_core`.
- Python package root: `/home/jul/prediction_core/python`.
- Existing basic Kelly-style sizing is in `python/src/weather_pm/edge_sizing.py`.
- Existing entry gate is in `python/src/prediction_core/decision/entry_policy.py` and currently returns a static `size_hint_usd = policy.max_position_usd` when entry is allowed.
- Existing strategy shortlist enriches rows with:
  - `edge_sizing`
  - `entry_policy`
  - `entry_decision`
  in `python/src/weather_pm/strategy_shortlist.py`.
- Existing wallet intel module is `python/src/weather_pm/wallet_intel.py`.
- Existing profitable wallet artifacts show three sizing styles:
  - `breadth/grid small-ticket surface trader`: 18/29 accounts, median average trade size ≈ 25.95 USDC, usually 174–200 recent trades.
  - `sparse/large-ticket conviction trader`: 10/29 accounts, median average trade size ≈ 279.5 USDC, much larger max trades.
  - `selective weather trader`: 1/29 account, too sparse to copy as default.
- Existing pattern matrix says top profitable weather accounts are all event-surface/exact-bin grid accounts; top80 counts are mostly `range_or_bin` over `threshold`.
- Current operator summary uses conservative sizing labels such as `micro_paper_only` and `paper_until_execution_validated`.
- Relevant tests already exist:
  - `python/tests/test_edge_sizing.py`
  - `python/tests/test_weather_strategy_shortlist.py`
  - `python/tests/test_entry_policy.py`
  - `python/tests/test_paper_watchlist.py`

## Design cible

### Core idea

Build a new deterministic sizing layer:

```text
recommended_size = base_size
  × edge_multiplier
  × confidence_multiplier
  × liquidity_multiplier
  × wallet_style_multiplier
  × timing_multiplier
  × correlation_cap_remaining
```

Then classify:

```text
NO_TRADE | PROBE | OPEN | ADD | HOLD | HOLD_CAPPED | REDUCE_REVIEW
```

### Default style to imitate

Default should imitate **breadth/grid small-ticket surface trader**, not large-ticket conviction accounts.

Initial defaults:

```text
PROBE:       1–3 USDC
OPEN:        5–15 USDC
ADD:         5–20 USDC
STRONG_ADD: 20–50 USDC max, paper only initially
```

### Correlation caps

Caps must be based on correlated surface keys, not only market IDs:

```text
surface_key = city + date + variable/kind
market_key  = market_id + outcome/token
```

Example caps for initial paper mode:

```text
max_per_market_usdc: 15
max_per_surface_usdc: 50
max_per_city_day_usdc: 75
max_total_weather_open_usdc: 250
```

### Wallet-style priors

Wallet intel should adjust confidence/priority, but never blindly copy size.

Rules:

```text
breadth/grid small-ticket match   → allow normal small sizing
sparse/large-ticket match         → cap to small sizing unless independent edge is very strong
selective weather trader          → confidence bump only, no size bump
unknown/no wallet match           → use model/execution only
```

---

## Phase 1 — Add deterministic sizing domain

### Task 1: Create dynamic sizing tests

**Objective:** Define expected behavior before implementation.

**Files:**
- Create: `python/tests/test_dynamic_position_sizing.py`
- Create later: `python/src/weather_pm/dynamic_position_sizing.py`

**Step 1: Write failing tests**

Create `python/tests/test_dynamic_position_sizing.py`:

```python
from __future__ import annotations

from weather_pm.dynamic_position_sizing import (
    ExposureState,
    SizingInput,
    SizingPolicy,
    calculate_dynamic_position_size,
)


def test_grid_style_positive_edge_opens_small_position() -> None:
    decision = calculate_dynamic_position_size(
        SizingInput(
            market_id="m1",
            surface_key="Paris|2026-04-27|high_temp",
            model_probability=0.67,
            market_price=0.55,
            net_edge=0.108,
            confidence=0.82,
            spread=0.03,
            depth_usd=900.0,
            hours_to_resolution=18.0,
            wallet_style="breadth/grid small-ticket surface trader",
            current_market_exposure_usdc=0.0,
            current_surface_exposure_usdc=0.0,
            current_total_weather_exposure_usdc=40.0,
        ),
        policy=SizingPolicy.paper_weather_grid_default(),
    )

    assert decision.action == "OPEN"
    assert 5.0 <= decision.recommended_size_usdc <= 15.0
    assert decision.max_market_remaining_usdc > 0
    assert decision.wallet_style_reference == "breadth/grid small-ticket surface trader"


def test_large_ticket_wallet_does_not_force_large_size() -> None:
    decision = calculate_dynamic_position_size(
        SizingInput(
            market_id="m2",
            surface_key="Dallas|2026-04-27|high_temp",
            model_probability=0.72,
            market_price=0.58,
            net_edge=0.12,
            confidence=0.85,
            spread=0.04,
            depth_usd=1200.0,
            hours_to_resolution=12.0,
            wallet_style="sparse/large-ticket conviction trader",
            current_market_exposure_usdc=0.0,
            current_surface_exposure_usdc=0.0,
            current_total_weather_exposure_usdc=20.0,
        ),
        policy=SizingPolicy.paper_weather_grid_default(),
    )

    assert decision.action == "OPEN"
    assert decision.recommended_size_usdc <= 15.0
    assert "large_ticket_style_capped" in decision.reasons


def test_surface_cap_blocks_repeated_add() -> None:
    decision = calculate_dynamic_position_size(
        SizingInput(
            market_id="m3",
            surface_key="Hong Kong|2026-04-26|high_temp",
            model_probability=0.80,
            market_price=0.62,
            net_edge=0.15,
            confidence=0.9,
            spread=0.02,
            depth_usd=1500.0,
            hours_to_resolution=4.0,
            wallet_style="breadth/grid small-ticket surface trader",
            current_market_exposure_usdc=10.0,
            current_surface_exposure_usdc=50.0,
            current_total_weather_exposure_usdc=120.0,
        ),
        policy=SizingPolicy.paper_weather_grid_default(),
    )

    assert decision.action == "HOLD_CAPPED"
    assert decision.recommended_size_usdc == 0.0
    assert "surface_cap_reached" in decision.reasons


def test_thin_book_or_wide_spread_only_allows_probe() -> None:
    decision = calculate_dynamic_position_size(
        SizingInput(
            market_id="m4",
            surface_key="Seoul|2026-04-27|high_temp",
            model_probability=0.70,
            market_price=0.55,
            net_edge=0.12,
            confidence=0.84,
            spread=0.12,
            depth_usd=35.0,
            hours_to_resolution=20.0,
            wallet_style="breadth/grid small-ticket surface trader",
            current_market_exposure_usdc=0.0,
            current_surface_exposure_usdc=0.0,
            current_total_weather_exposure_usdc=0.0,
        ),
        policy=SizingPolicy.paper_weather_grid_default(),
    )

    assert decision.action == "PROBE"
    assert 1.0 <= decision.recommended_size_usdc <= 3.0
    assert "execution_quality_poor" in decision.reasons
```

**Step 2: Run and verify RED**

Run from `/home/jul/prediction_core/python`:

```bash
PYTHONPATH=src python3 -m pytest tests/test_dynamic_position_sizing.py -q
```

Expected: fail with `ModuleNotFoundError: No module named 'weather_pm.dynamic_position_sizing'`.

### Task 2: Implement dynamic sizing dataclasses and defaults

**Objective:** Add the pure sizing module with no network calls.

**Files:**
- Create: `python/src/weather_pm/dynamic_position_sizing.py`

**Step 1: Implement minimal module**

```python
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class SizingPolicy:
    name: str
    probe_min_usdc: float
    probe_max_usdc: float
    open_min_usdc: float
    open_max_usdc: float
    strong_max_usdc: float
    max_per_market_usdc: float
    max_per_surface_usdc: float
    max_total_weather_open_usdc: float
    min_net_edge_probe: float
    min_net_edge_open: float
    min_confidence_open: float
    max_good_spread: float
    min_good_depth_usd: float

    @classmethod
    def paper_weather_grid_default(cls) -> "SizingPolicy":
        return cls(
            name="paper_weather_grid_default",
            probe_min_usdc=1.0,
            probe_max_usdc=3.0,
            open_min_usdc=5.0,
            open_max_usdc=15.0,
            strong_max_usdc=30.0,
            max_per_market_usdc=15.0,
            max_per_surface_usdc=50.0,
            max_total_weather_open_usdc=250.0,
            min_net_edge_probe=0.03,
            min_net_edge_open=0.06,
            min_confidence_open=0.75,
            max_good_spread=0.08,
            min_good_depth_usd=50.0,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class SizingInput:
    market_id: str
    surface_key: str
    model_probability: float
    market_price: float
    net_edge: float
    confidence: float
    spread: float
    depth_usd: float
    hours_to_resolution: float | None
    wallet_style: str | None
    current_market_exposure_usdc: float
    current_surface_exposure_usdc: float
    current_total_weather_exposure_usdc: float


@dataclass(frozen=True, slots=True)
class DynamicSizingDecision:
    policy: str
    action: str
    recommended_size_usdc: float
    max_market_remaining_usdc: float
    max_surface_remaining_usdc: float
    max_total_remaining_usdc: float
    wallet_style_reference: str | None
    reasons: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# Optional alias for future portfolio-wide helpers.
ExposureState = SizingInput


def calculate_dynamic_position_size(
    sizing_input: SizingInput,
    *,
    policy: SizingPolicy | None = None,
) -> DynamicSizingDecision:
    policy = policy or SizingPolicy.paper_weather_grid_default()
    reasons: list[str] = []

    market_remaining = max(policy.max_per_market_usdc - sizing_input.current_market_exposure_usdc, 0.0)
    surface_remaining = max(policy.max_per_surface_usdc - sizing_input.current_surface_exposure_usdc, 0.0)
    total_remaining = max(policy.max_total_weather_open_usdc - sizing_input.current_total_weather_exposure_usdc, 0.0)
    cap_remaining = min(market_remaining, surface_remaining, total_remaining)

    if market_remaining <= 0.0:
        reasons.append("market_cap_reached")
    if surface_remaining <= 0.0:
        reasons.append("surface_cap_reached")
    if total_remaining <= 0.0:
        reasons.append("total_weather_cap_reached")
    if cap_remaining <= 0.0:
        return _decision(policy, "HOLD_CAPPED", 0.0, market_remaining, surface_remaining, total_remaining, sizing_input.wallet_style, reasons)

    if sizing_input.net_edge < policy.min_net_edge_probe:
        reasons.append("edge_below_probe")
        return _decision(policy, "NO_TRADE", 0.0, market_remaining, surface_remaining, total_remaining, sizing_input.wallet_style, reasons)

    execution_poor = sizing_input.spread > policy.max_good_spread or sizing_input.depth_usd < policy.min_good_depth_usd
    if execution_poor:
        reasons.append("execution_quality_poor")

    if sizing_input.confidence < policy.min_confidence_open:
        reasons.append("confidence_below_open")

    if execution_poor or sizing_input.confidence < policy.min_confidence_open or sizing_input.net_edge < policy.min_net_edge_open:
        size = min(policy.probe_max_usdc, cap_remaining)
        size = max(min(size, policy.probe_max_usdc), policy.probe_min_usdc) if cap_remaining >= policy.probe_min_usdc else 0.0
        return _decision(policy, "PROBE" if size > 0 else "HOLD_CAPPED", size, market_remaining, surface_remaining, total_remaining, sizing_input.wallet_style, reasons)

    target = _edge_scaled_size(sizing_input.net_edge, policy)
    style = (sizing_input.wallet_style or "").lower()
    if "sparse/large-ticket" in style:
        reasons.append("large_ticket_style_capped")
        target = min(target, policy.open_max_usdc)
    elif "breadth/grid" in style:
        reasons.append("grid_style_reference")
    elif "selective" in style:
        reasons.append("selective_style_confidence_only")
        target = min(target, policy.open_max_usdc)

    size = min(target, cap_remaining)
    action = "ADD" if sizing_input.current_market_exposure_usdc > 0.0 else "OPEN"
    if size <= 0.0:
        action = "HOLD_CAPPED"
    return _decision(policy, action, size, market_remaining, surface_remaining, total_remaining, sizing_input.wallet_style, reasons)


def _edge_scaled_size(net_edge: float, policy: SizingPolicy) -> float:
    if net_edge >= 0.18:
        return policy.strong_max_usdc
    if net_edge >= 0.10:
        return policy.open_max_usdc
    return policy.open_min_usdc


def _decision(policy: SizingPolicy, action: str, size: float, market_remaining: float, surface_remaining: float, total_remaining: float, wallet_style: str | None, reasons: list[str]) -> DynamicSizingDecision:
    return DynamicSizingDecision(
        policy=policy.name,
        action=action,
        recommended_size_usdc=round(float(size), 4),
        max_market_remaining_usdc=round(float(market_remaining), 4),
        max_surface_remaining_usdc=round(float(surface_remaining), 4),
        max_total_remaining_usdc=round(float(total_remaining), 4),
        wallet_style_reference=wallet_style,
        reasons=list(reasons),
    )
```

**Step 2: Run tests**

```bash
PYTHONPATH=src python3 -m pytest tests/test_dynamic_position_sizing.py -q
```

Expected: pass.

---

## Phase 2 — Add portfolio exposure extraction

### Task 3: Add exposure aggregation tests

**Objective:** Compute current exposure by market, surface, and total from paper/open rows.

**Files:**
- Modify: `python/tests/test_dynamic_position_sizing.py`
- Modify: `python/src/weather_pm/dynamic_position_sizing.py`

**Step 1: Add failing test**

```python
from weather_pm.dynamic_position_sizing import build_exposure_index


def test_build_exposure_index_groups_by_market_and_surface() -> None:
    positions = [
        {"market_id": "m1", "surface_key": "Paris|2026-04-27|high_temp", "filled_usdc": 10.0},
        {"market_id": "m2", "surface_key": "Paris|2026-04-27|high_temp", "paper_notional_usd": 12.5},
        {"market_id": "m3", "surface_key": "Seoul|2026-04-27|high_temp", "filled_usdc": 7.5},
    ]

    exposure = build_exposure_index(positions)

    assert exposure["by_market"] == {"m1": 10.0, "m2": 12.5, "m3": 7.5}
    assert exposure["by_surface"] == {
        "Paris|2026-04-27|high_temp": 22.5,
        "Seoul|2026-04-27|high_temp": 7.5,
    }
    assert exposure["total_weather"] == 30.0
```

**Step 2: Implement helper**

Add:

```python
def build_exposure_index(positions: list[dict[str, Any]]) -> dict[str, Any]:
    by_market: dict[str, float] = {}
    by_surface: dict[str, float] = {}
    total = 0.0
    for row in positions:
        if not isinstance(row, dict):
            continue
        amount = _position_notional(row)
        if amount <= 0.0:
            continue
        market_id = str(row.get("market_id") or "").strip()
        surface_key = str(row.get("surface_key") or row.get("city_date_surface") or "").strip()
        if market_id:
            by_market[market_id] = round(by_market.get(market_id, 0.0) + amount, 4)
        if surface_key:
            by_surface[surface_key] = round(by_surface.get(surface_key, 0.0) + amount, 4)
        total += amount
    return {"by_market": by_market, "by_surface": by_surface, "total_weather": round(total, 4)}


def _position_notional(row: dict[str, Any]) -> float:
    for key in ("filled_usdc", "paper_notional_usd", "paper_notional_usdc", "notional_usdc", "spend_usdc"):
        value = row.get(key)
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                pass
    return 0.0
```

**Step 3: Verify**

```bash
PYTHONPATH=src python3 -m pytest tests/test_dynamic_position_sizing.py -q
```

---

## Phase 3 — Integrate with shortlist rows

### Task 4: Add dynamic sizing to strategy shortlist output

**Objective:** Every shortlist row with edge/entry data should include `dynamic_sizing` and use it for operator sizing text.

**Files:**
- Modify: `python/src/weather_pm/strategy_shortlist.py`
- Modify: `python/tests/test_weather_strategy_shortlist.py`

**Step 1: Add test expectation**

In the existing test around London edge sizing, add assertions like:

```python
assert london["dynamic_sizing"]["policy"] == "paper_weather_grid_default"
assert london["dynamic_sizing"]["action"] in {"OPEN", "PROBE", "ADD"}
assert london["dynamic_sizing"]["recommended_size_usdc"] > 0
assert london["operator_entry_summary"]["dynamic_size_usdc"] == london["dynamic_sizing"]["recommended_size_usdc"]
```

If the row has no exposure context, default current exposure to 0.

**Step 2: Import the new engine**

At the top of `strategy_shortlist.py`:

```python
from weather_pm.dynamic_position_sizing import SizingInput, SizingPolicy, calculate_dynamic_position_size
```

**Step 3: Build `surface_key`**

Add helper:

```python
def _surface_key(row: dict[str, Any], *, city: str | None, date: str | None) -> str:
    kind = row.get("market_kind") or row.get("kind") or "weather"
    return "|".join(str(part or "unknown") for part in [city, date, kind])
```

**Step 4: Attach dynamic sizing in `_shortlist_row`**

After `entry_decision` and `edge_sizing` are computed:

```python
dynamic = calculate_dynamic_position_size(
    SizingInput(
        market_id=str(row.get("market_id") or opportunity.get("market_id") or ""),
        surface_key=_surface_key(row, city=city, date=date),
        model_probability=float(opportunity.get("prediction_probability") or 0.0),
        market_price=float(opportunity.get("market_price") or 0.0),
        net_edge=float(edge_sizing.get("net_edge") if isinstance(edge_sizing, dict) else opportunity.get("probability_edge") or 0.0),
        confidence=float(opportunity.get("confidence") or 0.8),
        spread=float(opportunity.get("spread") or 0.0),
        depth_usd=float(opportunity.get("order_book_depth_usd") or 0.0),
        hours_to_resolution=_optional_number(opportunity.get("hours_to_resolution")),
        wallet_style=_dominant_wallet_style(matched_accounts),
        current_market_exposure_usdc=float(opportunity.get("current_market_exposure_usdc") or 0.0),
        current_surface_exposure_usdc=float(opportunity.get("current_surface_exposure_usdc") or 0.0),
        current_total_weather_exposure_usdc=float(opportunity.get("current_total_weather_exposure_usdc") or 0.0),
    )
)
row["surface_key"] = dynamic_input.surface_key
row["dynamic_sizing"] = dynamic.to_dict()
```

Use local variables so the exact code does not refer to `dynamic_input` before assignment.

**Step 5: Dominant wallet style helper**

```python
def _dominant_wallet_style(accounts: list[dict[str, Any]]) -> str | None:
    for account in accounts:
        style = account.get("style") or account.get("inferred_style") or account.get("strategy_style")
        if isinstance(style, str) and style.strip():
            return style.strip()
    return None
```

**Step 6: Verify targeted tests**

```bash
PYTHONPATH=src python3 -m pytest tests/test_weather_strategy_shortlist.py tests/test_dynamic_position_sizing.py -q
```

---

## Phase 4 — Upgrade entry decision to use dynamic size

### Task 5: Preserve static policy but expose dynamic size in operator summary

**Objective:** Do not break `EntryDecision`; add dynamic sizing as a parallel field first.

**Files:**
- Modify: `python/src/weather_pm/strategy_shortlist.py`
- Modify: `python/tests/test_weather_strategy_shortlist.py`

**Step 1: Add operator summary fields**

In `_operator_entry_summary`, add:

```python
dynamic = row.get("dynamic_sizing") if isinstance(row.get("dynamic_sizing"), dict) else None
if dynamic is not None:
    summary["dynamic_action"] = dynamic.get("action")
    summary["dynamic_size_usdc"] = _optional_number(dynamic.get("recommended_size_usdc"))
    summary["dynamic_reasons"] = list(dynamic.get("reasons") or [])
```

**Step 2: Test blocked/capped behavior**

Add a test where the shortlist row includes `current_surface_exposure_usdc=50.0`; assert:

```python
assert row["dynamic_sizing"]["action"] == "HOLD_CAPPED"
assert row["dynamic_sizing"]["recommended_size_usdc"] == 0.0
assert "surface_cap_reached" in row["dynamic_sizing"]["reasons"]
```

**Step 3: Verify**

```bash
PYTHONPATH=src python3 -m pytest tests/test_weather_strategy_shortlist.py tests/test_dynamic_position_sizing.py -q
```

---

## Phase 5 — Add wallet-profitable sizing profile extraction

### Task 6: Convert profitable-wallet artifacts into reusable priors

**Objective:** Let the system load known wallet style stats from artifacts without hardcoding account names.

**Files:**
- Create: `python/src/weather_pm/wallet_sizing_priors.py`
- Create: `python/tests/test_wallet_sizing_priors.py`

**Step 1: Write tests**

```python
from weather_pm.wallet_sizing_priors import build_wallet_sizing_priors


def test_build_wallet_sizing_priors_summarizes_styles() -> None:
    payload = {
        "accounts": [
            {"handle": "Railbird", "style": "breadth/grid small-ticket surface trader", "recent_trade_avg_usdc": 21.43, "recent_trade_max_usdc": 29.98},
            {"handle": "ColdMath", "style": "sparse/large-ticket conviction trader", "recent_trade_avg_usdc": 194.87, "recent_trade_max_usdc": 4149.66},
            {"handle": "0xhana", "style": "breadth/grid small-ticket surface trader", "recent_trade_avg_usdc": 23.69, "recent_trade_max_usdc": 75.0},
        ]
    }

    priors = build_wallet_sizing_priors(payload)

    grid = priors["styles"]["breadth/grid small-ticket surface trader"]
    assert grid["accounts"] == 2
    assert grid["median_recent_trade_avg_usdc"] == 22.56
    assert grid["recommended_copy_mode"] == "imitate_small_grid_notional"

    large = priors["styles"]["sparse/large-ticket conviction trader"]
    assert large["recommended_copy_mode"] == "confidence_only_cap_size"
```

**Step 2: Implement module**

Use `statistics.median`, group by `style`, and return:

```json
{
  "styles": {
    "breadth/grid small-ticket surface trader": {
      "accounts": 18,
      "median_recent_trade_avg_usdc": 25.95,
      "median_recent_trade_max_usdc": 211.24,
      "recommended_copy_mode": "imitate_small_grid_notional"
    }
  }
}
```

**Step 3: Verify**

```bash
PYTHONPATH=src python3 -m pytest tests/test_wallet_sizing_priors.py -q
```

---

## Phase 6 — CLI / artifact output

### Task 7: Add a CLI command to build sizing priors from artifacts

**Objective:** Regenerate sizing priors from the saved profitable-wallet file.

**Files:**
- Modify: `python/src/weather_pm/cli.py`
- Modify or create CLI test in `python/tests/test_cli_score_market.py` or new `python/tests/test_wallet_sizing_priors_cli.py`

**CLI target:**

```bash
PYTHONPATH=src python3 -m weather_pm.cli wallet-sizing-priors \
  --input ../data/polymarket/weather_priority_accounts_recent_behavior_20260425.json \
  --output ../data/polymarket/weather_wallet_sizing_priors_latest.json
```

**Expected JSON fields:**

```json
{
  "source": "...weather_priority_accounts_recent_behavior_20260425.json",
  "styles": {...},
  "operator_default_style": "breadth/grid small-ticket surface trader",
  "copy_warning": "wallet priors adjust size/confidence but do not authorize blind copy-trading"
}
```

**Verification:**

```bash
PYTHONPATH=src python3 -m pytest tests/test_wallet_sizing_priors.py tests/test_wallet_sizing_priors_cli.py -q
```

---

## Phase 7 — Paper monitor integration

### Task 8: Apply dynamic sizing to paper add decisions

**Objective:** Existing paper monitor should use dynamic sizing before allowing `ADD_REVIEW` or `OPTIONAL_TINY_ADD`.

**Files:**
- Modify: `python/src/weather_pm/paper_watchlist.py`
- Modify: `python/tests/test_paper_watchlist.py`

**Rules:**

- If current market or surface cap reached → `HOLD_CAPPED`, no add.
- If `dynamic_sizing.action == PROBE` → only allow tiny paper add if not already added this cycle.
- If `dynamic_sizing.action in {OPEN, ADD}` and existing exposure < cap → allow add capped by `recommended_size_usdc`.
- If paper add already executed in current cycle → no repeated add.

**Test examples:**

```python
def test_paper_watchlist_uses_dynamic_surface_cap_to_block_add():
    ...
    assert row["operator_action"] == "HOLD_CAPPED"
    assert row["add_allowed"] is False
    assert row["dynamic_sizing"]["action"] == "HOLD_CAPPED"
```

**Verification:**

```bash
PYTHONPATH=src python3 -m pytest tests/test_paper_watchlist.py tests/test_dynamic_position_sizing.py -q
```

---

## Phase 8 — Full validation and rollout

### Task 9: Run targeted validation bundle

**Objective:** Ensure sizing changes do not break existing operator behavior.

Run:

```bash
cd /home/jul/prediction_core/python
PYTHONPATH=src python3 -m pytest \
  tests/test_dynamic_position_sizing.py \
  tests/test_wallet_sizing_priors.py \
  tests/test_edge_sizing.py \
  tests/test_entry_policy.py \
  tests/test_weather_strategy_shortlist.py \
  tests/test_paper_watchlist.py \
  tests/test_paper_watchlist_cli.py \
  -q
```

Expected: all pass.

### Task 10: Run full Python suite

```bash
cd /home/jul/prediction_core/python
PYTHONPATH=src python3 -m pytest tests -q
```

Expected: all pass.

### Task 11: Generate one paper-only sizing report

Use a known artifact and generate latest priors:

```bash
cd /home/jul/prediction_core/python
PYTHONPATH=src python3 -m weather_pm.cli wallet-sizing-priors \
  --input ../data/polymarket/weather_priority_accounts_recent_behavior_20260425.json \
  --output ../data/polymarket/weather_wallet_sizing_priors_latest.json
```

Then regenerate/refresh an operator shortlist if an existing CLI command is available. If no stable CLI exists, do not invent one; only verify module tests and artifacts.

### Task 12: Commit only source/tests/docs, not live generated data unless requested

Check status:

```bash
git status --short
```

Stage only implementation + tests + this plan if appropriate:

```bash
git add \
  .hermes/plans/2026-04-26_213441-polymarket-dynamic-position-sizing.md \
  python/src/weather_pm/dynamic_position_sizing.py \
  python/src/weather_pm/wallet_sizing_priors.py \
  python/src/weather_pm/strategy_shortlist.py \
  python/src/weather_pm/paper_watchlist.py \
  python/src/weather_pm/cli.py \
  python/tests/test_dynamic_position_sizing.py \
  python/tests/test_wallet_sizing_priors.py \
  python/tests/test_weather_strategy_shortlist.py \
  python/tests/test_paper_watchlist.py
```

Commit:

```bash
git commit -m "feat: add dynamic Polymarket weather position sizing"
```

Do not stage `data/polymarket/*` generated outputs unless Julien explicitly asks.

---

## Risks and mitigations

### Risk: copying profitable wallets blindly

**Mitigation:** Wallet style only adjusts confidence/size caps. It never authorizes copy-trading by itself.

### Risk: oversized correlated exposure

**Mitigation:** Enforce surface/city/date caps before sizing.

### Risk: large-ticket profiles distort defaults

**Mitigation:** Default to `breadth/grid small-ticket surface trader`; large-ticket style gets capped to normal small size.

### Risk: existing tests expect static `size_hint_usd`

**Mitigation:** Add `dynamic_sizing` in parallel first; do not remove or change `EntryDecision.size_hint_usd` until downstream surfaces are migrated.

### Risk: generated artifact churn

**Mitigation:** Tests should use fixtures/dicts, not live data files. Generated `data/polymarket/*` should remain uncommitted unless requested.

---

## Acceptance criteria

- `dynamic_position_sizing.py` exists and is deterministic/pure.
- Sizing outputs include action, size, cap remaining, wallet style reference, and reasons.
- Shortlist rows include `surface_key` and `dynamic_sizing`.
- Operator summaries expose `dynamic_size_usdc` and reasons.
- Paper watchlist add decisions obey dynamic cap rules.
- Wallet sizing priors can be built from the profitable-account artifact.
- Targeted pytest bundle passes.
- Full Python pytest suite passes.
- No real Polymarket orders are placed.
