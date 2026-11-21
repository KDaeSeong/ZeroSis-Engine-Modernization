# SDK 동적 열거형의 DB·Lua 오류 경계

현재 상태: 독립 실행 5,808개 검사와 정식 GameCore 161개 파일의 x64 컴파일을 통과했사와요. attempt_033의 정식 연결도 미해결 0개로 통과했답니다. 검토용 산출물은 별도 Stage에 두며 실제 게임 라이브러리 등록은 미검증이랍니다.

후속 [나머지 여섯 등록 경로](M3_LUA_REGISTRATION.md)의 오류 전달을 추가하면서 이 열거형 시험도 같은 현재 SDK와 제공자에 맞추어 다시 실행하와요. 아래 603개 패치와 attempt_033은 열거형 단계 당시 기록이며 현재 전체 상태는 프로젝트 README를 기준으로 하와요.

요구사항은 정상 이름↔ID 대응·입력 행 순서·개수·기존 Lua 표의 동일성을 보존하면서, DB 실패를 전달하고 Lua 오류가 C++ 소유 자원의 정리를 건너뛰지 않게 하는 것이랍니다. 원본 DB·모드 ID·버전·저장 키·스키마·밸런스는 변경하지 않사와요.

영향 범위는 SDK `CvLuaEnums::RegisterDynamicEnums`, 실패 반환을 검사하지 않던 `CvLuaEnums::Register`, 새 `ZeroSisLuaEnums.h`이랍니다. 원본은 attempt_032의 600개 패치와 설치 SDK 사본으로 고정하고 별도 프로젝트에서만 수정하와요.

DB 행·개수 조회와 문자열 복사는 Lua 표를 변경하기 전에 끝내고, Lua 쓰기는 소유 자원이 없는 콜백에서 보호 호출로 수행하와요. DB 오류는 표를 변경하기 전에 실패하며, Lua 쓰기 도중 오류가 나면 표가 일부 변경될 수 있으므로 상위 스크립트 서비스가 초기화 중인 VM을 폐기해야 하와요. 표 자체의 원자적 교체나 전체 게임 상태의 복구를 주장하지 않사와요.

독립 수용 기준은 SQL 준비·반복·개수 실패 전달, 정상 표의 원본 및 별도 SQLite 기준 대조, Lua/C++ 할당 실패 시 조회·메모리·스택 정리와 재시도, 실제 FLua 보호 함수에서 상위 등록 실패 전달이랍니다. 시험 실행 파일의 가져오기를 검사하여 GameCore가 포함되지 않는 것을 확인한 뒤 실행했사와요.

## 재현 결과와 가설 정정

최초의 ‘C Lua의 longjmp 때문에 원본 DB 결과 객체의 정리가 건너뛰어질 수 있다’라는 위험 가설은 현재 Windows x64 구성에서 성립하지 않았사와요. 실제 원본 함수·DB·Lua를 연결한 `/EHsc /O2`와 `/EHsc /Od` 각각에서 Lua 할당 실패 56곳을 주입했으나, 조회 수가 원래 값으로 복원되고 재시도도 성공했답니다. NULL 이름에서 발생한 Lua 오류 역시 조회를 남기지 않았사와요. 따라서 이를 재현된 원본 누수나 수정 완료한 누수로 보고하지 않사와요.

이는 Microsoft가 문서화한 [x64 setjmp/longjmp의 스택 해제 동작](https://learn.microsoft.com/en-us/cpp/build/x64-calling-convention?view=msvc-170#setjmplongjmp)과 일치하와요. 다른 플랫폼·최적화·noexcept 함수까지 일반화하지 않으며, [예외 처리 옵션에 따른 제한](https://learn.microsoft.com/en-us/cpp/cpp/using-setjmp-longjmp?view=msvc-170)도 구분하와요. 새 구현은 이러한 구현별 차이에 의존하지 않도록 Lua 쓰기를 보호 호출 안에 두었답니다.

실제로 재현한 결함은 없는 테이블·없는 열·행 반복 중 SQLite 정수 넘침·개수 조회 실패를 원본이 정상 반환하는 네 경로와, `CvLuaEnums::Register`가 FLua 실패 반환을 무시하는 경로이랍니다. 수정본은 DB 오류 때 기존 Lua 표를 보존하고, 상위 등록 실패를 C++ 예외로 전달해 실행부가 초기화 중인 VM을 폐기할 수 있게 하와요.

## 실행 검증

| 검증 | 결과 |
|---|---|
| 실제 DB·Lua·FLua 연결, 원본/수정본 × `/O2`·`/Od` | 4개 실행 파일, 경고 0개, 28개 프로세스, 5,808개 검사 |
| 보유 BNW 규칙 DB | 임무 58행의 이름↔ID·개수와 Python SQLite 기준 일치 |
| 정상 경계 | 빈 표, 개수 키 생략, 중복 이름·ID, 음수·최대/최소 ID, 한글·빈 이름, 기존 키·표 동일성, 반복 등록 |
| 수정본의 할당 실패 | 최적화 구성마다 Lua 57곳·C++ 51곳; 조회·힙·스택 정리와 재시도 성공 |
| DB 실패 | 구성마다 4종; 표 변경 전에 실패 전달, 조회 해제와 정상 재시도 |
| 상위 등록 함수 | 실제 FLua 보호 호출의 SQL/Lua 실패 전달, 잠금·스택 복원과 재시도 |
| 입력 경계 | 잘못된 인수 8종·닫힌 DB 거부, 300자 이상 식별자 처리 |

시험의 `GC.GetGameDatabase()`와 `pRegister` 진입부는 작은 계측용 대체물이랍니다. `RegisterDynamicEnums`와 `Register`는 정확한 SDK 함수 본문이며 DB·Lua·FLua는 실제 제공자랍니다. 전체 정적 열거형, 나머지 게임 라이브러리, 게임 객체의 finalizer, 실제 GameCore 로딩·지도 생성·턴·멀티코어는 이 결과로 검증됐다고 표시하지 않사와요.

## 재현과 배포 범위

정식 SDK 생성은 `define_lua_enum_patches.py --apply`와 `build_sdk_x64.py`를 사용하와요. `build_lua_enums.py --production`은 실제 생성된 SDK 본문이 시험 후보와 같은지 먼저 확인하고, `verify_lua_enums.py`가 DB·Lua·FLua 실행 및 별도 SQLite 기준 비교를 수행하와요. `lua_enums_evidence.py`는 원본 600개 패치 보존과 새 3개 패치, 실제 SDK·시험의 동일 헤더 소비를 대조하와요.

연결 의존 기록은 `refresh_lua_enum_integration.py --phase build`, 검토용 묶음은 `--phase stage`로 갱신하와요. 이 절차는 GameCore DLL을 연결·검사하며 실제로 불러오지 않사와요. 설치된 SDK·게임 실행 파일·MODS·저장 파일은 변경하지 않으며, 결과는 이 프로젝트의 `Stage/LuaEnums`, `Stage/GameCore_x64`, `Stage/NativeHost`에만 반영하와요.
