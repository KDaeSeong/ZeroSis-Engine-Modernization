# 지도·게임 스크립트의 GameInfo 규칙 조회

실제 x64 GameCore 초기화에서 없었던 `GameInfo`를 별도 실행부의 전용 규칙 DB에 연결했사와요. 영향 범위는 실행부의 Lua 서비스·규칙 조회·검증 도구이며, GameCore SDK 패치·모드 ID·밸런스·저장 형식·설치된 게임은 변경하지 않사와요. 검토 묶음은 `Stage/NativeHost/Review`에 두고 실제 초기화 시험은 매번 새 복사본에서 수행하와요.

## 요구사항과 구현

| ID | 요구사항 | 구현 |
|---|---|---|
| GI01 | 기존 스크립트의 ID·Type 조회 | `GameInfo.Terrains.TERRAIN_GRASS`, `GameInfo.Units[0]`; 없는 행은 nil |
| GI02 | 전체 순회와 조건 조회 | `GameInfo.Features()`, `GameInfo.Features{NaturalWonder=true}`, 단일 SQL 조건식 |
| GI03 | 값 의미 보존 | boolean→Lua boolean, 정수/실수→number, 길이를 보존한 UTF-8 text→string, SQL NULL→nil |
| GI04 | 독립된 순회 수명 | 한 질의의 결과를 복사한 뒤 DB 문장을 해제; 중첩·교차 순회와 행 수정이 다른 조회에 영향 없음 |
| GI05 | 실패 시 복구 | DB·C++ 할당 오류는 Lua 오류로 전달하고 Lua 할당 실패는 보호 호출 안에서 처리 |
| GI06 | 현재 실제 규칙과 대조 | 실제 GameCore VM에서 12개 표 순회와 표본 필터·ID 조회; 전용 실행 DB의 독립 SQL과 대조 |

자료형을 단순히 숫자로 통일하지 않사와요. Lua에서 숫자 0도 참이므로, `Eras.NoGoodies`나 `Features.NaturalWonder`의 false를 정확히 전달해야 지도 규칙이 유지된답니다. SDK DB 제공자의 boolean 판별을 사용하며 현재 규칙 DB의 해당 열은 `boolean` 선언이랍니다.

`GameInfoDatabase.h`는 `ScriptRules` 계약을 구현하고 `HostRun`이 사용하는 전용 `rules.db`를 빌리와요. `ScriptSystem`은 첫 VM 생성 전에 규칙 제공자를 연결하며, 게임 라이브러리가 연결된 VM은 기존 소유 스레드·GameCore 잠금 검사를 그대로 거칩니다. 종료 시 VM과 finalizer를 먼저 닫고 DB 연결을 닫는 순서를 유지하와요.

Lua 5.1 오류는 C++ 소멸자를 건너뛸 수 있사와요. 조회 결과를 보유한 C++ 프레임에서 Lua 행을 만드는 작업을 별도 `lua_pcall`로 보호하고, 모든 C++ 소유자가 정리된 뒤 Lua 오류를 다시 전달하와요. 초기 설치의 C++ 예외도 기존 보호 콜백으로 변환하와요.

## 검증과 근거

`Tests/sdk_host_game_info.cpp`는 실제 x64 Lua·DB 제공자와 메모리 DB를 사용하와요. ID/이름·불리언·음수·실수·NULL·UTF-8과 NUL 문자열, 조건값 바인딩, 중첩 순회, SQL 오류와 미지원 입력, DB 갱신 뒤 재조회, Lua/C++ 할당 실패 뒤 재시도, VM 설치 실패, 외부 스레드 거부와 종료 시 자원 해제를 검사하와요. 최적화 켬/끔 두 구성의 결과와 실제 실패 횟수는 `evidence/host_game_info/conformance.json`에 기록하와요.

실제 GameCore 시험은 `CoreRuntimeProbe.h`가 담당하와요. `Worlds`, `Terrains`, `Features`, `Resources`, `Improvements`, `Eras`, `Civilizations`, `Units`, `Buildings`, `MapScripts`, `Map_Sizes`, `Natural_Wonder_Placement`를 순회하고, ID와 Type이 모두 있는 행은 두 조회 경로를 대조하와요. 불리언 시대·자연경관 조건·개척자 복합 조건과 초원 ID 등의 관측값은 Python SQLite가 해당 실행의 DB에서 독립 조회한 값과 비교하와요. 영어·한국어 실행 기록은 `evidence/host_runtime/conformance.json`에 연결하와요.

```text
python tools/host_game_info_evidence.py build
python tools/host_game_info_evidence.py verify
python tools/host_game_info_evidence.py validate
python tools/build_native_host.py
python tools/prepare_native_host_bundle.py
python tools/verify_native_host.py
python tools/audit_host_script_bindings.py
python tools/native_host_evidence.py
python tools/audit_native_host_services.py
python tools/stage_native_host.py
python tools/refresh_host_runtime.py
python tools/verify_project.py
```

전체 실행부 빌드·검증도 GameInfo 검사를 포함하므로 위의 개별 세 명령은 독립 재현용이랍니다. 실행 입력이 같으면 `refresh_host_runtime.py`는 기존 실제 실행 근거를 검증하고 재사용하와요.

## 남은 범위

원본 Windows 실행부의 전체 GameInfo 동등성을 입증한 결과는 아니랍니다. 표 순회 순서는 현재 SQLite 조회 순서이며 원본과의 결정성 대조는 남아 있사와요. 현재 질의가 만든 행은 값 복사이며 이후 DB 변경은 다음 질의에 반영하와요. 원본 캐시·행 객체 동일성·변경 알림의 의미는 후속 비교 대상이랍니다.

조건은 nil·조건 표 또는 단일 SQL 식 한 개를 받으며, 원문 SQL의 미바인드 매개변수·주석·여러 문장은 거부하와요. SQL NULL 조건은 `"ColumnName IS NULL"`로 표현할 수 있사와요. 바이너리 열과 Lua에서 정확히 나타낼 수 없는 큰 정수는 명시적으로 거부하며, 임의 값을 잘라서 반환하지 않사와요. 전체 모드 API·DB.Query·UI의 Path/Locale 서비스, 새 게임 설정·실제 지도 생성·턴 진행은 별도 구현 과제랍니다.
