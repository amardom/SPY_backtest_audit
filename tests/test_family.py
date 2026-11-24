"""Family accounting, temporal boundaries and original-result safeguards."""
from datetime import date
from decimal import Decimal
from itertools import combinations
import json
from pathlib import Path
import tempfile
import unittest

from spy_backtest_audit.backtest import simulate
from spy_backtest_audit.family import unit_factors, calendar_return, prepare_period, reconcile_primary
from spy_backtest_audit.signals import Strategy, ScheduledTrade
from tests.test_backtest import bars
class FamilyTests(unittest.TestCase):
    def test_factor_product_matches_full_accounting_with_dividends_and_fees(self):
        data = bars([100,102,99,105,101,104,107,100,109],dividends=[1,0,2,0,1,0,3,0,2])
        for horizon in (1,2,3):
            for fee in (Decimal(0),Decimal(5),Decimal(10)):
                factors = unit_factors(data,horizon,fee)
                for count in (1,2):
                    for entries in combinations(range(1,len(factors)),count):
                        if any(b<=a+horizon for a,b in zip(entries,entries[1:])):
                            continue
                        schedule=tuple(ScheduledTrade(data[e-1].date,data[e].date,data[e+horizon].date,'scheduled') for e in entries)
                        actual=simulate(data,schedule,fee,Decimal('12345.67')).total_return
                        self.assertLess(abs(calendar_return(entries,factors,horizon)-actual),Decimal('1e-20'))
    def test_invalid_calendars_rejected(self):
        for entries in ((-1,),(4,),(0,1),(2,0),(0,0)):
            with self.subTest(entries=entries),self.assertRaises(ValueError):
                calendar_return(entries,(Decimal(1),)*4,1)
        self.assertEqual(calendar_return((),(Decimal(1),),1),0)
    def test_family_rejects_final_period(self):
        with self.assertRaisesRegex(ValueError,'final evaluation'):
            prepare_period((),{},'final_evaluation',Strategy())
    def test_validation_warmup_and_horizon_cutoff(self):
        data=bars([100,102,99,101,95,102,98,104,96,105,97,103,95,104,98,106,97,103,94,107])
        plan={'validation':{'start':str(data[8].date),'end_exclusive':str(data[-1].date)},'final_evaluation':{'start':str(data[-1].date)}}
        context,first,signals=prepare_period(data,plan,'validation',Strategy(3,Decimal('.1'),3))
        self.assertEqual(context[first].date,data[9].date)
        self.assertTrue(signals.trades)
        for trade in signals.trades:
            self.assertGreaterEqual(trade.signal_date,data[8].date)
            self.assertLess(trade.exit_date,data[-1].date)
            self.assertEqual(trade.status,'scheduled')
    def test_primary_reconciliation_rejects_changed_returns(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'outputs/validation').mkdir(parents=True)
            summary={'scenarios':[dict(strategy='dip',cost_bps_per_side='5',total_return='.1',max_close_drawdown='-.2',trades=3)],'control_return_quantiles':{'p50':'.05'}}
            (root/'outputs/validation/summary.json').write_text(json.dumps(summary))
            row=dict(period='validation',net_return='.1',max_close_drawdown='-.2',trades=3,control_median='.05')
            reconcile_primary(root,row)
            for key,value in (('net_return','.2'),('trades',4),('control_median','.2')):
                with self.subTest(key=key),self.assertRaises(ValueError):
                    reconcile_primary(root,dict(row,**{key:value}))
