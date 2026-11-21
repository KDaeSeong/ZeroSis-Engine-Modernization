"""Publish the attested offline candidate and exact cleanup/storage receipts."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,gzip,hashlib,json,os,sys
sys.dont_write_bytecode=True
STAGE=Path(__file__).absolute().parent
PROJECT=STAGE.parents[2]
IDENTIFIER='20261116T142423Z_21271db09067'
sys.path[:0]=[str(PROJECT/'tools')]
import build_exit_confirm_host as common
import retained_menu_suite_host_input as menu
from menu_suite_storage import storage


def read(path):return json.loads(Path(path).read_text('utf-8-sig'))
def ref(path):return common.artifact(Path(path).absolute())
def save(path,value):Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
def new(path,value):
    assert not Path(path).exists();save(path,value)
    return ref(path)


def source_changes():
    changed=[];retired=[];unchanged=[]
    for index in sorted(STAGE.glob('source_before*.json')):
        for row in read(index)['backups']:
            before=row['source'];now=ref(before['path']);backup=Path(row['backup']['path'])
            assert hashlib.sha256(gzip.decompress(backup.read_bytes())).hexdigest()==before['sha256']
            if (now['bytes'],now['sha256'])!=(before['bytes'],before['sha256']):
                changed.append(dict(before=before,after=now,backup=ref(backup)))
                continue
            unchanged.append(now)
            assert backup.parent==STAGE/'source_before' and backup.suffix=='.gz'
            owned=ref(backup);assert owned['links']==1 and not owned['file_attributes']&0x401
            assert owned['sha256']==row['backup']['sha256']
            retired.append(dict(before=owned,source=now,allocated_bytes=storage.allocated(backup)))
    new(STAGE/'unchanged_backup_cleanup_plan.json',dict(files=retired,
        reason='Exact source bytes still exist; retain backups only for changed files.',recursive_delete=False))
    for row in retired:
        assert ref(row['before']['path'])==row['before'] and ref(row['source']['path'])==row['source']
        Path(row['before']['path']).unlink()
    new(STAGE/'unchanged_backup_cleanup_result.json',dict(status='PASS_ONLY_UNCHANGED_SOURCE_BACKUP_DUPLICATES_REMOVED',
        files=retired,deleted_files=len(retired),released_unique_allocated_bytes=sum(r['allocated_bytes'] for r in retired),
        changed_file_backups_preserved=True,source_bytes_deleted=False))
    return new(STAGE/'source_changes.json',dict(status='PASS_CHANGED_FILES_AND_ONLY_REQUIRED_BEFORE_BACKUPS_RETAINED',
        changed=changed,unchanged_sources=unchanged,retired_backup_duplicates=len(retired),
        original_backup_indexes_remain_historical_with_explicit_retirement_ledger=True,
        mutable_docs_and_progress_snapshot_before_final_publication=True,
        new_production_headers=[ref(PROJECT/'Source/Presentation'/n) for n in (
            'OriginalTerrainCacheSamplingModel.h','OriginalReflectionProjectionModel.h',
            'OriginalIceAssets.h','OriginalIceContract.h','OriginalIceShader.h')],
        native_execution=False))


def cleanup_summary():
    rows=[]
    for path in sorted(STAGE.rglob('*cleanup*json')):
        if 'plan' in path.name or path.name=='cleanup_summary.json':continue
        value=read(path)
        if not str(value.get('status','')).startswith('PASS'):continue
        count=value.get('deleted_files',value.get('files_deleted',value.get('removed_files')))
        if isinstance(count,list):count=len(count)
        if count is None:
            fallback=value.get('files',value.get('deleted',[]))
            count=fallback if isinstance(fallback,int) else len(fallback)
        sizes=[(key,value[key]) for key in ('released_unique_allocated_bytes','allocated_bytes_removed',
            'deleted_allocated_bytes','allocated_bytes_released','reclaimed_allocated_bytes') if value.get(key) is not None]
        assert len(sizes)<=1,(path,sizes)
        logical=next((value[k] for k in ('released_logical_bytes','logical_bytes_removed','deleted_logical_bytes') if k in value),None)
        rows.append(dict(receipt=ref(path),deleted_files=count,allocated_bytes_released=sizes[0][1] if sizes else None,
            allocation_field=sizes[0][0] if sizes else None,logical_bytes_released=logical))
    assert not any(q.is_file() and q.suffix.lower() in ('.obj','.exe','.cso','.dxbc','.rsp','.cmd') for q in STAGE.rglob('*'))
    return new(STAGE/'cleanup_summary.json',dict(status='PASS_PHASE12_OWN_REGENERABLE_TEMPORARIES_REMOVED',receipts=rows,
        deleted_files=sum(row['deleted_files'] for row in rows),
        confirmed_allocated_bytes_released=sum(row['allocated_bytes_released'] or 0 for row in rows),
        allocation_not_measured_receipts=sum(row['allocated_bytes_released'] is None for row in rows),
        note='Cumulative temporary allocations retired, not a claimed final project size reduction. Original Ice cleanup1 corrects an unmeasured allocation; only cleanup2 is added as measured.',
        phase12_private_exe_obj_cso_dxbc_rsp_cmd_remaining=0,
        old_runtimes_originals_saves_and_claude_outputs_deleted=False,full_project_copies_created=0))


def update_index(value):
    path=PROJECT/'evidence/save_menu/20261013_original_screen/current_progress.json';index=read(path)
    index.update(utc=value['utc'],status=value['status'],current_source_working_stage=str(STAGE),
        current_offline_stage=ref(STAGE/'current_work.json'),current_host_build_id=IDENTIFIER,
        current_host_build=dict(value['current_host'],status='CURRENT_COMPILED_EXPLICIT_PREPARED_PROFILE_NOT_REGISTERED_OR_EXECUTED',
            registered=False,globally_registered=False,prepared_profile_only=True,host_executed=False,gamecore_loaded=False,
            screen_verification_deferred=True,full_engine_goal_complete=False),
        latest_source_matches_linked_candidate=True,latest_host_source_matches_current_link_proof=True,
        latest_source_matches_linked_candidate_scope='All current frozen Host sources; standalone ice/projection parts remain explicitly unactivated.',
        latest_current_source_compile_link_proof=value['current_host']['build_result'],
        latest_current_source_pe_attestation=value['current_host']['independent_attestation'],
        latest_current_source_actual_cpp_compilation_verified=True,
        latest_current_source_actual_cpp_compilation_verified_proof=value['current_host']['build_result'],
        prepared_runtime_matches_latest_source=False,prepared_runtime_matches_current_linked_candidate=False,
        latest_private_prepared_pair_matches_current_host_and_selected_sdk_sources=False,
        full_engine_goal_complete=False,actual_runtime_acceptance=False,
        current_native_or_screen_relaunch_allowed=False,screen_verification_deferred=True,
        requested_phase12_scope=[2,3],terrain_cache_height_water_reflection_phase12_status='OFFLINE_COMPILE_LINK_ATTESTED_NATIVE_PENDING')
    # Preserve the actual previous runtime90b98 and registered/default selection.
    assert index['current_prepared_runtime']['run_id']=='20261116T123457Z_90b98a574efc'
    save(path,index)


def publish():
    assert not (STAGE/'current_work.json').exists()
    report=PROJECT/'evidence/ui_window_host'/IDENTIFIER/'build_result.json';build=read(report)
    directory=STAGE/'pair_preparation'/IDENTIFIER;profile=read(directory/'prepared_profile.json')
    att=read(directory/'independent_attestation.json');review=read(STAGE/'cache/cache_final_build_review.json')
    assert review['status'].startswith('PASS') and not build['host_runtime_executed'] and not build['gamecore_loaded']
    assert not profile['native_execution'] and not profile['globally_registered']
    assert read(STAGE/'host_build/controller_exit.json')['returncode']==0
    for row in build['current_source_inputs']:common.sealed(row)
    frozen=menu.frozen_rows(build)
    previous=read(STAGE.parent/'phase11/runtime_integration/current_work.json')
    packages={name:ref(value['source']['path']) for name,value in previous['packages'].items()}
    assert len(packages)==6 and all(packages[k]['sha256']==v['source']['sha256'] for k,v in previous['packages'].items())
    changes=ref(STAGE/'source_changes.json') if (STAGE/'source_changes.json').exists() else source_changes()
    cleanup=ref(STAGE/'cleanup_summary.json') if (STAGE/'cleanup_summary.json').exists() else cleanup_summary()
    binding=new(STAGE/'compiled_asset_binding.json',dict(status='PASS_PHASE12_HOST_WITH_EXISTING_SIX_ASSETS_RUNTIME_PENDING',
        host=build['executable'],packages=packages,new_asset_packages=0,original_asset_package_copies=0,
        new_runtime_materialized=False,native_execution_allowed=False,default_promoted=False))
    value=dict(schema='zerosis.phase12.cache_height_water_reflection.current_work.v1',
        status='PASS_PHASE12_REQUESTED_OFFLINE_PARTS_COMPILED_LINKED_ATTESTED_NATIVE_PENDING',
        utc=datetime.now(timezone.utc).isoformat(),scope_numbers=[2,3],full_engine_goal_complete=False,
        latest_source_matches_linked_candidate=True,prepared_runtime_matches_latest_source=False,actual_runtime_acceptance=False,
        current_host=dict(build_id=IDENTIFIER,parent_build_id='20261116T114748Z_014dd63ad3bc',build_result=ref(report),
            executable=build['executable'],prepared_profile=ref(directory/'prepared_profile.json'),
            independent_attestation=ref(directory/'independent_attestation.json'),
            compiler_dependency_count=build['compiler_dependency_count'],current_source_input_count=len(build['current_source_inputs']),
            frozen_input_count=len(frozen),source_manifest_count=att['source_manifest_count'],translation_units=5,
            additional_manifest_rows=len(read(build['menu_suite_component']['path'])['sources']),
            compiler_and_linker_warnings=0,required_ui_sidecar_files=154),
        packages=packages,compiled_asset_binding=binding,source_manifest=build['menu_suite_component'],source_changes=changes,
        proofs=dict(components=ref(STAGE/'component_receipts.json'),final_build_review=ref(STAGE/'cache/cache_final_build_review.json')),
        recorded_compile=dict(plan=ref(STAGE/'host_build/plan.json'),review=ref(STAGE/'plan_review.json'),
            controller_exit=ref(STAGE/'host_build/controller_exit.json'),attempts=1,automatic_retry=False),
        retained_prepared_runtime=previous['current_prepared_runtime'],
        retention_reason='Keep new21271/current prepared014dd90b98, immediate parent dbb/aa885, prior99b3 and recovery4c8f/40a sessions. Native acceptance is held; frozen parent dependencies and user sessions remain required.',
        original_install_mods_settings_saves_default_or_registration_changed=False,
        native_host_sdk_clr_hwnd_gpu_audio_or_game_attempts=0,new_game_runtime_materialized=False,
        scope_results={
            '2':dict(status='ORIGINAL_STAMP_AND_HEIGHT_METRICS_CONNECTED_CACHE_COORDINATE_COMPONENT_READY',
                implemented=['single u16 truncation before centered-float storage','lossless heightmap code recovery without another large array',
                    'raw/255*.2 world metric, .866 Y metric and explicit candidate display origin',
                    'known-only per-axis world-height/normal bounds and original material-coordinate origin restoration'],
                remaining=['original packed cache/compression/residency and full scratch-to-final integration',
                    'runtime metric overrides and original world camera/origin','x87 cutoff precision and original placement comparison']),
            '3':dict(status='RAW_DRAW_AND_WATER_PROJECTOR_CONNECTED_ORIGINAL_PROJECTION_ICE_COMPONENTS_ONLY',
                implemented=['same Raw producer matrix in dedicated interpolated water XY/W projection','original UV/WRAP and invalid-projector sample guard',
                    'explicit original RH bounds/axis projector CPU component','ice8B vertex/assets/VS CPU and shader components'],
                remaining=['actual original bounds/axis and clip-plane producer','wonders/landmarks/ice scene providers',
                    'ice fracture/crack mesh and full pixel shader','actual GPU colour/depth and runtime water calibration'])},
        claude_scope=dict(item=4,source_models_untouched=True,outputs_preserved=True,
            new_geometry_handoff_present=True,result_review_and_production_integration_by_separate_step=True),
        piece_placement_report='규칙 동등, 배치 동등은 미검증',
        checks=dict(cache_sampling_cpu=2355453,production_height_binding_cpu=528575,reflection_projection_cpu=144,
            terrain_model_geometry=90876,water_surface=853718,water_bridge=547501,
            deterministic_parallel_checks_per_mode=198,deterministic_optimization_modes=2,
            ice_cpu=625,ice_vs_cpu_interpretation_components=4864,homogeneous_wrap_cases=180,
            original_static_plan_claims=68,new_strict_shader_entry_points=9,actual_compiler_command_phases=12),
        protection=dict(before=ref(STAGE/'protection_before.json.gz'),precompile=ref(STAGE/'protection_prestage.json'),after_pending=True),
        storage=dict(before=ref(STAGE/'storage_before.json'),precompile=ref(STAGE/'storage_prestage.json'),after_pending=True,
            cleanup_summary=cleanup,new_asset_packages=0,existing_asset_package_copies=0,full_project_copies_created=0,
            new_full_runtime_bundles=0,confirmed_disposable_bytes=0,threshold_bytes=10*1024**3,
            concurrent_claude_outputs_present=True,project_net_delta_must_not_be_attributed_only_to_this_task=True))
    new(STAGE/'current_work.json',value);update_index(value)
    path=PROJECT/'docs/TERRAIN_OFFLINE_PHASE12.md';text=path.read_text('utf8')
    text+='\n## 통합 빌드 결과\n\n현재 후보는 `'+IDENTIFIER+'`다. 실제 5개 번역 단위 컴파일·링크와 독립 파일 검증을 통과했으며 경고는0개다. C++14 4개와 지형 C++17, 실제 컴파일 입력652개·동결 입력1114개·소스 목록487개를 검증했다. UI154개는 기존 파일 링크로 연결해 새 고유 자산 payload가0이다. 새 Host는 실행하지 않았고 별도 실행 묶음 연동은 남아 있다.\n'
    path.write_text(text,encoding='utf8')
    print(json.dumps(dict(status=value['status'],host=IDENTIFIER,cleanup=read(cleanup['path'])['confirmed_allocated_bytes_released'])))


def close():
    path=STAGE/'current_work.json';value=read(path);assert value['storage']['after_pending']
    protection=read(STAGE/'protection_after.json');assert protection['status']=='PASS' and not protection['differences']
    before,after=read(STAGE/'storage_before.json'),read(STAGE/'storage_after.json')
    value['protection'].update(after=ref(STAGE/'protection_after.json'),after_pending=False)
    value['storage'].update(after=ref(STAGE/'storage_after.json'),after_pending=False,
        before_unique_allocated_bytes=before['unique_allocated_bytes'],after_unique_allocated_bytes=after['unique_allocated_bytes'],
        allocated_bytes_change=after['unique_allocated_bytes']-before['unique_allocated_bytes'],
        measurement='Real os.stat identity deduplication and FileStandardInfo.AllocationSize; final receipt/index writes follow scan. Includes concurrent Claude work; directories/driver heaps excluded.')
    value['utc']=datetime.now(timezone.utc).isoformat();save(path,value);update_index(value)
    print(json.dumps(dict(status=value['status'],allocated_bytes=after['unique_allocated_bytes'],
        delta=value['storage']['allocated_bytes_change'],protected_paths=protection['paths'])))


if __name__=='__main__':
    cli=argparse.ArgumentParser();cli.add_argument('action',choices=['publish','close']);args=cli.parse_args()
    publish() if args.action=='publish' else close()
