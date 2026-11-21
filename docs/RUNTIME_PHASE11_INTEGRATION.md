# 최신 빌드 격리 실행 묶음 연동 — 11단계

2026-11-16. 최신 Host `20261116T114748Z_014dd63ad3bc`와 기존 SDK430을 새 `20261116T123457Z_90b98a574efc`에 연결했다. 파일 전용 연동이며 엔진 소스 변경·재빌드·Host/GameCore/CLR/창/GPU/음향/게임 실행은 0회다. 기본 실행·등록·원본 설치·MODS·설정·사용자 저장을 변경하지 않았다.

위치: `C:\Users\home\OneDrive\Documents\Firaxis ModBuddy\ZeroSis' Engine Modernization\Build\InteractiveGameRuntime\20261116T123457Z_90b98a574efc`. 기존 aa885는 직전 준비본, 99b3/4c8f는 이전·복구 자료, 40a의 사용자 저장은 보존했다. 새 게임 전용이며 다른 묶음의 저장을 Resume으로 넘기는 경로는 차단 상태다.

기존 준비 도구5개의 바이트 핀과 Native 차단 가드를 재사용했다. 새 래퍼는 명시014dd/3e2ad 준비 profile과 별도 증거 루트만 선택한다. 기본 묶음을 1회 준비하고 검토한6팩 overlay를 1회 적용했다. 초기 request/manifest/Play는 작은 gzip 이력으로 보존했으며 최종 overlay/request/manifest가 현재 기준이다.

terrain/fog/water/LEAN/lighting/screen_light 여섯 팩은 원본과 동일한 파일 ID·SHA·수정 시각·속성을 가진 직접 하드링크다. 새 자산 복사·패키지 생성은 0이다. 정적 specscreenmap은 물 Raw 반사와 분리해 새 ZEROSIS_SCREEN_LIGHT_ASSETS 경로에 연결했다.

필수 UI154개와 지원 자료8개를 공유하며, 공유 원본의 attrs32/바이트는 변경하지 않았다. DB2개와 GR2/config는 독립 사본이다. Backend V4는23payload+manifest1을 유지하고 보충 자산은 WorldAssets의 별도 고정 목록으로 검증한다.

Play에는 묶음 내부5환경 경로와 고정 manifest를 읽는 순수Python 검사만 앞에 추가했고 나머지 기존본문은 그대로 보존했다. Play/Resume은 호출하지 않았다. 파일검사 함수/CLI 정상 입력과 잘못된 핀·경로4건 거부를 확인했고 독립 계약/자산/저장 검토도 통과했다.

새 핵심 실할당은 65,601,840B이며64MiB이하다. 기존 지원 자료의 중복8개는8,212,480B를 회수했고 V1 terrain 별칭1개 삭제는 공유payload 회수0B로 구분했다. 전체 프로젝트 전후 용량은 current_work.json의 최종storage를 따른다.

실제 원본 화면·UI·게임·저장/모드·멀티코어 성능 수락은 보류다. 원본 캐시 재표본화/압축·높이 보정, 반사 카메라/누락 제공자, 숲 GR2/배치·곡면 기저·세계 카메라 연결은 이전 단계의 남은 작업으로 유지한다. **규칙 동등, 배치 동등은 미검증**이다.

최종 상태: `evidence/world_terrain_original/phase11/runtime_integration/current_work.json`.
