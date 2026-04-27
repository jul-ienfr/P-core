# Polymarket Live-Ready Execution Implementation Plan

> **For Hermes:** Use `phase-plan-executor` or `subagent-driven-development` to execute this plan task-by-task. Use strict TDD. Do not enable real-money trading until the final operator switch task, and even then keep the default mode `paper`.

**Goal:** Make the Polymarket weather runtime live-ready so moving from paper to live is a controlled config change, with execution, risk, idempotence, audit, and reconciliation already tested.

**Architecture:** Keep strategy/scoring/paper logic separate from order execution. Add a canonical `prediction_core.polymarket_execution` layer with an injected executor interface, a dry-run executor, a future real CLOB executor seam, pre-trade risk gates, idempotency, append-only audit logs, and exchange reconciliation. `prediction_core.polymarket_runtime` remains the orchestrator and must route all live orders through the explicit executor interface only.

**Tech Stack:** Python 3.x, pytest, existing `/home/jul/prediction_core/python` src layout, existing `prediction_core.polymarket_runtime`, `prediction_core.polymarket_marketdata`, `prediction_core.execution`, `prediction_core.decision`, and existing CLI wrapper `python/scripts/prediction-core`.

---

## Contexte vérifié

Verified live on 2026-04-27:

- Repo root: `/home/jul/prediction_core`; Python package root: `/home/jul/prediction_core/python`.
- Current branch: `main...origin/main`.
- Existing runtime file: `python/src/prediction_core/polymarket_runtime.py`.
- Existing market-data file: `python/src/prediction_core/polymarket_marketdata.py`.
- Existing stack recommendation file: `python/src/prediction_core/polymarket_stack.py` says:
  - Gamma REST for discovery outside hot path;
  - CLOB WebSocket for hot market data;
  - CLOB REST for authenticated order placement/cancel;
  - Data API for analytics outside hot path.
- Existing runtime currently has:
  - `evaluate_cached_market_decisions(...)` producing `PAPER_SIGNAL_ONLY`, `HOLD`, or `WAIT_MARKETDATA` decisions;
  - `plan_disabled_execution_actions(...)` now accepts `execution_mode="paper"|"live"` and requires an injected `order_executor` for live;
  - `run_polymarket_runtime_cycle(...)` still calls the planner in default paper mode.
- Existing market-data cache tracks best bid/ask/spread/depth and CLOB websocket snapshots.
- Existing strategy layer exists under `python/src/prediction_core/strategies/` with contracts, registry, weather/Panoptique adapters, measurement, bookmaker bridge, paper bridge, and CLI smoke surface.
- Current targeted verification run:
  - `PYTHONPATH=src python3 -m pytest tests/test_polymarket_runtime_scaffold.py tests/test_strategy_*.py tests/test_execution_*.py tests/test_paper_execution_integration.py -q`
  - Result: `86 passed`.
- Current uncommitted work exists from previous slices. Before executing this plan, inspect `git status --short` and avoid mixing unrelated strategy-plan files with this execution work.

## Non-goals / guardrails

- Do not store private keys in git, tests, docs, or examples.
- Do not submit real orders during implementation tests.
- Do not make `live` the default.
- Do not let strategy code call an exchange client directly.
- Do not bypass risk gates for convenience.
- Do not use market orders. Initial live path is limit orders only.
- Do not add auto-size escalation. Keep sizing explicit and capped.
- Do not call live CLOB REST in unit tests; use injected fakes/dry-run adapters.

## Target live switch contract

Final operator config should be conceptually this small:

```json
{
  "execution_mode": "paper",
  "executor": "dry_run",
  "max_position_usdc": 10,
  "max_daily_loss_usdc": 25,
  "max_total_exposure_usdc": 100
}
```

Then, only after credentials and manual approval:

```json
{
  "execution_mode": "live",
  "executor": "clob_rest",
  "max_position_usdc": 10,
  "max_daily_loss_usdc": 25,
  "max_total_exposure_usdc": 100
}
```

`execution_mode="live"` must still fail closed if executor credentials, risk state, idempotency store, or audit log are unavailable.

---

## Phase 0 — Stabilize current worktree before live-ready changes

**Goal:** Avoid mixing live-execution work with unrelated strategy/core files.

### Task 0.1: Inspect current diff and untracked files

**Files:** none.

**Step 1: Run status**

```bash
cd /home/jul/prediction_core
git status --short --branch
```

**Expected:** Shows current modified/untracked files. Decide whether to commit, stash, or continue on a feature branch.

**Step 2: Run targeted baseline**

```bash
cd /home/jul/prediction_core/python
PYTHONPATH=src python3 -m pytest tests/test_polymarket_runtime_scaffold.py tests/test_strategy_*.py tests/test_execution_*.py tests/test_paper_execution_integration.py -q
```

**Expected:** pass. Last verified state was `86 passed`.

### Task 0.2: Create a dedicated branch

**Files:** none.

```bash
cd /home/jul/prediction_core
git switch -c feat/polymarket-live-ready-execution
```

If branch already exists, use:

```bash
git switch feat/polymarket-live-ready-execution
```

---

## Phase 1 — Canonical order/executor contracts

Status: completed for Tasks 1.1 and 1.2 in this slice.

**Goal:** Create a small deterministic execution contract that all paper/dry/live paths use.

### Task 1.1: Add failing tests for order request/result models

- [x] Completed in this slice.

**Files:**
- Create: `python/tests/test_polymarket_execution_contracts.py`
- Create later: `python/src/prediction_core/polymarket_execution.py`

**Step 1: Write failing test**

```python
import pytest

from prediction_core.polymarket_execution import ExecutionMode, OrderRequest, OrderResult, OrderSide, OrderType


def test_order_request_serializes_limit_buy():
    order = OrderRequest(
        market_id="m1",
        token_id="yes-token",
        outcome="Yes",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        limit_price=0.44,
        notional_usdc=7.5,
        idempotency_key="weather:m1:yes-token:buy:20260427T010000Z",
    )

    assert order.to_dict() == {
        "market_id": "m1",
        "token_id": "yes-token",
        "outcome": "Yes",
        "side": "buy",
        "order_type": "limit",
        "limit_price": 0.44,
        "notional_usdc": 7.5,
        "idempotency_key": "weather:m1:yes-token:buy:20260427T010000Z",
        "metadata": {},
    }


def test_order_request_rejects_invalid_price_and_size():
    with pytest.raises(ValueError, match="limit_price must be between 0 and 1"):
        OrderRequest(market_id="m1", token_id="t", outcome="Yes", side="buy", order_type="limit", limit_price=1.5, notional_usdc=5, idempotency_key="k")
    with pytest.raises(ValueError, match="notional_usdc must be positive"):
        OrderRequest(market_id="m1", token_id="t", outcome="Yes", side="buy", order_type="limit", limit_price=0.5, notional_usdc=0, idempotency_key="k")


def test_order_result_serializes_executor_response():
    result = OrderResult(
        accepted=True,
        status="accepted",
        exchange_order_id="dry-1",
        idempotency_key="k",
        raw_response={"ok": True},
    )

    assert result.to_dict()["accepted"] is True
    assert result.to_dict()["exchange_order_id"] == "dry-1"
```

**Step 2: Verify RED**

```bash
cd /home/jul/prediction_core/python
PYTHONPATH=src python3 -m pytest tests/test_polymarket_execution_contracts.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'prediction_core.polymarket_execution'`.

### Task 1.2: Implement minimal contracts

- [x] Completed in this slice.

**Files:**
- Create: `python/src/prediction_core/polymarket_execution.py`

**Implementation sketch:**

```python
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Protocol


class ExecutionMode(str, Enum):
    PAPER = "paper"
    DRY_RUN = "dry_run"
    LIVE = "live"


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    LIMIT = "limit"


def _enum_value(value: Any) -> Any:
    return value.value if isinstance(value, Enum) else value


@dataclass(frozen=True, kw_only=True)
class OrderRequest:
    market_id: str
    token_id: str
    outcome: str
    side: OrderSide | str
    order_type: OrderType | str
    limit_price: float
    notional_usdc: float
    idempotency_key: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.market_id.strip():
            raise ValueError("market_id is required")
        if not self.token_id.strip():
            raise ValueError("token_id is required")
        if not self.idempotency_key.strip():
            raise ValueError("idempotency_key is required")
        object.__setattr__(self, "side", OrderSide(str(self.side).lower()))
        object.__setattr__(self, "order_type", OrderType(str(self.order_type).lower()))
        if not 0.0 < float(self.limit_price) < 1.0:
            raise ValueError("limit_price must be between 0 and 1")
        if float(self.notional_usdc) <= 0.0:
            raise ValueError("notional_usdc must be positive")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["side"] = _enum_value(self.side)
        payload["order_type"] = _enum_value(self.order_type)
        return payload


@dataclass(frozen=True, kw_only=True)
class OrderResult:
    accepted: bool
    status: str
    idempotency_key: str
    exchange_order_id: str | None = None
    raw_response: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class OrderExecutor(Protocol):
    def submit_order(self, order: OrderRequest) -> OrderResult:
        ...
```

**Step 3: Verify GREEN**

```bash
PYTHONPATH=src python3 -m pytest tests/test_polymarket_execution_contracts.py -q
python3 -m py_compile src/prediction_core/polymarket_execution.py tests/test_polymarket_execution_contracts.py
```

Expected: pass.

---

## Phase 2 — Dry-run executor and runtime adapter

Status: completed for runtime adapter Task 2.3 in this slice. Dry-run executor Tasks 2.1 and 2.2 were already completed by the prior execution-layer slice.

**Goal:** Make the runtime use the canonical `OrderExecutor` contract without hitting real Polymarket.

### Task 2.1: Add failing tests for `DryRunPolymarketExecutor`

**Files:**
- Modify: `python/tests/test_polymarket_execution_contracts.py`
- Modify later: `python/src/prediction_core/polymarket_execution.py`

**Test to add:**

```python
from prediction_core.polymarket_execution import DryRunPolymarketExecutor


def test_dry_run_executor_accepts_without_network_and_records_order():
    executor = DryRunPolymarketExecutor()
    order = OrderRequest(
        market_id="m1",
        token_id="yes-token",
        outcome="Yes",
        side="buy",
        order_type="limit",
        limit_price=0.44,
        notional_usdc=7.5,
        idempotency_key="k1",
    )

    result = executor.submit_order(order)

    assert result.accepted is True
    assert result.status == "dry_run_accepted"
    assert result.exchange_order_id == "dry-run:k1"
    assert executor.orders == [order]
```

**Verify RED:**

```bash
PYTHONPATH=src python3 -m pytest tests/test_polymarket_execution_contracts.py::test_dry_run_executor_accepts_without_network_and_records_order -q
```

Expected: import/name failure.

### Task 2.2: Implement dry-run executor

**Files:**
- Modify: `python/src/prediction_core/polymarket_execution.py`

**Implementation sketch:**

```python
class DryRunPolymarketExecutor:
    def __init__(self) -> None:
        self.orders: list[OrderRequest] = []

    def submit_order(self, order: OrderRequest) -> OrderResult:
        self.orders.append(order)
        return OrderResult(
            accepted=True,
            status="dry_run_accepted",
            exchange_order_id=f"dry-run:{order.idempotency_key}",
            idempotency_key=order.idempotency_key,
            raw_response={"dry_run": True, "order": order.to_dict()},
        )
```

**Verify GREEN:**

```bash
PYTHONPATH=src python3 -m pytest tests/test_polymarket_execution_contracts.py -q
```

### Task 2.3: Update runtime planner to use `OrderExecutor.submit_order`

- [x] Completed in this slice.

**Files:**
- Modify: `python/src/prediction_core/polymarket_runtime.py`
- Modify: `python/tests/test_polymarket_runtime_scaffold.py`

**Goal:** Replace raw callable `order_executor(order_dict)` with canonical `OrderExecutor.submit_order(OrderRequest)`.

**Test changes:**

Update existing live-mode test to use `DryRunPolymarketExecutor` and assert `executor_result.status == dry_run_accepted`.

**Implementation notes:**

- Build `OrderRequest` from each `PAPER_SIGNAL_ONLY` decision.
- Construct idempotency key initially as deterministic fallback:
  `f"{market_id}:{token_id}:BUY:{limit_price}:{notional_usdc}"`
- Return `orders_submitted` as serialized order + serialized result.
- Keep `execution_mode="paper"` behavior backward-compatible.

**Verify:**

```bash
PYTHONPATH=src python3 -m pytest tests/test_polymarket_runtime_scaffold.py tests/test_polymarket_execution_contracts.py -q
```

---

## Phase 3 — Pre-trade risk gates

Status: completed for Tasks 3.1 and 3.2 in this slice. Task 3.3 remains pending because this slice intentionally did not touch runtime.

**Goal:** Ensure live execution cannot occur unless exposure, spread, stale-book, and loss limits are acceptable.

### Task 3.1: Add risk model tests

- [x] Completed in this slice.

**Files:**
- Create: `python/tests/test_polymarket_execution_risk.py`
- Modify later: `python/src/prediction_core/polymarket_execution.py`

**Tests:**

```python
import pytest

from prediction_core.polymarket_execution import ExecutionRiskLimits, ExecutionRiskState, OrderRequest, evaluate_execution_risk


def _order(notional=7.5, price=0.44):
    return OrderRequest(market_id="m1", token_id="t", outcome="Yes", side="buy", order_type="limit", limit_price=price, notional_usdc=notional, idempotency_key="k")


def test_risk_allows_order_inside_limits():
    result = evaluate_execution_risk(
        _order(),
        limits=ExecutionRiskLimits(max_order_notional_usdc=10, max_total_exposure_usdc=100, max_daily_loss_usdc=25, max_spread=0.05),
        state=ExecutionRiskState(total_exposure_usdc=20, daily_realized_pnl_usdc=0),
        market_snapshot={"spread": 0.03, "sequence": 10},
    )

    assert result.allowed is True
    assert result.blocked_by == []


def test_risk_blocks_oversized_order():
    result = evaluate_execution_risk(
        _order(notional=11),
        limits=ExecutionRiskLimits(max_order_notional_usdc=10, max_total_exposure_usdc=100, max_daily_loss_usdc=25, max_spread=0.05),
        state=ExecutionRiskState(total_exposure_usdc=20, daily_realized_pnl_usdc=0),
        market_snapshot={"spread": 0.03, "sequence": 10},
    )

    assert result.allowed is False
    assert "max_order_notional_usdc" in result.blocked_by


def test_risk_blocks_wide_spread_and_daily_loss():
    result = evaluate_execution_risk(
        _order(),
        limits=ExecutionRiskLimits(max_order_notional_usdc=10, max_total_exposure_usdc=100, max_daily_loss_usdc=25, max_spread=0.05),
        state=ExecutionRiskState(total_exposure_usdc=20, daily_realized_pnl_usdc=-30),
        market_snapshot={"spread": 0.08, "sequence": 10},
    )

    assert result.allowed is False
    assert set(result.blocked_by) >= {"max_spread", "max_daily_loss_usdc"}
```

**Verify RED:** fails because classes/functions do not exist.

### Task 3.2: Implement risk dataclasses and evaluator

- [x] Completed in this slice.

**Files:**
- Modify: `python/src/prediction_core/polymarket_execution.py`

Add:

```python
@dataclass(frozen=True, kw_only=True)
class ExecutionRiskLimits:
    max_order_notional_usdc: float
    max_total_exposure_usdc: float
    max_daily_loss_usdc: float
    max_spread: float

@dataclass(frozen=True, kw_only=True)
class ExecutionRiskState:
    total_exposure_usdc: float = 0.0
    daily_realized_pnl_usdc: float = 0.0

@dataclass(frozen=True, kw_only=True)
class ExecutionRiskDecision:
    allowed: bool
    blocked_by: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_execution_risk(order: OrderRequest, *, limits: ExecutionRiskLimits, state: ExecutionRiskState, market_snapshot: dict[str, Any]) -> ExecutionRiskDecision:
    blocked = []
    if order.notional_usdc > limits.max_order_notional_usdc:
        blocked.append("max_order_notional_usdc")
    if state.total_exposure_usdc + order.notional_usdc > limits.max_total_exposure_usdc:
        blocked.append("max_total_exposure_usdc")
    if state.daily_realized_pnl_usdc <= -abs(limits.max_daily_loss_usdc):
        blocked.append("max_daily_loss_usdc")
    spread = market_snapshot.get("spread")
    if spread is None:
        blocked.append("missing_spread")
    elif float(spread) > limits.max_spread:
        blocked.append("max_spread")
    return ExecutionRiskDecision(allowed=not blocked, blocked_by=blocked)
```

**Verify:**

```bash
PYTHONPATH=src python3 -m pytest tests/test_polymarket_execution_risk.py tests/test_polymarket_execution_contracts.py -q
```

### Task 3.3: Enforce risk in runtime live path

- [x] Completed in this slice.

**Files:**
- Modify: `python/tests/test_polymarket_runtime_scaffold.py`
- Modify: `python/src/prediction_core/polymarket_runtime.py`

**Test:** live planner with a wide spread decision must not call executor and must return blocked order attempt with `blocked_by=["max_spread"]`.

**Implementation notes:**

- Extend planner parameters:
  - `risk_limits: ExecutionRiskLimits | None = None`
  - `risk_state: ExecutionRiskState | None = None`
- In live mode, require `risk_limits` and `risk_state`; fail closed if missing.
- For paper mode, keep current behavior unchanged.
- Decision market snapshot can be extracted from decision fields: `spread`, `best_bid`, `best_ask`.

**Verify:**

```bash
PYTHONPATH=src python3 -m pytest tests/test_polymarket_runtime_scaffold.py tests/test_polymarket_execution_risk.py -q
```

---

## Phase 4 — Idempotency store

Status: completed for Tasks 4.1 and 4.2 in this slice. Task 4.3 remains pending because this slice intentionally did not touch runtime.

**Goal:** Prevent duplicate orders from repeated cron/runtime cycles.

### Task 4.1: Add JSONL idempotency store tests

- [x] Completed in this slice.

**Files:**
- Create: `python/tests/test_polymarket_execution_idempotency.py`
- Modify later: `python/src/prediction_core/polymarket_execution.py`

**Tests:**

```python
from prediction_core.polymarket_execution import JsonlIdempotencyStore


def test_idempotency_store_claims_key_once(tmp_path):
    store = JsonlIdempotencyStore(tmp_path / "ids.jsonl")

    assert store.claim("k1", metadata={"market_id": "m1"}) is True
    assert store.claim("k1", metadata={"market_id": "m1"}) is False
    assert store.seen("k1") is True


def test_idempotency_store_survives_reopen(tmp_path):
    path = tmp_path / "ids.jsonl"
    assert JsonlIdempotencyStore(path).claim("k1") is True
    assert JsonlIdempotencyStore(path).claim("k1") is False
```

**Verify RED:** missing class.

### Task 4.2: Implement `JsonlIdempotencyStore`

- [x] Completed in this slice.

**Files:**
- Modify: `python/src/prediction_core/polymarket_execution.py`

**Implementation notes:**

- Load existing JSONL keys on init.
- `claim(key)` returns False if already seen.
- Append JSON object with `key`, `claimed_at`, `metadata`.
- Parent dirs created automatically.
- No external DB yet; JSONL is enough for local cron safety.

**Verify:**

```bash
PYTHONPATH=src python3 -m pytest tests/test_polymarket_execution_idempotency.py -q
```

### Task 4.3: Enforce idempotency in live planner

- [x] Completed in this slice.

**Files:**
- Modify: `python/tests/test_polymarket_runtime_scaffold.py`
- Modify: `python/src/prediction_core/polymarket_runtime.py`

**Expected behavior:**

- If idempotency key already claimed, skip executor call.
- Output attempt with `status="duplicate_skipped"` and original key.

**Verify:**

```bash
PYTHONPATH=src python3 -m pytest tests/test_polymarket_runtime_scaffold.py tests/test_polymarket_execution_idempotency.py -q
```

---

## Phase 5 — Append-only audit log

Status: completed for Tasks 5.1 and 5.2 in this slice. Task 5.3 remains pending because this slice intentionally did not touch runtime.

**Goal:** Every live/dry-run attempt is reconstructable after the fact.

### Task 5.1: Add audit log tests

- [x] Completed in this slice.

**Files:**
- Create: `python/tests/test_polymarket_execution_audit.py`
- Modify later: `python/src/prediction_core/polymarket_execution.py`

**Tests:**

```python
import json

from prediction_core.polymarket_execution import JsonlExecutionAuditLog


def test_audit_log_appends_decision_order_and_result(tmp_path):
    path = tmp_path / "audit.jsonl"
    log = JsonlExecutionAuditLog(path)

    log.append("decision", {"market_id": "m1", "action": "PAPER_SIGNAL_ONLY"})
    log.append("order_submitted", {"idempotency_key": "k1", "status": "dry_run_accepted"})

    rows = [json.loads(line) for line in path.read_text().splitlines()]
    assert [row["event_type"] for row in rows] == ["decision", "order_submitted"]
    assert rows[0]["payload"]["market_id"] == "m1"
    assert "recorded_at" in rows[0]
```

### Task 5.2: Implement audit log

- [x] Completed in this slice.

**Files:**
- Modify: `python/src/prediction_core/polymarket_execution.py`

**Implementation notes:**

- `append(event_type, payload)` writes one JSON line.
- Include UTC ISO `recorded_at`.
- Return written row for tests/callers.

### Task 5.3: Wire audit into planner

- [x] Completed in this slice.

**Files:**
- Modify: `python/src/prediction_core/polymarket_runtime.py`
- Modify: `python/tests/test_polymarket_runtime_scaffold.py`

**Expected events:**

- `execution_decision_seen`
- `execution_order_blocked` if risk/idempotency blocks
- `execution_order_submitted` if executor called
- `execution_order_failed` if executor raises

**Verify:**

```bash
PYTHONPATH=src python3 -m pytest tests/test_polymarket_execution_audit.py tests/test_polymarket_runtime_scaffold.py -q
```

---

## Phase 6 — Reconciliation interface

Status: completed for Tasks 6.1 and 6.2 in this slice.

**Goal:** Compare local submitted orders/ledger with exchange-reported orders/fills before trusting live state.

### Task 6.1: Add reconciliation tests

- [x] Completed in this slice.

**Files:**
- Create: `python/tests/test_polymarket_execution_reconciliation.py`
- Modify later: `python/src/prediction_core/polymarket_execution.py`

**Tests:**

```python
from prediction_core.polymarket_execution import reconcile_orders


def test_reconcile_orders_detects_missing_exchange_order():
    local = [{"exchange_order_id": "ord-1", "token_id": "t", "notional_usdc": 5.0}]
    exchange = []

    result = reconcile_orders(local_orders=local, exchange_orders=exchange)

    assert result["missing_on_exchange"] == ["ord-1"]
    assert result["unexpected_on_exchange"] == []
    assert result["ok"] is False


def test_reconcile_orders_passes_matching_order_ids():
    local = [{"exchange_order_id": "ord-1", "token_id": "t"}]
    exchange = [{"id": "ord-1", "token_id": "t"}]

    result = reconcile_orders(local_orders=local, exchange_orders=exchange)

    assert result["ok"] is True
```

### Task 6.2: Implement reconciliation helper

- [x] Completed in this slice.

**Files:**
- Modify: `python/src/prediction_core/polymarket_execution.py`

**Implementation notes:**

- Keep it pure and payload-based first.
- Later real Data/CLOB API fetcher can feed it.
- Match by `exchange_order_id` local and `id`/`order_id` exchange.

**Verify:**

```bash
PYTHONPATH=src python3 -m pytest tests/test_polymarket_execution_reconciliation.py -q
```

---

## Phase 7 — Future real CLOB executor seam, fail-closed without credentials

Status: completed for Tasks 7.1 and 7.2 in this slice.

**Goal:** Add the production seam without implementing unsafe credential handling yet.

### Task 7.1: Add tests for credential fail-closed behavior

- [x] Completed in this slice.

**Files:**
- Modify: `python/tests/test_polymarket_execution_contracts.py`
- Modify later: `python/src/prediction_core/polymarket_execution.py`

**Test:**

```python
import pytest

from prediction_core.polymarket_execution import ClobRestPolymarketExecutor, ExecutionCredentialsError


def test_clob_rest_executor_requires_credentials():
    with pytest.raises(ExecutionCredentialsError, match="credentials are required"):
        ClobRestPolymarketExecutor.from_env(env={})
```

### Task 7.2: Implement fail-closed CLOB executor stub

- [x] Completed in this slice.

**Files:**
- Modify: `python/src/prediction_core/polymarket_execution.py`

**Implementation notes:**

- Add `ExecutionCredentialsError`.
- `from_env(env=os.environ)` checks required names but does not log their values.
- Required env names can be placeholders initially:
  - `POLYMARKET_PRIVATE_KEY`
  - `POLYMARKET_FUNDER_ADDRESS`
  - `POLYMARKET_CHAIN_ID`
- `submit_order` can raise `NotImplementedError("real CLOB REST submission not wired yet")` until actual client is integrated in a later explicit task.
- This keeps live mode impossible unless real executor implementation is consciously completed.

**Verify:**

```bash
PYTHONPATH=src python3 -m pytest tests/test_polymarket_execution_contracts.py -q
```

---

## Phase 8 — CLI/config switch surface

Status: completed for Tasks 8.1 and 8.2 in this slice.

**Goal:** Expose execution mode safely through CLI/runtime config.

### Task 8.1: Add CLI tests for default paper and dry-run mode

- [x] Completed in this slice.

**Files:**
- Modify: `python/tests/test_polymarket_runtime_scaffold.py` or create `python/tests/test_polymarket_execution_cli.py`
- Modify later: CLI parser in `python/src/prediction_core/app.py` or existing script wiring used by `python/scripts/prediction-core`

**Expected behavior:**

- Existing `polymarket-runtime-cycle` remains paper by default.
- New arg `--execution-mode paper|dry_run|live` exists.
- `--execution-mode live` without explicit env/credentials/executor setup exits non-zero with fail-closed error.
- `--execution-mode dry_run` produces `orders_submitted` with `dry_run_accepted`, no real network.

**Verify:**

```bash
PYTHONPATH=src python3 -m pytest tests/test_polymarket_runtime_scaffold.py -q
```

### Task 8.2: Implement CLI args and executor selection

- [x] Completed in this slice.

**Files:**
- Modify: likely `python/src/prediction_core/app.py` and/or script command handler for `polymarket-runtime-cycle`.

**Implementation notes:**

- Add `--execution-mode`, default `paper`.
- For `dry_run`, instantiate `DryRunPolymarketExecutor`.
- For `live`, instantiate `ClobRestPolymarketExecutor.from_env()` only after risk/idempotency/audit paths are configured.
- Require paths:
  - `--idempotency-jsonl`
  - `--audit-jsonl`
- In live mode, refuse if either path missing.

---

## Phase 9 — End-to-end dry-run live rehearsal

Status: completed for Tasks 9.1 and 9.2 in this slice.

**Goal:** Prove the full live path works without real orders.

### Task 9.1: Add E2E dry-run fixture test

- [x] Completed in this slice.

**Files:**
- Create: `python/tests/test_polymarket_live_ready_dry_run.py`

**Scenario:**

- Fixture market with two tokens.
- Fixture CLOB websocket events.
- Probability says YES has enough edge.
- Runtime cycle uses `execution_mode="dry_run"`.
- Risk limits allow order.
- Idempotency store empty.
- Audit log path provided.

**Expected:**

- one dry-run order submitted;
- idempotency key recorded;
- audit has decision + submitted event;
- no paper intent for that order;
- no real network call.

### Task 9.2: Implement runtime support until E2E passes

- [x] Completed in this slice.

**Files:**
- Modify runtime/CLI as needed.

**Verify:**

```bash
PYTHONPATH=src python3 -m pytest tests/test_polymarket_live_ready_dry_run.py tests/test_polymarket_runtime_scaffold.py tests/test_polymarket_execution_*.py -q
```

---

## Phase 10 — Documentation and operator runbook

Status: completed for Tasks 10.1 and 10.2 in this slice.

**Goal:** Make tomorrow’s live switch boring and auditable.

### Task 10.1: Write live-ready runbook

- [x] Completed in this slice.

**Files:**
- Create: `docs/polymarket-live-ready-runbook.md`

**Must include:**

- mode definitions: `paper`, `dry_run`, `live`;
- exact CLI examples;
- required env vars, without values;
- risk limits explanation;
- idempotency store path;
- audit log path;
- pre-live checklist;
- rollback checklist;
- post-run reconciliation checklist.

### Task 10.2: Add docs test or smoke check if docs tooling exists

- [x] Completed in this slice with targeted `git diff --check` validation.

If no docs tooling exists, at minimum run:

```bash
cd /home/jul/prediction_core
git diff --check
```

---

## Phase 11 — Final verification

**Goal:** Confirm the live-ready path is tested without sending real orders.

Run from `/home/jul/prediction_core/python`:

```bash
PYTHONPATH=src python3 -m pytest tests/test_polymarket_execution_*.py tests/test_polymarket_runtime_scaffold.py tests/test_polymarket_live_ready_dry_run.py -q
PYTHONPATH=src python3 -m pytest tests/test_strategy_*.py tests/test_execution_*.py tests/test_paper_execution_integration.py -q
PYTHONPATH=src python3 -m pytest tests -q
python3 -m py_compile src/prediction_core/polymarket_execution.py src/prediction_core/polymarket_runtime.py
```

Run from `/home/jul/prediction_core`:

```bash
git diff --check
git status --short
```

Expected:

- all tests pass;
- no real order was submitted;
- docs/runbook exists;
- live mode is still fail-closed unless explicit executor, risk limits, idempotency store, audit log, and credentials are configured.

---

## Done criteria

This plan is complete only when:

- [x] `OrderRequest` / `OrderResult` / `OrderExecutor` contracts exist.
- [x] Dry-run executor uses the same path as future live orders.
- [x] Runtime live mode cannot run without explicit executor.
- [x] Runtime live/dry-run mode cannot run without risk limits.
- [x] Duplicate idempotency keys are skipped.
- [x] Audit JSONL records every attempt.
- [x] Reconciliation helper detects missing/unexpected exchange orders.
- [x] CLI exposes `--execution-mode` while defaulting to `paper`.
- [x] `dry_run` E2E test passes.
- [x] `live` remains fail-closed without credentials and operator setup.
- [x] Full relevant test suite passes.
- [x] Operator runbook documents the exact switch and rollback.

## Suggested commit sequence

1. `feat: add polymarket execution order contracts`
2. `feat: add dry-run polymarket executor`
3. `feat: route runtime execution through order executor`
4. `feat: add pre-trade execution risk gates`
5. `feat: add execution idempotency store`
6. `feat: add execution audit log`
7. `feat: add polymarket execution reconciliation helper`
8. `feat: add fail-closed clob rest executor seam`
9. `feat: expose execution mode in runtime cli`
10. `test: add live-ready dry-run runtime rehearsal`
11. `docs: add polymarket live-ready runbook`
