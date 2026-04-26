from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable


@dataclass(frozen=True, kw_only=True)
class GateDecision:
    status: str
    enough_data: bool
    paper_strategy_ready: bool
    reasons: list[str] = field(default_factory=list)
    total_predictions: int = 0
    matched_observations: int = 0
    hit_rate: float | None = None
    liquidity_caveat_rate: float | None = None
    weather_only_caveat: bool = False

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "enough_data": self.enough_data,
            "paper_strategy_ready": self.paper_strategy_ready,
            "reasons": list(self.reasons),
            "total_predictions": self.total_predictions,
            "matched_observations": self.matched_observations,
            "hit_rate": self.hit_rate,
            "liquidity_caveat_rate": self.liquidity_caveat_rate,
            "weather_only_caveat": self.weather_only_caveat,
        }


@dataclass(frozen=True, kw_only=True)
class LiveMicrotestGateDecision:
    """Decision record for the Phase 10 live micro-test gate.

    This gate is intentionally conservative: it can say that prerequisites are
    sufficient to draft a *separate* live micro-test plan, but it never enables
    live trading inside this migration plan.
    """

    status: str
    separate_plan_may_be_drafted: bool
    live_trading_allowed_by_this_plan: bool = False
    reasons: list[str] = field(default_factory=list)
    matched_observations: int = 0
    out_of_sample_positive_archetypes: list[str] = field(default_factory=list)
    paper_strategy_positive_after_costs: bool = False
    unresolved_leakage_issues: list[str] = field(default_factory=list)
    dashboard_state_exposed: bool = False
    explicit_user_approval: bool = False

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "separate_plan_may_be_drafted": self.separate_plan_may_be_drafted,
            "live_trading_allowed_by_this_plan": self.live_trading_allowed_by_this_plan,
            "reasons": list(self.reasons),
            "matched_observations": self.matched_observations,
            "out_of_sample_positive_archetypes": list(self.out_of_sample_positive_archetypes),
            "paper_strategy_positive_after_costs": self.paper_strategy_positive_after_costs,
            "unresolved_leakage_issues": list(self.unresolved_leakage_issues),
            "dashboard_state_exposed": self.dashboard_state_exposed,
            "explicit_user_approval": self.explicit_user_approval,
        }


def decide_live_microtest_gate(
    *,
    matched_observations: int,
    out_of_sample_positive_archetypes: Iterable[str] = (),
    paper_strategy_positive_after_costs: bool = False,
    unresolved_leakage_issues: Iterable[str] = (),
    dashboard_state_exposed: bool = False,
    explicit_user_approval: bool = False,
    min_matched_observations: int = 200,
) -> LiveMicrotestGateDecision:
    """Evaluate the Phase 10 gate without authorizing live trading.

    Returns ``blocked`` unless every Phase 8 live-discussion prerequisite is
    true and explicit user approval exists. Even then, the result only permits
    drafting a separate future micro-test plan; this migration plan remains
    paper-only/read-only and cannot place real orders.
    """

    archetypes = sorted({str(item) for item in out_of_sample_positive_archetypes if str(item).strip()})
    leakage_issues = [str(item) for item in unresolved_leakage_issues if str(item).strip()]
    reasons: list[str] = []
    if matched_observations < min_matched_observations:
        reasons.append(f"requires {min_matched_observations}+ matched shadow/crowd observations; found {matched_observations}")
    if not archetypes:
        reasons.append("requires an out-of-sample positive relationship for at least one archetype")
    if not paper_strategy_positive_after_costs:
        reasons.append("requires paper strategy to remain positive after conservative spread/slippage")
    if leakage_issues:
        reasons.append("unresolved source leakage/lookahead issues must be cleared: " + "; ".join(leakage_issues))
    if not dashboard_state_exposed:
        reasons.append("requires dashboard state sufficient for Julien to understand decisions")
    if not explicit_user_approval:
        reasons.append("requires separate explicit Julien approval for live micro-test planning")

    if reasons:
        return LiveMicrotestGateDecision(
            status="blocked",
            separate_plan_may_be_drafted=False,
            reasons=reasons,
            matched_observations=matched_observations,
            out_of_sample_positive_archetypes=archetypes,
            paper_strategy_positive_after_costs=paper_strategy_positive_after_costs,
            unresolved_leakage_issues=leakage_issues,
            dashboard_state_exposed=dashboard_state_exposed,
            explicit_user_approval=explicit_user_approval,
        )

    return LiveMicrotestGateDecision(
        status="eligible_for_separate_plan",
        separate_plan_may_be_drafted=True,
        reasons=["all Phase 8 live-discussion prerequisites and explicit approval are present; draft a separate plan before any live action"],
        matched_observations=matched_observations,
        out_of_sample_positive_archetypes=archetypes,
        paper_strategy_positive_after_costs=paper_strategy_positive_after_costs,
        unresolved_leakage_issues=leakage_issues,
        dashboard_state_exposed=dashboard_state_exposed,
        explicit_user_approval=explicit_user_approval,
    )


def decide_measurement_gate(
    *,
    total_predictions: int,
    matched_observations: int,
    hit_rate: float | None,
    categories: Iterable[str],
    liquidity_caveat_rate: float | None,
    out_of_sample_positive: bool | None = None,
    min_predictions: int = 100,
    min_matched: int = 30,
    preferred_paper_matched: int = 200,
    promising_hit_rate: float = 0.55,
    max_liquidity_caveat_rate: float = 0.25,
) -> GateDecision:
    reasons: list[str] = []
    category_set = {str(c) for c in categories if c}
    weather_only = category_set == {"weather"}

    if total_predictions < min_predictions:
        reasons.append(f"requires 100+ shadow predictions logged; found {total_predictions}")
    if matched_observations < min_matched:
        reasons.append(f"requires 30+ matched after-window observations; found {matched_observations}")
    if not category_set:
        reasons.append("requires market category evidence or explicit weather-only caveat; found none")

    if reasons:
        return GateDecision(
            status="not_enough_data",
            enough_data=False,
            paper_strategy_ready=False,
            reasons=reasons,
            total_predictions=total_predictions,
            matched_observations=matched_observations,
            hit_rate=hit_rate,
            liquidity_caveat_rate=liquidity_caveat_rate,
            weather_only_caveat=weather_only,
        )

    if weather_only:
        reasons.append("weather-only caveat: category diversity gate not met; interpretation is weather-market-local")
    elif len(category_set) < 2:
        reasons.append("category caveat: fewer than two market categories observed")

    if hit_rate is not None and hit_rate < 0.5:
        reasons.append(f"directional relationship rejected: hit rate {hit_rate:.3f} below 0.500 after enough data")
        return GateDecision(
            status="rejected",
            enough_data=True,
            paper_strategy_ready=False,
            reasons=reasons,
            total_predictions=total_predictions,
            matched_observations=matched_observations,
            hit_rate=hit_rate,
            liquidity_caveat_rate=liquidity_caveat_rate,
            weather_only_caveat=weather_only,
        )

    liquidity_ok = liquidity_caveat_rate is not None and liquidity_caveat_rate <= max_liquidity_caveat_rate
    if (
        matched_observations >= preferred_paper_matched
        and hit_rate is not None
        and hit_rate >= promising_hit_rate
        and out_of_sample_positive is True
        and liquidity_ok
    ):
        reasons.append("preferred paper-strategy experiment gate met: 200+ matched, positive out-of-sample directional relationship, acceptable liquidity caveat rate")
        return GateDecision(
            status="promising",
            enough_data=True,
            paper_strategy_ready=True,
            reasons=reasons,
            total_predictions=total_predictions,
            matched_observations=matched_observations,
            hit_rate=hit_rate,
            liquidity_caveat_rate=liquidity_caveat_rate,
            weather_only_caveat=weather_only,
        )

    if out_of_sample_positive is False:
        reasons.append("directional relationship not positive out-of-sample; do not advance to paper strategy experiment")
    if matched_observations < preferred_paper_matched:
        reasons.append(f"paper strategy experiment prefers 200+ matched observations; found {matched_observations}")
    if not liquidity_ok:
        reasons.append("liquidity caveat rate is unknown or above threshold for later strategy experiments")

    return GateDecision(
        status="enough_data",
        enough_data=True,
        paper_strategy_ready=False,
        reasons=reasons,
        total_predictions=total_predictions,
        matched_observations=matched_observations,
        hit_rate=hit_rate,
        liquidity_caveat_rate=liquidity_caveat_rate,
        weather_only_caveat=weather_only,
    )
