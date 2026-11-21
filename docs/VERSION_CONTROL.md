# Git 형상관리 범위

이 저장소는 ZeroSis' Engine Modernization의 작성 소스·검사·도구·문서와 SDK 수정 패치를 관리한다. 공개 배포본이나 독립 실행 가능한 게임 설치 묶음이 아니다. 실게임·화면 확인 보류는 그대로 유지한다.

## 포함

- `Source`의 호스트·렌더러·이식·동시성 등 작성 코드와 Lua 소스/저작권 고지.
- `Tests`, `tools`, `docs`와 실행 진입점.
- `evidence` 안에서 작성한 Python/C++/패치와 Claude 인계 소스. 동결 제공자 사본·실행 결과 데이터는 제외한다.
- `patches/sdk-bnw-x64.patch`: 현재 원본 SDK 기준의 전체 수정분. 원본/수정 트리 파일별 SHA-256은 `sdk-bnw-inputs.json`에 있다.

## 로컬 입력으로 보존

원본 게임 자산, `Source/Assets`, 원본 SDK와 생성된 `SDK_BNW_x64`, 외부 제공자 `ThirdParty`, 원본 UI를 포함한 대형 자동 생성 헤더, Build/Stage/Play, 저장 파일, 실행 결과·캡처·데이터베이스는 업로드하지 않는다. 기존 파일을 삭제하거나 이동하는 규칙이 아니다.

원본 SDK 폴더는 프로젝트 초기에 확보한 바이트 기준이다. 기존 `sdk_x64_patches.json` 이후 직접 보정한 변경도 새 SDK 패치에 포함한다. SDK 작업 후 다음을 실행한다.

```powershell
python -B tools/refresh_sdk_version_control.py
git add patches
git add <변경한-작성-소스>
git commit -m "변경 목적"
git push
```

현재 작업 폴더에서는 커밋 전에 SDK 패치와 실제 SDK 수정 트리의 일치, 포함 파일·크기·비밀 값 형태를 검사한다. SDK 변경 후 패치 갱신을 빠뜨리면 커밋을 중단한다. 새 복제본에서 같은 검사를 켜려면 `git config core.hooksPath .githooks`를 실행한다. 필요하면 `git config zerosis.python <Python-실행파일>`로 검사에 쓸 Python을 지정한다.

줄바꿈 자동 변환은 사용하지 않는다. SHA가 고정된 기존 소스 바이트를 그대로 보존하기 위한 설정이며 일반 소스 비교는 계속 가능하다.

## 복제와 빌드의 경계

새 복제본에는 위 로컬 입력이 없다. 맞는 원본 SDK를 준비하고 manifest의 SHA를 확인한 뒤, 새 수정 SDK 경로에 원본 바이트를 준비하여 `git apply --check patches/sdk-bnw-x64.patch`와 `git apply patches/sdk-bnw-x64.patch`를 적용한다. 현재 사용 중인 SDK 위에 같은 패치를 다시 적용하지 않는다. `--reverse --check`는 현재 수정 SDK와 패치의 연결을 파일 변경 없이 검증한다.

과거 빌드 도구의 고정 제공자·이력 JSON·로컬 경로도 별도 입력이다. Git 복제만으로 완전한 새 환경 빌드가 되는 것으로 보고하지 않는다. 이 저장소는 먼저 소스 이력·검토·되돌리기와 공동 작업의 기준을 제공한다. 검증된 로컬 실행 묶음과 사용자 저장은 기존 위치에서 보존한다.
