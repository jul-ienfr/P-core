from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class RiskCaps:
    max_order_usdc: float
    max_position_usdc: float
    max_event_usdc: float
    min_edge: float
    live_order_allowed: bool = False


@dataclass(frozen=True)
class StrategyProfile:
    id: str
    label: str
    inspiration: str
    required_inputs: tuple[str, ...]
    entry_gates: tuple[str, ...]
    risk_caps: RiskCaps
    execution_mode: str
    do_not_trade_rules: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["required_inputs"] = list(self.required_inputs)
        payload["entry_gates"] = list(self.entry_gates)
        payload["do_not_trade_rules"] = list(self.do_not_trade_rules)
        return payload


_PROFILES: tuple[StrategyProfile, ...] = (
    StrategyProfile(
        id="surface_grid_trader",
        label="Surface grid trader",
        inspiration="Event-surface arbitrage: trade only when related weather bins/thresholds disagree and source routing is direct.",
        required_inputs=("event_surface", "direct_resolution_source", "orderbook_depth", "strict_limit"),
        entry_gates=("surface_inconsistency_present", "source_confirmed", "edge_survives_fill", "strict_limit_not_crossed"),
        risk_caps=RiskCaps(max_order_usdc=15.0, max_position_usdc=45.0, max_event_usdc=60.0, min_edge=0.04),
        execution_mode="paper_strict_limit",
        do_not_trade_rules=("source_missing", "source_conflict", "empty_orderbook", "price_above_strict_limit", "edge_destroyed_by_fill"),
    ),
    StrategyProfile(
        id="exact_bin_anomaly_hunter",
        label="Exact-bin anomaly hunter",
        inspiration="Exact temperature/rainfall bin specialists: exploit impossible bin mass or stale exact-bin quotes without copying wallets.",
        required_inputs=("exact_bin_surface", "exact_bin_price_mass", "direct_resolution_source", "neighbor_thresholds"),
        entry_gates=("exact_bin_mass_anomaly", "source_confirmed", "neighbor_bins_consistent", "strict_limit_not_crossed"),
        risk_caps=RiskCaps(max_order_usdc=10.0, max_position_usdc=30.0, max_event_usdc=45.0, min_edge=0.05),
        execution_mode="paper_strict_limit",
        do_not_trade_rules=("source_missing", "ambiguous_exact_bin_rules", "isolated_bin_without_neighbor_context", "price_above_strict_limit"),
    ),
    StrategyProfile(
        id="threshold_resolution_harvester",
        label="Threshold resolution harvester",
        inspiration="Near-resolution threshold trading where official/latest source already favors one side.",
        required_inputs=("direct_resolution_source", "latest_observation", "threshold_value", "hours_to_resolution", "strict_limit"),
        entry_gates=("near_resolution_window", "source_margin_favors_side", "latest_source_available", "strict_limit_not_crossed"),
        risk_caps=RiskCaps(max_order_usdc=8.0, max_position_usdc=24.0, max_event_usdc=35.0, min_edge=0.03),
        execution_mode="paper_micro_strict_limit",
        do_not_trade_rules=("source_missing", "latest_observation_missing", "source_margin_too_small", "priced_in", "price_above_strict_limit"),
    ),
    StrategyProfile(
        id="profitable_consensus_radar",
        label="Profitable consensus radar",
        inspiration="Use clusters of profitable weather accounts as radar only; require independent source/orderbook confirmation before any paper entry.",
        required_inputs=("consensus_signal", "top_handles", "direct_resolution_source", "independent_edge", "orderbook_depth"),
        entry_gates=("multi_handle_consensus", "independent_source_confirms", "edge_survives_fill", "not_wallet_copy_only"),
        risk_caps=RiskCaps(max_order_usdc=5.0, max_position_usdc=15.0, max_event_usdc=25.0, min_edge=0.06),
        execution_mode="watchlist_only",
        do_not_trade_rules=("wallet_copy_only", "source_missing", "consensus_without_edge", "thin_book", "handle_cluster_conflict"),
    ),
    StrategyProfile(
        id="conviction_signal_follower",
        label="Conviction signal follower",
        inspiration="Follow repeated high-conviction strategy archetypes only after model/source/execution independently agree.",
        required_inputs=("matched_trader_archetypes", "probability_edge", "direct_resolution_source", "execution_snapshot"),
        entry_gates=("conviction_archetype_match", "min_edge_met", "source_confirmed", "edge_survives_fill"),
        risk_caps=RiskCaps(max_order_usdc=12.0, max_position_usdc=36.0, max_event_usdc=50.0, min_edge=0.07),
        execution_mode="paper_strict_limit",
        do_not_trade_rules=("source_missing", "archetype_only_no_edge", "conflicting_archetypes", "edge_destroyed_by_fill", "portfolio_cap_reached"),
    ),
    StrategyProfile(
        id="macro_weather_event_trader",
        label="Macro weather event trader",
        inspiration="Large weather-event themes such as hurricanes, freezes, heat waves, and precipitation outbreaks with event-level risk controls.",
        required_inputs=("macro_event_context", "forecast_bundle", "resolution_rules", "liquidity_snapshot"),
        entry_gates=("macro_event_identified", "forecast_source_supported", "rules_clear", "liquidity_sufficient"),
        risk_caps=RiskCaps(max_order_usdc=20.0, max_position_usdc=60.0, max_event_usdc=80.0, min_edge=0.08),
        execution_mode="operator_review",
        do_not_trade_rules=("unclear_resolution_rules", "unsupported_forecast_source", "headline_only_no_market_edge", "event_correlation_cap_reached"),
    ),
)

_PROFILE_BY_ID = {profile.id: profile for profile in _PROFILES}


def strategy_id_for_profile(profile_id: str) -> str:
    return f"weather_profile_{profile_id}_v1"


def list_strategy_profiles() -> list[dict[str, Any]]:
    return [profile.to_dict() for profile in _PROFILES]


def get_strategy_profile(profile_id: str) -> dict[str, Any]:
    try:
        return _PROFILE_BY_ID[profile_id].to_dict()
    except KeyError as exc:
        raise KeyError(f"unknown strategy profile id: {profile_id}") from exc


def classify_candidate_row(row: dict[str, Any]) -> dict[str, Any]:
    blockers = _row_blockers(row)
    profile_id = _profile_id_for_row(row)
    if blockers and profile_id is None:
        return {"profile_id": None, "profile": None, "blockers": blockers}

    profile = get_strategy_profile(profile_id) if profile_id else None
    return {
        "profile_id": profile_id,
        "profile": profile["label"] if profile else None,
        "risk_caps": profile["risk_caps"] if profile else None,
        "execution_mode": profile["execution_mode"] if profile else None,
        "blockers": [],
    }


def operator_profile_matrix() -> list[dict[str, Any]]:
    matrix: list[dict[str, Any]] = []
    for profile in _PROFILES:
        matrix.append(
            {
                "id": profile.id,
                "label": profile.label,
                "execution_mode": profile.execution_mode,
                "max_order_usdc": profile.risk_caps.max_order_usdc,
                "max_position_usdc": profile.risk_caps.max_position_usdc,
                "entry_gates": list(profile.entry_gates),
                "required_inputs": list(profile.required_inputs),
                "do_not_trade": list(profile.do_not_trade_rules),
            }
        )
    return matrix


def compact_strategy_profile_report() -> dict[str, Any]:
    return {"profile_count": len(_PROFILES), "profiles": operator_profile_matrix()}


def strategy_profiles_markdown() -> str:
    lines = [
        "# Weather Strategy Profiles",
        "",
        "| ID | Execution | Max order | Entry gates | Do-not-trade |",
        "| --- | --- | ---: | --- | --- |",
    ]
    for row in operator_profile_matrix():
        lines.append(
            "| {id} | {execution_mode} | {max_order_usdc:g} | {gates} | {blocks} |".format(
                id=row["id"],
                execution_mode=row["execution_mode"],
                max_order_usdc=row["max_order_usdc"],
                gates=", ".join(row["entry_gates"]),
                blocks=", ".join(row["do_not_trade"]),
            )
        )
    lines.append("")
    return "\n".join(lines)


def _row_blockers(row: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    source_direct = row.get("source_direct")
    source_status = str(row.get("source_status") or "").lower()
    if source_direct is False or source_status in {"source_missing", "source_fetch_error", "source_conflict"}:
        blockers.append("source_missing" if source_status != "source_conflict" else "source_conflict")
    execution_blocker = row.get("execution_blocker")
    if execution_blocker in {"empty_orderbook", "missing_tradeable_quote", "edge_destroyed_by_fill", "strict_limit_price_exceeded"}:
        blockers.append(str(execution_blocker))
    return blockers


def _profile_id_for_row(row: dict[str, Any]) -> str | None:
    inconsistency_types = {str(item) for item in row.get("surface_inconsistency_types") or []}
    threshold_watch = row.get("threshold_watch") if isinstance(row.get("threshold_watch"), dict) else {}
    consensus_signal = row.get("consensus_signal") if isinstance(row.get("consensus_signal"), dict) else {}
    question = str(row.get("question") or "").lower()
    event_category = str(row.get("event_category") or row.get("category") or "").lower()

    if _is_macro_weather_event(question, event_category):
        return "macro_weather_event_trader"
    if threshold_watch.get("eligible") or threshold_watch.get("recommendation") in {"paper_micro_strict_limit", "avoid_price_too_high", "priced_in"}:
        return "threshold_resolution_harvester"
    if "exact_bin_mass_exceeds_one" in inconsistency_types or "exact_bin_mass_below_one" in inconsistency_types or _number(row.get("exact_bin_price_mass"), 0.0) > 1.0:
        return "exact_bin_anomaly_hunter"
    if int(row.get("surface_inconsistency_count") or len(inconsistency_types)) > 0:
        return "surface_grid_trader"
    if int(consensus_signal.get("handle_count") or row.get("consensus_handle_count") or 0) >= 2:
        return "profitable_consensus_radar"
    if row.get("matched_traders") or row.get("matched_trader_archetypes"):
        return "conviction_signal_follower"
    if _number(row.get("probability_edge"), 0.0) >= 0.08 and str(row.get("decision_status") or "") in {"trade", "trade_small"}:
        return "conviction_signal_follower"
    return None


def _is_macro_weather_event(question: str, event_category: str) -> bool:
    haystack = f"{event_category} {question}"
    terms = ("hurricane", "tropical storm", "landfall", "freeze", "heat wave", "blizzard", "snowstorm", "macro")
    return any(term in haystack for term in terms)


def _number(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
