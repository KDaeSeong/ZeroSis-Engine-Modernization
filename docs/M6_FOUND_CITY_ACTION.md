# M6: 실제 SDK 도시 건설과 native fresh-session 복원

이 문서는 2026-10-01에 수행한 turn-zero 도시 건설·복원 시험의 역사적 기록이랍니다. 이후 생산·연구 명령과 정상 턴 진행을 더한 별도 검증은 [M6 도시 결정 문서](M6_CITY_DECISIONS.md)에 기록했으며, 두 결과를 하나의 실행으로 합산하지 않사와요. 아래 실행 ID와 고정 대조표는 당시 시험 그대로 보존했답니다.

2026-10-01 영어·한국어의 별도 고정 turn-zero 실행에서 시작 정착민에게 원본 규칙 DB의 정상 `MISSION_FOUND` 액션을 보내 도시 건설을 확인했사와요. 이 입력은 기존 50턴 승급/팝업 fixture와 별도이며, 실제 GameCore를 격리 실행부에서 로드했답니다.

| 언어 | 실행 ID | 결과 |
|---|---|---|
| 영어 (`en_US`) | `20261001T132958Z_85b26e6ec8a4` | 도시 건설·새 세션 복원 통과 |
| 한국어 (`ko_KR`) | `20261001T133138Z_9f53f21a6da0` | 도시 건설·새 세션 복원 통과 |

두 실행 모두 규칙 DB에서 `MISSION_FOUND`의 실제 mission ID 21과 `GameInfoActions`의 `ActionInfoIndex` 22를 확인했사와요. 선택한 시작 정착민 unit ID 8192에 `Game.CanHandleAction` 사전 확인 뒤 `Game.HandleAction`을 호출했고, SDK 경로는 `sendPushMission`에서 `CvDllNetMessageHandler::ResponsePushMission`으로 이어졌답니다. 승격 fixture의 `Game.HandleAction` 입력이나 `SendUnitCommand`를 재사용하지 않고 정상 도시 건설 mission을 통과했사와요.

한 번의 정상 SDK `Update` 뒤 플레이어 0에 도시 ID 8192가 (11, 15)에 생겼고 인구는 1이었답니다. 창립자 정착민은 맵에서 사라졌으며, 다른 인간 유닛 한 기가 남았사와요. 결과 DB 표본은 도시 1행·유닛 5행이었답니다. 새로 지은 도시의 상태 표본은 저장 직전·복원 직후·복원 뒤 세 번의 idle update 후에도 해시 `983bf1385e8f01fbe575dca49d1015cfd3c8a2b72b74d2fe1b6ddd497d2ecde1`로 같았사와요.

도시 건설 뒤 native checkpoint는 영어 9,636,521바이트, 한국어 9,636,587바이트로 각각 133개 구획을 담았답니다. 각 언어의 같은 실행 내 checkpoint와 새 GameCore 세션 복원본을 비교해 CvGame 이외 132개 구획은 바이트 단위로 같았사와요. CvGame 구획에는 고정 복원 경로의 metadata 변화만 있었답니다. 기존 replay 메시지는 바이트 동일했고 replay 수는 2→3으로 늘며 turn-zero의 현지화된 세션 시작 메시지 하나가 추가됐사와요. 세션 수는 1→2였고 RNG/replay version까지의 prefix와 session counter 뒤 suffix는 같았답니다. 영어·한국어 간 archive 전체 바이트 비교는 수행하지 않았사와요.

이 검사는 `--check-found-city` 실행 모드의 별도 도구 [run_found_city_probe.py](../tools/run_found_city_probe.py)와 [verify_found_city_probe.py](../tools/verify_found_city_probe.py)로 수행했사와요. 승급 fixture의 입력 정책이나 기존 50턴 대조표에 합쳐 세지 않사와요. [영어·한국어 전체 검증 결과](../evidence/found_city/validators/20261001T133337Z_1a3ac8bc417a/conformance.json)는 SHA-256 `fbac834736943ba28353fe71a68166aeba3f5cdc116891e0cc5d83afdba65374`이며, 상위 [evidence/found_city/conformance.json](../evidence/found_city/conformance.json)은 이 frozen 결과를 가리키는 포인터 파일이랍니다.

범위는 고정 turn-zero 도시 건설과 그 상태의 native 새 세션 복원까지랍니다. 실행 뒤 턴 진행은 확인하지 않았으며 renderer, 도시 생산·연구 선택, decision UI, 화면에서의 사용자 입력, Steam/DLC entitlement, retail EXE·저장 호환성도 검증하지 않았사와요. 활성 모드 목록은 비어 있었고, accepted Stage는 승격하지 않았답니다. 따라서 이 결과는 전체 엔진 개조나 M6 입력/UI 완료를 뜻하지 않사와요.
