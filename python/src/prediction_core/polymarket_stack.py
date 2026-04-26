from __future__ import annotations

from copy import deepcopy
from typing import Any

_FASTEST_STACK: dict[str, Any] = {
    "fastest_hot_path": {
        "technology": "Polymarket/rs-clob-client",
        "repository": "https://github.com/Polymarket/rs-clob-client",
        "language": "Rust",
        "transport": "CLOB WebSocket",
        "role": "long-running daemon for live orderbook updates",
        "why": "keeps one async process alive and avoids CLI process startup overhead",
    },
    "official_cli": {
        "repository": "Polymarket/polymarket-cli",
        "url": "https://github.com/Polymarket/polymarket-cli",
        "language": "Rust",
        "sdk": "polymarket-client-sdk",
        "uses": ["Gamma API", "CLOB API", "Data API", "Bridge API", "CTF API"],
        "best_for": "terminal automation and JSON scripting",
        "not_best_for": "tight low-latency trading loops because each command starts a process",
    },
    "recommended_architecture": [
        "Gamma REST for market discovery and clobTokenIds, cached outside the hot path",
        "CLOB WebSocket for live orderbook and price updates",
        "CLOB REST for order placement and account/trading operations",
        "Data API for analytics, wallets, trades, and historical behaviour outside the hot path",
    ],
}

_DECISION_TABLE: list[dict[str, Any]] = [
    {
        "layer": "discovery",
        "api": "Gamma API",
        "preferred_client": "polymarket-client-sdk gamma feature or cached HTTP fetcher",
        "hot_path": False,
        "purpose": "events, markets, tags, rules, descriptions, resolution sources, clobTokenIds",
    },
    {
        "layer": "live_market_data",
        "api": "CLOB WebSocket",
        "preferred_client": "Polymarket/rs-clob-client with ws feature",
        "hot_path": True,
        "purpose": "orderbook, best bid/ask, trades, price updates",
    },
    {
        "layer": "order_execution",
        "api": "CLOB REST",
        "preferred_client": "Polymarket/rs-clob-client clob feature",
        "hot_path": True,
        "purpose": "placing/cancelling orders, balances, allowances, authenticated trading calls",
    },
    {
        "layer": "analytics",
        "api": "Data API",
        "preferred_client": "polymarket-client-sdk data feature or batch/offline jobs",
        "hot_path": False,
        "purpose": "public trades, wallets, positions, leaderboards, post-trade analytics",
    },
    {
        "layer": "operator_cli",
        "api": "Gamma API + CLOB API + Data API",
        "preferred_client": "Polymarket/polymarket-cli with JSON output",
        "hot_path": False,
        "purpose": "manual checks, scripts, agent actions, smoke tests",
    },
]


def recommended_polymarket_stack() -> dict[str, Any]:
    """Return the grounded Polymarket integration stack preference for prediction_core."""

    return deepcopy(_FASTEST_STACK)


def stack_decision_table() -> list[dict[str, Any]]:
    """Return the API/client split used to keep low-latency work on the hot path."""

    return deepcopy(_DECISION_TABLE)
