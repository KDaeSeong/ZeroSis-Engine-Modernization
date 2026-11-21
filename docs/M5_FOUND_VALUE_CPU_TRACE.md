# M5: FoundValue의 실제 물리 코어 추적

공유 입력 FoundValue 후보의 별도 영어 worker 4 실행에서, 서로 다른 물리 코어가 순수 점수 계산 작업을 동시에 스케줄한 구간을 확인했사와요. [최종 strict proof](../evidence/found_value_cpu_capture/validators/20261002T161959Z_fa946449f9d9/conformance.json)는 `ACTUAL_FOUND_VALUE_SCHEDULED_DISTINCT_CORE_OVERLAP_PASS`이며, 전체 턴 속도 향상이나 전체 엔진의 병렬화 완료를 뜻하지는 않사와요.

2026-10-05 보관 안내: 원본 ETL·reader·당시 strict 결과는 보존했지만, 사용자 지시에 따른 [구형 실행 묶음 정리](../evidence/storage_cleanup/20261005T082918Z_ca2240df4d1f/plan.json)에서 연결된 과거 SDK 실행 폴더와 save_restore 보고서를 삭제했사와요. 따라서 이 문서는 당시 관측 기록이며, strict gate가 참조한 모든 원본을 현재 보유하거나 같은 gate를 지금 다시 통과했다는 뜻은 아니랍니다. 삭제 경로·SHA·당시 결과는 정리 ledger에 남겼사와요.

## 실행과 입력 연결

실행은 [공유 SDK 후보](../evidence/found_value_shared_sdk/20261002T154635Z_480d61cc2900/build_result.json)와 [영어·한국어 0/1/2/4 행렬](../evidence/found_value_shared_sdk_runtime/20261002T155959Z_f8b7cb268407/conformance.json)을 사전 조건으로 사용했답니다. 동일한 host·SDK·지도·UI·액션 fixture를 사용하며, Explore와 CitySite worker는 0, FoundValue worker는 4였사와요. `ZEROSIS_FOUND_VALUE_CPU_TRACE=1`만 FoundValue 전용 CPU opt-in으로 주입하고 상속된 값을 제거했답니다. CitySite CPU trace는 꺼진 상태였사와요.

실제 SDK 실행 `20261002T161323Z_422f18cf0e62`는 native 저장의 fresh-session 복원과 50턴 진행을 통과했사와요. [실행 결과](../evidence/save_restore/20261002T161323Z_422f18cf0e62/result.json) · [캡처 결과](../evidence/found_value_cpu_capture/20261002T161321Z_563fd5f53c64/result.json). WPR은 고유 이름의 본 작업 세션만 시작·종료했고, 실행 전후의 전역 및 해당 세션은 idle였답니다. 일반 권한으로 시작한 두 시도는 `0x80070005`에서 GameCore 실행 전에 중단됐으며, 관리자 권한의 숨김 helper 실행이 실제 추적을 만들었사와요. [관리자 실행 기록](../evidence/found_value_cpu_capture/launches/20261002T161251Z_c1541d6c40b9/launch_result.json)

[FoundValueCpuTrace.h](../Source/Concurrency/FoundValueCpuTrace.h)의 제공자 `ZeroSis.FoundValueCpuTrace`, GUID `{49a604e1-6c99-4e01-b41d-73694f2290a6}`를 사용했사와요. batch marker는 동기 제출·join을 감싸고, job marker의 QPC 구간은 `evaluate_shared_prevalidated` 실행만 감싼답니다. SDK 객체 읽기·scalar shadow·결과 setter는 이 job 구간에 포함되지 않으며, worker 스택에서의 dense 입력 구성은 포함된답니다.

SDK의 `ZEROSIS_FOUND_VALUE_LAYOUT.cpu_batch_id`를 ETW batch ID와 연결했고, 세션마다 다시 시작하는 `call_id`와 구별했사와요. 지도 타일 수를 뜻하는 `fact_count=960`, 모든 job index와 worker TID별 작업 수까지 맞췄답니다. 200회 LAYOUT 가운데 비어 있지 않은 199개 배치만 ETW job 범위를 만들며, 빈 호출은 CPU batch ID 0이랍니다.

## 독립 검증 결과

| 항목 | 보존된 추적과 strict 대조 결과 |
|---|---|
| 대상 process ID | 31364 |
| 연결된 batch / job | 199 / 21,976 |
| 관측한 서로 다른 worker TID | 491; 배치별 최대 4개, OS의 TID 재사용은 수명 구간으로 구별 |
| topology | 논리 프로세서 12개, 물리 코어 6개 |
| 전체 CSwitch / worker 관련 | 1,364,418 / 4,295 |
| worker CPU slice | 1,877 |
| 손실 event / buffer / reader event | 모두 0 |
| QPC frequency | 10,000,000 ticks/second |
| 보수 겹침 | 126 ticks = 12.6마이크로초 |

증거 구간의 같은 batch ID는 `193008666735`, 두 작업은 job 0/TID 19012/core 0과 job 2/TID 34032/core 2랍니다. 원시 구간 `[193008675019, 193008675147)`의 양끝에서 한 틱씩을 제외해 `[193008675020, 193008675146)`을 사용했사와요. marker 구간과 실제 CSwitch slice의 교집합이며, 서로 다른 스레드의 시간 marker가 겹쳤다는 사실만으로 통과한 것은 아니랍니다. 명령어 retirement나 전체 프로세스의 작업 분포를 측정한 proof도 아니랍니다.

[reader 출력](../evidence/found_value_cpu_capture/20261002T161321Z_563fd5f53c64/reader.json)은 raw-QPC·capture-time topology를 사용하고 Process 4/5, Thread 3, CSwitch 5의 알려진 kernel event 형태만 읽었사와요. process와 worker의 시작·종료 수명, group/logical CPU→physical core 연결, 한 logical CPU나 한 TID의 불가능한 scheduling overlap, 손실된 추적을 별도로 검사했답니다. [보존 ETL](../Build/FoundValueCpuCapture/20261002T161321Z_563fd5f53c64/found_value_cpu.etl)은 87,031,808바이트이며 새 캡처 없이 다시 검사할 수 있사와요.

## 검사기 정정과 출처

첫 strict 시도는 SDK 빌드가 보관한 byte-identical reader proof의 동결 경로를 원본 경로와 직접 비교해 실패했사와요. 원본 hash, 빌드의 고유 frozen 경로 및 정확히 하나인 original-source mapping으로 고쳤답니다. 다음 시도는 실제 reader의 typed version/count 배열을 mock의 dictionary 형태로 가정해 실패했사와요. 실제 reader schema로 수정하고 알려지지 않은 버전·중복·합계 불일치·이전 dictionary 형태를 거부하도록 했답니다. 이전 실패 proof와 원본 ETL은 보존했고 SDK나 추적을 다시 실행하지 않았사와요.

읽기 전용 검토에서 연결된 SDK result JSON 내부의 request·stdout 아티팩트를 다시 해시 검사해야 하는 결함도 찾아 고쳤사와요. 최종 strict gate는 캡처·SDK·reader·행렬뿐 아니라 실제 실행 결과와 요청 내부의 아티팩트도 검사한답니다. validator의 다섯 local Python dependency 파일은 run별 frozen copy로 보관했고, 실행 전후 원본 해시가 같았사와요. [순수 검사 회귀 proof](../evidence/found_value_cpu_capture_regression/20261002T162838Z_7451fef57bb7/conformance.json)는 [테스트 입력](../Tests/found_value_cpu_capture_validator.py)과 local Python closure를 동결해 20개 검사 그룹의 통과를 기록했사와요. raw 겹침 1·2틱은 보수 proof에서 제외하고 3틱은 통과하는 경계도 검사했으며, 이 순수 회귀 자체는 GameCore나 CPU 추적을 실행하지 않았답니다.

## 남은 범위

이 추적은 영어·빈 mod 목록·고정 50턴 fixture의 한 실행이랍니다. 한국어의 점수·저장 동등성은 별도 8행렬에서 확인했고, 한국어 CPU trace를 수행한 것으로 취급하지 않사와요. 성능 향상, 공유 후보의 unset 환경 런타임, retail `.Civ5Save`, renderer·사용자 gameplay 입력·실제 오디오·비어 있지 않은 mod 목록·장기 실패 회귀·전체 GameCore 동등성·정식 Stage 승격은 여전히 남아 있답니다. [공유 입력 구현과 크기](M5_FOUND_VALUE_SHARED_FACTS.md) · [원래 dense 후보 이력](M5_FOUND_VALUE_SCORES.md)
