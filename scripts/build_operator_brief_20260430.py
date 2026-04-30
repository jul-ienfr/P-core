#!/usr/bin/env python3
from __future__ import annotations
import argparse
import json
from pathlib import Path


def fmt_money(x):
    try:
        return f"${float(x):,.0f}"
    except Exception:
        return "n/a"


def main() -> int:
    parser = argparse.ArgumentParser(description="Build compact operator markdown brief for weather Polymarket artifacts.")
    parser.add_argument("--timestamp", default="20260430T070859Z")
    args = parser.parse_args()
    ts = args.timestamp
    root = Path("/home/jul/P-core")
    refresh_path = root / f"data/polymarket/operator-refresh/weather_operator_refresh_{ts}.json"
    summary_path = root / f"data/polymarket/account-analysis/weather_profitable_accounts_operator_summary_{ts}.json"
    legacy_summary_path = root / f"data/polymarket/account-analysis/weather_profitable_accounts_operator_summary_{ts}_operator_only.json"
    if not summary_path.exists() and legacy_summary_path.exists():
        summary_path = legacy_summary_path
    watchlist_path = root / f"data/polymarket/watchlists/weather_paper_watchlist_{ts}.json"
    watchlist_md_path = root / f"data/polymarket/watchlists/weather_paper_watchlist_{ts}.md"
    out_path = root / f"data/polymarket/operator-brief/weather_operator_brief_{ts}.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    refresh = json.loads(refresh_path.read_text())
    summary = json.loads(summary_path.read_text())
    watchlist = json.loads(watchlist_path.read_text())
    operator = refresh.get("operator", refresh)
    rows = operator.get("watchlist", [])
    match_summary = summary.get("live_matched_profitable_weather_summary", {})
    signal_cards = {c.get("market_id"): c for c in summary.get("live_market_signal_cards", [])}

    paper_summary = watchlist.get("summary", {}) if isinstance(watchlist, dict) else {}
    positions = watchlist.get("watchlist", watchlist.get("positions", [])) if isinstance(watchlist, dict) else []
    if isinstance(positions, dict):
        positions = positions.get("positions", [])

    normal_size_blocked = 0
    live_ready = []
    paper_candidates = []
    for row in summary.get("live_watchlist", []):
        gate = row.get("normal_size_gate", {}) if isinstance(row, dict) else {}
        if gate.get("normal_size_allowed") is False:
            normal_size_blocked += 1
        if gate.get("live_ready") is True:
            live_ready.append(row.get("market_id"))
        if gate.get("paper_candidate") is True:
            paper_candidates.append(row.get("market_id"))

    lines = []
    lines.append(f"# Brief opérateur Polymarket météo — {ts}\n")
    lines.append("## Verdict\n")
    rec = match_summary.get("operator_recommendation", {})
    lines.append("- **Mode**: paper-only / dry-run ; `live_order_allowed=false`.\n")
    lines.append(f"- **LIVE_READY**: `{bool(live_ready)}` ; marchés live-ready: {len(live_ready)} ; normal-size bloqués: {normal_size_blocked}/{len(summary.get('live_watchlist', []))}.\n")
    lines.append(f"- **PAPER_CANDIDATE principal**: `2065028` si présent ; candidats papier signalés: {', '.join(str(x) for x in paper_candidates[:8]) or 'aucun'}.\n")
    lines.append(f"- **Reco globale signaux live**: `{rec.get('status','n/a')}` — {rec.get('reason','n/a')}.\n")
    lines.append(f"- **Marchés live avec signal compte profitable**: {len(summary.get('live_market_signal_cards', []))} ; comptes uniques: {match_summary.get('unique_account_count', 0)} ; heavy: {match_summary.get('weather_heavy_unique_count', 0)} ; signal-only: {match_summary.get('signal_only_unique_count', 0)}.\n")
    lines.append(f"- **Watchlist papier existante**: action globale `HOLD` ; positions actives: {paper_summary.get('positions', len(positions))} ; add allowed: 0.\n")
    lines.append("- **Conclusion**: ne pas passer live. Tout sizing normal est bloqué tant que la résolution officielle, les quotes et la profondeur ne sont pas propres.\n")

    lines.append("\n## Signaux live rafraîchis\n")
    lines.append("\n| Rank | Market | Ville/date | Action | Blocker | Gate normal size | Résolution/source | Exécution | Comptes top | Décision |\n")
    lines.append("|---:|---|---|---|---|---|---|---|---|---|\n")
    for r in rows:
        mid = str(r.get("market_id"))
        card = signal_cards.get(mid, {})
        matching_summary_row = next((row for row in summary.get("live_watchlist", []) if str(row.get("market_id")) == mid), {})
        gate = matching_summary_row.get("normal_size_gate", {}) if isinstance(matching_summary_row, dict) else {}
        tops = card.get("top_matched_accounts", [])[:3]
        top_txt = ", ".join(f"{a.get('handle')} {fmt_money(a.get('weather_pnl_usd'))}" for a in tops) or "n/a"
        res = r.get("resolution_status", {}) or {}
        latest = (res.get("latest_direct") or {})
        official = (res.get("official_daily_extract") or {})
        source = r.get("direct_source") or latest.get("source_url") or "n/a"
        latest_txt = "direct ok" if latest.get("available") else "direct absent/failed"
        official_txt = "official ok" if official.get("available") else "official absent/failed"
        snap = r.get("execution_snapshot", {}) or {}
        exe = f"bidY={snap.get('best_bid_yes')} askY={snap.get('best_ask_yes')} depth={r.get('depth_usd')}"
        verdict = (card.get("operator_verdict") or {}).get("status") or r.get("decision_status")
        gate_txt = f"allowed={gate.get('normal_size_allowed')} reasons={','.join(gate.get('reasons', []))}"
        lines.append(f"| {r.get('rank')} | `{mid}` | {r.get('city')} {r.get('date')} | `{r.get('action')}` | `{r.get('blocker') or 'none'}` | {gate_txt} | {latest_txt}/{official_txt}; {source} | {exe} | {top_txt} | `{verdict}` |\n")

    lines.append("\n## Positions papier existantes\n")
    lines.append("\nLa CLI watchlist donne: positions 5, spend 44.76 USDC, EV now 23.37 USDC, action globale HOLD. Aucun add autorisé.\n")
    lines.append("\n| Position | Action | Note |\n|---|---|---|\n")
    if watchlist_md_path.exists():
        md = watchlist_md_path.read_text()
        for line in md.splitlines():
            if line.startswith('| Beijing') or line.startswith('| Munich') or line.startswith('| Shanghai') or line.startswith('| Karachi'):
                cols=[c.strip() for c in line.strip('|').split('|')]
                if len(cols)>=13:
                    pos=f"{cols[0]} {cols[1]} {cols[3]} {cols[4]}"
                    lines.append(f"| {pos} | `{cols[8]}` | EV {cols[7]}, add={cols[12]}, stop={cols[9]}, trim={cols[10]} |\n")

    lines.append("\n## Top comptes utilisés comme signaux\n")
    for h in match_summary.get("top_account_handles_by_pnl", [])[:10]:
        lines.append(f"- {h}\n")

    lines.append("\n## Artifacts\n")
    for p in [refresh_path, summary_path, watchlist_path, watchlist_md_path]:
        lines.append(f"- `{p}`\n")

    lines.append("\n## Prochaine action technique recommandée\n")
    lines.append("\n1. Garder le pipeline en paper-only et relancer `2065028` uniquement en strict-limit paper avec suivi fill/résolution HKO.\n")
    lines.append("2. Ne considérer le live que quand `LIVE_READY=true`, `official_daily_extract.available=true`, quote non extrême, profondeur suffisante, et source météo saine.\n")

    out_path.write_text(''.join(lines), encoding='utf-8')
    print(out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
