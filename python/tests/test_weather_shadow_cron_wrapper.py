from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "weather_shadow_cron_wrapper.py"
_SPEC = importlib.util.spec_from_file_location("weather_shadow_cron_wrapper", SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
weather_shadow_cron_wrapper = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(weather_shadow_cron_wrapper)


def test_live_readiness_and_shadow_bridge_are_paper_only(tmp_path: Path) -> None:
    account_summary = {
        "daily_operator_rollup": {
            "live_ready": False,
            "live_ready_count": 1,
            "watchlist_count": 2,
            "normal_size_blocked_count": 1,
            "global_recommendation": "paper_micro_only",
            "not_ready_reason_counts": {"insufficient_depth": 1},
        },
        "live_watchlist": [
            {
                "market_id": "m-ready",
                "city": "Dallas",
                "temp": 35,
                "unit": "C",
                "side": "YES",
                "normal_size_gate": {"live_ready": True, "reasons": []},
            },
            {
                "market_id": "m-blocked",
                "city": "Hong Kong",
                "temp": 23,
                "unit": "C",
                "side": "NO",
                "normal_size_gate": {"live_ready": False, "reasons": ["insufficient_depth"]},
            },
        ],
    }

    readiness_path = tmp_path / "readiness.json"
    bridge_path = tmp_path / "bridge.json"
    readiness = weather_shadow_cron_wrapper.build_live_readiness(account_summary, output_json=readiness_path)
    bridge = weather_shadow_cron_wrapper.build_shadow_autopilot_bridge(
        readiness=readiness,
        account_summary=account_summary,
        output_json=bridge_path,
    )

    assert readiness_path.exists()
    assert bridge_path.exists()
    assert readiness["paper_only"] is True
    assert readiness["live_order_allowed"] is False
    assert readiness["no_real_order_placed"] is True
    assert readiness["status"] == "NOT_READY"
    assert readiness["ready_market_ids"] == ["m-ready"]
    assert bridge["mode"] == "dry-run/shadow"
    assert bridge["paper_only"] is True
    assert bridge["live_order_allowed"] is False
    assert bridge["orders_allowed"] is False
    assert bridge["messages_allowed"] is False
    assert bridge["action_counts"] == {"PAPER_AUTOPILOT_SHADOW_REVIEW": 1, "WATCH_ONLY": 1}
    assert bridge["would_place_order_count"] == 1
    assert bridge["can_micro_live"] is False
    assert bridge["micro_live_allowed"] is False
    assert all(action["no_real_order_placed"] is True for action in bridge["actions"])
    assert all(action["idempotency_key"] for action in bridge["actions"])
    weather_shadow_cron_wrapper.assert_safety({"live_readiness": readiness, "shadow_autopilot_bridge": bridge})


def test_compact_state_change_detects_only_compact_field_changes() -> None:
    current_payload = {
        "live_readiness": {
            "status": "NOT_READY",
            "live_ready_count": 0,
            "watchlist_count": 2,
            "normal_size_blocked_count": 2,
            "global_recommendation": "watch_only",
            "not_ready_reason_counts": {"missing_tradeable_quote": 2},
        },
        "shadow_autopilot_bridge": {
            "action_counts": {"WATCH_ONLY": 2},
            "proposed_action_count": 2,
        },
    }
    current = weather_shadow_cron_wrapper.compact_state(current_payload)
    previous = dict(current)

    assert weather_shadow_cron_wrapper.diff_state(previous, current) == {"changed": False, "initial": False, "fields": []}

    changed = dict(current)
    changed["live_ready_count"] = 1
    diff = weather_shadow_cron_wrapper.diff_state(previous, changed)

    assert diff["changed"] is True
    assert diff["initial"] is False
    assert diff["fields"] == ["live_ready_count"]


def test_assert_safety_rejects_live_orders() -> None:
    try:
        weather_shadow_cron_wrapper.assert_safety({"nested": {"live_order_allowed": True}})
    except RuntimeError as exc:
        assert "live_order_allowed=true" in str(exc)
    else:
        raise AssertionError("expected live_order_allowed safety violation")


def test_wrapper_main_with_fixture_inputs_writes_artifacts(tmp_path: Path, monkeypatch) -> None:
    data_root = tmp_path / "data" / "polymarket"
    input_json = data_root / "strategy-shortlists" / "weather_strategy_shortlist_fixture.json"
    input_json.parent.mkdir(parents=True)
    input_json.write_text(
        json.dumps(
            {
                "run_id": "fixture-run",
                "source": "fixture",
                "summary": {"shortlisted": 1},
                "shortlist": [
                    {
                        "rank": 1,
                        "market_id": "fixture-market",
                        "city": "Dallas",
                        "date": "May 1",
                        "action": "YES",
                        "decision_status": "watch",
                        "matched_traders": ["weatherace"],
                        "probability_edge": 0.05,
                        "order_book_depth_usd": 5,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    classified_csv = data_root / "weather_profitable_accounts_classified_top5000.csv"
    classified_csv.write_text(
        "userName,rank,weather_pnl_usd,weather_volume_usd,pnl_over_volume_pct,classification,active_weather_positions,recent_weather_activity,recent_nonweather_activity,recommended_use,profile_url,sample_weather_titles\n"
        "weatherace,1,100,1000,10,weather_heavy,1,1,0,follow,https://example.test,Weather market\n",
        encoding="utf-8",
    )
    reverse_json = data_root / "weather_heavy_trader_registry_full.json"
    reverse_json.write_text(json.dumps({"accounts": [{"handle": "weatherace", "classification": "weather_heavy"}]}), encoding="utf-8")

    monkeypatch.setattr(
        weather_shadow_cron_wrapper,
        "run_json",
        lambda cmd, repo, timeout=300: _fake_run_json(cmd, repo=repo, timeout=timeout),
    )

    rc = weather_shadow_cron_wrapper.main(
        [
            "--repo",
            str(ROOT),
            "--data-root",
            str(data_root),
            "--timestamp",
            "20260501T120000Z",
            "--input-json",
            str(input_json),
            "--source",
            "fixture",
            "--skip-resolution-status",
            "--skip-orderbook",
        ]
    )

    assert rc == 0
    state_path = data_root / "shadow-cron" / "weather_shadow_state_20260501T120000Z.json"
    change_path = data_root / "shadow-cron" / "weather_shadow_state_change_20260501T120000Z.json"
    assert state_path.exists()
    assert change_path.exists()
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["paper_only"] is True
    assert state["live_order_allowed"] is False
    assert state["no_real_order_placed"] is True
    assert state["messages_sent"] is False
    assert state["cron_created"] is False
    assert state["shadow_autopilot_bridge"]["orders_allowed"] is False
    assert state["can_micro_live"] is False
    assert state["micro_live_allowed"] is False
    assert state["micro_live_safety"]["kill_switch"] == "forced_disabled"
    assert state["paper_autopilot_ledger"]["paper_only"] is True
    assert state["live_canary_preflight"]["live_order_allowed"] is False
    assert state["live_canary_preflight"]["orders_allowed"] is False
    assert state["live_canary_preflight"]["eligible_count"] == 0
    assert Path(state["artifacts"]["live_canary_preflight_json"]).exists()
    assert (data_root / "shadow-cron" / "MICRO_LIVE_DISABLED.paper_only").exists()


def _fake_run_json(cmd: list[str], *, repo: Path, timeout: int = 300) -> dict:
    if "operator-refresh" in cmd:
        output = Path(cmd[cmd.index("--output-json") + 1])
        payload = {
            "summary": {"paper_only": True, "operator_watchlist_rows": 1},
            "operator": {
                "watchlist": [
                    {
                        "market_id": "fixture-market",
                        "city": "Dallas",
                        "temp": 35,
                        "unit": "C",
                        "side": "YES",
                        "matched_traders": ["weatherace"],
                        "normal_size_gate": {"live_ready": False, "reasons": ["insufficient_depth"]},
                    }
                ]
            },
            "artifacts": {"output_json": str(output)},
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload), encoding="utf-8")
        return {"ok": True, "paper_only": True, "live_order_allowed": False, "artifacts": {"output_json": str(output)}}
    if "profitable-accounts-operator-summary" in cmd:
        output = Path(cmd[cmd.index("--output-json") + 1])
        payload = {
            "daily_operator_rollup": {
                "live_ready": False,
                "live_ready_count": 0,
                "watchlist_count": 1,
                "normal_size_blocked_count": 1,
                "global_recommendation": "paper_micro_only",
                "not_ready_reason_counts": {"insufficient_depth": 1},
            },
            "live_watchlist": [
                {
                    "market_id": "fixture-market",
                    "city": "Dallas",
                    "temp": 35,
                    "unit": "C",
                    "side": "YES",
                    "normal_size_gate": {"live_ready": False, "reasons": ["insufficient_depth"]},
                }
            ],
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload), encoding="utf-8")
        return {"ok": True, "paper_only": True, "live_order_allowed": False, "artifacts": {"output_json": str(output)}}
    raise AssertionError(f"unexpected command: {cmd}")
