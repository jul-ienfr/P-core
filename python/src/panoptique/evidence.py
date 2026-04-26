from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Any


class EvidenceStatus(str, Enum):
    UNVERIFIED = "unverified"
    VERIFIED = "verified"
    PLAUSIBLE = "plausible"
    REJECTED = "rejected"


class InvalidEvidenceTransition(ValueError):
    """Raised when an evidence claim status change would erase reviewed state."""


def _coerce_status(status: EvidenceStatus | str) -> EvidenceStatus:
    try:
        return status if isinstance(status, EvidenceStatus) else EvidenceStatus(status)
    except ValueError as exc:
        valid = ", ".join(item.value for item in EvidenceStatus)
        raise ValueError(f"Unsupported evidence status {status!r}; expected one of: {valid}") from exc


def _validate_confidence(confidence: float) -> float:
    value = float(confidence)
    if not 0.0 <= value <= 1.0:
        raise ValueError("confidence must be between 0.0 and 1.0")
    return value


@dataclass(frozen=True, kw_only=True)
class EvidenceClaim:
    """Small explicit model for Panoptique research claims.

    Phase 6 intentionally keeps this lightweight and stdlib-only. Claims begin as
    unverified unless the caller supplies a reviewed status; later phases can bind
    these IDs to measurements and reports.
    """

    claim_id: str
    claim: str
    source_url: str
    status: EvidenceStatus = EvidenceStatus.UNVERIFIED
    confidence: float = 0.0
    rationale: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", _coerce_status(self.status))
        object.__setattr__(self, "confidence", _validate_confidence(self.confidence))
        if not self.claim_id.strip():
            raise ValueError("claim_id is required")
        if not self.claim.strip():
            raise ValueError("claim text is required")
        if not self.source_url.strip():
            raise ValueError("source_url is required")

    def transition(self, status: EvidenceStatus | str, *, confidence: float | None = None, rationale: str | None = None) -> "EvidenceClaim":
        next_status = _coerce_status(status)
        if self.status is not EvidenceStatus.UNVERIFIED and next_status is not EvidenceStatus.UNVERIFIED:
            raise InvalidEvidenceTransition(
                "reviewed evidence claims must transition back to unverified before a contradictory reviewed status"
            )
        return replace(
            self,
            status=next_status,
            confidence=self.confidence if confidence is None else _validate_confidence(confidence),
            rationale=self.rationale if rationale is None else rationale,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "claim": self.claim,
            "source_url": self.source_url,
            "status": self.status.value,
            "confidence": self.confidence,
            "rationale": self.rationale,
        }
