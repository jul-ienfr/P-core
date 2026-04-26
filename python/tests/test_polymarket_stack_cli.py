import json
import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "prediction-core"


def _pythonpath_env():
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT / "src")
    return env


def test_polymarket_stack_cli_prints_compact_recommendation():
    result = subprocess.run(
        [sys.executable, "-m", "prediction_core.app", "polymarket-stack"],
        capture_output=True,
        text=True,
        check=False,
        env=_pythonpath_env(),
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["fastest_hot_path"]["technology"] == "Polymarket/rs-clob-client"
    assert payload["official_cli"]["repository"] == "Polymarket/polymarket-cli"


def test_repo_wrapper_polymarket_stack_table_lists_hot_path_layers():
    result = subprocess.run(
        [str(SCRIPT), "polymarket-stack", "--table"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    hot_layers = [row["layer"] for row in payload["layers"] if row["hot_path"]]
    assert hot_layers == ["live_market_data", "order_execution"]
