# M3 후보 승격 체크리스트

이 문서는 격리된 공유 Lua·새 게임 후보를 정식 Source → Build → Stage 흐름으로 승격하기 위한 작업 순서랍니다. 현재 `Stage/NativeHost`의 9개 파일 V3 묶음과 정적 Lua 링크는 과거 기준선이며, 공유 Lua 후보의 승격 완료를 뜻하지 않사와요. 공유 Lua 회귀 검사와 GameCore 후보 링크는 별도 후보 증거이며, 첫 턴·멀티코어 실행은 아직 검증되지 않았답니다.

기존 실행기의 닫힌 내부 순서를 복제하거나 동등성을 입증하는 일이 승격의 선결 조건은 아니랍니다. 새 호스트가 공개 SDK 계약에 맞춰 호출 순서를 정의하고 격리 실행으로 검증하되, 원본 실행기 동등성은 별도 미검증 항목으로 남기면 된답니다.

## 순서대로 진행할 작업

1. **후보의 완료 상태를 갱신하와요.** 다음 격리 새 게임 실행의 request, 빌드 입력, 복사된 bundle, stdout/stderr, 관측값과 SHA-256을 하나의 실행 ID에 묶고, 그 실행에서 검증한 범위를 정확히 기록하와요. `tools/run_new_game_probe.py:11-28,51-83,93-122`는 이미 shared Lua 후보를 별도 실행부로 만들고 증거를 기록하지만, 보고 상태는 accepted host와 턴 검증을 분리해야 한답니다.

2. **공유 Lua를 정식 Build 입력으로 편입하와요.** `Source/SharedLua/ldo.c`의 native callback guard와 `Source/SharedLua/ZeroSisLuaCallback.cpp`를 소스 기준으로 고정하고, `tools/build_shared_lua_runtime.py:18-26,49-85`의 임시 링크 치환을 재현 가능한 공식 build target으로 편입하와요. GameCore와 Host의 모든 VM API 호출이 같은 `ZeroSisLua51_x64.dll`에 연결되는지 import table, map, linker response 및 source manifest로 검증하와요. 기존 정적 Lua archive는 구성요소·비교 시험용으로 보존하고, 공유 DLL 및 import library를 별도 provider 산출물로 관리하면 된답니다.

3. **Host의 정식 링크와 런타임 의존성을 바꾸와요.** `tools/build_native_host.py:46-55`와 `tools/host_new_game_components.py:20-29`는 현재 정적 Lua library를 연결하므로 shared import library, `LUA_BUILD_AS_DLL` 및 `ZEROSIS_SHARED_LUA_RUNTIME` 정의를 쓰는 정식 Host/test Build 경로를 추가해야 한답니다. 실행 파일 import에 shared DLL이 있고, DLL 안에 단일 Lua VM 구현이 있으며, GameCore와 Host 양쪽에 private Lua 구현이 남지 않는지 검증하와요.

4. **V4 번들의 구성과 검증기를 함께 전환하와요.** `Source/Host/HostFiles.h:10-15,87-90`에는 V3/9개와 shared V4/10개 분기가 이미 있사와요. 그러나 `tools/prepare_native_host_bundle.py:21-24,47-55`는 9개 V3만 만들고, `tools/verify_native_host.py:84,122-131` 및 `tools/verify_project.py:1133`도 V3/9개 기준이랍니다. 정식 builder와 parser는 shared Lua DLL을 포함한 10개 V4 파일 및 각 해시·아키텍처를 확인하고, V4 수락과 V3·파일 누락·중복·잘못된 경로·Lua DLL 해시 변조 거부를 회귀 검사해야 한답니다.

5. **공유 Lua 회귀를 정식 검증 계약에 연결하와요.** `tools/verify_shared_lua_callbacks.py:11-34`는 O2/Od 두 구성에서 실제 shared Lua callback 경계를 검사하며, 현재 70개 native checks의 범위는 callback 예외 변환·복구이고 GameCore 미로드랍니다. `tools/verify_shared_lua_boundary.py`의 static/shared 교차 VM 시험도 이와 분리해 유지하와요. 두 증거를 Build manifest에 묶고, `tools/verify_project.py`에서 소스·빌드 입력·DLL import·검증 결과 해시를 확인하되 이를 새 게임 통과로 확대하면 안 된답니다.

6. **예외 경계와 인터페이스 계수를 동기화하와요.** `tools/stage_host_exception_boundary.py:29-30`은 candidate 22를 기록하지만, 현재 `tools/verify_host_exception_boundary.py:10,48-53`는 candidate 26 및 native checks 1,034를 기록하와요. `tools/verify_project.py:1161-64`의 기대값 22/874는 오래된 기준이므로 현재 증거 생성기·Stage·검증기가 같은 실측 결과를 소비하게 맞추어야 한답니다. 이는 알려진 파이프라인 불일치이지 이후 전체 검사 합계의 약속은 아니와요. `native_host_evidence.py:45-51`의 override 기반 계수와 `verify_project.py:1128-29`의 고정 service slot 기대치도 Host 서비스 변경 후 실측에 맞춰 동기화하와요.

7. **새 게임 런타임 증거를 별도 Stage review로 승격하와요.** `tools/stage_native_host.py:15-23,32-43`은 기존 Host·GameInfo·예외 경계 자료를 담지만 공유 Lua·새 게임 후보 파일은 담지 않사와요. `tools/stage_host_runtime.py:9-30`도 초기화 전용 런타임 review이며 새 게임·턴·멀티코어 값을 false로 기록한답니다. 따라서 새 게임 candidate 검증기·실행기·설정·SDK 후보 입력·Lua callback/지도 회귀·실행 request와 결과를 SHA-256과 함께 별도 Stage review에 복사하고, 현재 검증된 단계 및 남은 단계를 명시하와요.

8. **마지막에 승격 manifest와 전체 검증을 갱신하와요.** Source 파일 → Build 응답/입력·DLL·import/map → Stage V4 번들·review manifest가 같은 파일 해시와 provider 구성을 가리키게 만든 뒤 `tools/verify_project.py`에 새 경로, 카운트, 상태 및 범위 검사를 연결하와요. 실제 첫 턴이 통과하기 전에는 turn 검증으로 표기하지 않고, 게임 계산 멀티코어는 별도 관문으로 유지해야 한답니다.

## 현재 증거의 해석

정식 승격은 새 Build와 Stage 묶음의 재현성·해시 검증을 요구한답니다. 현 V3/9개 정적 Stage는 역사적 baseline이고, shared Lua runtime/callback 및 새 게임은 각각 후보/격리 실행 증거랍니다. 실제 새 게임 성공, 턴 진행 완료 및 멀티코어 검증 여부는 해당 실행 결과로 따로 판정해야 하와요.
