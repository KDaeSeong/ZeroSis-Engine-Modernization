# 후속 메모 (Codex, 2026-11-16, 12단계 2·3번)

높이장 절삭·원본 기본 높이 metric과 물 Raw/소비 projector 공유를 연결했다. 새 캐시 sampling·반사 투영·얼음 파일전용 부품은 확인된 계약까지만 구현했다. 전체 컴파일/링크와 최종 보존·용량 결과는 vidence/world_terrain_original/phase12/current_work.json, 설명은 docs/TERRAIN_OFFLINE_PHASE12.md를 따른다. 기존 준비 묶음90b98은 이전 소스용이며 새 소스와 동일하다고 표시하지 않는다. 실게임·화면·Host/SDK/CLR/HWND/GPU/음향 실행 보류 및 Claude의4번 담당 경계는 유지한다.

# Claude 인계 — ZeroSis' 엔진 개조

## Claude 담당 분리 — 2026-11-16

Claude에게 넘길 현재 작업은 docs/CLAUDE_WORK_ASSIGNMENT.md를 따른다. 4번의 원본 곡면 기저·세계 카메라·숲 모델/배치 분석과 별도 CPU 부품을 맡기며, 기존 Source/Tests/공통 도구/진척 기록은 직접 수정하지 않고 vidence/world_terrain_original/claude_geometry/의 근거·패치 제안으로 전달한다. Codex는 2·3번과 공통 렌더/빌드/실행 묶음 통합을 담당한다. 실게임·화면 실행 보류는 그대로 유지한다. 아래의 최신014dd/90b98 연동 상태는 완료 기준선이다.

## 최신014dd 빌드 격리 실행 묶음 연동 — 2026-11-16

최신014dd Host/SDK430을 새 `20261116T123457Z_90b98a574efc`에 파일 전용으로 연결했다. 최신 소스·컴파일본·준비묶음의 Host/SDK/6팩SHA가 일치하고 static specscreenmap을 별도5번째ENV에 연결했다. UI154/지원8/6팩 직접공유·독립DB/GR2/config·새게임전용/교차Resume차단·독립 계약/자산/저장/사전검사 PASS다. 소스변경·재빌드·Host/SDK/CLR/창/GPU/음향/게임 실행·기본실행/등록변경0이다. 기존 aa885/99b3/4c8f/40a 저장과 기존6팩을 보존했다. 중복지원8개7.83MiB회수·원본 자산복사0이며 실제 게임/화면 수락보류는 유지한다. 상세는 docs/RUNTIME_PHASE11_INTEGRATION.md, 최종상태는 evidence/world_terrain_original/phase11/runtime_integration/current_work.json이다.

## 선택 작업 2·3·4·7 오프라인 통합 — 2026-11-16

최신 컴파일 후보는 `20261116T114748Z_014dd63ad3bc`이며 실제 5TU 컴파일·링크/독립 attestation 경고0이다. 방향 행렬·법선 UNORM 보기를 교정하고 지형 t9=정적 specscreenmap/물 Raw의 원본 자원·샘플러를 분리했다. 기존 8단계 t9=Raw 추론은 owner+8 누락으로 폐기했다. 원본 물 blend/FOW 선후·단일 안개, 지형 정점 0/2/4 작업자를 연결했다. 숲·쌍삼차·일반 RH 카메라는 CPU/Shader 부품만이며 원본 GR2/배치/basis/world camera가 없어 생산 제출 미연결이다. CPU 모드합계703,353/strict13/원본68 PASS, Host/SDK/CLR/창/GPU/음향/게임0회다. 기존5팩/aa885·99b3·4c8f·40a 사용자 저장/기본 실행을 보존했고 새팩1,398,304B 하나만 추가했다. 새 runtime은 미생성이고 다음 연동 때 ZEROSIS_SCREEN_LIGHT_ASSETS와 해당 SHA팩을 함께 넣어야 한다. 상세는 docs/TERRAIN_OFFLINE_PHASE10.md, 현재 상태는 evidence/world_terrain_original/phase10/current_work.json이다.

## 최신8단계 빌드 격리 실행 묶음 연동 — 2026-11-15

최신dbb01a1f4f50 Host/SDK430을 새 `20261115T134603Z_aa8853762399`에 연결했다. 최신소스·컴파일본·준비묶음이일치한다. 5팩직접하드링크/UI154/지원8공유/4ENV/독립DB·새게임전용·사전검사와독립계약/자산/저장검증PASS다. 엔진소스변경·재빌드·Host/SDK/CLR/창/GPU/음향/게임실행·기본실행/등록변경0이다. 새핵심할당62.55MiB,5팩새복사0·중복지원7.83MiB회수,이전99b3/복구4c8f/40a사용자저장은보존했다. 실제화면/게임수락보류는유지한다. 상세는 `docs/RUNTIME_PHASE9_INTEGRATION.md`,최종상태는 `evidence/world_terrain_original/phase9/runtime_integration/current_work.json`이다.

## 원본 법선·화면 반사·동적 그림자·물 안개 8단계 — 2026-11-15

현재 실제 컴파일·링크 후보는 `20261115T121456Z_dbb01a1f4f50`이며 경고0, 독립 파일 검증과 profile 봉인까지 통과했다. 원본 bulk 기본법선/half 값·RGBA8 정밀도, t9=Reflection Texture Raw/품질 규칙/공유 반사, private 지형·현재유닛 그림자→물, 물.4 FOW/유닛제외 표식을 연결했다. CPU314,862·새 strict12/재사용4·원본68주장 통과, Host/SDK/CLR/HWND/GPU/음향/게임 실행0이다. 첫 빌드는 링크 뒤 기록 전 중단돼 새 STAGE/검토 계획으로 다시 기록했고, 첫 payload와 모든 임시물을 정확히 정리했다. 기존5팩/99b3·4c8f·40a저장/기본 실행을 보존했다. 새 runtime은 만들지 않아99b3는 직전23c 조합이다. 원본 캐시 보기·밉·압축/정규화·반사 전체 장면/카메라/색공간·하드웨어 물 혼합·실GPU/화면은 계속 미확정이다. 상세는 `docs/NORMAL_REFLECTION_SHADOW_WATER_PHASE8.md`, 최종 상태는 `evidence/world_terrain_original/phase8/current_work.json`이다.

## 최신 빌드 격리 실행 묶음 연동 — 2026-11-15

최신23c5037 Host/SDK430을 새 `20261115T101941Z_99b3c393ee9a`에 파일 전용으로 연동했다. 이제최신소스·컴파일본·격리준비본이일치한다. 다섯원본팩직접하드링크·UI154/지원6개·4ENV·새DB격리·파일사전검사/독립계약·자산·저장검사를통과했다. 소스/재빌드0·게임/Host/GPU실행0·기본실행/등록변경0이다. 기존4c8f와40a사용자저장은보존했다. 새핵심실할당62.52MiB,새팩복사0·중복지원8개회수7.83MiB다. 원본화면/게임플레이수락은계속보류다. 상세는 `docs/RUNTIME_PHASE7_INTEGRATION.md`, 최종상태는 `evidence/world_terrain_original/phase7/runtime_integration/current_work.json`이다.

## 세부 법선·자기그림자·최종 반사 합성 6단계 — 2026-11-15

현재 컴파일 후보는 `20261115T093013Z_23c5037b12b9`다. 원본 materialH→Sobel16·MacroShadow→CacheBake·bakedSpec→finalt8 연결을 추가 확인하고 생산/합성을 연결했다. 이전t8=albedo 해석을수정했고 원본 NORMAL0 생산·현재68/66/정밀도·그림자보정·screenLight1은후보/미확인이다. CPU부품185,761검사·현재셰이더10단계·실제C++14다섯단위컴파일/링크경고0, Host/GPU/게임0회다. 새팩/CPU원본복사0, 기존다섯팩·4c8f/40a저장·기본실행을보존했다. 동적유닛그림자/물t13·실GPU화면수락은계속미검증이다. 상세는 `docs/LIGHTING_FIELDS_PHASE6_IMPLEMENTATION.md`, 근거는 `evidence/world_terrain_original/phase6/current_work.json`이다.

## 원본 조명·혼합 5단계 — 2026-11-15

현재 컴파일 후보는 `20261115T064034Z_2b0664f7ca2e`다. 원본 지형 조사광/감마/LUT·별도 반사 조명, 물 전체 조명식과 q2³/그림자 항을 연결했다. 중립 세부 법선/그림자·캐시/광원/불투명 혼합은 후보이며 원본 spec 경로·물 전용 FOW GPU 연결은 미추적이다. CPU/자산/선택·캐시10,548검사와 strict셰이더6개·실제 C++14 다섯 단위 컴파일/링크 경고0, Host·GPU·게임 실행0회다. 730040B 보조팩 하나만 추가하고 네 기존팩·4c8f/40a 저장·기본실행을 보존했다. 상세는 `docs/LIGHTING_PHASE5_IMPLEMENTATION.md`, 근거는 `evidence/world_terrain_original/phase5/current_work.json`이다.

## 고정 수면·등고선·반사·굴절 4단계 — 2026-11-15

현재 컴파일 후보는 `20261115T055523Z_51738aa69964`다. 고정 평면·높이장 등고선·원본LEAN광학·격리반사/장면굴절 후보와 실제depth/ID·유닛높이·캐시키를 연결했다. CPU·셰이더6개strict·C++14컴파일/링크 경고0, Host/SDK/창/GPU/게임실행0회다. 물LEAN1개3,495,363바이트만 추가했고 기존팩·4c8f/40a저장·기본실행은보존했다. 원본런타임수위/광학/캐시/전체blend·추가depth항은미복원/미확인, 장면굴절은원본에서확인되지않은별도후보다. 상세는 `docs/WATER_SURFACE_PHASE4_IMPLEMENTATION.md`, 근거는 `evidence/world_terrain_original/phase4/current_work.json`이다.

## 물·해안선·강 3단계 — 2026-11-15

현재 컴파일 후보는 `20261115T043249Z_a0d991ededdd`다. 원본14DDS·13스타일·9프로필과 SDK 공유변으로 색 전용 수면/해안/강 후보를 연결했고 CPU·strict 셰이더·실제 컴파일/링크까지 통과했다. 새 보조 팩은5,180,388바이트/SHA `2ff227dae9d16398e038e8ea33624940a9581e0eb2d37c3891121fae22c25afc`이고 지형/안개 팩은 재사용했다. 실게임·창·GPU 실행0회, 4c8f/40a 저장과 기본 실행본을 보존했다. 상수 수면·등고선 해안·완전한 LEAN/반사/굴절은 미복원이며 세부 후보/남은 관문은 `docs/WATER_PHASE3_IMPLEMENTATION.md`, 근거는 `evidence/world_terrain_original/phase3/current_work.json`에 있다.

## 전장의 안개 2단계 — 2026-11-15

현재 컴파일 후보는 `20261115T034310Z_77ed882144d1`다. 마스크·구름 단순 흐름·색 변환·거리 안개를 색 전용 패스로 연결했고 오프라인 부품검사와 실제 컴파일·링크까지 통과했다. 지형 V2는 재사용하고 안개 SHA `42ae12554e1514dd48a9a5df25f47b4280d22d180dff29d169c602334e879bcc` 한 묶음만 추가했다. 실게임·창·GPU 실행0회, 기존4c8f/40a 사용자 세션을 보존했고 새 게임 실행 묶음·기본 실행 변경은 없다. 채널·마스크·LUT 로더·구름 흐름·거리 보정은 후보이며 상세와 남은 관문은 `docs/FOG_PHASE2_IMPLEMENTATION.md`, 근거는 `evidence/world_terrain_original/phase2/current_work.json`에 있다.

## 원본 지형 1단계 — 2026-11-15

현재 컴파일 후보는 `20261115T024443Z_8470b8d966f8`, 새 지형은 ZSTERR02/SHA `02104c582759bf0cefb58f97379699e45300eb2a9c6da6fdd3c65d1440cb84e8`이다. 오프라인 구현·부품검사·실제 컴파일·링크까지 완료했고 Host/SDK/CLR/창/GPU/음향/게임 실행은0회다. 새 V2 게임 실행 묶음은 아직 만들지 않았으며 직전 준비본4c8f와40a 사용자 세션을 보존했다. **규칙 동등, 배치 동등은 미검증**이며 보정 후보·남은 관문은 `docs/TERRAIN_PHASE1_IMPLEMENTATION.md`에 명시했다. 기록은 `evidence/world_terrain_original/phase1/current_work.json`이다.

## 유휴 렌더링 재사용 단계 — 2026-11-15

추가 연동 기록: 기존 SDK 제작 당시의 Windows 파일 두 개가 운영체제 갱신 뒤 달라져 첫 준비가 중단됐다. WinSxS의 실제 옛 사본을 재해시해 같은 바이트임을 확인하고, 합계352,256바이트의 역사 자료로만 보관했다. 고정된 static SDK·부모·프로필과 정확한 두 원래 입력에만 적용되는 검증 별칭을 추가했다. 보관 바이트는 일반 검증과 종료 재해시를 거치며 기존 전체 SDK 입력·객체·의존성 검사는 유지했다. 훼손·범위 이탈 거부14개와 공개 파일 검증을 통과해 준비 재시도1이 성공했다. SDK 재빌드·시스템 파일 변경·과거 도구 실행은 없었다. 근거는 `evidence/sdk_runtime_play/historical_os_inputs/validation_result.json`과 `evidence/game_menu/idle_render_cache/runtime_input_recovery.json`이다.

현재 Host는 `20261115T005626Z_256252d8abe3`, 별도 실행 묶음은 `20261115T011241Z_4c8fd55e99db`이다. 부모는 `2b25`/`40a8`이며 SDK430과 V4 자산154개를 그대로 사용했다. C++14 다섯 단위를 실제 컴파일·링크했고 경고는0개다. 현재·동결 입력은 각각 818개·818개, 실제 컴파일 의존은 587개다. 준비본은189파일이고 기본 실행·등록은 바꾸지 않았다.

정지 상태의 유닛 애니메이션이 지형 메시 생성·버퍼 업로드·ID GPU 읽기·전체 픽셀 윤곽 계산을 매번 반복하던 경로를 줄였다. 동일한 지형 입력에는 단일 소유 캐시를 사용하고, 지형·시야·시점·확대·해상도·장치·문맥이 바뀌면 다시 만든다. 메타데이터는 반환값과 독립적으로 보유하고 완성된 후보만 교체한다. 색·깊이는 매번 지우고 지형과 현재 유닛 자세를 다시 그리므로 이전 자세의 깊이를 재사용하지 않는다. 렌더 대상과 읽기용 자원을 재사용하며, 유닛 버퍼는 현재 프레임의 정확한 크기만 보유한다. 자동 애니메이션의 반복 로그만 생략했다.

운영 헤더를 사용하는 순수 CPU 캐시 검사와 소스 회귀 대조를 통과했다. 원래 지형·유닛·윤곽 수식과 애니메이션·입력 세대 검사는 유지했다. 새 Host·SDK·창·GPU·게임은 실행하지 않았다. CPU 절감률·실제 프레임 시간·동작 중 잔상/클릭 판정 확인은 실행 보류 해제 뒤의 관문이다. D2D/문자 자원 생성과 유닛 CPU 계산 등 잔여 비용도 있으므로 CPU 문제 전체 해결이나 실측 성능을 선언하지 않는다.

Windows의 cmd.exe가 이전 빌드 이후 바뀐 것은 사전부터 존재한 도구 차이였다. 이전 보고서를 수정하지 않고, 현재 Microsoft 서명·SHA와 부모의 옛 두 행을 묶은 cmd 한정 선택을 추가했다. 나머지 제공자·게이트 검사는 유지했다. 기록은 `evidence/game_menu/idle_render_cache/current_work.json`이다. `40a8`의 사용자 세션과 저장은 보호 대상으로 남겼다.

최신 갱신: 2026-11-15, 한국 시각. 아래 "슬라이더 마우스 오버 단계"가 현재 쌍이다. 그 아래 "원본 규칙 후속 단계"는 직전 쌍, "리플레이 계절 키·휠 단계"와 "보상 알림 단계"는 그 이전 쌍의 기록이다. 전체 엔진 목표의 완료나 실게임 실행 승인이 아니다.

## 후속 메모 (Claude, 2026-11-15)

- 조각 선택·배치를 정적으로 해독했다(`retail_piece_placement_probe.json`, `piece_cells.json`, 계획 문서 2.7절). Host·게임·GPU는 쓰지 않았다.
  - 대조는 단계 4→1 순서의 탐욕 배치이고, 위치·조각·방향(4종) 순서를 C 런타임 `rand()`로 섞는다.
  - 조각 칸은 지형 비트 마스크와 대륙 번호로 지도 칸을 제약한다. 지형 비트 이름은 조각 파일 이름에서 붙였다.
  - 텍셀 지도는 육각당 64×64텍셀이고, 조각 이미지는 1:1로 찍힌다.
- 이어서 시드와 지도 칸 채우기를 확정했다(`retail_map_cells_probe.json`, 계획 문서 2.8절).
  - CreateTerrain이 `srand(GetPreGame()->mapRandomSeed())`를 부른다(이름은 SDK 머리말 슬롯 순서 기준).
  - 플롯은 지형·언덕·산·자연 경관에 따라 지형 비트 하나와 `GetContinentType` 대륙 번호가 된다. 다른 지물은 비트를 바꾸지 않는다.
- 이어서 남은 세 가지를 정리했다(`retail_terrain_remaining_probe.json`, 계획 문서 2.9절).
  - 파일 조회는 추가 색인(콘텐츠 패키지·모드)이 Base 색인(FPK, Assets)보다 먼저다. 그래서 DLC/Shared의 TerrainDef.csv가 적용된다. 패키지 활성화 호출 자체는 추적하지 않았다.
  - 반사 캐시는 장치 등급 8 이상, 내부 플래그 0xd90f4c, TerrainDetailLevel 2–3, TerrainTessLevel ≠ 0일 때만 켜진다.
  - 지도 칸 함수의 두 번째 플롯 반복은 얼음·범람원 목록과 강 변 레코드만 만들고 칸은 건드리지 않는다.
- 0단계의 정적 분석은 여기까지다. 남은 열린 질문은 계획 문서 5절에 있고, 대부분 실제 게임과의 대조가 필요하다.

## 후속 메모 (Claude, 2026-11-09)

- 원본 지형 계획의 0단계 1·2를 정적으로 마쳤다. 결과는 `docs/WORLD_TERRAIN_ORIGINAL_PLAN.md` 2.2·2.3·2.5절에 정리했다. Host·게임·GPU는 쓰지 않았다.
  - 효과 레코드 배열(0x5d1e5c0, 0x520바이트)의 패스 표로 지형·FOW 셰이더의 실제 DXBC를 확정했다(`retail_terrain_pipeline_probe.json`).
  - 그중 SM5 셰이더 26개의 수식을 `fxc /dumpbin` 명령 대조로 고정했다(`terrain_shader_semantics.json`, 26/26 PASS).
    - 재질 혼합은 TerrainShaderScreen에 있고, 가중치는 확산 알파의 8제곱 × w이다.
    - CacheBake는 조명 캐시다.
    - 지형 면은 높이장 격자이며, SM5에서는 쌍삼차로 테셀레이션한다.
  - `TerrainPiecesLibrary.fxsb`를 전부 해독했다(`pieces_library_format.json`): 버전 20, 배열 4개, 조각 299개, 행 런렝스 이미지 4장.
  - `shader_disasm.py`의 명령 수 집계 오류를 고치고 색인을 다시 만들었다.
- 이어서 CPU 쪽 혼합을 정적으로 확정했다(`retail_terrain_blend_cpu_probe.json`, `pieces_id_rows.json`, 계획 문서 2.1·2.2·2.6절).
  - 처리 순서: 텍셀 ID 지도 → 5×5 커널 가중치 → 청크당 상위 8재질 → 셰이더에서 확산 알파의 8제곱 곱.
  - 조각 _T1 값과 텍셀 ID는 TerrainDef의 행 번호다.
  - BaseDominance는 읽힌 뒤 버려진다.
  - `TF_BLEND.dds`는 LayoutSystem용이고, `hexgridid`는 EXE에 이름이 없다.
- 이 시점의 남은 0단계는 2026-11-15 메모에서 갱신했다.

## 후속 메모 (Claude, 2026-11-08)

- 사용자가 "Host와 게임 실행해봐"라고 요청해서, 그 요청에 한해 실행 보류를 풀었다. 준비본 `20261108T003146Z_40a8030edf08`의 `Play.ps1`을 한 번 실행했다.
  - 새 게임 0턴에서 지도, 유닛 패널, 상단 막대가 표시되는 것과 프로세스가 응답하는 것을 확인했다.
  - 실행 기록과 자동 저장은 그 준비본의 `sessions/350dd3b9ceb408a391b5a8aa63b48301/`에 있다. 이것은 사용자 자료로 보존한다.
  - 이후 실행도 사용자가 요청할 때만 한다.
- 관찰: 정지 화면에서도 지형·유닛 프레임 로그가 계속 출력됐고, 약 11분 동안 CPU를 약 600초 썼다. 원인은 아직 조사하지 않았다.
- 사용자가 "왜 타일 그래픽이 기존 문명이랑 다르지?"라고 물었다. 원본 지형 혼합과 전장의 안개를 정적으로 분석했고, 결과와 구현 계획을 `docs/WORLD_TERRAIN_ORIGINAL_PLAN.md`에 남겼다(근거는 `evidence/world_terrain_original/`). 구현은 아직 시작하지 않았다.

## 현재 결론 — 슬라이더 마우스 오버 단계 (Claude, 2026-11-08)

사용자가 "진행해"로 남은 오프라인 항목을 이어가라고 했다. 원본 슬라이더 상태 비트를 정적으로 분석한 뒤 두 가지를 물었다. 사용자는 음량 방향키를 "원본처럼 마우스 오버만" 받기로 했고, 이전 쌍 8837/1fba는 "삭제"를 골랐다. 직전 Host `986e`를 부모로 한 번 컴파일·링크해 별도 실행 묶음까지 연결했다. Host와 게임은 실행하지 않았다.

| 항목 | 현재 값 |
|---|---|
| Host 빌드 | `20261108T002841Z_2b25aaa753e3` (부모 `20261107T120745Z_986e193d1ed1`) |
| 별도 실행 묶음 | `Build/InteractiveGameRuntime/20261108T003146Z_40a8030edf08` |
| Host SHA-256 | `59f73d19915ff2bbe9b32e0a94f8a39c2dd3fdf245bb703d876bd63126183dd9` |
| SDK SHA-256 | `430f3122d0b555d6daae14aa7c011ef43ce8f978270477c8af596ca4b0493ab9` (변경 없음) |
| 실제 컴파일 | C++14 다섯 단위, 도구 경고 0개, 실제 컴파일 시도 1회 |
| 대조한 입력 | 현재 802개·동결 802개·실제 컴파일 의존 586개 |
| 실행 묶음 | 정확히 189파일: UI 자산 154개(V4), backend 24개, Python 지원 모듈 6개 |
| 보호 대조 | 계획의 보호 파일 3,707개 중 내용·ID 변경 0개, 하드링크 수 변화 12건 |
| 용량 | 고유 할당 16,550,336,392 → 16,578,620,200바이트 (+28,283,808). 새 쌍이 늘린 양과 이전 쌍에서 회수한 79,339,824바이트를 합한 결과다 |
| 실행 횟수 | Host/SDK/창/GPU/게임 0회 |

반영 내용:

1. **음량 방향키의 마우스 오버 조건**
   - 정적 분석(`retail_slider_gate_probe.py/.json`): `.text` 전체에서 상태 비트 0x10000을 켜는 명령은 0x5f2550 하나, 끄는 명령은 0x6d3680 하나뿐이다.
   - 이 둘은 모든 컨트롤의 가상 슬롯 35/36(포인터 진입·이탈)의 기본 구현이다. Slider는 이 슬롯을 0x7641d0/0x6359b0으로 덮어쓴다. 덮어쓴 함수는 Lua 콜백 5(`Mouse.eMouseEnter`)나 6(`Mouse.eMouseExit`)을 부른 뒤, 기본 구현을 호출해 비트를 켜거나 끈다.
   - 따라서 0x10000은 포인터 오버 상태다. 원본 슬라이더의 키와 휠은 포인터가 그 위에 있을 때만 움직이며, 키보드 포커스는 조건이 아니다.
   - `MenuFrontEndOptionsModel.h`: Input에 `hover`(키 이벤트 당시 포인터 아래에 있는 컨트롤)를 추가했다. 음량 키는 `hover==KeyFor(Control::Volume)`일 때만 처리한다. 이제 Tab 포커스로는 슬라이더가 움직이지 않는다.
   - `MenuLifecycleWindow.h`는 마지막 PointerMove의 `hovered` 값을 이 `hover`로 넘긴다.
   - 남은 차이: WM_KEYUP을 컨트롤에 전달하는 UI 관리자 경로는 추적하지 않았다. 포인터 오버는 필요조건으로만 증명되었다. 또 옵션 화면이 열린 뒤 포인터가 한 번은 움직여야 hover가 잡힌다.
   - `Locale.ToPercent`(0x5f7640)는 `{1: percent}`에 double 하나를 넘기는 ICU 백분율 형식이다. 엔진 표시는 정수 퍼센트이므로 정수 값에서는 결과가 같다. 원본의 float 누적은 모형화하지 않았다.
2. **이전 쌍 8837/1fba 퇴역**
   - 참조 이전: 보상 옵션 화면 시험의 RUNTIME을 9a1a로 옮겼다. 9a1a는 1fba와 localization.db 바이트·skin 행이 같고, 해상도 미리보기 시험이 이미 쓰는 묶음이다.
   - 빌더 수정: PROTECTED_ROOTS에서 1fba를 빼고 527e를 넣었다. 부모에게서 물려받은 1fba 보호 행 189개는 `RETIRED_ROOTS`로 제외한다. 섞여 있던 줄바꿈도 CRLF로 통일했다.
   - 삭제 절차(`retire_old_pair.py`): 먼저 검토된 계획에 1fba 보호 행과 8837 언급이 없음을 확인했다. 이어서 파일 1,121개를 ID·mtime·속성·SHA-256으로 다시 대조했다. 그다음 항목 단위 FileDispositionInfoEx(DELETE|POSIX|IGNORE_READONLY)로 파일을 지우고, 디렉터리 107개를 안쪽부터 지웠다.
   - 결과: 공유 하드링크 1,067개는 이 이름 하나만 빠졌고, 읽기 전용 속성은 바꾸지 않았다. V3·V4·현재 묶음의 UIFrontEnd 파일은 각 154개 모두 여전히 읽기 전용이다. 단일 링크 파일에서 79,339,824바이트를 회수했다. 저장·세션 파일은 없었다.

부품 검사: 옵션 통합 5,515개, 보상 옵션 화면(9a1a) 10,954개, 해상도 미리보기 53,928개를 통과했다.

근거와 기록은 `evidence/game_menu/native_slider_hover/` 아래에 있다:
- `current_work.json`
- `retail_slider_gate_probe.*`
- `retirement_plan.json`, `retirement_result.json`
- `prepared_runtime_verification.json`, `protection_after.json`
- `host_build/plan_review.json`

빌드 도구는 두 개만 바꿨다: `tools/build_menu_suite_host.py`(STAGE·부모·보호 실행 묶음·RETIRED_ROOTS)와 `tools/attest_prepared_menu_host.py`(STAGE). 원본은 stage의 `source_before/`에 있고, 고정 gate `587d564e…`는 그대로다.

## 직전 결론 — 원본 규칙 후속 단계 (Claude, 2026-11-07)

사용자가 "전부 작업해"로, 기록만 해 두었던 오프라인 항목을 모두 반영하라고 지시했다. 세 항목을 반영했고, 직전 Host `b281`을 부모로 한 번 컴파일·링크해 별도 실행 묶음까지 연결했다. 검사는 파일 대조, 정적 분석, 통제 콘솔로만 했고 Host와 게임은 실행하지 않았다.

| 항목 | 현재 값 |
|---|---|
| Host 빌드 | `20261107T120745Z_986e193d1ed1` (부모 `20261106T225828Z_b281e2cf6094`) |
| 별도 실행 묶음 | `Build/InteractiveGameRuntime/20261107T121011Z_527ea94501fb` |
| Host SHA-256 | `ba7a20c4df114cec21f1ca5c4543f0738e3d4108a38bbf6e2fd85c36602b33a7` |
| SDK SHA-256 | `430f3122d0b555d6daae14aa7c011ef43ce8f978270477c8af596ca4b0493ab9` (변경 없음) |
| 실제 컴파일 | C++14 다섯 단위, 도구 경고 0개, 실제 컴파일 시도 1회 |
| 대조한 입력 | 현재 797개·동결 797개·실제 컴파일 의존 586개(새 헤더 `Source/Host/UiLocaleArguments.h` 포함) |
| 실행 묶음 | 정확히 189파일: UI 자산 154개(V4), backend 24개, Python 지원 모듈 6개 |
| 보호 대조 | 계획의 보호 파일 3,707개 중 내용·ID 변경 0개. 하드링크 수 증가 1,612건은 새 묶음의 cache 별칭이다 |
| 용량 | 고유 할당 16,444,449,576 → 16,550,057,864바이트 (+105,608,288). 확인된 폐기 가능량 0 |
| 실행 횟수 | Host/SDK/창/GPU/게임 0회 |

반영 내용:

1. **WindowTrim V4**
   - 원본 Image는 StretchMode가 없으면 Size 픽셀을 TextureOffset부터 1:1로 그린다(`evidence/game_menu/frontend_windowtrim/`).
   - `tools/menu_frontend_assets_v4.py`가 이 규칙으로 V3에서 `Source/Assets/UIFrontEndV4`를 만든다. 스프라이트는 MainMenu 114·116, SinglePlayer 117·119이며, 원본 영역은 (0,0)-(82,394)이고 대상 영역은 82×394이다.
   - 바뀐 packet은 2개이고, 나머지 152개는 V3의 하드링크다. V3와 그 목록(`eb5408e1…`)은 그대로 보존했다.
   - 그림 밖 아래 2줄은 원본 sampler·FTXT 결과가 미확정이므로 그리지 않는다.
   - CPU 대조 결과, 페이지마다 바뀐 픽셀 45,305개가 모두 WindowTrim 안에 있었고 밖의 변화는 0개였다.
   - V3를 쓰던 시험 5개(격자·옵션 통합·리플레이 복원·보상 옵션 화면·해상도 미리보기)는 V4와 목록 `dbd8c092…`로 옮겼다.
2. **옵션 음량 슬라이더**
   - 소매 Slider 메시지 처리부 0x5e03e0을 정적 분석했다(`native_offline_followup/retail_slider_key_probe.py/.json`).
   - 키 분기로 들어가는 메시지는 WM_KEYUP(0x101)뿐이다. VK_LEFT/VK_UP은 줄이고 VK_RIGHT/VK_DOWN은 늘리며, 한 번에 `1/(100/WheelSteps)`만큼 움직인다. Home/End와 수정키는 처리하지 않는다.
   - `OptionsMenu.xml`의 EffectsVolumeSlider는 WheelSteps="1"이므로 한 단계는 1%이다.
   - `MenuFrontEndOptionsModel.h`에서 반대로 되어 있던 ↑/↓ 방향을 고쳤고, 엔진 확장이던 Shift ×10과 Home/End를 없앴다. 휠은 메시지당 한 단계이며 원래부터 원본 방향이었다.
   - 남은 차이: 소매는 키를 뗄 때 움직이지만, 엔진 창은 자동 반복을 뺀 첫 WM_KEYDOWN에서 움직인다. 한 번 누르면 한 단계인 것은 같다. key-up 대기열을 만들려면 모든 화면이 공유하는 BitmapWindow를 바꿔야 하고 HWND 없이는 검증할 수 없어서 보류했다.
3. **Locale 인자**
   - 소매 `Locale.Lookup`/`ConvertTextKey`는 인자를 boolean→`PushArgument(int)`, number→`PushArgument(double)`, string→`PushArgument(const char*)`로 넘긴다.
   - 새 `Source/Host/UiLocaleArguments.h`의 `PushRetailLocaleArgument`가 같은 분기를 하고, `UiPopupContext::Localize`가 이것을 쓴다.
   - 불리언은 이제 오류가 아니라 1/0으로 넘어간다. 정수 값 숫자도 double로 넘긴다.
   - 그대로 둔 것: 문자열 인자의 Host 키 조회와 NUL 거부, 비유한 숫자 거부.

근거와 기록은 `evidence/game_menu/native_offline_followup/` 아래에 있다.
- `current_work.json`(현재 상태와 남은 범위), `retail_slider_key_probe.*`
- `frontend_v4/assets_v4.json`, `frontend_v4_render_check.*`
- `locale_arguments/f97c66d003e8d605/result.json`
- `prepared_runtime_verification.json`, `protection_after.json`, `prune_evaluation.json`, `host_build/plan_review.json`

부품 검사는 모두 V4로 통과했다: Locale 인자 20개, 옵션 통합 5,510개, 격자 77,411개, 리플레이 복원 320,992개, 보상 옵션 화면 10,954개, 해상도 미리보기 53,928개.

빌드 도구는 두 개만 바꿨다: `tools/build_menu_suite_host.py`(STAGE·부모 상수, 보호 실행 묶음에 48d9 추가)와 `tools/attest_prepared_menu_host.py`(STAGE). 원본은 stage의 `source_before/`에 gzip으로 있다. 고정 gate `587d564e…`는 그대로다.

정리 판단 — 이전 쌍 `8837`/`1fba`는 이 단계에서는 삭제하지 않았다(다음 단계에서 사용자 결정으로 퇴역: 위 현재 결론).
- 저장·세션 파일이 없고, 회수 가능한 단일 링크 할당은 79,339,824바이트뿐이다.
- 봉인된 현재 소스 두 개가 1fba를 참조한다: 빌더 PROTECTED_ROOTS와 `Tests/menu_reward_options_view.py`의 RUNTIME. 이번 계획의 보호 목록에도 1fba가 들어 있다. 지금 지우면 현재 소스와 동결 입력의 일치가 깨진다.
- 다음 빌드 단계를 시작할 때 처리한다. 먼저 보상 화면 시험을 같은 localization.db를 가진 현재 묶음으로 옮긴다. 다음으로 PROTECTED_ROOTS에서 1fba를 뺀다. 그다음 typed 계획으로 두 폴더를 퇴역한다(`prune_evaluation.json`).

## 이전 결론 — 리플레이 계절 키·휠 단계 (Claude, 2026-11-07)

사용자가 "오프라인 잔여 소항목"을 지시했다. 그중 원본 근거가 확보된 두 항목을 반영하고, 직전 Host `0f1d`를 부모로 한 번 컴파일·링크해 별도 실행 묶음까지 연결했다. 파일 전용 검사만 했으며 Host·게임은 실행하지 않았다.

| 항목 | 현재 값 |
|---|---|
| Host 빌드 | `20261106T225828Z_b281e2cf6094` (부모 `20261106T134645Z_0f1da0168223`) |
| 별도 실행 묶음 | `Build/InteractiveGameRuntime/20261106T230144Z_48d9fd363237` |
| Host SHA-256 | `47eb201e1b9d9004b3b724ae5b0399dcce433a1b640f09b3877b9920a52de1a2` |
| SDK SHA-256 | `430f3122d0b555d6daae14aa7c011ef43ce8f978270477c8af596ca4b0493ab9` (변경 없음) |
| 실제 컴파일 | C++14 다섯 단위, 도구 경고 0개, 실제 컴파일 시도 1회 |
| 대조한 입력 | 현재 780개·동결 780개·실제 컴파일 의존 585개 |
| 실행 묶음 | 정확히 189파일, UI 자산154, backend24, Python 지원 모듈6 |
| 보호 대조 | 계획의 보호 파일 3,518개 내용·ID 변경 0, 하드링크 수 증가 1,456건(새 묶음의 cache 별칭) |
| 실행 횟수 | Host/SDK/창/GPU/게임 0회 |

반영 내용:

1. **계절 날짜**: 소매 `CivilizationV_DX11.exe`(SHA `b7c8977e…`)의 Lua `Locale.Lookup`(0x5cc8d0)은 존재 검사 없이 `Localization::Lookup`을 부르고, 원본 지역화 추적(`evidence/localization/reference/basic.log` 11행)은 없는 키에 키 자체를 돌려준다. 따라서 원본 리플레이는 `TXT_KEY_SEASON_WINTER, 3999 BC`처럼 원시 키를 보인다. `HostRun.h`는 Lookup 결과를 그대로 쓰고, `MenuReplayCalendar.h`의 월/계절 이름 검사는 빈 문자열·NUL·길이만 거부한다. 숫자 템플릿 검사는 바꾸지 않았다.
2. **TurnSlider 휠**: 소매 슬라이더 WM_MOUSEWHEEL(0x5e0832)은 메시지마다 float32 `1/(100/WheelSteps)`만큼 움직인다. 방향은 `HIWORD>0`이면 감소, 아니면 증가이며, 0x7af7c0에서 [0,1]로 고정한 뒤 콜백을 부른다. `SliderControl::SetValue`(0x7af7c0)는 콜백 없이 저장하고, 콜백 경로 `SetAndCall`(0x481330)은 따로 있다. ReplayViewer는 매번 SetValue로 턴 비율을 다시 넣으므로, 엔진은 현재 턴의 float 비율에서 한 단계를 움직이고 원본 floor로 턴을 정한다. 결과적으로 길이 10턴 미만의 리플레이는 앞으로 굴려도 그대로이며, 이것은 원본 동작이라 고치지 않았다.
   - 원본의 상태 비트 0x10000 의미는 미확정이다. 엔진은 슬라이더 사각형 위의 휠만 받는다.

근거와 기록: `evidence/game_menu/replay_season_wheel/`의 `current_work.json`(현재 상태·남은 범위), `retail_static_probe.py/.json`(재현 가능한 정적 분석, 실행 없음), `prepared_runtime_verification.json`, `protection_after.json`, `host_build/plan_review_final.json`. 부품 검사: 달력 28,280개, 스크롤 모델 107,570개(휠 골든 7,674건), 복원 장면 320,992개 통과.

이번 단계에서 바꾼 빌드 도구는 `tools/build_menu_suite_host.py`(STAGE·부모·보호 실행 묶음 상수)와 `tools/attest_prepared_menu_host.py`(STAGE)뿐이며, 원본은 stage의 `source_before/`에 gzip으로 있다. 고정 gate `587d564e…`는 그대로다. `calendar`·`scroll_model` 부품 영수증은 덮어쓰기 전 원본을 보관했다. 이전 쌍 `8837`/`1fba`는 이제 두 단계 전이며 정리 후보로만 기록했고 삭제하지 않았다. 확인된 폐기 가능량은 0이다.

WindowTrim(2026-11-07 후속, 기록만): 소매 EXE 정적 분석으로 원본 동작을 확인했다(`evidence/game_menu/frontend_windowtrim/`).
- XML `Image` 태그는 factory 0x72eb80과 생성자 0x503430으로 만들어지며, StretchMode 기본값은 0이다.
- StretchMode 0이면 Size 픽셀을 TextureOffset부터 1:1로 샘플한다. UV는 `오프셋/텍스처 크기 .. (오프셋+Size)/텍스처 크기`이며 전체 그림을 Size로 축소하지 않는다.
- 그 결과 활성 BNW 그림 98×394가 82열로 잘리고(불투명 텍셀 445/438개가 보이지 않음), 아래 2줄은 그림 밖을 읽는다. G&K 자체 그림은 82×395였다. 그림 밖 2줄의 sampler 주소 모드와 FTXT 타일 셰이더 결과는 미확정이다.
- 사용자 결정에 따라 그때는 V3 묶음과 준비본을 바꾸지 않았다. 이후 "원본 규칙 후속 단계"에서 V4 묶음으로 반영했다(위 현재 결론).

프로젝트:

`C:\Users\home\OneDrive\Documents\Firaxis ModBuddy\ZeroSis' Engine Modernization`

이하 상대 경로는 이 프로젝트 기준이다.

## 그 이전 결론 — 보상 알림 단계 (Codex, 2026-11-06)

**보상 알림 옵션의 최종 소스를 새 x64 Host로 실제 컴파일·링크하고, 기존 SDK 및 UI 자산과 별도 실행 묶음으로 연결했다.** 파일 전용 독립 검사를 통과했으며 게임은 실행하지 않았다.

| 항목 | 당시 값 |
|---|---|
| Host 빌드 | `20261106T134645Z_0f1da0168223` |
| 별도 실행 묶음 | `Build/InteractiveGameRuntime/20261106T135115Z_e38cb351eca4` |
| Host SHA-256 | `717cfa2abcd4d992d4f9a5bcef275f1a60e5396f6086dde0c06559082d21d4da` |
| SDK SHA-256 | `430f3122d0b555d6daae14aa7c011ef43ce8f978270477c8af596ca4b0493ab9` |
| 실제 컴파일 | C++14 다섯 단위, 도구 경고 0개 |
| 대조한 입력 | 현재 772개·동결 772개·실제 컴파일 의존 585개 |
| 실행 묶음 | 정확히 189파일, UI 자산154, backend24, Python 지원 모듈6 |
| 실행 횟수 | Host/SDK/창/GPU/게임 0회 |
| 기본 실행·전역 등록 | 변경하지 않음; explicit prepared profile만 생성 |
| 저장 제한 | 새 게임 전용; 다른 묶음의 저장 불러오기 금지 |

## 보상 알림 단계의 기록

해당 stage는 `evidence/game_menu/options_reward_popups/`이다.

- 현재 상태·정리·용량·남은 범위: `current_work.json`
- 완성된 묶음 대조: `prepared_runtime_verification.json`
- 실제 빌드: `evidence/ui_window_host/20261106T134645Z_0f1da0168223/build_result.json`
- 독립 PE/소스 검사·정확한 오브젝트 정리·봉인 프로필: `pair_preparation/20261106T134645Z_0f1da0168223/`
- 현재 Host 소스 계획: `host_build/reviewed.final.plan.json`
- 현재 소스 메타데이터 목록: `host_build/source_manifest_final.json`
- 기존 규칙 모듈 연결 결과: `evidence/game_menu/menu_runtime_ui_followup/pair_preparation/20261106T134645Z_0f1da0168223/materialization/result.json`

첫 file-only 계획은 컴파일 전 정리 검사부의 좁은 수정 때문에 퇴역했다. `host_build/unapplied_plan_superseded.json`과 압축 계획이 근거다. **그 계획을 실행하거나 이미 끝난 최종 계획을 다시 실행하지 않는다.** 실제 컴파일 시도는 한 번이다.

## 유지해야 할 사용자 범위

- 전체 목표는 문명 5의 기존 UI를 유지하는 64비트·멀티코어 엔진 개조다. 옵션 한 개·컴파일 성공을 전체 목표 완료로 바꾸지 않는다.
- Codex의 전체 자동 목표는 사용자가 일시 중단한 상태이며, 이후 재개 요청은 우선 빌드 연동 범위였다. 추가 작업은 사용자의 위임 범위에 맞춘다.
- **실게임과 화면 확인은 별도 보류 중이다.** 새 Host, GameCore DLL, CLR, HWND, GPU, 음향 장치, 실제 게임을 임의 실행하지 않는다.
- 파일 대조, 정적 분석, 실제 컴파일/링크, SDK 없는 통제 콘솔과 기존 Lua 5.1 제공자의 통제 검사가 기존 허용 범위였다.
- 원본 문명·MODS·원본 설정·사용자 저장·기본 실행본·전역 등록은 변경하지 않았다.
- 작업 공간과 프로젝트의 AGENTS.md를 읽는다. `.git`은 읽기 전용이다. 전체 프로젝트 사본 대신 변경 파일 백업과 기존 입력 경로를 재사용한다.
- 폐기 가능한 반복 빌드·실패 시험본·임시 파일은 수시로 정리하고, 실제 점유량이 10GiB를 초과하면 다음 큰 빌드 전에 정리한다. 사용자 자료·유일한 복구 자료로 한도를 맞추지 않는다.

## 이번 소스의 중요한 계약

1. `MenuOptionsContract.h`/`MenuOptionsStore.h`: 새 `noRewardPopups=false`. 기존 V1/V2는 해당 버전의 canonical 비교로 읽고 파일을 쓰지 않는다. 변경값을 명시적으로 확정한 경우에만 V3을 원자 기록하며 기존 순서를 보존하고 `policyInfo` 뒤에 새 키를 추가한다. 마이그레이션 계획은 `migration_plan.json`에 있다. GameCore 저장/Mod 스키마 이전이 아니다.
2. `HostServices.h`/`MenuOptionsHostBinding.h`: 적용 임시값과 SDK가 읽는 확정 원자 셀을 분리한다. `BindNoRewardPopupsSnapshot`은 정상·비활성·소유 스레드에서 한 번 연결한다. 저장 성공 및 committed 대입 뒤 noexcept release-store하며 SDK getter는 acquire-load만 한다. 캐시·취소·저장 실패·별도 해상도 미리보기는 초안을 발행하지 않는다.
3. `MenuFrontEndOptionsModel.h`/`MenuFrontEndOptionsView.h`/`MenuRewardOptionsLayout.h`: 기존 ID 유지, 새 컨트롤17. 원본 보상 알림→기본 도움말 순서와15px 간격. 32px 체크 상자는 기존 후보 계약이며 원본 네이티브 기본 크기 실증값이 아니다. 기존20초 해상도 확인·부분 확정·취소·자동 복귀를 유지한다.
4. `UiMenuOptions.lua`와 관련 도구: 원본 체크 콜백을 재사용하고 전체 원본 OptionsMenu를 실행하지 않는다. 지원 항목8개, private key9개(별도 터치 도움말 포함), V3 provenance/입력 검사부를 함께 맞췄다. Game 탭은 보상 알림/기본 도움말 지원의 합집합이다.
5. 실제 임베드 Lua 검사에서 `Popup` 이름 필터가 `NoRewardPopupsCheckbox`까지 숨기는 결함을 발견했다. **해당 ID·CheckBox 형식·지원true가 모두 맞는 항목만 예외**로 고쳤다. 미지원 팝업은 계속 숨긴다.
6. SDK430의 유적·기술·불가사의·자연경관·걸작 다섯 소비 소스는 실제 DLL의 유효 빌드 입력 SHA와 일치한다. SDK 규칙·보상 수치·DLL을 수정하지 않았다.

최종 Lua SHA는 `b75f00e5476cb7f9545187215d5b777414bb05dd66ba5bc02ae2b74dde684f19`, 최종 generated header SHA는 `561af68d28ab76236c68f34b8605d0cd9bac83d89fc1f032cae523bfe8172e16`이다.

현재 임베드 근거는 `embedded_options_revision2.result.json`이다. 최초 원본 대비74개 payload 중3개만 바뀌었고 나머지71개·음향 registry tail·공유 글꼴은 보존했다. 첫 `embedded_options.result.json`과 `independent_source_review.json`은 수정 전 역사 기록이며, 최종 리뷰는 **`independent_source_review_final.json`**이다.

## 부품 검사와 정리

- `contract/delivery.json`: 5,563개 통과, V1/V2 읽기 보존·V3 이전·원자 셀·기존20초 흐름.
- `view/delivery.json`: 10,954개 통과, 경고0, V3 자산154개 불변. `view/attempt02/cpu_reward_game.png`는 한 번 시각 확인한 CPU 진단 이미지이며 실제 인게임 화면이 아니다.
- `integration/db7b393d669f766e/result.json`: 본체 메뉴 통합5,500개 통과.
- `binding/delivery.json` 및 `binding/4d2aac9a11814351/result.json`: 실제 getter 형식 CPP33개·기존연결26개·실제 임베드 Lua295개·snapshot 계약7개와 잘못된 계약3개 거부. 통제 콘솔의 의존 DLL은 KERNEL32뿐이다.
- `component_cleanup.json`: 이번 부품 삭제133사건을 중복 제거했고, 실패 콘솔5개 퇴역/최신제품9개 및 미분류 옛보조3개 보존/임시 잔여0을 확인했다. 앞선 wave의59사건을 다시 회수량에 포함하지 않았다.
- 새 Host의 오브젝트5개와 환경 명령 파일1개는 독립 검사 뒤 별도로 정리했다. 새 실행 파일·map·필요한 동결 입력·프로필은 보존했다.
- 기존 하드링크 검사 중 생성 단계의 Win32 오류5로 실행되지 않은 분기가 있다. 미검증 한계를 통과로 바꾸지 않는다.
- `Build/MenuFrontEndComponent/current`, `Build/MenuOptionsComponent/current`, `Build/MenuOptionsFollowup/current`는 용도 미분류라 보존했다.
- 8837/1fba는 당시 직전 검증 준비본으로 보존했다(이후 "슬라이더 마우스 오버 단계"에서 퇴역). 기본732·사용자cbbd 저장·등록Host4·필요한 최근/복구 입력은 보호 목록을 따른다.

실제 할당량은 `current_work.json`의 storage와 `storage_before.json`/`storage_after.json`을 읽는다. 파일 ID 중복을 제거하며 볼륨 여유 공간·하드링크 중복 논리 크기·실제 할당을 혼동하지 않는다. 삭제한 대용량 파일을 증거용으로 재복사하지 않는다. `.codex`의 세션/내부 DB는 이 작업의 정리 대상이 아니다.

## 이후의 미완료 범위

원본 전체 옵션/메뉴, 원본3D·렌더링, 실제 인게임 입력/턴, 저장과 별도 프로세스 복원, 기존 문명 저장/모드 호환성, 멀티코어 안정성, 실제 UI/글꼴/화면 전환 동등성은 완료되지 않았다. 일부 재생 화면도 단순화 상태다. 현행 `evidence/game_menu/native_slider_hover/current_work.json`의 `remaining`을 읽고 사용자 위임 범위 안에서 이어간다. 이미 끝난 빌드 연동을 반복해 개발 진척으로 세지 않는다.
