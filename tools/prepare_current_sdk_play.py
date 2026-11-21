"""Prepare one current-SDK private runtime without executing native code.

The production runner owns materialization. This wrapper restricts its I/O,
checks the sealed R11/B11 inputs before and after, and records the actual result.
It never promotes a release or migrates an older bundle's saves.
"""
from __future__ import annotations

import argparse
import ast
from contextlib import ExitStack, redirect_stderr, redirect_stdout
import hashlib
import importlib
import io
import json
import os
from pathlib import Path
import re
import stat
import sys
from unittest.mock import patch


PROJECT = Path(__file__).absolute().parents[1]
STAGE = PROJECT / 'evidence/sdk_runtime_play'
SOURCE_RUN = '20261020T110323Z_27da680b90f1'
HOST_BUILD = '20261018T024443Z_23a2e7fdb8ea'
SOURCE_REQUEST = PROJECT / f'evidence/interactive_game/{SOURCE_RUN}/request.json'
SOURCE_REQUEST_SHA = '7b04270096d0815c1ad682b3f99db2496b713db9cc7c5f5af05956d1744020f1'
IDENTITY = PROJECT / 'evidence/goody_hut/runtime_fonts/preparation_identity_audit.json'
IDENTITY_SHA = 'e7b3de4e0c7ac30e8933ac52a8d5d2df0f32d0457dbf08fb40089164cb28719e'
POST = PROJECT / 'evidence/sdk_runtime_current/post_publication_checks.json'
POST_SHA = '890cc4278df239dde1ea73760ad74e866aa4bfeebfb7e0e536a05012245b3635'
SDK_BUILD = PROJECT / 'evidence/sdk_runtime_current/build_result.json'
SDK_DLL = PROJECT / 'Build/SDKIncremental/x64/runtime_candidate/CvGameCoreDLL_Expansion2_x64_runtime_candidate.dll'
SDK_SHA = '60984b68246d16bef42a4d0f5a159ae51104edb356a26c85ff917493279cbfe5'
TOOLS = ('interactive_ui_driver.py', 'render_ui_popup.py', 'ui_pixel_scene.py',
         'ui_bitmap_fonts.py', 'civ5_ui_assets.py', 'found_value_runtime_options.py')
REPARSE = getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400)
READONLY = getattr(stat, 'FILE_ATTRIBUTE_READONLY', 1)
RUN_PATTERN = re.compile(r'\d{8}T\d{6}Z_[0-9a-f]{12}\Z')
HASH_PATTERN = re.compile(r'[0-9a-f]{64}\Z')


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def key(path):
    value = os.path.normcase(os.path.abspath(os.fsdecode(path)))
    if value.startswith('\\\\?\\'):
        value = value[4:]
    return os.path.normpath(value)


def within(path, root):
    value, base = key(path), key(root)
    return value == base or value.startswith(base + os.sep)


def ordinary(path):
    path = Path(path)
    require(path.is_absolute() and within(path, PROJECT), 'Input escaped the engine project')
    for item in (*reversed(path.parents), path):
        try:
            info = item.lstat()
        except FileNotFoundError:
            continue
        require(not stat.S_ISLNK(info.st_mode) and not getattr(info, 'st_file_attributes', 0) & REPARSE,
                'A project input contains a symlink or reparse point: ' + str(item))
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode), 'Expected an ordinary input file: ' + str(path))
    return info


def artifact(path):
    path = Path(path)
    before = ordinary(path)
    hasher = hashlib.sha256()
    with path.open('rb') as stream:
        opened = os.fstat(stream.fileno())
        require((before.st_dev, before.st_ino, before.st_size) ==
                (opened.st_dev, opened.st_ino, opened.st_size), 'Input changed while opening')
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            hasher.update(block)
    after = path.lstat()
    require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) ==
            (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns), 'Input changed while hashing')
    return {'path': str(path), 'bytes': before.st_size, 'sha256': hasher.hexdigest()}


def checked(row):
    current = artifact(row['path'])
    require(current['sha256'] == row['sha256'] and current['bytes'] == row.get('bytes', current['bytes']),
            'Pinned input changed: ' + str(row['path']))
    return current


def read(path):
    ordinary(path)
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write_new(path, document):
    with Path(path).open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(document, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


class Capture(io.TextIOBase):
    """Bound diagnostic logs without allowing a runner to flood the receipt."""
    def __init__(self):
        self.parts = []
        self.characters = 0
        self.retained = 0

    def write(self, value):
        require(isinstance(value, str), 'Runner wrote a non-text diagnostic')
        self.characters += len(value)
        keep = value[:max(0, 32768 - self.retained)]
        self.parts.append(keep)
        self.retained += len(keep)
        return len(value)

    def flush(self):
        return None

    def getvalue(self):
        return ''.join(self.parts)


class PreparationGuard:
    """Audit only this process and this preparation's narrowly owned outputs.

    Existing content-addressed files may only be linked into the fresh runtime.
    The cache helper's readonly chmod on that new alias is allowed only when it
    is already readonly and the requested mode is identical; no attribute change
    on an existing cache object is authorized.
    """
    def __init__(self):
        self.denied = []
        self.run_id = None
        self.allocated_roots = set()
        self.parents = (PROJECT / 'Build/InteractiveGameRuntime', PROJECT / 'evidence/interactive_game')
        self.cache_root = PROJECT / 'Build/RuntimeInputCache'
        self.cache_rows = {}
        self.cache_ids = set()
        self.new_cache = None
        self.created_cache = set()
        self.temporary_cache = set()
        self.stage_created = False
        self.native_attempts = 0
        self.idempotent_readonly_calls = 0
        self.original_stat = os.stat
        self.original_lstat = os.lstat
        self.original_access = os.access

    def fail(self, event, reason):
        self.denied.append({'event': event, 'reason': reason})
        raise RuntimeError('Preparation guard: ' + reason)

    def blocked_read(self, path):
        target = key(path)
        parts = [part.casefold() for part in Path(target).parts]
        return (any(part in ('my games', 'mods', 'saves', '.codex') for part in parts)
                or ('steamapps' in parts and 'common' in parts)
                or target.startswith('\\\\'))

    def check_read(self, event, path):
        if self.blocked_read(path):
            self.fail(event, 'Retail installation, user state, internal records or network paths are forbidden')

    def guarded_stat(self, path, *args, **kwargs):
        if isinstance(path, (str, bytes, os.PathLike)):
            self.check_read('metadata.stat', path)
        return self.original_stat(path, *args, **kwargs)

    def guarded_lstat(self, path, *args, **kwargs):
        self.check_read('metadata.lstat', path)
        return self.original_lstat(path, *args, **kwargs)

    def guarded_access(self, path, *args, **kwargs):
        self.check_read('metadata.access', path)
        return self.original_access(path, *args, **kwargs)

    def fresh_path(self, path):
        return self.stage_created and within(path, STAGE) or self.run_id is not None and any(
            within(path, parent / self.run_id) for parent in self.parents)

    def existing_cache_alias(self, path):
        try:
            info = os.lstat(path)
        except FileNotFoundError:
            return None
        return info if (info.st_dev, info.st_ino) in self.cache_ids else None

    def write_allowed(self, event, path, flags=0):
        target = key(path)
        if self.fresh_path(target):
            if self.existing_cache_alias(target) is not None:
                self.fail(event, 'A write would modify a shared immutable cache object')
            return
        shard = self.new_cache.parent if self.new_cache is not None else None
        if shard is not None and key(Path(target).parent) == key(shard) and re.fullmatch(
                r'\.publish-[a-zA-Z0-9_]{8}', Path(target).name) and not os.path.lexists(target):
            if not flags & os.O_EXCL or not flags & os.O_CREAT:
                self.fail(event, 'Cache temporaries require exclusive creation')
            self.temporary_cache.add(target)
            return
        if target in self.temporary_cache:
            return
        self.fail(event, 'Write escaped this preparation\'s new files')

    def install_cache(self, rows, new_hash):
        for row in rows:
            path = Path(row['cache']['path'])
            require(key(path) == key(self.cache_root / row['cache']['sha256'][:2] / row['cache']['sha256']),
                    'Unexpected cache input path')
            checked(row['cache'])
            target = Path(row['target']['path'])
            checked(row['target'])
            left, right = path.stat(), target.stat()
            require((left.st_dev, left.st_ino) == (right.st_dev, right.st_ino)
                    and getattr(left, 'st_file_attributes', 0) & READONLY,
                    'R11 immutable input is not the verified readonly cache alias')
            self.cache_rows[key(path)] = artifact(path)
            self.cache_ids.add((left.st_dev, left.st_ino))
        self.new_cache = self.cache_root / new_hash[:2] / new_hash
        if os.path.lexists(self.new_cache):
            item = checked({'path': str(self.new_cache), 'bytes': 6941696, 'sha256': new_hash})
            info = self.new_cache.stat()
            require(getattr(info, 'st_file_attributes', 0) & READONLY, 'Existing current SDK cache is mutable')
            self.cache_rows[key(self.new_cache)] = item
            self.cache_ids.add((info.st_dev, info.st_ino))

    def audit(self, event, args):
        if event.startswith(('subprocess.', 'ctypes.dlopen', 'ctypes.dlsym', 'socket.', 'urllib.', 'http.client.',
                             'os.exec', 'os.spawn')) or event in (
                'os.system', 'os.startfile', 'os.startfile/2', 'os.posix_spawn', 'os.posix_spawnp',
                'os.kill', 'os.killpg', 'os.fork', 'os.forkpty', 'winreg.OpenKey', 'winreg.CreateKey',
                'winreg.SetValue', 'winreg.SetValueEx', 'sqlite3.connect', 'sqlite3.connect/handle'):
            self.native_attempts += 1
            self.fail(event, 'Process execution, DLL loading, registry and network access are forbidden')
        if event in ('open', 'os.listdir', 'os.scandir', 'os.chdir') and args:
            path = args[0]
            writing = False
            flags = 0
            if event == 'open':
                mode, flags = args[1:3]
                writing = isinstance(mode, str) and any(c in mode for c in 'wax+') or (
                    type(flags) is int and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
            if isinstance(path, (str, bytes, os.PathLike)):
                self.check_read(event, path)
                if writing:
                    self.write_allowed(event, path, flags if type(flags) is int else 0)
            elif isinstance(path, int) and writing:
                info = os.fstat(path)
                allowed = False
                for temporary in self.temporary_cache:
                    try:
                        candidate = os.lstat(temporary)
                    except FileNotFoundError:
                        continue
                    allowed |= (candidate.st_dev, candidate.st_ino) == (info.st_dev, info.st_ino)
                if not allowed:
                    self.fail(event, 'Writable descriptor is not a newly created cache temporary')
        if event == 'os.mkdir':
            path = Path(os.fsdecode(args[0]))
            self.check_read(event, path)
            if key(path) == key(STAGE) and not os.path.lexists(path):
                self.stage_created = True
                return
            if any(key(path.parent) == key(parent) for parent in self.parents):
                if key(path) in self.allocated_roots and os.path.lexists(path):
                    info = path.lstat()
                    if path.name != self.run_id or not stat.S_ISDIR(info.st_mode) or getattr(info, 'st_file_attributes', 0) & REPARSE:
                        self.fail(event, 'An allocated runtime/evidence directory changed type or identity')
                    return
                if not RUN_PATTERN.fullmatch(path.name) or os.path.lexists(path):
                    self.fail(event, 'Runner tried to reuse an existing runtime/evidence directory')
                if self.run_id is not None and path.name != self.run_id:
                    self.fail(event, 'Runner allocated more than one private run')
                self.run_id = path.name
                self.allocated_roots.add(key(path))
                return
            if self.fresh_path(path):
                return
            allowed_dirs = {key(self.cache_root), *(key(Path(p).parent) for p in self.cache_rows)}
            if self.new_cache is not None:
                allowed_dirs.add(key(self.new_cache.parent))
            if key(path) in allowed_dirs:
                if os.path.lexists(path):
                    info = path.lstat()
                    if not stat.S_ISDIR(info.st_mode) or getattr(info, 'st_file_attributes', 0) & REPARSE:
                        self.fail(event, 'Cache directory changed identity or type')
                return
            self.fail(event, 'Directory creation escaped the fresh run or exact cache shards')
        if event == 'os.link':
            source, target = (Path(os.fsdecode(value)) for value in args[:2])
            self.check_read(event, source)
            self.check_read(event, target)
            allowed_sources = set(self.cache_rows) | self.created_cache
            if key(source) not in allowed_sources or not self.fresh_path(target) or os.path.lexists(target):
                self.fail(event, 'Only verified cache-to-new-runtime hardlinks are allowed')
            info = source.stat()
            if not getattr(info, 'st_file_attributes', 0) & READONLY:
                self.fail(event, 'A mutable cache object cannot be linked')
            self.cache_ids.add((info.st_dev, info.st_ino))
            return
        if event in ('os.rename', 'os.replace'):
            source, target = (Path(os.fsdecode(value)) for value in args[:2])
            if (key(source) in self.temporary_cache and self.new_cache is not None
                    and key(target) == key(self.new_cache) and not os.path.lexists(target)):
                self.created_cache.add(key(target))
                return
            self.fail(event, 'Only atomic publication of this SDK cache object is allowed')
        if event == 'os.symlink':
            self.fail(event, 'Symlink creation is forbidden')
        if event in ('os.remove', 'os.rmdir', 'os.chmod', 'os.utime', 'os.truncate'):
            path = Path(os.fsdecode(args[0]))
            self.check_read(event, path)
            if key(path) in self.temporary_cache:
                return
            if not self.fresh_path(path):
                self.fail(event, 'Mutation escaped newly owned runtime/evidence/stage files')
            alias = self.existing_cache_alias(path)
            if alias is not None:
                if event == 'os.chmod' and stat.S_IMODE(alias.st_mode) == args[1] and getattr(
                        alias, 'st_file_attributes', 0) & READONLY:
                    self.idempotent_readonly_calls += 1
                    return
                if event == 'os.remove':
                    return  # Removing only the newly created alias cannot change cache bytes.
                self.fail(event, 'Shared cache attributes and content must remain unchanged')


def source_closure(initial):
    pending = [Path(path) for path in initial]
    result = {}
    while pending:
        path = pending.pop()
        if key(path) in result:
            continue
        result[key(path)] = artifact(path)
        tree = ast.parse(path.read_text(encoding='utf-8-sig'), filename=str(path))
        names = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.extend(alias.name.split('.')[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                names.append(node.module.split('.')[0])
        for name in names:
            candidate = PROJECT / 'tools' / (name + '.py')
            if candidate.is_file() and key(candidate) not in result:
                pending.append(candidate)
    return list(result.values())


def scoped_inventory(roots, additional):
    paths = [Path(path) for path in additional]
    for root in roots:
        for directory, children, files in os.walk(root, followlinks=False):
            for name in children:
                info = (Path(directory) / name).lstat()
                require(not getattr(info, 'st_file_attributes', 0) & REPARSE,
                        'Reparse directory appeared in owned outputs')
            paths.extend(Path(directory) / name for name in files)
    unique, aliases, logical = {}, 0, 0
    for path in paths:
        info = ordinary(path)
        identity = (info.st_dev, info.st_ino)
        if identity in unique:
            aliases += 1
        else:
            unique[identity] = {'path': str(path), 'bytes': info.st_size}
            logical += info.st_size
    return {'scope': 'NEW_RUNTIME_AND_EVIDENCE_PLUS_EXACT_NEW_CACHE_OBJECTS',
            'path_count': len(paths), 'unique_file_ids': len(unique),
            'hardlink_aliases_deduplicated': aliases, 'unique_logical_bytes': logical,
            'physical_allocation_measured': False, 'whole_project_net_measured': False,
            'includes_reused_input_file_ids': True}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-request', type=Path, required=True)
    parser.add_argument('--sdk-build', type=Path, required=True)
    parser.add_argument('--sdk-build-sha256', required=True)
    args = parser.parse_args(argv)
    require(not sys.flags.optimize, 'Run this bounded preparation without Python optimization')
    require(key(args.source_request) == key(SOURCE_REQUEST) and key(args.sdk_build) == key(SDK_BUILD),
            'This preparation accepts only the sealed R11 request and current SDK report')
    require(HASH_PATTERN.fullmatch(args.sdk_build_sha256), 'Expected a complete lowercase report SHA-256')
    require(not os.path.lexists(STAGE), 'Preparation stage already exists; inspect it before any further work')
    sys.dont_write_bytecode = True
    guard = PreparationGuard()
    sys.addaudithook(guard.audit)
    protected = {}

    def preserve(row):
        current = checked(row)
        previous = protected.setdefault(key(current['path']), current)
        require(previous == current, 'Conflicting protected artifact pins')
        return current

    try:
        preserve({'path': str(SOURCE_REQUEST), 'sha256': SOURCE_REQUEST_SHA, 'bytes': 50167})
        preserve({'path': str(IDENTITY), 'sha256': IDENTITY_SHA, 'bytes': 33616})
        preserve({'path': str(POST), 'sha256': POST_SHA, 'bytes': 49586})
        source, identity, post = read(SOURCE_REQUEST), read(IDENTITY), read(POST)
        require(post['status'] == 'PASS_CURRENT_RUNTIME_SDK_POST_PUBLICATION_CHECKS', 'Current SDK publication is not sealed')
        for field in ('index', 'document'):
            preserve(post[field])
        fixed = {
            'host_build': (PROJECT / f'evidence/ui_window_host/{HOST_BUILD}/build_result.json', 662669,
                           '8e6a2a283d22e042202d98b5e59320de5de73d1f98c44762e409f21f7fea1a02'),
            'default_release': (PROJECT / 'Play/EarlyAccess/release.json', 7907,
                                '5587028d64ff6206780837ee7112f0c34d62676fb0627ee099d4eb03aef9c2c5'),
            'default_launcher': (PROJECT / 'tools/Start-Engine.ps1', 11697,
                                 'c487ce6c89e374bb625961ce81cf6cbae210608c578542658038e6cb06173d7c'),
            'hold': (PROJECT / 'evidence/goody_hut/runtime_fonts/system_freeze_hold.json', 2341,
                     '6e7443f5ef796c9eadee4f7fdbc4123545467031be1d5c641159283078f56a5b'),
            'prepared': (PROJECT / 'evidence/goody_hut/runtime_fonts/prepared.json', 989,
                         '796cdf84885c408903f96d2ff1c3d414aef2008317bdb33338d79c1e1a573fa4')}
        for path, size, sha in fixed.values():
            preserve({'path': str(path), 'bytes': size, 'sha256': sha})
        hold = read(fixed['hold'][0])
        require(hold.get('engine_native_execution_still_held') is True and
                hold.get('offline_resume', {}).get('native_host_gamecore_hwnd_execution_allowed') is False,
                'The original-game test hold changed')
        require(source['run_id'] == SOURCE_RUN and source['smoke'] is False and source['resume_from'] is None
                and source['ui_support_from_run'] is None and source['stage_or_mods_changed'] is False,
                'R11 is not the expected unused private preparation')
        old_rows = {Path(row['path']).name: row for row in source['runtime_inputs']}
        require(len(old_rows) == len(source['runtime_inputs']) == 24, 'Expected exactly24 distinct R11 input names')
        for row in old_rows.values():
            require(key(Path(row['path']).parent) == key(PROJECT / 'Build/InteractiveGameRuntime' / SOURCE_RUN),
                    'R11 runtime input escaped its private directory')
            preserve(row)
        for row in identity['shared_terrain_inputs']:
            preserve(row)
        expected_font = identity['owned_font_binding']
        require(len(expected_font['inputs']) == 15, 'Expected the captured fifteen owned font inputs')
        for row in expected_font['inputs']:
            preserve(row)
        sdk_ref = preserve({'path': str(SDK_BUILD), 'sha256': args.sdk_build_sha256})
        sdk = read(SDK_BUILD)
        require(sdk['status'] == 'PASS_CURRENT_RUNTIME_SDK_CANDIDATE_COMPILED_LINKED_NOT_LOADED'
                and key(sdk['generated_dll']['path']) == key(SDK_DLL)
                and sdk['generated_dll']['sha256'] == SDK_SHA and sdk['gamecore_loaded'] is False,
                'SDK report does not identify the sealed current unloaded candidate')
        sdk_dll = preserve(sdk['generated_dll'])
        require(sdk_dll['bytes'] == 6941696, 'Current SDK candidate size differs')
        preserve(sdk['shared_lua_dll'])
        require(sdk['shared_lua_dll']['sha256'] == old_rows['ZeroSisLua51_x64.dll']['sha256'],
                'Current SDK expects another Lua dependency')
        guard.install_cache(identity['immutable_cache_links'], SDK_SHA)
        for row in guard.cache_rows.values():
            preserve(row)
        original_cache_paths = set(guard.cache_rows)
        private_databases = {name: preserve(old_rows[name]) for name in ('rules.db', 'localization.db')}
        require(sum(row['bytes'] for row in private_databases.values()) == 57501696,
                'Unexpected private database profile')
        inventory = source['interactive_ui_support_inventory']
        require(set(inventory['tools']) == set(TOOLS), 'Source has an unexpected UI support closure')
        for name in TOOLS:
            preserve(inventory['tools'][name]['frozen'])
            current = preserve(artifact(PROJECT / 'tools' / name))
            require(current['sha256'] == inventory['tools'][name]['frozen']['sha256'],
                    'Current support tool differs from R11: ' + name)
        for name, path in (('inline_icons', PROJECT / 'evidence/ui_popup/assets/inline_icons.json'),
                           ('asset_preparation_provenance', PROJECT / 'evidence/ui_popup/assets/prepared.json')):
            frozen = preserve(inventory[name]['frozen'])
            current = preserve(artifact(path))
            require(current['sha256'] == frozen['sha256'], 'Current owned UI assets differ from R11')
        preserve(inventory['frozen_support_manifest'])
        preserve(source['interactive_ui_support'])
        policy = PROJECT / 'evidence/concurrency/runtime_configuration/PolicyInfo.ini'
        preserve(artifact(policy))
        require(re.findall(rb'^\s*PolicyInfo\s*=\s*([01])\s*$', policy.read_bytes(), re.M) == [b'1'],
                'Private PolicyInfo must have the retained single enabled value')
        unit = source['unit_assets']['source_manifest']
        unit_manifest = Path(unit['original_path'])
        require(key(unit_manifest) == key(PROJECT / 'Build/UnitAssets/fbb3b9ec4b43242cbee022b9cdf712f37ccbdf6290015ee2ee27b6547a570573/unit-assets.manifest.json'),
                'Unit manifest is not the existing owned unit package')
        preserve({'path': str(unit_manifest), 'bytes': unit['bytes'], 'sha256': unit['sha256']})
        helpers = source_closure([PROJECT / 'tools/run_interactive_game.py', Path(__file__).absolute(),
                                  *(PROJECT / 'tools' / name for name in TOOLS),
                                  PROJECT / 'tools/current_runtime_sdk_input.py', PROJECT / 'tools/sealed_terrain_input.py'])
        for row in helpers:
            preserve(row)
        host = read(fixed['host_build'][0])
        host_source_matches = 0
        for row in host['sources']:
            frozen = preserve(row)
            original = row.get('original_source')
            require(original and within(original, PROJECT), 'A B11 source has no owned current-source mapping')
            current_source = preserve(artifact(original))
            require((current_source['bytes'], current_source['sha256']) ==
                    (frozen['bytes'], frozen['sha256']), 'A current Host source differs from B11: ' + str(original))
            host_source_matches += 1
        require(host_source_matches == 80, 'Expected the exact eighty-source B11 mapping')
        catalog = next(row for row in host['sources'] if Path(row['path']).name == 'NativeSaveCatalog.h')
        preserve(catalog)
        catalog_text = Path(catalog['path']).read_text(encoding='utf-8')
        require('if(entry.archive.sections[0].bytes!=bundleManifest)' in catalog_text and
                'Load source belongs to another engine bundle' in catalog_text,
                'B11 exact-bundle save rejection source contract differs')
        STAGE.mkdir(exist_ok=False)
        arguments = [str(PROJECT / 'tools/run_interactive_game.py'), '--host-build', str(fixed['host_build'][0]),
                     '--runtime-sdk-build', str(SDK_BUILD), '--runtime-sdk-build-sha256', args.sdk_build_sha256,
                     '--terrain-assets-from-run', SOURCE_RUN, '--unit-assets-manifest', str(unit_manifest),
                     '--policy-info-settings', str(policy), '--found-value-workers', 'auto', '--language', 'ko_KR',
                     '--top-panel', '--action-info-panel', '--notification-panel']
        write_new(STAGE / 'preparation_started.json', {
            'schema': 'zerosis.current_sdk_play.preparation_started.v1', 'source_request': artifact(SOURCE_REQUEST),
            'sdk_build': sdk_ref, 'sdk_dll': sdk_dll, 'runner_argv': arguments,
            'protected_inputs': list(protected.values()), 'source_helper_count': len(helpers),
            'new_game_only': True, 'native_execution_allowed': False, 'default_promotion_allowed': False})
        old_path, old_argv = sys.path[:], sys.argv[:]
        stdout, stderr = Capture(), Capture()
        try:
            sys.path.insert(0, str(PROJECT / 'tools'))
            with ExitStack() as stack:
                stack.enter_context(patch.object(os, 'stat', guard.guarded_stat))
                stack.enter_context(patch.object(os, 'lstat', guard.guarded_lstat))
                stack.enter_context(patch.object(os, 'access', guard.guarded_access))
                runner = importlib.import_module('run_interactive_game')
                renderer = importlib.import_module('render_ui_popup')
                require(key(runner.__file__) == key(PROJECT / 'tools/run_interactive_game.py') and
                        tuple(runner.FOUND_VALUE_SUPPORT_TOOLS) == TOOLS, 'Unexpected production runner import')
                require(renderer.owned_font_input_binding(read(PROJECT / 'evidence/ui_popup/assets/prepared.json')) == expected_font,
                        'Production renderer no longer resolves the captured owned font bank')
                sys.argv = arguments.copy()
                with redirect_stdout(stdout), redirect_stderr(stderr), patch.object(
                        runner.subprocess, 'Popen', side_effect=RuntimeError('Native execution is forbidden')) as process:
                    code = runner.main()
                    require(code in (None, 0) and process.call_count == 0, 'Production prepare-only call failed')
        finally:
            sys.path[:] = old_path
            sys.argv[:] = old_argv
            for name, capture in (('materializer.stdout.log', stdout), ('materializer.stderr.log', stderr)):
                with (STAGE / name).open('x', encoding='utf-8', newline='\n') as stream:
                    stream.write(capture.getvalue())
        summaries = [json.loads(line) for line in stdout.getvalue().splitlines() if line.startswith('{')]
        require(len(summaries) == 1 and summaries[0]['status'] == 'PRIVATE_CONTINUOUS_GAME_PREPARED'
                and summaries[0]['run_id'] == guard.run_id, 'No unique actual production preparation result')
        runtime, evidence = (parent / guard.run_id for parent in guard.parents)
        request_path = evidence / 'request.json'
        require(key(summaries[0]['request']) == key(request_path), 'Runner summary points outside its new request')
        request = read(request_path)
        current = {Path(row['path']).name: row for row in request['runtime_inputs']}
        require(len(current) == len(request['runtime_inputs']) == 24 and current.keys() == old_rows.keys(),
                'Prepared runtime has a different input name set')
        changed = {name for name in current if current[name]['sha256'] != old_rows[name]['sha256']}
        require(changed == {'CvGameCoreDLL_Expansion2_x64.dll', 'bundle.manifest'},
                'Unexpected R11 runtime input hash deltas')
        for name, row in current.items():
            require(key(row['path']) == key(runtime / name), 'Actual prepared input escaped the new runtime')
            checked(row)
        require(current['CvGameCoreDLL_Expansion2_x64.dll']['sha256'] == SDK_SHA and
                key(current['CvGameCoreDLL_Expansion2_x64.dll']['source']) == key(SDK_DLL),
                'The actual new runtime does not use the current SDK')
        manifest = 'ZEROSIS_HOST_BUNDLE_V4\n' + ''.join(
            Path(row['path']).name + '|' + row['sha256'] + '\n' for row in request['runtime_inputs']
            if Path(row['path']).name != 'bundle.manifest')
        require((runtime / 'bundle.manifest').read_text(encoding='ascii') == manifest and
                current['bundle.manifest']['sha256'] != old_rows['bundle.manifest']['sha256'],
                'New SDK did not receive its own exact bundle identity')
        require(request['smoke'] is False and request['resume_from'] is None and request['ui_support_from_run'] is None
                and request['input_profile'] == 'MANUAL_CONTINUOUS_GAME_LOOP' and request['stage_or_mods_changed'] is False
                and request['language'] == 'ko_KR' and all(request[name] is True for name in (
                    'top_panel', 'action_info_panel', 'notification_panel')), 'Prepared request is not the fixed new-game-only profile')
        require(request['runtime_sdk_candidate']['gamecore']['sha256'] == SDK_SHA and
                request['runtime_sdk_candidate']['report']['sha256'] == args.sdk_build_sha256,
                'Actual SDK selection differs from the pinned report')
        scope = request['runtime_sdk_candidate_scope']
        require(scope['status'] == 'PREPARED_NOT_EXECUTED' and scope['new_game_only'] is True and all(
            scope[name] is False for name in ('host_sdk_execution_verified', 'retail_save_restore_verified',
                                             'prior_bundle_save_migration_performed', 'default_release_changed')),
                'SDK candidate scope claims execution, migration or promotion')
        resume_path = Path(request['resume_launcher']['path'])
        checked(request['resume_launcher'])
        resume_text = resume_path.read_text(encoding='utf-8-sig')
        require(key(resume_path) == key(runtime / 'Resume.ps1') and
                "throw 'Save loading is disabled" in resume_text and
                all(value not in resume_text for value in ('play-load', 'ShowDialog', '$Checkpoint')),
                'The new-game-only candidate exposes a save-loading launcher')
        policy_record = request['policy_info_options']
        require(policy_record['origin'] == 'EXPLICIT_POLICY_SETTINGS_READ_ONLY' and
                policy_record['original_user_settings'] is None and policy_record['original_policy_info'] is None
                and key(policy_record['settings_input']['original_path']) == key(policy),
                'Actual preparation read a different policy origin')
        new_support = request['interactive_ui_support_inventory']
        require(set(new_support['tools']) == set(TOOLS), 'Actual runtime UI support closure changed')
        for name in TOOLS:
            require(checked(new_support['tools'][name]['frozen'])['sha256'] ==
                    inventory['tools'][name]['frozen']['sha256'], 'Actual UI support differs from R11: ' + name)
        for name in ('inline_icons', 'asset_preparation_provenance'):
            require(checked(new_support[name]['frozen'])['sha256'] == inventory[name]['frozen']['sha256'],
                    'Actual runtime UI asset identity differs from R11')
        require(renderer.owned_font_input_binding(read(new_support['asset_preparation_provenance']['frozen']['path'])) == expected_font,
                'Actual frozen runtime lost the owned font binding')
        methods = request['materializations']
        links = [row for row in methods if row.get('materialization_method') == 'hardlink']
        require(len(links) == 15, 'Expected fifteen readonly immutable runtime links')
        for row in links:
            cache, target = Path(row['cache']), Path(row['target'])
            left, right = ordinary(cache), ordinary(target)
            require((left.st_dev, left.st_ino) == (right.st_dev, right.st_ino)
                    and getattr(right, 'st_file_attributes', 0) & READONLY,
                    'Actual immutable input is not the expected readonly cache link')
        databases = []
        for name in private_databases:
            current_info, prior_info = ordinary(current[name]['path']), ordinary(old_rows[name]['path'])
            require((current_info.st_dev, current_info.st_ino) != (prior_info.st_dev, prior_info.st_ino)
                    and current_info.st_nlink == 1 and not getattr(current_info, 'st_file_attributes', 0) & READONLY,
                    'Private writable database is shared or readonly')
            databases.append(artifact(current[name]['path']))
        require(not any((runtime / name).exists() for name in ('sessions', 'checkpoint-input.zssave'))
                and not any((evidence / name).exists() for name in ('attempt.json', 'result.json', 'driver_result.json')),
                'Preparation unexpectedly created native execution or save outputs')
        for row in protected.values():
            checked(row)
        imported = {}
        for name, module in list(sys.modules.items()):
            path = getattr(module, '__file__', None)
            if path and within(path, PROJECT / 'tools') and Path(path).suffix == '.py':
                require(key(path) in protected, 'A local helper was imported without a pre-execution hash pin')
                imported[name] = artifact(path)
        require(not guard.denied and guard.native_attempts == 0, 'Forbidden operation was attempted')
        for path in guard.temporary_cache:
            require(not os.path.lexists(path), 'Unpublished SDK cache temporary remains')
        new_cache_paths = [path for path in guard.created_cache if path not in original_cache_paths]
        retained_scope = scoped_inventory([runtime, evidence], new_cache_paths)
        new_unique_ids = set()
        baseline_ids = {tuple((Path(row['path']).stat().st_dev, Path(row['path']).stat().st_ino))
                        for row in guard.cache_rows.values()}
        new_owned_logical = 0
        for root in (runtime, evidence):
            for directory, _, files in os.walk(root, followlinks=False):
                for name in files:
                    info = ordinary(Path(directory) / name)
                    file_id = (info.st_dev, info.st_ino)
                    if file_id not in baseline_ids and file_id not in new_unique_ids:
                        new_unique_ids.add(file_id)
                        new_owned_logical += info.st_size
        retained_scope.update(new_unique_logical_bytes_excluding_reused_cache_ids=new_owned_logical,
                              new_cache_objects=len(new_cache_paths), private_database_bytes=57501696,
                              stage_receipts_excluded=True, directories_and_physical_allocation_excluded=True)
        result = {
            'schema': 'zerosis.current_sdk_play.prepared.v1', 'status': 'PREPARED_NOT_EXECUTED',
            'source_run_id': SOURCE_RUN, 'host_build_id': HOST_BUILD, 'run_id': guard.run_id,
            'current_candidate_prepared': True, 'default_current_prepared_runtime_unchanged': SOURCE_RUN,
            'b11_current_original_source_matches': host_source_matches,
            'request': artifact(request_path), 'sdk_build': sdk_ref, 'sdk_dll': sdk_dll,
            'actual_runner_main_calls': 1, 'runtime_inputs': 24, 'changed_runtime_input_names': sorted(changed),
            'immutable_hardlinks': len(links), 'cache_hits': sum(row.get('cache_method') == 'cache-hit' for row in links),
            'new_cache_objects': len(new_cache_paths), 'private_databases': databases,
            'frontend_tools_unchanged': True, 'owned_font_binding': expected_font,
            'protected_inputs_unchanged': len(protected), 'source_helpers': imported,
            'runner_argv': arguments, 'scoped_storage': retained_scope,
            'diagnostic_characters': {'stdout': stdout.characters, 'stderr': stderr.characters},
            'forbidden_access_attempts': guard.denied, 'native_process_or_ctypes_calls': guard.native_attempts,
            'existing_cache_attribute_changes_allowed': False,
            'idempotent_readonly_calls_on_new_aliases': guard.idempotent_readonly_calls,
            'new_game_only': True, 'prior_bundle_save_rejection_contract_preserved': True,
            'prior_bundle_save_rejection_scope': 'UNCHANGED_B11_SOURCE_AND_NEW_EXACT_MANIFEST_NOT_NATIVE_TESTED',
            'host_executed': False, 'gamecore_loaded': False, 'window_created': False,
            'retail_install_MODS_saves_settings_or_processes_accessed': False,
            'host_sdk_execution_verified': False, 'retail_save_restore_verified': False,
            'prior_bundle_save_migration_performed': False, 'default_promoted': False,
            'full_engine_goal_complete': False}
        write_new(STAGE / 'prepared.json', result)
        print(json.dumps({'status': result['status'], 'run_id': guard.run_id,
                          'request': result['request'], 'prepared': artifact(STAGE / 'prepared.json'),
                          'scoped_new_logical_bytes': new_owned_logical, 'host_executed': False,
                          'gamecore_loaded': False, 'default_promoted': False}, ensure_ascii=False))
        return 0
    except BaseException as error:
        if guard.stage_created and STAGE.is_dir() and not (STAGE / 'preparation_failure.json').exists():
            write_new(STAGE / 'preparation_failure.json', {
                'status': 'PREPARATION_FAILED_NO_NATIVE_EXECUTION', 'error': type(error).__name__ + ': ' + str(error),
                'run_id': guard.run_id, 'forbidden_access_attempts': guard.denied,
                'native_process_or_ctypes_calls': guard.native_attempts, 'cleanup_performed': False,
                'native_execution_verified': False, 'default_promoted': False})
        raise


if __name__ == '__main__':
    raise SystemExit(main())
