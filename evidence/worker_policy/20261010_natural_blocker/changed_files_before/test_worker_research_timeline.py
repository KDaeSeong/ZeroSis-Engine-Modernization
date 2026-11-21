"""Synthetic contract mutations only; these tests do not claim native gameplay."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from action_info_panel_timeline import KEY_BASE, verify_action_info_panel_timeline
from probe_world_builder import artifact
from verify_interactive_decisions import (verify_worker_research_integration,
                                           worker_research_contract_required,
                                           research_callback_source_pair, research_callback_targets)
from worker_research_timeline import (CAPABILITY, REQUEST_FLAGS, VERIFIER_FILES,
                                      exact_worker_research_profile, verify_worker_research_timeline)


def fixture(*, restored=False, complete=True, saturated=True, final_completion=False):
    """Three exact worker turns, optionally one natural award and a new choice."""
    t0 = 6 if restored else 0
    lines = [CAPABILITY, f'INTERACTIVE_GAME_STARTED={t0}|0|40|24']
    key = KEY_BASE + 2

    def hud(generation, turn):
        lines.append(f'INTERACTIVE_ACTION_INFO_PANEL_FRAME={generation}|{generation}|{turn}|0|100|101|snapshot|folder')

    def world(generation, turn, panel=True):
        lines.extend([f'INTERACTIVE_GPU_SCENE_COMMITTED={generation}|101',
                      f'INTERACTIVE_WORLD_FRAME={generation}|{generation}|{turn}|3|26|101|54|0|1'])
        if panel:
            hud(generation, turn)

    def target(phase, generation, turn, blocker=-1, notification=-1):
        lines.append(f'INTERACTIVE_ACTION_INFO_SMOKE_TARGET={phase}|{blocker}|{notification}|{key}|{generation}|{turn}')

    def post(generation, chosen, turn, context, before, after, marker, technology):
        world(generation, turn, False)
        lines.extend([f'INTERACTIVE_UI_SCENE_REQUEST={generation}|{context}|snapshot-{generation}|folder-{generation}',
                      f'INTERACTIVE_UI_FRAME={generation}|{generation}|{turn}|{context}|100|101|snapshot-{generation}|folder-{generation}',
                      marker, f'INTERACTIVE_SMOKE_BUTTON={generation}|{chosen}|1|0',
                      f'INTERACTIVE_SMOKE_POSTED={generation}|{chosen}|100|100',
                      f'UI_WINDOW_INPUT=1|2|{chosen}|1|44|44|{before}|{after}|{turn}|99'])
        if context == 'tech-award':
            lines.append(f'INTERACTIVE_TECH_AWARD_CLOSED={chosen}|{turn}|0|STATE_UNCHANGED')
        lines.append(f'INTERACTIVE_UI_NATIVE_INPUT={generation}|1|{chosen}|1')

    phases = [('unit-right', 3, -1), ('unit-left', 3, -1)]
    if not restored:
        phases += [('notification', 2, 7), ('research', 1, 8)]
    for index, (phase, blocker, notice) in enumerate(phases):
        generation, kind = 1 + index * 4, 5 if phase == 'unit-right' else 1
        hud(generation, t0); target(phase, generation, t0, blocker, notice)
        lines.extend([f'INTERACTIVE_SMOKE_BUTTON={generation}|{key}|{kind}|0',
                      f'INTERACTIVE_SMOKE_POSTED={generation}|{key}|1000|650',
                      f'INTERACTIVE_ACTION_INFO_PANEL_INPUT={generation}|{kind}|{key}|2|1|0'])
        if phase == 'notification':
            lines.append(f'INTERACTIVE_ACTION_INFO_NOTIFICATION_OPENED=production|{generation+1}|{t0}')
        if phase in ('unit-right', 'unit-left', 'notification'):
            lines.append(f'INTERACTIVE_ACTION_INFO_SMOKE_VERIFIED={phase}|{generation+2}|{t0}')
    progress = 36 if saturated else 0
    left = 0 if saturated else 35
    post(20, 700, t0, 'research-tree', 1, 1, 'INTERACTIVE_DECISION_RESEARCH_TARGET=2|700', 2)
    lines.append('INTERACTIVE_UI_NATIVE_KEY=21|research-tree|27|1|0')
    world(22, t0)
    lines.extend([f'INTERACTIVE_DECISION_BEFORE_TURN={t0},{t0},0,8192,0,2,1,0,106,{progress},{left},3',
                  f'INTERACTIVE_WORKER_RESEARCH_SELECTED={t0}|0|2|22|2|0|{progress}|{left}',
                  'INTERACTIVE_WORKER_BUILD_FIXTURE=32770|571|2|0|400|3',
                  'INTERACTIVE_WORKER_BUILD_TARGET=32770|571|2|33|12|23',
                  'INTERACTIVE_WORKER_BUILD_STARTED=32770|571|2|200|-1'])
    tech = 2
    for index, (before, returned) in enumerate(((24, 27), (32, 34), (36, 39))):
        turn = t0 + index
        hud(before, turn); target('end-turn', before, turn)
        lines.extend([f'INTERACTIVE_WORKER_RESEARCH_BEFORE_TURN={turn}|0|{tech}|{before}|0|{progress}|{left}',
                      f'INTERACTIVE_SMOKE_BUTTON={before}|{key}|1|0',
                      f'INTERACTIVE_SMOKE_POSTED={before}|{key}|1000|650',
                      f'INTERACTIVE_END_TURN_ACCEPTED={turn}',
                      f'INTERACTIVE_ACTION_INFO_PANEL_INPUT={before}|1|{key}|2|1|0'])
        completes = complete and index == (2 if final_completion else 0)
        if completes:
            lines.append(f'INTERACTIVE_UI_QUEUED=68|0|0|{tech}')
        lines.append(f'INTERACTIVE_NEXT_HUMAN_TURN={turn+1}|7')
        if completes:
            lines.append(f'INTERACTIVE_TECH_AWARD_SHOWN=0|0|{tech}|{turn+1}|1')
            post(returned - 1, 600, turn + 1, 'tech-award', 1, 0,
                 f'INTERACTIVE_WORKER_TECH_AWARD_TARGET={turn+1}|0|{tech}|600|{returned-1}|1', tech)
            left = 0
        else:
            progress += 6; left = max(0, left - 6)
        world(returned, turn + 1)
        if completes:
            lines.append(f'INTERACTIVE_WORKER_TECH_AWARD_RETURNED={turn+1}|0|{tech}|{returned}|-1|1|0')
        lines.append(f'INTERACTIVE_WORKER_RESEARCH_TURN_RETURNED={turn+1}|0|{tech}|{returned}|{-1 if completes else tech}|{int(completes)}|{progress}|{left}')
        if index == 0:
            lines.append(f'INTERACTIVE_DECISION_AFTER_TURN={turn+1},{turn+1},0,8192,0,2,1,9,106,{progress},{left},3')
        amount, improvement, mission, mission_build = (0, 3, -1, -1) if index == 2 else (200 + index * 100, -1, 33, 2)
        lines.append(f'INTERACTIVE_WORKER_BUILD_OBSERVED={turn+1}|32770|571|2|{amount}|{improvement}|120|{mission}|{mission_build}')
        if index == 0:
            lines.append(f'INTERACTIVE_WORKER_BUILD_AWAITING_TURN={turn+1}|32770|571|2|200|120|33|2')
        lines.append(f'INTERACTIVE_WORKER_BUILD_PROGRESS={turn+1}|32770|571|2|{amount}|{improvement}')
        if completes and index < 2:
            hud(28, turn + 1); target('research-continuation', 28, turn + 1, 1, 9)
            lines.extend([f'INTERACTIVE_SMOKE_BUTTON=28|{key}|1|0',
                          f'INTERACTIVE_SMOKE_POSTED=28|{key}|1000|650',
                          f'INTERACTIVE_ACTION_INFO_PANEL_INPUT=28|1|{key}|2|1|0'])
            tech, progress, left = 3, 0, 20
            post(29, 800, turn + 1, 'research', 0, 0,
                 f'INTERACTIVE_WORKER_RESEARCH_TARGET={turn+1}|0|3|800|29', tech)
            world(30, turn + 1)
            lines.append(f'INTERACTIVE_WORKER_RESEARCH_SELECTED={turn+1}|0|3|30|3|0|0|20')
    lines.extend([f'INTERACTIVE_WORKER_BUILD_COMPLETED=32770|571|2|3|{t0+3}',
                  'INTERACTIVE_ACTION_INFO_PANEL_SMOKE_COMPLETE=1'])
    return '\n'.join(lines) + '\n'


class Timeline(unittest.TestCase):
    def reject(self, text):
        with self.assertRaises(RuntimeError):
            verify_worker_research_timeline(text, required=True)

    def test_completed_equal_progress_and_zero_left(self):
        for restored in (False, True):
            text = fixture(restored=restored)
            proof = verify_worker_research_timeline(text, required=True)
            self.assertEqual(len(proof['awards']), 1)
            self.assertEqual(len(proof['continuations']), 1)
            self.assertEqual(verify_action_info_panel_timeline(text, restored, True, True), (True, None))

    def test_incomplete_zero_left_and_strict_progress(self):
        for saturated in (False, True):
            text = fixture(complete=False, saturated=saturated)
            self.assertEqual(verify_worker_research_timeline(text, required=True)['awards'], [])
            self.assertEqual(verify_action_info_panel_timeline(text, False, True, True), (True, None))
        text = fixture(complete=False)
        self.reject(text.replace('27|2|0|42|0', '27|2|0|36|0'))
        self.reject(text.replace('27|2|0|42|0', '27|2|0|42|1'))

    def test_final_turn_completion_needs_no_additional_choice(self):
        text = fixture(final_completion=True)
        proof = verify_worker_research_timeline(text, required=True)
        self.assertEqual(len(proof['awards']), 1)
        self.assertEqual(proof['continuations'], [])
        self.assertEqual(verify_action_info_panel_timeline(text, False, True, True), (True, None))

    def test_explicit_scope_and_version(self):
        self.assertIsNone(verify_worker_research_timeline('', required=False))
        for required in (False, 1, None, 'true'):
            with self.subTest(required=required), self.assertRaises(RuntimeError):
                verify_worker_research_timeline(fixture(), required=required)
        self.reject(fixture().replace(CAPABILITY, CAPABILITY[:-1] + '2'))
        self.assertFalse(verify_action_info_panel_timeline(fixture(), False, True)[0])
        for flag in REQUEST_FLAGS:
            request = dict.fromkeys(REQUEST_FLAGS, True); request[flag] = 1
            self.assertFalse(exact_worker_research_profile(request))

    def test_missing_duplicate_malformed_and_unknown_records(self):
        text = fixture()
        for name in ('WORKER_RESEARCH_CONTRACT', 'WORKER_RESEARCH_SELECTED', 'WORKER_RESEARCH_BEFORE_TURN',
                     'WORKER_RESEARCH_TURN_RETURNED', 'WORKER_TECH_AWARD_TARGET', 'WORKER_TECH_AWARD_RETURNED',
                     'WORKER_RESEARCH_TARGET', 'DECISION_RESEARCH_TARGET', 'DECISION_BEFORE_TURN',
                     'DECISION_AFTER_TURN', 'TECH_AWARD_SHOWN', 'TECH_AWARD_CLOSED', 'UI_QUEUED'):
            line = next(line for line in text.splitlines() if line.startswith('INTERACTIVE_' + name + '='))
            for replacement in ('', line + '\n' + line, line + '|invalid'):
                with self.subTest(name=name, replacement=replacement):
                    self.reject(text.replace(line, replacement, 1))
        self.reject(text + 'INTERACTIVE_WORKER_RESEARCH_BYPASS=1\n')
        self.reject(text + 'INTERACTIVE_RESEARCH_COMPLETION_FIXTURE=2|0|1\n')
        self.reject(text + 'INTERACTIVE_UI_QUEUED=68|bad\n')

    def test_identity_progress_remaining_and_callback_mutations(self):
        text = fixture()
        mutations = (
            ('BEFORE_TURN=0|0|2|24|0|36|0', 'BEFORE_TURN=0|1|2|24|0|36|0'),
            ('BEFORE_TURN=0|0|2|24|0|36|0', 'BEFORE_TURN=0|0|2|24|1|36|0'),
            ('TURN_RETURNED=1|0|2|27|-1|1|36|0', 'TURN_RETURNED=1|0|2|27|-1|1|35|0'),
            ('TURN_RETURNED=1|0|2|27|-1|1|36|0', 'TURN_RETURNED=1|0|3|27|-1|1|36|0'),
            ('TURN_RETURNED=1|0|2|27|-1|1|36|0', 'TURN_RETURNED=1|0|2|27|2|1|36|0'),
            ('AWARD_TARGET=1|0|2|600|26|1', 'AWARD_TARGET=2|0|2|600|26|1'),
            ('AWARD_TARGET=1|0|2|600|26|1', 'AWARD_TARGET=1|0|2|600|25|1'),
            ('RESEARCH_TARGET=1|0|3|800|29', 'RESEARCH_TARGET=1|0|2|800|29'),
            ('SMOKE_POSTED=26|600|100|100', 'SMOKE_POSTED=26|601|100|100'),
            ('UI_NATIVE_INPUT=26|1|600|1', 'UI_NATIVE_INPUT=26|1|600|0'),
            ('UI_NATIVE_INPUT=26|1|600|1', 'UI_NATIVE_INPUT=26|1|601|1'),
            ('UI_WINDOW_INPUT=1|2|600|1|44|44|1|0|1|99', 'UI_WINDOW_INPUT=1|2|600|1|44|45|1|0|1|99'),
            ('UI_WINDOW_INPUT=1|2|600|1|44|44|1|0|1|99', 'UI_WINDOW_INPUT=1|2|600|1|44|44|1|1|1|99'),
            ('DECISION_AFTER_TURN=1,1,0,8192,0,2,1,9,106,36,0,3', 'DECISION_AFTER_TURN=1,1,0,8192,0,2,1,0,106,36,0,3'),
            ('GPU_SCENE_COMMITTED=27|101', 'GPU_SCENE_COMMITTED=27|102'),
            ('PANEL_FRAME=27|27|1|0|100|101', 'PANEL_FRAME=27|27|1|1|100|101'),
        )
        for before, after in mutations:
            with self.subTest(before=before):
                self.assertIn(before, text)
                self.reject(text.replace(before, after, 1))

    def test_missing_choice_cannot_reuse_owned_technology(self):
        text = fixture()
        first = text.index('INTERACTIVE_ACTION_INFO_PANEL_FRAME=28|')
        last = text.index('INTERACTIVE_ACTION_INFO_PANEL_FRAME=32|')
        text = text[:first] + text[last:]
        text = text.replace('BEFORE_TURN=1|0|3|32|0|0|20', 'BEFORE_TURN=1|0|2|32|0|36|0')
        self.reject(text)

    def test_popup_return_and_worker_observation_order(self):
        text = fixture()
        a = 'INTERACTIVE_WORKER_TECH_AWARD_RETURNED=1|0|2|27|-1|1|0'
        b = 'INTERACTIVE_WORKER_RESEARCH_TURN_RETURNED=1|0|2|27|-1|1|36|0'
        self.reject(text.replace(a + '\n' + b, b + '\n' + a))
        self.reject(text.replace('INTERACTIVE_TECH_AWARD_CLOSED=600|1|0|STATE_UNCHANGED\n', ''))
        self.reject(text.replace('INTERACTIVE_UI_NATIVE_KEY=21|research-tree|27|1|0', ''))


class FrozenOriginalCallbackSources(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).parent / 'fixtures/worker_research_callbacks'
        cls.metadata = json.loads((root / 'provenance.json').read_text(encoding='utf8'))
        cls.sources = {}
        for row in cls.metadata['files']:
            raw = (root / row['name']).read_bytes()
            if len(raw) != row['bytes'] or hashlib.sha256(raw).hexdigest() != row['sha256']:
                raise RuntimeError('Frozen original callback fixture differs from its captured manifest')
            cls.sources[row['name']] = raw.decode('utf-8-sig')

    def verify(self, kind='tree', context=None, included=None, requested=None, delivered=None):
        item = self.metadata[kind]
        return research_callback_source_pair(
            requested if requested is not None else item['requested'],
            delivered if delivered is not None else item['delivered'], item['technology'],
            context if context is not None else self.sources['TechTree.lua' if kind == 'tree' else 'TechPopup.lua'],
            included if included is not None else self.sources['TechButtonInclude.lua'], research_tree=kind == 'tree')

    def test_real_tree_b2_and_popup_b1_callback_pairs(self):
        self.assertEqual(self.metadata['tree']['delivered']['id'], 'B2')
        self.assertEqual(self.metadata['tree']['technology'], 2)
        self.verify('tree'); self.verify('popup')

    def test_context_without_shared_include_reproduces_original_failure(self):
        item = self.metadata['tree']
        with self.assertRaisesRegex(RuntimeError, 'does not bind'):
            research_callback_targets(item['requested'], item['delivered'], item['technology'],
                                      self.sources['TechTree.lua'], research_tree=True)

    def test_missing_wrong_or_duplicate_include_is_rejected(self):
        for kind, name in [('tree', 'TechTree.lua'), ('popup', 'TechPopup.lua')]:
            body = self.sources[name]
            self.assertIn('include( "TechButtonInclude" );', body)
            for replacement in ('', 'include( "OtherInclude" );',
                                'include( "TechButtonInclude" );\ninclude( "TechButtonInclude" );'):
                with self.subTest(kind=kind, replacement=replacement), self.assertRaises(RuntimeError):
                    self.verify(kind, context=body.replace('include( "TechButtonInclude" );', replacement))

    def test_wrong_context_callback_is_rejected(self):
        for kind, name in [('tree', 'TechTree.lua'), ('popup', 'TechPopup.lua')]:
            body = self.sources[name].replace('Mouse.eLClick, TechSelected', 'Mouse.eLClick, OtherSelected')
            with self.subTest(kind=kind), self.assertRaises(RuntimeError):
                self.verify(kind, context=body)

    def test_wrong_included_argument_or_callback_binding_is_rejected(self):
        body = self.sources['TechButtonInclude.lua']
        for before, after in (
            ('SetVoids(void1, void2)', 'SetVoids(void2, void1)'),
            ('RegisterCallback(thisEvent, thisCallback)', 'RegisterCallback(thisEvent, OtherCallback)'),
            ('function AddCallbackToSmallButtons(', 'function DifferentCallbackToSmallButtons('),
            ('local buttonName = "B"..tostring(buttonNum);', 'local buttonName = "Other"..tostring(buttonNum);'),
        ):
            self.assertIn(before, body)
            with self.subTest(before=before), self.assertRaises(RuntimeError):
                self.verify(included=body.replace(before, after))

    def test_wrong_delivered_technology_or_alias_bound_is_rejected(self):
        for change in ({'void1': 3}, {'void2': 1}, {'id': 'B6'}):
            delivered = {**self.metadata['tree']['delivered'], **change}
            with self.subTest(change=change), self.assertRaises(RuntimeError):
                self.verify(delivered=delivered)


class FrozenCapability(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.loop = self.root / 'InteractiveGameLoop.h'; self.loop.write_text(CAPABILITY)
        self.build = self.root / 'build.json'
        self.build.write_text(json.dumps({'sources': [artifact(self.loop)]}))
        runner = self.root / 'run_interactive_game.py'; runner.write_text('# frozen runner\n')
        inventory = {}
        for name in VERIFIER_FILES:
            path = self.root / name; path.write_text('# frozen verifier\n'); inventory[name] = artifact(path)
        self.request = {**dict.fromkeys(REQUEST_FLAGS, True), 'worker_research_contract': 1,
                        'provenance': {'host_build': artifact(self.build), 'frozen_runner': artifact(runner),
                                       'worker_research_verifiers': inventory}}

    def test_exact_capability(self):
        self.assertTrue(worker_research_contract_required(self.request))

    def test_missing_false_or_mutated_contract_rejected(self):
        for value in (None, False, True, 0, 2, '1'):
            request = copy.deepcopy(self.request)
            if value is None:
                del request['worker_research_contract']
            else:
                request['worker_research_contract'] = value
            with self.subTest(value=value), self.assertRaises(RuntimeError):
                worker_research_contract_required(request)

    def test_missing_or_changed_frozen_module_rejected(self):
        request = copy.deepcopy(self.request)
        del request['provenance']['worker_research_verifiers'][VERIFIER_FILES[0]]
        with self.assertRaises(RuntimeError):
            worker_research_contract_required(request)
        (self.root / VERIFIER_FILES[0]).write_text('# changed\n')
        with self.assertRaises(RuntimeError):
            worker_research_contract_required(self.request)

    def test_out_of_scope_or_legacy_capability(self):
        for key in ('tech_award', 'combat_smoke', 'game_menu_smoke'):
            request = copy.deepcopy(self.request); request[key] = True
            with self.assertRaises(RuntimeError):
                worker_research_contract_required(request)
            del request['worker_research_contract']
            self.assertFalse(worker_research_contract_required(request))
        self.loop.write_text('// previous native contract\n')
        self.build.write_text(json.dumps({'sources': [artifact(self.loop)]}))
        self.request['provenance']['host_build'] = artifact(self.build)
        del self.request['worker_research_contract']
        self.assertFalse(worker_research_contract_required(self.request))


class PacketIntegration(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.session = self.root / 'sessions' / 'synthetic'; self.session.mkdir(parents=True)
        self.text = fixture()
        self.driver = {'status': 'INTERACTIVE_UI_DRIVER_PASS', 'returncode': 0, 'error': None, 'scene_requests': []}
        self.frames = [list(map(int, row.split('|'))) for row in re.findall(r'^INTERACTIVE_WORLD_FRAME=(.+)$', self.text, re.M)]
        self.events = verify_worker_research_timeline(self.text, required=True)['callback_inputs']
        self.paths = []
        for event in self.events:
            sequence, generation, context = event['sequence'], event['generation'], event['context']
            snapshot = self.session / f'play-ui-{sequence}.json'
            folder = self.session / f'play-ui-{sequence}'; (folder / 'source_ui').mkdir(parents=True)
            popup = {'research-tree': ('TechTree', 'ResearchTree', 1), 'research': ('TechPopup', 'Research', 0),
                     'tech-award': ('TechAwardPopup', 'TechAward', 1)}[context]
            target = {'key': event['key'], 'id': 'ContinueButton' if context == 'tech-award' else 'TechButton',
                      'event': 'LeftClick', 'visible': True, 'disabled': False, 'void1': event['technology'], 'void2': 0}
            document = {'contextName': popup[0], 'popupKind': popup[1], 'timerSemaphore': popup[2],
                        'active': True, 'inputTargets': [target]}
            snapshot.write_text(json.dumps(document))
            packet = folder / 'scene.packet'; packet.write_bytes(b'ZSUPIX02')
            body = ('Controls.ContinueButton:RegisterCallback( Mouse.eLClick, OnContinueButtonClicked );\n'
                    'UIManager:DequeuePopup( ContextPtr );' if context == 'tech-award' else
                    'include( "TechButtonInclude" );\n'
                    'thisTechButtonInstance.TechButton:RegisterCallback( Mouse.eLClick, TechSelected );')
            source = folder / 'source_ui' / (popup[0] + '.lua'); source.write_text(body)
            original_sources = [artifact(source)]
            if context != 'tech-award':
                included = folder / 'source_ui' / 'TechButtonInclude.lua'
                included.write_text('function AddCallbackToSmallButtons( thisTechButtonInstance, maxSmallButtons, void1, void2, thisEvent, thisCallback )\n'
                                    'local buttonName = "B"..tostring(buttonNum);\n'
                                    'thisTechButtonInstance[buttonName]:SetVoids(void1, void2);\n'
                                    'thisTechButtonInstance[buttonName]:RegisterCallback(thisEvent, thisCallback);\nend\n')
                original_sources.append(artifact(included))
            hits = [[event['key'], 100, 100, 200, 200]]
            manifest = {'context': context, 'packet_version': 'ZSUPIX02', 'snapshot_state_unchanged': True,
                        'closed_context_not_drawn': False, 'retained_input_targets': [target], 'snapshot': artifact(snapshot),
                        'packet': artifact(packet), 'original_context_sources': original_sources, 'hit_regions': hits}
            manifest_path = folder / 'scene_manifest.json'; manifest_path.write_text(json.dumps(manifest))
            world_path = self.session / f'play-scene-{generation}.json'
            world_path.write_text(json.dumps({'generation': generation, 'turn': event['turn'], 'activePlayer': event['owner'],
                                              'hits': hits, 'pixelHitCount': 0}))
            self.driver['scene_requests'].append({'sequence': sequence, 'context': context, 'folder': str(folder),
                'snapshot_before_sha256': artifact(snapshot)['sha256'], 'snapshot_after_sha256': artifact(snapshot)['sha256'],
                'snapshot_state_unchanged': True, 'packet': artifact(packet), 'manifest': artifact(manifest_path)})
            self.text = self.text.replace(f'snapshot-{sequence}', str(snapshot)).replace(f'folder-{sequence}', str(folder))
            self.paths.append((snapshot, folder, world_path))

    def verify(self):
        return verify_worker_research_integration(self.text, self.root, self.driver, self.frames, required=True)

    def test_exact_original_packets(self):
        proof = self.verify()
        self.assertEqual(len(proof['original_callbacks']), 3)
        self.assertFalse(proof['human_input_verified'])

    def test_snapshot_and_driver_changes_rejected(self):
        self.driver['scene_requests'][1]['snapshot_state_unchanged'] = False
        with self.assertRaises(RuntimeError):
            self.verify()
        self.driver['scene_requests'][1]['snapshot_state_unchanged'] = True
        self.paths[1][0].write_text('{}')
        with self.assertRaises(RuntimeError):
            self.verify()

    def test_unpinned_shared_include_is_rejected(self):
        _, folder, _ = self.paths[0]
        path = folder / 'scene_manifest.json'
        manifest = json.loads(path.read_text())
        manifest['original_context_sources'] = [row for row in manifest['original_context_sources']
                                               if Path(row['path']).name != 'TechButtonInclude.lua']
        path.write_text(json.dumps(manifest))
        self.driver['scene_requests'][0]['manifest'] = artifact(path)
        with self.assertRaisesRegex(RuntimeError, 'included callback source pair'):
            self.verify()

    def test_frontmost_hit_and_original_source_changes_rejected(self):
        _, folder, world_path = self.paths[1]
        world = json.loads(world_path.read_text()); world['hits'].append([999, 100, 100, 200, 200])
        world_path.write_text(json.dumps(world))
        with self.assertRaises(RuntimeError):
            self.verify()
        world['hits'].pop(); world_path.write_text(json.dumps(world))
        next((folder / 'source_ui').glob('*.lua')).write_text('// replaced callback')
        with self.assertRaises(RuntimeError):
            self.verify()


if __name__ == '__main__':
    unittest.main()
