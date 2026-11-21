# SDK 로그 제공자와 호출부 통합

2026-09-26 최신 통합: attempt_025·556개 패치·SDK 수정 파일 94개·제공자 16개의 정식 연결은 미해결 0개이며, 명시적 초기화·종료와 SDK WalkStack 및 도시 AI 전략 정리·게임/지도 생성 실패 정리 수정을 반영했사와요. 아래 이전 단계의 연결 차이는 당시 구성의 기록이랍니다. 현재 비교는 지도 15→2·지도 객체 15→5·로그를 제외한 파일 2→1·로그 1→0이며, [최신 초기화 계약](M2_GAMECORE_BOOTSTRAP.md)을 기준으로 검토하와요.

2026-09-26 / `LOGGING_NATIVE_COMPONENT_PASS`와 `LOGGING_SDK_LINK_PASS_NOT_GAME_RUNTIME`의 수용 기록이랍니다. 실제 SDK 선언에 맞춘 Windows x64 로그 제공자와 준비된 문자열을 넘기는 호출부 155개를 통합했사와요. 정식 attempt_021의 GameCore 161개 오브젝트에 제공자 15개를 연결하며, 로그 제공자의 제외/포함 비교는 미해결 심볼 3→2개랍니다. DLL 생성·로드·실게임 실행은 후속 관문이와요.

## 요구사항과 수용 증거

| ID | 요구사항 | 확인 범위 |
|---|---|---|
| LOG01 | 실제 SDK 로그 관리자와 가상 함수 구현 | `FILogFileMgr`, `FILogFile`의 실제 선언·호출 및 Windows 파일 출력 |
| LOG02 | 준비된 문자열을 서식으로 재해석하지 않음 | 38개 SDK 파일의 155개 호출에서 실제 CvString·포인터 인수와 `%s` 변환 확인 |
| LOG03 | 같은 로그의 동시 출력 보존 | 작업자 8개, 1,600개 기록의 누락·중복·혼합 없음 |
| LOG04 | 파일 실패 뒤 기존 기록 보존 | 실패 19개, 부분 쓰기 되돌리기, 오류 후 명시적 복구 |
| LOG05 | 버퍼·플래그·보관·수명 계약 | 기록 보류/배출, 비활성화, 재열기, 보관 이름 충돌, 삭제 후 기존 포인터 안전성 |
| LOG06 | 전체 SDK 패치와 제공자 일치 | 기존 495개 패치 보존, 48개 추가, 총 543개·수정 SDK 파일 89개·161개 컴파일 |
| LOG07 | 재현 가능한 개발용 패키지 | Source→Build→Stage의 현재 소스·라이브러리·실행 기록·해시 일치 |

원본 SDK·설치 게임·MODS·저장 파일은 변경하지 않았사와요. Mod ID·버전·저장 키·스키마·게임 규칙·밸런스와 SDK 클래스 배치를 보존하와요. 수정은 별도 이식 프로젝트에만 있사와요.

## 공개 API와 수명

`Source/Providers/Logging/SdkLogFile.h/.cpp`의 `ZeroSisLogging::NativeLogManager`가 실제 구현이랍니다. 호스트는 기존 디렉터리로 `Configure`하고 모듈의 바인딩에 `Bind`한 뒤 로그를 활성화해야 하와요. 기본 싱글턴은 미설정·비활성 상태이며, 호스트 초기화 연결은 아직 완료하지 않았사와요.

좁은 파일 이름은 엄격한 UTF-8, 넓은 이름은 UTF-16으로 받으며 로그 디렉터리 아래의 파일 이름만 허용하와요. 경로 이동·예약 장치명·잘못된 문자를 거부하와요. 대소문자를 구분하지 않는 같은 이름은 같은 객체를 반환하며, 처음 요청한 플래그와 제목을 유지하와요. 후속 플래그 변경은 `SetFlags`로 명시하와요.

파일별 잠금으로 한 기록 전체를 직렬화하와요. `DeleteLog`는 객체를 관리자 종료까지 보관하므로 SDK가 캐시한 포인터의 수명을 끊지 않사와요. 같은 이름의 후속 `GetLog`는 새 객체를 반환하와요. 파일 삭제는 하지 않으며, 보관 이동도 기존 목적지를 덮어쓰지 않사와요. 관리자당 생성·퇴역 객체의 합계는 4,096개로 제한하와요.

설정 변경·관리자 바인딩·종료는 소비자 호출이 모두 멈춘 경계에서만 허용하와요. 이 수명 조건을 실제 호스트에 연결하는 작업은 남아 있사와요.

## 출력과 실패 처리

기본 기록은 UTC 시간과 CRLF를 사용하며 Debug/Warning/Error의 구분을 기록하와요. 제목은 서식으로 해석하지 않사와요. 기록·제목·버퍼는 각각 1 MiB 경계를 검사하고 `%n` 및 잘못된 서식을 거부하와요. 형식 문자열의 올바른 가변 인수 개수·타입은 호출부의 계약이랍니다.

`DontFlushOnWrite`와 버퍼 크기에 따라 기록을 보류할 수 있으며, 용량 도달·플래그 변경·닫기·보관 시 배출하와요. 부분 쓰기나 플러시 실패는 쓰기 전 파일 끝으로 되돌리고 오류를 보관하와요. 명시적 닫기·열기로 회복하기 전에는 새 기록을 추가하지 않사와요. 콘솔 실패와 되돌리기 실패는 별도 상태로 노출하와요. SDK 기록 함수는 반환값이 없으므로 호스트가 `GetStatus`로 실패·보류·마지막 오류를 확인해야 하와요.

실패를 반환하면서 Windows 오류 번호를 0으로 남기는 백엔드를 시험하여, 기존 구현이 부분 기록을 성공으로 오인하는 결함을 재현했사와요. 기존 `seed\r\n` 뒤에 `abcdef`가 남은 실패 기록을 `evidence/logging/regressions/missing_error_code/before.json`에 보존했사와요. 현재 구현은 이 경우 쓰기/플러시에 `ERROR_WRITE_FAULT`, 닫기에 `ERROR_GEN_FAILURE`를 부여하며 원래 파일 내용 보존과 명시적 재시도를 통과했사와요.

준비된 SDK 문자열은 `Msg("%s", static_cast<const char*>(text))` 형태로 전달하와요. 155개 실제 호출 표현을 시험에 사용하여 `100% %s %n`이 그대로 기록되는지 확인했사와요. `CvDllDatabaseUtility::LogMsg`의 공유 static 버퍼는 지역 버퍼로 바꾸었사와요. 이 함수의 기존 1,024바이트 서식 버퍼와 긴 입력 처리 경계는 별도의 후속 항목이랍니다.

## 검증 범위와 재현

현재 native 시험은 **2,169개 검사, 실패 19개, 공유 로그 기록 1,600개, SDK 호출 155개**를 통과했사와요. 제공자와 독립 시험 실행 파일은 `/MD /W4 /WX`로 빌드하고 AMD64 및 Windows/C++ 런타임 DLL 의존성을 검사했사와요. 전체 GameCore의 기존 경고 위치 343곳은 별도 기록이랍니다.

원본 아카이브에서는 구체적인 로그 구현을 확보하지 못했으므로, 원본 비공개 출력 형식과 완전히 같다는 증거는 없사와요. 전원 차단 내구성, 지속적인 되돌리기 실패 복구, GameCore 초기화, 게임 병렬 처리·성능은 이 시험의 수용 범위 밖이와요.

```powershell
python tools/build_logging_provider.py
python tools/verify_logging_provider.py
python tools/logging_evidence.py
# analyze_sdk_x64.py: 현재 제공자 14개와 --logging-provider evidence/logging/build_result.json
python tools/probe_logging_link.py
python tools/probe_filesystem_link.py
python tools/probe_world_builder_map_link.py
python tools/probe_world_builder_map_bridge_link.py
python tools/verify_world_builder_map_integration.py
python tools/stage_logging_provider.py
# 영향 받은 파일/지도/현지화 Stage를 먼저 갱신한 뒤 실행하와요.
python tools/stage_sdk_x64_port.py
python tools/verify_project.py
```

검토 묶음은 `Stage/Logging`과 `Stage/GameCore_x64/Providers/Logging`이랍니다. 연결 후 남는 항목은 `FDebugHelper::GetInstance`와 `FDebugHelper::LoadSymbols`이며, 디버그 구현과 DLL 초기화 경계를 다음으로 다루어야 하와요.
