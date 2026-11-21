"""Bounded launcher/HUD integration tests; synthetic records are not native proof."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import patch

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / 'Tests'))
sys.path.insert(0, str(PROJECT / 'tools'))

import run_interactive_game as runner
from action_info_panel_timeline import verify_action_info_panel_timeline
from probe_world_builder import artifact
from test_worker_research_timeline import fixture, policy_fixture
from verify_interactive_decisions import worker_policy_contract_required
from worker_research_timeline import CAPABILITY, POLICY_CAPABILITY, REQUEST_FLAGS, VERIFIER_FILES


class FrozenWorkerContracts(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='worker-policy-runner-')
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.tools = self.root / 'tools'; self.tools.mkdir()
        for name in VERIFIER_FILES:
            (self.tools / name).write_text('# synthetic verifier source: ' + name + '\n', encoding='utf8')
        self.frozen = self.root / 'frozen_inputs'; self.frozen.mkdir()
        self.runner = self.frozen / 'run_interactive_game.py'
        self.runner.write_text('# synthetic frozen runner\n', encoding='utf8')
        self.loop = self.root / 'InteractiveGameLoop.h'
        self.build = self.root / 'build_result.json'
        self.request = {name: True for name in REQUEST_FLAGS}
        self.patch_project = patch.object(runner, 'PROJECT', self.root)
        self.patch_project.start(); self.addCleanup(self.patch_project.stop)
        self.source('')

    def source(self, capabilities):
        self.loop.write_text('// synthetic sealed loop\n' + capabilities + '\n', encoding='utf8')
        self.build.write_text(json.dumps({'sources': [artifact(self.loop)]}), encoding='utf8')
        self.request['provenance'] = {'host_build': artifact(self.build), 'frozen_runner': artifact(self.runner)}

    def freeze(self):
        return runner.freeze_worker_contracts(self.request, self.runner, artifact(self.loop))

    def test_legacy_loop_preserves_exact_request_and_result_shape(self):
        before = copy.deepcopy(self.request)
        self.assertEqual(self.freeze(), (False, False, {}))
        self.assertEqual(self.request, before)
        self.assertEqual([path.name for path in self.frozen.iterdir()], [self.runner.name])
        for failure in (None, 'undeclared policy records'):
            self.assertEqual(runner.worker_policy_result_fields(required=False, proof=None, failure=failure,
                inputs_unchanged=True, success=failure is None), {})

    def test_research_only_loop_keeps_its_previous_three_file_contract(self):
        self.source(CAPABILITY)
        research, policy, inventory = self.freeze()
        self.assertTrue(research); self.assertFalse(policy)
        self.assertEqual(set(inventory), set(VERIFIER_FILES))
        self.assertEqual(self.request['worker_research_contract'], 1)
        self.assertNotIn('worker_policy_contract', self.request)
        self.assertEqual(set(self.request['provenance']),
                         {'host_build', 'frozen_runner', 'worker_research_verifiers'})

    def test_policy_uses_same_exact_frozen_files_and_no_fourth_module(self):
        self.source(CAPABILITY + '\n' + POLICY_CAPABILITY)
        research, policy, inventory = self.freeze()
        self.assertTrue(research); self.assertTrue(policy)
        self.assertEqual(self.request['worker_policy_contract'], 1)
        self.assertTrue(worker_policy_contract_required(self.request))
        self.assertEqual(set(inventory), set(VERIFIER_FILES))
        self.assertEqual(set(path.name for path in self.frozen.iterdir()),
                         set(VERIFIER_FILES) | {self.runner.name})
        for name, ref in inventory.items():
            self.assertEqual(ref, artifact(self.frozen / name))
            self.assertEqual((self.frozen / name).read_bytes(), (self.tools / name).read_bytes())

    def test_non_exact_profiles_do_not_gain_capability(self):
        self.source(CAPABILITY + '\n' + POLICY_CAPABILITY)
        base = copy.deepcopy(self.request)
        for key, value in [('smoke', False), ('unit_actions', 1), ('research_tree', False),
                           ('social_policy_smoke', True), ('tech_award', True)]:
            with self.subTest(key=key, value=value):
                self.request = copy.deepcopy(base); self.request[key] = value
                before = copy.deepcopy(self.request)
                self.assertEqual(self.freeze(), (False, False, {}))
                self.assertEqual(self.request, before)

    def test_policy_without_frozen_research_is_rejected(self):
        self.source(POLICY_CAPABILITY)
        with self.assertRaisesRegex(RuntimeError, 'requires the frozen natural research'):
            self.freeze()

    def test_changed_loop_is_rejected_before_any_verifier_copy(self):
        self.source(CAPABILITY + '\n' + POLICY_CAPABILITY)
        pinned = artifact(self.loop)
        self.loop.write_text('changed after sealing', encoding='utf8')
        with self.assertRaises(RuntimeError):
            runner.freeze_worker_contracts(self.request, self.runner, pinned)
        self.assertEqual([path.name for path in self.frozen.iterdir()], [self.runner.name])

    def test_declared_legacy_or_out_of_profile_policy_is_rejected(self):
        self.request['worker_policy_contract'] = 1
        with self.assertRaises(RuntimeError):
            self.freeze()
        self.source(CAPABILITY + '\n' + POLICY_CAPABILITY)
        self.request['smoke'] = False
        with self.assertRaises(RuntimeError):
            self.freeze()

    def test_changed_frozen_verifier_cannot_be_reused(self):
        self.source(CAPABILITY + '\n' + POLICY_CAPABILITY)
        self.freeze()
        (self.frozen / VERIFIER_FILES[0]).write_text('tampered frozen verifier', encoding='utf8')
        with self.assertRaises(RuntimeError):
            worker_policy_contract_required(self.request)

    def test_result_proof_never_promotes_failed_or_changed_input_runs(self):
        proof = {'contract_version': 1, 'completed_cycle_count': 0, 'cycles': []}
        fields = runner.worker_policy_result_fields(required=True, proof=proof, failure=None,
                                                   inputs_unchanged=True, success=True)
        self.assertEqual(set(fields), {'worker_policy_contract_required', 'worker_policy_verified',
                         'worker_policy_evidence', 'worker_policy_failure',
                         'worker_policy_verifier_inputs_unchanged'})
        self.assertTrue(fields['worker_policy_verified'])
        for saved_proof, failure, unchanged, success in ((proof, None, True, False),
                (proof, None, False, True), (proof, 'incomplete cycle', True, True),
                (None, None, True, True)):
            with self.subTest(failure=failure, unchanged=unchanged, success=success):
                result = runner.worker_policy_result_fields(required=True, proof=saved_proof,
                    failure=failure, inputs_unchanged=unchanged, success=success)
                self.assertFalse(result['worker_policy_verified'])


class NaturalPolicyHudBinding(unittest.TestCase):
    @staticmethod
    def verify(text, *, restored=False, **overrides):
        options = dict(worker_build_profile=True, worker_research_contract=True, worker_policy_contract=True)
        options.update(overrides)
        return verify_action_info_panel_timeline(text, restored=restored, **options)

    def test_zero_and_one_cycle_fresh_and_restore(self):
        for restored in (False, True):
            for cycle in (False, True):
                with self.subTest(restored=restored, cycle=cycle):
                    self.assertEqual(self.verify(policy_fixture(restored=restored, cycle=cycle),
                                                 restored=restored), (True, None))

    def test_research_only_legacy_hud_is_unchanged(self):
        for restored in (False, True):
            self.assertEqual(self.verify(fixture(restored=restored), restored=restored,
                                        worker_policy_contract=False), (True, None))

    def test_policy_requires_explicit_worker_and_research_opt_in(self):
        text = policy_fixture()
        for key, value in (('worker_policy_contract', False), ('worker_policy_contract', 1),
                           ('worker_policy_contract', None), ('worker_build_profile', False),
                           ('worker_research_contract', False)):
            with self.subTest(key=key, value=value):
                self.assertFalse(self.verify(text, **{key: value})[0])

    def test_policy_hud_requires_actual_posted_input_and_original_blocker(self):
        text = policy_fixture()
        target = re.search(r'^INTERACTIVE_ACTION_INFO_SMOKE_TARGET=policy-continuation\|([^\n]+)$', text, re.M)
        self.assertIsNotNone(target)
        blocker, notification, key, generation, turn = target[1].split('|')
        self.assertEqual(blocker, '0')
        mutations = [
            (target[0], target[0].replace('policy-continuation|0|', 'policy-continuation|1|')),
            (target[0], target[0].replace(f'|{notification}|{key}|', f'|-1|{key}|')),
            (target[0], target[0].replace(f'|{key}|{generation}|', f'|{int(key)+1}|{generation}|')),
            (target[0], target[0].replace(f'|{generation}|{turn}', f'|{int(generation)-1}|{turn}')),
        ]
        for prefix in (f'INTERACTIVE_SMOKE_POSTED={generation}|{key}|',
                       f'INTERACTIVE_SMOKE_BUTTON={generation}|{key}|',
                       f'INTERACTIVE_ACTION_INFO_PANEL_INPUT={generation}|1|{key}|'):
            line = next(row for row in text.splitlines() if row.startswith(prefix))
            mutations.extend(((line, ''), (line, line + '\n' + line)))
        for old, new in mutations:
            with self.subTest(record=old, replacement=new):
                self.assertFalse(self.verify(text.replace(old, new, 1))[0])

    def test_policy_must_return_before_same_turn_end_turn(self):
        text = policy_fixture()
        line = next(row for row in text.splitlines() if row.startswith('INTERACTIVE_WORKER_POLICY_RETURNED='))
        self.assertFalse(self.verify(text.replace(line, '', 1))[0])
        turn = line.split('=', 1)[1].split('|')[1]
        end_turn = next(row for row in text.splitlines() if row.startswith('INTERACTIVE_ACTION_INFO_SMOKE_TARGET=end-turn|')
                        and row.endswith('|' + turn))
        late = text.replace(line + '\n', '', 1).replace(end_turn, end_turn + '\n' + line, 1)
        self.assertFalse(self.verify(late)[0])


if __name__ == '__main__':
    unittest.main()
