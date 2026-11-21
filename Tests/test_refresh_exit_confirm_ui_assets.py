"""Pure in-memory rejection tests for the bounded UI text producer."""
import ctypes
from pathlib import Path
import subprocess
import sys
import unittest

sys.dont_write_bytecode = True
PROJECT = Path(__file__).absolute().parents[1]
sys.path.insert(0, str(PROJECT / 'tools'))
import prepare_ui_popup_assets as preparer
import refresh_exit_confirm_ui_assets as refresh
import ui_font_profile as font_api


class CanonicalCatalogTests(unittest.TestCase):
    def header(self, texts):
        return refresh.render_header(texts, [], preparer)

    def test_original_order_and_non_ascii_bytes_round_trip(self):
        texts = [('First', b'function First()\r\nend\n'), ('Second', bytes((0x41, 0x80, 0xff)))]
        parsed, tail = refresh.parse_text_arrays(self.header(texts), preparer)
        self.assertEqual(parsed, texts)
        self.assertIn('{"First",First,sizeof(First)-1}', tail)
        self.assertLess(tail.index('First'), tail.index('Second'))

    def test_duplicate_hidden_payload_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            refresh.parse_text_arrays(self.header([('One', b'one'), ('One', b'two')]), preparer)

    def test_noncanonical_escape_and_nul_are_rejected(self):
        original = self.header([('One', b'A')])
        for changed in (original.replace(b'\\x41', b'\\101'), original.replace(b'\\x41', b'\\x00')):
            with self.subTest(changed=changed[-90:]):
                with self.assertRaises(ValueError):
                    refresh.parse_text_arrays(changed, preparer)

    def test_truncated_literal_and_source_injection_are_rejected(self):
        original = self.header([('One', b'A')])
        for changed in (original.replace(b'"\\x41";', b'"\\x41;'),
                        original.replace(b'"\\x41";', b'"\\x41" /* hidden */;')):
            with self.assertRaises(ValueError):
                refresh.parse_text_arrays(changed, preparer)

    def test_full_header_reconstruction_detects_fake_index_or_suffix(self):
        original = self.header([('One', b'A')])
        for changed in (original.replace(b'sizeof(One)-1', b'sizeof(One)'), original + b'int fake;\n'):
            arrays, _ = refresh.parse_text_arrays(changed, preparer)
            self.assertNotEqual(refresh.render_header(arrays, [], preparer), changed)

    def test_scene_preserves_all_six_private_state_guards(self):
        guards = [guard for _, _, guard in refresh.HOST_LUA[2:8]]
        sources = {key: b'-- addendum\n' for key, _, _ in refresh.HOST_LUA}
        sources['host_ui_runtime'] = '\n'.join(guards).encode('ascii')
        raw = refresh.scene_bytes(sources)
        self.assertEqual(len(refresh.HOST_LUA), 10)
        for guard in guards:
            self.assertIn(('\nif ' + guard + ' then\n').encode('ascii'), raw)
        sources['host_ui_runtime'] = b'no guards'
        with self.assertRaisesRegex(ValueError, 'guard missing'):
            refresh.scene_bytes(sources)


class SharedGlyphBoundaryTests(unittest.TestCase):
    def bank(self, glyph):
        return {'schema': font_api.BANK_SCHEMA, 'profileId': 'a' * 64,
                'glyphSets': {'b' * 64: glyph}}

    def glyph(self):
        return {'advance': 8, 'width': 7, 'height': 10, 'originX': 0, 'originY': -2}

    def test_json_keys_become_exact_integer_codepoints(self):
        bank = refresh.normalize_bank(self.bank({'65': self.glyph()}), font_api)
        self.assertEqual(set(bank['glyphSets']['b' * 64]), {65})
        self.assertEqual(bank['glyphSets']['b' * 64][65], self.glyph())

    def test_duplicate_boolean_noncanonical_and_extra_fields_fail(self):
        invalid = [
            {'65': self.glyph(), 65: self.glyph()},
            {'065': self.glyph()},
            {'65': dict(self.glyph(), width=True)},
            {'65': dict(self.glyph(), untrusted=1)},
        ]
        for glyphs in invalid:
            with self.subTest(glyphs=glyphs):
                with self.assertRaises(ValueError):
                    refresh.normalize_bank(self.bank(glyphs), font_api)

    def test_equal_digest_cannot_replace_metrics(self):
        bank = {'b' * 64: {65: self.glyph()}}
        metrics = {'fonts': {'TwCenMT22': {'sha256': 'b' * 64, 'glyphSet': 'b' * 64}},
                   'glyphSets': {'b' * 64: {65: dict(self.glyph(), advance=9)}}}
        with self.assertRaisesRegex(ValueError, 'different glyph metrics'):
            font_api.intern_font_metrics(metrics, bank, 'a' * 64)


class FileOnlyBoundaryTests(unittest.TestCase):
    def test_native_process_dll_full_main_and_resolver_are_denied(self):
        with refresh.FileOnlyGuard(preparer) as guard:
            calls = [lambda: subprocess.Popen(['never-run']), lambda: ctypes.CDLL('never-load'),
                     lambda: preparer.main(), lambda: preparer.UiAssets(Path('never-resolve'))]
            for call in calls:
                with self.assertRaisesRegex(RuntimeError, 'Forbidden'):
                    call()
            self.assertEqual(len(guard.rejected_calls), 4)

    def test_existing_frozen_parent_is_noop_and_new_directory_is_denied(self):
        with refresh.FileOnlyGuard(preparer) as guard:
            existing = PROJECT / 'Source/Assets/UI/Assets/UI'
            existing.mkdir(parents=True, exist_ok=True)
            self.assertIn(str(existing), guard.existing_mkdir_noops)
            with self.assertRaises((OSError, ValueError)):
                (existing / '__forbidden_new_directory__').mkdir()


if __name__ == '__main__':
    unittest.main()
