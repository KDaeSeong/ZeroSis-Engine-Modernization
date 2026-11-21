"""Publish an offline-only current pair and close protection/storage records."""
from datetime import datetime,timezone
import argparse
import json
from pathlib import Path
import sys

sys.dont_write_bytecode=True
STAGE=Path(__file__).absolute().parent
PROJECT=STAGE.parents[2]
sys.path.insert(0,str(PROJECT/'tools'))
import build_exit_confirm_host as common

def read(path):return json.loads(Path(path).read_text('utf8'))
def save(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
def ref(path):return common.artifact(Path(path).absolute())

def publish(build_id,run_id):
    output=STAGE/'current_work.json';assert not output.exists()
    verified=read(STAGE/'prepared_runtime_verification.json')
    assert verified['build_id']==build_id and verified['run_id']==run_id and verified['native_attempts']==0
    build_path=PROJECT/'evidence/ui_window_host'/build_id/'build_result.json'
    build=read(build_path);profile=STAGE/'pair_preparation'/build_id/'prepared_profile.json'
    runtime=PROJECT/'Build/InteractiveGameRuntime'/run_id
    tests=read(STAGE/'tests/result.json')
    assert tests['status'].startswith('PASS')
    assert read(STAGE/'source_integration_review2.json')['status']=='PASS'
    old=PROJECT/'evidence/game_menu/native_slider_hover/current_work.json'
    value=dict(schema='zerosis.idle_render_cache.current_work.v1',utc=datetime.now(timezone.utc).isoformat(),
        status='PASS_IDLE_RENDER_CACHE_SOURCE_AND_EXPLICIT_PAIR_OFFLINE_NATIVE_PERFORMANCE_PENDING',
        goal_turn_classification='progress',full_goal_redefined=False,full_engine_goal_complete=False,
        implemented=[
            'Exact detached ground-input key reuses immutable GPU ground meshes and owned ground ID/anchor/contour metadata. Ordered plots, terrain/fog/camera/viewport/device/context changes invalidate it.',
            'Each animated pose clears and redraws ground and units. Color, ID, depth and staging surfaces are reused by viewport size; no stale unit depth is reused.',
            'Unit dynamic vertex buffers reuse exact current-frame capacities, discard-upload current poses and evict inactive texture groups. Cache publication occurs only after a complete successful candidate.',
            'Automatic animation suppresses repeated frame trace lines; ordinary scene publication retains diagnostics. Animation, hit/pixel-hit/generation checks, game rules and saves are unchanged.'],
        current_host=dict(status='CURRENT_COMPILED_EXPLICIT_PREPARED_PROFILE_NOT_REGISTERED_OR_EXECUTED',
            build_id=build_id,parent_build_id='20261108T002841Z_2b25aaa753e3',executable=build['executable'],
            build_result=ref(build_path),prepared_profile=ref(profile),
            independent_attestation=ref(STAGE/'pair_preparation'/build_id/'independent_attestation.json'),
            compiler_dependency_count=build['compiler_dependency_count'],current_source_input_count=len(build['current_source_inputs']),
            frozen_input_count=verified['frozen_inputs_verified'],source_manifest_count=read(profile)['source_manifest_count'],
            catalog_entries=74,required_sidecar_files=154,sidecar_asset_pack='Source/Assets/UIFrontEndV4',
            actual_compile_attempts=1,host_pipeline_attempts=2,failed_dependency_discoveries=1,
            compiler_and_linker_warnings=0),
        current_prepared_runtime=dict(runtime_directory=str(runtime),run_id=run_id,physical_file_paths=189,
            host_sha256=verified['host']['sha256'],gamecore_sha256=verified['gamecore']['sha256'],
            prepared_verification=ref(STAGE/'prepared_runtime_verification.json'),native_attempts=0,new_game_only=True),
        working_source_matches_current_frozen_and_prepared_profile=True,
        source_manifest=ref(STAGE/'host_build/source_manifest2.json'),
        proofs=dict(cache_cpu_tests=ref(STAGE/'tests/result.json'),source_integration=ref(STAGE/'source_integration_review2.json'),
            plan_review=ref(STAGE/'host_build/plan_review2.json'),failed_dependency_discovery=ref(STAGE/'host_build/failed_discovery.json'),
            system_tool_selection=ref(STAGE/'host_build/system_tool_selection.json'),
            system_tool_signature=ref(STAGE/'host_build/system_tool_signature.json')),
        protection=dict(before=ref(STAGE/'protection_before.json.gz'),precompile=ref(STAGE/'protection_precompile.json'),
            after_pending=True,prior_user_runtime='Build/InteractiveGameRuntime/20261108T003146Z_40a8030edf08',
            prior_user_session='sessions/350dd3b9ceb408a391b5a8aa63b48301',original_default_mods_or_saves_changed=False),
        storage=dict(before=ref(STAGE/'storage_before.json'),precompile=ref(STAGE/'storage_precompile.json'),
            after_pending=True,full_project_copies_created=0,confirmed_disposable_bytes=0,threshold_bytes=10*1024**3,
            intermediate_cleanup=ref(STAGE/'pair_preparation'/build_id/'cleanup_result.json'),
            previous_user_runtime_and_recovery_preserved=True),
        supersedes=ref(old),
        remaining=[
            'Item 1: live idle CPU/frame-time, moving-unit ghost/occlusion and ground picking regressions remain unmeasured until separately authorized Host/GPU execution.',
            'Remaining idle costs include per-frame D2D/text factories, unit CPU pose assembly, output metadata copies and full retained scene input comparisons. No claimed CPU percentage.',
            'Original 3D terrain/FOW implementation, remaining menu/backend/input fidelity, replay, real gameplay/turn/save-load/mod acceptance and measured multicore stability remain part of the original engine objective.'],
        native_execution=False,current_native_or_screen_relaunch_allowed=False,screen_verification_deferred=True,
        measured_live_cpu_reduction_percent=None,default_or_registration_changed=False)
    save(output,value)
    current=PROJECT/'evidence/save_menu/20261013_original_screen/current_progress.json'
    progress=read(current);progress.update(utc=value['utc'],status=value['status'],
        current_source_working_stage=str(STAGE),latest_source_matches_linked_candidate=True,
        prepared_runtime_matches_latest_source=True,current_offline_stage=ref(output),full_engine_goal_complete=False,
        idle_cpu_item_status='OFFLINE_IMPLEMENTATION_AND_PACKAGE_PASS_NATIVE_PERFORMANCE_PENDING')
    save(current,progress)
    section=(f'## 유휴 렌더링 재사용 단계 — 2026-11-15\n\n'
        f'현재 Host는 `{build_id}`, 별도 실행 묶음은 `{run_id}`이다. 부모는 `2b25`/`40a8`이며 SDK430과 V4 자산154개를 그대로 사용했다. '
        f'C++14 다섯 단위를 실제 컴파일·링크했고 경고는0개다. 현재·동결 입력은 각각 {len(build["current_source_inputs"])}개·{verified["frozen_inputs_verified"]}개, '
        f'실제 컴파일 의존은 {build["compiler_dependency_count"]}개다. 준비본은189파일이고 기본 실행·등록은 바꾸지 않았다.\n\n'
        '정지 상태의 유닛 애니메이션이 지형 메시 생성·버퍼 업로드·ID GPU 읽기·전체 픽셀 윤곽 계산을 매번 반복하던 경로를 줄였다. '
        '동일한 지형 입력에는 단일 소유 캐시를 사용하고, 지형·시야·시점·확대·해상도·장치·문맥이 바뀌면 다시 만든다. '
        '메타데이터는 반환값과 독립적으로 보유하고 완성된 후보만 교체한다. 색·깊이는 매번 지우고 지형과 현재 유닛 자세를 다시 그리므로 이전 자세의 깊이를 재사용하지 않는다. '
        '렌더 대상과 읽기용 자원을 재사용하며, 유닛 버퍼는 현재 프레임의 정확한 크기만 보유한다. 자동 애니메이션의 반복 로그만 생략했다.\n\n'
        '운영 헤더를 사용하는 순수 CPU 캐시 검사와 소스 회귀 대조를 통과했다. 원래 지형·유닛·윤곽 수식과 애니메이션·입력 세대 검사는 유지했다. '
        '새 Host·SDK·창·GPU·게임은 실행하지 않았다. CPU 절감률·실제 프레임 시간·동작 중 잔상/클릭 판정 확인은 실행 보류 해제 뒤의 관문이다. '
        'D2D/문자 자원 생성과 유닛 CPU 계산 등 잔여 비용도 있으므로 CPU 문제 전체 해결이나 실측 성능을 선언하지 않는다.\n\n'
        'Windows의 cmd.exe가 이전 빌드 이후 바뀐 것은 사전부터 존재한 도구 차이였다. 이전 보고서를 수정하지 않고, '
        '현재 Microsoft 서명·SHA와 부모의 옛 두 행을 묶은 cmd 한정 선택을 추가했다. 나머지 제공자·게이트 검사는 유지했다. '
        '기록은 `evidence/game_menu/idle_render_cache/current_work.json`이다. `40a8`의 사용자 세션과 저장은 보호 대상으로 남겼다.\n\n')
    for name in ('docs/CLAUDE_HANDOFF.md','docs/ORIGINAL_MENUS_OFFLINE.md'):
        path=PROJECT/name;text=path.read_text('utf8');head,tail=text.split('\n',1)
        if name.endswith('CLAUDE_HANDOFF.md'):
            tail=tail.replace('최신 갱신: 2026-11-09','이전 갱신: 2026-11-09',1)
        else:
            tail=tail.replace('최신 Host는 `20261108','이전 Host는 `20261108',1)
            tail=tail.replace('현재 기록은 `evidence/game_menu/native_slider_hover/current_work.json`','직전 기록은 `evidence/game_menu/native_slider_hover/current_work.json`',1)
        path.write_text(head+'\n\n'+section+tail.lstrip('\n'),encoding='utf8')
    print(json.dumps(dict(status=value['status'],build_id=build_id,run_id=run_id)))

def close():
    path=STAGE/'current_work.json';value=read(path);assert value['storage']['after_pending']
    protection=read(STAGE/'protection_after.json');assert protection['status']=='PASS'
    before=read(STAGE/'storage_before.json');after=read(STAGE/'storage_after.json')
    value['protection'].update(after=ref(STAGE/'protection_after.json'),after_pending=False)
    value['storage'].update(after=ref(STAGE/'storage_after.json'),after_pending=False,
        before_unique_allocated_bytes=before['unique_allocated_bytes'],after_unique_allocated_bytes=after['unique_allocated_bytes'],
        allocated_bytes_change=after['unique_allocated_bytes']-before['unique_allocated_bytes'],
        measurement='One FileStandardInfo allocation per real os.stat identity; receipt creation and final small record updates follow the scan.')
    save(path,value)
    current=PROJECT/'evidence/save_menu/20261013_original_screen/current_progress.json'
    progress=read(current);progress['current_offline_stage']=ref(path);save(current,progress)
    print(json.dumps(dict(status='PASS_CLOSED_OFFLINE_IDLE_CACHE_WORK',protected=protection['paths'],
        allocated_bytes_change=value['storage']['allocated_bytes_change'],native_attempts=0,measured_live_cpu_reduction_percent=None)))

if __name__=='__main__':
    cli=argparse.ArgumentParser();cli.add_argument('action',choices=['publish','close']);cli.add_argument('--build');cli.add_argument('--run');args=cli.parse_args()
    if args.action=='publish':publish(args.build,args.run)
    else:close()
