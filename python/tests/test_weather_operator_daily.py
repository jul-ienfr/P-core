from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "weather_operator_daily.py"
_SPEC = importlib.util.spec_from_file_location("weather_operator_daily", SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
weather_operator_daily = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(weather_operator_daily)


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_latest_shadow_skip_diagnostics_ignores_unsafe_payloads(tmp_path: Path) -> None:
    safe_old = _write_json(
        tmp_path / "old" / "shadow_profile_skip_diagnostics_old.json",
        {
            "paper_only": True,
            "live_order_allowed": False,
            "summary": {"skipped": 1, "paper_only": True, "live_order_allowed": False},
        },
    )
    unsafe_new = _write_json(
        tmp_path / "new" / "shadow_profile_skip_diagnostics_new.json",
        {
            "paper_only": True,
            "live_order_allowed": True,
            "summary": {"skipped": 99, "paper_only": True, "live_order_allowed": True},
        },
    )
    safe_old.touch()
    unsafe_new.touch()

    selected = weather_operator_daily.latest_shadow_skip_diagnostics(tmp_path)

    assert selected is not None
    assert selected["summary"]["skipped"] == 1
    assert selected["artifacts"]["shadow_skip_diagnostics_json"] == str(safe_old)
    assert selected["paper_only"] is True
    assert selected["live_order_allowed"] is False



def test_render_daily_markdown_exposes_actionable_only_summary(tmp_path: Path) -> None:
    refresh = _write_json(tmp_path / "refresh.json", {"paper_only": True, "live_order_allowed": False})
    monitor = _write_json(tmp_path / "monitor.json", {"paper_only": True, "live_order_allowed": False})
    watchlist_md = tmp_path / "watchlist.md"
    watchlist_md.write_text("# watchlist\n", encoding="utf-8")
    daily_json = tmp_path / "daily.json"
    account_summary = _write_json(
        tmp_path / "account_summary.json",
        {
            "paper_only": True,
            "live_order_allowed": False,
            "daily_operator_rollup": {
                "live_ready": False,
                "live_ready_count": 0,
                "watchlist_count": 8,
                "global_recommendation": "paper_micro_only",
                "normal_size_blocked_count": 8,
                "not_ready_reason_counts": {"missing_tradeable_quote": 5, "insufficient_depth": 8},
            },
            "daily_operator_markdown": "- no ready markets",
            "shadow_skip_diagnostics": {
                "paper_only": True,
                "live_order_allowed": False,
                "summary": {"paper_orders": 0, "skipped": 9, "skip_reasons": {"account_no_trade_label": 9}, "unlock_reasons": {"wait_for_target_account_trade_or_promote_signal_only": 9}},
                "market_unlocks": [{"market_id": "m-cpr-1"}, {"market_id": "m-cpr-2"}, {"market_id": "m-cpr-3"}],
            },
        },
    )
    paper_watchlist = _write_json(
        tmp_path / "watchlist.json",
        {
            "paper_only": True,
            "live_order_allowed": False,
            "summary": {"positions": 2, "total_spend": 15, "total_ev_now": 3, "action_counts": {"HOLD_MONITOR": 1, "ADD": 1}},
            "watchlist": [
                {"city": "Munich", "operator_action": "HOLD_MONITOR", "paper_ev_now_usdc": 1.0},
                {"city": "Dallas", "operator_action": "ADD", "add_allowed": True, "max_add_usdc": 5, "paper_ev_now_usdc": 2.0},
            ],
        },
    )

    markdown = weather_operator_daily.render_daily_markdown(
        stamp="20260430T120000Z",
        refresh_path=refresh,
        account_summary_path=account_summary,
        paper_monitor_path=monitor,
        paper_watchlist_path=paper_watchlist,
        paper_watchlist_md=watchlist_md,
        daily_json_path=daily_json,
    )

    assert "## Actionable-only" in markdown
    assert "- ACTIONABLE_NOW: 1" in markdown
    assert "- MONITOR_EXISTING: 1" in markdown
    assert "- WAIT_FOR_QUOTE_OR_DEPTH: 8" in markdown
    assert "- CPR_SIGNAL_ONLY: 3 markets / 9 skips" in markdown
    assert "Dallas" in markdown
    assert "Munich" in markdown



def test_render_daily_markdown_explains_why_markets_are_not_actionable(tmp_path: Path) -> None:
    refresh = _write_json(tmp_path / "refresh.json", {"paper_only": True, "live_order_allowed": False})
    monitor = _write_json(tmp_path / "monitor.json", {"paper_only": True, "live_order_allowed": False})
    watchlist_md = tmp_path / "watchlist.md"
    watchlist_md.write_text("# watchlist\n", encoding="utf-8")
    daily_json = tmp_path / "daily.json"
    account_summary = _write_json(
        tmp_path / "account_summary.json",
        {
            "paper_only": True,
            "live_order_allowed": False,
            "daily_operator_rollup": {
                "live_ready": False,
                "live_ready_count": 0,
                "watchlist_count": 2,
                "global_recommendation": "paper_micro_only",
                "normal_size_blocked_count": 2,
                "not_ready_reason_counts": {"missing_tradeable_quote": 1, "insufficient_depth": 2},
            },
            "daily_operator_markdown": "- no ready markets",
        },
    )
    paper_watchlist = _write_json(
        tmp_path / "watchlist.json",
        {
            "paper_only": True,
            "live_order_allowed": False,
            "summary": {"positions": 0, "total_spend": 0, "total_ev_now": 0, "action_counts": {}},
            "watchlist": [
                {
                    "market_id": "2065018",
                    "city": "Hong Kong",
                    "temp": 23,
                    "unit": "C",
                    "side": "NO",
                    "normal_size_gate": {
                        "live_ready": False,
                        "reasons": ["extreme_quote", "insufficient_depth", "official_resolution_unavailable"],
                        "verdict": "paper_strict_limit_only",
                    },
                },
                {
                    "market_id": "2074350",
                    "city": "Dallas",
                    "temp": 35,
                    "unit": "C",
                    "side": "YES",
                    "normal_size_gate": {
                        "live_ready": False,
                        "reasons": ["missing_tradeable_quote", "insufficient_depth"],
                        "verdict": "paper_strict_limit_only",
                    },
                },
            ],
        },
    )

    markdown = weather_operator_daily.render_daily_markdown(
        stamp="20260430T120000Z",
        refresh_path=refresh,
        account_summary_path=account_summary,
        paper_monitor_path=monitor,
        paper_watchlist_path=paper_watchlist,
        paper_watchlist_md=watchlist_md,
        daily_json_path=daily_json,
    )

    assert "### Why not actionable" in markdown
    assert "2065018" in markdown
    assert "Hong Kong 23C NO" in markdown
    assert "extreme_quote, insufficient_depth, official_resolution_unavailable" in markdown
    assert "2074350" in markdown
    assert "Dallas 35C YES" in markdown
    assert "missing_tradeable_quote, insufficient_depth" in markdown
    assert "paper_strict_limit_only" in markdown



def test_render_daily_markdown_includes_shadow_skip_diagnostics(tmp_path: Path) -> None:
    refresh = _write_json(tmp_path / "refresh.json", {"paper_only": True, "live_order_allowed": False})
    monitor = _write_json(tmp_path / "monitor.json", {"paper_only": True, "live_order_allowed": False})
    watchlist_md = tmp_path / "watchlist.md"
    watchlist_md.write_text("# watchlist\n", encoding="utf-8")
    daily_json = tmp_path / "daily.json"
    account_summary = _write_json(
        tmp_path / "account_summary.json",
        {
            "paper_only": True,
            "live_order_allowed": False,
            "daily_operator_rollup": {
                "live_ready": False,
                "live_ready_count": 0,
                "watchlist_count": 3,
                "global_recommendation": "watch_only",
                "normal_size_blocked_count": 3,
                "not_ready_reason_counts": {"account_no_trade_label": 9},
            },
            "daily_operator_markdown": "- no ready markets",
            "shadow_skip_diagnostics": {
                "paper_only": True,
                "live_order_allowed": False,
                "summary": {
                    "paper_orders": 0,
                    "skipped": 9,
                    "skip_reasons": {"account_no_trade_label": 9},
                    "unlock_reasons": {"wait_for_target_account_trade_or_promote_signal_only": 9},
                    "paper_only": True,
                    "live_order_allowed": False,
                },
                "market_unlocks": [
                    {
                        "market_id": "m-kuala-26",
                        "question": "Will Kuala Lumpur be 26°C or below?",
                        "city": "Kuala Lumpur",
                        "handles": ["ColdMath", "Poligarch"],
                        "skipped": 2,
                        "unlock_condition": "wait_for_target_account_trade_or_promote_signal_only",
                        "operator_action": "Keep CPR as signal-only until one target account actually trades this market; do not synthesize a copy-trade paper order from abstention.",
                        "paper_only": True,
                        "live_order_allowed": False,
                    }
                ],
                "operator_next_actions": ["treat_all_no_trade_cpr_replay_as_signal_only_not_orderable"],
            },
        },
    )
    paper_watchlist = _write_json(
        tmp_path / "watchlist.json",
        {"paper_only": True, "live_order_allowed": False, "summary": {"positions": 0, "total_spend": 0, "total_ev_now": 0, "action_counts": {}}},
    )

    markdown = weather_operator_daily.render_daily_markdown(
        stamp="20260430T120000Z",
        refresh_path=refresh,
        account_summary_path=account_summary,
        paper_monitor_path=monitor,
        paper_watchlist_path=paper_watchlist,
        paper_watchlist_md=watchlist_md,
        daily_json_path=daily_json,
    )

    assert "## Diagnostics replay CPR" in markdown
    assert "Paper orders: 0" in markdown
    assert "Skipped: 9" in markdown
    assert "account_no_trade_label" in markdown
    assert "wait_for_target_account_trade_or_promote_signal_only" in markdown
    assert "m-kuala-26" in markdown
    assert "ColdMath, Poligarch" in markdown
    assert "signal-only" in markdown
    assert "live_order_allowed=false" in markdown
