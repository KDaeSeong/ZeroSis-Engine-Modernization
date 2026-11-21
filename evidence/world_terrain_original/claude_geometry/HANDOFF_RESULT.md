# Claude 인계 결과 — 원본 곡면·카메라·숲

기준일 2026-11-16. 분담 문서 `docs/CLAUDE_WORK_ASSIGNMENT.md`의 A는 완료, B는 단서 수집 단계, C는 시작하지 않았다.
Host·GameCore·프로젝트 CLR·SDK DLL·창·GPU·음향·실제 게임은 실행하지 않았다. 기존 Source/Tests/도구/문서는 수정하지 않았다.
조각 배치는 **규칙 동등, 배치 동등은 미검증**이다.

## A. 곡면 기저와 패치 입력 — 확보한 값

입력: `CivilizationV_DX11.exe` SHA-256 `b7c8977ebab33ba6c1abf65d63fa310f8d096341465e0fc419f1b4da0fcd8818`, 이미지 기준 0x400000.

| 항목 | 값 | 수준 |
|---|---|---|
| `cb1[10..13]` | (1/8)·[[-1,7,-7,1],[3,-12,9,0],[-3,0,3,0],[1,6,1,0]] — 행은 t³·t²·t·1, 열은 제어점 0..3 | confirmed |
| 기저의 종류 | Mitchell–Netravali B=3/4, C=0. 균등 B-스플라인·Catmull-Rom·Bezier가 아니다 | confirmed |
| 제어점 색인 | `(py+r+2)<<8 \| (px+c+2)`, c가 먼저 증가. VS는 `(id&255)-3`, `(id>>8)-3`로 푼다. 제어점 5가 패치 원점, u는 c, v는 r 방향 | confirmed |
| 패치 순서·단계 | 행(py) 바깥, 열(px) 안쪽. 다섯 단계, 단계마다 n=(n>>1)+1 | confirmed |
| 높이 단위 | 제어 높이 = 높이 텍스처 알파 × 0.2 × 255 (알파 1에서 51) | confirmed |
| 수평 단위 | 월드 xy = 높이 텍셀 × (1.0, 0.866). 0.866은 0x3f5db22d이며 √3/2가 아니다 | confirmed |
| 분할 계수 | `cb1[14].x` = 설정 `BicubicTerrainTessSubdiv`(0xd90f14)에서 온 정수, 디버그 조작 범위 1..16, 정수 분할 | confirmed (설정 파일의 실제 값은 미확인) |
| 패치 사용 조건 | `BicubicTerrainTessellation`(0xd90f1c)≠0, `TerrainTessLevel`≠0, 장치 등급≥10 | confirmed |
| 그리기별 `cb0[4..6]` 배치 | [4]=셀 정수 4개, [5].xy=1/(W+1),1/(H+1), [6].xy=(W-1)/(W단계-1), [6].z=높이 밉 단계 | 배치 confirmed, 실제 W·H·원점 값은 candidate |
| `cb0[0..3]` 이동 행렬의 원천 | 객체 +0x1ab0.. 필드 형 해석이 두 곳에서 다르다 | unknown |

경로: 리터럴 9개(0x6add87–0x6ade3a) → 스택 영상 → 블록 얻기 0x6be670(크기 0x250) → 복사(0x6adf21–0x6adfcd, 블록 +0xa0..+0xdc) → DS의 `mul/mad cb1[11], cb1[10], cb1[12]`, `add cb1[13]`, `dp4` 연쇄. 색인은 0x6c9c00, 그리기별 상수는 0x5c37e0.

성질: 가중치 합은 1, C1 연속이다. 제어점을 지나지 않는다(t=0 가중치 1/8, 6/8, 1/8). 선형 재현이 없다 — 제어값 (-1,0,1,2)의 결과는 `-t³/2 + 3t²/4 + 3t/4`다. 따라서 "평면은 평면으로 나온다"를 검사 기준으로 쓰면 안 된다.

Codex 참고: 1단계 후보였던 높이 배율 2.3과 기준 15300/65535는 이 값(알파×0.2×255, 헥스당 높이 텍셀 64)과 대조할 필요가 있다. 같은 `cb1[16].z`를 비테셀레이션 패스도 쓴다.

## 파일

| 파일 | 내용 |
|---|---|
| `basis_retail_probe.py` / `.json` | 표준 라이브러리만 쓰는 정적 프로브. 구간 12개 SHA 고정, 스택 영상·복사 해독, 색인 규칙, 셰이더 목록 대조 |
| `OriginalTerrainBicubicRetail.h` | 독립 CPU 부품(네임스페이스 `ZeroSisClaudeGeometry::TerrainBicubicRetail`). 기저, 색인 부호화/해독, 단계 크기, DS 연산 순서 평가, 미탐색 제어점 거부, 단위 |
| `original_terrain_bicubic_retail_test.cpp` | 독립 기준 검사. 기대값은 배정밀도 Mitchell–Netravali 커널, 닫힌 식, 리터럴 색인 |
| `run_bicubic_cpu_check.py` | MSVC C++14 `/O2`·`/Od` `/W4 /WX /fp:strict /MT` 컴파일·링크·실행, KERNEL32 전용 확인, 임시물 정리 |
| `bicubic_cpu_attempt01/result.json` | 위 실행 결과 |
| `proposed_changes.patch` | `OriginalTerrainTessellationModel.h`에 `RetailBasis()`를 추가하는 제안. 적용하지 않았다 |
| `findings.json` | 주장별 수준·근거·한계 |

## API·단위 계약 (부품)

- `RetailBasis()` — `basis[k][i]`: k=0..3은 t³,t²,t,1, i는 제어점. 기존 `OriginalTerrainTessellation::Basis`와 같은 배치다.
- `Heights[r*4+c]` — c는 x(도메인 u), r은 y(도메인 v). 패치는 제어점 1과 2 사이 한 간격이다.
- `EvaluateKnown` — 16칸 가운데 하나라도 미탐색이면 높이를 읽기 전에 거부한다. 도메인은 [0,1]만 허용한다.
- `ControlHeight(alpha)` = (alpha×0.2f)×255. `PatchWorldXY`는 월드 행렬(`cb0[0..3]`) 적용 전 값이다.
- 타일 선택 ID(R32_UINT)는 다루지 않는다. 이 부품은 높이와 위치만 계산한다.

## 실제 검사 명령과 결과

```
python -B -X utf8 evidence/world_terrain_original/claude_geometry/basis_retail_probe.py
  → PASS_FILE_ONLY, 기저×8 = [[-1,7,-7,1],[3,-12,9,0],[-3,0,3,0],[1,6,1,0]], cb1[16] = (1.0, 0.866, 0.2)
python -B -X utf8 evidence/world_terrain_original/claude_geometry/run_bicubic_cpu_check.py 01
  → PASS_CPU_COMPILE_LINK_RUN, /O2와 /Od 모두 검사 158,432개, 곡면 표본 100,000개, 최대 오차 1.7e-5, 경고 0
```

CPU·컴파일 통과는 원본 화면·GPU·실게임 동등성을 뜻하지 않는다.

## B. 세계 카메라 — 현재 단서 (전부 candidate)

- 카메라 클래스 메서드와 호출 지점 목록은 `findings.json` B1에 있다.
- 0x42d790은 90° 여섯 면 큐브 촬영, 0x74ef80/0x4bb6e0은 뼈대 애니메이션 카메라로 보이며 세계 카메라 후보에서 제외했다.
- 0x487330이 45와 10000을 카메라 설정 메서드에 넘긴다. 설정 `Minimum Zoom Level`의 기본값은 11.0이다. 세계 화면과의 연결은 아직 추적하지 않았다.
- 실제 인스턴스·자세·시야각·클립 평면·확대 곡선은 unknown이다.

## C. 숲 — 미착수

## 정리 내역

- `bicubic_cpu_attempt01/work`의 exe·obj·rsp를 파일 ID·크기·SHA 기록 후 삭제했다(목록은 `result.json`의 `cleanup`).
- 이 폴더 밖에는 파일을 만들지 않았다. `assignment.json`과 기존 백업은 건드리지 않았다.
