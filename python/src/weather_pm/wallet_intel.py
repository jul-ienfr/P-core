from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


_DATA_API_BASE_URL = "https://data-api.polymarket.com"
_GAMMA_BASE_URL = "https://gamma-api.polymarket.com"
_DEFAULT_TIMEOUT_SECONDS = 20


@dataclass(frozen=True, slots=True)
class PolymarketPosition:
    event_slug: str
    category: str
    realized_pnl: float
    cash_pnl: float
    status: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_slug": self.event_slug,
            "category": self.category,
            "realized_pnl": self.realized_pnl,
            "cash_pnl": self.cash_pnl,
            "status": self.status,
        }


@dataclass(frozen=True, slots=True)
class TraderStrategyProfile:
    wallet: str
    total_markets_traded: int
    total_pnl: float
    primary_category: str | None
    category_breakdown: dict[str, dict[str, float | int]]
    tags: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "wallet": self.wallet,
            "total_markets_traded": self.total_markets_traded,
            "total_pnl": self.total_pnl,
            "primary_category": self.primary_category,
            "category_breakdown": self.category_breakdown,
            "tags": self.tags,
        }


def trader_profile_api_plan(wallet: str) -> dict[str, Any]:
    return {
        "wallet": wallet,
        "endpoints": [
            {"name": "traded", "path": "/traded", "params": {"user": wallet}},
            {"name": "closed_positions", "path": "/closed-positions", "params": {"user": wallet, "limit": 50, "offset": 0}},
            {"name": "open_positions", "path": "/positions", "params": {"user": wallet}},
        ],
        "gamma_enrichment": "Use eventSlug on each position with Gamma /events to attach category/tags.",
    }


def build_trader_strategy_profile(
    *,
    wallet: str,
    traded_count: int,
    closed_positions: Iterable[PolymarketPosition],
    open_positions: Iterable[PolymarketPosition],
) -> TraderStrategyProfile:
    counted_positions = list(closed_positions) + [
        position for position in open_positions if position.status == "redeemable"
    ]
    totals: dict[str, dict[str, float | int]] = {}
    for position in counted_positions:
        category = position.category or "unknown"
        pnl = position.realized_pnl
        if position.status == "redeemable":
            pnl += position.cash_pnl
        row = totals.setdefault(category, {"trades": 0, "pnl": 0.0, "share": 0.0})
        row["trades"] = int(row["trades"]) + 1
        row["pnl"] = round(float(row["pnl"]) + pnl, 10)

    total_positions = max(len(counted_positions), 1)
    for row in totals.values():
        row["share"] = round(int(row["trades"]) / total_positions, 4)

    total_pnl = round(sum(float(row["pnl"]) for row in totals.values()), 10)
    primary_category = _primary_category(totals)
    tags = _profile_tags(primary_category, totals)
    return TraderStrategyProfile(
        wallet=wallet,
        total_markets_traded=int(traded_count),
        total_pnl=total_pnl,
        primary_category=primary_category,
        category_breakdown=totals,
        tags=tags,
    )


def fetch_trader_strategy_profile(wallet: str, *, page_size: int = 50) -> TraderStrategyProfile:
    traded_payload = _fetch_data_api_json("/traded", {"user": wallet})
    closed_positions = _fetch_closed_positions(wallet, page_size=page_size)
    open_payload = _fetch_data_api_json("/positions", {"user": wallet})
    open_positions = [_position_from_payload(item) for item in _payload_items(open_payload)]
    return build_trader_strategy_profile(
        wallet=wallet,
        traded_count=_traded_count(traded_payload),
        closed_positions=closed_positions,
        open_positions=open_positions,
    )


def _fetch_closed_positions(wallet: str, *, page_size: int) -> list[PolymarketPosition]:
    positions: list[PolymarketPosition] = []
    offset = 0
    limit = max(int(page_size), 1)
    while True:
        page_payload = _fetch_data_api_json("/closed-positions", {"user": wallet, "limit": limit, "offset": offset})
        page_items = _payload_items(page_payload)
        if not page_items:
            break
        positions.extend(_position_from_payload(item) for item in page_items)
        offset += limit
    return positions


def _fetch_data_api_json(path: str, params: dict[str, Any] | None = None) -> Any:
    return _fetch_json(_DATA_API_BASE_URL, path, params)


def _fetch_gamma_json(path: str, params: dict[str, Any] | None = None) -> Any:
    return _fetch_json(_GAMMA_BASE_URL, path, params)


def _fetch_json(base_url: str, path: str, params: dict[str, Any] | None = None) -> Any:
    query = urlencode({key: value for key, value in (params or {}).items() if value is not None}, doseq=True)
    url = f"{base_url}{path}"
    if query:
        url = f"{url}?{query}"
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "weather-pm/0.1"})
    try:
        with urlopen(request, timeout=_DEFAULT_TIMEOUT_SECONDS) as response:
            payload = response.read().decode("utf-8")
    except HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")
        except Exception:
            detail = ""
        raise RuntimeError(f"Polymarket request failed with HTTP {exc.code} for {url}: {detail[:200]}") from exc
    except URLError as exc:
        raise RuntimeError(f"Polymarket request failed for {url}: {exc}") from exc
    try:
        return json.loads(payload)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Polymarket returned invalid JSON for {url}") from exc


def _payload_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("data", "positions", "results", "markets"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def _traded_count(payload: Any) -> int:
    if isinstance(payload, dict):
        for key in ("count", "total", "totalCount", "total_count"):
            if key in payload:
                return int(_as_float(payload.get(key)))
    return len(_payload_items(payload))


def _position_from_payload(raw: dict[str, Any]) -> PolymarketPosition:
    event_slug = str(raw.get("eventSlug") or raw.get("event_slug") or raw.get("slug") or "")
    category = str(raw.get("category") or raw.get("categorySlug") or raw.get("category_slug") or "").strip().lower()
    if not category and event_slug:
        category = _fetch_gamma_event_category(event_slug)
    return PolymarketPosition(
        event_slug=event_slug,
        category=category or "unknown",
        realized_pnl=_as_float(raw.get("realizedPnl") or raw.get("realized_pnl") or raw.get("realizedPNL")),
        cash_pnl=_as_float(raw.get("cashPnl") or raw.get("cash_pnl") or raw.get("cashPNL")),
        status=_position_status(raw),
    )


def _fetch_gamma_event_category(event_slug: str) -> str:
    payload = _fetch_gamma_json("/events", {"slug": event_slug})
    candidates = _payload_items(payload)
    if isinstance(payload, dict):
        candidates = candidates or [payload]
    for event in candidates:
        category = str(event.get("category") or event.get("categorySlug") or event.get("category_slug") or "").strip().lower()
        if category:
            return category
        tags = event.get("tags")
        if isinstance(tags, list):
            for tag in tags:
                if isinstance(tag, dict):
                    label = str(tag.get("label") or tag.get("name") or tag.get("slug") or "").strip().lower()
                else:
                    label = str(tag).strip().lower()
                if label:
                    return label
    return "unknown"


def _position_status(raw: dict[str, Any]) -> str:
    if bool(raw.get("redeemable")):
        return "redeemable"
    return str(raw.get("status") or "active").strip().lower() or "active"


def _as_float(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return 0.0
    return 0.0


def _primary_category(totals: dict[str, dict[str, float | int]]) -> str | None:
    if not totals:
        return None
    return max(totals, key=lambda category: (float(totals[category]["pnl"]), int(totals[category]["trades"])))


def _profile_tags(primary_category: str | None, totals: dict[str, dict[str, float | int]]) -> list[str]:
    tags: list[str] = []
    if primary_category:
        tags.append(f"{primary_category}_leader")
    weather = totals.get("weather")
    if weather and float(weather.get("share", 0.0)) >= 0.5 and float(weather.get("pnl", 0.0)) > 0:
        tags.append("weather_specialist")
    return tags
