from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

StatusFetcher = Callable[..., dict[str, Any]]

_DEFAULT_OUTPUT_DIR = Path("/home/jul/prediction_core/data/polymarket")
_DEFAULT_REPOLL_SCHEDULE = "every 2h"
_DEFAULT_REPOLL_REPEAT = 24


def write_paper_resolution_monitor(
    *,
    market_id: str,
    source: str = "live",
    settlement_date: str,
    paper_side: str,
    paper_notional_usd: float | None = None,
    paper_shares: float | None = None,
    output_dir: str | Path = _DEFAULT_OUTPUT_DIR,
    status_fetcher: StatusFetcher | None = None,
) -> dict[str, Any]:
    """Persist a paper-only resolution monitor snapshot for one weather market."""
    if status_fetcher is None:
        from weather_pm.cli import resolution_status_for_market_id

        status_fetcher = resolution_status_for_market_id
    status = status_fetcher(market_id, source=source, date=settlement_date)
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    date_slug = settlement_date.replace("-", "")
    raw_path = out_dir / f"weather_paper_{_safe_slug(market_id)}_resolution_marketdate_{date_slug}.json"
    monitor_path = out_dir / f"weather_paper_{_safe_slug(market_id)}_monitor_latest.md"

    paper_trade = {
        "side": paper_side,
        "notional_usd": paper_notional_usd,
        "shares": paper_shares,
    }
    enriched_status = {
        **status,
        "mode": "paper_only",
        "poll_timestamp": timestamp,
        "paper_trade": paper_trade,
    }
    raw_path.write_text(json.dumps(enriched_status, indent=2, sort_keys=True))
    monitor_path.write_text(_render_monitor_markdown(enriched_status, timestamp=timestamp))

    should_repoll = str(status.get("confirmed_outcome") or "pending") == "pending"
    cron_repoll = (
        {
            "schedule": _DEFAULT_REPOLL_SCHEDULE,
            "repeat": _DEFAULT_REPOLL_REPEAT,
            "prompt": _cron_prompt(
                market_id=market_id,
                source=source,
                settlement_date=settlement_date,
                paper_side=paper_side,
                paper_notional_usd=paper_notional_usd,
                paper_shares=paper_shares,
                output_dir=str(out_dir),
            ),
        }
        if should_repoll
        else None
    )
    return {
        "mode": "paper_only",
        "market_id": market_id,
        "source": source,
        "settlement_date": settlement_date,
        "poll_timestamp": timestamp,
        "paper_trade": paper_trade,
        "status": status,
        "should_repoll": should_repoll,
        "cron_repoll": cron_repoll,
        "artifacts": {
            "raw_status_json": str(raw_path),
            "operator_monitor_md": str(monitor_path),
        },
    }


def _render_monitor_markdown(status: dict[str, Any], *, timestamp: str) -> str:
    latest = _dict(status.get("latest_direct"))
    official = _dict(status.get("official_daily_extract"))
    latency = _dict(status.get("latency"))
    latest_latency = _dict(latency.get("latest"))
    official_latency = _dict(latency.get("official"))
    route = _dict(status.get("source_route"))
    trade = _dict(status.get("paper_trade"))
    lines = [
        f"# Weather paper resolution monitor — {status.get('market_id')}",
        "",
        f"Poll timestamp: {timestamp}",
        "Mode: paper only",
        f"Market: {status.get('market_id')}",
        f"Source: {status.get('source')}",
        f"Settlement date: {status.get('date')}",
        f"Paper side: {trade.get('side')}",
        f"Paper notional USD: {trade.get('notional_usd')}",
        f"Paper shares: {trade.get('shares')}",
        "",
        f"Latest direct: available={latest.get('available')} value={latest.get('value')} timestamp={latest.get('timestamp')} tier={latest.get('latency_tier')}",
        f"Official daily extract: available={official.get('available')} value={official.get('value')} timestamp={official.get('timestamp')} tier={official.get('latency_tier')}",
        f"Provisional outcome: {status.get('provisional_outcome')}",
        f"Confirmed outcome: {status.get('confirmed_outcome')}",
        f"Operator action: {status.get('action_operator')}",
        "",
        f"Latest polling focus: {latest_latency.get('polling_focus')}",
        f"Official polling focus: {official_latency.get('polling_focus')}",
        f"Official expected lag seconds: {official_latency.get('expected_lag_seconds')}",
        f"Latest URL: {route.get('latest_url')}",
        f"Official history URL: {route.get('history_url')}",
        "",
        "Note: provisional latest observations are useful for monitoring, but final paper outcome stays pending until the official daily extract is available.",
    ]
    return "\n".join(lines) + "\n"


def _cron_prompt(
    *,
    market_id: str,
    source: str,
    settlement_date: str,
    paper_side: str,
    paper_notional_usd: float | None,
    paper_shares: float | None,
    output_dir: str,
) -> str:
    return (
        "Paper-only weather resolution monitor repoll. "
        "In /home/jul/P-core, run the weather-pm monitor-paper-resolution command for "
        f"market_id={market_id}, source={source}, date={settlement_date}, paper_side={paper_side}, "
        f"paper_notional_usd={paper_notional_usd}, paper_shares={paper_shares}, output_dir={output_dir}. "
        "Update the same raw JSON and operator markdown artifacts. Do not place real orders; this is paper-only. "
        "Report back whether confirmed_outcome is still pending or confirmed."
    )


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_slug(value: str) -> str:
    return "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value)
