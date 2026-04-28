from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Mapping


class PolymarketFeeCategory(str, Enum):
    CRYPTO = "crypto"
    SPORTS = "sports"
    FINANCE = "finance"
    POLITICS = "politics"
    MENTIONS = "mentions"
    TECH = "tech"
    ECONOMICS = "economics"
    CULTURE = "culture"
    WEATHER = "weather"
    OTHER = "other"
    GEOPOLITICS = "geopolitics"


TAKER_FEE_RATES: dict[PolymarketFeeCategory, float] = {
    PolymarketFeeCategory.CRYPTO: 0.072,
    PolymarketFeeCategory.SPORTS: 0.03,
    PolymarketFeeCategory.FINANCE: 0.04,
    PolymarketFeeCategory.POLITICS: 0.04,
    PolymarketFeeCategory.MENTIONS: 0.04,
    PolymarketFeeCategory.TECH: 0.04,
    PolymarketFeeCategory.ECONOMICS: 0.05,
    PolymarketFeeCategory.CULTURE: 0.05,
    PolymarketFeeCategory.WEATHER: 0.05,
    PolymarketFeeCategory.OTHER: 0.05,
    PolymarketFeeCategory.GEOPOLITICS: 0.0,
}


@dataclass(frozen=True, slots=True)
class PolymarketFeeEstimate:
    shares: float
    price: float
    fee_rate: float
    fee_usdc: float
    liquidity_role: str
    formula: str = "shares * fee_rate * price * (1 - price)"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class PolymarketOrderValidation:
    ok: bool
    blockers: tuple[str, ...]
    price: float
    shares: float
    notional_usdc: float
    minimum_order_size_shares: float
    minimum_tick_size: float

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["blockers"] = list(self.blockers)
        return payload


@dataclass(frozen=True, slots=True)
class PolymarketMarketRules:
    minimum_order_size_shares: float = 5.0
    minimum_tick_size: float = 0.01
    category: PolymarketFeeCategory | str = PolymarketFeeCategory.OTHER
    maker_fee_rate: float = 0.0
    taker_fee_rate: float | None = None
    market_buy_min_notional_usdc: float = 1.0
    fee_precision_usdc: float = 0.00001

    def __post_init__(self) -> None:
        minimum_order_size = _positive_float(self.minimum_order_size_shares, "minimum_order_size_shares")
        minimum_tick_size = _positive_float(self.minimum_tick_size, "minimum_tick_size")
        category = normalize_polymarket_fee_category(self.category)
        maker_fee_rate = max(0.0, _finite_float(self.maker_fee_rate, "maker_fee_rate"))
        taker_fee_rate = self.taker_fee_rate
        if taker_fee_rate is None:
            taker_fee_rate = TAKER_FEE_RATES[category]
        else:
            taker_fee_rate = max(0.0, _finite_float(taker_fee_rate, "taker_fee_rate"))
        object.__setattr__(self, "minimum_order_size_shares", minimum_order_size)
        object.__setattr__(self, "minimum_tick_size", minimum_tick_size)
        object.__setattr__(self, "category", category)
        object.__setattr__(self, "maker_fee_rate", maker_fee_rate)
        object.__setattr__(self, "taker_fee_rate", taker_fee_rate)
        object.__setattr__(self, "market_buy_min_notional_usdc", max(0.0, _finite_float(self.market_buy_min_notional_usdc, "market_buy_min_notional_usdc")))
        object.__setattr__(self, "fee_precision_usdc", _positive_float(self.fee_precision_usdc, "fee_precision_usdc"))

    def minimum_notional_usdc(self, *, price: float) -> float:
        return round(self.minimum_order_size_shares * _valid_price(price), 8)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["category"] = self.category.value if isinstance(self.category, PolymarketFeeCategory) else str(self.category)
        return payload


def normalize_polymarket_fee_category(value: PolymarketFeeCategory | str | None) -> PolymarketFeeCategory:
    if isinstance(value, PolymarketFeeCategory):
        return value
    text = str(value or "other").strip().lower().replace(" / general", "").replace("/general", "")
    aliases = {
        "other / general": "other",
        "general": "other",
        "finance / politics / mentions / tech": "finance",
        "economics / culture / weather / other": "weather",
    }
    text = aliases.get(text, text)
    try:
        return PolymarketFeeCategory(text)
    except ValueError:
        return PolymarketFeeCategory.OTHER


def estimate_polymarket_fee(
    *,
    shares: float,
    price: float,
    category: PolymarketFeeCategory | str | None = PolymarketFeeCategory.OTHER,
    liquidity_role: str = "taker",
    fee_rate: float | None = None,
    precision_usdc: float = 0.00001,
) -> PolymarketFeeEstimate:
    safe_shares = _non_negative_float(shares, "shares")
    safe_price = _valid_price(price)
    role = str(liquidity_role or "taker").strip().lower()
    category_value = normalize_polymarket_fee_category(category)
    applied_rate = 0.0 if role == "maker" else (TAKER_FEE_RATES[category_value] if fee_rate is None else max(0.0, _finite_float(fee_rate, "fee_rate")))
    raw_fee = safe_shares * applied_rate * safe_price * (1.0 - safe_price)
    fee = _round_fee(raw_fee, precision_usdc=precision_usdc)
    return PolymarketFeeEstimate(shares=safe_shares, price=safe_price, fee_rate=applied_rate, fee_usdc=fee, liquidity_role="maker" if role == "maker" else "taker")


def normalize_polymarket_market_rules(market: Mapping[str, Any] | PolymarketMarketRules) -> PolymarketMarketRules:
    if isinstance(market, PolymarketMarketRules):
        return market
    category = market.get("category") or market.get("fee_category") or market.get("market_category") or PolymarketFeeCategory.OTHER
    maker_rate = _fee_rate_from_market(market.get("maker_fee_rate"), market.get("maker_base_fee"), default=0.0)
    taker_rate = _fee_rate_from_market(market.get("taker_fee_rate"), market.get("taker_base_fee"), default=None)
    return PolymarketMarketRules(
        minimum_order_size_shares=_float_or_default(market.get("minimum_order_size"), 5.0),
        minimum_tick_size=_float_or_default(market.get("minimum_tick_size"), 0.01),
        category=category,
        maker_fee_rate=maker_rate,
        taker_fee_rate=taker_rate,
        market_buy_min_notional_usdc=_float_or_default(market.get("market_buy_min_notional_usdc"), 1.0),
    )


def polymarket_order_size_for_notional(*, notional_usdc: float, price: float, rules: PolymarketMarketRules | Mapping[str, Any] | None = None) -> float:
    market_rules = normalize_polymarket_market_rules(rules or {})
    safe_notional = _positive_float(notional_usdc, "notional_usdc")
    safe_price = _valid_price(price)
    raw_shares = safe_notional / safe_price
    shares = math.floor(raw_shares / market_rules.minimum_tick_size) * market_rules.minimum_tick_size
    shares = round(shares, 8)
    if shares < market_rules.minimum_order_size_shares:
        raise ValueError("order size is below Polymarket minimum_order_size")
    return shares


def validate_polymarket_limit_order(
    *,
    price: float,
    shares: float,
    rules: PolymarketMarketRules | Mapping[str, Any] | None = None,
    market_buy: bool = False,
) -> PolymarketOrderValidation:
    market_rules = normalize_polymarket_market_rules(rules or {})
    safe_price = _finite_float(price, "price")
    safe_shares = _non_negative_float(shares, "shares")
    blockers: list[str] = []
    if not 0.0 < safe_price < 1.0:
        blockers.append("price_out_of_range")
    elif not _is_on_tick(safe_price, market_rules.minimum_tick_size):
        blockers.append("price_not_on_minimum_tick_size")
    if safe_shares < market_rules.minimum_order_size_shares:
        blockers.append("size_below_minimum_order_size")
    notional = round(max(0.0, safe_price) * safe_shares, 8)
    if market_buy and notional <= market_rules.market_buy_min_notional_usdc:
        blockers.append("market_buy_notional_below_ui_minimum")
    return PolymarketOrderValidation(
        ok=not blockers,
        blockers=tuple(blockers),
        price=safe_price,
        shares=safe_shares,
        notional_usdc=notional,
        minimum_order_size_shares=market_rules.minimum_order_size_shares,
        minimum_tick_size=market_rules.minimum_tick_size,
    )


def _round_fee(value: float, *, precision_usdc: float) -> float:
    precision = _positive_float(precision_usdc, "precision_usdc")
    if value < precision:
        return 0.0
    return round(round(value / precision) * precision, 5)


def _fee_rate_from_market(explicit: Any, base_fee: Any, *, default: float | None) -> float | None:
    explicit_value = _optional_float(explicit)
    if explicit_value is not None:
        return explicit_value
    base_value = _optional_float(base_fee)
    if base_value is None:
        return default
    # CLOB market objects often expose 1000 for a 0.05-rate category.
    # Keep category docs authoritative when base fee uses this protocol unit.
    return default


def _is_on_tick(price: float, tick: float) -> bool:
    units = round(price / tick)
    return math.isclose(price, units * tick, rel_tol=1e-9, abs_tol=1e-9)


def _valid_price(value: Any) -> float:
    number = _finite_float(value, "price")
    if not 0.0 < number < 1.0:
        raise ValueError("price must be finite and between 0 and 1")
    return number


def _positive_float(value: Any, name: str) -> float:
    number = _finite_float(value, name)
    if number <= 0.0:
        raise ValueError(f"{name} must be finite and positive")
    return number


def _non_negative_float(value: Any, name: str) -> float:
    number = _finite_float(value, name)
    if number < 0.0:
        raise ValueError(f"{name} must be finite and non-negative")
    return number


def _finite_float(value: Any, name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be finite") from exc
    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite")
    return number


def _optional_float(value: Any) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _float_or_default(value: Any, default: float) -> float:
    number = _optional_float(value)
    return default if number is None else number
