"""Regression tests for the retained TradeRoute civilization icon layers."""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / 'tools'))

import render_ui_popup


LAYER_SUFFIXES = ('', 'BG', 'Shadow', 'Highlight')
ENDPOINTS = ('FromCivIcon', 'ToCivIcon')


class FakeCompiler:
    def __init__(self, geometry, sprite_keys, retained_rows=2):
        self.geometry = geometry
        self.sprites = [(None, key) for key in sprite_keys]
        self.trade_route_state = {'retained_row_count': retained_rows}

    @staticmethod
    def color(_raw):
        return (1.0, 1.0, 1.0, 1.0)


def captured_scene(*, hidden_ancestor=False, empty_clip_keys=(), zero_alpha_keys=()):
    empty_clip_keys = set(empty_clip_keys)
    zero_alpha_keys = set(zero_alpha_keys)
    geometry = []
    rows = []
    key = 1
    for _ in range(2):
        layers = []
        for endpoint in ENDPOINTS:
            for suffix in LAYER_SUFFIXES:
                control_key = key
                key += 1
                layer_id = endpoint + suffix
                layers.append({
                    'kind': 'Image',
                    'id': layer_id,
                    'key': control_key,
                    'hidden': suffix != 'BG',
                    'attributes': {},
                    'color': {'w': 0.0 if control_key in zero_alpha_keys else 1.0},
                    'children': [],
                })
                clip = (4.0, 5.0, 4.0, 5.0) if control_key in empty_clip_keys else (0.0, 0.0, 24.0, 24.0)
                geometry.append({
                    'key': control_key,
                    'style_decoration': False,
                    'bounds': (0.0, 0.0, 24.0, 24.0),
                    'clip': clip,
                })
        rows.append({'id': 'TRInstance', 'kind': 'Box', 'hidden': False,
                     'children': [{'id': 'IconBox', 'kind': 'Box', 'hidden': False,
                                   'children': layers}]})
    return {'tree': {'id': 'Root', 'kind': 'Context', 'hidden': hidden_ancestor,
                     'children': rows}}, geometry


def sprite_keys_for(tree, include_hidden=False):
    keys = []

    def visit(node, ancestors_visible=True):
        visible = ancestors_visible and node.get('hidden') is False
        if node.get('kind') == 'Image' and (visible or include_hidden):
            keys.append(node['key'])
        for child in node.get('children', []):
            visit(child, visible)

    visit(tree['tree'])
    return keys


class TradeRouteIconLayerTests(unittest.TestCase):
    def proof(self, tree, geometry, sprite_keys):
        return render_ui_popup.trade_route_icon_proof(
            tree, FakeCompiler(geometry, sprite_keys))

    def test_default_color_icons_draw_visible_background_layers(self):
        tree, geometry = captured_scene()
        visible = sprite_keys_for(tree)
        proof = self.proof(tree, geometry, visible)
        self.assertEqual(proof['row_civilization_icon_visible_layer_keys'], visible)
        self.assertEqual(proof['row_civilization_icon_sprite_keys'], visible)
        self.assertEqual(len(proof['row_civilization_icon_keys']), 4)

    def test_composite_icon_draws_all_active_layers(self):
        tree, geometry = captured_scene()
        layers = [node for row in tree['tree']['children']
                  for box in row['children'] for node in box['children']]
        for layer in layers:
            layer['hidden'] = False
        visible = sprite_keys_for(tree)
        proof = self.proof(tree, geometry, visible)
        self.assertEqual(len(proof['row_civilization_icon_visible_layer_keys']), 16)
        self.assertEqual(proof['row_civilization_icon_sprite_keys'], visible)

    def test_missing_visible_sprite_is_rejected(self):
        tree, geometry = captured_scene()
        visible = sprite_keys_for(tree)
        with self.assertRaisesRegex(ValueError, 'visible civilization icon layers'):
            self.proof(tree, geometry, visible[:-1])

    def test_hidden_layer_emitting_sprite_is_rejected(self):
        tree, geometry = captured_scene()
        visible = sprite_keys_for(tree)
        hidden_key = next(node['key'] for node in tree['tree']['children'][0]['children'][0]['children']
                          if node['id'] == 'FromCivIcon')
        with self.assertRaisesRegex(ValueError, 'visible civilization icon layers'):
            self.proof(tree, geometry, visible + [hidden_key])

    def test_missing_geometry_for_visible_layer_is_rejected(self):
        tree, geometry = captured_scene()
        visible = sprite_keys_for(tree)
        missing_key = visible[0]
        with self.assertRaisesRegex(ValueError, 'lost its geometry'):
            self.proof(tree, [row for row in geometry if row['key'] != missing_key], visible)

    def test_hidden_ancestor_suppresses_all_sprite_requirements(self):
        tree, geometry = captured_scene(hidden_ancestor=True)
        proof = self.proof(tree, geometry, [])
        self.assertEqual(proof['row_civilization_icon_visible_layer_keys'], [])
        self.assertEqual(proof['row_civilization_icon_sprite_keys'], [])

    def test_empty_clip_suppresses_sprite_requirement(self):
        tree, geometry = captured_scene()
        visible = sprite_keys_for(tree)
        clipped_key = visible[0]
        geometry = [dict(row, clip=(0.0, 0.0, 0.0, 0.0))
                    if row['key'] == clipped_key else row for row in geometry]
        proof = self.proof(tree, geometry, visible[1:])
        self.assertNotIn(clipped_key, proof['row_civilization_icon_visible_layer_keys'])

    def test_zero_tint_alpha_suppresses_sprite_requirement(self):
        tree, geometry = captured_scene()
        visible = sprite_keys_for(tree)
        faded_key = visible[0]
        def set_zero_alpha(node):
            if node.get('key') == faded_key:
                node['color']['w'] = 0.0
            for child in node.get('children', []):
                set_zero_alpha(child)
        set_zero_alpha(tree['tree'])
        proof = self.proof(tree, geometry, visible[1:])
        self.assertNotIn(faded_key, proof['row_civilization_icon_visible_layer_keys'])

    def test_missing_layer_is_rejected(self):
        tree, geometry = captured_scene()
        tree['tree']['children'][0]['children'][0]['children'].pop()
        with self.assertRaisesRegex(ValueError, 'retain both original four-layer'):
            self.proof(tree, geometry, sprite_keys_for(tree))

    def test_duplicate_layer_key_is_rejected(self):
        tree, geometry = captured_scene()
        layers = tree['tree']['children'][0]['children'][0]['children']
        layers[1]['key'] = layers[0]['key']
        with self.assertRaisesRegex(ValueError, 'missing or duplicate key'):
            self.proof(tree, geometry, sprite_keys_for(tree))


if __name__ == '__main__':
    unittest.main()
