"""Create one fresh preparation scope from reviewed, existing project artifacts.

Only the B11 build JSON is recursively interpreted. Historical source-seal
documents are preserved as files, never expanded into obsolete live sources.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

sys.dont_write_bytecode = True
SELF = Path(__file__).absolute()
STAGE = SELF.parent
PROJECT = STAGE.parents[2]
OWNED = PROJECT / 'evidence/goody_hut/owned_fonts'
OUTPUT = STAGE / 'scope.json'
BUILD_ID = '20261018T024443Z_23a2e7fdb8ea'
R10 = PROJECT / 'evidence/interactive_game/20261017T233110Z_b4d9e31f65f9/request.json'
PROGRESS = PROJECT / 'evidence/save_menu/20261013_original_screen/current_progress.json'
BASE = PROJECT / 'evidence/goody_hut/source/frozen_candidate_preservation.json'
HELPER = PROJECT / 'evidence/concurrency/runtime_configuration/prepare_candidate.py'
LEGACY = PROJECT / 'evidence/save_overwrite/linked_candidate/prepare_candidate.py'
PACKAGE = 'fbb3b9ec4b43242cbee022b9cdf712f37ccbdf6290015ee2ee27b6547a570573'
TOOLS = ('interactive_ui_driver.py', 'render_ui_popup.py', 'ui_pixel_scene.py',
         'ui_bitmap_fonts.py', 'civ5_ui_assets.py', 'found_value_runtime_options.py', 'run_interactive_game.py')
PINS = {
    BASE: 'a0fc4ec83b4acd80d9a1b98089e088ac18f2078b5ba8b7d8d49b344f8910ab5b',
    PROGRESS: '63dd778f0bef17c59e5da857f43386f86ef729bc2f45760bde746d3d665be89b',
    R10: '97956933c47af867aa46fe57a51b3c65e8ea4813b7959338219ddba66ae129ae',
    HELPER: 'fc2d186c5d9ace093ff083aea1c1b3d08bb2a42ca47f51de3961ebd850728999',
    LEGACY: 'f28dbf303b8e5ae653fff70a923c86c62a77e0fbd64c92633eefc619d6039d2f',
    STAGE / 'prepare_runtime.py': '5eeec37c747631370f1961e66dabc6bd8c2a8b8aa1fc2c7bddd14bb73db55821',
    OWNED / 'attestation_retry.json': '3781696d52d15ba0104d64d8ff28dd9c2d2da2fd86adc3e7e39b3c5c0e4f9bfb',
    OWNED / 'build_objects_retired.json': '8b7ffe059e69a4868c830348af1ae099fb245fc90607e4efef505af5e0d2cdf4',
    OWNED / 'capture_result.json': 'b3a682a88d76eeb809202107b9e6c7765f0293b02d43f216bc03af626da57bc5',
    OWNED / 'source_conformance.json': '0ec30d9e1bb69a3d6ef10a0df4ec40e581c524200f695f053116aa09514a8f57',
    OWNED / 'build_run.json': 'bc46920d49b3fa8b2736d8af25f907beea4c9ae53df64ea5d3e35a4f9d9f4a98',
    OWNED / 'linked_conformance.json': '9bab61ce715cfcfdb47a25b414abd4e56766fe96aaaa8f9605f323ba66829bca',
    STAGE / 'frontend_tests_retry_03.json': 'aa7e551e90659fa3a7c2013daa93e0da9c9bc59472b32b8d6d8dfa6fd6b8ced3',
    STAGE / 'font_drift_review.json': 'cdf503ab1ce14e71596bfb2da20c2ce0d74196fd6c101ec46de4dc5d64f86375',
    PROJECT / 'Tests/ui_pixel_scene.py': '1f5c95e7b262b11d72400cfdcc9e146b09a860e746c36643acd418092975a22f',
}
MSVC = r'C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Tools\MSVC\14.44.35207\bin\Hostx64\x64'
EXTERNAL_TOOLCHAIN = {
    'compiler': dict(path=MSVC + r'\cl.exe', sha256='8a547dfca2d7df1b6be1e2d212132c1b3b5a661caf5b2ecce481e21b3c1860a6'),
    'dumpbin': dict(path=MSVC + r'\dumpbin.exe', sha256='9144a2fdba48bc27e6bfcd5eece6f925488758a5c25553b6de7567df794f5f5a'),
    'linker': dict(path=MSVC + r'\link.exe', sha256='4408c812a3f5e68cba935b8550a90cfc932ec7242a9c39efcb5c0945a6006c9a'),
}


def require(value, message):
    if not value:
        raise RuntimeError(message)


def key(path):
    return os.path.normcase(os.path.abspath(path))


def project_path(value):
    path = Path(value)
    path = path if path.is_absolute() else PROJECT / path
    require(path.is_absolute() and str(path) == os.path.abspath(path) and
            key(path).startswith(key(PROJECT) + os.sep), 'Artifact escaped its canonical project path')
    return path


def ordinary(path):
    path = project_path(path)
    for item in (path, *path.parents):
        require(not getattr(item.lstat(), 'st_file_attributes', 0) & 0x400, 'Reparse input or ancestor')
    before = path.stat()
    require(stat.S_ISREG(before.st_mode), 'Expected an ordinary artifact: ' + str(path))
    return path, before


def identity(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


def install_guard():
    published = False

    def audit(event, args):
        nonlocal published
        if event == 'open' and args and isinstance(args[0], (str, bytes, os.PathLike)):
            path = key(os.fsdecode(args[0])).removeprefix('\\\\?\\')
            require(path.startswith(key(PROJECT) + os.sep), 'Scope writer cannot read outside the project')
            mode, flags = args[1:3]
            writing = isinstance(mode, str) and any(c in mode for c in 'wax+') or (
                type(flags) is int and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
            if writing:
                require(path == key(OUTPUT) and not published and type(flags) is int and
                        flags & os.O_CREAT and flags & os.O_EXCL, 'Only one fresh scope JSON may be written')
                published = True
        if event.startswith(('subprocess.', 'os.exec', 'os.spawn', 'ctypes.', 'socket.', 'urllib.', 'http.client.')) or event in (
                'os.system', 'os.startfile', 'os.startfile/2', 'os.posix_spawn', 'os.posix_spawnp', 'os.kill', 'os.killpg',
                'os.fork', 'os.forkpty', 'os.listdir', 'os.scandir', 'os.chdir', 'os.remove', 'os.rmdir', 'os.mkdir',
                'os.rename', 'os.link', 'os.symlink', 'os.chmod', 'os.utime'):
            raise RuntimeError('Read-only scope writer forbids: ' + event)
    sys.addaudithook(audit)


def refs(value):
    if isinstance(value, dict):
        if isinstance(value.get('path'), str) and isinstance(value.get('sha256'), str):
            yield value
        for child in value.values():
            yield from refs(child)
    elif isinstance(value, list):
        for child in value:
            yield from refs(child)


def main():
    incident = json.loads((STAGE / 'system_freeze_hold.json').read_text(encoding='utf-8'))
    require(type(incident) is dict and incident.get('engine_build_preparation_and_large_io_stopped') is False,
            'Original Windows freeze hold is active; heavy engine work is forbidden')
    require(not sys.flags.optimize and len(sys.argv) == 1 and STAGE == PROJECT / 'evidence/goody_hut/runtime_fonts', 'Wrong unoptimized invocation')
    require(not os.path.lexists(OUTPUT), 'Scope already exists: do not overwrite or replay this writer')
    b'x'.decode('utf-8-sig')
    install_guard()
    recorded, cache, retired, excluded = {}, {}, {}, set()

    def artifact(path, expected=None):
        path, before = ordinary(path)
        mark = identity(before)
        if mark not in cache:
            with path.open('rb') as stream:
                cache[mark] = hashlib.file_digest(stream, 'sha256').hexdigest()
            require(identity(path.stat()) == mark, 'Artifact changed during hashing')
        row = dict(path=str(path), bytes=before.st_size, sha256=cache[mark])
        if expected is not None:
            require(expected['sha256'] == row['sha256'] and ('bytes' not in expected or expected['bytes'] == row['bytes']),
                    'Sealed artifact differs: ' + str(path))
        old = recorded.setdefault(key(path), row)
        require(old == row, 'Conflicting pins or changed artifact: ' + str(path))
        return row

    def add(row):
        require(isinstance(row, dict) and isinstance(row.get('path'), str) and
                re.fullmatch('[0-9a-f]{64}', row.get('sha256', '')), 'Malformed artifact reference')
        path = project_path(row['path'])
        if key(path) in retired:
            approved = retired[key(path)]
            require(path.suffix.lower() == '.obj' and not os.path.lexists(path) and row['sha256'] == approved['sha256'] and
                    ('bytes' not in row or row['bytes'] == approved['bytes']), 'Retired-object exception does not match its exact ledger')
            excluded.add(key(path))
            return None
        return artifact(path, row)

    def document(path):
        row = artifact(path)
        require(row['bytes'] <= 8 * 1024 * 1024, 'JSON artifact exceeds its bound')
        raw = Path(row['path']).read_bytes()
        require(hashlib.sha256(raw).hexdigest() == row['sha256'], 'JSON changed while reading')
        return json.loads(raw.decode('utf-8-sig'))

    for path, sha in PINS.items():
        artifact(path, dict(sha256=sha))
    artifact(SELF)
    pe = document(OWNED / 'attestation_retry.json')
    retirement = document(OWNED / 'build_objects_retired.json')
    require(pe['build_id'] == BUILD_ID and pe['status'] == 'PASS_READONLY_LINKED_PE_67_EXACT_PAYLOADS_NATIVE_PENDING' and
            pe['catalog']['entry_count'] == 67 and pe['inputs_unchanged'] is True and
            retirement['build_id'] == BUILD_ID and retirement['status'] == 'PASS_RETIRED_EXACT_TEN_OBJECTS' and
            retirement['removed_count'] == 10 and retirement['protected_unchanged'] is True and
            retirement['pe'] == artifact(OWNED / 'attestation_retry.json'), 'B11 PE/retirement approval differs')
    coff = pe['compilation']['actual_coff_objects']
    expected_coff = {key(row['object']['path']): row['object'] for row in coff}
    retired = {key(row['path']): row for row in retirement['objects_before']}
    require(len(coff) == len(expected_coff) == len(retired) == 10 and set(expected_coff) == set(retired) and
            all(row['returncode'] == 0 and row['machine_hex'] == '0x8664' for row in coff), 'Wrong exact ten-COFF retirement closure')
    for path, row in retired.items():
        project_path(row['path'])
        require(key(row['path']).startswith(key(PROJECT / 'Build/UiWindowHost' / BUILD_ID) + os.sep) and
                Path(row['path']).suffix.lower() == '.obj' and not os.path.lexists(row['path']) and
                all(row[name] == expected_coff[path][name] for name in ('path', 'bytes', 'sha256')), 'Retired file lineage differs')
    require(len(pe['compilation']['link_objects_before']) == 5 and
            pe['compilation']['link_objects_before'] == pe['compilation']['link_objects_after'], 'Final five-object link proof differs')
    build_ref = add(pe['build_result'])
    require(key(build_ref['path']) == key(PROJECT / f'evidence/ui_window_host/{BUILD_ID}/build_result.json'), 'Wrong actual build report')
    build = document(build_ref['path'])
    require(build['status'] == 'UI_WINDOW_HOST_CANDIDATE_BUILT' and build['build_id'] == BUILD_ID and build['error'] is None, 'B11 did not build')
    build_refs = list(refs(build))
    require(all(build[role] == row for role, row in EXTERNAL_TOOLCHAIN.items()), 'Approved historical toolchain paths/SHA differ')
    external = [row for row in build_refs if not key(row['path']).startswith(key(PROJECT) + os.sep)]
    require(len(external) == 3 and {key(row['path']) for row in external} == {key(row['path']) for row in EXTERNAL_TOOLCHAIN.values()} and
            all(row in EXTERNAL_TOOLCHAIN.values() for row in external), 'Unexpected external build artifact reference')
    object_refs = [row for row in build_refs if Path(row['path']).suffix.lower() == '.obj']
    discovery = {key(row['object']['path']) for row in coff if row['phase'] == 'dependency_discovery'}
    require(len(object_refs) == 5 and {key(row['path']) for row in object_refs} == discovery and
            all('bytes' not in row for row in object_refs), 'Build JSON no longer has its exact five hash-only discovery object refs')
    for row in build_refs:
        if row not in external:
            add(row)
    require(excluded == discovery, 'Build JSON excluded more than its five approved absent discovery refs')
    base = document(BASE)
    require(base['status'] == 'PASS_EXISTING_B9_R10_AND_DEFAULT_PRESERVED_AFTER_SOURCE_EDITS' and
            base['count'] == len(base['artifacts']) == 623 and base['retired_raw_objects_not_required'] is True, 'Wrong 623-ref frozen preservation ledger')
    for row in base['artifacts']:
        require(key(project_path(row['path'])) not in retired, 'Frozen baseline unexpectedly overlaps new retired COFF')
        add(row)

    # Preserve these receipts themselves; do not walk their historical live-source maps.
    for name in ('source_conformance.json', 'source_seal.json', 'build_run.json', 'attestation_retry.json',
                 'capture_result.json', 'linked_conformance.json', 'build_objects_retired.json', 'build_scope.json', 'catalog.json'):
        artifact(OWNED / name)
    for row in (pe['actual_build_run'], pe['actual_catalog'], pe['source_seal']):
        add(row)
    prior = document(R10)
    require(prior['run_id'] == R10.parent.name and len(prior['runtime_inputs']) == 24 and prior['smoke'] is False and
            prior['resume_from'] is None and prior['ui_support_from_run'] is None, 'Wrong unused R10 reference')
    for row in prior['runtime_inputs']:
        add(row)
    support = prior['interactive_ui_support_inventory']
    require(set(support['tools']) == set(TOOLS) - {'run_interactive_game.py'}, 'R10 did not retain six support tools')
    for row in support['tools'].values():
        add(row['frozen'])
    for row in (support['inline_icons']['frozen'], support['asset_preparation_provenance']['frozen'],
                support['frozen_support_manifest'], prior['interactive_ui_support']):
        add(row)
    for role, row in prior['launcher_control_metadata'].items():
        if role == 'python':
            require(key(row['path']) == key(sys.executable), 'Unexpected external R10 launcher interpreter')
        else:
            add(row)
    release_path = PROJECT / 'Play/EarlyAccess/release.json'
    release = document(release_path)
    default_request = add(release['request'])  # Relative paths are relative to PROJECT, not the release directory.
    for row in document(default_request['path'])['runtime_inputs']:
        add(row)
    for row in (*release['launchers'].values(), release['shared_launcher']):
        add(row)
    for name in ('source_before.zip', 'basic_binding.json', 'frontend_tests.json', 'test_font_binding.py', 'validate_frontend.py',
                 'frontend_tests_retry_03.json', 'font_drift_review.json'):
        artifact(STAGE / name)
    tests = document(STAGE / 'frontend_tests_retry_03.json')
    require(tests['schema'] == 'zerosis.goody_hut.frontend_component_tests.v1' and tests['status'] == 'PASS_PYTHON_COMPONENTS_NO_NATIVE' and
            tests['inputs_unchanged'] is True and not tests['forbidden_access_attempts'] and not tests['component_scratch_remaining'] and
            all(tests[name] is False for name in ('native_host_gamecore_hwnd_executed', 'retail_user_state_accessed', 'default_promoted', 'full_engine_goal_complete')),
            'Final frontend component approval did not pass privately')
    for row in tests['inputs']:
        add(row)

    capture = document(OWNED / 'capture_result.json')
    root = project_path(capture['cache_root'])
    require(capture['status'] == 'PASS' and capture['selected_files'] == len(capture['owned_inputs']) == 15 and
            root.parent == PROJECT / 'Build/SharedUiFontInputs' and re.fullmatch('[0-9a-f]{64}', root.name) and
            capture['content_id'] == root.name and capture['source_and_cache_byte_identical'] is True and
            capture['source_file_hardlinks_created'] == 0, 'Owned font capture differs')
    for row in capture['owned_inputs']:
        require(Path(row['path']).is_relative_to(root), 'Owned font escaped its captured cache')
        add(row)
    profile = add(capture['profile'])
    prepared = add(build['ui_assets'])
    prepared_doc = document(prepared['path'])
    require(prepared_doc['font_input_profile']['profile_id'] == capture['owned_profile']['profile_id'] and
            prepared_doc['font_input_profile']['asset_root'] == str(root) and
            add(dict(path=str(PROJECT / 'evidence/ui_popup/assets/prepared.json'), sha256=prepared['sha256']))['bytes'] == prepared['bytes'],
            'Frozen/current prepared UI or owned-font profile differs')
    source_inputs = {'tools/' + name: artifact(PROJECT / 'tools' / name) for name in TOOLS}
    unit_root = PROJECT / 'Build/UnitAssets' / PACKAGE
    package = artifact(unit_root / 'unit-assets.bin', dict(sha256=PACKAGE))
    unit_manifest = artifact(unit_root / 'unit-assets.manifest.json', dict(sha256='5fcfbdc669ffd233c4ec64118e8e938656079527028a7ac052659421c6b24e7a'))
    policy = artifact(HELPER.parent / 'PolicyInfo.ini', dict(sha256='af852aac03c83306ba18fef78dddf7c4eec965db3d526fec5555feba25d98ad9'))
    icons = artifact(PROJECT / 'evidence/ui_popup/assets/inline_icons.json')
    require(icons['sha256'] == support['inline_icons']['frozen']['sha256'], 'Original inline icons changed from R10')
    scope = dict(schema='zerosis.goody_hut.font_runtime_preparation.scope.v1', host_build_id=BUILD_ID,
        host_build=build_ref, pe_attestation=artifact(OWNED / 'attestation_retry.json'),
        raw_objects_retired=artifact(OWNED / 'build_objects_retired.json'), source_inputs=source_inputs,
        existing_runtime=artifact(R10), unit_manifest=unit_manifest, unit_package=package, private_policy=policy,
        preservation=sorted(recorded.values(), key=lambda row: key(row['path'])), progress_before=artifact(PROGRESS),
        owned_font_capture=artifact(OWNED / 'capture_result.json'), font_inputs=capture['owned_inputs'], font_profile=profile,
        font_asset_root=str(root), font_profile_id=capture['owned_profile']['profile_id'], expected_frozen_prepared=prepared,
        expected_inline_icons=icons, helper_module=artifact(HELPER), preserved_identity_guard=artifact(LEGACY),
        preparation_guard=artifact(STAGE / 'prepare_runtime.py'), private_preparation_allowed=True,
        retail_mod_test_hold_active=True, native_host_gamecore_hwnd_execution_allowed=False,
        retail_user_state_or_game_process_access_allowed=False, default_promotion_allowed=False, full_engine_goal_complete=False)
    require(len(scope) == 28 and not os.path.lexists(OUTPUT), 'Scope is not the exact fresh 28-key handoff')
    # Recheck every retained path after collection, independently of hardlink digest reuse.
    cache.clear()
    for row in list(recorded.values()):
        artifact(row['path'], row)
    with OUTPUT.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(scope, stream, ensure_ascii=False, indent=2);stream.write('\n');stream.flush();os.fsync(stream.fileno())
    print(json.dumps(dict(status='SCOPE_CREATED_RUNTIME_NOT_EXECUTED', output=artifact(OUTPUT), scope_keys=len(scope),
        preservation_refs=len(scope['preservation']), source_inputs=len(source_inputs), font_inputs=len(capture['owned_inputs']),
        build_artifact_refs=len(build_refs), build_unique_artifact_paths=len({key(row['path']) for row in build_refs}),
        retired_objects_approved=len(retired), build_missing_object_refs_excluded=len(excluded),
        excluded_external_toolchain=len(external), excluded_external_toolchain_refs=sorted(external, key=lambda row: key(row['path'])),
        external_toolchain_verification='PINNED_B11_PE_AND_BUILD_HISTORY_ONLY_NO_EXTERNAL_REHASH_OR_EXECUTION', unexpected_external_refs=0)))


if __name__ == '__main__':
    main()
