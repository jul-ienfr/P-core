from __future__ import annotations

from weather_pm.wallet_intel import (
    PolymarketPosition,
    TraderStrategyProfile,
    build_trader_strategy_profile,
    fetch_trader_strategy_profile,
    trader_profile_api_plan,
)


def test_trader_profile_api_plan_uses_required_polymarket_endpoints() -> None:
    plan = trader_profile_api_plan("0xabc")

    assert plan["wallet"] == "0xabc"
    assert plan["endpoints"] == [
        {"name": "traded", "path": "/traded", "params": {"user": "0xabc"}},
        {"name": "closed_positions", "path": "/closed-positions", "params": {"user": "0xabc", "limit": 50, "offset": 0}},
        {"name": "open_positions", "path": "/positions", "params": {"user": "0xabc"}},
    ]
    assert plan["gamma_enrichment"] == "Use eventSlug on each position with Gamma /events to attach category/tags."


def test_build_trader_strategy_profile_combines_closed_and_redeemable_pnl_by_category() -> None:
    profile = build_trader_strategy_profile(
        wallet="0xabc",
        traded_count=42,
        closed_positions=[
            PolymarketPosition(event_slug="nyc-weather", category="weather", realized_pnl=12.5, cash_pnl=0.0, status="closed"),
            PolymarketPosition(event_slug="election", category="politics", realized_pnl=-4.0, cash_pnl=0.0, status="closed"),
        ],
        open_positions=[
            PolymarketPosition(event_slug="hk-weather", category="weather", realized_pnl=3.0, cash_pnl=2.0, status="redeemable"),
            PolymarketPosition(event_slug="btc", category="crypto", realized_pnl=99.0, cash_pnl=1.0, status="active"),
        ],
    )

    assert isinstance(profile, TraderStrategyProfile)
    assert profile.total_markets_traded == 42
    assert profile.total_pnl == 13.5
    assert profile.category_breakdown["weather"] == {"trades": 2, "pnl": 17.5, "share": 0.6667}
    assert profile.category_breakdown["politics"] == {"trades": 1, "pnl": -4.0, "share": 0.3333}
    assert "weather_specialist" in profile.tags
    assert profile.primary_category == "weather"


def test_fetch_trader_strategy_profile_paginates_closed_positions_and_enriches_categories(monkeypatch) -> None:
    calls: list[tuple[str, dict[str, object] | None]] = []

    def fake_fetch(path: str, params: dict[str, object] | None = None):
        calls.append((path, params))
        if path == "/traded":
            return [{"market": "m1"}, {"market": "m2"}, {"market": "m3"}]
        if path == "/closed-positions" and params and params.get("offset") == 0:
            return [
                {"eventSlug": "nyc-weather", "realizedPnl": "10.5", "cashPnl": 0, "status": "closed"},
                {"eventSlug": "election", "realizedPnl": -2, "cashPnl": 0, "status": "closed"},
            ]
        if path == "/closed-positions" and params and params.get("offset") == 2:
            return [{"eventSlug": "hk-weather", "realizedPnl": 4, "cashPnl": 0, "status": "closed"}]
        if path == "/closed-positions" and params and params.get("offset") == 4:
            return []
        if path == "/positions":
            return [
                {"eventSlug": "hk-weather", "realizedPnl": 1, "cashPnl": 2, "redeemable": True},
                {"eventSlug": "btc", "realizedPnl": 20, "cashPnl": 0, "status": "active"},
            ]
        raise AssertionError((path, params))

    def fake_event_category(event_slug: str) -> str:
        return {"nyc-weather": "weather", "hk-weather": "weather", "election": "politics", "btc": "crypto"}[event_slug]

    monkeypatch.setattr("weather_pm.wallet_intel._fetch_data_api_json", fake_fetch)
    monkeypatch.setattr("weather_pm.wallet_intel._fetch_gamma_event_category", fake_event_category)

    profile = fetch_trader_strategy_profile("0xabc", page_size=2)

    assert profile.total_markets_traded == 3
    assert profile.total_pnl == 15.5
    assert profile.category_breakdown["weather"] == {"trades": 3, "pnl": 17.5, "share": 0.75}
    assert profile.category_breakdown["politics"] == {"trades": 1, "pnl": -2.0, "share": 0.25}
    assert profile.primary_category == "weather"
    assert calls == [
        ("/traded", {"user": "0xabc"}),
        ("/closed-positions", {"user": "0xabc", "limit": 2, "offset": 0}),
        ("/closed-positions", {"user": "0xabc", "limit": 2, "offset": 2}),
        ("/closed-positions", {"user": "0xabc", "limit": 2, "offset": 4}),
        ("/positions", {"user": "0xabc"}),
    ]
