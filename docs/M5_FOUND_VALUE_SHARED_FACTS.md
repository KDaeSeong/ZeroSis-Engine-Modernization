# FoundValue 공유 입력 후보

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
