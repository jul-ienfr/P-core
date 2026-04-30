import json
import re
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "weather_operator_paper_cron_prompt.py"


def run_script(*args: str) -> str:
    return subprocess.check_output([sys.executable, str(SCRIPT), *args], text=True)


def extract_json_block(prompt: str) -> dict:
    match = re.search(r"```json\n(.*?)\n```", prompt, re.S)
    assert match, prompt
    return json.loads(match.group(1))


def test_prompt_contains_required_cron_paper_only_contract():
    prompt = run_script()

    assert "weather_operator_daily.py" in prompt
    assert "*/30 * * * *" in prompt
    assert "48h" in prompt
    assert "96" in prompt
    assert "paper_only" in prompt
    assert "live_order_allowed" in prompt
    assert "no_real_order_placed" in prompt
    assert "daily_json" in prompt
    assert "daily_md" in prompt
    assert "READY DETECTED" in prompt
    assert "P1" in prompt
    assert "deliver local by default" in prompt
    assert "CEO" in prompt
    assert "final JSON stdout" in prompt

    contract = extract_json_block(prompt)
    assert contract["script"] == "weather_operator_daily.py"
    assert contract["schedule"]["interval_minutes"] == 30
    assert contract["schedule"]["duration_hours"] == 48
    assert contract["schedule"]["expected_runs"] == 96
    assert contract["safety"]["paper_only"] is True
    assert contract["safety"]["live_order_allowed"] is False
    assert contract["safety"]["no_real_order_placed"] is True
    assert contract["delivery"]["local_by_default"] is True
    assert contract["delivery"]["external_routine_reports_via"] == "CEO"


def test_prompt_accepts_custom_paths_without_creating_cron():
    prompt = run_script("--repo-root", "/tmp/repo", "--artifact-dir", "artifacts/weather")
    contract = extract_json_block(prompt)

    assert contract["repo_root"] == "/tmp/repo"
    assert contract["artifact_dir"] == "artifacts/weather"
    assert contract["creates_real_cron"] is False
    assert "Do not install, edit, or enable a real cron" in prompt
