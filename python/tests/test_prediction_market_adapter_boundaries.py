from __future__ import annotations

from prediction_core.execution.prediction_market_adapters import (
    AdapterBoundaryPolicy,
    PredictionMarketAdapterCapability,
    audit_known_prediction_market_candidates,
    candidate_prediction_market_adapter_capability,
    evaluate_prediction_market_adapter_policy,
)


def test_known_candidate_audit_keeps_original_language_boundaries_and_no_imports() -> None:
    audits = audit_known_prediction_market_candidates()

    assert set(audits) == {"pmxt", "pykalshi", "parsec", "polyclawster"}
    assert audits["pmxt"].capability.language == "python"
    assert audits["pykalshi"].capability.language == "python"
    assert audits["parsec"].capability.language == "rust"
    assert audits["polyclawster"].capability.language == "python"

    for audit in audits.values():
        assert audit.metadata_only is True
        assert audit.imported_dependency is False
        assert audit.capability.read_only is True
        assert audit.capability.paper_only is True
        assert audit.capability.live_order_allowed is False
        assert "paper" in audit.capability.allowed_modes
        assert "read_only" in audit.capability.allowed_modes
        assert audit.capability.blocks_live_execution_reason


def test_default_policy_blocks_live_mutable_prediction_market_capabilities() -> None:
    capability = PredictionMarketAdapterCapability(
        adapter_id="unsafe-live-client",
        venue="example",
        language="python",
        allowed_modes=("read_only", "paper", "live"),
        read_only=False,
        paper_only=False,
        live_order_allowed=True,
        supports_market_discovery=True,
        supports_orderbook=True,
        supports_replay=True,
        supports_paper=True,
        blocks_live_execution_reason="",
    )

    result = evaluate_prediction_market_adapter_policy(capability)

    assert result.approved is False
    assert result.paper_only is True
    assert result.live_order_allowed is False
    assert result.blocks_live_execution is True
    assert "separate approval" in result.reason
    assert "live_order_allowed" in result.violations
    assert "read_only=false" in result.violations
    assert "paper_only=false" in result.violations
    assert "mode=live" in result.violations


def test_explicit_policy_flags_can_approve_discovery_without_enabling_real_execution() -> None:
    capability = candidate_prediction_market_adapter_capability("pmxt")
    policy = AdapterBoundaryPolicy(
        allow_market_discovery=True,
        allow_orderbook=True,
        allow_replay=True,
        allow_paper=True,
        allow_live_execution=False,
        approval_reference="phase-5-boundary-only",
    )

    result = evaluate_prediction_market_adapter_policy(capability, policy)

    assert result.approved is True
    assert result.live_order_allowed is False
    assert result.paper_only is True
    assert result.read_only is True
    assert result.reason == "approved for read-only/paper boundary"


def test_candidate_audit_payloads_are_contract_safe_for_docs_and_analytics() -> None:
    audit = audit_known_prediction_market_candidates()["parsec"]
    payload = audit.to_dict()

    assert payload["candidate_id"] == "parsec"
    assert payload["capability"]["language"] == "rust"
    assert payload["capability"]["paper_only"] is True
    assert payload["capability"]["live_order_allowed"] is False
    assert payload["metadata_only"] is True
    assert payload["imported_dependency"] is False
    assert "credentials" not in payload
    assert "wallet" not in payload
