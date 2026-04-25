from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable


@dataclass(slots=True)
class WeatherTrader:
    rank: int
    handle: str
    wallet: str
    weather_pnl_usd: float
    weather_volume_usd: float
    pnl_over_volume_pct: float
    classification: str
    confidence: str
    active_positions: int
    active_weather_positions: int
    active_nonweather_positions: int
    recent_activity: int
    recent_weather_activity: int
    recent_nonweather_activity: int
    sample_weather_titles: list[str]
    sample_nonweather_titles: list[str]
    profile_url: str

    @property
    def is_weather_heavy(self) -> bool:
        return "weather-heavy" in self.classification or "specialist" in self.classification

    @property
    def weather_signal_count(self) -> int:
        return self.active_weather_positions + self.recent_weather_activity

    def to_registry_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["is_weather_heavy"] = self.is_weather_heavy
        payload["weather_signal_count"] = self.weather_signal_count
        return payload


def load_weather_traders(path: str | Path) -> list[WeatherTrader]:
    with Path(path).open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    traders = [_trader_from_row(row) for row in rows]
    return sorted(traders, key=lambda trader: trader.weather_pnl_usd, reverse=True)


def reverse_engineer_weather_traders(traders: Iterable[WeatherTrader], *, min_pnl_usd: float = 0.0) -> dict[str, Any]:
    accounts = [trader for trader in traders if trader.weather_pnl_usd >= min_pnl_usd]
    priority = [trader for trader in accounts if trader.is_weather_heavy]
    generalists = [trader for trader in accounts if not trader.is_weather_heavy]
    ranked_priority = sorted(priority, key=lambda trader: (trader.weather_signal_count, trader.weather_pnl_usd), reverse=True)
    ranked_accounts = ranked_priority + sorted(generalists, key=lambda trader: trader.weather_pnl_usd, reverse=True)
    return {
        "total_accounts": len(accounts),
        "weather_heavy_count": len(priority),
        "generalist_count": len(generalists),
        "priority_accounts": [trader.handle for trader in ranked_priority],
        "patterns": {
            "dominant_market_types": ["exact_temperature_bins", "threshold_temperature_contracts"],
            "common_signal_sources": ["city/date/bucket grid", "station-resolution observations", "settlement-source latency"],
        },
        "reverse_engineering_hypotheses": [
            "city/date/bucket grid specialists likely price correlated exact-bin and threshold contracts together",
            "weather-heavy accounts appear to focus on repeatable settlement-source/station workflows rather than broad news flow",
        ],
        "accounts": [
            {
                **trader.to_registry_dict(),
                "recommended_use": "model_and_execution_template" if trader.is_weather_heavy else "signal_only_generalist",
            }
            for trader in ranked_accounts
        ],
    }


def build_weather_trader_registry(traders: Iterable[WeatherTrader]) -> dict[str, Any]:
    accounts = sorted(list(traders), key=lambda trader: trader.weather_pnl_usd, reverse=True)
    return {
        "source": "polymarket_weather_leaderboard",
        "accounts": [trader.to_registry_dict() for trader in accounts],
    }


def _trader_from_row(row: dict[str, str]) -> WeatherTrader:
    return WeatherTrader(
        rank=_to_int(row.get("rank")),
        handle=str(row.get("userName") or ""),
        wallet=str(row.get("proxyWallet") or ""),
        weather_pnl_usd=_to_float(row.get("weather_pnl_usd")),
        weather_volume_usd=_to_float(row.get("weather_volume_usd")),
        pnl_over_volume_pct=_to_float(row.get("pnl_over_volume_pct")),
        classification=str(row.get("classification") or ""),
        confidence=str(row.get("confidence") or ""),
        active_positions=_to_int(row.get("active_positions")),
        active_weather_positions=_to_int(row.get("active_weather_positions")),
        active_nonweather_positions=_to_int(row.get("active_nonweather_positions")),
        recent_activity=_to_int(row.get("recent_activity")),
        recent_weather_activity=_to_int(row.get("recent_weather_activity")),
        recent_nonweather_activity=_to_int(row.get("recent_nonweather_activity")),
        sample_weather_titles=_split_titles(row.get("sample_weather_titles")),
        sample_nonweather_titles=_split_titles(row.get("sample_nonweather_titles")),
        profile_url=str(row.get("profile_url") or ""),
    )


def _to_int(value: str | None) -> int:
    return int(float(value or 0))


def _to_float(value: str | None) -> float:
    return float(value or 0.0)


def _split_titles(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split("|") if part.strip()]
