"""Package source, archived data and verified results for review."""
from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = ('.gitignore','.gitattributes','README.md','pyproject.toml','requirements.lock','run.py')
RAW_FILES = ('spy.csv','spy.manifest.json','spy.yahoo.json','spy.yahoo.acquisition.json')
def collect_payload(root):
    paths = [root/name for name in ROOT_FILES]
    paths.extend(root/'data/raw'/name for name in RAW_FILES)
    for directory in ('spy_backtest_audit','scripts','tests'):
        paths.extend((root/directory).rglob('*.py'))
    paths.extend(p for p in (root/'research').rglob('*') if p.suffix in ('.md','.json','.csv','.lock'))
    paths.extend(p for p in (root/'outputs').rglob('*') if p.suffix in ('.csv','.json','.pdf','.png','.svg'))
    paths.extend((root/'reports').rglob('*.pdf'))
    result = {}
    for path in sorted(set(paths)):
        relative = path.relative_to(root)
        if '__pycache__' in relative.parts:
            continue
        if not path.is_file():
            raise ValueError(f'Required package file missing: {relative}')
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError(f'Package file must be inside the project: {relative}')
        result[relative.as_posix()] = path
    return result
def validate_payload(root):
    sys.path.insert(0,str(root))
    from run import check_inputs, show_summary
    output=io.StringIO()
    with redirect_stdout(output):
        valid = check_inputs(root) and show_summary(root)==0
    if not valid:
        raise ValueError(output.getvalue().strip())
    manifest=json.loads((root/'data/raw/spy.manifest.json').read_text(encoding='utf-8'))
    public=root/'reports/spy-backtest-audit.pdf'
    detailed=root/'outputs/report/spy-backtest-audit-research.pdf'
    if not public.is_file() or public.read_bytes()!=detailed.read_bytes():
        raise ValueError('Public report is missing or stale; regenerate the study before packaging')
    original=root/'data/raw/spy.yahoo.json'
    if hashlib.sha256(original.read_bytes()).hexdigest()!=manifest['original_sha256']:
        raise ValueError('Original Yahoo response differs from the archived manifest')
def build_release(root,destination):
    validate_payload(root)
    paths=collect_payload(root)
    manifest=dict(version=1,kind='complete_review_bundle',
                  files={name:hashlib.sha256(path.read_bytes()).hexdigest() for name,path in paths.items()})
    destination.parent.mkdir(parents=True,exist_ok=True)
    temporary=None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent,suffix='.zip',delete=False) as stream:
            temporary=Path(stream.name)
        with zipfile.ZipFile(temporary,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
            def write(name,data):
                info=zipfile.ZipInfo('spy-backtest-audit/'+name,date_time=(1980,1,1,0,0,0))
                info.compress_type=zipfile.ZIP_DEFLATED
                info.external_attr=0o100644<<16
                archive.writestr(info,data,compresslevel=9)
            for name,path in paths.items():
                data=path.read_bytes()
                if hashlib.sha256(data).hexdigest()!=manifest['files'][name]:
                    raise ValueError(f'File changed during packaging: {name}')
                write(name,data)
            write('package_manifest.json',(json.dumps(manifest,indent=2,sort_keys=True)+'\n').encode())
        temporary.replace(destination)
        temporary=None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return destination


if __name__=='__main__':
    try:
        path=build_release(ROOT,ROOT/'dist/spy-backtest-audit-review.zip')
        print(f'Complete review package: {path} ({path.stat().st_size/1024/1024:.1f} MiB)')
    except (OSError,ValueError,KeyError) as exc:
        raise SystemExit(f'Packaging failed: {exc}')
