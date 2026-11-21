# M2: Lua x64 제공자

후속 스트림 단계에서 미해결 심볼은 **278개**로 줄었사와요. 아래 342→302·61개 검사는 Lua 단계 당시의 기록이며, 최신 상태는 [스트림 제공자 기록](M2_STREAM_PROVIDER.md)에 있답니다.

2026-09-24 완료한 구성요소 기록이랍니다. 실제 설치된 32비트 Lua와 독립 x64 제공자의
관측 가능한 동작을 비교하고, GameCore와 같은 /MD 런타임으로 제공자를 연결하와요.
GameCore의 Lua 정수 ABI와 기존 저장 필드는 바꾸지 않으며 설치 DLL도 보존하와요.

SDK lua51_Win32.lib는 lua51_Win32.dll용 import library임을 실제 링크 지도와
실행 파일 의존성으로 확인했사와요. 시험 참조는 M0 해시와 일치하는 설치 Lua DLL을
Build/Lua_reference의 비교별 x86 폴더에 복사한 것이며, 시험 시작 시 실제 로드 경로를 확인하와요.
이 독립 프로그램은 GameCore를 불러오지 않사와요.

수용 기준은 4개 반올림 모드에서 3개 정수 API의 결과가 실제 Lua DLL 및 Python
기준과 일치하고, 자료구조·클로저·오류·코루틴·GC·C 콜백·동일 아키텍처 바이트코드
왕복 시험을 통과하며, 실제 GameCore 연결에서 Lua 미해결 이름이 사라지는 것이랍니다.
전체 Lua API·실제 게임 콜백과 잠금·다른 아키텍처 바이트코드·게임 저장 호환성은
별도 관문으로 유지하와요.

숫자 변환 차이가 확인되면 x64 제공자에서 SDK의 현재 반올림 모드를 따르도록
수정하와요. [Intel SSE2 변환 설명](https://www.intel.com/content/dam/develop/external/us/en/documents/18072-347603.pdf)의
CVTSD2SI를 사용하며, x87/SSE 상태가 서로 다른 기존 호스트 환경까지의 동등성을
자동으로 추정하지 않사와요.

## 확인한 차이와 수정 결과

| 검증 | 관측·결과 |
|---|---|
| 실제 참조 | 설치 Lua DLL 해시 f58ceffeb317e42b7691d823b0db4da63da0b988d2b381ccec9c3c18a58c0e35, M0와 일치 |
| 입력·API | 6,218개 숫자 × 4개 반올림 모드 × 3개 정수 API = 74,616개 결과 |
| 수정 전 공식 x64 Lua | 실제 x86 Lua와 297개 결과 불일치 |
| SDK 반올림에 맞춘 x64 제공자 | 74,616개 모두 일치, 별도 Python 기준과도 일치 |
| 스크립트 | 12개 결과가 x86·x64·Python 기준에서 일치 |
| C API 수명 | C 클로저, registry 참조, userdata payload, GC finalizer 호출 확인 |
| 바이트코드 | 각 아키텍처 안에서 dump/load 왕복 확인; x86→x64 직접 로드 미검증 |
| 제공자 빌드 | 29개 AMD64 오브젝트, /MD, /W3 /WX 경고 0건 |
| 기존 숫자 경계값 재시험 | 실제 /MD 제공자로 42,250개 변환·Lua 74개 사례·39회 오류 복구 통과 |
| 실제 GameCore 연결 | Lua C API 40개 해결, 전체 미해결 심볼 342→302, 새 미해결 이름 0개 |
| 원본·빌드·Stage 정합성 | 61개 검사 통과 |

공식 소스의 기본 x64 변환은 소수 부분을 버리는 반면 실제 참조는 현재 반올림
모드를 따랐사와요. x64에서 SSE2 CVTSD2SI를 사용하여 네 모드의 결과를 맞췄으며,
Lua 정수형 자체는 기존 x64 헤더의 pointer 크기를 유지했사와요. 32비트 범위를
벗어나는 게임 필드는 앞 단계의 입력 검사로 거부하와요.

추가로 SDK의 모듈 탐색 경로 두 군데를 유지하고, 원래 최대 크기가 제한된
해시 테이블의 개수를 native byte 계산에 넘기는 변환 세 곳을 명시했사와요.
모든 변경은 원본 해시·치환 횟수를 기록한 6개 패치이며, 공식 원본은 그대로랍니다.

## 산출물과 남은 관문

- [제공자 패치 계약](../Source/Providers/Lua51/patches.json)
- [29개 오브젝트와 /MD 빌드](../evidence/lua_provider/build_result.json)
- [수정 전 297개 차이](../evidence/lua_reference/upstream/conformance.json)
- [실제 x86 Lua와 수정 제공자 비교](../evidence/lua_reference/provider/conformance.json)
- [연결 오류 40개 해소 근거](../evidence/lua_provider/link_delta.json)
- [현재 전체 연결 기록](../evidence/sdk_x64/link_analysis.json)
- [정합성 검사](../evidence/project_verification.json)

Stage/GameCore_x64/Providers/Lua51에는 제공자 소스·라이선스 57개, 실제 x64
정적 라이브러리와 검증 기록을 보관했사와요. 게임 설치 경로나 MODS에 배포하지
않았고 전체 GameCore DLL도 아직 생성되지 않았사와요.

다음 연결 대상에는 FDataStream·FMemoryStream·FAutoArchive 등 저장·메모리
서비스가 포함되어 있사와요. 실제 x86 동작을 기준으로 저장 바이트와 실패·수명
계약을 비교해야 하며, 남은 302개 심볼을 이름만 채우는 구현으로 닫지 않사와요.
전체 x64 실행부·실제 게임 계산의 멀티코어 통합·실게임 수용은 계속 진행 중이랍니다.
