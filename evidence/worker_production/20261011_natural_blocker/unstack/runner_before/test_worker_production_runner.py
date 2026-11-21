"""Synthetic launcher and original-HUD checks; not native gameplay evidence."""
from __future__ import annotations

import copy
from pathlib import Path
import re
import sys
import unittest

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / 'Tests'))
sys.path.insert(0, str(PROJECT / 'tools'))

import run_interactive_game as runner
from action_info_panel_timeline import verify_action_info_panel_timeline
import test_worker_policy_runner as policy_runner_tests
from test_worker_research_timeline import policy_fixture, production_fixture
from verify_interactive_decisions import worker_production_contract_required
from worker_research_timeline import CAPABILITY, POLICY_CAPABILITY, PRODUCTION_CAPABILITY, VERIFIER_FILES


class FrozenProductionContracts(unittest.TestCase):
    setUp = policy_runner_tests.FrozenWorkerContracts.setUp
    source = policy_runner_tests.FrozenWorkerContracts.source
    freeze = policy_runner_tests.FrozenWorkerContracts.freeze

    def production_source(self):
        self.source('\n'.join((CAPABILITY, POLICY_CAPABILITY, PRODUCTION_CAPABILITY)))

    def test_existing_policy_contract_does_not_acquire_production_keys(self):
        self.source(CAPABILITY + '\n' + POLICY_CAPABILITY)
        research, policy, inputs = self.freeze()
        self.assertTrue(research and policy)
        self.assertEqual(set(inputs), set(VERIFIER_FILES))
        self.assertNotIn('worker_production_contract', self.request)
        self.assertFalse(worker_production_contract_required(self.request))
        self.assertEqual(runner.worker_production_result_fields(required=False, proof=None,
            failure='undeclared record', inputs_unchanged=True, success=False), {})

    def test_production_uses_same_three_sealed_verifiers(self):
        self.production_source()
        research, policy, inputs = self.freeze()
        self.assertTrue(research and policy)
        self.assertEqual(self.request['worker_production_contract'], 1)
        self.assertTrue(worker_production_contract_required(self.request))
        self.assertEqual(set(inputs), set(VERIFIER_FILES))
        self.assertEqual(set(p.name for p in self.frozen.iterdir()), set(VERIFIER_FILES) | {self.runner.name})

    def test_production_requires_both_prior_capabilities(self):
        for capabilities in (PRODUCTION_CAPABILITY, CAPABILITY + '\n' + PRODUCTION_CAPABILITY):
            with self.subTest(capabilities=capabilities):
                self.source(capabilities)
                with self.assertRaisesRegex(RuntimeError, 'requires the frozen research and policy'):
                    self.freeze()

    def test_non_exact_profiles_do_not_gain_production(self):
        self.production_source()
        original = copy.deepcopy(self.request)
        for key, value in (('smoke', False), ('unit_actions', 1), ('research_tree', False),
                           ('social_policy_smoke', True), ('tech_award', True)):
            with self.subTest(key=key):
                self.request = copy.deepcopy(original)
                self.request[key] = value
                before = copy.deepcopy(self.request)
                self.assertEqual(self.freeze(), (False, False, {}))
                self.assertEqual(self.request, before)

    def test_undeclared_host_cannot_claim_production(self):
        self.source(CAPABILITY + '\n' + POLICY_CAPABILITY)
        self.request['worker_production_contract'] = 1
        with self.assertRaises(RuntimeError):
            self.freeze()

    def test_mutated_sealed_inputs_are_rejected(self):
        self.production_source()
        self.freeze()
        (self.frozen / VERIFIER_FILES[0]).write_text('changed', encoding='utf8')
        with self.assertRaises(RuntimeError):
            worker_production_contract_required(self.request)

    def test_partial_proof_never_promotes_failed_run(self):
        proof = {'contract_version': 1, 'completed_cycle_count': 0, 'cycles': []}
        accepted = runner.worker_production_result_fields(required=True, proof=proof, failure=None,
            inputs_unchanged=True, success=True)
        self.assertTrue(accepted['worker_production_verified'])
        self.assertEqual(set(accepted), {'worker_production_contract_required', 'worker_production_verified',
            'worker_production_evidence', 'worker_production_failure', 'worker_production_verifier_inputs_unchanged'})
        for saved, failure, unchanged, success in ((proof, None, True, False),
                (proof, None, False, True), (proof, 'incomplete', True, True), (None, None, True, True)):
            with self.subTest(failure=failure, unchanged=unchanged, success=success):
                result = runner.worker_production_result_fields(required=True, proof=saved, failure=failure,
                    inputs_unchanged=unchanged, success=success)
                self.assertFalse(result['worker_production_verified'])


class ProductionHudBinding(unittest.TestCase):
    @staticmethod
    def verify(text, *, restored=False, **overrides):
        options = dict(worker_build_profile=True, worker_research_contract=True,
                       worker_policy_contract=True, worker_production_contract=True)
        options.update(overrides)
        return verify_action_info_panel_timeline(text, restored=restored, **options)

    def test_zero_and_one_cycle_on_both_profiles(self):
        for restored in (False, True):
            for cycle in (False, True):
                with self.subTest(restored=restored, cycle=cycle):
                    self.assertEqual(self.verify(production_fixture(restored=restored, cycle=cycle),
                        restored=restored), (True, None))

    def test_policy_only_legacy_is_unchanged(self):
        for restored in (False, True):
            self.assertEqual(self.verify(policy_fixture(restored=restored), restored=restored,
                worker_production_contract=False), (True, None))

    def test_production_requires_explicit_full_contract(self):
        text = production_fixture()
        for key, value in (('worker_production_contract', False), ('worker_production_contract', 1),
                ('worker_production_contract', None), ('worker_policy_contract', False),
                ('worker_research_contract', False), ('worker_build_profile', False)):
            with self.subTest(key=key, value=value):
                self.assertFalse(self.verify(text, **{key: value})[0])

    def test_original_blocker_and_consumed_posted_input_are_required(self):
        text = production_fixture()
        target = re.search(r'^INTERACTIVE_ACTION_INFO_SMOKE_TARGET=production-continuation\|([^\n]+)$', text, re.M)
        self.assertIsNotNone(target)
        blocker, notification, key, generation, turn = target[1].split('|')
        self.assertEqual(blocker, '2')
        mutations = [(target[0], target[0].replace('production-continuation|2|', 'production-continuation|1|')),
            (target[0], target[0].replace(f'|{notification}|{key}|', f'|-1|{key}|')),
            (target[0], target[0].replace(f'|{key}|{generation}|', f'|{int(key)+1}|{generation}|'))]
        for prefix in (f'INTERACTIVE_SMOKE_POSTED={generation}|{key}|',
                f'INTERACTIVE_SMOKE_BUTTON={generation}|{key}|',
                f'INTERACTIVE_ACTION_INFO_PANEL_INPUT={generation}|1|{key}|'):
            line = next(row for row in text.splitlines() if row.startswith(prefix))
            mutations.extend(((line, ''), (line, line + '\n' + line)))
        for old, new in mutations:
            with self.subTest(record=old, replacement=new):
                self.assertFalse(self.verify(text.replace(old, new, 1))[0])

    def test_return_must_precede_the_same_turn_end_turn(self):
        text = production_fixture()
        line = next(row for row in text.splitlines() if row.startswith('INTERACTIVE_WORKER_PRODUCTION_RETURNED='))
        self.assertFalse(self.verify(text.replace(line, '', 1))[0])
        turn = line.split('=', 1)[1].split('|')[1]
        end_turn = next(row for row in text.splitlines()
            if row.startswith('INTERACTIVE_ACTION_INFO_SMOKE_TARGET=end-turn|') and row.endswith('|' + turn))
        late = text.replace(line + '\n', '', 1).replace(end_turn, end_turn + '\n' + line, 1)
        self.assertFalse(self.verify(late)[0])


if __name__ == '__main__':
    unittest.main()
