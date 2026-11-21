# 원본 자산을 사용하는 3D 지형 후보

> 2026-11-08: 원본 타일 혼합과 전장의 안개를 재현하는 계획과 정적 근거는 [WORLD_TERRAIN_ORIGINAL_PLAN.md](WORLD_TERRAIN_ORIGINAL_PLAN.md)에 있다. 이 문서의 지형은 여전히 타일마다 단일 재질을 쓰는 후보다.

2026-10-09 [최신 정리 결과](../evidence/storage_cleanup/20261009_trade_route_pair_cleanup/summary.json)의 NTFS 고유 파일 점유량은 **25.63→8.80GiB**, 누적 **16.83GiB·65.66% 감소**랍니다. 직전 9.06GiB 측정 이후 만든 별도 프로세스 복원 검증 자료까지 포함했사와요. 구형 Host와 교역로 실행 두 묶음의 Build/evidence 여섯 폴더·11,555개 파일을 삭제하고, 새 복원 DB/DDS 416개는 내용 변경 없이 압축했답니다. 삭제 전후 보호 파일 80,355개의 SHA가 같으며 사용자 저장 8개·실행 경로 10건도 재확인했사와요. 경로별 파일 크기 합계는 21.33GiB이고, 여기 보고한 점유량은 하드링크 중복과 NTFS 압축을 반영한 파일 데이터 크기랍니다.

2026-10-09 [추가 용량 정리](../evidence/storage/20261008T164816Z_2268d33ad2b9_cold/final_summary.json) 직후 NTFS 고유 파일 점유량은 **13.10→8.34GiB**랍니다. 앞선 대량 정리 전 **25.63GiB 대비 총 17.29GiB·67.46% 감소**했사와요. 이번에는 cold Build/evidence 7,507개를 검토하여 7,500개를 내용 변경 없이 압축하고 절감 없는 7개는 원복했답니다. 보호 파일 4,606개 해시와 사용자 저장 8개·실행 연결 10건을 재확인했사와요. 현재 실행본·사용자 저장 의존 버전·재사용 빌드 캐시는 제외했으며, 아래 용량은 각 당시 기록이랍니다.

교역로 [Host 224629](../evidence/ui_window_host/20261008T224629Z_ee41544939ef/build_result.json)의 [새 게임 225105](../evidence/interactive_game/20261008T225105Z_a09bb643b908/trade_route_validation.json)와 [별도 프로세스 복원 233650](../evidence/interactive_game/20261008T233650Z_5cfa5136b39e/trade_route_validation.json)이 모두 **독립 검사 PASS**랍니다. 원본 1턴 저장과 복사본·복원 초기 SDK 상태가 일치하고, 세 탭·금 수익 정렬·닫기/재열기/Escape의 실제 입력 9건 뒤 2턴 진행·저장 2회·정상 종료를 확인했사와요. 저장 133개 구역 중 132개는 같고 Game 구역만 달랐으며, 그 내부 변화의 reload metadata·난수 동등성은 별도 미검증으로 남겼답니다. 휠은 내용이 넘치지 않는 상태에서의 입력 소비만 검증했으며 사람의 플레이·원본 전체 화면의 증거는 아니랍니다. 수동 기본 실행본과 전체 추정 약 30%는 유지하와요. 아래 실패 기록은 수정 전 이력이랍니다.

2026-10-09 [최신 정리](../evidence/storage_cleanup/20261008T141026Z_retirement_plan/final_summary.json)로 NTFS 고유 파일 점유량을 **25.63→12.57GiB**, 13.06GiB·50.97% 줄였사와요. 구형 빌드·실패/대체 시험 50개 폴더·43,436개 파일을 삭제하고, 완료된 시험 DB/DDS 1,568개를 내용 변경 없이 압축했답니다. 삭제 전후 보호 파일 40,825개와 압축 대상의 전후 해시, 사용자 저장 8개·실행 경로 10건을 확인했사와요. 현재 실행에 필요한 원본 자산·최신 검증·CPU 추적·사용자 저장은 보존했으며, 아래 용량과 구형 raw 링크는 당시 기록으로 읽으시와요.

최신 교역로 후보의 세계 표시·SDK 실행은 1턴까지 진행했으나 원본 교역창의 문명 아이콘 sprite 대조에서 실패했사와요. 원본 snapshot과 준비 로그를 보존했으며 [현재 실패 경계](CONTINUOUS_PLAY.md)를 먼저 해결해야 하와요. 이 실행으로 교역창 GPU 표시나 원본 전체 UI·세계 화면을 통과했다고 계산하지 않사와요.

2026-10-08 상단창 통합 검증 뒤 [정리 결과](../evidence/storage_cleanup/20261007T203350Z_manual_retirement_draft/summary.json)로 대체된 수동 실행본·Host·실패 시험의 Build/evidence **16개 폴더, 6,221개 파일·논리 2.36GiB**를 제거했사와요. [정리 전](../evidence/storage/20261007T210827Z.json)과 [정리 후](../evidence/storage/20261007T212931Z.json)의 NTFS 고유 파일 점유량은 **19.24→17.44GiB, 1.81GiB 감소**했답니다. 삭제 전후 보호 경로 54,726개의 해시가 같았으며, [삭제 후 경로 검사](../evidence/storage_cleanup/20261007T203350Z_manual_retirement_draft/post_cleanup_validation.json)에서 사용자 저장 8개와 New·Continue·저장별 Load 10건을 확인했사와요. 실패 자동시험의 저장 3개도 경로·크기·SHA가 고정된 폐기 목록에 포함했으며 사용자 저장과 겹치지 않사와요. 최신 상단창 새 게임·복원, 현재 수동 실행본과 필요한 선전포고·CPU 검증 자료는 보존했답니다. 아래의 14.80GiB 등 이전 수치는 해당 당시 기록이랍니다.

2026-10-05, 기존 F01·N04의 세계 표시·입력 경로를 진행했사와요. 원본 DDS를 사용하는 D3D11 지형 mesh·원근 카메라·깊이 검사·픽셀별 타일 선택을 같은 게임 창에 연결했답니다. **원본 전체 renderer나 원래 문명 5와 같은 화면의 완료는 아니랍니다.**

## 현재 증거

2026-10-08 [TopPanel 시험 후보](CONTINUOUS_PLAY.md)는 원본 상단 정보를 월드와 같은 HWND·D3D11 장치에 합성하고, 과학 표시에서 기술 트리로 갔다가 동일 SDK 상태로 복귀했사와요. 새 게임 37개·별도 프로세스 복원 39개 프레임과 턴 진행·재저장을 통과했답니다. 원본 전체 세계 화면이나 전체 상단 버튼의 완성이 아니며, 7개 미연결 클릭과 툴팁·표시 정밀도 항목 때문에 상단창은 시험 옵션으로 유지하와요. 수동 기본 실행본은 아래의 선전포고 검증 버전이랍니다.

2026-10-08 최신 선전포고·저장 복원 시험 뒤 [추가 정리](../evidence/storage_cleanup/20261007T193212Z_c1a07d6e4b39/summary.json)로 6개 Build/evidence 폴더·8,463개 파일·논리 2.63GiB를 제거했사와요. 고유 파일 점유량은 16.79→14.80GiB로 1.99GiB 감소했고, 보호 경로 43,558개·사용자 저장 8개·실행 경로 10건을 확인했답니다. [같은 날 앞선 12.44GiB](../evidence/storage_cleanup/20261007T185251Z_9a72c5df1e41/summary.json)와 [10월 7일의 11.09GiB](../evidence/storage_cleanup/20261007T124510Z_e6f679eb7803/summary.json)는 이후 시험 자료를 만들기 전의 기록이랍니다.

2026-10-06 현재 Host `20261006T132536Z_f8bcf55e3ffa`는 원본 UnitPanel과 **좌측 선택·우측 이동/공격·Shift 예약·같은 타일 취소**를 3D 픽셀 선택에 연결했사와요. [새 게임·복원·전투 및 독립 대조](CONTINUOUS_PLAY.md)는 각각 37·39·39개 committed 프레임과 실제 SDK 상태를 확인하와요. 클릭은 release 시점의 좌표와 장면 세대를 사용하며, UI/지도 사이 드래그와 focus/capture 상실은 이전 press를 취소하와요. 원본 전체 renderer·그룹 선택·모든 모드와 한 판의 사람 플레이는 미완료랍니다. 현재 수동 새 게임 기본값은 선전포고 수정이 포함된 `20261007T202612Z_d895c0fe84ab`이며 기존 저장은 맞는 보관 버전으로 연결하와요.

이전 기본 Host `20261005T124208Z_65c9f8ce7280`에서 원본 Warrior IdleA의 **native x64 곡선 샘플 → CPU 뼈/가중치 변환 → 실제 GPU 정점 갱신 → 같은 창의 표시 시간 루프**를 통과했사와요. [새 게임](../evidence/interactive_game/20261005T124511Z_ad7083cc8304/result.json)과 [별도 프로세스 복원](../evidence/interactive_game/20261005T125355Z_d882b8fab075/result.json)은 도시 조작·금 구매·연구 트리·1→2턴·재저장까지 확인했답니다. 당시 수동 기본 실행본은 `20261005T125723Z_ac109f515719`로 연결했고, [현재 실행·독립 검사·캡처 표](CONTINUOUS_PLAY.md)에 증거를 연결했사와요. 이동·전투 clip, 다른 유닛, 원본 전체 renderer와 한 판의 사람 플레이는 미완료랍니다.

[ZSUNIT02 v2 패키지](../Build/UnitAssets/480678966a78bedbee642040285010aa86f8a2cc34b0929c2774dcee8ab54266/unit-assets.manifest.json)는 1,276,167바이트이며, 기존 정적 기하 뒤에 원본 GSD·GR2 다섯 파일, 3개 rig의 23개 뼈·부모·역 bind 행렬, 정점과 네 가중치를 보존하와요. 기존 ZSUNIT01 v1 판독도 유지하며 원본 파일은 private bundle에 풀어 해시로 고정하와요. 프레임별 전체 메시를 미리 복제한 자산 묶음을 만들지 않았답니다. 저장 스키마·규칙·모드 ID는 그대로이며 이전 저장은 해당 실행 버전으로 연결하와요.

[원본 public sampler](../evidence/granny_animation/20261005T105701Z/report.json)와 [native C ABI](../evidence/granny_animation_bridge/20261005T113900Z/report.json)를 사용한 [CPU skinning 검사](../evidence/unit_animation/20261005T124200Z/report.json)는 t=0을 v1 정적 정점과 대조하고, 중간 시점 변화·clip 반복·잘못된 시간의 원자적 거부·다른 스레드·부모 순환을 검사했사와요. palette는 rig의 뼈마다 한 번 계산해 각 정점의 가중치에 적용하와요. private SDK assembly와 CLR 4 설정을 사용하며 x86 실행 도우미를 게임 런타임에 넣지 않았답니다.

[새 게임 애니메이션 대조](../validators/20261005T125315Z_a906278c8d90/animation.json)와 [복원 대조](../validators/20261005T125729Z_cf1ba850d111/animation.json)는 world/UI 각각 실제 단조 시계의 세 표본을 비교했사와요. 전사 영역의 픽셀이 바뀌되 입력 세대·턴과 갱신 전후 관측 SDK 상태는 동일했답니다. 재표시는 GameCore/Lua를 호출하지 않고 보존한 world와 UI overlay를 사용하와요. [창 부품 검사](../evidence/bitmap_window/20261005T123839Z_6694ccd3719b/conformance.json)는 O2/Od 각각 164개 검사·8개 COM 창 수명 균형과 대기 키/클릭/스크롤의 보존을 확인했사와요. 화면 크기·hit·scroll·pixel 선택 표가 달라지면 refresh를 거부하며 기존 화면과 준비된 후보를 보존하와요.

[최신 지형·전체 화면 검사](../Build/terrain_renderer_validation/20261005T125302Z/manifest.json)는 `/O2 /W4 /WX /fp:strict`에서 원본 전사의 0.5초·1초·반복 시점과 GPU 픽셀 변화, 지형 ID·hit·projection 보존을 검사했사와요. 지형과 유닛의 같은 장치/CPU 경로 색상은 정확히 대조하며, 전체 HUD의 CPU WIC/GPU Direct2D 가장자리만 별도 한계로 비교하와요. alpha는 정확히 일치하고 일반 RGB 채널 편차는 16 이하, 일치하는 유닛 마커의 타원 테두리에서만 64 이하랍니다. 차이 픽셀은 0.1% 이하·평균 RGB 채널 편차는 0.01 이하이며, 이는 선택한 fixture의 한계로 원본 게임의 시각 동등성을 뜻하지 않사와요.

수동 경로는 지형·HUD·도시 backdrop·팝업을 같은 D3D11 장치에서 합성하며 PNG 왕복을 제거했사와요. 타일 ID 표의 CPU 읽기와 자동 시험의 명시적 PNG는 유지하와요. 표시 루프의 33ms 최소 간격을 실제 30FPS나 전체 성능 개선의 증거로 해석하지 않사와요. 종료 시 표시 자원을 Host의 DLL 고정보다 먼저 해제하와요.

[이번 정리 기록](../evidence/storage_cleanup_components/20261005T131139Z_cec8c068b454/summary.json)에 따라 구형 통합·실패·부품 시험을 정리했사와요. v1 loader의 역사적 입력은 [6,538바이트 헤더](../Build/UnitAssets/b36aa9c2b78af7e597357275abaf9763abd7c252f6eb721d49921cf2a06f4b94/WorldUnitAssets.v1.h)로 분리해 원래 SHA를 대조했으며, [정리 목록](../evidence/storage_cleanup/20261005T130800Z_6219606ef78e/plan.json)에 이전 경로와 보존 경로를 기록했답니다. 기존 sealed manifest는 다시 쓰지 않았으며 과거 경로는 이 명시적 이전 기록으로 추적하와요.

## 초기 표시 검증 이력

2026-10-05 08시대 후보 Host는 `20261005T080027Z_8f0303f56bac`였으며, 원본 전사 모델 패키지와 도시 화면을 같은 3D 지형의 카메라·좌표에 연결했사와요. 아래 이력의 대체된 실행 원본은 정리 대상이며 현재 재실행 근거는 위 최신 자료에 한정하와요.

[표시/입력 좌표 대조](../evidence/interactive_game/20261005T080258Z_60bdb6a3449c/city_terrain_projection_review.json)는 실제 도시 snapshot 17개를 같은 지형 프레임과 대조했사와요. [복원 뒤 좌표 대조](../evidence/interactive_game/20261005T080546Z_3e57c443e4c6/city_terrain_projection_review.json)는 표시한 snapshot 19개를 통과했고, 실제 표시되지 않은 취소 snapshot 1개는 별도 기록했답니다. [실제 GPU 화면](../Build/InteractiveGameRuntime/20261005T080258Z_60bdb6a3449c/sessions/c4c5d52951f35b448c296a64a590e9d8/play-scene-1-gpu.png)에서 지형 위 전사 12명의 대기 자세를 확인했사와요.

보관 안내: 2026-10-05 사용자 지시로 대체된 실행·빌드·시험 사본을 정리했사와요. 아래 개발 이력의 일부 과거 raw 링크는 더 이상 존재하지 않으며, 현재 보관하는 통합 자료는 위 최신 source/restore와 [연속 실행 문서의 표](CONTINUOUS_PLAY.md)에 한정해 확인하와요. 원본 CPU 추적·현재 provider·필요한 부품 기준·사용자 저장은 별도 보존했답니다.

[지형 경계 GPU 회귀](../Build/terrain_renderer_validation/20261005T055218Z/manifest.json)는 깊이 검사를 이긴 타일 ID의 4방향 경계와 모든 highlight span을 독립 대조했사와요. span 순서·범위·누락·숨겨진 타일, 산 위 anchor의 실제 픽셀 ID, WorldView 전달 일치도 통과했답니다. [표시 변환 시험](../Tests/city_view_terrain_projection.py)은 잘못된 schema/span 거부, BGRA·DDS와 기존 2D 경로를 검증하와요.

| 자료 | 확인 범위 |
|---|---|
| [원본 자산 표](../Build/TerrainAssets/2bee85c22c77b0342896f827989ca7d6f4ca3ae8f4dfe3a2179faaab4d689b13/terrain-assets.manifest.json) | 원본 TerrainDef.csv의 대륙·재질 ID별 diffuse 35행과 높이 DDS 5종, 원본 bytes와 전체 mip 보존, 입력 CSV·FPK·높이 파일 전후 SHA 동일 |
| [3D GPU 부품 검증](../Build/terrain_renderer_validation/20261005T053047Z/manifest.json) · [9×9 시험 화면](../Build/terrain_renderer_validation/20261005T053047Z/captures/world_terrain_fixture.png) | 하드웨어 D3D11, 17,646 triangles·81 타일 키; draw 순서 역전에도 색·선택 결과 동일, 원본 산 높이 제거 시 색·픽셀 ID 변화, 안개 비공개·지도 밖 선택 차단, 산봉우리 anchor 보정 |
| [창 입력 검증](../evidence/bitmap_window/20261005T051951Z_520cb7f524d3/conformance.json) | O2/Od 각각 기존 87개·새 pixel 17개 검사, UI 우선 선택·잘못된 표 거부·PNG 읽기 실패 후 기존 장면 보존·세대 교체 |
| [최신 x64 Host](../evidence/ui_window_host/20261005T080027Z_8f0303f56bac/build_result.json) | PE32+ x64, 경고를 오류로 처리한 빌드 통과; EXE SHA `f5ded53cf71de06565bcc43224607e7f949987993e677291c69c4ba72dc123f4` |
| [실제 SDK 이동·턴·저장](../evidence/interactive_game/20261005T053342Z_825f30da4786/result.json) · [독립 대조](../evidence/interactive_game/validators/20261005T053621Z_7e3e53fe3d40/conformance.json) | 실제 전사 16385의 타일 (12,14) 이동, 정상 1턴·native 저장·종료, 실제 게시 좌표의 `.pick` ID와 창 입력·SDK 상태 대조; 8개 프레임의 D3D11 지형 사용 |
| [실제 세계 창 캡처](../Build/InteractiveGameRuntime/20261005T053342Z_825f30da4786/sessions/2a057a753be58251715367a19594c4c8/play-scene-2-gpu.png) | 공개된 원본 재질 지형과 현재 임시 유닛 표식을 같은 창에서 표시; 사람이 한 판 플레이한 증거는 아니랍니다 |

[픽셀 증거 검증기 시험](../Tests/terrain_pick_packet.py)은 경계 좌표·잘못된 길이/인덱스·미공개 타일 14개 사례를 통과했사와요. 독립 이동 검증기의 오래된 PID 비교는 실제 Host와 실행 도우미를 각각 대조하도록 고쳤고, 타일/유닛 키 도메인도 현재 컴파일 계약의 32비트 위치로 맞췄답니다. 실패 보고서도 보존하와요.

## 구현 경계

- [WorldViewState.h](../Source/Host/WorldViewState.h)는 GameCore 소유 스레드·잠금 안에서 공개된 plot의 아트 대륙 번호를 복사하와요. 미탐험 지형의 재질·높이 속성을 renderer에 넘기지 않으며, 기존 규칙·명령·저장 형식은 바꾸지 않았답니다.
- [WorldTerrainRenderer.cpp](../Source/Presentation/WorldTerrainRenderer.cpp)는 원본 BC3 DDS의 mip를 GPU에 올리고, 같은 mesh·카메라·depth로 색상과 R32_UINT 타일 표를 함께 생성하와요. 원본 높이 DDS는 A16B16G16R16이며 부동소수점 half 데이터로 해석하지 않았답니다. RGB의 일치를 검사하고 R 채널을 표본으로 사용하며, 별도 의미가 확인되지 않은 alpha는 높이로 섞지 않사와요.
- [WorldViewRenderer.cpp](../Source/Presentation/WorldViewRenderer.cpp)는 그 결과에 현재 HUD·유닛·도시 표식을 합성하와요. popup 장면은 자체 입력 표로 교체되므로 뒤의 월드 픽셀 선택이 닫힌 UI를 통과하지 않사와요.
- 도시 화면은 같은 frame generation의 중심점과 타일 ID 경계 span을 detached projection으로 전달하와요. [UiCityView.lua](../Source/Presentation/UiCityView.lua)는 원본 `FLuaVector` 재include와 `VecAdd` 뒤에도 grid identity·offset을 보존하고, [UiScene.lua](../Source/Host/UiScene.lua)는 snapshot의 tree·native hit를 만들기 전에 재투영·재배치하와요. 보이지 않는 anchor는 화면 밖에 두며 이전 2D 좌표를 대신 표시하지 않사와요. 도시 타일 명령은 원본 작업/구매 버튼으로만 받으며, popup 뒤의 일반 유닛 이동용 world pixel 입력은 계속 차단하와요.
- [BitmapWindow.cpp](../Source/Presentation/BitmapWindow.cpp)는 UI 사각 영역을 먼저 검사하고, 나머지 위치에서 실제 픽셀의 타일 키를 읽사와요. 화면·사각 hit·pixel hit·장면 세대를 함께 교체하며, 실패하면 이전 장면을 유지하와요.
- 자동 시험에서는 1920×1080 픽셀 표를 RLE `.pick`으로 보관하여 불필요한 큰 JSON 배열을 만들지 않사와요. 저장 게임의 스키마가 아닌 시험용 그림/입력 증거 형식이랍니다.

원본 자산 패키지는 34,675,072바이트이고 SHA `2bee85c22c77b0342896f827989ca7d6f4ca3ae8f4dfe3a2179faaab4d689b13`로 주소를 정해 재사용하와요. 실행 준비는 기존 immutable runtime cache를 통해 같은 payload를 재사용하며, Host bundle manifest가 파일을 검증·고정하와요. 원본 설치본·Stage·MODS와 이전 보관 실행본·저장은 변경하지 않았답니다.

[정리 결과](../evidence/build_tidy/20261005T060038Z_3588cae60e1a/cleanup.json)는 미리보기 후 미참조 빌드 오브젝트 20개·72,386,206 논리 바이트를 제거하고 보호 자료의 해시 보존을 확인했사와요. [검증용 DDS 압축](../evidence/build_tidy/20261005T060956Z_2f91adae05fa/raster_storage.json)은 완료된 두 실행의 파생 raster 37개를 NTFS 투명 압축하여 파일별 저장량 합계를 305,533,568바이트 줄였답니다. 파일 경로·논리 내용·SHA는 모두 보존했으며, 볼륨 전체의 여유 공간 증가량을 측정한 값은 아니랍니다.

## 원본 유닛 모델 연결 이력

유닛의 원본 art tag, 문화/시대 variation, 문명 art style, 소유자 시대, 방향, 승선 여부를 GameCore 소유 스레드에서 복사하고 표시 DTO까지 보존했사와요. 실제 SDK의 전사와 개척자 snapshot에서 해당 정보가 기록되며, 저장 형식이나 게임 규칙은 바꾸지 않았답니다. 새 [Host 빌드](../evidence/ui_window_host/20261005T064152Z_4041f78f067f/build_result.json)는 PE32+ x64·경고 오류 처리로 통과했고, [이동·턴·저장 실행](../evidence/interactive_game/20261005T064438Z_dca2b9aa4085/result.json) 및 [독립 대조](../evidence/interactive_game/validators/20261005T064615Z_7cfcb3e75366/conformance.json)도 통과했사와요. EXE SHA는 `2b62a6ef4eeae3475175572e64421e7911ece973a1609e6f2f875413c843649b`랍니다.

`WorldUnitAssets.h`의 크기가 제한된 `ZSUNIT01` 패키지 판독기와 같은 D3D11 카메라·depth를 사용하는 유닛 색상 pass를 작성했사와요. 지형 타일 ID와 CityView 좌표는 유지하며, 현재 유닛 표식의 입력을 그대로 사용하와요. 승선·문화/시대 변형·알 수 없는 art tag는 기본 전사 모델로 대체하지 않사와요. **원본 전사 패키지의 x64 부품 표시와 위 실제 SDK 게임의 이동·저장 복원까지 통과**했답니다. [이전 지형 부품 시험](../Build/terrain_renderer_validation/20261005T064149Z/manifest.json)은 유닛 패키지가 없는 범위이고, 그 실행 파일의 소스·동결 사본·EXE 해시를 대조한 뒤 새 부품 검증에 재사용했사와요. 수동 실행 기본 버전은 앞서 도시 조작·저장 복원까지 검증한 버전을 유지하와요.

원본 전사 art의 V2×3/기본×6/V4×3과 각각의 FXSXML·GR2·idle 참조를 `Resource/Common/UnitModels.fpk`에서 좁게 추출했사와요. [준비 보고서](../evidence/unit_models/20261005T070200Z_r2.json)는 `FAILED_PARTIAL`이며 원본 XML/FPK·도구·SDK의 전후 해시는 동일하와요. 기존 다른 프로젝트의 x86 준비 도구는 원본 모델 검사에서 `position=null`, 재질/대기 자세 조회에서 접근 위반으로 실패했답니다. 이후 준비기는 첫 실패 뒤 추가 helper 실행을 막도록 바꾸었고, 게임 실행에 이 x86 도구를 넣지 않았사와요.

별도 private [정점 형식 진단](../Build/UnitModelTools/20261005T070200Z_vertexprobe/warrior-v2-layout-v2runtime.json)은 원본 V2 사본의 829개 정점·68바이트 stride를 읽었으나 SDK/wrapper가 반환한 모든 attribute 이름이 빈 문자열이었답니다. 이후 아래 GSD 선행 로드로 이름 누락 원인을 해결했사와요. 필드 의미를 임의 추정한 메시나 대체 모델은 만들지 않았사와요.

[충돌 중간물 정리](../evidence/unit_models/20261005_granny_dump_cleanup.json)는 이번 준비에서 생긴 중복 덤프 4개·45,586,310 논리 바이트를 삭제하고 서로 다른 오류 모듈의 진단 덤프 2개를 보존했사와요. 보존 파일 해시를 대조했으며, 설치본과 저장은 변경하지 않았답니다. 이 부분 구현·진단으로 전체 추정 완료율 약 30%를 올리지 않았사와요.

실행 검증 뒤 [빌드 정리](../evidence/build_tidy/20261005T065418Z_8ce1b3eabdc0/cleanup.json)도 미리보기와 참조 대조를 거쳐 완료했사와요. 새 Host의 미참조 오브젝트 5개·18,637,108 논리 바이트를 삭제하고 실행본·동결 입력·검증 기록을 보존했답니다. 이번 덤프 정리와 합하면 9개·64,223,418바이트(약 61.2MiB)이며, 물리 여유 공간 증가량을 측정한 값은 아니랍니다.

## 원본 전사 모델의 첫 x64 표시 검증

`UnitModels.fpk::unitmodels_stringdatabase.gsd`를 GR2보다 먼저 불러오자 정점·뼈·재질 이름이 복원됐사와요. GSD SHA는 `f063955e71728fc76fdc097b9759e291f203c895d32f5f6eeaf5e4f78f73a959`이며, [Nexus Buddy 제작자의 안내](https://forums.civfanatics.com/threads/nexus-buddy-2-granny-editor-for-civ-5.496855/post-15527919)와 로컬 원본 `LoadStringDatabase` 호출을 근거로 연결했답니다. 기존 `SampleBone`은 이름 복원과 작업용 사본 재저장 뒤에도 접근 위반으로 실패했으므로, 최종 준비기는 원본 `IGrannyCurve.Sample`로 대기 clip의 t=0 위치·회전·크기 곡선을 읽고 부모 뼈 변환을 합성하와요. 이 x86 준비 도구는 x64 게임 런타임에 포함하지 않았사와요.

SDK의 `LocalTransform.ScaleShear`는 앞의 네 값으로 quaternion을 돌려주는 오류가 관찰됐사와요. Nexus Buddy `GrannyBoneWrapper.getScaleShear`의 원본 구조 판독을 사용하고 위치·회전·inverse의 SDK 일치와 전체 bind hierarchy를 검사했답니다. [실제 export](../Build/StockUnitExports/20261005T072135Z/export-manifest.json)는 V2/기본/V4 각각 829/863/796개 정점, 654/674/638개 삼각형, 23개 뼈 전부의 곡선 샘플을 보존하와요. bindWorld × inverseBind의 최대 잔차는 `5.17e-5`이며 원본 FPK/XML의 전후 해시는 동일하와요. `pack_unit_models.py --validate-transforms-only`의 별도 이중 정밀도 재구성에서는 bind 잔차 최대 `5.57e-5`, export의 t=0 world 행렬과의 차이 최대 `1.33e-5`였답니다. 이는 원본 게임의 애니메이션 재생과 시각 동등성 증거는 아니랍니다.

[유닛 패키지](../Build/UnitAssets/b36aa9c2b78af7e597357275abaf9763abd7c252f6eb721d49921cf2a06f4b94/unit-assets.manifest.json)는 482,941바이트, SHA `b36aa9c2b78af7e597357275abaf9763abd7c252f6eb721d49921cf2a06f4b94`이며 원본 BC3 DDS 3개와 V2×3/기본×6/V4×3을 포함하와요. 원본 scale 0.14와 spacing 13을 보존하되 4×3 배치·타일 단위 1/80·방향 보정은 후보 정책이랍니다. 원본 diffuse alpha의 의미·SREF 조명·실시간 자세 변화는 아직 재현하지 않았사와요.

[부품 실행 결과](../Build/terrain_renderer_validation/20261005T073432Z/manifest.json)는 `PASS_COMPONENT_CONTRACT`이며 하드웨어 D3D11에 7,920개 유닛 삼각형을 표시했사와요. [실제 캡처](../Build/terrain_renderer_validation/20261005T073432Z/captures/original_warrior.png)에서 12명 전사의 대기 자세를 확인했고, 방향 변경·숨겨진 유닛/미지원 art 제외·지형 아래 모델의 depth 가림·타일 ID와 도시 projection 유지·잘못된 인덱스 거부를 검증했답니다. 새 컴파일 없이 이전 실행 파일을 재사용했으므로 반복 EXE/OBJ는 만들지 않았사와요.

2026-10-05 07:31 UTC [저장량 실측](../evidence/storage/20261005T073115Z.json)은 246,003개 경로, 경로별 크기 합계 81.50GiB, 하드링크 중복과 NTFS 압축을 반영한 파일 데이터 점유량 약 75.11GiB였사와요. DDS 20.95GiB·DB 20.62GiB·시험 저장 8.54GiB·JSON 6.17GiB가 큰 항목이며, 소규모 OBJ 정리만으로 충분하지 않답니다. 이 감사는 metadata만 읽었고 파일 삭제·내용 수정은 하지 않았으며, 다음 정리는 완료된 시험 자료의 중복과 보관량을 중심으로 진행해야 하와요.

같은 날 [완료 시험 자료 압축](../evidence/storage/20261005T074739Z_5771916e475f/compression.json)은 DB/DDS 496개·논리 크기 약 8GiB의 파일 데이터 점유량을 4,392,805,460바이트(4.09GiB) 줄였사와요. 496개 모두 보관된 SHA와 압축 전후 SHA가 일치하며, 참조한 요청·결과 보고서 해시도 보존됐답니다. 수동 실행본·저장 파일·설치본·MODS는 대상에서 제외했고 삭제한 파일은 없사와요. `tools/compact_completed_runtime_evidence.py`는 기본 미리보기와 `--apply`를 제공하며, 실행 중인 Host가 없고 완료 기록·경로·해시가 확인된 단일 링크 DB/DDS만 처리하와요. [07:53 UTC 재측정](../evidence/storage/20261005T075348Z.json)의 파일 데이터 점유량은 약 71.06GiB이며, 이 수치는 전체 볼륨 여유 공간이 아닌 파일별 NTFS 할당량을 합산한 값이랍니다. 압축은 내용과 참조를 유지하지만 반복 시험본 자체의 보관량을 줄인 것은 아니므로 중복 생성 억제도 계속 필요하와요.

## 원본 모델의 실제 SDK 통합과 보관 정리

Host의 bundle 허용 목록에서 `unit-assets.bin`이 빠졌던 결함을 고치고, 검증·고정한 경로만 표시 계층에 전달하와요. 원본 전사 패키지가 포함된 source/restore에서 각각 30개·35개 model frame 기록이 남았으며, 각 프레임은 지원 유닛 모델 1개·삼각형 7,920개랍니다. [source 독립 검사](../validators/20261005T080828Z_555df83eb3ba/conformance.json)와 [restore 독립 검사](../validators/20261005T081016Z_ff5040048eaa/conformance.json)는 패키지 SHA·바이트 수·header와 bundle 포함을 확인하고, 실제 저장의 133구획을 대조했사와요. 현재 모델은 idle t=0 자세이고 움직임 애니메이션·전체 원본 모델은 미완료랍니다.

[주 정리](../evidence/storage_cleanup/20261005T082918Z_ca2240df4d1f/cleanup.json)는 170,765개 파일, [보조 정리](../evidence/storage_cleanup_auxiliary/20261005T085645Z_666964063a4c/cleanup.json)는 4,287개 파일을 실제 삭제했사와요. 합계 175,052개·73,402,188,353바이트(논리 68.36GiB)이며, 대용량 복구 archive는 만들지 않았답니다. 두 정리 모두 현재 의존 파일 21,047개의 전후 SHA가 일치했고, [삭제 후 검사](../evidence/storage_cleanup/20261005T082918Z_ca2240df4d1f/post_cleanup_validation.json)에서 새 게임·이어하기·저장 8개의 버전 연결과 bundle 8개를 확인했사와요. 이 검사는 게임을 실제로 플레이한 증거가 아니랍니다. [첫 정리 직후 점유량](../evidence/storage/20261005T090842Z.json)은 파일 데이터 15.45GiB이며, 삭제 파일의 경로 합계 크기와 실제 NTFS 점유량은 구분하와요.

원본 DDS/index뿐 아니라 변환한 DDS도 공통 cache에 보관하고 기존 장면 경로에는 읽기 전용 hardlink를 두도록 바꿨사와요. 경로를 resolve하기 전에 junction을 거부하며, hardlink 한도에 닿으면 검증한 사본을 사용하와요. 작은 fixture 90개 검사와 [실제 새 게임·저장 복원](CONTINUOUS_PLAY.md)을 통과하고 수동 기본 실행본에 반영했답니다. [두 실행의 실제 파일 ID 대조](../evidence/storage_reuse/20261005T095243Z.json)는 5,016개 DDS 경로가 286개 파일을 공유함을 확인했사와요.

[BitmapWindow](../Source/Presentation/BitmapWindow.cpp)는 같은 장치의 GPU Scene 텍스처를 직접 공유하와요. 수동 UI의 마지막 합성 PNG 왕복을 제거했지만 세계 그림과 중첩 도시 backdrop의 PNG 경계는 유지했답니다. [O2/Od 각각 106개 검사](../evidence/bitmap_window/20261005T094517Z_fcd7ef815923/conformance.json)는 같은 크기에서 PNG/GPU 픽셀·alpha·UV·clip·실패 프레임 보존·입력 세대·resize를 대조했고, 실제 SDK의 모든 GPU commit도 독립 검사에 포함했사와요. [후속 정리](../evidence/storage_cleanup/20261005T095358Z_36cc1f399102/summary.json)로 대체된 이전 통합 pair와 창 시험 묶음을 제거했답니다.

초기 조사에서 SDK `Nexus/x86/Firaxis.Framework.Granny.Implx64.dll`의 AMD64/PE32+·CLR flags `0x10`을 확인했사와요. 이후 위의 실제 x64 curve 실행과 native 연결부까지 검증했답니다. 프레임마다 전체 메시를 복제하는 준비 방식은 채택하지 않았사와요.

## 아직 원본과 다른 부분

현재 카메라, 높이 배율 2.3, UV 단위 0.8, 조명, 육각 경계에서 높이를 잇는 정책과 조각 선택은 후보 정책이랍니다. 원본 지형 조각 `_T1`의 채널 의미·이웃 조합·회전·블렌딩을 복원한 결과로 간주하지 않사와요. 특히 현재 산 모양은 원본보다 뾰족하며, 원본 게임과의 비교·보정이 남아 있답니다.

전사 이외의 유닛·도시·나무·개선 시설·도로의 원본 모델, 강·해안선·물·안개 효과, 전체 UI·애니메이션·음향과 한 판의 통합은 계속 미완료랍니다. 수동 색상 PNG 경계는 제거했지만 타일 ID 표는 CPU에서 읽으며, 연속 렌더링과 전체 게임 성능을 완료한 증거는 아니랍니다. 원본 외부 저장·선택 모드·장기 플레이도 별도 관문이며, 이 부품 진전만으로 약 30%라는 전체 추정 완료율을 올리지 않았사와요.
