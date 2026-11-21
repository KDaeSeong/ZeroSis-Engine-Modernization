"""Read-only registry/layout tests; no generated files or native APIs are used."""
from __future__ import annotations

import ast
import gzip
import hashlib
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
import xml.etree.ElementTree as ET


sys.dont_write_bytecode = True
PROJECT = Path(__file__).absolute().parents[1]
sys.path.insert(0, str(PROJECT / 'tools'))
import refresh_menu_suite_ui_assets as refresh
import prepare_ui_popup_assets as preparer
import menu_options_assets as options
import ui_font_profile as font_api


class MenuSuiteAssetRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.old = json.loads((PROJECT / 'evidence/ui_popup/assets/prepared.json').read_bytes())

    def test_74_payload_registry_has_only_the_five_intended_additions(self):
        names = [name for name, _ in preparer.SCRIPTS] + [name for name, _, _ in preparer.LAYOUTS]
        names += ['SharedFontMetrics', 'ZeroSisUiScene', 'ProductionCommandGuard', 'ResearchCommandGuard']
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(len(names), 74)
        self.assertEqual(set(refresh.NEW_LAYOUTS + refresh.NEW_SCRIPTS) - set(names), set())
        self.assertEqual(len(preparer.LAYOUTS), 30)

    def tree(self, name):
        _, relative, kind = next(row for row in preparer.LAYOUTS if row[0] == name)
        element = ET.parse(PROJECT / 'Source/Assets/UI' / relative).getroot()
        return (options.menu_options_control_tree(element, kind) if kind in ('MenuOptions', 'TouchHelp')
                else preparer.map_menu_control_tree(element))

    def test_all_three_layouts_preserve_every_original_node_attribute_and_child_order(self):
        for name in refresh.NEW_LAYOUTS:
            with self.subTest(name=name):
                tree = self.tree(name)
                _, relative, _ = next(row for row in preparer.LAYOUTS if row[0] == name)
                element = ET.parse(PROJECT / 'Source/Assets/UI' / relative).getroot()
                def actual(node):
                    return dict(kind=node.tag, attributes=dict(node.attrib), children=[actual(child) for child in node])
                self.assertEqual({key: tree[key] for key in ('kind', 'attributes', 'children')}, actual(element))
        metadata = self.tree('MapMenuLayout')['mapMenu']
        self.assertEqual(metadata['profile'], 'ORIGINAL_PRIVATE_MAP_MENU_V1')
        self.assertEqual(metadata['omittedStackGrowth'], 'Bottom')
        self.assertEqual(metadata['originalLua']['bytes'], 8537)
        self.assertEqual(metadata['originalXml']['bytes'], 6685)

    def test_new_layout_styles_and_font_references_reuse_existing_bank_without_font_loading(self):
        snapshots = PROJECT / 'Source/Assets/UI'
        with refresh.reuse.FileOnlyGuard(preparer), mock.patch.object(preparer, 'load_font', side_effect=AssertionError('font loader forbidden')), \
                mock.patch.object(preparer, 'production_font_metrics', side_effect=AssertionError('glyph extraction forbidden')):
            for name in refresh.NEW_LAYOUTS:
                tree = self.tree(name)
                defaults = preparer.production_style_defaults(snapshots, tree)
                tree['styleDefaults'] = defaults['controls']
                tree['fontMetrics'] = refresh.reuse_font_metrics(tree, self.old)
                resolved = font_api.resolve_prepared_font_metrics(self.old, tree['fontMetrics'])
                self.assertTrue(resolved['fonts'])
                self.assertNotIn('glyphSets', tree['fontMetrics'])
                self.assertEqual(tree['fontMetrics']['sharedProfileId'], self.old['shared_font_metrics']['profileId'])

    def test_unknown_new_font_fails_closed_instead_of_extracting_glyphs(self):
        tree = dict(kind='Context', attributes=dict(Font='UnknownNewFont'), children=[])
        with self.assertRaisesRegex(RuntimeError, 'absent from the retained bank'):
            refresh.reuse_font_metrics(tree, self.old)

    def test_options_checkbox_defaults_preserve_source_candidate_disclosure(self):
        with refresh.reuse.FileOnlyGuard(preparer):
            tree = self.tree('MenuOptionsLayout')
            defaults = options.menu_checkbox_defaults(tree, PROJECT / 'Source/Assets/UI')
        self.assertTrue(defaults)
        for value in defaults.values():
            self.assertEqual(value['style'], 'Button_16')
            self.assertFalse(value['defaultBindingVerified'])
            self.assertFalse(value['retailWidgetGeometryVerified'])
            self.assertEqual(value['width'], 32)

    def test_only_read_only_formatting_helpers_are_called_from_the_old_refresher(self):
        tree = ast.parse(Path(refresh.__file__).read_text(encoding='utf-8'))
        calls = {node.func.attr for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                 and isinstance(node.func.value, ast.Name) and node.func.value.id == 'reuse'}
        self.assertFalse(calls & {'main', 'prepare', 'apply'})
        self.assertFalse(any(isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and
                             node.func.attr in ('WinDLL', 'CDLL', 'LoadLibrary', 'production_font_metrics') for node in ast.walk(tree)))

    def test_old_header_reconstructs_from_only_old_scene_gzip_and_unchanged_arrays(self):
        temporary = tempfile.TemporaryDirectory(prefix='_menu_scene_recovery_', dir=PROJECT)
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        old_arrays = [('Other', b'-- retained payload\n'), ('ZeroSisUiScene', b'-- old scene\n')]
        new_arrays = [('Other', old_arrays[0][1]), ('ZeroSisUiScene', b'-- new scene\n')]
        original = refresh.reuse.render_header(old_arrays, [], preparer)
        current = root / 'header.h'
        current.write_bytes(refresh.reuse.render_header(new_arrays, [], preparer))
        def compressed(name, raw):
            path = root / name
            path.write_bytes(gzip.compress(raw, mtime=0))
            return dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(), backup=refresh.checked(path))
        recipe = dict(schema='zerosis.menu_suite_ui.header_reconstruction.v1',
            old_scene=compressed('old_scene.gz', old_arrays[1][1]),
            old_prepared=compressed('old_prepared.gz', b'{"purchase_audio":[]}'),
            expected_header=dict(bytes=len(original), sha256=hashlib.sha256(original).hexdigest()),
            unchanged_payloads=refresh.reuse.payload_identities([old_arrays[0]]))
        with mock.patch.object(refresh, 'HEADER', current), mock.patch.object(refresh.reuse, 'AUDIO', ()):
            self.assertEqual(refresh.reconstruct_prior_header(dict(header_recovery_ref=recipe)), original)
            current.write_bytes(refresh.reuse.render_header([('Other', b'-- unexpected change\n'), new_arrays[1]], [], preparer))
            with self.assertRaisesRegex(RuntimeError, 'outside the old-scene recovery role'):
                refresh.reconstruct_prior_header(dict(header_recovery_ref=recipe))


if __name__ == '__main__':
    unittest.main()
