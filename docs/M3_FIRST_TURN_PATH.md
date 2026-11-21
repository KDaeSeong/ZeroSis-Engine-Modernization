# M3: 첫 턴 진입 경로와 호스트 경계

## 현재 관측과 조사 범위

2026-10-01 최신 후보는 영어·한국어 × worker 0·4 네 실행에서 native checkpoint를 새 세션에 복원한 뒤 50턴까지 정상 SDK 진행을 통과했사와요. 같은 언어의 checkpoint·복원 직후·최종 archive는 지도 GUID 16바이트만 독립 새 게임 차이로 정규화한 뒤 133개 구획 전체가 같고, 계속 진행한 48개 턴의 의미 상태 표본·명령·턴 이벤트·탐색 workload도 일치했답니다. 29·38턴의 별도 합법 승급 시험 입력과 25·50턴의 공식 BNW 순위 팝업 원문 Lua·retained scene·SDK 난수·타이머를 포함한 범위이와요. 이 고정 인간 skip fixture는 사용자 조작이나 화면 렌더링·완전한 게임 동등성·유용한 멀티코어를 입증하지 않사와요. [50턴 고정 대조표](../evidence/extended_turns/20261001T115602Z_12bb487f337d/conformance.json) · [공식 UI·난수 대조표](../evidence/ui_popup/runtime/001c8e7abfed47498cb4cfb639623ca0/conformance.json) · [UI 구현 범위](M3_UI_POPUP_BOUNDARY.md)

아래 2026-09-27·29 기록은 각 단계 당시의 첫 진입·두 턴 관측이며, 최신 50턴 범위와 구분하와요.

2026-09-27 첫 턴 실행에서 영어·한국어 격리 세션 모두 인간 턴 진입, 실제 SDK `AutoSave` 기록, 133개 직렬화 섹션, embedded DB integrity, 정상 정리와 DLL 해제를 통과했사와요. 각 세션에서 세 번의 추가 idle `Update`를 수행했으며 턴은 0으로 유지됐답니다. 그 시험의 저장 크기는 영어 9,621,733 bytes, 한국어 9,621,739 bytes였사와요. 실행별 결과는 [첫 턴·저장 대조표](../evidence/first_turn/conformance.json)에 있답니다.

영어·한국어 격리 실행 모두 정상 인간 end-turn 입력에서 SDK를 통해 AI 턴을 처리하고, 일곱 번째 SDK `Update`에서 턴 0→1로 진행했사와요. 두 실행 모두 그 뒤 세 번의 idle `Update`에도 턴 1을 유지하고 정상 정리와 DLL 해제를 통과했답니다. 최종 플레이어 관측에서 비인간 AI 슬롯 1·22·23이 도시를 각각 1곳 보유해 합계 3곳임을 확인했사와요([영어 로그](../evidence/turn_cycle/20260927T130728Z_e9957aeeef94/stdout.log), [한국어 로그](../evidence/turn_cycle/20260927T130803Z_947095a7aac5/stdout.log); 행 형식은 `id,human,turnActive,cities,units`랍니다). 두 언어의 공통 관측은 [턴 사이클 대조표](../evidence/turn_cycle/conformance.json), 개별 결과는 [영어](../evidence/turn_cycle/20260927T130728Z_e9957aeeef94/result.json)와 [한국어](../evidence/turn_cycle/20260927T130803Z_947095a7aac5/result.json)에 있답니다.

2026-09-29 최신 강화 격리 실행은 영어·한국어 각각 턴 0→1 뒤 133개 구획 checkpoint를 저장하고 GameCore DLL을 내린 다음, 새 세션에서 복원해 턴 1→2를 마쳤사와요. 복원 직후 83,125바이트 의미 상태 표본이 저장 직전과 일치했으며, archive는 133개 중 132개 구획이 바이트 단위로 같았답니다. 유일한 차이 Game `3,0`은 별도 고정 턴 1 fixture에서 기존 ReplayMessage 6개와 난수 앞·뒤 Game 바이트가 보존되고, 세션 수 1→2와 `TXT_KEY_MISC_RELOAD` 메시지 한 건이 추가되는 reload metadata 차이와 맞았사와요. 이 metadata 검증은 해당 고정 fixture만을 대상으로 하며 일반 Game 섹션 전체 보존을 입증하지 않사와요. 복원 뒤 세 번의 idle `Update` 동안 턴 1과 인간 입력 대기를 유지했답니다([영·한 저장·복원 대조표](../evidence/save_restore/conformance.json), [영어 로그](../evidence/save_restore/20260929T130348Z_bf47936ffcf6/stdout.log), [한국어 로그](../evidence/save_restore/20260929T130427Z_3d6e46a8a5c2/stdout.log), [저장 복원 경로](M3_NATIVE_SAVE_RESTORE.md)). archive 133개는 bundle 식별 1개와 SDK 직렬화 구획 132개이며, 바이트 동일 132개에는 bundle과 SDK 구획 131개가 포함된답니다. retail Civilization V 저장 호환성·완전한 상태 결정성은 여전히 검증되지 않았사와요.

현재 [NewGameProbe.h](../Source/Host/NewGameProbe.h#L9-L47)는 설정 적용 후 `ICvGame1::Init()`과 `Init2()`를 호출하고 지도·플레이어 상태를 관측한답니다. 그 probe 자체는 `DoGameStarted()` 또는 `Update()`를 호출하지 않사와요. 별도 shared-Lua 격리 새 게임 후보는 영어·한국어 모두 40×24 지도 960칸, 육지 233칸·바다 727칸, 주요 문명 2개·도시국가 2개, 주요 문명 유닛 4개·도시국가 유닛 2개와 턴 0 초기화를 통과했답니다. 실행별 원자료와 입력 해시는 [새 게임 영어·한국어 쌍 검증](../evidence/new_game/conformance.json)에 있사와요.

이 문서는 `Source/SDK_BNW_x64/CvGameCoreDLLUtil/include/CvDllInterfaces.h`, SDK의 `CvGame.cpp`/`CvPlayer.cpp`, 현재 호스트 인터페이스 구현을 따라간 정적 조사랍니다. 위 새 게임 생성 결과는 런타임 증거지만 첫 턴 런타임 결과는 아니며, 게임 실행기 쪽 턴 컨트롤러 구현은 이 SDK 소스에 포함되어 있지 않사와요.

## 공개 호출면과 SDK에서 확인되는 순서

`ICvGame1`은 `CvDllInterfaces.h:979-1065`에 선언되어 있으며 공개 메서드로 `Init`, `Init2`, `DoGameStarted`, `Update`, `UpdateSelectionList`, `UpdateTestEndTurn`, `GetGameTurn`, `GetGameState`, `GetPlayer`를 제공한답니다. 이 인터페이스에는 외부 호출자가 임의로 턴 숫자를 올리는 메서드가 없사와요. `CvDllGame.cpp:298-305`는 `Init`/`Init2`를 실제 `CvGame::init`/`init2`로 전달하고, `CvDllGame.cpp:143-146`은 `DoGameStarted`를 전달하며, `CvDllGame.cpp:484-487`은 `Update`를 `CvGame::update`로 전달한답니다.

SDK 내부 새 게임 초기화 순서는 `CvGame.cpp:402-425`에서 확인된답니다. `init2()`는 `InitPlayers()` → `InitMap()` → 외교 초기화 → 초기 아이템 적용 → 고고학/점수 초기화 → `setFinalInitialized(true)` 순으로 진행한 뒤 성공을 반환한답니다. 이 단계는 지도·문명 초기화 완료를 뜻할 뿐, 인간의 첫 턴 입력 완료를 뜻하지는 않는답니다.

`ICvGame1::DoGameStarted()`는 공개 ABI에 존재하며 실제 `CvGame::DoGameStarted()`는 `CvGame.cpp:890-926`에서 해제 가능한 지형 특성을 계산하고 활성 플레이어 유닛 순환기를 다시 만든답니다. 공개 ABI와 역할을 보면 초기화 뒤 게임 시작 통지 후보인 것이와요. 게임 실행기에서 이를 정확히 언제 호출하는지는 이 SDK 저장소만으로 입증되지 않았지만, 새 호스트는 SDK 계약을 바탕으로 호출 순서를 정의하고 격리된 런타임으로 검증할 수 있답니다. 다만 그 결과가 원본 실행기의 순서와 동등하다는 점은 별도로 검증해야 한답니다.

그 다음 공개 진행 메서드는 `ICvGame1::Update()`랍니다. `CvGame::update()`는 `CvGame.cpp:1436-1546`에서 시작·종료 Lua hook을 발행하고, 일시정지/게임 상태를 확인한 뒤 게임 업데이트를 수행한답니다. 활성 플레이어 수가 0이면 `CvGame.cpp:1488-1493`에서 `gDLL->CanAdvanceTurn()`이 참일 때만 내부 턴 처리를 호출한답니다. 이후 정상 업데이트 경로에서 점수, 전쟁, 이동, 타이머, 플레이어 알림, 턴 비활성화 확인을 수행하고 턴 슬라이스를 증가시켜요(`CvGame.cpp:1495-1524`). 그러므로 외부 호스트의 진행 단위는 게임 인터페이스의 `Update()`이며, 반복 횟수를 턴 수로 간주하면 안 된답니다.

SDK의 `CvGame::doTurn()`은 이름과 달리 임의로 부르는 “턴 시작” API가 아니라 턴 경계 전체를 처리하는 내부 메서드랍니다. 본문은 `CvGame.cpp:7499-7527`에서 종료 경계 작업 뒤 `gDLL->DoTurn()`을 호출하고, 팀·지도·게임 시스템의 차례 처리를 수행한답니다. 이어 `CvGame.cpp:7558-7572`에서 UI 턴 상태를 초기화하고 게임 턴 및 경과 턴을 증가시키며, `CvGame.cpp:7583-7645`에서 턴 방식에 따라 플레이어/팀을 활성화한답니다. 마지막에는 새 게임 턴을 엔진에 알리지요(`CvGame.cpp:7671-7679`). 이 내부 호출 순서를 우회하거나 `GameTurn`을 직접 바꾸면 정상 턴 규칙을 검증한 것이 아니랍니다.

## 인간, AI, 준비 상태와 턴 완료

플레이어의 인간 여부와 활성 상태는 서로 다른 값이랍니다. 설정 단계의 `ICvPreGame1::isHuman(PlayerTypes)` 및 `isReady(PlayerTypes)`는 `CvDllInterfaces.h:1475-1482`에 있으며, 게임 플레이 단계에서는 `ICvPlayer1::IsHuman()`, `IsAlive()`, `IsTurnActive()`가 `CvDllInterfaces.h:1268-1302`에 공개되어 있사와요. `isReady`는 프리게임 슬롯 준비 상태이며 실제 턴을 끝냈다는 뜻으로 볼 수 없답니다. 게임 턴은 `IsTurnActive`와 활성 플레이어 수, 턴 처리 콜백으로 판정해야 한답니다.

순차 턴에서 `CvGame::doTurn()`은 살아 있고 순차 턴을 쓰는 첫 플레이어를 활성화한답니다(`CvGame.cpp:7615-7645`). 동시/동적 턴은 먼저 AI를 활성화하고 인간 처리는 이후 이동 업데이트 경로로 넘긴답니다(`CvGame.cpp:7583-7601`, `CvGame.cpp:8083-8159`). `updateMoves()`는 활성 AI 문명을 처리하고 `allAICivsProcessedThisTurn()`을 확인한 뒤 인간 자동 이동/활성 플레이어 처리로 진행한답니다(`CvGame.cpp:8093-8159`). AI 이동은 `AI_unitUpdate()` 및 자동 이동 상태를 거쳐 완료 판정한답니다(`CvGame.cpp:8164-8200`, `CvGame.cpp:8231-8344`). 이 과정은 AI 슬롯을 인간 슬롯처럼 자동 완료 처리하는 것이 아니랍니다.

플레이어 활성화 자체도 많은 엔진 부작용을 일으킨답니다. 공개 `ICvPlayer1::SetTurnActive()`는 `CvDllInterfaces.h:1293-1295`에 노출되지만, 실제 `CvPlayer::setTurnActive()`는 `CvPlayer.cpp:15846-15950`에서 종료 상태 초기화, 활성 인원수 변경, UI dirty/status 알림, 초기 유닛/AI/도시 처리를 수행한답니다. 턴 완료 때도 비활성화와 `TURN_END` 등 알림이 수반된답니다(`CvPlayer.cpp:16001-16007`). 따라서 이 setter를 테스트 편의용 턴 스킵이나 직접 게임 턴 진행 대용으로 쓰지 말고, 새 호스트의 정상 업데이트/턴 컨트롤러 경로 안에서 검증해야 한답니다.

## 외부 호스트가 제공해야 할 턴 서비스

턴 진행은 GameCore DLL만으로 완결되지 않는답니다. SDK의 호스트 ABI인 `ICvDLLUtility.h`는 `DoTurn()`(`:62`), 턴 완료 송수신(`:92-98`), 초기 AI 처리 통지와 `allAIProcessedThisTurn()`(`:160-168`), 슬롯 제어(`:170-171`), `GameplayTurnChanged()`/`PublishNewGameTurn()`/`SendGameDoTurnProcessed()`(`:303-327`), `allAICivsProcessedThisTurn()`(`:387`)를 외부 엔진 계약으로 선언한답니다. 이 중 `allAIProcessedThisTurn`과 `allAICivsProcessedThisTurn`은 별개 API이므로 하나로 뭉뚱그리면 안 된답니다.

현재 호스트는 이 턴 경계를 로컬 단일 플레이어 명령·상태로 연결했으며, [HostServices.h](../Source/Host/HostServices.h#L142-L209)의 로컬 turn signal, player option 명령과 autosave 경로가 실제 첫 턴 및 양 언어의 한 사이클에서 관측됐사와요. 두 실행 모두 `PLAYEROPTION_WAIT_END_TURN=true`, 유닛별 SDK `MISSION_SKIP`, `UpdateTestEndTurn`, `DoControl(CONTROL_ENDTURN)`을 거쳐 인간 차례를 정상 종료했으며, 직접 턴 숫자나 플레이어 활성 상태를 바꾸지 않았답니다. SDK ABI의 완료·처리 API와 구현 연결은 [CvDllInterfaces.h](../Source/SDK_BNW_x64/CvGameCoreDLLUtil/include/CvDllInterfaces.h#L979-L1065), [ICvDLLUtility.h](../Source/SDK_BNW_x64/CvGameCoreDLLUtil/include/ICvDLLUtility.h#L92-L168), [ICvDLLUtility.h의 진행 알림](../Source/SDK_BNW_x64/CvGameCoreDLLUtil/include/ICvDLLUtility.h#L303-L327)에 근거하와요. 이 검증은 로컬 단일 플레이어의 언어별 한 사이클이지 네트워크 멀티플레이 구현의 증거는 아니랍니다.

UI 쪽도 턴 진입 이벤트를 관측하는 계약이랍니다. `CvPlayer.cpp:15892-15965`는 플레이어 턴 시작 상태와 활성 플레이어 시작 이벤트를 발행한답니다. 현재 `HostServices.h:189-201`은 `PublishEndTurnDirty`, 플레이어 턴 상태, 활성 플레이어 턴 시작/종료를 호스트 이벤트로 기록한답니다. 이는 화면 없는 호스트가 이벤트를 보존하는 구현이지, 사용자 입력을 대신하거나 인간의 턴을 자동 완료하는 구현은 아니와요.

## 다음 연결 단계와 검증 기준

다음 검증은 턴 2 이후의 장기 진행, retail 저장 파일 호환성, 화면 출력과 모드 통합이랍니다. 새 세션 저장 복원과 한 번의 턴 재개는 통과했지만, 장기 진행과 원본 실행기와의 완전한 동등성은 아직 미검증이와요.

첫 턴 진입·자동 저장, 정상 end-turn부터 턴 0→1, 그리고 새 세션 복원 뒤 턴 1→2까지 영어·한국어 모두 검증됐답니다. 복원 전·후에 각각 세 번의 idle update를 관측했고, 복원 의미 상태 표본과 133개 중 132개 archive 구획의 바이트 일치를 확인했사와요. 별도 M5 worker 행렬은 0·1·2·4 요청을 포함하며, conformance의 여섯 EN/KR × 1/2/4 비교 행은 각 언어 안에서 직렬 기준과 worker 실행의 턴 1·복원 직후·턴 2 archive를 대조했답니다. 각 언어 안에서 세 archive 비교마다 총 133개 중 132개 section은 byte-exact였고, Map section의 GUID 16바이트를 제외한 나머지도 같았으며, 영어·한국어 전체 바이트 동일성은 검사하지 않았사와요. 별도 한국어 직렬 반복 실행도 세 archive를 GUID만 정규화해 비교했답니다. 이는 작은 SDK 탐색 점수 경로에 한정된 결과이며, 요청 2·4는 여러 thread를 생성했지만 점수 작업은 한 thread가 처리했사와요. worker 0 source 기본값은 확인했으나 unset 환경변수 런타임은 시험하지 않았고, 물리 멀티코어·성능·전체 게임 동등성 증거도 아니와요. retail 저장 호환성, 렌더러, 전체 게임 계산 멀티코어, Stage 승격, 원본 실행기/게임과의 완전 동등성은 미검증이랍니다. [작업자 행렬 상세](M5_SDK_EXPLORATION_WORKERS.md)
