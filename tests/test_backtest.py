"""Small hand-computable examples for fills, dividends and cash accounting."""
from datetime import date, timedelta
from decimal import Decimal
import unittest

from spy_backtest_audit.backtest import simulate
from spy_backtest_audit.data import DailyBar
from spy_backtest_audit.signals import ScheduledTrade


D = Decimal
def bars(opens, closes=None, dividends=None):
    closes = opens if closes is None else closes
    dividends = [0] * len(opens) if dividends is None else dividends
    result = []
    for i, (opening, closing, dividend) in enumerate(zip(opens, closes, dividends)):
        o, c = D(str(opening)), D(str(closing))
        result.append(DailyBar(date(2020, 1, 1) + timedelta(days=i), o, max(o, c), min(o, c),
                               c, c, 1000, D(str(dividend)), D(1)))
    return tuple(result)
def trade(data, entry, exit=None):
    return ScheduledTrade(data[entry-1].date, data[entry].date,
                          data[exit].date if exit is not None else None,
                          "scheduled" if exit is not None else "awaiting_exit")
class AccountingTests(unittest.TestCase):
    def test_scheduled_entry_exit_use_opens_not_closes(self):
        data = bars([100, 100, 110], [100, 150, 20])
        result = simulate(data, (trade(data, 1, 2),), D(0), D(1000))
        self.assertEqual(result.total_return, D("0.1"))
        self.assertEqual(result.trades[0].entry_price, D(100))
        self.assertEqual(result.trades[0].exit_price, D(110))
        self.assertEqual(result.trades[0].exit_reason, "scheduled_open")
    def test_proportional_cost_on_both_sides(self):
        data = bars([100, 100, 110])
        result = simulate(data, (trade(data, 1, 2),), D(100), D(1000))
        expected = D("1.1") * D("0.99") / D("1.01") - 1
        self.assertAlmostEqual(result.total_return, expected, places=25)
        execution = result.trades[0]
        self.assertEqual(result.total_cost, execution.entry_cost + execution.exit_cost)
        self.assertAlmostEqual(result.equity[-1].cash, D(1000) + execution.shares * 10 - result.total_cost, places=23)
    def test_entry_day_dividend_excluded_exit_day_included(self):
        data = bars([100, 100, 100], dividends=[0, 5, 7])
        result = simulate(data, (trade(data, 1, 2),), D(0), D(1000))
        self.assertEqual(result.trades[0].dividends, D(70))
        self.assertEqual(result.total_return, D("0.07"))
    def test_dividend_cash_not_reinvested_until_next_entry(self):
        data = bars([100] * 6, dividends=[0, 0, 2, 0, 0, 0])
        result = simulate(data, (trade(data, 1, 3), trade(data, 4, 5)), D(0), D(1000))
        self.assertEqual(result.equity[2].shares, D(10))
        self.assertEqual(result.equity[2].cash, D(20))
        self.assertEqual(result.trades[1].shares, D("10.2"))
        self.assertEqual(result.total_return, D("0.02"))
    def test_pending_exit_is_liquidated_at_terminal_close_with_cost(self):
        data = bars([100, 100, 100], [100, 100, 120])
        result = simulate(data, (trade(data, 1),), D(5), D(1000))
        expected = D("1.2") * (1 - D("0.0005")) / (1 + D("0.0005")) - 1
        self.assertAlmostEqual(result.total_return, expected, places=25)
        self.assertEqual(result.terminal_liquidations, 1)
        self.assertEqual(result.trades[0].exit_reason, "terminal_close")
        self.assertEqual(result.equity[-1].shares, 0)
    def test_unavailable_entry_does_not_create_trade(self):
        data = bars([100, 100])
        pending = ScheduledTrade(data[-1].date, None, None, "awaiting_entry")
        result = simulate(data, (pending,), D(10), D(1000))
        self.assertFalse(result.trades)
        self.assertEqual(result.total_return, 0)
        self.assertEqual(result.total_cost, 0)
    def test_close_drawdown_and_cash_baseline(self):
        data = bars([100, 100, 90, 120])
        result = simulate(data, (trade(data, 1),), D(0), D(1000))
        self.assertEqual(result.max_drawdown, D("-0.1"))
        cash = simulate(data, (), D(10), D(1000))
        self.assertEqual(cash.total_return, 0)
        self.assertEqual(cash.max_drawdown, 0)
    def test_overlap_and_invalid_costs_rejected(self):
        data = bars([100] * 5)
        with self.assertRaisesRegex(ValueError, "Overlapping"):
            simulate(data, (trade(data, 1, 4), trade(data, 2, 3)), D(0))
        for fee in (D(-1), D(10000), D("NaN")):
            with self.subTest(fee=fee), self.assertRaises(ValueError):
                simulate(data, (), fee)
    def test_higher_costs_reduce_same_calendar_return(self):
        data = bars([100, 100, 110, 110, 120])
        schedule = (trade(data, 1, 2), trade(data, 3, 4))
        values = [simulate(data, schedule, D(fee)).total_return for fee in (0, 5, 10)]
        self.assertGreater(values[0], values[1])
        self.assertGreater(values[1], values[2])


if __name__ == "__main__":
    unittest.main()
