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


def _decision_payload() -> dict[str, object]:
    return {
        "examples": [
            {
                "label": "trade",
                "account": "alice",
                "wallet": "0xabc",
                "market_id": "m-paris-hi-21",
                "timestamp": "2026-05-04T12:35:00Z",
                "timestamp_bucket": "2026-05-04T12:00:00Z",
                "city": "Paris",
                "date": "2026-05-04",
                "market_type": "high_temperature",
                "side": "YES",
                "price": 0.37,
                "threshold": 21.0,
                "bin_center": 21.5,
            }
        ]
    }


def _forecast_payload() -> dict[str, object]:
    return {
        "forecasts": [
            {
                "market_id": "m-paris-hi-21",
                "city": "Paris",
                "date": "2026-05-04",
                "market_type": "high_temperature",
                "forecast_timestamp": "2026-05-04T11:00:00Z",
                "forecast_value": 20.8,
                "station_id": "LFPG",
                "station_name": "Paris Charles de Gaulle",
                "official_source_available": True,
            },
            {
                "market_id": "m-paris-hi-21",
                "city": "Paris",
                "date": "2026-05-04",
                "market_type": "high_temperature",
                "forecast_timestamp": "2026-05-04T13:00:00Z",
                "forecast_value": 22.4,
            },
        ]
    }


def _resolution_payload() -> dict[str, object]:
    return {
        "resolutions": [
            {
                "market_id": "m-paris-hi-21",
                "resolution_source": "official_station_history",
                "station_id": "LFPG",
                "station_name": "Paris Charles de Gaulle",
                "observation_timestamp": "2026-05-05T06:00:00Z",
                "observation_value": 21.7,
                "resolution_value": 21.7,
                "official_source_available": True,
            }
        ]
    }


def test_forecast_at_time_separates_decision_features_from_resolution_observation() -> None:
    from weather_pm.weather_decision_context import enrich_decision_weather_context

    payload = enrich_decision_weather_context(_decision_payload(), _forecast_payload(), _resolution_payload())

    row = payload["examples"][0]
    assert row["forecast_value_at_decision"] == 20.8
    assert row["forecast_value"] == 20.8
    assert row["forecast_timestamp"] == "2026-05-04T11:00:00Z"
    assert row["forecast_age_minutes"] == 95
    assert row["observation_value"] == 21.7
    assert row["resolution_value"] == 21.7
    assert row["decision_context_leakage_allowed"] is False
    assert row["resolution_source"] == "official_station_history"
    assert row["station_id"] == "LFPG"
    assert row["station_name"] == "Paris Charles de Gaulle"
    assert row["distance_to_threshold"] == -0.2
    assert row["distance_to_bin_center"] == -0.7
    assert row["official_source_available"] is True
    assert row["weather_context_available"] is True
    assert row["missing_reason"] is None
    assert payload["summary"]["with_weather_context"] == 1
    assert payload["summary"]["decision_context_leakage_allowed"] is False
    assert payload["paper_only"] is True
    assert payload["live_order_allowed"] is False


def test_missing_forecast_before_decision_is_explicit_unavailable() -> None:
    from weather_pm.weather_decision_context import enrich_decision_weather_context

    payload = enrich_decision_weather_context(_decision_payload(), {"forecasts": [_forecast_payload()["forecasts"][1]]}, None)

    row = payload["examples"][0]
    assert row["weather_context_available"] is False
    assert row["missing_reason"] == "no_forecast_at_or_before_decision"
    assert row["forecast_value_at_decision"] is None
    assert row["official_source_available"] is False
    assert row["decision_context_leakage_allowed"] is False


def test_sparse_forecast_mapping_matches_primary_key_market_id_and_city() -> None:
    from weather_pm.weather_decision_context import enrich_decision_weather_context

    decisions = {
        "examples": [
            {
                "id": "2112228",
                "market_id": "m-seoul-low-10",
                "primary_key": "2112228",
                "timestamp": "2026-05-01T09:30:00Z",
                "city": "Seoul",
                "date": "May 1",
                "market_type": "low_temperature",
                "threshold": 10.0,
            },
            {
                "id": "2112238",
                "market_id": "m-seoul-high-20",
                "timestamp": "2026-05-01T09:30:00Z",
                "city": "Seoul",
                "date": "May 1",
                "market_type": "high_temperature",
                "threshold": 20.0,
            },
            {
                "id": "2119999",
                "market_id": "m-toronto-high-19",
                "timestamp": "2026-04-28T09:30:00Z",
                "city": "Toronto",
                "date": "April 28",
                "market_type": "high_temperature",
                "threshold": 19.0,
            },
        ]
    }
    forecasts = {
        "2112228": {"forecast_high_c": 11.2, "freshness_minutes": 30, "source": "by_primary_key"},
        "m-seoul-high-20": {"forecast_high_c": 21.3, "freshness_minutes": 45, "source": "by_market_id"},
        "toronto": {"forecast_high_c": 20.0, "freshness_minutes": 60, "source": "by_city"},
    }

    payload = enrich_decision_weather_context(decisions, forecasts)

    assert payload["summary"]["with_weather_context"] == 3
    rows = payload["examples"]
    assert rows[0]["weather_context_available"] is True
    assert rows[0]["forecast_value_at_decision"] == 11.2
    assert rows[0]["forecast_source"] == "by_primary_key"
    assert rows[1]["forecast_value_at_decision"] == 21.3
    assert rows[1]["forecast_source"] == "by_market_id"
    assert rows[2]["forecast_value_at_decision"] == 20.0
    assert rows[2]["forecast_source"] == "by_city"
    assert all(row["decision_context_leakage_allowed"] is False for row in rows)


def test_cli_enrich_decision_weather_context_writes_artifact_and_compact_summary(tmp_path: Path) -> None:
    decisions_path = tmp_path / "decisions.json"
    forecasts_path = tmp_path / "forecasts.json"
    resolutions_path = tmp_path / "resolutions.json"
    output_path = tmp_path / "weather_context.json"
    decisions_path.write_text(json.dumps(_decision_payload()), encoding="utf-8")
    forecasts_path.write_text(json.dumps(_forecast_payload()), encoding="utf-8")
    resolutions_path.write_text(json.dumps(_resolution_payload()), encoding="utf-8")

    result = _run_weather_pm(
        "enrich-decision-weather-context",
        "--decision-dataset-json",
        str(decisions_path),
        "--forecast-snapshots-json",
        str(forecasts_path),
        "--resolution-sources-json",
        str(resolutions_path),
        "--output-json",
        str(output_path),
    )

    assert result["paper_only"] is True
    assert result["live_order_allowed"] is False
    assert result["examples"] == 1
    assert result["with_weather_context"] == 1
    assert result["decision_context_leakage_allowed"] is False
    artifact = json.loads(output_path.read_text(encoding="utf-8"))
    assert artifact["summary"]["with_weather_context"] == 1
    assert artifact["examples"][0]["forecast_value_at_decision"] == 20.8
