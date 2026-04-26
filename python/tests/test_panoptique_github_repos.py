from __future__ import annotations

import json
from pathlib import Path

from panoptique.artifacts import read_jsonl
from panoptique.github_repos import (
    DEFAULT_SEARCH_TERMS,
    GitHubRepoMetadata,
    analyze_ecosystem,
    build_github_search_url,
    normalize_github_repo,
    render_ecosystem_report,
    run_github_repo_crawl,
)
from panoptique.repositories import PanoptiqueRepository, connect_sqlite_memory


def github_item() -> dict:
    return {
        "full_name": "example/polymarket-bot-template",
        "html_url": "https://github.com/example/polymarket-bot-template",
        "stargazers_count": 42,
        "forks_count": 7,
        "pushed_at": "2026-04-20T10:00:00Z",
        "topics": ["polymarket", "trading-bot", "agent"],
        "description": "Polymarket trading bot with OpenAI prompt config and threshold parameters",
        "readme_text": "# Bot\nSet OPENAI_API_KEY and EDGE_THRESHOLD=0.08 in config.yaml. Prompt template included.",
    }


def test_default_search_terms_are_phase6_v0_terms() -> None:
    assert DEFAULT_SEARCH_TERMS == (
        "polymarket bot",
        "kalshi bot",
        "prediction market trading bot",
        "polymarket agent",
    )
    assert "q=polymarket+bot" in build_github_search_url("polymarket bot")


def test_normalize_github_repo_records_metadata_only_and_readme_hash() -> None:
    metadata = normalize_github_repo(github_item(), search_term="polymarket bot")

    assert isinstance(metadata, GitHubRepoMetadata)
    assert metadata.name == "example/polymarket-bot-template"
    assert metadata.url == "https://github.com/example/polymarket-bot-template"
    assert metadata.stars == 42
    assert metadata.forks == 7
    assert metadata.pushed_at == "2026-04-20T10:00:00Z"
    assert metadata.topics == ["polymarket", "trading-bot", "agent"]
    assert len(metadata.readme_hash) == 64
    assert "polymarket" in metadata.detected_keywords
    assert "openai_api_key" in metadata.detected_keywords
    assert "readme_text" not in metadata.to_dict()
    assert metadata.raw["readme_text_present"] is True
    assert metadata.raw["default_crawler_no_clone"] is True


def test_crawler_uses_fixture_fetcher_writes_json_artifacts_and_external_repo_rows(tmp_path: Path) -> None:
    conn = connect_sqlite_memory()
    repo = PanoptiqueRepository(conn)
    repo.create_schema()
    calls: list[str] = []

    def fetcher(term: str, *, limit: int) -> list[dict]:
        calls.append(term)
        assert limit == 2
        return [github_item()]

    result = run_github_repo_crawl(
        output_dir=tmp_path,
        repository=repo,
        terms=("polymarket bot", "kalshi bot"),
        limit_per_term=2,
        fetcher=fetcher,
        fetched_at="2026-04-26T12:00:00Z",
    )

    assert result.status == "ok"
    assert result.count == 1
    assert calls == ["polymarket bot", "kalshi bot"]
    payload = json.loads(result.artifact_path.read_text(encoding="utf-8"))
    assert payload["metadata"]["crawler_mode"] == "public_metadata_only_no_clone"
    assert payload["repositories"][0]["name"] == "example/polymarket-bot-template"
    assert payload["repositories"][0]["readme_hash"]
    assert "Likely templates" in result.report_path.read_text(encoding="utf-8")
    rows = repo.list_external_repos()
    assert rows[0]["name"] == "example/polymarket-bot-template"
    assert rows[0]["raw"]["stars"] == 42


def test_crawler_default_path_does_not_clone_repos(tmp_path: Path) -> None:
    cloned_marker = tmp_path / "should_not_exist"

    def fetcher(term: str, *, limit: int) -> list[dict]:
        return [{**github_item(), "clone_marker": str(cloned_marker)}]

    result = run_github_repo_crawl(output_dir=tmp_path, terms=("polymarket bot",), limit_per_term=1, fetcher=fetcher)

    assert result.status == "ok"
    assert not cloned_marker.exists()


def test_ecosystem_analysis_report_flags_templates_parameters_and_prompt_exposure() -> None:
    metadata = normalize_github_repo(github_item(), search_term="polymarket bot")
    analysis = analyze_ecosystem([metadata])
    report = render_ecosystem_report([metadata], analysis=analysis)

    assert analysis["likely_templates"] == ["example/polymarket-bot-template"]
    assert "EDGE_THRESHOLD" in analysis["common_parameters"]
    assert analysis["prompt_or_config_exposure"] == ["example/polymarket-bot-template"]
    assert "prompt/config exposure if visible" in report
    assert "No third-party code was executed" in report


def test_manual_audit_command_is_tmp_only_and_no_code_execution() -> None:
    metadata = normalize_github_repo(github_item(), search_term="polymarket bot")
    command = metadata.manual_audit_command()

    assert command.startswith("git clone --depth 1")
    assert " /tmp/panoptique-audit-" in command
    assert "cd " not in command
    assert "python" not in command
    assert "npm" not in command
