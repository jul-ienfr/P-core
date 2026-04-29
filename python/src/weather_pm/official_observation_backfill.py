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
PROXY_SOURCE_MARKERS = ("proxy", "gamma", "clob", "polymarket")


def build_official_observation_backfill(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate local official weather observations into resolution rows.

    This contract intentionally accepts only explicit official observation fields.
    It does not infer weather outcomes from Polymarket/Gamma/CLOB market-resolution
    proxies; those remain useful for market resolution coverage but are not official
    meteorological observations.
    """

    rows = _observation_rows(payload)
    normalized = [_normalize_observation(row, index) for index, row in enumerate(rows)]
    return {
        "paper_only": True,
        "live_order_allowed": False,
        "summary": {
            "observations": len(normalized),
            "official_source_available": bool(normalized),
        },
        "resolutions": normalized,
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


def _require_objects(rows: list[Any], label: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f"{label}[{index}] must be an object")
        out.append(row)
    return out


def _normalize_observation(row: dict[str, Any], index: int) -> dict[str, Any]:
    missing = [field for field in REQUIRED_OBSERVATION_FIELDS if row.get(field) in (None, "")]
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
        "resolution_source": row.get("resolution_source") or row.get("source") or "official_weather_observation",
        "official_source_available": True,
    }
    for key in ("market_id", "primary_key", "condition_id", "slug", "question", "city", "date", "market_type", "station_name"):
        if row.get(key) not in (None, ""):
            normalized[key] = row[key]
    if row.get("resolution_value") not in (None, ""):
        resolution_value = _to_float(row.get("resolution_value"))
        if resolution_value is None:
            raise ValueError(f"official observation row {index} resolution_value must be numeric when provided")
        normalized["resolution_value"] = resolution_value
    return normalized


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
