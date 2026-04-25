from __future__ import annotations

import re
from collections import Counter
from typing import Any, Iterable

from weather_pm.traders import WeatherTrader

_THRESHOLD_RE = re.compile(r"temperature in (?P<city>.+?) be .+? or (?P<direction>higher|below) on (?P<date>.+?)\?", re.I)
_RANGE_RE = re.compile(r"temperature in (?P<city>.+?) be between .+? on (?P<date>.+?)\?", re.I)
_EXACT_RE = re.compile(r"temperature in (?P<city>.+?) be (?:exactly )?-?\d+(?:\.\d+)?(?:°)?[CF] on (?P<date>.+?)\?", re.I)
_SLUG_DATE_RE = re.compile(r"-(?P<month>january|february|march|april|may|june|july|august|september|october|november|december)-(?P<day>\d{1,2})(?:-|$)", re.I)
_TITLE_PREFIX_RE = re.compile(r"^(?P<title>Will .+?\?)(?:\s|$)", re.I)


def extract_weather_strategy_rules(traders: Iterable[WeatherTrader]) -> dict[str, Any]:
    accounts = [_account_strategy(trader) for trader in traders]
    return {"account_count": len(accounts), "accounts": accounts, "summary": summarize_strategy_rules({"accounts": accounts})}


def summarize_strategy_rules(rules: dict[str, Any]) -> dict[str, Any]:
    accounts = list(rules.get("accounts") or [])
    archetypes = Counter(str(account.get("primary_archetype") or "unknown") for account in accounts)
    cities: Counter[str] = Counter()
    for account in accounts:
        for item in account.get("top_cities") or []:
            city = item.get("city") if isinstance(item, dict) else None
            count = item.get("count") if isinstance(item, dict) else 0
            if city:
                cities[str(city)] += int(count or 0)
    return {
        "account_count": len(accounts),
        "archetype_counts": dict(archetypes),
        "top_cities": [city for city, _ in cities.most_common(10)],
        "implementation_priorities": _implementation_priorities(archetypes),
    }


def _account_strategy(trader: WeatherTrader) -> dict[str, Any]:
    parsed_titles = [_parse_title(title) for title in trader.sample_weather_titles]
    parsed_titles = [item for item in parsed_titles if item]
    market_counts = Counter(item["market_type"] for item in parsed_titles)
    city_counts = Counter(item["city"] for item in parsed_titles)
    event_counts = Counter((item["city"], item.get("date") or "unknown") for item in parsed_titles)
    archetype = _infer_archetype(market_counts, event_counts)
    return {
        "handle": trader.handle,
        "wallet": trader.wallet,
        "weather_pnl_usd": trader.weather_pnl_usd,
        "weather_volume_usd": trader.weather_volume_usd,
        "pnl_over_volume_pct": trader.pnl_over_volume_pct,
        "weather_signal_count": trader.weather_signal_count,
        "primary_archetype": archetype,
        "market_type_counts": dict(market_counts),
        "top_cities": [{"city": city, "count": count} for city, count in city_counts.most_common(10)],
        "repeated_city_date_events": [
            {"city": city, "date": date, "count": count}
            for (city, date), count in event_counts.most_common(10)
            if count >= 2
        ],
        "strategy_rules": _strategy_rules(archetype, market_counts, event_counts),
        "sample_size": len(parsed_titles),
    }


def _parse_title(title: str) -> dict[str, str] | None:
    stripped = _normalize_observed_title(title)
    for market_type, pattern in (("threshold", _THRESHOLD_RE), ("exact_range", _RANGE_RE), ("exact_value", _EXACT_RE)):
        match = pattern.search(stripped)
        if match:
            return {"market_type": market_type, "city": match.group("city"), "date": match.group("date")}
    city_match = re.search(r"temperature in (?P<city>.+?) be ", stripped, re.I)
    if city_match:
        return {"market_type": "weather_other", "city": city_match.group("city"), "date": _date_from_slug(title)}
    return None


def _normalize_observed_title(raw_title: str) -> str:
    stripped = raw_title.strip()
    prefix = _TITLE_PREFIX_RE.search(stripped)
    if prefix:
        return prefix.group("title")
    return stripped


def _date_from_slug(raw_title: str) -> str:
    match = _SLUG_DATE_RE.search(raw_title)
    if not match:
        return "unknown"
    return f"{match.group('month').title()} {int(match.group('day'))}"


def _infer_archetype(market_counts: Counter[str], event_counts: Counter[tuple[str, str]]) -> str:
    repeated_event = any(count >= 2 for count in event_counts.values())
    exact_count = market_counts.get("exact_value", 0) + market_counts.get("exact_range", 0)
    threshold_count = market_counts.get("threshold", 0)
    if repeated_event and exact_count >= threshold_count:
        return "event_surface_grid_specialist"
    if threshold_count >= max(exact_count, 1):
        return "threshold_harvester"
    if exact_count > 0:
        return "exact_bin_anomaly_hunter"
    return "weather_signal_generalist"


def _strategy_rules(archetype: str, market_counts: Counter[str], event_counts: Counter[tuple[str, str]]) -> list[str]:
    rules: list[str] = []
    if archetype == "event_surface_grid_specialist":
        rules.append("build full city/date event surfaces before scoring isolated markets")
    if market_counts.get("exact_value", 0) or market_counts.get("exact_range", 0):
        rules.append("prioritize exact-bin and adjacent threshold inconsistencies")
    if market_counts.get("threshold", 0):
        rules.append("track near-resolution threshold contracts for cheap certainty harvesting")
    if any(count >= 2 for count in event_counts.values()):
        rules.append("cluster orders by city/date rather than treating markets independently")
    if not rules:
        rules.append("use account as weak signal source only until more trade history is available")
    return rules


def _implementation_priorities(archetypes: Counter[str]) -> list[str]:
    priorities: list[str] = []
    if archetypes.get("event_surface_grid_specialist", 0) or archetypes.get("exact_bin_anomaly_hunter", 0):
        priorities.append("event_surface_builder")
    if archetypes.get("threshold_harvester", 0):
        priorities.append("near_resolution_threshold_watcher")
    priorities.extend(["trader_activity_history_import", "strategy_backtest_replay", "paper_then_live_execution_loop"])
    seen = set()
    return [item for item in priorities if not (item in seen or seen.add(item))]
