from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class PredictionMarketAdapterCapability:
    adapter_id: str
    venue: str
    language: str
    allowed_modes: tuple[str, ...] = ("read_only", "paper")
    read_only: bool = True
    paper_only: bool = True
    live_order_allowed: bool = False
    supports_market_discovery: bool = False
    supports_orderbook: bool = False
    supports_replay: bool = False
    supports_paper: bool = False
    blocks_live_execution_reason: str = "live execution requires separate approval outside this boundary contract"

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["allowed_modes"] = list(self.allowed_modes)
        return payload


@dataclass(frozen=True, slots=True)
class AdapterBoundaryPolicy:
    allow_market_discovery: bool = True
    allow_orderbook: bool = True
    allow_replay: bool = True
    allow_paper: bool = True
    allow_live_execution: bool = False
    approval_reference: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class AuditResult:
    candidate_id: str
    capability: PredictionMarketAdapterCapability
    metadata_only: bool = True
    imported_dependency: bool = False
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["capability"] = self.capability.to_dict()
        payload["notes"] = list(self.notes)
        return payload


@dataclass(frozen=True, slots=True)
class AdapterPolicyEvaluation:
    adapter_id: str
    approved: bool
    read_only: bool
    paper_only: bool
    live_order_allowed: bool
    blocks_live_execution: bool
    reason: str
    violations: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["violations"] = list(self.violations)
        return payload


_BLOCK_REASON = "live execution requires separate approval outside this boundary contract"

_CANDIDATE_CAPABILITIES: dict[str, PredictionMarketAdapterCapability] = {
    "pmxt": PredictionMarketAdapterCapability(
        adapter_id="pmxt",
        venue="multi_prediction_markets",
        language="python",
        supports_market_discovery=True,
        supports_orderbook=True,
        supports_replay=True,
        supports_paper=True,
        blocks_live_execution_reason=_BLOCK_REASON,
    ),
    "pykalshi": PredictionMarketAdapterCapability(
        adapter_id="pykalshi",
        venue="kalshi",
        language="python",
        supports_market_discovery=True,
        supports_orderbook=True,
        supports_replay=True,
        supports_paper=True,
        blocks_live_execution_reason=_BLOCK_REASON,
    ),
    "parsec": PredictionMarketAdapterCapability(
        adapter_id="parsec",
        venue="multi_prediction_markets",
        language="rust",
        supports_market_discovery=True,
        supports_orderbook=True,
        supports_replay=True,
        supports_paper=False,
        blocks_live_execution_reason=_BLOCK_REASON,
    ),
    "polyclawster": PredictionMarketAdapterCapability(
        adapter_id="polyclawster",
        venue="polymarket",
        language="python",
        supports_market_discovery=True,
        supports_orderbook=False,
        supports_replay=True,
        supports_paper=False,
        blocks_live_execution_reason=_BLOCK_REASON,
    ),
}


def candidate_prediction_market_adapter_capability(candidate_id: str) -> PredictionMarketAdapterCapability:
    key = candidate_id.strip().lower()
    if key not in _CANDIDATE_CAPABILITIES:
        raise KeyError(f"unknown prediction-market adapter candidate: {candidate_id}")
    return _CANDIDATE_CAPABILITIES[key]


def audit_known_prediction_market_candidates() -> dict[str, AuditResult]:
    return {
        candidate_id: AuditResult(
            candidate_id=candidate_id,
            capability=capability,
            metadata_only=True,
            imported_dependency=False,
            notes=(
                "metadata-only Phase 5 audit; no dependency import or client construction",
                "preserve original language side behind P-core contracts",
                "paper/read-only default; no wallet signing, credentials, order, or cancel primitive",
            ),
        )
        for candidate_id, capability in _CANDIDATE_CAPABILITIES.items()
    }


def evaluate_prediction_market_adapter_policy(
    capability: PredictionMarketAdapterCapability,
    policy: AdapterBoundaryPolicy | None = None,
) -> AdapterPolicyEvaluation:
    policy = policy or AdapterBoundaryPolicy()
    violations: list[str] = []

    if capability.live_order_allowed:
        violations.append("live_order_allowed")
    if not capability.read_only:
        violations.append("read_only=false")
    if not capability.paper_only:
        violations.append("paper_only=false")
    if "live" in capability.allowed_modes:
        violations.append("mode=live")
    if policy.allow_live_execution:
        violations.append("policy_allow_live_execution")
    if capability.supports_market_discovery and not policy.allow_market_discovery:
        violations.append("market_discovery_not_allowed")
    if capability.supports_orderbook and not policy.allow_orderbook:
        violations.append("orderbook_not_allowed")
    if capability.supports_replay and not policy.allow_replay:
        violations.append("replay_not_allowed")
    if capability.supports_paper and not policy.allow_paper:
        violations.append("paper_not_allowed")

    if violations:
        return AdapterPolicyEvaluation(
            adapter_id=capability.adapter_id,
            approved=False,
            read_only=True,
            paper_only=True,
            live_order_allowed=False,
            blocks_live_execution=True,
            reason="blocked: prediction-market adapters are read-only/paper by default; live or mutable execution requires separate approval",
            violations=tuple(violations),
        )

    return AdapterPolicyEvaluation(
        adapter_id=capability.adapter_id,
        approved=True,
        read_only=True,
        paper_only=True,
        live_order_allowed=False,
        blocks_live_execution=True,
        reason="approved for read-only/paper boundary",
        violations=(),
    )


__all__ = [
    "AdapterBoundaryPolicy",
    "AdapterPolicyEvaluation",
    "AuditResult",
    "PredictionMarketAdapterCapability",
    "audit_known_prediction_market_candidates",
    "candidate_prediction_market_adapter_capability",
    "evaluate_prediction_market_adapter_policy",
]
