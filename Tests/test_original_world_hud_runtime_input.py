"""Controlled filesystem regressions for the original-HUD Host input gate.

Only private project-owned miniature fixtures replace evidence pins/counts.
Their inert PE/COFF data does not attest the real Host, SDK, save compatibility,
window routing, or campaign UI. The actual 592-input gate is a separate run.
"""
from __future__ import annotations

import copy
import gzip
import hashlib
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
from test_retained_host_runtime_input import fixture_pe, reference, runner

HUD_BUILD_ID = '20261024T055841Z_974a5be57533'
HUD_REPORT_SHA = '6aa2ccdb8ce1308521fc01f88fa45745153244b6931754a0b3111dc2129d1302'
HUD_EXECUTABLE_SHA = '600b3806b2bec50de07f85425f1532c259df3877d443cadd46de31bc3d935cd5'
HUD_STAGE = 'evidence/original_world_hud/host_build/974a5be5753302c4498c'
SOURCE_PATHS = ('Source/Presentation/WorldViewRenderer.cpp',
                'Source/Presentation/BitmapWindow.h',
                'Source/Presentation/BitmapWindow.cpp',
                'Source/Presentation/WorldCameraControls.h',
                'Source/Host/InteractiveGameLoop.h')
METADATA_PATHS = ('evidence/save_menu/20261013_original_screen/current_progress.json',
                  'docs/ORIGINAL_WORLD_HUD.md')
OLD_METADATA_PATHS = (METADATA_PATHS[0], 'docs/M7_RETAIL_SAVE_BOUNDARY.md')
OPERATIONAL_PATHS = ('tools/retained_host_runtime_input.py', 'tools/prepare_latest_engine_pair.py')
OLD_OPERATIONAL_PATHS = ('tools/run_interactive_game.py', *OPERATIONAL_PATHS)
LIBRARY_NAMES = ('msvcrt.lib', 'msvcprt.lib', 'vcruntime.lib', 'oldnames.lib',
                 'bcrypt.lib', 'kernel32.lib', 'ucrt.lib', 'uuid.lib')
REJECTIONS = (RuntimeError, OSError, ValueError, EOFError)


class FixtureFiles:
    """Small real files; no native loader, compiler, or asset materialization."""
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
        return self.write(relative, (json.dumps(value, sort_keys=True, ensure_ascii=True) + '\n').encode('ascii'))

    def compressed(self, relative, payload):
        return self.write(relative, gzip.compress(payload, mtime=0))

    def donor_link(self, path, payload, *, keep=None):
        path = Path(path)
        relative = path.relative_to(self.build_root)
        donor = self.write(self.project / 'Build/UiWindowHost' / retained.RESTORE_BUILD_ID / relative, payload)
        path.parent.mkdir(parents=True, exist_ok=True)
        os.link(donor['path'], path)
        row = reference(path, payload)
        info = path.stat()
        row.update(file_identity=[info.st_dev, info.st_ino], mtime_ns=info.st_mtime_ns,
                   reused_from_path=donor['path'])
        if keep:
            self.kept[keep] = row
        return row

    def historical(self, relative, old_payload, new_payload, backup_relative):
        after = self.write(relative, new_payload, keep=relative)
        backup = self.compressed(backup_relative, old_payload)
        self.kept[relative + ' backup ' + str(backup_relative)] = backup
        return dict(before=dict(original_path=str(self.project / relative), bytes=len(old_payload),
                                sha256=hashlib.sha256(old_payload).hexdigest(), backup=backup),
                    after=after)


class OriginalWorldHudRuntimeInputTests(FixtureFiles, unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='_world_hud_host_inputs_', dir=PROJECT)
        self.addCleanup(temporary.cleanup)
        self.project = Path(temporary.name).absolute()
        self.build_root = self.project / 'Build/UiWindowHost' / HUD_BUILD_ID
        self.stage = self.project / HUD_STAGE
        self.kept, self.retired_payloads = {}, {}
        self.real_registry = retained.registered_host_spec
        self.template = self.make_build()
        self.publish()

    def make_build(self):
        """Represent the actual schema with tiny, explicitly synthetic bytes."""
        self.source_revisions = []
        current, compiler, sources = [], [], []
        for index, relative in enumerate(SOURCE_PATHS):
            revision = self.historical(relative, ('// prior %d\n' % index).encode('ascii'),
                ('// fixture current %d\n' % index).encode('ascii'),
                'evidence/original_world_hud/source_backups/%s.before.gz' % Path(relative).name)
            self.source_revisions.append(dict(category='production_source', **revision))
            original = copy.deepcopy(revision['after'])
            frozen = self.write(self.build_root / 'frozen/include_roots/project' / relative,
                                Path(original['path']).read_bytes(), keep=relative + ' frozen')
            frozen.update(original_path=original['path'], original_source=original['path'],
                          materialization='owned_changed_source_copy', relative_path=relative)
            current.append(original); compiler.append(frozen); sources.append(copy.deepcopy(frozen))
        entry = self.write('Source/Host/FixtureEntry.cpp', b'// Inert dependency fixture.\n', keep='current entry')
        entry_frozen = self.donor_link(self.build_root / 'frozen/include_roots/project/Source/Host/FixtureEntry.cpp',
                                      Path(entry['path']).read_bytes(), keep='frozen dependency')
        entry_frozen.update(original_path=entry['path'], materialization='attested_snapshot_hardlink')
        current.append(entry); compiler.append(entry_frozen)
        for index in range(10):
            relative = 'Source/Scripting/FixtureUi%02d.lua' % index
            original = self.write(relative, ('-- literal lua fixture %d\n' % index).encode('ascii'))
            frozen = self.donor_link(self.build_root / 'frozen/include_roots/project' / relative,
                                     Path(original['path']).read_bytes())
            # The actual ten Lua source-manifest rows have this sole alias.
            frozen.update(original_source=original['path'], materialization='attested_snapshot_hardlink',
                          relative_path=relative)
            current.append(original); sources.append(frozen)
        implicit = []
        for name in LIBRARY_NAMES:
            original = self.write('private_fixture_toolchain/' + name, b'!<arch>\nfixture ' + name.encode('ascii'))
            frozen = self.donor_link(self.build_root / 'frozen/implicit_libraries' / name,
                                     Path(original['path']).read_bytes(), keep=name)
            frozen.update(name=name, original_path=original['path'], materialization='attested_snapshot_hardlink')
            implicit.append(frozen)
        self.old_operational = []
        for index, relative in enumerate(OLD_OPERATIONAL_PATHS):
            revision = self.historical(relative, ('# prior operation %d\n' % index).encode('ascii'),
                ('# operation at link %d\n' % index).encode('ascii'),
                'evidence/native_restore_contract/pair_preparation/source_backups/%s.before.gz' % Path(relative).name)
            self.old_operational.append(dict(category='operational_source', **revision))
        self.old_metadata = []
        for index, relative in enumerate(OLD_METADATA_PATHS):
            revision = self.historical(relative, ('prior document %d\n' % index).encode('ascii'),
                ('document at link %d\n' % index).encode('ascii'),
                'evidence/native_restore_contract/publication/%s.before.gz' % Path(relative).name)
            self.old_metadata.append(dict(category='metadata', **revision))
        self.inherited_metadata = []
        for index, relative in enumerate(OLD_METADATA_PATHS):
            payload = ('inherited document %d\n' % index).encode('ascii')
            backup = self.compressed('evidence/native_save_archive/host_relink/18bbd0dd26e70e623276/publication/%s.before.gz' %
                                     Path(relative).name, payload)
            self.inherited_metadata.append(dict(original_path=str(self.project / relative), bytes=len(payload),
                sha256=hashlib.sha256(payload).hexdigest(), backup=backup))
        # Two post-link operational changes remain outside all compiler/current
        # source inventories. They never waive any of the five C++ revisions.
        self.operational_revisions = []
        for relative in OPERATIONAL_PATHS:
            old = reference(self.project / relative)
            backup = self.compressed('evidence/original_world_hud/pair_preparation/source_backups/%s.before.gz' %
                                     Path(relative).name, Path(old['path']).read_bytes())
            after = self.write(relative, b'# controlled post-link operational revision\n')
            self.operational_revisions.append(dict(before=old, backup=backup, after=after))
        self.publication_revisions = []
        for index, relative in enumerate(METADATA_PATHS):
            path = self.project / relative
            if not path.exists():
                self.write(relative, b'fixture HUD document at link\n')
            old = reference(path)
            backup = self.compressed(self.stage / ('publication/%s.before.gz' % path.name), path.read_bytes())
            after = self.write(relative, ('published fixture %d\n' % index).encode('ascii'))
            self.publication_revisions.append(dict(before=old, backup=backup, after=after,
                                                   gzip_roundtrip_verified=True))
        executable = self.write(self.build_root / 'final/ZeroSisHost_x64.exe', fixture_pe(), keep='PE')
        executable['pe'] = dict(architecture='x64', pe_format='PE32+', is_dll=False)
        units, objects = [], []
        for index, (name, stem) in enumerate(retained.UNITS):
            directory = self.build_root / 'final' / ('tu_%02d_%s' % (index, name))
            payload = b'inert historical object ' + name.encode('ascii')
            obj = self.write(directory / 'obj' / (stem + '.obj'), payload)
            self.retired_payloads[obj['path']] = payload
            Path(obj['path']).unlink()
            response = self.write(directory / (name + '.compile.rsp'), b'/c fixture.cpp\n', keep=name + ' rsp')
            dependency = self.document(directory / (name + '.sourceDependencies.json'),
                dict(Version='1.2', Data=dict(Source=compiler[0]['path'], Includes=[row['path'] for row in compiler[1:]])))
            self.kept[name + ' dependencies'] = dependency
            log = self.write(self.stage / ('compile_' + name + '.log'), b'controlled compile evidence\n')
            units.append(dict(translation_unit=name, returncode=0, coff_machine='0x8664', response=response, dependency_report=dependency,
                object=obj, log=log, expected_dependency_count=len(compiler), actual_dependency_count=len(compiler)))
            objects.append(obj)
        environment_payload = ('@echo off\ncall "C:\\Program Files\\Microsoft Visual Studio\\2022\\Community\\'
            'VC\\Auxiliary\\Build\\vcvars64.bat" >nul\nif errorlevel 1 exit /b 1\nset\n').encode('ascii')
        self.assertEqual(140, len(environment_payload))
        environment = self.write(self.build_root / 'read_build_environment.cmd', environment_payload)
        self.retired_payloads[environment['path']] = environment_payload
        Path(environment['path']).unlink()
        self.targets = copy.deepcopy(objects) + [environment]
        link_response = self.write(self.build_root / 'final/link.rsp', b'controlled link response\n', keep='link rsp')
        link_log = self.write(self.stage / 'link.log', b'controlled link evidence\n', keep='link log')
        # The added small Python source is copied only into this private fixture.
        helper = self.write('tools/retained_world_hud_host_input.py',
                            (PROJECT / 'tools/retained_world_hud_host_input.py').read_bytes(), keep='new helper')
        protected = [copy.deepcopy(row['after']) for row in self.old_operational]
        protected.append(copy.deepcopy(self.publication_revisions[0]['before']))
        command_tools = {}
        for name in ('cmd.exe', 'cl.exe', 'link.exe'):
            command_tools[name] = self.write('private_fixture_toolchain/' + name,
                b'inert command identity; never executable ' + name.encode('ascii'))
            protected.append(copy.deepcopy(command_tools[name]))
        self.command_tools = command_tools
        return dict(schema='zerosis.ui_window_host_build.v1', status='UI_WINDOW_HOST_CANDIDATE_BUILT',
            build_id=HUD_BUILD_ID, executable=executable, source_inputs_unchanged=True, provider_inputs_unchanged=True,
            host_runtime_executed=False, gamecore_loaded=False, native_restore_approved=False,
            compiler_inputs=compiler, compiler_dependency_count=len(compiler), sources=sources,
            current_source_inputs=current, source_revision_provenance=copy.deepcopy(self.source_revisions),
            historical_operational_recovery=copy.deepcopy(self.old_operational),
            historical_metadata_recovery=copy.deepcopy(self.old_metadata),
            inherited_historical_metadata_recovery=copy.deepcopy(self.inherited_metadata),
            implicit_libraries=implicit, libraries=copy.deepcopy(implicit), protected_artifacts=protected,
            imports=dict(dependencies=['controlled-fixture-%d.dll' % index for index in range(24)]),
            catalog=dict(entry_count=67, ordered_payload_manifest_sha256=
                'db76873a3dff1360b89a4b57cc6c0da51893ace2efb234c5f83b739227bb411c'),
            restore_contract_marker=dict(ascii='NATIVE_RESTORE_CONTRACT_VERIFIED=SOURCE_ORDER_V1|',
                                         inclusion_evidence_only=True),
            final_compilation=dict(translation_units=units), link_response=link_response, link_log=link_log,
            link_snapshot=dict(objects_before=copy.deepcopy(objects), objects_after=copy.deepcopy(objects),
                               response=copy.deepcopy(link_response), returncode=0),
            fixture_added_helper=helper)

    def publish(self, changes=None):
        """Reseal only this miniature graph, never the actual build evidence."""
        changes = changes or {}
        def changed(name, value):
            if name in changes:
                changes[name](value)
            return value
        real_spec = self.real_registry(HUD_BUILD_ID)
        self.assertIsNotNone(real_spec)
        def proof(name, value):
            return self.document(real_spec[name + '_path'], changed(name, value))
        self.build = changed('build', copy.deepcopy(self.template))
        self.runtime_rows = []
        request_rows = []
        prior_root = self.project / 'Build/InteractiveGameRuntime/20261024T050152Z_fd0465b26387'
        for index in range(24):
            payload = ('obsolete controlled reference %d\n' % index).encode('ascii')
            name = 'bundle.manifest' if index == 23 else 'fixture_%02d.bin' % index
            full = reference(prior_root / name, payload)
            # These obsolete payloads intentionally do not exist. Their exact
            # authenticated prior-request identity is not an arbitrary waiver.
            row = dict(path=full['path'], sha256=full['sha256'])
            if index < 23:
                row['source'] = str(self.project / 'controlled_sources' / name)
            if 11 <= index < 23:
                row['bytes'] = full['bytes']
            request_rows.append(row); self.runtime_rows.append(full)
        prior_request = dict(run_id='20261024T050152Z_fd0465b26387', cwd=str(prior_root), smoke=False,
                             runtime_inputs=request_rows)
        self.prior_request_ref = proof('prior_request', prior_request)
        source_audit = self.document('evidence/original_world_hud/source_audit.json',
            dict(changes=[dict(before=dict(path=row['before']['original_path'], bytes=row['before']['bytes'],
                    sha256=row['before']['sha256']), after=copy.deepcopy(row['after']),
                    backup=copy.deepcopy(row['before']['backup'])) for row in self.source_revisions],
                 fixture_not_actual_runtime=True))
        authority = dict(schema='zerosis.original_world_hud.host_build_inputs.v1',
            baseline_build_id=retained.RESTORE_BUILD_ID, references=dict(source_audit=source_audit,
                prepared_request=copy.deepcopy(self.prior_request_ref)),
            changed_production_paths=list(SOURCE_PATHS), compiler_dependency_count=len(self.template['compiler_inputs']),
            current_source_count=len(self.template['current_source_inputs']), source_manifest_count=len(self.template['sources']),
            protected_artifact_count=len(self.template['protected_artifacts']),
            dependency_counts=[len(self.template['compiler_inputs'])] * 5,
            planned_direct_children=7, host_sdk_or_window_execution_allowed=False,
            full_engine_goal_complete=False)
        self.authority_ref = proof('authority', authority)
        self.build.update(profile=copy.deepcopy(self.authority_ref),
            original_world_hud_profile=copy.deepcopy(self.authority_ref),
            prepared_runtime_inputs=copy.deepcopy(self.runtime_rows),
            provider_inputs=[], system_libraries=[], build_tools=[], provider_reports={},
            ui_assets=copy.deepcopy(self.template['compiler_inputs'][-1]))
        started = self.document(self.stage / 'started.json', dict(fixture_not_actual_runtime=True))
        builder = self.write('tools/build_original_world_hud_host.py', b'# inert fixture build-source evidence\n')
        parent_libraries = [dict(row, path=row['reused_from_path']) for row in self.template['implicit_libraries']]
        baseline_build = self.document('evidence/ui_window_host/%s/build_result.json' % retained.RESTORE_BUILD_ID,
            dict(build_id=retained.RESTORE_BUILD_ID, implicit_libraries=parent_libraries, fixture_not_actual_runtime=True))
        baseline_attestation = self.document('evidence/native_restore_contract/host_build/fixture/attestation.json',
                                            dict(fixture_not_actual_runtime=True))
        self.build.update(started=copy.deepcopy(started), baseline_build=copy.deepcopy(baseline_build),
                          compiler=copy.deepcopy(self.command_tools['cl.exe']),
                          linker=copy.deepcopy(self.command_tools['link.exe']))
        for unit in self.build['final_compilation']['translation_units']:
            unit['command'] = [self.command_tools['cl.exe']['path'], '@' + unit['response']['path']]
        imports = self.document(self.stage / 'imports.static.json',
            dict(source='PURE_FILE_BACKED_PE_IMPORT_DIRECTORY', image=copy.deepcopy(self.build['executable']),
                 dependencies=list(self.build['imports']['dependencies'])))
        self.build['imports'].update(source='PURE_FILE_BACKED_PE_IMPORT_DIRECTORY', log=imports)
        self.report_ref = self.document(real_spec['report_path'], self.build)
        objects = [copy.deepcopy(unit['object']) for unit in self.build['final_compilation']['translation_units']]
        environment_log = self.write(self.stage / 'environment.stdout.log', b'inert environment transcript\n')
        commands = [dict(phase='environment', returncode=0, executable=self.command_tools['cmd.exe']['path'],
            command=[self.command_tools['cmd.exe']['path'], '/c', str(self.build_root / 'read_build_environment.cmd')],
            log=environment_log)]
        for unit in self.template['final_compilation']['translation_units']:
            commands.append(dict(phase='compile', returncode=0, executable=self.command_tools['cl.exe']['path'],
                command=[self.command_tools['cl.exe']['path'], '@' + unit['response']['path']], log=copy.deepcopy(unit['log'])))
        commands.append(dict(phase='link', returncode=0, executable=self.command_tools['link.exe']['path'],
            command=[self.command_tools['link.exe']['path'], '@' + self.build['link_response']['path']],
            log=copy.deepcopy(self.build['link_log'])))
        run = dict(schema='zerosis.original_world_hud.host_build_run.v1',
            status='PASS_CURRENT_ORIGINAL_WORLD_HUD_HOST_BUILD_ONLY', build_id=HUD_BUILD_ID,
            build_result=copy.deepcopy(self.report_ref), profile=copy.deepcopy(self.authority_ref),
            started=copy.deepcopy(started), builder=builder, baseline_build=baseline_build,
            actual_objects=objects, retained_runtime_inputs=copy.deepcopy(self.runtime_rows),
            commands=commands, catalog=copy.deepcopy(self.build['catalog']),
            restore_contract_marker=copy.deepcopy(self.build['restore_contract_marker']),
            input_files_unchanged=True, no_automatic_retry=True, host_or_sdk_or_window_executed=False,
            sdk_restore_verified=False, native_restore_approved=False, full_engine_goal_complete=False)
        self.run_ref = proof('run', run)
        materialized = len(self.template['compiler_inputs']) + 10 + 8
        attestation = dict(schema='zerosis.original_world_hud.host_build.independent_attestation.v1',
            status='PASS_CURRENT_ORIGINAL_WORLD_HUD_HOST_STATIC_ATTESTATION', build_id=HUD_BUILD_ID,
            build_result=copy.deepcopy(self.report_ref), run=copy.deepcopy(self.run_ref),
            authority=copy.deepcopy(self.authority_ref), executable=copy.deepcopy(self.build['executable']),
            started=copy.deepcopy(started), baseline_build=copy.deepcopy(baseline_build),
            baseline_attestation=baseline_attestation, actual_objects=copy.deepcopy(objects),
            compiler_dependency_union=len(self.template['compiler_inputs']),
            current_inputs_verified=len(self.template['current_source_inputs']),
            source_manifest_verified=len(self.template['sources']),
            protected_artifacts_verified=len(self.template['protected_artifacts']),
            units=[dict(translation_unit=unit['translation_unit'], dependencies=len(self.template['compiler_inputs']),
                        coff_machine='0x8664', object_bytes=unit['object']['bytes'], returncode=0)
                   for unit in self.build['final_compilation']['translation_units']],
            imports_verified=24, imports=list(self.build['imports']['dependencies']), implicit_libraries_verified=8,
            catalog=copy.deepcopy(self.build['catalog']), restore_contract_marker=copy.deepcopy(self.build['restore_contract_marker']),
            materialization=dict(private_source_copies=5, donor_hardlinks=materialized - 5,
                copied_source_bytes=sum(row['after']['bytes'] for row in self.source_revisions)),
            seven_recorded_commands_verified=True, returncodes=[0] * 7, exact_response_relocation_verified=True,
            native_v1_schema_changed=False, native_contract_source_hashes_unchanged=True,
            original_ui_payloads_regenerated=False, source_edited=False,
            host_or_sdk_or_window_executed=False, sdk_or_host_module_loaded=False,
            child_process_started=False, actual_window_wheel_routing_verified=False,
            full_campaign_ui_verified=False, sdk_restore_verified=False,
            native_restore_approved=False, full_engine_goal_complete=False)
        self.attestation_ref = proof('attestation', attestation)
        plan = dict(schema='zerosis.original_world_hud.host_retirement_plan.v1',
            run=copy.deepcopy(self.run_ref), independent_attestation=copy.deepcopy(self.attestation_ref),
            build_result=copy.deepcopy(self.report_ref), targets=copy.deepcopy(self.targets), target_files=6,
            host_or_sdk_or_window_executed=False, large_binary_backup_created=False)
        self.plan_ref = proof('plan', plan)
        retirement = dict(schema='zerosis.original_world_hud.host_retirement.v1',
            status='PASS_VERIFIED_CURRENT_WORLD_HUD_HOST_INTERMEDIATES_RETIRED',
            plan=copy.deepcopy(self.plan_ref), run=copy.deepcopy(self.run_ref),
            independent_attestation=copy.deepcopy(self.attestation_ref), executable=copy.deepcopy(self.build['executable']),
            deleted_files=6, deleted_paths=[row['path'] for row in self.targets], deleted_empty_directories=6,
            all_targets_absent=True, host_or_sdk_or_window_executed=False, full_engine_goal_complete=False)
        self.retirement_ref = proof('retirement', retirement)
        publication = dict(schema='zerosis.original_world_hud.host_publication.v1',
            status='PASS_CURRENT_WORLD_HUD_HOST_PUBLISHED_WITHOUT_RUNTIME_PROMOTION',
            run=copy.deepcopy(self.run_ref), build_result=copy.deepcopy(self.report_ref),
            independent_attestation=copy.deepcopy(self.attestation_ref), retirement=copy.deepcopy(self.retirement_ref),
            changed_metadata=copy.deepcopy(self.publication_revisions), old_prepared_pair_unchanged=True,
            old_prepared_pair_contains_new_host=False, native_runtime_attempts=0,
            host_or_sdk_or_window_executed=False, full_engine_goal_complete=False)
        self.publication_ref = proof('publication', publication)
        audit = dict(schema='zerosis.original_world_hud.host_finish_audit.v1',
            status='PASS_CURRENT_WORLD_HUD_HOST_BUILD_PUBLICATION_AND_CLEANUP_AUDIT', build_id=HUD_BUILD_ID,
            build_result=copy.deepcopy(self.report_ref), run=copy.deepcopy(self.run_ref),
            independent_attestation=copy.deepcopy(self.attestation_ref), retirement=copy.deepcopy(self.retirement_ref),
            publication=copy.deepcopy(self.publication_ref), executable=copy.deepcopy(self.build['executable']),
            current_source_inputs_rehashed=len(self.template['current_source_inputs']),
            frozen_donor_metadata_preserved=True, current_source_matches_new_link=True,
            prepared_runtime_updated=False, native_runtime_attempts=0,
            host_or_sdk_or_window_executed=False, full_engine_goal_complete=False)
        self.audit_ref = proof('audit', audit)
        corrected_progress = self.write(METADATA_PATHS[0], b'corrected fixture progress\n')
        correction = dict(schema='zerosis.original_world_hud.host_metadata_correction.v1',
            status='PASS_CURRENT_SOURCE_PROOF_ALIASES_AND_DOCUMENTATION_REFERENCE_CORRECTED',
            before=copy.deepcopy(self.publication_revisions[0]['after']),
            after=copy.deepcopy(corrected_progress),
            backup=self.compressed(self.stage / 'publication/correction01.before.gz',
                b'published fixture 0\n'),
            build_result=copy.deepcopy(self.report_ref), independent_attestation=copy.deepcopy(self.attestation_ref),
            current_documentation=copy.deepcopy(self.publication_revisions[1]['after']),
            host_sdk_or_window_executed=False, binary_or_source_changes=False, full_engine_goal_complete=False)
        self.correction_ref = self.document(self.stage / 'publication/correction01.json', changed('correction', correction))
        post_audit = dict(schema='zerosis.original_world_hud.host_post_publication_audit.v1',
            status='PASS_CURRENT_WORLD_HUD_HOST_LINK_METADATA_AND_CLEANUP_READBACK', build_id=HUD_BUILD_ID,
            previous_finish_audit=copy.deepcopy(self.audit_ref), metadata_correction=copy.deepcopy(self.correction_ref),
            build_result=copy.deepcopy(self.report_ref), independent_attestation=copy.deepcopy(self.attestation_ref),
            retirement=copy.deepcopy(self.retirement_ref), executable=copy.deepcopy(self.build['executable']),
            current_progress=copy.deepcopy(corrected_progress),
            current_documentation=copy.deepcopy(self.publication_revisions[1]['after']), retired_files_absent=6,
            latest_source_proof_pointers_match_new_host=True, new_host_materialized_in_prepared_runtime=False,
            actual_window_wheel_or_gpu_viewport_verified=False, native_runtime_attempts=0, full_engine_goal_complete=False)
        self.post_audit_ref = proof('post_audit', post_audit)
        ledger = dict(schema='zerosis.original_world_hud.operational_revisions.v1', build_id=HUD_BUILD_ID,
            build_result=copy.deepcopy(self.report_ref), revisions=copy.deepcopy(self.operational_revisions),
            added_operational_sources=[copy.deepcopy(self.template['fixture_added_helper'])],
            compiled_host_sources_changed=False, host_or_sdk_executed=False)
        self.ledger_ref = self.document(real_spec['operational_revisions_path'], changed('ledger', ledger))
        self.proof_refs = dict(report=self.report_ref, run=self.run_ref, authority=self.authority_ref,
            prior_request=self.prior_request_ref, attestation=self.attestation_ref, plan=self.plan_ref,
            retirement=self.retirement_ref, publication=self.publication_ref, audit=self.audit_ref,
            post_audit=self.post_audit_ref)

    def fixture_spec(self, build_id):
        spec = self.real_registry(build_id)
        if build_id != HUD_BUILD_ID or spec is None:
            return spec
        spec = copy.deepcopy(spec)
        for name, row in self.proof_refs.items():
            spec[name + '_path'] = str(Path(row['path']).relative_to(self.project))
            spec[name + '_sha256'] = row['sha256']
        spec.update(executable_sha256=self.template['executable']['sha256'],
            compiler_dependency_count=len(self.template['compiler_inputs']),
            current_source_count=len(self.template['current_source_inputs']),
            source_manifest_count=len(self.template['sources']),
            protected_artifact_count=len(self.template['protected_artifacts']),
            dependency_counts=(len(self.template['compiler_inputs']),) * 5,
            materialized_input_count=len(self.template['compiler_inputs']) + 18,
            private_source_copies=5, donor_hardlinks=len(self.template['compiler_inputs']) + 13,
            operational_before={relative: dict(bytes=row['before']['bytes'], sha256=row['before']['sha256'])
                for relative, row in zip(OPERATIONAL_PATHS, self.operational_revisions)})
        return spec

    def validate(self, *, build=None, integration=False):
        value = self.build if build is None else build
        before = copy.deepcopy(value)
        report_path = Path(self.report_ref['path'])
        original_report = report_path.read_bytes() if report_path.exists() else None
        try:
            with (mock.patch.object(retained, 'registered_host_spec', side_effect=self.fixture_spec),
                  mock.patch.object(subprocess, 'Popen', side_effect=AssertionError('No native execution'))):
                if integration:
                    with (mock.patch.object(runner, 'PROJECT', self.project),
                          mock.patch.object(runner, 'check_artifacts', side_effect=AssertionError('No generic gate fallback'))):
                        return runner.check_host_runtime_artifacts(value)
                return retained.validate_retained_host_runtime(value, self.project)
        finally:
            self.assertEqual(before, value, 'Validation mutated the supplied fixture report')
            self.assertEqual(original_report, report_path.read_bytes() if report_path.exists() else None,
                             'Validation changed its immutable fixture report file')

    def rejected(self, *, build=None):
        with self.assertRaises(REJECTIONS):
            self.validate(build=build)

    def reject_changed_file(self, path):
        path = Path(path)
        original, info = path.read_bytes(), path.stat()
        try:
            path.write_bytes(original + b'controlled corruption')
            self.rejected()
        finally:
            path.write_bytes(original)
            os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns))

    def reject_missing_file(self, path):
        path = Path(path)
        temporary = path.with_name(path.name + '.held_by_fixture')
        self.assertFalse(temporary.exists())
        path.rename(temporary)
        try:
            self.rejected()
        finally:
            temporary.rename(path)

    def test_controlled_retired_objects_and_retained_files_pass_without_approvals(self):
        result = self.validate()
        self.assertEqual(HUD_BUILD_ID, result['registered_build_id'])
        self.assertEqual(len(self.template['compiler_inputs']), result['compiler_dependency_count'])
        self.assertEqual(len(self.template['current_source_inputs']), result['current_source_count'])
        self.assertEqual(len(self.template['sources']), result['source_manifest_count'])
        self.assertEqual(5, len(result['absent_final_objects']))
        self.assertEqual(140, result['absent_environment_setup']['bytes'])
        self.assertEqual(7, result['historical_metadata_backups_verified'])
        self.assertEqual(5, result['historical_operational_backups_verified'])
        self.assertEqual(5, result['historical_source_backups_verified'])
        self.assertTrue(result['prior_unexecuted_prepared_pair_context_historical'])
        self.assertEqual(24, result['prior_prepared_pair_context_inputs'])
        self.assertTrue(all(not Path(row['path']).exists() for row in self.runtime_rows))
        for field in ('host_executed', 'sdk_restore_verified', 'native_restore_approved',
                      'save_compatibility_verified', 'actual_window_wheel_routing_verified'):
            self.assertIs(result[field], False, field)

    def test_registered_runner_dispatches_the_exact_controlled_hud_report(self):
        self.assertEqual(self.validate(), self.validate(integration=True))

    def test_obsolete_prior_context_is_not_a_general_missing_file_exception(self):
        request = json.loads(Path(self.prior_request_ref['path']).read_bytes())
        shapes = {}
        for row in request['runtime_inputs']:
            shape = frozenset(row)
            shapes[shape] = shapes.get(shape, 0) + 1
        self.assertEqual({frozenset(('source', 'path', 'sha256')): 11,
                          frozenset(('source', 'path', 'sha256', 'bytes')): 12,
                          frozenset(('path', 'sha256')): 1}, shapes)
        self.validate()
        foreign_live = copy.deepcopy(self.runtime_rows[0])
        self.publish({'build': lambda value: value.update(extra_live_dependency=foreign_live)})
        self.rejected()
        self.publish({'prior_request': lambda value: value.update(smoke=True)})
        self.rejected()
        self.publish({'prior_request': lambda value: value['runtime_inputs'].__setitem__(
            1, copy.deepcopy(value['runtime_inputs'][0]))})
        self.rejected()

    def test_parent_donor_remains_required_when_the_current_hardlink_survives(self):
        row = self.template['implicit_libraries'][0]
        self.assertEqual(Path(row['path']).stat().st_ino, Path(row['reused_from_path']).stat().st_ino)
        self.reject_missing_file(row['reused_from_path'])
        self.assertTrue(Path(row['path']).is_file())

    def test_source_before_provenance_has_a_strict_resource_bound(self):
        for size in (-1, 8 * 1024 * 1024 + 1):
            with self.subTest(declared_before_bytes=size):
                self.publish({'build': lambda value: value['source_revision_provenance'][0]['before'].update(bytes=size)})
                self.rejected()

    def test_incoming_report_requires_the_registered_exact_json_identity(self):
        for field, replacement in (('build_id', HUD_BUILD_ID + '_other'),
                                   ('status', 'UNATTESTED'), ('source_inputs_unchanged', 1)):
            with self.subTest(field=field):
                changed = copy.deepcopy(self.build)
                changed[field] = replacement
                self.rejected(build=changed)
        changed = copy.deepcopy(self.build)
        changed['final_compilation']['translation_units'][0]['returncode'] = False
        self.rejected(build=changed)

    def test_each_required_proof_is_pinned_and_cannot_be_missing(self):
        for row in self.proof_refs.values():
            with self.subTest(proof=Path(row['path']).name, state='changed'):
                self.reject_changed_file(row['path'])
            with self.subTest(proof=Path(row['path']).name, state='missing'):
                self.reject_missing_file(row['path'])

    def test_current_sources_frozen_dependency_libraries_pe_and_rsp_stay_required(self):
        labels = ('PE', 'current entry', 'frozen dependency', SOURCE_PATHS[0],
                  SOURCE_PATHS[0] + ' frozen', 'msvcrt.lib', 'host_main rsp',
                  'host_main dependencies', 'link rsp', 'new helper')
        for label in labels:
            with self.subTest(artifact=label, state='changed'):
                self.reject_changed_file(self.kept[label]['path'])
            with self.subTest(artifact=label, state='missing'):
                self.reject_missing_file(self.kept[label]['path'])

    def test_resurrecting_any_of_five_coff_objects_or_the_environment_is_rejected(self):
        for path, payload in self.retired_payloads.items():
            with self.subTest(target=Path(path).name):
                Path(path).write_bytes(payload)
                try:
                    self.rejected()
                finally:
                    Path(path).unlink()

    def test_missing_objects_need_the_exact_authenticated_six_target_boundary(self):
        def missing(value):
            value['targets'].pop()
        def duplicate(value):
            value['targets'][-1] = copy.deepcopy(value['targets'][0])
        def foreign(value):
            value['targets'][-1]['path'] = str(self.build_root / 'foreign.obj')
        def false_environment(value):
            value['targets'][-1]['sha256'] = '0' * 64
        for change in (missing, duplicate, foreign, false_environment):
            with self.subTest(change=change.__name__):
                self.publish({'plan': change})
                self.rejected()
        self.publish({'retirement': lambda value: value['deleted_paths'].pop()})
        self.rejected()
        self.publish({'retirement': lambda value: value.update(all_targets_absent=False)})
        self.rejected()

    def test_compile_attestation_and_dependency_union_remain_structural_checks(self):
        def remove_unit(value):
            value['final_compilation']['translation_units'].pop()
        def wrong_count(value):
            value['compiler_dependency_count'] += 1
        for change in (remove_unit, wrong_count):
            with self.subTest(change=change.__name__):
                self.publish({'build': change})
                self.rejected()
        self.publish({'attestation': lambda value: value['units'][0].update(coff_machine='0x014c')})
        self.rejected()
        unit = self.template['final_compilation']['translation_units'][0]
        bad_dependency = self.document(unit['dependency_report']['path'],
            dict(Version='1.2', Data=dict(Source=self.template['compiler_inputs'][0]['path'], Includes=[])))
        self.template['final_compilation']['translation_units'][0]['dependency_report'] = bad_dependency
        self.publish()
        self.rejected()

    def test_literal_lua_alias_rows_and_implicit_libraries_are_kept_separate(self):
        self.assertEqual(10, sum('original_path' not in row for row in self.template['sources']))
        current_paths = {row['path'] for row in self.template['current_source_inputs']}
        self.assertTrue(all(row['original_path'] not in current_paths for row in self.template['implicit_libraries']))
        self.validate()
        Path(self.template['sources'][-1]['path']).unlink()
        self.rejected()

    def test_cpp_before_annotation_never_waives_a_changed_live_source(self):
        before = self.source_revisions[0]['before']
        historical_live_row = dict(path=before['original_path'], bytes=before['bytes'], sha256=before['sha256'])
        self.publish({'build': lambda value: value.update(foreign_live_source_before=historical_live_row)})
        self.rejected()

    def test_operational_or_metadata_exceptions_cannot_be_rebound_to_cpp(self):
        def operation(value):
            row = value['revisions'][0]
            row['before']['path'] = row['after']['path'] = str(self.project / SOURCE_PATHS[0])
        self.publish({'ledger': operation})
        self.rejected()
        def metadata(value):
            row = value['changed_metadata'][0]
            row['before']['path'] = row['after']['path'] = str(self.project / SOURCE_PATHS[0])
        self.publish({'publication': metadata})
        self.rejected()

    def test_operational_exceptions_cannot_intersect_current_or_compiler_sources(self):
        for inventory, field in (('compiler_inputs', 'original_path'), ('sources', 'original_source')):
            with self.subTest(inventory=inventory):
                self.publish({'build': lambda value: value[inventory][0].update(
                    {field: str(self.project / OPERATIONAL_PATHS[0])})})
                self.rejected()
        self.publish({'build': lambda value: value['current_source_inputs'].__setitem__(
            0, copy.deepcopy(self.operational_revisions[0]['after']))})
        self.rejected()

    def test_backup_bytes_and_foreign_metadata_paths_are_not_generic_exceptions(self):
        for revision in (self.source_revisions[0], self.old_operational[0], self.old_metadata[0]):
            with self.subTest(history=revision['category']):
                self.reject_changed_file(revision['before']['backup']['path'])
        for revision in (self.operational_revisions[0], self.publication_revisions[0]):
            self.reject_changed_file(revision['backup']['path'])
        def foreign(value):
            row = value['changed_metadata'][0]
            row['before']['path'] = row['after']['path'] = str(self.project / 'docs/unrelated.md')
        self.publish({'publication': foreign})
        self.rejected()

    def test_registry_scope_cannot_claim_sdk_restore_or_full_ui_execution(self):
        for stage, field in (('attestation', 'native_restore_approved'),
                             ('attestation', 'sdk_restore_verified'),
                             ('run', 'host_or_sdk_or_window_executed'),
                             ('audit', 'host_or_sdk_or_window_executed')):
            with self.subTest(stage=stage, field=field):
                self.publish({stage: lambda value: value.update({field: True})})
                self.rejected()


class OriginalWorldHudRegistryTests(unittest.TestCase):
    def test_actual_registered_identity_and_source_proof_scope(self):
        spec = retained.registered_host_spec(HUD_BUILD_ID)
        self.assertIsNotNone(spec)
        self.assertEqual(HUD_BUILD_ID, spec['build_id'])
        self.assertEqual('evidence/ui_window_host/%s/build_result.json' % HUD_BUILD_ID,
                         spec['report_path'])
        self.assertEqual(HUD_REPORT_SHA, spec['report_sha256'])
        self.assertEqual(HUD_EXECUTABLE_SHA, spec['executable_sha256'])
        self.assertEqual(549, spec['compiler_dependency_count'])
        self.assertEqual(592, spec['current_source_count'])
        self.assertEqual(85, spec['source_manifest_count'])
        self.assertEqual((465, 266, 270, 279, 301), tuple(spec['dependency_counts']))

    def test_registry_results_are_fresh_including_nested_mutable_values(self):
        first = retained.registered_host_spec(HUD_BUILD_ID)
        self.assertIsNotNone(first)
        expected = copy.deepcopy(first)
        for value in first.values():
            if type(value) in (dict, list, set):
                value.clear()
        first['report_sha256'] = '0' * 64
        first['build_id'] = 'unregistered'
        self.assertEqual(expected, retained.registered_host_spec(HUD_BUILD_ID))

    def test_unknown_builds_reject_before_any_native_process(self):
        with mock.patch.object(subprocess, 'Popen', side_effect=AssertionError('No native execution')):
            for build_id in ('', None, 'unregistered', HUD_BUILD_ID + '_copy'):
                with self.subTest(build_id=build_id):
                    self.assertIsNone(retained.registered_host_spec(build_id))
                    with self.assertRaises(RuntimeError):
                        retained.validate_retained_host_runtime({'build_id': build_id}, PROJECT)
        self.assertIsNotNone(retained.registered_host_spec(retained.BUILD_ID))
        self.assertIsNotNone(retained.registered_host_spec(retained.RESTORE_BUILD_ID))


if __name__ == '__main__':
    unittest.main()
