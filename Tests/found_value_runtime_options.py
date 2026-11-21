"""Headless tests of production worker policy, launcher and child-env wiring."""
from __future__ import annotations

import copy
import hashlib
import importlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

PROJECT = Path(__file__).absolute().parents[1]
TOOLS = PROJECT / 'tools'
FIELD = 'found_value_worker_policy'
ERRORS = (ValueError, TypeError, RuntimeError)
CONTROLLED_CHILDREN = []
_MODULES = {}


def production(name):
    if name in _MODULES:
        return _MODULES[name]
    sys.path.insert(0, str(TOOLS))
    if name == 'options':
        existing = sys.modules.get('found_value_runtime_options')
        if existing is not None and Path(existing.__file__).absolute() == TOOLS / 'found_value_runtime_options.py':
            module = existing
        else:
            spec = importlib.util.spec_from_file_location('_tested_found_value_policy', TOOLS / 'found_value_runtime_options.py')
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
    else:
        # The test and production helper intentionally have the same filename.
        # Bind the actual helper during imports, including unittest discovery.
        with patch.dict(sys.modules, {'found_value_runtime_options': production('options')}):
            module = importlib.import_module({'runner': 'run_interactive_game', 'driver': 'interactive_ui_driver'}[name])
    _MODULES[name] = module
    return module


class PolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.api = production('options')

    def reject(self, call):
        with self.assertRaises(ERRORS):
            call()

    def test_auto_uses_the_supplied_logical_hint_and_exact_caps(self):
        cases = ((None, 'unavailable', 0), (0, 'cpu_count', 0), (1, 'cpu_count', 0),
                 (2, 'cpu_count', 2), (3, 'cpu_count', 2), (4, 'cpu_count', 4),
                 (5, 'process_cpu_count', 4), (256, 'process_cpu_count', 4))
        for hint, source, expected in cases:
            with self.subTest(hint=hint, source=source):
                value = self.api.resolve_policy('auto', hint, source)
                self.assertEqual(value['resolved_workers'], expected)
                self.assertEqual(value['cpu_hint'], {'source': source, 'available_logical_cpus': hint})
                self.assertEqual(value, self.api.validate_policy(value))
                self.assertIs(value['trace_enabled'], False)
                self.assertIs(value['cpu_trace_enabled'], False)

    def test_explicit_zero_and_one_are_distinct_valid_selections(self):
        for requested, expected in (('0', 0), ('1', 1), ('2', 2), ('4', 4)):
            with self.subTest(requested=requested):
                value = self.api.resolve_policy(requested)
                self.assertEqual((value['requested'], value['resolved_workers']), (requested, expected))
                self.assertEqual(value['cpu_hint'], {'source': 'explicit', 'available_logical_cpus': None})

    def test_request_strings_are_exact_and_types_are_not_coerced(self):
        for value in (None, True, False, 0, 2, 2.0, b'2', '', '01', '00', ' 2', '2 ', '+2', '-1', '3', '8', 'AUTO'):
            with self.subTest(value=repr(value)):
                self.reject(lambda: self.api.resolve_policy(value))

    def test_invalid_cpu_hints_and_sources_are_rejected(self):
        for hint in (True, False, -1, 1.5, '4', [], {}):
            with self.subTest(hint=repr(hint)):
                self.reject(lambda: self.api.resolve_policy('auto', hint, 'cpu_count'))
        for source in (None, True, 1, '', 'other', 'explicit', 'legacy_request'):
            with self.subTest(source=repr(source)):
                self.reject(lambda: self.api.resolve_policy('auto', None, source))
        self.reject(lambda: self.api.resolve_policy('auto', 4, 'unavailable'))
        self.reject(lambda: self.api.resolve_policy('2', 4, 'cpu_count'))

    def test_validation_is_exact_and_returns_independent_nested_values(self):
        original = self.api.resolve_policy('auto', 3, 'cpu_count')
        before = copy.deepcopy(original)
        checked = self.api.validate_policy(original)
        self.assertEqual(checked, before)
        self.assertIsNot(checked, original)
        self.assertIsNot(checked['cpu_hint'], original['cpu_hint'])
        checked['cpu_hint']['source'] = 'changed'
        self.assertEqual(original, before)
        for field in original:
            candidate = copy.deepcopy(original)
            del candidate[field]
            with self.subTest(missing=field):
                self.reject(lambda: self.api.validate_policy(candidate))
        candidate = copy.deepcopy(original)
        candidate['extra'] = 0
        self.reject(lambda: self.api.validate_policy(candidate))

    def test_validation_rejects_forged_worker_trace_schema_and_hint_values(self):
        baseline = self.api.resolve_policy('auto', 3, 'cpu_count')
        changes = (('schema', 'unknown'), ('requested', True), ('requested', '3'),
                   ('resolved_workers', True), ('resolved_workers', 3), ('resolved_workers', 4),
                   ('trace_enabled', True), ('trace_enabled', 0),
                   ('cpu_trace_enabled', True), ('cpu_trace_enabled', 0),
                   ('cpu_hint', {}), ('cpu_hint', {'source': 'cpu_count', 'available_logical_cpus': True}),
                   ('cpu_hint', {'source': 'unavailable', 'available_logical_cpus': 3}),
                   ('cpu_hint', {'source': 'legacy_request', 'available_logical_cpus': None}))
        for field, value in changes:
            with self.subTest(field=field, value=repr(value)):
                candidate = copy.deepcopy(baseline)
                candidate[field] = value
                self.reject(lambda: self.api.validate_policy(candidate))
        explicit = self.api.resolve_policy('1')
        explicit['cpu_hint']['source'] = 'legacy_request'
        self.reject(lambda: self.api.validate_policy(explicit))

    def test_missing_legacy_policy_is_zero_but_present_null_is_invalid(self):
        legacy = self.api.policy_from_request({'unrelated': 1})
        self.assertEqual((legacy['requested'], legacy['resolved_workers']), ('0', 0))
        self.assertEqual(legacy['cpu_hint'], {'source': 'legacy_request', 'available_logical_cpus': None})
        for request in (None, [], True, {FIELD: None}, {FIELD: {}}, {FIELD: False}):
            with self.subTest(request=repr(request)):
                self.reject(lambda: self.api.policy_from_request(request))
        policy = self.api.resolve_policy('auto', 4, 'cpu_count')
        self.assertEqual(self.api.policy_from_request({FIELD: policy}), policy)

    def test_driver_requires_the_resolved_flag_to_match_sealed_policy(self):
        for requested, hint, source, flag in (('auto', 3, 'cpu_count', '2'), ('0', None, 'unavailable', '0'),
                                               ('1', None, 'unavailable', '1'), ('4', None, 'unavailable', '4')):
            policy = self.api.resolve_policy(requested, hint, source)
            self.assertEqual(self.api.driver_policy(policy, flag), policy)
            for bad in (None, int(flag), True, 'auto', '3', '00', ' ' + flag, '4' if flag != '4' else '2'):
                with self.subTest(requested=requested, bad=repr(bad)):
                    self.reject(lambda: self.api.driver_policy(policy, bad))
        self.assertEqual(self.api.driver_policy(None, None), self.api.policy_from_request({}))
        self.assertEqual(self.api.driver_policy(None, '0'), self.api.policy_from_request({}))
        for bad in ('1', '2', '4', 'auto', 0, False, ''):
            self.reject(lambda: self.api.driver_policy(None, bad))

    def test_child_environment_ignores_all_ambient_case_variants(self):
        parent = {'PATH': 'synthetic-path', 'KEEP': 'unchanged',
                  'ZEROSIS_FOUND_VALUE_WORKERS': 'malformed', 'zerosis_found_value_workers': '99',
                  'ZeRoSiS_FoUnD_VaLuE_TrAcE': '1', 'ZEROSIS_FOUND_VALUE_CPU_TRACE': 'invalid',
                  'zerosis_found_value_cpu_trace': '1', 'OTHER_ZEROSIS_FOUND_VALUE_WORKERS': 'keep'}
        original = copy.deepcopy(parent)
        synthetic_process = {'SYNTHETIC_PARENT': 'unchanged'}
        with patch.object(os, 'environ', synthetic_process):
            for requested in ('0', '1', '2', '4'):
                child = self.api.child_environment(parent, self.api.resolve_policy(requested))
                self.assertIsNot(child, parent)
                self.assertEqual(child['ZEROSIS_FOUND_VALUE_WORKERS'], requested)
                self.assertEqual(child['KEEP'], 'unchanged')
                self.assertEqual(child['OTHER_ZEROSIS_FOUND_VALUE_WORKERS'], 'keep')
                knobs = {key.upper() for key in child if key.upper() in self.api.ENVIRONMENT_NAMES}
                self.assertEqual(knobs, {'ZEROSIS_FOUND_VALUE_WORKERS'})
                self.assertEqual(parent, original)
            self.assertEqual(synthetic_process, {'SYNTHETIC_PARENT': 'unchanged'})

    def test_environment_bad_types_fail_without_mutating_parent(self):
        policy = self.api.resolve_policy('2')
        for parent in (None, [], {'PATH': None}, {1: 'value'}, {'PATH': 1}):
            with self.subTest(kind=type(parent).__name__):
                before = copy.deepcopy(parent)
                self.reject(lambda: self.api.child_environment(parent, policy))
                self.assertEqual(parent, before)


class RunnerGlueTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.api, cls.runner = production('options'), production('runner')

    def test_fresh_auto_samples_one_cpu_source_once(self):
        with patch.object(self.runner.os, 'process_cpu_count', return_value=3, create=True) as process_count, \
                patch.object(self.runner.os, 'cpu_count', side_effect=AssertionError('Unexpected second CPU query')):
            policy = self.runner.select_found_value_policy()
        self.assertEqual(process_count.call_count, 1)
        self.assertEqual(policy, self.api.resolve_policy('auto', 3, 'process_cpu_count'))

    def test_cpu_failure_fallback_and_unknown_hint_are_recorded(self):
        with patch.object(self.runner.os, 'process_cpu_count', side_effect=OSError('synthetic'), create=True), \
                patch.object(self.runner.os, 'cpu_count', return_value=2) as fallback:
            self.assertEqual(self.runner.select_found_value_policy(), self.api.resolve_policy('auto', 2, 'cpu_count'))
            self.assertEqual(fallback.call_count, 1)
        with patch.object(self.runner.os, 'process_cpu_count', side_effect=NotImplementedError, create=True), \
                patch.object(self.runner.os, 'cpu_count', side_effect=OSError('synthetic')):
            self.assertEqual(self.runner.select_found_value_policy(), self.api.resolve_policy('auto'))

    def test_explicit_and_existing_policy_never_requery_cpu(self):
        policy = self.api.resolve_policy('auto', 4, 'cpu_count')
        with patch.object(self.runner.os, 'process_cpu_count', side_effect=AssertionError('CPU requery'), create=True), \
                patch.object(self.runner.os, 'cpu_count', side_effect=AssertionError('CPU requery')):
            self.assertEqual(self.runner.select_found_value_policy('0'), self.api.resolve_policy('0'))
            self.assertEqual(self.runner.select_found_value_policy(previous_request={FIELD: policy}), policy)
            self.assertEqual(self.runner.select_found_value_policy(support_policy=policy), policy)
            self.assertEqual(self.runner.select_found_value_policy(previous_request={})['resolved_workers'], 0)
            with self.assertRaises(ERRORS):
                self.runner.select_found_value_policy('2', support_policy=policy)

    def test_play_resume_and_smoke_use_one_resolved_policy(self):
        for requested, hint, source, count in (('auto', 3, 'cpu_count', '2'), ('0', None, 'unavailable', '0'),
                                               ('1', None, 'unavailable', '1'), ('4', None, 'unavailable', '4')):
            policy = self.api.resolve_policy(requested, hint, source)
            arguments = self.runner.found_value_driver_arguments(policy)
            self.assertEqual(arguments, ['--found-value-workers', count])
            play, resume = self.runner.build_interactive_launchers(
                python_ps="'python.exe'", driver_ps="'interactive_ui_driver.py'", common_driver_args=' --sealed-common',
                policy_info=1, default_checkpoint="'checkpoint.zssave'", worker_policy=policy)
            for script in (play, resume):
                self.assertEqual(script.count('--found-value-workers ' + count), 1)
                self.assertNotIn('--found-value-workers auto', script)
                self.assertNotIn('cpu_count', script)
                self.assertNotIn('ZEROSIS_FOUND_VALUE_TRACE', script)
                self.assertNotIn('ZEROSIS_FOUND_VALUE_CPU_TRACE', script)
                self.assertIn(' --sealed-common', script)
            self.assertIn('--mode play --timeout 0', play)
            self.assertIn('--mode play-load --checkpoint $Checkpoint --timeout 0', resume)
            # This is the same production helper called on the smoke environment
            # immediately before the real runner's Host Popen.
            parent = {'KEEP': 'smoke', 'zerosis_found_value_workers': 'bad', 'ZEROSIS_FOUND_VALUE_TRACE': '1'}
            before = copy.deepcopy(parent)
            env = self.runner.child_environment(parent, policy)
            self.assertEqual(env, {'KEEP': 'smoke', 'ZEROSIS_FOUND_VALUE_WORKERS': count})
            self.assertEqual(parent, before)

    def test_launcher_rejects_bad_policy_and_policy_info(self):
        kwargs = dict(python_ps="'python'", driver_ps="'driver'", common_driver_args='',
                      policy_info=1, default_checkpoint="''", worker_policy=self.api.resolve_policy('0'))
        for value in (True, False, '1', 2, None):
            with self.assertRaises(ERRORS):
                self.runner.build_interactive_launchers(**{**kwargs, 'policy_info': value})
        with self.assertRaises(ERRORS):
            self.runner.build_interactive_launchers(**{**kwargs, 'worker_policy': {}})


class ControlledStop(Exception):
    """The actual driver reached its intercepted initial Host boundary."""


class DriverGlueTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.api, cls.driver = production('options'), production('driver')

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='found_value_driver_contract_', dir=PROJECT / 'Tests')
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        self.manifest = self.folder / 'support.json'
        self.parent = {'PATH': 'synthetic-path', 'KEEP': 'synthetic-parent',
                       'ZEROSIS_FOUND_VALUE_WORKERS': 'malformed', 'zerosis_found_value_workers': '99',
                       'ZeRoSiS_FoUnD_VaLuE_TrAcE': '1', 'ZEROSIS_FOUND_VALUE_CPU_TRACE': 'bad',
                       'zerosis_found_value_cpu_trace': '1', 'ZEROSIS_UI_WINDOW_PROFILE': 'synthetic-profile',
                       'ZEROSIS_PLAY_ACTION_INFO_PANEL': 'old', 'ZEROSIS_PLAY_NOTIFICATION_PANEL': 'old'}
        self.parent_before = copy.deepcopy(self.parent)

    def document(self, policy, *, legacy=False):
        names = set(self.driver.SUPPORT) | {'interactive_ui_driver.py'}
        if not legacy:
            names.add('found_value_runtime_options.py')
        document = {'tools': {name: self.driver.artifact(TOOLS / name) for name in sorted(names)}}
        if not legacy:
            document[FIELD] = copy.deepcopy(policy)
        return document

    def write_manifest(self, document):
        self.manifest.write_text(json.dumps(document), encoding='utf8')
        return hashlib.sha256(self.manifest.read_bytes()).hexdigest()

    def drive(self, document, flag, *, manifest_sha=None):
        digest = self.write_manifest(document)
        return self.driver.drive(['NEVER_EXECUTE_HOST'], cwd=self.folder, runtime=self.folder,
                                 tools_dir=TOOLS, icons_source=self.folder,
                                 support_manifest=self.manifest, support_manifest_sha256=manifest_sha or digest,
                                 timeout=0, scene_timeout=1, report_path=self.folder / 'must-not-exist.json',
                                 top_panel=True, action_info_panel=True, notification_panel=True,
                                 found_value_workers=flag)

    def capture_child(self, document, flag, expected):
        def intercepted(command, **kwargs):
            self.assertEqual(command, ['NEVER_EXECUTE_HOST'])
            env = kwargs['env']
            self.assertIsNot(env, self.parent)
            self.assertEqual(env['ZEROSIS_FOUND_VALUE_WORKERS'], str(expected))
            self.assertEqual({key.upper() for key in env if key.upper() in self.api.ENVIRONMENT_NAMES},
                             {'ZEROSIS_FOUND_VALUE_WORKERS'})
            self.assertEqual(env['KEEP'], 'synthetic-parent')
            self.assertNotIn('ZEROSIS_UI_WINDOW_PROFILE', env)
            self.assertEqual(env['ZEROSIS_UI_SMALL_ASSETS'], '1')
            for name in ('ZEROSIS_PLAY_TOP_PANEL', 'ZEROSIS_PLAY_ACTION_INFO_PANEL', 'ZEROSIS_PLAY_NOTIFICATION_PANEL'):
                self.assertEqual(env[name], '1')
            self.assertEqual(self.parent, self.parent_before)
            CONTROLLED_CHILDREN.append({'workers': expected, 'parent_unchanged': True,
                                        'initial_environment_traces_removed': True,
                                        'actual_driver_before_native_call': True})
            raise ControlledStop()

        with patch.object(self.driver.os, 'environ', self.parent), \
                patch.object(self.driver.subprocess, 'Popen', side_effect=intercepted) as popen:
            with self.assertRaises(ControlledStop):
                self.drive(document, flag)
        self.assertEqual(popen.call_count, 1)
        self.assertEqual(self.parent, self.parent_before)
        self.assertFalse((self.folder / 'must-not-exist.json').exists())

    def reject_before_child(self, document, flag, *, manifest_sha=None):
        with patch.object(self.driver.os, 'environ', self.parent), \
                patch.object(self.driver.subprocess, 'Popen', side_effect=AssertionError('Rejected policy reached native boundary')) as popen:
            with self.assertRaises((ValueError, RuntimeError, OSError)):
                self.drive(document, flag, manifest_sha=manifest_sha)
        self.assertEqual(popen.call_count, 0)
        self.assertEqual(self.parent, self.parent_before)

    def test_real_driver_passes_exact_sealed_initial_environment(self):
        for requested, hint, source, count in (('auto', 3, 'cpu_count', 2), ('auto', 8, 'cpu_count', 4),
                                              ('0', None, 'unavailable', 0), ('1', None, 'unavailable', 1)):
            with self.subTest(requested=requested, hint=hint):
                policy = self.api.resolve_policy(requested, hint, source)
                self.capture_child(self.document(policy), str(count), count)

    def test_real_driver_missing_legacy_profile_is_always_scalar_zero(self):
        document = self.document(None, legacy=True)
        for flag in (None, '0'):
            self.capture_child(document, flag, 0)
        for flag in ('1', '2', '4', 'auto', True, 0):
            self.reject_before_child(document, flag)

    def test_real_driver_rejects_missing_or_different_resolved_flag(self):
        document = self.document(self.api.resolve_policy('auto', 3, 'cpu_count'))
        for flag in (None, '0', '1', '4', 'auto', '02', ' 2', True, 2):
            with self.subTest(flag=repr(flag)):
                self.reject_before_child(document, flag)

    def test_real_driver_present_null_and_malformed_policy_are_not_legacy(self):
        for policy in (None, {}, False, {'resolved_workers': 0}):
            with self.subTest(policy=repr(policy)):
                self.reject_before_child(self.document(policy), '0')
        forged = self.api.resolve_policy('2')
        forged['trace_enabled'] = True
        self.reject_before_child(self.document(forged), '2')

    def test_real_driver_rejects_manifest_hash_and_exact_tool_set_mismatches(self):
        document = self.document(self.api.resolve_policy('2'))
        self.reject_before_child(document, '2', manifest_sha='0' * 64)
        for removed in ('found_value_runtime_options.py', 'interactive_ui_driver.py', 'render_ui_popup.py'):
            candidate = copy.deepcopy(document)
            del candidate['tools'][removed]
            self.reject_before_child(candidate, '2')
        candidate = copy.deepcopy(document)
        candidate['tools']['unexpected.py'] = {}
        self.reject_before_child(candidate, '2')
        legacy = self.document(None, legacy=True)
        legacy['tools']['found_value_runtime_options.py'] = document['tools']['found_value_runtime_options.py']
        self.reject_before_child(legacy, None)

    def test_real_driver_rejects_helper_and_driver_file_identity_mismatches(self):
        document = self.document(self.api.resolve_policy('2'))
        for name in ('found_value_runtime_options.py', 'interactive_ui_driver.py'):
            for field, value in (('sha256', '0' * 64), ('bytes', True),
                                  ('path', str(TOOLS / 'civ5_ui_assets.py'))):
                candidate = copy.deepcopy(document)
                candidate['tools'][name][field] = value
                with self.subTest(name=name, field=field):
                    self.reject_before_child(candidate, '2')

    def test_real_driver_rejects_loaded_module_bytes_outside_the_sealed_identity(self):
        document = self.document(self.api.resolve_policy('2'))
        different = self.folder / 'different_loaded_source.py'
        different.write_text('# Deliberately different synthetic loaded source.\n', encoding='utf8')
        for module in (self.driver, self.driver.worker_options):
            with patch.object(module, '__file__', str(different)):
                self.reject_before_child(document, '2')


if __name__ == '__main__':
    unittest.main()
