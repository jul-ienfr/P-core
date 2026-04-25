from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from weather_pm.market_parser import parse_market_question
from weather_pm.resolution_parser import parse_resolution_metadata
from weather_pm.source_routing import build_resolution_source_route


def test_hong_kong_observatory_routes_to_direct_current_weather_and_daily_extract() -> None:
    structure = parse_market_question("Will the highest temperature in Hong Kong be 29°C or higher on April 25?")
    resolution = parse_resolution_metadata(
        resolution_source="https://www.hko.gov.hk/en/wxinfo/currwx/current.htm",
        description="This market resolves according to the official highest temperature recorded by the Hong Kong Observatory.",
        rules="Source: Hong Kong Observatory daily extract, finalized by weather.gov.hk.",
    )

    route = build_resolution_source_route(structure, resolution)

    assert route.provider == "hong_kong_observatory"
    assert route.direct is True
    assert route.supported is True
    assert route.latency_tier == "direct_latest"
    assert route.polling_focus == "hko_current_weather_and_daily_extract"
    assert route.latest_url == "https://www.hko.gov.hk/en/wxinfo/currwx/current.htm"
    assert route.history_url == "https://www.hko.gov.hk/en/wxinfo/dailywx/extract.htm"
    assert route.manual_review_needed is False
