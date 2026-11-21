"""Portable retained-input regression fixtures; no Host or SDK image is run."""
from __future__ import annotations

import copy
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


sys.dont_write_bytecode = True
PROJECT = Path(__file__).absolute().parents[1]
sys.path.insert(0, str(PROJECT / 'tools'))
import retained_host_runtime_input as retained

RUNNER_PATH = PROJECT / 'tools/run_interactive_game.py'
SPEC = importlib.util.spec_from_file_location('retained_host_input_runner_tests', RUNNER_PATH)
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)

REJECTIONS = (RuntimeError, OSError, ValueError, EOFError)
STAGE_SUFFIX = 'evidence/native_save_archive/host_relink/18bbd0dd26e70e623276'
METADATA = ('evidence/save_menu/20261013_original_screen/current_progress.json',
            'docs/M7_RETAIL_SAVE_BOUNDARY.md')


def reference(path, payload=None):
    if payload is None:
        payload = Path(path).read_bytes()
    return dict(path=str(path), bytes=len(payload), sha256=hashlib.sha256(payload).hexdigest())


def fixture_pe():
    """An independent tiny PE32+ header used only as a hash-bound file input."""
    raw = bytearray(1024)
    raw[:2] = b'MZ'
    struct.pack_into('<I', raw, 60, 128)
    raw[128:132] = b'PE\0\0'
    struct.pack_into('<HHIIIHH', raw, 132, 0x8664, 1, 0, 0, 0, 240, 0x22)
    struct.pack_into('<H', raw, 152, 0x20b)
    struct.pack_into('<I', raw, 168, 0x1000)
    struct.pack_into('<Q', raw, 176, 0x140000000)
    struct.pack_into('<II', raw, 184, 4096, 512)
    struct.pack_into('<II', raw, 208, 8192, 512)
    struct.pack_into('<H', raw, 220, 3)
    struct.pack_into('<I', raw, 260, 16)
    raw[392:397] = b'.text'
    struct.pack_into('<IIII', raw, 400, 1, 4096, 512, 512)
    struct.pack_into('<I', raw, 428, 0x60000020)
    raw[512] = 0xc3
    return bytes(raw)


class RetainedHostRuntimeInputTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='_retained_host_inputs_', dir=PROJECT)
        self.addCleanup(temporary.cleanup)
        self.project = Path(temporary.name).absolute()
        self.build_root = self.project / 'Build/UiWindowHost' / retained.BUILD_ID
        self.stage = self.project / STAGE_SUFFIX
        self.kept = {}
        self.object_payloads = {}
        self.template = self.make_build()
        self.revision_template = self.make_metadata()
        self.publish()

    def write(self, relative, raw, *, keep=None):
        path = self.project / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        row = reference(path, raw)
        if keep:
            self.kept[keep] = row
        return row

    def document(self, relative, value):
        raw = (json.dumps(value, sort_keys=True, ensure_ascii=True) + '\n').encode('ascii')
        return self.write(relative, raw)

    def make_build(self):
        executable = self.write(self.build_root / 'final/ZeroSisHost_x64.exe', fixture_pe(), keep='PE')
        source = self.write(self.build_root / 'frozen/source.h', b'// Portable fixture source.\n', keep='source')
        library = self.write(self.build_root / 'frozen/provider.lib', b'!<arch>\nfixture\n', keep='library')
        units, objects = [], []
        for index, (name, stem) in enumerate(retained.UNITS):
            directory = self.build_root / 'final' / ('tu_%02d_%s' % (index, name))
            payload = b'opaque retired object: ' + stem.encode('ascii')
            obj = reference(directory / 'obj' / (stem + '.obj'), payload)
            self.object_payloads[obj['path']] = payload
            response = self.write(directory / (name + '.compile.rsp'), b'/c fixture.cpp\n', keep=name + ' rsp')
            dependency = self.document(directory / (name + '.sourceDependencies.json'),
                dict(Data=dict(Source=source['path'], Includes=[])))
            self.kept[name + ' dependencies'] = dependency
            log = self.write(self.stage / ('compile_' + name + '.log'), b'fixture compile receipt\n', keep=name + ' log')
            units.append(dict(translation_unit=name, returncode=0, response=response,
                dependency_report=dependency, log=log, object=obj))
            objects.append(obj)
        link_response = self.write(self.build_root / 'final/link_retry01.rsp', b'fixture link response\n', keep='link rsp')
        link_log = self.write(self.stage / 'link_retry01/link.log', b'fixture link receipt\n', keep='link log')
        return dict(schema='zerosis.ui_window_host_build.v1', build_id=retained.BUILD_ID,
            status='UI_WINDOW_HOST_CANDIDATE_BUILT', error=None, source_inputs_unchanged=True,
            provider_inputs_unchanged=True, executable=executable, sources=[source], compiler_inputs=[source],
            libraries=[library], final_compilation=dict(translation_units=units),
            link_response=link_response, link_log=link_log,
            link_snapshot=dict(response=link_response, objects_before=objects,
                               objects_after=copy.deepcopy(objects), returncode=0))

    def make_metadata(self):
        revisions = []
        for index, relative in enumerate(METADATA):
            before_bytes = ('historical metadata %d\n' % index).encode('ascii')
            after = self.write(relative, ('published metadata %d\n' % index).encode('ascii'))
            before = reference(self.project / relative, before_bytes)
            backup = self.write(self.stage / ('publication/metadata_%d.before.gz' % index),
                gzip.compress(before_bytes, mtime=0), keep='metadata backup %d' % index)
            revisions.append(dict(before=before, after=after, backup=backup, backup_roundtrip_verified=True))
        return revisions

    def publish(self, changes=None):
        """Resign the small test authority graph to exercise semantic guards."""
        changes = changes or {}
        def changed(name, value):
            if name in changes:
                changes[name](value)
            return value
        revisions = changed('revisions', copy.deepcopy(self.revision_template))
        build = copy.deepcopy(self.template)
        build['historical_metadata'] = [copy.deepcopy(row['before']) for row in revisions]
        self.build = changed('build', build)
        self.report_ref = self.document('evidence/ui_window_host/%s/build_result.json' % retained.BUILD_ID, self.build)
        proof = changed('attestation', dict(status='PASS_RELINKED_NATIVE_HOST_STATIC_ATTESTATION',
            build_result=copy.deepcopy(self.report_ref), actual_coff_objects=[dict(translation_unit=unit['translation_unit'],
            object=copy.deepcopy(unit['object'])) for unit in self.build['final_compilation']['translation_units']]))
        self.attestation_ref = self.document(self.stage / 'attestation.json', proof)
        plan = changed('plan', dict(build_result=copy.deepcopy(self.report_ref), attestation=copy.deepcopy(self.attestation_ref),
            targets=copy.deepcopy(self.template['link_snapshot']['objects_before'])))
        self.plan_ref = self.write(self.stage / 'publication/retirement_plan.json.gz',
            gzip.compress(json.dumps(plan, sort_keys=True).encode('ascii'), mtime=0))
        retirement = changed('retirement', dict(
            status='PASS_FIVE_ATTESTED_OBJECTS_AND_TWO_PRECOMPILE_FAILED_SNAPSHOTS_RETIRED',
            plan=copy.deepcopy(self.plan_ref), attestation=copy.deepcopy(self.attestation_ref)))
        self.retirement_ref = self.document(self.stage / 'publication/retirement.json', retirement)
        post = changed('post', dict(authorized_metadata_revisions=copy.deepcopy(revisions)))
        self.post_ref = self.document(self.stage / 'publication/post.json', post)
        update = changed('update', dict(build_result=copy.deepcopy(self.report_ref),
            attestation=copy.deepcopy(self.attestation_ref), cleanup=copy.deepcopy(self.retirement_ref),
            changed_metadata=copy.deepcopy(revisions)))
        self.update_ref = self.document(self.stage / 'publication/progress_update.json', update)
        audit = changed('audit', dict(status='PASS_FRESH_CURRENT_HOST_LINK_PUBLICATION_AND_RETIREMENT_AUDIT',
            human_escape_stop_respected=True, new_host_runtime_executed=False,
            attestation=copy.deepcopy(self.attestation_ref), post=copy.deepcopy(self.post_ref),
            executable=copy.deepcopy(self.build['executable'])))
        self.audit_ref = self.document(self.stage / 'publication/final_audit.json', audit)

    def validate(self, *, integration=False, build=None):
        value = self.build if build is None else build
        before = copy.deepcopy(value)
        report_bytes = Path(self.report_ref['path']).read_bytes()
        pins = dict(REPORT_SHA=self.report_ref['sha256'], AUDIT_SHA=self.audit_ref['sha256'],
                    UPDATE_SHA=self.update_ref['sha256'])
        try:
            with mock.patch.multiple(retained, **pins), mock.patch.object(subprocess, 'Popen',
                    side_effect=AssertionError('No child process is allowed in a retained-input test')):
                if integration:
                    with mock.patch.object(runner, 'PROJECT', self.project), mock.patch.object(runner,
                            'check_artifacts', side_effect=AssertionError('Current build must use the new gate')):
                        return runner.check_host_runtime_artifacts(value)
                return retained.validate_retained_host_runtime(value, self.project)
        finally:
            self.assertEqual(before, value, 'Validation mutated the sealed report')
            self.assertEqual(report_bytes, Path(self.report_ref['path']).read_bytes(),
                             'Validation rewrote the sealed report file')

    def rejected(self, *, integration=False, build=None):
        with self.assertRaises(REJECTIONS):
            self.validate(integration=integration, build=build)

    def test_exact_retired_five_and_two_backups_are_accepted(self):
        result = self.validate()
        self.assertEqual('RETAINED_HOST_RUNTIME_INPUTS_WITH_ATTESTED_FINAL_OBJECT_RETIREMENT', result['scope'])
        self.assertEqual(2, result['historical_metadata_backups_verified'])
        self.assertEqual([], result['absent_discovery_objects'])
        self.assertEqual([dict(original_path=row['path'], sha256=row['sha256'], bytes=row['bytes'])
            for row in self.template['link_snapshot']['objects_before']], result['absent_final_objects'])
        self.assertIs(result['host_executed'], False)
        self.assertIs(result['save_compatibility_verified'], False)

    def test_runner_dispatches_current_build_to_the_retained_gate(self):
        self.assertEqual(self.validate(), self.validate(integration=True))

    def test_each_retained_artifact_must_keep_its_exact_bytes(self):
        for label, row in self.kept.items():
            with self.subTest(artifact=label):
                path = Path(row['path'])
                original = path.read_bytes()
                try:
                    path.write_bytes(original + b'changed')
                    self.rejected(integration=True)
                finally:
                    path.write_bytes(original)

    def test_each_retained_artifact_must_remain_present(self):
        for label, row in self.kept.items():
            with self.subTest(artifact=label):
                path = Path(row['path'])
                original = path.read_bytes()
                try:
                    path.unlink()
                    self.rejected()
                finally:
                    path.write_bytes(original)

    def test_pe_machine_and_optional_header_drift_are_rejected_by_identity(self):
        path = Path(self.kept['PE']['path'])
        original = path.read_bytes()
        # This gate rehashes an attested PE; it does not replace the PE verifier.
        for offset, value in ((132, 0x4c), (152, 0xfa), (153, 0x01)):
            with self.subTest(offset=offset):
                changed = bytearray(original)
                changed[offset] = value
                try:
                    path.write_bytes(changed)
                    self.rejected()
                finally:
                    path.write_bytes(original)

    def test_each_authority_receipt_must_remain_byte_identical(self):
        evidence = (self.report_ref, self.audit_ref, self.update_ref,
                    self.attestation_ref, self.post_ref, self.retirement_ref, self.plan_ref)
        for row in evidence:
            with self.subTest(receipt=Path(row['path']).name):
                path = Path(row['path'])
                original = path.read_bytes()
                try:
                    path.write_bytes(original + b' ')
                    self.rejected(integration=True)
                finally:
                    path.write_bytes(original)

    def test_missing_authority_receipt_is_rejected(self):
        for row in (self.audit_ref, self.attestation_ref, self.plan_ref,
                    self.retirement_ref, self.post_ref, self.update_ref):
            with self.subTest(receipt=Path(row['path']).name):
                path = Path(row['path'])
                original = path.read_bytes()
                try:
                    path.unlink()
                    self.rejected()
                finally:
                    path.write_bytes(original)

    def test_retired_objects_must_be_absent_even_when_their_bytes_match(self):
        for row in self.template['link_snapshot']['objects_before']:
            with self.subTest(object=Path(row['path']).name):
                path = Path(row['path'])
                path.parent.mkdir(parents=True, exist_ok=True)
                try:
                    path.write_bytes(self.object_payloads[row['path']])
                    self.rejected()
                finally:
                    path.unlink()

    def test_arbitrary_missing_artifact_is_not_a_retirement_exception(self):
        missing = reference(self.build_root / 'final/arbitrary_missing.obj', b'not attested')
        self.publish({
            'build': lambda value: value.update(unrelated_artifact=copy.deepcopy(missing)),
            'plan': lambda value: value['targets'].append(copy.deepcopy(missing)),
        })
        self.rejected(integration=True)

    def test_nonregular_retained_source_is_rejected(self):
        path = Path(self.kept['source']['path'])
        original = path.read_bytes()
        path.unlink()
        path.mkdir()
        try:
            self.rejected()
        finally:
            path.rmdir()
            path.write_bytes(original)

    def test_noncanonical_artifact_paths_are_rejected(self):
        source = self.kept['source']
        bad_paths = ('relative/source.h', str(Path(source['path']).parent / '..' / 'frozen/source.h'))
        for path in bad_paths:
            with self.subTest(path=path):
                extra = dict(source, path=path)
                self.publish({'build': lambda value: value.update(extra_reference=extra)})
                self.rejected()

    def test_retired_translation_unit_shape_and_returncodes_are_strict(self):
        def wrong_name(value):
            value['final_compilation']['translation_units'][0]['translation_unit'] = 'other'
        def wrong_order(value):
            value['final_compilation']['translation_units'].reverse()
        def missing_unit(value):
            value['final_compilation']['translation_units'].pop()
        for label, change in (('name', wrong_name), ('order', wrong_order), ('count', missing_unit)):
            with self.subTest(case=label):
                self.publish({'build': change})
                self.rejected()
        for returncode in (1, -1, False, '0'):
            with self.subTest(returncode=returncode, value_type=type(returncode).__name__):
                def wrong_returncode(value):
                    value['final_compilation']['translation_units'][0]['returncode'] = returncode
                self.publish({'build': wrong_returncode})
                self.rejected()

    def test_retirement_and_attestation_must_bind_the_same_five_objects(self):
        def absent_target(value):
            value['targets'].pop()
        def changed_target_bytes(value):
            value['targets'][0]['bytes'] += 1
        def changed_object_hash(value):
            value['actual_coff_objects'][0]['object']['sha256'] = '0' * 64
        def unrelated_object_path(value):
            value['final_compilation']['translation_units'][0]['object']['path'] = str(
                self.build_root / 'final/other.obj')
        changes = (('plan', absent_target), ('plan', changed_target_bytes),
                   ('attestation', changed_object_hash), ('build', unrelated_object_path))
        for stage, change in changes:
            with self.subTest(stage=stage, change=change.__name__):
                self.publish({stage: change})
                self.rejected()

    def test_publication_scope_and_cross_build_proofs_are_not_transferable(self):
        cases = (
            ('audit', 'human_escape_stop_respected', False),
            ('audit', 'new_host_runtime_executed', True),
            ('audit', 'status', 'OTHER_PUBLICATION'),
            ('attestation', 'status', 'OTHER_ATTESTATION'),
            ('retirement', 'status', 'OTHER_RETIREMENT'),
        )
        for stage, key, value in cases:
            with self.subTest(stage=stage, key=key):
                self.publish({stage: lambda document: document.update({key: value})})
                self.rejected()
        for stage, key in (('attestation', 'build_result'), ('update', 'build_result'),
                           ('update', 'attestation'), ('retirement', 'attestation'),
                           ('plan', 'attestation'), ('plan', 'build_result'), ('audit', 'executable')):
            with self.subTest(stage=stage, cross_build_reference=key):
                def wrong_binding(document):
                    document[key]['sha256'] = '1' * 64
                self.publish({stage: wrong_binding})
                self.rejected()

    def test_backup_contents_must_restore_the_exact_historical_metadata(self):
        bad_backup = self.write(self.stage / 'publication/wrong.before.gz',
            gzip.compress(b'wrong historical bytes\n', mtime=0))
        def wrong_backup(revisions):
            revisions[0]['backup'] = bad_backup
        self.publish({'revisions': wrong_backup})
        self.rejected()

    def test_metadata_revision_requires_both_exact_authorized_paths(self):
        def arbitrary_path(revisions):
            for key in ('before', 'after'):
                revisions[0][key]['path'] = str(self.project / 'docs/arbitrary_metadata.md')
        def mismatched_paths(revisions):
            revisions[0]['after']['path'] = revisions[1]['after']['path']
        def duplicate_path_with_distinct_historical_bytes(revisions):
            # Both backups still correctly match their distinct before hashes.
            for key in ('before', 'after'):
                revisions[1][key]['path'] = revisions[0][key]['path']
        def missing_revision(revisions):
            revisions.pop()
        for change in (arbitrary_path, mismatched_paths,
                       duplicate_path_with_distinct_historical_bytes, missing_revision):
            with self.subTest(change=change.__name__):
                self.publish({'revisions': change})
                self.rejected()

    def test_metadata_backup_claim_and_post_must_agree(self):
        self.publish({'revisions': lambda rows: rows[0].update(backup_roundtrip_verified=False)})
        self.rejected()
        self.publish({'post': lambda document: document['authorized_metadata_revisions'].pop()})
        self.rejected()

    def test_live_metadata_may_evolve_without_replacing_its_build_time_identity(self):
        # Only the two backed-up historical identities are exempt, not all docs.
        for relative in METADATA:
            (self.project / relative).write_bytes(b'later legitimate published metadata\n')
        result = self.validate()
        self.assertEqual(2, result['historical_metadata_backups_verified'])

    def test_repeated_retained_reference_cannot_override_the_verified_size(self):
        for size in (self.kept['source']['bytes'] + 1, True, '1'):
            with self.subTest(size=size, value_type=type(size).__name__):
                extra = dict(self.kept['source'], bytes=size)
                self.publish({'build': lambda value: value.update(late_source_reference=extra)})
                self.rejected()

    def test_input_report_must_match_pinned_json_without_bool_integer_coercion(self):
        for key, value in (('source_inputs_unchanged', 1), ('build_id', 'another_build')):
            with self.subTest(field=key):
                changed = copy.deepcopy(self.build)
                changed[key] = value
                self.rejected(build=changed)
        changed = copy.deepcopy(self.build)
        changed['final_compilation']['translation_units'][0]['returncode'] = False
        self.rejected(integration=True, build=changed)

    def test_older_builds_keep_the_existing_artifact_validation_path(self):
        old = dict(build_id='20261016T120000Z_012345abcdef', note='legacy fixture')
        original = copy.deepcopy(old)
        with (mock.patch.object(retained, 'validate_retained_host_runtime',
                side_effect=AssertionError('Unrelated builds cannot use a current-build exemption')),
                mock.patch.object(runner, 'check_artifacts') as check,
                mock.patch.object(subprocess, 'Popen', side_effect=AssertionError('No child process'))):
            self.assertEqual(dict(scope='RETAINED_HOST_RUNTIME_INPUTS', absent_discovery_objects=[]),
                             runner.check_host_runtime_artifacts(old))
        check.assert_called_once_with(old)
        self.assertEqual(original, old)


if __name__ == '__main__':
    unittest.main()
