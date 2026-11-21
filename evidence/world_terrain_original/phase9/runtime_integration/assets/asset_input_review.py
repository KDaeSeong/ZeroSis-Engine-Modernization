"""Independent, read-only input review for the phase9 isolated runtime.

Only a new report inside this evidence directory is written. Native modules,
launchers, UI, renderers, audio and the game are never loaded or executed.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import sys
from datetime import datetime, timezone

OUT = Path(__file__).absolute().parent
PROJECT = OUT.parents[4]
OLD = PROJECT / 'Build/InteractiveGameRuntime/20261115T101941Z_99b3c393ee9a'
BINDING = PROJECT / 'evidence/world_terrain_original/phase8/compiled_asset_binding.json'
PROFILE = PROJECT / 'evidence/world_terrain_original/phase8/pair_preparation/20261115T121456Z_dbb01a1f4f50/prepared_profile.json'
HOST = '8e67b0fc6c90c354c6341dfcc39f87b5ae030dd564da9bb1210ad602ba3a70e5'
SDK = '430f3122d0b555d6daae14aa7c011ef43ce8f978270477c8af596ca4b0493ab9'
NAMES = {'terrain':'terrain-assets.bin', 'fog':'WorldAssets/fog-assets.bin',
         'water':'WorldAssets/water-assets.bin', 'lean':'WorldAssets/water-lean-assets.bin',
         'lighting':'WorldAssets/lighting-assets.bin'}
MAGIC = {'terrain':(b'ZSTERR02',2,41), 'fog':(b'ZSFOG001',1,9),
         'water':(b'ZSWATER1',1,25), 'lean':(b'ZSWLEAN1',1,1), 'lighting':(b'ZSLIGHT1',1,15)}
HASHES = {'terrain':'02104c582759bf0cefb58f97379699e45300eb2a9c6da6fdd3c65d1440cb84e8',
          'fog':'42ae12554e1514dd48a9a5df25f47b4280d22d180dff29d169c602334e879bcc',
          'water':'2ff227dae9d16398e038e8ea33624940a9581e0eb2d37c3891121fae22c25afc',
          'lean':'69c6780dbeb5f8605d8231cef944d0ec9392109b6ccc81a9d3b76ae83cfd0ef7',
          'lighting':'d0873d3915da23e45ee1b66187bb7e4174673a1e8cce1fea16b6151ff515e424'}
CACHE = {}
DENIED = []


def require(value, message):
    if not value:
        raise ValueError(message)


def boundary(event, args):
    if event.startswith(('subprocess.', 'socket.', 'winreg.')) or event in ('os.system', 'os.startfile', 'ctypes.dlopen'):
        DENIED.append(event)
        raise PermissionError('Native/process/network/registry calls are forbidden')
    if event == 'open':
        mode, flags = args[1], args[2]
        writing = isinstance(mode, str) and any(c in mode for c in 'wax+')
        writing |= isinstance(flags, int) and bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
        if writing:
            path = Path(os.fsdecode(args[0])).absolute()
            require(path.parent == OUT and path.name == 'asset_input_review.json', 'Write escaped exact evidence output')
    elif event in ('os.mkdir', 'os.remove', 'os.rmdir', 'os.chmod', 'os.utime', 'os.rename', 'os.replace', 'os.link', 'os.symlink'):
        DENIED.append(event)
        raise PermissionError('Input review does not mutate files or directories')


def canonical(path):
    path = Path(path).absolute()
    require('..' not in path.parts, 'Noncanonical input')
    for item in (path, *path.parents):
        s = item.lstat()
        require(not stat.S_ISLNK(s.st_mode) and not getattr(s, 'st_file_attributes', 0) & 0x400, 'Reparse input: ' + str(item))
    require(path.resolve() == path, 'Resolved input differs')
    return path


def artifact(path, fresh=False):
    path = canonical(path)
    before = path.stat()
    require(stat.S_ISREG(before.st_mode), 'Not an ordinary file: ' + str(path))
    key = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, getattr(before, 'st_file_attributes', 0))
    if fresh or key not in CACHE:
        with path.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        CACHE[key] = digest
    after = path.stat()
    require(key == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, getattr(after, 'st_file_attributes', 0)), 'Input changed during read')
    return dict(path=str(path), bytes=before.st_size, sha256=CACHE[key], file_identity=[before.st_dev,before.st_ino],
                mtime_ns=before.st_mtime_ns, file_attributes=getattr(before,'st_file_attributes',0), links=after.st_nlink)


def verify_ref(row):
    path = row.get('path', row.get('original_path'))
    actual = artifact(path)
    for key in ('bytes','sha256','file_identity','mtime_ns','file_attributes'):
        if key in row:
            require(actual[key] == row[key], 'Reference mismatch ' + key + ': ' + str(path))
    return actual


def read(path):
    require(Path(path).stat().st_size <= 8*1024*1024, 'JSON size bound')
    return json.loads(Path(path).read_text('utf8'))


def run():
    compiled, profile = read(BINDING), read(PROFILE)
    require(compiled['host']['sha256'] == HOST and profile['executable_sha256'] == HOST, 'Latest Host pin differs')
    require(profile['build_id'] == '20261115T121456Z_dbb01a1f4f50' and profile['prepared_profile_only'] and not profile['globally_registered'], 'Latest profile scope differs')
    require(set(compiled['packages']) == set(NAMES), 'Compiled five package contract differs')
    require(compiled['new_asset_packages'] == compiled['asset_payload_copies'] == 0 and not compiled['native_launch_allowed'], 'Compiled binding scope differs')
    host = verify_ref(compiled['host'])
    sealed_sources = [dict(name=name, artifact=verify_ref(row)) for name,row in compiled['compiled_sources'].items()]
    oldrequest = read(PROJECT / 'evidence/interactive_game' / OLD.name / 'request.json')
    oldmanifest = read(OLD / 'WorldAssets/assets.manifest.json')
    require(set(oldmanifest['packages']) == set(NAMES), 'Retained runtime asset roles differ')
    packages = []
    for role,relative in NAMES.items():
        source = artifact(compiled['packages'][role]['path'], fresh=True)
        verify_ref(compiled['packages'][role])
        alias = artifact(OLD / relative, fresh=True)
        require(source['sha256'] == alias['sha256'] == HASHES[role], 'Package SHA differs: ' + role)
        require(all(source[k] == alias[k] for k in ('bytes','file_identity','mtime_ns','file_attributes')), 'Retained package alias differs: ' + role)
        require(source['file_attributes'] == 32 and source['links'] >= 2, 'Original package attributes or link contract differs')
        with Path(source['path']).open('rb') as stream:
            header = stream.read(24)
        magic,version,count = MAGIC[role]
        require(header[:8] == magic and struct.unpack_from('<II',header,8) == (version,count), 'Package format/count differs: ' + role)
        manifestpath = Path(source['path']).with_name(Path(source['path']).stem + '.manifest.json')
        manifest = read(manifestpath)
        if role == 'terrain':
            require(manifest['format'] == 'ZEROSIS_CIV5_ORIGINAL_TERRAIN_PACKAGE_V2', 'Terrain manifest format differs')
            require(manifest['package']['sha256'] == source['sha256'] and manifest['package']['row_count'] == count, 'Terrain manifest package differs')
        else:
            require(manifest['sha256'] == source['sha256'] and manifest['bytes'] == source['bytes'] and manifest['package']['asset_count'] == count, 'Manifest package differs: ' + role)
        entry = oldmanifest['packages'][role]
        require(entry == dict(relative_path=relative,bytes=source['bytes'],sha256=source['sha256']), 'Retained manifest role differs')
        packages.append(dict(role=role,artifact=source,retained_runtime_alias=alias,source_manifest=artifact(manifestpath),
                             relative_path=relative,magic=magic.decode(),version=version,record_count=count,
                             reuse='DIRECT_HARDLINK_READ_ONLY_USE_NO_ATTRIBUTE_CHANGE'))
    sidecar = profile['required_sidecar']
    require(sidecar['file_count'] == len(sidecar['files']) == 154 and profile['catalog']['entry_count'] == 74, 'UI contract counts differ')
    expectedpaths = set()
    ui_bytes = 0
    for row in sidecar['files']:
        relative = row['relative_path']
        require(relative not in expectedpaths and '..' not in Path(relative).parts and ':' not in relative, 'Unsafe or duplicate UI path')
        expectedpaths.add(relative)
        source, frozen = verify_ref(row['source']), verify_ref(row['frozen'])
        target = artifact(OLD / 'UIFrontEnd' / relative)
        require(all(source[k] == frozen[k] == target[k] for k in ('bytes','sha256','file_identity','mtime_ns','file_attributes')), 'UI source/frozen/retained mismatch: ' + relative)
        require(target['file_attributes'] & 1, 'UI immutable input lost read-only attribute')
        ui_bytes += target['bytes']
    actualpaths = {p.relative_to(OLD/'UIFrontEnd').as_posix() for p in (OLD/'UIFrontEnd').rglob('*') if p.is_file()}
    require(actualpaths == expectedpaths, 'Retained UI files differ from exact profile inventory')
    support = oldrequest['interactive_ui_support_inventory']
    require(len(support['tools']) == 6, 'Six support modules required')
    tools = []
    for name,row in support['tools'].items():
        current, source = verify_ref(row['frozen']), verify_ref(row['source'])
        require(current['sha256'] == source['sha256'], 'Support source differs: ' + name)
        tools.append(dict(name=name,runtime=current,source=source))
    assets = []
    for key,name in [('inline_icons','inline_icons.json'),('asset_preparation_provenance','prepared.json')]:
        current, source = verify_ref(support[key]['frozen']), verify_ref(support[key]['source'])
        require(current['sha256'] == source['sha256'], 'Support asset source differs: ' + name)
        assets.append(dict(name=name,artifact=current,source=source))
    verify_ref(support['frozen_support_manifest'])
    backend = (OLD/'bundle.manifest').read_text('ascii').splitlines()
    require(backend[0] == 'ZEROSIS_HOST_BUNDLE_V4' and len(backend) == 24, 'V4 backend allowlist differs')
    backend_files = []
    for line in backend[1:]:
        name,digest = line.split('|')
        row = artifact(OLD/name)
        require(row['sha256'] == digest, 'Retained backend mismatch: ' + name)
        backend_files.append(dict(name=name,artifact=row))
    require(len({r['name'] for r in backend_files}) == 23, 'Duplicate backend payload')
    require(next(r['artifact']['sha256'] for r in backend_files if r['name']=='CvGameCoreDLL_Expansion2_x64.dll') == SDK, 'SDK pin differs')
    unit = oldrequest['unit_assets']
    unit_package = verify_ref(unit['package'])
    require(verify_ref(unit['source_package'])['sha256'] == unit_package['sha256'], 'Unit source package differs')
    require(verify_ref(unit['manifest'])['sha256'] == verify_ref(unit['source_manifest'])['sha256'], 'Unit manifest differs')
    with Path(unit_package['path']).open('rb') as stream:
        require(stream.read(12) == b'ZSUNIT02\2\0\0\0', 'Unit V2 format differs')
    animation = unit['animation_runtime']
    require(animation['format_version'] == 2 and len(animation['dependencies']) == len(animation['embedded_inputs']) == 5, 'Animation contract count differs')
    animation_inputs = [verify_ref(row) for row in animation['dependencies'] + animation['embedded_inputs']]
    animation_config = verify_ref(animation['config'])
    animation_report = verify_ref(animation['bridge_report'])
    animation_preparer = verify_ref(animation['preparer'])
    require(not DENIED, 'Unexpected forbidden operation')
    return dict(schema='zerosis.phase9.asset_input_review.v1',status='PASS_PHASE8_FIVE_PACK_UI154_UNIT_ANIMATION_REUSE_PLAN_FILE_ONLY',
                utc=datetime.now(timezone.utc).isoformat(),scope='NoNative0',binding=artifact(BINDING),current_profile=artifact(PROFILE),
                host=host,compiled_source_seals=sealed_sources,packages=packages,backend_files=backend_files,
                frozen_support=dict(tools=tools,assets=assets),ui=dict(file_count=154,embedded_count=74,logical_bytes=ui_bytes,
                source_frozen_retained_sha_identity_attributes_match=True,profile_paths_exact=True),
                unit=dict(package=unit_package,animation_dependencies_and_embedded_inputs=animation_inputs,config=animation_config,
                bridge_report=animation_report,preparer=animation_preparer),
                plan=dict(five_direct_existing_source_hardlinks=True,new_asset_payload_copies=0,attribute_mutations=0,
                keep_backend_23_plus_manifest=True,share_support_six_modules_two_assets=True,keep_rules_localization_private=True,
                new_validator_host_pin=HOST,sdk_pin=SDK,phase7_validator_reusable_unchanged=False),
                native_host_gamecore_clr_hwnd_gpu_audio_or_game_attempts=0,guard_denials=DENIED,
                production_source_edits=0,original_mods_settings_saves_default_registration_changed=False,
                verifier_source=artifact(__file__))


def main():
    output = OUT / 'asset_input_review.json'
    require(not output.exists(), 'Do not overwrite prior evidence')
    sys.addaudithook(boundary)
    proof = run()
    with output.open('x',encoding='utf8') as stream:
        json.dump(proof,stream,indent=2)
        stream.write('\n')
    print(json.dumps(dict(status=proof['status'],scope=proof['scope'],packages=5,ui=154,support=8,animation_inputs=10,
                          package_bytes=sum(r['artifact']['bytes'] for r in proof['packages']),output=artifact(output))))


if __name__ == '__main__':
    main()
