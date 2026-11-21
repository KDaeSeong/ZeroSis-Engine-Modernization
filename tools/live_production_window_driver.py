"""Record bounded native production input on one freshly owned SDK HWND.

The retained stock context stays live across scene replacements. This is an
explicit posted-message test profile, with owner-controlled animation time and
explicit mouse-leave messages; it is not human input or retail display proof.
"""
from __future__ import annotations
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import queue
import sqlite3
import subprocess
import sys
import threading
import time

from civ5_ui_assets import require, sha256
from render_ui_popup import artifact
from ui_window_frame import verify_frame, verify_closed_frame


def collect_live_production_window(process, directory, evidence, timeout, frozen_tools):
    directory = Path(directory).resolve(strict=True)
    evidence, frozen_tools = Path(evidence), Path(frozen_tools)
    channels = {name: bytearray() for name in ('stdout', 'stderr')}
    signals, reader_errors = queue.Queue(), []
    report = {'status': 'LIVE_PRODUCTION_WINDOW_PENDING', 'pid': process.pid,
              'scope': 'actual_SDK_production_category_pointer_panel_wheel_scene_epochs_and_unit_order',
              'production_interactions_enabled': True, 'real_user_click_verified': False,
              'installed_game_launched': False, 'automatic_mouse_leave_tracking': False,
              'owner_clock_step_seconds': 0.125, 'positive_scroll_motion_verified': False,
              'scenes': [], 'updates': [], 'frames': [], 'batches': [], 'completion': None,
              'error': None, 'cleanup': None}
    report_path = evidence / 'ui_window.json'

    def checkpoint():
        temporary = report_path.with_suffix('.json.tmp')
        temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
        temporary.replace(report_path)

    def read(name, stream):
        try:
            while True:
                line = stream.readline(1024 * 1024)
                if not line:
                    break
                require(len(line) < 1024 * 1024 and len(channels[name]) + len(line) < 32 * 1024 * 1024,
                        'Owned production diagnostic stream exceeded its bound')
                channels[name] += line
                if name == 'stdout' and (line.startswith(b'UI_WINDOW_') or line.startswith(b'UI_PRODUCTION_WINDOW_')):
                    signals.put(line.decode('utf8', errors='strict').strip())
        except Exception as error:
            reader_errors.append(str(error))
            signals.put('READER_ERROR')
        finally:
            if name == 'stdout': signals.put('STDOUT_EOF')

    threads = [threading.Thread(target=read, args=(name, getattr(process, name)), daemon=True) for name in channels]
    deadline, timed_out = time.monotonic() + timeout, False
    prepared, frames, batches, refreshes = {}, {}, {}, {}
    initial = selected = owned_window = None
    last_revision = 0
    actions = ('units-collapse-stale-click', 'units-expand', 'hover-unit', 'clear-hover',
               'wheel-down', 'wheel-up', 'buildings-collapse', 'buildings-expand', 'select-unit')

    def acknowledge(value):
        process.stdin.write((value + '\n').encode('ascii'))
        process.stdin.flush()

    def prepare(snapshot, revision, active, left):
        snapshot = Path(snapshot).resolve(strict=True)
        expected = f'ui-popup-1-live-{revision}.json' if revision else 'ui-popup-1-window.json'
        require(snapshot.is_relative_to(directory) and snapshot.name == expected and
                (not prepared or snapshot.parent == initial['snapshot_path'].parent),
                'Production snapshot escaped its owned exact SDK session')
        before = artifact(snapshot)
        state = json.loads(snapshot.read_text(encoding='utf8'))
        require(state.get('active') is active and state.get('contextName') == 'ProductionPopup' and
                state.get('popupKind') == 'Production' and state.get('timerSemaphore') == 0,
                'Production update has an invalid stock context lifetime')
        folder = snapshot.parent / ('presentation-popup-1' + (f'-live-{revision}' if revision else ''))
        require(folder.resolve().is_relative_to(directory) and not folder.exists(),
                'Refusing to reuse a production presentation directory')
        folder.mkdir()
        database = snapshot.parent / 'rules.db'
        require(database.resolve(strict=True).is_relative_to(directory), 'Production color DB escaped owned runtime')
        db_before = artifact(database)
        with sqlite3.connect(database.resolve().as_uri() + '?mode=ro', uri=True) as connection:
            rows = connection.execute('SELECT Type,Red,Green,Blue,Alpha FROM Colors WHERE Type LIKE ?', ('COLOR_%',)).fetchall()
        colors = {row[0]: list(row[1:]) for row in rows}
        require(len(rows) == len(colors), 'Duplicate live color key')
        (folder / 'inline_colors.json').write_text(json.dumps({'database': db_before, 'colors': colors},
                                                 ensure_ascii=False, indent=2) + '\n', encoding='utf8')
        icons = frozen_tools / 'inline_icons.json'
        (folder / 'inline_icons.json').write_bytes(icons.read_bytes())
        require(sha256(icons) == sha256(folder / 'inline_icons.json'), 'Frozen FontIcons changed while copying')
        manifest = folder / 'scene_manifest.json'
        command = [sys.executable, '-B', '-X', 'utf8', str(frozen_tools / 'render_ui_popup.py'),
                   '--prepare', str(snapshot), '--directory', str(folder), '--manifest', str(manifest), '--context', 'production']
        if not active: command.append('--closed')
        child = subprocess.run(command, cwd=directory, capture_output=True, timeout=min(60, left),
                               creationflags=subprocess.CREATE_NO_WINDOW)
        log = evidence / f'ui_production_prepare_{revision}.log'
        log.write_bytes(child.stdout + child.stderr)
        require(child.returncode == 0, 'Production scene preparation failed: ' + str(log))
        require(sha256(snapshot) == before['sha256'] and sha256(database) == db_before['sha256'],
                'Preparing production pixels changed SDK UI state or database')
        compiled = json.loads(manifest.read_text(encoding='utf8'))
        require(compiled['snapshot']['sha256'] == before['sha256'] and compiled['snapshot_state_unchanged'] is True,
                'Prepared production scene lost its frozen live-state binding')
        row = {'sequence': 1, 'revision': revision, 'active': active, 'snapshot': before, 'database': db_before,
               'manifest': artifact(manifest), 'prepare_log': artifact(log), 'prepare_command': command,
               'packet': compiled['packet'], 'retained_runtime_bounds_check': compiled['retained_runtime_bounds_check']}
        value = {'snapshot_path': snapshot, 'folder': folder, 'compiled': compiled, 'state': state, 'row': row}
        prepared[str(snapshot)] = value
        report['updates' if revision else 'scenes'].append(row)
        checkpoint()
        return value

    def find_node(state, control_id):
        found = []
        def visit(node):
            if node.get('id') == control_id: found.append(node)
            for child in node.get('children', []): visit(child)
        visit(state['tree'])
        require(len(found) == 1, 'Production node ID is not unique: ' + control_id)
        return found[0]

    def point(width, height, region):
        key, x0, y0, x1, y1 = region
        require(0 < key and 0 <= x0 < x1 <= 1920 and 0 <= y0 < y1 <= 1080,
                'Production region escaped its logical viewport')
        scale = min(width / 1920, height / 1080)
        x = round((width - 1920 * scale) / 2 + (x0 + x1) * scale / 2)
        y = round((height - 1080 * scale) / 2 + (y0 + y1) * scale / 2)
        lx = (x - (width - 1920 * scale) / 2) / scale
        ly = (y - (height - 1080 * scale) / 2) / scale
        require(0 <= x < width and 0 <= y < height and x0 <= lx < x1 and y0 <= ly < y1,
                'Production mapped point escaped the retained region')
        return [x, y], [lx, ly]

    try:
        for thread in threads: thread.start()
        checkpoint()
        user32 = ctypes.WinDLL('user32', use_last_error=True)
        user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        user32.PostMessageW.restype = wintypes.BOOL
        user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        user32.GetClientRect.restype = wintypes.BOOL
        user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
        user32.ClientToScreen.restype = wintypes.BOOL
        user32.IsWindowVisible.argtypes = [wintypes.HWND]
        user32.IsWindowVisible.restype = wintypes.BOOL

        def check_window(handle, tid, width=900, height=600):
            pid, client = wintypes.DWORD(), wintypes.RECT()
            require(user32.GetWindowThreadProcessId(wintypes.HWND(handle), ctypes.byref(pid)) == tid and pid.value == process.pid,
                    'Production HWND does not belong to the exact fresh owned child/thread')
            require(user32.GetClientRect(wintypes.HWND(handle), ctypes.byref(client)) and
                    [client.right, client.bottom] == [width, height] and user32.IsWindowVisible(wintypes.HWND(handle)),
                    'Production native client or visible-window state differs')

        def post(handle, plan):
            require(user32.PostMessageW(wintypes.HWND(handle), plan['message'], plan['wparam'], plan['lparam']),
                    'Posting to owned production HWND failed')
            if plan['message'] == 0x0201:
                require(user32.PostMessageW(wintypes.HWND(handle), 0x0202, 0, plan['lparam']),
                        'Posting the owned production mouse release failed')
                plan['release'] = {'message': 0x0202, 'wparam': 0, 'lparam': plan['lparam'], 'posted_successfully': True}
            plan['posted_successfully'] = True

        def mouse_plan(message, key, client, logical, handle, delta=None):
            x, y = client
            plan = {'message': message, 'wparam': 1 if message == 0x0201 else 0, 'lparam': (y << 16) | x,
                    'key': key, 'client_point': client, 'logical_point': logical}
            if delta is not None:
                screen = wintypes.POINT(x, y)
                require(user32.ClientToScreen(wintypes.HWND(handle), ctypes.byref(screen)) and
                        -32768 <= screen.x <= 32767 and -32768 <= screen.y <= 32767,
                        'Wheel screen coordinate conversion escaped signed message coordinates')
                plan.update(wparam=(delta & 0xffff) << 16,
                            lparam=((screen.y & 0xffff) << 16) | (screen.x & 0xffff),
                            screen_point=[screen.x, screen.y], wheel_delta=delta, logical_scroll_delta=-delta * 48 / 120)
            return plan

        while True:
            left = deadline - time.monotonic()
            require(left > 0, 'Owned production host exceeded its execution deadline')
            try: signal = signals.get(timeout=min(left, 0.25))
            except queue.Empty: continue
            if signal == 'STDOUT_EOF': break
            if signal == 'READER_ERROR': raise ValueError('; '.join(reader_errors))
            fields = signal.split('=', 1)[1].split('|')
            if signal.startswith('UI_WINDOW_EXPECTED_CONTROL='):
                seq, key, city, unit = map(int, fields)
                require(seq == 1 and selected is None and key > 0 and city >= 0 and unit >= 0, 'Invalid selected unit declaration')
                selected = {'key': key, 'city_id': city, 'unit_id': unit}
                report['selected_control'] = selected
            elif signal.startswith('UI_WINDOW_SCENE_REQUEST='):
                require(fields[:2] == ['1', '0'] and initial is None and selected is not None, 'Unexpected initial production request')
                initial = prepare(fields[2], 0, True, left)
                acknowledge('READY|1')
            elif signal.startswith('UI_PRODUCTION_WINDOW_UPDATE='):
                seq, turn, revision, active = map(int, fields[:4])
                require(seq == 1 and turn == 0 and revision == last_revision + 1 and active in (0, 1), 'Invalid production update order')
                prepare(fields[4], revision, bool(active), left)
                last_revision = revision
                acknowledge(f'UPDATE|1|{revision}')
            elif signal.startswith('UI_WINDOW_FRAME='):
                require(len(fields) == 13 and int(fields[0]) == 1, 'Invalid production GPU frame metadata')
                phase = fields[1]
                revision = int(phase.split('-')[1]) if phase.startswith('live-') else 0
                require(phase in ('initial', 'resized') or phase == f'live-{last_revision}', 'Production capture phase differs')
                value = next((value for value in prepared.values() if value['row']['revision'] == revision), None)
                require(value is not None and phase not in frames, 'Production capture lacks a unique prepared scene')
                value['row']['png'] = artifact(value['folder'] / 'popup.png')
                capture = Path(fields[12]).resolve(strict=True)
                name = 'frame-live.png' if revision else f'frame-{phase}.png'
                require(capture == (value['folder'] / name).resolve(strict=True), 'Production capture escaped prepared scene')
                frame = {'sequence': 1, 'phase': phase, 'revision': revision, 'hwnd': int(fields[2]), 'owner_thread': int(fields[3]),
                         'client': [int(fields[4]), int(fields[5])], 'render_count': int(fields[6]), 'present_count': int(fields[7]),
                         'present_hresult': int(fields[8]), 'device_kind': fields[9], 'present_occluded': bool(int(fields[10])),
                         'is_window_visible': bool(int(fields[11])), 'png': artifact(capture)}
                checker = verify_frame if value['row']['active'] else verify_closed_frame
                frame['pixel_check'] = checker(Path(value['row']['png']['path']), capture, *frame['client'])
                report['frames'].append(frame); frames[phase] = frame
                checkpoint()
            elif signal.startswith('UI_PRODUCTION_WINDOW_DEVICE='):
                seq, phase, identity = fields
                require(seq == '1' and phase in frames and int(identity) > 0 and 'device_identity' not in frames[phase], 'Invalid GPU device identity')
                frames[phase]['device_identity'] = int(identity)
                checkpoint()
            elif signal.startswith('UI_PRODUCTION_WINDOW_REFRESH='):
                seq, batch, revision, old, new, device_before, device_after = map(int, fields[:7])
                require(seq == 1 and batch in batches and revision == last_revision and revision not in refreshes and
                        old == revision and new == old + 1 and device_before == device_after == frames['initial']['device_identity'] and
                        f'live-{revision}' in frames and frames[f'live-{revision}']['device_identity'] == device_after,
                        'Production refresh lost generation or device continuity')
                refreshes[revision] = {'batch': batch, 'old_generation': old, 'generation': new, 'device_identity': device_after, 'png_path': fields[7]}
                report['updates'][revision - 1]['refresh'] = refreshes[revision]
                checkpoint()
            elif signal.startswith('UI_PRODUCTION_WINDOW_READY='):
                seq, batch, generation, handle, tid, width, height = map(int, fields[:7])
                require(seq == 1 and batch == len(batches) + 1 and batch <= len(actions) and generation == last_revision + 1,
                        'Unexpected live production input batch')
                check_window(handle, tid, width, height)
                value = prepared.get(str(Path(fields[7]).resolve(strict=True)))
                require(value is not None and value['row']['active'] and Path(fields[8]).resolve(strict=True) == value['folder'] / 'popup.png',
                        'Production READY lacks the exact current scene')
                require('initial' in frames and 'resized' in frames and frames['initial']['hwnd'] == frames['resized']['hwnd'] == handle and
                        frames['initial']['device_identity'] == frames['resized']['device_identity'], 'Production resize lost window/device identity')
                if owned_window is None: owned_window = [handle, tid]
                require(owned_window == [handle, tid], 'Production batches replaced their owned HWND/thread')
                action = actions[batch - 1]
                hits = value['compiled']['hit_regions']
                def hit_for(control_id=None, unit=False):
                    candidates = [target for target in value['state']['inputTargets'] if target.get('event') == 'LeftClick' and
                                  (target.get('void1') == 6 and target.get('void2') == selected['unit_id'] if unit else target['id'] == control_id)]
                    require(len(candidates) == 1, 'Production action lacks its unique actual target')
                    regions = [hit for hit in hits if hit[0] == candidates[0]['key']]
                    require(len(regions) == 1, 'Production target has no unique clipped native hit')
                    client, logical = point(width, height, regions[0])
                    top = next((hit for hit in reversed(hits) if hit[1] <= logical[0] < hit[3] and hit[2] <= logical[1] < hit[4]), None)
                    require(top == regions[0], 'Production action point is covered by another click target')
                    return regions[0][0], client, logical
                plans = []
                if action.startswith('units-'):
                    key, client, logical = hit_for('UnitButton')
                    plans.append(mouse_plan(0x0201, key, client, logical, handle))
                    if action == 'units-collapse-stale-click':
                        old_key, old_client, old_logical = hit_for(unit=True)
                        plans.append(mouse_plan(0x0201, old_key, old_client, old_logical, handle))
                        plans.append({'message': 0x02A3, 'wparam': 0, 'lparam': 0, 'key': 0})
                elif action.startswith('buildings-'):
                    key, client, logical = hit_for('BuildingsButton')
                    plans.append(mouse_plan(0x0201, key, client, logical, handle))
                elif action in ('hover-unit', 'select-unit'):
                    key, client, logical = hit_for(unit=True)
                    plans.append(mouse_plan(0x0200 if action == 'hover-unit' else 0x0201, key, client, logical, handle))
                    if action == 'select-unit': plans.append({'message': 0x0100, 'wparam': 27, 'lparam': 0, 'key': 0})
                elif action == 'clear-hover':
                    plans.append({'message': 0x02A3, 'wparam': 0, 'lparam': 0, 'key': 0})
                else:
                    scrolls = value['compiled']['scroll_regions']
                    require(len(scrolls) == 1, 'Production fixture has ambiguous scroll ownership')
                    key, x0, y0, x1, y1 = scrolls[0]
                    logical = [(x0 + x1) / 2, y1 - 6]
                    # Find a genuinely empty panel point, rather than use a button's wheel owner.
                    require(not any(hit[1] <= logical[0] < hit[3] and hit[2] <= logical[1] < hit[4] for hit in hits),
                            'Wheel fixture does not hit empty ScrollPanel space')
                    region = [key, logical[0] - 2, logical[1] - 2, logical[0] + 2, logical[1] + 2]
                    client, logical = point(width, height, region)
                    plans.append(mouse_plan(0x020A, key, client, logical, handle, -120 if action == 'wheel-down' else 120))
                row = {'sequence': 1, 'batch': batch, 'generation': generation, 'hwnd': handle, 'owner_thread': tid,
                       'client': [width, height], 'action': action, 'planned_inputs': plans,
                       'snapshot': value['row']['snapshot'], 'manifest': value['row']['manifest'], 'native_events': [], 'stale_events': []}
                if action.startswith('wheel-'): row['scroll_targets_before'] = value['state']['scrollTargets']
                report['batches'].append(row); batches[batch] = row
                for plan in plans: post(handle, plan)
                checkpoint()
                acknowledge(f'STEP|1|{batch}')
            elif signal.startswith('UI_PRODUCTION_WINDOW_EVENT='):
                seq, batch, kind, key, vk = map(int, fields[:5])
                require(seq == 1 and batch in batches, 'Production input event lacks its owned batch')
                batches[batch]['native_events'].append({'kind': kind, 'key': key, 'virtual_key': vk, 'delta': float(fields[5]), 'generation': int(fields[6])})
            elif signal.startswith('UI_PRODUCTION_WINDOW_STALE='):
                seq, batch, kind, key, old, current, vk = map(int, fields)
                require(seq == 1 and batch in batches and old < current, 'Invalid old-scene native rejection')
                batches[batch]['stale_events'].append({'kind': kind, 'key': key, 'old_generation': old, 'generation': current, 'virtual_key': vk})
            elif signal.startswith('UI_PRODUCTION_WINDOW_BATCH='):
                seq, batch, count, accepted, stale, active, generation = map(int, fields)
                require(seq == 1 and batch in batches and 'completion' not in batches[batch], 'Invalid duplicate production batch completion')
                batches[batch]['completion'] = {'event_count': count, 'accepted_total': accepted, 'stale_total': stale,
                                               'active': bool(active), 'generation': generation}
                checkpoint()
            elif signal.startswith('UI_PRODUCTION_WINDOW_CLOSED='):
                seq, handle, generation = map(int, fields)
                require(seq == 1 and len(batches) == len(actions) and generation == last_revision + 1 and
                        owned_window[0] == handle and not report['updates'][-1]['active'], 'Production did not reach its exact closed scene')
                check_window(handle, owned_window[1])
                plans = [dict(batches[len(actions)]['planned_inputs'][0]),
                         dict(batches[5]['planned_inputs'][0]), {'message': 0x0100, 'wparam': 27, 'lparam': 0, 'key': 0}]
                for plan in plans: post(handle, plan)
                report['closed_input_plan'] = plans
                checkpoint()
                acknowledge('CLOSED_INPUTS|1')
            elif signal.startswith('UI_PRODUCTION_WINDOW_CLOSED_EVENT='):
                seq, kind, key, vk = map(int, fields[:4])
                require(seq == 1, 'Invalid closed production event')
                report.setdefault('closed_events', []).append({'kind': kind, 'key': key, 'virtual_key': vk,
                    'delta': float(fields[4]), 'generation': int(fields[5]), 'consumed': bool(int(fields[6]))})
            elif signal.startswith('UI_PRODUCTION_WINDOW_COMPLETE='):
                seq, count, delivered, accepted, stale, closed_count, closed_accepted, generation = map(int, fields[:8])
                require(seq == 1 and count == len(actions) and report['completion'] is None and closed_count == 1 and
                        closed_accepted == 0 and generation == last_revision + 1 and fields[8] == 'owner-thread', 'Invalid live production completion')
                report['completion'] = {'batch_count': count, 'delivered': delivered, 'accepted': accepted, 'stale': stale,
                    'closed_input_count': closed_count, 'closed_accepted': closed_accepted, 'generation': generation}
                checkpoint()
        process.wait(timeout=max(1, deadline - time.monotonic()))
        require(not reader_errors and process.returncode == 0 and report['completion'] is not None and
                set(refreshes) == set(range(1, last_revision + 1)) and len(frames) == last_revision + 2,
                'Live production child, frames or scene updates did not complete')
        report['status'] = 'LIVE_SDK_PRODUCTION_INTERACTIONS_PASS'
    except Exception as error:
        timed_out = isinstance(error, (TimeoutError, subprocess.TimeoutExpired)) or time.monotonic() >= deadline
        report.update(status='LIVE_SDK_PRODUCTION_INTERACTIONS_FAILED', error=str(error))
        if process.stdin and not process.stdin.closed: process.stdin.close()
        if process.poll() is None:
            try:
                process.wait(timeout=5); report['cleanup'] = 'owned_child_exited_after_input_eof'
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    process.wait(timeout=5); report['cleanup'] = 'terminated_owned_pid'
                except subprocess.TimeoutExpired:
                    process.kill(); process.wait(timeout=5); report['cleanup'] = 'killed_owned_pid'
    finally:
        if process.stdin and not process.stdin.closed: process.stdin.close()
        for thread in threads:
            if thread.ident is not None: thread.join(timeout=5)
        if any(thread.is_alive() for thread in threads): report.update(status='LIVE_SDK_PRODUCTION_INTERACTIONS_FAILED', error='Owned reader remained live')
        report.update(returncode=process.returncode, timed_out=timed_out)
        checkpoint()
    return bytes(channels['stdout']), bytes(channels['stderr']), timed_out, report
