from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from weather_pm.calibrated_probability import CalibratedProbabilityInput, threshold_probability
from weather_pm.models import ForecastBundle, MarketStructure
from weather_pm.probability_model import build_model_output


def test_model_output_exposes_stable_method_version_confidence_metadata() -> None:
    structure = MarketStructure(
        city="Denver",
        measurement_kind="high",
        unit="F",
        is_threshold=True,
        is_exact_bin=False,
        target_value=80.0,
        range_low=None,
        range_high=None,
        threshold_direction="above",
    )
    forecast_bundle = ForecastBundle(
        source_count=2,
        consensus_value=82.0,
        dispersion=1.2,
        historical_station_available=True,
    )

    payload = build_model_output(structure, forecast_bundle).to_dict()

    assert payload["method"] == "calibrated_gaussian_threshold_v1"
    assert payload["version"] == "v1"
    assert isinstance(payload["confidence"], float)


def test_calibrated_probability_provenance_round_trips() -> None:
    probability_input = CalibratedProbabilityInput(
        forecast_value=82.0,
        target_value=80.0,
        threshold_direction="above",
        dispersion=1.2,
        provenance={"dataset": "fixture", "agent": "F"},
    )

    output = threshold_probability(probability_input)

    assert probability_input.schema_version == "calibrated_probability_input_v1"
    assert output.schema_version == "calibrated_probability_output_v1"
    assert output.provenance == {"dataset": "fixture", "agent": "F"}
