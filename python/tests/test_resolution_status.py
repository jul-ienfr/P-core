from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

import weather_pm.cli as weather_cli
from weather_pm.models import StationHistoryBundle, StationHistoryPoint


class FakeResolutionStatusClient:
    def __init__(self, *, latest: StationHistoryBundle, history: StationHistoryBundle) -> None:
        self.latest = latest
        self.history = history
        self.latest_calls: list[tuple[str, str]] = []
        self.history_calls: list[tuple[str, str, str, str]] = []

    def fetch_latest_bundle(self, structure, resolution):
        self.latest_calls.append((structure.city, resolution.provider))
        return self.latest

    def fetch_history_bundle(self, structure, resolution, *, start_date: str, end_date: str):
        self.history_calls.append((structure.city, resolution.provider, start_date, end_date))
        return self.history


def _hko_market() -> dict[str, object]:
    return {
        "id": "hko-high-29",
        "question": "Will the highest temperature in Hong Kong be 29°C or higher on April 25?",
        "resolution_source": "https://www.weather.gov.hk/en/cis/climat.htm",
        "description": "This market resolves to the highest temperature recorded by the Hong Kong Observatory on 25 Apr '26.",
        "rules": "This market resolves based on the finalized Hong Kong Observatory Daily Extract.",
    }


def test_resolution_status_reports_provisional_latest_until_official_daily_extract_is_available() -> None:
    latest = StationHistoryBundle(
        source_provider="hong_kong_observatory",
        station_code="HKO",
        source_url="https://data.weather.gov.hk/weatherAPI/opendata/weather.php?dataType=rhrread&lang=en",
        latency_tier="direct_latest",
        points=[StationHistoryPoint(timestamp="2026-04-25T15:45:00+08:00", value=29.2, unit="c")],
        summary={"min": 29.2, "max": 29.2, "mean": 29.2},
    )
    official_empty = StationHistoryBundle(
        source_provider="hong_kong_observatory",
        station_code="HKO",
        source_url="https://data.weather.gov.hk/weatherAPI/opendata/opendata.php?dataType=CLMMAXT&rformat=json&station=HKO&year=2026&month=4",
        latency_tier="direct_history",
        points=[],
        summary={},
    )
    client = FakeResolutionStatusClient(latest=latest, history=official_empty)

    with patch("weather_pm.cli.get_market_by_id", return_value=_hko_market()):
        payload = weather_cli.resolution_status_for_market_id(
            "hko-high-29",
            source="live",
            date="2026-04-25",
            client=client,
        )

    assert client.latest_calls == [("Hong Kong", "hong_kong_observatory")]
    assert client.history_calls == [("Hong Kong", "hong_kong_observatory", "2026-04-25", "2026-04-25")]
    assert payload["source_route"]["latest_url"] == "https://data.weather.gov.hk/weatherAPI/opendata/weather.php?dataType=rhrread&lang=en"
    assert payload["source_route"]["history_url"] == "https://data.weather.gov.hk/weatherAPI/opendata/opendata.php?dataType=CLMMAXT&rformat=json&station=HKO&year=2026&month=4"
    assert payload["latest_direct"] == {
        "available": True,
        "value": 29.2,
        "timestamp": "2026-04-25T15:45:00+08:00",
        "latency_tier": "direct_latest",
        "source_url": "https://data.weather.gov.hk/weatherAPI/opendata/weather.php?dataType=rhrread&lang=en",
        "polling_focus": "hko_current_weather_api",
        "expected_lag_seconds": None,
    }
    assert payload["official_daily_extract"] == {
        "available": False,
        "value": None,
        "timestamp": None,
        "latency_tier": "direct_history",
        "source_url": "https://data.weather.gov.hk/weatherAPI/opendata/opendata.php?dataType=CLMMAXT&rformat=json&station=HKO&year=2026&month=4",
        "polling_focus": "hko_official_daily_extract",
        "expected_lag_seconds": 86400,
    }
    assert payload["provisional_outcome"] == "yes"
    assert payload["confirmed_outcome"] == "pending"
    assert payload["action_operator"] == "monitor_until_official_daily_extract"
    assert payload["latency"]["latest"]["polling_focus"] == "hko_current_weather_api"
    assert payload["latency"]["official"]["polling_focus"] == "hko_official_daily_extract"
    assert payload["latency"]["official"]["expected_lag_seconds"] == 86400


def test_resolution_status_reports_source_lag_seconds_for_latest_and_official_points() -> None:
    latest = StationHistoryBundle(
        source_provider="hong_kong_observatory",
        station_code="HKO",
        source_url="latest-url",
        latency_tier="direct_latest",
        points=[StationHistoryPoint(timestamp="2026-04-25T15:45:00+08:00", value=29.2, unit="c")],
        summary={"min": 29.2, "max": 29.2, "mean": 29.2},
    )
    official = StationHistoryBundle(
        source_provider="hong_kong_observatory",
        station_code="HKO",
        source_url="official-url",
        latency_tier="direct_history",
        points=[StationHistoryPoint(timestamp="2026-04-25", value=29.6, unit="c")],
        summary={"min": 29.6, "max": 29.6, "mean": 29.6},
    )

    with patch("weather_pm.cli.get_market_by_id", return_value=_hko_market()), patch(
        "weather_pm.cli._utc_now", return_value=datetime(2026, 4, 25, 8, 0, tzinfo=timezone.utc)
    ):
        payload = weather_cli.resolution_status_for_market_id(
            "hko-high-29",
            source="live",
            date="2026-04-25",
            client=FakeResolutionStatusClient(latest=latest, history=official),
        )

    assert payload["latest_direct"]["source_lag_seconds"] == 900
    assert payload["official_daily_extract"]["source_lag_seconds"] == 28800
    assert payload["latency"]["latest"]["source_lag_seconds"] == 900
    assert payload["latency"]["official"]["source_lag_seconds"] == 28800



def test_resolution_status_confirms_outcome_from_official_daily_extract_when_published() -> None:
    latest = StationHistoryBundle(
        source_provider="hong_kong_observatory",
        station_code="HKO",
        source_url="latest-url",
        latency_tier="direct_latest",
        points=[StationHistoryPoint(timestamp="2026-04-25T12:00:00+08:00", value=28.7, unit="c")],
        summary={"min": 28.7, "max": 28.7, "mean": 28.7},
    )
    official = StationHistoryBundle(
        source_provider="hong_kong_observatory",
        station_code="HKO",
        source_url="official-url",
        latency_tier="direct_history",
        points=[StationHistoryPoint(timestamp="2026-04-25", value=29.6, unit="c")],
        summary={"min": 29.6, "max": 29.6, "mean": 29.6},
    )

    with patch("weather_pm.cli.get_market_by_id", return_value=_hko_market()):
        payload = weather_cli.resolution_status_for_market_id(
            "hko-high-29",
            source="live",
            date="2026-04-25",
            client=FakeResolutionStatusClient(latest=latest, history=official),
        )

    assert payload["latest_direct"]["available"] is True
    assert payload["official_daily_extract"]["available"] is True
    assert payload["official_daily_extract"]["value"] == 29.6
    assert payload["provisional_outcome"] == "no"
    assert payload["confirmed_outcome"] == "yes"
    assert payload["action_operator"] == "resolution_confirmed"


def test_resolution_status_parser_requires_date() -> None:
    parser = weather_cli.build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["resolution-status", "--market-id", "hko-high-29", "--source", "live"])

    args = parser.parse_args(["resolution-status", "--market-id", "hko-high-29", "--source", "live", "--date", "2026-04-25"])
    assert args.command == "resolution-status"
    assert args.date == "2026-04-25"
