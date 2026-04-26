from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from prediction_core.analytics import canonicalize_entity_type


def test_canonicalize_entity_type_keeps_known_canonical_types() -> None:
    assert canonicalize_entity_type("Person") == "Person"
    assert canonicalize_entity_type("Organization") == "Organization"
    assert canonicalize_entity_type("Product") == "Product"
    assert canonicalize_entity_type("Location") == "Location"


def test_canonicalize_entity_type_maps_common_extractor_aliases() -> None:
    assert canonicalize_entity_type("government agency") == "Organization"
    assert canonicalize_entity_type("prediction-market platform") == "Organization"
    assert canonicalize_entity_type("forecasting model") == "Product"
    assert canonicalize_entity_type("city-region") == "Location"
    assert canonicalize_entity_type("expert journalist") == "Person"


def test_canonicalize_entity_type_uses_non_latin_hints_without_over_merging_unknowns() -> None:
    assert canonicalize_entity_type("政府部门") == "Organization"
    assert canonicalize_entity_type("城市") == "Location"
    assert canonicalize_entity_type("软件系统") == "Product"
    assert canonicalize_entity_type("当事人") == "Person"
    assert canonicalize_entity_type(None) == "Entity"
    assert canonicalize_entity_type("WeatherResolutionRule") == "WeatherResolutionRule"
