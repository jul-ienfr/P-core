from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DASHBOARD = ROOT / "infra" / "analytics" / "grafana" / "dashboards" / "weather-shadow-profiles.json"


def test_weather_shadow_profiles_grafana_dashboard_is_paper_only_operator_surface() -> None:
    assert DASHBOARD.exists(), "Phase 10 dashboard artifact from the shadow profile reference plan must exist"

    dashboard = json.loads(DASHBOARD.read_text(encoding="utf-8"))
    assert dashboard["uid"] == "weather-shadow-profiles"
    assert dashboard["title"] == "Weather Shadow Profiles — Paper Only"
    assert dashboard.get("editable") is False

    targets_raw = json.dumps([panel.get("targets", []) for panel in dashboard["panels"]], sort_keys=True).lower()
    assert "private_key" not in targets_raw
    assert "wallet_secret" not in targets_raw
    assert "place_order" not in targets_raw
    assert "cancel_order" not in targets_raw
    assert "live_order_allowed = true" not in targets_raw

    panels = {panel["title"]: panel for panel in dashboard["panels"]}
    expected_titles = {
        "Top shadow profiles",
        "Profiles that would trade now",
        "Converging markets",
        "Recent profitable-account moves",
        "Important abstentions",
        "Paper PnL by profile",
        "Hit rate by city",
        "Hit rate by market type",
        "Weather source freshness",
        "Orderbook spread and depth",
        "Paper-only guardrails",
    }
    assert expected_titles.issubset(panels)

    guardrails = panels["Paper-only guardrails"]
    guardrail_text = json.dumps(guardrails, sort_keys=True).lower()
    assert "paper_only=true" in guardrail_text
    assert "live_order_allowed=false" in guardrail_text
    assert "no wallet" in guardrail_text
    assert "no signing" in guardrail_text

    for panel in dashboard["panels"]:
        assert panel.get("datasource", {}).get("uid") == "${DS_CLICKHOUSE}"
        panel_text = json.dumps(panel, sort_keys=True).lower()
        assert "paper_only" in panel_text or panel["title"] == "Paper-only guardrails"
        assert "live_order_allowed" in panel_text or panel["title"] == "Paper-only guardrails"
