"""Maintain current progress/documentation for the verified offline wave."""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path

STAGE=Path(__file__).absolute().parent
PROJECT=STAGE.parents[2]
BUILD='20261104T131943Z_deb06f03ff1f'
RUN='20261104T132911Z_4f194ae38472'


def read(path):return json.loads(Path(path).read_text('utf8'))
def write(path,value):Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
def ref(path):
    path=Path(path).absolute();raw=path.read_bytes()
    return dict(path=str(path),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())


def main():
    cli=argparse.ArgumentParser();cli.add_argument('--close-storage',action='store_true');args=cli.parse_args()
    verification=read(STAGE/'prepared_runtime_verification.json')
    assert verification['status']=='PASS_SINGLE_CURRENT_PREPARED_RUNTIME_AND_FULL_SOURCE_CLOSURE_NOT_EXECUTED'
    pair=STAGE/'pair_preparation'/BUILD
    build=read(PROJECT/'evidence/ui_window_host'/BUILD/'build_result.json')
    att=read(pair/'independent_attestation.json')
    runtime=Path(verification['runtime_directory'])
    materialization=Path(verification['materialization']['path'])
    before=read(STAGE/'storage_before.json')
    storage=dict(before=ref(STAGE/'storage_before.json'),precompile=ref(STAGE/'storage_precompile.json'),
        before_unique_allocated_bytes=before['unique_allocated_bytes'],after_pending=not args.close_storage,
        measurement='FileStandardInfo.AllocationSize, once per real os.stat file identity; directories excluded.',
        threshold_bytes=10*1024**3,confirmed_disposable_bytes=0,full_project_copies_created=0)
    if args.close_storage:
        after=read(STAGE/'storage_after.json');assert not after['errors'] and not after.get('reparse_skipped')
        storage.update(after=ref(STAGE/'storage_after.json'),after_unique_allocated_bytes=after['unique_allocated_bytes'],
            allocated_bytes_change=after['unique_allocated_bytes']-before['unique_allocated_bytes'],
            scope_note='Final scan includes then-existing documentation/status and cleanup proofs; small closing status edits are written after the scan.')
    current_host=dict(status='CURRENT_COMPILED_EXPLICIT_PREPARED_PROFILE_NOT_REGISTERED_OR_EXECUTED',build_id=BUILD,
        executable=build['executable'],build_result=verification['build_result'],
        independent_attestation=ref(pair/'independent_attestation.json'),prepared_profile=verification['profile'],
        registered=False,globally_registered=False,prepared_profile_only=True,
        compiler_dependency_count=573,current_source_input_count=707,frozen_input_count=707,
        source_manifest_count=att['source_manifest_count'],catalog_entries=74,original_ui_layouts=30,required_sidecar_files=154,
        host_executed=False,gamecore_loaded=False,screen_verification_deferred=True,full_engine_goal_complete=False)
    current_runtime=dict(status='CURRENT_EXPLICIT_MENU_REPLAY_HOST_AND_SDK_PREPARED_NOT_EXECUTED_SCREEN_DEFERRED',
        run_id=RUN,host_build_id=BUILD,runtime_directory=str(runtime),host=verification['host'],gamecore=verification['gamecore'],
        bundle_manifest=ref(runtime/'bundle.manifest'),proofs=dict(request=verification['request'],materialization=ref(materialization),
        runtime_verification=ref(STAGE/'prepared_runtime_verification.json'),prepared_profile=verification['profile']),
        runtime_input_count=24,physical_runtime_files=189,required_sidecar_files=154,frozen_python_support_files=6,
        new_game_only=True,native_attempts=0,host_or_sdk_executed=False,default_promoted=False,
        globally_registered=False,original_ui_accepted=False,full_engine_goal_complete=False)
    compile_proof=dict(status='PASS_CURRENT_FIVE_TU_X64_CPP14_COMPILE_LINK_AND_INDEPENDENT_ATTESTATION',build_id=BUILD,
        build_result=verification['build_result'],independent_attestation=ref(pair/'independent_attestation.json'),
        translation_units=5,compiler_dependency_count=573,current_source_input_count=707,catalog_entries=74,
        required_sidecar_files=154,host_executed=False,SDK_executed=False,native_acceptance=False)
    remaining=['Native Host/GameCore/window/GPU/gameplay/save/mod/multicore acceptance remains deferred and incomplete.',
        'Full original options and main-menu branches still require real backend support; current options are six supported settings.',
        'ReplayMap is simplified; full original 3D map, retail replay wrapper/catalog and full original Lua execution remain unsupported.',
        'Original season localization keys are absent; SEASONS dates are unavailable without inventing names. Other calendars remain independent.',
        'Map and message scrollbar thumb-center mapping remains an existing P2 item. Legend drag uses exact press origin and retained input geometry.',
        'Series above1024points still use the existing bounded display sampling; raw history is preserved. The65536-point fixture proves its exact64x1024case only.',
        'Six legacy font faces are preserved; full modern Hangul coverage is proven for the new 14px Shadow face only.',
        'Four source-backed WindowTrim resampling candidates and native glyph/widget/filter equivalence require actual screen acceptance.']
    proofs=dict(calendar=ref(STAGE/'calendar/result.json'),pointer_metadata=ref(STAGE/'calendar/pointer_metadata/result.json'),
        window_translation_unit=ref(STAGE/'calendar/pointer_metadata/window_translation_unit_compile.json'),
        legend=ref(STAGE/'legend/ink_revision/result.json'),skin=ref(STAGE/'skin/fixture_result.json'),
        graph_colors=ref(STAGE/'graph_colors/fixture_result.json'),graph_exact_boundary=ref(STAGE/'graph_colors/exact_difference_boundary.json'),
        replay_scene=ref(STAGE/'integration/scene/ac0277a49fb8bc63/result.json'),cpu_color_pixels=ref(STAGE/'integration/cpu_visual_followup.json'))
    current=dict(schema='zerosis.replay_calendar_legend.current_work.v1',utc=datetime.now(timezone.utc).isoformat(),
        status='PASS_CURRENT_X64_REPLAY_CALENDAR_LEGEND_SKIN_PAIR_PREPARED_OFFLINE',goal_turn_classification='progress',
        full_goal_redefined=False,full_engine_goal_complete=False,requirements=ref(STAGE/'requirements.json'),
        requirements_addendum=ref(STAGE/'requirements_addendum.json'),current_host=current_host,current_prepared_runtime=current_runtime,
        working_source_matches_current_frozen_and_prepared_profile=True,proofs=proofs,
        immutable_assets=ref(STAGE/'legend/assets_v3.json'),source_manifest=verification['source_manifest'],
        intermediate_cleanup=ref(pair/'cleanup_result.json'),evidence_cleanup=ref(STAGE/'owned_evidence_cleanup.json'),
        current_and_recovery_preserved=['currentdeb/4f194','previous613f/f127','requiredbc34donor','registeredHost4/prior424fb','default732/usercbbdsaves'],
        storage=storage,remaining=remaining,native_execution=False,current_native_or_screen_relaunch_allowed=False,
        screen_verification_deferred=True,default_or_registration_changed=False)
    write(STAGE/'current_work.json',current)
    path=PROJECT/'evidence/save_menu/20261013_original_screen/current_progress.json';progress=read(path)
    progress.update(utc=current['utc'],status=current['status'],full_engine_goal_complete=False,current_goal_turn_classification='progress',
        current_host_build_id=BUILD,current_host_build=current_host,current_prepared_runtime=current_runtime,
        latest_host_sdk_preparation_stage=current_runtime,latest_private_prepared_pair_matches_current_host_and_selected_sdk_sources=True,
        prepared_runtime_matches_current_linked_candidate=True,prepared_runtime_matches_latest_source=True,
        latest_source_matches_integrated_syntax_proof=True,latest_source_matches_linked_candidate=True,
        latest_cpp_source_matches_actual_host_syntax_proof=True,latest_current_source_actual_cpp_compilation_verified=True,
        latest_host_source_matches_current_link_proof=True,latest_integrated_syntax_proof=compile_proof,
        latest_current_source_compile_link_proof=compile_proof,latest_actual_host_syntax_proof=compile_proof,
        latest_current_source_actual_cpp_compilation_verified_proof=compile_proof,
        latest_current_source_pe_attestation=ref(pair/'independent_attestation.json'),
        latest_host_source_matches_current_link_proof_scope='Currentdeb707source/frozen inputs,573compiler dependencies,74embeddedpayloads and154V3sidecar files match explicit4f194+SDK430. Unexecuted; default/globalHost4 unchanged.',
        latest_source_matches_linked_candidate_scope='Exact current707Source inputs and prepared189files verified; native acceptance remains deferred.',
        latest_actual_host_syntax_proof_scope='Five actual C++14 translation units compiled and linked, /fp:strict, zero warnings; no Host/SDK execution.',
        limits=remaining,screen_verification_deferred=True,current_native_or_screen_relaunch_allowed=False,
        host_executed=False,gamecore_loaded=False,hwnd_created=False,gpu_executed=False,default_promoted=False,
        native_acceptance_complete=False)
    progress['replay_calendar_legend_stage']=dict(current,record=ref(STAGE/'current_work.json'))
    progress.setdefault('storage',{})['latest_replay_calendar_legend_wave']=storage
    progress['storage']['older_fields_are_prior_wave_history']=True
    write(path,progress)
    if not args.close_storage:
        doc=PROJECT/'docs/ORIGINAL_MENUS_OFFLINE.md';old=doc.read_text('utf8');tail=old[old.index('효과음 설정은'):]
        top=f'''# 원본 메뉴 복원과 격리 실행 묶음 — 실제 실행 보류

최신 컴파일 Host는 `{BUILD}`, 격리 준비본은 `{RUN}`이다. 실제 소스/동결 입력707개, 컴파일 의존573개와 SDK `430f3122`를 파일 검사로 대조했다. C++14 다섯 단위 컴파일·링크와 독립 검사에서 경고0개다. Host·SDK·창·GPU·게임 실행 시도는0회다.

| 영역 | 이번 복원 | 확인 범위와 남은 부분 |
|---|---|---|
| 주 메뉴·옵션 외형 | 확장팩2→확장팩1→기본 스킨 상속, 실제 화면·스타일·하단 위치 재생성 | 지원 설정6종과 원본 장식. 전체 옵션·나머지 주 메뉴 분기는 미지원. 창 테두리4곳의 원본 전체 그림 변환은 실제 표시 일치 미검증 |
| 재생 날짜·글꼴 | 원본 날짜 눈금5개, 짧은 기록의 공통 그래프 가로 범위, 원본 턴 문구,14픽셀 Shadow/한글11,172자 | 원본 Lua6종과 SDK 주간 계산 대조. 원본 계절 번역4개 부재는 해당 달력만 사용 불가. 다른6개 글꼴은 기존 기록 보존 |
| 범례·그래프 | 문명 문양10종/실제 문명45개, 이름의 색상 표지,32픽셀 행 간격·체크 상자·세로 이동 | 원본 Lua 색상 선택385사례·769선택 결과 일치. 실제 누름 좌표·합쳐진 이동·해제·취소·입력 도형 고정 검사. 지도·메시지 이동 막대의 기존 P2 계산은 남음 |
| 메시지·기록 | 원본 배치·선택 메뉴·18픽셀 글꼴·아이콘148개·원문 보존 | 1MiB문장·빈 메시지100,000개·그래프65,536점 검사. 원본3DReplayMap·파일 포장/목록·전체 원본 Lua와 실제 위젯 일치는 남음 |
| 실행 묶음 | Host·SDK·백엔드24개·자산154개·Python지원6개, 실제189개 파일 | 해시·실제 파일 식별자·읽기 전용·모듈 의존성 대조. 새 게임 전용, 기본 실행본 승격·실게임 수락은 수행하지 않음 |

새 묶음: `Build/InteractiveGameRuntime/{RUN}`. 파일 준비 검증은 `evidence/game_menu/replay_calendar_legend/prepared_runtime_verification.json`, 현재 종합 기록은 같은 폴더의 `current_work.json`이다. 이전613f/f127, 현재 전역Host4, 기본 실행본·사용자 저장과 필요한 부모 입력은 보존한다.

'''
        doc.write_text(top+tail,encoding='utf8')
        hud=PROJECT/'docs/ORIGINAL_WORLD_HUD.md';body=hud.read_text('utf8');body=body.split('\n\n',1)[1]
        notice=f'> 2026-11-04: Current Host `{BUILD}` and SDK430 are prepared in isolated runtime `{RUN}`, with154-file UIFrontEndV3,189actualfiles and707current/frozen inputs verified. Native/screen execution remains held; globalHost4/default/previous613f-f127 preserved. See [original menu offline scope](ORIGINAL_MENUS_OFFLINE.md).\n\n'
        hud.write_text(notice+body,encoding='utf8')
    print(json.dumps(dict(status=current['status'],runtime=RUN,storage_pending=storage['after_pending'],full_engine_goal_complete=False)))


if __name__=='__main__':main()
