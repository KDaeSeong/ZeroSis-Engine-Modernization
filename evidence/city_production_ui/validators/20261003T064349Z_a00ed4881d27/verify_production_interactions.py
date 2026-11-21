"""Independently verify posted ProductionPopup category, pointer, wheel and epoch interactions.

This checks actual SDK-retained snapshots and owned HWND input/GPU evidence. It
does not prove human input, retail UI timing, or retail pixel equivalence.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
import re

from probe_world_builder import artifact
from ui_window_frame import verify_frame, verify_closed_frame
from verify_world_builder_map_object import check_artifacts


EXPECTED_ACTIONS = (
    'units-collapse-stale-click', 'units-expand', 'hover-unit', 'clear-hover',
    'wheel-down', 'wheel-up', 'buildings-collapse', 'buildings-expand', 'select-unit',
)
WINDOW_MESSAGES = {
    'WM_MOUSEMOVE': 0x0200, 'WM_LBUTTONDOWN': 0x0201, 'WM_MOUSELEAVE': 0x02A3,
    'WM_MOUSEWHEEL': 0x020A, 'WM_KEYDOWN': 0x0100,
}


def _fail(message):
    raise RuntimeError('Production interaction proof: ' + message)


def _rows(text, key):
    return re.findall(r'^' + re.escape(key) + r'=([^\r\n]*)$', text, re.M)


def _one(text, key):
    rows = _rows(text, key)
    if len(rows) != 1:
        _fail(f'expected one {key} marker, found {len(rows)}')
    return rows[0]


def _ints(fields, name):
    if any(not re.fullmatch(r'-?\d+', field) for field in fields):
        _fail(name + ' contains a malformed integer field')
    return [int(field) for field in fields]


def _doc(row, name):
    if type(row) is not dict or type(row.get('path')) is not str or type(row.get('sha256')) is not str:
        _fail(name + ' is not a path/hash artifact')
    check_artifacts(row)
    try:
        return json.loads(Path(row['path']).read_text(encoding='utf-8-sig'))
    except Exception as error:
        _fail(name + ' is not readable UTF-8 JSON: ' + str(error))


def _same_artifact(left, right, name):
    if type(left) is not dict or type(right) is not dict or \
       Path(left.get('path', '')).resolve() != Path(right.get('path', '')).resolve() or \
       left.get('sha256') != right.get('sha256'):
        _fail(name + ' artifact path/hash differs across its records')


def _float_equal(left, right, tolerance=1e-6):
    return type(left) in (int, float) and type(right) in (int, float) and \
        math.isfinite(left) and math.isfinite(right) and abs(left - right) <= tolerance


def _children(node):
    return node.get('children', []) if type(node) is dict and type(node.get('children')) is list else []


def _find_id(tree, control_id):
    found = []
    def visit(node):
        if type(node) is not dict:
            return
        if node.get('id') == control_id:
            found.append(node)
        for child in _children(node):
            visit(child)
    visit(tree)
    if len(found) != 1:
        _fail(f'expected one retained control ID {control_id}, found {len(found)}')
    return found[0]


def _find_key(tree, key):
    found = []
    def visit(node):
        if type(node) is not dict:
            return
        if node.get('key') == key:
            found.append(node)
        for child in _children(node):
            visit(child)
    visit(tree)
    if len(found) != 1:
        _fail(f'expected one retained key {key}, found {len(found)}')
    return found[0]


def _subtree_keys(node):
    result = set()
    def visit(value):
        if type(value) is not dict:
            return
        if type(value.get('key')) is int:
            result.add(value['key'])
        for child in _children(value):
            visit(child)
    visit(node)
    return result


def _target(state, key):
    targets = state.get('inputTargets')
    if type(targets) is not list:
        _fail('Production snapshot has no callback target list')
    found = [row for row in targets if type(row) is dict and row.get('key') == key and row.get('event') == 'LeftClick']
    if len(found) != 1:
        _fail(f'expected one retained callback target {key}, found {len(found)}')
    return found[0]


def _hit(manifest, key):
    hits = manifest.get('hit_regions')
    if type(hits) is not list:
        _fail('Prepared manifest has no native hit map')
    found = [row for row in hits if type(row) is list and len(row) == 5 and row[0] == key]
    if len(found) != 1:
        _fail(f'expected one prepared hit region for control key {key}, found {len(found)}')
    return found[0]


def _top_hit(manifest, x, y):
    hits = manifest.get('hit_regions', [])
    return next((hit for hit in reversed(hits)
                 if hit[1] <= x < hit[3] and hit[2] <= y < hit[4]), None)


def _scroll(state, manifest):
    targets = state.get('scrollTargets')
    regions = manifest.get('scroll_regions')
    if type(targets) is not list or type(regions) is not list:
        _fail('Production snapshot/manifest lacks scroll target provenance')
    expected = []
    for row in targets:
        if type(row) is not dict or row.get('event') != 'Scroll' or row.get('visible') is not True or row.get('disabled') is not False:
            _fail('Malformed captured Production scroll target')
        bounds, clipped = row.get('bounds'), row.get('clippedBounds')
        if type(bounds) is not dict or type(clipped) is not dict:
            _fail('Scroll target lacks retained and clipped XYWH bounds')
        expected.append([row['key'], clipped['x'], clipped['y'],
                         clipped['x'] + clipped['width'], clipped['y'] + clipped['height']])
    expected.sort(key=lambda item: item[0])
    if regions != expected:
        _fail('Prepared scroll regions differ from captured scrollTargets')
    return targets, regions


def _scene_artifacts(row, revision, active, session):
    if type(row) is not dict or row.get('sequence') != 1 or row.get('revision') != revision or row.get('active') is not active:
        _fail('Scene/update identity or active state is out of sequence')
    snapshot_art = row.get('snapshot')
    state = _doc(snapshot_art, f'snapshot revision {revision}')
    expected_name = 'ui-popup-1-window.json' if revision == 0 else f'ui-popup-1-live-{revision}.json'
    snapshot_path = Path(snapshot_art['path']).resolve()
    if snapshot_path.parent != Path(session).resolve() or snapshot_path.name != expected_name:
        _fail('Scene snapshot escaped the exact owned restored SDK session or revision name')
    if state.get('contextName') != 'ProductionPopup' or state.get('popupKind') != 'Production' or \
       state.get('active') is not active or state.get('timerSemaphore') != 0:
        _fail('Scene snapshot is not the exact official ProductionPopup lifetime state')
    expected_lifecycle = ['queued', 'shown:16'] if active else [
        'queued', 'shown:16', 'processed:16', 'context-hidden:ProductionPopup']
    if state.get('lifecycle') != expected_lifecycle:
        _fail('ProductionPopup snapshot lifecycle differs from its exact source event sequence')
    manifest = _doc(row.get('manifest'), f'prepared manifest revision {revision}')
    _same_artifact(manifest.get('snapshot'), snapshot_art, 'manifest snapshot')
    if manifest.get('context') != 'production' or manifest.get('context_name') != 'ProductionPopup' or \
       manifest.get('snapshot_state_unchanged') is not True or manifest.get('packet_version') != 'ZSUPIX02':
        _fail('Production scene manifest lost source state or the V2 packet contract')
    if manifest.get('packet') != row.get('packet'):
        _fail('Scene packet artifact differs between update row and prepared manifest')
    check_artifacts(row.get('packet'))
    database = row.get('database')
    check_artifacts(database)
    if Path(database['path']).name != 'rules.db' or Path(database['path']).resolve().parent != Path(session).resolve():
        _fail('Production live color database escaped the exact restored session')
    if manifest.get('inline_color_source', {}).get('sha256') is None or \
       manifest.get('inline_icon_source', {}).get('sha256') is None:
        _fail('Production scene lacks original color/icon mapping provenance')
    check_artifacts(manifest['inline_color_source']); check_artifacts(manifest['inline_icon_source'])
    for field in ('original_context_sources', 'pack_sources', 'selected_assets', 'font_sources', 'frozen_ui'):
        check_artifacts(manifest.get(field, []))
    png = row.get('png')
    check_artifacts(png)
    if type(png) is not dict or Path(png['path']).resolve().parent != Path(row['manifest']['path']).resolve().parent:
        _fail('Rendered source PNG is not next to its unique prepared manifest')
    if manifest.get('closed_context_not_drawn') is (not active):
        pass
    else:
        _fail('Closed/active scene manifest draw policy is inconsistent')
    if not active:
        if state.get('inputTargets') != [] or state.get('scrollTargets') != [] or \
           manifest.get('geometry') != [] or manifest.get('hit_regions') != [] or \
           manifest.get('scroll_regions') != [] or any(manifest.get(name) != 0 for name in ('texture_count', 'sprite_count')):
            _fail('Closed ProductionPopup scene contributes retained paint or input')
    else:
        _scroll(state, manifest)
    return state, manifest


def _message(plan):
    message = plan.get('message')
    if type(message) is str:
        message = WINDOW_MESSAGES.get(message)
    if type(message) is not int:
        _fail('Planned native input lacks an exact Windows message ID')
    return message


def _signed_word(value):
    return value - 65536 if value >= 32768 else value


def _unpack_lparam(value):
    value &= 0xffffffff
    return [_signed_word(value & 0xffff), _signed_word((value >> 16) & 0xffff)]


def _logical_from_client(client, size):
    width, height = size
    scale = min(width / 1920.0, height / 1080.0)
    left, top = (width - 1920 * scale) / 2, (height - 1080 * scale) / 2
    return [(client[0] - left) / scale, (client[1] - top) / scale]


def _plan_kind(plan):
    message = _message(plan)
    mapping = {0x0201: 1, 0x0200: 3, 0x02A3: 3, 0x020A: 4, 0x0100: 0}
    if message not in mapping:
        _fail('Unsupported native input message in interaction plan')
    return mapping[message]


def _validate_plan(plan, client_size, scene, manifest, action, selected):
    if type(plan) is not dict or plan.get('posted_successfully') is not True:
        _fail('Native input plan was not successfully posted to its owned HWND')
    message = _message(plan)
    key = plan.get('key')
    if type(key) is not int or key < 0:
        _fail('Native input plan has an invalid retained target key')
    if message in (0x0201, 0x0200):
        client = plan.get('client_point'); logical = plan.get('logical_point')
        if type(client) is not list or len(client) != 2 or type(logical) is not list or len(logical) != 2 or \
           _unpack_lparam(plan.get('lparam')) != client or (message == 0x0201 and plan.get('wparam') != 1):
            _fail('Mouse plan coordinates differ from the exact posted LPARAM')
        mapped = _logical_from_client(client, client_size)
        if any(not _float_equal(a, b, 1e-4) for a, b in zip(mapped, logical)):
            _fail('Posted client point does not map to the planned logical point')
        top = _top_hit(manifest, *logical)
        if message == 0x0201 and (top is None or top[0] != key):
            _fail('Posted control click does not target the topmost retained hit region')
        if message == 0x0200 and ((top[0] if top else 0) != key):
            _fail('Posted hover move does not resolve to its captured topmost callback key')
        if action == 'hover-unit' and (message != 0x0200 or key != selected['key']):
            _fail('Hover action does not target the selected retained unit row')
        if action == 'select-unit' and message == 0x0201 and key != selected['key']:
            _fail('Final click does not target the selected retained unit row')
    elif message == 0x020A:
        if plan.get('logical_scroll_delta') is None or type(plan.get('wheel_delta')) is not int or \
           not _float_equal(plan['logical_scroll_delta'], -plan['wheel_delta'] * 48 / 120):
            _fail('Wheel plan delta differs from the native scroll pixel conversion')
        if _unpack_lparam(plan.get('lparam')) != plan.get('screen_point'):
            _fail('Wheel screen point differs from posted LPARAM')
        logical = plan.get('logical_point')
        client = plan.get('client_point')
        if type(logical) is not list or len(logical) != 2 or type(client) is not list or len(client) != 2 or \
           any(not _float_equal(a, b, 1e-4) for a, b in zip(_logical_from_client(client, client_size), logical)):
            _fail('Wheel plan lacks its client-mapped logical point')
    elif message == 0x02A3:
        if key != 0 or plan.get('wparam') != 0 or plan.get('lparam') != 0:
            _fail('Mouse-leave plan must clear hover without identifying an old control')
    elif message == 0x0100:
        if key != 0 or plan.get('wparam') != 27 or plan.get('lparam') != 0:
            _fail('Late/closed keyboard plan is not an exact Escape keydown')


def _assert_category(snapshot, manifest, stack_id, expanded, selected_key=None):
    stack = _find_id(snapshot['tree'], stack_id)
    if stack.get('hidden') is (not expanded):
        pass
    else:
        _fail(stack_id + ' hidden state differs from requested category state')
    descendants = _subtree_keys(stack)
    rendered = {row.get('key') for row in manifest.get('geometry', []) if type(row) is dict}
    if expanded:
        if stack.get('hidden') is True or stack.get('key') not in rendered:
            _fail(stack_id + ' expanded state is absent from the prepared scene')
    else:
        if stack.get('hidden') is not True or descendants & rendered:
            _fail(stack_id + ' collapsed subtree remains in the prepared scene')
    if selected_key is not None:
        targets = {row.get('key') for row in snapshot.get('inputTargets', []) if type(row) is dict}
        hits = {row[0] for row in manifest.get('hit_regions', [])}
        if expanded and (selected_key not in targets or selected_key not in hits):
            _fail('Expanded unit category lacks the selected unit callback/hit')
        if not expanded and (selected_key in targets or selected_key in hits):
            _fail('Collapsed unit category still exposes the old selected unit callback/hit')


def _verify_source_rows(request, report):
    check_artifacts(request)
    check_artifacts(report)
    helpers = request.get('ui_window_tools')
    if type(helpers) is not list:
        _fail('Frozen live interaction helper closure is missing')
    names = [Path(row.get('path', '')).name for row in helpers if type(row) is dict]
    required = {'live_production_window_driver.py', 'render_ui_popup.py', 'ui_pixel_scene.py',
                'ui_bitmap_fonts.py', 'civ5_ui_assets.py', 'ui_window_frame.py', 'inline_icons.json'}
    if len(names) != len(helpers) or len(names) != len(set(names)) or not required.issubset(set(names)):
        _fail('Frozen helper closure is incomplete or duplicated')
    for row in helpers:
        source = row.get('original_source')
        if type(source) is not str:
            _fail('Frozen helper has no original source identity')
        original = Path(source).resolve(strict=True)
        copied = Path(row['path']).resolve(strict=True)
        if copied.read_bytes() != original.read_bytes():
            _fail('Frozen helper differs from its exact original source: ' + copied.name)
    for row in report.get('scenes', []) + report.get('updates', []):
        command = row.get('prepare_command')
        if type(command) is not list or not command:
            _fail('Scene prepare command provenance is missing')
        frozen_renderer = next(Path(item['path']).resolve() for item in helpers
                               if Path(item['path']).name == 'render_ui_popup.py')
        context_ok = command[-2:] == ['--context', 'production'] if row.get('active') else \
            command[-3:] == ['--context', 'production', '--closed']
        if not context_ok or not any(Path(arg).resolve() == frozen_renderer for arg in command):
            _fail('Scene preparation did not use the frozen renderer helper')


def verify_interactions(request, result, output, evidence_directory, runtime_directory):
    """Validate the driver's complete actual SDK/owned-HWND interaction report.

    `evidence_directory` is the immutable per-run evidence folder and
    `runtime_directory` is the private frozen runtime root from request.cwd;
    the exact restored SDK session is derived from its Host marker and scene request.
    """
    if request.get('production_interactions_requested') is not True or \
       result.get('production_interactions_enabled') is not True:
        _fail('Actual production interaction mode was not explicitly requested and completed')
    report_artifact = result.get('ui_window_report')
    report = _doc(report_artifact, 'live interaction report')
    if report.get('status') != 'LIVE_SDK_PRODUCTION_INTERACTIONS_PASS' or \
       report.get('production_interactions_enabled') is not True or \
       report.get('scope') != 'actual_SDK_production_category_pointer_panel_wheel_scene_epochs_and_unit_order' or \
       report.get('real_user_click_verified') is not False or report.get('installed_game_launched') is not False or \
       report.get('automatic_mouse_leave_tracking') is not False or report.get('positive_scroll_motion_verified') is not False or \
       report.get('returncode') != 0 or report.get('timed_out') is not False or report.get('error') is not None or \
       report.get('pid') != result.get('pid'):
        _fail('Live driver did not finish with its narrow posted-input/non-retail scope')
    if request.get('inherited_ui_window_profile_environment_removed') is not True or \
       request.get('ui_window_profile_environment_overrides') != {'ZEROSIS_UI_WINDOW_PROFILE': 'display-refresh'}:
        _fail('Live interaction run did not isolate its explicit native presentation profile')
    _verify_source_rows(request, report)

    runtime_root = Path(runtime_directory).resolve(strict=True)
    requested_runtime = Path(request.get('cwd', '')).resolve(strict=True)
    if runtime_root != requested_runtime:
        _fail('Common validator runtime path differs from the exact runtime recorded in request.json')
    session_rows = _rows(output, 'FOUND_CITY_RESTORE_SESSION_DIRECTORY')
    restore_sessions = [Path(value).resolve(strict=True) for value in session_rows]
    scene_request = _one(output, 'UI_WINDOW_SCENE_REQUEST').split('|')
    if len(scene_request) != 3 or scene_request[:2] != ['1', '0']:
        _fail('Host log lacks the exact initial production scene request')
    requested_snapshot = Path(scene_request[2]).resolve(strict=True)
    session = requested_snapshot.parent
    if session not in restore_sessions or session_rows.count(str(session)) != 1 or \
       session.parent != runtime_root / 'sessions' or \
       requested_snapshot.name != 'ui-popup-1-window.json':
        _fail('Initial snapshot is not from the exact Host-logged restored SDK session')
    restore_marker = 'FOUND_CITY_RESTORE_SESSION_DIRECTORY=' + str(session)
    if output.find(restore_marker) < 0 or output.find(restore_marker) > output.find('UI_WINDOW_SCENE_REQUEST='):
        _fail('Host did not identify the restored session before requesting the production scene')
    evidence_directory = Path(evidence_directory).resolve(strict=True)
    if Path(report_artifact['path']).resolve().parent != evidence_directory:
        _fail('Driver report escaped its unique run evidence directory')
    selected = report.get('selected_control')
    if type(selected) is not dict or any(type(selected.get(k)) is not int for k in ('key', 'city_id', 'unit_id')) or \
       min(selected.values()) < 0 or selected['key'] == 0:
        _fail('Live driver has no exact selected unit/city/control identity')

    scenes, updates = report.get('scenes'), report.get('updates')
    if type(scenes) is not list or len(scenes) != 1 or type(updates) is not list or len(updates) != 7:
        _fail('Live interaction must retain one initial scene and seven exact immutable revisions')
    _same_artifact(scenes[0]['snapshot'], {'path': str(requested_snapshot),
                   'sha256': scenes[0]['snapshot'].get('sha256')}, 'Host initial scene request')
    scene_state, scene_manifest = _scene_artifacts(scenes[0], 0, True, session)
    if scene_state.get('presentationClock') != 0.25 or scene_state.get('retailTimingVerified') is not False:
        _fail('Initial Production snapshot is not the owned clock-0.25 state')
    unit_targets = [row for row in scene_state.get('inputTargets', []) if type(row) is dict and
                    row.get('key') == selected['key'] and row.get('event') == 'LeftClick']
    if len(unit_targets) != 1 or (unit_targets[0].get('void1'), unit_targets[0].get('void2')) != (6, selected['unit_id']):
        _fail('Selected native unit target does not retain the exact stock production callback tuple')
    selected_node = _find_key(scene_state['tree'], selected['key'])
    if selected_node.get('kind') != 'Button' or selected_node.get('buttonState') != 'normal':
        _fail('Selected unit key is not the actual initial normal Production Button')
    _assert_category(scene_state, scene_manifest, 'UnitButtonStack', True, selected['key'])
    _assert_category(scene_state, scene_manifest, 'BuildingButtonStack', True)

    states = [scene_state]
    manifests = [scene_manifest]
    for revision, row in enumerate(updates, 1):
        state, manifest = _scene_artifacts(row, revision, revision != 7, session)
        expected_clock = 0.25 + 0.125 * min(revision, 6)
        if not _float_equal(state.get('presentationClock'), expected_clock, 1e-9) or \
           state.get('retailTimingVerified') is not False:
            _fail(f'Owner presentation clock/proof policy differs at revision {revision}')
        states.append(state); manifests.append(manifest)

    host_updates = []
    for line in _rows(output, 'UI_PRODUCTION_WINDOW_UPDATE'):
        fields = line.split('|')
        if len(fields) != 5:
            _fail('Malformed Host production revision marker')
        seq, turn, revision, active = _ints(fields[:4], 'PRODUCTION_WINDOW_UPDATE')
        host_updates.append((seq, turn, revision, active, Path(fields[4]).resolve(strict=True)))
    expected_host_updates = [(1, 0, revision, int(revision != 7),
                              Path(updates[revision - 1]['snapshot']['path']).resolve(strict=True))
                             for revision in range(1, 8)]
    if host_updates != expected_host_updates:
        _fail('Host revision markers differ from the exact retained snapshot paths and active lifetimes')

    # The exact stock controls and their visible/hidden descendant geometry must
    # follow the active retained snapshots.
    _assert_category(states[1], manifests[1], 'UnitButtonStack', False, selected['key'])
    _assert_category(states[2], manifests[2], 'UnitButtonStack', True, selected['key'])
    _assert_category(states[5], manifests[5], 'BuildingButtonStack', False)
    _assert_category(states[6], manifests[6], 'BuildingButtonStack', True)
    for state, manifest in ((states[3], manifests[3]),):
        row = _find_key(state['tree'], selected['key'])
        hover = [node for node in _all_nodes(row) if node.get('kind') == 'ShowOnMouseOver']
        if row.get('buttonState') != 'hover' or not hover or any(node.get('hovered') is not True for node in hover):
            _fail('Pointer hover snapshot does not retain the selected row and its real hover subtree')
        hover_keys = set().union(*(_subtree_keys(node) for node in hover))
        geometry_keys = {node.get('key') for node in manifest.get('geometry', []) if type(node) is dict}
        if not (hover_keys & geometry_keys):
            _fail('Hovered stock subtree produced no retained raster geometry')
    cleared = _find_key(states[4]['tree'], selected['key'])
    clear_groups = [node for node in _all_nodes(cleared) if node.get('kind') == 'ShowOnMouseOver']
    if cleared.get('buttonState') != 'normal' or any(node.get('hovered') is not False for node in clear_groups):
        _fail('Pointer-clear state was not retained before the building category interaction')

    actions = report.get('batches')
    completion = report.get('completion')
    if type(actions) is not list or len(actions) != len(EXPECTED_ACTIONS) or type(completion) is not dict:
        _fail('Live native action batches or completion record are missing')
    if [row.get('action') for row in actions] != list(EXPECTED_ACTIONS):
        _fail('Native action order differs from the required category/hover/wheel/unit fixture')
    batch_ids = [row.get('batch') for row in actions]
    if batch_ids != list(range(1, 10)):
        _fail('Native input batch sequence is not contiguous from one')
    initial_generation = 1
    update_batches = [1, 2, 3, 4, 7, 8, 9]
    # The stale zero-key reconciliation produces no extra revision when hover is already clear.
    for revision, row in enumerate(updates, 1):
        refresh = row.get('refresh')
        if type(refresh) is not dict or refresh.get('batch') != update_batches[revision - 1] or \
           refresh.get('old_generation') != revision or refresh.get('generation') != revision + 1:
            _fail(f'Scene refresh {revision} has a missing/noncontiguous generation transition')
        if not refresh.get('device_identity') or refresh.get('png_path') != row.get('png', {}).get('path'):
            _fail(f'Scene refresh {revision} lost same-device or rendered PNG provenance')

    expected_plan_lengths = [3, 1, 1, 1, 1, 1, 1, 1, 2]
    start_generations = [1, 2, 3, 4, 5, 5, 5, 6, 7]
    active_events = []
    stale_events = []
    for index, batch in enumerate(actions):
        action = EXPECTED_ACTIONS[index]
        if batch.get('sequence') != 1 or batch.get('batch') != index + 1 or \
           batch.get('hwnd') != actions[0].get('hwnd') or batch.get('owner_thread') != actions[0].get('owner_thread') or \
           batch.get('generation') != start_generations[index] or \
           batch.get('client') != [900, 600]:
            _fail(f'{action} batch changed its owned HWND/thread/client or started from an unexpected epoch')
        state = scene_state if index == 0 else None
        manifest = scene_manifest if index == 0 else None
        ready_snapshot = batch.get('snapshot')
        check_artifacts(ready_snapshot)
        if index == 0:
            _same_artifact(ready_snapshot, scenes[0]['snapshot'], 'first READY snapshot')
        else:
            rev = batch['generation'] - 1
            if rev < 0 or rev >= len(updates):
                _fail('Batch READY refers to an unknown scene revision')
            state, manifest = states[rev], manifests[rev]
            _same_artifact(ready_snapshot, updates[rev - 1]['snapshot'], 'READY snapshot')
        if batch.get('manifest', {}).get('sha256') != (scenes[0] if index == 0 else updates[batch['generation'] - 2])['manifest']['sha256']:
            _fail('Batch READY manifest differs from its retained scene revision')
        plans = batch.get('planned_inputs')
        if type(plans) is not list or len(plans) != expected_plan_lengths[index]:
            _fail(f'{action} does not contain its exact planned native message count')
        for plan in plans:
            _validate_plan(plan, batch['client'], state, manifest, action, selected)

        def target_id(key):
            target = _target(state, key)
            if target.get('visible') is not True or target.get('disabled') is not False:
                _fail('Planned click target is not a visible enabled original callback')
            return target.get('id')

        if action.startswith('units-') and target_id(plans[0]['key']) != 'UnitButton':
            _fail('Unit category action is not bound to the stock UnitButton callback')
        if action.startswith('buildings-') and target_id(plans[0]['key']) != 'BuildingsButton':
            _fail('Building category action is not bound to the stock BuildingsButton callback')
        if action == 'units-collapse-stale-click':
            old_target = _target(state, plans[1]['key'])
            if (old_target.get('void1'), old_target.get('void2')) != (6, selected['unit_id']):
                _fail('Same-batch old unit click does not carry the selected stock unit tuple')
            _hit(manifest, plans[1]['key'])
        if action.startswith('wheel-'):
            targets, regions = _scroll(state, manifest)
            if len(regions) != 1:
                _fail('Wheel action does not have one visible scroll panel owner')
            plan = plans[0]
            if plan['key'] != regions[0][0] or not (regions[0][1] <= plan['logical_point'][0] < regions[0][3] and
                                                     regions[0][2] <= plan['logical_point'][1] < regions[0][4]) or \
               _top_hit(manifest, *plan['logical_point']) is not None:
                _fail('Wheel point is not empty space owned by the retained ScrollPanel')
            scroll = next((target for target in targets if target['key'] == plan['key']), None)
            if scroll is None or scroll.get('maximumScroll') != 0 or scroll.get('scrollY') != 0:
                _fail('Expected max-zero scroll clamp is not supported by the captured Production panel')
            expected_delta = 48 if action == 'wheel-down' else -48
            if not _float_equal(plan.get('logical_scroll_delta'), expected_delta):
                _fail('Wheel direction/delta differs from the required down/up no-motion probes')
            if index + 1 < len(states) and states[index + 1].get('scrollTargets') != state.get('scrollTargets'):
                _fail('Max-zero wheel changed retained scroll state')
        native = batch.get('native_events')
        stale = batch.get('stale_events')
        batch_done = batch.get('completion')
        if type(native) is not list or type(stale) is not list or type(batch_done) is not dict:
            _fail(action + ' batch lacks native event/stale/completion records')
        stale_events.extend((index + 1, row) for row in stale)
        active_events.extend((index + 1, row) for row in native)
        if batch_done.get('event_count') != len(plans) or batch_done.get('active') is not (index != 8):
            _fail(action + ' batch native queue count or active transition differs')
        expected_end_generation = {1: 2, 2: 3, 3: 4, 4: 5, 5: 5, 6: 5, 7: 6, 8: 7, 9: 8}[index + 1]
        if batch_done.get('generation') != expected_end_generation:
            _fail(action + ' batch ended at an unexpected native scene generation')

    expected_native = [
        (1, 1, actions[0]['planned_inputs'][0]['key']),
        (2, 1, actions[1]['planned_inputs'][0]['key']),
        (3, 3, actions[2]['planned_inputs'][0]['key']), (4, 3, 0),
        (5, 4, actions[4]['planned_inputs'][0]['key']),
        (6, 4, actions[5]['planned_inputs'][0]['key']),
        (7, 1, actions[6]['planned_inputs'][0]['key']),
        (8, 1, actions[7]['planned_inputs'][0]['key']),
        (9, 1, actions[8]['planned_inputs'][0]['key']),
    ]
    if len(active_events) != len(expected_native):
        _fail('Native dispatch event count differs from the exact click/hover/wheel action plan')
    for (batch_id, event), (wanted_batch, wanted_kind, wanted_key) in zip(active_events, expected_native):
        if batch_id != wanted_batch or event.get('kind') != wanted_kind or event.get('generation') != actions[batch_id - 1]['generation'] or \
           (wanted_key is not None and event.get('key') != wanted_key):
            _fail('Native event does not match the planned current-generation action order')
        if wanted_kind == 4:
            plan = actions[batch_id - 1]['planned_inputs'][0]
            if event.get('key') != plan['key'] or not _float_equal(event.get('delta'), plan['logical_scroll_delta']):
                _fail('Native wheel event differs from its posted panel owner/delta')
        elif wanted_kind in (1, 3):
            plan = next((item for item in actions[batch_id - 1]['planned_inputs']
                         if _plan_kind(item) == wanted_kind and item.get('key') == event.get('key')), None)
            if plan is None:
                _fail('Native pointer/click dispatch key differs from successfully posted message')
        if event.get('virtual_key') != (27 if wanted_kind == 0 else 0):
            _fail('Native event virtual key differs from its message kind')

    expected_stale = [(1, 1, selected['key'], 1, 2, 0),
                      (1, 3, 0, 1, 2, 0),
                      (9, 0, 0, 7, 8, 27)]
    actual_stale = [(batch, event.get('kind'), event.get('key'), event.get('old_generation'),
                     event.get('generation'), event.get('virtual_key')) for batch, event in stale_events]
    if actual_stale != expected_stale:
        _fail('Old unit click, stale zero-key leave, or final late Escape was not rejected in its exact scene epoch')
    reconcile = [tuple(_ints(line.split('|'), 'RECONCILE_CLEAR'))
                 for line in _rows(output, 'UI_PRODUCTION_WINDOW_RECONCILE_CLEAR')]
    if reconcile != [(1, 1, 1, 2, 1)]:
        _fail('Stale zero-key mouse-leave was not reconciled exactly once into the current active context')
    # The first batch has two input events rejected as stale; the old unit click
    # is removed, while only the zero-key clear is replayed into the new epoch.
    if active_events[0][1]['key'] != actions[0]['planned_inputs'][0]['key']:
        _fail('First collapse batch did not dispatch the stock category control first')

    # Native marker counts, result rows and RNG/SDK-state observations are three
    # independent views of every dispatched event.
    gameplay = []
    for line in _rows(output, 'UI_PRODUCTION_WINDOW_GAMEPLAY'):
        fields = line.split('|')
        if len(fields) != 6:
            _fail('Malformed SDK-state input marker')
        seq, kind, key, active_after, equal = _ints(fields[:5], 'GAMEPLAY')
        try: delta = float(fields[5])
        except ValueError: _fail('Malformed SDK-state input delta')
        if seq != 1 or active_after not in (0, 1) or equal not in (0, 1) or not math.isfinite(delta):
            _fail('Invalid SDK-state input marker values')
        if active_after and equal != 1:
            _fail('Nonclosing native interaction changed SDK gameplay state')
        gameplay.append((kind, key, active_after, equal, delta))
    input_rows = []
    for line in _rows(output, 'UI_WINDOW_INPUT'):
        fields = line.split('|')
        if len(fields) != 10:
            _fail('Malformed RNG/timer/turn input marker')
        row = _ints(fields, 'UI_WINDOW_INPUT')
        if row[0] != 1 or row[4] != row[5] or row[6:8] != [0, 0] or row[8] != 0:
            _fail('Input changed RNG, popup timer, or game turn')
        input_rows.append(row)
    if len(gameplay) != 11 or len(input_rows) != 11:
        _fail('SDK/RNG input observations do not cover all active/reconciled/closed dispatches')
    expected_gameplay = []
    for position, (batch_id, event) in enumerate(active_events):
        kind = {0: 1, 1: 2, 3: 3, 4: 4}[event['kind']]
        closing_selection = position == len(active_events) - 1
        expected_gameplay.append((kind, event['key'], 0 if closing_selection else 1,
                                  0 if closing_selection else 1,
                                  event['delta'] if kind == 4 else 0.0))
        if position == 0:
            expected_gameplay.append((3, 0, 1, 1, 0.0)) # reconciled stale leave
    expected_gameplay.append((1, 27, 0, 1, 0.0)) # closed Escape is dispatched and rejected
    if gameplay != expected_gameplay:
        _fail('SDK-state markers differ from actual native dispatch order or no-mutation contract')

    # Batch totals deliberately count the stale leave as rejected and its one
    # explicit reconciliation as accepted; this source path can therefore have
    # accepted + stale one larger than drained delivery count.
    if [row['completion']['accepted_total'] for row in actions] != [2, 3, 4, 5, 6, 7, 8, 9, 10] or \
       [row['completion']['stale_total'] for row in actions] != [2, 2, 2, 2, 2, 2, 2, 2, 3] or \
       completion != {'batch_count': 9, 'delivered': 12, 'accepted': 10, 'stale': 3,
                      'closed_input_count': 1, 'closed_accepted': 0, 'generation': 8}:
        _fail('Live batch totals differ from the actual category/hover/wheel/stale/closed protocol')

    closed_plan = report.get('closed_input_plan')
    if type(closed_plan) is not list or len(closed_plan) != 3:
        _fail('Closed scene lacks its old-coordinate click, wheel, and Escape rejection plan')
    for plan in closed_plan:
        if plan.get('posted_successfully') is not True:
            _fail('A closed-scene rejection input was not posted to the same HWND')
    select_plan, wheel_up_plan, closed_escape = closed_plan
    if _message(select_plan) != 0x0201 or select_plan.get('key') != selected['key'] or \
       select_plan.get('client_point') != actions[8]['planned_inputs'][0].get('client_point') or \
       _message(wheel_up_plan) != 0x020A or wheel_up_plan.get('key') != actions[5]['planned_inputs'][0].get('key') or \
       _message(closed_escape) != 0x0100 or closed_escape.get('wparam') != 27:
        _fail('Closed old-coordinate click/wheel/Escape plan is not tied to the prior live controls')
    closed_events = report.get('closed_events')
    if closed_events != [{'kind': 0, 'key': 0, 'virtual_key': 27, 'delta': 0.0, 'generation': 8, 'consumed': False}]:
        _fail('Closed scene did not deliver exactly one rejected current-generation Escape')
    if _one(output, 'UI_PRODUCTION_WINDOW_CLOSED') != '1|' + str(actions[0]['hwnd']) + '|8':
        _fail('Closed context did not retain the original HWND and final scene generation')
    closed_lines = _rows(output, 'UI_PRODUCTION_WINDOW_CLOSED_EVENT')
    if closed_lines != ['1|0|0|27|0|8|0']:
        _fail('Closed native event marker differs from its exact rejected Escape')
    complete_line = _one(output, 'UI_PRODUCTION_WINDOW_COMPLETE')
    if complete_line != '1|9|12|10|3|1|0|8|owner-thread':
        _fail('Native completion marker differs from verified batch/closed counts')

    # All frames come from the same HWND and owner thread, on the same D3D
    # device, and are recomputed from their exact frozen source scene PNG.
    frames = report.get('frames')
    expected_phases = ['initial', 'resized'] + [f'live-{revision}' for revision in range(1, 8)]
    if type(frames) is not list or [row.get('phase') for row in frames] != expected_phases:
        _fail('GPU frame sequence is incomplete or out of update order')
    identities = [row.get('device_identity') for row in frames]
    if any(type(identity) is not int or identity <= 0 for identity in identities) or len(set(identities)) != 1:
        _fail('Initial, resize and live update captures do not share one verified D3D device identity')
    hwnd, owner_thread = actions[0]['hwnd'], actions[0]['owner_thread']
    source_by_revision = {0: scenes[0], **{row['revision']: row for row in updates}}
    pixel_results = []
    previous_render = previous_present = 0
    for frame in frames:
        revision = frame.get('revision')
        if frame.get('sequence') != 1 or frame.get('hwnd') != hwnd or frame.get('owner_thread') != owner_thread or \
           frame.get('is_window_visible') is not True or frame.get('client') != ([1000, 700] if frame['phase'] == 'initial' else [900, 600]):
            _fail('GPU frame escaped its persistent visible HWND/thread or expected client size')
        if type(frame.get('render_count')) is not int or type(frame.get('present_count')) is not int or \
           frame['render_count'] <= previous_render or frame['present_count'] <= previous_present:
            _fail('GPU render/present counters are not strictly continuous')
        previous_render, previous_present = frame['render_count'], frame['present_count']
        source_row = source_by_revision.get(revision)
        if source_row is None:
            _fail('GPU frame has no immutable source scene revision')
        source_png = source_row.get('png')
        capture_png = frame.get('png')
        check_artifacts(source_png); check_artifacts(capture_png)
        checker = verify_frame if source_row['active'] else verify_closed_frame
        pixel = checker(Path(source_png['path']), Path(capture_png['path']), *frame['client'])
        if pixel != frame.get('pixel_check'):
            _fail('Independent GPU PNG parity recomputation differs from the driver record')
        for false_field in ('same_swapchain_buffer_verified', 'capture_origin_verified',
                            'desktop_capture_verified', 'human_visual_review_verified', 'pixel_origin_verified'):
            if false_field in pixel and pixel.get(false_field) is not False:
                _fail('Pixel-only verifier overstated capture origin: ' + false_field)
        pixel_results.append(pixel)
    device_rows = []
    for line in _rows(output, 'UI_PRODUCTION_WINDOW_DEVICE'):
        fields = line.split('|')
        if len(fields) != 3:
            _fail('Malformed GPU device identity marker')
        device_rows.append((fields[0], fields[1], int(fields[2])))
    if device_rows != [('1', phase, identities[index]) for index, phase in enumerate(expected_phases)]:
        _fail('GPU frame device identity markers differ from per-frame report records')
    refresh_rows = []
    for line in _rows(output, 'UI_PRODUCTION_WINDOW_REFRESH'):
        fields = line.split('|')
        if len(fields) != 8:
            _fail('Malformed live scene refresh marker')
        refresh_rows.append(fields)
    expected_refresh = []
    for row in updates:
        item = row['refresh']
        expected_refresh.append([str(1), str(item['batch']), str(row['revision']), str(item['old_generation']),
                                 str(item['generation']), str(item['device_identity']), str(item['device_identity']),
                                 item['png_path']])
    if refresh_rows != expected_refresh:
        _fail('Live refresh markers differ from same-device, contiguous-generation update records')

    frame_lines = _rows(output, 'UI_WINDOW_FRAME')
    if len(frame_lines) != len(frames):
        _fail('Native frame logs are missing or duplicated')
    for line, frame in zip(frame_lines, frames):
        fields = line.split('|')
        expected = [str(frame['sequence']), frame['phase'], str(frame['hwnd']), str(frame['owner_thread']),
                    str(frame['client'][0]), str(frame['client'][1]), str(frame['render_count']),
                    str(frame['present_count']), str(frame['present_hresult']), frame['device_kind'],
                    str(int(frame['present_occluded'])), str(int(frame['is_window_visible'])), frame['png']['path']]
        if fields != expected or frame.get('device_kind') not in ('hardware', 'warp') or \
           frame.get('present_hresult') not in (0, 0x087A0001) or \
           frame.get('present_occluded') != (frame.get('present_hresult') == 0x087A0001):
            _fail('Native frame marker differs from exact frame metadata or Present HRESULT')

    expected_expected_control = f"1|{selected['key']}|{selected['city_id']}|{selected['unit_id']}"
    selection_rows = _rows(output, 'PRODUCTION_UI_SELECTION')
    if selection_rows != [f"{selected['city_id']},{selected['unit_id']},{selected['key']}"] or \
       _rows(output, 'UI_WINDOW_EXPECTED_CONTROL') != [expected_expected_control] or \
       _rows(output, 'PRODUCTION_UI_WINDOW_ROUTE') != ['OWNED_HWND_HIT_OFFICIAL_CALLBACK_SDK_RECEIVER']:
        _fail('Final stock unit selection is not bound to the original callback and SDK receiver')

    return {
        'driver_report': artifact(Path(report_artifact['path'])),
        'selected_control': selected,
        'production_categories_verified': True,
        'production_hover_and_clear_verified': True,
        'empty_panel_wheel_routing_verified': True,
        'positive_scroll_motion_verified': False,
        'max_zero_scroll_clamp_verified': True,
        'old_unit_click_rejected_after_scene_replacement': True,
        'stale_zero_key_pointer_reconciliation_verified': True,
        'late_escape_rejected_after_selection': True,
        'closed_old_coordinate_click_and_wheel_not_delivered': True,
        'closed_escape_rejected': True,
        'same_hwnd_thread_and_d3d_device_verified': True,
        'scene_epoch_sequence_verified': True,
        'gpu_frames': frames,
        'gpu_bitmap_pixel_parity_verified': True,
        'sdk_nonclosing_state_and_rng_turn_invariance_verified': True,
        'human_input_verified': False,
        'installed_game_launched': False,
        'retail_pixel_equivalence_verified': False,
        'whole_ui_equivalence_verified': False,
        'world_renderer_verified': False,
    }


def _all_nodes(tree):
    result = []
    def visit(node):
        if type(node) is not dict:
            return
        result.append(node)
        for child in _children(node):
            visit(child)
    visit(tree)
    return result
