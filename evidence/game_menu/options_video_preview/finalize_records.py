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
    prepared=dict(status='CURRENT_EXPLICIT_VIDEO_CONFIRMATION_HOST_AND_SDK_PREPARED_NOT_EXECUTED_SCREEN_DEFERRED',
        run_id=run_id,host_build_id=build_id,runtime_directory=str(runtime),host=verification['host'],gamecore=verification['gamecore'],
        bundle_manifest=ref(runtime/'bundle.manifest'),request=verification['request'],materialization=verification['materialization'],
        backend_inputs=24,sidecar_files=154,physical_file_paths=189,frozen_python_modules=6,
        native_attempts=0,new_game_only=True,cross_bundle_load_allowed=False,default_promoted=False)
    compile_proof=dict(status='PASS_FIVE_ACTUAL_CXX14_TRANSLATION_UNITS_COMPILED_AND_LINKED_OFFLINE',
        build_id=build_id,build_result=verification['build_result'],prepared_pair_verification=ref(STAGE/'prepared_runtime_verification.json'),
        **counts,catalog_entries=74,required_sidecar_files=154,host_executed=False,SDK_executed=False,native_acceptance=False)
    remaining=[
        'Actual Host/GameCore/window/GPU/gameplay/save/mod/multicore acceptance is deferred and incomplete.',
        'Real display mode/readback/confirmation-visible interval/focus/close rollback remain unexecuted; controlled fake-backend and exact-source proofs do not close native acceptance.',
        'Only six existing supported options are connected; full original options and remaining main-menu branches still need real backend support.',
        'ReplayMap is simplified; original3D map, retail replay wrapper/catalog and full original Lua execution remain unsupported.',
        'Original map slider WheelSteps10, native widget/gutter/filter/anti-alias and six legacy font equivalence remain unverified. Four WindowTrim candidates remain open.',
        'Original season localization keys are absent; SEASONS dates remain unavailable; other calendar types remain independent.',
        'NoRewardPopups has a real SDK read boundary but remains a future preference/UI implementation; worker options require separate Host-preference and SDK-current-value contracts. No rule/balance change was made.',
        'The private preferences still read V1/V2 and atomically write unchanged V2. No new settings, persistent schema or game-save compatibility claim was introduced.'
    ]
    proofs=dict(countdown=ref(STAGE/'countdown/delivery.json'),session=ref(STAGE/'session/delivery.json'),
        view=ref(STAGE/'view/delivery.json'),integrated=ref(STAGE/'integration/0c4bec2367f66b83/result.json'),
        software_visual_review=ref(STAGE/'integration/scene_visual_review.json'))
    current=dict(schema='zerosis.options_video_preview.current_work.v1',utc=datetime.now(timezone.utc).isoformat(),
        status='PASS_CURRENT_X64_ORIGINAL_VIDEO_CONFIRMATION_PAIR_PREPARED_OFFLINE',
        goal_turn_classification='progress',full_goal_redefined=False,full_engine_goal_complete=False,
        requirements=ref(STAGE/'requirements.json'),requirements_addendum=ref(STAGE/'requirements_addendum.json'),current_host=host,current_prepared_runtime=prepared,
        working_source_matches_current_frozen_and_prepared_profile=True,proofs=proofs,
        immutable_assets=ref(PROJECT/'evidence/game_menu/replay_calendar_legend/legend/assets_v3.json'),
        source_manifest=verification['source_manifest'],intermediate_cleanup=ref(pair/'cleanup_result.json'),
        component_cleanup=ref(component_cleanup),
        current_and_recovery_preserved=['current/new-runtime','recentee8c/9a1','recovery829/01dfa','older requireddeb/4f194/613f/f127 snapshots','requiredbc34donor',
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
    progress['options_video_preview_stage']=dict(current,record=ref(STAGE/'current_work.json'))
    progress.setdefault('storage',{})['latest_options_video_preview_wave']=storage
    progress['storage']['older_fields_are_prior_wave_history']=True
    write(path,progress)
    if not args.close_storage:
        doc=PROJECT/'docs/ORIGINAL_MENUS_OFFLINE.md';old=doc.read_text('utf8');tail=old[old.index('효과음 설정은'):]
        top=f'''# 원본 메뉴 복원과 격리 실행 묶음 — 실제 실행 보류

최신 Host는 `{build_id}`, 별도 준비본은 `{run_id}`이다. 현재 소스 {counts['current_source_input_count']}개·동결 입력 {counts['frozen_input_count']}개·컴파일 의존 {counts['compiler_dependency_count']}개를 대조했다. C++14 다섯 단위의 실제 컴파일·링크와 독립 검사에서 경고0개다. Host·SDK·창·GPU·음향·실제 화면 전환 실행은0회다.

| 지원 화면 설정 흐름 | 이번 복원 | 확인 범위 |
|---|---|---|
| 해상도 적용 | 원본 ApplyResButton과20초 확인 창, 해상도·전체화면만 미리 적용 | 기존 실제 적용/판독/복원 경계에 연결. 다른 초안은 유지 |
| 수락 | 원본 OnOK처럼 지원하는 비해상도 설정을 먼저 확정한 뒤 화면 미리보기 | 비해상도 설정은 거절해도 유지, 별도 적용과 구분 |
| 예 | 현재 표시값만 확정하고 복귀 기준 갱신, 옵션 창 유지 | 기존 V2의 필드·순서·스키마로 원자 기록, 나머지 초안 유지 |
| 아니오·시간 초과·Esc | 직전 확정 표시값으로 복구하고 옵션 창 유지 | 실제 모델/세션과 가짜 표시부에서 복구·오류·오너 계약 확인 |
| 종료·오류 | 소유한 미리보기를 복구한 뒤 취소, 복구 실패 시 세션 중지 | 창보다 모델이 먼저 정리되는 수명과 콜백 해제 확인 |
| 시간 기준 | 화면 적용이 끝난 순간부터 시작, 이후 지연은 제한 없이 계산 | 적용에21초가 걸린 경우와 이후60초 멈춤을 별개로 검사 |

원본 Lua 타이머103사례/4348상태·콜백흐름10사례, 순수 타이머30568검사, 세션2866검사, 원본 배치53928검사와 최종 본체5467검사를 통과했다. 화면과 음향 처리부는 실행하지 않았으며 소프트웨어 진단 이미지를 실제 게임 화면으로 제시하지 않는다. 현재 V3의 그림·글꼴을 그대로 재사용했다.

현재 기록: `evidence/game_menu/options_video_preview/current_work.json`. 독립 묶음 검사: 같은 폴더 `prepared_runtime_verification.json`. 최근ee8c/9a1·복구829/01dfa·필요한 구형 동결 입력·기본 실행본·사용자 저장을 보존한다. 전체 원본 옵션·주 메뉴 분기·원본3D·전체 Lua·글꼴·실게임 저장/모드/멀티코어 검증은 남아 있다.

'''
        tail=tail.replace('그래프 원본65,536점과 모든 표시 점을 유지하고 연결선 그리기만 제한한다.','그래프는 원본100구간·101표본 위치 정책으로 표시하며 원자료를 그대로 보존한다.')
        tail=tail.replace('진척·근거·정리·용량은 `evidence/game_menu/menu_runtime_ui_followup/current_work.json`에 기록한다.','최신 진척·근거·정리·용량은 위 현재 기록 경로에 기록한다.')
        doc.write_text(top+tail,encoding='utf8')
        hud=PROJECT/'docs/ORIGINAL_WORLD_HUD.md';body=hud.read_text('utf8').split('\n\n',1)[1]
        hud.write_text(f'> 2026-11-05: Current Host `{build_id}` and SDK430 are prepared in isolated runtime `{run_id}`. Full current/frozen source closure and189runtime files verified. Original supported video confirmation/rollback flow restored with unchanged V1/V2 preferences and reused V3 assets; source graph/messages/guides preserved. Native/screen acceptance remains held; default/registered/recent/recovery preserved. See [original menu offline scope](ORIGINAL_MENUS_OFFLINE.md).\n\n'+body,encoding='utf8')
    print(json.dumps(dict(status=current['status'],runtime=run_id,counts=counts,storage_pending=storage['after_pending'],full_engine_goal_complete=False)))


if __name__=='__main__':main()
