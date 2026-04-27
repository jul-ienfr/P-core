from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Mapping

from weather_pm.strategy_profiles import get_strategy_profile, list_strategy_profiles, strategy_id_for_profile

from .contracts import StrategyDescriptor, StrategyMode, StrategyRunRequest, StrategyRunResult, StrategySide, StrategySignal, StrategyTarget


def _mapping(payload: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = payload.get(key)
    return value if isinstance(value, Mapping) else {}


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _generated_at(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return datetime.now(UTC)


def _side(payload: Mapping[str, Any], gate_status: str) -> StrategySide:
    if gate_status != "fixture_profile_ready":
        return StrategySide.SKIP
    action = str(payload.get("action") or payload.get("side") or "unknown").lower()
    if action in {"yes", "buy", "paper_add", "paper_probe", "paper_trade"}:
        return StrategySide.YES
    if action in {"no", "sell"}:
        return StrategySide.NO
    return StrategySide.UNKNOWN


def _blockers(payload: Mapping[str, Any]) -> list[str]:
    raw = payload.get("blockers") or payload.get("execution_blockers") or []
    blockers = [raw] if isinstance(raw, str) else [str(item) for item in raw]
    portfolio_risk = payload.get("portfolio_risk") if isinstance(payload.get("portfolio_risk"), Mapping) else {}
    risk_blockers = portfolio_risk.get("blockers") if isinstance(portfolio_risk.get("blockers"), list) else []
    return [*blockers, *[str(item) for item in risk_blockers]]


def _missing_gates(payload: Mapping[str, Any], profile: Mapping[str, Any]) -> list[str]:
    satisfied = {str(item) for item in payload.get("satisfied_gates") or []}
    return [str(gate) for gate in profile.get("entry_gates") or [] if str(gate) not in satisfied]


def _gate_status(payload: Mapping[str, Any], profile: Mapping[str, Any], blockers: list[str], missing_gates: list[str]) -> str:
    if blockers:
        return "skip"
    if not payload.get("satisfied_gates") and payload.get("probability_yes") is None and payload.get("probability") is None and not _mapping(payload, "score"):
        return "not_enough_data"
    if missing_gates:
        return "not_enough_data"
    if payload.get("profile_gate_status"):
        return str(payload["profile_gate_status"])
    return "fixture_profile_ready"


def build_weather_profile_signal(
    payload: Mapping[str, Any],
    *,
    profile: Mapping[str, Any],
    strategy_id: str,
    mode: StrategyMode,
) -> StrategySignal:
    score = _mapping(payload, "score") or payload
    blockers = _blockers(payload)
    missing_gates = _missing_gates(payload, profile)
    gate_status = _gate_status(payload, profile, blockers, missing_gates)
    market_id = str(payload.get("market_id") or score.get("market_id") or "unknown")
    probability = _float_or_none(score.get("probability_yes", score.get("probability", score.get("forecast_probability"))))
    confidence = float(score.get("confidence", payload.get("confidence", 0.0)) or 0.0)
    edge = _float_or_none(score.get("edge", score.get("probability_edge", payload.get("edge", payload.get("probability_edge")))))
    risk_caps = profile.get("risk_caps") if isinstance(profile.get("risk_caps"), Mapping) else {}
    risks = ["paper/research profile adapter; no live execution", *blockers]
    portfolio_risk = payload.get("portfolio_risk") if isinstance(payload.get("portfolio_risk"), Mapping) else {}
    risks.extend(str(reason) for reason in portfolio_risk.get("reasons") or [])
    if missing_gates:
        risks.append("missing profile entry gates: " + ", ".join(missing_gates))
    if gate_status == "not_enough_data":
        risks.append("not enough profile fixture data")
    return StrategySignal(
        strategy_id=strategy_id,
        market_id=market_id,
        target=StrategyTarget.EVENT_OUTCOME_FORECASTING,
        mode=mode,
        generated_at=_generated_at(payload.get("generated_at")),
        side=_side(payload, gate_status),
        probability=probability,
        confidence=confidence,
        expected_move=edge,
        features={
            "profile_id": profile["id"],
            "profile_label": profile["label"],
            "execution_mode": profile["execution_mode"],
            "required_inputs": list(profile.get("required_inputs") or []),
            "entry_gates": list(profile.get("entry_gates") or []),
            "satisfied_gates": list(payload.get("satisfied_gates") or []),
            "missing_gates": missing_gates,
            "blockers": blockers,
            "risk_caps": dict(risk_caps),
            "token_id": payload.get("token_id") or score.get("token_id"),
            "market_price": score.get("market_price"),
            "best_bid": score.get("best_bid"),
            "best_ask": score.get("best_ask"),
            "spread": score.get("spread"),
            "liquidity_usd": score.get("liquidity_usd"),
            "probability_source": score.get("probability_source") or payload.get("probability_source"),
            "probability_method": score.get("probability_method") or payload.get("probability_method"),
            "probability_synthetic": score.get("probability_synthetic") if score.get("probability_synthetic") is not None else payload.get("probability_synthetic"),
            "probability_market_derived": score.get("probability_market_derived") if score.get("probability_market_derived") is not None else payload.get("probability_market_derived"),
            "probability_confidence": score.get("probability_confidence") or payload.get("probability_confidence"),
            "probability_error": score.get("probability_error") or payload.get("probability_error"),
            "forecast_source_provider": score.get("forecast_source_provider") or payload.get("forecast_source_provider"),
            "forecast_source_station_code": score.get("forecast_source_station_code") or payload.get("forecast_source_station_code"),
            "forecast_source_url": score.get("forecast_source_url") or payload.get("forecast_source_url"),
            "forecast_source_latency_tier": score.get("forecast_source_latency_tier") or payload.get("forecast_source_latency_tier"),
            "feature_family": score.get("feature_family"),
            "portfolio_risk": dict(portfolio_risk) if portfolio_risk else {},
        },
        risks=risks,
        source={"adapter": "weather_profile_strategy", "profile_id": profile["id"], "references": list(payload.get("source_references") or [])},
        metadata={"gate_status": gate_status, "profile_inspiration": profile.get("inspiration"), "do_not_trade_rules": list(profile.get("do_not_trade_rules") or [])},
        gate_status=gate_status,
    )


class WeatherProfileStrategy:
    def __init__(self, profile_id: str, payloads: list[Mapping[str, Any]] | None = None, *, mode: StrategyMode | str = StrategyMode.PAPER_ONLY) -> None:
        resolved_mode = mode if isinstance(mode, StrategyMode) else StrategyMode(str(mode))
        if resolved_mode == StrategyMode.LIVE_ALLOWED:
            raise ValueError("WeatherProfileStrategy is paper/research only")
        self.profile = get_strategy_profile(profile_id)
        self.payloads = list(payloads or [])
        self.descriptor = StrategyDescriptor(
            strategy_id=strategy_id_for_profile(str(self.profile["id"])),
            name=self.profile["label"],
            target=StrategyTarget.EVENT_OUTCOME_FORECASTING,
            mode=resolved_mode,
            source="weather_pm.strategy_profiles",
            description=self.profile["inspiration"],
            metadata={
                "execution_mode": self.profile["execution_mode"],
                "risk_caps": self.profile["risk_caps"],
                "required_inputs": self.profile["required_inputs"],
                "entry_gates": self.profile["entry_gates"],
                "do_not_trade_rules": self.profile["do_not_trade_rules"],
            },
        )

    def run(self, request: StrategyRunRequest) -> StrategyRunResult:
        payloads = self.payloads or [request.payload]
        signals = [
            build_weather_profile_signal(
                {**dict(payload), "market_id": dict(payload).get("market_id", request.market_id)},
                profile=self.profile,
                strategy_id=self.descriptor.strategy_id,
                mode=self.descriptor.mode,
            )
            for payload in payloads
        ]
        return StrategyRunResult(strategy_id=self.descriptor.strategy_id, market_id=request.market_id, mode=self.descriptor.mode, signals=signals)


def build_weather_profile_strategies(
    payloads_by_profile: Mapping[str, list[Mapping[str, Any]] | Mapping[str, Any]] | None = None,
    *,
    mode: StrategyMode | str = StrategyMode.PAPER_ONLY,
) -> list[WeatherProfileStrategy]:
    payloads_by_profile = payloads_by_profile or {}
    strategies: list[WeatherProfileStrategy] = []
    for profile in list_strategy_profiles():
        raw_payloads = payloads_by_profile.get(profile["id"], [])
        payloads = [raw_payloads] if isinstance(raw_payloads, Mapping) else list(raw_payloads)
        strategies.append(WeatherProfileStrategy(profile["id"], payloads=payloads, mode=mode))
    return strategies


__all__ = ["WeatherProfileStrategy", "build_weather_profile_signal", "build_weather_profile_strategies"]
