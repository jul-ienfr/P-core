import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATASOURCE = ROOT / "infra" / "analytics" / "grafana" / "provisioning" / "datasources" / "clickhouse.yml"
DASHBOARD_PROVIDER = ROOT / "infra" / "analytics" / "grafana" / "provisioning" / "dashboards" / "prediction-core.yml"
DASHBOARDS = ROOT / "infra" / "analytics" / "grafana" / "dashboards"
STRATEGY_VS_PROFILE = DASHBOARDS / "strategy-vs-profile.json"
DECISION_DEBUG = DASHBOARDS / "decision-debug.json"
PAPER_LEDGER = DASHBOARDS / "paper-ledger.json"
DATA_FRESHNESS = DASHBOARDS / "data-freshness.json"
STRATEGY_OVERVIEW = DASHBOARDS / "strategy-overview.json"
STRATEGY_DETAIL = DASHBOARDS / "strategy-detail.json"
STRATEGY_HEALTH = DASHBOARDS / "strategy-health.json"
STRATEGY_CONTROL = DASHBOARDS / "strategy-control.json"
WEATHER_OPERATOR_COCKPIT = DASHBOARDS / "weather-operator-cockpit.json"
ALERTS = ROOT / "infra" / "analytics" / "grafana" / "provisioning" / "alerting" / "prediction-core-alerts.yml"
COMPOSE = ROOT / "infra" / "analytics" / "docker-compose.yml"
ALL_DASHBOARDS = [
    STRATEGY_VS_PROFILE,
    DECISION_DEBUG,
    PAPER_LEDGER,
    DATA_FRESHNESS,
    STRATEGY_OVERVIEW,
    STRATEGY_DETAIL,
    STRATEGY_HEALTH,
    STRATEGY_CONTROL,
    WEATHER_OPERATOR_COCKPIT,
]


def test_grafana_clickhouse_datasource_is_provisioned() -> None:
    text = DATASOURCE.read_text()
    assert "grafana-clickhouse-datasource" in text
    assert "prediction-core-clickhouse" in text
    assert "prediction_core" in text
    assert "jsonData" in text


def test_grafana_and_clickhouse_default_local_only() -> None:
    text = COMPOSE.read_text()
    assert "${GRAFANA_BIND_ADDR:-127.0.0.1}:${GRAFANA_PORT:-3000}:3000" in text
    assert "${CLICKHOUSE_HTTP_BIND_ADDR:-127.0.0.1}:${CLICKHOUSE_HTTP_PORT:-8123}:8123" in text
    assert "${CLICKHOUSE_NATIVE_BIND_ADDR:-127.0.0.1}:${CLICKHOUSE_NATIVE_PORT:-9000}:9000" in text


def test_grafana_dashboard_provider_is_provisioned() -> None:
    text = DASHBOARD_PROVIDER.read_text()
    assert "Prediction Core" in text
    assert "/var/lib/grafana/dashboards" in text


def test_all_dashboards_are_french_paris_and_provisionable() -> None:
    expected_uids = {
        "prediction-core-strategy-vs-profile",
        "prediction-core-decision-debug",
        "prediction-core-paper-ledger",
        "prediction-core-data-freshness",
        "prediction-core-strategy-overview",
        "prediction-core-strategy-detail",
        "prediction-core-strategy-health",
        "prediction-core-strategy-control",
        "prediction-core-weather-operator-cockpit",
    }
    dashboards = [json.loads(path.read_text()) for path in ALL_DASHBOARDS]
    assert {dashboard["uid"] for dashboard in dashboards} == expected_uids
    for dashboard in dashboards:
        assert dashboard["timezone"] == "Europe/Paris"
        assert dashboard["title"]
        assert dashboard["panels"]
        text = json.dumps(dashboard, ensure_ascii=False)
        assert "prediction-core-clickhouse" in text
        assert "countLignes" not in text
        assert "âge_minutes" not in text


def test_strategy_vs_profile_dashboard_has_required_panels() -> None:
    dashboard = json.loads(STRATEGY_VS_PROFILE.read_text())
    text = json.dumps(dashboard, ensure_ascii=False)
    for label in [
        "Comparaison stratégies / profils",
        "PnL net",
        "Trades / skips",
        "Edge moyen",
        "Classement",
        "ROI moyen",
        "Taux de skip",
        "Raisons de skip",
        "Distribution de l’edge des signaux",
        "Exposition",
        "Coûts",
        "Score composite stratégie",
        "run_id",
        "market",
        "business_time",
    ]:
        assert label in text
    for source in [
        "profile_metrics",
        "strategy_metrics",
        "debug_decisions",
        "strategy_signals",
        "paper_pnl_snapshots",
    ]:
        assert source in text
    assert "prediction-core-clickhouse" in text


def test_decision_debug_dashboard_has_required_panels() -> None:
    dashboard = json.loads(DECISION_DEBUG.read_text())
    text = json.dumps(dashboard, ensure_ascii=False)
    for label in ["Debug des décisions", "Drilldown marché", "Observation (Paris)", "Prix limite", "Carnet OK", "Risque OK", "debug_decisions", "skip_reason", "risk_ok", "run_id", "market", "business_time"]:
        assert label in text
    assert "prediction-core-clickhouse" in text


def test_paper_ledger_dashboard_has_required_panels() -> None:
    dashboard = json.loads(PAPER_LEDGER.read_text())
    text = json.dumps(dashboard, ensure_ascii=False)
    for label in ["Ledger paper", "paper_pnl_snapshots", "paper_positions", "paper_orders", "Lignes paper dans la fenêtre", "Ordres paper", "Statut des ordres paper", "PnL net USDC", "Comparaison paper / live", "Observation paper (Paris)", "Observation live (Paris)", "execution_events", "run_id", "market", "business_time"]:
        assert label in text
    assert dashboard["time"]["from"] == "now-48h"
    assert "prediction-core-clickhouse" in text


def test_data_freshness_dashboard_is_provisioned() -> None:
    dashboard = json.loads(DATA_FRESHNESS.read_text())
    text = json.dumps(dashboard, ensure_ascii=False)
    for label in ["Fraîcheur des données", "Fraîcheur des données par table", "Dernière run par stratégie/profil", "Dernière run (Paris)", "Dernière observation (Paris)", "Lignes dans la fenêtre sélectionnée", "Sources obsolètes", "age_minutes"]:
        assert label in text
    for source in ["profile_decisions", "debug_decisions", "strategy_signals", "profile_metrics", "strategy_metrics", "paper_orders", "paper_positions", "paper_pnl_snapshots", "execution_events", "strategy_configs"]:
        assert source in text
    assert "prediction-core-clickhouse" in text


def test_strategy_overview_dashboard_is_provisioned() -> None:
    dashboard = json.loads(STRATEGY_OVERVIEW.read_text())
    text = json.dumps(dashboard, ensure_ascii=False)
    for label in ["Vue d’ensemble des stratégies", "Stratégies actives", "Stratégies en live", "Stratégies en paper", "Stratégies obsolètes", "Classement score / PnL / ROI", "Répartition paper / live", "Principaux blocages par stratégie", "Configuration des stratégies", "Activée", "Mode configuré", "Configurer stratégie"]:
        assert label in text
    for label in ["strategy", "profile", "run_id", "mode", "business_time", "Statut de santé"]:
        assert label in text
    for source in ["profile_metrics", "debug_decisions", "strategy_signals", "profile_decisions", "execution_events", "strategy_configs"]:
        assert source in text
    assert dashboard["uid"] == "prediction-core-strategy-overview"
    assert "prediction-core-clickhouse" in text


def test_strategy_detail_dashboard_is_provisioned() -> None:
    dashboard = json.loads(STRATEGY_DETAIL.read_text())
    text = json.dumps(dashboard, ensure_ascii=False)
    for label in ["Détail stratégie", "Résumé stratégie", "PnL net dans le temps", "ROI dans le temps", "Décisions récentes", "Marchés actifs", "Ordres paper récents", "Événements live récents", "Comparaison paper / live pour cette stratégie", "Diagnostic brut", "Configuration de la stratégie"]:
        assert label in text
    for source in ["profile_metrics", "debug_decisions", "paper_orders", "execution_events", "strategy_configs"]:
        assert source in text
    assert dashboard["uid"] == "prediction-core-strategy-detail"
    assert "prediction-core-clickhouse" in text


def test_strategy_health_dashboard_is_provisioned() -> None:
    dashboard = json.loads(STRATEGY_HEALTH.read_text())
    text = json.dumps(dashboard, ensure_ascii=False)
    for label in ["Santé et attentes des stratégies", "Matrice santé des stratégies", "Stratégies sans données récentes", "Stratégies bloquées par source / carnet / risque", "Écart attentes / activité", "Préparation live", "Attentes risque", "État configuré des stratégies", "DESACTIVEE", "LIVE_INTERDIT"]:
        assert label in text
    for status in ["OK", "PAPER_SEUL", "LIVE_ACTIF", "DONNEES_OBSOLETES", "BLOQUE", "RISQUE_BLOQUE", "SOURCE_BLOQUEE", "CARNET_BLOQUE", "AUCUN_SIGNAL_RECENT"]:
        assert status in text
    for source in ["profile_metrics", "debug_decisions", "strategy_signals", "execution_events", "strategy_configs"]:
        assert source in text
    assert dashboard["uid"] == "prediction-core-strategy-health"
    assert "prediction-core-clickhouse" in text


def test_strategy_control_dashboard_is_provisioned() -> None:
    dashboard = json.loads(STRATEGY_CONTROL.read_text())
    text = json.dumps(dashboard, ensure_ascii=False)
    for label in ["Pilotage paper/live", "Actions à faire maintenant", "Stratégies candidates au live", "Stratégies à surveiller ou désactiver", "Écart configuration / activité", "Dernières décisions actionnables", "Action recommandée", "Candidate live à examiner", "Rien à faire", "Comparaison stratégies / profils", "Fraîcheur des données", "Debug des décisions", "Ledger paper"]:
        assert label in text
    for label in ["strategy", "profile", "market", "mode", "business_time", "Configurer stratégie", "Live autorisé", "Mode configuré"]:
        assert label in text
    for source in ["strategy_configs", "debug_decisions", "strategy_signals", "profile_metrics", "execution_events"]:
        assert source in text
    assert dashboard["uid"] == "prediction-core-strategy-control"
    assert dashboard["timezone"] == "Europe/Paris"
    assert "prediction-core-clickhouse" in text


def test_weather_operator_cockpit_dashboard_is_provisioned() -> None:
    dashboard = json.loads(WEATHER_OPERATOR_COCKPIT.read_text())
    text = json.dumps(dashboard, ensure_ascii=False)
    for label in [
        "Weather Operator Cockpit",
        "Marchés météo par ville / date / source",
        "Probabilité modèle vs prix marché",
        "Fraîcheur source météo minutes",
        "Alertes intraday",
        "Risk cap et action paper",
        "Position et ordres paper météo",
        "Settlement officiel météo",
        "Statut settlement officiel",
        "Paper only",
        "Live autorisé",
        "PAPER_ONLY",
    ]:
        assert label in text
    for label in ["run_id", "strategy", "profile", "market", "mode", "business_time"]:
        assert label in text
    for source in ["strategy_signals", "profile_decisions", "paper_orders", "resolution_events", "debug_decisions"]:
        assert source in text
    for weather_field in ["city", "date", "source", "provider", "station_code", "observed_value", "intraday", "risk_caps"]:
        assert weather_field in text
    assert dashboard["uid"] == "prediction-core-weather-operator-cockpit"
    assert dashboard["timezone"] == "Europe/Paris"
    assert dashboard["time"]["from"] == "now-48h"
    assert "prediction-core-clickhouse" in text


def test_existing_dashboards_link_to_strategy_console() -> None:
    for path in [STRATEGY_VS_PROFILE, DECISION_DEBUG, PAPER_LEDGER, DATA_FRESHNESS, STRATEGY_OVERVIEW, STRATEGY_DETAIL, STRATEGY_HEALTH]:
        text = path.read_text()
        assert "prediction-core-strategy-control" in text

    for path in [STRATEGY_VS_PROFILE, DECISION_DEBUG, PAPER_LEDGER, DATA_FRESHNESS]:
        text = path.read_text()
        assert "prediction-core-strategy-overview" in text
        assert "prediction-core-strategy-detail" in text
        assert "prediction-core-strategy-health" in text

    control_text = STRATEGY_CONTROL.read_text()
    for uid in [
        "prediction-core-strategy-overview",
        "prediction-core-strategy-detail",
        "prediction-core-strategy-health",
        "prediction-core-strategy-vs-profile",
        "prediction-core-data-freshness",
        "prediction-core-decision-debug",
        "prediction-core-paper-ledger",
    ]:
        assert uid in control_text


    text = ALERTS.read_text()
    for label in ["prediction-core-clickhouse", "Données analytics obsolètes", "Aucune décision récente", "Taux de skip élevé", "Événement live détecté", "execution_events"]:
        assert label in text
