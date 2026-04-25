from __future__ import annotations

from weather_pm.event_surface import build_weather_event_surface


def test_build_weather_event_surface_groups_city_date_and_flags_monotonic_threshold_violation() -> None:
    markets = [
        {"id": "london-19", "question": "Will the highest temperature in London be 19°C or higher on April 25?", "yes_price": 0.40},
        {"id": "london-20", "question": "Will the highest temperature in London be 20°C or higher on April 25?", "yes_price": 0.45},
        {"id": "london-21", "question": "Will the highest temperature in London be 21°C or higher on April 25?", "yes_price": 0.20},
        {"id": "paris-18", "question": "Will the highest temperature in Paris be 18°C or higher on April 25?", "yes_price": 0.55},
    ]

    surface = build_weather_event_surface(markets)

    assert surface["event_count"] == 2
    london = surface["events"][0]
    assert london["event_key"] == "London|high|c|April 25"
    assert london["market_count"] == 3
    assert london["threshold_count"] == 3
    assert london["inconsistencies"] == [
        {
            "type": "threshold_monotonicity_violation",
            "direction": "higher",
            "lower_market_id": "london-19",
            "higher_market_id": "london-20",
            "lower_target": 19.0,
            "higher_target": 20.0,
            "lower_price": 0.4,
            "higher_price": 0.45,
            "severity": 0.05,
        }
    ]


def test_build_weather_event_surface_flags_exact_bin_mass_overround() -> None:
    markets = [
        {"id": "nyc-70", "question": "Will the highest temperature in New York City be exactly 70°F on April 25?", "yes_price": 0.34},
        {"id": "nyc-71", "question": "Will the highest temperature in New York City be exactly 71°F on April 25?", "yes_price": 0.33},
        {"id": "nyc-72", "question": "Will the highest temperature in New York City be exactly 72°F on April 25?", "yes_price": 0.36},
    ]

    surface = build_weather_event_surface(markets, exact_mass_tolerance=1.0)

    nyc = surface["events"][0]
    assert nyc["exact_bin_count"] == 3
    assert nyc["exact_bin_price_mass"] == 1.03
    assert nyc["inconsistencies"] == [
        {
            "type": "exact_bin_mass_overround",
            "price_mass": 1.03,
            "tolerance": 1.0,
            "severity": 0.03,
        }
    ]
