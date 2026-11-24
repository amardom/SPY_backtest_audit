"""Distribution contains a complete payload, not a PDF with dangling references."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from scripts.package_release import ROOT_FILES, RAW_FILES, build_release, collect_payload, validate_payload
class PackageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        for name in ROOT_FILES:
            (self.root/name).write_text('synthetic source')
        for name in RAW_FILES:
            path=self.root/'data/raw'/name
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text('synthetic data')
        for name in ('spy_backtest_audit/module.py','scripts/tool.py','tests/test_case.py',
                     'research/record.json','outputs/backtest/equity.csv','outputs/report/report_facts.json',
                     '.env','.venv/lib/cache.py','.git/config','spy_backtest_audit/__pycache__/ignored.py'):
            path=self.root/name; path.parent.mkdir(parents=True,exist_ok=True); path.write_text('synthetic fixture')
    def test_payload_keeps_inputs_and_intermediates_but_omits_environment_and_caches(self):
        payload=collect_payload(self.root)
        self.assertIn('outputs/backtest/equity.csv',payload)
        self.assertIn('data/raw/spy.yahoo.json',payload)
        self.assertIn('research/record.json',payload)
        for name in ('.env','.venv/lib/cache.py','.git/config','spy_backtest_audit/__pycache__/ignored.py'):
            self.assertNotIn(name,payload)
    def test_public_report_is_included_in_payload(self):
        report=self.root/'reports/spy-backtest-audit.pdf'
        report.parent.mkdir(); report.write_bytes(b'synthetic report')
        self.assertIn('reports/spy-backtest-audit.pdf',collect_payload(self.root))
    def test_stale_public_report_is_rejected(self):
        public=self.root/'reports/spy-backtest-audit.pdf'
        public.parent.mkdir(); public.write_bytes(b'old report')
        detailed=self.root/'outputs/report/spy-backtest-audit-research.pdf'
        detailed.write_bytes(b'new report')
        (self.root/'data/raw/spy.manifest.json').write_text('{}')
        with patch('run.check_inputs',return_value=True),patch('run.show_summary',return_value=0):
            with self.assertRaisesRegex(ValueError,'Public report is missing or stale'):
                validate_payload(self.root)
    def test_missing_required_snapshot_fails(self):
        (self.root/'data/raw/spy.csv').unlink()
        with self.assertRaisesRegex(ValueError,'Required package file missing'):
            collect_payload(self.root)
    def test_incomplete_report_rejected_before_build(self):
        with patch('run.check_inputs',return_value=True),patch('run.show_summary',return_value=1):
            with self.assertRaises(ValueError):
                validate_payload(self.root)
    def test_archive_is_deterministic_and_manifest_covers_every_payload_file(self):
        path=self.root/'dist/review.zip'
        with patch('scripts.package_release.validate_payload'):
            build_release(self.root,path)
            original=path.read_bytes()
            build_release(self.root,path)
        self.assertEqual(path.read_bytes(),original)
        with zipfile.ZipFile(path) as archive:
            names=archive.namelist()
            manifest=json.loads(archive.read('spy-backtest-audit/package_manifest.json'))
            self.assertEqual(set(names),{'spy-backtest-audit/'+n for n in manifest['files']}|{'spy-backtest-audit/package_manifest.json'})
            for name,expected in manifest['files'].items():
                self.assertEqual(hashlib.sha256(archive.read('spy-backtest-audit/'+name)).hexdigest(),expected)
