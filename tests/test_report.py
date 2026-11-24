"""Headline provenance checks use invented results, never private market data."""
import json
from pathlib import Path
import tempfile
import unittest

try:
    from spy_backtest_audit.report import collect_facts
except ImportError:
    collect_facts = None
@unittest.skipIf(collect_facts is None, "Install pinned report dependencies")
class ReportFactsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.validation = dict(snapshot_sha256="synthetic", freeze_sha256="synthetic-freeze",
                               classification="PROMISING_MORE_RESEARCH", controls_count=3,
                               scenarios=[dict(strategy="dip", cost_bps_per_side="5", total_return="0.1234", trades=7)],
                               control_return_quantiles={"p50": "0.2345"}, primary_control_contrast="-0.1111")
        evidence = {key: self.validation[key] for key in ("snapshot_sha256", "freeze_sha256", "classification", "scenarios", "primary_control_contrast", "control_return_quantiles")}
        files = {
            "outputs/backtest/summary.json": {"signal_run": {"snapshot_sha256": "synthetic"}},
            "outputs/controls/summary.json": {"config": {"calendars": 3}},
            "outputs/validation/summary.json": self.validation,
            "outputs/data/session_audit.json": {"passed": True},
            "research/validation_first_observation.json": {"evidence": evidence},
        }
        for name, value in files.items():
            p = self.root / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(value))
    def add_uncertainty_fixture(self):
        import hashlib
        p = self.root / "outputs/uncertainty/summary.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        source = self.root / "outputs/validation/summary.json"
        p.write_text(json.dumps(dict(snapshot_sha256="synthetic", source_sha256={
            "outputs/validation/summary.json":hashlib.sha256(source.read_bytes()).hexdigest()})))
    def test_headlines_follow_computed_inputs_not_case_constants(self):
        self.add_uncertainty_fixture()
        family = self.root / "outputs/parameter_family/summary.json"
        family.parent.mkdir(parents=True)
        family.write_text(json.dumps(dict(snapshot_sha256="synthetic", source_sha256={})))
        headline = collect_facts(self.root)["headline"]
        self.assertEqual(headline["validation_return"], "12.34%")
        self.assertEqual(headline["control_median"], "23.45%")
        self.assertEqual(headline["contrast_pp"], "-11.11 pp")
        self.assertEqual(headline["trades"], 7)
    def test_changed_validation_cannot_silently_rewrite_report(self):
        self.validation["primary_control_contrast"] = "0.99"
        (self.root / "outputs/validation/summary.json").write_text(json.dumps(self.validation))
        with self.assertRaisesRegex(ValueError, "first validation observation"):
            collect_facts(self.root)
    def test_mixed_snapshots_rejected(self):
        (self.root / "outputs/backtest/summary.json").write_text(json.dumps({"signal_run": {"snapshot_sha256": "other"}}))
        with self.assertRaisesRegex(ValueError, "validated snapshot"):
            collect_facts(self.root)
    def test_failed_calendar_rejected(self):
        (self.root / "outputs/data/session_audit.json").write_text('{"passed":false}')
        with self.assertRaisesRegex(ValueError, "validated snapshot"):
            collect_facts(self.root)


if __name__ == "__main__":
    unittest.main()
