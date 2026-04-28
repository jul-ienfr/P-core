from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from weather_pm.orderbook_simulator import simulate_orderbook_fill
from weather_pm.paper_ledger import (
    PaperLedgerError,
    paper_ledger_place,
    paper_ledger_refresh,
    render_paper_ledger_markdown,
    write_paper_ledger_artifacts,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "orderbook_fill_parity.json"


def _parity_fixture():
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _candidate(**overrides):
    payload = {
        "surface_id": "seoul-2026-04-26-temp-c",
        "market_id": "mkt-seoul-20c-higher",
        "token_id": "tok-no-20c",
        "side": "NO",
        "strict_limit": 0.30,
        "spend_usdc": 5.0,
        "source_status": "source_confirmed",
        "station_status": "station_confirmed",
        "station": "RKSI",
        "account_consensus": {
            "classification": "true_multi_account_consensus",
            "unique_accounts": 4,
            "dominant_side": "NO",
        },
        "model_reason": "station observed below threshold",
        "inconsistency_reason": "threshold monotonicity violation",
        "orderbook": {"no_asks": [{"price": 0.28, "size": 100.0}]},
        "actual_refresh_price": 0.28,
    }
    payload.update(overrides)
    return payload


def test_weather_orderbook_normalization_accepts_supported_no_formats():
    from weather_pm.orderbook_simulator import normalize_orderbook_asks

    cases = [
        {"noAsks": [{"price": 0.31, "quantity": 2.0}, {"price": 0.29, "size": 3.0}]},
        {"no_ask_levels": [{"price": 0.31, "quantity": 2.0}, {"price": 0.29, "size": 3.0}]},
        {"NO": {"asks": [{"price": 0.31, "quantity": 2.0}, {"price": 0.29, "size": 3.0}]}},
        {"NO": {"ask_levels": [{"price": 0.31, "quantity": 2.0}, {"price": 0.29, "size": 3.0}]}},
    ]

    for orderbook in cases:
        assert normalize_orderbook_asks(orderbook, side="NO") == [
            {"price": 0.29, "size": 3.0},
            {"price": 0.31, "size": 2.0},
        ]


def test_weather_orderbook_normalization_accepts_supported_yes_formats():
    from weather_pm.orderbook_simulator import normalize_orderbook_asks

    cases = [
        {"yes_ask_levels": [{"price": 0.62, "quantity": 2.0}, {"price": 0.58, "size": 3.0}]},
        {"YES": {"asks": [{"price": 0.62, "quantity": 2.0}, {"price": 0.58, "size": 3.0}]}},
        {"YES": {"ask_levels": [{"price": 0.62, "quantity": 2.0}, {"price": 0.58, "size": 3.0}]}},
        {"asks": [{"price": 0.62, "quantity": 2.0}, {"price": 0.58, "size": 3.0}]},
    ]

    for orderbook in cases:
        assert normalize_orderbook_asks(orderbook, side="YES") == [
            {"price": 0.58, "size": 3.0},
            {"price": 0.62, "size": 2.0},
        ]


def test_weather_orderbook_normalization_does_not_use_top_level_asks_for_no_side():
    from weather_pm.orderbook_simulator import normalize_orderbook_asks

    assert normalize_orderbook_asks({"asks": [{"price": 0.31, "size": 2.0}]}, side="NO") == []


def test_weather_orderbook_bids_normalize_to_descending_rust_compatible_shape():
    from weather_pm.orderbook_simulator import normalize_orderbook_bids, rust_compatible_orderbook_payload

    orderbook = {
        "NO": {
            "asks": [{"price": 0.31, "quantity": 2.0}],
            "bid_levels": [{"price": 0.27, "quantity": 4.0}, {"price": 0.29, "size": 3.0}],
        }
    }

    assert normalize_orderbook_bids(orderbook, side="NO") == [
        {"price": 0.29, "size": 3.0},
        {"price": 0.27, "size": 4.0},
    ]
    assert rust_compatible_orderbook_payload(orderbook, side="NO") == {
        "bids": [{"price": 0.29, "quantity": 3.0}, {"price": 0.27, "quantity": 4.0}],
        "asks": [{"price": 0.31, "quantity": 2.0}],
    }


def test_weather_orderbook_bid_fallback_is_yes_only():
    from weather_pm.orderbook_simulator import normalize_orderbook_bids

    orderbook = {"bid_levels": [{"price": 0.59, "size": 2.0}]}

    assert normalize_orderbook_bids(orderbook, side="YES") == [{"price": 0.59, "size": 2.0}]
    assert normalize_orderbook_bids(orderbook, side="NO") == []


def test_weather_orderbook_normalization_ignores_invalid_levels():
    from weather_pm.orderbook_simulator import normalize_orderbook_asks

    assert normalize_orderbook_asks(
        {
            "no_asks": [
                {"price": 0.31, "size": 2.0},
                {"price": 0.0, "size": 2.0},
                {"price": 0.30, "size": 0.0},
                {"price": "bad", "size": 1.0},
            ]
        },
        side="NO",
    ) == [{"price": 0.31, "size": 2.0}]


def test_weather_paper_ledger_simulate_orderbook_fill_matches_parity_fixture():
    payload = _parity_fixture()

    result = simulate_orderbook_fill(
        payload["polymarket_orderbook"],
        side="NO",
        spend_usd=payload["requests"]["spend_usdc"],
        strict_limit=payload["requests"]["strict_limit"],
    )

    expected = dict(payload["expected"]["spend_fill"])
    expected.pop("filled_quantity")

    assert result == expected


def test_weather_paper_ledger_place_uses_parity_fixture_spend_fill():
    payload = _parity_fixture()
    expected = payload["expected"]["spend_fill"]
    expected_fill = dict(expected)
    expected_fill.pop("filled_quantity")

    ledger = paper_ledger_place(
        _candidate(
            orderbook=payload["polymarket_orderbook"],
            spend_usdc=payload["requests"]["spend_usdc"],
            strict_limit=payload["requests"]["strict_limit"],
            actual_refresh_price=expected["top_ask"],
        )
    )

    order = ledger["orders"][0]
    assert order["status"] == "filled"
    assert order["filled_usdc"] == expected["fillable_spend"]
    assert order["shares"] == pytest.approx(expected["fillable_spend"] / expected["avg_fill_price"], rel=1e-6)
    assert order["avg_fill_price"] == pytest.approx(expected["avg_fill_price"], rel=1e-6)
    assert order["simulated_fill"] == expected_fill
    assert order["unfilled_usdc"] == 0.0
    assert order["live_order_allowed"] is False
    assert order["order_type"] == "limit_only_paper"


def test_paper_ledger_place_records_limit_only_filled_entry_with_required_context():
    ledger = paper_ledger_place(_candidate())

    assert ledger["summary"]["orders"] == 1
    assert ledger["summary"]["status_counts"] == {"filled": 1}
    assert ledger["summary"]["paper_only"] is True
    assert ledger["summary"]["live_order_allowed"] is False
    order = ledger["orders"][0]
    assert order["paper_only"] is True
    assert order["live_order_allowed"] is False
    assert order["status"] == "filled"
    assert order["order_type"] == "limit_only_paper"
    assert order["surface_id"] == "seoul-2026-04-26-temp-c"
    assert order["market_id"] == "mkt-seoul-20c-higher"
    assert order["token_id"] == "tok-no-20c"
    assert order["side"] == "NO"
    assert order["strict_limit"] == 0.30
    assert order["actual_refresh_price"] == 0.28
    assert order["source_status"] == "source_confirmed"
    assert order["station_status"] == "station_confirmed"
    assert order["account_consensus"]["unique_accounts"] == 4
    assert order["model_reason"] == "station observed below threshold"
    assert order["inconsistency_reason"] == "threshold monotonicity violation"
    assert order["simulated_fill"]["fill_status"] == "filled"
    assert order["filled_usdc"] == 5.0
    assert order["shares"] == pytest.approx(17.857142, rel=1e-6)


def test_paper_ledger_place_charges_opening_slippage_and_marks_exit_cost_as_estimate():
    ledger = paper_ledger_place(
        _candidate(
            spend_usdc=10.0,
            orderbook={"no_asks": [{"price": 0.28, "size": 20.0}, {"price": 0.30, "size": 20.0}]},
            maker_base_fee=0.0,
            taker_base_fee=0.005,
            opening_fee_usdc=0.10,
            estimated_exit_fee_bps=40.0,
            estimated_exit_fee_usdc=0.20,
        )
    )

    order = ledger["orders"][0]
    assert order["filled_usdc"] == 10.0
    assert order["shares"] == pytest.approx(34.666611, rel=1e-6)
    assert order["avg_fill_price"] == pytest.approx(0.288462, rel=1e-6)
    assert order["opening_trading_fee_usdc"] == 0.05
    assert order["opening_fixed_fee_usdc"] == 0.1
    assert order["opening_fee_usdc"] == 0.15
    assert order["slippage_usdc"] == pytest.approx(0.293349, rel=1e-6)
    assert order["all_in_entry_cost_usdc"] == 10.15
    assert order["estimated_exit_fee_usdc"] == 0.24
    assert order["exit_cost_basis"] == "estimate_until_live_exit_book"
    assert order["realized_exit_fee_usdc"] is None
    assert order["pnl_usdc"] == -10.39
    assert order["net_pnl_after_all_costs"] == -10.39
    assert ledger["summary"]["opening_fee_usdc"] == 0.15
    assert ledger["summary"]["estimated_exit_fee_usdc"] == 0.24
    assert ledger["summary"]["net_pnl_after_all_costs"] == -10.39


def test_weather_paper_ledger_refresh_uses_parity_fixture_exit_orderbook():
    payload = _parity_fixture()
    ledger = paper_ledger_place(_candidate(orderbook=payload["polymarket_orderbook"]))
    order = ledger["orders"][0]
    order["shares"] = payload["requests"]["exit_quantity"]
    order["filled_usdc"] = 5.0
    order["all_in_entry_cost_usdc"] = 5.0
    order["estimated_exit_fee_bps"] = 0.0
    order["estimated_exit_fee_usdc"] = 0.0

    refreshed = paper_ledger_refresh(
        {"orders": [order]},
        refreshes={
            "tok-no-20c": {
                "best_bid": payload["polymarket_orderbook"]["no_bids"][0]["price"],
                "exit_orderbook": {"no_bids": payload["polymarket_orderbook"]["no_bids"]},
            }
        },
    )

    refreshed_order = refreshed["orders"][0]
    expected = payload["expected"]["exit_value"]
    assert refreshed_order["exit_cost_basis"] == "live_bid_book"
    assert refreshed_order["paper_exit_value_usdc"] == pytest.approx(expected["value"], rel=1e-6)
    assert refreshed_order["mtm_usdc"] == pytest.approx(expected["value"], rel=1e-6)
    assert refreshed_order["realized_exit_fee_usdc"] == 0.0
    assert refreshed_order["pnl_usdc"] == pytest.approx(expected["value"] - 5.0, rel=1e-6)


def test_paper_ledger_refresh_uses_live_bid_book_for_real_paper_exit_costs():
    ledger = paper_ledger_place(
        _candidate(
            spend_usdc=5.0,
            maker_base_fee=0.0,
            taker_base_fee=0.005,
            opening_fee_usdc=0.10,
            estimated_exit_fee_bps=40.0,
            estimated_exit_fee_usdc=0.20,
        )
    )

    refreshed = paper_ledger_refresh(
        ledger,
        refreshes={
            "tok-no-20c": {
                "best_bid": 0.43,
                "exit_orderbook": {"no_bids": [{"price": 0.43, "size": 7.85715}, {"price": 0.41, "size": 20.0}]},
            }
        },
    )

    order = refreshed["orders"][0]
    assert order["exit_cost_basis"] == "live_bid_book"
    assert order["paper_exit_value_usdc"] == pytest.approx(7.478571, rel=1e-6)
    assert order["realized_exit_fee_usdc"] == pytest.approx(0.029914, rel=1e-6)
    assert order["pnl_usdc"] == pytest.approx(2.323657, rel=1e-6)
    assert order["net_pnl_after_all_costs"] == pytest.approx(2.323657, rel=1e-6)
    assert refreshed["summary"]["realized_exit_fee_usdc"] == pytest.approx(0.029914, rel=1e-6)


def test_paper_ledger_place_records_planned_when_no_spend_is_requested():
    ledger = paper_ledger_place(_candidate(spend_usdc=0.0))

    order = ledger["orders"][0]
    assert order["paper_only"] is True
    assert order["live_order_allowed"] is False
    assert order["status"] == "planned"
    assert order["operator_action"] == "PENDING_LIMIT"
    assert ledger["summary"]["status_counts"] == {"planned": 1}


def test_paper_ledger_place_records_partial_fill_but_still_never_market_buys():
    ledger = paper_ledger_place(_candidate(orderbook={"no_asks": [{"price": 0.28, "size": 5.0}]}))

    order = ledger["orders"][0]
    assert order["paper_only"] is True
    assert order["live_order_allowed"] is False
    assert order["status"] == "partial"
    assert order["filled_usdc"] == 1.4
    assert order["unfilled_usdc"] == 3.6
    assert order["simulated_fill"]["execution_blocker"] == "insufficient_executable_depth"
    assert order["live_order_allowed"] is False


def test_paper_ledger_place_skips_when_price_moved_above_strict_limit():
    ledger = paper_ledger_place(_candidate(actual_refresh_price=0.34, orderbook={"no_asks": [{"price": 0.34, "size": 100.0}]}))

    order = ledger["orders"][0]
    assert order["paper_only"] is True
    assert order["live_order_allowed"] is False
    assert order["status"] == "skipped_price_moved"
    assert order["filled_usdc"] == 0.0
    assert order["operator_action"] == "NO_ADD_PRICE_MOVED"
    assert order["simulated_fill"]["execution_blocker"] == "strict_limit_price_exceeded"


def test_paper_ledger_place_enforces_no_market_buy_for_missing_book():
    with pytest.raises(PaperLedgerError, match="paper ledger requires a refresh orderbook"):
        paper_ledger_place(_candidate(orderbook=None, actual_refresh_price=None))


def test_paper_ledger_refresh_updates_mtm_pnl_and_operator_actions():
    ledger = paper_ledger_place(_candidate(spend_usdc=5.0))
    refreshed = paper_ledger_refresh(
        ledger,
        refreshes={
            "tok-no-20c": {
                "source_status": "source_confirmed",
                "station_status": "station_confirmed",
                "actual_refresh_price": 0.44,
                "best_bid": 0.43,
                "orderbook": {"no_asks": [{"price": 0.31, "size": 100.0}]},
            }
        },
        max_position_usdc=5.0,
    )

    order = refreshed["orders"][0]
    assert order["operator_action"] == "TAKE_PROFIT_REVIEW_PAPER"
    assert order["exit_policy"]["action"] == "HOLD"
    assert order["exit_policy"]["reason"] == "no_exit_trigger"
    assert order["status"] == "filled"
    assert order["actual_refresh_price"] == 0.44
    assert order["mtm_usdc"] == pytest.approx(7.678571, rel=1e-6)
    assert order["pnl_usdc"] == pytest.approx(2.678571, rel=1e-6)
    assert refreshed["summary"]["action_counts"] == {"TAKE_PROFIT_REVIEW_PAPER": 1}


def test_paper_ledger_refresh_emits_pending_red_flag_no_add_and_hold_capped_actions():
    ledger = {
        "orders": [
            paper_ledger_place(_candidate(token_id="filled-a", market_id="m1", actual_refresh_price=0.29))["orders"][0],
            paper_ledger_place(_candidate(token_id="filled-b", market_id="m2", spend_usdc=10.0))["orders"][0],
            paper_ledger_place(_candidate(token_id="partial-c", market_id="m3", orderbook={"no_asks": [{"price": 0.28, "size": 5.0}]}))["orders"][0],
            paper_ledger_place(_candidate(token_id="skip-d", market_id="m4", actual_refresh_price=0.35, orderbook={"no_asks": [{"price": 0.35, "size": 100.0}]}))["orders"][0],
        ]
    }

    refreshed = paper_ledger_refresh(
        ledger,
        refreshes={
            "filled-a": {"source_status": "source_missing", "station_status": "station_missing", "actual_refresh_price": 0.27, "best_bid": 0.26},
            "filled-b": {"source_status": "source_confirmed", "station_status": "station_confirmed", "actual_refresh_price": 0.29, "best_bid": 0.28},
            "partial-c": {"source_status": "source_confirmed", "station_status": "station_confirmed", "actual_refresh_price": 0.29, "best_bid": 0.28},
            "skip-d": {"source_status": "source_confirmed", "station_status": "station_confirmed", "actual_refresh_price": 0.36, "best_bid": 0.35},
        },
        max_position_usdc=5.0,
    )

    actions = {order["token_id"]: order["operator_action"] for order in refreshed["orders"]}
    assert actions == {
        "filled-a": "RED_FLAG_RECHECK_SOURCE",
        "filled-b": "HOLD_CAPPED",
        "partial-c": "PENDING_LIMIT",
        "skip-d": "NO_ADD_PRICE_MOVED",
    }


def test_paper_ledger_refresh_applies_settlement_win_and_loss():
    ledger = {"orders": [paper_ledger_place(_candidate(token_id="win"))["orders"][0], paper_ledger_place(_candidate(token_id="loss", market_id="m2"))["orders"][0]]}

    refreshed = paper_ledger_refresh(ledger, settlements={"win": "win", "loss": "loss"})

    by_token = {order["token_id"]: order for order in refreshed["orders"]}
    assert by_token["win"]["status"] == "settled_win"
    assert by_token["win"]["pnl_usdc"] == pytest.approx(12.857142, rel=1e-6)
    assert by_token["loss"]["status"] == "settled_loss"
    assert by_token["loss"]["pnl_usdc"] == -5.0


def test_paper_ledger_artifacts_write_json_csv_and_markdown_under_polymarket_dir(tmp_path: Path):
    ledger = paper_ledger_place(_candidate())
    result = write_paper_ledger_artifacts(ledger, output_dir=tmp_path / "data" / "polymarket")

    assert Path(result["artifacts"]["json"]).exists()
    assert Path(result["artifacts"]["csv"]).exists()
    markdown = Path(result["artifacts"]["markdown"]).read_text(encoding="utf-8")
    assert "# Polymarket weather paper ledger" in markdown
    assert "mkt-seoul-20c-higher" in markdown
    assert render_paper_ledger_markdown(ledger).startswith("# Polymarket weather paper ledger")


def _run_weather_pm(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT / "src")
    return subprocess.run(
        [sys.executable, "-m", "weather_pm.cli", *args],
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
        env=env,
        check=False,
    )


def test_paper_ledger_cli_place_refresh_and_report(tmp_path: Path):
    candidate_path = tmp_path / "candidate.json"
    ledger_path = tmp_path / "paper_ledger.json"
    refresh_path = tmp_path / "refresh.json"
    out_dir = tmp_path / "data" / "polymarket"
    candidate_path.write_text(json.dumps(_candidate()), encoding="utf-8")

    placed = _run_weather_pm(
        "paper-ledger-place",
        "--candidate-json",
        str(candidate_path),
        "--ledger-json",
        str(ledger_path),
        "--output-dir",
        str(out_dir),
    )
    assert placed.returncode == 0, placed.stderr
    placed_payload = json.loads(placed.stdout)
    assert placed_payload["summary"]["status_counts"] == {"filled": 1}
    assert ledger_path.exists()

    refresh_path.write_text(json.dumps({"refreshes": {"tok-no-20c": {"actual_refresh_price": 0.44, "best_bid": 0.43, "source_status": "source_confirmed", "station_status": "station_confirmed"}}}), encoding="utf-8")
    refreshed = _run_weather_pm(
        "paper-ledger-refresh",
        "--ledger-json",
        str(ledger_path),
        "--refresh-json",
        str(refresh_path),
        "--output-dir",
        str(out_dir),
    )
    assert refreshed.returncode == 0, refreshed.stderr
    refreshed_payload = json.loads(refreshed.stdout)
    assert refreshed_payload["summary"]["action_counts"] == {"TAKE_PROFIT_REVIEW_PAPER": 1}

    reported = _run_weather_pm("paper-ledger-report", "--ledger-json", str(ledger_path), "--output-dir", str(out_dir))
    assert reported.returncode == 0, reported.stderr
    report_payload = json.loads(reported.stdout)
    assert Path(report_payload["artifacts"]["json"]).exists()
    assert Path(report_payload["artifacts"]["csv"]).exists()
    assert Path(report_payload["artifacts"]["markdown"]).exists()
