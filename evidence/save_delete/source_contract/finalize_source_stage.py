"""Record scoped source proof and current-source drift without running a game."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import stat

PROJECT = Path(__file__).absolute().parents[3]
STAGE = PROJECT / 'evidence/save_delete/source_contract'
PROGRESS = PROJECT / 'evidence/save_menu/20261013_original_screen/current_progress.json'


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def artifact(path):
    data = path.read_bytes()
    return {'path': str(path), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf8')


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def tidy_empty_preflight():
    receipt = STAGE / 'empty_preflight_cleanup.json'
    require(not os.path.lexists(receipt), 'Refusing to overwrite cleanup receipt')
    target = STAGE / 'frontend/20261015T214533Z_f6cfbf8f34b1'
    absolute = target.resolve(strict=True)
    require(absolute == target and absolute.parent == (STAGE / 'frontend').resolve(strict=True),
            'Empty preflight directory escaped the exact source-stage path')
    for path in (absolute, *absolute.parents):
        info = path.lstat()
        require(not stat.S_ISLNK(info.st_mode) and not getattr(info, 'st_file_attributes', 0) & 0x400,
                'Empty preflight path contains a reparse point')
    before = target.stat()
    require(not list(target.iterdir()), 'Preflight directory is no longer empty')
    row = {'path': str(target), 'file_identity': [before.st_dev, before.st_ino],
           'files_removed': 0, 'logical_file_bytes_removed': 0,
           'status': 'INVENTORIED_EMPTY_DIRECTORY'}
    write(receipt, row)
    now = target.stat()
    require([now.st_dev, now.st_ino] == row['file_identity'] and not list(target.iterdir()),
            'Empty preflight directory changed after inventory')
    target.rmdir()
    row.update(status='REMOVED_EMPTY_DIRECTORY', absent=not os.path.lexists(target))
    write(receipt, row)
    print(json.dumps(row))


def finalize(storage_path):
    conformance_path = STAGE / 'conformance.json'
    require(not conformance_path.exists(), 'Refusing to overwrite final conformance')
    scope = read(STAGE / 'scope.json')
    changes, unchanged = [], []
    for row in scope['source_before']:
        require(artifact(Path(row['path'])) == {key: row[key] for key in ('path', 'bytes', 'sha256')},
                'Source backup seal changed: ' + row['path'])
        if row['source'] == str(PROGRESS):
            continue
        current = artifact(Path(row['source']))
        (unchanged if current['sha256'] == row['sha256'] else changes).append({
            'before': {key: row[key] for key in ('path', 'bytes', 'sha256')}, 'current': current})
    previous_progress = next(row for row in scope['source_before'] if row['source'] == str(PROGRESS))
    require(artifact(PROGRESS)['sha256'] == previous_progress['sha256'], 'Progress changed before final publication')

    paths = {
        'native_catalog': PROJECT / 'evidence/native_save_catalog/20261015T212100Z_739bb586f19b/result.json',
        'native_catalog_cleanup': PROJECT / 'evidence/native_save_catalog/20261015T212100Z_739bb586f19b/cleanup.json',
        'extracted_handoff': PROJECT / 'evidence/save_delete/native_handoff/20261015T212934Z_a59da6f5ea51/result.json',
        'extracted_handoff_cleanup': PROJECT / 'evidence/save_delete/native_handoff/20261015T212934Z_a59da6f5ea51/cleanup.json',
        'host_cpp_syntax': STAGE / 'host_syntax/20261015T213449Z_895375fc6f9e/result.json',
        'lua_tests': STAGE / 'lua_tests.json',
        'asset_tests': STAGE / 'ui_asset_tests.json',
        'frontend': STAGE / 'frontend/20261015T214730Z_ecd660a73c8b/result.json',
        'empty_preflight_cleanup': STAGE / 'empty_preflight_cleanup.json',
        'storage_before': PROJECT / 'evidence/storage/20261015T210541Z.json',
        'storage_after': storage_path,
    }
    records = {key: read(path) for key, path in paths.items()}
    native, handoff = records['native_catalog'], records['extracted_handoff']
    require(native['status'] == 'NATIVE_SAVE_CATALOG_BOUNDARIES_PASS' and native['native_checks'] == 756 and
            native['source_inputs_unchanged'] is True and all(run['status'] == 'PASS' and run['checks'] == 378 and
            run['native_exit_code'] == 0 and not run['compiler_and_linker_warnings'] and
            run['gamecore_loaded'] is False and run['retail_saves_touched'] is False for run in native['runs']),
            'Native catalog proof failed')
    require(handoff['status'] == 'PASS' and handoff['total_checks'] == 630 and
            all(run['status'] == 'PASS' and run['checks'] == 315 and not run['compiler_and_linker_warnings']
                for run in handoff['runs']), 'Extracted handoff proof failed')
    for record in (native, handoff):
        for source in record['sources']:
            require(artifact(Path(source['path'])) == {key: source[key] for key in ('path', 'bytes', 'sha256')},
                    'Current native source drifted from its execution proof')
    syntax = records['host_cpp_syntax']
    require(syntax['status'] == 'PASS' and syntax['compiler_exit_code'] == 0 and not syntax['warnings'] and
            syntax['consumed_project_input_count'] == 210 and syntax['gamecore_or_host_executed'] is False and
            syntax['hwnd_created'] is False and syntax['linked'] is False, 'Host syntax proof failed')
    for source in syntax['consumed_project_inputs'].values():
        require(artifact(Path(source['path'])) == source, 'Current C++ input drifted from its syntax proof')
    lua, frontend = records['lua_tests'], records['frontend']
    require(lua['exit_code'] == 0 and lua['summary']['unit_tests'] == 6 and lua['summary']['checks'] == 5031 and
            lua['summary']['source_sha256'] == artifact(PROJECT / 'Source/Host/UiScene.lua')['sha256'],
            'Lua regression proof failed or drifted')
    require(records['asset_tests']['returncode'] == 0, 'UI asset source proof failed')
    require(frontend['status'] == 'PASS_ORIGINAL_DELETE_STATES_THROUGH_FROZEN_CPU_DRIVER_ONLY' and
            len(frontend['states']) == 14 and len(frontend['python_renderer_children']) == 14 and
            frontend['cleanup']['status'] == 'COMPLETE' and frontend['cleanup']['directory_absent'] is True,
            'Frontend proof failed')
    for source in frontend['support_sources'].values():
        require(artifact(Path(source['path'])) == source, 'Current Python frontend drifted from its proof')
    frontend_cleanups = []
    for path in sorted((STAGE / 'frontend').glob('*/result.json')):
        result = read(path)
        cleanup = result['cleanup']
        require(cleanup['status'] == 'COMPLETE' and cleanup['directory_absent'] is True and
                not os.path.lexists(cleanup['directory']), 'Frontend temporary directory remains')
        frontend_cleanups.append({'result': artifact(path), 'status': result['status'], 'cleanup': cleanup})
    require(not list((PROJECT / 'Build').glob('pull-down-compositor-load-driver-owned-delete-*')),
            'An owned frontend temporary directory remains')
    catalog_cleanup, handoff_cleanup = records['native_catalog_cleanup'], records['extracted_handoff_cleanup']
    require(catalog_cleanup['retail_saves_touched'] is False and
            handoff_cleanup['retail_or_user_files_touched'] is False and handoff_cleanup['root_removed'] is True,
            'Native fixture cleanup scope or completion changed')
    for row in (*catalog_cleanup['deleted'], *handoff_cleanup['deleted']):
        require(not os.path.lexists(row['path']), 'A retired native fixture still exists')

    preserved = {}
    for relative, expected in {
        'Play/EarlyAccess/release.json': '5587028d64ff6206780837ee7112f0c34d62676fb0627ee099d4eb03aef9c2c5',
        'tools/Start-Engine.ps1': 'c487ce6c89e374bb625961ce81cf6cbae210608c578542658038e6cb06173d7c',
        'Source/Host/NativeSaveArchive.h': 'd1ce478b093adb53acb280ff8d286ffa1d791f28783d888d9f22738e69a8e5dc',
        'evidence/ui_window_host/20261015T134352Z_8bd70cf290e9/build_result.json':
            'e11d807ae9bf6aa43120a6351b2d0a845ee2d671c601d76ec56a365fa58431c2',
        'Build/UiWindowHost/20261015T134352Z_8bd70cf290e9/final/ZeroSisHost_x64.exe':
            '3e83d2b773d689a8d86674318bf7f76963fc236debbd7f0086046f1d3307766e',
    }.items():
        preserved[relative] = artifact(PROJECT / relative)
        require(preserved[relative]['sha256'] == expected, 'Protected current/recovery artifact changed: ' + relative)
    before, after = records['storage_before'], records['storage_after']
    require(after['status'] == 'COMPLETE_METADATA_AUDIT' and not after['errors'] and not after['skipped'] and
            after['root'] == str(PROJECT), 'Final storage audit incomplete or outside project')
    storage = {'before_unique_GetCompressedFileSizeW_bytes': before['unique_allocated_bytes'],
               'after_unique_GetCompressedFileSizeW_bytes': after['unique_allocated_bytes'],
               'net_unique_increase_bytes': after['unique_allocated_bytes'] - before['unique_allocated_bytes'],
               'after_GiB': after['unique_allocated_bytes'] / 1024**3,
               'frontend_generated_files_removed': sum(row['cleanup']['file_count'] for row in frontend_cleanups),
               'frontend_generated_logical_bytes_removed': sum(row['cleanup']['logical_bytes_removed'] for row in frontend_cleanups),
               'frontend_physical_bytes_reclaimed_measured': False,
               'native_generated_files_removed': len(catalog_cleanup['deleted']) + len(handoff_cleanup['deleted']),
               'native_generated_logical_bytes_removed': catalog_cleanup['logical_before'] - catalog_cleanup['logical_after'] + handoff_cleanup['logical_bytes_removed'],
               'native_generated_allocated_bytes_removed': catalog_cleanup['allocated_before'] - catalog_cleanup['allocated_after'] + handoff_cleanup['allocated_bytes_removed'],
               'full_project_copies_created': 0,
               'limits': 'Unique NTFS identities and GetCompressedFileSizeW; not volume free space or directory overhead. Finalizer, conformance and progress publication finish after the audit; their small metadata changes are outside that snapshot.'}
    proofs = {key: artifact(path) for key, path in paths.items()}
    new_sources = [artifact(PROJECT / relative) for relative in (
        'Tests/owned_save_delete_scene.py', 'Tests/owned_save_delete_check.py',
        'Tests/owned_save_delete_handoff.py', 'Tests/owned_save_delete_handoff.cpp.in',
        'Tests/owned_save_delete_frontend.py')]
    report = {'schema': 'zerosis.owned_save_delete_source_conformance.v1',
              'utc': datetime.now(timezone.utc).isoformat(),
              'status': 'PASS_SOURCE_NATIVE_FIXTURE_LUA_AND_FROZEN_CPU_FRONTEND_ONLY',
              'scope': artifact(STAGE / 'scope.json'), 'finalizer': artifact(Path(__file__).absolute()),
              'previous_progress_backup': artifact(Path(previous_progress['path'])),
              'changed_sources': changes, 'unchanged_preserved_inputs': unchanged, 'new_sources': new_sources,
              'proofs': proofs, 'frontend_attempts_and_cleanup': frontend_cleanups,
              'protected_artifacts_unchanged': preserved, 'storage': storage,
              'verification': {'native_owned_archive_checks_O2_Od': 756,
                  'extracted_handoff_checks_O2_Od': 630, 'lua_unit_tests': 6,
                  'original_lua_fixture_checks': 5031, 'actual_frozen_cpu_renderer_states': 14,
                  'ui_source_asset_tests': 10, 'actual_cpp_syntax_consumed_inputs': 210,
                  'actual_cpp_syntax_warnings': 0, 'original_ui_lua_xml_unchanged': True,
                  'archive_schema_or_mod_identifiers_changed': False,
                  'current_delete_lua_embedded_in_linked_host': False,
                  'current_source_compiled_and_linked': False,
                  'host_gamecore_hwnd_executed': False, 'retail_mods_saves_settings_or_processes_accessed': False,
                  'native_host_delete_verified': False, 'default_release_promoted': False,
                  'retail_mod_test_hold_active': True, 'full_engine_goal_complete': False},
              'implementation': ['Original Yes/No/Escape is connected to a one-use deletion grant and exact selected owned path.',
                  'Native deletion revalidates the listed archive and exact bundle through the same exclusive read/delete handle.',
                  'Deleted rows disappear; original pooled controls and save/load close handoff remain valid.',
                  'Save confirmation excludes background scroll input and preserves nested original style decorations.'],
              'limits': ['Lua deletion service and SDK are fixtures; native catalog uses only own generated archives.',
                  'Extracted C++ handoff substitutes SDK/Lua/OS boundaries and is not actual Host execution.',
                  'Host syntax uses the preserved B5 generated UI header and does not embed the new deletion Lua.',
                  'Frozen CPU renderer uses an explicit small component catalog and rules database, not full Host preparation.',
                  'Actual Lua call failure locks the native UI; fixture retry is not live recovery proof.'],
              'next_steps': ['Regenerate the coherent UI catalog/header and compile/link one current x64 candidate using retained inputs.',
                  'Prepare a matching private candidate without changing EA0.6 or accessing retail settings.',
                  'After explicit human test-end release, verify actual menu confirmation/cancel/delete/refresh, named save and fresh SDK restore.',
                  'Complete original UI, gameplay/campaign, retail save/mod compatibility, physical IME and measured multicore/stability gates.']}
    write(conformance_path, report)
    progress = read(PROGRESS)
    progress.update(utc=report['utc'], status='OWNED_SAVE_DELETE_SOURCE_CHECKS_PASS_LINKED_HOST_PREDATES_DELETE',
                    prior_goal_turn_classification='progress: connected original private-save deletion, same-handle native validation, Lua confirmation and list refresh, fixed Save modal scroll/style rendering, passed scoped native/Lua/CPU proofs and cleaned own temporary files',
                    latest_source_matches_linked_candidate=False,
                    latest_cpp_source_matches_actual_host_syntax_proof=True,
                    latest_source_matches_integrated_syntax_proof=False,
                    latest_integrated_syntax_proof=proofs['host_cpp_syntax'],
                    syntax_proof_uses_preserved_generated_ui_header=True,
                    prepared_runtime_matches_latest_source=False,
                    latest_full_source_embedding_limit='Current deletion C++/Lua and Python source is ahead of preserved B5/R4. C++ syntax passed against the old generated UI header; no current deletion Lua embedding, new link, native Host/SDK/window acceptance or default promotion is claimed.')
    progress['current_prepared_runtime'].update(current_source_candidate=False,
        status='PRESERVED_B5_PREPARED_NOT_EXECUTED_SOURCE_AHEAD')
    progress['load_menu_linked_candidate_stage']['current_source_candidate'] = False
    progress['load_menu_runtime_preparation_stage']['current_source_candidate'] = False
    progress['user_mod_test_isolation'].update(
        latest_user_clarification='The user is testing a new mod in retail Civ V, not the separate x64 prototype.',
        retail_test_hold_still_active=True,
        retail_MODS_user_saves_or_game_processes_accessed_this_stage=False,
        game_Host_GameCore_HWND_or_component_windows_executed_this_stage=False,
        retail_settings_accessed_this_stage=False, original_user_settings_read_this_stage=False,
        current_stage_policy_source='NOT_NEEDED_NO_RETAIL_SETTINGS_ACCESSED')
    progress['owned_save_delete_source_stage'] = {'conformance': artifact(conformance_path),
        'verification': report['verification'], 'remaining_gates': report['next_steps']}
    progress['proofs']['owned_save_delete_source_conformance'] = artifact(conformance_path)
    progress['proofs']['owned_save_delete_storage_after'] = proofs['storage_after']
    progress['storage'].update(latest_measured_unique_GetCompressedFileSizeW_bytes=after['unique_allocated_bytes'],
                               latest_measured_utc=after['utc'], owned_save_delete_source_stage=storage)
    require(artifact(PROGRESS)['sha256'] == previous_progress['sha256'], 'Progress changed during final checks')
    write(PROGRESS, progress)
    print(json.dumps({'status': report['status'], 'conformance': artifact(conformance_path),
                      'progress': artifact(PROGRESS), 'storage': storage}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--tidy-empty-preflight', action='store_true')
    parser.add_argument('--storage', type=Path)
    args = parser.parse_args()
    if args.tidy_empty_preflight:
        tidy_empty_preflight()
    else:
        require(args.storage is not None, 'Final storage report is required')
        finalize(args.storage)
