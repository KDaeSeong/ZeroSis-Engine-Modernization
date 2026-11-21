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
    prepared=dict(status='CURRENT_EXPLICIT_REPLAY_SCROLL_GRAPH_HOST_AND_SDK_PREPARED_NOT_EXECUTED_SCREEN_DEFERRED',
        run_id=run_id,host_build_id=build_id,runtime_directory=str(runtime),host=verification['host'],gamecore=verification['gamecore'],
        bundle_manifest=ref(runtime/'bundle.manifest'),request=verification['request'],materialization=verification['materialization'],
        backend_inputs=24,sidecar_files=154,physical_file_paths=189,frozen_python_modules=6,
        native_attempts=0,new_game_only=True,cross_bundle_load_allowed=False,default_promoted=False)
    compile_proof=dict(status='PASS_FIVE_ACTUAL_CXX14_TRANSLATION_UNITS_COMPILED_AND_LINKED_OFFLINE',
        build_id=build_id,build_result=verification['build_result'],prepared_pair_verification=ref(STAGE/'prepared_runtime_verification.json'),
        **counts,catalog_entries=74,required_sidecar_files=154,host_executed=False,SDK_executed=False,native_acceptance=False)
    remaining=[
        'Actual Host/GameCore/window/GPU/gameplay/save/mod/multicore acceptance is deferred and incomplete.',
        'Full original options and main-menu branches need additional backend support; current options cover six supported settings.',
        'ReplayMap remains simplified; original3D map, retail replay wrapper/catalog, full original Lua and graph mouse guides remain unsupported.',
        'Original map slider WheelSteps10 semantics are not proven and that wheel action is not implemented; no guessed native policy was added.',
        'Native scrollbar minimum/gutter/widget/cap/filter/anti-alias equivalence remains unverified. Four WindowTrim resampling candidates and bottom-frame trim fidelity remain open.',
        'Original season localization keys are absent; SEASONS dates remain unavailable without inventing labels; other calendar types remain independent.',
        'Six legacy font faces are preserved; full modern Hangul coverage is proven only for the additional14px Shadow face.',
        'Source-backed graph100-segment projection is restored and raw histories retained; this does not prove retail replay format or native pixel acceptance.'
    ]
    proofs=dict(scroll=ref(STAGE/'scroll_model/result.json'),graph=ref(STAGE/'graph/fixture_result.json'),
        viewport=ref(STAGE/'message_viewport/result.json'),lines=ref(STAGE/'lines/delivery.json'),
        input_batch=ref(STAGE/'input_batch/delivery.json'),
        cpu_lines=ref(STAGE/'cpu_lines/attempt_10576ffd40397109e280/result.json'),
        integrated_scene=ref(STAGE/'integration/scene/1c02f8367cb0b8db/result.json'),
        software_visual_review=ref(STAGE/'integration/scene_visual_review.json'))
    current=dict(schema='zerosis.replay_scroll_graph.current_work.v1',utc=datetime.now(timezone.utc).isoformat(),
        status='PASS_CURRENT_X64_REPLAY_CONTINUOUS_SCROLL_ORIGINAL_GRAPH_PAIR_PREPARED_OFFLINE',
        goal_turn_classification='progress',full_goal_redefined=False,full_engine_goal_complete=False,
        requirements=ref(STAGE/'requirements.json'),current_host=host,current_prepared_runtime=prepared,
        working_source_matches_current_frozen_and_prepared_profile=True,proofs=proofs,
        immutable_assets=ref(PROJECT/'evidence/game_menu/replay_calendar_legend/legend/assets_v3.json'),
        source_manifest=verification['source_manifest'],intermediate_cleanup=ref(pair/'cleanup_result.json'),
        component_cleanup=ref(component_cleanup),permission_failure_resolution=ref(STAGE/'host_build/permission_resolution.json'),
        current_and_recovery_preserved=['current829/new-runtime','recentdeb/4f194','recovery613f/f127','requiredbc34donor',
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
    progress['replay_scroll_graph_stage']=dict(current,record=ref(STAGE/'current_work.json'))
    progress.setdefault('storage',{})['latest_replay_scroll_graph_wave']=storage
    progress['storage']['older_fields_are_prior_wave_history']=True
    write(path,progress)
    if not args.close_storage:
        doc=PROJECT/'docs/ORIGINAL_MENUS_OFFLINE.md';old=doc.read_text('utf8');tail=old[old.index('효과음 설정은'):]
        top=f'''# 원본 메뉴 복원과 격리 실행 묶음 — 실제 실행 보류

최신 Host는 `{build_id}`, 별도 실행 준비본은 `{run_id}`이다. 실제 소스 {counts['current_source_input_count']}개, 동결 입력 {counts['frozen_input_count']}개와 컴파일 의존 {counts['compiler_dependency_count']}개를 대조했다. C++14 다섯 단위의 실제 컴파일·링크, 독립 파일 검사가 통과했으며 경고는0개다. Host·SDK·창·GPU·게임 실행은0회다.

| 영역 | 이번 반영 | 검증과 남은 부분 |
|---|---|---|
| 지도 이동 막대 | 원본 floor 턴 선택,32픽셀 손잡이, 실제 누름 위치·합쳐진 첫 이동·해제·취소 | 소스 입력 연결 통과. 원본 WheelSteps10과 실제 위젯 정책은 미지원·미검증 |
| 재생 메시지 | 페이지 이동 대신 원본 연속 스택, 행 간격·63픽셀 끝 여백, 소수 스크롤·보이는 행만 표시 | 1MiB문장·빈 기록100,000개, 연속 범위·원문 보존 통합 검사. 네이티브 위젯 일치는 보류 |
| 재생 그래프 | 원본100구간·101표본, 정수 좌표·희소 기록의 끊김·최대값/눈금·폭1선 | 원본 Lua111사례 대조, 최대65,536개 원자료/6,400개 선분 연결. 점 표시는 원본에 없어 제거 |
| 실제 입력 경로 | 연속 휠·드래그 배치 유실 수정, Home/End/Page Up/Page Down 전달 | 순수 공유 정책2,784검사와 실제 창 소스 컴파일. 모달·클릭·뒤로 경계 유지 |
| 실행 묶음 | 새 Host+기존 SDK430, 자산154개 재사용, 백엔드24개·Python지원6개·실제189개 파일 | 전체 소스/동결/묶음 대조. 새 게임 전용, 기본 승격·실게임 실행 없음 |

통합 Scene 검사는312,868개를 통과했다. 화면 이미지는 순수 소프트웨어 진단이며 실제 게임 화면 증거가 아니다. 전체 옵션·나머지 주 메뉴 기능, 원본3D와 재생 파일 포장, 전체 원본 Lua·글꼴 및 테두리/위젯/필터 일치, 저장·모드·멀티코어의 실사용 검증은 남아 있다.

현재 기록: `evidence/game_menu/replay_scroll_graph/current_work.json`. 독립 묶음 검사: 같은 폴더 `prepared_runtime_verification.json`. 최근deb/4f194, 복구613f/f127, 필요한 부모·기본 실행본과 사용자 저장을 보존했다.

'''
        doc.write_text(top+tail,encoding='utf8')
        hud=PROJECT/'docs/ORIGINAL_WORLD_HUD.md';body=hud.read_text('utf8').split('\n\n',1)[1]
        hud.write_text(f'> 2026-11-05: Current Host `{build_id}` and SDK430 are prepared in isolated runtime `{run_id}`. Full current/frozen source closure and189runtime files verified. Original replay scroll/100-segment graph source restored. Native/screen acceptance remains held; default/registered/recent/recovery preserved. See [original menu offline scope](ORIGINAL_MENUS_OFFLINE.md).\n\n'+body,encoding='utf8')
    print(json.dumps(dict(status=current['status'],runtime=run_id,counts=counts,storage_pending=storage['after_pending'],full_engine_goal_complete=False)))


if __name__=='__main__':main()
