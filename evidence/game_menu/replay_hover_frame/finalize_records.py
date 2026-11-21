"""Record the verified offline source/bundle state without claiming native acceptance."""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path

STAGE=Path(__file__).absolute().parent
PROJECT=STAGE.parents[2]


def read(path):return json.loads(Path(path).read_text('utf8'))
def write(path,value):Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
def ref(path):
    path=Path(path).absolute();raw=path.read_bytes()
    return dict(path=str(path),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())


def main():
    cli=argparse.ArgumentParser();cli.add_argument('--close-storage',action='store_true');args=cli.parse_args()
    verification=read(STAGE/'prepared_runtime_verification.json')
    assert verification['status']=='PASS_SINGLE_CURRENT_PREPARED_RUNTIME_AND_FULL_SOURCE_CLOSURE_NOT_EXECUTED'
    build_id,run_id=verification['build_id'],verification['run_id']
    pair=STAGE/'pair_preparation'/build_id
    build=read(verification['build_result']['path']);att=read(pair/'independent_attestation.json')
    runtime=Path(verification['runtime_directory'])
    counts=dict(compiler_dependency_count=att['compiler_input_count'],current_source_input_count=att['current_input_count'],
        frozen_input_count=att['frozen_input_count'],source_manifest_count=att['source_manifest_count'])
    assert counts['current_source_input_count']==verification['current_source_inputs_verified']
    assert counts['frozen_input_count']==verification['frozen_inputs_verified']
    component_cleanup=STAGE/'component_cleanup.json'
    assert component_cleanup.is_file()
    before=read(STAGE/'storage_before.json')
    storage=dict(before=ref(STAGE/'storage_before.json'),precompile=ref(STAGE/'storage_precompile.json'),
        before_unique_allocated_bytes=before['unique_allocated_bytes'],after_pending=not args.close_storage,
        measurement='FileStandardInfo.AllocationSize, once per real os.stat identity; directories excluded.',
        confirmed_disposable_bytes=0,threshold_bytes=10*1024**3,full_project_copies_created=0)
    if args.close_storage:
        after=read(STAGE/'storage_after.json');assert not after['errors'] and not after.get('reparse_skipped')
        storage.update(after=ref(STAGE/'storage_after.json'),after_unique_allocated_bytes=after['unique_allocated_bytes'],
            allocated_bytes_change=after['unique_allocated_bytes']-before['unique_allocated_bytes'],
            scope_note='Final scan includes then-existing status/documentation/cleanup proofs; small closing status edits follow the scan.')
    host=dict(status='CURRENT_COMPILED_EXPLICIT_PREPARED_PROFILE_NOT_REGISTERED_OR_EXECUTED',
        build_id=build_id,executable=build['executable'],build_result=verification['build_result'],
        independent_attestation=ref(pair/'independent_attestation.json'),prepared_profile=verification['profile'],
        **counts,catalog_entries=74,original_ui_layouts=30,required_sidecar_files=154,
        registered=False,globally_registered=False,prepared_profile_only=True,host_executed=False,gamecore_loaded=False,
        screen_verification_deferred=True,full_engine_goal_complete=False)
    prepared=dict(status='CURRENT_EXPLICIT_REPLAY_POINTER_GUIDE_GRID_CAP_HOST_AND_SDK_PREPARED_NOT_EXECUTED_SCREEN_DEFERRED',
        run_id=run_id,host_build_id=build_id,runtime_directory=str(runtime),host=verification['host'],gamecore=verification['gamecore'],
        bundle_manifest=ref(runtime/'bundle.manifest'),request=verification['request'],materialization=verification['materialization'],
        backend_inputs=24,sidecar_files=154,physical_file_paths=189,frozen_python_modules=6,
        native_attempts=0,new_game_only=True,cross_bundle_load_allowed=False,default_promoted=False)
    compile_proof=dict(status='PASS_FIVE_ACTUAL_CXX14_TRANSLATION_UNITS_COMPILED_AND_LINKED_OFFLINE',
        build_id=build_id,build_result=verification['build_result'],prepared_pair_verification=ref(STAGE/'prepared_runtime_verification.json'),
        **counts,catalog_entries=74,required_sidecar_files=154,host_executed=False,SDK_executed=False,native_acceptance=False)
    remaining=[
        'Actual Host/GameCore/window/GPU/gameplay/save/mod/multicore acceptance remains deferred and incomplete.',
        'Full original options and main-menu branches need more backend support; current options cover six supported settings.',
        'ReplayMap remains simplified; original3D map, retail replay wrapper/catalog and full original Lua execution remain unsupported.',
        'Original map slider WheelSteps10 semantics remain unproven and that wheel action is not implemented.',
        'Native widget/gutter/cap/filter/anti-alias and glyph equivalence remain unverified. Four WindowTrim resampling candidates remain open; the confirmed Grid9 corner stretching is fixed.',
        'Original season localization keys are absent; SEASONS dates remain unavailable; other calendar types are independent.',
        'Six legacy font faces are preserved; full modern Hangul coverage is proven only for the additional14px Shadow face.',
        'Original graph guides, source100-segment projection and continuous messages are restored in source; CPU and console proofs do not establish native screen or retail replay acceptance.'
    ]
    proofs=dict(guides=ref(STAGE/'guides/delivery.json'),frame=ref(STAGE/'frame/delivery.json'),
        pointer_sampling=ref(STAGE/'pointer_sampling/delivery.json'),
        input_batch=ref(STAGE/'input_batch/pointer_policy/result.json'),
        integrated_scene=ref(STAGE/'integration/scene/a0de38449720b88e/result.json'),
        software_visual_review=ref(STAGE/'integration/scene_visual_review.json'))
    current=dict(schema='zerosis.replay_hover_frame.current_work.v1',utc=datetime.now(timezone.utc).isoformat(),
        status='PASS_CURRENT_X64_ORIGINAL_POINTER_GUIDES_AND_GRID_CAP_PAIR_PREPARED_OFFLINE',
        goal_turn_classification='progress',full_goal_redefined=False,full_engine_goal_complete=False,
        requirements=ref(STAGE/'requirements.json'),current_host=host,current_prepared_runtime=prepared,
        working_source_matches_current_frozen_and_prepared_profile=True,proofs=proofs,
        immutable_assets=ref(PROJECT/'evidence/game_menu/replay_calendar_legend/legend/assets_v3.json'),
        source_manifest=verification['source_manifest'],intermediate_cleanup=ref(pair/'cleanup_result.json'),
        component_cleanup=ref(component_cleanup),
        current_and_recovery_preserved=['current/new-runtime','recent829/01dfa','recoverydeb/4f194','older required613f/f127 snapshots','requiredbc34donor',
            'registeredHost4/prior424fb','default732/usercbbdsaves'],
        storage=storage,remaining=remaining,native_execution=False,current_native_or_screen_relaunch_allowed=False,
        screen_verification_deferred=True,default_or_registration_changed=False)
    write(STAGE/'current_work.json',current)
    path=PROJECT/'evidence/save_menu/20261013_original_screen/current_progress.json';progress=read(path)
    scope=f"Current {build_id}: {counts['current_source_input_count']} current sources, {counts['frozen_input_count']} frozen inputs, {counts['compiler_dependency_count']} actual compiler dependencies,74payloads,154V3sidecars and189runtime files verified. Host/SDK unexecuted; default/global registration unchanged."
    progress.update(utc=current['utc'],status=current['status'],full_engine_goal_complete=False,current_goal_turn_classification='progress',
        current_host_build_id=build_id,current_host_build=host,current_prepared_runtime=prepared,
        latest_host_sdk_preparation_stage=prepared,latest_private_prepared_pair_matches_current_host_and_selected_sdk_sources=True,
        prepared_runtime_matches_current_linked_candidate=True,prepared_runtime_matches_latest_source=True,
        latest_source_matches_integrated_syntax_proof=True,latest_source_matches_linked_candidate=True,
        latest_cpp_source_matches_actual_host_syntax_proof=True,latest_current_source_actual_cpp_compilation_verified=True,
        latest_host_source_matches_current_link_proof=True,latest_integrated_syntax_proof=compile_proof,
        latest_current_source_compile_link_proof=compile_proof,latest_actual_host_syntax_proof=compile_proof,
        latest_current_source_actual_cpp_compilation_verified_proof=compile_proof,
        latest_current_source_pe_attestation=ref(pair/'independent_attestation.json'),
        latest_host_source_matches_current_link_proof_scope=scope,latest_source_matches_linked_candidate_scope=scope,
        latest_actual_host_syntax_proof_scope='Five actual C++14 units compiled and linked, fp:strict, zero warnings. No Host/SDK execution.',
        limits=remaining,screen_verification_deferred=True,current_native_or_screen_relaunch_allowed=False,
        host_executed=False,gamecore_loaded=False,hwnd_created=False,gpu_executed=False,default_promoted=False,native_acceptance_complete=False)
    progress['replay_hover_frame_stage']=dict(current,record=ref(STAGE/'current_work.json'))
    progress.setdefault('storage',{})['latest_replay_hover_frame_wave']=storage
    progress['storage']['older_fields_are_prior_wave_history']=True
    write(path,progress)
    if not args.close_storage:
        doc=PROJECT/'docs/ORIGINAL_MENUS_OFFLINE.md';old=doc.read_text('utf8');tail=old[old.index('효과음 설정은'):]
        top=f'''# 원본 메뉴 복원과 격리 실행 묶음 — 실제 실행 보류

최신 Host는 `{build_id}`, 별도 준비본은 `{run_id}`이다. 현재 소스 {counts['current_source_input_count']}개·동결 입력 {counts['frozen_input_count']}개·컴파일 의존 {counts['compiler_dependency_count']}개를 대조했다. C++14 다섯 단위 컴파일·링크와 독립 검사에서 경고0개다. Host·SDK·창·GPU·실제 포인터 조회 실행은0회다.

| 영역 | 이번 변경 | 검증과 남은 부분 |
|---|---|---|
| 재생 그래프 마우스 안내 | 원본 엄격 내부 경계·십자선2개·빨간8픽셀 축 안내2개·원본 RGBA/순서 | 원본 Lua685사례, C++6299검사. 데이터 없음 문구는 원본처럼 안내선 위에 표시. 실제 화면 합격은 보류 |
| 현재 마우스 위치 | 정지 포인터와 화면 재진입에도 현재 좌표를 샘플, 창밖/조회실패는 숨김 | 실제 메서드를 추출한 가짜 조회10508검사/2630샘플, 창 코드 컴파일만 수행. 기존 입력 큐·캡처·이동/이탈 경로 보존 |
| 원본 테두리 | 아래 모서리50픽셀·중앙70픽셀의 개별 원본 조각 크기 보존 | 실제16스타일×4상태×29크기,77411검사. 대칭·가로/세로 조각과 원본 장식 위치 보존 |
| 통합 화면·입력 | 안내선은 버튼 영역과 기록을 바꾸지 않으며, key0/뒤로 hover도 후속 클릭을 버리지 않음 | 최종319366통합검사와2786입력정책검사. 소프트웨어 진단PNG는 동일 바이트를 재사용하고 실제 실행 화면으로 제시하지 않음 |
| 별도 실행 묶음 | 새 Host+기존SDK430, 변경 없는 자산154개·백엔드24개·Python지원6개·실제189개 파일 | 전체 현재 소스·동결 입력·묶음 대조. 새 게임 전용, 기본 승격·실게임 실행 없음 |

이전의 원본100구간 그래프·연속 메시지·지도 floor 턴 선택과 원문 보존은 유지한다. 전체 옵션·나머지 주 메뉴 기능, 원본3D·재생 파일 포장·전체 Lua·글꼴, 실제 위젯·필터·저장·모드·멀티코어 검증은 남아 있다.

현재 기록: `evidence/game_menu/replay_hover_frame/current_work.json`. 독립 묶음 검사: 같은 폴더 `prepared_runtime_verification.json`. 최근829/01dfa·복구deb/4f194·필요한 구형 동결 입력·기본 실행본·사용자 저장을 보존한다.

'''
        doc.write_text(top+tail,encoding='utf8')
        hud=PROJECT/'docs/ORIGINAL_WORLD_HUD.md';body=hud.read_text('utf8').split('\n\n',1)[1]
        hud.write_text(f'> 2026-11-05: Current Host `{build_id}` and SDK430 are prepared in isolated runtime `{run_id}`. Full current/frozen source closure and189runtime files verified. Original pointer guides/current-position sampling and authored grid cap sizes restored; source100-segment graph and continuous messages preserved. Native/screen acceptance remains held; default/registered/recent/recovery preserved. See [original menu offline scope](ORIGINAL_MENUS_OFFLINE.md).\n\n'+body,encoding='utf8')
    print(json.dumps(dict(status=current['status'],runtime=run_id,counts=counts,storage_pending=storage['after_pending'],full_engine_goal_complete=False)))


if __name__=='__main__':main()
