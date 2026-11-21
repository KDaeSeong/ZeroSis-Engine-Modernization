"""Seal this source-only change without promoting or executing a native Host."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json

STAGE = Path(__file__).absolute().parent
PROJECT = STAGE.parents[2]
PROGRESS = PROJECT / 'evidence/save_menu/20261013_original_screen/current_progress.json'
REFERENCES = {
    'native': 'evidence/save_overwrite/source_contract/native_transaction/20261016T120946Z_b5b44dda6e0e/result.json',
    'native_conformance': 'evidence/save_overwrite/source_contract/native_transaction/20261016T120946Z_b5b44dda6e0e/conformance.json',
    'native_cleanup': 'evidence/save_overwrite/source_contract/native_transaction/20261016T120946Z_b5b44dda6e0e/cleanup.json',
    'handoff': 'evidence/save_overwrite/native_handoff/20261016T120204Z_d36ac97cdbfc/result.json',
    'handoff_cleanup': 'evidence/save_overwrite/native_handoff/20261016T120204Z_d36ac97cdbfc/cleanup.json',
    'delete_handoff': 'evidence/save_delete/native_handoff/20261016T120203Z_5d16bb58245e/result.json',
    'delete_handoff_cleanup': 'evidence/save_delete/native_handoff/20261016T120203Z_5d16bb58245e/cleanup.json',
    'lua': 'evidence/save_overwrite/source_contract/lua/20261016T120552Z_456052170a64.json',
    'frontend': 'evidence/save_overwrite/source_contract/frontend/20261016T120258Z_7a1dc8c7a247/result.json',
    'renderer': 'evidence/save_overwrite/source_contract/renderer_regression/final.json',
    'syntax': 'evidence/save_overwrite/source_contract/host_syntax/20261016T120959Z_fcdb4d09a200/result.json',
}
SOURCES = [
    'Source/Host/NativeSaveCatalog.h', 'Source/Host/UiSaveMenuContract.h',
    'Source/Host/UiPopupContext.h', 'Source/Host/InteractiveGameSession.h',
    'Source/Host/UiScene.lua', 'Source/Presentation/UiPresentationInput.lua', 'tools/ui_pixel_scene.py',
    'Tests/native_save_catalog.cpp', 'Tests/native_save_catalog_check.py',
    'Tests/owned_save_replace_transaction_fixture.h',
    'Tests/owned_save_overwrite_handoff.py', 'Tests/owned_save_overwrite_handoff.cpp.in',
    'Tests/owned_save_overwrite_scene.py', 'Tests/owned_save_overwrite_check.py',
    'Tests/owned_save_overwrite_frontend.py', 'Tests/owned_save_delete_scene.py',
    'Tests/save_menu_scene.py', 'Tests/load_menu_scene.py', 'Tests/load_menu_host_syntax.py',
]


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def seal(path):
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    return {'path': str(path), 'bytes': path.stat().st_size, 'sha256': digest}


def check_current_references(node):
    count = 0
    if isinstance(node, dict):
        if isinstance(node.get('path'), str) and isinstance(node.get('sha256'), str):
            path = Path(node['path'])
            if any(path.is_relative_to(PROJECT / name) for name in ('Source', 'Tests', 'tools')):
                require(seal(path)['sha256'] == node['sha256'], 'A proven source changed: ' + str(path))
                count += 1
        for value in node.values():
            count += check_current_references(value)
    elif isinstance(node, list):
        for value in node:
            count += check_current_references(value)
    return count


def main():
    destination = STAGE / 'conformance.json'
    require(not destination.exists(), 'Finalized source stage must not be replayed')
    scope = json.loads((STAGE / 'scope.json').read_text(encoding='utf-8'))
    protected = json.loads((STAGE / 'baseline_protection.json').read_text(encoding='utf-8'))['files']
    for row in protected:
        path = Path(row['path'])
        current, info = seal(path), path.stat()
        require(all(current[key] == row[key] for key in ('bytes', 'sha256')) and
                (info.st_dev, info.st_ino) == (row['device'], row['file_id']), 'Protected baseline changed: ' + str(path))
    for row in scope['source_before']:
        require(seal(Path(row['backup']))['sha256'] == row['sha256'], 'Changed-file backup differs')
    require(seal(STAGE / 'source_before/current_progress.json')['sha256'] ==
            '98ae88dbae64597b6e6214aa6b87900568d808e3d19aaedd2bc9dbb2b259a5eb', 'Historical progress snapshot differs')
    proofs = {name: json.loads((PROJECT / relative).read_text(encoding='utf-8')) for name, relative in REFERENCES.items()}
    native, handoff, deletion = (proofs[name] for name in ('native', 'handoff', 'delete_handoff'))
    require(native['status'] == 'NATIVE_SAVE_CATALOG_BOUNDARIES_PASS' and native['source_inputs_unchanged'] and
            native['native_checks'] == 756 and native['replacement_checks'] == 438 and
            native['process_interruption_recovery_cases'] == 12 and
            not native['replacement_atomic_or_power_loss_durability_claimed'], 'Native replacement proof differs')
    for name, expected in (('handoff', 464), ('delete_handoff', 630)):
        row = proofs[name]
        require(row['status'] == 'PASS' and row['total_checks'] == expected and
                not row['actual_host_gamecore_or_hwnd_executed'] and not row['actual_save_files_accessed'] and
                not row['retail_files_accessed'], 'Extracted handoff proof differs: ' + name)
    for row in [*native['runs'], *handoff['runs'], *deletion['runs']]:
        require(row['status'] == 'PASS' and row['compiler_exit_code'] == 0 and
                row['compiler_and_linker_warnings'] == 0, 'Native component compile/run failed or warned')
    lua = proofs['lua']['result']
    require(proofs['lua']['unit_tests'] == 6 and len(lua['cases']) == 6 and lua['checks'] == 1558 and
            lua['original_sources_unchanged'] and lua['temporary_styles_removed'] and
            not lua['retail_user_state_accessed'] and not lua['native_host_or_gamecore_executed'], 'Lua callback proof differs')
    require(lua['source_sha256']['scene'] == seal(PROJECT / SOURCES[4])['sha256'] and
            lua['source_sha256']['input'] == seal(PROJECT / SOURCES[5])['sha256'], 'Lua source seal differs')
    frontend, renderer, syntax = (proofs[name] for name in ('frontend', 'renderer', 'syntax'))
    require(frontend['status'] == 'PASS_ORIGINAL_OVERWRITE_STATES_THROUGH_FROZEN_CPU_DRIVER_ONLY' and
            len(frontend['states']) == 7 and frontend['scene_source_sha256']['scene'] == lua['source_sha256']['scene'] and
            frontend['scene_source_sha256']['input'] == lua['source_sha256']['input'] and
            frontend['support_sources']['ui_pixel_scene.py']['sha256'] == seal(PROJECT / SOURCES[6])['sha256'] and
            frontend['cleanup']['status'] == 'COMPLETE' and frontend['cleanup']['directory_absent'] and
            not Path(frontend['cleanup']['directory']).exists(), 'CPU frontend or cleanup differs')
    require(renderer['status'] == 'PASS' and renderer['test_count'] == 3 and renderer['sources_unchanged'], 'Renderer regression failed')
    require(syntax['status'] == 'PASS' and syntax['compiler_exit_code'] == 0 and not syntax['warnings'] and
            syntax['consumed_project_input_count'] == 210 and not syntax['linked'] and
            not syntax['gamecore_or_host_executed'] and not syntax['hwnd_created'], 'Actual Host C++ syntax proof failed')
    syntax_paths = {str(Path(row['path'])).casefold(): row for row in syntax['consumed_project_inputs'].values()}
    for relative in SOURCES[:4]:
        row = syntax_paths.get(str(PROJECT / relative).casefold())
        require(row is not None and row['sha256'] == seal(PROJECT / relative)['sha256'], 'Current C++ source is not in syntax proof')
    for name in ('native_cleanup', 'handoff_cleanup', 'delete_handoff_cleanup'):
        require(proofs[name]['status'] == 'COMPLETE', 'Owned cleanup incomplete: ' + name)
    for name in ('handoff_cleanup', 'delete_handoff_cleanup'):
        require(not Path(proofs[name]['root']).exists(), 'Owned handoff scratch remains')
    checked = sum(check_current_references(proofs[name]) for name in ('native', 'handoff', 'delete_handoff', 'frontend', 'renderer', 'syntax'))
    report = {
        'schema': 'zerosis.owned_save_overwrite.source_conformance.v1', 'utc': datetime.now(timezone.utc).isoformat(),
        'status': 'PASS_SOURCE_AND_COMPONENT_ONLY', 'requirements': scope['requirements'],
        'sources': [seal(PROJECT / relative) for relative in SOURCES],
        'proofs': {name: seal(PROJECT / relative) for name, relative in REFERENCES.items()},
        'protected_baselines_reverified': len(protected), 'current_source_references_reverified': checked,
        'changed_file_backups': seal(STAGE / 'scope.json'),
        'historical_progress_snapshot': seal(STAGE / 'source_before/current_progress.json'),
        'verification': {'native_catalog_checks': 756, 'new_native_replacement_checks': 438,
                         'actual_owned_process_interruption_restart_cases': 12,
                         'new_mock_handoff_checks': 464, 'existing_mock_deletion_handoff_checks': 630,
                         'lua_unit_tests': 6, 'original_lua_cases': 6, 'original_lua_checks': 1558,
                         'cpu_frontend_states': 7, 'existing_renderer_tests': 3,
                         'current_host_cpp_syntax_inputs': 210, 'compiler_warnings': 0,
                         'original_save_ui_lua_xml_unchanged': True, 'archive_schema_unchanged': True,
                         'retail_mod_test_hold_active': True, 'retail_state_accessed': False,
                         'host_gamecore_or_hwnd_executed': False, 'current_source_linked_or_prepared': False,
                         'default_promoted': False, 'full_engine_goal_complete': False},
        'coverage_mapping': lua['coverage_mapping'],
        'independent_review': {'finding': 'Exclusive stage reopen failure left an orphan but raised ordinary failure.',
                               'resolution': 'Track stageMayRemain; return recoveryRequired and preserved stage path.',
                               'actual_shared_reader_reproduction_passed': True,
                               'reviewed_production_sha256': seal(PROJECT / SOURCES[0])['sha256']},
        'cleanup': {'native': seal(PROJECT / REFERENCES['native_cleanup']),
                    'frontend': frontend['cleanup'],
                    'final_handoff_receipts': [seal(PROJECT / REFERENCES[name]) for name in ('handoff_cleanup', 'delete_handoff_cleanup')],
                    'root_renderer_fixture_limit': 'Existing small fixture helper verifies bounds/reparse points and removes its directories; it emits no per-file byte/hash deletion ledger. These deletions are excluded from component deletion totals.'},
        'limits': ['Private journal format v1 is new; the native game archive schema is unchanged.',
                   'Two no-replace renames are not an atomic replacement. Power-loss ordering is unverified.',
                   'C++ handoff SDK, Lua, parent/child modal and storage services are mocked.',
                   'CPU renderer and headless original Lua are not actual Host/SDK/window/IME acceptance.',
                   'B6/R6 remain preserved and no longer match the current source; current Lua is not embedded or linked.',
                   'Original full UI/3D/campaign, retail Civ5Save/mod compatibility and multicore performance remain incomplete.']}
    destination.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    progress = json.loads(PROGRESS.read_text(encoding='utf-8'))
    progress.update(status='OVERWRITE_SOURCE_COMPONENTS_PASS_LINK_AND_NATIVE_ACCEPTANCE_PENDING',
                    latest_source_matches_linked_candidate=False,
                    latest_cpp_source_matches_actual_host_syntax_proof=True,
                    latest_source_matches_integrated_syntax_proof=False,
                    latest_integrated_syntax_proof=seal(PROJECT / REFERENCES['syntax']),
                    syntax_proof_uses_preserved_generated_ui_header=True,
                    prepared_runtime_matches_latest_source=False, full_engine_goal_complete=False)
    progress['current_prepared_runtime']['current_source_candidate'] = False
    progress['owned_save_overwrite_source_stage'] = {
        'status': report['status'], 'conformance': seal(destination), 'verification': report['verification'],
        'preserved_host': scope['baseline_host'], 'preserved_prepared_runtime': scope['baseline_prepared_runtime'],
        'remaining': ['Embed/link current Lua and C++ into the next candidate, reusing frozen inputs.',
                      'After explicit human mod-test end, verify actual original-menu save/overwrite/cancel/restart/fresh SDK restore and IME.',
                      'Complete original full UI/3D/campaign, retail save/mod compatibility and multicore acceptance.']}
    PROGRESS.write_text(json.dumps(progress, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps({'status': report['status'], 'conformance': seal(destination),
                      'progress': seal(PROGRESS), 'protected_files_unchanged': len(protected)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
