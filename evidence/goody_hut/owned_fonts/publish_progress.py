"""Publish the verified private build milestone without promoting a runtime."""
from pathlib import Path
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os

STAGE = Path(__file__).absolute().parent
PROJECT = STAGE.parents[2]
INDEX = PROJECT / 'evidence/save_menu/20261013_original_screen/current_progress.json'


def ref(path):
    path = Path(path)
    before = path.stat()
    with path.open('rb') as stream:
        sha = hashlib.file_digest(stream, 'sha256').hexdigest()
    after = path.stat()
    assert (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    return dict(path=str(path), bytes=after.st_size, sha256=sha)


def document(name):
    return json.loads((STAGE / name).read_bytes())


def write(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n');stream.flush();os.fsync(stream.fileno())


def main():
    before = ref(INDEX)
    assert before['sha256'] == 'a258dde165ea5b3fd5ff1fb9063b5c3cdc6dde8ad6db55d75143eb00f3fcce9e'
    old = INDEX.read_bytes();data = json.loads(old)
    assert data['full_engine_goal_complete'] is False and data['full_goal_redefined'] is False
    scope, source = document('build_scope.json'), document('source_seal.json')
    pe, run, retired = document('attestation_retry.json'), document('build_run.json'), document('build_objects_retired.json')
    capture, component, contract = document('capture_result.json'), document('headless_component.json'), document('owned_input_contract.json')
    storage_before, storage_after = document('storage_prebuild.json'), document('storage_postbuild.json')
    cleanup = document('interrupted_cleanup.json')
    assert pe['status'] == 'PASS_READONLY_LINKED_PE_67_EXACT_PAYLOADS_NATIVE_PENDING' and pe['catalog']['entry_count'] == 67
    assert run['status'] == 'PASS' and len(run['actual_objects']) == 10 and run['link_snapshot']['returncode'] == 0
    assert retired['status'] == 'PASS_RETIRED_EXACT_TEN_OBJECTS' and retired['removed_count'] == 10 and retired['protected_unchanged']
    assert cleanup['status'] == 'PASS' and cleanup['protected_unchanged'] and component['checks'] == 485 and contract['status'] == 'PASS'
    assert storage_before['status'] == storage_after['status'] == 'PASS_METADATA_ONLY'
    build_id = pe['build_id'];build = json.loads(Path(pe['build_result']['path']).read_bytes())
    for row in [*source['production_sources'].values(), *source['new_assets_and_tests'].values(),
                *source['font_original_inputs'], pe['executable'], pe['build_result']]:
        assert ref(row['path']) == row
    assert all(not Path(row['object']['path']).exists() for row in run['actual_objects'])
    assert ref(PROJECT / 'Play/EarlyAccess/release.json')['sha256'] == '5587028d64ff6206780837ee7112f0c34d62676fb0627ee099d4eb03aef9c2c5'
    assert ref(PROJECT / 'tools/Start-Engine.ps1')['sha256'] == 'c487ce6c89e374bb625961ce81cf6cbae210608c578542658038e6cb06173d7c'
    backup = STAGE / 'current_progress.before_owned_fonts.json.gz'
    with backup.open('xb') as stream:
        stream.write(gzip.compress(old, compresslevel=9, mtime=0))
    assert gzip.decompress(backup.read_bytes()) == old
    when = datetime.now(timezone.utc).isoformat()
    stage = dict(status='PASS_CURRENT_SOURCE_X64_LINK_AND_EXACT_67_PE_NATIVE_PENDING',
                 build_id=build_id, source_seal=ref(STAGE / 'source_seal.json'), source_conformance=ref(STAGE / 'source_conformance.json'),
                 build_scope=ref(STAGE / 'build_scope.json'), actual_build_run=ref(STAGE / 'build_run.json'),
                 compile_link=pe['build_result'], executable=pe['executable'], pe_attestation=ref(STAGE / 'attestation_retry.json'),
                 actual_catalog=ref(STAGE / 'catalog.json'), original_popup_component=ref(STAGE / 'headless_component.json'),
                 owned_input_contract=ref(STAGE / 'owned_input_contract.json'), owned_font_capture=ref(STAGE / 'capture_result.json'),
                 coff_parser_boundary=ref(STAGE / 'coff_parser_contract.json'), source_matches_candidate=True,
                 original_popup_cases=32, original_popup_checks=485, shared_font_selected_glyphs=component['shared_font_transport']['selected_glyph_count'],
                 catalog_entries=67, actual_cpp_compiles=10, actual_link_objects=5, raw_compiler_objects_remaining=0,
                 objects_retired=ref(STAGE / 'build_objects_retired.json'), interrupted_cleanup=ref(STAGE / 'interrupted_cleanup.json'),
                 owned_font_input_count=15, owned_font_input_bytes=sum(row['bytes'] for row in capture['owned_inputs']),
                 generation_uses_live_installed_fonts=False, renderer_owned_font_root_binding_complete=False,
                 new_source_matching_runtime_prepared=False, current_source_cpp_compiled_or_linked=True,
                 native_acceptance=False, default_promoted=False, full_engine_goal_complete=False,
                 next_required=['Bind the matching private runtime and renderer to the same owned font profile and retained inputs.',
                                'After explicit human mod-test release, verify the actual x64 UI/3D, original Goody/Pantheon pixels, input, SDK effects and following turn.',
                                'Complete full campaign, original save/mod compatibility and measured useful multicore/stability acceptance.'])
    pre, post = storage_before['audit'], storage_after['audit']
    storage = dict(before_audit=ref(STAGE / 'storage_prebuild.json'), after_audit=ref(STAGE / 'storage_postbuild.json'),
                   before_unique_GetCompressedFileSizeW_bytes=pre['unique_allocated_bytes'],
                   after_unique_GetCompressedFileSizeW_bytes=post['unique_allocated_bytes'],
                   net_snapshot_decrease_bytes=pre['unique_allocated_bytes']-post['unique_allocated_bytes'],
                   removed_file_count=cleanup['deleted_files']+retired['removed_count'],
                   removed_logical_path_bytes=cleanup['deleted_logical_bytes']+retired['retired_logical_bytes'],
                   interrupted_last_link_GetCompressedFileSizeW_bytes=cleanup['last_link_GetCompressedFileSizeW_bytes'],
                   owned_font_inputs_preserved_bytes=stage['owned_font_input_bytes'], full_project_copies_created=0,
                   raw_objects_remaining=0, comparison_is_metadata_interval_not_writer_allocation_trace=True,
                   audit_excludes_later_small_publication_and_backup=True,
                   measurement='GetCompressedFileSizeW once per NTFS file ID; not volume free space or physical cluster/MFT accounting')
    conformance = dict(schema='zerosis.goody_hut.owned_font_link_conformance.v1', utc=when,
                       status=stage['status'], full_goal=data['full_goal'], full_goal_redefined=False,
                       full_engine_goal_complete=False, stage=stage, storage=storage,
                       prior_progress=before, exact_prior_progress_backup=ref(backup),
                       latest_sources_and_executable_rehashed_after_cleanup=True,
                       retail_mod_test_hold_active=True, host_gamecore_hwnd_executed=False,
                       retail_user_state_or_game_processes_accessed=False, default_promoted=False)
    write(STAGE / 'linked_conformance.json', conformance)
    stage['conformance'] = ref(STAGE / 'linked_conformance.json')
    data.update(utc=when, status='GOODY_HUT_OWNED_FONT_X64_LINKED_PE_PASS_RUNTIME_AND_NATIVE_PENDING',
                prior_goal_turn_classification='no_progress', current_goal_turn_classification='progress',
                current_host_build_id=build_id, latest_source_matches_linked_candidate=True,
                latest_current_source_actual_cpp_compilation_verified=True,
                latest_current_source_compile_link_proof=pe['build_result'], latest_current_source_pe_attestation=stage['pe_attestation'],
                last_linked_candidate_compile_link_proof=pe['build_result'], last_linked_candidate_pe_attestation=stage['pe_attestation'],
                prepared_runtime_matches_current_linked_candidate=False, prepared_runtime_matches_latest_source=False,
                goody_hut_link_stage=stage, latest_storage_audit=storage['after_audit'],
                latest_full_source_embedding_limit='The current source and67 catalog payloads passed ten real x64 COFF compilations, final five-object linking and exact read-only PE verification. Four changed/generated C++ headers are bound to actual compiler dependencies. Raw objects were retired after attestation. Native behavior remains unverified.')
    data['current_prepared_runtime']['current_source_candidate'] = False
    data['proofs']['goody_hut_owned_font_linked_pe'] = stage['pe_attestation']
    data['storage'].update(latest_measured_unique_GetCompressedFileSizeW_bytes=post['unique_allocated_bytes'], latest_measured_utc=post['utc'],
                           owned_font_inputs_link_stage=storage,
                           current_build=dict(build_id=build_id, frozen_input_reuse=build['frozen_input_reuse'],
                                              raw_compiler_objects_remaining=0, after_unique_GetCompressedFileSizeW_bytes=post['unique_allocated_bytes'],
                                              post_build_metadata_audit_pending=False, default_release_promoted=False,
                                              current_frozen_source_and_linked_PE_retained=True))
    data['user_mod_test_isolation'].update(retail_test_hold_still_active=True, game_Host_GameCore_HWND_or_component_windows_executed_this_stage=False,
                                         retail_MODS_user_saves_or_game_processes_accessed_this_stage=False,
                                         latest_engine_cleanup=dict(conformance=ref(STAGE / 'linked_conformance.json'),
                                                                    retail_mods_user_saves_settings_or_game_processes_accessed=False,
                                                                    host_gamecore_hwnd_executed=False, default_promoted=False, retail_test_hold_still_active=True))
    data['latest_native_acceptance'] = dict(completed_categories=0, total_categories=4, final_acceptance_percent=0,
                                            overall_development_percent=None, scope='Full original UI/campaign, original saves, original mods, useful measured multicore/stability')
    assert ref(INDEX) == before
    temp = INDEX.with_suffix('.json.owned_fonts.tmp')
    write(temp, data)
    os.replace(temp, INDEX)
    saved = json.loads(INDEX.read_bytes())
    assert saved['current_host_build_id'] == build_id and not saved['full_engine_goal_complete'] and saved['full_goal'] == conformance['full_goal']
    write(STAGE / 'progress_update.json', dict(schema='zerosis.goody_hut.owned_font_progress_update.v1', status='PASS',
           before=before, after=ref(INDEX), prior_backup=ref(backup), conformance=ref(STAGE / 'linked_conformance.json'),
           full_goal_unchanged=True, default_promoted=False))
    print(json.dumps(dict(status='PASS', build_id=build_id, progress=ref(INDEX), conformance=ref(STAGE / 'linked_conformance.json'),
                          unique_GiB=round(post['unique_allocated_bytes']/2**30, 4), net_prebuild_snapshot_decrease_MiB=round(storage['net_snapshot_decrease_bytes']/2**20, 2),
                          retired_logical_MiB=round(storage['removed_logical_path_bytes']/2**20, 2))))


if __name__ == '__main__':
    main()
