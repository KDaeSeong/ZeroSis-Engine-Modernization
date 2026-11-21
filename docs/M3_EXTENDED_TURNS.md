# M3: 50턴 save/restore 및 retained UI 후보 증거

상태: **고정 설정에서 실행한 50턴 네 건이 모두 통과했사와요.** 이는 명시된 fixture와 host 설정에 대한 headless 후보 증거랍니다. retail save 호환성, 전체 게임 동등성, 화면 렌더링, multicore 성능을 입증하지는 않는답니다.

## Save/restore 후보

현재 후보는 save/restore patch row 19개를 포함하며 translation unit 10개를 다시 compile했답니다. 분리 SDK link report에는 기존 accepted object 149개를 재사용했다고 기록돼 있답니다. operation reset 수정은 `Reset`에서 reinforcement flag를 초기화한답니다. 이 flag는 기존 stream에 이미 boolean으로 들어가므로 초기화 보정은 save schema를 바꾸지 않는답니다. 추출한 method body의 component test는 통과했지만, 해당 기록 자체가 전체 DLL이나 Civ V runtime 증거가 아닌 component fixture라고 범위를 한정한답니다. [`evidence/save_restore/20260930T135908Z_17e2f6b3c869/restore_sdk_build.json`](../evidence/save_restore/20260930T135908Z_17e2f6b3c869/restore_sdk_build.json)과 [`evidence/component_tests/save_restore_initializers/20260930T130108Z_ae69f050/record.json`](../evidence/component_tests/save_restore_initializers/20260930T130108Z_ae69f050/record.json)을 보시와요.

이전 extended run은 turn 42에서 구현되지 않은 `GameplayGoldenAgeStarted` host callback 때문에 멈췄답니다: [`evidence/save_restore/20260930T134756Z_f72d953180c9/result.json`](../evidence/save_restore/20260930T134756Z_f72d953180c9/result.json). 이후 host가 owner-locked 방식으로 소유된 start/end event 기록을 추가했으며, 아래 네 실행은 그 수정 뒤 turn 50까지 통과했답니다. 여기서는 Golden Age callback의 구체적인 발생 횟수를 주장하지 않는답니다.

## 실행 행렬과 비교

동결된 [`evidence/extended_turns/20261001T111328Z_ffbdaa5df681/conformance.json`](../evidence/extended_turns/20261001T111328Z_ffbdaa5df681/conformance.json)과 [`summary.json`](../evidence/extended_turns/20261001T111328Z_ffbdaa5df681/summary.json)은 네 실행의 통과를 기록한답니다. 각 실행은 configured 40x24 fixture를 시작하고 turn 1 이후 checkpoint를 만든 뒤 한 번 복원했으며, real AI turn과 human skip-remaining-units 동작으로 이후 48턴을 진행해 turn 50까지 도달했답니다.

| 실행 | Locale | Worker 설정 | 결과 |
| --- | --- | ---: | --- |
| `20260930T135908Z_17e2f6b3c869` | `en_US` | 0 | 통과, turn 50 |
| `20260930T140118Z_8a513248d180` | `ko_KR` | 0 | 통과, turn 50 |
| `20261001T110956Z_5f5f92002439` | `en_US` | 4 | 통과, turn 50 |
| `20261001T111052Z_f98e39aae89a` | `ko_KR` | 4 | 통과, turn 50 |

strict archive 및 per-turn 검사가 통과했답니다. 같은 locale 안에서 worker-0과 worker-4의 checkpoint, restored, final archive는 독립 생성된 16-byte Map GUID만 정규화한 뒤 일치했으며, 비교 대상은 archive entry 133개랍니다. 이어진 48개 semantic snapshot, normal turn event, workload, fixture 승급 명령도 모두 같았답니다. `en_US`와 `ko_KR`의 semantic snapshot 및 popup mode/draw는 같았지만, locale 간 serialized archive byte equality는 주장하지 않는답니다.

각 실행은 batch 346개와 plot 24,371개를 처리했고 batch별 plot 수는 16–171개였답니다. worker-4 실행의 batch 346개 모두 `used_threads=1`, `max_overlap=1`로 기록됐답니다. worker 생성 또는 setting 4는 실제 multicore 실행이나 speedup의 증거가 아니랍니다. 통제된 성능 benchmark나 CPU overlap 측정은 이 보고서 범위에 없답니다.

## 선택형 정상 승급 경로

이 실행은 별도 `--check-save-restore-ui-promotions` fixture 경로를 명시적으로 켰답니다. turn 29에는 `PROMOTION_SHOCK_1`, turn 38에는 `PROMOTION_SHOCK_2`를 정상 명령 경로로 적용했답니다. 대상은 player 0의 unit 16385였으며 promotion level은 1에서 2, 2에서 3으로 올랐고 XP는 각각 16과 30으로 유지됐답니다. fixture는 일반 legality 검사에서 허용된 첫 승급을 골라 local command route로 전달한답니다. 승급 상태를 직접 쓰거나 XP를 지급하지 않으며 unit readiness도 우회하지 않는답니다. 이 선택형 경로는 fixture 검증이지 새 game rule이나 임의 gameplay의 보증이 아니랍니다.

host 설정은 빈 mod list를 명시적으로 활성화했답니다. activation이 미설정이면 거부하며, versioned activation/save manifest가 아직 없어 nonempty manifest는 지원하지 않는답니다.

## 한계

이 증거는 고정 fixture와 시험한 후보에 한정된답니다. retail save, 임의 map/configuration, 전체 gameplay 동등성, interactive gameplay, accepted-stage 승격은 검증하지 않았답니다. UI/RNG 실행 상세와 renderer 및 retail lifecycle의 미완료 범위는 [`M3_UI_POPUP_BOUNDARY.md`](M3_UI_POPUP_BOUNDARY.md)에 적었답니다.

## 후속 SDK 선택·액션 경로

같은 정상 승급 선택 정책을 SDK 단일 유닛 선택과 `Game.CanHandleAction/HandleAction`으로 전달하는 별도 후보도 한·영 × worker 0·4에서 50턴을 통과했사와요. 그 후보는 선택에 따른 실제 SDK 상태 변경을 포함하므로, 위 직접 local-command 후보와 archive 바이트가 같다고 주장하지 않사와요. 각 후보 안에서 같은 언어의 직렬·4워커를 대조했답니다. [후속 구현·실행 범위와 고정 근거](M6_LOCAL_UNIT_ACTIONS.md)
