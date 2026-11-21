"""Regression tests for ordered, parallel Civ V UI pack hashing."""
import hashlib
from pathlib import Path
import struct
import sys
import tempfile
from threading import Barrier, BrokenBarrierError, Lock
import unittest
from unittest import mock

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "tools"))
import civ5_ui_assets as assets_module


def make_fpk(name: str, payload: bytes) -> bytes:
    encoded = name.encode("utf-8")
    padded_len = (len(encoded) + 3) // 4 * 4
    padding = padded_len - len(encoded)
    padding_bytes = bytes([padding]) + bytes(padding - 1) if padding else b""
    offset = 14 + 4 + padded_len + 16
    return (struct.pack("<I", 6) + b"FPK_\0\0" + struct.pack("<I", 1) +
            struct.pack("<I", len(encoded)) + encoded + padding_bytes +
            struct.pack("<QII", 0, len(payload), offset) + payload)


class UiPackIntegrityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="ui-pack-integrity-", dir=PROJECT)
        self.addCleanup(self.temporary.cleanup)
        self.game_root = Path(self.temporary.name) / "game"
        self.pack_root = self.game_root / "Resource" / "DX9"
        self.pack_root.mkdir(parents=True)
        self.pack_bytes: dict[Path, bytes] = {}
        for index, name in enumerate(assets_module.PACK_POLICY):
            path = self.pack_root / name
            data = make_fpk(f"fixture-{index}.bin", f"payload-{index}".encode("ascii"))
            path.write_bytes(data)
            self.pack_bytes[path.resolve()] = data

    def test_initial_records_preserve_policy_order_and_exact_metadata(self) -> None:
        ui_assets = assets_module.UiAssets(self.game_root)

        self.assertEqual([Path(row["path"]).name for row in ui_assets.pack_records],
                         list(assets_module.PACK_POLICY))
        for record in ui_assets.pack_records:
            path = Path(record["path"]).resolve()
            expected = self.pack_bytes[path]
            self.assertEqual(record["bytes"], len(expected))
            self.assertEqual(record["sha256"], hashlib.sha256(expected).hexdigest())
            self.assertEqual(record["entries"], 1)

    def test_same_length_source_mutation_fails_unchanged_check(self) -> None:
        ui_assets = assets_module.UiAssets(self.game_root)
        path = Path(ui_assets.pack_records[0]["path"])
        before = path.read_bytes()
        changed = before[:-1] + bytes([before[-1] ^ 0x01])
        self.assertEqual(len(changed), len(before))
        path.write_bytes(changed)

        self.assertFalse(ui_assets.unchanged())

    def test_size_change_fails_unchanged_check(self) -> None:
        ui_assets = assets_module.UiAssets(self.game_root)
        path = Path(ui_assets.pack_records[0]["path"])
        path.write_bytes(path.read_bytes() + b"x")

        self.assertFalse(ui_assets.unchanged())

    def test_hash_read_error_propagates_and_all_parallel_tasks_finish(self) -> None:
        ui_assets = assets_module.UiAssets(self.game_root)
        expected_paths = set(self.pack_bytes)
        barrier = Barrier(len(assets_module.PACK_POLICY))
        lock = Lock()
        started: set[Path] = set()
        finished: set[Path] = set()
        actual_sha256 = assets_module.sha256
        failed_path = next(iter(expected_paths))

        def controlled_hash(value) -> str:
            path = Path(value).resolve()
            with lock:
                started.add(path)
            try:
                barrier.wait(timeout=10)
                if path == failed_path:
                    raise OSError("injected pack read failure")
                return actual_sha256(path)
            except BrokenBarrierError as error:
                raise AssertionError("all four pack hashes must overlap") from error
            finally:
                with lock:
                    finished.add(path)

        with mock.patch.object(assets_module, "sha256", side_effect=controlled_hash):
            with self.assertRaisesRegex(OSError, "injected pack read failure"):
                ui_assets.unchanged()

        self.assertEqual(started, expected_paths)
        self.assertEqual(finished, expected_paths)

    def test_success_returns_only_after_all_four_overlapping_hashes_finish(self) -> None:
        expected_paths = set(self.pack_bytes)
        barrier = Barrier(len(assets_module.PACK_POLICY))
        lock = Lock()
        started: set[Path] = set()
        finished: set[Path] = set()
        actual_sha256 = assets_module.sha256

        def synchronized_hash(value) -> str:
            path = Path(value).resolve()
            with lock:
                started.add(path)
            try:
                barrier.wait(timeout=10)
                return actual_sha256(path)
            except BrokenBarrierError as error:
                raise AssertionError("all four pack hashes must overlap") from error
            finally:
                with lock:
                    finished.add(path)

        with mock.patch.object(assets_module, "sha256", side_effect=synchronized_hash):
            ui_assets = assets_module.UiAssets(self.game_root)

        self.assertEqual(started, expected_paths)
        self.assertEqual(finished, expected_paths)
        self.assertEqual(len(ui_assets.pack_records), len(assets_module.PACK_POLICY))

    def test_unchanged_returns_true_after_all_four_overlapping_hashes_finish(self) -> None:
        ui_assets = assets_module.UiAssets(self.game_root)
        expected_paths = set(self.pack_bytes)
        barrier = Barrier(len(assets_module.PACK_POLICY))
        lock = Lock()
        started: set[Path] = set()
        finished: set[Path] = set()
        actual_sha256 = assets_module.sha256

        def synchronized_hash(value) -> str:
            path = Path(value).resolve()
            with lock:
                started.add(path)
            try:
                barrier.wait(timeout=10)
                return actual_sha256(path)
            except BrokenBarrierError as error:
                raise AssertionError("all four final pack hashes must overlap") from error
            finally:
                with lock:
                    finished.add(path)

        with mock.patch.object(assets_module, "sha256", side_effect=synchronized_hash):
            self.assertTrue(ui_assets.unchanged())

        self.assertEqual(started, expected_paths)
        self.assertEqual(finished, expected_paths)

    def test_new_instance_recognizes_mutation_without_process_cache(self) -> None:
        first = assets_module.UiAssets(self.game_root)
        path = Path(first.pack_records[0]["path"])
        original_hash = first.pack_records[0]["sha256"]
        before = path.read_bytes()
        path.write_bytes(before[:-1] + bytes([before[-1] ^ 0x01]))

        self.assertFalse(first.unchanged())
        second = assets_module.UiAssets(self.game_root)
        new_record = next(row for row in second.pack_records if Path(row["path"]).resolve() == path.resolve())
        self.assertEqual(new_record["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertNotEqual(new_record["sha256"], original_hash)


if __name__ == "__main__":
    unittest.main()
