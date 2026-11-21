"""Check that the three real entrypoints stop before preparation during a hold."""
from contextlib import redirect_stderr, redirect_stdout
import ctypes
import hashlib
import io
import json
import os
from pathlib import Path
import runpy
import sys
from unittest.mock import patch

sys.dont_write_bytecode = True
STAGE = Path(__file__).absolute().parent
PROJECT = STAGE.parents[2]
REPORT = STAGE / 'hold_entrypoints.json'
MESSAGE = 'Original Windows freeze hold is active; heavy engine work is forbidden'


def ref(path):
    data = path.read_bytes()
    return dict(path=str(path), bytes=len(data), sha256=hashlib.sha256(data).hexdigest())


def main():
    assert not sys.flags.optimize and not REPORT.exists()
    targets = [STAGE / name for name in ('make_scope.py', 'prepare_runtime.py', 'publish_progress.py')]
    protected = [*targets, STAGE / 'system_freeze_hold.json',
                 STAGE / 'frontend_tests_retry_03.json',
                 PROJECT / 'evidence/save_menu/20261013_original_screen/current_progress.json',
                 PROJECT / 'Play/EarlyAccess/release.json', PROJECT / 'tools/Start-Engine.ps1']
    before = [ref(p) for p in protected]
    parents = [PROJECT / 'Build/InteractiveGameRuntime', PROJECT / 'evidence/interactive_game']
    before_ids = [sorted(p.name for p in parent.iterdir()) for parent in parents]
    denied = []

    def audit(event, args):
        if event == 'open' and args and isinstance(args[0], (str, bytes, os.PathLike)):
            path = Path(os.fsdecode(args[0])).absolute()
            mode, flags = args[1:3]
            writing = isinstance(mode, str) and any(c in mode for c in 'wax+') or type(flags) is int and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
            if writing and path != REPORT:
                denied.append(event);raise RuntimeError('Held entrypoint attempted a write')
            normalized = os.path.normcase(str(path))
            if '\\my games\\' in normalized:
                denied.append(event);raise RuntimeError('Retail user state access forbidden')
        if event in ('os.mkdir', 'os.remove', 'os.rmdir', 'os.rename', 'os.link', 'os.symlink', 'os.chmod', 'os.utime') or event.startswith(('subprocess.', 'os.exec', 'os.spawn', 'ctypes.dlopen', 'socket.')) or event in ('os.system', 'os.startfile', 'os.startfile/2', 'os.kill'):
            denied.append(event);raise RuntimeError('Forbidden entrypoint side effect: ' + event)

    sys.addaudithook(audit)
    results = []
    for target in targets:
        stdout, stderr, actual = io.StringIO(), io.StringIO(), None
        compile(target.read_bytes(), str(target), 'exec')
        with redirect_stdout(stdout), redirect_stderr(stderr), patch.object(sys, 'argv', [str(target)]):
            try:
                runpy.run_path(str(target), run_name='__main__')
            except RuntimeError as exc:
                actual = str(exc)
        results.append(dict(source=ref(target), actual_exception=actual,
                            held_before_preparation=actual == MESSAGE,
                            stdout_bytes=len(stdout.getvalue().encode('utf-8')), stderr_bytes=len(stderr.getvalue().encode('utf-8'))))
    unchanged = before == [ref(p) for p in protected]
    same_ids = before_ids == [sorted(p.name for p in parent.iterdir()) for parent in parents]
    no_outputs = all(not (STAGE / name).exists() for name in
                     ('scope.json', 'preparation_started.json', 'prepared.json', 'preparation_identity_audit.json', 'conformance.json', 'progress_update.json'))
    passed = unchanged and same_ids and no_outputs and not denied and all(r['held_before_preparation'] for r in results)
    value = dict(schema='zerosis.original_freeze.held_entrypoints.v1', status='PASS_THREE_ACTUAL_ENTRYPOINTS_STOPPED' if passed else 'FAILED',
                 inputs=before, results=results, inputs_unchanged=unchanged, runtime_and_evidence_ids_unchanged=same_ids,
                 preparation_or_publication_outputs_created=not no_outputs, forbidden_access_attempts=denied,
                 game_or_host_or_gamecore_executed=False, retail_user_state_accessed=False,
                 default_promoted=False, full_engine_goal_complete=False)
    with REPORT.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2);stream.write('\n')
    print(json.dumps(dict(status=value['status'], entrypoints=len(results), report=ref(REPORT))))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
