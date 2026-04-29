from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from weather_pm.account_trades import (
    backfill_account_trades_from_followlist,
    build_historical_weather_trade_profile,
    classify_weather_trade,
    import_account_trades,
)
from weather_pm.cli import build_parser


TRADE_ROWS = [
    {
        "transactionHash": "0xaaa",
        "proxyWallet": "0xCold",
        "userName": "ColdMath",
        "title": "Will the highest temperature in London be exactly 20°C on April 25?",
        "slug": "london-high-temp-20c-apr-25",
        "side": "BUY",
        "outcome": "Yes",
        "price": "0.31",
        "size": "120",
        "timestamp": "2026-04-24T10:15:00Z",
    },
    {
        "transactionHash": "0xbbb",
        "proxyWallet": "0xCold",
        "userName": "ColdMath",
        "title": "Will the highest temperature in London be 21°C or higher on April 25?",
        "slug": "london-high-temp-21c-or-higher-apr-25",
        "side": "SELL",
        "outcome": "No",
        "price": "0.82",
        "size": "20",
        "timestamp": "2026-04-24T16:45:00Z",
    },
    {
        "transactionHash": "0xccc",
        "proxyWallet": "0xMacro",
        "userName": "MacroWeather",
        "title": "Will there be more than 25 named storms during Atlantic Hurricane Season?",
        "slug": "atlantic-hurricane-season-named-storms",
        "side": "BUY",
        "outcome": "Yes",
        "price": "0.47",
        "size": "80",
        "timestamp": "2026-04-22T08:00:00Z",
    },
    {
        "transactionHash": "0xddd",
        "proxyWallet": "0xCold",
        "userName": "ColdMath",
        "title": "Will Arsenal win the Premier League?",
        "slug": "arsenal-premier-league",
        "side": "BUY",
        "outcome": "Yes",
        "price": "0.12",
        "size": "50",
        "timestamp": "2026-04-23T10:00:00Z",
    },
]


def test_classify_weather_trade_extracts_weather_market_type_and_notional() -> None:
    trade = classify_weather_trade(TRADE_ROWS[0])

    assert trade.trade_id == "0xaaa"
    assert trade.wallet == "0xCold"
    assert trade.handle == "ColdMath"
    assert trade.is_weather is True
    assert trade.weather_market_type == "exact_value"
    assert trade.city == "London"
    assert trade.side == "BUY"
    assert trade.outcome == "Yes"
    assert trade.notional_usd == 37.2


def test_import_account_trades_filters_weather_and_builds_historical_profile(tmp_path: Path) -> None:
    input_json = tmp_path / "trades.json"
    trades_out = tmp_path / "weather_trades.json"
    profiles_out = tmp_path / "profiles.json"
    input_json.write_text(json.dumps({"trades": TRADE_ROWS}), encoding="utf-8")

    result = import_account_trades(input_json, trades_out=trades_out, profiles_out=profiles_out)

    assert result["summary"] == {
        "input_trades": 4,
        "weather_trades": 3,
        "accounts": 2,
        "paper_only": True,
        "live_order_allowed": False,
    }
    weather_trades = json.loads(trades_out.read_text(encoding="utf-8"))["trades"]
    assert [row["trade_id"] for row in weather_trades] == ["0xaaa", "0xbbb", "0xccc"]
    profiles = json.loads(profiles_out.read_text(encoding="utf-8"))["profiles"]
    cold = profiles[0]
    assert cold["handle"] == "ColdMath"
    assert cold["trade_count"] == 2
    assert cold["weather_market_type_counts"] == {"exact_value": 1, "threshold": 1}
    assert cold["primary_archetype"] == "event_surface_grid_specialist"
    assert "learn_timing_and_sizing" in cold["recommended_uses"]


def test_build_historical_weather_trade_profile_marks_macro_weather_accounts() -> None:
    trades = [classify_weather_trade(TRADE_ROWS[2])]

    profile = build_historical_weather_trade_profile("0xMacro", trades)

    assert profile["handle"] == "MacroWeather"
    assert profile["primary_archetype"] == "macro_weather_event_trader"
    assert profile["weather_market_type_counts"] == {"macro_weather": 1}
    assert profile["avg_trade_notional_usd"] == 37.6


def test_backfill_account_trades_from_followlist_fetches_public_trades_and_writes_artifact(tmp_path: Path) -> None:
    followlist = tmp_path / "followlist.csv"
    out_json = tmp_path / "raw_account_trades.json"
    followlist.write_text(
        "wallet,handle,bucket,rank,score\n"
        "0xCold,ColdMath,weather,1,98.5\n"
        "0xMacro,MacroWeather,weather,2,77\n"
        "0xIgnored,Ignored,weather,3,1\n",
        encoding="utf-8",
    )
    calls: list[dict[str, object]] = []

    def fake_http_get(url: str, params: dict[str, object]) -> list[dict[str, object]]:
        calls.append({"url": url, "params": dict(params)})
        if params["user"] == "0xCold":
            return [{"transactionHash": "0xaaa", "proxyWallet": "0xCold"}]
        return {"data": [{"transactionHash": "0xbbb", "proxyWallet": "0xMacro"}]}  # type: ignore[return-value]

    result = backfill_account_trades_from_followlist(
        followlist,
        out_json,
        limit_accounts=2,
        trades_per_account=50,
        http_get=fake_http_get,
    )

    assert [call["url"] for call in calls] == ["https://data-api.polymarket.com/trades"] * 2
    assert [call["params"] for call in calls] == [
        {"user": "0xCold", "limit": 50},
        {"user": "0xMacro", "limit": 50},
    ]
    assert result["summary"] == {
        "accounts_requested": 2,
        "accounts_succeeded": 2,
        "accounts_failed": 0,
        "raw_trades": 2,
        "paper_only": True,
        "live_order_allowed": False,
    }
    artifact = json.loads(out_json.read_text(encoding="utf-8"))
    assert artifact["source"] == "polymarket_data_api_account_trades"
    assert artifact["paper_only"] is True
    assert artifact["live_order_allowed"] is False
    assert [account["wallet"] for account in artifact["accounts"]] == ["0xCold", "0xMacro"]
    assert artifact["accounts"][0]["bucket"] == "weather"
    assert artifact["accounts"][0]["rank"] == "1"
    assert artifact["accounts"][0]["score"] == "98.5"
    assert artifact["raw_trades"] == [
        {"transactionHash": "0xaaa", "proxyWallet": "0xCold"},
        {"transactionHash": "0xbbb", "proxyWallet": "0xMacro"},
    ]
    assert artifact["summary"]["per_account_counts"] == {"0xCold": 1, "0xMacro": 1}
    assert artifact["summary"]["errors"] == []


def test_backfill_account_trades_from_followlist_records_account_errors_without_aborting(tmp_path: Path) -> None:
    followlist = tmp_path / "followlist.csv"
    out_json = tmp_path / "raw_account_trades.json"
    followlist.write_text("wallet,handle\n0xCold,ColdMath\n0xBroken,Broken\n", encoding="utf-8")

    def fake_http_get(url: str, params: dict[str, object]) -> dict[str, object]:
        if params["user"] == "0xBroken":
            raise RuntimeError("public API unavailable")
        return {"trades": [{"transactionHash": "0xaaa", "proxyWallet": "0xCold"}]}

    result = backfill_account_trades_from_followlist(followlist, out_json, http_get=fake_http_get)

    assert result["summary"]["accounts_succeeded"] == 1
    assert result["summary"]["accounts_failed"] == 1
    artifact = json.loads(out_json.read_text(encoding="utf-8"))
    assert artifact["raw_trades"] == [{"transactionHash": "0xaaa", "proxyWallet": "0xCold"}]
    assert artifact["summary"]["per_account_counts"] == {"0xCold": 1, "0xBroken": 0}
    assert artifact["summary"]["errors"] == [{"wallet": "0xBroken", "handle": "Broken", "error": "public API unavailable"}]


def test_public_http_get_json_uses_browser_user_agent(monkeypatch) -> None:
    from weather_pm import account_trades

    captured: dict[str, object] = {}

    class FakeResponse:
        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return b"[]"

    def fake_urlopen(request: object, timeout: int) -> FakeResponse:
        captured["headers"] = dict(request.header_items())  # type: ignore[attr-defined]
        captured["full_url"] = request.full_url  # type: ignore[attr-defined]
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(account_trades.urllib.request, "urlopen", fake_urlopen)

    assert account_trades._public_http_get_json("https://data-api.polymarket.com/trades", {"user": "0xabc", "limit": 1}) == []

    assert captured["full_url"] == "https://data-api.polymarket.com/trades?user=0xabc&limit=1"
    assert captured["timeout"] == 30
    assert captured["headers"] == {
        "Accept": "application/json",
        "User-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
    }


def test_cli_backfill_account_trades_parser_accepts_followlist_options() -> None:
    parser = build_parser()

    args = parser.parse_args(
        [
            "backfill-account-trades",
            "--followlist",
            "follow.csv",
            "--out-json",
            "raw.json",
            "--limit-accounts",
            "7",
            "--trades-per-account",
            "33",
        ]
    )

    assert args.command == "backfill-account-trades"
    assert args.followlist == "follow.csv"
    assert args.out_json == "raw.json"
    assert args.limit_accounts == 7
    assert args.trades_per_account == 33


def test_cli_import_account_trades_writes_weather_trades_and_profiles(tmp_path: Path) -> None:
    input_json = tmp_path / "trades.json"
    trades_out = tmp_path / "weather_trades.json"
    profiles_out = tmp_path / "profiles.json"
    input_json.write_text(json.dumps(TRADE_ROWS), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "weather_pm.cli",
            "import-account-trades",
            "--trades-json",
            str(input_json),
            "--trades-out",
            str(trades_out),
            "--profiles-out",
            str(profiles_out),
        ],
        capture_output=True,
        text=True,
        check=False,
        env={"PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")},
    )

    assert result.returncode == 0, result.stderr
    compact = json.loads(result.stdout)
    assert compact["summary"]["weather_trades"] == 3
    assert compact["artifacts"] == {"weather_trades": str(trades_out), "profiles": str(profiles_out)}
    assert json.loads(trades_out.read_text(encoding="utf-8"))["paper_only"] is True
    assert json.loads(profiles_out.read_text(encoding="utf-8"))["live_order_allowed"] is False
