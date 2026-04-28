from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass(frozen=True)
class Alert:
    title: str
    message: str
    severity: Severity = Severity.INFO
    payload: dict[str, Any] = field(default_factory=dict)

    @property
    def dedupe_key(self) -> str:
        raw = json.dumps(
            {"title": self.title, "message": self.message, "severity": self.severity.value, "payload": redact(self.payload)},
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class NotificationConfig:
    sink: Literal["log", "webhook", "telegram", "discord"] = "log"
    enabled: bool = False
    url: str | None = None
    token: str | None = None
    chat_id: str | None = None


_SECRET_RE = re.compile(r"(secret|token|password|passwd|api[_-]?key|authorization|auth|credential)", re.I)
_ALLOWED_COMMANDS = {"status", "risk", "reconciliation", "preflight"}
_DENIED_COMMANDS = {"buy", "sell", "cancel", "live-on"}


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: "[REDACTED]" if _SECRET_RE.search(str(key)) else redact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact(item) for item in value)
    return value


def render_alert(alert: Alert, sink: str = "log") -> dict[str, Any]:
    payload = redact(alert.payload)
    text = f"[{alert.severity.value}] {alert.title}: {alert.message}"
    if sink == "telegram":
        return {"text": text, "payload": payload}
    if sink == "discord":
        return {"content": text, "embeds": [{"title": alert.title, "description": alert.message}], "payload": payload}
    return {"text": text, "severity": alert.severity.value, "payload": payload, "dedupe_key": alert.dedupe_key}


def send_alert(alert: Alert, config: NotificationConfig | None = None, logger: logging.Logger | None = None) -> dict[str, Any]:
    config = config or NotificationConfig()
    rendered = render_alert(alert, config.sink)
    (logger or logging.getLogger(__name__)).info("notification dry-run %s", rendered)
    return {"sent": False, "dry_run": True, "sink": config.sink, "payload": rendered}


def command_allowed(command: str) -> bool:
    normalized = command.strip().lower()
    if normalized in _DENIED_COMMANDS:
        return False
    return normalized in _ALLOWED_COMMANDS


def require_allowed_command(command: str) -> None:
    if not command_allowed(command):
        raise PermissionError(f"bot command denied: {command}")
