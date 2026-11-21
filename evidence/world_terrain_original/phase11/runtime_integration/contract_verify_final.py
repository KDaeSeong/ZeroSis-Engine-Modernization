"""Independently verify phase-eleven file-only runtime binding; never launch it."""
from __future__ import annotations

import sys
sys.dont_write_bytecode = True

import argparse
import ast
import base64
import gzip
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat


HERE = Path(__file__).absolute().parent
STAGE = HERE
PROJECT = STAGE.parents[3]
HOST_ID = '20261116T114748Z_014dd63ad3bc'
HOST_SHA = 'c3bb5ffc2e57630d28a8305f288b501352c03f0e1970b1dc5b321d6ba0683383'
SDK_SHA = '430f3122d0b555d6daae14aa7c011ef43ce8f978270477c8af596ca4b0493ab9'
PROFILE_SHA = '3e2ad9b8d1205f087b1ead5de5b846923035821b794691f26d42d21e2dec2c89'
CONTRACT_SHA = None
PLAN_SHA = None
FINAL_RESULT_SHA = None
EXPECTED_RUN_ID = None
PACKS = {
    'terrain': (112874723, '02104c582759bf0cefb58f97379699e45300eb2a9c6da6fdd3c65d1440cb84e8'),
    'fog': (8184971, '42ae12554e1514dd48a9a5df25f47b4280d22d180dff29d169c602334e879bcc'),
    'water': (5180388, '2ff227dae9d16398e038e8ea33624940a9581e0eb2d37c3891121fae22c25afc'),
    'lean': (3495363, '69c6780dbeb5f8605d8231cef944d0ec9392109b6ccc81a9d3b76ae83cfd0ef7'),
    'lighting': (730040, 'd0873d3915da23e45ee1b66187bb7e4174673a1e8cce1fea16b6151ff515e424'),
    'screen_light': (1398304, 'f02165b489bfe80557e1fd0246c0a2423f5494a28f4974d935120ea14528a0e0'),
}
ENVIRONMENT = {
    'ZEROSIS_FOG_ASSETS': 'fog',
    'ZEROSIS_WATER_ASSETS': 'water',
    'ZEROSIS_WATER_SURFACE_ASSETS': 'lean',
    'ZEROSIS_LIGHTING_ASSETS': 'lighting',
    'ZEROSIS_SCREEN_LIGHT_ASSETS': 'screen_light',
}
BACKEND_NAMES = {
    'ZeroSisHost_x64.exe', 'CvGameCoreDLL_Expansion2_x64.dll',
    'ZeroSisDatabase_x64.dll', 'ZeroSisLocalization_x64.dll',
    'rules.db', 'localization.db', 'icudt44l.dat', 'audio-catalog.bin',
    'script-catalog.bin', 'ZeroSisLua51_x64.dll', 'terrain-assets.bin',
    'unit-assets.bin', 'ZeroSisGrannyAnimationBridge.dll', 'Firaxis.Framework.dll',
    'Firaxis.Framework.Granny.dll', 'Firaxis.Framework.FirePlace.dll',
    'Firaxis.Framework.Granny.Implx64.dll', 'ZeroSisHost_x64.exe.config',
    'unitmodels_stringdatabase.gsd', 'Warrior.gr2', 'Warrior_V2.gr2',
    'Warrior_V4.gr2', 'Warrior_IdleA.gr2',
}
RUN_PATTERN = re.compile(r'\d{8}T\d{6}Z_[0-9a-f]{12}')
SHA_PATTERN = re.compile(r'[0-9a-f]{64}')


class VerificationError(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise VerificationError(message)


def key(path):
    return os.path.normcase(os.path.abspath(os.fspath(path)))


def absolute_path(value):
    require(type(value) is str and value and Path(value).is_absolute(), 'Expected an absolute path')
    path = Path(value)
    require('..' not in path.parts and not value.startswith(('\\\\', '//')), 'Escaped path')
    return path


def relative_path(value):
    require(type(value) is str and value and '\\' not in value and '\0' not in value,
            'Expected a plain slash-separated relative path')
    path = PurePosixPath(value)
    require(not path.is_absolute() and all(part not in ('', '.', '..') and ':' not in part
            for part in value.split('/')) and str(path) == value, 'Unsafe relative member path')
    return Path(*path.parts)


def ordinary(path, directory=False):
    path = absolute_path(str(path))
    for item in (*reversed(path.parents), path):
        info = item.lstat()
        require(not stat.S_ISLNK(info.st_mode) and not getattr(info, 'st_file_attributes', 0) & 0x400,
                'Reparse or symbolic-link path: ' + str(item))
        require(stat.S_ISDIR(info.st_mode) if item != path or directory else stat.S_ISREG(info.st_mode),
                'Nonordinary path: ' + str(item))
    return info


def snapshot(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns,
            getattr(info, 'st_file_attributes', 0), info.st_nlink)


def unique_pairs(pairs):
    result = {}
    for name, value in pairs:
        require(name not in result, 'Duplicate JSON member: ' + name)
        result[name] = value
    return result


def parse_json(raw):
    require(len(raw) <= 32 * 1024 * 1024, 'JSON exceeds the bounded contract')
    return json.loads(raw.decode('utf-8-sig'), object_pairs_hook=unique_pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(VerificationError('Nonfinite JSON')))


class Files:
    def __init__(self):
        self.paths = {}
        self.contents = {}
        self.bytes_hashed = 0

    def raw(self, path, maximum=32 * 1024 * 1024):
        info = ordinary(path)
        require(info.st_size <= maximum, 'Artifact exceeds read bound: ' + str(path))
        raw = Path(path).read_bytes()
        require(snapshot(info) == snapshot(ordinary(path)) and len(raw) == info.st_size,
                'File changed while read: ' + str(path))
        self.paths[key(path)] = (Path(path), snapshot(info))
        return raw

    def artifact(self, reference, readonly=False):
        require(type(reference) is dict and SHA_PATTERN.fullmatch(reference.get('sha256', '')),
                'Invalid artifact reference')
        path = absolute_path(reference.get('path'))
        require(path.is_relative_to(PROJECT), 'Artifact escaped the engine project: ' + str(path))
        info = ordinary(path)
        if 'bytes' in reference:
            require(type(reference['bytes']) is int and reference['bytes'] == info.st_size,
                    'Artifact length differs: ' + str(path))
        if 'file_identity' in reference:
            require(reference['file_identity'] == [info.st_dev, info.st_ino],
                    'Artifact file identity differs: ' + str(path))
        if readonly:
            require(getattr(info, 'st_file_attributes', 0) & 1, 'Mutable linked payload: ' + str(path))
        identity = (info.st_dev, info.st_ino)
        cached = self.contents.get(identity)
        if cached is None:
            digest = hashlib.sha256()
            with path.open('rb') as stream:
                require(snapshot(os.fstat(stream.fileno())) == snapshot(info), 'File changed before open')
                for block in iter(lambda: stream.read(1024 * 1024), b''):
                    digest.update(block)
                    self.bytes_hashed += len(block)
                require(snapshot(os.fstat(stream.fileno())) == snapshot(info), 'File changed during hash')
            cached = (info.st_size, digest.hexdigest())
            self.contents[identity] = cached
        require(cached == (info.st_size, reference['sha256']), 'Artifact SHA differs: ' + str(path))
        require(snapshot(ordinary(path)) == snapshot(info), 'File changed after hash')
        self.paths[key(path)] = (path, snapshot(info))
        return dict(path=str(path), bytes=info.st_size, sha256=cached[1],
                    file_identity=[info.st_dev, info.st_ino], readonly=bool(
                        getattr(info, 'st_file_attributes', 0) & 1), link_count=info.st_nlink,
                    attributes=getattr(info, 'st_file_attributes', 0), mtime_ns=info.st_mtime_ns)

    def document(self, reference):
        row = self.artifact(reference)
        return parse_json(self.raw(Path(row['path'])))

    def finish(self):
        for path, before in self.paths.values():
            require(snapshot(ordinary(path)) == before, 'Observed input changed before seal: ' + str(path))


def same_artifact(left, right):
    return type(left) is dict and type(right) is dict and key(left.get('path', '')) == key(
        right.get('path', '')) and left.get('sha256') == right.get('sha256') and (
            'bytes' not in left or 'bytes' not in right or left['bytes'] == right['bytes'])


def backend_manifest(raw):
    text = raw.decode('ascii')
    lines = text.splitlines()
    require(lines and lines[0] == 'ZEROSIS_HOST_BUNDLE_V4', 'Wrong backend manifest version')
    result = {}
    for line in lines[1:]:
        parts = line.split('|')
        require(len(parts) == 2, 'Malformed backend manifest row')
        name, digest = parts
        require(name in BACKEND_NAMES and name not in result and SHA_PATTERN.fullmatch(digest),
                'Unknown or duplicate backend manifest row')
        result[name] = digest
    require(set(result) == BACKEND_NAMES and len(result) == 23, 'Backend manifest must retain the 23 payload names')
    return result


def runtime_rows(rows, runtime):
    require(type(rows) is list and len(rows) == 24, 'Backend request must contain exactly 24 rows')
    result = {}
    for row in rows:
        require(type(row) is dict, 'Malformed runtime input')
        path = absolute_path(row.get('path'))
        require(path.parent == runtime and path.name in BACKEND_NAMES | {'bundle.manifest'} and
                path.name not in result and SHA_PATTERN.fullmatch(row.get('sha256', '')),
                'Runtime input path, name, SHA or uniqueness differs')
        result[path.name] = row
    require(set(result) == BACKEND_NAMES | {'bundle.manifest'}, 'Runtime input name set differs')
    return result


def snapshot_originals(files, row, base_result, run_id, runtime):
    archive = files.artifact(row)
    require(Path(archive['path']).is_relative_to(STAGE / 'overlay'), 'Snapshot archive escaped overlay evidence')
    with gzip.open(archive['path'], 'rb') as stream:
        raw = stream.read(32 * 1024 * 1024 + 1)
    doc = parse_json(raw)
    require(doc.get('schema') == 'zerosis.phase11.base_runtime_snapshot.v1' and
            doc.get('run_id') == run_id and doc.get('runtime_directory') == str(runtime) and
            same_artifact(doc.get('base_result'), base_result), 'Archived base snapshot identity differs')
    require(type(doc.get('files')) is list and len(doc['files']) == 3, 'Snapshot must retain the three originals')
    result, references = {}, {}
    expected_paths = {'request.json': PROJECT / 'evidence/interactive_game' / run_id / 'request.json',
                      'bundle.manifest': runtime / 'bundle.manifest', 'Play.ps1': runtime / 'Play.ps1'}
    for entry in doc['files']:
        name = entry.get('relative_path')
        require(name in expected_paths and name not in result, 'Unexpected or duplicate snapshot original')
        original = entry.get('artifact')
        require(type(original) is dict and key(original.get('path', '')) == key(expected_paths[name]) and
                SHA_PATTERN.fullmatch(original.get('sha256', '')), 'Archived original reference differs')
        data = base64.b64decode(entry['data_base64'], validate=True)
        require(len(data) == original.get('bytes', len(data)) and
                hashlib.sha256(data).hexdigest() == original['sha256'], 'Archived original bytes differ')
        result[name], references[name] = data, original
    require(set(result) == set(expected_paths), 'Snapshot lost a required original')
    return doc, result, references


def launcher_prefix(new_raw, original_raw, package_paths, asset_manifest, validator):
    # The unchanged entire original program must be the suffix. Only the narrow
    # file-check/environment prefix is admitted before that program.
    original = original_raw.decode('utf-8-sig')
    current = new_raw.decode('utf-8-sig')
    require(original and current.endswith(original), 'Original Play program was altered')
    prefix = current[:-len(original)]
    require(prefix and '\0' not in prefix, 'Missing launcher binding prefix')
    prefix_paths = prefix.replace('\\', '/')
    for variable, role in ENVIRONMENT.items():
        member = str(package_paths[role]).replace('\\', '/')
        require(re.search(r"(?mi)^\s*\$env:" + re.escape(variable) +
                          r"\s*=\s*Join-Path\s+\$PSScriptRoot\s+'" + re.escape(member) + r"'\s*$", prefix_paths),
                'Launcher must bind a bundle-local package: ' + variable)
        require(len(re.findall(r'(?i)\$env:' + re.escape(variable) + r'\b', prefix)) == 1,
                'Launcher reassigns a supplemental binding')
    require('WorldAssets/verify_assets.py' in prefix.replace('\\', '/') and
            '--root $PSScriptRoot' in prefix and '--manifest' in prefix and
            '--manifest-sha256 ' + asset_manifest['sha256'] in prefix and
            str(relative_path('WorldAssets/assets.manifest.json')).replace('\\', '/') in prefix.replace('\\', '/'),
            'Launcher does not verify its exact bundle asset manifest')
    require(re.search(r'(?is)if\s*\(\s*\$LASTEXITCODE\s*-ne\s*0\s*\)\s*\{\s*throw\b', prefix),
            'Launcher does not stop after failed asset verification')
    require(not re.search(r'(?i)Start-Process|Invoke-Expression|Add-Type|SetEnvironmentVariable|Set-ItemProperty|Remove-Item|Copy-Item|Move-Item|\breg(?:\.exe)?\b', prefix),
            'Launcher prefix has a process, registry or file mutation command')
    require(len(re.findall(r'(?m)^\s*&\s+', prefix)) == 1, 'Launcher prefix must invoke only one file validator')
    require(validator['sha256'] and '--mode' not in prefix and '--play' not in prefix,
            'Launcher prefix must not launch the Host or driver')
    return dict(original_play_bytes=len(original_raw), original_play_unchanged=True,
                prefix_lines=len(prefix.splitlines()), five_bundle_local_bindings=True,
                verification_precedes_driver=True, launcher_executed=False)


def validator_ast(raw):
    tree = ast.parse(raw.decode('utf-8-sig'))
    allowed_imports = {'__future__', 'argparse', 'pathlib', 'hashlib', 'json', 'os', 'stat', 'sys', 'struct', 're'}
    forbidden_names = {'eval', 'exec', '__import__', 'compile', 'breakpoint', 'input'}
    forbidden_attributes = {'system', 'popen', 'Popen', 'run', 'call', 'check_call', 'check_output',
                            'startfile', 'execv', 'execve', 'spawnv', 'spawnve', 'fork', 'kill',
                            'dlopen', 'dlsym', 'WinDLL', 'CDLL', 'LoadLibrary', 'import_module',
                            'spec_from_file_location', 'module_from_spec', 'connect', 'urlopen',
                            'write_text', 'write_bytes', 'unlink', 'rmdir', 'mkdir', 'rename', 'replace',
            'chmod', 'utime', 'truncate', 'symlink_to', 'hardlink_to'}
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split('.')[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            require(node.level == 0 and node.module, 'Validator has a relative import')
            imports.add(node.module.split('.')[0])
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                require(node.func.id not in forbidden_names, 'Validator dynamically executes input')
            if isinstance(node.func, ast.Attribute):
                require(node.func.attr not in forbidden_attributes, 'Validator has a forbidden operation')
            if isinstance(node.func, ast.Attribute) and node.func.attr == 'open' or isinstance(node.func, ast.Name) and node.func.id == 'open':
                mode_args = node.args[:1] if isinstance(node.func, ast.Attribute) else node.args[1:2]
                for arg in mode_args:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        require(not any(char in arg.value for char in 'wax+'), 'Validator opens an output file')
                for kw in node.keywords:
                    if kw.arg == 'mode' and isinstance(kw.value, ast.Constant):
                        require(kw.value.value in ('r', 'rb', 'rt'), 'Validator opens an output file')
    require(imports <= allowed_imports, 'Validator imports an unapproved module')
    return dict(ast_parsed=True, imports=sorted(imports), native_or_network_imports=False,
                imported_or_executed=False, semantic_runtime_acceptance_claimed=False)


def verify(result_path):
    files = Files()
    result_path = absolute_path(str(result_path))
    require(result_path == STAGE / 'overlay/result.json', 'Expected the exact phase-eleven overlay result')
    result_raw = files.raw(result_path)
    result_ref = dict(path=str(result_path), bytes=len(result_raw), sha256=hashlib.sha256(result_raw).hexdigest())
    require(result_ref['sha256'] == FINAL_RESULT_SHA, 'Final result differs from the parent-sealed artifact')
    result = parse_json(result_raw)
    require(result.get('schema') == 'zerosis.phase11.runtime_asset_integration.v1' and
            type(result.get('status')) is str and result['status'].startswith('PASS') and
            result.get('native_attempts') == 0 and type(result['native_attempts']) is int and
            result.get('default_or_registration_changed') is False and
            result.get('supersedes_base_runtime_image') is True,
            'Final integration result claims execution/promotion or is incomplete')
    run_id = result.get('run_id')
    require(type(run_id) is str and RUN_PATTERN.fullmatch(run_id) and
            run_id == EXPECTED_RUN_ID and run_id not in ('20261115T134603Z_aa8853762399', '20261115T101941Z_99b3c393ee9a', '20261115T011241Z_4c8fd55e99db', '20261108T003146Z_40a8030edf08'),
            'Runtime is not a newly allocated run')
    runtime = absolute_path(result.get('runtime_directory'))
    require(runtime == PROJECT / 'Build/InteractiveGameRuntime' / run_id, 'Runtime escaped its new-game root')
    ordinary(runtime, directory=True)
    require(not (runtime / 'sessions').exists() and not list(runtime.glob('interactive-ui-*.json')),
            'Fresh file-only runtime has session or UI-execution outputs')
    require(result.get('guard_denials') == [] and result.get('new_game_only') is True and
            result.get('source_engine_changes') == result.get('host_rebuilds') ==
            result.get('additional_asset_payload_copies') == 0, 'Overlay changed engine code or claims native activity')
    plan_ref = files.artifact(result['plan'])
    require(Path(plan_ref['path']) == STAGE / 'overlay/plan.json' and plan_ref['sha256'] == PLAN_SHA,
            'Final result does not match the reviewed exact plan')
    plan = files.document(plan_ref)
    require(plan.get('run_id') == run_id and plan.get('runtime_directory') == str(runtime), 'Plan/runtime identity differs')
    files.artifact(plan['adapter_source'])
    files.artifact(plan['validator_source'])
    files.artifact(plan['compiled_asset_binding'])
    contract = files.document(dict(path=str(HERE / 'contract_preparer_audit.json'), sha256=CONTRACT_SHA))
    audited_sources = dict(contract['sources'])
    audited_sources.update(contract['helpers'])
    for reference in audited_sources.values():
        files.artifact(reference)
    profile = files.document(dict(path=str(PROJECT / 'evidence/world_terrain_original/phase10/pair_preparation' /
                                          HOST_ID / 'prepared_profile.json'), sha256=PROFILE_SHA))
    require(profile['build_id'] == HOST_ID and profile['executable_sha256'] == HOST_SHA and
            profile['prepared_profile_only'] is True and profile['globally_registered'] is False and
            profile['native_execution'] is False, 'Current Host profile changed or gained execution approval')
    base_ref = files.artifact(result['base_result'])
    require(Path(base_ref['path']) == STAGE / 'base_preparation' / HOST_ID / 'materialization/result.json',
            'Base result is outside the exact guarded preparation stage')
    base_result = files.document(base_ref)
    require(base_result.get('status') == 'PASS_CURRENT_HOST_AND_GREAT_WORK_SDK_PREPARED_NOT_EXECUTED' and
            base_result.get('run_id') == run_id and base_result.get('host_build_id') == HOST_ID and
            base_result.get('native_attempts') == 0 and base_result.get('guard_denials') == [] and
            all(base_result.get(field) is False for field in ('host_or_sdk_executed', 'default_promoted',
                'save_compatibility_verified', 'prior_bundle_migrated', 'full_engine_goal_complete')),
            'Base result is not its guarded unexecuted new-game preparation')
    archive, original, original_refs = snapshot_originals(files, result['base_snapshot'], base_ref, run_id, runtime)
    require(same_artifact(original_refs['request.json'], base_result['request']) and
            same_artifact(original_refs['bundle.manifest'], base_result['bundle_manifest']),
            'Archived original request/manifest do not match the historical base result')
    base_request = parse_json(original['request.json'])
    require(same_artifact(base_request['launcher'], original_refs['Play.ps1']) and
            base_request.get('run_id') == run_id and base_request.get('smoke') is False and
            base_request.get('resume_from') is None, 'Archived launcher/request provenance differs')
    # Do not resolve historical base_result.request against the now-rewritten
    # live request. The hash-authenticated archive is its original byte source.
    request_ref = files.artifact(result['request'])
    require(Path(request_ref['path']) == PROJECT / 'evidence/interactive_game' / run_id / 'request.json',
            'Final request path escaped its isolated run')
    request = files.document(request_ref)
    require(request_ref['file_identity'] == original_refs['request.json']['file_identity'] and
            request_ref['attributes'] == original_refs['request.json']['file_attributes'] == 32,
            'The private request was replaced or its attributes were changed')
    require(request.get('run_id') == run_id and request.get('smoke') is False and
            request.get('resume_from') is None and request.get('stage_or_mods_changed') is False,
            'Final request enables native smoke or prior saves')
    allowed_changes = {'runtime_inputs', 'terrain_assets', 'materializations', 'launcher', 'launcher_control_metadata'}
    require(set(request) - set(base_request) == {'presentation_asset_binding', 'presentation_asset_overlay'},
            'Unexpected new request fields')
    require({name for name, value in base_request.items() if request.get(name) != value} == allowed_changes,
            'Expected exactly the five documented existing request fields to change')
    for name, value in base_request.items():
        if name not in allowed_changes:
            require(name in request and request[name] == value, 'Unrelated request field changed: ' + name)
    before_rows = runtime_rows(base_request['runtime_inputs'], runtime)
    current_rows = runtime_rows(request['runtime_inputs'], runtime)
    changed = {name for name in current_rows if current_rows[name]['sha256'] != before_rows[name]['sha256']}
    require(changed == {'terrain-assets.bin', 'bundle.manifest'}, 'Unexpected changes after base preparation')
    for name in set(current_rows) - changed:
        require(current_rows[name] == before_rows[name], 'An unchanged backend row changed shape or provenance: ' + name)
    require({k: v for k, v in current_rows['bundle.manifest'].items() if k != 'sha256'} ==
            {k: v for k, v in before_rows['bundle.manifest'].items() if k != 'sha256'},
            'Backend manifest row changed beyond its SHA')
    require(set(current_rows['terrain-assets.bin']) == set(before_rows['terrain-assets.bin']) and
            {k: v for k, v in current_rows['terrain-assets.bin'].items() if k not in ('sha256', 'source')} ==
            {k: v for k, v in before_rows['terrain-assets.bin'].items() if k not in ('sha256', 'source')},
            'Terrain row changed beyond its direct source and SHA')
    manifest_before = backend_manifest(original['bundle.manifest'])
    manifest_after = backend_manifest(files.raw(runtime / 'bundle.manifest'))
    manifest_current = files.artifact(current_rows['bundle.manifest'])
    require(manifest_current['file_identity'] == original_refs['bundle.manifest']['file_identity'] and
            manifest_current['attributes'] == original_refs['bundle.manifest']['file_attributes'] == 32 and
            manifest_current['link_count'] == 1, 'The private backend manifest was replaced or had attributes changed')
    require({name for name in manifest_after if manifest_after[name] != manifest_before[name]} == {'terrain-assets.bin'},
            'Backend manifest changed beyond the V2 terrain row')
    for name, row in current_rows.items():
        files.artifact(row, readonly=name != 'terrain-assets.bin' and
                       Path(name).suffix.lower() in ('.exe', '.dll', '.bin', '.dat'))
        if name != 'bundle.manifest':
            require(row['sha256'] == manifest_after[name], 'Request/backend manifest disagree: ' + name)
    require(current_rows['ZeroSisHost_x64.exe']['sha256'] == HOST_SHA and
            current_rows['CvGameCoreDLL_Expansion2_x64.dll']['sha256'] == SDK_SHA,
            'Latest Host/SDK pair differs')
    for name, backend_name in (('host', 'ZeroSisHost_x64.exe'), ('gamecore', 'CvGameCoreDLL_Expansion2_x64.dll')):
        require(same_artifact(result[name], current_rows[backend_name]) and same_artifact(result[name], base_result[name]),
                'Result/backend/base pair disagree: ' + name)
        files.artifact(result[name], readonly=True)
    manifest_ref = files.artifact(result['asset_manifest'])
    require(Path(manifest_ref['path']) == runtime / 'WorldAssets/assets.manifest.json' and
            same_artifact(request.get('presentation_asset_binding'), manifest_ref),
            'Request lacks its current bundle-local asset manifest')
    asset_manifest = files.document(manifest_ref)
    require(asset_manifest.get('schema') == 'zerosis.world_assets.runtime_binding.v1' and
            asset_manifest.get('runtime_directory') == str(runtime) and
            same_artifact(asset_manifest.get('host'), result['host']) and
            same_artifact(asset_manifest.get('gamecore'), result['gamecore']) and
            type(asset_manifest.get('packages')) is dict and set(asset_manifest['packages']) == set(PACKS) and
            type(result.get('packages')) is dict and set(result['packages']) == set(PACKS),
            'Asset manifest identity, roles or pair differs')
    linked, package_paths = {}, {}
    for role, (size, digest) in PACKS.items():
        member = asset_manifest['packages'][role]
        require(member.get('bytes') == size and member.get('sha256') == digest,
                'Wrong phase-ten immutable asset pin: ' + role)
        relative = relative_path(member.get('relative_path'))
        require(relative == Path('terrain-assets.bin') if role == 'terrain' else
                relative.parent == Path('WorldAssets') and relative.suffix == '.bin',
                'Asset target is not in its exact runtime role')
        require(runtime / relative == Path(plan['packages'][role]['target_path']), 'Asset target differs from the reviewed plan')
        target_path = runtime / relative
        row = result['packages'][role]
        require(row.get('method') == 'hardlink' and type(row.get('source')) is dict and
                type(row.get('target')) is dict and key(row['target'].get('path', '')) == key(target_path) and
                row['source'].get('sha256') == row['target'].get('sha256') == digest and
                row['source'].get('bytes') == row['target'].get('bytes') == size,
                'Asset hardlink record differs: ' + role)
        # Existing source packs have the archive attribute, not READONLY. Their
        # immutability is a no-write/read-only-consumer policy; changing attrs on
        # a new hardlink would also change the donor and is expressly forbidden.
        source, target = files.artifact(row['source']), files.artifact(row['target'])
        require(source['file_identity'] == target['file_identity'] and source['link_count'] == target['link_count'] >= 2,
                'Asset is a copy or different file identity: ' + role)
        require(source['attributes'] == target['attributes'] == 32 and
                source['mtime_ns'] == target['mtime_ns'] and not source['readonly'] and not target['readonly'],
                'Asset donor attrs or mtime changed instead of retaining the no-write-use policy: ' + role)
        planned_source = plan['packages'][role]['source']
        require(same_artifact(row['source'], planned_source) and source['file_identity'] == planned_source['file_identity'] and
                source['mtime_ns'] == planned_source['mtime_ns'] and source['link_count'] == planned_source['links'] + 1,
                'Asset donor differs from the reviewed original or has an unexpected link mutation')
        require(not Path(source['path']).is_relative_to(runtime) and Path(source['path']).is_relative_to(PROJECT / 'Build'),
                'Asset source must reuse a pre-existing engine build/cache input')
        linked[role], package_paths[role] = dict(source=source, target=target, method='hardlink',
            read_only=False, immutability_policy='READ_ONLY_USE_NO_ATTRIBUTE_CHANGE'), relative
    require(len({key(runtime / path) for path in package_paths.values()}) == 6, 'Asset target roles alias a path')
    require(key(current_rows['terrain-assets.bin'].get('source', '')) == key(linked['terrain']['source']['path']),
            'Terrain backend row does not identify the new direct donor')
    require(same_artifact(request['terrain_assets']['package'], linked['terrain']['target']),
            'Terrain provenance still points to the legacy package')
    terrain_manifest = files.document(request['terrain_assets']['source_manifest'])
    require(terrain_manifest.get('format') == 'ZEROSIS_CIV5_ORIGINAL_TERRAIN_PACKAGE_V2' and
            type(terrain_manifest.get('package')) is dict and
            terrain_manifest['package'].get('sha256') == PACKS['terrain'][1] and
            terrain_manifest['package'].get('bytes') == PACKS['terrain'][0],
            'Terrain source manifest is not the exact V2 package provenance')
    require(request['terrain_assets'].get('originals_checked_during_preparation') is False,
            'File-only terrain integration claims a retail recheck')
    base_materializations = base_request.get('materializations')
    require(type(base_materializations) is list, 'Missing base materialization provenance')
    original_terrain = [row for row in base_materializations if key(row.get('target', '')) == key(runtime / 'terrain-assets.bin')]
    require(len(original_terrain) == 1 and archive.get('original_terrain_materialization') == original_terrain[0],
            'Archived terrain link provenance differs')
    retained = [row for row in base_materializations if row != original_terrain[0]]
    methods = request.get('materializations')
    require(type(methods) is list and len(methods) == len(retained) + 6 and methods[:len(retained)] == retained,
            'Unrelated materializations were changed or legacy terrain link remains')
    appended = {key(row.get('target', '')): row for row in methods[len(retained):]}
    require(set(appended) == {key(runtime / path) for path in package_paths.values()},
            'Appended materializations must be exactly the six direct links')
    for role, pair in linked.items():
        row = appended[key(pair['target']['path'])]
        require(row.get('materialization_method', row.get('method')) == 'hardlink' and
                row.get('sha256') == pair['target']['sha256'] and row.get('read_only') is False and
                row.get('immutability_policy') == 'READ_ONLY_USE_NO_ATTRIBUTE_CHANGE',
                'Appended materialization is not its exact no-attribute-change hardlink')
    validator = asset_manifest.get('validator')
    require(type(validator) is dict and validator.get('relative_path') == 'WorldAssets/verify_assets.py' and
            type(validator.get('bytes')) is int and validator['bytes'] > 0,
            'Missing bundle-local file validator')
    validator_ref = files.artifact(dict(validator, path=str(runtime / relative_path(validator['relative_path']))))
    require(validator_ref['sha256'] == plan['validator_source']['sha256'] and
            validator_ref['bytes'] == plan['validator_source']['bytes'] and
            same_artifact(result['validator'], validator_ref), 'Bundled validator differs from its reviewed source')
    validator_review = validator_ast(files.raw(Path(validator_ref['path'])))
    expected_world_files = {path.name for role, path in package_paths.items() if role != 'terrain'} | {
        'assets.manifest.json', 'verify_assets.py'}
    children = list((runtime / 'WorldAssets').iterdir())
    require({path.name for path in children} == expected_world_files, 'WorldAssets has unexpected or missing members')
    for path in children:
        ordinary(path)
    launcher = files.artifact(result['launcher'])
    require(Path(launcher['path']) == runtime / 'Play.ps1' and same_artifact(request['launcher'], launcher) and
            same_artifact(request['launcher_control_metadata']['play'], launcher) and
            same_artifact(request['launcher_control_metadata']['selected'], launcher),
            'Final launcher control hashes differ')
    controls = request['launcher_control_metadata']
    base_controls = base_request['launcher_control_metadata']
    require(set(controls) == set(base_controls), 'Launcher control metadata shape changed')
    for name in set(controls) - {'play', 'selected'}:
        require(controls[name] == base_controls[name], 'Unrelated launcher control changed: ' + name)
    launcher_review = launcher_prefix(files.raw(runtime / 'Play.ps1'), original['Play.ps1'],
                                      package_paths, manifest_ref, validator_ref)
    require(launcher['file_identity'] == original_refs['Play.ps1']['file_identity'] and
            launcher['attributes'] == original_refs['Play.ps1']['file_attributes'] == 32,
            'Private launcher identity or attrs changed')
    resume = files.artifact(request['resume_launcher'])
    require(same_artifact(request['resume_launcher'], base_request['resume_launcher']) and
            b"throw 'Save loading is disabled" in files.raw(Path(resume['path'])),
            'Resume became enabled or changed')
    scope = request['runtime_sdk_candidate_scope']
    require(scope.get('new_game_only') is True and scope.get('host_sdk_execution_verified') is False and
            scope.get('prior_bundle_save_migration_performed') is False and scope.get('default_release_changed') is False,
            'Current SDK scope claims execution or migration')
    shared_support = result.get('shared_support')
    require(type(shared_support) is list and len(shared_support) == 8, 'Expected exactly eight deduplicated support inputs')
    donor_id = '20261115T134603Z_aa8853762399'
    donor_root = PROJECT / 'Build/InteractiveGameRuntime' / donor_id
    donor_request_path = PROJECT / 'evidence/interactive_game' / donor_id / 'request.json'
    donor_request = parse_json(files.raw(donor_request_path))
    donor_inventory = donor_request['interactive_ui_support_inventory']
    source_refs = [row['frozen'] for row in donor_inventory['tools'].values()] + [
        donor_inventory['inline_icons']['frozen'], donor_inventory['asset_preparation_provenance']['frozen']]
    require(len(source_refs) == 8, 'Donor frozen support closure is not the retained eight inputs')
    expected_support = {key(row['path']): row for row in source_refs}
    require(len(expected_support) == 8, 'Duplicate donor support input')
    shared_verified = []
    seen_support = set()
    planned_support = {key(row['source']['path']): row['source'] for row in plan['shared_support']}
    for row in shared_support:
        require(type(row) is dict and row.get('method') == 'hardlink' and type(row.get('source')) is dict and
                type(row.get('target')) is dict, 'Malformed shared support link')
        source_key = key(row['source'].get('path', ''))
        require(source_key in expected_support and source_key not in seen_support and
                same_artifact(row['source'], expected_support[source_key]), 'Unexpected shared support donor')
        seen_support.add(source_key)
        source_path = absolute_path(row['source']['path'])
        require(source_path.is_relative_to(donor_root / 'interactive_ui_support'), 'Shared support escaped retained donor')
        relative = source_path.relative_to(donor_root)
        require(key(row['target'].get('path', '')) == key(runtime / relative), 'Shared support changed its sibling path')
        source, target = files.artifact(row['source']), files.artifact(row['target'])
        require(source['file_identity'] == target['file_identity'] and source['link_count'] == target['link_count'] >= 2 and
                source['sha256'] == target['sha256'] and source['bytes'] == target['bytes'] and
                source['attributes'] == target['attributes'] == 32 and source['mtime_ns'] == target['mtime_ns'],
                'Shared support changed bytes, attrs, mtime, or file identity')
        require(source_key in planned_support and source['file_identity'] == planned_support[source_key]['file_identity'] and
                source['mtime_ns'] == planned_support[source_key]['mtime_ns'] and
                source['link_count'] == planned_support[source_key]['links'] + 1,
                'Shared support donor differs from the reviewed input or has an unexpected link mutation')
        shared_verified.append(dict(source=source, target=target, method='hardlink',
                                    immutability_policy='READ_ONLY_USE_NO_ATTRIBUTE_CHANGE'))
    require(seen_support == set(expected_support), 'Shared support did not cover the exact eight retained inputs')
    overlay_meta = request.get('presentation_asset_overlay')
    require(type(overlay_meta) is dict and overlay_meta.get('schema') == 'zerosis.phase11.request_overlay.v1' and
            same_artifact(overlay_meta.get('base_result'), base_ref) and
            same_artifact(overlay_meta.get('base_snapshot'), result['base_snapshot']) and
            overlay_meta.get('packages') == result['packages'] and overlay_meta.get('shared_support') == shared_support and
            overlay_meta.get('launcher_prefix') == result.get('launcher_prefix') and
            overlay_meta.get('supersedes_base_runtime_image') is True and overlay_meta.get('native_attempts') == 0 and
            overlay_meta.get('default_or_registration_changed') is False and overlay_meta.get('new_game_only') is True,
            'Current overlay request provenance differs from the sealed final result')
    cleanup_ref = files.artifact(result['cleanup_receipt'])
    require(Path(cleanup_ref['path']) == STAGE / 'overlay/cleanup_result.json', 'Cleanup receipt escaped overlay evidence')
    cleanup = files.document(cleanup_ref)
    require(cleanup.get('status') == 'PASS_EXACT_FRESH_DUPLICATES_AND_OLD_TERRAIN_ALIAS_RETIRED' and
            cleanup.get('retired_files') == 9 and type(cleanup.get('files')) is list and len(cleanup['files']) == 9 and
            cleanup.get('source_attributes_modified') is False and cleanup.get('originals_or_old_runtimes_deleted') is False and
            cleanup.get('shared_link_payload_bytes_freed') == 0, 'Cleanup scope or preservation claims differ')
    retired_expected = {key(row['target']['path']): row['target'] for row in plan['shared_support']}
    retired_expected[key(plan['base_terrain']['path'])] = plan['base_terrain']
    seen_retired = set()
    released = 0
    for row in cleanup['files']:
        name = key(row.get('path', ''))
        require(name in retired_expected and name not in seen_retired, 'Cleanup has an unexpected or duplicate leaf')
        seen_retired.add(name)
        expected = retired_expected[name]
        require(all(row.get(field) == expected[field] for field in (
            'path', 'bytes', 'sha256', 'file_identity', 'mtime_ns', 'file_attributes', 'links')) and
            type(row.get('allocated_bytes')) is int and row['allocated_bytes'] >= 0,
            'Cleanup leaf is not its reviewed pre-removal identity')
        current_info = ordinary(Path(row['path']))
        require([current_info.st_dev, current_info.st_ino] != row['file_identity'],
                'Old duplicate file identity still occupies a retired target')
        if row['links'] == 1:
            released += row['allocated_bytes']
    require(seen_retired == set(retired_expected) and cleanup.get('released_unique_allocated_bytes') == released,
            'Cleanup reclaim accounting differs from exact single-link retired files')
    old_terrain_cache = absolute_path(archive['original_terrain_materialization']['cache'])
    require(old_terrain_cache.is_relative_to(PROJECT / 'Build/RuntimeInputCache'), 'Old terrain cache escaped its retained root')
    old_terrain = files.artifact(dict(path=str(old_terrain_cache), bytes=plan['base_terrain']['bytes'],
                                     sha256=plan['base_terrain']['sha256']), readonly=True)
    require(old_terrain['file_identity'] == plan['base_terrain']['file_identity'] and
            old_terrain['mtime_ns'] == plan['base_terrain']['mtime_ns'] and
            old_terrain['attributes'] == plan['base_terrain']['file_attributes'] and
            old_terrain['link_count'] == plan['base_terrain']['links'] - 1,
            'Removing the legacy terrain alias changed its retained cache payload or metadata')
    sidecar = profile['required_sidecar']
    require(sidecar['file_count'] == len(sidecar['files']) == 154 and sidecar['relative_root'] == 'UIFrontEnd',
            'Expected the latest exact UI154 sidecar contract')
    ui_members = set()
    for member in sidecar['files']:
        relative = relative_path(member['relative_path'])
        require(str(relative) not in ui_members, 'Duplicate UI sidecar member')
        ui_members.add(str(relative))
        source = files.artifact(member['frozen'], readonly=True)
        target = files.artifact(dict(path=str(runtime / 'UIFrontEnd' / relative),
            bytes=source['bytes'],sha256=source['sha256']),readonly=True)
        require(source['file_identity'] == target['file_identity'] and source['mtime_ns'] == target['mtime_ns'] and
                source['attributes'] == target['attributes'], 'UI sidecar differs from latest frozen bytes/identity')
    require(len(ui_members) == 154, 'Missing UI sidecar members')
    files.finish()
    return dict(schema='zerosis.phase11.independent_runtime_binding_verification.v1',
        status='PASS_INDEPENDENT_FILE_ONLY_LATEST_HOST_AND_SIX_ASSET_BINDINGS',
        integration_result=result_ref, run_id=run_id, runtime_directory=str(runtime),
        historical_base_result=base_ref, archived_originals_verified=3,
        base_request_revalidated_against_live_rewrite=False,
        runtime_input_count=24, backend_payloads=23, changed_from_base=sorted(changed),
        host_sha256=HOST_SHA, gamecore_sha256=SDK_SHA, packages=linked,
        asset_manifest=manifest_ref, launcher=launcher, launcher_review=launcher_review,
        ui_sidecar_files=154, supplemental_environment_bindings=5, package_count=6,
        shared_support=shared_verified, shared_support_files=8,
        cleanup_receipt=cleanup_ref, retired_exact_leaf_files=9,
        released_unique_allocated_bytes=released, shared_payload_bytes_reclaimed=0,
        validator=validator_ref, validator_review=validator_review,
        observed_files=len(files.paths), unique_contents_hashed=len(files.contents),
        unique_bytes_hashed=files.bytes_hashed, old_sources_verified_unchanged=len(audited_sources),
        actual_preparer_executed=False, launcher_or_validator_executed=False,
        execution_flag_scope='THIS_INDEPENDENT_VERIFIER_ONLY',
        host_gamecore_clr_hwnd_gpu_audio_or_game_executed=False, native_attempts=0,
        default_or_registration_changed=False, prior_bundle_save_migrated=False,
        new_game_only=True, real_game_or_visual_acceptance=False,
        superseded_base_result_preserved_as_historical=True)


def audit_native_boundary(event, args):
    if event.startswith(('subprocess.', 'ctypes.dlopen', 'ctypes.dlsym', 'socket.',
                         'urllib.', 'http.client.', 'os.exec', 'os.spawn')) or event in (
        'os.system', 'os.startfile', 'os.startfile/2', 'winreg.OpenKey', 'winreg.CreateKey',
        'winreg.SetValue', 'winreg.SetValueEx', 'sqlite3.connect', 'sqlite3.connect/handle'):
        raise VerificationError('Independent verifier forbids native, network, registry or database activity')


def main(argv=None):
    global CONTRACT_SHA, PLAN_SHA, FINAL_RESULT_SHA, EXPECTED_RUN_ID
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--result', type=Path, default=STAGE / 'overlay/result.json')
    parser.add_argument('--output', type=Path, default=HERE / 'contract_final_verification.json')
    parser.add_argument('--result-sha256', required=True)
    parser.add_argument('--plan-sha256', required=True)
    parser.add_argument('--preparer-sha256', required=True)
    parser.add_argument('--run-id', required=True)
    args = parser.parse_args(argv)
    for digest in (args.result_sha256,args.plan_sha256,args.preparer_sha256):
        require(SHA_PATTERN.fullmatch(digest), 'Explicit parent-sealed hash required')
    require(RUN_PATTERN.fullmatch(args.run_id), 'Exact fresh run ID required')
    FINAL_RESULT_SHA, PLAN_SHA, CONTRACT_SHA = args.result_sha256,args.plan_sha256,args.preparer_sha256
    EXPECTED_RUN_ID = args.run_id
    require(not sys.flags.optimize, 'Do not disable the verifier checks with Python optimization')
    sys.addaudithook(audit_native_boundary)
    output = args.output.absolute()
    require(output.parent == HERE and output.name.startswith('contract_') and output.suffix == '.json' and
            not os.path.lexists(output), 'Preserve existing evidence; output must be a new contract JSON')
    report = verify(args.result.absolute())
    report['verifier'] = dict(path=str(Path(__file__).absolute()),
                              sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    with output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    raw = output.read_bytes()
    print(json.dumps(dict(status=report['status'], path=str(output), bytes=len(raw),
                         sha256=hashlib.sha256(raw).hexdigest(), native_attempts=0)))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (VerificationError, OSError, ValueError, KeyError, TypeError) as error:
        print(json.dumps(dict(status='FAIL_INDEPENDENT_FILE_ONLY_RUNTIME_BINDING',
                              error=type(error).__name__ + ': ' + str(error), native_attempts=0)))
        raise SystemExit(1)
