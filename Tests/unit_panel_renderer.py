"""Focused original UnitPanel recommended-divider crop checks; no native game."""
from __future__ import annotations

import copy
import hashlib
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
import xml.etree.ElementTree as ET

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / 'tools'))
from ui_pixel_scene import Compiler

GAME_UI = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Sid Meier's Civilization V") / 'Assets/DLC/Expansion2/UI/InGame/WorldView'
POLICY = 'UNIT_PANEL_ORIGINAL_RECOMMENDED_DIVIDER_ATLAS_SUBREGION_CANDIDATE'


def compiler_for(context='unit-panel', texture_size=(512, 2)):
    compiler = Compiler.__new__(Compiler)
    compiler.context, compiler.width, compiler.height = context, 1920, 1080
    compiler.keys, compiler.styles, compiler.geometry = set(), {}, []
    compiler.economic_slot_keys, compiler.economic_context_keys = set(), set()
    compiler.assets = SimpleNamespace(outputs={
        'bar300x2.dds': {'conversion': {'source_scalable': True}}})
    compiler.texture = lambda _name: (b'', *texture_size)
    paints = []
    compiler.paint = lambda *args: paints.append(args)
    return compiler, paints


class UnitPanelDividerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.paths = [GAME_UI / name for name in ('UnitPanel.xml', 'UnitPanel_small.xml')]
        cls.before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in cls.paths}
        cls.sources = []
        for path in cls.paths:
            source = ET.parse(path).getroot().find(".//*[@ID='WorkerActionPanel']/*[@ID='RecommendedActionDivider']")
            assert source is not None and source.tag == 'Image'
            cls.sources.append(dict(source.attrib))

    @classmethod
    def tearDownClass(cls):
        assert cls.before == {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in cls.paths}

    def node(self, source=None):
        attrs = copy.deepcopy(source or self.sources[1])
        return {'key': 16, 'kind': 'Image', 'id': attrs['ID'], 'attributes': attrs,
                'sourceAttributes': copy.deepcopy(attrs), 'hidden': False, 'disabled': False,
                'x': 126, 'y': 870, 'width': 240, 'height': 1, 'children': [],
                'texture': 'bar300x2.dds', 'textureX': 30, 'textureY': 0}

    def test_both_original_layouts_use_exact_crop_and_preserve_clip(self):
        for source in self.sources:
            with self.subTest(source=source):
                self.assertEqual(source, {'Anchor': 'C,T', 'ID': 'RecommendedActionDivider',
                    'Offset': '0,105', 'Size': '240.1', 'Texture': 'bar300x2.dds', 'TextureOffset': '30.0'})
                node = self.node(source)
                compiler, paints = compiler_for()
                clip = (0, 0, 1920, 1080)
                compiler.node(node, (106, 765, 280, 192), {}, clip)
                self.assertEqual(len(paints), 1)
                self.assertEqual(paints[0][2:5], ((30, 0, 270, 1), (126, 870, 366, 871), clip))
                self.assertEqual(compiler.geometry[0]['original_texture_source_extent'], [240, 1])
                self.assertEqual(compiler.geometry[0]['original_texture_source_policy'], POLICY)
                self.assertIs(compiler.geometry[0]['retail_texture_stretch_verified'], False)

    def test_changed_source_offset_extent_identity_and_context_are_rejected(self):
        for mutate in (
            lambda n: n.update(textureX=29), lambda n: n.update(textureY=1),
            lambda n: n.update(width=241), lambda n: n.update(height=2),
            lambda n: n.update(id='OtherDivider'), lambda n: n.update(texture='other.dds'),
            lambda n: n['sourceAttributes'].update(Size='241.1'),
            lambda n: n['sourceAttributes'].update(TextureOffset='29.0'),
            lambda n: n['sourceAttributes'].update(Offset='0,106'),
            lambda n: n['attributes'].update(Anchor='L,T'),
            lambda n: n['attributes'].update(TextureOffset='0.0'),
        ):
            node = self.node(); mutate(node)
            compiler, _ = compiler_for()
            with self.subTest(node=node), self.assertRaises(ValueError):
                compiler.node(node, (106, 765, 280, 192), {}, (0, 0, 1920, 1080))
        for context in ('city-view', 'top-panel', 'economic-overview', 'social-policy'):
            compiler, _ = compiler_for(context)
            with self.subTest(context=context), self.assertRaises(ValueError):
                compiler.node(self.node(), (106, 765, 280, 192), {}, (0, 0, 1920, 1080))

    def test_image_crop_permission_does_not_allow_other_atlas_combinations(self):
        normal = dict(key=16, texture_name='bar300x2.dds', u=30, v=0,
                      bounds=(126, 870, 240, 1), clip=(0, 0, 1920, 1080), color=(1, 1, 1, 1),
                      source_extent=(240, 1), unit_panel_divider=True)
        for replacement in ({'u': 0}, {'v': 1}, {'source_extent': (239, 1)},
                            {'source_extent': None}, {'bounds': (126, 870, 239, 1)},
                            {'stretch_full_texture': True}, {'economic_divider': True}):
            compiler, _ = compiler_for()
            with self.subTest(replacement=replacement), self.assertRaises(ValueError):
                compiler.image(**(normal | replacement))
        for context in ('city-view', 'economic-overview', 'top-panel'):
            compiler, _ = compiler_for(context)
            with self.subTest(context=context), self.assertRaises(ValueError):
                compiler.image(**normal)
        for texture_size in ((269, 2), (512, 1), (1024, 2)):
            compiler, _ = compiler_for(texture_size=texture_size)
            with self.subTest(texture_size=texture_size), self.assertRaises(ValueError):
                compiler.image(**normal)
        compiler, _ = compiler_for()
        with self.assertRaises(ValueError):
            compiler.image(**(normal | {'unit_panel_divider': False}))


if __name__ == '__main__':
    unittest.main()
