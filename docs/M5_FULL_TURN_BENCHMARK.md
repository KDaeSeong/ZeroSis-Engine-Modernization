# BNW GameCore 전체 턴 측정

**그리스·로마 초반 두 턴에서는 직렬 모드가 네 반복 모두 가장 빨랐습니다.** 같은 반복에서 두 턴 시간을 합친 뒤 비교하면 1·2·4워커가 직렬보다 각각 중앙값 5.292ms, 12.999ms, 6.297ms 더 걸렸습니다. 이 구간의 SDK 스냅샷에는 도시가 0개였습니다. 중후반 지도와 기존 미국·로마 규칙 DB의 성능은 별도 측정 대상입니다. [측정 도구](../tools/benchmark_bnw_turns.py) · [독립 검증 도구](../tools/verify_full_turn_benchmark.py)

## 턴 시간

단위는 밀리초입니다. 각 셀은 중앙값과 괄호 안의 최소–최대입니다. 모드마다 독립 시간 측정 프로세스 4개에서 같은 두 턴을 측정해 **턴별 4개, 모드별 8개, 전체 32개** 표본을 얻었습니다. 두 턴 합계는 각 프로세스 안에서 구한 값으로 집계했습니다.

| FoundValue 워커 | 2→3턴 | 3→4턴 | 두 턴 합계 | 합계의 중앙절대편차 |
|---|---:|---:|---:|---:|
| 0 (직렬) | 24.965 (23.749–26.202) | 23.777 (23.085–23.959) | 48.514 (47.377–50.072) | 0.972 |
| 1 | 28.261 (25.094–37.538) | 25.816 (25.228–39.795) | 53.806 (50.862–77.333) | 2.192 |
| 2 | 32.645 (27.820–35.547) | 29.220 (25.595–32.173) | 61.348 (56.646–65.523) | 3.995 |
| 4 | 28.339 (27.473–29.256) | 26.430 (25.858–28.964) | 54.645 (53.578–58.220) | 0.626 |

FoundValue 상세 로그를 끄고 시간을 잰 프로세스 16개와 로그를 켠 진단 프로세스 4개에서 총 40개 SDK 세션을 대조했습니다. 20개 프로세스에서 초기·복원·턴별 상태, 명령 수신 순서, 동기 난수와 최종 저장이 일치했습니다. 2턴 시작·3턴 시작·4턴 진입 시 동기 난수는 각각 `3870627774`, `243226600`, `246333258`이었습니다. 진단에서 1·2·4워커 설정은 각각 두 턴에 걸쳐 총 279개 후보 작업을 완료했고, 지도 점수 및 지역 합계가 직렬과 일치했습니다. [상태·난수·명령 및 저장 검증 코드](../tools/verify_full_turn_benchmark.py)

각 반복의 원시 타이머 값은 마이크로초이며 셀 안의 순서는 2→3턴, 3→4턴입니다.

| 반복 | 0 (직렬) | 1워커 | 2워커 | 4워커 |
|---|---:|---:|---:|---:|
| 1 | 24292, 23085 | 25094, 25768 | 31939, 25595 | 28958, 25871 |
| 2 | 23749, 23959 | 27139, 25228 | 33350, 32173 | 29256, 28964 |
| 3 | 25637, 23683 | 29382, 25863 | 35547, 29614 | 27473, 26988 |
| 4 | 26202, 23870 | 37538, 39795 | 27820, 28826 | 27720, 25858 |

## 진단 로그의 FoundValue 시간

단위는 **µs**입니다. 모드당 상세 추적을 켠 프로세스 1개에서 2→3턴과 3→4턴을 합산했습니다. 복원된 세션의 각 `BENCH_BEGIN`과 `BENCH_END` 사이에는 FoundValue 호출이 4개씩 있었습니다. 각 병렬 모드가 완료한 후보 작업은 첫 턴 127개, 다음 턴 152개입니다.

| 워커 | 관측 수집 | 워커 호출 | 직렬 대조 | 합산·반영 | 세부 타이머 밖 | FoundValue 전체 | 진단 턴 전체 |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | — | — | — | — | 1,826 | 1,826 | 201,537 |
| 1 | 1,526 | 2,050 | 2,167 | 86 | 75 | 5,904 | 259,204 |
| 2 | 1,161 | 2,100 | 2,018 | 86 | 65 | 5,430 | 223,252 |
| 4 | 1,077 | 2,946 | 1,685 | 189 | 62 | 5,959 | 186,527 |

관측 수집부터 합산·반영까지 네 열은 SDK가 순서대로 잰 `snapshot_us`, `worker_us`, `shadow_us`, `reduction_us`입니다. 관측 수집은 게임 스레드가 지도와 후보 입력을 만드는 구간입니다. 워커 호출은 브리지의 입력 복사·검증, 작업 실행·조인 대기, 결과 반환을 포함합니다. 계산과 대기의 개별 시간 및 스레드별 CPU 시간은 기록되지 않습니다. 브리지 내부의 `worker_batch_us`도 이 로그에는 출력되지 않습니다. 직렬 대조에는 후보마다 원본 `PlotFoundValue` 재계산, 점수 비교와 임시 결과 기록이 들어갑니다. 지역 합산과 지도·지역 반영도 한 타이머를 공유합니다. [SDK의 구간 경계](../Source/Concurrency/FoundValueSharedSdkCapture.inc) · [워커 브리지](../Source/Concurrency/FoundValueSharedBridge.cpp)

FoundValue 전체는 각 호출에서 워커 수를 확인하기 직전부터 상세 로그 출력 직전까지 잰 `total_us`의 합계입니다. 세부 타이머 밖의 값은 여기서 네 구간을 한 번씩 뺀 차이입니다. 직렬 경로에는 전체 타이머만 있어 1,826µs 전체가 미분해입니다. 1워커에서 원본 대조는 FoundValue의 36.7%였고, 4워커에서 워커 호출은 49.4%였습니다. [직렬 타이머](../tools/build_found_value_shared_sdk_candidate.py)

진단 턴 전체는 같은 프로세스의 `EXTENDED_TURN_CYCLE_DURATION_US` 합계입니다. 여기에는 FoundValue 타이머가 끝난 뒤의 상세 로그 출력도 들어갑니다. 이 진단 턴에서 FoundValue 계측 구간이 차지한 비율은 0·1·2·4워커 순으로 0.91%, 2.28%, 2.43%, 3.19%였습니다. 위의 추적을 끈 32개 표본에서 단계별 소요 시간은 관측되지 않았습니다. [Host 턴 타이머](../Source/Host/FirstTurnProbe.h)

아래 명령은 로컬 측정의 `result.json`과 `verify-{0,1,2,4}/stdout.log` 네 개를 읽어 이 표를 출력합니다. `--json`을 붙이면 턴별 시간과 호출·작업 수도 출력합니다. [분석 도구](../tools/analyze_found_value_phases.py) · [집중 검사](../Tests/full_turn_benchmark.py)

```powershell
& 'C:/Python314/python.exe' tools/analyze_found_value_phases.py evidence/full_turn_benchmark/20261121T154000Z_518f4da7d6/result.json
```

## 실행 조건

2026년 11월 22일에 실시간 렌더링 없이 Windows x64 Host와 BNW GameCore를 연결했습니다. 측정 대상은 그리스 인간 플레이어가 2턴을 끝내고 3턴을 돌려받는 구간과, 3턴을 끝내고 4턴을 돌려받는 구간입니다. 같은 DLL에서 FoundValue 워커 수만 0·1·2·4로 바꿨습니다. 0은 원본 SDK의 직렬 경로이고, 워커 경로에는 게임 스레드의 관측값 수집, 워커 실행·대기, 원본 직렬 함수와의 대조, 결과 반영 비용이 포함됩니다. 탐색과 도시 특화 평가의 워커 수는 모두 0입니다.

| 조건 | 이번 실행에 사용한 값 |
|---|---|
| 지도·시드 | Continents, Duel 40×24, 지도 `0x5A17C0DE`, 동기 난수 `0x0BADC0DE` |
| 세력·언어 | 인간 그리스·알렉산더, AI 로마·아우구스투스, 도시 국가 2개, 야만인, `en_US` |
| 규칙 입력 | 설치 환경의 `Civ5DebugDatabase.db` 읽기 전용 원본에서 복사. SHA-256 `05f9ec7fd8c4919f8f00a3a031aa24280c523387aad319daed4e1c95a257968d`. 문명 100·유닛 435·건물 749개, 자원 설정 5(전략적 균형). 시뮬레이션에서 별도로 활성화한 모드는 0개 |
| 실행본 | MSVC 14.44 x64 `/O2 /MD /fp:strict`. BNW 오브젝트 161개와 브리지 4개를 연결. Host SHA-256 `cbf0c1b3e028e738068adc601933db8dc36e759ffc60529974d244bb2bf46d56`, GameCore SHA-256 `21a42e859ef33dea48e4cadbf061f1ba0957e8b710c7e9e92436eeca8acf484c` |
| 장비 | Windows 11 빌드 26300, AMD Ryzen 7 7800X3D, 논리 프로세서 16개, 고해상도 카운터 주파수 10 MHz. 별도 렌더러 부하 검사를 종료한 뒤 순차 실행 |

이 설치의 캐시에는 VP 모드팩 데이터가 들어 있으며 미국·워싱턴의 `Playable`은 0입니다. 과거 기록의 미국·로마와 문명 45·유닛 148·건물 140개 조건을 재현하려면 그 조건의 규칙 DB가 필요합니다. 이번 비교에서는 실제 DB에서 플레이 가능한 그리스를 명시했습니다. 원본 지도 Lua와 옵션 DB에는 자원값 5가 등록되어 있어 Host가 해당 옵션의 1–6 범위와 등록값을 함께 검증하도록 했습니다. 새 게임의 그리스 유닛 3개는 SDK에서 직접 열거하고 실제 명령을 받은 유닛 ID와 순서를 대조했습니다.

## 시계와 동등성

`FirstTurnProbe::AdvanceOneTurn`이 정상 유닛 대기 명령과 턴 종료 명령을 준비하기 직전부터, 실제 `ICvGame1::Update()`가 AI 처리를 마치고 다음 인간 턴을 활성화할 때까지 `steady_clock`으로 잽니다. 정상 턴 제어, SDK 콜백, 프레임 로그와 유닛 명령 ID 수집은 이 구간에 들어갑니다. 프로세스 시작, 지도 생성, 저장·복원, 이후 유휴 업데이트 3회, 상태 파일 쓰기와 결과 검증은 구간 밖에서 수행합니다. [Host 타이머](../Source/Host/FirstTurnProbe.h)

현재 SDK의 워커 경로는 계산된 후보마다 원본 `PlotFoundValue`를 직렬로 한 번 더 호출하고 점수를 대조한 뒤 지도에 반영합니다. 상세 로그를 끈 시간 표본에도 이 대조 비용이 포함됩니다. [SDK의 점수 대조](../Source/Concurrency/FoundValueSharedSdkCapture.inc)

각 프로세스가 같은 시드로 새 게임을 시작해 1턴에 저장하고 GameCore를 언로드합니다. 새 SDK 세션에서 그 저장을 복원하고 2턴까지 진행한 뒤 표본을 수집합니다. 두 측정 턴 모두 `PLAYEROPTION_WAIT_END_TURN`을 켜고 유닛 8192, 16385, 24578 순서로 `MISSION_SKIP(-1,-1,0,0,1)`을 실행한 뒤 `CONTROL_ENDTURN`을 전달했습니다. 준비 턴 0→1에서 발생한 황금기 알림은 설치본의 `GoldenAgePopup.lua`가 열고 Escape로 닫았습니다. 이때 실제 SDK 턴 타이머의 증가·감소와 동기 난수 보존을 확인했습니다. [황금기 알림의 헤드리스 실행](../Source/Host/TurnBenchmarkGoldenAge.h)

모드별 첫 실행은 FoundValue 점수·지역 합계·실제 작업 검증용입니다. 시간 표본은 이 추적을 끈 별도 프로세스에서 얻습니다. 반복마다 순서를 0·1·4·2, 1·2·0·4, 2·4·1·0, 4·0·2·1로 바꿉니다. 각 실행의 원본 명령 수신 순서, 양쪽 경계의 동기 난수, 프레임과 SDK 상태 스냅샷, 최종 저장의 133개 구획을 같은 직렬 기준과 대조합니다. 독립 새 게임의 지도 GUID 16바이트만 기존 저장 비교 규약대로 정규화합니다. [실행 및 집계](../tools/benchmark_bnw_turns.py) · [독립 재검사](../tools/verify_full_turn_benchmark.py)

## 재현

이 작업 폴더에는 위 실행에 사용한 V4 입력 묶음이 있습니다. 저장소 루트에서 다음 명령을 실행하면 새로운 전용 디렉터리와 세션을 사용합니다.

```powershell
& 'C:/Python314/python.exe' tools/benchmark_bnw_turns.py --bundle Build/FullTurnBenchmark/golden-inputs --human CIVILIZATION_GREECE --language en_US --start-turn 2 --stop-turn 4 --repeats 4
```

아래 예시의 실행 ID는 이 작업 폴더에서 측정한 값입니다. 새 체크아웃에서는 벤치마크가 출력한 로컬 결과 경로를 사용합니다. 16개 시간 측정과 4개 진단의 자식 프로세스 로그, 세션별 SDK 파일, 원본 명령열을 다시 읽고 표의 통계를 재계산합니다.

```powershell
& 'C:/Python314/python.exe' tools/verify_full_turn_benchmark.py evidence/full_turn_benchmark/20261121T154000Z_518f4da7d6/result.json
```

새 체크아웃에서는 프로젝트 명세와 해시가 일치하는 원본·수정 SDK 각 1,105개 파일이 필요합니다. 아래 예시는 이 머신의 설치 경로를 사용합니다. 빌더는 고정 버전 SQLite 3.7.17과 ICU 4.4.2, 공유 Lua, 현지화·DB 제공자, BNW 및 Host를 구성합니다. 입력 준비 도구는 설치 게임의 ICU 자료·음향 XML·Lua와 두 DB를 전용 폴더에 복사하며 기존 파일과 해시가 다르면 중단합니다. [빌더](../tools/build_full_turn_runtime.py) · [입력 준비](../tools/prepare_full_turn_inputs.py)

```powershell
$gameDir = "D:/Program Files (x86)/Steam/steamapps/common/Sid Meier's Civilization V"
$cacheDir = "D:/Documents/My Games/Sid Meier's Civilization 5/cache"
& 'C:/Python314/python.exe' tools/build_full_turn_runtime.py all --icu-data "$gameDir/Locale/icudt44l.dat"
& 'C:/Python314/python.exe' tools/prepare_full_turn_inputs.py --game $gameDir --cache $cacheDir --modules Build/FullTurnBenchmark/modules --golden-age --output Build/FullTurnBenchmark/golden-inputs
```
