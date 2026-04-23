from __future__ import annotations

import re

from weather_pm.models import MarketStructure

_THRESHOLD_RE = re.compile(
    r"Will the (?P<measurement>highest|lowest) temperature in (?P<city>.+?) be (?P<target>-?\d+(?:\.\d+)?)(?:°)?(?P<unit>[CF]) or (?P<direction>higher|below)(?: on (?P<date>.+?))?\?",
    re.IGNORECASE,
)
_BIN_RE = re.compile(
    r"Will the (?P<measurement>highest|lowest) temperature in (?P<city>.+?) be between (?P<low>-?\d+(?:\.\d+)?)(?P<unit>[CF]) and (?P<high>-?\d+(?:\.\d+)?)(?P=unit)\?",
    re.IGNORECASE,
)
_EXACT_VALUE_RE = re.compile(
    r"Will the (?P<measurement>highest|lowest) temperature in (?P<city>.+?) be exactly (?P<target>-?\d+(?:\.\d+)?)(?:°)?(?P<unit>[CF])(?: on (?P<date>.+?))?\?",
    re.IGNORECASE,
)
_EVENT_RE = re.compile(
    r"(?P<measurement>Highest|Lowest) temperature in (?P<city>.+?) on (?P<date>.+?)\?",
    re.IGNORECASE,
)


CITY_DEFAULT_UNITS = {
    "tokyo": "c",
    "hong kong": "c",
    "amsterdam": "c",
    "helsinki": "c",
    "istanbul": "c",
    "auckland": "c",
    "shenzhen": "c",
    "tel aviv": "c",
    "san francisco": "f",
    "dallas": "f",
    "denver": "f",
    "miami": "f",
    "nyc": "f",
    "new york": "f",
    "london": "f",
    "toronto": "f",
}


def parse_market_question(question: str) -> MarketStructure:
    threshold_match = _THRESHOLD_RE.fullmatch(question.strip())
    if threshold_match:
        direction = threshold_match.group("direction").lower()
        measurement = threshold_match.group("measurement")
        return MarketStructure(
            city=threshold_match.group("city"),
            measurement_kind=_measurement_kind(measurement),
            unit=threshold_match.group("unit").lower(),
            is_threshold=True,
            is_exact_bin=False,
            target_value=float(threshold_match.group("target")),
            range_low=None,
            range_high=None,
            threshold_direction=direction,
            date_local=threshold_match.group("date"),
        )

    bin_match = _BIN_RE.fullmatch(question.strip())
    if bin_match:
        return MarketStructure(
            city=bin_match.group("city"),
            measurement_kind=_measurement_kind(bin_match.group("measurement")),
            unit=bin_match.group("unit").lower(),
            is_threshold=False,
            is_exact_bin=True,
            target_value=None,
            range_low=float(bin_match.group("low")),
            range_high=float(bin_match.group("high")),
            threshold_direction=None,
            date_local=None,
        )

    exact_value_match = _EXACT_VALUE_RE.fullmatch(question.strip())
    if exact_value_match:
        target_value = float(exact_value_match.group("target"))
        return MarketStructure(
            city=exact_value_match.group("city"),
            measurement_kind=_measurement_kind(exact_value_match.group("measurement")),
            unit=exact_value_match.group("unit").lower(),
            is_threshold=False,
            is_exact_bin=True,
            target_value=target_value,
            range_low=target_value,
            range_high=target_value,
            threshold_direction=None,
            date_local=exact_value_match.group("date"),
        )

    event_match = _EVENT_RE.fullmatch(question.strip())
    if event_match:
        city = event_match.group("city")
        return MarketStructure(
            city=city,
            measurement_kind=_measurement_kind(event_match.group("measurement")),
            unit=_default_unit_for_city(city),
            is_threshold=False,
            is_exact_bin=True,
            target_value=None,
            range_low=None,
            range_high=None,
            threshold_direction=None,
            date_local=event_match.group("date"),
        )

    raise ValueError(f"Unsupported market question format: {question}")


def _measurement_kind(raw_value: str) -> str:
    return "high" if raw_value.lower() == "highest" else "low"


def _default_unit_for_city(city: str) -> str:
    return CITY_DEFAULT_UNITS.get(city.strip().lower(), "f")
