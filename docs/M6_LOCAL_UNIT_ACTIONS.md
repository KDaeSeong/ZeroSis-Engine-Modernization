# M6: SDK 단일 유닛 선택과 승급 액션

별도 turn-zero fixture에서는 실제 SDK `MISSION_FOUND` 도시 건설과 새 GameCore 세션 복원을 검증했사와요. 이는 승급·50턴 실행과 다른 입력 경로이니 [도시 건설·복원 기록](M6_FOUND_CITY_ACTION.md)을 보시와요.

2026-10-01 영어·한국어 × worker 0·4 네 실행에서 SDK 유닛 선택 뒤 `Game.CanHandleAction`과 `Game.HandleAction`으로 승급을 적용하고 50턴까지 정상 진행했사와요. 같은 언어의 checkpoint·복원 직후·최종 archive 133개 구획은 독립 새 게임 지도 GUID 16바이트만 정규화한 뒤 모두 같았고, 모든 추가 턴 의미 상태 표본·명령·이벤트도 일치했답니다. 25·50턴 공식 순위 팝업의 원문 Lua·실제 SDK 난수·타이머 수명주기도 네 실행에서 같았사와요. [고정 저장·턴 대조표](../evidence/extended_turns/20261001T115602Z_12bb487f337d/conformance.json) · [실행·계측 요약](../evidence/extended_turns/20261001T115602Z_12bb487f337d/summary.json) · [공식 UI·난수 대조표](../evidence/ui_popup/runtime/001c8e7abfed47498cb4cfb639623ca0/conformance.json)

| 언어 | worker | 실행 ID | 결과 |
|---|---:|---|---|
| 영어 | 0 | `20261001T114736Z_c14174c5919d` | 50턴 통과 |
| 한국어 | 0 | `20261001T114940Z_24a26bc651db` | 50턴 통과 |
| 영어 | 4 | `20261001T114954Z_fa4d21cff081` | 50턴 통과 |
| 한국어 | 4 | `20261001T115008Z_9f2843d6aea4` | 50턴 통과 |

별도 `--fixture-unit-actions`와 host mode `--check-save-restore-ui-actions`를 명시한 시험 입력이랍니다. `--fixture-promotions`, UI, save/restore와 추가 턴도 필요하며, 기존 직접 local-command 시험 경로는 별도 opt-in으로 보존했사와요. 선택은 `HostState::selectLocalUnit`이 fresh SDK unit wrapper를 얻어 `ICvGame1::SelectUnit(unit, true, false, false)`으로 전달한답니다. Lua는 실제 `GameInfoActions`의 타입·명령·승급 원본 ID·ActionInfoIndex·확인 팝업 여부를 대조한 뒤 action을 실행하와요. `Game.HandleAction`에서 SDK 선택 유닛과 명령 적합성을 다시 검사하고 `sendDoCommand → ResponseDoCommand → CvUnit::doCommand`으로 이어진답니다. 승급 상태·XP·readiness를 직접 쓰지 않사와요.

네 실행 모두 플레이어 0의 유닛 16385에 29턴 `PROMOTION_SHOCK_1`을 action 153으로, 38턴 `PROMOTION_SHOCK_2`를 action 152로 적용했사와요. 레벨은 1→2와 2→3이며 XP는 각각 16·30으로 유지했답니다. 각 추가 턴의 입력 경로 표기 48개와 승급당 한 개의 action 기록을 scope·순서·형식·promotion tuple까지 검증했사와요. action index를 승급 DB ID 1·2와 혼동하지 않사와요.

[LocalUnitSelection.h](../Source/Host/LocalUnitSelection.h)는 owner/unit ID만 보관하고 매번 새 wrapper를 반환한답니다. 선택·조회·명령은 소유 스레드와 GameCore lock을 요구하며, 타 플레이어·유닛 소멸·지연 사망을 발견하면 오래된 ID를 무효화하와요. 열거기는 ID snapshot·binding epoch와 SDK 방식의 참조 계수를 사용하고, 세션 언바인드 뒤에는 SDK resolver를 호출하지 않는답니다. 현재 선택과 마지막 선택은 분리했으며, 다중 선택·토글·그룹·선택 소리와 아직 구현하지 않은 trade 표시 요청은 명시적으로 거부하와요. [Host 서비스](../Source/Host/HostServices.h) · [실제 SDK 세션 바인딩](../Source/Host/LocalSdkSession.h) · [시험 입력](../Source/Host/FixturePromotionInput.h)

모형 SDK wrapper를 사용하는 `/O2`·`/Od` 구성요소 회귀는 합계 46개 검사를 통과했고 실제 소비 compiler input과 검사 전후 hash를 동결했사와요. [고정 구성요소 기록](../evidence/local_unit_selection/20261001T114433Z_9100d8ffc14d/conformance.json)은 GameCore를 로드하지 않았으며, 실제 세션 guard의 부정 입력 실행 증거로 확대하지 않사와요. 위 네 런타임은 정상 선택·승급 경로의 실제 SDK 실행 증거랍니다.

선택을 공급하는 것은 고정 fixture이며 화면에서 사용자가 클릭하는 입력은 아직 구현하지 않았답니다. 지도·유닛 renderer, 완전한 UnitPanel, 도시·여러 유닛 선택, 의사결정 팝업, 실제 키보드·마우스 전달, UI가 열린 뒤의 새 세션 복원과 retail UI 타이밍은 남아 있사와요. 실제 탐색 4워커는 여전히 scoring thread 1·max overlap 1이므로 이 입력 구현으로 멀티코어·성능·전체 엔진 완료를 주장하지 않사와요.
