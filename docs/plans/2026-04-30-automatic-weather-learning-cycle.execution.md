# Automatic Weather Learning Cycle — Phase Plan Executor Board

**Source Plan:** `docs/plans/2026-04-30-automatic-weather-learning-cycle.md`
**Repo Path:** `/home/jul/P-core/.parallel/weather-learning/integration`
**Concurrency:** 3
**Parallel Mode:** safe
**Validation Mode:** standard
**Max Retries Per Task:** 1
**Resume:** true
**Commit Mode:** per-phase
**Worker Backend:** delegate-task

> Native `agent.phase_plan_executor.parser` was not available in `/home/jul/.hermes/hermes-agent` during preflight (`ModuleNotFoundError`). Use this file as a phase-plan-executor-compatible execution board. If native `/plan` execution remains unavailable or stalls, execute phase-by-phase with fresh `delegate_task` workers as specified by the `phase-plan-executor` skill.
>
> Hard guardrail: strict paper-only. Every produced runtime artifact must preserve `paper_only=true`, `live_order_allowed=false`, `no_real_order_placed=true`, and recursive safety scan must find no nested `live_order_allowed=true`.

## Phase 1 — Cycle orchestrator minimal
**Progress:** 100%

- [x] Task 1: Create `python/src/weather_pm/learning_cycle.py` and `python/tests/test_weather_learning_cycle.py`; add `build_learning_cycle_contract(...)` using strict RED/GREEN TDD.
- [x] Task 2: Add recursive safety validation `validate_learning_cycle_safety(...)` rejecting nested `live_order_allowed=true`, with targeted RED/GREEN tests.
- [x] Task 3: Add CLI subcommand `learning-cycle` in `python/src/weather_pm/cli.py` for dry-run/no-network contract writing, with subprocess test.
- [x] Run phase validation: `PYTHONPATH=python/src python3 -m pytest -q python/tests/test_weather_learning_cycle.py` plus `python3 -m py_compile python/src/weather_pm/learning_cycle.py python/src/weather_pm/cli.py`.

### Phase Status
- [x] Phase 1 complete

## Phase 2 — Experiment ledger
**Progress:** 100%

- [x] Task 4: Add append-only `learning_experiments.jsonl` writer with stable canonical experiment hash and paper-only fields, using RED/GREEN tests.
- [x] Task 5: Add ledger deduplication by experiment hash, with `force=False` default and RED/GREEN tests.
- [x] Run phase validation: `PYTHONPATH=python/src python3 -m pytest -q python/tests/test_weather_learning_cycle.py`.

### Phase Status
- [x] Phase 2 complete

## Phase 3 — Information scoring and backfill planner
**Progress:** 100%

- [x] Task 6: Add `score_high_information_case(...)` prioritizing threshold proximity, source gaps, profile disagreement, liquidity, unresolved uncertainty, with RED/GREEN tests.
- [x] Task 7: Add `build_learning_backfill_plan(...)` from learning report + ledger, deduplicating and sorting high-information cases, with RED/GREEN tests.
- [x] Run phase validation: `PYTHONPATH=python/src python3 -m pytest -q python/tests/test_weather_learning_cycle.py`.

### Phase Status
- [x] Phase 3 complete

## Phase 4 — Policy engine
**Progress:** 100%

- [x] Task 8: Add `build_learning_policy_actions(...)` converting report `profile_actions` into safe paper-only policy actions, with RED/GREEN tests.
- [x] Task 9: Add anti-false-edge promotion thresholds (`min_resolved_for_promotion`, ROI, winrate) and block thin-sample promotions, with RED/GREEN tests.
- [x] Run phase validation: `PYTHONPATH=python/src python3 -m pytest -q python/tests/test_weather_learning_cycle.py`.

### Phase Status
- [x] Phase 4 complete

## Phase 5 — Full learning-cycle assembly
**Progress:** 100%

- [x] Task 10: Add pure `assemble_learning_cycle_result(...)` combining contract, report, policy, backfill plan, ledger writes, and safety validation, with RED/GREEN tests.
- [x] Task 11: Extend CLI `learning-cycle` to read `--learning-report-json` and write full artifacts: contract, result, policy, backfill plan, summary markdown, ledger, with subprocess test.
- [x] Run phase validation: `PYTHONPATH=python/src python3 -m pytest -q python/tests/test_weather_learning_cycle.py` plus CLI smoke using existing CPR learning report and `--no-network`.

### Phase Status
- [x] Phase 5 complete

## Phase 6 — Daily operator integration
**Progress:** 100%

- [x] Task 12: Add `latest_safe_learning_cycle(...)` to `scripts/weather_operator_daily.py`, ignoring unsafe nested live payloads, with RED/GREEN test in `python/tests/test_weather_operator_daily.py`.
- [x] Task 13: Add `render_learning_cycle_markdown(...)` and integrate compact learning-cycle summary into daily Markdown, with RED/GREEN tests.
- [x] Run phase validation: `PYTHONPATH=python/src python3 -m pytest -q python/tests/test_weather_operator_daily.py python/tests/test_weather_learning_cycle.py`.

### Phase Status
- [x] Phase 6 complete

## Phase 7 — Backfill execution automation, bounded
**Progress:** 100%

- [x] Task 14: Add `select_learning_accounts(...)` prioritizing profiles needing resolution/backfill from followlist + learning report, with RED/GREEN tests.
- [x] Task 15: Add `build_bounded_backfill_commands(...)` emitting plan-only bounded commands for existing weather CLI surfaces, with RED/GREEN tests; do not execute heavy network backfill in tests.
- [x] Run phase validation: `PYTHONPATH=python/src python3 -m pytest -q python/tests/test_weather_learning_cycle.py`.

### Phase Status
- [x] Phase 7 complete

## Phase 8 — Cron productionization
**Progress:** 100% for repo/doc prep; live cron prompt update and listing verification remain controller verification pending.

- [x] Task 16: Prepared the intended cron job `312c3b855271` prompt documentation to run lightweight `learning-cycle --dry-run --no-network` before `scripts/weather_operator_daily.py`, with local-only delivery and recursive paper-only safety checks. Actual Hermes cron prompt update must be performed by the controller.
- [x] Add or update ops documentation `docs/ops/weather_learning_cycle_cron.md` describing cron schedule, safety invariants, artifacts, and recovery.
- [x] Verification note: repo docs now define the required post-update cron listing checks for job `312c3b855271`, `deliver=local`, workdir `/home/jul/P-core/.parallel/weather-learning/integration`, and prompt `learning-cycle` safety checks; live cron listing verification is controller verification pending because this subagent did not call the cronjob tool.

### Phase Status
- [x] Phase 8 repo/doc prep complete; controller cron update/verification pending

## Phase 9 — Heavy learning backfill plan
**Progress:** 100%

- [x] Task 17: Draft heavy backfill cron prompt/documentation for once/twice daily bounded learning runs; do not enable heavy cron until light cycle is validated.
- [x] Add heavy backfill safety checklist to `docs/ops/weather_learning_cycle_cron.md`: `max_accounts`, `trades_per_account`, `lookback_days`, no live order, recursive safety scan, insufficient-signal behavior.
- [x] Run documentation/smoke validation and ensure no live execution path is introduced.

### Phase Status
- [x] Phase 9 complete

## Final Verification
**Progress:** 100%

- [x] Run targeted suites: `PYTHONPATH=python/src python3 -m pytest -q python/tests/test_weather_learning_cycle.py python/tests/test_weather_shadow_paper_runner.py python/tests/test_weather_operator_daily.py`.
- [x] Run py_compile: `PYTHONPATH=python/src python3 -m py_compile python/src/weather_pm/learning_cycle.py python/src/weather_pm/cli.py python/src/weather_pm/shadow_paper_runner.py scripts/weather_operator_daily.py`.
- [x] Run CLI smoke: `weather_pm.cli learning-cycle --learning-report-json /tmp/weather_learning_final_safe_report.json --dry-run --no-network` into `data/polymarket/learning-cycles/final-smoke-*`.
- [x] Run daily smoke: `PYTHONPATH=python/src python3 scripts/weather_operator_daily.py --skip-cron-monitor`.
- [x] Verify latest artifacts recursively contain no nested `live_order_allowed=true` and preserve `paper_only=true`, `live_order_allowed=false`, `no_real_order_placed=true`.
- [x] Run `git diff --check` and path-scoped `git status --short`.
- [ ] Commit/push scoped weather changes to `origin/main` only after all validation passes.

### Phase Status
- [x] Final Verification complete

## Global Status
**Overall Progress:** 100%
- [x] Plan complete
