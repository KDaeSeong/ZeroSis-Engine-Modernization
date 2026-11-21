"""Small original-source EconomicOverview composition/packet-contract tests.

No native process, SDK fixture, screenshot, build, or persistent test output is
created. These checks are component evidence, not retail pixels or gameplay.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
import xml.etree.ElementTree as ET

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / 'tools'))

from civ5_ui_assets import sha256
from ui_pixel_scene import (Compiler, ECONOMIC_KEY_SPAN, ECONOMIC_SPECS, SOLID,
                            compose_economic_overview_snapshot, economic_tree_inventory,
                            economic_walk, validate_economic_overview_prepared)
from interactive_ui_driver import validate_economic_overview_scene_proof
from render_ui_popup import retained_bounds

GAME = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Sid Meier's Civilization V")


def original_tree(element):
    return {'kind': element.tag, 'attributes': dict(element.attrib),
            'children': [original_tree(child) for child in element]}


def prepared_sources():
    trees, rows = {}, {}
    for slot, (name, kind, layout, _) in ECONOMIC_SPECS.items():
        folder = GAME / 'Assets/DLC/Expansion2/UI/InGame/Popups'
        xml = folder / (name + '.xml')
        lua = (GAME / 'Assets/UI/InGame/Popups' if slot == 'parent' else folder) / (name + '.lua')
        tree = original_tree(ET.parse(xml).getroot())
        tree.update(contextName=name, popupKind=kind)
        trees[layout] = tree
        rows[slot] = {'contextName': name, 'popupKind': kind, 'layoutAsset': layout, 'luaAsset': name,
                      'lua': {'path': str(lua), 'sha256': sha256(lua)},
                      'xml': {'path': str(xml), 'sha256': sha256(xml)},
                      **economic_tree_inventory(tree)}
        if slot != 'parent':
            rows[slot].update(controlId=slot, visibility='visible' if slot == 'EconomicGeneralInfo' else 'hidden')
    return {'xml_control_trees': trees, 'economic_overview': {
        'parent': rows['parent'], 'children': {name: rows[name] for name in ('EconomicGeneralInfo', 'HappinessInfo')},
        'xmlContexts': [
            {'id': 'EconomicGeneralInfo', 'fileName': 'Assets/UI/InGame/Popups/EconomicGeneralInfo', 'hidden': '0'},
            {'id': 'HappinessInfo', 'fileName': 'Assets/UI/InGame/Popups/HappinessInfo', 'hidden': '1'}],
        'treeNames': [value[2] for value in ECONOMIC_SPECS.values()], 'sourceBytesPreserved': True}}


def captured_tree(source, sequence=None):
    sequence = [0] if sequence is None else sequence
    sequence[0] += 1
    attrs = copy.deepcopy(source['attributes'])
    viewport = source['kind'] in ('Context', 'LuaContext')
    node = {'key': sequence[0], 'kind': source['kind'], 'id': attrs.get('ID', ''),
            'attributes': attrs, 'sourceAttributes': copy.deepcopy(attrs),
            'hidden': attrs.get('Hidden') in ('1', 'true', 'True'), 'disabled': False,
            'x': 0 if viewport else 40, 'y': 0 if viewport else 50,
            'width': 1920 if viewport else 100, 'height': 1080 if viewport else 20,
            'text': 'Original localized caption', 'buttonState': 'normal',
            'hovered': False, 'children': []}
    node['children'] = [captured_tree(child, sequence) for child in source['children'] if child['kind'] != 'Instance']
    return node


def target(node, event='LeftClick'):
    bounds = {field: node[field] for field in ('x', 'y', 'width', 'height')}
    row = {'key': node['key'], 'id': node['id'], 'event': event, 'visible': True, 'disabled': False,
           'bounds': bounds, 'clippedBounds': dict(bounds), 'void1': 3, 'void2': -1}
    if event == 'Scroll':
        row.update(scrollY=0, contentHeight=120, viewportHeight=node['height'], maximumScroll=100)
    return row


def fixture(prepared, selected='EconomicGeneralInfo', active=True):
    snapshots = {}
    for slot, (name, kind, layout, base) in ECONOMIC_SPECS.items():
        source = prepared['economic_overview']['parent'] if slot == 'parent' else prepared['economic_overview']['children'][slot]
        vm_active = active and (slot == 'parent' or slot == selected)
        snapshot = {'contextName': name, 'popupKind': kind, 'active': vm_active,
                    'timerSemaphore': int(active) if slot == 'parent' else 0,
                    'economicOverview': {
                        'role': {'parent': 'parent', 'EconomicGeneralInfo': 'general', 'HappinessInfo': 'happiness'}[slot],
                        'originalLua': copy.deepcopy(source['lua']), 'originalXml': copy.deepcopy(source['xml'])},
                    'tree': captured_tree(prepared['xml_control_trees'][layout]),
                    'inputTargets': [], 'scrollTargets': [], 'presentationClock': 0,
                    'animationPolicy': 'ZEROSIS_FRONTEND_XML_TIMELINE_V1', 'retailTimingVerified': False,
                    'fontMetrics': {'policy': 'CIV5_GLYPHGEN_GGXML_LAYOUT_V1',
                                    'wrapPolicy': 'GREEDY_ASCII_SPACE_WORD_WRAP_SPLIT_LONG_WORD_AT_CODEPOINT',
                                    'retailMetricSemanticsVerified': False, 'fonts': {}},
                    'lifecycle': ['queued', 'shown:30'] if vm_active else ['queued', 'closed']}
        snapshots[slot] = snapshot
        if slot == 'parent':
            for node in economic_walk(snapshot['tree']):
                if node['kind'] == 'LuaContext':
                    node['hidden'] = node['id'] != selected
                if node['id'] in ('GeneralInfoSelectHighlight', 'HappinessSelectHighlight'):
                    node['hidden'] = node['id'] != ('GeneralInfoSelectHighlight' if selected == 'EconomicGeneralInfo'
                                                   else 'HappinessSelectHighlight')
                if active and node['id'] in ('GeneralInfoButton', 'HappinessButton', 'CloseButton'):
                    snapshot['inputTargets'].append(target(node))
        elif vm_active:
            button = next(node for node in economic_walk(snapshot['tree']) if node['kind'] == 'Button')
            button['hidden'] = False
            snapshot['inputTargets'].append(target(button))
            panel = next(node for node in economic_walk(snapshot['tree']) if node['kind'] == 'ScrollPanel')
            panel['hidden'] = False
            snapshot['scrollTargets'].append(target(panel, 'Scroll'))
    parent = snapshots['parent']
    parent['embeddedContexts'] = [{'controlId': slot, 'keyBase': ECONOMIC_SPECS[slot][3], 'snapshot': snapshots[slot]}
                                  for slot in ('EconomicGeneralInfo', 'HappinessInfo')]
    return parent


def manifest_for(snapshot, prepared):
    normalized, proof = compose_economic_overview_snapshot(snapshot, prepared)
    geometry = []
    def collect(node):
        if node['hidden']:
            return
        geometry.append({'key': node['key'], 'id': node['id'], 'kind': node['kind'],
                         'style_decoration': False, 'bounds': [node[name] for name in ('x', 'y', 'width', 'height')]})
        if node['kind'] == 'ShowOnMouseOver' and not node['hovered']:
            return
        for child in node['children']:
            collect(child)
    if snapshot['active']:
        collect(normalized['tree'])
    def region(row):
        r = row['clippedBounds']
        return [row['key'], r['x'], r['y'], r['x'] + r['width'], r['y'] + r['height']]
    return {'economic_overview_scene': proof, 'geometry': geometry,
            'original_context_sources': [ref for rows in proof['source_contract'].values() for ref in rows.values()],
            'hit_regions': [region(row) for row in normalized['inputTargets'] if row['event'] == 'LeftClick'],
            'scroll_regions': [region(row) for row in normalized['scrollTargets']]}


class EconomicOverviewRendererTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = prepared_sources()

    def setUp(self):
        self.prepared = copy.deepcopy(self.original)
        self.snapshot = fixture(self.prepared)

    def rejected(self, mutate):
        snapshot = copy.deepcopy(self.snapshot)
        mutate(snapshot)
        with self.assertRaises((ValueError, RuntimeError)):
            compose_economic_overview_snapshot(snapshot, self.prepared)

    def test_original_six_files_and_complete_trees(self):
        validate_economic_overview_prepared(self.prepared, verify_files=True)

    def test_both_original_tabs_and_closed_state(self):
        for tab in ('EconomicGeneralInfo', 'HappinessInfo'):
            for active in (True, False):
                with self.subTest(tab=tab, active=active):
                    snapshot = fixture(self.prepared, tab, active)
                    untouched = copy.deepcopy(snapshot)
                    normalized, proof = compose_economic_overview_snapshot(snapshot, self.prepared)
                    self.assertEqual(snapshot, untouched)
                    self.assertEqual(proof['active_child'], tab if active else None)
                    manifest = manifest_for(snapshot, self.prepared)
                    validate_economic_overview_scene_proof(snapshot, manifest, self.prepared, closed=not active)
                    if active:
                        retained_bounds(normalized, manifest['geometry'], context='economic-overview')

    def test_every_child_key_and_callback_payload_preserved(self):
        original = self.snapshot['embeddedContexts'][0]['snapshot']
        root = original['tree']
        root['ownerKey'] = root['key']
        normalized, proof = compose_economic_overview_snapshot(self.snapshot, self.prepared)
        slot = next(node for node in economic_walk(normalized['tree']) if node.get('id') == 'EconomicGeneralInfo')
        self.assertEqual([node['key'] for node in economic_walk(slot['children'][0])],
                         [node['key'] + ECONOMIC_KEY_SPAN for node in economic_walk(root)])
        self.assertEqual(slot['children'][0]['ownerKey'], root['key'] + ECONOMIC_KEY_SPAN)
        rebased = proof['original_input_targets'][-1]
        self.assertEqual(rebased['key'], original['inputTargets'][0]['key'] + ECONOMIC_KEY_SPAN)
        self.assertEqual((rebased['void1'], rebased['void2']), (3, -1))
        self.assertEqual(proof['original_scroll_targets'][0]['key'],
                         original['scrollTargets'][0]['key'] + ECONOMIC_KEY_SPAN)

    def test_missing_extra_duplicate_and_wrong_slots_rejected(self):
        for mutate in (
            lambda s: s['embeddedContexts'].pop(),
            lambda s: s['embeddedContexts'].append(copy.deepcopy(s['embeddedContexts'][0])),
            lambda s: s['embeddedContexts'][1].update(controlId='EconomicGeneralInfo'),
            lambda s: s['embeddedContexts'][0].update(keyBase=ECONOMIC_KEY_SPAN * 2),
            lambda s: s['embeddedContexts'][0]['snapshot'].update(contextName='HappinessInfo'),
            lambda s: s['embeddedContexts'][0]['snapshot']['economicOverview'].update(role='happiness'),
            lambda s: s['embeddedContexts'][0]['snapshot'].update(embeddedContexts=[{}]),
        ):
            self.rejected(mutate)

    def test_visibility_timer_and_highlight_mutations_rejected(self):
        for mutate in (
            lambda s: s.update(timerSemaphore=0),
            lambda s: s['embeddedContexts'][0]['snapshot'].update(timerSemaphore=1),
            lambda s: s['embeddedContexts'][1]['snapshot'].update(active=True),
            lambda s: s['embeddedContexts'][1]['snapshot']['inputTargets'].append(target(s['embeddedContexts'][1]['snapshot']['tree'])),
            lambda s: s['embeddedContexts'][1]['snapshot']['scrollTargets'].append(target(s['embeddedContexts'][1]['snapshot']['tree'], 'Scroll')),
            lambda s: next(n for n in economic_walk(s['tree']) if n.get('id') == 'GeneralInfoSelectHighlight').update(hidden=True),
        ):
            self.rejected(mutate)

    def test_keys_and_unknown_references_rejected(self):
        for value in (0, True, ECONOMIC_KEY_SPAN, -1):
            self.rejected(lambda s, value=value: s['embeddedContexts'][0]['snapshot']['tree'].update(key=value))
        self.rejected(lambda s: s['embeddedContexts'][0]['snapshot']['tree']['children'][0].update(key=1))
        self.rejected(lambda s: s['tree']['children'][0].update(key=1))
        self.rejected(lambda s: s['embeddedContexts'][0]['snapshot']['inputTargets'][0].update(key=999999))
        self.rejected(lambda s: s['embeddedContexts'][0]['snapshot']['tree'].update(ownerKey=999999))

    def test_missing_original_controls_and_forged_sources_rejected(self):
        self.rejected(lambda s: s['embeddedContexts'][0]['snapshot']['tree']['children'].pop(0))
        self.rejected(lambda s: s['tree']['children'].append(copy.deepcopy(s['tree']['children'][-1])))
        self.rejected(lambda s: s['embeddedContexts'][1]['snapshot']['economicOverview']['originalLua'].update(sha256='f' * 64))
        self.prepared['economic_overview']['children']['HappinessInfo']['control_ids'].pop()
        with self.assertRaises(ValueError):
            compose_economic_overview_snapshot(self.snapshot, self.prepared)

    def test_frozen_xml_tree_tampering_rejected(self):
        tree = self.prepared['xml_control_trees']['EconomicGeneralLayout']
        tree['children'].pop()
        self.prepared['economic_overview']['children']['EconomicGeneralInfo'].update(economic_tree_inventory(tree))
        with self.assertRaises(ValueError):
            validate_economic_overview_prepared(self.prepared, verify_files=True)

    def test_complete_original_dynamic_instance_and_missing_control(self):
        source = self.prepared['xml_control_trees']['EconomicGeneralLayout']
        template = next(node for node in economic_walk(source) if node['kind'] == 'Instance')
        vm = self.snapshot['embeddedContexts'][0]['snapshot']
        container = next(node for node in economic_walk(vm['tree']) if node['kind'] == 'Stack' and not node['children'])
        row = captured_tree(template['children'][0], [10000])
        container['children'].append(row)
        compose_economic_overview_snapshot(self.snapshot, self.prepared)
        row['children'].pop()
        with self.assertRaises(ValueError):
            compose_economic_overview_snapshot(self.snapshot, self.prepared)

    def test_conflicting_font_and_clock_rejected(self):
        font_snapshot = copy.deepcopy(self.snapshot)
        font_snapshot['fontMetrics']['fonts']['TwCenMT20'] = {'sha256': 'a'}
        font_snapshot['embeddedContexts'][0]['snapshot']['fontMetrics']['fonts']['TwCenMT20'] = {'sha256': 'b'}
        with self.assertRaises(ValueError):
            compose_economic_overview_snapshot(font_snapshot, self.prepared)
        clock_snapshot = copy.deepcopy(self.snapshot)
        clock_snapshot['embeddedContexts'][0]['snapshot']['presentationClock'] = 1
        with self.assertRaises(ValueError):
            compose_economic_overview_snapshot(clock_snapshot, self.prepared)

    def test_unsealed_child_style_source_rejected(self):
        source = {'path': 'Assets/UI/Styles.xml', 'sha256': 'b' * 64}
        self.prepared['xml_control_trees']['EconomicGeneralLayout']['styleDefaultsSource'] = source
        self.snapshot['embeddedContexts'][0]['snapshot']['styleDefaultsSource'] = copy.deepcopy(source)
        compose_economic_overview_snapshot(self.snapshot, self.prepared)
        self.rejected(lambda s: s['embeddedContexts'][0]['snapshot']['styleDefaultsSource'].update(sha256='a' * 64))

    def test_driver_rejects_wrong_hit_key_source_or_missing_child(self):
        original = manifest_for(self.snapshot, self.prepared)
        for change in (
            lambda m: m['hit_regions'][-1].__setitem__(0, 3),
            lambda m: m['hit_regions'][-1].__setitem__(1, 999),
            lambda m: m['original_context_sources'].pop(),
            lambda m: m['economic_overview_scene'].update(full_gameplay_coverage=True),
            lambda m: m['scroll_regions'][0].__setitem__(0, 3),
            lambda m: m['scroll_regions'][0].__setitem__(2, 999),
            lambda m: m['geometry'].__setitem__(slice(None), [r for r in m['geometry'] if r['key'] < ECONOMIC_KEY_SPAN]),
        ):
            manifest = copy.deepcopy(original)
            change(manifest)
            with self.assertRaises((RuntimeError, ValueError)):
                validate_economic_overview_scene_proof(self.snapshot, manifest, self.prepared, closed=False)

    def test_original_bar_paints_fraction_and_dynamic_rgba(self):
        source = next(node for node in economic_walk(self.prepared['xml_control_trees']['EconomicGeneralLayout'])
                      if node['kind'] == 'Bar' and node['attributes']['ID'] == 'GrowthBar')
        node = captured_tree(source)
        node.update(key=ECONOMIC_KEY_SPAN + 99, x=20, y=30, width=4, height=30, percent=0.5,
                    fgColor={'x': 0.2, 'y': 0.6, 'z': 0.1, 'w': 0.5})
        compiler = Compiler.__new__(Compiler)
        compiler.context, compiler.width, compiler.height = 'economic-overview', 1920, 1080
        compiler.keys, compiler.styles, compiler.geometry = set(), {}, []
        compiler.economic_slot_keys, compiler.economic_context_keys = set(), set()
        compiler.economic_bar_sources = {(ECONOMIC_KEY_SPAN, 'GrowthBar'): source['attributes']}
        paints = []
        compiler.paint = lambda *args: paints.append(args)
        compiler.node(node, (0, 0, 1920, 1080), {}, (0, 0, 1920, 1080))
        self.assertEqual(paints[0][0:2], (node['key'], SOLID))
        self.assertEqual(paints[0][3], (20, 45, 24, 60))
        self.assertEqual(paints[0][5], (0.2, 0.6, 0.1, 0.5))
        for invalid in (float('nan'), -0.01, 1.01):
            compiler.keys.clear()
            node['percent'] = invalid
            with self.assertRaises(ValueError):
                compiler.node(node, (0, 0, 1920, 1080), {}, (0, 0, 1920, 1080))

    def test_original_economic_general_divider_uses_bounded_atlas_crop(self):
        source = next(node for node in economic_walk(self.prepared['xml_control_trees']['EconomicGeneralLayout'])
                      if node['kind'] == 'Image' and node['attributes'].get('Texture') == 'bar900x2.dds')
        self.assertEqual(source['attributes']['Size'], '680.1')
        self.assertEqual(source['attributes']['TextureOffset'], '110.0')
        node = captured_tree(source)
        node.update(key=ECONOMIC_KEY_SPAN + 166, x=728, y=383.5, width=680, height=1,
                    texture='bar900x2.dds', textureX=110, textureY=0)

        def compile_node(texture_size=(1024, 2), context='economic-overview'):
            compiler = Compiler.__new__(Compiler)
            compiler.context, compiler.width, compiler.height = context, 1920, 1080
            compiler.keys, compiler.styles, compiler.geometry = set(), {}, []
            compiler.economic_slot_keys, compiler.economic_context_keys = set(), set()
            compiler.assets = SimpleNamespace(outputs={
                'bar900x2.dds': {'conversion': {'source_scalable': True}}})
            compiler.texture = lambda _name: (b'', *texture_size)
            paints = []
            compiler.paint = lambda *args: paints.append(args)
            compiler.node(node, (0, 0, 1920, 1080), {}, (0, 0, 1920, 1080))
            return compiler, paints

        compiler, paints = compile_node()
        self.assertEqual(len(paints), 1)
        self.assertEqual(paints[0][0], node['key'])
        self.assertEqual(paints[0][2], (110, 0, 790, 1))
        self.assertEqual(paints[0][3], (728, 383.5, 1408, 384.5))
        self.assertEqual(compiler.geometry[0]['original_texture_source_extent'], [680, 1])
        self.assertEqual(compiler.geometry[0]['original_texture_source_policy'],
                         'ECONOMIC_GENERAL_ORIGINAL_DIVIDER_ATLAS_SUBREGION_CANDIDATE')
        for mutate in (
                lambda n: n.update(key=1),
                lambda n: n.update(textureX=109),
                lambda n: n.update(id='ForgedDivider'),
                lambda n: n['sourceAttributes'].update(Size='681.1'),
                lambda n: n['sourceAttributes'].update(Texture='other.dds'),
                lambda n: n['attributes'].update(Offset='1,0'),
                lambda n: n.update(width=681),
        ):
            invalid = copy.deepcopy(node)
            mutate(invalid)
            compiler = Compiler.__new__(Compiler)
            compiler.context, compiler.width, compiler.height = 'economic-overview', 1920, 1080
            compiler.keys, compiler.styles, compiler.geometry = set(), {}, []
            compiler.economic_slot_keys, compiler.economic_context_keys = set(), set()
            compiler.assets = SimpleNamespace(outputs={
                'bar900x2.dds': {'conversion': {'source_scalable': True}}})
            compiler.texture = lambda _name: (b'', 1024, 2)
            compiler.paint = lambda *args: None
            with self.assertRaises(ValueError):
                compiler.node(invalid, (0, 0, 1920, 1080), {}, (0, 0, 1920, 1080))
        with self.assertRaises(ValueError):
            compile_node(texture_size=(789, 2))
        with self.assertRaises(ValueError):
            compile_node(context='social-policy')

    def test_arbitrary_visible_lua_context_still_rejected(self):
        compiler = Compiler.__new__(Compiler)
        compiler.context, compiler.keys, compiler.economic_slot_keys = 'economic-overview', set(), set()
        node = next(n for n in economic_walk(self.snapshot['tree']) if n['kind'] == 'LuaContext')
        with self.assertRaises(ValueError):
            compiler.node(node, (0, 0, 1920, 1080), {}, (0, 0, 1920, 1080))


if __name__ == '__main__':
    unittest.main(verbosity=2)
