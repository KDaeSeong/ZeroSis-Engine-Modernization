# 연속 게임 실행 경로

<!-- current-early-access-0.2-20261009 -->
**현재 사용자용 실행 경로는 ZeroSis' 얼리 액세스 0.2**랍니다. [이용 안내](EARLY_ACCESS_KR.md)와 `Play/EarlyAccess`의 [새 게임](../Play/EarlyAccess/새%20게임.cmd)·[이어하기](../Play/EarlyAccess/이어하기.cmd)·[불러오기](../Play/EarlyAccess/불러오기.cmd)를 이용하시와요. 수동 실행본 `20261009T132430Z_a0a5dd8fd007`에는 원본 턴 안내 버튼을 포함했답니다. [새 실행](../evidence/interactive_game/20261009T130410Z_7c35d16e64b9/action_info_panel_validation_followup_coverage.json)과 [저장 복원](../evidence/interactive_game/20261009T131452Z_16632c1f4d4a/action_info_panel_validation_followup_coverage.json)의 입력·상태·저장을 대조했고, [실행 경로 20개](../evidence/runtime_promotion/20261009_early_access_02/runtime_and_launcher_validation.json)와 기존 저장 8개도 유지했사와요. 자동 입력이 없는 [일반 새 게임 창의 생성·응답](../evidence/runtime_promotion/20261009_early_access_02/manual_startup_observation.json)을 확인했으며, 사람이 한 판을 완주한 증거는 아니랍니다.

<!-- historical-early-access-0.1-20261009 -->
이전 EA 0.1의 작은 실행 설정·배포 기록·안내서는 [이력 폴더](../Play/EarlyAccess/history/0.1)에 남겼사와요. EA 0.1에서 직접 저장한 게임도 이어하기에서 찾고 해당 엔진으로 열도록 유지했답니다. **아래는 당시 실행 기본값·진척도·용량을 보존한 이전 기록**이며, 현재 사용 안내는 위 EA 문서를 기준으로 하와요.

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

2026-10-09 개발 소스의 `civ5_ui_assets.py`에서 원본 UI 팩 네 개의 SHA 계산을 병렬화했사와요. 장면 시작과 끝의 전체 원본 검사를 모두 유지하며 디스크/프로세스 캐시를 추가하지 않았답니다. [비교 결과](../evidence/ui_preparation_benchmark/20261009T015540Z_09a6ff4c0592/result.json)는 동일한 실제 SDK 스냅샷 세 종류를 순차/병렬 방식으로 교대 준비한 기록이와요. 각 방식 3회, profiler를 끈 준비 함수의 중앙값이랍니다.

| 장면 | 순차 검사 | 병렬 검사 | 중앙값 감소 |
|---|---:|---:|---:|
| 도시 화면 | 2.912초 | 2.608초 | 10.4% |
| 상단 정보창 | 2.710초 | 1.378초 | 49.2% |
| 교역로 | 3.239초 | 2.391초 | 26.2% |

18회 출력의 `scene.packet`·텍스처·원본 자산/UI 사본은 각 경로의 크기·SHA가 같고, 기존 기준 packet SHA 및 입력 65개의 전후 SHA도 일치하와요. 기존 자산 검사 92개와 별도 병렬/변조 검사 7개가 통과했답니다. 비교 도구의 마지막 집계 필드 누락은 원본 실패 journal을 보존하고 그 측정값으로만 재집계했으며, 결과의 `recovery_provenance`에서 추적할 수 있사와요. 준비 함수 외 프로세스 시작·입력 전달·전체 게임 속도는 이 측정에 포함되지 않으며, 현재 수동 실행본과 동결된 새 게임/복원 쌍의 코드는 그대로랍니다. 이번 변경은 다음 개발 실행을 위한 소스 검증이며 새 Host/실게임 실행이나 수동 승격 완료로 보고하지 않사와요. 각 비교 쌍의 임시 출력은 바로 삭제했고 [정리 후 점유량](../evidence/storage/20261009T015904Z.json)은 8.80GiB랍니다.

2026-10-09 [최신 정리 결과](../evidence/storage_cleanup/20261009_trade_route_pair_cleanup/summary.json)의 NTFS 고유 파일 점유량은 **25.63→8.80GiB**, 누적 **16.83GiB·65.66% 감소**랍니다. 직전 9.06GiB 측정 이후 만든 별도 프로세스 복원 검증 자료까지 포함했사와요. 구형 Host와 교역로 실행 두 묶음의 Build/evidence 여섯 폴더·11,555개 파일을 삭제하고, 새 복원 DB/DDS 416개는 내용 변경 없이 압축했답니다. 삭제 전후 보호 파일 80,355개의 SHA가 같으며 사용자 저장 8개·실행 경로 10건도 재확인했사와요. 경로별 파일 크기 합계는 21.33GiB이고, 여기 보고한 점유량은 하드링크 중복과 NTFS 압축을 반영한 파일 데이터 크기랍니다.

2026-10-09 [추가 용량 정리](../evidence/storage/20261008T164816Z_2268d33ad2b9_cold/final_summary.json) 직후 NTFS 고유 파일 점유량은 **13.10→8.34GiB**랍니다. 앞선 대량 정리 전 **25.63GiB 대비 총 17.29GiB·67.46% 감소**했사와요. 이번에는 cold Build/evidence 7,507개를 검토하여 7,500개를 내용 변경 없이 압축하고 절감 없는 7개는 원복했답니다. 보호 파일 4,606개 해시와 사용자 저장 8개·실행 연결 10건을 재확인했사와요. 현재 실행본·사용자 저장 의존 버전·재사용 빌드 캐시는 제외했으며, 아래 용량은 각 당시 기록이랍니다.

교역로 [Host 224629](../evidence/ui_window_host/20261008T224629Z_ee41544939ef/build_result.json)의 [새 게임 225105](../evidence/interactive_game/20261008T225105Z_a09bb643b908/trade_route_validation.json)와 [별도 프로세스 복원 233650](../evidence/interactive_game/20261008T233650Z_5cfa5136b39e/trade_route_validation.json)이 모두 **독립 검사 PASS**랍니다. 원본 1턴 저장과 복사본·복원 초기 SDK 상태가 일치하고, 세 탭·금 수익 정렬·닫기/재열기/Escape의 실제 입력 9건 뒤 2턴 진행·저장 2회·정상 종료를 확인했사와요. 저장 133개 구역 중 132개는 같고 Game 구역만 달랐으며, 그 내부 변화의 reload metadata·난수 동등성은 별도 미검증으로 남겼답니다. 휠은 내용이 넘치지 않는 상태에서의 입력 소비만 검증했으며 사람의 플레이·원본 전체 화면의 증거는 아니랍니다. 수동 기본 실행본과 전체 추정 약 30%는 유지하와요. 아래 실패 기록은 수정 전 이력이랍니다.

2026-10-09 [최신 정리 결과](../evidence/storage_cleanup/20261008T141026Z_retirement_plan/final_summary.json): NTFS 고유 파일 점유량 **25.63→12.57GiB**, 13.06GiB·50.97% 감소랍니다. 대체된 Build/evidence 50개 폴더·43,436개 파일을 삭제하고 완료된 시험 DB/DDS 1,568개를 무손실 압축했사와요. 삭제 전후 보호 파일 40,825개, 압축 전후 각 대상 파일의 SHA가 같았답니다. [PlanOnly 검사](../evidence/storage_cleanup/20261008T141026Z_retirement_plan/post_cleanup_validation.json)에서 사용자 저장 8개와 New·Continue·저장별 Load 경로 10건을 보존했으며, 게임을 실제 실행한 검사는 아니랍니다. 현재 기본 실행본 `20261007T202612Z_d895c0fe84ab`와 저장이 있는 세 버전, 최신 통과 근거와 현재 실패 진단은 유지하와요. 아래 삭제된 구형 실행의 raw 링크는 당시 이력이며, 이번 폐기 목록·SHA·상태는 위 정리 결과의 참조 자료로 추적하와요.

구형 교역로 Host `135705`와 실행 `140841`·`161612`의 원본 Build/evidence는 최신 새 게임·복원 쌍으로 대체하여 삭제했사와요. `140841`은 문명 아이콘 처리에서 실패했고, `161612`의 자체 PASS 표시는 실제 탭 입력을 재검사했을 때 인정되지 않았답니다. 경로·크기·SHA는 [압축 삭제 목록](../evidence/storage_cleanup/20261009_trade_route_pair_cleanup/recovery_01/retired-files.jsonl.gz)에, 당시 결과는 [상태 기록](../evidence/storage_cleanup/20261009_trade_route_pair_cleanup/recovery_01/retired-statuses.json.gz)에 남겼사와요. 현재 통과 근거는 위 `225105`·`233650` 쌍이며, 삭제된 구형 원본 링크를 현재 증거로 사용하지 않사와요.

2026-10-08 상단창 통합 검증 뒤 [정리 결과](../evidence/storage_cleanup/20261007T203350Z_manual_retirement_draft/summary.json)로 대체된 수동 실행본·Host·실패 시험의 Build/evidence **16개 폴더, 6,221개 파일·논리 2.36GiB**를 제거했사와요. [정리 전](../evidence/storage/20261007T210827Z.json)과 [정리 후](../evidence/storage/20261007T212931Z.json)의 NTFS 고유 파일 점유량은 **19.24→17.44GiB, 1.81GiB 감소**했답니다. 삭제 전후 보호 경로 54,726개의 해시가 같았으며, [삭제 후 경로 검사](../evidence/storage_cleanup/20261007T203350Z_manual_retirement_draft/post_cleanup_validation.json)에서 사용자 저장 8개와 New·Continue·저장별 Load 10건을 확인했사와요. 실패 자동시험의 저장 3개도 경로·크기·SHA가 고정된 폐기 목록에 포함했으며 사용자 저장과 겹치지 않사와요. 최신 상단창 새 게임·복원, 현재 수동 실행본과 필요한 선전포고·CPU 검증 자료는 보존했답니다. 아래의 14.80GiB 등 이전 수치는 해당 당시 기록이랍니다.

2026-10-08 원본 BNW 상단 정보창을 `--top-panel` 시험 옵션으로 연결한 구형 Host `20261007T205518Z_12228ee7e01b`의 SHA-256은 `22ed4c0987fa3f320f9ebba963e3a80e9befd208faceea12ee1a7b0b268fa14c`였답니다. 이 Host와 새 게임 `20261007T210013Z_55d5320ad39d`·복원 `20261007T210357Z_334991eea806` raw 자료는 현재 교역로 통과 쌍으로 대체하여 삭제했사와요. 아래 관련 구형 링크는 당시 이력이며 [압축 진단](../evidence/storage_cleanup/20261009_top_panel_retention_review/retired-diagnostics.json.gz)과 [파일별 경로·SHA 목록](../evidence/storage_cleanup/20261009_top_panel_retention_review/retired-files.jsonl.gz)으로 추적하와요. 최신 보유 통과 근거는 위 교역로 쌍이랍니다.

| 상단창 개발 후보 증거 | 확인한 범위 |
|---|---|
| [새 게임 자동 시험](../evidence/interactive_game/20261007T210013Z_55d5320ad39d/result.json) | 37개 committed 프레임; 도시 건설 전 숨김 → 건설 후 정보 표시; 과학 클릭 → 기술 트리 → Escape 복귀의 SDK 상태 동일; 도시·생산·금 구매·연구·0→1턴·저장 2회·정상 종료 |
| [별도 프로세스 복원](../evidence/interactive_game/20261007T210357Z_334991eea806/result.json) | 동일 Host에서 위 저장의 상태 일치; 기존 도시의 과학 클릭 왕복; 도시 조작·1→2턴·재저장 2회·정상 종료; 39개 프레임 |
| [원본 Lua 부품](../evidence/top_panel_scene_component/result.json) · [렌더링 회귀](../evidence/top_panel_scene_component/native_render_validation.json) | 원본 callback과 비모달·timer 0 계약, 실제 SDK의 도시 건설 전 숨김 상태, 음수 금 표시의 한정된 색상 문법 및 다른 잘못된 문법 거부; 공통 표시기 188개 검사 통과 |

[새 게임 독립 검사](../evidence/interactive_game/20261007T210013Z_55d5320ad39d/top_panel_validation.json)와 [복원 독립 검사](../evidence/interactive_game/20261007T210357Z_334991eea806/top_panel_validation.json)는 실제 과학 callback·native Escape·동일 SDK 상태·활성 플레이어·턴 갱신·입력 세대·단일 HWND/장치를 확인하와요. 두 검사에 처음 적힌 GPU 캡처 시점 설명은 잘못되어, [새 게임 정정](../evidence/interactive_game/20261007T210013Z_55d5320ad39d/top_panel_revalidation.json)과 [복원 정정](../evidence/interactive_game/20261007T210357Z_334991eea806/top_panel_revalidation.json)을 함께 읽어야 한답니다. `-gpu.png`는 상단창 GPU 합성과 장면 commit 뒤의 실제 backbuffer 캡처랍니다. 같은 세대의 별도 합성 참조와 source 908개·restore 938개 픽셀이 다르고 최대 RGB 차이는 각각 1·2/255이며, alpha와 상단 띠 밖은 같았사와요. 따라서 실제 표시 증거는 존재하지만 픽셀 완전 일치나 원본 게임 화면 동등성으로 판정하지 않사와요. 원래 `result.json`과 최초 검사 보고서는 보존했답니다.

변경 범위는 [UiPopupContext](../Source/Host/UiPopupContext.h), [InteractiveUiSession](../Source/Host/InteractiveUiSession.h), [InteractiveGameSession](../Source/Host/InteractiveGameSession.h), [입력·표시 루프](../Source/Host/InteractiveGameLoop.h), [UiScene](../Source/Host/UiScene.lua), [UI 컴파일러](../tools/ui_pixel_scene.py)와 [실행 준비](../tools/run_interactive_game.py)랍니다. 첫 HWND 생성 전 메시지 큐를 읽지 않도록 고쳤고, 과학 popup 요청은 Lua callback이 끝난 뒤 처리하며 상태·RNG 보존을 검사하와요. 음수 금 표시의 원본 색상 닫기 패턴은 정확한 GoldPerTurn 위젯에만 허용하고 원본 문자열 자체는 보존하와요. 원본 설치 자료·MODS·저장 스키마·게임 규칙은 변경하지 않았답니다.

**아래 2026-10-08 구형 상단창 후보는 당시 과학 버튼만 연결했사와요.** 금·교역·문화·관광·신앙·도감·메뉴의 7개 클릭은 아직 backend 미지원으로 오류를 일으키므로 수동 기본값에 넣지 않았사와요. 툴팁의 hover 연결·그리기·자동 크기·배치, 기본 도움말 설정, 숫자 따옴표 표시, 다른 모달 화면 위 상단창 유지도 남아 있답니다. 자동 시험은 HWND에 입력을 게시한 제한된 시나리오이며 사람의 한 판, 원본 전체 UI, 외부 저장과 모든 모드의 호환성을 증명하지 않사와요.

2026-10-08 수동 새 게임 기본값은 `20261007T202612Z_d895c0fe84ab`로 갱신했사와요. [승격 기록](../evidence/runtime_promotion/20261007T203124Z/promotion.json)과 [경로 검사](../evidence/runtime_promotion/20261007T203124Z/launcher_validation.json)에서 New·Continue·저장별 Load 총 10건, 사용자 저장 8개의 해시 보존을 확인했답니다. 선전포고 검증을 통과한 Host와 원본 Warrior/IdleA·애니메이션 의존성·동결 UI 지원물을 함께 연결했으며, 기존 저장 세 버전은 해당 저장용으로 유지하와요. 원본 유닛 자료를 빠뜨린 직전 준비본의 승격은 [별도 철회 기록](../evidence/runtime_promotion/20261007T202716Z/replacement_candidate_status.json)으로 남겼답니다. 이 연결 검사는 사람의 한 판 플레이 증거가 아니랍니다.

2026-10-08 개발 후보 [Host `20261007T192802Z_20ff3a2b797c`](../evidence/ui_window_host/20261007T192802Z_20ff3a2b797c/build_result.json)는 원본 선전포고 확인창·현재 거래 조회·실제 SDK 전쟁과 공격 명령을 연결했사와요. 최신 증거는 아래와 같으며, 전체 추정 약 30%를 유지하며 수동 기본값은 문서 상단의 승격 기록을 따르와요.

| 개발 후보 증거 | 통과 범위와 한계 |
|---|---|
| [이동 선전포고](../evidence/interactive_game/20261007T192923Z_503f1dbbd104/result.json) | 원본 No·Escape에서 상태 보존, Yes에서 실제 전쟁·외교·이동 공격·AI 응답·도시/생산/연구·턴 진행·저장 2회·정상 종료; 43개 프레임 |
| [저장 복원](../evidence/interactive_game/20261007T193254Z_1453ea25dd27/result.json) | 위 실행의 저장을 별도 프로세스에서 복원하여 초기 상태 일치·도시/생산/연구·턴 진행·재저장 2회·정상 종료; 41개 프레임 |
| [원거리 선전포고 별도 재검증](../evidence/interactive_game/20261007T191737Z_cb79c4f6eb96/declare_war_revalidation.json) | 이전 Host `190026Z_e8927b74abf4`의 실제 공격·저장·정상 종료 기록을 수정된 입력 enum 검사기로 확인; 원본 FAILED 결과는 보존, 재실행으로 표기하지 않음 |
| [원본 Lua 부품](../evidence/declare_war_scene_component/result.json) · [AI 응답 렌더링](../evidence/declare_war_scene_component/leader_response_renderer_validation.json) | 거래 없는 최초 팝업·정상 거래/아이콘·잘못된 실제 아이콘 거부와 SDK 전쟁 응답 표시; 원본 전체 배치·3D 지도자 동등성은 미검증 |

개발 후보의 실행 파일 SHA-256은 `7d75dbd22b7bc08ff57df6d2ff96b87e5f37698bbe68ca8aa563ace1ed8a4fca`랍니다. 자동 시험용으로 준비한 지도·유닛·도시 상태이며, 정상 한 판과 기존 외부 저장 호환성은 아직 검증하지 않았사와요.

이번 결함 수정은 [UiScene.lua](../Source/Host/UiScene.lua)의 숨겨진 원본 placeholder 측정 시점, [UI 표시 정책](../tools/ui_pixel_scene.py)과 [입력 드라이버](../tools/interactive_ui_driver.py)·[렌더러](../tools/render_ui_popup.py)의 실제 SDK 전쟁 응답 허용, [시험 준비](../Source/Host/InteractiveGameSession.h)의 네이티브 `GetDeclareWarMove` 호출에 적용했사와요. [검사기](../tools/run_interactive_game.py)는 Host 입력 enum을 올바르게 대조하고 성공한 선전포고 실행의 저장 복원을 허용하와요. [원본 Lua 부품](../Tests/declare_war_scene.lua), [아이콘 목록](../Tests/inline_icon_catalog.py), [선전포고 검사기 회귀](../Tests/interactive_declare_war_contract.py)와 위 실제 SDK 실행을 확인했답니다. 원본 XML의 임시 아이콘 오타를 새 아이콘으로 등록하지 않았으며 실제로 표시하는 알 수 없는 아이콘은 계속 거부하와요.

2026-10-08 최신 시험 뒤 [추가 정리](../evidence/storage_cleanup/20261007T193212Z_c1a07d6e4b39/summary.json)는 대체된 Host와 실패 실행의 Build/evidence 6개 폴더·8,463개 파일·논리 2.63GiB를 제거했사와요. 고유 파일 점유량은 **16.79→14.80GiB, 1.99GiB 감소**했고, 보호 경로 43,558개·사용자 저장 8개·실행 경로 10건을 확인했답니다. AI 응답 렌더링 진단에 쓴 이전 실패 snapshot은 [경로·SHA 기록](../evidence/storage_cleanup/20261007T193212Z_c1a07d6e4b39/retired-historical-reference.json)과 [실제 삭제 결과](../evidence/storage_cleanup/20261007T193212Z_c1a07d6e4b39/cleanup.json)로 추적하와요. 위 최신 성공 실행·복원과 원거리 재검증의 원본 자료는 유지하와요.

같은 날 [앞선 정리](../evidence/storage_cleanup/20261007T185251Z_9a72c5df1e41/summary.json)의 8개 폴더·8,032개 파일·논리 2.55GiB 삭제와 14.39→12.44GiB 측정은 뒤이은 시험 자료를 만들기 전의 기록이랍니다.

2026-10-06 수동 실행 기준 Host `20261006T132536Z_f8bcf55e3ffa`는 **왼쪽 버튼 해제로 선택, 오른쪽 버튼 해제로 이동·공격**하는 세계 입력을 실제 x64 GameCore에 연결했사와요. 원본 UnitPanel·도시·생산·연구 화면의 기존 연결도 유지하와요. 전체 추정 진척은 약 30%이며, 원본 전체 UI·3D와 사람이 한 판을 정상 플레이하는 목표는 미완료랍니다.

| 2026-10-06 당시 기준 | 확인한 범위 |
|---|---|
| [Host 빌드](../evidence/ui_window_host/20261006T132536Z_f8bcf55e3ffa/build_result.json) | PE32+ x64, SHA `c5f135769f4b1e57f880c6c1889f12d242363b5d9ce1577a675eb418096e7f18` |
| [새 게임](../evidence/interactive_game/20261006T132933Z_c6976cdbae5b/result.json) · [별도 프로세스 복원](../evidence/interactive_game/20261006T133311Z_b83e6f290c55/result.json) | 각각 37·39개 committed 프레임; 원본 방어 행동·도시 조작·금 구매·연구 트리·1→2턴·저장·정상 종료; 초기 복원 상태 일치 |
| [독립 대조](../validators/20261006T133655Z_165cb9011b52/conformance.json) | 실제 HWND 버튼·세대·좌표·GPU 선택 ID, 원본 UI callback, 같은 장치, 저장 133구획과 복원 대조 |
| [근접·원거리 전투](../evidence/interactive_game/20261006T134330Z_9d66f439b55e/result.json) | 실제 우클릭·GPU 타일 ID·피해/경험치·생존/사망과 SDK callback 대조; 39개 프레임 |
| [창 입력 부품](../evidence/bitmap_window/20261006T132646Z_43520a264230/conformance.json) | O2/Od 각각 PASS 165; 좌우 release, modifier, 장면 세대·포커스·capture 취소와 표시 갱신 |
| [명령 전달 부품](../evidence/local_game_commands/conformance.json) | O2/Od 각각 59개, 총 118개 검사; 교환/전쟁/외교 명령 tuple·FIFO·재진입 거부·unbind 수명 |
| [당시 수동 실행 연결](../evidence/runtime_promotion/20261006T134752Z/promotion.json) · [당시 실행 경로 검사](../evidence/runtime_promotion/20261006T134752Z/launcher_validation.json) | 2026-10-06 당시 새 게임 기본 `20261006T133923Z_6730b22058d0`; New·Continue·기존 저장 8개 Load 경로 총 10건 검사, 저장 해시 유지 |
| [2026-10-07 산출물 정리](../evidence/storage_cleanup/20261007T124510Z_e6f679eb7803/summary.json) | 구형 Build/evidence 20개 폴더·14,380개 파일 삭제; 보호 28,211개 경로·저장 8개 불변, 실행 경로 10건 재확인; NTFS 고유 파일 점유량 14.45→11.09GiB |

원본 `InGame.lua`의 기본 왼쪽 선택과 `WorldView.lua`의 오른쪽 해제 명령을 기준으로 연결했사와요. 이동은 `ICvGame1::SelectionListMove`를 통해 원본 SDK가 이동/자리 교환을 결정하며, 같은 타일에서 Shift 없는 우클릭은 `COMMAND_CANCEL_ALL`을 전달하와요. Shift는 원본 receiver의 대기열 인자로 전달하고, 보이는 적에 대한 원거리 명령은 원본 `CanRangeStrikeAt`와 공중/지상 분기를 사용하와요. Alt/Ctrl은 원본 BNW 이동 래퍼에서도 사용하지 않는 인자랍니다.

실제 새 게임과 복원에서 왼쪽 빈 타일 클릭 전후 SDK 상태 파일의 바이트 일치, 오른쪽 이동으로 좌표·이동력 변화, Shift 예약 후 SDK head mission, 현재 위치 우클릭 후 mission 해제를 확인했사와요. 예약을 관찰하기 위한 자동 시험에서만 `FinishMoves`로 이동력을 소진시키며 수동 게임에는 적용하지 않사와요. [실제 로그와 검증기 변조 검사](../evidence/interactive_game/20261006T132933Z_c6976cdbae5b/world_mouse_check.json)는 정상 1건과 잘못된 버튼·명령 누락 등 5건 거부를 확인하와요.

첫 전투 실행 `20261006T133653Z_55bff44be6f4`는 Host가 정상 종료하고 전투 결과도 나왔지만 검증기가 과거의 왼쪽 클릭·사각형 hit만 요구해 FAILED로 기록했사와요. 검증기를 실제 오른쪽 버튼과 저장된 GPU 픽셀 ID를 대조하도록 수정한 뒤 위 별도 실행에서 PASS를 얻었답니다. 이 실패 묶음과 앞선 UnitPanel 실행 쌍 `20261006T120232Z_10eeb7212e57`/`20261006T121618Z_e382f0b538e7`, Host `20261006T120008Z_32a336f5d95d`, 저장이 없는 이전 수동 기본값 `20261005T125723Z_ac109f515719`는 10월 7일에 정리했사와요. 원본 보고서를 PASS로 바꾸지 않았으며, 삭제한 raw 파일의 경로·SHA·당시 상태는 [정리 목록](../evidence/storage_cleanup/20261007T124510Z_e6f679eb7803/plan.json)으로만 추적하와요.

공개 SDK에 없는 `UI.LocationSelect`의 전체 스택 순환·Alt/Ctrl 그룹·Shift 선택, 경로 미리보기, 선전포고의 나머지 진입 방식, 특수 선택 모드와 UnitPanel 우클릭/Civilopedia·tooltip은 아직 남아 있사와요. 자리 교환 receiver 연결은 부품 검사를 통과했지만 실제 지도에서의 교환은 아직 검증하지 않았답니다. 이 범위를 전체 원본 조작 동등성으로 확대하지 않사와요.

선전포고 창은 `Expansion2/UI/InGame/Popups/DeclareWarPopup.lua`와 원본 XML을 유지하와요. 현재 거래·scratch deal·교역로·동맹/보호 정보 조회와 원본 명령 순서를 연결했답니다. Host는 콜백에서 모은 전체 명령을 검증한 뒤 실제 SDK에 전달하며, 후속 명령 예외는 확인한 선택 유닛·턴·대상·모드에만 한정하와요. 지도에서 선택한 유닛의 이동/원거리 공격 확인에서 No/Escape의 상태·난수 보존과 Yes의 명령 순서를 확인했답니다. 지도 좌표 없는 외교 화면 직접 선전포고, 전체 지도자 3D·중첩 외교 창·전체 게임 동등성은 남아 있사와요.

수동 새 게임에는 시험 fixture나 시간제한이 없사와요. 기존 저장을 이어 가면 저장 bundle에 맞는 보관 버전을 선택하며, 이번 경로 검사는 실제 사람의 장시간 조작을 뜻하지 않사와요. 설치본·MODS·저장 형식·밸런스는 변경하지 않았답니다.

## 이전 애니메이션 통합 기준

2026-10-05 당시 기본 Host `20261005T124208Z_65c9f8ce7280`는 **원본 전사의 IdleA 뼈 애니메이션을 같은 게임 창의 D3D11 표시와 시간 루프에 연결**했사와요. 세계 화면과 도시 UI가 열린 화면에서 시간이 흐를 때 전사 영역의 픽셀이 바뀌고, 입력 세대와 관측한 SDK 상태가 유지됨을 확인했답니다. 도시 조작·금 구매·연구 트리·1턴 저장 → 새 프로세스 복원·2턴 재저장도 통과했사와요. 기존 F01/F07/N04의 진전이며, 인구·금·작업장 등을 준비한 자동 시험이랍니다. 원본 전체 UI·모델·이동/전투 애니메이션·효과·한 판 플레이의 완료는 아니며 [표시 경계](WORLD_TERRAIN.md)를 유지하와요.

보관 안내: [13:19 UTC 실측](../evidence/storage/20261005T131917Z.json)의 파일 점유량은 **7.56GiB**랍니다. 이번 시험 뒤 정리 전 9.63GiB에서 **2.07GiB 감소**했고, 최초 75.11GiB보다 **67.55GiB 감소**했사와요. [이번 정리 종합 기록](../evidence/storage_cleanup_components/20261005T131139Z_cec8c068b454/summary.json)은 구형 실행·실패 시험·미참조 오브젝트 8,854개·논리 2.70GiB 삭제와 완료 시험 DB/DDS 467개의 무손실 압축을 기록하와요. [최종 보존 검사](../evidence/storage_cleanup_components/20261005T131139Z_cec8c068b454/post_cleanup_validation.json)는 사용자 저장 8개의 해시·실행 버전 연결과 bundle 6개를 확인했답니다. 아래 과거 이력의 대체된 raw 링크와 Stage 검토 사본은 현재 보유 자료가 아니며, 현재 통합 자료는 이 표랍니다. 파일 점유량은 중복 하드링크와 NTFS 압축을 반영한 값이며 볼륨 전체 여유 공간과 구분하와요.

| 최신 자료 | 확인한 범위 |
|---|---|
| [Host 빌드](../evidence/ui_window_host/20261005T124208Z_65c9f8ce7280/build_result.json) | PE32+ x64, EXE SHA `1ec633a49611dcf5cc3f880eecfb9a4f566b695238a8b398da540cf00d4a9c82`; 원본 IdleA·CPU skinning·표시 전용 시간 루프 |
| [SDK 새 게임](../evidence/interactive_game/20261005T124511Z_ad7083cc8304/result.json) · [새 프로세스 복원](../evidence/interactive_game/20261005T125355Z_d882b8fab075/result.json) | PID 1828과 20556, 각각 30·34개 committed 게임 프레임; 도시 조작·금 구매·연구 트리, 1→2턴·재저장·정상 종료 |
| [새 게임 독립 대조](../validators/20261005T125352Z_1af8a4f8a77f/conformance.json) · [복원 독립 대조](../validators/20261005T125715Z_e4b893bfa12a/conformance.json) | GPU world/Scene의 세대·장치, 원본 callback·게시 좌표, native 저장 133구획과 복원 상태 |
| [새 게임 애니메이션 대조](../validators/20261005T125315Z_a906278c8d90/animation.json) · [복원 애니메이션 대조](../validators/20261005T125729Z_cf1ba850d111/animation.json) | 실행마다 world/UI 각 3개 실제 시계 표본; 동일 입력 세대·턴·관측 SDK 상태, 전사 영역 픽셀 변화 |
| [창 부품 검사](../evidence/bitmap_window/20261005T123839Z_6694ccd3719b/conformance.json) | O2/Od 각각 164개 검사·8개 COM 창 수명 균형; 애니메이션 갱신 중 대기 키/클릭/스크롤 보존, 입력 기하 변경 거부와 실패 원자성 |
| [원본 뼈 애니메이션 부품 검사](../evidence/unit_animation/20261005T124200Z/report.json) | 세 rig의 원본 뼈·가중치, t=0 정점 대조, 중간 시점·반복 재생·잘못된 시간·스레드·부모 순환 거부 |
| [세계 화면 부품 대조](../Build/terrain_renderer_validation/20261005T125302Z/manifest.json) | 실제 변화하는 전사 픽셀·반복 시점, 지형 ID·projection 보존; 전체 HUD의 D2D 가장자리만 명시한 한계로 비교 |
| [세계 애니메이션 캡처](../Build/InteractiveGameRuntime/20261005T124511Z_ad7083cc8304/sessions/04e9a9c6ff5da92ebaa3afe81876ba73/animation-world-3.png) · [도시 UI 캡처](../Build/InteractiveGameRuntime/20261005T124511Z_ad7083cc8304/sessions/04e9a9c6ff5da92ebaa3afe81876ba73/animation-ui-3.png) | 개발용 세계 화면과 원본 도시 UI 일부; 원본 전체 표시 동등성의 증거는 아님 |
| [당시 수동 실행 상태](../evidence/storage_cleanup/20261007T124510Z_e6f679eb7803/retired-statuses.json) · [이전 기본 실행 연결](../evidence/runtime_promotion/20261005T130614Z/promotion.json) | 당시 검증한 Host·원본 애니메이션 자산을 새 게임에 연결; 저장 없는 해당 실행 묶음은 10월 7일 정리 |
| [정리 종합 기록](../evidence/storage_cleanup_components/20261005T131139Z_cec8c068b454/summary.json) · [남긴 자료 압축](../evidence/storage/20261005T131822Z_68fe163f466d/compression.json) | 기록된 삭제 8,854개·논리 2.70GiB; DB 6개·DDS 461개 내용/SHA 보존, 압축으로 파일 점유량 1,159,313,024바이트 감소 |

당시 [Start-Engine.ps1](../tools/Start-Engine.ps1)의 기본 새 게임은 `20261005T125723Z_ac109f515719`였사와요. 현재 기본값은 문서 상단의 `20261007T202612Z_d895c0fe84ab`이며 이전 저장을 가진 세 버전과 저장별 버전 선택을 유지하와요. 당시 실행 경로 검사는 자동 입력·총 실행 제한이 없음을 확인했으며 사람 플레이를 확인한 것은 아니랍니다.

수동 실행에서는 세계 그림·도시 backdrop·팝업의 PNG 생성·재디코딩을 생략하고 창과 같은 장치에서 합성하와요. 애니메이션 갱신은 보존한 표시 상태만 사용하며 GameCore/Lua를 다시 호출하지 않고 입력 세대·대기 이벤트를 유지한답니다. 자동 시험만 명시적 캡처 PNG를 남기며 타일 ID 표의 CPU 읽기는 유지하와요. 일정 FPS나 전체 게임 성능 개선률은 아직 검증하지 않았사와요. SDK 규칙·저장 형식·밸런스·Mod ID·설치본·MODS는 바꾸지 않았답니다.

## 앞선 연구 완료 팝업 통합 이력

앞선 후보 `20261005T042314Z_410dcfc80bf1`는 **실제 턴의 연구 완료 → 원본 한국어 TechAwardPopup 표시·계속 버튼 → 1턴 저장 → 새 프로세스 복원·2턴 재저장**을 통과했사와요. 연구 진행도를 비용보다 1 낮게 준비한 시험이며, 남은 연구의 완료와 기술 획득·팝업 요청은 원본 SDK의 턴 처리가 실행했답니다. 기존 F01/F07/N04의 결함 수정이며 원본 3D·전체 UI·한 판 플레이의 완료를 뜻하지 않사와요.

| 최신 자료 | 확인한 범위 |
|---|---|
| [x64 Host 빌드](../evidence/ui_window_host/20261005T042314Z_410dcfc80bf1/build_result.json) | PE32+ x64, EXE SHA-256 `a7dd346b0cab94f3c01e4edf710a41ba37fef28b7cb1676906c60c47e4be3795` |
| [연구 완료 통합 실행](../evidence/interactive_game/20261005T043305Z_91228dbc328d/result.json) | PID 13864; 목축업 연구 36/37 준비 후 실제 턴으로 획득, 원본 popup 68·Data3=2, 계속 버튼 입력, timer 1→0·게임 상태 보존, 1턴 저장 |
| [새 프로세스 복원](../evidence/interactive_game/20261005T043542Z_5e14f45f0798/result.json) | PID 6556; 초기 저장 상태 일치, 원본 도시·구매·연구 트리 조작, 2턴 진행·재저장·정상 종료 |
| [입력·자산·저장 독립 대조](../evidence/interactive_game/validators/20261005T044723Z_81fe8cf36850/conformance.json) | 원본 Lua/XML→생성 헤더→실제 컴파일 입력, 미획득→획득 기술 상태, HWND 세대·원본 계속 버튼·timer 해제, native 저장의 정확한 복사와 초기 복원 상태, 보상 팝업 미재생 대조 통과 |
| [연구 완료 GPU 캡처](../Build/InteractiveGameRuntime/20261005T043305Z_91228dbc328d/sessions/6aef18b2a2e1dbb76cd51235a5beeb53/play-scene-29-gpu.png) | 목축업 제목·한국어 인용문·해제 아이콘·설명·계속 버튼과 양옆 장식. 후면 세계 화면은 개발용 2D |
| [공통 UI 부품 검사](../evidence/ui_scene_component/20261005T042252Z_02e9a2327875/report.json) · [표시 검사](../Tests/ui_pixel_scene.py) | TechAward lifecycle·크기 계산·탭 문자열과 기존 UI 부품 검사 통과; 원본 양옆 스타일까지 표시 검사 176개 통과 |
| [실패 장면의 재컴파일](../evidence/ui_popup/tech_award_replay/20261005T043221Z/manifest.json) | 원본 Image·AlphaAnim 장식을 공통 경로로 준비. 실제 SDK 실행 증거는 위 통합 실행에 별도 보존 |
| [정리 미리보기](../evidence/build_tidy/20261005T044231Z_b3fe2fbdbb8d/cleanup.json) · [정리 결과](../evidence/build_tidy/20261005T044557Z_8e802fff44df/cleanup.json) | 이번 세 빌드의 미참조 오브젝트 12개·50,960,031 논리 바이트(약 48.6MiB) 제거. 보고서·EXE 해시 일치, 동결 입력·저장·캡처 보존. 물리 여유 공간 증가량은 별도 측정하지 않았사와요 |
| [수동 실행 준비](../evidence/interactive_game/20261005T043931Z_3c992ec47c9b/request.json) · [실행 경로 대조](../evidence/interactive_game/20261005T043931Z_3c992ec47c9b/launcher_validation.json) | 자동 시험 옵션 없는 별도 runtime의 새 게임을 기본값으로 연결. 통과 실행과 같은 Host/Core bundle·화면 helper, 총 실행 제한 없음, 기존 수동 저장 해시·보관 엔진 선택 유지 |

당시 [Start-Engine.ps1](../tools/Start-Engine.ps1)의 새 게임 기본 runtime은 `20261005T043931Z_3c992ec47c9b`였답니다. 기존 이어하기와 명시적 불러오기는 저장 당시 보관 엔진을 계속 선택하며, 시험용 저장을 자동 이어하기 목록에 넣지 않았사와요. 이 확인은 실제 자동 통합 시험과 실행 경로 대조의 범위이며, 해당 수동 실행본의 사람 플레이나 전체 게임 완료를 뜻하지 않사와요.

[UiPopupContext.h](../Source/Host/UiPopupContext.h)와 [InteractiveUiSession.h](../Source/Host/InteractiveUiSession.h)는 SDK가 요청하는 TechAward를 원본 base Lua·Expansion2 XML로 실행하와요. [HostServices.h](../Source/Host/HostServices.h)는 원본 연구 알림의 `length=-1` 값을 보존하며, 팝업 닫기는 게임 상태를 바꾸지 않고 원본 timer·processed 콜백을 처리한답니다. 이 변경은 전체 알림 UI나 원본 음향의 완성을 뜻하지 않사와요.

[UiScene.lua](../Source/Host/UiScene.lua)와 [픽셀 장면 도구](../tools/ui_pixel_scene.py)는 원본 한국어 인용문의 `[TAB]`을 보존하와요. 현재 들여쓰기는 해당 GGXML 글꼴의 공백 폭 네 배이며, 원본 게임의 탭 간격과 동일한지는 미검증이랍니다. `DoAutoSize`, 글꼴 배치와 장식 애니메이션도 원본 화면과의 동등성은 남아 있사와요. 원본 Lua/XML·현지화·게임 규칙·밸런스·Mod ID·저장 키·스키마와 설치본·Stage·MODS는 변경하지 않았답니다.

연구 알림의 음수 길이를 거부한 [첫 실패](../evidence/interactive_game/20261005T033549Z_1e8ebd5b8acf/result.json), 인용문의 탭 처리가 없었던 [다음 실패](../evidence/interactive_game/20261005T041545Z_7aaa99cb8671/result.json), 양옆 스타일을 처리하지 못한 [표시 실패](../evidence/interactive_game/20261005T042438Z_69658243b83b/result.json)를 보존했사와요. 마지막 수정은 Python 화면 준비 경로에 적용하여 동일 Host를 재사용했으며 불필요한 C++ 재빌드는 하지 않았답니다.

## 앞선 금 구매 통합 검증 이력

이전 후보 `20261005T023134Z_816dfa798184`는 **원본 도시 구매 창에서 유닛·건물의 금 구매, 원본 효과음, 연구 선택, 1턴 저장 → 새 프로세스 복원 → 2턴 재저장**을 통과했사와요. 복원 뒤 타일 구매 모드에서 구매 창을 연 채 실제 창 닫기를 보내도 도시 선택과 구매 모드를 해제하고 최종 저장을 마쳤답니다. 기존 F05/F07/N01/N04의 진전이며, 전체 원본 UI·3D·한 판 플레이의 완료를 뜻하지 않사와요.

| 최신 자료 | 확인한 범위 |
|---|---|
| [x64 Host 빌드](../evidence/ui_window_host/20261005T023134Z_816dfa798184/build_result.json) | PE32+ x64, EXE SHA-256 `2ab0604f326c2b971df3fd76b0ce9225641ec8d66d3ffc435214289d8c7bfe67` |
| [새 게임 통합 실행](../evidence/interactive_game/20261005T023352Z_67f9e2e154b0/result.json) | 개척자 500금·기념비 280금 구매, 실제 수량 각각 +1, 원본 금 구매 효과음 두 건의 장치 재생 완료, 연구·점령·1턴 저장 |
| [새 프로세스 복원](../evidence/interactive_game/20261005T025109Z_319d4f07a3eb/result.json) | 정찰병 140금·곡창 340금 구매, 2턴 진행, 중첩 구매 창의 WM_CLOSE, 도시 선택/구매 모드 해제와 최종 저장 |
| [입력·빌드·저장 독립 대조](../evidence/interactive_game/validators/20261005T025958Z_20c5c8ccc24e/conformance.json) | 같은 Host/Core/Lua, 원본 버튼의 인자·좌표·입력 세대, SDK 구매 결과, 원본 WAV/XML과 실제 컴파일 바이트, native 저장·복원 상태·2턴·종료 대조 통과 |
| [도시 화면 재진입 GPU 캡처](../Build/InteractiveGameRuntime/20261005T025109Z_319d4f07a3eb/sessions/486932b3e03a83012336afc4b7a0ee25/play-scene-37-gpu.png) | 2턴의 곡창·기념비·위인 진행 막대와 타일 구매 모드. 세계 화면은 개발용 2D |
| [실패 스냅샷의 자산 재준비](../evidence/ui_asset_repair/20261005T024933Z_28084d6a9bd3/result.json) | 원본 `MeterBarGreatPersonBack.dds`의 Scalable BC001 사전/인덱스를 214×29 픽셀로 복원. 이 자료 자체는 SDK 실행 증거가 아니며 실제 복원 실행은 위 행에 별도 보존 |
| [공통 UI 부품 검사](../evidence/ui_scene_component/20261005T021537Z_4d90bfd02eb9/report.json) · [텍스처 경계 검사](../Tests/civ5_ui_assets.py) | 기존 UI 회귀와 독립 타일 재배열·잘못된 인덱스·FPK 경계 등 64개 검사 통과 |
| [빌드 중간물 정리](../evidence/build_tidy/20261005T024822Z_a2a3489afa99/cleanup.json) | 미리보기 후 미참조 오브젝트 20개·81,314,738 논리 바이트 제거. 실행 파일·동결 입력·저장·검증 기록 보존 확인 |

[ProductionCommandGuard.lua](../Source/Host/ProductionCommandGuard.lua)와 [UiPopupContext.h](../Source/Host/UiPopupContext.h)는 원본 구매 콜백의 입력 경계·도시·소유자·활성 턴을 검사하고, Lua 호출이 끝난 뒤 구매 가능 여부를 다시 확인하여 원본 SDK receiver에 전달하와요. [HostServices.h](../Source/Host/HostServices.h)의 공통 오디오 소유자가 팝업을 닫은 뒤에도 구매 소리의 수명을 유지한답니다. 금·신앙·타일 구매 WAV/XML은 원본에서 보존했지만, **신앙 구매의 실제 UI/게임 규칙 경로는 아직 검증하지 않았사와요.** 게임 규칙·밸런스·원본 Lua/XML·Mod ID·저장 키·스키마와 설치본·Stage·MODS는 변경하지 않았답니다.

[UiScene.lua](../Source/Host/UiScene.lua)는 연구 선택창의 반복 전체 배치 계산을 묶어 처리하와요. 같은 Pottery 준비 상태에서 초기 표시의 Lua 명령 계측은 기존 200만 제한 초과에서 453,000으로 내려갔으며 제한 자체는 그대로랍니다. [첫 시간 초과](../evidence/interactive_game/20261005T021945Z_2d6078f3782b/result.json)와 [재시도 시간 초과](../evidence/interactive_game/20261005T022657Z_059d8ef67361/result.json)는 확장된 전체 자동 시험의 기존 180초 총 제한에 걸린 기록이랍니다. 자동 시험의 총 제한만 300초로 조정했고, 화면 준비·Lua의 개별 제한과 수동 게임 동작은 유지했사와요. 이 수치는 전체 턴 성능 향상이나 사람 플레이의 쾌적함을 증명하지 않사와요.

[텍스처 변환기](../tools/civ5_ui_assets.py)는 원본 `UITextures.fpk`의 `FTXTInterface Scalable` + `BC001` 자료를 같은 묶음의 인덱스와 함께 검증하고 픽셀 바이트를 복사해 복원하와요. 표시 정보가 붙은 타일 자료를 일반 픽셀로 오인하지 않으며, 인덱스 누락·표식 불일치·범위 오류는 계속 거부한답니다. [앞선 복원 실패](../evidence/interactive_game/20261005T023809Z_069d2af4a841/result.json)를 보존했고, 성공한 복원은 같은 Host/저장을 수정된 화면 준비 helper로 실행한 결과랍니다. 소스 실행과 복원 실행의 helper 보관본은 서로 다르며 원본 픽셀 동등성은 별도 미검증 항목이랍니다.

자동 구매 시험은 최소 금 5,000·인구 3·작업장 1개와 Pottery 선행 조건을 준비하와요. 이는 정상 성장·생산의 증거가 아니랍니다. 당시 미연결이었던 `TechAwardPopup`은 위 최신 후보에서 연결했지만, 신앙 구매, 나머지 전체 UI·원본 3D, 모드·외부 저장과 한 판 전체의 통합은 남아 있사와요.

## 이전 보관 후보

Host `20261005T010913Z_2204a58d132d`는 원본 CityView의 **전문가 자동 배치 전환·배치/해제, 작업 타일 지정/초기화, 유료 타일 구매와 원본 구매 효과음**을 연결했사와요. 생산 창 복귀·점령·외교 처리·1턴 저장과 새 프로세스의 2턴 재저장을 통과했답니다. 기존 F05/F07/N01/N04의 구현이며, 최종 목표인 원본 UI·조작·3D를 유지한 x64·멀티코어 범위는 그대로랍니다.

| 최신 자료 | 확인한 범위 |
|---|---|
| [x64 Host 빌드](../evidence/ui_window_host/20261005T010913Z_2204a58d132d/build_result.json) | PE32+ x64, EXE SHA-256 `40fa0b7db642ef7c31b35b1cab07c4b7eedc60b6ed80c521a03abfac1f4c2d0f`; 최신 Lua·원본 WAV를 실제 컴파일 입력에 포함 |
| [도시 조작·점령 통합 실행](../evidence/interactive_game/20261005T011034Z_029abca77fbf/result.json) | PID 12144; 도시 8192의 원본 버튼으로 전문가·작업 타일·타일 구매, 가격 40 차감과 소유권 변경; 생산·연구·점령·외교·1턴 저장 |
| [새 프로세스 복원](../evidence/interactive_game/20261005T011227Z_351bfebce3a6/result.json) | PID 32524; 원본 자동 배치 해제→전문가 제거 묶음, 역방향 배치, 다른 타일 구매 가격 25 차감, 2턴 재저장 |
| [입력·컴파일·저장 독립 대조](../evidence/interactive_game/validators/20261005T011407Z_7fc5b8877175/conformance.json) | 원본 버튼 ID·인자·창 세대·보이는 클릭 영역, SDK 결과, 효과음 Started→Completed, 컴파일된 Lua/WAV의 정확한 바이트, 초기 복원 상태 동일성과 native archive 133구획 대조 |
| [타일 구매 뒤 GPU 캡처](../Build/InteractiveGameRuntime/20261005T011034Z_029abca77fbf/sessions/038550f8f40f77abff6fbe5ba799ecf8/play-scene-17-gpu.png) | 원본 도시 프레임·시민 패널·체크 그림과 타일 구매 가격 표시. 세계 화면은 개발용 2D |
| [공통 UI 회귀](../evidence/ui_scene_component/20261005T010005Z_5ea186c42015/report.json) | 좌표 처리 변경 뒤 기존 순위·생산·연구 트리 Lua 부품 검사 통과. 실게임 검증과 별도 범위 |
| [수동 실행 준비](../evidence/interactive_game/20261005T011615Z_a23ddba1df0c/request.json) · [실행 경로 대조](../evidence/interactive_game/20261005T011615Z_a23ddba1df0c/launcher_validation.json) | `새 게임.cmd`가 검증한 Host의 별도 수동 실행본을 선택. 자동 입력·시험용 도시 준비·총 실행 제한 없음. 기존 이어하기는 저장 당시 보관 버전 선택 |

[HostServices.h](../Source/Host/HostServices.h)의 원본 선택 도시 목록과 [UiPopupContext.h](../Source/Host/UiPopupContext.h)의 지연 명령이 원본 `Game.SelectedCitiesGameNetMessage`를 연결하와요. 원본 콜백이 끝난 뒤 선택 도시·소유자·활성 인간 턴·건물·타일 조건을 재확인하고 SDK receiver를 호출한답니다. 전문가 클릭은 자동 배치 해제와 슬롯 명령을 함께 보낼 수 있어 전체 묶음을 먼저 검증하와요. `SetNoAutoAssignSpecialists`가 `DoReallocateCitizens`를 실행한 뒤의 두 번째 명령에서는 재배치로 달라지는 슬롯 조건만 SDK에 맡기고, 도시·건물·종류 조건은 계속 확인하와요. 이를 잘못 거부했던 [복원 실패 기록](../evidence/interactive_game/20261005T010039Z_89cf0b28934e/result.json)도 보존했답니다. 게임 규칙·밸런스와 원본 Lua/XML은 변경하지 않았사와요.

[UiCityView.lua](../Source/Presentation/UiCityView.lua)는 원본 도시 명령의 인자를 전달하고, [UiScene.lua](../Source/Host/UiScene.lua)는 원본 타일 구매 XML의 `Offset="0,"`를 처리하와요. [픽셀 장면 도구](../tools/ui_pixel_scene.py)·[팝업 렌더러](../tools/render_ui_popup.py)는 보존된 `checked`·`disabled` 값으로 원본 `CheckBox.dds`/`CheckBox2TheBox.dds`를 표시한답니다. 상태별 네 프레임 대응은 후보 해석이며 원본 위젯과의 픽셀 동등성을 증명하지 않사와요. 관광 아이콘 문자열·글꼴/숫자 표시와 원본 3D는 아직 미완료랍니다.

[자산 준비 도구](../tools/prepare_ui_popup_assets.py)는 원본 Audio XML과 `SoundData.fpk`의 `notificationbuytile.wav` 47,548바이트를 보존하와요. 원본 WAV의 짧은 마지막 ADPCM 블록과 fact 표본 수도 기록한답니다. [UiAudioPlayback.h](../Source/Host/UiAudioPlayback.h)는 시스템 WinMM으로 재생하고, 구매 receiver 뒤에만 소리를 요청하와요. `Started`는 장치의 버퍼 수락, `Completed`는 재생 완료와 버퍼·장치 정리 성공으로 구분하와요. 종료 정리에 무한 대기를 넣지 않으며, 장치가 버퍼 반환을 확인하지 못하면 소유 메모리를 성급히 해제하지 않고 실패로 남긴답니다. 이 오류 경로의 장치 고장 주입 검사는 아직 없사와요. [Microsoft의 버퍼 반환 규약](https://learn.microsoft.com/en-us/windows/win32/api/mmeapi/nf-mmeapi-waveoutunprepareheader)과 [재생 중지 규약](https://learn.microsoft.com/en-us/windows/win32/api/mmeapi/nf-mmeapi-waveoutreset)에 맞춘 경계랍니다. 원본 음량 60의 WinMM 값 대응은 후보 정책이며 사람의 청취·원본 믹서·전체 게임 음향 동등성은 미검증이랍니다.

자동 시험은 작업장 1개·최소 인구 3·최소 금 200을 준비하며 이를 별도 fixture로 기록하와요. 정상적인 건물 생산이나 도시 성장의 증거로 계산하지 않사와요. 복원 초기 상태는 이 준비 전의 실제 저장 상태와 바이트 동일하며, 이후 두 번째 구매의 가격·소유권을 검사했답니다. [InteractiveGameSession.h](../Source/Host/InteractiveGameSession.h)·[InteractiveGameLoop.h](../Source/Host/InteractiveGameLoop.h)와 [실행 검증기](../tools/run_interactive_game.py)·[독립 대조기](../tools/verify_owned_city_ui.py)에 근거를 연결했사와요.

당시 [Start-Engine.ps1](../tools/Start-Engine.ps1)의 새 게임 기본값은 별도로 준비한 수동 runtime `20261005T011615Z_a23ddba1df0c`였답니다. 자동 시험 저장을 이어하기 목록에 넣지 않았으며, 실제 기존 수동 저장의 버전 선택도 확인했사와요. 이 확인은 실행 경로와 파일 대조이며 사람이 직접 조작한 증거는 아니랍니다. 설치본·MODS·Stage·사용자 저장을 변경하지 않았답니다.

건물 판매·생산 큐 수정·실업 시민 재배치·불태우기 중지는 전달 경로만 연결돼 있으며 실제 실행 검증은 남아 있사와요. 건물/유닛 구매 효과음, 다른 점령 선택, 전체 외교·승리 화면·원본 3D·모드·외부 저장·전체 턴 성능·한 판의 연속 플레이도 미완료랍니다. 이번 자동 통과를 전체 엔진 완성이나 원본 UI 전체 보존으로 계산하지 않사와요.

이번 두 빌드의 [정리 미리보기](../evidence/build_tidy/20261005T011257Z_d7a454ec42bd/cleanup.json)를 확인한 뒤 [미참조 오브젝트 8개를 삭제](../evidence/build_tidy/20261005T011942Z_1e456fe71a9a/cleanup.json)했사와요. 제거량은 32,021,840 논리 바이트(약 30.5MiB)이며 물리 여유 공간 증가량은 측정하지 않았답니다. 빌드 보고서·EXE의 보존 해시는 일치했고 동결 입력·실행 기록·저장·캡처는 삭제 범위에서 제외했사와요.

아래는 이번 전문가·타일 명령 연결 이전의 기준 기록이랍니다. 이전 수동 기본 버전과 당시 미완료 설명은 위 최신 상태와 구분하와요.

2026-10-05 일반 도시의 원본 CityView 조작을 Host `20261004T165154Z_68deb24e165f`에 연결했사와요. 도시 클릭으로 편집 가능한 화면을 열고, 시민 집중·성장 억제와 생산 선택을 원본 콜백으로 적용한 뒤 같은 도시 화면으로 돌아오와요. 점령 도시의 읽기 전용 보기 경로도 함께 통과했으며 최종 목표인 원본 전체 UI·조작·3D를 유지한 x64·멀티코어 범위는 그대로랍니다.

| 최신 자료 | 확인한 범위 |
|---|---|
| [x64 Host](../evidence/ui_window_host/20261004T165154Z_68deb24e165f/build_result.json) | PE32+ x64, 일반 도시 진입·시민 명령·원본 생산 창의 부모 CityView 보존; Lua 생성 카탈로그 자동 갱신과 입력 동결 |
| [실제 통합 실행](../evidence/interactive_game/20261004T165558Z_17a5347255a4/result.json) | 일반 도시 8192의 WorkerHeader·생산 집중·성장 억제·생산 선택·Return, 점령 도시 16385의 보기·복귀·괴뢰 선택, 외교 나가기, 0→1턴·저장·정상 종료 |
| [새 프로세스 복원](../evidence/interactive_game/20261004T165833Z_c0923c72fc51/result.json) | PID 26036→22316; 시민 집중 1·성장 억제 1을 복원 초기 상태에 보존한 뒤 원본 UI로 0·0으로 변경; 생산·연구·1→2턴·재저장·정상 종료 |
| [도시 UI·저장 독립 대조](../evidence/interactive_game/validators/20261004T172016Z_1be5689ee58a/conformance.json) | 두 실행의 원본 버튼 ID·인자·보이는 클릭 영역·창 입력 세대, SDK 설정 변경·중첩 생산·동일 도시 복귀, 최신 Lua의 실제 컴파일 입력, 저장 복사본과 133구획·2턴 재저장 대조 통과 |
| [원본 생산 창의 합성](../Build/InteractiveGameRuntime/20261004T165558Z_17a5347255a4/sessions/cd992776f5338d2f44aec5b0d36f1b9e/play-scene-11-gpu.png) · [같은 도시 화면 복귀](../Build/InteractiveGameRuntime/20261004T165558Z_17a5347255a4/sessions/cd992776f5338d2f44aec5b0d36f1b9e/play-scene-12-gpu.png) | 부모 CityView의 오른쪽 시민 관리와 세계 배경을 보존한 생산 창, 주문 뒤 원본 도시 생산 정보의 갱신 |
| [기존 공통 UI 회귀](../evidence/ui_scene_component/20261004T164517Z_bc19c2c8bd97/report.json) | 순위·생산·연구 트리의 기존 Lua 부품 검사 통과 |

변경은 기존 F05/F07/N01/N04에 해당하와요. [InteractiveUiSession.h](../Source/Host/InteractiveUiSession.h)는 일반 도시 진입과 중첩 생산 창·부모 Lua 상태·두 단계 종료를 관리하고, [UiPopupContext.h](../Source/Host/UiPopupContext.h)와 [UiCityView.lua](../Source/Presentation/UiCityView.lua)는 원본 `SendSetCityAIFocus`·`SendSetCityAvoidGrowth` 요청을 Lua 호출이 끝난 뒤 원본 SDK receiver에 전달하와요. 적용 직전에도 활성 인간 플레이어의 턴, 선택 도시의 owner/ID, 일반 도시 모드와 괴뢰 여부를 확인한답니다. [InteractiveGameSession.h](../Source/Host/InteractiveGameSession.h)·[InteractiveGameLoop.h](../Source/Host/InteractiveGameLoop.h)는 실제 세계 클릭·원본 UI 입력·합성·SDK 값 조회·저장 흐름을 연결하며, 부모 화면의 입력은 활성 생산 창 아래에서 전달하지 않사와요.

[UiInputDispatch.h](../Source/Host/UiInputDispatch.h)는 원본 시민 버튼의 `void1`만 있는 인자를 그대로 보존하와요. 기존 생산·연구의 두 인자 계약도 유지한답니다. [UiScene.lua](../Source/Host/UiScene.lua)는 CityView Bottom Stack 자식의 양수 Offset을 다음 행 간격과 크기 계산에 반영하와요. 실제 좌표에서 CityGrowthLabel은 y=67..80, FoodBox는 기존 y=69에서 y=101로 내려가 둘의 겹침이 해소됐답니다. [픽셀 장면 도구](../tools/ui_pixel_scene.py)는 일반 모드 false와 보기 모드 true를 각각 유효한 CityView 입력으로 검증하며, [통합 실행 검증기](../tools/run_interactive_game.py)는 일반 도시와 점령 도시의 증거를 서로 다른 owner/ID·원본 스냅샷에 연결하와요.

[빌드 도구](../tools/build_ui_window_host.py)는 컴파일 전 [원본 UI 카탈로그 생성](../tools/prepare_ui_popup_assets.py)을 반드시 수행하와요. 앞선 두 빌드는 수정 Lua를 보관하면서도 실제 generated header에는 이전 코드가 들어가, 원본 집중 버튼에서 `SendSetCityAIFocus`가 없다는 오류가 드러났답니다. 최종 빌드에는 생성 명령·로그·갱신한 헤더와 입력을 함께 보존했고, 실제 SDK 설정 변경까지 통과했사와요. 앞선 실패 실행과 검증기 실패 기록도 그대로 남겼답니다.

[독립 검증기](../tools/verify_owned_city_ui.py)는 소스 실행과 복원 실행 각각의 원본 CityView 입력·SDK 수신·생산 창 복귀를 대조하와요. 준비 보고서와 실제 컴파일에 사용된 생성 헤더의 Lua 바이트를 현재·동결 입력에 연결하고, 동일 Host/Core/Lua와 서로 다른 프로세스·저장 구획·다음 턴을 함께 검사했답니다. 최초 실행에서 드러난 검증기의 누락된 보관 목록, 보고서 경로 항목, 일반 도시와 점령 보기의 구분, 도시 ID와 생산 복귀 로그 필드 해석을 바로잡았으며 최종 결과는 `OWNED_CITY_ORIGINAL_UI_AND_FRESH_NATIVE_RESTORE_TURN_TWO_PASS`랍니다.

이 통과는 한국어 자동 창 입력의 특정 도시·점령·저장 경로이며, 사람의 전면 창 조작이나 한 판 전체의 완료 증거는 아니랍니다. 전체 원본 3D·일반 도시의 나머지 명령과 구매·활성 모드·외부 저장 호환은 남아 있사와요. 관광 태그 문자열과 글꼴·체크 그림·위젯·애니메이션의 원본 표시 동등성도 미완료랍니다. 게임 규칙·밸런스·Mod ID·버전·저장 키·스키마·설치본·Stage·MODS는 변경하지 않았으며, 수동 실행 기본 버전은 기존 보관본이랍니다.

검증 뒤 [첫 두 빌드 정리](../evidence/build_tidy/20261004T165619Z_8c407461dea9/cleanup.json)와 [최종 빌드 정리](../evidence/build_tidy/20261004T170446Z_e0611b598427/cleanup.json)로, 미리보기에서 확인한 오브젝트 12개·47,301,199 논리 바이트(약 45.1MiB)를 제거했사와요. 실행 파일·동결 입력·검증 로그·저장·GPU 캡처의 보존 해시는 유지됐으며, 실제 디스크 여유 공간 증가량으로 해석하지 않사와요.

아래는 일반 도시 조작 연결 이전의 점령 도시 보기 기준 기록이랍니다.

2026-10-05 이전 Host `20261004T160411Z_711fa960c852`에서 **도시 점령 → 원본 ‘도시 보기’ → 읽기 전용 CityView → 같은 점령 창으로 복귀 → 괴뢰정부 선택 → 외교 나가기 → 1턴 저장 → 새 프로세스 복원 → 2턴 재저장**을 통과했사와요. 목표는 원래 문명 5의 UI·조작·3D 세계 화면을 유지한 64비트 실행과 멀티코어 활용이며, 현재 2D 세계 창과 일부 원본 Lua/XML 연결은 개발 중간 단계랍니다.

| 최신 자료 | 확인한 범위 |
|---|---|
| [x64 Host 빌드](../evidence/ui_window_host/20261004T160411Z_711fa960c852/build_result.json) | PE32+ x64, 선택 도시 수명·CityView 진입과 복귀·일시 보존한 점령 팝업의 재개 |
| [도시 보기 통합 실행](../evidence/interactive_game/20261004T161349Z_e639bb465ff6/result.json) | 원본 CityView_small.xml·CityView.lua, View/Return/Puppet 자동 창 입력·장면 세대·콜백 순서, SDK 상태와 타이머, 0→1턴·저장·정상 종료 |
| [별도 프로세스 복원](../evidence/interactive_game/20261004T161511Z_09441ee9bcf2/result.json) | 괴뢰도시·상대 수도 보존, 원본 생산·연구 트리, 1→2턴·재저장·정상 종료 |
| [저장 파일 독립 대조](../evidence/interactive_game/validators/20261004T161813Z_c32d9cf4e97b/conformance.json) | 동일 Host/Core/provider·서로 다른 PID, 최종 저장과 복사본 동일, 133구획 중 132개 바이트 동일; Game 구획은 원본 reload 기록·세션 증가만 허용 |
| [도시 화면 GPU 캡처](../Build/InteractiveGameRuntime/20261004T161349Z_e639bb465ff6/sessions/73756ac9beec6f22ad89012568c45be7/play-scene-17-gpu.png) | 원본 도시 프레임·한국어 도시 이름·건물 패널·복귀 버튼 표시; 정보 글자 겹침도 남아 있사와요 |
| [공통 UI 회귀 검사](../evidence/ui_scene_component/20261004T160115Z_c368b3a6a749/report.json) | 공통 좌표·Stack·ScrollPanel 처리 변경 후 기존 순위·생산·연구 트리 부품 검사 통과 |

이 작업은 기존 F05/F07/N01/N04의 점령·도시 UI와 저장 연결에 해당하와요. [HostServices.h](../Source/Host/HostServices.h), [UiPopupContext.h](../Source/Host/UiPopupContext.h), [InteractiveUiSession.h](../Source/Host/InteractiveUiSession.h), [InteractiveGameSession.h](../Source/Host/InteractiveGameSession.h), [InteractiveGameLoop.h](../Source/Host/InteractiveGameLoop.h)에서 도시 소유자와 ID로 SDK 객체를 다시 조회하고, 원본 시민 갱신 receiver를 Lua 호출 밖에서 실행하도록 연결했사와요. 점령 팝업의 Lua 상태는 도시 보기 동안 보존하며 원본 Return 콜백 뒤에 재개하와요. 도시 화면 표시 시점과 복귀 시점의 SDK 상태는 바이트 동일했답니다. 진입 시 시민 갱신 전후 기록도 보존했지만, 그 갱신 자체가 시민 배치를 절대 변경하지 않는다는 주장으로 확대하지 않사와요.

[UiScene.lua](../Source/Host/UiScene.lua), [UiCityView.lua](../Source/Presentation/UiCityView.lua), [UiPresentationInput.lua](../Source/Presentation/UiPresentationInput.lua), [ScriptSystem.h](../Source/Host/ScriptSystem.h)에서 원본 small/default 레이아웃 선택·선택 상태·스크롤·자동 Stack 크기·좌표·체크 위젯·FlipAnim과 포함 파일 조회를 연결했사와요. [WorldViewRenderer.cpp](../Source/Presentation/WorldViewRenderer.cpp)와 해당 헤더는 전체 도시/외교 화면에서 임시 HUD를 감추며, [준비 도구](../tools/prepare_ui_popup_assets.py), [픽셀 장면 도구](../tools/ui_pixel_scene.py), [팝업 렌더러](../tools/render_ui_popup.py), [입력 드라이버](../tools/interactive_ui_driver.py), [실행 검증기](../tools/run_interactive_game.py), [빌드 도구](../tools/build_ui_window_host.py)는 동결 원본·소스·입력 증거와 연결됐답니다. 원본 에셋·게임 규칙·밸런스·Mod ID·버전·저장 키·스키마·설치본·Stage·MODS는 변경하지 않았사와요.

**현재 UI가 원본과 완전히 같다는 증거는 없사와요.** 실제 GPU 캡처에는 좌측 도시 정보의 글자 겹침과 원본 small XML의 불완전한 `[ICON_TOURISM` 문자열이 남아 있답니다. small XML이 생략한 글꼴은 원본 standard XML의 글꼴로 보완했고, 체크 그림·FlipAnim의 음수 Pause·일부 이미지 확대는 명시적인 후보 해석이랍니다. 이들의 원본 표시·시간 동등성은 미검증이며, 세계 화면은 임시 2D이고 원본 yield overlay도 아직 렌더링 검증을 통과하지 않았사와요. `TutorialPopupScreen`은 [원본 파일과 147개 FPK 이름 색인 조사](../evidence/ui_popup/assets/city_view_include_inventory/20261004T152005Z_7d5697235c29/city_view_include_inventory.json)에서 찾지 못했으며 빈 대체 소스를 넣지 않았답니다. 튜토리얼 실행은 미검증으로 남기와요.

이번 통과는 자동 창 입력과 GPU 후면 버퍼 캡처를 사용한 점령 도시의 읽기 전용 보기 경로랍니다. 사람이 실제 전면 창에서 조작한 증거, 일반 소유 도시 진입·전체 도시 명령, 합병·불태우기·해방, 전체 외교·원본 3D·실제 음향·외부 저장·활성 모드·한 판 전체는 남아 있사와요. 시험 준비에서 상대 수도와 별도 점령 도시를 만들고 표적 체력을 낮췄으므로 자연적인 AI 확장·정상 생산 증거로 계산하지 않사와요. 독립 저장 대조기는 점령과 복원 파일을 검증하며, CityView 입력 검증은 통합 실행의 별도 검사에 있답니다. 최신 시험 후보를 수동 실행 기본 버전으로 바꾸지 않았사와요.

최종 실행까지의 실패 기록과 렌더 준비 기록은 보존했사와요. [첫 정리](../evidence/build_tidy/20261004T155212Z_558423487ba5/cleanup.json)와 [두 번째 정리](../evidence/build_tidy/20261004T161857Z_abb5abce2480/cleanup.json)에서는 각각 미리보기를 대조한 뒤 참조되지 않은 오브젝트 총 32개·125,756,380 논리 바이트(약 119.9MiB)를 제거했답니다. 실행 파일·동결 입력·저장·GPU 캡처·검증 기록의 보존 해시가 유지됐으며, 물리 여유 공간 증가량을 측정한 값은 아니랍니다.

아래는 CityView 연결 이전의 기준 기록이며, 당시 미완료 문구는 위 최신 증거와 구분하와요.

2026-10-04 이전 Host `20261004T142446Z_bcd9e468c403`에서 **도시 점령 → 원본 괴뢰정부 선택 → 원본 외교 창의 나가기 → 1턴 저장 → 새 프로세스 복원 → 2턴 재저장**을 통과했사와요.

| 자료 | 이번에 확인한 범위 |
|---|---|
| [x64 Host 빌드](../evidence/ui_window_host/20261004T142446Z_bcd9e468c403/build_result.json) | PE32+ x64, 점령·외교의 소유 큐와 원본 콜백, 괴뢰도시 생산 선택 제한 |
| [실제 점령 실행](../evidence/interactive_game/20261004T142639Z_a016d37121eb/result.json) | 한국어 원본 점령 팝업의 괴뢰정부 클릭, 실제 SDK TASK_CREATE_PUPPET=19, 첫 외교 대사·BackButton 클릭, 0→1턴·저장·정상 종료 |
| [별도 프로세스 복원](../evidence/interactive_game/20261004T142837Z_78b64a3df42c/result.json) | 괴뢰도시·상대 수도 보존, 생산 가능한 본래 도시의 원본 생산·연구 트리, 1→2턴·재저장·정상 종료 |
| [저장 파일 독립 대조](../evidence/interactive_game/validators/20261004T143555Z_844290b6b069/conformance.json) | 동일 Host/Core/provider·별도 PID, 최종 저장과 복사본 동일, 의미 상태·도시 지배 상태·133구획과 DB 무결성, 원본 reload 변화만 허용 |

플레이어 0이 점령한 도시 16385는 원소유자 1의 괴뢰도시로 유지됐고, 플레이어 1의 수도 8192도 남았사와요. 수도가 없던 상대는 시험 준비에서 원본 SDK 창건 경로로 수도를 먼저 세웠고, 별도로 만든 점령 대상 도시만 체력 1로 맞췄답니다. 자연적인 AI 확장이나 정상 생산을 검증한 시험으로 확대하지 않사와요. 복원 직후 다섯 도시의 소유권·좌표·괴뢰/불태우기·원소유자·수도·도시 수·생존 상태가 모두 선행 최종 상태와 일치했답니다. 저장 133구획 중 132개는 바이트 동일하며 Game 구획은 기존 replay 10건을 보존한 채 불러오기 기록 1건과 세션 1→2만 추가됐사와요.

원본 `GenericPopup/PuppetCityPopup`의 전체 팝업 값과 callback을 유지하고, 필수 점령 선택이 끝난 뒤 대기 중인 `LeaderHeadRoot` 첫 인사를 열도록 연결했사와요. 원본 외교용 영어 검색 카탈로그는 private rules 연결의 임시 테이블로 제공하며 실제 한국어 대사와 원본 문구를 대조했답니다. `WarStateChanged`의 소유 값 전달, `Locale.Substring`과 PreGame 이름 조회, 숫자 RGBA 태그, 미지정 Stack 크기, 원본 아이콘의 표시 분기와 GridButton 문구 처리를 보완했사와요. 원본 에셋·게임 규칙·밸런스·Mod ID·버전·저장 키·스키마·설치본·Stage·MODS는 변경하지 않았답니다.

[이전 복원 실패](../evidence/interactive_game/20261004T142111Z_6ff3d073cfcb/result.json)는 복원 상태가 일치한 뒤 괴뢰도시에 생산 창을 요청해 발생했사와요. 원본 `ProductionPopup.OnPopup`은 괴뢰도시의 생산 직접 선택을 거부하므로 Host도 큐에 넣기 전에 같은 제한을 적용하와요. 최신 [복원 stdout](../evidence/interactive_game/20261004T142837Z_78b64a3df42c/stdout.log)의 `INTERACTIVE_PUPPET_PRODUCTION_GUARD=16385|HOST_CALL_REJECTED`는 이 진입점의 직접 호출 거부 증거랍니다. 괴뢰도시 생산 버튼을 실제 창에서 클릭한 증거로 계산하지 않사와요. 원본 괴뢰정부 선택과 외교 나가기에는 별도의 자동 HWND 클릭·원본 callback 증거가 있답니다.

실제 GPU 캡처의 [점령 창](../Build/InteractiveGameRuntime/20261004T142639Z_a016d37121eb/sessions/8748e4f09a53ad2ca7c71e5cdf3e0a3d/play-scene-16-gpu.png)과 [외교 창](../Build/InteractiveGameRuntime/20261004T142639Z_a016d37121eb/sessions/8748e4f09a53ad2ca7c71e5cdf3e0a3d/play-scene-17-gpu.png)에서 한국어 문구·문명 아이콘·버튼 표시를 확인했사와요. 외교 화면 뒤에는 임시 세계 HUD가 남아 일부 겹치며, 지도자 3D·원본 전체 합성·글꼴/비활성 색상/효과의 retail 동등성은 미검증이랍니다. ‘도시 보기’의 원본 CityView, 다른 점령 선택의 실제 통합 검증, 거래·논의·요구·평화 협상, 승리 처리·음향·외부 저장·활성 모드·사람의 한 판 플레이도 남아 있사와요. 최신 후보를 수동 실행 기본 버전으로 바꾸지 않았답니다.

최종 검증 뒤 [정리 미리보기](../evidence/build_tidy/20261004T144137Z_653f87c83bd4/cleanup.json)와 [정리 결과](../evidence/build_tidy/20261004T144418Z_5e0562acc606/cleanup.json)를 대조해, 여섯 빌드의 참조되지 않은 오브젝트 24개·81,233,789 논리 바이트(약 77.5MiB)를 제거했사와요. 실행 파일·동결 입력·저장·검증 기록의 보존 해시는 유지됐으며, 물리 여유 공간 증가량을 측정한 값은 아니랍니다.

아래는 이번 점령 연결 이전부터 보존한 검증 이력이랍니다.

2026-10-04 전투 후보 Host `20261004T103804Z_67cc9869ddb7`에서 현재 보이는 외국 유닛·적대 여부·체력을 표시하고, 대상 타일 클릭을 원본 근접 이동 공격 또는 `MISSION_RANGE_ATTACK`으로 연결했사와요. 소유자와 유닛 ID를 함께 식별하며, 숨겨진 타일이나 은폐 유닛의 정보를 화면에 넘기지 않사와요. 명령 직전에도 가시성·전쟁 관계·이동력·원본 공격 가능 판정을 확인하와요. 근접 공격은 인접 타일에 한정하고 새 선전포고가 필요한 이동을 거부하와요. 체력 표시는 SDK 최대 체력을 사용한답니다.

[실제 SDK 전투 검사](../evidence/interactive_game/20261004T104051Z_d6485e912eae/result.json)는 네이티브 창의 공격 클릭, 전투 콜백의 정확한 참가자, 전후 피해·경험치, 적 전사, 다음 턴과 저장을 통과했사와요. 원본 유닛 두 쌍을 시험 준비로 생성했고 원거리 표적만 체력 1로 시작했답니다. 근접 공격 후 아군 피해 28·경험치 5, 야만인 피해 35·경험치 0을 확인했고, 원거리 공격은 표적 제거와 경험치 2를 확인했사와요. 원본 전투 수치·규칙을 변경하지 않았으며, 이 시험 준비를 정상 생산이나 사람의 플레이 증거로 계산하지 않사와요.

[새 프로세스 복원 검사](../evidence/interactive_game/20261004T104206Z_6914d051e35d/result.json)는 전투 후 1턴 저장의 상태 표본이 완전히 일치함을 확인한 뒤, 방어 태세·이동·도시 선택·생산·연구 트리·2턴·재저장·정상 종료까지 통과했사와요. 도시로 카메라를 옮길 때 화면 밖 유닛의 클릭 사각형을 그대로 내보내던 결함도 수정했답니다. [최종 파일·상태 직접 대조](../evidence/interactive_game/20261004T104206Z_6914d051e35d/combat_review.json)에 현재 소스와 동결 빌드의 일치, 실제 수치와 복원 상태를 기록하와요.

이 전투 검증 다음 단계였던 도시 점령·괴뢰 선택·외교 복귀·저장 재개는 위 최신 후보에서 확인했사와요. 다른 점령 선택의 실제 통합 검증과 원본 CityView·전체 외교·렌더러·음향·저장 호환성·한 판 전체 완료 기준은 계속 남아 있답니다. 아래 수동 실행 `.cmd`는 기존 보관 버전을 선택하와요.

전투 작업의 실패 기록도 보존했사와요. [첫 검사](../evidence/interactive_game/20261004T103230Z_542500bb383a/result.json)는 야만인 경험치 증가를 잘못 요구한 검증기 결함이었고, SDK `CvUnit::changeExperience`의 야만인 예외에 맞춰 수정했답니다. [첫 복원 검사](../evidence/interactive_game/20261004T103653Z_64232f21d93e/result.json)는 위 클릭 영역 결함을 실제로 드러낸 실행이랍니다. 성공 기록으로 덮어쓰지 않았사와요.

두 전투 빌드의 검증 후 [중간 파일 정리](../evidence/build_tidy/20261004T104828Z_a5d63c431ccc/cleanup.json)로 참조되지 않은 오브젝트 8개·23,974,665 논리 바이트를 제거했사와요. 실행 파일·동결 입력·저장·검증 보고서의 보존 해시를 대조했으며, 물리 여유 공간 증가량을 측정한 값은 아니랍니다.

2026-10-04 수동 실행 `20261003T231546Z_820e150e7872`에서 실제 이동 뒤 연구 창을 열 때 `Interactive replacement scene could not commit after bounded input drain`으로 종료됐사와요. [실패 실행](../evidence/manual_play/20261003T231546Z_820e150e7872/launch.json)은 보존했답니다. Host `20261003T235743Z_f2f8e581fe1f`는 PNG를 반복해서 읽던 교체 루프를 제거하고, 메시지를 최대 256개 처리한 뒤 이전 세대 입력을 보존하면서 한 번에 교체하와요. 게임 명령은 이전 세대를 거부하며 닫기 요청은 저장 경로에 전달하와요. 물리 입력의 정확한 화면 경계는 밀리초 timestamp만으로 증명하지 않사와요.

[창 처리 검사](../evidence/bitmap_window/20261003T233635Z_0522c0079f99/conformance.json)는 O2/Od 각각 87개 항목을 통과했사와요. 1,024개 마우스 메시지 적체, 잘못된 교체 자료의 실패 보존, 이전 세대 클릭·포인터·닫기 요청, 입력 큐 초과 보고와 새 세대 입력을 확인했답니다. [새 게임 검사](../evidence/interactive_game/20261004T000242Z_8b9bc6fbbb24/result.json)는 원본 명령·농장 완공·6턴 저장과 화면 교체 중 닫기 뒤 최종 저장을 통과했사와요. [새 프로세스 재개 검사](../evidence/interactive_game/20261004T000459Z_088cb8b3a5ba/result.json)는 초기 의미 상태 동일성·합법 방어 태세·생산/연구·7턴과 팝업 준비 중 닫기 뒤 최종 저장을 통과했답니다. 각각 자동 HWND 입력의 증거이며, 연속 사람 입력이나 한 판 전체 완료의 증거로 확대하지 않사와요.

추가 검토에서 제기했던 종료 시 저장 누락 우려는 `QueueClose`의 gameplay 분기를 잘못 읽은 결과였사와요. 원래도 gameplay 닫기는 HWND와 `IsOpen()`을 유지하며 저장을 기다린답니다. 이 조건을 거꾸로 요구한 [235440 검사 실패](../evidence/interactive_game/20261003T235440Z_84b7c2116454/result.json)를 보존했고, 게임 동작을 바꾸지 않고 검사 조건을 바로잡았사와요. 닫기 요청 뒤 추가 화면 적용을 생략하는 guard와 두 종료 시점의 회귀 검사는 유지하와요. [최종 대조 기록](../evidence/interactive_game/20261004T000459Z_088cb8b3a5ba/scene_input_review.json)에 현재 소스·수동 실행 파일의 해시 일치, 저장 버전 선택, 창 응답 관측과 중간 오브젝트 12개·35,585,459 논리 바이트 정리를 함께 기록했답니다.

2026-10-04 직접 실행 경로를 [엔진 실행](../엔진%20실행.cmd)·[새 게임](../새%20게임.cmd)·[저장 불러오기](../저장%20불러오기.cmd)에 연결했사와요. 최신 수동 runtime은 `20261004T000710Z_796f1ea91c5e`이며, 기존 `20261003T230735Z_2003f24507ce`와 `20261003T154510Z_b1af9e8eb764`도 이전 저장을 위해 보관하와요. 새 게임은 최신 수정본으로 시작하며, 이어서 하기는 수동 runtime의 마지막 저장을 찾아 저장 내부 Bundle과 일치하는 버전을 선택하와요. 수동 저장이 없으면 새 게임으로 시작하고, 시간 제한 0·자동 입력 없음·단일 실행을 유지하와요. 이전 저장은 이전 버전으로 열리며 자동 변환하지 않사와요. [조작과 현재 범위](../바로%20실행%20안내.txt)

Host `20261003T174144Z_ed5ac73609cd`의 [통합 실행](../evidence/interactive_game/20261003T174431Z_03aae6d96254/result.json)에서 실제 원본 방어 태세·이동·생산·연구 트리 선택과 농장 완공을 확인했사와요. 원본 UnitPanel의 이동력 조건에 맞춰 이동력이 없는 유닛의 행동을 숨기고, 명령 직전에도 다시 확인하와요. 건설 전용 시험은 원본 InitUnit으로 일꾼 하나를 생성하며 생산 시간을 건너뛴 시험 준비임을 명시하와요. 건설 진행은 200 → 첫 다음 턴 200 → 300 → 400 → 500 → 600 → 6턴 농장 완공이었고, 원본 건설 시간·작업 속도·기술을 변경하지 않았답니다. 첫 새 턴의 대기는 같은 BUILD 미션·같은 건설 ID·회복된 이동력이 남아 있을 때만 허용하며, 이후에는 실제 진행도 증가를 요구하와요.

그 저장을 [새 프로세스에 복원](../evidence/interactive_game/20261003T230319Z_b522e4e36dcd/result.json)해 실제 이동·원본 생산·연구 트리 선택·7턴·재저장을 통과했사와요. [저장 파일 직접 대조](../evidence/interactive_game/20261003T230319Z_b522e4e36dcd/worker_restore_review.json)는 원본과 복사본의 동일성, 초기 의미 상태, 농장 ID 3의 유지, 133개 native 구획 중 132개의 바이트 동일성을 확인하와요. Game 구획의 차이는 원본의 불러오기 replay와 session counter 증가뿐이랍니다. GPU 캡처에서 농장·도로의 한국어 이름과 버튼 배치도 검토했지만 원본 3D·전체 UI·사람의 한 판·원본 저장·활성 모드 동등성은 미완료랍니다.

보존된 [174554 재개 실패](../evidence/interactive_game/20261003T174554Z_fb47a26e050b/result.json)는 복원 상태가 일치한 뒤 시험이 첫 비개척자 유닛인 일꾼에게 방어 태세를 요구한 결과랍니다. 최신 시험은 이동력·원본 `CanStartMission`·현재 activity를 확인해 합법적인 방어 유닛을 고르며, 위 000459 재개에서 `--unit-actions`까지 통과했사와요. 기존 실패 기록은 그대로 보존하와요.

같은 세계 창의 한국어 원본 연구 트리도 [실행 151838](../evidence/interactive_game/20261003T151838Z_d5129b807a9a/result.json)와 [독립 대조 154410](../validators/20261003T154410Z_b98a46674ce9/conformance.json)를 통과했사와요. 생산 → TechPopup의 OpenTTButton → TechTree tech 1 → 선택 후 열린 상태 유지 → native Escape timer 1→0 → 정상 턴·저장을 같은 HWND·장치의 15개 장면으로 연결했답니다. 요청 key 790 위의 원본 작은 버튼 B2(key 870)가 실제 입력을 받으므로 게시 위치·맨 위 hit 순서·같은 연구 payload와 원본 Lua 등록을 모두 검사하와요. 아래 104543 Host와 1→2턴 pair는 기존 연구 목록 경로의 보존된 기준이며, 새 연구 트리 전체 재개 pair로 바꾸어 주장하지 않사와요.

2026-10-03, `--play <language>`와 private native 저장을 새 프로세스에서 이어 가는 `--play-load <language> <checkpoint>`에 원본 생산·연구 선택 창을 연결했사와요. 같은 세계 창에서 실제 도시 건설 → 원본 생산·연구 콜백 → 정상 1턴 → 저장·닫기를 수행하고, 별도 프로세스에서 그 저장을 복원해 원본 창을 다시 열고 2턴·재저장까지 통과했답니다. 도시·생산·연구 진행 상태와 모든 native 저장 구획을 독립 대조했사와요. 한국어 고정 시험의 자동 HWND 입력이며, 현재 세계 그림은 첫 2D 전략 지도이고 원본 3D·전체 UI·사람 조작의 완성 증거는 아니랍니다.

## 변경과 경계

- `Source/Host/InteractiveGameSession.h`가 명령용 VM·실제 Game/Map/receiver·LocalSdkSession·LocalTurnController·native autosave를 GameCore 세션 동안 소유하와요. 종료 때 이들을 Core unload 전에 해제하와요.
- `InteractiveGameLoop.h`는 소유 스레드의 짧은 `Session::WithCore` 호출에서만 SDK 입력·갱신·상태 수집을 수행하와요. 창 메시지 처리·대기·표시는 Core lock 밖에서 처리하며 WndProc은 게임 규칙을 직접 호출하지 않사와요.
- `InteractiveUiSession.h`가 원본 popup 요청을 중앙 큐에 보관하고 현재 Lua 콜백이 끝난 소유자 경계에서 context를 열거나 닫사와요. 생산·연구 창은 세계 창과 같은 HWND·D3D 장치를 사용하며, 원본 콜백의 payload와 실제 SDK receiver 경로를 유지하와요. 열린 popup은 저장·턴 종료를 막고, 종료 때 context·타이머·binding을 Core unload 전에 정리하와요.
- retained scene을 값 복사한 뒤 Core lock 밖에서 원본 자산의 표시 packet을 준비하와요. `INTERACTIVE_UI_SCENE_REQUEST`와 정확한 LF 끝의 `UI_READY` 응답을 연결하며, 준비 중 입력과 오래된 세대는 거부하와요. driver·자산 목록·renderer는 실행마다 동결하고 기록해 이전 성공 실행의 재개 입력을 보존하와요.
- `LocalSdkSession.h`의 기본 경로는 기존 founding만 지원하와요. 명시적 live profile에서 이동·대기와 방어 태세·회복·비활성화·경계·약탈·시설 건설을 허용하와요. 시설 건설은 실제 SDK BuildInfo ID와 `(buildID,-1,flags=0,shift=false)`를 확인하며, 나머지 자세 행동은 `(-1,-1,0,false)`만 사용하와요. 소유권·현재 턴·단일 선택·busy 상태·좌표·원본 mission 이름과 실제 `CanStartMission`을 재검사한 뒤 receiver에 전달하와요. 이 legality 질의 자체를 장거리 경로 도달의 증명으로 해석하지 않사와요.
- `WorldViewState.h`가 정확한 plot/unit identity와 현재 플레이어의 탐색·가시 상태를 값 복사하와요. 미탐색 지형과 보이지 않는 현재 도시 정보는 표시 자료에 포함하지 않으며 SDK adapter는 수집 함수 밖으로 나가지 않사와요.
- `Source/Presentation/WorldViewRenderer.h/.cpp`는 실제 snapshot의 1920×1080 지도 PNG와 안정적인 hit key를 생성하와요. 기존 BitmapWindow의 1280×720 client·letterbox·D3D 장치를 재사용하와요. 키보드는 방향키·Tab·Space·Enter·F5·Escape를 명시적으로 허용하와요.
- 플레이 경로의 WM_CLOSE는 닫기 요청을 보관하고 진행 중인 턴이 안정된 뒤 저장하와요. 창과 Core 정리는 그 뒤에 진행하며 기존 popup의 닫기 정책은 유지하와요.
- `tools/run_interactive_game.py`는 기존 Core·provider와 cache를 재사용해 격리 runtime을 만들고, 같은 loop에 유한 HWND 입력을 보내는 `--smoke`를 제공하와요. 설치본·활성 SDK·Stage·MODS·사용자 기존 저장은 수정하지 않사와요. Mod ID·버전·save key·schema·규칙과 밸런스도 변경하지 않았답니다.

## 저장을 이어 가는 경로

- `HostMain.cpp`가 checkpoint 절대 경로를 runtime 디렉터리 변경 전에 확정하와요. 불러오기에서는 새 게임을 먼저 만들지 않고 pristine GameCore에 `SdkGameRestore::Load`를 적용한 뒤 실제 Map/Game/receiver와 명령용 VM을 연결하와요.
- `InteractiveGameSession.h`가 원본 `InitTacticalAnalysisMap`, 각 player의 `LaterInit`, `DoGameStarted`를 한 번씩 수행하와요. 복원 직후의 native 구획과 세 번의 정상 idle update에서 turn·elapsed·active player·의미 상태 표본을 대조하와요.
- 새 게임과 불러오기 모두 원본 `SendPlayerOption(PLAYEROPTION_WAIT_END_TURN,true)` 명령으로 이 Host의 수동 턴 종료 정책을 설정하와요. SDK의 player option 목록은 `Read`에서 초기화되고 `Write`로 저장되지 않으므로 세션 정책을 다시 설정해야 한답니다. UI 준비 상태나 턴 종료 legality를 강제로 바꾸지 않고 저장 형식 V1도 유지하와요.
- `--resume-run`은 선행 실행의 request/result·저장·의미 상태·runtime 입력과 해시를 검사하고, 동일 sealed Host와 정확히 같은 engine manifest만 허용하와요. 선행 저장은 보존하며 private runtime에 복사한 `checkpoint-input.zssave`로 실행하와요. 원본 Civ V 외부 저장 컨테이너나 서로 다른 후보 사이의 마이그레이션은 이 경로의 검증 범위가 아니랍니다.
- 복원도 같은 `InteractiveGameLoop`의 선택·이동·대기·턴·저장·닫기 경로를 사용하와요. 준비 단계는 `Play.ps1`과 `Resume.ps1`을 생성하고, smoke 단계는 동일 경로에 자동 HWND 입력을 전달하와요.

## 현재 실제 증거

| 자료 | 확인한 범위 |
|---|---|
| [현재 sealed Host](../evidence/ui_window_host/20261003T104543Z_2dddaea613c2/build_result.json) | x64 PE32+ `/O2 /W4 /WX`, 원본 popup 큐·같은 세계 HWND의 생산/연구·native 저장 재개, 동결 입력·provider 해시 보존 |
| [선행 도시·생산·연구 실행](../evidence/interactive_game/20261003T114216Z_3758b8174d09/result.json) | 실제 도시 8192 건설, 생산 unit 1·연구 tech 1 원본 콜백, 0 → 1턴과 native 저장 두 건·정상 닫기 |
| [선행 실행 독립 대조](../validators/20261003T114922Z_3a8ec8ba4a98/conformance.json) | 실제 콜백 payload·게시 좌표·같은 HWND/장치의 13개 세계 JSON/GPU 장면·저장·Core unload |
| [별도 프로세스 저장 재개](../evidence/interactive_game/20261003T122307Z_4e2fe1f5c726/result.json) | 1턴 checkpoint → 별도 Host PID 48820 → 원본 생산·연구 재선택 → 2턴·native 재저장 두 건, 입력·동결 지원 도구 해시 유지 |
| [재개 pair 독립 대조](../validators/20261003T123324Z_c58a7d75eb8b/conformance.json) | 정확한 선행 최종 저장·복사본·복원 저장, 다른 Host PID·같은 city/unit/tech·생산/연구 진행, 133개 구획과 원본 reload metadata, 재개 실행의 12개 세계 JSON/GPU 장면·같은 장치 |
| [실제 화면과 표시 경계 검토](../evidence/interactive_game/20261003T122307Z_4e2fe1f5c726/ui_fidelity_review.json) | native 생산·연구·2턴 GPU 캡처 직접 검토, 활성 0×0 연구 진행계와 후보 ScrollAnim 정책·도시 이름 표시의 미검증 경계 기록 |
| [완료된 중간물 정리](../evidence/intermediate_tidy/20261003T112055Z_4c91c3d87d4f/verification.json) | 참조되지 않은 object 760개·498,503,901 논리 바이트 정리, 실행 파일·저장·동결 입력·검증 기록 보존 |
| [정리 재점검](../evidence/intermediate_tidy/20261003T121718Z_1a00ef9fcdb1/cleanup.json) | 추가 삭제 대상 0개, 참조 object 302개와 재사용 기준·캐시 보존 |

재개 직후 상태는 선행 실행의 마지막 상태와 바이트 동일하며, 도시 8192·unit 1·tech 1과 생산 queue를 유지했사와요. 다음 정상 턴에서 생산은 5 → 10, 연구 진행은 4 → 8로 증가했답니다. 독립 검증은 선행 최종 저장·private 복사본·복원 roundtrip archive의 실제 경로·해시·내용을 대조했고, 133개 구획 중 132개는 같았사와요. Game 구획은 기존 replay 8건과 앞뒤 바이트를 보존하면서 원본 reload replay 1건과 session counter 1 → 2만 추가됐답니다. replay 개수는 archive에서 읽었으며 이전 이동 전용 시험의 6 → 7이나 55바이트 차이를 이번 검증 조건에 옮기지 않았사와요.

원본 연구 버튼의 요청 target key는 26, 실제 hit-test가 소비한 겹친 자식 버튼 key는 73이었사와요. 두 키의 좌표·visible/enabled·원본 left-click payload가 동일 tech 1을 가리킴을 검사했고, 실제 SDK research tuple 한 건을 연결했답니다. 실제 전달 키가 요청 키와 같았다는 주장이나 원본 retail hit/clip 동등성 주장은 하지 않사와요.

이 과정의 [112604](../evidence/interactive_game/20261003T112604Z_c61311ad1232/result.json)·[113644](../evidence/interactive_game/20261003T113644Z_c3f5141fa5dc/result.json) 실행은 짧은 생산 목록의 ScrollBar 범위와 XYWH/LTRB 대조 오류로, [115134 재개](../evidence/interactive_game/20261003T115134Z_5b546e453222/result.json)는 복원 통과 뒤 연구 ScrollAnim의 표시 크기를 texture crop으로 잘못 해석해 실패했사와요. 각각 실패 기록과 동결 지원 도구를 보존했고, 수정한 지원 도구로 별도 실행을 수행했답니다. 같은 sealed C++ Host를 재사용했으며 실패 판정이나 SDK legality 조건을 바꾸지 않았사와요. 독립 verifier의 경로 계약 수정 과정에서 나온 실패 기록도 그대로 보존하와요.

## 남은 표시 경계

원본 TechPopup Lua는 현재 연구의 `ProgressMeter`를 활성화하고 percent setter를 호출하와요. 해당 원본 XML과 실제 snapshot은 Image/Meter를 0×0으로 기록하며, 현재 frontend는 그 상태를 보존하지만 픽셀을 그리지 않사와요. 원본 native renderer의 자연 크기·alpha 의미는 관측하지 못했으므로 연구 진행계의 표시 보존 완료로 계산하지 않사와요. `ScrollAnim`의 nearest stretch·mask 샘플링도 명시한 후보 정책이며 원본 retail 동등성은 미검증이랍니다.

실제 GPU 캡처에서는 원본 생산·연구 창과 세계 배경·HUD, 재개 뒤 2턴 표시를 확인했사와요. 세계 도시 이름에는 `TXT_KEY_CITY_NAME_WASHINGTON`이 그대로 표시돼 있어 N04의 현지화 결함이 남아 있답니다. 캡처는 숨긴 시험 창의 back buffer이며 사람이 보이는 창을 조작한 증거는 아니랍니다. 원본 3D·카메라·음향·필수 전체 UI와 원본 게임 비교도 계속 남아 있사와요.

## 이동·저장 재개 초기 경로의 증거

| 자료 | 확인한 범위 |
|---|---|
| [현재 sealed Host](../evidence/ui_window_host/20261003T093835Z_79b4e0bf86a7/build_result.json) | x64 PE32+ `/O2 /W4 /WX`, 네 C++ 번역 단위와 동결 입력·provider 해시 보존 |
| [선행 새 게임 실행](../evidence/interactive_game/20261003T094459Z_47ea18946632/result.json) | 실제 이동·대기·0 → 1턴·native 저장·정상 닫기, 복원 입력 생성 |
| [새 프로세스 복원 실행](../evidence/interactive_game/20261003T094646Z_afbcea477060/result.json) | 1턴 checkpoint 보존·복원, unit 16385의 (12,14) → (11,13), 합법 대기·1 → 2턴·7 SDK updates, native 재저장 두 건과 정상 Core unload |
| [독립 대조](../evidence/interactive_game/validators/20261003T095244Z_e5f5c6a94647/conformance.json) | 정확한 선행 checkpoint·같은 bundle·별도 PID·의미 상태·native 구획·실제 입력·턴·재저장, 자동 입력 8건·10개 JSON/GPU 장면·같은 장치 연결 |
| [첫 후보 중간물 정리](../evidence/build_tidy/20261003T093721Z_50ecb48bfffd/cleanup.json) | 참조되지 않은 object 4개, 11,164,952바이트 정리; 보존 입력 해시 유지 |
| [현재 후보 중간물 정리](../evidence/build_tidy/20261003T094929Z_6b36e773fe5d/cleanup.json) | 참조되지 않은 object 4개, 11,165,190바이트 정리; EXE·보고서·동결 입력·실행·저장·캡처 보존 |

독립 대조는 복원 전후 133개 native 구획 중 132개가 바이트 동일함을 확인했사와요. 나머지 Game 구획의 55바이트 증가는 원본 SDK의 `TXT_KEY_MISC_RELOAD` replay 한 건과 session counter 1 → 2로 엄격히 제한했답니다. 기존 replay 6건, RNG를 포함한 앞부분과 session counter 뒤 전체 나머지는 바이트 동일하와요. 이 판정은 동결한 한국어 turn-one 시험 자료에 관한 증거이며 임의 저장의 호환성이나 전체 게임 상태의 일반 보존 증명으로 확대하지 않사와요.

첫 복원 후보의 [093014 실행](../evidence/interactive_game/20261003T093014Z_2733c88e5332/result.json)은 FAILED로 보존돼 있사와요. 저장과 이동은 복원됐지만 저장되지 않는 수동 턴 종료 옵션을 복원 세션에 설정하지 않아 SDK가 정상 턴 종료를 거부했답니다. 원본 option 명령을 새 게임·불러오기 공통 세션 정책으로 적용한 별도 093835 Host와 새 실행 쌍으로 수정 결과를 검증했사와요. 실패 판정을 덮어쓰거나 UI·SDK의 턴 종료 조건을 약화하지 않았답니다. 독립 verifier의 자료 계약 수정 중 나온 세 실패 기록도 보존하와요.

실제 GPU 초기 복원·다음 턴 캡처를 직접 검토해 한국어 HUD·버튼 배치와 이동 후 시야 갱신을 확인했사와요. Present는 숨긴 시험 창의 occluded 상태였으므로 실제 사람이 보이는 창을 조작한 증거는 아니랍니다.

## 앞선 구현의 증거

| 자료 | 확인한 범위 |
|---|---|
| [sealed Host](../evidence/ui_window_host/20261003T084859Z_51717210a5e6/build_result.json) | x64 PE32+ `/O2 /W4 /WX`, 네 C++ 번역 단위와 동결 입력·provider 해시 보존 |
| [한국어 실제 실행](../evidence/interactive_game/20261003T085630Z_e8f305dee65a/result.json) | 같은 창에서 posted input 6건, 실제 SDK 이동·턴·저장·WM_CLOSE와 Core unload |
| [독립 대조](../evidence/interactive_game/validators/20261003T090011Z_82a384e4f23a/conformance.json) | unit 16385의 (12,15) → (12,14), 이동력 감소·실제 move mission, 0 → 1턴·7 SDK updates, 장면별 hit와 세대 연결, 8개 JSON/GPU 장면·같은 장치, 두 native archive의 133개 구획과 40×24 지도 |
| [기존 도시 명령 회귀](../evidence/city_decisions/20261003T085827Z_36c343c49e78/result.json) | 같은 새 Host의 기본 founding·생산/연구·정상 턴·새 세션 native 복원 통과 |
| [중간물 정리](../evidence/build_tidy/20261003T085941Z_c03e69ae68f5/cleanup.json) | 참조되지 않은 최종 object 4개, 11,145,239바이트 정리; EXE·보고서·동결 입력·실행·저장·캡처 보존 |

같은 실행의 첫 판정은 [085418 run](../evidence/interactive_game/20261003T085418Z_24414e14f7c2/result.json)에 FAILED로 보존돼 있사와요. 실행 자체는 exit 0으로 위 순서를 마쳤으나 Python 집계기가 CRLF 줄끝을 인식하지 못했답니다. 줄끝 정규화를 고친 runner로 별도 085630 실행을 수행했으며 C++ 후보를 바꾸거나 판정 조건을 약화하지 않았사와요. 앞선 두 컴파일 실패와 두 독립 verifier의 자료 계약 수정 기록도 보존했답니다.

## 실행과 남은 필수 구현

`python tools/run_interactive_game.py --host-build evidence/ui_window_host/20261003T104543Z_2dddaea613c2/build_result.json --language ko_KR`는 실행하지 않고 별도 runtime과 launcher를 준비하와요. `Play.ps1`은 `--play ko_KR`로 새 게임을 시작하며 종료 시 private native checkpoint를 남기와요. `Resume.ps1`은 `--play-load`로 같은 bundle의 checkpoint를 선택해 이어 가와요.

선행 실행의 마지막 정상 저장을 복사해 준비하려면 같은 명령에 `--resume-run 20261003T114216Z_3758b8174d09`를 추가하와요. 일반 자동 이동·턴 시험은 `--smoke`, 도시·생산·연구 선택 경로는 `--smoke --decisions`로 실행하와요. 현재 재개 pair의 독립 대조 명령은 `python tools/verify_interactive_decisions.py --run 20261003T122307Z_4e2fe1f5c726 --source-run 20261003T114216Z_3758b8174d09`랍니다.

검증 때 준비한 `Build/InteractiveGameRuntime/20261003T122307Z_4e2fe1f5c726/Resume.ps1`은 기본으로 해당 runtime의 복사된 1턴 checkpoint를 열며, 경로 인수로 다른 호환 private checkpoint를 지정할 수 있사와요. launcher의 PowerShell 구문은 검사했지만 보이는 창에서 사람의 조작 시험은 아직 수행하지 않았답니다.

일반 생산·연구 선택 창과 세계 창의 연결·동일 bundle 저장 재개는 위 고정 시험에서 통과했사와요. 전체 도시·전투·외교 화면, 연구 트리와 선택 UI의 나머지 기능·표시 동등성, 원본 지형·유닛 그림·음향·카메라·시야 기억·사람 입력, 폭넓은 저장 재개·외부 저장·선택 모드·전체 규칙·성능·장기 회귀와 최종 배포는 [기존 완료 기준](ENGINE_COMPLETION_STATUS.md)에 계속 남아 있사와요. 이 고정 입력의 저장 재개를 한 판 전체나 전체 엔진의 완료로 환산하지 않사와요.
