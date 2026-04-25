from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from weather_pm.resolution_parser import WEATHER_SOURCE_PROVIDER_CATALOG


@dataclass(slots=True)
class WeatherSourceCoverageReport:
    provider_count: int
    providers: list[str]
    by_category: dict[str, list[str]]
    direct_low_latency: list[str]
    fallback_only: list[str]
    manual_review_only: list[str]
    route_support_counts: dict[str, int]
    automation_summary: dict[str, int]
    next_integration_targets: list[dict[str, str]]
    caveats: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_weather_source_coverage_report() -> WeatherSourceCoverageReport:
    """Summarize integrated weather resolution source coverage.

    This is an intentionally explicit inventory: it answers "what do we route today?"
    without claiming exhaustive coverage of every meteorological service on earth.
    """
    providers = sorted(WEATHER_SOURCE_PROVIDER_CATALOG)
    by_category: dict[str, list[str]] = {}
    direct_low_latency: list[str] = []
    fallback_only: list[str] = []
    manual_review_only: list[str] = []
    route_support_counts: dict[str, int] = {}

    for provider in providers:
        metadata = WEATHER_SOURCE_PROVIDER_CATALOG[provider]
        category = str(metadata["category"])
        by_category.setdefault(category, []).append(provider)
        route_support = str(metadata["route_support"])
        route_support_counts[route_support] = route_support_counts.get(route_support, 0) + 1
        if route_support in {"direct_latest", "direct_history", "direct_api", "direct_or_injected"}:
            direct_low_latency.append(provider)
        elif route_support.startswith("fallback"):
            fallback_only.append(provider)
        elif route_support in {"manual_review", "scrape_review", "unsupported"}:
            manual_review_only.append(provider)

    automation_summary = {
        "provider_count": len(providers),
        "automated_or_direct_provider_count": len(direct_low_latency) + len(fallback_only),
        "direct_provider_count": len(direct_low_latency),
        "fallback_provider_count": len(fallback_only),
        "manual_review_provider_count": len(manual_review_only),
    }

    return WeatherSourceCoverageReport(
        provider_count=len(providers),
        providers=providers,
        by_category={category: sorted(values) for category, values in sorted(by_category.items())},
        direct_low_latency=sorted(direct_low_latency),
        fallback_only=sorted(fallback_only),
        manual_review_only=sorted(manual_review_only),
        route_support_counts=dict(sorted(route_support_counts.items())),
        automation_summary=automation_summary,
        next_integration_targets=_next_integration_targets(),
        caveats=[
            "Coverage is broad but not literally exhaustive; unknown local services still fall back to manual_review.",
            "Several commercial/official providers require explicit source_url or injected payload/API credentials before automated polling.",
            "Weather.com page scraping remains manual-review only because browser/API access is brittle.",
        ],
    )


def _next_integration_targets() -> list[dict[str, str]]:
    """Return the remaining non-automated providers operators should prioritize next."""
    target_rank = {
        "unsupported": 0,
        "manual_review": 1,
        "scrape_review": 2,
    }
    targets: list[dict[str, str]] = []
    for provider, metadata in WEATHER_SOURCE_PROVIDER_CATALOG.items():
        route_support = str(metadata["route_support"])
        if route_support not in target_rank:
            continue
        targets.append(
            {
                "provider": provider,
                "category": str(metadata["category"]),
                "reason": route_support,
            }
        )
    return sorted(targets, key=lambda item: (target_rank[item["reason"]], item["category"], item["provider"]))
