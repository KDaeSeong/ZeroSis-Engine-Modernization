"""Read-only exact cleanup planning for one failed dependency-discovery tree."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

sys.dont_write_bytecode = True
STAGE = Path(__file__).absolute().parent
PROJECT = STAGE.parents[3]
BUILD_ID = '20261115T033820Z_3377b24b6421'
ROOT = PROJECT / 'Build/UiWindowHost' / BUILD_ID
PHASE = STAGE.parent
FAILURE_DIR = PHASE / 'host_build/attempts/3377b24b642104544b68'

spec = importlib.util.spec_from_file_location('failed_discovery_storage', PROJECT / 'tools/audit_exit_host_storage.py')
storage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(storage)


def write_new(path, value):
    with path.open('x', encoding='utf8') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def snapshot(path):
    path = Path(path).absolute()
    before = storage.ordinary(path)
    digest = storage.digest(path)
    allocation = storage.allocated(path)
    after = storage.ordinary(path)
    assert storage.metadata(before) == storage.metadata(after), path
    return dict(path=str(path), **storage.metadata(after), sha256=digest, allocated_bytes=allocation)


def directory(path):
    path = Path(path).absolute()
    for parent in (path, *path.parents):
        before = os.stat(parent, follow_symlinks=False)
        assert stat.S_ISDIR(before.st_mode) and not before.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT
    info = os.stat(path, follow_symlinks=False)
    return dict(path=str(path), file_identity=[info.st_dev, info.st_ino], mtime_ns=info.st_mtime_ns,
                file_attributes=info.st_file_attributes, links=info.st_nlink)


def main():
    assert ROOT.is_absolute() and ROOT.parent == PROJECT / 'Build/UiWindowHost'
    assert ROOT.resolve() == ROOT and ROOT.name == BUILD_ID
    assert not (STAGE / 'plan.json').exists()
    failure_path = FAILURE_DIR / 'failure.json'
    failure = json.loads(failure_path.read_text('utf8'))
    assert failure['status'] == 'FAILED_DO_NOT_REPLAY' and failure['build_id'] == BUILD_ID
    assert failure['detail'].endswith('discover_terrain_renderer')
    assert not failure['completed_translation_units'] and not failure['materialized']
    assert failure['host_sdk_clr_window_gpu_or_dll_executed'] is False
    assert not any((ROOT / name).exists() for name in ('frozen', 'final', 'objects'))
    assert {x['phase'] for x in failure['commands']} == {
        'environment', 'discover_host_main', 'discover_window', 'discover_renderer',
        'discover_world_renderer', 'discover_terrain_renderer'}
    directories, files = [directory(ROOT)], []
    for parent, children, names in os.walk(ROOT, followlinks=False):
        for name in children:
            directories.append(directory(Path(parent) / name))
        for name in names:
            path = Path(parent) / name
            assert path.is_relative_to(ROOT) and path.suffix in ('.cmd', '.rsp', '.json')
            row = snapshot(path)
            assert row['links'] == 1 and not row['file_attributes'] & 0x401, path
            files.append(row)
    assert len(files) == 11 and len(directories) == 8
    assert sum(path['path'].endswith('.sourceDependencies.json') for path in files) == 5
    assert sum(path['path'].endswith('.compile.rsp') for path in files) == 5
    assert any(path['path'].endswith('read_build_environment.cmd') for path in files)

    command = ['rg', '-l', '-F', BUILD_ID.split('_')[1], 'Source', 'Tests', 'tools', 'docs', 'evidence', 'Build',
               '-g', '*.json', '-g', '*.py', '-g', '*.md', '-g', '*.cpp', '-g', '*.h', '-g', '*.inc',
               '-g', '*.ps1', '-g', '*.rsp', '-g', '*.txt',
               '-g', '!evidence/world_terrain_original/phase2/cleanup_failed_discovery/**']
    scan = subprocess.run(command, cwd=PROJECT, capture_output=True, timeout=90,
                          creationflags=subprocess.CREATE_NO_WINDOW)
    assert scan.returncode in (0, 1) and not scan.stderr, scan.stderr[:500]
    matches = sorted({PROJECT / name for name in scan.stdout.decode('utf8').splitlines()})
    outside = [path for path in matches if not path.is_relative_to(ROOT)]
    allowed_history = {FAILURE_DIR / 'started.json', failure_path}
    assert set(outside).issubset(allowed_history), outside
    reverse = dict(status='PASS_NO_CURRENT_INPUT_REVERSE_REFERENCE', command=command,
                   exit_code=scan.returncode, matched_files=[str(path) for path in matches],
                   external_references=[dict(path=str(path), classification='TERMINAL_FAILED_ATTEMPT_HISTORY') for path in outside],
                   scan_output_sha256=hashlib.sha256(scan.stdout).hexdigest(),
                   limitations='Textual references in the listed source/config/evidence formats; current build plans and protected paths are also checked structurally below.')
    write_new(STAGE / 'reverse_refs.json', reverse)

    current_plan_path = PHASE / 'host_build/plan_retry01.json'
    current_plan = json.loads(current_plan_path.read_text('utf8'))
    assert BUILD_ID not in current_plan_path.read_text('utf8')
    current_rows = list(storage.path_rows(current_plan))
    assert not any(Path(row['path']).is_relative_to(ROOT) for row in current_rows)
    protection_path = PHASE / 'protection_before.json.gz'
    protection = json.loads(gzip.decompress(protection_path.read_bytes()).decode('utf8'))
    protected_rows = list(storage.path_rows(protection))
    assert not any(Path(row['path']).is_relative_to(ROOT) for row in protected_rows)

    preserve = [snapshot(path) for path in sorted(FAILURE_DIR.iterdir()) if path.is_file()]
    preserve += [snapshot(path) for path in sorted((PHASE / 'compile_fix').iterdir()) if path.is_file()]
    preserve += [snapshot(current_plan_path), snapshot(protection_path)]
    sentinels = [PROJECT / 'Build/UiWindowHost' / identifier / 'final/ZeroSisHost_x64.exe'
                 for identifier in ('20261115T024443Z_8470b8d966f8', '20261115T005626Z_256252d8abe3')]
    sentinels += [PROJECT / 'Build/UnitGreatWorkSaveSDK/2bdcdf80a1695780f864/CvGameCoreDLL_Expansion2_x64.dll']
    sentinels += [PROJECT / 'Build/InteractiveGameRuntime' / identifier / 'Play.ps1'
                  for identifier in ('20261115T011241Z_4c8fd55e99db', '20261108T003146Z_40a8030edf08')]
    sentinels += [path for path in (PROJECT / 'Build/InteractiveGameRuntime/20261108T003146Z_40a8030edf08/sessions').rglob('*')
                  if path.is_file() and path.suffix.lower() in ('.zssave', '.civ5save')]
    preserve += [snapshot(path) for path in sentinels]
    assert all(not Path(row['path']).is_relative_to(ROOT) for row in preserve)
    file_counts = Counter(tuple(row['file_identity']) for row in files)
    unique = {tuple(row['file_identity']): row for row in files}
    protected_identities = {tuple(row['file_identity']) for row in preserve}
    assert not protected_identities.intersection(unique)
    plan = dict(schema='zerosis.original_fog.phase2.failed_discovery_cleanup_plan.v1',
                utc=datetime.now(timezone.utc).isoformat(), status='PLAN_ONLY_AWAIT_SUCCESS_AND_ROOT_APPLY_INSTRUCTION',
                root=str(ROOT), build_id=BUILD_ID, failure=snapshot(failure_path),
                reverse_reference_review=snapshot(STAGE / 'reverse_refs.json'),
                files=sorted(files, key=lambda row: row['path']), directories=directories,
                preserved=preserve, preserved_file_count=len(preserve),
                logical_bytes=sum(row['bytes'] for row in files), unique_file_ids=len(unique),
                expected_unique_allocated_release=sum(row['allocated_bytes'] for key, row in unique.items()
                    if file_counts[key] == row['links']),
                protected_full_baseline_paths=len(protected_rows), latest_retry_plan=snapshot(current_plan_path),
                apply_requirements=[
                    'Explicit root apply instruction after a successful new Host independent attestation',
                    'Exact SHA of this plan; failure/log/fix-backup hashes and protected sentinels unchanged',
                    'Re-enumerate the exact same 11 files and 8 directories; reject new files or reparse points',
                    'Revalidate every file ID/SHA/mtime/attributes/link count/allocation before any deletion',
                    'Delete only each enumerated ordinary file, then verified empty directories from deepest to root',
                    'Rehash preserved evidence/sentinels afterwards and write a thin deletion receipt'],
                deleted_files=0, source_tests_build_helpers_modified=False,
                native_host_gamecore_clr_hwnd_gpu_audio_or_game_executed=False)
    write_new(STAGE / 'plan.json', plan)
    print(json.dumps(dict(status=plan['status'], files=len(files), directories=len(directories),
                         logical_bytes=plan['logical_bytes'], expected_release=plan['expected_unique_allocated_release'],
                         preserved=len(preserve), external_references=len(outside),
                         plan_sha256=storage.digest(STAGE / 'plan.json'))))


if __name__ == '__main__':
    main()
