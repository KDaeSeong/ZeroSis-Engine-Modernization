"""Audit and publish the prepared private pair; never start its native images."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import gzip
import hashlib
import json
import os
from pathlib import Path
import sys

PROJECT = Path(__file__).absolute().parents[3]
STAGE = Path(__file__).absolute().parent
sys.path.insert(0, str(PROJECT / 'tools'))
import prepare_current_sdk_play as base


def write_new(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write('\n')


def file_id(path):
    info = base.ordinary(Path(path))
    return info.st_dev, info.st_ino


class FileStandardInfo(ctypes.Structure):
    _fields_ = [('AllocationSize', ctypes.c_longlong), ('EndOfFile', ctypes.c_longlong),
                ('NumberOfLinks', wintypes.DWORD), ('DeletePending', ctypes.c_ubyte),
                ('Directory', ctypes.c_ubyte)]


kernel = ctypes.WinDLL('kernel32', use_last_error=True)
kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                              wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
kernel.CreateFileW.restype = wintypes.HANDLE
kernel.GetFileInformationByHandleEx.argtypes = [wintypes.HANDLE, ctypes.c_int,
                                               wintypes.LPVOID, wintypes.DWORD]
kernel.GetFileInformationByHandleEx.restype = wintypes.BOOL
kernel.CloseHandle.argtypes = [wintypes.HANDLE]
kernel.CloseHandle.restype = wintypes.BOOL


def allocation(path):
    before = base.ordinary(path)
    handle = kernel.CreateFileW(str(path), 0, 7, None, 3, 0x200000, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        value = FileStandardInfo()
        if not kernel.GetFileInformationByHandleEx(handle, 1, ctypes.byref(value), ctypes.sizeof(value)):
            raise ctypes.WinError(ctypes.get_last_error())
        after = base.ordinary(path)
        assert (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) == (
            after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
        assert value.EndOfFile == before.st_size and not value.Directory
        return value.AllocationSize
    finally:
        assert kernel.CloseHandle(handle)


def main():
    assert not sys.flags.optimize
    assert PROJECT == base.PROJECT and STAGE == PROJECT / 'evidence/native_restore_contract/pair_preparation'
    assert not (STAGE / 'publication.json').exists()
    result_path = STAGE / 'materialization/result.json'
    result = base.read(result_path)
    assert result['status'] == 'PASS_CURRENT_HOST_AND_GREAT_WORK_SDK_PREPARED_NOT_EXECUTED'
    assert result['host_build_id'] == '20261024T042219Z_e6399c82ee5c'
    assert result['host_or_sdk_executed'] is False and result['native_attempts'] == 0
    assert not result['guard_denials'] and result['new_game_only'] is True
    request_ref = base.checked(result['request'])
    request = base.read(Path(request_ref['path']))
    runtime = PROJECT / 'Build/InteractiveGameRuntime' / result['run_id']
    assert not (runtime / 'sessions').exists()
    started = base.read(STAGE / 'materialization/started.json')
    for row in started['protected_inputs']:
        base.checked(row)
    rows = {Path(row['path']).name: base.checked(row) for row in request['runtime_inputs']}
    assert len(rows) == 24 and request['smoke'] is False and request['resume_from'] is None
    assert request['stage_or_mods_changed'] is False
    assert rows['ZeroSisHost_x64.exe']['sha256'] == (
        '2212f0e59812b68330990e4b0c0c974ad3baba78727f15fbd701b2a1b7d24da8')
    assert rows['CvGameCoreDLL_Expansion2_x64.dll']['sha256'] == (
        '430f3122d0b555d6daae14aa7c011ef43ce8f978270477c8af596ca4b0493ab9')
    assert request['host_runtime_validation']['registered_build_id'] == result['host_build_id']
    assert request['host_runtime_validation']['historical_operational_backups_verified'] == 3
    assert request['runtime_sdk_candidate_scope']['host_sdk_execution_verified'] is False
    assert request['runtime_sdk_candidate_scope']['new_game_only'] is True
    resume = Path(base.checked(request['resume_launcher'])['path'])
    assert "throw 'Save loading is disabled" in resume.read_text(encoding='utf-8-sig')
    existing_ids, links = set(), []
    for method in request['materializations']:
        if method['materialization_method'] != 'hardlink':
            continue
        cache, target = Path(method['cache']), Path(method['target'])
        assert file_id(cache) == file_id(target)
        assert target.stat().st_file_attributes & 1
        assert base.artifact(cache)['sha256'] == method['sha256']
        if method['cache_method'] == 'cache-hit':
            existing_ids.add(file_id(cache))
        links.append(dict(cache=str(cache), target=str(target), file_identity=list(file_id(cache))))
    assert len(links) == 15 and len(existing_ids) == 14 and len(result['cache_created']) == 1
    old_request = base.read(PROJECT / 'evidence/interactive_game/20261024T031412Z_e06aeb61ed6a/request.json')
    old_rows = {Path(row['path']).name: row for row in old_request['runtime_inputs']}
    private_ids = set()
    for name in ('rules.db', 'localization.db'):
        path = Path(rows[name]['path'])
        assert path.is_relative_to(runtime)
        assert path.stat().st_nlink == 1 and not path.stat().st_file_attributes & 1
        assert file_id(path) != file_id(old_rows[name]['path'])
        private_ids.add(file_id(path))
    assert len(private_ids) == 2 and not private_ids & existing_ids
    support = request['interactive_ui_support_inventory']['tools']
    assert len(support) == 6
    for row in support.values():
        frozen = base.checked(row['frozen'])
        source = base.artifact(Path(row['source']['original_path']))
        assert frozen['sha256'] == source['sha256'] == row['source']['sha256']
    regression = base.read(STAGE / 'regression_tests.json')
    current_tests = base.read(STAGE / 'current_host_tests.json')
    assert regression['tests_run'] == 74 and regression['failures'] == 0 and regression['errors'] == 1
    assert regression['failed_tests'] == [
        'test_actual_current_report_static_validation (test_current_runtime_sdk_input.RetainedEvidenceTests.test_actual_current_report_static_validation)']
    assert current_tests['tests_run'] == 20 and current_tests['failures'] == current_tests['errors'] == 0
    for proof in (regression, current_tests):
        assert not proof['native_attempts'] and proof['host_or_sdk_executed'] is False
        for row in proof['inputs']:
            base.checked(row)
    for filename, status in (
        ('actual_host_input_gate.json', 'PASS_ACTUAL_CURRENT_RESTORE_HOST_INPUT_GATE'),
        ('actual_sdk_input_gate.json', 'PASS_ACTUAL_SELECTED_GREAT_WORK_SDK_INPUT_GATE')):
        gate = base.read(STAGE / filename)
        assert gate['status'] == status and not gate['native_attempts']
    audit = dict(schema='zerosis.native_restore.prepared_pair_audit.v1',
        status='PASS_ACTUAL_PREPARED_RESTORE_PAIR_INPUTS_AND_PRIVATE_STORAGE',
        preparation=base.artifact(result_path), request=request_ref, run_id=result['run_id'],
        runtime_inputs_rehashed=24, immutable_links_verified=links,
        existing_cache_file_ids_reused=14, new_cache_payloads=1, separate_private_databases=2,
        frozen_ui_tools_verified=6, protected_inputs_rehashed=len(started['protected_inputs']),
        new_component_tests_passed=20, legacy_regression_tests_passed=73,
        older_sdk_parent_regression_rejects_current_delta=True,
        selected_great_work_sdk_actual_gate_passed=True,
        host_or_sdk_executed=False, native_sessions_created=False,
        original_game_mods_settings_saves_changed=False, default_promoted=False,
        old_pair_and_native_saves_preserved=True, full_engine_goal_complete=False)
    write_new(STAGE / 'audit.json', audit)
    prior_update = base.read(PROJECT / 'evidence/native_restore_contract/publication/progress_update.json')
    changes = []
    backup_root = STAGE / 'publication_backups'
    backup_root.mkdir(exist_ok=False)
    for entry in prior_update['changed_metadata']:
        before = base.checked(entry['after'])
        path = Path(before['path'])
        raw = path.read_bytes()
        backup = backup_root / (path.name + '.before.gz')
        with backup.open('xb') as stream:
            stream.write(gzip.compress(raw, mtime=0))
        assert gzip.decompress(backup.read_bytes()) == raw
        changes.append(dict(before=before, backup=base.artifact(backup), gzip_roundtrip_verified=True))
    pre_edit = dict(schema='zerosis.native_restore.prepared_pair_publication_before.v1',
        audit=base.artifact(STAGE / 'audit.json'), publisher=base.artifact(Path(__file__).absolute()),
        metadata=changes, host_or_sdk_executed=False)
    write_new(STAGE / 'publication_pre_edit.json', pre_edit)
    progress = PROJECT / 'evidence/save_menu/20261013_original_screen/current_progress.json'
    document = PROJECT / 'docs/M7_RETAIL_SAVE_BOUNDARY.md'
    data = base.read(progress)
    assert data['current_host_build_id'] == result['host_build_id']
    data['previous_private_pair_startup_stage'] = data['latest_host_sdk_preparation_stage']
    proofs = {name: base.artifact(STAGE / filename) for name, filename in (
        ('preparation', 'materialization/result.json'), ('audit', 'audit.json'),
        ('new_host_tests', 'current_host_tests.json'), ('regression', 'regression_tests.json'),
        ('actual_host_input_gate', 'actual_host_input_gate.json'),
        ('actual_selected_sdk_gate', 'actual_sdk_input_gate.json'),
        ('operational_revisions', 'operational_revisions.json'))}
    pair = dict(status='CURRENT_RESTORE_CONTRACT_PAIR_PREPARED_NOT_EXECUTED',
        run_id=result['run_id'], host_build_id=result['host_build_id'], host=result['host'],
        gamecore=result['gamecore'], bundle_manifest=result['bundle_manifest'], proofs=proofs,
        runtime_inputs=24, immutable_hardlinks=15, existing_cache_file_identities_reused=14,
        separate_private_databases=2, current_ui_support_frozen=6,
        current_host_source_closure_matches_candidate=True,
        selected_sdk_includes_current_great_work_guard=True,
        latest_private_pair_matches_current_selected_sources=True,
        default_prepared_runtime_unchanged=True, new_game_only=True,
        save_loading_launcher_disabled=True, historical_native_saves_preserved=True,
        new_component_tests_passed=20, applicable_legacy_tests_passed=73,
        older_sdk_parent_test_rejects_current_delta=True, selected_sdk_actual_gate_passed=True,
        host_or_sdk_executed=False, host_sdk_execution_verified=False,
        initialization_and_normal_close_verified=False, city_founding_verified=False,
        turn_progress_verified=False, native_restore_verified=False,
        retail_save_restore_verified=False, prior_bundle_save_migration_performed=False,
        new_current_host_included=True, default_promoted=False,
        original_ui_3d_campaign_accepted=False, multicore_performance_accepted=False,
        execution_boundary='Second human physical Escape stop remains in force until direct human resumption.',
        full_engine_goal_complete=False)
    data['latest_host_sdk_preparation_stage'] = pair
    data['native_restore_pair_preparation_stage'] = pair.copy()
    data['status'] = 'CURRENT_RESTORE_CONTRACT_PAIR_PREPARED_NATIVE_EXECUTION_PENDING'
    for name in ('prepared_runtime_matches_current_linked_candidate',
                 'prepared_runtime_matches_latest_source',
                 'latest_private_prepared_pair_matches_current_host_and_selected_sdk_sources'):
        data[name] = True
    data['native_restore_contract_stage']['prepared_runtime_updated'] = True
    data['native_restore_contract_stage']['new_host_executed'] = False
    data['full_engine_goal_complete'] = False
    data['current_goal_turn_classification'] = 'progress'
    header = '\n\n## Current restore-contract Host and SDK private pair preparation\n'
    old_text = document.read_text(encoding='utf-8')
    assert header not in old_text
    text = header + (
        '\nThe linked e639 restore-contract Host (2212f0e5...) is now paired with the existing '
        '430f3122... Great Work SDK in private run ' + result['run_id'] + '. Both actual input gates '
        'passed without native execution. All 24 runtime inputs and 87 protected inputs were '
        'rehashed; 15 immutable cache hardlinks include 14 existing identities and one new Host '
        'cache payload. The two writable databases have private identities; six UI tools are frozen.\n'
        '\nThe new gate component suite passed 20 tests. Existing regression tests passed 73 '
        'checks; one retained test still expects the older 60984 SDK and correctly rejects the '
        'current CvUnit delta. The selected 430f SDK was independently validated successfully. '
        'The original failing receipt is preserved rather than relabelled as a passing suite.\n'
        '\nThis candidate remains new-game-only, with its save-loading launcher disabled. '
        'The preceding b9 trial and its native saves, the default release, original game, mods, '
        'settings and saves are retained. No Host/SDK/UI was started. The second physical Escape '
        'hold remains in force. City founding, turns, actual SDK restore/reopen, retail saves, '
        'original UI/3D/full campaign and measured multicore acceptance remain unverified.\n')
    replacement = (json.dumps(data, indent=2, ensure_ascii=False) + '\n').encode('utf-8')
    document_bytes = (old_text + text).encode('utf-8')
    for change in changes:
        base.checked(change['before'])
    progress.write_bytes(replacement)
    document.write_bytes(document_bytes)
    for change in changes:
        change['after'] = base.artifact(Path(change['before']['path']))
    publication = dict(schema='zerosis.native_restore.prepared_pair_publication.v1',
        status='PASS_CURRENT_RESTORE_PAIR_PREPARED_AND_PUBLISHED_WITHOUT_EXECUTION',
        pre_edit=base.artifact(STAGE / 'publication_pre_edit.json'),
        audit=base.artifact(STAGE / 'audit.json'), proofs=proofs, changed_metadata=changes,
        current_pair_matches_current_selected_sources=True, host_or_sdk_executed=False,
        second_human_escape_stop_respected=True, default_promoted=False, full_engine_goal_complete=False)
    write_new(STAGE / 'publication.json', publication)
    for row in started['protected_inputs']:
        base.checked(row)
    for root, patterns in (
        (PROJECT, ('host_runtime_inputs_test_*', '_retained_host_inputs_*', '_restore_host_inputs_*')),
        (PROJECT / 'Tests', ('sdk_input_*',)),
        (Path(result['cache_created'][0]).parent, ('.publish-*',))):
        for pattern in patterns:
            assert not list(root.glob(pattern)), 'Inspect any remaining test/cache temporary before cleanup'
    paths = []
    for root in (runtime, PROJECT / 'evidence/interactive_game' / result['run_id'], STAGE):
        paths.extend(path for path in root.rglob('*') if path.is_file())
    paths.extend(Path(path) for path in result['cache_created'])
    unique = {}
    for path in paths:
        identity = file_id(path)
        unique.setdefault(identity, path)
    owned = [path for identity, path in unique.items() if identity not in existing_ids]
    allocated = sum(allocation(path) for path in owned)
    storage = dict(schema='zerosis.native_restore.pair_scoped_storage.v1',
        scope='New private runtime, evidence, pair preparation and exact new Host cache; existing cache IDs excluded.',
        metric='FileStandardInfo.AllocationSize', path_count=len(paths), unique_file_ids=len(unique),
        hardlink_aliases_deduplicated=len(paths)-len(unique),
        existing_input_file_ids_excluded=len(existing_ids), owned_unique_file_ids=len(owned),
        owned_file_data_allocated_bytes=allocated,
        source_test_files_and_this_storage_receipt_excluded=True,
        whole_project_net_measured=False, reproducible_temporary_files_remaining=0,
        files_deleted_this_step=0, retained_private_trial_and_recovery_artifacts_preserved=True)
    write_new(STAGE / 'storage.json', storage)
    print(json.dumps(dict(status=publication['status'], run_id=result['run_id'],
        new_tests_passed=20, legacy_tests_passed=73, legacy_parent_rejection=1,
        allocated_owned_scope_bytes=allocated, host_or_sdk_executed=False)))


if __name__ == '__main__':
    main()
