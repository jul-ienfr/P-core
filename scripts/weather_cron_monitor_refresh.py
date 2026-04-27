#!/usr/bin/env python3
import csv, json, math, os, re, statistics, subprocess, sys, time
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

REPO = Path('/home/jul/P-core')
PYTHON_SRC = REPO / 'python' / 'src'
PREDICTION_CORE = REPO / 'python' / 'scripts' / 'prediction-core'
PYTHON = sys.executable or 'python3'
sys.path.insert(0, str(PYTHON_SRC))
from prediction_core.analytics.clickhouse_writer import create_clickhouse_writer_from_env  # noqa: E402
from prediction_core.analytics.events import serialize_event  # noqa: E402
from weather_pm.analytics_adapter import (  # noqa: E402
    debug_decision_events_from_shortlist,
    execution_events_from_payload,
    profile_decision_events_from_shortlist,
    strategy_signal_events_from_shortlist,
)
from weather_pm.runtime_operator_profiles import build_runtime_weather_profile_summary  # noqa: E402
from weather_pm.paper_report import build_paper_portfolio_report  # noqa: E402
from weather_pm.polymarket_settlement import (  # noqa: E402
    enrich_exited_position_with_official_outcome,
    resolution_check_schedule_from_gamma_event,
    resolve_position_from_gamma_event,
)

BASE = Path('/home/jul/P-core/data/polymarket')
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
    result={
        'official_resolution_source':prev,
        'official_resolution_source_status':'available' if prev else 'missing',
        'resolution_source_newly_available':False,
        'market_fetch_error':None,
        'polymarket_event':None,
        'resolution_scheduled_at':pos.get('resolution_scheduled_at'),
        'auto_check_at':pos.get('auto_check_at'),
        'auto_check_after_seconds':pos.get('auto_check_after_seconds'),
    }
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
                result['polymarket_event']=item
                result.update(resolution_check_schedule_from_gamma_event(item, check_delay_seconds=60))
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

def enrich_closed_position(pos):
    p=deepcopy(pos)
    rs=extract_resolution_source(p)
    event=rs.pop('polymarket_event', None)
    p.update(rs)
    if p.get('action') == 'EXIT_PAPER' and isinstance(event, dict):
        p=enrich_exited_position_with_official_outcome(p, event)
    return p


def run_cmd(cmd, timeout=180):
    env=os.environ.copy()
    env['PYTHONPATH']=str(PYTHON_SRC)+(os.pathsep+env['PYTHONPATH'] if env.get('PYTHONPATH') else '')
    return subprocess.run(cmd, cwd=str(REPO), text=True, capture_output=True, timeout=timeout, check=False, env=env)


def load_json(path):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return None


def ch_time(value):
    parsed=datetime.strptime(value, '%Y%m%dT%H%M%SZ').replace(tzinfo=timezone.utc)
    return parsed.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]


def build_runtime_analytics_rows(report, stamp):
    observed_at=ch_time(stamp)
    observed_dt=datetime.strptime(observed_at, '%Y-%m-%d %H:%M:%S.%f').replace(tzinfo=timezone.utc)
    weather_profiles=report.get('weather_profiles') if isinstance(report.get('weather_profiles'), dict) else {}
    decisions=weather_profiles.get('decisions') if isinstance(weather_profiles.get('decisions'), list) else []
    mode=str(report.get('runtime_execution_mode') or 'dry_run')
    run_id=str(report.get('run_id') or stamp)
    prediction_runs=[{
        'run_id':run_id,'strategy_id':'','profile_id':'','market_id':'','observed_at':observed_at,'completed_at':observed_at,
        'source':'weather_cron_monitor_refresh','mode':mode,'status':str(report.get('operator_verdict',{}).get('status') or 'unknown'),
        'strategy_count':int(weather_profiles.get('strategy_count') or 0),'profile_count':int(weather_profiles.get('profile_count') or 0),
        'market_count':len(report.get('runtime_watchlist') or []),'raw':json.dumps(report, sort_keys=True)
    }]
    shortlist_payload={'run_id':run_id,'mode':mode,'observed_at':observed_dt.isoformat(),'rows':decisions}
    profile_decisions=[serialize_event(event) for event in profile_decision_events_from_shortlist(shortlist_payload, default_observed_at=observed_dt)]
    debug_decisions=[serialize_event(event) for event in debug_decision_events_from_shortlist(shortlist_payload, default_observed_at=observed_dt)]
    strategy_signals=[serialize_event(event) for event in strategy_signal_events_from_shortlist(shortlist_payload, default_observed_at=observed_dt)]
    execution_payload={'run_id':run_id,'mode':mode,'observed_at':observed_dt.isoformat(),'events':report.get('execution_events') or []}
    execution_events=[serialize_event(event) for event in execution_events_from_payload(execution_payload, default_observed_at=observed_dt)]
    profile_metrics=[]
    for decision in decisions:
        if not isinstance(decision, dict): continue
        raw=json.dumps(decision, sort_keys=True)
        enter=decision.get('decision') == 'enter'
        profile_metrics.append({
            'run_id':run_id,'strategy_id':str(decision.get('strategy_id') or ''),'profile_id':str(decision.get('profile_id') or ''),'market_id':str(decision.get('market_id') or ''),'observed_at':observed_at,'mode':mode,
            'decision_count':1,'trade_count':1 if enter else 0,'skip_count':0 if enter else 1,'exposure_usdc':float(decision.get('capped_spend_usdc') or 0.0),'gross_pnl_usdc':0.0,'net_pnl_usdc':0.0,'roi':None,'raw':raw
        })
    strategy_metrics_by_id={}
    for row in profile_metrics:
        aggregate=strategy_metrics_by_id.setdefault(row['strategy_id'], {
            'run_id':row['run_id'],'strategy_id':row['strategy_id'],'profile_id':'','market_id':'','observed_at':row['observed_at'],'mode':row['mode'],
            'signal_count':0,'trade_count':0,'skip_count':0,'avg_edge':None,'gross_pnl_usdc':0.0,'net_pnl_usdc':0.0,'exposure_usdc':0.0,'raw':'{}'
        })
        aggregate['signal_count']+=1; aggregate['trade_count']+=int(row['trade_count']); aggregate['skip_count']+=int(row['skip_count']); aggregate['exposure_usdc']+=float(row['exposure_usdc'] or 0.0)
    for strategy_id, row in strategy_metrics_by_id.items(): row['raw']=json.dumps({'strategy_id':strategy_id,'runtime_summary':report.get('runtime_summary')}, sort_keys=True)
    return {'prediction_runs':prediction_runs,'strategy_signals':strategy_signals,'profile_decisions':profile_decisions,'debug_decisions':debug_decisions,'execution_events':execution_events,'profile_metrics':profile_metrics,'strategy_metrics':list(strategy_metrics_by_id.values())}


def export_runtime_analytics(report, stamp):
    rows_by_table=build_runtime_analytics_rows(report, stamp)
    counts={table:len(rows) for table, rows in rows_by_table.items()}
    os.environ.setdefault('PREDICTION_CORE_CLICKHOUSE_URL','http://127.0.0.1:8123')
    os.environ.setdefault('PREDICTION_CORE_CLICKHOUSE_HOST','127.0.0.1')
    os.environ.setdefault('PREDICTION_CORE_CLICKHOUSE_PORT','8123')
    os.environ.setdefault('PREDICTION_CORE_CLICKHOUSE_USER','prediction')
    os.environ.setdefault('PREDICTION_CORE_CLICKHOUSE_PASSWORD','prediction')
    os.environ.setdefault('PREDICTION_CORE_CLICKHOUSE_DATABASE','prediction_core')
    writer=create_clickhouse_writer_from_env()
    if writer is None: return {'enabled':False,'inserted':False,'rows':counts}
    for table, rows in rows_by_table.items(): writer.insert_rows(table, rows)
    return {'enabled':True,'inserted':True,'rows':counts}


def build_runtime_strategy_report(stamp):
    runtime_dir=BASE/'runtime'
    runtime_dir.mkdir(parents=True, exist_ok=True)
    audit_dir=runtime_dir/'audit'
    audit_dir.mkdir(parents=True, exist_ok=True)
    markets_path=runtime_dir/f'weather_runtime_live_markets_{stamp}.json'
    events_path=runtime_dir/f'weather_runtime_live_events_{stamp}.jsonl'
    probabilities_path=runtime_dir/f'weather_runtime_live_probabilities_{stamp}.json'
    runtime_path=runtime_dir/f'weather_runtime_dryrun_{stamp}.json'
    ids_path=audit_dir/f'weather_runtime_ids_{stamp}.jsonl'
    audit_path=audit_dir/f'weather_runtime_audit_{stamp}.jsonl'
    probe_code=f"""
import json
from pathlib import Path
from weather_pm.polymarket_live import list_live_weather_markets
markets=list_live_weather_markets(limit=12, active=True, closed=False)
selected=[]
for m in markets:
    if len(selected) >= 3:
        break
    if (m.get('hours_to_resolution') or 0) > 0 and m.get('clob_token_id'):
        selected.append(m)
if len(selected) < 3:
    selected=markets[:3]
markets_for_runtime=[]; events=[]; probs={{}}
for m in selected:
    tid=str(m.get('clob_token_id'))
    yes_ask=float(m.get('best_ask') or 0) or None
    yes_bid=float(m.get('best_bid') or 0)
    probs[tid]=round(min(0.99, max(0.0, (yes_ask or 0.01) + 0.05)), 6)
    markets_for_runtime.append({{'id':str(m.get('id')),'question':m.get('question'),'clob_token_id':tid,'clobTokenIds':[tid],'outcomes':['Yes'],'best_bid':yes_bid,'best_ask':yes_ask,'liquidity':float(m.get('volume') or m.get('ask_depth_usd') or 1000),'closed':False}})
    bids=m.get('bids') or []; asks=m.get('asks') or []
    event={{'event_type':'book','asset_id':tid,'bids':bids[:10],'asks':asks[:10],'source_market_id':str(m.get('id')),'source':'live_gamma_clob_snapshot'}}
    if not event['asks'] and yes_ask: event['asks']=[{{'price':yes_ask,'size':float(m.get('best_ask_size') or 1)}}]
    if not event['bids'] and yes_bid: event['bids']=[{{'price':yes_bid,'size':float(m.get('best_bid_size') or 1)}}]
    events.append(event)
Path({str(markets_path)!r}).write_text(json.dumps(markets_for_runtime, indent=2, sort_keys=True), encoding='utf-8')
Path({str(events_path)!r}).write_text('\\n'.join(json.dumps(e, sort_keys=True) for e in events)+'\\n', encoding='utf-8')
Path({str(probabilities_path)!r}).write_text(json.dumps(probs, indent=2, sort_keys=True), encoding='utf-8')
print(json.dumps({{'selected':len(selected),'market_ids':[m.get('id') for m in selected]}}))
"""
    probe=run_cmd([PYTHON,'-c',probe_code], timeout=180)
    artifacts={'markets_json':str(markets_path),'events_jsonl':str(events_path),'probabilities_json':str(probabilities_path),'runtime_json':str(runtime_path),'idempotency_jsonl':str(ids_path),'audit_jsonl':str(audit_path)}
    if probe.returncode != 0:
        return {'ok':False,'stage':'live_probe','paper_only':True,'error':probe.stderr[-2000:],'stdout':probe.stdout[-1000:],'artifacts':artifacts}
    cmd=[str(PREDICTION_CORE),'polymarket-runtime-cycle','--markets-json',str(markets_path),'--dry-run-events-jsonl',str(events_path),'--probabilities-json',str(probabilities_path),'--max-events','3','--paper-notional-usdc','5','--min-edge','0.02','--execution-mode','dry_run','--idempotency-jsonl',str(ids_path),'--audit-jsonl',str(audit_path),'--max-order-notional-usdc','5','--max-total-exposure-usdc','20','--max-daily-loss-usdc','10','--max-spread','0.05']
    cycle=run_cmd(cmd, timeout=180)
    if cycle.stdout.strip(): runtime_path.write_text(cycle.stdout, encoding='utf-8')
    if cycle.returncode != 0:
        return {'ok':False,'stage':'runtime_cycle','paper_only':True,'error':cycle.stderr[-2000:],'stdout':cycle.stdout[-1000:],'artifacts':artifacts}
    dry=load_json(runtime_path)
    if not isinstance(dry, dict): return {'ok':False,'stage':'parse_runtime_json','paper_only':True,'artifacts':artifacts}
    runtime_summary=dry.get('decisions',{}).get('summary',{}) if isinstance(dry.get('decisions'), dict) else {}
    markets_payload=load_json(markets_path); probabilities_payload=load_json(probabilities_path)
    weather_profiles=build_runtime_weather_profile_summary(markets=markets_payload if isinstance(markets_payload, list) else [], probabilities=probabilities_payload if isinstance(probabilities_payload, dict) else {}, runtime_result=dry, artifacts=artifacts)
    rows=[]
    for d in dry.get('decisions',{}).get('decisions',[]):
        if isinstance(d, dict): rows.append({'market_id':d.get('market_id'),'question':d.get('question'),'outcome':d.get('outcome'),'best_bid':d.get('best_bid'),'best_ask':d.get('best_ask'),'model_probability':d.get('model_probability'),'edge_vs_ask':d.get('edge_vs_ask'),'action':d.get('action'),'execution_enabled':d.get('execution_enabled')})
    execution=dry.get('execution') if isinstance(dry.get('execution'), dict) else {}
    runtime_mode=str(dry.get('mode') or '')
    runtime_execution_mode=runtime_mode.split(' ',1)[0] if runtime_mode else 'dry_run'
    signal_count=int(runtime_summary.get('paper_signal_count') or 0)
    execution_events=[]
    if isinstance(execution, dict):
        for index, order in enumerate(execution.get('orders_submitted') or [], start=1):
            if isinstance(order, dict):
                execution_events.append({**order,'event_type':order.get('status') or 'dry_run_order_submitted','execution_event_id':order.get('order_id') or f'{stamp}:submitted:{index}','paper_only':True,'live_order_allowed':False})
        for index, intent in enumerate(execution.get('paper_intents') or [], start=1):
            if isinstance(intent, dict):
                execution_events.append({**intent,'event_type':intent.get('status') or 'paper_intent','execution_event_id':intent.get('intent_id') or f'{stamp}:intent:{index}','paper_only':True,'live_order_allowed':False})
    status='ADD_REVIEW' if signal_count > 0 or weather_profiles.get('enter_count', 0) > 0 else 'HOLD'
    report={'ok':True,'run_id':stamp,'paper_only':True,'no_real_orders':True,'runtime_execution_mode':runtime_execution_mode,'runtime_summary':{'processed_events':dry.get('marketdata',{}).get('processed_events') if isinstance(dry.get('marketdata'), dict) else None,'paper_signal_count':signal_count,'hold_count':runtime_summary.get('hold_count'),'orders_submitted':len(execution.get('orders_submitted',[])) if isinstance(execution, dict) else 0,'paper_intent_count':len(execution.get('paper_intents',[])) if isinstance(execution, dict) else 0,'weather_profile_count':weather_profiles['profile_count'],'weather_profile_strategy_count':weather_profiles['strategy_count'],'weather_profile_signal_count':weather_profiles['signal_count'],'weather_profile_decision_count':weather_profiles.get('decision_count',0),'weather_profile_enter_count':weather_profiles.get('enter_count',0),'weather_profile_skip_count':weather_profiles.get('skip_count',0)},'weather_profiles':weather_profiles,'execution_events':execution_events,'operator_verdict':{'status':status,'reason':'runtime dry-run strategy refresh'},'runtime_watchlist':rows,'artifacts':artifacts}
    report['analytics']=export_runtime_analytics(report, stamp)
    return report


def refresh_position(pos, dtiso):
    p=deepcopy(pos)
    book=best_book(p.get('token_id')) if p.get('token_id') else {'book_fetch_error':'missing token_id'}
    fc=fetch_forecast(p)
    rs=extract_resolution_source(p)
    event=rs.pop('polymarket_event', None)
    p.update(book); p.update(fc); p.update(rs)
    settlement=resolve_position_from_gamma_event(p, event) if isinstance(event, dict) else {'settlement_status':'UNSETTLED'}
    p.update(settlement)
    if p.get('settlement_status') in ('SETTLED_WON','SETTLED_LOST'):
        p['action']=p['settlement_status']
        p['reason']=f"official Polymarket final outcome: {p.get('winning_outcome')}"
        p['refreshed_at']=dtiso
        p['max_add_usdc']=0; p['add_allowed']=False
        return p
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
    closed=[enrich_closed_position(p) for p in closed]
    portfolio_report=build_paper_portfolio_report(refreshed, closed)
    runtime_report=build_runtime_strategy_report(stamp)
    alerts=[]; verify=[]
    for p in refreshed:
        if p.get('action') in ('EXIT_PAPER','TRIM_OR_STOP_MONITOR','SETTLED_WON','SETTLED_LOST') or p.get('resolution_source_newly_available') or (p.get('p_side_now') is not None and p.get('p_side_now') < p.get('hard_stop_if_p_below', -1)):
            alerts.append({k:p.get(k) for k in ['city','date','question','side','temp','action','reason','p_side_now','hard_stop_if_p_below','trim_review_if_p_below','best_bid_now','best_ask_now','official_resolution_source','resolution_source_newly_available','resolution_scheduled_at','resolution_checked_at','auto_check_at','winning_outcome','paper_settlement_value_usdc','paper_realized_pnl_usdc']})
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
        'portfolio_report':portfolio_report,
        'runtime_strategy_ok':runtime_report.get('ok'),
        'runtime_execution_mode':runtime_report.get('runtime_execution_mode'),
        'weather_profile_count':runtime_report.get('weather_profiles',{}).get('profile_count') if isinstance(runtime_report.get('weather_profiles'), dict) else 0,
        'weather_profile_strategy_count':runtime_report.get('weather_profiles',{}).get('strategy_count') if isinstance(runtime_report.get('weather_profiles'), dict) else 0,
        'weather_profile_signal_count':runtime_report.get('weather_profiles',{}).get('signal_count') if isinstance(runtime_report.get('weather_profiles'), dict) else 0,
        'weather_profile_decision_count':runtime_report.get('weather_profiles',{}).get('decision_count') if isinstance(runtime_report.get('weather_profiles'), dict) else 0,
        'weather_profile_enter_count':runtime_report.get('weather_profiles',{}).get('enter_count') if isinstance(runtime_report.get('weather_profiles'), dict) else 0,
        'weather_profile_skip_count':runtime_report.get('weather_profiles',{}).get('skip_count') if isinstance(runtime_report.get('weather_profiles'), dict) else 0,
        'analytics_inserted':runtime_report.get('analytics',{}).get('inserted') if isinstance(runtime_report.get('analytics'), dict) else False,
        'rules':'paper only; dry-run simulated paper orders allowed; no real orders; Seoul Apr26 NO20 and Karachi Apr27 NO36 capped no-add'
    }
    out={'summary':summary,'positions':refreshed,'alerts':alerts,'verify_forecast_source':[p.get('question') for p in verify],'closed_positions':closed,'runtime_strategies':runtime_report}
    json_path=BASE/f'weather_paper_cron_monitor_{stamp}.json'
    md_path=BASE/f'weather_paper_cron_monitor_{stamp}.md'
    csv_path=BASE/f'weather_paper_cron_monitor_{stamp}.csv'
    write_json(json_path, out)
    fields=['city','date','question','side','temp','action','settlement_status','winning_outcome','official_settlement_status','official_winning_outcome','resolution_scheduled_at','resolution_checked_at','auto_check_at','auto_check_after_seconds','paper_settlement_value_usdc','official_paper_settlement_value_usdc','paper_realized_pnl_usdc','official_hold_to_settlement_pnl_usdc','p_side_now','hard_stop_if_p_below','trim_review_if_p_below','best_bid_now','best_ask_now','filled_usdc','paper_ev_now_usdc','paper_mtm_bid_usdc','current_forecast_max_c','forecast_query_used','official_resolution_source','resolution_source_newly_available','reason']
    with open(csv_path,'w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f, fieldnames=fields); w.writeheader()
        for p in refreshed + closed: w.writerow({k:p.get(k) for k in fields})
    lines=[]
    lines.append(f"# Weather paper cron monitor — {stamp}")
    lines.append("")
    lines.append("Paper only — no real orders placed. No fresh add unless Julien explicitly asks.")
    lines.append("")
    lines.append(f"Summary: active={len(refreshed)}, closed_preserved={len(closed)}, spend={spend:.4f} USDC, EV={ev:.4f} USDC, MTM_bid={mtm:.4f} USDC, actions={counts}, alerts={len(alerts)}")
    lines.append("")
    lines.append("## Runtime strategies")
    if runtime_report.get('ok'):
        rp=runtime_report.get('runtime_summary',{})
        wp=runtime_report.get('weather_profiles',{})
        an=runtime_report.get('analytics',{})
        lines.append(f"- Mode: `{runtime_report.get('runtime_execution_mode')}`")
        lines.append(f"- Profils météo: {wp.get('profile_count')} ; stratégies: {wp.get('strategy_count')} ; signaux: {wp.get('signal_count')} ; décisions: {wp.get('decision_count')} ; enter={wp.get('enter_count')} ; skip={wp.get('skip_count')}")
        lines.append(f"- Runtime: processed_events={rp.get('processed_events')}, paper_signal_count={rp.get('paper_signal_count')}, simulated_orders={rp.get('orders_submitted')}")
        lines.append(f"- Grafana/ClickHouse: inserted={an.get('inserted')}, rows={an.get('rows')}")
        decisions=wp.get('decisions') if isinstance(wp.get('decisions'), list) else []
        if decisions:
            lines.append("")
            lines.append("| Profil | Décision | Side | Edge | Confidence | Notional | Blockers |")
            lines.append("|---|---:|---:|---:|---:|---:|---|")
            for decision in decisions:
                blockers=', '.join(decision.get('blockers') or []) if isinstance(decision, dict) else ''
                lines.append(f"| {decision.get('profile_id')} | {decision.get('decision_status')} | {decision.get('side')} | {decision.get('edge')} | {decision.get('confidence')} | {decision.get('capped_spend_usdc')} | {blockers or '-'} |")
    else:
        lines.append(f"- FAILED stage={runtime_report.get('stage')} error={runtime_report.get('error')}")
    lines.append("")
    pr=portfolio_report
    pnl=pr['pnl_usdc']; pr_counts=pr['counts']
    lines.append("## Portfolio PnL")
    lines.append(f"- Counts: open={pr_counts['open']}, settled={pr_counts['settled']}, exit_paper={pr_counts['exit_paper']}, total={pr_counts['total']}")
    lines.append(f"- Realized: {pnl['realized_total']:.6f} USDC (settled={pnl['settled_realized']:.6f}, exit_paper={pnl['exit_realized']:.6f})")
    lines.append(f"- Open MTM bid: {pnl['open_mtm_bid']:.6f} USDC")
    lines.append(f"- Realized + open MTM: {pnl['realized_plus_open_mtm']:.6f} USDC")
    lines.append(f"- If open loses: {pnl['if_open_loses']:.6f} USDC; if open wins full payout: {pnl['if_open_wins_full_payout']:.6f} USDC")
    lines.append(f"- Official hold-to-settlement PnL for EXIT_PAPER rows: {pnl['official_hold_to_settlement_for_exits']:.6f} USDC (postmortem only; does not rewrite exit PnL)")
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
    if closed:
        lines.append("## Closed / exited positions")
        lines.append("| Position | Action | Exit PnL | Official final | Official hold-to-settlement PnL |")
        lines.append("|---|---:|---:|---:|---:|")
        for p in closed:
            pos=f"{p.get('city')} {p.get('date')} {p.get('side')}{p.get('temp')}"
            official=p.get('official_settlement_status') or 'not checked'
            lines.append(f"| {pos} | {p.get('action')} | {p.get('paper_realized_pnl_usdc')} | {official} {p.get('official_winning_outcome') or ''} | {p.get('official_hold_to_settlement_pnl_usdc')} |")
        lines.append("")
    lines.append(f"Artifacts: `{json_path}`, `{csv_path}`, `{md_path}`")
    md_path.write_text('\n'.join(lines)+'\n', encoding='utf-8')
    # Verification
    ok=json_path.exists() and csv_path.exists() and md_path.exists() and out['summary']['paper_only'] is True and out['summary']['no_real_order_placed'] is True and runtime_report.get('ok') is True
    print(json.dumps({'ok':ok,'json':str(json_path),'csv':str(csv_path),'md':str(md_path),'summary':summary,'runtime_strategies':{'ok':runtime_report.get('ok'),'mode':runtime_report.get('runtime_execution_mode'),'weather_profile_count':summary.get('weather_profile_count'),'weather_profile_strategy_count':summary.get('weather_profile_strategy_count'),'weather_profile_signal_count':summary.get('weather_profile_signal_count'),'weather_profile_decision_count':summary.get('weather_profile_decision_count'),'weather_profile_enter_count':summary.get('weather_profile_enter_count'),'weather_profile_skip_count':summary.get('weather_profile_skip_count'),'analytics_inserted':summary.get('analytics_inserted')} ,'alerts':alerts}, ensure_ascii=False))
if __name__=='__main__': main()

