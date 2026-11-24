"""Calendar feasibility and observable-information checks; no market outcomes."""
from dataclasses import replace
from decimal import Decimal
from itertools import combinations
import random
import unittest
from unittest.mock import Mock

from spy_backtest_audit.controls import sample_calendar, mean_entry_volatility
from spy_backtest_audit.backtest import simulate
from spy_backtest_audit.signals import ScheduledTrade
from tests.test_signals import bars_from_returns
class ControlTests(unittest.TestCase):
    def test_seed_reproduces_calendar_and_prices_do_not_affect_sampling(self):
        bars = bars_from_returns(["0.01"] * 40)
        first = sample_calendar(bars, 4, 5, 3, random.Random(1729))
        changed = tuple(replace(b, close=b.close * 100) for b in bars)
        self.assertEqual(first, sample_calendar(changed, 4, 5, 3, random.Random(1729)))
        self.assertNotEqual(first, sample_calendar(bars, 4, 5, 3, random.Random(1730)))
    def test_count_duration_nonoverlap_and_bounds(self):
        bars = bars_from_returns(["0.01"] * 100)
        positions = {bar.date: i for i, bar in enumerate(bars)}
        rng = random.Random(1729)
        for _ in range(30):
            schedule = sample_calendar(bars, 22, 8, 5, rng)
            self.assertEqual(len(schedule), 8)
            previous_exit = -1
            for trade in schedule:
                e, x = positions[trade.entry_date], positions[trade.exit_date]
                self.assertGreaterEqual(e, 22)
                self.assertEqual(x - e, 5)
                self.assertGreater(e, previous_exit)
                self.assertEqual(trade.signal_date, bars[e-1].date)
                previous_exit = x
            result = simulate(bars[22:], schedule, Decimal(5))
            self.assertEqual(len(result.trades), 8)
            self.assertEqual(result.terminal_liquidations, 0)
    def test_compressed_sampler_covers_each_small_feasible_calendar_once(self):
        # Six eligible sessions, two 1-interval trades: six feasible schedules.
        bars = bars_from_returns(["0"] * 6)
        expected = {(a, b) for a, b in combinations(range(1, 6), 2) if b > a + 1}
        actual = set()
        for slots in combinations(range(4), 2):
            rng = Mock()
            rng.sample.return_value = slots
            schedule = sample_calendar(bars, 1, 2, 1, rng)
            entries = tuple((t.entry_date - bars[0].date).days for t in schedule)
            self.assertNotIn(entries, actual)
            actual.add(entries)
        self.assertEqual(actual, expected)
    def test_infeasible_calendars_rejected(self):
        bars = bars_from_returns(["0"] * 10)
        for first, count, holding in ((0, 1, 1), (1, 0, 1), (1, 1, 0), (1, 4, 5)):
            with self.subTest(first=first, count=count, holding=holding), self.assertRaises(ValueError):
                sample_calendar(bars, first, count, holding, random.Random(1))
    def test_entry_volatility_does_not_use_entry_or_future_prices(self):
        bars = bars_from_returns(["0.01", "-0.01", "0.01", "-0.02", "0.5", "0"])
        schedule = (ScheduledTrade(bars[4].date, bars[5].date, bars[6].date, "scheduled"),)
        changed = bars[:5] + tuple(replace(b, close=b.close * 10) for b in bars[5:])
        self.assertEqual(mean_entry_volatility(bars, schedule, 3),
                         mean_entry_volatility(changed, schedule, 3))
    def test_workflow_records_every_draw_and_excludes_validation(self):
        from datetime import date
        import json
        from pathlib import Path
        import tempfile
        from spy_backtest_audit.data import Snapshot
        from spy_backtest_audit.workflow import write_signal_artifacts, write_backtest_artifacts, write_control_artifacts

        project = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "research").mkdir()
            for name in ("strategy", "execution", "data_plan", "controls", "diagnostics"):
                config = json.loads((project / f"research/{name}.json").read_text())
                if name == "strategy":
                    config["lookback_sessions"] = 3
                    config["holding_open_intervals"] = 2
                if name == "controls":
                    config["calendars"] = 3
                (root / f"research/{name}.json").write_text(json.dumps(config))
            bars = bars_from_returns(["0.01", "-0.01", "0.01", "-0.1"] + ["0"] * 20,
                                     start=date(2000, 1, 1))
            validation = replace(bars[-1], date=date(2016, 1, 4), close=Decimal(99999))
            snapshot = Snapshot(bars + (validation,), "synthetic", "synthetic", "SPY")
            signals, _ = write_signal_artifacts(root, snapshot)
            write_backtest_artifacts(root, snapshot, signals)
            summary, output = write_control_artifacts(root, snapshot, signals)
            self.assertEqual(summary["matched_trades"], 1)
            diagnostic_dir = root / "outputs/diagnostics"
            details = json.loads((diagnostic_dir / "summary.json").read_text())
            self.assertEqual(details["stage"], "development_exploratory_temporal_diagnostics")
            self.assertTrue(all(c["dip"]["last_date"] < "2016-01-01" for c in details["comparisons"]))
            import csv
            with (output / "calendars.csv").open() as stream:
                calendar_rows = list(csv.DictReader(stream))
            self.assertEqual(len(calendar_rows), 3)
            self.assertTrue(all(r["exit_date"] < "2016-01-01" for r in calendar_rows))
            first = {p.name: p.read_bytes() for p in output.iterdir()}
            write_control_artifacts(root, snapshot, signals)
            self.assertEqual(first, {p.name: p.read_bytes() for p in output.iterdir()})
            pending = replace(signals.trades[0], exit_date=None, status="awaiting_exit")
            with self.assertRaisesRegex(ValueError, "pending"):
                write_control_artifacts(root, snapshot, replace(signals, trades=(pending,)))


if __name__ == "__main__":
    unittest.main()
