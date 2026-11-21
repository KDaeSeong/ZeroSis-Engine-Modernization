"""Independent tiny archives exercise metadata checks without native execution.

The synthetic Game prefix/suffix are opaque sentinel bytes, not complete SDK
streams. These tests establish verifier acceptance/rejection boundaries only.
"""
from __future__ import annotations

from contextlib import closing, contextmanager, redirect_stdout
import ctypes
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


PROJECT = Path(__file__).absolute().parents[1]
sys.path.insert(0, str(PROJECT / "tools"))

import verify_restore_game_metadata as verifier


PREFIX = b"independent opaque fields and RNG sentinel\x19\x83"
SUFFIX = b"independent remaining Game fields\x06\x11\x1b"
INT32_MAX = 2**31 - 1
TEMPLATES = {
    "en_US": "Session {1_number} starts",
    "ko_KR": "세션 {1_number}{1: plural 1?이; 2?가;} 시작됐습니다.",
}


@contextmanager
def fixture_database(path: Path):
    with closing(sqlite3.connect(path)) as connection:
        with connection:
            yield connection


def replay_message(turn: int, kind: int, plots, player: int, text: str | bytes) -> bytes:
    encoded = text.encode("utf-8") if isinstance(text, str) else text
    return (
        struct.pack("<3i", turn, kind, len(plots))
        + b"".join(struct.pack("<2h", *plot) for plot in plots)
        + struct.pack("<2i", player, len(encoded))
        + encoded
    )


def existing_messages(count: int) -> list[bytes]:
    return [
        replay_message(index, 3, [(index % 17, -(index % 13))], index % 64,
                       f"Independent message {index}: 기존 기록")
        for index in range(count)
    ]


def game_section(messages: list[bytes], sessions: int, *, prefix: bytes = PREFIX,
                 suffix: bytes = SUFFIX, version: int = 2,
                 declared_count: int | None = None) -> bytes:
    count = len(messages) if declared_count is None else declared_count
    return prefix + struct.pack("<2i", version, count) + b"".join(messages) + struct.pack("<i", sessions) + suffix


def archive_payload(game: bytes, *, flags: int = 0, turn: int = 1,
                    elapsed: int = 1, active: int = 0,
                    replace_sections: dict[tuple[int, int], bytes] | None = None,
                    version: int = 1, teams: int = 64, players: int = 64,
                    section_count: int = 133) -> bytes:
    # The encoder intentionally does not use verifier constants or parsers.
    payload = bytearray(b"ZEROSIS_SAVE_V1\0")
    payload += struct.pack("<8I", version, flags, turn, elapsed, active, teams, players, section_count)
    identities = [(kind, 0) for kind in range(1, 6)]
    identities += [(6, slot) for slot in range(64)]
    identities += [(7, slot) for slot in range(64)]
    replacements = replace_sections or {}
    for identity in identities:
        content = game if identity == (3, 0) else f"opaque section {identity}".encode("ascii")
        content = replacements.get(identity, content)
        payload += struct.pack("<3I", *identity, len(content)) + content
    return bytes(payload)


def seal(payload: bytes) -> bytes:
    return payload + hashlib.sha256(payload).digest()


def expected_reload(language: str, sessions: int) -> str:
    decimal = f"{sessions:,}"
    if language == "en_US":
        return f"Session {decimal} starts"
    return f"세션 {decimal}{'이' if sessions == 1 else '가'} 시작됐습니다."


class RestoreGameMetadataTests(unittest.TestCase):
    def setUp(self) -> None:
        self.forbidden_calls = []
        for name in ("Popen", "run", "call", "check_call", "check_output", "getoutput", "getstatusoutput"):
            self.guard(subprocess, name)
        for name in ("system", "startfile", "spawnl", "spawnle", "spawnlp", "spawnlpe",
                     "spawnv", "spawnve", "spawnvp", "spawnvpe"):
            if hasattr(os, name):
                self.guard(os, name)
        for name in ("CDLL", "WinDLL", "OleDLL", "PyDLL"):
            self.guard(ctypes, name, create=True)
        for name in ("cdll", "windll", "oledll", "pydll"):
            loader = getattr(ctypes, name, None)
            if loader is not None:
                self.guard(loader, "LoadLibrary")

        self.fixture_base = (PROJECT / "evidence/save_menu/20261013_original_screen").resolve(strict=True)
        self.temporary = tempfile.TemporaryDirectory(prefix="tiny_restore_metadata_", dir=self.fixture_base)
        self.fixture = Path(self.temporary.name).resolve(strict=True)
        self.assertEqual(self.fixture.parent, self.fixture_base)
        self.addCleanup(self.cleanup_fixture)
        self.before_path = self.fixture / "checkpoint.zssave"
        self.after_path = self.fixture / "restored.zssave"
        self.rules_path = self.fixture / "rules.sqlite"
        self.locale_path = self.fixture / "locale.sqlite"
        with fixture_database(self.rules_path) as connection:
            connection.execute('CREATE TABLE GameOptions ("Type" TEXT, "Default" INTEGER)')
            connection.execute('INSERT INTO GameOptions VALUES (?, ?)', ("GAMEOPTION_NEW_RANDOM_SEED", 0))
        with fixture_database(self.locale_path) as connection:
            connection.execute('CREATE TABLE LocalizedText ("Language" TEXT, "Tag" TEXT, "Text" TEXT)')
            connection.execute('CREATE TABLE Languages ("Type" TEXT, "PluralRule" INTEGER)')
            connection.execute('CREATE TABLE LanguagePriorities ("LanguageSet" TEXT, "Language" TEXT, "Priority" INTEGER)')
            connection.executemany('INSERT INTO LocalizedText VALUES (?, ?, ?)', [
                (language, "TXT_KEY_MISC_RELOAD", template) for language, template in TEMPLATES.items()
            ])
            connection.executemany('INSERT INTO Languages VALUES (?, ?)', [
                (language, 2) for language in TEMPLATES
            ])
            connection.executemany('INSERT INTO LanguagePriorities VALUES (?, ?, ?)', [
                ("en_US", "en_US", 100), ("ko_KR", "ko_KR", 100), ("ko_KR", "en_US", 50),
            ])

    def guard(self, owner, name: str, **kwargs) -> None:
        guard = patch.object(owner, name, side_effect=AssertionError("Native execution is forbidden"), **kwargs)
        mocked = guard.start()
        self.addCleanup(guard.stop)
        self.forbidden_calls.append(mocked)

    def cleanup_fixture(self) -> None:
        resolved = self.fixture.resolve(strict=True)
        self.assertEqual(resolved.parent, self.fixture_base)
        self.assertTrue(resolved.name.startswith("tiny_restore_metadata_"))
        self.temporary.cleanup()
        self.assertFalse(resolved.exists())

    def tearDown(self) -> None:
        for mocked in self.forbidden_calls:
            mocked.assert_not_called()

    def pair(self, *, language: str = "en_US", turn: int = 1, elapsed: int = 1,
             active: int = 0, sessions: int = 1, count: int = 6) -> tuple[bytes, bytes]:
        messages = existing_messages(count)
        reload = replay_message(turn, 0, [(-1, -1)], active, expected_reload(language, sessions + 1))
        before = archive_payload(game_section(messages, sessions), turn=turn, elapsed=elapsed, active=active)
        after = archive_payload(game_section(messages + [reload], sessions + 1), turn=turn, elapsed=elapsed, active=active)
        return before, after

    def verify(self, before: bytes, after: bytes, *, language: str = "en_US",
               fixed_fixture: bool | None = False, configuration_verified=True):
        self.before_path.write_bytes(seal(before))
        self.after_path.write_bytes(seal(after))
        before_hashes = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in (
            self.before_path, self.after_path, self.rules_path, self.locale_path,
        )}
        keywords = {} if fixed_fixture is None else {"fixed_fixture": fixed_fixture}
        try:
            return verifier.verify_game_restore(
                self.before_path, self.after_path, rules_db_path=self.rules_path,
                localization_db_path=self.locale_path, language=language,
                configuration_verified=configuration_verified, **keywords,
            )
        finally:
            self.assertEqual(before_hashes, {
                path: hashlib.sha256(path.read_bytes()).hexdigest() for path in before_hashes
            })

    def assert_rejected(self, before: bytes, after: bytes, **kwargs) -> None:
        with self.assertRaises(RuntimeError):
            self.verify(before, after, **kwargs)

    def test_default_fixture_en_ko_contract_is_preserved(self) -> None:
        for language in TEMPLATES:
            with self.subTest(language=language):
                before, after = self.pair(language=language)
                result = self.verify(before, after, language=language, fixed_fixture=None)
                self.assertEqual(result["status"], "FIXTURE_GAME_RESTORE_METADATA_PASS")
                self.assertEqual(result["scope"], "FIXED_EN_KO_TURN1_NATIVE_SAVE_FIXTURE_ONLY")
                self.assertEqual(result["changed_sections"], [[3, 0]])
                self.assertEqual((result["replay_count_before"], result["replay_count_after"]), (6, 7))
                self.assertEqual((result["sessions_before"], result["sessions_after"]), (1, 2))
                self.assertEqual(result["appended_replay_message"]["text"], expected_reload(language, 2))
                self.assertTrue(result["new_random_seed_option_disabled"])
                self.assertFalse(result["retail_save_compatibility_verified"])
                self.assertFalse(result["general_game_section_preservation_verified"])

    def test_current_archive_turn_zero_other_player_session_ten_empty_replay(self) -> None:
        for language in TEMPLATES:
            with self.subTest(language=language):
                before, after = self.pair(language=language, turn=0, elapsed=0, active=7, sessions=9, count=0)
                result = self.verify(before, after, language=language)
                self.assertEqual(result["status"], "CURRENT_ARCHIVE_GAME_RESTORE_METADATA_PASS")
                self.assertEqual(result["scope"], "EN_KO_MANUAL_NATIVE_SAVE_V1_CURRENT_ARCHIVE_PAIR")
                self.assertEqual(result["archive_header"], {"flags": 0, "turn": 0, "elapsed": 0, "active_player": 7})
                self.assertEqual((result["replay_count_before"], result["replay_count_after"]), (0, 1))
                self.assertEqual((result["sessions_before"], result["sessions_after"]), (9, 10))
                self.assertEqual(result["appended_replay_message"]["turn"], 0)
                self.assertEqual(result["appended_replay_message"]["player"], 7)
                self.assertEqual(result["appended_replay_message"]["text"], expected_reload(language, 10))
                self.assertTrue(result["input_pair_game_byte_preservation_verified"])
                self.assertEqual(result["non_game_sections_byte_identical"], 132)
                self.assertTrue(result["single_player_provenance_required_from_caller"])
                self.assertFalse(result["arbitrary_saved_game_options_verified"])
                self.assertIsNone(result["new_random_seed_option_disabled"])
                self.assertTrue(result["new_random_seed_database_default_disabled"])
                self.assertIn("saved options are not independently decoded", result["new_random_seed_evidence"])
                self.assertFalse(result["retail_save_compatibility_verified"])
                self.assertFalse(result["general_game_section_preservation_verified"])

    def test_session_thousand_uses_actual_icu_decimal_grouping(self) -> None:
        for language, text in (("en_US", "Session 1,000 starts"), ("ko_KR", "세션 1,000가 시작됐습니다.")):
            with self.subTest(language=language):
                before, after = self.pair(language=language, turn=23, elapsed=26, active=12, sessions=999, count=0)
                result = self.verify(before, after, language=language)
                self.assertEqual((result["sessions_before"], result["sessions_after"]), (999, 1000))
                self.assertEqual(result["appended_replay_message"]["text"], text)

    def test_replay_count_byte_rollover_and_256_messages(self) -> None:
        for count in (255, 256):
            with self.subTest(count=count):
                before, after = self.pair(turn=41, elapsed=43, active=63, sessions=2, count=count)
                result = self.verify(before, after)
                self.assertEqual((result["replay_count_before"], result["replay_count_after"]), (count, count + 1))
                self.assertTrue(result["existing_replay_messages_byte_identical"])
                self.assertTrue(result["game_prefix_through_rng_and_replay_version_identical"])
                self.assertTrue(result["game_suffix_after_session_counter_identical"])

    def test_explicit_fixed_mode_does_not_silently_expand(self) -> None:
        for overrides in ({"turn": 0}, {"elapsed": 2}, {"active": 7}, {"sessions": 9}, {"count": 0}):
            with self.subTest(overrides=overrides):
                before, after = self.pair(**overrides)
                self.assert_rejected(before, after, fixed_fixture=True)

    def test_configuration_must_be_actual_true(self) -> None:
        before, after = self.pair()
        for value in (False, None, 1, "true"):
            with self.subTest(value=value):
                self.assert_rejected(before, after, configuration_verified=value)

    def test_random_seed_default_must_be_unique_false(self) -> None:
        before, after = self.pair()
        for values in ([], [1], [0, 0]):
            with self.subTest(values=values):
                with fixture_database(self.rules_path) as connection:
                    connection.execute('DELETE FROM GameOptions')
                    connection.executemany('INSERT INTO GameOptions VALUES (?, ?)', [
                        ("GAMEOPTION_NEW_RANDOM_SEED", value) for value in values
                    ])
                self.assert_rejected(before, after)

    def test_unknown_language_and_custom_template_are_rejected(self) -> None:
        before, after = self.pair()
        self.assert_rejected(before, after, language="fr_FR")
        for rows in ([], ["Changed Session {1_number}"]):
            with self.subTest(rows=rows):
                with fixture_database(self.locale_path) as connection:
                    connection.execute('DELETE FROM LocalizedText WHERE "Language"=?', ("en_US",))
                    connection.executemany('INSERT INTO LocalizedText VALUES (?, ?, ?)', [
                        ("en_US", "TXT_KEY_MISC_RELOAD", text) for text in rows
                    ])
                self.assert_rejected(before, after)

    def test_fixed_fixture_duplicate_text_contract_is_preserved(self) -> None:
        before, after = self.pair()
        with fixture_database(self.locale_path) as connection:
            connection.execute('INSERT INTO LocalizedText VALUES (?, ?, ?)',
                               ("en_US", "TXT_KEY_MISC_RELOAD", TEMPLATES["en_US"]))
        self.assert_rejected(before, after, fixed_fixture=True)

    def test_current_archive_plural_rule_and_selected_language_priority_are_checked(self) -> None:
        before, after = self.pair(language="ko_KR", turn=0, elapsed=0, active=7, sessions=9, count=0)
        with fixture_database(self.locale_path) as connection:
            connection.execute('UPDATE Languages SET "PluralRule"=1 WHERE "Type"=?', ("ko_KR",))
        self.assert_rejected(before, after, language="ko_KR")
        with fixture_database(self.locale_path) as connection:
            connection.execute('UPDATE Languages SET "PluralRule"=2 WHERE "Type"=?', ("ko_KR",))
            connection.execute('UPDATE LanguagePriorities SET "Priority"=101 WHERE "LanguageSet"=? AND "Language"=?',
                               ("ko_KR", "en_US"))
        self.assert_rejected(before, after, language="ko_KR")
        with fixture_database(self.locale_path) as connection:
            connection.execute('UPDATE LanguagePriorities SET "Priority"=50 WHERE "LanguageSet"=? AND "Language"=?',
                               ("ko_KR", "en_US"))
            connection.execute('DELETE FROM Languages WHERE "Type"=?', ("ko_KR",))
        self.assert_rejected(before, after, language="ko_KR")

    def test_header_changes_and_unsupported_header_values_are_rejected(self) -> None:
        before, after = self.pair(turn=0, elapsed=0, active=7, sessions=9, count=0)
        for index, value in ((1, 1), (2, 3), (3, 4), (4, 8)):
            with self.subTest(changed_index=index):
                changed = bytearray(after)
                struct.pack_into("<I", changed, 16 + 4 * index, value)
                self.assert_rejected(before, bytes(changed))
        for index, value in ((1, 1), (2, INT32_MAX + 1), (3, INT32_MAX + 1),
                             (4, 64), (0, 2), (5, 63), (6, 63), (7, 132)):
            with self.subTest(unsupported_index=index, value=value):
                changed_before, changed_after = bytearray(before), bytearray(after)
                struct.pack_into("<I", changed_before, 16 + 4 * index, value)
                struct.pack_into("<I", changed_after, 16 + 4 * index, value)
                self.assert_rejected(bytes(changed_before), bytes(changed_after))

    def test_non_game_sections_must_all_remain_byte_identical(self) -> None:
        messages = existing_messages(6)
        reload = replay_message(1, 0, [(-1, -1)], 0, "Session 2 starts")
        before = archive_payload(game_section(messages, 1))
        for identity in ((1, 0), (2, 0), (4, 0), (5, 0), (6, 0), (6, 63), (7, 0), (7, 63)):
            with self.subTest(identity=identity):
                after = archive_payload(game_section(messages + [reload], 2), replace_sections={identity: b"changed"})
                self.assert_rejected(before, after)

    def test_opaque_game_prefix_and_suffix_cannot_change(self) -> None:
        messages = existing_messages(6)
        reload = replay_message(1, 0, [(-1, -1)], 0, "Session 2 starts")
        before = archive_payload(game_section(messages, 1))
        for kwargs in ({"prefix": b"X" + PREFIX[1:]}, {"suffix": SUFFIX[:-1] + b"X"}):
            with self.subTest(kwargs=kwargs):
                after = archive_payload(game_section(messages + [reload], 2, **kwargs))
                self.assert_rejected(before, after)
        self.assert_rejected(before, archive_payload(game_section(messages + [reload], 2, suffix=SUFFIX + b"extra")))

    def test_existing_replay_record_and_invalid_utf8_cannot_change(self) -> None:
        messages = existing_messages(6)
        reload = replay_message(1, 0, [(-1, -1)], 0, "Session 2 starts")
        before = archive_payload(game_section(messages, 1))
        for replacement in (
            replay_message(99, 3, [(0, 0)], 0, "Changed existing record"),
            replay_message(0, 3, [(0, 0)], 0, b"\xff"),
        ):
            with self.subTest(replacement=replacement):
                changed_messages = [replacement] + messages[1:]
                after = archive_payload(game_section(changed_messages + [reload], 2))
                self.assert_rejected(before, after)

    def test_appended_event_must_have_exact_input_turn_player_type_plot_and_text(self) -> None:
        before, _ = self.pair(turn=0, elapsed=0, active=7, sessions=9, count=0)
        valid = {"turn": 0, "kind": 0, "plots": [(-1, -1)], "player": 7, "text": "Session 10 starts"}
        for overrides in ({"turn": 1}, {"kind": 1}, {"plots": []}, {"plots": [(0, 0)]},
                          {"plots": [(-1, -1), (-1, -1)]}, {"player": 0},
                          {"text": "Session 2 starts"}, {"text": b"\xff"}):
            with self.subTest(overrides=overrides):
                after = archive_payload(game_section([replay_message(**(valid | overrides))], 10), turn=0, elapsed=0, active=7)
                self.assert_rejected(before, after)

    def test_more_than_one_event_and_missing_reload_are_rejected(self) -> None:
        messages = existing_messages(6)
        reload = replay_message(1, 0, [(-1, -1)], 0, "Session 2 starts")
        before = archive_payload(game_section(messages, 1))
        for after_game in (
            game_section(messages + [reload, reload], 2),
            game_section(messages + [reload, reload], 2, declared_count=7),
            game_section(messages, 2),
        ):
            with self.subTest(after_game_bytes=len(after_game)):
                self.assert_rejected(before, archive_payload(after_game))

    def test_session_counter_requires_one_increment_with_no_overflow(self) -> None:
        for old, new in ((0, 1), (9, 9), (9, 11), (-1, 0), (INT32_MAX, -2**31)):
            with self.subTest(old=old, new=new):
                before = archive_payload(game_section([], old), turn=0, elapsed=0, active=7)
                reload = replay_message(0, 0, [(-1, -1)], 7, expected_reload("en_US", new))
                after = archive_payload(game_section([reload], new), turn=0, elapsed=0, active=7)
                self.assert_rejected(before, after)

    def test_replay_version_and_impossible_or_negative_count_are_rejected(self) -> None:
        reload = replay_message(1, 0, [(-1, -1)], 0, "Session 2 starts")
        for version, count in ((1, 0), (2, -1), (2, 100001), (2, 100000)):
            with self.subTest(version=version, count=count):
                before = archive_payload(game_section([], 1, version=version, declared_count=count))
                after = archive_payload(game_section([reload], 2, version=version, declared_count=count + 1))
                self.assert_rejected(before, after)

    def test_checksum_truncation_section_order_size_and_trailing_bytes_are_rejected(self) -> None:
        before, after = self.pair()
        self.before_path.write_bytes(seal(before))
        valid_after = seal(after)
        corrupt_digest = valid_after[:-1] + bytes([valid_after[-1] ^ 1])
        wrong_order = bytearray(after)
        struct.pack_into("<I", wrong_order, 48, 2)
        zero_size = bytearray(after)
        struct.pack_into("<I", zero_size, 56, 0)
        excess_size = bytearray(after)
        struct.pack_into("<I", excess_size, 56, len(after))
        cases = [
            corrupt_digest, valid_after[:79], seal(after[:54]), seal(after[:-8]),
            seal(bytes(wrong_order)), seal(bytes(zero_size)), seal(bytes(excess_size)), seal(after + b"trailing"),
        ]
        for index, encoded in enumerate(cases):
            with self.subTest(case=index):
                self.after_path.write_bytes(encoded)
                with self.assertRaises(RuntimeError):
                    verifier.verify_game_restore(
                        self.before_path, self.after_path, rules_db_path=self.rules_path,
                        localization_db_path=self.locale_path, language="en_US",
                        configuration_verified=True, fixed_fixture=False,
                    )

    def test_cli_current_archive_is_explicit_and_keeps_fixture_as_default(self) -> None:
        for current in (False, True):
            with self.subTest(current=current):
                before, after = self.pair()
                self.before_path.write_bytes(seal(before))
                self.after_path.write_bytes(seal(after))
                args = ["verify_restore_game_metadata.py", "--checkpoint", str(self.before_path),
                        "--restored", str(self.after_path), "--rules-db", str(self.rules_path),
                        "--localization-db", str(self.locale_path), "--language", "en_US", "--configuration-verified"]
                if current:
                    args.append("--current-archive")
                output = io.StringIO()
                with patch.object(sys, "argv", args), redirect_stdout(output):
                    verifier.main()
                result = json.loads(output.getvalue())
                expected = "CURRENT_ARCHIVE_GAME_RESTORE_METADATA_PASS" if current else "FIXTURE_GAME_RESTORE_METADATA_PASS"
                self.assertEqual(result["status"], expected)


if __name__ == "__main__":
    unittest.main()
