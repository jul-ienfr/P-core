from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from prediction_core.app import build_parser


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT / "src")
    env["PYTHONUNBUFFERED"] = "1"
    return env


def test_build_parser_accepts_serve_command() -> None:
    parser = build_parser()
    args = parser.parse_args(["serve", "--host", "127.0.0.1", "--port", "8080"])
    assert args.command == "serve"
    assert args.host == "127.0.0.1"
    assert args.port == 8080


def test_module_help_exits_cleanly() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "prediction_core.app", "--help"],
        capture_output=True,
        text=True,
        env=_env(),
        check=False,
    )
    assert result.returncode == 0
    assert "serve" in result.stdout


def test_serve_help_exits_cleanly() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "prediction_core.app", "serve", "--help"],
        capture_output=True,
        text=True,
        env=_env(),
        check=False,
    )
    assert result.returncode == 0
    assert "--host" in result.stdout
    assert "--port" in result.stdout


def test_serve_command_starts_server_and_answers_healthcheck() -> None:
    process = subprocess.Popen(
        [sys.executable, "-m", "prediction_core.app", "serve", "--host", "127.0.0.1", "--port", "8091"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=_env(),
    )
    try:
        ready_line = process.stdout.readline()
        assert "prediction_core server listening on http://127.0.0.1:8091" in ready_line

        response = subprocess.run(
            ["curl", "-sS", "http://127.0.0.1:8091/health"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert response.returncode == 0
        assert '"status": "ok"' in response.stdout
        assert '"service": "prediction_core_python"' in response.stdout
    finally:
        process.terminate()
        process.wait(timeout=5)
