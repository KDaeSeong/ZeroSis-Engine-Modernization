"""Actual sealed-source and collision regressions; no runner main/native call."""
import copy
import ast
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
PROJECT = Path(__file__).absolute().parents[1]
sys.path.insert(0, str(PROJECT / 'tools'))
import run_interactive_game as runner
import verify_interactive_decisions as decisions
import verify_interactive_game as verifier
from probe_world_builder import artifact
from worker_research_timeline import REQUEST_FLAGS, EXCLUDED_FLAGS, VERIFIER_FILES


class ContinuousHostSourceIndexTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.actual = json.loads((PROJECT / 'evidence/ui_window_host/20261101T074006Z_c2fd2fe9be38/build_result.json').read_bytes())

    def test_actual_lowercase_frozen_source_names_keep_all_capability_checks(self):
        sources = runner.continuous_host_code_sources(self.actual)
        self.assertEqual(Path(sources['hostmain.cpp']['path']).name, 'hostmain.cpp')
        self.assertIn('--play-load-smoke', Path(sources['hostmain.cpp']['path']).read_text(encoding='utf-8'))
        loop = Path(sources['interactivegameloop.h']['path']).read_text(encoding='utf-8')
        self.assertIn('ZEROSIS_PLAY_ACTION_INFO_PANEL', loop)
        self.assertIn('ZEROSIS_PLAY_NOTIFICATION_PANEL', loop)
        self.assertIn('socialpolicysmokefixture.h', sources)
        self.assertIn('economicoverviewsmokefixture.h', sources)
        self.assertIn('worldterrainrenderer.cpp', sources)
        for name in ('WorldTerrainRenderer.cpp', 'WorldViewRenderer.cpp', 'WorldViewRenderer.h',
                     'WorldViewState.h', 'WorldUnitAssets.h'):
            self.assertIn(name, sources)
            self.assertIs(sources[name], sources.get(name.lower()))
        for token in ('ZEROSIS_PLAY_RESEARCH_TREE_SMOKE', 'ZEROSIS_PLAY_TECH_AWARD_SMOKE',
                      'ZEROSIS_PLAY_UNIT_ACTIONS_SMOKE', 'ZEROSIS_PLAY_WORKER_BUILD_SMOKE',
                      'ZEROSIS_PLAY_COMBAT_SMOKE', 'ZEROSIS_PLAY_CITY_CAPTURE_SMOKE',
                      'ZEROSIS_PLAY_DECLARE_WAR_SMOKE', 'ZEROSIS_PLAY_SOCIAL_POLICY_SMOKE',
                      'ZEROSIS_PLAY_ECONOMIC_OVERVIEW_SMOKE', 'ZEROSIS_PLAY_ACTION_INFO_PANEL',
                      'ZEROSIS_PLAY_NOTIFICATION_PANEL', 'ZEROSIS_PLAY_GAME_MENU_SMOKE'):
            self.assertIn(token, loop)
        prior = json.loads((PROJECT / 'evidence/interactive_game/20261022T001546Z_7fba195072e4/request.json').read_bytes())
        spec = {Path(row['path']).name: row for row in prior['runtime_inputs']}
        self.assertEqual(len(spec), 24)
        self.assertIn('terrain-assets.bin', spec)
        self.assertIn('unit-assets.bin', spec)
        for name in ('terrain-assets.bin', 'unit-assets.bin'):
            self.assertEqual(artifact(Path(spec[name]['path']))['sha256'], spec[name]['sha256'])
        self.assertEqual(len(sources), len(set(sources)))

    def test_every_runner_code_basename_lookup_uses_the_same_casefold_identity(self):
        tree = ast.parse((PROJECT / 'tools/run_interactive_game.py').read_text(encoding='utf8'))
        checked = []
        for node in ast.walk(tree):
            values = []
            if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) and node.value.id == 'sources':
                values = [node.slice]
            elif isinstance(node, ast.Compare) and len(node.ops) == 1 and isinstance(node.ops[0], (ast.In, ast.NotIn)):
                if isinstance(node.comparators[0], ast.Name) and node.comparators[0].id == 'sources':
                    values = [node.left]
            for value in values:
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    self.assertEqual(value.value, value.value.casefold())
                    checked.append(value.value)
        self.assertIn('worldterrainrenderer.cpp', checked)
        self.assertIn('socialpolicysmokefixture.h', checked)
        self.assertIn('economicoverviewsmokefixture.h', checked)

    def test_casefold_code_collision_is_rejected_before_last_row_wins(self):
        value = copy.deepcopy(self.actual)
        row = next(row for row in value['sources'] if Path(row['path']).name.casefold() == 'hostmain.cpp')
        value['sources'].append(dict(row, path=str(Path(row['path']).with_name('HOSTMAIN.CPP'))))
        with self.assertRaisesRegex(RuntimeError, 'Ambiguous sealed Host source basename'):
            runner.continuous_host_code_sources(value)

    def test_missing_required_code_and_missing_play_token_still_fail(self):
        value = copy.deepcopy(self.actual)
        value['sources'] = [row for row in value['sources'] if Path(row['path']).name.casefold() != 'localturnsignals.h']
        with self.assertRaisesRegex(RuntimeError, 'continuous gameplay implementation'):
            runner.continuous_host_code_sources(value)
        temporary = tempfile.TemporaryDirectory(prefix='_host_source_case_', dir=PROJECT)
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / 'hostmain.cpp'
        path.write_text('// token intentionally absent\n', encoding='utf-8')
        value = copy.deepcopy(self.actual)
        for row in value['sources']:
            if Path(row['path']).name.casefold() == 'hostmain.cpp':
                row['path'] = str(path)
        with self.assertRaisesRegex(RuntimeError, 'continuous gameplay implementation'):
            runner.continuous_host_code_sources(value)

    def test_actual_verifier_keeps_canonical_required_and_optional_keys(self):
        names = verifier.REQUIRED_SOURCES | {'WorldTerrainRenderer.cpp', 'WorldUnitAssets.h',
            'InteractiveUiSession.h', 'UiPopupContext.h', 'HostServices.h'}
        indexed = verifier.canonical_host_code_sources(self.actual, names)
        self.assertEqual(set(indexed), names)
        for name, row in indexed.items():
            self.assertEqual(Path(row['path']).name.casefold(), name.casefold())
        self.assertIn('INTERACTIVE_DECISION_SMOKE_COMPLETE=1',
            Path(indexed['InteractiveGameLoop.h']['path']).read_text(encoding='utf8'))
        value = copy.deepcopy(self.actual)
        value['sources'].append(indexed['InteractiveGameLoop.h'])
        with self.assertRaisesRegex(RuntimeError, 'Ambiguous sealed Host source basename'):
            verifier.canonical_host_code_sources(value, names)

    def test_actual_final_host_all_four_worker_contracts_and_file_only_profile(self):
        temporary = tempfile.TemporaryDirectory(prefix='_actual_worker_contract_', dir=PROJECT)
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        frozen = root / 'run_interactive_game.py'
        frozen.write_bytes((PROJECT / 'tools/run_interactive_game.py').read_bytes())
        build_path = PROJECT / 'evidence/ui_window_host/20261101T074006Z_c2fd2fe9be38/build_result.json'
        request = {name: True for name in REQUEST_FLAGS}
        request.update({name: False for name in EXCLUDED_FLAGS})
        request['provenance'] = {'host_build': artifact(build_path), 'frozen_runner': artifact(frozen)}
        loop = runner.continuous_host_code_sources(self.actual)['interactivegameloop.h']
        with patch('subprocess.Popen', side_effect=AssertionError('Native execution is forbidden')):
            research, policy, inventory = runner.freeze_worker_contracts(request, frozen, loop)
            self.assertTrue(research)
            self.assertTrue(policy)
            self.assertEqual(set(inventory), set(VERIFIER_FILES))
            for check in (decisions.worker_research_contract_required, decisions.worker_policy_contract_required,
                          decisions.worker_production_contract_required, decisions.worker_unstack_contract_required):
                self.assertTrue(check(request))
            preparation = {name: False for name in REQUEST_FLAGS}
            preparation['provenance'] = {'host_build': artifact(build_path), 'frozen_runner': artifact(frozen)}
            self.assertEqual(runner.freeze_worker_contracts(preparation, frozen, loop), (False, False, {}))
            for name in ('worker_research_contract', 'worker_policy_contract', 'worker_production_contract'):
                self.assertNotIn(name, preparation)
        original = request['provenance']['host_build']['sha256']
        request['provenance']['host_build']['sha256'] = '0' * 64
        with self.assertRaisesRegex(RuntimeError, 'Changed map object input'):
            decisions.worker_research_contract_required(request)
        request['provenance']['host_build']['sha256'] = original
        duplicate = copy.deepcopy(self.actual)
        duplicate['sources'].append(dict(loop, path=str(Path(loop['path']).with_name('INTERACTIVEGAMELOOP.H'))))
        duplicate_path = root / 'duplicate_build.json'
        duplicate_path.write_text(json.dumps(duplicate), encoding='utf8')
        request['provenance']['host_build'] = artifact(duplicate_path)
        for check in (decisions.worker_research_contract_required, decisions.worker_policy_contract_required,
                      decisions.worker_production_contract_required, decisions.worker_unstack_contract_required):
            with self.assertRaisesRegex(RuntimeError, 'Ambiguous sealed Host source basename'):
                check(request)


if __name__ == '__main__':
    unittest.main()
