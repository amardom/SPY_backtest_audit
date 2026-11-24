"""Acquisition checks use a mocked server, never real vendor requests."""
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from spy_backtest_audit.acquire import acquire_snapshot, normalize_yahoo, query_url
from spy_backtest_audit.data import DataValidationError, load_snapshot
def payload():
    stamp = int(datetime(2020, 1, 2, 14, 30, tzinfo=timezone.utc).timestamp())
    result = {
        "meta": {"symbol": "SPY", "currency": "USD", "exchangeTimezoneName": "America/New_York"},
        "timestamp": [stamp],
        "indicators": {"quote": [{"open": [100], "high": [102], "low": [99],
                                     "close": [101], "volume": [1000]}],
                       "adjclose": [{"adjclose": [100.5]}]},
        "events": {"dividends": {str(stamp): {"date": stamp, "amount": 0.5}}},
    }
    return {"chart": {"error": None, "result": [result]}}
class AcquisitionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "research").mkdir()
        self.plan = json.loads((Path(__file__).resolve().parents[1] / "research/data_plan.json").read_text())
        (self.root / "research/data_plan.json").write_text(json.dumps(self.plan))
    def test_reserved_window_cannot_be_requested(self):
        self.plan["acquisition_end_exclusive"] = "2023-01-01"
        with self.assertRaisesRegex(DataValidationError, "reserved"):
            query_url(self.plan)
    def test_response_outside_requested_window_rejected(self):
        data = payload()
        data["chart"]["result"][0]["timestamp"] = [int(datetime(2022, 1, 3, 14, 30, tzinfo=timezone.utc).timestamp())]
        with self.assertRaisesRegex(DataValidationError, "outside"):
            normalize_yahoo(json.dumps(data).encode(), self.plan)
    def test_missing_vendor_price_not_silently_dropped(self):
        data = payload()
        data["chart"]["result"][0]["indicators"]["quote"][0]["open"] = [None]
        with self.assertRaisesRegex(DataValidationError, "Missing vendor"):
            normalize_yahoo(json.dumps(data).encode(), self.plan)
    def test_cached_acquisition_is_identical_and_offline(self):
        raw = json.dumps(payload()).encode()
        response = MagicMock()
        response.__enter__.return_value.read.return_value = raw
        with patch("spy_backtest_audit.acquire.urlopen", return_value=response) as network:
            csv_path, manifest = acquire_snapshot(self.root)
            self.assertEqual(network.call_count, 1)
        original_csv = csv_path.read_bytes()
        original_manifest = manifest.read_bytes()
        with patch("spy_backtest_audit.acquire.urlopen", side_effect=AssertionError("No network permitted")):
            acquire_snapshot(self.root)
        self.assertEqual(csv_path.read_bytes(), original_csv)
        self.assertEqual(manifest.read_bytes(), original_manifest)
        result = load_snapshot(csv_path, manifest)
        self.assertEqual(str(result.bars[0].dividend), "0.5")
        self.assertEqual(result.bars[0].split_factor, 1)
        self.assertEqual(json.loads(manifest.read_text())["price_basis"], "split_adjusted")
    def test_tampered_original_archive_rejected(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(payload()).encode()
        with patch("spy_backtest_audit.acquire.urlopen", return_value=response):
            acquire_snapshot(self.root)
        (self.root / "data/raw/spy.yahoo.json").write_bytes(b"tampered")
        with patch("spy_backtest_audit.acquire.urlopen", side_effect=AssertionError("No network permitted")):
            with self.assertRaisesRegex(DataValidationError, "hash mismatch"):
                acquire_snapshot(self.root)
    def test_tampered_normalized_snapshot_not_overwritten(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(payload()).encode()
        with patch("spy_backtest_audit.acquire.urlopen", return_value=response):
            csv_path, _ = acquire_snapshot(self.root)
        csv_path.write_bytes(b"tampered")
        with patch("spy_backtest_audit.acquire.urlopen", side_effect=AssertionError("No network permitted")):
            with self.assertRaisesRegex(DataValidationError, "refusing to overwrite"):
                acquire_snapshot(self.root)
        self.assertEqual(csv_path.read_bytes(), b"tampered")


if __name__ == "__main__":
    unittest.main()
