# 조사·독립 구현·기준 빌드 재현과 한계

## 현재 차용 객체 수명 통합 재현

2026-09-27 현재 패치 생성기는 `define_lua_borrowed_patches.py`이랍니다. 고정된 attempt_036의 629개 패치를 보존하고 차용 참조·수명·거래 자기 대입 수정 64개를 추가하여 693개를 재현하와요. 지원 헤더는 `Source/Porting`의 기존 10개와 `Source/LuaBorrowed/ZeroSisLuaBorrowed.h`이며, 기존 게임 저장 형식은 바꾸지 않사와요.

```text
python tools/define_lua_borrowed_patches.py --apply
python tools/build_sdk_x64.py --vs "C:\Program Files\Microsoft Visual Studio\2022\Community"
python tools/build_lua_borrowed_sdk_candidate.py
python tools/refresh_lua_borrowed_integration.py --phase build
python tools/refresh_lua_borrowed_integration.py --phase stage
```

별도 SDK 후보 컴파일은 소멸자 추적 주소를 대조하는 실제 PCH 클래스 배치 증거도 생성하와요. 이미 같은 입력으로 완료한 경우 그 입력 해시를 검증한 기록을 재사용할 수 있답니다. 정식 통합 갱신 기록은 `evidence/lua_borrowed/integration_refresh`이며, 정식 SDK 본문을 실행한 참조 시험은 `production_verification.json`으로 추적하와요. 예전 `candidate_verification.json`과 후보 DLL 연결 기록은 통합 전 이력이므로 현재 판정에 사용하지 않사와요.

각 프로세스가 실제 종료하고 성공한 뒤 다음 명령을 실행하며, 관측 중단만으로 재시작하지 않사와요. 실패한 갱신은 종료를 확인하고 원인을 수정한 뒤 `--from-step`으로 재개하와요. 현재 `--phase stage`에는 실행부 구성요소·GameInfo 검사와 `refresh_host_runtime.py`의 실제 GameCore 초기화·조회·종료 검증도 포함하와요. 같은 실행 입력의 근거가 있으면 재사용하며 달라졌으면 새 복사본에서 영어·한국어로 실행하와요. 새 게임·지도 생성·턴은 아직 별도 구현 관문이랍니다. 아래는 각 단계 당시의 기록이와요.

중첩된 GC 갱신의 연결 단계만 실패했다면, 선행 성공 단계와 도구 해시를 보존한 상태에서 `python tools/refresh_lua_borrowed_integration.py --phase build --from-step refresh_gc_lifecycle_integration --gc-from-step analyze_sdk_x64`로 연결부터 재개할 수 있사와요. 컴파일·구성요소 입력이 달라졌다면 이 재개 방식으로 건너뛰지 않사와요.

## 이전 프랙탈 수치 경계 재현

프랙탈 수치 단계 당시 패치 생성기는 `define_fractal_numeric_patches.py`였답니다. attempt_035의 620개를 보존하고 수치·오류 경계 9개를 추가한 629개를 재현했사와요. 아래는 해당 단계의 컴파일·연결과 독립 오류 재현·검토 묶음 갱신 이력이랍니다.

```text
python tools/define_fractal_numeric_patches.py --apply
python tools/build_sdk_x64.py --vs "C:\Program Files\Microsoft Visual Studio\2022\Community"
python tools/refresh_fractal_numeric_integration.py --phase build
python tools/refresh_fractal_numeric_integration.py --phase stage
```

갱신 기록은 `evidence/fractal_numeric/integration_refresh`에 있사와요. 각 프로세스가 실제 종료하고 성공한 뒤 다음 명령을 실행하며, 관측 중단만으로 재시작하지 않사와요. 종료한 실패 단계만 원인을 수정한 뒤 `--from-step`으로 재개하와요. 원본의 예상된 0 나눗셈·메모리 오류 종료를 수정본 실패와 구분하며, 전체 GameCore 실행과 게임 계산 멀티코어는 별도 관문이랍니다. [수치 계약과 정확한 시험 범위](M3_FRACTAL_NUMERICS.md)를 기준으로 하와요. 아래 명령은 각 단계 당시의 기록이며 현재 전체 갱신에는 위 절차를 사용하와요.

## 이전 프랙탈 소유권·선택 인수 수정 재현

소유권 단계의 패치 생성기는 `define_lua_fractal_patches.py`이랍니다. 기존 attempt_034의 613개를 보존하고 7개를 추가하여 총 620개를 재현하와요. 아래 절차는 실제 GameCore를 로드하지 않고 정식 컴파일·연결과 독립 시험·검토용 묶음을 갱신하와요.

```text
python tools/define_lua_fractal_patches.py --apply
python tools/build_sdk_x64.py --vs "C:\Program Files\Microsoft Visual Studio\2022\Community"
python tools/refresh_lua_fractal_integration.py --phase build
python tools/refresh_lua_fractal_integration.py --phase stage
```

각 명령의 완료와 성공을 확인한 뒤 다음 명령을 실행하와요. 갱신 기록은 `evidence/lua_fractal/integration_refresh`에 보존되며, 끝난 프로세스의 실패 원인을 수정한 뒤에만 `--from-step`으로 재개하와요. 원본과 수정본의 수명 시험은 계측 객체를 사용하고, 실제 프랙탈 계산은 난수·컨테이너 어댑터를 사용하와요. 전체 GameCore 실행·입력 수치 전체의 안전성·게임 객체 수명·게임 멀티코어 검증은 별도랍니다. [정확한 프랙탈 시험 범위](M3_LUA_FRACTAL.md)를 기준으로 구분하와요. 아래 절차는 각 단계 당시의 기록이므로 현재 전체 갱신에는 위 명령을 사용하와요.

## 이전 Lua 등록 오류 전달 재현

등록 단계의 패치 생성기는 `define_lua_registration_patches.py`이랍니다. 기존 attempt_033의 603개를 보존하고 10개를 추가하여 당시 총 613개를 재현했사와요. 후속 프랙탈 패치는 보존하지만, 현재 전체 통합에는 맨 위의 프랙탈 갱신 절차가 필요하와요.

```powershell
python tools/define_lua_registration_patches.py --apply
python tools/build_sdk_x64.py --vs "C:\Program Files\Microsoft Visual Studio\2022\Community" --phase all
python tools/refresh_lua_registration_integration.py --phase build
python tools/refresh_lua_registration_integration.py --phase stage
```

각 명령의 완료와 성공을 확인한 뒤 다음 명령을 실행하와요. 갱신 기록은 `evidence/lua_registration/integration_refresh`에 보존되며, 끝난 프로세스의 실패 원인을 수정한 뒤에만 `--from-step`으로 재개하와요. 게임 메서드·게임 객체 수명·실게임은 이 독립 시험의 통과 범위가 아니랍니다. [정확한 등록 시험 범위](M3_LUA_REGISTRATION.md)를 기준으로 구분하와요. 이후 절차는 각 단계 당시의 기록이랍니다.

## 이전 전체 GC 초기화·종료 제어 재현

2026-09-26 현재 패치 생성기는 `define_gc_lifecycle_patches.py`이랍니다. 기존 588개를 보존하고 12개를 추가한 600개 패치를 재현하와요. 아래 절차는 확보된 원본 보존본·의존성·기준 증거를 사용하며, 이후의 단계별 명령은 과거 기록이랍니다.

```powershell
python tools/define_gc_lifecycle_patches.py
python tools/define_logging_caller_patches.py
python tools/define_bootstrap_patches.py
python tools/define_debug_caller_patches.py
python tools/define_globals_cleanup_patches.py
python tools/define_construction_patches.py
python tools/define_host_binding_patches.py
python tools/define_database_postprocess_patches.py
python tools/define_database_loader_patches.py
python tools/define_info_cleanup_patches.py
python tools/define_database_cache_patches.py
python tools/define_startup_owners_patches.py
python tools/define_gc_lifecycle_patches.py
python tools/build_sdk_x64.py --vs "C:\Program Files\Microsoft Visual Studio\2022\Community"
python tools/build_gc_lifecycle.py
python tools/verify_gc_lifecycle.py
python tools/refresh_world_builder_dependencies.py
python tools/refresh_gc_lifecycle_integration.py
python tools/refresh_gc_lifecycle_stage.py
```

각 명령의 성공을 확인한 뒤 다음 명령을 실행하와요. 통합·검토본 도구는 실패 시 중단하고 `evidence/gc_lifecycle`에 단계별 로그를 보존하와요. 실행 세션이 종료된 것을 확인하고 원인을 수정한 뒤에만 `--from-step`으로 재개하와요. 독립 시험은 실행하지만 GameCore DLL과 Civ V는 실행하지 않사와요. [정확한 시험 범위와 남은 초기화 작업](M3_GC_LIFECYCLE.md)에 미검증 범위를 기록했답니다.

## 최초 수집 절차

`tools/collect_baseline.py`는 Python 표준 라이브러리와 설치된 Microsoft `dumpbin`을 사용해 파일을 읽는 도구랍니다. Civ V 실행이나 GameCore DLL 로딩, 소스 빌드, 설치·설정 변경을 수행하지 않사와요. 출력 경로는 이 독립 프로젝트 아래로 제한되어 있사와요.

이번 조사에 사용한 경로는 다음과 같사와요.

```powershell
python "C:\Users\home\OneDrive\Documents\Firaxis ModBuddy\ZeroSis' Engine Modernization\tools\collect_baseline.py" --game "C:\Program Files (x86)\Steam\steamapps\common\Sid Meier's Civilization V" --sdk "C:\Program Files (x86)\Steam\steamapps\common\Sid Meier's Civilization V SDK\CvGameCoreSource" --mods "C:\Users\home\OneDrive\Documents\My Games\Sid Meier's Civilization 5\MODS" --dumpbin "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Tools\MSVC\14.44.35207\bin\Hostx64\x64\dumpbin.exe" --out "C:\Users\home\OneDrive\Documents\Firaxis ModBuddy\ZeroSis' Engine Modernization\evidence\2026-09-22"
```

기존 조사 기록을 보존하면서 다시 조사하려면 프로젝트 아래의 새로운 출력 디렉터리를 지정하면 된답니다. 같은 출력 디렉터리를 사용하면 해당 수집 도구의 결과 파일이 갱신된답니다. `engine_services.csv`는 수집 도구가 원시 호출 목록을 이름별로 묶어 만드는 초기 작업 목록이며, 각 항목은 구현·계약 검토 대기로 표시되어 있사와요.

## 판독 범위

- 게임 루트의 EXE/DLL, DLC 경로의 GameCore DLL, 설치 모드의 GameCore 이름을 가진 DLL을 조사하와요.
- SDK의 각 모듈 파일과 루트 파일에 SHA-256을 기록하고 수집 끝에 다시 대조하와요.
- EXE/DLL의 PE 헤더에서 Machine·Optional Header Magic·LAA를 판독하와요.
- SDK의 `.lib` 파일은 `dumpbin /HEADERS`의 machine 관측값을 수집하와요. 관측 개수는 모든 링크 심볼 수나 코드 함수 수가 아니와요.
- DX11 EXE와 기본 BNW GameCore의 `dumpbin /DEPENDENTS` 원문을 남기와요. 실행 중 동적 로딩, 엔진 콜백, 전이 의존성 전체를 조사한 결과는 아니와요.
- `gDLL->메서드(...)`의 텍스트 위치를 모으와요. 주석·조건부 컴파일·간접 호출은 구문과 의미를 추가로 검토할 대상이랍니다.
- 설치 모드 파일과 modinfo의 선언은 기록하되, 활성화 또는 실제 로드를 추론하지 않사와요.

## 추가 환경 관측

다음 컴파일러 파일을 확인했사와요. 이후 수치 시험에는 VS 2022, SDK 기준 DLL에는 원본 프로젝트의 v90 도구 세트를 사용했사와요. VS 2010 컴파일러 자체로 빌드한 결과는 아니랍니다.

| 도구 | 파일 버전 |
|---|---|
| Visual C++ 2008 `VC/bin/cl.exe` | 15.00.30729.01 |
| Visual C++ 2010 `VC/bin/cl.exe` | 16.00.40219.01 |
| VS 2022 MSVC Hostx64/x64 `cl.exe` | 19.44.35213.0 |

## M1 연결 계약 조사

아래 명령은 소스·라이브러리를 읽어 `evidence/m1`을 갱신하며 게임을 실행하지 않사와요.

```powershell
python "C:\Users\home\OneDrive\Documents\Firaxis ModBuddy\ZeroSis' Engine Modernization\tools\analyze_contracts.py" --sdk "C:\Program Files (x86)\Steam\steamapps\common\Sid Meier's Civilization V SDK\CvGameCoreSource" --dumpbin "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Tools\MSVC\14.44.35207\bin\Hostx64\x64\dumpbin.exe"
```

이 조사기는 C++ 전처리기·컴파일러가 아니므로 호출 후보와 선언 이름 연결을 실제 오버로드 선택·스레드 안전성 증거로 보지 않사와요.

## 독립 x86·x64 수치 구현 검증

다음 명령은 새로 만든 **수치 시험 프로그램 두 개만 빌드·실행**하와요. Civ V 또는 GameCore DLL은 실행·로드하지 않사와요. 결과는 `evidence/numerics`, 빌드 파일은 `Build/Numerics`, 검증된 헤더·기록은 `Stage/Numerics`에 갱신하와요.

```powershell
python "C:\Users\home\OneDrive\Documents\Firaxis ModBuddy\ZeroSis' Engine Modernization\tools\verify_numerics.py" --sdk "C:\Program Files (x86)\Steam\steamapps\common\Sid Meier's Civilization V SDK\CvGameCoreSource" --vs "C:\Program Files\Microsoft Visual Studio\2022\Community"
```

원본 난수 소스 해시가 M0 기록과 다르면 추출을 중단하와요. x86 참조는 원본 산술식과 별도 수치 래퍼이며, 기존 GameCore 클래스 전체의 실행은 아니랍니다. 모든 기록을 x64 출력·Python 기준과 비교하고, 경고 발생이나 입력 변경 시 성공으로 처리하지 않사와요. 실행 기록의 해시는 출력 기록 자체의 식별자이며 게임 저장 호환성을 뜻하지 않사와요.

## 원본 SDK x86 기준 DLL 빌드

이 명령은 `Source/SDK_BNW_Original`에 바이트가 같은 복사본을 만들고, 별도 `Build/SDK_Reference`에서 빌드하와요. 설치 SDK 또는 이미 있는 복사본이 M0와 다르면 덮어쓰지 않고 중단하와요. 1,105개 입력 파일, 설치된 VC++ 2008 개발 도구·MSBuild 4·Windows SDK v7.0A가 필요하와요.

```powershell
python "C:\Users\home\OneDrive\Documents\Firaxis ModBuddy\ZeroSis' Engine Modernization\tools\build_sdk_reference.py" --sdk "C:\Program Files (x86)\Steam\steamapps\common\Sid Meier's Civilization V SDK\CvGameCoreSource" --msbuild "C:\Windows\Microsoft.NET\Framework\v4.0.30319\MSBuild.exe" --windows-sdk "C:\Program Files (x86)\Microsoft SDKs\Windows\v7.0A"
```

`Source/BuildSupport`의 리소스 전용 헤더와 targets를 사용해 누락된 MFC 리소스 헤더 의존을 표준 Windows 버전 정보 정의로 연결하고 링크 지도를 생성하와요. 원본 SDK 소스·프로젝트는 변경하지 않사와요. MSBuild 경로는 [공식 특수문자 규칙](https://learn.microsoft.com/en-us/visualstudio/msbuild/how-to-escape-special-characters-in-msbuild)에 따라 아포스트로피를 리터럴로 전달하와요.

성공 상태는 DLL 생성과 원본·복사본 해시 일치를 뜻하며 경고 0건을 뜻하지 않사와요. 빌드 경고·오류는 시도별 `evidence/sdk_reference/attempts`에 보관하와요. **생성 DLL의 로드·설치·게임 실행은 이 명령에 포함되지 않사와요.**

## 실제 연결 요구사항과 기록 정합성

SDK 기준 빌드 이후 아래 명령으로 161개 COFF 오브젝트·링크 지도를 조사하와요. x86 SDK 라이브러리의 제공 후보를 보여 주며 x64 구현을 자동 생성하지 않사와요.

```powershell
python "C:\Users\home\OneDrive\Documents\Firaxis ModBuddy\ZeroSis' Engine Modernization\tools\analyze_link_dependencies.py" --dumpbin "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Tools\MSVC\14.44.35207\bin\Hostx64\x64\dumpbin.exe"
python "C:\Users\home\OneDrive\Documents\Firaxis ModBuddy\ZeroSis' Engine Modernization\tools\verify_project.py"
```

마지막 명령은 M0 원본 1,139개, SDK 복사본, 조사 입력, 시험에 사용된 코드·실행 파일·Stage의 해시와 보고서 연결을 확인하는 기록 검증이랍니다. 자체적으로 컴파일·시험 프로그램·게임을 다시 실행하지 않사와요.

## 실제 SDK CRC 코드와 작업 실행기 검증

아래 명령은 독립 CRC 시험 두 개와 x64 작업 실행기 시험 하나를 빌드·실행하와요. CRC 참조에는 설치된 VC++ 2008 v90·Windows SDK v7.0A·VC90 런타임을 사용하고, 새 구현에는 VS 2022를 사용하와요. 참조 도구 경로는 `build_crc_reference.py`에 현재 설치 경로로 명시되어 있사와요.

```powershell
python "C:\Users\home\OneDrive\Documents\Firaxis ModBuddy\ZeroSis' Engine Modernization\tools\verify_crc.py" --sdk "C:\Program Files (x86)\Steam\steamapps\common\Sid Meier's Civilization V SDK\CvGameCoreSource" --vs "C:\Program Files\Microsoft Visual Studio\2022\Community" --dumpbin "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Tools\MSVC\14.44.35207\bin\Hostx64\x64\dumpbin.exe"
python "C:\Users\home\OneDrive\Documents\Firaxis ModBuddy\ZeroSis' Engine Modernization\tools\verify_ordered_jobs.py" --vs "C:\Program Files\Microsoft Visual Studio\2022\Community"
python "C:\Users\home\OneDrive\Documents\Firaxis ModBuddy\ZeroSis' Engine Modernization\tools\verify_project.py"
```

CRC 원본 헤더·타입 정의·라이브러리의 M0 해시를 확인하고, v90 링크 지도에서 실제 `FCRC::Calc` 제공자를 검사한 뒤 실행하와요. 전체·분할 출력을 x64·Python zlib 계산과 비교하며 `evidence/crc`에 기록하와요. 작업 실행기는 역순 완료를 유도한 72회 실행·4,608개 기록을 비교하고 `evidence/ordered_jobs`에 남긴답니다.

헤더는 `Stage/Numerics/CvCompatibleCrc32.h`, `Stage/Concurrency/OrderedBatch.h`에 검증 기록과 함께 복사하와요. 게임 DLL·설치 MODS 배포, 물리 코어 추적, 게임 성능 측정은 수행하지 않사와요.

## 작업 결과의 값 상태 반영 검증

다음 명령은 `VersionedState`·`OrderedBatch`·CRC를 결합한 독립 x64 시험 프로그램을 빌드·실행하와요. VS 2022가 필요하며, 기존 `Stage/Concurrency/OrderedBatch.h`와 `Stage/Numerics/CvCompatibleCrc32.h`가 시험 대상 소스와 일치해야 하와요. 처음 구성할 때는 앞 절의 CRC·작업 실행기 검증을 먼저 진행하와요.

```powershell
python "C:\Users\home\OneDrive\Documents\Firaxis ModBuddy\ZeroSis' Engine Modernization\tools\verify_state_commit.py" --vs "C:\Program Files\Microsoft Visual Studio\2022\Community"
python "C:\Users\home\OneDrive\Documents\Firaxis ModBuddy\ZeroSis' Engine Modernization\tools\verify_project.py"
```

21개 이름 있는 시험 사례와 2,304회 정상 반영의 18,432개 상태 기록을 비교하와요. 정상·거부 경로, 준비 예외와 복사/이동 예외 주입, 실제 다른 스레드의 취소 요청을 포함한답니다. 실행 결과는 `evidence/state_commit`, 실행 파일·이진 기록은 `Build/StateCommit/x64`, 검증된 헤더·기록은 `Stage/State`에 남기와요.

이 시험은 별도 값 상태를 소유·교체하며 기존 GameCore 객체를 연결하지 않사와요. 실제 메모리 고갈·저장 복구·전체 게임 턴·성능 시험도 포함하지 않사와요. 입력 코드·출력·빌드 로그·실행 파일·Stage는 해시로 연결하며, 마지막 기록 정합성 명령은 시험을 재실행하지 않사와요. [상태 반영 계약](M2_STATE_COMMIT.md)

## 실제 BNW C++ x64 이식·컴파일·연결 조사

기존 x86 기준 빌드의 `snapshot_manifest.json`과 원본 해시가 먼저 필요하와요. 다음 명령은 별도 `Source/SDK_BNW_x64`를 생성하고 C++ 161개를 컴파일하며, 할당기·Lua·숫자·스트림의 독립 시험 프로그램을 실행하와요. GameCore DLL·Civ V는 실행하지 않사와요.

```powershell
python "C:\Users\home\OneDrive\Documents\Firaxis ModBuddy\ZeroSis' Engine Modernization\tools\define_database_caller_patches.py"
python "C:\Users\home\OneDrive\Documents\Firaxis ModBuddy\ZeroSis' Engine Modernization\tools\build_sdk_x64.py" --vs "C:\Program Files\Microsoft Visual Studio\2022\Community"
python "C:\Users\home\OneDrive\Documents\Firaxis ModBuddy\ZeroSis' Engine Modernization\tools\verify_sdk_x64_allocator.py" --vs "C:\Program Files\Microsoft Visual Studio\2022\Community"
python "C:\Users\home\OneDrive\Documents\Firaxis ModBuddy\ZeroSis' Engine Modernization\tools\build_lua_component.py" --vs "C:\Program Files\Microsoft Visual Studio\2022\Community"
python "C:\Users\home\OneDrive\Documents\Firaxis ModBuddy\ZeroSis' Engine Modernization\tools\compare_lua_reference.py" --vs "C:\Program Files\Microsoft Visual Studio\2022\Community"
python "C:\Users\home\OneDrive\Documents\Firaxis ModBuddy\ZeroSis' Engine Modernization\tools\build_lua_provider.py" --vs "C:\Program Files\Microsoft Visual Studio\2022\Community"
python "C:\Users\home\OneDrive\Documents\Firaxis ModBuddy\ZeroSis' Engine Modernization\tools\compare_lua_reference.py" --vs "C:\Program Files\Microsoft Visual Studio\2022\Community" --label provider --runtime MD --library "C:\Users\home\OneDrive\Documents\Firaxis ModBuddy\ZeroSis' Engine Modernization\Build\Lua_provider\x64\ZeroSis_Lua51_x64.lib"
python "C:\Users\home\OneDrive\Documents\Firaxis ModBuddy\ZeroSis' Engine Modernization\tools\verify_numeric_boundaries.py" --vs "C:\Program Files\Microsoft Visual Studio\2022\Community" --lua-provider "C:\Users\home\OneDrive\Documents\Firaxis ModBuddy\ZeroSis' Engine Modernization\evidence\lua_provider\build_result.json"
python "C:\Users\home\OneDrive\Documents\Firaxis ModBuddy\ZeroSis' Engine Modernization\tools\verify_stream_provider.py" --vs "C:\Program Files\Microsoft Visual Studio\2022\Community"
python "C:\Users\home\OneDrive\Documents\Firaxis ModBuddy\ZeroSis' Engine Modernization\tools\verify_serialization_provider.py" --vs "C:\Program Files\Microsoft Visual Studio\2022\Community"
python "C:\Users\home\OneDrive\Documents\Firaxis ModBuddy\ZeroSis' Engine Modernization\tools\verify_foundation_provider.py" --vs "C:\Program Files\Microsoft Visual Studio\2022\Community"
python "C:\Users\home\OneDrive\Documents\Firaxis ModBuddy\ZeroSis' Engine Modernization\tools\verify_temp_heap_provider.py" --vs "C:\Program Files\Microsoft Visual Studio\2022\Community"
python "C:\Users\home\OneDrive\Documents\Firaxis ModBuddy\ZeroSis' Engine Modernization\tools\verify_temp_heap_callers.py" --vs "C:\Program Files\Microsoft Visual Studio\2022\Community"
python "C:\Users\home\OneDrive\Documents\Firaxis ModBuddy\ZeroSis' Engine Modernization\tools\verify_auto_archive_provider.py" --vs "C:\Program Files\Microsoft Visual Studio\2022\Community"
python "C:\Users\home\OneDrive\Documents\Firaxis ModBuddy\ZeroSis' Engine Modernization\tools\build_database_reference.py"
python "C:\Users\home\OneDrive\Documents\Firaxis ModBuddy\ZeroSis' Engine Modernization\tools\run_database_reference.py"
python "C:\Users\home\OneDrive\Documents\Firaxis ModBuddy\ZeroSis' Engine Modernization\tools\build_database_provider.py" --vs "C:\Program Files\Microsoft Visual Studio\2022\Community"
python "C:\Users\home\OneDrive\Documents\Firaxis ModBuddy\ZeroSis' Engine Modernization\tools\build_database_fault_tests.py" --vs "C:\Program Files\Microsoft Visual Studio\2022\Community"
python "C:\Users\home\OneDrive\Documents\Firaxis ModBuddy\ZeroSis' Engine Modernization\tools\verify_database_provider.py"
python "C:\Users\home\OneDrive\Documents\Firaxis ModBuddy\ZeroSis' Engine Modernization\tools\build_flua_provider.py" --vs "C:\Program Files\Microsoft Visual Studio\2022\Community"
python "C:\Users\home\OneDrive\Documents\Firaxis ModBuddy\ZeroSis' Engine Modernization\tools\verify_flua_provider.py"
python "C:\Users\home\OneDrive\Documents\Firaxis ModBuddy\ZeroSis' Engine Modernization\tools\build_string_provider.py" --vs "C:\Program Files\Microsoft Visual Studio\2022\Community"
python "C:\Users\home\OneDrive\Documents\Firaxis ModBuddy\ZeroSis' Engine Modernization\tools\verify_string_provider.py"
python "C:\Users\home\OneDrive\Documents\Firaxis ModBuddy\ZeroSis' Engine Modernization\tools\analyze_sdk_x64.py" --vs "C:\Program Files\Microsoft Visual Studio\2022\Community" --lua-provider "C:\Users\home\OneDrive\Documents\Firaxis ModBuddy\ZeroSis' Engine Modernization\evidence\lua_provider\build_result.json" --stream-provider "C:\Users\home\OneDrive\Documents\Firaxis ModBuddy\ZeroSis' Engine Modernization\evidence\streams\provider\build_result.json" --serialization-provider "C:\Users\home\OneDrive\Documents\Firaxis ModBuddy\ZeroSis' Engine Modernization\evidence\serialization\candidate\build_result.json" --foundation-provider "C:\Users\home\OneDrive\Documents\Firaxis ModBuddy\ZeroSis' Engine Modernization\evidence\foundation\build_result.json" --temp-heap-provider "C:\Users\home\OneDrive\Documents\Firaxis ModBuddy\ZeroSis' Engine Modernization\evidence\temp_heap\build_result.json" --auto-archive-provider "C:\Users\home\OneDrive\Documents\Firaxis ModBuddy\ZeroSis' Engine Modernization\evidence\auto_archive\build_result.json" --database-provider "C:\Users\home\OneDrive\Documents\Firaxis ModBuddy\ZeroSis' Engine Modernization\evidence\database\candidate\build_result.json" --flua-provider "C:\Users\home\OneDrive\Documents\Firaxis ModBuddy\ZeroSis' Engine Modernization\evidence\flua\build_result.json" --string-provider "C:\Users\home\OneDrive\Documents\Firaxis ModBuddy\ZeroSis' Engine Modernization\evidence\strings\build_result.json"
python "C:\Users\home\OneDrive\Documents\Firaxis ModBuddy\ZeroSis' Engine Modernization\tools\stage_sdk_x64_port.py"
python "C:\Users\home\OneDrive\Documents\Firaxis ModBuddy\ZeroSis' Engine Modernization\tools\verify_project.py"
```

생성 변경의 정식 입력은 `Source/Porting/sdk_x64_patches.json`이와요. `build_sdk_x64.py`는 원본 해시·치환 횟수를 확인하고 기존 생성 기록과 다른 이식 파일이 있으면 중단하와요. 헤더만 먼저 확인하려면 `--phase pch`를 사용할 수 있으며, 전체 연결 분석과 Stage에는 기본 전체 컴파일이 필요하와요.

`build_sdk_x64.py` 성공은 161개 오브젝트 생성과 기존 `/W3`에서 숫자 변환 경고 0건까지이와요. `analyze_sdk_x64.py`의 `X64_LINK_BLOCKERS_CAPTURED`는 **실제 링크 실패를 기록한 성공 상태**이며 DLL 성공이 아니랍니다. Lua·스트림·열거형 직렬화·기반·임시 메모리·자동 상태 기록·데이터베이스 제공자 연결 후 해당 데이터베이스 단계의 미해결 심볼은 72개였으며, 필수 SDK 제공자를 빈 구현으로 채우거나 x86 라이브러리를 연결하지 않사와요.

`verify_sdk_x64_allocator.py`는 수정한 SDK 헤더 자체를 포함한 독립 시험을 실행하와요. 실제 할당 주소가 4GB 경계보다 높은지 확인하므로 해당 조건을 제공하지 않는 환경에서는 성공으로 처리하지 않사와요. 주소 자체는 실행마다 달라질 수 있으며, 4GB를 넘는 물리 메모리를 할당하지는 않사와요.

`build_lua_component.py`는 처음 한 번 공식 Lua 5.1.4 소스를 내려받고 공개 SHA-256을 확인하와요. 보관된 소스가 있으면 네트워크 없이 재현하와요. 생성되는 `/MT` 라이브러리는 수정 전 비교용이랍니다. `build_lua_provider.py`는 별도 `/MD` 제공자를 만들고, `compare_lua_reference.py`는 실제 설치 Lua DLL의 복사본과 비교하와요. provider 비교가 통과한 라이브러리만 실제 연결 조사에 넣는답니다. `verify_numeric_boundaries.py`는 범위 검사와 실제 SDK 함수 추출본을 실행하고 Python 정수 기준·원본 알림 표와 대조하와요. 실행 기록은 `evidence/numeric_boundaries`에 남긴답니다.

Stage 도구는 컴파일·입력·오브젝트·할당기·숫자 경계값·호출부 검증·링크 실패 자료가 일치할 때 변경 소스 62개, 지원 헤더 4개, Lua·스트림·열거형 직렬화·기반·임시 메모리·자동 상태 기록 제공자 소스·라이선스·시험·정적 라이브러리, 호출부 시험과 기록을 `Stage/GameCore_x64`에 보관하와요. 기존 게임·설치 MODS 배포는 포함하지 않사와요. 시도별 기록은 `evidence/sdk_x64/attempts`, 경고 위치와 미해결 심볼은 같은 상위 evidence 폴더의 CSV에 있답니다. [현재 검증 범위](M2_TEMP_HEAP_CALLERS.md)

`verify_stream_provider.py`는 원본 SDK 아카이브를 연결한 VC9 x86 참조와 VS2022 x64 제공자를 빌드·실행하와요. 실행부가 요구하는 빈 FString 공유 저장소만 시험 코드에서 제공하며, 실제 스트림 코드는 아카이브에서 오와요. 3개 endian 모드의 바이트를 Python 기준과 대조하고, 원본과 다른 범위 초과 이동의 상태 보존은 별도 기대 차이로 기록하와요. [스트림 검증 범위](M2_STREAM_PROVIDER.md)

`define_serialization_patches.py`는 이전 직렬화 단계의 생성기이며 attempt_009 뒤의 저장 폭 보존 패치 9개만 다루와요. 이 단계의 계획 재현에는 `define_auto_archive_caller_patches.py`를 사용하와요. 최신 계획은 문서 끝의 현지화 진입점을 사용하와요. 보관된 attempt_013의 458개 패치를 그대로 확인한 뒤 자동 기록 호출부 패치 21개를 재구성하며, 반복 실행해도 패치와 숫자 수정 기록의 내용이 같음을 확인했답니다. `define_temp_heap_caller_patches.py`는 이전 임시 메모리 호출부 단계의 생성기로 보존하와요. `verify_serialization_provider.py`는 원본 SDK 열거형·문자열 연산자, 실제 컨테이너 헤더, 리플레이·투표 함수 추출본을 비교하와요. 1바이트 GameTypes 예외와 4바이트 목록 길이를 별도로 확인하고, 순서 없는 목록의 차이는 보고서에 남긴답니다. [직렬화 검증 범위](M2_SERIALIZATION_PROVIDER.md)

`verify_foundation_provider.py`는 원본 SDK의 CRC·잠금·시간·정렬 메모리와 x64 제공자를 빌드하여 독립 실행하와요. 직접 DLL 의존성을 검사한 뒤 다항식·객체 배치, 실제 OS 작업자의 잠금, QPC 전후 시간 범위, 크기 0·정렬·높은 주소를 확인하와요. 작업자 동시 실행은 실제 게임 턴의 병렬 실행 증거가 아니며, 원본과 다른 오류 처리·초기화 정책도 별도 기록하와요. [기반 제공자 검증 범위](M2_FOUNDATION_PROVIDER.md)

`verify_temp_heap_provider.py`는 먼저 기반 제공자의 현재 증거를 확인하고, 실제 SDK 임시 메모리와 새 x64 구현을 독립 실행하와요. 13,520개 순차 동작은 별도 모델과 비교하며, 작업자 1·2·4·8개의 주소·내용·마지막 반납, 작은 공간의 400,000회 경쟁, 크기·대여 수·호스트 export의 실패와 복구를 검증하와요. 큰 주소 시험은 4GiB 가상 범위를 예약하고 8KiB 페이지만 커밋하며 실제 메모리 고갈 시험은 아니랍니다. `GetTempHeap` export를 제공하는 독립 시험 호스트가 필요하고, export가 없는 실패 시험 실행 파일은 별도로 빌드하와요. 이 호스트를 실제 게임 실행부로 계산하지 않사와요. [임시 메모리 검증 범위](M2_TEMP_HEAP_PROVIDER.md)

`verify_temp_heap_callers.py`는 실제 수정한 SDK 래퍼와 내장 데이터베이스 지원 헤더를 실행하와요. 한 실행 파일은 실제 Foundation 할당기, 다른 파일은 크기 기록·실패 주입용 할당기를 사용하며 링크 지도에서 분리를 검사한답니다. Build 내부의 고유 한글 파일명에만 시험 자료를 만들고, 기존 파일을 재사용하거나 실패 흔적을 임의로 지우지 않사와요. 각각 33개 정상 자료와 입출력 실패 26건, 별도 할당 실패 5건을 검사하며, 성공한 실행은 자신이 만든 시험 파일을 제거하와요. 기존 SDK·숫자·제공자 입력이 바뀌면 해당 회귀를 먼저 갱신해야 연결·Stage 관문을 통과하와요. [호출부 검증 범위](M2_TEMP_HEAP_CALLERS.md)

`verify_auto_archive_provider.py`는 실제 원본 아카이브의 x86 코드와 새 x64 제공자를 빌드하여 직접 DLL 의존성을 확인한 뒤 실행하와요. 현재 Streams·Serialization 증거가 먼저 필요하와요. 등록 순서와 주소 순서를 분리한 4,114개 동작의 Python 모델, 실제 변수 템플릿, 반대 물리 배치의 교차 읽기, 실패/거부와 재시도를 검증하와요. 원본의 작은 디버그 출력 버퍼를 넘길 큰 실수는 x64 후보에만 실행하며, 실수 표시 차이는 별도 기록하와요. 후속 호출부 검증에서는 별도 x64 실행 파일로 소멸·부분 생성 실패·벡터 변경 실패·공유 이름의 동시 초기화를 시험하와요. 변수 배치가 바뀌었으므로 GameCore 161개와 제공자를 모두 다시 컴파일한 attempt_014를 사용하며, 이전 오브젝트와 혼용하지 않사와요. [자동 기록 제공자 검증 범위](M2_AUTO_ARCHIVE_PROVIDER.md) · [호출부와 ABI 이전](M2_AUTO_ARCHIVE_CALLERS.md)

## 검증 한계

수집 종료 코드 0, PE 판독, XML 프로젝트 메타데이터, 해시 일치는 정적 조사 증거이와요. 게임 로드·실제 프레임·턴 시간·메모리 압박·모드 효과·동기화·저장 호환성은 증명하지 않사와요. 모든 입력의 변경을 방지하는 잠금 도구도 아니며, 해시 대조 범위는 기록된 1,139개 파일과 이번 수집 구간이랍니다.

작업공간의 광역 파일 탐색 중 과거 `outputs`의 Python 패키지 폴더 일부는 접근이 제한되어 있었사와요. 최종 SDK·게임·MODS 수집은 명시된 경로에서 종료 코드 0으로 완료했으며, 이를 컴퓨터 전체에 엔진 소스가 없다는 주장으로 확대하지 않사와요.

데이터베이스 참조 도구는 복사한 실제 x86 DLL과 Lua 의존성의 가져오기를 검사한 뒤 소유한 시험 데이터베이스만 실행하와요. 원본 double 조회 결함은 별도 프로세스의 예상 접근 위반으로 기록하며 게임 실행이 아니랍니다. x64 도구는 공식 SQLite 3.7.17의 고정 체크섬을 검사하고 실제 DLL을 빌드하와요. verify_database_provider.py는 선행 빌드의 원본/후보 기록 비교·파일 교환·수명·독립 연결 동시 실행 및 41개 가져오기의 공개 함수·연결 라이브러리·실제 구현 지도를 검증하와요. [범위와 남은 관문](M2_DATABASE_PROVIDER.md)

데이터베이스 단계의 패치 생성 진입점은 define_database_caller_patches.py이며 attempt_014의 479개 패치를 보존하고 조회 대입 선언 한 항목을 추가하와요. 이전 단계의 생성기는 해당 단계 기록을 재현할 때만 사용하와요. 할당 실패 시험은 제품과 동일한 세 오브젝트에 시험용 할당기를 별도 DLL로 연결하므로 제품 DLL에는 실패 제어 함수가 포함되지 않사와요.

데이터베이스 캐시 비교는 `python tools/verify_database_corpus.py --vs "C:\Program Files\Microsoft Visual Studio\2022\Community"`로 프로젝트 폴더에서 재현하와요. 원본·후보 제공자 검증이 먼저 필요하며, 캐시의 쓰기 기록 파일이 있거나 복사 중 해시·수정 시간이 바뀌면 중단하와요. 소유한 복사본만 읽기 전용으로 열고 표별 자료형 조회·전체 SQL hex 값의 SHA-256과 실행 기록을 비교한답니다. `database_corpus_evidence.py`는 고정한 복사본·도구·실행 파일·로그를 확인하며, 나중에 갱신될 실제 캐시 경로는 과거 출처로만 취급하와요. Stage에는 소스·도구·보고서·조회 기록을 포함하며 60MB가량의 캐시 복사본은 연구용 Build에 남기와요. 최종 순서는 캐시 비교, `stage_sdk_x64_port.py`, `verify_project.py`랍니다.

Lua C++ 연결부는 프로젝트 폴더에서 `python tools/build_flua_provider.py --vs "C:\Program Files\Microsoft Visual Studio\2022\Community"`, `python tools/verify_flua_provider.py` 순서로 재현하와요. 원본 x86 SDK 아카이브와 복사한 Lua DLL을 사용하며 x64 쪽은 기존 Lua·Foundation 제공자의 증거가 먼저 필요하와요. 연결 명령에는 `--flua-provider evidence/flua/build_result.json`을 추가하고 Stage·전체 검증을 갱신하와요. [정확한 실행 범위](M2_FLUA_PROVIDER.md)

문자열 제공자는 `python tools/build_string_provider.py --vs "C:\Program Files\Microsoft Visual Studio\2022\Community"`, `python tools/verify_string_provider.py` 순서로 재현하와요. 원본 VC9 아카이브·x64 구현·독립 모델을 대조하며 스트림 제공자의 검증이 먼저 필요하와요. 연결에는 `--string-provider evidence/strings/build_result.json`을 추가하와요. 시험용 실패 할당기는 별도 실행 파일에만 연결하며 제품 라이브러리는 같은 두 오브젝트를 그대로 사용하와요. [문자열 검증 범위](M2_STRINGS_PROVIDER.md)

현지화의 숫자·문자 변환 단계는 프로젝트 폴더에서 아래 순서로 재현하와요. `fetch_icu44_source.py`는 고정한 공식 커밋 ZIP의 SHA-256을 검사하며 보관 ZIP이 있으면 네트워크 없이 동작하와요. 원본 관찰 도구는 복사된 구성요소의 가져오기를 검사한 뒤 시험 DB를 사용하와요. 알려진 NaN 영문 읽기 결함은 별도 프로세스의 스택 소진으로 기록하며 게임 실행이 아니랍니다.

```powershell
python tools/fetch_icu44_source.py
python tools/build_icu44.py
python tools/build_localization_icu.py
python tools/build_localization_reference.py
python tools/verify_localization_reference.py
python tools/verify_icu44.py
python tools/stage_localization_icu.py
python tools/verify_project.py
```

기록된 구현만 다시 확인하려면 `python tools/localization_icu_evidence.py`를 사용하와요. 이 명령은 새 실행 없이 원본·빌드·원본 비교 기록과 실제 연결 지도를 검증하와요. Stage는 현지화 숫자·문자 부품의 검토용 묶음이며 전체 Localization DLL이나 게임 배포물이 아니랍니다. [구현·의도한 차이·남은 관문](M2_LOCALIZATION_PROVIDER.md)

## 현지화 SDK 연결 단계

이 현지화 단계의 패치 생성기는 `define_localization_patches.py`이며, 현재 최신 생성기는 아래 지도 부가 데이터 단계의 `define_world_builder_mod_patches.py`이랍니다. attempt_015의 기존 480개 항목을 보존하고 객체 배치가 바뀌지 않는 내부 접근 선언 2개를 더하와요. GameCore 재컴파일 뒤 공용 SDK 명세를 참조하는 기존 제공자의 기록도 갱신하와요.

```powershell
python tools/define_localization_patches.py
python tools/build_sdk_x64.py --vs "C:\Program Files\Microsoft Visual Studio\2022\Community"
python tools/verify_database_provider.py
python tools/refresh_localization_dependencies.py
python tools/probe_localization_runtime.py
python tools/build_localization_provider.py
python tools/verify_localization_provider.py
python tools/localization_provider_evidence.py
```

전체 연결 조사에는 기존 제공자 인수와 함께 `--localization-provider evidence/localization/provider/build_result.json`을 추가하와요. 이 현지화 단계에서 16개 해소 후 미해결 항목은 36개였사와요. `stage_localization_icu.py`, `stage_localization_values.py`, `stage_localization_provider.py`로 기록과 검토본을 확인하와요. 실게임 실행 명령은 포함하지 않사와요. [수용 범위와 의도한 차이](M2_LOCALIZATION_INTEGRATION.md)

## 지도 형식 이름·그룹 연결 단계

SDK 헤더 변경 없이 실제 타입 이름·그룹 제공자를 추가했사와요. `probe_world_builder.py`, `build_world_builder_types.py`, `verify_world_builder_types.py`, `world_builder_types_evidence.py`를 순서대로 실행하와요. 원본 VC9 라이브러리와 새 x64 구현을 비교하고, 저장 형식과 2,048회 조작은 별도 모델로도 확인하와요.

전체 연결 명령의 기존 10개 제공자에 `--world-builder-types-provider evidence/world_builder/types/build_result.json`을 추가하와요. 이 타입·그룹 단계의 기록은 36→33개이며 `stage_world_builder_types.py`, `stage_sdk_x64_port.py`, `verify_project.py`로 검토본과 정합성을 확인하와요. 지도 부가 데이터와 전체 지도 파일의 구현·검증은 후속 범위랍니다. [계약과 검증](M2_WORLD_BUILDER_PROVIDER.md)

## 지도 부가 데이터 연결 단계

현재 최신 생성기는 `define_world_builder_mod_patches.py`이랍니다. 기존 482개를 그대로 유지하고 내부 접근 선언 6개를 더한 뒤 `build_sdk_x64.py --vs "C:\Program Files\Microsoft Visual Studio\2022\Community"`로 전체를 재컴파일하와요. `probe_world_builder_mod_data.py`, `refresh_world_builder_dependencies.py`, `world_builder_mod_data_evidence.py`를 순서대로 실행하와요. 재검증 도구는 변경된 SDK 명세를 사용하는 의존성을 실제로 다시 빌드·시험하와요.

전체 연결 명령에 `--world-builder-mod-data-provider evidence/world_builder/mod_data/build_result.json`을 추가하와요. 현재 기록은 33→17개랍니다. `stage_localization_values.py`, `stage_localization_provider.py`, `stage_world_builder_types.py`, `stage_world_builder_mod_data.py`, `stage_sdk_x64_port.py`, `verify_project.py` 순서로 검토본과 현재 증거를 맞추와요. 실게임 실행은 포함하지 않사와요. [부가 데이터 범위와 한계](M2_WORLD_BUILDER_MOD_DATA.md)
