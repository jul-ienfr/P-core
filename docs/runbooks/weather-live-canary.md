# Weather Polymarket LIVE_CANARY runbook

Status: pre-cabled, disabled by default. This runbook does **not** authorize live orders by itself.

## Safety invariant

Default state must stay:

- `WEATHER_LIVE_CANARY_MODE` unset or `shadow`
- no Polymarket live secrets required
- no direct order API call

In that state every preflight/execution artifact must report:

- `paper_only=true`
- `live_order_allowed=false` or no submission
- `orders_allowed=false` for executor output
- `no_real_order_placed=true`
- execution rows are `skipped_shadow_mode`, `skipped_not_armed`, or `skipped_client_not_configured`

## One-switch live model

Everything is wired behind one operational config element:

```bash
WEATHER_LIVE_CANARY_MODE=shadow  # default/noop
WEATHER_LIVE_CANARY_MODE=live    # only switch that can arm + submit, after preflight and client secrets
```

The old multi-switch arming variables (`WEATHER_LIVE_CANARY_ENABLED`, `WEATHER_LIVE_CANARY_KILL_SWITCH`, `WEATHER_LIVE_CANARY_DRY_RUN`) are intentionally no longer required for normal operation. `config_from_env()` derives them from `WEATHER_LIVE_CANARY_MODE`:

- `shadow` => disabled + kill switch + dry-run
- `live` => enabled + no kill switch + non-dry-run

Market/risk guardrails remain separate and must still be set conservatively:

- `WEATHER_LIVE_CANARY_ALLOWLIST=<market-id>[,<market-id>]`
- `WEATHER_LIVE_CANARY_MAX_ORDER_USDC=1`
- `WEATHER_LIVE_CANARY_MAX_DAILY_USDC=1`
- `WEATHER_LIVE_CANARY_MIN_QUALITY=85`
- `WEATHER_LIVE_CANARY_MAX_SPREAD=0.04`
- `WEATHER_LIVE_CANARY_MIN_DEPTH_USDC=25`
- `WEATHER_LIVE_CANARY_CONFIRM=I_ACCEPT_MICRO_LIVE_WEATHER_RISK` is still required by preflight before any non-dry-run order can be armed.

Live submission additionally requires secrets in env/stdin-backed shell only, never in repo/logs:

- `POLYMARKET_PRIVATE_KEY`
- `POLYMARKET_FUNDER` or `POLYMARKET_PROXY_WALLET`
- optional `POLYMARKET_HOST=https://clob.polymarket.com`
- optional `POLYMARKET_CHAIN_ID=137`
- optional `POLYMARKET_SIGNATURE_TYPE=1`

## Shadow preflight + noop execution

```bash
cd /home/jul/P-core
PYTHONPATH=python/src python3 -m weather_pm.cli live-canary-preflight \
  --operator-json data/polymarket/shadow-cron/weather_account_bridge_<STAMP>.json \
  --output-json data/polymarket/shadow-cron/weather_live_canary_preflight_<STAMP>.json \
  --run-id <STAMP>

PYTHONPATH=python/src python3 -m weather_pm.cli live-canary-execute \
  --preflight-json data/polymarket/shadow-cron/weather_live_canary_preflight_<STAMP>.json \
  --output-json data/polymarket/shadow-cron/weather_live_canary_execute_<STAMP>.json
```

With `WEATHER_LIVE_CANARY_MODE` unset, the executor is a noop even if the input preflight contains an armed payload from a fixture/test.

The shadow wrapper emits both artifacts automatically:

```bash
PYTHONPATH=python/src python3 scripts/weather_shadow_cron_wrapper.py \
  --repo /home/jul/P-core \
  --source live \
  --operator-limit 10 \
  --max-shadow-actions 10
```

## Strict live-canary arming conditions

A row only arms a micro live payload when **all** are true:

1. `WEATHER_LIVE_CANARY_MODE=live`
2. `WEATHER_LIVE_CANARY_CONFIRM=I_ACCEPT_MICRO_LIVE_WEATHER_RISK`
3. market id is in `WEATHER_LIVE_CANARY_ALLOWLIST`
4. notional is `<= WEATHER_LIVE_CANARY_MAX_ORDER_USDC` and `<= WEATHER_LIVE_CANARY_MAX_DAILY_USDC` (defaults: `1.0`)
5. live quality is `>= WEATHER_LIVE_CANARY_MIN_QUALITY` (default: `85`)
6. spread is `<= WEATHER_LIVE_CANARY_MAX_SPREAD` (default: `0.04`)
7. depth is `>= WEATHER_LIVE_CANARY_MIN_DEPTH_USDC` (default: `25`)
8. row is already paper-vetted (`PAPER_MICRO`, `PAPER_STRICT`, or `MICRO_LIVE_CANDIDATE`)
9. `normal_size_gate.live_ready=true`
10. no execution blocker and no portfolio risk block

If any guard fails, the row remains `DRY_RUN_ONLY` with `live_execution_payload=null`.

## Example authorized micro-live sequence

Do not run this until explicitly authorized by Julien for a named market and budget.

```bash
cd /home/jul/P-core
export WEATHER_LIVE_CANARY_MODE=live
export WEATHER_LIVE_CANARY_CONFIRM=I_ACCEPT_MICRO_LIVE_WEATHER_RISK
export WEATHER_LIVE_CANARY_ALLOWLIST=<market-id>
export WEATHER_LIVE_CANARY_MAX_ORDER_USDC=1
export WEATHER_LIVE_CANARY_MAX_DAILY_USDC=1
# Set Polymarket secrets via masked/stdin shell, not command history/logs.

PYTHONPATH=python/src python3 -m weather_pm.cli live-canary-preflight \
  --operator-json <operator-or-account-bridge.json> \
  --output-json data/polymarket/shadow-cron/weather_live_canary_preflight_<STAMP>.json \
  --run-id <STAMP>

PYTHONPATH=python/src python3 -m weather_pm.cli live-canary-execute \
  --preflight-json data/polymarket/shadow-cron/weather_live_canary_preflight_<STAMP>.json \
  --output-json data/polymarket/shadow-cron/weather_live_canary_execute_<STAMP>.json
```

## Verification checklist

```bash
cd /home/jul/P-core
PYTHONPATH=python/src python3 -m pytest -q \
  python/tests/test_weather_live_canary_gate.py \
  python/tests/test_weather_live_canary_executor.py \
  python/tests/test_weather_shadow_cron_wrapper.py \
  python/tests/test_weather_paper_autopilot_bridge.py \
  python/tests/test_weather_operator_summary_live_quality.py

python3 -m py_compile \
  python/src/weather_pm/live_canary_gate.py \
  python/src/weather_pm/live_canary_executor.py \
  python/src/weather_pm/polymarket_live_order_client.py \
  python/src/weather_pm/cli.py \
  scripts/weather_shadow_cron_wrapper.py

# Safety scan: should print 0 outside deliberately armed fixture/test contexts.
python3 - <<'PY'
import json, pathlib
bad=[]
for p in pathlib.Path('data/polymarket/shadow-cron').glob('*.json'):
    try: obj=json.loads(p.read_text())
    except Exception: continue
    if '"live_order_submitted": true' in json.dumps(obj):
        bad.append(str(p))
print(len(bad))
for p in bad[:20]: print(p)
PY
```
