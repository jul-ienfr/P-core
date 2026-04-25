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

    for provider in providers:
        metadata = WEATHER_SOURCE_PROVIDER_CATALOG[provider]
        category = str(metadata["category"])
        by_category.setdefault(category, []).append(provider)
        route_support = str(metadata["route_support"])
        if route_support in {"direct_latest", "direct_history", "direct_api", "direct_or_injected"}:
            direct_low_latency.append(provider)
        elif route_support.startswith("fallback"):
            fallback_only.append(provider)
        elif route_support in {"manual_review", "scrape_review", "unsupported"}:
            manual_review_only.append(provider)

    return WeatherSourceCoverageReport(
        provider_count=len(providers),
        providers=providers,
        by_category={category: sorted(values) for category, values in sorted(by_category.items())},
        direct_low_latency=sorted(direct_low_latency),
        fallback_only=sorted(fallback_only),
        manual_review_only=sorted(manual_review_only),
        caveats=[
            "Coverage is broad but not literally exhaustive; unknown local services still fall back to manual_review.",
            "Several commercial/official providers require explicit source_url or injected payload/API credentials before automated polling.",
            "Weather.com page scraping remains manual-review only because browser/API access is brittle.",
        ],
    )
