"""Read-only checkbox/default and full-source tree contracts, without Lua or UI.

The synthetic snapshots below test source/schema rejection only. They are not
runtime, pixel, input-dispatch, native backend, or retail-default evidence.
Only the selected installed UI XML/Lua and two tiny original FPK entries are
read; no texture, fixture directory, compiler, Host or game is created.
"""
from contextlib import ExitStack
from copy import deepcopy
import ctypes
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

PROJECT = Path(__file__).absolute().parents[1]
sys.path.insert(0, str(PROJECT / 'tools'))

import prepare_ui_popup_assets as freezer
from civ5_ui_assets import Fpk
from ui_pixel_scene import Compiler, anchor, game_menu_contract, load_menu_controls_contract, pair


class LoadMenuCheckboxAssets(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.guards = ExitStack()
        cls.addClassCleanup(cls.guards.close)
        cls.forbidden = []

        def forbid(owner, name, **kwargs):
            cls.forbidden.append(cls.guards.enter_context(patch.object(
                owner, name, side_effect=AssertionError('Source-only checks prohibit execution or artifact writes'),
                **kwargs)))

        for name in ('Popen', 'run', 'call', 'check_call', 'check_output', 'getoutput', 'getstatusoutput'):
            forbid(subprocess, name)
        for name in ('system', 'startfile', 'spawnl', 'spawnle', 'spawnlp', 'spawnlpe',
                     'spawnv', 'spawnve', 'spawnvp', 'spawnvpe'):
            if hasattr(os, name):
                forbid(os, name)
        for name in ('CDLL', 'WinDLL', 'OleDLL', 'PyDLL'):
            forbid(ctypes, name, create=True)
        for name in ('copy', 'copy2', 'copyfile', 'copytree'):
            forbid(shutil, name)
        for name in ('mkdtemp', 'TemporaryDirectory'):
            forbid(tempfile, name)
        for name in ('write_bytes', 'write_text', 'mkdir'):
            forbid(Path, name)
        for name in ('mkdir', 'makedirs'):
            forbid(os, name)
        forbid(freezer, 'main')
        forbid(freezer, 'freeze_source')
        cls.addClassCleanup(cls.verify_guards)
        cls.styles = freezer.GAME / freezer.STYLE_SOURCE
        cls.xml = freezer.GAME / freezer.LOAD_MENU_XML
        cls.lua = freezer.GAME / freezer.LOAD_MENU_LUA
        cls.paths = [cls.styles, cls.xml, cls.lua,
                     freezer.GAME / freezer.GAME_MENU_XML, freezer.GAME / freezer.GAME_MENU_LUA,
                     freezer.GAME / freezer.MAP_UTILITIES_LUA,
                     PROJECT / 'tools/prepare_ui_popup_assets.py', PROJECT / 'tools/ui_pixel_scene.py']
        cls.before = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in cls.paths}
        cls.addClassCleanup(cls.verify_sources)
        cls.original = ET.parse(cls.xml).getroot()
        cls.pack = Fpk(freezer.GAME / 'Resource/DX9/Expansion2UITextures.fpk')
        cls.assets = SimpleNamespace(packs=[cls.pack])
        cls.defaults = freezer.observed_load_menu_check_defaults(cls.styles, cls.xml, cls.assets)
        cls.atlas_before = {name: cls.pack.read(name)[1]
                            for name in ('checkbox.dds', 'checkbox-index.dds')}

    @classmethod
    def verify_guards(cls):
        for guard in cls.forbidden:
            guard.assert_not_called()

    @classmethod
    def verify_sources(cls):
        after = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in cls.paths}
        if after != cls.before:
            raise AssertionError('An attested UI source changed during source-only checks')
        if hasattr(cls, 'atlas_before'):
            after_atlas = {name: cls.pack.read(name)[1] for name in cls.atlas_before}
            if after_atlas != cls.atlas_before:
                raise AssertionError('The selected original atlas changed during source-only checks')

    def tree(self):
        tree = freezer.load_menu_control_tree(deepcopy(self.original))
        tree.update(contextName='LoadMenu', popupKind='LoadMenu')
        return tree

    def test_original_implicit_controls_and_observed_atlas_remain_explicit_candidates(self):
        self.assertEqual(set(self.defaults), {'AutoCheck', 'CloudCheck'})
        for control_id, row in self.defaults.items():
            original = self.original.find(".//*[@ID='" + control_id + "']")
            self.assertEqual(row['controlSourceAttributes'], dict(original.attrib))
            self.assertFalse({'Size', 'Style', 'ButtonTexture'} & row['controlSourceAttributes'].keys())
            self.assertEqual((row['width'], row['height'], row['frameCount']), (32, 32, 4))
            self.assertEqual(row['sourceStyleAttributes'], {
                'Texture': 'Assets/UI/Art/Controls/Checkbox.dds', 'Size': '32,32',
            })
            self.assertEqual(row['atlas'], {
                'width': 32, 'height': 128, 'cellWidth': 32, 'cellHeight': 32, 'frameCount': 4,
                'sha256': '7dc39bf9ead582d052dda940eca1694d90866aa83065ec776598c9dcc583a240',
            })
            self.assertEqual(row['atlasSource'], self.atlas_before['checkbox.dds'])
            self.assertEqual(row['atlasIndexSource'], self.atlas_before['checkbox-index.dds'])
            for field in ('defaultBindingVerified', 'retailGeometryVerified', 'retailWidgetStateMappingVerified'):
                self.assertIs(row[field], False)
        changed = deepcopy(self.defaults)
        changed['AutoCheck']['atlas']['width'] = 1
        self.assertEqual(changed['CloudCheck']['atlas']['width'], 32)

    def test_attachment_reuses_exact_installed_source_without_rewriting_original_nodes(self):
        tree = self.tree()
        original_tree = deepcopy(tree)
        snapshots = PROJECT / 'Source/Assets/UI'
        with patch.object(freezer, 'freeze_source', return_value=(self.styles, self.styles)) as reused:
            defaults = freezer.load_menu_check_defaults(snapshots, self.assets)
        reused.assert_called_once_with(freezer.STYLE_SOURCE, snapshots)
        freezer.attach_load_menu_control_defaults(tree, defaults)
        self.assertEqual(tree.pop('controlDefaultSizes'), self.defaults)
        self.assertEqual(tree, original_tree)

    def test_attachment_rejects_foreign_ids_geometry_source_and_verified_flags(self):
        for mutation in ('context', 'id', 'size', 'style', 'source',
                         'defaultBindingVerified', 'retailGeometryVerified', 'retailWidgetStateMappingVerified'):
            tree, defaults = self.tree(), deepcopy(self.defaults)
            if mutation == 'context':
                tree['contextName'] = 'SaveMenu'
            elif mutation == 'id':
                defaults['Foreign'] = defaults.pop('AutoCheck')
            elif mutation == 'size':
                defaults['AutoCheck']['width'] = 16
            elif mutation == 'style':
                defaults['AutoCheck']['style'] = 'SquareCheck'
            elif mutation == 'source':
                defaults['AutoCheck']['controlSourceAttributes']['Size'] = '32,32'
            else:
                defaults['AutoCheck'][mutation] = True
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                freezer.attach_load_menu_control_defaults(tree, defaults)

    def test_compositor_accepts_only_the_exact_observed_candidate(self):
        compiler = SimpleNamespace(context='load-menu', load_menu_checkbox_defaults=self.defaults)
        row = self.defaults['AutoCheck']
        node = {'kind': 'CheckBox', 'id': 'AutoCheck', 'defaultSize': deepcopy(row),
                'sourceAttributes': deepcopy(row['controlSourceAttributes']), 'texture': row['texture']}
        attrs = {**row['controlSourceAttributes'], 'Texture': row['texture'], 'ButtonTexture': row['texture']}
        self.assertEqual(Compiler.load_menu_checkbox_default(compiler, node, attrs, 32, 32), row)
        for mutation in ('atlas_sha', 'source_sha', 'index_sha', 'width', 'missing', 'source_attr', 'runtime_texture'):
            altered, actual_attrs = deepcopy(node), deepcopy(attrs)
            width = 32
            if mutation == 'atlas_sha':
                altered['defaultSize']['atlas']['sha256'] = '0' * 64
            elif mutation == 'source_sha':
                altered['defaultSize']['source']['sha256'] = '0' * 64
            elif mutation == 'index_sha':
                altered['defaultSize']['atlasIndexSource']['sha256'] = '0' * 64
            elif mutation == 'width':
                width = 0
            elif mutation == 'missing':
                altered.pop('defaultSize')
            elif mutation == 'source_attr':
                altered['sourceAttributes']['Size'] = '32,32'
            else:
                actual_attrs['ButtonTexture'] = 'Other.dds'
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                Compiler.load_menu_checkbox_default(compiler, altered, actual_attrs, width, 32)

    def source_snapshot(self):
        """A schema-only synthetic full tree; no positions or runtime are certified."""
        sequence = 0
        def node(element, *, kind=None, origin=None, role=None, owner=None):
            nonlocal sequence
            sequence += 1
            result = {'key': sequence, 'kind': kind or element.tag, 'id': element.get('ID', ''),
                      'sourceAttributes': dict(element.attrib), 'attributes': dict(element.attrib),
                      'hidden': element.get('Hidden', '').lower() in ('1', 'true'), 'disabled': False,
                      'x': 0, 'y': 0, 'width': 32, 'height': 32, 'children': []}
            if element.tag == 'Context' or element.get('ID') in ('BGBlock', 'DeleteConfirm', 'ReferencedPackagesWindow'):
                result['width'], result['height'] = 1920, 1080
            if origin is not None:
                result['styleChildSource'] = {'style': 'GenericPullDown', 'ownerKey': owner,
                    'ownerPullDownKey': owner, 'path': 'Assets/UI/Styles.xml',
                    'sha256': self.before[str(self.styles)], 'indices': list(origin)}
            if role:
                result.update(originalDataKind=role, ownerPullDownKey=owner)
            for index, child in enumerate(element):
                if child.tag != 'Instance':
                    result['children'].append(node(child, origin=([*origin, index + 1] if origin is not None else None), owner=owner))
            return result
        root = node(self.original)
        def walk(item):
            yield item
            for child in item['children']:
                yield from walk(child)
        by_id = {item['id']: item for item in walk(root) if item['id']}
        pull = by_id['SortByPullDown']
        owner = pull['key']
        style = ET.parse(self.styles).getroot().find('GenericPullDown')
        button = node(style[0][0], origin=[1, 1], role='ButtonData', owner=owner)
        popup = node(style[1], kind='Grid', origin=[2], role='GridData', owner=owner)
        panel = node(style[2], kind='ScrollPanel', origin=[3], role='ScrollPanelData', owner=owner)
        stack = node(style[3], kind='Stack', origin=[4], role='StackData', owner=owner)
        panel['children'].append(stack);popup['children'].append(panel)
        popup['hidden'] = True;pull['children'] = [button, popup]
        style_ref = {'path': 'Assets/UI/Styles.xml', 'sha256': self.before[str(self.styles)]}
        widget = {'key': owner, 'opened': False, 'style': 'GenericPullDown', 'buttonKey': button['key'],
                  'popupKey': popup['key'], 'scrollPanelKey': panel['key'], 'stackKey': stack['key'],
                  'entryKeys': [], 'originalStyleSource': style_ref,
                  'geometryPolicy': 'ZEROSIS_ORIGINAL_GENERIC_PULL_DOWN_COMPOSITE_CANDIDATE_V1',
                  'retailGeometryVerified': False, 'retailWidgetBehaviorVerified': False}
        menu = deepcopy(self.tree()['loadMenu'])
        menu.update(controlOnly=False, sourceApisBound=True, nativeVmConnected=False, retailBackendVerified=False,
                    frontendStatePolicy='OWNED_LOCAL_INGAME_VIEW_OPAQUE_IDENTITY_NO_RETAIL_NUMERIC_ENUM_CLAIM',
                    unsupportedActions=['cloud', 'delete', 'automatic-save-filter'])
        bg = by_id['BGBlock']
        target = {'key': bg['key'], 'id': bg['id'], 'event': 'ConsumeMouse', 'consumeMouse': True,
                  'visible': True, 'disabled': False,
                  'bounds': dict(x=0, y=0, width=1920, height=1080),
                  'clippedBounds': dict(x=0, y=0, width=1920, height=1080)}
        central = next(item for item in walk(root) if item['kind'] == 'Grid' and
                       item['sourceAttributes'].get('ConsumeMouse') == '1')
        central['attributes']['ConsumeMouse'] = '1'
        grid_target = {**target, 'key': central['key'], 'id': central['id'],
                       'bounds': dict(x=0, y=0, width=32, height=32),
                       'clippedBounds': dict(x=0, y=0, width=32, height=32)}
        bg['attributes']['ConsumeMouse'] = '1'
        return {'contextName': 'LoadMenu', 'popupKind': 'LoadMenu', 'active': True, 'contextHidden': False,
                'timerSemaphore': 0, 'lifecycle': ['queued'], 'loadMenu': menu, 'tree': root,
                'pullDowns': [widget], 'inputTargets': [target, grid_target]}, by_id

    def test_full_source_candidate_and_its_unverified_runtime_boundary(self):
        snapshot, _ = self.source_snapshot()
        result = load_menu_controls_contract(snapshot)
        self.assertTrue(result['full_original_tree_matched'])
        self.assertTrue(result['source_api_bound_candidate'])
        self.assertIs(result['native_load_handoff_verified'], False)
        self.assertIs(result['retail_geometry_verified'], False)
        for field in ('nativeVmConnected', 'runtimeIntegrationVerified', 'retailBackendVerified', 'retailLayoutVerified'):
            altered = deepcopy(snapshot);altered['loadMenu'][field] = True
            with self.subTest(field=field), self.assertRaises(ValueError):
                load_menu_controls_contract(altered)

    def test_full_source_rejects_removed_controls_relabelled_sources_and_forged_style_origin(self):
        for mutation in ('drop', 'reorder', 'source_attrs', 'style_origin', 'api_bound', 'consumer_id'):
            snapshot, by_id = self.source_snapshot()
            if mutation == 'drop':
                parent = next(item for item in self.walk(snapshot['tree']) if by_id['AutoCheck'] in item['children'])
                parent['children'].remove(by_id['AutoCheck'])
            elif mutation == 'reorder':
                snapshot['tree']['children'] = list(reversed(snapshot['tree']['children']))
            elif mutation == 'source_attrs':
                by_id['CloudCheck']['sourceAttributes']['Offset'] = '0,0'
            elif mutation == 'style_origin':
                by_id['SortByPullDown']['children'][0]['styleChildSource']['ownerPullDownKey'] = 99999
            elif mutation == 'consumer_id':
                by_id['BGBlock']['id'] = 'ForeignConsumer'
            else:
                snapshot['loadMenu']['sourceApisBound'] = False
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                load_menu_controls_contract(snapshot)

    def test_full_source_rejects_boolean_timer_enabled_mismatch_and_forged_supported_actions(self):
        for mutation in ('boolean_timer', 'disabled_node', 'hidden_target', 'supported_actions', 'numeric_state'):
            snapshot, by_id = self.source_snapshot()
            if mutation == 'boolean_timer':
                snapshot['timerSemaphore'] = False
            elif mutation == 'disabled_node':
                by_id['BGBlock']['disabled'] = True
            elif mutation == 'hidden_target':
                snapshot['inputTargets'][0]['visible'] = False
            elif mutation == 'supported_actions':
                snapshot['loadMenu']['unsupportedActions'] = []
            else:
                snapshot['loadMenu']['frontendStatePolicy'] = 'RETAIL_STATE_ENUM_EQUALS_ZERO'
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                load_menu_controls_contract(snapshot)

    @staticmethod
    def walk(node):
        yield node
        for child in node['children']:
            yield from LoadMenuCheckboxAssets.walk(child)

    def test_full_source_modal_blocks_background_callbacks_and_requires_its_consumer(self):
        snapshot, by_id = self.source_snapshot()
        by_id['ReferencedPackagesWindow']['hidden'] = False
        with self.assertRaises(ValueError):
            load_menu_controls_contract(snapshot)
        target = snapshot['inputTargets'][0]
        target.update(key=by_id['ReferencedPackagesWindow']['key'], id='ReferencedPackagesWindow')
        snapshot['inputTargets'] = [target]
        result = load_menu_controls_contract(snapshot)
        self.assertEqual(result['modal_key'], target['key'])
        self.assertIn(by_id['CloseReferencedPackagesButton']['key'], result['modal_input_keys'])
        snapshot['inputTargets'].append({'key': by_id['StartButton']['key'], 'event': 'LeftClick',
                                        'visible': True, 'disabled': False})
        with self.assertRaises(ValueError):
            load_menu_controls_contract(snapshot)

    def game_menu_schema_snapshot(self):
        """Synthetic closed original tree; not an actual/native snapshot."""
        original = ET.parse(freezer.GAME / freezer.GAME_MENU_XML).getroot()
        styles = {element.tag: dict(element.attrib) for element in ET.parse(self.styles).getroot()}
        sequence = 0

        def node(element, parent=(0, 0, 1920, 1080)):
            nonlocal sequence
            sequence += 1
            attrs = {**styles.get(element.get('Style'), {}), **element.attrib}
            size = attrs.get('Size', '32,32')
            bounds = parent if element.tag == 'Context' or element.get('Style') == 'BGBlock' else (
                anchor(attrs, parent, *pair(size)) if 'Full' not in size else parent)
            result = {'key': sequence, 'kind': element.tag, 'id': element.get('ID', ''),
                      'sourceAttributes': dict(element.attrib), 'attributes': attrs,
                      'hidden': element.get('Hidden', '').lower() in ('1', 'true'), 'disabled': False,
                      'text': element.get('String', ''), 'buttonState': 'normal', 'hovered': False,
                      'x': bounds[0], 'y': bounds[1], 'width': bounds[2], 'height': bounds[3], 'children': []}
            if element.tag == 'AlphaAnim' and element.get('Cycle') == 'Once':
                result['animation'] = {'clock': 0, 'alpha': .2, 'elapsed': 0, 'normalizedPhase': 0,
                    'activationStartTime': 0, 'running': False, 'completed': False,
                    'timingPolicy': 'CIV5_GAME_MENU_ONCE_HOVER_CANDIDATE_V1', 'retailTimingVerified': False,
                    'childOpacityPolicy': 'MULTIPLY_CAPTURED_ALPHA_THROUGH_DESCENDANTS'}
            result['children'] = [node(child, bounds) for child in element if child.tag != 'Instance']
            return result

        menu = freezer.game_menu_control_tree(original)['gameMenu']
        menu.update(owner=0, turn=0, modal=True, timerSemaphore=0, confirmationVisible=False)
        return {'contextName': 'GameMenu', 'popupKind': 'GameMenu', 'active': False,
                'timerSemaphore': 0, 'lifecycle': ['queued', 'closed'], 'gameMenu': menu,
                'tree': node(original), 'presentationClock': 0, 'inputTargets': [], 'scrollTargets': []}, original

    def test_game_menu_historical_and_new_child_source_inventory_schema(self):
        for binding in (None, False, True):
            snapshot, original = self.game_menu_schema_snapshot()
            menu = snapshot['gameMenu']
            if binding is not True:
                menu.pop('loadMenuSourceApisBound');menu.pop('sourceConnectedChildren')
                if binding is False:
                    menu['loadMenuSourceApisBound'] = False
                menu['unconnectedLuaContexts'] = [freezer.control_tree(element)
                    for element in original if element.tag == 'LuaContext']
            with self.subTest(binding=binding):
                result = game_menu_contract(snapshot, closed=True)
                self.assertIs(result['load_menu_source_apis_bound'], binding is True)
                self.assertEqual(result['source_connected_children'], ['SaveMenu', 'LoadMenu'] if binding is True else [])
                self.assertEqual(len(result['unconnectedLuaContexts']), 3 if binding is True else 5)
                self.assertIs(result['child_contexts_runtime_verified'], False)
                self.assertIs(result['retail_pixels_verified'], False)

    def test_game_menu_child_source_inventory_rejects_mixed_or_forged_schemas(self):
        for mutation in ('old_inventory_with_new_flag', 'new_inventory_without_flag', 'unknown_child',
                         'reordered_source_children', 'nonboolean_flag'):
            snapshot, original = self.game_menu_schema_snapshot()
            menu = snapshot['gameMenu']
            if mutation == 'old_inventory_with_new_flag':
                menu['unconnectedLuaContexts'] = [freezer.control_tree(element)
                    for element in original if element.tag == 'LuaContext']
            elif mutation == 'new_inventory_without_flag':
                menu.pop('loadMenuSourceApisBound');menu.pop('sourceConnectedChildren')
            elif mutation == 'unknown_child':
                menu['sourceConnectedChildren'].append('OptionsMenu_InGame')
            elif mutation == 'reordered_source_children':
                menu['sourceConnectedChildren'].reverse()
            else:
                menu['loadMenuSourceApisBound'] = 1
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                game_menu_contract(snapshot, closed=True)


if __name__ == '__main__':
    unittest.main()
