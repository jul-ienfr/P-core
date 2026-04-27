from __future__ import annotations

from pathlib import Path


REQUIRED_PATHS = [
    "README.md",
    "contracts/README.md",
    "python/README.md",
    "python/src/prediction_core/__init__.py",
    "python/tests/__init__.py",
    "rust/README.md",
    "rust/Cargo.toml",
    "rust/crates/live_engine/Cargo.toml",
    "rust/crates/live_engine/src/lib.rs",
    "rust/crates/pm_types/Cargo.toml",
    "rust/crates/pm_types/src/lib.rs",
    "rust/crates/pm_book/Cargo.toml",
    "rust/crates/pm_book/src/lib.rs",
    "rust/crates/pm_signal/Cargo.toml",
    "rust/crates/pm_signal/src/lib.rs",
    "rust/crates/pm_storage/Cargo.toml",
    "rust/crates/pm_storage/src/lib.rs",
    "rust/crates/pm_risk/Cargo.toml",
    "rust/crates/pm_risk/src/lib.rs",
    "rust/crates/pm_executor/Cargo.toml",
    "rust/crates/pm_executor/src/lib.rs",
    "rust/crates/pm_ledger/Cargo.toml",
    "rust/crates/pm_ledger/src/lib.rs",
]


def test_prediction_core_scaffold_exists() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    missing = [relative for relative in REQUIRED_PATHS if not (repo_root / relative).exists()]
    assert missing == []
