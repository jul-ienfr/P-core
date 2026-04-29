from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from weather_pm.account_trades import classify_weather_trade


def build_trade_no_trade_dataset(
    weather_trades: Iterable[dict[str, Any]],
    markets: Iterable[dict[str, Any]],
    *,
    accounts: Iterable[str | dict[str, Any]] | None = None,
) -> dict[str, Any]:
    trades = [_normalize_trade(row) for row in weather_trades]
    market_rows = [_normalize_market(row) for row in markets]
    account_rows = _normalize_accounts(accounts, trades)
    trade_index = _trade_index(trades)
    examples: list[dict[str, Any]] = []
    for account_meta in account_rows:
        account = account_meta["wallet"]
        for market in market_rows:
            trade = trade_index.get((account, market["surface_key"], market["weather_market_type"]))
            examples.append(_dataset_row(account_meta, market, trade))
    trade_examples = sum(1 for row in examples if row["label"] == "trade")
    return {
        "source": "polymarket_weather_account_trades",
        "paper_only": True,
        "live_order_allowed": False,
        "summary": {
            "accounts": len(account_rows),
            "markets": len(market_rows),
            "examples": len(examples),
            "trade_examples": trade_examples,
            "no_trade_examples": len(examples) - trade_examples,
            "paper_only": True,
            "live_order_allowed": False,
        },
        "examples": examples,
    }


def build_promoted_profile_opportunity_dataset(promoted_profiles: dict[str, Any], markets: Iterable[dict[str, Any]]) -> dict[str, Any]:
    profiles = _promoted_profile_accounts(promoted_profiles)
    market_rows = [_normalize_market(row) for row in markets]
    examples: list[dict[str, Any]] = []
    for profile in profiles:
        for market in market_rows:
            row = _dataset_row(profile, market, None)
            row.update(
                {
                    "label": "trade",
                    "abstention_reason": None,
                    "shadow_signal_source": "promoted_profile_opportunity_watch",
                    "profile_id": profile.get("profile_id") or profile.get("wallet") or profile.get("handle") or "promoted_shadow_profile",
                    "suggested_min_edge": profile.get("suggested_min_edge"),
                    "suggested_max_order_usdc": profile.get("suggested_max_order_usdc"),
                }
            )
            examples.append(row)
    return {
        "source": "polymarket_weather_promoted_profile_opportunities",
        "paper_only": True,
        "live_order_allowed": False,
        "summary": {
            "accounts": len(profiles),
            "markets": len(market_rows),
            "examples": len(examples),
            "trade_examples": len(examples),
            "no_trade_examples": 0,
            "promoted_profiles": len(profiles),
            "paper_only": True,
            "live_order_allowed": False,
        },
        "examples": examples,
    }


def load_followlist_accounts(accounts_csv: str | Path, *, limit: int | None = None) -> list[dict[str, Any]]:
    """Load selected top accounts from a weather followlist CSV.

    The loader is read-only/paper-only: it only parses local CSV rows and keeps
    ranking metadata for downstream no-trade expansion.
    """
    with Path(accounts_csv).open("r", encoding="utf-8", newline="") as handle:
        rows = [_normalize_account(row) for row in csv.DictReader(handle)]
    rows = [row for row in rows if row.get("wallet")]
    rows.sort(key=_account_sort_key)
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        wallet = str(row.get("wallet") or "")
        if wallet and wallet not in seen:
            seen.add(wallet)
            deduped.append(row)
        if limit is not None and len(deduped) >= limit:
            break
    return deduped


def build_shadow_profile_operator_report(dataset: dict[str, Any], *, limit: int = 10) -> dict[str, Any]:
    examples = [row for row in dataset.get("examples", []) if isinstance(row, dict)]
    by_account: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in examples:
        by_account[str(row.get("wallet") or "")].append(row)
    profiles = [_profile_from_examples(wallet, rows) for wallet, rows in by_account.items()]
    profiles.sort(key=lambda row: (row["trade_count"], row["total_trade_notional_usd"]), reverse=True)
    profiles = profiles[:limit]
    return {
        "source": "polymarket_weather_shadow_profiles",
        "paper_only": True,
        "live_order_allowed": False,
        "summary": {
            **dict(dataset.get("summary") or {}),
            "shadow_profile_count": len(profiles),
            "paper_only": True,
            "live_order_allowed": False,
        },
        "profiles": profiles,
        "operator_next_actions": [
            "compare_trade_vs_no_trade_surfaces",
            "backtest_shadow_profiles_before_any_execution",
            "keep_profitable_accounts_as_radar_not_copytrade",
        ],
        "discord_brief": _discord_brief(profiles),
    }


def build_learned_shadow_patterns_report(dataset: dict[str, Any], *, limit: int = 20) -> dict[str, Any]:
    examples = [row for row in dataset.get("examples", []) if isinstance(row, dict)]
    by_account: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in examples:
        wallet = str(row.get("wallet") or "")
        if wallet:
            by_account[wallet].append(row)
    patterns = [_learned_pattern_from_examples(wallet, rows) for wallet, rows in by_account.items()]
    patterns.sort(key=lambda row: (_priority_sort(row["replay_priority"]), row["trade_count"], row["avg_trade_notional_usd"]), reverse=True)
    patterns = patterns[: max(0, int(limit))]
    trade_examples = sum(1 for row in examples if row.get("label") == "trade")
    no_trade_examples = sum(1 for row in examples if row.get("label") == "no_trade")
    summary = {
        "accounts": len(by_account),
        "examples": len(examples),
        "trade_examples": trade_examples,
        "no_trade_examples": no_trade_examples,
        "abstention_rate": _rate(no_trade_examples, len(examples)),
        "paper_only": True,
        "live_order_allowed": False,
    }
    report = {
        "source": "polymarket_weather_learned_shadow_patterns",
        "paper_only": True,
        "live_order_allowed": False,
        "summary": summary,
        "learned_patterns": patterns,
        "operator_next_actions": [
            "Use learned patterns as research prompts for independent forecast and orderbook confirmation.",
            "Run paper replay only; keep paper_only=true and live_order_allowed=false.",
            "Check city/date surfaces against current resolution rules before any simulated order.",
            "Review caveats for sparse samples and abstention-heavy accounts before prioritizing replay.",
        ],
    }
    report["discord_markdown"] = learned_shadow_patterns_markdown(report)
    return report


def write_learned_shadow_patterns_artifacts(
    *,
    dataset_json: str | Path,
    output_json: str | Path,
    output_md: str | Path | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    payload = json.loads(Path(dataset_json).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("dataset JSON must be an object")
    report = build_learned_shadow_patterns_report(payload, limit=limit)
    output_path = Path(output_json)
    report.setdefault("artifacts", {})["dataset_json"] = str(dataset_json)
    report["artifacts"]["output_json"] = str(output_path)
    if output_md:
        report["artifacts"]["output_md"] = str(output_md)
    _write_json(output_path, report)
    if output_md:
        md_path = Path(output_md)
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(learned_shadow_patterns_markdown(report), encoding="utf-8")
    return {"summary": report["summary"], "artifacts": {key: value for key, value in report["artifacts"].items() if key in {"output_json", "output_md"}}}


def learned_shadow_patterns_markdown(report: dict[str, Any]) -> str:
    summary = dict(report.get("summary") or {})
    lines = [
        "# Learned Weather Shadow Patterns",
        f"Safety: paper replay only; live_order_allowed={summary.get('live_order_allowed', False)}.",
        f"Accounts={summary.get('accounts', 0)} examples={summary.get('examples', 0)} trades={summary.get('trade_examples', 0)} abstention_rate={summary.get('abstention_rate', 0)}",
        "",
    ]
    for row in [item for item in report.get("learned_patterns", []) if isinstance(item, dict)]:
        name = row.get("handle") or row.get("wallet") or "unknown"
        cities = ", ".join(str(city.get("city")) for city in row.get("top_cities", [])[:3] if isinstance(city, dict)) or "n/a"
        types = ", ".join(str(item.get("market_type")) for item in row.get("market_type_bias", [])[:3] if isinstance(item, dict)) or "n/a"
        lines.append(
            f"- **{name}** `{row.get('wallet', '')}`: {row.get('behavioral_profile')} / {row.get('profile_archetype')}; "
            f"trades={row.get('trade_count', 0)}, no-trades={row.get('no_trade_count', 0)}, avg_px={row.get('avg_entry_price', 0)}, "
            f"avg_notional=${row.get('avg_trade_notional_usd', 0)}, cities={cities}, types={types}, priority={row.get('replay_priority')}"
        )
    lines.extend([
        "",
        "Next: confirm any candidate with independent forecast checks and orderbook/liquidity review before paper simulation.",
    ])
    return "\n".join(lines) + "\n"


def write_promoted_profile_opportunity_dataset_artifact(
    *,
    promoted_profiles_json: str | Path,
    markets_json: str | Path,
    dataset_out: str | Path,
) -> dict[str, Any]:
    promoted_profiles = json.loads(Path(promoted_profiles_json).read_text(encoding="utf-8"))
    markets = _load_rows(markets_json, ("markets", "opportunities", "data", "results"))
    dataset = build_promoted_profile_opportunity_dataset(promoted_profiles if isinstance(promoted_profiles, dict) else {}, markets)
    dataset_path = Path(dataset_out)
    dataset.setdefault("artifacts", {})["dataset"] = str(dataset_path)
    _write_json(dataset_path, dataset)
    return {"summary": dataset["summary"], "artifacts": {"dataset": str(dataset_path)}}


def write_shadow_profile_artifacts(
    *,
    weather_trades_json: str | Path,
    markets_json: str | Path,
    dataset_out: str | Path,
    report_out: str | Path,
    limit: int = 10,
    accounts_csv: str | Path | None = None,
    limit_accounts: int | None = None,
) -> dict[str, Any]:
    trades = _load_rows(weather_trades_json, ("trades", "data", "results"))
    markets = _load_rows(markets_json, ("markets", "opportunities", "data", "results"))
    accounts = load_followlist_accounts(accounts_csv, limit=limit_accounts) if accounts_csv else None
    dataset = build_trade_no_trade_dataset(trades, markets, accounts=accounts)
    report = build_shadow_profile_operator_report(dataset, limit=limit)
    dataset_path = Path(dataset_out)
    report_path = Path(report_out)
    _write_json(dataset_path, dataset)
    report.setdefault("artifacts", {})["dataset"] = str(dataset_path)
    report.setdefault("artifacts", {})["report"] = str(report_path)
    _write_json(report_path, report)
    return {"summary": report["summary"], "artifacts": {"dataset": str(dataset_path), "report": str(report_path)}}


def _normalize_trade(row: dict[str, Any]) -> dict[str, Any]:
    if "is_weather" in row and "weather_market_type" in row:
        return dict(row)
    return classify_weather_trade(row).to_dict()


def _normalize_market(row: dict[str, Any]) -> dict[str, Any]:
    question = str(row.get("question") or row.get("title") or row.get("market_title") or "")
    classified = classify_weather_trade({"title": question, "slug": row.get("slug") or row.get("market_slug") or ""})
    city = str(row.get("city") or classified.city or "")
    date = str(row.get("date") or row.get("resolution_date") or "")
    market_type = str(row.get("weather_market_type") or classified.weather_market_type)
    return {
        "market_id": str(row.get("market_id") or row.get("id") or row.get("conditionId") or question),
        "question": question,
        "city": city,
        "date": date,
        "surface_key": _surface_key(city, date, question),
        "weather_market_type": market_type,
        "yes_price": _to_float(row.get("yes_price") or row.get("price") or row.get("market_price")),
        "model_probability": _to_float(row.get("model_probability") or row.get("probability") or row.get("fair_probability")),
    }


def _dataset_row(account_meta: dict[str, Any], market: dict[str, Any], trade: dict[str, Any] | None) -> dict[str, Any]:
    metadata = _followlist_metadata(account_meta)
    base = {
        "wallet": account_meta["wallet"],
        "market_id": market["market_id"],
        "question": market["question"],
        "city": market["city"],
        "date": market["date"],
        "surface_key": market["surface_key"],
        "weather_market_type": market["weather_market_type"],
        "yes_price": market["yes_price"],
        "model_probability": market["model_probability"],
        **metadata,
        "paper_only": True,
        "live_order_allowed": False,
    }
    if trade:
        return {
            **base,
            "label": "trade",
            "handle": metadata.get("handle") or str(trade.get("handle") or ""),
            "account_trade_count": int(trade.get("trade_count") or 1),
            "account_first_trade_timestamp": str(trade.get("first_timestamp") or trade.get("timestamp") or ""),
            "account_last_trade_timestamp": str(trade.get("last_timestamp") or trade.get("timestamp") or ""),
            "account_trade_price": _to_float(trade.get("avg_price", trade.get("price"))),
            "account_trade_size": _to_float(trade.get("total_size", trade.get("size"))),
            "account_trade_notional_usd": _to_float(trade.get("total_notional_usd", trade.get("notional_usd"))),
            "abstention_reason": None,
        }
    return {
        **base,
        "label": "no_trade",
        "handle": metadata.get("handle") or "",
        "account_trade_count": 0,
        "account_first_trade_timestamp": "",
        "account_last_trade_timestamp": "",
        "account_trade_price": 0.0,
        "account_trade_size": 0.0,
        "account_trade_notional_usd": 0.0,
        "abstention_reason": "no_account_trade_on_surface",
    }


def _promoted_profile_accounts(promoted_profiles: dict[str, Any]) -> list[dict[str, Any]]:
    rows = promoted_profiles.get("profiles") if isinstance(promoted_profiles.get("profiles"), list) else []
    accounts: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict) or row.get("recommendation") != "promote_to_paper_profile":
            continue
        account = _normalize_account(row)
        account["profile_id"] = str(row.get("profile_id") or account.get("wallet") or account.get("handle") or "promoted_shadow_profile")
        account["suggested_min_edge"] = _to_float(row.get("suggested_min_edge")) if row.get("suggested_min_edge") is not None else None
        account["suggested_max_order_usdc"] = _to_float(row.get("suggested_max_order_usdc")) if row.get("suggested_max_order_usdc") is not None else None
        key = str(account.get("wallet") or account.get("handle") or account.get("profile_id") or "").lower()
        if key and key not in seen:
            seen.add(key)
            accounts.append(account)
    return accounts


def _normalize_accounts(accounts: Iterable[str | dict[str, Any]] | None, trades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if accounts is None:
        return [_normalize_account({"wallet": wallet}) for wallet in _accounts_from_trades(trades)]
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for account in accounts:
        row = _normalize_account(account if isinstance(account, dict) else {"wallet": account})
        wallet = str(row.get("wallet") or "")
        if wallet and wallet not in seen:
            seen.add(wallet)
            normalized.append(row)
    return normalized


def _normalize_account(row: dict[str, Any]) -> dict[str, Any]:
    wallet = str(row.get("wallet") or row.get("proxyWallet") or row.get("address") or "").strip()
    return {
        "wallet": wallet,
        "handle": str(row.get("handle") or row.get("userName") or row.get("name") or "").strip(),
        "bucket": str(row.get("bucket") or row.get("tier") or "").strip(),
        "rank": int(_to_float(row.get("rank"))) if str(row.get("rank") or "").strip() else 0,
        "score": _to_float(row.get("score")),
        "profile_url": str(row.get("profile_url") or row.get("profileUrl") or "").strip(),
    }


def _account_sort_key(row: dict[str, Any]) -> tuple[int, float, str]:
    rank = int(row.get("rank") or 0)
    rank_key = rank if rank > 0 else 10**9
    return (rank_key, -_to_float(row.get("score")), str(row.get("wallet") or ""))


def _followlist_metadata(account_meta: dict[str, Any]) -> dict[str, Any]:
    return {key: account_meta.get(key) for key in ("handle", "bucket", "rank", "score", "profile_url") if account_meta.get(key) not in (None, "", 0)}


def _summarize_trade_hits(rows: list[dict[str, Any]]) -> dict[str, Any]:
    first = dict(rows[0]) if rows else {}
    notionals = [_to_float(row.get("notional_usd")) for row in rows]
    sizes = [_to_float(row.get("size")) for row in rows]
    prices = [_to_float(row.get("price")) for row in rows]
    timestamps = sorted(str(row.get("timestamp") or "") for row in rows if row.get("timestamp"))
    first["trade_count"] = len(rows)
    first["total_notional_usd"] = round(sum(notionals), 6)
    first["total_size"] = round(sum(sizes), 6)
    first["avg_price"] = round(sum(prices) / len(prices), 6) if prices else 0.0
    if timestamps:
        first["first_timestamp"] = timestamps[0]
        first["last_timestamp"] = timestamps[-1]
    return first


def _profile_from_examples(wallet: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    trades = [row for row in rows if row.get("label") == "trade"]
    no_trades = [row for row in rows if row.get("label") == "no_trade"]
    type_counts = Counter(str(row.get("weather_market_type") or "unknown") for row in trades)
    total_notional = round(sum(_to_float(row.get("account_trade_notional_usd")) for row in trades), 6)
    return {
        "wallet": wallet,
        "handle": _first_non_empty(str(row.get("handle") or "") for row in trades),
        "behavioral_profile": _behavioral_profile(type_counts),
        "trade_count": len(trades),
        "no_trade_count": len(no_trades),
        "total_trade_notional_usd": total_notional,
        "avg_trade_notional_usd": round(total_notional / len(trades), 6) if trades else 0.0,
        "weather_market_type_counts": dict(type_counts),
        "top_trade_surfaces": _top_surfaces(trades),
        "paper_only": True,
        "live_order_allowed": False,
    }


def _learned_pattern_from_examples(wallet: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    trades = [row for row in rows if row.get("label") == "trade"]
    no_trades = [row for row in rows if row.get("label") == "no_trade"]
    total_notional = sum(_to_float(row.get("account_trade_notional_usd")) for row in trades)
    avg_entry = sum(_to_float(row.get("account_trade_price")) for row in trades) / len(trades) if trades else 0.0
    type_counts = Counter(str(row.get("weather_market_type") or "unknown") for row in trades)
    profile = _behavioral_profile(type_counts)
    return {
        "wallet": wallet,
        "handle": _first_non_empty(str(row.get("handle") or "") for row in trades),
        "behavioral_profile": profile,
        "profile_archetype": _profile_archetype(profile, trades, no_trades),
        "trade_count": len(trades),
        "no_trade_count": len(no_trades),
        "avg_entry_price": round(avg_entry, 6),
        "avg_trade_notional_usd": round(total_notional / len(trades), 6) if trades else 0.0,
        "top_cities": _city_bias(rows),
        "market_type_bias": [{"market_type": key, "trade_count": count} for key, count in type_counts.most_common(5) if key],
        "timing": _timing_surface(trades),
        "city_date_surfaces": _city_date_surfaces(trades),
        "abstention_rate": _rate(len(no_trades), len(rows)),
        "confidence": _pattern_confidence(len(trades), len(rows)),
        "replay_priority": _replay_priority(len(trades), len(rows), total_notional),
        "caveats": _pattern_caveats(trades, no_trades),
        "paper_only": True,
        "live_order_allowed": False,
    }


def _city_bias(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cities = sorted({str(row.get("city") or "") for row in rows if row.get("city")})
    ranked = []
    for city in cities:
        city_rows = [row for row in rows if str(row.get("city") or "") == city]
        trade_count = sum(1 for row in city_rows if row.get("label") == "trade")
        no_trade_count = sum(1 for row in city_rows if row.get("label") == "no_trade")
        if trade_count:
            ranked.append({"city": city, "trade_count": trade_count, "no_trade_count": no_trade_count})
    ranked.sort(key=lambda row: (row["trade_count"], -row["no_trade_count"], row["city"]), reverse=True)
    return ranked[:5]


def _city_date_surfaces(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts = Counter((str(row.get("city") or ""), str(row.get("date") or "")) for row in rows)
    return [{"city": city, "date": date, "trade_count": count} for (city, date), count in counts.most_common(5) if city or date]


def _timing_surface(rows: list[dict[str, Any]]) -> dict[str, Any]:
    dates = Counter(str(row.get("date") or "unknown") for row in rows)
    return {"top_resolution_dates": [{"date": key, "trade_count": count} for key, count in dates.most_common(3) if key]}


def _profile_archetype(profile: str, trades: list[dict[str, Any]], no_trades: list[dict[str, Any]]) -> str:
    if not trades:
        return "observer_abstainer"
    abstention = _rate(len(no_trades), len(trades) + len(no_trades))
    if abstention >= 0.67:
        return "selective_surface_specialist"
    if profile == "threshold_harvester":
        return "threshold_bias_replayer"
    if len({str(row.get("city") or "") for row in trades}) <= 1:
        return "city_surface_specialist"
    return "multi_surface_weather_replayer"


def _pattern_confidence(trade_count: int, total_count: int) -> str:
    if trade_count >= 5 and total_count >= 8:
        return "high"
    if trade_count >= 2:
        return "medium"
    if trade_count == 1:
        return "low"
    return "none"


def _replay_priority(trade_count: int, total_count: int, total_notional: float) -> str:
    if trade_count >= 2 and total_notional >= 25 and _rate(trade_count, total_count) >= 0.25:
        return "high"
    if trade_count >= 1:
        return "medium"
    return "low"


def _priority_sort(priority: str) -> int:
    return {"low": 1, "medium": 2, "high": 3}.get(priority, 0)


def _pattern_caveats(trades: list[dict[str, Any]], no_trades: list[dict[str, Any]]) -> list[str]:
    caveats = ["Historical behavior only; confirm current forecast, rules, liquidity, and orderbook independently."]
    if len(trades) < 3:
        caveats.append("Sparse trade sample; treat pattern confidence conservatively.")
    if no_trades and _rate(len(no_trades), len(trades) + len(no_trades)) >= 0.5:
        caveats.append("High abstention rate; replay should model pass/no-trade decisions as strongly as entries.")
    return caveats


def _rate(numerator: int, denominator: int) -> float:
    return round(float(numerator) / float(denominator), 6) if denominator else 0.0


def _trade_index(trades: list[dict[str, Any]]) -> dict[tuple[str, str, str], dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for trade in trades:
        if not trade.get("is_weather"):
            continue
        city = str(trade.get("city") or "")
        title = str(trade.get("title") or "")
        keys = {_surface_key(city, "", title)}
        date = _date_from_title(title)
        if city and date:
            keys.add(_surface_key(city, date, title))
        for surface_key in keys:
            key = (str(trade.get("wallet") or ""), surface_key, str(trade.get("weather_market_type") or ""))
            grouped[key].append(trade)
    return {key: _summarize_trade_hits(rows) for key, rows in grouped.items()}


def _surface_key(city: str, date: str, question: str) -> str:
    if city and date:
        return f"{city.lower()}|{date.lower()}"
    if city:
        return city.lower()
    return question.lower()


def _date_from_title(title: str) -> str:
    match = __import__("re").search(r" on (?P<date>[A-Za-z]+\s+\d{1,2})(?:\?|$)", title)
    return match.group("date") if match else ""


def _normalize_accounts(accounts: Iterable[str | dict[str, Any]] | None, trades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    raw_accounts: Iterable[str | dict[str, Any]] = accounts if accounts is not None else _accounts_from_trades(trades)
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for account in raw_accounts:
        row = _normalize_account(account)
        wallet = str(row.get("wallet") or "")
        if wallet and wallet not in seen:
            seen.add(wallet)
            normalized.append(row)
    return normalized


def _normalize_account(row: str | dict[str, Any]) -> dict[str, Any]:
    if not isinstance(row, dict):
        return {"wallet": str(row)}
    wallet = str(_first_value(row, "wallet", "proxyWallet", "proxy_wallet", "address", "account", "user") or "")
    normalized: dict[str, Any] = {"wallet": wallet}
    handle = str(_first_value(row, "handle", "userName", "username", "name") or "")
    if handle:
        normalized["handle"] = handle
    bucket = str(_first_value(row, "bucket", "tier", "group", "category") or "")
    if bucket:
        normalized["bucket"] = bucket
    rank_value = _first_value(row, "rank", "ranking", "position")
    if rank_value not in (None, ""):
        normalized["rank"] = _to_int(rank_value)
    score_value = _first_value(row, "score", "follow_score", "pnl_score", "total_score")
    if score_value not in (None, ""):
        normalized["score"] = _to_float(score_value)
    profile_url = str(_first_value(row, "account_profile_url", "profile_url", "profileUrl", "url") or "")
    if profile_url:
        normalized["account_profile_url"] = profile_url
    return normalized


def _followlist_metadata(account_meta: dict[str, Any]) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    for key in ("handle", "bucket", "rank", "score", "account_profile_url"):
        if key in account_meta:
            metadata[key] = account_meta[key]
    return metadata


def _account_sort_key(row: dict[str, Any]) -> tuple[int, int, float, str]:
    has_rank = 0 if row.get("rank") not in (None, "") else 1
    rank = _to_int(row.get("rank")) if has_rank == 0 else 10**12
    return (has_rank, rank, -_to_float(row.get("score")), str(row.get("wallet") or ""))


def _first_value(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in row and row[key] not in (None, ""):
            return row[key]
    lowered = {str(key).lower(): value for key, value in row.items()}
    for key in keys:
        value = lowered.get(key.lower())
        if value not in (None, ""):
            return value
    return None


def _summarize_trade_hits(rows: list[dict[str, Any]]) -> dict[str, Any]:
    first = dict(rows[0])
    timestamps = sorted(str(row.get("timestamp") or "") for row in rows if row.get("timestamp"))
    total_notional = round(sum(_to_float(row.get("notional_usd")) for row in rows), 6)
    total_size = round(sum(_to_float(row.get("size")) for row in rows), 6)
    weighted_price = total_notional / total_size if total_size else sum(_to_float(row.get("price")) for row in rows) / len(rows)
    first.update(
        {
            "trade_count": len(rows),
            "first_timestamp": timestamps[0] if timestamps else "",
            "last_timestamp": timestamps[-1] if timestamps else "",
            "total_notional_usd": total_notional,
            "total_size": total_size,
            "avg_price": round(weighted_price, 6),
        }
    )
    return first


def _accounts_from_trades(trades: list[dict[str, Any]]) -> list[str]:
    seen: list[str] = []
    for trade in trades:
        wallet = str(trade.get("wallet") or "")
        if wallet and wallet not in seen:
            seen.append(wallet)
    return seen


def _behavioral_profile(type_counts: Counter[str]) -> str:
    if not type_counts:
        return "abstention_only"
    if type_counts.get("macro_weather", 0) >= max(type_counts.values()):
        return "macro_weather_event_trader"
    if type_counts.get("threshold", 0) > type_counts.get("exact_value", 0) + type_counts.get("exact_range", 0):
        return "threshold_harvester"
    return "surface_grid_accumulator"


def _top_surfaces(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts = Counter(str(row.get("surface_key") or "") for row in rows)
    return [{"surface_key": key, "count": count} for key, count in counts.most_common(5) if key]


def _discord_brief(profiles: list[dict[str, Any]]) -> str:
    top = profiles[0] if profiles else {}
    return f"Shadow profiles météo: {len(profiles)} comptes, top={top.get('handle') or top.get('wallet') or 'n/a'}, mode paper-only."


def _load_rows(path: str | Path, keys: tuple[str, ...]) -> list[dict[str, Any]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in keys:
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
    raise ValueError(f"JSON {path} must be a list or contain one of {keys}")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _first_non_empty(values: Iterable[str]) -> str:
    for value in values:
        if value:
            return value
    return ""


def _to_int(value: Any) -> int:
    if value is None:
        return 0
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _to_float(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
