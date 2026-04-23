from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from unittest.mock import patch

import weather_pm.cli as weather_cli


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    project_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(project_root / "src")
    return subprocess.run(
        [sys.executable, "-m", "weather_pm.cli", *args],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def test_parse_market_command_outputs_parsed_json() -> None:
    result = _run_cli(
        "parse-market",
        "--question",
        "Will the highest temperature in Denver be 64F or higher?",
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["city"] == "Denver"
    assert payload["measurement_kind"] == "high"
    assert payload["is_threshold"] is True
    assert payload["threshold_direction"] == "higher"


def test_score_market_command_outputs_score_and_decision() -> None:
    result = _run_cli(
        "score-market",
        "--question",
        "Will the highest temperature in Denver be 64F or higher?",
        "--yes-price",
        "0.43",
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["score"]["grade"] in {"A", "B", "C", "D"}
    assert payload["decision"]["status"] in {"trade", "trade_small", "watchlist", "skip"}
    assert payload["resolution"]["provider"] == "wunderground"


def test_score_market_command_marks_ambiguous_resolution_for_manual_review() -> None:
    result = _run_cli(
        "score-market",
        "--question",
        "Will the highest temperature in Denver be 64F or higher?",
        "--yes-price",
        "0.43",
        "--resolution-source",
        "Resolution source: local weather blog",
        "--description",
        "This market resolves from a public blog weather report.",
        "--rules",
        "Unofficial source may be used.",
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["resolution"]["manual_review_needed"] is True
    assert payload["score"]["total_score"] <= 59.0
    assert payload["decision"]["status"] in {"watchlist", "skip"}


def test_score_market_command_live_event_extracts_clean_resolution_metadata() -> None:
    event_market = {
        "id": "404359",
        "question": "Lowest temperature in Miami on April 23?",
        "yes_price": 0.0,
        "best_bid": 0.0,
        "best_ask": 0.0,
        "volume": 13146.135531999998,
        "hours_to_resolution": 12.0,
        "resolution_source": "https://www.wunderground.com/history/daily/us/fl/miami/KMIA",
        "description": (
            "This market will resolve to the temperature range that contains the lowest "
            "temperature recorded at the Miami Intl Airport Station in degrees Fahrenheit "
            "on 23 Apr '26."
        ),
        "rules": (
            "This market resolves based on the final daily observation published at the "
            "resolution source."
        ),
    }

    with patch("weather_pm.cli.get_market_by_id", return_value=event_market), patch(
        "weather_pm.cli.list_weather_markets", return_value=[event_market]
    ):
        payload = weather_cli._score_market_from_market_id("404359", source="live")

    assert payload["resolution"]["provider"] == "wunderground"
    assert payload["resolution"]["station_code"] == "KMIA"
    assert payload["resolution"]["station_name"] == "Miami Intl Airport"
    assert payload["resolution"]["station_type"] == "airport"


def test_build_parser_accepts_source_argument_for_fetch_event_book_and_score_commands() -> None:
    parser = weather_cli.build_parser()

    fetch_args = parser.parse_args(["fetch-markets", "--source", "live", "--limit", "5"])
    event_args = parser.parse_args(["fetch-event-book", "--market-id", "event-123", "--source", "live"])
    score_args = parser.parse_args(["score-market", "--market-id", "abc", "--source", "live"])

    assert fetch_args.source == "live"
    assert fetch_args.limit == 5
    assert event_args.source == "live"
    assert event_args.market_id == "event-123"
    assert score_args.source == "live"
    assert score_args.market_id == "abc"


def test_fetch_markets_command_keeps_stable_json_shape_for_live_source() -> None:
    project_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(project_root / "src")
    inline = """
import io
import json
import sys
from contextlib import redirect_stdout
from unittest.mock import patch

import weather_pm.cli as cli

with patch('weather_pm.cli.list_weather_markets', return_value=[{
    'id': 'live-1',
    'category': 'weather',
    'question': 'Will the highest temperature in Denver be 64F or higher?',
    'yes_price': 0.44,
    'best_bid': 0.43,
    'best_ask': 0.45,
    'volume': 12345.6,
    'hours_to_resolution': 12.0,
    'resolution_source': 'NOAA',
    'description': 'desc',
    'rules': 'rules',
}]):
    sys.argv = ['weather_pm.cli', 'fetch-markets', '--source', 'live', '--limit', '1']
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = cli.main()
    payload = json.loads(buffer.getvalue())
    assert code == 0
    assert isinstance(payload, list)
    assert payload[0]['id'] == 'live-1'
    assert payload[0]['spread'] == 0.02
    assert payload[0]['volume_usd'] == 12345.6
"""
    result = subprocess.run(
        [sys.executable, "-c", inline],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_fetch_event_book_command_outputs_event_and_normalized_child_markets() -> None:
    event_book = {
        "id": "event-123",
        "category": "weather",
        "question": "Denver daily highest temperature event",
        "resolution_source": "NOAA",
        "description": "desc",
        "rules": "rules",
        "markets": [
            {
                "id": "live-1",
                "category": "weather",
                "question": "Will the highest temperature in Denver be 64F or higher?",
                "yes_price": 0.44,
                "best_bid": 0.43,
                "best_ask": 0.45,
                "volume": 12345.6,
                "hours_to_resolution": 12.0,
                "resolution_source": "NOAA",
                "description": "desc",
                "rules": "rules",
            }
        ],
    }

    with patch("weather_pm.cli.get_event_book_by_id", return_value=event_book):
        parser = weather_cli.build_parser()
        args = parser.parse_args(["fetch-event-book", "--market-id", "event-123", "--source", "live"])
        assert args.market_id == "event-123"
        assert args.source == "live"

        result = weather_cli._normalize_event_book_payload(event_book)

    assert result["event"]["id"] == "event-123"
    assert result["event"]["rules"] == "rules"
    assert result["markets"][0]["id"] == "live-1"
    assert result["markets"][0]["spread"] == 0.02
    assert result["markets"][0]["volume_usd"] == 12345.6


def test_score_market_command_with_live_market_id_supports_event_style_highest_temperature_resolution_via_event_payload() -> None:
    highest_event_market = {
        "id": "322442",
        "question": "Highest temperature in Hong Kong on April 1?",
        "yes_price": 0.0,
        "best_bid": 0.0,
        "best_ask": 0.0,
        "volume": 221180.29265700004,
        "hours_to_resolution": 12.0,
        "resolution_source": "https://www.weather.gov.hk/en/cis/climat.htm",
        "description": (
            "This market will resolve to the temperature range that contains the highest "
            "temperature recorded by the Hong Kong Observatory in degrees Celsius on 1 Apr '26."
        ),
        "rules": (
            "This market resolves based on the finalized Hong Kong Observatory Daily Extract."
        ),
    }
    neighboring_event_market = {
        "id": "322481",
        "question": "Highest temperature in Hong Kong on April 2?",
        "yes_price": 0.0,
        "best_bid": 0.0,
        "best_ask": 0.0,
        "volume": 289784.951444,
        "hours_to_resolution": 36.0,
        "resolution_source": "https://www.weather.gov.hk/en/cis/climat.htm",
        "description": (
            "This market will resolve to the temperature range that contains the highest "
            "temperature recorded by the Hong Kong Observatory in degrees Celsius on 2 Apr '26."
        ),
        "rules": "Source: finalized Hong Kong Observatory Daily Extract.",
    }

    with patch("weather_pm.cli.get_market_by_id", return_value=highest_event_market), patch(
        "weather_pm.cli.list_weather_markets", return_value=[highest_event_market, neighboring_event_market]
    ):
        payload = weather_cli._score_market_from_market_id("322442", source="live")

    assert payload["market"]["city"] == "Hong Kong"
    assert payload["market"]["measurement_kind"] == "high"
    assert payload["market"]["unit"] == "c"
    assert payload["market"]["is_exact_bin"] is True
    assert payload["market"]["date_local"] == "April 1"
    assert payload["resolution"]["provider"] == "hong_kong_observatory"
    assert payload["resolution"]["station_name"] == "Hong Kong Observatory"
    assert payload["resolution"]["station_type"] == "station"
    assert payload["resolution"]["manual_review_needed"] is False
    assert payload["neighbors"]["neighbor_market_count"] >= 1
    assert payload["decision"]["status"] in {"trade", "trade_small", "watchlist", "skip"}
