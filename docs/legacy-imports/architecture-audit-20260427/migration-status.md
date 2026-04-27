# P-core cleanup / migration status

## Current decision

`/home/jul/P-core` is the canonical project folder for Polymarket / PredictionCore.

## Completed in this cleanup pass

- Created this architecture documentation area under `docs/architecture/`.
- Moved Polymarket/weather docs from root `docs/` into `docs/polymarket/`.
- Moved reverse-engineering JSON docs into `docs/polymarket/reverse-engineering/`.
- Moved generated strategy profile matrix into `docs/polymarket/generated/`.
- Created structured `data/polymarket/` subfolders.
- Moved currently present flat Polymarket generated artifacts into:
  - `data/polymarket/latest/`
  - `data/polymarket/account-analysis/`
  - `data/polymarket/reports/operator/`
  - `data/polymarket/ledgers/`
  - `data/polymarket/scans/`
  - `data/polymarket/archive/`

## Not done automatically / requires caution

### Duplicate roots

These roots were identified but not deleted:

- `/home/jul/prediction_core`
- `/home/jul/swarm/subprojects/prediction`
- `/home/jul/swarm/prediction_core`

Reason: they may contain unmerged work, dashboard/UI donor code, or historical data. They should be archived only after a dedicated comparison/audit.

### Worktrees

Current P-core worktrees were identified but not removed:

- `.claude/worktrees/profile-integration`
- `.claude/worktrees/profile-ledger`
- `.claude/worktrees/profile-models`
- `.claude/worktrees/profile-runner`

Reason: `git worktree remove` is safe only after verifying whether each branch is merged or disposable.

### Dirty Git state

The main checkout had many pre-existing deletions and modifications before this cleanup. The cleanup avoided destructive resets. Review `git status --short` before committing.

## Next recommended cleanup pass

1. Audit duplicate roots against `/home/jul/P-core`:
   - compare `git remote`, latest commits, and untracked files;
   - extract only missing docs/data/code worth keeping;
   - move obsolete roots to an archive folder or remove them after confirmation.
2. Audit `.claude/worktrees/*`:
   - check branch, diff, and merge status;
   - remove worktrees that are merged/disposable;
   - keep active worktrees outside the main project tree if ongoing.
3. Update code writers that still output directly to flat `data/polymarket/` paths so new artifacts land in the appropriate subfolder.
4. Add/adjust tests for any path constants if scripts depend on old locations.
