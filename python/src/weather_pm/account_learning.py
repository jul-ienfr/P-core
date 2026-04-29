from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from weather_pm.market_parser import parse_market_question


@dataclass(frozen=True, slots=True)
class AccountTrade:
    wallet: str
    handle: str | None
    title: str
    side: str
    price: float | None
    size: float | None
    usdc: float | None
    timestamp: str | None
    city: str | None
    date: str | None
    market_type: str
    timing_bucket: str
    size_bucket: str
    price_bucket: str
    source: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ShadowProfile:
    wallet: str
    handle: str | None
    trade_count: int
    observed_usdc: float
    avg_trade_usdc: float | None
    max_trade_usdc: float | None
    sizing_buckets: dict[str, int]
    timing_buckets: dict[str, int]
    city_buckets: dict[str, int]
    type_buckets: dict[str, int]
    side_buckets: dict[str, int]
    price_buckets: dict[str, int]
    abstention_signals: list[str]
    top_examples: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_account_trade_backfill(input_json: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(input_json).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("account trade backfill JSON must be an object")
    trades = [trade.to_dict() for trade in normalize_account_trades(payload)]
    followed_accounts = _followed_accounts(payload, trades)
    return {
        "artifact": "account_trades",
        "source": str(input_json),
        "paper_only": True,
        "live_order_allowed": False,
        "trade_count": len(trades),
        "accounts": max(_account_count(trades), len(followed_accounts)),
        "followed_accounts": followed_accounts,
        "trades": trades,
    }


def normalize_account_trades(payload: dict[str, Any]) -> list[AccountTrade]:
    metadata = _account_metadata(payload)
    trades: list[AccountTrade] = []
    for raw in _iter_trade_rows(payload):
        wallet = str(raw.get("wallet") or raw.get("user") or raw.get("proxyWallet") or "").strip()
        handle = _clean_optional(raw.get("handle") or raw.get("username") or raw.get("name"))
        if not wallet and handle:
            wallet = f"handle:{handle}"
        if wallet in metadata:
            handle = handle or metadata[wallet].get("handle")
        title = str(raw.get("title") or raw.get("question") or raw.get("market") or raw.get("marketTitle") or "").strip()
        if not wallet or not title:
            continue
        price = _optional_float(raw.get("price") or raw.get("avgPrice") or raw.get("averagePrice"))
        size = _optional_float(raw.get("size") or raw.get("shares") or raw.get("quantity"))
        usdc = _optional_float(raw.get("usdc") or raw.get("notional") or raw.get("value") or raw.get("amount"))
        if usdc is None and price is not None and size is not None:
            usdc = round(price * size, 4)
        city, date, market_type = _market_shape(title, raw)
        trades.append(
            AccountTrade(
                wallet=wallet,
                handle=handle,
                title=title,
                side=str(raw.get("side") or raw.get("outcome") or raw.get("action") or "unknown").strip().lower() or "unknown",
                price=price,
                size=size,
                usdc=usdc,
                timestamp=_clean_optional(raw.get("timestamp") or raw.get("createdAt") or raw.get("created_at") or raw.get("time")),
                city=city,
                date=date,
                market_type=market_type,
                timing_bucket=_timing_bucket(raw),
                size_bucket=_size_bucket(usdc),
                price_bucket=_price_bucket(price),
                source=str(raw.get("source") or "public_backfill"),
            )
        )
    return trades


def build_shadow_profiles(trades_payload: dict[str, Any]) -> dict[str, Any]:
    trades = [item for item in trades_payload.get("trades", []) if isinstance(item, dict)]
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for trade in trades:
        wallet = str(trade.get("wallet") or "").strip()
        if wallet:
            grouped[wallet].append(trade)
    handles = _followed_account_handles(trades_payload)
    for wallet in handles:
        grouped.setdefault(wallet, [])
    profiles = [_build_profile(wallet, rows, handle=handles.get(wallet)).to_dict() for wallet, rows in sorted(grouped.items())]
    profiles.sort(key=lambda row: (float(row.get("observed_usdc") or 0.0), int(row.get("trade_count") or 0)), reverse=True)
    return {
        "artifact": "shadow_profiles",
        "source": trades_payload.get("source"),
        "paper_only": True,
        "live_order_allowed": False,
        "summary": {
            "accounts": len(profiles),
            "trades": len(trades),
            "observed_usdc": round(sum(float(row.get("observed_usdc") or 0.0) for row in profiles), 2),
            "abstention_profiles": sum(1 for row in profiles if row.get("trade_count") == 0),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
        "profiles": profiles,
    }


def write_account_trade_import(input_json: str | Path, output_json: str | Path) -> dict[str, Any]:
    payload = load_account_trade_backfill(input_json)
    output_path = Path(output_json)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload.setdefault("artifacts", {})["output_json"] = str(output_path)
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return _compact_trade_import(payload)



def write_shadow_profile_report(trades_json: str | Path, output_json: str | Path, output_md: str | Path | None = None) -> dict[str, Any]:
    trades_payload = json.loads(Path(trades_json).read_text(encoding="utf-8"))
    if not isinstance(trades_payload, dict):
        raise ValueError("account trades JSON must be an object")
    report = build_shadow_profiles(trades_payload)
    report.setdefault("artifacts", {})["source_trades_json"] = str(trades_json)
    output_path = Path(output_json)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    report["artifacts"]["output_json"] = str(output_path)
    if output_md:
        md_path = Path(output_md)
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(shadow_profiles_markdown(report), encoding="utf-8")
        report["artifacts"]["output_md"] = str(md_path)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return _compact_profile_report(report)


def write_account_learning_backfill_pipeline(input_json: str | Path, output_dir: str | Path, *, run_id: str | None = None) -> dict[str, Any]:
    resolved_run_id = run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_path = Path(output_dir)
    trades_json = output_path / "account_trades.json"
    profiles_json = output_path / "shadow_profiles.json"
    profiles_md = output_path / "shadow_profiles.md"
    trade_import = write_account_trade_import(input_json, trades_json)
    profile_report = write_shadow_profile_report(trades_json, profiles_json, output_md=profiles_md)
    return {
        "artifact": "account_learning_backfill_pipeline",
        "run_id": resolved_run_id,
        "paper_only": True,
        "live_order_allowed": False,
        "trade_import": trade_import,
        "profile_report": profile_report,
        "artifacts": {
            "source_backfill_json": str(input_json),
            "account_trades_json": str(trades_json),
            "shadow_profiles_json": str(profiles_json),
            "shadow_profiles_md": str(profiles_md),
        },
    }


def shadow_profiles_markdown(report: dict[str, Any]) -> str:
    lines = ["# Polymarket weather shadow profiles", "", "Read-only profile artifact. No wallet, signature, or live order action is authorized.", ""]
    summary = report.get("summary", {}) if isinstance(report.get("summary"), dict) else {}
    lines.extend([
        f"- Accounts: {summary.get('accounts', 0)}",
        f"- Trades: {summary.get('trades', 0)}",
        f"- Observed USDC: {summary.get('observed_usdc', 0)}",
        "",
        "| Account | Trades | Avg USDC | Top sizing | Top timing | Top city | Top type | Abstention |",
        "| --- | ---: | ---: | --- | --- | --- | --- | --- |",
    ])
    for profile in report.get("profiles", []):
        if not isinstance(profile, dict):
            continue
        account = profile.get("handle") or profile.get("wallet")
        lines.append(
            "| "
            + " | ".join(
                [
                    _md(account),
                    str(profile.get("trade_count", 0)),
                    str(profile.get("avg_trade_usdc") or ""),
                    _md(_top_bucket(profile.get("sizing_buckets"))),
                    _md(_top_bucket(profile.get("timing_buckets"))),
                    _md(_top_bucket(profile.get("city_buckets"))),
                    _md(_top_bucket(profile.get("type_buckets"))),
                    _md(", ".join(profile.get("abstention_signals") or [])),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def build_shadow_profile_deep_dive(profiles_payload: dict[str, Any], *, wallet: str | None = None, handle: str | None = None) -> dict[str, Any]:
    profiles = [item for item in profiles_payload.get("profiles", []) if isinstance(item, dict)]
    target = None
    for profile in profiles:
        if wallet and str(profile.get("wallet") or "").lower() == wallet.lower():
            target = profile
            break
        if handle and str(profile.get("handle") or "").lower() == handle.lower():
            target = profile
            break
    if target is None:
        raise ValueError("profile not found for wallet/handle")
    return {
        "artifact": "shadow_profile_deep_dive",
        "paper_only": True,
        "live_order_allowed": False,
        "profile": target,
        "operator_notes": _deep_dive_notes(target),
    }


def write_shadow_profile_deep_dive(profiles_json: str | Path, *, wallet: str | None = None, handle: str | None = None, output_md: str | Path | None = None) -> dict[str, Any]:
    payload = json.loads(Path(profiles_json).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("shadow profiles JSON must be an object")
    report = build_shadow_profile_deep_dive(payload, wallet=wallet, handle=handle)
    report.setdefault("artifacts", {})["source_profiles_json"] = str(profiles_json)
    if output_md:
        output_path = Path(output_md)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(shadow_profile_deep_dive_markdown(report), encoding="utf-8")
        report["artifacts"]["output_md"] = str(output_path)
    return report


def shadow_profile_deep_dive_markdown(report: dict[str, Any]) -> str:
    profile = report.get("profile", {}) if isinstance(report.get("profile"), dict) else {}
    lines = [f"# Shadow profile deep dive: {profile.get('handle') or profile.get('wallet')}", "", "Paper-only/read-only account-learning artifact.", ""]
    for note in report.get("operator_notes", []):
        lines.append(f"- {note}")
    lines.extend(["", "## Examples", ""])
    for example in profile.get("top_examples", []):
        if isinstance(example, dict):
            lines.append(f"- {example.get('side')} {example.get('usdc')} USDC @ {example.get('price')}: {example.get('title')}")
    lines.append("")
    return "\n".join(lines)


def _iter_trade_rows(payload: dict[str, Any]) -> Iterable[dict[str, Any]]:
    for key in ("trades", "account_trades", "activity", "data", "results"):
        rows = payload.get(key)
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, dict):
                    yield row
    accounts = payload.get("accounts")
    if isinstance(accounts, list):
        for account in accounts:
            if not isinstance(account, dict):
                continue
            base = {
                "wallet": account.get("wallet"),
                "handle": account.get("handle") or account.get("name") or account.get("username"),
            }
            for key in ("top_recent_weather_trades", "recent_weather_trades_detail", "trades", "account_trades"):
                rows = account.get(key)
                if isinstance(rows, list):
                    for row in rows:
                        if isinstance(row, dict):
                            yield {**base, **row}


def _account_metadata(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    metadata: dict[str, dict[str, Any]] = {}
    accounts = payload.get("accounts")
    if isinstance(accounts, list):
        for account in accounts:
            if not isinstance(account, dict):
                continue
            wallet = str(account.get("wallet") or "").strip()
            if wallet:
                metadata[wallet] = account
    return metadata


def _followed_accounts(payload: dict[str, Any], trades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    accounts: dict[str, dict[str, Any]] = {}
    for wallet, account in _account_metadata(payload).items():
        accounts[wallet] = {
            "wallet": wallet,
            "handle": _clean_optional(account.get("handle") or account.get("name") or account.get("username")),
        }
    for trade in trades:
        wallet = str(trade.get("wallet") or "").strip()
        if wallet:
            accounts.setdefault(wallet, {"wallet": wallet, "handle": _clean_optional(trade.get("handle"))})
    return [account for _, account in sorted(accounts.items())]


def _followed_account_handles(trades_payload: dict[str, Any]) -> dict[str, str | None]:
    handles: dict[str, str | None] = {}
    accounts = trades_payload.get("followed_accounts")
    if isinstance(accounts, list):
        for account in accounts:
            if not isinstance(account, dict):
                continue
            wallet = str(account.get("wallet") or "").strip()
            if wallet:
                handles[wallet] = _clean_optional(account.get("handle"))
    return handles


def _build_profile(wallet: str, rows: list[dict[str, Any]], *, handle: str | None = None) -> ShadowProfile:
    usdcs = [float(row["usdc"]) for row in rows if isinstance(row.get("usdc"), (int, float))]
    observed_usdc = round(sum(usdcs), 2)
    examples = sorted(rows, key=lambda row: float(row.get("usdc") or 0.0), reverse=True)[:5]
    return ShadowProfile(
        wallet=wallet,
        handle=_clean_optional(rows[0].get("handle")) if rows else handle,
        trade_count=len(rows),
        observed_usdc=observed_usdc,
        avg_trade_usdc=round(observed_usdc / len(usdcs), 2) if usdcs else None,
        max_trade_usdc=round(max(usdcs), 2) if usdcs else None,
        sizing_buckets=_counter(rows, "size_bucket"),
        timing_buckets=_counter(rows, "timing_bucket"),
        city_buckets=_counter(rows, "city"),
        type_buckets=_counter(rows, "market_type"),
        side_buckets=_counter(rows, "side"),
        price_buckets=_counter(rows, "price_bucket"),
        abstention_signals=_abstention_signals(rows),
        top_examples=[_example(row) for row in examples],
    )


def _market_shape(title: str, raw: dict[str, Any]) -> tuple[str | None, str | None, str]:
    city = _clean_optional(raw.get("city"))
    date = _clean_optional(raw.get("date") or raw.get("date_local"))
    raw_kind = _clean_optional(raw.get("kind") or raw.get("market_type") or raw.get("type"))
    if city or date or raw_kind:
        return city, date, raw_kind or _fallback_market_type(title)
    try:
        structure = parse_market_question(title)
    except ValueError:
        return None, None, _fallback_market_type(title)
    if structure.is_exact_bin:
        market_type = "exact_bin_or_temp_surface"
    elif structure.is_threshold:
        market_type = "threshold"
    else:
        market_type = structure.measurement_kind
    return structure.city, structure.date_local, market_type


def _fallback_market_type(title: str) -> str:
    normalized = title.lower()
    if " between " in normalized or "exactly" in normalized:
        return "exact_bin_or_temp_surface"
    if " or higher" in normalized or " or below" in normalized or "more than" in normalized or "less than" in normalized:
        return "threshold"
    if any(token in normalized for token in ("temperature", "snow", "rain", "precipitation", "hurricane", "tornado", "storm")):
        return "weather_general"
    return "unknown"


def _timing_bucket(raw: dict[str, Any]) -> str:
    hours = _optional_float(raw.get("hours_to_resolution") or raw.get("lead_time_hours"))
    if hours is None:
        return "historical_unknown"
    if hours < 6:
        return "same_day_close"
    if hours < 24:
        return "same_day"
    if hours < 72:
        return "one_to_three_days"
    return "early"


def _size_bucket(usdc: float | None) -> str:
    if usdc is None:
        return "unknown"
    if usdc < 10:
        return "micro_<10"
    if usdc < 100:
        return "small_10_100"
    if usdc < 1000:
        return "medium_100_1000"
    return "large_1000_plus"


def _price_bucket(price: float | None) -> str:
    if price is None:
        return "unknown"
    cents = price * 100 if price <= 1 else price
    if cents < 10:
        return "0_10c"
    if cents < 25:
        return "10_25c"
    if cents < 50:
        return "25_50c"
    if cents < 75:
        return "50_75c"
    if cents < 90:
        return "75_90c"
    return "90_100c"


def _abstention_signals(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return ["no_public_weather_trades_in_backfill"]
    signals: list[str] = []
    if all(row.get("timing_bucket") == "historical_unknown" for row in rows):
        signals.append("timing_unobservable_from_public_backfill")
    if _counter(rows, "price_bucket").get("unknown") == len(rows):
        signals.append("price_unobservable_from_public_backfill")
    if len(rows) < 3:
        signals.append("sparse_public_weather_sample")
    return signals


def _deep_dive_notes(profile: dict[str, Any]) -> list[str]:
    notes = ["Use as account-learning prior only; do not copy-trade or authorize live orders."]
    notes.append(f"Sizing prior: {_top_bucket(profile.get('sizing_buckets')) or 'unknown'}.")
    notes.append(f"Timing prior: {_top_bucket(profile.get('timing_buckets')) or 'unknown'}.")
    notes.append(f"Market-shape prior: {_top_bucket(profile.get('type_buckets')) or 'unknown'}.")
    if profile.get("abstention_signals"):
        notes.append("Abstention/coverage caveats: " + ", ".join(profile.get("abstention_signals") or []))
    return notes


def _counter(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts = Counter(str(row.get(key) or "unknown") for row in rows)
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def _top_bucket(value: Any) -> str:
    if not isinstance(value, dict) or not value:
        return ""
    key = next(iter(value))
    return f"{key} ({value[key]})"


def _example(row: dict[str, Any]) -> dict[str, Any]:
    return {key: row.get(key) for key in ("title", "side", "price", "usdc", "city", "date", "market_type", "timing_bucket")}


def _compact_trade_import(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "artifact": payload.get("artifact"),
        "trade_count": payload.get("trade_count"),
        "accounts": payload.get("accounts"),
        "paper_only": True,
        "live_order_allowed": False,
        "artifacts": payload.get("artifacts", {}),
    }


def _compact_profile_report(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "artifact": report.get("artifact"),
        "summary": report.get("summary", {}),
        "paper_only": True,
        "live_order_allowed": False,
        "artifacts": report.get("artifacts", {}),
    }


def _account_count(trades: list[dict[str, Any]]) -> int:
    return len({str(trade.get("wallet") or "") for trade in trades if trade.get("wallet")})


def _followed_accounts(payload: dict[str, Any], trades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    followed: dict[str, dict[str, Any]] = {}
    accounts = payload.get("accounts")
    if isinstance(accounts, list):
        for account in accounts:
            if not isinstance(account, dict):
                continue
            wallet = str(account.get("wallet") or "").strip()
            handle = _clean_optional(account.get("handle") or account.get("name") or account.get("username"))
            key = wallet or (f"handle:{handle}" if handle else "")
            if key:
                followed[key] = {"wallet": wallet or key, "handle": handle}
    for trade in trades:
        wallet = str(trade.get("wallet") or "").strip()
        if wallet:
            followed.setdefault(wallet, {"wallet": wallet, "handle": trade.get("handle")})
    return list(followed.values())


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return round(float(value), 4)
    if isinstance(value, str):
        cleaned = re.sub(r"[^0-9.\-]", "", value)
        if not cleaned:
            return None
        try:
            return round(float(cleaned), 4)
        except ValueError:
            return None
    return None


def _clean_optional(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _md(value: Any) -> str:
    return str(value or "").replace("|", "\\|")
