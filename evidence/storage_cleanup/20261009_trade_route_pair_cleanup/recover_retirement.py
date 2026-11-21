"""New residual plan for the zero-deletion interruption; never replay its latch."""
import argparse
from concurrent.futures import Future, ThreadPoolExecutor
import gzip
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
from threading import Lock
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OUT = HERE / 'recovery_01'
sys.path.insert(0, str(ROOT / 'tools'))
import prune_superseded_runtime_artifacts as retirement

ORIGINAL_PLAN_SHA = '0f32e5d03439f0da44903622d35da2746d5889a99149db40dbcb17bbce628c4a'


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def emit(**row):
    print(json.dumps(row, ensure_ascii=False), flush=True)


def artifact(path):
    return {'path': str(path), 'sha256': retirement.digest(path)}


def ledger(path):
    with gzip.open(path, 'rt', encoding='utf8') as stream:
        return [json.loads(line) for line in stream]


def identity(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


def parallel_hashes(expected, phase):
    """Hash every live file; share only simultaneous reads of identical files."""
    cache, lock = {}, Lock()

    def check(item):
        name, expected_sha = item
        path = Path(name)
        key = identity(retirement.regular(path))
        with lock:
            owner = key not in cache
            future = cache.setdefault(key, Future())
        if owner:
            try:
                future.set_result(retirement.digest(path))
            except BaseException as error:
                future.set_exception(error)
                raise
        retirement.require(future.result() == expected_sha, 'Protected SHA changed: ' + name)
        retirement.require(identity(retirement.regular(path)) == key, 'File changed while hashing: ' + name)

    with ThreadPoolExecutor(max_workers=4) as pool:
        for count, _ in enumerate(pool.map(check, expected.items()), 1):
            if count % 2000 == 0:
                emit(phase=phase, checked=count, total=len(expected))
    emit(phase=phase, checked=len(expected), total=len(expected), status='PASS')


def wait_idle():
    """Keep the existing global guard; wait only for verified live processes."""
    deadline = time.monotonic() + 900
    while True:
        try:
            retirement.no_active_host()
            return
        except RuntimeError:
            query = subprocess.run(['powershell.exe', '-NoProfile', '-Command',
                "$ErrorActionPreference='Stop'; $p=@(Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^(ZeroSisHost_x64|cl|link)\\.exe$' } | Select-Object ProcessId,Name); ConvertTo-Json -InputObject $p -Compress"],
                capture_output=True, text=True, timeout=20, creationflags=subprocess.CREATE_NO_WINDOW)
            retirement.require(query.returncode == 0, 'Cannot verify active compiler/Host state')
            active = json.loads(query.stdout)
            retirement.require(isinstance(active, list) and active, 'Idle guard failed without a verified live process')
            retirement.require(time.monotonic() < deadline, 'Verified active process has not finished within 15 minutes')
            emit(phase='WAIT_VERIFIED_ACTIVE_PROCESS', processes=active)
            time.sleep(10)


def verify_baseline():
    retirement.require(retirement.ROOT == ROOT, 'Wrong project root')
    retirement.require(retirement.digest(HERE / 'plan.json') == ORIGINAL_PLAN_SHA, 'Original plan changed')
    original = read(HERE / 'plan.json')
    failed = read(HERE / 'cleanup.json')
    retirement.require(failed['status'] == 'FAILED_PARTIAL_RETIREMENT_RETAINED'
                       and failed['removed_files'] == failed['removed_logical_bytes'] == 0
                       and failed['completed_directories'] == []
                       and failed['protected_hashes_verified_before'] is True
                       and failed['plan_sha256'] == ORIGINAL_PLAN_SHA,
                       'Recovery applies only to the verified zero-deletion interruption')
    retirement.require(original['script_sha256'] == retirement.digest(Path(retirement.__file__)), 'Retirement helpers changed')
    for name in ('protected', 'ledger', 'retired_statuses'):
        path = retirement.boundary(Path(original[name]['path']))
        retirement.require(path.parent == HERE and retirement.digest(path) == original[name]['sha256'], 'Original ledger changed')
    targets = [retirement.legal_target(ROOT / row['path']) for row in original['directories']]
    retirement.require(len(set(targets)) == 6 and original['files'] == 11555, 'Reviewed six-folder scope changed')
    return original, targets


def residual_inventory(plan, targets):
    rows = ledger(Path(plan['ledger']['path']))
    recorded = {str(ROOT / row['path']): row for row in rows}
    retirement.require(len(rows) == len(recorded) == plan['files'], 'Duplicate or missing ledger paths')
    actual = {}
    for target in targets:
        for path, info in retirement.inventory(target):
            name = str(path)
            retirement.require(name in recorded, 'Unplanned residual file: ' + name)
            row = recorded[name]
            retirement.require(identity(info) == (row['device'], row['file_id'], row['bytes'], row['mtime_ns']),
                               'Residual identity changed: ' + name)
            actual[name] = row['sha256']
    retirement.require(actual.keys() == recorded.keys(), 'Residual target inventory changed')
    return rows, actual


def prepare():
    retirement.require(not OUT.exists(), 'Do not overwrite a residual plan')
    wait_idle()
    original, targets = verify_baseline()
    _, actual = residual_inventory(original, targets)
    parallel_hashes(actual, 'residual_files')
    OUT.mkdir()
    plan = dict(original)
    for name, basename in (('protected', 'protected.json.gz'), ('ledger', 'retired-files.jsonl.gz'),
                           ('retired_statuses', 'retired-statuses.json.gz')):
        target = OUT / basename
        shutil.copyfile(original[name]['path'], target)
        retirement.require(retirement.digest(target) == original[name]['sha256'], 'Residual ledger copy differs')
        plan[name] = artifact(target)
    plan.update(scope='NEW_RESIDUAL_PLAN_AFTER_VERIFIED_ZERO_DELETION_INTERRUPTION',
                prior_plan=artifact(HERE / 'plan.json'), prior_attempt=artifact(HERE / 'cleanup.json'),
                residual_inventory_and_hashes_rechecked=True,
                recovery_script=artifact(Path(__file__)))
    destination = OUT / 'plan.json'
    destination.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    emit(status='PREVIEW_ONLY', plan=str(destination), sha256=retirement.digest(destination),
         files=plan['files'], directories=len(targets), protected_files=plan['current_dependency_files'])


def apply(expected_plan_sha):
    plan_path = retirement.boundary(OUT / 'plan.json')
    retirement.require(retirement.digest(plan_path) == expected_plan_sha, 'Reviewed residual plan changed')
    retirement.require(not (OUT / 'cleanup.json').exists(), 'Residual plan already started; do not replay')
    plan = read(plan_path)
    original, targets = verify_baseline()
    retirement.require(plan['status'] == 'PREVIEW_ONLY' and plan['root'] == str(ROOT), 'Wrong residual plan')
    retirement.require(plan['directories'] == original['directories'] and plan['files'] == original['files'], 'Residual scope differs')
    retirement.require(plan['prior_plan'] == artifact(HERE / 'plan.json')
                       and plan['prior_attempt'] == artifact(HERE / 'cleanup.json'), 'Prior attempt record changed after planning')
    retirement.require(plan['recovery_script'] == artifact(Path(__file__)), 'Recovery code changed after planning')
    for name in ('protected', 'ledger', 'retired_statuses'):
        path = retirement.boundary(Path(plan[name]['path']))
        retirement.require(path.parent == OUT and retirement.digest(path) == plan[name]['sha256'] == original[name]['sha256'],
                           'Residual ledger changed')
    with gzip.open(plan['protected']['path'], 'rt', encoding='utf8') as stream:
        protected = json.load(stream)
    retirement.require(len(protected) == plan['current_dependency_files'], 'Protection count differs')
    retirement.require(not any(any(Path(name).is_relative_to(target) for target in targets) for name in protected),
                       'Protected file intersects deletion set')
    wait_idle()
    parallel_hashes(protected, 'protected_before')
    test = OUT / 'readonly-hardlink-check'
    test.mkdir()
    source, alias = test / 'source', test / 'alias'
    source.write_bytes(b'preserved-readonly-hardlink')
    os.link(source, alias)
    os.chmod(source, stat.S_IREAD)
    attrs = source.stat().st_file_attributes
    retirement.unlink_without_attribute_changes(alias)
    retirement.require(not alias.exists() and source.read_bytes() == b'preserved-readonly-hardlink'
                       and source.stat().st_file_attributes == attrs, 'Readonly hardlink self-test failed')
    retirement.unlink_without_attribute_changes(source)
    test.rmdir()
    wait_idle()
    rows, _ = residual_inventory(plan, targets)
    wait_idle()
    progress = {'status': 'REMOVING', 'plan_sha256': expected_plan_sha, 'removed_files': 0,
                'removed_logical_bytes': 0, 'completed_directories': [],
                'protected_hashes_verified_before': True, 'readonly_hardlink_attribute_preservation_verified': True,
                'volume_free_bytes_before': shutil.disk_usage(ROOT).free, 'errors': []}
    output = OUT / 'cleanup.json'

    def checkpoint():
        output.write_text(json.dumps(progress, ensure_ascii=False, indent=2) + '\n', encoding='utf8')

    checkpoint()
    try:
        for row in rows:
            path = ROOT / row['path']
            retirement.require('..' not in path.parts and any(path.is_relative_to(target) for target in targets), 'Unapproved deletion path')
            retirement.require(identity(retirement.regular(path)) == (row['device'], row['file_id'], row['bytes'], row['mtime_ns']),
                               'Deletion identity changed: ' + str(path))
            retirement.require(retirement.digest(path) == row['sha256'], 'Deletion SHA changed: ' + str(path))
            retirement.unlink_without_attribute_changes(path)
            retirement.require(not path.exists(), 'Deleted path still exists')
            progress['removed_files'] += 1
            progress['removed_logical_bytes'] += row['bytes']
            if progress['removed_files'] % 1000 == 0:
                checkpoint()
                emit(phase='delete', files=progress['removed_files'], total=plan['files'])
        for target in targets:
            for current, dirs, files in os.walk(target, topdown=False, followlinks=False):
                retirement.require(not files, 'Unplanned file remains in target')
                retirement.boundary(Path(current)).rmdir()
            progress['completed_directories'].append(str(target.relative_to(ROOT)))
        checkpoint()
        parallel_hashes(protected, 'protected_after')
        retirement.require(progress['removed_files'] == plan['files'], 'Deletion count differs')
        progress.update(status='PASS_OBSOLETE_ARTIFACT_RETIREMENT', protected_hashes_verified_after=True)
    except BaseException as error:
        progress['status'] = 'FAILED_PARTIAL_RETIREMENT_RETAINED'
        progress['errors'].append(type(error).__name__ + ': ' + str(error))
        raise
    finally:
        progress['volume_free_bytes_after'] = shutil.disk_usage(ROOT).free
        progress['volume_free_bytes_delta'] = progress['volume_free_bytes_after'] - progress['volume_free_bytes_before']
        checkpoint()
        emit(status=progress['status'], removed_files=progress['removed_files'], report=str(output), errors=progress['errors'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--prepare', action='store_true')
    mode.add_argument('--apply-plan-sha')
    args = parser.parse_args()
    prepare() if args.prepare else apply(args.apply_plan_sha)
