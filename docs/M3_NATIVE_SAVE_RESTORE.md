# M3: 네이티브 SDK 저장과 복원 경로

## 현재 상태

2026-10-01에는 저장 후보 19개 패치·10개 translation unit 기반으로 영어·한국어 × worker 0·4 네 실행을 50턴까지 진행했사와요. 정상 턴 1 checkpoint를 새 세션에서 읽는 기존 복원 경로를 그대로 사용하고, 48개 추가 턴과 합법 승급 시험 입력·공식 순위 팝업 두 번을 거쳤답니다. 같은 언어의 직렬·4워커는 checkpoint·복원 직후·50턴 archive의 133개 구획을 지도 GUID 16바이트만 정규화한 뒤 전체 일치시켰으며, 각 실행 안에서 지도 GUID도 보존했사와요. 언어별 모든 계속 턴의 의미 상태 표본·명령·이벤트도 같았답니다. [50턴 고정 대조표](../evidence/extended_turns/20261001T115602Z_12bb487f337d/conformance.json) · [SDK19 연결 기록](../evidence/save_restore_sdk/20260930T125743Z_1d1ec65732fd/build_result.json)

추가 패치는 `CvAIOperation::Reset`에서 저장되는 reinforcement 플래그 기본값을 초기화하며 필드·순서·저장 스키마를 바꾸지 않는답니다. 서로 다른 실행 사이의 worker 대조와 같은 실행의 restore 전후 132/133개 byte-exact 판정은 다른 비교이므로 아래 턴 1 reload metadata 설명을 유지하와요. UI가 실제 열린 뒤의 새 세션 복원, retail 저장 호환성, 비어 있지 않은 활성 모드 manifest, 전체 상태 동등성·장시간/실패 회귀·Stage 승격은 남아 있사와요.

## 2026-09-29 두 턴 저장·복원 이력

2026-09-29 최신 격리 실행에서 영어와 한국어 모두 실제 SDK native archive를 새 GameCore 세션에 복원하고, 복원 뒤 정상 턴을 이어 갔사와요. 각 실행은 새 게임 턴 0→1 뒤 133개 구획으로 턴 1 checkpoint를 만들고 GameCore DLL을 내렸으며, 새 세션에서 이를 읽고 턴 1→2까지 진행한 뒤 정상 종료했답니다. 최신 영어 `20260929T130348Z_bf47936ffcf6`와 한국어 `20260929T130427Z_3d6e46a8a5c2`는 강화 대조표에서 통과했사와요([대조표](../evidence/save_restore/conformance.json), [영어 로그](../evidence/save_restore/20260929T130348Z_bf47936ffcf6/stdout.log), [한국어 로그](../evidence/save_restore/20260929T130427Z_3d6e46a8a5c2/stdout.log)).

복원 직후 GameCore 의미 상태 표본은 양쪽 모두 83,125바이트로 같았고, 지도 960칸·플레이어 슬롯 64개·도시 3개·유닛 7개·기술 상태 행 5,184개를 포함해 검사한 값이 checkpoint 직전과 일치했사와요. archive는 bundle 식별 1개와 실제 SDK 직렬화 구획 132개, 합계 133개랍니다. 바이트 비교에서 동일한 132개는 bundle 식별 구획 1개와 SDK 직렬화 구획 131개를 포함하며, 달라진 유일 구획은 Game `3,0`이와요. 별도 고정 영어·한국어 턴 1 fixture 검증에서 Game 차이는 저장된 난수까지의 앞부분과 세션 카운터 뒤의 뒷부분이 그대로이고, 기존 ReplayMessage 6개가 바이트 그대로 보존되며, 세션 수가 1→2로 늘고 `TXT_KEY_MISC_RELOAD` 메시지 1개가 추가되는 reload metadata 차이와 일치했답니다. 이 검사는 고정 fixture 범위에 한정되며 일반 Game 구획 전체 보존이나 retail 호환성을 뜻하지 않사와요. 복원 뒤 세 번의 idle `Update`에서 턴 1과 인간 입력 대기 상태를 유지했고, 정상 end-turn 입력으로 턴 2에 도달했답니다.

이 결과는 **이 프로젝트의 bundle 식별 native archive에 대한 격리 SDK 저장·복원·턴 재개 통과**를 뜻한답니다. 기존 Civilization V retail 저장 파일 호환성, 완전한 게임 상태 결정성, 설치된 게임 실행, 전체 GameCore 동등성이나 정식 Stage 승격을 증명하지는 않사와요. 그러므로 Civ V x64 이식과 게임 계산 멀티코어라는 사용자 목표 전체는 아직 완료되지 않았답니다.

## 실행 기록과 검증 범위

| 언어 | run ID | checkpoint | 복원 직후 | 재개 턴 | 결과 |
|---|---|---:|---|---|---|
| 영어 `en_US` | `20260929T130348Z_bf47936ffcf6` | 9,695,395 bytes, 133 sections | 턴 1, 활성 인간 1명, 40×24 지도 | 1→2 | 통과 |
| 한국어 `ko_KR` | `20260929T130427Z_3d6e46a8a5c2` | 9,695,567 bytes, 133 sections | 턴 1, 활성 인간 1명, 40×24 지도 | 1→2 | 통과 |

두 실행의 상태 표본은 SHA-256 `59ee8704c4e47b8186b7bf5a8f917c84252ad4455588f226957bbbc649b8faf9`로 일치했사와요. [통합 대조표](../evidence/save_restore/conformance.json)에는 snapshot 행 수, 복원·재개 관측, 132/133 archive 구획 비교, 고정 Game metadata fixture 검증과 남은 호환성 플래그가 있답니다. 각 run 폴더의 `result.json`, `stdout.log`, `stderr.log`가 실행별 자료이며, [최신 SDK 연결 기록](../evidence/save_restore_sdk/20260929T130300Z_bde1b7fd4ce6/build_result.json)은 저장·복원 후보가 18개 패치, 9개 translation unit 재컴파일, 기존 오브젝트 150개와 새 게임 오브젝트 2개 재사용으로 연결됐음을 기록하와요. 이 후보는 별도 Build 산출물이며 활성 SDK를 갱신하거나 accepted bundle을 교체하지 않았답니다.

## 실제 저장·복원 경로

`SdkGameSave::Capture`는 `Pregame → Game → Map → Supporting → Team[0..63] → Player[0..63]` 순서로 실제 SDK writer를 호출하고, bundle 식별 섹션을 앞에 둔 133개 archive를 만든답니다([저장 구현](../Source/Host/SdkGameSave.h#L15-L82)). 영어·한국어의 턴 0 첫 진입 자동 저장은 별도 실행에서 각각 133개 섹션과 내장 SQLite 무결성 검사를 통과했으며, 그 초기 자동 저장 자료는 [첫 턴 대조표](../evidence/first_turn/conformance.json)에 있사와요.

복원 구현은 새 owner-thread 세션과 미초기화 Game/Map을 요구하고, archive 형식·체크섬·bundle 식별을 검사한 뒤 SDK reader를 호출한답니다([복원 구현](../Source/Host/SdkGameRestore.h#L10-L97), [새 세션 실행과 사후 검사](../Source/Host/HostRun.h#L114-L169)). Pregame을 초기화하고 저장값을 읽은 뒤 `GAME_LOADED`와 호스트의 loaded-game 상태를 설정하며, `HostServices::IsLoadedGame()`은 그 상태를 반환하와요([서비스 구현](../Source/Host/HostServices.h#L404)). 이어 `Game.Read → Map.Read → Supporting.Read → Team.Read[0..63] → Player.Read[0..63]`를 수행한 다음 플레이어 `LaterInit()`과 `DoGameStarted()`를 호출하고, 의미 상태·활성 인간·지도 크기와 idle 대기를 검증한답니다.

초기 문서의 “복원 미구현”, “`IsLoadedGame()`은 항상 false”, “복원 준비에 `Init2()`가 필요”라는 기술은 현재 코드와 실행 결과에 맞지 않아 정정했사와요. `CvTeam::Read`와 `CvPlayer::Read`는 각자 내부에서 인수 없는 `reset()`을 호출하며, 그 기본 인수는 `bConstructorCall=false`라 저장값을 읽기 전에 하위 배열과 객체 상태를 준비한답니다([팀 reader](../Source/SDK_BNW_x64/CvGameCoreDLL_Expansion2/CvTeam.cpp#L6814-L6826), [플레이어 reader](../Source/SDK_BNW_x64/CvGameCoreDLL_Expansion2/CvPlayer.cpp#L21790-L21805), [플레이어 reset](../Source/SDK_BNW_x64/CvGameCoreDLL_Expansion2/CvPlayer.cpp#L1035-L1090), [팀 reset](../Source/SDK_BNW_x64/CvGameCoreDLL_Expansion2/CvTeam.cpp#L231-L289)). 이 경로에 `Init2()`를 추가 호출하지 않으며, 복원한 활성 턴 수가 1인 것도 실제 실행에서 확인했답니다. `Init2()`는 새 게임 지도와 시작 항목을 만드는 초기화이므로 복원 전 단계로 쓰지 않사와요.

## 아직 남은 관문

- retail Civilization V 저장 파일을 읽고 쓰는 호환성은 검증하지 않았사와요.
- 의미 상태 표본은 넓은 범위의 부분 비교이며, 전체 상태 결정성이나 두 실행기의 완전 동등성은 입증하지 않았답니다.
- 설치된 게임은 실행하지 않았고, 후보는 accepted Stage에 승격되지 않았사와요.
- 장기 진행, 실패 주입 뒤 전체 복구, 렌더러, 활성 모드 연동, 게임 계산 멀티코어와 성능은 별도 검증 과제이와요.
