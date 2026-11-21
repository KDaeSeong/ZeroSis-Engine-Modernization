"""Record the offline normal/shadow/final-specular milestone without native execution."""
from datetime import datetime, timezone
from pathlib import Path
import argparse, json, re, sys
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
    names = [path.name for path in (PROJECT / 'Source/Presentation').glob('OriginalLightingField*')]
    names += ['OriginalLightingModel.h', 'OriginalTerrainShader.h', 'OriginalTerrainGpu.inc',
              'OriginalTerrainGpuTypes.inc', 'OriginalWaterReflection.inc', 'WorldTerrainRenderer.cpp']
    for name in names:
        path = PROJECT / 'Source/Presentation' / name
        matches = [row for row in frozen.values() if common.key(row['origin']) == common.key(path)]
        assert len(matches) == 1 and matches[0]['sha256'] == ref(path)['sha256'], name
    previous = read(STAGE.parent / 'phase5/current_work.json')
    packages = {name: ref(row['path']) for name, row in previous['packages'].items()}
    assert all(packages[name]['sha256'] == row['sha256'] for name, row in previous['packages'].items())
    proofs = {name: ref(STAGE / path) for name, path in (
        ('original_bindings', 'semantics/retail_cache_bindings.json'), ('fields', 'field_cpu/current.json'),
        ('material_reference', 'review/material_sampler/attempt01/result.json'),
        ('pipeline', 'pipeline/cpu01/result.json'), ('shaders', 'shader/completion.json'),
        ('integration', 'review/integration_review.json'), ('asset_integration', 'review/asset_integration_review.json'),
        ('components', 'review/component_completion.json'), ('build_plan', 'host_build/plan_review.json'))}
    for name, item in proofs.items():
        assert read(item['path'])['status'].startswith('PASS'), name
    binding = dict(schema='zerosis.original_lighting_fields.phase6.compiled_asset_binding.v1', host=build['executable'],
        packages=packages, compiled_field_binding=ref(PROJECT / 'Source/Presentation/OriginalLightingFieldBinding.h'),
        explicit_environment={key: packages[name]['path'] for key, name in (
            ('ZEROSIS_LIGHTING_ASSETS', 'lighting'), ('ZEROSIS_WATER_ASSETS', 'water'),
            ('ZEROSIS_FOG_ASSETS', 'fog'), ('ZEROSIS_WATER_SURFACE_ASSETS', 'lean'))},
        terrain_requirement='Existing sealed V2 terrain-assets.bin is required for a future isolated runtime.',
        new_asset_packages=0, existing_asset_package_copies_created=0, retained_cpu_texture_clone_bytes=0,
        runtime_materialized=False, native_launch_allowed=False, default_promoted=False, full_engine_goal_complete=False)
    save(STAGE / 'compiled_asset_binding.json', binding)
    value = dict(schema='zerosis.original_lighting_fields.phase6.current_work.v1', utc=datetime.now(timezone.utc).isoformat(),
        status='PASS_PHASE6_DETAIL_NORMAL_MACRO_SHADOW_FINAL_SPECULAR_OFFLINE_COMPILE_LINK_GPU_PENDING',
        completed_scope='Requested offline detail-normal producer, known-only terrain macro-shadow producer and traced final baked-specular composition; actual CPU/shader/compiler-link evidence, no native acceptance.',
        full_goal_redefined=False, full_engine_goal_complete=False,
        current_host=dict(build_id=identifier, parent_build_id='20261115T064034Z_2b0664f7ca2e', build_result=ref(report),
            executable=build['executable'], prepared_profile=ref(profile),
            independent_attestation=ref(STAGE / 'pair_preparation' / identifier / 'independent_attestation.json'),
            compiler_dependency_count=build['compiler_dependency_count'], current_source_input_count=len(build['current_source_inputs']),
            frozen_input_count=len(frozen), compiler_and_linker_warnings=0, translation_units=5,
            embedded_ui_payloads=74, required_ui_sidecar_files=154, default_or_global_registration_changed=False),
        packages=packages, compiled_asset_binding=ref(STAGE / 'compiled_asset_binding.json'), proofs=proofs,
        source_manifest=build['menu_suite_component'], calibration_candidates=ref(STAGE / 'calibration_notes.json'),
        implemented=[
            'Original mixed material-height→Sobel/cardinal strength16, macro-shadow→CacheBake and baked-specular→finalt8 bindings traced in original selected code; prior finalt8 albedo interpretation corrected.',
            'Shared68x68 material-height GPU scratch and66x66 per-mesh normal with exact alpha8/Sobel; zero new original packs or retained CPU texture clones.',
            'Known-only40-step terrain shadow from existing Atlas by const reference, all4 bilinear support nodes checked before reads, unknown-ray neutral fallback, bounded66x66 texture.',
            'Generated normal and macro shadow feed terrain lighting; baked specular now participates in confirmed linear-space final composition with neutral screen-light1 and both gates enabled candidates.',
            'Canonical mesh field ownership/reuse across wrapped images and reflected/main terrain; no field capture/sample/allocation/draw on idle reuse and no field allocation for zero-material chunks.',
            'Depth/R32_UINT identity, caller output on failure, detached SDK/RNG boundary, existing original packages/live runtimes/user saves/default execution retained.'],
        checks=dict(field_cpu=112653, corrected_lighting_reference=3689, borrowed_material_reference=15515,
                    preparation_policy_cpu=53904, current_shader_entry_points=10, actual_stage_shader_compiles=8),
        native_host_sdk_clr_hwnd_gpu_audio_or_game_attempts=0, new_game_runtime_materialized=False,
        latest_source_matches_linked_candidate=True, prepared_runtime_matches_latest_source=False,
        retained_prepared_runtime='Build/InteractiveGameRuntime/20261115T011241Z_4c8fd55e99db',
        retained_user_session='Build/InteractiveGameRuntime/20261108T003146Z_40a8030edf08/sessions/350dd3b9ceb408a391b5a8aa63b48301',
        piece_placement_report='규칙 동등, 배치 동등은 미검증',
        remaining=[
            'Original base vertex-normal generator, cache resolution/format/compression/resampling/order, coordinate/camera/shadow calibration and final screen-lightt9 producer/runtime flags are unverified.',
            'This stage generates terrain macro-shadows; dynamic scene/unit shadow production and water t13 shadow wiring remain unresolved.',
            'Water grey0.4 GPU FOW, original native blend states, GPU resource creation and actual colour/depth/ID/occlusion/UI/input/CityView/performance/VRAM/original-screen acceptance remain held.',
            'Original trees/tessellation/camera, exact piece placement, full gameplay/save/mod/multicore acceptance remain further work.'],
        protection=dict(before=ref(STAGE / 'protection_before.json.gz'), precompile=ref(STAGE / 'protection_precompile.json'), after_pending=True),
        storage=dict(before=ref(STAGE / 'storage_before.json'), precompile=ref(STAGE / 'storage_precompile.json'), after_pending=True,
            full_project_copies_created=0, existing_asset_package_copies=0, new_asset_packages=0,
            final_build_cleanup=ref(STAGE / 'pair_preparation' / identifier / 'cleanup_result.json'),
            confirmed_disposable_bytes=0, threshold_bytes=10 * 1024**3))
    save(output, value)
    progress = PROJECT / 'evidence/save_menu/20261013_original_screen/current_progress.json'
    index = read(progress)
    index.update(utc=value['utc'], status=value['status'], current_source_working_stage=str(STAGE),
        current_offline_stage=ref(output), latest_source_matches_linked_candidate=True,
        prepared_runtime_matches_latest_source=False, full_engine_goal_complete=False,
        original_lighting_fields_phase6_status='DETAIL_NORMAL_MACRO_SHADOW_FINAL_BAKED_SPECULAR_OFFLINE_BUILD_PASS_NATIVE_PENDING')
    save(progress, index)
    notes = (f'# 세부 법선·자기그림자·최종 반사 합성 6단계 — 오프라인 구현\n\n2026-11-15. 컴파일 후보 `{identifier}`. '
        '서브에이전트3개로 정적 연결 추적·계산·자산/자료흐름을 분담했다. Host/SDK/CLR/창/GPU/음향/실게임 실행0회, '
        '원본 설치·MODS·설정·사용자 저장·기본 실행·등록·SDK ABI/저장 스키마 변경은 없다.\n\n'
        '원본 코드에서 세 연결을 추가 확정했다. 혼합 재질 높이 MRT1→NormalCalculate(한 텍셀8탭,강도16), '
        'Macro Shadow40step→CacheBake t2, 구운 반사광→최종 TerrainShader t8이다. '
        '이전 t8=확산색 해석은 수정했다. 기본 법선은 별도 NORMAL0 정점 스트림이고 Sobel 출력은 세부 법선 t0이다. '
        '현재 높이장 정점 법선을 그 기본 법선으로 공급하는 부분은 여전히 현재 기하 후보이다.\n\n'
        '기존 다섯 팩의 압축 텍스처를 그대로 사용한다. GPU는 공유68² R16_FLOAT 높이 임시 목표 한 장을 굽고 '
        '청크마다66² RGBA16 법선과 R16 그림자를 보관한다. CPU 원본 텍스처 상주복사·새 자산팩·전역 법선/그림자 사본은0이다. '
        '청크별 법선+그림자 논리 텍셀은43,560바이트다. CPU 필드 참조의110KiB한도에는GPU 정점 staging/드라이버 할당을 포함하지 않는다.\n\n'
        '높이는 원본 alpha8 가중 평균, null0/missing.5 의미를 유지한다. 알려진 중심/이웃만 읽고 미탐색 이웃은 중심으로 대체한다. '
        '그림자는 원본2..41번째 위치를 검사하고4개 bilinear 지지점 모두 알려진 경우만 높이를 읽으며, '
        '미탐색에 닿는 광선은0으로 돌린다. 현재 방향(-1,1),변환축척·offset, bias/strength.125는 보정 후보다.\n\n'
        '최종 반사 합성은 decode(확산)+decode(반사)×화면조명을 다시 encode하는 확인된 원본 경로를 따른다. '
        '화면 조명 t9 생산자/값과 실제 enable 상수는 미확정이라 현재는1과두 gate 켜짐을 사용한다. '
        '지도 경계 halo의GPU 좌표가CPU canonical계약과 다르던 결함을 수정하고, 바뀐 높이 셰이더만 다시 컴파일했다.\n\n'
        '반사/주 화면이 같은 완성 필드를 공유한다. 시간만 바뀐 프레임은 capture·높이읽기·할당·bake를 건너뛰고 '
        '재질 없는 청크도 필드를 만들지 않는다. 위치·깊이·정수 타일ID를 섞지 않는다. '
        '새 필드는 완성 뒤 소유하며, 실패해도 기존 필드를 이동하지 않는다. 내부 모든 임시 자원의 프레임 단위 롤백까지 주장하지 않는다.\n\n'
        '필드112,653(UNORM16전수65,536 포함)·이름 정정 조명 참조3,689·BC3참조15,515·실제 준비 정책53,904 검사를 통과했다. '
        '마지막 정책 검사는GPU를대체한CPU backend로실제 Bridge.inc를실행한것이며실GPU검사가아니다. '
        '현재 셰이더10단계가통과했고 이번단계 실제compile8회, 변경없는본문은SHA로재사용했다. '
        f'C++14다섯단위실제컴파일/링크 경고0,현재/동결입력{len(build["current_source_inputs"])}개·실제의존{build["compiler_dependency_count"]}개를대조했다.\n\n'
        '남은 관문은 원본 정점 법선 생산·캐시 형식/해상도/재표본·카메라/그림자 보정·화면 조명t9, 동적 장면/유닛 그림자와물t13연결이다. '
        '물전용회색FOW/원본하드웨어혼합·GPU색/ID/깊이/가림·UI/입력/CityView·성능/VRAM·원본화면은계속미검증이다. '
        '현재CPUfloat높이와GPUhalf높이저장의정밀도차이는후보로분리한다. 전체게임/저장/모드/멀티코어완료를뜻하지않는다. '
        '조각 배치는 **규칙 동등, 배치 동등은 미검증**이다.\n\n'
        '상태: `evidence/world_terrain_original/phase6/current_work.json`. '
        '격리연동: 같은폴더 `compiled_asset_binding.json`; 다섯기존팩과명시적조명환경값을재사용한다. '
        '실행묶음4c8f와40a사용자저장·직전2b0664복구후보를보존했다.\n')
    (PROJECT / 'docs/LIGHTING_FIELDS_PHASE6_IMPLEMENTATION.md').write_text(notes, encoding='utf8')
    path = PROJECT / 'docs/CLAUDE_HANDOFF.md'
    head, tail = path.read_text('utf8').split('\n', 1)
    entry = (f'## 세부 법선·자기그림자·최종 반사 합성 6단계 — 2026-11-15\n\n현재 컴파일 후보는 `{identifier}`다. '
        '원본 materialH→Sobel16·MacroShadow→CacheBake·bakedSpec→finalt8 연결을 추가 확인하고 생산/합성을 연결했다. '
        '이전t8=albedo 해석을수정했고 원본 NORMAL0 생산·현재68/66/정밀도·그림자보정·screenLight1은후보/미확인이다. '
        'CPU부품185,761검사·현재셰이더10단계·실제C++14다섯단위컴파일/링크경고0, Host/GPU/게임0회다. '
        '새팩/CPU원본복사0, 기존다섯팩·4c8f/40a저장·기본실행을보존했다. '
        '동적유닛그림자/물t13·실GPU화면수락은계속미검증이다. 상세는 `docs/LIGHTING_FIELDS_PHASE6_IMPLEMENTATION.md`, '
        '근거는 `evidence/world_terrain_original/phase6/current_work.json`이다.\n\n')
    path.write_text(head + '\n\n' + entry + tail.lstrip('\n'), encoding='utf8')
    path = PROJECT / 'docs/WORLD_TERRAIN_ORIGINAL_PLAN.md'
    text = path.read_text('utf8')
    old = '확산 캐시 × 화면 공간 조명 버퍼'
    assert text.count(old) == 1
    text = text.replace(old, '반사 조명 캐시(t8) × 화면 공간 조명 버퍼(t9)', 1)
    marker = '## 5. 열린 질문'
    assert text.count(marker) == 1
    text = text.replace(marker, '### 법선·자기그림자·최종 반사 후속 기록 (2026-11-15)\n\n'
        '원본 렌더 호출로 materialH→Sobel(strength16)·MacroShadow→CacheBake·bakedSpec→finalt8을추가확정했다. '
        '2.5절의이전t8=확산해석은반사조명으로정정했다. 생산/합성을오프라인연동·컴파일/링크까지통과했으나 '
        '캐시표현·정점법선생산·화면조명/그림자런타임보정·동적유닛그림자와GPU화면은별도미확인이다. '
        '상세는 `LIGHTING_FIELDS_PHASE6_IMPLEMENTATION.md`와 `evidence/world_terrain_original/phase6/current_work.json`이다.\n\n' + marker, 1)
    path.write_text(text, encoding='utf8')
    print(json.dumps(dict(status=value['status'], build_id=identifier, native_attempts=0, new_asset_packages=0)))


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
        measurement='Allocation counted once per real os.stat identity; receipt/index writes follow scan.')
    save(path, value)
    progress = PROJECT / 'evidence/save_menu/20261013_original_screen/current_progress.json'
    index = read(progress)
    index['current_offline_stage'] = ref(path)
    save(progress, index)
    print(json.dumps(dict(status='PASS_CLOSED_ORIGINAL_LIGHTING_FIELDS_PHASE6_OFFLINE', protected=protection['paths'],
        unique_allocated_bytes=after['unique_allocated_bytes'], allocated_bytes_change=value['storage']['allocated_bytes_change'], native_attempts=0)))


if __name__ == '__main__':
    cli = argparse.ArgumentParser()
    cli.add_argument('action', choices=['publish', 'close'])
    cli.add_argument('--build-id')
    args = cli.parse_args()
    publish(args.build_id) if args.action == 'publish' else close()
