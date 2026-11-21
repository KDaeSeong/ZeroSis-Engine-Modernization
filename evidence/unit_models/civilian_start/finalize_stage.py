"""Publish a source/asset-only result after verifying this stage's real receipts."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import os

PROJECT = Path(__file__).absolute().parents[3]
STAGE = Path(__file__).absolute().parent
PROGRESS = PROJECT / 'evidence/save_menu/20261013_original_screen/current_progress.json'
COMPONENT_ID = '20261016T134720Z_7a7e178dafbd'
EXPORT_ID = '20261016T135657Z_d0a5c707425a'
PACKAGE_ID = 'fbb3b9ec4b43242cbee022b9cdf712f37ccbdf6290015ee2ee27b6547a570573'
STORAGE_ID = '20261016T140601Z'


def require(value, message):
    if not value:
        raise RuntimeError(message)


def read(path):
    return json.loads(Path(path).read_text('utf-8'))


def artifact(path):
    path = Path(path)
    with path.open('rb') as stream:
        sha = hashlib.file_digest(stream, 'sha256').hexdigest()
    return {'path': str(path), 'bytes': path.stat().st_size, 'sha256': sha}


def check(row):
    actual = artifact(row['path'])
    require(all(actual[k] == row[k] for k in ('path', 'bytes', 'sha256')), 'Receipt no longer matches: ' + row['path'])


def publish(path, value):
    temporary = path.with_name(path.name + '.civilian-publish.tmp')
    require(not temporary.exists(), 'Inspect an interrupted publication before continuing')
    with temporary.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def main():
    destination = STAGE / 'conformance.json'
    require(not destination.exists(), 'Do not replace or replay a completed stage result')
    scope_path = STAGE / 'scope.json'
    require(artifact(scope_path)['sha256'] == '943746d6cc04cd175bc5f63d95bbf94d7bc0efd6a186bfabd2578a1444853785', 'Scope changed')
    scope = read(scope_path)
    require(scope['original_game_new_mod_test_hold'] and not scope['deployment']['host_execution_allowed'], 'Mod-test hold changed')
    for row in scope['protected']:
        check(row)
    for pair in scope['existing_files_before']:
        check(pair['backup'])
        require(pair['source']['sha256'] == pair['backup']['sha256'], 'Changed-file backup differs')
    component_path = STAGE / COMPONENT_ID / 'result.json'
    syntax_path = STAGE / 'syntax/result.json'
    export_path = PROJECT / 'Build/CivilianUnitExports' / EXPORT_ID / 'export-manifest.json'
    package_path = PROJECT / 'Build/UnitAssets' / PACKAGE_ID / 'unit-assets.manifest.json'
    preparation_path = STAGE / 'preparation_contract.json'
    for path, expected in (
        (component_path, '38d2ab9d72495bd7879501d82852d1c0c8a34741ab66b540ee308286bef8ab5b'),
        (syntax_path, '273b6329e57b8d9f9017b7273e018c363c44953253b197a07cd69916ea09fdd1'),
        (export_path, '0319dc51f35ada30241da8c179880707fb9b32e0f0b589727db255df718420be'),
        (package_path, '5fcfbdc669ffd233c4ec64118e8e938656079527028a7ac052659421c6b24e7a'),
        (preparation_path, '1a3b3659482c1d39fed0a32041697a3701f664a6d9f059c24002365be0566436')):
        require(artifact(path)['sha256'] == expected, 'Executed proof changed: ' + str(path))
    component, syntax, exported, package, preparation = (read(path) for path in (component_path, syntax_path, export_path, package_path, preparation_path))
    require(component['status'] == 'PASS_HEADLESS_PRODUCTION_WORLD_UNIT_ART_SELECTION' and len(component['variants']) == 2, 'Production component failed')
    for row in component['inputs']:
        check(row)
    cleanup = read(STAGE / 'cleanup.json')
    plan = read(STAGE / 'cleanup_plan.json')
    check(cleanup['plan'])
    require(cleanup['status'] == 'COMPLETE' and cleanup['removed_file_count'] == 35 and cleanup['protected_unchanged'], 'Owned cleanup incomplete')
    removed = {row['path']: row for row in cleanup['removed']}
    require(all(not Path(path).exists() for path in removed), 'Retired temporary file reappeared')
    for row in plan['protected']:
        check(row)
    for variant in component['variants']:
        require(variant['cases'] == 48 and variant['checks'] == 51 and variant['exit_code'] == 0 and variant['compiler_and_linker_warnings'] == 0 and variant['imports'] == ['KERNEL32.dll'], 'Component receipt differs')
        require(removed[variant['object']['path']]['sha256'] == variant['object']['sha256'], 'Historical object cleanup differs')
        for key in ('response', 'compile_log', 'dependencies', 'executable', 'imports_log', 'execution_log'):
            check(variant[key])
    require(syntax['status'] == 'PASS' and len(syntax['translation_units']) == 3 and not syntax['linked'] and not syntax['host_gamecore_hwnd_executed'] and syntax['project_inputs_before'] == syntax['project_inputs_after'] and syntax['generated_code_artifacts'] == [], 'Current consumer syntax failed')
    for row in syntax['project_inputs_after'].values():
        check(row)
    for row in syntax['translation_units']:
        require(row['exit_code'] == 0 and not row['warnings'], 'Current TU failed')
        for key in ('response', 'compile_log', 'dependencies'):
            check(row[key])
    review = read(STAGE / 'source_review.json')
    for row in review['sources']:
        check(row)
    require(exported['status'] == 'PASS_CIVILIAN_UNIT_EXPORT' and len(exported['outputs']) == len(exported['helper_calls']) == 10 and exported['original_inputs_unchanged'] and exported['helper_inputs_unchanged'], 'Original exports failed')
    require(exported['material_reference_metadata_regression']['cases'] == 13 and exported['material_reference_metadata_regression']['passed'], 'Material metadata regression failed')
    for row in exported['outputs']:
        check(row['json'])
        for key in ('model', 'idle', 'fxsxml'):
            check(row[key]['extracted'])
    for row in exported['helper_calls']:
        require(row['exit_code'] == 0 and not row['timed_out'] and not row['output_overflow'] and not row['reader_errors'] and row['reader_threads_finished'], 'Asset child failed')
        check(row['stdout'])
        check(row['stderr'])
    require(package['status'] == 'PASS_ORIGINAL_UNIT_PACKAGE' and package['package']['sha256'] == PACKAGE_ID, 'Combined package failed')
    check(package['package'])
    for key in ('exact_code_inputs_after', 'fixed_inputs_after'):
        for row in package[key]:
            check(row)
    require(package['exact_code_inputs_before'] == package['exact_code_inputs_after'] and package['fixed_inputs_before'] == package['fixed_inputs_after'], 'Package code/fixed input changed')
    require(package['serialized_counts']['meshes_per_art'] == {'ART_DEF_UNIT__WARRIOR': 12, 'ART_DEF_UNIT__SETTLER': 9, 'ART_DEF_UNIT__WORKER': 8}, 'Original members were not preserved')
    require(package['base_preservation']['animation_extension_bytes'] == 793226 and package['base_preservation']['whole_animation_extension_equal'] and package['base_preservation']['old_mesh_float8_and_index_records_equal'], 'Warrior bytes changed')
    require(len(package['binary_validation']['malformed_binary_rejections']) == 16 and len(package['binary_validation']['preserved_content_mutation_rejections']) == 3 and len(package['civilian_transform_checks']) == 10, 'Binary/transform coverage incomplete')
    require(preparation['status'] == 'PASS_EXISTING_PYTHON_PREPARATION_READERS_ONLY' and not preparation['forbidden_attempts'] and preparation['process_or_ctypes_library_calls_after_guard'] == 0 and preparation['old_and_new_embedded_inputs_equal'], 'Existing preparation reader contract failed')
    for row in preparation['inputs_after']:
        check(row)
    for value in (component, exported, package):
        require(value['gamecore_loaded'] is False and value['host_executed'] is False and value['hwnd_created'] is False, 'Native hold violated')
    preserved_candidates = []
    for rel, expected in (
        ('evidence/ui_window_host/20261016T122615Z_1af4a5449cf1/build_result.json', '1c6e4f2640bca96c687fb118e47e48116d8162a48276ccc91405578a40ea170d'),
        ('Build/UiWindowHost/20261016T122615Z_1af4a5449cf1/final/ZeroSisHost_x64.exe', 'c830cd9faecea8c8696375850759fcab2500fe351d049983c5d8c4ff9f389f17'),
        ('evidence/interactive_game/20261016T123256Z_fae85fb9fe79/request.json', 'f0b9b8e898946337a56b6fc180b783b552385104b3786cd573b6ebbf42ca07ef')):
        row = artifact(PROJECT / rel)
        require(row['sha256'] == expected, 'Prior candidate changed')
        preserved_candidates.append(row)
    storage_path = PROJECT / 'evidence/storage' / (STORAGE_ID + '.json')
    before, after = read(scope['storage_before']['path']), read(storage_path)
    check(scope['storage_before'])
    require(after['status'] == 'COMPLETE_METADATA_AUDIT' and not after['errors'] and not after['skipped'], 'Storage audit incomplete')
    storage = {'before_unique_GetCompressedFileSizeW_bytes': before['unique_allocated_bytes'],
               'after_unique_GetCompressedFileSizeW_bytes': after['unique_allocated_bytes'],
               'net_unique_increase_bytes': after['unique_allocated_bytes'] - before['unique_allocated_bytes'],
               'removed_files': cleanup['removed_file_count'], 'removed_unique_bytes': cleanup['removed_unique_GetCompressedFileSizeW_bytes'],
               'limits': 'Metadata snapshot excludes its own new report and later finalization/index bytes; directory/MFT overhead excluded. Hardlink identities counted once.'}
    proofs = {name: artifact(path) for name, path in {
        'scope': scope_path, 'component': component_path, 'actual_current_consumer_syntax': syntax_path,
        'source_review': STAGE / 'source_review.json', 'original_exports': export_path,
        'combined_asset_manifest': package_path, 'existing_preparation_contract': preparation_path,
        'cleanup_plan': STAGE / 'cleanup_plan.json', 'cleanup': STAGE / 'cleanup.json', 'storage_after': storage_path,
    }.items()}
    remaining = [
        'Compile/link and PE-attest a current Host containing both camera and unit selector changes; prepare a private run with the new pinned asset package.',
        'Wait for explicit human end of the original-game new-mod test before Host/GameCore/HWND/GPU execution.',
        'Verify actual visible Settler9/Worker8/Warrior12, facing/terrain/depth/ID picking, camera keys and save/load/menu/turn flow in the current candidate.',
        'Restore civilian animation, other grounded culture/era/embarked art and original material/formation/scale equivalence.',
        'Complete the original full UI/3D/campaign, original saves/mod compatibility and useful deterministic multicore runtime gates.',
    ]
    record = {'schema': 'zerosis.civilian_unit.source_asset_conformance.v1', 'utc': datetime.now(timezone.utc).isoformat(),
              'status': 'PASS_SOURCE_COMPONENT_AND_ASSET_PREPARATION_ONLY', 'scope_sha256': proofs['scope']['sha256'],
              'proofs': proofs, 'current_source_files': review['sources'], 'current_asset_package': package['package'],
              'verification': {'component_optimizations': ['/O2', '/Od'], 'cases_per_optimization': 48, 'checks_per_optimization': 51,
                  'actual_consumer_translation_units': 3, 'current_cpp_dependencies': len(syntax['project_inputs_after']),
                  'actual_asset_export_calls_passed': 10, 'original_source_models_added': 10, 'original_civilian_instances_added': 17,
                  'arts': 3, 'textures': 13, 'meshes_per_art': package['serialized_counts']['meshes_per_art'],
                  'source_curve_poses_independently_recomputed': 10, 'malformed_binary_rejections': 16,
                  'preserved_content_mutation_rejections': 3, 'material_metadata_string_cases': 13,
                  'warrior_extension_bytes_preserved': 793226, 'embedded_files_unchanged': 5,
                  'existing_python_readers_passed': True, 'warnings': 0},
              'failed_attempt': {'manifest': artifact(PROJECT / 'Build/CivilianUnitExports/20261016T135209Z_7989a41f38d5/export-manifest.json'),
                  'cause': 'Asset helper succeeded; metadata path policy initially rejected an original authoring absolute material string.',
                  'resolution': 'Compare only the inert final name to the original declared FXSXML/FPK name; filesystem path guard unchanged.',
                  'raw_inputs_and_JSON_retired_by_cleanup': True},
              'preserved_prior_candidates': preserved_candidates, 'storage': storage,
              'retail_new_mod_test_hold_active': True, 'retail_mods_saves_settings_or_processes_accessed': False,
              'host_gamecore_gpu_hwnd_executed': False, 'new_host_linked': False, 'new_runtime_prepared': False,
              'actual_screen_verified': False, 'civilian_animation_playback': False, 'default_promoted': False,
              'save_schema_changed': False, 'full_goal_redefined': False, 'full_engine_goal_complete': False,
              'remaining_gates': remaining, 'limits': package['limits']}
    previous = artifact(PROGRESS)
    require(previous['sha256'] == 'd6e2283434a5fe76ebad4b993282caa8a194513d0e1a3c87e27bd9f1ae788215', 'Progress changed during this stage')
    progress = read(PROGRESS)
    require(progress['civilian_unit_model_stage']['scope'] == proofs['scope'], 'Progress scope differs')
    publish(destination, record)
    conformance = artifact(destination)
    progress.update(utc=record['utc'], status='CIVILIAN_UNIT_SOURCE_AND_ASSET_PASS_LINK_AND_NATIVE_PENDING',
        prior_goal_turn_classification='progress: connected the real initial civilian art selector, compiled three current consumers, exported ten actual original models and produced a byte-preserving three-art package',
        latest_source_matches_linked_candidate=False, prepared_runtime_matches_latest_source=False,
        latest_cpp_source_matches_actual_host_syntax_proof=True, latest_integrated_syntax_proof=proofs['actual_current_consumer_syntax'],
        latest_current_source_compile_link_proof=None, latest_current_source_pe_attestation=None,
        full_goal_redefined=False, full_engine_goal_complete=False, latest_storage_audit=proofs['storage_after'],
        latest_full_source_embedding_limit='Current camera and civilian selector C++ pass actual Host/renderer syntax; new three-art package and existing Python readers pass. B7/R7 remain prior candidates; current linking, private preparation and actual screen/game acceptance are pending.')
    progress['civilian_unit_model_stage'] = {'status': record['status'], 'scope': proofs['scope'], 'conformance': conformance,
        'asset_package': package['package'], 'native_acceptance': False, 'civilian_animation': False, 'default_promoted': False}
    progress['proofs']['civilian_unit_conformance'] = conformance
    progress['current_prepared_runtime']['current_source_candidate'] = False
    progress['next_native_gates'] = remaining
    progress['storage']['civilian_unit_stage'] = storage
    progress['storage']['latest_measured_utc'] = after['utc']
    progress['user_mod_test_isolation'].update(retail_test_hold_still_active=True, native_window_tests_held=True,
        latest_user_clarification='64비트 말고 새로운 모드 테스트하는거',
        retail_MODS_user_saves_or_game_processes_accessed_this_stage=False,
        game_Host_GameCore_HWND_or_component_windows_executed_this_stage=False,
        retail_settings_accessed_this_stage=False, original_user_settings_read_this_stage=False)
    require(artifact(PROGRESS) == previous, 'Progress changed before publication')
    publish(PROGRESS, progress)
    print(json.dumps({'status': record['status'], 'conformance': conformance, 'progress': artifact(PROGRESS), 'storage': storage}))


if __name__ == '__main__':
    main()
