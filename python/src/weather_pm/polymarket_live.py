from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from weather_pm.market_parser import parse_market_question

_GAMMA_BASE_URL = "https://gamma-api.polymarket.com"
_CLOB_BASE_URL = "https://clob.polymarket.com"
_DEFAULT_TIMEOUT_SECONDS = 20
_NULL_STRINGS = {"", "null", "none", "n/a"}
_WEATHER_TOKENS = (
    "temperature",
    "highest temperature",
    "lowest temperature",
    "high temperature",
    "low temperature",
    "degrees",
    "fahrenheit",
    "celsius",
    "weather",
)


def _fetch_gamma_json(path: str, params: dict[str, Any] | None = None) -> Any:
    query = urlencode({key: value for key, value in (params or {}).items() if value is not None}, doseq=True)
    url = f"{_GAMMA_BASE_URL}{path}"
    if query:
        url = f"{url}?{query}"

    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "weather-pm/0.1",
        },
    )
    try:
        with urlopen(request, timeout=_DEFAULT_TIMEOUT_SECONDS) as response:
            payload = response.read().decode("utf-8")
    except HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")
        except Exception:
            detail = ""
        raise RuntimeError(f"Gamma request failed with HTTP {exc.code} for {url}: {detail[:200]}") from exc
    except URLError as exc:
        raise RuntimeError(f"Gamma request failed for {url}: {exc}") from exc

    try:
        return json.loads(payload)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Gamma returned invalid JSON for {url}") from exc



def _fetch_clob_json(path: str, params: dict[str, Any] | None = None, *, timeout_seconds: float = 2.0) -> Any:
    query = urlencode({key: value for key, value in (params or {}).items() if value is not None}, doseq=True)
    url = f"{_CLOB_BASE_URL}{path}"
    if query:
        url = f"{url}?{query}"

    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36 weather-pm/0.1",
        },
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            payload = response.read().decode("utf-8")
    except HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")
        except Exception:
            detail = ""
        raise RuntimeError(f"CLOB request failed with HTTP {exc.code} for {url}: {detail[:200]}") from exc
    except URLError as exc:
        raise RuntimeError(f"CLOB request failed for {url}: {exc}") from exc

    try:
        return json.loads(payload)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"CLOB returned invalid JSON for {url}") from exc



def _fetch_clob_book(token_id: str, *, timeout_seconds: float = 2.0) -> dict[str, Any]:
    payload = _fetch_clob_json("/book", params={"token_id": token_id}, timeout_seconds=timeout_seconds)
    if not isinstance(payload, dict):
        raise RuntimeError(f"CLOB /book response for token {token_id} was not an object")
    return payload


def _fetch_gamma_markets(*, limit: int, active: bool, closed: bool) -> list[dict[str, Any]]:
    payload = _fetch_gamma_json(
        "/markets",
        params={
            "limit": max(int(limit), 1),
            "active": str(bool(active)).lower(),
            "closed": str(bool(closed)).lower(),
        },
    )
    if not isinstance(payload, list):
        raise RuntimeError("Gamma /markets response was not a list")
    return [item for item in payload if isinstance(item, dict)]


def _fetch_gamma_market(market_id: str) -> dict[str, Any]:
    payload = _fetch_gamma_json(f"/markets/{market_id}")
    if not isinstance(payload, dict):
        raise RuntimeError(f"Gamma /markets/{market_id} response was not an object")
    return payload


def _parse_jsonish_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.lower() in _NULL_STRINGS:
            return []
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            return []
        if isinstance(parsed, list):
            return parsed
        if parsed is None:
            return []
    return []


def _as_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.lower() in _NULL_STRINGS:
            return default
        try:
            return float(stripped)
        except ValueError:
            return default
    return default


def _compute_hours_to_resolution(raw: dict[str, Any]) -> float | None:
    resolution_value = (
        raw.get("endDate")
        or raw.get("end_date")
        or raw.get("resolutionDate")
        or raw.get("resolution_date")
        or raw.get("resolveDate")
        or raw.get("resolve_date")
        or raw.get("closedTime")
        or raw.get("closeTime")
    )
    if resolution_value in (None, ""):
        return None

    resolved_at: datetime | None = None
    if isinstance(resolution_value, (int, float)):
        timestamp = float(resolution_value)
        if timestamp > 1_000_000_000_000:
            timestamp /= 1000.0
        try:
            resolved_at = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    elif isinstance(resolution_value, str):
        stripped = resolution_value.strip()
        if stripped.lower() in _NULL_STRINGS:
            return None
        normalized = stripped.replace("Z", "+00:00")
        try:
            resolved_at = datetime.fromisoformat(normalized)
        except ValueError:
            return None
        if resolved_at.tzinfo is None:
            resolved_at = resolved_at.replace(tzinfo=timezone.utc)
    else:
        return None

    hours = (resolved_at.astimezone(timezone.utc) - datetime.now(timezone.utc)).total_seconds() / 3600.0
    return round(hours, 2)


def _infer_yes_index(raw: dict[str, Any]) -> int:
    outcomes = _parse_jsonish_list(raw.get("outcomes"))
    if not outcomes:
        return 0

    normalized = [str(item).strip().lower() for item in outcomes]
    for idx, outcome in enumerate(normalized):
        if outcome in {"yes", "true"}:
            return idx
    for idx, outcome in enumerate(normalized):
        if outcome.startswith("yes"):
            return idx

    if len(normalized) == 2:
        for idx, outcome in enumerate(normalized):
            if outcome in {"no", "false"}:
                return 1 - idx
        return 0

    return 0


def _looks_like_weather_market(raw: dict[str, Any]) -> bool:
    question = str(raw.get("question") or raw.get("title") or "").strip()
    if not question:
        return False

    lowered_question = question.lower()
    category = raw.get("category")
    category_lower = str(category).strip().lower() if category is not None else ""
    text_parts = [
        lowered_question,
        category_lower,
        str(raw.get("description") or "").lower(),
        str(raw.get("rules") or "").lower(),
        str(raw.get("resolutionSource") or raw.get("resolution_source") or "").lower(),
    ]
    searchable = " ".join(part for part in text_parts if part)

    if not any(token in searchable for token in _WEATHER_TOKENS):
        return False

    try:
        parse_market_question(question)
    except ValueError:
        return False
    return True



def _matches_requested_state(raw: dict[str, Any], *, active: bool, closed: bool) -> bool:
    if bool(raw.get("archived")):
        return False
    if not closed and bool(raw.get("closed")):
        return False
    if active and raw.get("active") is False:
        return False
    return True



def _pick_yes_price(raw: dict[str, Any], yes_index: int) -> float:
    prices = _parse_jsonish_list(raw.get("outcomePrices") or raw.get("outcome_prices"))
    if yes_index < len(prices):
        return _as_float(prices[yes_index])
    for key in ("yes_price", "lastTradePrice", "last_trade_price", "price"):
        if key in raw:
            return _as_float(raw.get(key))
    return 0.0



def _pick_best_bid(raw: dict[str, Any], yes_index: int) -> float:
    bid_candidates = (
        raw.get("bestBids"),
        raw.get("best_bids"),
        raw.get("topBids"),
        raw.get("top_bids"),
    )
    for candidate in bid_candidates:
        bids = _parse_jsonish_list(candidate)
        if yes_index < len(bids):
            return _as_float(bids[yes_index])
    for key in ("bestBid", "best_bid", "topBid", "top_bid", "bid"):
        if key in raw:
            return _as_float(raw.get(key))
    return 0.0



def _pick_best_ask(raw: dict[str, Any], yes_index: int) -> float:
    ask_candidates = (
        raw.get("bestAsks"),
        raw.get("best_asks"),
        raw.get("topAsks"),
        raw.get("top_asks"),
    )
    for candidate in ask_candidates:
        asks = _parse_jsonish_list(candidate)
        if yes_index < len(asks):
            return _as_float(asks[yes_index])
    for key in ("bestAsk", "best_ask", "topAsk", "top_ask", "ask"):
        if key in raw:
            return _as_float(raw.get(key))
    return 0.0



def _pick_yes_token_id(raw: dict[str, Any], yes_index: int) -> str | None:
    token_ids = _parse_jsonish_list(raw.get("clobTokenIds") or raw.get("clob_token_ids") or raw.get("tokenIds") or raw.get("token_ids"))
    if yes_index >= len(token_ids):
        return None
    token_id = str(token_ids[yes_index]).strip()
    return token_id or None



def _normalize_book_levels(levels: Any) -> list[dict[str, float]]:
    if not isinstance(levels, list):
        return []

    normalized: list[dict[str, float]] = []
    for level in levels:
        if not isinstance(level, dict):
            continue
        price = _as_float(level.get("price"))
        size = _as_float(level.get("size"))
        if price <= 0.0 or size <= 0.0:
            continue
        normalized.append({"price": price, "size": size})
    return normalized



def _sum_book_depth_usd(levels: list[dict[str, float]]) -> float:
    return round(sum(level["price"] * level["size"] for level in levels), 2)



def _extract_clob_book_metrics(raw: dict[str, Any], yes_index: int) -> dict[str, Any]:
    token_id = _pick_yes_token_id(raw, yes_index)
    if not token_id:
        return {
            "clob_token_id": None,
            "bids": [],
            "asks": [],
            "best_bid": None,
            "best_ask": None,
            "best_bid_size": None,
            "best_ask_size": None,
            "bid_depth_usd": 0.0,
            "ask_depth_usd": 0.0,
        }

    try:
        book = _fetch_clob_book(token_id)
    except (RuntimeError, TimeoutError, OSError) as exc:
        if isinstance(exc, RuntimeError) and "HTTP 404" not in str(exc) and "timed out" not in str(exc).lower():
            raise
        return {
            "clob_token_id": token_id,
            "bids": [],
            "asks": [],
            "best_bid": None,
            "best_ask": None,
            "best_bid_size": None,
            "best_ask_size": None,
            "bid_depth_usd": 0.0,
            "ask_depth_usd": 0.0,
        }

    bids = _normalize_book_levels(book.get("bids"))
    asks = _normalize_book_levels(book.get("asks"))
    return {
        "clob_token_id": token_id,
        "bids": bids,
        "asks": asks,
        "best_bid": bids[0]["price"] if bids else None,
        "best_ask": asks[0]["price"] if asks else None,
        "best_bid_size": bids[0]["size"] if bids else None,
        "best_ask_size": asks[0]["size"] if asks else None,
        "bid_depth_usd": _sum_book_depth_usd(bids),
        "ask_depth_usd": _sum_book_depth_usd(asks),
    }



def _normalize_gamma_market(raw: dict[str, Any]) -> dict[str, Any]:
    question = str(raw.get("question") or raw.get("title") or "").strip()
    yes_index = _infer_yes_index(raw)
    book_metrics = _extract_clob_book_metrics(raw, yes_index)
    best_bid = book_metrics["best_bid"] if book_metrics["best_bid"] is not None else _pick_best_bid(raw, yes_index)
    best_ask = book_metrics["best_ask"] if book_metrics["best_ask"] is not None else _pick_best_ask(raw, yes_index)
    description = raw.get("description") or raw.get("marketDescription") or raw.get("descriptionMarkdown")
    rules = raw.get("rules") or raw.get("resolutionCriteria") or raw.get("resolution_criteria") or raw.get("clarification") or description
    resolution_source = raw.get("resolutionSource") or raw.get("resolution_source") or raw.get("resolutionCriteria") or rules or description
    market_id = raw.get("id") or raw.get("conditionId") or raw.get("condition_id") or raw.get("slug") or ""

    return {
        "id": str(market_id),
        "category": "weather",
        "question": question,
        "yes_price": _pick_yes_price(raw, yes_index),
        "best_bid": best_bid,
        "best_ask": best_ask,
        "best_bid_size": book_metrics["best_bid_size"],
        "best_ask_size": book_metrics["best_ask_size"],
        "bid_depth_usd": book_metrics["bid_depth_usd"],
        "ask_depth_usd": book_metrics["ask_depth_usd"],
        "bids": book_metrics["bids"],
        "asks": book_metrics["asks"],
        "clob_token_id": book_metrics["clob_token_id"],
        "volume": _as_float(raw.get("volume") or raw.get("volumeNum") or raw.get("liquidityClob") or raw.get("liquidity")),
        "hours_to_resolution": _compute_hours_to_resolution(raw),
        "resolution_source": resolution_source,
        "description": description,
        "rules": rules,
    }


def _merge_market_with_event_context(raw_market: dict[str, Any], raw_event: dict[str, Any]) -> dict[str, Any]:
    merged = dict(raw_event)
    merged.update(raw_market)
    for field in (
        "description",
        "marketDescription",
        "descriptionMarkdown",
        "rules",
        "resolutionCriteria",
        "resolution_criteria",
        "clarification",
        "resolutionSource",
        "resolution_source",
        "endDate",
        "end_date",
        "resolutionDate",
        "resolution_date",
        "resolveDate",
        "resolve_date",
        "closedTime",
        "closeTime",
    ):
        if raw_market.get(field) in (None, "") and raw_event.get(field) not in (None, ""):
            merged[field] = raw_event[field]

    fallback_text = (
        merged.get("description")
        or merged.get("marketDescription")
        or merged.get("descriptionMarkdown")
    )
    if merged.get("resolutionSource") in (None, "") and merged.get("resolution_source") in (None, "") and fallback_text not in (None, ""):
        merged["resolutionSource"] = fallback_text
    if merged.get("rules") in (None, "") and fallback_text not in (None, ""):
        merged["rules"] = fallback_text
    return merged


def _should_fetch_event_details(raw_event: dict[str, Any]) -> bool:
    event_id = str(raw_event.get("id") or "").strip().lower()
    if event_id.startswith("event-") or event_id.isdigit():
        return True
    for field in ("marketsCount", "marketCount", "markets_count", "market_count"):
        count = raw_event.get(field)
        if isinstance(count, (int, float)) and count > 0:
            return True
        if isinstance(count, str):
            stripped = count.strip()
            if stripped.isdigit() and int(stripped) > 0:
                return True
    return False


def _normalize_gamma_series_event(raw: dict[str, Any]) -> dict[str, Any]:
    description = raw.get("description") or raw.get("marketDescription") or raw.get("descriptionMarkdown")
    resolution_source = raw.get("resolutionSource") or raw.get("resolution_source") or description
    yes_index = _infer_yes_index(raw)
    book_metrics = _extract_clob_book_metrics(raw, yes_index)
    return {
        "id": str(raw.get("id") or raw.get("slug") or ""),
        "category": "weather",
        "question": str(raw.get("question") or raw.get("title") or "").strip(),
        "yes_price": _pick_yes_price(raw, yes_index),
        "best_bid": book_metrics["best_bid"] if book_metrics["best_bid"] is not None else _pick_best_bid(raw, yes_index),
        "best_ask": book_metrics["best_ask"] if book_metrics["best_ask"] is not None else _pick_best_ask(raw, yes_index),
        "best_bid_size": book_metrics["best_bid_size"],
        "best_ask_size": book_metrics["best_ask_size"],
        "bid_depth_usd": book_metrics["bid_depth_usd"],
        "ask_depth_usd": book_metrics["ask_depth_usd"],
        "bids": book_metrics["bids"],
        "asks": book_metrics["asks"],
        "clob_token_id": book_metrics["clob_token_id"],
        "volume": _as_float(raw.get("volume") or raw.get("openInterest") or raw.get("liquidity")),
        "hours_to_resolution": _compute_hours_to_resolution(raw),
        "resolution_source": resolution_source,
        "description": description,
        "rules": raw.get("rules") or raw.get("resolutionCriteria") or raw.get("resolution_criteria") or raw.get("clarification") or description,
    }



def list_live_weather_markets(limit: int = 100, active: bool = True, closed: bool = False) -> list[dict[str, Any]]:
    raw_markets = _fetch_gamma_markets(limit=limit, active=active, closed=closed)
    normalized: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for raw_market in raw_markets:
        if not _matches_requested_state(raw_market, active=active, closed=closed):
            continue
        if not _looks_like_weather_market(raw_market):
            continue
        normalized_market = _normalize_gamma_market(raw_market)
        market_id = str(normalized_market.get("id") or "")
        if market_id and market_id in seen_ids:
            continue
        if market_id:
            seen_ids.add(market_id)
        normalized.append(normalized_market)
        if len(normalized) >= limit:
            break

    page_size = max(int(limit), 1)
    offset = 0
    while len(normalized) < limit:
        series_payload = _fetch_gamma_json("/series", params={"limit": page_size, "offset": offset})
        if not isinstance(series_payload, list) or not series_payload:
            break
        for series in series_payload:
            if not isinstance(series, dict):
                continue
            for event in series.get("events") or []:
                if not isinstance(event, dict):
                    continue
                if not _matches_requested_state(event, active=active, closed=closed):
                    continue
                if not _looks_like_weather_market(event):
                    continue

                child_markets = event.get("markets") or []
                if not child_markets and _should_fetch_event_details(event) and event.get("id") not in (None, ""):
                    try:
                        event_payload = _fetch_gamma_json(f"/events/{event['id']}")
                    except RuntimeError:
                        event_payload = None
                    if isinstance(event_payload, dict):
                        child_markets = event_payload.get("markets") or []
                emitted_child_market = False
                for child_market in child_markets:
                    if not isinstance(child_market, dict):
                        continue
                    if not _matches_requested_state(child_market, active=active, closed=closed):
                        continue
                    contextual_child_market = _merge_market_with_event_context(child_market, event)
                    if not _looks_like_weather_market(contextual_child_market):
                        continue
                    normalized_market = _normalize_gamma_market(contextual_child_market)
                    market_id = str(normalized_market.get("id") or "")
                    if market_id and market_id in seen_ids:
                        continue
                    if market_id:
                        seen_ids.add(market_id)
                    normalized.append(normalized_market)
                    emitted_child_market = True
                    if len(normalized) >= limit:
                        return normalized[:limit]
                if emitted_child_market:
                    continue

                normalized_event = _normalize_gamma_series_event(event)
                event_id = str(normalized_event.get("id") or "")
                if event_id and event_id in seen_ids:
                    continue
                if event_id:
                    seen_ids.add(event_id)
                normalized.append(normalized_event)
                if len(normalized) >= limit:
                    return normalized[:limit]
        if len(series_payload) < page_size:
            break
        offset += len(series_payload)
    return normalized[:limit]



def get_live_market_by_id(market_id: str) -> dict[str, Any]:
    try:
        raw_market = _fetch_gamma_market(market_id)
    except RuntimeError as exc:
        if "HTTP 404" not in str(exc):
            raise
        event_payload = _fetch_gamma_json(f"/events/{market_id}")
        if not isinstance(event_payload, dict):
            raise RuntimeError(f"Gamma /events/{market_id} response was not an object") from exc
        if not _looks_like_weather_market(event_payload):
            raise KeyError(f"Market {market_id} is not recognized as a supported weather market") from exc
        return _normalize_gamma_series_event(event_payload)

    if not _looks_like_weather_market(raw_market):
        raise KeyError(f"Market {market_id} is not recognized as a supported weather market")
    return _normalize_gamma_market(raw_market)


def get_live_event_book_by_id(event_id: str) -> dict[str, Any]:
    event_payload = _fetch_gamma_json(f"/events/{event_id}")
    if not isinstance(event_payload, dict):
        raise RuntimeError(f"Gamma /events/{event_id} response was not an object")

    child_markets = event_payload.get("markets") or []
    normalized_markets = []
    for market in child_markets:
        if not isinstance(market, dict):
            continue
        contextual_market = _merge_market_with_event_context(market, event_payload)
        if not _looks_like_weather_market(contextual_market):
            continue
        normalized_markets.append(_normalize_gamma_market(contextual_market))
    if not normalized_markets:
        raise KeyError(f"Event {event_id} is not recognized as a supported weather event")

    question = str(event_payload.get("question") or event_payload.get("title") or "").strip()
    description = event_payload.get("description") or event_payload.get("marketDescription") or event_payload.get("descriptionMarkdown")
    resolution_source = event_payload.get("resolutionSource") or event_payload.get("resolution_source") or description
    rules = event_payload.get("rules") or event_payload.get("resolutionCriteria") or event_payload.get("resolution_criteria") or event_payload.get("clarification") or description
    return {
        "id": str(event_payload.get("id") or event_id),
        "category": "weather",
        "question": question,
        "description": description,
        "resolution_source": resolution_source,
        "rules": rules,
        "markets": normalized_markets,
    }


__all__ = [
    "list_live_weather_markets",
    "get_live_market_by_id",
    "get_live_event_book_by_id",
    "_parse_jsonish_list",
    "_as_float",
    "_compute_hours_to_resolution",
    "_infer_yes_index",
    "_looks_like_weather_market",
    "_pick_yes_token_id",
    "_normalize_book_levels",
    "_fetch_clob_book",
    "_normalize_gamma_market",
    "_normalize_gamma_series_event",
]
