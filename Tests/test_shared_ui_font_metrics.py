"""Pure in-memory tests for lossless shared UI glyph transport.

No font files, DLLs, game processes, windows, saved games or scratch outputs are
opened. The large fixture preserves every record in a changed 17,315-glyph set.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest

sys.dont_write_bytecode = True
PROJECT = Path(__file__).absolute().parents[1]
sys.path.insert(0, str(PROJECT / 'tools'))
from ui_font_profile import (
    BANK_SCHEMA, STORAGE_TAG, TRANSPORT_FIELDS, intern_font_metrics,
    resolve_prepared_font_metrics,
)

PROFILE = hashlib.sha256(b'selected-original-font-input-profile').hexdigest()
FONT_A = hashlib.sha256(b'original-font-A.ggxml').hexdigest()
FONT_B = hashlib.sha256(b'original-font-B.ggxml').hexdigest()
SOURCE_GLYPH_COUNT = 17315


def glyph(codepoint):
    return {'advance': codepoint % 31, 'width': codepoint % 29, 'height': codepoint % 37,
            'originX': -(codepoint % 7), 'originY': codepoint % 11}


def metadata(identity):
    return {'glyphSet': identity, 'sha256': identity, 'ggxmlPath': 'Assets/UI/Fonts/selected.ggxml',
            'lineAdvance': 24, 'baselineOffset': -2, 'spacing': 0, 'fudgeadv': 1}


def inline_metrics(glyphs=None):
    return {'policy': 'CIV5_GLYPHGEN_GGXML_LAYOUT_V1', 'retailMetricSemanticsVerified': False,
            'wrapPolicy': 'GREEDY_ASCII_SPACE_WORD_WRAP_SPLIT_LONG_WORD_AT_CODEPOINT',
            'fonts': {'TwCenMT20': metadata(FONT_A)},
            'glyphSets': {FONT_A: glyphs if glyphs is not None else {32: glyph(32), 65: glyph(65)}}}


def shared_fixture():
    source = inline_metrics()
    compact = {name: copy.deepcopy(value) for name, value in source.items() if name != 'glyphSets'}
    compact.update(glyphSetStorage=STORAGE_TAG, sharedProfileId=PROFILE, glyphSetRefs=[FONT_A])
    prepared = {'shared_font_metrics': {'schema': BANK_SCHEMA, 'profileId': PROFILE,
                                      'glyphSets': {FONT_A: {'32': glyph(32), '65': glyph(65)}}}}
    return source, compact, prepared


class SharedUiFontMetrics(unittest.TestCase):
    def test_full_changed_set_round_trip_preserves_every_source_integer(self):
        values = {codepoint: glyph(codepoint) for codepoint in range(SOURCE_GLYPH_COUNT)}
        source = inline_metrics(values)
        source['fonts']['TwCenMT22'] = metadata(FONT_A)
        untouched = copy.deepcopy(source)
        bank = {}
        compact = intern_font_metrics(source, bank, PROFILE)
        self.assertEqual(source, untouched)
        self.assertNotIn('glyphSets', compact)
        self.assertEqual(compact['glyphSetRefs'], [FONT_A])
        self.assertEqual(len(bank), 1)
        self.assertEqual(bank[FONT_A], values)
        self.assertEqual(len(bank[FONT_A]), SOURCE_GLYPH_COUNT)
        # Exercise JSON's real integer-key loss, then resolve only the selected layout.
        prepared, stored = json.loads(json.dumps([
            {'shared_font_metrics': {'schema': BANK_SCHEMA, 'profileId': PROFILE, 'glyphSets': bank}}, compact]))
        encoded_before = json.dumps(prepared, sort_keys=True)
        resolved = resolve_prepared_font_metrics(prepared, stored)
        self.assertEqual(resolved, untouched)
        self.assertEqual(len(resolved['glyphSets'][FONT_A]), SOURCE_GLYPH_COUNT)
        self.assertEqual(set(resolved['glyphSets'][FONT_A]), set(range(SOURCE_GLYPH_COUNT)))
        self.assertTrue(all(type(value) is int for record in resolved['glyphSets'][FONT_A].values()
                            for value in record.values()))
        self.assertEqual(json.dumps(prepared, sort_keys=True), encoded_before)
        self.assertTrue(all(field not in resolved for field in TRANSPORT_FIELDS))
        self.assertLess(len(json.dumps(stored)), 2000)
        second = intern_font_metrics(source, bank, PROFILE)
        self.assertEqual(second, compact)
        self.assertEqual(len(bank), 1)

    def test_legacy_inline_json_is_still_supported_without_a_bank(self):
        source = inline_metrics()
        stored = json.loads(json.dumps(source))
        before = copy.deepcopy(stored)
        self.assertEqual(resolve_prepared_font_metrics({}, stored), source)
        self.assertEqual(stored, before)

    def test_selected_layout_does_not_expand_or_mutate_unrelated_bank_maps(self):
        source, compact, prepared = shared_fixture()
        prepared['shared_font_metrics']['glyphSets'][FONT_B] = {'unused-record': None}
        untouched = copy.deepcopy(prepared)
        result = resolve_prepared_font_metrics(prepared, compact)
        self.assertEqual(result, source)
        self.assertEqual(set(result['glyphSets']), {FONT_A})
        self.assertEqual(prepared, untouched)
        result['glyphSets'][FONT_A][32]['advance'] += 1
        self.assertEqual(prepared, untouched)

    def test_missing_bank_and_missing_referenced_set_are_rejected(self):
        _, compact, prepared = shared_fixture()
        for missing in ({}, {'shared_font_metrics': None}):
            with self.subTest(missing=missing), self.assertRaises(ValueError):
                resolve_prepared_font_metrics(missing, compact)
        prepared['shared_font_metrics']['glyphSets'].clear()
        with self.assertRaises(ValueError):
            resolve_prepared_font_metrics(prepared, compact)

    def test_duplicate_sparse_or_unsorted_reference_inventory_is_rejected(self):
        _, compact, prepared = shared_fixture()
        compact['fonts']['TwCenMT22'] = metadata(FONT_B)
        prepared['shared_font_metrics']['glyphSets'][FONT_B] = {'32': glyph(32)}
        for references in ([FONT_A, FONT_A], {1: FONT_A, 3: FONT_B},
                           list(reversed(sorted([FONT_A, FONT_B]))), [FONT_A]):
            with self.subTest(references=references), self.assertRaises(ValueError):
                resolve_prepared_font_metrics(prepared, {**compact, 'glyphSetRefs': references})

    def test_mixed_partial_or_unknown_storage_is_rejected(self):
        source, compact, prepared = shared_fixture()
        cases = [{**compact, 'glyphSets': source['glyphSets']},
                 {**compact, 'glyphSetStorage': 'UNKNOWN_STORAGE'}]
        for missing in TRANSPORT_FIELDS:
            cases.append({name: value for name, value in compact.items() if name != missing})
        for case in cases:
            with self.subTest(fields=sorted(case)), self.assertRaises(ValueError):
                resolve_prepared_font_metrics(prepared, case)

    def test_profile_mismatch_and_foreign_bank_schema_are_rejected(self):
        _, compact, prepared = shared_fixture()
        for field, value in (('profileId', '0' * 64), ('schema', 'unknown-schema')):
            changed = copy.deepcopy(prepared)
            changed['shared_font_metrics'][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                resolve_prepared_font_metrics(changed, compact)
        changed = copy.deepcopy(prepared)
        changed['shared_font_metrics']['unexpected'] = True
        with self.assertRaises(ValueError):
            resolve_prepared_font_metrics(changed, compact)

    def test_stale_source_sha_cannot_masquerade_as_a_glyph_set(self):
        _, compact, prepared = shared_fixture()
        for field, value in (('sha256', FONT_B), ('glyphSet', FONT_B), ('glyphSet', 'NOT_A_SHA')):
            changed = copy.deepcopy(compact)
            changed['fonts']['TwCenMT20'][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                resolve_prepared_font_metrics(prepared, changed)

    def test_same_sha_cannot_silently_replace_different_metrics(self):
        source = inline_metrics()
        bank = {}
        intern_font_metrics(source, bank, PROFILE)
        untouched = copy.deepcopy(bank)
        changed = copy.deepcopy(source)
        changed['glyphSets'][FONT_A][32]['originX'] -= 1
        with self.assertRaises(ValueError):
            intern_font_metrics(changed, bank, PROFILE)
        self.assertEqual(bank, untouched)

    def test_duplicate_integer_and_string_codepoints_are_rejected(self):
        source = inline_metrics({32: glyph(32), '32': glyph(32)})
        with self.assertRaises(ValueError):
            resolve_prepared_font_metrics({}, source)

    def test_noncanonical_and_out_of_range_codepoints_are_rejected(self):
        for codepoint in ('032', '-1', '1.5', 0x110000, -1, True):
            with self.subTest(codepoint=codepoint), self.assertRaises(ValueError):
                resolve_prepared_font_metrics({}, inline_metrics({codepoint: glyph(32)}))

    def test_numeric_loss_and_invalid_dimensions_are_rejected(self):
        invalid = [('advance', 1.0), ('advance', True), ('originX', float('nan')),
                   ('originY', float('inf')), ('width', -1), ('height', -1),
                   ('advance', 9007199254740993), ('originX', -9007199254740993)]
        for field, value in invalid:
            changed = inline_metrics()
            changed['glyphSets'][FONT_A][32][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                resolve_prepared_font_metrics({}, changed)
        exact = inline_metrics()
        exact['glyphSets'][FONT_A][32].update(advance=9007199254740991, originX=-9007199254740991)
        self.assertEqual(resolve_prepared_font_metrics({}, exact), exact)

    def test_missing_or_extra_glyph_metric_fields_are_rejected(self):
        for mutation in ('missing', 'extra'):
            changed = inline_metrics()
            record = changed['glyphSets'][FONT_A][32]
            if mutation == 'missing':
                record.pop('originY')
            else:
                record['unexpected'] = 0
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                resolve_prepared_font_metrics({}, changed)


if __name__ == '__main__':
    unittest.main()
