from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from panoptique.paper_strategies import (
    PaperStrategyConfig,
    PaperStrategyInput,
    decide_paper_strategy,
    render_paper_strategy_report,
    run_paper_strategy_fixture,
)
from prediction_core.execution import BookLevel, OrderBookSnapshot


BASE = datetime(2026, 4, 26, 12, 0, tzinfo=UTC)


def book(*, bid: float = 0.48, ask: float = 0.50, bid_qty: float = 200.0, ask_qty: float = 200.0) -> OrderBookSnapshot:
    return OrderBookSnapshot(
        bids=[BookLevel(price=bid, quantity=bid_qty)],
        asks=[BookLevel(price=ask, quantity=ask_qty)],
        timestamp=BASE,
        venue="fixture",
    )


def strategy_input(
    *,
    direction: str = "up",
    confidence: float = 0.82,
    expected_move: float = 0.08,
    observed_move: float = 0.0,
    order_book: OrderBookSnapshot | None = None,
) -> PaperStrategyInput:
    return PaperStrategyInput(
        observation_id="obs-1",
        prediction_id="pred-1",
        market_id="m1",
        observed_at=BASE,
        predicted_crowd_direction=direction,
        confidence=confidence,
        expected_crowd_move=expected_move,
        observed_crowd_move=observed_move,
        book=order_book or book(),
    )


def test_front_run_fade_and_skip_decision_boundaries() -> None:
    config = PaperStrategyConfig(min_confidence=0.70, min_expected_move=0.03, min_net_edge=0.01)

    front_run = decide_paper_strategy(strategy_input(), config=config)
    assert front_run.mode == "front_run_paper"
    assert front_run.paper_side == "buy"
    assert front_run.status == "paper_candidate"
    assert front_run.friction_assumptions["liquidity_role"] == "taker"
    assert front_run.cost_breakdown is not None
    assert front_run.net_edge_after_costs > 0.0

    fade = decide_paper_strategy(
        strategy_input(confidence=0.58, expected_move=0.0, observed_move=0.07),
        config=config,
    )
    assert fade.mode == "fade_paper"
    assert fade.paper_side == "sell"
    assert fade.status == "paper_candidate"

    low_signal = decide_paper_strategy(strategy_input(confidence=0.40, expected_move=0.01), config=config)
    assert low_signal.mode == "skip"
    assert low_signal.status == "skip"
    assert low_signal.cost_breakdown is not None
    assert any("confidence" in reason or "expected crowd move" in reason for reason in low_signal.reasons)


def test_strategies_reject_bad_depth_and_bad_spread() -> None:
    config = PaperStrategyConfig(max_spread=0.06, paper_quantity=50.0, min_fill_ratio=0.80)

    shallow = decide_paper_strategy(strategy_input(order_book=book(ask_qty=10.0)), config=config)
    assert shallow.mode == "skip"
    assert shallow.status == "skip"
    assert any("depth" in reason for reason in shallow.reasons)

    wide = decide_paper_strategy(strategy_input(order_book=book(bid=0.40, ask=0.55)), config=config)
    assert wide.mode == "skip"
    assert wide.status == "skip"
    assert any("spread" in reason for reason in wide.reasons)
    assert wide.cost_breakdown is not None
    assert wide.friction_assumptions["max_spread"] == 0.06


def test_report_uses_research_language_and_friction_for_every_candidate() -> None:
    decisions = [
        decide_paper_strategy(strategy_input(), config=PaperStrategyConfig()),
        decide_paper_strategy(strategy_input(confidence=0.3, expected_move=0.0), config=PaperStrategyConfig()),
    ]

    report = render_paper_strategy_report(decisions, status="ok", artifact_path=Path("artifact.jsonl"), out_of_sample_fraction=0.5)
    lowered = report.lower()
    assert "paper-only research" in lowered
    assert "no real orders" in lowered
    assert "profit" not in lowered
    assert "predicted crowd move" in lowered
    assert "simulated entry/exit assumptions" in lowered
    assert "failure modes" in lowered
    assert "friction assumptions" in lowered

    for decision in decisions:
        payload = decision.to_dict()
        assert payload["friction_assumptions"]
        if decision.mode != "skip":
            assert payload["cost_breakdown"] is not None


def test_run_paper_strategy_fixture_writes_artifacts_and_supports_oos_split(tmp_path: Path) -> None:
    fixture_path = tmp_path / "signals.jsonl"
    rows = [
        {
            "observation_id": "obs-1",
            "prediction_id": "pred-1",
            "market_id": "m1",
            "observed_at": BASE.isoformat(),
            "predicted_crowd_direction": "up",
            "confidence": 0.82,
            "expected_crowd_move": 0.08,
            "observed_crowd_move": 0.0,
            "book": {"bids": [{"price": 0.48, "quantity": 200.0}], "asks": [{"price": 0.50, "quantity": 200.0}]},
        },
        {
            "observation_id": "obs-2",
            "prediction_id": "pred-2",
            "market_id": "m2",
            "observed_at": BASE.isoformat(),
            "predicted_crowd_direction": "down",
            "confidence": 0.90,
            "expected_crowd_move": -0.07,
            "observed_crowd_move": 0.0,
            "book": {"bids": [{"price": 0.47, "quantity": 200.0}], "asks": [{"price": 0.49, "quantity": 200.0}]},
        },
    ]
    fixture_path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")

    result = run_paper_strategy_fixture(fixture_path=fixture_path, output_dir=tmp_path / "out", out_of_sample_fraction=0.5)

    assert result.status == "ok"
    assert result.count == 2
    assert result.db_status == "skipped_unavailable"
    assert result.artifact_path.parent.name == "out"
    artifact_rows = [json.loads(line) for line in result.artifact_path.read_text(encoding="utf-8").splitlines()]
    assert {row["decision"]["split"] for row in artifact_rows} == {"train", "out_of_sample"}
    assert all(row["decision"]["paper_only"] is True for row in artifact_rows)
    assert "No real orders" in result.report_path.read_text(encoding="utf-8")


def test_run_paper_strategy_fixture_skips_when_insufficient_data(tmp_path: Path) -> None:
    missing = tmp_path / "missing.jsonl"

    result = run_paper_strategy_fixture(fixture_path=missing, output_dir=tmp_path / "out")

    assert result.status == "not_enough_data"
    assert result.count == 0
    rows = [json.loads(line) for line in result.artifact_path.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["metadata"]["status"] == "not_enough_data"
    assert rows[0]["metadata"]["paper_only"] is True
