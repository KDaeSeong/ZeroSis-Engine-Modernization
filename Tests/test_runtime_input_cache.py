import errno
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import runtime_input_cache


class RuntimeInputCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='runtime-input-cache-test-')
        self.root = Path(self.temp.name)
        self.source = self.root / 'source.dll'
        self.source.write_bytes(b'isolated fake runtime payload\x00\x01')
        self.cache = self.root / 'cache'
        self.outputs = self.root / 'outputs'
        self.outputs.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def test_cache_is_an_independent_snapshot_and_targets_reuse_it(self):
        first = self.outputs / 'one.dll'
        result = runtime_input_cache.materialize_immutable(self.source, first, self.cache)
        cache_file = Path(result['cache'])
        self.assertEqual(result['materialization_method'], 'hardlink')
        self.assertIn(result['cache_method'], ('cache-created', 'cache-created-atomic-rename'))
        self.assertEqual(first.read_bytes(), self.source.read_bytes())
        self.assertFalse(os.path.samefile(self.source, cache_file))
        self.assertTrue(os.path.samefile(first, cache_file))
        self.assertFalse(os.stat(cache_file).st_mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))

        second = self.outputs / 'two.dll'
        again = runtime_input_cache.materialize_immutable(self.source, second, self.cache)
        self.assertEqual(again['cache_method'], 'cache-hit')
        self.assertTrue(os.path.samefile(second, cache_file))
        self.assertEqual(again['sha256'], result['sha256'])

    def test_existing_target_and_corrupt_hash_slot_fail_closed(self):
        target = self.outputs / 'already.dll'
        target.write_bytes(b'owned target')
        with self.assertRaisesRegex(RuntimeError, 'Target already exists'):
            runtime_input_cache.materialize_immutable(self.source, target, self.cache)

        good_target = self.outputs / 'good.dll'
        result = runtime_input_cache.materialize_immutable(self.source, good_target, self.cache)
        cache_file = Path(result['cache'])
        os.chmod(cache_file, stat.S_IREAD | stat.S_IWRITE)
        cache_file.write_bytes(b'corrupt')
        with self.assertRaisesRegex(RuntimeError, 'cache entry is corrupt'):
            runtime_input_cache.materialize_immutable(self.source, self.outputs / 'next.dll', self.cache)

    def test_cross_volume_link_failure_uses_verified_copy(self):
        original_link = runtime_input_cache.os.link
        target = self.outputs / 'copied.dll'

        def force_cross_volume(source, destination, *args, **kwargs):
            if Path(destination) == target:
                raise OSError(errno.EXDEV, 'different volume')
            return original_link(source, destination, *args, **kwargs)

        runtime_input_cache.os.link = force_cross_volume
        try:
            result = runtime_input_cache.materialize_immutable(self.source, target, self.cache)
        finally:
            runtime_input_cache.os.link = original_link
        self.assertEqual(result['materialization_method'], 'verified-copy-cross-volume')
        self.assertEqual(target.read_bytes(), self.source.read_bytes())
        self.assertFalse(os.path.samefile(target, result['cache']))

    def test_source_symlink_is_rejected(self):
        link = self.root / 'source-link.dll'
        try:
            link.symlink_to(self.source)
        except (OSError, NotImplementedError):
            self.skipTest('Symlink creation is unavailable in this test environment')
        with self.assertRaisesRegex(RuntimeError, 'symlink or reparse point'):
            runtime_input_cache.materialize_immutable(link, self.outputs / 'linked.dll', self.cache)

    def test_temp_descriptor_closes_when_source_validation_fails(self):
        fd, temp_name = tempfile.mkstemp(dir=self.root)
        missing = self.root / 'missing-source.dll'
        try:
            with self.assertRaisesRegex(RuntimeError, 'source does not exist'):
                runtime_input_cache._copy_to_temp(missing, fd)
            with self.assertRaises(OSError):
                os.fstat(fd)
        finally:
            Path(temp_name).unlink(missing_ok=True)

    def test_cleanup_failure_preserves_primary_validation_error(self):
        original_link = runtime_input_cache.os.link
        original_unlink = Path.unlink
        target = self.outputs / 'failed-copy.dll'

        def force_cross_volume(source, destination, *args, **kwargs):
            if Path(destination) == target:
                raise OSError(errno.EXDEV, 'different volume')
            return original_link(source, destination, *args, **kwargs)

        def injected_unlink(path, *args, **kwargs):
            if path == target:
                raise PermissionError('injected readonly-delete failure')
            return original_unlink(path, *args, **kwargs)

        original_hash = runtime_input_cache._hash_path
        def fail_target_validation(path, role):
            if role == 'materialized target' and path == target:
                raise ValueError('injected primary validation failure')
            return original_hash(path, role)

        try:
            with mock.patch.object(runtime_input_cache.os, 'link', force_cross_volume), \
                 mock.patch.object(Path, 'unlink', injected_unlink), \
                 mock.patch.object(runtime_input_cache, '_hash_path', fail_target_validation):
                with self.assertRaisesRegex(ValueError, 'injected primary validation failure') as caught:
                    runtime_input_cache.materialize_immutable(self.source, target, self.cache)
            self.assertTrue(any('Could not remove failed materialized target' in note for note in caught.exception.__notes__))
        finally:
            if target.exists():
                os.chmod(target, stat.S_IREAD | stat.S_IWRITE)
                original_unlink(target)


if __name__ == '__main__':
    unittest.main()
