from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from weather_pm.consensus_tracker import build_weather_consensus_tracker
from weather_pm.threshold_watcher import build_threshold_watch_report

FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "polymarket_weather_city_date_surface.json"

EXPECTED_MARKET_KEYS = {
    "market_id",
    "question",
    "contract_kind",
    "side_tokens",
    "orderbook",
    "source_url",
    "account_consensus_hint",
}
EXPECTED_TOKEN_KEYS = {"yes", "no"}
EXPECTED_ORDERBOOK_KEYS = {"best_bid", "best_ask", "spread"}
EXPECTED_SCHEMA_KEYS = {
    "schema_version",
    "surface_identity",
    "source",
    "account_consensus",
    "markets",
}


def _load_surface_fixture() -> dict[str, Any]:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _normalized_surface_identity(payload: dict[str, Any]) -> tuple[str, str, str, str]:
    identity = payload["surface_identity"]
    return (
        str(identity["city"]),
        str(identity["date"]),
        str(identity["measurement_kind"]),
        str(identity["unit"]),
    )


def test_production_contract_fixture_loads_multi_market_city_date_surface() -> None:
    payload = _load_surface_fixture()

    assert set(payload) == EXPECTED_SCHEMA_KEYS
    assert payload["schema_version"] == 1
    assert _normalized_surface_identity(payload) == ("Chicago", "2026-04-30", "high", "f")
    assert payload["source"] == {
        "provider": "noaa",
        "station_code": "KMDW",
        "station_name": "Chicago Midway International Airport",
        "source_url": "https://www.ncei.noaa.gov/access/services/data/v1?dataset=daily-summaries&stations=KMDW&startDate=2026-04-30&endDate=2026-04-30&format=json&units=standard&includeAttributes=false",
        "status": "source_confirmed_fixture",
    }
    assert payload["account_consensus"] == {
        "unique_accounts": 4,
        "signal_count": 11,
        "dominant_side": "YES",
        "top_handles": ["LakeWx", "GridSharp", "ThresholdCat"],
    }

    markets = payload["markets"]
    assert isinstance(markets, list)
    assert len(markets) == 5
    assert {market["contract_kind"] for market in markets} == {"exact_bin", "threshold_high", "threshold_low"}


def test_production_contract_fixture_market_rows_include_tokens_books_source_and_consensus_hints() -> None:
    payload = _load_surface_fixture()
    source_url = payload["source"]["source_url"]

    exact_bins = []
    threshold_high = []
    threshold_low = []
    for market in payload["markets"]:
        assert set(market) == EXPECTED_MARKET_KEYS
        assert set(market["side_tokens"]) == EXPECTED_TOKEN_KEYS
        assert all(isinstance(market["side_tokens"][side], str) and market["side_tokens"][side] for side in EXPECTED_TOKEN_KEYS)
        assert set(market["orderbook"]) == EXPECTED_ORDERBOOK_KEYS
        assert market["orderbook"]["spread"] == round(market["orderbook"]["best_ask"] - market["orderbook"]["best_bid"], 4)
        assert market["source_url"] == source_url
        assert {"unique_accounts", "signal_count", "dominant_side"}.issubset(market["account_consensus_hint"])
        if market["contract_kind"] == "exact_bin":
            exact_bins.append(market)
        elif market["contract_kind"] == "threshold_high":
            threshold_high.append(market)
        elif market["contract_kind"] == "threshold_low":
            threshold_low.append(market)

    assert [market["question"] for market in exact_bins] == [
        "Will the highest temperature in Chicago be exactly 70°F on April 30?",
        "Will the highest temperature in Chicago be exactly 71°F on April 30?",
        "Will the highest temperature in Chicago be exactly 72°F on April 30?",
    ]
    assert [market["question"] for market in threshold_high] == [
        "Will the highest temperature in Chicago be 72°F or higher on April 30?"
    ]
    assert [market["question"] for market in threshold_low] == [
        "Will the highest temperature in Chicago be 70°F or below on April 30?"
    ]


def test_production_contract_fixture_has_stable_json_output_schema() -> None:
    payload = _load_surface_fixture()

    canonical = json.loads(json.dumps(payload, sort_keys=True, separators=(",", ":")))

    assert list(canonical) == ["account_consensus", "markets", "schema_version", "source", "surface_identity"]
    assert list(canonical["surface_identity"]) == ["city", "date", "measurement_kind", "unit"]
    assert list(canonical["source"]) == ["provider", "source_url", "station_code", "station_name", "status"]
    assert list(canonical["markets"][0]) == [
        "account_consensus_hint",
        "contract_kind",
        "market_id",
        "orderbook",
        "question",
        "side_tokens",
        "source_url",
    ]


def test_threshold_watcher_report_from_production_fixture_has_stable_schema() -> None:
    payload = _load_surface_fixture()
    report = build_threshold_watch_report(
        payload,
        hours_to_resolution=2,
        observed_value=73.0,
        limit=10,
    )

    assert report["summary"] == {
        "input_markets": 5,
        "threshold_markets": 2,
        "near_resolution_thresholds": 2,
        "recommendation_counts": {"paper_micro_strict_limit": 2},
    }
    assert list(report["threshold_watch"][0]) == [
        "market_id",
        "question",
        "eligible",
        "threshold_kind",
        "threshold_direction",
        "threshold",
        "hours_to_resolution",
        "source_status",
        "source_confirmed",
        "source_value",
        "source_margin",
        "favored_side",
        "candidate_side",
        "top_ask",
        "strict_limit",
        "recommendation",
        "blocker",
        "reason",
    ]
    by_id = {row["market_id"]: row for row in report["threshold_watch"]}
    assert by_id["chicago-high-72f-or-higher-20260430"]["recommendation"] == "paper_micro_strict_limit"
    assert by_id["chicago-high-70f-or-below-20260430"]["favored_side"] == "NO"



def test_production_contract_event_surface_source_first_statuses() -> None:
    from weather_pm.event_surface import build_weather_event_surface

    source = {
        "provider": "noaa",
        "station_code": "KMDW",
        "station_name": "Chicago Midway International Airport",
        "station_type": "airport",
        "source_url": "https://www.weather.gov/wrh/Climate?wfo=lot",
        "wording_clear": True,
        "rules_clear": True,
        "manual_review_needed": False,
        "revision_risk": "low",
    }

    confirmed = build_weather_event_surface(
        [
            {
                "id": "confirmed",
                "question": "Will the highest temperature in Chicago be exactly 70°F on April 30?",
                "yes_price": 0.25,
                "resolution": source,
            }
        ]
    )["events"][0]
    missing = build_weather_event_surface(
        [{"id": "missing", "question": "Will the highest temperature in Chicago be exactly 70°F on April 30?", "yes_price": 0.25}]
    )["events"][0]
    conflict = build_weather_event_surface(
        [
            {
                "id": "conflict-a",
                "question": "Will the highest temperature in Chicago be exactly 70°F on April 30?",
                "yes_price": 0.25,
                "resolution": source,
            },
            {
                "id": "conflict-b",
                "question": "Will the highest temperature in Chicago be exactly 71°F on April 30?",
                "yes_price": 0.25,
                "resolution": {**source, "station_code": "KORD"},
            },
        ]
    )["events"][0]

    assert confirmed["source"]["status"] == "source_confirmed"
    assert confirmed["execution_status"] == "source_confirmed_candidate"
    assert missing["source"]["status"] == "source_missing"
    assert missing["execution_status"] == "source_missing_do_not_trade"
    assert conflict["source"]["status"] == "source_conflict"
    assert conflict["execution_status"] == "source_missing_do_not_trade"


def test_consensus_tracker_aggregates_surface_signals_and_detects_cluster_type() -> None:
    signals = [
        {
            "handle": "LakeWx",
            "wallet": "0xlake",
            "title": "Will the highest temperature in Chicago be exactly 72°F on April 30?",
            "side": "YES",
            "active_value_usdc": 125,
            "recent_trade_usdc": 20,
            "surface": "KMDW",
        },
        {
            "handle": "GridSharp",
            "wallet": "0xgrid",
            "title": "Will the highest temperature in Chicago be exactly 72°F on April 30?",
            "side": "YES",
            "active_value_usdc": 75,
            "recent_trade_usdc": 15,
            "surface": "KMDW",
        },
        {
            "handle": "SoloWhale",
            "wallet": "0xsolo",
            "title": "Will the highest temperature in Miami be exactly 80°F on April 30?",
            "side": "NO",
            "active_value_usdc": 900,
            "recent_trade_usdc": 200,
            "surface": "KMIA",
        },
        {
            "handle": "SoloWhale",
            "wallet": "0xsolo",
            "title": "Will the highest temperature in Miami be exactly 80°F on April 30?",
            "side": "NO",
            "active_value_usdc": 500,
            "recent_trade_usdc": 120,
            "surface": "KMIA",
        },
    ]

    report = build_weather_consensus_tracker(signals)

    by_key = {tuple(cluster["key"][part] for part in ("city", "date", "measurement_kind", "unit", "surface")): cluster for cluster in report["clusters"]}
    chicago = by_key[("Chicago", "April 30", "high", "f", "KMDW")]
    miami = by_key[("Miami", "April 30", "high", "f", "KMIA")]

    assert chicago["unique_account_count"] == 2
    assert chicago["signal_count"] == 2
    assert chicago["active_value_usdc"] == 200.0
    assert chicago["recent_trade_usdc"] == 35.0
    assert chicago["dominant_side"] == "YES"
    assert chicago["dominant_temperatures"] == [72.0]
    assert chicago["top_handles"] == ["LakeWx", "GridSharp"]
    assert chicago["cluster_type"] == "true_multi_account_consensus"

    assert miami["unique_account_count"] == 1
    assert miami["signal_count"] == 2
    assert miami["cluster_type"] == "single_account_heavy"


def test_consensus_tracker_weights_recent_same_surface_above_generic_city_history_and_skips_malformed_titles() -> None:
    signals = [
        {
            "handle": "RecentSurface",
            "wallet": "0xrecent",
            "title": "Will the highest temperature in Chicago be 72°F or higher on April 30?",
            "side": "YES",
            "recent_trade_usdc": 10,
            "active_value_usdc": 10,
            "surface": "KMDW",
            "signal_kind": "recent_trade",
        },
        {
            "handle": "OldCity",
            "wallet": "0xold",
            "title": "Will the highest temperature in Chicago be 75°F or higher on April 30?",
            "side": "YES",
            "recent_trade_usdc": 0,
            "active_value_usdc": 1000,
            "surface": "generic_city_history",
            "signal_kind": "historical_city",
        },
        {"handle": "Broken", "title": "Will it be nice out?", "side": "YES", "active_value_usdc": 999},
    ]

    report = build_weather_consensus_tracker(signals)

    assert report["summary"]["malformed_signal_count"] == 1
    recent = next(cluster for cluster in report["clusters"] if cluster["key"]["surface"] == "KMDW")
    historical = next(cluster for cluster in report["clusters"] if cluster["key"]["surface"] == "generic_city_history")
    assert recent["weight_components"]["recent_same_surface"] > historical["weight_components"]["generic_historical_city"]
    assert recent["consensus_score"] > historical["consensus_score"]


def test_consensus_tracker_artifact_schema_is_stable(tmp_path: Path) -> None:
    from weather_pm.consensus_tracker import write_weather_consensus_artifacts

    signals = [
        {
            "handle": "LakeWx",
            "wallet": "0xlake",
            "title": "Will the highest temperature in Chicago be exactly 72°F on April 30?",
            "side": "YES",
            "active_value_usdc": 125,
            "recent_trade_usdc": 20,
            "surface": "KMDW",
        }
    ]

    artifact = write_weather_consensus_artifacts(signals, output_dir=tmp_path)
    payload = json.loads(Path(artifact["json_path"]).read_text())

    assert list(payload) == ["schema_version", "summary", "clusters", "malformed_signals", "artifacts"]
    assert list(payload["clusters"][0]) == [
        "key",
        "unique_account_count",
        "signal_count",
        "active_value_usdc",
        "recent_trade_usdc",
        "dominant_side",
        "dominant_temperatures",
        "top_handles",
        "cluster_type",
        "consensus_score",
        "weight_components",
    ]
    assert Path(artifact["json_path"]).name == "weather_consensus_tracker_latest.json"
    assert Path(artifact["csv_path"]).name == "weather_consensus_tracker_latest.csv"
    assert Path(artifact["md_path"]).name == "weather_consensus_tracker_latest.md"
