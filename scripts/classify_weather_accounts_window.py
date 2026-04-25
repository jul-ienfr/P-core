from __future__ import annotations

import argparse
import concurrent.futures
import csv
import json
import threading
import time
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any

WEATHER_TERMS = [
    "temperature",
    "weather",
    "rain",
    "snow",
    "hurricane",
    "tornado",
    "wind",
    "degree",
    "degrees",
    "°c",
    "°f",
    "celsius",
    "fahrenheit",
    "highest temperature",
    "low temperature",
    "air quality",
]
NONWEATHER_TERMS = [
    "fifa",
    "nba",
    "nfl",
    "nhl",
    "trump",
    "election",
    "iran",
    "bitcoin",
    "btc",
    "ethereum",
    "ufc",
    "soccer",
    "premier league",
    "senate",
    "president",
    "tariff",
    "fed",
    "oscar",
    "grammy",
]
FIELDNAMES = [
    "rank",
    "userName",
    "proxyWallet",
    "xUsername",
    "weather_pnl_usd",
    "weather_volume_usd",
    "pnl_over_volume_pct",
    "classification",
    "confidence",
    "active_positions",
    "active_weather_positions",
    "active_nonweather_positions",
    "recent_activity",
    "recent_weather_activity",
    "recent_nonweather_activity",
    "sample_weather_titles",
    "sample_nonweather_titles",
    "profile_url",
]
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
    "Accept": "application/json,text/plain,*/*",
    "Origin": "https://polymarket.com",
    "Referer": "https://polymarket.com/leaderboard/weather/all/profit",
}

_done = 0
_lock = threading.Lock()


def _is_weather(title: str | None) -> bool:
    text = (title or "").lower()
    return any(term in text for term in WEATHER_TERMS)


def _is_nonweather(title: str | None) -> bool:
    text = (title or "").lower()
    return any(term in text for term in NONWEATHER_TERMS) and not _is_weather(text)


def _fetch(endpoint: str, wallet: str, limit: int) -> list[dict[str, Any]]:
    params = urllib.parse.urlencode({"user": wallet, "limit": limit})
    req = urllib.request.Request(f"https://data-api.polymarket.com/{endpoint}?{params}", headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _as_title(row: dict[str, Any]) -> str:
    return str(row.get("title") or row.get("slug") or row.get("eventSlug") or "")


def classify_row(row: dict[str, str]) -> dict[str, Any]:
    global _done
    wallet = row["proxyWallet"]
    positions = _fetch("positions", wallet, 100)
    activity = _fetch("activity", wallet, 200)
    pos_weather = [p for p in positions if _is_weather(_as_title(p))]
    pos_non = [p for p in positions if _is_nonweather(_as_title(p))]
    act_weather = [a for a in activity if _is_weather(_as_title(a))]
    act_non = [a for a in activity if _is_nonweather(_as_title(a))]
    weather_signal = len(pos_weather) + len(act_weather)
    non_signal = len(pos_non) + len(act_non)
    if weather_signal >= 10 and non_signal <= weather_signal:
        classification = "weather specialist / weather-heavy"
        confidence = "medium"
    elif weather_signal >= 5:
        classification = "weather-heavy mixed"
        confidence = "medium" if weather_signal >= non_signal else "low"
    elif weather_signal > 0:
        classification = "profitable in weather but currently/recently generalist"
        confidence = "low"
    else:
        classification = "not enough public recent data to classify"
        confidence = "low"
    out = {
        "rank": row.get("rank"),
        "userName": row.get("userName"),
        "proxyWallet": wallet,
        "xUsername": row.get("xUsername"),
        "weather_pnl_usd": row.get("pnl"),
        "weather_volume_usd": row.get("vol"),
        "pnl_over_volume_pct": row.get("pnl_over_volume_pct"),
        "classification": classification,
        "confidence": confidence,
        "active_positions": len(positions),
        "active_weather_positions": len(pos_weather),
        "active_nonweather_positions": len(pos_non),
        "recent_activity": len(activity),
        "recent_weather_activity": len(act_weather),
        "recent_nonweather_activity": len(act_non),
        "sample_weather_titles": " | ".join((_as_title(x) for x in (pos_weather + act_weather)[:5])),
        "sample_nonweather_titles": " | ".join((_as_title(x) for x in (pos_non + act_non)[:5])),
        "profile_url": row.get("profile_url") or ("https://polymarket.com/profile/" + wallet),
    }
    with _lock:
        _done += 1
        if _done % 100 == 0:
            print(f"classified {_done}", flush=True)
    return out


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def _rank(row: dict[str, Any]) -> int:
    try:
        return int(float(row.get("rank") or 999999999))
    except ValueError:
        return 999999999


def _existing_classified_limit(path: Path, *, fallback: int) -> int:
    stem = path.stem
    marker = "_top"
    if marker in stem:
        suffix = stem.rsplit(marker, 1)[-1]
        try:
            return int(suffix)
        except ValueError:
            pass
    try:
        return len(_read_csv(path))
    except Exception:
        return fallback


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="/home/jul/prediction_core")
    parser.add_argument("--limit", type=int, default=2000)
    parser.add_argument("--workers", type=int, default=16)
    args = parser.parse_args()

    base = Path(args.base)
    full_csv = base / "data/polymarket/weather_profitable_accounts.csv"
    data_dir = base / "data/polymarket"
    existing_candidates = list(data_dir.glob("weather_profitable_accounts_classified_top*.csv")) + [
        data_dir / "weather_profitable_accounts_classified.csv",
    ]
    existing_candidates = [p for p in existing_candidates if p.exists()]
    existing_path = max(
        existing_candidates,
        key=lambda p: _existing_classified_limit(p, fallback=0),
    )
    out_csv = base / f"data/polymarket/weather_profitable_accounts_classified_top{args.limit}.csv"
    out_json = base / f"data/polymarket/weather_profitable_accounts_classified_top{args.limit}_summary.json"

    full = _read_csv(full_csv)
    existing = _read_csv(existing_path)
    existing_by_wallet = {str(r.get("proxyWallet") or ""): r for r in existing}
    target = full[: args.limit]
    results: list[dict[str, Any]] = []
    to_fetch: list[dict[str, str]] = []
    for row in target:
        wallet = str(row.get("proxyWallet") or "")
        if wallet in existing_by_wallet:
            results.append(existing_by_wallet[wallet])
        else:
            to_fetch.append(row)
    print(json.dumps({"target": len(target), "existing_path": str(existing_path), "reuse_existing": len(results), "to_fetch": len(to_fetch)}, ensure_ascii=False), flush=True)
    started = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = [ex.submit(classify_row, row) for row in to_fetch]
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())
    results.sort(key=_rank)
    with out_csv.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(results)
    counts = Counter(str(r.get("classification") or "unknown") for r in results)
    weather_heavy = [r for r in results if "weather-heavy" in str(r.get("classification")) or "specialist" in str(r.get("classification"))]
    summary = {
        "source_full_csv": str(full_csv),
        "existing_path": str(existing_path),
        "output_csv": str(out_csv),
        "rank_window": f"1-{args.limit}",
        "classified_count": len(results),
        "newly_enriched_count": len(to_fetch),
        "elapsed_seconds": round(time.time() - started, 2),
        "classification_counts": dict(sorted(counts.items())),
        "weather_heavy_or_specialist_count": len(weather_heavy),
        "top_newly_classified_weather_heavy": [
            {
                "rank": r.get("rank"),
                "handle": r.get("userName"),
                "pnl": float(r.get("weather_pnl_usd") or 0),
                "class": r.get("classification"),
                "active_weather": int(float(r.get("active_weather_positions") or 0)),
                "recent_weather": int(float(r.get("recent_weather_activity") or 0)),
                "profile": r.get("profile_url"),
            }
            for r in weather_heavy
            if _rank(r) > args.limit // 2
        ][:20],
    }
    out_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
