"""Check frozen boundary/screen logic with synthetic observations only."""
from datetime import date
from decimal import Decimal
import unittest

from spy_backtest_audit.signals import Strategy, generate_signals
from spy_backtest_audit.validation import prepare_validation, classify_screen
from tests.test_signals import bars_from_returns

D = Decimal
class ValidationTests(unittest.TestCase):
    def test_first_signal_uses_only_warmup_and_enters_second_validation_session(self):
        bars = bars_from_returns(["0.01", "-0.01", "0.01", "-0.1"] + ["0"] * 10,
                                 start=date(2015, 12, 28))
        context, first_entry, signals = prepare_validation(bars, date(2016, 1, 1), date(2017, 1, 1),
                                                          Strategy(3, D(2), 5))
        self.assertEqual(first_entry, 5)
        self.assertEqual(signals.trades[0].signal_date, date(2016, 1, 1))
        self.assertEqual(signals.trades[0].entry_date, date(2016, 1, 2))
        self.assertEqual(signals.trades[0].exit_date, date(2016, 1, 7))
        self.assertEqual(len(context), len(bars))
    def test_administrative_cutoff_logs_tail_without_phantom_holding(self):
        bars = bars_from_returns(["0.01", "-0.01", "0.01", "-0.1", "-0.2", "-0.3", "-0.4", "-0.5", "-0.6"])
        result = generate_signals(bars, Strategy(3, D("0.5"), 3), last_entry_index=5)
        self.assertEqual(len(result.trades), 1)
        self.assertEqual(result.trades[0].exit_date, bars[8].date)
        decisions = {e.signal_date: e.decision for e in result.events}
        self.assertEqual(decisions[bars[7].date], "ignored_holding")
        self.assertEqual(decisions[bars[8].date], "excluded_tail")
        self.assertEqual(decisions[bars[9].date], "excluded_tail")
    def test_warmup_never_creates_prior_positions(self):
        bars = bars_from_returns(["0.01", "-0.01", "-0.5"] + ["0"] * 10,
                                 start=date(2015, 12, 28))
        _, _, result = prepare_validation(bars, date(2016, 1, 1), date(2017, 1, 1), Strategy(3, D(2), 5))
        self.assertFalse(result.trades)
        self.assertTrue(all(e.signal_date >= date(2016, 1, 1) for e in result.events))
    def test_dates_after_validation_do_not_change_signals(self):
        bars = bars_from_returns(["0.01", "-0.01", "0.01", "-0.1"] + ["0"] * 20,
                                 start=date(2015, 12, 28))
        start, end = date(2016, 1, 1), date(2016, 1, 12)
        strategy = Strategy(3, D(2), 5)
        expected = prepare_validation(tuple(b for b in bars if b.date < end), start, end, strategy)
        self.assertEqual(prepare_validation(bars, start, end, strategy), expected)
        self.assertTrue(all(t.exit_date < end for t in expected[2].trades))
    def test_insufficient_warmup_or_horizon_rejected(self):
        bars = bars_from_returns(["0.01"] * 8, start=date(2016, 1, 1))
        with self.assertRaisesRegex(ValueError, "warmup"):
            prepare_validation(bars, date(2016, 1, 1), date(2017, 1, 1), Strategy(3, D(2), 5))
        with self.assertRaisesRegex(ValueError, "holding horizon"):
            prepare_validation(bars, date(2016, 1, 5), date(2016, 1, 8), Strategy(3, D(2), 5))
    def test_screen_matches_all_frozen_branches_including_zero_boundaries(self):
        cases = [
            (D(0), None, D(0), 0, "INCONCLUSIVE"),
            (D(0), D(1), D(1), 10, "NOT_SUPPORTED_BY_VALIDATION_SCREEN"),
            (D(1), D(0), D(1), 10, "NOT_SUPPORTED_BY_VALIDATION_SCREEN"),
            (D(1), D(-1), D(1), 10, "NOT_SUPPORTED_BY_VALIDATION_SCREEN"),
            (D(1), D(1), D(0), 10, "INCONCLUSIVE_COST_FRAGILE"),
            (D(1), D(1), D(1), 10, "PROMISING_MORE_RESEARCH"),
        ]
        for primary, contrast, stress, count, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(classify_screen(primary, contrast, stress, count), expected)
        with self.assertRaises(ValueError):
            classify_screen(D(1), None, D(1), 10)
    def test_invalid_entry_cutoff_rejected(self):
        bars = bars_from_returns(["0"] * 10)
        for cutoff in (0, len(bars), True):
            with self.subTest(cutoff=cutoff), self.assertRaises(ValueError):
                generate_signals(bars, Strategy(), last_entry_index=cutoff)


if __name__ == "__main__":
    unittest.main()
