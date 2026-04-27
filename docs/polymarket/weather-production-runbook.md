# Polymarket Weather Production Runbook

This runbook is for the paper-first Polymarket weather operator pipeline. Live execution is guarded and must remain disabled unless every readiness gate passes and explicit live mode is enabled.

## Daily Operating Loop

1. **Refresh profitable weather accounts**
   - Import or refresh classified profitable weather-account activity.
   - Rebuild strategy/archetype evidence and confirm the sample is current enough for operator use.

2. **Build account consensus**
   - Run the consensus tracker against current profitable-account trades/positions.
   - Treat consensus as a signal only; prefer true multi-account consensus over single-account-heavy clusters.

3. **Source check first**
   - Build or refresh the city/date event surface.
   - Confirm exact official source/station and settlement wording before ranking any candidate.
   - Any `source_missing`, `source_fetch_error`, or `source_conflict` row is do-not-trade.

4. **Surface score and inconsistency review**
   - Review exact-bin mass, neighbor-bin anomalies, threshold monotonicity, and YES/NO side inversions.
   - Keep crude-proxy or long-tail edges micro-paper only unless source and replay evidence are strong.

5. **Orderbook simulate**
   - Simulate strict-limit fills from fresh CLOB books for expected spend sizes.
   - Do not market buy. If strict limit is exceeded, depth is insufficient, or fill destroys edge, leave the row watch-only.

6. **Place paper limits**
   - Use only the strict-limit paper ledger.
   - Record source/station status, market/token, side, limit, simulated fill, consensus context, and model/inconsistency reason.
   - Respect portfolio caps by city/date, station/source, archetype, side, correlated surface, and total paper exposure.

7. **Monitor**
   - Refresh source and orderbook status for paper orders.
   - Follow ledger actions: `HOLD`, `HOLD_CAPPED`, `PENDING_LIMIT`, `TAKE_PROFIT_REVIEW_PAPER`, `RED_FLAG_RECHECK_SOURCE`, `NO_ADD_PRICE_MOVED`.
   - Recheck any source red flag before adding or maintaining exposure.

8. **Postmortem**
   - After settlement, compare official outcome, paper fill quality, source latency, consensus accuracy, and portfolio-cap impact.
   - Feed lessons back into thresholds, replay/backtest assumptions, and candidate sizing.

## Production Operator Report

Use the production report command to chain the implemented layers into a compact JSON/Markdown handoff:

```bash
cd /home/jul/P-core/python
PYTHONPATH=src python3 -m weather_pm.cli production-weather-report \
  --surface-json tests/fixtures/polymarket_weather_city_date_surface.json \
  --paper-ledger-json data/polymarket/weather_paper_ledger_latest.json \
  --backtest-json data/polymarket/weather_archetype_backtest_latest.json \
  --consensus-json data/polymarket/weather_consensus_tracker_latest.json \
  --output-dir ../data/polymarket \
  --observed-value 73 \
  --hours-to-resolution 2
```

Artifacts:

- `data/polymarket/weather_production_operator_report_latest.json`
- `data/polymarket/weather_production_operator_report_latest.md`

## Guarded Live Readiness

Live execution is refused unless all checks pass:

- source confirmed;
- orderbook/fill simulation fresh;
- paper ledger healthy;
- historical replay/backtest available;
- risk caps satisfied;
- explicit live mode enabled.

Even when the command is invoked with `--live-mode-enabled`, the report must still refuse live execution if any other gate fails. The default operating mode is paper-only.
