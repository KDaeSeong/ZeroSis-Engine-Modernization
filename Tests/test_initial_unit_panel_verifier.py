"""Adversarial boundaries for the stock selected-unit panel integration proof."""
import copy
import json
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from verify_interactive_decisions import verify_unit_panel_world_frames, verify_unit_panel_trace, verify_unit_panel_integration
from run_interactive_game import maximum_smoke_timeout


def trace_fixture(*, restored=False, found=True, build=True, fortify=True, skip=True):
    lines = ["INTERACTIVE_ORIGINAL_UNIT_PANEL_CONTRACT=1", "INTERACTIVE_GAME_STARTED=0|0|64|64",
             "INTERACTIVE_UNIT_SELECTED=0|3|2|4",
             "INTERACTIVE_INITIAL_UNIT_SELECTION=" + ("restore" if restored else "fresh") +
             "|0|0|3|3|selected|SEMANTIC_SAMPLE_UNCHANGED|RNG_UNCHANGED|SDK_SELECTION_EFFECTS_ALLOWED",
             "INTERACTIVE_WORLD_FRAME=1|1|0|3|2|10|1|0|1"]
    generation = 1
    cases = ([('found', 3, 11, 5, -1, 42, 0)] if found else []) + ([('skip', 4, 12, 6, -1, 1, 0)] if skip else [])
    if build: cases.append(('build', 6, 13, 7, 9, 200, -1))
    for kind, unit, action, mission, data, result1, result2 in cases:
        key = generation * 100
        target = f"{kind}|0|{unit}|0|{action}|{mission}|{data}|{key}|{generation}"
        lines += [f"INTERACTIVE_UNIT_SELECTED=0|{unit}|2|4",
                  "INTERACTIVE_ORIGINAL_UNIT_MISSION_TARGET=" + target,
                  f"INTERACTIVE_SMOKE_POSTED={generation}|{key}|40|550",
                  f"INTERACTIVE_ORIGINAL_UNIT_ACTION=0|{unit}|0|{action}",
                  f"INTERACTIVE_UNIT_PANEL_INPUT={generation}|1|{key}|1",
                  f"INTERACTIVE_WORLD_FRAME={generation+1}|{generation+1}|0|3|2|10|1|0|1",
                  f"INTERACTIVE_ORIGINAL_UNIT_MISSION_OBSERVED={target}|{generation+1}|{result1}|{result2}"]
        generation += 2
    if fortify:
        lines += ["INTERACTIVE_ORIGINAL_UNIT_ACTION_TARGET=7|17|700", "INTERACTIVE_ORIGINAL_UNIT_ACTION=0|7|0|17"]
    return '\n'.join(lines) + '\n'


def verify_trace(text, **overrides):
    options = dict(required=True, restored=False, unit_actions=True, worker_build=True, expected_found=True)
    options.update(overrides)
    return verify_unit_panel_trace(text, **options)


class UnitPanelTrace(unittest.TestCase):
    def test_fresh_and_restore_exact_command_partition(self):
        proof = verify_trace(trace_fixture())
        self.assertEqual([row['kind'] for row in proof['missions']], ['found', 'skip', 'build'])
        self.assertEqual(proof['original_command_count'], 4)
        self.assertFalse(proof['initial']['full_save_bytes_unchanged_claimed'])
        proof = verify_trace(trace_fixture(restored=True, found=False), restored=True, expected_found=False)
        self.assertEqual([row['kind'] for row in proof['missions']], ['skip', 'build'])

    def test_legacy_is_distinct_from_versioned_host(self):
        self.assertIsNone(verify_trace('INTERACTIVE_ORIGINAL_UNIT_ACTION=0|7|0|17\n', required=False))
        for text, options in [(trace_fixture(), {'required': False}),
                              (trace_fixture().replace('INTERACTIVE_ORIGINAL_UNIT_PANEL_CONTRACT=1\n', ''), {}),
                              (trace_fixture().replace('CONTRACT=1', 'CONTRACT=2'), {})]:
            with self.subTest(options=options), self.assertRaises(RuntimeError): verify_trace(text, **options)

    def test_reject_extra_duplicate_missing_or_malformed_command(self):
        original = trace_fixture()
        cases = [original + 'INTERACTIVE_ORIGINAL_UNIT_ACTION=0|99|0|17\n',
                 original + 'INTERACTIVE_ORIGINAL_UNIT_ACTION=0|3|0|11\n',
                 original.replace('INTERACTIVE_ORIGINAL_UNIT_ACTION=0|3|0|11\n', ''),
                 original + 'INTERACTIVE_ORIGINAL_UNIT_ACTION=not-a-record\n',
                 original + 'INTERACTIVE_ORIGINAL_UNIT_MISSION_TARGET=skip|broken\n',
                 original + 'INTERACTIVE_UNIT_ACTION=0|6|7|9|-1\n']
        for text in cases:
            with self.subTest(text=text[-90:]), self.assertRaises(RuntimeError): verify_trace(text)

    def test_reject_missing_wrong_or_duplicate_actual_input(self):
        original = trace_fixture()
        record = 'INTERACTIVE_UNIT_PANEL_INPUT=1|1|100|1\n'
        for replacement in ('', record + record, record.replace('=1|', '=2|'), record.replace('|1\n', '|0\n')):
            with self.subTest(replacement=replacement), self.assertRaises(RuntimeError):
                verify_trace(original.replace(record, replacement))

    def test_reject_stale_generation_wrong_result_and_out_of_order_post(self):
        original = trace_fixture()
        cases = [original.replace('found|0|3|0|11|5|-1|100|1|2|42|0', 'found|0|3|0|11|5|-1|100|1|1|42|0'),
                 original.replace('skip|0|4|0|12|6|-1|300|3|4|1|0', 'skip|0|4|0|12|6|-1|300|3|4|2|0'),
                 original.replace('found|0|3|0|11|5|-1|100|1|2|42|0', 'found|0|3|0|11|5|-1|100|1|2|42|1'),
                 original.replace('INTERACTIVE_SMOKE_POSTED=1|100|40|550\nINTERACTIVE_ORIGINAL_UNIT_ACTION=0|3|0|11',
                                  'INTERACTIVE_ORIGINAL_UNIT_ACTION=0|3|0|11\nINTERACTIVE_SMOKE_POSTED=1|100|40|550')]
        for text in cases:
            with self.subTest(text=text[-90:]), self.assertRaises(RuntimeError): verify_trace(text)

    def test_reject_initial_selection_scope_and_semantic_claim_changes(self):
        original = trace_fixture()
        cases = [original.replace('=fresh|', '=restore|'),
                 original.replace('fresh|0|0|3|3|selected', 'fresh|0|0|3|0|selected'),
                 original.replace('SDK_SELECTION_EFFECTS_ALLOWED', 'SAVE_UNCHANGED'),
                 original.replace('INTERACTIVE_UNIT_SELECTED=0|3|2|4\n', '', 1),
                 original.replace('INTERACTIVE_UNIT_SELECTED=0|4|2|4', 'INTERACTIVE_UNIT_SELECTED=0|99|2|4')]
        for text in cases:
            with self.subTest(text=text[:200]), self.assertRaises(RuntimeError): verify_trace(text)

    def test_existing_does_not_falsely_claim_ready(self):
        text = trace_fixture().replace('INTERACTIVE_UNIT_SELECTED=0|3|2|4\n', '', 1)
        text = text.replace('fresh|0|0|3|3|selected', 'fresh|0|0|3|0|existing')
        self.assertEqual(verify_trace(text)['initial']['mode'], 'existing')

    def test_none_ready_has_no_invented_initial_sdk_selection(self):
        text = trace_fixture().replace('INTERACTIVE_UNIT_SELECTED=0|3|2|4\n', '', 1)
        text = text.replace('fresh|0|0|3|3|selected', 'fresh|0|0|-1|0|none-ready')
        self.assertEqual(verify_trace(text)['initial']['unit'], -1)


class UnitPanelTimeout(unittest.TestCase):
    def test_only_exact_combined_profile_gets_900_seconds(self):
        profile = dict.fromkeys(('smoke', 'decisions', 'research_tree', 'unit_actions', 'worker_build',
                                 'top_panel', 'action_info_panel', 'notification_panel'), True)
        self.assertEqual(maximum_smoke_timeout(SimpleNamespace(**profile)), 900)
        for omitted in profile:
            changed = dict(profile, **{omitted: False})
            with self.subTest(omitted=omitted):
                self.assertEqual(maximum_smoke_timeout(SimpleNamespace(**changed)), 300)
        self.assertEqual(maximum_smoke_timeout(SimpleNamespace()), 300)
        self.assertEqual(maximum_smoke_timeout(SimpleNamespace(game_menu=True)), 900)


class UnitPanelArtifacts(unittest.TestCase):
    def setUp(self):
        test_root = Path(__file__).resolve().parent
        self.tmp = tempfile.TemporaryDirectory(prefix='zerosis-unit-panel-contract-', dir=test_root)
        self.runtime = Path(self.tmp.name).resolve(strict=True)
        self.assertEqual(self.runtime.parent, test_root)
        self.addCleanup(self.tmp.cleanup)
        self.session = self.runtime / 'sessions' / 'contract-fixture'
        self.session.mkdir(parents=True)
        semantic = 'G|0|0|0|0\n' + ''.join(f'P|{i}|1|1|1|0|0|3|0|0|-1\n' for i in range(64))
        semantic += 'U|0|3|0|2|4|120|0|0|1|0|0|\n'
        for name in ('play-initial-state.txt', 'play-initial-selection-before-state.txt', 'play-initial-selection-after-state.txt'):
            (self.session / name).write_text(semantic, encoding='utf-8')
        scenes, self.panels = panel_frames()
        self.panels[0]['hit_regions'][-1][0] = 100
        self.panels[0]['targets'] = [{'key': 100, 'event': 'LeftClick', 'id': 'BuildCityButton',
                                     'void1': 11, 'visible': True, 'disabled': False}]
        self.world = scenes[1][0]
        self.world.update(activePlayer=0, cities=[])
        self.world['units'][0].update(x=2, y=4)
        self.world['hits'][-1][0] = 100
        self.after = {'generation': 2, 'turn': 0, 'activePlayer': 0, 'originalUnitPanel': False,
                      'units': [], 'cities': [{'id': 42, 'owner': 0, 'x': 2, 'y': 4}], 'hits': []}
        self.driver = {'status': 'INTERACTIVE_UI_DRIVER_PASS', 'returncode': 0, 'error': None}
        self.output = trace_fixture(build=False, fortify=False, skip=False)
        first = 'INTERACTIVE_WORLD_FRAME=1|1|0|3|2|10|1|0|1'
        source = str(self.session / 'panel.json')
        folder = str(self.session / 'panel')
        self.output = self.output.replace(first, f'INTERACTIVE_UI_SCENE_REQUEST=1|unit-panel|{source}|{folder}\n'
            f'INTERACTIVE_UI_FRAME=1|1|0|unit-panel|1|10|{source}|{folder}\n' + first)

    def verify(self, *, restored=False, reference=None):
        for index, world in enumerate((self.world, self.after), 1):
            (self.session / f'play-scene-{index}.json').write_text(json.dumps(world), encoding='utf-8')
        frames = [[1, 1, 0, 1, len(self.world['hits']), 10, 1, 0, 1], [2, 2, 0, 0, len(self.after['hits']), 10, 2, 0, 1]]
        # Existing packet/source verification is its own contract. Here feed its
        # accepted output to exercise the added initial-state/frame/mission joins.
        with patch('verify_interactive_decisions.ui_snapshots', return_value=self.panels):
            return verify_unit_panel_integration(self.output, self.runtime, self.driver, frames,
                required=True, restored=restored, unit_actions=False, worker_build=False, decisions=True,
                expected_restore_state=reference)

    def test_initial_sample_and_actual_found_join(self):
        proof = self.verify()
        self.assertTrue(proof['same_original_callback_and_committed_hit_verified'])
        self.assertFalse(proof['full_sdk_or_save_bytes_preserved'])

    def test_reject_changed_initial_or_postselection_sample(self):
        for name in ('play-initial-state.txt', 'play-initial-selection-after-state.txt'):
            path = self.session / name
            data = path.read_bytes()
            path.write_bytes(data + b'changed\n')
            with self.subTest(name=name), self.assertRaises(RuntimeError): self.verify()
            path.write_bytes(data)

    def test_reject_wrong_source_restore_semantic_baseline(self):
        self.output = self.output.replace('=fresh|', '=restore|')
        reference = self.session / 'source-final.txt'
        reference.write_bytes((self.session / 'play-initial-state.txt').read_bytes())
        self.assertIsNotNone(self.verify(restored=True, reference=reference)['source_restore_semantic_reference'])
        reference.write_bytes(b'wrong-source')
        with self.assertRaises(RuntimeError): self.verify(restored=True, reference=reference)

    def test_reject_wrong_initial_unit_or_forged_found_outcome(self):
        original = copy.deepcopy(self.world)
        self.world['units'][0]['id'] = 9
        with self.assertRaises(RuntimeError): self.verify()
        self.world = original
        self.after['units'] = copy.deepcopy(self.world['units'])
        with self.assertRaises(RuntimeError): self.verify()
        self.after['units'] = []
        self.after['cities'][0]['x'] += 1
        with self.assertRaises(RuntimeError): self.verify()

    def test_reject_invented_found_callback_or_obscured_hwnd(self):
        self.panels[0]['targets'][0]['id'] = 'UnitActionButton'
        with self.assertRaises(RuntimeError): self.verify()
        self.panels[0]['targets'][0]['id'] = 'BuildCityButton'
        self.world['hits'].append([999, 20, 820, 70, 870])
        with self.assertRaises(RuntimeError): self.verify()


def panel_frames():
    panel = {"context": "unit-panel", "generation": 1, "turn": 0,
             "snapshot_active": True, "timer_semaphore": 0,
             "hit_regions": [[71, 0, 800, 200, 1000], [72, 20, 820, 70, 870]]}
    world = {"generation": 1, "turn": 0, "originalUnitPanel": True,
             "units": [{"id": 3, "owner": 0, "selected": True}],
             "hits": [[0x5A57000300000001, 1000, 0, 1100, 40]] + copy.deepcopy(panel["hit_regions"])}
    return {1: (world, None)}, [panel]


class UnitPanelFrames(unittest.TestCase):
    def test_original_packet_and_non_unit_world_controls_remain(self):
        scenes, panels = panel_frames()
        proof = verify_unit_panel_world_frames(scenes, panels)
        self.assertEqual(len(proof["active_frames"]), 1)
        self.assertTrue(proof["fallback_found_skip_and_action_hits_absent"])

    def test_reject_every_fallback_unit_control(self):
        keys = [0x5A57000300000000 | value for value in (2, 3, 13, 14)] + [0x5A57000500000011]
        for key in keys:
            scenes, panels = panel_frames()
            scenes[1][0]["hits"].append([key, 1100, 0, 1200, 40])
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                verify_unit_panel_world_frames(scenes, panels)

    def test_reject_forged_overlay_metadata(self):
        for value in (False, None, 1, "true"):
            scenes, panels = panel_frames()
            scenes[1][0]["originalUnitPanel"] = value
            with self.subTest(value=value), self.assertRaises(RuntimeError):
                verify_unit_panel_world_frames(scenes, panels)
        scenes, panels = panel_frames()
        panels[0]["generation"] = 2
        with self.assertRaises(RuntimeError):
            verify_unit_panel_world_frames(scenes, panels)

    def test_reject_missing_obscured_or_changed_packet(self):
        for change in ("missing", "duplicate", "bounds", "order"):
            scenes, panels = panel_frames()
            hits = scenes[1][0]["hits"]
            if change == "missing": hits.pop()
            if change == "duplicate": hits.append(copy.deepcopy(hits[-1]))
            if change == "bounds": hits[-1][1] += 1
            if change == "order": hits[-2:] = reversed(hits[-2:])
            with self.subTest(change=change), self.assertRaises(RuntimeError):
                verify_unit_panel_world_frames(scenes, panels)

    def test_reject_missing_selection_or_modal_timer(self):
        scenes, panels = panel_frames()
        scenes[1][0]["units"][0]["selected"] = False
        with self.assertRaises(RuntimeError):
            verify_unit_panel_world_frames(scenes, panels)
        scenes, panels = panel_frames()
        panels[0]["timer_semaphore"] = 1
        with self.assertRaises(RuntimeError):
            verify_unit_panel_world_frames(scenes, panels)

    def test_fallback_remains_permitted_without_original_panel(self):
        scenes, panels = panel_frames()
        scenes[2] = ({"generation": 2, "turn": 0, "originalUnitPanel": False,
                      "units": [], "hits": [[0x5A57000300000003, 0, 0, 20, 20]]}, None)
        self.assertEqual(len(verify_unit_panel_world_frames(scenes, panels)["active_frames"]), 1)


if __name__ == "__main__":
    unittest.main()
