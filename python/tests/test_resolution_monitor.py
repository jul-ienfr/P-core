from __future__ import annotations

import json
from pathlib import Path


def _status_payload(*, confirmed: str = "pending") -> dict[str, object]:
    return {
        "market_id": "hko-high-29",
        "source": "live",
        "date": "2026-04-25",
        "latest_direct": {
            "available": True,
            "value": 29.2,
            "timestamp": "2026-04-25T15:45:00+08:00",
            "latency_tier": "direct_latest",
        },
        "official_daily_extract": {
            "available": confirmed != "pending",
            "value": 29.6 if confirmed != "pending" else None,
            "timestamp": "2026-04-25" if confirmed != "pending" else None,
            "latency_tier": "direct_history",
        },
        "provisional_outcome": "yes",
        "confirmed_outcome": confirmed,
        "action_operator": "resolution_confirmed" if confirmed != "pending" else "monitor_until_official_daily_extract",
        "latency": {
            "latest": {"polling_focus": "hko_current_weather_api"},
            "official": {"polling_focus": "hko_official_daily_extract", "expected_lag_seconds": 86400},
        },
        "source_route": {
            "provider": "hong_kong_observatory",
            "station_code": "HKO",
            "latest_url": "https://data.weather.gov.hk/weatherAPI/opendata/weather.php?dataType=rhrread&lang=en",
            "history_url": "https://data.weather.gov.hk/weatherAPI/opendata/opendata.php?dataType=CLMMAXT&rformat=json&station=HKO&year=2026&month=4",
            "polling_focus": "hko_official_daily_extract",
        },
    }


def test_write_paper_resolution_monitor_persists_raw_status_and_operator_markdown(tmp_path: Path) -> None:
    from weather_pm.resolution_monitor import write_paper_resolution_monitor

    calls: list[tuple[str, str, str]] = []

    def fake_status(market_id: str, *, source: str, date: str):
        calls.append((market_id, source, date))
        return _status_payload()

    payload = write_paper_resolution_monitor(
        market_id="hko-high-29",
        source="live",
        settlement_date="2026-04-25",
        paper_side="yes",
        paper_notional_usd=5.0,
        paper_shares=17.24,
        output_dir=tmp_path,
        status_fetcher=fake_status,
    )

    assert calls == [("hko-high-29", "live", "2026-04-25")]
    assert payload["mode"] == "paper_only"
    assert payload["should_repoll"] is True
    assert payload["cron_repoll"]["schedule"] == "every 2h"
    assert payload["cron_repoll"]["repeat"] == 24

    raw_path = Path(str(payload["artifacts"]["raw_status_json"]))
    monitor_path = Path(str(payload["artifacts"]["operator_monitor_md"]))
    assert raw_path.exists()
    assert monitor_path.exists()
    raw = json.loads(raw_path.read_text())
    assert raw["market_id"] == "hko-high-29"
    assert raw["paper_trade"] == {"side": "yes", "notional_usd": 5.0, "shares": 17.24}

    markdown = monitor_path.read_text()
    assert "Mode: paper only" in markdown
    assert "Market: hko-high-29" in markdown
    assert "Paper side: yes" in markdown
    assert "Latest direct: available=True value=29.2" in markdown
    assert "Official daily extract: available=False value=None" in markdown
    assert "Provisional outcome: yes" in markdown
    assert "Confirmed outcome: pending" in markdown
    assert "Operator action: monitor_until_official_daily_extract" in markdown
    assert "Official polling focus: hko_official_daily_extract" in markdown


def test_write_paper_resolution_monitor_stops_repoll_when_confirmed(tmp_path: Path) -> None:
    from weather_pm.resolution_monitor import write_paper_resolution_monitor

    payload = write_paper_resolution_monitor(
        market_id="hko-high-29",
        source="live",
        settlement_date="2026-04-25",
        paper_side="yes",
        paper_notional_usd=5.0,
        paper_shares=17.24,
        output_dir=tmp_path,
        status_fetcher=lambda market_id, *, source, date: _status_payload(confirmed="yes"),
    )

    assert payload["should_repoll"] is False
    assert payload["status"]["confirmed_outcome"] == "yes"
    assert payload["cron_repoll"] is None


def test_monitor_paper_resolution_parser_accepts_trade_context() -> None:
    import weather_pm.cli as weather_cli

    parser = weather_cli.build_parser()
    args = parser.parse_args(
        [
            "monitor-paper-resolution",
            "--market-id",
            "hko-high-29",
            "--source",
            "live",
            "--date",
            "2026-04-25",
            "--paper-side",
            "yes",
            "--paper-notional-usd",
            "5",
            "--paper-shares",
            "17.24",
            "--output-dir",
            "/tmp/weather-monitor",
        ]
    )

    assert args.command == "monitor-paper-resolution"
    assert args.date == "2026-04-25"
    assert args.paper_side == "yes"
    assert args.paper_notional_usd == 5.0
    assert args.paper_shares == 17.24
