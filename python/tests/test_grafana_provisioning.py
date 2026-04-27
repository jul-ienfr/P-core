import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATASOURCE = ROOT / "infra" / "analytics" / "grafana" / "provisioning" / "datasources" / "clickhouse.yml"
DASHBOARD_PROVIDER = ROOT / "infra" / "analytics" / "grafana" / "provisioning" / "dashboards" / "prediction-core.yml"
DASHBOARDS = ROOT / "infra" / "analytics" / "grafana" / "dashboards"
STRATEGY_VS_PROFILE = DASHBOARDS / "strategy-vs-profile.json"
DECISION_DEBUG = DASHBOARDS / "decision-debug.json"
PAPER_LEDGER = DASHBOARDS / "paper-ledger.json"
COMPOSE = ROOT / "infra" / "analytics" / "docker-compose.yml"


def test_grafana_clickhouse_datasource_is_provisioned() -> None:
    text = DATASOURCE.read_text()
    assert "grafana-clickhouse-datasource" in text
    assert "prediction-core-clickhouse" in text
    assert "prediction_core" in text
    assert "jsonData" in text


def test_grafana_is_lan_accessible_but_clickhouse_defaults_local_only() -> None:
    text = COMPOSE.read_text()
    assert "${GRAFANA_BIND_ADDR:-0.0.0.0}:${GRAFANA_PORT:-3000}:3000" in text
    assert "${CLICKHOUSE_HTTP_BIND_ADDR:-127.0.0.1}:${CLICKHOUSE_HTTP_PORT:-8123}:8123" in text
    assert "${CLICKHOUSE_NATIVE_BIND_ADDR:-127.0.0.1}:${CLICKHOUSE_NATIVE_PORT:-9000}:9000" in text


def test_grafana_dashboard_provider_is_provisioned() -> None:
    text = DASHBOARD_PROVIDER.read_text()
    assert "Prediction Core" in text
    assert "/var/lib/grafana/dashboards" in text


def test_strategy_vs_profile_dashboard_has_required_panels() -> None:
    dashboard = json.loads(STRATEGY_VS_PROFILE.read_text())
    text = json.dumps(dashboard)
    for label in ["Strategy vs Profile", "Net PnL", "Trade Count", "Skip Count", "Average Edge"]:
        assert label in text
    assert "profile_metrics" in text
    assert "strategy_metrics" in text
    assert "prediction-core-clickhouse" in text


def test_decision_debug_dashboard_has_required_panels() -> None:
    dashboard = json.loads(DECISION_DEBUG.read_text())
    text = json.dumps(dashboard)
    for label in ["Decision Debug", "debug_decisions", "skip_reason", "risk_ok"]:
        assert label in text
    assert "prediction-core-clickhouse" in text


def test_paper_ledger_dashboard_has_required_panels() -> None:
    dashboard = json.loads(PAPER_LEDGER.read_text())
    text = json.dumps(dashboard)
    for label in ["Paper Ledger", "paper_pnl_snapshots", "paper_positions", "net_pnl_usdc"]:
        assert label in text
    assert "prediction-core-clickhouse" in text
