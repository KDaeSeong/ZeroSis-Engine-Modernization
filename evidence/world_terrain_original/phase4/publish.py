"""Record the offline fixed-surface/optics milestone without launching or promoting a runtime."""
from datetime import datetime,timezone
import argparse,json,re,sys
from pathlib import Path
sys.dont_write_bytecode=True
STAGE=Path(__file__).absolute().parent;PROJECT=STAGE.parents[2]
sys.path.insert(0,str(PROJECT/'tools'))
import build_exit_confirm_host as common
import retained_menu_suite_host_input as menu
def read(path):return json.loads(Path(path).read_text('utf8'))
def ref(path):return common.artifact(Path(path).absolute())
def save(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf8')

def publish(identifier):
    assert re.fullmatch(r'\d{8}T\d{6}Z_[0-9a-f]{12}',identifier or '')
    output=STAGE/'current_work.json';assert not output.exists()
    report=PROJECT/'evidence/ui_window_host'/identifier/'build_result.json';build=read(report)
    assert not build['host_runtime_executed'] and not build['gamecore_loaded']
    profile=STAGE/'pair_preparation'/identifier/'prepared_profile.json';prepared=read(profile)
    assert not prepared['native_execution'] and not prepared['globally_registered']
    frozen=menu.frozen_rows(build)
    names=['OriginalWaterSurfaceBinding.h','OriginalWaterSurfaceModel.h','OriginalWaterSurfaceShader.h','OriginalWaterSurfaceGpu.inc',
        'OriginalWaterSurfaceGpuTypes.inc','OriginalWaterSurfaceTargets.inc','OriginalWaterReflection.inc','OriginalWaterLeanPackage.h',
        'OriginalWaterOpticsModel.h','WorldTerrainUnits.inc']
    for name in names:
        path=PROJECT/'Source/Presentation'/name;item=ref(path)
        matches=[row for row in frozen.values() if common.key(row['origin'])==common.key(path)]
        assert len(matches)==1 and matches[0]['sha256']==item['sha256']
    packages={}
    for name,directory,digest,leaf in (
        ('terrain','OriginalTerrainAssets','02104c582759bf0cefb58f97379699e45300eb2a9c6da6fdd3c65d1440cb84e8','terrain-assets.bin'),
        ('fog','OriginalFogAssets','42ae12554e1514dd48a9a5df25f47b4280d22d180dff29d169c602334e879bcc','fog-assets.bin'),
        ('water','OriginalWaterAssets','2ff227dae9d16398e038e8ea33624940a9581e0eb2d37c3891121fae22c25afc','water-assets.bin'),
        ('lean','OriginalWaterLeanAssets','69c6780dbeb5f8605d8231cef944d0ec9392109b6ccc81a9d3b76ae83cfd0ef7','water-lean-assets.bin')):
        packages[name]=ref(PROJECT/'Build'/directory/digest/leaf);assert packages[name]['sha256']==digest
    proofs={name:ref(STAGE/path) for name,path in (
        ('assets','assets/lean_completion.json'),('package','package_tests/attempt1/result.json'),
        ('surface_model','model/current_surface.json'),('optics','optics/current.json'),('semantics','semantics/optics_contract.json'),
        ('pipeline','pipeline/cpu/result.json'),('cache','cache_cpu/regression_result.json'),
        ('shaders','shader/completion.json'),('integration','review/integration_review.json'),('build_plan','host_build/plan_review.json'))}
    for name,item in proofs.items():assert read(item['path'])['status'].startswith('PASS'),name
    binding=dict(schema='zerosis.water_surface.phase4.compiled_asset_binding.v1',host=build['executable'],packages=packages,
        compiled_binding=ref(PROJECT/'Source/Presentation/OriginalWaterSurfaceBinding.h'),
        explicit_environment={key:packages[name]['path'] for key,name in (
            ('ZEROSIS_WATER_ASSETS','water'),('ZEROSIS_FOG_ASSETS','fog'),('ZEROSIS_WATER_SURFACE_ASSETS','lean'))},
        terrain_requirement='Existing sealed V2 terrain-assets.bin must be staged beside a future isolated Host; no runtime materialization in this milestone.',
        exact_outer_and_blob_sha256=True,existing_asset_package_copies_created=0,runtime_materialized=False,
        native_launch_allowed=False,default_promoted=False,full_engine_goal_complete=False)
    save(STAGE/'compiled_asset_binding.json',binding)
    value=dict(schema='zerosis.water_surface.phase4.current_work.v1',utc=datetime.now(timezone.utc).isoformat(),
        status='PASS_PHASE4_FIXED_SURFACE_CONTOUR_OPTICS_OFFLINE_COMPILE_LINK_GPU_PENDING',
        completed_scope='Requested offline fixed water surface, height-contour coast, original LEAN reflection operations and isolated scene-refraction candidate; CPU/shader/compile-link only.',
        full_goal_redefined=False,full_engine_goal_complete=False,
        current_host=dict(build_id=identifier,parent_build_id='20261115T043249Z_a0d991ededdd',build_result=ref(report),
            executable=build['executable'],prepared_profile=ref(profile),
            independent_attestation=ref(STAGE/'pair_preparation'/identifier/'independent_attestation.json'),
            compiler_dependency_count=build['compiler_dependency_count'],current_source_input_count=len(build['current_source_inputs']),
            frozen_input_count=len(frozen),compiler_and_linker_warnings=0,translation_units=5,embedded_ui_payloads=74,
            required_ui_sidecar_files=154,default_or_global_registration_changed=False),
        packages=packages,compiled_asset_binding=ref(STAGE/'compiled_asset_binding.json'),proofs=proofs,
        source_manifest=build['menu_suite_component'],calibration_candidates=ref(STAGE/'calibration_notes.json'),
        implemented=[
            'Actual constant-height water geometry clipped against known original heightfield triangles and SDK water hexes; shared exact height crossings generate contour shoreline ribbons under counted adaptive LOD.',
            'Plane writes real depth and exact fragment R32_UINT tile identity; shoreline/rivers write colour only. Surface mode invalidates metadata, and water unit/anchor height uses max(terrain,plane).',
            'Only consumed original WaterBumps LEAN raw added as one3,495,363B package; two16-bit planes with full mip chain, exact signed decode and single scale application.',
            'Original covariance/Gaussian/narrow+wide lobe, unnormalised raw Fresnel, asymmetric four-tap reflection, gamma operations and alpha factor connected with explicit runtime/composite candidates.',
            'Own half-resolution mirror-camera cache draws explored terrain/visible units, clips below plane/unknown, shares prepared unit geometry and preserves main picking/metadata.',
            'Isolated pre-water colour/depth/ID copies feed point-sampled refraction only after positive same-tile ID, behind-plane depth and reconstructed underwater Y; failed guards use public depth tint.',
            'One current offscreen target set/geometry, encoded UNORM surface view, main clip0/reflection clip1, independent presentation clocks and full input-generation path retained.'],
        native_host_sdk_clr_hwnd_gpu_audio_or_game_attempts=0,new_game_runtime_materialized=False,
        latest_source_matches_linked_candidate=True,prepared_runtime_matches_latest_source=False,
        retained_prepared_runtime='Build/InteractiveGameRuntime/20261115T011241Z_4c8fd55e99db',
        retained_user_session='Build/InteractiveGameRuntime/20261108T003146Z_40a8030edf08/sessions/350dd3b9ceb408a391b5a8aa63b48301',
        piece_placement_report='규칙 동등, 배치 동등은 미검증',
        remaining=[
            'Actual GPU resource/format validation, raster colour/depth/ID/occlusion, complete input/CityView/UI regression, performance/VRAM and original screen comparison remain held.',
            'Runtime plane level, header-scale to shader binding, layer weights, light/warp/cache camera/UV/sampler calibration and exact original blend/shadow remain candidates.',
            'Original extra sat(4h)*q2^3 depth-colour term and complete original lighting/cache semantics are not reproduced; no original screen-refraction path was found and the new scene refraction is explicitly a candidate.',
            'Original camera/lighting/trees/tessellation, phase-one piece placement and full gameplay/save/mod/multicore acceptance remain further work.'],
        protection=dict(before=ref(STAGE/'protection_before.json.gz'),precompile=ref(STAGE/'protection_precompile.json'),after_pending=True),
        storage=dict(before=ref(STAGE/'storage_before.json'),precompile=ref(STAGE/'storage_precompile.json'),after_pending=True,
            full_project_copies_created=0,existing_terrain_fog_water_package_copies=0,new_lean_packages=1,
            final_build_cleanup=ref(STAGE/'pair_preparation'/identifier/'cleanup_result.json'),confirmed_disposable_bytes=0,threshold_bytes=10*1024**3))
    save(output,value)
    progress=PROJECT/'evidence/save_menu/20261013_original_screen/current_progress.json';index=read(progress)
    index.update(utc=value['utc'],status=value['status'],current_source_working_stage=str(STAGE),current_offline_stage=ref(output),
        latest_source_matches_linked_candidate=True,prepared_runtime_matches_latest_source=False,full_engine_goal_complete=False,
        original_water_surface_phase4_status='FIXED_SURFACE_CONTOUR_LEAN_REFLECTION_AND_SCENE_REFRACTION_OFFLINE_BUILD_PASS_GPU_ORIGINAL_COMPARISON_PENDING')
    save(progress,index)
    notes=(f'# 고정 수면·등고선·반사·굴절 4단계 — 오프라인 구현\n\n2026-11-15. 컴파일 Host `{identifier}`. '
        '새 물 LEAN 패키지3,495,363바이트만 추가했고 기존 지형·안개·물25역할 패키지를 재사용했다. '
        'Host/SDK/CLR/창/GPU/음향/실게임 실행0회, 새 게임 실행 묶음·기본 실행 변경·전역 등록·저장/SDK ABI 변경은 없다.\n\n'
        '수면은 실제 고정 높이 평면이며 정제된 높이장 삼각형과SDK 물 육각으로 잘랐다. 같은 수위 교점에서 등고선 해안 리본을 만든다. '
        'raw0.19836은 원본 DefaultWaterline에서 가져온 초기 후보이며 미확인 런타임 plane 상수의 확정값이 아니다. '
        '기존 높이 offset/scale도 후보로 유지한다. unknown 텍셀은 높이를 읽기 전 제외하고 LOD quad 안의 unknown도 건너뛴다. '
        'step4 기본·결정적 LOD·2M 버텍스·131072등고선·2^-24텍셀 snap은 품질/안전 정책이다.\n\n'
        '물 평면은 실제 깊이와 정확한 타일 ID를 함께 쓴다. 등고선/강은RGB만 쓴다. '
        '모드 전환은 지형 메타데이터 키를 무효화하고, 물 유닛·중심 anchor는max(지형높이,수면높이)를 사용한다. '
        '시간만 변할 때는 고정 기하·선택 표·전체 입력 세대를 보존하는 기존 경로를 유지한다.\n\n'
        '원본 LEAN 두16비트 평면을 실제 텍스처로 읽고 두 층의 모멘트·공분산·좁고 넓은 Gaussian·원본 raw Fresnel·비대칭4탭·gamma2.2와정확역gamma를 연결했다. '
        '정규화N·2π·Schlick F0를 원본식에 끼우지 않았다. 원본alpha요소는 새 격리 장면의불투명합성가중치로 적용했고 저장 프레임alpha는1이다. '
        '별도 반사 카메라가 기존 지형과 현재 보이는 유닛 버퍼를 재사용하며 수면 아래/미탐색은 자른다. '
        '실제 반사 이미지·자원 생성·샘플 위치는GPU 미검증이다.\n\n'
        '굴절은 주 화면의물 그리기 전색/깊이/ID를 별도복사한 새 후보 경로다. '
        '양수의같은타일ID→수면뒤깊이→복원된세계Y가수면아래인지 확인한뒤에만색을 읽는다. '
        '검사실패·현재보이지않는칸은공개깊이색으로대체하고, 장면의UI나미탐색색을끌어오지않는다. '
        '확인한 원본PS에는이장면굴절경로가없으므로원본재현확정으로보고하지않는다.\n\n'
        '런타임수위·headerScale→S·두층가중치·조명/warp/k/반사세기·카메라/캐시/샘플러·굴절변위/흡수는후보이다. '
        '원본의추가q2³깊이색항·전체 blend/light/shadow와캐시실행순서는미복원/미확인이다. '
        '세부확정식과후보는 `phase4/calibration_notes.json`과 `phase4/semantics/optics_contract.json`에 구분했다.\n\n'
        'CPU수면853,718·광학6,093·LEAN1,748,046·통합15,407·캐시179검사 및셰이더6개strict컴파일을통과했다. '
        '통합40×24fixture는아틀라스추가복사0·미탐색3,784,704텍셀변조불변,peakWS32,759,808바이트였다. 이는실게임성능측정이아니다. '
        f'C++14다섯단위실제컴파일/링크는경고0,현재/동결입력{len(build["current_source_inputs"])}개·컴파일의존{build["compiler_dependency_count"]}개를대조했다.\n\n'
        '명시적 `ZEROSIS_WATER_SURFACE_ASSETS`가새LEAN팩을가리키며 기존V2지형/물팩이함께필요하다. '
        '빈경로는직전색덧그림경로다. 격리실행연동정보는 `phase4/compiled_asset_binding.json`, 현재상태는 `phase4/current_work.json`이다. '
        'GPU색/깊이/ID·가림·CityView/입력·성능·원본화면·전체게임/저장/모드/멀티코어는미검증이다. '
        '조각배치는 **규칙 동등, 배치 동등은 미검증**이다.\n')
    (PROJECT/'docs/WATER_SURFACE_PHASE4_IMPLEMENTATION.md').write_text(notes,encoding='utf8')
    path=PROJECT/'docs/CLAUDE_HANDOFF.md';head,tail=path.read_text('utf8').split('\n',1)
    entry=(f'## 고정 수면·등고선·반사·굴절 4단계 — 2026-11-15\n\n현재 컴파일 후보는 `{identifier}`다. '
        '고정 평면·높이장 등고선·원본LEAN광학·격리반사/장면굴절 후보와 실제depth/ID·유닛높이·캐시키를 연결했다. '
        'CPU·셰이더6개strict·C++14컴파일/링크 경고0, Host/SDK/창/GPU/게임실행0회다. '
        '물LEAN1개3,495,363바이트만 추가했고 기존팩·4c8f/40a저장·기본실행은보존했다. '
        '원본런타임수위/광학/캐시/전체blend·추가depth항은미복원/미확인, 장면굴절은원본에서확인되지않은별도후보다. '
        '상세는 `docs/WATER_SURFACE_PHASE4_IMPLEMENTATION.md`, 근거는 `evidence/world_terrain_original/phase4/current_work.json`이다.\n\n')
    path.write_text(head+'\n\n'+entry+tail.lstrip('\n'),encoding='utf8')
    path=PROJECT/'docs/WORLD_TERRAIN_ORIGINAL_PLAN.md';text=path.read_text('utf8');marker='## 5. 열린 질문';assert text.count(marker)==1
    text=text.replace(marker,'### 고정 수면·등고선·반사·굴절 후속 기록 (2026-11-15)\n\n고정 평면/실제 높이 교점·LEAN 반사·격리 장면 굴절 후보를CPU·strict 셰이더·컴파일/링크까지 연결했다. '
        '수위/광학/캐시 보정·전체 원본blend/light/shadow·추가 깊이항과GPU화면은별도미확인/미복원으로분리한다. '
        '상세는 `WATER_SURFACE_PHASE4_IMPLEMENTATION.md`와 `evidence/world_terrain_original/phase4/current_work.json`에있다.\n\n'+marker,1)
    path.write_text(text,encoding='utf8')
    print(json.dumps(dict(status=value['status'],build_id=identifier,native_attempts=0,runtime_materialized=False)))

def close():
    path=STAGE/'current_work.json';value=read(path);assert value['storage']['after_pending']
    protection=read(STAGE/'protection_after.json');assert protection['status']=='PASS'
    before=read(STAGE/'storage_before.json');after=read(STAGE/'storage_after.json')
    assert read(STAGE/'plan_check_receipt.json')['status'].startswith('PASS')
    value['protection'].update(after=ref(STAGE/'protection_after.json'),after_pending=False)
    value['proofs']['plan68']=ref(STAGE/'plan_check_receipt.json')
    value['storage'].update(after=ref(STAGE/'storage_after.json'),after_pending=False,cleanup_summary=ref(STAGE/'cleanup_summary.json'),
        before_unique_allocated_bytes=before['unique_allocated_bytes'],after_unique_allocated_bytes=after['unique_allocated_bytes'],
        allocated_bytes_change=after['unique_allocated_bytes']-before['unique_allocated_bytes'],
        measurement='Allocation counted once per real os.stat identity; small receipt/final-index writes follow this scan.')
    save(path,value)
    progress=PROJECT/'evidence/save_menu/20261013_original_screen/current_progress.json';index=read(progress);index['current_offline_stage']=ref(path);save(progress,index)
    print(json.dumps(dict(status='PASS_CLOSED_WATER_SURFACE_PHASE4_OFFLINE',protected=protection['paths'],unique_allocated_bytes=after['unique_allocated_bytes'],
        allocated_bytes_change=value['storage']['allocated_bytes_change'],native_attempts=0)))
if __name__=='__main__':
    cli=argparse.ArgumentParser();cli.add_argument('action',choices=['publish','close']);cli.add_argument('--build-id');args=cli.parse_args()
    if args.action=='publish':publish(args.build_id)
    else:close()
