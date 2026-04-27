from __future__ import annotations

from pathlib import Path


XTASK_MANIFEST_PATH = Path("rust/xtask/Cargo.toml")
XTASK_MAIN_PATH = Path("rust/xtask/src/main.rs")
WORKSPACE_MANIFEST_PATH = Path("rust/Cargo.toml")


def test_prediction_core_rust_workspace_includes_xtask_entrypoint() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    workspace_manifest = (repo_root / WORKSPACE_MANIFEST_PATH).read_text()
    xtask_manifest = (repo_root / XTASK_MANIFEST_PATH).read_text()
    xtask_main = (repo_root / XTASK_MAIN_PATH).read_text()

    assert '"xtask"' in workspace_manifest
    assert 'name = "xtask"' in xtask_manifest
    assert 'cargo run -p xtask -- pm-storage-runtime' in xtask_main
    assert 'check_pm_storage_runtime.sh' in xtask_main
    assert 'run_pm_storage_runtime_test.sh' in xtask_main
    assert 'pm-storage-runtime' in xtask_main
    assert 'std::process::Command' in xtask_main
