from __future__ import annotations

import pytest

from panoptique.evidence import EvidenceClaim, EvidenceStatus, InvalidEvidenceTransition


def test_evidence_claim_defaults_to_unverified_with_explicit_confidence() -> None:
    claim = EvidenceClaim(
        claim_id="EV-PAN-001",
        claim="Public bot homogenization may create predictable crowd-flow patterns.",
        source_url="https://example.test/brief",
        confidence=0.2,
    )

    assert claim.status == EvidenceStatus.UNVERIFIED
    assert claim.confidence == 0.2
    assert claim.to_dict()["status"] == "unverified"


def test_unverified_claim_can_transition_to_verified_plausible_or_rejected() -> None:
    claim = EvidenceClaim(
        claim_id="EV-PAN-002",
        claim="Repository contains weather/paper modules.",
        source_url="file:///home/jul/prediction_core/README.md",
    )

    verified = claim.transition(EvidenceStatus.VERIFIED, confidence=0.95, rationale="confirmed from repo docs")
    plausible = claim.transition("plausible", confidence=0.65, rationale="consistent with public metadata")
    rejected = claim.transition("rejected", confidence=0.9, rationale="contradicted by plan")

    assert verified.status == EvidenceStatus.VERIFIED
    assert verified.confidence == 0.95
    assert verified.rationale == "confirmed from repo docs"
    assert plausible.status == EvidenceStatus.PLAUSIBLE
    assert rejected.status == EvidenceStatus.REJECTED


def test_evidence_transition_rejects_unknown_status_and_out_of_range_confidence() -> None:
    claim = EvidenceClaim(claim_id="EV-PAN-003", claim="x", source_url="https://example.test")

    with pytest.raises(ValueError):
        claim.transition("unsupported")
    with pytest.raises(ValueError):
        claim.transition(EvidenceStatus.VERIFIED, confidence=1.5)


def test_verified_claim_cannot_be_rewritten_without_returning_to_unverified() -> None:
    claim = EvidenceClaim(claim_id="EV-PAN-004", claim="x", source_url="https://example.test").transition(
        EvidenceStatus.VERIFIED, confidence=0.9
    )

    with pytest.raises(InvalidEvidenceTransition):
        claim.transition(EvidenceStatus.REJECTED, confidence=0.8)
