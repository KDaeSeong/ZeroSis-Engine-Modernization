"""Drive only a freshly launched owned SDK host's hidden presentation HWND.

The official UI VM remains live. Prepare its captured state, then post bounded
test messages to a HWND whose process ID is verified against that owned child.
"""
from __future__ import annotations
import ctypes
from ctypes import wintypes
import json
import math
from pathlib import Path
import queue
import sqlite3
import subprocess
import sys
import threading
import time

from civ5_ui_assets import require, sha256
from render_ui_popup import artifact, png_pixels, portrait_readback


def selected_hit_client_point(hits, key, width, height):
    """Find an integer client pixel owned by this hit after child occlusion."""
    matches = [hit for hit in hits if hit[0] == key]
    require(len(matches) == 1 and len(matches[0]) == 5,
            'Selected control has no unique clipped hit region')
    _, x0, y0, x1, y1 = matches[0]
    require(0 <= x0 < x1 <= 1920 and 0 <= y0 < y1 <= 1080,
            'Selected hit is outside its retained scene')
    require(type(width) is int and type(height) is int and 0 < width <= 1920 and 0 < height <= 1080,
            'Invalid selected fixture client dimensions')
    scale = min(width / 1920, height / 1080)
    dx, dy = (width - 1920 * scale) / 2, (height - 1080 * scale) / 2
    center = [round(dx + (x0+x1)*scale/2), round(dy + (y0+y1)*scale/2)]

    def owned_pixel(x, y):
        logical = [(x-dx)/scale, (y-dy)/scale]
        if not (0 <= x < width and 0 <= y < height and
                x0 <= logical[0] < x1 and y0 <= logical[1] < y1):
            return None
        top = next((hit for hit in reversed(hits)
                    if hit[1] <= logical[0] < hit[3] and hit[2] <= logical[1] < hit[4]), None)
        return logical if top is not None and top[0] == key else None

    logical = owned_pixel(*center)
    if logical is not None:
        return matches[0], center, logical
    # Higher hit rectangle edges partition the selected area into cells with a
    # constant topmost callback. Test one client pixel from each nonempty cell.
    lo_x, hi_x = max(0, math.ceil(dx+x0*scale)), min(width, math.ceil(dx+x1*scale))
    lo_y, hi_y = max(0, math.ceil(dy+y0*scale)), min(height, math.ceil(dy+y1*scale))
    require(lo_x < hi_x and lo_y < hi_y, 'Selected hit has no client pixel')
    cuts_x, cuts_y = {lo_x, hi_x}, {lo_y, hi_y}
    for hit in hits[hits.index(matches[0])+1:]:
        if hit[1] < x1 and x0 < hit[3] and hit[2] < y1 and y0 < hit[4]:
            cuts_x.update(max(lo_x, min(hi_x, math.ceil(dx+edge*scale))) for edge in (hit[1], hit[3]))
            cuts_y.update(max(lo_y, min(hi_y, math.ceil(dy+edge*scale))) for edge in (hit[2], hit[4]))
    def representatives(cuts, preferred):
        edges = sorted(cuts)
        values = [max(a, min(b-1, preferred)) for a, b in zip(edges, edges[1:]) if a < b]
        return sorted(values, key=lambda value: (abs(value-preferred), value))
    for y in representatives(cuts_y, center[1]):
        for x in representatives(cuts_x, center[0]):
            logical = owned_pixel(x, y)
            if logical is not None:
                return matches[0], [x, y], logical
    raise ValueError('Selected control has no unoccluded client pixel')


def collect_live_window(process, directory, evidence, timeout, frozen_tools, *, display_resize=False, refresh_closed=False,
                        production_fixture=False,research_fixture=False):
    require(type(research_fixture) is bool and not (production_fixture and research_fixture), 'Conflicting selected popup fixtures')
    selected_fixture=production_fixture or research_fixture
    require(type(refresh_closed) is bool and (not refresh_closed or display_resize),
            'Closed scene refresh requires the explicit GPU display profile')
    require(type(production_fixture) is bool and (not selected_fixture or refresh_closed),
            'Production button fixture requires the GPU closed refresh profile')
    sequences = (1,) if selected_fixture else (1, 2)
    context = 'research' if research_fixture else 'production' if selected_fixture else 'ranking'
    directory = Path(directory).resolve(strict=True)
    evidence = Path(evidence)
    channels = {name: bytearray() for name in ('stdout', 'stderr')}
    signals = queue.Queue()
    errors = []
    report = {'status': 'LIVE_UI_WINDOW_PENDING', 'pid': process.pid,
              'scope': 'actual_live_SDK_research_VM_and_owned_GPU_HWND_selected_tech_hit_and_closed_refresh' if research_fixture else
                       'actual_live_SDK_production_VM_and_owned_GPU_HWND_selected_unit_hit_and_closed_refresh' if production_fixture else
                       'actual_live_SDK_UI_VM_and_owned_GPU_HWND_closed_scene_refresh_with_posted_test_input' if refresh_closed else
                       'actual_live_SDK_UI_VM_and_owned_GPU_HWND_display_resize_with_posted_test_input' if display_resize else
                       'actual_live_SDK_UI_VM_and_owned_hidden_HWND_with_posted_test_input',
              'display_resize_enabled': display_resize,
              'refresh_closed_enabled': refresh_closed,
              'production_fixture_enabled': production_fixture,
              'research_fixture_enabled':research_fixture,
              'real_user_click_verified': False, 'installed_game_launched': False,
              'scenes': [], 'refresh_scenes': [], 'windows': [], 'frames': [], 'error': None, 'cleanup': None}
    report_path = evidence / 'ui_window.json'

    def checkpoint():
        tmp = report_path.with_suffix('.json.tmp')
        tmp.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        tmp.replace(report_path)

    def read(name, stream):
        try:
            while True:
                line = stream.readline(1024 * 1024)
                if not line:
                    break
                if len(channels[name]) + len(line) > 32 * 1024 * 1024:
                    raise ValueError('Owned host diagnostic stream exceeds its bound')
                channels[name] += line
                if name == 'stdout' and line.startswith(b'UI_WINDOW_'):
                    signals.put(line.decode('utf-8', errors='strict').strip())
        except Exception as error:
            errors.append(str(error))
            signals.put('READER_ERROR')
        finally:
            if name == 'stdout':
                signals.put('STDOUT_EOF')

    threads = [threading.Thread(target=read, args=(name, getattr(process, name)), daemon=True)
               for name in channels]
    deadline = time.monotonic() + timeout
    timed_out = False
    prepared, ready, complete, frames, contexts, refreshed, refresh_ready, expected_controls = {}, {}, {}, {}, {}, {}, {}, {}
    def expected_turn(seq):
        return 0 if selected_fixture else seq * 25
    try:
        if display_resize:
            from ui_window_frame import verify_frame, verify_closed_frame
        for thread in threads:
            thread.start()
        checkpoint()
        user32 = ctypes.WinDLL('user32', use_last_error=True)
        user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        user32.PostMessageW.restype = wintypes.BOOL
        user32.IsWindowVisible.argtypes = [wintypes.HWND]
        user32.IsWindowVisible.restype = wintypes.BOOL
        user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        user32.GetClientRect.restype = wintypes.BOOL
        while True:
            left = deadline - time.monotonic()
            if left <= 0:
                timed_out = True
                raise TimeoutError('Owned live UI host exceeded its execution deadline')
            try:
                signal = signals.get(timeout=min(left, 0.25))
            except queue.Empty:
                continue
            if signal == 'STDOUT_EOF':
                break
            if signal == 'READER_ERROR':
                raise ValueError('; '.join(errors))
            if signal.startswith('UI_WINDOW_EXPECTED_CONTROL='):
                require(selected_fixture, 'Unexpected production selected-control declaration')
                seq, key, city, unit = map(int, signal.split('=', 1)[1].split('|'))
                require(seq == 1 and seq not in expected_controls and key > 0 and city >= 0 and unit >= 0,
                        'Invalid or duplicate official production control selection')
                expected_controls[seq] = ({'key':key,'player_id':city,'tech_id':unit} if research_fixture else {'key':key,'city_id':city,'unit_id':unit})
            elif signal.startswith('UI_WINDOW_SCENE_REQUEST='):
                seq, turn, raw_path = signal.split('=', 1)[1].split('|', 2)
                seq, turn = int(seq), int(turn)
                require(seq in sequences and turn == expected_turn(seq) and seq not in prepared and
                        (not selected_fixture or seq in expected_controls),
                        'Unexpected or duplicate live SDK presentation request')
                snapshot = Path(raw_path).resolve(strict=True)
                phase = 'window' if selected_fixture else 'shown'
                require(snapshot.is_relative_to(directory) and snapshot.name == f'ui-popup-{seq}-{phase}.json',
                        'Live SDK snapshot escaped the owned child runtime')
                initial_hash = sha256(snapshot)
                scene_dir = snapshot.parent / f'presentation-popup-{seq}'
                require(scene_dir.resolve().is_relative_to(directory) and not scene_dir.exists(),
                        'Refusing to reuse a live presentation directory')
                scene_dir.mkdir()
                database = snapshot.parent / 'rules.db'
                require(database.resolve().is_relative_to(directory), 'Live color DB escaped owned runtime')
                db_before = artifact(database)
                with sqlite3.connect(database.resolve().as_uri() + '?mode=ro', uri=True) as connection:
                    rows = connection.execute('SELECT Type, Red, Green, Blue, Alpha FROM Colors WHERE Type LIKE ?',
                                              ('COLOR_%',)).fetchall()
                colors = {row[0]: list(row[1:]) for row in rows}
                require(len(colors) == len(rows), 'Duplicate original live database color key')
                (scene_dir / 'inline_colors.json').write_text(json.dumps({'database': db_before, 'colors': colors},
                                                                        ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
                if selected_fixture:
                    icons = Path(frozen_tools) / 'inline_icons.json'
                    require(icons.is_file(), 'Frozen production FontIcons catalog is missing')
                    (scene_dir / 'inline_icons.json').write_bytes(icons.read_bytes())
                    require(sha256(icons) == sha256(scene_dir / 'inline_icons.json'),
                            'Production FontIcons catalog changed while copying')
                manifest = scene_dir / 'scene_manifest.json'
                command = [sys.executable, '-B', '-X', 'utf8', str(Path(frozen_tools) / 'render_ui_popup.py'),
                           '--prepare', str(snapshot), '--directory', str(scene_dir), '--manifest', str(manifest)]
                if selected_fixture:command += ['--context',context]
                child = subprocess.run(command, cwd=directory, capture_output=True, timeout=min(60, left),
                                       creationflags=subprocess.CREATE_NO_WINDOW)
                log = evidence / f'ui_window_prepare_{seq}.log'
                log.write_bytes(child.stdout + child.stderr)
                require(child.returncode == 0, 'Live popup scene preparation failed: ' + str(log))
                require(sha256(snapshot) == initial_hash and sha256(database) == db_before['sha256'],
                        'Preparing pixels changed actual SDK UI state/database')
                compiled = json.loads(manifest.read_text(encoding='utf-8'))
                require(compiled['snapshot']['sha256'] == initial_hash and compiled['snapshot_state_unchanged'] is True,
                        'Compiled scene lost actual shown-state binding')
                row = {'sequence': seq, 'turn': turn, 'snapshot': artifact(snapshot),
                       'database': db_before, 'manifest': artifact(manifest), 'prepare_log': artifact(log),
                       'prepare_command': command, 'packet': compiled['packet'],
                       'retained_runtime_bounds_check': compiled['retained_runtime_bounds_check']}
                report['scenes'].append(row)
                prepared[seq] = (snapshot, scene_dir, compiled, row)
                checkpoint()
                process.stdin.write(f'READY|{seq}\n'.encode('ascii'))
                process.stdin.flush()
            elif signal.startswith('UI_WINDOW_REFRESH_REQUEST='):
                require(refresh_closed, 'Unexpected closed scene refresh request')
                seq, turn, raw_path = signal.split('=', 1)[1].split('|', 2)
                seq, turn = int(seq), int(turn)
                require(seq in ready and seq not in complete and seq not in refreshed and turn == expected_turn(seq),
                        'Unexpected/duplicate closed scene refresh sequence')
                snapshot = Path(raw_path).resolve(strict=True)
                shown, original_dir, original_compiled, original_row = prepared[seq]
                require(snapshot == (shown.parent / f'ui-popup-{seq}-closed.json').resolve(strict=True) and
                        snapshot.is_relative_to(directory), 'Closed scene escaped the exact owned SDK session')
                initial_hash = sha256(snapshot)
                closed = json.loads(snapshot.read_text(encoding='utf-8'))
                old = json.loads(shown.read_text(encoding='utf-8'))
                require(closed.get('active') is False and closed.get('timerSemaphore') == 0 and
                        closed.get('tree') == old.get('tree') and closed.get('draws') == old.get('draws'),
                        'The official callback did not preserve and deactivate its retained popup')
                scene_dir = snapshot.parent / f'presentation-popup-{seq}-closed'
                require(scene_dir.resolve().is_relative_to(directory) and not scene_dir.exists(),
                        'Refusing to reuse a closed scene presentation directory')
                scene_dir.mkdir()
                colors = original_dir / 'inline_colors.json'
                (scene_dir / 'inline_colors.json').write_bytes(colors.read_bytes())
                require(sha256(scene_dir / 'inline_colors.json') == sha256(colors), 'Closed scene color input changed')
                if selected_fixture:
                    icons = original_dir / 'inline_icons.json'
                    (scene_dir / 'inline_icons.json').write_bytes(icons.read_bytes())
                    require(sha256(scene_dir / 'inline_icons.json') == sha256(icons), 'Closed scene icon input changed')
                manifest = scene_dir / 'scene_manifest.json'
                command = [sys.executable, '-B', '-X', 'utf8', str(Path(frozen_tools) / 'render_ui_popup.py'),
                           '--prepare', str(snapshot), '--directory', str(scene_dir), '--manifest', str(manifest),
                           '--closed']
                if selected_fixture:command += ['--context',context]
                child = subprocess.run(command, cwd=directory, capture_output=True, timeout=min(60, left),
                                       creationflags=subprocess.CREATE_NO_WINDOW)
                log = evidence / f'ui_window_refresh_prepare_{seq}.log'
                log.write_bytes(child.stdout + child.stderr)
                require(child.returncode == 0, 'Closed SDK scene preparation failed: ' + str(log))
                require(sha256(snapshot) == initial_hash and sha256(Path(original_row['database']['path'])) == original_row['database']['sha256'],
                        'Closed scene preparation changed captured SDK state or rules DB')
                compiled = json.loads(manifest.read_text(encoding='utf-8'))
                require(compiled.get('status') == 'ACTUAL_SDK_CLOSED_POPUP_EMPTY_SCENE_COMPILED' and
                        compiled.get('closed_context_not_drawn') is True and
                        compiled.get('snapshot_state_unchanged') is True and compiled['snapshot']['sha256'] == initial_hash and
                        compiled.get('hit_regions') == [] and compiled.get('sprite_count') == 0 and compiled.get('texture_count') == 0,
                        'Closed scene did not compile an empty contribution from its exact official snapshot')
                row = {'sequence': seq, 'turn': turn, 'snapshot': artifact(snapshot),
                       'manifest': artifact(manifest), 'prepare_log': artifact(log), 'prepare_command': command,
                       'packet': compiled['packet'], 'source_shown_snapshot': original_row['snapshot'],
                       'closed_context_not_drawn': True}
                report['refresh_scenes'].append(row)
                refreshed[seq] = (snapshot, scene_dir, compiled, row)
                checkpoint()
                process.stdin.write(f'REFRESH|{seq}\n'.encode('ascii'))
                process.stdin.flush()
            elif signal.startswith('UI_WINDOW_DISPLAY_CONTEXT='):
                require(display_resize, 'Unexpected display context in a hidden-only presentation profile')
                seq, session, station, desktop = signal.split('=', 1)[1].split('|')
                seq, session = int(seq), int(session)
                require(seq in prepared and seq not in contexts and station and desktop and session >= 0,
                        'Invalid owned display context')
                contexts[seq] = {'session_id': session, 'window_station': station, 'thread_desktop': desktop}
            elif signal.startswith('UI_WINDOW_FRAME='):
                require(display_resize, 'Unexpected GPU frame in a hidden-only presentation profile')
                fields = signal.split('=', 1)[1].split('|', 12)
                require(len(fields) == 13, 'Malformed owned GPU frame metadata')
                seq, phase, handle, tid, width, height, rendered, presented, hr, device, occluded, visible, raw_path = fields
                seq, handle, tid, width, height, rendered, presented, hr, occluded, visible = map(
                    int, (seq, handle, tid, width, height, rendered, presented, hr, occluded, visible))
                require(seq in prepared and seq in contexts and phase in ('initial', 'resized', 'closed') and
                        ((phase != 'closed' and seq not in ready) or
                         (phase == 'closed' and refresh_closed and seq in refreshed and seq in ready and seq not in complete)) and
                        (seq, phase) not in frames, 'Duplicate/out-of-order owned GPU capture')
                require((width, height) == ((1000, 700) if phase == 'initial' else (900, 600)) and
                        rendered > 0 and presented == rendered and hr in (0, 0x087A0001) and device in ('hardware', 'warp') and
                        occluded == int(hr == 0x087A0001) and visible == 1, 'GPU capture is not a valid owned surface/Present result')
                require((phase == 'initial') == ((seq, 'initial') not in frames), 'GPU resize preceded the initial frame')
                owner_pid = wintypes.DWORD()
                actual_tid = user32.GetWindowThreadProcessId(wintypes.HWND(handle), ctypes.byref(owner_pid))
                require(owner_pid.value == process.pid and actual_tid == tid and
                        bool(user32.IsWindowVisible(wintypes.HWND(handle))), 'GPU capture HWND is not the exact visible owned child')
                snapshot, scene_dir, compiled, scene_row = refreshed[seq] if phase == 'closed' else prepared[seq]
                capture = Path(raw_path).resolve(strict=True)
                require(capture == (scene_dir / f'frame-{phase}.png').resolve(strict=True),
                        'GPU capture escaped the exact owned scene path')
                frame = {'sequence': seq, 'phase': phase, 'hwnd': handle, 'pid': process.pid, 'owner_thread': tid,
                         'client': [width, height], 'render_count': rendered, 'present_count': presented,
                         'present_hresult': hr, 'device_kind': device, 'present_occluded': bool(occluded),
                         'native_visible': bool(visible), 'parent_visible': True, 'png': artifact(capture),
                         'desktop_context': contexts[seq], 'desktop_pixels_verified': False}
                frames[seq, phase] = frame
                report['frames'].append(frame)
                checkpoint()
            elif signal.startswith('UI_WINDOW_READY='):
                values = [int(v) for v in signal.split('=', 1)[1].split('|')]
                require(len(values) == 5, 'Invalid live UI window identity')
                seq, handle, tid, width, height = values
                require(seq in prepared and seq not in ready and handle > 0 and width > 0 and height > 0,
                        'Unexpected live window creation')
                owner_pid = wintypes.DWORD()
                actual_tid = user32.GetWindowThreadProcessId(wintypes.HWND(handle), ctypes.byref(owner_pid))
                require(owner_pid.value == process.pid and actual_tid == tid,
                        'Refusing to post input to a window not owned by this exact SDK child')
                actual_client = wintypes.RECT()
                require(bool(user32.GetClientRect(wintypes.HWND(handle), ctypes.byref(actual_client))) and
                        [actual_client.right, actual_client.bottom] == [width, height], 'Native/parent HWND client sizes differ')
                snapshot, scene_dir, compiled, row = prepared[seq]
                png = scene_dir / 'popup.png'
                row['png'] = artifact(png)
                if not selected_fixture:
                    row['portrait_readback'] = portrait_readback(
                        json.loads(snapshot.read_text(encoding='utf-8')), compiled, png_pixels(png))
                if display_resize:
                    require([width, height] == [900, 600] and bool(user32.IsWindowVisible(wintypes.HWND(handle))) and
                            (seq, 'initial') in frames and (seq, 'resized') in frames,
                            'Display/resize did not provide both captures before input')
                    previous = None
                    for phase in ('initial', 'resized'):
                        frame = frames[seq, phase]
                        require(frame['hwnd'] == handle and frame['owner_thread'] == tid,
                                'GPU capture identity differs from its input HWND')
                        if previous:
                            require(frame['device_kind'] == previous['device_kind'] and
                                    frame['render_count'] > previous['render_count'] and
                                    frame['present_count'] > previous['present_count'], 'GPU resize lost device/counter continuity')
                        frame['pixel_check'] = verify_frame(png, Path(frame['png']['path']), *frame['client'])
                        previous = frame
                require(sha256(snapshot) == row['snapshot']['sha256'], 'Native rendering changed captured SDK UI state')
                window = {'sequence': seq, 'hwnd': handle, 'pid': owner_pid.value, 'owner_thread': tid,
                          'client': [width, height], 'synthetic_messages_posted': True,
                          'input_policy': 'Actual selected technology hit then late Escape' if research_fixture else 'Actual selected unit hit then late Escape' if production_fixture else
                                          'Escape then late Return' if seq == 1 else 'CloseButton click then late Escape'}
                report['windows'].append(window)
                ready[seq] = window
                checkpoint()

                def post(message, wparam, lparam):
                    require(bool(user32.PostMessageW(wintypes.HWND(handle), message, wparam, lparam)),
                            'Posting to owned UI test HWND failed')

                # Ignored key and a letterbox click must not reach a callback.
                post(0x0100, 0x70, 0)  # F1
                post(0x0201, 1, 0)  # top-left, outside displayed scene
                if selected_fixture:
                    selected = expected_controls[seq]
                    hit, point, logical = selected_hit_client_point(compiled['hit_regions'], selected['key'], width, height)
                    x, y = point
                    window.update(selected_control=selected, selected_hit=hit, posted_click_client=point,
                                  posted_click_logical=logical,
                                  selected_point_policy='SELECTED_TOPMOST_VISIBLE_CLIENT_PIXEL_V1')
                    post(0x0201, 1, (y << 16) | x)
                    post(0x0100, 27, 0)
                elif seq == 1:
                    post(0x0100, 27, 0)
                    post(0x0100, 27, 1 << 30)  # native repeat filtering
                    post(0x0100, 13, 0)  # stale input after official close
                else:
                    hits = compiled['hit_regions']
                    require(hits == [[12, 745.0, 804.0, 895.0, 836.0]], 'Actual CloseButton hit area differs')
                    scale = min(width / 1920, height / 1080)
                    x = round((width - 1920 * scale) / 2 + 820 * scale)
                    y = round((height - 1080 * scale) / 2 + 820 * scale)
                    require(0 <= x < width and 0 <= y < height, 'CloseButton test point escaped owned client')
                    window['posted_click_client'] = [x, y]
                    post(0x0201, 1, (y << 16) | x)
                    post(0x0100, 27, 0)
                checkpoint()
                process.stdin.write(f'INPUTS|{seq}\n'.encode('ascii'))
                process.stdin.flush()
            elif signal.startswith('UI_WINDOW_REFRESH_DEVICE='):
                require(refresh_closed, 'Unexpected refreshed device identity')
                seq, before, after = map(int, signal.split('=', 1)[1].split('|'))
                require(seq in ready and seq in refreshed and seq not in refresh_ready and
                        (seq, 'closed') in frames and 0 < before == after < (1 << 64) and
                        'refresh_device_identity_before' not in ready[seq], 'GPU refresh changed or omitted its owned device identity')
                ready[seq].update(refresh_device_identity_before=before, refresh_device_identity_after=after)
            elif signal.startswith('UI_WINDOW_REFRESH_READY='):
                require(refresh_closed, 'Unexpected refreshed scene ready marker')
                fields = signal.split('=', 1)[1].split('|', 7)
                require(len(fields) == 8, 'Malformed refreshed scene metadata')
                seq, handle, tid, before, after, width, height = map(int, fields[:7])
                require(seq in refreshed and seq in ready and seq not in refresh_ready and seq not in complete and
                        before == 1 and after == 2 and [width, height] == [900, 600] and
                        (seq, 'closed') in frames, 'Invalid scene generation/closed frame sequence')
                window = ready[seq]
                require(window.get('refresh_device_identity_before', 0) == window.get('refresh_device_identity_after') and
                        window.get('refresh_device_identity_before', 0) > 0, 'Refreshed client omits its exact owned GPU device identity')
                require((handle, tid) == (window['hwnd'], window['owner_thread']), 'Refresh replaced its owned HWND/thread')
                owner_pid = wintypes.DWORD()
                actual_tid = user32.GetWindowThreadProcessId(wintypes.HWND(handle), ctypes.byref(owner_pid))
                actual_client = wintypes.RECT()
                require(owner_pid.value == process.pid and actual_tid == tid and
                        bool(user32.IsWindowVisible(wintypes.HWND(handle))) and
                        bool(user32.GetClientRect(wintypes.HWND(handle), ctypes.byref(actual_client))) and
                        [actual_client.right, actual_client.bottom] == [width, height],
                        'Refreshed GPU frame does not belong to the same visible owned client')
                snapshot, scene_dir, compiled, row = refreshed[seq]
                png = Path(fields[7]).resolve(strict=True)
                require(png == (scene_dir / 'popup.png').resolve(strict=True), 'Refreshed source PNG escaped its exact scene')
                row['png'] = artifact(png)
                frame = frames[seq, 'closed']
                previous = frames[seq, 'resized']
                require(frame['hwnd'] == handle and frame['owner_thread'] == tid and
                        frame['device_kind'] == previous['device_kind'] and
                        frame['render_count'] > previous['render_count'] and frame['present_count'] > previous['present_count'],
                        'Scene replacement lost device/window/counter continuity')
                frame['pixel_check'] = verify_closed_frame(png, Path(frame['png']['path']), width, height)
                require(sha256(snapshot) == row['snapshot']['sha256'], 'Native scene replacement changed official closed UI state')
                window.update(scene_generation_before=before, scene_generation_after=after,
                              refresh_input_policy='old selected technology hit then rejected Escape' if research_fixture else 'old selected unit hit then rejected Escape' if production_fixture else
                                                   'old CloseButton click then rejected Escape',
                              refresh_client=[width, height])
                refresh_ready[seq] = True
                scale = min(width / 1920, height / 1080)
                if selected_fixture:
                    x, y = window['posted_click_client']
                else:
                    x = round((width - 1920 * scale) / 2 + 820 * scale)
                    y = round((height - 1080 * scale) / 2 + 820 * scale)
                window['refresh_posted_click_client'] = [x, y]
                require(bool(user32.PostMessageW(wintypes.HWND(handle), 0x0201, 1, (y << 16) | x)) and
                        bool(user32.PostMessageW(wintypes.HWND(handle), 0x0100, 27, 0)),
                        'Posting the bounded closed-scene batch to the owned HWND failed')
                checkpoint()
                process.stdin.write(f'REFRESH_INPUTS|{seq}\n'.encode('ascii'))
                process.stdin.flush()
            elif signal.startswith('UI_WINDOW_REFRESH_COMPLETE='):
                require(refresh_closed, 'Unexpected refresh completion')
                seq, delivered, accepted, generation, owner = signal.split('=', 1)[1].split('|')
                seq, delivered, accepted, generation = map(int, (seq, delivered, accepted, generation))
                require(seq in refresh_ready and seq not in complete and not ready[seq].get('refresh_completed') and
                        delivered == 1 and accepted == 0 and generation == 2 and owner == 'owner-thread',
                        'Closed scene delivered an old control click or accepted input')
                ready[seq].update(refresh_delivered=delivered, refresh_accepted=accepted, refresh_completed=True)
                checkpoint()
            elif signal.startswith('UI_WINDOW_COMPLETE='):
                seq, delivered, accepted, owner = signal.split('=', 1)[1].split('|')
                seq = int(seq)
                require(seq in ready and seq not in complete and int(accepted) == 1 and
                        int(delivered) >= 1 and owner == 'owner-thread' and
                        (not refresh_closed or ready[seq].get('refresh_completed') is True), 'Invalid completed live window scope')
                complete[seq] = True
                ready[seq]['delivered'] = int(delivered)
                ready[seq]['accepted'] = int(accepted)
                ready[seq]['completed'] = True
                checkpoint()
        process.wait(timeout=max(1, deadline - time.monotonic()))
        require(not errors and process.returncode == 0 and set(complete) == set(sequences) and
                (not display_resize or set(frames) == {(seq, phase) for seq in sequences for phase in
                    (('initial', 'resized', 'closed') if refresh_closed else ('initial', 'resized'))}) and
                (not refresh_closed or set(refreshed) == set(refresh_ready) == set(sequences)),
                'Live SDK window sequence/process did not complete')
        report['status'] = 'LIVE_SDK_RESEARCH_WINDOW_POSTED_INPUT_PASS' if research_fixture else 'LIVE_SDK_UI_WINDOW_POSTED_INPUT_PASS'
    except Exception as error:
        report['status'] = 'LIVE_SDK_UI_WINDOW_FAILED'
        report['error'] = str(error)
        if isinstance(error, (TimeoutError, subprocess.TimeoutExpired)):
            timed_out = True
        if process.stdin and not process.stdin.closed:
            process.stdin.close()  # Let a blocked preparer read EOF and use normal host cleanup.
        if process.poll() is None:
            try:
                process.wait(timeout=5)
                report['cleanup'] = 'owned_child_exited_after_input_eof'
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    process.wait(timeout=5)
                    report['cleanup'] = 'terminated_owned_pid'
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
                    report['cleanup'] = 'killed_owned_pid'
    finally:
        if process.stdin and not process.stdin.closed:
            process.stdin.close()
        for thread in threads:
            if thread.ident is not None:
                thread.join(timeout=5)
        if any(thread.is_alive() for thread in threads):
            report.update(status='LIVE_SDK_UI_WINDOW_FAILED', error='Owned host output reader did not terminate')
        report.update(returncode=process.returncode, timed_out=timed_out)
        checkpoint()
    return bytes(channels['stdout']), bytes(channels['stderr']), timed_out, report
