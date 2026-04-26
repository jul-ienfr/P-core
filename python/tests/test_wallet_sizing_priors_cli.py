from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _run_weather_pm(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT / "src")
    return subprocess.run(
        [sys.executable, "-m", "weather_pm.cli", *args],
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
        env=env,
        check=False,
    )


def test_wallet_sizing_priors_cli_writes_output_with_source(tmp_path: Path) -> None:
    payload = {
        "accounts": [
            {
                "handle": "Railbird",
                "style": "breadth/grid small-ticket surface trader",
                "recent_trade_avg_usdc": 21.43,
                "recent_trade_max_usdc": 29.98,
            },
            {
                "handle": "0xhana",
                "style": "breadth/grid small-ticket surface trader",
                "recent_trade_avg_usdc": 23.69,
                "recent_trade_max_usdc": 75.0,
            },
            {
                "handle": "ColdMath",
                "style": "sparse/large-ticket conviction trader",
                "recent_trade_avg_usdc": 194.87,
                "recent_trade_max_usdc": 4149.66,
            },
        ]
    }
    input_json = tmp_path / "wallet_behavior.json"
    output_json = tmp_path / "wallet_priors.json"
    input_json.write_text(json.dumps(payload), encoding="utf-8")

    result = _run_weather_pm("wallet-sizing-priors", "--input", str(input_json), "--output", str(output_json))

    assert result.returncode == 0, result.stderr
    stdout_payload = json.loads(result.stdout)
    written = json.loads(output_json.read_text(encoding="utf-8"))
    assert stdout_payload == written
    assert written["source"] == str(input_json)
    assert written["operator_default_style"] == "breadth/grid small-ticket surface trader"
    assert written["copy_warning"] == "wallet priors adjust size/confidence but do not authorize blind copy-trading"
    assert written["styles"]["breadth/grid small-ticket surface trader"]["accounts"] == 2
    assert written["styles"]["breadth/grid small-ticket surface trader"]["median_recent_trade_avg_usdc"] == 22.56
    assert written["styles"]["sparse/large-ticket conviction trader"]["recommended_copy_mode"] == "confidence_only_cap_size"
