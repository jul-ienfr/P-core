from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from weather_pm.account_trades import classify_weather_trade
from weather_pm.shadow_profiles import (
    build_learned_shadow_patterns_report,
    build_trade_no_trade_dataset,
    build_shadow_profile_operator_report,
    load_followlist_accounts,
)


def _trade(title: str, *, wallet: str = "0xCold", handle: str = "ColdMath", price: float = 0.31, size: float = 100.0) -> dict[str, object]:
    return classify_weather_trade(
        {
            "transactionHash": f"0x{abs(hash((title, wallet, price))) % 999999:x}",
            "proxyWallet": wallet,
            "userName": handle,
            "title": title,
            "slug": title.lower().replace(" ", "-"),
            "side": "BUY",
            "outcome": "Yes",
            "price": price,
            "size": size,
            "timestamp": "2026-04-24T10:00:00Z",
        }
    ).to_dict()


MARKETS = [
    {
        "market_id": "m-london-20",
        "question": "Will the highest temperature in London be exactly 20°C on April 25?",
        "city": "London",
        "date": "April 25",
        "yes_price": 0.31,
        "model_probability": 0.55,
    },
    {
        "market_id": "m-london-21",
        "question": "Will the highest temperature in London be 21°C or higher on April 25?",
        "city": "London",
        "date": "April 25",
        "yes_price": 0.73,
        "model_probability": 0.40,
    },
    {
        "market_id": "m-paris-18",
        "question": "Will the highest temperature in Paris be exactly 18°C on April 25?",
        "city": "Paris",
        "date": "April 25",
        "yes_price": 0.40,
        "model_probability": 0.41,
    },
]


def test_build_trade_no_trade_dataset_marks_abstentions_by_account_and_surface() -> None:
    trades = [_trade(MARKETS[0]["question"]), _trade(MARKETS[1]["question"], price=0.73, size=20)]

    dataset = build_trade_no_trade_dataset(trades, MARKETS, accounts=["0xCold"])

    assert dataset["summary"] == {
        "accounts": 1,
        "markets": 3,
        "examples": 3,
        "trade_examples": 2,
        "no_trade_examples": 1,
        "paper_only": True,
        "live_order_allowed": False,
    }
    rows = dataset["examples"]
    assert [row["label"] for row in rows] == ["trade", "trade", "no_trade"]
    assert rows[0]["weather_market_type"] == "exact_value"
    assert rows[0]["account_trade_notional_usd"] == 31.0
    assert rows[2]["account_trade_notional_usd"] == 0.0
    assert rows[2]["abstention_reason"] == "no_account_trade_on_surface"


def test_load_followlist_accounts_selects_top_ranked_wallets_with_metadata(tmp_path: Path) -> None:
    followlist_csv = tmp_path / "followlist.csv"
    followlist_csv.write_text(
        "wallet,handle,bucket,rank,score,profile_url\n"
        "0xLow,LowScore,weather,3,12.5,https://polymarket.com/profile/low\n"
        "0xTop,TopScore,weather,1,91.2,https://polymarket.com/profile/top\n"
        "0xMid,MidScore,weather,2,45.0,https://polymarket.com/profile/mid\n",
        encoding="utf-8",
    )

    accounts = load_followlist_accounts(followlist_csv, limit=2)

    assert [account["wallet"] for account in accounts] == ["0xTop", "0xMid"]
    assert accounts[0] == {
        "wallet": "0xTop",
        "handle": "TopScore",
        "bucket": "weather",
        "rank": 1,
        "score": 91.2,
        "account_profile_url": "https://polymarket.com/profile/top",
    }


def test_build_trade_no_trade_dataset_uses_followlist_metadata_and_zero_trade_accounts() -> None:
    accounts = [
        {"wallet": "0xCold", "handle": "ColdFollow", "bucket": "elite", "rank": 1, "score": 99.0, "account_profile_url": "https://example/0xCold"},
        {"wallet": "0xQuiet", "handle": "QuietOne", "bucket": "watch", "rank": 2, "score": 75.5, "account_profile_url": "https://example/0xQuiet"},
    ]
    trades = [_trade(MARKETS[0]["question"], handle="TradeHandle")]

    dataset = build_trade_no_trade_dataset(trades, MARKETS[:1], accounts=accounts)

    assert dataset["summary"]["accounts"] == 2
    assert dataset["summary"]["trade_examples"] == 1
    assert dataset["summary"]["no_trade_examples"] == 1
    trade_row, no_trade_row = dataset["examples"]
    assert trade_row["label"] == "trade"
    assert trade_row["handle"] == "ColdFollow"
    assert trade_row["bucket"] == "elite"
    assert trade_row["rank"] == 1
    assert trade_row["score"] == 99.0
    assert trade_row["account_profile_url"] == "https://example/0xCold"
    assert no_trade_row["wallet"] == "0xQuiet"
    assert no_trade_row["label"] == "no_trade"
    assert no_trade_row["handle"] == "QuietOne"
    assert no_trade_row["bucket"] == "watch"
    assert no_trade_row["rank"] == 2
    assert no_trade_row["score"] == 75.5


def test_build_trade_no_trade_dataset_summarizes_duplicate_trade_hits() -> None:
    first = _trade(MARKETS[0]["question"], price=0.20, size=10)
    second = _trade(MARKETS[0]["question"], price=0.40, size=30)
    second["timestamp"] = "2026-04-24T11:30:00Z"

    dataset = build_trade_no_trade_dataset([first, second], MARKETS[:1], accounts=["0xCold"])

    row = dataset["examples"][0]
    assert row["label"] == "trade"
    assert row["account_trade_count"] == 2
    assert row["account_first_trade_timestamp"] == "2026-04-24T10:00:00Z"
    assert row["account_last_trade_timestamp"] == "2026-04-24T11:30:00Z"
    assert row["account_trade_notional_usd"] == 14.0
    assert row["account_trade_price"] == 0.35
    assert row["account_trade_size"] == 40.0


def test_build_shadow_profile_operator_report_summarizes_behavioral_patterns() -> None:
    trades = [
        _trade(MARKETS[0]["question"], price=0.31, size=100),
        _trade(MARKETS[1]["question"], price=0.73, size=20),
        _trade("Will the highest temperature in Seoul be exactly 22°C on April 25?", wallet="0xBot", handle="GridBot", price=0.18, size=200),
    ]
    dataset = build_trade_no_trade_dataset(trades, MARKETS, accounts=["0xCold", "0xBot"])

    report = build_shadow_profile_operator_report(dataset, limit=5)

    assert report["summary"]["paper_only"] is True
    assert report["profiles"][0]["wallet"] == "0xCold"
    assert report["profiles"][0]["behavioral_profile"] == "surface_grid_accumulator"
    assert report["profiles"][0]["trade_count"] == 2
    assert report["profiles"][0]["no_trade_count"] == 1
    assert "compare_trade_vs_no_trade_surfaces" in report["operator_next_actions"]
    assert "Shadow profiles météo" in report["discord_brief"]


def test_build_learned_shadow_patterns_report_extracts_operator_patterns() -> None:
    trades = [
        _trade(MARKETS[0]["question"], wallet="0xCold", handle="ColdMath", price=0.31, size=100),
        _trade(MARKETS[1]["question"], wallet="0xCold", handle="ColdMath", price=0.73, size=20),
        _trade(MARKETS[2]["question"], wallet="0xParis", handle="ParisThreshold", price=0.40, size=50),
    ]
    dataset = build_trade_no_trade_dataset(trades, MARKETS, accounts=["0xCold", "0xParis"])

    report = build_learned_shadow_patterns_report(dataset, limit=2)

    assert report["source"] == "polymarket_weather_learned_shadow_patterns"
    assert report["paper_only"] is True
    assert report["live_order_allowed"] is False
    assert report["summary"] == {
        "accounts": 2,
        "examples": 6,
        "trade_examples": 3,
        "no_trade_examples": 3,
        "abstention_rate": 0.5,
        "paper_only": True,
        "live_order_allowed": False,
    }
    cold = report["learned_patterns"][0]
    assert cold["wallet"] == "0xCold"
    assert cold["handle"] == "ColdMath"
    assert cold["behavioral_profile"] == "surface_grid_accumulator"
    assert cold["trade_count"] == 2
    assert cold["no_trade_count"] == 1
    assert cold["avg_entry_price"] == 0.52
    assert cold["avg_trade_notional_usd"] == 22.8
    assert cold["top_cities"] == [{"city": "London", "trade_count": 2, "no_trade_count": 0}]
    assert cold["market_type_bias"] == [{"market_type": "exact_value", "trade_count": 1}, {"market_type": "threshold", "trade_count": 1}]
    assert cold["abstention_rate"] == 0.333333
    assert cold["replay_priority"] == "high"
    assert any("paper replay only" in action for action in report["operator_next_actions"])
    assert any("independent forecast" in action for action in report["operator_next_actions"])
    assert all("copy" not in json.dumps(action).lower() for action in report["operator_next_actions"])


def test_cli_shadow_patterns_report_writes_json_and_markdown(tmp_path: Path) -> None:
    dataset_json = tmp_path / "dataset.json"
    output_json = tmp_path / "patterns.json"
    output_md = tmp_path / "patterns.md"
    dataset = build_trade_no_trade_dataset(
        [_trade(MARKETS[0]["question"]), _trade(MARKETS[1]["question"], price=0.73, size=20)],
        MARKETS,
        accounts=["0xCold"],
    )
    dataset_json.write_text(json.dumps(dataset), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "weather_pm.cli",
            "shadow-patterns-report",
            "--dataset-json",
            str(dataset_json),
            "--output-json",
            str(output_json),
            "--output-md",
            str(output_md),
            "--limit",
            "1",
        ],
        capture_output=True,
        text=True,
        check=False,
        env={"PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")},
    )

    assert result.returncode == 0, result.stderr
    compact = json.loads(result.stdout)
    assert compact["summary"]["abstention_rate"] == 0.333333
    assert compact["artifacts"] == {"output_json": str(output_json), "output_md": str(output_md)}
    saved = json.loads(output_json.read_text(encoding="utf-8"))
    assert saved["learned_patterns"][0]["wallet"] == "0xCold"
    markdown = output_md.read_text(encoding="utf-8")
    assert "Learned Weather Shadow Patterns" in markdown
    assert "paper replay only" in markdown
    assert "copy" not in markdown.lower()


def test_cli_shadow_profile_report_writes_dataset_and_operator_report(tmp_path: Path) -> None:
    trades_json = tmp_path / "trades.json"
    markets_json = tmp_path / "markets.json"
    dataset_out = tmp_path / "dataset.json"
    report_out = tmp_path / "report.json"
    trades_json.write_text(json.dumps({"trades": [_trade(MARKETS[0]["question"]), _trade(MARKETS[1]["question"], price=0.73, size=20)]}), encoding="utf-8")
    markets_json.write_text(json.dumps({"markets": MARKETS}), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "weather_pm.cli",
            "shadow-profile-report",
            "--weather-trades-json",
            str(trades_json),
            "--markets-json",
            str(markets_json),
            "--dataset-out",
            str(dataset_out),
            "--report-out",
            str(report_out),
            "--limit",
            "3",
        ],
        capture_output=True,
        text=True,
        check=False,
        env={"PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")},
    )

    assert result.returncode == 0, result.stderr
    compact = json.loads(result.stdout)
    assert compact["summary"]["trade_examples"] == 2
    assert compact["artifacts"] == {"dataset": str(dataset_out), "report": str(report_out)}
    assert json.loads(report_out.read_text(encoding="utf-8"))["live_order_allowed"] is False


def test_cli_shadow_profile_report_accepts_followlist_csv_and_account_limit(tmp_path: Path) -> None:
    trades_json = tmp_path / "trades.json"
    markets_json = tmp_path / "markets.json"
    accounts_csv = tmp_path / "accounts.csv"
    dataset_out = tmp_path / "dataset.json"
    report_out = tmp_path / "report.json"
    trades_json.write_text(json.dumps({"trades": [_trade(MARKETS[0]["question"], wallet="0xTop", handle="TradeTop")]}), encoding="utf-8")
    markets_json.write_text(json.dumps({"markets": MARKETS[:1]}), encoding="utf-8")
    accounts_csv.write_text(
        "wallet,handle,bucket,rank,score,profile_url\n"
        "0xQuiet,QuietFollow,watch,2,88,https://example/quiet\n"
        "0xTop,TopFollow,elite,1,99,https://example/top\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "weather_pm.cli",
            "shadow-profile-report",
            "--weather-trades-json",
            str(trades_json),
            "--markets-json",
            str(markets_json),
            "--dataset-out",
            str(dataset_out),
            "--report-out",
            str(report_out),
            "--accounts-csv",
            str(accounts_csv),
            "--limit-accounts",
            "2",
        ],
        capture_output=True,
        text=True,
        check=False,
        env={"PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")},
    )

    assert result.returncode == 0, result.stderr
    compact = json.loads(result.stdout)
    assert compact["summary"]["accounts"] == 2
    assert compact["summary"]["no_trade_examples"] == 1
    saved = json.loads(dataset_out.read_text(encoding="utf-8"))
    assert [row["wallet"] for row in saved["examples"]] == ["0xTop", "0xQuiet"]
    assert saved["examples"][0]["handle"] == "TopFollow"
    assert saved["examples"][1]["label"] == "no_trade"
    assert saved["examples"][1]["handle"] == "QuietFollow"
