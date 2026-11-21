"""Record the compiled offline FOW milestone without creating or launching a runtime."""
from datetime import datetime,timezone
import argparse,json,re,sys
from pathlib import Path
sys.dont_write_bytecode=True
STAGE=Path(__file__).absolute().parent;PROJECT=STAGE.parents[2]
sys.path.insert(0,str(PROJECT/'tools'))
import build_exit_confirm_host as common
import retained_menu_suite_host_input as menu

TERRAIN='02104c582759bf0cefb58f97379699e45300eb2a9c6da6fdd3c65d1440cb84e8'
FOG='42ae12554e1514dd48a9a5df25f47b4280d22d180dff29d169c602334e879bcc'
def read(path):return json.loads(Path(path).read_text('utf8'))
def ref(path):return common.artifact(Path(path).absolute())
def save(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf8')

def publish(identifier):
    assert re.fullmatch(r'\d{8}T\d{6}Z_[0-9a-f]{12}',identifier or '')
    output=STAGE/'current_work.json';assert not output.exists()
    report_path=PROJECT/'evidence/ui_window_host'/identifier/'build_result.json';build=read(report_path)
    assert build['host_runtime_executed'] is False and build['gamecore_loaded'] is False
    profile=STAGE/'pair_preparation'/identifier/'prepared_profile.json';sealed=read(profile)
    assert sealed['native_execution'] is False and sealed['globally_registered'] is False
    terrain=PROJECT/'Build/OriginalTerrainAssets'/TERRAIN/'terrain-assets.bin'
    fog=PROJECT/'Build/OriginalFogAssets'/FOG/'fog-assets.bin'
    assert ref(terrain)['sha256']==TERRAIN and ref(fog)['sha256']==FOG
    frozen=menu.frozen_rows(build)
    for name in ('OriginalFogBinding.h','OriginalTerrainBinding.h','OriginalFogGpu.inc','OriginalFogShader.h'):
        path=PROJECT/'Source/Presentation'/name;row=ref(path)
        matches=[r for r in frozen.values() if common.key(r['origin'])==common.key(path)]
        assert len(matches)==1 and matches[0]['sha256']==row['sha256']
    proofs={name:ref(STAGE/path) for name,path in (
        ('assets','assets/completion.json'),('cpu_model','model/current_model.json'),
        ('model_contract','model/model_contract.json'),('cpu_package','package_tests/attempt1/result.json'),
        ('cpu_state','state/cpu/result.json'),('cache_regression','cache_cpu/regression_result.json'),
        ('shaders','shader/current.json'),('independent_integration','review/integration_asset_review_retry01.json'),
        ('distance_bytecode','review/exact_distance_followup.json'),('build_plan','host_build/plan_review_retry01.json'))}
    for name,row in proofs.items():assert read(row['path'])['status'].startswith('PASS'),name
    binding=dict(schema='zerosis.original_fog.phase2.compiled_asset_binding.v1',host=build['executable'],
        terrain_binding_source=ref(PROJECT/'Source/Presentation/OriginalTerrainBinding.h'),terrain_package=ref(terrain),
        fog_binding_source=ref(PROJECT/'Source/Presentation/OriginalFogBinding.h'),fog_package=ref(fog),
        fog_manifest=ref(fog.with_name('fog-assets.manifest.json')),
        explicit_environment={'ZEROSIS_FOG_ASSETS':str(fog)},
        terrain_requirement='V2 terrain-assets.bin resolved inside a future isolated runtime; original terrain package reused by identity/SHA.',
        decoder='Exact outer package SHA256 plus every embedded raw blob SHA256, complete bounded DDS mips and candidate TGA colour-key volume.',
        native_launch_allowed=False,runtime_materialized=False,default_promoted=False,full_engine_goal_complete=False)
    save(STAGE/'compiled_asset_binding.json',binding)
    value=dict(schema='zerosis.original_fog.phase2.current_work.v1',utc=datetime.now(timezone.utc).isoformat(),
        status='PASS_PHASE2_OFFLINE_IMPLEMENTATION_COMPILE_LINK_NATIVE_GPU_PENDING',
        full_goal_redefined=False,full_engine_goal_complete=False,
        completed_scope='Requested phase-two fog implementation, controlled CPU checks, shader compilation and actual C++ compile/link only.',
        implemented=[
            'State-only canonical exploration/visibility mask with smooth boundaries, per-axis wrapping and exact unknown-colour denial.',
            'Pinned original three cloud tiles, flowfield, FX_Fog and simple candidate motion; independent fog clock preserves unit animation opt-in.',
            'Original R replacement blend and R*(1-B) direct-RGB 3D LUT, asset-supported candidate32-cubed colour-key decoding.',
            'Original exponential distance/height equation and FogRamp.R/FogColor.csv with explicit candidate runtime calibration and finite horizontal-ray policy.',
            'Colour-only post-pass after ground/visible units before UI; integer plot ID/metadata/cache and retained-input-generation contracts preserved.',
            'One supplemental8,184,971-byte package; phase-one112,874,723-byte terrain reused; no runtime or default promotion.'],
        current_host=dict(build_id=identifier,parent_build_id='20261115T024443Z_8470b8d966f8',
            executable=build['executable'],build_result=ref(report_path),prepared_profile=ref(profile),
            independent_attestation=ref(STAGE/'pair_preparation'/identifier/'independent_attestation.json'),
            compiler_dependency_count=build['compiler_dependency_count'],current_source_input_count=len(build['current_source_inputs']),
            frozen_input_count=len(frozen),compiler_and_linker_warnings=0,embedded_ui_payloads=74,required_ui_sidecar_files=154,
            default_or_global_registration_changed=False),
        terrain_package=ref(terrain),fog_package=ref(fog),compiled_asset_binding=ref(STAGE/'compiled_asset_binding.json'),
        proofs=proofs,source_manifest=build['menu_suite_component'],calibration_candidates=ref(STAGE/'calibration_notes.json'),
        placement_report='규칙 동등, 배치 동등은 미검증',
        retained_prepared_runtime='Build/InteractiveGameRuntime/20261115T011241Z_4c8fd55e99db',
        retained_user_session='Build/InteractiveGameRuntime/20261108T003146Z_40a8030edf08/sessions/350dd3b9ceb408a391b5a8aa63b48301',
        native_host_sdk_clr_hwnd_gpu_audio_or_game_attempts=0,new_game_runtime_materialized=False,
        latest_source_matches_linked_candidate=True,prepared_runtime_matches_latest_source=False,
        remaining=[
            'Real GPU output/resource creation, mask edges, inverse-projection precision, exact tile ID/picking equality and full UI regression remain held.',
            'Original CPU FOW channel construction, mask resolution/kernel/samplers, FluidFOW simulation, LUT loader and runtime distance constants remain candidate-equivalence questions.',
            'Original phase-one piece placement/height calibration, lighting/tessellation/water/river/trees/camera, full gameplay/save/mod/multicore acceptance remain outside this offline milestone.'],
        protection=dict(before=ref(STAGE/'protection_before.json.gz'),precompile=ref(STAGE/'protection_precompile.json'),after_pending=True),
        storage=dict(before=ref(STAGE/'storage_before.json'),precompile=ref(STAGE/'storage_precompile.json'),after_pending=True,
            full_project_copies_created=0,new_large_terrain_packages=0,new_supplemental_fog_packages=1,
            final_build_cleanup=ref(STAGE/'pair_preparation'/identifier/'cleanup_result.json'),
            confirmed_disposable_bytes=0,threshold_bytes=10*1024**3))
    save(output,value)
    progress=PROJECT/'evidence/save_menu/20261013_original_screen/current_progress.json';index=read(progress)
    index.update(utc=value['utc'],status=value['status'],current_source_working_stage=str(STAGE),current_offline_stage=ref(output),
        latest_source_matches_linked_candidate=True,prepared_runtime_matches_latest_source=False,full_engine_goal_complete=False,
        original_fog_phase2_status='OFFLINE_IMPLEMENTATION_AND_COMPILE_LINK_PASS_GPU_GAME_COMPARISON_PENDING')
    save(progress,index)
    notes=(f'# 전장의 안개 2단계 구현 — 오프라인 검증\n\n2026-11-15. 컴파일 Host `{identifier}`. '
        f'안개 패키지 SHA `{FOG}`(8,184,971바이트), 지형 SHA `{TERRAIN}`(기존 파일 재사용). '
        '새 게임 실행 묶음·기본 실행 변경·전역 등록은 없고, Host/SDK/CLR/창/GPU/음향/실게임 실행은0회다.\n\n'
        '탐색·가시 상태만 정규화한 마스크를 만들고 경계를 흐린다. 미탐색 칸은 정확한 칸 소유 판정으로 지형색과 LUT 읽기를 막으므로 '
        '흐린 R이 양수여도 숨은 재질을 드러내지 않는다. 구름3장·흐름장·FX_Fog를 쓴 단순 후보 흐름을 연결했다. '
        '안개와 유닛 시계를 분리해 구름만 켰을 때 유닛 애니메이션 옵션을 바꾸지 않는다.\n\n'
        '원본 명령의 `lerp(base,terrain,R)`→`lerp(C,LUT(C.rgb),R*(1-B))`와 거리·높이 지수식·FogRamp.R·FogColor.csv를 적용했다. '
        '지형·현재 보이는 유닛을 그린 다음 UI 앞에서 색만 합성한다. R32_UINT 선택 표·현재 입력 세대·캐시된 픽셀 윤곽은 별도로 보존한다. '
        '마스크는 탐색·가시 변화 때만 업로드하고, 시간만 흐를 때 지형 아틀라스·ID 읽기·전체 윤곽을 재계산하지 않는다.\n\n'
        '16텍셀/육각·5탭 가우스·RGBA8 반올림·채널 해석·샘플러·색 키32³ 배치·단순 구름 합성·거리 상수·기존 카메라는 후보이다. '
        '거리 수평 광선의 유한 극한 가드도 명시적 안전 정책이다. 원본 FluidFOW 시뮬레이션이나 원본 화면 일치를 확정하지 않는다. '
        '세부는 `phase2/calibration_notes.json`, 계산 근거는 `phase2/model/model_contract.json`과 `phase2/review/exact_distance_followup.json`이다.\n\n'
        '순수 CPU 모델111,489·상태819,514·패키지164,414·기존 캐시179검사와 strict VS/PS 두 쌍을 통과했다. '
        f'C++14 다섯 단위를 실제 컴파일·링크했고 현재/동결 입력은{len(build["current_source_inputs"])}개, 컴파일 의존은{build["compiler_dependency_count"]}개다. '
        '경고는0개이며 이것은 GPU 출력·성능·실게임 승인의 증거가 아니다.\n\n'
        '`ZEROSIS_FOG_ASSETS`는 명시적으로 고른 보조 패키지만 읽는 코드 경로다. 빈 값은 기존 경로이며 V2 지형과 고정된 안개 SHA가 함께 필요하다. '
        '후속 격리 실행 묶음에 연동할 정보를 `phase2/compiled_asset_binding.json`에 고정했다. 실행 검증 보류는 계속 유지된다. '
        '전체 상태는 `phase2/current_work.json`에 있다. 원본 조각 배치는 **규칙 동등, 배치 동등은 미검증**이다.\n')
    (PROJECT/'docs/FOG_PHASE2_IMPLEMENTATION.md').write_text(notes,encoding='utf8')
    handoff=PROJECT/'docs/CLAUDE_HANDOFF.md';text=handoff.read_text('utf8');head,tail=text.split('\n',1)
    entry=(f'## 전장의 안개 2단계 — 2026-11-15\n\n현재 컴파일 후보는 `{identifier}`다. '
        '마스크·구름 단순 흐름·색 변환·거리 안개를 색 전용 패스로 연결했고 오프라인 부품검사와 실제 컴파일·링크까지 통과했다. '
        f'지형 V2는 재사용하고 안개 SHA `{FOG}` 한 묶음만 추가했다. '
        '실게임·창·GPU 실행0회, 기존4c8f/40a 사용자 세션을 보존했고 새 게임 실행 묶음·기본 실행 변경은 없다. '
        '채널·마스크·LUT 로더·구름 흐름·거리 보정은 후보이며 상세와 남은 관문은 `docs/FOG_PHASE2_IMPLEMENTATION.md`, '
        '근거는 `evidence/world_terrain_original/phase2/current_work.json`에 있다.\n\n')
    handoff.write_text(head+'\n\n'+entry+tail.lstrip('\n'),encoding='utf8')
    plan=PROJECT/'docs/WORLD_TERRAIN_ORIGINAL_PLAN.md';text=plan.read_text('utf8');marker='## 5. 열린 질문';assert text.count(marker)==1
    text=text.replace(marker,'### 2단계 구현 기록 (2026-11-15)\n\n마스크·구름 단순 흐름·원본 색 혼합/LUT·거리 안개를 색 전용 패스로 연결했다. '
        'CPU·strict 셰이더·C++14 컴파일/링크를 통과했으며 실게임·GPU·화면 대조는 보류다. '
        '확정 수식과 후보 마스크/샘플러/구름/LUT 로더/거리 보정의 구분은 `FOG_PHASE2_IMPLEMENTATION.md`와 '
        '`evidence/world_terrain_original/phase2/current_work.json`에 있다.\n\n'+marker,1)
    plan.write_text(text,encoding='utf8')
    print(json.dumps(dict(status=value['status'],build_id=identifier,native_attempts=0,runtime_materialized=False)))

def close():
    path=STAGE/'current_work.json';value=read(path);assert value['storage']['after_pending']
    protection=read(STAGE/'protection_after.json');assert protection['status']=='PASS'
    before=read(STAGE/'storage_before.json');after=read(STAGE/'storage_after.json')
    check=read(STAGE/'plan_check_receipt.json');assert check['status'].startswith('PASS')
    failed=read(STAGE/'cleanup_failed_discovery/result.json');assert failed['root_absent']
    value['current_host'].update(pipeline_attempts=2,completed_compilation_sets=1,
        prior_failure='First /Zs discovery rejected a C4456 new-pointer name collision with an existing V1 scalar; exact rename re-reviewed; no failed object compilation.',
        correction_review=ref(STAGE/'review/integration_asset_review_retry01.json'))
    value['proofs']['plan68']=ref(STAGE/'plan_check_receipt.json')
    value['protection'].update(after=ref(STAGE/'protection_after.json'),after_pending=False)
    value['storage'].update(after=ref(STAGE/'storage_after.json'),after_pending=False,
        retry_precompile=ref(STAGE/'storage_precompile_retry01.json'),
        failed_discovery_cleanup=ref(STAGE/'cleanup_failed_discovery/result.json'),cleanup_summary=ref(STAGE/'cleanup_summary.json'),
        before_unique_allocated_bytes=before['unique_allocated_bytes'],after_unique_allocated_bytes=after['unique_allocated_bytes'],
        allocated_bytes_change=after['unique_allocated_bytes']-before['unique_allocated_bytes'],
        measurement='Allocation counted once per real os.stat identity; receipt creation/final small writes follow scan.')
    save(path,value)
    progress=PROJECT/'evidence/save_menu/20261013_original_screen/current_progress.json';index=read(progress);index['current_offline_stage']=ref(path);save(progress,index)
    print(json.dumps(dict(status='PASS_CLOSED_FOG_PHASE2_OFFLINE',protected=protection['paths'],unique_allocated_bytes=after['unique_allocated_bytes'],
        allocated_bytes_change=value['storage']['allocated_bytes_change'],native_attempts=0)))

if __name__=='__main__':
    cli=argparse.ArgumentParser();cli.add_argument('action',choices=['publish','close']);cli.add_argument('--build-id');args=cli.parse_args()
    if args.action=='publish':publish(args.build_id)
    else:close()
