"""Replay season-name and TurnSlider wheel fidelity stage: start record and changed-file backups.

usage: python -B -X utf8 work.py start
No Host, GameCore, window, GPU, audio or game process is started.
"""
from __future__ import annotations
import datetime
import gzip
import hashlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
STAGE = Path(__file__).absolute().parent
PROJECT = STAGE.parents[2]
PREVIOUS = PROJECT / 'evidence/game_menu/options_reward_popups'
CHANGED = [
    'Source/Host/HostRun.h',
    'Source/Host/MenuReplayCalendar.h',
    'Source/Host/MenuReplayScrollModel.h',
    'Source/Host/MenuReplayPresentation.h',
    'Tests/menu_replay_calendar.py',
    'Tests/menu_replay_calendar.cpp',
    'Tests/menu_replay_restoration.py',
    'Tests/menu_replay_restored_scene.cpp',
    'Tests/menu_replay_scroll_model.py',
    'Tests/menu_replay_scroll_model.cpp',
    'Tests/menu_replay_input_batch.py',
    'docs/CLAUDE_HANDOFF.md',
]


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def write_new(path: Path, value) -> None:
    with path.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write('\n')


def backup(name: str) -> dict:
    path = PROJECT / name
    raw = path.read_bytes()
    digest = sha256(raw)
    target = STAGE / 'source_before' / (name.replace('/', '__') + '.' + digest[:16] + '.gz')
    target.parent.mkdir(exist_ok=True)
    with target.open('xb') as stream:
        stream.write(gzip.compress(raw, mtime=0))
    if sha256(gzip.decompress(target.read_bytes())) != digest:
        raise ValueError('Backup does not round-trip: ' + name)
    return dict(path=name, bytes=len(raw), sha256=digest, mtime_ns=path.stat().st_mtime_ns,
                backup=str(target.relative_to(PROJECT)).replace('\\', '/'), backup_bytes=target.stat().st_size)


def start() -> int:
    storage = json.loads((PREVIOUS / 'storage_after.json').read_text('utf8'))
    newest = max((p for p in PROJECT.rglob('*') if p.is_file() and '.git' not in p.parts
                  and STAGE not in p.parents), key=lambda p: p.stat().st_mtime_ns)
    write_new(STAGE / 'startup.json', dict(
        schema='zerosis.replay_season_wheel.startup.v1',
        utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        previous_stage=str(PREVIOUS.relative_to(PROJECT)).replace('\\', '/'),
        previous_storage=dict(status=storage['status'], utc=storage['utc'],
                              unique_allocated_bytes=storage['unique_allocated_bytes'],
                              confirmed_disposable_bytes=storage['confirmed_disposable_bytes'],
                              threshold_bytes=storage['threshold_bytes']),
        newest_project_file_outside_stage=dict(path=str(newest.relative_to(PROJECT)).replace('\\', '/'),
                                               mtime_utc=datetime.datetime.fromtimestamp(newest.stat().st_mtime, datetime.timezone.utc).isoformat()),
        cleanup_decision='No project file changed after the previous storage scan except its closing status records; '
                         'confirmed disposable bytes stay 0, below the 10 GiB threshold. Nothing deleted.',
        native_execution=False))
    write_new(STAGE / 'source_before.json', dict(changed_file_backups=[backup(name) for name in CHANGED],
                                                 full_project_copy=False))
    print(json.dumps(dict(status='STARTED', backups=len(CHANGED))))
    return 0


RECEIPTS = [
    'evidence/game_menu/replay_calendar_legend/calendar/result.json',
    'evidence/game_menu/replay_scroll_graph/scroll_model/result.json',
]


def receipts() -> int:
    """Keep the two component receipts that their drivers overwrite in place."""
    write_new(STAGE / 'receipts_before.json', dict(overwritten_component_receipts=[backup(name) for name in RECEIPTS]))
    print(json.dumps(dict(status='RECEIPTS_KEPT', receipts=len(RECEIPTS))))
    return 0


BUILD_TOOLS = [
    'tools/build_menu_suite_host.py',
    'tools/attest_prepared_menu_host.py',
    'evidence/save_menu/20261013_original_screen/current_progress.json',
]


def tools() -> int:
    """Back up the two wave-pinned build tools and the shared progress record before editing."""
    write_new(STAGE / 'tools_before.json', dict(changed_file_backups=[backup(name) for name in BUILD_TOOLS]))
    print(json.dumps(dict(status='TOOLS_KEPT', backups=len(BUILD_TOOLS))))
    return 0


def measure(label: str) -> int:
    sys.path.insert(0, str(PROJECT / 'tools'))
    from menu_suite_storage import storage
    value = storage.measure_storage()
    value.update(schema='zerosis.replay_season_wheel.storage.v1',
                 utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                 confirmed_disposable_bytes=0, threshold_bytes=10 * 1024 ** 3,
                 measurement='FileStandardInfo.AllocationSize once per real os.stat identity; directories excluded.',
                 native_execution=False)
    value.pop('source_replacement_released_after_this_receipt', None)
    write_new(STAGE / ('storage_' + label + '.json'), value)
    print(json.dumps({key: value[key] for key in ('status', 'file_paths', 'unique_allocated_bytes')}))
    return 0


if __name__ == '__main__':
    commands = dict(start=start, receipts=receipts, tools=tools)
    if len(sys.argv) == 3 and sys.argv[1] == 'measure' and sys.argv[2] in ('before', 'after'):
        raise SystemExit(measure(sys.argv[2]))
    if len(sys.argv) != 2 or sys.argv[1] not in commands:
        raise SystemExit(__doc__)
    raise SystemExit(commands[sys.argv[1]]())
