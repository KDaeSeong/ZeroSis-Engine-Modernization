# M5: 실제 도시 부지 점수 구간의 물리 코어 실행 추적

2026-10-02 정상 SDK의 `CvCitySpecializationAI::FindBestSites` 호출에서 서로 다른 물리 코어의 워커 실행 구간이 겹쳤음을 확인했사와요. 기존 ETL을 수정된 reader로 다시 읽고, root 검증기가 실제 SDK 출력·직렬 결과·프로세스와 스레드 수명·CPU topology·CSwitch 기록을 독립 대조한 결과랍니다. 한 함수의 짧은 계산 구간에 대한 증거이며 성능 향상이나 엔진 전체의 멀티코어 완료는 뜻하지 않사와요.

최신 고정 proof는 [실제 CPU 상관관계 검증](../evidence/city_site_cpu_capture/validators/20261002T135821Z_58917ed9d73d/conformance.json), SHA-256 `36938a4ed0c03dae6d520ab7041a72391c34fb72a415b41b31655b7727e740be`이랍니다. FoundValue용 선택 검증을 추가한 뒤에도 기존 CitySite 경로를 다시 통과했사와요. 검증기는 새 WPR 기록이나 GameCore 실행을 시작하지 않고 보존된 실제 실행을 분석했사와요. 앞선 [QPC 보수 구간 검증](../evidence/city_site_cpu_capture/validators/20261002T130249Z_cf95e34976c4/conformance.json)도 보존했답니다.

| 항목 | 관측과 검증 |
|---|---|
| 실제 capture | `20261002T121432Z_9a2ccbd4b82b`, GameCore PID `35296` |
| 실제 SDK 실행 | `20261002T121433Z_7fb45ecaad9c`, 50턴, worker 4, trace 명시적 활성화 |
| GameCore SHA-256 | `e85735b6dee55aeeddd286e4a959cd0f19ed45945a090654d1c4263758925354` |
| ETL SHA-256 | `fa11997c6f332a0dce3ae7dbd66f17ceead0dc9374cdf69702ebd85ca6e03a37` |
| 작업 | turn 43의 batch/call 1, 후보 95개 × 타일 슬롯 18개 |
| worker TID와 작업 수 | `33704:36`, `26600:24`, `11252:16`, `2312:19` |
| marker와 계산 중 CPU slice | begin/end 190개, 유효 작업 95개, 교집합 slice 79개 |
| topology | 단일 processor group, 논리 CPU 12개, 물리 코어 6개 |
| loss | events/buffers/reader events 모두 0, buffer callback 78회(두 pass 합계) |
| CSwitch | 전체 1,488,260개, worker 관련 32개, CPU 미매핑 0개 |
| QPC frequency | 10,000,000Hz, raw ETL clock type와 capture topology 일치 |

root가 찾은 가장 긴 원시 교집합은 job 29/TID 26600/core 0과 job 30/TID 33704/core 5의 `[49782340247,49782340251)`이랍니다. Microsoft는 다른 스레드에서 읽은 QPC 값의 차이가 한 틱 이내이면 순서가 모호하다고 설명하와요. 이 검증기는 그 지침을 바탕으로 **양끝에서 각각 한 틱을 제외하는 자체 보수 정책**을 적용했사와요. 원시 4틱에서 2틱이 남았고, 승격한 구간은 `[49782340248,49782340250)` = **0.2µs**랍니다. 1·2틱의 원시 겹침만 있는 입력은 물리 병렬 proof로 승격하지 않사와요. [QPC 공식 지침](https://learn.microsoft.com/en-us/windows/win32/sysinfo/acquiring-high-resolution-time-stamps)

reader 자체의 첫 원시 witness는 1틱이었으므로 이를 그대로 채택하지 않았답니다. root가 전체 유효 교집합에서 긴 구간을 다시 찾고, reader의 원시 witness도 실제 job/CPU slice 안에 있는지 별도로 확인했사와요. 같은 물리 코어의 SMT 논리 CPU 둘은 통과 근거가 되지 않으며, 동일 논리 CPU에 두 워커가 겹치거나 한 TID가 두 CPU에 동시에 있는 입력은 거부한답니다.

[독립 상관관계 회귀 검증](../evidence/city_site_cpu_capture_regressions/20261002T130535Z_39fa2252aa54/regressions.json)은 실제 decoded 기록을 고정한 순수 검증 함수로 19개 사례를 검사했사와요. 잘못된 입력 14종을 거부했고, SMT만 겹친 기록과 원시 1·2틱은 물리 코어 proof로 승격하지 않았답니다. 이 회귀 검증 자체는 ETL을 다시 읽거나 GameCore를 실행한 증거가 아니랍니다.

`CitySiteCpuTraceJob`은 JobBegin의 TraceLogging 쓰기가 끝난 뒤 QPC를 읽고, `evaluate_all`을 감싼 scope가 끝날 때 JobEnd를 쓰기 전에 QPC를 읽사와요. 따라서 provider mutex와 marker 쓰기 자체는 구간 밖이지만, 함수 호출·반환·RAII 및 QPC 접근 경계 비용은 포함될 수 있답니다. 이 증거는 그 구간의 **스케줄된 CPU 시간**이며, 점수 산술 명령이 동시에 retire됐다는 명령 단위 증거는 아니랍니다. 한 틱 정책도 모든 하드웨어의 시계 접근 비용을 보정하는 알고리즘은 아니랍니다.

실제 capture는 WPR을 사용 중인 세션이 없는지 먼저 확인하고, 고유 instance `ZeroSisCitySite_20261002T121432Z_9a2ccbd4b82b`만 시작·종료했사와요. 전후 topology, OS, QPC frequency와 raw ETL boot 정보를 대조했고, worker의 PID/TID 수명을 job과 CPU slice마다 확인했답니다. 이 reader는 단일 processor group의 확인된 mapping만 지원하며 다중 group은 추정하지 않고 거부하와요.

초기 reader는 classic kernel event의 TDH metadata 조회에서 `ERROR_NOT_FOUND (1168)`를 반환했사와요. [원래 capture 결과](../evidence/city_site_cpu_capture/20261002T121432Z_9a2ccbd4b82b/result.json)의 실패 기록은 보존했고, capture 자체의 시작·정상 SDK 실행·종료·입력 hash가 유효함을 확인한 뒤 새 immutable proof에서 reader 문제만 복구했답니다. 수정 reader는 확인된 process v4/v5, thread v3, CSwitch v5의 payload 범위와 offset만 읽고 알 수 없는 version이나 잘못된 크기는 거부하와요. marker는 TDH의 필드와 타입, event header PID/TID를 엄격히 대조한답니다. [reader 구성요소 검증](../evidence/city_site_cpu_trace/20261002T124805Z_04a6d4f6ea54/conformance.json) · [CSwitch 공식 schema](https://learn.microsoft.com/en-us/windows/win32/etw/cswitch) · [Microsoft PerfView parser](https://github.com/microsoft/perfview/blob/a4f670e/src/TraceEvent/Parsers/KernelTraceEventParser.cs)

CPU trace는 `ZEROSIS_CITY_SITE_CPU_TRACE=1`을 명시한 실행에만 켜지며 기본값은 꺼짐이랍니다. trace를 켠 실행도 [같은 언어의 직렬 기준](../evidence/city_site_runtime/20261002T122213Z_6dc2fc7bd9f7/conformance.json)과 ordered yield·공식 UI·RNG·native archive·계속 진행한 턴 상태가 같았사와요. 독립 새 게임의 map GUID 16바이트만 기존 계약대로 정규화했으며 결과 값이나 명령 순서는 정규화하지 않았답니다.

이 증거로 F03의 독립 계산 동시 실행을 **해당 정상 FindBestSites 호출 범위에서** 확인했사와요. 반복 측정한 전체 턴 성능(N02), 더 무거운 계산 경로, 전체 GameCore 결정성, 화면 renderer·사용자 gameplay 입력·활성 모드·retail 저장 호환성·장기/실패 회귀·정식 Stage 승격은 남아 있답니다. 원본 SDK·활성 SDK·Stage·MODS는 이 분석에서 바뀌지 않았사와요.
