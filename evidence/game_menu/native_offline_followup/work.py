"""Native offline follow-up wave: WindowTrim V4 pack, options slider wheel/keys, Localize booleans.

usage: python -B -X utf8 work.py start
       python -B -X utf8 work.py backup LABEL PATH [PATH ...]
       python -B -X utf8 work.py measure LABEL
No Host, GameCore, window, GPU, audio or game process is started.
"""
from __future__ import annotations
import datetime
import gzip
import hashlib
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
STAGE = Path(__file__).absolute().parent
PROJECT = STAGE.parents[2]
PREVIOUS = PROJECT / 'evidence/game_menu/replay_season_wheel'


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def write_new(path: Path, value) -> None:
    with path.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write('\n')


def backup_one(name: str) -> dict:
    path = PROJECT / name
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    target = STAGE / 'source_before' / (name.replace('/', '__') + '.' + digest[:16] + '.gz')
    target.parent.mkdir(exist_ok=True)
    if not target.exists():
        with target.open('xb') as stream:
            stream.write(gzip.compress(raw, mtime=0))
    if hashlib.sha256(gzip.decompress(target.read_bytes())).hexdigest() != digest:
        raise ValueError('Backup does not round-trip: ' + name)
    return dict(path=name, bytes=len(raw), sha256=digest, mtime_ns=path.stat().st_mtime_ns,
                backup=str(target.relative_to(PROJECT)).replace('\\', '/'))


def start() -> int:
    previous = json.loads((PREVIOUS / 'current_work.json').read_text('utf8'))
    storage = json.loads((PREVIOUS / 'storage_after.json').read_text('utf8'))
    write_new(STAGE / 'startup.json', dict(
        schema='zerosis.native_offline_followup.startup.v1', utc=now(),
        previous_stage=str(PREVIOUS.relative_to(PROJECT)).replace('\\', '/'),
        previous_status=previous['status'], previous_host=previous['current_host']['build_id'],
        previous_runtime=previous['current_prepared_runtime']['run_id'],
        previous_storage=dict(utc=storage['utc'], unique_allocated_bytes=storage['unique_allocated_bytes'],
                              confirmed_disposable_bytes=0, threshold_bytes=10 * 1024 ** 3),
        cleanup_decision='Only evidence/doc records changed after the previous storage scan; confirmed disposable bytes stay 0. '
                         'The older 8837/1fba pair is evaluated separately at the end of this wave.',
        user_request='2026-11-07: "전부 작업해" - apply every recorded offline follow-up item.',
        native_execution=False))
    print(json.dumps(dict(status='STARTED')))
    return 0


def backup(label: str, names: list[str]) -> int:
    if re.fullmatch('[a-z0-9_]{1,40}', label) is None:
        raise SystemExit('Use a canonical backup label')
    write_new(STAGE / ('backup_' + label + '.json'), dict(utc=now(), changed_file_backups=[backup_one(n) for n in names],
                                                          full_project_copy=False))
    print(json.dumps(dict(status='BACKED_UP', label=label, files=len(names))))
    return 0


def measure(label: str) -> int:
    sys.path.insert(0, str(PROJECT / 'tools'))
    from menu_suite_storage import storage
    value = storage.measure_storage()
    value.update(schema='zerosis.native_offline_followup.storage.v1', utc=now(), confirmed_disposable_bytes=0,
                 threshold_bytes=10 * 1024 ** 3, native_execution=False,
                 measurement='FileStandardInfo.AllocationSize once per real os.stat identity; directories excluded.')
    value.pop('source_replacement_released_after_this_receipt', None)
    write_new(STAGE / ('storage_' + label + '.json'), value)
    print(json.dumps({key: value[key] for key in ('status', 'file_paths', 'unique_allocated_bytes')}))
    return 0


if __name__ == '__main__':
    if sys.argv[1:] == ['start']:
        raise SystemExit(start())
    if len(sys.argv) >= 4 and sys.argv[1] == 'backup':
        raise SystemExit(backup(sys.argv[2], sys.argv[3:]))
    if len(sys.argv) == 3 and sys.argv[1] == 'measure' and re.fullmatch('[a-z0-9_]{1,40}', sys.argv[2]):
        raise SystemExit(measure(sys.argv[2]))
    raise SystemExit(__doc__)
