"""Adapt the prior closed-wave record writer without changing preserved history."""
from pathlib import Path

STAGE=Path(__file__).absolute().parent
PROJECT=STAGE.parents[2]
text=(PROJECT/'evidence/game_menu/replay_scroll_graph/finalize_records.py').read_text('utf8')
text=text.replace('zerosis.replay_scroll_graph.current_work.v1','zerosis.replay_hover_frame.current_work.v1')
text=text.replace('PASS_CURRENT_X64_REPLAY_CONTINUOUS_SCROLL_ORIGINAL_GRAPH_PAIR_PREPARED_OFFLINE',
    'PASS_CURRENT_X64_ORIGINAL_POINTER_GUIDES_AND_GRID_CAP_PAIR_PREPARED_OFFLINE')
text=text.replace('CURRENT_EXPLICIT_REPLAY_SCROLL_GRAPH_HOST_AND_SDK','CURRENT_EXPLICIT_REPLAY_POINTER_GUIDE_GRID_CAP_HOST_AND_SDK')
text=text.replace("component_cleanup=ref(component_cleanup),permission_failure_resolution=ref(STAGE/'host_build/permission_resolution.json'),",
    'component_cleanup=ref(component_cleanup),')
text=text.replace("['current829/new-runtime','recentdeb/4f194','recovery613f/f127','requiredbc34donor'",
    "['current/new-runtime','recent829/01dfa','recoverydeb/4f194','older required613f/f127 snapshots','requiredbc34donor'")
text=text.replace("progress['replay_scroll_graph_stage']","progress['replay_hover_frame_stage']")
text=text.replace("['latest_replay_scroll_graph_wave']","['latest_replay_hover_frame_wave']")
begin=text.index('    remaining=[')
end=text.index('    current=dict(',begin)
text=text[:begin]+'''    remaining=[
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
'''+text[end:]
begin=text.index("        top=f'''")
end=text.index("        doc.write_text(top+tail",begin)
doc_source="""        top=f'''# 원본 메뉴 복원과 격리 실행 묶음 — 실제 실행 보류

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

'''"""
text=text[:begin]+doc_source+'\n'+text[end:]
text=text.replace('Original replay scroll/100-segment graph source restored.',
    'Original pointer guides/current-position sampling and authored grid cap sizes restored; source100-segment graph and continuous messages preserved.')
output=STAGE/'finalize_records.py'
assert not output.exists()
compile(text,str(output),'exec')
with output.open('x',encoding='utf8') as stream:stream.write(text)
print('CREATED_CURRENT_WAVE_RECORD_WRITER')
