from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "classify_weather_accounts_window.py"
spec = importlib.util.spec_from_file_location("classify_weather_accounts_window", SCRIPT_PATH)
assert spec is not None and spec.loader is not None
classify_weather_accounts_window = importlib.util.module_from_spec(spec)
spec.loader.exec_module(classify_weather_accounts_window)


def test_existing_classified_limit_reads_top_suffix() -> None:
    assert classify_weather_accounts_window._existing_classified_limit(
        Path("weather_profitable_accounts_classified_top10050.csv"), fallback=0
    ) == 10050


def test_read_csv_and_rank_helpers_are_deterministic(tmp_path: Path) -> None:
    csv_path = tmp_path / "accounts.csv"
    csv_path.write_text("rank,proxyWallet\n2,0x2\n1,0x1\n", encoding="utf-8")

    rows = classify_weather_accounts_window._read_csv(csv_path)

    assert [row["proxyWallet"] for row in rows] == ["0x2", "0x1"]
    assert sorted(rows, key=classify_weather_accounts_window._rank)[0]["proxyWallet"] == "0x1"


def test_classify_row_uses_injected_fetch_for_weather_heavy(monkeypatch) -> None:
    def fake_fetch(endpoint: str, wallet: str, limit: int):
        assert wallet == "0xabc"
        if endpoint == "positions":
            return [{"title": f"Will the highest temperature in Paris be {i}°C?"} for i in range(6)]
        return [{"title": "Will the highest temperature in London be 20°C?"} for _ in range(4)]

    monkeypatch.setattr(classify_weather_accounts_window, "_fetch", fake_fetch)

    row = classify_weather_accounts_window.classify_row(
        {
            "rank": "7",
            "userName": "wx",
            "proxyWallet": "0xabc",
            "xUsername": "",
            "pnl": "123.45",
            "vol": "1000",
            "pnl_over_volume_pct": "12.3",
        }
    )

    assert row["classification"] == "weather specialist / weather-heavy"
    assert row["confidence"] == "medium"
    assert row["active_weather_positions"] == 6
    assert row["recent_weather_activity"] == 4
    assert row["profile_url"] == "https://polymarket.com/profile/0xabc"
    assert "highest temperature" in row["sample_weather_titles"]


def test_main_reuses_existing_rows_and_writes_summary_without_fetching(tmp_path: Path, monkeypatch, capsys) -> None:
    base = tmp_path
    data_dir = base / "data" / "polymarket"
    data_dir.mkdir(parents=True)
    full_csv = data_dir / "weather_profitable_accounts.csv"
    full_csv.write_text("rank,userName,proxyWallet,pnl,vol,pnl_over_volume_pct\n1,wx,0x1,10,100,10\n", encoding="utf-8")
    existing_csv = data_dir / "weather_profitable_accounts_classified_top1.csv"
    with existing_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=classify_weather_accounts_window.FIELDNAMES)
        writer.writeheader()
        writer.writerow(
            {
                "rank": "1",
                "userName": "wx",
                "proxyWallet": "0x1",
                "weather_pnl_usd": "10",
                "weather_volume_usd": "100",
                "pnl_over_volume_pct": "10",
                "classification": "weather specialist / weather-heavy",
                "confidence": "cached",
                "active_positions": "1",
                "active_weather_positions": "1",
                "active_nonweather_positions": "0",
                "recent_activity": "0",
                "recent_weather_activity": "0",
                "recent_nonweather_activity": "0",
                "sample_weather_titles": "weather",
                "sample_nonweather_titles": "",
                "profile_url": "https://polymarket.com/profile/0x1",
            }
        )

    monkeypatch.setattr("sys.argv", ["classify_weather_accounts_window.py", "--base", str(base), "--limit", "1", "--workers", "1"])
    monkeypatch.setattr(classify_weather_accounts_window, "_fetch", lambda *args: (_ for _ in ()).throw(AssertionError("must reuse cached row")))

    assert classify_weather_accounts_window.main() == 0

    out_csv = data_dir / "weather_profitable_accounts_classified_top1.csv"
    out_json = data_dir / "weather_profitable_accounts_classified_top1_summary.json"
    assert out_csv.exists()
    summary = json.loads(out_json.read_text(encoding="utf-8"))
    assert summary["classified_count"] == 1
    assert summary["newly_enriched_count"] == 0
    assert summary["weather_heavy_or_specialist_count"] == 1
    assert "reuse_existing" in capsys.readouterr().out
