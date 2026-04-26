from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence
from urllib.parse import quote_plus
from urllib.request import Request, urlopen
from uuid import uuid5, NAMESPACE_URL

from .contracts import SCHEMA_VERSION

DEFAULT_SEARCH_TERMS = (
    "polymarket bot",
    "kalshi bot",
    "prediction market trading bot",
    "polymarket agent",
)

KEYWORDS = (
    "polymarket",
    "kalshi",
    "prediction market",
    "trading bot",
    "agent",
    "openai_api_key",
    "anthropic_api_key",
    "prompt",
    "config",
    "threshold",
    "edge_threshold",
    "kelly",
)

PARAMETER_MARKERS = ("EDGE_THRESHOLD", "THRESHOLD", "KELLY", "MAX_POSITION", "MIN_EDGE", "SLIPPAGE")


@dataclass(frozen=True, kw_only=True)
class GitHubRepoMetadata:
    name: str
    url: str
    stars: int
    forks: int
    pushed_at: str | None
    topics: list[str] = field(default_factory=list)
    readme_hash: str | None = None
    detected_keywords: list[str] = field(default_factory=list)
    search_terms: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)
    schema_version: str = SCHEMA_VERSION

    @property
    def repo_id(self) -> str:
        return str(uuid5(NAMESPACE_URL, self.url))

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "url": self.url,
            "stars": self.stars,
            "forks": self.forks,
            "pushed_at": self.pushed_at,
            "topics": list(self.topics),
            "readme_hash": self.readme_hash,
            "detected_keywords": list(self.detected_keywords),
            "search_terms": list(self.search_terms),
            "raw": dict(self.raw),
            "schema_version": self.schema_version,
        }

    def to_external_repo_record(self) -> dict[str, Any]:
        return {"repo_id": self.repo_id, "url": self.url, "name": self.name, "raw": self.to_dict()}

    def manual_audit_command(self) -> str:
        safe_name = self.name.replace("/", "-")
        target = f"/tmp/panoptique-audit-{safe_name}"
        return f"git clone --depth 1 {self.url}.git {target}  # inspect only; do not run third-party code"


@dataclass(frozen=True, kw_only=True)
class GitHubCrawlResult:
    command: str
    status: str
    count: int
    artifact_path: Path
    report_path: Path
    db_status: str
    errors: list[str] = field(default_factory=list)


def build_github_search_url(term: str, *, limit: int = 25) -> str:
    return f"https://api.github.com/search/repositories?q={quote_plus(term)}&sort=stars&order=desc&per_page={int(limit)}"


def fetch_github_repos_public(term: str, *, limit: int = 25) -> list[dict[str, Any]]:
    request = Request(build_github_search_url(term, limit=limit), headers={"Accept": "application/vnd.github+json", "User-Agent": "panoptique-read-only-crawler"})
    with urlopen(request, timeout=20) as response:  # noqa: S310 - intentional public GitHub API read-only call
        payload = json.loads(response.read().decode("utf-8"))
    return list(payload.get("items", []))


def _readme_hash(item: dict[str, Any]) -> str | None:
    text = item.get("readme_text")
    if text is None:
        return item.get("readme_hash")
    return sha256(str(text).encode("utf-8")).hexdigest()


def _combined_public_text(item: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("full_name", "name", "description", "readme_text"):
        value = item.get(key)
        if value:
            parts.append(str(value))
    parts.extend(str(topic) for topic in item.get("topics") or [])
    return "\n".join(parts).lower()


def detect_keywords(item: dict[str, Any]) -> list[str]:
    text = _combined_public_text(item)
    found: list[str] = []
    for keyword in KEYWORDS:
        if keyword.lower() in text:
            found.append(keyword)
    if "openai_api_key" not in found and "openai_api_key" in text.replace(" ", "_"):
        found.append("openai_api_key")
    return sorted(set(found))


def normalize_github_repo(item: dict[str, Any], *, search_term: str) -> GitHubRepoMetadata:
    name = str(item.get("full_name") or item.get("name") or item.get("html_url") or "unknown")
    url = str(item.get("html_url") or item.get("url") or "")
    readme_text = item.get("readme_text")
    raw = {
        "source": "github_public_api_or_fixture",
        "search_term": search_term,
        "description": item.get("description"),
        "readme_text_present": readme_text is not None,
        "default_crawler_no_clone": True,
    }
    return GitHubRepoMetadata(
        name=name,
        url=url,
        stars=int(item.get("stargazers_count") or item.get("stars") or 0),
        forks=int(item.get("forks_count") or item.get("forks") or 0),
        pushed_at=item.get("pushed_at"),
        topics=list(item.get("topics") or []),
        readme_hash=_readme_hash(item),
        detected_keywords=detect_keywords(item),
        search_terms=[search_term],
        raw=raw,
    )


def merge_repositories(repositories: Iterable[GitHubRepoMetadata]) -> list[GitHubRepoMetadata]:
    merged: dict[str, GitHubRepoMetadata] = {}
    for repo in repositories:
        existing = merged.get(repo.url)
        if existing is None:
            merged[repo.url] = repo
            continue
        terms = sorted(set(existing.search_terms + repo.search_terms))
        keywords = sorted(set(existing.detected_keywords + repo.detected_keywords))
        merged[repo.url] = GitHubRepoMetadata(
            name=existing.name,
            url=existing.url,
            stars=max(existing.stars, repo.stars),
            forks=max(existing.forks, repo.forks),
            pushed_at=existing.pushed_at or repo.pushed_at,
            topics=sorted(set(existing.topics + repo.topics)),
            readme_hash=existing.readme_hash or repo.readme_hash,
            detected_keywords=keywords,
            search_terms=terms,
            raw={**existing.raw, "search_terms": terms},
        )
    return sorted(merged.values(), key=lambda r: (-r.stars, r.name))


def analyze_ecosystem(repositories: Sequence[GitHubRepoMetadata]) -> dict[str, Any]:
    likely_templates = [repo.name for repo in repositories if any(marker in repo.name.lower() for marker in ("template", "starter", "boilerplate"))]
    common_parameters = sorted({marker for repo in repositories for marker in PARAMETER_MARKERS if marker.lower() in json.dumps(repo.to_dict()).lower()})
    exposure_keywords = {"prompt", "config", "openai_api_key", "anthropic_api_key"}
    prompt_or_config_exposure = [repo.name for repo in repositories if exposure_keywords.intersection(repo.detected_keywords)]
    keyword_counts: dict[str, int] = {}
    for repo in repositories:
        for keyword in repo.detected_keywords:
            keyword_counts[keyword] = keyword_counts.get(keyword, 0) + 1
    return {
        "likely_templates": likely_templates,
        "common_parameters": common_parameters,
        "prompt_or_config_exposure": prompt_or_config_exposure,
        "keyword_counts": dict(sorted(keyword_counts.items())),
    }


def render_ecosystem_report(repositories: Sequence[GitHubRepoMetadata], *, analysis: dict[str, Any] | None = None) -> str:
    analysis = analysis or analyze_ecosystem(repositories)
    lines = [
        "# Panoptique GitHub Ecosystem Crawl",
        "",
        "Read-only public metadata report. No repositories were cloned by the default crawler. No third-party code was executed.",
        "",
        "## Summary",
        f"- Repositories recorded: {len(repositories)}",
        f"- Likely templates: {', '.join(analysis['likely_templates']) if analysis['likely_templates'] else 'none detected'}",
        f"- Common parameters: {', '.join(analysis['common_parameters']) if analysis['common_parameters'] else 'none detected'}",
        f"- prompt/config exposure if visible: {', '.join(analysis['prompt_or_config_exposure']) if analysis['prompt_or_config_exposure'] else 'none detected'}",
        "",
        "## Repositories",
    ]
    for repo in repositories:
        lines.append(f"- {repo.name} ({repo.url}) stars={repo.stars} forks={repo.forks} keywords={','.join(repo.detected_keywords) or 'none'}")
    lines.extend(["", "## Manual audit", "Optional manual audit may shallow clone a selected repo into `/tmp` only; inspect files only and do not run code."])
    return "\n".join(lines) + "\n"


def run_github_repo_crawl(
    *,
    output_dir: str | Path,
    repository: Any | None = None,
    terms: Sequence[str] = DEFAULT_SEARCH_TERMS,
    limit_per_term: int = 25,
    fetcher: Callable[[str], list[dict[str, Any]]] | None = None,
    fetched_at: str | None = None,
) -> GitHubCrawlResult:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    timestamp = fetched_at or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    safe_timestamp = timestamp.replace(":", "").replace("-", "")
    artifact_path = output / f"github_repos_{safe_timestamp}.json"
    report_path = output / f"github_repos_{safe_timestamp}.md"
    fetch = fetcher or (lambda term, *, limit: fetch_github_repos_public(term, limit=limit))
    errors: list[str] = []
    collected: list[GitHubRepoMetadata] = []
    for term in terms:
        try:
            items = fetch(term, limit=limit_per_term)  # type: ignore[misc]
            collected.extend(normalize_github_repo(item, search_term=term) for item in items)
        except Exception as exc:  # pragma: no cover - network failure path covered by CLI/manual use
            errors.append(f"{term}: {exc}")
    repos = merge_repositories(collected)
    analysis = analyze_ecosystem(repos)
    db_status = "skipped_unavailable"
    if repository is not None:
        for repo in repos:
            repository.upsert_external_repo(repo)
        db_status = "inserted"
    payload = {
        "metadata": {
            "source": "github_public_api",
            "schema_version": SCHEMA_VERSION,
            "fetched_at": timestamp,
            "search_terms": list(terms),
            "limit_per_term": limit_per_term,
            "crawler_mode": "public_metadata_only_no_clone",
            "db_status": db_status,
        },
        "repositories": [repo.to_dict() for repo in repos],
        "analysis": analysis,
        "errors": errors,
    }
    artifact_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report_path.write_text(render_ecosystem_report(repos, analysis=analysis), encoding="utf-8")
    return GitHubCrawlResult(
        command="github-repos-crawl",
        status="ok" if not errors else "error",
        count=len(repos),
        artifact_path=artifact_path,
        report_path=report_path,
        db_status=db_status,
        errors=errors,
    )
