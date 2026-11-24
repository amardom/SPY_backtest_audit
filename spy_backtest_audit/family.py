"""Evaluate the recorded lookback, threshold and holding-period grid."""
import csv
from dataclasses import asdict
from datetime import date, timedelta
from decimal import Decimal, localcontext
import hashlib
from itertools import product
import json
import random

from .backtest import simulate, ExecutedTrade
from .controls import sample_calendar
from .diagnostics import quantiles
from .protocol import verify_validation_freeze
from .signals import Strategy, ScheduledTrade, generate_signals
from .validation import prepare_validation
def unit_factors(bars, holding, fee):
    """Reuse the accounting engine for every feasible isolated full trade."""
    return tuple(Decimal(1) + simulate(bars[e:e+holding+1],
        (ScheduledTrade(bars[e].date-timedelta(days=1), bars[e].date, bars[e+holding].date, 'scheduled'),),
        fee, Decimal(1)).total_return for e in range(len(bars)-holding))
def calendar_return(entries, factors, holding):
    if any(type(e) is not int or not 0 <= e < len(factors) for e in entries):
        raise ValueError('Control entry outside factor table')
    if any(b <= a + holding for a, b in zip(entries, entries[1:])):
        raise ValueError('Control positions overlap or violate next-session entry rule')
    with localcontext() as context:
        context.prec = 28
        wealth = Decimal(1)
        for e in entries:
            wealth *= factors[e]
        return wealth - 1
def prepare_period(bars, plan, period, strategy):
    if period not in ('development', 'validation'):
        raise ValueError('Family cannot access final evaluation')
    start, end = (date.fromisoformat(plan[period][k]) for k in ('start', 'end_exclusive'))
    if end > date.fromisoformat(plan['final_evaluation']['start']):
        raise ValueError('Family window crosses final evaluation')
    if period == 'validation':
        context, first, signals = prepare_validation(bars, start, end, strategy)
    else:
        context = tuple(b for b in bars if start <= b.date < end)
        first = strategy.lookback_sessions + 2
        signals = generate_signals(context, strategy)
    return context, first, signals
def reconcile_primary(root, row):
    folder = 'backtest' if row['period'] == 'development' else 'validation'
    summary = json.loads((root / f'outputs/{folder}/summary.json').read_text())
    original = next(s for s in summary['scenarios'] if s['strategy']=='dip' and s['cost_bps_per_side']=='5')
    for key, original_key in (('net_return','total_return'),('max_close_drawdown','max_close_drawdown')):
        if abs(Decimal(row[key])-Decimal(original[original_key])) > Decimal('1e-20'):
            raise ValueError('Parameter family primary differs from original result')
    if row['trades'] != original['trades']:
        raise ValueError('Primary trade count differs')
    if row['period'] == 'development':
        reference = json.loads((root/'outputs/controls/summary.json').read_text())['control_return_quantiles_nearest_rank']['p50']
    else:
        reference = summary['control_return_quantiles']['p50']
    if abs(Decimal(row['control_median'])-Decimal(reference)) > Decimal('1e-20'):
        raise ValueError('Primary random-reference median differs')
def write_family_artifacts(root, snapshot):
    freeze = verify_validation_freeze(root)
    if snapshot.sha256 != freeze['snapshot_sha256']:
        raise ValueError('Family snapshot differs from original freeze')
    record_path = root/'research/parameter_family_plan_record.json'
    record = json.loads(record_path.read_text())
    for name, expected in record['file_sha256'].items():
        if hashlib.sha256((root/name).read_bytes()).hexdigest() != expected:
            raise ValueError('Family plan or original observation changed')
    cfg = json.loads((root/'research/parameter_family.json').read_text())
    plan = json.loads((root/'research/data_plan.json').read_text())
    execution = json.loads((root/'research/execution.json').read_text())
    capital, fee = Decimal(execution['initial_capital_usd']), Decimal(cfg['cost_bps_per_side'])
    if fee != Decimal(execution['primary_cost_bps_per_side']) or cfg['selection'] != 'none':
        raise ValueError('Unsupported family specification')
    output = root/'outputs/parameter_family'
    output.mkdir(parents=True, exist_ok=True)
    rows, factors_cache = [], {}
    with (output/'controls.csv').open('w',encoding='utf-8',newline='') as cs, (output/'trades.csv').open('w',encoding='utf-8',newline='') as ts:
        cw = csv.writer(cs,lineterminator='\n')
        cw.writerow(('period','cell','draw','net_return','entry_indices'))
        tw = csv.writer(ts,lineterminator='\n')
        tw.writerow(('period','cell',*tuple(ExecutedTrade.__dataclass_fields__)))
        for period in cfg['periods']:
            for lookback, threshold, holding in product(cfg['lookback_sessions'],cfg['threshold_sigma'],cfg['holding_open_intervals']):
                strategy = Strategy(lookback,Decimal(threshold),holding)
                context, first, signals = prepare_period(snapshot.bars,plan,period,strategy)
                evaluation = context[first:]
                result = simulate(evaluation,signals.trades,fee,capital)
                cell = f'L{lookback}_S{threshold}_H{holding}'
                for trade in result.trades:
                    tw.writerow((period,cell,*asdict(trade).values()))
                values = []
                if result.trades:
                    key = (period,lookback if period=='development' else 0,holding)
                    if key not in factors_cache:
                        factors_cache[key] = unit_factors(evaluation,holding,fee)
                    factors = factors_cache[key]
                    positions = {b.date:i for i,b in enumerate(evaluation)}
                    rng = random.Random(cfg['seed'])
                    for draw in range(cfg['calendars']):
                        calendar = sample_calendar(context,first,len(result.trades),holding,rng)
                        entries = tuple(positions[t.entry_date] for t in calendar)
                        value = calendar_return(entries,factors,holding)
                        if draw == 0 and abs(value-simulate(evaluation,calendar,fee,capital).total_return)>Decimal('1e-20'):
                            raise ValueError('Accelerated control differs from accounting engine')
                        cw.writerow((period,cell,draw,str(value),' '.join(map(str,entries))))
                        values.append(value)
                median = Decimal(quantiles(sorted(values))['p50']) if values else None
                primary = [lookback,threshold,holding] == cfg['primary']
                row = dict(period=period,cell=cell,lookback_sessions=lookback,threshold_sigma=threshold,
                    holding_open_intervals=holding,primary=primary,evaluation_start=str(evaluation[0].date),
                    evaluation_end=str(evaluation[-1].date),trades=len(result.trades),terminal_liquidations=result.terminal_liquidations,
                    net_return=str(result.total_return),max_close_drawdown=str(result.max_drawdown),
                    control_median=str(median) if median is not None else None,
                    contrast_pp=str((result.total_return-median)*100) if median is not None else None,controls=len(values))
                if primary:
                    reconcile_primary(root,row)
                rows.append(row)
            print(f'Parameter family: {period}, 27 cells completed.',flush=True)
    with (output/'metrics.csv').open('w',encoding='utf-8',newline='') as stream:
        writer = csv.DictWriter(stream,fieldnames=tuple(rows[0]),lineterminator='\n')
        writer.writeheader(); writer.writerows(rows)
    sources = ['research/parameter_family.json','research/parameter_family_rules.md','research/parameter_family_plan_record.json',
               'research/data_plan.json','research/execution.json','research/strategy.json','research/validation_first_observation.json',
               'outputs/backtest/summary.json','outputs/controls/summary.json','outputs/validation/summary.json']
    summary = dict(stage=cfg['stage'],config=cfg,snapshot_sha256=snapshot.sha256,results=rows,
        source_sha256={s:hashlib.sha256((root/s).read_bytes()).hexdigest() for s in sources},
        code_sha256={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((root/'spy_backtest_audit').glob('*.py'))},
        positive_counts={period:dict(net_return=sum(Decimal(x['net_return'])>0 for x in rows if x['period']==period),
            contrast=sum(x['contrast_pp'] is not None and Decimal(x['contrast_pp'])>0 for x in rows if x['period']==period)) for period in cfg['periods']},
        original_validation_screen='unchanged',selected_replacement=None,final_evaluation='not_accessed')
    (output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    return summary,output
