"""Configuration loader for the weather live observer.

The live observer is deliberately paper-only.  The selected scenario is only the
prepared collection intensity; ``collection.enabled`` is the master switch that
controls whether future live collection may run.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
from typing import Any, Mapping

try:  # pragma: no cover - exercised implicitly when PyYAML is installed
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore[assignment]


ALLOWED_SCENARIOS = frozenset({"minimal", "realistic", "aggressive"})
ALLOWED_STORAGE_BACKENDS = frozenset(
    {"local_jsonl", "local_parquet", "postgres_timescale", "clickhouse", "s3_archive"}
)
_TRUE_VALUES = frozenset({"1", "true", "on"})
_FALSE_VALUES = frozenset({"0", "false", "off"})


@dataclass(frozen=True)
class RetentionConfig:
    raw_days: int | None = None
    compact_days: int | None = None
    aggregate_days: int | None = None


@dataclass(frozen=True)
class ScenarioConfig:
    market_limit: int = 0
    surface_limit: int = 0
    followed_account_limit: int = 0
    compact_market_snapshot_interval_seconds: int = 0
    bin_surface_snapshot_interval_seconds: int = 0
    forecast_snapshot_interval_seconds: int = 0
    trade_trigger_poll_interval_seconds: int = 0
    full_book_policy: str = "event_only"
    retention: RetentionConfig = field(default_factory=RetentionConfig)


@dataclass(frozen=True)
class CollectionConfig:
    enabled: bool = False
    dry_run: bool = True
    reason: str | None = None


@dataclass(frozen=True)
class ToggleConfig:
    enabled: bool = True
    reason: str | None = None


@dataclass(frozen=True)
class ProfileConfig:
    enabled: bool = True
    reason: str | None = None
    source_account: str | None = None


@dataclass(frozen=True)
class StorageConfig:
    enabled: bool = True
    primary: str = "local_jsonl"
    analytics: str | None = None
    archive: str | None = None
    mirror: tuple[str, ...] = ()


@dataclass(frozen=True)
class PathsConfig:
    base_dir: str = "/home/jul/P-core/data/polymarket/live_observer"
    jsonl_dir: str = "/home/jul/P-core/data/polymarket/live_observer/jsonl"
    parquet_dir: str = "/home/jul/P-core/data/polymarket/live_observer/parquet"
    reports_dir: str = "/home/jul/P-core/data/polymarket/live_observer/reports"
    manifests_dir: str = "/home/jul/P-core/data/polymarket/live_observer/manifests"


@dataclass(frozen=True)
class S3Config:
    enabled: bool = False
    bucket_env: str = "PREDICTION_CORE_S3_BUCKET"
    prefix: str = "polymarket/live_observer"


@dataclass(frozen=True)
class SafetyConfig:
    paper_only: bool = True
    live_order_allowed: bool = False
    allow_wallet: bool = False
    allow_signing: bool = False
    require_mountpoint: str | None = None
    refuse_if_not_mounted: bool = True
    max_full_book_markets_per_run: int | None = None


@dataclass(frozen=True)
class LiveObserverConfig:
    version: int
    active_scenario: str
    scenarios: dict[str, ScenarioConfig]
    collection: CollectionConfig
    streams: dict[str, ToggleConfig]
    profiles: dict[str, ProfileConfig]
    followed_accounts: dict[str, ToggleConfig]
    storage: StorageConfig
    paths: PathsConfig
    s3: S3Config
    safety: SafetyConfig

    @property
    def active(self) -> ScenarioConfig:
        return self.scenarios[self.active_scenario]

    @property
    def live_collection_active(self) -> bool:
        return bool(self.collection.enabled and not self.collection.dry_run)


def load_live_observer_config(path: str | Path) -> LiveObserverConfig:
    """Load, validate, and apply environment overrides to live observer config."""

    data = _read_yaml(Path(path))
    if not isinstance(data, Mapping):
        raise ValueError("weather live observer config must be a YAML mapping")

    config = _build_config(data)
    config = _apply_env_overrides(config)
    _validate_config(config)
    return config


def _read_yaml(path: Path) -> Mapping[str, Any]:
    if yaml is None:  # pragma: no cover
        raise RuntimeError("PyYAML is required to load weather live observer YAML config")
    with path.open("r", encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle) or {}
    return loaded


def _build_config(data: Mapping[str, Any]) -> LiveObserverConfig:
    active_scenario = str(data.get("active_scenario", "minimal"))
    scenarios = {
        name: _scenario_config(value if isinstance(value, Mapping) else {})
        for name, value in _mapping(data.get("scenarios")).items()
    }
    collection = _collection_config(_mapping(data.get("collection")))
    streams = {
        name: _toggle_config(value if isinstance(value, Mapping) else {})
        for name, value in _mapping(data.get("streams")).items()
    }
    profiles = {
        name: _profile_config(value if isinstance(value, Mapping) else {})
        for name, value in _mapping(data.get("profiles")).items()
    }
    followed_accounts = {
        name: _toggle_config(value if isinstance(value, Mapping) else {})
        for name, value in _mapping(data.get("followed_accounts")).items()
    }

    return LiveObserverConfig(
        version=int(data.get("version", 1)),
        active_scenario=active_scenario,
        scenarios=scenarios,
        collection=collection,
        streams=streams,
        profiles=profiles,
        followed_accounts=followed_accounts,
        storage=_storage_config(_mapping(data.get("storage"))),
        paths=_paths_config(_mapping(data.get("paths"))),
        s3=_s3_config(_mapping(data.get("s3"))),
        safety=_safety_config(_mapping(data.get("safety"))),
    )


def _mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {}


def _scenario_config(data: Mapping[str, Any]) -> ScenarioConfig:
    retention = _mapping(data.get("retention"))
    return ScenarioConfig(
        market_limit=int(data.get("market_limit", 0)),
        surface_limit=int(data.get("surface_limit", 0)),
        followed_account_limit=int(data.get("followed_account_limit", 0)),
        compact_market_snapshot_interval_seconds=int(
            data.get("compact_market_snapshot_interval_seconds", 0)
        ),
        bin_surface_snapshot_interval_seconds=int(
            data.get("bin_surface_snapshot_interval_seconds", 0)
        ),
        forecast_snapshot_interval_seconds=int(data.get("forecast_snapshot_interval_seconds", 0)),
        trade_trigger_poll_interval_seconds=int(data.get("trade_trigger_poll_interval_seconds", 0)),
        full_book_policy=str(data.get("full_book_policy", "event_only")),
        retention=RetentionConfig(
            raw_days=_optional_int(retention.get("raw_days")),
            compact_days=_optional_int(retention.get("compact_days")),
            aggregate_days=_optional_int(retention.get("aggregate_days")),
        ),
    )


def _collection_config(data: Mapping[str, Any]) -> CollectionConfig:
    return CollectionConfig(
        enabled=bool(data.get("enabled", False)),
        dry_run=bool(data.get("dry_run", True)),
        reason=_optional_str(data.get("reason")),
    )


def _toggle_config(data: Mapping[str, Any]) -> ToggleConfig:
    return ToggleConfig(enabled=bool(data.get("enabled", True)), reason=_optional_str(data.get("reason")))


def _profile_config(data: Mapping[str, Any]) -> ProfileConfig:
    return ProfileConfig(
        enabled=bool(data.get("enabled", True)),
        reason=_optional_str(data.get("reason")),
        source_account=_optional_str(data.get("source_account")),
    )


def _storage_config(data: Mapping[str, Any]) -> StorageConfig:
    return StorageConfig(
        enabled=bool(data.get("enabled", True)),
        primary=str(data.get("primary", "local_jsonl")),
        analytics=_optional_str(data.get("analytics")),
        archive=_optional_str(data.get("archive")),
        mirror=tuple(str(item) for item in data.get("mirror", []) or []),
    )


def _paths_config(data: Mapping[str, Any]) -> PathsConfig:
    default = PathsConfig()
    return PathsConfig(
        base_dir=str(data.get("base_dir", default.base_dir)),
        jsonl_dir=str(data.get("jsonl_dir", default.jsonl_dir)),
        parquet_dir=str(data.get("parquet_dir", default.parquet_dir)),
        reports_dir=str(data.get("reports_dir", default.reports_dir)),
        manifests_dir=str(data.get("manifests_dir", default.manifests_dir)),
    )


def _s3_config(data: Mapping[str, Any]) -> S3Config:
    return S3Config(
        enabled=bool(data.get("enabled", False)),
        bucket_env=str(data.get("bucket_env", "PREDICTION_CORE_S3_BUCKET")),
        prefix=str(data.get("prefix", "polymarket/live_observer")),
    )


def _safety_config(data: Mapping[str, Any]) -> SafetyConfig:
    return SafetyConfig(
        paper_only=bool(data.get("paper_only", True)),
        live_order_allowed=bool(data.get("live_order_allowed", False)),
        allow_wallet=bool(data.get("allow_wallet", False)),
        allow_signing=bool(data.get("allow_signing", False)),
        require_mountpoint=_optional_str(data.get("require_mountpoint")),
        refuse_if_not_mounted=bool(data.get("refuse_if_not_mounted", True)),
        max_full_book_markets_per_run=_optional_int(data.get("max_full_book_markets_per_run")),
    )


def _apply_env_overrides(config: LiveObserverConfig) -> LiveObserverConfig:
    active_scenario = os.getenv("WEATHER_LIVE_OBSERVER_SCENARIO", config.active_scenario)

    collection = config.collection
    enabled_override = os.getenv("WEATHER_LIVE_OBSERVER_ENABLED")
    if enabled_override is not None:
        collection = CollectionConfig(
            enabled=_parse_bool_env("WEATHER_LIVE_OBSERVER_ENABLED", enabled_override),
            dry_run=collection.dry_run,
            reason=collection.reason,
        )

    paths = config.paths
    base_dir_override = os.getenv("WEATHER_LIVE_OBSERVER_BASE_DIR")
    if base_dir_override:
        base = base_dir_override.rstrip("/")
        paths = PathsConfig(
            base_dir=base,
            jsonl_dir=f"{base}/jsonl",
            parquet_dir=f"{base}/parquet",
            reports_dir=f"{base}/reports",
            manifests_dir=f"{base}/manifests",
        )

    storage = config.storage
    primary_override = os.getenv("WEATHER_LIVE_OBSERVER_PRIMARY_STORAGE")
    if primary_override:
        storage = StorageConfig(
            enabled=storage.enabled,
            primary=primary_override,
            analytics=storage.analytics,
            archive=storage.archive,
            mirror=storage.mirror,
        )

    return LiveObserverConfig(
        version=config.version,
        active_scenario=active_scenario,
        scenarios=config.scenarios,
        collection=collection,
        streams=config.streams,
        profiles=config.profiles,
        followed_accounts=config.followed_accounts,
        storage=storage,
        paths=paths,
        s3=config.s3,
        safety=config.safety,
    )


def _validate_config(config: LiveObserverConfig) -> None:
    if config.active_scenario not in ALLOWED_SCENARIOS:
        raise ValueError(f"unknown active_scenario: {config.active_scenario}")
    if config.active_scenario not in config.scenarios:
        raise ValueError(f"active_scenario not configured: {config.active_scenario}")
    unknown_scenarios = sorted(set(config.scenarios) - ALLOWED_SCENARIOS)
    if unknown_scenarios:
        raise ValueError(f"unknown scenario config keys: {', '.join(unknown_scenarios)}")
    _validate_storage_backend("storage.primary", config.storage.primary)
    if config.storage.analytics is not None:
        _validate_storage_backend("storage.analytics", config.storage.analytics)
    if config.storage.archive is not None:
        _validate_storage_backend("storage.archive", config.storage.archive)
    for backend in config.storage.mirror:
        _validate_storage_backend("storage.mirror", backend)

    if config.safety.paper_only is not True:
        raise ValueError("safety.paper_only must be true")
    if config.safety.live_order_allowed is not False:
        raise ValueError("safety.live_order_allowed must be false")
    if config.safety.allow_wallet is not False:
        raise ValueError("safety.allow_wallet must be false")
    if config.safety.allow_signing is not False:
        raise ValueError("safety.allow_signing must be false")


def _validate_storage_backend(field_name: str, value: str) -> None:
    if value not in ALLOWED_STORAGE_BACKENDS:
        raise ValueError(f"unknown {field_name}: {value}")


def _parse_bool_env(name: str, value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False
    raise ValueError(f"{name} must be one of 0, 1, false, true, off, on")


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)
