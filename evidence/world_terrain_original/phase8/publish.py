"""Publish and close the bounded phase-eight offline milestone."""
from datetime import datetime,timezone
from pathlib import Path
import argparse,json,sys
sys.dont_write_bytecode=True
STAGE=Path(__file__).absolute().parent
PROJECT=STAGE.parents[2]
sys.path.insert(0,str(PROJECT/'tools'))
import build_exit_confirm_host as common
import retained_menu_suite_host_input as menu
IDENTIFIER='20261115T121456Z_dbb01a1f4f50'

def read(path):return json.loads(Path(path).read_text('utf8'))
def ref(path):return common.artifact(Path(path).absolute())
def save(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
def write_new(path,value):
    with path.open('x',encoding='utf8')as f:json.dump(value,f,ensure_ascii=False,indent=2);f.write('\n')

def cleanup_summary():
    patterns=['**/water_cleanup_result.json','**/asset_cleanup_result.json','**/screen_cleanup_result.json',
        '**/normal_contract_cleanup_receipt.json','dynamic_shadow/**/cleanup_result.json',
        'normal_adapter/**/cleanup_result.json','pair_preparation/**/cleanup_result.json']
    paths={path for pattern in patterns for path in STAGE.glob(pattern)}
    paths.add(STAGE/'interrupted_cleanup/result.json');rows=[]
    for path in sorted(paths):
        value=read(path);assert value['status'].startswith('PASS')
        amount=next(value[k]for k in('released_unique_allocated_bytes','allocated_bytes_released','deleted_allocated_bytes')if k in value)
        count=next((value[k]for k in('deleted_files','files_deleted','retired_files')if k in value),None)
        if count is None:count=len(value['files'])
        rows.append(dict(receipt=ref(path),files=count,released_unique_allocated_bytes=amount))
    result=dict(status='PASS_PHASE8_OWNED_TEMPORARIES_RETIRED',receipts=rows,files_deleted=sum(r['files']for r in rows),
        released_unique_allocated_bytes=sum(r['released_unique_allocated_bytes']for r in rows),
        accounting='Sum of independently verified retired file lifetimes, including interrupted build. Net project allocation is reported separately.',
        original_asset_packs_copied=0,new_asset_packs=0,new_full_runtime_bundles=0,shared_readonly_donor_attributes_changed=False)
    write_new(STAGE/'cleanup_summary.json',result);return result

def publish():
    output=STAGE/'current_work.json';assert not output.exists()
    report=PROJECT/'evidence/ui_window_host'/IDENTIFIER/'build_result.json';build=read(report)
    profile=STAGE/'pair_preparation'/IDENTIFIER/'prepared_profile.json';prepared=read(profile)
    assert not build['host_runtime_executed']and not build['gamecore_loaded']and not prepared['native_execution']and not prepared['globally_registered']
    frozen=menu.frozen_rows(build)
    for row in read(STAGE/'root_source_freeze.json')['sources']:
        assert ref(row['path'])['sha256']==row['sha256']
    for row in build['current_source_inputs']:
        assert ref(row['path'])['sha256']==row['sha256']
    previous=read(STAGE.parent/'phase7/runtime_integration/current_work.json')
    packages={name:ref(row['source']['path'])for name,row in previous['packages'].items()}
    assert all(row['sha256']==previous['packages'][name]['source']['sha256']for name,row in packages.items())
    cleanup=cleanup_summary()
    proofs={name:ref(STAGE/path)for name,path in (
        ('components','component_receipts.json'),('original_normal','normal_cache/normal_contract_semantics.json'),
        ('normal_adapter','normal_adapter/cpu01/result.json'),('normal_regressions','normal_regressions/asset_cpu_completion.json'),
        ('screen','screen_lighting/screen_current.json'),('screen_integration','screen_lighting/screen_integration_review.json'),
        ('water_source','water_fog/water_final_source_reseal.json'),('dynamic_shadow','dynamic_shadow/shadow_final_source_reseal.json'),
        ('field_reuse','normal_cache/normal_contract_shader/normal_contract_field_reseal.json'),
        ('plan_review','normal_cache/normal_contract_retry_plan_review.json'),('plan68','plan_check_receipt.json'))}
    assert all(read(row['path'])['status'].startswith('PASS')for row in proofs.values())
    binding=dict(status='PASS_PHASE8_COMPILED_FIVE_ASSET_BINDING_RUNTIME_PENDING',host=build['executable'],packages=packages,
        compiled_sources={name:ref(PROJECT/'Source/Presentation'/name)for name in('OriginalTerrainNormalModel.h','OriginalScreenLightingModel.h','OriginalScreenLightingShader.h','OriginalDynamicShadowModel.h','OriginalDynamicShadowShader.h','OriginalWaterFogModel.h','OriginalLightingFieldBinding.h')},
        new_asset_packages=0,asset_payload_copies=0,runtime_materialized=False,default_promoted=False,native_launch_allowed=False)
    write_new(STAGE/'compiled_asset_binding.json',binding)
    value=dict(schema='zerosis.original_normal_reflection_shadow_water.phase8.current_work.v1',
        status='PASS_PHASE8_NORMAL_SCREEN_REFLECTION_DYNAMIC_SHADOW_WATER_FOG_OFFLINE_BUILD_NATIVE_PENDING',
        utc=datetime.now(timezone.utc).isoformat(),scope_numbers=[2,3,4,5],full_engine_goal_complete=False,
        latest_source_matches_linked_candidate=True,prepared_runtime_matches_latest_source=False,
        actual_runtime_acceptance=False,current_host=dict(build_id=IDENTIFIER,parent_build_id='20261115T093013Z_23c5037b12b9',
            build_result=ref(report),executable=build['executable'],prepared_profile=ref(profile),
            independent_attestation=ref(profile.with_name('independent_attestation.json')),
            compiler_dependency_count=build['compiler_dependency_count'],current_source_input_count=len(build['current_source_inputs']),
            frozen_input_count=len(frozen),translation_units=5,compiler_and_linker_warnings=0,required_ui_sidecar_files=154),
        packages=packages,compiled_asset_binding=ref(STAGE/'compiled_asset_binding.json'),proofs=proofs,
        source_manifest=build['menu_suite_component'],retained_prepared_runtime='Build/InteractiveGameRuntime/20261115T101941Z_99b3c393ee9a',
        retained_recovery_runtime='Build/InteractiveGameRuntime/20261115T011241Z_4c8fd55e99db',
        retained_user_session='Build/InteractiveGameRuntime/20261108T003146Z_40a8030edf08/sessions/350dd3b9ceb408a391b5a8aa63b48301',
        implemented=[
            'Original bulk 5x5 base normals, source float projection followed by half GPU input, RGBA8 normal precision and explicit raw/world/normalization calibration boundaries.',
            'Finalt9 Reflection Texture Raw provider, original quality/debug-gate rules and exact non-tessellated UV; shared1024/disabled32 images, waterless minimal reflection, no recursive reflection input.',
            'Private known terrain/current visible unit depth production and water projected shadow receiver; prepared pose/VB reuse and no main ID writes.',
            'Water gray.4 FOW, overlay/LUT/distance order, fragment marker excluding overlying units and single colour-only post-pass; original hardware blending remains unproven.'],
        checks=dict(pure_cpu=314862,new_strict_shader_entry_points=12,reused_unchanged_field_shader_entry_points=4,original_bytecode_claims=68,actual_compiler_command_phases=12),
        native_host_sdk_clr_hwnd_gpu_audio_or_game_attempts=0,new_game_runtime_materialized=False,
        original_install_mods_settings_saves_default_or_registration_changed=False,piece_placement_report='규칙 동등, 배치 동등은 미검증',
        build_interruption=dict(first_build_id='20261115T115920Z_a4b5d1514cc1',status='UNATTESTED_AFTER_LINK_PAYLOAD_RETIRED',
            original_plan_replayed=False,source_feature_changes_for_retry=0,cause='Unconfirmed interruption before final records; no returncode/guard state reconstructed.',
            fresh_recorded_plan=ref(STAGE/'host_build_retry01/plan.json'),launcher=ref(STAGE/'host_build_retry01/launcher.json'),
            retired=ref(STAGE/'interrupted_cleanup/result.json')),
        remaining=[
            'Original normal-cache RTV/SRV gamma choice, compressed codecs/residency, selected cache resolutions/mips/resampling, D3DX normalization precision and world/raw calibration.',
            'Original reflection camera/plane, all four scene classes and colour-space/sampler calibration; original hardware water blend states.',
            'Latest compiled candidate is sealed but not materialized into an execution bundle; retained99b3 still contains previous23c image.',
            'GPU colour/depth/ID/occlusion, actual UI/input/CityView, performance/VRAM, original screen comparison and gameplay/save/mod/multicore acceptance remain held.'],
        protection=dict(before=ref(STAGE/'protection_before.json.gz'),precompile=ref(STAGE/'protection_precompile.json'),after_pending=True),
        storage=dict(before=ref(STAGE/'storage_before.json'),precompile=ref(STAGE/'storage_precompile.json'),after_pending=True,
            full_project_copies_created=0,existing_asset_package_copies=0,new_asset_packages=0,new_full_runtime_bundles=0,
            cleanup_summary=ref(STAGE/'cleanup_summary.json'),confirmed_disposable_bytes=0,threshold_bytes=10*1024**3))
    write_new(output,value);update_index(value)
    path=PROJECT/'docs/CLAUDE_HANDOFF.md';head,tail=path.read_text('utf8').split('\n',1)
    entry=(f'## 원본 법선·화면 반사·동적 그림자·물 안개 8단계 — 2026-11-15\n\n현재 실제 컴파일·링크 후보는 `{IDENTIFIER}`이며 경고0, 독립 파일 검증과 profile 봉인까지 통과했다. '
        '원본 bulk 기본법선/half 값·RGBA8 정밀도, t9=Reflection Texture Raw/품질 규칙/공유 반사, private 지형·현재유닛 그림자→물, 물.4 FOW/유닛제외 표식을 연결했다. '
        'CPU314,862·새 strict12/재사용4·원본68주장 통과, Host/SDK/CLR/HWND/GPU/음향/게임 실행0이다. '
        '첫 빌드는 링크 뒤 기록 전 중단돼 새 STAGE/검토 계획으로 다시 기록했고, 첫 payload와 모든 임시물을 정확히 정리했다. '
        '기존5팩/99b3·4c8f·40a저장/기본 실행을 보존했다. 새 runtime은 만들지 않아99b3는 직전23c 조합이다. '
        '원본 캐시 보기·밉·압축/정규화·반사 전체 장면/카메라/색공간·하드웨어 물 혼합·실GPU/화면은 계속 미확정이다. '
        '상세는 `docs/NORMAL_REFLECTION_SHADOW_WATER_PHASE8.md`, 최종 상태는 `evidence/world_terrain_original/phase8/current_work.json`이다.\n\n')
    path.write_text(head+'\n\n'+entry+tail.lstrip('\n'),encoding='utf8')
    path=PROJECT/'docs/WORLD_TERRAIN_ORIGINAL_PLAN.md';text=path.read_text('utf8');marker='## 5. 열린 질문';assert text.count(marker)==1
    note=('### 법선·반사·동적 그림자·물 안개 후속 기록 (2026-11-15)\n\n'
        '8단계에서 기본 bulk법선→float 투영/half 입력·법선 RGBA8 정밀도, 최종t9=Reflection Texture Raw의 생산/품질/UV 경로를 추가 확인했다. '
        '현재 지형/유닛 반사와 물 투영 그림자·회색.4 물 FOW를 오프라인 구현하고 실제 컴파일·링크까지 검증했다. '
        '원본 캐시 보기/압축/밉/선택 해상도·정규화와 세계단위 보정·전체 반사 장면/카메라·원본 하드웨어 혼합·실GPU/화면 수락은 미확정으로 유지한다. '
        '자세한 구분은 `NORMAL_REFLECTION_SHADOW_WATER_PHASE8.md`, 근거는 `evidence/world_terrain_original/phase8/current_work.json`이다.\n\n')
    path.write_text(text.replace(marker,note+marker,1),encoding='utf8')
    print(json.dumps(dict(status=value['status'],build_id=IDENTIFIER,temporary_files_retired=cleanup['files_deleted'],retired_allocated_bytes=cleanup['released_unique_allocated_bytes'])))

def update_index(value):
    path=PROJECT/'evidence/save_menu/20261013_original_screen/current_progress.json';index=read(path)
    index.update(utc=value['utc'],status=value['status'],current_source_working_stage=str(STAGE),current_offline_stage=ref(STAGE/'current_work.json'),
        latest_source_matches_linked_candidate=True,prepared_runtime_matches_latest_source=False,full_engine_goal_complete=False,
        original_normal_reflection_shadow_water_phase8_status='OFFLINE_COMPILE_LINK_ATTESTED_NATIVE_PENDING')
    save(path,index)

def close():
    path=STAGE/'current_work.json';value=read(path);assert value['storage']['after_pending']
    protection=read(STAGE/'protection_after.json');assert protection['status']=='PASS'
    before,after=read(STAGE/'storage_before.json'),read(STAGE/'storage_after.json')
    value['protection'].update(after=ref(STAGE/'protection_after.json'),after_pending=False)
    value['storage'].update(after=ref(STAGE/'storage_after.json'),after_pending=False,before_unique_allocated_bytes=before['unique_allocated_bytes'],
        after_unique_allocated_bytes=after['unique_allocated_bytes'],allocated_bytes_change=after['unique_allocated_bytes']-before['unique_allocated_bytes'],
        measurement='Real os.stat identity deduplication; hardlinks counted once. Receipt/index writes follow scan, directory/driver allocation excluded.')
    value['utc']=datetime.now(timezone.utc).isoformat();save(path,value);update_index(value)
    print(json.dumps(dict(status=value['status'],allocated_bytes=after['unique_allocated_bytes'],delta=value['storage']['allocated_bytes_change'],protected_paths=protection['paths'])))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['publish','close']);a=parser.parse_args()
    if a.action=='publish':publish()
    else:close()
