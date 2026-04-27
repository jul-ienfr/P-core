from __future__ import annotations

import json
from pathlib import Path

from weather_pm.production_operator import (
    build_live_readiness_checks,
    build_production_weather_report,
    write_production_weather_report_artifacts,
)

FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "polymarket_weather_city_date_surface.json"


def _surface() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _paper_ledger() -> dict:
    return {
        "orders": [
            {
                "order_id": "paper-1",
                "market_id": "chicago-high-72f-or-higher-20260430",
                "token_id": "yes-token",
                "side": "YES",
                "status": "filled",
                "operator_action": "HOLD",
                "filled_usdc": 5.0,
                "mtm_usdc": 5.5,
                "pnl_usdc": 0.5,
                "source_status": "source_confirmed",
                "station_status": "station_confirmed",
            }
        ]
    }


def _backtest() -> dict:
    return {
        "schema_version": 1,
        "summary": {
            "replayed_trade_count": 4,
            "fillability": 0.82,
            "pnl_usdc": 3.4,
            "max_drawdown_usdc": 1.0,
        },
    }


def test_live_readiness_refuses_without_explicit_live_mode_even_when_other_gates_pass() -> None:
    report = build_production_weather_report(_surface(), paper_ledger=_paper_ledger(), backtest_report=_backtest(), live_mode_enabled=False)

    checks = report["live_readiness"]

    assert checks["ready"] is False
    assert checks["status"] == "refuse_live_execution"
    assert checks["checks"]["source_confirmed"]["pass"] is True
    assert checks["checks"]["book_fresh"]["pass"] is True
    assert checks["checks"]["paper_ledger_healthy"]["pass"] is True
    assert checks["checks"]["backtest_replay_available"]["pass"] is True
    assert checks["checks"]["risk_caps_satisfied"]["pass"] is True
    assert checks["checks"]["explicit_live_mode_enabled"]["pass"] is False
    assert "explicit_live_mode_enabled" in checks["blockers"]


def test_live_readiness_lists_all_blockers_for_unsafe_report() -> None:
    unsafe_surface = _surface()
    unsafe_surface["source"]["status"] = "source_missing"
    unsafe_surface["markets"][0]["orderbook"] = {}
    bad_ledger = {"orders": [{"status": "filled", "operator_action": "RED_FLAG_RECHECK_SOURCE", "filled_usdc": 4}]}

    checks = build_live_readiness_checks(
        source_confirmed=False,
        book_fresh=False,
        paper_ledger=bad_ledger,
        backtest_report=None,
        risk_caps_satisfied=False,
        explicit_live_mode_enabled=True,
    )

    assert checks["ready"] is False
    assert checks["status"] == "refuse_live_execution"
    assert checks["blockers"] == [
        "source_confirmed",
        "book_fresh",
        "paper_ledger_healthy",
        "backtest_replay_available",
        "risk_caps_satisfied",
    ]


def test_production_weather_report_chains_layers_candidates_blockers_and_actions() -> None:
    report = build_production_weather_report(_surface(), paper_ledger=_paper_ledger(), backtest_report=_backtest(), observed_value=73.0)

    assert list(report) == [
        "schema_version",
        "report_type",
        "summary",
        "production_layers",
        "top_current_candidates",
        "blockers",
        "strict_next_actions",
        "live_readiness",
        "components",
        "artifacts",
    ]
    assert report["report_type"] == "polymarket_weather_production_operator"
    layers = {row["layer"]: row["status"] for row in report["production_layers"]}
    assert layers["source_first_event_surface"] == "implemented"
    assert layers["cross_market_inconsistency_engine"] == "implemented"
    assert layers["orderbook_strict_limit_simulation"] == "implemented"
    assert layers["guarded_live_execution"] == "guarded"
    assert layers["real_money_live_execution"] == "missing"
    assert report["summary"]["implemented_layers"] >= 8
    assert report["summary"]["missing_layers"] >= 1
    assert report["top_current_candidates"]
    top = report["top_current_candidates"][0]
    assert {"market_id", "candidate_side", "source_status", "execution", "threshold_watch", "portfolio_risk", "strict_next_action"}.issubset(top)
    assert top["live_order_allowed"] is False
    assert "enable live mode only after explicit operator approval" in report["strict_next_actions"]


def test_production_weather_report_artifacts_have_stable_json_and_markdown(tmp_path: Path) -> None:
    artifact = write_production_weather_report_artifacts(
        _surface(),
        output_dir=tmp_path,
        paper_ledger=_paper_ledger(),
        backtest_report=_backtest(),
        observed_value=73.0,
    )

    json_path = Path(artifact["json_path"])
    md_path = Path(artifact["md_path"])
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    markdown = md_path.read_text(encoding="utf-8")

    assert json_path.name == "weather_production_operator_report_latest.json"
    assert md_path.name == "weather_production_operator_report_latest.md"
    assert payload["artifacts"]["json_path"] == str(json_path)
    assert payload["artifacts"]["md_path"] == str(md_path)
    assert "# Polymarket Weather Production Operator Report" in markdown
    assert "## Implemented vs Missing Production Layers" in markdown
    assert "## Guarded Live Readiness" in markdown
    assert artifact["summary"] == payload["summary"]
