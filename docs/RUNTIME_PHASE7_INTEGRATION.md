# 최신 빌드 격리 실행 묶음 연동 — 7단계

2026-11-15. 최신 Host `20261115T093013Z_23c5037b12b9`와 SDK430을 새 묶음 `20261115T101941Z_99b3c393ee9a`에 연결했다. 엔진 소스 수정·Host 재빌드0회, Host/GameCore/CLR/창/GPU/음향/실게임 실행0회다. 기본 실행·전역 등록·원본 게임/MODS/설정·사용자 저장은 변경하지 않았다.

위치: `C:\Users\home\OneDrive\Documents\Firaxis ModBuddy\ZeroSis' Engine Modernization\Build\InteractiveGameRuntime\20261115T101941Z_99b3c393ee9a`. `Play.ps1`에는 실제 원본 실행기 본문을 그대로 남기고, 앞에 4개 묶음 내부 환경 경로와 파일 전용 검사만 추가했다. 실행 자체는 보류다. Resume.ps1의 이전 묶음 저장 불러오기 차단도 유지했다.

기존 준비 도구의 명시적 프로필 경로와 실행 차단 감사 가드를 재사용했다. 첫 시도는 사용자 지정 출력 부모 폴더가 없어 runtime 생성 전에 멈췄으며, 부모를 만든 새 경로에서 파일 준비가 성공했다. 실패 원문/호출 기록을 남겼고 실제 runtime은 하나만 생성했다.

기본 파일 준비가 끝난 새 묶음에만 별도 파일 어댑터를 적용했다. 원래 request/bundle.manifest/Play 원문은 작은 gzip으로 보존했다. 기본 준비 영수증은 변경 전 이력이고, 최종 overlay/result.json·현재 request·WorldAssets/assets.manifest.json을 최종 근거로 삼는다. 같은 새 묶음을 V1 전용 지형 재사용 도구의 입력으로 무조건 취급하지 않는다.

지형 V2는 기존 terrain-assets.bin 행을 바꿨다. 안개·물·LEAN·조명은 WorldAssets의 별도 목록에 둬 V4 backend allowlist(23payload+manifest1)를 유지했다. 다섯 팩130,465,485B는 직접 하드링크라 새 cache/payload 복사가0이다. source와 target의SHA/ID/mtime/속성을 대조했고 팩의기존attrs32를바꾸지않았다. 공유자료는읽기전용으로사용하며chmod/내용쓰기를하지않는다.

같은 UI 준비자료·아이콘·지원Python6개도 기존4c8f 입력으로 공유해 새 사본8개를 제거했다. 반면 rules.db/localization.db57,501,696B와기존private모델/config사본정책은유지했다. 새세션·옵션은새runtime아래에만생기도록기존경계를보존했다. UI154·지원6개·원본font/UI읽기루트·UnitV2/애니메이션·SDK를독립대조했다.

실제파일전용사전검사와잘못된pin/경로4개거부,계약/자산/저장독립검토가통과했다. 새핵심자료고유실할당65,560,880B(약62.52MiB)는64MiB예산안이다. 이값은증거/디렉터리를제외하며전체폴더증가량과다르다. 중복지원8개의실할당8,212,480B를정리했고 구형지형cachealias1개삭제는payload회수0B로구분했다.

남은원본조명/카메라/동적그림자·성능·UI/클릭/저장/모드/멀티코어·실제GPU/원본화면관문은그대로다. 현재의파일연동성공은실게임수락을뜻하지않는다. 상태: `evidence/world_terrain_original/phase7/runtime_integration/current_work.json`.
