from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNBOOK = ROOT / "docs" / "prediction-core-clickhouse-grafana.md"


def test_prediction_core_runbook_documents_operator_commands() -> None:
    text = RUNBOOK.read_text()

    for command in [
        "docker compose up -d",
        "docker-compose up -d",
        "curl -fsS http://127.0.0.1:8123/ping",
        "infra/analytics/scripts/smoke_clickhouse.sh",
        "infra/analytics/scripts/smoke_weather_export.sh",
        "python3 -m weather_pm.cli export-analytics-clickhouse",
        "--dry-run",
        "--paper-ledger-json",
        "/home/jul/P-core",
    ]:
        assert command in text


def test_prediction_core_runbook_names_dashboards_and_env_vars() -> None:
    text = RUNBOOK.read_text()

    for label in [
        "Strategy vs Profile",
        "Decision Debug",
        "Paper Ledger",
        "Weather Operator Cockpit",
        "weather-operator-cockpit.json",
        "city/date/source",
        "model probability vs market price",
        "official settlement status",
        "PREDICTION_CORE_CLICKHOUSE_URL",
        "PREDICTION_CORE_CLICKHOUSE_HOST",
        "PREDICTION_CORE_CLICKHOUSE_PORT",
        "PREDICTION_CORE_CLICKHOUSE_USER",
        "PREDICTION_CORE_CLICKHOUSE_PASSWORD",
        "PREDICTION_CORE_CLICKHOUSE_DATABASE",
    ]:
        assert label in text


def test_prediction_core_runbook_documents_security_and_local_compose_quirk() -> None:
    text = RUNBOOK.read_text()

    for phrase in [
        "Do not put secrets in `raw`",
        "Do not paste passwords in ClickHouse URLs",
        "environment variables",
        "Not supported URL scheme http+docker",
        "Docker Compose v2",
        "legacy `docker-compose`",
    ]:
        assert phrase in text
