from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

PYTHON_SRC = Path(__file__).resolve().parents[1] / "src"


def _run_weather_pm(*args: str) -> dict[str, object]:
    result = subprocess.run(
        [sys.executable, "-m", "weather_pm.cli", *args],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PYTHONPATH": str(PYTHON_SRC)},
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def _example(wallet: str, market_id: str, *, pnl: float, capturable: str = "capturable", label: str = "trade", market_type: str = "high_temperature", price: float = 0.42, distance_to_threshold: float = -0.2, forecast_age_minutes: int = 45) -> dict[str, object]:
    return {
        "label": label,
        "account": wallet,
        "wallet": wallet,
        "market_id": market_id,
        "city": "Paris",
        "date": "2026-05-04",
        "market_type": market_type,
        "side": "YES",
        "price": price,
        "pnl": pnl,
        "capturability": capturable,
        "orderbook_context_available": capturable == "capturable",
        "weather_context_available": True,
        "distance_to_threshold": distance_to_threshold,
        "forecast_age_minutes": forecast_age_minutes,
    }


def test_robust_positive_slice_outputs_robust_candidate() -> None:
    from weather_pm.winner_pattern_engine import build_winner_pattern_engine

    decision_context = {"examples": [_example("0xa", f"m{i}", pnl=3.0) for i in range(3)] + [_example("0xb", f"n{i}", pnl=2.0) for i in range(3)]}
    payload = build_winner_pattern_engine(decision_context, {"trades": []}, min_resolved_trades=5)

    robust = payload["robust_patterns"]
    assert robust
    assert robust[0]["pattern_status"] == "robust_candidate"
    assert robust[0]["archetype"] == "threshold_harvester"
    assert robust[0]["capturable_contexts"] >= 5
    assert payload["paper_only"] is True
    assert payload["live_order_allowed"] is False


def test_negative_or_bad_capturability_outputs_anti_pattern_and_blocks_live_radar() -> None:
    from weather_pm.winner_pattern_engine import build_winner_pattern_engine

    decision_context = {"examples": [_example("0xa", f"m{i}", pnl=-2.0, capturable="not_capturable") for i in range(6)]}
    payload = build_winner_pattern_engine(decision_context, {"trades": []}, min_resolved_trades=5)

    anti = payload["anti_patterns"]
    assert anti
    assert anti[0]["pattern_status"] == "anti_pattern"
    assert anti[0]["block_live_radar"] is True
    assert anti[0]["reason"] in {"negative_out_of_sample_pnl", "bad_capturability"}


def test_concentration_or_small_sample_downgrades_to_research_only() -> None:
    from weather_pm.winner_pattern_engine import build_winner_pattern_engine

    concentrated = {"examples": [_example("0xwhale", f"m{i}", pnl=10.0) for i in range(5)] + [_example("0xsmall", "m6", pnl=1.0)]}
    payload = build_winner_pattern_engine(concentrated, {"trades": []}, min_resolved_trades=5, max_top1_pnl_share=0.8)

    research = payload["research_only_patterns"]
    assert research
    assert research[0]["pattern_status"] == "research_only"
    assert research[0]["reason"] == "concentrated_or_small_sample"


def test_archetype_labels_cover_initial_pattern_families() -> None:
    from weather_pm.winner_pattern_engine import classify_archetype

    assert classify_archetype({"distance_to_threshold": 0.1, "market_type": "high_temperature"}) == "threshold_harvester"
    assert classify_archetype({"market_type": "exact_bin", "bin_center": 72}) == "exact_bin_anomaly_hunter"
    assert classify_archetype({"forecast_age_minutes": 5, "price": 0.87}) == "late_certainty_compounder"
    assert classify_archetype({"surface_count": 4}) == "surface_grid_trader"
    assert classify_archetype({"label": "no_trade"}) == "abstention_filter"
    assert classify_archetype({}) == "unclear"



def _v2_example(
    idx: int,
    *,
    pnl: float = 1.0,
    wallet: str | None = None,
    sample_split: str | None = None,
    capturability: str = "capturable",
    forecast_age_minutes: int = 60,
    distance_to_threshold: float = 1.5,
    resolution_verified: bool = True,
    time_to_resolution_minutes: int = 120,
    spread: float = 0.04,
    depth_near_touch: float = 50.0,
    estimated_slippage_bps: float = 100.0,
) -> dict[str, object]:
    row = _example(
        wallet or f"0x{idx % 4}",
        f"v2-{idx}",
        pnl=pnl,
        capturable=capturability,
        distance_to_threshold=distance_to_threshold,
        forecast_age_minutes=forecast_age_minutes,
    )
    row.update(
        {
            "timestamp": f"2026-04-{idx + 1:02d}T10:00:00Z",
            "sample_split": sample_split or ("train" if idx < 12 else "out_of_sample"),
            "notional": 10.0,
            "forecast_value_at_decision": 21.5,
            "threshold": 20.0,
            "forecast_source": "official",
            "resolution_verified": resolution_verified,
            "resolution_source": "official_station",
            "resolution_value": 22.0,
            "observation_timestamp": "2026-05-01T23:59:00Z",
            "time_to_resolution_minutes": time_to_resolution_minutes,
            "spread": spread,
            "depth_near_touch": depth_near_touch,
            "estimated_slippage_bps": estimated_slippage_bps,
        }
    )
    return row


def _passing_v2_examples() -> list[dict[str, object]]:
    # 20 trades, 4 wallets, OOS 8/8 positive, top trade/wallet concentration below v2 caps.
    return [_v2_example(i, pnl=1.0, wallet=f"0x{i % 4}") for i in range(20)]


def test_v2_gate_blocks_small_sample_with_explicit_promotion_blocker() -> None:
    from weather_pm.winner_pattern_engine import build_winner_pattern_engine

    payload = build_winner_pattern_engine({"examples": _passing_v2_examples()[:19]}, {"trades": []}, min_resolved_trades=5)

    assert payload["robust_patterns"] == []
    pattern = payload["research_only_patterns"][0]
    assert pattern["pattern_status"] == "research_only"
    assert pattern["promotion_gate_version"] == "weather_winner_pattern_v2_2026_04"
    assert pattern["promotion_eligible"] is False
    assert "insufficient_resolved_sample" in pattern["promotion_blockers"]
    assert pattern["promotion_metrics"]["resolved_trades"] == 19
    assert pattern["paper_only"] is True
    assert pattern["live_order_allowed"] is False


def test_v2_gate_blocks_wallet_concentration_even_with_positive_pnl() -> None:
    from weather_pm.winner_pattern_engine import build_winner_pattern_engine

    rows = [_v2_example(i, pnl=1.0, wallet="0xwhale" if i < 11 else f"0x{i % 4}") for i in range(20)]
    payload = build_winner_pattern_engine({"examples": rows}, {"trades": []}, min_resolved_trades=5, max_top1_pnl_share=0.95)

    assert payload["robust_patterns"] == []
    pattern = payload["research_only_patterns"][0]
    assert "wallet_concentrated_pnl" in pattern["promotion_blockers"]
    assert pattern["promotion_metrics"]["max_wallet_trade_share"] > 0.5
    assert pattern["promotion_eligible"] is False


def test_v2_gate_blocks_missing_out_of_sample_split() -> None:
    from weather_pm.winner_pattern_engine import build_winner_pattern_engine

    rows = [_v2_example(i, sample_split="train") for i in range(20)]
    payload = build_winner_pattern_engine({"examples": rows}, {"trades": []}, min_resolved_trades=5)

    pattern = payload["research_only_patterns"][0]
    assert "insufficient_out_of_sample_sample" in pattern["promotion_blockers"]
    assert pattern["promotion_metrics"]["oos_resolved_trades"] == 0


def test_v2_gate_blocks_available_orderbook_that_is_not_capturable() -> None:
    from weather_pm.winner_pattern_engine import build_winner_pattern_engine

    rows = [
        _v2_example(i, capturability="not_capturable", spread=0.15, depth_near_touch=2.0, estimated_slippage_bps=400.0)
        for i in range(20)
    ]
    for row in rows:
        row["orderbook_context_available"] = True
    payload = build_winner_pattern_engine({"examples": rows}, {"trades": []}, min_resolved_trades=5)

    pattern = payload["research_only_patterns"][0]
    assert "insufficient_historical_capturable_ratio" in pattern["promotion_blockers"]
    assert "historical_spread_too_wide" in pattern["promotion_blockers"]
    assert pattern["promotion_metrics"]["historical_capturable_ratio"] == 0.0


def test_v2_gate_blocks_stale_forecast_and_unverified_resolution() -> None:
    from weather_pm.winner_pattern_engine import build_winner_pattern_engine

    rows = [_v2_example(i, forecast_age_minutes=360, resolution_verified=False) for i in range(20)]
    payload = build_winner_pattern_engine({"examples": rows}, {"trades": []}, min_resolved_trades=5)

    pattern = payload["research_only_patterns"][0]
    assert "stale_forecast" in pattern["promotion_blockers"]
    assert "unverified_resolution" in pattern["promotion_blockers"]
    assert pattern["promotion_metrics"]["forecast_fresh_pct"] == 0.0
    assert pattern["promotion_metrics"]["resolution_verified_pct"] == 0.0


def test_v2_gate_promotes_only_when_all_promotion_criteria_pass() -> None:
    from weather_pm.winner_pattern_engine import build_winner_pattern_engine

    payload = build_winner_pattern_engine({"examples": _passing_v2_examples()}, {"trades": []}, min_resolved_trades=5)

    assert payload["research_only_patterns"] == []
    pattern = payload["robust_patterns"][0]
    assert pattern["pattern_status"] == "robust_candidate"
    assert pattern["reason"] == "passed_weather_winner_pattern_v2_promotion_gate"
    assert pattern["promotion_eligible"] is True
    assert pattern["promotion_blockers"] == []
    assert pattern["promotion_metrics"]["resolved_trades"] == 20
    assert pattern["promotion_metrics"]["oos_resolved_trades"] == 8
    assert pattern["promotion_metrics"]["unique_wallets"] == 4
    assert payload["summary"]["promotion_gate_version"] == "weather_winner_pattern_v2_2026_04"
    assert payload["paper_only"] is True
    assert payload["live_order_allowed"] is False
    assert pattern["paper_only"] is True
    assert pattern["live_order_allowed"] is False

def test_cli_winner_pattern_engine_writes_json_md_and_compact_stdout(tmp_path: Path) -> None:
    decision_path = tmp_path / "decision_context.json"
    trades_path = tmp_path / "resolved_trades.json"
    output_json = tmp_path / "patterns.json"
    output_md = tmp_path / "patterns.md"
    decision_path.write_text(json.dumps({"examples": [_example("0xa", f"m{i}", pnl=3.0) for i in range(3)] + [_example("0xb", f"n{i}", pnl=2.0) for i in range(3)]}), encoding="utf-8")
    trades_path.write_text(json.dumps({"trades": []}), encoding="utf-8")

    result = _run_weather_pm(
        "winner-pattern-engine",
        "--decision-context-json", str(decision_path),
        "--resolved-trades-json", str(trades_path),
        "--output-json", str(output_json),
        "--output-md", str(output_md),
    )

    assert result["paper_only"] is True
    assert result["live_order_allowed"] is False
    assert result["robust_patterns"] >= 1
    assert result["anti_patterns"] == 0
    assert result["research_only_patterns"] == 0
    assert result["output_json"] == str(output_json)
    artifact = json.loads(output_json.read_text(encoding="utf-8"))
    assert artifact["operator_next_actions"]
    assert artifact["feature_importance_counters"]["market_type"] >= 1
    assert "# Weather Winner Pattern Engine" in output_md.read_text(encoding="utf-8")
