"""Independent six-package/UI audit. Only owned JSON evidence is written."""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
import argparse
import ast
import hashlib
import importlib.util
import json
import os
import re
import struct
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).absolute().parent
PROJECT = ROOT.parents[3]
OLD = PROJECT / 'Build/InteractiveGameRuntime/20261115T134603Z_aa8853762399'
BINDING = PROJECT / 'evidence/world_terrain_original/phase10/compiled_asset_binding.json'
PROFILE = PROJECT / 'evidence/world_terrain_original/phase10/pair_preparation/20261116T114748Z_014dd63ad3bc/prepared_profile.json'
HOST = 'c3bb5ffc2e57630d28a8305f288b501352c03f0e1970b1dc5b321d6ba0683383'
SDK = '430f3122d0b555d6daae14aa7c011ef43ce8f978270477c8af596ca4b0493ab9'
NAMES = {'terrain': 'terrain-assets.bin', 'fog': 'WorldAssets/fog-assets.bin',
         'water': 'WorldAssets/water-assets.bin', 'lean': 'WorldAssets/water-lean-assets.bin',
         'lighting': 'WorldAssets/lighting-assets.bin', 'screen_light': 'WorldAssets/screen-light-assets.bin'}
EXPECTED = {
    'terrain': ('02104c582759bf0cefb58f97379699e45300eb2a9c6da6fdd3c65d1440cb84e8', 112874723, b'ZSTERR02', 2, 41),
    'fog': ('42ae12554e1514dd48a9a5df25f47b4280d22d180dff29d169c602334e879bcc', 8184971, b'ZSFOG001', 1, 9),
    'water': ('2ff227dae9d16398e038e8ea33624940a9581e0eb2d37c3891121fae22c25afc', 5180388, b'ZSWATER1', 1, 25),
    'lean': ('69c6780dbeb5f8605d8231cef944d0ec9392109b6ccc81a9d3b76ae83cfd0ef7', 3495363, b'ZSWLEAN1', 1, 1),
    'lighting': ('d0873d3915da23e45ee1b66187bb7e4174673a1e8cce1fea16b6151ff515e424', 730040, b'ZSLIGHT1', 1, 15),
    'screen_light': ('f02165b489bfe80557e1fd0246c0a2423f5494a28f4974d935120ea14528a0e0', 1398304, b'ZSSCRL01', 1, 1398256)}
ENV = {'fog': 'ZEROSIS_FOG_ASSETS', 'water': 'ZEROSIS_WATER_ASSETS',
       'lean': 'ZEROSIS_WATER_SURFACE_ASSETS', 'lighting': 'ZEROSIS_LIGHTING_ASSETS',
       'screen_light': 'ZEROSIS_SCREEN_LIGHT_ASSETS'}
MANAGED = {'Firaxis.Framework.dll', 'Firaxis.Framework.Granny.dll', 'Firaxis.Framework.FirePlace.dll'}
SUPPORT = ['interactive_ui_support/assets/prepared.json', 'interactive_ui_support/assets/inline_icons.json']
UTILITY = PROJECT / 'evidence/world_terrain_original/phase9/runtime_integration/assets/asset_input_review.py'
FONT_HELPER = UTILITY.with_name('asset_ui_font_review_v2.py')
UTILITY_SHA = '1302d6dc881a523202693eaff6aa6db8c0dbb1b053205e36ea0bff306edc761c'
FONT_HELPER_SHA = '407d3310d3a720496ebe8d5ec140694f0d646322c1e426d30f856dc49b8ae500'
DENIED = []


def load_module(path, name, expected):
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise ValueError('Pinned independent reader changed')
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


utility = load_module(UTILITY, 'asset_input_review', UTILITY_SHA)
font_helper = load_module(FONT_HELPER, 'phase9_pinned_font_reader', FONT_HELPER_SHA)
require, artifact, verify_ref, canonical, read = utility.require, utility.artifact, utility.verify_ref, utility.canonical, utility.read


def boundary(event, args):
    if event.startswith(('subprocess.', 'socket.', 'winreg.')) or event in ('os.system', 'os.startfile', 'ctypes.dlopen'):
        DENIED.append(event)
        raise PermissionError('Asset verifier cannot execute processes, native libraries, network or registry operations')
    if event == 'open':
        mode, flags = args[1], args[2]
        writing = isinstance(mode, str) and any(c in mode for c in 'wax+')
        writing |= isinstance(flags, int) and bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
        if writing:
            path = Path(os.fsdecode(args[0])).absolute()
            require(path.parent == ROOT and path.name.startswith('asset_') and path.suffix == '.json', 'Write escaped owned asset evidence')
    elif event in ('os.mkdir', 'os.remove', 'os.rmdir', 'os.chmod', 'os.utime', 'os.rename', 'os.replace', 'os.link', 'os.symlink'):
        DENIED.append(event)
        raise PermissionError('Asset verifier does not mutate runtime or original inputs')


def write_new(path, value):
    require(path.parent == ROOT and path.name.startswith('asset_') and not path.exists(), 'Evidence must be a fresh owned file')
    with path.open('x', encoding='utf8') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')
    return artifact(path)


def raw_header(path, role):
    expected, size, magic, version, count = EXPECTED[role]
    row = artifact(path, fresh=True)
    require(row['bytes'] == size and row['sha256'] == expected, 'Package exact pin differs: ' + role)
    with Path(path).open('rb') as stream:
        header = stream.read(16)
    require(header[:8] == magic and struct.unpack_from('<II', header, 8) == (version, count), 'Package header differs: ' + role)
    return row


def backend(root):
    lines = (root / 'bundle.manifest').read_text('ascii').splitlines()
    require(lines and lines[0] == 'ZEROSIS_HOST_BUNDLE_V4' and len(lines) == 24, 'Backend requires exactly23 payloads plus signature')
    result = {}
    for line in lines[1:]:
        name, digest = line.split('|')
        require(name not in result and Path(name).name == name and re.fullmatch('[0-9a-f]{64}', digest), 'Unsafe duplicate backend entry')
        result[name] = digest
    require(len(result) == 23 and 'screen-light-assets.bin' not in result, 'Supplemental package changed the native allowlist')
    return result


def same_content(actual, before, identity=True):
    keys = ('bytes', 'sha256', 'mtime_ns', 'file_attributes') + (('file_identity',) if identity else ())
    require(all(actual[k] == before[k] for k in keys), 'Content or protected metadata changed: ' + actual['path'])


def input_review():
    binding, profile = read(BINDING), read(PROFILE)
    require(binding['host']['sha256'] == profile['executable_sha256'] == HOST, 'Latest Host binding differs')
    require(profile['build_id'] == '20261116T114748Z_014dd63ad3bc' and profile['prepared_profile_only'] and not profile['globally_registered'] and not profile['native_execution'], 'Profile not isolated and file-only')
    require(set(binding['packages']) == set(NAMES), 'Compiled role set differs')
    require(binding['new_package_bytes'] == 1398304 and binding['original_five_packages_copied'] == 0, 'Unexpected asset copy contract')
    host = verify_ref(binding['host'])
    packages = []
    for role in NAMES:
        row = raw_header(binding['packages'][role]['path'], role)
        same_content(row, binding['packages'][role])
        require(row['file_attributes'] == 32, 'Source package attributes changed')
        packages.append(dict(role=role, source=row, relative_path=NAMES[role]))
    sidecar = profile['required_sidecar']
    require(sidecar['file_count'] == len(sidecar['files']) == 154 and profile['catalog']['entry_count'] == 74, 'UI154/catalog74 differs')
    ui = []
    for row in sidecar['files']:
        source, frozen = verify_ref(row['source']), verify_ref(row['frozen'])
        same_content(source, frozen)
        require(source['file_attributes'] & 1, 'UI immutable flag missing')
        ui.append(dict(relative_path=row['relative_path'], source=source, frozen=frozen))
    support_names = SUPPORT + ['interactive_ui_support/tools/' + p.name for p in sorted((OLD / 'interactive_ui_support/tools').glob('*.py'))]
    require(len(support_names) == 8, 'Support inventory is not six modules plus two assets')
    support = [dict(relative_path=name, source=artifact(OLD / name, fresh=True)) for name in support_names]
    require(all(row['source']['file_attributes'] == 32 for row in support), 'Shared support attributes changed')
    oldrequest = read(PROJECT / 'evidence/interactive_game' / OLD.name / 'request.json')
    unit = oldrequest['unit_assets']
    unitref = verify_ref(unit['package'])
    require(verify_ref(unit['source_package'])['sha256'] == unitref['sha256'], 'Unit source differs')
    require(verify_ref(unit['manifest'])['sha256'] == verify_ref(unit['source_manifest'])['sha256'], 'Unit manifest differs')
    with Path(unitref['path']).open('rb') as stream:
        require(stream.read(12) == b'ZSUNIT02\2\0\0\0', 'Unit V2 lost')
    animation = unit['animation_runtime']
    require(animation['format_version'] == 2 and len(animation['dependencies']) == len(animation['embedded_inputs']) == 5, 'Animation input contract differs')
    animation_inputs = [verify_ref(row) for row in animation['dependencies'] + animation['embedded_inputs']]
    font = font_helper.run(OLD)
    return dict(schema='zerosis.phase11.asset_input_review.v1', status='PASS_LATEST_SIX_PACK_UI154_INPUTS_FILE_ONLY',
        utc=datetime.now(timezone.utc).isoformat(), binding=artifact(BINDING), current_profile=artifact(PROFILE), host=host,
        previous_runtime=str(OLD), packages=packages, ui=ui, support=support, backend=backend(OLD),
        unit=dict(package=unitref, animation_inputs=animation_inputs), font=font,
        verifier_source=artifact(__file__), pinned_reader=artifact(UTILITY), pinned_font_reader=artifact(FONT_HELPER),
        new_asset_payload_copies=0, originals_modified=False, native_host_sdk_clr_hwnd_gpu_audio_or_game_executed=False)


def pe_metadata(path, managed, dll):
    row = artifact(path)
    with Path(path).open('rb') as stream:
        dos = stream.read(64)
        require(dos[:2] == b'MZ', 'Invalid DOS signature')
        offset = struct.unpack_from('<I', dos, 60)[0]
        require(64 <= offset <= min(row['bytes'] - 264, 1024 * 1024), 'Invalid PE offset')
        stream.seek(offset)
        head = stream.read(24)
        require(head[:4] == b'PE\0\0', 'Invalid PE signature')
        machine, sections, _, _, _, optional_size, flags = struct.unpack_from('<HHIIIHH', head, 4)
        optional = stream.read(optional_size)
        magic = struct.unpack_from('<H', optional)[0]
        require(bool(flags & 0x2000) == dll and 0 < sections <= 96, 'PE type differs')
        if managed:
            require(machine == 0x14c and magic == 0x10b and optional_size >= 224, 'Managed wrapper must remain PE32 AnyCPU')
            rva, size = struct.unpack_from('<II', optional, 96 + 14 * 8)
            require(rva and size >= 20, 'Managed CLR metadata missing')
            table = stream.read(sections * 40)
            found = None
            for i in range(sections):
                _, va, length, start = struct.unpack_from('<IIII', table, 40 * i + 8)
                if va <= rva and rva - va + 20 <= length:
                    stream.seek(start + rva - va)
                    found = struct.unpack_from('<I', stream.read(20), 16)[0]
                    break
            require(found is not None and found & 1 and not found & (2 | 0x10 | 0x20000), 'Managed wrapper not IL-only AnyCPU')
        else:
            require(machine == 0x8664 and magic == 0x20b and optional_size >= 240, 'Native input not AMD64 PE32+')
    return dict(name=Path(path).name, sha256=row['sha256'], machine=hex(machine), optional_magic=hex(magic),
                managed_metadata_only=managed, loaded_or_executed=False)


def validator_ast(path):
    tree = ast.parse(Path(path).read_text('utf8'))
    denied_imports = {'subprocess', 'ctypes', 'winreg', 'socket', 'http', 'urllib', 'requests', 'multiprocessing', 'threading', 'importlib'}
    denied_calls = {'Popen', 'system', 'startfile', 'LoadLibrary', 'WinDLL', 'CDLL', 'CreateProcess',
                    'write_text', 'write_bytes', 'mkdir', 'unlink', 'rmdir', 'chmod', 'rename', 'replace', 'link', 'symlink'}
    pins = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or '']
            require(not any(n.split('.')[0] in denied_imports for n in names), 'Verifier imports executable capability')
        if isinstance(node, ast.Call):
            require(not (isinstance(node.func, ast.Attribute) and node.func.attr in denied_calls), 'Verifier mutates or executes')
            require(not (isinstance(node.func, ast.Name) and node.func.id in {'eval', 'exec', 'compile', '__import__'}), 'Verifier dynamically executes')
            if isinstance(node.func, ast.Attribute) and node.func.attr == 'open':
                modes = [node.args[0]] if node.args else []
                modes += [k.value for k in node.keywords if k.arg == 'mode']
                require(all(not isinstance(n, ast.Constant) or not isinstance(n.value, str) or not any(c in n.value for c in 'wax+') for n in modes), 'Verifier opens for writing')
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and node.targets[0].id in {'EXPECTED', 'HOST', 'SDK'}:
            pins[node.targets[0].id] = ast.literal_eval(node.value)
    require(pins == {'HOST': HOST, 'SDK': SDK, 'EXPECTED': {role: (NAMES[role], EXPECTED[role][0], EXPECTED[role][2]) for role in NAMES}}, 'Validator has stale six-package pins')
    return dict(ast_parsed=True, root_validator_imported=False, root_validator_executed=False, pinned_roles=6)


def final_review(run_id):
    require(re.fullmatch(r'\d{8}T\d{6}Z_[0-9a-f]{12}', run_id), 'Invalid run ID')
    baseline = read(ROOT / 'asset_input_review.json')
    root = canonical(PROJECT / 'Build/InteractiveGameRuntime' / run_id)
    require(root != OLD, 'New runtime must be independent from prior baseline')
    manifestpath = root / 'WorldAssets/assets.manifest.json'
    manifest = read(manifestpath)
    require(manifest['schema'] == 'zerosis.world_assets.runtime_binding.v1' and Path(manifest['runtime_directory']) == root, 'Manifest identity differs')
    require(set(manifest['packages']) == set(NAMES), 'Runtime is missing exact six-package role set')
    compiled = read(BINDING)
    packages = []
    for role in NAMES:
        before = next(row['source'] for row in baseline['packages'] if row['role'] == role)
        source = raw_header(before['path'], role)
        same_content(source, before)
        require(source['file_attributes'] == 32, 'Source attribute mutation')
        entry = manifest['packages'][role]
        require(entry == dict(relative_path=NAMES[role], bytes=EXPECTED[role][1], sha256=EXPECTED[role][0]), 'Manifest role differs')
        target = raw_header(root / NAMES[role], role)
        same_content(target, source)
        require(target['file_identity'] == source['file_identity'] and target['links'] >= 2, 'Package is not original-source hardlink')
        packages.append(dict(role=role, source=source, target=target, new_payload_copies=0))
    host, sdk = artifact(root / 'ZeroSisHost_x64.exe', fresh=True), artifact(root / 'CvGameCoreDLL_Expansion2_x64.dll', fresh=True)
    require(host['sha256'] == HOST and sdk['sha256'] == SDK, 'Latest Host/SDK pair differs')
    for key, actual in (('host', host), ('gamecore', sdk)):
        require(verify_ref(manifest[key])['path'] == actual['path'], 'Manifest native input escaped runtime')
    core = backend(root)
    expectedcore = dict(baseline['backend']);expectedcore['ZeroSisHost_x64.exe'] = HOST
    require(core == expectedcore, 'Native23 allowlist contents differ')
    binaries = []
    for name, digest in core.items():
        row = artifact(root / name, fresh=True)
        require(row['sha256'] == digest, 'Backend bytes differ: ' + name)
        if name.endswith(('.exe', '.dll')):
            binaries.append(pe_metadata(root / name, name in MANAGED, name.endswith('.dll')))
        if name in {'rules.db', 'localization.db'}:
            old = artifact(OLD / name)
            require(row['file_identity'] != old['file_identity'] and row['links'] == 1, 'Database seed is shared')
    profile = read(PROFILE)
    expectedpaths = set()
    for row in profile['required_sidecar']['files']:
        relative = row['relative_path'];expectedpaths.add(relative)
        require('..' not in Path(relative).parts and ':' not in relative, 'Unsafe sidecar path')
        target, frozen = artifact(root / 'UIFrontEnd' / relative), verify_ref(row['frozen'])
        same_content(target, frozen)
        require(target['file_identity'] == frozen['file_identity'] and target['file_attributes'] & 1, 'UI immutable alias differs')
    require({p.relative_to(root / 'UIFrontEnd').as_posix() for p in (root / 'UIFrontEnd').rglob('*') if p.is_file()} == expectedpaths and len(expectedpaths) == 154, 'UI154 exact path set differs')
    support_manifest = read(root / 'interactive_ui_support/support_manifest.json')
    require(len(support_manifest['tools']) == 6, 'Expected six support modules')
    support = []
    for row in baseline['support']:
        source, target = artifact(row['source']['path'], fresh=True), artifact(root / row['relative_path'], fresh=True)
        same_content(source, row['source']);same_content(target, source)
        require(target['file_identity'] == source['file_identity'] and target['file_attributes'] == 32, 'Support not shared without attribute changes')
        support.append(dict(relative_path=row['relative_path'], source=source, target=target))
    for name, row in support_manifest['tools'].items():
        require(Path(row['path']) == root / 'interactive_ui_support/tools' / name and verify_ref(row)['sha256'] == artifact(root / 'interactive_ui_support/tools' / name)['sha256'], 'Support tool path escaped runtime')
    for key, name in (('inline_icons', 'inline_icons.json'), ('asset_preparation_provenance', 'prepared.json')):
        require(Path(support_manifest[key]['path']) == root / 'interactive_ui_support/assets' / name, 'Support metadata points outside runtime')
        verify_ref(support_manifest[key])
    driver = (root / 'interactive_ui_support/tools/interactive_ui_driver.py').read_text('utf8')
    require('env = dict(os.environ)' in driver and 'cwd=cwd, env=env' in driver, 'UI driver does not inherit explicit local asset environment')
    font = font_helper.run(root)
    require(font['font_profile_id'] == baseline['font']['font_profile_id'], 'Owned font profile changed')
    unit = artifact(root / 'unit-assets.bin')
    require(unit['sha256'] == baseline['unit']['package']['sha256'], 'Unit V2 payload differs')
    validator = root / 'WorldAssets/verify_assets.py'
    require(manifest['validator']['relative_path'] == 'WorldAssets/verify_assets.py' and artifact(validator)['sha256'] == manifest['validator']['sha256'], 'Validator binding differs')
    pure = validator_ast(validator)
    play = (root / 'Play.ps1').read_text('utf8');normalized = play.replace('\\', '/')
    verifierpos = normalized.find('WorldAssets/verify_assets.py');driverpos = normalized.find('interactive_ui_driver.py')
    require(0 <= verifierpos < driverpos and '$LASTEXITCODE' in normalized[verifierpos:driverpos] and 'throw' in normalized[verifierpos:driverpos], 'Validator is not fail-closed before native/UI driver')
    for role, name in ENV.items():
        lines = re.findall(r'^\$env:' + name + r'\s*=([^\n]+)', normalized, re.M)
        require(len(lines) == 1 and '$PSScriptRoot' in lines[0] and 'Join-Path' in lines[0] and NAMES[role] in lines[0], 'Asset ENV not exact bundle-local role: ' + name)
    require(not re.search(r'SetEnvironmentVariable\([^\n]*(?:Machine|User)', play), 'Persistent environment mutation')
    require(not (root / 'sessions').exists() and not list(root.glob('interactive-ui-*.json')) and not list(root.glob('menu-options.*')), 'Unexpected native session output')
    requestpath = PROJECT / 'evidence/interactive_game' / run_id / 'request.json'
    request = read(requestpath)
    require(request['run_id'] == run_id and Path(request['cwd']) == root and request['smoke'] is False and request['resume_from'] is None, 'Request is not fresh private new-game state')
    require(len(request['runtime_inputs']) == 24, 'Backend input inventory changed')
    require(verify_ref(request['presentation_asset_binding'])['sha256'] == artifact(manifestpath)['sha256'], 'Request asset binding differs')
    for row in request['runtime_inputs']:
        verify_ref(row)
    require(not DENIED, 'Unexpected forbidden operation')
    return dict(schema='zerosis.phase11.asset_final_review.v1', status='PASS_LATEST_SIX_PACK_UI154_RUNTIME_ASSETS_FILE_ONLY',
        utc=datetime.now(timezone.utc).isoformat(), run_id=run_id, runtime_directory=str(root),
        packages=packages, package_payload_copies=0, package_source_attributes_modified=False,
        host=host, gamecore=sdk, backend_payloads=23, backend_inputs=24, pe_metadata=binaries,
        ui_sidecar_files=154, original_ui_inputs=74, shared_support=support, owned_font_inputs=15,
        font_review=font, installed_font_equality_required=False, validator_ast=pure, local_environment=ENV,
        request=artifact(requestpath), manifest=artifact(manifestpath), compiled_binding=artifact(BINDING),
        verifier_source=artifact(__file__), input_review=artifact(ROOT / 'asset_input_review.json'),
        guard_denials=DENIED, native_host_sdk_clr_hwnd_gpu_audio_or_game_attempts=0,
        actual_gameplay_or_screen_verified=False, current_or_original_or_runtime_files_modified=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('input', 'final'))
    parser.add_argument('--run-id')
    parser.add_argument('--output-name')
    args = parser.parse_args()
    output = ROOT / (args.output_name or ('asset_input_review.json' if args.action == 'input' else 'asset_final_review.json'))
    require(not output.exists() and output.parent == ROOT and output.name.startswith('asset_') and output.suffix == '.json', 'Use fresh owned evidence name')
    sys.addaudithook(boundary)
    result = input_review() if args.action == 'input' else final_review(args.run_id)
    record = write_new(output, result)
    print(json.dumps(dict(status=result['status'], packages=6, ui=154, output=record)))


if __name__ == '__main__':
    main()
