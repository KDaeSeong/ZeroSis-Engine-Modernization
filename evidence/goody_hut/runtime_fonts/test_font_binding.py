"""Read-only font binding and renderer carrier tests; no pixels or native run.

The actual sealed fifteen-file cache is read, never modified. Negative payloads
are in-memory copies. Font-atlas materialization is virtualized so Compiler.font
can prove its real source selection without creating any image or runtime.
"""
from __future__ import annotations

from contextlib import contextmanager
import copy
from dataclasses import replace
import hashlib
import io
import json
import os
from pathlib import Path
import sys
from types import MappingProxyType, SimpleNamespace
import unittest
from unittest.mock import patch


STAGE = Path(__file__).absolute().parent
PROJECT = STAGE.parents[2]
PREPARED = PROJECT / 'evidence/ui_popup/assets/prepared.json'
PROFILE = PROJECT / 'Source/Assets/UI/font_input_profile.json'
CONTENT_ID = '06ba57aa477fc561db3f97089f98bf1cf70a34c047b8fa8dbcee2fc1d255a617'
CACHE = PROJECT / 'Build/SharedUiFontInputs' / CONTENT_ID
FONT_IDS = ('TwCenMT14', 'TwCenMT16', 'TwCenMT18', 'TwCenMT20', 'TwCenMT22', 'TwCenMT24')
EXPECTED_PATHS = {'Assets/UI/ColorAtlas.xml'} | {
    'Assets/UI/Fonts/Tw Cent MT/' + font_id + '.ggxml' for font_id in FONT_IDS
} | {'kTwCenMT%d%s.dds' % (size, suffix)
     for size in (14, 18, 20, 22) for suffix in ('', 'Shadow')}

sys.dont_write_bytecode = True
sys.path.insert(0, str(PROJECT / 'tools'))
import ui_pixel_scene as pixel
import ui_bitmap_fonts as bitmap_fonts
import render_ui_popup as renderer


def path_key(path):
    return os.path.normcase(os.path.abspath(os.fspath(path)))


def file_identity(path):
    path = Path(path)
    info = path.lstat()
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    after = path.lstat()
    identity = lambda row: (row.st_dev, row.st_ino, row.st_size, row.st_mtime_ns,
                            row.st_nlink, getattr(row, 'st_file_attributes', 0))
    if identity(info) != identity(after):
        raise AssertionError('Owned font changed during the independent test hash')
    return {'path': str(path), 'bytes': info.st_size, 'sha256': digest,
            'identity': list(identity(info))}


class OwnedFontBindingTests(unittest.TestCase):
    """Exercise actual cache identities while fencing every content read."""
    input_preservation_verified = False
    denied_reads = []
    glyph_counts = {}
    carrier_contexts = []

    @classmethod
    def setUpClass(cls):
        if PREPARED.stat().st_size > 64 * 1024 * 1024:
            raise AssertionError('Prepared catalog exceeds the reviewed test input bound')
        full = json.loads(PREPARED.read_text(encoding='utf-8'))
        cls.prepared = {name: full[name] for name in
                        ('compiled_assets', 'font_input_profile', 'shared_font_metrics')}
        cls.rows = copy.deepcopy(cls.prepared['font_input_profile']['original_inputs'])
        cls.allowed = {path_key(row['path']) for row in cls.rows}
        if len(cls.rows) != 15 or len(cls.allowed) != 15:
            raise AssertionError('The test must inspect the actual fifteen-file font cache')
        if Path(cls.prepared['font_input_profile']['asset_root']) != CACHE:
            raise AssertionError('Test input is not the exact currently sealed owned font cache')
        cls.before = [file_identity(row['path']) for row in cls.rows]
        cls.before_by_path = {path_key(row['path']): row for row in cls.before}
        for row in cls.rows:
            observed = cls.before_by_path[path_key(row['path'])]
            if (observed['bytes'], observed['sha256']) != (row['bytes'], row['sha256']):
                raise AssertionError('Actual owned input differs from its frozen preparation ref')

    @classmethod
    def tearDownClass(cls):
        cls.after = [file_identity(row['path']) for row in cls.rows]
        if cls.before != cls.after:
            raise AssertionError('Read-only tests changed an owned font payload or file identity')
        cls.input_preservation_verified = True

    @contextmanager
    def cache_reads_only(self):
        """Forbid mutable profiles, installed fonts, and all other content reads."""
        real_open = io.open
        reads = []
        blocked = []

        def guarded_open(file, mode='r', *args, **kwargs):
            if not isinstance(file, (str, bytes, os.PathLike)):
                raise AssertionError('Unexpected file-descriptor access in font binding')
            candidate = path_key(os.fsdecode(file))
            if any(char in mode for char in 'wax+'):
                raise AssertionError('Font binding tests must not write files')
            if candidate not in self.allowed:
                blocked.append(str(file));type(self).denied_reads.append(str(file))
                raise AssertionError('Font binding attempted an unsealed content read')
            reads.append(candidate)
            return real_open(file, mode, *args, **kwargs)

        with patch('io.open', side_effect=guarded_open), patch('builtins.open', side_effect=guarded_open):
            yield reads
        self.assertFalse(blocked, 'Binding must not fall back to an installed font or mutable source profile')
        self.assertNotIn(path_key(PROFILE), reads)

    def binding(self, prepared=None):
        with self.cache_reads_only() as reads:
            result = pixel.owned_font_input_binding(self.prepared if prepared is None else prepared)
        return result, reads

    def rejected(self, prepared):
        with self.cache_reads_only():
            with self.assertRaises((RuntimeError, ValueError, OSError)):
                pixel.owned_font_input_binding(prepared)

    def clone(self):
        return copy.deepcopy(self.prepared)

    def test_01_legacy_absent_fields_returns_none_without_font_reads(self):
        for legacy in ({}, {'compiled_assets': self.prepared['compiled_assets']}):
            with self.subTest(legacy=tuple(legacy)):
                result, reads = self.binding(legacy)
                self.assertIsNone(result)
                self.assertEqual(reads, [])

    def test_02_actual_fifteen_inputs_form_the_exact_content_address(self):
        binding, reads = self.binding()
        self.assertEqual(set(binding), {'schema', 'asset_root', 'profile_id', 'cache_content_id', 'inputs'})
        self.assertEqual(binding['schema'], 'zerosis.ui.owned_font_binding.v1')
        self.assertEqual(Path(binding['asset_root']), CACHE)
        self.assertEqual(binding['cache_content_id'], CONTENT_ID)
        self.assertEqual(binding['profile_id'], self.prepared['shared_font_metrics']['profileId'])
        actual = {Path(row['path']).relative_to(CACHE).as_posix(): row for row in binding['inputs']}
        self.assertEqual(set(actual), EXPECTED_PATHS)
        self.assertEqual({path_key(row['path']) for row in binding['inputs']}, self.allowed)
        self.assertEqual(set(reads), self.allowed)
        inventory = sorted((relative, row['bytes'], row['sha256']) for relative, row in actual.items())
        derived = hashlib.sha256(json.dumps(inventory, separators=(',', ':'), ensure_ascii=True).encode('ascii')).hexdigest()
        self.assertEqual(derived, CONTENT_ID)
        after_binding, after_reads = self.binding()
        self.assertEqual(after_binding, binding)
        self.assertEqual(set(after_reads), self.allowed)

    def test_03_six_real_fonts_and_full_glyph_maps_use_only_owned_sources(self):
        bank = self.prepared['shared_font_metrics']['glyphSets']
        hashes = set()
        with self.cache_reads_only():
            for font_id in FONT_IDS:
                font = bitmap_fonts.load_font(CACHE, font_id, 'Base')
                hashes.add(font.ggxml_sha256)
                self.assertEqual(len(font.glyphs), 2529)
                self.assertTrue(font.ggxml_path.is_relative_to(CACHE))
                self.assertTrue(font.color_atlas_path.is_relative_to(CACHE))
                self.assertTrue(all(sheet.path.is_relative_to(CACHE) for sheet in font.sheets.values()))
                expected = bank[font.ggxml_sha256]
                self.assertEqual(set(map(int, expected)), set(font.glyphs))
                for codepoint, glyph in font.glyphs.items():
                    self.assertEqual(expected[str(codepoint)], {
                        'advance': glyph.a + glyph.b + glyph.c, 'width': glyph.width,
                        'height': glyph.height, 'originX': glyph.origin_x, 'originY': glyph.origin_y})
                type(self).glyph_counts[font_id] = len(font.glyphs)
        self.assertEqual(hashes, set(bank))
        self.assertEqual(len(hashes), 4)

    def test_04_frozen_module_location_and_stale_profile_paths_do_not_redirect_fonts(self):
        prepared = self.clone()
        prepared['font_input_profile']['manifest'] = {
            'path': str(PROJECT / 'Source/Assets/UI/does-not-exist-profile.json'), 'sha256': '0' * 64}
        prepared['font_input_profile']['helper'] = {
            'path': str(PROJECT / 'tools/does-not-exist-profile-helper.py'), 'sha256': '0' * 64}
        frozen_file = PROJECT / 'Build/InteractiveGameRuntime/20261017T233110Z_b4d9e31f65f9' / \
            'interactive_ui_support/tools/ui_pixel_scene.py'
        with patch.object(pixel, '__file__', str(frozen_file)):
            binding, reads = self.binding(prepared)
        self.assertEqual(Path(binding['asset_root']), CACHE)
        self.assertEqual(set(reads), self.allowed)

    def test_05_partial_or_explicitly_invalid_owned_fields_never_select_legacy(self):
        cases = [None, [], 'legacy', {'font_input_profile': None, 'shared_font_metrics': None}]
        for field in ('font_input_profile', 'shared_font_metrics'):
            prepared = self.clone();prepared.pop(field);cases.append(prepared)
            prepared = self.clone();prepared[field] = None;cases.append(prepared)
            prepared = self.clone();prepared[field] = [];cases.append(prepared)
        for index, prepared in enumerate(cases):
            with self.subTest(case=index):
                self.rejected(prepared)

    def test_06_profile_and_shared_bank_must_agree(self):
        for field, value in (('input_storage', 'INSTALLED_GAME_FALLBACK'), ('profile_id', '0' * 64),
                             ('profile_id', 'not-a-digest')):
            prepared = self.clone();prepared['font_input_profile'][field] = value
            with self.subTest(metadata=field, value=value):
                self.rejected(prepared)
        for field, value in (('schema', 'zerosis.ui.shared_font_metrics.v999'), ('profileId', '0' * 64),
                             ('glyphSets', [])):
            prepared = self.clone();prepared['shared_font_metrics'][field] = value
            with self.subTest(bank=field):
                self.rejected(prepared)

    def test_07_complete_four_set_inventory_is_bound_to_six_ggxml_refs(self):
        for operation in ('remove', 'extra', 'empty'):
            prepared = self.clone();sets = prepared['shared_font_metrics']['glyphSets']
            first = next(iter(sets))
            if operation == 'remove':
                sets.pop(first)
            elif operation == 'extra':
                sets['0' * 64] = sets[first]
            else:
                sets[first] = {}
            with self.subTest(operation=operation):
                self.rejected(prepared)

    def test_08_missing_duplicate_and_unexpected_input_paths_are_rejected(self):
        cases = []
        prepared = self.clone();prepared['font_input_profile']['original_inputs'].pop();cases.append(prepared)
        prepared = self.clone();rows = prepared['font_input_profile']['original_inputs'];rows[-1] = dict(rows[0]);cases.append(prepared)
        prepared = self.clone();prepared['font_input_profile']['original_inputs'][0]['path'] = str(CACHE / 'unselected.dds');cases.append(prepared)
        prepared = self.clone();prepared['font_input_profile']['original_inputs'][0]['path'] = str(PROFILE);cases.append(prepared)
        prepared = self.clone();row = prepared['font_input_profile']['original_inputs'][0]
        path = Path(row['path']);row['path'] = str(path.parent / '..' / path.parent.name / path.name);cases.append(prepared)
        for index, prepared in enumerate(cases):
            with self.subTest(case=index):
                self.rejected(prepared)

    def test_09_root_and_header_must_name_the_same_canonical_engine_project(self):
        roots = (str(CACHE.parent / ('0' * 64)), str(PROJECT), str(CACHE / '..' / CONTENT_ID),
                 r'C:\Program Files (x86)\Steam\steamapps\common\Sid Meier\Civilization V')
        for root in roots:
            prepared = self.clone();prepared['font_input_profile']['asset_root'] = root
            with self.subTest(root=root):
                self.rejected(prepared)
        for header in (str(PROJECT / 'Source/Host/wrong.generated.h'),
                       str(PROJECT.parent / 'ForeignEngine/Source/Host/UiPopupAssets.generated.h')):
            prepared = self.clone();prepared['compiled_assets']['path'] = header
            with self.subTest(header=header):
                self.rejected(prepared)
        prepared = self.clone();prepared.pop('compiled_assets');self.rejected(prepared)

    def test_10_input_refs_are_exact_and_must_match_payload_sizes_and_hashes(self):
        for operation in ('omit_size', 'extra_field', 'bool_size', 'wrong_size', 'wrong_sha', 'uppercase_sha'):
            prepared = self.clone();row = prepared['font_input_profile']['original_inputs'][0]
            if operation == 'omit_size':
                row.pop('bytes')
            elif operation == 'extra_field':
                row['untrusted'] = True
            elif operation == 'bool_size':
                row['bytes'] = True
            elif operation == 'wrong_size':
                row['bytes'] += 1
            elif operation == 'wrong_sha':
                row['sha256'] = '0' * 64
            else:
                row['sha256'] = row['sha256'].upper()
            with self.subTest(operation=operation):
                self.rejected(prepared)

    def test_11_root_and_input_reparse_points_are_rejected_without_source_reads(self):
        real_lstat = Path.lstat
        for target in (CACHE, Path(self.rows[1]['path'])):
            def tagged(path, *args, **kwargs):
                info = real_lstat(path, *args, **kwargs)
                if path_key(path) != path_key(target):
                    return info
                values = {name: getattr(info, name) for name in dir(info) if name.startswith('st_')}
                values['st_file_attributes'] = values.get('st_file_attributes', 0) | 0x400
                return SimpleNamespace(**values)
            with self.subTest(target=target.name), patch.object(Path, 'lstat', tagged):
                self.rejected(self.prepared)

    def test_12_actual_cache_hash_drift_is_rejected_without_installed_fallback(self):
        real_sha = pixel.sha256
        targets = [next(row['path'] for row in self.rows if row['path'].endswith(suffix))
                   for suffix in ('.ggxml', '.dds')]
        for target in targets:
            def drift(path):
                return '0' * 64 if path_key(path) == path_key(target) else real_sha(path)
            with self.subTest(kind=Path(target).suffix), patch.object(pixel, 'sha256', side_effect=drift):
                self.rejected(self.prepared)

    def test_13_compiler_loads_cache_glyphs_and_atlases_with_no_materialization(self):
        compiler = pixel.Compiler.__new__(pixel.Compiler)
        compiler.game_root = PROJECT / 'Build/UnusableInstalledFontRoot'
        compiler.font_root = CACHE
        compiler.font_input_refs = {Path(row['path']): dict(row) for row in self.rows}
        compiler.destination = STAGE / 'virtual-font-scene-not-created'
        compiler.fonts, compiler.font_records = {}, []
        virtual = {}
        materializations = []
        real_sha = pixel.sha256

        def destination(path, unused_game_root):
            return Path(path)

        def materialize(source, output, digest):
            self.assertTrue(Path(source).is_relative_to(CACHE))
            self.assertEqual(real_sha(source), digest)
            materializations.append((str(source), str(output), digest))
            virtual[path_key(output)] = digest

        def virtual_sha(path):
            return virtual[path_key(path)] if path_key(path) in virtual else real_sha(path)

        with self.cache_reads_only(), patch.object(pixel, 'candidate_directory', side_effect=destination), \
                patch.object(pixel, 'materialize_font_atlas', side_effect=materialize), \
                patch.object(pixel, 'sha256', side_effect=virtual_sha), \
                patch.object(pixel, 'load_font', wraps=bitmap_fonts.load_font) as loader:
            for style in ('Base', 'Shadow'):
                font = compiler.font('TwCenMT22', style)
                self.assertEqual(font.game_root, CACHE)
                self.assertEqual(len(font.glyphs), 2529)
                self.assertEqual(font.glyphs[ord('A')].abc_advance,
                                 self.prepared['shared_font_metrics']['glyphSets'][font.ggxml_sha256][str(ord('A'))]['advance'])
            self.assertEqual(loader.call_count, 2)
            self.assertTrue(all(Path(call.args[0]) == CACHE for call in loader.call_args_list))
            # A repeated font request must use its retained parsed asset.
            compiler.font('TwCenMT22', 'Base')
            self.assertEqual(loader.call_count, 2)
        self.assertTrue(materializations)
        self.assertTrue(all(Path(row['ggxml_path']).is_relative_to(CACHE) and
                            Path(row['color_atlas_path']).is_relative_to(CACHE) and
                            all(Path(sheet['source_path']).is_relative_to(CACHE) for sheet in row['sheets'])
                            for row in compiler.font_records))
        self.assertFalse(compiler.destination.exists())

    def test_14_unselected_font_id_is_rejected_before_any_glyph_or_atlas_load(self):
        compiler = pixel.Compiler.__new__(pixel.Compiler)
        compiler.game_root = PROJECT / 'Build/UnusableInstalledFontRoot'
        compiler.font_root = CACHE
        compiler.font_input_refs = {Path(row['path']): dict(row) for row in self.rows}
        compiler.fonts, compiler.font_records = {}, []
        with self.cache_reads_only() as reads, \
                patch.object(pixel, 'load_font', side_effect=AssertionError('Unselected font parser called')) as loader, \
                patch.object(pixel, 'materialize_font_atlas', side_effect=AssertionError('Unselected font atlas copied')) as atlas:
            with self.assertRaises((RuntimeError, ValueError)):
                compiler.font('TwCenMT30', 'Base')
        self.assertEqual(reads, [])
        self.assertEqual(loader.call_count, 0)
        self.assertEqual(atlas.call_count, 0)

    def test_15_foreign_font_atlas_is_rejected_before_any_materialization(self):
        compiler = pixel.Compiler.__new__(pixel.Compiler)
        compiler.game_root = PROJECT / 'Build/UnusableInstalledFontRoot'
        compiler.font_root = CACHE
        compiler.font_input_refs = {Path(row['path']): dict(row) for row in self.rows}
        compiler.fonts, compiler.font_records = {}, []
        with self.cache_reads_only():
            font = bitmap_fonts.load_font(CACHE, 'TwCenMT22', 'Base')
        sheets = dict(font.sheets)
        first = next(iter(sheets))
        sheets[first] = replace(sheets[first], path=PROJECT / 'Build/UnsealedFontAtlas.dds')
        altered = replace(font, sheets=MappingProxyType(sheets),
                          layers=tuple(replace(layer, sheet=sheets[layer.texture_alias]) for layer in font.layers))
        with self.cache_reads_only(), patch.object(pixel, 'load_font', return_value=altered) as loader, \
                patch.object(pixel, 'materialize_font_atlas', side_effect=AssertionError('Foreign atlas copied')) as atlas:
            with self.assertRaises((RuntimeError, ValueError)):
                compiler.font('TwCenMT22', 'Base')
        self.assertEqual(loader.call_count, 1)
        self.assertEqual(atlas.call_count, 0)
        self.assertEqual(compiler.font_records, [])

    def test_16_every_live_prepare_context_passes_its_frozen_binding_before_compilation(self):
        """Exercise the real carrier reads, stopping before any output or pixels."""
        class StopBeforeCompiler(RuntimeError):
            pass

        directory = STAGE / 'virtual-prepare-scene-not-created'
        snapshot_path = STAGE / 'virtual-snapshot-not-created.json'
        support_path = STAGE / 'virtual-support-not-created.json'
        frozen_path = STAGE / 'virtual-frozen-prepared-not-created.json'
        manifest_path = directory / 'scene_manifest.json'
        real_read_text, real_is_file, real_sha = Path.read_text, Path.is_file, renderer.sha256
        expected_binding, _ = self.binding()

        for context in pixel.SCENE_CONTEXTS:
            with self.subTest(context=context):
                payloads, carrier_reads, constructor_calls = {}, [], []

                def put(path, value):
                    raw = json.dumps(value, ensure_ascii=True, separators=(',', ':')).encode('ascii')
                    payloads[path_key(path)] = raw
                    return {'path': str(path), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}

                frozen = put(frozen_path, self.prepared)
                support = put(support_path, {'asset_preparation_provenance': frozen})
                put(directory / 'preparation_inputs.json', {'support_manifest': support})
                put(directory / 'inline_colors.json', {'colors': {}})
                put(directory / 'inline_icons.json', {'icons': {}})
                snapshot = {'presentationClock': 0,
                            'cityView': {'layoutVariant': 'default', 'smallUIAssets': False},
                            'unitPanel': {'layoutVariant': 'default', 'smallUIAssets': False,
                                          'retailLayoutVariantSelectionVerified': False}}
                put(snapshot_path, snapshot)

                def text(path, *args, **kwargs):
                    identity = path_key(path)
                    if identity in payloads:
                        carrier_reads.append(identity)
                        return payloads[identity].decode('ascii')
                    return real_read_text(path, *args, **kwargs)

                def exists(path):
                    return True if path_key(path) in payloads else real_is_file(path)

                def digest(path):
                    return hashlib.sha256(payloads[path_key(path)]).hexdigest() \
                        if path_key(path) in payloads else real_sha(path)

                def constructor(game_root, destination, **kwargs):
                    constructor_calls.append((game_root, destination, kwargs))
                    raise StopBeforeCompiler('Carrier transfer proved; no Compiler initialization or output follows')

                with self.cache_reads_only(), patch.object(Path, 'read_text', text), \
                        patch.object(Path, 'is_file', exists), patch.object(renderer, 'sha256', side_effect=digest), \
                        patch.object(renderer, 'Compiler', side_effect=constructor):
                    with self.assertRaises(StopBeforeCompiler):
                        renderer.prepare(snapshot_path, directory, manifest_path, context=context)
                self.assertEqual(len(constructor_calls), 1)
                game_root, destination, kwargs = constructor_calls[0]
                self.assertEqual(Path(game_root), renderer.GAME)
                self.assertEqual(Path(destination), directory)
                self.assertEqual(Path(kwargs['font_root']), CACHE)
                self.assertEqual(kwargs['font_binding'], expected_binding)
                self.assertEqual(kwargs['context'], context)
                self.assertEqual(kwargs['economic_overview_prepared'],
                                 self.prepared if context == 'economic-overview' else None)
                self.assertIn(path_key(directory / 'preparation_inputs.json'), carrier_reads)
                self.assertIn(path_key(support_path), carrier_reads)
                self.assertIn(path_key(frozen_path), carrier_reads)
                self.assertNotIn(path_key(PROFILE), carrier_reads)
                self.assertFalse(directory.exists())
                self.assertFalse(manifest_path.exists())
                type(self).carrier_contexts.append(context)


def main():
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(OwnedFontBindingTests)
    result = unittest.TextTestRunner(verbosity=2, stream=sys.stderr).run(suite)
    passed = result.wasSuccessful() and OwnedFontBindingTests.input_preservation_verified and \
        not OwnedFontBindingTests.denied_reads
    print(json.dumps({'status': 'PASS_OWNED_FONT_BINDING_PYTHON_NO_NATIVE' if passed else 'FAILED_OWNED_FONT_BINDING',
                      'tests_run': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors),
                      'actual_owned_inputs': len(getattr(OwnedFontBindingTests, 'rows', [])),
                      'unique_glyph_sets': 4, 'glyph_counts': OwnedFontBindingTests.glyph_counts,
                      'frozen_carrier_contexts_before_compiler': OwnedFontBindingTests.carrier_contexts,
                      'compiler_constructor_executed': False,
                      'owned_inputs_unchanged': OwnedFontBindingTests.input_preservation_verified,
                      'blocked_unsealed_read_attempts': len(OwnedFontBindingTests.denied_reads),
                      'source_profile_read': False, 'installed_font_fallback': False,
                      'atlas_payload_copies': 0,
                      'renderer_prepare_prefix_executed': bool(OwnedFontBindingTests.carrier_contexts),
                      'pixels_or_packet_rendered': False, 'native_executed': False,
                      'retail_user_state_accessed': False, 'native_acceptance_verified': False}, sort_keys=True))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
