# Panoptique Bookmaker v0

Bookmaker v0 is a minimal, auditable scaffold for comparing Panoptique agents and shadow forecasters. It is **research-only** and **paper-only**. It never routes orders, allocates capital, or creates a live strategy.

## Scope

- Combine agent probabilities with a simple weighted average.
- Preserve per-agent Brier/calibration metadata from existing `prediction_core` metrics.
- Report separated measurement targets:
  - `event_outcome_forecasting`
  - `crowd_movement_forecasting`
  - `executable_edge_after_costs`
- Include anti-correlation metadata as a placeholder only.

## Non-goals

- No live trading.
- No wallet credentials.
- No capital allocation.
- No complex correlation or portfolio math.
- No strategy decisioning.

## Contracts

`BookmakerInput` contains one agent/shadow probability, optional Brier score, optional calibration bucket, and a non-negative report weight.

`BookmakerOutput` contains the weighted-average probability plus explicit safety flags:

- `research_only: true`
- `paper_only: true`
- `capital_allocated: false`
- `trading_action: none`

## Algorithm

1. Drop inputs with non-positive weights.
2. Clamp probabilities to `[0, 1]` using `prediction_core.evaluation.clamp_probability`.
3. Compute the weighted mean of remaining probabilities.
4. Return the result with metadata documenting input metrics and metric target separation.

## Metric separation

Bookmaker v0 does not collapse all performance into one score:

- Event outcomes are scored through existing `prediction_core.evaluation` Brier/log-loss/ECE helpers via `panoptique.agent_scores.bind_shadow_prediction_to_event_outcome`.
- Crowd movement forecasts are scored separately via `panoptique.agent_scores.bind_shadow_prediction_to_crowd_flow`.
- Executable edge after costs is represented only as a measurement record via `panoptique.agent_scores.executable_edge_after_costs_record`.

## Anti-correlation placeholder

The output includes:

```json
{
  "anti_correlation": {
    "status": "placeholder_not_applied",
    "note": "Future versions may discount correlated agents; v0 only reports a weighted average."
  }
}
```

No anti-correlation math is applied in v0.
