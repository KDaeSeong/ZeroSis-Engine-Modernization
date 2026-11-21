"""File-only menu Host regressions; no Host, SDK, DLL, window or GPU is run.

Miniature private files exercise the source and retirement boundaries. They do
not claim a native runtime or UI result. Current production sources may change
while these tests run: assertions use the fixture's sealed closure exclusively.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest import mock


sys.dont_write_bytecode = True
PROJECT = Path(__file__).absolute().parents[1]
sys.path.insert(0, str(PROJECT / 'tools'))
import prepare_latest_engine_pair as preparer
import retained_host_runtime_input as retained
import retained_menu_suite_host_input as menu


def reference(path, payload=None):
    path = Path(path).absolute()
    payload = path.read_bytes() if payload is None else payload
    return dict(path=str(path), bytes=len(payload), sha256=hashlib.sha256(payload).hexdigest())


def header(payloads):
    raw = bytearray()
    for name, payload in payloads:
        raw += ('static const char %s[]=\n' % name).encode('ascii')
        chunks = [payload[index:index + 64] for index in range(0, len(payload), 64)] or [b'']
        for index, chunk in enumerate(chunks):
            raw += b'"' + b''.join(('\\x%02x' % value).encode('ascii') for value in chunk) + b'"'
            raw += b';\n' if index == len(chunks) - 1 else b'\n'
    raw += b'static const Script scripts[]={\n'
    for name, _ in payloads:
        raw += ('{"%s",%s,sizeof(%s)-1},\n' % (name, name, name)).encode('ascii')
    return bytes(raw + b'};\n')


def pe_fixture(payloads):
    """Inert PE bytes with a real source/name/size table in readonly data."""
    raw = bytearray(8192)
    raw[:2] = b'MZ'
    struct.pack_into('<I', raw, 0x3c, 128)
    raw[128:132] = b'PE\0\0'
    struct.pack_into('<HHIIIHH', raw, 132, 0x8664, 1, 0, 0, 0, 240, 0x22)
    optional, imagebase, section_rva, section_raw = 152, 0x140000000, 0x1000, 512
    struct.pack_into('<H', raw, optional, 0x20b)
    struct.pack_into('<Q', raw, optional + 24, imagebase)
    struct.pack_into('<I', raw, optional + 108, 16)
    struct.pack_into('<II', raw, optional + 120, section_rva, 40)
    section = optional + 240
    raw[section:section + 8] = b'.rdata\0\0'
    struct.pack_into('<IIII', raw, section + 8, len(raw) - section_raw, section_rva, len(raw) - section_raw, section_raw)
    struct.pack_into('<I', raw, section + 36, 0x40000040)
    struct.pack_into('<5I', raw, section_raw, 0, 0, 0, section_rva + 64, 0)
    raw[section_raw + 64:section_raw + 77] = b'kernel32.dll\0'
    marker_at = section_raw + 96
    raw[marker_at:marker_at + len(menu.MARKER)] = menu.MARKER
    table_at, cursor = section_raw + 256, section_raw + 256 + len(payloads) * 24
    for index, (name, payload) in enumerate(payloads):
        encoded = name.encode('ascii') + b'\0'
        name_rva = section_rva + cursor - section_raw
        raw[cursor:cursor + len(encoded)] = encoded
        cursor += len(encoded)
        data_rva = section_rva + cursor - section_raw
        raw[cursor:cursor + len(payload) + 1] = payload + b'\0'
        cursor += len(payload) + 1
        struct.pack_into('<QQQ', raw, table_at + index * 24, imagebase + name_rva, imagebase + data_rva, len(payload))
    return bytes(raw)


class PrivateFiles(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='_menu_host_file_gate_', dir=PROJECT)
        self.addCleanup(temporary.cleanup)
        self.project = Path(temporary.name).absolute()

    def write(self, relative, raw):
        path = self.project / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        return reference(path)

    def document(self, relative, value):
        return self.write(relative, (json.dumps(value, sort_keys=True) + '\n').encode('ascii'))


class CatalogTests(unittest.TestCase):
    def payloads(self, count):
        return [('ZeroSisUiScene', b'-- frozen scene\n'), ('ExitConfirm', b'-- original exit\n'),
                ('ExitConfirmLayout', b'<Context/>')] + [('Payload%d' % index, b'-- %d\n' % index)
                                                      for index in range(count - 3)]

    def test_real_dynamic_counts_do_not_need_a_67_entry_parser_adapter(self):
        for count in (69, 71):
            with self.subTest(count=count):
                payloads = self.payloads(count)
                arrays, order = menu.parse_catalog(header(payloads), count, ('ExitConfirm', 'ExitConfirmLayout'))
                self.assertEqual(list(arrays), order)
                self.assertEqual(len(order), count)

    def test_a_sealed_69_entry_catalog_rejects_an_old_67_count(self):
        with self.assertRaisesRegex(RuntimeError, 'sealed count'):
            menu.parse_catalog(header(self.payloads(69)), 67, ('ExitConfirm',))

    def test_duplicate_registry_and_nul_payloads_are_rejected(self):
        for raw in (header(self.payloads(3)) + b'static const Script scripts[]={\n};\n',
                    header([('ZeroSisUiScene', b'x\0y'), *self.payloads(3)[1:]])):
            with self.subTest(size=len(raw)), self.assertRaises(RuntimeError):
                menu.parse_catalog(raw, 3, ('ExitConfirm',))

    def test_file_backed_pe_reads_actual_catalog_and_imports(self):
        payloads = self.payloads(3)
        pe = menu.PE(pe_fixture(payloads))
        self.assertEqual(pe.imports(), ['kernel32.dll'])
        self.assertEqual(len(pe.occurrences(menu.MARKER)), 1)
        arrays, order = menu.parse_catalog(header(payloads), 3, ('ExitConfirm',))
        actual = pe.catalog(arrays, order)
        self.assertEqual(actual['entry_count'], 3)
        self.assertEqual(actual['total_payload_bytes'], sum(len(raw) for _, raw in payloads))

    def test_payload_splicing_and_executable_data_are_rejected(self):
        payloads = self.payloads(3)
        arrays, order = menu.parse_catalog(header(payloads), 3, ('ExitConfirm',))
        raw = bytearray(pe_fixture(payloads))
        raw[raw.index(payloads[1][1])] ^= 1
        with self.assertRaisesRegex(RuntimeError, 'payload'):
            menu.PE(bytes(raw)).catalog(arrays, order)
        raw = bytearray(pe_fixture(payloads))
        struct.pack_into('<I', raw, 152 + 240 + 36, 0x60000040)
        with self.assertRaises(RuntimeError):
            menu.PE(bytes(raw)).catalog(arrays, order)


class SourceClosureTests(PrivateFiles):
    def fixture(self):
        current = self.write('Source/Host/UiScene.lua', b'-- current at publication\n')
        frozen = self.write('Build/UiWindowHost/fixture/frozen/project/Source/Host/UiScene.lua',
                            Path(current['path']).read_bytes())
        frozen.update(original_source=current['path'], original_path=str(self.project / 'Build/UiWindowHost/old/frozen/UiScene.lua'),
                      materialization='owned_changed_source_copy')
        build = dict(build_id='fixture', compiler_dependency_count=0, compiler_inputs=[], sources=[frozen],
                     provider_inputs=[], system_libraries=[], build_tools=[], implicit_libraries=[], provider_reports={},
                     shared_lua_build=frozen, ui_assets=frozen, current_source_inputs=[current])
        spec = dict(build_id='fixture', materialized_input_count=1, current_source_count=1, compiler_dependency_count=0,
                    source_manifest_count=1, donor_hardlinks=0, private_source_copies=1, nonfrozen_current_inputs=[])
        run = dict(materialized=[frozen], current_inputs=[current])
        return build, spec, run, current, frozen

    def test_donor_path_is_not_substituted_for_the_actual_lua_source(self):
        build, spec, run, current, frozen = self.fixture()
        _, _, _, aliases = menu._closure(build, self.project, spec, run, retained._Files(check_metadata=True))
        self.assertEqual(set(aliases), {menu.key(current['path'])})
        self.assertEqual(aliases[menu.key(current['path'])]['path'], frozen['path'])

    def test_frozen_closure_remains_valid_after_live_source_edit_but_latest_preflight_rejects_it(self):
        build, spec, run, current, _ = self.fixture()
        report = self.document('evidence/report.json', build)
        spec.update(report_path='evidence/report.json', report_sha256=report['sha256'])
        Path(current['path']).write_bytes(b'-- an explicitly later source revision\n')
        menu._closure(build, self.project, spec, run, retained._Files(check_metadata=True))
        with self.assertRaisesRegex(RuntimeError, 'Changed retained Host input'):
            menu.check_current_source_closure(build, self.project, spec, retained._Files(check_metadata=True))

    def test_frozen_content_change_is_not_waived_as_source_drift(self):
        build, spec, run, _, frozen = self.fixture()
        Path(frozen['path']).write_bytes(b'-- changed snapshot\n')
        with self.assertRaises(RuntimeError):
            menu._closure(build, self.project, spec, run, retained._Files(check_metadata=True))

    def test_unexplained_current_source_and_conflicting_source_alias_are_rejected(self):
        for alteration in ('extra', 'alias'):
            with self.subTest(alteration=alteration):
                build, spec, run, _, _ = self.fixture()
                if alteration == 'extra':
                    build['current_source_inputs'].append(self.write('Source/Host/Extra.h', b'// extra\n'))
                    spec['current_source_count'] = 2
                else:
                    build['sources'][0]['original_source'] = str(self.project / 'Source/Host/Other.lua')
                with self.assertRaises(RuntimeError):
                    menu._closure(build, self.project, spec, run, retained._Files(check_metadata=True))


class RetirementTests(PrivateFiles):
    def fixture(self):
        build_id = 'fixture'
        root = self.project / 'Build/UiWindowHost' / build_id
        image = self.write(root / 'final/ZeroSisHost_x64.exe', b'INERT_IMAGE_BYTES')
        units = []
        for index, (name, stem) in enumerate(zip(menu.TUS, menu.STEMS)):
            path = root / f'final/tu_{index:02d}_{name}/obj/{stem}.obj'
            units.append(dict(translation_unit=name, object=reference(path, b'historical object ' + name.encode('ascii'))))
        setup = reference(root / 'read_build_environment.cmd', b'historical environment')
        candidates = [unit['object'] for unit in units] + [setup]
        build = dict(build_id=build_id, executable=image, final_compilation=dict(translation_units=units))
        plan = dict(candidates=candidates, retained_current_executable=image, historical_object_refs_retired_after_verification=True)
        plan_ref = self.document('evidence/cleanup_plan.json', plan)
        result = dict(status='PASS_EXACT_CURRENT_BUILD_INTERMEDIATE_CLEANUP', files_deleted=6,
                      plan_sha256=plan_ref['sha256'], all_candidates_absent=True, current_image_unchanged=True,
                      protected_objects_or_sources_deleted=False, runtime_default_or_saves_deleted=False)
        result_ref = self.document('evidence/cleanup_result.json', result)
        report_ref = self.document('evidence/report.json', build)
        attestation_ref = self.document('evidence/attestation.json', dict(code_objects_checked=5, native_execution=False))
        refs = dict(report=report_ref, attestation=attestation_ref, cleanup_plan=plan_ref, cleanup_result=result_ref)
        ledger = dict(schema='zerosis.menu_host.typed_retirement.v1', build_id=build_id, native_execution=False,
                      historical_only=True, missing_input_exception_scope='EXACT_TYPED_SIX_INTERMEDIATES', **refs,
                      retired=[dict(**unit['object'], role='FINAL_COFF_OBJECT', translation_unit=unit['translation_unit']) for unit in units] +
                              [dict(**setup, role='BUILD_ENVIRONMENT_SCRIPT', translation_unit=None)])
        spec = dict(cleanup_status=result['status'])
        for name, row in refs.items():
            spec[name + '_path'] = str(Path(row['path']).relative_to(self.project))
            spec[name + '_sha256'] = row['sha256']
        return build, spec, dict(retirement_ledger=ledger, cleanup_plan=plan, cleanup_result=result)

    def test_only_exact_five_objects_and_environment_script_are_historical(self):
        build, spec, proof = self.fixture()
        retired = menu._retirement(build, self.project, spec, proof, retained._Files(check_metadata=True))
        self.assertEqual(len(retired), 6)

    def test_role_swap_and_missing_provider_substitution_are_rejected(self):
        for alteration in ('role', 'provider', 'reappeared'):
            with self.subTest(alteration=alteration):
                build, spec, proof = self.fixture()
                if alteration == 'role':
                    proof['retirement_ledger']['retired'][0]['role'] = 'BUILD_ENVIRONMENT_SCRIPT'
                elif alteration == 'provider':
                    proof['retirement_ledger']['retired'][0]['path'] = str(self.project / 'Build/provider.dll')
                else:
                    path = Path(proof['retirement_ledger']['retired'][0]['path'])
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(b'a retired object reappeared')
                with self.assertRaises(RuntimeError):
                    menu._retirement(build, self.project, spec, proof, retained._Files(check_metadata=True))


class RegistrationAndPreparationTests(PrivateFiles):
    def test_python_support_closure_requires_every_imported_sibling(self):
        first = self.write('support/first.py', b'import second\nimport json\n')
        second = self.write('support/second.py', b'from enum import Enum\n')
        result = preparer.audit_python_support_closure(self.project / 'support', {'first.py': first, 'second.py': second})
        self.assertEqual(result['module_count'], 2)
        self.assertEqual(result['local_import_edges']['first.py'], ['second.py'])
        self.assertFalse(result['imported_or_executed_modules'])
        with self.assertRaisesRegex(RuntimeError, 'missing frozen modules: second'):
            preparer.audit_python_support_closure(self.project / 'support', {'first.py': first})

    def test_python_support_rejects_dynamic_and_live_project_import_fallback(self):
        for source in (b'import sys\nsys.path.insert(0,"unused-live-tools")\n', b'__import__("unused-helper")\n'):
            with self.subTest(source=source):
                row = self.write('support/first.py', source)
                with self.assertRaises(RuntimeError):
                    preparer.audit_python_support_closure(self.project / 'support', {'first.py': row})

    def test_current_actual_ui_tools_close_with_exact_six_frozen_modules(self):
        values = {name: preparer.base.artifact(PROJECT / 'tools' / name) for name in preparer.base.TOOLS}
        result = preparer.audit_python_support_closure(PROJECT / 'tools', values)
        self.assertEqual(result['module_count'], 6)
        self.assertFalse(result['live_project_tools_fallback'])

    def test_integrated_menu_pair_is_closed_until_final_registration(self):
        with mock.patch.object(retained, 'MENU_SUITE_BUILD_ID', None), \
                self.assertRaisesRegex(RuntimeError, 'not been byte-attested'):
            preparer.main(['--menu-suite-host'])

    def test_registration_cannot_be_changed_by_a_caller_spec(self):
        actual = retained.registered_host_spec(menu.EXIT_BUILD_ID)
        self.assertEqual(actual['catalog']['entry_count'], 69)
        self.assertEqual(actual['materialized_input_count'], 601)
        self.assertEqual(actual['kind'], 'retained_menu_suite')
        changed = copy.deepcopy(actual)
        changed['catalog']['entry_count'] = 67
        self.assertEqual(retained.registered_host_spec(menu.EXIT_BUILD_ID)['catalog']['entry_count'], 69)
        with self.assertRaisesRegex(RuntimeError, 'changed retained menu Host specification'):
            menu.validate_retained_menu_suite_host_runtime(dict(build_id=menu.EXIT_BUILD_ID), PROJECT,
                                                           changed, retained._Files(check_metadata=True))

    def test_freeze_preserves_helper_and_profile_next_to_the_frozen_dispatcher(self):
        dispatcher = self.write('evidence/interactive_game/fixture/retained_host_runtime_input.py', b'# frozen dispatcher\n')
        helper = self.write('tools/retained_menu_suite_host_input.py', b'# inert helper fixture\n')
        profile = self.write('evidence/profile.json', b'{"fixture":true}\n')
        request = dict(provenance=dict(retained_host_runtime_input=dispatcher))
        fake = mock.Mock()
        fake.registration_reference.return_value = profile
        fake.FROZEN_PROFILE_NAME = menu.FROZEN_PROFILE_NAME
        spec = dict(build_id='fixture', helper_path='tools/retained_menu_suite_host_input.py', helper_sha256=helper['sha256'])
        with mock.patch.object(preparer, 'PROJECT', self.project), mock.patch.object(retained, '_menu_suite_helper', return_value=fake):
            result = preparer.freeze_menu_host_registration(request, spec, mock.Mock(run_id='fixture'))
        self.assertEqual(set(result), {'retained_menu_suite_host_input', 'retained_menu_suite_host_profile'})
        for name, row in result.items():
            self.assertEqual(request['provenance'][name], row)
            self.assertEqual(Path(row['path']).parent, Path(dispatcher['path']).parent)

    def test_gate_has_no_native_execution_imports_or_calls(self):
        tree = ast.parse((PROJECT / 'tools/retained_menu_suite_host_input.py').read_text(encoding='utf-8'))
        imports = {alias.name.split('.')[0] for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
        self.assertFalse(imports & {'ctypes', 'subprocess', 'sqlite3', 'win32api', 'clr'})
        self.assertFalse(any(isinstance(node, ast.Attribute) and node.attr in
                             ('Popen', 'LoadLibrary', 'WinDLL', 'CDLL', 'startfile', 'system') for node in ast.walk(tree)))


if __name__ == '__main__':
    unittest.main()
