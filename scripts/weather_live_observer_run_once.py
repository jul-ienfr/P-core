#!/usr/bin/env python3
"""Safe one-shot wrapper for the weather live observer.

This script intentionally performs no installation, update, or scheduler setup. It
loads YAML config, delegates one bounded run to weather_pm.live_observer, and can
write operator-friendly JSON/Markdown summaries.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PYTHON_SRC = ROOT / "python" / "src"
if str(PYTHON_SRC) not in sys.path:
    sys.path.insert(0, str(PYTHON_SRC))

from weather_pm.live_observer import run_live_observer_once  # noqa: E402
from weather_pm.live_observer_config import load_live_observer_config  # noqa: E402

SAFE_UNAVAILABLE_CODES = {"collection_disabled", "read_only_unavailable"}


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        config = load_live_observer_config(args.config)
        summary = run_live_observer_once(config, source=args.source, dry_run=args.dry_run)
        payload = summary.to_dict()
        if args.summary_json:
            _write_text(Path(args.summary_json), json.dumps(payload, indent=2, sort_keys=True) + "\n", create_dirs=args.create_report_dirs)
        if args.summary_md:
            _write_text(Path(args.summary_md), _markdown_summary(payload), create_dirs=args.create_report_dirs)
        print(json.dumps(payload, sort_keys=True))
        return _exit_code(payload)
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 2


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one safe weather live-observer pass")
    parser.add_argument(
        "--config",
        type=Path,
        default=ROOT / "config" / "weather_live_observer.yaml",
        help="Path to weather live observer YAML config",
    )
    parser.add_argument(
        "--source",
        choices=("live", "fixture"),
        default="live",
        help="Source to collect from. live uses bounded public read-only Polymarket data; fixture is local smoke mode.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Run without writing snapshots")
    parser.add_argument("--summary-json", type=Path, help="Optional JSON summary report path")
    parser.add_argument("--summary-md", type=Path, help="Optional Markdown summary report path")
    parser.add_argument(
        "--create-report-dirs",
        dest="create_report_dirs",
        action="store_true",
        default=True,
        help="Create parent directories for summary report paths (default)",
    )
    parser.add_argument(
        "--no-create-report-dirs",
        dest="create_report_dirs",
        action="store_false",
        help="Fail if a summary report parent directory does not already exist",
    )
    return parser


def _write_text(path: Path, text: str, *, create_dirs: bool) -> None:
    parent = path.parent
    if parent and not parent.exists():
        if not create_dirs:
            raise OSError(f"summary parent directory does not exist: {parent}")
        parent.mkdir(parents=True, exist_ok=True)
    if parent and not parent.is_dir():
        raise OSError(f"summary parent path is not a directory: {parent}")
    path.write_text(text, encoding="utf-8")


def _markdown_summary(payload: dict[str, Any]) -> str:
    errors = payload.get("errors") or []
    snapshots = payload.get("snapshots") or {}
    lines = [
        "# Weather Live Observer Run Summary",
        "",
        f"- Scenario: {payload.get('scenario')}",
        f"- Source: {payload.get('source')}",
        f"- Dry-run: {str(payload.get('dry_run')).lower()}",
        f"- Collection enabled: {str(payload.get('collection_enabled')).lower()}",
        f"- Collection active: {str(payload.get('collection_active')).lower()}",
        f"- Paper-only: {str(payload.get('paper_only')).lower()}",
        f"- Live order allowed: {str(payload.get('live_order_allowed')).lower()}",
        "",
        "## Snapshots",
    ]
    if snapshots:
        for name, count in sorted(snapshots.items()):
            lines.append(f"- {name}: {count}")
    else:
        lines.append("- none")
    lines.extend(["", "## Errors"])
    if errors:
        for error in errors:
            lines.append(f"- {error.get('code')}: {error.get('message')}")
    else:
        lines.append("- none")
    return "\n".join(lines) + "\n"


def _exit_code(payload: dict[str, Any]) -> int:
    errors = payload.get("errors") or []
    if not errors:
        return 0
    if all(error.get("code") in SAFE_UNAVAILABLE_CODES for error in errors):
        return 0
    if payload.get("snapshots") or payload.get("storage_results"):
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
