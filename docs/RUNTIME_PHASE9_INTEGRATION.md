# 최신 빌드 격리 실행 묶음 연동 — 9단계

2026-11-15. 최신 Host `20261115T121456Z_dbb01a1f4f50`와 동일 SDK430을 새 `20261115T134603Z_aa8853762399`에 파일 전용으로 연결했다. 엔진 소스 변경·재빌드·Host/GameCore/CLR/창/GPU/음향/실게임 실행0회, 기본 실행·등록·원본 설치/MODS/설정·사용자 저장 변경0이다.

위치: `C:\Users\home\OneDrive\Documents\Firaxis ModBuddy\ZeroSis' Engine Modernization\Build\InteractiveGameRuntime\20261115T134603Z_aa8853762399`. 이전99b3는 직전23c 조합으로,4c8f는 복구용으로,40a 사용자 저장은 그대로 보존한다. 최신 컴파일 후보·새 준비 묶음의 Host/SDK 및다섯팩SHA가 일치한다. 실제 게임·화면 수락은 보류다.

기존 준비 helper5개의 정확한바이트핀·실행차단가드를 그대로 사용하고, 새래퍼에는명시phase8프로필/f351핀·새evidence root·build-ID부모폴더준비만적용했다. 기본 준비는1회에성공했고 새runtime도1개만만들었다. 전역Host선택과production tool소스는바꾸지않았다.

완성된 기본이미지에만 SHA고정 overlay계획을단회적용했다. 원래request/bundle.manifest/Play본문은작은gzip에보존했다. 기본영수증은overlay이전이력이며 최종overlay/result.json·현재request·WorldAssets/assets.manifest.json이 현재기준이다.

terrain-assets.bin은V2로연결하고 나머지4팩은WorldAssets에별도목록을둬 backend23payload+manifest1의allowlist를유지했다. 기존5팩130,465,485B/UI154/지원6개와준비자료·아이콘2개를하드링크로재사용했다. 공유팩/지원자료attrs32를바꾸거나본문쓰기/chmod하지않는다. DB2개57,501,696B와기존개별GR2/config6개는독립사본이다.

Play에는묶음내4환경경로와고정manifest SHA를검사하는순수Python사전검사를앞에넣었다. 나머지원래Play본문은바이트그대로이고검사실패시중단한다. Resume의새게임전용/이전묶음저장차단도유지했다. 실행기자체는호출하지않았으며 사전검사CLI파서만실제실행해정상및잘못된핀/경로4개거부를확인했다.

계약·자산·저장독립검증을통과했다. UI원본74·sidecar154·유닛/애니메이션·ownedfont15의봉인출처/실제읽기경로를대조했다. ownedfont는기존한국어복구입력이며설치본font와무조건동일하다는요구로바꾸지않았다. 글꼴의화면가독성과실제엔진표시는미검증이다.

새핵심고유실할당65,589,552B(약62.55MiB),64MiB한도여유1,519,312B다. Hostcache/runtime동일ID는한번만계상했다. evidence/디렉터리/드라이버할당은이값에포함하지않으며프로젝트전체변화는current_work.json의최종storage를따른다. 새팩/원본DDS사본/전체프로젝트복제0이다.

중복지원8개실할당8,212,480B를정리했고 V1지형cache의새별칭1개퇴역은payload회수0B로구분했다. 자산검토의미사용초기검토기2개29,568B도정리했으며작은실패요약과현재검토기·SHA증거는보존했다.

원본캐시보기·압축·밉·실제해상도/배율·반사전체장면/카메라·원본하드웨어혼합·GPU색/깊이/ID/가림·실제UI/도시화면/입력·성능/VRAM·전체게임/저장/모드/멀티코어관문은남아있다. 조각배치는 **규칙 동등, 배치 동등은 미검증**이다.

최종상태: `evidence/world_terrain_original/phase9/runtime_integration/current_work.json`.
