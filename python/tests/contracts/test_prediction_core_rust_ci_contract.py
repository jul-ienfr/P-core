from __future__ import annotations

from pathlib import Path

import pytest


WORKFLOW_PATH = Path(".github/workflows/prediction-core-rust-runtime.yml")


def test_prediction_core_rust_runtime_workflow_exists_and_runs_xtask_bundle() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    workflow_path = repo_root / WORKFLOW_PATH
    if not workflow_path.exists():
        pytest.skip("prediction-core Rust runtime workflow is not present in the canonical repo")
    workflow = workflow_path.read_text()

    assert "name: prediction-core-rust-runtime" in workflow
    assert "workflow_dispatch:" in workflow
    assert "push:" in workflow
    assert "pull_request:" in workflow
    assert "rust/**" in workflow
    assert "tests/test_prediction_core_rust_" in workflow
    assert "cargo run -p xtask -- pm-storage-runtime" in workflow
    assert "./scripts/check_pm_storage_runtime.sh" not in workflow
    assert "docker" in workflow
    assert "working-directory: rust" in workflow
