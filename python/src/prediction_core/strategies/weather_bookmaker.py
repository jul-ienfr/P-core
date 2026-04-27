from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Mapping

from .contracts import StrategyDescriptor, StrategyMode, StrategyRunRequest, StrategyRunResult, StrategySide, StrategySignal, StrategyTarget


def _mapping(payload: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = payload.get(key)
    return value if isinstance(value, Mapping) else {}


def _float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    return float(value)


def _generated_at(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return datetime.now(UTC)


def _execution_blockers(execution: Mapping[str, Any]) -> list[str]:
    blockers: list[str] = []
    reason = execution.get("best_effort_reason") or execution.get("execution_blocker")
    if reason:
        blockers.append(str(reason))
    spread = execution.get("spread")
    if spread is not None and _float(spread) > 0.07:
        blockers.append("spread_too_wide")
    depth = execution.get("fillable_size_usd", execution.get("depth_usd"))
    if depth is not None and _float(depth) < 25.0:
        blockers.append("insufficient_executable_depth")
    return list(dict.fromkeys(blockers))


def build_weather_bookmaker_signal(payload: Mapping[str, Any], *, strategy_id: str = "weather_bookmaker_v1") -> StrategySignal:
    """Build a paper-only meta-signal from weather, wallet, surface and execution inputs.

    This v1 is intentionally conservative: it never allocates real capital and it
    hard-skips execution blockers before rewarding confirming signals.
    """

    weather = _mapping(payload, "weather") or _mapping(payload, "score")
    wallets = _mapping(payload, "profitable_wallets") or _mapping(payload, "wallets")
    surface = _mapping(payload, "event_surface") or _mapping(payload, "surface")
    execution = _mapping(payload, "execution")
    resolution = _mapping(payload, "resolution") or _mapping(payload, "source_route")

    market_id = str(payload.get("market_id") or weather.get("market_id") or "unknown")
    probability = _float(weather.get("probability_yes", weather.get("probability", payload.get("probability_yes"))), 0.5)
    market_price = _float(payload.get("market_price", weather.get("market_price", weather.get("market_implied_yes_probability"))), 0.5)
    edge = _float(weather.get("edge", weather.get("probability_edge", probability - market_price)), probability - market_price)
    weather_confidence = _float(weather.get("confidence"), 0.0)

    blockers = _execution_blockers(execution)
    reasons: list[str] = []
    if edge >= 0.05:
        reasons.append("forecast_edge_positive")
    if bool(resolution.get("source_direct") or resolution.get("direct") or resolution.get("source_latest_url")):
        reasons.append("direct_resolution_source")
    if _float(wallets.get("matched_count", wallets.get("matched_profitable_weather_count")), 0.0) > 0 and str(wallets.get("alignment", "yes")).lower() not in {"none", "no", "against"}:
        reasons.append("profitable_wallet_alignment")
    if _float(surface.get("inconsistency_count", surface.get("surface_inconsistency_count")), 0.0) > 0:
        reasons.append("surface_anomaly_support")
    if not blockers and _float(execution.get("fillable_size_usd", execution.get("depth_usd")), 0.0) >= 25.0:
        reasons.append("execution_depth_ok")

    confirming = sum(1 for item in ("profitable_wallet_alignment", "surface_anomaly_support") if item in reasons)
    if blockers or edge < 0.02:
        decision = "SKIP"
        gate_status = "skip"
        side = StrategySide.SKIP
    elif edge >= 0.05 and "direct_resolution_source" in reasons and "execution_depth_ok" in reasons and confirming > 0:
        decision = "PAPER_ADD"
        gate_status = "paper_add"
        side = StrategySide.YES
    elif edge >= 0.05 and "execution_depth_ok" in reasons:
        decision = "PAPER_PROBE"
        gate_status = "paper_probe"
        side = StrategySide.YES
    else:
        decision = "HOLD"
        gate_status = "hold"
        side = StrategySide.UNKNOWN

    confirmation_bonus = 0.08 * confirming + (0.04 if "direct_resolution_source" in reasons else 0.0) + (0.04 if "execution_depth_ok" in reasons else 0.0)
    confidence = min(1.0, max(0.0, weather_confidence + confirmation_bonus - (0.25 if blockers else 0.0)))
    features = {
        "decision": decision,
        "paper_only": True,
        "market_price": market_price,
        "net_edge": edge,
        "weather_confidence": weather_confidence,
        "reasons": reasons,
        "blockers": blockers,
        "inputs": {
            "weather": dict(weather),
            "profitable_wallets": dict(wallets),
            "event_surface": dict(surface),
            "execution": dict(execution),
            "resolution": dict(resolution),
        },
    }
    risks = blockers or ["weather_bookmaker_v1 is paper-only; no real order"]
    return StrategySignal(
        strategy_id=strategy_id,
        market_id=market_id,
        target=StrategyTarget.EVENT_OUTCOME_FORECASTING,
        mode=StrategyMode.PAPER_ONLY,
        generated_at=_generated_at(payload.get("generated_at")),
        side=side,
        probability=probability,
        confidence=confidence,
        expected_move=edge,
        features=features,
        risks=risks,
        source={"adapter": "weather_bookmaker_v1"},
        metadata={"gate_status": gate_status, "decision": decision},
        gate_status=gate_status,
    )


class WeatherBookmakerStrategy:
    def __init__(self, payloads: list[Mapping[str, Any]] | None = None) -> None:
        self.payloads = list(payloads or [])
        self.descriptor = StrategyDescriptor(
            strategy_id="weather_bookmaker_v1",
            name="Weather bookmaker v1",
            target=StrategyTarget.EVENT_OUTCOME_FORECASTING,
            mode=StrategyMode.PAPER_ONLY,
            source="prediction_core.strategies.weather_bookmaker",
            description="Paper-only meta-strategy combining weather edge, profitable-wallet alignment, event-surface support, source quality, and execution blockers.",
        )

    def run(self, request: StrategyRunRequest) -> StrategyRunResult:
        rows = self.payloads or [request.payload]
        signals = [build_weather_bookmaker_signal({**dict(row), "market_id": dict(row).get("market_id", request.market_id)}, strategy_id=self.descriptor.strategy_id) for row in rows]
        return StrategyRunResult(strategy_id=self.descriptor.strategy_id, market_id=request.market_id, mode=self.descriptor.mode, signals=signals)


__all__ = ["WeatherBookmakerStrategy", "build_weather_bookmaker_signal"]
