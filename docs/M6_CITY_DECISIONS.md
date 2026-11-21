# M6: 실제 SDK 도시 생산·연구 선택과 턴·복원

2026-10-02 별도 EN/KO 실행에서 실제 GameCore SDK가 도시 생산 명령과 연구 명령을 받아들이고, 이후 정상 한 턴을 진행하는지 확인했사와요. 이 시험은 앞선 turn-zero `MISSION_FOUND` 시험에 새로운 명령을 보낸 별도 실행이며, 그 역사적 시험 결과는 [M6_FOUND_CITY_ACTION.md](M6_FOUND_CITY_ACTION.md)에 그대로 보존했답니다. 두 단계의 결과를 한 실행으로 합치지 않고, 각 실행의 artifact와 복원 경계를 따로 검증했사와요.

| 언어 | 실제 실행 ID | turn-zero 결정 상태 | 1턴 뒤 결정 상태 |
|---|---|---|---|
| 영어 (`en_US`) | `20261002T121011Z_ee7f0e5c3d76` | `[0,0,0,8192,1,1,1,0,70,0,35,1]` | `[1,1,0,8192,1,1,1,5,70,4,31,1]` |
| 한국어 (`ko_KR`) | `20261002T121327Z_86902f81ea35` | `[0,0,0,8192,1,1,1,0,70,0,35,1]` | `[1,1,0,8192,1,1,1,5,70,4,31,1]` |

각 상태 행의 열은 `turn, elapsedTurn, activePlayer, cityID, unitType, techID, orderQueueLength, productionStored, productionNeeded, researchProgress, researchLeft, population` 순서랍니다. 두 언어 모두 같은 실제 SDK 도시 ID `8192`, 생산 유닛 ID `1`, 기술 ID `1`에서 시작했으며, 법적 생산·연구 후보를 SDK Lua의 `city:CanTrain` 및 `player:CanResearch`로 걸러낸 뒤 전송했사와요. 받아들인 생산 선택은 도시의 생산 유닛과 길이 1의 큐에서 다시 확인했고, 연구 선택은 플레이어의 현재 기술에서 확인했답니다. 이후 생산량은 `0→5` (필요량 70), 연구량은 `0→4` (남은 양 `35→31`)로 진행됐고 도시 인구는 1로 유지됐사와요.

호스트에 포함된 probe는 생산에 `Game.CityPushOrder(city, OrderTypes.ORDER_TRAIN, unitID, false, true, true)`를 호출했사와요. 호출은 `EngineServices.sendPushOrder`를 지나 실제 SDK 수신기 `ResponseCityPushOrder(active, cityID, order, data, alt, shift, control)`까지 전달됐답니다. 연구는 `Network.SendResearch(techID, 0, -1, false)`에서 `EngineServices.sendResearch`와 `ResponseResearch(active, tech, 0, false)`로 이어졌사와요. 명령 인자와 수신기 연결은 보존된 `CityDecisionProbe.h`, `HostServices.h`, `LocalSdkSession.h`에서 대조했답니다. 이는 공식 Lua/Network API와 SDK 수신 경로를 통한 명령 시험이지, ProductionPopup/TechPopup을 화면에서 클릭하거나 사용자가 조작한 시험은 아니랍니다. `CanTrain`·`CanResearch`의 합법성 사전 검사는 포함했지만 renderer·도시 결정 UI 동작은 검증하지 않았사와요.

결정 입력 뒤 SDK 알림 만료를 위한 update를 수행했고, `CITY_DECISION_NOTIFICATION_UPDATE=SDK_UPDATE_WITHOUT_TURN_ADVANCE` 관측과 함께 전후 12개 상태 값이 두 언어에서 그대로 같았사와요. 그다음 정상 SDK 턴 완료 경로를 한 차례 진행하여 두 언어 모두 turn/elapsed가 `0→1`이 되고 도시 선택은 유지되며 생산·연구만 전진했답니다. 정상 턴 cycle event와 상태 표본은 EN/KO 의미 대조에서 일치했사와요.

각 언어 실행은 명시적 활성 모드 0개로 별도 SDK session 세 개를 사용했답니다. 첫 session에서 실제 `MISSION_FOUND`로 만든 도시를 turn-zero checkpoint에 저장하고, 두 번째 session에서 복원해 idle update 세 번 뒤에도 상태 표본을 확인했사와요. 그 상태에서 도시 결정을 보내 정상 턴을 진행하고 turn-one checkpoint를 썼으며, 세 번째 fresh session에서 이를 복원하고 idle update 세 번을 더 수행했사와요. 따라서 각 실행에는 시작 autosave와 turn-zero·turn-one 두 checkpoint, 두 개의 복원 archive가 있답니다. 세션마다 `SESSION_ACTIVE_MODS=0`을 확인했고 Stage 승격 요청·승격은 모두 거짓이었사와요.

각 언어의 두 native 복원쌍에서 133개 save 구획 중 CvGame 이외 132개는 바이트 단위로 같았답니다. CvMap GUID는 각각의 checkpoint/restore 쌍 안에서 유지됐고, RNG 및 replay version까지의 CvGame prefix와 기존 replay 기록은 정확히 보존됐사와요. CvGame에서는 원본 `CvGame::Read` 계약대로 replay 하나와 session counter 하나가 추가됐답니다. turn-zero 복원은 replay 수 `2→3`, 세션 수 `1→2`였으며 turn-one 복원은 replay 수 `9→10`, 세션 수 `2→3`이었사와요. 추가 replay는 각 checkpoint turn, type 0, player 0, plot `(-1,-1)`의 현지화된 session 시작 기록이었고 counter 뒤 나머지 Game bytes도 같았답니다. 각 실행에서 복원 직후 및 복원 뒤 세 idle update의 네 의미 상태 행은 모두 결정 후 상태와 같았사와요. EN과 KO의 save archive 전체 바이트를 서로 비교하지는 않았답니다.

검증기는 원본 SDK·호스트를 빌드하거나 게임 UI를 실행하지 않고 실제 실행 artifact를 독립 분석했사와요. 고정 검증 결과는 [EN/KO conformance](../evidence/city_decisions/validators/20261002T122447Z_8a2f98738c1a/conformance.json), SHA-256 `312e7897e54608a346d7b8067ed1a3556ec1c68ad46c3b85e1b323e0de1926c8`랍니다. 검증기는 원 실행 상태행과 stdout·result 기록을 대조하고, save archive·GameCore replay/session 증가·132개 section·세션·입력 hash·빌드 source closure를 교차 확인했사와요. 실행에 사용한 GameCore 후보 hash는 `e85735b6dee55aeeddd286e4a959cd0f19ed45945a090654d1c4263758925354`랍니다. 빌드·runtime artifact와 동결한 SDK·도구 참조 사본은 해당 conformance에 연결되어 있사와요.

번들에 기록된 `prepare_native_host_bundle.py`의 실행 당시 SHA-256은 `0d9f2da1c9b0cccc2521231b62614ac34bcbbab68641e1f5b32848ec75758be1`이며, 이를 보존한 [Stage 검토용 사본](../Stage/NativeHost/Review/tools/prepare_native_host_bundle.py)이 같은 hash임을 새 검증기 proof가 독립 확인했사와요. 현재 `tools/prepare_native_host_bundle.py`는 이후 변경되어 그 hash와 다르며, proof에는 동결 사본과 현재 파일의 hash를 분리해 기록했답니다.

기존 [도시 건설 검증](../evidence/found_city/validators/20261002T122214Z_2ac044cf18b1/conformance.json)은 SHA-256 `da0aa84507f0acae113b19cea0652afaa398196a27845123e204a7fcbed46c2a`의 별도 turn-zero EN/KO proof랍니다. 별도 M5 부지 점수 행렬은 [최신 conformance](../evidence/city_site_runtime/20261002T122213Z_6dc2fc7bd9f7/conformance.json), SHA-256 `7877d161bfb54c67923c4b17e0b32aab1e5ad4103da01a3d8ebfe21d14160d1c`에 있사와요. 그 경로의 별도 CPU trace 실행은 QPC 오차 정책을 적용한 실제 물리 코어 겹침 검증을 통과했사와요. 이 도시 결정 시험과 별개의 함수 범위 증거이며 성능 향상을 뜻하지는 않사와요. [M5 CPU 추적과 고정 proof](M5_CITY_SITE_CPU_TRACE.md)

이 결과는 도시 생산·연구 결정의 SDK 전달, 한 번의 정상 턴 진행, 해당 두 checkpoint의 격리 fresh-session 복원만을 입증하와요. UI 렌더링·실제 화면 클릭·retail EXE/저장 호환성·멀티플레이·장시간 또는 실패 회귀·기준 게임과 전체 상태 동등성·엔진 전체의 물리 병렬 실행과 성능 향상·정식 Stage 승격은 남아 있답니다. 기존 이름·ID·버전·저장 키·schema·밸런스·MODS·Stage 산출물은 이 작업에서 변경하지 않았사와요.
