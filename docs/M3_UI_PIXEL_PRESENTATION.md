# M3: 원본 UI 픽셀·창·입력 후보와 충돌 회귀

2026-10-03 KST 현재, 실제 GameCore의 살아 있는 순위 팝업 UI VM을 원본 그림·글꼴 렌더러와 자체 D3D11/DXGI 창에 연결하고, 닫힌 팝업의 그림·클릭 영역을 같은 창·장치에서 교체했사와요. 영어 직렬·한국어 FoundValue 4워커는 각각 50턴까지 통과했으며, 25·50턴마다 초기 1000×700·크기 변경 900×600·닫힘 900×600의 GPU 버퍼를 대조했답니다. Codex 시험 데스크톱의 `Present`는 모두 `DXGI_STATUS_OCCLUDED`였사와요. 사용자 화면·사람의 입력·도시 결정 UI·팝업 아래 세계 화면 복원은 아직 남아 있답니다.

## 요구사항과 변경 범위

목표는 기존 팝업의 Lua·XML·텍스처·글꼴·문자·색·컨트롤 키를 보존해 화면과 입력을 연결하는 것이랍니다. 변경 범위는 `Source/Presentation`, opt-in 경로를 추가한 `Source/Host`와 생성 UI header, 독립 `tools`·`Tests`와 검증기, 그리고 이 문서와 상태 요약이랍니다. 게임 규칙·밸런스·Mod ID·버전·저장 키·스키마 번호의 변경은 없사와요. 이번 동기화는 Source → 실행별 고유 Build까지이며, SDK 재컴파일·Stage·Civ V MODS·설치본 배포는 수행하지 않았답니다.

| 구성 | 구현·검증 범위 | 고정 검증 기록 |
|---|---|---|
| 네이티브 픽셀 렌더러 | 엄격한 `ZSUPIX01` 소유값 패킷, WIC DDS/PNG, D2D 소프트웨어 합성·클리핑·색 적용, O2/Od 각 33항목 | [bitmap renderer](../evidence/bitmap_renderer/20261002T171317Z_516c7fa8b73e/conformance.json) |
| 원본 그림·글꼴·배치 | FPK v6 및 BC001/2/4/8 사전+색인 복원, alpha8 GGXML 글꼴, 원본 9분할 스타일, 실제 DB 인라인 색, EN/KO retained 상태의 PNG | [최종 원본 픽셀 기록](../evidence/ui_popup_pixels/20261002T175437Z_6a2da4d9ab82/conformance.json) |
| 독립 창·입력 큐·GPU 버퍼 | 소유 HWND의 메시지 처리, 1920×1080 논리 좌표, Escape/Enter·클릭·닫기 입력, 실패·종료 수명, GPU 읽기·크기 변경·같은 장치의 장면 교체와 실패 보존, O2/Od 각 54항목 | [최종 창 회귀](../evidence/bitmap_window/20261003T011316Z_57ba4ffcfd47/conformance.json) |
| 공식 Lua 입력 | 실제 팝업의 키·CloseButton 콜백, 숨김·닫힘·잘못된 키 거부, 중복 입력의 타이머·난수 보존 | [Lua 입력 구성요소](../evidence/ui_presentation_input/20261002T171126Z_4d4f80be2042/conformance.json) |
| 실제 SDK VM·GPU 창 입력 통합 | EN 직렬·KO FoundValue 4워커 각 50턴, GPU 버퍼 12장·같은 창의 닫힌 장면 갱신·이전 클릭 영역 제거·공식 callback·타이머·RNG·저장·AI 점수 대조 | [최종 통합 기록](../evidence/live_ui_window/validators/20261003T013008Z_0f6efdd27e/conformance.json) |

픽셀 기록 SHA-256은 `b6f4ad513bbffdea6d2dece0abb5f1966d879f549f510a7e5768eaf27810e318`, 현재 54항목 창 회귀 기록은 `3d157956c4e2f8efa228a23de5c8bea5b887b6277ba43892ef229c3a743895c4`랍니다. 각 기록은 동결 소스·의존성·산출물·로그의 해시를 보유하와요.

## 현재 같은 창·장치의 닫힌 장면 갱신

[현재 실행부 빌드](../evidence/ui_window_host/20261003T011457Z_7c714315c54b/build_result.json)는 세 TU와 501개 소비 입력을 동결한 x64 후보랍니다. EXE SHA-256은 `e34674c0fe2d03e2482d112aca3523e5bde168da30f9f21d56ba3ab3e43a61a5`이며, 기존 GameCore DLL `a58a0d20cbaecad13ea248fe362d0c15bb97096802b9f60c5ef5f0dd8bb90c07`를 재사용했사와요. SDK 재컴파일이나 Stage/MODS 배포는 하지 않았답니다.

| 언어·FoundValue 워커 | 현재 실제 실행 | 종료·관찰 |
|---|---|---|
| 영어·0 | [012258Z_910241fe89dd](../evidence/save_restore/20261003T012258Z_910241fe89dd/result.json) | 50턴·팝업 2건·GPU 캡처 6장·exit 0·core unload |
| 한국어·4 | [011934Z_1bcbba8ad56c](../evidence/save_restore/20261003T011934Z_1bcbba8ad56c/result.json) | 50턴·팝업 2건·GPU 캡처 6장·exit 0·core unload |

`BitmapWindow::UpdateScene`은 새 소유 그림과 hit map을 모두 준비한 뒤 같은 창·D3D11 장치·swapchain에서 교체하와요. 소유 스레드·scene 크기·PNG 크기·키·입력 큐를 검사하고, 실패하면 기존 그림·hit map·장면 번호를 보존한답니다. 입력에는 장면 번호를 붙이며, 이미 대기 중인 이전 입력은 갱신을 거부하도록 했사와요. O2/Od 각 54항목은 정상 그림 교체·새 클릭 영역·기존 입력 보존·잘못된 PNG·다른 스레드·닫힌 창·빈 장면을 검사했고, 각 구성의 초기·크기 변경·교체·실패 뒤·빈 장면 GPU 캡처 다섯 장을 보유한답니다.

실제 SDK 경로는 `--ui-window-refresh --ui-window-display --ui-window-popups`와 명시적인 창 명령에서만 `display-refresh` 프로필을 선택하와요. 기존 `display-resize` 및 headless 경로는 유지했답니다. 원본 callback으로 닫힌 snapshot은 active=false·timer=0·closed lifecycle을 유지하며, 닫힌 context의 retained tree는 보존하고 화면 기여만 texture·sprite·hit 0의 패킷으로 컴파일하와요. handshake 뒤 `UpdateScene`으로 장면 번호 1→2를 교체하고, 같은 HWND·소유 TID·nonzero 장치 identity를 전후 대조했답니다. 장치 identity는 소유 D3D11 포인터의 진단값이며 게임 SDK 포인터를 보관하는 기능은 아니랍니다.

닫힌 네 장의 900×600 GPU 버퍼는 전체 2,160,000픽셀이 `(0,0,0,255)`이며 오차·제외 0으로 검사했사와요. 별도로 네 원본 1920×1080 PNG의 전체 8,294,400픽셀이 `(0,0,0,0)`임을 확인했답니다. 초기·크기 변경 여덟 장의 안정 영역 4,929,600픽셀과 합하면 GPU 대조 픽셀은 7,089,600개이며, 그 여덟 장의 분수 배율 경계 제외 30,400개는 그대로 기록했사와요. 이는 팝업의 화면 기여를 지워 빈 버퍼로 만든 검증이며, 팝업 아래의 세계 화면을 복원하거나 도시 생산·연구 결정을 그린 결과는 아니랍니다.

갱신 이후 부모가 이전 CloseButton 위치를 클릭하고 Escape를 보내면 클릭은 빈 hit map에서 전달되지 않고 Escape 한 건만 장면 번호 2로 전달돼 비활성 팝업 경계에서 거부됐사와요. 부모는 교체 전후 입력 생산을 handshake로 멈추는 관리된 시험 묶음을 사용하와요. `GetMessageTime`의 밀리초 경계는 보조 방어이며 같은 틱의 실제 입력을 엄격히 분리하지 못하므로 비동기 사람 입력의 장면 경계 격리를 입증하지 않사와요. 닫힌 snapshot·타이머·난수·추가 입력 수락 0을 대조했고, 같은 언어·워커 기준의 세 archive·모든 continuation 상태·FoundValue 200회 192,000점·CitySite 95점도 같았답니다. manifest의 Host EXE 해시 한 줄 교체와 CvMap GUID의 기존 16바이트 정규화 외에 gameplay 구획을 변경하지 않았사와요.

[최종 갱신 기록](../evidence/live_ui_window/validators/20261003T013008Z_0f6efdd27e/conformance.json)의 SHA-256은 `835331488e30bfa25d6073b11a98dbd0ee366035e394d65b1fa64615c249bb16`이며 검사기 21개 local module의 동결 입력과 54항목 구성요소·빌드·런타임·캡처를 연결했사와요. 현재 실행의 session 1·`WinSta0`·`CodexSandboxDesktop-6a63f6b133814cca4f25cdf9cd59bfa8`에서 모든 `Present`는 `0x087A0001`였답니다. GPU 출처·장치·창 소유권은 소스와 실행 체인에서 확인하고 순수 PNG 검사는 픽셀 내용만 판정하와요. 사용자 데스크톱 표시·사람의 입력·전체 엔진 동등성·물리 멀티코어·성능 향상의 proof로 확대하지 않사와요.

## 이전 GPU 버퍼·크기 변경과 실제 SDK 통합

[앞선 실행부 빌드](../evidence/ui_window_host/20261003T001657Z_857842a564ad/build_result.json)는 세 TU와 501개 소비 입력을 동결했으며 경고·미지정 DLL import 없이 x64 EXE를 만들었사와요. EXE SHA-256은 `d7ed7d722865fb4e03440037d4b6e02f1ab867d5d220b1b2acf7e495681face0`랍니다. 아래 역사적 실행과 같은 GameCore DLL `a58a0d20cbaecad13ea248fe362d0c15bb97096802b9f60c5ef5f0dd8bb90c07`를 재사용했사와요.

| 언어·FoundValue 워커 | 당시 실제 실행 | 종료·관찰 |
|---|---|---|
| 영어·0 | [002254Z_c05d8abe3da5](../evidence/save_restore/20261003T002254Z_c05d8abe3da5/result.json) | 50턴·팝업 2건·GPU 캡처 4장·exit 0·core unload |
| 한국어·4 | [002055Z_3c33e58524a2](../evidence/save_restore/20261003T002055Z_3c33e58524a2/result.json) | 50턴·팝업 2건·GPU 캡처 4장·exit 0·core unload |

두 실행은 Explore·CitySite 워커 0과 빈 활성 모드 목록을 사용하와요. 명시적인 창 시험 명령에 `ZEROSIS_UI_WINDOW_PROFILE=display-resize`를 함께 지정할 때만 새 표시·크기 변경 시험을 선택하며 기존 기본 경로는 유지한답니다. HWND의 실제 PID·소유 TID·client 크기·표시 상태를 확인하고, 하드웨어 D3D11 장치의 DXGI swapchain에 D2D로 그렸사와요. `DrawBitmap → EndDraw → CopyResource → Map → PNG → Present` 순서로 같은 backbuffer를 읽는 경로를 소스·빌드·실행 해시로 연결했답니다. DXGI factory는 장치의 COM adapter를 통해 얻으므로 EXE의 직접 `dxgi.dll` import가 필수인 것은 아니랍니다.

각 팝업은 표시 상태를 설정한 뒤 1000×700에서 캡처하고, 900×600으로 크기를 바꿔 버퍼를 재생성하고 다시 캡처했사와요. 장치 종류와 render/present 횟수의 증가를 확인했고, 여덟 장의 안정된 내부·검은 여백에서 총 4,929,600개 픽셀을 대조했답니다. 분수 배율의 화면 경계 30,400개 픽셀은 별도 제외 수로 기록했사와요. 원본 texel 경계의 정확한 동률과 `1e-4` texel 이내 반올림은 이웃 후보를 명시적으로 비교하며 검사를 생략하지 않사와요. 채널 오차는 최대 1바이트이고 모든 캡처 픽셀의 alpha 255도 확인했답니다. 순수 PNG 검사는 픽셀 대조의 범위이며 GPU 출처와 HWND 소유권은 별도 실행 기록과 소스 경로에서 확인하와요.

실행은 session 1의 `WinSta0` 안 `CodexSandboxDesktop-d47f6d5a7ae6188e6de5ae15bb1e4b50` 데스크톱에서 이뤄졌사와요. 실제 `Present` 결과는 모두 `0x087A0001`(`DXGI_STATUS_OCCLUDED`)이며 성공적인 사용자 화면 표시로 바꾸어 판정하지 않았답니다. 시험 창의 GPU 그림·버퍼 읽기·크기 변경·자동 입력이 검증 범위이고, 사용자 데스크톱 픽셀과 실제 사람의 입력은 미검증이랍니다.

크기를 바꾼 창에서도 25턴 Escape와 50턴 실제 CloseButton 키 12 클릭을 각각 한 번 수락하고 늦은 입력을 거부했사와요. 공식 Lua callback·timer 1→0·RNG 보존, 팝업별 20개 control bounds와 초상화별 980개 원본 픽셀을 확인했답니다. 같은 언어·워커의 기존 기준과 FoundValue 200회·192,000개 ordered 점수 및 area totals·호출 순서, CitySite 95개 점수·reduction, 계속 진행 상태·명령·event가 같았사와요. 각 실행의 세 archive는 manifest에서 Host EXE 해시 한 줄 차이만 확인하고, 나머지 132구획은 기존 지도 GUID 16바이트 정규화 외에 일치했답니다.

[앞선 GPU 통합 기록](../evidence/live_ui_window/validators/20261003T002647Z_40151c5def/conformance.json)의 SHA-256은 `2d09e77eae42db779ed848dec723f5add46241ab53b10e8217d2c81a74688e85`랍니다. 검사기 21개 local module의 실행 전후 해시와 당시 창 구성요소의 O2/Od 각 38항목 기록을 함께 연결했사와요. 초기 GPU 시험의 WIC 픽셀 형식 오류와 재진입 방어에 가려진 `WM_SIZE` 처리 오류는 수정했으며 실패 증거도 보존했답니다. 지속된 표시 가림 상태는 위 시험 데스크톱의 관찰 결과로 남겼사와요.

## 이전 숨긴 창의 SDK 통합 이력

앞선 숨긴 창 실행부의 [고유 빌드](../evidence/ui_window_host/20261002T183451Z_d0ed25e9338f/build_result.json)는 HostMain·BitmapWindow·BitmapRenderer의 세 TU를 각각 컴파일하고, 498개 소비 입력을 동결해 다시 빌드했사와요. 경고·미지정 DLL import는 없었답니다. EXE 해시는 `b7aa58469751ee7747683407966db752bd71a8e4b42959d4f2d755619649545e`이며, 기존 GameCore DLL `a58a0d20cbaecad13ea248fe362d0c15bb97096802b9f60c5ef5f0dd8bb90c07`와 provider를 재사용했사와요. GameCore 구현을 새로 컴파일하거나 실행부에 정적으로 연결하지 않았답니다.

| 언어·FoundValue 워커 | 실제 실행 | 기준 실행 | 종료·관찰 |
|---|---|---|---|
| 영어·0 | [184455Z_f4dd2d31708d](../evidence/save_restore/20261002T184455Z_f4dd2d31708d/result.json) | 154859Z_8e35b68dfaa0 | 50턴·팝업 2건·exit 0·core unload |
| 한국어·4 | [184319Z_0703e6361b09](../evidence/save_restore/20261002T184319Z_0703e6361b09/result.json) | 155207Z_38c434218a11 | 50턴·팝업 2건·exit 0·core unload |

두 실행의 Explore·CitySite 워커는 0이며 활성 모드 목록은 비어 있답니다. 언어별 같은 워커의 [기존 8개 실행 기록](../evidence/found_value_shared_sdk_runtime/20261002T155959Z_f8b7cb268407/conformance.json)을 SHA-256으로 고정해 기준으로 사용했사와요. 새 연결 경로는 `--check-save-restore-ui-window-actions <language> 48` 명령으로 명시적으로 선택하며, 기존 headless 검증은 기본값 그대로 보존하와요.

`game.Update()`가 반환한 뒤 소유 스레드와 GameCore 잠금을 유지한 채 팝업 snapshot을 전달하와요. 부모는 동결한 helper로 원본 자료와 패킷을 준비하고, 실제 SDK 자식 프로세스가 PNG를 렌더링하고 창을 생성하와요. 원본 snapshot은 준비 전후·창 생성 뒤까지 같았답니다. HWND의 PID·TID를 실제 OS 조회값과 대조한 뒤 전체 시험 입력을 큐에 넣고 별도 handshake로 메시지 처리를 시작하와요. WndProc는 입력을 큐에만 넣으며 SDK·Lua 호출은 소유 스레드에서 수행한답니다. 팝업이 활성인 동안 다음 GameCore update는 진행하지 않사와요.

25턴에는 Escape를 받아들이고 이후 Return을 거부했으며, 50턴에는 실제 CloseButton 키 12의 좌표 클릭을 받아들이고 이후 Escape를 거부했사와요. 각 창은 정확히 두 입력을 전달하고 하나만 수락했답니다. F1·letterbox 클릭·반복 key-down은 native 경계에서 걸러졌사와요. 수락한 입력은 공식 Lua handler로 timer 1→0을 한 번만 수행하고, 늦은 입력은 timer 0을 유지하며 Lua에 다시 들어가지 않았답니다. 네 창의 모든 입력은 native synchronous RNG seed를 보존했사와요.

각 언어의 checkpoint·restored checkpoint·final archive는 133구획을 검사했사와요. 구획 1,0은 각각의 실제 bundle manifest와 정확히 같고, 두 manifest의 차이는 검증된 Host EXE SHA-256 한 줄뿐이랍니다. 나머지 132구획은 지도 GUID의 기존 16바이트 정규화 외에 같았사와요. 계속 진행 턴의 상태 frame·snapshot·명령·event, popup shown/closed 상태·원본 draw 순서도 기준과 같았답니다. 턴의 `duration_us`와 scoring의 실행 시간·스케줄링 식별자는 측정값으로 구분하며 성능 향상을 주장하지 않사와요.

언어별 FoundValue 200회·192,000개 ordered plot score와 area totals·호출 순서, CitySite 1회·95개 ordered score와 reduction도 원시 실행 로그에서 기존 parser로 읽어 기준과 직접 대조했사와요. 한국어 worker 경로의 공유 입력 layout 200건도 검사했답니다. 각 팝업은 20개 캡처된 control bounds와 두 초상화별 원본 DDS 픽셀 980개를 대조했사와요. PNG는 한국어 [25턴](../Build/NewGameRuntime/20261002T184319Z_0703e6361b09/sessions/85fe44d2bea43eaa0cb84701a353ce58/presentation-popup-1/popup.png)·[50턴](../Build/NewGameRuntime/20261002T184319Z_0703e6361b09/sessions/85fe44d2bea43eaa0cb84701a353ce58/presentation-popup-2/popup.png)에서 확인할 수 있답니다.

앞선 숨긴 창 통합 기록의 SHA-256은 `7a1496c79310f1e91609302e72359011dd02f61fcb7731959edbb094638a4554`이며, 당시 검사 코드의 16개 local module closure와 실행 요청·로그·그림·패킷·소스 해시를 보유하와요. 대형 벡터와 게임 자료를 또 복제하지 않고 기존 원시 로그의 해시와 의미 signature를 연결했답니다. 초기 통합 시도의 Win32 선언 누락·중복 source 기록, 부모 기록기의 문자열 경로 오류, 263자 원본 UI 보관 경로 문제는 각각 실패 증거를 보존하고 수정했사와요. 실제 자료는 원본 경로·해시를 manifest에 보관하면서 짧은 파일명으로 동결하와요. 실패 실행과 통과 기록은 구분했답니다.

## `bitmap_window_O2.exe` 접근 위반 대응

이 파일은 새 창·입력 구성요소의 시험 프로그램이랍니다. 이전 기록 `173607Z_2f3b60df4eb8`, `173718Z_3aebb8714efe`는 종료 코드 `3221225477`(`0xC0000005`)와 빈 시험 출력을 남겼사와요. 기존 실패 EXE는 이후 다시 실행하지 않았답니다.

코드 검토에서 WIC·D2D 인터페이스가 남아 있는 상태로 `CoUninitialize`를 먼저 호출하는 순서를 발견했사와요. 소멸자에서 창과 렌더링 대상, 모든 COM 소유물을 먼저 정리하고 마지막에 COM 초기화를 균형 있게 해제하도록 고쳤답니다. [Microsoft의 COM 종료 설명](https://learn.microsoft.com/en-us/windows/win32/api/combaseapi/nf-combaseapi-couninitialize)과 맞춘 수명 순서랍니다. 과거 충돌의 예외 주소·모듈은 확보하지 못했으므로, 이 결함이 그 접근 위반의 직접 원인이었다고 확정하지 않사와요.

또한 생성 실패 뒤 재시도와 닫힌 객체 재사용이 COM 초기화 횟수·닫힘 상태를 틀어지게 만드는 결함을 막았사와요. 현재 객체는 유효한 인수를 받은 `Create` 시도를 한 번만 허용하고, 생성·호출·파괴를 같은 소유 스레드에서 수행하는 계약이랍니다. 소유 스레드 밖 파괴는 fail-fast 계약 위반으로 처리하며, 자동으로 다른 스레드에 파괴를 전달하는 기능은 없사와요. 그 위반 경로의 실행 시험은 앞선 28·38항목과 현재 54항목에 포함되지 않았답니다.

앞선 O2 PID 27064와 Od PID 42384는 모두 28항목을 통과하고 `0x00000000`으로 종료했사와요. 각 실행은 PNG 부재에 따른 생성 실패·같은 객체 재시도 거부, 다른 스레드의 메시지·입력 호출 거부, 정상 창 생성·크기 변경·좌표 변환·닫힘·재생성 거부를 검사했답니다. 이후 GPU 경로의 O2/Od 각 38항목은 버퍼 캡처·크기 변경·불투명 여백, 같은 파일 덮어쓰기 거부, 과대 크기의 사전 거부와 다른 스레드·닫힌 창의 캡처 거부까지 통과했사와요. 현재 O2 PID 30928·Od PID 35516은 장면 교체 회귀를 포함한 각 54항목을 `0x00000000`으로 종료했고, 양쪽 로그의 COM 초기화 2회·해제 2회·소멸 완료를 확인했답니다.

시험 전 빌드·EXE 해시·시도 상태를 기록하고, 시작한 자식 PID·종료 코드·로그·시간 초과 정리를 즉시 연결하와요. 시험 프로세스의 SEH는 예외 코드·주소·모듈을 기록하고 실패 코드로 종료하므로 오류창 억제가 성공 판정을 만들지 않사와요. `SetErrorMode`와 `WerSetFlags(WER_FAULT_REPORTING_NO_UI)`는 이 시험 프로세스에 적용하고 부모의 이전 오류 모드는 `finally`에서 복구한답니다. [오류 모드 문서](https://learn.microsoft.com/en-us/windows/win32/api/errhandlingapi/nf-errhandlingapi-seterrormode)

## 실제 SDK 상태와 원본 픽셀의 연결

EN 상태는 `20261002T161323Z_422f18cf0e62`, KO 상태는 `20261002T155207Z_38c434218a11`의 실제 50턴 SDK 실행에서 봉인한 첫 순위 팝업이랍니다. 각 실행의 `result → request → host candidate/GameCore build → 실행 입력` 해시를 대조하고, 정확한 언어 인수·고유 실행 폴더·빈 활성 모드 목록·accepted bundle을 확인했사와요. 현재 그림 생성은 그 상태를 읽기만 하며 GameCore나 Lua를 다시 실행하지 않사와요.

EN은 224개 sprite, KO는 126개 sprite이며 각각 15개 텍스처와 실제 CloseButton 키 12의 영역 `(745,804)–(895,836)`을 보유하와요. 두 언어 모두 별도로 캡처된 20개 컨트롤의 좌표·크기를 계산 결과와 대조했답니다. 기존 runtime이 크기를 측정하지 않은 Label·스타일 컨트롤 9개는 제외 사유를 기록해 남겨 두었사와요.

Portrait 키 16·26은 각각 원본 atlas 오프셋 `(0,0)`, `(384,128)`에서 그리와요. 각 초상화의 중앙 영역에서 980개 불투명 표본을 원본 DDS와 별도로 대조했답니다. 현재 native renderer의 linear interpolation을 픽셀 중심에서 계산하고 채널당 1바이트 오차를 허용하와요. 프레임·문명 아이콘·행 구분선을 초상화 검증에 섞지 않았으며, 두 언어 모두 네 초상화 검사를 통과했사와요. 원본 게임 화면과의 픽셀 비교는 아직 아니랍니다.

FPK 해석 37항목, 글꼴 7항목, 배치 32항목도 동결 입력으로 통과했사와요. 전체 게임 팩이나 SDK를 새로 복제하지 않고 선택된 원본 DDS·색인·글꼴·XML·증거만 보유하와요. 결과는 [영어 PNG](../Build/UiPopupPixels/20261002T175437Z_6a2da4d9ab82/en_US/popup.png)와 [한국어 PNG](../Build/UiPopupPixels/20261002T175437Z_6a2da4d9ab82/ko_KR/popup.png)에서 확인할 수 있답니다.

## 남은 실게임 관문과 회귀 위험

- 현재 연결 검증은 시험 데스크톱의 자체 HWND GPU 버퍼와 크기 변경·자동 메시지 입력을 포함하와요. 사용자 데스크톱의 가리지 않은 실제 표시·사람의 키/마우스 입력·입력 후 gameplay 상태에 따른 동적 재렌더링은 남아 있답니다.
- FPK 우선순위는 E2 → E1 → base의 명시적 후보 정책이며 retail 규칙은 아직 확인하지 못했사와요. 별도의 `FTXTInterface Compressed` 형식은 지원하지 않사와요.
- 글꼴 spacing border·baseline·shadow 효과, 혼합 9분할 edge·Full 스타일의 세부 의미는 원본 화면과 교정해야 하와요. 글꼴 대체 없이 원본 atlas를 사용했지만 retail pixel equivalence는 미검증이랍니다.
- ScrollBar handle·자동 숨김·스크롤 입력·hover·tooltip, 도시 생산·연구 UI와 다른 팝업·세계 렌더링·실제 오디오는 남아 있사와요.
- 활성 모드·열린 UI를 포함한 저장·복원·retail 저장 컨테이너·기준판 동등성·장기 회귀·성능 향상·정식 Stage 승격은 전체 엔진 관문으로 유지하와요.

## 중간 산출물 정리

큰 검증 단계 뒤의 보관·정리 기준을 프로젝트 [AGENTS.md](../AGENTS.md)에 남겼사와요. 최신 통과 실행 파일·비교 기준·동결 입력·소스·로그·저장·캡처·검증 기록이 참조하는 파일을 보존하고, 다시 생성 가능한 미참조 중간 파일부터 정리하와요. 앞선 [정리 기록](../evidence/build_tidy/20261003T003543Z_db52af1dd9cc/cleanup.json)은 UI Host 세 빌드의 미참조 최종 TU 오브젝트 9개·19,349,809바이트를 제거했답니다. 현재 갱신 검증 뒤에도 미리보기 후 [추가 정리 기록](../evidence/build_tidy/20261003T013227Z_03a66ab8b52b/cleanup.json)으로 최신 UI Host의 미참조 오브젝트 3개·6,545,498바이트(6.24MiB)를 제거했사와요. 두 정리의 합계는 25,895,307바이트(24.70MiB)랍니다. discovery 및 해시 참조 구성요소 오브젝트·실행 파일·소스·저장·캡처를 보존하고 삭제 뒤 참조 산출물 해시를 대조하와요. 설치본·MODS·사용자 저장은 변경하지 않았답니다.

현재 proof·빌드·창 구성요소·실행 요청·팝업 manifest에 연결된 보존 파일 1,115개와 현재 검사기 소스 21개를 삭제 뒤 다시 해시 대조했사와요. [보존 확인 기록](../evidence/build_tidy/20261003T013227Z_03a66ab8b52b/retained_check.json)은 sealed proof 불변, 미리보기와 실제 삭제 목록 일치, 12장·7,089,600개 GPU 픽셀 집계를 함께 확인한답니다.

창 수명 회귀를 재현할 때에는 `C:\Python314\python.exe -B -X utf8 tools\verify_bitmap_window.py`를 프로젝트 폴더에서 실행하와요. 원본 픽셀 후보는 같은 Python으로 `tools\render_ui_popup.py`를 실행하와요. 각 도구는 새 고유 Build와 증거를 만들며, 이전 실패 파일을 직접 재실행하는 방식으로 재현하지 않사와요.
