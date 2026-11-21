"""Publish source-only menu evidence without promoting or executing a runtime."""
from pathlib import Path
import hashlib
import json
from datetime import datetime, timezone

STAGE=Path(__file__).resolve().parent
PROJECT=STAGE.parents[2]


def read(path):
    return json.loads(path.read_bytes())


def artifact(path):
    raw=path.read_bytes()
    return dict(path=str(path),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())


def save(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def main():
    assert not (STAGE/'publication.json').exists(), 'Single source publication only'
    before=read(STAGE/'before.json')
    pins={Path(row['path']):row for row in before['sources']}
    progress_path=PROJECT/'evidence/save_menu/20261013_original_screen/current_progress.json'
    doc_path=PROJECT/'docs/ORIGINAL_WORLD_HUD.md'
    for path in [progress_path,doc_path]:
        assert artifact(path)['sha256']==pins[path]['sha256'], 'Metadata changed before publication'
    required={
        'lua_tests.json':('status','PASS'),
        'cpp_tests_fixture_thunk_fix.json':('status','PASS'),
        'cpp_current_source_equivalence.json':('status','PASS_CURRENT_EXTRACTED_CPP_IDENTICAL_TO_EXECUTED_FIXTURE'),
        'host_syntax.json':('status','PASS_CURRENT_HOSTMAIN_SYNTAX_ONLY'),
        'asset_tests.json':('status','PASS'),
        'timeline_regression.json':('status','PASS'),
        'driver_tests.json':('status','PASS'),
        'owner_review.json':('result','NO_CONFIRMED_P0_P1_DEFECT'),
        'cleanup_result.json':('status','PASS_EXACT_TASK_INTERMEDIATE_CLEANUP'),
        'driver_shown_source_gate.json':('cleanup_status','DELETED_EXACT_OWN_TEMPORARY_FILE'),
    }
    for name,(key,value) in required.items():
        assert read(STAGE/name)[key]==value, name
    for name,key in [('driver_tests.json','sources_after'),('asset_tests.json','source_files')]:
        for row in read(STAGE/name)[key]:
            assert artifact(Path(row['path']))==row, 'A tested source changed'
    for name,digest in read(STAGE/'lua_tests.json')['input_sources_after'].items():
        assert artifact(PROJECT/name)['sha256']==digest, 'A Lua/input fixture source changed'
    for row in read(STAGE/'cpp_current_source_equivalence.json')['current_production_sources']:
        assert artifact(Path(row['path']))['sha256']==row['sha256']
    syntax=read(STAGE/'host_syntax.json')
    for row in syntax['actual_inputs'].values():
        assert artifact(Path(row['path']))==row, 'A compiled C++ input changed'
    review=read(STAGE/'owner_review.json')
    assert not review['findings']
    for row in review['source_pins']:
        actual=artifact(PROJECT/row['path'])
        assert (actual['bytes'],actual['sha256'])==(row['bytes'],row['sha256'])
    proof_refs={name.removesuffix('.json'):artifact(STAGE/name) for name in required}
    production_names=[
        'Source/Host/UiPopupContext.h','Source/Host/UiScene.lua',
        'Source/Host/InteractiveUiSession.h','Source/Host/InteractiveGameSession.h',
        'Source/Host/InteractiveGameLoop.h','Source/Presentation/UiPresentationInput.lua',
        'tools/prepare_ui_popup_assets.py','tools/interactive_ui_driver.py',
        'tools/ui_pixel_scene.py','tools/render_ui_popup.py',
        'Source/Assets/UI/Assets/UI/FrontEnd/ExitConfirm.lua',
        'Source/Assets/UI/Assets/UI/FrontEnd/ExitConfirm.xml',
    ]
    production=[artifact(PROJECT/name) for name in production_names]
    test_names=['Tests/game_menu_scene.py','Tests/exit_confirm_scene.py','Tests/exit_confirm_ui_assets.py',
                'Tests/game_menu_exit_lifecycle.py','Tests/game_menu_exit_lifecycle.cpp.in','Tests/test_exit_confirm_driver.py']
    tests=[artifact(PROJECT/name) for name in test_names]
    manifest=dict(schema='zerosis.game_menu.offline_exit.source_manifest.v1',
                  status='SOURCE_AND_OFFLINE_CHECKS_COMPLETE_RUNTIME_NOT_BUILT',
                  requirements=artifact(STAGE/'requirements.json'),before=artifact(STAGE/'before.json'),
                  production_sources=production,test_sources=tests,proofs=proof_refs,
                  new_embedded_ui_header_generated=False,new_host_linked=False,
                  native_host_or_gamecore_executed=False,native_window_or_gpu_tested=False,
                  source_only_not_whole_engine_acceptance=True)
    save(STAGE/'source_manifest.json',manifest)
    stage=dict(status='PASS_EXIT_CONFIRM_SOURCE_AND_OFFLINE_COMPONENTS_NOT_EMBEDDED_OR_LINKED',
               scope='Original GameMenu ExitGame -> separate stock ExitConfirm -> No/Escape returns parent, Yes produces one deferred owner-bound no-save exit.',
               source_manifest=artifact(STAGE/'source_manifest.json'),proofs=proof_refs,
               lua_component_checks=679,cpp_component_cases_per_profile=30,cpp_component_checks_total=126,
               asset_tests=8,driver_contract_tests=11,historical_timeline_regressions=20,
               actual_hostmain_syntax_inputs=syntax['actual_input_count'],compiler_warnings=syntax['warnings'],
               generated_ui_header_updated=False,host_compile_link_complete=False,
               original_ui_pixel_or_native_exit_acceptance=False,full_engine_goal_complete=False,
               screen_verification_deferred=True,current_native_or_screen_relaunch_allowed=False,
               source_only_remaining=['Original options, main-menu frontend, correct current-setup restart, retirement replay/endgame, map save, touch-help settings.'],
               acceptance_remaining=['Rebuild/freeze a current Host with the new embedded scripts/layout and updated driver closure.','After direct human release, verify actual ExitConfirm display, No/Escape/Yes and WM_CLOSE ordering, native shutdown, save preservation and regression.'])
    progress=read(progress_path)
    assert progress['current_prepared_runtime']['run_id']=='20261024T091253Z_713037fbac49'
    assert progress['screen_verification_deferred'] is True
    progress['utc']=datetime.now(timezone.utc).isoformat()
    progress['status']='OFFLINE_EXIT_MENU_SOURCE_IMPLEMENTED_NOT_LINKED_SCREEN_DEFERRED'
    progress['current_goal_turn_classification']='progress'
    for key in ['latest_source_matches_linked_candidate','latest_host_source_matches_current_link_proof',
                'prepared_runtime_matches_latest_source','latest_private_prepared_pair_matches_current_host_and_selected_sdk_sources',
                'latest_source_matches_integrated_syntax_proof','latest_source_matches_linked_candidate_scope']:
        if key.endswith('_scope'):
            progress[key]='Working ExitConfirm sources differ from the preserved hover Host. The new source stage has compile-only and explicit fixture proof, without a current linked or embedded runtime.'
        else:
            progress[key]=False
    progress['latest_cpp_source_matches_actual_host_syntax_proof']=True
    progress['latest_current_source_actual_cpp_compilation_verified']=False
    progress['latest_actual_host_syntax_proof']=artifact(STAGE/'host_syntax.json')
    progress['latest_actual_host_syntax_proof_scope']=syntax['limit']
    current=progress['current_prepared_runtime']
    current['status']='PRESERVED_PRIOR_HOVER_SOURCE_PREPARED_NOT_EXECUTED_SCREEN_DEFERRED'
    current['current_source_candidate']=False
    current['current_host_source_closure_matches_candidate']=False
    current['working_host_source_differs_from_runtime']=True
    current['working_source_difference']='ExitConfirm menu lifecycle, original assets, input addendum and driver/render/pixel contract source changes are not embedded in this preserved runtime.'
    progress['game_menu_exit_offline_source_stage']=stage
    progress['full_engine_goal_complete']=False
    progress['current_native_or_screen_relaunch_allowed']=False
    progress['screen_verification_deferred']=True
    progress['next_native_gates']=[
        'First rebuild and freeze the current ExitConfirm source/embedded UI/driver closure; the preserved 713037 pair predates this feature.',
        'After explicit direct human release of screen/native testing, verify original ExitConfirm No/Escape/Yes, WM_CLOSE order, shutdown and save preservation.',
        *progress['next_native_gates'],
    ]
    progress['limits'].append('The offline ExitConfirm stage executes Lua with explicit SDK/player/clock fixtures and extracted C++ with substituted owner/OS boundaries. Current HostMain /Zs consumes the preserved older generated UI header. The shown renderer check stops at an explicit texture boundary; closed packet compilation and source geometry do not prove raster, physical input or native exit.')
    save(progress_path,progress)
    raw=doc_path.read_bytes();old=raw.decode('utf-8-sig').replace('\r\n','\n')
    addition='''

## 2026-10-26 오프라인 종료 메뉴 구현

현재 작업 소스는 보존 중인 `20261024T091253Z_713037fbac49` 시험본보다 새 버전이다.
이 시험본과 기본 실행본은 교체하지 않았으며, 새 종료 메뉴가 들어 있는 실행 파일로 표시하지 않는다.

- 원본 GameMenu의 종료 버튼은 별도 원본 `ExitConfirm.lua/xml` 모달로 연결한다. 기존 원본 파일의 바이트와 XML 순서는 보존한다.
- 아니요·Esc는 같은 부모 게임 메뉴로 복귀한다. 자식 타이머는 0, 부모의 기존 타이머는 유지한다.
- 예는 원본 PopModal 뒤 소유 플레이어·턴에 묶인 종료 요청을 한 번 전달한다. 부모 닫기가 성공하면 추가 입력·Tick·저장·새 장면 게시 전에 루프를 반환한다. 창 자원 해제 뒤 기존 HostRun 정리 경로를 사용한다.
- 창 닫기(WM_CLOSE)의 기존 저장 후 종료와 메뉴 확인 후 저장 없는 종료는 서로 다른 경로로 유지한다.
- 입력 addendum 및 실제 scene driver·renderer·pixel 계약에도 새 문맥을 연결했다. 원본 옵션·주 메뉴·재시작·은퇴·지도 저장·터치 도움말 전체 구현은 완료하지 않았다.

오프라인 결과: 원본 Lua 메뉴/확인창 679개 확인, 실제 추출 C++ 최적화·비최적화 각 30사례/63확인, 자산 8개·드라이버 계약 11개·기존 기록 분석 20개 검사 통과. 현재 HostMain은 466개 입력의 `/Zs` 검사에서 경고 없이 통과했다.

이 결과는 전체 새 Host 링크·새 UI 임베딩·실제 화면·물리 입력·SDK 종료 수락이 아니다. C++ 구문 검사는 기존 생성 UI 헤더를 읽고, Lua와 SDK/플레이어/시간 경계는 명시적 시험값을 쓴다. 표시 상태의 renderer 검사는 텍스처 경계까지만 확인했으며, 실제 raster/시각 일치는 주장하지 않는다.

근거: `evidence/game_menu/offline_exit/source_manifest.json`, `host_syntax.json`, `lua_tests.json`, `cpp_tests_fixture_thunk_fix.json`, `driver_tests.json`, `owner_review.json`. 정리 경로·크기·해시는 같은 폴더의 정리 기록에 남긴다. 원본 설치·MODS·설정·저장 파일은 수정하지 않는다.
'''
    data=(old.rstrip()+addition+'\n').replace('\n','\r\n').encode('utf-8')
    if raw.startswith(b'\xef\xbb\xbf'):
        data=b'\xef\xbb\xbf'+data
    doc_path.write_bytes(data)
    publication=dict(status='PASS_SOURCE_ONLY_PROGRESS_AND_DOCUMENTATION_PUBLICATION',
                     before_metadata=[pins[progress_path],pins[doc_path]],
                     after_metadata=[artifact(progress_path),artifact(doc_path)],
                     source_manifest=artifact(STAGE/'source_manifest.json'),
                     existing_runtime_replaced=False,default_promoted=False,
                     current_native_or_screen_relaunch_allowed=False)
    save(STAGE/'publication.json',publication)
    print(json.dumps(dict(status=publication['status'],production_files=len(production),test_files=len(tests),
                         current_runtime_preserved=current['run_id'],current_source_matches_preserved_runtime=False)))


if __name__=='__main__':
    main()
