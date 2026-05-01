# Weather Polymarket LIVE_CANARY runbook

Status: prepared, disabled by default. This runbook does **not** authorize live orders by itself.

## Safety invariant

Default state must stay:

- `WEATHER_LIVE_CANARY_ENABLED` unset/false
- `WEATHER_LIVE_CANARY_KILL_SWITCH=true` or unset
- `WEATHER_LIVE_CANARY_DRY_RUN=true` or unset
- no `WEATHER_LIVE_CANARY_CONFIRM`

In that state every preflight artifact must report:

- `paper_only=true`
- `live_order_allowed=false`
- `orders_allowed=false`
- `eligible_count=0`
- `no_real_order_placed=true`

## Dry-run preflight

```bash
cd /home/jul/P-core
PYTHONPATH=python/src python3 -m weather_pm.cli live-canary-preflight \
  --operator-json data/polymarket/shadow-cron/weather_account_bridge_<STAMP>.json \
  --output-json data/polymarket/shadow-cron/weather_live_canary_preflight_<STAMP>.json \
  --run-id <STAMP>
```

The shadow wrapper also emits this artifact automatically:

```bash
PYTHONPATH=python/src python3 scripts/weather_shadow_cron_wrapper.py \
  --repo /home/jul/P-core \
  --source live \
  --operator-limit 10 \
  --max-shadow-actions 10
```

## Strict live-canary arming conditions

A row only arms a micro live payload when **all** are true:

1. `WEATHER_LIVE_CANARY_ENABLED=true`
2. `WEATHER_LIVE_CANARY_KILL_SWITCH=false`
3. `WEATHER_LIVE_CANARY_DRY_RUN=false`
4. `WEATHER_LIVE_CANARY_CONFIRM=I_ACCEPT_MICRO_LIVE_WEATHER_RISK`
5. market id is in `WEATHER_LIVE_CANARY_ALLOWLIST`
6. notional is `<= WEATHER_LIVE_CANARY_MAX_ORDER_USDC` and `<= WEATHER_LIVE_CANARY_MAX_DAILY_USDC` (defaults: `1.0`)
7. live quality is `>= WEATHER_LIVE_CANARY_MIN_QUALITY` (default: `85`)
8. spread is `<= WEATHER_LIVE_CANARY_MAX_SPREAD` (default: `0.04`)
9. depth is `>= WEATHER_LIVE_CANARY_MIN_DEPTH_USDC` (default: `25`)
10. row is already paper-vetted (`PAPER_MICRO`, `PAPER_STRICT`, or `MICRO_LIVE_CANDIDATE`)
11. `normal_size_gate.live_ready=true`
12. no execution blocker and no portfolio risk block

If any guard fails, the row remains `DRY_RUN_ONLY` with `live_execution_payload=null`.

## Example armed preflight command

Do not run this until explicitly authorized by Julien for a named market and budget.

```bash
cd /home/jul/P-core
WEATHER_LIVE_CANARY_ENABLED=true \
WEATHER_LIVE_CANARY_KILL_SWITCH=false \
WEATHER_LIVE_CANARY_DRY_RUN=false \
WEATHER_LIVE_CANARY_CONFIRM=I_ACCEPT_MICRO_LIVE_WEATHER_RISK \
WEATHER_LIVE_CANARY_ALLOWLIST=<market-id> \
WEATHER_LIVE_CANARY_MAX_ORDER_USDC=1 \
WEATHER_LIVE_CANARY_MAX_DAILY_USDC=1 \
PYTHONPATH=python/src python3 -m weather_pm.cli live-canary-preflight \
  --operator-json <operator-or-account-bridge.json> \
  --output-json data/polymarket/shadow-cron/weather_live_canary_preflight_<STAMP>.json \
  --run-id <STAMP>
```

## Important limitation

Current implementation only builds a guarded `live_execution_payload`; it does not call any Polymarket order submission API. That is deliberate. The next step, if authorized, is to wire an execution adapter that consumes only preflight rows with `canary_action=MICRO_LIVE_LIMIT_ORDER_ALLOWED` and matching idempotency keys.

## Verification checklist

```bash
cd /home/jul/P-core
PYTHONPATH=python/src python3 -m pytest -q \
  python/tests/test_weather_live_canary_gate.py \
  python/tests/test_weather_shadow_cron_wrapper.py \
  python/tests/test_weather_paper_autopilot_bridge.py \
  python/tests/test_weather_operator_summary_live_quality.py

python3 -m py_compile \
  python/src/weather_pm/live_canary_gate.py \
  python/src/weather_pm/cli.py \
  scripts/weather_shadow_cron_wrapper.py

# Safety scan: should print 0 outside deliberately armed fixture/test contexts.
python3 - <<'PY'
import json, pathlib
bad=[]
for p in pathlib.Path('data/polymarket/shadow-cron').glob('*.json'):
    try: obj=json.loads(p.read_text())
    except Exception: continue
    if '"live_order_allowed": true' in json.dumps(obj):
        bad.append(str(p))
print(len(bad))
for p in bad[:20]: print(p)
PY
```
