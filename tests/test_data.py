"""Synthetic implementation checks; no real prices or trading conclusions."""
import csv
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from spy_backtest_audit.data import COLUMNS, DataValidationError, load_snapshot
class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.csv = Path(self.temp.name) / "prices.csv"
        self.manifest = Path(self.temp.name) / "manifest.json"
        self.rows = [
            ["2020-01-02", "100", "102", "99", "101", "100.5", "1000", "0", "1"],
            ["2020-01-03", "101", "103", "100", "102", "101.5", "1200", "0.5", "1"],
        ]
    def write(self, rows=None, **changes):
        buffer = io.StringIO(newline="")
        writer = csv.writer(buffer)
        writer.writerow(COLUMNS)
        writer.writerows(self.rows if rows is None else rows)
        self.csv.write_bytes(buffer.getvalue().encode())
        metadata = dict(schema_version=1, symbol="SPY", currency="USD",
                        source="SYNTHETIC TEST DATA - not market observations",
                        retrieved_at="2026-10-20T12:00:00+00:00", price_basis="unadjusted",
                        adjustment_notes="Synthetic positive adjusted prices",
                        usage_notes="Synthetic fixtures generated only for implementation checks",
                        sha256=hashlib.sha256(self.csv.read_bytes()).hexdigest())
        metadata.update(changes)
        self.manifest.write_text(json.dumps(metadata), encoding="utf-8")
    def test_valid_snapshot_preserves_prices_and_actions(self):
        self.write()
        result = load_snapshot(self.csv, self.manifest)
        self.assertEqual(len(result.bars), 2)
        self.assertEqual(str(result.bars[0].open), "100")
        self.assertEqual(str(result.bars[0].adjusted_close), "100.5")
        self.assertEqual(str(result.bars[1].dividend), "0.5")
        self.assertEqual(result.bars[0].volume, 1000)
    def test_changed_bytes_fail_hash(self):
        self.write()
        self.csv.write_bytes(self.csv.read_bytes() + b"\n")
        with self.assertRaisesRegex(DataValidationError, "SHA-256 mismatch"):
            load_snapshot(self.csv, self.manifest)
    def test_duplicate_or_unsorted_dates_rejected(self):
        for rows in ([self.rows[0], self.rows[0]], list(reversed(self.rows))):
            with self.subTest(rows=rows):
                self.write(rows)
                with self.assertRaisesRegex(DataValidationError, "strictly increasing"):
                    load_snapshot(self.csv, self.manifest)
    def test_invalid_numeric_and_price_values_rejected(self):
        for column, value in [("open", "NaN"), ("close", "Infinity"),
                              ("open", "0"), ("low", "102"), ("high", "99"),
                              ("adjusted_close", "-1"), ("volume", "1.5"),
                              ("volume", "-1"), ("dividend", "-1"),
                              ("split_factor", "0"), ("close", ""), ("open", "invalid")]:
            with self.subTest(column=column, value=value):
                rows = [row.copy() for row in self.rows]
                rows[0][COLUMNS.index(column)] = value
                self.write(rows)
                with self.assertRaises(DataValidationError):
                    load_snapshot(self.csv, self.manifest)
    def test_header_and_empty_csv_rejected(self):
        self.write([])
        with self.assertRaisesRegex(DataValidationError, "at least one"):
            load_snapshot(self.csv, self.manifest)
        self.csv.write_text("date,close\n2020-01-02,100\n")
        metadata = json.loads(self.manifest.read_text())
        metadata["sha256"] = hashlib.sha256(self.csv.read_bytes()).hexdigest()
        self.manifest.write_text(json.dumps(metadata))
        with self.assertRaisesRegex(DataValidationError, "header"):
            load_snapshot(self.csv, self.manifest)
    def test_manifest_conventions_rejected(self):
        for changes in ({"source": ""}, {"retrieved_at": "2026-10-20"},
                        {"symbol": "QQQ"}, {"currency": "EUR"},
                        {"price_basis": "adjusted"}, {"schema_version": True}):
            with self.subTest(changes=changes):
                self.write(**changes)
                with self.assertRaises(DataValidationError):
                    load_snapshot(self.csv, self.manifest)
    def test_cli_success_and_failure(self):
        self.write()
        command = [sys.executable, "-m", "spy_backtest_audit", "--data", str(self.csv),
                   "--manifest", str(self.manifest)]
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(command, cwd=root, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("VALID SNAPSHOT", result.stdout)
        self.csv.write_bytes(b"corrupted")
        result = subprocess.run(command, cwd=root, capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn("SHA-256 mismatch", result.stderr)
    def test_cli_requires_both_paths(self):
        result = subprocess.run([sys.executable, "-m", "spy_backtest_audit", "--data", str(self.csv)],
                                cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("together", result.stderr)


if __name__ == "__main__":
    unittest.main()
