"""Publish evidence-based offline status; native acceptance remains deferred."""
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
    verified=read(STAGE/'prepared_runtime_verification.json')
    assert verified['status']=='PASS_SINGLE_CURRENT_PREPARED_RUNTIME_AND_FULL_SOURCE_CLOSURE_NOT_EXECUTED'
    build_id,run_id=verified['build_id'],verified['run_id'];pair=STAGE/'pair_preparation'/build_id
    build=read(verified['build_result']['path']);att=read(pair/'independent_attestation.json')
    counts=dict(compiler_dependency_count=att['compiler_input_count'],current_source_input_count=att['current_input_count'],
        frozen_input_count=att['frozen_input_count'],source_manifest_count=att['source_manifest_count'])
    assert counts['current_source_input_count']==verified['current_source_inputs_verified']
    assert counts['frozen_input_count']==verified['frozen_inputs_verified']
    proofs={key:ref(STAGE/path) for key,path in [('contract','contract/delivery.json'),('view','view/delivery.json'),
        ('binding','binding/delivery.json'),('integrated','integration/db7b393d669f766e/result.json'),
        ('embedded_catalog','embedded_options_revision2.result.json'),('migration_plan','migration_plan.json'),
        ('independent_source_review','independent_source_review_final.json')]}
    assert read(proofs['integrated']['path'])['protected_inputs_unchanged']
    component=ref(STAGE/'component_cleanup.json');before=read(STAGE/'storage_before.json')
    space=dict(before=ref(STAGE/'storage_before.json'),precompile=ref(STAGE/'storage_precompile.json'),
        before_unique_allocated_bytes=before['unique_allocated_bytes'],after_pending=not args.close_storage,
        measurement='FileStandardInfo.AllocationSize once per real os.stat identity; directories excluded.',
        confirmed_disposable_bytes=0,threshold_bytes=10*1024**3,full_project_copies_created=0)
    if args.close_storage:
        after=read(STAGE/'storage_after.json');assert not after['errors'] and not after.get('reparse_skipped')
        assert read(STAGE/'protection_after.json')['status']=='PASS'
        space.update(after=ref(STAGE/'storage_after.json'),after_unique_allocated_bytes=after['unique_allocated_bytes'],
            allocated_bytes_change=after['unique_allocated_bytes']-before['unique_allocated_bytes'],
            scope_note='Final scan includes then-existing evidence/docs/cleanup records; small closing status edits follow the scan.')
    host=dict(status='CURRENT_COMPILED_EXPLICIT_PREPARED_PROFILE_NOT_REGISTERED_OR_EXECUTED',build_id=build_id,
        executable=build['executable'],build_result=verified['build_result'],independent_attestation=ref(pair/'independent_attestation.json'),
        prepared_profile=verified['profile'],**counts,catalog_entries=74,original_ui_layouts=30,required_sidecar_files=154,
        registered=False,globally_registered=False,prepared_profile_only=True,host_executed=False,gamecore_loaded=False,
        screen_verification_deferred=True,full_engine_goal_complete=False)
    runtime=Path(verified['runtime_directory'])
    prepared=dict(status='CURRENT_EXPLICIT_REWARD_OPTIONS_V3_HOST_AND_UNCHANGED_SDK_PREPARED_NOT_EXECUTED',
        run_id=run_id,host_build_id=build_id,runtime_directory=str(runtime),host=verified['host'],gamecore=verified['gamecore'],
        bundle_manifest=ref(runtime/'bundle.manifest'),request=verified['request'],materialization=verified['materialization'],
        backend_inputs=24,sidecar_files=154,physical_file_paths=189,frozen_python_modules=6,
        native_attempts=0,new_game_only=True,cross_bundle_load_allowed=False,default_promoted=False)
    remaining=[
        'Actual Host/GameCore/window/GPU/gameplay/save/mod/multicore acceptance remains deferred and incomplete.',
        'Reward popup/notification behavior in the five actual SDK consumers is source-verified only; no native reward event was executed.',
        'Seven supported front-end preference categories are connected, including conditional policy info; full original options and remaining menu branches need real backends.',
        'Actual display readback/confirmation timing/focus/close rollback and native UI geometry/filter/font equivalence are unexecuted.',
        'ReplayMap remains simplified; original3D map, retail replay wrapper/catalog and full original Lua execution are incomplete.',
        'Original map slider WheelSteps10, four WindowTrim candidates and absent season localization keys remain open.',
        'Private V1/V2 bytes are read unchanged; changed successful commits write planned V3. This is not a game-save or Mod-schema migration.'
    ]
    current=dict(schema='zerosis.options_reward_popups.current_work.v1',utc=datetime.now(timezone.utc).isoformat(),
        status='PASS_CURRENT_X64_REWARD_OPTIONS_V3_PAIR_PREPARED_OFFLINE',goal_turn_classification='progress',
        full_goal_redefined=False,full_engine_goal_complete=False,requirements=ref(STAGE/'requirements.json'),
        migration_plan=ref(STAGE/'migration_plan.json'),current_host=host,current_prepared_runtime=prepared,
        working_source_matches_current_frozen_and_prepared_profile=True,proofs=proofs,
        immutable_assets=ref(PROJECT/'evidence/game_menu/replay_calendar_legend/legend/assets_v3.json'),
        source_manifest=verified['source_manifest'],intermediate_cleanup=ref(pair/'cleanup_result.json'),component_cleanup=component,
        current_and_recovery_preserved=['current/new-runtime','recent8837/1fba','earlier ee8c/9a1 and829/01dfa closure inputs',
            'older requireddeb/4f194/613f/f127 snapshots','requiredbc34donor','registeredHost4/prior424fb','default732/usercbbdsaves'],
        storage=space,remaining=remaining,native_execution=False,current_native_or_screen_relaunch_allowed=False,
        screen_verification_deferred=True,default_or_registration_changed=False)
    write(STAGE/'current_work.json',current)
    compile_proof=dict(status='PASS_FIVE_ACTUAL_CXX14_TRANSLATION_UNITS_COMPILED_AND_LINKED_OFFLINE',
        build_id=build_id,build_result=verified['build_result'],prepared_pair_verification=ref(STAGE/'prepared_runtime_verification.json'),
        **counts,catalog_entries=74,required_sidecar_files=154,host_executed=False,SDK_executed=False,native_acceptance=False)
    path=PROJECT/'evidence/save_menu/20261013_original_screen/current_progress.json';progress=read(path)
    scope=f"Current {build_id}: {counts['current_source_input_count']} current and {counts['frozen_input_count']} frozen inputs, {counts['compiler_dependency_count']} compiler dependencies,74payloads,154V3 sidecars and189runtime files verified. No Host/SDK execution or default/global registration change."
    progress.update(utc=current['utc'],status=current['status'],full_engine_goal_complete=False,current_goal_turn_classification='progress',
        current_host_build_id=build_id,current_host_build=host,current_prepared_runtime=prepared,latest_host_sdk_preparation_stage=prepared,
        latest_private_prepared_pair_matches_current_host_and_selected_sdk_sources=True,prepared_runtime_matches_current_linked_candidate=True,
        prepared_runtime_matches_latest_source=True,latest_source_matches_integrated_syntax_proof=True,latest_source_matches_linked_candidate=True,
        latest_cpp_source_matches_actual_host_syntax_proof=True,latest_current_source_actual_cpp_compilation_verified=True,
        latest_host_source_matches_current_link_proof=True,latest_integrated_syntax_proof=compile_proof,
        latest_current_source_compile_link_proof=compile_proof,latest_actual_host_syntax_proof=compile_proof,
        latest_current_source_actual_cpp_compilation_verified_proof=compile_proof,latest_current_source_pe_attestation=ref(pair/'independent_attestation.json'),
        latest_host_source_matches_current_link_proof_scope=scope,latest_source_matches_linked_candidate_scope=scope,
        latest_actual_host_syntax_proof_scope='Five actual C++14 units compiled and linked offline, fp:strict, zero warnings. Host/SDK unexecuted.',
        limits=remaining,screen_verification_deferred=True,current_native_or_screen_relaunch_allowed=False,host_executed=False,
        gamecore_loaded=False,hwnd_created=False,gpu_executed=False,default_promoted=False,native_acceptance_complete=False)
    progress['options_reward_popups_stage']=dict(current,record=ref(STAGE/'current_work.json'))
    progress.setdefault('storage',{})['latest_options_reward_popups_wave']=space
    progress['storage']['older_fields_are_prior_wave_history']=True
    write(path,progress)
    if not args.close_storage:
        doc=PROJECT/'docs/ORIGINAL_MENUS_OFFLINE.md';old=doc.read_text('utf8');tail=old[old.index('효과음 설정은'):]
        top=f'''# 원본 메뉴 복원과 격리 실행 묶음 — 실제 실행 보류

최신 Host는 `{build_id}`, 별도 준비본은 `{run_id}`이다. 현재 소스 {counts['current_source_input_count']}개·동결 입력 {counts['frozen_input_count']}개·컴파일 의존 {counts['compiler_dependency_count']}개를 대조했다. C++14 다섯 단위의 실제 컴파일·링크와 독립 검사에서 경고0개다. Host·SDK·창·GPU·음향·실제 게임 실행은0회다.

| 이번 범위 | 구현 결과 | 검증 경계 |
|---|---|---|
| 보상 알림 없음 | 원본 체크 상자·한국어·콜백, 보상/기본 도움말 순서와15px 간격 복원 | 기존32px 후보 계약을 유지한 소스/CPU 검사이며 원본 네이티브 기본 크기 판정은 보류 |
| 실제 엔진 조회 | 유적·기술·불가사의·자연경관·걸작의 기존 SDK 조회가 확정 원자값을 읽음 | SDK 규칙·보상 수치·DLL은 그대로, 실제 보상 이벤트 실행은 보류 |
| 저장 경계 | 이전 V1/V2를 무수정 읽기, 새 항목 기본false, 변경 성공 시에만 명시된 V3 이전 | 저장 전·실패·취소·별도 해상도 적용은 확정값에 전달하지 않음 |
| 화면 확인 흐름 | 기존20초 확인·예/아니오·시간 초과·복구·부분 확정 유지 | 전체 수락은 보상 초안을 먼저 저장하고 해상도 확인; 화면 거절이 저장된 보상 설정을 되돌리지 않음 |
| 실행 묶음 | 실제 최신 x64 Host와 기존 SDK430·154개 V3 자산을189파일 묶음으로 연결 | 파일만 준비, 기본 실행/등록/저장 파일은 변경하지 않음 |

체크 상자 그림·글꼴·텍스처 묶음을 복제하지 않았다. 기존74개 임베드 중3개 텍스트 payload만 갱신했고 나머지71개와 음향/글꼴 바이트를 보존했다. 소프트웨어 진단 이미지는 실제 인게임 화면이 아니다.

현재 기록은 `evidence/game_menu/options_reward_popups/current_work.json`, 전체 원본 목표의 미완료 항목은 그 기록의 `remaining`이다. 화면 확인 보류는 계속 유지한다. 실제 플레이·원본3D·전체 UI·저장/모드/멀티코어 안정성은 완료로 보고하지 않는다.

'''
        doc.write_text(top+tail,encoding='utf8')
        hud=PROJECT/'docs/ORIGINAL_WORLD_HUD.md';body=hud.read_text('utf8').split('\n\n',1)[1]
        hud.write_text(f'> 2026-11-06: Current Host `{build_id}` and unchanged SDK430 are prepared in `{run_id}` with full current/frozen closure and189runtime files verified. Original reward preference now uses private V3 planned migration and committed atomic publication; previous video/replay work is retained. Native acceptance remains held. See [original menu offline scope](ORIGINAL_MENUS_OFFLINE.md).\n\n'+body,encoding='utf8')
    print(json.dumps(dict(status=current['status'],runtime=run_id,counts=counts,storage_pending=space['after_pending'],full_engine_goal_complete=False)))


if __name__=='__main__':main()
