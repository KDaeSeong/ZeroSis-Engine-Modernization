# M6 원본 연구 트리 연결

2026-10-03 현재 원본 BNW `TechPopup`의 `OpenTTButton` → 원본 `OpenTechTree` 콜백 → 기존 VM 종료 → 별도 `TechTree` VM 연결을 영어·한국어 실제 SDK에서 검증했사와요. 원본 연구 트리는 선택 후 열린 상태를 유지하며, 실제 SDK 연구 명령이 반환된 뒤 `SerialEventResearchDirty`를 전달하와요. 일반 선택·가로 스크롤·Escape·정상 턴·새 세션 native 복원이 통과한 범위이며, 같은 세계 HWND의 전체 그림과 사람 조작·전체 연구 기능은 이어서 검증 중이랍니다.

## 요구사항과 범위

- 설치본 BNW Lua·XML·도움말·아이콘·스타일을 읽어 격리 후보에 묶으며 원본 파일·게임 설치본·MODS·사용자 저장을 수정하지 않사와요.
- 기존 연구 창에서 원본 버튼과 팝업 요청을 통해 연구 트리에 도달해야 하며, 이전 VM의 보호된 콜백이 돌아오고 종료된 뒤 새 VM을 생성하와요.
- 표시와 일반 연구 선택 중에는 원본 타이머 1을 유지하고, 원본 닫기·Escape 후에는 0으로 돌아와야 한답니다.
- 원본 `(tech, 0, -1, false)` 콜백 한 건을 실제 SDK 수신기로 전달하고, 해당 기술의 실제 연구 상태와 갱신을 대조하와요.
- 측정된 가로 범위에서 0 → 240 → 0 스크롤과 닫힌 화면의 오래된 입력 거부를 검사하와요.
- 정상 1턴과 turn-zero/turn-one native checkpoint의 새 세션 복원을 확인하와요. 이 결과를 기존 게임의 외부 저장 형식 호환성으로 환산하지 않사와요.
- 이 첫 실행 모드는 소유 스레드의 retained Lua 입력이랍니다. 실제 HWND 입력·사람 입력·전체 연구 예약·무료 기술·탈취·Civilopedia·retail 픽셀 동등성은 별도 관문이와요.

## 원본과 변경 경계

원본 Lua는 `Assets/DLC/Expansion2/UI/TechTree/TechTree.lua`, XML은 `Assets/DLC/Expansion2/UI/InGame/TechTree/TechTree.xml`이랍니다. 기술·시대·선행 기술 연결선과 원본 callback을 유지하며 `TechTree`/`TechTreeLayout`을 준비하와요. 표시 모드 이름·Mod ID·버전·저장 키·스키마·밸런스는 이 연결의 변경 범위에 포함하지 않사와요.

실행부 변경은 `Source/Host/UiPopupContext.h`, `HostRun.h`, `HostMain.cpp`의 소유 VM·타이머·지연 요청·SDK 명령·갱신 경계이며, Lua 연결은 `UiScene.lua`, `ResearchCommandGuard.lua`, `Source/Presentation/UiPresentationInput.lua`에 있사와요. 준비·실행·독립 검증 경로는 `tools/prepare_ui_popup_assets.py`, `run_found_city_probe.py --research-tree`, `verify_city_research_tree_ui.py`이랍니다.

## 구성요소 증거

- [현재 전체 retained UI component](../evidence/ui_scene_component/20261003T134917Z_4266f4a68b54/report.json): 실제 공유 Lua 제공자와 native JSON encoder에서 Ranking·Production·Research·TechTree 원본 fixture·수명·타이머·입력 회귀를 통과했사와요. 앞선 Lua encoder의 [역사적 component](../evidence/ui_scene_component/20261003T074540Z_5c2f148b1f32/report.json)도 보존하와요.
- [연구 명령 guard](../evidence/research_command_guard/20261003T074413Z_20b964f83f01/conformance.json): 소유 context·활성 인간 플레이어·일반 연구 인수·거부 경계의 component 증거랍니다.
- [입력과 배치 반영 경계](../evidence/ui_presentation_input/20261003T074457Z_e36329e37d51/conformance.json): Tree 조회·클릭의 `FlushLayout`, 가로 offset과 기존 입력 회귀를 검사했사와요.
- `Tests/ui_pixel_scene.py`의 122개 구성요소 검사는 연구 트리의 enum 67 수명주기·가로 clip·원본 scrollbar 자료·Left/Right callback metadata를 포함하와요. 실제 SDK의 전체 동적 트리 그림은 아직 이 증거에 포함되지 않사와요.

## 현재 native 직렬화와 실제 SDK pair

`Source/Host/UiSnapshotJson.h`의 native encoder가 원본 array/object 구조·정렬·문자열 escape·유한 숫자·table cycle 경계를 보존하와요. 깊이 128·방문 1,000,000·출력 32MiB·작업 128MiB·단일 key 1MiB·동시에 보유하는 key 합계 8MiB로 제한하고, 예외 뒤 Lua stack을 복구하와요. `UiScene.lua`의 전체 capture는 그대로 유지하며 직렬화만 실제 native 경계로 옮겼답니다. [28개 native component와 roundtrip](../validators/20261003T134815Z_2998481f0571/conformance.json)은 encoder 부품 증거이며 SDK 실행을 대신하지 않사와요.

현재 [sealed Host](../evidence/ui_window_host/20261003T135256Z_d18b9e84841d/build_result.json)의 [영어 실행](../evidence/city_research_tree_ui/20261003T140852Z_0b3661569209/result.json)과 [한국어 실행](../evidence/city_research_tree_ui/20261003T141146Z_c7ac5fbf29a9/result.json)은 같은 공유 FoundValue GameCore와 Lua 제공자를 사용했사와요. [독립 pair 대조](../evidence/city_research_tree_ui/validators/20261003T141801Z_46a0f8e36a01/conformance.json)는 원본 OpenTT handoff·일반 tech 1 선택 한 건·열린 상태와 timer 1 유지·스크롤 0→240→0/max 4700·Escape 후 timer 0·오래된 입력 거부·정상 1턴·native 새 세션 복원과 원본 reload 구획 차이를 확인했답니다. HWND·GPU·사람 입력·무료 기술·탈취·Shift 예약·retail 저장은 이 pair의 검증 범위에 포함하지 않사와요.

[실제 직렬화 비용 검토](../evidence/city_research_tree_ui/20261003T140852Z_0b3661569209/serialization_review.json)는 두 언어의 snapshot 여섯 건씩에서 control 7,829개를 유지했음을 확인했사와요. 숨긴 control도 제거하지 않았고, 기존 snapshot의 8,000,000 명령 한도 초과가 전체 장면 약 1,217,000 샘플로 바뀌었답니다. Tree 한도 8,000,000과 다른 popup 한도 2,000,000은 그대로이며, 이 Lua 명령 수 차이를 native CPU 비용이나 전체 턴 속도 향상으로 계산하지 않사와요.

이 과정의 [135009 Host 빌드 실패](../evidence/ui_window_host/20261003T135009Z_ddc03d82860d/build_result.json)는 범위 밖 지역 변수와 없는 조회 함수 사용을 컴파일 단계에서 잡은 기록으로 SDK 실행 전이랍니다. [135721 영어](../evidence/city_research_tree_ui/20261003T135721Z_cab25c5ffdba/result.json)·[140132 한국어](../evidence/city_research_tree_ui/20261003T140132Z_68b9fec2e400/result.json)는 공유 FoundValue 옵션이 빠진 별도 Core 실행이므로 현재 pair의 엔진 일치 증거로 채택하지 않사와요. 관련 독립 검증 실패 기록도 보존하와요.

[첫 같은 세계 HWND 실행](../evidence/interactive_game/20261003T140428Z_c1e6a1c1a2b5/result.json)은 전체 연구 트리 snapshot까지 도달했으나 원본 2색 ColorSet과 3-layer SoftShadow의 표시 처리에서 실패했사와요. 동결 renderer와 실패 입력은 보존하고 원본 font·atlas·압축 texture 의미를 대조해 전체 scene을 준비하는 작업을 진행하와요. 실제 Escape timer 해제는 `UI_WINDOW_INPUT`을 같은 native key dispatch와 연결하는 [독립 gate component](../evidence/interactive_tree_timer_contract/20261003T144737Z_e8397ecf0440/conformance.json)로 보강했으며, 실제 HWND 통과 판정은 별도 새 실행이 필요하답니다.

## 첫 실제 실행과 수정 이력

첫 [sealed Host](../evidence/ui_window_host/20261003T072930Z_0f7d57af963d/build_result.json)는 x64 PE32+ `/O2 /W4 /WX` 빌드와 입력 해시 보존을 통과했사와요. [영어 실제 SDK 실행](../evidence/city_research_tree_ui/20261003T073459Z_e8f37fe5c324/result.json)은 원본 chooser의 `OpenTTButton` key 8, 팝업 enum 67, Data2 -1 요청과 기존 VM 종료를 확인한 뒤 연구 트리 초기 갱신 중 2,000,000 Lua 명령 처리 한도에 걸렸답니다. exit 1과 타이머 복구·Core 해제는 확인했으며 접근 위반·timeout은 아니었사와요. 연구 트리 표시·연구 선택·턴·복원 통과로 기록하지 않사와요.

원인은 원본의 각 label·숨김 갱신마다 후보 frontend가 전체 트리를 반복 순회한 경로였답니다. Tree의 `SetHide`는 조상 상태를 반영해 해당 하위 animation을 갱신하며, `SetText`는 원본 glyphgen 계측을 유지하고 배치를 지연하와요. 이벤트 묶음·snapshot·입력 조회·callback 경계에서 전체 배치를 한 번 반영하며, 다른 popup의 기존 동작은 유지하와요. 실행부에는 처리 단계별 Lua 명령 샘플 수와 한도·성공 여부 기록을 추가했사와요. 다음 실제 실행으로 이 수정의 효과를 확인하와요.

최적화 후 [두 번째 sealed Host](../evidence/ui_window_host/20261003T074643Z_b458592a057b/build_result.json)의 [영어 실행](../evidence/city_research_tree_ui/20261003T074929Z_9dc8705aae4d/result.json)은 마지막 배치의 anchor 순회까지 진행했으나 여전히 `popup|2000000|2000000|0`으로 처리 한도에 걸렸사와요. 정상 exit 1·타이머 복구·Core 해제를 확인했으며 연구 트리 통과는 아니랍니다. 전체 원본 화면의 다음 계측을 위해 Tree에만 유한 8,000,000 한도를 적용하고, 다른 세 popup의 2,000,000 한도는 유지했사와요. 이 변경의 실제 비용·성공 여부는 다음 sealed 실행으로 확인해야 하와요.

[세 번째 sealed Host](../evidence/ui_window_host/20261003T080654Z_a5e5396599f0/build_result.json)의 [영어 실행](../evidence/city_research_tree_ui/20261003T081553Z_bfe51f17f2b8/result.json)은 `popup|2713000|8000000|1`로 원본 트리의 popup 처리를 통과했으나, 검증용 장면의 JSON 직렬화에서 `snapshot|8000000|8000000|0`과 `zerosisuiscene.lua:906` 한도 초과를 기록했사와요. 정상 exit 1·timeout false·타이머 복구와 context 종료를 확인했으며, 표시 snapshot·연구 선택·턴·복원의 통과 증거는 아니랍니다. 처리 한도를 다시 올리는 반복 빌드를 이어 가지 않고 이 직렬화 결함을 미완료로 보존하와요. 전체 작업의 다음 우선순위는 연속 사용자 플레이 경로랍니다.

## 보관과 남은 관문

첫 반복 빌드의 [미리보기](../evidence/build_tidy/20261003T073909Z_f80d3e2df128/cleanup.json)와 [적용 기록](../evidence/build_tidy/20261003T073938Z_0070da349de0/cleanup.json)은 참조되지 않은 object 3개, 9,645,411바이트를 정리했사와요. EXE·보고서·동결 입력·실행·실패·저장 기록은 보존했답니다.

두 번째 반복 빌드도 [미리보기](../evidence/build_tidy/20261003T075323Z_56e69f184c36/cleanup.json)와 [적용](../evidence/build_tidy/20261003T080137Z_a38d5960d19a/cleanup.json)을 거쳐 object 3개, 9,648,286바이트를 정리했사와요. 두 차례 합계는 19,293,697바이트이며 참조된 입력·실패 증거와 실행 파일은 보존했답니다.

세 번째 반복 빌드도 [미리보기](../evidence/build_tidy/20261003T081805Z_93a20ce9f5b5/cleanup.json)와 [적용](../evidence/build_tidy/20261003T081829Z_dfdf814ba5ce/cleanup.json)을 거쳐 object 3개, 9,648,473바이트를 정리했사와요. 세 차례 합계는 28,942,170바이트이며 실행 파일·보고서·동결 입력·실행과 실패·저장 기록의 보존 조건을 유지했답니다.

영어·한국어 소유 SDK의 일반 선택·스크롤·턴·복원 pair는 위 현재 기록에서 통과했사와요. 남은 관문은 실제 동적 트리의 그림 컴파일·검토, 동일 HWND의 여러 장면 갱신·입력·크기 변경, 원본 future-tech/Shift 예약과 큐 순서·무료/탈취 상태와 실제 사람 조작이랍니다. 원본 `ResponseResearch`의 일반 큐는 `CanEverResearch`와 `pushResearch(tech,!shift)`를 사용하므로, 현재 `CanResearch`·shift false 경계는 원본 전체 연구 트리 기능을 포괄하지 않는답니다. 세계 렌더링·음향·전체 플레이·retail 저장·모드·성능·장기 회귀·배포는 전체 엔진의 남은 관문으로 유지하와요.
