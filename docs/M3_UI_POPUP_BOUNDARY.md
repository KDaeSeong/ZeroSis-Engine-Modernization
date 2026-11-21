# M3: `BUTTONPOPUP_WHOS_WINNING` UI/RNG 통합 경계

상태: **headless retained-scene 및 native RNG/timer 통합을 구현해 turn 50까지 검증했사와요.** 아래 turn-25 `AddPopup` 실패는 과거 기록이랍니다. 검증 범위는 persistent local UI VM에서 실제 GameCore Lua binding과 synchronous RNG를 사용해 원본 ranking popup을 실행하고, retained scene 및 timer lifecycle을 거친 결과랍니다. renderer 출력이나 retail UI event timing까지 입증한 것은 아니랍니다.

## 과거 경계 기록

과거 headless host 실행 `evidence/save_restore/20260929T132901Z_9f3534f3d83a`는 turn 24까지 진행한 뒤 turn 25 전에 `AddPopup`에서 실패했답니다. `Source/SDK_BNW_x64/CvGameCoreDLL_Expansion2/CvGame.cpp:7650-7667`의 `CvGame::doTurn`은 활성 플레이어 생존 여부, static tutorial 여부, single-player session 여부를 확인한답니다. 이어 `GC.getPROGRESS_POPUP_TURN_FREQUENCY()`를 game-speed train percent에 맞춰 조정하고, 경과 turn이 해당 주기로 나누어질 때 `CvPopupInfo(BUTTONPOPUP_WHOS_WINNING)`를 넣어 `ICvUserInterface1::AddPopup`을 호출한답니다. 7664행 주석은 이 popup이 synchronous random을 사용한다고 경고한답니다. 이 주기는 설정 가능하므로, 소스의 `/*25*/`와 당시 실행의 turn 25는 보통의 경계를 가리킬 뿐 보편 상수는 아니랍니다.

이 과거 실패는 이후 아래의 retained headless popup 경로로 해결했답니다. 다만 popup dispatch와 random draw가 gameplay state에 영향을 준다는 근거로 계속 보존하겠사와요.

## 원본 popup 동작과 synchronous RNG

검토한 설치본의 원본 script 경로는 다음과 같답니다.

`C:\Program Files (x86)\Steam\steamapps\common\Sid Meier's Civilization V\Assets\DLC\Expansion2\UI\InGame\Popups\WhosWinningPopup.lua`

SHA-256은 `7518289A57DDA5F35E91BF90F168F62B448C245A34C20A928863EB6C24B2E32B`랍니다. 파일의 `LastWriteTime`은 2025-05-18 18:41:58 local time이며, 설치본의 파일 메타데이터일 뿐 공식 배포일이라는 뜻은 아니랍니다.

`OnPopup` 51-58행은 `BUTTONPOPUP_WHOS_WINNING`만 처리하고 popup info를 보관한 뒤 module-local `InstanceManager`를 초기화한답니다. 70-82행은 `Game.Rand(#g_tListOfDudes, ...)`로 presentation name을 뽑고, 84-105행은 이전 mode와 다르며 `IsListModeAllowed`를 통과할 때까지 list mode draw를 반복한답니다. 182-304행의 mode 검사는 생존 플레이어, 정책, 시대, 관광, 불가사의, game option 같은 현재 상태를 살핀답니다. 따라서 draw 수와 결과는 상태에 따라 달라지므로, 고정 draw 수를 흉내 내거나 fallback mode를 고르는 방식은 원본 동작을 보존하지 못한답니다.

이후 script는 현재 플레이어와 도시를 기준으로 점수 계산(예: 308-380행), 행 생성(386-469행), control 배치(172-174행)를 수행하고 176행에서 `UIManager:QueuePopup`을 호출한답니다. 178행에서 `Events.SerialEventGameMessagePopup`에 `OnPopup`을 등록하며, 입력과 닫기 동작에는 `ContextPtr`, `Controls`, `UIManager`, `Mouse`, `KeyEvents`, `Keys`를 사용한답니다(473-489행). 표시/숨김 처리(494-503행)는 turn-timer semaphore와 popup lifecycle event도 변경한답니다.

RNG 경로는 presentation 전용 Lua PRNG가 아니라 native gameplay state랍니다. `Source/SDK_BNW_x64/CvGameCoreDLL_Expansion2/Lua/CvLuaGame.cpp:1500-1507`의 `Game.Rand`는 `GetInstance()->getJonRand().get`을 호출한답니다. `CvGame.cpp:9015-9026`은 `getJonRand`/`getJonRandNum`을 synchronous generator로 다루며, `CvGame.cpp:9370-9374,9568-9569`는 그 상태를 저장하고 읽는답니다. 그러므로 popup draw를 누락하거나 하나 더 소비하면 이후 동기화 결과와 저장 상태가 달라질 수 있답니다.

`g_iListMode`와 `g_iLastListMode`는 8-12행에서 `-1`로 초기화되는 module local이며, 해당 Lua module context가 살아 있는 동안 호출 사이에 유지된답니다. 통합 경로는 각 시험 실행에서 UI VM 하나를 유지하므로 popup 사이에 이 값들이 보존된답니다. popup 이후 UI VM 상태를 저장·복원하거나 retail UI process를 재생성하는 동작은 검증하지 않았답니다.

## 검증된 headless 통합

host는 설치된 원본 `WhosWinningPopup.lua`와 원본 XML layout, `InstanceManager`, `IconSupport`, `FLuaVector` dependency를 persistent local UI VM에 불러온답니다. 실제 GameCore Lua/game binding, `Game.Rand`, live player와 game data, SDK-backed timer lifecycle을 사용한답니다. popup 결과는 소유된 retained scene으로 복사하며, headless consumer는 이를 renderer 출력이라고 주장하지 않는답니다. 원본 handler가 직접 list를 선택하고 synchronous GameCore generator에서 draw를 소비한답니다.

동결된 [`evidence/ui_popup/runtime/92792d745404413ba3b50294ab8065aa/conformance.json`](../evidence/ui_popup/runtime/92792d745404413ba3b50294ab8065aa/conformance.json)은 turn 50까지 간 네 실행을 기록한답니다. `en_US`, `ko_KR` 각각 worker setting 0과 4로 실행했으며 네 건 모두 통과했답니다. 각 실행은 turn 25와 turn 50에서 popup 두 건을 처리했고 mode는 0, 1 순서였답니다. 각 popup의 실제 `Game.Rand` draw 순서(presentation name 뒤 list mode), RNG seed, 소유된 shown/closed scene snapshot이 기록됐으며 validator input도 실행 전후 동일했답니다.

## 남은 UI 경계

기존 headless host 실행 자체의 결과는 retained-control scene이랍니다. 2026-10-03 KST의 [별도 presentation 후보](M3_UI_PIXEL_PRESENTATION.md)는 살아 있는 SDK UI VM을 원본 그림·글꼴과 자체 D3D11/DXGI HWND에 연결하고, 닫힌 context의 그림·클릭 영역을 같은 창·장치에서 교체했사와요. 영어 직렬·한국어 FoundValue 4워커의 두 50턴 실행에서 네 팝업의 초기·크기 변경·닫힘 GPU 버퍼 총 12장, 자동 창 입력·공식 callback·timer/RNG·저장·AI 점수를 검증했고 기존 headless 기준과 shown/closed 상태가 같았답니다. 닫힌 context의 화면 기여를 지워 빈 GPU 버퍼로 만든 범위이며, underlying 세계 화면 복원이나 도시 결정 상태의 재렌더링은 남아 있사와요. 입력은 교체 전후 handshake로 관리한 자동 묶음이며 비동기 실제 입력의 장면 경계 격리를 입증하지 않사와요. 모든 `Present`는 시험 데스크톱에서 표시 가림 상태였으므로 사용자 화면·사람의 입력도 미검증이랍니다. 사용자 직접 gameplay 입력과 decision popup, 원본 화면의 글꼴·스타일 교정, retail UI queue ordering·event timing이 남아 있사와요. host는 명시적으로 빈 active-mod list만 받으며 nonempty active-mod manifest는 지원하지 않는답니다. 실행 중 persistent UI VM을 유지하지만 game save/restore 사이의 VM state 직렬화와 복원은 열린 popup 저장을 포함해 검증하지 않았답니다.

다음 도시 결정 화면의 원본 ProductionPopup·TechPopup 의존성, 현재 컨트롤·receiver 지원 차이와 미지원 분기는 [공식 도시 UI 연결 경계](M6_CITY_DECISION_UI.md)에 정적으로 기록했사와요. 이 조사는 실제 화면 콜백 구현·실행 proof와 구분한답니다.

시험 입력 정책은 이 고정된 configured 40x24 headless fixture와 host 경로에 한정된답니다. arbitrary retail-save 호환성이나 전체 게임 동등성을 뜻하지 않는답니다. worker setting 4에서도 관측 batch에 동시 실행은 없었으므로 실제 multicore 실행이나 speedup을 입증하지 않는답니다. 네 실행 보고서는 언어 간 serialized archive byte equality를 주장하지 않는답니다. archive 및 turn별 비교 범위는 [`M3_EXTENDED_TURNS.md`](M3_EXTENDED_TURNS.md)에 정리했답니다.
