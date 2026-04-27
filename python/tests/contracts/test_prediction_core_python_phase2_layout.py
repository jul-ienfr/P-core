from __future__ import annotations

from pathlib import Path


REQUIRED_PATHS = [
    "python/README.md",
    "python/src/prediction_core/replay/__init__.py",
    "python/src/prediction_core/paper/__init__.py",
    "python/src/prediction_core/calibration/__init__.py",
    "python/src/prediction_core/analytics/__init__.py",
    "python/src/prediction_core/evaluation/__init__.py",
    "python/docs/reuse-map.md",
]

SEED_EXTRACTION_DOMAINS = ["replay", "paper"]
REMAINING_PHASE2_DOMAINS = ["calibration", "analytics", "evaluation"]


def test_prediction_core_python_phase2_layout_exists() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    missing = [relative for relative in REQUIRED_PATHS if not (repo_root / relative).exists()]
    assert missing == []


def test_prediction_core_python_readme_frames_phase2_boundaries() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    readme = (repo_root / "python/README.md").read_text(encoding="utf-8")

    assert "## Phase 2 scope for this extraction" in readme
    assert "premières extractions canoniques minimales" in readme
    assert "ne sont pas migrées en bloc" in readme

    for domain in [*SEED_EXTRACTION_DOMAINS, *REMAINING_PHASE2_DOMAINS]:
        assert f"- `{domain}`" in readme


def test_prediction_core_python_reuse_map_documents_exports_and_minimal_domain_boundaries() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    reuse_map = (repo_root / "python/docs/reuse-map.md").read_text(encoding="utf-8")

    assert "## Principes d'exports Phase 2" in reuse_map
    assert "première extraction canonique minimale" in reuse_map
    assert "frontières de modules sans API stable" in reuse_map

    for domain in [*SEED_EXTRACTION_DOMAINS, *REMAINING_PHASE2_DOMAINS]:
        assert f"### {domain}" in reuse_map

    for domain in REMAINING_PHASE2_DOMAINS:
        assert "Frontière minimale à préserver" in reuse_map
        assert "Hors frontière pour cette extraction" in reuse_map
        assert f"`src/prediction_core/{domain}/`" in reuse_map
