"""First-use failures must be actionable and never trigger implicit downloads."""
from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import run
class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
    def call(self,args):
        output=io.StringIO()
        with redirect_stdout(output):
            result=run.main(args,root=self.root)
        return result,output.getvalue()
    def test_no_environment_is_nonzero_without_install_or_download(self):
        with patch('run.subprocess.run') as execute:
            code,text=self.call([])
        self.assertEqual(code,1)
        self.assertIn('--setup',text)
        execute.assert_not_called()
    def test_summary_does_not_require_environment(self):
        with patch('run.subprocess.run') as execute:
            code,text=self.call(['--summary'])
        self.assertEqual(code,1)
        self.assertIn('No generated report',text)
        execute.assert_not_called()
    def test_tests_do_not_require_market_snapshot(self):
        with patch('run.environment_python',return_value=Path('/fake/python')), patch('run.environment_ready',return_value=True), patch('run.check_inputs') as inputs, patch('run.subprocess.run') as execute:
            execute.return_value.returncode=0
            code,text=self.call(['--tests'])
        self.assertEqual(code,0)
        inputs.assert_not_called()
        self.assertIn('unittest',execute.call_args.args[0])
        self.assertEqual(execute.call_args.kwargs['cwd'],self.root)
    def test_missing_data_does_not_start_engine(self):
        with patch('run.environment_python',return_value=Path('/fake/python')), patch('run.environment_ready',return_value=True), patch('run.subprocess.run') as execute:
            code,text=self.call([])
        self.assertEqual(code,1)
        self.assertIn('snapshot missing',text)
        self.assertIn('--tests',text)
        execute.assert_not_called()
    def test_preflight_does_not_start_backtest(self):
        with patch('run.environment_python',return_value=Path('/fake/python')), patch('run.environment_ready',return_value=True), patch('run.check_inputs',return_value=True), patch('run.subprocess.run') as execute:
            code,text=self.call(['--check'])
        self.assertEqual(code,0)
        execute.assert_not_called()
    def test_failed_engine_return_code_is_preserved(self):
        with patch('run.environment_python',return_value=Path('/fake/python')), patch('run.environment_ready',return_value=True), patch('run.check_inputs',return_value=True), patch('run.subprocess.run') as execute:
            execute.return_value.returncode=7
            code,text=self.call([])
        self.assertEqual(code,7)
    def test_verified_summary_rejects_tampered_pdf_and_inputs(self):
        folder=self.root/'outputs/report'; folder.mkdir(parents=True)
        generator=self.root/'spy_backtest_audit/report.py'; generator.parent.mkdir(); generator.write_text('# synthetic generator')
        source=self.root/'outputs/result.json'; source.write_text('{}')
        pdf=folder/'spy-backtest-audit-research.pdf'; pdf.write_bytes(b'synthetic report')
        sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
        facts=dict(headline=dict(classification='SYNTHETIC',validation_return='-1.00%',control_median='1.00%',contrast_pp='-2.00 pp'),
                   family={'positive_counts':{'validation':{'contrast':6}}},
                   report_provenance=dict(inputs={'outputs/result.json':sha(source)},pdf_sha256=sha(pdf),report_code_sha256=sha(generator)))
        (folder/'report_facts.json').write_text(json.dumps(facts))
        code,text=self.call(['--summary'])
        self.assertEqual(code,0); self.assertIn('SYNTHETIC',text)
        for p in (pdf,source,generator):
            original=p.read_bytes(); p.write_bytes(b'changed')
            code,text=self.call(['--summary'])
            self.assertEqual(code,1); self.assertIn('Cannot present a verified report',text)
            p.write_bytes(original)
    def test_environment_detection_supports_posix_and_windows(self):
        for relative in ('.venv/bin/python','.venv/Scripts/python.exe'):
            path=self.root/relative; path.parent.mkdir(parents=True,exist_ok=True); path.touch()
            self.assertEqual(run.environment_python(self.root),path)
            path.unlink()
