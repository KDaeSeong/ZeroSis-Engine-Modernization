"""Run the reviewed Python components with no native or retail-state access."""
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import runpy
import sys
import tempfile
import traceback

sys.dont_write_bytecode = True
STAGE = Path(__file__).absolute().parent
PROJECT = STAGE.parents[2]
assert len(sys.argv) == 1 or sys.argv[1:] in (['--owned-baseline-retry'], ['--short-scratch-retry'], ['--hardlink-retry'])
REPORT = STAGE / ('frontend_tests_retry_03.json' if sys.argv[1:] == ['--hardlink-retry'] else
                  'frontend_tests_retry_02.json' if sys.argv[1:] == ['--short-scratch-retry'] else
                  'frontend_tests_retry_01.json' if len(sys.argv) == 2 else 'frontend_tests.json')
# Keep the authored run/session shape below Windows MAX_PATH in this test host.
SCRATCH = Path(r'C:\Users\home\AppData\Local\Temp') / 'zeros-ft-20261018-024443'


def ref(path):
    data = path.read_bytes()
    return dict(path=str(path), bytes=len(data), sha256=hashlib.sha256(data).hexdigest())


def main():
    assert not sys.flags.optimize and not REPORT.exists() and not SCRATCH.exists()
    assert SCRATCH.parent.resolve(strict=True) == Path(r'C:\Users\home\AppData\Local\Temp')
    prepared = PROJECT / 'evidence/ui_popup/assets/prepared.json'
    inputs = [PROJECT / 'tools' / name for name in
              ('render_ui_popup.py', 'ui_pixel_scene.py', 'ui_bitmap_fonts.py', 'civ5_ui_assets.py')]
    tests = [STAGE / 'test_font_binding.py', PROJECT / 'Tests/ui_pixel_scene.py']
    inputs.extend([*tests, Path(__file__).absolute()])
    inputs.extend(Path(row['path']) for row in json.loads(prepared.read_text(encoding='utf-8'))['font_input_profile']['original_inputs'])
    inputs.extend((prepared, PROJECT / 'Source/Assets/UI/font_input_profile.json',
                   PROJECT / 'Play/EarlyAccess/release.json', PROJECT / 'tools/Start-Engine.ps1'))
    before = [ref(path) for path in inputs]
    denied = []
    retail = [os.path.normcase(str(Path(root))) for root in
              (r'C:\Users\home\OneDrive\Documents\My Games', r'C:\Users\home\Documents\My Games')]

    def audit(event, args):
        if event in ('open', 'os.scandir', 'os.listdir') and args and isinstance(args[0], (str, bytes, os.PathLike)):
            path = Path(os.fsdecode(args[0])).absolute()
            key = os.path.normcase(str(path)).removeprefix('\\\\?\\')
            if any(key == root or key.startswith(root + os.sep) for root in retail):
                denied.append(event);raise RuntimeError('Retail user state access forbidden')
            if event == 'open':
                mode, flags = args[1:3]
                writing = isinstance(mode, str) and any(c in mode for c in 'wax+') or type(flags) is int and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
                if writing and path != REPORT and not path.is_relative_to(SCRATCH):
                    denied.append(event);raise RuntimeError('Write outside exact component scratch/report')
        if event in ('os.mkdir', 'os.remove', 'os.rmdir', 'os.chmod', 'os.utime', 'os.link', 'os.rename', 'os.symlink'):
            paths = args[:2] if event in ('os.link', 'os.rename', 'os.symlink') else args[:1]
            if any(isinstance(p, (str, bytes, os.PathLike)) and not Path(os.fsdecode(p)).absolute().is_relative_to(SCRATCH) for p in paths):
                denied.append(event);raise RuntimeError('Mutation outside exact component scratch')
        if event.startswith(('subprocess.', 'os.exec', 'os.spawn', 'ctypes.dlopen', 'socket.', 'urllib.', 'http.client.')) or event in ('os.system', 'os.startfile', 'os.startfile/2', 'os.kill', 'os.fork'):
            denied.append(event);raise RuntimeError('Processes/native loading/network forbidden')

    sys.addaudithook(audit)
    for path in [*tests, *inputs[:4], STAGE / 'prepare_runtime.py']:
        compile(path.read_bytes(), str(path), 'exec')
    SCRATCH.mkdir()
    tempfile.tempdir = str(SCRATCH)
    results = []
    try:
        for path in tests:
            stdout, stderr = io.StringIO(), io.StringIO()
            code, error = 0, None
            with redirect_stdout(stdout), redirect_stderr(stderr):
                try:
                    runpy.run_path(str(path), run_name='__main__')
                except SystemExit as exc:
                    code = exc.code or 0
                except Exception:
                    code, error = 1, traceback.format_exc()
            results.append(dict(test=ref(path), returncode=code, stdout=stdout.getvalue(), stderr=stderr.getvalue(), error=error))
    finally:
        remaining = list(SCRATCH.iterdir())
        if not remaining:
            SCRATCH.rmdir()
    unchanged = before == [ref(path) for path in inputs]
    passed = all(row['returncode'] == 0 for row in results) and unchanged and not denied and not SCRATCH.exists()
    report = dict(schema='zerosis.goody_hut.frontend_component_tests.v1',
                  status='PASS_PYTHON_COMPONENTS_NO_NATIVE' if passed else 'FAILED',
                  utc=datetime.now(timezone.utc).isoformat(), inputs=before, inputs_unchanged=unchanged,
                  results=results, forbidden_access_attempts=denied, component_scratch_remaining=SCRATCH.exists(),
                  native_host_gamecore_hwnd_executed=False, retail_user_state_accessed=False,
                  default_promoted=False, full_engine_goal_complete=False)
    with REPORT.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2);stream.write('\n')
    summaries = [json.loads(row['stdout']) if row['stdout'].strip() else {} for row in results]
    print(json.dumps(dict(status=report['status'], result=ref(REPORT),
                         tests=[dict(returncode=row['returncode'], status=summary.get('status'),
                                     tests_run=summary.get('tests_run'), checks=summary.get('checks'))
                                for row, summary in zip(results, summaries)])))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
