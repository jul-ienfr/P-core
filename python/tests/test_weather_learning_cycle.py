from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from weather_pm.learning_cycle import (
    append_learning_experiment,
    assemble_learning_cycle_result,
    build_bounded_backfill_commands,
    build_learning_backfill_plan,
    build_learning_cycle_contract,
    build_learning_policy_actions,
    score_high_information_case,
    select_learning_accounts,
    validate_learning_cycle_safety,
)


def _sample_experiment() -> dict[str, object]:
    return {
        "profile_id": "coldmath",
        "hypothesis": "near-threshold weather markets need source backfill",
        "market_id": "weather-nyc-high-70-2026-05-01",
        "inputs": {"threshold_f": 70, "sources": ["noaa", "ecmwf"]},
        "notes": "paper learning only",
    }


def test_append_learning_experiment_writes_stable_paper_only_jsonl(tmp_path: Path) -> None:
    ledger_path = tmp_path / "learning_experiments.jsonl"
    experiment = _sample_experiment()

    first = append_learning_experiment(ledger_path, experiment, run_id="learn-run-1")
    reordered = {
        "market_id": experiment["market_id"],
        "inputs": {"sources": ["noaa", "ecmwf"], "threshold_f": 70},
        "hypothesis": experiment["hypothesis"],
        "profile_id": experiment["profile_id"],
        "notes": experiment["notes"],
    }
    forced = append_learning_experiment(ledger_path, reordered, run_id="learn-run-2", force=True)

    rows = [json.loads(line) for line in ledger_path.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 2
    assert first["experiment_hash"] == forced["experiment_hash"]
    assert rows[0]["experiment_hash"] == rows[1]["experiment_hash"]
    assert rows[0]["run_id"] == "learn-run-1"
    assert rows[0]["status"] == "awaiting_resolution"
    assert rows[0]["paper_only"] is True
    assert rows[0]["live_order_allowed"] is False
    assert rows[0]["no_real_order_placed"] is True
    assert rows[0]["profile_id"] == experiment["profile_id"]
    assert rows[0]["hypothesis"] == experiment["hypothesis"]
    assert rows[0]["market_id"] == experiment["market_id"]
    assert rows[0]["inputs"] == experiment["inputs"]
    assert rows[0]["deduplicated"] is False




def test_append_learning_experiment_deduplicates_by_hash_unless_forced(tmp_path: Path) -> None:
    ledger_path = tmp_path / "learning_experiments.jsonl"
    experiment = _sample_experiment()

    first = append_learning_experiment(ledger_path, experiment, run_id="learn-run-1")
    duplicate = append_learning_experiment(ledger_path, dict(experiment), run_id="learn-run-2")
    forced = append_learning_experiment(ledger_path, dict(experiment), run_id="learn-run-3", force=True)

    rows = [json.loads(line) for line in ledger_path.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 2
    assert duplicate["experiment_hash"] == first["experiment_hash"] == forced["experiment_hash"]
    assert duplicate["run_id"] == "learn-run-1"
    assert duplicate["deduplicated"] is True
    assert forced["run_id"] == "learn-run-3"
    assert forced["deduplicated"] is False
    assert rows[0]["run_id"] == "learn-run-1"
    assert rows[1]["run_id"] == "learn-run-3"



def test_score_high_information_case_returns_weighted_safe_components() -> None:
    case = {
        "profile_id": "coldmath",
        "hypothesis": "resolve near threshold NOAA vs ECMWF spread",
        "market_id": "weather-nyc-high-70-2026-05-01",
        "threshold_f": 70,
        "forecast_f": 69.6,
        "source_gap": 3.5,
        "profile_probabilities": {"coldmath": 0.42, "railbird": 0.67},
        "liquidity": 850,
        "uncertainty": 0.8,
        "inputs": {"sources": ["noaa", "ecmwf"]},
    }

    scored = score_high_information_case(case)

    assert scored["paper_only"] is True
    assert scored["live_order_allowed"] is False
    assert scored["no_real_order_placed"] is True
    assert scored["information_score"] > 0
    assert set(scored["components"]) == {
        "near_threshold",
        "source_gap",
        "profile_disagreement",
        "liquidity",
        "unresolved_uncertainty",
    }
    assert scored["components"]["near_threshold"] > scored["components"]["liquidity"]
    assert scored["components"]["source_gap"] > 0
    assert scored["components"]["profile_disagreement"] > 0
    assert case.get("information_score") is None



def test_build_learning_backfill_plan_scores_sorts_and_deduplicates_ledger_cases(tmp_path: Path) -> None:
    ledger_path = tmp_path / "learning_experiments.jsonl"
    duplicate_case = {
        "profile_id": "coldmath",
        "hypothesis": "already tracked close threshold gap",
        "market_id": "weather-bos-high-65-2026-05-01",
        "threshold_f": 65,
        "forecast_f": 64.8,
        "source_gap": 2.0,
        "profile_probabilities": {"coldmath": 0.48, "railbird": 0.57},
        "liquidity": 600,
        "uncertainty": 0.7,
    }
    append_learning_experiment(
        ledger_path,
        {
            "profile_id": duplicate_case["profile_id"],
            "hypothesis": duplicate_case["hypothesis"],
            "market_id": duplicate_case["market_id"],
            "inputs": {
                "threshold_f": duplicate_case["threshold_f"],
                "forecast_f": duplicate_case["forecast_f"],
                "source_gap": duplicate_case["source_gap"],
                "profile_probabilities": duplicate_case["profile_probabilities"],
                "liquidity": duplicate_case["liquidity"],
                "uncertainty": duplicate_case["uncertainty"],
            },
        },
        run_id="existing-run",
    )
    report = {
        "paper_only": True,
        "live_order_allowed": False,
        "no_real_order_placed": True,
        "high_information_cases": [
            {
                "profile_id": "railbird",
                "hypothesis": "thin liquidity far from threshold",
                "market_id": "weather-mia-rain-2026-05-01",
                "threshold": 0.5,
                "observed": 0.2,
                "source_gap": 0.2,
                "profile_probabilities": {"coldmath": 0.51, "railbird": 0.53},
                "liquidity": 100,
                "unresolved_uncertainty": 0.2,
            },
            duplicate_case,
            {
                "profile_id": "coldmath",
                "hypothesis": "highest priority threshold and source disagreement",
                "market_id": "weather-nyc-high-70-2026-05-01",
                "threshold_f": 70,
                "forecast_f": 69.9,
                "source_gap": 4.0,
                "profile_probabilities": {"coldmath": 0.35, "railbird": 0.78},
                "liquidity": 900,
                "uncertainty": 0.9,
            },
        ],
    }

    plan = build_learning_backfill_plan(report, ledger_path, max_cases=2)

    assert plan["paper_only"] is True
    assert plan["live_order_allowed"] is False
    assert plan["no_real_order_placed"] is True
    assert plan["summary"]["input_cases"] == 3
    assert plan["summary"]["deduplicated_cases"] == 1
    assert len(plan["cases"]) == 2
    assert [case["market_id"] for case in plan["cases"]] == [
        "weather-nyc-high-70-2026-05-01",
        "weather-mia-rain-2026-05-01",
    ]
    assert plan["cases"][0]["information_score"] >= plan["cases"][1]["information_score"]
    assert "python3 -m weather_pm.cli learning-cycle" in plan["command_hints"][0]



def test_build_learning_policy_actions_maps_known_profile_actions_to_safe_paper_policy() -> None:
    report = {
        "paper_only": True,
        "live_order_allowed": False,
        "no_real_order_placed": True,
        "profile_actions": [
            {
                "profile_id": "coldmath",
                "action": "promote_candidate_paper_only",
                "resolved_count": 12,
                "roi": 0.11,
                "winrate": 0.64,
                "note": "paper signal only",
            },
            {
                "profile_id": "railbird",
                "action": "disable_or_reduce_shadow_profile",
                "resolved_count": 10,
                "roi": -0.02,
                "winrate": 0.42,
            },
            {
                "profile_id": "poligarch",
                "action": "collect_more_resolutions",
                "resolved_count": 3,
            },
            {"profile_id": "unknown", "action": "rebalance_live_book"},
        ],
    }

    policy = build_learning_policy_actions(report)

    assert policy["paper_only"] is True
    assert policy["live_order_allowed"] is False
    assert policy["no_real_order_placed"] is True
    assert [action["policy_action"] for action in policy["actions"]] == [
        "promote_shadow_profile_paper_only",
        "reduce_or_disable_shadow_profile",
        "request_resolution_backfill",
    ]
    assert policy["actions"][0]["profile_id"] == "coldmath"
    assert policy["actions"][0]["resolved_count"] == 12
    assert policy["actions"][0]["roi"] == 0.11
    assert policy["actions"][0]["winrate"] == 0.64
    for action in policy["actions"]:
        assert action["paper_only"] is True
        assert action["live_order_allowed"] is False
        assert action["no_real_order_placed"] is True
    assert policy["summary"] == {
        "input_profile_actions": 4,
        "policy_actions": 3,
        "ignored_unknown_actions": 1,
        "blocked_promotions": 0,
    }



def test_build_learning_policy_actions_blocks_unsafe_reports() -> None:
    report = {
        "paper_only": True,
        "live_order_allowed": False,
        "no_real_order_placed": True,
        "profile_actions": [
            {
                "profile_id": "coldmath",
                "action": "promote_candidate_paper_only",
                "live_order_allowed": True,
            }
        ],
    }

    try:
        build_learning_policy_actions(report)
    except ValueError as exc:
        assert "unsafe learning report" in str(exc)
    else:
        raise AssertionError("unsafe report should be rejected")



def test_build_learning_policy_actions_blocks_false_edge_promotions_with_threshold_reasons() -> None:
    report = {
        "paper_only": True,
        "live_order_allowed": False,
        "no_real_order_placed": True,
        "profile_actions": [
            {
                "profile_id": "thin",
                "action": "promote_candidate_paper_only",
                "resolved_count": 7,
                "roi": 0.20,
                "winrate": 0.80,
            },
            {
                "profile_id": "negative-roi",
                "action": "promote_candidate_paper_only",
                "resolved_count": 20,
                "roi": 0.049,
                "winrate": 0.70,
            },
            {
                "profile_id": "weak-winrate",
                "action": "promote_candidate_paper_only",
                "resolved_count": 20,
                "roi": 0.12,
                "winrate": 0.54,
            },
        ],
    }

    policy = build_learning_policy_actions(
        report,
        min_resolved_for_promotion=8,
        min_roi_for_promotion=0.05,
        min_winrate_for_promotion=0.55,
    )

    assert [action["policy_action"] for action in policy["actions"]] == [
        "request_resolution_backfill",
        "request_resolution_backfill",
        "request_resolution_backfill",
    ]
    assert [action["blocked_promotion_reason"] for action in policy["actions"]] == [
        "insufficient_resolved_sample",
        "roi_below_threshold",
        "winrate_below_threshold",
    ]
    assert policy["summary"]["blocked_promotions"] == 3
    assert policy["summary"]["policy_actions"] == 3



def test_select_learning_accounts_prioritizes_resolution_actions_case_insensitive_and_wallet_matches() -> None:
    followlist = [
        {"handle": "LowScore", "wallet": "0xlow", "profile_id": "low", "score": "99"},
        {"handle": "ColdMath", "wallet": "0xabc", "profile_id": "coldmath", "score": "0.20"},
        {"handle": "RailBird", "wallet": "0xdef", "profile_id": "railbird", "score": "10"},
        {"handle": "Poligarch", "wallet": "0x999", "profile_id": "poligarch", "score": "5"},
    ]
    report = {
        "paper_only": True,
        "live_order_allowed": False,
        "no_real_order_placed": True,
        "profile_actions": [
            {"profile_id": "coldmath", "action": "promote_candidate_paper_only", "score": 0.7},
            {"profile_id": "railbird", "action": "collect_more_resolutions", "score": 0.1},
            {"profile_id": "ignored", "wallet": "0x999", "action": "disable_or_reduce_shadow_profile", "score": 0.9},
        ],
    }

    selected = select_learning_accounts(followlist, report, max_accounts=3)

    assert [row["handle"] for row in selected] == ["RailBird", "Poligarch", "ColdMath"]
    assert [row["learning_action"] for row in selected] == [
        "collect_more_resolutions",
        "disable_or_reduce_shadow_profile",
        "promote_candidate_paper_only",
    ]
    assert selected[0]["learning_priority"] > selected[1]["learning_priority"] >= selected[2]["learning_priority"]
    for row in selected:
        assert row["paper_only"] is True
        assert row["live_order_allowed"] is False
        assert row["no_real_order_placed"] is True



def test_select_learning_accounts_uses_numeric_scores_for_ties_and_limits() -> None:
    followlist = [
        {"handle": "alpha", "profile_id": "alpha", "score": "2"},
        {"handle": "beta", "profile_id": "beta", "score": "5"},
        {"handle": "gamma", "profile_id": "gamma", "score": "1"},
    ]
    report = {
        "paper_only": True,
        "live_order_allowed": False,
        "no_real_order_placed": True,
        "profile_actions": [
            {"profile_id": "alpha", "action": "collect_more_resolutions"},
            {"profile_id": "beta", "action": "collect_more_resolutions"},
            {"profile_id": "gamma", "action": "collect_more_resolutions"},
        ],
    }

    selected = select_learning_accounts(followlist, report, max_accounts=2)

    assert [row["profile_id"] for row in selected] == ["beta", "alpha"]



def test_build_bounded_backfill_commands_returns_plan_only_safe_bounded_cli_steps(tmp_path: Path) -> None:
    commands = build_bounded_backfill_commands(
        output_dir=tmp_path / "learning run",
        followlist_csv=tmp_path / "follow list.csv",
        max_accounts=3,
        trades_per_account=25,
        lookback_days=14,
    )

    assert len(commands) == 6
    expected_surfaces = [
        "backfill-account-trades",
        "import-account-trades",
        "shadow-profile-report",
        "shadow-paper-runner",
        "shadow-profile-evaluator",
        "shadow-profile-learning-report",
    ]
    for command, surface in zip(commands, expected_surfaces):
        assert command.startswith("PYTHONPATH=python/src python3 -m weather_pm.cli ")
        assert surface in command
        assert "paper_only=true" in command
        assert "live_order_allowed=false" in command
        assert "no_real_order_placed=true" in command
        assert "paper-ledger-place" not in command
    assert "--limit-accounts 3" in commands[0]
    assert "--trades-per-account 25" in commands[0]
    assert "--max-accounts 3" in commands[2]
    assert "--lookback-days 14" in commands[5]
    assert "--no-network" in commands[3]
    assert "--max-order-usdc 0" in commands[3]
    assert str(tmp_path / "learning run" / "raw_account_trades.json") in commands[0]



def test_build_bounded_backfill_commands_rejects_unbounded_limits(tmp_path: Path) -> None:
    try:
        build_bounded_backfill_commands(tmp_path, tmp_path / "follow.csv", max_accounts=0, trades_per_account=10)
    except ValueError as exc:
        assert "max_accounts" in str(exc)
    else:
        raise AssertionError("unbounded max_accounts should be rejected")



def test_build_learning_cycle_contract_is_strictly_paper_only(tmp_path: Path) -> None:
    contract = build_learning_cycle_contract(
        run_id="learn-test",
        output_dir=tmp_path,
        max_accounts=5,
        trades_per_account=10,
        lookback_days=7,
    )

    assert contract["run_id"] == "learn-test"
    assert contract["paper_only"] is True
    assert contract["live_order_allowed"] is False
    assert contract["no_real_order_placed"] is True
    assert contract["output_dir"] == str(tmp_path)
    assert contract["limits"] == {
        "max_accounts": 5,
        "trades_per_account": 10,
        "lookback_days": 7,
    }


def test_validate_learning_cycle_safety_rejects_nested_live_order_flags() -> None:
    payload = {
        "paper_only": True,
        "live_order_allowed": False,
        "steps": [
            {"name": "safe", "live_order_allowed": False},
            {"name": "unsafe", "nested": {"live_order_allowed": True}},
        ],
    }

    result = validate_learning_cycle_safety(payload)

    assert result["ok"] is False
    assert "steps[1].nested.live_order_allowed" in result["violations"]


def test_validate_learning_cycle_safety_requires_top_level_paper_only() -> None:
    result = validate_learning_cycle_safety({"paper_only": False, "live_order_allowed": False})

    assert result["ok"] is False
    assert "paper_only" in result["violations"]


def _sample_learning_report() -> dict[str, object]:
    return {
        "paper_only": True,
        "live_order_allowed": False,
        "no_real_order_placed": True,
        "profile_actions": [
            {
                "profile_id": "coldmath",
                "action": "promote_candidate_paper_only",
                "resolved_count": 12,
                "roi": 0.09,
                "winrate": 0.61,
            },
            {
                "profile_id": "railbird",
                "action": "collect_more_resolutions",
                "resolved_count": 2,
            },
        ],
        "high_information_cases": [
            {
                "profile_id": "coldmath",
                "hypothesis": "near-threshold source gap",
                "market_id": "weather-nyc-high-70-2026-05-01",
                "threshold_f": 70,
                "forecast_f": 69.8,
                "source_gap": 3.5,
                "profile_probabilities": {"coldmath": 0.42, "railbird": 0.68},
                "liquidity": 800,
                "uncertainty": 0.7,
            },
            {
                "profile_id": "railbird",
                "hypothesis": "rain source disagreement",
                "market_id": "weather-mia-rain-2026-05-01",
                "threshold": 0.5,
                "observed": 0.48,
                "source_gap": 1.5,
                "profile_probabilities": {"coldmath": 0.49, "railbird": 0.58},
                "liquidity": 300,
                "uncertainty": 0.4,
            },
        ],
    }


def test_assemble_learning_cycle_result_combines_safe_outputs_and_appends_ledger(tmp_path: Path) -> None:
    result = assemble_learning_cycle_result(
        run_id="learn-full",
        output_dir=tmp_path,
        learning_report=_sample_learning_report(),
        max_accounts=5,
        trades_per_account=10,
        lookback_days=7,
        max_cases=1,
    )

    assert result["ok"] is True
    assert result["paper_only"] is True
    assert result["live_order_allowed"] is False
    assert result["no_real_order_placed"] is True
    assert result["contract"]["run_id"] == "learn-full"
    assert result["policy"]["summary"]["policy_actions"] == 2
    assert result["backfill_plan"]["summary"]["selected_cases"] == 1
    assert result["summary"] == {
        "policy_count": 2,
        "backfill_count": 1,
        "ledger_appended": 1,
        "safety_ok": True,
    }
    ledger_path = tmp_path / "learning_experiments.jsonl"
    rows = [json.loads(line) for line in ledger_path.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1
    assert rows[0]["run_id"] == "learn-full"
    assert rows[0]["paper_only"] is True
    assert rows[0]["live_order_allowed"] is False
    assert rows[0]["no_real_order_placed"] is True
    assert result["safety"]["ok"] is True


def test_assemble_learning_cycle_result_rejects_unsafe_report_without_ledger_write(tmp_path: Path) -> None:
    unsafe_report = _sample_learning_report()
    unsafe_report["profile_actions"] = [{"profile_id": "bad", "live_order_allowed": True}]

    try:
        assemble_learning_cycle_result(
            run_id="learn-unsafe",
            output_dir=tmp_path,
            learning_report=unsafe_report,
            max_accounts=5,
            trades_per_account=10,
            lookback_days=7,
        )
    except ValueError as exc:
        assert "unsafe learning report" in str(exc)
    else:
        raise AssertionError("unsafe report should be rejected")
    assert not (tmp_path / "learning_experiments.jsonl").exists()


def test_learning_cycle_cli_with_report_writes_full_artifacts_and_prints_cycle_json(tmp_path: Path) -> None:
    report_json = tmp_path / "learning_report.json"
    output_dir = tmp_path / "cycle"
    report_json.write_text(json.dumps(_sample_learning_report()), encoding="utf-8")

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "weather_pm.cli",
            "learning-cycle",
            "--run-id",
            "learn-full-cli",
            "--output-dir",
            str(output_dir),
            "--max-accounts",
            "5",
            "--trades-per-account",
            "10",
            "--lookback-days",
            "7",
            "--learning-report-json",
            str(report_json),
            "--dry-run",
            "--no-network",
        ],
        check=True,
        text=True,
        capture_output=True,
    )

    expected = {
        "learning_cycle_contract.json",
        "learning_cycle_result.json",
        "learning_policy_actions.json",
        "learning_backfill_plan.json",
        "learning_cycle_summary.md",
        "learning_experiments.jsonl",
    }
    assert expected.issubset({path.name for path in output_dir.iterdir()})
    result = json.loads((output_dir / "learning_cycle_result.json").read_text(encoding="utf-8"))
    assert result["ok"] is True
    assert result["paper_only"] is True
    assert result["live_order_allowed"] is False
    assert result["no_real_order_placed"] is True
    summary_md = (output_dir / "learning_cycle_summary.md").read_text(encoding="utf-8")
    assert "paper_only: true" in summary_md
    assert "live_order_allowed: false" in summary_md
    assert "policy_count: 2" in summary_md
    stdout_summary = json.loads(completed.stdout.strip().splitlines()[-1])
    assert stdout_summary["ok"] is True
    assert stdout_summary["artifacts"]["cycle_json"] == str(output_dir / "learning_cycle_result.json")


def test_learning_cycle_cli_writes_contract_and_prints_compact_json(tmp_path: Path) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "weather_pm.cli",
            "learning-cycle",
            "--run-id",
            "learn-test",
            "--output-dir",
            str(tmp_path),
            "--max-accounts",
            "5",
            "--trades-per-account",
            "10",
            "--lookback-days",
            "7",
            "--dry-run",
            "--no-network",
        ],
        check=True,
        text=True,
        capture_output=True,
    )

    contract_json = tmp_path / "learning_cycle_contract.json"
    assert contract_json.exists()
    contract = json.loads(contract_json.read_text(encoding="utf-8"))
    assert contract["paper_only"] is True
    assert contract["live_order_allowed"] is False
    assert contract["no_real_order_placed"] is True

    summary = json.loads(completed.stdout.strip().splitlines()[-1])
    assert summary["ok"] is True
    assert summary["paper_only"] is True
    assert summary["live_order_allowed"] is False
    assert summary["artifacts"]["contract_json"] == str(contract_json)
