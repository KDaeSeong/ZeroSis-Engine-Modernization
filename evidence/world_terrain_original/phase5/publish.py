"""Close the offline lighting milestone without launching or promoting a runtime."""
from datetime import datetime, timezone
import argparse, json, re, sys
from pathlib import Path
sys.dont_write_bytecode = True
STAGE = Path(__file__).absolute().parent
PROJECT = STAGE.parents[2]
sys.path.insert(0, str(PROJECT / 'tools'))
import build_exit_confirm_host as common
import retained_menu_suite_host_input as menu


def read(path):
    return json.loads(Path(path).read_text('utf8'))


def ref(path):
    return common.artifact(Path(path).absolute())


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf8')


def publish(identifier):
    assert re.fullmatch(r'\d{8}T\d{6}Z_[0-9a-f]{12}', identifier or '')
    output = STAGE / 'current_work.json'
    assert not output.exists()
    report = PROJECT / 'evidence/ui_window_host' / identifier / 'build_result.json'
    build = read(report)
    assert not build['host_runtime_executed'] and not build['gamecore_loaded']
    profile = STAGE / 'pair_preparation' / identifier / 'prepared_profile.json'
    prepared = read(profile)
    assert not prepared['native_execution'] and not prepared['globally_registered']
    frozen = menu.frozen_rows(build)
    names = [path.name for path in (PROJECT / 'Source/Presentation').glob('OriginalLighting*')]
    names += ['OriginalTerrainShader.h', 'OriginalTerrainGpu.inc', 'OriginalTerrainGpuTypes.inc',
              'OriginalWaterSurfaceShader.h', 'OriginalWaterSurfaceGpu.inc', 'OriginalWaterSurfaceGpuTypes.inc',
              'OriginalWaterReflection.inc', 'OriginalWaterSurfaceTargets.inc', 'WorldTerrainReuse.h', 'WorldViewRenderer.h']
    for name in names:
        path = PROJECT / 'Source/Presentation' / name
        item = ref(path)
        matches = [row for row in frozen.values() if common.key(row['origin']) == common.key(path)]
        assert len(matches) == 1 and matches[0]['sha256'] == item['sha256'], name
    packages = {}
    for name, directory, digest, leaf in (
        ('terrain', 'OriginalTerrainAssets', '02104c582759bf0cefb58f97379699e45300eb2a9c6da6fdd3c65d1440cb84e8', 'terrain-assets.bin'),
        ('fog', 'OriginalFogAssets', '42ae12554e1514dd48a9a5df25f47b4280d22d180dff29d169c602334e879bcc', 'fog-assets.bin'),
        ('water', 'OriginalWaterAssets', '2ff227dae9d16398e038e8ea33624940a9581e0eb2d37c3891121fae22c25afc', 'water-assets.bin'),
        ('lean', 'OriginalWaterLeanAssets', '69c6780dbeb5f8605d8231cef944d0ec9392109b6ccc81a9d3b76ae83cfd0ef7', 'water-lean-assets.bin'),
        ('lighting', 'OriginalLightingAssets', 'd0873d3915da23e45ee1b66187bb7e4174673a1e8cce1fea16b6151ff515e424', 'lighting-assets.bin')):
        packages[name] = ref(PROJECT / 'Build' / directory / digest / leaf)
        assert packages[name]['sha256'] == digest
    proofs = {name: ref(STAGE / path) for name, path in (
        ('assets', 'assets/completion.json'), ('package', 'assets/package_tests/attempt1/result.json'),
        ('lighting_model', 'lighting_cpu/current.json'), ('semantics', 'semantics/lighting_contract.json'),
        ('pipeline', 'pipeline/cpu01/result.json'), ('shaders', 'shader/completion.json'),
        ('integration', 'review/asset_pipeline_review.json'), ('build_plan', 'host_build/plan_review.json'))}
    for name, item in proofs.items():
        assert read(item['path'])['status'].startswith('PASS'), name
    binding = dict(schema='zerosis.original_lighting.phase5.compiled_asset_binding.v1', host=build['executable'], packages=packages,
        compiled_binding=ref(PROJECT / 'Source/Presentation/OriginalLightingBinding.h'),
        explicit_environment={key: packages[name]['path'] for key, name in (
            ('ZEROSIS_LIGHTING_ASSETS', 'lighting'), ('ZEROSIS_WATER_ASSETS', 'water'),
            ('ZEROSIS_FOG_ASSETS', 'fog'), ('ZEROSIS_WATER_SURFACE_ASSETS', 'lean'))},
        terrain_requirement='Existing sealed V2 terrain-assets.bin is required for a future isolated runtime.',
        exact_outer_and_blob_sha256=True, existing_asset_package_copies_created=0,
        runtime_materialized=False, native_launch_allowed=False, default_promoted=False, full_engine_goal_complete=False)
    save(STAGE / 'compiled_asset_binding.json', binding)
    value = dict(schema='zerosis.original_lighting.phase5.current_work.v1', utc=datetime.now(timezone.utc).isoformat(),
        status='PASS_PHASE5_ORIGINAL_LIGHTING_COMPOSITION_OFFLINE_COMPILE_LINK_GPU_PENDING',
        completed_scope='Requested offline original lighting/composition: confirmed terrain and water algebra, minimal original assets, controlled CPU/strict shader and actual C++ compile/link.',
        full_goal_redefined=False, full_engine_goal_complete=False,
        current_host=dict(build_id=identifier, parent_build_id='20261115T055523Z_51738aa69964', build_result=ref(report),
            executable=build['executable'], prepared_profile=ref(profile),
            independent_attestation=ref(STAGE / 'pair_preparation' / identifier / 'independent_attestation.json'),
            compiler_dependency_count=build['compiler_dependency_count'], current_source_input_count=len(build['current_source_inputs']),
            frozen_input_count=len(frozen), compiler_and_linker_warnings=0, translation_units=5,
            embedded_ui_payloads=74, required_ui_sidecar_files=154, default_or_global_registration_changed=False),
        packages=packages, compiled_asset_binding=ref(STAGE / 'compiled_asset_binding.json'), proofs=proofs,
        source_manifest=build['menu_suite_component'], calibration_candidates=ref(STAGE / 'calibration_notes.json'),
        implemented=[
            'Optional original sunlight/shadowlight/terrainLUT package,15 roles sharing9 payloads,730040B; four previous asset packages reused with no copies.',
            'Pointwise original CacheBake irradiance/diffuse gamma/LUT and separate specular auxiliary output with interpolated existing base normal, neutral detail normal/shadow candidates.',
            'Full confirmed original water pre-shadow depth/diffuse/narrow/wide/reflection/q2-cubed operations, exact gamma and alpha factor with explicit isolated opaque composition policy.',
            'Original Sobel/final terrain/water FOW reference algebra with independent goldens, guarded unknown callbacks and explicit invalid-domain policies.',
            'Known-only continent selector,44B vertex normal tail,80B lighting constants and320B water constants, matching exact shader slots and integer selection.',
            'Encoded UNORM terrain/main-reflection output; existing unit linear output keeps sRGB view. Exact lighting-path ground/target key and successful catalog publication.'],
        checks=dict(lighting_cpu=3689, package_cpu=4620, selector_and_cache_cpu=2239,
                    original_plan_claims=68, shader_entry_points=6),
        native_host_sdk_clr_hwnd_gpu_audio_or_game_attempts=0, new_game_runtime_materialized=False,
        latest_source_matches_linked_candidate=True, prepared_runtime_matches_latest_source=False,
        retained_prepared_runtime='Build/InteractiveGameRuntime/20261115T011241Z_4c8fd55e99db',
        retained_user_session='Build/InteractiveGameRuntime/20261108T003146Z_40a8030edf08/sessions/350dd3b9ceb408a391b5a8aa63b48301',
        piece_placement_report='규칙 동등, 배치 동등은 미검증',
        remaining=[
            'Actual normal-cache producer, projected/runtime/self-shadow input bindings, specular downstream routing, screen light/world mask/overlay producers and original cache order/resampling remain unresolved.',
            'Original water-specific grey0.4 FOW GPU producer and hardware blend state remain unresolved; current common FOW and isolated opaque scene-refraction composition are candidates.',
            'Runtime lighting/camera/cube axes/sampler/LUT/plane/optical constants, GPU resource creation and colour/depth/ID/occlusion, input/CityView/UI, performance/VRAM and original screen comparison are unverified.',
            'Trees/original tessellation/camera, piece layout equivalence and full gameplay/save/mod/multicore acceptance remain further work.'],
        protection=dict(before=ref(STAGE / 'protection_before.json.gz'), precompile=ref(STAGE / 'protection_precompile.json'), after_pending=True),
        storage=dict(before=ref(STAGE / 'storage_before.json'), precompile=ref(STAGE / 'storage_precompile.json'), after_pending=True,
            full_project_copies_created=0, existing_asset_package_copies=0, new_minimal_lighting_packages=1,
            final_build_cleanup=ref(STAGE / 'pair_preparation' / identifier / 'cleanup_result.json'),
            confirmed_disposable_bytes=0, threshold_bytes=10 * 1024**3))
    save(output, value)
    progress = PROJECT / 'evidence/save_menu/20261013_original_screen/current_progress.json'
    index = read(progress)
    index.update(utc=value['utc'], status=value['status'], current_source_working_stage=str(STAGE),
        current_offline_stage=ref(output), latest_source_matches_linked_candidate=True,
        prepared_runtime_matches_latest_source=False, full_engine_goal_complete=False,
        original_lighting_phase5_status='ORIGINAL_TERRAIN_WATER_ALGEBRA_AND_ASSETS_OFFLINE_BUILD_PASS_RUNTIME_BINDINGS_GPU_PENDING')
    save(progress, index)
    notes = (f'# 원본 조명·혼합 5단계 — 오프라인 구현\n\n2026-11-15. 컴파일 후보 `{identifier}`. '
        '서브에이전트3개로 수식·계산·자산을 분담했다. Host/SDK/CLR/창/GPU/음향/실게임 실행0회, '
        '새 게임 실행 묶음·기본 실행·전역 등록·원본/MODS/설정/사용자 저장 변경은 없다.\n\n'
        '지형에 대륙별 원본 조사 큐브·색 변환표를 연결했다. 15역할이9고유 입력을 공유하는730,040바이트 보조팩 하나만 추가했다. '
        '기존 지형·안개·물·LEAN 네 팩은 재사용한다. 원본 CacheBake 조사광×1.7/그림자 보간/확산+.001/정확 감마/LUT를 점별로 계산한다. '
        '기본 법선은 기존 높이장 법선의 보간, 세부 법선(.5,.5,1)과 그림자0은 명시적 후보이다. '
        '원본 반사 조명도 계산해 별도 보조 목표에 저장하지만 최종 확산에 더하지 않는다. 원본의 반사 합성 경로가 미추적이기 때문이다.\n\n'
        '물은 원본 깊이색을 추가 2.2승 없이 사용하고 Lambert 안의 raw Fresnel×두 좁은 반사항, 주 광원의 넓은 항, 독립 반사색, '
        '누락됐던 sat(4h)×q2³×깊이색, 그림자 감쇠, 정확 RGB감마/알파를 연결했다. '
        'q2>=16 때문에 가우스 항이0이 돼도 유한한 q2³은 보존한다. 비유한값 방어는 원본 유효영역 밖의 별도 정책이다. '
        '광원색/방향/K/수위/두 층 가중치/반사 캐시 보정은 후보로 남는다.\n\n'
        '지형과 반사의 이미 감마를 적용한 결과는 UNORM 목표에 쓴다. 기존 유닛은 선형 출력을 유지하므로 sRGB 목표에 쓴다. '
        '조명은 타일ID/깊이를 섞지 않는다. 미탐색은 색·대륙·물 속성을 읽기 전 차단하고, 조명 경로를 정확한 지형 캐시 키에 포함했다. '
        '실패한 후보는 이전 정상 프레임과 조명 카탈로그를 교체하지 않는다. 내부 FrameTargets 전체 롤백까지 보장하는 것은 아니다.\n\n'
        '계산3,689·자산4,620·선택/캐시2,239검사와 셰이더6개 strict컴파일을 통과했다. '
        '유한값 방어 변경으로 물2개만 추가 컴파일했고 지형/기존4개 결과를 재사용했다. '
        f'C++14 다섯 단위를 실제 컴파일/링크해 경고0, 현재/동결 입력{len(build["current_source_inputs"])}개, 실제 의존{build["compiler_dependency_count"]}개를 대조했다.\n\n'
        '남은 경계는 원본 normal-cache 생산자·그림자/화면 조명/월드 마스크/덧그림 입력·반사 최종 합성·캐시 해상도/순서와 GPU 검증이다. '
        '원본 물의 회색0.4 FOW식은 CPU참조에 있고 GPU는 기존 공통 FOW를 한 번만 쓴다. '
        '원본 하드웨어 혼합은 미확인으로, 기존 장면 굴절과 알파를 이용한 불투명 혼합은 별도 후보이다. '
        '원본 전체 화면·성능·저장/모드/멀티코어 완료를 뜻하지 않는다. 조각 배치는 **규칙 동등, 배치 동등은 미검증**이다.\n\n'
        '상태와 근거: `evidence/world_terrain_original/phase5/current_work.json`. '
        '격리 연동값: 같은 폴더의 `compiled_asset_binding.json`; `ZEROSIS_LIGHTING_ASSETS`가 새 보조팩을 가리킨다. '
        '현재 보류 중인 준비 실행본4c8f와40a 사용자 저장은 그대로 보존했다.\n')
    (PROJECT / 'docs/LIGHTING_PHASE5_IMPLEMENTATION.md').write_text(notes, encoding='utf8')
    path = PROJECT / 'docs/CLAUDE_HANDOFF.md'
    head, tail = path.read_text('utf8').split('\n', 1)
    entry = (f'## 원본 조명·혼합 5단계 — 2026-11-15\n\n현재 컴파일 후보는 `{identifier}`다. '
        '원본 지형 조사광/감마/LUT·별도 반사 조명, 물 전체 조명식과 q2³/그림자 항을 연결했다. '
        '중립 세부 법선/그림자·캐시/광원/불투명 혼합은 후보이며 원본 spec 경로·물 전용 FOW GPU 연결은 미추적이다. '
        'CPU/자산/선택·캐시10,548검사와 strict셰이더6개·실제 C++14 다섯 단위 컴파일/링크 경고0, Host·GPU·게임 실행0회다. '
        '730040B 보조팩 하나만 추가하고 네 기존팩·4c8f/40a 저장·기본실행을 보존했다. '
        '상세는 `docs/LIGHTING_PHASE5_IMPLEMENTATION.md`, 근거는 `evidence/world_terrain_original/phase5/current_work.json`이다.\n\n')
    path.write_text(head + '\n\n' + entry + tail.lstrip('\n'), encoding='utf8')
    path = PROJECT / 'docs/WORLD_TERRAIN_ORIGINAL_PLAN.md'
    text = path.read_text('utf8')
    marker = '## 5. 열린 질문'
    assert text.count(marker) == 1
    text = text.replace(marker, '### 원본 조명·혼합 후속 기록 (2026-11-15)\n\n'
        '지형 조사 큐브/LUT와 물 전체 조명식/q2³/그림자 항을 오프라인 구현·컴파일/링크까지 연결했다. '
        '세부 법선/그림자 생산자·원본 반사 합성·물 전용 FOW GPU·캐시 순서·런타임 상수·화면 동등성은 별도 미확인이다. '
        '상세는 `LIGHTING_PHASE5_IMPLEMENTATION.md`와 `evidence/world_terrain_original/phase5/current_work.json`에 있다.\n\n' + marker, 1)
    path.write_text(text, encoding='utf8')
    print(json.dumps(dict(status=value['status'], build_id=identifier, native_attempts=0, runtime_materialized=False)))


def close():
    path = STAGE / 'current_work.json'
    value = read(path)
    assert value['storage']['after_pending']
    protection = read(STAGE / 'protection_after.json')
    assert protection['status'] == 'PASS'
    before, after = read(STAGE / 'storage_before.json'), read(STAGE / 'storage_after.json')
    assert read(STAGE / 'plan_check_receipt.json')['status'].startswith('PASS')
    value['protection'].update(after=ref(STAGE / 'protection_after.json'), after_pending=False)
    value['proofs']['plan68'] = ref(STAGE / 'plan_check_receipt.json')
    value['storage'].update(after=ref(STAGE / 'storage_after.json'), after_pending=False,
        cleanup_summary=ref(STAGE / 'cleanup_summary.json'), before_unique_allocated_bytes=before['unique_allocated_bytes'],
        after_unique_allocated_bytes=after['unique_allocated_bytes'], allocated_bytes_change=after['unique_allocated_bytes']-before['unique_allocated_bytes'],
        measurement='Allocation counted once per real os.stat file identity; receipt/index writes follow scan.')
    save(path, value)
    progress = PROJECT / 'evidence/save_menu/20261013_original_screen/current_progress.json'
    index = read(progress)
    index['current_offline_stage'] = ref(path)
    save(progress, index)
    print(json.dumps(dict(status='PASS_CLOSED_ORIGINAL_LIGHTING_PHASE5_OFFLINE', protected=protection['paths'],
        unique_allocated_bytes=after['unique_allocated_bytes'], allocated_bytes_change=value['storage']['allocated_bytes_change'], native_attempts=0)))


if __name__ == '__main__':
    cli = argparse.ArgumentParser()
    cli.add_argument('action', choices=['publish', 'close'])
    cli.add_argument('--build-id')
    args = cli.parse_args()
    publish(args.build_id) if args.action == 'publish' else close()
