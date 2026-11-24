"""Offline calendar integrity and frozen-method checks; no vendor data required."""
import csv
from datetime import date
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from spy_backtest_audit.calendar import audit_calendar, compare_session_dates
from spy_backtest_audit.data import DailyBar, DataValidationError, Snapshot
from spy_backtest_audit.protocol import verify_validation_freeze

ROOT = Path(__file__).resolve().parents[1]
class CalendarTests(unittest.TestCase):
    def test_missing_and_unexpected_sessions_are_separate(self):
        expected = [date(2020, 1, 2), date(2020, 1, 3)]
        observed = [date(2020, 1, 2), date(2020, 1, 4)]
        result = compare_session_dates(observed, expected)
        self.assertFalse(result["passed"])
        self.assertEqual(result["missing"], ["2020-01-03"])
        self.assertEqual(result["unexpected"], ["2020-01-04"])
    def test_duplicate_or_unsorted_observations_fail(self):
        a, b = date(2020, 1, 2), date(2020, 1, 3)
        for observed in ([a, a], [b, a]):
            with self.subTest(observed=observed), self.assertRaises(DataValidationError):
                compare_session_dates(observed, [a, b])
    def test_reference_preserves_special_closures_and_early_close_sessions(self):
        with (ROOT / "research/calendar/xnys_2000_2021.csv").open() as stream:
            sessions = {r["date"] for r in csv.DictReader(stream)}
        for absent in ("2001-09-11", "2001-09-12", "2001-09-13", "2001-09-14",
                       "2004-06-11", "2007-01-02", "2012-10-29", "2012-10-30", "2018-12-05"):
            self.assertNotIn(absent, sessions)
        for present in ("2001-09-17", "2012-10-31", "2012-11-23", "2021-12-31"):
            self.assertIn(present, sessions)
    def test_complete_audit_and_missing_session_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(ROOT / "research/calendar", root / "research/calendar")
            shutil.copyfile(ROOT / "research/data_plan.json", root / "research/data_plan.json")
            with (root / "research/calendar/xnys_2000_2021.csv").open() as stream:
                dates = [date.fromisoformat(r["date"]) for r in csv.DictReader(stream)]
            bars = tuple(DailyBar(d, *([Decimal(1)] * 5), 1000, Decimal(0), Decimal(1)) for d in dates)
            snapshot = Snapshot(bars, "synthetic", "synthetic", "SPY")
            self.assertTrue(audit_calendar(root, snapshot)["passed"])
            with self.assertRaisesRegex(DataValidationError, "1 missing"):
                audit_calendar(root, Snapshot(bars[:-1], "synthetic", "synthetic", "SPY"))
            output = json.loads((root / "outputs/data/session_audit.json").read_text())
            self.assertFalse(output["passed"])
    def test_tampered_calendar_fails_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(ROOT / "research/calendar", root / "research/calendar")
            with (root / "research/calendar/xnys_2000_2021.csv").open("a") as stream:
                stream.write("2022-01-03\n")
            with self.assertRaisesRegex(DataValidationError, "hash mismatch"):
                audit_calendar(root, Snapshot((), "synthetic", "synthetic", "SPY"))
class FreezeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "research").mkdir()
        (self.root / "data/raw").mkdir(parents=True)
        self.config = self.root / "research/strategy.json"
        self.config.write_text('{"lookback":20}')
        freeze = dict(version=1, status="RULES_FROZEN_NOT_EXECUTED", snapshot_sha256="synthetic",
                      file_sha256={"research/strategy.json": hashlib.sha256(self.config.read_bytes()).hexdigest()})
        (self.root / "research/validation_freeze.json").write_text(json.dumps(freeze))
        (self.root / "data/raw/spy.manifest.json").write_text('{"sha256":"synthetic"}')
    def test_unchanged_method_accepted(self):
        self.assertEqual(verify_validation_freeze(self.root)["snapshot_sha256"], "synthetic")
    def test_parameter_change_not_silent(self):
        self.config.write_text('{"lookback":19}')
        with self.assertRaisesRegex(DataValidationError, "Frozen methodology changed"):
            verify_validation_freeze(self.root)
    def test_different_data_not_silent(self):
        (self.root / "data/raw/spy.manifest.json").write_text('{"sha256":"different"}')
        with self.assertRaisesRegex(DataValidationError, "Dataset differs"):
            verify_validation_freeze(self.root)


if __name__ == "__main__":
    unittest.main()
