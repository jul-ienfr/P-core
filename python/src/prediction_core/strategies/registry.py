from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .config import StrategyConfig, StrategyRegistryConfig
from .contracts import StrategyDescriptor, StrategyMode, StrategyRunRequest, StrategyRunResult


class StrategyProtocol(Protocol):
    descriptor: StrategyDescriptor

    def run(self, request: StrategyRunRequest) -> StrategyRunResult: ...


@dataclass(frozen=True, kw_only=True)
class RegisteredStrategy:
    strategy: StrategyProtocol
    config: StrategyConfig

    @property
    def descriptor(self) -> StrategyDescriptor:
        return self.strategy.descriptor

    @property
    def strategy_id(self) -> str:
        return self.descriptor.strategy_id

    @property
    def enabled(self) -> bool:
        return self.config.enabled


class StrategyRegistry:
    def __init__(self, config: StrategyRegistryConfig | None = None, *, allow_live: bool = False) -> None:
        self.config = config or StrategyRegistryConfig(allow_live=allow_live)
        self.allow_live = allow_live or self.config.allow_live
        self._strategies: dict[str, RegisteredStrategy] = {}

    def register(self, strategy: StrategyProtocol, config: StrategyConfig | None = None) -> None:
        descriptor = strategy.descriptor
        strategy_id = descriptor.strategy_id
        if strategy_id in self._strategies:
            raise ValueError(f"duplicate strategy_id: {strategy_id}")
        cfg = config or self.config.config_for(strategy_id)
        if descriptor.mode == StrategyMode.LIVE_ALLOWED and not (self.allow_live or cfg.allow_live):
            raise ValueError("live_allowed strategies are blocked by default")
        if cfg.mode == StrategyMode.LIVE_ALLOWED and not (self.allow_live or cfg.allow_live):
            raise ValueError("live_allowed strategy config requires explicit allow_live")
        self._strategies[strategy_id] = RegisteredStrategy(strategy=strategy, config=cfg)

    def registered(self) -> list[RegisteredStrategy]:
        return list(self._strategies.values())

    def enabled(self) -> list[RegisteredStrategy]:
        return [item for item in self._strategies.values() if item.enabled]

    def run_one(self, strategy_id: str, request: StrategyRunRequest) -> StrategyRunResult:
        if strategy_id not in self._strategies:
            raise KeyError(strategy_id)
        item = self._strategies[strategy_id]
        if not item.enabled:
            return StrategyRunResult(strategy_id=strategy_id, market_id=request.market_id, mode=item.descriptor.mode, signals=[], metadata={"skipped": "disabled"})
        try:
            return item.strategy.run(request)
        except Exception as exc:  # noqa: BLE001 - registry boundary captures strategy failures
            return StrategyRunResult(strategy_id=strategy_id, market_id=request.market_id, mode=item.descriptor.mode, errors=[str(exc)])

    def run_enabled(self, request: StrategyRunRequest) -> list[StrategyRunResult]:
        results: list[StrategyRunResult] = []
        for item in self.enabled():
            results.append(self.run_one(item.strategy_id, request))
        return results
