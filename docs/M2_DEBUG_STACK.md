# x64 SDK 호출 스택 수집

2026-09-26 / attempt_023에서 기존 **551개 SDK 패치를 그대로 보존**하고 `FDebugHelper.inl` 패치 1개를 추가했사와요. 총 552개 패치·수정 SDK 파일 93개·지원 헤더 5개·GameCore 오브젝트 161개랍니다. 실제 SDK 템플릿을 사용하는 별도 AMD64 실행 파일에서 **1,081개 검사와 257개 native 호출 스택**을 확인했사와요. GameCore 모듈은 로드하지 않았사와요.

## 요구사항·영향·호환성

기존 SDK `WalkStack`은 x64에서도 `StackWalk64`의 CONTEXT 인수를 null로 전달하며 디버그 제공자의 잠금을 거치지 않았사와요. [Microsoft StackWalk64 문서](https://learn.microsoft.com/en-us/windows/win32/api/dbghelp/nf-dbghelp-stackwalk64)는 x64 문맥을 요구하고, 전달한 문맥을 변경할 수 있으며 DbgHelp 호출을 직렬화하도록 안내하와요. 원본 템플릿을 정확히 추출한 시험에서 AMD64/null 전달을 관측했으며, 잘못된 원본 인수를 실제 Windows 함수에 전달한 충돌 시험은 수행하지 않았사와요.

수정 대상은 `Source/Providers/Debug/SdkDebugHelper.h/.cpp`와 생성 SDK의 `FirePlace/include/FireWorks/Win32/FDebugHelper.inl`이랍니다. `FDebugHelper`의 기존 메서드 서명·24바이트 객체 배치·가상 함수 목록을 보존하와요. 변경은 별도 Source→Build→Stage에 적용하며 게임 규칙·저장 키·스키마·원본 설치 파일을 변경하지 않사와요.

| ID | 요구사항 | 구현과 시험 |
|---|---|---|
| STK01 | 유효한 x64 문맥과 같은 심볼 세션 | AMD64·고유 프로세스 핸들·현재 스레드 검사, CONTEXT_CONTROL/RIP/RSP 검증 |
| STK02 | 호출자 문맥 보존 | CONTEXT 복사본을 전달하며 실제 스택·주입 backend 양쪽에서 원본 바이트 보존 |
| STK03 | 다른 DbgHelp 호출과 직렬화 | 심볼 조회와 스택 수집에 같은 잠금 사용, 작업자 8개·256개 스택에서 backend 중첩 0개 |
| STK04 | 콜백 실행 중 교착·세션 파괴 방지 | 잠금을 풀고 콜백 실행, 활성 순회가 있는 종료·backend 교체 거부, 콜백이 다른 스레드의 심볼 조회를 기다리는 시험 |
| STK05 | 손상·무한 순회 방지 | PC/스택 주소 쌍의 재방문 검사, 256개 상한, 잘못된 문맥·빈 주소·중간 실패 처리 |
| STK06 | 중단·예외와 관측 경계 | 콜백 false 즉시 중단, 콜백 예외 재전달 및 세션 보호 해제, 중간 실패까지 이미 관측한 프레임 수 기록 |
| STK07 | 실제 SDK와 원본 보존 | 정확한 원본 템플릿 경계 관측, 새 템플릿 직접 실행, 기존 패치 551개 보존·실제 SDK 161개 재컴파일 |

## 호출과 수명 계약

심볼을 먼저 등록한 현재 프로세스의 현재 스레드만 지원하와요. 호출자가 수집한 문맥과 그 문맥의 스택이 유효한 동안 호출해야 하며 다른 스레드·다른 프로세스·이미 해제된 스택에는 사용하지 않사와요. 새 내부 `ZeroSisDebug::WalkCurrentThread`는 SDK 템플릿의 위임 대상이랍니다.

각 Windows 스택 단계는 기존 심볼 잠금 안에서 실행하와요. 콜백은 잠금 밖에서 프레임 복사본을 받으며, 복사본을 바꾸어도 다음 순회 상태에 영향을 주지 않사와요. 활성 순회 수를 유지하여 콜백 중 `Shutdown`은 ERROR_BUSY로 실패하고 자원은 보존하와요. 콜백이 false를 반환하면 성공적인 소비자 중단으로 기록하며, 예외가 발생하면 보호 상태를 해제한 뒤 원래 예외를 전달하와요. 이 순회 보호가 모든 SDK 소비자의 일반 수명 보장을 대신하지는 않사와요.

`Status.lastWalkFrames/lastWalkStop`은 가장 최근에 완료된 순회의 프로세스 공용 진단값이랍니다. 스레드별 결과 저장소로 사용하지 않사와요. 심볼 조회 등은 `lastError`를 갱신할 수 있으므로 오류는 호출 경계에서 확인해야 하와요.

Windows가 FALSE와 오류 0을 반환하면 정상 끝과 읽을 수 없는 프레임을 확정해서 구분할 수 없사와요. 관측 프레임이 있으면 `BackendStopped`로 기록하고, 하나도 없으면 실패로 처리하와요. 이 결과로 전체 스택을 완전하게 수집했다고 주장하지 않사와요. 상한 도달은 `DepthLimit/ERROR_MORE_DATA`, 반복은 `RepeatedFrame/ERROR_INVALID_DATA`이며 관측된 프레임 수를 유지하와요.

## 검증과 남은 범위

- 실제 PDB가 있는 Leaf→Middle→Root 호출 순서와 4GiB보다 큰 명령 주소를 257개 스택에서 확인했사와요.
- 이 중 256개 스택은 작업자 8개로 실행하며 프레임의 심볼도 같은 서비스로 조회했사와요. backend 동시 진입과 잘못된 문맥·핸들 전달은 0개랍니다.
- backend 경계·실패 9종, 잘못된 문맥 3종, null 콜백·잘못된 세션·콜백 중단·콜백 예외·종료 거부와 교착 방지 경로를 검사했사와요.
- 기존 심볼 제공자 시험 1,730개도 같은 새 라이브러리로 다시 통과했사와요. 새 프로그램·라이브러리는 /MD /W4 /WX와 실제 SDK 헤더로 빌드하며 실행 전 DLL 의존성을 검사하와요.

`GetCallStack`, `FCallStack::toString`, 디버거 대기·미니덤프는 아직 구현 범위 밖이랍니다. 이번에는 현재 스레드 `WalkStack`과 심볼 서비스의 협조를 검증했으며 실제 GameCore 실행·전체 정적 초기화·게임 멀티코어·성능의 증거로 확대하지 않사와요. 실제 게임 상태를 소유할 x64 호스트 연결과 위 남은 디버그 경로를 이어가야 하와요.

## 재현

```powershell
python tools/define_debug_caller_patches.py
python tools/define_bootstrap_patches.py
python tools/define_logging_caller_patches.py
python tools/build_sdk_x64.py --vs "C:\Program Files\Microsoft Visual Studio\2022\Community"
python tools/build_debug_provider.py
python tools/verify_debug_provider.py
python tools/verify_debug_stack.py
python tools/debug_stack_evidence.py
```

그 뒤 영향받는 기반 제공자 기록을 갱신하고 정식 16개 제공자 연결·제외/포함 비교·Stage·전체 검증을 갱신하와요. `evidence/debug/stack`에 선언·native 실행·전체 갱신 기록을 보관하와요.
