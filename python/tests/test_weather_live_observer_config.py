from pathlib import Path

import pytest

from weather_pm.live_observer_config import load_live_observer_config


def test_default_config_loads_bounded_live_readonly_collection():
    config = load_live_observer_config(Path("config/weather_live_observer.yaml"))

    assert config.version == 1
    assert config.active_scenario == "minimal"
    assert config.active.market_limit == 100
    assert config.active.followed_account_limit == 10
    assert config.storage.primary == "local_jsonl"
    assert config.storage.analytics is None
    assert config.collection.enabled is True
    assert config.collection.dry_run is False
    assert config.live_collection_active is True
    assert config.safety.paper_only is True
    assert config.safety.live_order_allowed is False
    assert config.safety.allow_wallet is False
    assert config.safety.allow_signing is False
    assert config.safety.require_mountpoint == "/mnt/truenas"
    assert config.safety.refuse_if_not_mounted is True
    assert config.paths.base_dir == "/mnt/truenas/p-core/polymarket/live_observer"
    assert list(config.followed_accounts) == [
        "ColdMath",
        "Poligarch",
        "Railbird",
        "xX25Xx",
        "syacxxa",
        "0xhana",
        "Maskache2",
        "Amano-Hina",
        "mjf02",
        "dpnd",
    ]


def test_unknown_active_scenario_is_rejected(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("version: 1\nactive_scenario: turbo\nscenarios: {}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="unknown active_scenario"):
        load_live_observer_config(path)


@pytest.mark.parametrize(
    "yaml_text,match",
    [
        ("safety:\n  paper_only: false\n  live_order_allowed: false\n", "paper_only"),
        ("safety:\n  paper_only: true\n  live_order_allowed: true\n", "live_order_allowed"),
        ("safety:\n  paper_only: true\n  live_order_allowed: false\n  allow_wallet: true\n", "allow_wallet"),
        ("safety:\n  paper_only: true\n  live_order_allowed: false\n  allow_signing: true\n", "allow_signing"),
    ],
)
def test_safety_flags_are_enforced(tmp_path, yaml_text, match):
    path = tmp_path / "config.yaml"
    path.write_text(
        "version: 1\n"
        "active_scenario: minimal\n"
        "scenarios:\n"
        "  minimal:\n"
        "    market_limit: 100\n"
        + yaml_text,
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=match):
        load_live_observer_config(path)


def test_env_override_can_switch_to_minimal(monkeypatch):
    monkeypatch.setenv("WEATHER_LIVE_OBSERVER_SCENARIO", "minimal")
    config = load_live_observer_config(Path("config/weather_live_observer.yaml"))

    assert config.active_scenario == "minimal"
    assert config.active.market_limit == 100


def test_env_override_can_turn_collection_off_even_when_scenario_is_aggressive(monkeypatch):
    monkeypatch.setenv("WEATHER_LIVE_OBSERVER_SCENARIO", "aggressive")
    monkeypatch.setenv("WEATHER_LIVE_OBSERVER_ENABLED", "0")
    config = load_live_observer_config(Path("config/weather_live_observer.yaml"))

    assert config.active_scenario == "aggressive"
    assert config.collection.enabled is False
    assert config.live_collection_active is False


@pytest.mark.parametrize("value", ["1", "true", "on"])
def test_env_override_can_turn_collection_on(monkeypatch, value):
    monkeypatch.setenv("WEATHER_LIVE_OBSERVER_ENABLED", value)
    config = load_live_observer_config(Path("config/weather_live_observer.yaml"))

    assert config.collection.enabled is True
    assert config.live_collection_active is True


def test_env_override_can_replace_base_dir_and_primary_storage(monkeypatch):
    monkeypatch.setenv("WEATHER_LIVE_OBSERVER_BASE_DIR", "/tmp/weather-live")
    monkeypatch.setenv("WEATHER_LIVE_OBSERVER_PRIMARY_STORAGE", "local_jsonl")

    config = load_live_observer_config(Path("config/weather_live_observer.yaml"))

    assert config.paths.base_dir == "/tmp/weather-live"
    assert config.paths.jsonl_dir == "/tmp/weather-live/jsonl"
    assert config.paths.parquet_dir == "/tmp/weather-live/parquet"
    assert config.storage.primary == "local_jsonl"


def test_collection_disabled_makes_live_runner_noop(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        """
version: 1
active_scenario: aggressive
collection:
  enabled: false
  dry_run: false
  reason: operator_pause
scenarios:
  aggressive:
    market_limit: 1000
storage:
  enabled: true
safety:
  paper_only: true
  live_order_allowed: false
""",
        encoding="utf-8",
    )

    config = load_live_observer_config(path)

    assert config.active_scenario == "aggressive"
    assert config.collection.enabled is False
    assert config.collection.reason == "operator_pause"
    assert config.live_collection_active is False


def test_active_scenario_is_prepared_but_inactive_when_collection_is_off(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        """
version: 1
active_scenario: aggressive
collection:
  enabled: false
scenarios:
  aggressive:
    market_limit: 1000
storage:
  enabled: true
safety:
  paper_only: true
  live_order_allowed: false
""",
        encoding="utf-8",
    )

    config = load_live_observer_config(path)

    assert config.active_scenario == "aggressive"
    assert config.active.market_limit == 1000
    assert config.live_collection_active is False


def test_stream_and_profile_disable_flags_are_loaded(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        """
version: 1
active_scenario: aggressive
collection:
  enabled: true
streams:
  forecasts:
    enabled: false
profiles:
  shadow_coldmath_v0:
    enabled: false
    reason: noisy_profile
followed_accounts:
  ColdMath:
    enabled: false
    reason: pause_account
scenarios:
  aggressive:
    market_limit: 1000
storage:
  enabled: true
safety:
  paper_only: true
  live_order_allowed: false
""",
        encoding="utf-8",
    )

    config = load_live_observer_config(path)

    assert config.streams["forecasts"].enabled is False
    assert config.profiles["shadow_coldmath_v0"].enabled is False
    assert config.profiles["shadow_coldmath_v0"].reason == "noisy_profile"
    assert config.followed_accounts["ColdMath"].enabled is False
    assert config.followed_accounts["ColdMath"].reason == "pause_account"
