"""Run the one interrupted EA0.5 restore check with a durable small receipt."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
RESULT = HERE / 'restore_retry_runner_result.json'
START = HERE / 'restore_retry_runner_started.json'
if RESULT.exists() or START.exists():
    raise SystemExit('This one-shot restore retry has already been started.')
arguments = [
    sys.executable, '-B', '-X', 'utf8', 'tools/run_interactive_game.py',
    '--host-build', 'evidence/ui_window_host/20261010T061111Z_b26391596d41/build_result.json',
    '--smoke', '--decisions', '--research-tree', '--unit-actions', '--worker-build',
    '--top-panel', '--action-info-panel', '--notification-panel',
    '--unit-assets-manifest',
    'Build/UnitAssets/480678966a78bedbee642040285010aa86f8a2cc34b0929c2774dcee8ab54266/unit-assets.manifest.json',
    '--resume-run', '20261010T061414Z_954a8fa83ad8',
    '--ui-support-from-run', '20261010T061414Z_954a8fa83ad8',
    '--timeout', '900',
]
started = datetime.now(timezone.utc).isoformat()
process = subprocess.Popen(arguments, cwd=ROOT, stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, text=True, encoding='utf-8')
START.write_text(json.dumps({'schema': 1, 'started_utc': started,
    'wrapper_pid': os.getpid(), 'runner_pid': process.pid,
    'replaces_interrupted_attempt': '20261010T063059Z_50c613aa97cd',
    'arguments': arguments}, indent=2) + '\n', encoding='utf-8')
stdout, stderr = process.communicate()
runs = []
for line in stdout.splitlines():
    try:
        item = json.loads(line)
    except ValueError:
        continue
    if isinstance(item, dict) and ('run_id' in item or 'status' in item):
        runs.append({key: item[key] for key in
            ('run_id', 'status', 'result', 'returncode', 'timed_out', 'failures')
            if key in item})
record = {'schema': 1, 'started_utc': started,
    'completed_utc': datetime.now(timezone.utc).isoformat(),
    'runner_exit': process.returncode, 'runs': runs,
    'stderr_tail': stderr[-2000:]}
if process.returncode and not runs:
    record['stdout_tail'] = stdout[-2000:]
RESULT.write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
raise SystemExit(process.returncode)
