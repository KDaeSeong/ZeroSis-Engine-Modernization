"""Small contract/mutation checks; no native run, renderer or GameCore claim."""
from __future__ import annotations

import copy
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from economic_overview_timeline import (
    GENERAL_BASE, HAPPINESS_BASE, NAMES, TOP_BASE, verify_economic_overview_timeline,
)
from verify_interactive_economic_overview import native_save_paths, returned_production_target, verify_choice_capture
from verify_interactive_trade_route import VerificationError


def contract(mode='FRESH'):
    """Records follow the frozen Host's print order, not fabricated native proof."""
    children = {2: 1, 3: 1, 4: 1, 5: 1, 7: 2, 8: 2, 10: 1, 12: 1}
    keys = {stage: (TOP_BASE + 10 if stage in (1, 16) else
                   children[stage] * GENERAL_BASE + 100 + stage if stage in children else
                   27 if stage == 18 else 50 + stage) for stage in range(1, 19)}
    lines = [f'INTERACTIVE_ECONOMIC_FIXTURE={mode}|0|0|4|NO_SDK_SETUP']
    for stage, name in enumerate(NAMES, 1):
        key, generation = keys[stage], 100 + stage
        payload = 0 if stage in (2, 3) else 4 if stage in (10, 12) else 9 if stage == 13 else -1
        lines.append(f'INTERACTIVE_ECONOMIC_ACTION={stage}|{name}|{key}|{generation}|{200 + stage}|{payload}')
        if stage == 18:
            lines.extend((f'INTERACTIVE_UI_NATIVE_INPUT={generation}|0|0|1',
                          f'INTERACTIVE_UI_NATIVE_KEY={generation}|economic-overview|27|1|0'))
            continue
        lines.append(f'INTERACTIVE_SMOKE_POSTED={generation}|{key}|10|20')
        if stage in (1, 16):
            lines.extend(('INTERACTIVE_ECONOMIC_OVERVIEW_SHOWN=0|0|0|1',
                          f'INTERACTIVE_TOP_PANEL_INPUT={generation}|1|{key}|{key - TOP_BASE}|1'))
            continue
        if stage in children:
            lines.append(f'INTERACTIVE_ECONOMIC_OVERVIEW_CHILD_INPUT=2|{key}|1|1|1|{children[stage]}')
        if stage in (10, 12):
            lines.append('INTERACTIVE_ECONOMIC_PRODUCTION_OPENED=0|4|0')
        if stage in (11, 13):
            lines.append('INTERACTIVE_ECONOMIC_PRODUCTION_RETURNED=0|0')
        lines.append(f'INTERACTIVE_UI_NATIVE_INPUT={generation}|1|{key}|1')
        if stage == 13:
            lines.append(f'INTERACTIVE_ECONOMIC_PRODUCTION_VERIFIED=4|1|9|{keys[12]}|{GENERAL_BASE + 999}|1')
    lines.extend(('INTERACTIVE_ECONOMIC_COMPLETE=200|300|0|9|CANCEL_AND_DIFFERENT_PRODUCTION',
                  'INTERACTIVE_ECONOMIC_DECISION_BASELINE=4|9|1'))
    return '\n'.join(lines) + '\n'


class TimelineTests(unittest.TestCase):
    def test_fresh_and_restore(self):
        for mode in ('FRESH', 'RESTORED'):
            self.assertEqual(verify_economic_overview_timeline(contract(mode)), (True, None))

    def test_consumption_before_post_rejected_for_every_click(self):
        for stage in range(1, 18):
            with self.subTest(stage=stage):
                lines = contract().splitlines()
                post = next(i for i, value in enumerate(lines) if value.startswith(f'INTERACTIVE_SMOKE_POSTED={100 + stage}|'))
                marker = 'INTERACTIVE_TOP_PANEL_INPUT' if stage in (1, 16) else 'INTERACTIVE_UI_NATIVE_INPUT'
                consumed = next(i for i, value in enumerate(lines) if value.startswith(f'{marker}={100 + stage}|'))
                lines.insert(post, lines.pop(consumed))
                self.assertFalse(verify_economic_overview_timeline('\n'.join(lines))[0])

    def test_malformed_dispatch_records_rejected(self):
        for marker in ('INTERACTIVE_SMOKE_POSTED', 'INTERACTIVE_UI_NATIVE_INPUT',
                       'INTERACTIVE_TOP_PANEL_INPUT', 'INTERACTIVE_UI_NATIVE_KEY'):
            with self.subTest(marker=marker):
                value = contract().replace('INTERACTIVE_ECONOMIC_ACTION=3|', marker + '=MALFORMED\nINTERACTIVE_ECONOMIC_ACTION=3|')
                self.assertFalse(verify_economic_overview_timeline(value)[0])

    def test_passive_pointer_motion_remains_valid(self):
        value = contract().replace('INTERACTIVE_ECONOMIC_ACTION=3|',
                                  'INTERACTIVE_UI_NATIVE_INPUT=102|3|0|0\nINTERACTIVE_ECONOMIC_ACTION=3|')
        self.assertEqual(verify_economic_overview_timeline(value), (True, None))

    def test_extra_native_commands_rejected(self):
        for kind in (0, 1, 2, 4, 5):
            with self.subTest(kind=kind):
                value = contract().replace('INTERACTIVE_ECONOMIC_ACTION=3|',
                    f'INTERACTIVE_UI_NATIVE_INPUT=102|{kind}|0|1\nINTERACTIVE_ECONOMIC_ACTION=3|')
                self.assertFalse(verify_economic_overview_timeline(value)[0])

    def test_returned_row_wrong_namespace_rejected(self):
        for key in (GENERAL_BASE, HAPPINESS_BASE + 999, TOP_BASE + 999):
            with self.subTest(key=key):
                self.assertFalse(verify_economic_overview_timeline(contract().replace(
                    f'|{GENERAL_BASE + 999}|1\n', f'|{key}|1\n'))[0])


class CaptureTests(unittest.TestCase):
    def setUp(self):
        bounds = {'x': 10, 'y': 20, 'width': 30, 'height': 40}
        target = {'key': 63, 'id': 'Button', 'event': 'LeftClick', 'visible': True, 'disabled': False,
                  'void1': 6, 'void2': 9, 'clippedBounds': bounds}
        self.snapshot = {'contextName': 'ProductionPopup', 'popupKind': 'Production', 'active': True, 'timerSemaphore': 0,
            'inputTargets': [target], 'tree': {'key': 1, 'id': 'Root', 'children': [
                {'key': 63, 'id': 'Button', 'children': [
                    {'key': 64, 'id': 'UnitName', 'text': 'Original unit', 'children': []},
                    {'key': 65, 'id': 'ProductionButtonImage', 'texture': 'unit.dds', 'textureX': 45, 'textureY': 0, 'children': []}]}]}}
        self.manifest = {'hit_regions': [[63, 10, 20, 40, 60]]}

    def test_actual_choice_contract(self):
        verify_choice_capture(copy.deepcopy(self.snapshot), self.snapshot, self.manifest, 63, 9)

    def test_returned_production_keeps_original_right_click_without_counting_it_as_left_click(self):
        left = {'id': 'ProdButton', 'event': 'LeftClick', 'key': GENERAL_BASE + 314, 'void1': 8192,
                'visible': True, 'disabled': False}
        snapshot = {'inputTargets': [left, {**left, 'event': 'RightClick'}]}
        self.assertEqual(returned_production_target(snapshot, 8192), left)
        snapshot['inputTargets'].append(dict(left))
        with self.assertRaises(VerificationError):
            returned_production_target(snapshot, 8192)

    def test_missing_choice_content_rejected(self):
        with self.assertRaises(VerificationError):
            verify_choice_capture({}, self.snapshot, self.manifest, 63, 9)

    def test_wrong_context_payload_name_and_icon_rejected(self):
        for field in ('context', 'payload', 'name', 'icon', 'bounds'):
            with self.subTest(field=field):
                captured = copy.deepcopy(self.snapshot)
                if field == 'context': captured['popupKind'] = 'EconomicGeneral'
                elif field == 'payload': captured['inputTargets'][0]['void2'] = 10
                elif field == 'name': captured['tree']['children'][0]['children'][0]['text'] = 'Different unit'
                elif field == 'icon': captured['tree']['children'][0]['children'][1]['textureX'] = 90
                else: captured['inputTargets'][0]['clippedBounds']['x'] = 11
                with self.assertRaises(VerificationError):
                    verify_choice_capture(captured, self.snapshot, self.manifest, 63, 9)


class SaveTests(unittest.TestCase):
    def test_distinct_files_and_invalid_records(self):
        with tempfile.TemporaryDirectory(prefix='zerosis-economic-verifier-') as directory:
            paths = [(Path(directory) / f'play-save-{index}-turn-1.zssave').resolve() for index in (1, 2)]
            for path in paths: path.write_bytes(b'contract only; save bytes checked separately')
            output = ''.join(f'INTERACTIVE_NATIVE_SAVE=1|{path}\n' for path in paths)
            self.assertEqual(native_save_paths(output, set(paths), 1), paths)
            for invalid in (output.replace(str(paths[1]), str(paths[0])),
                            output.replace('INTERACTIVE_NATIVE_SAVE=1', 'INTERACTIVE_NATIVE_SAVE=2'),
                            output + 'INTERACTIVE_NATIVE_SAVE=MALFORMED\n'):
                with self.subTest(invalid=invalid), self.assertRaises(VerificationError):
                    native_save_paths(invalid, set(paths), 1)


if __name__ == '__main__':
    unittest.main()
