# 실행부 오류 객체와 DLL 해제 순서

2026-09-27 / 정식 x64 실행부의 초기화·종료 실패 경계를 보완하와요. GameCore SDK·공개 ICv 슬롯·게임 규칙·저장 형식·Mod ID·버전은 변경하지 않으며, 별도 프로젝트의 실행부만 대상이랍니다. 실제 GameCore 로딩은 수행하지 않았사와요.

## 결함과 요구사항

수정 전 Session::Initialize는 DLL에서 받은 예외를 `exception_ptr`로 보관하고, 예외 처리 블록 안에서 Cleanup을 호출했사와요. Cleanup이 FreeLibrary를 완료하면 아직 살아 있는 예외의 형식 정보·가상 함수·소멸자 코드가 사라질 수 있답니다. Shutdown의 저장된 정리 오류와 외부 호출자가 붙잡은 예외에도 같은 문제가 있었사와요.

Microsoft 문서에서도 DLL 참조 수가 0이 되면 모듈이 주소 공간에서 해제된다고 명시하와요. 이번 결함 여부는 그 일반 설명만으로 확정하지 않고 실제 별도 DLL로 재현했답니다. [FreeLibrary 계약](https://learn.microsoft.com/en-us/windows/win32/api/libloaderapi/nf-libloaderapi-freelibrary) · [C++ exception_ptr와 예외 보관](https://learn.microsoft.com/en-us/cpp/cpp/transporting-exceptions-between-threads?view=msvc-170)

| ID | 수용 기준 |
|---|---|
| HE01 | DLL 예외의 메시지를 DLL이 살아 있을 때 실행부 소유 값으로 복사하고, 원래 예외 처리 블록이 끝난 뒤 DLL 해제 가능 정리 수행 |
| HE02 | 초기화 실패 원인을 보존하고, 정리도 실패하면 원인과 정리 오류를 별도로 유지 |
| HE03 | 종료 실패 뒤 실행부 오류를 외부에서 보관한 상태로 종료를 재시도해도 DLL 예외 객체가 남지 않음 |
| HE04 | 표준·알 수 없는 형식·실제 InvalidNativeReference 오류, 긴 문구·null 문구에 대해 안전한 기록 유지 |
| HE05 | 정리 완료 뒤 잠금·실행 깊이·어댑터를 반납하고 같은 세션의 정상 초기화·종료 재실행 |
| HE06 | 원본/수정본의 정확한 Session 본문, 실제 시험 DLL 해제, /O2·/Od 결과, Source → Build → Stage를 추적 |

## 구현 계약

`HostFailure.h`의 ErrorSnapshot은 메시지 바이트 1,023개와 종료 문자, 원인 분류·잘림 여부를 보관하와요. 표준 예외의 what()을 원래 예외가 살아 있을 때 읽으며, 알 수 없는 예외와 null 메시지는 명시적 대체 문구로 기록하와요. 복사 과정은 고정 저장 공간을 사용하고 DLL 문자열 포인터·exception_ptr를 보관하지 않사와요. 런타임 자체의 예외 전달에 필요한 메모리까지 무할당이라고 주장하지는 않사와요.

Session은 catch 블록을 완전히 벗어난 다음 정리를 실행하와요. 상위 호출자에게 전달하는 HostOperationError는 실행부 코드와 ErrorSnapshot만 사용하므로 호출자가 오류를 보관한 채 DLL을 해제·재적재할 수 있답니다. 초기화의 원인과 CleanupPending의 정리 오류는 분리해 유지하와요.

새 실행부 내부 API인 `Session::CleanupError()`는 exception_ptr 대신 복사 가능한 ErrorSnapshot을 반환하와요. bool 검사 사용처는 유지하며, Present·Origin·Truncated·Message로 내용을 읽을 수 있답니다. 반환한 복사본은 이후 정리 성공으로 세션의 기록이 지워져도 유지하와요. 호출 시에는 기존처럼 수명 변경이 진행되지 않는 상태여야 하와요. 기존 SDK나 모드에 공개된 API의 변경은 아니랍니다.

## 실제 독립 실행 결과

원본 Session은 직전 정식 실행부가 소비했던 본문과 해시가 같은 사본으로 고정했사와요. 테스트는 실제 Windows DLL 로딩·해제를 사용하지만 GameCore 문맥과 게임 서비스는 계측 대체물이랍니다. 시험 DLL은 GameCore 오브젝트를 포함하지 않으며, 실제 통합된 NativeReference의 오류 형식도 별도로 실행하와요.

| 시험 | 관측 결과 |
|---|---|
| 원본 초기화 실패: 표준·알 수 없는 형식·NativeReference 오류 | 두 최적화 구성 모두 DLL 해제 후 접근 위반 |
| 원본 종료 실패와 외부 예외 보관, 초기화/정리 연속 실패 | 같은 접근 위반 재현 |
| 원본 합계 | 7개 사례 × /O2·/Od, 14개 프로세스 모두 0xC0000005 |
| 수정본 합계 | 11개 사례 × /O2·/Od, 22개 프로세스·874개 검사 통과 |
| 수정본 해제 순서 | FreeLibrary 전 추적한 외부 예외 0개, 생성/소멸 수 일치, 실제 모듈 해제 확인 |
| 오류 기록 | DLL 해제 뒤 외부 보관 오류를 다시 읽고, 알 수 없는 형식·null·긴 메시지와 잘림 상태 확인 |
| 실패 복구 | 정리 재시도와 기록 복사본 보존, 같은 세션의 정상 재시작·종료 확인 |

`evidence/host_exception_boundary/conformance.json`이 현재 실행 근거랍니다. 초기 탐색의 original_reproduction/original_build 기록은 이력이며, 현재 판정은 모든 입력 해시를 확인한 build_result와 conformance를 사용하와요. 실제 GameCore의 객체 소유자·이벤트·턴·저장·멀티코어는 이 시험 범위에 포함하지 않사와요.

## 재현과 배포 범위

```text
python tools/build_host_exception_boundary.py
python tools/verify_host_exception_boundary.py
python tools/host_exception_boundary_evidence.py
```

전체 검토 갱신 절차에는 이 세 단계와 전용 Stage 생성을 정식 실행부 빌드 전에 포함하와요. 이미 끝난 단계에서 재개할 때는 프로세스 종료·선행 도구 해시를 확인하와요. 검토용 파일은 `Stage/HostExceptionBoundary`, 실행부와 연결 기록은 `Stage/NativeHost`에 보관하와요. 정식 실행부가 수정 헤더를 소비한 빌드와 기존 검사 20,948개·24개 프로세스, Source → Build → Stage 갱신을 완료했사와요. 후속 Lua 접근 제어 통합에서도 이번 874개 검사를 다시 통과했답니다. 실제 GameCore 로딩·게임 객체 실행은 여전히 별도 관문이와요.
