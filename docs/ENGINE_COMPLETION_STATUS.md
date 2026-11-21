# 전체 엔진 완료 조건과 현재 상태

<!-- early-access-06-manual-native-20261012 -->
2026-10-12 [얼리 액세스 0.6](EARLY_ACCESS_KR.md)을 사용자용 새 게임에 연결했사와요. 생산 선택창의 컨텍스트와 원본 화면 시간 기준 보존 수정이 포함됐답니다. 전체 진척도는 여전히 **약 30%라는 거친 추정**이며 기능 목록을 실측한 완료율은 아니랍니다.

| 이번 사용자용 반영 | 확인한 범위 |
|---|---|
| 실행 묶음 | [엄격한 입력 검사](../evidence/runtime_promotion/20261012_early_access_06/runtime_validation_strict.json) 통과. 새 빌드 없이 검증된 x64 Host와 동결 UI 지원을 재사용했사와요. |
| 일반 실행·복원 | [실제 시험](../evidence/runtime_promotion/20261012_early_access_06/manual_probe_result.json) 통과. `--play`의 0턴에서 F5 저장·닫기, 별도 `--play-load`로 복원·닫기, 82,857바이트 SDK 상태 표본 일치를 확인했사와요. 사람이 한 판 플레이한 증거는 아니랍니다. |
| 기존 저장·경로 | [승격 직후 검사](../evidence/runtime_promotion/20261012_early_access_06/launcher_after.json) 12개 저장·28건 계획 통과. [실행 후 검사](../evidence/runtime_promotion/20261012_early_access_06/launcher_post_probe.json)에서 기존 저장 12개의 내용·식별자·수정 시각을 보존했사와요. 승격 전 경로 키 28개는 모두 유지했고 값 27개는 같으며, `ea:New`만 EA 0.6으로 교체했답니다. 승격 직후부터 실행 후까지 기존 28개 경로 값은 모두 같았고, 새 시험 저장 7개를 포함한 총 19개 저장·42건 계획을 확인했사와요. |
| 시험 실패 보존 | 첫 시험 도구는 실행 중 로그 잠금 때문에 실패했사와요. [실패 원문](../evidence/runtime_promotion/20261012_early_access_06/attempts/first_log_lock_failure/manual_probe_result.json)을 보존하고 도구를 수정했답니다. [첫 창의 별도 종료 기록](../evidence/runtime_promotion/20261012_early_access_06/first_probe_close.json)은 일반 실행 정상 종료만 확인하며 F5 성공으로 재분류하지 않사와요. |
| 이어하기 | 새 시험의 직접 저장만 [시험용 이름](../evidence/runtime_promotion/20261012_early_access_06/manual_probe_relocation.json)으로 보존하여, 기존 사용자 저장으로 연결되는 이어하기를 유지했사와요. |

원본 복원 검사 FAILED와 별도 보존 자료 pair PASS는 기존 범위로 유지하와요. 전체 원본 UI·세계 표시·전투와 외교·장기 캠페인·멀티코어 턴 성능·기존 문명 5 저장과 모드 호환성은 아직 남아 있답니다.

<!-- ea06-storage-retirement-20261012 -->
이번 구형 호스트 정리의 [전후 기록](../evidence/storage_cleanup/selected_ui_host_plans/20261012T133852Z_da5ce26f0cec/cleanup.json)에서는 Build·검증 폴더 8개의 2,600개 파일을 제거했사와요. 보호 파일 47,998개와 수동 실행 저장 19개의 내용·식별자·메타데이터를 보존했으며, 프로젝트 밖 Python 실행 도구는 읽기 전용으로 전후 검사했답니다. 현재 Host의 C++ 입력 64개와 Lua 소스 10개도 별도 대조로 보존했사와요. 현재 실행본·사용자 저장·원본 게임 자료는 정리 대상에 포함하지 않았사와요.

[정리 전 감사](../evidence/storage/20261012T130335Z.json)와 [정리 후 감사](../evidence/storage/20261012T135340Z.json)의 고유 파일 점유량은 **13.19→12.33GiB**, 순감소 **0.86GiB**랍니다. 정리 후 경로별 논리 합계는 45.78GiB이며 하드링크 중복과 압축 전 크기를 포함하와요. 두 감사의 오류·건너뜀은 0개이며, 이 파일 점유량 차이를 볼륨 여유 공간 증가량으로 바꾸어 설명하지 않사와요. [현재 참조 갱신 기록](../evidence/runtime_promotion/20261012_early_access_06/storage_finalization.json)에서 경로·크기·해시를 추적하와요.

다음 UI 복원 범위는 원본 `SaveMenu`의 저장 목록·이름 입력·저장·취소랍니다. 실제 문자 입력과 자식 화면의 입력 수명, 세션 내부의 이름 있는 원자적 저장을 연결해야 하와요. 원본 문명 5 저장과의 호환성·삭제·덮어쓰기·클라우드·지도 저장은 별도 관문으로 남아 있답니다. 전체 진척도는 약 30%의 거친 추정으로 유지하와요.

<!-- natural-worker-production-boundary-20261012 -->
2026-10-12 작업을 재개하고 서브에이전트 세 명의 교차 검토를 마쳤사와요. 전체 진척도는 **약 30%라는 거친 추정**이며, 기능 목록을 실측한 완료율은 아니랍니다. 이번에는 기존 F01·F07·N04의 자연 연구·정책·생산과 개발 저장의 별도 프로세스 복원 경로를 수정·검증했사와요.

| 전체 목표 | 현재 상태 | 남은 핵심 작업 |
|---|---|---|
| 64비트 구동 | 실제 SDK Host의 제한된 0→12턴 경로 확인 | 전체 게임 기능 연결 |
| 원본 UI 복원 | 주요 HUD·도시·연구·정책·생산 화면 일부 | 나머지 화면과 배치·입력 동등성 |
| 세계 화면과 한 판 플레이 | 부분 구현 | 지형·유닛 표시, 전투·외교·AI 통합 |
| 저장·불러오기 | 개발 저장으로 0→6턴 저장·별도 복원·12턴 재저장 확인 | 다양한 상태·장기 플레이의 복원 검증 |
| 멀티코어 처리 | 일부 계산 경로 검증 | 전체 턴 성능과 결과 일치 |
| 기존 저장·모드 호환 | 미완료 | 실제 원본 저장·모드 호환성 검증 |

| 이번 확인 항목 | 실제 결과 |
|---|---|
| 집중 검사 | [실행기 67개](../evidence/worker_production/20261011_natural_blocker/unstack/reminder_signal/runner/component.json)와 [최종 검증기 62개](../evidence/worker_production/20261011_production_retention/policy_order/component.json), 합계 129개 통과했사와요. 전체 프로젝트 검사 수나 전체 플레이 완료율은 아니랍니다. |
| 생산 팝업 수정 | [변경·보존 기록](../evidence/worker_production/20261011_production_retention/change.json). 같은 SDK 세션·유효 플레이어의 닫힌 Production 컨텍스트 하나와 화면 시간 기준을 함께 보존하와요. 원본 Lua/XML·완료 알림·엄격한 Meter 검사를 유지하며 저장 키·스키마·규칙·밸런스는 변경하지 않았답니다. |
| 새 x64 후보와 새 게임 | [124501 빌드](../evidence/ui_window_host/20261011T124501Z_5bf7bf678d40/build_result.json) 성공, [124731 새 게임](../evidence/interactive_game/20261011T124731Z_b821f4b6c26a/result.json) **통과**: 0→6턴, 일꾼 시설 완성, 저장 2회, 정상 종료·입력 자료 보존했사와요. |
| 복원 원문 | [125838 원본 결과](../evidence/interactive_game/20261011T125838Z_2f697438e208/result.json)는 **FAILED 그대로**랍니다. 실제 SDK는 6→12턴·저장 2회·정상 종료를 마쳤지만, 당시 검증기가 동기 콜백 순서를 잘못 기대하여 정책과 연계 검사를 실패로 기록했사와요. 원본 판정·동결 검증기는 수정하지 않았답니다. |
| 별도 보존 자료 대조 | [최종 후속 결과](../evidence/worker_production/20261011_production_retention/policy_order/postvalidation_attempts/20261011T135936Z/result.json)는 **PRESERVED_NATURAL_WORKER_UI_AND_CHECKPOINT_PAIR_PASS**랍니다. 원본 정책·생산 콜백, 일꾼 행동, 연구 완성·후속 선택, HUD 입력, 모든 생성 파일·출처 해시, 별도 프로세스의 개발 체크포인트 복원·재저장을 확인했사와요. 원본 FAILED의 재분류나 사람이 한 판 플레이한 증거는 아니랍니다. |
| 검증기 수정 | [변경·검사 기록](../evidence/worker_production/20261011_production_retention/policy_order/change.json). 외부 HUD 프레임 번호와 지속 Lua 컨텍스트 순번을 구분하고 실제 동기 콜백 순서를 검증하와요. ActionInfo의 정상 비모달 지형 선택은 전체 픽셀 계약으로 대조하며 모달 hit equality·지형 선택 차단은 엄격하게 유지했답니다. SocialPolicy는 실제 originalLayoutLua/Xml 필드의 원본 해시를 검사하와요. |
| Meter·GPU 증거 | [원본 값 보존 대조](../evidence/worker_production/20261011_production_retention/meter_retention.json)와 [실제 GPU 검토](../evidence/worker_production/20261011_production_retention/gpu_visual_review.json). 11턴 완료 팝업이 최초 Meter 값을 보존하고 원본 주문 콜백 1회 뒤 새 값으로 갱신됐사와요. [실제 GPU 파일](../Build/InteractiveGameRuntime/20261011T125838Z_2f697438e208/sessions/1f1c4710d814c21a6df4fc8e1907b3c7/play-scene-105-gpu.png)은 1280×720 개발 Host 화면이며 전체 원본 세계 화면·픽셀 동등성 증거는 아니랍니다. |
| 독립 검토 | [세 서브에이전트 기록](../evidence/worker_production/20261011_production_retention/final_review.json)에서 검증기·UI/복원·저장 공간의 범위와 미완료 관문을 교차 확인했사와요. |
| 폐기한 구형 실행 | [최근 세 묶음의 작은 진단](../evidence/worker_production/20261011_production_retention/retirement_diagnostics.json)에 114540 통과·115507 Meter 실패·123840 시간 역행 실패의 상태·해시·관찰값을 남겼사와요. raw Build/evidence와 시험 저장은 [확정 정리](../evidence/storage_cleanup/20261011T134947Z_958ea6f37c03/cleanup.json)로 제거했으며 현재 재실행 가능한 증거로 제시하지 않사와요. 앞선 105026·105954·113121도 [별도 진단](../evidence/worker_production/20261011_receiver_native/retry/retirement_diagnostics.json)만 보유하와요. |
| 사용자 자료 | [최종 전후 보존 검사](../evidence/worker_production/20261011_production_retention/manual_routes_final_preservation.json)에서 사용자 저장 12개·실행 계획 28건·실행 경로를 보존했사와요. 이 생산 수정 후보는 이후 EA 0.6 새 게임에 연결했으며, 일반 실행의 저장·별도 불러오기·정상 종료도 아래 최신 승격 기록으로 확인했답니다. |

복원 직후 SDK 의미 표본과 체크포인트 입력 바이트는 일치했사와요. SDK가 세션 시작 replay 기록 한 건을 추가하여 전체 저장 해시는 달랐으며, 133구역 중 132구역과 기존 replay 기록은 같았답니다. 전체 난수 동등성·원본 문명 5 저장 호환성·전체 UI·한 판 플레이 완료는 미검증으로 유지하와요.

10월 11~12일 구형 시험 열두 묶음의 raw Build/evidence **153,182파일·논리 합계 38.39GiB**를 다섯 확정 계획으로 정리했사와요. [094442](../evidence/storage_cleanup/20261011T094442Z_5e89fde11507/cleanup.json), [103844](../evidence/storage_cleanup/20261011T103844Z_69c2cc32923f/cleanup.json), [111433](../evidence/storage_cleanup/20261011T111433Z_e4f02efec6bf/cleanup.json), [121556](../evidence/storage_cleanup/20261011T121556Z_96ff25714fb5/cleanup.json), [134947](../evidence/storage_cleanup/20261011T134947Z_958ea6f37c03/cleanup.json)은 모두 통과했답니다. 다섯 계획의 고유 ID 기준 회수 예상치는 8.22GiB이며 볼륨 여유 공간의 실제 변화와 구분하와요. 마지막 정리에서는 보호 파일 67,910개·사용자 저장 12개의 전후 검사와 [변경 소스 8개의 내용 보존](../evidence/storage_cleanup/20261011T134947Z_958ea6f37c03/working_source_preservation.json)을 통과했사와요.

[오브젝트 5개](../evidence/build_tidy/20261011T114448Z_dc13717f6f6d/cleanup.json)와 [최근 오브젝트 10개](../evidence/build_tidy/20261011T131126Z_bbc85daeeab7/cleanup.json)도 제거했답니다. 현재 후보·새 게임·복원의 단독 텍스트/DB 7,549개는 [내용 보존 압축](../evidence/storage/20261012T111159Z_1c58f09b6a14_selected/compression.json)으로 실제 파일 점유량 0.80GiB를 더 줄였사와요. 해시·파일 ID·수정 시각을 보존했고 저장 파일·수동 EA·하드링크·읽기 전용 파일은 압축 대상에서 제외했답니다.

[앞선 검증 단계의 고유 파일 점유량](../evidence/storage/20261012T111800Z.json)은 **13.02GiB**이고, 하드링크·압축 전 크기를 포함하는 경로별 논리 합계는 46.28GiB랍니다. 측정 오류와 건너뛴 경로는 0개였사와요. [10월 11일 시작 측정 11.70GiB](../evidence/storage/20261011T090027Z.json)보다는 **1.32GiB 증가**했으며, 그 사이 추가한 새 빌드·검증 자료를 포함한 전체 변화랍니다. 삭제 논리량을 그대로 실제 여유 공간으로 설명하지 않사와요. [보관 이유와 확인 필요 후보](../evidence/storage_cleanup/20261011T134947Z_958ea6f37c03/retained_bundle_reasons.json)도 기록했으며 용도가 불분명한 기존 묶음은 임의로 삭제하지 않았답니다.

아래는 과거 시점의 기록이며 현재 완료 판정은 위 표를 기준으로 보시와요. 원본 전체 UI·세계 화면·한 판 플레이·기존 저장 및 모드 호환성은 아직 미완료랍니다.

<!-- early-access-05-known-smoke-limitation-20261010 -->
2026-10-10 **얼리 액세스 0.5**를 [사용자용 새 게임 실행기](../Play/EarlyAccess/새%20게임.cmd)에 연결했사와요. [수동 후보065253](../evidence/interactive_game/20261010T065253Z_25bd25e6bca5/request.json)은 자동 입력·시험 자금·전체 실행 제한을 사용하지 않으며, 최초 유닛 자동 선택·원본 유닛 패널·오른쪽 중복 표시 제거와 CityView 글자 묶음 배치를 포함하와요. [입력 무결성](../evidence/runtime_promotion/20261010_early_access_05/runtime_validation.json)과 [실행 경로 전후 검사](../evidence/runtime_promotion/20261010_early_access_05/launcher_after.json)를 통과했고 사용자 저장 12개를 보존했답니다. 후보의 수동 창은 이번에 실행하지 않았사와요.

[새 게임061414](../evidence/interactive_game/20261010T061414Z_954a8fa83ad8/result.json)는 원본 유닛 행동·일꾼 시설 건설·6턴·저장 2회·정상 종료를 통과했사와요. [실제 첫 화면](../Build/InteractiveGameRuntime/20261010T061414Z_954a8fa83ad8/sessions/154df6beb4d98085ab2061ed7ea47bed/play-scene-1-gpu.png)에서 개척자 원본 패널과 오른쪽 중복 제거를 확인했답니다. 이는 소유한 개발 창의 GPU 캡처이며 데스크톱·사람 플레이 증거는 아니랍니다.

**별도 복원064159는 FAILED 그대로**랍니다. 초기 저장·SDK 의미 표본은 같고, [도시 회귀](../evidence/city_view_layout/20261010_restore_label_batch/native_restore_20261010T065039Z.json)는 곡창 구매·금 4,835→4,495·건물 0→1·도시 화면 복귀를 확인했사와요. 이후 7턴 자연 기술 완성 알림을 유한 자동검사 계획이 거부해 새 저장·정상 종료까지 검증하지 못했답니다. [후속 계약](../evidence/unit_panel_integration/20261010_initial_selection/technology_award_smoke_followup.json)에 일반 플레이에서는 이 예외가 도달 불가능하다는 정적 근거와 필요한 검사 보완을 남겼사와요. 전체 복원 관문을 통과로 낮춰 잡지 않으며, 이 제한을 명시한 초기판으로 제공하와요. 이전063059는 프로세스가 종료됐지만 결과가 남지 않은 중단으로 별도 보존했답니다.

원본 전체 UI·세계 표시·전체 캠페인·기존 문명 5 저장·모드·멀티플레이 동등성은 여전히 미완료랍니다. 기존 저장은 원래 엔진으로 열리며, 새 화면은 EA 0.5 새 게임에서 확인할 수 있사와요. 다음 작업은 자연 기술 완성 뒤 원본 버튼 처리·완료된 연구 상태·후속 연구 선택을 유한 검사에 연결하고 복원 후 재저장까지 확인하는 것이와요.

<!-- visible-ui-ea04-20261010 -->
2026-10-10 사용자가 올린 EA 0.3 첫 화면에서 보이지 않던 개발 변경을 **사용자용 EA 0.4 새 게임 경로에 연결**했사와요. [새 실행기](../Play/EarlyAccess/새%20게임.cmd)는 [수동 준비본035556](../evidence/interactive_game/20261010T035556Z_6d704df23b8d/request.json)을 사용하며, 자동 시험 입력 없이 동작하와요. 기존 저장의 이어하기·불러오기는 해당 저장을 만든 버전으로 연결하므로, 이번 화면 변경은 새 게임에서 확인하는 범위랍니다.

같은 실행기로 사용자용 새 게임을 열어 [수동 시작 관찰](../evidence/runtime_promotion/20261010_early_access_04/manual_startup_observation.json)을 남겼사와요. 검증한 x64 실행 파일의 지문, 실행 연결, 0턴 초기 상태, 상단·행동·알림 패널 준비와 9,612,910바이트 초기 자동 저장을 확인했답니다. 자동 시험 입력과 전체 플레이 시간 제한은 없고 창을 그대로 두었사와요. 이 관찰은 바탕화면 픽셀·사람의 직접 조작·저장 왕복 검증을 뜻하지 않으며, 쓰기 중인 로그가 잠겨 초기 오류 부재도 확인하지 않았답니다.

| 실제 화면 변경 | 확인한 범위 |
|---|---|
| 상단 턴·날짜·도움말·메뉴 글자 잘림 수정 | 원본 크기 미지정 Stack의 크기 계산을 고쳤사와요. [실제 새 게임 화면](../Build/InteractiveGameRuntime/20261010T034034Z_9176fa0022dd/sessions/f02f043a241e05553a59b574430c7ed6/play-scene-1-gpu.png)과 복원 화면에서 표시를 확인했으며, 도시 0개의 왼쪽 정보 숨김은 원본대로 유지하와요. |
| 원본 게임 메뉴 | 상단 메뉴·Escape, 복귀·빠른 저장·확인 취소를 연결했사와요. [실제 메뉴 화면](../Build/InteractiveGameRuntime/20261010T034034Z_9176fa0022dd/sessions/f02f043a241e05553a59b574430c7ed6/play-scene-15-gpu.png)을 확인했으며, 일반 저장·불러오기·설정·재시작·포기·나가기의 하위 동작은 아직 미지원 안내랍니다. |
| 전사 모델과 대기 동작 | 기존 원본 전사 자산 묶음을 이번 사용자용 실행에도 포함했사와요. 월드·UI 각각 3개 실제 프레임의 움직임과 SDK 상태 보존을 확인했으며, 전체 6초 반복·다른 유닛·이동·전투 동작 검증은 포함하지 않사와요. |

[Host033706](../evidence/ui_window_host/20261010T033706Z_52c52260272a/build_result.json)의 [새 게임034034](../evidence/interactive_game/20261010T034034Z_9176fa0022dd/result.json)과 [별도 복원034750](../evidence/interactive_game/20261010T034750Z_77c89566944a/result.json)은 모두 통과했사와요. [새 게임 독립 검증](../evidence/game_menu_scene/20261010_native_034034/independent_validation.json)과 [복원 독립 검증](../evidence/game_menu_scene/20261010_restore_034750/independent_validation.json)은 메뉴·기존 HUD·턴 진행·저장·정상 종료·전사 대기 동작을 대조했답니다. 자동 입력과 실제 GPU 캡처의 증거이며, 지도·오른쪽 임시 패널을 포함한 원본 전체 UI 및 한 판 플레이 완료를 뜻하지 않사와요. 사용자용 조작은 [0.4 안내](EARLY_ACCESS_KR.md)에 정리했답니다.

이번 반영 전 [대체 메뉴 시험본 정리](../evidence/storage_cleanup/20261010_superseded_menu_candidates_live_alias_followup/retired.json)에서 10폴더·22,305파일을 제거했사와요. 삭제 경로의 논리 크기 6.117GiB와 다른 하드링크가 없는 파일의 사전 측정 점유량 약 4.783GiB를 구분하와요. 사용자 저장 11개와 보호 파일·생존 하드링크를 보존했고, 삭제된 012414·014720·021923 실행과 010743·014514 Host의 아래 과거 raw 링크는 현재 보유 자료가 아니랍니다. 원문 진단과 선택한 실제 GPU 9장은 [작은 압축 기록](../evidence/storage_cleanup/20261010_superseded_menu_candidates/diagnostics.json.gz)에 보존했사와요. 아래 내용은 각 시점의 이력이랍니다.

최종 0.4 검증 뒤에는 [직전 메뉴 시험본 6폴더 정리](../evidence/storage_cleanup/20261010_superseded_menu_pair_023559/retired.json)도 완료했사와요. 16,248파일의 삭제 경로 논리량은 4,754,600,103바이트, 회수 예상 점유량은 3,660,991,354바이트랍니다. 보호 파일 5,760개·사용자 저장 11개·생존 하드링크 40,293개의 전후 대조를 통과했고, 현재 수동 준비본과 최신 성공 시험본은 보존했사와요. 아래 이력의 Host023559·새 게임023901·복원024641 Build/evidence 원문 링크는 이제 폐기된 경로이며, 원문 진단 89개와 선택한 실제 GPU 6장은 [압축 기록](../evidence/storage_cleanup/20261010_superseded_menu_pair_023559/diagnostics.json.gz)으로 추적하와요. [시작 직전 용량 측정](../evidence/storage/20261010T042258Z.json)은 오류·건너뜀 없이 실제 할당량 17,177,936,719바이트(16.00GiB)를 확인했답니다. 앞선 측정 22,198,355,518바이트(20.67GiB) 대비 새 검증본·수동 준비본 증가분까지 포함한 순감소는 5,020,418,799바이트(4.68GiB)이며, 하드링크 경로를 중복 합산하지 않았사와요.

<!-- game-menu-pair-pass-and-top-panel-defect-20261010 -->
2026-10-10 [Host023559](../evidence/ui_window_host/20261010T023559Z_49c6a1742499/build_result.json)의 [새 게임023901](../evidence/interactive_game/20261010T023901Z_b061052028cb/result.json)과 [별도 복원024641](../evidence/interactive_game/20261010T024641Z_f3b22ca6ce28/result.json)이 모두 통과했사와요. 원본 게임 메뉴 12단계·Q 차단·빠른 저장을 확인했고, 새 게임은 1턴·저장 3회·정상 종료, 복원은 마지막 1턴 저장을 입력으로 2턴·저장 3회·정상 종료까지 완료했답니다. [새 게임 독립 검증](../evidence/game_menu_scene/20261010_native_023901/independent_validation.json)과 [복원 독립 검증](../evidence/game_menu_scene/20261010_restore_024641/independent_validation.json)은 실제 실행 파일·동결 소스와 입력 저장 보존을 대조했사와요. 복원 알림 검증은 빈 목록 21프레임 표시이며 클릭 증거는 아니랍니다. 전체 저장 133구역 중 132구역의 일치와 관찰한 SDK 상태의 일치를 전체 저장·난수 동등성으로 확대하지 않사와요.

복원의 [실제 1턴 메뉴 GPU](../Build/InteractiveGameRuntime/20261010T024641Z_f3b22ca6ce28/sessions/56a8f692a8f1564361d475bfb55e885b/play-scene-6-gpu.png)에서 원본 `포기` 버튼이 한국어로 표시되고 확인창 버튼 배치도 유지된 것을 확인했사와요. 1280×720 개발 창의 자동 입력 증거이며, **사용자가 열어 둔 EA 0.3에는 아직 반영하지 않았답니다.** 저장·불러오기·설정 등 하위 화면 연결과 전체 원본 UI·세계 화면 복원은 남아 있사와요.

같은 날 사용자가 현재 실제 창에서 변화가 잘 보이지 않는다고 지적했고, 상단의 메뉴·도움말·턴·날짜 글자가 잘리는 결함을 기존 EA와 최신 후보 모두에서 확인했사와요. 원본 크기 미지정 Stack이 높이 0으로 남아 자식의 y좌표가 음수가 되는 공통 배치 계산 문제랍니다. 왼쪽 정보가 도시 0일 때 숨겨지는 동작은 원본 Lua 계약이므로 유지하와요. 이 상단 배치 수정의 실제 실행 검증까지 마친 뒤 사용자용 반영을 진행하며, 아래 메뉴 시험 통과를 전체 UI 복원 완료로 계산하지 않사와요.

<!-- game-menu-native-fresh-20261010 -->
2026-10-10 배치와 창 입력 증거를 보완한 [x64 Host014514](../evidence/ui_window_host/20261010T014514Z_0a483def3217/build_result.json)의 [새 게임 통합 실행014720](../evidence/interactive_game/20261010T014720Z_fb875e0dba10/result.json)이 통과했사와요. 원본 상단 메뉴·월드 Escape 진입, 복귀·확인 취소·미지원 안내 닫기·빠른 저장과 알 수 없는 Q 키의 창 차단을 12단계에서 확인했답니다. 메뉴 조작 전후 SDK 관찰값 82,902바이트가 같았고, 이후 기존 알림·도시·연구 화면, 다음 턴·저장·정상 종료까지 통과했사와요. 저장은 빠른 저장 1회와 1턴 저장 2회이며, 전체 저장·난수 동등성이나 사람의 한 판 플레이를 증명하지 않사와요.

이 실행의 실제 GPU 캡처에서 [원본 메뉴](../Build/InteractiveGameRuntime/20261010T014720Z_fb875e0dba10/sessions/f58bfcfe7aa008a8888d4364c822ed26/play-scene-15-gpu.png) 하단 아이콘의 중앙 배치와 [확인창](../Build/InteractiveGameRuntime/20261010T014720Z_fb875e0dba10/sessions/f58bfcfe7aa008a8888d4364c822ed26/play-scene-18-gpu.png)의 Yes/No 부모 영역 내 배치를 직접 확인했사와요. 1280×720 개발 창의 제한된 비터치 장면이며 원본 실행 파일과 전체 화면·입력·애니메이션의 동등성을 확인한 결과는 아니랍니다. **아래 별도 프로세스 복원은 실패로 남겼으며, 현재 실행 중인 EA 0.3 및 사용자용 기본 실행 경로는 유지하와요.** 원본 저장·불러오기·설정 등 하위 메뉴의 기능 연결도 남아 있답니다.

후속 [별도 프로세스 복원021923](../evidence/interactive_game/20261010T021923Z_7dc72b3208dc/result.json)은 **FAILED**랍니다. 새 게임의 마지막 1턴 저장을 입력으로 삼아 초기 SDK 관찰값과 메뉴 조작 전후 상태 일치는 확인했으나, 실행부 내부의 300초 자동 입력 제한에 도달하여 이후 알림·도시 종료·턴 진행과 최종 저장·정상 종료 검증을 끝내지 못했사와요. 외부 실행기의 메뉴 시나리오 제한 900초와 내부 제한이 달랐답니다. 또한 1턴에서 표시되는 원본 포기 버튼에 `{TXT_KEY_RETIRE: upper}`가 그대로 나타나는 문자열 처리 결함을 발견했사와요. 한국어 DB에는 `포기`가 있으며 원본 XML의 표현식 처리 경계를 수정 중이랍니다. 새 게임 0턴에서 숨겨졌던 이 버튼은 앞선 화면 통과 범위에 포함되지 않으며, 이번 복원 전체를 통과로 재분류하지 않사와요.

위 결함의 [현지화 부품 수정](../evidence/game_menu_scene/20261010_restore_021923/localization_fix_component.json)은 원본 표현식 전체를 기존 변환기로 전달하며, 1턴 비터치·터치 fixture와 표시 검사에서 `포기`를 확인했사와요. 인접 HUD 회귀 2개도 통과했고 약 168MiB의 임시 시험 자료를 제거했답니다. 이 검사는 실제 DB를 사용하지만 현지화 호출 경계는 fixture이며 수정 후 실제 GPU 검증은 아직 남아 있사와요. `InteractiveGameLoop.h`의 전체 시간 조건에는 `gameMenuSmoke`만 추가하여 내부 제한을 외부와 같은 900초로 맞췄고 장면 제한·완료 조건은 유지했답니다. **이 두 소스 수정의 새 빌드·새 게임·별도 복원 검증과 사용자용 승격은 아직 전이랍니다.** [복원 독립 기록](../evidence/game_menu_scene/20261010_restore_021923/independent_validation.json)은 메뉴 12단계·Q 차단·빠른 저장 1회만 통과로 구분하며 전체 FAIL을 보존하와요.

이번 새 게임 검증 뒤 [구형 HUD 시험 세 쌍 정리](../evidence/storage_cleanup/20261010_superseded_hud_pairs/retired.json)로 Build/evidence 18폴더·39,876파일을 제거했사와요. 대상은 10월 8일 `225105/233650/224629`, 10월 9일 `065612/070344/063449`와 `080148/080652/074845` 실행·복원·Host 묶음이랍니다. 삭제 경로의 논리 크기는 11.855GiB, 다른 하드링크가 남지 않는 파일의 사전 측정 점유량은 2.646GiB였사와요. 보호 파일 5,829개·사용자 저장 10개·생존 하드링크 38,633개의 전후 검사를 통과했고, 실행 중인 EA 게임도 유지했답니다. 원문 진단 84개는 [압축 기록](../evidence/storage_cleanup/20261010_superseded_hud_pairs/diagnostics.json.gz)에서 길이·SHA 왕복을 확인했사와요. 아래 과거 기록의 해당 raw 실행본·화면·시험 저장은 이제 보유하지 않으며 압축 진단과 경로·SHA 원장으로만 추적하와요.

새 별도 복원 실행을 추가하기 전의 전체 고유 파일 점유량은 [정리 전 18.463GiB](../evidence/storage/20261010T021111Z.json)에서 [정리 후 15.836GiB](../evidence/storage/20261010T021806Z.json)로 **2.627GiB 감소**했답니다. 이 전후 값에는 정리 기록의 증가도 포함되며, 하드링크 중복과 압축 전 크기를 합한 경로별 논리 합계 42.048→30.213GiB 및 볼륨 여유 공간과 구분하와요.

<!-- game-menu-development-candidate-20261010 -->
2026-10-10 원본 게임 메뉴의 개발 연결을 포함한 [새 x64 Host](../evidence/ui_window_host/20261010T010743Z_6160fe65056b/build_result.json)가 빌드를 통과했사와요. 상단 메뉴·월드 Escape 진입, 원본 복귀·확인 취소·빠른 저장 요청을 연결하고, 확인창의 원본 마우스 차단 영역과 표시 순서를 반영했답니다. 알 수 없는 월드 키가 종료 동작으로 처리되던 경로도 수정했사와요. 원본 하위 저장·불러오기·설정 등은 아직 미연결이며 미지원 안내를 표시하와요.

첫 [실제 통합 실행](../evidence/interactive_game/20261010T012414Z_6abf227bfb5d/result.json)은 **FAILED**로 보존하와요. 메뉴 12단계와 빠른 저장 1회, 전후 SDK 관찰값 82,902바이트 동일은 확인했으나, Q 키가 창에서 차단되는 경로에 게임 처리 단계의 기록을 요구한 검사기 오류가 있었고 이후 연구 트리 진행 중 전체 300초 제한에 도달했답니다. [독립 대조](../evidence/game_menu_scene/20261010_native_012414/independent_validation.json)에서도 이 실행을 통과로 다시 분류하지 않았사와요.

[실제 GPU 화면](../evidence/game_menu_scene/20261010_native_012414/pixel_review.json)에서는 확인창의 No 버튼과 하단 아이콘이 부모 영역 밖으로 밀리는 결함도 발견했사와요. GameMenu의 크기 없는 원본 Stack에 자식 우선 크기 계산과 기존 앵커 배치를 연결하고 원본 음수 간격을 반영했답니다. [수정 부품 검사](../evidence/game_menu_scene/20261010_native_012414/layout_fix_component.json)는 비터치 243개·터치 257개, 표시 패킷 6개와 관련 HUD 회귀 2개를 통과했으며 임시 렌더 자료는 제거했사와요. 원본 Lua/XML·표시 문구·저장 스키마는 바꾸지 않았답니다.

창의 실제 Q 차단 지점을 기록하도록 보완하고 기록 검사기 20개 시험을 통과했사와요. 새 실행의 전체 제한은 추가된 메뉴 단계에 맞춰 900초까지 허용하되 개별 장면 제한 60초는 유지하와요. 네이티브 입력 수집기의 차단 영역 구분은 최적화 켬·끔 각각 87개 검사로 확인했답니다. **배치 수정 후 새 Host의 실제 화면·통합 통과·별도 프로세스 복원은 아직 검증 전이며, 현재 EA 0.3 실행본에는 이 변경을 배포하지 않았사와요.** 아래 메뉴 자산만 준비됐다는 문구는 이번 개발 연결 이전의 이력이랍니다. 부품 검사 수로 전체 UI 완료율을 올리지 않사와요.

이후 [대체된 시험본 정리](../evidence/storage_cleanup/20261010_superseded_game_menu_host/retired.json)로 Host `20261010T005010Z_6fb779d5bda3`·`20261009T152915Z_262e1edd772f`와 실패 실행 `20261009T153212Z_24547e20f8c7`의 Build/evidence 6폴더·7,900파일을 제거했사와요. 삭제 경로의 논리 크기는 2.226GiB이고, 다른 하드링크가 남지 않는 파일의 사전 측정 점유량은 1.857GiB랍니다. 보호 파일 4,936개와 생존 하드링크 이름 51,829개의 전후 검사를 통과했으며 실행 중인 EA 프로세스도 유지했사와요. 원문 진단 38개는 [작은 압축 기록](../evidence/storage_cleanup/20261010_superseded_game_menu_host/diagnostics.json.gz)에서 바이트·길이·SHA 복원을 확인했답니다. 아래 이력의 해당 구형 원본 실행·저장·화면 파일은 이제 보유하지 않으며, 삭제 목록과 압축 진단으로만 추적하와요.

<!-- early-access-03-and-game-menu-assets-20261010 -->
2026-10-10 [얼리 액세스 0.3 후보](../Play/EarlyAccess/release.json)를 [기존 EA 실행기](EARLY_ACCESS_KR.md)에 연결했사와요. [승격 기록](../evidence/runtime_promotion/20261010_early_access_03/promotion.json)의 일반 실행본 `20261009T163702Z_0461db127034`는 통과한 Host155317과 동결 지원155510을 재사용하며 원본 상단창·턴 안내·알림 패널을 포함하와요. [22개 실행 경로 검사](../evidence/runtime_promotion/20261010_early_access_03/launcher_validation_followup.json)는 기존 저장 9개의 내용·파일 식별자·수정 시각과 선택 경로를 보존했고, 신규 시작 자동 저장 1개가 새 후보로 연결되는 것도 확인했답니다. 첫 검사기의 빈 문자열 기대값·큰 정수 왕복 오류는 원문 FAIL을 유지한 별도 후속 검사로 바로잡았사와요.

[일반 실행 관측](../evidence/runtime_promotion/20261010_early_access_03/manual_startup_observation.json)은 실제 `--play ko_KR` 프로세스와 초기 자동 저장, 창 생성 뒤 기록되는 월드 generation 2와 상단창·턴 안내·알림 6개 장면 준비를 확인했사와요. 화면 조작 도구의 초기화 실패 때문에 실제 데스크톱 픽셀·직접 저장·창 닫기·사람의 한 판 플레이는 미검증이랍니다. 자동 새 게임·복원의 종료 수정 검증을 수동 종료 완료로 확대하지 않사와요. **기존 EA 0.2 저장은 해당 구형 Host로 열리므로 이번 종료 수정이 소급 적용되지 않사와요.** 아래 알림 후보의 미배포 문구와 EA 0.2 기본값은 이번 연결 전 이력이랍니다.

다음 원본 게임 메뉴의 [자산 계약 지원](../evidence/game_menu_scene/20261010_asset_contract/result.json)을 개발 소스에 추가했사와요. base `GameMenu.lua`·BNW XML·`MapUtilities`를 등록하고 원본 148개 노드·5개 하위 문맥·2개 템플릿을 보존하며 집중 검사 5개와 변조 거부 9종을 통과했답니다. 임시 시험 폴더는 모두 제거했사와요. **GameMenu의 실행·렌더링·빠른 저장 및 하위 메뉴 연결은 아직 구현 전이며, 이 자산 변경은 동결된 EA 0.3 실행본에 포함되지 않사와요.** 전체 원본 UI·3D 세계·한 판 완주·기존 저장 호환·멀티코어 성능 목표는 그대로 남아 있답니다.

이번 작업 뒤 [최신 파일 점유량](../evidence/storage/20261010T002819Z.json)은 **15.52GiB**이며, 직전 정리 직후 15.40GiB보다 약 **124MiB 증가**했사와요. 실행 자료를 재사용했고 새 일반 실행본·시작 저장·화면 준비물 등이 이 차이에 포함된답니다. 경로별 논리 합계는 38.63GiB로 하드링크·압축 중복을 포함하며 실제 점유량과 구분하와요. 이번 메뉴 시험의 임시 폴더와 파일 교체 임시물은 0개이고, 실행 중인 게임·저장·동결 입력은 보존했사와요.

<!-- notification-panel-candidate-20261009 -->
2026-10-10 원본 알림 패널을 포함한 [x64 후보](../evidence/ui_window_host/20261009T155317Z_8f390480966b/build_result.json)의 [새 게임 통합 검증](../evidence/interactive_game/20261009T155510Z_59a23754e9cf/result.json)과 [별도 프로세스 저장 복원](../evidence/interactive_game/20261009T160013Z_804760e7018f/result.json)이 통과했사와요. 새 실행에서는 원본 Lua/XML을 유지하며 생산 알림 클릭, 닫을 수 없는 알림의 거절, 생산 선택 뒤 해당 알림 제거, 다음 턴·저장·정상 종료를 확인했답니다. 복원은 초기 상태 일치와 빈 SDK 알림 목록의 18개 프레임 표시, 2턴 진행·재저장·정상 종료까지이며 알림 클릭이나 비어 있지 않은 목록의 복원을 검증한 결과는 아니랍니다. **사용자용 기본 실행본으로 배포하지 않았으며, 사람이 정상 한 판을 플레이하거나 원본 전체 UI의 동등성을 확인한 결과도 아니랍니다.**

[독립 검토](../evidence/notification_panel_scene/20261010_native_155510/independent_validation.json)는 거절 예외를 변조한 11건이 계속 실패하는지, SDK 상태 보존·알림 제거·각 저장 2회·명령 수 한도를 대조했사와요. 복원 저장의 133구역 중 132구역은 같고 전역 Game 구역은 달라서 전체 저장 바이트·난수 동등성은 미확인으로 유지하와요. 새 실행의 [실제 GPU 검토](../evidence/notification_panel_scene/20261010_native_155510/pixel_review.json)에서 원본 알림 아이콘과 생산 화면 연결, 정상 한글 거절 안내, 생산 아이콘 제거를 확인했답니다. 1280×720 숨김 창 캡처의 제한된 장면이며 원본 실행 파일과의 픽셀·애니메이션 동등성은 입증하지 않사와요.

정상적인 빈 알림 목록과 14개 분류의 원본 고정 큰 버튼을 처리하도록 표시 계약을 수정했사와요. 이후 [실행 153212](../evidence/interactive_game/20261009T153212Z_24547e20f8c7/result.json)은 알림 조작·제거를 끝냈으나 닫기 거절 안내의 한글 인코딩 손상과 거절 분류 때문에 FAILED로 남겼답니다. 신규 안내 문구 5개를 동일 내용의 Unicode escape로 바꾸고, 완전한 알림 입력 타임라인 안의 정확한 거절 한 번만 허용하도록 검사기를 수정한 뒤 위 새 실행으로 검증했사와요. 기존 실패 결과와 로그는 다시 분류하지 않았답니다. [GPU 표시 검토](../evidence/notification_panel_scene/20261010_native_153212/pixel_review.json)에서는 원본 연구·생산 원형 아이콘의 위치와 생산 아이콘 제거를 확인했으며, 처음 아이콘을 잘못 식별한 검토의 정정 이유와 이전 SHA도 보존했사와요.

[원본 UI 부품 검사](../evidence/notification_panel_scene/20261009_original_context/result.json) 142개, 창 표시 부품 검사 167개, 알림 타임라인·표시 계약 검사 각 15개를 통과했사와요. 원본 SDK 목록의 최대 활성 99행을 사용한 [분리된 Lua 검사](../evidence/notification_panel_scene/20261010_capacity/bounded_limits.json)에서 기존 명령 수 한도 부족을 확인하여 알림 목록 갱신·종료에만 별도 한도를 적용했답니다. 일반 입력의 한도는 유지하며, 이는 실제 게임의 모든 알림 종류나 99행 GPU 성능을 검증한 결과는 아니랍니다.

이번 통합 검증 뒤 [실패 실행 두 묶음 정리](../evidence/storage_cleanup/20261010_failed_notification_runs/cleanup.json)로 Build/evidence 네 폴더의 1,955파일·논리 797,627,838바이트를 제거했사와요. 보호 파일 6,488개, 외부 하드링크 생존 경로 16,109개, 기존 사용자 저장 8개와 EA 자동 저장 1개의 내용을 전후 대조했답니다. 실패144109·145225의 원문 65건은 2,834,498바이트의 [진단 보관본](../evidence/storage_cleanup/20261010_failed_notification_runs/diagnostics.json.gz)으로 복원 검증했으며 삭제한 raw 실행본을 현재 실행 근거로 사용하지 않사와요.

최신 Host155317과 새 실행155510·복원160013의 단독 파일 2,921개는 [내용 보존 압축](../evidence/storage/20261009T161208Z_c3f1233bada4_selected/compression.json)으로 559,899,227바이트를 줄였사와요. 삭제와 압축 전후 전체 고유 파일 할당은 [16.43GiB](../evidence/storage/20261009T160543Z.json)에서 [15.40GiB](../evidence/storage/20261009T162256Z.json)로 약 **1.03GiB 감소**했으며, 정리 후 경로별 논리 합계는 38.44GiB랍니다. 새 자료와 압축 전 크기·하드링크 중복을 포함하는 논리 합계를 실제 점유량과 혼동하지 않사와요. 이보다 앞선 [오브젝트 5개 정리](../evidence/build_tidy/20261009T155135Z_0cc69aaccaa2/cleanup.json)의 29,786,839바이트는 이번 전후 측정 구간에 포함하지 않사와요. 사용자 기본 실행 경로·원본 설치본·MODS·저장 형식은 유지했답니다.

2026-10-09 후속 수동 실행에서 EA 0.2 창이 종료되고 “Window creation is one-shot or renderer allocation failed” 오류가 확인됐사와요. [종료 기록](../evidence/runtime_promotion/20261009_early_access_02/manual_exit_observation.json)은 처음 창이 열렸던 증거와 별도로 보존했답니다. 창 처리 중 재진입하는 닫기 요청과 닫힌 창의 재생성 경로를 개발 소스에서 보완하여 [실제 창 부품 검사](../evidence/bitmap_window/20261009T141826Z_9b822ceecc4c/conformance.json)와 위 최신 x64 새 게임·복원의 자동 입력 정상 종료를 통과했사와요. 구형 수동 종료의 정확한 원인은 확정하지 않았으며 수정 후보의 수동 플레이 재검증·배포도 아직 전이랍니다. 아래 EA 0.2의 시작 성공은 수동 플레이 안정성 완료를 뜻하지 않사와요.

<!-- current-early-access-and-ui-priority-20261009 -->
2026-10-09 사용자용 **얼리 액세스 0.2**를 [이용 안내](EARLY_ACCESS_KR.md)에 연결했사와요. 수동 실행본 `20261009T132430Z_a0a5dd8fd007`는 Host `20261009T123034Z_dce2558fb5c5`와 검증된 동결 UI 도구를 사용하며 원본 턴 안내 버튼을 포함하와요. [실행 입력·경로 20개 검사](../evidence/runtime_promotion/20261009_early_access_02/runtime_and_launcher_validation.json)를 통과하고 기존 저장 8개의 SHA를 보존했답니다. 자동 입력 없는 [일반 새 게임 창 생성·응답](../evidence/runtime_promotion/20261009_early_access_02/manual_startup_observation.json)까지 확인했으며 사람이 한 판을 완주한 증거는 아니랍니다.

UI 우선 작업의 첫 범위는 **턴 안내·알림·메뉴·툴팁과 기존 도시·연구·생산 화면의 정상 새 게임 진입 연결**이랍니다. 이후 전체 외교·종교·세계 의회·문화 정보창·문명 백과사전·설정·원본 저장 화면, 입력과 배치의 동등성으로 넓히와요. 등록된 화면 종류나 자동 검사 수를 전체 UI 완료율로 계산하지 않사와요. 현재 기록에는 전체 기능군의 실측 처리 속도가 없어 확정 완료일을 산출할 수 없답니다.

원본 ActionInfoPanel은 [새 실행의 입력 5개](../evidence/interactive_game/20261009T130410Z_7c35d16e64b9/action_info_panel_validation_followup_coverage.json)와 [복원의 입력 3개](../evidence/interactive_game/20261009T131452Z_16632c1f4d4a/action_info_panel_validation_followup_coverage.json), 각 실행의 실제 다음 턴과 저장 2회를 검증했사와요. 원본 XML 트리·좌우 콜백·로컬 패킷에서 실제 월드 입력 좌표까지 대조했으며, [GPU 표시 검토](../evidence/action_info_panel_scene/20261009_native_130410/pixel_review.json)에서 연결된 19장면과 직접 본 한글 상태 5장도 확인했답니다. 검사기 초기 실패와 보완 전 보고서는 후속 보고서의 SHA 계보로 보존했으며, 검사기 수정으로 게임을 재실행한 것은 아니랍니다.

복원 초기 SDK 상태와 체크포인트 복사본은 일치하고 저장 133구역 중 132구역이 같았사와요. 달라진 Game 구역의 내부 재로딩 정보·난수 동등성은 미검증이랍니다. 내장 NotificationPanel·전체 알림·툴팁·자동 유닛 순환과 원본 전체 UI 동등성도 남아 있사와요. 실패 Host와 성공 빌드의 불필요한 OBJ 정리로 약 111.97MiB를 회수했으며, 추가 보관 압축은 실행 중인 수동 게임을 보호하는 조건 때문에 적용하지 않았답니다. 아래 기록의 진척도·용량·수동 기본값은 각 시점의 이력이랍니다.

<!-- current-economic-overview-20261009 -->
2026-10-09 경제 개요는 기존 F01·F07·N04 범위에서 **x64 새 실행과 저장 복원 자동 검증을 통과**했사와요. [현재 Host 후보](../evidence/ui_window_host/20261009T110943Z_83f88f1ab72f/build_result.json)는 원본 부모·일반·행복 화면을 별도 Lua VM으로 연결하며, 숫자 서식의 실제 provider 호출, 부모·자식 표시 시각 전달, 원본 가로 구분선의 정확한 atlas 영역 처리를 수정했답니다. renderer 계약 15개와 독립 검사기 계약 11개가 통과했고, 선택한 일반·행복·생산 GPU 캡처 3장에서는 뚜렷한 겹침·잘림을 찾지 못했사와요.

| 검증 | 결과와 근거 |
|---|---|
| 새 실행 | [native PASS](../evidence/interactive_game/20261009T112544Z_22caa6e51793/result.json), [독립 재평가 PASS](../evidence/interactive_game/20261009T112544Z_22caa6e51793/economic_overview_validation_followup.json). 원본 UI 18행동, 생산 취소·선택·복귀, 다음 턴과 서로 다른 저장 2개를 확인했답니다. |
| 저장 복원 | [native PASS](../evidence/interactive_game/20261009T113226Z_8b96bad78523/result.json), [독립 검사 PASS](../evidence/interactive_game/20261009T113226Z_8b96bad78523/economic_overview_validation.json). 첫 실행의 저장에서 시작해 경제 화면 조작·생산 변경·다음 턴·재저장을 확인했답니다. |

검사기의 초기 실패는 동일 생산 버튼의 좌클릭·우클릭 항목을 중복 좌클릭으로 센 결함이었으며, 수정 전 [FAIL 원문](../evidence/interactive_game/20261009T112544Z_22caa6e51793/economic_overview_validation.json)과 SHA를 별도 재평가 보고서에 보존했사와요. 이 결과는 준비된 SDK 시험 장면의 hidden HWND 입력과 후보 렌더러에 대한 증거랍니다. 원본 전체 표시 동등성, 문명 백과사전 우클릭 연결, 일반 새 게임부터 사람이 하는 전체 플레이는 미완료이며, 수동 기본 실행본과 전체 추정 약 30%는 유지하와요.

<!-- current-economic-cleanup-20261009 -->
경제 새 실행·복원 통과 뒤 [최종 정리 결과](../evidence/storage_cleanup/20261009_failed_economic_runs/summary.json)는 실제 점유량 **13.62→9.39GiB**, **4.23GiB·31.05% 감소**랍니다. 실패 실행 두 묶음과 대체 Host의 여섯 폴더·9,936파일을 삭제하고, 통과한 두 실행의 비공유 DB/DDS 891개는 SHA를 유지한 NTFS 압축으로 줄였사와요. 보호 파일 43,412개를 삭제 전후 대조했고, [수동 실행 경로 10개·기존 저장 8개](../evidence/storage_cleanup/20261009_failed_economic_runs/post_cleanup_validation.json)도 유지됐답니다. 삭제한 진단 원문 64경로는 2,854,145바이트의 [압축 원문](../evidence/storage_cleanup/20261009_failed_economic_runs/diagnostics.json.gz)으로 복구 검증했사와요. 경로별 논리 합계는 27.88GiB로, 하드링크 중복과 압축 전 크기를 포함한 값이랍니다. 이 정리 계획은 이미 적용했으므로 다시 실행하지 않사와요.

미실행·대체 Host 네 묶음의 [정리 결과](../evidence/storage_cleanup/20261009_economic_build_retries/cleanup.json)는 2,608파일·918,475,719바이트 제거, 보존 파일 91,454개 전후 SHA 일치와 수동 저장 8개 보존이랍니다. [정리 전](../evidence/storage/20261009T102830Z.json)·[정리 후](../evidence/storage/20261009T110152Z.json) 실제 점유량은 8.98→8.13GiB이며, 뒤이어 생성하는 실행 검증 자료는 이 정리 후 수치에 포함되지 않사와요. 삭제한 빌드의 진단 78개는 780,281바이트의 [압축 원문](../evidence/storage_cleanup/20261009_economic_build_retries/diagnostics.json.gz)으로 보존했답니다. 이전 삭제 계획은 다시 적용하지 않사와요.

<!-- current-storage-reduction-20261009 -->
2026-10-09 추가 [정리 결과](../evidence/storage_cleanup/20261009_compact_working_set/summary.json)는 실제 파일 점유량 **10.88→7.96GiB**, **2.93GiB·26.90% 감소**랍니다. 실패/대체 시험본·구형 빌드와 미사용 캐시 5,891개를 삭제하고, 보존할 동결 소스·검증 기록 9,034개는 내용·경로·수정 시각을 유지한 NTFS 압축으로 줄였사와요. 삭제 전후 보호 파일 90,775개와 압축 대상 전체 해시가 같았으며 사용자 저장 8개·새 게임/이어하기/불러오기 경로 10건을 확인했답니다. 경로별 표시 크기는 **26.21→23.61GiB**이며 하드링크 중복과 압축 전 크기가 포함된답니다. 원본 설치본·MODS·실행 기본값·저장 형식은 바꾸지 않았사와요.

퇴역한 RANGE 시험 20261007T191737Z_cb79c4f6eb96의 원래 FAILED 결과와 독립 재검증 PASS, 제어 장면·상태·규칙 DB·입력 열거형 원문은 [약 3.9MiB 진단 보관본](../evidence/storage_cleanup/20261009_compact_working_set/retired-diagnostics.json.gz)에 원본 바이트와 SHA로 보존했사와요. 구형 기술 트리 시험 20261003T151838Z_d5129b807a9a와 Host 20261007T190026Z_e8927b74abf4도 raw 실행 묶음은 퇴역했으며, 이전 문서의 해당 경로는 현재 보유 실행본을 뜻하지 않사와요. 최신 정책·신조·교역로 쌍, 선전포고 이동/복원, 수동 실행과 사용자 저장, 원본 CPU 추적 2개는 보존했답니다.

<!-- current-tenet-cleanup-20261009-stage17 -->
2026-10-09 앞선 [정리 결과](../evidence/storage_cleanup/20261009_failed_tenet_stage17/summary.json)는 실제 파일 점유량 **14.22→10.88GiB**, **3.34GiB·23.48% 감소**랍니다. 새 검증 자료까지 포함한 값이며 최초 25.63GiB 대비 누적 57.53% 감소했사와요. 실패 시험본 6,467개와 불필요한 오브젝트 5개를 삭제하고, 새 게임·복원 두 시험본의 DB·텍스처 831개만 무손실 압축했답니다. 삭제 전후 보호 파일 32,273개와 압축 대상 전후 해시가 같으며 사용자 저장 8개·실행 경로 10건도 보존했사와요. 오브젝트 정리는 위 측정 전이며, 경로별 파일 크기 합계 26.21GiB에는 하드링크 중복과 압축 전 크기가 포함된답니다.

[새 게임 신조 검사](../evidence/interactive_game/20261009T080148Z_94a71ea1588c/policy_tenets_validation.json)와 [별도 프로세스 복원 검사](../evidence/interactive_game/20261009T080652Z_ba55a6903d7e/policy_tenets_validation.json)가 모두 통과했사와요. 시험 전제로 이념을 준비한 뒤 원본 선택·취소·확인 입력으로 1단계 신조를 무료 2회, 문화 25를 소비하여 1회 채택했답니다. 취소 시 상태 보존·닫기/재열기/Escape·정상 턴 진행과 각 저장 2회를 확인했고, 복원에서는 추가 시험 지급 없이 신조 정보와 플레이어 저장 구역이 일치했사와요. 최초 검사기의 닫기 상태·팝업 기본값 판정 오류는 수정했으며 실패 판정과 당시 진단은 위 압축 보존 목록에 남겼답니다.

원본 정책 탭의 이념 신조 제외 조건을 바로잡고, [원본 실행 파일의 스크롤 막대 기본 동작](../evidence/social_policy_scene/20261009_original_scrollbar_default/result.json)을 확인하여 내용이 넘치지 않는 패널의 막대를 숨기도록 연결했사와요. [표시 부품 검사](../evidence/social_policy_scene/20261009_auto_scroll_visibility/result.json)도 통과했답니다. **정상 이념 선택·2/3단계 신조·차단된 정책 계열 전환·이념 변경·원본 전체 화면 동등성과 정상 한 판 플레이는 미완료**랍니다. 수동 기본 실행본과 전체 추정 약 30%는 유지하며, 아래는 이전 단계의 검증 기록이와요.

2026-10-09 07:21 UTC [최종 정리 기록](../evidence/storage_cleanup/20261009_failed_policy_tenet_064236/summary.json)의 NTFS 고유 파일 점유량은 **25.63→9.49GiB**, 누적 **16.14GiB·62.98% 감소**랍니다. 이번 후속 정리로 대체된 정책 Host/실패 실행의 8개 폴더·6,335개 파일을 삭제하고, 성공 실행 두 묶음의 DB/DDS 775개를 내용 변경 없이 압축해 약 1.68GiB를 줄였사와요. 마지막 삭제 전후 보호 파일 18,899개의 SHA가 같고, [사용자 저장 8개·실행 연결 10건](../evidence/storage_cleanup/20261009_failed_policy_tenet_064236/post_cleanup_validation.json)을 확인했답니다. 필요한 진단 43개는 합계 약 1.99MiB gzip으로 보존했사와요. [실측](../evidence/storage/20261009T072102Z.json)의 경로별 논리 합계는 22.10GiB이며, 9.49GiB는 하드링크 중복과 NTFS 압축을 반영한 점유량이랍니다. 이전 8.75GiB 측정 뒤 새로 통과한 정책 새 게임·복원 자료가 추가되었으며 아래의 다른 용량은 각 당시 기록이와요.

정책의 최신 [Host `20261009T063449Z_4cc92cfed9b4`](../evidence/ui_window_host/20261009T063449Z_4cc92cfed9b4/build_result.json)에서 [새 게임](../evidence/interactive_game/20261009T065612Z_717e525d9e22/social_policy_validation.json)과 [별도 프로세스 복원](../evidence/interactive_game/20261009T070344Z_3ac99a0df5c9/social_policy_validation.json)이 모두 **네이티브 실행 및 독립 검사 PASS**랍니다. 새 게임은 원본 취소 시 상태 보존·분기 0 채택으로 자동 정책 6 추가·정책 7 채택·원본 정책/이념 탭·설정·닫기/복귀·정상 0→1턴과 저장 2회를 확인했사와요. 시험 전용 문화 지급 뒤 실제 SDK 비용 25·30을 각각 소비했으며 게임 밸런스는 바꾸지 않았답니다. 복원은 원본 저장의 SDK 정책 보유 정보와 플레이어 구역 일치·추가 시험 지급 없음·1→2턴·재저장 2회를 확인했사와요. 저장 133개 구역 중 Game 구역만 다르며 난수 동등성은 미검증으로 남겼답니다.

이번 수정은 원본 정책 탭의 순차 분기 목록과 도시 유무를 장면 메타데이터에 넣고, 소유·문화 부족·도시 없는 상태의 버튼 검증과 실제 manifest 저장 누락을 바로잡았사와요. 원본 두 개의 크기 0×0 AlphaAnim 라벨 감싸기는 정확한 속성을 확인하여 허용했으며 [집중 검사 21개·실제 SDK 장면 변환](../evidence/social_policy_scene/20261009_policy_tenet_alpha/result.json)과 [저장 manifest 재검증](../evidence/social_policy_scene/20261009_policy_branch_eligibility/manifest-roundtrip-result.json)을 통과했답니다. **차단된 정책 분기 전환·이념 신조 선택·이념 변경, 하단 ScrollBar 넘침, 원본 전체 픽셀 동등성과 정상 한 판 플레이는 남아 있사와요.** 수동 기본 실행본·교역로 통과 쌍과 전체 추정 약 30%는 유지하와요.

삭제된 Host12/Fresh10/Fresh11/Fresh12와 이전 부품 검사의 입력은 [원본 경로·SHA·압축 진단 매핑](../evidence/storage_cleanup/20261009_failed_policy_tenet_064236/retired_reference_index.json)으로 추적하와요. Fresh10의 첫 GPU 프레임 14에 정책창이 없다는 이전 판독은 오류였으며, 원본 픽셀과 정정 보고서를 함께 보존했답니다. 당시 실패 판정은 그대로이며 최신 통과 근거는 위 새 게임·복원 쌍이랍니다.

2026-10-09 기존 N02/N04 범위에서 개발 소스의 UI 장면 준비 비용을 줄였사와요. 원본 FPK 네 개의 전체 SHA 검사를 생성 전후 각각 네 스레드로 실행하며, 원본 검증과 출력 순서는 유지하와요. [같은 입력의 순차/병렬 비교](../evidence/ui_preparation_benchmark/20261009T015540Z_09a6ff4c0592/result.json)에서 각 방식 3회 중앙값은 도시 화면 **2.91→2.61초**, 상단창 **2.71→1.38초**, 교역로 **3.24→2.39초**였답니다. 18회 모두 화면 명령·텍스처·원본 사본의 경로별 크기와 SHA가 같고, 기존 자산 검사 92개와 병렬/변조 검사 7개도 통과했사와요. 이는 준비 함수만의 측정이며 전체 턴·실게임 속도나 물리 멀티코어 추적의 증거로 확대하지 않사와요. 수동 실행본 승격과 새 Host 실행은 하지 않았고 전체 추정 약 30%도 유지하와요. 시험 임시물 제거 후 [실제 점유량](../evidence/storage/20261009T015904Z.json)은 **8.80GiB**랍니다.

2026-10-09 [최신 정리 결과](../evidence/storage_cleanup/20261009_trade_route_pair_cleanup/summary.json)의 NTFS 고유 파일 점유량은 **25.63→8.80GiB**, 누적 **16.83GiB·65.66% 감소**랍니다. 직전 9.06GiB 측정 이후 만든 별도 프로세스 복원 검증 자료까지 포함했사와요. 구형 Host와 교역로 실행 두 묶음의 Build/evidence 여섯 폴더·11,555개 파일을 삭제하고, 새 복원 DB/DDS 416개는 내용 변경 없이 압축했답니다. 삭제 전후 보호 파일 80,355개의 SHA가 같으며 사용자 저장 8개·실행 경로 10건도 재확인했사와요. 경로별 파일 크기 합계는 21.33GiB이고, 여기 보고한 점유량은 하드링크 중복과 NTFS 압축을 반영한 파일 데이터 크기랍니다.

2026-10-09 [추가 용량 정리](../evidence/storage/20261008T164816Z_2268d33ad2b9_cold/final_summary.json) 직후 NTFS 고유 파일 점유량은 **13.10→8.34GiB**랍니다. 앞선 대량 정리 전 **25.63GiB 대비 총 17.29GiB·67.46% 감소**했사와요. 이번에는 cold Build/evidence 7,507개를 검토하여 7,500개를 내용 변경 없이 압축하고 절감 없는 7개는 원복했답니다. 보호 파일 4,606개 해시와 사용자 저장 8개·실행 연결 10건을 재확인했사와요. 현재 실행본·사용자 저장 의존 버전·재사용 빌드 캐시는 제외했으며, 아래 용량은 각 당시 기록이랍니다.

교역로 [Host 224629](../evidence/ui_window_host/20261008T224629Z_ee41544939ef/build_result.json)의 [새 게임 225105](../evidence/interactive_game/20261008T225105Z_a09bb643b908/trade_route_validation.json)와 [별도 프로세스 복원 233650](../evidence/interactive_game/20261008T233650Z_5cfa5136b39e/trade_route_validation.json)이 모두 **독립 검사 PASS**랍니다. 원본 1턴 저장과 복사본·복원 초기 SDK 상태가 일치하고, 세 탭·금 수익 정렬·닫기/재열기/Escape의 실제 입력 9건 뒤 2턴 진행·저장 2회·정상 종료를 확인했사와요. 저장 133개 구역 중 132개는 같고 Game 구역만 달랐으며, 그 내부 변화의 reload metadata·난수 동등성은 별도 미검증으로 남겼답니다. 휠은 내용이 넘치지 않는 상태에서의 입력 소비만 검증했으며 사람의 플레이·원본 전체 화면의 증거는 아니랍니다. 수동 기본 실행본과 전체 추정 약 30%는 유지하와요. 아래 실패 기록은 수정 전 이력이랍니다.

2026-10-09 앞선 [용량 정리 결과](../evidence/storage_cleanup/20261008T141026Z_retirement_plan/final_summary.json)는 NTFS 고유 파일 점유량 **25.63→12.57GiB, 13.06GiB·50.97% 감소**랍니다. 대체된 빌드·실패/구형 시험의 50개 폴더·43,436개 파일을 삭제하고, 완료된 보관 시험의 DB/DDS 1,568개를 내용 변경 없이 압축했사와요. 삭제 전후 보호 파일 40,825개의 해시가 같았고, 후속 압축도 각 파일의 전후 SHA가 같았답니다. 사용자 저장 8개와 New·Continue·저장별 Load 경로 10건의 [정리 후 검사](../evidence/storage_cleanup/20261008T141026Z_retirement_plan/post_cleanup_validation.json)도 통과했사와요. 이 값은 하드링크 중복과 압축을 반영한 파일 점유량이며 볼륨 여유 공간이나 실게임 플레이의 증거는 아니랍니다. 아래의 다른 용량 수치는 당시 기록이며, 새 작업 전 점검과 폐기 가능한 산출물 10GiB 초과 시 다음 빌드 전 정리를 [작업 규칙](../AGENTS.md)에 반영했사와요.

구형 교역로 Host `135705`와 실행 `140841`·`161612`의 원본 Build/evidence는 최신 새 게임·복원 쌍으로 대체하여 삭제했사와요. `140841`은 문명 아이콘 처리에서 실패했고, `161612`의 자체 PASS 표시는 실제 탭 입력을 재검사했을 때 인정되지 않았답니다. 경로·크기·SHA는 [압축 삭제 목록](../evidence/storage_cleanup/20261009_trade_route_pair_cleanup/recovery_01/retired-files.jsonl.gz)에, 당시 결과는 [상태 기록](../evidence/storage_cleanup/20261009_trade_route_pair_cleanup/recovery_01/retired-statuses.json.gz)에 남겼사와요. 현재 통과 근거는 위 `225105`·`233650` 쌍이며, 삭제된 구형 원본 링크를 현재 증거로 사용하지 않사와요.

2026-10-08 상단창 통합 검증 뒤 [정리 결과](../evidence/storage_cleanup/20261007T203350Z_manual_retirement_draft/summary.json)로 대체된 수동 실행본·Host·실패 시험의 Build/evidence **16개 폴더, 6,221개 파일·논리 2.36GiB**를 제거했사와요. [정리 전](../evidence/storage/20261007T210827Z.json)과 [정리 후](../evidence/storage/20261007T212931Z.json)의 NTFS 고유 파일 점유량은 **19.24→17.44GiB, 1.81GiB 감소**했답니다. 삭제 전후 보호 경로 54,726개의 해시가 같았으며, [삭제 후 경로 검사](../evidence/storage_cleanup/20261007T203350Z_manual_retirement_draft/post_cleanup_validation.json)에서 사용자 저장 8개와 New·Continue·저장별 Load 10건을 확인했사와요. 실패 자동시험의 저장 3개도 경로·크기·SHA가 고정된 폐기 목록에 포함했으며 사용자 저장과 겹치지 않사와요. 최신 상단창 새 게임·복원, 현재 수동 실행본과 필요한 선전포고·CPU 검증 자료는 보존했답니다. 아래의 14.80GiB 등 이전 수치는 해당 당시 기록이랍니다.

2026-10-08 당시 Host `20261007T205518Z_12228ee7e01b`와 새 게임 `20261007T210013Z_55d5320ad39d`·복원 `20261007T210357Z_334991eea806`은 원본 BNW 상단창의 과학 표시 클릭 → 기술 트리 → Escape 복귀와 턴·저장을 확인한 이력이랍니다. 이 범위는 위 최신 교역로 통과 쌍에 포함되어 구형 raw 자료를 폐기했사와요. 당시 결과는 [압축 진단 기록](../evidence/storage_cleanup/20261009_top_panel_retention_review/retired-diagnostics.json.gz), 경로·크기·SHA는 [삭제 목록](../evidence/storage_cleanup/20261009_top_panel_retention_review/retired-files.jsonl.gz)으로 추적하며 현재 보유 실행본으로 제시하지 않사와요.

최신 통과한 교역로 Host 224629의 상단창은 원본 callback 8개 중 과학·교역로 2개를 연결했사와요. **이 통과 실행본의 정책·문화 개요·종교·경제 현황·백과사전·메뉴 6개는 아직 미연결 상태**랍니다. 정책 추가 연결은 문서 상단의 Host 063449 새 게임·복원 쌍에서 별도로 통과했사와요. 따라서 `--top-panel` 시험 옵션에 한정하며 수동 기본 실행본에는 승격하지 않았답니다. 툴팁 표시·설정 반영, 숫자에 남는 따옴표, 원본 전체 배치와 다른 화면 통합도 미완료랍니다. 이 제한된 시험 통과로 전체 추정 **약 30%**를 올리거나 정상 한 판 플레이를 완료로 표시하지 않사와요. 상세 증거와 변경 범위는 [연속 실행 기록](CONTINUOUS_PLAY.md)에 연결했답니다.

2026-10-08 수동 새 게임 기본값은 `20261007T202612Z_d895c0fe84ab`로 갱신했사와요. [승격 기록](../evidence/runtime_promotion/20261007T203124Z/promotion.json)과 [경로 검사](../evidence/runtime_promotion/20261007T203124Z/launcher_validation.json)에서 New·Continue·저장별 Load 총 10건, 사용자 저장 8개의 해시 보존을 확인했답니다. 선전포고 검증을 통과한 Host와 원본 Warrior/IdleA·애니메이션 의존성·동결 UI 지원물을 함께 연결했으며, 기존 저장 세 버전은 해당 저장용으로 유지하와요. 원본 유닛 자료를 빠뜨린 직전 준비본의 승격은 [별도 철회 기록](../evidence/runtime_promotion/20261007T202716Z/replacement_candidate_status.json)으로 남겼답니다. 이 연결 검사는 사람의 한 판 플레이 증거가 아니랍니다.

2026-10-08 개발 후보 [Host `20261007T192802Z_20ff3a2b797c`](../evidence/ui_window_host/20261007T192802Z_20ff3a2b797c/build_result.json)에서 원본 선전포고 확인창의 No·Escape·Yes, 실제 SDK 전쟁·외교·이동 공격과 AI 응답을 연결했사와요. [이동 공격 실행](../evidence/interactive_game/20261007T192923Z_503f1dbbd104/result.json)은 43개 프레임·저장·정상 종료를, [그 저장의 별도 프로세스 복원](../evidence/interactive_game/20261007T193254Z_1453ea25dd27/result.json)은 초기 상태 일치·41개 프레임·턴 진행·재저장을 통과했답니다. 이전 Host의 원거리 실행은 검사기의 입력 enum 혼동만 바로잡아 [별도 재검증 통과](../evidence/interactive_game/20261007T191737Z_cb79c4f6eb96/declare_war_revalidation.json)를 기록했고, 당시 FAILED 결과는 그대로 보존하와요. 전체 추정 약 30%를 유지하며, 수동 기본값은 위 승격 기록을 따르와요.

2026-10-08 최신 시험 뒤 [추가 정리](../evidence/storage_cleanup/20261007T193212Z_c1a07d6e4b39/summary.json)로 대체된 Host와 실패 실행의 Build/evidence 6개 폴더·8,463개 파일·논리 2.63GiB를 제거했사와요. NTFS 고유 파일 점유량은 **16.79→14.80GiB, 1.99GiB 감소**했답니다. 보호 경로 43,558개의 정리 전후 해시가 같으며 사용자 저장 8개와 실행 경로 10건도 다시 확인했사와요. 이전 실패 snapshot을 이용한 렌더링 진단은 작은 보고서·SHA와 삭제 기록만 남겼고, 최신 이동·복원 및 원거리 재검증의 원본 자료는 보존하와요.

같은 날 [앞선 정리](../evidence/storage_cleanup/20261007T185251Z_9a72c5df1e41/summary.json)는 8개 폴더·8,032개 파일·논리 2.55GiB를 제거하여 당시 파일 점유량을 14.39→12.44GiB로 줄였사와요. 이 이전 측정에는 뒤이어 만든 성공 실행·복원 자료가 포함되지 않사와요.

2026-10-08 현재 전체 목표는 **원래 문명 5의 UI·조작·3D 세계 화면을 유지한 64비트 실행과 멀티코어 활용**이랍니다. 게임 상태를 소유하는 x64 실행부·GameCore, 실제 독립 게임 계산의 멀티코어 실행, 기존 규칙·선택한 모드·저장 호환성과 유용한 성능 검증을 포함하와요. [기존 F01–F07/N01–N04 기준](ENGINE_PLAN.md)의 범위를 유지하며 개발용 세계 화면·원본 Lua/XML 일부·자동 시험 통과를 전체 게임 완료로 계산하지 않사와요.

전체 진척도는 **약 30%로 추정**하와요. 남은 구현량을 고려한 거친 추정이며 기능이나 통과 검사 수에 고정 가중치를 적용한 실측 완료율은 아니랍니다. 원래 화면으로 한 판을 정상 플레이하는 단계에는 아직 도달하지 않았사와요.

2026-10-07 [이번 정리 결과](../evidence/storage_cleanup/20261007T124510Z_e6f679eb7803/summary.json)는 대체된 Host 1개·실행 묶음 4개·실패한 창 시험 5개의 Build/evidence **20개 폴더, 14,380개 파일·논리 4.58GiB**를 삭제했사와요. 중단된 미완성 목록 2개도 별도 기록 후 정리했답니다. [정리 직전](../evidence/storage/20261007T125051Z.json)과 [직후](../evidence/storage/20261007T125752Z.json)의 NTFS 고유 파일 점유량은 **14.45→11.09GiB, 순감소 3.36GiB**랍니다. 소스·테스트·도구·현재 실행 의존성을 포함한 보호 경로 28,211개의 전후 해시가 같고, 사용자 저장 8개와 New·Continue·저장별 Load 경로 10건을 [삭제 후 다시 확인](../evidence/storage_cleanup/20261007T124510Z_e6f679eb7803/post_cleanup_validation.json)했사와요. 오류는 없었으며 이 검사는 실행 경로와 파일 보존의 증거랍니다.

2026-10-06 현재 Host `20261006T132536Z_f8bcf55e3ffa`는 원본 UnitPanel·도시·연구 연결에 이어 **왼쪽 해제 선택·오른쪽 해제 이동/공격·Shift 이동 예약·현재 위치 명령 취소**를 실제 SDK에 연결했사와요. [새 게임](../evidence/interactive_game/20261006T132933Z_c6976cdbae5b/result.json) 37개와 [별도 프로세스 복원](../evidence/interactive_game/20261006T133311Z_b83e6f290c55/result.json) 39개 committed 프레임에서 원본 방어 행동·도시 조작·금 구매·연구 트리·1→2턴·재저장·정상 종료를 통과했답니다. [독립 대조](../validators/20261006T133655Z_165cb9011b52/conformance.json)는 버튼·세대·픽셀 선택, 왼쪽 선택 전후 상태 일치와 저장 133구획을 확인했사와요. [근접·원거리 전투](../evidence/interactive_game/20261006T134330Z_9d66f439b55e/result.json)도 우클릭과 실제 SDK 피해·경험치·생존 결과를 통과했답니다. 경로 미리보기·그룹 선택·선전포고 확인·특수 모드·나머지 전체 화면은 남아 있으며, 전체 완료율 추정 약 30%를 유지하와요.

[2026-10-06 당시 새 게임 기본 경로](../evidence/runtime_promotion/20261006T134752Z/promotion.json)는 수동 실행본 `20261006T133923Z_6730b22058d0`으로 갱신했사와요. [New·Continue·저장별 Load 검사](../evidence/runtime_promotion/20261006T134752Z/launcher_validation.json) 10건과 사용자 저장 8개의 해시를 확인했답니다. 저장이 있는 이전 세 버전은 해당 저장을 계속 불러오는 데 사용하며, 사람의 정상 한 판 플레이는 아직 검증하지 않았사와요.

[앞선 정리 기록](../evidence/storage_cleanup/20261006T124237Z_28e44307f9a5/cleanup.json)은 대체된 Host 3개와 실패 자동 실행 4개의 Build/evidence 14개 폴더에서 **13,658개 파일·논리 4.34GiB**를 삭제했사와요. 최신 실행·복원 전체와 소스·테스트·도구·사용자 저장 8개를 포함한 보호 파일 31,224개의 전후 해시가 같았고 오류는 없었답니다. [정리 전](../evidence/storage/20261006T123507Z.json)과 [정리 후](../evidence/storage/20261006T125103Z.json)의 NTFS 파일 점유량은 **13.19→9.92GiB**, 순감소 **3.27GiB**랍니다. 하드링크·압축을 반영한 파일 점유량과 삭제한 경로의 논리 크기를 구분하와요. 원본이 삭제된 과거 시험은 [압축 삭제 목록](../evidence/storage_cleanup/20261006T124237Z_28e44307f9a5/retired-files.jsonl.gz)과 [당시 상태 요약](../evidence/storage_cleanup/20261006T124237Z_28e44307f9a5/retired-statuses.json)으로만 추적하와요.

앞선 기본 Host `20261005T124208Z_65c9f8ce7280`는 **원본 Warrior IdleA의 뼈 애니메이션을 실제 x64 게임의 표시 시간 루프에 연결**했사와요. 원본 지형·전사·도시 UI 일부를 같은 D3D11 장치에서 합성하고, world/UI 각각 시간에 따른 전사 픽셀 변화와 입력 세대·관측 SDK 상태 보존을 확인했답니다. 새 게임 30개·별도 프로세스 복원 34개 committed 프레임, 도시 조작·금 구매·연구 트리·1→2턴·재저장과 133구획 저장 대조도 통과했사와요. [현재 통합 증거](CONTINUOUS_PLAY.md)와 [표시/애니메이션 경계](WORLD_TERRAIN.md)에 근거를 연결했답니다. 인구·금·작업장 등을 준비한 자동 시험으로, 사람의 정상 성장·한 판 전체·원본 전체 UI/renderer의 완료는 아니랍니다.

[이전 실행 연결](../evidence/runtime_promotion/20261005T130614Z/promotion.json)에서 새 게임은 `20261005T125723Z_ac109f515719`를 사용했사와요. 현재 기본값은 문서 상단의 10월 8일 수동 실행본이랍니다. 실제 저장을 가진 이전 세 버전은 유지하며, [정리 후 검사](../evidence/storage_cleanup_components/20261005T131139Z_cec8c068b454/post_cleanup_validation.json)에서 사용자 저장 8개의 해시와 실행 경로·bundle 6개를 확인했답니다. 설치본·MODS·사용자 저장 형식·규칙·밸런스는 변경하지 않았사와요.

10월 5일의 [7.56GiB 측정](../evidence/storage/20261005T131917Z.json)과 10월 6일의 9.92GiB는 이전 시점의 값이랍니다. 10월 7일의 11.09GiB 역시 이전 정리 직후의 기록이며, 이후 작업과 최신 정리는 위 10월 8일 항목으로 추적하와요. 삭제한 과거 raw 자료와 Stage 검토 사본은 [압축 경로·SHA 목록](../evidence/storage_cleanup/20261007T124510Z_e6f679eb7803/retired-files.jsonl.gz)과 [당시 상태](../evidence/storage_cleanup/20261007T124510Z_e6f679eb7803/retired-statuses.json)로 추적하며 현재 재실행 근거로 쓰지 않사와요.

기존 미완료 항목은 전체 도시·전투·외교 기능과 UI, 신앙 구매, 글꼴·배치, 다른 유닛·이동/전투 애니메이션·원본 전체 지형/효과/카메라·전체 음향, 선택 모드·외부 저장·성능·장기 안정성과 한 판의 통합이랍니다. 이번 IdleA 연결과 정리로 이 전체 완료 경계를 축소하거나 추정 완료율을 올리지 않았사와요.

## 작업량이 커 보이는 이유

보유 SDK에는 GameCore 규칙 소스가 있지만 게임 EXE·전체 렌더러 프로젝트는 없으며, 이 실행부 경계를 별도로 구현해야 하와요. `--play`·`--play-load` 연속 경로의 실제 이동·저장 재개에 이어, 같은 세계 창의 원본 생산·연구 선택과 다음 턴·저장을 연결했답니다. 도시·생산·연구가 있는 1턴 저장을 새 프로세스에서 복원한 뒤 같은 원본 창과 SDK 콜백을 사용해 2턴·재저장·정상 닫기까지 자동 입력으로 확인했사와요. [현재 세계 표시](WORLD_TERRAIN.md)는 첫 3D 지형 후보이며, 원본 전체 renderer·필수 게임 UI·전체 음향·한 판 전체와 사람 조작의 완료 증거는 아직 없사와요.

공통 기반을 연결한 뒤 원본 UI를 실행하면서 추가 결함이 드러나고 있사와요. 연구 트리의 반복 순회·직렬화와 font·atlas·압축 texture 준비를 보완했고, 같은 세계 창의 원본 연구 트리 선택·닫기·턴·저장을 통과했사와요. 최근에는 유닛 행동·시설 표시와 원본 턴 처리에 따른 농장 완공·6턴 저장 → 새 프로세스 복원 → 7턴 재저장을 확인했답니다. 건설 시험의 일꾼은 시험 준비로 생성한 하나이며, 일꾼 생산이나 전체 플레이 완료로 계산하지 않사와요. [현재 실행과 파일 대조](CONTINUOUS_PLAY.md)에 그 범위를 기록하와요.

초기 범위 산정에서 전체 실행부의 구현량을 충분히 드러내지 못했고, 부품 검증 결과와 실제 플레이의 진척을 분리해 전달하지 못한 점이 작업 보고의 문제랍니다. 저장 재개가 통과한 뒤에도 이전 미완료 문구가 남았던 목록을 현재 증거에 맞춰 고쳤사와요. 새로 발견한 결함은 아래 기존 요구사항에 연결해 관리하며, 추가 개선 후보를 필수 완료 조건처럼 늘리지 않사와요.

후속 구현과 검증은 기존 F01–F07/N01–N04 가운데 어떤 미완료 항목을 해결하는지 먼저 명시하와요. 이미 통과한 범위는 영향 있는 변경·새 실패·남은 의문이 있을 때만 다시 검사하며, 같은 성공 경로의 변형이나 팝업 시험 개수를 전체 진척으로 계산하지 않사와요. 보고할 때에는 이번에 끝낸 항목, 기존 미완료 항목, 새로 발견한 결함을 각각 구분하와요.

## 기존 요구사항 대조

| 기존 ID | 확보한 증거의 범위 | 전체 완료를 막는 항목 |
|---|---|---|
| F01 x64 실행 | x64 Host·GameCore·제공자, 연속 세계 창의 이동·방어 태세·원본 생산/금 구매/연구 트리·연구 완료 팝업·일꾼 하나의 농장 완공; 원본 선전포고 No/Escape/Yes·이동 공격·AI 응답의 43개 프레임과 저장 복원 41개 프레임; 보관 수동 실행 진입점 | 필수 전체 게임 화면·명령·표시·입력, 한 판의 통합 |
| F02 주소 공간 | SDK 할당기·높은 가상 주소의 부품 검증 기록 | 실제 게임 자료의 주소·수명과 큰 상태에서의 통합 검증 |
| F03 멀티코어 | CitySite·FoundValue의 실제 SDK 계산·물리 코어 추적 기록 | 확인한 커널 범위를 유지하며 F04·N02를 별도 검증 |
| F04 결정성 | 고정 fixture의 worker별 점수·50턴 상태·명령·난수·native archive 대조 | 넓은 시나리오·사용자 명령·실패·취소의 통합 회귀 |
| F05 기존 규칙 | 원본 SDK receiver·규칙 정보의 제한된 정상 경로; 인간 선전포고 후 원본 전쟁·외교·공격 명령과 AI 응답, 취소 시 상태 보존 | 기준 게임과 전투·외교·AI·효과의 폭넓은 동등성 |
| F06 모드 | API·SQL/XML·Lua 수명 경계 구현·부품 기록 | 선택 모드의 로드·플레이·저장·UI 검증 |
| F07 저장 | 기존 1→2턴·50턴·농장 완공 6→7턴과 133구획 대조; 선전포고 후 1턴 저장 → 별도 프로세스에서 초기 상태 SHA 일치 → 2턴 재저장; 저장 Bundle과 맞는 보관 실행 버전 선택 | 폭넓은 플레이 저장 재개, 기존 외부 저장 컨테이너와 활성 모드·열린 UI의 호환성 |
| N01 장애 격리 | 작업 세대·소유권·취소·실패·오래된 결과·예외의 부분 검증; 타일 구매 모드의 중첩 구매 창 WM_CLOSE 뒤 도시 선택 해제와 최종 저장 | 전체 게임의 실패 복구·부분 반영·종료·재시작 |
| N02 성능 | 커널 병렬 동작·입력량 기록 | 전체 턴 반복 측정·복사·대기 비용을 포함한 유용한 개선 |
| N03 추적성 | 후보별 동결 입력·빌드·실행·해시·보관 기록 | 재현 가능한 최종 통합 Build·Stage·릴리스 |
| N04 UI 보존 | 첫 3D 지형·원본 전사 IdleA의 시간 갱신·깊이/픽셀 선택과 동일 좌표의 도시 버튼/타일 경계; 같은 세계 창의 원본 생산/연구 트리·턴·저장 재개, EN/KO 선택·스크롤 pair, 도시·시설·도로 이름과 유닛 행동 표시; CityView 시민 설정·전문가·작업 타일·타일 구매·유닛/건물 금 구매·원본 효과음의 장치 재생 완료·중첩 생산·복귀와 구매 창 종료; 원본 체크 아틀라스·위인 막대; 점령 도시 보기·괴뢰 선택·외교 나가기; 한국어 TechAwardPopup 표시·계속 버튼·timer 해제 | 다른 유닛·이동/전투 애니메이션·원본 전체 3D 모델·물/강·지형 조합/효과·카메라, 필수 전체 UI·신앙 구매·나머지 도시 조작·연속 사람 입력·전체 음향·기존 게임 비교, CityView 체크 프레임·글꼴·위젯·world offset, 연구 진행계/ScrollAnim·탭 간격·자동 크기의 원본 표시 의미 |

이 표는 새로운 목표나 완료율을 제안하지 않사와요. 부품의 통과 여부와 전체 게임의 완료 여부를 같은 숫자로 합치지 않으며, 기존 문서의 오래된 단계별 문구는 해당 당시 증거로만 해석하와요.

## 실행 우선순위

수동 연구 화면 전환에서 확인된 입력 적체 종료 오류는 Host `20261003T235743Z_f2f8e581fe1f`에 수정했사와요. O2/Od 창 처리 검사와 실제 SDK의 새 게임·저장 재개 자동 입력을 통과하고 최신 수동 실행에 연결했답니다. 화면 교체·팝업 준비 중 닫기 뒤 최종 저장도 확인했으며, 상세 범위와 실패 기록은 [연속 실행 기록](CONTINUOUS_PLAY.md)에 보존하와요. 이는 기존 N01/N04의 결함 수정이며 전체 게임 완료율을 올리는 독립 목표로 세지 않사와요.

1. 남은 전체 도시·전투·외교·연구 기능과 원본 세계 표시·입력·음향을 연결하는 F01·N04 통합을 이어 가와요. 현재의 유닛 행동·금 구매·연구 완료 팝업·일꾼 건설·저장 재개는 그 안의 제한된 통과 경로랍니다. 활성 0×0 연구 진행계·후보 ScrollAnim 정책은 기존 N04의 미검증 표시 경계로 유지하며, 팝업 검사 수를 전체 플레이 진척으로 환산하지 않사와요.
2. 연구 트리의 남은 기능은 [실행 기록](M6_TECH_TREE_UI.md)과 [같은 세계 창의 최신 기록](CONTINUOUS_PLAY.md)에 연결해 해결하와요. 직렬화 및 자산 준비의 수정 완료를 전체 연구·원본 표시 동등성·N02 전체 턴 성능 향상으로 확대하지 않사와요.
3. 통합 경로에서 규칙·모드·외부 저장·성능·장기 안정성과 최종 릴리스를 검증하와요. 필요 없는 반복 빌드 중간물은 보관 규칙에 따라 정리하와요.

완료 일정은 필수 구현량·측정된 작업 속도·통합 결함을 근거로 다시 산정해야 하며, 위 추정 완료율만으로 남은 시간을 환산하지 않사와요.
