from __future__ import annotations

from pathlib import Path

from .gates import GateDecision
from .measurement import MeasurementSummary


def _fmt_rate(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3f}"


def render_measurement_report(
    *,
    summary: MeasurementSummary,
    gate_decision: GateDecision | None,
    status: str,
    db_status: str,
    artifact_path: Path,
    errors: list[str] | None = None,
) -> str:
    gate = gate_decision or summary.gate_decision
    lines = [
        "# Panoptique Crowd-Flow Measurement",
        "",
        "Paper-only operator summary for shadow predictions versus later price/volume/orderbook movement.",
        "No real orders were placed. This report measures paper-only market movement, not monetary returns.",
        "",
        "## Run status",
        "",
        f"- Status: `{status}`",
        f"- DB status: `{db_status}`",
        f"- Artifact: `{artifact_path}`",
        "- Safety: no wallet credentials, no real-money trading, no trading action generated.",
        "",
        "## Measurement separation",
        "",
        "- Event accuracy: not measured",
        "- Crowd-flow prediction accuracy: " + summary.measurement_separation.get("crowd_flow_prediction_accuracy", "not_measured"),
        "- Execution feasibility: liquidity caveat only",
        "",
        "## Aggregate metrics",
        "",
        f"- Shadow predictions logged: `{summary.total_predictions}`",
        f"- Matched after-window observations: `{summary.matched_observations}`",
        f"- False positive rate: `{summary.false_positive_rate:.3f}`",
        f"- Insufficient liquidity count: `{summary.insufficient_liquidity_count}`",
        f"- Categories: `{', '.join(sorted(summary.categories)) if summary.categories else 'none'}`",
        "",
        "### Hit rate by shadow bot",
        "",
    ]
    if summary.hit_rate_by_agent:
        lines.extend(f"- `{agent}`: `{rate:.3f}`" for agent, rate in sorted(summary.hit_rate_by_agent.items()))
    else:
        lines.append("- none")
    lines.extend(["", "### Mean price delta by confidence bucket", ""])
    if summary.mean_price_delta_by_confidence_bucket:
        lines.extend(f"- `{bucket}`: `{value:.6f}`" for bucket, value in sorted(summary.mean_price_delta_by_confidence_bucket.items()))
    else:
        lines.append("- none")
    lines.extend(["", "### Mean volume response by window", ""])
    if summary.volume_response_by_window:
        lines.extend(f"- `{window_seconds}s`: `{value:.6f}`" for window_seconds, value in sorted(summary.volume_response_by_window.items()))
    else:
        lines.append("- none")
    if gate is not None:
        lines.extend([
            "",
            "## GateDecision",
            "",
            f"- Status: `{gate.status}`",
            f"- Enough data: `{gate.enough_data}`",
            f"- Later paper strategy ready: `{gate.paper_strategy_ready}`",
            f"- Hit rate: `{_fmt_rate(gate.hit_rate)}`",
            f"- Liquidity caveat rate: `{_fmt_rate(gate.liquidity_caveat_rate)}`",
            f"- Weather-only caveat: `{gate.weather_only_caveat}`",
            "",
            "### Gate reasons",
            "",
        ])
        lines.extend(f"- {reason}" for reason in (gate.reasons or ["none"]))
    if errors:
        lines.extend(["", "## Errors", ""])
        lines.extend(f"- {error}" for error in errors)
    return "\n".join(lines) + "\n"
