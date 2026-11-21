"""Headless regression tests for retained Host inputs and private PolicyInfo INIs."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


PROJECT = Path(__file__).resolve().parents[1]
RUNNER_PATH = PROJECT / 'tools' / 'run_interactive_game.py'
sys.path.insert(0, str(RUNNER_PATH.parent))
spec = importlib.util.spec_from_file_location('host_runtime_inputs_runner', RUNNER_PATH)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)

BUILD_ID = '20261016T120000Z_012345abcdef'
TRANSLATION_UNITS = (
    ('host_main', 'HostMain'),
    ('window', 'BitmapWindow'),
    ('renderer', 'BitmapRenderer'),
    ('world_renderer', 'WorldViewRenderer'),
    ('terrain_renderer', 'WorldTerrainRenderer'),
)
REJECTION_ERRORS = (RuntimeError, OSError)


class HostRuntimeInputTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='host_runtime_inputs_test_', dir=PROJECT)
        self.addCleanup(temporary.cleanup)
        self.fixture = Path(temporary.name).resolve(strict=True)
        self.host_root = self.fixture / 'Build' / 'UiWindowHost' / BUILD_ID
        self.retained = {}
        self.object_bytes = {}
        self.build = self.make_build()
        project_patch = mock.patch.object(runner, 'PROJECT', self.fixture)
        project_patch.start()
        self.addCleanup(project_patch.stop)

    def write_artifact(self, relative, label):
        path = self.host_root / relative
        payload = ('headless fixture: ' + label + '\n').encode('utf8')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        return {'path': str(path), 'sha256': hashlib.sha256(payload).hexdigest()}

    def keep(self, relative, label):
        row = self.write_artifact(relative, label)
        self.retained[label] = row
        return row

    def make_build(self):
        discovery = []
        final = []
        sources = []
        for index, (name, stem) in enumerate(TRANSLATION_UNITS):
            unit_dir = Path('dependency_discovery') / f'tu_{index:02d}_{name}'
            obj = self.write_artifact(unit_dir / 'obj' / f'{stem}.obj', name + ' discovery object')
            self.object_bytes[obj['path']] = Path(obj['path']).read_bytes()
            discovery.append({
                'translation_unit': name,
                'returncode': 0,
                'objects': [obj],
                'response': self.keep(unit_dir / f'{name}.compile.rsp', name + ' discovery rsp'),
                'log': self.keep(Path('logs') / f'discovery_{name}.log', name + ' discovery log'),
                'dependency_report': self.keep(unit_dir / f'{name}.sourceDependencies.json',
                                               name + ' discovery dependencies'),
            })
            final_dir = Path('final') / f'tu_{index:02d}_{name}'
            final.append({
                'translation_unit': name,
                'returncode': 0,
                'response': self.keep(final_dir / f'{name}.compile.rsp', name + ' final rsp'),
                'log': self.keep(Path('logs') / f'compile_{name}.log', name + ' final log'),
                'dependency_report': self.keep(final_dir / f'{name}.sourceDependencies.json',
                                               name + ' final dependencies'),
            })
            sources.append(self.keep(Path('frozen_inputs') / 'Source' / f'{stem}.cpp',
                                     name + ' frozen source'))
        return {
            'schema': 'zerosis.ui_window_host_build.v1',
            'build_id': BUILD_ID,
            'status': 'UI_WINDOW_HOST_CANDIDATE_BUILT',
            'source_inputs_unchanged': True,
            'provider_inputs_unchanged': True,
            'error': None,
            'executable': self.keep(Path('final') / 'ZeroSisHost_x64.exe', 'executable'),
            'sources': sources,
            'libraries': [self.keep(Path('frozen_inputs') / 'lib' / 'provider.lib', 'library')],
            'compiler_inputs': [self.keep(Path('frozen_inputs') / 'include' / 'fixture.h',
                                          'frozen dependency')],
            'compile_log': self.keep(Path('logs') / 'compile.log', 'compile log'),
            'link_log': self.keep(Path('logs') / 'link.log', 'link log'),
            'link_response': self.keep(Path('final') / 'link.rsp', 'link rsp'),
            'dependency_discovery': {'translation_units': discovery},
            'final_compilation': {'translation_units': final},
        }

    def discovery_objects(self):
        return [unit['objects'][0]
                for unit in self.build['dependency_discovery']['translation_units']]

    def retire_objects(self, indices=range(5)):
        objects = self.discovery_objects()
        for index in indices:
            Path(objects[index]['path']).unlink()

    def check(self, build=None):
        if build is None:
            build = self.build
        original = copy.deepcopy(build)
        try:
            return runner.check_host_runtime_artifacts(build)
        finally:
            self.assertEqual(original, build, 'Runtime validation mutated the sealed build record')

    def test_complete_build_checks_all_artifacts(self):
        self.assertEqual({
            'scope': 'RETAINED_HOST_RUNTIME_INPUTS', 'absent_discovery_objects': [],
        }, self.check())

    def test_exact_five_retired_objects_are_recorded_without_mutating_build(self):
        objects = copy.deepcopy(self.discovery_objects())
        self.retire_objects()
        result = self.check()
        self.assertEqual('RETAINED_HOST_RUNTIME_INPUTS', result['scope'])
        self.assertEqual([
            {'original_path': row['path'], 'sha256': row['sha256']} for row in objects
        ], result['absent_discovery_objects'])
        for annotation in result['absent_discovery_objects']:
            self.assertEqual({'original_path', 'sha256'}, set(annotation))
        request = {'host_runtime_validation': result, 'host_executable': self.build['executable']}
        runner.check_artifacts(request)
        with self.assertRaises(RuntimeError):
            runner.check_artifacts(self.build)

    def test_each_single_retired_object_is_accepted(self):
        for index, row in enumerate(self.discovery_objects()):
            with self.subTest(translation_unit=TRANSLATION_UNITS[index][0]):
                path = Path(row['path'])
                path.unlink()
                try:
                    self.assertEqual([
                        {'original_path': row['path'], 'sha256': row['sha256']}
                    ], self.check()['absent_discovery_objects'])
                finally:
                    path.write_bytes(self.object_bytes[row['path']])

    def test_present_changed_object_is_rejected_on_both_validation_paths(self):
        changed = Path(self.discovery_objects()[1]['path'])
        changed.write_bytes(b'changed discovery object\n')
        for retire_first in (False, True):
            with self.subTest(other_object_retired=retire_first):
                if retire_first:
                    self.retire_objects((0,))
                with self.assertRaises(RuntimeError):
                    self.check()

    def test_missing_retained_artifacts_are_rejected_on_both_validation_paths(self):
        for retire_objects in (False, True):
            if retire_objects:
                self.retire_objects()
            for label, row in self.retained.items():
                with self.subTest(retired=retire_objects, retained_artifact=label):
                    path = Path(row['path'])
                    payload = path.read_bytes()
                    path.unlink()
                    try:
                        with self.assertRaises(REJECTION_ERRORS):
                            self.check()
                    finally:
                        path.write_bytes(payload)

    def test_changed_retained_artifacts_are_rejected_on_both_validation_paths(self):
        for retire_objects in (False, True):
            if retire_objects:
                self.retire_objects()
            for label, row in self.retained.items():
                with self.subTest(retired=retire_objects, retained_artifact=label):
                    path = Path(row['path'])
                    payload = path.read_bytes()
                    path.write_bytes(payload + b'changed\n')
                    try:
                        with self.assertRaises(RuntimeError):
                            self.check()
                    finally:
                        path.write_bytes(payload)

    def test_retired_objects_require_successful_sealed_schema(self):
        self.retire_objects()
        cases = (
            ('schema', 'zerosis.ui_window_host_build.v2'),
            ('build_id', 'not-a-build-id'),
            ('status', 'UI_WINDOW_HOST_CANDIDATE_FAILED'),
            ('source_inputs_unchanged', False),
            ('source_inputs_unchanged', 1),
            ('provider_inputs_unchanged', False),
            ('provider_inputs_unchanged', 1),
            ('error', 'compile failed'),
        )
        for field, value in cases:
            with self.subTest(field=field, value=value):
                build = copy.deepcopy(self.build)
                build[field] = value
                with self.assertRaises(RuntimeError):
                    self.check(build)

    def test_unexpected_translation_unit_name_order_or_count_is_rejected(self):
        self.retire_objects()
        for phase in ('dependency_discovery', 'final_compilation'):
            for change in ('name', 'order', 'missing', 'extra'):
                with self.subTest(phase=phase, change=change):
                    build = copy.deepcopy(self.build)
                    units = build[phase]['translation_units']
                    if change == 'name':
                        units[0]['translation_unit'] = 'unexpected'
                    elif change == 'order':
                        units[0], units[1] = units[1], units[0]
                    elif change == 'missing':
                        units.pop()
                    else:
                        units.append(copy.deepcopy(units[-1]))
                    with self.assertRaises(RuntimeError):
                        self.check(build)

    def test_nonzero_and_noninteger_translation_unit_returncodes_are_rejected(self):
        self.retire_objects()
        for phase in ('dependency_discovery', 'final_compilation'):
            for code in (1, -1, '0', False, True, 0.0, None):
                with self.subTest(phase=phase, returncode=repr(code)):
                    build = copy.deepcopy(self.build)
                    build[phase]['translation_units'][0]['returncode'] = code
                    with self.assertRaises(RuntimeError):
                        self.check(build)

    def test_exact_single_discovery_object_per_unit_is_required(self):
        self.retire_objects()
        for count in (0, 2):
            with self.subTest(object_count=count):
                build = copy.deepcopy(self.build)
                unit = build['dependency_discovery']['translation_units'][0]
                unit['objects'] = unit['objects'] * count
                with self.assertRaises(RuntimeError):
                    self.check(build)

    def test_unexpected_discovery_object_paths_are_rejected(self):
        self.retire_objects()
        expected = Path(self.discovery_objects()[0]['path'])
        candidates = (
            self.fixture / 'other_build' / 'HostMain.obj',
            expected.parent / 'Other.obj',
            self.host_root / 'dependency_discovery' / 'tu_99_host_main' / 'obj' / 'HostMain.obj',
            Path('dependency_discovery') / 'tu_00_host_main' / 'obj' / 'HostMain.obj',
        )
        for path in candidates:
            with self.subTest(path=str(path)):
                build = copy.deepcopy(self.build)
                build['dependency_discovery']['translation_units'][0]['objects'][0]['path'] = str(path)
                with self.assertRaises(RuntimeError):
                    self.check(build)

    def test_object_hash_and_annotation_shape_remain_strict(self):
        self.retire_objects()
        for change in ('short_hash', 'uppercase_hash', 'extra_field', 'missing_hash'):
            with self.subTest(change=change):
                build = copy.deepcopy(self.build)
                row = build['dependency_discovery']['translation_units'][0]['objects'][0]
                if change == 'short_hash':
                    row['sha256'] = 'a' * 63
                elif change == 'uppercase_hash':
                    row['sha256'] = 'A' * 64
                elif change == 'extra_field':
                    row['historical'] = True
                else:
                    del row['sha256']
                with self.assertRaises(RuntimeError):
                    self.check(build)

    def test_other_build_executable_cannot_authorize_retired_objects(self):
        self.retire_objects()
        executable = self.fixture / 'other_build.exe'
        payload = Path(self.build['executable']['path']).read_bytes()
        executable.write_bytes(payload)
        self.build['executable']['path'] = str(executable)
        with self.assertRaises(RuntimeError):
            self.check()

    def test_directory_discovery_entry_is_rejected_on_both_validation_paths(self):
        directory = Path(self.discovery_objects()[1]['path'])
        directory.unlink()
        directory.mkdir()
        for retire_first in (False, True):
            with self.subTest(other_object_retired=retire_first):
                if retire_first:
                    self.retire_objects((0,))
                with self.assertRaises(RuntimeError):
                    self.check()

    def test_dangling_discovery_entry_is_not_retired(self):
        path = Path(self.discovery_objects()[1]['path'])
        path.unlink()
        lexists = runner.os.path.lexists
        # Model the dangling-link distinction without requiring symlink privileges.
        def dangling_lexists(value):
            return True if Path(value) == path else lexists(value)

        with mock.patch.object(runner.os.path, 'lexists', side_effect=dangling_lexists):
            for retire_first in (False, True):
                with self.subTest(other_object_retired=retire_first):
                    if retire_first:
                        self.retire_objects((0,))
                    with self.assertRaises(RuntimeError):
                        self.check()

    def test_retained_artifact_directory_is_rejected(self):
        self.retire_objects()
        path = Path(self.build['libraries'][0]['path'])
        path.unlink()
        path.mkdir()
        with self.assertRaises(RuntimeError):
            self.check()


class PolicyInfoInputTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='host_runtime_inputs_test_', dir=PROJECT)
        self.addCleanup(temporary.cleanup)
        self.fixture = Path(temporary.name).resolve(strict=True)
        self.private_ini = self.fixture / 'private-policy.ini'

    def test_explicit_private_ini_reports_value_origin_and_hash_without_writing(self):
        for value in (0, 1):
            with self.subTest(policy_info=value):
                payload = b'\xef\xbb\xbf[Interface]\r\nPolicyInfo = ' + str(value).encode('ascii') + b'\r\n'
                self.private_ini.write_bytes(payload)
                before_stat = self.private_ini.stat()
                result = runner.read_policy_info_options(None, self.private_ini)
                self.assertEqual(value, result['policy_info'])
                self.assertEqual('EXPLICIT_POLICY_SETTINGS_READ_ONLY', result['origin'])
                expected = {
                    'original_path': str(self.private_ini.resolve(strict=True)),
                    'sha256': hashlib.sha256(payload).hexdigest(), 'bytes': len(payload),
                }
                self.assertEqual(expected, result['source'])
                self.assertEqual(expected, result['settings_input'])
                self.assertIsNone(result['original_user_settings'])
                self.assertIsNone(result['original_policy_info'])
                self.assertIsNone(result['run_id'])
                self.assertEqual(payload, self.private_ini.read_bytes())
                self.assertEqual(before_stat.st_mtime_ns, self.private_ini.stat().st_mtime_ns)
                runner.check_artifacts({'policy_info_options': result})

    def test_default_route_is_fully_mocked_and_preserves_original_provenance(self):
        payload = b'[Interface]\nPolicyInfo = 1\n'
        settings = mock.Mock(spec=Path)
        settings.read_bytes.return_value = payload
        annotation = {'original_path': 'mock-only-default-settings',
                      'sha256': hashlib.sha256(payload).hexdigest(), 'bytes': len(payload)}
        with mock.patch.object(runner, 'Path', return_value=settings) as constructor, \
                mock.patch.object(runner, 'source_annotation', return_value=annotation) as source:
            result = runner.read_policy_info_options(None)
        constructor.assert_called_once_with(
            r"C:\Users\home\OneDrive\Documents\My Games\Sid Meier's Civilization 5\UserSettings.ini")
        settings.read_bytes.assert_called_once_with()
        source.assert_called_once_with(settings)
        self.assertEqual(1, result['policy_info'])
        self.assertEqual('ORIGINAL_USER_SETTINGS_READ_ONLY', result['origin'])
        self.assertEqual(annotation, result['original_user_settings'])
        self.assertEqual(annotation, result['settings_input'])
        self.assertEqual(1, result['original_policy_info'])

    def test_private_ini_requires_exactly_one_valid_policy_info(self):
        for payload in (b'[Interface]\n', b'PolicyInfo = 2\n',
                        b'PolicyInfo = 0\nPolicyInfo = 1\n', b'PolicyInfo = true\n'):
            with self.subTest(payload=payload):
                self.private_ini.write_bytes(payload)
                with self.assertRaises(RuntimeError):
                    runner.read_policy_info_options(None, self.private_ini)
                self.assertEqual(payload, self.private_ini.read_bytes())

    def test_changed_private_ini_annotation_is_rejected(self):
        self.private_ini.write_bytes(b'PolicyInfo = 1\n')
        with mock.patch.object(runner, 'source_annotation', return_value={'sha256': '0' * 64}):
            with self.assertRaises(RuntimeError):
                runner.read_policy_info_options(None, self.private_ini)


if __name__ == '__main__':
    unittest.main()
