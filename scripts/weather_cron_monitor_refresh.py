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
from prediction_core.analytics.events import PaperOrderEvent, PaperPnlSnapshotEvent, PaperPositionEvent, serialize_event  # noqa: E402
from weather_pm.analytics_adapter import (  # noqa: E402
    debug_decision_events_from_shortlist,
    execution_events_from_payload,
    profile_decision_events_from_shortlist,
    strategy_signal_events_from_shortlist,
)
from weather_pm.forecast_client import build_forecast_bundle  # noqa: E402
from weather_pm.market_parser import parse_market_question  # noqa: E402
from weather_pm.probability_model import build_model_output  # noqa: E402
from weather_pm.resolution_parser import parse_resolution_metadata  # noqa: E402
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


def _num(value, default=0.0):
    try:
        if value is None: return default
        return float(value)
    except (TypeError, ValueError):
        return default


def build_weather_model_probability_record(market):
    try:
        structure=parse_market_question(str(market.get('question') or ''))
        resolution=parse_resolution_metadata(resolution_source=market.get('resolution_source'), description=market.get('description'), rules=market.get('rules'))
        forecast=build_forecast_bundle(structure, live=True, resolution=resolution)
        model=build_model_output(structure, forecast)
        return {
            'probability_yes': model.probability_yes,
            'confidence': model.confidence,
            'source': 'weather_model',
            'method': model.method,
            'synthetic': False,
            'forecast_source_provider': forecast.source_provider,
            'forecast_source_station_code': forecast.source_station_code,
            'forecast_source_url': forecast.source_url,
            'forecast_source_latency_tier': forecast.source_latency_tier,
        }
    except Exception as exc:
        return {'probability_yes': None, 'confidence': 0.0, 'source': 'weather_model_unavailable', 'method': 'unavailable', 'synthetic': True, 'error': repr(exc)}


def _paper_market_id(position):
    return str(position.get('market_id') or position.get('slug') or position.get('question') or position.get('token_id') or '')


def _paper_strategy_id(position):
    return str(position.get('strategy_id') or 'weather_manual_paper_basket_v1')


def _paper_profile_id(position):
    return str(position.get('profile_id') or 'weather_manual_basket')


def _paper_status(position):
    return str(position.get('settlement_status') or position.get('action') or 'OPEN')


def build_paper_basket_analytics_rows(report, stamp):
    observed_at=ch_time(stamp)
    observed_dt=datetime.strptime(observed_at, '%Y-%m-%d %H:%M:%S.%f').replace(tzinfo=timezone.utc)
    run_id=str(report.get('run_id') or stamp)
    mode=str(report.get('runtime_execution_mode') or 'paper')
    positions=[row for row in report.get('positions') or [] if isinstance(row, dict)]
    closed=[row for row in report.get('closed_positions') or [] if isinstance(row, dict)]
    all_positions=positions+closed
    order_events=[]; position_events=[]
    for index, position in enumerate(all_positions, start=1):
        market_id=_paper_market_id(position); token_id=str(position.get('token_id') or '')
        strategy_id=_paper_strategy_id(position); profile_id=_paper_profile_id(position)
        quantity=_num(position.get('shares'))
        exposure=_num(position.get('filled_usdc'))
        avg_price=_num(position.get('entry_avg'), None)
        status=_paper_status(position)
        raw={**position, 'portfolio_source':'weather_cron_monitor'}
        order_events.append(PaperOrderEvent(run_id=run_id,strategy_id=strategy_id,profile_id=profile_id,market_id=market_id,token_id=token_id,observed_at=observed_dt,mode=mode,paper_order_id=str(position.get('order_id') or position.get('paper_order_id') or f'{run_id}:{index}:{token_id or market_id}'),side=str(position.get('side') or ''),price=avg_price,size=quantity,spend_usdc=exposure,status=status,opening_fee_usdc=_num(position.get('opening_fee_usdc'), 0.0),opening_slippage_usdc=_num(position.get('opening_slippage_usdc'), 0.0),estimated_exit_cost_usdc=_num(position.get('estimated_exit_cost_usdc'), 0.0),paper_only=True,live_order_allowed=False,raw=raw))
        if quantity > 0:
            mtm=position.get('paper_mtm_bid_usdc')
            if mtm is None and position.get('paper_settlement_value_usdc') is not None:
                mtm=_num(position.get('paper_settlement_value_usdc'))-_num(position.get('filled_usdc'))
            position_events.append(PaperPositionEvent(run_id=run_id,strategy_id=strategy_id,profile_id=profile_id,market_id=market_id,token_id=token_id,observed_at=observed_dt,mode=mode,paper_position_id=str(position.get('position_id') or f'{token_id or market_id}:{position.get("side") or ""}'),quantity=quantity,avg_price=avg_price,exposure_usdc=exposure,mtm_bid_usdc=_num(mtm, None),status=status,raw=raw))
    portfolio=report.get('summary',{}).get('portfolio_report') if isinstance(report.get('summary'), dict) else {}
    pnl=portfolio.get('pnl_usdc') if isinstance(portfolio, dict) and isinstance(portfolio.get('pnl_usdc'), dict) else {}
    spend=portfolio.get('spend_usdc') if isinstance(portfolio, dict) and isinstance(portfolio.get('spend_usdc'), dict) else {}
    counts=portfolio.get('counts') if isinstance(portfolio, dict) and isinstance(portfolio.get('counts'), dict) else {}
    exposure=_num(spend.get('total_displayed'), sum(_num(row.get('filled_usdc')) for row in all_positions))
    net=_num(pnl.get('realized_plus_open_mtm'), _num(pnl.get('realized_total'))+sum(_num(row.get('paper_mtm_bid_usdc')) for row in positions))
    gross=_num(pnl.get('realized_total'), net)
    pnl_event=PaperPnlSnapshotEvent(run_id=run_id,strategy_id='weather_manual_paper_basket_v1',profile_id='weather_manual_basket',market_id='',observed_at=observed_dt,mode=mode,gross_pnl_usdc=gross,net_pnl_usdc=net,costs_usdc=0.0,exposure_usdc=exposure,roi=round(net/exposure, 6) if exposure else None,winrate=(float(counts.get('settled') or 0)/float(counts.get('total') or 1)) if counts else None,raw={'portfolio_report': portfolio, 'positions': all_positions})
    return {'paper_orders':[serialize_event(event) for event in order_events],'paper_positions':[serialize_event(event) for event in position_events],'paper_pnl_snapshots':[serialize_event(pnl_event)]}


def _profile_decision_price(decision):
    raw=decision.get('raw_decision') if isinstance(decision.get('raw_decision'), dict) else {}
    for key in ('limit_price','strict_limit_price','market_price'):
        value=decision.get(key)
        if value is not None:
            try: return float(value)
            except (TypeError, ValueError): pass
    value=raw.get('market_price')
    if value is not None:
        try: return float(value)
        except (TypeError, ValueError): pass
    return None


def _profile_decision_spend(decision):
    for key in ('capped_spend_usdc','requested_spend_usdc','capped_notional_usdc','requested_notional_usdc','paper_notional_usd'):
        value=decision.get(key)
        if value is not None:
            try: return float(value)
            except (TypeError, ValueError): pass
    return None


def build_profile_decision_paper_analytics_rows(report, stamp):
    observed_at=ch_time(stamp)
    observed_dt=datetime.strptime(observed_at, '%Y-%m-%d %H:%M:%S.%f').replace(tzinfo=timezone.utc)
    runtime_report=report.get('runtime_strategies') if isinstance(report.get('runtime_strategies'), dict) else report
    weather_profiles=runtime_report.get('weather_profiles') if isinstance(runtime_report.get('weather_profiles'), dict) else {}
    decisions=weather_profiles.get('decisions') if isinstance(weather_profiles.get('decisions'), list) else []
    mode=str(report.get('runtime_execution_mode') or runtime_report.get('runtime_execution_mode') or 'dry_run')
    run_id=str(report.get('run_id') or runtime_report.get('run_id') or stamp)
    order_events=[]; position_events=[]; grouped={}; order_ids={}
    for index, decision in enumerate(decisions, start=1):
        if not isinstance(decision, dict): continue
        if decision.get('decision') != 'enter': continue
        if decision.get('paper_only', True) is not True: continue
        if decision.get('live_order_allowed', False) is not False: continue
        strategy_id=str(decision.get('strategy_id') or '')
        profile_id=str(decision.get('profile_id') or '')
        market_id=str(decision.get('market_id') or '')
        token_id=str(decision.get('token_id') or '')
        price=_profile_decision_price(decision)
        spend=_profile_decision_spend(decision)
        if not strategy_id or not profile_id or not market_id or not token_id or price is None or price <= 0 or spend is None or spend <= 0:
            continue
        size=round(spend/price, 8)
        side=str(decision.get('side') or '')
        status='profile_enter_paper_planned'
        paper_order_base=f'profile-decision:{strategy_id}:{profile_id}:{market_id}:{token_id}:{side}:{status}'
        duplicate_count=order_ids.get(paper_order_base, 0)+1
        order_ids[paper_order_base]=duplicate_count
        paper_order_id=paper_order_base if duplicate_count == 1 else f'{paper_order_base}:{duplicate_count}'
        raw_decision=decision.get('raw_decision') if isinstance(decision.get('raw_decision'), dict) else {}
        fill_status=str(decision.get('fill_status') or raw_decision.get('fill_status') or decision.get('status') or raw_decision.get('status') or '').lower()
        filled=fill_status in {'filled','partial'}
        fill_semantics='simulated_fill' if filled else 'planned_intent'
        raw={**decision,'analytics_source':'runtime_weather_profile_decision','fill_semantics':fill_semantics,'simulated':True,'paper_only':True,'live_order_allowed':False,'no_real_order_placed':True,'runtime_execution_mode':mode}
        order_events.append(PaperOrderEvent(run_id=run_id,strategy_id=strategy_id,profile_id=profile_id,market_id=market_id,token_id=token_id,observed_at=observed_dt,mode=mode,paper_order_id=paper_order_id,side=side,price=price,size=size,spend_usdc=spend,status=status,opening_fee_usdc=0.0,opening_slippage_usdc=0.0,estimated_exit_cost_usdc=0.0,paper_only=True,live_order_allowed=False,raw=raw))
        if not filled:
            continue
        position_events.append(PaperPositionEvent(run_id=run_id,strategy_id=strategy_id,profile_id=profile_id,market_id=market_id,token_id=token_id,observed_at=observed_dt,mode=mode,paper_position_id=f'{paper_order_id}:position',quantity=size,avg_price=price,exposure_usdc=spend,mtm_bid_usdc=0.0,status=status,raw=raw))
        grouped.setdefault((strategy_id, profile_id), {'exposure':0.0,'orders':[]})
        grouped[(strategy_id, profile_id)]['exposure']+=spend
        grouped[(strategy_id, profile_id)]['orders'].append(paper_order_id)
    pnl_events=[]
    for (strategy_id, profile_id), group in grouped.items():
        exposure=round(float(group['exposure']), 6)
        pnl_events.append(PaperPnlSnapshotEvent(run_id=run_id,strategy_id=strategy_id,profile_id=profile_id,market_id='',observed_at=observed_dt,mode=mode,gross_pnl_usdc=0.0,net_pnl_usdc=0.0,costs_usdc=0.0,exposure_usdc=exposure,roi=0.0 if exposure > 0 else None,winrate=None,raw={'analytics_source':'runtime_weather_profile_decision','fill_semantics':'simulated_fill','simulated':True,'paper_only':True,'live_order_allowed':False,'no_real_order_placed':True,'runtime_execution_mode':mode,'paper_order_ids':group['orders']}))
    return {'paper_orders':[serialize_event(event) for event in order_events],'paper_positions':[serialize_event(event) for event in position_events],'paper_pnl_snapshots':[serialize_event(event) for event in pnl_events]}


def build_runtime_analytics_rows(report, stamp):
    observed_at=ch_time(stamp)
    observed_dt=datetime.strptime(observed_at, '%Y-%m-%d %H:%M:%S.%f').replace(tzinfo=timezone.utc)
    runtime_report=report.get('runtime_strategies') if isinstance(report.get('runtime_strategies'), dict) else report
    weather_profiles=runtime_report.get('weather_profiles') if isinstance(runtime_report.get('weather_profiles'), dict) else {}
    decisions=weather_profiles.get('decisions') if isinstance(weather_profiles.get('decisions'), list) else []
    mode=str(report.get('runtime_execution_mode') or runtime_report.get('runtime_execution_mode') or 'dry_run')
    run_id=str(report.get('run_id') or runtime_report.get('run_id') or stamp)
    prediction_runs=[{
        'run_id':run_id,'strategy_id':'','profile_id':'','market_id':'','observed_at':observed_at,'completed_at':observed_at,
        'source':'weather_cron_monitor_refresh','mode':mode,'status':str(runtime_report.get('operator_verdict',{}).get('status') or 'unknown'),
        'strategy_count':int(weather_profiles.get('strategy_count') or 0),'profile_count':int(weather_profiles.get('profile_count') or 0),
        'market_count':len(runtime_report.get('runtime_watchlist') or []),'raw':json.dumps(report, sort_keys=True)
    }]
    shortlist_payload={'run_id':run_id,'mode':mode,'observed_at':observed_dt.isoformat(),'rows':decisions}
    profile_decisions=[serialize_event(event) for event in profile_decision_events_from_shortlist(shortlist_payload, default_observed_at=observed_dt)]
    debug_decisions=[serialize_event(event) for event in debug_decision_events_from_shortlist(shortlist_payload, default_observed_at=observed_dt)]
    strategy_signals=[serialize_event(event) for event in strategy_signal_events_from_shortlist(shortlist_payload, default_observed_at=observed_dt)]
    execution_payload={'run_id':run_id,'mode':mode,'observed_at':observed_dt.isoformat(),'events':runtime_report.get('execution_events') or []}
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
    for strategy_id, row in strategy_metrics_by_id.items(): row['raw']=json.dumps({'strategy_id':strategy_id,'runtime_summary':runtime_report.get('runtime_summary')}, sort_keys=True)
    rows={'prediction_runs':prediction_runs,'strategy_signals':strategy_signals,'profile_decisions':profile_decisions,'debug_decisions':debug_decisions,'execution_events':execution_events,'profile_metrics':profile_metrics,'strategy_metrics':list(strategy_metrics_by_id.values())}
    paper_rows=build_paper_basket_analytics_rows(report, stamp)
    profile_paper_rows=build_profile_decision_paper_analytics_rows(report, stamp)
    for table, table_rows in paper_rows.items():
        rows.setdefault(table, []).extend(table_rows)
    for table, table_rows in profile_paper_rows.items():
        rows.setdefault(table, []).extend(table_rows)
    return rows


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
    runtime_probabilities_path=runtime_dir/f'weather_runtime_cycle_probabilities_{stamp}.json'
    runtime_path=runtime_dir/f'weather_runtime_dryrun_{stamp}.json'
    ids_path=audit_dir/f'weather_runtime_ids_{stamp}.jsonl'
    audit_path=audit_dir/f'weather_runtime_audit_{stamp}.jsonl'
    probe_code=f"""
import json
import sys
from pathlib import Path
sys.path.insert(0, {str(Path(__file__).resolve().parent)!r})
from weather_cron_monitor_refresh import build_weather_model_probability_record
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
markets_for_runtime=[]; events=[]; probs={{}}; runtime_probs={{}}
for m in selected:
    tid=str(m.get('clob_token_id'))
    yes_ask=float(m.get('best_ask') or 0) or None
    yes_bid=float(m.get('best_bid') or 0)
    model_probability=build_weather_model_probability_record(m)
    probs[tid]=model_probability
    runtime_probs[tid]=round(min(0.99, max(0.0, (yes_ask or 0.01) + 0.05)), 6)
    markets_for_runtime.append({{'id':str(m.get('id')),'question':m.get('question'),'clob_token_id':tid,'clobTokenIds':[tid],'outcomes':['Yes'],'best_bid':yes_bid,'best_ask':yes_ask,'liquidity':float(m.get('volume') or m.get('ask_depth_usd') or 1000),'strategy_id':'weather_runtime_cycle_v1','profile_id':'runtime_cycle','closed':False,'probability_source':model_probability.get('source'),'probability_method':model_probability.get('method'),'forecast_source_provider':model_probability.get('forecast_source_provider'),'forecast_source_latency_tier':model_probability.get('forecast_source_latency_tier')}})
    bids=m.get('bids') or []; asks=m.get('asks') or []
    event={{'event_type':'book','asset_id':tid,'bids':bids[:10],'asks':asks[:10],'source_market_id':str(m.get('id')),'source':'live_gamma_clob_snapshot'}}
    if not event['asks'] and yes_ask: event['asks']=[{{'price':yes_ask,'size':float(m.get('best_ask_size') or 1)}}]
    if not event['bids'] and yes_bid: event['bids']=[{{'price':yes_bid,'size':float(m.get('best_bid_size') or 1)}}]
    events.append(event)
Path({str(markets_path)!r}).write_text(json.dumps(markets_for_runtime, indent=2, sort_keys=True), encoding='utf-8')
Path({str(events_path)!r}).write_text('\\n'.join(json.dumps(e, sort_keys=True) for e in events)+'\\n', encoding='utf-8')
Path({str(probabilities_path)!r}).write_text(json.dumps(probs, indent=2, sort_keys=True), encoding='utf-8')
Path({str(runtime_probabilities_path)!r}).write_text(json.dumps(runtime_probs, indent=2, sort_keys=True), encoding='utf-8')
print(json.dumps({{'selected':len(selected),'market_ids':[m.get('id') for m in selected]}}))
"""
    probe=run_cmd([PYTHON,'-c',probe_code], timeout=180)
    artifacts={'markets_json':str(markets_path),'events_jsonl':str(events_path),'probabilities_json':str(probabilities_path),'runtime_probabilities_json':str(runtime_probabilities_path),'runtime_json':str(runtime_path),'idempotency_jsonl':str(ids_path),'audit_jsonl':str(audit_path)}
    if probe.returncode != 0:
        return {'ok':False,'stage':'live_probe','paper_only':True,'error':probe.stderr[-2000:],'stdout':probe.stdout[-1000:],'artifacts':artifacts}
    cmd=[str(PREDICTION_CORE),'polymarket-runtime-cycle','--markets-json',str(markets_path),'--dry-run-events-jsonl',str(events_path),'--probabilities-json',str(runtime_probabilities_path),'--max-events','3','--paper-notional-usdc','5','--min-edge','0.02','--execution-mode','dry_run','--idempotency-jsonl',str(ids_path),'--audit-jsonl',str(audit_path),'--max-order-notional-usdc','5','--max-total-exposure-usdc','20','--max-daily-loss-usdc','10','--max-spread','0.05']
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
    live_readiness={'ready_for_live':False,'status':'paper_evaluation_required','remaining_conditions':['accumulate_24_48h_paper_runs','verify_profile_pnl_and_blockers_in_grafana','confirm_order_attribution_for_submitted_dry_run_orders','operator_live_ack_required','clob_credentials_and_kill_switch_preflight_required'],'live_order_allowed':False}
    report={'ok':True,'run_id':stamp,'paper_only':True,'no_real_orders':True,'runtime_execution_mode':runtime_execution_mode,'runtime_summary':{'processed_events':dry.get('marketdata',{}).get('processed_events') if isinstance(dry.get('marketdata'), dict) else None,'paper_signal_count':signal_count,'hold_count':runtime_summary.get('hold_count'),'orders_submitted':len(execution.get('orders_submitted',[])) if isinstance(execution, dict) else 0,'paper_intent_count':len(execution.get('paper_intents',[])) if isinstance(execution, dict) else 0,'weather_profile_count':weather_profiles['profile_count'],'weather_profile_strategy_count':weather_profiles['strategy_count'],'weather_profile_signal_count':weather_profiles['signal_count'],'weather_profile_decision_count':weather_profiles.get('decision_count',0),'weather_profile_enter_count':weather_profiles.get('enter_count',0),'weather_profile_skip_count':weather_profiles.get('skip_count',0)},'weather_profiles':weather_profiles,'execution_events':execution_events,'live_readiness':live_readiness,'operator_verdict':{'status':status,'reason':'runtime dry-run strategy refresh'},'runtime_watchlist':rows,'artifacts':artifacts}
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

def french_reason(text):
    if not text:
        return text
    replacements={
        'official Polymarket final outcome: Yes':'résultat final officiel Polymarket : Oui',
        'official Polymarket final outcome: No':'résultat final officiel Polymarket : Non',
        'p_side':'p_side',
        'hard_stop':'stop dur',
    }
    result=str(text)
    for old, new in replacements.items():
        result=result.replace(old, new)
    return result


def french_outcome(value):
    if value == 'Yes': return 'Oui'
    if value == 'No': return 'Non'
    return value or ''


def french_side(value):
    if value == 'yes': return 'oui'
    if value == 'no': return 'non'
    if value == 'skip': return 'ignorer'
    return value or ''


def french_decision_status(value):
    mapping={
        'paper_trade_small':'entrée paper limitée',
        'profile_enter_paper_planned':'entrée paper planifiée',
        'skip':'ignorer',
        'hold':'conserver',
    }
    return mapping.get(value, value or '')


def french_blocker(value):
    mapping={
        'edge_below_threshold':'edge sous le seuil',
        'execution_cost_exceeds_edge':'coût d’exécution supérieur à l’edge',
        'no_profile_candidate_market':'aucun marché candidat pour ce profil',
        'missing_probability':'probabilité manquante',
        'missing_liquidity':'liquidité manquante',
        'min_liquidity_not_met':'liquidité minimale non atteinte',
        'non_probability_signal':'signal sans probabilité exploitable',
        'synthetic_probability':'probabilité synthétique',
        'market_derived_probability_not_allowed':'probabilité dérivée du marché non autorisée',
        'circuit_breaker_tripped':'coupe-circuit activé',
        'max_open_positions_reached':'nombre maximal de positions ouvertes atteint',
        'daily_paper_loss_cap_reached':'limite de perte paper journalière atteinte',
        'deployed_capital_cap_reached':'limite de capital déployé atteinte',
    }
    return mapping.get(value, value)


def french_blockers(values):
    return ', '.join(french_blocker(str(value)) for value in values or [])


def french_action(value):
    mapping={
        'SETTLED_WON':'réglé gagné',
        'SETTLED_LOST':'réglé perdu',
        'EXIT_PAPER':'sortie paper',
        'HOLD_CAPPED':'conserver plafonné',
        'TRIM_OR_STOP_MONITOR':'surveiller réduction ou stop',
    }
    return mapping.get(value, value or '')


def french_action_counts(counts):
    if not counts:
        return '-'
    return ', '.join(f'{french_action(action)}={count}' for action, count in counts.items())


def french_analytics_rows(rows):
    if not isinstance(rows, dict):
        return '-'
    labels={
        'prediction_runs':'runs prédiction',
        'strategy_signals':'signaux stratégie',
        'profile_decisions':'décisions profil',
        'debug_decisions':'décisions debug',
        'execution_events':'événements exécution',
        'profile_metrics':'métriques profil',
        'strategy_metrics':'métriques stratégie',
        'paper_orders':'ordres paper',
        'paper_positions':'positions paper',
        'paper_pnl_snapshots':'snapshots PnL paper',
    }
    return ', '.join(f'{labels.get(key, key)}={value}' for key, value in rows.items())


def french_live_status(value):
    mapping={
        'paper_evaluation_required':'évaluation paper requise',
        'ready':'prêt',
        'blocked':'bloqué',
    }
    return mapping.get(value, value or '')


def french_bool(value):
    if value is True:
        return 'oui'
    if value is False:
        return 'non'
    return value


def french_mode(value):
    if value == 'dry_run':
        return 'paper à blanc'
    return value or ''


def french_live_condition(value):
    mapping={
        'accumulate_24_48h_paper_runs':'accumuler 24–48h de runs paper',
        'verify_profile_pnl_and_blockers_in_grafana':'vérifier PnL et blocages des profils dans Grafana',
        'confirm_order_attribution_for_submitted_dry_run_orders':'confirmer l’attribution des ordres à blanc soumis',
        'operator_live_ack_required':'validation live opérateur requise',
        'clob_credentials_and_kill_switch_preflight_required':'pré-vol identifiants CLOB et kill-switch requis',
    }
    return mapping.get(value, value)


def french_live_conditions(values):
    return ', '.join(french_live_condition(str(value)) for value in values or [])


def french_display_value(value):
    if value is None:
        return '-'
    return value


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
    out={'run_id':stamp,'runtime_execution_mode':runtime_report.get('runtime_execution_mode'),'summary':summary,'positions':refreshed,'alerts':alerts,'verify_forecast_source':[p.get('question') for p in verify],'closed_positions':closed,'runtime_strategies':runtime_report}
    out['analytics']=export_runtime_analytics(out, stamp)
    summary['analytics_inserted']=out['analytics'].get('inserted') if isinstance(out.get('analytics'), dict) else False
    summary['analytics_rows']=out['analytics'].get('rows') if isinstance(out.get('analytics'), dict) else {}
    runtime_report['analytics']=out['analytics']
    json_path=BASE/f'weather_paper_cron_monitor_{stamp}.json'
    md_path=BASE/f'weather_paper_cron_monitor_{stamp}.md'
    csv_path=BASE/f'weather_paper_cron_monitor_{stamp}.csv'
    write_json(json_path, out)
    fields=['city','date','question','side','temp','action','settlement_status','winning_outcome','official_settlement_status','official_winning_outcome','resolution_scheduled_at','resolution_checked_at','auto_check_at','auto_check_after_seconds','paper_settlement_value_usdc','official_paper_settlement_value_usdc','paper_realized_pnl_usdc','official_hold_to_settlement_pnl_usdc','p_side_now','hard_stop_if_p_below','trim_review_if_p_below','best_bid_now','best_ask_now','filled_usdc','paper_ev_now_usdc','paper_mtm_bid_usdc','current_forecast_max_c','forecast_query_used','official_resolution_source','resolution_source_newly_available','reason']
    with open(csv_path,'w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f, fieldnames=fields); w.writeheader()
        for p in refreshed + closed: w.writerow({k:p.get(k) for k in fields})
    lines=[]
    lines.append(f"# Monitoring cron météo paper — {stamp}")
    lines.append("")
    lines.append("Mode paper-only — aucun ordre réel placé. Aucun nouvel ajout sans demande explicite de Julien.")
    lines.append("")
    lines.append(f"Résumé : actifs={len(refreshed)}, sorties_préservées={len(closed)}, capital={spend:.4f} USDC, valeur attendue={ev:.4f} USDC, valeur au meilleur bid={mtm:.4f} USDC, actions={french_action_counts(counts)}, alertes={len(alerts)}")
    lines.append("")
    lines.append("## Stratégies exécutées")
    if runtime_report.get('ok'):
        rp=runtime_report.get('runtime_summary',{})
        wp=runtime_report.get('weather_profiles',{})
        an=runtime_report.get('analytics',{})
        lines.append(f"- Mode : `{french_mode(runtime_report.get('runtime_execution_mode'))}`")
        lines.append(f"- Profils météo : {wp.get('profile_count')} ; stratégies : {wp.get('strategy_count')} ; signaux : {wp.get('signal_count')} ; décisions : {wp.get('decision_count')} ; entrées={wp.get('enter_count')} ; ignorées={wp.get('skip_count')}")
        analytics_rows=an.get('rows') if isinstance(an.get('rows'), dict) else {}
        lines.append(f"- Exécution : événements traités={rp.get('processed_events')}, signaux paper={rp.get('paper_signal_count')}, ordres executor soumis={rp.get('orders_submitted')}, intentions paper={rp.get('paper_intent_count')}")
        lines.append(f"- Analytics paper : décisions d’entrée={wp.get('enter_count')}, lignes ordres paper={analytics_rows.get('paper_orders')}, lignes événements d’exécution={analytics_rows.get('execution_events')}")
        lines.append(f"- Grafana/ClickHouse : inséré={french_bool(an.get('inserted'))}, lignes={french_analytics_rows(an.get('rows'))}")
        lr=runtime_report.get('live_readiness') if isinstance(runtime_report.get('live_readiness'), dict) else {}
        lines.append(f"- Préparation live : prêt={french_bool(lr.get('ready_for_live'))} ; statut={french_live_status(lr.get('status'))} ; restant={french_live_conditions(lr.get('remaining_conditions'))}")
        decisions=wp.get('decisions') if isinstance(wp.get('decisions'), list) else []
        if decisions:
            lines.append("")
            lines.append("| Profil | Décision | Côté | Avantage | Confiance | Montant notionnel | Blocages |")
            lines.append("|---|---:|---:|---:|---:|---:|---|")
            for decision in decisions:
                blockers=french_blockers(decision.get('blockers') or []) if isinstance(decision, dict) else ''
                lines.append(f"| {decision.get('profile_id')} | {french_decision_status(decision.get('decision_status'))} | {french_side(decision.get('side'))} | {decision.get('edge')} | {decision.get('confidence')} | {decision.get('capped_spend_usdc')} | {blockers or '-'} |")
    else:
        lines.append(f"- FAILED stage={runtime_report.get('stage')} error={runtime_report.get('error')}")
    lines.append("")
    pr=portfolio_report
    pnl=pr['pnl_usdc']; pr_counts=pr['counts']
    lines.append("## PnL portefeuille")
    lines.append(f"- Comptes : ouvertes={pr_counts['open']}, réglées={pr_counts['settled']}, sorties_paper={pr_counts['exit_paper']}, total={pr_counts['total']}")
    lines.append(f"- Réalisé : {pnl['realized_total']:.6f} USDC (réglé={pnl['settled_realized']:.6f}, sortie_paper={pnl['exit_realized']:.6f})")
    lines.append(f"- Valeur des positions ouvertes au meilleur bid : {pnl['open_mtm_bid']:.6f} USDC")
    lines.append(f"- Réalisé + valeur ouverte au meilleur bid : {pnl['realized_plus_open_mtm']:.6f} USDC")
    lines.append(f"- Si les positions ouvertes perdent : {pnl['if_open_loses']:.6f} USDC ; si elles gagnent à 100% : {pnl['if_open_wins_full_payout']:.6f} USDC")
    lines.append(f"- Résultat officiel si les sorties paper avaient été conservées jusqu’au règlement : {pnl['official_hold_to_settlement_for_exits']:.6f} USDC (analyse après coup seulement ; ne réécrit pas le PnL de sortie)")
    lines.append("")
    if alerts:
        lines.append("## Alertes")
        for a in alerts:
            lines.append(f"- {french_action(a.get('action'))}: {a.get('city')} {a.get('date')} {a.get('side')}{a.get('temp')} — p={french_display_value(a.get('p_side_now'))} meilleur achat/vente={french_display_value(a.get('best_bid_now'))}/{french_display_value(a.get('best_ask_now'))} — {french_reason(a.get('reason'))}")
        lines.append("")
    lines.append("## Positions actives")
    lines.append("| Position | Action | Proba côté | meilleur achat/vente | Valeur attendue | Valeur bid | Prévision | Source officielle |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---|")
    for p in refreshed:
        pos=f"{p.get('city')} {p.get('date')} {p.get('side')}{p.get('temp')}"
        src=p.get('official_resolution_source') or 'manquante'
        lines.append(f"| {pos} | {french_action(p.get('action'))} | {french_display_value(p.get('p_side_now'))} | {french_display_value(p.get('best_bid_now'))}/{french_display_value(p.get('best_ask_now'))} | {french_display_value(p.get('paper_ev_now_usdc'))} | {french_display_value(p.get('paper_mtm_bid_usdc'))} | {french_display_value(p.get('current_forecast_max_c'))}°C via {french_display_value(p.get('forecast_query_used'))} | {src} |")
    lines.append("")
    if closed:
        lines.append("## Positions fermées / sorties")
        lines.append("| Position | Action | PnL sortie | Résultat officiel | Résultat officiel si conservé jusqu’au règlement |")
        lines.append("|---|---:|---:|---:|---:|")
        for p in closed:
            pos=f"{p.get('city')} {p.get('date')} {p.get('side')}{p.get('temp')}"
            official=french_action(p.get('official_settlement_status')) if p.get('official_settlement_status') else 'non vérifié'
            lines.append(f"| {pos} | {french_action(p.get('action'))} | {p.get('paper_realized_pnl_usdc')} | {official} {french_outcome(p.get('official_winning_outcome'))} | {p.get('official_hold_to_settlement_pnl_usdc')} |")
        lines.append("")
    lines.append(f"Artefacts : `{json_path}`, `{csv_path}`, `{md_path}`")
    md_path.write_text('\n'.join(lines)+'\n', encoding='utf-8')
    # Verification
    ok=json_path.exists() and csv_path.exists() and md_path.exists() and out['summary']['paper_only'] is True and out['summary']['no_real_order_placed'] is True and runtime_report.get('ok') is True
    runtime_summary=runtime_report.get('runtime_summary') if isinstance(runtime_report.get('runtime_summary'), dict) else {}
    analytics_rows=out.get('analytics',{}).get('rows') if isinstance(out.get('analytics'), dict) and isinstance(out.get('analytics',{}).get('rows'), dict) else {}
    print(json.dumps({'ok':ok,'json':str(json_path),'csv':str(csv_path),'md':str(md_path),'summary':summary,'runtime_strategies':{'ok':runtime_report.get('ok'),'mode':runtime_report.get('runtime_execution_mode'),'weather_profile_count':summary.get('weather_profile_count'),'weather_profile_strategy_count':summary.get('weather_profile_strategy_count'),'weather_profile_signal_count':summary.get('weather_profile_signal_count'),'weather_profile_decision_count':summary.get('weather_profile_decision_count'),'weather_profile_enter_count':summary.get('weather_profile_enter_count'),'weather_profile_skip_count':summary.get('weather_profile_skip_count'),'executor_orders_submitted':runtime_summary.get('orders_submitted'),'paper_intent_count':runtime_summary.get('paper_intent_count'),'analytics_paper_orders_rows':analytics_rows.get('paper_orders'),'analytics_execution_events_rows':analytics_rows.get('execution_events'),'analytics_inserted':summary.get('analytics_inserted')} ,'alerts':alerts}, ensure_ascii=False))
if __name__=='__main__': main()

