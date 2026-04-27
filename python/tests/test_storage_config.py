from prediction_core.storage.config import load_storage_stack_config, mask_url
from prediction_core.storage.health import _nats_health, storage_health_summary


def test_load_storage_stack_config_prefers_prediction_core_env(monkeypatch):
    monkeypatch.setenv("PREDICTION_CORE_DATABASE_URL", "postgresql+asyncpg://user:secret@localhost/db")
    monkeypatch.setenv("PANOPTIQUE_DATABASE_URL", "postgresql+asyncpg://old:old@localhost/db")
    monkeypatch.setenv("PREDICTION_CORE_REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("PREDICTION_CORE_S3_FORCE_PATH_STYLE", "true")

    config = load_storage_stack_config()

    assert config.postgres.database_url == "postgresql+asyncpg://user:secret@localhost/db"
    assert config.redis.url == "redis://localhost:6379/0"
    assert config.s3.force_path_style is True
    assert config.nats.monitor_url is None
    assert config.to_redacted_dict()["postgres"]["database_url"] == "postgresql+asyncpg://user:***@localhost/db"


def test_mask_url_without_password_is_unchanged():
    assert mask_url("postgresql://localhost/db") == "postgresql://localhost/db"


def test_nats_health_checks_monitor_endpoint_by_convention(monkeypatch):
    captured = {}

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self):
            return b"ok"

    def fake_urlopen(url, timeout):
        captured["url"] = url
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("prediction_core.storage.health.urlopen", fake_urlopen)

    result = _nats_health("nats://localhost:4222")

    assert result["configured"] is True
    assert result["ok"] is True
    assert result["response"] == "ok"
    assert result["monitor_url"] == "http://localhost:8222/healthz"
    assert captured == {"url": "http://localhost:8222/healthz", "timeout": 2}


def test_nats_health_uses_explicit_monitor_url(monkeypatch):
    captured = {}

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self):
            return b"ok"

    def fake_urlopen(url, timeout):
        captured["url"] = url
        return FakeResponse()

    monkeypatch.setattr("prediction_core.storage.health.urlopen", fake_urlopen)

    result = _nats_health("nats://localhost:4222", monitor_url="http://nats-monitor:8122")

    assert result["monitor_url"] == "http://nats-monitor:8122/healthz"
    assert captured["url"] == "http://nats-monitor:8122/healthz"


def test_nats_health_uses_explicit_monitor_port(monkeypatch):
    captured = {}

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self):
            return b"ok"

    def fake_urlopen(url, timeout):
        captured["url"] = url
        return FakeResponse()

    monkeypatch.setattr("prediction_core.storage.health.urlopen", fake_urlopen)

    result = _nats_health("nats://localhost:4222", monitor_port=9222)

    assert result["monitor_url"] == "http://localhost:9222/healthz"
    assert captured["url"] == "http://localhost:9222/healthz"


def test_nats_health_reports_unconfigured_or_errors(monkeypatch):
    assert _nats_health(None) == {"configured": False, "ok": False}

    def fake_urlopen(url, timeout):
        raise TimeoutError("boom")

    monkeypatch.setattr("prediction_core.storage.health.urlopen", fake_urlopen)

    result = _nats_health("nats://localhost:4222")

    assert result == {"configured": True, "ok": False, "error": "TimeoutError"}


def test_storage_health_summary_requires_postgres_primary():
    checks = {
        "postgres": {"configured": True, "ok": False},
        "redis": {"configured": True, "ok": True},
        "nats": {"configured": True, "ok": True},
    }

    summary = storage_health_summary(checks)

    assert summary["configured_count"] == 3
    assert summary["healthy_count"] == 2
    assert summary["unhealthy"] == ["postgres"]
    assert summary["ready"] is False
    assert summary["missing_required_primary"] == ["postgres"]
