"""Publish only a verified offline menu Host/pair and its small documentation.

python -B tools/publish_offline_menu_suite.py --request <new/request.json>
  --preparation-result <passed/result.json> --preparation-audit <passed/audit.json>

Use --check-only for read-only validation. This tool never starts a native
program or imports a builder. Registered profile/final audits remain immutable.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

sys.dont_write_bytecode = True
PROJECT = Path(__file__).absolute().parents[1]
STAGE = PROJECT / 'evidence/game_menu/offline_menu_suite'
PAIR_STAGE = STAGE / 'pair_preparation'
HOST_ID = '20261101T074006Z_c2fd2fe9be38'
HOST_SHA = '26b2a97071c91a37a6a70ef05acc1c2026cda2fc06f6ce28d4d3268a9558823a'
REPORT_SHA = '6077a003f247a82df3e5fe6cfa56671df2750ae0bb0fec9710f71df659439ba7'
SDK_SHA = '430f3122d0b555d6daae14aa7c011ef43ce8f978270477c8af596ca4b0493ab9'
DEFAULT_ID = '20261012T121847Z_732a6d5f07ea'
OLD_PREPARED_ID = '20261024T091253Z_713037fbac49'
INDEX = PROJECT / 'evidence/save_menu/20261013_original_screen/current_progress.json'
MENU_DOC = PROJECT / 'docs/OFFLINE_MENU_SUITE.md'
HUD_DOC = PROJECT / 'docs/ORIGINAL_WORLD_HUD.md'
PUBLICATION = STAGE / 'publication.json'
HOST_REPORT = PROJECT / 'evidence/ui_window_host' / HOST_ID / 'build_result.json'
HOST_AUDIT = PAIR_STAGE / HOST_ID / 'final_audit.json'
HOST_GATE = PAIR_STAGE / HOST_ID / 'registered_current_gate_audit.json'


def require(value, message):
    if not value:
        raise RuntimeError(message)


def key(path):
    return os.path.normcase(os.path.abspath(os.fspath(path)))


def within(path, root):
    return Path(key(path)).is_relative_to(Path(key(root)))


def ordinary(path):
    path = Path(os.path.abspath(path))
    for item in (path, *path.parents):
        if os.path.lexists(item):
            require(not item.lstat().st_file_attributes & 0x400, 'Reparse point in publication input/output: ' + str(item))
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode), 'Publication input is not an ordinary file: ' + str(path))
    return info


def artifact(path, expected=None):
    path = Path(os.path.abspath(path));before = ordinary(path)
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    after = ordinary(path)
    identity = lambda value: (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_file_attributes)
    require(identity(before) == identity(after), 'Input changed while hashing: ' + str(path))
    result = dict(path=str(path), bytes=after.st_size, sha256=digest.hexdigest())
    if expected:
        require(result['sha256'] == expected['sha256'] and result['bytes'] == expected.get('bytes', result['bytes']),
                'Pinned publication input differs: ' + str(path))
        if 'file_identity' in expected:
            require([after.st_dev, after.st_ino] == expected['file_identity'], 'Input file identity differs: ' + str(path))
        if 'mtime_ns' in expected:
            require(after.st_mtime_ns == expected['mtime_ns'], 'Input modification time differs: ' + str(path))
    return result


def load(path):
    ref = artifact(path)
    raw = Path(ref['path']).read_bytes()
    require(hashlib.sha256(raw).hexdigest() == ref['sha256'], 'JSON changed during read')
    value = json.loads(raw.decode('utf-8-sig'))
    require(type(value) is dict, 'Expected a JSON object: ' + str(path))
    return value, ref


def refs(value):
    if isinstance(value, dict):
        if type(value.get('path')) is str and re.fullmatch('[0-9a-f]{64}', value.get('sha256', '')):
            yield value
        for child in value.values():
            yield from refs(child)
    elif isinstance(value, list):
        for child in value:
            yield from refs(child)


def refers(value, ref):
    return any(key(row['path']) == key(ref['path']) and row['sha256'] == ref['sha256'] for row in refs(value))


def no_native_outputs(runtime, evidence):
    require(not (runtime / 'sessions').exists(), 'Prepared runtime already has native sessions')
    blocked = {'attempt.json', 'stdout.log', 'stderr.log', 'driver_result.json', 'smoke_result.json', 'play_result.json', 'native_result.json',
               'host_stdout.log', 'host_stderr.log', 'terminal_audit.json', 'prelaunch_input_audit.json'}
    for root in (runtime, evidence):
        for directory, names, files in os.walk(root, followlinks=False):
            for name in names:
                require(not (Path(directory) / name).lstat().st_file_attributes & 0x400, 'Reparse directory in new pair')
            for name in files:
                require(name.casefold() not in blocked and not name.casefold().endswith(('.zssave', '.civ5save')),
                        'Prepared pair contains a native/live-driver result or save: ' + str(Path(directory) / name))


def validate(request_path, preparation_path, audit_path):
    request, request_ref = load(request_path)
    prep, prep_ref = load(preparation_path);audit, audit_ref = load(audit_path)
    require(within(request_path, PROJECT / 'evidence/interactive_game') and Path(request_path).name == 'request.json',
            'Request is not an exact owned preparation request')
    require(within(preparation_path, PAIR_STAGE) and within(audit_path, PAIR_STAGE), 'Pair proof lies outside this menu preparation stage')
    run_id = request.get('run_id')
    require(type(run_id) is str and re.fullmatch(r'[0-9]{8}T[0-9]{6}Z_[0-9a-f]{12}', run_id) and
            run_id not in (OLD_PREPARED_ID, DEFAULT_ID) and Path(request_path).parent.name == run_id,
            'Request does not identify one new owned runtime')
    runtime = PROJECT / 'Build/InteractiveGameRuntime' / run_id
    require(key(request.get('cwd', '')) == key(runtime) and runtime.is_dir(), 'Request runtime directory differs')
    require(request.get('smoke') is False and all(value is False or value is None for name, value in request.items() if name.endswith('_smoke')) and
            request.get('resume_from') in (None, '') and not any('smoke' in str(arg).casefold() for arg in request.get('command', [])),
            'Publication requires a new-game-only, non-smoke preparation')
    require(prep.get('schema') == 'zerosis.latest_pair.prepared.v1' and
            prep.get('status') == 'PASS_CURRENT_HOST_AND_GREAT_WORK_SDK_PREPARED_NOT_EXECUTED' and
            prep.get('run_id') == audit.get('run_id') == run_id and prep.get('host_build_id') == HOST_ID and
            prep.get('runtime_input_count') == 24 and prep.get('actual_menu_source_closure_rechecked') is True and
            prep.get('native_attempts') == 0 and prep.get('host_or_sdk_executed') is False and
            prep.get('default_promoted') is False and prep.get('new_game_only') is True and not prep.get('guard_denials'),
            'Preparation result is not the passed final offline menu pair')
    require(str(audit.get('status', '')).startswith('PASS_') and
            refers(prep, request_ref) and refers(audit, request_ref) and refers(audit, prep_ref),
            'Preparation audit does not seal this exact passed request/result')
    closure = audit.get('current_source_closure', {})
    require(closure.get('source_count') == 636 and closure.get('native_execution') is False and
            audit.get('host_or_sdk_executed', False) is False and audit.get('native_execution', False) is False,
            'Final preparation audit lacks its offline current 636-input proof')
    adoption_refs = [];adoption = None
    if prep.get('adopted_unexecuted_preparation') is True:
        adoption = prep.get('adoption', {})
        require(adoption == audit.get('adoption') and adoption.get('original_creation_provenance_preserved') is True and
                adoption.get('request_and_payloads_rewritten') is False and adoption.get('materialization_replayed') is False and
                adoption.get('new_runtime_files_created') == 0 and adoption.get('original_failure_retained') is True,
                'Adopted preparation rewrote its creation history or replayed materialization')
        for name in ('creation_attempt', 'creation_failure', 'creator_adapter_recovery', 'current_metadata_rechecker', 'adoption_tool'):
            adoption_refs.append(artifact(adoption[name]['path'], adoption[name]))
        failure, _ = load(adoption['creation_failure']['path'])
        require(failure.get('status') == 'FAILED_PREPARATION_ONLY' and failure.get('native_attempts') == 0 and
                failure.get('failed_phase') == 'POST_MATERIALIZATION_VALIDATION', 'Adoption lost its original post-creation failure')
        recovered = gzip.decompress(Path(adoption['creator_adapter_recovery']['path']).read_bytes())
        require(hashlib.sha256(recovered).hexdigest() == adoption['creator_adapter']['sha256'] and
                len(recovered) == adoption['creator_adapter']['bytes'], 'Historical creator backup is not the actual original adapter')

    build, build_ref = load(HOST_REPORT);artifact(HOST_REPORT, dict(sha256=REPORT_SHA))
    final, final_ref = load(HOST_AUDIT);gate, gate_ref = load(HOST_GATE)
    require(build.get('build_id') == final.get('build_id') == HOST_ID and
            build.get('status') == 'UI_WINDOW_HOST_CANDIDATE_BUILT' and build.get('source_inputs_unchanged') is True and
            build.get('provider_inputs_unchanged') is True and len(build.get('current_source_inputs', [])) == 636 and
            len(build.get('compiler_inputs', [])) == 559 and build.get('catalog', {}).get('entry_count') == 74,
            'Final Host build identity or actual input counts differ')
    require(final.get('screen_verification_deferred') is True and final.get('current_native_or_screen_relaunch_allowed') is False and
            final.get('original_Host_SDK_game_window_or_GPU_execution') is False and final.get('full_engine_goal_complete') is False and
            gate.get('native_execution') is False and gate.get('current_source_scope', {}).get('source_count') == 636 and
            gate.get('current_source_scope', {}).get('actual_current_source_closure_verified') is True and
            gate.get('registered_profile', {}).get('report_sha256') == REPORT_SHA and
            gate.get('registered_profile', {}).get('audit_sha256') == final_ref['sha256'], 'Registered final Host proof or screen hold differs')
    require(refers(final, build_ref) and refers(final, build['executable']), 'Final Host audit does not seal its build/executable')
    build_executable = artifact(build['executable']['path'], dict(sha256=HOST_SHA, bytes=7130624))
    source_refs = [artifact(row['path'], row) for row in build['current_source_inputs']]
    require(len({key(row['path']) for row in source_refs}) == 636, 'Current source closure has duplicate aliases')
    ui_ref = artifact(build['ui_assets']['path'], build['ui_assets']);ui, _ = load(ui_ref['path'])
    require(len(ui.get('inputs', [])) == 74 and len(ui.get('xml_control_trees', {})) == 30, 'Sealed UI asset/layout counts differ')
    host_proof = request.get('host_runtime_validation', {})
    require(host_proof.get('registered_build_id') == HOST_ID and host_proof.get('current_source_count') == 636 and
            host_proof.get('compiler_dependency_count') == 559 and host_proof.get('execution_authorized') is False,
            'New request is not bound to the final current Host closure')
    runtime_refs = request.get('runtime_inputs')
    require(type(runtime_refs) is list and len(runtime_refs) == 24 and len({key(row['path']) for row in runtime_refs}) == 24,
            'Prepared runtime must expose exactly 24 distinct backend inputs')
    actual = {}
    for row in runtime_refs:
        require(Path(key(row['path'])).parent == Path(key(runtime)), 'Runtime backend input escaped its exact new directory')
        ref = artifact(row['path'], row);actual[Path(row['path']).name.casefold()] = ref
    host = actual['zerosishost_x64.exe'];sdk = actual['cvgamecoredll_expansion2_x64.dll']
    bundle = actual['bundle.manifest']
    require(host['sha256'] == HOST_SHA and host['bytes'] == 7130624 and sdk['sha256'] == SDK_SHA and
            refers(prep, host) and refers(prep, sdk), 'Prepared runtime Host/SDK exact pins differ')
    no_native_outputs(runtime, Path(request_path).parent)
    immutable = [build_ref, build_executable, final_ref, gate_ref, ui_ref, request_ref, prep_ref, audit_ref, *adoption_refs, *actual.values()]
    closure_sha = hashlib.sha256(json.dumps(source_refs, sort_keys=True, separators=(',', ':')).encode('utf8')).hexdigest()
    return dict(run_id=run_id, runtime=str(runtime), request=request_ref, preparation=prep_ref, preparation_audit=audit_ref,
                host=host, gamecore=sdk, bundle_manifest=bundle, build_executable=build_executable, build_result=build_ref, host_audit=final_ref,
                registered_current_gate=gate_ref, source_count=636, compiler_dependency_count=559, catalog_entries=74,
                original_ui_layouts=30, current_source_closure_sha256=closure_sha,
                preparation_method='ADOPTED_ALREADY_MATERIALIZED_UNEXECUTED_PAIR' if adoption else 'PASSED_FILE_ONLY_PREPARATION',
                adoption=adoption), immutable


def render_menu_doc(proof):
    adoption_note = ('\n이 준비본은 파일 생성 뒤 최종 감사의 경로 범위 검사에서 중단된 묶음을, 파일 복사나 요청 재작성 없이 별도 감사로 다시 확인해 채택한 것이다. 원래 생성 도구·실패 기록과 이후 채택 감사는 구분해 보존했다.\n'
                     if proof.get('adoption') else '')
    return f'''# 게임 내 메뉴 — 오프라인 구현·준비 기록

> 현재 상태(2026-11-01): Host `{HOST_ID}`와 SDK `430f3122`의 새 격리 묶음 `{proof['run_id']}`을 파일 검사로 준비했다. 게임·SDK·창·GPU 실행과 화면 확인은 보류하며, 기본 실행본은 유지한다.

5개 번역 단위의 컴파일·링크, 현재 소스 입력 636개와 컴파일 의존 파일 559개, UI payload 74개와 레이아웃 30개를 대조했다. 이는 소스·부품·파일 준비의 증거이며 실게임 수락을 뜻하지 않는다.

| 항목 | 이번에 연결한 범위 | 남은 범위 |
|---|---|---|
| 격리 실행 묶음 | 최신 Host와 선택 SDK의 정확한 파일·소스 조합, 별도 준비본 | 실제 실행·화면·입력 확인 |
| 옵션 | 창 크기·전체 화면·수직동기화·UI 효과음·기본 도움말의 적용, 값 확인, 취소·실패 복원, 별도 설정 저장 | 원본 OptionsManager 133개 API 전체, 그래픽 품질·음악 등 미지원 설정, 주 메뉴 옵션 화면 |
| 주 메뉴 복귀 | 원본 확인 콜백 종료 후 이전 게임·창·코어 정리, 별도 주 메뉴, 현재 설정으로 새 게임·종료 | 원본 주 메뉴 외형과 전체 설정·불러오기·다중 사용자 분기 |
| 현재 설정으로 재시작 | 현재 사전 설정 스트림과 별도 DLC·슬롯 패키지·이동 설정 캡처, 새 코어 재적용 | 실제 SDK 시작, 지형·문명·초기 난수 시드 일치 확인 |
| 은퇴 | 원본 은퇴 명령, SDK 재생 데이터 저장, 실제 최종 점수·역사적 순위·결과 화면 연결 | 전체 재생 화면·통계 화면·온라인 순위표, 실제 은퇴 실행 |
| 지도 저장 | 원본 SaveMapMenu, `.Civ5Map` 저장·목록·관측한 파일의 덮어쓰기·삭제, 잘못된 이름 거절 | 실제 SDK 출력과 게임 재읽기. 지도는 캠페인 저장을 대체하지 않음 |
| 터치 도움말 | 원본 Lua/XML 표시·닫기·체크박스와 별도 설정 저장 | 실제 터치 장치 입력·화면 확인 |

원본 설치·MODS·사용자 저장·기존 저장 스키마·밸런스·Mod ID는 변경하지 않았다. 표시 설정은 준비본의 `menu-options.zssettings`에, 지도·은퇴 출력은 격리 세션 안에 저장한다. 원본 INI와 기존 정책 표시 설정을 변경하지 않는다. 원본 옵션 소스 바이트를 보존하되 미구현 API가 성공했다고 처리하지 않으며, 터치 도움말의 원본 장치 조건도 유지한다.

## 검증 근거

- `evidence/ui_window_host/{HOST_ID}/build_result.json`: 최신 5개 번역 단위 컴파일·링크, 정확한 입력과 실행 파일.
- `evidence/game_menu/offline_menu_suite/pair_preparation/{HOST_ID}/final_audit.json`: 독립 파일 검사와 중간 산출물 정리. 이 감사는 발행 과정에서 수정하지 않는다.
- `evidence/game_menu/offline_menu_suite/options_touch/offline_suite_tests.json`: 공유 Lua와 부품 환경의 옵션·도움말·지도·기존 저장 흐름 검사.
- `evidence/game_menu/offline_menu_suite/options_touch/embedding_cross_tests.json`: 생성 장면·글꼴 메타데이터·원본 소스 결합 대조.
- `evidence/game_menu/offline_menu_suite/map_catalog/cpp_tests.json`: SDK 없는 본 지도 제공 코드의 실제 파일 보호 검사 67개. 하드링크 생성 검사는 권한 오류 5로 미실행.
- `evidence/game_menu/offline_menu_suite/map_catalog/long_path/final.json`: 세션 경로 180자·지도 이름 100자·전체 경로 294자의 저장·목록·덮어쓰기·삭제 확인.
- `evidence/game_menu/offline_menu_suite/frontend_lifecycle/`: 현재 설정 캡처·전환·은퇴 연결과 독립 소스 검토. 실제 게임 명령 실행 증거가 아님.

검사 과정에서 컴파일러·SDK 없는 작은 파일/설정 검사 프로그램·공유 Lua 제공자는 사용했다. Host·게임 SDK·CLR·HWND·GPU는 실행하지 않았다. 원본 픽셀 일치, 실제 플레이·캠페인 저장·모드 호환과 멀티코어 성능은 미검증이다.

## 완료 기록

- 준비 요청: `{Path(proof['request']['path']).relative_to(PROJECT).as_posix()}`
- 준비 결과: `{Path(proof['preparation']['path']).relative_to(PROJECT).as_posix()}`
- 준비 감사: `{Path(proof['preparation_audit']['path']).relative_to(PROJECT).as_posix()}`
- Host: 7,130,624바이트, SHA-256 `{HOST_SHA}`
- SDK SHA-256: `{SDK_SHA}`
- 새 세션·저장·실행 결과 없음, native acceptance 0, 기본 실행본 승격 없음, 전체 엔진 목표 미완료.
{adoption_note}
'''


def main(argv=None):
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--request', type=Path, required=True)
    cli.add_argument('--preparation-result', type=Path, required=True)
    cli.add_argument('--preparation-audit', type=Path, required=True)
    cli.add_argument('--check-only', action='store_true')
    args = cli.parse_args(argv)
    require(not sys.flags.optimize, 'Publication requires assertions/validation enabled')
    require(not PUBLICATION.exists(), 'Menu publication already exists; verify its receipt instead of replaying')
    proof, immutable = validate(args.request.absolute(), args.preparation_result.absolute(), args.preparation_audit.absolute())
    index, index_ref = load(INDEX);old_index = copy.deepcopy(index)
    default = copy.deepcopy(index['default_publication'])
    release_ref = artifact(default['release']['path'], default['release']);launcher_ref = artifact(default['launcher']['path'], default['launcher'])
    release, _ = load(release_ref['path'])
    require(release.get('runtime_id') == DEFAULT_ID and default.get('changed') is False and default.get('new_candidate_promoted') is False,
            'Default release is no longer the protected 732a6 baseline')
    require(index.get('current_prepared_runtime', {}).get('run_id') == OLD_PREPARED_ID,
            'Current prepared-runtime baseline changed; review before replacing its record')
    targets = (INDEX, MENU_DOC, HUD_DOC)
    require(all(ordinary(path).st_nlink == 1 for path in targets), 'Publication target has unexpected hardlinks')
    before = {str(path): artifact(path) for path in targets};raw_before = {str(path): path.read_bytes() for path in targets}
    index.update(utc=datetime.now(timezone.utc).isoformat(), status='PASS_CURRENT_MENU_SUITE_HOST_AND_SELECTED_SDK_PREPARED_NOT_EXECUTED_SCREEN_DEFERRED',
        current_goal_turn_classification='progress', screen_verification_deferred=True, current_native_or_screen_relaunch_allowed=False,
        native_acceptance_complete=False, native_acceptance_assertions=0, host_executed=False, gamecore_loaded=False,
        hwnd_created=False, gpu_executed=False, default_promoted=False, full_engine_goal_complete=False)
    require('prior_prepared_runtime_before_offline_menu_suite' not in index, 'Historical menu-pair publication already exists')
    index['prior_prepared_runtime_before_offline_menu_suite'] = copy.deepcopy(old_index['current_prepared_runtime'])
    index['current_host_build'] = dict(build_id=HOST_ID, status='LINKED_STATIC_VERIFIED_NOT_EXECUTED', executable=proof['build_executable'],
        build_result=proof['build_result'], final_audit=proof['host_audit'], registered_current_gate=proof['registered_current_gate'],
        current_source_inputs=636, compiler_dependency_count=559, catalog_entries=74, original_ui_layouts=30,
        host_executed=False, gamecore_loaded=False, screen_verification_deferred=True, full_engine_goal_complete=False)
    index['current_prepared_runtime'] = dict(status='CURRENT_MENU_SUITE_HOST_AND_SELECTED_SDK_PREPARED_NOT_EXECUTED_SCREEN_DEFERRED',
        run_id=proof['run_id'], host_build_id=HOST_ID, runtime_directory=proof['runtime'], host=proof['host'], gamecore=proof['gamecore'],
        bundle_manifest=proof['bundle_manifest'], proofs={name: proof[name] for name in ('request', 'preparation', 'preparation_audit')},
        runtime_input_count=24, current_source_closure_rechecked=636, new_game_only=True, native_attempts=0,
        preparation_method=proof['preparation_method'], adoption=proof['adoption'],
        host_or_sdk_executed=False, screen_verification_deferred=True, current_native_or_screen_relaunch_allowed=False,
        native_acceptance_assertions=0, default_promoted=False, full_engine_goal_complete=False)
    index['offline_menu_suite_stage'] = dict(proof, status='OFFLINE_SOURCE_BUILD_AND_PAIR_PREPARATION_ONLY',
        seven_requested_items_partially_implemented=True, native_acceptance_assertions=0, full_engine_goal_complete=False,
        unfinished=['OptionsManager 133 APIs and unsupported settings', 'Full original FrontEnd appearance and all branches',
                    'Full replay viewer/demographics and online leaderboard', 'Native UI/gameplay/save/mod/multicore acceptance'])
    require(index['default_publication'] == default and index['full_goal'] == old_index['full_goal'] and index['full_goal_redefined'] is False,
            'Publication changed default selection or redefined the goal')
    changed_keys = {'utc', 'status', 'current_goal_turn_classification', 'screen_verification_deferred', 'current_native_or_screen_relaunch_allowed',
                    'native_acceptance_complete', 'native_acceptance_assertions', 'host_executed', 'gamecore_loaded', 'hwnd_created', 'gpu_executed',
                    'default_promoted', 'full_engine_goal_complete', 'current_host_build', 'current_prepared_runtime'}
    require(all(index[name] == value for name, value in old_index.items() if name not in changed_keys), 'Unrelated historical progress record changed')
    notice = f'> 현재 상태(2026-11-01): 최신 Host `{HOST_ID}`와 선택 SDK `430f3122`의 새 격리 준비본 `{proof["run_id"]}`을 파일 검사로 확정했다. 화면 확인과 실제 실행은 보류하며, 기본 실행본 승격과 실게임 수락은 수행하지 않았다.'
    hud = raw_before[str(HUD_DOC)].decode('utf-8-sig')
    hud, count = re.subn(r'^> 현재 상태[^\r\n]*', notice, hud, count=1, flags=re.M)
    require(count == 1 and '## Offline menu suite (2026-11-01)' not in hud, 'HUD publication boundary changed')
    hud += f'\n\n## Offline menu suite (2026-11-01)\n\nThe current Host `{HOST_ID}` and private prepared pair `{proof["run_id"]}` contain the bounded menu work. Five translation units, 636 current source inputs, 559 compiler dependencies, 74 UI payloads and 30 layouts passed offline checks. Settings, main-menu return, captured-setup restart, retirement results, guarded map saving and original touch help have source/component coverage; the full original FrontEnd, all 133 option APIs, full replay/demographics and actual native input/render/game/save acceptance remain incomplete. No Host/SDK/HWND/GPU trial was started. The default 732a6 release and the explicit screen hold remain unchanged. See `docs/OFFLINE_MENU_SUITE.md` for the seven-item scope and exact preparation receipts.\n'
    outputs = {INDEX: (json.dumps(index, ensure_ascii=False, indent=2) + '\n').encode('utf8'),
               MENU_DOC: render_menu_doc(proof).encode('utf8'), HUD_DOC: hud.encode('utf8')}
    if args.check_only:
        print(json.dumps(dict(status='PASS_PUBLICATION_INPUTS_ONLY_NO_WRITES', run_id=proof['run_id'], source_inputs_rehashed=636,
                              runtime_inputs_rehashed=24, target_paths=[str(path) for path in targets], native_execution=False)))
        return

    backups = [];written = []
    for path in targets:
        require(artifact(path) == before[str(path)], 'Publication target changed before backup')
        if outputs[path] == raw_before[str(path)]:continue
        backup = STAGE / 'publication_backups' / (path.relative_to(PROJECT).as_posix().replace('/', '__') + '.' + before[str(path)]['sha256'][:12] + '.before.gz')
        backup.parent.mkdir(parents=True, exist_ok=True)
        if not backup.exists():
            with backup.open('xb') as stream:stream.write(gzip.compress(raw_before[str(path)], mtime=0))
        require(gzip.decompress(backup.read_bytes()) == raw_before[str(path)], 'Changed-file publication backup differs')
        backups.append(dict(original=before[str(path)], backup=artifact(backup)))

    def atomic(path, data):
        require(path in targets or path == PUBLICATION, 'Publication write escaped its exact output list')
        temporary = path.with_name(path.name + '.menu-publication-pending-' + str(os.getpid()))
        require(not os.path.lexists(temporary), 'Publication pending file already exists')
        try:
            with temporary.open('xb') as stream:stream.write(data);stream.flush();os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if temporary.exists():temporary.unlink()
    try:
        for row in immutable + [release_ref, launcher_ref]:artifact(row['path'], row)
        for path in targets:
            require(artifact(path) == before[str(path)], 'Publication target changed before commit')
            atomic(path, outputs[path]);written.append(path)
        for row in immutable + [release_ref, launcher_ref]:artifact(row['path'], row)
        after = [artifact(path) for path in targets]
        receipt = dict(schema='zerosis.menu_suite.publication.v1', status='PUBLISHED_MENU_SUITE_OFFLINE_BUILD_AND_PREPARED_PAIR_NOT_EXECUTED',
            utc=datetime.now(timezone.utc).isoformat(), publisher=artifact(__file__), prepared_pair=proof,
            before=list(before.values()), after=after, changed_file_only_backups=backups,
            default_release_unchanged=release_ref, default_launcher_unchanged=launcher_ref, prior_713037_record_preserved=True,
            registered_profile_and_final_audit_modified=False, source_inputs_rehashed=636, runtime_inputs_rehashed=24,
            native_acceptance_assertions=0, screen_verification_deferred=True, host_sdk_clr_hwnd_gpu_executed=False,
            full_engine_goal_complete=False)
        atomic(PUBLICATION, (json.dumps(receipt, ensure_ascii=False, indent=2) + '\n').encode('utf8'))
    except BaseException:
        for path in reversed(written):atomic(path, raw_before[str(path)])
        raise
    print(json.dumps(dict(status=receipt['status'], run_id=proof['run_id'], receipt=artifact(PUBLICATION), native_execution=False)))


if __name__ == '__main__':
    main()
