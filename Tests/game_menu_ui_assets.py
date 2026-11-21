"""Original GameMenu asset contract; no Host, native window, or child-menu proof.

Only the small Lua/XML/style sources are copied into a private temporary Build
directory. The test verifies installation hashes and removes that directory.
"""
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
import os
import re
import shutil
import stat
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / 'tools'))

import prepare_ui_popup_assets as freezer
from probe_world_builder import artifact


SOURCE_PATHS = {
    'GameMenu': 'Assets/UI/InGame/Menus/GameMenu.lua',
    'GameMenuLayout': 'Assets/DLC/Expansion2/UI/InGame/Menus/GameMenu.xml',
    'MapUtilities': 'Assets/Gameplay/Lua/MapUtilities.lua',
}


@contextmanager
def small_source_directory():
    build = (PROJECT / 'Build').resolve(strict=True)
    directory = Path(tempfile.mkdtemp(prefix='game-menu-assets-test-', dir=build))
    try:
        yield directory
    finally:
        # Check the absolute target and every ancestor/descendant before the
        # sole recursive deletion; never follow reparse points out of Build.
        absolute = Path(os.path.abspath(directory))
        if absolute.parent != build or not absolute.name.startswith('game-menu-assets-test-'):
            raise RuntimeError('GameMenu test cleanup escaped its private Build directory')
        reparse = getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400)
        for path in [*absolute.parents, absolute, *absolute.rglob('*')]:
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & reparse:
                raise RuntimeError('GameMenu test cleanup encountered a reparse point')
        shutil.rmtree(absolute)


def original_xml():
    return ET.parse(freezer.GAME / SOURCE_PATHS['GameMenuLayout']).getroot()


class GameMenuAssetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before = {name: artifact(freezer.GAME / relative)
                      for name, relative in SOURCE_PATHS.items()}
        cls.style_before = artifact(freezer.GAME / freezer.STYLE_SOURCE)

    @classmethod
    def tearDownClass(cls):
        for name, relative in SOURCE_PATHS.items():
            if artifact(freezer.GAME / relative) != cls.before[name]:
                raise AssertionError('An installed GameMenu source changed during the test')
        if artifact(freezer.GAME / freezer.STYLE_SOURCE) != cls.style_before:
            raise AssertionError('Installed Styles.xml changed during the test')

    def test_exact_base_lua_bnw_xml_and_real_include_registration(self):
        registry = dict(freezer.SCRIPTS + tuple((name, relative)
                        for name, relative, _ in freezer.LAYOUTS))
        for name, relative in SOURCE_PATHS.items():
            self.assertEqual(registry[name], relative)
        self.assertIn(('GameMenuLayout', SOURCE_PATHS['GameMenuLayout'], 'GameMenu'),
                      freezer.LAYOUTS)
        source = (freezer.GAME / SOURCE_PATHS['GameMenu']).read_text(encoding='utf-8-sig')
        includes = re.findall(r'^include\("([^"\n]+)"\);', source, re.MULTILINE)
        self.assertEqual(includes, ['IconSupport', 'SupportFunctions', 'InstanceManager', 'MapUtilities'])
        for name in includes:
            self.assertTrue((freezer.GAME / registry[name]).is_file(), name)

    def test_complete_original_tree_and_callback_controls_are_retained(self):
        original = original_xml()
        before = ET.tostring(original)
        tree = freezer.game_menu_control_tree(original)
        self.assertEqual(before, ET.tostring(original))
        metadata = tree.pop('gameMenu')
        self.assertEqual(tree, freezer.control_tree(original))
        self.assertEqual(metadata['retainedControlCount'], len(list(original.iter())))
        self.assertEqual(metadata['instanceNames'], ['GameOption', 'ModEntryInstance'])
        self.assertEqual(metadata['originalLua'], self.before['GameMenu'])
        self.assertEqual(metadata['originalXml'], self.before['GameMenuLayout'])
        self.assertEqual(metadata['originalMapUtilitiesLua'], self.before['MapUtilities'])
        controls = {node.get('ID'): node for node in original.iter() if node.get('ID')}
        source = (freezer.GAME / SOURCE_PATHS['GameMenu']).read_text(encoding='utf-8-sig')
        callbacks = re.findall(r'Controls\.([A-Za-z_][A-Za-z0-9_]*):RegisterCallback\(', source)
        self.assertTrue({'ReturnButton', 'QuickSaveButton', 'SaveGameButton', 'LoadGameButton',
                         'OptionsButton', 'Yes', 'No'}.issubset(callbacks))
        for name in callbacks:
            self.assertIn(name, controls)
            self.assertIn(controls[name].tag, ('Button', 'GridButton', 'TextButton'))
        self.assertFalse(metadata['childContextsRuntimeVerified'])
        self.assertFalse(metadata['retailLayoutVerified'])
        self.assertIs(metadata['loadMenuSourceApisBound'], True)
        self.assertEqual(metadata['sourceConnectedChildren'], ['SaveMenu', 'LoadMenu'])
        self.assertEqual(metadata['unconnectedLuaContexts'], [
            freezer.control_tree(node) for node in original if node.tag == 'LuaContext' and
            node.get('ID') not in ('SaveMenu', 'LoadMenu')])
        self.assertEqual(len(metadata['unconnectedLuaContexts']), 3)

    def test_mutations_cannot_hide_relabel_repoint_or_drop_original_controls(self):
        for change in ('button_hidden', 'button_string', 'child_hidden', 'child_file',
                       'child_defer', 'child_missing', 'template_missing', 'hover_missing',
                       'child_reorder'):
            candidate = deepcopy(original_xml())
            controls = {node.get('ID'): node for node in candidate.iter() if node.get('ID')}
            if change == 'button_hidden':
                controls['SaveGameButton'].set('Hidden', '1')
            elif change == 'button_string':
                controls['QuickSaveButton'].set('String', 'Replacement save button')
            elif change == 'child_hidden':
                controls['SaveMenu'].set('Hidden', '1')  # Even lexical source spelling is retained.
            elif change == 'child_file':
                controls['LoadMenu'].set('FileName', 'ReplacementLoadMenu')
            elif change == 'child_defer':
                controls['TouchControlsMenu'].set('DeferLoad', '0')
            elif change == 'child_missing':
                candidate.remove(controls['SaveMapMenu'])
            elif change == 'template_missing':
                candidate.remove(next(node for node in candidate if node.tag == 'Instance'))
            elif change == 'hover_missing':
                button = controls['ReturnButton']
                button.remove(button.find('ShowOnMouseOver'))
            else:
                candidate.remove(controls['LoadMenu'])
                candidate.append(controls['LoadMenu'])
            with self.subTest(change=change), self.assertRaises(ValueError):
                freezer.game_menu_control_tree(candidate)

    def test_small_frozen_sources_are_exact_reused_and_reject_tampering(self):
        with small_source_directory() as snapshots:
            for name, relative in SOURCE_PATHS.items():
                installed, frozen = freezer.freeze_source(relative, snapshots)
                self.assertEqual(installed, freezer.GAME / relative)
                self.assertEqual(installed.read_bytes(), frozen.read_bytes())
                self.assertEqual(artifact(installed), self.before[name])
                before = frozen.stat()
                self.assertEqual(freezer.freeze_source(relative, snapshots), (installed, frozen))
                after = frozen.stat()
                self.assertEqual((before.st_ino, before.st_mtime_ns),
                                 (after.st_ino, after.st_mtime_ns))
            target = snapshots / SOURCE_PATHS['GameMenu']
            target.write_bytes(target.read_bytes() + b'\n-- tampered fixture\n')
            tampered = target.read_bytes()
            with self.assertRaises(RuntimeError):
                freezer.freeze_source(SOURCE_PATHS['GameMenu'], snapshots)
            self.assertEqual(target.read_bytes(), tampered)

    def test_texture_inventory_contains_original_nested_style_dependencies(self):
        original = original_xml()
        tree = freezer.game_menu_control_tree(original)
        with small_source_directory() as snapshots:
            styles = freezer.production_style_defaults(snapshots, tree)
            tree['styleDefaults'] = styles['controls']
            expected = set()
            source_styles = {node.tag: node for node in
                             ET.parse(freezer.GAME / freezer.STYLE_SOURCE).getroot()}
            visited_styles = set()

            def collect(element):
                texture = element.get('Texture', '')
                if texture.casefold().endswith('.dds'):
                    expected.add(texture)
                style = element.get('Style')
                if style and style not in visited_styles:
                    visited_styles.add(style)
                    collect(source_styles[style])
                for child in element:
                    collect(child)

            collect(original)
            self.assertEqual(set(freezer.game_menu_texture_names(tree)), expected)
            self.assertIn('Assets/UI/Art/Controls/buttonsidesglow.dds', expected)
            self.assertIn('WindowTrimLeft_Tall.dds', expected)
            self.assertEqual(styles['source']['sha256'], self.style_before['sha256'])
            # DDS extraction and full asset generation are deliberately absent.
            self.assertEqual([p.suffix for p in snapshots.rglob('*') if p.is_file()], ['.xml'])


if __name__ == '__main__':
    unittest.main()
