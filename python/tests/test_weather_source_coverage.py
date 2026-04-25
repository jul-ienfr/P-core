from __future__ import annotations

from weather_pm.resolution_parser import WEATHER_SOURCE_PROVIDER_CATALOG
from weather_pm.source_coverage import build_weather_source_coverage_report
from weather_pm.source_routing import _DIRECT_OFFICIAL_URL_PROVIDERS


def test_weather_source_coverage_report_answers_integrated_provider_inventory_without_claiming_exhaustive_global_coverage() -> None:
    report = build_weather_source_coverage_report()
    payload = report.to_dict()

    assert payload["provider_count"] == len(WEATHER_SOURCE_PROVIDER_CATALOG)
    assert payload["provider_count"] >= 50
    assert set(_DIRECT_OFFICIAL_URL_PROVIDERS).issubset(set(payload["providers"]))
    assert "noaa" in payload["direct_low_latency"]
    assert "weatherapi" in payload["direct_low_latency"]
    assert "ecmwf_copernicus" in payload["fallback_only"]
    assert "national_weather_service" in payload["manual_review_only"]
    assert "weather_com" in payload["manual_review_only"]
    assert "official_asia_pacific" in payload["by_category"]
    assert "official_latin_america" in payload["by_category"]
    assert payload["route_support_counts"]["direct_history"] >= 20
    assert payload["automation_summary"]["automated_or_direct_provider_count"] > payload["automation_summary"]["manual_review_provider_count"]
    assert payload["automation_summary"]["provider_count"] == payload["provider_count"]
    assert payload["next_integration_targets"][0]["provider"] == "weather_com"
    assert payload["next_integration_targets"][0]["reason"] == "unsupported"
    assert any(target["provider"] == "national_weather_service" for target in payload["next_integration_targets"])
    assert any("not literally exhaustive" in caveat for caveat in payload["caveats"])
