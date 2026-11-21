# 지도 제공자의 정식 x64 SDK 통합

2026-09-26 최신 통합: attempt_025·556개 패치·SDK 수정 파일 94개·제공자 16개의 정식 연결은 미해결 0개이며, 명시적 초기화·종료와 SDK WalkStack 및 도시 AI 전략 정리·게임/지도 생성 실패 정리 수정을 반영했사와요. 아래 이전 단계의 연결 차이는 당시 구성의 기록이랍니다. 현재 비교는 지도 15→2·지도 객체 15→5·로그를 제외한 파일 2→1·로그 1→0이며, [최신 초기화 계약](M2_GAMECORE_BOOTSTRAP.md)을 기준으로 검토하와요.

2026-09-26 / `WORLD_BUILDER_MAP_SDK_INTEGRATION_PASS_NOT_GAME_RUNTIME`이랍니다. 정식 attempt_021의 GameCore 161개 오브젝트로 지도 제공자 제외/포함의 17→4 비교를 재검증했사와요. Windows 파일·로그 서비스를 포함한 제공자 15개의 정식 연결은 미해결 디버그 항목 2개랍니다. [파일 서비스](M2_FILESYSTEM_PROVIDER.md)·[로그 서비스](M2_LOGGING_PROVIDER.md)의 native 시험을 통과했으며 DLL 생성·초기화·실게임 실행은 아직 미완료랍니다.

## 요구사항과 결과

| ID | 요구사항 | 확인한 증거 |
|---|---|---|
| WB08-F1 | 기존 SDK 변경과 저장 계약 보존 | attempt_019의 488개 패치 내용 유지, 지도 접근 선언 7개와 후속 로그 호출부 48개 추가 |
| WB08-F2 | 지도와 GameCore의 클래스 선언 일치 | 543개 패치·89개 수정 SDK 파일, 지도 시험용 헤더가 정식 SDK 입력과 바이트 단위 일치 |
| WB08-F3 | 전체 GameCore 재컴파일 | C++ 161개 모두 AMD64 오브젝트 생성, 포인터·기존 숫자 변환 경고 관문 통과 |
| WB08-F4 | 실제 제품 제공자 연결 | 15개 제공자와 정식 연결, 남은 심볼 2개, 시험용 파일 시스템 바인딩 제외 |
| WB08-F5 | 영향 부품과 지도 회귀 검증 | 관련 부품 갱신 22단계, 지도 형식·객체·파일 연결 검증 재실행 |
| WB08-N1 | 전체 게임과 부품 증거 분리 | DLL 미생성·GameCore 미로드·게임 미실행·게임 멀티코어 미검증 명시 |

원본 SDK·설치 게임·지도·MODS·저장·Mod ID·버전·저장 키·스키마·밸런스는 변경하지 않았사와요. 작업 대상은 독립 프로젝트의 이식 SDK와 제공자·검증·별도 Stage랍니다. 새로운 파일 형식이나 마이그레이션을 추가하지 않았사와요.

## 무엇을 통합했는가

`CvWorldBuilderMap.h`, `CvWorldBuilderMapElementAllocator.h`, `CvWorldBuilderMapTypeGroup.h`, `FString.h`에 접근 선언을 반영했사와요. 풀·핸들용 2개와 지도 상태 교체용 5개이며 필드·가상 함수·공개 함수 서명·메모리 배치를 바꾸지 않사와요.

같은 클래스 시작점에 둘 이상의 접근 선언이 들어가는 경우를 위해 생성 도구가 해당 클래스의 연속된 friend 선언을 확인하도록 했사와요. 이미 적용된 선언을 중복 삽입하지 않으며, 실제 생성 헤더가 정식 SDK 헤더와 같은 해시인지 검증하와요.

데이터베이스·할당기·수치 경계·스트림·직렬화·기반 서비스·임시 메모리·자동 기록·Lua 연결·문자열·현지화·지도 형식·지도 부가 데이터의 영향 경로를 새 기준으로 갱신했사와요. 이전 패치 내용 비교와 새 접근 선언의 정확한 레시피 확인을 모두 유지했답니다.

실제 `WorldBuilderMapBridge` 제공자를 정식 연결 도구에 등록했사와요. GameCore와 지도 제공자의 패치/입력 목록, 형식·부가 데이터·문자열·기반 서비스 의존 관계가 정확히 같아야 연결하도록 하와요. 후속 파일·로그 서비스 통합 후 미해결 항목은 다음 두 개랍니다.

| 서비스 | 남은 진입점 |
|---|---|
| 디버그 | `FDebugHelper::GetInstance`, `FDebugHelper::LoadSymbols` |

정식 연결 응답에서 지도·파일 시스템·로그 제공자를 제외하면 17개, 객체 구현만 추가하면 7개, 전체 지도 제공자를 추가하면 4개가 된다는 비교도 같은 attempt_021 오브젝트로 재실행했사와요. 이 비교 도구는 정식 연결 보고서를 덮어쓰지 않사와요.

## 검증 범위

- 지도 형식 구성요소: 130개 입력, 원본 파일과의 바이트 왕복 127개·명시적 빈 슬롯 복구 3개, 실패·경계 검사 13,639회랍니다.
- 지도 객체: 원본 상태 기록 25개·66,867바이트 일치, 실패·경계 검사 131,322회랍니다.
- 지도 파일과 객체 연결: 원본 관측 상태 129개 일치·버전 9 시야 수정 1개, 출력 130개의 원본 SDK 재읽기 일치, 실패·경계 검사 16,669회랍니다.
- 버전 9 수정은 원본이 잘못 읽은 메모리를 재현하지 않고 파일의 시야 비트를 읽는 보완이랍니다. 세부 원본 명령과 반복 실행 증거는 [파일 연결 기록](M2_WORLD_BUILDER_MAP_BRIDGE.md)에 있사와요.
- 전체 GameCore의 기존 `/W3` 경고 위치는 343곳(인코딩 325·선언 5·구형 API 13)이랍니다. 새 지도 제공자·후보 시험 프로그램은 `/W4 /WX` 경고 없이 빌드했사와요. 전체 GameCore를 경고 0개라고 표시하지 않사와요.

전체 SDK 통합 검증은 `evidence/world_builder/map_bridge/sdk_integration.json`, 실제 컴파일·연결은 `evidence/sdk_x64/{build_result,link_analysis}.json`에 있사와요. 이 보고서들은 GameCore 실행의 증거가 아니랍니다.

## 다음 작업과 남은 수용 관문

1. 로그 서비스와 호출부 통합을 마쳤으며, 디버그 도우미의 실제 기능과 DLL 초기화 경계를 구현해야 하와요.
2. 후속 Windows 파일 서비스에서 임시 파일·쓰기/닫기/교체 실패 보존을 실제 지도 API로 검증했사와요. 전원 차단 복구·자산 카탈로그·메타데이터 보존은 남은 파일/호스트 관문이랍니다.
3. x64 실행부가 실제 게임 상태를 소유하고 초기화·새 게임·턴을 진행하도록 만들어야 하와요. 이어서 원본 결과·난수·모드·저장 호환성, 실제 게임 병렬 계산과 성능을 검증해야 하와요.
4. 실게임 비교 실행은 별도 허용 뒤 진행하며, 현재 부품 시험이나 파일 해시를 실게임 통과로 계산하지 않사와요.

## 재현 경로

```powershell
python tools/define_world_builder_map_patches.py
python tools/build_sdk_x64.py --vs "C:\Program Files\Microsoft Visual Studio\2022\Community"
python tools/refresh_world_builder_dependencies.py
python tools/build_world_builder_map_wire.py
python tools/verify_world_builder_map_wire.py
python tools/build_world_builder_map_object.py
python tools/verify_world_builder_map_object.py
python tools/build_world_builder_map_bridge.py
python tools/verify_world_builder_map_bridge.py
```

정식 연결은 `tools/analyze_sdk_x64.py`에 파일·로그·지도 제공자를 포함한 현재 제공자 15개를 함께 전달하와요. 정확한 현재 입력·라이브러리·응답 파일은 `evidence/sdk_x64/link_analysis.json`의 `providers`와 `link_response`에 있사와요. 이어서 두 지도 연결 비교, `verify_world_builder_map_integration.py`, 관련 Stage 도구와 `verify_project.py`를 실행하와요.
