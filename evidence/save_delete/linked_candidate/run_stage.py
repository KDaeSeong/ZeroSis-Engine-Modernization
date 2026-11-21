"""Build and prepare the owned-save-delete candidate without executing it."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

PROJECT = Path(__file__).absolute().parents[3]
STAGE = Path(__file__).absolute().parent
B5 = '20261015T134352Z_8bd70cf290e9'
PROGRESS = PROJECT / 'evidence/save_menu/20261013_original_screen/current_progress.json'


def artifact(path):
    data = path.read_bytes()
    return {'path': str(path), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf8')


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def start():
    output = STAGE / 'scope.json'
    require(not output.exists(), 'Refusing to overwrite linked-stage scope')
    progress = read(PROGRESS)
    require(progress['status'] == 'OWNED_SAVE_DELETE_SOURCE_CHECKS_PASS_LINKED_HOST_PREDATES_DELETE',
            'Expected the completed deletion source stage')
    before = STAGE / 'source_before/current_progress.json.txt'
    before.parent.mkdir(exist_ok=False)
    before.write_bytes(PROGRESS.read_bytes())
    donor_path = PROJECT / f'evidence/ui_window_host/{B5}/build_result.json'
    donor = read(donor_path)
    headers = [row for row in donor['compiler_inputs']
               if Path(row['path']).name == 'UiPopupAssets.generated.h']
    require(len(headers) == 1, 'Expected one sealed donor include-header recovery input')
    header = headers[0]
    require(artifact(Path(header['path']))['sha256'] == header['sha256'], 'Donor header changed')
    protected = {relative: artifact(PROJECT / relative) for relative in (
        'Play/EarlyAccess/release.json', 'tools/Start-Engine.ps1', 'Source/Host/NativeSaveArchive.h',
        f'evidence/ui_window_host/{B5}/build_result.json',
        f'Build/UiWindowHost/{B5}/final/ZeroSisHost_x64.exe',
        'evidence/interactive_game/20261015T205926Z_208415de0fbc/request.json',
        'evidence/load_menu/runtime_preparation/prepared.json')}
    require(not list((PROJECT / 'Build').glob('pull-down-compositor-load-driver-owned-delete-*')),
            'Previous stage temporary frontend directory remains')
    write(output, {'schema': 'zerosis.owned_save_delete_linked_scope.v1',
        'utc': datetime.now(timezone.utc).isoformat(), 'previous_goal_turn': 'PROGRESS',
        'requirements': [
            'Retain the full original UI/gameplay x64/multicore and retail save/mod compatibility endpoint.',
            'Regenerate the current owned-save-delete Lua/UI catalog and compile/link one current x64 Host.',
            'Reuse only attested immutable B5 inputs and existing original asset paths; never hardlink mutable Source.',
            'Read actual PE bytes to prove the current script/catalog payload, not only source files or build logs.',
            'Prepare a private matching runtime with explicit private policy settings, without Host/GameCore/HWND execution.',
            'Keep EA0.6/default and retained recovery candidates unchanged; no archive schema/Mod ID changes.',
            'No retail MODS/user saves/UserSettings.ini or game-process access while human mod testing remains active.',
            'Remove owned compiler and prepare temporary artifacts after verification and measure unique NTFS allocation.'],
        'prior_source_conformance': progress['owned_save_delete_source_stage']['conformance'],
        'progress_before': artifact(PROGRESS), 'progress_backup': artifact(before),
        'generated_header_before': artifact(PROJECT / 'Source/Host/UiPopupAssets.generated.h'),
        'header_recovery': artifact(Path(header['path'])),
        'prepared_assets_recovery': donor['ui_assets'],
        'donor_build': artifact(donor_path), 'protected_artifacts': protected,
        'storage_before': artifact(PROJECT / 'evidence/storage/20261015T215252Z.json'),
        'cleanup_at_start': 'Previous stage retired all owned frontend temporary directories and extracted native fixture Build root. No full clone is needed.',
        'retail_mod_test_hold_active': True, 'default_promoted': False,
        'host_gamecore_hwnd_executed': False})
    print(json.dumps({'status': 'SCOPED', 'scope': artifact(output)}))


def run_command(name, arguments):
    require((STAGE / 'scope.json').is_file(), 'Stage scope is required')
    receipt = STAGE / (name + '_invocation.json')
    require(not receipt.exists(), 'Refusing to overwrite an invocation receipt')
    command = [sys.executable, '-B', '-X', 'utf8', *arguments]
    stdout, stderr = STAGE / (name + '.stdout.log'), STAGE / (name + '.stderr.log')
    require(not stdout.exists() and not stderr.exists(), 'Refusing to overwrite invocation logs')
    record = {'argv': command, 'started_utc': datetime.now(timezone.utc).isoformat(),
              'status': 'RUNNING', 'host_gamecore_hwnd_or_retail_user_state_accessed': False}
    write(receipt, record)
    with stdout.open('xb') as out, stderr.open('xb') as err:
        process = subprocess.run(command, cwd=PROJECT, stdout=out, stderr=err, check=False)
    record.update(exit_code=process.returncode, finished_utc=datetime.now(timezone.utc).isoformat(),
                  stdout=artifact(stdout), stderr=artifact(stderr),
                  status='PASS' if process.returncode == 0 else 'FAIL')
    results = []
    for line in stdout.read_text(encoding='utf8', errors='replace').splitlines():
        try:
            value = json.loads(line)
        except ValueError:
            continue
        if type(value) is dict:
            results.append(value)
    record['result'] = results[-1] if results else None
    write(receipt, record)
    print(json.dumps(record, ensure_ascii=False))
    return process.returncode


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('start', 'build', 'prepare'))
    parser.add_argument('--build-id')
    args = parser.parse_args()
    if args.action == 'start':
        start()
    elif args.action == 'build':
        raise SystemExit(run_command('build', [str(PROJECT / 'tools/build_ui_window_host.py'), '--reuse-frozen-build', B5]))
    else:
        require(args.build_id is not None and re.fullmatch(r'\d{8}T\d{6}Z_[0-9a-f]{12}', args.build_id),
                'An exact owned Host build ID is required')
        built = read(STAGE / 'build_invocation.json')
        require(built['exit_code'] == 0 and built['result']['build_id'] == args.build_id,
                'Private preparation must match this stage successful build')
        policy = STAGE / 'PolicyInfo.ini'
        require(not policy.exists(), 'Refusing to overwrite private policy input')
        policy.write_bytes(b'[UserSettings]\r\nPolicyInfo = 1\r\n')
        raise SystemExit(run_command('prepare', [str(STAGE / 'prepare_candidate.py'), '--build-id', args.build_id]))
