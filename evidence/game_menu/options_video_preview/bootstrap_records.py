"""Create the current-wave writer while retaining earlier completed records."""
from pathlib import Path

STAGE=Path(__file__).absolute().parent
PROJECT=STAGE.parents[2]
text=(PROJECT/'evidence/game_menu/replay_hover_frame/finalize_records.py').read_text('utf8')
text=text.replace('zerosis.replay_hover_frame.current_work.v1','zerosis.options_video_preview.current_work.v1')
text=text.replace('PASS_CURRENT_X64_ORIGINAL_POINTER_GUIDES_AND_GRID_CAP_PAIR_PREPARED_OFFLINE',
    'PASS_CURRENT_X64_ORIGINAL_VIDEO_CONFIRMATION_PAIR_PREPARED_OFFLINE')
text=text.replace('CURRENT_EXPLICIT_REPLAY_POINTER_GUIDE_GRID_CAP_HOST_AND_SDK',
    'CURRENT_EXPLICIT_VIDEO_CONFIRMATION_HOST_AND_SDK')
text=text.replace("['current/new-runtime','recent829/01dfa','recoverydeb/4f194','older required613f/f127 snapshots'",
    "['current/new-runtime','recentee8c/9a1','recovery829/01dfa','older requireddeb/4f194/613f/f127 snapshots'")
text=text.replace("progress['replay_hover_frame_stage']","progress['options_video_preview_stage']")
text=text.replace("['latest_replay_hover_frame_wave']","['latest_options_video_preview_wave']")
text=text.replace("requirements=ref(STAGE/'requirements.json'),current_host=host", "requirements=ref(STAGE/'requirements.json'),requirements_addendum=ref(STAGE/'requirements_addendum.json'),current_host=host")
begin=text.index('    remaining=[')
end=text.index('    current=dict(',begin)
text=text[:begin]+'''    remaining=[
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
'''+text[end:]
begin=text.index("        top=f'''")
end=text.index('        doc.write_text(top+tail',begin)
document="""        top=f'''# 원본 메뉴 복원과 격리 실행 묶음 — 실제 실행 보류

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
"""
text=text[:begin]+document+text[end:]
text=text.replace("doc.write_text(top+tail,encoding='utf8')", "tail=tail.replace('그래프 원본65,536점과 모든 표시 점을 유지하고 연결선 그리기만 제한한다.','그래프는 원본100구간·101표본 위치 정책으로 표시하며 원자료를 그대로 보존한다.')\n        tail=tail.replace('진척·근거·정리·용량은 `evidence/game_menu/menu_runtime_ui_followup/current_work.json`에 기록한다.','최신 진척·근거·정리·용량은 위 현재 기록 경로에 기록한다.')\n        doc.write_text(top+tail,encoding='utf8')")
text=text.replace('Original pointer guides/current-position sampling and authored grid cap sizes restored; source100-segment graph and continuous messages preserved.',
    'Original supported video confirmation/rollback flow restored with unchanged V1/V2 preferences and reused V3 assets; source graph/messages/guides preserved.')
output=STAGE/'finalize_records.py';assert not output.exists()
compile(text,str(output),'exec')
with output.open('x',encoding='utf8') as stream:stream.write(text)
print('CREATED_CURRENT_VIDEO_PREVIEW_RECORD_WRITER')
