# M5: 도시 부지 점수의 FoundValue 경로

이 문서는 기존 dense 입력 후보의 구현·행렬·기본 환경 이력을 보존하와요. 후속 공유 입력 후보는 별도의 영어·한국어 0/1/2/4 행렬과 FoundValue 전용 실제 CPU trace를 통과했사와요. 현재 후보의 결과는 [공유 입력 구현과 실제 행렬](M5_FOUND_VALUE_SHARED_FACTS.md) 및 [물리 코어 추적](M5_FOUND_VALUE_CPU_TRACE.md)에 있답니다. 아래의 물리 코어 미검증 표기는 이 dense 행렬 자체의 범위랍니다.

2026-10-02 기준, FoundValue 계산을 실제 격리 x64 GameCore 후보에 연결하고 영어·한국어에서 작업자 0개·1개·2개·4개 설정을 각각 50턴 실행했사와요. 8개 실행 모두 native save/restore와 extended-turn 검증을 통과했고, 각 언어에서 worker 0 대비 1/2/4의 모든 ordered plot 점수와 원본 순서 area totals가 같았답니다. 현재 후보 GameCore SHA-256은 `cd1ef26f07e39b82dc2108e79dbd927eff4215662cc3bd8a01e1c3c33587814b`이며, 실행은 모두 활성 모드 수 `[0, 0]`이랍니다. [FoundValue SDK 후보 빌드](../evidence/found_value_sdk/20261002T133605Z_155601e32d67/build_result.json) · [8개 런 strict conformance](../evidence/found_value_sdk_runtime/20261002T141124Z_727921886bfd/conformance.json)

| 언어 | 요청 작업자 | 실행 ID | 실제 SDK 런 결과 |
|---|---:|---|---|
| 영어 (`en_US`) | 0 | `20261002T133819Z_83f867de0f55` | PASS, 50턴, 200회 FoundValue 평가 batch |
| 영어 (`en_US`) | 1 | `20261002T135739Z_f561335d9203` | PASS, 50턴, 200회 FoundValue 평가 batch |
| 영어 (`en_US`) | 2 | `20261002T140152Z_c602469b7e08` | PASS, 50턴, 200회 FoundValue 평가 batch |
| 영어 (`en_US`) | 4 | `20261002T134005Z_8e8ffaed79ed` | PASS, 50턴, 200회 FoundValue 평가 batch |
| 한국어 (`ko_KR`) | 0 | `20261002T134236Z_1623790d32da` | PASS, 50턴, 200회 FoundValue 평가 batch |
| 한국어 (`ko_KR`) | 1 | `20261002T135954Z_023ffdc07e27` | PASS, 50턴, 200회 FoundValue 평가 batch |
| 한국어 (`ko_KR`) | 2 | `20261002T140336Z_cda4e9f56b2f` | PASS, 50턴, 200회 FoundValue 평가 batch |
| 한국어 (`ko_KR`) | 4 | `20261002T134544Z_9423119fcbd5` | PASS, 50턴, 200회 FoundValue 평가 batch |

8회 실행은 각각 200 FoundValue 평가 batch를 기록했답니다. batch 하나에서 960 plot score를 확인해 총 1,600 batch, 1,536,000개 ordered score records를 대조했으며 source-order area totals, same-language archive·continuation, extended state/event snapshots 및 공식 UI RNG도 비교했사와요. 영어·한국어 각각 worker 0을 원본 SDK reference와 비교했고, worker 0 대비 1/2/4는 각 언어에서 3개 archive와 continuation을 비교해 모두 같았답니다. bundle identity 비교에서는 GameCore SHA 행만 정확히 치환했사와요. 언어 간 archive 바이트 동일성은 주장하지 않사와요. [영어 worker 0 실행 결과](../evidence/save_restore/20261002T133819Z_83f867de0f55/result.json) · [한국어 worker 0 실행 결과](../evidence/save_restore/20261002T134236Z_1623790d32da/result.json)

## 계산 경계와 호환성

원본 `CvCitySiteEvaluator::PlotFoundValue`의 계산은 [FoundValueScores.h](../Source/Concurrency/FoundValueScores.h)의 소유 값 커널로 옮겼고, [FoundValueScoreBridge.h](../Source/Concurrency/FoundValueScoreBridge.h)와 [FoundValueScoreBridge.cpp](../Source/Concurrency/FoundValueScoreBridge.cpp)가 C++14 caller와 C++17 구현 사이의 고정 크기 POD 경계를 제공하와요. SDK caller가 owner thread에서 SDK 객체를 읽어 candidate별 snapshot을 만들고, worker는 SDK 포인터를 받지 않고 snapshot만 평가한답니다. worker 결과는 기존 scalar `PlotFoundValue` shadow와 대조되며, 모든 점수와 area 누계의 사전 검증이 끝난 뒤 owner thread에서 원래 plot 순서로 setter를 호출하와요. 이는 검증 뒤의 순서 있는 적용을 뜻하며 setter 단계의 트랜잭션 rollback 보장은 아니랍니다. 실패, 불일치, overflow는 setter 호출 전에 중단한답니다. [커널 differential component 검증](../evidence/found_value_scores/20261002T132635Z_3f7668a4bf/conformance.json) · [C ABI bridge component 검증](../evidence/found_value_score_bridge/20261002T132847Z_11ac6db1ad/conformance.json) · [SDK capture mock component 검증](../evidence/found_value_sdk_capture/20261002T133508Z_e96e56059c44/conformance.json) · [최신 원본 비교 회귀 검증](../evidence/found_value_comparator/20261002T141003Z_072c035c83a5/conformance.json)

커널은 원본의 두 산술 세부를 의도적으로 보존한답니다. 첫째, 원본 faith 누계는 각 거리 반복마다 초기화되지 않아 거리 1–3에서 계산된 값이 이후 원본 순회에서 자격을 갖춘 거리 0·4·5 셀에도 carry-over될 수 있으며, 순회 순서도 결과 일부랍니다. 둘째, Celtic faith 보정의 `faith_flavor_multiplier`는 타일의 `settler_faith_multiplier`와 다른 입력이랍니다. 둘을 합치면 실제 원본 계산과 달라지므로 분리되어 있사와요.

작업자 0은 원본 scalar 경로이며 빌드 기본값도 0이랍니다. trace도 기본 꺼짐이고, 위의 worker 1/2/4 실행은 runner가 설정을 명시한 opt-in 행렬이와요. 별도 `SERIAL_TRACE_OFF` 기본 환경변수 gate의 EN `20261002T141001Z_138ed4db3f7f`·KO `20261002T141258Z_1ca3f90dc991` 실행도 각 50턴 통과했답니다. 두 요청에서 FoundValue worker/trace override는 비어 있고 inherited FoundValue 환경변수는 제거됐으며, state·archive·continuation·공식 UI signature는 같은 언어 worker 0 reference와 같았사와요. 이 기본 환경 gate에는 FoundValue score trace가 없으므로 점수 배열 직접 비교, worker job 관측 또는 OS worker 실행 부재를 입증하지 않는답니다. 이는 환경변수 기본값 및 턴 상태 연속성 확인이지 별도 FoundValue 계산 경로 관측이 아니랍니다. [기본 환경 EN/KO strict conformance](../evidence/found_value_default_environment/20261002T142850Z_a9c46a490e0b/conformance.json)

기본 환경 proof의 첫 검증 시도는 live tuple과 JSON에 저장된 list의 컨테이너 형태 차이로 실패했답니다. 새 strict proof에서 컨테이너 구조만 정규화하고 UI turn/mode/draw/ranked-order/value 내용은 그대로 비교했으며 값 변조 회귀도 거부했사와요. 실패한 이전 산출물은 보존되어 있답니다.

## 의미 결과와 진단 계측

게임 결정의 의미 결과는 각 plot index에 연결된 FoundValue 점수 및 원본 순서로 누적한 area totals랍니다. 이 값들은 worker 0/4 대조와 원본 SDK reference 대조의 대상이었사와요. 반면 worker 요청 수, 생성·사용 스레드 수, job 수, overlap, `helper_unique_plots`, snapshot/worker/shadow/reduction/total 시간은 실행 방식과 계측을 설명하는 진단값이랍니다. 이 진단값은 도시 선택 점수 그 자체가 아니며 결과 동등성의 대체 근거로 사용하지 않사와요.

현재 `total_us`에는 scalar shadow 비교가 포함되어 있어 실제 worker 경로만의 비용을 나타내지 않는답니다. trace와 계측 자체도 실행에 비용을 더할 수 있으므로 이 수치로 speedup이나 성능 향상을 주장할 수 없사와요. 또한 이번 conformance는 `physical_multicore_verified=false`, `performance_improvement_verified=false`로 기록되어 있답니다. 별도로 수행한 CitySite CPU trace는 다른 계산 경로의 증거이므로 FoundValue 물리 코어 동시 실행 증거로 전용하지 않사와요.

## 남은 관문과 다음 측정 후보

빌드 provenance는 각 입력의 원본 경로·hash와 동결된 컴파일 산출물을 기록하므로 후속 소스 변경과 현재 proof의 대상을 구분할 수 있답니다. 이는 저장된 후보 proof의 입력 기록이지 원본 소스를 영구 동결한다는 뜻은 아니랍니다. 활성 SDK 포인터와 Stage는 갱신되지 않았고, 정식 승격도 하지 않았사와요. retail 저장 호환성, 실제 렌더링·사용자 조작, 전체 GameCore 동등성은 미검증이랍니다. 이 결과는 격리 SDK 후보의 50턴 실행과 native save/restore 증거이며, 설치된 게임의 승인 검증을 대신하지 않사와요.

성능을 판단할 다음 작업 후보는 별도 계측으로 확인할 가치가 있답니다. kernel review의 snapshot reserve·불필요한 복사 축소 제안은 후속 공유 입력 경로에 반영했사와요. 지도 관측값 공유와 후보 배열 reserve를 구현하고 C 입력의 논리 크기를 대조했으며, 실제 프로세스 메모리와 속도 향상은 아직 측정하지 않았답니다. 원래 dense 경로는 역사적 기준으로 보존하와요.

1. 동일 save와 고정 workload에서 worker 0/1/2/4를 비교하고, snapshot·worker·shadow·reduction 비용을 분리해 p50/p95를 기록하와요. 우선 현재 shadow 포함 진단값과 shadow 없는 후보 production 경로를 구분해야 한답니다.
2. 실제 FoundValue 호출별 후보 수와 유효 job 수를 기준으로 작업량 구간을 나눠, 작은 호출에서 thread launch 비용이 이기는 지점과 큰 호출의 처리시간을 재현 가능하게 측정하와요.
3. 후속 공유 후보의 FoundValue 전용 ETW/QPC trace는 별도로 수집·검증했사와요. 물리 코어 동시 실행은 해당 공유 커널 범위에서 확인했고, CitySite trace나 이 dense 행렬로 대신 입증한 것은 아니랍니다. 다음 성능 비교는 같은 입력과 반복 조건을 고정해야 한답니다.

이 문서는 Source/Build 단계의 후보와 격리 SDK 실행만 다루며 Build→MODS 배포, renderer/UI, retail 저장, 실사용 승인은 다음 단계로 남아 있사와요.
