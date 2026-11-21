"""Render retained actual-SDK popup states through the isolated native renderer.

Freezes selected Python/source UI inputs, not entire SDK or game asset packs.
Never loads GameCore, launches the installed game, or changes a native save.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import shutil
import sqlite3
import struct
import subprocess
import sys
import uuid
import zlib

from civ5_ui_assets import sha256, require, PACK_POLICY, header, rgba32
from ui_pixel_scene import (Compiler, top_panel_interaction_contract,
                            valid_leader_message, valid_unit_panel_lifecycle, positive, rect,
                            validate_social_policy_hover_gate, SCENE_CONTEXTS, owned_font_input_binding,
                            PRIVATE_MENU_CONTEXTS)

PROJECT = Path(__file__).resolve().parents[1]
GAME = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Sid Meier's Civilization V")
RENDERER_PROOF = '20261002T171317Z_516c7fa8b73e'
RUNTIME = {'en_US': '20261002T161323Z_422f18cf0e62', 'ko_KR': '20261002T155207Z_38c434218a11'}
OWNED = ['tools/render_ui_popup.py', 'tools/ui_pixel_scene.py', 'tools/civ5_ui_assets.py',
         'tools/ui_bitmap_fonts.py', 'Tests/ui_pixel_scene.py', 'Tests/top_panel_renderer.py',
         'Tests/trade_route_renderer.py', 'Tests/economic_overview_renderer.py', 'Tests/action_info_panel_renderer.py',
         'Tests/game_menu_renderer.py',
         'Tests/civ5_ui_assets.py', 'Tests/ui_bitmap_fonts.py']


def artifact(path):
    path = Path(path).resolve(strict=True)
    return {'path': str(path), 'sha256': sha256(path), 'bytes': path.stat().st_size}


def check_artifact(row):
    require(type(row) is dict and Path(row['path']).is_file() and sha256(row['path']) == row['sha256'], 'Artifact hash mismatch')


def freeze(path, destination):
    require(not destination.exists() and not destination.is_symlink(), 'Refusing to overwrite frozen input')
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(path, destination)
    require(sha256(path) == sha256(destination), 'Frozen source copy differs')
    return {'original_path': str(Path(path).resolve()), **artifact(destination)}


def runtime_binding(runtime, language, sdk_run, directory):
    """Bind locale/state to the sealed invocation and exact host/GameCore bytes."""
    root = (PROJECT / 'Build/NewGameRuntime' / sdk_run).resolve(strict=True)
    request_row = runtime['request']
    require(Path(request_row['path']).resolve() ==
            (PROJECT / 'evidence/save_restore' / sdk_run / 'request.json').resolve(),
            'Runtime request is not from the selected unique SDK run')
    check_artifact(request_row)
    request = json.loads(Path(request_row['path']).read_text(encoding='utf-8'))
    require(request['run_id'] == sdk_run and Path(request['cwd']).resolve() == root and
            request['command'] == [str(root / 'ZeroSisHost_x64.exe'),
                                   '--check-save-restore-ui-actions', language, '48'],
            'Retained popup locale/invocation differs from selected SDK execution')
    require(request['ui_popups_enabled'] is True and request['session_activation'] ==
            {'source': 'COMPILED_HOST_FIXED_CONFIGURATION', 'active_mods': []} and
            runtime['session_active_mods'] == [0, 0] and runtime['accepted_bundle_unchanged'] is True,
            'Retained popup profile/mod activation is not the accepted isolated fixture')
    frozen = {}
    for name in ('candidate_build', 'accepted_bundle', 'found_value_sdk_build'):
        check_artifact(request[name])
        frozen[name] = freeze(request[name]['path'], directory / (name + '.json'))
    require(Path(request['accepted_bundle']['path']).resolve() ==
            (PROJECT / 'evidence/host/bundle.json').resolve(), 'Unexpected accepted host bundle')
    host = json.loads(Path(request['candidate_build']['path']).read_text(encoding='utf-8'))
    sdk = json.loads(Path(request['found_value_sdk_build']['path']).read_text(encoding='utf-8'))
    require(sdk['status'] == 'FOUND_VALUE_SHARED_SDK_CANDIDATE_LINKED' and sdk['inputs_unchanged'] is True,
            'Selected SDK input is not the sealed shared-FoundValue build')
    check_artifact(host['executable'])
    check_artifact(sdk['gamecore'])
    inputs = request['inputs']
    require(len({str(Path(row['path']).resolve()) for row in inputs}) == len(inputs),
            'Duplicate runtime input binding')
    for row in inputs:
        require(Path(row['path']).resolve().is_relative_to(root), 'Runtime input escaped its unique candidate')
        check_artifact(row)
    for basename, source in (('ZeroSisHost_x64.exe', host['executable']),
                             ('CvGameCoreDLL_Expansion2_x64.dll', sdk['gamecore'])):
        selected = [row for row in inputs if Path(row['path']).resolve() == root / basename]
        require(len(selected) == 1 and selected[0]['sha256'] == source['sha256'] and
                Path(selected[0]['source']).resolve() == Path(source['path']).resolve(),
                'Runtime executable bytes/source differ from sealed build: ' + basename)
    frozen['request'] = freeze(request_row['path'], directory / 'runtime_request.json')
    return {'language': language, 'command': request['command'], 'cwd': str(root),
            'active_mods': [], 'fixture_promotions_enabled': request['fixture_promotions_enabled'],
            'host': artifact(root / 'ZeroSisHost_x64.exe'),
            'gamecore': artifact(root / 'CvGameCoreDLL_Expansion2_x64.dll'),
            'inputs': inputs, 'frozen_proofs': frozen}


def retained_bounds(snapshot, geometry, *, context='ranking'):
    """Compare independently captured runtime bounds, excluding unmeasured controls."""
    actual = {row['key']: row for row in geometry if not row['style_decoration']}
    checked, deferred = [], []
    leader_controls_check = None

    def visit(node, parent_kind=None):
        if node['hidden']:
            return
        if node['kind'] == 'GridData':
            # Inline GridData is nine-slice source data consumed by its
            # owning GridButton; it has no independent runtime geometry.
            require(context in ('research', 'research-tree', 'diplomacy', 'unit-panel', 'social-policy', 'economic-overview', 'action-info-panel', 'game-menu', 'load-menu', 'menu-options') and parent_kind == 'GridButton' and
                    node['width'] == 0 and node['height'] == 0 and not node['children'],
                    'GridData is only valid as zero-area original GridButton draw data in a supported context')
            return
        key = node['key']
        require(key in actual, 'Visible retained control was omitted from the rendered scene: ' +
                str(key) + '/' + node['kind'] + '/' + node.get('id', ''))
        if node['kind'] in ('Label', 'TextButton', 'EditBox') or not node['width'] or not node['height']:
            deferred.append({'key': key, 'kind': node['kind'],
                             'reason': 'runtime label/style extent not measured'})
        else:
            expected = [node[name] for name in ('x', 'y', 'width', 'height')]
            require(all(abs(a - b) < 1e-5 for a, b in zip(expected, actual[key]['bounds'])),
                    'Scene geometry differs from actual retained runtime bounds: ' + str(key))
            checked.append({'key': key, 'kind': node['kind'], 'bounds': expected})
        if context in SCENE_CONTEXTS and node['kind'] == 'ShowOnMouseOver':
            hovered = node.get('hovered')
            require(type(hovered) is bool, 'ShowOnMouseOver lacks captured hover state during bounds verification')
            if not hovered:
                return
        if context == 'social-policy' and node['kind'] == 'HideOnMouseOver':
            hovered = node.get('hovered')
            require(type(hovered) is bool, 'HideOnMouseOver lacks captured hover state during bounds verification')
            if hovered:
                return
        for child in node['children']:
            visit(child, node['kind'])

    visit(snapshot['tree'])
    if context == 'ranking':
        require(any(row['key'] == 12 and row['kind'] == 'GridButton' for row in checked),
                'Actual CloseButton bounds were not independently checked')
    elif context == 'production':
        require(any(row['kind'] == 'GridButton' and row.get('id') == 'CloseButton' for row in actual.values()),
                'Production snapshot has no retained CloseButton')
    elif context == 'research':
        require(any(row['kind'] == 'GridButton' and row.get('id') == 'OpenTTButton'
                    for row in actual.values()), 'Research snapshot has no retained OpenTTButton')
    elif context == 'tech-award':
        targets = snapshot.get('inputTargets', [])
        require(type(targets) is list and
                sum(target.get('id') == 'ContinueButton' and target.get('event') == 'LeftClick'
                    for target in targets if type(target) is dict) == 1 and
                any(row['kind'] == 'GridButton' and row.get('id') == 'ContinueButton'
                    for row in actual.values()),
                'TechAward snapshot lacks its unique original ContinueButton callback and retained bounds')
    elif context == 'goody-hut-reward':
        targets = snapshot.get('inputTargets', [])
        close_rows = [row for row in actual.values() if row.get('id') == 'CloseButton']
        require(type(targets) is list and len(targets) == len(close_rows) == 1 and
                targets[0].get('id') == 'CloseButton' and targets[0].get('event') == 'LeftClick' and
                targets[0].get('key') == close_rows[0]['key'] and close_rows[0]['kind'] == 'GridButton' and
                tuple(close_rows[0]['bounds']) == (860, 675, 200, 36) and
                any(row['key'] == close_rows[0]['key'] and tuple(row['bounds']) == (860, 675, 200, 36)
                    for row in checked),
                'GoodyHutReward lacks its independently checked original outside-grid CloseButton bounds')
    elif context == 'city-capture':
        targets = snapshot.get('inputTargets', [])
        require(type(targets) is list and targets and all(type(target) is dict for target in targets) and
                all(target.get('event') == 'LeftClick' and target.get('id') != 'CloseButton'
                    for target in targets),
                'CityCapture snapshot lacks retained city-action callback targets')
    elif context == 'unit-panel':
        panel = snapshot.get('unitPanel')
        require(type(panel) is dict and panel.get('visible') is True and
                panel.get('contextHidden') is False and
                snapshot.get('hasRetainedUnitUi') is True,
                'UnitPanel lacks the retained selected-unit overlay contract')
        lifecycle = snapshot.get('lifecycle')
        require(valid_unit_panel_lifecycle(lifecycle, active=True) and
                snapshot.get('timerSemaphore') == 0,
                'UnitPanel must remain on its original queued, zero-timer world-overlay path')
        require(any(row['kind'] in ('Button', 'GridButton', 'TextButton') and
                    not row['style_decoration'] for row in actual.values()),
                'UnitPanel has no retained original action control geometry')
    elif context == 'city-view':
        targets = snapshot.get('inputTargets', [])
        require(type(targets) is list and
                sum(target.get('id') == 'ReturnToMapButton' and target.get('event') == 'LeftClick'
                    for target in targets if type(target) is dict) == 1 and
                any(row.get('kind') == 'GridButton' and row.get('id') == 'ReturnToMapButton'
                    for row in actual.values()),
                'CityView lacks its unique original ReturnToMapButton callback and retained bounds')
    elif context == 'top-panel':
        targets = snapshot.get('inputTargets', [])
        interaction = top_panel_interaction_contract(snapshot)
        science_geometry = any(row.get('kind') == 'TextButton' and row.get('id') == 'SciencePerTurn'
                               for row in actual.values())
        require(all(target.get('event') in ('LeftClick', 'ConsumeMouse') for target in targets
                    if type(target) is dict) and
                science_geometry is interaction['science_callback_available'],
                'TopPanel visible SciencePerTurn geometry differs from its original hidden-ancestor state')
    elif context == 'declare-war':
        targets = snapshot.get('inputTargets', [])
        required_ids = {'Button1', 'Button2'}
        stock_target_ids = required_ids | {'DiplomacyHeader', 'UnderProtectionOfHeader',
                                          'AlliedCityStatesHeader', 'ActiveDealsHeader',
                                          'TradeRoutesHeader'}
        require(type(targets) is list and
                required_ids <= {target.get('id') for target in targets if type(target) is dict and
                                 target.get('event') == 'LeftClick'} and
                all(target.get('event') == 'LeftClick' for target in targets if type(target) is dict) and
                all(target.get('id') in stock_target_ids for target in targets if type(target) is dict) and
                all(any(row.get('kind') == 'GridButton' and row.get('id') == button_id
                        for row in actual.values()) for button_id in required_ids),
                'DeclareWar callbacks differ from the original Yes/No and section-collapse controls')
        require(snapshot.get('hasRetainedPopupUi') is True and
                snapshot.get('contextName') == 'DeclareWarPopup' and
                snapshot.get('popupKind') == 'DeclareWar' and
                snapshot.get('timerSemaphore') == 1,
                'DeclareWar is not the retained original popup context')
    elif context == 'diplomacy':
        require(any(row['kind'] == 'GridButton' and row.get('id') == 'BackButton'
                    for row in actual.values()), 'Actual LeaderHead BackButton bounds were not independently checked')
        targets = snapshot.get('inputTargets', [])
        require(type(targets) is list and targets and
                sum(target.get('id') == 'BackButton' and target.get('event') == 'LeftClick'
                    for target in targets if type(target) is dict) == 1,
                'LeaderHead snapshot lacks its unique original BackButton callback target')

        def controls(node, found, parent_visible=True):
            if type(node) is dict:
                visible = parent_visible and node.get('hidden') is False
                if node.get('id') in ('LeaderSpeech', 'TitleText', 'MoodText', 'ThemSymbolShadow',
                                      'CivIconBG', 'CivIconShadow'):
                    require(node['id'] not in found, 'Duplicate original LeaderHead control')
                    found[node['id']] = (node, visible)
                for child in node.get('children', []):
                    controls(child, found, visible)
            return found

        captured = controls(snapshot.get('tree'), {})
        require(all(name in captured for name in ('LeaderSpeech', 'TitleText', 'MoodText',
                                                  'ThemSymbolShadow', 'CivIconBG', 'CivIconShadow')),
                'LeaderHead intro snapshot lacks its original text or civ-icon controls')
        required = {name: row[0] for name, row in captured.items()}
        require(all(captured[name][1] and isinstance(required[name].get('text'), str) and
                    required[name]['text'].strip()
                    for name in ('LeaderSpeech', 'TitleText', 'MoodText')),
                'LeaderHead intro snapshot lacks the visible nonempty leader speech/title/mood')
        # Original IconSupport.CivIconHookup(..., false, true) uses a complete
        # colored icon in CivIconBG for default player colors, hiding the two
        # composite layers. Non-default colors use all three layers instead.
        icon_names = ('CivIconBG', 'ThemSymbolShadow', 'CivIconShadow')
        visibility = tuple(captured[name][1] for name in icon_names)
        require(visibility in ((True, False, False), (True, True, True)),
                'LeaderHead civ icon is neither the original colored icon nor shadowed composite')
        visible_icons = [required[name] for name in icon_names if captured[name][1]]
        require(all(node.get('kind') == 'Image' and isinstance(node.get('texture'), str) and
                    node['texture'].strip() and node['key'] in actual and
                    actual[node['key']]['bounds'][2] > 0 and actual[node['key']]['bounds'][3] > 0
                    for node in visible_icons),
                'LeaderHead civ icon has no visible original textured geometry')
        leader_controls_check = {
            'civ_icon_mode': 'colored_icon' if visibility == (True, False, False) else 'shadowed_composite',
            'visible_civ_icon_controls': [node['id'] for node in visible_icons],
            'original_speech_title_mood_visible_nonempty': True,
        }
        message = snapshot.get('leaderMessage')
        require(valid_leader_message(message) and
                required['LeaderSpeech'].get('text') == message['text'] and
                snapshot.get('leaderRootUp') is True,
                'LeaderHead scene is not the original intro or exact human-declared-war response payload')
    elif context == 'action-info-panel':
        require(any(row['kind'] == 'GridButton' and row.get('id') == 'EndTurnButton' and
                    tuple(row['bounds']) == (1584, 844, 320, 36) for row in actual.values()),
                'ActionInfoPanel omitted its original 1920x1080 right/bottom button geometry')
    elif context == 'game-menu':
        require(any(row['kind'] == 'GridButton' and row.get('id') == 'ReturnButton' and
                    tuple(row['bounds']) == (800, 812.5, 320, 45) for row in actual.values()) and
                any(row['kind'] == 'Grid' and tuple(row['bounds']) == (718, 250.5, 484, 651)
                    for row in actual.values()),
                'GameMenu omitted its original centered frame or bottom ReturnButton geometry')
    elif context == 'exit-confirm':
        require(any(row['kind'] == 'Box' and row.get('id') == 'ExitConfirm' and
                    tuple(row['bounds']) == (0, 0, 1920, 1080) for row in actual.values()) and
                any(row['kind'] == 'Grid' and tuple(row['bounds']) == (710, 360, 500, 360)
                    for row in actual.values()) and
                all(sum(row['kind'] == 'GridButton' and row.get('id') == name and
                        tuple(row['bounds'])[2:] == (400, 42) for row in actual.values()) == 1
                    for name in ('Yes', 'No')),
                'ExitConfirm omitted its original modal shield, centered frame or Yes/No geometry')
    elif context == 'save-menu':
        expected_save_geometry = {
            ('GridButton', 'BackButton'): (519, 819, 150, 32),
            ('GridButton', 'SaveButton'): (1142, 806, 260, 45),
            ('ScrollPanel', 'ScrollPanel'): (902, 349, 495, 400),
            ('EditBox', 'NameBox'): (547, 470, 324, 22),
        }
        require(any(row['kind'] == 'Grid' and tuple(row['bounds']) == (480, 247, 960, 658)
                    for row in actual.values()) and
                all(any(row['kind'] == kind and row.get('id') == identifier and
                        tuple(row['bounds']) == bounds for row in actual.values())
                    for (kind, identifier), bounds in expected_save_geometry.items()),
                'SaveMenu omitted its original frame, save/back buttons, list viewport, or NameBox geometry')
    elif context == 'load-menu':
        menu = snapshot.get('loadMenu')
        expected_load_geometry = {
            ('GridButton', 'BackButton'): (519, 819, 150, 32),
            ('GridButton', 'StartButton'): (1142, 806, 260, 45),
            ('ScrollPanel', 'ScrollPanel'): (902, 377, 495, 400),
            ('PullDown', 'SortByPullDown'): (1002, 342, 290, 27),
            ('CheckBox', 'AutoCheck'): (1358, 302, 32, 32),
            ('CheckBox', 'CloudCheck'): (1093, 302, 32, 32),
        }
        require(type(menu) is dict and menu.get('sourceApisBound') is True and
                menu.get('controlOnly') is False and
                any(row['kind'] == 'Grid' and tuple(row['bounds']) == (480, 247, 960, 658)
                    for row in actual.values()) and
                all(any(row['kind'] == kind and row.get('id') == identifier and
                        tuple(row['bounds']) == bounds for row in actual.values())
                    for (kind, identifier), bounds in expected_load_geometry.items()),
                'LoadMenu omitted its complete original frontend frame, back/load controls, list/sort, or checkbox candidate geometry')
    elif context in PRIVATE_MENU_CONTEXTS:
        require(any(row['kind'] == 'Grid' and tuple(row['bounds']) == (480,247,960,658) for row in actual.values()),
                'Private menu omitted its original centered 960x658 frame')
        button_id = 'AcceptButton' if context == 'menu-options' else 'CloseButton' if context == 'touch-help' else 'SaveButton'
        require(sum(row['kind'] == 'GridButton' and row.get('id') == button_id for row in actual.values()) == 1,
                'Private menu omitted its unique original save/close control')
        if context == 'map-menu':
            require(sum(row['kind'] == 'EditBox' and row.get('id') == 'NameBox' and
                        tuple(row['bounds'])[2:] == (324,22) for row in actual.values()) == 1,
                    'Map menu NameBox lost its original 324x22 editing rectangle')
    elif context == 'notification-panel':
        panel_geometry = [row for row in actual.values()
                          if row.get('kind') == 'ScrollPanel' and row.get('id') == 'SmallScrollPanel']
        panel_bounds = panel_geometry[0]['bounds'] if panel_geometry else ()
        scroll_targets = [target for target in snapshot.get('scrollTargets', [])
                          if type(target) is dict and target.get('id') == 'SmallScrollPanel']
        viewport = snapshot.get('tree', {})
        overflow = (scroll_targets[0].get('maximumScroll', 0) > 0) if len(scroll_targets) == 1 else False
        source_scroll_offset = 20 if overflow else 0  # NotificationPanel.lua: ProcessStackSizes
        expected_x = viewport.get('x', 0) + viewport.get('width', 0) - 80 - source_scroll_offset
        require(len(panel_geometry) == len(scroll_targets) == 1 and len(panel_bounds) == 4 and
                panel_bounds[0] == expected_x and panel_bounds[2] == 80 and panel_bounds[3] > 0 and
                0 <= panel_bounds[1] < panel_bounds[1] + panel_bounds[3] <= 1080 and
                all(target.get('key') in actual and
                    tuple(actual[target['key']]['bounds']) == tuple(
                        target['bounds'][name] for name in ('x', 'y', 'width', 'height'))
                    for target in snapshot.get('inputTargets', [])),
                'NotificationPanel omitted its original right-edge scroll viewport or retained input geometry')
    else:
        require(any(row['kind'] == 'GridButton' and row.get('id') == 'CloseButton'
                    for row in actual.values()), 'ResearchTree snapshot has no retained CloseButton')
    return {'context': context, 'checked': checked, 'deferred': deferred,
            'leader_controls_check': leader_controls_check,
            'retail_layout_equivalence_verified': False}


def portrait_readback(snapshot, manifest, pixels):
    """Compare opaque interior atlas samples using the native linear sampler."""
    portraits = []

    def visit(node):
        if node['hidden']:
            return
        if node['kind'] == 'Image' and node.get('id') == 'Portrait':
            portraits.append(node)
        for child in node['children']:
            visit(child)

    visit(snapshot['tree'])
    require(len(portraits) == 2, 'Selected SDK popup needs two separately bound portrait controls')
    rows = []
    for node in portraits:
        name = node['texture'].replace('\\', '/').rsplit('/', 1)[-1].casefold()
        assets = [row for row in manifest['selected_assets'] if row['basename'] == name]
        require(len(assets) == 1, 'Portrait has no unique original atlas binding')
        check_artifact(assets[0]['output'])
        data = Path(assets[0]['output']['path']).read_bytes()
        words = header(data)
        rgba32(words)
        require((node['width'], node['height']) == (64, 64), 'Unexpected actual portrait size')
        colors, samples = set(), 0
        # The central 32x32 area is inside the portrait, away from frames,
        # neighboring civ icons, row separators and panel clipping edges.
        for y in range(math.ceil(node['y'] + 16), math.floor(node['y'] + 48)):
            for x in range(math.ceil(node['x'] + 16), math.floor(node['x'] + 48)):
                # BitmapRenderer uses linear interpolation. Account for the
                # half-pixel target anchor by sampling at pixel centers.
                sx = node['textureX'] + x - node['x']
                sy = node['textureY'] + y - node['y']
                ix, iy = math.floor(sx), math.floor(sy)
                fx, fy = sx - ix, sy - iy
                neighbors = []
                for dx, dy, weight in ((0, 0, (1-fx)*(1-fy)), (1, 0, fx*(1-fy)),
                                        (0, 1, (1-fx)*fy), (1, 1, fx*fy)):
                    if not weight:
                        continue
                    require(0 <= ix+dx < words[4] and 0 <= iy+dy < words[3],
                            'Portrait sample escaped original atlas')
                    offset = 128 + ((iy+dy) * words[4] + ix+dx) * 4
                    b, g, r, a = data[offset:offset + 4]
                    neighbors.append(((r, g, b, a), weight))
                if any(color[3] != 255 for color, _ in neighbors):
                    continue
                expected = tuple(math.floor(sum(color[c] * weight for color, weight in neighbors) + 0.5)
                                 for c in range(4))
                actual_offset = (y * 1920 + x) * 4
                require(all(abs(a-b) <= 1 for a, b in zip(pixels[actual_offset:actual_offset + 4], expected)),
                        'Native portrait pixels differ from original atlas for control ' + str(node['key']))
                colors.add(expected)
                samples += 1
        require(samples >= 128 and len(colors) >= 16, 'Original portrait interior is empty or uninformative')
        rows.append({'control_key': node['key'], 'texture': node['texture'],
                     'atlas_offset': [node['textureX'], node['textureY']],
                     'opaque_interior_samples': samples, 'distinct_source_rgba_values': len(colors),
                     'sampling': 'linear interpolation at pixel centers; opaque neighbors only',
                     'channel_tolerance': 1,
                     'all_opaque_samples_match_original_atlas': True,
                     'retail_pixels_verified': False})
    return rows


def png_pixels(path, *, expected_dimensions=(1920, 1080)):
    """Strict bounded RGBA PNG readback for pixel evidence, no image edits."""
    require(isinstance(expected_dimensions, (tuple, list)) and len(expected_dimensions) == 2 and
            all(type(value) is int and 0 < value <= 32768 for value in expected_dimensions),
            'Invalid expected PNG dimensions')
    path = Path(path)
    require(path.stat().st_size <= 256 * 1024 * 1024, 'PNG file exceeds its byte bound')
    data = path.read_bytes()
    require(data[:8] == b'\x89PNG\r\n\x1a\n', 'Renderer output is not PNG')
    pos, packed, ihdr, ended, saw_idat, idat_closed, chunk_count = 8, bytearray(), None, False, False, False, 0
    while pos < len(data):
        chunk_count += 1
        require(chunk_count <= 65536, 'PNG chunk count exceeds its bound')
        require(pos + 12 <= len(data), 'Truncated PNG chunk')
        size, = struct.unpack_from('>I', data, pos)
        require(size <= 16 * 1024 * 1024 and pos + size + 12 <= len(data), 'Unbounded/truncated PNG chunk')
        kind = data[pos + 4:pos + 8]
        require(not ended, 'PNG chunk follows IEND')
        payload = data[pos + 8:pos + 8 + size]
        crc, = struct.unpack_from('>I', data, pos + 8 + size)
        require(zlib.crc32(kind + payload) & 0xffffffff == crc, 'PNG CRC differs')
        if kind == b'IHDR':
            require(ihdr is None and pos == 8 and size == 13, 'Duplicate/invalid PNG header')
            ihdr = struct.unpack('>IIBBBBB', payload)
        elif kind == b'IDAT':
            require(ihdr is not None and not idat_closed, 'Invalid/noncontiguous PNG image data')
            require(len(packed) + size <= 256 * 1024 * 1024, 'PNG compressed data exceeds its byte bound')
            packed += payload
            saw_idat = True
        elif kind == b'IEND':
            require(size == 0 and saw_idat and pos + 12 == len(data), 'Invalid PNG end')
            ended = True
        elif saw_idat:
            idat_closed = True
        pos += size + 12
    require(ended and ihdr is not None, 'Incomplete PNG image')
    width, height = ihdr[:2]
    require(0 < width <= 32768 and 0 < height <= 32768 and
            width * height * 4 <= 256 * 1024 * 1024,
            'PNG dimensions exceed bounded pixel storage')
    require((width, height) == tuple(expected_dimensions) and ihdr[2:] == (8, 6, 0, 0, 0),
            f'Expected noninterlaced 8-bit RGBA PNG {tuple(expected_dimensions[0:2])}')
    stride = width * 4
    decoder = zlib.decompressobj()
    raw = decoder.decompress(packed, (stride + 1) * height + 1)
    require(len(raw) == (stride + 1) * height and decoder.eof and not decoder.unconsumed_tail and not decoder.unused_data,
            'Invalid bounded PNG pixel stream')
    pixels = bytearray(stride * height)
    prev = bytearray(stride)
    for y in range(height):
        start = y * (stride + 1)
        filt = raw[start]
        require(filt <= 4, 'Unsupported PNG filter')
        row = bytearray(raw[start + 1:start + 1 + stride])
        for x in range(stride):
            a = row[x - 4] if x >= 4 else 0
            b = prev[x]
            c = prev[x - 4] if x >= 4 else 0
            if filt == 1:
                prediction = a
            elif filt == 2:
                prediction = b
            elif filt == 3:
                prediction = (a + b) // 2
            elif filt == 4:
                p = a + b - c
                da, db, dc = abs(p - a), abs(p - b), abs(p - c)
                prediction = a if da <= db and da <= dc else b if db <= dc else c
            else:
                prediction = 0
            row[x] = (row[x] + prediction) & 255
        pixels[y * stride:(y + 1) * stride] = row
        prev = row
    return pixels


def trade_route_icon_proof(snapshot, compiler):
    """Check the stock icon layers selected by CivIconHookup's captured state.

    Default-color major civilizations draw the full icon in CivIconBG and hide
    CivIcon. Composite icons use the foreground, background and optional shadow
    and highlight. Retain every original layer, but require packets only for
    layers the captured visibility, clip and image tint actually draw.
    """
    primary_ids = {'FromCivIcon', 'ToCivIcon'}
    layer_ids = {prefix + suffix for prefix in primary_ids
                 for suffix in ('', 'BG', 'Shadow', 'Highlight')}
    geometry = {row['key']: row for row in compiler.geometry if not row['style_decoration']}
    primary_keys, layer_keys, visible_keys = [], [], []

    def collect(node, visible=True):
        visible = visible and node.get('hidden') is False
        if node.get('kind') == 'ShowOnMouseOver':
            visible = visible and node.get('hovered') is True
        elif node.get('kind') == 'HideOnMouseOver':
            visible = visible and node.get('hovered') is False
        if node.get('kind') == 'Image' and node.get('id') in layer_ids:
            key = node.get('key')
            require(type(key) is int and key not in layer_keys,
                    'TradeRoute civilization icon layer has a missing or duplicate key')
            layer_keys.append(key)
            if node['id'] in primary_ids:
                primary_keys.append(key)
            if visible:
                require(key in geometry,
                        'Visible original TradeRoute civilization icon layer lost its geometry')
                drawn = geometry[key]
                color = node.get('color')
                alpha = (color['w'] if color is not None else
                         compiler.color(node['attributes']['Color'])[3]
                         if 'Color' in node['attributes'] else 1)
                if positive(rect(drawn['bounds'])) and positive(drawn['clip']) and alpha > 0:
                    visible_keys.append(key)
        for child in node.get('children', []):
            collect(child, visible)

    collect(snapshot['tree'])
    rows = compiler.trade_route_state['retained_row_count']
    require(len(primary_keys) == rows * 2 and len(layer_keys) == rows * 8,
            'TradeRoute rows do not retain both original four-layer civilization icons')
    sprite_keys = {sprite[1] for sprite in compiler.sprites} & set(layer_keys)
    require(sprite_keys == set(visible_keys),
            'Original TradeRoute visible civilization icon layers differ from renderer sprites')
    return {'row_civilization_icon_keys': sorted(primary_keys),
            'row_civilization_icon_layer_keys': sorted(layer_keys),
            'row_civilization_icon_visible_layer_keys': sorted(visible_keys),
            'row_civilization_icon_sprite_keys': sorted(sprite_keys)}


def prepare(snapshot_path, directory, manifest_path, *, closed=False, context='ranking'):
    snapshot_hash = sha256(snapshot_path)
    snapshot = json.loads(Path(snapshot_path).read_text(encoding='utf-8'))
    color_source = json.loads((directory / 'inline_colors.json').read_text(encoding='utf-8'))
    require(context == 'ranking' or context in SCENE_CONTEXTS, 'Unknown selected popup context')
    live_context = context in SCENE_CONTEXTS
    economic_prepared = None
    economic_prepared_source = None
    frozen_prepared = None
    font_binding = None
    support = None
    preparation_inputs = directory / 'preparation_inputs.json'
    if preparation_inputs.is_file():
        inputs = json.loads(preparation_inputs.read_text(encoding='utf-8'))
        support = inputs.get('support_manifest')
        check_artifact(support)
        support_doc = json.loads(Path(support['path']).read_text(encoding='utf-8'))
        frozen_prepared_source = support_doc.get('asset_preparation_provenance')
        check_artifact(frozen_prepared_source)
        frozen_prepared = json.loads(Path(frozen_prepared_source['path']).read_text(encoding='utf-8'))
        font_binding = owned_font_input_binding(frozen_prepared)
        if context == 'economic-overview':
            economic_prepared_source = frozen_prepared_source
            economic_prepared = frozen_prepared
    require(context != 'economic-overview' or economic_prepared is not None,
            'EconomicOverview requires its frozen prepared UI source')
    research_context = context in ('research', 'research-tree')
    city_view_layout_variant = 'default'
    if context == 'city-view':
        city_view = snapshot.get('cityView')
        require(type(city_view) is dict and city_view.get('layoutVariant') in ('default', 'small') and
                type(city_view.get('smallUIAssets')) is bool and
                city_view['smallUIAssets'] == (city_view['layoutVariant'] == 'small'),
                'CityView snapshot layoutVariant and smallUIAssets profile do not agree')
        city_view_layout_variant = city_view['layoutVariant']
    unit_panel_layout_variant = 'default'
    if context == 'unit-panel':
        unit_panel = snapshot.get('unitPanel')
        require(type(unit_panel) is dict and unit_panel.get('layoutVariant') in ('default', 'small'),
                'UnitPanel snapshot lacks its selected original layout variant')
        require(type(unit_panel.get('smallUIAssets')) is bool and
                unit_panel['smallUIAssets'] == (unit_panel['layoutVariant'] == 'small') and
                unit_panel.get('retailLayoutVariantSelectionVerified') is False,
                'UnitPanel variant does not preserve the original OptionsManager profile/proof boundary')
        unit_panel_layout_variant = unit_panel['layoutVariant']
    icon_path = directory / 'inline_icons.json'
    require(not live_context or icon_path.is_file(),
            'Selected live popup context requires prepared original FontIcons mapping and glyph provenance')
    icon_source = json.loads(icon_path.read_text(encoding='utf-8')) if icon_path.is_file() else {}
    require(not live_context or type(icon_source.get('icons')) is dict,
            'Selected live popup inline icon mapping is malformed')
    snapshot_clock = snapshot.get('presentationClock', 0)
    compiler = Compiler(GAME, directory, inline_colors=color_source['colors'],
                        inline_icons=icon_source.get('icons', {}), context=context,
                        snapshot_clock=snapshot_clock,
                        city_view_layout_variant=city_view_layout_variant,
                        unit_panel_layout_variant=unit_panel_layout_variant,
                        economic_overview_prepared=economic_prepared,
                        font_root=font_binding['asset_root'] if font_binding is not None else None,
                        font_binding=font_binding)
    packet = directory / 'scene.packet'
    packet.write_bytes(compiler.compile(snapshot, closed=closed))
    if context == 'economic-overview':
        snapshot = compiler.economic_overview_snapshot
        check_artifact(economic_prepared_source)
    frozen_ui = []
    originals = {compiler.styles_path, *compiler.context_sources}
    for row in compiler.font_records:
        originals.add(Path(row['ggxml_path']))
        originals.add(Path(row['color_atlas_path']))
    for index, source in enumerate(sorted(originals)):
        # Keep the exact original path/hash in the manifest while avoiding
        # MAX_PATH in the deeper live SDK session directory.
        frozen_ui.append(freeze(source, directory / 'source_ui' / f'{index:02d}_{source.name}'))
    require(compiler.unchanged() and sha256(snapshot_path) == snapshot_hash, 'UI/assets or actual SDK snapshot changed during compilation')
    if frozen_prepared is not None:
        check_artifact(support)
        check_artifact(frozen_prepared_source)
        require(owned_font_input_binding(frozen_prepared) == font_binding, 'Owned font inputs changed during scene preparation')
    bounds_check = ({'checked': [], 'deferred': [], 'inactive_context_not_drawn': True,
                     'retail_layout_equivalence_verified': False} if closed else
                    retained_bounds(snapshot, compiler.geometry, context=context))
    event_targets = [target for target in snapshot.get('inputTargets', []) if type(target) is dict]
    top_panel_fullscreen_controls = []
    top_panel_tooltip_controls = []
    top_panel_tooltip_proof = None
    if context == 'top-panel':
        top_panel_fullscreen_controls = [row for row in compiler.geometry
                                         if row.get('kind') != 'Context' and
                                         tuple(row.get('bounds', ())) == (0, 0, 1920, 1080)]
        require(not top_panel_fullscreen_controls,
                'TopPanel source scene contains a non-root full-viewport control')
        def collect_top_panel_tooltips(node):
            attrs = node.get('attributes', {})
            tooltip_type = attrs.get('ToolTipType')
            tooltip_string = attrs.get('ToolTip')
            if tooltip_type or tooltip_string or node.get('toolTipCallback') is True:
                top_panel_tooltip_controls.append({
                    'key': node.get('key'), 'id': node.get('id', ''), 'kind': node.get('kind'),
                    'toolTipType': tooltip_type, 'toolTip': tooltip_string,
                    'toolTipCallback': node.get('toolTipCallback') is True,
                    'hidden': node.get('hidden') is True,
                })
            for child in node.get('children', []):
                collect_top_panel_tooltips(child)
        collect_top_panel_tooltips(snapshot['tree'])
        tooltip_callback_targets = [target for target in event_targets
                                    if target.get('event') != 'ConsumeMouse' and
                                    target.get('toolTipCallback') is True]
        require(top_panel_tooltip_controls or tooltip_callback_targets,
                'TopPanel snapshot lost its original TooltipType or tooltip callback controls')
        tooltip_snapshot = snapshot.get('topPanelTooltip')
        if tooltip_snapshot is not None:
            require(type(tooltip_snapshot) is dict and
                    tooltip_snapshot.get('type') == 'TooltipTypeTopPanel' and
                    type(tooltip_snapshot.get('tree')) is dict and
                    tooltip_snapshot.get('retailPlacementVerified') is False and
                    tooltip_snapshot.get('retailAutosizeVerified') is False,
                    'TopPanel tooltip snapshot differs from the original unverified placement/autosize contract')
        top_panel_tooltip_proof = {
            'callback_targets': tooltip_callback_targets,
            'source_control_tooltips': top_panel_tooltip_controls,
            'captured_tooltip_type': (tooltip_snapshot.get('type') if tooltip_snapshot else None),
            'captured_tooltip_tree': (copy.deepcopy(tooltip_snapshot['tree']) if tooltip_snapshot else None),
            'retail_placement_verified': False,
            'retail_autosize_verified': False,
            'rasterized': False,
        }
    context_name = {'production': 'ProductionPopup', 'research': 'TechPopup',
                    'research-tree': 'TechTree',
                    'tech-award': 'TechAwardPopup',
                    'goody-hut-reward': 'GoodyHutPopup',
                    'ranking': 'WhosWinningPopup', 'city-capture': 'GenericPopup',
                    'diplomacy': 'diplomacy', 'city-view': 'CityView', 'unit-panel': 'UnitPanel',
                    'declare-war': 'DeclareWarPopup', 'top-panel': 'TopPanel',
                    'trade-route': 'TradeRoute', 'social-policy': 'SocialPolicyPopup',
                    'economic-overview': 'EconomicOverview', 'action-info-panel': 'ActionInfoPanel',
                    'notification-panel': 'NotificationPanel', 'game-menu': 'GameMenu', 'exit-confirm': 'ExitConfirm', 'save-menu': 'SaveMenu',
                    'load-menu': 'LoadMenu', **{key:value[0] for key,value in PRIVATE_MENU_CONTEXTS.items()}}[context]
    popup_kind = {'production': 'Production', 'research': 'Research',
                  'research-tree': 'ResearchTree',
                  'tech-award': 'TechAward',
                  'goody-hut-reward': 'GoodyHutReward',
                  'ranking': 'WhosWinning', 'city-capture': 'CityCapture',
                  'diplomacy': 'LeaderHead', 'city-view': 'CityView', 'unit-panel': 'UnitPanel',
                  'declare-war': 'DeclareWar', 'top-panel': 'TopPanel',
                  'trade-route': 'TradeRoute', 'social-policy': 'SocialPolicy',
                  'economic-overview': 'EconomicOverview', 'action-info-panel': 'ActionInfoPanel',
                  'notification-panel': 'NotificationPanel', 'game-menu': 'GameMenu', 'exit-confirm': 'ExitConfirm', 'save-menu': 'SaveMenu',
                  'load-menu': 'LoadMenu', **{key:value[1] for key,value in PRIVATE_MENU_CONTEXTS.items()}}[context]
    right_targets = [target for target in event_targets if target.get('event') == 'RightClick']
    city_view_check_atlas_policy = None
    if context == 'city-view':
        expected_check_assets = {str(row['check_atlas_texture']).replace('\\', '/').rsplit('/', 1)[-1].casefold()
                                 for row in compiler.geometry if 'check_atlas_frame' in row}
        require(expected_check_assets <= {'checkbox.dds', 'checkbox2thebox.dds'},
                'CityView check atlas policy encountered an uninspected original texture')
        check_asset_rows = [row for row in compiler.assets.records
                            if str(row.get('requested_name', '')).replace('\\', '/').rsplit('/', 1)[-1].casefold()
                            in expected_check_assets]
        require({str(row.get('requested_name', '')).replace('\\', '/').rsplit('/', 1)[-1].casefold()
                 for row in check_asset_rows} == expected_check_assets and
                all(row.get('conversion', {}).get('width') == 32 and
                    row.get('conversion', {}).get('height') == 128 and
                    row.get('source') and row.get('index_source') and row.get('output')
                    for row in check_asset_rows),
                'CityView check atlas policy lacks exact decoded original texture provenance')
        city_view_check_atlas_policy = {
            'policy': 'CIV5_CHECK_ATLAS_CHECKED_DISABLED_CELL_CANDIDATE_V1',
            'state_frames': [
                {'checked': False, 'disabled': False, 'frame': 0, 'appearance': 'unchecked enabled'},
                {'checked': True, 'disabled': False, 'frame': 1, 'appearance': 'checked enabled'},
                {'checked': True, 'disabled': True, 'frame': 2, 'appearance': 'checked disabled'},
                {'checked': False, 'disabled': True, 'frame': 3, 'appearance': 'unchecked disabled'},
            ],
            'assets': [{'requested_name': row['requested_name'], 'source': row['source'],
                        'index_source': row['index_source'], 'conversion': row['conversion'],
                        'output': row['output']} for row in check_asset_rows],
            'retail_widget_state_mapping_verified': False,
            'retail_pixels_verified': False,
        }
    trade_route_icons = (trade_route_icon_proof(snapshot, compiler)
                         if context == 'trade-route' else {})
    social_policy_check_atlas_policy = None
    if context == 'social-policy':
        expected_check_assets = {str(row['check_atlas_texture']).replace('\\', '/').rsplit('/', 1)[-1].casefold()
                                 for row in compiler.geometry if 'check_atlas_frame' in row}
        check_asset_rows = [row for row in compiler.assets.records
                            if str(row.get('requested_name', '')).replace('\\', '/').rsplit('/', 1)[-1].casefold()
                            in expected_check_assets]
        require(closed or expected_check_assets or compiler.social_policy_state['current_tab'] == 'Ideologies' and
                {str(row.get('requested_name', '')).replace('\\', '/').rsplit('/', 1)[-1].casefold()
                 for row in check_asset_rows} == expected_check_assets and
                all(type(row.get('conversion', {}).get('height')) is int and
                    row['conversion']['height'] % 4 == 0 and
                    row.get('source') and row.get('index_source') and row.get('output')
                    for row in check_asset_rows),
                'SocialPolicy checkbox atlas lacks exact original decoded texture provenance')
        social_policy_check_atlas_policy = {
            'policy': 'CIV5_SOCIAL_POLICY_CHECK_ATLAS_FOUR_STATE_CANDIDATE_V1',
            'state_frames': [
                {'checked': False, 'disabled': False, 'frame': 0},
                {'checked': True, 'disabled': False, 'frame': 1},
                {'checked': True, 'disabled': True, 'frame': 2},
                {'checked': False, 'disabled': True, 'frame': 3},
            ],
            'assets': [{'requested_name': row['requested_name'], 'source': row['source'],
                        'index_source': row['index_source'], 'conversion': row['conversion'],
                        'output': row['output']} for row in check_asset_rows],
            'retail_widget_state_mapping_verified': False,
            'retail_pixels_verified': False,
        }
    social_policy_hover_gates = []
    if context == 'social-policy':
        def collect_hover_gates(node):
            if type(node) is dict:
                if node.get('kind') == 'HideOnMouseOver':
                    validate_social_policy_hover_gate(node)
                    social_policy_hover_gates.append(node)
                for child in node.get('children', []):
                    collect_hover_gates(child)
        collect_hover_gates(snapshot['tree'])
    manifest = {'status': ('PRIVATE_HOST_MENU_COMPONENT_SCENE_COMPILED' if context in PRIVATE_MENU_CONTEXTS else
                           'STOCK_TOP_PANEL_COMPONENT_SCENE_COMPILED' if context == 'top-panel' else
                           'STOCK_TRADE_ROUTE_COMPONENT_SCENE_COMPILED' if context == 'trade-route' else
                           'STOCK_SOCIAL_POLICY_COMPONENT_SCENE_COMPILED' if context == 'social-policy' else
                           'STOCK_ECONOMIC_OVERVIEW_COMPONENT_SCENE_COMPILED' if context == 'economic-overview' else
                           'STOCK_ACTION_INFO_PANEL_COMPONENT_SCENE_COMPILED' if context == 'action-info-panel' else
                           'STOCK_NOTIFICATION_PANEL_COMPONENT_SCENE_COMPILED' if context == 'notification-panel' else
                           'STOCK_EXIT_CONFIRM_COMPONENT_SCENE_COMPILED' if context == 'exit-confirm' else
                           'STOCK_GAME_MENU_COMPONENT_SCENE_COMPILED' if context == 'game-menu' else
                           'STOCK_SAVE_MENU_COMPONENT_SCENE_COMPILED' if context == 'save-menu' else
                           'STOCK_LOAD_MENU_CONTROL_COMPONENT_SCENE_COMPILED' if context == 'load-menu' else
                           'ACTUAL_SDK_CLOSED_POPUP_EMPTY_SCENE_COMPILED' if closed else
                           'ACTUAL_SDK_RETAINED_POPUP_SCENE_COMPILED'), 'packet': artifact(packet),
                'snapshot': artifact(snapshot_path), 'snapshot_state_unchanged': True,
                'context': context,
                'economic_overview_scene': compiler.economic_overview_scene,
                'economic_overview_prepared_source': economic_prepared_source,
                'action_info_panel_scene': compiler.action_info_panel_scene,
                'notification_panel_scene': compiler.notification_panel_scene,
                'game_menu_scene': compiler.game_menu_scene,
                'exit_confirm_scene': compiler.exit_confirm_scene,
                'save_menu_scene': compiler.save_menu_scene,
                'load_menu_controls': compiler.load_menu_scene,
                'private_menu_scene': compiler.private_menu_scene,
                'goody_hut_reward_scene': compiler.goody_hut_reward_scene,
                'context_name': context_name,
                'popup_kind': popup_kind,
                'city_view_layout_variant': (compiler.city_view_layout_variant
                                             if context == 'city-view' else None),
                'unit_panel_layout_variant': (compiler.unit_panel_layout_variant
                                              if context == 'unit-panel' else None),
                'top_panel_world_overlay': ({
                    'policy': 'ZEROSIS_TOPPANEL_OVER_LIVE_WORLD_V1',
                    'source_layout': str(compiler.layout_path.relative_to(compiler.game_root)).replace('\\', '/'),
                    'source_contract': compiler.top_panel_source_contract,
                    'active_player': snapshot['topPanel']['activePlayer'],
                    'nonmodal': True, 'timer_semaphores': 0, 'timer_semaphore': 0,
                    'full_screen_opaque_placeholder': False,
                    'non_root_full_viewport_controls': top_panel_fullscreen_controls,
                    'host_compositor_required': True,
                    'host_compositor_runtime_verified': False,
                    'original_control_tree_and_styles_retained': True,
                    'info_stack_hidden': compiler.top_panel_interaction_contract['info_stack_hidden'],
                    'science_callback_available': compiler.top_panel_interaction_contract['science_callback_available'],
                    'science_callback_target': compiler.top_panel_interaction_contract['science_callback_target'],
                    'other_original_callback_targets_preserved_but_not_claimed_complete': [target for target in event_targets
                        if target.get('event') not in ('ConsumeMouse',) and target.get('id') != 'SciencePerTurn'],
                    'consume_mouse_targets': [target for target in event_targets
                        if target.get('event') == 'ConsumeMouse'],
                    'tooltip_controls': top_panel_tooltip_controls,
                    'tooltip': top_panel_tooltip_proof,
                    'tooltip_callbacks_executed_by_renderer': False,
                    'retail_pixels_verified': False,
                    'original_visibility_semantics_verified': False,
                } if context == 'top-panel' else None),
                'city_view_context_font_policy': (compiler.city_view_context_font_policy
                                                  if context == 'city-view' else None),
                'city_view_check_atlas_policy': city_view_check_atlas_policy,
                'social_policy_check_atlas_policy': social_policy_check_atlas_policy,
                'trade_route_scene': ({
                    'policy': 'ORIGINAL_TRADE_ROUTE_OVERVIEW_RETAINED_TREE_V1',
                    'source_contract': compiler.trade_route_source_contract,
                    'modal': snapshot['tradeRoute']['modal'],
                    'timer_semaphore': snapshot['tradeRoute']['timerSemaphore'],
                    'row_template': snapshot['tradeRoute']['rowTemplate'],
                    'retained_row_count': compiler.trade_route_state['retained_row_count'],
                    'selected_tab': compiler.trade_route_state['selected_tab'],
                    'row_selection_present': snapshot['tradeRoute']['rowSelectionPresent'],
                    'row_tooltip_control_digests': compiler.trade_route_state['row_tooltips'],
                    **trade_route_icons,
                    'main_scroll': copy.deepcopy(snapshot['tradeRoute']['mainScroll']),
                    'row_tooltips_rasterized': False,
                    'original_input_targets': event_targets,
                    'scroll_target_policy': 'exact original MainScroll target bounds, clipping, offset, content extent, viewport and maximum range crosschecked; wheel/retail scroll semantics unverified',
                    'row_tooltip_policy': 'original per-control runtime tooltip strings remain on retained controls; tooltip popovers are not rasterized and retail placement/autosize are unverified',
                    'retail_pixels_verified': False,
                    'retail_style_timing_verified': False,
                } if context == 'trade-route' else None),
                'social_policy_scene': ({
                    'policy': 'ORIGINAL_SOCIAL_POLICY_POPUP_RETAINED_TREE_V1',
                    'source_contract': compiler.social_policy_source_contract,
                    'active_player': compiler.social_policy_state['active_player'],
                    'current_tab': compiler.social_policy_state['current_tab'],
                    'policy_info': compiler.social_policy_state['policy_info'],
                    'has_city': compiler.social_policy_state['has_city'],
                    'policy_tab_branch_ids': compiler.social_policy_state['policy_tab_branch_ids'],
                    'ideology_pane_visible': compiler.social_policy_state['ideology_pane_visible'],
                    'policy_count': compiler.social_policy_state['policy_count'],
                    'branch_count': compiler.social_policy_state['branch_count'],
                    'branch_switch_confirmation_present': compiler.social_policy_state['branch_switch_confirmation_present'],
                    'ideology_change_present': compiler.social_policy_state['ideology_change_present'],
                    'original_input_targets': event_targets,
                    'confirmation_states': {
                        control_id: next((node.get('hidden') is False for node in snapshot['tree'].get('children', [])
                                          if node.get('id') == control_id), None)
                        for control_id in ('PolicyConfirm', 'TenetConfirm', 'ChangeIdeologyConfirm')},
                    'retail_pixels_verified': False,
                    'all_policy_actions_use_stock_callbacks': True,
                    'full_policy_gameplay_coverage': False,
                } if context == 'social-policy' else None),
                'social_policy_hover_gate_policy': ({
                    'policy': 'ZEROSIS_RETAINED_SOCIAL_POLICY_INVERSE_HOVER_GATE_V1',
                    'gate_count': len(social_policy_hover_gates),
                    'hovered_keys': [node['key'] for node in social_policy_hover_gates
                                     if node.get('hovered') is True],
                    'blank_area_hover_verified': False,
                    'retail_behavior_verified': False,
                } if context == 'social-policy' else None),
                'presentation_clock': snapshot_clock,
                'animation_policy': snapshot.get('animationPolicy') if live_context else None,
                'style_decoration_policy': ('Original GameMenu parent controls, detail/mod rows, stock style decorations and captured Once/Bounce child opacity; five original child LuaContexts stay hidden and uninstantiated; retail pixels/timing unverified'
                                            if context == 'game-menu' else
                                            'Original DeclareWarPopup Styles.xml children and captured hover/collapse state are retained under their source controls; original generated instance nodes and all detail sections remain in the captured tree; stock style expansion/timing and retail pixels unverified'
                                            if context == 'declare-war' else
                                            'Original ActionInfoPanel EndTurnButton/Text, stock GridData/styles and captured AlphaAnim/ScrollAnim state; NotificationPanel declaration retained as unconnected metadata; retail timing and pixels unverified'
                                            if context == 'action-info-panel' else
                                            'Original NotificationPanel templates, live SDK rows, scroll viewport and source animations are retained; SlideAnim and OneBounce use explicit frontend timing candidates; retail timing and pixels unverified'
                                            if context == 'notification-panel' else
                                            'Complete original EconomicOverview, EconomicGeneralInfo and HappinessInfo trees retain their own styles and source controls; only the two original LuaContext slots are composed; retail embedded layout, style timing and pixels unverified'
                                            if context == 'economic-overview' else
                                            'Original TopPanel XML tree, stock styles, source text, icon atlas regions, tooltip declarations, and capture-time control state; generated dynamic tooltip content is retained as metadata but not rasterized; retail layout/timing unverified'
                                            if context == 'top-panel' else
                                            'Original TradeRouteOverview tabs, sortable headers and source-generated TRInstance rows are retained; runtime tooltip strings remain metadata and are not rasterized; retail style expansion, scrollbar geometry and pixels unverified'
                                            if context == 'trade-route' else
                                            'Original UnitPanel controls from the retained selected-unit tree; stock ToolTipType subtrees and generated hover tooltip content are not rasterized; retail style expansion/timing unverified'
                                            if context == 'unit-panel' else
                                            'Official Styles.xml controls/hover children anchored to retained LeaderHeadRoot controls; Bounce alpha uses the retained clock under the frontend timeline policy; retail style expansion/timing unverified'
                                            if context == 'diplomacy' else
                                            'Original SocialPolicyPopup tabs, scroll panels, policy/branch instances, confirmation contexts and controls are retained; source-resolved captions and checkbox state are drawn from the SDK snapshot; original style timing and retail pixels unverified'
                                            if context == 'social-policy' else
                                            'Official Styles.xml children anchored to original popup controls; retail style expansion/timing and pixels unverified'
                                             if context in ('tech-award', 'goody-hut-reward', 'city-capture') else
                                            'Official Styles.xml children and hover overlays anchored to original retained CityView controls; retail style expansion and widget-state ordering unverified'
                                            if context == 'city-view' else None),
                'leaderhead_display_policy': ('Original LeaderHeadRoot text and civ-symbol controls from either DIPLO_UI_STATE_DEFAULT_ROOT/LEADERHEAD_ANIM_INTRO or DIPLO_UI_STATE_WAR_DECLARED_BY_HUMAN/LEADERHEAD_ANIM_ATTACKED with data1=0; original 3D leader model/animation not rendered; nested DiscussionDialog/DiploTrade callbacks unsupported'
                                             if context == 'diplomacy' else None),
                'stock_escape_closes_popup': False if context == 'city-capture' else True if context in ('diplomacy', 'tech-award', 'goody-hut-reward', 'declare-war', 'trade-route', 'social-policy', 'economic-overview', *PRIVATE_MENU_CONTEXTS) else None,
                'stock_enter_closes_popup': True if context in ('diplomacy', 'tech-award', 'goody-hut-reward', 'economic-overview') else None,
                'retail_timing_verified': snapshot.get('retailTimingVerified', False) if live_context else False,
                'original_context_sources': [{'path': str(path), 'sha256': digest}
                                             for path, digest in sorted(compiler.context_sources.items())],
                'closed_context_not_drawn': closed,
                'width': compiler.width, 'height': compiler.height, 'geometry': compiler.geometry,
                'labels': compiler.labels, 'hit_regions': compiler.hits,
                'scroll_regions': compiler.scroll_regions,
                'scroll_region_policy': ('Private source-bound map list ScrollPanel; original options/touch children expose no scroll targets; parent timer and retail input behavior remain separately unverified'
                                         if context in PRIVATE_MENU_CONTEXTS else
                                         'Original GameMenu details/mods ScrollPanels retain their captured vertical range and clipping; hidden panels expose no scroll targets; retail wheel semantics unverified'
                                         if context == 'game-menu' else
                                         'Original DeclareWarDetailsScrollPanel clipped to its retained viewport; offsets/content/viewport/range crosschecked with scrollTargets; retail wheel semantics unverified'
                                         if context == 'declare-war' else
                                         'Original EconomicGeneralInfo/HappinessInfo ScrollPanels retain child VM key ranges, clipped bounds and captured offsets/content/viewport/range; hidden children expose no scroll targets; retail wheel semantics unverified'
                                         if context == 'economic-overview' else
                                         'Original SocialPolicy vertical branch ScrollPanels retain captured offsets, clipping and content/viewport ranges; retail wheel semantics unverified'
                                         if context == 'social-policy' else
                                         'Original NotificationPanel SmallScrollPanel retains captured vertical offset, viewport and clipping; retail wheel semantics unverified'
                                         if context == 'notification-panel' else
                                         'Original vertical MainScroll clipped to its retained viewport; scroll offset/content/viewport/range crosschecked with scrollTargets; retail wheel semantics unverified'
                                         if context == 'trade-route' else
                                         'not applicable; selected TechAwardPopup layout has no scroll controls'
                                         if context == 'tech-award' else
                                         'not applicable; original GoodyHutPopup has no scroll controls'
                                         if context == 'goody-hut-reward' else
                                         'GenericPopup CityCapture has no ScrollPanel or ScrollBar in the selected original XML; input wheel semantics are not encoded'
                                         if context == 'city-capture' else
                                         'Visible horizontal TechTree ScrollPanel clippedBounds; exact scrollX/contentWidth/viewportWidth/maximumScroll checked against retained state; input wheel semantics unverified'
                                         if context == 'research-tree' else
                                         'Visible vertical ScrollPanel clippedBounds; exact scrollY/contentHeight/viewportHeight/maximumScroll checked against retained state; input wheel semantics unverified'
                                         if context in ('production', 'research') else
                                         'Visible original vertical CityView ScrollPanel clippedBounds; range crosschecked against retained scroll targets; wheel semantics unverified'
                                         if context in ('city-view', 'declare-war') else
                                         'not applicable; selected original LeaderHeadRoot layout has no scroll control'
                                         if context == 'diplomacy' else 'not encoded in ranking ZSUPIX01'),
                'scroll_region_provenance': ({'snapshot': artifact(snapshot_path),
                                              'field': 'scrollTargets',
                                              'tree_crosscheck': ('visible horizontal retained ScrollPanels; exact viewport, ancestor clipping, offset and content extent'
                                                                  if context == 'research-tree' else
                                                                  'visible vertical retained ScrollPanels; exact viewport, ancestor clipping, offset and content extent')}
                                             if live_context and context not in ('city-capture', 'diplomacy') else None),
                'packet_version': 'ZSUPIX02' if live_context else 'ZSUPIX01',
                'input_target_policy': ('Complete original XML with explicitly inventoried Host-derived controls; exact visible callback/consumer order is retained; options expose only backend capabilities, retail OptionsManager API completeness and native acceptance remain false'
                                         if context in PRIVATE_MENU_CONTEXTS else
                                         'Original separate ExitConfirm full-screen input shield and Yes/No callbacks are retained in tree order; stock PushModal/PopModal preserves the parent GameMenu timer; native exit and retail pixels remain unverified'
                                         if context == 'exit-confirm' else
                                         'Original GameMenu XML and inherited Styles.xml consumers merge with enabled callbacks in original tree order; full-screen ExitConfirm blocks earlier menu input; five child menu VMs remain hidden and uninstantiated; renderer does not execute menu actions or certify native saving'
                                         if context == 'game-menu' else
                                         'Original DeclareWarPopup Button1/Button2 Yes/No callbacks and five stock CommonBehaviors section-collapse callbacks are retained by control ID; no synthetic callback is substituted; stock Lua action/Network.SendChangeWar path remains the command authority'
                                         if context == 'declare-war' else
                                         'Original ActionInfoPanel EndTurnButton LeftClick/RightClick callbacks share one source-anchored hit region; disabled state exposes neither callback; stock Lua/SDK remain the command authority; NotificationPanel is unconnected'
                                         if context == 'action-info-panel' else
                                         'Original NotificationPanel per-notification left-click activation and right-click removal callbacks retain native IDs, payloads and clipped bounds; destinations beyond current SDK routes remain explicitly unintegrated'
                                         if context == 'notification-panel' else
                                         'Original EconomicOverview tabs/CloseButton and visible child callbacks preserve numeric payloads; child keys occupy separate fixed VM ranges and hidden children expose no hits; retail input behavior and complete gameplay remain unverified'
                                         if context == 'economic-overview' else
                                        'Original three TradeRoute tabs, fourteen sortable headers and CloseButton LeftClick targets are retained by exact IDs and clipped bounds; stock rows have no selection callbacks; no row input is synthesized'
                                        if context == 'trade-route' else
                                        'Original SocialPolicy tabs, PolicyInfo CheckBox, policy/branch callback IDs and confirmation Yes/No controls are retained with original callback payloads and bounds; all gameplay decisions remain in stock Lua/SDK'
                                        if context == 'social-policy' else
                                        'Original TopPanel callback targets and source ConsumeMouse controls are retained by key/id/bounds; only SciencePerTurn is an implemented downstream route; menu/overview targets remain visible and explicitly unsupported'
                                        if context == 'top-panel' else
                                        'PuppetCityPopup registered visible enabled city-action LeftClick controls; GenericPopup callback bounds and clipping crosschecked against retained XYWH; ESC consumes without closing'
                                        if context == 'city-capture' else
                                        'Original UnitPanel retained button targets are validated and visible enabled LeftClick rectangles are encoded; right-click actions and ToolTipType hover popovers are unsupported'
                                        if context == 'unit-panel' else
                                        'LeaderHeadRoot callback targets crosschecked against retained controls; BackButton is the original return callback; Escape/Enter use the original InputHandler; trade/discussion/war/demand actions remain unsupported and must fail visibly'
                                        if context == 'diplomacy' else
                                        'registered visible enabled LeftClick controls; bounds and ScrollPanel clipping independently checked against retained XYWH'
                                        if context == 'production' else
                                        'Research TechPopup retains and crosschecks LeftClick/RightClick callback provenance; ZSUPIX02 encodes LeftClick rectangles only'
                                        if context == 'research' else
                                        'TechAwardPopup retains original ContinueButton callback; hidden CloseButton is not an input target'
                                        if context == 'tech-award' else
                                         'Original GoodyHutPopup retains one CloseButton LeftClick target outside its parent grid; Escape/Return dequeue the informational modal without granting rewards or issuing gameplay commands'
                                         if context == 'goody-hut-reward' else
                                        'TechTree retains original LeftClick/RightClick TechButton and CloseButton callbacks; ZSUPIX02 encodes LeftClick rectangles only'
                                        if context == 'research-tree' else 'selected ranking GridButton close target'),
                'input_target_count': len(compiler.hits),
                'retained_input_targets': ([target for target in event_targets
                                            if target.get('event') != 'ConsumeMouse']
                                           if context in ('unit-panel', 'top-panel') else
                                           event_targets if live_context else []),
                'consume_mouse_targets': ([target for target in event_targets
                                           if target.get('event') == 'ConsumeMouse']
                                          if context in ('unit-panel', 'top-panel') else []),
                'unsupported_callback_controls': ([{'id': name, 'supported': False,
                    'reason': 'Original LeaderHeadRoot callback is outside the DEFAULT_ROOT intro/Back/Escape surface'}
                    for name in ('DiscussButton', 'DemandButton', 'TradeButton', 'WarButton')]
                    if context == 'diplomacy' else
                    [{'id': target.get('id', ''), 'key': target.get('key'), 'supported': False,
                      'reason': 'Original TopPanel callback is outside the supported SciencePerTurn-to-TechTree route'}
                     for target in event_targets if target.get('event') != 'ConsumeMouse' and
                     target.get('id') != 'SciencePerTurn'] if context == 'top-panel' else []),
                'city_view_world_overlay': (compiler.city_view_policy if context == 'city-view' else None),
                'unit_panel_world_overlay': ({'policy': 'ZEROSIS_UNITPANEL_OVER_LIVE_WORLD_V1',
                                              'source_layout': str(compiler.layout_path.relative_to(compiler.game_root)).replace('\\', '/'),
                                              'timer_semaphore': 0,
                                              'full_screen_opaque_placeholder': False,
                                              'base_layer_policy': ('original Base is RGBA 0,0,0,0'
                                                                    if compiler.unit_panel_layout_variant == 'default' else
                                                                    'small layout has no full-viewport Base control'),
                                              'composited_over_live_world_by_host': True,
                                              'tool_tip_type_subtrees_rendered': False,
                                              'generated_hover_tooltips_supported': False,
                                              'retail_layout_variant_selection_verified': False,
                                              'consume_mouse_target_policy': 'source ConsumeMouse=1 controls are registered by original key and bounds; overlay hit regions are ordered by retained tree preorder so child callbacks follow parent blockers; no callback is synthesized',
                                              'retail_pixels_verified': False,
                                              'original_visibility_semantics_verified': False}
                                             if context == 'unit-panel' else None),
                'city_view_projection': (copy.deepcopy(snapshot['cityView']['projection'])
                                         if context == 'city-view' else None),
                'city_view_world_anchors': ([{'key': row['key'], 'id': row.get('id', ''),
                                              'bounds': row['bounds'],
                                              'world_position': row['world_position'],
                                              'policy': row['world_position_policy']}
                                             for row in compiler.geometry
                                             if row['kind'] == 'WorldAnchor']
                                            if context == 'city-view' else []),
                'unencoded_right_click_target_count': len(right_targets) if research_context or context == 'unit-panel' else 0,
                'native_right_click_supported': False if research_context or context == 'unit-panel' else None,
                'pedia_context_supported': False if research_context else None,
                'scroll_region_count': len(compiler.scroll_regions),
                'input_callback_coverage_claimed': False,
                'retail_input_semantics_verified': False,
                'derived_animation_textures': compiler.derived_textures,
                'scroll_thumb_policy': ('Original DeclareWarDetailsScrollPanel viewport and VertShuttle minimum retained; thumb is a frontend estimate from captured scroll range, retail geometry unverified'
                                        if context == 'declare-war' else
                                        'not applicable; selected TechAwardPopup layout has no scroll control'
                                        if context == 'tech-award' else
                                         'not applicable; original GoodyHutPopup has no scroll control'
                                         if context == 'goody-hut-reward' else
                                        'not applicable; selected GenericPopup layout has no scroll control'
                                        if context == 'city-capture' else
                                        'not applicable; selected original LeaderHeadRoot layout has no scroll control'
                                        if context == 'diplomacy' else
                                        'original Grid3Shuttle minimum width plus retained horizontal track/content/scroll range; proportional thumb is owned frontend candidate geometry, source engine geometry unverified' if context == 'research-tree' else
                                        'original VertShuttle minimum Size plus retained track/content/scroll range; proportional thumb is owned frontend candidate geometry, source engine geometry unverified' if context == 'research' else
                                        'captured scrollY/contentHeight, captured viewport size, original style minimum; frontend estimate only, retail geometry unverified'),
                'retained_runtime_bounds_check': bounds_check,
                'sprite_count': len(compiler.sprites), 'texture_count': len(compiler.textures),
                'asset_pack_policy': list(PACK_POLICY), 'retail_asset_priority_verified': False,
                'pack_sources': compiler.assets.pack_records, 'selected_assets': compiler.assets.records,
                'selected_original_images': [{'requested_name': row['requested_name'],
                                              'source': row['source'],
                                              'conversion': row['conversion'], 'output': row['output']}
                                             for row in compiler.assets.records],
                'font_sources': compiler.font_records, 'frozen_ui': frozen_ui,
                'owned_font_input_binding': font_binding,
                'inline_color_source': artifact(directory / 'inline_colors.json'),
                'inline_icon_source': artifact(icon_path) if icon_path.is_file() else None,
                'candidate_policy_limits': ['font horizontal/baseline/effect compositing not retail-calibrated',
                    'shadow mask cell-border sampling not retail-calibrated',
                    'Full style dimensions interpreted against viewport', 'nine-slice mixed edge metrics not retail-calibrated',
                    'tooltip UI is retained but not rasterized',
                    'Production Meter draws original asset clipped to captured percent plus percentPlus in a candidate clockwise arc from twelve oclock; retail meter semantics unverified',
                    'ScrollAnim mask uses source alpha times original mask alpha at captured owner clock/phase; retail shader equivalence unverified'] +
                    (['LeaderHeadRoot 3D leader model and response animation are not rendered; only the original retained XML text/icon controls are represented',
                      'DiscussionDialog and DiploTrade nested LuaContexts are retained as hidden source-backed handles; their actions are unsupported']
                     if context == 'diplomacy' else []) +
                    (['TechPopup ScrollBar thumb uses an owned proportional layout rule and original VertShuttle size; source engine thumb geometry unverified',
                      'TechPopup right-click pedia callbacks are retained as metadata but not encoded by native hit packet; pedia interaction unsupported']
                     if context == 'research' else
                     ['TechTree ScrollBar uses an owned horizontal proportional layout rule and original Grid3Shuttle minimum; source engine thumb geometry unverified',
                      'TechTree right-click callbacks are retained as metadata but not encoded by native hit packet; native right-click remains unsupported']
                     if context == 'research-tree' else []),
                'gamecore_executed': False, 'installed_game_launched': False, 'stage_promoted': False,
                'retail_pixels_verified': False}
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def execute(command, cwd, log):
    process = subprocess.run([str(arg) for arg in command], cwd=cwd, capture_output=True,
                             timeout=60, creationflags=subprocess.CREATE_NO_WINDOW)
    output = process.stdout.decode('utf-8', errors='replace')
    errors = process.stderr.decode('utf-8', errors='replace')
    log.write_text(output + errors, encoding='utf-8')
    require(process.returncode == 0, 'Isolated presentation command failed: ' + str(log) + '\n' + (output + errors)[-2000:])
    return output, artifact(log)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare', type=Path)
    parser.add_argument('--directory', type=Path)
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--closed', action='store_true', help='Prepare the empty contribution of an officially dequeued popup context')
    parser.add_argument('--context', choices=('ranking', *SCENE_CONTEXTS), default='ranking',
                        help='Select the explicit original UI layout context for retained-state compilation')
    args = parser.parse_args()
    if args.prepare:
        require(args.directory is not None and args.manifest is not None, 'Missing scene destinations')
        prepare(args.prepare, args.directory, args.manifest, closed=args.closed, context=args.context)
        return 0
    require(args.context == 'ranking', 'Live popup contexts require an explicitly captured SDK snapshot via --prepare')
    require(not args.closed, '--closed requires an explicit captured SDK state and scene destinations')
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ_') + uuid.uuid4().hex[:12]
    build = PROJECT / 'Build/UiPopupPixels' / run_id
    evidence = PROJECT / 'evidence/ui_popup_pixels' / run_id
    build.mkdir(parents=True)
    evidence.mkdir(parents=True)
    report = {'status': 'UI_POPUP_PIXEL_CANDIDATE_FAILED', 'run_id': run_id,
              'scope': 'OFFSCREEN_PIXELS_FROM_RETAINED_ACTUAL_SDK_POPUP_STATE',
              'gamecore_executed': False, 'installed_game_launched': False, 'stage_promoted': False,
              'mods_written': False, 'retail_pixel_equivalence_verified': False,
              'native_window_input_verified': False, 'world_renderer_verified': False,
              'source_inputs_unchanged': False, 'frozen_inputs': [], 'tests': [], 'scenes': [], 'error': None}
    originals = [PROJECT / name for name in OWNED]
    before = {str(path): sha256(path) for path in originals}
    try:
        for source in originals:
            report['frozen_inputs'].append(freeze(source, build / 'frozen' / source.relative_to(PROJECT)))
        report['python'] = artifact(sys.executable)
        renderer_path = PROJECT / 'evidence/bitmap_renderer' / RENDERER_PROOF / 'conformance.json'
        renderer = json.loads(renderer_path.read_text(encoding='utf-8'))
        require(renderer['status'] == 'BITMAP_RENDERER_COMPONENT_PASS' and renderer['source_inputs_unchanged'] is True,
                'No accepted immutable native renderer component')
        for row in renderer['frozen_inputs'].values():
            check_artifact(row)
        cli = renderer['renderer_artifact']
        executable = Path(cli['executable'])
        require(sha256(executable) == cli['executable_sha256'], 'Native renderer CLI differs from component proof')
        report['renderer_component'] = freeze(renderer_path, build / 'frozen' / 'renderer_component.json')
        report['renderer_executable'] = artifact(executable)
        for test in ('civ5_ui_assets.py', 'ui_bitmap_fonts.py', 'ui_pixel_scene.py'):
            output, log = execute([sys.executable, '-B', '-X', 'utf8', build / 'frozen/Tests' / test],
                                  build, evidence / (test + '.log'))
            report['tests'].append({'test': test, 'log': log, 'output': Path(log['path']).read_text(encoding='utf-8').strip()})
        for language, sdk_run in RUNTIME.items():
            runtime_path = PROJECT / 'evidence/save_restore' / sdk_run / 'result.json'
            runtime = json.loads(runtime_path.read_text(encoding='utf-8'))
            require(runtime['status'] == 'ISOLATED_NATIVE_SAVE_RESTORE_EXTENDED_PASS' and
                    runtime['candidate_inputs_unchanged'] is True and runtime['cleanup_completed'] is True and
                    runtime['module_unloaded'] is True, 'Selected SDK runtime is not accepted/clean')
            snapshots = sorted((row for row in runtime['generated_files'] if row['path'].endswith('ui-popup-1-shown.json')),
                               key=lambda row: row['path'])
            require(snapshots, 'No sealed actual SDK popup snapshot')
            selected = snapshots[0]
            check_artifact(selected)
            require(Path(selected['path']).resolve().is_relative_to(PROJECT / 'Build/NewGameRuntime' / sdk_run),
                    'Runtime snapshot escaped selected unique SDK run')
            directory = build / language
            directory.mkdir()
            binding = runtime_binding(runtime, language, sdk_run, directory)
            snapshot = freeze(selected['path'], directory / 'snapshot.json')
            runtime_proof = freeze(runtime_path, directory / 'runtime_result.json')
            database = Path(selected['path']).parent / 'rules.db'
            bindings = [row for row in runtime['generated_files'] if Path(row['path']).resolve() == database.resolve()]
            require(len(bindings) == 1, 'Selected actual SDK color database has no unique runtime binding')
            check_artifact(bindings[0])
            with sqlite3.connect(database.resolve().as_uri() + '?mode=ro', uri=True) as connection:
                rows = connection.execute('SELECT Type, Red, Green, Blue, Alpha FROM Colors WHERE Type LIKE ?', ('COLOR_%',)).fetchall()
            colors = {row[0]: list(row[1:]) for row in rows}
            require(len(colors) == len(rows), 'Duplicate actual SDK database color key')
            (directory / 'inline_colors.json').write_text(json.dumps({'database': bindings[0], 'colors': colors},
                                                                           ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            manifest_path = directory / 'scene_manifest.json'
            _, prepare_log = execute([sys.executable, '-B', '-X', 'utf8', build / 'frozen/tools/render_ui_popup.py',
                                      '--prepare', snapshot['path'], '--directory', directory, '--manifest', manifest_path],
                                     build, evidence / (language + '_prepare.log'))
            manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
            check_artifact(manifest['packet'])
            png = directory / 'popup.png'
            output, native_log = execute([executable, manifest['packet']['path'], png], build,
                                         evidence / (language + '_native.log'))
            expected = f"BITMAP_RENDER_PASS width=1920 height=1080 sprites={manifest['sprite_count']} textures={manifest['texture_count']} hits=1 scope=OFFSCREEN_D2D_WIC"
            require(output.strip() == expected, 'Native renderer output/counts differ from compiled scene')
            pixels = png_pixels(png)
            require(tuple(pixels[:4]) == (0, 0, 0, 0), 'Source clear top bar became opaque')
            bg = tuple(pixels[(35 * 1920) * 4:(35 * 1920) * 4 + 4])
            require(bg == (0, 0, 0, 200), 'Original background style alpha was lost')
            portrait_checks = portrait_readback(json.loads(Path(snapshot['path']).read_text(encoding='utf-8')),
                                                manifest, pixels)
            require(manifest['hit_regions'] == [[12, 745.0, 804.0, 895.0, 836.0]], 'Real CloseButton geometry differs')
            require(sha256(snapshot['path']) == snapshot['sha256'] and sha256(selected['path']) == selected['sha256'],
                    'Rendering changed original or retained SDK UI state')
            report['scenes'].append({'language': language, 'sdk_run': sdk_run, 'snapshot': snapshot,
                'runtime_binding': binding,
                'runtime_result': runtime_proof, 'manifest': artifact(manifest_path), 'packet': manifest['packet'],
                'png': artifact(png), 'native_log': native_log, 'prepare_log': prepare_log,
                'portrait_readback': portrait_checks,
                'retained_runtime_bounds_check': manifest['retained_runtime_bounds_check'],
                'clear_top_pixel_rgba': [0, 0, 0, 0],
                'source_background_pixel_rgba': list(bg), 'snapshot_state_unchanged': True,
                'width': 1920, 'height': 1080, 'sprite_count': manifest['sprite_count'],
                'texture_count': manifest['texture_count'], 'hit_regions': manifest['hit_regions']})
        after = {str(path): sha256(path) for path in originals}
        require(after == before and sha256(executable) == report['renderer_executable']['sha256'], 'Presentation inputs changed')
        report.update(status='RETAINED_ACTUAL_SDK_UI_OFFSCREEN_PIXELS_PASS', source_inputs_unchanged=True,
                      source_hashes_before=before, source_hashes_after=after)
    except Exception as error:
        report['error'] = str(error)
    report_path = evidence / 'conformance.json'
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': report['status'], 'report': str(report_path), 'sha256': sha256(report_path), 'error': report['error']}, ensure_ascii=False))
    return 0 if report['status'] == 'RETAINED_ACTUAL_SDK_UI_OFFSCREEN_PIXELS_PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
