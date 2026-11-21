"""One-shot fresh/restore validation of the natural-research candidate.

This does not promote a release or reinterpret an existing failed run.
"""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
HOST = 'evidence/ui_window_host/20261010T072241Z_8a97a1f4381e/build_result.json'
UNIT_ASSETS = 'Build/UnitAssets/480678966a78bedbee642040285010aa86f8a2cc34b0929c2774dcee8ab54266/unit-assets.manifest.json'
START = HERE / 'native_pair_started.json'
RESULT = HERE / 'native_pair_result.json'


def now():
    return datetime.now(timezone.utc).isoformat()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def phase(name, source):
    command = [sys.executable, '-B', '-X', 'utf8', 'tools/run_interactive_game.py',
               '--host-build', HOST, '--smoke', '--decisions', '--research-tree',
               '--unit-actions', '--worker-build', '--top-panel', '--action-info-panel',
               '--notification-panel', '--unit-assets-manifest', UNIT_ASSETS,
               '--ui-support-from-run', source, '--timeout', '900']
    if name == 'restore':
        command += ['--resume-run', source]
    stdout_path = HERE / (name + '_runner.stdout.log')
    stderr_path = HERE / (name + '_runner.stderr.log')
    record_path = HERE / (name + '_runner.json')
    with stdout_path.open('xb') as output, stderr_path.open('xb') as errors:
        process = subprocess.Popen(command, cwd=ROOT, stdout=output, stderr=errors)
        record = {'schema': 1, 'status': 'RUNNING', 'started_utc': now(),
                  'wrapper_pid': os.getpid(), 'runner_pid': process.pid,
                  'command': command, 'source_run': source}
        write(record_path, record)
        returncode = process.wait()
    records = []
    for line in stdout_path.read_text(encoding='utf-8', errors='replace').splitlines():
        try:
            item = json.loads(line)
        except ValueError:
            continue
        if isinstance(item, dict) and 'run_id' in item and 'result' in item:
            records.append(item)
    record.update(completed_utc=now(), returncode=returncode, summaries=records)
    record['status'] = 'FAILED'
    write(record_path, record)
    if returncode or len(records) != 1:
        raise RuntimeError(name + ' validation did not finish successfully; inspect its existing logs')
    summary = records[0]
    run_id = summary['run_id']
    if not re.fullmatch(r'\d{8}T\d{6}Z_[0-9a-f]{12}', run_id):
        raise RuntimeError('Unexpected validation run identity')
    expected = ROOT / 'evidence/interactive_game' / run_id / 'result.json'
    if Path(summary['result']).resolve(strict=True) != expected.resolve(strict=True):
        raise RuntimeError('Validation output is outside its exact evidence directory')
    result = json.loads(expected.read_text(encoding='utf-8-sig'))
    status = 'CONTINUOUS_INTERACTIVE_SDK_WORKER_BUILD_' + ('RESTORE_' if name == 'restore' else '') + 'SMOKE_PASS'
    if result.get('status') != status or result.get('failures') or result.get('worker_research_verified') is not True:
        raise RuntimeError(name + ' lacks the full worker and natural-research success contract')
    record.update(status='PASS', run_id=run_id, result=str(expected))
    write(record_path, record)
    return run_id


def main():
    with START.open('x', encoding='utf-8') as stream:
        json.dump({'schema': 1, 'started_utc': now(), 'wrapper_pid': os.getpid(),
                   'host_build': HOST, 'automatic_retry': False}, stream, indent=2)
    record = {'schema': 1, 'status': 'FAILED', 'manual_play_verified': False,
              'release_promoted': False, 'host_build': HOST}
    try:
        record['fresh_run'] = phase('fresh', '20261010T061414Z_954a8fa83ad8')
        record['restore_run'] = phase('restore', record['fresh_run'])
        record['status'] = 'FRESH_AND_RESTORE_NATIVE_WORKER_RESEARCH_PASS'
    except Exception as error:
        record['error'] = str(error)
    record['completed_utc'] = now()
    write(RESULT, record)
    return 0 if record['status'].endswith('_PASS') else 1


if __name__ == '__main__':
    raise SystemExit(main())
