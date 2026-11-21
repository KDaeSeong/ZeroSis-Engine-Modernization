"""Verify only the fixture-defined CvGame.Read reload metadata changes.

This is deliberately scoped to the isolated turn-1, single-player EN/KO fixture.
It does not establish retail-save compatibility or prove arbitrary CvGame streams.
The byte contract follows CvGame::Read/Write and CvReplayMessage::read/write:
Read increments m_iNumSessions and appends one TXT_KEY_MISC_RELOAD replay entry.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import struct
from pathlib import Path
from typing import Any


MAGIC = b"ZEROSIS_SAVE_V1\0"
SECTION_COUNT = 133
REPLAY_MESSAGE_VERSION = 2
FIXTURE_TURN = 1
FIXTURE_OLD_SESSIONS = 1
FIXTURE_NEW_SESSIONS = 2
FIXTURE_OLD_REPLAY_MESSAGES = 6
LANGUAGE_RELOAD_TEXT = {
    "en_US": ("Session {1_number} starts", "Session 2 starts"),
    "ko_KR": ("세션 {1_number}{1: plural 1?이; 2?가;} 시작됐습니다.", "세션 2가 시작됐습니다."),
}


def _fail(message: str) -> None:
    raise RuntimeError(message)


def _archive(path: str | Path) -> tuple[dict[str, int], dict[tuple[int, int], bytes]]:
    path = Path(path)
    data = path.read_bytes()
    if len(data) < 80 or data[:16] != MAGIC:
        _fail(f"Invalid native save envelope: {path}")
    payload_end = len(data) - 32
    if hashlib.sha256(data[:payload_end]).digest() != data[payload_end:]:
        _fail(f"Native save checksum differs: {path}")
    version, flags, turn, elapsed, active, teams, players, count = struct.unpack_from("<8I", data, 16)
    if (version, teams, players, count) != (1, 64, 64, SECTION_COUNT):
        _fail(f"Native save fixture header differs: {path}")
    sections: dict[tuple[int, int], bytes] = {}
    offset = 48
    expected = [(kind, 0) for kind in range(1, 6)] + [(6, slot) for slot in range(64)] + [(7, slot) for slot in range(64)]
    for identity in expected:
        if offset + 12 > payload_end:
            _fail(f"Truncated section header in {path}")
        kind, slot, size = struct.unpack_from("<3I", data, offset)
        offset += 12
        if (kind, slot) != identity or not size or size > payload_end - offset:
            _fail(f"Native save section order or size differs in {path}")
        sections[identity] = data[offset:offset + size]
        offset += size
    if offset != payload_end:
        _fail(f"Unexpected trailing bytes in {path}")
    return ({"flags": flags, "turn": turn, "elapsed": elapsed, "active_player": active}, sections)


def _i32(data: bytes, offset: int) -> int:
    if offset < 0 or offset + 4 > len(data):
        _fail("CvGame replay/session field is truncated")
    return struct.unpack_from("<i", data, offset)[0]


def _replay_message(data: bytes, offset: int) -> tuple[int, dict[str, Any]]:
    """Read the exact fields emitted by CvReplayMessage::write."""
    start = offset
    turn = _i32(data, offset)
    kind = _i32(data, offset + 4)
    plot_count = _i32(data, offset + 8)
    offset += 12
    if plot_count < 0 or plot_count > 4096:
        _fail("CvReplayMessage plot count is outside the fixture parser bound")
    plots: list[tuple[int, int]] = []
    for _ in range(plot_count):
        if offset + 4 > len(data):
            _fail("CvReplayMessage plot list is truncated")
        plots.append(struct.unpack_from("<hh", data, offset))
        offset += 4
    player = _i32(data, offset)
    text_size = _i32(data, offset + 4)
    offset += 8
    if text_size < 0 or text_size > len(data) - offset:
        _fail("CvReplayMessage text length is invalid")
    text_bytes = data[offset:offset + text_size]
    try:
        text = text_bytes.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise RuntimeError("CvReplayMessage text is not valid UTF-8") from exc
    offset += text_size
    return offset, {
        "start": start,
        "turn": turn,
        "type": kind,
        "plots": plots,
        "player": player,
        "text": text,
        "text_bytes": text_bytes,
    }


def _reload_text(language: str, localization_db_path: str | Path) -> tuple[str, str]:
    if language not in LANGUAGE_RELOAD_TEXT:
        _fail("This verifier supports only the EN/KO fixed fixture")
    with sqlite3.connect(Path(localization_db_path).resolve().as_uri()+'?mode=ro',uri=True) as connection:
        rows = connection.execute(
            'SELECT "Text" FROM LocalizedText WHERE "Language"=? AND "Tag"=?',
            (language, "TXT_KEY_MISC_RELOAD"),
        ).fetchall()
    template, formatted = LANGUAGE_RELOAD_TEXT[language]
    if rows != [(template,)]:
        _fail(f"{language} TXT_KEY_MISC_RELOAD fixture text differs")
    return template, formatted


def _random_seed_option_is_disabled(rules_db_path: str | Path) -> bool:
    with sqlite3.connect(Path(rules_db_path).resolve().as_uri()+'?mode=ro',uri=True) as connection:
        rows = connection.execute(
            'SELECT "Default" FROM GameOptions WHERE "Type"=?',
            ("GAMEOPTION_NEW_RANDOM_SEED",),
        ).fetchall()
    if rows != [(0,)]:
        _fail("Fixture database does not default GAMEOPTION_NEW_RANDOM_SEED to false")
    return True


def verify_game_restore(
    checkpoint_path: str | Path,
    restored_path: str | Path,
    *,
    rules_db_path: str | Path,
    localization_db_path: str | Path,
    language: str,
    configuration_verified: bool,
) -> dict[str, Any]:
    """Verify the fixture's one expected Game-section transformation.

    The caller supplies the checkpoint and restored ``.zssave`` plus the exact
    rules/localization databases and the host's successful configuration flag.
    The game-option database default is false and the fixture host reports that
    it applied and verified all database-backed options before the checkpoint.
    """
    if configuration_verified is not True:
        _fail("The runtime did not verify the fixture game-option configuration")
    random_seed_disabled = _random_seed_option_is_disabled(rules_db_path)
    reload_template, expected_text = _reload_text(language, localization_db_path)
    before_header, before_sections = _archive(checkpoint_path)
    after_header, after_sections = _archive(restored_path)
    expected_header = {"flags": 0, "turn": FIXTURE_TURN, "elapsed": 1, "active_player": 0}
    if before_header != expected_header or after_header != expected_header:
        _fail("Checkpoint/restored archive metadata is outside the fixed turn-1 fixture")
    changed_sections = [identity for identity in before_sections if before_sections[identity] != after_sections[identity]]
    if changed_sections != [(3, 0)]:
        _fail(f"Expected only Game section (3,0) to change; observed {changed_sections}")

    before = before_sections[(3, 0)]
    after = after_sections[(3, 0)]
    common = min(len(before), len(after))
    changed_at = next((index for index in range(common) if before[index] != after[index]), None)
    if changed_at is None or changed_at < 4:
        _fail("No serialized replay-message count change was found")
    # In CvGame::Write, replay-message version and count follow both RNG streams.
    # First-difference anchoring means every earlier Game field, including RNG,
    # must remain byte-identical; it does not infer a universal section offset.
    count_offset = changed_at
    if _i32(before, count_offset - 4) != REPLAY_MESSAGE_VERSION or \
            before[:count_offset] != after[:count_offset]:
        _fail("First Game-section difference is not the versioned replay-message count")
    old_count = _i32(before, count_offset)
    new_count = _i32(after, count_offset)
    if old_count != FIXTURE_OLD_REPLAY_MESSAGES or new_count != old_count + 1:
        _fail("Replay-message count differs from the six-to-seven-message fixture")

    old_cursor = count_offset + 4
    new_cursor = count_offset + 4
    for _ in range(old_count):
        old_next, _ = _replay_message(before, old_cursor)
        new_next, _ = _replay_message(after, new_cursor)
        if before[old_cursor:old_next] != after[new_cursor:new_next]:
            _fail("An existing CvReplayMessage changed during restore")
        old_cursor, new_cursor = old_next, new_next

    new_cursor, appended = _replay_message(after, new_cursor)
    if (appended["turn"], appended["type"], appended["plots"], appended["player"], appended["text"]) != \
            (FIXTURE_TURN, 0, [(-1, -1)], 0, expected_text):
        _fail("The appended replay message is not the fixture's exact reload event")
    before_sessions = _i32(before, old_cursor)
    after_sessions = _i32(after, new_cursor)
    if (before_sessions, after_sessions) != (FIXTURE_OLD_SESSIONS, FIXTURE_NEW_SESSIONS):
        _fail("CvGame::Read session counter did not change from 1 to 2")
    if before[old_cursor + 4:] != after[new_cursor + 4:]:
        _fail("Unexpected Game-section bytes changed after the session counter")

    return {
        "status": "FIXTURE_GAME_RESTORE_METADATA_PASS",
        "language": language,
        "changed_sections": [list(identity) for identity in changed_sections],
        "game_bytes_before": len(before),
        "game_bytes_after": len(after),
        "replay_version": REPLAY_MESSAGE_VERSION,
        "replay_count_before": old_count,
        "replay_count_after": new_count,
        "existing_replay_messages_byte_identical": True,
        "appended_replay_message": {
            "turn": appended["turn"], "type": appended["type"],
            "plots": [list(plot) for plot in appended["plots"]],
            "player": appended["player"], "text": appended["text"],
            "localization_key": "TXT_KEY_MISC_RELOAD",
            "localization_template": reload_template,
        },
        "sessions_before": before_sessions,
        "sessions_after": after_sessions,
        "game_prefix_through_rng_and_replay_version_identical": True,
        "game_suffix_after_session_counter_identical": True,
        "new_random_seed_option_disabled": random_seed_disabled,
        "scope": "FIXED_EN_KO_TURN1_NATIVE_SAVE_FIXTURE_ONLY",
        "retail_save_compatibility_verified": False,
        "general_game_section_preservation_verified": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--restored", required=True)
    parser.add_argument("--rules-db", required=True)
    parser.add_argument("--localization-db", required=True)
    parser.add_argument("--language", choices=tuple(LANGUAGE_RELOAD_TEXT), required=True)
    parser.add_argument("--configuration-verified", action="store_true")
    args = parser.parse_args()
    result = verify_game_restore(
        args.checkpoint, args.restored,
        rules_db_path=args.rules_db,
        localization_db_path=args.localization_db,
        language=args.language,
        configuration_verified=args.configuration_verified,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
