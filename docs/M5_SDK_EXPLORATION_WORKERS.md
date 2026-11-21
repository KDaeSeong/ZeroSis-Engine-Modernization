# M5: SDK 탐색 점수 작업자 행렬

## 2026-10-01 최신 50턴 비교

영어·한국어 × worker 0·4 네 실행이 native fresh-session 복원 뒤 50턴까지 진행하고, 같은 언어에서 checkpoint·복원 직후·최종 archive 133개 구획 전체를 독립 새 게임 지도 GUID 16바이트만 정규화한 뒤 일치시켰사와요. 모든 추가 턴 의미 상태 표본·명령·턴 이벤트·탐색 workload 및 29·38턴 승급 입력도 같았답니다. 25·50턴 공식 순위 팝업의 원문 Lua·retained control tree·실제 SDK RNG 소비·타이머 수명주기를 별도로 비교했사와요. [고정 저장·턴 대조표](../evidence/extended_turns/20261001T111328Z_ffbdaa5df681/conformance.json) · [측정 요약](../evidence/extended_turns/20261001T111328Z_ffbdaa5df681/summary.json) · [공식 팝업·난수 대조표](../evidence/ui_popup/runtime/92792d745404413ba3b50294ab8065aa/conformance.json)

각 실행은 346 batches·24,371 plots, batch당 16–171 plots를 포함한답니다. 두 4워커 실행 모두 346개 batch 전부에서 실제 scoring thread 수와 최대 겹침이 1이었사와요. 따라서 이 경로의 실제 병렬 계산과 유용한 성능 향상은 여전히 미입증이랍니다. OS thread ID별 CPU 시간이나 물리 코어 추적은 수집하지 않았고, `worker_ids`는 관측 스레드를 재매핑한 번호랍니다.

| 언어 | 요청 worker | 탐색 Update 합계 | snapshot 합계 | worker 합계 | shadow 검증 합계 | scoring thread 최대 | 최대 겹침 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 영어 | 0 | 36,370 µs | 0 | 0 | 0 | 0 | 0 |
| 영어 | 4 | 333,361 µs | 24,904 µs | 288,673 µs | 7,155 µs | 1 | 1 |
| 한국어 | 0 | 18,611 µs | 0 | 0 | 0 | 0 | 0 |
| 한국어 | 4 | 347,609 µs | 25,268 µs | 300,658 µs | 7,740 µs | 1 | 1 |

이 수치는 서로 다른 시간·캐시 조건에서 각 한 번씩 실행한 계측·shadow 포함 진단값이랍니다. 반복 교차 benchmark가 아니므로 언어별 속도 차이, 전체 턴 이득이나 일반적인 성능을 주장하는 근거로 쓰지 않사와요. 기존 두 턴 행렬과 최신 50턴 비교의 SDK build·host mode·승급·팝업 조건이 다르므로 두 측정을 합쳐 개선율을 계산하지 않사와요. SDK19와 실제 연결된 호스트는 고정 각 run의 request/build manifest에 보존했답니다.

다음 계산 후보로 도시 부지의 네 yield 점수를 소유된 이웃 값에서 한 번에 계산하는 커널을 분리하고 원문 helper와 차등 검사했사와요. 이는 실제 SDK 연결 전 구성요소 단계이며, 현재 탐색 경로의 병렬성·성능 판정을 바꾸지 않사와요. [도시 부지 커널과 남은 연결 관문](M5_CITY_SITE_SCORES.md)

후속 SDK 단일 유닛 선택·`Game.HandleAction` 입력 후보도 한·영 × worker 0·4에서 50턴 archive·의미 상태·명령·UI/RNG 비교를 통과했사와요. 그 실행도 각 346 batch·24,371 plots이며 4워커의 scoring thread·max overlap은 모두 1이었답니다. 위 표는 이전 직접 local-command 후보의 측정이므로 후속 후보 값과 섞어 성능 차이를 계산하지 않사와요. [후속 고정 요약](../evidence/extended_turns/20261001T115602Z_12bb487f337d/summary.json) · [선택·액션 범위](M6_LOCAL_UNIT_ACTIONS.md)

## 2026-09-29 두 턴 검증 이력

2026-09-29 실제 SDK `CvEconomicAI`의 `UpdatePlots` Range 1 탐색 점수 계산에 한정해 worker 요청값 0·1·2·4를 적용한 한·영 8회 행렬을 실행했사와요. 각 실행은 두 턴을 진행하고 턴 1 저장, 새 GameCore 세션 복원, 턴 2 저장까지 수행했답니다. 행렬 및 archive 대조는 [통합 conformance](../evidence/explore_sdk_runtime/conformance.json), 후보 연결 정보는 [SDK build 결과](../evidence/explore_sdk/20260929T130314Z_4e1669ad4478/build_result.json)에 있사와요.

결과는 **SDK 탐색 점수 worker 경로의 실행·결과 일치 검증 통과**랍니다. 요청 2와 4에서는 요청된 수만큼 worker thread를 생성했지만, 점수 작업은 한 thread가 모두 처리했고 최대 동시 scoring invocation은 1이었사와요. worker 요청값 1도 겹친 호출은 없었으므로 물리 멀티코어 사용이나 성능 향상을 입증하지 않았답니다. SDK 후보 link 단계 기록의 `gamecore_loaded=false`는 빌드 단계만 가리키며, 별도 여덟 격리 런타임에서는 후보 GameCore DLL을 실제 로드했사와요. 설치된 retail EXE는 실행하지 않았고, 후보는 active SDK를 갱신하거나 Stage에 승격되지 않았답니다.

## 작업자 행렬과 측정 경계

각 worker 설정은 영어·한국어 각 1회씩, 합계 2회 실행이랍니다. aggregate 계측은 설정당 32 batches·690 scored plots를 포함하며, 개별 batch는 16–30개 plot 작업이와요. 2·4 worker 설정은 각각 2·4개 스레드를 생성했지만, 기록된 점수 작업은 한 thread가 모두 처리했답니다.

| 요청 worker | 실행 수 | 생성 worker thread 수 | 실제 scoring thread 최대 | 최대 동시 scoring | 탐색 Update 합계 | 정상 턴 중앙값 | 해석 |
|---:|---:|---:|---:|---:|---:|---:|---|
| 0 | 2 | 0 | 0 | 0 | 789 µs | 23,643.5 µs | 기존 직렬 경로 |
| 1 | 2 | 1 | 1 | 1 | 20,155 µs | 28,939.5 µs | 시작·snapshot·shadow 비용 포함 |
| 2 | 2 | 2 | 1 | 1 | 23,899 µs | 32,395 µs | 여러 스레드 중 하나가 작업 처리 |
| 4 | 2 | 4 | 1 | 1 | 32,965 µs | 33,869 µs | 여러 스레드 중 하나가 작업 처리 |

수치는 계측 및 shadow comparison이 포함된 진단 실행값이며 benchmark가 아니랍니다. 특히 worker batch 구간 외에 snapshot 복사와 shadow 검증 비용이 들어가므로 속도 비교나 전체 턴 성능 주장에 사용하지 않사와요. 이 fixture의 작은 batch에서는 worker 경로가 serial보다 느렸으며, 이 결과만으로 다른 부하에서의 성능을 일반화할 수도 없답니다.

## 저장 비교와 결정성 범위

대조표의 여섯 EN/KR × 1/2/4 비교 행은 각 언어 안에서 직렬 0-worker 기준과 해당 worker 실행의 세 archive checkpoint(턴 1, restore 직후, 턴 2)를 대조한 결과랍니다. 각 archive는 133개 section이며, 132개는 바이트 단위로 같고 남은 Map section도 새 게임 `CvMapGUID` 필드만 제외하면 같았사와요. 비교에서 각 archive의 132개 exact section은 bundle identity 1개와 SDK section 131개를 포함한답니다. 언어별 live batch order도 일치했으며, 영어와 한국어 사이의 전체 바이트 동일성은 assert하지 않았사와요. 언어 문자열 필드가 다르므로 cross-language byte equality를 판정 범위에 넣지 않았답니다. `CvMapGUID`는 지도 section offset 34의 16 bytes이며, 같은 실행 안에서는 저장·복원 전후 일정했사와요.

각 archive는 총 133개 구획, 즉 bundle identity 1개와 실제 SDK serialized section 132개로 구성된답니다. 이 행렬에서 말하는 132개 raw section의 일치는 독립 실행 사이의 새 게임 지도 GUID 바이트를 제외한 archive 비교 결과이와요. 별도 같은 실행 restore 판정에서는 133개 가운데 132개가 byte-exact이며 그 132개에는 bundle identity와 SDK section 131개가 포함되고, 유일한 Game 구획 차이는 고정 fixture의 session/replay reload metadata랍니다. 두 비교 범위를 섞어 “132개 SDK 구획이 모두 같다”고 읽어서는 안 되와요. 저장·복원 대조표의 fixture 설명은 [M3 native save/restore 기록](M3_NATIVE_SAVE_RESTORE.md)에 있답니다.

같은 언어의 직렬 반복 대조도 한국어 `20260929T130459Z_54ea239fd0f9`에서 수행했사와요. 직렬 baseline `20260929T130427Z_3d6e46a8a5c2`와 세 archive checkpoint(턴 1, 복원 직후, 턴 2)를 비교해 archive마다 133개 구획을 지도 GUID 차이만 정규화한 뒤 일치시켰고, live batch order·SDK snapshot·turn event도 같았답니다([반복 실행 결과](../evidence/save_restore/20260929T130459Z_54ea239fd0f9/result.json)).

직렬 worker 값 0은 frozen builder source에서 기본값으로 확인했사와요. 다만 행렬의 모든 런타임은 worker 값을 명시적으로 설정했고, worker 환경변수를 설정하지 않은 별도 런타임 실행은 하지 않았으므로 런타임의 unset-environment 동작까지 입증한 것은 아니랍니다. 대조표의 validator 입력은 검사 전·후 hash가 같고 검사기는 확인 전에 고정된 자료랍니다.

## 초기화 보정과 관련 독립 검사

행렬에 사용한 후보는 저장 스키마와 직렬화 항목 수를 바꾸지 않고, 아직 초기화되지 않던 상태 세 곳을 보정했사와요.

- `CvMilitaryAI::Reset`은 플레이어 수용 배열 4개를 군사 전략 개수로 순회해 기본 fixture의 25개 전략에서는 63개 플레이어 슬롯 중 38개가 초기화되지 않았고, 전략 개수가 63을 넘으면 범위 밖 쓰기가 생길 수 있었답니다. 후보는 `MAX_CIV_PLAYERS`(63) 기준으로 별도 초기화하와요.
- `PlayerCulture`는 `m_eOpinion=NO_PUBLIC_OPINION`, `m_ePreferredIdeology=NO_POLICY_BRANCH_TYPE`, `m_eOpinionBiggestInfluence=NO_PLAYER`와 파생 tooltip 문자열 두 개의 빈 문자열 기본값을 설정하와요.
- `TraitEntry`는 DB 선택값이 NULL일 때 `CombatBonusImprovement`가 설정되지 않던 경로에 `NO_IMPROVEMENT` 기본값을 둔답니다.

관련 fixture 회귀는 전략 개수 25·63·64·80의 경계를 확인했지만, 이는 전체 GameCore 회귀나 실제 저장 archive 검증을 대체하지 않는답니다([initializer fixture 기록](../evidence/component_tests/save_restore_initializers/20260929T125735Z_ff202d5c/record.json)). 저장 복원용 최신 후보는 18개 패치·9개 translation unit으로 연결됐으며, 변경 목록과 provenance는 [patch manifest](../evidence/save_restore_sdk/20260929T130300Z_bde1b7fd4ce6/frozen/save_restore_patches.json)에 있사와요.

탐색 계산의 앞단 helper들도 범위를 구분해 보시와요. bridge 경계 43개 검사는 [bridge conformance](../evidence/explore_score_bridge/reports/20260929T123733Z_ada71ac9d0/conformance.json), score kernel 500개 검사는 [kernel conformance](../evidence/explore_plot_scores/conformance_20260929T121247Z_653fcc6a.json)에 있답니다. 이 helper 및 initializer fixture 검사는 SDK 전체 상태, 전체 GameCore worker overlap, retail 호환성 증거가 아니와요.

## 남은 관문

실제 겹치는 scoring 호출이나 물리 코어의 동시 실행은 관측되지 않았고, 성능 향상·전체 게임 결정성·전체 GameCore 동등성·retail 저장 호환성·설치 게임 실행·정식 Stage 승격도 미검증이랍니다. 현재 검증은 언어별 고정 두 턴 restore fixture와 하나의 작은 탐색 점수 작업 경로에 국한되며, cross-language 바이트 동일성·unset worker 환경변수의 런타임 동작·장기 턴·다른 AI 계산·렌더링·모드 연결 전체의 결과를 보증하지 않사와요.
