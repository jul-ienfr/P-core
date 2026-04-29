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
