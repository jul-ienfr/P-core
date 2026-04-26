from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class SizingPolicy:
    name: str
    probe_min_usdc: float
    probe_max_usdc: float
    open_min_usdc: float
    open_max_usdc: float
    strong_max_usdc: float
    max_per_market_usdc: float
    max_per_surface_usdc: float
    max_total_weather_open_usdc: float
    min_net_edge_probe: float
    min_net_edge_open: float
    min_confidence_open: float
    max_good_spread: float
    min_good_depth_usd: float

    @classmethod
    def paper_weather_grid_default(cls) -> "SizingPolicy":
        return cls(
            name="paper_weather_grid_default",
            probe_min_usdc=1.0,
            probe_max_usdc=3.0,
            open_min_usdc=5.0,
            open_max_usdc=15.0,
            strong_max_usdc=30.0,
            max_per_market_usdc=15.0,
            max_per_surface_usdc=50.0,
            max_total_weather_open_usdc=250.0,
            min_net_edge_probe=0.03,
            min_net_edge_open=0.06,
            min_confidence_open=0.75,
            max_good_spread=0.08,
            min_good_depth_usd=50.0,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class SizingInput:
    market_id: str
    surface_key: str
    model_probability: float
    market_price: float
    net_edge: float
    confidence: float
    spread: float
    depth_usd: float
    hours_to_resolution: float | None
    wallet_style: str | None
    current_market_exposure_usdc: float
    current_surface_exposure_usdc: float
    current_total_weather_exposure_usdc: float


@dataclass(frozen=True, slots=True)
class DynamicSizingDecision:
    policy: str
    action: str
    recommended_size_usdc: float
    max_market_remaining_usdc: float
    max_surface_remaining_usdc: float
    max_total_remaining_usdc: float
    wallet_style_reference: str | None
    reasons: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# Optional alias for future portfolio-wide helpers.
ExposureState = SizingInput


def calculate_dynamic_position_size(
    sizing_input: SizingInput,
    *,
    policy: SizingPolicy | None = None,
) -> DynamicSizingDecision:
    policy = policy or SizingPolicy.paper_weather_grid_default()
    reasons: list[str] = []

    market_remaining = max(policy.max_per_market_usdc - sizing_input.current_market_exposure_usdc, 0.0)
    surface_remaining = max(policy.max_per_surface_usdc - sizing_input.current_surface_exposure_usdc, 0.0)
    total_remaining = max(policy.max_total_weather_open_usdc - sizing_input.current_total_weather_exposure_usdc, 0.0)
    cap_remaining = min(market_remaining, surface_remaining, total_remaining)

    if market_remaining <= 0.0:
        reasons.append("market_cap_reached")
    if surface_remaining <= 0.0:
        reasons.append("surface_cap_reached")
    if total_remaining <= 0.0:
        reasons.append("total_weather_cap_reached")
    if cap_remaining <= 0.0:
        return _decision(
            policy,
            "HOLD_CAPPED",
            0.0,
            market_remaining,
            surface_remaining,
            total_remaining,
            sizing_input.wallet_style,
            reasons,
        )

    if sizing_input.net_edge < policy.min_net_edge_probe:
        reasons.append("edge_below_probe")
        return _decision(
            policy,
            "NO_TRADE",
            0.0,
            market_remaining,
            surface_remaining,
            total_remaining,
            sizing_input.wallet_style,
            reasons,
        )

    execution_poor = sizing_input.spread > policy.max_good_spread or sizing_input.depth_usd < policy.min_good_depth_usd
    if execution_poor:
        reasons.append("execution_quality_poor")

    if sizing_input.confidence < policy.min_confidence_open:
        reasons.append("confidence_below_open")

    if execution_poor or sizing_input.confidence < policy.min_confidence_open or sizing_input.net_edge < policy.min_net_edge_open:
        size = min(policy.probe_max_usdc, cap_remaining)
        size = max(min(size, policy.probe_max_usdc), policy.probe_min_usdc) if cap_remaining >= policy.probe_min_usdc else 0.0
        return _decision(
            policy,
            "PROBE" if size > 0 else "HOLD_CAPPED",
            size,
            market_remaining,
            surface_remaining,
            total_remaining,
            sizing_input.wallet_style,
            reasons,
        )

    target = _edge_scaled_size(sizing_input.net_edge, policy)
    style = (sizing_input.wallet_style or "").lower()
    if "sparse/large-ticket" in style:
        reasons.append("large_ticket_style_capped")
        target = min(target, policy.open_max_usdc)
    elif "breadth/grid" in style:
        reasons.append("grid_style_reference")
    elif "selective" in style:
        reasons.append("selective_style_confidence_only")
        target = min(target, policy.open_max_usdc)

    size = min(target, cap_remaining)
    action = "ADD" if sizing_input.current_market_exposure_usdc > 0.0 else "OPEN"
    if size <= 0.0:
        action = "HOLD_CAPPED"
    return _decision(
        policy,
        action,
        size,
        market_remaining,
        surface_remaining,
        total_remaining,
        sizing_input.wallet_style,
        reasons,
    )


def build_exposure_index(positions: list[dict[str, Any]]) -> dict[str, Any]:
    by_market: dict[str, float] = {}
    by_surface: dict[str, float] = {}
    total = 0.0
    for row in positions:
        if not isinstance(row, dict):
            continue
        amount = _position_notional(row)
        if amount <= 0.0:
            continue
        market_id = str(row.get("market_id") or "").strip()
        surface_key = str(row.get("surface_key") or row.get("city_date_surface") or "").strip()
        if market_id:
            by_market[market_id] = round(by_market.get(market_id, 0.0) + amount, 4)
        if surface_key:
            by_surface[surface_key] = round(by_surface.get(surface_key, 0.0) + amount, 4)
        total += amount
    return {"by_market": by_market, "by_surface": by_surface, "total_weather": round(total, 4)}


def _position_notional(row: dict[str, Any]) -> float:
    for key in ("filled_usdc", "paper_notional_usd", "paper_notional_usdc", "notional_usdc", "spend_usdc"):
        value = row.get(key)
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                pass
    return 0.0


def _edge_scaled_size(net_edge: float, policy: SizingPolicy) -> float:
    if net_edge >= 0.18:
        return policy.strong_max_usdc
    if net_edge >= 0.10:
        return policy.open_max_usdc
    return policy.open_min_usdc


def _decision(
    policy: SizingPolicy,
    action: str,
    size: float,
    market_remaining: float,
    surface_remaining: float,
    total_remaining: float,
    wallet_style: str | None,
    reasons: list[str],
) -> DynamicSizingDecision:
    return DynamicSizingDecision(
        policy=policy.name,
        action=action,
        recommended_size_usdc=round(float(size), 4),
        max_market_remaining_usdc=round(float(market_remaining), 4),
        max_surface_remaining_usdc=round(float(surface_remaining), 4),
        max_total_remaining_usdc=round(float(total_remaining), 4),
        wallet_style_reference=wallet_style,
        reasons=list(reasons),
    )
