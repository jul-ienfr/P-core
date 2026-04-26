from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_compose_and_env_are_local_only_and_secret_free() -> None:
    compose = (ROOT / "infra" / "panoptique" / "docker-compose.yml").read_text()
    env = (ROOT / "infra" / "panoptique" / ".env.example").read_text()
    readme = (ROOT / "infra" / "panoptique" / "README.md").read_text()

    assert "timescale/timescaledb" in compose
    assert "redis:" in compose
    assert "127.0.0.1:${PANOPTIQUE_POSTGRES_PORT:-5432}:5432" in compose
    assert "127.0.0.1:${PANOPTIQUE_REDIS_PORT:-6379}:6379" in compose
    assert "healthcheck:" in compose
    assert "PANOPTIQUE_REDIS_URL=redis://localhost:6379/0" in env
    assert "PYTHONPATH" not in env
    assert "PRIVATE_KEY" not in env
    assert "WALLET" not in env
    assert "audit/replay" in readme
