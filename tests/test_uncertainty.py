"""Synthetic implementation checks, not claims of nominal empirical coverage."""
import csv
from dataclasses import asdict
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import unittest

try:
    import numpy as np
    from spy_backtest_audit.uncertainty import bootstrap_mean, stationary_indices, daily_log_growth, paired_difference, reconstruct_paired_series
except ImportError:
    np = None

from spy_backtest_audit.backtest import simulate
from spy_backtest_audit.data import Snapshot
from tests.test_backtest import bars, trade
@unittest.skipIf(np is None, "Install pinned NumPy dependency")
class UncertaintyTests(unittest.TestCase):
    def test_circular_continuation_and_restart_rule(self):
        class Fixed:
            def integers(self, low, high, size):
                return np.full(size, high-1)
            def random(self, size):
                return np.ones(size) * .9
        indices = stationary_indices(5, 2, 5, Fixed())
        np.testing.assert_array_equal(indices, [[4, 0, 1, 2, 3]] * 2)
        np.testing.assert_array_equal(stationary_indices(5, 2, 1, Fixed()), [[4]*5]*2)
    def test_constant_contrast_has_degenerate_interval(self):
        result = bootstrap_mean(np.full(100, .0004), mean_block=20, resamples=200, seed=1, period_code=0)
        self.assertAlmostEqual(result["lower"], .0004, places=15)
        self.assertAlmostEqual(result["upper"], .0004, places=15)
        self.assertLess(result["bootstrap_standard_error"], 1e-15)
    def test_paired_identical_portfolios_cancel(self):
        days = [1, 2, 3, 4]
        values = [.01, -.03, .02, .001]
        delta = paired_difference(days, values, days, values)
        result = bootstrap_mean(delta, mean_block=2, resamples=50, seed=1, period_code=0)
        self.assertEqual(result["point"], 0)
        self.assertEqual(result["lower"], 0)
        self.assertEqual(result["upper"], 0)
    def test_seed_reproducibility_and_independent_period_streams(self):
        values = np.arange(100, dtype=float)/10000
        kwargs = dict(mean_block=5, resamples=200, seed=314159, period_code=0)
        first = bootstrap_mean(values, **kwargs)
        second = bootstrap_mean(values, **kwargs)
        np.testing.assert_array_equal(first["means"], second["means"])
        changed = bootstrap_mean(values, **dict(kwargs, period_code=1))
        self.assertFalse(np.array_equal(first["means"], changed["means"]))
        self.assertEqual(first["point"], changed["point"])
    def test_correlated_synthetic_series_has_larger_block_uncertainty(self):
        rng = np.random.default_rng(42)
        innovations = rng.normal(0, .001, 612)
        series = np.zeros(612)
        for t in range(1, len(series)):
            series[t] = .8*series[t-1] + innovations[t]
        observed = series[100:]
        iid = bootstrap_mean(observed, mean_block=1, resamples=800, seed=123, period_code=0)
        dependent = bootstrap_mean(observed, mean_block=20, resamples=800, seed=123, period_code=0)
        self.assertGreater(dependent["bootstrap_standard_error"], iid["bootstrap_standard_error"]*1.3)
        self.assertEqual(dependent["point"], iid["point"])
    def test_log_growth_reconciles_with_total_wealth(self):
        data = bars([100, 100, 110], dividends=[0, 0, 2])
        result = simulate(data, (trade(data, 1, 2),), Decimal(5), Decimal(1000))
        values = daily_log_growth(result.equity, Decimal(1000))
        self.assertAlmostEqual(float(values.sum()), float(np.log1p(float(result.total_return))), places=12)
    def test_bad_alignment_values_and_parameters_rejected(self):
        for args in (([1,2], [0,0], [1,3], [0,0]), ([1,2], [0], [1,2], [0,0]),
                     ([1,2], [0,float("nan")], [1,2], [0,0])):
            with self.subTest(args=args), self.assertRaises(ValueError):
                paired_difference(*args)
        for mean in (0, 11, True):
            with self.subTest(mean=mean), self.assertRaises(ValueError):
                bootstrap_mean(np.zeros(10), mean_block=mean, resamples=20, seed=1, period_code=0)
        for values in ([1], [1,float("inf")], [[1,2],[3,4]]):
            with self.subTest(values=values), self.assertRaises(ValueError):
                bootstrap_mean(values, mean_block=1, resamples=20, seed=1, period_code=0)
    def test_archived_control_reconstruction_and_tamper_detection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "outputs/backtest").mkdir(parents=True)
            (root / "outputs/controls").mkdir()
            data = bars([100, 100, 110, 105])
            schedule = (trade(data, 1, 2),)
            result = simulate(data, schedule, Decimal(5), Decimal(1000))
            def write(path, records):
                with path.open("w", newline="") as stream:
                    writer = csv.DictWriter(stream, fieldnames=tuple(records[0]))
                    writer.writeheader(); writer.writerows(records)
            write(root / "outputs/backtest/dip_5bps_equity.csv", [asdict(p) for p in result.equity])
            write(root / "outputs/controls/calendars.csv", [dict(draw=0, decision_date=schedule[0].signal_date,
                  entry_date=schedule[0].entry_date, exit_date=schedule[0].exit_date)])
            recorded = dict(draw=0, total_return=str(result.total_return), trades=1)
            write(root / "outputs/controls/draws.csv", [recorded])
            summary = dict(execution={"primary_cost_bps_per_side":"5"},
                           scenarios=[dict(strategy="dip", cost_bps_per_side="5", total_return=str(result.total_return))])
            (root / "outputs/backtest/summary.json").write_text(json.dumps(summary))
            args = (root, Snapshot(data,"synthetic","synthetic","SPY"), "development", Decimal(1000), Decimal(5), 1)
            _, _, _, delta = reconstruct_paired_series(*args)
            np.testing.assert_array_equal(delta, np.zeros(len(data)))
            recorded["total_return"] = "0.99"
            write(root / "outputs/controls/draws.csv", [recorded])
            with self.assertRaisesRegex(ValueError, "recorded result"):
                reconstruct_paired_series(*args)


if __name__ == "__main__":
    unittest.main()
