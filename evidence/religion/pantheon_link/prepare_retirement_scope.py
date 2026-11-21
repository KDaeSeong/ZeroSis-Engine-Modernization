"""Prepare an exact engine-only cleanup lease; do not remove payload files."""
from pathlib import Path
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
import stat
import sys

STAGE = Path(__file__).absolute().parent
PROJECT = STAGE.parents[2]
RETAIL = Path(r"C:\Users\home\OneDrive\Documents\My Games\Sid Meier's Civilization 5")
OUTPUT = STAGE / 'retire_superseded_scope.json'
PROGRESS = PROJECT / 'evidence/save_menu/20261013_original_screen/current_progress.json'
CURRENT_PROGRESS_SHA = 'c3180e19cead6bcd732973abd78462ba38f9a99bd2a6fc3f9980f492d25ae815'
HISTORICAL_PROGRESS_SHA = '2b2044938274bf039e29386565ccccb035e770d610225a15dd5ead4fef00c309'
BUILD_ID, RUN_ID = '20261017T231735Z_dfbda3dc7eb7', '20261017T233110Z_b4d9e31f65f9'
STEP = 'start'
PROTECTED, ROOTS, HISTORICAL_REPLACEMENTS = {}, [], []


def key(path):
    return os.path.normcase(os.path.abspath(path))


def absolute(path):
    path = Path(path)
    return path if path.is_absolute() else PROJECT / path


def ref(path):
    path = absolute(path)
    assert not path.is_relative_to(RETAIL), str(path)
    assert path.resolve(strict=True) == path, str(path)
    for member in (path, *path.parents):
        info = member.lstat()
        assert not stat.S_ISLNK(info.st_mode) and not getattr(info, 'st_file_attributes', 0) & 0x400, str(member)
        if member == PROJECT:
            break
    before = path.stat()
    assert stat.S_ISREG(before.st_mode), str(path)
    with path.open('rb') as stream:
        sha = hashlib.file_digest(stream, 'sha256').hexdigest()
    after = path.stat()
    assert (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns), str(path)
    return dict(path=str(path), bytes=after.st_size, sha256=sha)


def refs(value):
    if isinstance(value, dict):
        if isinstance(value.get('path'), str) and isinstance(value.get('sha256'), str) and len(value['sha256']) == 64:
            yield value
        else:
            for child in value.values():
                yield from refs(child)
    elif isinstance(value, list):
        for child in value:
            yield from refs(child)


def read(path):
    path = absolute(path)
    assert not path.is_relative_to(RETAIL), str(path)
    return json.loads(path.read_bytes())


def add(row):
    global STEP
    path = absolute(row['path'])
    STEP = 'protect ' + str(path)
    assert not any(path.is_relative_to(root) for root in ROOTS), 'Protected candidate intersection: ' + str(path)
    actual = ref(path)
    if key(path) == key(PROGRESS) and row['sha256'] == HISTORICAL_PROGRESS_SHA:
        assert actual['sha256'] == CURRENT_PROGRESS_SHA
        archive = STAGE / 'progress_before.json.gz'
        original = gzip.decompress(archive.read_bytes())
        assert len(original) == row['bytes'] and hashlib.sha256(original).hexdigest() == row['sha256']
        HISTORICAL_REPLACEMENTS.append(dict(historical_reference=row, preserved_in=ref(archive), current_reference=actual, decompressed_original_verified=True))
    else:
        assert actual['sha256'] == row['sha256'], 'Protected hash mismatch: ' + str(path)
        assert 'bytes' not in row or actual['bytes'] == row['bytes'], 'Protected size mismatch: ' + str(path)
    identity = key(path)
    assert identity not in PROTECTED or PROTECTED[identity] == actual, 'Conflicting reference: ' + str(path)
    PROTECTED[identity] = actual


def main():
    global STEP
    assert not sys.flags.optimize
    assert not OUTPUT.exists() and not (STAGE / 'superseded_retired.json').exists()
    parent = read(STAGE / 'scope.json')
    retry = read(STAGE / 'retry_02_scope.json')
    runtime = read(STAGE / 'runtime/scope.json')
    plan = read(STAGE / 'retire_superseded_plan.json')
    ROOTS.extend(Path(row['path']) for row in plan['candidate_roots'])
    assert [root.relative_to(PROJECT).as_posix() for root in ROOTS] == ['Build/UiWindowHost/20261016T122615Z_1af4a5449cf1', 'Build/InteractiveGameRuntime/20261016T123256Z_fae85fb9fe79', 'Build/InteractiveGameRuntime/20261016T143731Z_bc358fc8d62a']
    tool = STAGE / 'retire_superseded.py'
    compile(tool.read_bytes(), str(tool), 'exec', dont_inherit=True)
    for name in ['all_source_and_test_seals', 'protected_artifacts', 'original_assets', 'verifier_dependencies']:
        for row in refs(parent[name]):
            add(row)
    for name in ['additional_protected_artifacts', 'prior_attempt_artifacts', 'repair_artifacts', 'previous_failed_attempt', 'hardlink_permission_probes', 'new_source_snapshots_before_retry', 'mutable_derived_before_retry']:
        for row in refs(retry[name]):
            add(row)
    for name in ['source_inputs', 'additional_protected_artifacts', 'private_policy', 'helper_module', 'preserved_identity_guard', 'preparation_guard', 'progress_backup']:
        for row in refs(runtime[name]):
            add(row)
    objects = read(STAGE / 'build_objects_retired.json')
    raw_retired = {key(absolute(row['path'])) for row in refs(objects['objects_before'])}
    assert len(raw_retired) == 10
    rollback_build, rollback_run = '20261016T142908Z_fc2e23c1fd1e', '20261017T005450Z_9e280ca26b49'
    report_current = PROJECT / 'evidence/ui_window_host' / BUILD_ID / 'build_result.json'
    report_rollback = PROJECT / 'evidence/ui_window_host' / rollback_build / 'build_result.json'
    for row in refs(read(report_current)):
        if key(absolute(row['path'])) not in raw_retired:
            add(row)
    old_report = read(report_rollback)
    for name in ['sources', 'compiler_inputs', 'provider_inputs', 'system_libraries', 'provider_reports', 'ui_assets', 'build_tools', 'executable', 'map', 'link_log', 'link_response', 'response', 'compile_log']:
        for row in refs(old_report[name]):
            add(row)
    preserved = [PROJECT / 'Build/UiWindowHost' / name for name in [BUILD_ID, rollback_build, '20261011T124501Z_5bf7bf678d40', '20261014T110906Z_a60e98e7bde6']]
    preserved += [PROJECT / 'Build/InteractiveGameRuntime' / name for name in [RUN_ID, rollback_run, '20261012T121847Z_732a6d5f07ea', '20261014T114953Z_5248d2dd93bc']]
    for path in preserved:
        assert path.resolve(strict=True) == path and path.is_dir(), str(path)
        assert all(not path.is_relative_to(root) and not root.is_relative_to(path) for root in ROOTS), str(path)
    sensitive = {'sessions', 'attempts', 'frames', 'screenshots', 'attempt.json', 'result.json', 'driver_result.json', 'window_result.json', 'stdout.log', 'stderr.log'}
    for run in [RUN_ID, rollback_run]:
        request_path = PROJECT / 'evidence/interactive_game' / run / 'request.json'
        add(ref(request_path))
        for row in read(request_path)['runtime_inputs']:
            add(row)
        stack = [PROJECT / 'Build/InteractiveGameRuntime' / run]
        while stack:
            folder = stack.pop()
            with os.scandir(folder) as entries:
                for entry in entries:
                    path = Path(entry.path)
                    info, name = path.lstat(), path.name.casefold()
                    assert not stat.S_ISLNK(info.st_mode) and not getattr(info, 'st_file_attributes', 0) & 0x400, str(path)
                    assert name not in sensitive and not name.startswith('checkpoint') and path.suffix.casefold() not in ['.zssave', '.civ5save', '.sav', '.save', '.dmp', '.mdmp'], str(path)
                    if stat.S_ISDIR(info.st_mode):
                        stack.append(path)
                    else:
                        add(ref(path))
    release_path = PROJECT / 'Play/EarlyAccess/release.json'
    add(ref(release_path))
    release = read(release_path)
    add(release['request'])
    for row in read(release['request']['path'])['runtime_inputs']:
        add(row)
    add(ref(PROJECT / 'tools/Start-Engine.ps1'))
    readonly_ids = {(row['device_id'], row['file_id']) for row in plan['files'] if row['attributes'] & 1}
    covered = set()
    for run in ['20261016T123256Z_fae85fb9fe79', '20261016T143731Z_bc358fc8d62a']:
        request_path = PROJECT / 'evidence/interactive_game' / run / 'request.json'
        add(ref(request_path))
        for row in read(request_path)['materializations']:
            if 'cache' not in row:
                assert row['materialization_method'] == 'private-copy'
                assert Path(row['target']).name in ('rules.db', 'localization.db')
                continue
            path = absolute(row['cache'])
            assert path.is_relative_to(PROJECT / 'Build/RuntimeInputCache'), str(path)
            info = path.stat()
            identity = (str(info.st_dev), format(info.st_ino, 'x'))
            assert identity in readonly_ids and info.st_file_attributes & 1, str(path)
            add(dict(path=str(path), bytes=row['size'], sha256=row['sha256']))
            covered.add(identity)
    assert covered == readonly_ids and len(covered) == 17
    current = ref(PROGRESS)
    assert current['sha256'] == CURRENT_PROGRESS_SHA
    scope = dict(schema='zerosis.pantheon_link.superseded_retirement_scope.v1', utc=datetime.now(timezone.utc).isoformat(), prior_goal_turn_classification='NO_PROGRESS_STATUS_ONLY_REVALIDATED_NOW', plan=ref(STAGE / 'retire_superseded_plan.json'), retirement_tool=ref(tool), current_host_build_id=BUILD_ID, current_runtime_id=RUN_ID, pe_attestation=ref(STAGE / f'attestation_{BUILD_ID}.json'), runtime_identity=ref(STAGE / 'runtime/preparation_identity_audit.json'), runtime_request=ref(PROJECT / 'evidence/interactive_game' / RUN_ID / 'request.json'), object_retirement=ref(STAGE / 'build_objects_retired.json'), progress_before_retirement=current, readonly_unlink_probe=ref(STAGE / 'readonly_unlink_probe.json'), preserved_roots=[str(path) for path in preserved], deletion_allowed=True, retail_mod_test_hold_active=True, host_gamecore_hwnd_execution_allowed=False, retail_user_state_or_game_process_access_allowed=False, default_promotion_allowed=False, full_engine_goal_complete=False, readonly_cache_aliases_covered=17, historical_reference_migrations=HISTORICAL_REPLACEMENTS, authorization_source='Existing explicit human cleanup requests; new current build, PE, private runtime and probe gates passed. Only exact three obsolete payload roots are authorized.', retirement_limits='Old version live-path revalidation requires regeneration. Native UI, campaign, saves, mods and real multicore acceptance remain unverified. No shared attributes will be changed.')
    for path in [report_current, report_rollback, STAGE / 'scope.json', STAGE / 'retry_02_scope.json', STAGE / 'runtime/scope.json', STAGE / 'progress_before.json.gz', STAGE / 'progress_retirement_authorized.json.gz', STAGE / 'progress_publication_interim.json', STAGE / 'build_retry_02_run.json', STAGE / 'catalog_retry_02.json', STAGE / 'retire_superseded.pre_readonly.py', STAGE / 'probe_readonly_unlink.py', STAGE / 'readonly_unlink_probe.json', Path(__file__)]:
        add(ref(path))
    for name in ['plan', 'retirement_tool', 'pe_attestation', 'runtime_identity', 'runtime_request', 'object_retirement', 'progress_before_retirement', 'readonly_unlink_probe']:
        add(scope[name])
    scope['protected_artifacts'] = sorted(PROTECTED.values(), key=lambda row: key(row['path']))
    assert len(scope['protected_artifacts']) > 1100
    assert len(HISTORICAL_REPLACEMENTS) == 1
    STEP = 'exclusive scope write'
    with OUTPUT.open('x', encoding='utf-8') as stream:
        json.dump(scope, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps(dict(status='PASS_SCOPE_CREATED_NO_DELETION', scope=ref(OUTPUT), protected=len(PROTECTED), protected_readonly_ids=len(covered), retirement_tool=scope['retirement_tool'], preserved_roots=len(preserved), candidate_files=len(plan['files']), candidate_directories=len(plan['directories'])), ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except BaseException as failure:
        print(json.dumps(dict(status='SCOPE_NOT_APPLIED', step=STEP, error=repr(failure)), ensure_ascii=False))
        sys.exit(1)
