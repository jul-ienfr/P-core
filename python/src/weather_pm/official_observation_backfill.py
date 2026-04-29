from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REQUIRED_OBSERVATION_FIELDS = (
    "station_id",
    "observation_value",
    "observation_timestamp",
    "resolution_timestamp",
)
IDENTIFIER_FIELDS = ("market_id", "condition_id", "slug", "primary_key")
MARKET_METADATA_FIELDS = (
    "market_id",
    "primary_key",
    "condition_id",
    "slug",
    "question",
    "title",
    "city",
    "date",
    "market_type",
)
OBSERVATION_METADATA_FIELDS = (
    "market_id",
    "primary_key",
    "condition_id",
    "slug",
    "question",
    "title",
    "city",
    "date",
    "market_type",
    "station_name",
    "observation_unit",
    "resolution_source_url",
)
PROXY_SOURCE_MARKERS = ("proxy", "gamma", "clob", "polymarket")


def build_official_observation_backfill(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate local official weather observations into resolution rows.

    The input contract is intentionally local-file first and paper-only.  Payloads
    may contain either a bare observation object, an ``observations``/``resolutions``
    collection, or a dataset with ``markets`` plus ``observations``.  When markets
    are supplied, observations are attached only by exact market identifiers
    (market_id/slug/condition_id/primary_key) or by exact city/date/market_type.
    Missing and orphaned rows are reported as diagnostics; no observations are
    invented from market metadata or market-resolution proxies.
    """

    rows = _observation_rows(payload)
    normalized = [_normalize_observation(row, index) for index, row in enumerate(rows)]
    markets = _market_rows(payload)
    if not markets:
        return {
            "paper_only": True,
            "live_order_allowed": False,
            "summary": {
                "observations": len(normalized),
                "official_source_available": bool(normalized),
            },
            "resolutions": normalized,
        }

    resolutions, diagnostics, matched_observation_indexes = _match_markets_to_observations(markets, normalized)
    unmatched_observations = [
        (index, row) for index, row in enumerate(normalized) if index not in matched_observation_indexes
    ]
    diagnostics.extend(_unmatched_observation_diagnostics(unmatched_observations))
    return {
        "paper_only": True,
        "live_order_allowed": False,
        "summary": {
            "observations": len(resolutions),
            "official_source_available": bool(resolutions),
            "markets": len(markets),
            "matched_markets": len(resolutions),
            "unmatched_markets": len(markets) - len(resolutions),
            "unmatched_observations": len(unmatched_observations),
        },
        "diagnostics": diagnostics,
        "resolutions": resolutions,
    }


def write_official_observation_backfill(input_json: str | Path, output_json: str | Path) -> dict[str, Any]:
    payload = _load_object(input_json, "official observation input JSON")
    artifact = build_official_observation_backfill(payload)
    output_path = Path(output_json)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")
    return dict(artifact["summary"])


def _observation_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("observations", "resolutions"):
        value = payload.get(key)
        if isinstance(value, list):
            return _require_objects(value, key)
        if isinstance(value, dict):
            return _require_objects(list(value.values()), key)
    return _require_objects([payload], "root")


def _market_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    value = payload.get("markets")
    if value is None:
        return []
    if isinstance(value, list):
        return _require_objects(value, "markets")
    if isinstance(value, dict):
        return _require_objects(list(value.values()), "markets")
    raise ValueError("markets must be a list or object when provided")


def _require_objects(rows: list[Any], label: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f"{label}[{index}] must be an object")
        out.append(row)
    return out


def _normalize_observation(row: dict[str, Any], index: int) -> dict[str, Any]:
    missing = [field for field in REQUIRED_OBSERVATION_FIELDS if row.get(field) in (None, "")]
    if not (row.get("resolution_source") or row.get("source")):
        missing.append("resolution_source")
    if missing:
        raise ValueError(f"official observation row {index} missing required fields: {', '.join(missing)}")
    if _looks_like_proxy(row):
        raise ValueError(f"official observation row {index} appears to be a market/proxy source, not an official weather observation")
    observation_value = _to_float(row.get("observation_value"))
    if observation_value is None:
        raise ValueError(f"official observation row {index} observation_value must be numeric")
    normalized = {
        "station_id": str(row["station_id"]).strip(),
        "observation_value": observation_value,
        "observation_timestamp": str(row["observation_timestamp"]).strip(),
        "resolution_timestamp": str(row["resolution_timestamp"]).strip(),
        "resolution_source": row.get("resolution_source") or row.get("source"),
        "official_source_available": True,
    }
    for key in OBSERVATION_METADATA_FIELDS:
        if row.get(key) not in (None, ""):
            normalized[key] = row[key]
    if row.get("resolution_value") not in (None, ""):
        resolution_value = _to_float(row.get("resolution_value"))
        if resolution_value is None:
            raise ValueError(f"official observation row {index} resolution_value must be numeric when provided")
        normalized["resolution_value"] = resolution_value
    return normalized


def _match_markets_to_observations(markets: list[dict[str, Any]], observations: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], set[int]]:
    resolutions: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    matched_observation_indexes: set[int] = set()
    for market in markets:
        matches = _candidate_observations(market, observations)
        if len(matches) > 1:
            raise ValueError(
                "ambiguous official observations for market "
                f"{_market_label(market)}; provide market_id, condition_id, slug, or unique city/date/market_type"
            )
        if not matches:
            diagnostics.append(
                {
                    "level": "warning",
                    "code": "unmatched_market",
                    **_diagnostic_market_identity(market),
                    "message": "no local official observation matched market identifiers or city/date/market_type",
                }
            )
            continue
        observation_index, observation = matches[0]
        matched_observation_indexes.add(observation_index)
        resolutions.append(_merge_market_observation(market, observation))
    return resolutions, diagnostics, matched_observation_indexes


def _candidate_observations(market: dict[str, Any], observations: list[dict[str, Any]]) -> list[tuple[int, dict[str, Any]]]:
    identifier_matches = [
        (index, row)
        for index, row in enumerate(observations)
        if _shares_identifier(market, row)
    ]
    if identifier_matches:
        return identifier_matches
    if not all(market.get(key) not in (None, "") for key in ("city", "date", "market_type")):
        return []
    return [
        (index, row)
        for index, row in enumerate(observations)
        if _same_key(market.get("city"), row.get("city"))
        and _same_key(market.get("date"), row.get("date"))
        and _same_key(market.get("market_type"), row.get("market_type"))
    ]


def _shares_identifier(market: dict[str, Any], observation: dict[str, Any]) -> bool:
    return any(
        market.get(field) not in (None, "")
        and observation.get(field) not in (None, "")
        and str(market[field]) == str(observation[field])
        for field in IDENTIFIER_FIELDS
    )


def _merge_market_observation(market: dict[str, Any], observation: dict[str, Any]) -> dict[str, Any]:
    merged = dict(observation)
    for key in MARKET_METADATA_FIELDS:
        if market.get(key) not in (None, ""):
            merged[key] = market[key]
    return merged


def _unmatched_observation_diagnostics(rows: list[tuple[int, dict[str, Any]]]) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    for index, row in rows:
        diagnostic = {
            "level": "warning",
            "code": "unmatched_observation",
            "observation_index": index,
            **_diagnostic_market_identity(row),
            "message": "official observation was not attached to any supplied market",
        }
        diagnostics.append(diagnostic)
    return diagnostics


def _diagnostic_market_identity(row: dict[str, Any]) -> dict[str, Any]:
    for key in IDENTIFIER_FIELDS:
        if row.get(key) not in (None, ""):
            return {key: row[key]}
    identity: dict[str, Any] = {}
    for key in ("city", "date", "market_type"):
        if row.get(key) not in (None, ""):
            identity[key] = row[key]
    return identity


def _market_label(market: dict[str, Any]) -> str:
    identity = _diagnostic_market_identity(market)
    if identity:
        return ", ".join(f"{key}={value}" for key, value in identity.items())
    return "<unknown>"


def _same_key(left: Any, right: Any) -> bool:
    return _norm_key(left) == _norm_key(right) and _norm_key(left) != ""


def _norm_key(value: Any) -> str:
    return str(value or "").strip().lower()


def _looks_like_proxy(row: dict[str, Any]) -> bool:
    source_text = " ".join(str(row.get(key) or "") for key in ("source", "resolution_source", "status"))
    return any(marker in source_text.lower() for marker in PROXY_SOURCE_MARKERS)


def _load_object(path: str | Path, label: str) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be an object")
    return payload


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
