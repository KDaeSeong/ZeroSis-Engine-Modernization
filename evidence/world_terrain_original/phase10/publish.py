"""Publish verified phase-ten offline work; never promote or run a game."""
from datetime import datetime,timezone
from pathlib import Path
import argparse
import json
import sys
sys.dont_write_bytecode=True
STAGE=Path(__file__).absolute().parent
PROJECT=STAGE.parents[2]
sys.path[:0]=[str(PROJECT/'tools'),str(PROJECT/'Tests')]
import build_exit_confirm_host as common
import retained_menu_suite_host_input as menu
from original_water_shader import ref as storage_ref


def read(path):return json.loads(Path(path).read_text('utf-8-sig'))
def ref(path):return common.artifact(Path(path).absolute())
def save(path,value):Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
def write_new(path,value):
    with Path(path).open('x',encoding='utf8') as stream:json.dump(value,stream,ensure_ascii=False,indent=2);stream.write('\n')


def cleanup_summary():
    rows=[]
    for path in sorted(STAGE.rglob('*cleanup*json')):
        if path.name in ('cleanup_summary.json','extracted_cleanup_plan.json') or 'plan' in path.name:continue
        value=read(path)
        if not str(value.get('status','')).startswith('PASS'):continue
        sizes=[value[key] for key in ('released_unique_allocated_bytes','allocated_bytes_removed','deleted_allocated_bytes','allocated_bytes_released') if key in value]
        if not sizes:continue
        assert len(sizes)==1
        leaves=value.get('files',[])
        count=value.get('deleted_files',value.get('files_deleted',len(leaves) if isinstance(leaves,list) else leaves))
        rows.append(dict(receipt=ref(path),deleted_files=count,released_unique_allocated_bytes=sizes[0]))
    value=dict(status='PASS_THIS_PHASE_TEMPORARIES_RETIRED',receipts=rows,
        deleted_files=sum(row['deleted_files'] for row in rows),
        released_unique_allocated_bytes=sum(row['released_unique_allocated_bytes'] for row in rows),
        old_runtime_or_original_or_saves_deleted=False,full_project_copies_created=0)
    write_new(STAGE/'cleanup_summary.json',value)
    return value


def update_index(value):
    path=PROJECT/'evidence/save_menu/20261013_original_screen/current_progress.json'
    index=read(path)
    index.update(utc=value['utc'],status=value['status'],current_source_working_stage=str(STAGE),
        current_offline_stage=ref(STAGE/'current_work.json'),current_host_build_id=value['current_host']['build_id'],
        latest_source_matches_linked_candidate=True,prepared_runtime_matches_latest_source=False,
        prepared_runtime_matches_current_linked_candidate=False,full_engine_goal_complete=False,
        requested_phase10_scope=[2,3,4,7],actual_runtime_acceptance=False,
        terrain_cache_reflection_trees_camera_multicore_phase10_status='OFFLINE_COMPILE_LINK_ATTESTED_NATIVE_PENDING')
    save(path,index)


def publish(identifier):
    output=STAGE/'current_work.json';assert not output.exists()
    report=PROJECT/'evidence/ui_window_host'/identifier/'build_result.json';build=read(report)
    prepared_path=STAGE/'pair_preparation'/identifier/'prepared_profile.json';prepared=read(prepared_path)
    assert build['build_id']==identifier and not build['host_runtime_executed'] and not build['gamecore_loaded']
    assert not prepared['native_execution'] and not prepared['globally_registered']
    assert read(STAGE/'host_build_retry02/controller_exit.json')['returncode']==0
    for row in build['current_source_inputs']:common.sealed(row)
    frozen=menu.frozen_rows(build)
    previous=read(STAGE.parent/'phase9/runtime_integration/current_work.json')
    packages={name:ref(value['source']['path']) for name,value in previous['packages'].items()}
    assert all(packages[name]['sha256']==value['source']['sha256'] for name,value in previous['packages'].items())
    screen_path=PROJECT/'Build/OriginalScreenLightAssets/f02165b489bfe80557e1fd0246c0a2423f5494a28f4974d935120ea14528a0e0/screen-light-assets.bin'
    packages['screen_light']=ref(screen_path)
    assert packages['screen_light']['sha256']=='f02165b489bfe80557e1fd0246c0a2423f5494a28f4974d935120ea14528a0e0'
    proofs={name:ref(STAGE/path) for name,path in (
        ('components','component_receipts.json'),('build_plan_review','retry02_plan_review.json'),
        ('independent_final_build_review','cache/cache_final_build_review.json'),
        ('cache_views','cache/cache_view_contract.json'),
        ('owner_correction','cache/cache_owner_contract.json'),
        ('terrain_regressions','cache_regressions/asset_cpu01/asset_result.json'),
        ('water','reflection/water_completion.json'),('multicore','multicore/parallel_current_work.json'),
        ('forest_tessellation_camera','geometry/forest_tessellation_cpu_attempt01/result.json'),
        ('forest_tessellation_shaders','geometry/shader02/result.json'),('terrain_shader','terrain_shader01/result.json'))}
    assert all(read(row['path'])['status'].startswith('PASS') for row in proofs.values())
    cleanup=cleanup_summary()
    binding=dict(status='PASS_PHASE10_COMPILED_ASSET_BINDING_RUNTIME_PENDING',host=build['executable'],packages=packages,
        required_new_environment=dict(name='ZEROSIS_SCREEN_LIGHT_ASSETS',value=str(screen_path)),
        original_five_packages_copied=0,new_package_bytes=packages['screen_light']['bytes'],
        new_runtime_materialized=False,native_execution_allowed=False,default_promoted=False)
    write_new(STAGE/'compiled_asset_binding.json',binding)
    value=dict(schema='zerosis.phase10.requested_render_cache_multicore.current_work.v1',
        status='PASS_PHASE10_REQUESTED_OFFLINE_PARTS_COMPILED_LINKED_ATTESTED_NATIVE_PENDING',
        utc=datetime.now(timezone.utc).isoformat(),scope_numbers=[2,3,4,7],full_engine_goal_complete=False,
        latest_source_matches_linked_candidate=True,prepared_runtime_matches_latest_source=False,actual_runtime_acceptance=False,
        current_host=dict(build_id=identifier,parent_build_id='20261115T121456Z_dbb01a1f4f50',build_result=ref(report),
            executable=build['executable'],prepared_profile=ref(prepared_path),
            independent_attestation=ref(prepared_path.with_name('independent_attestation.json')),
            compiler_dependency_count=build['compiler_dependency_count'],current_source_input_count=len(build['current_source_inputs']),
            frozen_input_count=len(frozen),translation_units=5,compiler_and_linker_warnings=0,required_ui_sidecar_files=154),
        packages=packages,proofs=proofs,compiled_asset_binding=ref(STAGE/'compiled_asset_binding.json'),
        source_manifest=build['menu_suite_component'],
        recorded_compile=dict(first_unattested_launcher=ref(STAGE/'host_build/launcher_interruption.json'),
            readonly_link_failure=ref(STAGE/'retry01_link_failure.json'),
            fresh_plan=ref(STAGE/'host_build_retry02/plan.json'),
            controller_exit=ref(STAGE/'host_build_retry02/controller_exit.json'),
            source_feature_changes_for_retry=0,original_plan_replayed=False),
        retained_prepared_runtime=previous['current_prepared_runtime'],
        retention_reason='Keep the new sealed candidate plus dbb/aa885 as current prepared baseline, prior99b3, recovery4c8f and40a user sessions. The new candidate has no runtime acceptance; retained frozen parent inputs remain current verification dependencies.',
        original_install_mods_settings_saves_default_or_registration_changed=False,
        native_host_sdk_clr_hwnd_gpu_audio_or_game_attempts=0,new_game_runtime_materialized=False,
        scope_results={
            '2':dict(status='OFFLINE_RULE_AND_FORMAT_CORRECTIONS_CONNECTED',
                implemented=['row-vector T*R(0)*Mirror orientation','RGBA8 typeless with UNORM RTV/SRV and LINEAR_CLAMP',
                             'explicit original 128/256/512 full-mip scratch contract'],
                remaining=['original scratch resampling and current halo correspondence','compression and residency','raw/world normalization and original placement comparison']),
            '3':dict(status='OFFLINE_WATER_BLEND_AND_STATIC_SCREEN_INPUT_CONNECTED',
                implemented=['independent original static specscreenmap BC3 11-mip package','water Raw reflection UNORM/WRAP and recovered scene mask',
                             'original OM8 source-alpha RGB/additive alpha','preblend FOW and marker2 single-fog composition','three obsolete full-frame refraction copies removed'],
                remaining=['original reflection camera and plane','wonders/landmarks/ice providers','actual GPU colours and depth']),
            '4':dict(status='COMPILED_COMPONENTS_ONLY_PRODUCTION_SUBMISSION_PENDING',
                implemented=['original forest 90-instance and chroma equations','explicit-basis 4x4 bicubic CPU/HS/DS','explicit-input general RH camera math'],
                remaining=['original compressed GR2 decoding and tree placement stream','actual original bicubic basis and patch scaling','world-camera pose FOV zoom and unit calibration']),
            '7':dict(status='USEFUL_DETERMINISTIC_TERRAIN_WORKERS_CONNECTED',
                implemented=['bounded persistent 0/2/4-worker preparation','immutable shared inputs and per-index output','owner-only D3D upload/publication','scalar equality/failure/FP-mode guards'],
                remaining=['real game multicore stability and measured frame/turn improvement'])},
        superseded_inferences=['Phase8 terrain t9 was incorrectly assigned to water Raw reflection; owner+8 proves static specscreenmap.',
            'Original Raw scene callbacks are units/wonders/landmarks/ice; terrain/forest inclusion is not inferred.'],
        piece_placement_report='규칙 동등, 배치 동등은 미검증',
        checks=dict(cpu_mode_total=703353,optimization_mode_repeats_included=True,new_strict_shader_entry_points=13,
            original_static_claims=68,actual_compiler_command_phases=12),
        protection=dict(before=ref(STAGE/'protection_before.json.gz'),precompile=ref(STAGE/'protection_precompile.json'),after_pending=True),
        storage=dict(before=ref(STAGE/'storage_before.json'),precompile=ref(STAGE/'storage_precompile.json'),after_pending=True,
            cleanup_summary=ref(STAGE/'cleanup_summary.json'),new_asset_packages=1,new_asset_bytes=1398304,
            existing_asset_package_copies=0,full_project_copies_created=0,new_full_runtime_bundles=0,
            confirmed_disposable_bytes=0,threshold_bytes=10*1024**3))
    write_new(output,value)
    docs=(f"# 선택 작업 2·3·4·7 오프라인 구현 — 2026-11-16\n\n현재 컴파일 후보는 `{identifier}`다. "
        '전체 5개 번역 단위의 실제 컴파일·링크와 독립 파일 검증을 통과했으며 경고는 0개다. '
        'Host·GameCore·CLR·창·GPU·음향·게임 실행은 0회다.\n\n'
        '| 항목 | 구현·검증한 부분 | 남은 부분 |\n|---|---|---|\n'
        '| 2 지형·캐시 | 원본 방향 행렬 교정, typeless/UNORM 보기와 샘플러 연결, 원본 품질·밉 계산 계약 | scratch 재표본화·압축·상주·세계 단위 및 실제 배치 대조 |\n'
        '| 3 물·반사 | 정적 specscreenmap과 물 Raw 분리, 원본 투명도 혼합·혼합 전 안개, 이중 안개 차단, 불필요한 화면 복사 3개 제거 | 반사 카메라·평면과 불가사의/시설/얼음 제공자·GPU 수락 |\n'
        '| 4 숲·곡면·카메라 | 90개 인스턴스/색 수식, 명시 기저 쌍삼차 HS/DS, 일반 RH 카메라 계산 부품 | 압축 GR2·원본 배치/기저/세계 카메라 입력 확보 후 생산 렌더 연결 |\n'
        '| 7 멀티코어 | 지형 65×65 정점의 0·2·4 작업자와 소유 스레드 공개, 직렬 전체 44바이트 대조·예외·FP 검사 | 실제 게임 안정성과 성능 실측 |\n\n'
        '검사는 CPU 모드별 합계 703,353건(O2/Od 반복 포함), 새 strict 셰이더 13개, 원본 정적 주장 68개다. '
        '숲·곡면·카메라 부품의 생산 렌더 제출은 활성화하지 않았다. 규칙 동등, 배치 동등은 미검증이다.\n\n'
        '**이전 분석 정정:** 객체 기준 주소의 8바이트 차이 때문에 8단계에서 t9 자원을 잘못 연결했다. '
        '지형 최종 t9는 정적 `specscreenmap.dds`(UNORM/CLAMP), 물 ReflectionMap은 동적 Raw(UNORM/WRAP)다. '
        '이전 증거는 당시 기록으로 보존하고 이번 owner 정정 계약이 해석을 대체한다.\n\n'
        '기존 다섯 자산 묶음은 복제·수정하지 않았고 1,398,304바이트의 조명 보조 묶음 하나만 추가했다. '
        '다음 격리 실행 묶음에는 `ZEROSIS_SCREEN_LIGHT_ASSETS` 경로와 새 패키지 SHA를 함께 연결해야 한다. '
        '현재 보관 중인 aa885 실행 묶음은 직전 dbb 후보로 유지되며 새 후보의 실행 묶음 연동은 아직 하지 않았다.\n\n'
        '설치본·MODS·설정·사용자 저장·기본 실행·전역 등록·저장 ABI는 바꾸지 않았다. '
        'Source/Tests 변경은 필요한 파일만 gzip으로 보존하고 재생성 가능한 검사·빌드 중간물은 경로·ID·SHA 영수증 뒤 제거했다. '
        '보관량 전후와 정리 총계는 최종 근거 `evidence/world_terrain_original/phase10/current_work.json`의 storage 항목을 따른다.\n')
    (PROJECT/'docs/TERRAIN_OFFLINE_PHASE10.md').write_text(docs,encoding='utf8')
    path=PROJECT/'docs/CLAUDE_HANDOFF.md';head,tail=path.read_text('utf8').split('\n',1)
    entry=(f'## 선택 작업 2·3·4·7 오프라인 통합 — 2026-11-16\n\n최신 컴파일 후보는 `{identifier}`이며 실제 5TU 컴파일·링크/독립 attestation 경고0이다. '
        '방향 행렬·법선 UNORM 보기를 교정하고 지형 t9=정적 specscreenmap/물 Raw의 원본 자원·샘플러를 분리했다. '
        '기존 8단계 t9=Raw 추론은 owner+8 누락으로 폐기했다. 원본 물 blend/FOW 선후·단일 안개, 지형 정점 0/2/4 작업자를 연결했다. '
        '숲·쌍삼차·일반 RH 카메라는 CPU/Shader 부품만이며 원본 GR2/배치/basis/world camera가 없어 생산 제출 미연결이다. '
        'CPU 모드합계703,353/strict13/원본68 PASS, Host/SDK/CLR/창/GPU/음향/게임0회다. '
        '기존5팩/aa885·99b3·4c8f·40a 사용자 저장/기본 실행을 보존했고 새팩1,398,304B 하나만 추가했다. '
        '새 runtime은 미생성이고 다음 연동 때 ZEROSIS_SCREEN_LIGHT_ASSETS와 해당 SHA팩을 함께 넣어야 한다. '
        '상세는 docs/TERRAIN_OFFLINE_PHASE10.md, 현재 상태는 evidence/world_terrain_original/phase10/current_work.json이다.\n\n')
    path.write_text(head+'\n\n'+entry+tail.lstrip('\n'),encoding='utf8')
    update_index(value)
    print(json.dumps(dict(status=value['status'],build_id=identifier,cleanup_files=cleanup['deleted_files'],
        cleanup_allocated_bytes=cleanup['released_unique_allocated_bytes'])))


def close():
    path=STAGE/'current_work.json';value=read(path);assert value['storage']['after_pending']
    protection=read(STAGE/'protection_after.json');assert protection['status']=='PASS' and not protection['differences']
    before,after=read(STAGE/'storage_before.json'),read(STAGE/'storage_after.json')
    value['protection'].update(after=ref(STAGE/'protection_after.json'),after_pending=False)
    value['storage'].update(after=ref(STAGE/'storage_after.json'),after_pending=False,
        before_unique_allocated_bytes=before['unique_allocated_bytes'],after_unique_allocated_bytes=after['unique_allocated_bytes'],
        allocated_bytes_change=after['unique_allocated_bytes']-before['unique_allocated_bytes'],
        measurement='Real os.stat identity deduplication; receipt/index writes follow scan; directory/driver allocation excluded.')
    value['utc']=datetime.now(timezone.utc).isoformat();save(path,value);update_index(value)
    print(json.dumps(dict(status=value['status'],allocated_bytes=after['unique_allocated_bytes'],
        delta=value['storage']['allocated_bytes_change'],protected_paths=protection['paths'])))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=('publish','close'));parser.add_argument('--build-id');args=parser.parse_args()
    if args.action=='publish':
        assert args.build_id;publish(args.build_id)
    else:close()
