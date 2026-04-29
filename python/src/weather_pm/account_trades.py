from __future__ import annotations

import csv
import json
import re
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Iterable


@dataclass(frozen=True, slots=True)
class WeatherAccountTrade:
    trade_id: str
    wallet: str
    handle: str
    title: str
    slug: str
    side: str
    outcome: str
    price: float
    size: float
    notional_usd: float
    timestamp: str
    is_weather: bool
    weather_market_type: str
    city: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def classify_weather_trade(raw: dict[str, Any]) -> WeatherAccountTrade:
    title = str(raw.get("title") or raw.get("question") or raw.get("marketTitle") or raw.get("market_title") or "")
    slug = str(raw.get("slug") or raw.get("marketSlug") or raw.get("eventSlug") or raw.get("conditionId") or "")
    price = _to_float(raw.get("price") or raw.get("avgPrice") or raw.get("averagePrice"))
    size = _to_float(raw.get("size") or raw.get("amount") or raw.get("shares"))
    market_type = _weather_market_type(title, slug)
    is_weather = market_type != "non_weather"
    return WeatherAccountTrade(
        trade_id=str(raw.get("transactionHash") or raw.get("transaction_hash") or raw.get("id") or raw.get("tradeId") or ""),
        wallet=str(raw.get("proxyWallet") or raw.get("proxy_wallet") or raw.get("wallet") or raw.get("user") or ""),
        handle=str(raw.get("userName") or raw.get("handle") or raw.get("name") or ""),
        title=title,
        slug=slug,
        side=str(raw.get("side") or raw.get("action") or "").upper(),
        outcome=str(raw.get("outcome") or raw.get("outcomeLabel") or raw.get("asset") or ""),
        price=price,
        size=size,
        notional_usd=round(price * size, 6),
        timestamp=str(raw.get("timestamp") or raw.get("createdAt") or raw.get("created_at") or raw.get("time") or ""),
        is_weather=is_weather,
        weather_market_type=market_type,
        city=_city_from_title(title) if is_weather else None,
    )


POLYMARKET_PUBLIC_TRADES_URL = "https://data-api.polymarket.com/trades"


def backfill_account_trades_from_followlist(
    followlist_csv: str | Path,
    out_json: str | Path,
    *,
    limit_accounts: int = 20,
    trades_per_account: int = 100,
    http_get: Callable[[str, dict[str, object]], Any] | None = None,
) -> dict[str, Any]:
    """Backfill public historical Polymarket trades for wallets in a followlist.

    This runner is intentionally read-only: it calls only the public data API and
    writes a local JSON artifact that can be fed to import_account_trades.
    """
    selected_accounts = _load_followlist_accounts(followlist_csv, limit_accounts=limit_accounts)
    getter = http_get or _public_http_get_json
    raw_trades: list[dict[str, Any]] = []
    per_account_counts: dict[str, int] = {}
    errors: list[dict[str, str]] = []
    accounts_succeeded = 0

    for account in selected_accounts:
        wallet = account["wallet"]
        handle = account.get("handle", "")
        try:
            response = getter(POLYMARKET_PUBLIC_TRADES_URL, {"user": wallet, "limit": trades_per_account})
            rows = _normalize_public_trades_response(response)
            raw_trades.extend(rows)
            per_account_counts[wallet] = len(rows)
            accounts_succeeded += 1
        except Exception as exc:  # pragma: no cover - exercised via injected test double
            per_account_counts[wallet] = 0
            errors.append({"wallet": wallet, "handle": handle, "error": str(exc)})

    summary = {
        "accounts_requested": len(selected_accounts),
        "accounts_succeeded": accounts_succeeded,
        "accounts_failed": len(errors),
        "raw_trades": len(raw_trades),
        "per_account_counts": per_account_counts,
        "errors": errors,
        "paper_only": True,
        "live_order_allowed": False,
    }
    artifact = {
        "source": "polymarket_data_api_account_trades",
        "endpoint": POLYMARKET_PUBLIC_TRADES_URL,
        "paper_only": True,
        "live_order_allowed": False,
        "accounts": selected_accounts,
        "raw_trades": raw_trades,
        "summary": summary,
    }
    output_path = Path(out_json)
    _write_json(output_path, artifact)
    return {
        "summary": {
            "accounts_requested": summary["accounts_requested"],
            "accounts_succeeded": summary["accounts_succeeded"],
            "accounts_failed": summary["accounts_failed"],
            "raw_trades": summary["raw_trades"],
            "paper_only": True,
            "live_order_allowed": False,
        },
        "artifacts": {"raw_trades": str(output_path)},
    }


def import_account_trades(
    trades_json: str | Path,
    *,
    trades_out: str | Path,
    profiles_out: str | Path,
) -> dict[str, Any]:
    raw_trades = _load_trade_rows(trades_json)
    classified = [classify_weather_trade(row) for row in raw_trades]
    weather_trades = [trade for trade in classified if trade.is_weather]
    grouped: dict[str, list[WeatherAccountTrade]] = defaultdict(list)
    for trade in weather_trades:
        grouped[trade.wallet].append(trade)
    profiles = [build_historical_weather_trade_profile(wallet, trades) for wallet, trades in grouped.items()]
    profiles.sort(key=lambda row: (float(row["total_notional_usd"]), int(row["trade_count"])), reverse=True)

    trades_path = Path(trades_out)
    profiles_path = Path(profiles_out)
    trades_payload = {
        "source": "polymarket_account_trades",
        "paper_only": True,
        "live_order_allowed": False,
        "trades": [trade.to_dict() for trade in weather_trades],
    }
    profiles_payload = {
        "source": "polymarket_account_trades",
        "paper_only": True,
        "live_order_allowed": False,
        "profiles": profiles,
    }
    _write_json(trades_path, trades_payload)
    _write_json(profiles_path, profiles_payload)
    return {
        "summary": {
            "input_trades": len(raw_trades),
            "weather_trades": len(weather_trades),
            "accounts": len(profiles),
            "paper_only": True,
            "live_order_allowed": False,
        },
        "artifacts": {"weather_trades": str(trades_path), "profiles": str(profiles_path)},
    }


def build_historical_weather_trade_profile(wallet: str, trades: Iterable[WeatherAccountTrade]) -> dict[str, Any]:
    trade_list = [trade for trade in trades if trade.is_weather]
    type_counts = Counter(trade.weather_market_type for trade in trade_list)
    city_counts = Counter(trade.city for trade in trade_list if trade.city)
    total_notional = round(sum(trade.notional_usd for trade in trade_list), 6)
    trade_count = len(trade_list)
    profile = {
        "wallet": wallet,
        "handle": _first_non_empty(trade.handle for trade in trade_list),
        "trade_count": trade_count,
        "total_notional_usd": total_notional,
        "avg_trade_notional_usd": round(total_notional / trade_count, 6) if trade_count else 0.0,
        "weather_market_type_counts": dict(type_counts),
        "top_cities": [{"city": city, "count": count} for city, count in city_counts.most_common(5)],
        "primary_archetype": _primary_archetype(type_counts),
        "recommended_uses": ["learn_timing_and_sizing", "derive_trade_no_trade_examples"],
        "paper_only": True,
        "live_order_allowed": False,
    }
    if profile["primary_archetype"] == "macro_weather_event_trader":
        profile["recommended_uses"].append("macro_weather_event_watchlist")
    return profile


def _load_trade_rows(path: str | Path) -> list[dict[str, Any]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("trades", "raw_trades", "data", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
    raise ValueError("trades JSON must be a list or an object with trades/raw_trades/data/results")


def _load_followlist_accounts(path: str | Path, *, limit_accounts: int) -> list[dict[str, str]]:
    accounts: list[dict[str, str]] = []
    with Path(path).open(newline="", encoding="utf-8") as csv_file:
        for row in csv.DictReader(csv_file):
            wallet = str(row.get("wallet") or "").strip()
            if not wallet:
                continue
            account = {"wallet": wallet, "handle": str(row.get("handle") or "").strip()}
            for key in ("bucket", "rank", "score"):
                value = row.get(key)
                if value is not None and str(value).strip() != "":
                    account[key] = str(value).strip()
            accounts.append(account)
            if len(accounts) >= limit_accounts:
                break
    return accounts


def _normalize_public_trades_response(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("trades", "data", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
    return []


def _public_http_get_json(url: str, params: dict[str, object]) -> Any:
    query = urllib.parse.urlencode(params)
    request_url = f"{url}?{query}" if query else url
    request = urllib.request.Request(
        request_url,
        headers={
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
        },
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # nosec B310 - public read-only data API URL
        return json.loads(response.read().decode("utf-8"))


def _weather_market_type(title: str, slug: str) -> str:
    text = f"{title} {slug}".lower()
    if any(token in text for token in ("temperature", "highest temp", "highest-temperature", "°c", "°f", "named storms", "hurricane", "rain", "snow")):
        if "named storms" in text or "hurricane" in text:
            return "macro_weather"
        return _market_type_from_title(title)
    return "non_weather"


def _market_type_from_title(title: str) -> str:
    lowered = title.lower()
    if " between " in lowered:
        return "exact_range"
    if " or higher" in lowered or " or below" in lowered:
        return "threshold"
    if re.search(r"-?\d+(?:\.\d+)?\s*(?:°)?[cf]\b", lowered):
        return "exact_value"
    return "weather_other"


def _city_from_title(title: str) -> str | None:
    match = re.search(r"temperature in (?P<city>.+?) be ", title, re.I)
    return match.group("city") if match else None


def _primary_archetype(type_counts: Counter[str]) -> str:
    if not type_counts:
        return "unknown"
    if type_counts.get("macro_weather", 0) >= max(type_counts.values()):
        return "macro_weather_event_trader"
    if type_counts.get("threshold", 0) > type_counts.get("exact_value", 0) + type_counts.get("exact_range", 0):
        return "threshold_harvester"
    return "event_surface_grid_specialist"


def _first_non_empty(values: Iterable[str]) -> str:
    for value in values:
        if value:
            return value
    return ""


def _to_float(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
