# SDK 빌드 시간 개선

## 확정 범위

- 사용자 요구: Civ V SDK 소스의 빌드·컴파일 시간을 줄이고, 긴 코드 편집 시 발생하는 렉도 다룬다.
- 빌드 대상: 별도 작업장의 BNW x86 SDK 사본과 기존 x64 SDK 포트. 기존 원본·포트 생성기와 검증 결과를 덮어쓰지 않는다.
- 구현: 전용 출력 폴더에 PCH·OBJ·MSBuild 의존성 기록을 유지하는 개발용 증분 컴파일 진입점. 병렬 컴파일 개수는 제한 가능하게 한다.
- 저장 호환성: 게임 소스·저장 키·스키마·Mod ID·버전·밸런스 변경 없음. 게임 실행·DLL 배포 범위는 포함하지 않는다.
- 편집기: 현재 사용 중인 편집기는 미확인. 설치된 VS Code에 가벼운 별도 편집 프로필을 준비했으며 기존 편집기의 전역 설정은 변경하지 않았다.

## 확인한 병목

`tools/build_sdk_x64.py`는 매번 새 attempt 출력 폴더를 생성하여 PCH와 C++ 161개를 재컴파일한다. 기존 원본 SDK 프로젝트의 `MultiProcessorCompilation`은 이미 켜져 있다. 원본 x86 SDK는 개발 반복 빌드에도 `EnablePREfast=true`로 정적 분석을 요청한다.

## 수용 기준

1. 실제 SDK의 전체 C++ 파일을 컴파일하고 객체 아키텍처를 확인한다.
2. 변경 없는 두 번째 실행은 컴파일을 생략한다.
3. CPP 변경, 일반 헤더 변경, PCH 헤더 변경, 출력 누락·손상, 컴파일 실패 후 복구에서 오래된 객체를 재사용하지 않는다.
4. 원본 SDK, 기존 accepted 산출물, 게임 및 MODS를 변경하지 않는다.
5. 첫 컴파일과 반복 컴파일 시간을 같은 도구에서 측정한다. 이를 게임 실행 속도 향상으로 해석하지 않는다.

## 사용법

현재 ModBuddy 작업장 루트의 PowerShell에서 실행한다.

```powershell
python "C:\Users\home\OneDrive\Documents\Firaxis ModBuddy\ZeroSis' Engine Modernization\tools\build_sdk_incremental.py" --arch x64
python "C:\Users\home\OneDrive\Documents\Firaxis ModBuddy\ZeroSis' Engine Modernization\tools\build_sdk_incremental.py" --arch x86
```

`--jobs 2`를 추가하면 편집 중 컴파일의 CPU 사용량을 낮출 수 있다. 기본값은 최대 4개이며 MSBuild 프로젝트 병렬도는 1개로 고정하여 중첩 병렬 실행을 피한다. `--rebuild`는 이 도구의 전용 OBJ/PCH만 재생성한다. 프로젝트·PCH·OBJ·의존성 기록은 `Build/SDKIncremental/x86` 또는 `x64`에 유지한다. 같은 출력 폴더를 사용하는 동시 실행은 잠금으로 거부한다.

이 진입점은 **컴파일 전용**이다. DLL 링크·게임 설치·MODS 배포는 기존 절차로 수행해야 한다. 기존 x86 SDK의 v90/Win32 ABI와 최적화 설정, x64 포트의 검증된 MSVC 14.44.35207·`/Od`·`/MD`·`/fp:strict` 설정을 유지한다. 개발용 x86 사본에서는 정적 분석을 끄지만 원래 검증용 프로젝트와 분석 관문은 보존한다. 새 결과를 기존 accepted 보고서 또는 Stage의 공식 산출물로 승격하지 않는다.

## 2026-10-02 검증 결과

실제 BNW SDK 161개 translation unit을 x86·x64 각각 컴파일했고, COFF 아키텍처와 수치 경고 관문을 통과했다. 아래 시간은 입력·출력 해시 확인과 컴파일을 포함하는 도구 내부 측정 구간이며 Python 시작·프로젝트 준비 시간은 제외한다.

| 대상 | 최종 무변경 확인 구간 | MSBuild 구간 | 재컴파일 | 재사용 |
|---|---:|---:|---:|---:|
| x64 | 3.385초 | 0.548초 | 0개 | 161개 |
| x86 | 4.407초 | 0.927초 | 0개 | 161개 |

전체 재컴파일을 수행한 실행도 각각 통과했다. 측정은 한 차례의 로컬 관측이며 다른 작업과 파일 캐시의 영향을 포함한다. 전체 재빌드 향상률이나 게임 실행 성능의 근거로 확대하지 않는다. 핵심 개선은 **변경 없는 161개 파일의 재컴파일을 생략하는 것**이다.

실제 MSVC를 사용하는 별도 작은 C++ fixture에서 18개 검증 항목을 통과했다. CPP 하나 변경 시 해당 객체만, 개별 헤더 변경 시 해당 소비자만, PCH의 간접 헤더 변경 시 PCH와 모든 소비자가 재컴파일되었다. 수정 시간을 되돌린 내용 변경·OBJ 누락과 손상·PCH 손상·컴파일 실패와 복구·헤더 삭제와 복구·컴파일 옵션 변경·동시 실행·출력 폴더 밖 파일 보호도 확인했다. 마지막에는 fixture 객체를 실제 링크·실행하여 변경한 상수 값이 들어 있는지 확인했다. 게임 런타임 시험은 아니다.

- [보존 확인 및 최종 요약](../evidence/sdk_incremental/summary.json): 설치 SDK 원본 1,105개와 원본 사본의 SHA-256 일치, 생성된 x64 SDK 파일·attempt_037의 객체·컴파일 명령·기존 빌더 해시 보존.
- [x64 최종 실행](../evidence/sdk_incremental/x64/20261002T124115Z_fa13c52dc045/build_result.json)
- [x86 최종 실행](../evidence/sdk_incremental/x86/20261002T124009Z_a5b4ee8a93a6/build_result.json)
- [의존성·복구 검증](../evidence/sdk_incremental/validation/20261002T123744Z_4d75905740c1/conformance.json)

## 긴 코드의 편집 렉

현재 포트의 `CvDiplomacyAI.cpp`는 1,015,685바이트, `CvPlayer.cpp`는 760,704바이트다. 크기는 원인 후보이며 실제 지연의 원인으로 확정하지 않았다. 소스를 임의로 나누거나 함수·게임 동작을 변경하지 않았다.

프로젝트 루트의 `Open-SDK-Editor.cmd`를 실행하면 설치된 VS Code로 `SDK-Fast-Edit.code-workspace`를 연다. `--disable-extensions`와 `%TEMP%/ZeroSis-SDK-Fast-Edit`의 별도 사용자 프로필을 사용하며 전역 설정·확장 설치 상태는 변경하지 않는다. 해당 프로필의 세션·편집기 이력은 임시 폴더 정리 시 사라질 수 있으므로 작업은 일반 소스 파일에 직접 저장한다. `Ctrl+Shift+B`는 x64 증분 컴파일이며 작업 목록에서 x86 컴파일도 선택할 수 있다.

워크스페이스는 Build·Stage·evidence·원본 SDK 사본·ThirdParty를 검색과 파일 감시에서 제외한다. 의미 기반 강조·CodeLens·미니맵·sticky scroll·괄호 색상·인라인 제안·입력 중 서식화를 끄고, 긴 한 줄의 토큰화 상한을 2,000자로 줄였다. VS Code의 큰 파일 최적화는 유지하고 접기는 들여쓰기 기반으로 제한했다. 자동 완성·확장 기반 진단이 필요한 경우에는 기존 편집 프로필을 사용한다.

JSON·PowerShell 구문, 설치된 VS Code 1.124.2의 설정 키와 실행 파일을 확인했다. **편집기 GUI 실행, 긴 코드에서의 실제 키 입력·스크롤 지연, ModBuddy 자체의 편집 렉 해결은 아직 검증하지 않았다.** 현재 사용하는 편집기와 지연이 발생하는 파일이 확인되면 그 환경에서 원인을 좁혀야 한다.

## 구현 파일과 회귀 범위

- `tools/build_sdk_incremental.py`: 별도 개발용 프로젝트 생성, 증분 컴파일, 해시 보완, 전용 출력 잠금·복구, 실행별 보고서.
- `Tests/verify_sdk_incremental.py`: 실제 컴파일러·PCH·링커로 의존성 및 복구 동작 검증.
- `SDK-Fast-Edit.code-workspace`, `tools/Open-SDK-Editor.ps1`, `Open-SDK-Editor.cmd`: 별도 편집 프로필 및 컴파일 작업.
- 이 문서: 요구사항·실측·검증 범위·사용법.

컴파일러와 Windows SDK 경로·버전은 현재 설치 환경에 맞춰 고정했다. 다른 PC 또는 도구 버전 변경 시 검토가 필요하다. 새 헤더가 생기거나 삭제된 경우에는 include 검색 우선순위 변화에 대비하여 전용 객체를 보수적으로 모두 재컴파일한다. 기존 Source → Build → Stage/MODS 검증과 실게임 새 게임·턴 진행·저장/불러오기·UI/로그 관문은 이 개발 도구의 통과 결과로 대체하지 않는다.

공식 참고: [MSBuild 증분 빌드](https://learn.microsoft.com/en-us/visualstudio/msbuild/incremental-builds?view=vs-2022), [MSVC 병렬 컴파일](https://learn.microsoft.com/en-us/cpp/build/reference/mp-build-with-multiple-processes?view=msvc-170), [VS Code 명령행과 별도 사용자 프로필](https://code.visualstudio.com/docs/configure/command-line).
