"""Verify original owned-city UI callbacks and a fresh-process native-save restore pair.

This validator binds actual posted HWND clicks to original retained CityView
targets, checks the SDK focus/avoid-growth operations and production return,
then compares the turn-one save with a fresh-process restore through turn two.
It does not establish retail renderer equivalence, full 3D CityView, or human input.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import struct
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from collect_baseline import PROJECT, digest
from verify_first_turn_candidate import inspect_save
from verify_world_builder_map_object import check_artifacts
import verify_city_capture_restore as save_restore
import verify_interactive_game as interactive
import verify_restore_game_metadata as metadata

EVIDENCE = PROJECT / 'evidence/interactive_game'
RUNTIME = PROJECT / 'Build/InteractiveGameRuntime'
RUN_ID = re.compile(r'\d{8}T\d{6}Z_[0-9a-f]{12}\Z')
ALLOWED_PROFILES = {
    'POSTED_HWND_CITY_CAPTURE_SMOKE',
    'POSTED_HWND_CONTINUOUS_TREE_DECISION_UI_LOOP',
}
TARGET_MARKERS = {
    'WorkerHeader': r'^INTERACTIVE_OWNED_CITY_HEADER_TARGET=(\d+)\|(\d+)\|(\d+)$',
    'focus': r'^INTERACTIVE_OWNED_CITY_FOCUS_TARGET=(\d+)\|(-?\d+)\|(\d+)\|(\d+)$',
    'AvoidGrowthButton': r'^INTERACTIVE_OWNED_CITY_GROWTH_TARGET=(\d+)\|([01])\|(\d+)\|(\d+)$',
    'ProductionButton': r'^INTERACTIVE_OWNED_CITY_PRODUCTION_TARGET=(\d+)\|(\d+)\|(\d+)$',
    'ReturnToMapButton': r'^INTERACTIVE_OWNED_CITY_RETURN_TARGET=(\d+)\|(\d+)\|(\d+)$',
}
TARGET_MARKER_NAMES = {
    'WorkerHeader': 'INTERACTIVE_OWNED_CITY_HEADER_TARGET',
    'focus': 'INTERACTIVE_OWNED_CITY_FOCUS_TARGET',
    'AvoidGrowthButton': 'INTERACTIVE_OWNED_CITY_GROWTH_TARGET',
    'ProductionButton': 'INTERACTIVE_OWNED_CITY_PRODUCTION_TARGET',
    'ReturnToMapButton': 'INTERACTIVE_OWNED_CITY_RETURN_TARGET',
}
FROZEN_INPUTS = (
    'verify_owned_city_ui.py', 'verify_interactive_game.py', 'verify_city_capture_restore.py',
    'verify_restore_game_metadata.py', 'verify_first_turn_candidate.py',
    'verify_world_builder_map_object.py', 'collect_baseline.py', 'run_interactive_game.py',
    'interactive_ui_driver.py', 'prepare_ui_popup_assets.py', 'build_ui_window_host.py',
)
CITY_UI_SOURCES = (
    PROJECT / 'Source/Assets/UI/Assets/DLC/Expansion2/UI/InGame/CityView/CityView.lua',
    PROJECT / 'Source/Assets/UI/Assets/DLC/Expansion2/UI/InGame/CityView/CityView.xml',
    PROJECT / 'Source/Assets/UI/Assets/DLC/Expansion2/UI/InGame/CityView/CityView_small.xml',
    PROJECT / 'Source/Assets/UI/Assets/UI/SupportFunctions.lua',
)
RETAINED_HOST_SOURCES = (
    PROJECT / 'Source/Host/UiScene.lua',
    PROJECT / 'Source/Presentation/UiPresentationInput.lua',
    PROJECT / 'Source/Presentation/UiCityView.lua',
    PROJECT / 'Source/Host/UiPopupAssets.generated.h',
    PROJECT / 'Source/SDK_BNW_x64/CvGameCoreDLLUtil/include/CvEnums.h',
)
HOST_POLICY_SOURCES = ('InteractiveGameLoop.h', 'InteractiveGameSession.h', 'UiPopupContext.h', 'UiAudioPlayback.h', 'HostServices.h')
STOCK_AUDIO_SOURCES = tuple(PROJECT / 'Source/Assets/Audio' / name for name in
                           ('Audio2DScripts.xml', 'AudioDefines.xml', 'NotificationBuyTile.wav'))
SECTION_IDENTITIES = ([(kind, 0) for kind in range(1, 6)] +
                      [(6, index) for index in range(64)] +
                      [(7, index) for index in range(64)])
YIELD_ENUM_SOURCE = PROJECT / 'Source/SDK_BNW_x64/CvGameCoreDLL_Expansion2/CvGameCoreEnums.h'
PRODUCTION_GUARD_SOURCE = PROJECT / 'Source/Host/ProductionCommandGuard.lua'
PRODUCTION_POPUP_SOURCE = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Sid Meier's Civilization V") / \
    'Assets/DLC/Expansion2/UI/InGame/Popups/ProductionPopup.lua'


def fail(message: str) -> None:
    raise RuntimeError(message)


def absolute(path: Path | str) -> Path:
    return Path(path).resolve(strict=True)


def digest_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def artifact(path: Path) -> dict[str, Any]:
    resolved = path.resolve(strict=True)
    return {'path': str(resolved), 'sha256': digest(resolved), 'bytes': resolved.stat().st_size}


def freeze_inputs() -> tuple[Path, list[dict[str, Any]], dict[str, str]]:
    proof = EVIDENCE / 'validators' / (
        datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ_') + uuid.uuid4().hex[:12])
    proof.mkdir(parents=True, exist_ok=False)
    sources = ([PROJECT / 'tools' / name for name in FROZEN_INPUTS] +
               list(CITY_UI_SOURCES) + list(RETAINED_HOST_SOURCES) + list(STOCK_AUDIO_SOURCES) +
               [PROJECT / 'Source/Host' / name for name in HOST_POLICY_SOURCES] +
               [YIELD_ENUM_SOURCE, PRODUCTION_GUARD_SOURCE, PRODUCTION_POPUP_SOURCE])
    before: dict[str, str] = {}
    frozen: list[dict[str, Any]] = []
    for source in sources:
        if not source.is_file():
            fail(f'Missing verifier input: {source}')
        source = source.resolve(strict=True)
        before[str(source)] = digest(source)
        target = proof / source.name
        if target.exists():
            target = proof / (source.parent.name + '_' + source.name)
        shutil.copy2(source, target)
        row = artifact(target)
        if row['sha256'] != before[str(source)]:
            fail(f'Frozen verifier/source differs from its input: {source}')
        frozen.append({'original_path': str(source), **row})
    return proof, frozen, before


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding='utf-8'))
    if type(value) is not dict:
        fail(f'Expected a JSON object: {path.name}')
    return value


def checked_path(ref: Any, expected: Path | None = None) -> Path:
    if not isinstance(ref, dict):
        fail('Missing immutable artifact reference')
    check_artifacts(ref)
    path = absolute(ref['path'])
    if expected is not None and path != absolute(expected):
        fail('Artifact reference differs from its exact expected path')
    return path


def checked_json_ref(ref: Any, expected: Path | None = None) -> tuple[Path, dict]:
    path = checked_path(ref, expected)
    return path, read_json(path)


def run_pair(run_id: str) -> tuple[Path, dict, dict, dict, str, str]:
    if not RUN_ID.fullmatch(run_id):
        fail(f'Invalid run identity: {run_id}')
    root = EVIDENCE / run_id
    request_path, result_path = root / 'request.json', root / 'result.json'
    request, result = read_json(request_path), read_json(result_path)
    if request.get('run_id') != run_id or result.get('run_id') != run_id:
        fail('Run request/result identity differs from its evidence directory')
    check_artifacts(request)
    check_artifacts(result)
    checked_path(result.get('request'), request_path)
    attempt_path = checked_path(result.get('attempt'), root / 'attempt.json')
    checked_path(result.get('stdout'), root / 'stdout.log')
    checked_path(result.get('stderr'), root / 'stderr.log')
    attempt = read_json(attempt_path)
    stdout = checked_path(result['stdout']).read_text(encoding='utf-8').replace('\r\n', '\n').replace('\r', '\n')
    stderr = checked_path(result['stderr']).read_text(encoding='utf-8', errors='replace')
    return root, request, result, attempt, stdout, stderr


def runtime_for(request: dict, run_id: str) -> Path:
    runtime = absolute(request.get('cwd', ''))
    expected = absolute(RUNTIME / run_id)
    if runtime != expected:
        fail('Run cwd differs from its exact private runtime')
    return runtime


def immutable_run(run_id: str, root: Path, request: dict, result: dict,
                  attempt: dict, stdout: str, stderr: str, *, restore: bool) -> dict:
    profile = request.get('input_profile')
    if profile not in ALLOWED_PROFILES or request.get('smoke') is not True or \
       request.get('decisions') is not True or request.get('stage_or_mods_changed') is not False:
        fail('Run is not an isolated owned-city decision/save smoke')
    if restore and request.get('city_capture_smoke') is not False:
        fail('Fresh restore must continue the checkpoint without replaying the city-capture fixture')
    if not restore and request.get('city_capture_smoke') is not True:
        fail('Source run must use the verified ordinary-city setup followed by CityView actions')
    save_restore.immutable_result(result, attempt, request, stdout, stderr, capture=not restore)
    if request.get('command') is None or result.get('returncode') != 0 or \
       result.get('timed_out') is not False or result.get('runtime_inputs_unchanged') is not True or \
       attempt.get('status') != 'FINISHED' or attempt.get('returncode') != 0 or \
       attempt.get('timed_out') is not False or attempt.get('host_pid') != result.get('pid') or \
       attempt.get('pid') != result.get('driver_pid'):
        fail('Runner result/attempt does not prove a clean completed distinct Host process')
    if result.get('owned_city_sequence_required') is not True or \
       result.get('owned_city_sequence_verified') is not True or result.get('native_window_posted_input_verified') is not True or \
       result.get('human_input_verified') is not False:
        fail('Runner does not report an actual passing owned-city input sequence with explicit human-input boundary')
    if re.search(r'HOST_FAILURE|HOST_NATIVE_EXCEPTION|HOST_CLEANUP_PENDING|SCRIPT_FAILURE|INTERACTIVE_INPUT_REJECTED',
                 stdout + '\n' + stderr):
        fail('Run output contains Host, cleanup, script, or rejected-input failure')
    runtime = runtime_for(request, run_id)
    provenance = interactive.verify_provenance(request, result, runtime, expected_input_profile=profile)
    driver_command = save_restore.driver_command(request, result, root, runtime,
        checked_path(request['resume_from']['checkpoint_input']) if restore else None)
    driver_path, driver = checked_json_ref(result.get('interactive_ui_driver'), root / 'driver_result.json')
    if driver.get('status') != 'INTERACTIVE_UI_DRIVER_PASS' or driver.get('returncode') != 0 or \
       driver.get('pid') != result.get('pid') or driver.get('error') is not None or \
       driver.get('scene_request_count') != len(driver.get('scene_requests', [])):
        fail('Actual scene driver result is missing, failed, or does not match its completed Host')
    return {'profile': profile, 'runtime': runtime, 'provenance': provenance,
            'driver_path': driver_path, 'driver': driver, 'driver_command': driver_command}


def exact_rows(text: str, marker: str, pattern: str) -> list[tuple[str, ...]]:
    rows = []
    for line in text.splitlines():
        if line.startswith(marker + '='):
            match = re.fullmatch(pattern, line)
            if match is None:
                fail(f'Malformed runtime marker: {marker}')
            rows.append(tuple(match.groups()))
    return rows


def one_marker(text: str, marker: str, pattern: str) -> tuple[str, ...]:
    rows = exact_rows(text, marker, pattern)
    if len(rows) != 1:
        fail(f'Expected one runtime marker {marker}; observed {len(rows)}')
    return rows[0]


def runtime_inputs(request: dict, runtime: Path) -> dict[str, dict]:
    rows = request.get('runtime_inputs')
    if not isinstance(rows, list) or not rows:
        fail('Run request lacks its private runtime-input manifest')
    by_name: dict[str, dict] = {}
    for row in rows:
        path = checked_path(row)
        if not path.is_relative_to(absolute(runtime)) or path.name in by_name or digest(path) != row.get('sha256'):
            fail('Runtime input is duplicate, changed, or outside the private runtime')
        by_name[path.name] = row
    return by_name


def generated_inventory(result: dict, runtime: Path) -> dict[str, list[Path]]:
    paths = []
    rows = result.get('generated_files')
    if not isinstance(rows, list):
        fail('Run result omits its generated-file inventory')
    for row in rows:
        paths.append(checked_path(row))
    session_root = absolute(runtime / 'sessions')
    actual = sorted(absolute(path) for path in session_root.rglob('*') if path.is_file())
    if any(not path.is_relative_to(session_root) for path in paths) or \
       sorted(paths) != actual or len(paths) != len(set(paths)):
        fail('Generated-file inventory is incomplete, duplicated, or outside the exact session tree')
    named: dict[str, list[Path]] = {}
    for path in paths:
        named.setdefault(path.name, []).append(path)
    return named


def exactly_one(named: dict[str, list[Path]], filename: str, runtime: Path) -> Path:
    matches = named.get(filename, [])
    if len(matches) != 1 or not matches[0].is_relative_to(absolute(runtime / 'sessions')):
        fail(f'Expected exactly one generated artifact: {filename}')
    return matches[0]


def runtime_identity(data: bytes) -> tuple[int, int, int, int]:
    try:
        fields = data.decode('utf-8', errors='strict').splitlines()[0].split('|')
        if len(fields) != 5 or fields[0] != 'G':
            raise ValueError
        turn, elapsed, active, plots = map(int, fields[1:])
    except (UnicodeDecodeError, IndexError, ValueError) as exc:
        raise RuntimeError('Semantic SDK snapshot has no valid Game identity') from exc
    if turn < 0 or elapsed < 0 or not 0 <= active < 64 or plots <= 0:
        fail('Semantic SDK identity is outside native limits')
    return turn, elapsed, active, plots


def sdk_yield_values() -> dict[str, int]:
    # The original SDK enum header is retained in the Windows-1252 source encoding.
    text = YIELD_ENUM_SOURCE.read_text(encoding='cp1252', errors='strict')
    match = re.search(r'enum\s+YieldTypes\s*\{([^}]+)\}', text, re.S)
    if match is None:
        fail('Retained Expansion2 SDK has no YieldTypes enum')
    values, current = {}, -1
    for raw in match.group(1).split(','):
        token = re.sub(r'//[^\n]*|/\*.*?\*/', '', raw, flags=re.S).strip()
        if not token:
            continue
        item = re.fullmatch(r'([A-Z][A-Z0-9_]*)\s*(?:=\s*(-?\d+))?', token)
        if item is None:
            fail('Retained Expansion2 YieldTypes enum has an unrecognized declaration')
        current = int(item.group(2)) if item.group(2) is not None else current + 1
        values[item.group(1)] = current
    if values.get('NO_YIELD') != -1 or values.get('YIELD_GOLD') != 2 or values.get('YIELD_FAITH') != 5:
        fail('Retained Expansion2 SDK GOLD/FAITH yield values differ from the expected original enum order')
    return values


def citizen_rows(text: str, phase: str) -> dict[tuple[int, int], tuple[int, int]]:
    matches = exact_rows(text, 'INTERACTIVE_CITY_CITIZENS_STATE',
                         r'^INTERACTIVE_CITY_CITIZENS_STATE=(initial|final)\|(-?\d+)\|(-?\d+)\|(-?\d+)\|([01])$')
    selected = [row for row in matches if row[0] == phase]
    if not selected:
        fail(f'No actual SDK citizen-state rows for phase {phase}')
    result: dict[tuple[int, int], tuple[int, int]] = {}
    for _phase, owner, city, focus, avoid in selected:
        identity = (int(owner), int(city))
        if identity[0] < 0 or identity[1] < 0 or identity in result:
            fail(f'Duplicate or invalid SDK citizen identity in {phase}')
        result[identity] = (int(focus), int(avoid))
    return result


def ui_frames(text: str) -> list[dict[str, Any]]:
    rows = exact_rows(text, 'INTERACTIVE_UI_FRAME',
        r'^INTERACTIVE_UI_FRAME=(\d+)\|(\d+)\|(-?\d+)\|([^|]+)\|(\d+)\|(\d+)\|([^|]+)\|([^|]+)$')
    return [{'sequence': int(a), 'generation': int(b), 'turn': int(c), 'context': d,
             'hwnd': int(e), 'device': int(f), 'snapshot': absolute(g),
             'folder': absolute(h)} for a, b, c, d, e, f, g, h in rows]


def scenes_by_sequence(driver: dict, runtime: Path) -> dict[int, dict]:
    session_root = absolute(runtime / 'sessions')
    result: dict[int, dict] = {}
    rows = driver.get('scene_requests')
    if not isinstance(rows, list):
        fail('UI driver omits actual scene request records')
    for row in rows:
        if type(row) is not dict or type(row.get('sequence')) is not int or row['sequence'] in result:
            fail('UI driver scene sequence is malformed or duplicated')
        manifest_path, manifest = checked_json_ref(row.get('manifest'))
        folder = absolute(row.get('folder', ''))
        if not manifest_path.is_relative_to(session_root) or folder != manifest_path.parent or \
           row.get('snapshot_state_unchanged') is not True:
            fail('UI scene manifest escaped its session or did not preserve its snapshot')
        snapshot_path, snapshot = checked_json_ref(manifest.get('snapshot'))
        if not snapshot_path.is_relative_to(session_root) or manifest.get('snapshot_state_unchanged') is not True or \
           row.get('snapshot_before_sha256') != digest(snapshot_path) or \
           manifest.get('snapshot', {}).get('sha256') != digest(snapshot_path):
            fail('Actual scene manifest does not bind the exact unchanged private snapshot')
        if row.get('context') != manifest.get('context') or \
           row.get('snapshot_before_sha256') != manifest.get('snapshot', {}).get('sha256'):
            fail('Driver scene request context/hash differs from its retained manifest')
        result[row['sequence']] = {'request': row, 'manifest_path': manifest_path,
                                   'manifest': manifest, 'snapshot_path': snapshot_path,
                                   'snapshot': snapshot, 'folder': folder}
    return result


def source_mirror(manifest: dict, variant: str) -> list[dict]:
    expected = {
        'Assets/DLC/Expansion2/UI/InGame/CityView/CityView.lua': CITY_UI_SOURCES[0],
        'Assets/DLC/Expansion2/UI/InGame/CityView/' + ('CityView_small.xml' if variant == 'small' else 'CityView.xml'):
            CITY_UI_SOURCES[2] if variant == 'small' else CITY_UI_SOURCES[1],
        'Assets/UI/SupportFunctions.lua': CITY_UI_SOURCES[3],
    }
    source_rows = manifest.get('original_context_sources')
    if not isinstance(source_rows, list):
        fail('CityView scene manifest omits original Lua/XML source provenance')
    checked = []
    for suffix, source in expected.items():
        matches = [row for row in source_rows if type(row) is dict and
                   str(row.get('path', '')).replace('\\', '/').casefold().endswith(suffix.casefold())]
        source = absolute(source)
        if len(matches) != 1 or matches[0].get('sha256') != digest(source) or \
           digest(absolute(matches[0].get('path', ''))) != digest(source):
            fail(f'CityView manifest does not prove exact original source bytes: {suffix}')
        checked.append({'source': artifact(source), 'manifest_source': matches[0], 'verified': True})
    return checked


def view_snapshot(scene: dict, owner: int, city: int) -> dict:
    manifest, snapshot = scene['manifest'], scene['snapshot']
    profile = snapshot.get('cityView')
    if (scene['request'].get('context'), manifest.get('context'), manifest.get('context_name'),
        manifest.get('popup_kind')) != ('city-view', 'city-view', 'CityView', 'CityView'):
        fail('Scene is not the original CityView context')
    if (snapshot.get('contextName'), snapshot.get('popupKind'), snapshot.get('active'),
        snapshot.get('timerSemaphore'), snapshot.get('lifecycle')) != ('CityView', 'CityView', True, 0, ['queued']):
        fail('CityView snapshot lacks the original queued, active, released-timer lifecycle')
    if type(profile) is not dict or (profile.get('owner'), profile.get('city'), profile.get('viewingMode')) != (owner, city, False):
        fail('CityView is not the exact selected owner/city in editable mode')
    variant = profile.get('layoutVariant')
    small = profile.get('smallUIAssets')
    if type(small) is not bool or variant != ('small' if small else 'default'):
        fail('CityView snapshot has an inconsistent original SmallUIAssets layout selection')
    sources = source_mirror(manifest, variant)
    return {'owner': owner, 'city': city, 'layout_variant': variant, 'small_ui_assets': small,
            'original_source_provenance': sources, 'snapshot': artifact(scene['snapshot_path']),
            'manifest': artifact(scene['manifest_path'])}


def frame_for_target(frames: list[dict], scenes: dict[int, dict], generation: int,
                     owner: int, city: int) -> tuple[dict, dict, dict]:
    candidates = [row for row in frames if row['generation'] == generation and row['context'] == 'city-view']
    if len(candidates) != 1:
        fail(f'No unique CityView UI frame maps HWND generation {generation}')
    frame = candidates[0]
    scene = scenes.get(frame['sequence'])
    if scene is None or scene['folder'] != frame['folder'] or scene['snapshot_path'] != frame['snapshot']:
        fail('UI frame sequence does not map to its exact driver scene request')
    view = view_snapshot(scene, owner, city)
    return frame, scene, view


def target_click(name: str, target_marker: tuple[str, ...], text: str,
                 posted_rows: list[tuple[str, ...]], native_rows: list[tuple[str, ...]],
                 frames: list[dict], scenes: dict[int, dict], owner: int, city: int) -> dict:
    if name == 'focus':
        target_city, value, key_text, generation_text = target_marker
        focus_value_to_id = {0: 'FoodFocusButton', 1: 'ProductionFocusButton'}
        if int(value) not in focus_value_to_id:
            fail(f'Focus callback carries an unsupported source enum value: {value}')
        expected_ids = {focus_value_to_id[int(value)]}
        expected_operation_value = int(value)
    elif name == 'AvoidGrowthButton':
        target_city, value, key_text, generation_text = target_marker
        expected_ids, expected_operation_value = {name}, int(value)
    else:
        target_city, key_text, generation_text = target_marker
        expected_ids, expected_operation_value = {name}, None
    if int(target_city) != city:
        fail(f'{name} target belongs to a different SDK city')
    key, generation = int(key_text), int(generation_text)
    posted = [row for row in posted_rows if int(row[0]) == generation and int(row[1]) == key]
    consumed = [row for row in native_rows if int(row[0]) == generation and int(row[2]) == key]
    if len(posted) != 1 or len(consumed) != 1 or consumed[0][1] != '1' or consumed[0][3] != '1':
        fail(f'{name} target does not map to exactly one posted and consumed native ControlClick')
    frame, scene, view = frame_for_target(frames, scenes, generation, owner, city)
    manifest = scene['manifest']
    targets = [row for row in manifest.get('retained_input_targets', []) if type(row) is dict and
               row.get('key') == key and row.get('event') == 'LeftClick']
    if len(targets) != 1:
        fail(f'{name} click key is not a unique original retained LeftClick target')
    row = targets[0]
    bounds, clipped = row.get('bounds'), row.get('clippedBounds')
    if row.get('id') not in expected_ids or row.get('visible') is not True or row.get('disabled') is not False or \
       type(bounds) is not dict or bounds != clipped or \
       any(type(bounds.get(axis)) not in (int, float) for axis in ('x', 'y', 'width', 'height')) or \
       bounds['width'] <= 0 or bounds['height'] <= 0 or bounds['x'] < 0 or bounds['y'] < 0 or \
       bounds['x'] + bounds['width'] > 1920 or bounds['y'] + bounds['height'] > 1080:
        fail(f'{name} target ID/bounds are not visible, enabled, unique, and unclipped')
    if name == 'focus' and row.get('void1') != expected_operation_value:
        fail('Retained focus control ID does not carry its exact original CityAIFocusTypes void1 value')
    if expected_operation_value is not None and name == 'focus':
        operation_rows = [r for r in exact_rows(text, 'INTERACTIVE_CITY_SETTING_APPLIED',
            r'^INTERACTIVE_CITY_SETTING_APPLIED=(\d+)\|(\d+)\|(\d+)\|(-?\d+)$')
            if int(r[0]) == owner and int(r[1]) == city and int(r[2]) == 1 and int(r[3]) == expected_operation_value]
    else:
        operation_rows = []
    return {'id': row['id'], 'key': key, 'generation': generation,
            'scene_sequence': frame['sequence'], 'bounds': bounds, 'clipped_bounds': clipped,
            'visible': row['visible'], 'enabled': not row['disabled'],
            'posted_input': list(posted[0]), 'native_input': list(consumed[0]),
            'city_view': view, 'sdk_focus_operation': operation_rows}


def png_dimensions(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    if len(data) < 24 or data[:8] != b'\x89PNG\r\n\x1a\n' or data[12:16] != b'IHDR':
        fail(f'City backdrop is not a PNG: {path.name}')
    width, height = struct.unpack_from('>II', data, 16)
    if not (0 < width <= 8192 and 0 < height <= 8192):
        fail('City backdrop dimensions are outside the retained renderer limit')
    return width, height


def scene_and_input_proof(text: str, result: dict, runtime: Path,
                          owner: int, city: int) -> dict:
    generated = generated_inventory(result, runtime)
    driver_path, driver = checked_json_ref(result.get('interactive_ui_driver'))
    scenes = scenes_by_sequence(driver, runtime)
    frames = ui_frames(text)
    if not frames:
        fail('Run has no UI frame records mapping scene revisions to HWND generations')
    posted_rows = exact_rows(text, 'INTERACTIVE_SMOKE_POSTED',
                             r'^INTERACTIVE_SMOKE_POSTED=(\d+)\|(\d+)\|(-?\d+)\|(-?\d+)$')
    native_rows = exact_rows(text, 'INTERACTIVE_UI_NATIVE_INPUT',
                             r'^INTERACTIVE_UI_NATIVE_INPUT=(\d+)\|(\d+)\|(\d+)\|([01])$')
    if not posted_rows or not native_rows:
        fail('Host output does not include actual posted HWND and native UI input records')
    target_values = {}
    for name, pattern in TARGET_MARKERS.items():
        target_values[name] = one_marker(text, TARGET_MARKER_NAMES[name], pattern)
    # Target marker names are deliberately distinct from control IDs.
    clicks = {
        'WorkerHeader': target_click('WorkerHeader', target_values['WorkerHeader'], text, posted_rows,
            native_rows, frames, scenes, owner, city),
        'Focus': target_click('focus', target_values['focus'], text, posted_rows,
            native_rows, frames, scenes, owner, city),
        'AvoidGrowthButton': target_click('AvoidGrowthButton', target_values['AvoidGrowthButton'], text, posted_rows,
            native_rows, frames, scenes, owner, city),
        'ProductionButton': target_click('ProductionButton', target_values['ProductionButton'], text, posted_rows,
            native_rows, frames, scenes, owner, city),
        'ReturnToMapButton': target_click('ReturnToMapButton', target_values['ReturnToMapButton'], text, posted_rows,
            native_rows, frames, scenes, owner, city),
    }
    if len({row['generation'] for row in clicks.values()}) != 5:
        fail('City management clicks do not each bind to a distinct current HWND generation')
    if len({row['key'] for row in clicks.values()}) != 5:
        fail('City management controls do not have distinct retained input keys')

    backdrop_rows = exact_rows(text, 'INTERACTIVE_CITY_BACKDROP',
                               r'^INTERACTIVE_CITY_BACKDROP=(\d+)\|([^|]+)$')
    backdrop_proofs = []
    for revision_text, png_text in backdrop_rows:
        revision = int(revision_text)
        request = scenes.get(revision)
        if request is None or request['request'].get('context') != 'city-view':
            fail('City backdrop marker has no corresponding retained CityView scene request')
        png = absolute(png_text)
        if png not in generated.get(png.name, []) or not png.is_relative_to(absolute(runtime / 'sessions')):
            fail('City backdrop PNG is absent from the exact runtime generated-file inventory')
        backdrop_proofs.append({'sequence': revision, 'png': artifact(png),
                                'dimensions': list(png_dimensions(png)),
                                'scene_manifest': artifact(request['manifest_path']),
                                'snapshot': artifact(request['snapshot_path'])})
    if not backdrop_proofs:
        fail('Actual owned CityView run did not compose a city backdrop')
    return {'clicks': clicks, 'scene_requests': [
                {'sequence': seq, 'context': row['request']['context'],
                 'manifest': artifact(row['manifest_path']), 'snapshot': artifact(row['snapshot_path'])}
                for seq, row in sorted(scenes.items())],
            'city_backdrops': backdrop_proofs, 'city_backdrop_composed': True,
            'actual_ui_driver': artifact(driver_path)}


def management_proof(text: str, result: dict, runtime: Path, owner: int, city: int) -> dict | None:
    if result.get('city_management_required') is not True:
        return None
    if result.get('city_management_verified') is not True:
        fail('Original CityView management scenario did not complete')
    verified = one_marker(text, 'INTERACTIVE_CITY_MANAGEMENT_VERIFIED',
        r'^INTERACTIVE_CITY_MANAGEMENT_VERIFIED=(\d+)\|(\d+)\|(\d+)\|(\d+)\|(\d+)\|(\d+)\|(\d+)$')
    fixture = one_marker(text, 'INTERACTIVE_CITY_UI_FIXTURE',
        r'^INTERACTIVE_CITY_UI_FIXTURE=(\d+)\|(-?\d+)\|(-?\d+)\|(\d+)\|(\d+)\|(\d+)\|(\d+)\|(\d+)$')
    if int(verified[0]) != city or int(fixture[0]) != city or int(verified[1]) != int(fixture[5]) or \
       result.get('city_management') != [list(verified)] or result.get('city_management_fixture') != [list(fixture)]:
        fail('Management result differs from its actual SDK scenario and fixture')
    expected = {'automation': 'NoAutoSpecialistCheckbox',
                'specialist-first': r'Building(?:Empty|Filled)SpecialistSlot[123]',
                'specialist-return': r'Building(?:Empty|Filled)SpecialistSlot[123]',
                'force-plot': 'PlotButtonImage', 'reset-plots': 'ResetButton',
                'buy-mode': 'BuyPlotButton', 'buy-plot': 'BuyPlotAnchoredButton'}
    rows = exact_rows(text, 'INTERACTIVE_CITY_MANAGEMENT_TARGET',
        r'^INTERACTIVE_CITY_MANAGEMENT_TARGET=([^|]+)\|(\d+)\|(-?\d+)\|(\d+)\|(\d+)$')
    if [row[0] for row in rows] != list(expected):
        fail('Original management callbacks did not follow the exact scenario order')
    _, driver = checked_json_ref(result['interactive_ui_driver'])
    scenes, frames = scenes_by_sequence(driver, runtime), ui_frames(text)
    posted = exact_rows(text, 'INTERACTIVE_SMOKE_POSTED',
        r'^INTERACTIVE_SMOKE_POSTED=(\d+)\|(\d+)\|(-?\d+)\|(-?\d+)$')
    native = exact_rows(text, 'INTERACTIVE_UI_NATIVE_INPUT',
        r'^INTERACTIVE_UI_NATIVE_INPUT=(\d+)\|(\d+)\|(\d+)\|([01])$')
    clicks = []
    for name, city_text, value_text, key_text, generation_text in rows:
        key, generation, value = int(key_text), int(generation_text), int(value_text)
        if int(city_text) != city:
            fail('Management target belongs to a different city')
        frame, scene, view = frame_for_target(frames, scenes, generation, owner, city)
        targets = [target for target in scene['manifest'].get('retained_input_targets', [])
                   if target.get('key') == key and target.get('event') == 'LeftClick']
        posted_clicks = [r for r in posted if int(r[0]) == generation and int(r[1]) == key]
        native_clicks = [r for r in native if int(r[0]) == generation and int(r[2]) == key]
        if len(targets) != 1 or len(posted_clicks) != 1 or len(native_clicks) != 1 or \
           native_clicks[0][1] != '1' or native_clicks[0][3] != '1':
            fail('Management callback lacks an exact posted and consumed original target')
        target = targets[0]
        if not re.fullmatch(expected[name], target.get('id', '')) or target.get('visible') is not True or \
           target.get('disabled') is not False or target.get('bounds') != target.get('clippedBounds'):
            fail('Management callback target is changed, hidden, disabled, or clipped')
        if name in ('force-plot', 'buy-plot') and target.get('void1') != value:
            fail('Management plot index differs from its actual original callback payload')
        if name.startswith('specialist-') and (target.get('void1') != int(verified[1]) or
            target.get('void2') not in (1, 2, 3) or
            ('Empty' in target['id']) != (value == 1) or value not in (-1, 1)):
            fail('Specialist target differs from its actual building, slot, or add/remove direction')
        clicks.append({'step': name, 'value': value, 'key': key, 'generation': generation,
                       'original_target': target, 'posted': list(posted_clicks[0]),
                       'native_input': list(native_clicks[0]), 'city_view': view})
    commands = exact_rows(text, 'INTERACTIVE_CITY_COMMAND_DELIVERED',
        r'^INTERACTIVE_CITY_COMMAND_DELIVERED=(\d+)\|(\d+)\|(\d+)\|(-?\d+)\|(-?\d+)\|(-?\d+)\|([01])\|([01])\|([01])\|([01])$')
    if len(commands) not in (6, 7) or any(int(row[0]) != owner or int(row[1]) != city for row in commands) or \
       len([row for row in commands if row[2] == '2']) != 1:
        fail('Management receiver delivery is duplicate, missing, or targets a different owner/city')
    audio_request_rows = exact_rows(text, 'UI_AUDIO_REQUEST', r'^UI_AUDIO_REQUEST=([^|]+)\|([^|]+)\|(\d+)$')
    audio_status_rows = exact_rows(text, 'UI_AUDIO_STATUS', r'^UI_AUDIO_STATUS=([^|]+)\|([^|]+)\|(\d+)$')
    # The audio service now reports every cue. Keep the historical tile proof
    # explicitly tile-only; gold purchase pairs are checked independently below.
    audio_request_matches = [row for row in audio_request_rows if row[0] == 'AS2D_INTERFACE_BUY_TILE']
    audio_status_matches = [row for row in audio_status_rows if row[0] == 'AS2D_INTERFACE_BUY_TILE']
    if len(audio_request_matches) != 1 or len(audio_status_matches) != 1:
        fail('Original tile-purchase cue is absent or duplicated among audio service events')
    audio_request, audio_completed = audio_request_matches[0], audio_status_matches[0]
    if audio_request != ('AS2D_INTERFACE_BUY_TILE', 'Started', '0') or \
       audio_completed != ('AS2D_INTERFACE_BUY_TILE', 'Completed', '0') or \
       result.get('city_audio_requests') != [list(audio_request)] or \
       result.get('city_audio_status') != [list(audio_completed)] or \
       result.get('city_audio_wave_out_completed') is not True:
        fail('Original tile-purchase cue lacks a successful waveOut submission and completion')
    return {'scenario': list(verified), 'fixture': list(fixture), 'original_clicks': clicks,
            'receiver_deliveries': [list(row) for row in commands],
            'tile_purchase_audio': {'request': list(audio_request), 'completed': list(audio_completed),
                                    'human_audibility_verified': False, 'retail_mixer_equivalence_verified': False},
            'sdk_getter_assertions_completed': True, 'fixture_is_not_normal_city_development': True,
            'building_sales_queue_edits_and_item_purchases_verified': False}


def purchase_proof(text: str, result: dict, named: dict[str, list[Path]], runtime: Path,
                   scenes: dict[int, dict], frames: list[dict], owner: int, city: int,
                   yield_values: dict[str, int]) -> dict:
    if result.get('city_purchase_required') is not True or result.get('city_purchase_verified') is not True:
        fail('Runner does not report the required successful owned-city purchase sequence')
    opens = exact_rows(text, 'INTERACTIVE_CITY_PURCHASE_OPEN',
        r'^INTERACTIVE_CITY_PURCHASE_OPEN=(\d+)\|(\d+)\|(\d+)\|(\d+)$')
    targets = exact_rows(text, 'INTERACTIVE_CITY_PURCHASE_TARGET',
        r'^INTERACTIVE_CITY_PURCHASE_TARGET=(\d+)\|(\d+)\|(\d+)\|(\d+)\|(\d+)\|(\d+)\|(\d+)\|(\d+)\|(\d+)$')
    delivered = exact_rows(text, 'INTERACTIVE_CITY_PURCHASE_DELIVERED',
        r'^INTERACTIVE_CITY_PURCHASE_DELIVERED=(\d+)\|(\d+)\|(-?\d+)\|(-?\d+)\|(-?\d+)\|(-?\d+)\|(\d+)$')
    verified = exact_rows(text, 'INTERACTIVE_CITY_PURCHASE_VERIFIED',
        r'^INTERACTIVE_CITY_PURCHASE_VERIFIED=(\d+)\|(\d+)\|(\d+)\|(\d+)\|(\d+)\|(\d+)\|(\d+)\|(\d+)\|(\d+)\|(\d+)$')
    if len(opens) != 2 or len(targets) != 2 or len(delivered) != 2 or len(verified) != 2:
        fail('Purchase trace must contain exactly two opener, target, receiver, and SDK result rows')
    if [int(row[1]) for row in opens] != [0, 1] or [int(row[1]) for row in targets] != [0, 1] or \
       [int(row[1]) for row in verified] != [0, 1]:
        fail('Purchase item enums must be exactly ordered unit (0), then building (1)')
    tech_fixture = one_marker(text, 'INTERACTIVE_CITY_PURCHASE_TECH_FIXTURE',
        r'^INTERACTIVE_CITY_PURCHASE_TECH_FIXTURE=(\d+)\|(\d+)\|([01])\|1$')
    purchase_rows = []
    line_positions = {index: line for index, line in enumerate(text.splitlines())}
    delivery_positions = [next((i for i, line in line_positions.items()
        if line == 'INTERACTIVE_CITY_PURCHASE_DELIVERED=' + '|'.join(row)), -1) for row in delivered]
    for index, (open_row, target_row, delivery, outcome) in enumerate(zip(opens, targets, delivered, verified)):
        o, t, d, v = tuple(map(int, open_row)), tuple(map(int, target_row)), \
                      tuple(map(int, delivery)), tuple(map(int, outcome))
        if o[0] != city or o[1] != t[1] or t[0] != city or \
           (v[0], v[1], v[2], v[3], v[4], v[6], v[8]) != (city, t[1], t[2], t[3], t[4], t[5], t[6]) or \
           d[0] != owner or d[1] != city:
            fail('Purchase SDK target/result/receiver rows disagree on city, item, enum, or turn')
        if v[5] != t[4] - t[3] or v[7] != t[5] or v[9] != t[6] + 1:
            fail('Purchase did not subtract exact GOLD, preserve FAITH, and increment stock once')
        expected_item_fields = (t[2], -1, -1) if t[1] == 0 else (-1, t[2], -1)
        if d[2:5] != expected_item_fields or d[5] != yield_values['YIELD_GOLD']:
            fail('Purchase receiver did not carry the selected unit/building and GOLD yield')
        open_key, open_generation = o[2], o[3]
        target_key, target_generation = t[7], t[8]
        open_post = [r for r in exact_rows(text, 'INTERACTIVE_SMOKE_POSTED',
            r'^INTERACTIVE_SMOKE_POSTED=(\d+)\|(\d+)\|(-?\d+)\|(-?\d+)$') if int(r[1]) == open_key and int(r[0]) == open_generation]
        open_input = [r for r in exact_rows(text, 'INTERACTIVE_UI_NATIVE_INPUT',
            r'^INTERACTIVE_UI_NATIVE_INPUT=(\d+)\|(\d+)\|(\d+)\|([01])$') if int(r[0]) == open_generation and int(r[2]) == open_key and r[1:] and r[1] == '1' and r[3] == '1']
        target_post = [r for r in exact_rows(text, 'INTERACTIVE_SMOKE_POSTED',
            r'^INTERACTIVE_SMOKE_POSTED=(\d+)\|(\d+)\|(-?\d+)\|(-?\d+)$') if int(r[1]) == target_key and int(r[0]) == target_generation]
        target_input = [r for r in exact_rows(text, 'INTERACTIVE_UI_NATIVE_INPUT',
            r'^INTERACTIVE_UI_NATIVE_INPUT=(\d+)\|(\d+)\|(\d+)\|([01])$') if int(r[0]) == target_generation and int(r[2]) == target_key and r[1] == '1' and r[3] == '1']
        if any(len(rows) != 1 for rows in (open_post, open_input, target_post, target_input)):
            fail('Purchase opener or item is not tied to one posted and consumed HWND callback')
        frame_rows = [row for row in frames if row['generation'] == target_generation and row['context'] == 'production']
        if len(frame_rows) != 1:
            fail('Purchase target does not map to one live ProductionPopup frame')
        frame = frame_rows[0]
        opener_frames = [row for row in frames if row['generation'] == open_generation and row['context'] == 'city-view']
        if len(opener_frames) != 1 or opener_frames[0]['sequence'] >= frame['sequence'] or d[6] != frame['turn']:
            fail('Purchase opener/target/receiver turn are out of the required live frame order')
        opener_scene = scenes.get(opener_frames[0]['sequence'])
        if opener_scene is None:
            fail('Purchase opener frame has no retained CityView scene manifest')
        opener_targets = [r for r in opener_scene['manifest'].get('retained_input_targets', [])
            if type(r) is dict and r.get('id') == 'PurchaseButton' and r.get('key') == open_key and r.get('event') == 'LeftClick']
        if len(opener_targets) != 1 or opener_targets[0].get('visible') is not True or \
           opener_targets[0].get('disabled') is not False or \
           opener_targets[0].get('bounds') != opener_targets[0].get('clippedBounds'):
            fail('Purchase opener is not the exact visible, enabled, fully visible original CityView control')
        scene = scenes.get(frame['sequence'])
        if scene is None or scene['folder'] != frame['folder'] or scene['snapshot_path'] != frame['snapshot']:
            fail('Purchase frame does not bind to its exact retained snapshot')
        retained = [r for r in scene['manifest'].get('retained_input_targets', []) if type(r) is dict and r.get('key') == target_key and r.get('event') == 'LeftClick']
        if len(retained) != 1:
            fail('Purchase target key is absent from original retained ProductionPopup callbacks')
        control = retained[0]
        bounds = control.get('bounds')
        if control.get('visible') is not True or control.get('disabled') is not False or \
           control.get('void1') != t[1] or control.get('void2') != t[2] or \
           type(bounds) is not dict or bounds != control.get('clippedBounds') or \
           bounds.get('width', 0) <= 0 or bounds.get('height', 0) <= 0:
            fail('Purchase item is hidden, disabled, clipped, or has a mismatched live void payload')
        before_name = f'play-purchase-{t[1]}-before-state.txt'
        after_name = f'play-purchase-{t[1]}-after-state.txt'
        before_path, after_path = exactly_one(named, before_name, runtime), exactly_one(named, after_name, runtime)
        before_records, after_records = before_path.read_text(encoding='utf-8').splitlines(), after_path.read_text(encoding='utf-8').splitlines()
        player_before = [line.split('|') for line in before_records if line.startswith(f'P|{owner}|')]
        player_after = [line.split('|') for line in after_records if line.startswith(f'P|{owner}|')]
        units_before = [line.split('|') for line in before_records if line.startswith(f'U|{owner}|')]
        units_after = [line.split('|') for line in after_records if line.startswith(f'U|{owner}|')]
        unit_type_before = [row for row in units_before if len(row) > 3 and int(row[3]) == t[2]]
        unit_type_after = [row for row in units_after if len(row) > 3 and int(row[3]) == t[2]]
        if len(player_before) != 1 or len(player_after) != 1 or len(player_before[0]) < 9 or len(player_after[0]) < 9 or \
           int(player_before[0][8]) != t[4] or int(player_after[0][8]) != v[5] or not units_before or not units_after:
            fail('Purchase before/after semantic snapshots omit actual owner/item player state or purchased unit type')
        if int(tech_fixture[0]) != int(player_before[0][5]) or int(tech_fixture[1]) < 0:
            fail('Purchase-only Pottery prerequisite fixture targets a different team or invalid tech ID')
        if t[1] == 0:
            ids_before = {int(row[2]) for row in unit_type_before}
            ids_after = {int(row[2]) for row in unit_type_after}
            all_ids_before = {int(row[2]) for row in units_before}
            all_ids_after = {int(row[2]) for row in units_after}
            new_ids = all_ids_after - all_ids_before
            if len(unit_type_before) != t[6] or len(unit_type_after) != v[9] or \
               len(new_ids) != 1 or all_ids_before - all_ids_after or \
               len(all_ids_after) != len(all_ids_before) + 1 or \
               not any(int(row[2]) in new_ids and int(row[3]) == t[2] for row in units_after):
                fail('Unit purchase snapshots do not show the exact SDK unit-type count increment and one new unit ID')
        elif {(int(row[2]), int(row[3])) for row in units_before} != {(int(row[2]), int(row[3])) for row in units_after}:
            fail('Building purchase changed the actual SDK unit-ID/type records')
        purchase_rows.append({'enum': t[1], 'item': t[2], 'price': t[3], 'target': control,
            'open_generation': open_generation, 'target_generation': target_generation,
            'cityview_frame_sequence': opener_frames[0]['sequence'],
            'production_frame_sequence': frame['sequence'], 'delivery': list(delivery), 'verified': list(outcome),
            'before_state': artifact(before_path), 'after_state': artifact(after_path)})
    audio_requests = exact_rows(text, 'UI_AUDIO_REQUEST', r'^UI_AUDIO_REQUEST=([^|]+)\|([^|]+)\|(\d+)$')
    audio_statuses = exact_rows(text, 'UI_AUDIO_STATUS', r'^UI_AUDIO_STATUS=([^|]+)\|([^|]+)\|(\d+)$')
    gold_requests = [r for r in audio_requests if r[0] == 'AS2D_INTERFACE_CITY_SCREEN_PURCHASE']
    gold_statuses = [r for r in audio_statuses if r[0] == 'AS2D_INTERFACE_CITY_SCREEN_PURCHASE']
    if gold_requests != [('AS2D_INTERFACE_CITY_SCREEN_PURCHASE', 'Started', '0')]*2 or \
       gold_statuses != [('AS2D_INTERFACE_CITY_SCREEN_PURCHASE', 'Completed', '0')]*2 or \
       result.get('purchase_audio_requests') != [list(r) for r in gold_requests] or \
       result.get('purchase_audio_status') != [list(r) for r in gold_statuses]:
        fail('Two GOLD purchase audio requests lack their actual service Started/Completed records')
    lines = text.splitlines()
    request_positions = [i for i, line in enumerate(lines) if line.startswith('UI_AUDIO_REQUEST=AS2D_INTERFACE_CITY_SCREEN_PURCHASE|')]
    status_positions = [i for i, line in enumerate(lines) if line.startswith('UI_AUDIO_STATUS=AS2D_INTERFACE_CITY_SCREEN_PURCHASE|')]
    return_positions = [i for i, line in enumerate(lines) if re.fullmatch(r'INTERACTIVE_CITY_PRODUCTION_RETURNED=\d+\|\d+', line)]
    expected_return_markers = 4 if result.get('purchase_close_required') is True else 3
    if len(request_positions) != 2 or len(status_positions) != 2 or len(return_positions) != expected_return_markers or \
       any(delivery_positions[i] < 0 or not delivery_positions[i] < request_positions[i] for i in range(2)) or \
       any(status_positions[i] < request_positions[i] for i in range(2)):
        fail('Gold cue requests do not follow their delivered purchases or complete after their starts')
    after_related_return = [status_positions[i] > return_positions[i + 1] for i in range(2)]
    continuity = None
    if not all(after_related_return):
        # Completion may race with closing the purchase popup. In that case the
        # shared HostServices owner and joined playback workers must keep the
        # original cue alive through the retained CityView handoff.
        services = (PROJECT / 'Source/Host/HostServices.h').read_text(encoding='utf-8')
        playback = (PROJECT / 'Source/Host/UiAudioPlayback.h').read_text(encoding='utf-8')
        if 'std::shared_ptr<UiAudioPlayback> uiAudio;' not in services or \
           'host_.uiAudio->Request2D' not in (PROJECT / 'Source/Host/UiPopupContext.h').read_text(encoding='utf-8') or \
           'std::thread([this, raw, playback =' not in playback or 'voice->worker.join()' not in playback:
            fail('Early purchase cue completion lacks same-owner playback lifetime through popup closure')
        continuity = {'shared_owner': 'HostServices::uiAudio', 'per_voice_worker': True,
                      'owner_stop_joins_worker': True, 'verified': True}
    return {'purchases': purchase_rows, 'receiver_deliveries': [list(row) for row in delivered],
            'purchase_prerequisite_fixture': {'team': int(tech_fixture[0]),
                'tech_id': int(tech_fixture[1]), 'already_known_before_fixture': int(tech_fixture[2]),
                'granted_for_purchase_scenario_only': True,
                'normal_technology_reward_popup_verified': False},
            'gold_purchase_audio': {'requests': [list(r) for r in gold_requests],
                                    'statuses': [list(r) for r in gold_statuses],
                                    'request_positions': request_positions,
                                    'completion_positions': status_positions,
                                    'popup_return_positions': return_positions,
                                    'completed_after_popup_return': all(after_related_return),
                                    'shared_owner_continuity': continuity,
                                    'human_audibility_verified': False,
                                    'retail_mixer_equivalence_verified': False}}


def settings_proof(text: str, source_final: dict[tuple[int, int], tuple[int, int]],
                   restore_initial: dict[tuple[int, int], tuple[int, int]] | None,
                   owner: int, city: int) -> dict:
    settings = one_marker(text, 'INTERACTIVE_OWNED_CITY_SETTINGS_VERIFIED',
                          r'^INTERACTIVE_OWNED_CITY_SETTINGS_VERIFIED=(\d+)\|(-?\d+)\|([01])$')
    if int(settings[0]) != city or source_final.get((owner, city)) != (int(settings[1]), int(settings[2])):
        fail('Source final SDK focus/forced-avoid state differs from the verified CityView result')
    if restore_initial is not None and source_final != restore_initial:
        fail('Source final citizen focus/forced-avoid records differ from fresh restore initial records')
    target = (owner, city)
    if target not in source_final or (restore_initial is not None and target not in restore_initial):
        fail('Owned CityView city is absent from source-final or restore-initial citizen records')
    applied = exact_rows(text, 'INTERACTIVE_CITY_SETTING_APPLIED',
                         r'^INTERACTIVE_CITY_SETTING_APPLIED=(\d+)\|(\d+)\|(\d+)\|(-?\d+)$')
    focus_target = one_marker(text, 'INTERACTIVE_OWNED_CITY_FOCUS_TARGET',
        r'^INTERACTIVE_OWNED_CITY_FOCUS_TARGET=(\d+)\|(-?\d+)\|(\d+)\|(\d+)$')
    avoid_target = one_marker(text, 'INTERACTIVE_OWNED_CITY_GROWTH_TARGET',
        r'^INTERACTIVE_OWNED_CITY_GROWTH_TARGET=(\d+)\|([01])\|(\d+)\|(\d+)$')
    expected = {(owner, city, 1, int(focus_target[1])), (owner, city, 2, int(avoid_target[1]))}
    actual = {(int(row[0]), int(row[1]), int(row[2]), int(row[3])) for row in applied}
    if actual != expected or len(applied) != 2 or \
       (int(settings[1]), int(settings[2])) != (int(focus_target[1]), int(avoid_target[1])):
        fail('Actual SDK operation result rows do not match both posted original CityView setting controls')
    return {'city': target, 'focus': int(settings[1]), 'forced_avoid_growth': int(settings[2]),
            'focus_operation': 'ResponseSetCityAIFocus', 'avoid_operation': 'ResponseSetCityAvoidGrowth',
            'actual_sdk_operations': [list(row) for row in applied],
            'source_final_equals_restore_initial': restore_initial is not None,
            'final_citizens': {f'{p}:{c}': list(value) for (p, c), value in sorted(source_final.items())},
            'restore_initial_citizens': None if restore_initial is None else
                {f'{p}:{c}': list(value) for (p, c), value in sorted(restore_initial.items())}}


def purchase_close_proof(text: str, result: dict, scenes: dict[int, dict], frames: list[dict],
                         owner: int, city: int) -> dict:
    if result.get('purchase_close_required') is not True or result.get('purchase_close_verified') is not True:
        fail('Fresh-restore run does not report the required real-HWND nested purchase close regression')
    target = one_marker(text, 'INTERACTIVE_CITY_PURCHASE_CLOSE_TARGET',
        r'^INTERACTIVE_CITY_PURCHASE_CLOSE_TARGET=(\d+)\|(\d+)\|(\d+)\|(\d+)$')
    verified = one_marker(text, 'INTERACTIVE_CITY_PURCHASE_CLOSE_VERIFIED',
        r'^INTERACTIVE_CITY_PURCHASE_CLOSE_VERIFIED=(\d+)\|(\d+)\|0\|0\|0$')
    city_id, turn, key, generation = map(int, target)
    if (city_id, turn) != tuple(map(int, verified)) or city_id != city:
        fail('Nested purchase-close result did not verify the selected city and close turn')
    result_targets = result.get('purchase_close_targets')
    result_rows = result.get('purchase_close_results')
    if result_targets != [list(target)] or result_rows != [[str(city_id), str(turn)]]:
        fail('Runner purchase-close arrays differ from the independently parsed stdout markers')
    candidates = [row for row in frames if row['generation'] == generation and row['context'] == 'city-view']
    if len(candidates) != 1 or candidates[0]['turn'] != turn:
        fail('Purchase close target does not bind to one same-generation owned CityView frame and turn')
    scene = scenes.get(candidates[0]['sequence'])
    if scene is None or scene['folder'] != candidates[0]['folder'] or scene['snapshot_path'] != candidates[0]['snapshot']:
        fail('Purchase close CityView frame does not bind to its exact retained scene')
    view_snapshot(scene, owner, city)
    targets = [row for row in scene['manifest'].get('retained_input_targets', [])
               if type(row) is dict and row.get('id') == 'PurchaseButton' and row.get('key') == key and
               row.get('event') == 'LeftClick']
    posted = [row for row in exact_rows(text, 'INTERACTIVE_SMOKE_POSTED',
        r'^INTERACTIVE_SMOKE_POSTED=(\d+)\|(\d+)\|(-?\d+)\|(-?\d+)$')
        if int(row[0]) == generation and int(row[1]) == key]
    native = [row for row in exact_rows(text, 'INTERACTIVE_UI_NATIVE_INPUT',
        r'^INTERACTIVE_UI_NATIVE_INPUT=(\d+)\|(\d+)\|(\d+)\|([01])$')
        if int(row[0]) == generation and int(row[2]) == key and row[1] == '1' and row[3] == '1']
    if len(targets) != 1 or len(posted) != 1 or len(native) != 1:
        fail('Close regression PurchaseButton is not one exact posted and consumed original callback in its HWND generation')
    control = targets[0]
    bounds = control.get('bounds')
    if control.get('visible') is not True or control.get('disabled') is not False or \
       type(bounds) is not dict or bounds != control.get('clippedBounds') or \
       bounds.get('width', 0) <= 0 or bounds.get('height', 0) <= 0:
        fail('Close regression target is not fully visible and enabled in its original CityView scene')
    close_events = exact_rows(text, 'INTERACTIVE_PREPARE_CLOSE_RETAINED',
        r'^INTERACTIVE_PREPARE_CLOSE_RETAINED=(\d+)\|(\d+)$')
    if len(close_events) != 1 or int(close_events[0][1]) <= 0:
        fail('Nested production preparation did not retain the actual native WM_CLOSE event')
    lines = text.splitlines()
    purchase_positions = [i for i, line in enumerate(lines)
        if line.startswith('INTERACTIVE_CITY_PURCHASE_VERIFIED=')]
    target_position = lines.index('INTERACTIVE_CITY_PURCHASE_CLOSE_TARGET=' + '|'.join(target))
    verified_position = lines.index('INTERACTIVE_CITY_PURCHASE_CLOSE_VERIFIED=' + '|'.join(verified) + '|0|0|0')
    if len(purchase_positions) != 2 or target_position <= purchase_positions[-1] or verified_position <= target_position:
        fail('Native purchase-close regression did not occur after both purchases or verify after its target')
    return {'target': list(target), 'verified': list(verified), 'same_generation_posted_consumed': True,
            'retained_target': control, 'posted': list(posted[0]), 'native_input': list(native[0]),
            'prepare_close_retained': list(close_events[0]), 'ui_selection_purchase_mode_cleared': True}


def verify_production_return(text: str, named: dict[str, list[Path]], runtime: Path,
                             scenes: dict[int, dict], frames: list[dict], owner: int, city: int,
                             *, close_result: dict | None = None) -> dict:
    returned = exact_rows(text, 'INTERACTIVE_CITY_PRODUCTION_RETURNED',
                          r'^INTERACTIVE_CITY_PRODUCTION_RETURNED=(\d+)\|(\d+)$')
    expected_returns = 4 if close_result is not None else 3
    if len(returned) != expected_returns or any(tuple(map(int, row)) != (owner, city) for row in returned):
        fail('Original ProductionPopup did not return to the exact retained CityView owner/city')
    return_rows = []
    for line in text.splitlines():
        match = re.fullmatch(r'UI_POPUP_production-returned-(\d+)=(\d+),(\d+),(\d+)', line)
        if match:
            return_rows.append(tuple(match.groups()))
        elif line.startswith('UI_POPUP_production-returned-'):
            fail('Malformed ProductionPopup parent refresh marker')
    if len(return_rows) != expected_returns:
        fail(f'Expected {expected_returns} Production/purchase parent refresh markers; observed {len(return_rows)}')
    snapshots = [path for paths in named.values() for path in paths
                 if re.fullmatch(r'ui-popup-\d+-production-returned-\d+\.json', path.name)]
    if len(snapshots) != expected_returns:
        fail(f'Production/purchase/close flow did not preserve {expected_returns} exact parent CityView refresh snapshots')
    refreshes = []
    used_snapshots = set()
    for rev_marker in return_rows:
        # Reopening CityView creates a new VM whose revision starts over.
        # Bind each chronological marker to its exact file, never revision sort.
        name = f'ui-popup-{rev_marker[1]}-production-returned-{rev_marker[0]}.json'
        snapshot_path = exactly_one(named, name, runtime)
        if snapshot_path not in snapshots or snapshot_path in used_snapshots:
            fail('Production return marker reused or omitted its exact parent snapshot')
        used_snapshots.add(snapshot_path)
        snapshot = read_json(snapshot_path)
        match = re.fullmatch(r'ui-popup-(\d+)-production-returned-(\d+)\.json', snapshot_path.name)
        if match is None or int(match.group(1)) != int(rev_marker[1]) or \
           int(match.group(2)) != int(rev_marker[0]) or int(rev_marker[3]) != snapshot_path.stat().st_size or \
           snapshot_path not in named.get(snapshot_path.name, []):
            fail('Production return marker does not identify its exact saved parent snapshot')
        profile = snapshot.get('cityView')
        if (snapshot.get('contextName'), snapshot.get('popupKind'), snapshot.get('active'),
            snapshot.get('timerSemaphore'), snapshot.get('lifecycle')) != ('CityView', 'CityView', True, 0, ['queued']) or \
           type(profile) is not dict or (profile.get('owner'), profile.get('city'), profile.get('viewingMode')) != (owner, city, False):
            fail('Production/purchase return parent snapshot changed its editable owner/city or lifecycle')
        refreshes.append({'marker': list(rev_marker), 'snapshot': artifact(snapshot_path), 'scene': snapshot})
    if close_result is not None:
        lines = text.splitlines()
        close_target_position = next((i for i, line in enumerate(lines)
            if line.startswith('INTERACTIVE_CITY_PURCHASE_CLOSE_TARGET=')), -1)
        final_return = return_rows[-1]
        final_return_line = f"UI_POPUP_production-returned-{final_return[0]}={','.join(final_return[1:])}"
        if close_target_position < 0 or final_return_line not in lines or lines.index(final_return_line) <= close_target_position:
            fail('Fourth same-city parent refresh was not produced by the final close/cancel regression')
    return_target = one_marker(text, TARGET_MARKER_NAMES['ReturnToMapButton'], TARGET_MARKERS['ReturnToMapButton'])
    generation = int(return_target[2])
    candidates = [row for row in frames if row['generation'] == generation and row['context'] == 'city-view']
    if len(candidates) != 1 or candidates[0]['sequence'] not in scenes:
        fail('Production return did not publish a refreshed CityView scene for its retained HWND generation')
    refreshed = scenes[candidates[0]['sequence']]
    refreshed_view = view_snapshot(refreshed, owner, city)
    production_marker = one_marker(text, TARGET_MARKER_NAMES['ProductionButton'], TARGET_MARKERS['ProductionButton'])
    prod_city, _prod_key, prod_generation = map(int, production_marker)
    if prod_city != city:
        fail('Nested ProductionPopup was not opened by the original selected CityView production control')
    production_order = one_marker(text, 'INTERACTIVE_DECISION_PRODUCTION_TARGET',
                                  r'^INTERACTIVE_DECISION_PRODUCTION_TARGET=(\d+)\|(\d+)\|(\d+)$')
    selected_city, unit, popup_key = map(int, production_order)
    if selected_city != city:
        fail('Nested production item belongs to a different selected SDK city')
    posts = exact_rows(text, 'INTERACTIVE_SMOKE_POSTED',
                       r'^INTERACTIVE_SMOKE_POSTED=(\d+)\|(\d+)\|(-?\d+)\|(-?\d+)$')
    inputs = exact_rows(text, 'INTERACTIVE_UI_NATIVE_INPUT',
                        r'^INTERACTIVE_UI_NATIVE_INPUT=(\d+)\|(\d+)\|(\d+)\|([01])$')
    prod_cityview_frames = [row for row in frames if row['generation'] == prod_generation and
                            row['context'] == 'city-view']
    purchase_opens = exact_rows(text, 'INTERACTIVE_CITY_PURCHASE_OPEN',
        r'^INTERACTIVE_CITY_PURCHASE_OPEN=(\d+)\|(\d+)\|(\d+)\|(\d+)$')
    first_purchase_opener_frames = [row for row in frames if len(purchase_opens) == 2 and
        row['generation'] == int(purchase_opens[0][3]) and row['context'] == 'city-view']
    if len(prod_cityview_frames) != 1 or len(first_purchase_opener_frames) != 1:
        fail('Original ProductionButton and first purchase opener do not each bind to one CityView frame')
    prod_cityview_frame = prod_cityview_frames[0]
    first_purchase_frame = first_purchase_opener_frames[0]
    popup_frames = [row for row in frames if row['context'] == 'production' and
                    prod_cityview_frame['sequence'] < row['sequence'] < first_purchase_frame['sequence']]
    if len(popup_frames) != 1:
        fail('Original ProductionPopup is not uniquely ordered between its CityView opener and first purchase opener')
    popup_frame = popup_frames[0]
    popup_generation = popup_frame['generation']
    popup_posts = [row for row in posts if int(row[0]) == popup_generation and int(row[1]) == popup_key]
    popup_inputs = [row for row in inputs if int(row[0]) == popup_generation and int(row[2]) == popup_key and
                    row[1] == '1' and row[3] == '1']
    if len(popup_posts) != 1 or len(popup_inputs) != 1:
        fail('Nested ProductionPopup item does not map to one posted and consumed callback in its exact HWND generation')
    popup_scene = scenes.get(popup_frame['sequence'])
    if popup_scene is None or popup_scene['folder'] != popup_frame['folder'] or \
       popup_scene['snapshot_path'] != popup_frame['snapshot'] or popup_scene['request'].get('context') != 'production':
        fail('Production item UI frame does not bind to its exact nested popup scene request')
    production_targets = [row for row in popup_scene['manifest'].get('retained_input_targets', [])
                          if type(row) is dict and row.get('key') == popup_key and row.get('event') == 'LeftClick']
    if len(production_targets) != 1:
        fail('Nested production selection is not a unique original retained callback target')
    target = production_targets[0]
    bounds = target.get('bounds')
    if target.get('visible') is not True or target.get('disabled') is not False or \
       target.get('void1') != 6 or target.get('void2') != unit or type(bounds) is not dict or \
       bounds != target.get('clippedBounds') or bounds.get('width', 0) <= 0 or bounds.get('height', 0) <= 0:
        fail('Nested production target lacks its visible, enabled original ORDER_TRAIN payload and bounds')
    return_frame = candidates[0]
    if not (prod_cityview_frame['sequence'] < popup_frame['sequence'] < return_frame['sequence']):
        fail('CityView production opener, nested ProductionPopup selection, and refreshed return are out of order')
    close_proof = None if close_result is None else purchase_close_proof(
        text, close_result, scenes, frames, owner, city)
    return {'owner': owner, 'city': city, 'parent_snapshots': [row['snapshot'] for row in refreshes],
            'refresh_markers': [row['marker'] for row in refreshes], 'production_return_marker': list(returned),
            'post_refresh_cityview_sequence': candidates[0]['sequence'],
            'production_selection': {'city': city, 'unit': unit, 'target_id': target.get('id'),
                'key': popup_key, 'generation': popup_frame['generation'], 'void1': target['void1'],
                'void2': target['void2'], 'bounds': bounds, 'visible': target['visible'],
                'enabled': not target['disabled'], 'posted': list(popup_posts[0]),
                'native_input': list(popup_inputs[0]), 'popup_scene': artifact(popup_scene['manifest_path'])},
            'refreshed_city_view': refreshed_view, 'purchase_close': close_proof,
            'same_editable_parent_owner_city': True,
            'refresh_published': True}


def _frozen_source(source: Path, frozen: list[dict]) -> dict:
    source = absolute(source)
    live_hash = digest(source)
    matches = [row for row in frozen if absolute(row['original_path']) == source]
    if len(matches) != 1 or matches[0]['sha256'] != live_hash:
        fail(f'Current source is not independently frozen byte-for-byte: {source}')
    return {'live': artifact(source), 'frozen': matches[0]}


def verify_focus_source_contract() -> dict:
    city_lua = CITY_UI_SOURCES[0]
    lua = city_lua.read_text(encoding='utf-8', errors='strict')
    enum_header = RETAINED_HOST_SOURCES[-1]
    enums = enum_header.read_text(encoding='utf-8', errors='strict')
    enum_match = re.search(r'enum\s+CityAIFocusTypes\s*\{([^}]+)\}', enums, re.S)
    if enum_match is None:
        fail('SDK enum header has no CityAIFocusTypes definition')
    fields = []
    for raw in enum_match.group(1).split(','):
        token = re.sub(r'//[^\n]*|/\*.*?\*/', '', raw, flags=re.S).strip()
        match = re.fullmatch(r'(NO_CITY_AI_FOCUS_TYPE|CITY_AI_FOCUS_TYPE_FOOD|CITY_AI_FOCUS_TYPE_PRODUCTION)\s*(?:=\s*(-?\d+))?', token)
        if match is not None:
            fields.append((match.group(1), int(match.group(2)) if match.group(2) else None))
    values: dict[str, int] = {}
    current = -1
    for name, explicit in fields:
        current = explicit if explicit is not None else current + 1
        values[name] = current
    expected = {'NO_CITY_AI_FOCUS_TYPE': -1, 'CITY_AI_FOCUS_TYPE_FOOD': 0,
                'CITY_AI_FOCUS_TYPE_PRODUCTION': 1}
    if values != expected:
        fail(f'Compiled SDK CityAIFocusTypes numeric contract changed: {values}')
    controls = {'FoodFocusButton': ('CITY_AI_FOCUS_TYPE_FOOD', 0),
                'ProductionFocusButton': ('CITY_AI_FOCUS_TYPE_PRODUCTION', 1)}
    for control, (symbol, value) in controls.items():
        if not re.search(rf'Controls\.{control}:SetVoid1\(\s*CityAIFocusTypes\.{symbol}\s*\)', lua) or \
           not re.search(rf'Controls\.{control}:RegisterCallback\(\s*Mouse\.eLClick\s*,\s*FocusChanged\s*\)', lua):
            fail(f'Original CityView.lua does not bind {control} to its SDK focus value/callback')
        if values[symbol] != value:
            fail(f'Original {control} binding does not match its numeric SDK focus enum')
    return {'cityview_lua': artifact(city_lua), 'sdk_enum_header': artifact(enum_header),
            'enum_values': values, 'control_bindings': {name: {'void1_enum': symbol, 'numeric_value': value}
                for name, (symbol, value) in controls.items()}, 'verified': True}


def cpp_literal(data: bytes) -> bytes:
    return '\n'.join('"' + ''.join('\\x%02x' % byte for byte in data[i:i + 64]) + '"'
                     for i in range(0, len(data), 64)).encode('ascii') or b'""'


def verify_host_policy_sources(request: dict, frozen: list[dict]) -> dict:
    provenance = request.get('provenance')
    if type(provenance) is not dict or type(provenance.get('host_build')) is not dict:
        fail('Request omits the sealed Host build report')
    build_path = checked_path(provenance['host_build'])
    build = read_json(build_path)
    if build.get('status') != 'UI_WINDOW_HOST_CANDIDATE_BUILT':
        fail('Run did not use a completed sealed UI Host build')
    sources = {Path(row.get('path', '')).name: row for row in build.get('sources', []) if type(row) is dict}
    if not set(HOST_POLICY_SOURCES) <= sources.keys():
        fail('Sealed Host build omits owned-city input/settings source files')
    checked = {}
    for name in HOST_POLICY_SOURCES:
        row = sources[name]
        path = checked_path(row)
        text = path.read_text(encoding='utf-8', errors='strict')
        expected_source = PROJECT / 'Source/Host' / name
        if absolute(row.get('original_source', '')) != absolute(expected_source) or \
           digest(path) != digest(expected_source):
            fail(f'Sealed Host source input differs from its current source: {name}')
        frozen_input = _frozen_source(expected_source, frozen)
        tokens = {
            'InteractiveGameLoop.h': ('INTERACTIVE_OWNED_CITY_HEADER_TARGET=', 'INTERACTIVE_OWNED_CITY_FOCUS_TARGET=',
                'INTERACTIVE_OWNED_CITY_GROWTH_TARGET=', 'INTERACTIVE_OWNED_CITY_PRODUCTION_TARGET=',
                'INTERACTIVE_OWNED_CITY_RETURN_TARGET=', 'INTERACTIVE_OWNED_CITY_SEQUENCE_VERIFIED=',
                'purchaseSelections[]={0,1}', 'INTERACTIVE_CITY_PURCHASE_TARGET=',
                'INTERACTIVE_CITY_PURCHASE_CLOSE_TARGET=', 'INTERACTIVE_CITY_PURCHASE_CLOSE_VERIFIED=',
                'PostMessageW(window.NativeHandle(),WM_CLOSE,0,0)', 'purchaseCloseSmoke=true',
                'L"\\\\play-purchase-"+std::to_wstring(selection)+L"-before-state.txt"',
                'L"\\\\play-purchase-"+std::to_wstring(selection)+L"-after-state.txt"'),
            'InteractiveGameSession.h': ('INTERACTIVE_CITY_CITIZENS_STATE=', 'int CityFocus(int city)',
                'bool CityAvoidGrowth(int city)', 'PurchaseObservation ObservePurchase',
                'c:GetNumBuilding(id)', 'u:GetUnitType()', 'void PrepareCityPurchaseSmoke(int city)',
                'TECH_POTTERY', 'SetHasTech', 'INTERACTIVE_CITY_PURCHASE_TECH_FIXTURE='),
            'UiPopupContext.h': ('ResponseSetCityAIFocus', 'ResponseSetCityAvoidGrowth',
                'INTERACTIVE_CITY_SETTING_APPLIED=', 'ReturnFromCityProduction', 'RefreshCityView',
                'host_.uiAudio->Request2D', 'INTERACTIVE_CITY_PURCHASE_DELIVERED='),
            'UiAudioPlayback.h': ('Request2D', 'AS2D_INTERFACE_BUY_TILE', 'AS2D_INTERFACE_CITY_SCREEN_PURCHASE',
                                  'AS2D_INTERFACE_FAITH_PURCHASE', 'WHDR_DONE', 'waveOutOpen', 'waveOutSetVolume',
                                  'waveOutUnprepareHeader', 'waveOutClose', 'voice->worker.join()'),
            'HostServices.h': ('std::shared_ptr<UiAudioPlayback> uiAudio;',),
        }[name]
        if any(token not in text for token in tokens):
            fail(f'Sealed Host source lacks the owned-city contract: {name}')
        checked[name] = {'artifact': row, 'tokens': list(tokens), 'current_and_frozen_source': frozen_input, 'verified': True}

    # The C++ translation unit must compile the very header generated from the
    # current retained Lua, not merely rely on a present source marker.
    input_lua, city_lua = RETAINED_HOST_SOURCES[1], RETAINED_HOST_SOURCES[2]
    ui_scene = RETAINED_HOST_SOURCES[0]
    if 'Events.SerialEventExitCityScreen.CallImmediate()' not in ui_scene.read_text(encoding='utf-8'):
        fail('Compiled retained CityView close path does not issue the original full city-screen exit callback')
    generated_header = RETAINED_HOST_SOURCES[3]
    source_closure = {str(path): _frozen_source(path, frozen)
                      for path in (*RETAINED_HOST_SOURCES, CITY_UI_SOURCES[0])}
    build_tools = {Path(row.get('original_path', '')).name: row
                   for row in build.get('build_tools', []) if type(row) is dict}
    builder_row = build_tools.get('build_ui_window_host.py')
    if not isinstance(builder_row, dict) or absolute(builder_row.get('original_path', '')) != absolute(PROJECT / 'tools/build_ui_window_host.py') or \
       digest(checked_path(builder_row)) != digest(PROJECT / 'tools/build_ui_window_host.py'):
        fail('Sealed build report does not bind the current Host builder source')
    prepared_path, prepared = checked_json_ref(build.get('ui_assets'))
    if prepared.get('status') != 'INSTALLED_UI_POPUP_ASSETS_PREPARED_NOT_RUNTIME_VERIFIED':
        fail('Host build does not reference a completed retained-UI preparation report')
    prepared_contract = {
        'builder': PROJECT / 'tools/prepare_ui_popup_assets.py',
        'host_ui_runtime': ui_scene,
        'host_ui_input_addendum': input_lua,
        'host_ui_city_view_addendum': city_lua,
        'compiled_assets': generated_header,
    }
    prepared_rows = {}
    for field, current in prepared_contract.items():
        ref = prepared.get(field)
        path = checked_path(ref, current)
        if digest(path) != digest(current):
            fail(f'UI preparation report source differs from its exact current bytes: {field}')
        prepared_rows[field] = {'artifact': ref, 'current_and_frozen_source': _frozen_source(current, frozen)}
    compiler_headers = [row for row in build.get('compiler_inputs', []) if type(row) is dict and
                        str(row.get('relative_path', '')).replace('\\', '/').casefold() ==
                        'source/host/uipopupassets.generated.h']
    if len(compiler_headers) != 1:
        fail('Host compiler dependency report does not identify one frozen UiPopupAssets.generated.h')
    compiler_header = checked_path(compiler_headers[0])
    if absolute(compiler_headers[0].get('original_path', '')) != absolute(generated_header) or \
       digest(compiler_header) != digest(generated_header) or \
       compiler_headers[0].get('sha256') != digest(generated_header):
        fail('Compiled generated-header input is stale or differs from the current generated UI asset')
    combined = (ui_scene.read_bytes() + b'\n' + input_lua.read_bytes() +
                b'\nif hasRetainedCityUi then\n' + city_lua.read_bytes() + b'\nend\n')
    expected_chunk = b'static const char ZeroSisUiScene[]=\n' + cpp_literal(combined) + b';'
    header_bytes = compiler_header.read_bytes()
    if expected_chunk not in header_bytes:
        fail('Compiled generated header does not embed the exact current UiScene/input/CityView Lua chunk')
    guard_source_rows = [row for row in build.get('sources', []) if type(row) is dict and
        Path(row.get('original_source', '')).name == PRODUCTION_GUARD_SOURCE.name]
    if len(guard_source_rows) != 1:
        fail('Frozen Host build does not identify exactly one ProductionCommandGuard.lua input')
    guard_row = guard_source_rows[0]
    guard_snapshot = checked_path(guard_row)
    guard_bytes = PRODUCTION_GUARD_SOURCE.read_bytes()
    if absolute(guard_row.get('original_source', '')) != absolute(PRODUCTION_GUARD_SOURCE) or \
       digest(guard_snapshot) != digest(PRODUCTION_GUARD_SOURCE):
        fail('Frozen Host ProductionCommandGuard.lua differs from its exact current source')
    guard_chunk = b'static const char ProductionCommandGuard[]=\n' + cpp_literal(guard_bytes) + b';'
    if guard_chunk not in header_bytes:
        fail('Compiled generated header does not embed the exact ProductionCommandGuard.lua bytes')
    frozen_guard = _frozen_source(PRODUCTION_GUARD_SOURCE, frozen)

    popup_inputs = [row for row in prepared.get('inputs', []) if type(row) is dict and row.get('name') == 'ProductionPopup']
    if len(popup_inputs) != 1:
        fail('Prepared asset catalog omits the unique original ProductionPopup.lua input')
    popup_input = popup_inputs[0]
    installed_popup = checked_path(popup_input.get('installed'), PRODUCTION_POPUP_SOURCE)
    popup_snapshot = checked_path(popup_input.get('snapshot'),
        PROJECT / 'Source/Assets/UI/Assets/DLC/Expansion2/UI/InGame/Popups/ProductionPopup.lua')
    if digest(installed_popup) != digest(popup_snapshot):
        fail('Prepared ProductionPopup.lua snapshot differs from its exact currently installed original')
    popup_bytes = popup_snapshot.read_bytes()
    popup_chunk = b'static const char ProductionPopup[]=\n' + cpp_literal(popup_bytes) + b';'
    if popup_chunk not in header_bytes:
        fail('Compiled generated header does not embed the exact prepared original ProductionPopup.lua bytes')
    frozen_popup = _frozen_source(PRODUCTION_POPUP_SOURCE, frozen)
    audio = prepared.get('buy_tile_audio')
    if not isinstance(audio, dict) or audio.get('status') != 'ORIGINAL_CIV5_BUY_TILE_SOUND_FROZEN':
        fail('Prepared UI assets omit the original tile-purchase sound provenance')
    wave_path = checked_path(audio.get('wave'), STOCK_AUDIO_SOURCES[2])
    wave_bytes = wave_path.read_bytes()
    if audio.get('fpk', {}).get('sha256') != digest_bytes(wave_bytes):
        fail('Embedded purchase sound differs from the frozen original FPK entry')
    audio_array = re.search(rb'static const unsigned char Audio2DInterfaceBuyTileWave\[\]=\{(.*?)\};',
                            header_bytes, re.S)
    if audio_array is None or bytes(int(value, 16) for value in re.findall(rb'0x([0-9a-f]{2})',
                                                        audio_array.group(1))) != wave_bytes:
        fail('Compiled UI header does not contain the exact original WAV bytes')
    audio_xml = audio.get('audio_xml')
    if not isinstance(audio_xml, list) or len(audio_xml) != 2:
        fail('Purchase sound provenance omits its original mapping XML')
    for row, expected_source in zip(audio_xml, STOCK_AUDIO_SOURCES[:2]):
        if digest(checked_path(row.get('snapshot'), expected_source)) != digest(checked_path(row.get('original'))):
            fail('Frozen purchase sound mapping differs from its original XML')
    purchase_audio = prepared.get('purchase_audio')
    expected_cues = {
        'AS2D_INTERFACE_BUY_TILE': ('SND_INTERFACE_BUY_TILE',
            'NotificationBuyTile', 60, True, 1, 'Audio2DInterfaceBuyTile'),
        'AS2D_INTERFACE_CITY_SCREEN_PURCHASE': ('SND_INTERFACE_CITY_SCREEN_PURCHASE',
            'CityScreenPurchase', 65, True, 1, 'Audio2DInterfaceCityScreenPurchase'),
        'AS2D_INTERFACE_FAITH_PURCHASE': ('SND_INTERFACE_FAITH_PURCHASE',
            'FaithPurchase', 35, False, None, 'Audio2DInterfaceFaithPurchase'),
    }
    if not isinstance(purchase_audio, list) or len(purchase_audio) != 3:
        fail('Prepared UI assets omit the three original stock tile and purchase cue records')
    compiled_purchase = {}
    for row in purchase_audio:
        if type(row) is not dict or type(row.get('script')) is not dict:
            fail('Prepared purchase cue metadata is malformed')
        script_id = row['script'].get('script_id')
        if script_id not in expected_cues or script_id in compiled_purchase:
            fail('Prepared purchase cue catalog contains an unknown or duplicate stock cue')
        sound_id, filename, volume, duplicates, limit, symbol = expected_cues[script_id]
        script, definition, policy = row['script'], row.get('definition'), row.get('duplicate_policy')
        if script.get('sound_id') != sound_id or script.get('sound_type') != 'GAME_SFX' or \
           script.get('min_volume') != volume or script.get('max_volume') != volume or \
           type(definition) is not dict or definition != {'sound_id': sound_id, 'filename': filename, 'load_type': 'DYNAMIC_RES'} or \
           type(policy) is not dict or policy.get('bDontTriggerDuplicates') is not duplicates or \
           policy.get('iDontPlayMoreThan') != limit or policy.get('limit_present_in_source') is not (limit is not None):
            fail(f'Original stock purchase cue mapping, volume, or duplicate policy changed: {script_id}')
        wave = checked_path(row.get('wave'))
        wav_bytes = wave.read_bytes()
        if row['wave'].get('sha256') != digest_bytes(wav_bytes):
            fail(f'Frozen stock purchase cue bytes differ from their prepared metadata: {script_id}')
        if script_id == 'AS2D_INTERFACE_BUY_TILE':
            tile_wave = audio.get('wave')
            tile_fpk = audio.get('fpk')
            if row.get('source') is not None or row.get('fpk', {}).get('sha256') != tile_fpk.get('sha256') or \
               row.get('fpk', {}).get('entry') != tile_fpk.get('entry') or \
               row.get('fpk', {}).get('pack_path') != tile_fpk.get('pack_path') or \
               row.get('wave') != tile_wave or script != audio.get('script') or \
               definition != audio.get('definition'):
                fail('Purchase catalog tile cue differs from the separately verified original BuyTile record')
        elif script_id == 'AS2D_INTERFACE_CITY_SCREEN_PURCHASE':
            source = row.get('fpk')
            if not isinstance(source, dict) or source.get('sha256') != digest_bytes(wav_bytes) or \
               source.get('entry') != 'cityscreenpurchase.wav' or \
               source.get('pack_path') != audio.get('fpk', {}).get('pack_path') or \
               source.get('bytes') != len(wav_bytes):
                fail('Gold purchase WAV differs from the exact original FPK entry')
        else:
            source = row.get('source')
            source_path = checked_path(source)
            if source_path.read_bytes() != wav_bytes:
                fail('Faith purchase WAV differs from the exact installed loose source')
        cue_xml = row.get('audio_xml')
        if not isinstance(cue_xml, list) or len(cue_xml) != 2:
            fail(f'Original stock purchase cue omits both mapping XML records: {script_id}')
        if script_id == 'AS2D_INTERFACE_BUY_TILE':
            tile_xml = audio.get('audio_xml')
            if not isinstance(tile_xml, list) or len(tile_xml) != 2 or any(
                cue_row.get('original') != tile_row.get('original') or
                cue_row.get('snapshot') != tile_row.get('snapshot')
                for cue_row, tile_row in zip(cue_xml, tile_xml)):
                fail('Purchase catalog tile cue XML records differ from the separately verified original BuyTile mapping')
        for xml_row in cue_xml:
            original, frozen_xml = checked_path(xml_row.get('original')), checked_path(xml_row.get('snapshot'))
            if digest(original) != digest(frozen_xml):
                fail(f'Frozen purchase cue mapping XML differs from its original source: {script_id}')
        audio_array = re.search(rb'static const unsigned char ' + symbol.encode('ascii') +
                                rb'Wave\[\]=\{(.*?)\};', header_bytes, re.S)
        if audio_array is None or bytes(int(value, 16) for value in re.findall(rb'0x([0-9a-f]{2})',
                                                    audio_array.group(1))) != wav_bytes:
            fail(f'Compiled UI header does not embed the exact original purchase WAV: {script_id}')
        compiled_purchase[script_id] = {'metadata': row, 'exact_embedded_wav_sha256': digest_bytes(wav_bytes),
                                        'verified': True}
    preparation = build.get('ui_asset_preparation')
    if type(preparation) is not dict or preparation.get('returncode') != 0 or \
       not isinstance(preparation.get('stdout'), dict) or not isinstance(preparation.get('stderr'), dict):
        fail('Host build report does not prove successful UI asset preparation command/output')
    check_artifacts(preparation)
    focus_contract = verify_focus_source_contract()
    return {'build_report': artifact(build_path), 'compiled_owned_city_sources': checked,
            'ui_asset_preparation_report': artifact(prepared_path),
            'ui_asset_preparation_command': preparation['command'],
            'preparer_builder': prepared_rows['builder'], 'generated_header_compile_input': {
                'prepared_report_artifact': prepared_rows['compiled_assets']['artifact'],
                'compiler_input': compiler_headers[0], 'embedded_runtime': 'UiScene.lua + UiPresentationInput.lua + guarded UiCityView.lua',
            'exact_embedded_chunk_sha256': digest_bytes(combined),
                'compiled_header_sha256': digest(compiler_header), 'verified': True},
            'retained_lua_and_sdk_sources': source_closure, 'focus_contract': focus_contract,
            'compiled_purchase_lua': {
                'production_command_guard': {'current_source': frozen_guard,
                    'frozen_host_source': guard_row, 'exact_compiled_script_sha256': digest_bytes(guard_bytes),
                    'verified': True},
                'installed_production_popup': {'prepared_input': popup_input,
                    'exact_installed_source': artifact(installed_popup),
                    'prepared_snapshot': artifact(popup_snapshot),
                    'exact_compiled_script_sha256': digest_bytes(popup_bytes),
                    'separately_frozen_installed_source': frozen_popup, 'verified': True}},
            'compiled_tile_purchase_audio': {'original_provenance': audio,
                'exact_embedded_wav_sha256': digest_bytes(wave_bytes),
                'frozen_sources': [_frozen_source(path, frozen) for path in STOCK_AUDIO_SOURCES]},
            'compiled_purchase_audio': compiled_purchase}


def verify(run_id: str, restore_id: str, proof: Path, frozen: list[dict],
           source_hashes: dict[str, str]) -> dict:
    if run_id == restore_id:
        fail('Source and restore must be distinct actual Host processes')
    source_root, srq, sres, satt, sout, serr = run_pair(run_id)
    restore_root, rrq, rres, ratt, rout, rerr = run_pair(restore_id)
    source_run = immutable_run(run_id, source_root, srq, sres, satt, sout, serr, restore=False)
    restore_run = immutable_run(restore_id, restore_root, rrq, rres, ratt, rout, rerr, restore=True)
    if sres.get('pid') == rres.get('pid') or sres.get('driver_pid') == rres.get('driver_pid') or \
       sres.get('pid') == sres.get('driver_pid') or rres.get('pid') == rres.get('driver_pid'):
        fail('Source and restore do not share one run profile across four distinct Host/driver PIDs')
    source_runtime, restore_runtime = source_run['runtime'], restore_run['runtime']
    provenance = save_restore.same_provenance(srq, rrq, source_runtime, restore_runtime)
    if source_run['provenance']['gamecore_sha256'] != restore_run['provenance']['gamecore_sha256'] or \
       source_run['provenance']['host_executable_sha256'] != restore_run['provenance']['host_executable_sha256'] or \
       source_run['provenance']['shared_lua_sha256'] != restore_run['provenance']['shared_lua_sha256']:
        fail('Source and restore Host/Core/shared-Lua chains differ')
    host_policy = verify_host_policy_sources(srq, frozen)
    restore_policy = verify_host_policy_sources(rrq, frozen)
    if host_policy['build_report']['sha256'] != restore_policy['build_report']['sha256'] or \
       {key: value for key, value in host_policy.items() if key != 'build_report'} != \
       {key: value for key, value in restore_policy.items() if key != 'build_report'}:
        fail('Source and restore compiled Host owned-city source closures differ')

    resume = rrq.get('resume_from')
    if type(resume) is not dict or resume.get('run_id') != run_id:
        fail('Restore request does not bind the specified source run')
    frozen_result = checked_path(resume.get('run_result'), restore_root / 'resume-source-result.json')
    if frozen_result.read_bytes() != (source_root / 'result.json').read_bytes():
        fail('Restore request froze a different source result')
    named_source = generated_inventory(sres, source_runtime)
    named_restore = generated_inventory(rres, restore_runtime)
    saves = exact_rows(sout, 'INTERACTIVE_NATIVE_SAVE', r'^INTERACTIVE_NATIVE_SAVE=(\d+)\|(.+)$')
    restore_saves = exact_rows(rout, 'INTERACTIVE_NATIVE_SAVE', r'^INTERACTIVE_NATIVE_SAVE=(\d+)\|(.+)$')
    if len(saves) < 2 or len(restore_saves) < 2:
        fail('Source and restore did not write initial and final native SDK saves')
    source_turn, source_save_text = int(saves[-1][0]), saves[-1][1]
    if source_turn != 1:
        fail('Source final native checkpoint is not the required turn-one save')
    source_save = absolute(source_save_text)
    if source_save.name != 'play-save-2-turn-1.zssave' or source_save not in named_source.get(source_save.name, []):
        fail('Source checkpoint is not its exact generated second turn-one save')
    source_final_path = exactly_one(named_source, 'play-final-state.txt', source_runtime)
    source_final = source_final_path.read_bytes()
    identity = save_restore.state_identity(source_final)
    if identity[0] != 1 or identity[1] != 1:
        fail('Source semantic state is not a turn-one SDK state')
    source_inputs = runtime_inputs(srq, source_runtime)
    restore_inputs = runtime_inputs(rrq, restore_runtime)
    if source_inputs.keys() != restore_inputs.keys() or any(
        source_inputs[name].get('sha256') != restore_inputs[name].get('sha256')
        for name in source_inputs
    ):
        fail('Fresh restore did not retain the exact source runtime input/provider chain')
    source_manifest = absolute(source_inputs['bundle.manifest']['path'])
    restore_manifest = absolute(restore_inputs['bundle.manifest']['path'])
    source_db = source_save.parent / 'Civ5SavedGameDatabase.db'
    if absolute(source_db) not in named_source.get(source_db.name, []):
        fail('Source native save sidecar database is absent from the immutable generated inventory')
    source_archive = save_restore.archive(source_save, source_manifest, source_db, identity)

    checkpoint_source = checked_path(resume.get('checkpoint_source'), source_save)
    checkpoint_input = checked_path(resume.get('checkpoint_input'))
    if not checkpoint_input.is_relative_to(restore_runtime) or checkpoint_input == checkpoint_source or \
       checkpoint_input.read_bytes() != source_save.read_bytes() or \
       digest(checkpoint_input) != resume['checkpoint_input'].get('sha256') or \
       digest(checkpoint_source) != resume['checkpoint_source'].get('sha256'):
        fail('Fresh restore checkpoint is not the exact immutable source turn-one save copy')
    restore_marker = exact_rows(rout, 'INTERACTIVE_RESTORE_CHECKPOINT',
                                r'^INTERACTIVE_RESTORE_CHECKPOINT=(.+)$')
    if len(restore_marker) != 1 or absolute(restore_marker[0][0]) != checkpoint_input:
        fail('Restore Host loaded a different checkpoint than the frozen source save')
    restore_initial_path = exactly_one(named_restore, 'play-initial-state.txt', restore_runtime)
    restore_initial_bytes = restore_initial_path.read_bytes()
    if restore_initial_bytes != source_final:
        fail('Fresh restore initial semantic SDK state differs byte-for-byte from source final state')
    restore_final_path = exactly_one(named_restore, 'play-final-state.txt', restore_runtime)
    restore_final_bytes = restore_final_path.read_bytes()
    restore_identity = save_restore.state_identity(restore_final_bytes)
    if restore_identity != (2, 2, identity[2], identity[3]):
        fail('Fresh restore did not preserve the turn-one state and advance exactly one normal turn to turn two')
    next_turn = exact_rows(rout, 'INTERACTIVE_NEXT_HUMAN_TURN', r'^INTERACTIVE_NEXT_HUMAN_TURN=(\d+)\|(\d+)$')
    if not any(int(turn) == 2 and int(updates) > 0 for turn, updates in next_turn):
        fail('Fresh restore lacks an actual SDK update on the turn-two human turn')

    source_citizens = citizen_rows(sout, 'final')
    restore_citizens = citizen_rows(rout, 'initial')
    header = one_marker(sout, 'INTERACTIVE_OWNED_CITY_HEADER_TARGET', TARGET_MARKERS['WorkerHeader'])
    city = int(header[0])
    shown_rows = [row for row in exact_rows(sout, 'INTERACTIVE_CITY_VIEW_SHOWN',
                            r'^INTERACTIVE_CITY_VIEW_SHOWN=(\d+)\|(\d+)\|([01])$') if row[2] == '0']
    if len(shown_rows) != 1 or int(shown_rows[0][1]) != city:
        fail('Run did not enter one original editable CityView for its exact selected city')
    owner = int(shown_rows[0][0])
    city_decision = one_marker(sout, 'INTERACTIVE_DECISION_CITY_READY', r'^INTERACTIVE_DECISION_CITY_READY=(\d+)$')
    if int(city_decision[0]) != city or (owner, city) not in source_citizens:
        fail('CityView target is not the owned city selected by the actual SDK decision sequence')
    settings = settings_proof(sout, source_citizens, restore_citizens, owner, city)
    source_scene = scene_and_input_proof(sout, sres, source_runtime, owner, city)
    production_return = verify_production_return(sout, named_source, source_runtime,
        scenes_by_sequence(source_run['driver'], source_runtime), ui_frames(sout), owner, city)
    restore_final_citizens = citizen_rows(rout, 'final')
    restored_settings = settings_proof(rout, restore_final_citizens, None, owner, city)
    if restore_final_citizens.get((owner, city)) == restore_citizens.get((owner, city)):
        fail('Fresh restore did not change either citizen setting through its original CityView')
    restored_scene = scene_and_input_proof(rout, rres, restore_runtime, owner, city)
    restored_production_return = verify_production_return(rout, named_restore, restore_runtime,
        scenes_by_sequence(restore_run['driver'], restore_runtime), ui_frames(rout), owner, city,
        close_result=rres)
    source_management = management_proof(sout, sres, source_runtime, owner, city)
    restored_management = management_proof(rout, rres, restore_runtime, owner, city)
    if (source_management is None) != (restored_management is None):
        fail('Source and restore did not use the same CityView management implementation')
    if sres.get('purchase_close_required') is not False or sres.get('purchase_close_verified') is not False or \
       sres.get('purchase_close_targets') != [] or sres.get('purchase_close_results') != []:
        fail('Source run unexpectedly entered the restore-only purchase close regression')
    yield_values = sdk_yield_values()
    source_purchase = purchase_proof(sout, sres, named_source, source_runtime,
        scenes_by_sequence(source_run['driver'], source_runtime), ui_frames(sout), owner, city, yield_values)
    restored_purchase = purchase_proof(rout, rres, named_restore, restore_runtime,
        scenes_by_sequence(restore_run['driver'], restore_runtime), ui_frames(rout), owner, city, yield_values)
    # Each run validates its own live SDK item, price, and exact state deltas;
    # prior source purchases can make different restored choices necessary.
    if [row['enum'] for row in source_purchase['purchases']] != \
       [row['enum'] for row in restored_purchase['purchases']]:
        fail('Fresh and restored runs do not cover the same purchase selection enums')
    # The return target and all posted inputs are tied to this one source run.
    if source_scene['clicks']['ReturnToMapButton']['id'] != 'ReturnToMapButton':
        fail('CityView return click did not retain the original ReturnToMapButton')

    # Reuse the native archive comparer: reload may append only the official
    # SDK Game-section message, and the next-turn save must preserve that proof.
    restored_checkpoint = exactly_one(named_restore, 'play-restored-checkpoint.zssave', restore_runtime)
    restored_db = restored_checkpoint.parent / 'Civ5SavedGameDatabase.db'
    if absolute(restored_db) not in named_restore.get(restored_db.name, []):
        fail('Restored checkpoint sidecar database is not in generated-file inventory')
    restored_archive = save_restore.archive(restored_checkpoint, restore_manifest, restored_db, identity)
    reload = save_restore.verify_reload(checkpoint_input, restored_checkpoint, rrq.get('language', ''),
        absolute(restore_inputs['localization.db']['path']), srq, *identity)
    before = {(row['kind'], row['index']): row['sha256'] for row in source_archive['sections']}
    after = {(row['kind'], row['index']): row['sha256'] for row in restored_archive['sections']}
    changed = [key for key in SECTION_IDENTITIES if before.get(key) != after.get(key)]
    if before.keys() != after.keys() or changed != [(3, 0)]:
        fail('Turn-one save restore changed native sections beyond the official SDK Game section')
    final_turn, final_save_text = int(restore_saves[-1][0]), restore_saves[-1][1]
    final_save = absolute(final_save_text)
    if final_turn != 2 or final_save.name != 'play-save-2-turn-2.zssave' or \
       final_save not in named_restore.get(final_save.name, []) or final_save.parent != restore_final_path.parent:
        fail('Turn-two native save is missing or is not paired with its actual final semantic state')
    final_db = final_save.parent / 'Civ5SavedGameDatabase.db'
    if absolute(final_db) not in named_restore.get(final_db.name, []):
        fail('Turn-two native save sidecar database is absent from the generated inventory')
    final_archive = save_restore.archive(final_save, restore_manifest, final_db, restore_identity)
    close_proof = restored_production_return.get('purchase_close')
    if not isinstance(close_proof, dict):
        fail('Fresh restore did not retain its independently verified purchase-close result')
    close_proof['final_native_checkpoint'] = artifact(final_save)
    close_proof['final_native_checkpoint_archive'] = final_archive
    close_proof['final_semantic_sdk_state'] = artifact(restore_final_path)
    close_proof['final_native_checkpoint_verified'] = True
    source_hashes_after = {path: digest(Path(path)) for path in source_hashes}
    if source_hashes_after != source_hashes or any(digest(Path(row['path'])) != row['sha256'] for row in frozen):
        fail('Verifier, helper, original UI sources, or frozen evidence changed during validation')

    return {
        'status': 'OWNED_CITY_ORIGINAL_UI_AND_FRESH_NATIVE_RESTORE_TURN_TWO_PASS',
        'scope': 'ACTUAL_SDK_OWNED_CITY_SETTINGS_SPECIALISTS_PLOTS_GOLD_UNIT_BUILDING_PURCHASE_AUDIO_PRODUCTION_SAVE_FRESH_RESTORE_TURN_TWO_CLOSE',
        'source_run': run_id, 'restore_run': restore_id,
        'pids': {'source_host': sres['pid'], 'source_driver': sres['driver_pid'],
                 'restore_host': rres['pid'], 'restore_driver': rres['driver_pid'],
                 'four_distinct_processes': True},
        'same_host_core_shared_lua_and_runtime_chain': True, 'provenance': provenance,
        'host_policy_sources': host_policy,
        'restore_host_build_report': restore_policy['build_report'],
        'owned_city': {'owner': owner, 'city': city, 'viewing_mode': False, 'editable': True,
                       'original_cityview_lifecycle': 'queued', 'scene_and_input_proof': source_scene,
                       'sdk_settings': settings, 'management': source_management, 'production_return': production_return,
                       'purchases': source_purchase},
        'restored_owned_city': {'owner': owner, 'city': city, 'scene_and_input_proof': restored_scene,
                               'sdk_settings': restored_settings, 'management': restored_management,
                               'production_return': restored_production_return, 'purchases': restored_purchase},
        'purchase_sequence_verified': True,
        'restore_purchase_close_regression_verified': True,
        'purchase_yield_enum_values': yield_values,
        'purchase_audio_original_provenance': host_policy.get('compiled_purchase_audio'),
        'source_turn': identity[0], 'restore_initial_turn': save_restore.state_identity(restore_initial_bytes)[0],
        'restored_turn': restore_identity[0], 'source_final_state_sha256': digest(source_final_path),
        'restore_initial_state_sha256': digest(restore_initial_path),
        'restore_initial_state_byte_identical_to_source_final': True,
        'citizen_focus_and_forced_avoid_exact_across_restore': True,
        'checkpoint': {'source': artifact(source_save), 'restore_input': artifact(checkpoint_input),
                       'bytes_identical': True, 'source_native_archive': source_archive,
                       'restored_native_archive': restored_archive, 'reload_comparison': reload,
                       'changed_sections': [list(row) for row in changed],
                       'turn_two_save': artifact(final_save), 'turn_two_archive': final_archive},
        'turn_one_to_turn_two_native_save_preserved': True,
        'retail_renderer_equivalence_verified': False,
        'full_cityview_ui_3d_equivalence_verified': False,
        'human_input_verified': False,
        'retail_save_compatibility_verified': False,
        'accepted_stage_promoted': False,
        'limitations': ['The CityView backdrop is a retained 2D scene request; retail 3D rendering is unverified.',
                        'Automated posted clicks do not establish human input or full original UI pixel equivalence.'],
        'frozen_sources': frozen, 'source_hashes_before': source_hashes,
        'source_hashes_after': source_hashes_after, 'proof_directory': str(proof),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id', required=True, help='Actual ordinary owned-city decision UI run ID')
    parser.add_argument('--restore-id', required=True, help='Fresh-process restore run ID for the source run')
    args = parser.parse_args()
    proof, frozen, source_hashes = freeze_inputs()
    try:
        report = verify(args.run_id, args.restore_id, proof, frozen, source_hashes)
        report['validator_sha256'] = digest(Path(os.path.abspath(__file__)))
        path = proof / 'conformance.json'
        path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        check_artifacts(report)
        print(json.dumps({'status': report['status'], 'proof': artifact(path),
                          'run_id': args.run_id, 'restore_id': args.restore_id,
                          'owned_city': report['owned_city']['owner'],
                          'city_id': report['owned_city']['city']}, ensure_ascii=False))
    except Exception as exc:
        (proof / 'validation_failure.json').write_text(json.dumps({
            'status': 'OWNED_CITY_VALIDATION_FAILED', 'run_id': args.run_id,
            'restore_id': args.restore_id, 'validator_path': os.path.abspath(__file__),
            'error': str(exc)}, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        raise


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'OWNED_CITY_UI_VERIFY_FAILED: {exc}', file=sys.stderr)
        raise SystemExit(1) from exc
