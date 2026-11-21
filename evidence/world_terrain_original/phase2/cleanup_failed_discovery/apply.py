"""Apply the reviewed exact failed-discovery leaf plan after a pinned success."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys

sys.dont_write_bytecode = True
STAGE = Path(__file__).absolute().parent
spec = importlib.util.spec_from_file_location('failed_discovery_plan', STAGE / 'plan.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)
PLAN_SHA = '95a1ec1029322d160cf6df631bf665615869d60aac5a11814842457ee6ac9740'
SUCCESS_ID = '20261115T034310Z_77ed882144d1'
REPORT_SHA = 'f0d5b91291d158e1c256e7753497de1955dd55fbafe6da93545878fb8156346f'
ATTEST_SHA = '13f0b2bbe1181efcdd76db2a844e479bb8cf050d4b42af625bdca069a6c246fa'


def main():
    plan_path = STAGE / 'plan.json'
    assert audit.storage.digest(plan_path) == PLAN_SHA
    assert not (STAGE / 'apply_started.json').exists(), 'A partially applied plan cannot be replayed'
    plan = json.loads(plan_path.read_text('utf8'))
    root = Path(plan['root'])
    assert root == audit.ROOT and root.resolve() == root
    assert root.parent == audit.PROJECT / 'Build/UiWindowHost'
    assert root.name == '20261115T033820Z_3377b24b6421'
    assert plan['status'] == 'PLAN_ONLY_AWAIT_SUCCESS_AND_ROOT_APPLY_INSTRUCTION'
    assert len(plan['files']) == 11 and len(plan['directories']) == 8
    assert all(Path(row['path']).is_relative_to(root) for row in plan['files'] + plan['directories'])

    report_path = audit.PROJECT / 'evidence/ui_window_host' / SUCCESS_ID / 'build_result.json'
    attest_path = audit.PHASE / 'pair_preparation' / SUCCESS_ID / 'independent_attestation.json'
    assert audit.storage.digest(report_path) == REPORT_SHA and audit.storage.digest(attest_path) == ATTEST_SHA
    report = json.loads(report_path.read_text('utf8'))
    attest = json.loads(attest_path.read_text('utf8'))
    assert report['status'] == 'UI_WINDOW_HOST_CANDIDATE_BUILT' and report['build_id'] == SUCCESS_ID
    assert attest['status'] == 'PASS_INDEPENDENT_CURRENT_MENU_SUITE_HOST_BYTES_AND_INPUTS'
    assert attest['host_or_sdk_or_dll_or_window_execution'] is False
    assert attest['full_native_or_original_ui_acceptance'] is False
    assert attest['build_result']['path'] == str(report_path) and attest['build_result']['sha256'] == REPORT_SHA
    assert attest['image']['sha256'] == report['executable']['sha256']
    assert not any(Path(row['path']).is_relative_to(root) for row in audit.storage.path_rows(report))
    success_preserved = [audit.snapshot(path) for path in (report_path, attest_path, Path(report['executable']['path']))]
    assert success_preserved[2]['sha256'] == report['executable']['sha256']

    actual_files, actual_directories = [], [audit.directory(root)]
    for parent, children, names in os.walk(root, followlinks=False):
        actual_directories += [audit.directory(Path(parent) / name) for name in children]
        actual_files += [audit.snapshot(Path(parent) / name) for name in names]
    assert sorted(actual_files, key=lambda row: row['path']) == plan['files']
    assert sorted(actual_directories, key=lambda row: row['path']) == sorted(plan['directories'], key=lambda row: row['path'])
    for row in plan['preserved']:
        assert audit.snapshot(row['path']) == row, row['path']
    assert audit.snapshot(plan['reverse_reference_review']['path']) == plan['reverse_reference_review']
    assert all(row['links'] == 1 and not row['file_attributes'] & 0x401 for row in actual_files)
    assert sum(row['allocated_bytes'] for row in actual_files) == plan['expected_unique_allocated_release']
    free_before = shutil.disk_usage(audit.PROJECT).free
    audit.write_new(STAGE / 'apply_started.json', dict(
        utc=datetime.now(timezone.utc).isoformat(), plan_sha256=PLAN_SHA,
        successful_report=success_preserved[0], independent_attestation=success_preserved[1],
        successful_image=success_preserved[2], explicit_root_apply_instruction=True,
        delete_files=len(actual_files), delete_directories=len(actual_directories),
        volume_free_bytes_before=free_before))
    deleted, removed_directories = [], []
    try:
        for row in plan['files']:
            path = Path(row['path'])
            assert audit.snapshot(path) == row
            path.unlink()
            assert not os.path.lexists(path)
            deleted.append(row['path'])
        for row in sorted(plan['directories'], key=lambda item: len(Path(item['path']).parts), reverse=True):
            path = Path(row['path'])
            # Child deletion changes directory mtime; its identity and attributes must remain fixed.
            now = audit.directory(path)
            assert now['file_identity'] == row['file_identity'] and now['file_attributes'] == row['file_attributes']
            assert not any(path.iterdir())
            path.rmdir()
            removed_directories.append(row['path'])
        assert not os.path.lexists(root)
        for row in plan['preserved'] + success_preserved:
            assert audit.snapshot(row['path']) == row, row['path']
        free_after = shutil.disk_usage(audit.PROJECT).free
        result = dict(schema='zerosis.original_fog.phase2.failed_discovery_cleanup_result.v1',
            status='PASS_EXACT_FAILED_DISCOVERY_TREE_REMOVED', utc=datetime.now(timezone.utc).isoformat(),
            plan_sha256=PLAN_SHA, successful_report=success_preserved[0],
            independent_attestation=success_preserved[1], successful_image=success_preserved[2],
            files_deleted=len(deleted), directories_deleted=len(removed_directories),
            root_absent=True, deleted_file_list_in_plan=True,
            logical_bytes_removed=plan['logical_bytes'], last_links_deleted=len(deleted),
            summed_predelete_unique_allocation_bytes=plan['expected_unique_allocated_release'],
            volume_free_bytes_before=free_before, volume_free_bytes_after=free_after,
            observed_volume_free_delta_bytes=free_after-free_before,
            volume_delta_attributed_to_this_cleanup=False,
            allocation_note='Every candidate had one link, was revalidated with FILE_STANDARD_INFO AllocationSize, and its final path is now absent. Volume free-space change is observational because other build cleanup may run concurrently.',
            preserved_files=len(plan['preserved'])+len(success_preserved),
            preserved_sha_bytes_ids_mtimes_attributes_links_and_allocations_unchanged=True,
            failure_logs_fix_backups_current_hosts_sdk_runtimes_and_saves_preserved=True,
            source_tests_build_helpers_default_mods_original_game_or_saves_deleted=False,
            native_host_gamecore_clr_hwnd_gpu_audio_or_game_executed=False)
        audit.write_new(STAGE / 'result.json', result)
        print(json.dumps({key: result[key] for key in ('status', 'files_deleted', 'directories_deleted',
            'logical_bytes_removed', 'summed_predelete_unique_allocation_bytes', 'preserved_files')}))
    except BaseException as error:
        audit.write_new(STAGE / 'partial_failure.json', dict(status='PARTIAL_FAILURE_DO_NOT_REPLAY',
            error_type=type(error).__name__, error=str(error), deleted_files=deleted,
            removed_directories=removed_directories, plan_sha256=PLAN_SHA))
        raise


if __name__ == '__main__':
    main()
