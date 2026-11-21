"""Controlled filesystem fixtures for registered restore-Host runtime gates.

These tests replace evidence pins only for their private project-owned fixtures.
They do not attest the actual runtime, launch a Host, or load an SDK image.
"""
from __future__ import annotations

import copy
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


sys.dont_write_bytecode = True
PROJECT = Path(__file__).absolute().parents[1]
sys.path.insert(0, str(PROJECT / 'tools'))
sys.path.insert(0, str(PROJECT / 'Tests'))
import retained_host_runtime_input as retained
from test_retained_host_runtime_input import fixture_pe, reference

RUNNER_SPEC = importlib.util.spec_from_file_location(
    'restore_host_input_component_runner', PROJECT / 'tools/run_interactive_game.py')
runner = importlib.util.module_from_spec(RUNNER_SPEC)
RUNNER_SPEC.loader.exec_module(runner)
PREPARER_SPEC = importlib.util.spec_from_file_location(
    'restore_host_input_component_preparer', PROJECT / 'tools/prepare_latest_engine_pair.py')
preparer = importlib.util.module_from_spec(PREPARER_SPEC)
PREPARER_SPEC.loader.exec_module(preparer)

RESTORE_BUILD_ID = '20261024T042219Z_e6399c82ee5c'
STAGE_SUFFIX = 'evidence/native_restore_contract/host_build/e6399c82ee5c15c73b86'
REJECTIONS = (RuntimeError, OSError, ValueError, EOFError)
OPERATIONAL_PATHS = ('tools/run_interactive_game.py',
                     'tools/retained_host_runtime_input.py',
                     'tools/prepare_latest_engine_pair.py')
SOURCE_PATHS = ('Source/Host/SdkGameRestore.h', 'Source/Host/HostRun.h',
                'Source/Host/InteractiveGameSession.h')
METADATA_PATHS = ('evidence/save_menu/20261013_original_screen/current_progress.json',
                  'docs/M7_RETAIL_SAVE_BOUNDARY.md')


class RestoreHostRuntimeInputTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='_restore_host_inputs_', dir=PROJECT)
        self.addCleanup(temporary.cleanup)
        self.project = Path(temporary.name).absolute()
        self.build_root = self.project / 'Build/UiWindowHost' / RESTORE_BUILD_ID
        self.stage = self.project / STAGE_SUFFIX
        self.kept = {}
        self.retired_payloads = {}
        self.real_registry = retained.registered_host_spec
        self.template = self.make_build()
        self.publish()

    def write(self, relative, payload, *, keep=None):
        path = self.project / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        row = reference(path, payload)
        info = path.stat()
        row.update(file_identity=[info.st_dev, info.st_ino], mtime_ns=info.st_mtime_ns)
        if keep:
            self.kept[keep] = row
        return row

    def document(self, relative, value):
        payload = (json.dumps(value, sort_keys=True, ensure_ascii=True) + '\n').encode('ascii')
        return self.write(relative, payload)

    def compressed(self, relative, payload):
        return self.write(relative, gzip.compress(payload, mtime=0))

    def historical(self, relative, old_payload, new_payload, backup_relative):
        after = self.write(relative, new_payload, keep=relative)
        before = reference(self.project / relative, old_payload)
        backup = self.compressed(backup_relative, old_payload)
        self.kept[relative + ' backup'] = backup
        return dict(before=before, backup=backup, after=after)

    def make_build(self):
        executable = self.write(self.build_root / 'final/ZeroSisHost_x64.exe',
                                fixture_pe(), keep='PE')
        executable['pe'] = dict(architecture='x64', pe_format='PE32+', is_dll=False)
        dependency = self.write(self.build_root / 'frozen/fixture.h',
                                b'// Compiled portable fixture header.\n', keep='compiler input')
        library = self.write(self.build_root / 'frozen/provider.lib',
                             b'!<arch>\ncontrolled fixture\n', keep='library')
        units, objects = [], []
        for index, (name, stem) in enumerate(retained.UNITS):
            directory = self.build_root / 'final' / ('tu_%02d_%s' % (index, name))
            payload = b'controlled retired COFF evidence: ' + stem.encode('ascii')
            obj = self.write(directory / 'obj' / (stem + '.obj'), payload)
            self.retired_payloads[obj['path']] = payload
            Path(obj['path']).unlink()
            response = self.write(directory / (name + '.compile.rsp'),
                                 b'/c controlled_fixture.cpp\n', keep=name + ' rsp')
            deps = self.document(directory / (name + '.sourceDependencies.json'),
                                 dict(Version='1.2', Data=dict(Source=dependency['path'], Includes=[])))
            self.kept[name + ' dependencies'] = deps
            log = self.write(self.stage / ('compile_' + name + '.log'),
                             b'controlled compile receipt\n', keep=name + ' log')
            units.append(dict(translation_unit=name, returncode=0, object=obj,
                              response=response, dependency_report=deps, log=log,
                              expected_dependency_count=4, actual_dependency_count=4))
            objects.append(obj)
        environment_path = self.build_root / 'read_build_environment.cmd'
        # Exact retained setup-command bytes, treated as inert fixture data.
        environment_payload = (
            '@echo off\ncall "C:\\Program Files\\Microsoft Visual Studio\\2022\\Community\\'
            'VC\\Auxiliary\\Build\\vcvars64.bat" >nul\nif errorlevel 1 exit /b 1\nset\n').encode('ascii')
        self.assertEqual(140, len(environment_payload))
        self.assertEqual('fbea552a6bb1afe675455702d2bcb52b666cb58115922a59f508f1cefc0e55bf',
                         hashlib.sha256(environment_payload).hexdigest())
        environment = self.write(environment_path, environment_payload)
        self.retired_payloads[environment['path']] = environment_payload
        environment_path.unlink()
        self.targets = copy.deepcopy(objects) + [environment]
        self.source_revisions = []
        for index, relative in enumerate(SOURCE_PATHS):
            old_payload = ('// Old compiled source %d.\n' % index).encode('ascii')
            self.source_revisions.append(self.historical(
                relative, old_payload, ('// Current compiled source %d.\n' % index).encode('ascii'),
                'evidence/native_restore_contract/source_backups/%s.before.%s.gz' %
                (Path(relative).name, hashlib.sha256(old_payload).hexdigest()[:16])))
        self.metadata_revisions = []
        for index, relative in enumerate(METADATA_PATHS):
            self.metadata_revisions.append(self.historical(
                relative, ('Historical documentation %d\n' % index).encode('ascii'),
                ('Current documentation %d\n' % index).encode('ascii'),
                'evidence/native_save_archive/host_relink/18bbd0dd26e70e623276/publication/%s.before.gz' %
                Path(relative).name))
        self.publication_revisions = []
        for index, revision in enumerate(self.metadata_revisions):
            relative = METADATA_PATHS[index]
            before = copy.deepcopy(revision['after'])
            backup = self.compressed(self.project /
                ('evidence/native_restore_contract/publication/%s.before.gz' % Path(relative).name),
                ('Current documentation %d\n' % index).encode('ascii'))
            self.kept[relative + ' publication backup'] = backup
            after = self.write(relative, ('Published documentation %d\n' % index).encode('ascii'))
            self.publication_revisions.append(dict(before=before, after=after, backup=backup,
                                                   gzip_roundtrip_verified=True))
        self.operational_revisions = []
        for index, relative in enumerate(OPERATIONAL_PATHS):
            self.operational_revisions.append(self.historical(
                relative, ('# Historical operational tool %d\n' % index).encode('ascii'),
                ('# Current operational tool %d\n' % index).encode('ascii'),
                'evidence/native_restore_contract/pair_preparation/source_backups/%s.before.gz' %
                Path(relative).name))
        link_response = self.write(self.build_root / 'final/link.rsp',
                                   b'controlled final link response\n', keep='link rsp')
        link_log = self.write(self.stage / 'link.log', b'controlled link receipt\n', keep='link log')
        compiled_sources = [copy.deepcopy(row['after']) for row in self.source_revisions]
        self.source_before_rows = [dict(original_path=row['before']['path'],
            bytes=row['before']['bytes'], sha256=row['before']['sha256'], backup=copy.deepcopy(row['backup']))
            for row in self.source_revisions]
        self.metadata_before_rows = [dict(original_path=row['before']['path'],
            bytes=row['before']['bytes'], sha256=row['before']['sha256'], backup=copy.deepcopy(row['backup']))
            for row in self.metadata_revisions]
        # original_path provenance proves a prior gzip's identity; it is not a
        # waiver for a changed current compiled source or an unrelated document.
        protected = [copy.deepcopy(row['before']) for row in self.operational_revisions]
        compiler = [copy.deepcopy(dependency)] + copy.deepcopy(compiled_sources)
        for row in compiler:
            row['original_path'] = row['path']
        for row in compiled_sources:
            row['original_source'] = row['path']
        for unit in units:
            deps = self.document(unit['dependency_report']['path'], dict(
                Version='1.2', Data=dict(Source=dependency['path'],
                    Includes=[row['path'] for row in compiled_sources])))
            unit['dependency_report'] = deps
            self.kept[unit['translation_unit'] + ' dependencies'] = deps
        return dict(schema='zerosis.ui_window_host_build.v1',
            status='UI_WINDOW_HOST_CANDIDATE_BUILT', build_id=RESTORE_BUILD_ID,
            executable=executable, source_inputs_unchanged=True, provider_inputs_unchanged=True,
            compiler_inputs=compiler, compiler_dependency_count=4,
            current_source_inputs=copy.deepcopy(compiled_sources) +
                [copy.deepcopy(row['before']) for row in self.publication_revisions],
            sources=copy.deepcopy(compiled_sources), libraries=[library],
            imports=dict(dependencies=['controlled-dependency-%d.dll' % index for index in range(24)]),
            catalog=dict(entry_count=67, ordered_payload_manifest_sha256=
                'db76873a3dff1360b89a4b57cc6c0da51893ace2efb234c5f83b739227bb411c'),
            restore_contract_marker=dict(ascii='NATIVE_RESTORE_CONTRACT_VERIFIED=SOURCE_ORDER_V1|',
                                         inclusion_evidence_only=True),
            final_compilation=dict(translation_units=units),
            link_response=link_response, link_log=link_log,
            link_snapshot=dict(objects_before=copy.deepcopy(objects), objects_after=copy.deepcopy(objects),
                               response=copy.deepcopy(link_response), returncode=0),
            source_revision_provenance=[dict(before=copy.deepcopy(before), after=copy.deepcopy(revision['after']))
                for before, revision in zip(self.source_before_rows, self.source_revisions)],
            historical_metadata_recovery=copy.deepcopy(self.metadata_before_rows),
            protected_artifacts=protected)

    def publish(self, changes=None):
        """Pin a controlled miniature authority graph, never real runtime proof."""
        changes = changes or {}
        def changed(stage, value):
            if stage in changes:
                changes[stage](value)
            return value
        self.build = changed('build', copy.deepcopy(self.template))
        self.report_ref = self.document(
            'evidence/ui_window_host/%s/build_result.json' % RESTORE_BUILD_ID, self.build)
        run = changed('run', dict(status='PASS_CURRENT_NATIVE_RESTORE_HOST_BUILD_ONLY',
            build_id=RESTORE_BUILD_ID, build_result=copy.deepcopy(self.report_ref),
            host_or_sdk_or_window_executed=False,
            actual_objects=[copy.deepcopy(unit['object']) for unit in
                            self.build['final_compilation']['translation_units']]))
        self.run_ref = self.document(self.stage / 'run.json', run)
        attest = changed('attestation', dict(
            schema='zerosis.native_restore.host_build.independent_attestation.v1',
            status='PASS_CURRENT_NATIVE_RESTORE_HOST_STATIC_ATTESTATION',
            build_id=RESTORE_BUILD_ID, build_result=copy.deepcopy(self.report_ref),
            run=copy.deepcopy(self.run_ref),
            executable=copy.deepcopy(self.build['executable']), units=[
                dict(translation_unit=unit['translation_unit'], dependencies=4,
                     object_bytes=unit['object']['bytes'], coff_machine='0x8664', returncode=0)
                for unit in self.build['final_compilation']['translation_units']],
            source_edited=False, host_or_sdk_or_window_executed=False,
            sdk_or_host_module_loaded=False, child_process_started=False,
            compiler_dependency_union=len(self.template['compiler_inputs']),
            source_manifest_verified=len(self.template['sources']),
            current_inputs_verified=len(self.template['current_source_inputs']),
            protected_artifacts_verified=len(self.template['protected_artifacts']),
            imports_verified=24, catalog=copy.deepcopy(self.build['catalog']),
            restore_contract_marker=copy.deepcopy(self.build['restore_contract_marker']),
            sdk_restore_verified=False, native_restore_approved=False, full_engine_goal_complete=False))
        self.attestation_ref = self.document(self.stage / 'attestation.json', attest)
        plan = changed('plan', dict(
            schema='zerosis.native_restore.host_intermediate_retirement_plan.v1',
            build_result=copy.deepcopy(self.report_ref), executable=copy.deepcopy(self.build['executable']),
            targets=copy.deepcopy(self.targets), target_files=6,
            independent_attestation_required_before_deletion=True, deletion_performed=False))
        self.plan_ref = self.document(self.stage / 'retirement/plan.json', plan)
        retirement = changed('retirement', dict(
            schema='zerosis.native_restore.host_intermediate_retirement.v1',
            status='PASS_VERIFIED_CURRENT_HOST_INTERMEDIATES_RETIRED',
            plan=copy.deepcopy(self.plan_ref), independent_static_attestation=copy.deepcopy(self.attestation_ref),
            deleted_files=6, deleted_empty_directories=6, deleted_paths=[row['path'] for row in self.targets],
            all_targets_absent=True, large_binary_backup_created=False,
            executable=copy.deepcopy(self.build['executable']),
            sources_and_shared_inputs_not_deleted=True, host_sdk_or_ui_executed=False,
            full_engine_goal_complete=False))
        self.retirement_ref = self.document(self.stage / 'retirement/result.json', retirement)
        pre_edit = changed('pre_edit', dict(schema='controlled.fixture.before_publication.v1',
            fixture_not_actual_runtime=True))
        self.pre_edit_ref = self.document('evidence/native_restore_contract/publication/pre_edit.json', pre_edit)
        update = changed('update', dict(
            schema='zerosis.native_restore.progress_publication.v1',
            status='PASS_CURRENT_RESTORE_HOST_PROOF_PUBLISHED_WITHOUT_RUNTIME_PROMOTION',
            build_result=copy.deepcopy(self.report_ref), static_attestation=copy.deepcopy(self.attestation_ref),
            retirement=copy.deepcopy(self.retirement_ref), changed_metadata=copy.deepcopy(self.publication_revisions),
            pre_edit=copy.deepcopy(self.pre_edit_ref),
            current_host_source_matches_linked_candidate=True, prepared_runtime_matches_new_current_host=False,
            new_host_executed=False, original_ui_3d_campaign_accepted=False, full_engine_goal_complete=False))
        self.update_ref = self.document('evidence/native_restore_contract/publication/progress_update.json', update)
        audit = changed('audit', dict(
            schema='zerosis.native_restore.current_host_final_audit.v1',
            status='PASS_CURRENT_RESTORE_HOST_PUBLICATION_RETIREMENT_AND_INPUT_AUDIT',
            publication=copy.deepcopy(self.update_ref), build_result=copy.deepcopy(self.report_ref),
            static_attestation=copy.deepcopy(self.attestation_ref), retirement=copy.deepcopy(self.retirement_ref),
            executable=copy.deepcopy(self.build['executable']), current_host_executed=False,
            second_human_escape_stop_respected=True, sdk_restore_or_reopen_verified=False,
            default_runtime_promoted=False, full_engine_goal_complete=False))
        self.audit_ref = self.document('evidence/native_restore_contract/publication/final_audit.json', audit)
        ledger = changed('ledger', dict(
            schema='zerosis.native_restore.operational_revisions.v1', build_id=RESTORE_BUILD_ID,
            build_result=copy.deepcopy(self.report_ref), revisions=copy.deepcopy(self.operational_revisions),
            compiled_host_sources_changed=False, host_or_sdk_executed=False))
        self.ledger_ref = self.document(
            'evidence/native_restore_contract/pair_preparation/operational_revisions.json', ledger)

    def fixture_spec(self, build_id):
        spec = self.real_registry(build_id)
        if build_id != RESTORE_BUILD_ID or spec is None:
            return spec
        spec = copy.deepcopy(spec)
        for field, row in (('report', self.report_ref), ('attestation', self.attestation_ref),
                           ('retirement', self.retirement_ref), ('plan', self.plan_ref),
                           ('publication', self.update_ref), ('audit', self.audit_ref),
                           ('pre_edit', self.pre_edit_ref)):
            spec[field + '_sha256'] = row['sha256']
        spec['executable_sha256'] = self.template['executable']['sha256']
        spec['operational_before'] = {relative: dict(bytes=row['before']['bytes'],
            sha256=row['before']['sha256']) for relative, row in
            zip(OPERATIONAL_PATHS, self.operational_revisions)}
        spec.update(compiler_dependency_count=len(self.template['compiler_inputs']),
                    current_source_count=len(self.template['current_source_inputs']),
                    source_manifest_count=len(self.template['sources']),
                    protected_artifact_count=len(self.template['protected_artifacts']),
                    dependency_counts=(4, 4, 4, 4, 4))
        return spec

    def validate(self, *, integration=False, build=None):
        value = self.build if build is None else build
        before = copy.deepcopy(value)
        path = Path(self.report_ref['path'])
        report_bytes = path.read_bytes() if path.exists() else None
        try:
            with (mock.patch.object(retained, 'registered_host_spec', side_effect=self.fixture_spec),
                  mock.patch.object(subprocess, 'Popen', side_effect=AssertionError('No native process may run'))):
                if integration:
                    with (mock.patch.object(runner, 'PROJECT', self.project),
                          mock.patch.object(runner, 'check_artifacts',
                              side_effect=AssertionError('Registered builds require their exact runtime gate'))):
                        return runner.check_host_runtime_artifacts(value)
                return retained.validate_retained_host_runtime(value, self.project)
        finally:
            self.assertEqual(before, value, 'Runtime validation mutated the incoming sealed report')
            self.assertEqual(report_bytes, path.read_bytes() if path.exists() else None,
                             'Runtime validation rewrote its pinned report file')

    def rejected(self, *, integration=False, build=None):
        with self.assertRaises(REJECTIONS):
            self.validate(integration=integration, build=build)

    def replace_then_reject(self, path, payload, *, integration=False):
        path = Path(path)
        original = path.read_bytes()
        info = path.stat()
        try:
            path.write_bytes(payload)
            self.rejected(integration=integration)
        finally:
            path.write_bytes(original)
            os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns))

    def test_controlled_five_coff_six_target_graph_is_accepted(self):
        result = self.validate()
        self.assertEqual('RETAINED_CURRENT_RESTORE_HOST_INPUTS_WITH_ATTESTED_FINAL_OBJECT_RETIREMENT',
                         result['scope'])
        self.assertEqual(RESTORE_BUILD_ID, result['registered_build_id'])
        self.assertEqual(5, len(result['absent_final_objects']))
        self.assertEqual([], result['absent_discovery_objects'])
        self.assertEqual(2, result['historical_metadata_backups_verified'])
        self.assertEqual(3, result['historical_operational_backups_verified'])
        self.assertEqual(3, len(result['current_operational_sources']))
        self.assertTrue(result['current_restore_contract_linked'])
        self.assertIs(result['host_executed'], False)
        self.assertIs(result['sdk_restore_verified'], False)
        self.assertIs(result['native_restore_approved'], False)
        self.assertIs(result['save_compatibility_verified'], False)
        self.assertEqual(140, result['absent_environment_setup']['bytes'])
        self.assertEqual(self.ledger_ref['sha256'], result['operational_revisions']['sha256'])

    def test_registered_runner_dispatches_to_the_new_gate(self):
        self.assertEqual(self.validate(), self.validate(integration=True))

    def test_registry_is_exact_fresh_and_preserves_legacy_dynamic_pins(self):
        first = self.real_registry(RESTORE_BUILD_ID)
        self.assertEqual(RESTORE_BUILD_ID, first['build_id'])
        first['report_sha256'] = '0' * 64
        first['operational_before'].clear()
        second = self.real_registry(RESTORE_BUILD_ID)
        self.assertNotEqual(first['report_sha256'], second['report_sha256'])
        self.assertEqual(set(OPERATIONAL_PATHS), set(second['operational_before']))
        for value in ('unregistered', '', None):
            self.assertIsNone(self.real_registry(value))
        with mock.patch.object(retained, 'REPORT_SHA', '1' * 64):
            legacy = self.real_registry(retained.BUILD_ID)
            self.assertEqual('1' * 64, legacy['report_sha256'])
            self.assertEqual('legacy_native_envelope', legacy['kind'])

    def test_wrong_build_and_nonidentical_incoming_report_are_rejected(self):
        for field, replacement in (('build_id', '20261024T042219Z_000000000000'),
                                   ('source_inputs_unchanged', 1), ('status', 'UNATTESTED')):
            with self.subTest(field=field):
                changed = copy.deepcopy(self.build)
                changed[field] = replacement
                self.rejected(build=changed)
        changed = copy.deepcopy(self.build)
        changed['final_compilation']['translation_units'][0]['returncode'] = False
        self.rejected(integration=True, build=changed)

    def test_each_proof_file_is_hash_bound(self):
        for row in (self.report_ref, self.attestation_ref, self.run_ref, self.plan_ref,
                    self.retirement_ref, self.pre_edit_ref, self.update_ref, self.audit_ref):
            with self.subTest(proof=Path(row['path']).name):
                path = Path(row['path'])
                self.replace_then_reject(path, path.read_bytes() + b' ', integration=True)

    def test_missing_retained_response_is_not_a_retirement_exception(self):
        Path(self.kept['host_main rsp']['path']).unlink()
        self.rejected(integration=True)

    def test_current_files_and_backup_artifacts_cannot_drift(self):
        for label, row in self.kept.items():
            if label in METADATA_PATHS:
                # Published documents may evolve; only their exact historical
                # before identities are backed by this runtime-input gate.
                continue
            with self.subTest(artifact=label):
                path = Path(row['path'])
                self.replace_then_reject(path, path.read_bytes() + b'changed')

    def test_resurrected_object_or_environment_command_is_rejected(self):
        for path, payload in self.retired_payloads.items():
            with self.subTest(retired_file=Path(path).name):
                target = Path(path)
                target.parent.mkdir(parents=True, exist_ok=True)
                try:
                    target.write_bytes(payload)
                    self.rejected(integration=True)
                finally:
                    target.unlink()

    def test_retirement_requires_the_exact_five_objects_and_environment_target(self):
        def missing(value):
            value['targets'].pop()
        def duplicate(value):
            value['targets'][-1] = copy.deepcopy(value['targets'][0])
        def foreign(value):
            value['targets'][-1]['path'] = str(self.build_root / 'foreign.obj')
        def wrong_environment(value):
            value['targets'][-1]['sha256'] = '0' * 64
        for change in (missing, duplicate, foreign, wrong_environment):
            with self.subTest(change=change.__name__):
                self.publish({'plan': change})
                self.rejected()
        self.publish({'retirement': lambda value: value['deleted_paths'].pop()})
        self.rejected()

    def test_coff_attestation_and_compile_inventory_are_exact(self):
        for stage, field, replacement in (
            ('attestation', 'coff_machine', '0x014c'),
            ('attestation', 'object_bytes', 0),
            ('attestation', 'returncode', 1)):
            with self.subTest(field=field):
                def change(value):
                    value['units'][0][field] = replacement
                self.publish({stage: change})
                self.rejected()
        self.publish({'run': lambda value: value['actual_objects'][0].update(sha256='0' * 64)})
        self.rejected()
        self.publish({'build': lambda value: value['final_compilation']['translation_units'].reverse()})
        self.rejected()
        self.publish({'build': lambda value: value['final_compilation']['translation_units'][0].update(returncode=False)})
        self.rejected()

    def test_plain_json_retirement_scope_and_proof_bindings_are_checked(self):
        for stage, field, replacement in (
            ('attestation', 'status', 'OTHER_ATTESTATION'),
            ('attestation', 'host_or_sdk_or_window_executed', True),
            ('retirement', 'all_targets_absent', False),
            ('retirement', 'deleted_files', 5),
            ('audit', 'second_human_escape_stop_respected', False),
            ('audit', 'current_host_executed', True),
            ('update', 'new_host_executed', True),
            ('run', 'host_or_sdk_or_window_executed', True)):
            with self.subTest(stage=stage, field=field):
                self.publish({stage: lambda value: value.update({field: replacement})})
                self.rejected()
        for stage, field in (('attestation', 'build_result'), ('run', 'build_result'),
                             ('plan', 'executable'), ('retirement', 'independent_static_attestation'),
                             ('update', 'pre_edit'), ('audit', 'publication')):
            with self.subTest(stage=stage, binding=field):
                self.publish({stage: lambda value: value[field].update(sha256='0' * 64)})
                self.rejected()

    def test_actual_dependency_reports_and_union_must_match(self):
        path = self.kept['host_main dependencies']['path']
        bad = dict(Version='1.2', Data=dict(Source=str(self.project / 'unregistered.h'), Includes=[]))
        row = self.document(path, bad)
        self.publish({'build': lambda value: value['final_compilation']['translation_units'][0].update(
            dependency_report=copy.deepcopy(row))})
        self.rejected()
        self.document(path, dict(Version='1.2', Data=dict(Source=self.template['compiler_inputs'][0]['path'],
            Includes=[row['path'] for row in self.template['compiler_inputs'][1:]])))
        # Refresh only the fixture's changed receipt metadata, not any expected closure.
        current = reference(path)
        info = Path(path).stat()
        current.update(file_identity=[info.st_dev, info.st_ino], mtime_ns=info.st_mtime_ns)
        self.template['final_compilation']['translation_units'][0]['dependency_report'] = current
        for change in (
            lambda value: value['final_compilation']['translation_units'][0].update(actual_dependency_count=3),
            lambda value: value['compiler_inputs'][0].update(original_path=str(self.project / OPERATIONAL_PATHS[0]))):
            self.publish({'build': change})
            self.rejected()

    def test_operational_exceptions_cannot_intersect_any_compiled_source_inventory(self):
        for inventory, field in (('compiler_inputs', 'original_path'), ('sources', 'original_source')):
            with self.subTest(inventory=inventory):
                self.publish({'build': lambda value: value[inventory][0].update(
                    {field: str(self.project / OPERATIONAL_PATHS[0])})})
                self.rejected()
        self.publish({'build': lambda value: value['current_source_inputs'].__setitem__(
            0, copy.deepcopy(self.operational_revisions[0]['after']))})
        self.rejected()

    def test_original_path_backup_provenance_is_not_a_current_source_waiver(self):
        historical = copy.deepcopy(self.source_revisions[0]['before'])
        self.publish({'build': lambda value: value.update(extra_source_before_reference=historical)})
        self.rejected()
        foreign = reference(self.project / 'docs/never_owned_by_this_proof.md', b'foreign')
        self.publish({'build': lambda value: value.update(extra_historical_reference=foreign)})
        self.rejected()

    def test_metadata_requires_exact_paths_and_gzip_roundtrip(self):
        def foreign(value):
            row = value['changed_metadata'][0]
            row['before']['path'] = row['after']['path'] = str(self.project / 'docs/foreign.md')
        def duplicate(value):
            value['changed_metadata'][1] = copy.deepcopy(value['changed_metadata'][0])
        for change in (foreign, duplicate):
            self.publish({'update': change})
            self.rejected()
        self.publish({'update': lambda value: value['changed_metadata'][0].update(gzip_roundtrip_verified=False)})
        self.rejected()
        wrong = self.compressed(self.project / 'evidence/native_restore_contract/publication/wrong.before.gz',
                                b'wrong recovered metadata')
        self.publish({'update': lambda value: value['changed_metadata'][0].update(backup=wrong)})
        self.rejected()

    def test_operational_ledger_is_exact_and_cannot_claim_runtime_or_compiled_changes(self):
        for field, value in (('compiled_host_sources_changed', True), ('host_or_sdk_executed', True),
                             ('build_id', retained.BUILD_ID)):
            with self.subTest(field=field):
                self.publish({'ledger': lambda document: document.update({field: value})})
                self.rejected()
        self.publish({'ledger': lambda value: value['build_result'].update(sha256='0' * 64)})
        self.rejected()
        self.publish({'ledger': lambda value: value['revisions'].pop()})
        self.rejected()
        self.publish({'ledger': lambda value: value['revisions'].__setitem__(
            1, copy.deepcopy(value['revisions'][0]))})
        self.rejected()

    def test_operational_source_before_and_backup_paths_are_bounded(self):
        self.publish({'ledger': lambda value: value['revisions'][0]['before'].update(bytes=-1)})
        self.rejected()
        outside = self.compressed('docs/foreign-before.gz',
            ('# Historical operational tool 0\n').encode('ascii'))
        self.publish({'ledger': lambda value: value['revisions'][0].update(backup=outside)})
        self.rejected()
        wrong = self.compressed(
            'evidence/native_restore_contract/pair_preparation/source_backups/wrong-before.gz', b'wrong')
        self.publish({'ledger': lambda value: value['revisions'][0].update(backup=wrong)})
        self.rejected()

    def test_operational_source_before_exact_resource_bound_and_one_byte_over(self):
        for size, accepted in ((8 * 1024 * 1024, True), (8 * 1024 * 1024 + 1, False)):
            with self.subTest(size=size):
                old = b'x' * size
                before = reference(self.project / OPERATIONAL_PATHS[0], old)
                backup = self.compressed(
                    'evidence/native_restore_contract/pair_preparation/source_backups/bounded-before.gz', old)
                self.operational_revisions[0].update(before=before, backup=backup)
                self.template['protected_artifacts'][0] = copy.deepcopy(before)
                self.publish()
                if accepted:
                    self.assertEqual(3, self.validate()['historical_operational_backups_verified'])
                else:
                    self.rejected()

    def test_operational_foreign_path_or_later_unpinned_after_is_rejected(self):
        def foreign(value):
            row = value['revisions'][0]
            row['before']['path'] = row['after']['path'] = str(self.project / 'tools/foreign.py')
        self.publish({'ledger': foreign})
        self.rejected()
        self.publish({'ledger': lambda value: value['revisions'][0]['after'].update(sha256='0' * 64)})
        self.rejected()
        self.publish({'ledger': lambda value: value['revisions'][0]['before'].update(sha256='0' * 64)})
        self.rejected()

    def test_restore_selector_is_resolved_before_any_materialization(self):
        for arguments, selected in (([], retained.BUILD_ID),
                                     (['--restore-contract-host'], RESTORE_BUILD_ID)):
            with self.subTest(arguments=arguments):
                with (mock.patch.object(retained, 'registered_host_spec', return_value=None) as lookup,
                      mock.patch.object(preparer, 'PROJECT', self.project),
                      mock.patch.object(preparer, 'STAGE_ROOT', self.project / 'legacy_materialization'),
                      mock.patch.object(preparer, 'RESTORE_STAGE_ROOT', self.project / 'restore_materialization'),
                      mock.patch.object(preparer.base, 'checked', side_effect=AssertionError('No input reads')),
                      mock.patch.object(preparer.base, 'read', side_effect=AssertionError('No input reads')),
                      mock.patch.object(preparer.base, 'artifact', side_effect=AssertionError('No input reads')),
                      mock.patch.object(preparer, 'PairGuard', side_effect=AssertionError('No preparation')),
                      mock.patch.object(subprocess, 'Popen', side_effect=AssertionError('No native launch'))):
                    with self.assertRaisesRegex(RuntimeError, 'not registered'):
                        preparer.main(arguments)
                lookup.assert_called_once_with(selected)
        self.assertFalse((self.project / 'legacy_materialization').exists())
        self.assertFalse((self.project / 'restore_materialization').exists())


if __name__ == '__main__':
    unittest.main()
