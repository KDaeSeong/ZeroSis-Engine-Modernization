# Claude 작업 분담 — 원본 곡면·카메라·숲

작성 기준: 2026-11-16, 11단계 파일 전용 연동 완료 상태.

## 목적과 담당 경계

전체 목표는 원본 문명 5의 UI와 게임 진행을 유지하는 64비트·멀티코어 엔진이다. 이번 Claude 담당은 남은 목록 **4번의 원본 입력 추적과 독립 계산 부품**이다. 기존 계산 부품을 다시 만드는 작업이 아니다. 아직 확보하지 못한 원본 값을 확인하여 실제 렌더 연결에 필요한 근거를 제공한다.

| 담당 | 범위 |
|---|---|
| Claude | 원본 곡면 기저·패치 배율, 세계 카메라 값, 숲 GR2 해독·배치 규칙의 정적 추적과 별도 CPU 부품 |
| Codex | 2번 캐시·높이 보정, 3번 물·반사 구현, 공통 렌더러·Host 연동, 통합 빌드·격리 묶음·현재 진척 기록 |

이는 파일 충돌을 피하기 위한 분담이다. Claude는 기존 Source/Tests/도구/진척 문서를 직접 수정하지 않고, 별도 근거·부품·패치 제안으로 전달한다. Codex가 검토하여 공통 코드에 반영한다. 별도 새 카메라의 모양이나 임의 나무로 원본을 대체하지 않는다.

## 먼저 읽을 자료

작업 공간은 `C:\Users\home\OneDrive\Documents\Firaxis ModBuddy`이고, 프로젝트는 그 아래 `ZeroSis' Engine Modernization`이다. 아래 경로는 프로젝트 기준이다.

1. 작업 공간과 프로젝트의 `AGENTS.md`.
2. 이 문서와 `docs/CLAUDE_HANDOFF.md` 맨 위의 최신 기록.
3. `evidence/world_terrain_original/phase11/runtime_integration/current_work.json` — 현재 준비 묶음과 보류 조건.
4. `docs/TERRAIN_OFFLINE_PHASE10.md`, `docs/WORLD_TERRAIN_ORIGINAL_PLAN.md`의 2.5–2.9절 및 5절.
5. `evidence/world_terrain_original/phase10/geometry/`의 아래 자료.

현재 기준은 Host `20261116T114748Z_014dd63ad3bc`, 격리 묶음 `20261116T123457Z_90b98a574efc`, SDK430이다. 파일 연동 검증만 통과했으며 실게임·화면 수락은 아니다. 과거 단계의 기록과 충돌하면 최신 정정 근거를 따른다.

## 우선순위와 완료 조건

### A. 곡면 기저와 패치 입력 — 먼저 진행

- 원본 `TerrainShader`의 `cb1[10..13]`에 실제 올라가는 16개 기저 값을 추적한다. B-스플라인·Catmull-Rom·Bezier 중 하나를 관행만으로 선택하지 않는다.
- 상수의 출처 → 계산/메모리 배치 → 버퍼 갱신 → HS/DS 소비를 주소와 바이트 해시로 연결한다.
- 가능하면 패치 제어점 순서, 위치·높이 단위, 패치 간격·배율도 같은 방식으로 확정한다. 기저 값과 세계 배율의 확정 여부는 각각 구분한다.
- 기존 `OriginalTerrainTessellationModel.h`와 `OriginalTerrainTessellationShader.h`는 명시 기저 입력의 계산 부품이다. 실제 원본 기저가 확인된 것으로 취급하지 않는다.

참조:

- `evidence/world_terrain_original/phase10/geometry/geometry_probe.json`
- `evidence/world_terrain_original/phase10/geometry/TerrainShader_0_hs.asm.txt`
- `evidence/world_terrain_original/phase10/geometry/TerrainShader_0_ds.asm.txt`
- `evidence/world_terrain_original/retail_terrain_pipeline_probe.json`
- `Source/Presentation/OriginalTerrainTessellationModel.h`
- `Source/Presentation/OriginalTerrainTessellationShader.h`

완료 기준은 실제 업로드 값과 경로를 재현 가능한 정적 근거로 제시하는 것이다. 독립 계산 검사는 상수 면·평면·곡면·패치 경계와 미탐색 제어점 거부를 다룬다. 기존 검사가 명시적으로 넣은 Bezier 기저는 원본의 증거가 아니다.

### B. 실제 세계 카메라 — A 다음 진행

- 일반 카메라 계산 함수가 아닌 실제 세계 화면에서 사용하는 인스턴스와 호출 경로를 찾는다.
- 자세·시야각·가까운/먼 클립 평면·확대 곡선·지도/세계 단위를 추적한다. 축과 행렬의 좌우수계 변환도 근거로 구분한다.
- 원본의 일반 RH 투영/LookAt 연산과 도→라디안 변환은 이미 확인됐다. 일반 초기화의 near=1/far=10000을 실제 세계 화면의 값으로 단정하지 않는다.
- 물의 반사 투영 카메라와 세계 카메라는 같은 대상이라고 가정하지 않는다. 반사 관련 발견은 Codex에게 주소·근거로 전달하고 담당 파일은 수정하지 않는다.

참조:

- `evidence/world_terrain_original/phase10/geometry/camera_retail_contract.json`
- `Source/Presentation/OriginalCameraModel.h`
- `Source/Presentation/WorldCameraControls.h`
- `Source/Presentation/WorldTerrainRenderer.cpp` — 읽기 전용, 현재 시점은 보정 후보.

완료 기준은 확인한 실제 호출값과 미확정 보정값을 분리하여 연결 가능한 입력 계약을 제시하는 것이다. CPU 행렬 검사가 원본 화면과의 일치를 증명하지는 않는다.

### C. 숲 모델 해독과 배치 — A/B 뒤의 작업

- 선택된 원본 GR2의 압축 형식2를 파일만으로 해독할 수 있는지 조사한다. 가능하면 별도의 bounded CPU 판독/해독 부품과 독립 검사를 만든다.
- 정점·색인·UV·인스턴스 입력과 원본 나무 배치의 난수/간격/마스크 사용을 각각 추적한다.
- 원본 마스크의 nonzero 비율은 이미 집계됐으나 배치 임계값은 확정되지 않았다. XML 주석의 '200의 배수' 문구로 실제 값360을 수정하지 않는다.
- 현재 확인된 설정은 타일 텍스처4개, random360, grid0, overlay0.6, spacing1.33이다. 기존 숲 계산 부품은 90개 인스턴스와 색 수식까지만 검증돼 있다.
- 파일만으로 해독하지 못한 경우 필요한 알고리즘/자료와 막힌 위치를 기록한다. SDK DLL 실행이나 임의 모델 대체로 우회하지 않는다.

참조:

- `evidence/world_terrain_original/phase10/geometry/forest_assets_contract.json`
- `evidence/world_terrain_original/phase10/geometry/ForestShader_0_vs.asm.txt`
- `evidence/world_terrain_original/phase10/geometry/ForestShader_0_ps.asm.txt`
- `Source/Presentation/OriginalForestModel.h`
- `Source/Presentation/OriginalForestShader.h`
- `Tests/original_forest_tessellation.cpp`, `Tests/original_forest_tessellation.py`

완료 기준은 선택 원본 SHA에 묶인 판독 결과와 잘못된 입력·범위 초과·미탐색 입력을 거부하는 검사다. 숲 전체가 복원됐다는 보고에는 모델·배치·재질·실제 화면의 검증 수준을 구분한다.

## 쓰기 가능한 담당 산출물

Claude의 작업물은 `evidence/world_terrain_original/claude_geometry/` 아래에만 작성한다.

- `findings.json`: 각 주장에 `confirmed`/`candidate`/`unknown`, 입력 SHA, 주소·원본 바이트 또는 셰이더 명령 근거, 한계를 기록.
- 파일 전용 재현 스크립트와 새 CPU 부품·검사. 기존 판독기와 원본 자산 경로를 재사용한다.
- `proposed_changes.patch`: 필요한 기존 코드 변경 제안. 직접 적용하지 않는다.
- `HANDOFF_RESULT.md`: 확보한 값, 미확정 항목, 변경 제안 파일, API/단위 계약, 실제 검사 명령·결과, 정리 내역.

현재 폴더의 `assignment.json`은 분담 기준이므로 읽기 전용으로 둔다. 이전 `phase*` 근거와 출력은 덮어쓰지 않는다. 보존할 결과가 있으면 작은 별도 결과로 추가한다.

Codex 전담 파일: 공통 Renderer/GPU/Targets `.cpp`·`.inc`, `Source/Host/InteractiveGameLoop.h`, 실행 묶음/캐시/준비·정리 도구, `docs/CLAUDE_HANDOFF.md`, 원본 계획과 현재 진척 JSON. 기존 모델·셰이더·검사 파일도 Claude는 읽기 전용 참조로 사용한다.

## 실행·보존·보고 조건

- **Host, GameCore DLL, 프로젝트 CLR, GrannyBridge/SDK DLL, HWND, GPU, 음향 장치와 실제 게임을 실행하거나 로드하지 않는다.** Play/Resume도 호출하지 않는다.
- 파일 전용 Python, 고정 원본 PE/DXBC 정적 판독, FXC 컴파일/역어셈블, 그래픽·SDK를 사용하지 않는 통제 CPU 검사와 컴파일·링크까지 허용한다. 추가 패키지 설치 없이 기존 판독기와 만들어 둔 JSON을 우선 재사용한다.
- 새 CPU 부품은 가능한 C++14 `/O2 /MT /W4 /WX /fp:strict`로 검사한다. 구현을 그대로 복제한 기대값 대신 원본 명령·별도 수학식·독립 기준을 사용한다.
- 타일 선택 ID는 `R32_UINT`의 정확한 타일 값이다. 색 혼합이나 곡면 연결로 바꾸지 않는다. 미탐색 제어점·재질·모델 입력은 사용 전에 차단한다.
- 원본 설치·MODS·설정·사용자 저장·기본 실행·전역 등록·기존 저장 키/ABI를 변경하지 않는다.
- 전체 프로젝트·FPK·자산 묶음을 복제하지 않는다. 필요한 소량의 범위만 RAM 또는 작은 파일로 읽고 기존 6팩은 재사용한다. 변경되지 않은 모델·텍스처를 중복 보관하지 않는다.
- 검사 후 재생성 가능한 임시 산출물은 의존성을 확인하고 정확한 경로·파일 ID·크기·SHA·처리 결과를 남겨 정리한다. 공유 하드링크의 속성을 변경하지 않으며 용도 불명인 옛 자료는 삭제하지 않는다.
- **조각 배치는 '규칙 동등, 배치 동등은 미검증'**으로 보고한다. CPU/컴파일 PASS를 원본 화면·배치·실게임·성능 동등성으로 표현하지 않는다.
- 소스 주석과 내부 메시지는 일반 기술 문체로 작성한다.

## 이미 교정한 원본 규칙 — 되돌리지 말 것

- 지형 최종 t9는 정적 `specscreenmap.dds`의 UNORM/CLAMP 입력이다. 물의 동적 Raw 반사와 다르다. 과거 phase8의 t9=Raw 해석은 객체 기준 주소의 8바이트 차이를 빠뜨린 오류로 폐기됐다.
- 물 Raw 반사는 UNORM/WRAP이다. 원본 Raw 콜백은 유닛·불가사의·지형 시설·얼음이며 지형·숲을 임의로 포함하지 않는다.
- 조각 방향은 행 벡터의 `T * R(0) * Mirror`로 교정됐다. 방향 행렬이 아직 미확정이라는 과거 설명을 재사용하지 않는다.
- 원본 공유 scratch 품질128/256/512와 전체 밉 계약은 확인됐다. 현재 청크별68/66 halo와 같은 기하라는 증거는 없으므로 단순 크기 치환을 하지 않는다.
- 최신 단계11의 실행 묶음 연동은 끝났다. 이것을 남은 작업으로 다시 만들지 않는다.
