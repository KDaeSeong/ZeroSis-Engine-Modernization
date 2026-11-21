"""Materialize a private continuous game and verify its posted HWND input path.

The smoke driver runs the same persistent loop as --play. It proves one bounded
select/move/explicit skip/normal turn/save/close sequence, not human acceptance,
retail renderer equivalence, selected mods, or a complete playable Civ V port.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid

from collect_baseline import PROJECT, digest
from probe_world_builder import artifact
from run_new_game_probe import verify_city_site_base, verify_found_value_base
from runtime_input_cache import materialize_immutable
from verify_world_builder_map_object import check_artifacts


def materialize_checkpoint(run_id: str, build: dict, runtime: Path, evidence: Path) -> dict:
    if not re.fullmatch(r'[0-9]{8}T[0-9]{6}Z_[0-9a-f]{12}', run_id):
        raise ValueError('Resume run must be an immutable interactive run identity')
    source_result = PROJECT / 'evidence/interactive_game' / run_id / 'result.json'
    result = json.loads(source_result.read_text(encoding='utf8'))
    accepted = {'CONTINUOUS_INTERACTIVE_SDK_WINDOW_SMOKE_PASS', 'CONTINUOUS_INTERACTIVE_SDK_WINDOW_RESTORE_SMOKE_PASS',
                'CONTINUOUS_INTERACTIVE_SDK_DECISION_UI_SMOKE_PASS', 'CONTINUOUS_INTERACTIVE_SDK_DECISION_UI_RESTORE_SMOKE_PASS',
                'CONTINUOUS_INTERACTIVE_SDK_TREE_DECISION_UI_SMOKE_PASS', 'CONTINUOUS_INTERACTIVE_SDK_TREE_DECISION_UI_RESTORE_SMOKE_PASS'}
    if result.get('status') not in accepted or result.get('returncode') != 0 or not result.get('runtime_inputs_unchanged'):
        raise RuntimeError('Resume requires a successfully completed private interactive run')
    check_artifacts(result)
    request = json.loads(Path(result['request']['path']).read_text(encoding='utf8'))
    check_artifacts(request)
    source_runtime = (PROJECT / 'Build/InteractiveGameRuntime' / run_id).resolve(strict=True)
    if Path(request['cwd']).resolve(strict=True) != source_runtime or request.get('run_id') != run_id:
        raise RuntimeError('Checkpoint source runtime identity differs')
    for row in request['runtime_inputs']:
        path = Path(row['path']).resolve(strict=True)
        if path.parent != source_runtime or digest(path) != row['sha256']:
            raise RuntimeError('Checkpoint source runtime input escaped or changed from its immutable inventory')
    expected_manifest = 'ZEROSIS_HOST_BUNDLE_V4\n' + ''.join(Path(row['path']).name + '|' + row['sha256'] + '\n'
        for row in request['runtime_inputs'] if Path(row['path']).name != 'bundle.manifest')
    if (source_runtime / 'bundle.manifest').read_text(encoding='ascii') != expected_manifest:
        raise RuntimeError('Checkpoint source manifest differs from its actual runtime input inventory')
    host_rows = [row for row in request['runtime_inputs'] if Path(row['path']).name == 'ZeroSisHost_x64.exe']
    if len(host_rows) != 1 or host_rows[0]['sha256'] != build['executable']['sha256']:
        raise RuntimeError('Resume requires the exact sealed Host that wrote the native save; no bundle migration is applied')
    if digest(source_runtime / 'bundle.manifest') != digest(runtime / 'bundle.manifest'):
        raise RuntimeError('Resume requires the exact engine bundle, rules and providers that wrote the native save')
    output = Path(result['stdout']['path']).read_text(encoding='utf8').replace('\r\n', '\n').replace('\r', '\n')
    saves = re.findall(r'^INTERACTIVE_NATIVE_SAVE=(\d+)\|(.+)$', output, re.M)
    if len(saves) < 2 or len(result.get('next_human_turn', [])) != 1:
        raise RuntimeError('Checkpoint source did not complete its save and normal close sequence')
    turn = int(saves[-1][0])
    if turn != int(result['next_human_turn'][0][0]):
        raise RuntimeError('Checkpoint source turn differs from its final human turn')
    checkpoint = Path(saves[-1][1]).resolve(strict=True)
    state = checkpoint.parent / 'play-final-state.txt'
    inventory = {str(Path(row['path']).resolve(strict=True)): row for row in result['generated_files']}
    for path in (checkpoint, state):
        if not path.is_relative_to((source_runtime / 'sessions').resolve(strict=True)) or str(path) not in inventory or \
                digest(path) != inventory[str(path)]['sha256']:
            raise RuntimeError('Resume source escaped or differs from its final private-session inventory')
    local_checkpoint, expected_state, prior_result = runtime / 'checkpoint-input.zssave', evidence / 'checkpoint-state.txt', evidence / 'resume-source-result.json'
    for source, target in ((checkpoint, local_checkpoint), (state, expected_state), (source_result, prior_result)):
        shutil.copy2(source, target)
        if digest(source) != digest(target):
            raise RuntimeError('Resume provenance changed during checkpoint materialization')
    return {'run_id': run_id, 'run_result': artifact(prior_result), 'checkpoint_source': artifact(checkpoint),
            'checkpoint_input': artifact(local_checkpoint), 'expected_state': artifact(expected_state),
            'checkpoint_source_state': artifact(state), 'turn': turn}


def source_annotation(path: Path) -> dict:
    """Record mutable source provenance without making future resume depend on it."""
    path = Path(path).resolve(strict=True)
    return {'original_path': str(path), 'sha256': digest(path), 'bytes': path.stat().st_size}


def native_save_paths_valid(rows: list[tuple[str, str]], sessions: Path) -> bool:
    try:
        root = Path(sessions).resolve(strict=True)
        paths = [Path(path).resolve(strict=True) for _, path in rows]
        return bool(paths) and all(path.is_file() and path.is_relative_to(root) for path in paths)
    except (OSError, RuntimeError, ValueError):
        return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--host-build', type=Path, required=True)
    parser.add_argument('--language', choices=('en_US', 'ko_KR'), default='ko_KR')
    parser.add_argument('--smoke', action='store_true')
    parser.add_argument('--decisions', action='store_true', help='Run the bounded city-production-research decision smoke; requires --smoke')
    parser.add_argument('--research-tree', action='store_true', help='Use the original TechPopup handoff and TechTree in the same world window; requires --smoke --decisions')
    parser.add_argument('--resume-run', help='Resume the final native save of an accepted interactive run from this exact sealed Host')
    parser.add_argument('--timeout', type=int, default=120)
    args = parser.parse_args()
    if args.decisions and not args.smoke:
        parser.error('--decisions is only valid together with --smoke')
    if args.research_tree and not (args.smoke and args.decisions):
        parser.error('--research-tree requires --smoke --decisions')
    if not 30 <= args.timeout <= 300:
        parser.error('Timeout must be 30 to 300 seconds')
    inputs = {
        'host_build': args.host_build.resolve(strict=True),
        'shared_lua_build': PROJECT / 'evidence/shared_lua_runtime/build_result.json',
        'explore_sdk_build': PROJECT / 'evidence/explore_sdk/build_result.json',
        'city_site_sdk_build': PROJECT / 'evidence/city_site_sdk/build_result.json',
        'found_value_shared_sdk_build': PROJECT / 'evidence/found_value_shared_sdk/build_result.json',
        'bundle': PROJECT / 'evidence/host/bundle.json',
    }
    documents = {name: json.loads(path.read_text(encoding='utf8')) for name, path in inputs.items()}
    for name, document in documents.items():
        if name == 'bundle':
            # The reusable bundle's inputs are its immutable payload and
            # manifest. Its historical preparation script is not frozen and
            # is not executed by this runner (the established city runner
            # uses the same payload/manifest verification boundary).
            check_artifacts(document['files'])
            check_artifacts(document['manifest'])
        else:
            check_artifacts(document)
    build, lua, found, bundle = (documents[name] for name in ('host_build', 'shared_lua_build', 'found_value_shared_sdk_build', 'bundle'))
    if build.get('status') != 'UI_WINDOW_HOST_CANDIDATE_BUILT' or not build.get('source_inputs_unchanged'):
        raise RuntimeError('Continuous game requires a sealed window host')
    sources = {Path(row['path']).name: row for row in build['sources']}
    required = {'HostMain.cpp', 'HostRun.h', 'InteractiveGameSession.h', 'InteractiveGameLoop.h',
                'WorldViewState.h', 'WorldViewRenderer.cpp', 'WorldViewRenderer.h', 'BitmapWindow.cpp',
                'LocalSdkSession.h', 'LocalTurnController.h', 'LocalTurnSignals.h'}
    if not required <= sources.keys() or '--play-smoke' not in Path(sources['HostMain.cpp']['path']).read_text(encoding='utf8'):
        raise RuntimeError('Host does not contain the continuous gameplay implementation')
    if not any('INTERACTIVE_UI_SCENE_REQUEST' in Path(row['path']).read_text(encoding='utf8')
               for row in build['sources'] if Path(row['path']).suffix.lower() in ('.h', '.cpp')):
        raise RuntimeError('Sealed Host source does not contain the retained UI scene handshake')
    if args.decisions and not any('ZEROSIS_PLAY_DECISIONS_SMOKE' in Path(row['path']).read_text(encoding='utf8')
                                  for row in build['sources'] if Path(row['path']).suffix.lower() in ('.h', '.cpp')):
        raise RuntimeError('Sealed Host source does not contain the requested decision-smoke selector')
    if args.resume_run and '--play-load-smoke' not in Path(sources['HostMain.cpp']['path']).read_text(encoding='utf8'):
        raise RuntimeError('Host does not contain the native save-to-play resume implementation')
    if args.research_tree and 'ZEROSIS_PLAY_RESEARCH_TREE_SMOKE' not in Path(sources['InteractiveGameLoop.h']['path']).read_text(encoding='utf8'):
        raise RuntimeError('Sealed Host does not contain the original research-tree world-window input sequence')
    if lua.get('status') != 'SHARED_LUA_RUNTIME_CANDIDATE_BUILT':
        raise RuntimeError('Continuous game requires the accepted shared Lua provider')
    city = documents['city_site_sdk_build']
    verify_city_site_base(city, documents['explore_sdk_build'])
    verify_found_value_base(found, city, 'SHARED_FACTS')
    core = found['gamecore']
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ_') + uuid.uuid4().hex[:12]
    runtime = PROJECT / 'Build/InteractiveGameRuntime' / run_id
    evidence = PROJECT / 'evidence/interactive_game' / run_id
    runtime.mkdir(parents=True, exist_ok=False)
    evidence.mkdir(parents=True, exist_ok=False)
    rows, materializations = [], []
    for row in bundle['files']:
        name = Path(row['path']).name
        source = Path(build['executable']['path']) if name == 'ZeroSisHost_x64.exe' else Path(core['path']) if name == 'CvGameCoreDLL_Expansion2_x64.dll' else Path(row['path'])
        target = runtime / name
        if source.suffix.lower() in ('.dll', '.exe', '.bin', '.dat'):
            materializations.append(materialize_immutable(source, target, PROJECT / 'Build/RuntimeInputCache'))
        else:
            shutil.copy2(source, target)
            materializations.append({'target': str(target), 'materialization_method': 'private-copy'})
        if digest(source) != digest(target):
            raise RuntimeError('Private continuous runtime differs from its accepted input')
        rows.append({'source': str(source), **artifact(target)})
    lua_source = Path(lua['lua_dll']['path'])
    lua_target = runtime / lua_source.name
    materializations.append(materialize_immutable(lua_source, lua_target, PROJECT / 'Build/RuntimeInputCache'))
    rows.append({'source': str(lua_source), **artifact(lua_target)})
    manifest = runtime / 'bundle.manifest'
    manifest.write_text('ZEROSIS_HOST_BUNDLE_V4\n' + ''.join(Path(row['path']).name + '|' + row['sha256'] + '\n' for row in rows), encoding='ascii')
    rows.append(artifact(manifest))
    support_source = PROJECT / 'tools'
    support_tools = runtime / 'interactive_ui_support' / 'tools'
    support_tools.mkdir(parents=True, exist_ok=False)
    support_sources = {name: support_source / name for name in
                       ('interactive_ui_driver.py', 'render_ui_popup.py', 'ui_pixel_scene.py',
                        'ui_bitmap_fonts.py', 'civ5_ui_assets.py')}
    support_rows = {}
    for name, source in support_sources.items():
        target = support_tools / name
        shutil.copy2(source, target)
        if digest(source) != digest(target):
            raise RuntimeError('Frozen interactive UI support changed during materialization: ' + name)
        support_rows[name] = {'source': source_annotation(source), 'frozen': artifact(target)}
    icons_source = PROJECT / 'evidence/ui_popup/assets/inline_icons.json'
    icon_prep_source = PROJECT / 'evidence/ui_popup/assets/prepared.json'
    icon_dir = runtime / 'interactive_ui_support' / 'assets'
    icon_dir.mkdir(parents=True, exist_ok=False)
    icons_target, prep_target = icon_dir / 'inline_icons.json', icon_dir / 'prepared.json'
    shutil.copy2(icons_source, icons_target)
    shutil.copy2(icon_prep_source, prep_target)
    if digest(icons_source) != digest(icons_target) or digest(icon_prep_source) != digest(prep_target):
        raise RuntimeError('Frozen inline icon catalog/provenance changed during materialization')
    icon_prep_doc = json.loads(prep_target.read_text(encoding='utf8'))
    icon_catalog_row = icon_prep_doc.get('inline_icon_catalog', {})
    if Path(icon_catalog_row.get('path', '')).resolve() != icons_source.resolve() or \
            icon_catalog_row.get('sha256') != digest(icons_source):
        raise RuntimeError('Frozen icon catalog does not match its prepared-source provenance')
    support_manifest_path = runtime / 'interactive_ui_support' / 'support_manifest.json'
    support_manifest = {'tools': {name: row['frozen'] for name, row in support_rows.items()},
                        'inline_icons': artifact(icons_target),
                        'asset_preparation_provenance': artifact(prep_target)}
    support_manifest_path.write_text(json.dumps(support_manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    support_manifest_artifact = artifact(support_manifest_path)
    support_record_path = evidence / 'interactive_ui_support.json'
    support_record = {'tools': support_rows, 'inline_icons': {'source': source_annotation(icons_source), 'frozen': artifact(icons_target)},
                      'asset_preparation_provenance': {'source': source_annotation(icon_prep_source), 'frozen': artifact(prep_target)},
                      'frozen_support_manifest': support_manifest_artifact,
                      'sdk_session_profile': {'ZEROSIS_UI_SMALL_ASSETS': '1',
                          'policy': 'interactive_ui_driver.drive overwrites inherited environment for every Host session'},
                      'python': artifact(Path(sys.executable)), 'manual_launcher_protocol': 'INTERACTIVE_UI_SCENE_REQUEST/UI_READY v1'}
    support_record_path.write_text(json.dumps(support_record, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    references = {}
    for name, source in {**inputs, 'runner': Path(__file__).resolve(), 'runtime_cache_helper': PROJECT / 'tools/runtime_input_cache.py'}.items():
        target = evidence / (name + source.suffix)
        shutil.copy2(source, target)
        if digest(source) != digest(target):
            raise RuntimeError('Continuous runtime provenance changed during materialization')
        references[name] = artifact(target)
    frozen_runner_path = evidence / 'frozen_inputs' / 'run_interactive_game.py'
    frozen_runner_path.parent.mkdir(parents=True, exist_ok=False)
    shutil.copy2(Path(__file__).resolve(), frozen_runner_path)
    if digest(Path(__file__).resolve()) != digest(frozen_runner_path):
        raise RuntimeError('Frozen interactive runner changed during preservation')
    frozen_runner = artifact(frozen_runner_path)
    resume = materialize_checkpoint(args.resume_run, build, runtime, evidence) if args.resume_run else None
    launcher = runtime / 'Play.ps1'
    python_ps = "'" + sys.executable.replace("'", "''") + "'"
    driver_ps = "'" + str(support_tools / 'interactive_ui_driver.py').replace("'", "''") + "'"
    tools_ps = "'" + str(support_tools).replace("'", "''") + "'"
    icons_ps = "'" + str(icons_target).replace("'", "''") + "'"
    support_manifest_ps = "'" + str(support_manifest_path).replace("'", "''") + "'"
    common_driver_args = " --host (Join-Path $PSScriptRoot 'ZeroSisHost_x64.exe') --cwd $PSScriptRoot --runtime $PSScriptRoot --tools " + tools_ps + " --icons " + icons_ps + " --support-manifest " + support_manifest_ps + " --support-manifest-sha256 " + support_manifest_artifact['sha256'] + " --report $UiReport --language " + args.language + " --scene-timeout 60"
    launcher.write_text("$ErrorActionPreference = 'Stop'\n$UiReport = Join-Path $PSScriptRoot ('interactive-ui-' + [guid]::NewGuid().ToString('N') + '.json')\n& " + python_ps + ' ' + driver_ps + common_driver_args + " --mode play --timeout 0\nexit $LASTEXITCODE\n", encoding='utf8')
    resume_launcher = runtime / 'Resume.ps1'
    default_checkpoint = "(Join-Path $PSScriptRoot 'checkpoint-input.zssave')" if resume else "''"
    resume_launcher.write_text("param([string]$Checkpoint = " + default_checkpoint + ")\n$ErrorActionPreference = 'Stop'\n"
        "$UiReport = Join-Path $PSScriptRoot ('interactive-ui-' + [guid]::NewGuid().ToString('N') + '.json')\n"
        "if (-not $Checkpoint) {\n  Add-Type -AssemblyName System.Windows.Forms\n  $picker = New-Object System.Windows.Forms.OpenFileDialog\n"
        "  $picker.Title = \"ZeroSis' Civilization - 저장한 게임 열기\"\n  $picker.Filter = 'ZeroSis saves (*.zssave)|*.zssave'\n"
        "  $picker.InitialDirectory = (Join-Path $PSScriptRoot 'sessions')\n  try {\n"
        "    if ($picker.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) { return }\n    $Checkpoint = $picker.FileName\n"
        "  } finally { $picker.Dispose() }\n}\n& " + python_ps + ' ' + driver_ps + common_driver_args +
        " --mode play-load --checkpoint $Checkpoint --timeout 0\nexit $LASTEXITCODE\n", encoding='utf-8-sig')
    mode = '--play-load-smoke' if resume and args.smoke else '--play-load' if resume else '--play-smoke' if args.smoke else '--play'
    command = [sys.executable, '-B', '-X', 'utf8', str(support_tools / 'interactive_ui_driver.py'),
               '--host', str(runtime / 'ZeroSisHost_x64.exe'), '--cwd', str(runtime), '--runtime', str(runtime),
               '--tools', str(support_tools), '--icons', str(icons_target), '--support-manifest', str(support_manifest_path),
               '--support-manifest-sha256', support_manifest_artifact['sha256'],
               '--report', str(evidence / 'driver_result.json'),
               '--language', args.language, '--mode', mode.removeprefix('--'), '--timeout', str(args.timeout), '--scene-timeout', '60']
    if resume:
        command.extend(['--checkpoint', resume['checkpoint_input']['path']])
        launcher = resume_launcher
    request = {'run_id': run_id, 'command': command, 'cwd': str(runtime), 'language': args.language,
               'smoke': args.smoke, 'decisions': args.decisions, 'research_tree': args.research_tree,
               'timeout': args.timeout, 'runtime_inputs': rows, 'materializations': materializations,
               'provenance': {**references, 'frozen_runner': frozen_runner},
               'launcher': artifact(launcher), 'stage_or_mods_changed': False,
               'resume_launcher': artifact(resume_launcher), 'resume_from': resume,
               'interactive_ui_support': artifact(support_record_path),
               'interactive_ui_support_inventory': {'tools': support_rows,
                   'inline_icons': support_record['inline_icons'],
                   'asset_preparation_provenance': support_record['asset_preparation_provenance'],
                   'frozen_support_manifest': support_record['frozen_support_manifest']},
               'launcher_control_metadata': {'play': artifact(runtime / 'Play.ps1'), 'resume': artifact(resume_launcher),
                   'selected': artifact(launcher),
                   'python': artifact(Path(sys.executable)), 'driver': support_rows['interactive_ui_driver.py']['frozen']},
               'sdk_session_profile': support_record['sdk_session_profile'],
               'input_profile': 'POSTED_HWND_CONTINUOUS_TREE_DECISION_UI_LOOP' if args.research_tree else
                                'POSTED_HWND_CONTINUOUS_DECISION_UI_LOOP' if args.decisions else
                                'POSTED_HWND_CONTINUOUS_GAME_LOOP' if args.smoke else 'MANUAL_CONTINUOUS_GAME_LOOP'}
    request_path = evidence / 'request.json'
    request_path.write_text(json.dumps(request, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    if not args.smoke:
        print(json.dumps({'status': 'PRIVATE_CONTINUOUS_GAME_PREPARED', 'run_id': run_id, 'launcher': str(launcher), 'request': str(request_path)}, ensure_ascii=False))
        return 0
    environment = dict(os.environ)
    environment.pop('ZEROSIS_UI_WINDOW_PROFILE', None)
    environment.pop('ZEROSIS_PLAY_DECISIONS_SMOKE', None)
    environment.pop('ZEROSIS_PLAY_RESEARCH_TREE_SMOKE', None)
    if args.decisions:
        environment['ZEROSIS_PLAY_DECISIONS_SMOKE'] = '1'
    if args.research_tree:
        environment['ZEROSIS_PLAY_RESEARCH_TREE_SMOKE'] = '1'
    print('RUN_CONTINUOUS_GAME_SMOKE ' + run_id, flush=True)
    process = subprocess.Popen(command, cwd=runtime, env=environment, stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW)
    attempt_path = evidence / 'attempt.json'
    attempt_path.write_text(json.dumps({'status': 'RUNNING', 'pid': process.pid, 'command': command}, indent=2) + '\n', encoding='utf8')
    timed_out = False
    try:
        stdout, stderr = process.communicate(timeout=args.timeout + 15)
    except subprocess.TimeoutExpired:
        timed_out = True
        process.kill()
        stdout, stderr = process.communicate(timeout=10)
    attempt_path.write_text(json.dumps({'status': 'FINISHED', 'pid': process.pid,
        'host_pid': json.loads((evidence / 'driver_result.json').read_text(encoding='utf8')).get('pid')
                    if (evidence / 'driver_result.json').is_file() else None,
        'returncode': process.returncode, 'timed_out': timed_out}, indent=2) + '\n', encoding='utf8')
    (evidence / 'stdout.log').write_bytes(stdout)
    (evidence / 'stderr.log').write_bytes(stderr)
    text = (stdout + b'\n' + stderr).decode('utf8', errors='replace').replace('\r\n', '\n').replace('\r', '\n')
    support_unchanged = all(digest(Path(row['frozen']['path'])) == row['frozen']['sha256'] for row in support_rows.values()) and \
        digest(icons_target) == support_record['inline_icons']['frozen']['sha256'] and \
        digest(prep_target) == support_record['asset_preparation_provenance']['frozen']['sha256'] and \
        digest(support_manifest_path) == support_record['frozen_support_manifest']['sha256']
    launcher_control_unchanged = all(digest(Path(row['path'])) == row['sha256']
                                     for row in request['launcher_control_metadata'].values())
    unchanged = all(digest(Path(row['path'])) == row['sha256'] for row in rows) and support_unchanged and launcher_control_unchanged
    checkpoint_unchanged = resume is None or digest(Path(resume['checkpoint_input']['path'])) == resume['checkpoint_input']['sha256']
    initial_states = list((runtime / 'sessions').glob('*/play-initial-state.txt'))
    semantic_restore_equal = bool(resume and len(initial_states) == 1 and initial_states[0].read_bytes() == Path(resume['expected_state']['path']).read_bytes())
    starts = re.findall(r'^INTERACTIVE_GAME_STARTED=(\d+)\|(\d+)\|(\d+)\|(\d+)$', text, re.M)
    selected = re.findall(r'^INTERACTIVE_UNIT_SELECTED=(\d+)\|(\d+)\|(\d+)\|(\d+)$', text, re.M)
    moved = re.findall(r'^INTERACTIVE_SMOKE_MOVEMENT_VERIFIED=(\d+)\|(\d+)\|(\d+)$', text, re.M)
    next_turn = re.findall(r'^INTERACTIVE_NEXT_HUMAN_TURN=(\d+)\|(\d+)$', text, re.M)
    frames = [list(map(int, match.split('|'))) for match in re.findall(r'^INTERACTIVE_WORLD_FRAME=(.+)$', text, re.M)]
    posted = re.findall(r'^INTERACTIVE_SMOKE_POSTED=(.+)$', text, re.M)
    native_inputs = re.findall(r'^INTERACTIVE_WINDOW_INPUT=(.+)$', text, re.M)
    driver_result = json.loads((evidence / 'driver_result.json').read_text(encoding='utf8')) if (evidence / 'driver_result.json').is_file() else {}
    driver_ok = driver_result.get('status') == 'INTERACTIVE_UI_DRIVER_PASS'
    native_saves = re.findall(r'^INTERACTIVE_NATIVE_SAVE=(\d+)\|(.+)$', text, re.M)
    saves_with_paths_valid = native_save_paths_valid(native_saves, runtime / 'sessions')
    if args.decisions:
        scene_contexts = {row.get('context') for row in driver_result.get('scene_requests', []) if type(row) is dict}
        success = not timed_out and process.returncode == 0 and unchanged and driver_ok and len(starts) == 1 and \
            len(next_turn) == 1 and int(next_turn[0][0]) == int(starts[0][0]) + 1 and len(frames) >= 5 and \
            all(len(row) == 9 and row[5] > 0 and row[6] > 0 for row in frames) and \
            len({row[5] for row in frames}) == 1 and {'production', 'research'} <= scene_contexts and \
            posted and native_inputs and len(native_saves) >= 2 and saves_with_paths_valid and \
            int(native_saves[-1][0]) == int(next_turn[0][0]) and 'INTERACTIVE_DECISION_SMOKE_COMPLETE=1' in text and \
            'INTERACTIVE_PLAY_CLOSED=' in text and 'INTERACTIVE_GAME_SESSION_STOPPED=true' in text and \
            'INTERACTIVE_PLAY_SHUTDOWN_PASS GAMECORE_LOADED=true GAMECORE_UNLOADED=true' in text and \
            not re.search(r'HOST_FAILURE|HOST_NATIVE_EXCEPTION|HOST_CLEANUP_PENDING|INTERACTIVE_INPUT_REJECTED', text)
    else:
        success = not timed_out and process.returncode == 0 and unchanged and driver_ok and len(starts) == 1 and len(moved) == 1 and selected and len(next_turn) == 1 and len(frames) >= 5 and len(posted) >= 6 and len(native_inputs) >= 6 and \
        int(next_turn[0][0]) == int(starts[0][0]) + 1 and all(len(row) == 9 and row[5] > 0 and row[6] > 0 for row in frames) and \
        len({row[5] for row in frames}) == 1 and 'INTERACTIVE_SMOKE_SEQUENCE=SELECT_MOVE_EXPLICIT_SKIP_END_TURN_SAVE_WM_CLOSE' in text and \
        'INTERACTIVE_PLAY_CLOSED=' in text and 'INTERACTIVE_GAME_SESSION_STOPPED=true' in text and \
        'INTERACTIVE_PLAY_SHUTDOWN_PASS GAMECORE_LOADED=true GAMECORE_UNLOADED=true' in text and \
        not re.search(r'HOST_FAILURE|HOST_NATIVE_EXCEPTION|HOST_CLEANUP_PENDING|INTERACTIVE_INPUT_REJECTED', text)
    if resume:
        success = success and checkpoint_unchanged and semantic_restore_equal and int(starts[0][0]) == resume['turn'] and \
            'INTERACTIVE_RESTORE_IDLE_STATE_UNCHANGED=true' in text and len(re.findall(r'^INTERACTIVE_RESTORE_IDENTITY=', text, re.M)) == 1 and \
            len(re.findall(r'^INTERACTIVE_RESTORE_SECTIONS_EQUAL=', text, re.M)) == 1
    if args.research_tree:
        success = success and 'research-tree' in scene_contexts and \
            len(re.findall(r'^INTERACTIVE_DECISION_TREE_HANDOFF_TARGET=\d+$', text, re.M)) == 1 and \
            text.splitlines().count('INTERACTIVE_DECISION_TREE_SELECTION_REMAINS_OPEN=true') == 1
    failures = re.findall(r'^HOST_FAILURE: (.+)$', text, re.M)
    if driver_result.get('error'):
        failures.append('Interactive UI driver: ' + str(driver_result['error']))
    generated = [artifact(path) for path in sorted((runtime / 'sessions').rglob('*')) if path.is_file()]
    status_prefix = ('CONTINUOUS_INTERACTIVE_SDK_DECISION_UI_RESTORE_SMOKE_' if resume else
                     'CONTINUOUS_INTERACTIVE_SDK_DECISION_UI_SMOKE_') if args.decisions else \
                    ('CONTINUOUS_INTERACTIVE_SDK_WINDOW_RESTORE_SMOKE_' if resume else 'CONTINUOUS_INTERACTIVE_SDK_WINDOW_SMOKE_')
    if args.research_tree:
        status_prefix = 'CONTINUOUS_INTERACTIVE_SDK_TREE_DECISION_UI_RESTORE_SMOKE_' if resume else \
                        'CONTINUOUS_INTERACTIVE_SDK_TREE_DECISION_UI_SMOKE_'
    result = {'status': status_prefix + ('PASS' if success else 'FAILED'),
              'run_id': run_id, 'pid': driver_result.get('pid', process.pid), 'driver_pid': process.pid, 'returncode': process.returncode,
              'exit_code_hex': f'0x{process.returncode & 0xffffffff:08X}', 'timed_out': timed_out,
              'request': artifact(request_path), 'attempt': artifact(attempt_path),
              'stdout': artifact(evidence / 'stdout.log'), 'stderr': artifact(evidence / 'stderr.log'),
              'runtime_inputs_unchanged': unchanged, 'generated_files': generated,
              'resume_from_run': resume['run_id'] if resume else None, 'checkpoint_input_unchanged': checkpoint_unchanged,
              'semantic_restore_equal': semantic_restore_equal, 'fresh_process_restore_verified': bool(resume and success),
              'startup': starts, 'selections': selected, 'movement': moved, 'next_human_turn': next_turn,
              'frames': frames, 'posted_inputs': posted, 'native_inputs': native_inputs,
              'native_window_posted_input_verified': bool(success), 'human_input_verified': False,
              'decision_ui_smoke_requested': args.decisions, 'decision_ui_sequence_verified': bool(args.decisions and success),
              'research_tree_requested': args.research_tree, 'research_tree_sequence_verified': bool(args.research_tree and success),
              'interactive_ui_driver': artifact(evidence / 'driver_result.json') if (evidence / 'driver_result.json').is_file() else None,
              'interactive_ui_support_unchanged': support_unchanged,
              'launcher_control_metadata_unchanged': launcher_control_unchanged,
              'native_saves': native_saves, 'native_save_paths_valid': saves_with_paths_valid,
              'retail_renderer_equivalence_verified': False, 'full_gameplay_verified': False,
              'external_retail_save_compatibility_verified': False, 'stage_or_mods_changed': False,
              'failures': failures}
    result_path = evidence / 'result.json'
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps({'status': result['status'], 'run_id': run_id, 'result': str(result_path), 'failures': result['failures']}, ensure_ascii=False))
    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())
