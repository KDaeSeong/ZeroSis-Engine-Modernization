# M5: 도시 부지 점수 커널과 GameCore 연결

2026-10-02에는 CPU trace를 기본 꺼짐으로 포함한 새 후보 DLL `e85735b6dee55aeeddd286e4a959cd0f19ed45945a090654d1c4263758925354`와 현재 host로 EN/KO × worker 0·4의 네 실행을 각각 50턴까지 검증했사와요. 같은 언어의 ordered yield, 133개 archive 구획과 continuation·UI·RNG가 같았답니다. worker 4의 생성/사용/최대 겹침은 EN `4/4/3`, KO `4/3/3`이었으며 이 네 실행에서는 CPU trace를 껐사와요. [현재 후보 빌드](../evidence/city_site_sdk/20261001T135932Z_86b1d2704654/build_result.json) · [현재 네 실행 대조표](../evidence/city_site_runtime/20261002T122213Z_6dc2fc7bd9f7/conformance.json)

별도 trace 활성 실행의 ETL도 reader 수정 후 엄격한 상관관계 검증을 통과했사와요. 원시 QPC 겹침 4틱의 양끝을 한 틱씩 제외해 남은 2틱 구간에서 서로 다른 물리 코어의 워커가 스케줄됨을 확인했답니다. 속도 향상과 엔진 전체 멀티코어는 별도 관문이랍니다. [실제 CPU 추적 범위와 고정 proof](M5_CITY_SITE_CPU_TRACE.md)

아래는 최초 후보와 8개 실행의 역사적 기록이랍니다. 위의 현재 후보·현재 host 실행과 같은 빌드나 실행으로 합치지 않사와요.

2026-10-01에 `CvCitySpecializationAI::FindBestSites`의 실제 SDK 호출부에 부지 점수 경로를 연결한 격리 x64 GameCore 후보를 빌드하고, 영어·한국어 × 작업자 0·1·2·4의 8개 실행을 각각 50턴까지 검증했사와요. 후보 DLL SHA-256은 `491c058d79c10742da7646524098c2c01ad18e4836d4ce33a4f4b9518aa58d6c`이며, 기존 SDK 파일·활성 SDK 포인터·Stage는 갱신하지 않았답니다. [실제 런타임 대조표](../evidence/city_site_runtime/20261001T130231Z_e7fee65603d6/conformance.json) · [후보 빌드 기록](../evidence/city_site_sdk/20261001T124622Z_90b055bd9e66/build_result.json)

커널 [CitySiteScores.h](../Source/Concurrency/CitySiteScores.h)는 `PlotValueForSpecificYield`와 `PlotValueForScience`의 관측값을 소유된 POD 값으로 계산하와요. `evaluate_all`은 각 후보의 이웃 셀을 한 번 순회해 식량·생산·금·과학 값을 반환하며, 원문 helper의 지원 ring 거리 밖 multiplier 유지와 타국 소유 셀의 multiplier 초기화를 보존한답니다. `int32` 중간 계산이 넘치면 결과 대신 overflow를 반환한답니다.

분리된 C ABI bridge는 C++14 caller와 C++17 구현으로 `/O2`·`/Od` 각각 518 checks를 통과했사와요. ABI·설정·입력 범위, 늦은 잘못된 셀·산술 overflow에서의 결과 원자성, worker accounting을 확인한 구성요소 검증이랍니다. [Bridge 경계 검증](../evidence/city_site_score_bridge/20261001T122312Z_620a2d060be4/conformance.json)

SDK caller commit 검증은 동결된 builder 결과의 `FindBestSites`·snapshot helper와 원본 SDK의 두 scalar helper 본문을 추출해 `/O2`·`/Od` 각각 57 checks를 통과했사와요. capture 예외·bridge 실패·overflow·shadow 불일치에서 기존 `m_iBestValue[4]`를 보존하고, owner thread/lock 검사가 map read와 값을 지우기 전에 실행되는지, 성공 시 네 yield의 고정 순서 reduction 후 한 번에 반영되는지 확인했답니다. 빈 후보는 0으로 반영되고 작업자 0은 기존 scalar 결과와 같았사와요. 다만 GC·map·plot·bridge가 source-shaped mock이므로 실제 GameCore 런타임 증거와는 구분하와요. [SDK commit component 검증](../evidence/city_site_sdk_commit/20261001T124430Z_98e38687f755/conformance.json)

후보 SDK translation unit은 원본 baseline과 같은 경고 7개를 냈고 새 bridge 및 링크는 경고 0개였사와요. PCH는 참고 자료로만 두고 재사용하지 않았으며, 소스는 Windows-1252로 명시 해석해 별도 Build 후보를 생성했답니다. 원본 소스·활성 SDK·Stage는 바뀌지 않았사와요. 입력 provenance에는 실제 translation-unit source/header 의존성을 기록했지만 시스템 헤더를 컴파일 전 완전히 동결하지 않았고, compiler helper DLL·link library와 OS 환경도 동결 범위가 아니랍니다.

실제 런타임 행렬은 매 실행에서 turn 43, player 1, 도시 2개의 `FindBestSites` 호출을 확인했사와요. 각 호출의 후보 95개에는 18개 타일 슬롯을 관측했고, 모든 설정의 최대값은 식량 184·생산 129·금 80·과학 209였답니다. 95개 후보의 plot index와 네 yield를 little-endian 정수로 직렬화한 1,900바이트 결과의 SHA-256은 `df358f20444b41a02905a3c43cd072bbf2f1ab1459aad6c785f62cd4edcbb9c5`였으며, 모든 ordered value를 직접 비교해 worker 설정 간 결과가 같음을 확인했사와요.

| 요청 작업자 | en_US: 생성/사용/최대 겹침 | ko_KR: 생성/사용/최대 겹침 |
|---:|---:|---:|
| 0 | scalar 경로, 0/0/0 | scalar 경로, 0/0/0 |
| 1 | 1/1/1 | 1/1/1 |
| 2 | 2/2/2 | 2/2/2 |
| 4 | 4/4/4 | 4/1/1 |

같은 언어의 worker 비교는 매 비교에서 세 archive와 계속 진행한 턴의 의미 상태를 대조했고, 같은 SDK 프로파일의 133개 archive 구획을 비교했사와요. 한 실행 안의 GUID는 고정되어 있답니다. 원본 SDK reference와는 archive 전체가 아니라 bundle identity를 제외한 게임 데이터 구획 132개(실제 CvGame 구획 포함)와 continuation을 대조했고, bundle identity에서는 GameCore SHA-256 행 하나만 치환했사와요. 독립 새 게임 archive 사이에서 정규화한 값은 지도 GUID 16바이트뿐이랍니다. 영어·한국어 간 archive 전체 바이트 동일성은 주장하지 않사와요.

당시 두 작업자 요청은 양 언어에서 각각 두 작업 스레드와 최대 겹침 2를 기록했답니다. 네 작업자 요청은 영어에서 네 스레드·최대 겹침 4, 한국어에서는 네 스레드를 만들었지만 점수 작업은 한 스레드만 수행해 최대 겹침 1이었사와요. 이 역사적 행렬 자체는 score invocation의 겹침 증거이며 물리 CPU 동시 실행이나 일반 workload 전반의 멀티코어 입증은 아니랍니다.

계측 `total_us`는 serial EN/KO 518/406µs, worker 1은 1960/1221µs, worker 2는 1543/1540µs, worker 4는 1585/1592µs였사와요. 이는 capture·thread launch/join·scalar shadow·reduction·trace 준비를 포함한 진단 시간이지 benchmark가 아니랍니다. trace 파일 쓰기는 측정 구간에서 빠져도 런타임에 영향을 줄 수 있어 성능 향상이나 speedup을 주장하지 않사와요.

이 M5 증거는 해당 호출 경로의 결정성과 후보 연결까지랍니다. 실제 화면 렌더러·사용자 조작·비어 있지 않은 활성 모드 manifest·retail 저장 호환성·전체 GameCore 동등성·장기/실패 회귀·정식 Stage 승격은 남아 있사와요. 이 행렬은 도시 건설 `MISSION_FOUND` 입력도 검증하지 않았답니다. [M5 탐색 작업자 기록](M5_SDK_EXPLORATION_WORKERS.md)에서 별도 탐색 batch 계측과 구분하와요.
