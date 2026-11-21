"""Safety contracts for the font-only deduplicator, using tiny isolated files."""
from pathlib import Path
from contextlib import redirect_stdout
import gzip
import io
import json
import os
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import deduplicate_runtime_font_dds as d


class FontDedupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='fd-', dir=d.PROJECT)
        self.root = Path(self.temp.name).resolve()
        self.output = self.root / 'evidence/storage/font_dds_dedup/test'
        self.output.mkdir(parents=True)
        self.texture = (self.root / 'Build/InteractiveGameRuntime/20261010T000000Z_123456abcdef'
                        '/sessions/0123456789abcdef0123456789abcdef/play-ui-1/textures')
        self.texture.mkdir(parents=True)

    def tearDown(self):
        self.temp.cleanup()

    def candidate(self, name, payload=b'DDS tiny-font-payload'):
        p = self.texture / name
        p.write_bytes(payload)
        return d.full_record(p)

    def setup_plan(self):
        rows = [self.candidate('font-a.dds'), self.candidate('font-b.dds')]
        groups, assigned, held = d.group_plan(rows, self.root)
        self.assertFalse(held)
        plan = {'root': str(self.root), 'groups': groups, 'protection': [],
                'old_unique_allocated_bytes': sum(row['allocated_bytes'] for row in rows),
                'metadata_contract': 'TEST', 'runtime_paths': [str(self.texture.parents[3])], 'manifests': []}
        return plan, assigned

    def invoke(self, plan, rows):
        with patch.object(d, 'load_plan', return_value=(self.output / 'plan.json', plan, rows)), \
                patch.object(d, 'no_active_work'), patch.object(d, 'verify_inputs'):
            d.apply_plan(self.output / 'plan.json', 'a' * 64, root=self.root)

    def test_exact_target_boundary_and_different_payloads(self):
        left = self.candidate('same-size-a.dds', b'DDS aaaa')
        right = self.candidate('same-size-b.dds', b'DDS bbbb')
        self.assertNotEqual(left['sha256'], right['sha256'])
        self.assertEqual(d.group_plan([left, right], self.root)[1], [])
        protected = self.root / 'Source/private.dds'
        protected.parent.mkdir()
        protected.write_bytes(b'DDS aaaa')
        with self.assertRaisesRegex(ValueError, 'exact retained'):
            d.target_path(protected, self.root)

    def test_already_shared_identity_is_held(self):
        row = self.candidate('shared.dds')
        sibling = self.texture / 'shared-alias.dds'
        os.link(row['path'], sibling)
        rows = [d.full_record(Path(row['path'])), d.full_record(sibling)]
        self.assertEqual(d.group_plan(rows, self.root)[1], [])

    def test_wrong_plan_seal_is_rejected_before_apply(self):
        plan = self.output / 'plan.json'
        plan.write_text('{}', encoding='utf8')
        with self.assertRaisesRegex(ValueError, 'Approved plan SHA'):
            d.load_plan(plan, '0' * 64, self.root)

    @unittest.skipUnless(os.name == 'nt', 'Windows process guard')
    def test_process_guard_rechecks_exit_and_same_or_reused_known_nonwriter(self):
        candidate = {'Id': 1234, 'CreationTime': 'first', 'Reason': 'PYTHON_COMMAND_LINE_UNAVAILABLE'}
        with patch.object(d, 'process_query', side_effect=[[candidate], []]) as query:
            self.assertEqual(d.no_active_work(self.root)['exited_candidates_rechecked'], 1)
            self.assertEqual(query.call_args.kwargs['ZS_FONT_RECHECK_PID'], '1234')
        for created in ('first', 'reused'):
            with self.subTest(created=created):
                live = {**candidate, 'CreationTime': created, 'Reason': 'KNOWN_NON_WRITER'}
                with patch.object(d, 'process_query', side_effect=[[candidate], [live]]):
                    self.assertEqual(d.no_active_work(self.root)['exited_candidates_rechecked'], 0)

    @unittest.skipUnless(os.name == 'nt', 'Windows process guard')
    def test_process_guard_blocks_live_unknown_writers_and_inaccessible_recheck(self):
        candidate = {'Id': 1234, 'CreationTime': 'first', 'Reason': 'PYTHON_COMMAND_LINE_UNAVAILABLE'}
        for created in ('first', 'reused', None):
            for reason in ('PYTHON_COMMAND_LINE_UNAVAILABLE', 'PYTHON_RUNTIME_WRITER',
                           'PROJECT_NATIVE_PROCESS', 'PROCESS_IDENTITY_UNAVAILABLE'):
                with self.subTest(created=created, reason=reason):
                    live = {**candidate, 'CreationTime': created, 'Reason': reason}
                    with patch.object(d, 'process_query', side_effect=[[candidate], [live]]):
                        with self.assertRaisesRegex(ValueError, 'process is active'):
                            d.no_active_work(self.root)
        with patch.object(d, 'process_query', side_effect=[[candidate], PermissionError('CIM inaccessible')]):
            with self.assertRaises(PermissionError):
                d.no_active_work(self.root)

    @unittest.skipUnless(os.name == 'nt', 'Actual Windows CIM process lookup')
    def test_process_guard_real_cim_recheck_of_current_nonwriter(self):
        query = d.process_query
        candidate = {'Id': os.getpid(), 'CreationTime': 'initial', 'Reason': 'PYTHON_COMMAND_LINE_UNAVAILABLE'}

        def intercepted(command, root, **environment):
            return query(command, root, **environment) if environment else [candidate]

        with patch.object(d, 'process_query', side_effect=intercepted):
            self.assertEqual(d.no_active_work(self.root)['status'], 'NO_ACTIVE_PROJECT_NATIVE_PROCESS')
        self.assertEqual(d.no_active_compression(self.root)['status'], 'NO_ACTIVE_STANDARD_COMPRESSION_PROCESS')

    def test_compression_refresh_accepts_only_exact_attribute_addition_and_lower_allocation(self):
        before = self.candidate('compressible.dds')
        accepted = {**before, 'attributes': before['attributes'] | d.COMPRESSED,
                    'allocated_bytes': before['allocated_bytes'] - 1}
        self.assertTrue(d.compression_only_refresh(before, accepted))
        mutations = {'path': str(self.texture / 'different.dds'), 'sha256': '0' * 64,
                     'bytes': before['bytes'] + 1, 'device': before['device'] + 1,
                     'file_id': before['file_id'] + 1, 'mtime_ns': before['mtime_ns'] + 1,
                     'links': before['links'] + 1,
                     'attributes': accepted['attributes'] | d.READONLY,
                     'allocated_bytes': before['allocated_bytes']}
        for field, value in mutations.items():
            with self.subTest(field=field):
                self.assertFalse(d.compression_only_refresh(before, {**accepted, field: value}))
        self.assertFalse(d.compression_only_refresh(accepted, {**accepted, 'allocated_bytes': 1}))

    @unittest.skipUnless(os.name == 'nt', 'Windows continuation identities')
    def test_compression_refresh_is_opt_in_and_records_old_and_new_metadata(self):
        plan, rows = self.setup_plan()
        original_record = d.full_record

        def stop_before_second(path):
            if str(path) == rows[1]['path']:
                raise RuntimeError('stop before second')
            return original_record(path)

        with patch.object(d, 'full_record', side_effect=stop_before_second):
            with self.assertRaisesRegex(RuntimeError, 'stop before second'):
                self.invoke(plan, rows)
        events = [json.loads(line) for line in (self.output / 'apply-journal.jsonl').read_text('utf8').splitlines()]

        def compression_metadata(path):
            record = original_record(path)
            if str(path) == rows[1]['path']:
                return {**record, 'attributes': record['attributes'] | d.COMPRESSED,
                        'allocated_bytes': record['allocated_bytes'] - 1}
            return record

        with patch.object(d, 'full_record', side_effect=compression_metadata):
            with self.assertRaisesRegex(ValueError, 'Remaining original changed'):
                d.partition_remaining(plan, rows, events, self.root)
            remaining, completed, anchors, groups, refreshed = d.partition_remaining(
                plan, rows, events, self.root, accept_compression_only=True)
        self.assertEqual((len(remaining), len(completed), len(refreshed)), (1, 1, 1))
        self.assertEqual(refreshed[0]['before']['attributes'], rows[1]['attributes'])
        self.assertEqual(refreshed[0]['after']['sha256'], rows[1]['sha256'])
        self.assertEqual(refreshed[0]['after']['allocated_bytes'], remaining[0]['allocated_bytes'])
        self.assertEqual(remaining[0]['allocated_bytes'], rows[1]['allocated_bytes'] - 1)

    @unittest.skipUnless(os.name == 'nt', 'Windows continuation cache identities')
    def test_continuation_preserves_completed_alias_and_fills_existing_shard(self):
        plan, rows = self.setup_plan()
        third = self.candidate('font-c.dds')
        groups, rows, _ = d.group_plan(rows + [third], self.root)
        plan.update(groups=groups, target_files=3,
                    old_unique_allocated_bytes=sum(row['allocated_bytes'] for row in rows))
        original_record = d.full_record

        def stop_before_second(path):
            if str(path) == rows[1]['path']:
                raise RuntimeError('stop before next replacement')
            return original_record(path)

        with patch.object(d, 'full_record', side_effect=stop_before_second):
            with self.assertRaisesRegex(RuntimeError, 'stop before next'):
                self.invoke(plan, rows)
        old_journal = self.output / 'apply-journal.jsonl'
        old_hash = d.digest(old_journal)
        events = [json.loads(line) for line in old_journal.read_text('utf8').splitlines()]
        remaining, completed, anchors, groups, refreshed = d.partition_remaining(plan, rows, events, self.root)
        self.assertFalse(refreshed)
        self.assertEqual((len(remaining), len(completed), len(anchors)), (2, 1, 1))
        self.assertEqual((groups[0]['starting_links'], groups[0]['final_links']), (2, 4))
        self.assertFalse(groups[0]['new_cache'])
        self.output = self.output / 'continuation'
        self.output.mkdir()
        ledger = self.output / 'completed.jsonl.gz'
        with gzip.open(ledger, 'wt', encoding='utf8') as stream:
            for row in completed:
                stream.write(json.dumps(row) + '\n')
        continued = {**plan, 'groups': groups, 'target_files': 2,
                     'old_unique_allocated_bytes': sum(row['allocated_bytes'] for row in remaining),
                     'continuation': {'history': [], 'completed_files': 1, 'completed_ledger': d.artifact(ledger),
                                      'existing_anchors': anchors, 'original_target_count': 3}}
        with patch.object(d, 'no_active_work'):
            d.verify_inputs(continued, remaining, self.root)

        def stop_before_third(path):
            if str(path) == rows[2]['path']:
                raise RuntimeError('second guarded stop')
            return original_record(path)

        with patch.object(d, 'full_record', side_effect=stop_before_third):
            with self.assertRaisesRegex(RuntimeError, 'second guarded stop'):
                self.invoke(continued, remaining)
        second_journal = self.output / 'apply-journal.jsonl'
        second_hash = d.digest(second_journal)
        parent_targets = self.output / 'targets.jsonl.gz'
        with gzip.open(parent_targets, 'wt', encoding='utf8') as stream:
            for row in remaining:
                stream.write(json.dumps(row) + '\n')
        continued['ledger'] = d.artifact(parent_targets)
        parent_path = self.output / 'plan.json'
        parent_path.write_text(json.dumps(continued), encoding='utf8')
        sealed_tool = self.output / 'sealed.py'
        sealed_tool.write_text('# isolated historical source', encoding='utf8')
        third_output = self.output / 'remaining'
        with patch.object(d, 'load_plan', return_value=(parent_path, continued, remaining)), \
                patch.object(d, 'no_active_work', return_value={}), redirect_stdout(io.StringIO()):
            d.write_remaining_plan(parent_path, 'a' * 64, sealed_tool, third_output, self.root)
        third_plan = d.read_json(third_output / 'plan.json')
        third_rows = d.read_ledger(third_plan['ledger'], self.root)
        self.assertIn(continued['continuation']['completed_ledger'], third_plan['continuation']['history'])
        self.assertEqual((len(third_rows), third_plan['continuation']['completed_files']), (1, 2))
        self.assertEqual((third_plan['groups'][0]['starting_links'], third_plan['groups'][0]['final_links']), (3, 4))
        saved_ledger = ledger.read_bytes()
        try:
            ledger.write_bytes(b'changed earlier completed ledger')
            with self.assertRaisesRegex(ValueError, 'history changed'):
                d.check_completed(third_plan, self.root)
        finally:
            ledger.write_bytes(saved_ledger)
        self.output = third_output
        self.invoke(third_plan, third_rows)
        with patch.object(d, 'no_active_work'):
            d.verify_inputs(third_plan, third_rows, self.root, resumed=True)
        self.assertEqual(d.digest(old_journal), old_hash)
        self.assertEqual(d.digest(second_journal), second_hash)
        self.assertTrue(d.same_identity(d.snapshot(Path(completed[0]['path'])), completed[0]))
        self.assertEqual(d.snapshot(Path(anchors[0]['path']))['links'], 4)

    def test_shard_capacity_is_bounded(self):
        row = self.candidate('template.dds')
        rows = [{**row, 'path': str(self.texture / f'font-{n}.dds'), 'file_id': n + 1}
                for n in range(d.MEMBERS_PER_SHARD + 1)]
        groups, assigned, _ = d.group_plan(rows, self.root)
        self.assertEqual(len(groups), 2)
        self.assertEqual(len(assigned), len(rows))
        self.assertTrue(all(group['final_links'] <= d.LINK_CAP for group in groups))

    @unittest.skipUnless(os.name == 'nt', 'Windows hardlink attributes and disposition')
    def test_success_keeps_bytes_and_cleans_temporaries(self):
        plan, rows = self.setup_plan()
        self.invoke(plan, rows)
        anchor = Path(rows[0]['anchor'])
        for row in rows:
            target = Path(row['path'])
            self.assertEqual(d.digest(target), row['sha256'])
            self.assertTrue(d.same_identity(d.snapshot(target), d.snapshot(anchor)))
            self.assertTrue(d.snapshot(target)['attributes'] & d.READONLY)
            self.assertTrue(all(not p.exists() for p in d.temp_paths(target, 'a' * 64)))

    @unittest.skipUnless(os.name == 'nt', 'Windows readonly rollback')
    def test_failed_post_replace_check_restores_original_and_preserves_sibling_attributes(self):
        plan, rows = self.setup_plan()
        original_verify = d.verify_replacement
        seen = []

        def injected(target, anchor, expected):
            original_verify(target, anchor, expected)
            seen.append(target)
            if len(seen) == 2:
                raise RuntimeError('injected after atomic replacement')

        with patch.object(d, 'verify_replacement', side_effect=injected):
            with self.assertRaisesRegex(RuntimeError, 'injected'):
                self.invoke(plan, rows)
        anchor = Path(rows[0]['anchor'])
        self.assertTrue(d.snapshot(anchor)['attributes'] & d.READONLY)
        self.assertTrue(d.snapshot(Path(rows[0]['path']))['attributes'] & d.READONLY)
        self.assertTrue(d.same_identity(d.snapshot(Path(rows[1]['path'])), rows[1]))
        self.assertEqual(d.snapshot(Path(rows[1]['path']))['attributes'], rows[1]['attributes'])
        for row in rows:
            self.assertEqual(d.digest(Path(row['path'])), row['sha256'])
            self.assertTrue(all(not p.exists() for p in d.temp_paths(Path(row['path']), 'a' * 64)))

    @unittest.skipUnless(os.name == 'nt', 'Windows readonly recovery')
    def test_recovery_retains_backup_when_restore_rename_fails(self):
        plan, rows = self.setup_plan()
        row = rows[0]
        target, anchor = Path(row['path']), Path(row['anchor'])
        anchor.parent.mkdir(parents=True)
        anchor.write_bytes(target.read_bytes())
        os.chmod(anchor, stat.S_IREAD)
        fresh, backup = d.temp_paths(target, 'a' * 64)
        os.link(target, backup)
        os.link(anchor, fresh)
        os.replace(fresh, target)
        with patch.object(d.os, 'replace', side_effect=PermissionError('injected recovery rename')):
            with self.assertRaises(PermissionError):
                d.restore_pending(row, 'a' * 64, self.root)
        self.assertTrue(backup.exists())
        self.assertEqual(d.digest(backup), row['sha256'])
        self.assertTrue(d.snapshot(anchor)['attributes'] & d.READONLY)
        d.restore_pending(row, 'a' * 64, self.root)
        self.assertTrue(d.same_identity(d.snapshot(target), row))
        self.assertFalse(backup.exists())


if __name__ == '__main__':
    unittest.main()
