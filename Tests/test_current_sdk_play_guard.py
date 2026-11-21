"""Exercise guard decisions directly, without registering a process audit hook.

All filesystem fixtures belong to one disposable directory below these tests.
No production main, runtime, DLL, subprocess, retail path or user save is opened.
"""
import importlib.util
import os
from pathlib import Path
import stat
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


sys.dont_write_bytecode = True
TEST_ROOT = Path(__file__).absolute().parent
SPEC = importlib.util.spec_from_file_location(
    '_current_sdk_play_guard_under_test', TEST_ROOT.parent / 'tools/prepare_current_sdk_play.py')
guard_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guard_module)

RUN = '20261022T010203Z_123456abcdef'
OTHER_RUN = '20261022T010204Z_abcdef123456'


class PreparationGuardTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='_current_sdk_play_guard_', dir=TEST_ROOT)
        self.addCleanup(temporary.cleanup)
        self.project = Path(temporary.name)
        self.addCleanup(patch.stopall)
        patch.object(guard_module, 'PROJECT', self.project).start()
        patch.object(guard_module, 'STAGE', self.project / 'evidence/sdk_runtime_play').start()
        self.guard = guard_module.PreparationGuard()
        for parent in (*self.guard.parents, self.guard.cache_root):
            parent.mkdir(parents=True, exist_ok=True)

    def mkdir_event(self, path):
        self.guard.audit('os.mkdir', (str(path), 0o777, -1))

    def allocate(self, parent, run=RUN):
        path = parent / run
        self.mkdir_event(path)
        path.mkdir()
        return path

    def rejects(self, event, *arguments):
        with self.assertRaisesRegex(RuntimeError, 'Preparation guard:'):
            self.guard.audit(event, arguments)

    def test_existing_run_and_preexisting_counterpart_are_rejected(self):
        old = self.guard.parents[0] / OTHER_RUN
        old.mkdir()
        self.rejects('os.mkdir', str(old), 0o777, -1)
        self.assertIsNone(self.guard.run_id)
        counterpart = self.guard.parents[1] / RUN
        counterpart.mkdir()
        self.allocate(self.guard.parents[0])
        self.rejects('os.mkdir', str(counterpart), 0o777, -1)
        self.assertTrue(old.is_dir())
        self.assertTrue(counterpart.is_dir())

    def test_new_runtime_and_evidence_allow_repeated_directory_mkdir(self):
        for parent in self.guard.parents:
            allocated = self.allocate(parent)
            for _ in range(3):
                self.mkdir_event(allocated)
            nested = allocated / 'interactive_ui_support' / 'tools'
            self.mkdir_event(nested)
            nested.mkdir(parents=True)
            self.mkdir_event(nested)
        self.assertEqual(self.guard.run_id, RUN)
        self.assertEqual(self.guard.denied, [])

    def test_second_run_id_cannot_be_allocated(self):
        self.allocate(self.guard.parents[0])
        for parent in self.guard.parents:
            other = parent / OTHER_RUN
            self.rejects('os.mkdir', str(other), 0o777, -1)
            self.assertFalse(other.exists())
        self.assertEqual(self.guard.run_id, RUN)

    def test_allocated_root_replaced_by_a_file_is_rejected(self):
        allocated = self.allocate(self.guard.parents[0])
        allocated.rmdir()
        allocated.write_bytes(b'not a directory')
        self.rejects('os.mkdir', str(allocated), 0o777, -1)
        self.assertEqual(allocated.read_bytes(), b'not a directory')

    def test_writes_are_confined_to_new_run_and_new_stage(self):
        runtime = self.allocate(self.guard.parents[0])
        self.guard.audit('open', (str(runtime / 'rules.db'), 'wb', os.O_WRONLY | os.O_CREAT))
        self.mkdir_event(guard_module.STAGE)
        guard_module.STAGE.mkdir()
        self.guard.audit('open', (str(guard_module.STAGE / 'prepared.json'), 'x', os.O_WRONLY | os.O_CREAT | os.O_EXCL))
        for target in (self.project / 'Source/original.cpp', self.guard.parents[0] / OTHER_RUN / 'rules.db',
                       self.guard.cache_root / 'unapproved.bin'):
            self.rejects('open', str(target), 'wb', os.O_WRONLY | os.O_CREAT)
            self.assertFalse(target.exists())

    def test_cache_temporary_requires_exclusive_creation_and_exact_publication(self):
        self.guard.new_cache = self.guard.cache_root / '60' / ('60' + 'a' * 62)
        shard = self.guard.new_cache.parent
        self.mkdir_event(shard)
        shard.mkdir()
        temporary = shard / '.publish-abcdefgh'
        self.rejects('open', str(temporary), None, os.O_WRONLY | os.O_CREAT)
        self.guard.audit('open', (str(temporary), None, os.O_WRONLY | os.O_CREAT | os.O_EXCL))
        temporary.write_bytes(b'bounded test data')
        self.guard.audit('os.rename', (str(temporary), str(self.guard.new_cache), -1, -1))
        self.assertIn(guard_module.key(self.guard.new_cache), self.guard.created_cache)
        wrong = self.guard.cache_root / '61' / ('61' + 'a' * 62)
        self.rejects('os.rename', str(temporary), str(wrong), -1, -1)
        self.rejects('open', str(wrong.parent / '.publish-abcdefgh'), None,
                     os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        self.assertTrue(temporary.exists())  # Only guard decisions ran, never a real rename.
        self.assertFalse(self.guard.new_cache.exists())

    def test_cache_links_require_readonly_source_and_forbid_shared_writes(self):
        runtime = self.allocate(self.guard.parents[0])
        cache = self.guard.cache_root / '60' / ('60' + 'b' * 62)
        self.guard.cache_rows[guard_module.key(cache)] = {}
        target = runtime / 'CvGameCoreDLL_Expansion2_x64.dll'
        readonly = SimpleNamespace(st_dev=31, st_ino=47, st_mode=stat.S_IFREG | 0o444,
                                   st_file_attributes=guard_module.READONLY)
        with patch.object(Path, 'stat', return_value=readonly):
            self.guard.audit('os.link', (str(cache), str(target), -1, -1))
        self.assertIn((31, 47), self.guard.cache_ids)
        with patch.object(guard_module.os, 'lstat', return_value=readonly):
            self.rejects('open', str(target), 'wb', os.O_WRONLY | os.O_TRUNC)
            self.guard.audit('os.chmod', (str(target), 0o444, -1))
            self.rejects('os.chmod', str(target), 0o666, -1)
            self.rejects('os.utime', str(target), None, None, -1)
        mutable = SimpleNamespace(st_dev=31, st_ino=48, st_mode=stat.S_IFREG | 0o666,
                                  st_file_attributes=0)
        with patch.object(Path, 'stat', return_value=mutable):
            self.rejects('os.link', str(cache), str(target), -1, -1)
        self.rejects('os.link', str(cache.parent / 'unknown'), str(target), -1, -1)
        self.assertEqual(self.guard.idempotent_readonly_calls, 1)
        self.assertFalse(target.exists())  # No real hardlink or attribute mutation occurred.

    def test_native_process_dll_and_network_events_fail_before_any_os_call(self):
        events = ('subprocess.Popen', 'os.system', 'os.startfile', 'os.exec', 'os.spawn',
                  'ctypes.dlopen', 'ctypes.dlsym', 'socket.connect', 'winreg.OpenKey', 'sqlite3.connect')
        for event in events:
            with self.subTest(event=event):
                self.rejects(event, 'not executed')
        self.assertEqual(self.guard.native_attempts, len(events))

    def test_retail_and_user_paths_are_rejected_before_file_or_metadata_access(self):
        paths = [self.project / name / 'never-opened' for name in ('My Games', 'MODS', 'Saves', '.codex')]
        paths.append(self.project / 'steamapps/common/retail-game/never-opened')
        for path in paths:
            for event, tail in (('open', ('rb', 0)), ('os.listdir', ()), ('os.scandir', ())):
                with self.subTest(path=path, event=event):
                    self.rejects(event, str(path), *tail)
            for method, original in ((self.guard.guarded_stat, 'original_stat'),
                                     (self.guard.guarded_lstat, 'original_lstat'),
                                     (self.guard.guarded_access, 'original_access')):
                sentinel = Mock(side_effect=AssertionError('Forbidden OS metadata access'))
                with patch.object(self.guard, original, sentinel):
                    with self.assertRaisesRegex(RuntimeError, 'Preparation guard:'):
                        method(path, os.F_OK) if original == 'original_access' else method(path)
                sentinel.assert_not_called()


if __name__ == '__main__':
    unittest.main()
