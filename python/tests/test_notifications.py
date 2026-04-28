import logging

import pytest

from prediction_core.notifications import (
    Alert,
    NotificationConfig,
    Severity,
    command_allowed,
    redact,
    require_allowed_command,
    send_alert,
)


def test_dry_run_no_network(monkeypatch, caplog):
    def fail_network(*args, **kwargs):
        raise AssertionError("network should not be used")

    monkeypatch.setattr("socket.create_connection", fail_network)
    alert = Alert("test", "message", Severity.WARNING, {"market": "abc"})

    with caplog.at_level(logging.INFO):
        result = send_alert(alert, NotificationConfig(sink="webhook", enabled=True, url="https://example.test/hook"))

    assert result["sent"] is False
    assert result["dry_run"] is True
    assert result["sink"] == "webhook"
    assert "notification dry-run" in caplog.text


def test_redaction():
    payload = redact(
        {
            "api_key": "abc",
            "nested": {"token": "def", "value": 1},
            "items": [{"password": "ghi"}],
        }
    )

    assert payload["api_key"] == "[REDACTED]"
    assert payload["nested"]["token"] == "[REDACTED]"
    assert payload["nested"]["value"] == 1
    assert payload["items"][0]["password"] == "[REDACTED]"


def test_stable_dedupe_key():
    first = Alert("title", "message", Severity.INFO, {"b": 2, "a": 1, "token": "secret"})
    second = Alert("title", "message", Severity.INFO, {"a": 1, "token": "secret", "b": 2})

    assert first.dedupe_key == second.dedupe_key


def test_bot_command_denial():
    for command in ("status", "risk", "reconciliation", "preflight"):
        assert command_allowed(command)

    for command in ("buy", "sell", "cancel", "live-on", "unknown"):
        assert not command_allowed(command)
        with pytest.raises(PermissionError):
            require_allowed_command(command)
