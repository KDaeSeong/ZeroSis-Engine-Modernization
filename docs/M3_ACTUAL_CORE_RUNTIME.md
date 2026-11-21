# 실제 x64 GameCore 초기화·Lua 실행

2026-09-27에 정식 attempt_037 DLL과 새 실행부를 별도 폴더로 복사하여 실제 초기화·SDK Lua 등록·선택된 조회·정상 종료·DLL 해제를 영어와 한국어에서 확인했사와요. 이번에는 실제 GameCore가 DB를 적재하고 게임 객체를 생성·해제했답니다. 새 게임 생성·지도 생성·턴 진행과 게임 계산의 멀티코어는 아직 수행하지 않았사와요.

## 요구사항과 실행 범위

| ID | 기준 |
|---|---|
| AR01 | 현재 빌드와 해시가 같은 실제 x64 실행부·GameCore·제공자·자료 9개 및 manifest를 새 시험 폴더에 복사 |
| AR02 | 실제 GameCore의 초기화·DB 후처리/캐시·플레이어/팀 전역 객체 생성 경로를 실행하고 초기화 완료 확인 |
| AR03 | 실제 SDK의 전체 라이브러리 등록 호출을 완료하고 플레이어/팀 ID·지도 크기·게임 턴·타입 정보를 Lua에서 읽기 |
| AR04 | 실제 GC 종료 뒤 Lua VM을 닫는 순서에서 보관한 플레이어/팀 참조의 거부, 소유 스레드·잠금, DLL 해제 확인 |
| AR05 | 영어/한국어의 게임 상태 관측 일치, SQL 독립 조회의 표본 타입 ID 일치, 새 세션 DB 무결성, 입력 파일 해시 보존 |
| AR06 | 실행 명령·현재 소스·빌드·DLL·stdout/stderr·생성 DB·검토 묶음을 연결하며 새 게임/턴/멀티코어 검증과 구분 |

사용자가 요청한 엔진 개조·계속 진행의 범위에서 별도 실행부의 개발 검증을 수행했사와요. 초기 조사 문서에 두었던 실제 DLL 로딩의 별도 허가 대기는 이번 격리된 검증에 적용하지 않사와요. 기존 Civ V 실행파일이나 사용자 저장 파일을 시험 입력으로 사용하지 않으며, 생성물은 `Build/HostRuntime/<실행 ID>/sessions/<새 ID>`에 있사와요.

실행기는 프로세스를 숨겨 시작하고 시간 제한을 두며, 자기 자식 프로세스가 제한을 넘으면 해당 프로세스만 종료하고 실패로 기록하와요. 자식에게 전달되는 오류 모드는 이 임시 실행기 프로세스에서 설정·복원하와요. 오류 모드 상속은 [Microsoft SetErrorMode 문서](https://learn.microsoft.com/en-us/windows/win32/api/errhandlingapi/nf-errhandlingapi-seterrormode)의 계약을 사용하와요.

## 실제 관측 결과

현재 근거는 `evidence/host_runtime/conformance.json`과 그 안에 지정한 두 실행 기록이랍니다. 그 이전 initialize 단독 실행과 초기 probe 실행은 이력으로 남기며 현재 산출물 검증에는 사용하지 않사와요.

| 관측 항목 | 영어·한국어 공통 결과 |
|---|---|
| 실제 초기화·정상 종료 | 종료 코드 0, 초기화와 종료 완료 표시 |
| 플레이어·팀 슬롯 | 각 64개, 실제 GetID 결과와 Lua 표의 인덱스 일치 |
| 지도 | 너비 0·높이 0·타일 0, 지도 생성 전 상태 |
| 게임 턴 | -1, 새 게임 시작 전 상태 |
| GameInfoTypes | 이름·숫자 형식을 확인한 항목 3,299개 |
| GameInfo 규칙 조회 | 12개 표의 577개 행 순회, ID·Type이 모두 있는 행의 양쪽 조회 대조 |
| GameInfo 독립 SQL 대조 | 표별 행 수, 초원 ID, 고대 시대 보너스 유적 플래그, 해당 플래그가 참인 시대 6개·자연경관 17개·개척자 복합 조건 1개 |
| SQL과 대조한 타입 | UNIT_SETTLER=0, CIVILIZATION_AMERICA=0, BUILDING_MONUMENT=28 |
| 종료 뒤 참조 | 플레이어 0·팀 0의 GetID 호출 각각 거부; 정확한 만료 인스턴스 오류 확인 |
| Lua finalizer | 전역 객체 종료 뒤 1회 실행, 게임 소유 스레드와 잠금 보유 |
| DLL 수명 | 실제 GameCore 모듈이 프로세스에서 해제된 뒤 완료 표시 |
| 입력 파일 | 원본 Stage 묶음과 복사한 실행 입력의 SHA-256 보존 |
| 새로 생긴 파일 | 각 실행에서 전용 rules.db와 Civ5SavedGameDatabase.db, 두 DB quick_check 통과 |

플레이어·팀 수치는 초기화된 슬롯 수랍니다. 모든 도시·유닛·거래·의회 객체의 수명이나 모든 Lua 게임 메서드가 실행됐다는 뜻으로 확대하지 않사와요. 타입 값의 독립 SQL 비교는 위 세 항목이며, 전체 3,299개 값의 원본 동등성을 이번 시험의 결과로 주장하지 않사와요.

## 구현과 재현

`CoreRuntimeProbe.h`는 실제 라이브러리를 연결한 VM에서 읽기 검사를 실행하고, 그 VM을 GC 종료 뒤까지 보유하와요. 마지막에 만든 userdata의 finalizer가 남은 플레이어·팀 참조를 보호 호출로 읽어 거부 결과를 기록하와요. 실행부 소유 관측 값만 남으므로 DLL 해제 뒤에도 결과를 확인할 수 있답니다.

```text
python tools/run_gamecore_initialization.py --mode check-core --language en_US
python tools/run_gamecore_initialization.py --mode check-core --language ko_KR
python tools/host_runtime_evidence.py --record <영어 실행 ID> <한국어 실행 ID>
python tools/stage_host_runtime.py
python tools/verify_project.py
```

`refresh_host_runtime.py`는 현재 빌드와 일치하는 실행 근거가 있으면 그것을 검증하고 검토 묶음만 갱신하와요. 실행 입력이 달라졌다면 두 언어의 실제 검증을 새로 수행하와요. 기존 구성요소 검사 20,948개·Lua 접근 검사 1,440개·DLL 예외 검사 874개는 독립 시험 범위 그대로 보관하며, 실제 실행 근거는 `Stage/NativeHost/RuntimeReview`에 구분하와요.

## 다음 실제 관문

초기 시험에서 없었던 `GameInfo` 전역 조회를 구현한 뒤 실제 VM에서 12개 표와 표본 조회를 검증했사와요. 현재 기록은 그 구현을 소비한 새 실행부로 갱신하며, 예전 GameInfo 부재 관측은 해당 실행 이력에만 남기와요. [규칙 조회 구현과 범위](M3_HOST_GAME_INFO.md)

다음으로 PreGame 설정·지도 스크립트 선택·지도 생성·도시/유닛 생성·첫 턴의 필수 실행부 호출을 연결해야 하와요. 원본과의 결과 비교, 실제 게임 계산의 멀티코어, 표시·입력·음향, 기존 모드와 저장·멀티플레이·장시간 회귀도 남아 있답니다. [새 게임 공개 진입점과 연결 순서](M3_NEW_GAME_CONNECTIONS.md)
