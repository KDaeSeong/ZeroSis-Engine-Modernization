"""Original callback, single-use overwrite grant and renderer regressions."""
import json
import copy
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import unittest
import uuid

from owned_save_overwrite_scene import verify_component
import owned_save_overwrite_scene as scene_module
from ui_pixel_scene import save_menu_contract
from owned_save_delete_scene import verify_component as verify_deletion
from save_menu_scene import verify_component as verify_legacy_save
from load_menu_scene import verify_component as verify_legacy_load


class OwnedSaveOverwriteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = verify_component(include_snapshot=True)

    def test_original_callbacks_and_exclusive_single_use_queue(self):
        self.assertEqual(len(self.result['cases']), 6)
        for row in self.result['cases']:
            with self.subTest(case=row['case']):
                self.assertGreater(row['checks'], 30)
                self.assertEqual(row['capabilityQueries'], 1)
                self.assertEqual(row['timerChanges'], 0)
                self.assertEqual(len(row['deleteCalls']), 0)
                self.assertEqual(len(row['overwriteCalls']), int(row['case'] in ('selected', 'entered', 'native-fault')))
                self.assertEqual([r['kind'] for r in row['requests']],
                                 ['Overwrite', 'Close'] if row['case'] in ('selected', 'entered') else ['Close'])
                self.assertGreaterEqual(len(row['compositorContractStages']), 3)
                self.assertEqual(row['realArchiveWrites'], 0)
                self.assertFalse(row['nativeHostOrGameCoreExecuted'])

    def test_capability_must_be_an_actual_boolean(self):
        with self.assertRaisesRegex(RuntimeError, 'overwrite capability must be a boolean'):
            verify_component(cases=('invalid-capability',))

    def test_protected_sources_and_scratch_cleanup(self):
        self.assertTrue(self.result['original_sources_unchanged'])
        self.assertTrue(self.result['temporary_styles_removed'])
        self.assertTrue(all(row['result']=='REMOVED_ABSENT' for row in self.result['temporary_cleanup']))
        self.assertFalse(self.result['retail_user_state_accessed'])

    def test_renderer_rejects_untyped_ambiguous_or_forged_admission(self):
        original = self.result['snapshots']['selected']['commit-confirmation']
        for field, value in (('localOverwriteBackendBound', 1), ('deleteConfirmationArmed', True),
                             ('confirmationOp', 'delete'), ('saveActionAvailable', False)):
            with self.subTest(field=field):
                changed = copy.deepcopy(original)
                changed['saveMenu'][field] = value
                with self.assertRaises(ValueError):
                    save_menu_contract(changed)

    def test_existing_save_and_load_deletion_contracts(self):
        self.assertEqual(verify_deletion()['status'], 'PASS_ORIGINAL_OWNED_SAVE_DELETE_LUA_FIXTURES')

    def test_legacy_save_and_load_without_overwrite_capability(self):
        self.assertEqual(verify_legacy_save()['status'], 'PASS_ORIGINAL_SAVE_MENU_COMPONENT')
        self.assertEqual(verify_legacy_load()['status'], 'PASS_COMPLETE_ORIGINAL_LOAD_MENU_LUA_FIXTURES')


if __name__ == '__main__':
    program = unittest.main(exit=False)
    if program.result.wasSuccessful():
        result = OwnedSaveOverwriteTests.result
        folder = scene_module.PROJECT / 'evidence/save_overwrite/source_contract/lua'
        folder.mkdir(parents=True, exist_ok=True)
        receipt = folder / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ_') + uuid.uuid4().hex[:12] + '.json')
        proof = {'schema': 'zerosis.owned_save_overwrite_lua_checks.v1', 'unit_tests': program.result.testsRun,
                 'result': {key: value for key, value in result.items() if key != 'snapshots'},
                 'all_own_style_cleanup_receipts': scene_module.SCRATCH_RECEIPTS,
                 'check_source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                 'scene_fixture_source_sha256': hashlib.sha256(Path(scene_module.__file__).read_bytes()).hexdigest(),
                 'host_gamecore_or_native_window_executed': False}
        with receipt.open('x', encoding='utf8') as stream:
            json.dump(proof, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
        print(json.dumps({'status': result['status'], 'checks': result['checks'], 'case_count': len(result['cases']),
                          'unit_tests': program.result.testsRun, 'source_sha256': result['source_sha256'],
                          'temporary_styles_removed': result['temporary_styles_removed'],
                          'compositor_stages': {row['case']: row['compositorContractStages'] for row in result['cases']},
                          'coverage_mapping': result['coverage_mapping'],
                          'report': str(receipt), 'report_sha256': hashlib.sha256(receipt.read_bytes()).hexdigest(),
                          'real_archive_writes': 0, 'real_archive_deletes': 0}, ensure_ascii=False))
    raise SystemExit(0 if program.result.wasSuccessful() else 1)
