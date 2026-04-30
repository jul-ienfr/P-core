# Weather learning-cycle cron productionization

This document describes the intended production cron wiring for the automatic weather learning cycle in this worktree. It is paper-only operational documentation and prompt preparation; the live Hermes cron job update must be performed by the controller, not by repo-only workers.

## Cron job

- Job id: `312c3b855271`
- Intended schedule: every 30 minutes
- Delivery: `local` only
- Workdir: `/home/jul/P-core/.parallel/weather-learning/integration`
- Enabled toolsets expected by controller listing: `terminal/file`
- Execution order: run a lightweight `weather_pm.cli learning-cycle --dry-run --no-network` first, then run `scripts/weather_operator_daily.py --skip-cron-monitor`.

Controller state before this repo/doc prep already showed job `312c3b855271` exists, is enabled, uses `deliver=local`, workdir `/home/jul/P-core/.parallel/weather-learning/integration`, runs every 30 minutes, and has `terminal/file` toolsets. The actual prompt update and live cron verification remain **controller verification pending** because subagents must not call the Hermes cronjob tool.

## Exact intended cron prompt skeleton

```bash
cd /home/jul/P-core/.parallel/weather-learning/integration

RUN_ID="learn-$(date -u +%Y%m%dT%H%M%SZ)"
OUT="data/polymarket/learning-cycles/$RUN_ID"

LATEST_REPORT="$({ find data/polymarket -type f \
  -name '*shadow_profile_learning_report*.json' \
  -print 2>/dev/null || true; } | sort | tail -n 1)"

if [ -z "$LATEST_REPORT" ]; then
  echo "No shadow_profile_learning_report JSON found; aborting lightweight learning cycle before daily operator."
  exit 1
fi

PYTHONPATH=python/src python3 -m weather_pm.cli learning-cycle \
  --run-id "$RUN_ID" \
  --learning-report-json "$LATEST_REPORT" \
  --output-dir "$OUT" \
  --max-accounts 5 \
  --trades-per-account 50 \
  --lookback-days 30 \
  --dry-run \
  --no-network

PYTHONPATH=python/src python3 scripts/weather_operator_daily.py --skip-cron-monitor

python3 - "$OUT" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
json_paths = sorted(root.rglob('*.json'))
if not json_paths:
    raise SystemExit(f'No JSON artifacts found under {root}')


def walk(value, path='root'):
    if isinstance(value, dict):
        if value.get('live_order_allowed') is True:
            raise SystemExit(f'Unsafe live_order_allowed=true at {path}')
        for key, child in value.items():
            walk(child, f'{path}.{key}')
    elif isinstance(value, list):
        for index, child in enumerate(value):
            walk(child, f'{path}[{index}]')

for json_path in json_paths:
    payload = json.loads(json_path.read_text(encoding='utf-8'))
    walk(payload, str(json_path))
    if isinstance(payload, dict):
        if payload.get('paper_only') is False:
            raise SystemExit(f'Unsafe paper_only=false in {json_path}')
        if payload.get('no_real_order_placed') is False:
            raise SystemExit(f'Unsafe no_real_order_placed=false in {json_path}')

print(f'Paper-only safety scan passed for {len(json_paths)} JSON artifact(s) under {root}')
PY
```

The prompt intentionally keeps `--dry-run` and `--no-network` mandatory and uses a small bounded cycle (`--max-accounts 5`, `--trades-per-account 50`, `--lookback-days 30`) so the half-hourly cron remains lightweight.

## Safety invariants

Every cron-produced learning-cycle artifact must preserve strict paper-only semantics:

- `paper_only=true`
- `live_order_allowed=false`
- `no_real_order_placed=true`
- no nested `live_order_allowed=true` anywhere in JSON artifacts
- no live order paths, no wallet signing, no real order placement, and no network access in the learning-cycle step
- daily operator runs only after the learning-cycle command succeeds

If any safety scan fails, the cron prompt should exit non-zero and report the failing artifact/path locally.

## Artifacts

Each run writes under:

- `data/polymarket/learning-cycles/$RUN_ID/`

Expected lightweight artifacts include:

- `learning_cycle_contract.json`
- `learning_cycle_result.json`
- `learning_policy_actions.json`
- `learning_backfill_plan.json`
- `learning_cycle_summary.md`
- append-only learning ledger JSONL path reported by the CLI result

The daily operator may additionally update its normal paper/operator artifacts under `data/polymarket/operator-daily/`, `data/polymarket/watchlists/`, and `data/polymarket/latest/` depending on existing script behavior.

## Heavy learning backfill plan

Status: **NOT enabled**. This section is documentation and prompt preparation only. Do not create, enable, or update a heavy cron job until the lightweight 30-minute learning cycle has completed several successful safe runs with controller-reviewed artifacts.

The future heavy learning backfill should remain bounded, local-delivered, paper-only, and plan-first. It is intended for once- or twice-daily learning enrichment after the light cycle is proven stable; it is not a live trading or live order placement path.

### Candidate schedules

Use `deliver=local` if a controller later enables a heavy learning cron. Candidate schedules, in increasing intensity:

- Conservative once daily: `15 03 * * *` UTC, after normal daily operator artifacts have settled.
- Optional twice daily: `15 03,15 * * *` UTC, only if the once-daily run has remained safe and bounded.

### Draft prompt skeleton for future controller review

The following skeleton is intentionally dry-run/no-network and plan-only. It must not be installed as an enabled cron until the gating criteria above are satisfied.

```bash
cd /home/jul/P-core/.parallel/weather-learning/integration

RUN_ID="heavy-learn-$(date -u +%Y%m%dT%H%M%SZ)"
OUT="data/polymarket/learning-cycles/$RUN_ID"
LATEST_REPORT="$({ find data/polymarket -type f \
  -name '*shadow_profile_learning_report*.json' \
  -print 2>/dev/null || true; } | sort | tail -n 1)"

if [ -z "$LATEST_REPORT" ]; then
  echo "insufficient_signal=true reason=no_shadow_profile_learning_report"
  exit 0
fi

# Conservative defaults. Do not raise bounds until repeated safe runs exist.
MAX_ACCOUNTS="20"
TRADES_PER_ACCOUNT="100"
LOOKBACK_DAYS="30"

PYTHONPATH=python/src python3 -m weather_pm.cli learning-cycle \
  --run-id "$RUN_ID" \
  --learning-report-json "$LATEST_REPORT" \
  --output-dir "$OUT" \
  --max-accounts "$MAX_ACCOUNTS" \
  --trades-per-account "$TRADES_PER_ACCOUNT" \
  --lookback-days "$LOOKBACK_DAYS" \
  --dry-run \
  --no-network

python3 - "$OUT" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
json_paths = sorted(root.rglob('*.json'))
if not json_paths:
    print('insufficient_signal=true reason=no_json_artifacts')
    raise SystemExit(0)

saw_high_information_case = False

def walk(value, path='root'):
    global saw_high_information_case
    if isinstance(value, dict):
        if value.get('live_order_allowed') is True:
            raise SystemExit(f'Unsafe live_order_allowed=true at {path}')
        if value.get('paper_only') is False:
            raise SystemExit(f'Unsafe paper_only=false at {path}')
        if value.get('no_real_order_placed') is False:
            raise SystemExit(f'Unsafe no_real_order_placed=false at {path}')
        if value.get('high_information') is True or value.get('information_score', 0) > 0:
            saw_high_information_case = True
        for key, child in value.items():
            walk(child, f'{path}.{key}')
    elif isinstance(value, list):
        for index, child in enumerate(value):
            walk(child, f'{path}[{index}]')

for json_path in json_paths:
    payload = json.loads(json_path.read_text(encoding='utf-8'))
    walk(payload, str(json_path))

if not saw_high_information_case:
    print('insufficient_signal=true reason=no_safe_high_information_cases')
    raise SystemExit(0)

print(f'paper_only=true live_order_allowed=false no_real_order_placed=true recursive safety scan passed for {len(json_paths)} JSON artifact(s) under {root}')
PY
```

### Heavy backfill safety checklist

Before any future heavy cron enablement, verify all of the following locally and in controller review:

- Bounds are explicit and conservative: recommended defaults `max_accounts=20`, `trades_per_account=100`, `lookback_days=30`.
- Allowed future upper examples are still bounded: `max_accounts` 20-50, `trades_per_account` 100-250, `lookback_days` 30-90; do not use higher values without a separate plan.
- The first controller run is plan-only / dry-run, keeps `--dry-run --no-network`, and uses `deliver=local`.
- Runtime artifacts preserve `paper_only=true`, `live_order_allowed=false`, and `no_real_order_placed=true`.
- Recursive safety scan fails non-zero on any nested `live_order_allowed=true`, `paper_only=false`, or `no_real_order_placed=false`.
- No live orders, no wallet signing, no `paper-ledger-place`, no real order submission, and no network-heavy workaround is introduced.
- Insufficient-signal behavior is graceful: if there are not enough safe reports, resolutions, or high-information cases, skip and report `insufficient_signal=true` rather than forcing a backfill.
- Keep the light 30-minute learning cycle unchanged while reviewing heavy backfill output.

### Heavy backfill rollback and recovery

1. If the heavy plan emits `insufficient_signal=true`, leave the heavy job disabled and wait for more safe light-cycle reports/resolutions.
2. If any recursive safety scan fails, quarantine the run directory, leave or return heavy scheduling to disabled, and fix the generator before another attempt.
3. If the run exceeds the configured bounds or takes too long, reduce `max_accounts`, `trades_per_account`, and/or `lookback_days` before retrying plan-only.
4. Controller rollback path for any future heavy job: disable the heavy job entirely; do not modify the validated light job `312c3b855271` unless its own prompt changed.
5. Never use live/network execution as a recovery shortcut.

## Recovery and rollback

1. If the cron run fails because no learning report JSON exists, produce or restore a safe `*shadow_profile_learning_report*.json` artifact before re-enabling the updated prompt.
2. If the learning-cycle CLI fails, inspect the run directory under `data/polymarket/learning-cycles/$RUN_ID/` and do not proceed to live/network backfill as a workaround.
3. If the safety scan reports `live_order_allowed=true`, `paper_only=false`, or `no_real_order_placed=false`, leave the cron failing, quarantine the artifact, and fix the generator before the next run.
4. Controller rollback path: restore job `312c3b855271` to the previously validated daily-operator-only prompt while keeping `deliver=local`, the same workdir, and paper-only flags.
5. Re-run controller verification after any cron prompt edit.

## Controller verification checklist

After the controller updates the Hermes cron prompt, verify the live cron listing shows:

- [ ] job `312c3b855271`
- [ ] enabled, schedule every 30 minutes
- [ ] `deliver=local`
- [ ] workdir `/home/jul/P-core/.parallel/weather-learning/integration`
- [ ] prompt runs `learning-cycle` before `scripts/weather_operator_daily.py`
- [ ] prompt includes `--dry-run --no-network`
- [ ] prompt finds latest `shadow_profile_learning_report` JSON
- [ ] prompt recursively fails/reports if any nested `live_order_allowed=true`

Status: **controller verification pending**. This repository update does not claim the live cron prompt has already been updated.
