from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def read_doc(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def test_panoptique_strategy_docs_exist_with_stable_headings() -> None:
    required = {
        "docs/strategy/PANOPTIQUE_STRATEGY.md": [
            "# Panoptique Strategy",
            "## Thèse centrale",
            "## Non-objectifs",
            "## Architecture progressive",
            "## Mesure avant capital",
            "## Paper-only boundary",
        ],
        "docs/strategy/EVIDENCE_REGISTER.md": [
            "# Panoptique Evidence Register",
            "## Classification scale",
            "## Major empirical claims",
            "| Claim | Classification | Evidence status | Phase impact |",
            "bot homogenization",
            "Polymarket volume/efficiency",
            "weather bot degradation",
            "copy-trading decay",
            "phase gates",
        ],
        "docs/strategy/ASSUMPTIONS.md": [
            "# Panoptique Assumptions",
            "## Assumptions to test",
            "| Assumption | Falsification signal | Planned measurement source |",
            "Verified facts are separated from hypotheses",
        ],
        "docs/strategy/GATES.md": [
            "# Panoptique Gates",
            "## Hard gates",
            "Phase 2 sample target: 200+ paper resolved trades",
            "Level 2 statistical gate: p<0.05 / 100+ markets",
            "No Phase 10/live without separate explicit approval",
            "paper-only",
        ],
        "docs/panoptique/current-system-map.md": [
            "# Current System Map",
            "## Existing module mapping",
            "weather_pm/weather_latency_edge.py",
            "winning_patterns.py",
            "wallet_intel.py",
            "traders.py",
            "strategy_extractor.py",
            "event_surface.py",
            "prediction_core/analytics",
            "prediction_core/calibration",
            "prediction_core/evaluation",
            "prediction_core/execution",
        ],
    }

    for relative_path, expected_fragments in required.items():
        path = REPO_ROOT / relative_path
        assert path.exists(), f"missing required Panoptique doc: {relative_path}"
        content = read_doc(relative_path)
        for fragment in expected_fragments:
            assert fragment in content, f"{relative_path} missing fragment: {fragment}"


def test_root_readme_has_short_panoptique_pointer() -> None:
    readme = read_doc("README.md")
    assert "## Panoptique migration" in readme
    assert "docs/plans/2026-04-26-panoptique-migration-plan.md" in readme
    assert "docs/strategy/PANOPTIQUE_STRATEGY.md" in readme
    assert "paper-only" in readme
