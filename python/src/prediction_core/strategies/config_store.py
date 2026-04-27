from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from prediction_core.analytics.events import StrategyConfigEvent

from .config import StrategyConfig
from .contracts import StrategyMode


DEFAULT_STRATEGY_CONFIG_PATH = Path("/home/jul/P-core/data/strategy_config.json")
DEFAULT_STRATEGY_AUDIT_PATH = Path("/home/jul/P-core/data/strategy_config_audit.jsonl")


def default_strategy_config_path() -> Path:
    return Path(os.environ.get("PREDICTION_CORE_STRATEGY_CONFIG_PATH") or DEFAULT_STRATEGY_CONFIG_PATH)


def default_strategy_audit_path() -> Path:
    return Path(os.environ.get("PREDICTION_CORE_STRATEGY_AUDIT_PATH") or DEFAULT_STRATEGY_AUDIT_PATH)


class StrategyConfigStore:
    def __init__(self, path: Path | None = None, *, audit_path: Path | None = None) -> None:
        self.path = path or default_strategy_config_path()
        self.audit_path = audit_path or default_strategy_audit_path()

    def list_configs(self) -> dict[str, Any]:
        return {"strategies": {strategy_id: self._config_to_payload(config) for strategy_id, config in self._load_configs().items()}}

    def list_config_events(self, *, observed_at: datetime | None = None) -> list[StrategyConfigEvent]:
        timestamp = observed_at or datetime.now(UTC)
        return [self._config_to_event(config, observed_at=timestamp) for config in self._load_configs().values()]

    def get_config(self, strategy_id: str) -> StrategyConfig:
        configs = self._load_configs()
        return configs.get(strategy_id, StrategyConfig(strategy_id=strategy_id))

    def update_config(self, strategy_id: str, payload: dict[str, Any]) -> StrategyConfig:
        current = self.get_config(strategy_id)
        merged = {
            "strategy_id": strategy_id,
            "enabled": payload.get("enabled", current.enabled),
            "mode": payload.get("mode", current.mode.value),
            "allow_live": payload.get("allow_live", current.allow_live),
            "settings": payload.get("settings", current.settings),
        }
        config = self._config_from_payload(merged)
        configs = self._load_configs()
        configs[strategy_id] = config
        self._write_configs(configs)
        self._append_audit("update", strategy_id, self._config_to_payload(config))
        return config

    def set_enabled(self, strategy_id: str, enabled: bool) -> StrategyConfig:
        return self.update_config(strategy_id, {"enabled": enabled})

    def set_mode(self, strategy_id: str, mode: str, *, allow_live: bool | None = None) -> StrategyConfig:
        payload: dict[str, Any] = {"mode": mode}
        if allow_live is not None:
            payload["allow_live"] = allow_live
        return self.update_config(strategy_id, payload)

    def _load_configs(self) -> dict[str, StrategyConfig]:
        if not self.path.exists():
            return {}
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("strategy config file must be an object")
        raw_strategies = payload.get("strategies", {})
        if not isinstance(raw_strategies, dict):
            raise ValueError("strategy config strategies must be an object")
        return {str(strategy_id): self._config_from_payload({**dict(raw), "strategy_id": str(strategy_id)}) for strategy_id, raw in raw_strategies.items() if isinstance(raw, dict)}

    def _write_configs(self, configs: dict[str, StrategyConfig]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"strategies": {strategy_id: self._config_to_payload(config) for strategy_id, config in sorted(configs.items())}}
        with NamedTemporaryFile("w", encoding="utf-8", dir=str(self.path.parent), delete=False) as tmp:
            json.dump(payload, tmp, indent=2, sort_keys=True)
            tmp.write("\n")
            temp_path = Path(tmp.name)
        temp_path.replace(self.path)

    def _append_audit(self, action: str, strategy_id: str, payload: dict[str, Any]) -> None:
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)
        event = {"observed_at": datetime.now(UTC).isoformat(), "action": action, "strategy_id": strategy_id, "config": payload}
        with self.audit_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n")

    def _config_from_payload(self, payload: dict[str, Any]) -> StrategyConfig:
        strategy_id = payload.get("strategy_id")
        if not isinstance(strategy_id, str) or not strategy_id.strip():
            raise ValueError("strategy_id is required")
        settings = payload.get("settings", {})
        if not isinstance(settings, dict):
            raise ValueError("settings must be an object")
        _validate_settings(settings)
        return StrategyConfig(
            strategy_id=strategy_id,
            enabled=bool(payload.get("enabled", False)),
            mode=StrategyMode(str(payload.get("mode", StrategyMode.RESEARCH_ONLY.value))),
            allow_live=bool(payload.get("allow_live", False)),
            settings=dict(settings),
        )

    def _config_to_payload(self, config: StrategyConfig) -> dict[str, Any]:
        payload = asdict(config)
        payload["mode"] = config.mode.value
        return payload

    def _config_to_event(self, config: StrategyConfig, *, observed_at: datetime) -> StrategyConfigEvent:
        payload = self._config_to_payload(config)
        return StrategyConfigEvent(
            strategy_id=config.strategy_id,
            observed_at=observed_at,
            enabled=config.enabled,
            mode=config.mode.value,
            allow_live=config.allow_live,
            settings=dict(config.settings),
            raw=payload,
        )


def _validate_settings(settings: dict[str, Any]) -> None:
    for key, value in settings.items():
        if isinstance(value, bool):
            continue
        if isinstance(value, int | float) and value < 0:
            raise ValueError(f"{key} must be non-negative")
    max_order = settings.get("max_order_usdc")
    max_position = settings.get("max_position_usdc")
    if isinstance(max_order, int | float) and isinstance(max_position, int | float) and max_position < max_order:
        raise ValueError("max_position_usdc must be >= max_order_usdc")
