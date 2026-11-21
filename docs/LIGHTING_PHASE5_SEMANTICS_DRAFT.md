# 5단계 조명·합성 정적 계약 초안

2026-11-15. 이 문서는 원본 바이트코드의 연산과 현재 구현에 필요한 정책을 분리한 분석 초안이다. 실제 게임·창·GPU 실행 결과를 뜻하지 않는다. 기존 0–4단계 증거는 수정하지 않았다.

재현 가능한 근거는 `evidence/world_terrain_original/phase5/semantics/lighting_contract.py`와 같은 이름의 JSON이다. 물 PS2는 기존 3단계 목록을 재사용했고, 지형 조명·최종 합성·자기 그림자에 필요한 DXBC 여섯 개만 선택해서 읽었다. 원본 EXE와 셰이더 SHA를 대조한 뒤 임시 DXBC는 전부 정리했다.

## 물 PS2의 확정 수식

`D`는 `t6(1-saturate(4*t7.A),0)`의 LOD0 샘플값이다. 원본 PS는 이 `D.rgb`에 별도의 2.2승을 적용하지 않는다. `N=(meanX,meanY,1)`은 정규화하지 않는다.

```
L = saturate(dot(N, primaryLight))
F = (1 - dot(N, normalize(camera - world)))^5
C = L * (D.rgb + F * (G1*C1 + G2*C2))
  + Gwide1 * D.rgb * C1
  + pow(reflectionMean.rgb, gamma) * reflectionGain
  + saturate(4*h) * q2^3 * D.rgb
C = C + negativeShadow * (saturate(dynamicShadow.R) * shadowStrength * C)
alpha = saturate(D.a + reflectionMean.a * D.a)
encoded = pow(C, inverseGamma)
```

`G1`과 `G2`는 각각 거부 조건을 적용한 주·보조 좁은 가우스 항이다. 넓은 항은 주 광원 것 한 번만 더한다. `q2`는 보조 가우스 항의 지수값이며 **가우스 항이 거부돼도 r1.w가 덮이지 않아 추가 깊이 항에 그대로 사용된다**. 원본이 하지 않은 Fresnel clamp, F0, 법선 재정규화, `q2` 거부 마스크를 이 확정식에 넣지 않는다. 비정상·오버플로 방어가 필요하면 별도의 현재 정책으로 명시한다.

다음 연산은 감마를 적용한 뒤의 색에서 수행한다.

1. `overlay.rgb + (1-overlay.a)*encoded`라는 셰이더 내부의 사전 곱 알파 합성.
2. `lerp(0.4, colour, FOW.R)`.
3. `lerp(colour, LUT(colour), FOW.R*(1-FOW.B))`.
4. 거리·높이 안개. 위 물 알파는 유지된다.

상수 버퍼의 광원 방향·색·K, 반사 이득, 그림자 강도, 좌표 투영, 원본 시계·층 혼합값은 실행 중 값이므로 미확정이다. 정확한 출력 알파가 밝혀졌다는 사실만으로 외부의 하드웨어 혼합 상태가 밝혀진 것은 아니다.

## CacheBake와 법선

원본 기본 법선 `n=(nx,ny,nz)`에 대해 다음 식을 쓴다. 일반적인 직교화된 접공간 기저로 임의 교체하지 않는다.

```
T = (-nz, 0, nx) / sqrt(nz*nz + nx*nx)
B = (0, nz, -ny) / sqrt(nz*nz + ny*ny)
m = 2*normalCache.rgb - 1
N = T*m.x + B*m.y + n*m.z
```

최종 `N`의 정규화는 없다. 접공간 분모가 0인 입력의 방어는 현재 정책이다.

```
I = gain*cube4(N) + shadowR*(gain*cube5(N) - gain*cube4(N))
diffuse.rgb = LUT(pow(albedoSample.rgb*I + epsilon, inverseGamma))
diffuse.a = 1
e = 64*specSample.a + 1
f = pow(saturate(dot(N, light)), e) * e * saturate(1-shadowR)
specular.rgb = LUT(pow(specSample.rgb*f, inverseGamma))
specular.a = specSample.a*f
```

확산의 cube 혼합에서는 `shadowR`를 clamp하지 않는다. 샘플된 cube 값에 추가 2.2승도 없다. 두 출력은 같은 `t8` 3D LUT를 사용한다. `cube4=햇빛`, `cube5=그림자빛`이라는 자산 이름 연결은 현재 해석이며 원본 업로드 호출까지 추적한 사실이 아니다.

NormalCalculate는 `t0.R`의 8개 샘플을 사용한다. 카드널 오프셋이라는 해석 아래 다음 식과 같다.

```
Sx = NW - NE + 2*Left + SW - SE - 2*Right
Sy = NW + NE + 2*North - SW - SE - 2*South
encoded = .5 + .5*normalize(-strength*Sx, strength*Sy, 4)
```

그러나 원본의 텍셀 오프셋·강도, `t0`가 혼합 재질 높이 캐시인지 다른 높이장인지, 캐시 해상도는 미확정이다. 레지스트리도 실행 중 채우는 `.bss` 표다. 현재 재질 높이의 Sobel 생산이나 중립 법선 `(.5,.5,1)`을 쓰면 생산 경로를 후보라고 명시한다.

## 최종 지형과 남은 파이프라인 경계

```
C0 = cacheEnabled ? litCache : 0
C = screenLightEnabled
  ? pow(pow(albedoCache, gamma)*screenLight + pow(C0, gamma), inverseGamma)
  : C0
C = lerp(C, worldLUT(C), saturate(projectedMask.R)*maskStrength)
C = overlay.rgb + (1-overlay.a)*C
C = lerp(baseLayer, C, FOW.R)
C = lerp(C, fowLUT(C), FOW.R*(1-FOW.B))
C = distanceHeightFog(C)
alpha = 1
```

CacheBake의 두 번째 반사 출력이 최종 `litCache` 또는 화면 조명에 어떻게 들어가는지는 추적되지 않았다. 확산·반사 단순합은 현재 합성 정책으로 분리해야 한다. 같은 샘플을 받는 점별 연산을 한 셰이더에 넣을 수 있지만, 캐시 재표본·해상도·실행 순서까지 동등해지는 것은 아니다.

선택 DXBC에는 외부 OM 혼합 상태가 없다. 알려진 원본 패스 표도 VS/PS/GS/HS/DS 핸들 다섯 개뿐이다. 셰이더 내부의 사전 곱 알파 식, 원본 알파 출력, 현재 장면 합성 정책을 각각 기록한다.

자기 그림자 PS는 별도로 `t0.A*255*heightScale`을 광선 높이와 비교하는 40회 탐색이다. 원본의 주축 정규화 방향, 루프 전 한 걸음, 매회 상승, 부드러운 감소 식은 확정했다. 현재 높이장에 연결할 경우 좌표·편향·방향과 미탐색 광선 처리 정책이 추가로 필요하며, 동적 장면 그림자를 복원한 것으로 보고하지 않는다. 기본 그림자 0과 명시적 후보 입력도 유효한 오프라인 경로다.

정확한 32비트 상수는 JSON에 원본 DXBC의 바이트 위치와 함께 고정했다. 특히 ray rise는 단순한 `.314485f`가 아니라 `0x3ea1043d`이고, 역감마는 `0x3ee8ba2f`다. 기존 위치·깊이·정수 타일 ID·미탐색 차단을 유지하고 실제 화면 수락 관문은 별도로 남긴다.
