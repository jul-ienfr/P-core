from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from weather_pm.history_client import StationHistoryClient, build_station_history_bundle
from weather_pm.market_parser import parse_market_question
from weather_pm.resolution_parser import parse_resolution_metadata


class _FakeStationHistoryClient(StationHistoryClient):
    def __init__(self, payloads: list[dict[str, object]], *, now_utc: datetime | None = None) -> None:
        super().__init__(timeout=0.1, now_utc=now_utc)
        self.requested_urls: list[str] = []
        self._payloads = list(payloads)

    def _fetch_json(self, url: str) -> dict[str, object]:
        self.requested_urls.append(url)
        if not self._payloads:
            raise AssertionError(f"unexpected extra fetch for {url}")
        return self._payloads.pop(0)


def test_station_latest_client_reports_source_health_and_lag_metadata() -> None:
    structure = parse_market_question("Will the current temperature in Denver be 64F or higher on April 25?")
    resolution = parse_resolution_metadata(
        resolution_source="Resolution source: NOAA latest station observation for station KDEN",
        description="Official current temperature at Denver International Airport station KDEN.",
        rules="Source: https://api.weather.gov/stations/KDEN/observations/latest station KDEN.",
    )
    client = _FakeStationHistoryClient(
        [
            {
                "properties": {
                    "timestamp": "2026-04-25T21:53:00+00:00",
                    "temperature": {"value": 20.0, "unitCode": "wmoUnit:degC"},
                }
            }
        ],
        now_utc=datetime(2026, 4, 25, 22, 3, tzinfo=timezone.utc),
    )

    bundle = client.fetch_latest_bundle(structure, resolution)

    assert bundle.source_lag_seconds == 600
    assert bundle.source_health == "healthy"
    assert bundle.latency_diagnostics()["source_health"] == "healthy"
    assert bundle.to_dict()["summary"]["source_health"] == "healthy"


def test_build_station_history_bundle_fallback_exposes_reason_and_source_health() -> None:
    structure = parse_market_question("Will the highest temperature in Madrid be 28C or higher on April 25?")
    resolution = parse_resolution_metadata(
        resolution_source="Public website page: https://example.com/weather/history.html",
        description="This market resolves from the temperature table on the linked HTML page.",
        rules="Scrape the table on the source website after the daily data is posted.",
    )
    client = _FakeStationHistoryClient([{"content": "daily weather narrative without rows"}])

    bundle = build_station_history_bundle(structure, resolution, start_date="2026-04-25", end_date="2026-04-25", client=client)

    assert bundle.latency_tier == "unsupported"
    assert bundle.fallback_reason == "history_fetch_failed:ValueError"
    assert bundle.source_health == "failed"
    assert bundle.latency_diagnostics()["fallback_reason"] == "history_fetch_failed:ValueError"
    assert bundle.to_dict()["summary"] == {"fallback_reason": "history_fetch_failed:ValueError", "source_health": "failed"}


def test_hko_daily_extract_empty_official_payload_is_diagnosed_as_published_empty() -> None:
    structure = parse_market_question("Will the highest temperature in Hong Kong be 23C or higher on April 26?")
    resolution = parse_resolution_metadata(
        resolution_source="https://www.weather.gov.hk/en/cis/climat.htm",
        description="This market resolves according to the Daily Maximum Temperature at the Hong Kong Observatory.",
        rules="Use the official Hong Kong Observatory climate extract for the relevant day.",
    )
    client = _FakeStationHistoryClient(
        [
            {
                "type": ["Daily Maximum Temperature (°C) at the Hong Kong Observatory"],
                "fields": ["年/Year", "月/Month", "日/Day", "數值/Value", "數據完整性/data Completeness"],
                "data": [],
            }
        ]
    )

    bundle = build_station_history_bundle(structure, resolution, start_date="2026-04-26", end_date="2026-04-26", client=client)

    assert bundle.latency_tier == "direct_history"
    assert bundle.source_health == "published_empty"
    assert bundle.fallback_reason == "official_source_empty_payload"
    assert bundle.latency_diagnostics()["fallback_reason"] == "official_source_empty_payload"
    assert bundle.to_dict()["summary"] == {"fallback_reason": "official_source_empty_payload", "source_health": "published_empty"}


def test_hko_daily_extract_parses_list_rows_from_official_opendata_payload() -> None:
    structure = parse_market_question("Will the highest temperature in Hong Kong be 23C or higher on April 26?")
    resolution = parse_resolution_metadata(
        resolution_source="https://www.weather.gov.hk/en/cis/climat.htm",
        description="This market resolves according to the Daily Maximum Temperature at the Hong Kong Observatory.",
        rules="Use the official Hong Kong Observatory climate extract for the relevant day.",
    )
    client = _FakeStationHistoryClient(
        [
            {
                "type": ["Daily Maximum Temperature (°C) at the Hong Kong Observatory"],
                "fields": ["年/Year", "月/Month", "日/Day", "數值/Value", "數據完整性/data Completeness"],
                "data": [["2026", "4", "25", "22.8", "C"], ["2026", "4", "26", "24.6", "C"]],
            }
        ]
    )

    bundle = build_station_history_bundle(structure, resolution, start_date="2026-04-26", end_date="2026-04-26", client=client)

    assert client.requested_urls == [
        "https://data.weather.gov.hk/weatherAPI/opendata/opendata.php?dataType=CLMMAXT&rformat=json&station=HKO&year=2026&month=4"
    ]
    assert bundle.source_provider == "hong_kong_observatory"
    assert bundle.station_code == "HKO"
    assert bundle.latency_tier == "direct_history"
    assert bundle.source_health == "healthy"
    assert bundle.latest() is not None
    assert bundle.latest().timestamp == "2026-04-26"
    assert bundle.latest().value == 24.6
    assert bundle.to_dict()["summary"]["max"] == 24.6
