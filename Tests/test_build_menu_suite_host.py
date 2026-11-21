"""Pure planning regressions. No compiler, Host, SDK, DLL or UI is executed."""
from __future__ import annotations

import ast
import json
import struct
import types
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


sys.dont_write_bytecode = True
PROJECT = Path(__file__).absolute().parents[1]
sys.path.insert(0, str(PROJECT / 'tools'))
import build_menu_suite_host as builder


class CurrentMenuHostPlannerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.parent = json.loads(builder.PARENT_REPORT.read_bytes())

    def test_include_roots_are_derived_from_actual_manifest_coordinates(self):
        roots = builder.input_root_map(self.parent)
        self.assertEqual(builder.common.key(roots['project'][1]), builder.common.key(PROJECT))
        self.assertGreater(len(roots), 1)
        for row in self.parent['compiler_inputs']:
            frozen, actual = roots[row['root_name']]
            self.assertEqual(builder.common.key(Path(frozen) / row['relative_path']), builder.common.key(row['path']))
            self.assertEqual(builder.common.key(Path(actual) / row['relative_path']), builder.common.key(row['original_path']))

    def test_actual_authenticated_loader_modules_and_coff_directive_return_shapes(self):
        parser, pure, references = builder.load_helpers()
        self.assertIsInstance(parser, types.ModuleType)
        self.assertIsInstance(pure, types.ModuleType)
        self.assertEqual(references['parser']['sha256'], builder.PARSER_SHA)
        self.assertEqual(references['object_helpers']['sha256'], builder.PURE_HELPER_SHA)
        directives = b' /DEFAULTLIB:"msvcrt" /DEFAULTLIB:ucrt.lib '
        raw = bytearray(60 + len(directives))
        struct.pack_into('<HHIIIHH', raw, 0, 0x8664, 1, 0, 0, 0, 0, 0)
        raw[20:28] = b'.drectve'
        struct.pack_into('<IIIIHHI', raw, 36, len(directives), 60, 0, 0, 0, 0, 0x00100a00)
        raw[60:] = directives
        actual = parser.coff(bytes(raw))
        self.assertIsInstance(actual, dict)
        self.assertEqual(actual['machine_hex'], '0x8664')
        self.assertEqual(actual['section_count'], 1)
        self.assertEqual(pure.object_defaults(bytes(raw)), ['msvcrt.lib', 'ucrt.lib'])

    def test_actual_retained_pe_import_catalog_and_summary_api_shapes_agree(self):
        parser, pure, _ = builder.load_helpers()
        generated = next(row for row in self.parent['compiler_inputs']
                         if Path(row['original_path']).name.casefold() == 'uipopupassets.generated.h')
        arrays, order = builder.menu.parse_catalog(builder.common.read_bytes(generated), self.parent['catalog']['entry_count'], ('ZeroSisUiScene', 'ExitConfirm'))
        data = builder.common.read_bytes(self.parent['executable'])
        original, current = parser.PE(data), builder.menu.PE(data)
        self.assertEqual(pure.catalog_summary(original.catalog(arrays, order)), self.parent['catalog'])
        self.assertEqual(current.catalog(arrays, order), self.parent['catalog'])
        self.assertEqual(original.imports(), current.imports())
        self.assertEqual(current.imports(), self.parent['imports']['dependencies'])
        self.assertEqual(len(current.occurrences(builder.menu.MARKER)), 1)

    def test_syntax_discovery_uses_current_roots_without_old_objects_or_counts(self):
        roots = builder.input_root_map(self.parent)
        for unit in self.parent['final_compilation']['translation_units']:
            with self.subTest(unit=unit['translation_unit']):
                dependency = PROJECT / 'Build/UnusedPureFixture' / (unit['translation_unit'] + '.json')
                response = builder.discovery_response(Path(unit['response']['path']).read_bytes(), roots, dependency).decode('utf-8')
                self.assertNotIn(str(builder.PARENT_ROOT), response)
                self.assertNotIn(builder.PARENT_ROOT.as_posix(), response)
                self.assertEqual(response.splitlines().count('/Zs'), 1)
                self.assertNotIn('/c', response.splitlines())
                self.assertFalse(any(line.casefold().startswith('/fo') for line in response.splitlines()))
                self.assertIn('/sourceDependencies "' + str(dependency) + '"', response)

    def test_case_preserving_windows_and_posix_paths_are_relocated(self):
        source = builder.PARENT_ROOT / 'frozen/include_roots/project'
        text = '"' + str(source / 'Source/Host/HostMain.cpp') + '"\n/I"' + source.as_posix() + '/Source/Host"'
        value = builder.replace_paths(text, [(source, PROJECT)])
        self.assertIn(str(PROJECT / 'Source/Host/HostMain.cpp'), value)
        self.assertNotIn(str(builder.PARENT_ROOT), value)

    def test_nested_project_sdk_and_system_targets_are_relocated_exactly_once(self):
        root = PROJECT / 'Build/UiWindowHost/pure_regression'
        sdk = PROJECT / 'Source/SDK_BNW_x64'
        system = Path(r'C:\Program Files\ExampleToolchain\include')
        pairs = [(PROJECT, root / 'frozen/include_roots/project'),
                 (sdk, root / 'frozen/include_roots/sdk'),
                 (system, root / 'frozen/include_roots/system_00')]
        text = '\n'.join(['/external:I"' + str(sdk / 'CvGameCoreDLL_Expansion2') + '"',
                          '/I"' + str(system) + '"',
                          '"' + str(PROJECT / 'Source/Host/HostMain.cpp') + '"'])
        actual = builder.replace_paths(text, pairs)
        self.assertEqual(actual.splitlines(), [
            '/external:I"' + str(root / 'frozen/include_roots/sdk/CvGameCoreDLL_Expansion2') + '"',
            '/I"' + str(root / 'frozen/include_roots/system_00') + '"',
            '"' + str(root / 'frozen/include_roots/project/Source/Host/HostMain.cpp') + '"'])

    def test_all_five_real_discovery_recipes_keep_direct_sdk_and_system_frozen_roots(self):
        roots = builder.input_root_map(self.parent)
        root = PROJECT / 'Build/UiWindowHost/pure_regression'
        pairs = [(actual, root / 'frozen/include_roots' / name) for name, (_, actual) in roots.items()]
        for unit in self.parent['final_compilation']['translation_units']:
            with self.subTest(unit=unit['translation_unit']):
                discovery = builder.discovery_response(Path(unit['response']['path']).read_bytes(), roots,
                    PROJECT / 'Build/pure_discovery.json').decode('utf-8')
                lines = [line for line in discovery.splitlines() if not line.startswith('/sourceDependencies')]
                frozen = builder.replace_paths('\n'.join(lines), pairs)
                self.assertIn('/external:I"' + str(root / 'frozen/include_roots/sdk/CvGameCoreDLL_Expansion2') + '"', frozen)
                for index in range(len(self.parent['system_include_roots'])):
                    self.assertIn('/I"' + str(root / ('frozen/include_roots/system_%02d' % index)) + '"', frozen)
                self.assertNotIn(str(root / 'frozen/include_roots/project/Build/UiWindowHost'), frozen)

    def test_conflicting_include_roots_are_rejected(self):
        row = dict(self.parent['compiler_inputs'][0])
        conflicting = dict(row, original_path=str(PROJECT / 'outside/HostMain.cpp'))
        with self.assertRaisesRegex(RuntimeError, 'Conflicting'):
            builder.input_root_map(dict(compiler_inputs=[row, conflicting]))

    def test_a_direct_native_launch_needs_the_exact_pending_toolchain_command(self):
        guard = object.__new__(builder.BuildGuard)
        guard.denied, guard.pending = [], None
        with self.assertRaises(PermissionError):
            guard.audit('subprocess.Popen', ('unused.exe', ['unused.exe'], str(PROJECT), None))
        self.assertEqual(guard.denied[0]['event'], 'subprocess.Popen')

    def test_native_module_state_and_network_events_are_forbidden(self):
        for event in ('ctypes.dlopen', 'sqlite3.connect', 'winreg.OpenKey', 'socket.connect', 'os.startfile'):
            with self.subTest(event=event):
                guard = object.__new__(builder.BuildGuard)
                guard.denied = []
                with self.assertRaises(PermissionError):
                    guard.audit(event, ('unused sentinel',))
                self.assertEqual(guard.denied[0]['event'], event)

    def test_build_does_not_read_old_fixed_dependency_or_replaced_source_lists(self):
        tree = ast.parse(Path(builder.__file__).read_text(encoding='utf-8'))
        self.assertFalse(any(isinstance(node, ast.Attribute) and node.attr in ('COUNTS', 'REPLACED', 'ASSETS', 'ADDENDA')
                             for node in ast.walk(tree)))
        self.assertFalse(any(isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and
                             node.func.attr in ('main', 'parser69', 'prepare_plan') for node in ast.walk(tree)))

    def test_source_inventory_allows_project_revision_but_rejects_changed_external_toolchain(self):
        temporary = tempfile.TemporaryDirectory(prefix='_menu_planner_sources_', dir=PROJECT)
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        project, external = root / 'project', root / 'external'
        (project / 'tools').mkdir(parents=True)
        external.mkdir()
        own = project / 'Source/Host/Fixture.h'
        own.parent.mkdir(parents=True)
        own.write_bytes(b'// old current source\n')
        outside = external / 'FixtureCompiler.h'
        outside.write_bytes(b'// fixed external toolchain\n')
        old = dict(current_source_inputs=[builder.common.artifact(own), builder.common.artifact(outside)])
        (project / 'tools/retained_menu_suite_host_input.py').write_bytes(b'# inert format helper fixture\n')
        own.write_bytes(b'// changed current source\n')
        with mock.patch.object(builder, 'PROJECT', project), mock.patch.object(builder, '__file__', str(project / 'tools/build_menu_suite_host.py')):
            (project / 'tools/build_menu_suite_host.py').write_bytes(b'# inert builder fixture\n')
            self.assertEqual(len(builder.source_inventory(old, [])), 4)
            outside.write_bytes(b'// changed external toolchain\n')
            with self.assertRaisesRegex(RuntimeError, 'External compiler/SDK input changed'):
                builder.source_inventory(old, [])


if __name__ == '__main__':
    unittest.main()
