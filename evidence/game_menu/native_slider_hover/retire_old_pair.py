"""Typed retirement of the older 8837/1fba Host/runtime pair, approved by the user on 2026-11-07 ("삭제").

usage: python -B -X utf8 retire_old_pair.py plan
       python -B -X utf8 retire_old_pair.py apply --plan-sha256 SHA
Only the exact recorded directory entries are removed. A hardlinked file keeps every other name, and its
readonly attribute is never cleared (FileDispositionInfoEx DELETE|POSIX|IGNORE_READONLY removes one entry).
No Host, GameCore, window, GPU, audio or game process is started.
"""
from __future__ import annotations
import argparse
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
STAGE = Path(__file__).absolute().parent
PROJECT = STAGE.parents[2]
sys.path.insert(0, str(PROJECT / 'tools'))
from menu_suite_storage import storage

ROOTS = {'host_8837': PROJECT / 'Build/UiWindowHost/20261105T133256Z_8837e4ca5f08',
         'runtime_1fba': PROJECT / 'Build/InteractiveGameRuntime/20261105T133817Z_1fba743abc09'}
IDS = ('8837e4ca5f08', '1fba743abc09')
PLAN_SHA = 'e60fcea85ba7b0e9dddcca66a53b06798bf31dd399b5783bb3ded5d34ea8d1fc'
CURRENT_BUILD, CURRENT_RUN = '20261107T120745Z_986e193d1ed1', '20261107T121011Z_527ea94501fb'


def require(value, message):
    if not value:
        raise RuntimeError(message)


def now():
    return datetime.now(timezone.utc).isoformat()


def read(path):
    return json.loads(Path(path).read_text('utf8'))


def digest(path):
    value = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            value.update(block)
    return value.hexdigest()


def write_new(path, value):
    with Path(path).open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write('\n')


def record(path):
    info = os.stat(path, follow_symlinks=False)
    require(not info.st_file_attributes & 0x400, 'Reparse point inside a retirement root: ' + str(path))
    return dict(path=str(path), bytes=info.st_size, file_identity=[info.st_dev, info.st_ino], mtime_ns=info.st_mtime_ns,
                file_attributes=info.st_file_attributes, links=info.st_nlink)


def references():
    """Live files that could still select the old pair; the builder only names it in RETIRED_ROOTS."""
    hits = []
    candidates = [PROJECT / 'tools/Start-Engine.ps1', *PROJECT.glob('Play/**/*.json'), *PROJECT.glob('Play/**/*.ps1'),
                  *PROJECT.glob('tools/*.py'), *PROJECT.glob('tools/*.ps1'), *PROJECT.glob('Tests/*.py'),
                  *PROJECT.glob('Tests/*.cpp'), *PROJECT.glob('Tests/*.h'), *PROJECT.glob('Source/Host/*.h')]
    for path in candidates:
        if not path.is_file():
            continue
        text = path.read_bytes().decode('utf8', errors='replace')
        for line_number, line in enumerate(text.splitlines(), 1):
            if any(identifier in line for identifier in IDS):
                allowed = path.name == 'build_menu_suite_host.py' and line.startswith('RETIRED_ROOTS = ')
                hits.append(dict(path=str(path.relative_to(PROJECT)), line=line_number, allowed=allowed))
    return hits


def plan():
    output = STAGE / 'retirement_plan.json'
    require(not output.exists(), 'Inspect the existing retirement plan')
    review = read(STAGE / 'host_build/plan_review.json')
    require(review['status'] == 'PASS_FILE_ONLY_PLAN_REVIEW' and review['plan']['sha256'] == PLAN_SHA and
            review['checks']['retired_runtime_unprotected'] and review['checks']['old_pair_not_referenced'],
            'The reviewed build plan must already exclude the old pair')
    build_plan = read(STAGE / 'host_build/plan.json')
    sealed = [row['path'] for group in ('protected_artifacts', 'current_source_inputs') for row in build_plan[group]]
    current = read(PROJECT / 'evidence/ui_window_host' / CURRENT_BUILD / 'build_result.json')
    sealed += [row['path'] for row in current['current_source_inputs']]
    request = (PROJECT / 'evidence/interactive_game' / CURRENT_RUN / 'request.json').read_text('utf8')
    profile = (PROJECT / 'evidence/game_menu/native_offline_followup/pair_preparation' / CURRENT_BUILD /
               'prepared_profile.json').read_text('utf8')
    require(not any(identifier in request or identifier in profile for identifier in IDS),
            'The current prepared pair still names the old pair')
    hits = references()
    require(all(hit['allowed'] for hit in hits), 'A live file still references the old pair: ' + repr(hits))
    roots, files, directories = {}, [], []
    for name, root in ROOTS.items():
        require(root.is_dir() and not os.stat(root, follow_symlinks=False).st_file_attributes & 0x400, 'Root is not a real directory')
        require(not any(Path(path).is_relative_to(root) for path in sealed), 'A sealed current row lies under ' + name)
        count = single = allocated = single_allocated = 0
        for directory, names, leaves in os.walk(root, topdown=True, followlinks=False):
            for item in names:
                record(Path(directory) / item)
            directories.append(str(Path(directory)))
            for leaf in leaves:
                path = Path(directory) / leaf
                relative = path.relative_to(root)
                require(path.suffix.casefold() not in ('.civ5save', '.sav') and
                        relative.parts[0].casefold() not in ('sessions', 'settings', 'saves'), 'Save or session data: ' + str(path))
                row = record(path)
                row.update(sha256=digest(path), allocated_bytes=storage.allocated(path), root=name)
                files.append(row)
                count += 1
                allocated += row['allocated_bytes']
                if row['links'] == 1:
                    single += 1
                    single_allocated += row['allocated_bytes']
        roots[name] = dict(path=str(root), files=count, single_link_files=single, allocated_bytes=allocated,
                           single_link_allocated_bytes=single_allocated)
    value = dict(schema='zerosis.native_slider_hover.retirement_plan.v1', utc=now(),
                 user_decision='2026-11-07 AskUserQuestion: "삭제" for the older 8837/1fba pair',
                 reviewed_build_plan=dict(path=str(STAGE / 'host_build/plan.json'), sha256=PLAN_SHA),
                 roots=roots, files=files, directories=sorted(directories, key=lambda p: (-p.count(os.sep), p)),
                 live_references=hits, expected_released_bytes=sum(r['single_link_allocated_bytes'] for r in roots.values()),
                 method='Per-entry FileDispositionInfoEx DELETE|POSIX_SEMANTICS|IGNORE_READONLY_ATTRIBUTE after identity, '
                        'mtime, attributes and SHA-256 re-check; then RemoveDirectory bottom-up. Other hardlinks keep bytes and flags.',
                 native_execution=False)
    write_new(output, value)
    raw = output.read_bytes()
    print(json.dumps(dict(status='RETIREMENT_PLAN_WRITTEN', files=len(files), directories=len(directories),
                          expected_released_bytes=value['expected_released_bytes'], sha256=hashlib.sha256(raw).hexdigest())))
    return 0


def remove_entry(path):
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                                   wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.SetFileInformationByHandle.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel.SetFileInformationByHandle.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.CreateFileW('\\\\?\\' + str(path), 0x10000, 7, None, 3, 0x00200000, None)
    require(handle not in (None, ctypes.c_void_p(-1).value), 'Cannot open the entry for disposition: ' + str(path))
    try:
        flags = wintypes.DWORD(0x13)  # FILE_DISPOSITION_FLAG_DELETE | POSIX_SEMANTICS | IGNORE_READONLY_ATTRIBUTE
        if not kernel.SetFileInformationByHandle(handle, 21, ctypes.byref(flags), 4):
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        kernel.CloseHandle(handle)


def apply(plan_sha):
    path = STAGE / 'retirement_plan.json'
    raw = path.read_bytes()
    require(re.fullmatch('[0-9a-f]{64}', plan_sha or '') and hashlib.sha256(raw).hexdigest() == plan_sha, 'Retirement plan differs')
    output = STAGE / 'retirement_result.json'
    require(not output.exists(), 'Inspect the existing retirement result')
    retirement = json.loads(raw)
    hits = references()
    require(all(hit['allowed'] for hit in hits), 'A live file references the old pair again')
    # Verify every entry before the first removal, so a changed tree aborts with nothing deleted.
    for row in retirement['files']:
        now_row = record(row['path'])
        require(all(now_row[k] == row[k] for k in ('bytes', 'file_identity', 'mtime_ns', 'file_attributes')),
                'Entry metadata changed since the plan: ' + row['path'])
        require(digest(row['path']) == row['sha256'], 'Entry bytes changed since the plan: ' + row['path'])
    listed = {row['path'].casefold() for row in retirement['files']}
    for root in ROOTS.values():
        for directory, names, leaves in os.walk(root, followlinks=False):
            for leaf in leaves:
                require(str(Path(directory) / leaf).casefold() in listed, 'Unplanned file appeared: ' + str(Path(directory) / leaf))
    removed, survivors = [], []
    for row in retirement['files']:
        remove_entry(row['path'])
        require(not os.path.lexists(row['path']), 'Entry still exists after disposition: ' + row['path'])
        removed.append(dict(path=row['path'], sha256=row['sha256'], links_before=row['links'],
                            allocated_bytes=row['allocated_bytes']))
        if row['links'] > 1:
            survivors.append(row['file_identity'])
    for directory in retirement['directories']:
        os.rmdir(directory)
    require(not any(os.path.lexists(root) for root in ROOTS.values()), 'A retirement root still exists')
    value = dict(schema='zerosis.native_slider_hover.retirement_result.v1', utc=now(),
                 status='PASS_OLDER_PAIR_RETIRED_EXACT_ENTRIES', plan=dict(path=str(path), sha256=plan_sha),
                 files_removed=len(removed), directories_removed=len(retirement['directories']),
                 single_link_entries_released=sum(1 for row in removed if row['links_before'] == 1),
                 released_allocated_bytes=sum(row['allocated_bytes'] for row in removed if row['links_before'] == 1),
                 shared_entries_unlinked_only=len(survivors), roots_absent=True, removed=removed,
                 readonly_attributes_changed=False, saves_or_sessions_removed=0, native_execution=False)
    write_new(output, value)
    print(json.dumps({k: value[k] for k in ('status', 'files_removed', 'directories_removed', 'released_allocated_bytes',
                                             'shared_entries_unlinked_only')}))
    return 0


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('operation', choices=('plan', 'apply'))
    cli.add_argument('--plan-sha256')
    args = cli.parse_args()
    require(os.name == 'nt' and sys.dont_write_bytecode, 'Use Windows Python -B')
    return plan() if args.operation == 'plan' else apply(args.plan_sha256)


if __name__ == '__main__':
    raise SystemExit(main())
