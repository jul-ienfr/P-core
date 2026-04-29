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


def test_official_observation_backfill_accepts_contract_and_preserves_guards(tmp_path: Path) -> None:
    from weather_pm.official_observation_backfill import build_official_observation_backfill

    source = {
        "observations": [
            {
                "market_id": "m-hko-high-30",
                "station_id": "HKO",
                "observation_value": 29.6,
                "observation_timestamp": "2026-04-26T23:59:00+08:00",
                "resolution_timestamp": "2026-04-27T09:00:00+08:00",
                "resolution_source": "hong_kong_observatory_official_daily_extract",
            }
        ]
    }

    artifact = build_official_observation_backfill(source)

    assert artifact["paper_only"] is True
    assert artifact["live_order_allowed"] is False
    assert artifact["summary"] == {"observations": 1, "official_source_available": True}
    assert artifact["resolutions"] == [
        {
            "market_id": "m-hko-high-30",
            "station_id": "HKO",
            "observation_value": 29.6,
            "observation_timestamp": "2026-04-26T23:59:00+08:00",
            "resolution_timestamp": "2026-04-27T09:00:00+08:00",
            "resolution_source": "hong_kong_observatory_official_daily_extract",
            "official_source_available": True,
        }
    ]

    input_path = tmp_path / "official.json"
    output_path = tmp_path / "backfill.json"
    input_path.write_text(json.dumps(source), encoding="utf-8")

    summary = _run_weather_pm(
        "official-observation-backfill",
        "--input-json",
        str(input_path),
        "--output-json",
        str(output_path),
    )

    assert summary == {"observations": 1, "official_source_available": True}
    written = json.loads(output_path.read_text(encoding="utf-8"))
    assert written["paper_only"] is True
    assert written["live_order_allowed"] is False
    assert written["resolutions"][0]["station_id"] == "HKO"


def test_official_observation_backfill_matches_local_observations_to_markets_by_city_date_type() -> None:
    from weather_pm.official_observation_backfill import build_official_observation_backfill

    payload = {
        "markets": [
            {
                "market_id": "toronto-high-apr30",
                "slug": "will-toronto-high-be-15c-or-above-april-30",
                "condition_id": "0xtoronto",
                "city": "Toronto",
                "date": "2026-04-30",
                "market_type": "high_temperature",
                "question": "Will the high temperature in Toronto be 15°C or above on April 30?",
            }
        ],
        "observations": [
            {
                "city": "toronto",
                "date": "2026-04-30",
                "market_type": "high_temperature",
                "station_id": "CA006158355",
                "station_name": "TORONTO CITY CENTRE",
                "observation_value": "16.2",
                "observation_unit": "c",
                "observation_timestamp": "2026-04-30T23:59:00-04:00",
                "resolution_timestamp": "2026-05-01T08:00:00-04:00",
                "resolution_source": "environment_canada_daily_climate_observations",
                "resolution_source_url": "file://fixtures/toronto-2026-04-30.json",
            }
        ],
    }

    artifact = build_official_observation_backfill(payload)

    assert artifact["paper_only"] is True
    assert artifact["live_order_allowed"] is False
    assert artifact["summary"] == {
        "observations": 1,
        "official_source_available": True,
        "markets": 1,
        "matched_markets": 1,
        "unmatched_markets": 0,
        "unmatched_observations": 0,
    }
    assert artifact["diagnostics"] == []
    assert artifact["resolutions"] == [
        {
            "market_id": "toronto-high-apr30",
            "slug": "will-toronto-high-be-15c-or-above-april-30",
            "condition_id": "0xtoronto",
            "city": "Toronto",
            "date": "2026-04-30",
            "market_type": "high_temperature",
            "question": "Will the high temperature in Toronto be 15°C or above on April 30?",
            "station_id": "CA006158355",
            "station_name": "TORONTO CITY CENTRE",
            "observation_value": 16.2,
            "observation_unit": "c",
            "observation_timestamp": "2026-04-30T23:59:00-04:00",
            "resolution_timestamp": "2026-05-01T08:00:00-04:00",
            "resolution_source": "environment_canada_daily_climate_observations",
            "resolution_source_url": "file://fixtures/toronto-2026-04-30.json",
            "official_source_available": True,
        }
    ]


def test_official_observation_backfill_matches_by_identifier_and_reports_unmatched_without_inventing() -> None:
    from weather_pm.official_observation_backfill import build_official_observation_backfill

    payload = {
        "markets": [
            {"market_id": "matched-market", "condition_id": "0xabc", "slug": "matched", "city": "Toronto", "date": "2026-04-30", "market_type": "rain"},
            {"market_id": "missing-official", "city": "Toronto", "date": "2026-05-01", "market_type": "rain"},
        ],
        "observations": [
            {
                "condition_id": "0xabc",
                "station_id": "YYZ",
                "observation_value": 0,
                "observation_unit": "mm",
                "observation_timestamp": "2026-04-30T23:59:00-04:00",
                "resolution_timestamp": "2026-05-01T08:00:00-04:00",
                "resolution_source": "official_local_fixture",
            },
            {
                "market_id": "orphan-observation",
                "station_id": "YYZ",
                "observation_value": 1.2,
                "observation_timestamp": "2026-05-02T23:59:00-04:00",
                "resolution_timestamp": "2026-05-03T08:00:00-04:00",
                "resolution_source": "official_local_fixture",
            },
        ],
    }

    artifact = build_official_observation_backfill(payload)

    assert [row["market_id"] for row in artifact["resolutions"]] == ["matched-market"]
    assert artifact["summary"]["matched_markets"] == 1
    assert artifact["summary"]["unmatched_markets"] == 1
    assert artifact["summary"]["unmatched_observations"] == 1
    assert artifact["diagnostics"] == [
        {
            "level": "warning",
            "code": "unmatched_market",
            "market_id": "missing-official",
            "message": "no local official observation matched market identifiers or city/date/market_type",
        },
        {
            "level": "warning",
            "code": "unmatched_observation",
            "observation_index": 1,
            "market_id": "orphan-observation",
            "message": "official observation was not attached to any supplied market",
        },
    ]


def test_official_observation_backfill_rejects_ambiguous_city_date_type_match() -> None:
    from weather_pm.official_observation_backfill import build_official_observation_backfill

    payload = {
        "markets": [{"market_id": "toronto-high", "city": "Toronto", "date": "2026-04-30", "market_type": "high_temperature"}],
        "observations": [
            {
                "city": "Toronto",
                "date": "2026-04-30",
                "market_type": "high_temperature",
                "station_id": "A",
                "observation_value": 16.2,
                "observation_timestamp": "2026-04-30T23:59:00-04:00",
                "resolution_timestamp": "2026-05-01T08:00:00-04:00",
                "resolution_source": "official_a",
            },
            {
                "city": "Toronto",
                "date": "2026-04-30",
                "market_type": "high_temperature",
                "station_id": "B",
                "observation_value": 16.4,
                "observation_timestamp": "2026-04-30T23:59:00-04:00",
                "resolution_timestamp": "2026-05-01T08:00:00-04:00",
                "resolution_source": "official_b",
            },
        ],
    }

    try:
        build_official_observation_backfill(payload)
    except ValueError as exc:
        assert "ambiguous official observations" in str(exc)
        assert "toronto-high" in str(exc)
    else:  # pragma: no cover - assertion clarity
        raise AssertionError("expected ambiguous local observations to be rejected")


def test_official_observation_backfill_rejects_proxy_without_official_observation() -> None:
    from weather_pm.official_observation_backfill import build_official_observation_backfill

    proxy_payload = {
        "resolutions": [
            {
                "market_id": "m-proxy",
                "source": "gamma_closed_outcomePrices_proxy",
                "observed_value": 0.0,
                "resolution_timestamp": "2026-04-27T00:00:00Z",
            }
        ]
    }

    try:
        build_official_observation_backfill(proxy_payload)
    except ValueError as exc:
        assert "observation_value" in str(exc)
    else:  # pragma: no cover - assertion clarity
        raise AssertionError("expected proxy-only payload to be rejected")


def test_official_observation_backfill_requires_core_fields() -> None:
    from weather_pm.official_observation_backfill import build_official_observation_backfill

    try:
        build_official_observation_backfill({"observations": [{"market_id": "missing-fields"}]})
    except ValueError as exc:
        message = str(exc)
        assert "station_id" in message
        assert "observation_timestamp" in message
        assert "resolution_timestamp" in message
    else:  # pragma: no cover - assertion clarity
        raise AssertionError("expected missing required fields to be rejected")
