# FoundValue 공유 입력 후보

## 2026-11-21 개척지 점수의 후보별 타일 복사 제거

`ZeroSisFoundValueEvaluateSharedBatch`의 워커는 게임 스레드가 복사·검증한 지도 타일을 직접 읽습니다. 원본처럼 `dx`를 바깥 루프, `dy`를 안쪽 루프로 두고 후보의 225개 슬롯을 방문합니다. 같은 지도 타일을 다시 만나도 해당 슬롯의 거리와 거리별 전략 점수를 사용합니다. 직렬 dense 입력과 공유 입력은 같은 정수 연산을 거칩니다. SDK 호출부는 모든 결과를 원본 직렬 함수와 대조한 뒤 지도 순서대로 적용합니다. [공유 입력 조회](../Source/Concurrency/FoundValueSharedScores.h) · [점수 계산](../Source/Concurrency/FoundValueScores.h) · [SDK 적용 경로](../Source/Concurrency/FoundValueSharedSdkCapture.inc)

기준 커밋 `86ef92a`와 수정본의 실제 공유 브리지를 MSVC 14.44 x64 `/O2`로 컴파일했습니다. 기준 워커는 후보마다 13,656바이트 `Snapshot`을 `memcpy`한 뒤 225개 타일 슬롯을 다시 채웠습니다. 수정본은 이 두 작업을 제거했습니다. 건설 가능한 후보는 점수 순회 한 번으로 처리하고, 건설 불가 후보는 입력 유효성 검사를 마친 뒤 점수 0을 반환합니다. 측정 대상은 워커 내부의 복사량과 순회 횟수입니다. [수정 전 어셈블리](../Build/FoundValueSlotScan/before/bridge.asm) · [수정 후 어셈블리](../Build/FoundValueSlotScan/after/bridge.asm)

| 검증 범위 | 빌드·실행 결과 | 기록 |
|---|---|---|
| Civ V SDK 없이 실행한 공유 C ABI | 일반 후보 48개와 경계 후보 4개에서 호출 스레드의 직렬 커널과 워커 1·2·4개의 순서별 정수 점수가 일치했습니다. `/O2`와 `/Od` 각각 84개 검사를 통과했습니다. | [검사](../tools/verify_found_value_shared_bridge.py) · [결과](../evidence/found_value_shared_bridge/20261121T095607Z_5e83bc1ada/conformance.json) |
| Civ V SDK 없이 실행한 dense C ABI | 기존 입력 형식의 회귀 검사 11개가 `/O2`와 `/Od`에서 각각 통과했습니다. | [검사](../tools/verify_found_value_score_bridge.py) · [결과](../evidence/found_value_score_bridge/20261121T095607Z_2283aabe6d/conformance.json) |
| Civ V SDK 없이 실행한 수정 전후 커널 | 고정 시드 `0x72a2f11d`의 읽기 전용 후보 512개에서 이전 dense 직렬 점수와 수정 후 직렬·공유 워커 1·2·4개의 점수를 인덱스별로 비교했습니다. 불일치는 0건입니다. | [재현 스크립트](../evidence/found_value_shared_bridge/slot_scan/compare_revision.py) · [전후 비교 기록](../Build/FoundValueSlotScan/comparison.json) |
| 원본 BNW 함수 본문과의 대조 | 원본·x64 경로의 `CvSiteEvaluationClasses.cpp`가 저장소 명세의 SHA-256과 일치했습니다. 기본·개척자 `PlotFoundValue` 본문을 추출하고 테스트가 공급한 타일 관측값으로 실행했습니다. `/O2`와 `/Od`에서 공유 커널은 각각 530개, dense 커널은 각각 533개 검사를 통과했습니다. | [원본 명세](../patches/sdk-bnw-inputs.json) · [공유 커널 결과](../evidence/found_value_shared_scores/20261121T095913Z_fd82444397/conformance.json) · [dense 커널 결과](../evidence/found_value_scores/20261121T095717Z_8369df0afa/conformance.json) |
| SDK 캡처 코드의 모의 실행 | 소유 스레드에서 관측값을 수집하고 결과를 순서대로 적용하는 경로가 `/O2`와 `/Od`에서 각각 49개 검사를 통과했습니다. | [캡처 검사 결과](../evidence/found_value_shared_sdk_capture/20261121T100059Z_7e99b93127c0/conformance.json) |

거리 1을 중심보다 먼저 방문한 경계 입력은 50점, 거리 4를 먼저 방문한 입력은 40점입니다. 앞 슬롯에서 계산한 신앙값이 중심과 거리 4·5에 이어지는 원본 동작을 두 함수 본문과 대조했습니다. 공유 브리지에서는 같은 지도 인덱스를 반복 참조한 경우와 호출 전후 입력 바이트도 확인했습니다. 마지막 슬롯의 전략 점수가 오버플로하면 앞 후보까지 포함해 출력 전체가 보존되고, 건설 불가 후보의 잘못된 슬롯은 워커 시작 전에 거부됩니다. [브리지 경계 검사](../Tests/found_value_shared_bridge.cpp) · [원본 함수 대조 사례](../Tests/found_value_shared_scores.cpp)

11월 21일 검증은 구성요소 실행까지였습니다. 11월 22일에는 별도 x64 GameCore와 헤드리스 Host를 연결해 그리스·로마 2→4턴을 측정했습니다. 아래의 2026-10-02 SDK 실행과 CPU 추적은 당시 커널에 대한 기록이며, 해당 후보 빌더는 당시 두 커널의 SHA-256을 고정합니다. [전체 턴 실측과 재현 조건](M5_FULL_TURN_BENCHMARK.md)

## 2026-10-02 공유 입력 SDK 후보

기존 FoundValue 후보에서 후보마다 225개 타일의 관측값을 복사하던 경로를, 호출마다 한 번 수집한 공통 설정과 지도 타일 관측값 및 후보별 인덱스·거리 배열로 바꿨사와요. 별도 후보를 사용하며 기존 dense 후보와 활성 SDK·Stage·MODS는 보존했답니다.

## 구현과 저장 경계

게임 스레드가 GameCore 잠금 아래 SDK 객체와 helper를 읽고, [FoundValueSharedSdkCapture.inc](../Source/Concurrency/FoundValueSharedSdkCapture.inc)가 소유 값 배열을 구성한답니다. [FoundValueSharedBridge.h](../Source/Concurrency/FoundValueSharedBridge.h)의 C++14 경계는 공통 설정 240바이트, 지도 타일당 116바이트, 후보당 1,848바이트랍니다. [FoundValueSharedBridge.cpp](../Source/Concurrency/FoundValueSharedBridge.cpp)가 호출자의 배열을 한 번 복사하고 모든 참조를 검증한 뒤, worker에는 후보 인덱스와 불변 소유 배열만 전달하와요.

후보의 225개 슬롯은 원본의 dx-major·dy-minor 순서를 유지하며, 잘린 좌표의 missing sentinel과 감긴 지도의 중복 참조를 보존한답니다. 같은 타일도 거리별 strategic 값이 다를 수 있어 거리 1–5 값을 따로 수집하와요. [FoundValueSharedScores.h](../Source/Concurrency/FoundValueSharedScores.h)는 worker 스택에서 dense 관측값을 구성해 기존 [FoundValueScores.h](../Source/Concurrency/FoundValueScores.h)로 계산하므로, 원본 faith carry와 순회 순서도 유지한답니다. worker에서의 dense 구성 비용은 여전히 존재하와요.

모든 점수를 원본 scalar 함수와 shadow 비교하고 area 합의 범위를 검사한 뒤, 게임 스레드가 원본 순서대로 setter를 호출하와요. 검증 이전 실패는 map·area setter 호출 전에 중단되며 setter 자체의 rollback 계약을 추가한 것은 아니랍니다. 저장 키·형식·Mod ID·버전·밸런스는 변경하지 않았사와요.

## 구성요소와 실제 SDK 연결

- [공유 커널 원본 함수 대조](../evidence/found_value_shared_scores/20261002T154249Z_2930c8a3f4/conformance.json): O2/Od 각각 529 검사와 생성 후보 512개를 통과했사와요.
- [C++14/C++17 연결부](../evidence/found_value_shared_bridge/20261002T152931Z_bbc131426b/conformance.json): O2/Od 각각 66 검사를 통과했사와요. 잘못된 참조·범위 중첩·late overflow·빈 배치와 owner TLS 배치 ID도 확인했답니다.
- [SDK capture exact-body mock](../evidence/found_value_shared_sdk_capture/20261002T154334Z_a5e3d787e2b9/conformance.json): O2/Od 각각 49 검사로 SDK 읽기·helper cache·순서 있는 적용과 진단 경계를 확인했사와요. 앞의 세 proof는 구성요소 검증이며 GameCore를 실행하지 않았답니다.
- [실제 shared SDK 링크](../evidence/found_value_shared_sdk/20261002T154635Z_480d61cc2900/build_result.json): SDK 객체 두 개와 새 연결부를 기존 객체에 연결했사와요. 최종 컴파일은 동결한 471개 dependency records만 읽었고 SDK 경고는 대응하는 원본 컴파일의 7개와 각각 같았으며 새 연결부·링크 경고는 0이랍니다. PCH·전체 SDK를 복제하지 않았사와요.

## 진단과 검증 범위

`ZEROSIS_FOUND_VALUE_LAYOUT`은 기존 VALUES·AREAS·TRACE의 연속 세 줄 다음에 기록되며, 호출당 C 입력의 논리적 크기는 `240 + 116 × 지도 타일 수 + 1848 × 후보 수`랍니다. 기존 dense 입력과 비교할 크기는 `19140 × 후보 수`이와요. 작은 호출에서는 지도 배열 비용이 더 클 수 있으며, 이 크기 차이는 속도 향상의 증거가 아니랍니다.

worker 기본값은 0이고 CPU trace도 기본 꺼짐이랍니다. runner의 `--found-value-layout shared`가 별도 SDK 후보를 고르며, `--found-value-cpu-trace`는 공유 후보·worker 4·save/restore의 명시적 진단 설정에서만 켜지와요. 상속된 trace 변수는 제거하고 실제 주입값을 요청과 결과에 따로 기록하와요. 배치 ID는 SDK 세션이 새로 시작돼도 구별할 수 있는 QPC 기반 값으로, 호출 ID와 별도로 대조한답니다.

## 실제 영어·한국어 50턴 행렬

[공유 입력 strict conformance](../evidence/found_value_shared_sdk_runtime/20261002T155959Z_f8b7cb268407/conformance.json)는 영어·한국어 × worker 0/1/2/4의 여덟 실행을 통과했사와요. 각 실행은 50턴과 새 SDK 세션에서의 native 저장 복원을 포함하며, 현재 공유 후보 DLL SHA-256은 `a58a0d20cbaecad13ea248fe362d0c15bb97096802b9f60c5ef5f0dd8bb90c07`이랍니다. 활성 모드는 모두 0개였사와요.

| 언어 | worker | 실행 ID | 결과 |
|---|---:|---|---|
| 영어 | 0 | `20261002T154859Z_8e35b68dfaa0` | PASS, 50턴 |
| 영어 | 1 | `20261002T155552Z_a284158aed7f` | PASS, 50턴 |
| 영어 | 2 | `20261002T155553Z_75aa832ed50a` | PASS, 50턴 |
| 영어 | 4 | `20261002T155207Z_5901a7fd1d28` | PASS, 50턴 |
| 한국어 | 0 | `20261002T154859Z_9a0300a58243` | PASS, 50턴 |
| 한국어 | 1 | `20261002T155552Z_4fc1c34dc8f8` | PASS, 50턴 |
| 한국어 | 2 | `20261002T155553Z_3b55d364248b` | PASS, 50턴 |
| 한국어 | 4 | `20261002T155207Z_38c434218a11` | PASS, 50턴 |

총 1,600회 평가와 1,536,000개 ordered plot 점수 및 source-order area totals를 직접 대조했사와요. 같은 언어의 worker 0 대비 1/2/4는 세 native archive, continuation 상태·이벤트 및 공식 UI 난수가 같았답니다. 공유 후보의 직렬 실행도 기존 dense 후보의 같은 언어 직렬 실행과 대조했으며, 기존 정책의 지도 GUID 16바이트 정규화와 정확한 GameCore bundle hash 행의 치환을 제외하면 비교 결과가 같았사와요. 언어 간 archive 전체 바이트 동일성은 이 결과의 주장이 아니랍니다.

worker 실행 여섯 개의 1,200개 LAYOUT 기록은 호출 ID·배치 ID·job 수와 크기 공식을 통과했사와요. C 경계의 합산 논리 입력은 공유형 377,589,888바이트, 대응 dense형 2,523,723,840바이트로 **85.04% 작았답니다**. 실제 프로세스 메모리의 감소량, 전체 복사량 또는 속도 향상률을 뜻하는 수치는 아니와요. worker 스택의 dense 구성과 필수 scalar shadow는 여전히 실행한답니다.

## 별도 실제 CPU 추적과 남은 관문

[FoundValue 전용 CPU reader 구성요소](../evidence/found_value_cpu_trace/20261002T151042Z_0d8765878529/conformance.json)의 오프라인 검증에 이어, 같은 공유 SDK의 별도 영어 worker 4 실행에서 실제 ETL을 보존했사와요. [strict CPU proof](../evidence/found_value_cpu_capture/validators/20261002T161959Z_fa946449f9d9/conformance.json)는 SDK의 비어 있지 않은 199개 배치와 21,976개 작업을 ETW marker에 연결하고 worker 수명·CSwitch·capture-time topology를 대조했답니다. 손실 이벤트는 0개이며, 서로 다른 물리 코어의 원시 겹침 128 QPC틱에서 양끝 한 틱씩을 제외한 126틱, 즉 12.6마이크로초가 남았사와요. [추적의 입력·검증·정확한 범위](M5_FOUND_VALUE_CPU_TRACE.md)

물리 병렬 실행은 이 FoundValue 커널 작업의 CPU 스케줄 구간 범위에서 확인했사와요. mandatory shadow 비용이 포함된 진단 시간을 benchmark로 사용하지 않으며, 전체 턴의 반복 성능과 전체 GameCore 동등성은 남아 있답니다. 기존 [기본 환경 EN/KO proof](../evidence/found_value_default_environment/20261002T142850Z_a9c46a490e0b/conformance.json)는 dense 후보의 별도 이력이므로 공유 후보의 unset 환경 실행으로 환산하지 않사와요. retail 저장, 렌더링·입력·오디오, 비어 있지 않은 mod 세션과 Stage 승격도 별도로 남아 있답니다.

## 테스트 실행 오류 정정

사용자가 보고한 `Build/FoundValueSharedScores/20261002T151050Z_ba42510ade/optimized/found_value_shared_scores.exe`는 개발용 원본 비교 테스트였사와요. 중복 타일 fixture에서 `center + 1/+2`를 잘못 선택해 missing sentinel을 벡터 인덱스로 사용하면서 access violation이 발생했답니다. 원본 순회의 실제 슬롯 127·142를 사용하고 sentinel·범위·거리를 검사하도록 고쳤으며, 수정 후 O2/Od 검증을 통과했사와요. 이전 실패 산출물은 보존하고 재실행하지 않았답니다.
