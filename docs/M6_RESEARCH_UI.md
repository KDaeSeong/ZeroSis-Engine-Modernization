# M6: 공식 연구 선택 UI의 일반 기술 선택 경로

2026-10-03 격리 x64 실행부에서 원본 BNW `TechPopup`을 열고, 실제 창의 합법 기술 버튼을 자동 클릭하여 SDK 연구 명령·정상 1턴·새 세션 native 저장 복원까지 영어·한국어로 검증했사와요. [독립 EN/KO 대조표](../evidence/city_research_ui/validators/20261003T063605Z_6bec92a0bef8/conformance.json)는 `ISOLATED_SDK_OFFICIAL_RESEARCH_UI_TURN_AND_NATIVE_RESTORE_PAIR_PASS`, SHA-256 `a3cbdfdb46f08735dfbbd213428e479f6ce2955e9e5b45d9e087b990a8acdc52`랍니다. 일반 기술 하나를 선택한 자동 시험의 범위이며 전체 연구 UI나 완성된 게임 엔진을 뜻하지 않사와요.

| 언어 | 실제 SDK run | PID | 선택 `[player,tech,key]` |
|---|---|---|---|
| 영어 | `20261003T062958Z_c2a5d9821f96` | 40508 | `[0,1,26]` |
| 한국어 | `20261003T063040Z_b204bc381fbc` | 43868 | `[0,1,26]` |

두 실행은 exit 0·timeout 없음·정상 Core 해제를 확인했사와요. [Host build](../evidence/ui_window_host/20261003T060726Z_eddea2a1f84d/build_result.json)는 x64 `/O2 /W4 /WX` 후보이며 EXE SHA-256은 `19809735ad14eb6a582b56982982fa57d492410483c71f6b104180aacaee1cc7`이와요. 기존 공유 FoundValue GameCore와 제공자를 재사용했으며 전체 SDK를 다시 빌드하지 않았답니다.

## 요구사항과 적용 범위

설치 원본 `TechPopup.lua/.xml`, `TechButtonInclude`, `TechHelpInclude`와 관련 include·스타일·글꼴·그림을 동결하고, 원본 `TechSelected`의 일반 연구 인자 `(tech,0,-1,false)`를 그대로 전달하는 요구사항이랍니다. 원본 규칙·효과·밸런스와 Mod ID·버전·저장 키·schema는 변경하지 않았사와요. 작업은 이 프로젝트의 Source·격리 Build·evidence에 한정하며 Stage·설치 게임·MODS·사용자 저장으로 배포하지 않았답니다.

`ResearchCommandGuard.lua`와 native `sendResearch`는 매 선택 때 활성 human 플레이어·현재 턴·소유 잠금·유효 기술·연구 가능 여부를 확인하와요. 무료 기술·도둑질·shift 예약 인자는 지원되지 않는다는 오류로 SDK 변경 전에 거부하와요. 원본 선택 인자를 일반 연구로 바꾸어 전달하지 않사와요.

`SmallUIAssets`는 사용자 `UserSettings.ini`의 저장된 0/1을 읽어 각 runtime의 `UserSettings.frozen.ini`에 고정했사와요. 두 언어의 동결 파일과 저장된 값 1이 같으며 native 출력도 그 값과 일치했답니다. 사용자 원본 파일은 수정하지 않았사와요. `AutoUIAssets`가 실제 retail에서 결정하는 유효 값·화면 크기 정책은 미검증이랍니다.

## 검증된 실행과 화면 경계

- 원본 `TechButton`의 보이는 LeftClick target과 `(tech,0)` payload를 대조하고, 작은 자식 버튼에 가리지 않은 실제 client 좌표를 클릭했사와요. 역순 hit map의 최상위 target도 같은 기술 key임을 독립 검사했답니다.
- 원본 콜백은 `local-research:1:0:-1:0` 명령을 정확히 한 건 생성했사와요. 늦은 Escape는 닫힌 context에서 거부됐답니다. 종료 순서는 SDK enum `BUTTONPOPUP_CHOOSETECH=11`에 따른 `queued → shown:11 → context-hidden:TechPopup → processed:11`이와요.
- 같은 HWND·소유 스레드·D3D 장치에서 초기 1000×700, 크기 변경 900×600, 닫힘 900×600 GPU 캡처를 언어당 세 장씩 검사했사와요. 장면 세대는 1→2로 증가하며 닫힌 장면의 옛 기술 좌표 클릭은 콜백을 만들지 않고 새 Escape도 거부됐답니다.
- 화면 준비·0.25의 표시 시간 진행 전후에는 게임 의미 상태 표본과 synchronous RNG seed가 같았사와요. 이는 모든 게임 필드·전체 RNG 상태를 비교했다는 뜻은 아니랍니다. 두 run의 seed 표시는 `2424833940|2424833940`이와요.
- 선택 후 유닛 생산량 0→5와 연구량 0→4의 정상 한 턴을 확인했사와요. 같은 언어의 기존 도시 결정 API 기준과 의미 상태가 같고, turn-zero·turn-one 저장을 각각 새로운 Core 세션에 복원한 뒤 세 idle update에서도 표본 상태를 유지했답니다. native 저장의 Game 이외 132구획은 byte exact이며 Game 구획의 원본 replay·session 증가를 별도로 대조했사와요.

픽셀 검사는 후보 bitmap과 자체 GPU readback의 대조랍니다. 모든 Present는 시험 desktop의 `DXGI_STATUS_OCCLUDED`였으며 실제 사용자 화면·사람 입력·retail 픽셀 동등성은 false로 유지하와요. [EN/KO 후보 PNG 육안 검토](../evidence/city_research_ui/visual_review_20261003T063505Z_2a1a2c679fd8/visual_review.json)에서도 전체 popup 수용은 통과시키지 않았답니다. 넓은 상단 장식은 원본 XML 치수와 일치하며, 기술 행은 원본 row 오른쪽 308과 ScrollPanel 오른쪽 300의 차이로 후보에서 8px 잘리와요. 원본 retail의 clip·padding 의미를 비교하기 전에는 임의로 좌표를 바꾸거나 retail도 같은 모습이라고 단정하지 않사와요.

## 변경 모듈과 구성요소 검증

Host의 `UiPopupContext.h`, `UiWindowPresentation.h`, `HostRun.h`, `HostMain.cpp`, `CityDecisionProbe.h`에 Research context·공식 클릭·기존 API 중복 연구 방지·턴/복원 경로를 연결했사와요. 원본 단위 초상화 호출에서 생략되는 player 인자도 실제 활성 플레이어로 처리하와요. 후보 `Locale.TruncateString`·작은 UI 설정·retained scroll geometry의 정확한 retail 의미는 별도 관문이랍니다.

Lua의 `ResearchCommandGuard.lua`, `UiScene.lua`, `UiPresentationInput.lua`와 asset 준비·Host 빌드·실행·scene renderer·window driver·독립 verifier를 갱신했사와요. LeftClick·RightClick의 원본 scalar metadata는 보존하지만 시험 packet과 native fixture는 LeftClick만 전달하와요. 오른쪽 클릭·Civilopedia 지원을 완료했다고 계산하지 않사와요.

연구 guard의 정상 인자와 15개 거부 사례, 연구 입력·원본 TechPopup을 실행하는 retained UI 구성요소 검증도 통과했사와요. Renderer의 grid·종료 lifecycle·생산 Left/Right metadata 회귀는 99항목을 통과했답니다. [클릭 지점 구성요소 8항목](../evidence/ui_selected_hit_point/20261003T062541Z_4a2d19192278/report.json)은 가리지 않은 내부 좌표 선택·완전 가림·중복 key·너무 작은 영역 거부를 포함하와요. 이 구성요소·오프라인 scene 준비는 실제 SDK run이나 사람 조작을 대신하지 않사와요.

## 실패 이력과 산출물 보관

연구 `20261003T060507Z_a447a5e7bf5c`는 생략된 초상화 player 인자, `20261003T060911Z_133b4136da12`는 원본 OpenTTButton의 inline GridData, `20261003T062106Z_55f8508a9be4`는 작은 자식 버튼과 겹친 시험 클릭 좌표, `20261003T062551Z_6b9b0516efea`는 숫자 popup enum을 symbolic 문자열로 가정한 closed renderer에서 각각 정상 exit 1로 끝났사와요. 앞의 인자 수정은 새 sealed Host에 반영했고, 나머지 Python 수정 뒤 새 runtime에서 위 두 언어 실행을 통과했답니다. 실패 로그·snapshot과 오프라인 진단은 보존했으며 이 실패들을 SDK 성공으로 합치지 않았사와요.

생산 회귀 `20261003T063212Z_a4db20f37771`와 `20261003T063534Z_5e22205ac84c`에서도 새 Left/Right metadata를 기존 renderer·driver가 하나의 key로 가정하는 오류가 각각 발견됐사와요. 오른쪽 클릭 정보를 보존하면서 LeftClick만 정확히 하나 찾도록 `live_production_window_driver.py`, `verify_city_production_ui.py`, `verify_production_interactions.py`도 맞췄답니다. 이 두 실패는 정상 exit 1·timeout 없음으로 보존했사와요. 수정 뒤 같은 sealed Host의 영어 `20261003T063936Z_66934f876a87`·한국어 `20261003T064055Z_4b41b54f1694` 생산 회귀와 [독립 pair 대조](../evidence/city_production_ui/validators/20261003T064411Z_b1c560071648/conformance.json)를 통과했답니다. 각 언어 9개 자동 입력 batch·9개 GPU frame, 원본 유닛 생산 선택·정상 턴·fresh native 복원이 기존 생산 fixture 범위에서 확인됐사와요.

[정리 기록](../evidence/build_tidy/20261003T062904Z_1cf6cdc63278/cleanup.json)에 따라 두 sealed build의 해시 참조 없는 중간 object 6개·17,684,538바이트를 삭제했사와요. EXE·build report·동결 입력·provider·소스·로그·저장·캡처·검증 보고서는 보존하고 해당 해시도 다시 확인했답니다.

## 남은 관문

실제 긴 연구/생산 목록의 scroll 이동, 연구 트리·무료 기술·도둑질·예약·Civilopedia·cancel, 성공 구매와 음향, 자동 OS mouse leave·비동기 사람 입력을 이어서 검증해야 하와요. 전체 세계 그래픽·음향·gameplay·retail 저장·활성 모드 호환, 반복 성능 향상·장기 안정성·정식 배포도 남아 있답니다. 이번 일반 연구 선택 통과로 전체 엔진 목표를 완료 처리하지 않사와요.
