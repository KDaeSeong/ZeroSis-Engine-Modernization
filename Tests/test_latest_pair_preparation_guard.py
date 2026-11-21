"""Exercise the two-payload preparation audit boundary without materialization."""
from __future__ import annotations

import os
from pathlib import Path
import sys
import unittest
from unittest import mock


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import prepare_latest_engine_pair as pair


class LatestPairPreparationGuardTests(unittest.TestCase):
    def setUp(self):
        self.rows = [dict(path='unused-host.exe', sha256='1' * 64, bytes=3),
                     dict(path='unused-sdk.dll', sha256='2' * 64, bytes=5)]
        self.guard = pair.PairGuard(self.rows)
        self.caches = [self.guard.cache_root / row['sha256'][:2] / row['sha256']
                       for row in self.rows]

    def audit_absent(self, event, arguments):
        # No filesystem action or audit hook is installed by these tests.
        with mock.patch.object(os.path, 'lexists', return_value=False):
            self.guard.audit(event, arguments)

    def create_temporary(self, cache, suffix='abcdefgh'):
        temporary = cache.parent / ('.publish-' + suffix)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        self.audit_absent('open', (str(temporary), 'w', flags))
        return temporary

    def test_both_shards_can_publish_only_their_exact_payload_targets(self):
        for index, cache in enumerate(self.caches):
            with self.subTest(index=index):
                self.audit_absent('os.mkdir', (str(cache.parent), 0o777, -1))
                temporary = self.create_temporary(cache)
                self.audit_absent('os.rename', (str(temporary), str(cache), -1, -1))
                self.assertEqual(pair.base.key(self.guard.new_cache), pair.base.key(cache))
        self.assertEqual(self.guard.created_cache, {pair.base.key(path) for path in self.caches})
        self.assertEqual(self.guard.denied, [])
        self.assertEqual(self.guard.native_attempts, 0)

    def test_switching_back_to_first_shard_keeps_its_temporary_writes_allowed(self):
        for cache in (self.caches[0], self.caches[1], self.caches[0]):
            self.audit_absent('os.mkdir', (str(cache.parent), 0o777, -1))
            self.create_temporary(cache)
            self.assertEqual(pair.base.key(self.guard.new_cache), pair.base.key(cache))
        self.assertEqual(len(self.guard.temporary_cache), 2)
        self.assertEqual(self.guard.denied, [])

    def test_third_shard_and_its_temporary_are_rejected(self):
        third = self.guard.cache_root / '33'
        for event, arguments in (
                ('os.mkdir', (str(third), 0o777, -1)),
                ('open', (str(third / '.publish-abcdefgh'), 'w',
                          os.O_WRONLY | os.O_CREAT | os.O_EXCL))):
            with self.subTest(event=event), self.assertRaisesRegex(RuntimeError, 'Preparation guard:'):
                self.audit_absent(event, arguments)
        self.assertEqual(self.guard.created_cache, set())
        self.assertEqual(self.guard.temporary_cache, set())

    def test_third_digest_in_an_allowed_shard_cannot_be_written_or_published(self):
        cache = self.caches[0]
        temporary = self.create_temporary(cache)
        third = cache.parent / ('11' + '3' * 62)
        for event, arguments in (
                ('open', (str(third), 'w', os.O_WRONLY | os.O_CREAT | os.O_EXCL)),
                ('os.rename', (str(temporary), str(third), -1, -1))):
            with self.subTest(event=event), self.assertRaisesRegex(RuntimeError, 'Preparation guard:'):
                self.audit_absent(event, arguments)
        self.assertEqual(self.guard.created_cache, set())

    def test_atomic_publication_cannot_overwrite_an_existing_pair_payload(self):
        cache = self.caches[1]
        temporary = self.create_temporary(cache)
        with mock.patch.object(os.path, 'lexists', return_value=True), \
                self.assertRaisesRegex(RuntimeError, 'Preparation guard:'):
            self.guard.audit('os.rename', (str(temporary), str(cache), -1, -1))
        self.assertEqual(self.guard.created_cache, set())

    def test_duplicate_payload_identity_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, 'distinct new Host and SDK payloads'):
            pair.PairGuard([self.rows[0], dict(self.rows[0])])

    def test_process_dll_and_network_events_are_rejected_without_invoking_them(self):
        events = ('subprocess.Popen', 'os.system', 'os.startfile', 'os.spawn',
                  'ctypes.dlopen', 'ctypes.dlsym', 'socket.connect',
                  'urllib.Request', 'http.client.connect', 'sqlite3.connect')
        for event in events:
            with self.subTest(event=event):
                guard = pair.PairGuard(self.rows)
                with self.assertRaisesRegex(RuntimeError, 'Process execution, DLL loading'):
                    guard.audit(event, ('unused-sentinel',))
                self.assertEqual(guard.native_attempts, 1)
                self.assertEqual(guard.created_cache, set())

    def test_nonfilesystem_binary_audit_arguments_are_not_decoded_as_paths(self):
        guard = pair.PairGuard(self.rows)
        for event in ('marshal.loads', 'compile', 'code.__new__'):
            with self.subTest(event=event):
                guard.audit(event, (b'\xe3\xff\x00',))
        self.assertEqual(guard.denied, [])
        self.assertEqual(guard.native_attempts, 0)
        self.assertEqual(guard.created_cache, set())

    @unittest.skipUnless(os.name == 'nt', 'Windows private-state path rules')
    def test_original_game_and_user_state_reads_fail_before_metadata_access(self):
        paths = (
            r'C:\Users\sentinel\Documents\My Games\Civilization 5\UserSettings.ini',
            r'C:\Steam\steamapps\common\Civilization 5\Assets\unused.dat',
            r'C:\Users\sentinel\MODS\unused.dat',
            r'C:\Users\sentinel\Saves\unused.zssave',
            r'C:\Users\sentinel\.codex\unused.json',
            r'\\server\share\unused.dat',
        )
        for path in paths:
            with self.subTest(path=path):
                guard = pair.PairGuard(self.rows)
                with self.assertRaisesRegex(RuntimeError, 'Retail installation, user state'):
                    guard.audit('open', (path, 'r', 0))
                with mock.patch.object(guard, 'original_stat',
                                       side_effect=AssertionError('Unexpected metadata read')), \
                        self.assertRaisesRegex(RuntimeError, 'Retail installation, user state'):
                    guard.guarded_stat(path)
                self.assertEqual(guard.native_attempts, 0)


if __name__ == '__main__':
    unittest.main()
