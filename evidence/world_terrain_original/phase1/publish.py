"""Publish the offline terrain milestone and leave real-engine acceptance explicit."""
from datetime import datetime,timezone
import argparse
import json
from pathlib import Path
import sys

sys.dont_write_bytecode=True
STAGE=Path(__file__).absolute().parent;PROJECT=STAGE.parents[2]
sys.path.insert(0,str(PROJECT/'tools'))
import build_exit_confirm_host as common
import retained_menu_suite_host_input as menu

BUILD='20261115T024443Z_8470b8d966f8'
PACKAGE='02104c582759bf0cefb58f97379699e45300eb2a9c6da6fdd3c65d1440cb84e8'
def read(path):return json.loads(Path(path).read_text('utf8'))
def ref(path):return common.artifact(Path(path).absolute())
def save(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf8')

def publish():
    output=STAGE/'current_work.json';assert not output.exists()
    report_path=PROJECT/'evidence/ui_window_host'/BUILD/'build_result.json';build=read(report_path)
    assert ref(report_path)['sha256']=='c2b21c5fc5905b59c5bb5e7e0df5e8626f885bbd85b50b604bbaeeb70dc656f3'
    assert build['host_runtime_executed'] is False and build['gamecore_loaded'] is False
    profile=STAGE/'pair_preparation'/BUILD/'prepared_profile.json';sealed=read(profile)
    assert sealed['native_execution'] is False and sealed['globally_registered'] is False
    package=PROJECT/'Build/OriginalTerrainAssets'/PACKAGE/'terrain-assets.bin'
    package_ref=ref(package);assert package_ref['sha256']==PACKAGE
    proofs={name:ref(STAGE/path) for name,path in (
        ('phase0','review/phase0_plan_check_receipt.json'),('asset_package','assets/result.json'),
        ('cpu_model','model/result.json'),('cpp_package_reader','package_tests/result.json'),
        ('tile_geometry','geometry_tests/result.json'),('default_map_cpu_pipeline','pipeline_tests/current/result.json'),
        ('hlsl_compile','shaders/retry01/result.json'),('gpu_source_contract','review/gpu_integration_review.json'))}
    for name in ('asset_package','cpu_model','cpp_package_reader','tile_geometry','default_map_cpu_pipeline','hlsl_compile','gpu_source_contract'):
        assert str(read(proofs[name]['path'])['status']).startswith('PASS'),name
    binding=dict(schema='zerosis.original_terrain.phase1.compiled_asset_binding.v1',host=build['executable'],
        compiled_binding_source=ref(PROJECT/'Source/Presentation/OriginalTerrainBinding.h'),terrain_package=package_ref,
        terrain_manifest=ref(package.with_name('terrain-assets.manifest.json')),
        decoder='ZSTERR02 exact outer SHA and every embedded blob SHA; V1 remains a separate retained path',
        native_launch_allowed=False,runtime_materialized=False,default_promoted=False,full_engine_goal_complete=False)
    save(STAGE/'compiled_asset_binding.json',binding)
    value=dict(schema='zerosis.original_terrain.phase1.current_work.v1',utc=datetime.now(timezone.utc).isoformat(),
        status='PASS_PHASE1_OFFLINE_IMPLEMENTATION_COMPILE_LINK_NATIVE_GPU_PENDING',
        full_goal_redefined=False,full_engine_goal_complete=False,completed_scope='Requested phase-one implementation, CPU component checks, shader compile and actual C++ compile/link only.',
        placement_report='규칙 동등, 배치 동등은 미검증',
        implemented=[
            'Global64texel/hex heightfield and row-ID material atlas from original299piece library; MSVCR90 shuffle and level4-to1 greedy placement with explicit orientation-order candidate.',
            'Detached initial seed/natural-wonder metadata; hidden fields excluded before cell generation/stamping/normal/top8/weight calculations.',
            'Normalized5x5 weights, top8 expanded slots without selected-slot renormalization, per-normal Z-up projection and scale*.33/.66, alpha8 raw-UNORM squared diffuse/specular mixing.',
            'Independent fragment tile ownership drives R32_UINT picking; current unit animation/retained input-generation checks and separate cache ownership remain.',
            'One SHA-sealed V2 package, camera-independent atlas reuse and weak per-chunk GPU lookup; explicit V2 path retains V1 and all current/default/user bundles.'],
        current_host=dict(build_id=BUILD,parent_build_id='20261115T005626Z_256252d8abe3',parent_build_report=build['baseline_build'],
            executable=build['executable'],build_result=ref(report_path),prepared_profile=ref(profile),
            independent_attestation=ref(STAGE/'pair_preparation'/BUILD/'independent_attestation.json'),
            compiler_dependency_count=build['compiler_dependency_count'],current_source_input_count=len(build['current_source_inputs']),
            frozen_input_count=len(menu.frozen_rows(build)),compiler_and_linker_warnings=0,
            pipeline_attempts=2,completed_compilation_sets=1,prior_failure='Input-freeze path length only; no failed object compilation.',
            embedded_ui_payloads=74,required_ui_sidecar_files=154,default_or_global_registration_changed=False),
        terrain_package=package_ref,compiled_asset_binding=ref(STAGE/'compiled_asset_binding.json'),proofs=proofs,
        source_manifest=ref(STAGE/'host_build/source_manifest2.json'),
        calibration_candidates=ref(STAGE/'calibration_notes.json'),
        further_format_candidates='RGBA16F squared-specular and R16F material-height targets, candidate fixed lighting/sRGB final encode; retail cache formats and complete lighting pass are not acceptance-proven.',
        retained_prepared_runtime='Build/InteractiveGameRuntime/20261115T011241Z_4c8fd55e99db',
        retained_user_session='Build/InteractiveGameRuntime/20261108T003146Z_40a8030edf08/sessions/350dd3b9ceb408a391b5a8aa63b48301',
        native_host_sdk_clr_hwnd_gpu_audio_or_game_attempts=0,new_game_runtime_materialized=False,
        latest_source_matches_linked_candidate=True,prepared_runtime_matches_latest_source=False,
        remaining=[
            'Real GPU color/height/picking comparison and regression, actual original placement comparison and live frame-time/CPU/VRAM measurement remain held.',
            'Orientation multiplication order, possible prior virtual-call rand consumption, height/UV calibration, top8 tie order, missing-height fallback and cache format are explicit candidates.',
            'FOW/cloud/LUT/distance fog, original lighting/tessellation/water/river/trees/camera and complete gameplay/save/mod/multicore acceptance remain later original-engine work.'],
        protection=dict(before=ref(STAGE/'protection_before.json.gz'),precompile=ref(STAGE/'protection_precompile.json'),after_pending=True),
        storage=dict(before=ref(STAGE/'storage_before.json'),precompile=ref(STAGE/'storage_precompile.json'),after_pending=True,
            full_project_copies_created=0,new_large_terrain_packages=1,
            final_build_cleanup=ref(STAGE/'pair_preparation'/BUILD/'cleanup_result.json'),
            confirmed_disposable_bytes=0,threshold_bytes=10*1024**3))
    save(output,value)
    progress=PROJECT/'evidence/save_menu/20261013_original_screen/current_progress.json';index=read(progress)
    index.update(utc=value['utc'],status=value['status'],current_source_working_stage=str(STAGE),
        current_offline_stage=ref(output),latest_source_matches_linked_candidate=True,
        prepared_runtime_matches_latest_source=False,full_engine_goal_complete=False,
        original_terrain_phase1_status='OFFLINE_IMPLEMENTATION_AND_COMPILE_LINK_PASS_GPU_GAME_COMPARISON_PENDING')
    save(progress,index)
    notes=(f'# 원본 지형 1단계 구현 — 오프라인 검증\n\n'
        f'2026-11-15. 컴파일 Host `{BUILD}`, 패키지 SHA `{PACKAGE}`. 실행 파일과 고정 자산 연결을 확인했으며 새 게임 실행 묶음을 만들거나 기본 실행본을 바꾸지 않았다.\n\n'
        '전역 높이장(육각당64×64텍셀), TerrainDef 행 순서, 조각/RLE·지도 칸·MSVCR90 섞기·탐욕 배치·5×5 커널·청크8재질·투영·alpha8 제곱 공간 혼합을 구현했다. '
        '전체 재질을 정규화한 뒤 top8을 뽑으며 선택8개를 다시 정규화하지 않는다. 미탐색 정보는 셀 생성 전부터 제외하고, 탐색/가시는 구분했다. 타일 선택은 색 재질과 별도 fragment 좌표로 R32_UINT에 쓴다.\n\n'
        '보고 표현은 **규칙 동등, 배치 동등은 미검증**이다. 방향 행렬의 곱셈 순서·사전 rand 소비·빈도 동률 순서는 미확정이다. '
        '높이 기준15300/65535·세계 높이 배율2.3·UV 세계 단위64/육각은 후보이며 원본 런타임 보정값으로 입증하지 않았다. '
        '설치본에도 없는 지브롤터 세부 높이는 선언 미존재를 보존하고 샘플0.5를 후보로 사용했다. NULL 높이0과는 구분했다. '
        '고정 조명·현재 보이지 않는 탐색 지형 밝기0.30은 후속 조명/FOW 단계 전까지 유지했다. 반사RGBA16F·재질높이R16F 출력 형식도 원본 일치의 증거가 아니다.\n\n'
        'CPU 모델37,999단언, 패키지 C++613검사, 기하52,877단언(정수육각 참조23,068점), 실제40×24 입력3종과2560×1536아틀라스 불변성 검사를 통과했다. '
        '40×24 CPU 콘솔은2.01초·최대 작업 집합203.9MiB로384MiB 한도 안이었다. 이는 GPU/전체 게임 성능 수치가 아니다. '
        f'VS/PS 엄격 컴파일과 실제 C++14다섯 단위 컴파일·링크는 최종 경고0, 현재/동결848개·컴파일 의존595개를 대조했다.\n\n'
        'Atlas64M텍셀·축256/16384칸·화면24M삼각형으로 제한하고 홀수 높이의 세로 감싸기는 명시 거부했다. '
        '실제 GPU 색/높이/ID 대조, 원본 배치·화면, 게임·저장·모드·멀티코어·성능은 미검증이다. FOW 구름/LUT/거리 안개는2단계, 원본 조명/테셀레이션/물/강/나무/카메라는 후속 범위다.\n\n'
        '근거와 현재 상태는 `evidence/world_terrain_original/phase1/current_work.json`, 각 model/package_tests/geometry_tests/pipeline_tests/shaders 결과에 있다. '
        'Source→고정 입력→링크 결과와 자산 SHA를 보존했고 원본 설치본·MODS·설정·사용자 저장·전역 등록은 변경하지 않았다.\n')
    (PROJECT/'docs/TERRAIN_PHASE1_IMPLEMENTATION.md').write_text(notes,encoding='utf8')
    handoff=PROJECT/'docs/CLAUDE_HANDOFF.md';text=handoff.read_text('utf8');head,tail=text.split('\n',1)
    entry=(f'## 원본 지형 1단계 — 2026-11-15\n\n'
        f'현재 컴파일 후보는 `{BUILD}`, 새 지형은 ZSTERR02/SHA `{PACKAGE}`이다. '
        '오프라인 구현·부품검사·실제 컴파일·링크까지 완료했고 Host/SDK/CLR/창/GPU/음향/게임 실행은0회다. '
        '새 V2 게임 실행 묶음은 아직 만들지 않았으며 직전 준비본4c8f와40a 사용자 세션을 보존했다. '
        '**규칙 동등, 배치 동등은 미검증**이며 보정 후보·남은 관문은 `docs/TERRAIN_PHASE1_IMPLEMENTATION.md`에 명시했다. '
        '기록은 `evidence/world_terrain_original/phase1/current_work.json`이다.\n\n')
    handoff.write_text(head+'\n\n'+entry+tail.lstrip('\n'),encoding='utf8')
    plan=PROJECT/'docs/WORLD_TERRAIN_ORIGINAL_PLAN.md';text=plan.read_text('utf8')
    marker='## 5. 열린 질문';assert text.count(marker)==1
    text=text.replace(marker,'### 1단계 구현 기록 (2026-11-15)\n\n오프라인 구현·부품검사·컴파일·링크 결과는 `TERRAIN_PHASE1_IMPLEMENTATION.md`와 `evidence/world_terrain_original/phase1/current_work.json`에 있다. 1절은 유지된 V1 후보의 설명이고 새 V2 경로는 전역 격자를 사용한다. 실제 GPU/원본 화면 대조는 보류다. 미확정 높이·UV 배율·지브롤터 대체값·빈도 동률·캐시 형식은 원본 규칙과 분리한 후보이며 **규칙 동등, 배치 동등은 미검증**으로 보고한다.\n\n'+marker,1)
    plan.write_text(text,encoding='utf8')
    print(json.dumps(dict(status=value['status'],build_id=BUILD,current_inputs=848,native_attempts=0,runtime_materialized=False)))

def close():
    path=STAGE/'current_work.json';value=read(path);assert value['storage']['after_pending']
    protection=read(STAGE/'protection_after.json');assert protection['status']=='PASS'
    before=read(STAGE/'storage_before.json');after=read(STAGE/'storage_after.json')
    value['protection'].update(after=ref(STAGE/'protection_after.json'),after_pending=False)
    cleanup=STAGE/'cleanup_failed_freeze/result.json';assert cleanup.is_file()
    value['storage'].update(after=ref(STAGE/'storage_after.json'),after_pending=False,
        failed_snapshot_cleanup=ref(cleanup),before_unique_allocated_bytes=before['unique_allocated_bytes'],
        after_unique_allocated_bytes=after['unique_allocated_bytes'],allocated_bytes_change=after['unique_allocated_bytes']-before['unique_allocated_bytes'],
        measurement='File allocation counted once per real os.stat identity; receipt creation and final small record writes follow this scan.')
    save(path,value)
    progress=PROJECT/'evidence/save_menu/20261013_original_screen/current_progress.json';index=read(progress);index['current_offline_stage']=ref(path);save(progress,index)
    print(json.dumps(dict(status='PASS_CLOSED_TERRAIN_PHASE1_OFFLINE',protected=protection['paths'],
        unique_allocated_bytes=after['unique_allocated_bytes'],allocated_bytes_change=value['storage']['allocated_bytes_change'],native_attempts=0)))

if __name__=='__main__':
    cli=argparse.ArgumentParser();cli.add_argument('action',choices=['publish','close']);args=cli.parse_args()
    if args.action=='publish':publish()
    else:close()
