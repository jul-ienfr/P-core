from __future__ import annotations

from datetime import UTC, datetime

import pytest

from prediction_core.strategies import StrategyDescriptor, StrategyMode, StrategyRunRequest, StrategyRunResult, StrategySignal
from prediction_core.strategies.config import StrategyConfig, StrategyRegistryConfig
from prediction_core.strategies.registry import StrategyRegistry


class DummyStrategy:
    def __init__(self, strategy_id: str = "dummy", *, mode: StrategyMode = StrategyMode.RESEARCH_ONLY, fail: bool = False) -> None:
        self.descriptor = StrategyDescriptor(strategy_id=strategy_id, name=strategy_id, target="event_outcome_forecasting", mode=mode)
        self.fail = fail

    def run(self, request: StrategyRunRequest) -> StrategyRunResult:
        if self.fail:
            raise RuntimeError("boom")
        signal = StrategySignal(
            strategy_id=self.descriptor.strategy_id,
            market_id=request.market_id,
            target=self.descriptor.target,
            mode=self.descriptor.mode,
            generated_at=datetime(2026, 1, 1, tzinfo=UTC),
            probability=0.6,
            confidence=0.7,
            features={},
            risks=[],
            source={"fixture": True},
        )
        return StrategyRunResult(strategy_id=self.descriptor.strategy_id, market_id=request.market_id, mode=self.descriptor.mode, signals=[signal])


def test_registration_and_duplicate_rejection() -> None:
    registry = StrategyRegistry()
    registry.register(DummyStrategy(), StrategyConfig(strategy_id="dummy", enabled=True))
    with pytest.raises(ValueError, match="duplicate"):
        registry.register(DummyStrategy(), StrategyConfig(strategy_id="dummy", enabled=True))


def test_enabled_filtering_and_disabled_skip() -> None:
    registry = StrategyRegistry()
    registry.register(DummyStrategy("on"), StrategyConfig(strategy_id="on", enabled=True))
    registry.register(DummyStrategy("off"), StrategyConfig(strategy_id="off", enabled=False))
    request = StrategyRunRequest(market_id="m")

    assert [item.strategy_id for item in registry.enabled()] == ["on"]
    assert len(registry.run_enabled(request)) == 1
    disabled = registry.run_one("off", request)
    assert disabled.signals == []
    assert disabled.metadata["skipped"] == "disabled"


def test_live_mode_rejected_by_default() -> None:
    registry = StrategyRegistry()
    with pytest.raises(ValueError, match="live_allowed"):
        registry.register(DummyStrategy("live", mode=StrategyMode.LIVE_ALLOWED), StrategyConfig(strategy_id="live", enabled=True))
    with pytest.raises(ValueError, match="allow_live"):
        StrategyConfig(strategy_id="live", mode=StrategyMode.LIVE_ALLOWED)


def test_live_mode_can_be_explicitly_represented_when_allowed() -> None:
    registry = StrategyRegistry(allow_live=True)
    registry.register(
        DummyStrategy("live", mode=StrategyMode.LIVE_ALLOWED),
        StrategyConfig(strategy_id="live", enabled=True, mode=StrategyMode.LIVE_ALLOWED, allow_live=True),
    )
    assert registry.enabled()[0].strategy_id == "live"


def test_failure_captured_in_result_errors() -> None:
    registry = StrategyRegistry()
    registry.register(DummyStrategy("bad", fail=True), StrategyConfig(strategy_id="bad", enabled=True))
    result = registry.run_enabled(StrategyRunRequest(market_id="m"))[0]
    assert result.signals == []
    assert result.errors == ["boom"]


def test_registry_config_default_disabled() -> None:
    cfg = StrategyRegistryConfig()
    assert cfg.config_for("missing").enabled is False
