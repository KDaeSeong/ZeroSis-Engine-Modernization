"""Plan, then separately retire one exact never-executed prepared runtime.

Only the 35 pinned payload paths below may be unlinked. Historical evidence,
current sessions/saves, immutable cache donors and default entrypoints remain.
"""
from __future__ import annotations

import argparse
import codecs
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import types

sys.dont_write_bytecode = True
PROJECT = Path(__file__).absolute().parents[4]
STAGE = PROJECT / 'evidence/original_world_hud/pair_preparation/retirement'
OLD_ID = '20261024T050152Z_fd0465b26387'
NEW_ID = '20261024T070230Z_cbbd79f1cbb6'
SOURCE_ID = '20261022T001546Z_7fba195072e4'
B9_ID = '20261024T031412Z_e06aeb61ed6a'
OLD = PROJECT / 'Build/InteractiveGameRuntime' / OLD_ID
NEW = PROJECT / 'Build/InteractiveGameRuntime' / NEW_ID
PROGRESS = PROJECT / 'evidence/save_menu/20261013_original_screen/current_progress.json'
DOCUMENT = PROJECT / 'docs/ORIGINAL_WORLD_HUD.md'
PLAN = STAGE / 'plan.json'
PROTECTED = STAGE / 'protected_inputs.json.gz'
STARTED = STAGE / 'apply_started.json'
RESULT = STAGE / 'result.json'
LEDGER = STAGE / 'deleted_files.json.gz'
POWERSHELL = Path(r'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe')
HELPERS = {
    'prune': ('tools/prune_superseded_runtime_artifacts.py', 'e7dc5a356deba20add2482c4109f5e78775b48480c5ea81e483289e97f3b3678'),
    'base': ('tools/prepare_current_sdk_play.py', '1254720f955671dc895c45109a9417a088211f0f5823d9c26e1d8b2ebf90e8ae'),
    'allocation': ('evidence/native_restore_contract/pair_preparation/publish.py', '1f4771576092bfbfcd34d899b0ac0ce03fa0a43ac50b5b37825784c4e8da1406'),
}
TARGET_NAMES = (
    'audio-catalog.bin', 'bundle.manifest', 'CvGameCoreDLL_Expansion2_x64.dll', 'Firaxis.Framework.dll',
    'Firaxis.Framework.FirePlace.dll', 'Firaxis.Framework.Granny.dll', 'Firaxis.Framework.Granny.Implx64.dll',
    'icudt44l.dat', 'localization.db', 'Play.ps1', 'Resume.ps1', 'rules.db', 'script-catalog.bin',
    'terrain-assets.bin', 'unit-assets.bin', 'unitmodels_stringdatabase.gsd', 'Warrior.gr2',
    'Warrior_IdleA.gr2', 'Warrior_V2.gr2', 'Warrior_V4.gr2', 'ZeroSisDatabase_x64.dll',
    'ZeroSisGrannyAnimationBridge.dll', 'ZeroSisHost_x64.exe', 'ZeroSisHost_x64.exe.config',
    'ZeroSisLocalization_x64.dll', 'ZeroSisLua51_x64.dll', 'interactive_ui_support/support_manifest.json',
    'interactive_ui_support/assets/inline_icons.json', 'interactive_ui_support/assets/prepared.json',
    'interactive_ui_support/tools/civ5_ui_assets.py', 'interactive_ui_support/tools/found_value_runtime_options.py',
    'interactive_ui_support/tools/interactive_ui_driver.py', 'interactive_ui_support/tools/render_ui_popup.py',
    'interactive_ui_support/tools/ui_bitmap_fonts.py', 'interactive_ui_support/tools/ui_pixel_scene.py',
)
SOURCE_NAMES = ('Source/Presentation/WorldViewRenderer.cpp', 'Source/Presentation/BitmapWindow.h',
                'Source/Presentation/BitmapWindow.cpp', 'Source/Presentation/WorldCameraControls.h',
                'Source/Host/InteractiveGameLoop.h')
REQUEST_PINS = {
    OLD_ID: '84c8b56d70dda98f9f6c1b8d3f894f0b6ea298564cab2d1130e8ef51ef22d3a4',
    NEW_ID: 'd2b4df310924a40e3c9e7f64cb007d1cd237d9f6287310eab52e94ca3f70bf2e',
    SOURCE_ID: 'c47775cec96ae5fc762ebadf394d894fcd524e7314ed8428d52b5220028477e7',
}
PINS = {
    'evidence/original_world_hud/host_build/inputs.json': 'db8dbd4d0c3e854dda26cf6786f4d34de3fb0b0750a8f8fe2d9b8d764c3ad594',
    'evidence/ui_window_host/20261024T055841Z_974a5be57533/build_result.json': '6aa2ccdb8ce1308521fc01f88fa45745153244b6931754a0b3111dc2129d1302',
    'evidence/original_world_hud/pair_preparation/execution/terminal_audit.json': '153f3f12899d477beb8c3c41356519cc76a8ac46fd6ada48bff093c85ffc09f7',
    'evidence/original_world_hud/pair_preparation/materialization/result.json': 'c8eeb0626f305ed8d60e714cfc0abfb5bc814628a686610e70171e66590cee41',
}


def require(value, message):
    if not value:
        raise RuntimeError(message)


def key(path):
    return os.path.normcase(os.path.abspath(os.fsdecode(path)))


def utc():
    return datetime.now(timezone.utc).isoformat()


def ordinary(path, inside=True):
    path = Path(path)
    require(path.is_absolute() and '..' not in path.parts and (not inside or path.is_relative_to(PROJECT)),
            'Noncanonical or out-of-project path')
    for item in (path, *path.parents):
        info = item.lstat()
        require(not stat.S_ISLNK(info.st_mode) and not getattr(info, 'st_file_attributes', 0) & 0x400,
                'Reparse path or ancestor')
    info = path.stat()
    require(stat.S_ISREG(info.st_mode), 'Expected an ordinary file')
    return info


def digest(path):
    ordinary(Path(path), inside=key(path) != key(POWERSHELL))
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read_json(path, maximum=8 * 1024 * 1024):
    require(ordinary(path).st_size <= maximum, 'JSON exceeds its read bound')
    def unique(pairs):
        result = {}
        for name, value in pairs:
            require(name not in result, 'Duplicate JSON key')
            result[name] = value
        return result
    return json.loads(Path(path).read_bytes().decode('utf-8-sig'), object_pairs_hook=unique,
                      parse_constant=lambda value: require(False, 'Nonfinite JSON value'))


def load_source(relative, expected, name):
    path = PROJECT / relative
    before = ordinary(path)
    raw = path.read_bytes()
    require(len(raw) <= 128 * 1024 and hashlib.sha256(raw).hexdigest() == expected and
            (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) ==
            (path.stat().st_dev, path.stat().st_ino, path.stat().st_size, path.stat().st_mtime_ns),
            'Authenticated helper changed')
    module = types.ModuleType(name)
    module.__file__ = str(path)
    sys.modules[name] = module
    exec(compile(raw, str(path), 'exec'), module.__dict__)
    return module


def helpers():
    base = load_source(*HELPERS['base'], 'prepare_current_sdk_play')
    prune = load_source(*HELPERS['prune'], '_exact_retirement_primitives')
    allocation = load_source(*HELPERS['allocation'], '_exact_retirement_allocation')
    require(base.PROJECT == prune.ROOT == allocation.PROJECT == PROJECT and allocation.base is base,
            'Authenticated helper roots differ')
    return base, prune, allocation


class Snapshots:
    def __init__(self, prune, allocation):
        self.prune, self.allocation, self.cache = prune, allocation, {}

    def take(self, path, expected=None, outside=False):
        path = Path(path)
        if outside:
            info = ordinary(path, inside=False)
        else:
            path = self.prune.boundary(path)
            info = self.prune.regular(path)
        state = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns,
                 getattr(info, 'st_file_attributes', 0), info.st_nlink)
        if state not in self.cache:
            self.cache[state] = (self.prune.digest(path), self.allocation.allocation(path) if not outside else None)
        sha, allocated = self.cache[state]
        require(state == (path.stat().st_dev, path.stat().st_ino, path.stat().st_size, path.stat().st_mtime_ns,
                          getattr(path.stat(), 'st_file_attributes', 0), path.stat().st_nlink), 'File changed while hashing')
        row = dict(path=str(path), bytes=info.st_size, sha256=sha, file_identity=[info.st_dev, info.st_ino],
                   mtime_ns=info.st_mtime_ns, attributes=getattr(info, 'st_file_attributes', 0),
                   nlinks=info.st_nlink, allocation_bytes=allocated)
        if expected is not None:
            require(type(expected.get('sha256')) is str and sha == expected['sha256'] and
                    ('bytes' not in expected or type(expected['bytes']) is int and row['bytes'] == expected['bytes']),
                    'Pinned input content differs')
        return row


def inventory(root, exclude=None):
    root = Path(root)
    require(root.is_relative_to(PROJECT) and root.is_dir(), 'Inventory root is missing or outside the project')
    files, directories = [], []
    stack = [root]
    while stack:
        directory = stack.pop()
        for ancestor in (directory, *directory.parents):
            require(not getattr(ancestor.lstat(), 'st_file_attributes', 0) & 0x400, 'Reparse inventory ancestor')
        directories.append(directory)
        for item in sorted(directory.iterdir(), key=lambda value: key(value)):
            if exclude is not None and (item == exclude or item.is_relative_to(exclude)):
                continue
            info = item.lstat()
            require(not stat.S_ISLNK(info.st_mode) and not getattr(info, 'st_file_attributes', 0) & 0x400,
                    'Reparse inventory entry')
            if stat.S_ISDIR(info.st_mode):
                stack.append(item)
            else:
                require(stat.S_ISREG(info.st_mode), 'Nonordinary inventory entry')
                files.append(item)
    return sorted(files, key=key), sorted(directories, key=lambda value: (-len(value.parts), key(value)))


def progress_guard():
    value = read_json(PROGRESS)
    old = value['native_restore_pair_preparation_stage']
    require(value['current_prepared_runtime']['run_id'] == NEW_ID and
            value['original_world_hud_pair_preparation_stage']['run_id'] == NEW_ID and
            old['status'] == 'SUPERSEDED_PREPARED_PAIR_BUILD_PAYLOAD_RETIREMENT_PLANNED' and
            old['current'] is False and old['payload_retirement_planned'] is True and
            old['superseded_by_run_id'] == NEW_ID,
            'Mutable progress has not explicitly superseded the old prepared payload')


def write_json(path, value):
    raw = (json.dumps(value, ensure_ascii=True, sort_keys=True, indent=2) + '\n').encode('ascii')
    require(len(raw) <= 256 * 1024, 'Receipt exceeds its small-file bound')
    with Path(path).open('xb') as stream:
        stream.write(raw)


def write_gzip(path, value):
    raw = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':')).encode('ascii')
    require(len(raw) <= 4 * 1024 * 1024, 'Compressed ledger exceeds its expanded bound')
    with Path(path).open('xb') as stream:
        with gzip.GzipFile(filename='', mode='wb', fileobj=stream, mtime=0) as compressed:
            compressed.write(raw)


def artifact_refs(value):
    if type(value) is dict:
        if type(value.get('path')) is str and type(value.get('sha256')) is str:
            yield value
        for child in value.values():
            yield from artifact_refs(child)
    elif type(value) is list:
        for child in value:
            yield from artifact_refs(child)


def collect(snap):
    files, directories = inventory(OLD)
    expected = {key(OLD / name) for name in TARGET_NAMES}
    require(len(TARGET_NAMES) == len(files) == 35 and {key(path) for path in files} == expected and
            len(directories) == 4 and not (OLD / 'sessions').exists() and
            not (PROJECT / 'evidence/interactive_game' / OLD_ID / 'driver_result.json').exists() and
            not (OLD / 'driver_result.json').exists(), 'Old runtime is not the exact never-executed 35-file payload')
    requests = {}
    for run, sha in REQUEST_PINS.items():
        path = PROJECT / 'evidence/interactive_game' / run / 'request.json'
        snap.take(path, dict(sha256=sha))
        requests[run] = read_json(path)
    old = requests[OLD_ID]
    require(old['run_id'] == OLD_ID and key(old['cwd']) == key(OLD) and old['smoke'] is False and
            old['resume_from'] is None and len(old['runtime_inputs']) == 24, 'Old request provenance differs')
    targets = [snap.take(path) for path in files]
    by_path = {key(row['path']): row for row in targets}
    for row in artifact_refs(old):
        if Path(row['path']).is_relative_to(OLD):
            require(key(row['path']) in by_path, 'The old request references an unexpected payload path')
            snap.take(row['path'], row)
    donors = []
    for row in old['materializations']:
        if row['materialization_method'] != 'hardlink':
            continue
        require(key(row['target']) in by_path and Path(row['cache']).is_relative_to(PROJECT / 'Build/RuntimeInputCache'),
                'A shared donor escaped the old payload/cache roles')
        donor = snap.take(row['cache'], dict(sha256=row['sha256'], bytes=row['size']))
        target = by_path[key(row['target'])]
        require(donor['file_identity'] == target['file_identity'] and donor['nlinks'] == target['nlinks'] > 1 and
                donor['attributes'] & 1, 'A shared cache donor is not the exact immutable alias')
        donors.append(donor)
    require(len({tuple(row['file_identity']) for row in targets}) == 35 and len(donors) == 15 and
            len({tuple(row['file_identity']) for row in donors}) == 15 and
            sum(row['nlinks'] == 1 for row in targets) == 20 and
            {tuple(row['file_identity']) for row in targets if row['nlinks'] > 1} ==
            {tuple(row['file_identity']) for row in donors}, 'Private/shared target inventory differs')
    private_allocation = sum(row['allocation_bytes'] for row in targets if row['nlinks'] == 1)
    require(private_allocation == 65249584, 'Last-link AllocationSize differs from the reviewed 65,249,584 bytes')
    return requests, targets, directories, donors


def protect(snap, requests, donors):
    paths, scopes = {}, []
    roots = (NEW, PROJECT / 'evidence/interactive_game' / OLD_ID,
             PROJECT / 'evidence/original_world_hud', PROJECT / 'Play')
    for root in roots:
        files, _ = inventory(root, exclude=STAGE)
        scopes.append(dict(root=str(root), paths=[str(path) for path in files]))
        paths.update((key(path), path) for path in files)
    additional = [PROGRESS, DOCUMENT, PROJECT / 'tools/Start-Engine.ps1',
        PROJECT / 'evidence/goody_hut/runtime_fonts/system_freeze_hold.json',
        PROJECT / 'evidence/serialization/unit_great_work_save/sdk_2bdcdf80a1695780f864/result.json',
        *(PROJECT / name for name in SOURCE_NAMES), *(PROJECT / relative for relative, _ in HELPERS.values()),
        *(PROJECT / name for name in ('tools/retained_host_runtime_input.py', 'tools/retained_world_hud_host_input.py',
                                     'tools/prepare_latest_engine_pair.py', 'Tests/test_original_world_hud_runtime_input.py')),
        *(PROJECT / relative for relative in PINS)]
    for run in REQUEST_PINS:
        additional.append(PROJECT / 'evidence/interactive_game' / run / 'request.json')
    require(len(requests[SOURCE_ID]['runtime_inputs']) == len(requests[NEW_ID]['runtime_inputs']) == 24,
            'Source/current immutable-input inventories differ')
    for run in (SOURCE_ID, NEW_ID):
        for row in requests[run]['runtime_inputs']:
            snap.take(row['path'], row)
            additional.append(Path(row['path']))
    save_scopes = []
    for run in (SOURCE_ID, B9_ID, NEW_ID):
        root = PROJECT / 'Build/InteractiveGameRuntime' / run
        files, _ = inventory(root)
        saves = [path for path in files if path.suffix.lower() == '.zssave']
        require(len(saves) == 2, 'A retained native-save scope differs from its exact two files')
        save_scopes.append(dict(run_id=run, paths=[str(path) for path in saves]))
        additional.extend(saves)
    additional.extend(Path(row['path']) for row in donors)
    for path in additional:
        require(not path.is_relative_to(OLD), 'A protected input overlaps the retirement target root')
        paths[key(path)] = path
    for relative, sha in PINS.items():
        snap.take(PROJECT / relative, dict(sha256=sha))
    require(digest(PROGRESS) == '787776b810bd21b0c227b9fdb81c9560920f949d20bc261625ca426a874007a3' and
            digest(DOCUMENT) == '6b4e39786f6916ca2179a07e4f6780d8f25e59417502662ebb498be23c3a4bb0',
            'The reviewed post-publication progress/documentation changed')
    return [snap.take(path) for _, path in sorted(paths.items())], scopes, save_scopes


def verify_rows(snap, rows, decrements=None):
    decrements = decrements or {}
    for before in rows:
        actual = snap.take(before['path'], before)
        expected = dict(before, nlinks=before['nlinks'] - decrements.get(tuple(before['file_identity']), 0))
        require(actual == expected, 'Retained file identity/metadata/bytes or exact link-count change differs: ' + before['path'])


def verify_scopes(scopes, save_scopes):
    for scope in scopes:
        files, _ = inventory(Path(scope['root']), exclude=STAGE)
        require([str(path) for path in files] == scope['paths'], 'A protected file inventory changed')
    for scope in save_scopes:
        files, _ = inventory(PROJECT / 'Build/InteractiveGameRuntime' / scope['run_id'])
        require([str(path) for path in files if path.suffix.lower() == '.zssave'] == scope['paths'],
                'A retained native-save inventory changed')


def process_guard(shell_before):
    require(ordinary(POWERSHELL, inside=False).st_size == shell_before['bytes'] and
            digest(POWERSHELL) == shell_before['sha256'], 'Read-only process-query executable changed')
    query = ("$ErrorActionPreference='Stop'; $p=@(Get-CimInstance Win32_Process -Filter "
             "\"Name='ZeroSisHost_x64.exe' OR Name='cl.exe' OR Name='link.exe' OR Name='Civ5.exe' OR Name='CivilizationV.exe' "
             "OR Name='CivilizationV_DX11.exe' OR Name='CivilizationV_Tablet.exe'\"); "
             "if($p.Count -ne 0){exit 3}; Write-Output '[]'")
    command = [str(POWERSHELL), '-NoLogo', '-NoProfile', '-NonInteractive', '-Command', query]
    result = subprocess.run(command, capture_output=True, text=True, timeout=30,
                            creationflags=subprocess.CREATE_NO_WINDOW)
    require(result.returncode == 0 and result.stdout.strip() == '[]', 'Host/game/compiler process scope is not provably idle')
    return dict(utc=utc(), query='Win32_Process exact Host/compiler/game names', count=0, returncode=0)


def plan(base, prune, allocation):
    require(not any(path.exists() for path in (PLAN, PROTECTED, STARTED, RESULT, LEDGER)), 'Retirement already has a plan/attempt')
    progress_guard()
    snap = Snapshots(prune, allocation)
    requests, targets, directories, donors = collect(snap)
    protected, scopes, saves = protect(snap, requests, donors)
    require(not ({tuple(row['file_identity']) for row in targets if row['nlinks'] == 1} &
                 {tuple(row['file_identity']) for row in protected}), 'A last-link target is still a protected input')
    verify_scopes(scopes, saves)
    verify_rows(Snapshots(prune, allocation), targets + protected + donors)
    shell = snap.take(POWERSHELL, outside=True)
    script = snap.take(Path(__file__).absolute())
    write_gzip(PROTECTED, dict(files=protected, scopes=scopes, save_scopes=saves))
    protected_ref = snap.take(PROTECTED)
    directory_rows = [dict(path=str(path), file_identity=[path.stat().st_dev, path.stat().st_ino]) for path in directories]
    value = dict(schema='zerosis.original_world_hud.unexecuted_pair_retirement_plan.v1', utc=utc(),
        status='PLANNED_EXACT_35_UNEXECUTED_PAYLOAD_FILES_NOT_APPLIED', old_run_id=OLD_ID, current_run_id=NEW_ID,
        script=script, helpers={name: dict(path=str(PROJECT / relative), sha256=sha) for name, (relative, sha) in HELPERS.items()},
        targets=targets, empty_directories_after_files=directory_rows, donors=donors, protected_inputs=protected_ref,
        protected_file_count=len(protected), native_save_count=6, last_link_files=20, shared_aliases=15,
        last_link_allocation_bytes=65249584, target_logical_bytes=sum(row['bytes'] for row in targets),
        allocation_metric='FileStandardInfo.AllocationSize; shared aliases contribute zero reclaimable data',
        query_executable=shell, process_query_performed_during_plan=False, deletion_applied=False,
        cache_payloads_deleted=False, readonly_attributes_changed=False, host_sdk_game_or_ui_executed=False,
        original_game_or_user_saves_accessed=False, full_engine_goal_complete=False)
    write_json(PLAN, value)
    print(json.dumps(dict(status=value['status'], plan=str(PLAN), sha256=digest(PLAN), script_sha256=script['sha256'],
        files=35, directories=4, protected_files=len(protected), private_allocation_bytes=65249584)))


def apply(base, prune, allocation, plan_sha, script_sha):
    require(re.fullmatch('[0-9a-f]{64}', plan_sha or '') and re.fullmatch('[0-9a-f]{64}', script_sha or ''),
            'Apply requires exact plan and script SHA-256 pins')
    require(digest(PLAN) == plan_sha and digest(Path(__file__)) == script_sha and
            not any(path.exists() for path in (STARTED, RESULT, LEDGER)), 'Plan/script changed or an apply attempt already exists')
    value = read_json(PLAN)
    require(value['script']['sha256'] == script_sha and value['old_run_id'] == OLD_ID and value['current_run_id'] == NEW_ID,
            'Plan belongs to another script or runtime')
    progress_guard()
    snap = Snapshots(prune, allocation)
    for name, (relative, sha) in HELPERS.items():
        require(value['helpers'][name] == dict(path=str(PROJECT / relative), sha256=sha), 'Plan helper identity changed')
    snap.take(PROTECTED, value['protected_inputs'])
    with gzip.open(PROTECTED, 'rb') as stream:
        expanded = stream.read(4 * 1024 * 1024 + 1)
    require(len(expanded) <= 4 * 1024 * 1024, 'Protected ledger exceeds its expansion bound')
    preserved = json.loads(expanded)
    _, targets, directories, donors = collect(snap)
    actual_directories = [dict(path=str(path), file_identity=[path.stat().st_dev, path.stat().st_ino]) for path in directories]
    require(targets == value['targets'] and donors == value['donors'] and
            actual_directories == value['empty_directories_after_files'],
            'The complete 35-file pre-unlink inventory changed')
    verify_rows(Snapshots(prune, allocation), preserved['files'] + value['donors'])
    verify_scopes(preserved['scopes'], preserved['save_scopes'])
    idle = process_guard(value['query_executable'])
    write_json(STARTED, dict(utc=utc(), plan_sha256=plan_sha, script_sha256=script_sha, process_scope=idle,
                            target_files=35, automatic_retry_allowed=False))
    deleted, removed_dirs, error = [], [], None
    try:
        for before in value['targets']:
            verify_rows(Snapshots(prune, allocation), [before])
            path = prune.boundary(Path(before['path']))
            require(key(path) in {key(OLD / name) for name in TARGET_NAMES}, 'Unlink escaped the exact target set')
            prune.unlink_without_attribute_changes(path)
            require(not os.path.lexists(path), 'An unlinked target is still present')
            deleted.append(before)
        for row in value['empty_directories_after_files']:
            path = prune.boundary(Path(row['path']))
            require(path.is_dir() and [path.stat().st_dev, path.stat().st_ino] == row['file_identity'] and
                    not list(path.iterdir()), 'A planned directory is changed or nonempty')
            path.rmdir(); removed_dirs.append(str(path))
        decrements = {tuple(row['file_identity']): 1 for row in value['donors']}
        verify_rows(Snapshots(prune, allocation), preserved['files'] + value['donors'], decrements)
        verify_scopes(preserved['scopes'], preserved['save_scopes'])
        require(len(deleted) == 35 and len(removed_dirs) == 4 and not OLD.exists(), 'Retirement did not finish exactly')
    except BaseException as exc:
        error = type(exc).__name__ + ': ' + str(exc)
    write_gzip(LEDGER, deleted)
    report = dict(schema='zerosis.original_world_hud.unexecuted_pair_retirement.v1', utc=utc(),
        status='PASS_EXACT_35_UNEXECUTED_PAIR_PAYLOAD_RETIRED' if error is None else 'FAILED_EXACT_RETIREMENT_REQUIRES_MANUAL_AUDIT',
        error=error, plan_sha256=plan_sha, script_sha256=script_sha, deleted_files=len(deleted),
        removed_empty_directories=len(removed_dirs), deleted_ledger=dict(path=str(LEDGER), sha256=digest(LEDGER)),
        last_link_allocation_bytes=65249584 if error is None else None, protected_file_count=len(preserved['files']),
        exact_shared_link_decrements_verified=error is None, cache_payloads_deleted=False,
        readonly_attributes_changed=False, host_sdk_game_or_ui_executed=False, full_engine_goal_complete=False)
    write_json(RESULT, report)
    require(error is None, 'Retirement requires manual audit; see the immutable result')
    print(json.dumps(dict(status=report['status'], result=str(RESULT), sha256=digest(RESULT), deleted_files=len(deleted))))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('plan', 'apply'))
    parser.add_argument('--plan-sha256')
    parser.add_argument('--script-sha256')
    args = parser.parse_args()
    require(not sys.flags.optimize and Path(__file__).absolute().parent == STAGE, 'Unexpected script location or optimized Python')
    require(args.mode == 'apply' or not (args.plan_sha256 or args.script_sha256), 'Plan does not accept apply authority pins')
    for encoding in ('utf-8', 'utf-8-sig', 'ascii', 'mbcs', 'cp1252'):
        codecs.lookup(encoding); b'x'.decode(encoding); 'x'.encode(encoding)
    base, prune, allocation = helpers()
    if args.mode == 'plan':
        plan(base, prune, allocation)
    else:
        apply(base, prune, allocation, args.plan_sha256, args.script_sha256)


if __name__ == '__main__':
    main()
