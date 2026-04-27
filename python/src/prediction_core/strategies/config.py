from __future__ import annotations

from dataclasses import dataclass, field

from .contracts import StrategyMode


@dataclass(frozen=True, kw_only=True)
class StrategyConfig:
    strategy_id: str
    enabled: bool = False
    mode: StrategyMode | str = StrategyMode.RESEARCH_ONLY
    allow_live: bool = False
    settings: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.strategy_id.strip():
            raise ValueError("strategy_id is required")
        mode = self.mode if isinstance(self.mode, StrategyMode) else StrategyMode(str(self.mode))
        object.__setattr__(self, "mode", mode)
        if mode == StrategyMode.LIVE_ALLOWED and not self.allow_live:
            raise ValueError("live_allowed strategies require explicit allow_live=True")


@dataclass(frozen=True, kw_only=True)
class StrategyRegistryConfig:
    strategies: dict[str, StrategyConfig] = field(default_factory=dict)
    allow_live: bool = False

    def config_for(self, strategy_id: str) -> StrategyConfig:
        return self.strategies.get(strategy_id, StrategyConfig(strategy_id=strategy_id, allow_live=self.allow_live))

    @classmethod
    def from_configs(cls, configs: list[StrategyConfig], *, allow_live: bool = False) -> "StrategyRegistryConfig":
        return cls(strategies={cfg.strategy_id: cfg for cfg in configs}, allow_live=allow_live)
