# x64 디버그 심볼 제공자와 GameCore 연결 후보

2026-09-26 / 실제 Windows DbgHelp를 사용하는 SDK 심볼 제공자를 구현하고 **독립 native 검사 1,730개**를 통과했사와요. attempt_025의 GameCore 오브젝트 161개와 제공자 16개로 정식 연결의 **미해결 0개, AMD64 GameCore DLL 생성**을 확인했사와요. 명시적 종료가 추가된 현재 디버그 제외/포함 비교는 3→0개랍니다. 이 DLL은 실행 준비가 끝난 배포물이 아니며 로드하지 않았사와요.

정식 제공자 목록은 디버그까지 16개·미해결 0개랍니다. 새 연결 후보의 근거는 `evidence/debug/link_trial.json`이고, 생성된 파일은 `Build/Debug/link_trial/after/GameCore_link_only.dll`이랍니다. [명시적 초기화·종료](M2_GAMECORE_BOOTSTRAP.md)를 정식 SDK에 반영했으며 전체 정적 초기화·소멸과 게임 실행 검증은 남아 있사와요.

## 요구사항과 확인한 동작

| ID | 요구사항 | 증거 |
|---|---|---|
| DBG01 | 실제 SDK 심볼 관리자 제공 | 원래 `FDebugHelper` 선언·24바이트 x64 배치 유지, 실제 GetInstance/LoadSymbols 연결 |
| DBG02 | 실제 Windows 심볼 정보 조회 | 시험 EXE의 로컬 PDB에서 함수 이름·모듈·소스 파일과 실제 함수 안의 행 번호 조회 |
| DBG03 | 스레드 간 DbgHelp 호출 직렬화 | 작업자 8개·심볼 조회 512개, backend 진입 중첩 0개 |
| DBG04 | 실패를 성공으로 오인하지 않음 | 오류 번호가 0인 실패 포함 19개 주입, 오류 반환·재시도·출력 초기화 |
| DBG05 | 정리 실패의 자원 소유권 보존 | SymCleanup/CloseHandle 실패 시 싱글턴과 핸들 유지, backend 교체 거부, 명시적 재시도 |
| DBG06 | 전체 GameCore 연결 요구 해소 | 같은 161개 오브젝트의 디버그 제공자 제외/포함 결과 3→0, 실제 DLL·링크 맵·내보내기 확인 |
| DBG07 | 현재 완료 범위의 구분 | 게임 DLL 미로드, DllMain 명시적 작업 이동·전체 정적 코드 검증 전, SDK WalkStack은 별도 1,081개 검사 통과; 원본 심볼 서비스 실행 비교·GetCallStack·실게임 미검증 |

새 소스는 `Source/Providers/Debug/SdkDebugHelper.h/.cpp`랍니다. 디버그 심볼 구현은 클래스 선언을 보존하와요. 후속 초기화 단계에서 기존 543개 패치를 보존하고 SDK 호출부 패치 8개를 추가했으며, 원본 SDK·게임·MODS·저장 파일은 변경하지 않았사와요. Mod ID·버전·저장 키·스키마·밸런스도 그대로랍니다.

## 초기화·조회·정리 계약

`GetInstance`는 객체만 생성하고 심볼 초기화를 수행하지 않사와요. 실제 `LoadSymbols`는 고유한 복제 프로세스 핸들을 만들고 심볼 세션을 초기화하와요. 의사 핸들인 GetCurrentProcess 값을 세션 식별자로 공유하지 않사와요. 명시된 현재 프로세스 모듈의 전체 경로·기준 주소·이미지 크기를 조회하여 SymLoadModuleExW와 SymGetModuleInfoW64로 확인하와요.

모듈이 이미 등록되어 0과 ERROR_SUCCESS를 반환하는 경우는 주소·크기가 같은 모듈 정보까지 조회해야 성공으로 처리하와요. 첫 모듈 등록을 생략한 실패가 같은 0을 반환하면 거부하와요. 이름·소스 파일은 UTF-8로 복사하며 부족한 출력 버퍼는 잘라 쓰지 않고 실패를 반환하와요. 실패한 이름 조회는 빈 문자열, 실패한 소스 행 조회는 빈 문자열과 0을 남기와요.

현재 구현의 조회·등록·해제·상태 조회는 한 재귀 잠금으로 보호하와요. DbgHelp와 옵션은 프로세스 안에서 다른 사용자와도 조정해야 하므로, 새 호스트는 심볼 서비스 소유자를 하나로 두어야 하와요. 각 모듈에 별도 사본을 만들어 동시에 직접 DbgHelp를 호출하는 구성은 아직 지원하지 않사와요. Microsoft는 [DbgHelp 함수의 동시 호출을 직렬화하고 고유한 핸들로 세션을 식별할 것](https://learn.microsoft.com/en-us/windows/win32/api/dbghelp/nf-dbghelp-syminitialize)을 요구하와요.

소비자가 모두 종료된 경계에서 `ZeroSisDebug::Shutdown`을 호출하와요. 정리에 실패하면 해당 자원을 가진 객체를 유지하여 재시도할 수 있으며, 성공 후에만 backend 교체를 허용하와요. 자동 종료 함수에서 심볼 정리를 실행하지 않사와요. 모듈 목록 전체 등록은 도중 실패하면 이미 등록된 모듈을 유지하므로, 호출부는 실패 결과와 상태를 확인하고 다시 시도해야 하와요.

## 원본 조사와 남은 초기화 결함

기존 x86 참조 DLL의 `FDebugHelper` 진입점은 읽기 전용으로 역어셈블했사와요. `evidence/debug/reference/entrypoint_disassembly.json`이 입력 DLL·도구·범위·결과 해시를 보존하와요. 원본 생성자가 LoadLibraryA·SymSetOptions·SymInitialize를 호출하고, GameCore의 DllMain이 해당 생성자와 LoadSymbols로 진입하는 경로를 확인했사와요. 원본 심볼 서비스의 native 실행 비교는 아직 하지 않았사와요.

attempt_021까지 DllMain에 남아 있던 LoadSymbols·타이머·컨텍스트 호출은 attempt_022에서 명시적 시작/종료 경계로 옮겼사와요. CRT가 실행하는 전체 정적 생성·소멸과 실제 모듈 수명 검증은 남아 있사와요. [Microsoft DllMain 문서](https://learn.microsoft.com/en-us/windows/win32/dlls/dllmain)는 로더 잠금 안에서 복잡한 초기화를 수행하는 대신, DllMain 종료 뒤 명시적 초기화 함수를 호출하도록 안내하와요. 컨텍스트 중복 생성과 부분 생성 실패도 별도 경계 시험으로 수정했으며 자세한 결과는 [초기화 기록](M2_GAMECORE_BOOTSTRAP.md)에 있사와요.

기존 SDK `WalkStack`의 x64 null context 전달은 attempt_023에서 문맥 복사본과 공유 잠금으로 수정했사와요. [실제 SDK 템플릿·native 스택 257개·1,081개 검사](M2_DEBUG_STACK.md)를 별도로 확인했사와요. [StackWalk64 문서](https://learn.microsoft.com/en-us/windows/win32/api/dbghelp/nf-dbghelp-stackwalk64)는 x64에서 유효한 context를 요구하므로, 새 템플릿은 이 계약을 따르며 콜백 밖 수집 잠금·반복/깊이 제한·활성 세션 보호를 적용하와요. `GetCallStack`·`FCallStack::toString`·디버거 대기·미니덤프 경로도 현재 심볼 제공자의 완료 범위에 포함하지 않사와요.

## 재현과 다음 관문

```powershell
python tools/build_debug_provider.py
python tools/verify_debug_provider.py
python tools/verify_debug_stack.py
python tools/debug_stack_evidence.py
python tools/probe_debug_link.py
python tools/debug_evidence.py
python tools/stage_debug_provider.py
python tools/verify_project.py
```

시험 EXE는 `/MD /W4 /WX`, 자체 PDB를 포함하여 빌드하와요. 실행 전에 AMD64와 Windows·DbgHelp·C++ 런타임 DLL 의존성을 검사하와요. GameCore 연결 후보는 실행 없이 PE 아키텍처, 실제 debug 메서드의 링크 맵, DllGetGameContext 내보내기를 확인하와요. 전체 GameCore의 기존 컴파일 경고 343곳은 그대로랍니다.

다음 수용 순서는 전체 정적 초기화·소멸 조사, GetCallStack·호출 스택 문자열·미니덤프 보완, 상태를 소유하는 x64 실행 호스트 연결이랍니다. 그 뒤 원본 규칙·난수·모드·저장 비교, 실제 게임 병렬 계산과 성능, 화면·입력·음향·장시간 실행을 검증해야 하와요.
