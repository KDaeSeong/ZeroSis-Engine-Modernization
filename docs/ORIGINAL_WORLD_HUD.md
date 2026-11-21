> 2026-11-08: Current Host `20261108T002841Z_2b25aaa753e3` and unchanged SDK430 are prepared in `20261108T003146Z_40a8030edf08` with full current/frozen closure, the V4 front-end sidecar and 189 runtime files verified. This wave gates the options volume arrow keys by the retail pointer-over state (Slider state bit 0x10000) on top of the native offline follow-up pair `986e`/`527e`, and retires the older `8837`/`1fba` pair by user decision. Native acceptance remains held. See [original menu offline scope](ORIGINAL_MENUS_OFFLINE.md).

# Original world HUD viewport and camera wheel

> 이전 준비 기록(2026-11-01): 당시 Host `20261101T074006Z_c2fd2fe9be38`와 선택 SDK `430f3122`의 새 격리 준비본 `20261101T080450Z_424fb64608b2`을 파일 검사로 확정했다. 화면 확인과 실제 실행은 보류하며, 기본 실행본 승격과 실게임 수락은 수행하지 않았다.


The world renderer now uses one diagnostic-HUD condition for both map width and
fallback drawing/hit targets. When the original TopPanel, UnitPanel and
ActionInfoPanel are all ready, the map uses the full 1920-pixel output width and
the diagnostic right panel contributes no drawing or buttons. Partial HUD
configurations retain the previous 1380-pixel map viewport. Original full-screen
modal presentation remains full width.

BitmapWindow now accepts an explicitly enabled, scene-generation-bound world
wheel viewport. Original ScrollPanel ownership, including empty panel space,
and ordinary UI hit ownership take priority. Modal/preparation/stale input is
rejected. The game loop consumes world-owned wheel input through the existing
camera zoom, preserving fractional wheel deltas and opposite-direction order at
the zoom limits. Existing keyboard camera controls and original UI scroll
encoding are preserved. The new input type is an in-memory event; the save and
scene file formats are unchanged.

The initial viewport/wheel production changes are limited to WorldViewRenderer.cpp, BitmapWindow.cpp/.h,
WorldCameraControls.h and InteractiveGameLoop.h. Their exact prior contents are
anchored to Host build 20261024T042219Z_e6399c82ee5c and recoverable from five
changed-file gzip backups. Game rules, balance, SDK, Mod IDs, save keys, default
release, installed MODS and user saves are unchanged.

## Verification and limits

`evidence/original_world_hud/component/result.json` records actual O2 and Od/RTC1
console component executions. Each performed 18 software-WIC renders, covered
eight HUD and eight full-screen configurations, checked full-width pixels and
ordered hit targets, and exercised 14 camera-wheel arithmetic cases. Unused
terrain functions are fail-closed stand-ins and were never called. No Host,
SDK, window, swapchain or D3D terrain/device was started by these checks.

The current production HostMain and BitmapWindow also passed compile-only
checks with their retained language/define settings and current include roots.
An initial validator include-path translation failure happened after both
component modes passed; its receipt is preserved. Only the missing SDK include
mapping and compile-only phase were repaired; the passing component modes were
not rerun.

This proves the software map/HUD boundary, camera arithmetic and source
compilation. It does not prove actual WM_MOUSEWHEEL routing, original HUD pixels,
the GPU terrain viewport, a complete game or original UI/3D equivalence. The
new linked Host `20261024T055841Z_974a5be57533` includes these five source changes. All five
translation units compiled, linked and passed independent static attestation.
The private run `20261024T070230Z_cbbd79f1cbb6` now contains this Host and
the selected `430f3122` SDK. It was executed once after direct human approval.
The actual hardware terrain output used 1920x1080 with map width 1920;
the initial visible window showed the original unit panel without the
diagnostic right panel. This is partial presentation evidence, not full
original UI/3D equivalence or camera-wheel acceptance.
Build, attestation and intermediate-retirement receipts are retained under
`evidence/original_world_hud/host_build/974a5be5753302c4498c/`.
The old stop records are preserved. Direct human approval resumed only this
trial. The user subsequently deferred screen verification; no further
Host/SDK/window trial is authorized by automatic continuation.

The driver exited normally with return code 0, no error and SDK unload.
An initial autosave and final native checkpoint were written at turn 0.
The initial and final states both contain no cities and two units.
Recorded unit-panel events are pointer movement, not a successful click.
No world-wheel or next-human-turn event was observed. Later screen captures
returned another window even after one target reselection, so app input
stopped. City founding, turn advancement, wheel routing and save loading
remain unverified. The empty top information stack at city count 0 is the
original TopPanel Lua branch and does not require a production change.
The trial wrapper did not explicitly set ZEROSIS_UI_POLICY_INFO; its
inherited value was not measured. A future authorized trial should set the
prepared value 1 before opening the Social Policy context.
Exact inputs, process results and native save hashes are recorded under
`evidence/original_world_hud/pair_preparation/execution/`.

## Retained outputs

The two passing component executables, maps, dependency reports, source backups
and compact evidence are retained. Four generated object files and two build
environment scripts were retired after verification: 5,906,561 logical bytes,
5,914,912 allocated file-data bytes. No complete runtime or asset copy was made
for this work. The original game and prior private trial/save evidence remain.

## Pointer-hover repaint follow-up

UiPanelRepaint.h separates input consumption from actual scene changes. The
four HUD dispatch paths retain their existing return values and exception
propagation. Pointer snapshots use the same owner clock without an SDK tick;
only actual hover/tooltip changes request repaint. Keyboard, camera, modal,
stale-generation and preparation protections remain in the original paths.
InteractiveUiSession.h, InteractiveGameSession.h and InteractiveGameLoop.h
use this helper. Save and mod schemas are unchanged.

Actual native component runs passed 27 cases and 150 checks in each of O2
and Od/RTC1. Seven retained-original Lua fixtures cover repeated hover,
key-zero no-ops, actual hover/tooltip changes, and existing click/scroll
behavior. ActionInfo performed 144 checks and Notification 149. These are
component fixtures with synthetic SDK bindings, not live game behavior.

The current Host `20261024T082423Z_b604cddf0d2d` compiled all five translation units and
linked once with 550 actual compiler inputs, 86 source-manifest entries and
593 current inputs. Independent file-only attestation checks its 67 exact
embedded payloads, 24 imports, and restore marker. Four source copies total
420,065 bytes; 589 immutable inputs share existing file identities.
The prepared runtime `20261024T091253Z_713037fbac49` now pairs this Host
with the selected `430f3122` SDK. It has not been launched or accepted in a
native UI test. The earlier cbbd trial and its partial native observations remain.
Screen verification remains deferred by the user. This fix is not evidence
that the previously unobserved click or wheel is now working.

Build and attestation receipts are under
`evidence/original_world_hud/hover_repaint/host_build/b604cddf0d2d34d1c183/`.
Five new Host objects, its environment script and six generated Lua
harness scripts were retired: 58,027,992 logical bytes and
58,048,664 allocated file-data bytes. The six harnesses
are retained only as hash-verified, roundtrip-checked gzip files; old report
references to uncompressed generated harnesses or objects are historical.
Current executable, map, compiler dependencies, changed-file backups,
component executables, prior runtime and six native trial saves remain.

## Prepared hover pair

`20261024T091253Z_713037fbac49` contains 24 backend inputs and 35 runtime files.
Fifteen immutable inputs share cache identities, two databases have private
file identities, and six Python UI support files match their sources. Only
the new Host payload was added to the shared cache. The preparation guard
recorded zero native attempts and no denied operations. Fifty-six retained
runtime/save/default inputs preserve their bytes, identities and attributes;
only the expected new immutable aliases change link counts.

Play.ps1 explicitly sets ZEROSIS_UI_POLICY_INFO=1 from the preserved private
settings. Resume.ps1 rejects cross-bundle save loading. No default release,
installed game, mod or user save was promoted or migrated. Actual input,
turn advancement, restore, original UI equivalence and performance remain
unverified, and the user screen hold remains in force. Receipts are under
`evidence/original_world_hud/hover_repaint/pair_preparation/`.

## 2026-10-26 오프라인 종료 메뉴 구현

현재 작업 소스는 보존 중인 `20261024T091253Z_713037fbac49` 시험본보다 새 버전이다.
이 시험본과 기본 실행본은 교체하지 않았으며, 새 종료 메뉴가 들어 있는 실행 파일로 표시하지 않는다.

- 원본 GameMenu의 종료 버튼은 별도 원본 `ExitConfirm.lua/xml` 모달로 연결한다. 기존 원본 파일의 바이트와 XML 순서는 보존한다.
- 아니요·Esc는 같은 부모 게임 메뉴로 복귀한다. 자식 타이머는 0, 부모의 기존 타이머는 유지한다.
- 예는 원본 PopModal 뒤 소유 플레이어·턴에 묶인 종료 요청을 한 번 전달한다. 부모 닫기가 성공하면 추가 입력·Tick·저장·새 장면 게시 전에 루프를 반환한다. 창 자원 해제 뒤 기존 HostRun 정리 경로를 사용한다.
- 창 닫기(WM_CLOSE)의 기존 저장 후 종료와 메뉴 확인 후 저장 없는 종료는 서로 다른 경로로 유지한다.
- 입력 addendum 및 실제 scene driver·renderer·pixel 계약에도 새 문맥을 연결했다. 원본 옵션·주 메뉴·재시작·은퇴·지도 저장·터치 도움말 전체 구현은 완료하지 않았다.

오프라인 결과: 원본 Lua 메뉴/확인창 679개 확인, 실제 추출 C++ 최적화·비최적화 각 30사례/63확인, 자산 8개·드라이버 계약 11개·기존 기록 분석 20개 검사 통과. 현재 HostMain은 466개 입력의 `/Zs` 검사에서 경고 없이 통과했다.

이 결과는 전체 새 Host 링크·새 UI 임베딩·실제 화면·물리 입력·SDK 종료 수락이 아니다. C++ 구문 검사는 기존 생성 UI 헤더를 읽고, Lua와 SDK/플레이어/시간 경계는 명시적 시험값을 쓴다. 표시 상태의 renderer 검사는 텍스처 경계까지만 확인했으며, 실제 raster/시각 일치는 주장하지 않는다.

근거: `evidence/game_menu/offline_exit/source_manifest.json`, `host_syntax.json`, `lua_tests.json`, `cpp_tests_fixture_thunk_fix.json`, `driver_tests.json`, `owner_review.json`. 정리 경로·크기·해시는 같은 폴더의 정리 기록에 남긴다. 원본 설치·MODS·설정·저장 파일은 수정하지 않는다.

## 2026-10-26 종료 메뉴 내장 자산과 Host 링크

- 현재 Host: `20261026T133507Z_ea39cdb67229`, `ZeroSisHost_x64.exe` 6,613,504바이트, SHA-256 `12397e93712c033e05611179d27fce2c655ca5235c79e130cb9741ac8806b850`.
- 기존 자산 67개 중 66개는 동일하고, 현재 장면 하나를 갱신하고 원본 ExitConfirm Lua·레이아웃 두 개를 추가해 내장 자산 69개·레이아웃 27개를 검증했다. 텍스처·글꼴·오디오는 기존 입력을 재사용했다.
- 현재 동결 입력 601개는 기존 하드링크 585개와 독립 사본 16개다. 실제 현재 C++ 5개 번역 단위를 한 번씩 컴파일하고 한 번 링크했으며 경고가 없다. 실제 의존 목록은 466/266/270/279/301개, 합집합 550개다.
- 별도 파일 검사에서 x64 PE32+·실제 69개 payload·기존 import 24개·읽기 전용 복원 표식 하나·COFF와 현재 입력 해시를 대조했다. 세 변경/추가 내장 Lua payload는 기존 Lua 5.1 제공자에서 구문만 컴파일했으며, 전역 문장·SDK 호출·화면을 실행하지 않았다.
- 첫 기본 권한 시도는 파일 생성 전 하드링크에서 접근 거부로 끝났다. 같은 입력 하나의 생성·삭제 권한 시험 후 이전 실패와 소스 복구본을 보존한 별도 계획으로 빌드했다. 첫 실패 시도는 컴파일·링크 실행이 0회였다.
- 실제 검증 뒤 이번 오브젝트 5개와 환경 파일을 정리했다. 마지막 실행본·저장·기본 실행·SDK는 보호했고, 공유 입력의 의도한 링크 수 증가만 허용했다.

이 단계는 새 Host/SDK 실행 묶음이나 실제 게임 수락이 아니다. 기존 `713037` 준비본과 기본 실행은 교체하지 않았다. 다음은 현행 Host에 맞는 격리 묶음의 오프라인 준비이며, 실제 종료 확인창 표시·취소/예·창 닫기 순서·SDK 정리·저장 보존은 직접 재개 지시 후 검증한다. 전체 원본 UI·캠페인·원본 저장/모드 호환·멀티코어 실효성은 여전히 미완료다.

근거: `evidence/game_menu/exit_host_build/ui_embedding_result.json`, `independent_attestation.json`, `embedded_lua_syntax.json`, `protection_after.json`, `cleanup_result.json` 및 현재 Host `build_result.json`.



## Offline menu suite (2026-11-01)

The current Host `20261101T074006Z_c2fd2fe9be38` and private prepared pair `20261101T080450Z_424fb64608b2` contain the bounded menu work. Five translation units, 636 current source inputs, 559 compiler dependencies, 74 UI payloads and 30 layouts passed offline checks. Settings, main-menu return, captured-setup restart, retirement results, guarded map saving and original touch help have source/component coverage; the full original FrontEnd, all 133 option APIs, full replay/demographics and actual native input/render/game/save acceptance remain incomplete. No Host/SDK/HWND/GPU trial was started. The default 732a6 release and the explicit screen hold remain unchanged. See `docs/OFFLINE_MENU_SUITE.md` for the seven-item scope and exact preparation receipts.
