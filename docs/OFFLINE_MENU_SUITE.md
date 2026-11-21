# 게임 내 메뉴 — 오프라인 구현·준비 기록

> 현재 상태(2026-11-01): Host `20261101T074006Z_c2fd2fe9be38`와 SDK `430f3122`의 새 격리 묶음 `20261101T080450Z_424fb64608b2`을 파일 검사로 준비했다. 게임·SDK·창·GPU 실행과 화면 확인은 보류하며, 기본 실행본은 유지한다.

5개 번역 단위의 컴파일·링크, 현재 소스 입력 636개와 컴파일 의존 파일 559개, UI payload 74개와 레이아웃 30개를 대조했다. 이는 소스·부품·파일 준비의 증거이며 실게임 수락을 뜻하지 않는다.

| 항목 | 이번에 연결한 범위 | 남은 범위 |
|---|---|---|
| 격리 실행 묶음 | 최신 Host와 선택 SDK의 정확한 파일·소스 조합, 별도 준비본 | 실제 실행·화면·입력 확인 |
| 옵션 | 창 크기·전체 화면·수직동기화·UI 효과음·기본 도움말의 적용, 값 확인, 취소·실패 복원, 별도 설정 저장 | 원본 OptionsManager 133개 API 전체, 그래픽 품질·음악 등 미지원 설정, 주 메뉴 옵션 화면 |
| 주 메뉴 복귀 | 원본 확인 콜백 종료 후 이전 게임·창·코어 정리, 별도 주 메뉴, 현재 설정으로 새 게임·종료 | 원본 주 메뉴 외형과 전체 설정·불러오기·다중 사용자 분기 |
| 현재 설정으로 재시작 | 현재 사전 설정 스트림과 별도 DLC·슬롯 패키지·이동 설정 캡처, 새 코어 재적용 | 실제 SDK 시작, 지형·문명·초기 난수 시드 일치 확인 |
| 은퇴 | 원본 은퇴 명령, SDK 재생 데이터 저장, 실제 최종 점수·역사적 순위·결과 화면 연결 | 전체 재생 화면·통계 화면·온라인 순위표, 실제 은퇴 실행 |
| 지도 저장 | 원본 SaveMapMenu, `.Civ5Map` 저장·목록·관측한 파일의 덮어쓰기·삭제, 잘못된 이름 거절 | 실제 SDK 출력과 게임 재읽기. 지도는 캠페인 저장을 대체하지 않음 |
| 터치 도움말 | 원본 Lua/XML 표시·닫기·체크박스와 별도 설정 저장 | 실제 터치 장치 입력·화면 확인 |

원본 설치·MODS·사용자 저장·기존 저장 스키마·밸런스·Mod ID는 변경하지 않았다. 표시 설정은 준비본의 `menu-options.zssettings`에, 지도·은퇴 출력은 격리 세션 안에 저장한다. 원본 INI와 기존 정책 표시 설정을 변경하지 않는다. 원본 옵션 소스 바이트를 보존하되 미구현 API가 성공했다고 처리하지 않으며, 터치 도움말의 원본 장치 조건도 유지한다.

## 검증 근거

- `evidence/ui_window_host/20261101T074006Z_c2fd2fe9be38/build_result.json`: 최신 5개 번역 단위 컴파일·링크, 정확한 입력과 실행 파일.
- `evidence/game_menu/offline_menu_suite/pair_preparation/20261101T074006Z_c2fd2fe9be38/final_audit.json`: 독립 파일 검사와 중간 산출물 정리. 이 감사는 발행 과정에서 수정하지 않는다.
- `evidence/game_menu/offline_menu_suite/options_touch/offline_suite_tests.json`: 공유 Lua와 부품 환경의 옵션·도움말·지도·기존 저장 흐름 검사.
- `evidence/game_menu/offline_menu_suite/options_touch/embedding_cross_tests.json`: 생성 장면·글꼴 메타데이터·원본 소스 결합 대조.
- `evidence/game_menu/offline_menu_suite/map_catalog/cpp_tests.json`: SDK 없는 본 지도 제공 코드의 실제 파일 보호 검사 67개. 하드링크 생성 검사는 권한 오류 5로 미실행.
- `evidence/game_menu/offline_menu_suite/map_catalog/long_path/final.json`: 세션 경로 180자·지도 이름 100자·전체 경로 294자의 저장·목록·덮어쓰기·삭제 확인.
- `evidence/game_menu/offline_menu_suite/frontend_lifecycle/`: 현재 설정 캡처·전환·은퇴 연결과 독립 소스 검토. 실제 게임 명령 실행 증거가 아님.

검사 과정에서 컴파일러·SDK 없는 작은 파일/설정 검사 프로그램·공유 Lua 제공자는 사용했다. Host·게임 SDK·CLR·HWND·GPU는 실행하지 않았다. 원본 픽셀 일치, 실제 플레이·캠페인 저장·모드 호환과 멀티코어 성능은 미검증이다.

## 완료 기록

- 준비 요청: `evidence/interactive_game/20261101T080450Z_424fb64608b2/request.json`
- 준비 결과: `evidence/game_menu/offline_menu_suite/pair_preparation/materialization_retry03_adoption_retry02/result.json`
- 준비 감사: `evidence/game_menu/offline_menu_suite/pair_preparation/materialization_retry03_adoption_retry02/final_prepared_pair_audit.json`
- Host: 7,130,624바이트, SHA-256 `26b2a97071c91a37a6a70ef05acc1c2026cda2fc06f6ce28d4d3268a9558823a`
- SDK SHA-256: `430f3122d0b555d6daae14aa7c011ef43ce8f978270477c8af596ca4b0493ab9`
- 새 세션·저장·실행 결과 없음, native acceptance 0, 기본 실행본 승격 없음, 전체 엔진 목표 미완료.

이 준비본은 파일 생성 뒤 최종 감사의 경로 범위 검사에서 중단된 묶음을, 파일 복사나 요청 재작성 없이 별도 감사로 다시 확인해 채택한 것이다. 원래 생성 도구·실패 기록과 이후 채택 감사는 구분해 보존했다.

