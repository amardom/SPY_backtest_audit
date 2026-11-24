"""Hand-checkable synthetic calendars; no real strategy returns are inspected."""
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
import json
from pathlib import Path
import statistics
import tempfile
import unittest

from spy_backtest_audit.data import DailyBar, Snapshot
from spy_backtest_audit.signals import Strategy, generate_signals
from spy_backtest_audit.workflow import write_signal_artifacts
def bars_from_returns(returns, start=date(2020, 1, 1)):
    price = Decimal("100")
    bars = [DailyBar(start, price, price, price, price, price, 1000, Decimal(0), Decimal(1))]
    for i, value in enumerate(returns, 1):
        price *= 1 + Decimal(str(value))
        bars.append(DailyBar(start + timedelta(days=i), price, price, price, price,
                             price, 1000, Decimal(0), Decimal(1)))
    return tuple(bars)
class SignalTests(unittest.TestCase):
    def test_prior_volatility_excludes_shock_and_uses_sample_denominator(self):
        bars = bars_from_returns(["0.01", "-0.01", "0.01", "-0.10", "0", "0", "0", "0"])
        result = generate_signals(bars, Strategy(3, Decimal(2), 2))
        event = result.events[0]
        expected = statistics.stdev([Decimal("0.01"), Decimal("-0.01"), Decimal("0.01")])
        self.assertEqual(event.signal_date, bars[4].date)
        self.assertEqual(event.prior_volatility, expected)
        self.assertEqual(event.daily_return, Decimal("-0.1"))
        self.assertEqual(result.trades[0].entry_date, bars[5].date)
        self.assertEqual(result.trades[0].exit_date, bars[7].date)
    def test_five_open_intervals_and_next_session_entry(self):
        bars = bars_from_returns(["0.01", "-0.01", "0.01", "-0.10"] + ["0"] * 7)
        trade = generate_signals(bars, Strategy(3, Decimal(2), 5)).trades[0]
        self.assertEqual(trade.signal_date, bars[4].date)
        self.assertEqual(trade.entry_date, bars[5].date)
        self.assertEqual(trade.exit_date, bars[10].date)
        self.assertEqual(trade.status, "scheduled")
    def test_signals_ignored_until_exit_and_exit_close_can_trigger(self):
        bars = bars_from_returns(["0.01", "-0.01", "0.01", "-0.1", "-0.2", "-0.3", "-0.4", "-0.5", "-0.6"])
        result = generate_signals(bars, Strategy(3, Decimal("0.5"), 3))
        decisions = {e.signal_date: e.decision for e in result.events}
        self.assertEqual(decisions[bars[4].date], "enter_next_open")
        for i in (5, 6, 7):
            self.assertEqual(decisions[bars[i].date], "ignored_holding")
        self.assertEqual(decisions[bars[8].date], "enter_next_open")
        self.assertEqual(result.trades[0].exit_date, bars[8].date)
        self.assertEqual(result.trades[1].entry_date, bars[9].date)
    def test_dividend_drop_is_not_an_economic_loss(self):
        bars = list(bars_from_returns(["0.01", "-0.01", "0.01", "0"]))
        close = bars[3].close - 5
        bars[4] = replace(bars[4], open=close, high=close, low=close, close=close,
                          adjusted_close=close, dividend=Decimal(5))
        self.assertFalse(generate_signals(tuple(bars), Strategy(3, Decimal(2), 5)).events)
    def test_vendor_adjusted_close_does_not_control_signals(self):
        bars = bars_from_returns(["0.01", "-0.01", "0.01", "-0.1", "0", "0"])
        modified = tuple(replace(b, adjusted_close=Decimal(1)) for b in bars)
        strategy = Strategy(3, Decimal(2), 2)
        self.assertEqual(generate_signals(bars, strategy), generate_signals(modified, strategy))
    def test_future_prices_do_not_change_past_decisions(self):
        bars = bars_from_returns(["0.01", "-0.01", "0.01", "-0.1", "0", "-0.3", "0", "0", "0"])
        strategy = Strategy(3, Decimal(2), 2)
        cutoff = 6
        modified = bars[:cutoff+1] + tuple(replace(b, close=b.close * 100) for b in bars[cutoff+1:])
        expected = [e for e in generate_signals(bars, strategy).events if e.signal_date <= bars[cutoff].date]
        actual = [e for e in generate_signals(modified, strategy).events if e.signal_date <= bars[cutoff].date]
        self.assertEqual(actual, expected)
        self.assertEqual(list(generate_signals(bars[:cutoff+1], strategy).events), expected)
    def test_tail_signal_retained_without_future_entry_or_exit(self):
        bars = bars_from_returns(["0.01", "-0.01", "0.01", "-0.1", "0"])
        strategy = Strategy(3, Decimal(2), 5)
        pending = generate_signals(bars[:-1], strategy).trades[0]
        self.assertEqual(pending.status, "awaiting_entry")
        self.assertIsNone(pending.entry_date)
        self.assertIsNone(pending.exit_date)
        pending = generate_signals(bars, strategy).trades[0]
        self.assertEqual(pending.status, "awaiting_exit")
        self.assertEqual(pending.entry_date, bars[5].date)
        self.assertIsNone(pending.exit_date)
    def test_zero_volatility_and_insufficient_history_do_not_trigger(self):
        bars = bars_from_returns(["0", "0", "0", "-0.5"])
        self.assertFalse(generate_signals(bars, Strategy(3, Decimal(2), 5)).events)
        self.assertFalse(generate_signals(bars, Strategy()).events)
        self.assertFalse(generate_signals((), Strategy()).events)
    def test_splits_unsorted_bars_and_invalid_parameters_rejected(self):
        bars = bars_from_returns(["0.01", "-0.01", "0.01", "-0.1"])
        with self.assertRaisesRegex(ValueError, "Split-event"):
            generate_signals((replace(bars[0], split_factor=Decimal(2)),) + bars[1:], Strategy())
        with self.assertRaisesRegex(ValueError, "strictly ordered"):
            generate_signals(tuple(reversed(bars)), Strategy())
        for args in ((1, Decimal(2), 5), (20, Decimal(0), 5), (20, Decimal("NaN"), 5), (20, Decimal(2), 0)):
            with self.subTest(args=args), self.assertRaises(ValueError):
                Strategy(*args)
    def test_development_artifacts_do_not_use_validation_to_finish_trade(self):
        root_of_project = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "research").mkdir()
            plan = json.loads((root_of_project / "research/data_plan.json").read_text())
            config = json.loads((root_of_project / "research/strategy.json").read_text())
            config["lookback_sessions"] = 3
            (root / "research/data_plan.json").write_text(json.dumps(plan))
            (root / "research/strategy.json").write_text(json.dumps(config))
            bars = bars_from_returns(["0.01", "-0.01", "0.01", "-0.1"] + ["0"] * 10,
                                     start=date(2015, 12, 26))
            result, output = write_signal_artifacts(root, Snapshot(bars, "synthetic", "synthetic", "SPY"))
            self.assertEqual(result.trades[0].status, "awaiting_exit")
            self.assertEqual(result.trades[0].entry_date, date(2015, 12, 31))
            self.assertIsNone(result.trades[0].exit_date)
            metadata = json.loads((output / "run.json").read_text())
            self.assertFalse(metadata["performance_evaluated"])
            first = {p.name: p.read_bytes() for p in output.iterdir()}
            write_signal_artifacts(root, Snapshot(bars, "synthetic", "synthetic", "SPY"))
            self.assertEqual(first, {p.name: p.read_bytes() for p in output.iterdir()})


if __name__ == "__main__":
    unittest.main()
