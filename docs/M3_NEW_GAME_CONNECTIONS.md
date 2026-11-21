# M3 새 게임과 지도 생성 연결 경로

## 현재 경계

정식 `CvGameCoreDLL_Expansion2` 소스와 격리 x64 실행 결과를 대조한 현재 상태를 정리했사와요. en_US·ko_KR 각각에서 실제 GameCore 초기화, SDK Lua 등록, Players/Teams ID 조회, GameInfo 조회, 종료와 DLL 해제가 통과했답. GameInfo는 언어별 실행에서 12개 규칙 테이블, 총 577행을 조회했고, 관측값은 `[6,9,25,42,29,8,45,148,140,38,70,17,0,0,6,17,1]`이었사와요. 그러나 새 게임은 아직 실행하지 않았으므로 지도 크기 `0×0`, 턴 `-1`인 초기화 상태가 최신 확인 결과랍니다. 아래 SDK 경로는 UTF-8 문서에서 소스 문자 인코딩(latin1)과 무관하게 읽을 수 있도록 파일명과 줄 번호로 적었사와요.

## 외부 호스트의 공개 진입점과 순서

SDK에는 `CvDllGameContext` 구현이 `CvDllContext.h/.cpp`라는 이름으로 있사와요. 헤더가 `ICvGameContext3`를 상속하고 `GetPreGame`, `GetGame`, `GetMap`, `SetGameDatabase`, `SetDLLIFace`, `Init`, `Uninit`을 공개하와요 ([CvDllContext.h:19-49, 144-178](../Source/SDK_BNW_x64/CvGameCoreDLL_Expansion2/CvDllContext.h)). 구현은 컨텍스트의 쿼리 인터페이스로 Context1–3을 돌려주고, `GetPreGame()`은 어댑터를 만들며, Game/Map은 내부 포인터가 존재할 때만 어댑터를 반환하와요 ([CvDllContext.cpp:102-113, 224-250](../Source/SDK_BNW_x64/CvGameCoreDLL_Expansion2/CvDllContext.cpp)). 이 반환 어댑터들은 사용 후 SDK의 `Destroy()` 계약으로 해제해야 하와요.

현재 호스트의 선행 순서는 그대로 유지하면 되와요. `Session::Initialize`가 컨텍스트를 얻고, 규칙 DB·UI·엔진 서비스를 먼저 연결한 뒤 `context->Init()`을 부르고, 마지막에 SDK Lua 라이브러리를 기존 스크립트 서비스에 바인딩하와요 ([GameCoreSession.h:37-54](../Source/Host/GameCoreSession.h)). 모든 다음 SDK 호출도 소유 스레드의 `GameCall` 잠금 범위에서 진행해야 하며, SDK의 `CvDllGameContext::Init/Uninit` 자체도 전역 수명 게이트를 사용하와요 ([CvDllContext.cpp:709-720](../Source/SDK_BNW_x64/CvGameCoreDLL_Expansion2/CvDllContext.cpp); [HostServices.h:164-168](../Source/Host/HostServices.h)).

그 다음 공개 게임 진입점은 `context->GetGame()->Init(handicap)`와 `Init2()`랍니다. `ICvGame1`이 두 함수를 공개하고([CvDllInterfaces.h:979-1022](../Source/SDK_BNW_x64/CvGameCoreDLLUtil/include/CvDllInterfaces.h)), `CvDllGame`은 이들을 내부 `CvGame::init`과 `init2`에 그대로 전달하와요 ([CvDllGame.cpp:298-305](../Source/SDK_BNW_x64/CvGameCoreDLL_Expansion2/CvDllGame.cpp)). `Init2()`의 반환값이 false면 성공으로 처리하면 안 되와요. 지도 크기·턴·플레이어 수 같은 관찰값은 `GetMap()`과 Game 어댑터에서 읽고, 지도 어댑터는 새 지도가 만들어지기 전에는 null일 수 있답니다 ([CvDllContext.cpp:229-250](../Source/SDK_BNW_x64/CvGameCoreDLL_Expansion2/CvDllContext.cpp)).

이 순서는 SDK의 의미를 보존하는 최소 경로랍니다: 설정 → `ICvGame1::Init` → `ICvGame1::Init2` → 결과 관찰. 호스트가 지도 객체를 직접 초기화하거나 GenerateMap Lua를 별도 실행하면 SDK가 `InitPlayers`, 시작 아이템, 해안 검증, 인접성 캐시, 최종 초기화 플래그 설정까지 수행하는 경로를 건너뛰게 되므로 채택하면 안 되와요 ([CvGame.cpp:402-420, 447-539](../Source/SDK_BNW_x64/CvGameCoreDLL_Expansion2/CvGame.cpp)).

## 프리게임 설정

설정은 `context->GetPreGame()`의 `ICvPreGame1`에서 하와요. ABI에는 게임 종류·속도·난이도·활성 플레이어, 지도 스크립트·월드 크기·지도 옵션·시드, 슬롯 상태·문명·지도자·팀·도시국가 수 설정자가 공개되어 있답니다 ([CvDllInterfaces.h:1418-1614](../Source/SDK_BNW_x64/CvGameCoreDLLUtil/include/CvDllInterfaces.h); 어댑터 선언 [CvDllPreGame.h:125-214](../Source/SDK_BNW_x64/CvGameCoreDLL_Expansion2/CvDllPreGame.h)).

구성은 이 순서가 안전하와요.

1. 새 게임 유형과 시나리오가 아닌 새 게임 시작을 선택하고, 게임 속도·시대·핸디캡·활성 플레이어·게임 옵션을 채우와요. `setGameType(GameTypes, GameStartTypes)`와 `setHandicap` 등은 SDK에 공개되어 있답니다 ([CvPreGame.h:173-216](../Source/SDK_BNW_x64/CvGameCoreDLL_Expansion2/CvPreGame.h)). 실제 호스트 프로토콜의 기본값은 아직 정의되지 않았으므로 임의 기본값을 성공으로 간주하지 말고 입력 설정을 모두 명시해야 하와요.
2. `setMapScriptName`에 카탈로그에서 확인된 정확한 가상 경로를 넣고, `setWorldSize`로 DB의 `Worlds.ID`에 해당하는 타입을 지정하와요. 이어서 맵 스크립트가 선언한 각 사용자 옵션을 `SetMapOption`으로 명시하와요 ([CvPreGame.h:226-231](../Source/SDK_BNW_x64/CvGameCoreDLL_Expansion2/CvPreGame.h)). 스크립트 이름 변경은 `ResetMapOptions()`를 호출해 옵션을 비우므로 스크립트 선택 뒤 옵션을 설정해야 하며, 월드 크기 변경은 기본 인자 `bResetSlots=true`로 슬롯도 재설정하므로 월드 크기 선택을 플레이어 설정보다 먼저 해야 하와요 ([CvPreGame.cpp:2718-2727, 3027-3049](../Source/SDK_BNW_x64/CvGameCoreDLL_Expansion2/CvPreGame.cpp)).
3. 원하는 주요 플레이어 슬롯 각각에 `SS_TAKEN` 또는 `SS_COMPUTER`를 지정하고, 슬롯의 문명·지도자·팀·핸디캡을 함께 기록하와요. 비활성 슬롯은 폐쇄 상태로 명시하고, 활성 플레이어를 실제 인간 슬롯에 맞추와요. `CvGame::init`은 `SS_TAKEN` 슬롯만 팀 셔플 목록에 넣고 `init2`는 `InitPlayers()`를 실행하므로, 빈 슬롯을 인간 또는 AI 플레이어로 잘못 열어 두면 안 되와요 ([CvGame.cpp:246-279, 402-405, 562-710](../Source/SDK_BNW_x64/CvGameCoreDLL_Expansion2/CvGame.cpp)).
4. `setNumMinorCivs`, 지도 기후·해수면, 지도·동기 난수 시드를 설정하와요. `CvGame::init`은 지도 시드로 `m_mapRand`를, 동기 시드로 `m_jonRand`를 초기화하므로 두 시드는 서로 다른 설정으로 보존해야 하와요 ([CvPreGame.h:226-261](../Source/SDK_BNW_x64/CvGameCoreDLL_Expansion2/CvPreGame.h); [CvGame.cpp:179-218](../Source/SDK_BNW_x64/CvGameCoreDLL_Expansion2/CvGame.cpp)). 영(0) 시드 사용은 `LoadPreGameFromIni`에서만 시계값 대체가 확인되므로 외부 호스트는 재현성을 위해 명시적인 비영 시드를 권장하와요 ([CvPreGame.cpp:1453-1460](../Source/SDK_BNW_x64/CvGameCoreDLL_Expansion2/CvPreGame.cpp)).

월드 크기 enum이나 문명 ID는 규칙 DB가 추가되었을 때도 호환되도록 GameInfo/규칙 조회 결과의 문자열 Type에서 현재 DB ID를 찾아야 하와요. 이 조회는 두 언어의 실제 GameCore 실행에서 통과했답. `CvMapGenerator::GetMapInitData`도 `Worlds` 행을 DB에서 직접 조회하므로 알 수 없는 월드 크기는 유효한 시작이 아니랍니다 ([CvMapGenerator.cpp:48-78](../Source/SDK_BNW_x64/CvGameCoreDLL_Expansion2/CvMapGenerator.cpp)).

## 실제 맵 생성 흐름

정적 소스에서 확인한 첫 새 게임 흐름은 아래와 같사와요.

```text
GetPreGame → 프리게임 설정 완료
GetGame()->Init(handicap)
GetGame()->Init2()
  ├─ InitPlayers()
  └─ InitMap()
       ├─ mapScriptName = CvPreGame::mapScriptName()
       ├─ CvMapGenerator(mapScriptName) → ScriptSystem::CreateLuaThread/LoadFile
       ├─ GetMapInitData(worldSize) → map.init(data)
       ├─ CvBarbarians::MapInit(numPlots)
       ├─ GenerateMap()
       ├─ GetGameInitialItemsOverrides()
       ├─ ValidateCoast(), updateAdjacency()
       └─ 시작 위치·초기 아이템·최종 게임 초기화
```

직접 근거는 `CvGame::init2`와 `InitMap` 호출부랍니다 ([CvGame.cpp:402-420, 447-539](../Source/SDK_BNW_x64/CvGameCoreDLL_Expansion2/CvGame.cpp)). 스크립트 생성기는 선택된 이름을 받아 Lua thread를 만들고 `LoadFile`을 호출하와요 ([CvMapGenerator.cpp:32-44](../Source/SDK_BNW_x64/CvGameCoreDLL_Expansion2/CvMapGenerator.cpp)). `GetMapInitData`는 DB 월드 행의 기본 폭·높이를 먼저 설정한 뒤 Lua 콜백으로 전달하고, 반환 테이블의 폭·높이·wrap·위도 필드는 선택적으로 덮어쓴답니다 ([CvMapGenerator.cpp:48-149](../Source/SDK_BNW_x64/CvGameCoreDLL_Expansion2/CvMapGenerator.cpp)). Continents 맵은 `GetMapScriptInfo`에서 5개 사용자 옵션을 정의하지만 `GetMapInitData`를 정의하지 않으므로 이 스크립트에선 규칙 DB 월드 크기 폭·높이가 기준이와요 ([Continents.lua:18-34, 117-142](../Source/Assets/Scripts/Assets/Maps/Continents.lua)).

`GenerateMap()`은 DLL이 임의로 흉내 내서는 안 되는 단일 진입점이랍니다. SDK가 정확한 Lua 전역을 찾아 보호된 `CallFunction`으로 부르며 함수가 없으면 오류를 내와요 ([CvMapGenerator.cpp:277-290](../Source/SDK_BNW_x64/CvGameCoreDLL_Expansion2/CvMapGenerator.cpp)). BNW Continents는 MapGenerator, FractalWorld, FeatureGenerator, TerrainGenerator를 include하고, 지도 생성 함수에서 지형·특징·강·호수와 시작 위치/자원 배치를 나눠 수행하와요 ([Continents.lua:10-13, 249-310](../Source/Assets/Scripts/Assets/Maps/Continents.lua); [Expansion2 MapGenerator.lua:779-812](../Source/Assets/Scripts/Assets/DLC/Expansion2/Gameplay/Lua/MapGenerator.lua); [AssignStartingPlots.lua: 파일 내 `Create`/배치 함수](../Source/Assets/Scripts/Assets/DLC/Expansion2/Gameplay/Lua/AssignStartingPlots.lua)).

현재 ScriptCatalog builder는 BASE_MAPS → BASE_GAMEPLAY → Expansion → Expansion2 우선순위에서 동일 가상 경로를 덮어써 선택하고, Expansion2의 MapGenerator를 남기도록 설계되어 있답니다 ([prepare_host_script_catalog.py:10-25](../tools/prepare_host_script_catalog.py)). 따라서 일반 맵 실행에서 `setMapScriptName("Assets/Maps/Continents.lua")`는 원본 경로 별칭으로 해석되고, `include("MapGenerator")` 같은 짧은 include는 선택된 유일한 `gameplay/lua/mapgenerator.lua`로 해석되어야 하와요 ([ScriptCatalog.h:24-45](../Source/Host/ScriptCatalog.h); [ScriptSystem.h:96-116, 250-260](../Source/Host/ScriptSystem.h)). 이 alias/overlay 계약이 깨져 있으면, 중복 이름 거부 또는 등록되지 않은 경로 실패가 나며 빈 스크립트나 대체 stub으로 통과시켜서는 안 되와요.

## 연결되어 있지 않거나 호출 때 증명이 필요한 엔진 서비스

`EngineServices`에서 지금 확인되는 연결은 실제 ScriptSystem 반환, 맵 면적용 `DoMapSetup`, 오디오, 게임 잠금·소유 스레드, 규칙 DB 기본 검사 등이랍니다 ([HostServices.h:69-128](../Source/Host/HostServices.h)). `DoMapSetup`은 전역 초기화와 소유 잠금 및 올바른 스레드를 요구하므로 새 지도의 `CvMap::init` 호출 전에 유지되어야 하와요 ([CvMap.cpp:483, 1417](../Source/SDK_BNW_x64/CvGameCoreDLL_Expansion2/CvMap.cpp); [HostServices.h:100-104](../Source/Host/HostServices.h)).

다음 항목은 인터페이스 상속용 기본 구현에서 명시적으로 Unsupported이며, 실제 새 게임 경로에서 호출되는지 정적 인용만으로는 확정할 수 없답니다: `GetModsDatabase`, `IsModActivated`, `IsPlayerConnected`, `getMapScriptName`, `VerifyPlayerSlot`, `GetEvaluatedMapScriptPath` ([GeneratedHostInterfaces.h:10-20, 115-118, 263-268](../Source/Host/GeneratedHostInterfaces.h)).

- `GetEvaluatedMapScriptPath`는 네트워크 초기화 데이터 `Commit()`과 WorldBuilder 후처리에서 호출된다는 것이 확인되었사와요. 표준 새 맵의 `CvGame::InitMap`은 `CvPreGame::mapScriptName()`을 `CvMapGenerator`에 직접 넘기므로, 이미 카탈로그에 있는 표준 가상 경로를 지정하면 이 resolver는 그 구체 경로에서 요구되지 않는답니다 ([CvDllNetInitInfo.cpp:232-239](../Source/SDK_BNW_x64/CvGameCoreDLL_Expansion2/CvDllNetInitInfo.cpp); [CvWorldBuilderMapLoader.cpp:1665-1678](../Source/SDK_BNW_x64/CvGameCoreDLL_Expansion2/CvWorldBuilderMapLoader.cpp); [CvGame.cpp:504-517](../Source/SDK_BNW_x64/CvGameCoreDLL_Expansion2/CvGame.cpp)). 멀티플레이어/시나리오 경로까지 지원할 때는 별도로 구현해야 하와요.
- `DoMapSetup`은 표준 지도 초기화에서 직접 확인된 필수 호출이며 호스트에 연결되어 있사와요. `MapSurface`는 폭·높이를 저장하지 않고 generation 번호와 `dirtyPlots` 크기만 보유하므로 폭·높이 일치 여부를 이 객체로 검증할 수는 없답 ([MapSurface.h:11-36](../Source/Host/MapSurface.h)). 실제 지도에서는 SDK의 `GetGridWidth()`, `GetGridHeight()`, `numPlots()` 결과를 관찰하고, `DoMapSetup`에 전달되는 `numPlots()`가 `width*height`와 같은지 확인해야 하와요 ([CvMap.cpp:423-433, 483](../Source/SDK_BNW_x64/CvGameCoreDLL_Expansion2/CvMap.cpp); [HostServices.h:100-104](../Source/Host/HostServices.h)).
- `IsModActivated`는 SDK 코드에 여러 DLC/시나리오 분기 호출이 있지만, 표준 기본 새 게임에서 최초로 호출되는지는 이 경로 분석만으로 알 수 없사와요 ([예: CvGame.cpp:5843-5855](../Source/SDK_BNW_x64/CvGameCoreDLL_Expansion2/CvGame.cpp)). 적중 시 의미 없는 false를 돌려 DLC 규칙을 숨기지 말고, 실제 활성 모드 상태를 제공하거나 실패로 분명히 남겨야 하와요.
- `GetModsDatabase`는 HostRun의 `HostState`가 mods DB 포인터 없이 만들어지므로 현재 호출되면 명시적 Unsupported랍니다 ([HostRun.h:55-57](../Source/Host/HostRun.h); [HostServices.h:113-116](../Source/Host/HostServices.h)). 구성 모드 테이블을 읽는 실제 SDK 경로가 선택되는지 조사하고, 활성 모드 규칙을 로드하지 않은 채 새 게임 성공으로 판정하지 않아야 하와요.
- `IsPlayerConnected`와 `VerifyPlayerSlot`은 사람/AI 슬롯 준비 또는 알림 경로에서 요구될 수 있지만, 이번에 지정한 `Init→Init2→맵 생성` 호출 경로의 가장 첫 호출이라는 증거는 아직 없사와요. 최초 실패 서비스 이름, SDK 스택, 변경 전후 슬롯·맵 관찰을 새 관문 로그에 보존해야 하와요.
- `getMapScriptName`은 표준 `CvGame::InitMap`이 아니라 일부 engine utility 소비자가 접근할 때 Unsupported랍니다. `GetEvaluatedMapScriptPath`와 마찬가지로 호출 로그가 생기기 전에는 필수 여부를 주장하지 않사와요.

즉 현재 자료로는 **다음 연결 후보와 직접 요구 경로**는 정할 수 있으나, 새 게임 첫 시도의 “첫 미연결 서비스”를 사실로 단정할 수는 없답니다. 이를 알아내려면 GameInfo가 연결된 실행부에서 새 게임 호출을 하고 Unsupported 이름을 오류 보고에 보존해야 하와요. 새 게임의 격리 실행은 진행 범위에 포함되어 있답.

## 다음 구현·판정 기준

1. 완료된 GameInfo 조회는 별도 미완료 항목에서 제외하고, 지도 생성에 필요한 Map/Fractal Lua 라이브러리의 활성 메서드·열거값을 실제 타입과 반환값까지 확인하와요. map script option 수와 값은 SDK 메타데이터 또는 DB에서 얻어 모두 설정하와요.
2. `Session::Initialize` 후 `GameCall` 안에서 모든 프리게임 값을 설정하고, getters로 다시 읽어 설정과 일치할 때만 `GetGame()->Init`을 시작하와요. 프리게임 setter 중 맵 스크립트나 월드 크기 설정에 슬롯/옵션 reset 부작용이 있으므로 위 순서를 지키와요.
3. `Init2()`가 true여도 곧장 합격시키지 말고 `GetMap()`의 양의 폭·높이와 그 곱인 plot 수, 선택된 MapScript 경로, 플레이어·팀 ID, turn 상태, 실패 없는 시작 위치 및 초기 유닛을 확인하와요. `Init2`가 `setFinalInitialized(true)`까지 호출한다는 사실만으로 이 실제 값을 대신할 수 없답니다 ([CvGame.cpp:402-420, 562-710](../Source/SDK_BNW_x64/CvGameCoreDLL_Expansion2/CvGame.cpp)).
4. 첫 `UnsupportedService`가 나오면 이름과 첫 SDK 호출 위치에 따라 필요한 서비스만 계약대로 연결하고 다시 같은 시드를 실행하와요. 활성 모드가 아닌데 임의로 `IsModActivated=false`, 지도 크기가 0인데 true 같은 가짜 성공, 빈 지도·stub은 합격이 아니랍니다.
5. 새 게임 및 지도 생성 다음 관문에서 초기 턴과 게임 상태를 진행하와요. 이번 문서 수정은 소스 대조와 정리만 수행했으며 추가 실행·전체 빌드·설치 게임/MODS/세이브 변경은 하지 않았사와요.

## 사실과 미확인 구분

**직접 확인:** 공개 인터페이스, 프리게임 setter, `CvGame::init → init2 → InitMap`, map script `LoadFile → GetMapInitData → map.init → GenerateMap`, 지도 이후 정리 작업, `DoMapSetup`의 SDK 호출, 현재 HostServices의 구현/Unsupported 선언은 위 줄 근거의 소스에서 확인했사와요.

**새 게임에서 아직 확인되지 않음:** 프리게임 설정이 새 GameCore 게임 객체와 Lua 양쪽에 반영되는지, 표준 지도 스크립트가 호스트 Lua 환경에서 전체 생성되는지, 양수 지도 폭·높이와 올바른 `width*height` plot 수, 시작 위치와 초기 유닛, 생성 경로에서 첫 미연결 서비스, 같은 시드 결과의 결정성. 초기화와 GameInfo 조회의 통과만으로 이 결과들을 증명했다고 볼 수 없사와요.
