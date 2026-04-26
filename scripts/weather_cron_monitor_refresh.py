#!/usr/bin/env python3
import csv, json, math, os, re, statistics, sys, time
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

BASE = Path('/home/jul/prediction_core/data/polymarket')
SOURCE_BASE = BASE / 'weather_paper_micro_after_karachi_add_20260425.json'
PREFS = [
    'weather_paper_active_ledger_post_exit_*.json',
    'weather_paper_active_monitor_*.json',
    'weather_paper_cron_monitor_*.json',
]
USER_AGENT='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/123 Safari/537.36'

def now_utc(): return datetime.now(timezone.utc)
def iso(dt): return dt.isoformat()
def ts(dt): return dt.strftime('%Y%m%dT%H%M%SZ')

def read_json(p):
    with open(p, encoding='utf-8') as f: return json.load(f)

def write_json(p, data):
    p.write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False)+"\n", encoding='utf-8')

def http_json(url, timeout=15):
    req=Request(url, headers={'User-Agent':USER_AGENT,'Accept':'application/json'})
    with urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode('utf-8'))

def latest_structural():
    cands=[]
    for pat in PREFS:
        for f in BASE.glob(pat):
            try:
                d=read_json(f)
                positions=d.get('active_positions') or d.get('positions') or []
                # Require active positions with token ids. Pick newest compatible
                # monitor/ledger by structure, not by pattern, so prior alerts such as
                # newly available resolution sources are not re-emitted every cron run.
                if positions and any(p.get('token_id') for p in positions):
                    cands.append((f.stat().st_mtime, f, d))
            except Exception:
                pass
    if cands:
        cands.sort(reverse=True, key=lambda x:x[0])
        return cands[0][1], cands[0][2]
    return SOURCE_BASE, read_json(SOURCE_BASE)

def active_closed_from(doc):
    if 'active_positions' in doc:
        active=doc.get('active_positions') or []
        closed=doc.get('closed_positions') or []
    else:
        active=doc.get('positions') or []
        closed=doc.get('closed_positions') or []
    # Exclude known closed rows by question+side+temp.
    closed_keys={(p.get('question'),p.get('side'),p.get('temp')) for p in closed}
    active=[p for p in active if (p.get('question'),p.get('side'),p.get('temp')) not in closed_keys and p.get('action')!='EXIT_PAPER']
    return deepcopy(active), deepcopy(closed)

def best_book(token_id):
    try:
        d=http_json('https://clob.polymarket.com/book?token_id='+quote(str(token_id)), timeout=12)
        bids=[{'price':float(x.get('price')), 'size':float(x.get('size',0))} for x in d.get('bids',[]) if x.get('price') is not None]
        asks=[{'price':float(x.get('price')), 'size':float(x.get('size',0))} for x in d.get('asks',[]) if x.get('price') is not None]
        bids_sorted=sorted(bids, key=lambda x:x['price'], reverse=True)
        asks_sorted=sorted(asks, key=lambda x:x['price'])
        return {
            'best_bid_now': bids_sorted[0]['price'] if bids_sorted else None,
            'best_ask_now': asks_sorted[0]['price'] if asks_sorted else None,
            'bid_levels': len(bids), 'ask_levels': len(asks),
            'top_bids': bids_sorted[:3], 'top_asks': asks_sorted[:3],
            'book_timestamp': d.get('timestamp'), 'book_fetch_error': None,
        }
    except Exception as e:
        return {'best_bid_now':None,'best_ask_now':None,'bid_levels':0,'ask_levels':0,'top_bids':[],'top_asks':[],'book_timestamp':None,'book_fetch_error':repr(e)}

def target_date(pos):
    if pos.get('forecast_target_date'): return pos['forecast_target_date']
    m=re.search(r'April\s+(\d+)', pos.get('date','') or pos.get('question',''))
    if m: return f"2026-04-{int(m.group(1)):02d}"
    return None

def forecast_query(pos):
    # Keep query identity stable: prior forecast_query_used, not broad city fallback unless nothing exists.
    return pos.get('forecast_query_used') or pos.get('forecast_area') or pos.get('station') or pos.get('city')

def fetch_forecast(pos):
    q=forecast_query(pos)
    tdate=target_date(pos)
    out={'forecast_query_used':q,'forecast_target_date':tdate,'forecast_fetch_error':None}
    if not q or not tdate:
        out['forecast_fetch_error']='missing query or target date'; return out
    try:
        d=http_json('https://wttr.in/'+quote(q)+'?format=j1', timeout=15)
        weather=d.get('weather') or []
        row=None
        for w in weather:
            if w.get('date')==tdate:
                row=w; break
        if row is None and weather:
            row=weather[0]
        if not row:
            out['forecast_fetch_error']='no weather rows'; return out
        out.update({
            'forecast_selected_date': row.get('date'),
            'current_forecast_max_c': float(row.get('maxtempC')) if row.get('maxtempC') not in (None,'') else None,
            'forecast_min_c': float(row.get('mintempC')) if row.get('mintempC') not in (None,'') else None,
            'forecast_narrative': ((row.get('hourly') or [{}])[4].get('weatherDesc') or [{}])[0].get('value') if row.get('hourly') else None,
            'forecast_area': (((d.get('nearest_area') or [{}])[0].get('areaName') or [{}])[0].get('value')),
            'forecast_source': f"wttr.in stable query `{q}` for market date (proxy forecast, not settlement source)",
            'forecast_source_stability': 'stable_query_reused',
        })
        prev=pos.get('current_forecast_max_c')
        if prev is None: prev=pos.get('station_forecast_max_c')
        out['forecast_move_c'] = round(out['current_forecast_max_c']-float(prev),2) if out.get('current_forecast_max_c') is not None and prev is not None else None
        return out
    except Exception as e:
        out['forecast_fetch_error']=repr(e); return out

def norm_cdf(x): return 0.5*(1+math.erf(x/math.sqrt(2)))
def p_side_from_forecast(pos, fc):
    maxc=fc.get('current_forecast_max_c')
    if maxc is None: return pos.get('p_side_now') or pos.get('base_p_side')
    temp=float(pos.get('temp'))
    sigma=1.4
    kind=pos.get('kind')
    side=pos.get('side')
    if kind=='higher':
        # YES = max >= threshold; continuity correction.
        p_yes = 1 - norm_cdf((temp-0.5-maxc)/sigma)
    else:
        # YES = exact whole degree, approx interval [temp-0.5,temp+0.5)
        p_yes = norm_cdf((temp+0.5-maxc)/sigma) - norm_cdf((temp-0.5-maxc)/sigma)
    p_yes=max(0.001,min(0.999,p_yes))
    p_side = (1-p_yes) if side=='NO' else p_yes
    return round(max(0.001,min(0.999,p_side)),4)

def market_slug_from_url(url):
    if not url: return None
    return urlparse(url).path.rstrip('/').split('/')[-1]

def extract_resolution_source(pos):
    slug=market_slug_from_url(pos.get('url'))
    prev=pos.get('official_resolution_source') or pos.get('resolutionSource') or pos.get('resolution_source')
    result={'official_resolution_source':prev,'official_resolution_source_status':'available' if prev else 'missing','resolution_source_newly_available':False,'market_fetch_error':None}
    if not slug: return result
    # Try Gamma event slug. If unavailable, keep prior; do not block monitor.
    urls=[f'https://gamma-api.polymarket.com/events?slug={quote(slug)}', f'https://gamma-api.polymarket.com/markets?slug={quote(slug)}']
    try:
        for url in urls:
            d=http_json(url, timeout=12)
            items=d if isinstance(d,list) else (d.get('data') if isinstance(d,dict) else None)
            if isinstance(items,dict): items=[items]
            if not items: continue
            # event or market fields
            for item in items:
                cand=item.get('resolutionSource') or item.get('resolution_source')
                if not cand:
                    for m in item.get('markets') or []:
                        cand=m.get('resolutionSource') or m.get('resolution_source')
                        if cand: break
                if cand:
                    result['official_resolution_source']=cand
                    result['official_resolution_source_status']='available'
                    result['resolution_source_newly_available']=not bool(prev) and cand!=prev
                    return result
        return result
    except Exception as e:
        result['market_fetch_error']=repr(e)
        return result

def thresholds(pos):
    entry=float(pos.get('entry_avg') or 0)
    hard=pos.get('hard_stop_if_p_below')
    trim=pos.get('trim_review_if_p_below')
    tp=pos.get('take_profit_review_if_bid_above')
    if hard is None: hard=max(0, round(entry-0.03,4))
    if trim is None: trim=max(0, round(entry+0.02,4))
    if tp is None: tp=round(min(0.99, entry+0.12),4)
    return float(hard), float(trim), float(tp)

def refresh_position(pos, dtiso):
    p=deepcopy(pos)
    book=best_book(p.get('token_id')) if p.get('token_id') else {'book_fetch_error':'missing token_id'}
    fc=fetch_forecast(p)
    rs=extract_resolution_source(p)
    p.update(book); p.update(fc); p.update(rs)
    old_p=p.get('p_side_now') or p.get('base_p_side')
    p['p_side_previous']=old_p
    p_now=p_side_from_forecast(p, fc)
    p['p_side_now']=p_now
    hard, trim, tp=thresholds(p)
    p['hard_stop_if_p_below']=hard; p['trim_review_if_p_below']=trim; p['take_profit_review_if_bid_above']=tp
    shares=float(p.get('shares') or 0); spend=float(p.get('filled_usdc') or 0)
    bid=p.get('best_bid_now'); ask=p.get('best_ask_now')
    p['paper_ev_now_usdc']=round(shares*p_now-spend,6)
    p['paper_mtm_bid_usdc']=round(shares*bid-spend,6) if bid is not None else None
    p['edge_vs_bid_now']=round(p_now-bid,4) if bid is not None else None
    p['edge_vs_ask_now']=round(p_now-ask,4) if ask is not None else None
    p['refreshed_at']=dtiso
    p['max_add_usdc']=0; p['add_allowed']=False
    reasons=[]
    if p_now < hard:
        p['action']='EXIT_PAPER'; reasons.append(f"p_side {p_now:.4f} < hard_stop {hard:.4f}")
    elif p_now < trim:
        p['action']='TRIM_OR_STOP_MONITOR'; reasons.append(f"p_side {p_now:.4f} < trim_review {trim:.4f}")
    else:
        p['action']='HOLD_CAPPED'; reasons.append('fresh book/forecast; capped/no add; no exit trigger')
    if p.get('resolution_source_newly_available'):
        reasons.insert(0,'official resolution source newly available')
    # explicit no-add caps
    if ('Seoul' in str(p.get('city')) and p.get('date')=='April 26' and p.get('side')=='NO' and int(p.get('temp') or -1)==20) or ('Karachi' in str(p.get('city')) and p.get('date')=='April 27' and p.get('side')=='NO' and int(p.get('temp') or -1)==36):
        p['add_allowed']=False; p['max_add_usdc']=0
    p['reason']='; '.join(reasons)
    return p

def main():
    dt=now_utc(); stamp=ts(dt); dtiso=iso(dt)
    src_path, src_doc = latest_structural()
    active, closed = active_closed_from(src_doc)
    refreshed=[refresh_position(p, dtiso) for p in active]
    alerts=[]; verify=[]
    for p in refreshed:
        if p.get('action') in ('EXIT_PAPER','TRIM_OR_STOP_MONITOR') or p.get('resolution_source_newly_available') or (p.get('p_side_now') is not None and p.get('p_side_now') < p.get('hard_stop_if_p_below', -1)):
            alerts.append({k:p.get(k) for k in ['city','date','question','side','temp','action','reason','p_side_now','hard_stop_if_p_below','trim_review_if_p_below','best_bid_now','best_ask_now','official_resolution_source','resolution_source_newly_available']})
        if p.get('forecast_source_stability') == 'VERIFY_FORECAST_SOURCE': verify.append(p)
    counts={}
    for p in refreshed: counts[p.get('action')]=counts.get(p.get('action'),0)+1
    spend=round(sum(float(p.get('filled_usdc') or 0) for p in refreshed),6)
    ev=round(sum(float(p.get('paper_ev_now_usdc') or 0) for p in refreshed),6)
    mtm=round(sum(float(p.get('paper_mtm_bid_usdc') or 0) for p in refreshed if p.get('paper_mtm_bid_usdc') is not None),6)
    summary={
        'generated_at':dtiso,'paper_only':True,'no_real_order_placed':True,
        'source_ledger':str(src_path),'active_count':len(refreshed),'closed_count_preserved':len(closed),
        'active_total_spend_usdc':spend,'active_total_ev_now_usdc':ev,'active_total_mtm_bid_usdc':mtm,
        'active_action_counts':counts,'alert_count':len(alerts),'verify_count':len(verify),
        'rules':'paper only; no real orders; Seoul Apr26 NO20 and Karachi Apr27 NO36 capped no-add; no fresh add unless Julien explicitly asks'
    }
    out={'summary':summary,'positions':refreshed,'alerts':alerts,'verify_forecast_source':[p.get('question') for p in verify],'closed_positions':closed}
    json_path=BASE/f'weather_paper_cron_monitor_{stamp}.json'
    md_path=BASE/f'weather_paper_cron_monitor_{stamp}.md'
    csv_path=BASE/f'weather_paper_cron_monitor_{stamp}.csv'
    write_json(json_path, out)
    fields=['city','date','question','side','temp','action','p_side_now','hard_stop_if_p_below','trim_review_if_p_below','best_bid_now','best_ask_now','filled_usdc','paper_ev_now_usdc','paper_mtm_bid_usdc','current_forecast_max_c','forecast_query_used','official_resolution_source','resolution_source_newly_available','reason']
    with open(csv_path,'w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f, fieldnames=fields); w.writeheader()
        for p in refreshed: w.writerow({k:p.get(k) for k in fields})
    lines=[]
    lines.append(f"# Weather paper cron monitor — {stamp}")
    lines.append("")
    lines.append("Paper only — no real orders placed. No fresh add unless Julien explicitly asks.")
    lines.append("")
    lines.append(f"Summary: active={len(refreshed)}, closed_preserved={len(closed)}, spend={spend:.4f} USDC, EV={ev:.4f} USDC, MTM_bid={mtm:.4f} USDC, actions={counts}, alerts={len(alerts)}")
    lines.append("")
    if alerts:
        lines.append("## Alerts")
        for a in alerts:
            lines.append(f"- {a.get('action')}: {a.get('city')} {a.get('date')} {a.get('side')}{a.get('temp')} — p={a.get('p_side_now')} bid/ask={a.get('best_bid_now')}/{a.get('best_ask_now')} — {a.get('reason')}")
        lines.append("")
    lines.append("## Active positions")
    lines.append("| Position | Action | p_side | bid/ask | EV | MTM | Forecast | Official source |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---|")
    for p in refreshed:
        pos=f"{p.get('city')} {p.get('date')} {p.get('side')}{p.get('temp')}"
        src=p.get('official_resolution_source') or 'missing'
        lines.append(f"| {pos} | {p.get('action')} | {p.get('p_side_now')} | {p.get('best_bid_now')}/{p.get('best_ask_now')} | {p.get('paper_ev_now_usdc')} | {p.get('paper_mtm_bid_usdc')} | {p.get('current_forecast_max_c')}°C via {p.get('forecast_query_used')} | {src} |")
    lines.append("")
    lines.append(f"Artifacts: `{json_path}`, `{csv_path}`, `{md_path}`")
    md_path.write_text('\n'.join(lines)+'\n', encoding='utf-8')
    # Verification
    ok=json_path.exists() and csv_path.exists() and md_path.exists() and out['summary']['paper_only'] is True and out['summary']['no_real_order_placed'] is True
    print(json.dumps({'ok':ok,'json':str(json_path),'csv':str(csv_path),'md':str(md_path),'summary':summary,'alerts':alerts}, ensure_ascii=False))
if __name__=='__main__': main()
