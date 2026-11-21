# M6: 공식 도시 생산 선택 UI 연결 경계

## 연구 UI 공통 변경 뒤의 생산 회귀

2026-10-03 연구 `TechPopup` 연결 뒤 같은 Host `20261003T060726Z_eddea2a1f84d`로 생산 창의 영어·한국어 회귀도 통과했사와요. 영어 `20261003T063936Z_66934f876a87`(PID 31412)·한국어 `20261003T064055Z_4b41b54f1694`(PID 36724)는 각각 exit 0·timeout 없음·`LIVE_SDK_PRODUCTION_INTERACTIONS_PASS`이며, 언어당 9개 입력 batch·9개 GPU frame과 유닛 선택 `[8192,1,128]`·정상 한 턴·fresh native 저장 복원을 확인했답니다. [최신 독립 EN/KO 대조](../evidence/city_production_ui/validators/20261003T064411Z_b1c560071648/conformance.json)는 `ISOLATED_SDK_OFFICIAL_PRODUCTION_UI_TURN_AND_NATIVE_RESTORE_PAIR_PASS`, SHA-256 `83316df0a3fe41e5b03c0c38795541411a05e3d773f2bb1d6cbf50498918fb65`이와요.

새 retained snapshot은 원본 LeftClick·RightClick metadata를 모두 보존하와요. Renderer는 양쪽 metadata를 검증하되 packet은 LeftClick만 생성하고, driver와 검증기도 이벤트별로 정확한 target을 찾도록 보완했답니다. 초기 두 회귀 실패와 정리 기록은 [연구 UI 경계 문서](M6_RESEARCH_UI.md)에 기록했사와요. 아래의 생산 입력 범위·실제 양의 scroll·사람 입력·성공 구매 등 미검증 경계는 유지하며, 일반 연구 한 건의 새 통과를 전체 생산·연구 UI 완료로 해석하지 않사와요.

## 실제 창 분류·pointer·wheel·장면 세대 검증

2026-10-03 생산 창의 실제 SDK 검증은 영어·한국어에서 유닛·건물 분류 접기와 펼치기, 마우스 강조와 해제, 빈 ScrollPanel 영역의 휠 전달과 최대값 0의 clamp, 이전 장면의 unit click·late Escape 거부로 확장됐사와요. Host `20261003T050046Z_30b8cea20b23`의 같은 창·D3D 장치에서 장면 세대 1→8과 두 언어 GPU 캡처 총 18장을 대조했고, 원본 callback의 합법 유닛 주문·정상 1턴·새 세션 native 저장 복원도 통과했답니다. 영어 run은 `20261003T051109Z_c7e4cfd90ca3`, 한국어 run은 `20261003T051302Z_63aa896abc0a`이며 둘 다 exit 0·timeout 없음·clean Core unload이와요. [공통 EN/KO conformance](../evidence/city_production_ui/validators/20261003T052822Z_3cb5d1dff3bd/conformance.json)는 `ISOLATED_SDK_OFFICIAL_PRODUCTION_UI_TURN_AND_NATIVE_RESTORE_PAIR_PASS`, SHA-256 `a78331d886f021dca73348261580fa62490f6bcf411281b496a82c878be81a9e`랍니다.

| 실제 입력 | 검증한 범위 |
|---|---|
| 유닛 분류 접기·펼치기 | 원본 category callback과 불변 snapshot 준비, 같은 창·장치의 atomic scene 교체 |
| 유닛 row hover·명시 mouse leave | 원본 ShowOnMouseOver 표시·해제; 이전 세대 key 0은 좌표와 무관한 해제로 재적용 |
| 빈 ScrollPanel 영역의 wheel down·up | 별도 viewport target으로 전달, 48 logical px/notch prototype 입력과 최대값 0 clamp |
| 분류를 접기 전에 생성된 unit click | 새 scene generation에서 Lua·SDK dispatch 전에 거부 |
| 건물 분류 접기·펼치기 | 원본 callback과 화면 교체; 건물 생산 주문은 실행하지 않음 |
| 실제 unit row 선택·late Escape | 원본 유닛 주문 한 건만 적용하고 이전 세대 Escape 거부 |
| 닫힌 장면의 옛 row click·wheel·새 Escape | 옛 좌표에서 callback을 생성하지 않고 새 Escape도 비활성 VM에서 거부 |

각 언어는 9개 입력 batch, 7개 새 scene revision, 9개 GPU frame과 같은 HWND·owner thread·D3D device를 기록하와요. Packet `ZSUPIX02`는 callback hit와 scroll viewport를 분리하며 `ZSUPIX01` 파싱도 보존하와요. Owner presentation clock만 활성 refresh마다 0.125 증가하고, 선택 전 입력은 SDK 상태·RNG·턴을 유지하와요. Unit 선택 `[8192,1,128]` 뒤 실제 생산 0→5·연구 0→4의 한 턴과 turn-zero/turn-one fresh restore를 기존 API 기준과 대조했답니다. 연구 선택 자체는 기존 API 경로이므로 연구 UI 증거가 아니랍니다. SDK 저장의 133구획 중 Game 이외 132구획은 byte exact이고, 원본 세션·replay 증가만 허용하와요.

관리된 자동 입력 두 fixture의 범위랍니다. 목록이 짧아 실제 스크롤 이동은 검증하지 않았고, 자동 OS mouse leave와 사람 입력·전체 Production UI·연구 UI·성공 구매·세계 화면·실제 음향·전체 gameplay·retail 저장·활성 모드 호환·유용한 성능 향상·장기 회귀·정식 배포는 남아 있사와요. 모든 Present는 시험 desktop의 `DXGI_STATUS_OCCLUDED`였답니다. 실제 패널의 viewport·reported content height는 모두 684이며 maximumScroll=0이랍니다. 양의 스크롤 이동에는 합법 생산 항목이 더 많은 실제 SDK fixture가 필요하와요. Synthetic profile에서 automatic leave tracking은 false이고 명시 WM_MOUSELEAVE를 게시하므로 기본 TrackMouseEvent의 사람 커서 동작은 검사하지 않았답니다. Scene 교체 중 pending input을 비우고 재시도하는 분기는 정적 구현 범위이며, 이번 두 run에서 그 분기가 실행됐다고 주장하지 않사와요.

첫 EN 시도 `20261003T050328Z_4247f16c824a`는 깊은 준비 디렉터리의 DDS index 파일 경로가 265자를 넘어 Python asset 준비에서 정상 exit 1로 끝났사와요. 로그·실패 snapshot은 보존했고 AV·timeout은 없었답니다. `civ5_ui_assets.py`의 후보 저장명만 request SHA 8자리와 payload SHA 16자리로 줄였으며, 원본 FPK entry·요청 이름·전체 SHA·index provenance는 유지했사와요. 이 Python 수정 뒤 같은 정상 sealed Host를 새 EN/KO runtime에서 실행했답니다. 별도 common verifier의 runtime root/session 혼동도 Host의 복원 경로와 scene 요청을 엄격히 연결하도록 수정하고 위 pair를 통과했사와요.

수정 모듈은 Host의 production window lifecycle·Lua input dispatch, retained UiScene·BitmapWindow/Renderer의 V2 scroll target, Python asset/scene 준비·실행 driver·독립 검증기이와요. 원본 UI Lua/XML·규칙·밸런스·Mod ID·버전·저장 키·schema는 바꾸지 않았사와요. 격리 Build와 evidence만 갱신하며 Stage·설치 게임·MODS·사용자 저장으로 배포하지 않았답니다. 검증 후 [이번 정리 기록](../evidence/build_tidy/20261003T052750Z_640de3a92369/cleanup.json)에 따라 미참조 final object 3개·8,012,603바이트를 제거했고, Host EXE·report·frozen input·로그·저장·캡처는 보존했사와요.

## 이전 selected-unit 창 입력 관문

아래 내용은 Host `20261003T041147Z_a73b82203b59`의 좁은 unit-only fixture 이력이랍니다. 당시 미검증 항목은 위 최신 관문과 구분해 읽으시와요.


2026-10-03의 최신 생산 UI 관문은 영어·한국어 직렬 fixture에서 원본 `ProductionPopup`의 실제 Button hit 좌표를 owned HWND에 게시하고, stock callback→SDK unit order→정상 1턴→새 세션 native 저장 복원까지 통과했사와요. Host `20261003T041147Z_a73b82203b59`와 같은 선택 `[8192,1,128]`을 사용하며, GPU 초기·resize·closed 캡처 6장의 bitmap parity 및 같은 HWND·D3D 장치·scene generation 1→2를 확인했답니다. 두 언어의 PNG에서 이전 생산 row 겹침과 도시 제목 border 잘림도 해소됐사와요. 자동 게시한 좁은 unit 선택 fixture이며 사람 입력·전체 Production UI·연구 UI·성공 구매·retail pixel/save 호환 증거는 아니랍니다. 모든 Present는 시험 desktop의 `DXGI_STATUS_OCCLUDED`이며, category·hover·scroll·append·cancel 및 다른 order 종류의 실제 창 검증이 남아 있답니다. 연구는 기존 API 경로이고, 구매 미연결 오디오는 SDK 변경 전에 거부하와요. 세계 화면·실제 음향·전체 gameplay 입력·활성 모드·유용한 성능 향상·장기 회귀·정식 Stage 승격도 남아 있답니다. [EN/KO conformance](../evidence/city_production_ui/validators/20261003T042526Z_e3d70f920b78/conformance.json)의 SHA-256은 `bf54edc4eee61d1265b30eff14bd744ccd14858d9a3274952128abd7c459c4f1`이와요. 영어 run은 `20261003T042320Z_38478e5b7441`, 한국어 run은 `20261003T042359Z_66020e7ce0c4`이며 두 run 모두 exit 0·timeout 없음·clean Core unload를 확인했사와요. 실제 hit는 `[128,35,265,375,307]`이고 선택한 합법 unit 1의 original callback만 받도록 fixture를 제한하와요. 초기 batch의 unit click 한 건을 받아들이고 late Escape를 거부하며, 닫힌 empty hit map의 옛 row 좌표 클릭은 callback event로 만들어지지 않고 새 Escape도 거부하와요. 오래된 scene-generation control event를 실제 주입해 거부한 proof는 이번에 포함하지 않사와요.

각 언어의 초기·resize frame은 안정 그림 영역 1,013,600픽셀·검은 letterbox 218,800픽셀을 대조하고 destination 경계 7,600픽셀을 제외했답니다. Closed capture 540,000픽셀과 transparent source 2,073,600픽셀은 제외 없이 대조하와요. Pure bitmap parity와 owned GPU readback 기록의 범위이며 사용자 desktop 표시·retail pixel 동등성은 false랍니다. [Root 육안 검토](../evidence/city_production_offscreen/visual_review_20261003T042820Z_694a61238de3/visual_review.json)는 이 두 fixture의 이전 row/title P2만 통과시키며 전체 popup 수용을 뜻하지 않사와요.

UI snapshot은 원본 GGXML로 측정한 `textFrame`·`fontMetricSource`·`fontMetrics`와 실제 visible enabled LeftClick callback의 `inputTargets`를 함께 기록하와요. Callback manifest에 한정한 scalar void1/void2는 실제 native collector의 unit tuple과 대조하고, visual tree에는 native pointer/객체를 내보내지 않사와요. Stack main-axis anchor는 row slot 기준으로 계산하고 cross-axis/offset을 보존하며, `SetText`와 Production `LocalizeAndSetText`를 공통 측정 경로로 묶었답니다. Renderer는 WrapWidth=0을 자동 줄바꿈 없음으로, lineAdvance를 GGXML+원본 LeadingOffset으로 검증하고, Production 닫힘의 정확한 `queued → shown:16 → processed:16 → context-hidden:ProductionPopup` 수명주기를 확인하와요. 원본 XML·문자열·balance/save schema는 변경하지 않았사와요.

별도 입력 부품에는 기본 비활성 pointer/wheel queue를 추가했사와요. O2/Od input-dispatch 각 65개와 BitmapWindow 각 63개, renderer geometry 67개·font 9개 회귀를 통과했지만 이번 실제 창 fixture는 pointer opt-in을 켜지 않으므로 hover/wheel 성공으로 계산하지 않사와요. 처음 연결 때 나타난 줄바꿈·현지화 textFrame·LeadingOffset·Ranking 전용 닫힘 가정 오류는 structured normal exit1로 기록됐으며 native AV/timeout은 없었사와요. 실패 입력·로그는 보존했답니다. 새 Host build 뒤 [정리 기록](../evidence/build_tidy/20261003T042152Z_0e524ca6c359/cleanup.json)의 unreferenced object 6개를 제거했고, 두 Host exe/report와 frozen input·저장·캡처는 보존했사와요.

## 이전 direct-key 증거 범위

현재 구현은 원본 BNW `ProductionPopup.lua/.xml`을 retained UI에서 실행하고, 합법 유닛 하나를 원본 callback으로 선택해 실제 SDK 도시 생산 명령으로 전달하는 단계까지 왔답니다. 최신 Host build는 `20261003T031737Z_1493b0b83b63`이며 EN·KO 실행 결과는 각각 [EN result](../evidence/city_production_ui/20261003T032021Z_127223acdc4a/result.json), [KO result](../evidence/city_production_ui/20261003T032146Z_467795e71ec3/result.json)이와요. 둘 다 `ISOLATED_SDK_OFFICIAL_PRODUCTION_UI_TURN_AND_NATIVE_RESTORE_PASS`, `exit_code=0`, `official_production_callback_verified=true`, `turn_advance_verified=true`랍니다. 두 run은 각각 `en_US`와 `ko_KR`의 serial-0 Production fixture이와요.

이 pass의 범위는 원본 ProductionPopup callback을 통한 실제 SDK unit order, 기존 연구 API 경로, 1턴 진행, 세 개의 fresh Core session에 대한 저장·복원 상태 검사이와요. 이것은 연구 선택 UI 검증이 아니랍니다: 결과 모두 `research_ui_verified=false`랍니다. 또한 `renderer_verified`, `interactive_input_verified`, `retail_save_compatibility_verified`, `accepted_stage_promoted`도 false이므로 전체 화면 렌더링, 사람 입력, retail save 호환, Stage 승격은 검증되지 않았사와요. EN·KO 두 fixture는 현재 생산 선택 경로의 이중 언어 반복이지 전체 ProductionPopup 동작이나 전체 언어 지원 증거가 아니랍니다. 도시 API 명령의 별도 이력은 [M6_CITY_DECISIONS.md](M6_CITY_DECISIONS.md)에 있사와요.

Pair conformance는 [검증 보고서](../evidence/city_production_ui/validators/20261003T032512Z_93505e9e4a52/conformance.json)에서 `ISOLATED_SDK_OFFICIAL_PRODUCTION_UI_TURN_AND_NATIVE_RESTORE_PAIR_PASS`로 확정되었답니다(SHA-256 `a478fe212a4e7e0aff0996fab6b67fb990b0c80825d160583251ec3ef3f97d75`). 양쪽 언어 모두 선택 tuple `[8192,1,128]`, timeout 없음, 종료 코드 0, purchase 거부 true 및 성공 purchase false를 확인하와요. 이는 앞서 적은 serial-0 Production fixture 두 건의 conformance이지, 다른 popup 항목이나 사용자 조작 범위를 추가하지 않는답니다. 별도 [UI input dispatch component 결과](../evidence/ui_input_dispatch/20261003T032238Z_f80af3799b0b/conformance.json)는 SHA-256 `e8f9577357392c8a66f00d0d3a56b1cdfd2776bd3e387ab3f42fcebe381191c0d`로 O2/Od 각각 54개 native 검사와 Lua mock ranking 회귀를 통과했사와요. 그 scope에는 Host window나 GameCore가 없으므로 stock popup 실제 native Button/Up/Down 조작 검증으로 해석하지 않는답니다.

앞선 실행에서 numeric `SetText`와 Food 중심 anchor 오류를 각각 수정했사와요. 그 뒤 `20261003T024516Z_e8fa02859ba0`은 native access violation으로 끝났고, 새 단계 추적 실행 `20261003T025851Z_b8fee6a9cd99`은 합법 유닛 조회 뒤 target 수집의 Lua 단계에서 같은 예외를 기록했답니다. 현재 구현은 좌·우 callback의 중복 retained key를 클릭 종류로 구분하고, Lua 오류가 발생할 수 있는 함수와 string/vector 소유의 전체 수명을 별도 noinline 함수로 분리하와요. 새 build의 두 언어 실행과 O2/Od 거부 회귀는 통과했지만 과거 AV의 정확한 예외 원인까지 확정한 것은 아니랍니다.

## 공식 자산과 준비 provenance

설치 원본은 `C:\Program Files (x86)\Steam\steamapps\common\Sid Meier's Civilization V\Assets`이와요. `evidence/ui_popup/assets/prepared.json`의 현재 provenance는 설치본과 동결된 `Source/Assets/UI` 복사본의 SHA-256이 일치함을 기록하와요. Production Lua는 `863e008b74eff264695c4878b279b2f087394ab0ee2ba555e0603e883f562530`, Production XML은 `a6ffceaead94919aaaa7ce754a7099564b160ada41472a493616696c1e473b24`, InfoTooltipInclude는 `405a3d677fff50acdc1155a97e713185219ca9fc2ceb61db6d298b1fc5382fa4`, IconSupport는 `c9815b6fb6ee5d9fbba1a523b56437e8d4fa798ab8633f9cfc7d9783be5434b4`, FLuaVector는 `e9170f61fc4bb070ee8d1617c547f2cb56b47937db00ccd8b184ad2a15bfb2f6`, InstanceManager는 `b5439abfd50c170f411972e9c9b60e8ecd7be8a13851cfc28c7c02d7bb781a1e`이와요. Production 스타일 출처 `Assets/UI/Styles.xml`은 `99294277279db2462fbf15dee401905351b80dc4dd5ecb151c0b4db1770d4374`랍니다. TechPopup Lua/XML SHA는 준비 manifest의 이 실행 입력이 아니므로 이 문서에서는 재검증된 provenance라고 섞어 쓰지 않사와요.

준비된 `inline_icons.json`은 원본 base/Expansion2 IconFontMapping XML과 명시 선택한 기본·Expansion2·DLC_07 GGXML에서 정적 glyph mapping을 만들며, 각 항목의 mapping/font 원본 및 hash를 보존하와요. `prepared.json` 상태는 `INSTALLED_UI_POPUP_ASSETS_PREPARED_NOT_RUNTIME_VERIFIED`, `stock_asset_search_order_verified=false`, `renderer_verified=false`랍니다. 따라서 자산의 출처 고정은 확인됐지만 stock 검색 우선순위 및 retail 렌더링 동등성은 아직 검증되지 않았사와요.

원본 ProductionPopup XML에는 `AlphaAnim, Box, Button, Container, Context, DownButton, Grid, GridButton, Image, Instance, Label, Meter, ScrollAnim, ScrollBar, ScrollPanel, ShowOnMouseOver, Stack, TextureBar, UpButton` kind가 있답니다. 공식 Lua는 `IconSupport`, `InstanceManager`, `InfoTooltipInclude`를 include하고, `IconSupport.lua`는 `FLuaVector.lua`를 포함하와요. 현재 static asset set 및 control tree provenance는 위 prepared manifest에서 추적 가능하답니다.

## 구현된 실행 경로와 경계

Host는 `BUTTONPOPUP_CHOOSEPRODUCTION`으로 공식 popup context를 열어 원본 `OnPopup`→`UpdateWindow`를 실행하며, 준비된 `ProductionLayout`의 동적 `ProdButton` 목록과 callback을 사용하와요. `ProductionCommandGuard.lua`는 매 입력 때 활성 human 소유 도시를 재획득하고 규칙 항목·현행 가능 여부를 검사한 뒤 SDK receiver로 전달한답니다. 최신 결과의 `production_ui_selection_logs`는 `8192,1,128`이며, official callback verification과 turn advance가 참이고 저장·복원 후 도시 결정 상태가 일치한답니다. 이는 실제 게임 데이터 명령의 좁은 fixture이지 pixel/human UI 검증이 아니랍니다.

Production 주문 receiver는 `ORDER_TRAIN`, `ORDER_CONSTRUCT`, `ORDER_CREATE`, `ORDER_MAINTAIN`을 구분하고, active human의 실제 도시와 유효 규칙 ID를 검사한 뒤 `ResponseCityPushOrder`로 실제 SDK legality check 및 명령 적용을 수행하도록 되어 있답니다(`Source/Host/LocalSdkSession.h:95-123`). Lua guard도 해당 네 생산 분기를 확인하와요(`Source/Host/ProductionCommandGuard.lua:14-27`). 현재 EN/KO fixture가 실제로 실행해 검증한 선택은 합법 유닛 훈련 하나뿐이므로 건물·프로젝트·process 명령은 receiver 정적 지원은 있으나 실제 실행 증거가 없답니다. append 선택은 원본 `shift=not g_append` 계약을 보존하며 receiver envelope가 양쪽 bool을 허용하나, 최신 fixture가 검증한 것은 아니랍니다.

구매 경계는 더 좁답니다. 원본 purchase callback은 `CityPurchaseUnit/Building/Project`로 가기 전에 `requirePurchaseAudio` gate에서 거부되며, 현재 native adapter는 이를 `Purchase UI audio backend is not connected` 사유로 거부하와요(`ProductionCommandGuard.lua:28-42`, `UiPopupContext.h:409`). 실제 city를 대상으로 한 `pcall` fixture는 이 오류 사유와 gameplay/order/event 불변을 확인하고, SDK purchase mutation 전에 종료된답니다(`UiPopupContext.h:461-484`). Pair conformance도 거부 true·성공 false를 기록하와요. 그러므로 구매 성공은 증거가 아니며 구매 UI는 오디오 backend 연결 전까지 미지원 경계로 남는답니다.

아래 native hit 미완료 및 과거 offscreen 표기는 앞선 direct-key 단계의 이력이랍니다. 현재 unit Button hit·두 언어 layout의 증거와 한계는 위 최신 관문을 따르며, 전체 stock UI 완료는 아니랍니다. Native `Button`, `UpButton`, `DownButton` hit dispatch의 Host 통합 및 실제 popup 조작 검증은 미완료 관문이며, offscreen diagnostic은 native hit 영역을 `GridButton` 두 건으로만 전달했다고 기록하와요. Native input-dispatch component 자체는 별도 O2/Od·mock 회귀를 통과했지만 이는 target collector 단위 검사이므로 category/scroll/cancel/append 등 모든 화면 조작을 사람이 사용할 수 있다고 해석하지 않사와요. 연구 선택 화면 역시 별도 `TechPopup` 경로이며 최신 run은 기존 연구 API 경로와 1턴 결과만 포함하고 `research_ui_verified=false`이므로 연구 UI는 검증하지 않았답니다.

## 이전 offscreen 및 pixel 검증 이력

[Offscreen diagnostic](../evidence/city_production_offscreen/production_frame_offscreen_20261003T031807Z_1d06e13b0e/diagnostic.json)은 `FAILED_SDK_RUN_PRODUCTION_FRAME_OFFSCREEN_DIAGNOSTIC_PASS`이와요. 이는 뒤이은 native 선택 단계가 실패한 과거 SDK 세션의 frame snapshot을 입력으로 삼았으며, scene packet 준비와 별도 bitmap CLI 렌더 성공만 뜻한답니다. diagnostic 자체는 `whole_production_ui_success=false`, `retail_pixels_verified=false`, `sdk_rerun=false`, `host_exe_rerun=false`로 범위를 제한하고 있사와요. 그러므로 이 기록을 SDK 성공이나 production 화면 통과에 합치면 안 된답니다.

Root의 해당 PNG 육안 점검에서는 unit/building row label 겹침과 상단 도시 제목 border 잘림을 확인했사와요. 따라서 pixel layout acceptance는 실패 상태이며 P2로 남는답니다. Asset hash 및 packet 생성 성공은 이 시각적 결함을 해소하지 않사와요. 기존 [GPU closed-scene refresh proof](../evidence/live_ui_window/validators/20261003T013008Z_0f6efdd27e/conformance.json)는 독립적인 창 refresh 증거이며 ProductionPopup layout·renderer·input gate를 통과시키지 않는답니다.

[육안 검토 기록](../evidence/city_production_offscreen/visual_review_20261003T032703Z_28f39581fbee/visual_review.json)은 확인한 PNG 해시와 겹침·잘림 영역, 화면 수용 미통과를 별도로 보존하와요. 검증 뒤 [정리 기록](../evidence/build_tidy/20261003T032534Z_938409b608e4/cleanup.json)에 따라 해시 참조에 없는 중간 오브젝트 18개·40,907,396바이트를 삭제했고, 6개 빌드 보고서·6개 실행 파일의 해시를 다시 확인했사와요. 동결 입력·로그·저장·캡처·Stage·MODS는 그 삭제 범위 밖이랍니다.

## 다음 검증 관문

1. 양의 범위가 있는 실제 생산 목록의 scroll 이동, Up/Down·append·cancel과 자동 OS mouse leave·사람 입력을 검증해야 하와요. 최신 category·hover/clear·빈 panel wheel의 max-zero clamp는 위 두 fixture에서 통과했답니다.
2. unit 외의 legal building/project/process 및 append=true, dirty event와 turn 결과를 실제 SDK에서 검증해야 하와요. 구매는 오디오 backend가 연결되기 전까지 mutation 전 거부만 검증돼 있답니다.
3. 연구 UI, 세계 renderer/audio, 일반 gameplay 입력, 사용자 실제 조작, retail 저장과 활성 모드 호환성, 반복 성능·장기 회귀·정식 배포를 이어서 진행해야 하와요.
4. 최신 pair의 category·pointer clear·빈 panel wheel·이전 장면 입력 거부·selected unit native hit·GPU bitmap parity·턴·fresh restore는 해당 fixture에서 완료됐답니다. Fixture·Host·renderer/font 입력이 바뀔 때 새 증거로 범위를 확인해야 하와요.
