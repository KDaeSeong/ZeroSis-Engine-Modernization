"""Verify two live SDK popup sessions driven through owned hidden HWNDs.

The evidence covers the retained BNW UI VM, its snapshots, a bounded native
window input batch, and same-worker SDK continuation parity. It does not prove
retail UI scheduling, human input, complete-game equivalence, or performance.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import shutil
import struct
import uuid
from datetime import datetime, timezone
from pathlib import Path

from collect_baseline import PROJECT, digest
from probe_world_builder import artifact
from verify_extended_turns import inspect_extended
from verify_found_value_shared_sdk_candidate import parse_trace_block, parse_shared_layouts, semantic_signature
from verify_city_site_sdk_candidate import inspect_traces, signature as city_site_signature
from verify_first_turn_candidate import read_artifact
from verify_world_builder_map_object import check_artifacts
from ui_window_frame import verify_frame, verify_closed_frame


ROOT = PROJECT / 'evidence/live_ui_window'
BASELINE_CORE_SHA256 = 'a58a0d20cbaecad13ea248fe362d0c15bb97096802b9f60c5ef5f0dd8bb90c07'
BASELINE_PROOF = PROJECT / 'evidence/found_value_shared_sdk_runtime/20261002T155959Z_f8b7cb268407/conformance.json'
BASELINE_PROOF_SHA256 = '9a243f61d9a745632f310c8be694423c1d5f0611b298e594bb9785831c3ed297'
DLL_NAME = 'CvGameCoreDLL_Expansion2_x64.dll'
WINDOW_MODE = '--check-save-restore-ui-window-actions'
STANDARD_ENVIRONMENT_KEYS = {'ZEROSIS_EXPLORE_WORKERS', 'ZEROSIS_CITY_SITE_WORKERS'}
FOUND_ENVIRONMENT = {'ZEROSIS_FOUND_VALUE_WORKERS', 'ZEROSIS_FOUND_VALUE_TRACE'}


def local_python_closure(entry: Path):
    tools = PROJECT / 'tools'
    pending = [entry.resolve()]
    closure = {}
    edges = []
    while pending:
        path = pending.pop()
        if path in closure:
            continue
        if not path.is_file() or not path.is_relative_to(tools):
            raise RuntimeError('Python validator closure escaped the tools directory')
        tree = ast.parse(path.read_text(encoding='utf8'), filename=str(path))
        closure[path] = tree
        for node in ast.walk(tree):
            modules = []
            if isinstance(node, ast.Import):
                modules.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                modules.append(node.module)
            for module in modules:
                candidate = tools / (module.replace('.', '/') + '.py')
                if candidate.is_file():
                    edges.append((path, candidate.resolve()))
                    pending.append(candidate.resolve())
    return closure, edges


def _artifact_json(ref):
    if not isinstance(ref, dict):
        raise RuntimeError('Expected a path/hash/size artifact reference')
    check_artifacts(ref)
    return json.loads(Path(ref['path']).read_text(encoding='utf-8'))


def _by_name(rows, filename):
    matches = [row for row in rows if Path(row['path']).name == filename]
    if len(matches) != 1:
        raise RuntimeError(f'Expected exactly one runtime artifact named {filename}')
    check_artifacts(matches[0])
    return matches[0]


def _snapshot_from_result(result, sequence, phase):
    return _by_name(result.get('generated_files', []), f'ui-popup-{sequence}-{phase}.json')


def _input_rows(text):
    lines = re.findall(r'^UI_WINDOW_INPUT=(.+)$', text, re.M)
    rows = []
    for line in lines:
        fields = line.split('|')
        if len(fields) != 10 or any(not re.fullmatch(r'-?\d+', value) for value in fields):
            raise RuntimeError('Malformed native UI input observation')
        seq, kind, key, consumed, seed_before, seed_after, held_before, held_after, turn, tid = map(int, fields)
        if seq not in (1, 2) or kind not in (1, 2) or consumed not in (0, 1) or \
           held_before not in (0, 1) or held_after not in (0, 1) or seed_before != seed_after or tid <= 0:
            raise RuntimeError('Native UI input identity, timer, or RNG observation is invalid')
        rows.append({'sequence': seq, 'kind': kind, 'key': key, 'consumed': bool(consumed),
                     'seed_before': seed_before, 'seed_after': seed_after,
                     'held_before': held_before, 'held_after': held_after,
                     'turn': turn, 'thread_id': tid})
    return rows


def _verify_live_window(result, request, output, run_id, display_resize=False, refresh_closed=False):
    if result.get('ui_window_popups_enabled') is not True or request.get('ui_window_popups_enabled') is not True:
        raise RuntimeError('The run did not explicitly enable live UI-window presentation')
    if any(record.get('ui_window_display_enabled', False) is not display_resize for record in (request, result)):
        raise RuntimeError('The GPU display opt-in differs from the requested verification scope')
    if refresh_closed and not display_resize or any(record.get('ui_window_refresh_enabled', False) is not refresh_closed
                                                  for record in (request, result)):
        raise RuntimeError('Closed scene refresh differs from its explicit GPU profile')
    if result.get('status') != 'ISOLATED_NATIVE_SAVE_RESTORE_EXTENDED_PASS' or \
       result.get('exit_code') != 0 or result.get('timed_out') is not False or \
       result.get('cleanup_completed') is not True or result.get('module_unloaded') is not True or \
       result.get('host_failures') or result.get('script_failures') or \
       result.get('candidate_inputs_unchanged') is not True or result.get('accepted_bundle_unchanged') is not True or \
       result.get('restore_verified') is not True or result.get('resumed_turn_verified') is not True or \
       result.get('extended_turns_verified') is not True or result.get('configuration_verified') is not True:
        raise RuntimeError('Live UI SDK result did not complete cleanly and unload its core module')
    if result.get('extra_restored_turns') != 48 or result.get('extended_turns_verified') is not True:
        raise RuntimeError('Live UI run did not finish the required 50-turn continuation')
    if request.get('ui_popups_enabled') is not True or request.get('fixture_promotions_enabled') is not True or \
       request.get('fixture_unit_actions_enabled') is not True or request.get('extra_restored_turns') != 48:
        raise RuntimeError('Live UI run does not carry the exact popup/promotion/action profile')
    command = request.get('command')
    if not isinstance(command, list) or len(command) != 4 or command[1] != WINDOW_MODE or \
       command[2] not in ('en_US', 'ko_KR') or command[3] != '48':
        raise RuntimeError('The recorded child command is not the explicit live-window SDK mode')
    if request.get('run_id') != run_id:
        raise RuntimeError('Run path and immutable request identity differ')
    if result.get('ui_window_report') is None:
        raise RuntimeError('Live HWND report artifact is missing')
    window_report_ref = result['ui_window_report']
    check_artifacts(window_report_ref)
    window_report = _artifact_json(window_report_ref)
    if window_report.get('status') != 'LIVE_SDK_UI_WINDOW_POSTED_INPUT_PASS' or \
       window_report.get('pid') != result.get('process_id') or window_report.get('returncode') != 0 or \
       type(result.get('process_id')) is not int or result['process_id'] <= 0 or \
       window_report.get('timed_out') is not False or window_report.get('error') is not None or \
       window_report.get('real_user_click_verified') is not False or \
       window_report.get('installed_game_launched') is not False:
        raise RuntimeError('Owned HWND driver did not report a bounded successful test session')
    if window_report.get('display_resize_enabled', False) is not display_resize:
        raise RuntimeError('The HWND driver display profile differs from its immutable request')
    if window_report.get('refresh_closed_enabled', False) is not refresh_closed:
        raise RuntimeError('The HWND refresh profile differs from its immutable request')
    gpu_scope = ('actual_live_SDK_UI_VM_and_owned_GPU_HWND_closed_scene_refresh_with_posted_test_input' if refresh_closed else
                 'actual_live_SDK_UI_VM_and_owned_GPU_HWND_display_resize_with_posted_test_input')
    if display_resize and window_report.get('scope') != gpu_scope:
        raise RuntimeError('The GPU driver scope was not explicitly recorded')
    evidence_dir = Path(result['request']['path']).resolve().parent
    if evidence_dir.name != run_id or evidence_dir.parent.resolve() != (PROJECT / 'evidence/save_restore').resolve():
        raise RuntimeError('Runtime request/result artifacts are not in their unique save_restore evidence directory')
    if Path(window_report_ref['path']).resolve().parent != evidence_dir or \
       Path(result['stdout']['path']).resolve().parent != evidence_dir or \
       Path(result['stderr']['path']).resolve().parent != evidence_dir:
        raise RuntimeError('Runtime logs or native-window report escaped their unique evidence directory')

    build_ref = request.get('candidate_build')
    build = _artifact_json(build_ref)
    check_artifacts(build)
    if build.get('status') != 'UI_WINDOW_HOST_CANDIDATE_BUILT' or \
       build.get('gamecore_loaded') is not False or build.get('sdk_linked') is not False or \
       build.get('stage_updated') is not False or build.get('mods_updated') is not False or \
       build.get('host_runtime_executed') is not False:
        raise RuntimeError('The host build is not the frozen isolated UI-window candidate')
    executable = build.get('executable')
    imports = build.get('imports', {}).get('dependencies')
    if not isinstance(executable, dict) or not isinstance(imports, list) or not imports:
        raise RuntimeError('UI-window host executable/import report is incomplete')
    check_artifacts(executable)
    input_rows = {Path(row['path']).name: row for row in request.get('inputs', [])}
    host_input = input_rows.get('ZeroSisHost_x64.exe')
    core_input = input_rows.get(DLL_NAME)
    if host_input is None or core_input is None or executable.get('sha256') != host_input.get('sha256') or \
       core_input.get('sha256') != BASELINE_CORE_SHA256:
        raise RuntimeError('Actual host/GameCore input hashes differ from their frozen identities')
    check_artifacts(host_input)
    runtime_executable = Path(command[0]).resolve()
    runtime_root = Path(request.get('cwd', '')).resolve()
    if runtime_executable != Path(host_input['path']).resolve() or \
       runtime_executable.name != 'ZeroSisHost_x64.exe' or runtime_root.name != run_id or \
       not runtime_root.is_relative_to((PROJECT / 'Build/NewGameRuntime').resolve()) or \
       not runtime_executable.is_relative_to(runtime_root):
        raise RuntimeError('Child executable is not the verified host copy inside this private runtime')
    expected_tools = {'live_ui_window_driver.py', 'render_ui_popup.py', 'ui_pixel_scene.py',
                      'ui_bitmap_fonts.py', 'civ5_ui_assets.py'}
    if display_resize:
        expected_tools.add('ui_window_frame.py')
    tool_rows = request.get('ui_window_tools')
    if not isinstance(tool_rows, list) or {Path(row.get('original_source', '')).name for row in tool_rows} != expected_tools or \
       len(tool_rows) != len(expected_tools):
        raise RuntimeError('The owned runtime did not freeze the complete UI-window tool set')
    frozen_tools = {}
    for tool in tool_rows:
        name = Path(tool['original_source']).name
        if Path(tool['original_source']).resolve() != (PROJECT / 'tools' / name).resolve():
            raise RuntimeError('A UI-window helper claims an unexpected source location')
        check_artifacts(tool)
        if not Path(tool['path']).resolve().is_relative_to(runtime_root):
            raise RuntimeError('A frozen UI-window helper escaped the private runtime')
        frozen_tools[name] = tool
    driver_text = Path(frozen_tools['live_ui_window_driver.py']['path']).read_text(encoding='utf-8')
    if 'GetWindowThreadProcessId' not in driver_text or \
       'owner_pid.value == process.pid and actual_tid == tid' not in driver_text or \
       'int(delivered) >= 1' not in driver_text:
        raise RuntimeError('Frozen HWND driver does not enforce owned PID/TID and delivery checks')
    if 'ZeroSisLua51_x64.dll' not in {Path(name).name for name in imports}:
        raise RuntimeError('Live host import table omits the shared Lua runtime')
    # DXGI is reached through the D3D11 device's COM adapter/factory. It need
    # not create a direct PE import when no standalone DXGI factory is called.
    if display_resize and (not {'d3d11.dll', 'd2d1.dll'} <= {Path(name).name.casefold() for name in imports} or
            not {'d3d11.lib', 'dxgi.lib', 'd2d1.lib'} <= {name.casefold() for name in build.get('system_library_names', [])}):
        raise RuntimeError('The GPU host imports/libraries omit its D3D11/DXGI/Direct2D contract')

    env = request.get('environment_overrides')
    found_env = request.get('found_value_environment_overrides')
    workers = request.get('found_value_workers')
    if type(workers) is not int or workers not in (0, 4) or \
       request.get('found_value_workers_enabled') is not True or result.get('found_value_workers') != workers or \
       result.get('found_value_workers_enabled') is not True or request.get('found_value_trace_enabled') is not True or \
       result.get('found_value_trace_enabled') is not True or request.get('inherited_found_value_environment_removed') is not True or \
       request.get('found_value_default_environment_profile') != 'EXPLICIT_OVERRIDES' or \
       result.get('found_value_default_environment_profile') != 'EXPLICIT_OVERRIDES' or \
       request.get('found_value_input_layout') != 'SHARED_FACTS' or \
       result.get('found_value_input_layout') != 'SHARED_FACTS' or \
       found_env != {'ZEROSIS_FOUND_VALUE_WORKERS': str(workers), 'ZEROSIS_FOUND_VALUE_TRACE': '1'}:
        raise RuntimeError('Found-value worker/trace process environment is not explicitly bound')
    if not isinstance(env, dict) or set(env) != STANDARD_ENVIRONMENT_KEYS or \
       env.get('ZEROSIS_EXPLORE_WORKERS') not in ('0', '1', '2', '4') or \
       env.get('ZEROSIS_CITY_SITE_WORKERS') not in ('0', '1', '2', '4'):
        raise RuntimeError('Existing exploration/city-site worker environment contract changed')
    city_build = _artifact_json(request.get('city_site_sdk_build'))
    found_build = _artifact_json(request.get('found_value_sdk_build'))
    check_artifacts(city_build)
    check_artifacts(found_build)
    if city_build.get('status') != 'CITY_SITE_SDK_CANDIDATE_LINKED' or \
       found_build.get('status') != 'FOUND_VALUE_SHARED_SDK_CANDIDATE_LINKED' or \
       found_build.get('gamecore', {}).get('sha256') != BASELINE_CORE_SHA256 or \
       found_build.get('gamecore', {}).get('sha256') != core_input.get('sha256'):
        raise RuntimeError('Selected Found-value SDK build/core chain is not the reviewed candidate')

    stdout_ref = result.get('stdout')
    check_artifacts(stdout_ref)
    if Path(stdout_ref['path']).read_text(encoding='utf-8') != output:
        raise RuntimeError('SDK stdout changed while the UI report was being checked')
    stderr_ref = result.get('stderr')
    check_artifacts(stderr_ref)
    stderr_text = Path(stderr_ref['path']).read_text(encoding='utf-8')
    if stderr_text not in (f'UI_WINDOW_PROCESS_START={result["process_id"]}\n',
                           f'UI_WINDOW_PROCESS_START={result["process_id"]}\r\n'):
        raise RuntimeError('Live-window process start identity is not the sole permitted stderr record')
    state_lines = re.findall(r'^UI_WINDOW_STATE_UNCHANGED=(\d+)\|before-input$', output, re.M)
    if state_lines != ['1', '2']:
        raise RuntimeError('Both UI windows must preserve their shown SDK state before input')
    ordered_output = output.splitlines()
    for seq in (1, 2):
        marker = f'UI_WINDOW_STATE_UNCHANGED={seq}|before-input'
        ready_marker = next((i for i, line in enumerate(ordered_output)
                             if line.startswith(f'UI_WINDOW_READY={seq}|')), None)
        first_input = next((i for i, line in enumerate(ordered_output)
                            if line.startswith(f'UI_WINDOW_INPUT={seq}|')), None)
        complete_marker = next((i for i, line in enumerate(ordered_output)
                                if line.startswith(f'UI_WINDOW_COMPLETE={seq}|')), None)
        marker_index = ordered_output.index(marker)
        if ready_marker is None or first_input is None or complete_marker is None or \
           not marker_index < ready_marker < first_input < complete_marker:
            raise RuntimeError('Shown-state observation, HWND creation, input, and completion order differs')
    input_rows = _input_rows(output)
    expected = {
        # The repeated native key-down is filtered by BitmapWindow before it
        # enters the Lua/SDK callback log, so only Escape and late Return land.
        1: [(1, 27, True, 1, 0), (1, 13, False, 0, 0)],
        2: [(2, 12, True, 1, 0), (1, 27, False, 0, 0)],
    }
    if refresh_closed:
        for value in expected.values():
            value.append((1, 27, False, 0, 0))
    for seq in (1, 2):
        rows = [row for row in input_rows if row['sequence'] == seq]
        values = [(row['kind'], row['key'], row['consumed'], row['held_before'], row['held_after']) for row in rows]
        if values != expected[seq] or any(row['turn'] != seq * 25 for row in rows):
            raise RuntimeError(f'Window {seq} did not dispatch the exact accepted/rejected input sequence')
        if len({row['thread_id'] for row in rows}) != 1:
            raise RuntimeError(f'Window {seq} callback moved between owner threads')
    complete = re.findall(r'^UI_WINDOW_COMPLETE=(\d+)\|(\d+)\|(\d+)\|([^\r\n]+)$', output, re.M)
    if complete != [('1', '2', '1', 'owner-thread'), ('2', '2', '1', 'owner-thread')]:
        raise RuntimeError('Both HWND batches must deliver two messages and accept exactly one')
    ready = re.findall(r'^UI_WINDOW_READY=(\d+)\|(\d+)\|(\d+)\|(\d+)\|(\d+)$', output, re.M)
    windows = window_report.get('windows')
    if len(windows or []) != 2 or len(ready) != 2 or [int(row[0]) for row in ready] != [1, 2]:
        raise RuntimeError('Live HWND report/owner identities are incomplete')
    if [int(row['sequence']) for row in windows] != [1, 2]:
        raise RuntimeError('Live HWND records are reordered')
    pids, tids, handles = set(), set(), set()
    for window, identity in zip(windows, ready):
        seq, hwnd, tid, width, height = map(int, identity)
        if (window.get('sequence'), window.get('hwnd'), window.get('pid'), window.get('owner_thread'),
            window.get('client')) != (seq, hwnd, result['process_id'], tid, [width, height]):
            raise RuntimeError('Reported HWND does not match its native ready record')
        if window.get('completed') is not True or window.get('delivered') != 2 or window.get('accepted') != 1:
            raise RuntimeError('Native input delivery count differs from the committed batch')
        if window.get('input_policy') != ('Escape then late Return' if seq == 1 else 'CloseButton click then late Escape'):
            raise RuntimeError('Native window input policy differs from the frozen test')
        if any(row['thread_id'] != tid for row in input_rows if row['sequence'] == seq):
            raise RuntimeError('UI callback thread differs from the exact HWND owner thread')
        if [width, height] != ([900, 600] if display_resize else [1000, 700]):
            raise RuntimeError('The committed input batch uses an unexpected client geometry')
        pids.add(window['pid']); tids.add(tid); handles.add(hwnd)
    if len(pids) != 1 or len(tids) != 1 or len(handles) != 2:
        raise RuntimeError('The two windows did not run on one owned SDK process/thread')

    scenes = window_report.get('scenes')
    if len(scenes or []) != 2 or [item.get('sequence') for item in scenes] != [1, 2]:
        raise RuntimeError('Two scheduled popup scenes were not prepared in order')
    scene_rows = []
    for seq, scene in enumerate(scenes, 1):
        if scene.get('turn') != seq * 25 or scene.get('retained_runtime_bounds_check') is None:
            raise RuntimeError('Popup scene lacks its turn or independent runtime-bounds evidence')
        refs = {}
        for key in ('snapshot', 'manifest', 'prepare_log', 'png', 'packet'):
            if key not in scene:
                raise RuntimeError('Popup scene is missing its ' + key + ' artifact')
            refs[key] = scene[key]
            check_artifacts(refs[key])
            artifact_path = Path(refs[key]['path']).resolve()
            if key == 'prepare_log':
                if artifact_path.parent != evidence_dir or artifact_path.name != f'ui_window_prepare_{seq}.log':
                    raise RuntimeError('Popup preparation log escaped its unique evidence directory')
            elif not artifact_path.is_relative_to(runtime_root):
                raise RuntimeError('Popup scene artifact escaped its private runtime directory')
        snapshot_data = _artifact_json(scene['snapshot'])
        manifest = _artifact_json(scene['manifest'])
        if manifest.get('snapshot', {}).get('sha256') != scene['snapshot']['sha256'] or \
           manifest.get('snapshot_state_unchanged') is not True or manifest.get('packet', {}).get('sha256') != scene['packet']['sha256'] or \
           manifest.get('retained_runtime_bounds_check') != scene['retained_runtime_bounds_check'] or \
           manifest.get('hit_regions') != [[12, 745.0, 804.0, 895.0, 836.0]]:
            raise RuntimeError('Prepared UI scene is not bound to the retained snapshot and bounds check')
        portrait = scene.get('portrait_readback')
        if not isinstance(portrait, list) or len(portrait) != 2 or \
           {row.get('control_key') for row in portrait} != {16, 26}:
            raise RuntimeError('Live renderer did not read back both original portrait controls')
        selected_assets = manifest.get('selected_assets')
        if not isinstance(selected_assets, list):
            raise RuntimeError('Scene manifest omits original selected texture bindings')
        for row in portrait:
            if row.get('all_opaque_samples_match_original_atlas') is not True or \
               row.get('retail_pixels_verified') is not False or row.get('opaque_interior_samples', 0) < 128 or \
               row.get('distinct_source_rgba_values', 0) < 16:
                raise RuntimeError('Portrait readback is missing an informative source-atlas match')
            basename = Path(row['texture']).name.casefold()
            bindings = [asset for asset in selected_assets if asset.get('basename', '').casefold() == basename]
            if len(bindings) != 1:
                raise RuntimeError('Portrait pixels do not bind to one selected original atlas')
            if not isinstance(bindings[0].get('frozen_source'), dict):
                raise RuntimeError('Portrait atlas lacks a retained immutable original source')
            check_artifacts(bindings[0]['frozen_source'])
            check_artifacts(bindings[0]['output'])
            if not Path(bindings[0]['frozen_source']['path']).resolve().is_relative_to(runtime_root) or \
               not Path(bindings[0]['output']['path']).resolve().is_relative_to(runtime_root):
                raise RuntimeError('Original portrait atlas or its readback copy escaped the private runtime')
        check_bounds(scene['retained_runtime_bounds_check'])
        shown_ref = _snapshot_from_result(result, seq, 'shown')
        closed_ref = _snapshot_from_result(result, seq, 'closed')
        shown_data = json.loads(Path(shown_ref['path']).read_text(encoding='utf-8'))
        closed_data = json.loads(Path(closed_ref['path']).read_text(encoding='utf-8'))
        if snapshot_data != shown_data or shown_data.get('active') is not True or \
           shown_data.get('timerSemaphore') != 1 or closed_data.get('active') is not False or \
           closed_data.get('timerSemaphore') != 0 or shown_data.get('tree') != closed_data.get('tree') or \
           shown_data.get('draws') != closed_data.get('draws'):
            raise RuntimeError('Input changed the shown snapshot or failed to close the official popup cleanly')
        scene_rows.append({'sequence': seq, 'turn': seq * 25, 'snapshot': scene['snapshot'],
                           'shown_snapshot': shown_ref, 'closed_snapshot': closed_ref,
                           'manifest': scene['manifest'], 'png': scene['png'],
                           'portrait_readback': portrait,
                           'bounds_checked_controls': len(scene['retained_runtime_bounds_check']['checked']),
                           'shown_state_preserved_before_input': True})
    refresh_rows = _verify_closed_refresh(window_report, output, scene_rows, windows, runtime_root, evidence_dir) if refresh_closed else []
    if not refresh_closed and (window_report.get('refresh_scenes') or 'UI_WINDOW_REFRESH_' in output):
        raise RuntimeError('A closed scene refresh ran without its explicit profile')
    gpu_frames = _verify_gpu_frames(window_report, output, scene_rows, windows, runtime_root,
                                   refresh_rows=refresh_rows) if display_resize else []
    if not display_resize and (window_report.get('frames') or 'UI_WINDOW_FRAME=' in output):
        raise RuntimeError('GPU captures ran without the explicit display profile')
    return {'run_id': run_id, 'process_id': result['process_id'],
            'result': artifact(Path(result['request']['path']).parent / 'result.json'),
            'request': result['request'], 'stdout': result['stdout'], 'stderr': result['stderr'],
            'window_report': window_report_ref, 'window_report_status': window_report['status'],
            'windows': windows, 'input_events': input_rows, 'scenes': scene_rows,
            'display_resize_enabled': display_resize, 'refresh_closed_enabled': refresh_closed,
            'refresh_scenes': refresh_rows, 'gpu_frames': gpu_frames,
            'command': command, 'found_value_workers': workers,
            'frozen_ui_window_tools': frozen_tools,
            'host_build': build_ref, 'host_executable': executable,
            'import_dependencies': imports, 'core_sha256': core_input['sha256']}


def _verify_closed_refresh(window_report, output, scenes, windows, runtime_root, evidence_dir):
    rows = window_report.get('refresh_scenes')
    native_ready = re.findall(r'^UI_WINDOW_REFRESH_READY=(.+)$', output, re.M)
    devices = re.findall(r'^UI_WINDOW_REFRESH_DEVICE=(\d+)\|(\d+)\|(\d+)$', output, re.M)
    complete = re.findall(r'^UI_WINDOW_REFRESH_COMPLETE=(\d+)\|(\d+)\|(\d+)\|(\d+)\|([^\r\n]+)$', output, re.M)
    unchanged = re.findall(r'^UI_WINDOW_REFRESH_STATE_UNCHANGED=(\d+)\|after-refresh$', output, re.M)
    if not isinstance(rows, list) or [row.get('sequence') for row in rows] != [1, 2] or len(native_ready) != 2 or \
       [int(row[0]) for row in devices] != [1, 2] or unchanged != ['1', '2'] or \
       complete != [('1', '1', '0', '2', 'owner-thread'), ('2', '1', '0', '2', 'owner-thread')]:
        raise RuntimeError('Both official closed contexts require one bounded scene refresh and a rejected new-generation input')
    checked = []
    lines = output.splitlines()
    for row, text, device in zip(rows, native_ready, devices):
        fields = text.split('|', 7)
        if len(fields) != 8:
            raise RuntimeError('Refreshed scene identity has an invalid field count')
        seq, hwnd, tid, before, after, width, height = map(int, fields[:7])
        source_png = Path(fields[7]).resolve(strict=True)
        window = windows[seq - 1] if seq in (1, 2) else {}
        if row.get('sequence') != seq or row.get('turn') != seq * 25 or \
           (hwnd, tid) != (window.get('hwnd'), window.get('owner_thread')) or \
           (before, after, width, height) != (1, 2, 900, 600) or \
           window.get('scene_generation_before') != before or window.get('scene_generation_after') != after or \
           window.get('refresh_client') != [width, height] or window.get('refresh_completed') is not True or \
           window.get('refresh_delivered') != 1 or window.get('refresh_accepted') != 0 or \
           window.get('refresh_input_policy') != 'old CloseButton click then rejected Escape':
            raise RuntimeError('Scene refresh replaced its exact HWND/thread or consumed an inactive control')
        device_seq, old_device, new_device = map(int, device)
        if device_seq != seq or not 0 < old_device == new_device < (1 << 64) or \
           window.get('refresh_device_identity_before') != old_device or window.get('refresh_device_identity_after') != new_device:
            raise RuntimeError('Scene refresh did not retain the same live D3D11 device identity')
        scale = min(width / 1920, height / 1080)
        point = [round((width - 1920 * scale) / 2 + 820 * scale),
                 round((height - 1080 * scale) / 2 + 820 * scale)]
        if window.get('refresh_posted_click_client') != point:
            raise RuntimeError('Closed scene did not test the former CloseButton location')
        scene = scenes[seq - 1]
        folder = Path(scene['png']['path']).parent.with_name(f'presentation-popup-{seq}-closed')
        for key in ('snapshot', 'manifest', 'prepare_log', 'png', 'packet', 'source_shown_snapshot'):
            if key not in row:
                raise RuntimeError('Closed scene is missing its ' + key + ' artifact')
            check_artifacts(row[key])
            path = Path(row[key]['path']).resolve(strict=True)
            if key == 'prepare_log':
                if path != (evidence_dir / f'ui_window_refresh_prepare_{seq}.log').resolve():
                    raise RuntimeError('Closed scene preparation log escaped its exact evidence path')
            elif not path.is_relative_to(runtime_root):
                raise RuntimeError('Closed scene artifact escaped its private runtime')
        if source_png != (folder / 'popup.png').resolve(strict=True) or \
           Path(row['png']['path']).resolve() != source_png or \
           Path(row['packet']['path']).resolve() != (folder / 'scene.packet').resolve(strict=True) or \
           Path(row['manifest']['path']).resolve() != (folder / 'scene_manifest.json').resolve(strict=True):
            raise RuntimeError('Closed scene was not drawn from its exact newly prepared contribution')
        for ref, expected in ((row['snapshot'], scene['closed_snapshot']),
                              (row['source_shown_snapshot'], scene['shown_snapshot'])):
            if Path(ref['path']).resolve() != Path(expected['path']).resolve() or ref['sha256'] != expected['sha256']:
                raise RuntimeError('Scene refresh lost its original live shown/closed snapshot identity')
        manifest = _artifact_json(row['manifest'])
        if manifest.get('status') != 'ACTUAL_SDK_CLOSED_POPUP_EMPTY_SCENE_COMPILED' or \
           manifest.get('closed_context_not_drawn') is not True or manifest.get('snapshot_state_unchanged') is not True or \
           manifest.get('snapshot', {}).get('sha256') != row['snapshot']['sha256'] or \
           manifest.get('packet', {}).get('sha256') != row['packet']['sha256'] or \
           (manifest.get('width'), manifest.get('height'), manifest.get('sprite_count'), manifest.get('texture_count')) != (1920, 1080, 0, 0) or \
           any(manifest.get(key) != [] for key in ('hit_regions', 'geometry', 'labels', 'selected_assets', 'font_sources')):
            raise RuntimeError('An inactive context retained visible paint or input regions')
        if Path(row['packet']['path']).read_bytes() != b'ZSUPIX01' + struct.pack('<5I', 1920, 1080, 0, 0, 0):
            raise RuntimeError('Closed context packet does not contain exactly zero paint/input commands')
        old_inputs = [i for i, line in enumerate(lines) if line.startswith(f'UI_WINDOW_INPUT={seq}|')]
        request_index = lines.index(f'UI_WINDOW_REFRESH_REQUEST={seq}|{seq * 25}|{row["snapshot"]["path"]}')
        ready_index = lines.index('UI_WINDOW_REFRESH_READY=' + text)
        frame_index = next(i for i, line in enumerate(lines) if line.startswith(f'UI_WINDOW_FRAME={seq}|closed|'))
        device_index = lines.index('UI_WINDOW_REFRESH_DEVICE=' + '|'.join(device))
        complete_index = lines.index(f'UI_WINDOW_REFRESH_COMPLETE={seq}|1|0|2|owner-thread')
        unchanged_index = lines.index(f'UI_WINDOW_REFRESH_STATE_UNCHANGED={seq}|after-refresh')
        final_index = lines.index(f'UI_WINDOW_COMPLETE={seq}|2|1|owner-thread')
        if len(old_inputs) != 3 or not old_inputs[1] < request_index < frame_index < device_index < ready_index < \
                old_inputs[2] < complete_index < unchanged_index < final_index:
            raise RuntimeError('Closed UI redraw and new-generation input did not follow the original close batch')
        checked.append({**row, 'same_hwnd_verified': True, 'same_device_identity_verified': True,
                        'device_identity_before': old_device, 'device_identity_after': new_device,
                        'scene_generation_before': before, 'scene_generation_after': after,
                        'inactive_hit_regions_removed_verified': True, 'closed_state_unchanged_after_refresh': True,
                        'world_frame_restored_verified': False})
    return checked


def _verify_gpu_frames(window_report, output, scenes, windows, runtime_root, *, refresh_rows=()):
    frames = window_report.get('frames')
    native = re.findall(r'^UI_WINDOW_FRAME=(.+)$', output, re.M)
    expected_order = [(seq, phase) for seq in (1, 2) for phase in
                      (('initial', 'resized', 'closed') if refresh_rows else ('initial', 'resized'))]
    if not isinstance(frames, list) or len(frames) != len(expected_order) or len(native) != len(expected_order) or \
       [(row.get('sequence'), row.get('phase')) for row in frames] != expected_order:
        raise RuntimeError('GPU frames do not contain the exact ordered captures for the selected popup profile')
    checked = []
    previous = None
    lines = output.splitlines()
    context_rows = re.findall(r'^UI_WINDOW_DISPLAY_CONTEXT=(\d+)\|(\d+)\|([^|\r\n]+)\|([^|\r\n]+)$', output, re.M)
    if len(context_rows) != 2 or [int(row[0]) for row in context_rows] != [1, 2]:
        raise RuntimeError('Both owner HWNDs require their exact native session/desktop context')
    contexts = {int(seq): {'session_id': int(session), 'window_station': station, 'thread_desktop': desktop}
                for seq, session, station, desktop in context_rows}
    for frame, text in zip(frames, native):
        fields = text.split('|', 12)
        if len(fields) != 13:
            raise RuntimeError('Native GPU metadata has an invalid field count')
        seq, phase, hwnd, tid, width, height, renders, presents, hr, device, occluded, visible, path = fields
        seq, hwnd, tid, width, height, renders, presents, hr, occluded, visible = map(
            int, (seq, hwnd, tid, width, height, renders, presents, hr, occluded, visible))
        index = len(checked)
        if (seq, phase) != expected_order[index] or \
           [width, height] != ([1000, 700] if phase == 'initial' else [900, 600]) or \
           renders <= 0 or presents != renders or hr not in (0, 0x087A0001) or occluded != int(hr == 0x087A0001) or visible != 1 or \
           device not in ('hardware', 'warp'):
            raise RuntimeError('GPU capture lacks exact dimensions/device/nonfailed Present status metadata')
        window = windows[seq - 1]
        values = {'sequence': seq, 'phase': phase, 'hwnd': hwnd, 'pid': window['pid'], 'owner_thread': tid,
                  'client': [width, height], 'render_count': renders, 'present_count': presents,
                  'present_hresult': hr, 'device_kind': device, 'present_occluded': bool(occluded),
                  'native_visible': True, 'parent_visible': True, 'desktop_context': contexts[seq],
                  'desktop_pixels_verified': False}
        if any(frame.get(key) != value for key, value in values.items()) or \
           (hwnd, tid) != (window['hwnd'], window['owner_thread']):
            raise RuntimeError('GPU metadata differs between the owner process and bounded parent driver')
        capture = Path(path).resolve(strict=True)
        scene = refresh_rows[seq - 1] if phase == 'closed' else scenes[seq - 1]
        expected_path = Path(scene['png']['path']).parent / f'frame-{phase}.png'
        if capture != expected_path.resolve(strict=True) or not capture.is_relative_to(runtime_root) or \
           Path(frame.get('png', {}).get('path', '')).resolve() != capture:
            raise RuntimeError('GPU frame is not the exact immutable capture from its popup directory')
        check_artifacts(frame['png'])
        pixel_check = (verify_closed_frame if phase == 'closed' else verify_frame)(Path(scene['png']['path']), capture, width, height)
        if frame.get('pixel_check') != pixel_check:
            raise RuntimeError('Independent GPU pixel recheck differs from the retained parent check')
        parity_key = 'pixel_content_verified' if phase == 'closed' else 'pixel_parity_verified'
        if pixel_check.get(parity_key) is not True or \
           pixel_check.get('capture_origin_verified') is not False or \
           pixel_check.get('same_swapchain_buffer_verified') is not False or \
           pixel_check.get('desktop_capture_verified') is not False:
            raise RuntimeError('The pure pixel checker exceeded its evidence scope')
        current_index = lines.index('UI_WINDOW_FRAME=' + text)
        unchanged_index = lines.index(f'UI_WINDOW_STATE_UNCHANGED={seq}|before-input')
        if phase != 'closed' and current_index >= unchanged_index or phase == 'closed' and current_index <= unchanged_index:
            raise RuntimeError('GPU draw/resize/capture happened after shown-state preservation or input')
        if previous and seq == previous['sequence'] and (device != previous['device_kind'] or
                renders <= previous['render_count'] or presents <= previous['present_count']):
            raise RuntimeError('GPU resize changed device identity or failed to advance Present')
        checked.append({**values, 'png': frame['png'], 'pixel_check': pixel_check,
                        'owned_native_draw_capture_present_sequence_verified': True,
                        'desktop_pixels_verified': False, 'human_input_verified': False})
        previous = checked[-1]
    return checked


def check_bounds(value):
    if not isinstance(value, dict) or not isinstance(value.get('checked'), list) or not value['checked']:
        raise RuntimeError('Independent retained-runtime control bounds are missing')
    if not isinstance(value.get('deferred'), list) or value.get('retail_layout_equivalence_verified') is not False:
        raise RuntimeError('Deferred retail-layout checks are not recorded')
    close = [row for row in value['checked'] if row.get('key') == 12]
    if len(close) != 1 or close[0].get('kind') != 'GridButton':
        raise RuntimeError('Independent bounds evidence omits the actual CloseButton')


def _baseline_rows(path):
    check_artifacts(artifact(path))
    proof = json.loads(path.read_text(encoding='utf-8'))
    if path.resolve() != BASELINE_PROOF.resolve() or digest(path)!=BASELINE_PROOF_SHA256:
        raise RuntimeError('The comparison input must be the reviewed immutable 8-run proof')
    if proof.get('status') != 'ACTUAL_SDK_FOUND_VALUE_ORDERED_RESULTS_AND_RESTORE_PASS' or \
       proof.get('gamecore_loaded') is not True or proof.get('physical_multicore_verified') is not False or \
       proof.get('performance_improvement_verified') is not False:
        raise RuntimeError('Selected shared Found-value reference proof has an unexpected scope')
    matches = {}
    for language, workers in (('en_US', 0), ('ko_KR', 4)):
        rows = [row for row in proof.get('runs', []) if row.get('language') == language and
                row.get('found_value_workers') == workers and row.get('ui_popups_enabled') is True]
        if len(rows) != 1:
            raise RuntimeError(f'No unique same-language/same-worker baseline row for {language}/{workers}')
        row = rows[0]
        check_artifacts(row)
        if row.get('final_turn') != 50 or row.get('inputs', {}).get(DLL_NAME) != BASELINE_CORE_SHA256 or \
           row.get('found_value_input_layout') != 'SHARED_FACTS':
            raise RuntimeError('Selected runtime baseline does not match the reviewed 50-turn SDK build')
        matches[language] = row
    return proof, matches


def _signature_bytes(value):
    # Native pair records become JSON arrays in retained evidence. Preserve
    # their integer values/order while treating tuples and JSON lists equally.
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode('ascii')


def _compare_to_baseline(actual, actual_ui, actual_found_calls, actual_city_traces, baseline):
    if actual['language'] != baseline['language'] or actual['final_turn'] != baseline['final_turn'] or \
       actual['found_value_workers'] != baseline['found_value_workers'] or actual['final_turn'] != 50:
        raise RuntimeError('Live-window run does not match its same-language/same-worker reference')
    if actual.get('workers') != baseline.get('workers') or actual.get('city_site_workers') != baseline.get('city_site_workers'):
        raise RuntimeError('Live-window run changed exploration or city-site worker settings')
    if actual['inputs'].get(DLL_NAME) != baseline['inputs'].get(DLL_NAME) or \
       actual['inputs'].get(DLL_NAME) != BASELINE_CORE_SHA256:
        raise RuntimeError('Live-window GameCore identity differs from its reference')
    # The native presenter requires a newly built host executable. Its only
    # permitted bundle difference is the matching executable hash line.
    if set(actual['inputs']) != set(baseline['inputs']):
        raise RuntimeError('Live-window and reference input manifests have different file sets')
    differing = {name for name in actual['inputs'] if actual['inputs'][name] != baseline['inputs'][name]}
    if differing != {'ZeroSisHost_x64.exe', 'bundle.manifest'}:
        raise RuntimeError('Live-window run changed inputs outside its host executable and bundle identity')
    for name, digest_value in baseline['inputs'].items():
        if name not in {'ZeroSisHost_x64.exe', 'bundle.manifest'} and actual['inputs'].get(name) != digest_value:
            raise RuntimeError('Live-window SDK/runtime input differs from the selected reference: ' + name)
    manifests = [_bundle_manifest(actual), _bundle_manifest(baseline)]
    host_name = b'ZeroSisHost_x64.exe|'
    manifest_host_lines = []
    for data, row in zip(manifests, (actual, baseline)):
        lines = [line for line in data.splitlines() if line.startswith(host_name)]
        host_hash = row['inputs']['ZeroSisHost_x64.exe'].encode('ascii')
        if len(lines) != 1 or lines[0] != host_name + host_hash or data.count(lines[0]) != 1:
            raise RuntimeError('Host bundle manifest does not name its exact verified executable hash')
        manifest_host_lines.append(lines[0])
    old_line, new_line = manifest_host_lines[1], manifest_host_lines[0]
    if old_line == new_line or manifests[0] != manifests[1].replace(old_line, new_line, 1):
        raise RuntimeError('The bundle manifest differs outside its single host executable SHA-256 token')
    for name in ('extended_observations', 'extended_events', 'fixture_promotions',
                 'fixture_promotion_policy_logs', 'input_routes', 'action_records', 'final_players'):
        if actual.get(name) != baseline.get(name):
            raise RuntimeError('Live-window run changed same-worker continuation state: ' + name)
    state_frames = lambda row: [{'turn': item['turn'], 'frames': item['frames']}
                                for item in row['extended_frames']]
    if state_frames(actual) != state_frames(baseline):
        raise RuntimeError('Live-window run changed continued SDK state frames')
    if [row['sha256'] for row in actual['extended_snapshots']] != \
       [row['sha256'] for row in baseline['extended_snapshots']]:
        raise RuntimeError('Live-window run changed same-worker extended-turn snapshots')
    for archive in ('checkpoint', 'restored_checkpoint', 'final'):
        current = actual['archive_comparisons'][archive]
        reference = baseline['archive_comparisons'][archive]
        if current.get('excluded_bytes') != reference.get('excluded_bytes') or \
           current.get('excluded_bytes') != {'section': [4, 0], 'offset': 34, 'count': 16, 'field': 'CvMap::m_guid'} or \
           len(current['sections']) != 133 or len(reference['sections']) != 133:
            raise RuntimeError('Live-window SDK archive does not have the expected 133-section shape')
        actual_manifest_section = [item for item in current['sections']
                                   if (item['kind'], item['index']) == (1, 0)]
        baseline_manifest_section = [item for item in reference['sections']
                                     if (item['kind'], item['index']) == (1, 0)]
        for section, data in ((actual_manifest_section, manifests[0]),
                              (baseline_manifest_section, manifests[1])):
            expected = {'kind': 1, 'index': 0, 'bytes': len(data),
                        'comparison_sha256': hashlib.sha256(data).hexdigest()}
            if section != [expected]:
                raise RuntimeError('SDK archive bundle-manifest section differs from its verified input bytes')
        actual_gameplay = [item for item in current['sections'] if (item['kind'], item['index']) != (1, 0)]
        baseline_gameplay = [item for item in reference['sections'] if (item['kind'], item['index']) != (1, 0)]
        if len(actual_gameplay) != 132 or actual_gameplay != baseline_gameplay:
            raise RuntimeError('Live-window SDK gameplay archive sections differ beyond CvMap GUID normalization')
    if actual_ui['official_ui_signature'] != baseline.get('official_ui_signature'):
        raise RuntimeError('Live-window official UI draw/lifecycle signature differs from its reference')
    baseline_found_calls = baseline.get('found_value_calls')
    if not isinstance(baseline_found_calls, list) or \
       _signature_bytes(semantic_signature(actual_found_calls)) != _signature_bytes(semantic_signature(baseline_found_calls)):
        raise RuntimeError('Live-window Found-value ordered scores, area totals, or owner-call sequence differ')
    baseline_city_traces = baseline.get('city_site_traces')
    if not isinstance(baseline_city_traces,list) or \
       _signature_bytes(city_site_signature(actual_city_traces)) != _signature_bytes(city_site_signature(baseline_city_traces)):
        raise RuntimeError('Live-window CitySite ordered scores, reduction, or owner-call sequence differ')
    base_result = _artifact_json(baseline['result'])
    base_snapshots = []
    for sequence in (1, 2):
        shown_ref = _snapshot_from_result(base_result, sequence, 'shown')
        closed_ref = _snapshot_from_result(base_result, sequence, 'closed')
        base_snapshots.append((json.loads(Path(shown_ref['path']).read_text(encoding='utf-8')),
                               json.loads(Path(closed_ref['path']).read_text(encoding='utf-8'))))
    for scene, (shown, closed) in zip(actual_ui['scenes'], base_snapshots):
        live_shown = _artifact_json(scene['shown_snapshot'])
        live_closed = _artifact_json(scene['closed_snapshot'])
        if live_shown != shown or live_closed != closed:
            raise RuntimeError('Shown/closed popup state differs from same-worker baseline at turn ' + str(scene['turn']))
    return {'baseline_run_id': baseline['run_id'], 'baseline_result': baseline['result'],
            'same_language': True, 'same_found_value_worker_setting': True,
            'same_gamecore_and_nonhost_runtime_inputs': True, 'archives_compared_per_state': 3,
            'archive_sections_checked_per_state': 133, 'gameplay_sections_equal_per_state': 132,
            'bundle_manifest_identity_change': 'section 1,0; exact host executable SHA-256 line replacement',
            'only_gameplay_normalization': 'CvMap::m_guid bytes 34..49 in section 4,0',
            'turn_continuation_and_state_equal': True, 'popup_shown_closed_snapshots_equal': True,
            'official_ui_rng_and_ranking_signature_equal': True,
            'found_value_calls_compared': len(actual_found_calls),
            'found_value_plot_scores_compared': sum(len(call['values']) for call in actual_found_calls),
            'found_value_signature_sha256': hashlib.sha256(_signature_bytes(semantic_signature(actual_found_calls))).hexdigest(),
            'found_value_ordered_scores_areas_call_order_equal': True,
            'city_site_calls_compared':len(actual_city_traces),
            'city_site_plot_scores_compared':sum(len(call['ordered_values']) for call in actual_city_traces),
            'city_site_signature_sha256':hashlib.sha256(_signature_bytes(city_site_signature(actual_city_traces))).hexdigest(),
            'city_site_ordered_scores_reduction_call_order_equal':True,
            'diagnostic_timing_excluded': ['extended_frames[*].duration_us'],
            'scoring_comparison_scope':'owner session/call/turn/player identity, every ordered score, area totals and reductions; scheduling identities and diagnostic timings are not gameplay state'}


def _bundle_manifest(row):
    result = _artifact_json(row['result'])
    request = _artifact_json(result['request'])
    matches = [item for item in request.get('inputs', []) if Path(item['path']).name == 'bundle.manifest']
    if len(matches) != 1:
        raise RuntimeError('Runtime request does not contain one bundle.manifest input')
    check_artifacts(matches[0])
    data = Path(matches[0]['path']).read_bytes()
    if hashlib.sha256(data).hexdigest() != row['inputs'].get('bundle.manifest'):
        raise RuntimeError('Bundle manifest artifact does not match its recorded input hash')
    return data


def verify_pair(runtime_paths, comparison_path, display_resize=False, refresh_closed=False):
    if refresh_closed and not display_resize:
        raise RuntimeError('Closed scene refresh requires GPU display verification')
    if len(runtime_paths) != 2:
        raise RuntimeError('Exactly two live runtime results are required')
    proof, baseline_by_language = _baseline_rows(comparison_path)
    rows = []
    ui_rows = []
    found_calls = []
    city_traces = []
    for path in runtime_paths:
        path = path.resolve(strict=True)
        save_root = (PROJECT / 'evidence/save_restore').resolve()
        if path.name != 'result.json' or path.parent.parent.resolve() != save_root:
            raise RuntimeError('Runtime result must be an existing evidence/save_restore/<run>/result.json')
        run_id = path.parent.name
        result_ref = artifact(path)
        result = _artifact_json(result_ref)
        request = _artifact_json(result.get('request'))
        check_artifacts(result)
        check_artifacts(request)
        if request.get('run_id') != run_id:
            raise RuntimeError('Run path does not bind to its exact request ID')
        workers = request.get('found_value_workers')
        language = request.get('command', [None, None, None])[2]
        if (language, workers) not in (('en_US', 0), ('ko_KR', 4)):
            raise RuntimeError('Live-window pair must be EN worker zero and KO worker four')
        row = inspect_extended(run_id, ui_popups=True, fixture_promotions=True, fixture_unit_actions=True,
                               sdk_city_sites=True, city_site_workers=0, sdk_found_values=True,
                               found_value_workers=workers, ui_window_popups=True, ui_window_display=display_resize,
                               ui_window_refresh=refresh_closed)
        output = Path(result['stdout']['path']).read_text(encoding='utf-8')
        live = _verify_live_window(result, request, output, run_id, display_resize=display_resize, refresh_closed=refresh_closed)
        calls=parse_trace_block(output,workers,final_turn=50)
        layouts=parse_shared_layouts(output,calls)
        traces=inspect_traces(output,row['city_site_workers'],50)
        live['found_value_summary']={'calls':len(calls),'plot_scores':sum(len(call['values']) for call in calls),
                                    'shared_input_layouts_verified':len(layouts)}
        live['city_site_summary']={'calls':len(traces),'plot_scores':sum(len(call['ordered_values']) for call in traces)}
        live['official_ui_signature'] = _ui_signature(live['scenes'])
        rows.append(row)
        ui_rows.append(live)
        found_calls.append(calls)
        city_traces.append(traces)
    by_language = {row['language']: index for index, row in enumerate(rows)}
    if set(by_language) != {'en_US', 'ko_KR'} or len(rows) != 2:
        raise RuntimeError('Live-window runs must contain one English and one Korean profile')
    comparisons = []
    for language in ('en_US', 'ko_KR'):
        index = by_language[language]
        comparison = _compare_to_baseline(rows[index], ui_rows[index],
                                          found_calls[index],city_traces[index],baseline_by_language[language])
        comparisons.append({'language': language, 'workers': rows[index]['found_value_workers'], **comparison})
    return proof, rows, ui_rows, comparisons


def _ui_signature(scenes):
    signature = []
    for scene in scenes:
        shown = _artifact_json(scene['shown_snapshot'])
        draws = shown.get('draws')
        if not isinstance(draws, list) or not draws:
            raise RuntimeError('Live official popup snapshot has no RNG observations')
        ranking = [node for node in _walk(shown['tree']) if node.get('id') == 'PlayerListStack']
        if len(ranking) != 1:
            raise RuntimeError('Live official popup snapshot lacks its original ranking stack')
        visible = [child for child in ranking[0]['children'] if not child['hidden']]
        signature.append([scene['turn'], draws[-1]['value'], draws, len(visible)])
    return signature


def _walk(node):
    yield node
    for child in node.get('children', []):
        yield from _walk(child)


def _verify_gpu_component(path, ui_rows, refresh_closed=False):
    if path is None:
        raise RuntimeError('The GPU profile requires the exact retained window component proof')
    path = path.resolve(strict=True)
    if path.name != 'conformance.json' or path.parent.parent != (PROJECT / 'evidence/bitmap_window').resolve():
        raise RuntimeError('GPU component proof escaped its expected unique evidence root')
    component = _artifact_json(artifact(path))
    before = component.get('source_hashes_before')
    if component.get('status') != 'BITMAP_WINDOW_COMPONENT_PASS' or component.get('error') is not None or \
       component.get('source_inputs_unchanged') is not True or before != component.get('source_hashes_after') or \
       component.get('gamecore_loaded') is not False or component.get('sdk_linked') is not False or \
       component.get('real_user_click_verified') is not False:
        raise RuntimeError('GPU window component did not pass its preserved lifetime/capture scope')
    for ref in component.get('frozen_inputs', {}).values():
        check_artifacts(ref)
    if set(component.get('builds', {})) != {'O2', 'Od'}:
        raise RuntimeError('GPU component omits one of the two native optimization builds')
    for build in component['builds'].values():
        if digest(Path(build['executable'])) != build['executable_sha256']:
            raise RuntimeError('GPU component executable changed after native tests')
    tests = component.get('test_runs')
    if not isinstance(tests, list) or len(tests) != 2:
        raise RuntimeError('GPU component tests are incomplete')
    counts = {test.get('checks') for test in tests}
    if len(counts) != 1 or not counts <= {38, 54} or refresh_closed and counts != {54}:
        raise RuntimeError('The GPU component does not include the required scene replacement regressions')
    for test in tests:
        if test.get('returncode') != 0 or test.get('timed_out') is not False or \
           test.get('com_init_markers') != 2 or test.get('com_uninit_markers') != 2 or \
           len(test.get('retained_gpu_frame_pngs', [])) != (5 if test['checks'] == 54 else 2):
            raise RuntimeError('GPU component capture/resize/COM regression gates were not completed')
        check_artifacts(test)
        log = Path(test['log']['path']).read_text(encoding='utf-8')
        expected = f'PASS|{test["checks"]}|hidden owned GPU HWND, same-buffer capture, resize, one-shot COM lifetime, owner-thread checks, and isolated input queue'
        if log.splitlines().count(expected) != 1:
            raise RuntimeError('GPU component test log does not prove its exact completed check count')
    for row in component.get('compiler_dependencies', []):
        if digest(Path(row['frozen_path'])) != row['frozen_sha256'] or row['sha256'] != row['frozen_sha256']:
            raise RuntimeError('GPU component frozen compiler input changed')
    for row in component.get('resolved_libraries', {}).values():
        if digest(Path(row['frozen_path'])) != row['frozen_sha256'] or row['sha256'] != row['frozen_sha256']:
            raise RuntimeError('GPU component frozen system library changed')
    for ui in ui_rows:
        build = _artifact_json(ui['host_build'])
        for name in ('window', 'window_header', 'renderer', 'renderer_header'):
            if build.get('source_hashes_before', {}).get(name) != before.get(name):
                raise RuntimeError('Actual SDK host consumed different GPU component source')
        window_source = _by_name(build['window_sources'], 'BitmapWindow.cpp')
        text = Path(window_source['path']).read_text(encoding='utf-8')
        frame_body = text.split('bool BitmapWindow::RenderFrame(', 1)[1].split('void BitmapWindow::QueueKey(', 1)[0]
        stages = ['->DrawBitmap(', '->EndDraw(', '->CopyResource(', '->Map(', '->Present(']
        positions = [frame_body.index(stage) for stage in stages]
        if positions != sorted(positions) or not all(token in text for token in
                ('CreateSwapChainForHwnd', 'CreateDxgiSurfaceRenderTarget', 'GetDesc1', 'CREATE_NEW')):
            raise RuntimeError('Frozen GPU backend does not preserve same-buffer draw/readback/Present ordering')
        if refresh_closed:
            update_body = text.split('bool BitmapWindow::UpdateScene(', 1)[1].split('std::uint64_t BitmapWindow::SceneGeneration(', 1)[0]
            if not all(token in update_body for token in ('DecodeSceneBitmap', 'PumpMessages', 'nextBitmap',
                    'hits_.swap(nextHits)', '++sceneGeneration_')) or any(token in update_body for token in
                    ('CreateWindow', 'CreateDevice', 'CreateSwapChain', 'DestroyWindow', 'ReleaseRenderTarget', 'device.Reset')):
                raise RuntimeError('Scene replacement is not an atomic candidate commit on the same owned GPU window')
            host_source = _by_name(build['sources'], 'UiWindowPresentation.h')
            host_text = Path(host_source['path']).read_text(encoding='utf-8')
            if not all(token in host_text for token in ('event.sceneGeneration!=inputGeneration',
                    'window.UpdateScene(next,nextPng', 'beforeRefresh.deviceIdentity!=afterRefresh.deviceIdentity',
                    'events.size()!=1 || refreshAccepted || snapshot()!=closed')):
                raise RuntimeError('The frozen actual host does not enforce scene generation and closed-state input checks')
    return artifact(path)


def _write_report(runtime_paths, comparison_path, display_resize=False, gpu_component=None, refresh_closed=False):
    closure, edges = local_python_closure(Path(__file__).resolve())
    if len({path.name.casefold() for path in closure}) != len(closure):
        raise RuntimeError('Python validator closure contains colliding frozen filenames')
    identifier = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ_') + uuid.uuid4().hex[:10]
    directory = ROOT / 'validators' / identifier
    frozen = directory / 'frozen'
    frozen.mkdir(parents=True, exist_ok=False)
    before = {path: digest(path) for path in closure}
    frozen_inputs = []
    for source in sorted(closure, key=lambda value: str(value).casefold()):
        target = frozen / source.name
        shutil.copy2(source, target)
        if digest(target) != before[source]:
            raise RuntimeError('Validator changed while the immutable closure was frozen')
        frozen_inputs.append({'original_source_path': str(source.resolve()),
                              'original_source_sha256': before[source],
                              'frozen': artifact(target)})
    try:
        proof, rows, ui_rows, comparisons = verify_pair(runtime_paths, comparison_path, display_resize=display_resize,
                                                      refresh_closed=refresh_closed)
        component_ref = _verify_gpu_component(gpu_component, ui_rows, refresh_closed=refresh_closed) if display_resize else None
    except Exception as error:
        failure={'status':'LIVE_SDK_UI_WINDOW_VALIDATOR_FAILED','error':str(error),'error_type':type(error).__name__,
                 'runtime_results':[artifact(path) for path in runtime_paths],
                 'comparison_proof':artifact(comparison_path),'validator_frozen_inputs':frozen_inputs,
                 'validator_source_hashes_before':{str(path):value for path,value in before.items()},
                 'validator_source_hashes_after':{str(path):digest(path) for path in closure},
                 'sdk_or_host_execution_performed':False}
        (directory/'failure.json').write_text(json.dumps(failure,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        raise
    after = {path: digest(path) for path in closure}
    if after != before:
        raise RuntimeError('A validator source changed during live UI verification')
    report = {
        'status': 'LIVE_SDK_UI_CLOSED_SCENE_GPU_REFRESH_AND_SAME_WORKER_STATE_PASS' if refresh_closed else
                  'LIVE_SDK_UI_GPU_SURFACE_RESIZE_AND_SAME_WORKER_STATE_PASS' if display_resize else
                  'LIVE_SDK_UI_WINDOW_AND_SAME_WORKER_STATE_PASS',
        'runs': [{'runtime': row, 'live_ui_window': ui} for row, ui in zip(rows, ui_rows)],
        'comparisons': comparisons,
        'comparison_proof': artifact(comparison_path),
        'validator_frozen_inputs': frozen_inputs,
        'validator_import_edges': [{'from_sha256': before[a], 'to_sha256': before[b]}
                                   for a, b in edges],
        'validator_source_hashes_before': {str(path.resolve()): value for path, value in before.items()},
        'validator_source_hashes_after': {str(path.resolve()): value for path, value in after.items()},
        'validator_inputs_unchanged': True,
        'actual_owned_hwnd_and_owner_thread_verified': True,
        'display_resize_enabled': display_resize,
        'refresh_closed_enabled': refresh_closed,
        'gpu_component': component_ref,
        'owned_gpu_draw_readback_present_resize_verified': display_resize,
        'owned_same_hwnd_and_device_closed_scene_refresh_verified': refresh_closed,
        'inactive_popup_hit_regions_removed_verified': refresh_closed,
        'managed_input_batches_only': True,
        'uncoordinated_physical_input_epoch_isolation_verified': False,
        'live_gameplay_decision_redraw_verified': False,
        'world_frame_restored_after_popup_verified': False,
        'desktop_pixels_verified': False,
        'official_ui_vm_and_snapshot_verified': True,
        'native_inputs_are_automated_test_messages': True,
        'real_human_input_verified': False,
        'retail_ui_timing_verified': False,
        'installed_game_launched': False,
        'full_engine_equivalence_verified': False,
        'gameplay_world_equivalence_verified': False,
        'physical_multicore_verified': False,
        'performance_improvement_verified': False,
        'scope': 'LIVE_ISOLATED_SDK_POPUP_VM_OWNED_GPU_HWND_CLOSED_SCENE_REFRESH_TEST_INPUT_AND_SAME_WORKER_SAVE_RESTORE_CONTINUATION' if refresh_closed else
                 'LIVE_ISOLATED_SDK_POPUP_VM_OWNED_GPU_HWND_DISPLAY_RESIZE_TEST_INPUT_AND_SAME_WORKER_SAVE_RESTORE_CONTINUATION' if display_resize else
                 'LIVE_ISOLATED_SDK_POPUP_VM_OWNED_HIDDEN_HWND_TEST_INPUT_AND_SAME_WORKER_SAVE_RESTORE_CONTINUATION',
    }
    check_artifacts(report)
    path = directory / 'conformance.json'
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (ROOT / 'latest.json').write_text(json.dumps(artifact(path), indent=2) + '\n', encoding='utf-8')
    return report, path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-result', action='append', type=Path, required=True,
                        help='Existing actual save_restore/<run>/result.json; repeat twice')
    parser.add_argument('--comparison', type=Path, default=BASELINE_PROOF,
                        help='Found-value 8-run comparison proof; defaults to the reviewed reference')
    parser.add_argument('--display-resize', action='store_true', help='Require owned GPU presentation, resize, and both frame captures')
    parser.add_argument('--refresh-closed', action='store_true', help='Require same-window/device redraw after the official callback dequeues the context')
    parser.add_argument('--gpu-component', type=Path, help='Exact retained O2/Od GPU window component proof; required with display resize')
    args = parser.parse_args()
    if len(args.runtime_result) != 2 or len({str(path.resolve()) for path in args.runtime_result}) != 2:
        parser.error('Provide exactly two distinct actual runtime result paths')
    if any(not path.is_file() for path in args.runtime_result) or not args.comparison.is_file():
        parser.error('All runtime and comparison evidence paths must already exist')
    if args.display_resize != bool(args.gpu_component) or (args.gpu_component and not args.gpu_component.is_file()):
        parser.error('--display-resize requires exactly one existing --gpu-component proof')
    if args.refresh_closed and not args.display_resize:
        parser.error('--refresh-closed requires --display-resize')
    report, path = _write_report(args.runtime_result, args.comparison.resolve(),
                                 display_resize=args.display_resize, gpu_component=args.gpu_component,
                                 refresh_closed=args.refresh_closed)
    print(json.dumps({'status': report['status'], 'runs': len(report['runs']),
                      'evidence': str(path), 'sha256': digest(path)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
