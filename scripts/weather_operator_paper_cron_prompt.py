#!/usr/bin/env python3
"""Generate a verifiable paper-only cron prompt for weather_operator_daily.py.

This script only prints an operator prompt. It does not create, install, or
modify any cron entry.
"""

from __future__ import annotations

import argparse
import json


DEFAULT_REPO_ROOT = "/home/jul/P-core"
DEFAULT_ARTIFACT_DIR = "data/polymarket/reports/operator"
SCRIPT_NAME = "weather_operator_daily.py"
INTERVAL_MINUTES = 30
DURATION_HOURS = 48
EXPECTED_RUNS = DURATION_HOURS * 60 // INTERVAL_MINUTES
CRON_EXPRESSION = "*/30 * * * *"


def build_contract(repo_root: str, artifact_dir: str) -> dict:
    """Return the machine-checkable contract embedded in the prompt."""
    return {
        "task": "weather_operator_paper_cron_prompt",
        "script": SCRIPT_NAME,
        "repo_root": repo_root,
        "artifact_dir": artifact_dir,
        "creates_real_cron": False,
        "schedule": {
            "cron_expression": CRON_EXPRESSION,
            "interval_minutes": INTERVAL_MINUTES,
            "duration_hours": DURATION_HOURS,
            "expected_runs": EXPECTED_RUNS,
        },
        "safety": {
            "paper_only": True,
            "live_order_allowed": False,
            "no_real_order_placed": True,
            "priority_on_safety_fail": "P1",
        },
        "stdout_validation": {
            "parse_final_json_stdout": True,
            "required_fields": [
                "paper_only",
                "live_order_allowed",
                "no_real_order_placed",
                "daily_json",
                "daily_md",
            ],
        },
        "artifact_validation": {
            "daily_json_exists": True,
            "daily_md_exists": True,
        },
        "ready_detected_report": {
            "required": True,
            "label": "READY DETECTED",
            "without_live_order": True,
        },
        "delivery": {
            "local_by_default": True,
            "external_routine_reports_via": "CEO",
        },
    }


def build_prompt(repo_root: str = DEFAULT_REPO_ROOT, artifact_dir: str = DEFAULT_ARTIFACT_DIR) -> str:
    contract = build_contract(repo_root, artifact_dir)
    contract_json = json.dumps(contract, indent=2, sort_keys=True)
    return f"""# Weather operator paper-only cron prompt (artifact, no real cron)

You are running a paper-only monitoring routine for `{SCRIPT_NAME}`.
Do not install, edit, or enable a real cron. This is a self-contained
prompt/specification for a cron-like run every {INTERVAL_MINUTES} minutes
during {DURATION_HOURS}h ({EXPECTED_RUNS} expected runs), equivalent to
cron expression `{CRON_EXPRESSION}`.

## Machine-checkable contract
```json
{contract_json}
```

## Execution contract
- Work from repo root: `{repo_root}`.
- Invoke `{SCRIPT_NAME}` in paper mode only for each scheduled tick.
- Enforce `paper_only: true`, `live_order_allowed: false`, and
  `no_real_order_placed: true` for every run.
- Parse final JSON stdout from `{SCRIPT_NAME}` after each run. The final
  JSON stdout must be the authoritative status object.
- Validate stdout fields: `paper_only`, `live_order_allowed`,
  `no_real_order_placed`, `daily_json`, and `daily_md`.
- Validate artifacts: the paths reported as `daily_json` and `daily_md`
  must exist, and should be under `{artifact_dir}` unless the operator
  explicitly reports a safer local path.
- If a safety invariant fails, classify the incident as `P1`, stop the
  routine, and report the exact failing field/value. Safety failures
  include any live-order allowance, any real order, or missing paper-only
  proof.
- Produce a `READY DETECTED` report only when the final JSON stdout and
  artifacts prove a ready signal without any live order. The report must
  explicitly state that no live order was placed.
- deliver local by default: write/keep routine outputs locally unless an
  explicit external escalation is required.
- Routine reports via CEO uniquement si externe; do not bypass CEO for
  external routine reporting.

## Success criteria
A run is successful only if final JSON stdout parses, safety booleans are
exactly `paper_only=true`, `live_order_allowed=false`,
`no_real_order_placed=true`, `daily_json` exists, `daily_md` exists, and
any `READY DETECTED` report contains no live-order action.
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Print a verifiable paper-only cron prompt for weather_operator_daily.py."
    )
    parser.add_argument("--repo-root", default=DEFAULT_REPO_ROOT)
    parser.add_argument("--artifact-dir", default=DEFAULT_ARTIFACT_DIR)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    print(build_prompt(repo_root=args.repo_root, artifact_dir=args.artifact_dir), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
