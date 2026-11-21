"""Run the real source-sealed preparer once and record generated payload sizes."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import os
import subprocess
import sys
import time

STAGE = Path(__file__).absolute().parent
PROJECT = STAGE.parents[2]


def ref(path):
    path = Path(path)
    assert path.is_absolute() and path.resolve(strict=True) == path
    before = path.stat()
    with path.open('rb') as stream:
        sha = hashlib.file_digest(stream, 'sha256').hexdigest()
    after = path.stat()
    assert (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    return dict(path=str(path), bytes=after.st_size, sha256=sha)


def write(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2);stream.write('\n');stream.flush();os.fsync(stream.fileno())


def main():
    assert sys.dont_write_bytecode and not sys.flags.optimize
    started, output = STAGE / 'generation_started.json', STAGE / 'generation_run.json'
    assert not started.exists() and not output.exists(), 'Inspect the current attempt; do not repeat it'
    scope = json.loads((STAGE / 'scope.json').read_bytes())
    assert scope['retail_mod_test_hold_active'] and not scope['host_gamecore_hwnd_execution_allowed']
    preservation = json.loads(Path(scope['frozen_preservation']['path']).read_bytes())
    current = [PROJECT / relative for relative in ('tools/prepare_ui_popup_assets.py', 'tools/ui_font_profile.py',
               'Source/Assets/UI/font_input_profile.json', 'Source/Host/UiScene.lua', 'Source/Presentation/UiPresentationInput.lua',
               'Source/Presentation/UiCityView.lua', 'Source/Presentation/UiUnitPanel.lua', 'Source/Presentation/UiSocialPolicy.lua',
               'Source/Presentation/UiEconomicOverview.lua', 'Source/Presentation/UiActionInfoPanel.lua', 'Source/Presentation/UiNotificationPanel.lua')]
    baseline = []
    for row in preservation['artifacts']:
        actual = ref(row['path']);assert actual == row;baseline.append(actual)
    baseline.extend(ref(path) for path in (*current, Path(__file__).absolute(), STAGE / 'scope.json', Path(scope['source_backup']['path'])))
    capture_ref = scope['owned_font_capture']
    assert ref(capture_ref['path']) == capture_ref
    capture = json.loads(Path(capture_ref['path']).read_bytes())
    assert capture['status'] == 'PASS' and capture['source_and_cache_byte_identical']
    assert all(ref(row['path']) == row for row in capture['owned_inputs'])
    baseline.extend([capture_ref, *capture['owned_inputs']])
    targets = [PROJECT / 'Source/Host/UiPopupAssets.generated.h', PROJECT / 'evidence/ui_popup/assets/prepared.json']
    identities = {(Path(row['path']).stat().st_dev, Path(row['path']).stat().st_ino) for row in baseline}
    assert all(path.stat().st_nlink == 1 and (path.stat().st_dev, path.stat().st_ino) not in identities for path in targets)
    before = [ref(path) for path in targets]
    command = [sys.executable, '-B', '-X', 'utf8', str(PROJECT / 'tools/prepare_ui_popup_assets.py')]
    write(started, dict(utc=datetime.now(timezone.utc).isoformat(), source_inputs=[ref(path) for path in current], command=command, targets_before=before))
    tick = time.monotonic()
    result, error = None, None
    try:
        result = subprocess.run(command, cwd=PROJECT, capture_output=True, timeout=300, creationflags=subprocess.CREATE_NO_WINDOW)
    except BaseException as failure:
        error = repr(failure)
    after = [ref(path) for path in targets]
    unchanged = [ref(row['path']) for row in baseline] == baseline
    success = result is not None and result.returncode == 0 and error is None and unchanged and all(row['bytes'] <= 128 * 1024 * 1024 for row in after)
    receipt = dict(schema='zerosis.goody_hut.shared_font_generation.v1', status='PASS' if success else 'FAIL',
        utc=datetime.now(timezone.utc).isoformat(), elapsed_seconds=time.monotonic()-tick, command=command,
        returncode=None if result is None else result.returncode, error=error,
        stdout='' if result is None else result.stdout.decode('utf-8', errors='replace')[-4000:],
        stderr='' if result is None else result.stderr.decode('utf-8', errors='replace')[-6000:],
        targets_before=before, targets_after=after, protected_count=len(baseline), protected_inputs_unchanged=unchanged,
        source_inputs=[ref(path) for path in current], actual_preparer_subprocess_result_unmodified=True, font_original_payload_copies=0, owned_font_capture=capture_ref, owned_font_input_count=len(capture['owned_inputs']),
        host_gamecore_hwnd_executed=False, retail_user_state_or_game_processes_accessed=False, default_promoted=False, full_engine_goal_complete=False)
    write(output, receipt)
    print(json.dumps(dict(status=receipt['status'], elapsed_seconds=receipt['elapsed_seconds'], targets=after, error=error, receipt=ref(output))))
    return 0 if success else 1


if __name__ == '__main__':
    raise SystemExit(main())
