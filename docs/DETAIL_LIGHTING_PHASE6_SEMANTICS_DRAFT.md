# 6단계 세부 법선·자기 그림자·반사 소비 경로 분석 초안

2026-11-15. 원본 EXE를 데이터로 읽고 선택한 코드만 해독했다. 원본 코드·Host·SDK·창·GPU·음향·게임은 실행하지 않았다. 이전 0–5단계 증거는 수정하지 않았다.

근거는 `evidence/world_terrain_original/phase6/semantics/retail_cache_bindings.json`과 재현 스크립트다. 원본 EXE SHA, 14개 선택 코드 블록 SHA, 16개 명령열 대조, 사용한 기존 셰이더 목록을 고정했다. 추가로 허용된 Composite VS/PS 두 개만 읽었으며, 임시 DXBC는 파일 ID·SHA·점유량 대조 뒤 전부 정리했다.

## 새로 연결한 원본 경로

| 연결 | 확정한 근거 | 남은 후보 |
|---|---|---|
| 혼합 재질 높이 → 세부 법선 | TerrainShaderScreen 패스1/2의 MRT1이 NormalCalculate descriptor의 첫 입력으로 전달된다 | 현재 68/66 크기, 반정밀 높이, UNORM16 법선, mip0, 현재 상위8재질·후광 경계·표본 방식 |
| 법선 오프셋·강도 | 원본 `0x6958fe..0x695948`이 `(1/width,1/height,0)`과 강도16을 설정한다 | 원본과 같은 실제 캐시 해상도·화면별 일정 |
| 자기 그림자 → 조사광·반사 조명 | CacheBake t2는 같은 경로의 Macro Shadow 출력이며, 이는 TerrainShaderScreen 패스3의 40회 광선 탐색이다 | 현재 atlas 좌표·원시 높이/월드 배율·광원 방향·편향·미탐색 광선 정책 |
| CacheBake 반사 MRT1 → 최종 지형 | 실제 TerrainShader descriptor 공급자가 비압축 반사 출력과 보관된 반사 캐시를 각각 slot8에 전달한다 | 화면 조명 t9의 생산·실제 값·켜짐 조건, 전체 압축·재표본·실행 순서 |

단순히 임시 자원의 생성 이름을 보고 연결하지 않았다. 같은 RT가 재사용되므로 원본의 `Terrain Render Temp`, `Terrain Shadow Temp` 이름과 그 순간의 내용이 다를 수 있다. 다른 객체의 같은 숫자 오프셋도 제외했다.

## 기본 법선과 세부 법선은 다른 입력

CacheBake VS는 `NORMAL0`의 `v1.xyz`를 `o1.xyz`로 그대로 보낸다. PS의 `v1.xyz`가 기본 법선 `n`이다. 세부 법선은 PS의 별도 텍스처 `t0.rgb`에서 `m=2*rgb-1`로 푼다.

```
T = (-nz,0,nx) / sqrt(nz²+nx²)
B = (0,nz,-ny) / sqrt(nz²+ny²)
N = T*m.x + B*m.y + n*m.z
```

원본 PS는 최종 `N`을 다시 정규화하지 않는다. 현재 높이장 정점 법선을 원본 `NORMAL0` 대신 공급하는 것은 현재 기하 공급 정책이다. 이번 추적이 원본 CPU의 정점 법선 생성까지 확정한 것은 아니다.

세부 법선은 혼합 재질 높이에 cardinal8tap Sobel을 적용한다. 강도16의 원본 값은 주소 `0x009efba8`, 비트 `0x41800000`이다. 원본의 연산은 다음과 같다.

```
Sx = NW - NE + 2*Left + SW - SE - 2*Right
Sy = NW + NE + 2*North - SW - SE - 2*South
encoded = .5 + .5*normalize(-16*Sx,16*Sy,4)
```

CacheBake의 앞 네 입력은 이 경로에서 `세부 법선, 혼합 확산, Macro Shadow, 혼합 반사` 순서다. 동적 장면 그림자까지 자동으로 포함됐다는 뜻은 아니다.

## 최종 t8 의미의 정정

예전 문서는 최종 TerrainShader의 t8을 확산 캐시로 추정했다. 이번 실제 descriptor와 호출 인수 추적으로, 이 경로의 t8이 **CacheBake가 만든 반사 캐시**임을 확인했다. 이전 증거를 고치지 않고 새 근거로 그 해석을 정정한다.

```
diffuse = cb1[28].x ? bakedDiffuse : 0
colour = cb1[27].x
    ? encode(decode(bakedSpecular)*screenLight + decode(diffuse))
    : diffuse
```

여기서 decode는 원본 float32 감마2.2승이고 encode는 원본 비트 `0x3ee8ba2f`의 역감마다. 그 뒤에 월드 마스크 LUT, 사전 곱 알파 덧그림, FOW, 거리 안개를 순서대로 적용한다.

`screenLight=1`은 아직 알 수 없는 화면 조명 입력을 대신하는 현재 후보다. 별도의 임의 반사 이득이 원본식에 있다는 근거는 없다. 실제 LUT와 큐브맵의 축·SRV 색공간·현재 재표본 경로 역시 실행 비교를 마치지 않았다.

추가로 읽은 Composite 패스0 PS는 `t0` RGBA를 그대로 복사한다. 이 셰이더만으로 외부 OM 알파/가산 혼합 상태를 확정하지 않는다. 이번 지형 반사 결합은 위의 원본 셰이더 내부 수식과 공급 경로를 따른다는 근거이며, 전체 렌더 상태나 화면 결과의 동등성을 뜻하지 않는다.

미탐색 높이·재질·그림자 광선은 현재 보호 정책으로 차단한다. 원본에 없던 유한값 방어와 광선 중단·중립 대체값도 별도로 기록한다. 위치·깊이·정수 타일 ID는 색 연산과 분리해 유지하며, 실제 GPU·화면·게임 수락 관문은 계속 보류한다.
