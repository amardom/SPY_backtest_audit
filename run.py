"""Run the study, tests and environment checks from the project directory."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
def environment_python(root):
    for relative in ('.venv/bin/python', '.venv/Scripts/python.exe'):
        candidate = root / relative
        if candidate.is_file():
            return candidate
    return None
def environment_ready(python, root):
    required = [line.strip().split('==') for line in (root/'requirements.lock').read_text().splitlines()
                if line.strip() and not line.startswith('#')]
    code = ("import sys; from importlib.metadata import version, PackageNotFoundError; "
            + "required=" + repr(required) + "; "
            + "bad=[]\n"
            + "for name,want in required:\n"
            + " try: got=version(name)\n"
            + " except PackageNotFoundError: got='missing'\n"
            + " if got!=want: bad.append(f'{name}: {got} (expected {want})')\n"
            + "if sys.version_info[:2]!=(3,12): bad.append('Python 3.12 required for the recorded environment')\n"
            + "print('\\n'.join(bad))\n"
            + "sys.exit(bool(bad))")
    result = subprocess.run([str(python), '-c', code], cwd=root, text=True, capture_output=True)
    if result.returncode:
        print(result.stdout.strip() or result.stderr.strip())
        print('Prepare the pinned environment: python3 run.py --setup')
        return False
    return True
def check_inputs(root):
    expected = (root/'data/raw/spy.csv',root/'data/raw/spy.manifest.json')
    if not all(p.is_file() for p in expected):
        print('Original frozen snapshot missing: data/raw/spy.csv and data/raw/spy.manifest.json.')
        print('The complete review package includes this snapshot. Extract it fully or restore the four data/raw files.')
        print('You can run synthetic tests without market data: python3 run.py --tests')
        print('A fresh vendor download may differ and cannot replace the frozen snapshot silently.')
        return False
    from spy_backtest_audit.data import load_snapshot
    from spy_backtest_audit.calendar import audit_calendar
    from spy_backtest_audit.protocol import verify_validation_freeze
    try:
        snapshot=load_snapshot(*expected)
        audit_calendar(root,snapshot)
        verify_validation_freeze(root)
    except (OSError,ValueError,KeyError) as exc:
        print(f'Input check failed: {exc}')
        return False
    print(f'Input checks passed: {len(snapshot.bars)} sessions; frozen snapshot and method verified.')
    return True
def show_summary(root):
    path=root/'outputs/report/report_facts.json'
    pdf=root/'outputs/report/spy-backtest-audit-research.pdf'
    if not path.is_file() or not pdf.is_file():
        print('No generated report found. Run: python3 run.py')
        return 1
    try:
        facts=json.loads(path.read_text(encoding='utf-8'))
        provenance=facts['report_provenance']
        hashes=dict(provenance['inputs'])
        hashes['outputs/report/spy-backtest-audit-research.pdf']=provenance['pdf_sha256']
        hashes['spy_backtest_audit/report.py']=provenance['report_code_sha256']
        if any(hashlib.sha256((root/p).read_bytes()).hexdigest()!=h for p,h in hashes.items()):
            raise ValueError('Report inputs or generator changed; regenerate before quoting it')
        headline=facts['headline']
        print('SPY Backtest Audit | recorded retrospective validation, 2016-2021')
        print(headline['classification'])
        print(f"Dip: {headline['validation_return']} | Control median: {headline['control_median']} | Difference: {headline['contrast_pp']}")
        print(f"Parameter-family positive contrasts: {facts['family']['positive_counts']['validation']['contrast']} / 27 (exploratory)")
        print(f'Report: {pdf}')
        print('Pages 1: decision | 8: uncertainty | 9-10: parameter family | 11: reproduction')
        return 0
    except (OSError,ValueError,KeyError) as exc:
        print(f'Cannot present a verified report: {exc}')
        return 1
def main(argv=None,root=ROOT):
    parser=argparse.ArgumentParser(description='SPY Backtest Audit: reproduce the study, test the code, or inspect recorded results.')
    action=parser.add_mutually_exclusive_group()
    action.add_argument('--setup',action='store_true',help='Create .venv and install requirements.lock (network access)')
    action.add_argument('--tests',action='store_true',help='Run the synthetic test suite; no market snapshot required')
    action.add_argument('--check',action='store_true',help='Check environment, snapshot, calendar and frozen method without a backtest')
    action.add_argument('--summary',action='store_true',help='Show verified existing results and report path; no recalculation')
    args=parser.parse_args(argv)
    if args.summary:
        return show_summary(root)
    python=environment_python(root)
    if args.setup:
        if python is None:
            if sys.version_info[:2]!=(3,12):
                print('Use Python 3.12 to create the recorded environment: python3.12 run.py --setup')
                return 1
            subprocess.run([sys.executable,'-m','venv',str(root/'.venv')],check=True)
            python=environment_python(root)
        subprocess.run([str(python),'-m','pip','install','-r',str(root/'requirements.lock')],cwd=root,check=True)
        if not environment_ready(python,root):
            return 1
        print('Environment ready. No market data acquired. Run python3 run.py --tests or python3 run.py.')
        return 0
    if python is None:
        print('Environment missing. Run once with Python 3.12: python3 run.py --setup')
        return 1
    if not environment_ready(python,root):
        return 1
    if args.tests:
        return subprocess.run([str(python),'-m','unittest','discover','-s','tests','-v'],cwd=root).returncode
    if not check_inputs(root):
        return 1
    if args.check:
        return 0
    print('Running the complete recorded study; this takes several minutes. No network requests.',flush=True)
    result=subprocess.run([str(python),'-m','spy_backtest_audit'],cwd=root)
    if result.returncode:
        return result.returncode
    return show_summary(root)


if __name__=='__main__':
    try:
        raise SystemExit(main())
    except (OSError,subprocess.CalledProcessError) as exc:
        print(f'Launcher failed: {exc}',file=sys.stderr)
        raise SystemExit(1)
