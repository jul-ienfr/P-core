from __future__ import annotations

import re

from weather_pm.models import ResolutionMetadata

_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
_STATION_RE = re.compile(r"\b([A-Z]{4})\b")
_NON_STATION_CODES = {"DATA", "NOAA"}
_WUNDERGROUND_CODE_RE = re.compile(r"/history/daily/(?:[^/]+/)+([A-Z]{4})(?:[/?#]|$)", re.IGNORECASE)
_ACCUWEATHER_URL_RE = re.compile(r"https?://[^\s?#]*accuweather\.com/[^\s?#]+", re.IGNORECASE)
_ACCUWEATHER_LOCATION_NAME_RE = re.compile(r"accuweather\.com/(?:[^\s/?#]+/){2}(?P<name>[^\s/?#]+)/", re.IGNORECASE)
_STATION_NAME_PATTERNS = (
    re.compile(
        r"\b(?:recorded|observed|published)\s+at\s+(?:the\s+)?(?P<name>[A-Za-z0-9 .'-]+?)\s+Station\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bfor\s+(?P<name>[A-Za-z0-9 .'-]+?)\s+station\s+[A-Z]{4}\b",
        re.IGNORECASE,
    ),
)


def parse_resolution_metadata(
    *,
    resolution_source: str | None,
    description: str | None,
    rules: str | None,
) -> ResolutionMetadata:
    source_text = resolution_source or ""
    description_text = description or ""
    rules_text = rules or ""
    combined = " ".join(part for part in [source_text, description_text, rules_text] if part).strip()
    lowered = combined.lower()

    provider = _detect_provider(lowered)
    source_url = _extract_url(combined)
    station_code = _extract_station_code(combined)
    station_name = _extract_station_name(description_text, station_code)
    if provider == "accuweather" and station_name == description_text.strip():
        station_name = _extract_accuweather_location_name(combined)
    station_type = _classify_station_type(combined, station_code, provider)
    wording_clear = _is_wording_clear(lowered, provider, station_code)
    rules_clear = _are_rules_clear(lowered, provider, station_code)
    manual_review_needed = _needs_manual_review(provider, station_code, station_name, wording_clear, rules_clear)
    revision_risk = "high" if manual_review_needed else "low"

    return ResolutionMetadata(
        provider=provider,
        source_url=source_url,
        station_code=station_code,
        station_name=station_name,
        station_type=station_type,
        wording_clear=wording_clear,
        rules_clear=rules_clear,
        manual_review_needed=manual_review_needed,
        revision_risk=revision_risk,
    )


def _detect_provider(lowered: str) -> str:
    if any(token in lowered for token in ["hong kong observatory", "weather.gov.hk"]):
        return "hong_kong_observatory"
    if "noaa" in lowered or "national weather service" in lowered or re.search(r"(?<!aviation)weather\.gov", lowered):
        return "noaa"
    if any(token in lowered for token in ["aviationweather.gov", "metar", "aviation weather", "airport observations"]):
        return "aviation_weather"
    if any(token in lowered for token in ["wunderground", "weather underground"]):
        return "wunderground"
    if any(token in lowered for token in ["meteostat", "meteostat.net"]):
        return "meteostat"
    if any(token in lowered for token in ["accuweather"]):
        return "accuweather"
    return "unknown"


def _extract_url(text: str) -> str | None:
    match = _URL_RE.search(text)
    return match.group(0) if match else None


def _extract_station_code(text: str) -> str | None:
    wunderground_match = _WUNDERGROUND_CODE_RE.search(text)
    if wunderground_match:
        return wunderground_match.group(1).upper()

    accuweather_key_from_url = _extract_accuweather_location_key(text)
    if accuweather_key_from_url:
        return accuweather_key_from_url

    accuweather_key_match = re.search(r"\blocation\s+key\s+(\d+)\b", text, re.IGNORECASE)
    if accuweather_key_match:
        return accuweather_key_match.group(1)

    station_keyword_match = re.search(r"station\s+([A-Z0-9]{4,8})\b", text, re.IGNORECASE)
    if station_keyword_match:
        raw_code = station_keyword_match.group(1)
        code = raw_code.upper()
        if code.isdigit():
            return code
        if raw_code == code and _STATION_RE.fullmatch(code) and code not in _NON_STATION_CODES:
            return code

    for match in _STATION_RE.finditer(text):
        code = match.group(1)
        if code not in _NON_STATION_CODES:
            return code
    return None


def _extract_accuweather_location_key(text: str) -> str | None:
    for url_match in _ACCUWEATHER_URL_RE.finditer(text):
        path = url_match.group(0).split("?", 1)[0].rstrip("/.,)")
        numeric_segments = re.findall(r"/(\d+)(?=/|$)", path)
        if numeric_segments:
            return numeric_segments[-1]
    return None


def _extract_station_name(description: str, station_code: str | None) -> str | None:
    if not description.strip():
        return None

    hong_kong_observatory_match = re.search(
        r"\bthe\s+(Hong Kong Observatory)\b|\b(Hong Kong Observatory)\b",
        description,
        re.IGNORECASE,
    )
    if hong_kong_observatory_match:
        return _clean_station_name(hong_kong_observatory_match.group(1) or hong_kong_observatory_match.group(2))

    for pattern in _STATION_NAME_PATTERNS:
        match = pattern.search(description)
        if match:
            return _clean_station_name(match.group("name"))

    if station_code and station_code in description:
        station_name_match = re.search(rf"(?P<name>[A-Za-z0-9 .'-]+?)\s+station\s+{re.escape(station_code)}\b", description, re.IGNORECASE)
        if station_name_match:
            return _clean_station_name(station_name_match.group("name"))

    return description.strip() or None


def _clean_station_name(name: str) -> str | None:
    cleaned = re.sub(r"\s+", " ", name).strip(" .,")
    cleaned = re.sub(r"\bthe\b\s+", "", cleaned, flags=re.IGNORECASE)
    return cleaned or None


def _extract_accuweather_location_name(text: str) -> str | None:
    match = _ACCUWEATHER_LOCATION_NAME_RE.search(text)
    if not match:
        return None
    name = match.group("name").replace("-", " ").title()
    return _clean_station_name(name)


def _classify_station_type(text: str, station_code: str | None, provider: str) -> str:
    if provider == "accuweather" and station_code:
        return "location"
    lowered = text.lower()
    if station_code and len(station_code) == 4 and not station_code.isdigit():
        return "airport"
    if "airport" in lowered:
        return "airport"
    if "station" in lowered or "observatory" in lowered:
        return "station"
    return "unknown"


def _is_wording_clear(lowered: str, provider: str, station_code: str | None) -> bool:
    markers = ["official", "observed", "resolves according to", "highest temperature", "lowest temperature", "recorded by", "recorded in"]
    if station_code is not None:
        return any(marker in lowered for marker in markers)
    if provider == "hong_kong_observatory":
        return "hong kong observatory" in lowered and any(marker in lowered for marker in markers)
    if provider == "accuweather":
        return "accuweather" in lowered and any(marker in lowered for marker in markers)
    if provider == "meteostat":
        return any(marker in lowered for marker in markers)
    return False


def _are_rules_clear(lowered: str, provider: str, station_code: str | None) -> bool:
    if provider == "unknown":
        return False
    if provider == "hong_kong_observatory":
        clarity_tokens = ["source", "observatory", "daily extract", "weather.gov.hk", "finalized"]
        return any(token in lowered for token in clarity_tokens)
    if provider == "accuweather":
        clarity_tokens = ["source", "accuweather", "location key", "daily forecast", "current conditions"]
        return any(token in lowered for token in clarity_tokens)
    if provider == "meteostat":
        clarity_tokens = ["source", "meteostat", "daily", "tmax", "tmin"]
        return any(token in lowered for token in clarity_tokens)
    if station_code is None:
        return False
    if provider == "aviation_weather":
        clarity_tokens = ["source", "station", "official", "aviationweather.gov", "metar", "aviation weather", "airport observations"]
        return any(token in lowered for token in clarity_tokens)
    clarity_tokens = ["source", "station", "official", "weather.gov", "daily climate report"]
    return any(token in lowered for token in clarity_tokens)


def _needs_manual_review(
    provider: str,
    station_code: str | None,
    station_name: str | None,
    wording_clear: bool,
    rules_clear: bool,
) -> bool:
    if provider == "unknown" or not wording_clear or not rules_clear:
        return True
    if station_code is not None:
        return False
    return station_name is None
