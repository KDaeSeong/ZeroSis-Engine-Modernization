"""Original ActionInfoPanel asset/packet components; no SDK, native or retail PASS.

Fixtures retain the complete installed action-control tree and real GGXML metrics.
Packet textures stay in one project-contained TemporaryDirectory per case.
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / 'tools'))

import prepare_ui_popup_assets as freezer
import interactive_ui_driver as driver
import render_ui_popup
from civ5_ui_assets import sha256
from ui_bitmap_fonts import load_font
from ui_pixel_scene import (Compiler, SCENE_CONTEXTS, action_info_panel_contract,
                            anchor, pair, wrap_production_text, notification_panel_contract,
                            notification_slide_transform, notification_one_bounce_alpha)

GAME = freezer.GAME
XML = GAME / 'Assets/DLC/Expansion2/UI/InGame/WorldView/ActionInfoPanel.xml'
LUA = XML.with_suffix('.lua')


def walk(node):
    yield node
    for child in node['children']:
        yield from walk(child)


def fixture(*, highlight=None, hovered=False, disabled=False):
    source = freezer.action_info_panel_control_tree(ET.parse(XML).getroot())
    styles = {node.tag: node for node in ET.parse(GAME / 'Assets/UI/Styles.xml').getroot()}
    metrics = freezer.production_font_metrics(source, {})
    clock = 0.25
    sequence = [0]

    def capture(node, parent=(0, 0, 1920, 1080), inherited=None):
        sequence[0] += 1
        original = copy.deepcopy(node['attributes'])
        attrs = {**(styles[original['Style']].attrib if original.get('Style') else {}), **original}
        for name in ('Font', 'FontStyle', 'ColorSet'):
            if name not in attrs and inherited and name in inherited:
                attrs[name] = inherited[name]
        kind = node['kind']
        width, height = pair(attrs.get('Size'))
        if kind == 'Context':
            bounds = (0, 0, 1920, 1080)
        elif kind == 'ShowOnMouseOver':
            bounds = parent
        elif kind == 'Label':
            font = load_font(GAME, attrs['Font'], attrs['FontStyle'])
            lines = wrap_production_text(attrs['String'], font, {}, 0)
            bounds = anchor(attrs, parent, max(line[1] for line in lines), font.line_advance)
        else:
            bounds = anchor(attrs, parent, width, height)
        result = {'kind': kind, 'key': sequence[0], 'id': original.get('ID', ''),
                  'attributes': attrs, 'sourceAttributes': original, 'children': [],
                  'hidden': attrs.get('Hidden') == '1', 'disabled': False,
                  'text': attrs.get('String', ''), 'buttonState': 'normal',
                  'hovered': hovered, **dict(zip(('x', 'y', 'width', 'height'), bounds))}
        if 'Texture' in attrs:
            result['texture'] = attrs['Texture']
        result['textureX'], result['textureY'] = pair(attrs.get('TextureOffset'))
        if kind == 'AlphaAnim':
            start, finish = float(attrs['AlphaStart']), float(attrs['AlphaEnd'])
            result['animation'] = {'clock': clock, 'alpha': start + (finish - start) * clock}
        elif kind == 'ScrollAnim':
            result['animation'] = {'clock': clock, 'phase': clock * float(attrs['Speed'])}
        elif kind == 'Label':
            result['textFrame'] = {**dict(zip(('x', 'y', 'width', 'height'), bounds)),
                                   'wrapWidth': 0, 'lineAdvance': font.line_advance,
                                   'baselineOffset': font.baseline_offset,
                                   'lines': [{'text': text, 'advanceWidth': advance} for text, advance in lines]}
            result['fontMetricSource'] = {key: metrics['fonts'][attrs['Font']][key]
                                          for key in ('ggxmlPath', 'sha256')}
        result['children'] = [capture(child, bounds, attrs) for child in node['children']]
        return result

    tree = capture(source)
    controls = {node['id']: node for node in walk(tree) if node['id']}
    button = controls['EndTurnButton']
    button['disabled'] = disabled
    button['buttonState'] = 'disabled' if disabled else 'hover' if hovered else 'normal'
    for name in ('Production', 'Science', 'FreeTech', 'EndTurn'):
        controls['EndTurnButton' + name + 'Alpha']['hidden'] = name != highlight
    controls['EndTurnButtonMouseOverAlpha']['hidden'] = highlight is not None
    bounds = {name: button[name] for name in ('x', 'y', 'width', 'height')}
    targets = [] if disabled else [
        {'key': button['key'], 'id': 'EndTurnButton', 'event': event,
         'visible': True, 'disabled': False, 'bounds': bounds, 'clippedBounds': dict(bounds)}
        for event in ('LeftClick', 'RightClick')]
    return {'contextName': 'ActionInfoPanel', 'popupKind': 'ActionInfoPanel',
            'active': True, 'nonmodal': True, 'timerSemaphore': 0, 'lifecycle': ['queued'],
            'presentationClock': clock, 'animationPolicy': 'ZEROSIS_FRONTEND_XML_TIMELINE_V1',
            'retailTimingVerified': False, 'fontMetrics': metrics,
            'actionInfoPanel': copy.deepcopy(source['actionInfoPanel']),
            'tree': tree, 'inputTargets': targets, 'scrollTargets': []}


_notification_component = None


def notification_component():
    global _notification_component
    if _notification_component is None:
        tests_path = str(PROJECT / 'Tests')
        if tests_path not in sys.path:
            sys.path.insert(0, tests_path)
        from notification_panel_scene import verify_component
        _notification_component = verify_component(include_snapshot=True)
    return _notification_component


def notification_fixture():
    return copy.deepcopy(notification_component()['retained_snapshot'])


class ActionInfoPanelTests(unittest.TestCase):
    def test_original_catalog_and_notification_declaration_are_preserved(self):
        before = {path: sha256(path) for path in (XML, LUA)}
        root = ET.parse(XML).getroot()
        raw = ET.tostring(root)
        prepared = freezer.action_info_panel_control_tree(root)
        self.assertEqual(ET.tostring(root), raw)
        self.assertEqual(dict(freezer.SCRIPTS)['ActionInfoPanel'], LUA.relative_to(GAME).as_posix())
        self.assertIn(('ActionInfoPanelLayout', XML.relative_to(GAME).as_posix(), 'ActionInfoPanel'), freezer.LAYOUTS)
        self.assertFalse(any(node['kind'] == 'LuaContext' for node in walk(prepared)))
        declaration = prepared['actionInfoPanel']['unconnectedLuaContexts']
        self.assertEqual(declaration, [{'kind': 'LuaContext', 'attributes': dict(root.find('LuaContext').attrib), 'children': []}])
        self.assertFalse(prepared['actionInfoPanel']['notificationPanelIntegrated'])
        self.assertEqual(len(list(walk(prepared))) + 1, len(list(root.iter())))
        self.assertEqual(before, {path: sha256(path) for path in before})

    def test_preparer_rejects_missing_duplicate_or_substituted_child_declaration(self):
        for mutation in ('missing', 'duplicate', 'file', 'inline'):
            root = ET.parse(XML).getroot()
            child = root.find('LuaContext')
            if mutation == 'missing': root.remove(child)
            elif mutation == 'duplicate': root.append(copy.deepcopy(child))
            elif mutation == 'file': child.set('FileName', 'OtherNotificationPanel')
            else: ET.SubElement(child, 'Label')
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                freezer.action_info_panel_control_tree(root)

    def test_original_1920_anchor_left_right_and_disabled_input_contract(self):
        self.assertIn('action-info-panel', SCENE_CONTEXTS)
        self.assertIn('action-info-panel', driver.CONTEXTS)
        for disabled in (False, True):
            snapshot = fixture(disabled=disabled)
            proof = action_info_panel_contract(snapshot)
            self.assertEqual(proof['end_turn_bounds'], [1584, 844, 320, 36])
            self.assertEqual(proof['callback_events'], [] if disabled else ['LeftClick', 'RightClick'])
            self.assertFalse(proof['full_notification_workflow_verified'])

    def test_driver_parses_full_original_action_info_request_line(self):
        # The first native ActionInfo request failed before rendering because the
        # protocol regex omitted a context already present in the mapping table.
        session = PROJECT / ('Build/InteractiveGameRuntime/20261009T125902Z_fd5dbd6a907a/'
                             'sessions/547c1ff010dfc41535e9ae1637665fb0')
        snapshot, folder = str(session / 'play-ui-2.json'), str(session / 'play-ui-2')
        line = f'INTERACTIVE_UI_SCENE_REQUEST=2|action-info-panel|{snapshot}|{folder}'
        for ending in ('', '\n', '\r\n'):
            self.assertEqual(driver.parse_scene_request(line + ending),
                             (2, 'action-info-panel', snapshot, folder))
        for context in sorted(driver.CONTEXTS):
            with self.subTest(context=context):
                self.assertEqual(driver.parse_scene_request(line.replace('|action-info-panel|', f'|{context}|')),
                                 (2, context, snapshot, folder))
        for invalid in (line.replace('|action-info-panel|', '|unknown-panel|'),
                        line.replace('=2|', '=0|'), line.replace('=2|', '=02|'),
                        line.rsplit('|', 1)[0], line + '|extra'):
            with self.subTest(invalid=invalid), self.assertRaisesRegex(RuntimeError, 'Malformed INTERACTIVE'):
                driver.parse_scene_request(invalid)

    def test_rejects_changed_geometry_source_callback_or_fake_child_vm(self):
        baseline = fixture()
        for mutation in ('anchor', 'hash', 'missing_right', 'wrong_key', 'wrong_clip', 'timer', 'integrated', 'child'):
            snapshot = copy.deepcopy(baseline)
            if mutation == 'anchor': snapshot['tree']['children'][0]['x'] -= 1
            elif mutation == 'hash': snapshot['actionInfoPanel']['originalLua']['sha256'] = '0' * 64
            elif mutation == 'missing_right': snapshot['inputTargets'].pop()
            elif mutation == 'wrong_key': snapshot['inputTargets'][0]['key'] += 1
            elif mutation == 'wrong_clip': snapshot['inputTargets'][0]['clippedBounds']['width'] -= 1
            elif mutation == 'timer': snapshot['timerSemaphore'] = 1
            elif mutation == 'integrated': snapshot['actionInfoPanel']['notificationPanelIntegrated'] = True
            else: snapshot['tree']['children'].append({'kind': 'LuaContext'})
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                action_info_panel_contract(snapshot)

    def test_real_original_textures_alpha_scroll_and_serialized_manifest(self):
        for highlight in ('Production', 'Science', 'FreeTech'):
            with self.subTest(highlight=highlight), tempfile.TemporaryDirectory(prefix='action-info-component-', dir=PROJECT / 'Tests') as name:
                directory = Path(name).resolve(strict=True)
                self.assertTrue(directory.is_relative_to(PROJECT))
                snapshot = fixture(highlight=highlight, hovered=True)
                path = directory / 'snapshot.json'
                path.write_text(json.dumps(snapshot), encoding='utf8')
                (directory / 'inline_colors.json').write_text('{"colors":{}}', encoding='utf8')
                (directory / 'inline_icons.json').write_text('{"icons":{}}', encoding='utf8')
                manifest_path = directory / 'scene_manifest.json'
                render_ui_popup.prepare(path, directory, manifest_path, context='action-info-panel')
                manifest = json.loads(manifest_path.read_text(encoding='utf8'))
                driver.validate_action_info_panel_scene_proof(snapshot, manifest)
                self.assertEqual(manifest['packet_version'], 'ZSUPIX02')
                self.assertEqual(len(manifest['hit_regions']), 1)
                self.assertTrue(any(row['id'] == 'EndTurnText' for row in manifest['geometry']))
                compiler = Compiler(GAME, directory / 'alpha-check', context='action-info-panel', snapshot_clock=0.25)
                compiler.compile(snapshot)
                alpha = next(node for node in walk(snapshot['tree']) if node['id'] == 'EndTurnButton' + highlight + 'Alpha')
                child_keys = {node['key'] for child in alpha['children'] for node in walk(child)}
                child_sprites = [sprite for sprite in compiler.sprites if sprite[1] in child_keys]
                self.assertTrue(child_sprites)
                self.assertTrue(all(abs(sprite[-1] - alpha['animation']['alpha']) < 1e-9 for sprite in child_sprites))
                self.assertEqual(len(compiler.derived_textures), 1)
                self.assertEqual((compiler.derived_textures[0]['width'], compiler.derived_textures[0]['height']), (320, 48))
                changed = copy.deepcopy(manifest)
                changed['action_info_panel_scene']['notificationPanelIntegrated'] = True
                with self.assertRaises(RuntimeError): driver.validate_action_info_panel_scene_proof(snapshot, changed)
                self.assertEqual(json.loads(path.read_text(encoding='utf8')), json.loads(json.dumps(snapshot)))

    def test_actual_original_lua_component_snapshot_compiles(self):
        from action_info_panel_scene import verify_component
        result = verify_component(include_snapshot=True)
        self.assertEqual(result['status'], 'PASS_ORIGINAL_ACTION_INFO_LUA_COMPONENT')
        self.assertFalse(result['live_sdk_verified'])
        snapshot = result['retained_snapshot']
        with tempfile.TemporaryDirectory(prefix='action-info-lua-render-', dir=PROJECT / 'Tests') as name:
            directory = Path(name).resolve(strict=True)
            self.assertTrue(directory.is_relative_to(PROJECT))
            path = directory / 'snapshot.json'
            path.write_text(json.dumps(snapshot), encoding='utf8')
            (directory / 'inline_colors.json').write_text('{"colors":{}}', encoding='utf8')
            (directory / 'inline_icons.json').write_bytes((PROJECT / 'evidence/ui_popup/assets/inline_icons.json').read_bytes())
            manifest_path = directory / 'scene_manifest.json'
            render_ui_popup.prepare(path, directory, manifest_path, context='action-info-panel')
            manifest = json.loads(manifest_path.read_text(encoding='utf8'))
            driver.validate_action_info_panel_scene_proof(snapshot, manifest)
            self.assertEqual(len(manifest['hit_regions']), 1)
            self.assertFalse(manifest['action_info_panel_scene']['notificationPanelIntegrated'])

    def test_driver_flag_explicitly_enables_or_clears_inherited_environment(self):
        with tempfile.TemporaryDirectory(prefix='action-info-env-', dir=PROJECT / 'Tests') as name:
            directory = Path(name).resolve(strict=True)
            support = directory / 'support.json'
            support.write_text('{}', encoding='utf8')
            for enabled in (False, True):
                with self.subTest(enabled=enabled), patch.dict(os.environ, {'ZEROSIS_PLAY_ACTION_INFO_PANEL': 'stale'}), \
                        patch.object(driver.subprocess, 'Popen', side_effect=RuntimeError('component-stop')) as launch:
                    with self.assertRaisesRegex(RuntimeError, 'component-stop'):
                        driver.drive(['not-executed'], cwd=directory, runtime=directory, tools_dir=directory,
                                     icons_source=support, support_manifest=support, support_manifest_sha256=sha256(support),
                                     timeout=0, scene_timeout=60, report_path=directory / 'unused.json', action_info_panel=enabled)
                    actual = launch.call_args.kwargs['env']
                    self.assertEqual(actual.get('ZEROSIS_PLAY_ACTION_INFO_PANEL'), '1' if enabled else None)

    def test_notification_panel_binds_original_rows_templates_and_registered_events(self):
        self.assertIn('notification-panel', SCENE_CONTEXTS)
        self.assertIn('notification-panel', driver.CONTEXTS)
        snapshot = notification_fixture()
        proof = notification_panel_contract(snapshot)
        self.assertEqual(proof['notification_ids'], list(range(100, 112)))
        self.assertEqual(proof['template_count'], 70)
        self.assertEqual(proof['dynamic_instance_count'], 12)
        self.assertEqual(proof['callback_events_per_notification'], {
            str(notification_id): ['LeftClick', 'RightClick'] for notification_id in range(100, 108)})
        self.assertEqual(len(proof['consumer_target_keys']), 8)
        self.assertFalse(proof['all_notification_destinations_integrated'])
        reordered = copy.deepcopy(snapshot)
        reordered['notificationPanel']['notifications'].reverse()
        self.assertEqual(notification_panel_contract(reordered)['dynamic_instance_count'], 12)

    def test_notification_panel_maps_fixed_big_stack_buttons_separately_from_instances(self):
        snapshot = notification_fixture()
        def strip_instances(node):
            node['children'] = [child for child in node['children'] if not child.get('instanceTemplate')]
            for child in node['children']:
                strip_instances(child)
        strip_instances(snapshot['tree'])
        rows = snapshot['notificationPanel']['notifications']
        production, tech = copy.deepcopy(rows[0]), copy.deepcopy(rows[1])
        production.update(id=100, type=0x77014c62, tooltip='production', summary='production')
        tech.update(id=101, type=0x5acfa6f7, tooltip='technology', summary='technology')
        snapshot['notificationPanel']['notifications'] = [production, tech]
        snapshot['inputTargets'] = []
        fixed = {node['id']: node for node in walk(snapshot['tree'])
                 if node.get('id') in ('ProductionButton', 'TechButton')}
        self.assertEqual(set(fixed), {'ProductionButton', 'TechButton'})
        for control_id, y, notification_id in (('TechButton', 634, 101), ('ProductionButton', 734, 100)):
            node = fixed[control_id]
            node.update(hidden=False, x=1820, y=y, width=100, height=100)
            bounds = {'x': 1820, 'y': y, 'width': 100, 'height': 100}
            for event in ('LeftClick', 'RightClick'):
                snapshot['inputTargets'].append({
                    'key': node['key'], 'id': control_id, 'event': event, 'void1': notification_id,
                    'visible': True, 'disabled': False, 'consumeMouse': False,
                    'bounds': dict(bounds), 'clippedBounds': dict(bounds),
                })
        proof = notification_panel_contract(snapshot)
        self.assertEqual(proof['fixed_notification_controls'], ['Production', 'Tech'])
        self.assertEqual(proof['dynamic_instance_count'], 0)
        self.assertEqual(proof['notification_ids'], [100, 101])

        missing = copy.deepcopy(snapshot)
        missing['inputTargets'].pop()
        with self.assertRaisesRegex(ValueError, 'fixed notification control'):
            notification_panel_contract(missing)

        mismatched = copy.deepcopy(snapshot)
        mismatched['notificationPanel']['notifications'][0]['type'] = 0x5acfa6f7
        with self.assertRaises(ValueError):
            notification_panel_contract(mismatched)

        # Stock Lua reuses one fixed button for duplicate type rows. An update
        # can Remove/Add an older SDK row after a newer row; the current valid
        # callback payload is therefore a member of the class, not necessarily
        # the last row in the current SDK array. Removing any one row can hide
        # the shared button while another SDK row remains.
        shared = copy.deepcopy(snapshot)
        first, second = copy.deepcopy(shared['notificationPanel']['notifications'][0]), \
            copy.deepcopy(shared['notificationPanel']['notifications'][0])
        first['id'], second['id'] = 200, 201
        shared['notificationPanel']['notifications'] = [first, second]
        shared['inputTargets'] = [target for target in shared['inputTargets']
                                  if target['id'] == 'ProductionButton']
        for target in shared['inputTargets']:
            target['void1'] = 201
        fixed_shared = {node['id']: node for node in walk(shared['tree'])
                        if node.get('id') in ('ProductionButton', 'TechButton')}
        fixed_shared['TechButton']['hidden'] = True
        proof = notification_panel_contract(shared)
        self.assertEqual(proof['notification_ids'], [200, 201])
        self.assertEqual(proof['fixed_notification_controls'], ['Production'])
        reordered = copy.deepcopy(shared)
        reordered['notificationPanel']['notifications'].reverse()
        for target in reordered['inputTargets']:
            target['void1'] = 200
        self.assertEqual(notification_panel_contract(reordered)['notification_ids'], [201, 200])
        invalid_shared_payload = copy.deepcopy(shared)
        for target in invalid_shared_payload['inputTargets']:
            target['void1'] = 999
        with self.assertRaisesRegex(ValueError, 'active SDK ID of its type'):
            notification_panel_contract(invalid_shared_payload)

        hidden_shared = copy.deepcopy(shared)
        hidden_shared['inputTargets'] = []
        for node in walk(hidden_shared['tree']):
            if node.get('id') in ('ProductionButton', 'TechButton'):
                node['hidden'] = True
        hidden_proof = notification_panel_contract(hidden_shared)
        self.assertEqual(hidden_proof['notification_count'], 2)
        self.assertEqual(hidden_proof['visible_input_target_count'], 0)
        self.assertTrue(hidden_proof['zero_hit_regions_are_originally_valid'])
        with tempfile.TemporaryDirectory(prefix='notification-hidden-fixed-', dir=PROJECT / 'Tests') as name:
            directory = Path(name).resolve(strict=True)
            path = directory / 'snapshot.json'
            path.write_text(json.dumps(hidden_shared), encoding='utf8')
            (directory / 'inline_colors.json').write_text('{"colors":{}}', encoding='utf8')
            (directory / 'inline_icons.json').write_bytes(
                (PROJECT / 'evidence/ui_popup/assets/inline_icons.json').read_bytes())
            manifest_path = directory / 'scene_manifest.json'
            render_ui_popup.prepare(path, directory, manifest_path, context='notification-panel')
            manifest = json.loads(manifest_path.read_text(encoding='utf8'))
            driver.validate_notification_panel_scene_proof(hidden_shared, manifest)
            self.assertEqual(manifest['hit_regions'], [])
            self.assertEqual(len(manifest['scroll_regions']), 1)

    def test_notification_panel_rejects_forged_source_lifecycle_template_and_callbacks(self):
        baseline = notification_fixture()
        mutations = ('source_hash', 'source_bytes', 'timer', 'unknown_template', 'source_control',
                     'missing_right', 'wrong_id', 'extra_destination')
        for mutation in mutations:
            snapshot = copy.deepcopy(baseline)
            if mutation == 'source_hash':
                snapshot['notificationPanel']['originalXml']['sha256'] = '0' * 64
            elif mutation == 'source_bytes':
                snapshot['notificationPanel']['originalXml']['bytes'] = 0
            elif mutation == 'timer':
                snapshot['timerSemaphore'] = 1
            elif mutation == 'unknown_template':
                next(node for node in walk(snapshot['tree']) if node.get('instanceTemplate'))['instanceTemplate'] = 'NotOriginal'
            elif mutation == 'source_control':
                next(node for node in walk(snapshot['tree']) if node['id'] == 'GenericButton')['sourceAttributes']['ID'] = 'FakeButton'
            elif mutation == 'missing_right':
                snapshot['inputTargets'].pop()
            elif mutation == 'wrong_id':
                snapshot['inputTargets'][0]['void1'] = 999
            else:
                snapshot['notificationPanel']['allNotificationDestinationsIntegrated'] = True
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                notification_panel_contract(snapshot)

    def test_actual_notification_component_snapshot_compiles_with_clipped_rows_and_blockers(self):
        result = notification_component()
        self.assertTrue(result['status'].startswith('PASS_'))
        self.assertFalse(result['nativePixelsVerified'])
        self.assertFalse(result['nativeSdkVerified'])
        snapshot = result['retained_snapshot']
        proof = notification_panel_contract(snapshot)
        self.assertEqual(proof['notification_count'], 12)
        self.assertEqual(proof['dynamic_instance_count'], 12)
        self.assertEqual(len(proof['consumer_target_keys']), 8)
        self.assertEqual(len(snapshot['inputTargets']), 24)
        missing_consumer = copy.deepcopy(snapshot)
        missing_consumer['inputTargets'] = [row for row in missing_consumer['inputTargets']
                                            if row['event'] != 'ConsumeMouse']
        with self.assertRaisesRegex(ValueError, 'mouse-consuming Container'):
            notification_panel_contract(missing_consumer)
        with tempfile.TemporaryDirectory(prefix='notification-panel-lua-render-', dir=PROJECT / 'Tests') as name:
            directory = Path(name).resolve(strict=True)
            self.assertTrue(directory.is_relative_to(PROJECT))
            path = directory / 'snapshot.json'
            path.write_text(json.dumps(snapshot), encoding='utf8')
            (directory / 'inline_colors.json').write_text('{"colors":{}}', encoding='utf8')
            (directory / 'inline_icons.json').write_bytes(
                (PROJECT / 'evidence/ui_popup/assets/inline_icons.json').read_bytes())
            manifest_path = directory / 'scene_manifest.json'
            render_ui_popup.prepare(path, directory, manifest_path, context='notification-panel')
            manifest = json.loads(manifest_path.read_text(encoding='utf8'))
            driver.validate_notification_panel_scene_proof(snapshot, manifest)
            self.assertEqual(len(manifest['hit_regions']), 16)
            self.assertEqual(len(manifest['scroll_regions']), 1)
            self.assertFalse(manifest['notification_panel_scene']['all_notification_destinations_integrated'])

    def test_notification_empty_sdk_inventory_alone_allows_zero_hit_regions(self):
        snapshot = notification_fixture()
        snapshot['notificationPanel']['notifications'] = []
        snapshot['inputTargets'] = []
        def strip_instances(node):
            node['children'] = [child for child in node['children'] if not child.get('instanceTemplate')]
            for child in node['children']:
                strip_instances(child)
        strip_instances(snapshot['tree'])
        outer = next(node for node in walk(snapshot['tree']) if node['id'] == 'OuterStack')
        def translate(node):
            node['x'] += 20
            for child in node['children']:
                translate(child)
        translate(outer)  # Empty SmallStack makes stock ProcessStackSizes reset its horizontal offset.
        panel = next(node for node in walk(snapshot['tree']) if node['id'] == 'SmallScrollPanel')
        panel['contentHeight'] = 0
        panel['scrollY'] = 0
        for node in walk(panel):
            if node['id'] in ('ScrollBar', 'UpButton', 'DownButton'):
                node['hidden'] = True
        target = snapshot['scrollTargets'][0]
        target['bounds']['x'] += 20
        target['clippedBounds']['x'] += 20
        target.update(contentHeight=0, maximumScroll=0, scrollY=0)
        proof = notification_panel_contract(snapshot)
        self.assertEqual(proof['notification_count'], 0)
        self.assertEqual(proof['consumer_target_keys'], [])
        nonempty = copy.deepcopy(snapshot)
        nonempty['notificationPanel']['notifications'] = [
            {'id': 100, 'type': 1, 'tooltip': '', 'summary': '', 'gameData': -1,
             'extraGameData': -1, 'player': 0, 'x': -1, 'y': -1}]
        with self.assertRaisesRegex(ValueError, 'original notification rows'):
            notification_panel_contract(nonempty)
        with tempfile.TemporaryDirectory(prefix='notification-empty-render-', dir=PROJECT / 'Tests') as name:
            directory = Path(name).resolve(strict=True)
            path = directory / 'snapshot.json'
            path.write_text(json.dumps(snapshot), encoding='utf8')
            (directory / 'inline_colors.json').write_text('{"colors":{}}', encoding='utf8')
            (directory / 'inline_icons.json').write_bytes(
                (PROJECT / 'evidence/ui_popup/assets/inline_icons.json').read_bytes())
            manifest_path = directory / 'scene_manifest.json'
            render_ui_popup.prepare(path, directory, manifest_path, context='notification-panel')
            manifest = json.loads(manifest_path.read_text(encoding='utf8'))
            driver.validate_notification_panel_scene_proof(snapshot, manifest)
            self.assertEqual(manifest['hit_regions'], [])
            self.assertEqual(len(manifest['scroll_regions']), 1)

    def test_notification_original_slide_and_finger_timing_candidates_are_source_bound(self):
        styles = {node.tag: node.attrib for node in ET.parse(GAME / 'Assets/UI/Styles.xml').getroot()}
        slide = styles['NotificationSlide']
        for elapsed in (0, 0.5, 1.0):
            phase = min(1.0, elapsed / float(slide['Speed']))
            offset_y = 500.0 * (1.0 - phase ** float(slide['FunctionPower']))
            animation = {'clock': elapsed, 'elapsed': elapsed, 'running': elapsed <= 1.0,
                         'phase': phase, 'offsetX': 0.0, 'offsetY': offset_y,
                         'timingPolicy': 'CIV5_NOTIFICATION_SLIDE_ROOT_CANDIDATE_V1',
                         'geometryPolicy': 'CIV5_NOTIFICATION_SLIDE_PARENT_FRAME_CANDIDATE_V1',
                         'retailTimingVerified': False, 'retailGeometryVerified': False}
            measured_phase, offset = notification_slide_transform(slide, animation, elapsed)
            self.assertAlmostEqual(measured_phase, phase)
            self.assertAlmostEqual(offset[1], offset_y)
        bad = copy.deepcopy(animation)
        bad['offsetY'] += 1
        with self.assertRaisesRegex(ValueError, 'transform'):
            notification_slide_transform(slide, bad, bad['clock'])
        finger = styles['NewFinger']
        for elapsed, alpha in ((0.5, 0.5), (3.0, 1.0), (6.5, 0.5), (7.5, 0.0)):
            animation = {'clock': elapsed, 'elapsed': elapsed, 'alpha': alpha,
                         'effectiveSpeed': 1, 'defaultSpeedUsed': True,
                         'timingPolicy': 'CIV5_NOTIFICATION_ONE_BOUNCE_CANDIDATE_V1',
                         'retailTimingVerified': False}
            self.assertAlmostEqual(notification_one_bounce_alpha(finger, animation, elapsed), alpha)
        animation['alpha'] = 0.75
        with self.assertRaisesRegex(ValueError, 'OneBounce candidate phase'):
            notification_one_bounce_alpha(finger, animation, animation['clock'])

    def test_notification_driver_requires_action_panel_and_sets_explicit_environment(self):
        with tempfile.TemporaryDirectory(prefix='notification-panel-env-', dir=PROJECT / 'Tests') as name:
            directory = Path(name).resolve(strict=True)
            support = directory / 'support.json'
            support.write_text('{}', encoding='utf8')
            with self.assertRaisesRegex(RuntimeError, 'requires --action-info-panel'):
                driver.drive(['not-executed'], cwd=directory, runtime=directory, tools_dir=directory,
                             icons_source=support, support_manifest=support, support_manifest_sha256=sha256(support),
                             timeout=0, scene_timeout=60, report_path=directory / 'unused.json',
                             notification_panel=True)
            with patch.dict(os.environ, {'ZEROSIS_PLAY_NOTIFICATION_PANEL': 'stale'}), \
                    patch.object(driver.subprocess, 'Popen', side_effect=RuntimeError('component-stop')) as launch:
                with self.assertRaisesRegex(RuntimeError, 'component-stop'):
                    driver.drive(['not-executed'], cwd=directory, runtime=directory, tools_dir=directory,
                                 icons_source=support, support_manifest=support, support_manifest_sha256=sha256(support),
                                 timeout=0, scene_timeout=60, report_path=directory / 'unused.json',
                                 action_info_panel=True, notification_panel=True)
                self.assertEqual(launch.call_args.kwargs['env']['ZEROSIS_PLAY_NOTIFICATION_PANEL'], '1')


if __name__ == '__main__':
    unittest.main()
