# 공유 Lua와 새 게임 실행 후보

2026-09-27, 실제 x64 GameCore의 `Init → Init2`를 호출하는 별도 후보가 영어·한국어에서 새 게임 생성과 정상 종료를 통과했사와요. 화면 없는 독립 실행부에서 확인한 결과이며, 턴 진행·저장/불러오기·멀티코어 완료를 뜻하지 않사와요. 기존 `Stage/NativeHost`와 원본 설치 자료는 보존하며, 실행마다 `Build/NewGameRuntime`에 새 사본을 만들고 입력 해시를 다시 대조한답니다.

## 실제 새 게임 관측

영어 실행 `20260927T072630Z_b70bfada5fbb`와 한국어 실행 `20260927T072700Z_4a1ece09dfcb`는 같은 호스트·GameCore·공유 Lua 및 규칙 입력을 사용했사와요. [실행 쌍 검증](../evidence/new_game/conformance.json)은 입력·소스·로그 해시, 언어, SDK/Lua 관측값, 정상 종료와 DLL 해제를 재확인했답니다.

| 항목 | 두 실행의 실제 관측 |
| --- | --- |
| 지도 | 40×24, 960칸, 육지 233칸·바다 727칸 |
| 지형 검사 | 실제 SDK Lua로 전체 960칸 순회, 알 수 없는 지형 0칸 |
| 플레이어 | 주요 문명 2개·도시국가 2개, 야만인은 별도 |
| 시작 유닛 | 주요 문명 각각 2개, 도시국가 합계 2개, 총 6개 |
| 시작 상태 | 주요 문명의 도시 0개, 턴 0, 최종 초기화 완료 |
| 종료 | 오류 출력 없음, 정상 정리 완료, GameCore DLL 해제 |

두 언어의 관측 집계와 호스트 알림은 같았사와요. 전체 타일·유닛 상태의 직렬화 비교까지 한 것은 아니므로 완전한 동일 시드 재현성 검증과는 구분하와요.

## 실제 실행에서 발견한 결함

| 결함 | 근거와 조치 |
| --- | --- |
| 호스트와 GameCore가 서로 다른 정적 Lua를 사용 | 실제 지도 생성 중 `luaH_free`가 다른 모듈의 `dummynode_`를 해제하려 했사와요. 디버거 주소와 링크 맵 심볼 주소가 일치했으며, 양방향·두 호출자 빌드의 최소 재현 4건 모두 `0xC0000374`로 종료됐답니다. 후보는 같은 `ZeroSisLua51_x64.dll`을 사용하며, 동일 시험의 4개 자식 프로세스·128회 테이블 생성/정리가 통과했사와요. |
| C++ 예외가 Lua 인터프리터 프레임을 통과 | 네이티브 예외가 Lua의 내부 오류 복귀 지점을 무효화하는 실제 스택을 확인했사와요. 공유 Lua의 C 함수 호출 바로 바깥에서 예외를 잡고 C++ 객체 정리 후 Lua 오류로 전달한답니다. 실제 디스패치, 중첩 보호 호출, 재사용, 긴 메시지, 일반 Lua 오류와 코루틴의 70개 검사가 통과했사와요. |
| 지도 생성 오류 반환 무시 | 필수 스크립트 적재와 보호 호출 실패를 전달하고 생성기를 `unique_ptr`로 소유하는 후보를 만들었사와요. 선택 함수가 없는 경우의 기본 동작은 유지하며, 존재하는 함수의 실행 오류는 중단하와요. 지도 생성 뒤 수집도 보호 호출 안으로 옮겼답니다. SDK 2개 소스만 별도로 컴파일하고 기존 객체 159개와 연결한 후보랍니다. |
| 규칙 표 공개 중 메모리 부족 | `GameDefines` snapshot을 소멸시킨 뒤 같은 함수에서 Lua 오류를 발생시키면 Windows unwind가 소멸자를 다시 실행하는 충돌을 재현했사와요. 소유 프레임을 인라인되지 않는 별도 함수로 분리한 뒤, 두 호출자 빌드 각각 435곳의 Lua 할당 실패와 같은 서비스의 재시도를 통과했답니다. |

## 연결한 기능

- `NewGameConfig`는 실제 규칙 DB에서 Type별 ID를 조회하고, 대륙 지도·결투 크기·주요 문명 2개·도시국가 2개·고정 난수 시드와 옵션을 설정한 뒤 읽어서 대조하와요. 규칙에 맞춰 프리게임 슬롯·승리 조건 저장소도 재설정한답니다.
- `GameDefines`는 VM 생성 시점의 실제 `Defines`를 조회하와요. 숫자·문자열·NULL을 구분하고, 새 VM은 변경된 DB 값을 읽으며, Lua에서 정확하게 표현할 수 없는 정수와 무한 실수는 거부한답니다.
- `DB.Query`는 지도 스크립트에서 쓰는 단일 SELECT와 익명 매개변수 바인딩을 지원하와요. 행 자료를 호스트 소유 snapshot으로 복사하여 DB statement 수명과 분리했으며, Lua/C++ 할당 실패와 같은 VM의 재사용을 검사했답니다.
- 보유 지도에서 요구하는 `table.fill` 두 호출 형태와 `math.clamp(value, minimum, maximum)`을 연결했사와요. 원본 지도 알고리즘이나 원본 스크립트를 대체하지 않았답니다.
- 필요한 플레이어 슬롯, 턴 상태, 팀·기술 알림과 지도 변경 알림을 화면 없는 호스트의 상태/이벤트로 보관하와요. 이는 그래픽·입력·음향 재생의 구현을 뜻하지 않사와요.
- 팝업 억제 상태는 UI 어댑터 사이에 공유하고, 선택 입력이 없는 세션의 유닛·플롯 선택 조회는 빈 상태를 반환하와요. 유닛 깃발 알림은 빌린 어댑터에서 ID와 소유자를 즉시 복사해 이벤트로 보존하와요. 그래픽 없는 SDK가 모든 유닛 소멸 알림을 보내지는 않으므로 이를 살아 있는 유닛 목록으로 취급하지 않사와요.
- Steam 연결이 없는 시험 호스트는 통계 변경 실패를 반환하고, 실패한 조회의 출력값을 보존하며, 업적을 해제했다고 보고하지 않사와요. 실제 두 실행에서는 발견 타일 통계 요청 23회가 이용 불가로 기록되었으며, 별도 업적 계정이나 가짜 성공 값을 만들지 않았답니다.
- 생성 완료 뒤 SDK와 Lua 양쪽에서 전체 타일 수, 지형 유효성, 육지/바다, 주요 문명·도시국가와 유닛 수를 대조하도록 성공 판정을 구성했사와요. 종료와 DLL 해제까지 확인되어야 후보 성공 표식이 나온답니다.

## 재현과 증거

후보를 다시 만드는 순서는 다음과 같사와요. 모든 명령은 프로젝트 폴더에서 실행하와요.

```powershell
python tools/build_shared_lua_runtime.py
python tools/verify_shared_lua_boundary.py
python tools/verify_shared_lua_callbacks.py
python tools/build_new_game_sdk_candidate.py
python tools/verify_map_generator_failure.py
python tools/host_new_game_components.py build
python tools/host_new_game_components.py verify
python tools/run_new_game_probe.py --compile --shared-lua --sdk-new-game --language en_US
python tools/run_new_game_probe.py --shared-lua --sdk-new-game --language ko_KR
python tools/verify_new_game_candidate.py --run <영어_실행_ID> --run <한국어_실행_ID>
```

공유 라이브러리를 다시 빌드하면 그것을 소비하는 증거도 다시 만들어야 한답니다. 각 실행은 소스·도구·응답 파일·바이너리·로그의 해시를 남기며, `check_artifacts`가 오래된 조합을 거부하와요.

- [정적 Lua 충돌과 공유 Lua 비교](../evidence/shared_lua_boundary/conformance.json)
- [C++/Lua 콜백 오류 회귀](../evidence/shared_lua_callbacks/conformance.json)
- [새 게임 호스트 구성요소](../evidence/host_new_game_components/conformance.json)
- [GameInfo와 DB.Query 구성요소](../evidence/host_game_info/conformance.json)
- [별도 SDK 후보](../evidence/new_game_sdk/build_result.json)
- [지도 실패와 VM 정리 28개 검사](../evidence/new_game_sdk/failure_conformance.json)
- [새 게임 호출 수명·잠금 4,096개 검사](../evidence/new_game_session/conformance.json)
- [외부 DLL 예외 수명 1,034개 검사](../evidence/host_exception_boundary/conformance.json)
- [가장 최근 실제 새 게임 실행 결과 위치](../evidence/new_game/latest.json)
- [두 언어 새 게임 생성·관측·종료 검증](../evidence/new_game/conformance.json)

현재 소스에 대해 호스트 구성요소 5,434개(두 최적화 구성·8회 실행), 규칙 조회 4,730개, 호출 수명·잠금 4,096개, 외부 DLL 예외 수명 1,034개, 지도 실패 정리 28개 검사를 다시 통과했사와요. 이들은 각 부품의 검사 수이며 실제 게임 턴 수가 아니랍니다.

이 후보는 아직 정식 SDK 패치 목록·전체 검증·Stage 배포 절차에 승격되지 않았사와요. 이전 정식 구성의 320개 프로젝트 검사 통과를 현재 소스 전체의 통과로 읽으면 안 된답니다.

## 남은 관문

1. 공유 Lua 10파일 묶음과 SDK 지도 실패 패치를 정식 생성·전체 검증·Stage 절차에 반영하와요. [승격 체크리스트](M3_CANDIDATE_PROMOTION.md)에 파일별 갭을 기록했답니다.
2. SDK의 정상 업데이트 경로로 첫 턴 진입과 인간·AI 턴 처리를 연결하고, 도시·유닛 수명, 저장/불러오기, 전체 상태의 동일 시드 재현성을 검증하와요. [첫 턴 경로 조사](M3_FIRST_TURN_PATH.md)를 바탕으로 진행하와요.
3. 실제 게임 계산을 작업자에 분산하고 순차 실행과 결과를 비교한 뒤 처리 시간과 메모리를 측정하와요.
4. 활성 모드 연결, 그래픽·입력·음향, 사용자 게임 환경과 장기 실행의 통합 검증을 마치와요.
