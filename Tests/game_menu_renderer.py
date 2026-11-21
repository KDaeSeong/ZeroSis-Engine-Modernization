"""Render the installed GameMenu in its real retained Lua component context.

Native APIs are explicit component fixtures. This proves source/packet contracts,
not a running Host, user gameplay, native saving, or retail pixel equivalence.
All packet textures/manifests live in one guarded temporary Build directory.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import struct
import sys
import unittest

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / 'tools'))

import interactive_ui_driver as driver
import prepare_ui_popup_assets as freezer
import render_ui_popup
from civ5_ui_assets import sha256
from game_menu_ui_assets import small_source_directory
from ui_pixel_scene import SCENE_CONTEXTS, game_menu_contract, game_menu_once_alpha


_components = {}


def component(*, touch=False):
    if touch not in _components:
        from game_menu_scene import verify_component
        _components[touch] = verify_component(include_snapshot=True, touch=touch)
    return _components[touch]


def walk(node):
    yield node
    for child in node['children']:
        yield from walk(child)


def render(snapshot, directory, *, closed=False):
    directory.mkdir()
    source = directory / 'snapshot.json'
    manifest = directory / 'manifest.json'
    source.write_text(json.dumps(snapshot, ensure_ascii=False), encoding='utf8')
    (directory / 'inline_colors.json').write_text('{"colors":{}}', encoding='utf8')
    (directory / 'inline_icons.json').write_text('{"icons":{}}', encoding='utf8')
    before = sha256(source)
    render_ui_popup.prepare(source, directory, manifest, context='game-menu', closed=closed)
    assert sha256(source) == before
    return json.loads(manifest.read_text(encoding='utf8'))


def packet_records(manifest):
    data = Path(manifest['packet']['path']).read_bytes()
    assert data[:8] == b'ZSUPIX02'
    _, _, textures, sprites, hits, scrolls = struct.unpack_from('<6I', data, 8)
    offset = 32
    for _ in range(textures):
        length, = struct.unpack_from('<I', data, offset)
        offset += 4 + length
    result = {}
    for name, count, fmt in (('sprites', sprites, '<IQ16f'), ('hits', hits, '<Q4f'),
                             ('scrolls', scrolls, '<Q4f')):
        size = struct.calcsize(fmt)
        result[name] = [struct.unpack_from(fmt, data, offset + index * size) for index in range(count)]
        offset += count * size
    assert offset == len(data)
    return result


def packet_hit(hits, x, y):
    # BitmapWindow.cpp::HitTestLogicalPoint uses this reverse ordered, half-open
    # rectangle rule before any pixel-hit fallback. This does not run native code.
    return next((key for key, left, top, right, bottom in reversed(hits)
                 if left <= x < right and top <= y < bottom), 0)


class GameMenuRendererTests(unittest.TestCase):
    def test_driver_recognizes_only_the_exact_menu_scene_name(self):
        self.assertIn('game-menu', SCENE_CONTEXTS)
        self.assertIn('game-menu', driver.CONTEXTS)
        folder = PROJECT / 'Build/menu-contract-protocol-only/sessions/component/play-ui-1'
        snapshot = folder.with_suffix('.json')
        line = f'INTERACTIVE_UI_SCENE_REQUEST=1|game-menu|{snapshot}|{folder}'
        self.assertEqual(driver.parse_scene_request(line), (1, 'game-menu', str(snapshot), str(folder)))
        for invalid in (line.replace('|game-menu|', '|game-menu-child|'),
                        line.replace('=1|', '=0|'), line + '|unexpected'):
            with self.subTest(line=invalid), self.assertRaises(RuntimeError):
                driver.parse_scene_request(invalid)
        self.assertFalse(folder.exists())

    def test_once_fade_boundaries_and_forged_timeline_are_checked(self):
        attrs = {'Cycle': 'Once', 'AlphaStart': '.2', 'AlphaEnd': '0', 'Speed': '1', 'Pause': '0'}
        for elapsed in (0, .25, 1):
            animation = {'clock': 5 + elapsed, 'alpha': .2 * (1 - elapsed), 'elapsed': elapsed,
                         'normalizedPhase': elapsed, 'activationStartTime': 5,
                         'running': elapsed < 1, 'completed': elapsed == 1,
                         'timingPolicy': 'CIV5_GAME_MENU_ONCE_HOVER_CANDIDATE_V1',
                         'retailTimingVerified': False,
                         'childOpacityPolicy': 'MULTIPLY_CAPTURED_ALPHA_THROUGH_DESCENDANTS'}
            self.assertEqual(game_menu_once_alpha(attrs, animation, animation['clock']), animation['alpha'])
            for field, value in (('alpha', .9), ('elapsed', -1), ('normalizedPhase', 2),
                                 ('activationStartTime', 100), ('completed', not animation['completed']),
                                 ('timingPolicy', 'retail'), ('retailTimingVerified', True),
                                 ('childOpacityPolicy', 'IGNORE_CHILDREN')):
                changed = {**animation, field: value}
                with self.subTest(elapsed=elapsed, field=field), self.assertRaises(ValueError):
                    game_menu_once_alpha(attrs, changed, animation['clock'])

    def test_real_original_snapshot_sources_children_and_callbacks(self):
        snapshot = copy.deepcopy(component()['retained_snapshot'])
        proof = game_menu_contract(snapshot)
        self.assertFalse(proof['child_contexts_runtime_verified'])
        self.assertEqual(len(proof['unconnectedLuaContexts']), 5)
        self.assertIn('ReturnButton', proof['callback_control_ids'])
        self.assertIn('QuickSaveButton', proof['callback_control_ids'])
        self.assertFalse(proof['retail_pixels_verified'])
        before = copy.deepcopy(snapshot)
        for mutation in ('child_visible', 'child_source', 'hash', 'caption', 'missing_node',
                         'callback_key', 'callback_event', 'callback_removed', 'frame', 'timer',
                         'confirmation_flag', 'unavailable_action', 'yes_hidden', 'yes_disabled'):
            changed = copy.deepcopy(snapshot)
            nodes = list(walk(changed['tree']))
            child = next(node for node in nodes if node.get('id') == 'SaveMenu')
            button = next(node for node in nodes if node.get('id') == 'QuickSaveButton')
            if mutation == 'child_visible': child['hidden'] = False
            elif mutation == 'child_source': child['sourceAttributes']['FileName'] = 'Other'
            elif mutation == 'hash': changed['gameMenu']['originalLua']['sha256'] = '0' * 64
            elif mutation == 'caption': button['attributes']['String'] = 'Replacement save label'
            elif mutation == 'missing_node': changed['tree']['children'].remove(child)
            elif mutation == 'callback_key': changed['inputTargets'][0]['key'] += 100000
            elif mutation == 'callback_event': changed['inputTargets'][0]['event'] = 'RightClick'
            elif mutation == 'callback_removed': changed['inputTargets'].pop()
            elif mutation == 'frame':
                next(node for node in changed['tree']['children'] if node['kind'] == 'Grid')['x'] += 1
            elif mutation == 'timer': changed['timerSemaphore'] = 0
            elif mutation == 'confirmation_flag': changed['gameMenu']['confirmationVisible'] = True
            elif mutation == 'unavailable_action': changed['gameMenu']['unavailableAction'] = 'ForeignMenu'
            else:
                yes = next(node for node in nodes if node.get('id') == 'Yes')
                yes['hidden' if mutation == 'yes_hidden' else 'disabled'] = True
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                game_menu_contract(changed)
        self.assertEqual(snapshot, before)

    def test_original_consumer_order_and_modal_input_reject_forgery(self):
        snapshots = component()
        notice = snapshots['notice_snapshot']
        proof = game_menu_contract(notice)
        self.assertEqual(proof['modal_input_policy'], 'ORIGINAL_EXIT_CONFIRM_AND_LATER_TREE_ORDER')
        before = copy.deepcopy(notice)
        for mutation in ('missing_consumer', 'reordered_consumer', 'style_consumption', 'consumer_bounds',
                         'consumer_disabled', 'behind_callback', 'callback_payload', 'callback_pressed',
                         'behind_scroll'):
            changed = copy.deepcopy(snapshots['details_notice_snapshot'] if mutation == 'behind_scroll' else notice)
            nodes = {node.get('id'): node for node in walk(changed['tree']) if node.get('id')}
            blocker = next(target for target in changed['inputTargets'] if target['id'] == 'ExitConfirm')
            no = next(target for target in changed['inputTargets'] if target['id'] == 'No')
            if mutation == 'missing_consumer': changed['inputTargets'].remove(blocker)
            elif mutation == 'reordered_consumer':
                changed['inputTargets'].remove(blocker)
                changed['inputTargets'].append(blocker)
            elif mutation == 'style_consumption': nodes['ExitConfirm']['attributes']['ConsumeMouse'] = '0'
            elif mutation == 'consumer_bounds': blocker['clippedBounds']['width'] -= 1
            elif mutation == 'consumer_disabled': blocker['disabled'] = not blocker['disabled']
            elif mutation == 'behind_callback':
                changed['inputTargets'].append(copy.deepcopy(next(target for target in
                    snapshots['retained_snapshot']['inputTargets'] if target['id'] == 'QuickSaveButton')))
            elif mutation == 'callback_payload': no['void1'] = 'unsupported callback payload'
            elif mutation == 'callback_pressed': nodes['No']['buttonState'] = 'pressed'
            else: changed['scrollTargets'] = copy.deepcopy(snapshots['details_snapshot']['scrollTargets'])
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                game_menu_contract(changed)
        self.assertEqual(notice, before)

    def test_real_menu_packets_preserve_captions_hover_opacity_and_details(self):
        original_paths = [freezer.GAME / path for path in
                          (freezer.GAME_MENU_LUA, freezer.GAME_MENU_XML, freezer.MAP_UTILITIES_LUA,
                           freezer.STYLE_SOURCE)]
        before = {path: sha256(path) for path in original_paths}
        snapshots = {**component(),
                     'confirmation_touch_snapshot': component(touch=True)['confirmation_touch_snapshot']}
        packets = []
        with small_source_directory() as directory:
            for name in ('retained_snapshot', 'animation_snapshot', 'details_snapshot',
                         'notice_snapshot', 'restored_notice_snapshot', 'confirmation_snapshot',
                         'confirmation_touch_snapshot', 'details_notice_snapshot'):
                with self.subTest(snapshot=name):
                    snapshot = copy.deepcopy(snapshots[name])
                    manifest = render(snapshot, directory / name)
                    self.assertEqual(manifest['status'], 'STOCK_GAME_MENU_COMPONENT_SCENE_COMPILED')
                    self.assertEqual(manifest['packet_version'], 'ZSUPIX02')
                    self.assertEqual(manifest['game_menu_scene'], game_menu_contract(snapshot))
                    driver.validate_game_menu_scene_proof(snapshot, manifest)
                    packet = packet_records(manifest)
                    self.assertEqual([list(row) for row in packet['hits']], manifest['hit_regions'])
                    self.assertEqual([list(row) for row in packet['scrolls']], manifest['scroll_regions'])
                    self.assertEqual(manifest['input_target_count'], len(snapshot['inputTargets']))
                    self.assertTrue(manifest['retained_runtime_bounds_check']['checked'])
                    self.assertEqual(manifest['retained_runtime_bounds_check']['context'], 'game-menu')
                    self.assertFalse(manifest['game_menu_scene']['retail_pixels_verified'])
                    captions = {row.get('text_control_id'): row for row in manifest['labels']
                                if row.get('text_control') == 'GridButton'}
                    self.assertIn('ReturnButton', captions)
                    if name == 'retained_snapshot':
                        self.assertIn('QuickSaveButton', captions)
                        self.assertEqual(snapshot['gameMenu']['turn'], 1)
                        self.assertEqual(captions['RetireButton']['text'], '포기')
                        self.assertNotIn('TXT_KEY_RETIRE', captions['RetireButton']['plain_text'])
                        for mutation in ('source', 'hits', 'children', 'input'):
                            changed = copy.deepcopy(manifest)
                            if mutation == 'source': changed['original_context_sources'] = []
                            elif mutation == 'hits': changed['hit_regions'][0][1] += 1
                            elif mutation == 'children':
                                changed['game_menu_scene']['child_contexts_runtime_verified'] = True
                            else: changed['retained_input_targets'].pop()
                            with self.subTest(proof_mutation=mutation), self.assertRaises(RuntimeError):
                                driver.validate_game_menu_scene_proof(snapshot, changed)
                    if name == 'details_snapshot':
                        self.assertEqual(manifest['scroll_region_count'], 1)
                    if name == 'details_notice_snapshot':
                        self.assertEqual(packet['scrolls'], [])
                        self.assertTrue(any(row['kind'] == 'ScrollPanel' for row in manifest['geometry']))
                    if name in ('notice_snapshot', 'restored_notice_snapshot'):
                        notice = name == 'notice_snapshot'
                        yes = next(node for node in walk(snapshot['tree']) if node.get('id') == 'Yes')
                        self.assertFalse(yes['hidden'])
                        self.assertIs(yes['disabled'], notice)
                        self.assertIs(manifest['game_menu_scene']['confirmation_visible'], notice)
                        self.assertIs(manifest['game_menu_scene']['confirmation_yes_disabled'], notice)
                        self.assertEqual(manifest['game_menu_scene']['unavailable_action'],
                                         'LoadMenu' if notice else None)
                        target_ids = {target['id'] for target in snapshot['inputTargets']}
                        self.assertNotIn('Yes', target_ids)
                        self.assertEqual('No' in target_ids, notice)
                        confirmation_keys = {node['key'] for node in walk(snapshot['tree'])
                                             if node.get('id') in ('Yes', 'No')}
                        painted_confirmation = {row['key'] for row in manifest['geometry']
                                                if row['key'] in confirmation_keys}
                        self.assertEqual(painted_confirmation, confirmation_keys if notice else set())
                    if snapshot['gameMenu']['confirmationVisible']:
                        controls = {node['id']: node for node in walk(snapshot['tree']) if node.get('id')}
                        confirmation = controls['ExitConfirm']
                        self.assertEqual(tuple(confirmation[field] for field in ('x', 'y', 'width', 'height')),
                                         (0, 0, 1920, 1080))
                        consumers = {target['key'] for target in snapshot['inputTargets']
                                     if target['event'] == 'ConsumeMouse'}
                        self.assertIn(confirmation['key'], consumers)
                        def center(node):
                            return node['x'] + node['width'] / 2, node['y'] + node['height'] / 2
                        for behind in ('QuickSaveButton', 'ReturnButton'):
                            x, y = center(controls[behind])
                            for front in ('Yes', 'No'):
                                node = controls[front]
                                self.assertFalse(node['x'] <= x < node['x'] + node['width'] and
                                                 node['y'] <= y < node['y'] + node['height'])
                            self.assertEqual(packet_hit(packet['hits'], x, y), confirmation['key'])
                            self.assertFalse(any(target['key'] == controls[behind]['key']
                                                 for target in snapshot['inputTargets']))
                        for front in ('Yes', 'No'):
                            node = controls[front]
                            expected = confirmation['key'] if node['disabled'] else node['key']
                            self.assertEqual(packet_hit(packet['hits'], *center(node)), expected)
                        for x, y in ((0, 0), (1919.5, 0), (0, 1079.5)):
                            self.assertEqual(packet_hit(packet['hits'], x, y), confirmation['key'])
                        if name == 'confirmation_touch_snapshot':
                            touch = controls['TouchHelpButton']
                            self.assertFalse(touch['hidden'])
                            self.assertEqual(packet_hit(packet['hits'], *center(touch)), touch['key'])
                            order = [row[0] for row in packet['hits']]
                            self.assertGreater(order.index(touch['key']), order.index(controls['No']['key']))
                    if name == 'animation_snapshot':
                        once = [node for node in walk(snapshot['tree']) if node['kind'] == 'AlphaAnim' and
                                node.get('animation', {}).get('running') is True]
                        self.assertEqual(len(once), 1)
                        fade = once[0]
                        child_keys = {node['key'] for child in fade['children'] for node in walk(child)}
                        # Decode the real packet and inspect only this original
                        # fade's child sprite alphas, without repainting a mock.
                        descendant = [value for value in packet['sprites'] if value[1] in child_keys]
                        self.assertTrue(descendant)
                        for value in descendant:
                            self.assertAlmostEqual(value[-1], fade['animation']['alpha'], places=6)
                    packets.append({'snapshot': name, 'sprites': manifest['sprite_count'],
                                    'textures': manifest['texture_count'],
                                    'inputs': manifest['input_target_count'],
                                    'scrolls': manifest['scroll_region_count']})
            temporary_bytes = sum(path.stat().st_size for path in directory.rglob('*') if path.is_file())
        self.assertFalse(directory.exists())
        self.assertEqual(before, {path: sha256(path) for path in original_paths})
        print('GAME_MENU_PACKET_COMPONENT=' + json.dumps({
            'packets': packets, 'temporary_bytes': temporary_bytes,
            'temporary_directory_removed': True, 'installed_sources_unchanged': True,
            'native_execution_verified': False, 'retail_pixels_verified': False}))

    def test_closed_original_menu_has_empty_packet_without_mutating_tree(self):
        snapshot = copy.deepcopy(component()['closed_snapshot'])
        before = copy.deepcopy(snapshot)
        with small_source_directory() as directory:
            manifest = render(snapshot, directory / 'closed', closed=True)
            self.assertEqual(Path(manifest['packet']['path']).stat().st_size, 32)
            self.assertEqual(manifest['hit_regions'], [])
            self.assertEqual(manifest['scroll_regions'], [])
            self.assertTrue(manifest['game_menu_scene']['closed'])
            self.assertEqual(manifest['game_menu_scene']['timer_semaphore'], 0)
            driver.validate_game_menu_scene_proof(snapshot, manifest, closed=True)
        self.assertFalse(directory.exists())
        self.assertEqual(snapshot, before)


if __name__ == '__main__':
    unittest.main()
