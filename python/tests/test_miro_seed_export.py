import json
import subprocess
import sys
from pathlib import Path

from weather_pm.miro_seed import build_miro_seed_markdown


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_build_miro_seed_markdown_includes_facts_but_excludes_market_prices():
    market = {
        "question": "Will the highest temperature in Paris be 25°C or higher on April 27?",
        "resolutionSource": "https://www.wunderground.com/history/daily/fr/paris/LFPG",
        "description": "Resolves using the highest temperature at Paris Charles de Gaulle Airport.",
        "outcomePrices": ["0.61", "0.39"],
        "volume": 12345,
    }
    research_items = [
        {
            "title": "Meteo France forecast",
            "url": "https://example.com/forecast",
            "source": "Meteo France",
            "published": "2026-04-25T12:00:00Z",
            "content": "Forecast calls for a cool air mass and max temperatures around 22°C.",
        }
    ]

    markdown = build_miro_seed_markdown(market, research_items)

    assert "Will the highest temperature in Paris" in markdown
    assert "https://www.wunderground.com/history/daily/fr/paris/LFPG" in markdown
    assert "Forecast calls for a cool air mass" in markdown
    assert "0.61" not in markdown
    assert "0.39" not in markdown
    assert "12345" not in markdown
    assert "outcomePrices" not in markdown
    assert "volume" not in markdown


def test_build_miro_seed_markdown_labels_prediction_question_without_odds():
    market = {"question": "Will X happen?", "yes_price": 0.8, "no_price": 0.2}

    markdown = build_miro_seed_markdown(market, [])

    assert "# Miro seed: Will X happen?" in markdown
    assert "## Prediction task" in markdown
    assert "Market prices are intentionally excluded" in markdown
    assert "0.8" not in markdown
    assert "0.2" not in markdown


def test_cli_miro_seed_export_writes_markdown_without_prices(tmp_path):
    input_path = tmp_path / "market.json"
    output_path = tmp_path / "seed.md"
    input_path.write_text(
        json.dumps(
            {
                "market": {"question": "Will Y happen?", "yes_price": 0.7, "volume": 999},
                "research_items": [{"title": "Official source", "content": "Only factual context."}],
            }
        )
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "weather_pm.cli",
            "miro-seed-export",
            "--input-json",
            str(input_path),
            "--output-md",
            str(output_path),
        ],
        cwd=PROJECT_ROOT,
        env={"PYTHONPATH": str(PROJECT_ROOT / "src")},
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    markdown = output_path.read_text()
    assert "Will Y happen?" in markdown
    assert "Only factual context." in markdown
    assert "0.7" not in markdown
    assert "999" not in markdown
    payload = json.loads(result.stdout)
    assert payload["output_md"] == str(output_path)
    assert payload["paper_only"] is True


def test_cli_miro_seed_export_can_fetch_fixture_market_by_id(tmp_path):
    output_path = tmp_path / "seed.md"
    manifest_path = tmp_path / "manifest.json"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "weather_pm.cli",
            "miro-seed-export",
            "--market-id",
            "denver-high-64",
            "--source",
            "fixture",
            "--output-md",
            str(output_path),
            "--output-manifest",
            str(manifest_path),
        ],
        cwd=PROJECT_ROOT,
        env={"PYTHONPATH": str(PROJECT_ROOT / "src")},
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    markdown = output_path.read_text()
    assert "Will the highest temperature in Denver be 64F or higher?" in markdown
    assert "KDEN" in markdown
    assert "0.43" not in markdown
    assert "14000" not in markdown
    payload = json.loads(result.stdout)
    assert payload["market_id"] == "denver-high-64"
    assert payload["prices_excluded"] is True
    assert payload["mirofish_upload"]["endpoint"] == "/api/graph/ontology/generate"
    assert payload["mirofish_upload"]["files"] == [str(output_path)]
    manifest = json.loads(manifest_path.read_text())
    assert manifest["simulation_requirement"] == "Will the highest temperature in Denver be 64F or higher?"
    assert manifest["project_name"] == "Polymarket Miro seed - denver-high-64"
    assert manifest["files"] == [str(output_path)]
    assert "curl -X POST" in manifest["curl_command"]


def test_cli_miro_seed_manifest_shell_quotes_uploaded_paths_and_question(tmp_path):
    input_path = tmp_path / "market.json"
    output_path = tmp_path / "seed with spaces.md"
    manifest_path = tmp_path / "manifest.json"
    input_path.write_text(
        json.dumps(
            {
                "market": {
                    "id": "quote-test",
                    "question": "Will Denver's high be >= 64F?",
                    "description": "Official resolution text only.",
                    "yes_price": 0.42,
                }
            }
        )
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "weather_pm.cli",
            "miro-seed-export",
            "--input-json",
            str(input_path),
            "--output-md",
            str(output_path),
            "--output-manifest",
            str(manifest_path),
        ],
        cwd=PROJECT_ROOT,
        env={"PYTHONPATH": str(PROJECT_ROOT / "src")},
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    manifest = json.loads(manifest_path.read_text())
    assert f"files=@{output_path}" in manifest["curl_command"]
    assert "'\"'\"'" in manifest["curl_command"]
    assert "seed with spaces.md" in manifest["curl_command"]


def test_cli_miro_seed_manifest_includes_miroshark_ask_endpoint_and_paper_toggle(tmp_path):
    input_path = tmp_path / "market.json"
    output_path = tmp_path / "seed.md"
    manifest_path = tmp_path / "manifest.json"
    input_path.write_text(json.dumps({"market": {"id": "m1", "question": "Will rain exceed 10mm?", "yes_price": 0.55}}))

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "weather_pm.cli",
            "miro-seed-export",
            "--input-json",
            str(input_path),
            "--output-md",
            str(output_path),
            "--output-manifest",
            str(manifest_path),
        ],
        cwd=PROJECT_ROOT,
        env={"PYTHONPATH": str(PROJECT_ROOT / "src")},
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    manifest = json.loads(manifest_path.read_text())
    assert manifest["paper_only"] is True
    assert manifest["live_order_allowed"] is False
    assert "/api/simulation/ask" in manifest["compatible_endpoints"]
    assert manifest["miroshark_ask_payload"]["question"] == "Will rain exceed 10mm?"
    assert "0.55" not in output_path.read_text()


def test_cli_miro_seed_export_target_miroshark_uses_base_url_and_omits_mirofish_upload(tmp_path):
    input_path = tmp_path / "market.json"
    output_path = tmp_path / "seed.md"
    manifest_path = tmp_path / "manifest.json"
    input_path.write_text(json.dumps({"market": {"id": "m2", "question": "Will snow fall?", "yes_price": 0.12}}))

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "weather_pm.cli",
            "miro-seed-export",
            "--input-json",
            str(input_path),
            "--output-md",
            str(output_path),
            "--output-manifest",
            str(manifest_path),
            "--target",
            "miroshark",
            "--base-url",
            "http://127.0.0.1:5001",
        ],
        cwd=PROJECT_ROOT,
        env={"PYTHONPATH": str(PROJECT_ROOT / "src")},
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    manifest = json.loads(manifest_path.read_text())
    assert payload["target"] == "miroshark"
    assert payload["mirofish_upload"] is None
    assert payload["miroshark_ask"]["endpoint"] == "/api/simulation/ask"
    assert manifest["target"] == "miroshark"
    assert manifest["base_url"] == "http://127.0.0.1:5001"
    assert manifest["primary_endpoint"] == "/api/simulation/ask"
    assert manifest["mirofish_upload"] is None
    assert manifest["miroshark_ask"]["endpoint"] == "/api/simulation/ask"
    assert "http://127.0.0.1:5001/api/simulation/ask" in manifest["miroshark_ask"]["curl_command"]
    assert "0.12" not in output_path.read_text()


def test_cli_miro_seed_export_target_both_keeps_both_upload_recipes(tmp_path):
    input_path = tmp_path / "market.json"
    output_path = tmp_path / "seed.md"
    manifest_path = tmp_path / "manifest.json"
    input_path.write_text(json.dumps({"market": {"id": "m3", "question": "Will wind exceed 20mph?", "volume": 456}}))

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "weather_pm.cli",
            "miro-seed-export",
            "--input-json",
            str(input_path),
            "--output-md",
            str(output_path),
            "--output-manifest",
            str(manifest_path),
            "--target",
            "both",
        ],
        cwd=PROJECT_ROOT,
        env={"PYTHONPATH": str(PROJECT_ROOT / "src")},
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    manifest = json.loads(manifest_path.read_text())
    assert payload["target"] == "both"
    assert payload["mirofish_upload"]["endpoint"] == "/api/graph/ontology/generate"
    assert payload["miroshark_ask"]["endpoint"] == "/api/simulation/ask"
    assert manifest["target"] == "both"
    assert manifest["mirofish_upload"]["endpoint"] == "/api/graph/ontology/generate"
    assert manifest["miroshark_ask"]["endpoint"] == "/api/simulation/ask"
    assert "456" not in output_path.read_text()
