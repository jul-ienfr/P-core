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



def test_latest_safe_learning_cycle_ignores_newer_unsafe_nested_live_payload(tmp_path: Path) -> None:
    safe_old = _write_json(
        tmp_path / "learning-cycles" / "20260430T010000Z" / "learning_cycle_result.json",
        {
            "ok": True,
            "paper_only": True,
            "live_order_allowed": False,
            "no_real_order_placed": True,
            "summary": {"policy_count": 1, "backfill_count": 2},
            "policy": {"actions": [{"policy_action": "request_resolution_backfill", "live_order_allowed": False}]},
        },
    )
    unsafe_new = _write_json(
        tmp_path / "learning-cycles" / "20260430T020000Z" / "learning_cycle_result.json",
        {
            "ok": True,
            "paper_only": True,
            "live_order_allowed": False,
            "no_real_order_placed": True,
            "summary": {"policy_count": 99, "backfill_count": 99},
            "policy": {"actions": [{"policy_action": "place_live_order", "live_order_allowed": True}]},
        },
    )
    safe_old.touch()
    unsafe_new.touch()

    selected = weather_operator_daily.latest_safe_learning_cycle(tmp_path)

    assert selected is not None
    path, payload = selected
    assert path == safe_old
    assert payload["summary"]["policy_count"] == 1
    assert payload["paper_only"] is True
    assert payload["live_order_allowed"] is False



def test_render_learning_cycle_markdown_summarizes_safe_cycle() -> None:
    markdown = weather_operator_daily.render_learning_cycle_markdown(
        {
            "ok": True,
            "paper_only": True,
            "live_order_allowed": False,
            "no_real_order_placed": True,
            "contract": {"run_id": "cycle-20260430"},
            "summary": {"policy_count": 2, "backfill_count": 1},
            "policy": {
                "actions": [
                    {"profile_id": "coldmath", "policy_action": "request_resolution_backfill", "reason": "thin sample"},
                    {"profile_id": "railbird", "policy_action": "reduce_or_disable_shadow_profile", "reason": "negative ROI"},
                ]
            },
            "backfill_plan": {"cases": [{"market_id": "m-threshold", "information_score": 87.5, "hypothesis": "near threshold"}]},
        }
    )

    assert "## Automatic learning cycle" in markdown
    assert "cycle-20260430" in markdown
    assert "paper_only=true" in markdown
    assert "live_order_allowed=false" in markdown
    assert "- Policy actions: 2" in markdown
    assert "- Backfill cases: 1" in markdown
    assert "coldmath" in markdown
    assert "m-threshold" in markdown



def test_render_daily_markdown_includes_learning_cycle_summary(tmp_path: Path) -> None:
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
            "daily_operator_rollup": {"live_ready": False, "live_ready_count": 0, "watchlist_count": 0, "global_recommendation": "watch_only"},
            "daily_operator_markdown": "- no ready markets",
        },
    )
    paper_watchlist = _write_json(
        tmp_path / "watchlist.json",
        {"paper_only": True, "live_order_allowed": False, "summary": {"positions": 0, "total_spend": 0, "total_ev_now": 0, "action_counts": {}}, "watchlist": []},
    )

    markdown = weather_operator_daily.render_daily_markdown(
        stamp="20260430T120000Z",
        refresh_path=refresh,
        account_summary_path=account_summary,
        paper_monitor_path=monitor,
        paper_watchlist_path=paper_watchlist,
        paper_watchlist_md=watchlist_md,
        daily_json_path=daily_json,
        learning_cycle={
            "paper_only": True,
            "live_order_allowed": False,
            "no_real_order_placed": True,
            "contract": {"run_id": "daily-cycle"},
            "summary": {"policy_count": 1, "backfill_count": 1},
            "policy": {"actions": [{"profile_id": "coldmath", "policy_action": "request_resolution_backfill"}]},
            "backfill_plan": {"cases": [{"market_id": "m1", "information_score": 42}]},
        },
    )

    assert "## Automatic learning cycle" in markdown
    assert "daily-cycle" in markdown
    assert "paper_only=true" in markdown
    assert "live_order_allowed=false" in markdown



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
            "live_watchlist": [
                {
                    "market_id": "2074350",
                    "city": "Dallas",
                    "temp": 35,
                    "unit": "C",
                    "side": "YES",
                    "normal_size_gate": {
                        "live_ready": False,
                        "reasons": ["missing_tradeable_quote", "insufficient_depth"],
                        "recommended_action": "paper_strict_limit_only",
                    },
                    "execution_snapshot": {
                        "best_bid_yes": 0.0,
                        "best_ask_yes": 0.001,
                        "best_bid_no": 0.999,
                        "best_ask_no": 1.0,
                        "yes_bid_depth_usd": 0.0,
                        "yes_ask_depth_usd": 0.0,
                    },
                },
            ],
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
    assert "quote=yes bid 0.0000 / ask 0.0010; no bid 0.9990 / ask 1.0000; depth=yes bid $0.00 / ask $0.00" in markdown



def test_render_daily_markdown_exposes_operator_buckets_and_source_diagnostics(tmp_path: Path) -> None:
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
                "live_ready_count": 1,
                "watchlist_count": 4,
                "global_recommendation": "paper_micro_only",
                "normal_size_blocked_count": 3,
                "not_ready_reason_counts": {
                    "official_resolution_unavailable": 2,
                    "missing_tradeable_quote": 1,
                    "insufficient_depth": 1,
                    "manual_review_required": 1,
                },
            },
            "daily_operator_markdown": "- no ready markets",
            "live_watchlist": [
                {
                    "market_id": "hk-empty",
                    "city": "Hong Kong",
                    "temp": 23,
                    "unit": "C",
                    "side": "NO",
                    "normal_size_gate": {"live_ready": False, "reasons": ["official_resolution_unavailable"], "recommended_action": "paper_strict_limit_only"},
                    "resolution_status": {
                        "latency": {
                            "official": {
                                "provider": "hong_kong_observatory",
                                "source_health": "published_empty",
                                "fallback_reason": "official_source_empty_payload",
                                "polling_focus": "hko_official_daily_extract",
                                "tier": "direct_history",
                                "source_url": "https://data.weather.gov.hk/example",
                            }
                        }
                    },
                },
                {
                    "market_id": "dallas-ready",
                    "city": "Dallas",
                    "temp": 35,
                    "unit": "C",
                    "side": "YES",
                    "normal_size_gate": {"live_ready": True, "reasons": []},
                },
            ],
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
                    "market_id": "manual-review",
                    "city": "Paris",
                    "temp": 20,
                    "unit": "C",
                    "side": "YES",
                    "normal_size_gate": {"live_ready": False, "reasons": ["manual_review_required"], "verdict": "manual_review"},
                }
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

    assert "## Synthèse opérateur" in markdown
    assert "- READY_NOW: 1" in markdown
    assert "- WAIT_SOURCE: 2" in markdown
    assert "- NO_EDGE: 1" in markdown
    assert "- MANUAL_REVIEW: 1" in markdown
    assert "## Diagnostics sources officielles" in markdown
    assert "hk-empty" in markdown
    assert "Hong Kong 23C NO" in markdown
    assert "published_empty" in markdown
    assert "official_source_empty_payload" in markdown
    assert "hko_official_daily_extract" in markdown



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


def test_learning_report_is_built_from_latest_safe_evaluation_and_paper_orders(tmp_path: Path, monkeypatch) -> None:
    evaluation = _write_json(
        tmp_path / "eval" / "shadow_profile_evaluation_20260430.json",
        {
            "paper_only": True,
            "live_order_allowed": False,
            "profiles": [
                {"profile_id": "sharp_rain", "recommendation": "promote_to_paper_profile", "resolved_orders": 8, "roi": 0.12, "winrate": 0.75}
            ],
        },
    )
    paper_orders = _write_json(
        tmp_path / "orders" / "shadow_paper_orders_20260430.json",
        {
            "paper_only": True,
            "live_order_allowed": False,
            "orders": [
                {
                    "market_id": "rain-1",
                    "profile_id": "sharp_rain",
                    "question": "Will it rain?",
                    "strict_limit_price": 0.52,
                    "features": {"forecast_context": {"model_probability_at_trade": 0.54}, "resolution": {"available": False}},
                }
            ],
        },
    )
    _write_json(
        tmp_path / "unsafe" / "shadow_profile_evaluation_unsafe.json",
        {"paper_only": True, "live_order_allowed": False, "nested": {"live_order_allowed": True}, "profiles": []},
    ).touch()
    monkeypatch.setattr(weather_operator_daily, "DATA", tmp_path)

    report = weather_operator_daily.build_daily_learning_report("20260430T120000Z")

    assert report is not None
    assert report["paper_only"] is True
    assert report["live_order_allowed"] is False
    assert report["summary"]["promote_profiles"] == 1
    assert report["summary"]["high_information_cases"] == 1
    assert report["artifacts"]["shadow_profile_evaluation_json"] == str(evaluation)
    assert report["artifacts"]["shadow_paper_orders_json"] == str(paper_orders)
    assert report["artifacts"]["learning_report_json"].endswith("weather_shadow_profile_learning_report_20260430T120000Z.json")
    assert Path(report["artifacts"]["learning_report_json"]).exists()


def test_learning_report_ignores_unsafe_nested_live_order_allowed(tmp_path: Path, monkeypatch) -> None:
    _write_json(
        tmp_path / "eval" / "shadow_profile_evaluation_unsafe.json",
        {"paper_only": True, "live_order_allowed": False, "nested": {"live_order_allowed": True}, "profiles": []},
    )
    _write_json(tmp_path / "orders" / "shadow_paper_orders.json", {"paper_only": True, "live_order_allowed": False, "orders": []})
    monkeypatch.setattr(weather_operator_daily, "DATA", tmp_path)

    assert weather_operator_daily.build_daily_learning_report("20260430T120000Z") is None


def test_render_daily_markdown_includes_learning_report_section(tmp_path: Path) -> None:
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
            "daily_operator_rollup": {"live_ready": False, "watchlist_count": 0, "not_ready_reason_counts": {}},
            "daily_operator_markdown": "- no ready markets",
        },
    )
    paper_watchlist = _write_json(
        tmp_path / "watchlist.json",
        {"paper_only": True, "live_order_allowed": False, "summary": {"positions": 0, "total_spend": 0, "total_ev_now": 0, "action_counts": {}}},
    )
    learning_report = {
        "paper_only": True,
        "live_order_allowed": False,
        "profile_actions": [{"profile_id": "sharp_rain", "action": "promote_candidate_paper_only", "reason": "positive_resolved_edge"}],
        "high_information_cases": [{"market_id": "rain-1", "learning_reason": "near_probability_threshold", "profile_id": "sharp_rain"}],
        "next_experiments": ["spawn_profile_variants_for_sharp_rain"],
    }

    markdown = weather_operator_daily.render_daily_markdown(
        stamp="20260430T120000Z",
        refresh_path=refresh,
        account_summary_path=account_summary,
        paper_monitor_path=monitor,
        paper_watchlist_path=paper_watchlist,
        paper_watchlist_md=watchlist_md,
        daily_json_path=daily_json,
        learning_report=learning_report,
    )

    assert "## Learning report" in markdown
    assert "### Profile actions" in markdown
    assert "sharp_rain" in markdown
    assert "promote_candidate_paper_only" in markdown
    assert "### High-information cases" in markdown
    assert "rain-1" in markdown
    assert "near_probability_threshold" in markdown
    assert "### Next experiments" in markdown
    assert "spawn_profile_variants_for_sharp_rain" in markdown
