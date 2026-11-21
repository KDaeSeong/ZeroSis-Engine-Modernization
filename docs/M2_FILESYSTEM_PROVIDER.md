# Windows 파일 서비스와 실제 지도 입출력

2026-09-26 최신 통합: attempt_025·556개 패치·SDK 수정 파일 94개·제공자 16개의 정식 연결은 미해결 0개이며, 명시적 초기화·종료와 SDK WalkStack 및 도시 AI 전략 정리·게임/지도 생성 실패 정리 수정을 반영했사와요. 아래 이전 단계의 연결 차이는 당시 구성의 기록이랍니다. 현재 비교는 지도 15→2·지도 객체 15→5·로그를 제외한 파일 2→1·로그 1→0이며, [최신 초기화 계약](M2_GAMECORE_BOOTSTRAP.md)을 기준으로 검토하와요.

2026-09-26 갱신 / `FILESYSTEM_NATIVE_COMPONENT_PASS`, `FILESYSTEM_SDK_LINK_PASS_NOT_GAME_RUNTIME`이랍니다. 파일 제공자의 독립 제외/포함 연결 비교는 **4→3개**이며, 후속 로그 제공자까지 포함한 현재 정식 연결은 **2개**랍니다. attempt_021은 161개 GameCore 오브젝트·543개 패치·89개 SDK 수정 파일·제공자 15개를 사용하와요. GameCore DLL 생성·초기화·게임 실행은 아직 미완료이와요.

## 요구사항과 영향 범위

| ID | 요구사항 | 수용 증거 |
|---|---|---|
| FS01 | 기존 FIFile/FIFileSystem/FFileSystem 서명 유지 | SDK 헤더 수정 없이 /MD x64 제공자와 실제 SDK 지도 소비자 연결 |
| FS02 | 실제 파일 읽기·쓰기·편집·위치·길이 | 독립 Win32 읽기로 결과 바이트 대조, 확장 영역 0 채움, 길이 축소와 위치 보존 |
| FS03 | 실패한 저장의 기존 파일 보존 | 쓰기·플러시·닫기·교체 실패 및 디스크의 읽기 전용·잠긴 대상 검증 |
| FS04 | 경로·메모리 매핑·전체 읽기 | 한글·보조 평면 문자·긴 경로, 읽기 전용 매핑, 기본/사용자 할당기와 실패 검사 |
| FS05 | 실제 지도 호출부 통합 | SDK Save/Load/Preview 실행, 지도 실패 12개, 파일·객체 상태 보존 |
| FS06 | 독립 파일의 동시 처리 | 작업자 4개에서 서로 다른 대상에 128회 저장과 읽기 대조 |
| FS07 | 실제 GameCore 연결 요구 해소 | 같은 161개 오브젝트의 제공자 제외/포함 비교 4→3, 빈 파일 서비스 바인딩 없음 |
| FS08 | 원본·저장 계약·배포 경계 | 원본 SDK·설치 게임·MODS·저장 파일 무변경, 개발 프로젝트 Source→Build→Stage만 사용 |

새 소스는 `Source/Providers/FileSystem/SdkFileSystem.h/.cpp`랍니다. 지도 저장 형식·게임 규칙·Mod ID·버전·저장 키·스키마는 바꾸지 않았사와요. 기존 지도 구현을 새 파일 제공자와 연결해 시험했으며, 현재 게임 설치에 적용한 결과는 아니랍니다.

## 파일 수명과 실패 계약

쓰기·편집은 목적지와 같은 디렉터리에 충돌하지 않는 임시 파일을 `CREATE_NEW`로 만들고 진행하와요. 편집은 기존 내용을 먼저 복사하므로 입력 읽기 실패도 목적지를 바꾸지 않사와요. 확장 영역은 직접 0을 기록하며, 사용하지 않은 디스크 영역의 내용을 가정하지 않사와요.

명시적인 `Close`는 쓰기 오류가 없을 때 플러시·핸들 닫기·파일 교체를 순서대로 수행하와요. 최초 오류는 해당 파일 객체에 남아 이후 닫기에서 부분 내용을 게시하지 못하도록 하와요. 성공한 닫기만 FILE_OK를 반환하며, 플러시만으로 목적지를 바꾸지 않사와요. FIFile 포인터를 직접 삭제하면 미완료 쓰기를 폐기하와요. SDK FFileInstance의 자동 닫기는 지원하지만, 저장 오류를 확인할 호출부는 직접 Close 결과를 확인해야 하와요. 이 소유 객체는 복사하지 않는 계약이랍니다.

임시 파일 충돌은 기존 충돌 파일을 보존하고 새 이름으로 재시도하와요. 현재 시험 환경에서 읽기/매핑 핸들이 열린 목적지는 교체가 거부됐으며, 원본 보존과 핸들을 닫은 후 성공하는 재시도를 확인했사와요. 각 파일 객체는 단일 소유자가 사용하고 같은 경로의 복수 작성자는 호출부가 직렬화해야 하와요. 서비스 교체 `SetInstance`는 기존 호출과 객체가 모두 종료된 초기화/종료 경계에서만 사용하와요.

플러시 후 같은 디렉터리에서 `MoveFileExW(REPLACE_EXISTING | WRITE_THROUGH)`를 호출하며, 기존 목적지를 먼저 삭제하거나 다른 볼륨으로 복사하지 않사와요. 이 API의 교체·오류 계약은 [Microsoft MoveFileExW 문서](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-movefileexw)를 기준으로 삼았사와요. 확장 공간을 직접 0으로 채우는 이유는 [SetEndOfFile 문서](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-setendoffile)가 확장 영역의 내용을 정의하지 않기 때문이랍니다.

## 지원 범위와 남은 제한

- 좁은 문자열 경로는 엄격한 UTF-8, 넓은 문자열 경로는 UTF-16으로 처리하와요. 원본의 비공개 좁은 문자열 구현과 동일하다고 주장하지 않사와요.
- 기본 읽기·쓰기·편집, RANDOM_ACCESS·HIDE_ERRORS를 지원하와요. 비동기·BIG_ENDIAN·텍스트 인코딩 등 미구현 플래그는 명시적으로 거부하와요. 버퍼 크기 인자는 별도 사용자 버퍼 없이 Windows 캐시를 사용하와요.
- 읽기 모드만 메모리 매핑을 지원하며 반환 주소는 읽기 전용이랍니다. 빈 파일에는 매핑을 만들지 않사와요. 쓰기 모드에서 매핑을 요청하면 오류로 처리하와요.
- SDK 길이와 위치의 uint 계약 때문에 4 GiB 이상 파일을 읽기/편집에서 거부하와요. 경계의 UINT_MAX 위치는 GetLastError로 실패와 구분해야 하와요. 실제 게임의 64비트 메모리 수용 관문과 별개랍니다.
- 기본 전체 읽기 결과는 delete[]로, 사용자 할당기 결과는 같은 할당기의 Delete로 해제하와요. 실패 결과는 null·0이며 할당기의 Delete는 예외를 던지지 않아야 하와요.
- PAK 카탈로그와 자산 검색 경로는 미구현이며 IsFileCatalogEnabled는 false랍니다. 불완전 타입만 공개된 FFileErrorHandler는 설치하지 않아 null을 반환하와요. 오류는 SDK 반환값과 Windows 오류 번호로 전달하와요.
- 전원 차단·프로세스 강제 종료 뒤 복구, 실패한 임시 파일 삭제의 재시도/청소 정책, 기존 ACL·별도 데이터 스트림·메타데이터 보존은 후속 호스트/저장 정책 관문이랍니다. 현재 실패 시험을 모든 파일 시스템의 원자성이나 전원 차단 내구성 증거로 확대하지 않사와요.

SDK 아카이브에는 FIFileSystem의 바인딩은 있지만 구체적인 Windows 파일 구현은 확보되지 않았사와요. 따라서 이 결과는 실제 Windows 입출력과 공개 SDK 소비자의 검증이며, 원본 비공개 파일 서비스 전체와의 동등성 검증은 아니랍니다.

## 검증 결과와 재현

파일 서비스 1,973개 검사와 지도 통합 113개 검사, 합계 **2,086개**를 통과했사와요. 일반 오류 주입 21개와 추가 경로/닫기 경계, 실제 지도 오류 12개를 포함하와요. 지원하지 않는 플래그·잘못된 UTF-8·위치 넘침·4 GiB 희소 파일 거부, 임시 이름 충돌 보존, 닫기 실패 뒤 핸들 회수와 임시 파일 제거도 확인했사와요. 네 작업자의 128개 독립 파일 시험은 게임 계산 병렬화 증거가 아니랍니다.

제공자와 두 시험 실행 파일은 /W4 /WX 경고 없이 AMD64로 빌드했으며, 실행 전 DLL 의존성이 Windows와 C++ 런타임뿐인지 확인했사와요. 전체 GameCore의 기존 경고 343곳은 그대로랍니다. 예전 지도 구성요소의 메모리 전송 시험 기록에 있는 파일 시스템 미구현 표시는 그 독립 시험 범위이며, 이번 실제 디스크 통합의 증거는 별도 `evidence/filesystem`에 있사와요.

```powershell
python tools/build_filesystem_provider.py
python tools/verify_filesystem_provider.py
python tools/filesystem_evidence.py
# analyze_sdk_x64.py: FileSystem과 Logging을 포함한 현재 제공자 15개 사용
python tools/probe_filesystem_link.py
python tools/probe_world_builder_map_link.py
python tools/probe_world_builder_map_bridge_link.py
python tools/verify_world_builder_map_integration.py
python tools/stage_filesystem_provider.py
python tools/stage_world_builder_map_object.py
python tools/stage_world_builder_map_bridge.py
python tools/stage_sdk_x64_port.py
python tools/verify_project.py
```

검토 묶음은 `Stage/FileSystem`과 `Stage/GameCore_x64/Providers/FileSystem`에 있사와요. 파일 연결 비교에서는 Logging을 제외해 4→3의 범위를 보존하와요. [로그 제공자](M2_LOGGING_PROVIDER.md)까지 포함한 정식 연결의 남은 항목은 디버그 도우미 2개이며, 그 뒤 실제 x64 실행부·게임 결과 동등성·게임 멀티코어·UI/모드·저장/동기화 관문을 이어가야 하와요.

