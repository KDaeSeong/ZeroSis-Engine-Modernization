"""Close the offline water milestone; never create, register or execute a game runtime."""
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
WATER='2ff227dae9d16398e038e8ea33624940a9581e0eb2d37c3891121fae22c25afc'
def read(path):return json.loads(Path(path).read_text('utf8'))
def ref(path):return common.artifact(Path(path).absolute())
def save(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf8')

def publish(identifier):
    assert re.fullmatch(r'\d{8}T\d{6}Z_[0-9a-f]{12}',identifier or '')
    output=STAGE/'current_work.json';assert not output.exists()
    report=PROJECT/'evidence/ui_window_host'/identifier/'build_result.json';build=read(report)
    assert build['host_runtime_executed'] is False and build['gamecore_loaded'] is False
    profile=STAGE/'pair_preparation'/identifier/'prepared_profile.json';prepared=read(profile)
    assert not prepared['native_execution'] and not prepared['globally_registered']
    frozen=menu.frozen_rows(build)
    for name in ('OriginalWaterBinding.h','OriginalWaterShader.h','OriginalWaterModel.h','OriginalWaterState.h',
        'OriginalWaterPackage.h','OriginalWaterBridge.h','OriginalWaterGpuTypes.inc','OriginalWaterGpu.inc'):
        path=PROJECT/'Source/Presentation'/name;item=ref(path)
        matches=[row for row in frozen.values() if common.key(row['origin'])==common.key(path)]
        assert len(matches)==1 and matches[0]['sha256']==item['sha256']
    packages={}
    for name,directory,digest,leaf in (('terrain','OriginalTerrainAssets',TERRAIN,'terrain-assets.bin'),
        ('fog','OriginalFogAssets',FOG,'fog-assets.bin'),('water','OriginalWaterAssets',WATER,'water-assets.bin')):
        packages[name]=ref(PROJECT/'Build'/directory/digest/leaf);assert packages[name]['sha256']==digest
    proofs={name:ref(STAGE/path) for name,path in (
        ('assets','assets/completion.json'),('package_reader','package_tests/attempt1/result.json'),
        ('model','model/current_model.json'),('state','state/current_state.json'),('bridge','bridge/attempt2/result.json'),
        ('cache','cache_cpu/regression_result.json'),('shader','shader/current.json'),
        ('sdk_contract','semantics/sdk_river_contract.json'),('original_shader_contract','semantics/shader_semantics.json'),
        ('coast_contract','semantics/coast_text_contract.json'),('integration','review/integration_review.json'),('plan','host_build/plan_review.json'))}
    for name,item in proofs.items():assert read(item['path'])['status'].startswith('PASS'),name
    binding=dict(schema='zerosis.original_water.phase3.compiled_asset_binding.v1',host=build['executable'],
        compiled_binding=ref(PROJECT/'Source/Presentation/OriginalWaterBinding.h'),packages=packages,
        water_manifest=ref(Path(packages['water']['path']).with_name('water-assets.manifest.json')),
        explicit_environment={'ZEROSIS_WATER_ASSETS':packages['water']['path'],'ZEROSIS_FOG_ASSETS':packages['fog']['path']},
        terrain_requirement='Future isolated runtime must provide the existing V2 terrain-assets.bin beside its executable.',
        exact_outer_and_blob_sha256=True,new_terrain_or_fog_copy=False,unused_lean_bytes_not_packaged=3932298,
        runtime_materialized=False,native_launch_allowed=False,default_promoted=False,full_engine_goal_complete=False)
    save(STAGE/'compiled_asset_binding.json',binding)
    value=dict(schema='zerosis.original_water.phase3.current_work.v1',utc=datetime.now(timezone.utc).isoformat(),
        status='PASS_PHASE3_WATER_OFFLINE_CANDIDATE_COMPILE_LINK_NATIVE_GPU_PENDING',
        completed_scope='Requested offline water/shore/river candidate: original asset and SDK/shader analysis, CPU topology/geometry/bridge checks, colour-only integration, actual compile/link.',
        full_goal_redefined=False,full_engine_goal_complete=False,
        current_host=dict(build_id=identifier,parent_build_id='20261115T034310Z_77ed882144d1',build_result=ref(report),
            executable=build['executable'],prepared_profile=ref(profile),
            independent_attestation=ref(STAGE/'pair_preparation'/identifier/'independent_attestation.json'),
            compiler_dependency_count=build['compiler_dependency_count'],current_source_input_count=len(build['current_source_inputs']),
            frozen_input_count=len(frozen),compiler_and_linker_warnings=0,translation_units=5,embedded_ui_payloads=74,
            required_ui_sidecar_files=154,default_or_global_registration_changed=False),
        packages=packages,compiled_asset_binding=ref(STAGE/'compiled_asset_binding.json'),proofs=proofs,
        source_manifest=build['menu_suite_component'],calibration_candidates=ref(STAGE/'calibration_notes.json'),
        implemented=[
            'Six existing SDK river accessors captured only for explored plots; exact canonical E/SE/SW ownership/flow. No SDK ABI/save changes or invented lake query.',
            'Exploration-safe hex water fans, shared coast/river ribbons, source profile interpolation, unknown-height callback denial and bounded adaptive2M-vertex geometry.',
            'One25-role24-blob SHA-sealed5,180,388B water package; original14DDS/13styles/9profiles; terrain/fog reused, unusedLEAN raw3,932,298B omitted.',
            'Confirmed depth-lookup and four UV symmetries with explicit candidate simple reflection/bump/foam/bank shading and flow calibration.',
            'Global water then coast then river layers before units/FOW; colour-only RGB blend, zero depth writes, original integer picking/contours/input-generation path retained.',
            'One current geometry per asset/atlas/water-state identity; visibility/time/camera reuse static geometry; independent unit/fog/water clocks.'],
        native_host_sdk_clr_hwnd_gpu_audio_or_game_attempts=0,new_game_runtime_materialized=False,
        latest_source_matches_linked_candidate=True,prepared_runtime_matches_latest_source=False,
        retained_prepared_runtime='Build/InteractiveGameRuntime/20261115T011241Z_4c8fd55e99db',
        retained_user_session='Build/InteractiveGameRuntime/20261108T003146Z_40a8030edf08/sessions/350dd3b9ceb408a391b5a8aa63b48301',
        piece_placement_report='규칙 동등, 배치 동등은 미검증',
        remaining=[
            'GPU resource creation/output, colour/depth/ID equality, occlusion, wrap edges and input/UI regression remain held; no screen or real-game proof.',
            'Original constant water plane and height-isoline shoreline, complete LEAN covariance/Gaussian reflection/refraction, coast runtime height/offset and river junction/endcap calibration are not restored by this colour overlay.',
            'Wave speeds, UV scales, widths/lift/profile meander/lighting/alpha are candidates; original visible river-flow timing is unknown and no public lake classification is available.',
            'Original lighting/trees/tessellation/camera, phase-one placement calibration and full gameplay/save/mod/multicore acceptance remain further work.'],
        protection=dict(before=ref(STAGE/'protection_before.json.gz'),precompile=ref(STAGE/'protection_precompile.json'),after_pending=True),
        storage=dict(before=ref(STAGE/'storage_before.json'),precompile=ref(STAGE/'storage_precompile.json'),after_pending=True,
            full_project_copies_created=0,new_terrain_or_fog_packages=0,new_water_packages=1,
            final_build_cleanup=ref(STAGE/'pair_preparation'/identifier/'cleanup_result.json'),confirmed_disposable_bytes=0,threshold_bytes=10*1024**3))
    save(output,value)
    progress=PROJECT/'evidence/save_menu/20261013_original_screen/current_progress.json';index=read(progress)
    index.update(utc=value['utc'],status=value['status'],current_source_working_stage=str(STAGE),current_offline_stage=ref(output),
        latest_source_matches_linked_candidate=True,prepared_runtime_matches_latest_source=False,full_engine_goal_complete=False,
        original_water_phase3_status='OFFLINE_COLOUR_OVERLAY_CANDIDATE_COMPILE_LINK_PASS_ORIGINAL_RENDERER_GPU_COMPARISON_PENDING')
    save(progress,index)
    notes=(f'# 물·해안선·강 3단계 — 오프라인 후보\n\n2026-11-15. 컴파일 Host `{identifier}`. '
        f'보조 패키지 SHA `{WATER}`, 5,180,388바이트·25역할·24고유 원본이다. 기존 지형·안개 팩은 재사용했고, 이번 경로에서 쓰지 않는 LEAN 원문3,932,298바이트는 담지 않았다. '
        '새 게임 실행 묶음·기본 실행 변경·전역 등록은 없고, Host/SDK/CLR/창/GPU/음향/실게임 실행은0회다.\n\n'
        'SDK가 소유하는 E/SE/SW 강변과 흐름을 탐색된 칸에서만 캡처한다. 해안·강은 양쪽 칸이 모두 탐색된 공유변만 사용하며, '
        '미탐색 water/relief/river/flow 값을 검사 단계에서도 읽지 않는다. 공개 IsLake가 없으므로 실제 lake값은false로 유지하고 새 SDK 인터페이스를 만들지 않았다. '
        '수면 육각·해안/강 리본과 원본9개100점 프로필 보간을 연결하고 경계의 미탐색 좌표에는 높이 콜백을 호출하지 않는다.\n\n'
        '전체 물→전체 해안→전체 강 순으로 지형 다음·유닛과 최종 안개 앞에서 색만 덧그린다. 색 목표0 하나·RGB 쓰기·깊이 쓰기0을 사용하며 '
        'R32_UINT 선택 표·지형 깊이·픽셀 윤곽·입력 세대는 기존 경로를 유지한다. 물/안개/유닛 시계는 분리했고, '
        '물 기하는 자산·정제된 아틀라스 객체·물 상태가 바뀔 때만 새로 만든다.\n\n'
        '원본 명령의 수심 좌표 `u=1-saturate(4h)`·LOD0와4종 UV 대칭은 확인했다. '
        '현재 기하는 지형 높이를 따르는 색 덧그림이며 원본의 상수 수면과 다르다. 원본 등고선 해안 추출·LEAN 공분산/Gaussian 반사·전체 굴절/반사·해안 높이/오프셋·강 합류부는 미복원이다. '
        '폭0.12/0.07·lift0.002·프로필 Y의 수평 흔들림 해석·속도·UV배율·단순 Fresnel/광택/알파는 후보이다. '
        '원본 River VS의0.05식은 확인한 PS에서 소비되지 않으므로 원본의 실제 가시 속도라고 부르지 않는다.\n\n'
        'CPU 모델98,318·자산 리더4,491·브리지547,501·캐시245검사를 통과했다. '
        f'최종 strict VS/PS와 C++14다섯 단위 실제 컴파일·링크 경고0, 현재/동결 입력{len(build["current_source_inputs"])}개·컴파일 의존{build["compiler_dependency_count"]}개를 대조했다. '
        '브리지는 원본 knot/중간값8,970개·지도10개·독립 높이65,484개를 대조했고 숨은 입력 NaN/Inf 치환에도 기하가 같았다. '
        '이는 GPU 픽셀·실게임·원본 화면·프레임 성능의 증거가 아니다.\n\n'
        '격자 축256·16384칸·짝수 높이 세로 감싸기·2M 버텍스 상한이며 필요하면 분할 수를 결정적으로 줄인다. '
        '`ZEROSIS_WATER_ASSETS`에 정확한 보조 팩을 명시한 V2 경로만 새 기능을 쓰며 빈 경로는 기존 렌더러이다. '
        '후속 격리 묶음 연동 정보는 `phase3/compiled_asset_binding.json`, 현재 상태·근거·보정 후보는 `phase3/current_work.json`에 있다. '
        '전체 엔진 완료가 아니며, 조각 배치는 **규칙 동등, 배치 동등은 미검증**이다.\n')
    (PROJECT/'docs/WATER_PHASE3_IMPLEMENTATION.md').write_text(notes,encoding='utf8')
    path=PROJECT/'docs/CLAUDE_HANDOFF.md';head,tail=path.read_text('utf8').split('\n',1)
    entry=(f'## 물·해안선·강 3단계 — 2026-11-15\n\n현재 컴파일 후보는 `{identifier}`다. '
        '원본14DDS·13스타일·9프로필과 SDK 공유변으로 색 전용 수면/해안/강 후보를 연결했고 CPU·strict 셰이더·실제 컴파일/링크까지 통과했다. '
        f'새 보조 팩은5,180,388바이트/SHA `{WATER}`이고 지형/안개 팩은 재사용했다. '
        '실게임·창·GPU 실행0회, 4c8f/40a 저장과 기본 실행본을 보존했다. '
        '상수 수면·등고선 해안·완전한 LEAN/반사/굴절은 미복원이며 세부 후보/남은 관문은 `docs/WATER_PHASE3_IMPLEMENTATION.md`, '
        '근거는 `evidence/world_terrain_original/phase3/current_work.json`에 있다.\n\n')
    path.write_text(head+'\n\n'+entry+tail.lstrip('\n'),encoding='utf8')
    path=PROJECT/'docs/WORLD_TERRAIN_ORIGINAL_PLAN.md';text=path.read_text('utf8');marker='## 5. 열린 질문';assert text.count(marker)==1
    text=text.replace(marker,'### 3단계 물·해안선·강 오프라인 기록 (2026-11-15)\n\n원본 자료·SDK 공유변을 사용하는 색 전용 후보와 CPU/셰이더/컴파일·링크를 연결했다. '
        '원본 상수 수면·등고선 해안·전체 LEAN/굴절/반사와 실제 화면은 미검증·미복원으로 남긴다. '
        '상세는 `WATER_PHASE3_IMPLEMENTATION.md`와 `evidence/world_terrain_original/phase3/current_work.json`에 있다.\n\n'+marker,1)
    path.write_text(text,encoding='utf8')
    print(json.dumps(dict(status=value['status'],build_id=identifier,native_attempts=0,runtime_materialized=False)))

def close():
    path=STAGE/'current_work.json';value=read(path);assert value['storage']['after_pending']
    protection=read(STAGE/'protection_after.json');assert protection['status']=='PASS'
    before=read(STAGE/'storage_before.json');after=read(STAGE/'storage_after.json')
    value['protection'].update(after=ref(STAGE/'protection_after.json'),after_pending=False)
    value['proofs']['plan68']=ref(STAGE/'plan_check_receipt.json')
    value['storage'].update(after=ref(STAGE/'storage_after.json'),after_pending=False,cleanup_summary=ref(STAGE/'cleanup_summary.json'),
        before_unique_allocated_bytes=before['unique_allocated_bytes'],after_unique_allocated_bytes=after['unique_allocated_bytes'],
        allocated_bytes_change=after['unique_allocated_bytes']-before['unique_allocated_bytes'],
        measurement='Allocation counted once per real os.stat identity; small receipt/final-index writes follow this scan.')
    save(path,value)
    progress=PROJECT/'evidence/save_menu/20261013_original_screen/current_progress.json';index=read(progress);index['current_offline_stage']=ref(path);save(progress,index)
    print(json.dumps(dict(status='PASS_CLOSED_WATER_PHASE3_OFFLINE',protected=protection['paths'],unique_allocated_bytes=after['unique_allocated_bytes'],
        allocated_bytes_change=value['storage']['allocated_bytes_change'],native_attempts=0)))
if __name__=='__main__':
    cli=argparse.ArgumentParser();cli.add_argument('action',choices=['publish','close']);cli.add_argument('--build-id');args=cli.parse_args()
    if args.action=='publish':publish(args.build_id)
    else:close()
