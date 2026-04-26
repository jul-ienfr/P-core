from __future__ import annotations

from prediction_core.analytics.trade_density import TradeDensity, summarize_trade_density


def test_summarize_trade_density_computes_execution_rates_and_intervals() -> None:
    summary = summarize_trade_density(
        [
            {"bot": "Bonereaper", "trades": 12866, "pnl_usd": 136020.18},
            {"bot": "0xe1D6b514", "trades": 18915, "pnl_usd": 180000.0},
        ],
        days=30,
    )

    assert summary.days == 30
    assert summary.rows[0] == TradeDensity(
        bot="Bonereaper",
        trades=12866,
        days=30,
        trades_per_minute=0.298,
        mean_minutes_between_trades=3.36,
        trades_per_day=428.87,
        pnl_usd=136020.18,
        pnl_per_trade=10.5721,
    )
    assert summary.rows[1].trades_per_minute == 0.438
    assert summary.rows[1].mean_minutes_between_trades == 2.28
    assert summary.to_dict()["rows"][0]["bot"] == "Bonereaper"


def test_summarize_trade_density_handles_zero_trades_without_fake_interval() -> None:
    summary = summarize_trade_density([{"bot": "idle", "trades": 0}], days=7)

    assert summary.rows[0].trades_per_minute == 0.0
    assert summary.rows[0].mean_minutes_between_trades is None
    assert summary.rows[0].pnl_per_trade is None
