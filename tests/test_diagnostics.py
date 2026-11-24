"""Hand-computable temporal attribution without resetting the portfolio."""
from datetime import date
from decimal import Decimal
import unittest

from spy_backtest_audit.backtest import BacktestResult, EquityPoint, ExecutedTrade
from spy_backtest_audit.diagnostics import period_metrics, quantiles

D = Decimal
def example():
    days = (date(2020, 12, 30), date(2020, 12, 31), date(2021, 1, 4), date(2021, 1, 5))
    levels = (D(100), D(90), D(81), D(99))
    points = tuple(EquityPoint(day, value if i in (0, 3) else D(0), D(0) if i in (0, 3) else D(1),
                               value, D(0)) for i, (day, value) in enumerate(zip(days, levels)))
    trade = ExecutedTrade(days[0], days[1], days[3], D(100), D(110), D(1), D(0), D(0), D(0), D("0.1"), "scheduled_open")
    return BacktestResult(points, (trade,), D("-0.01"), D("-0.19"), D(0), 0)
class DiagnosticTests(unittest.TestCase):
    def test_year_returns_compound_and_pnl_adds_without_capital_reset(self):
        rows = period_metrics(example(), D(100), [])
        years = [r for r in rows if r["period_kind"] == "year"]
        self.assertEqual(years[0]["starting_equity"], "100")
        self.assertEqual(years[1]["starting_equity"], "90")
        self.assertEqual(D(years[0]["total_return"]), D("-0.1"))
        self.assertEqual(D(years[1]["total_return"]), D("0.1"))
        compounded = (1 + D(years[0]["total_return"])) * (1 + D(years[1]["total_return"])) - 1
        self.assertEqual(compounded, D(rows[0]["total_return"]))
        self.assertEqual(sum(D(r["pnl_usd"]) for r in years), D(rows[0]["pnl_usd"]))
    def test_local_drawdown_resets_at_period_start_not_full_history_peak(self):
        rows = period_metrics(example(), D(100), [])
        annual = next(r for r in rows if r["period"] == "2021")
        self.assertEqual(D(annual["local_max_close_drawdown"]), D("-0.1"))
        self.assertEqual(D(rows[0]["local_max_close_drawdown"]), D("-0.19"))
    def test_entries_attributed_once_but_exposure_carries_across_years(self):
        years = [r for r in period_metrics(example(), D(100), []) if r["period_kind"] == "year"]
        self.assertEqual([r["entries"] for r in years], [1, 0])
        self.assertEqual([D(r["close_exposure_fraction"]) for r in years], [D("0.5"), D("0.5")])
        self.assertNotEqual(D(years[1]["total_return"]), 0)
    def test_blocks_equal_same_observation_window_and_empty_blocks_omitted(self):
        blocks = [{"label": "both", "start": "2020-01-01", "end_exclusive": "2022-01-01"},
                  {"label": "absent", "start": "2022-01-01", "end_exclusive": "2023-01-01"}]
        rows = period_metrics(example(), D(100), blocks)
        both = next(r for r in rows if r["period"] == "both")
        for key in ("total_return", "pnl_usd", "local_max_close_drawdown", "daily_portfolio_volatility"):
            self.assertEqual(both[key], rows[0][key])
        self.assertFalse(any(r["period"] == "absent" for r in rows))
    def test_one_observation_has_undefined_sample_volatility(self):
        result = example()
        from dataclasses import replace
        rows = period_metrics(replace(result, equity=result.equity[:1]), D(100), [])
        self.assertIsNone(rows[0]["daily_portfolio_volatility"])
    def test_nearest_rank_quantiles_are_not_interpolated(self):
        self.assertEqual(quantiles(range(20)), {"p05": "0", "p50": "9", "p95": "18"})
        with self.assertRaises(ValueError):
            quantiles([])


if __name__ == "__main__":
    unittest.main()
