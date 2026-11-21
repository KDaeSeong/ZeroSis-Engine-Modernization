"""Reuse the preserved preparation guard; audit one private overwrite runtime.

The parent run_stage command owns invocation and private PolicyInfo creation.
This wrapper never starts a Host, GameCore, window, or a preparation subprocess.
"""
from contextlib import ExitStack
from datetime import datetime, timezone
import argparse
import ctypes
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import sys
from unittest.mock import patch

PROJECT = Path(__file__).absolute().parents[3]
STAGE = Path(__file__).absolute().parent
BASE = PROJECT / 'evidence/save_delete/linked_candidate/prepare_candidate.py'
BASE_SHA256 = 'd2e9743307cb8687b5ab82e9ab76863ead2ca1d1ea4adca0ee18e189631b481e'
BASE_COMMON = PROJECT / 'evidence/save_delete/linked_candidate/run_stage.py'
BASE_COMMON_SHA256 = '03741b3a9d6045a31cd8a6f9d6cd68a819497e431e770db88564769443f4356a'
TOOLS = ('interactive_ui_driver.py', 'render_ui_popup.py', 'ui_pixel_scene.py',
         'ui_bitmap_fonts.py', 'civ5_ui_assets.py')


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError('Cannot load the exact preserved stage module')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def install_audit_guard(denied):
    retail = os.path.normcase(r"C:\Users\home\OneDrive\Documents\My Games\Sid Meier's Civilization 5")

    def audit(event, arguments):
        if event in ('open', 'os.listdir', 'os.scandir') and arguments and isinstance(arguments[0], (str, bytes, os.PathLike)):
            target = os.path.normcase(os.path.abspath(os.fsdecode(arguments[0])))
            if target.startswith('\\\\?\\'):
                target = target[4:]
            if target == retail or target.startswith(retail + os.sep):
                denied.append(event)
                raise RuntimeError('Retail user configuration, MODS and saves are forbidden during preparation')
        if event in ('subprocess.Popen', 'os.system', 'os.startfile', 'os.startfile/2',
                     'os.exec', 'os.posix_spawn', 'os.spawn', 'ctypes.dlopen'):
            denied.append(event)
            raise RuntimeError('Process execution or ctypes library loading is forbidden during preparation')

    sys.addaudithook(audit)


def verify_private_identity(helpers, build_id):
    artifact, read, require = helpers.artifact, helpers.read, helpers.require
    prepared = read(STAGE / 'prepared.json')
    require(prepared['status'] == 'PREPARED_NOT_EXECUTED' and prepared['host_build_id'] == build_id,
            'The preserved guard did not prepare this exact candidate')
    run_id = prepared['run_id']
    require(re.fullmatch(r'\d{8}T\d{6}Z_[0-9a-f]{12}', run_id) is not None, 'Unexpected private runtime ID')
    runtime = PROJECT / 'Build/InteractiveGameRuntime' / run_id
    evidence = PROJECT / 'evidence/interactive_game' / run_id
    request_path = evidence / 'request.json'
    require(prepared['request'] == artifact(request_path), 'Prepared request differs')
    request = read(request_path)
    build_path = PROJECT / f'evidence/ui_window_host/{build_id}/build_result.json'
    build = read(build_path)
    require(prepared['host_build'] == artifact(build_path), 'Prepared Host report differs')
    require(request['smoke'] is False and request['resume_from'] is None and request['ui_support_from_run'] is None,
            'Private preparation unexpectedly selected an execution or resume profile')
    require(not (runtime / 'sessions').exists() and not any((evidence / name).exists()
            for name in ('attempt.json', 'result.json', 'driver_result.json')), 'Unexpected native execution output')
    require(len(request['runtime_inputs']) == prepared['runtime_inputs'] == 24, 'Expected exactly 24 runtime inputs')
    by_path = {row['path']: row for row in request['runtime_inputs']}
    require(len(by_path) == 24, 'Private runtime contains duplicate input paths')
    immutable, databases = [], []
    for row in request['materializations']:
        if row.get('materialization_method') != 'hardlink':
            continue
        target, cache = Path(row['target']), Path(row['cache'])
        ti, ci = target.lstat(), cache.lstat()
        require(stat.S_ISREG(ti.st_mode) and stat.S_ISREG(ci.st_mode) and
                not (ti.st_file_attributes | ci.st_file_attributes) & 0x400,
                'Immutable runtime/cache file is not ordinary')
        require(ti.st_ino and (ti.st_dev, ti.st_ino) == (ci.st_dev, ci.st_ino) and
                ti.st_nlink >= 2 and ci.st_nlink >= 2 and ti.st_file_attributes & 1 and ci.st_file_attributes & 1,
                'Immutable runtime/cache identity or readonly policy differs')
        source_info = Path(by_path[str(target)]['source']).stat()
        require((source_info.st_dev, source_info.st_ino) != (ti.st_dev, ti.st_ino),
                'The immutable cache aliases its original input')
        target_ref, cache_ref = artifact(target), artifact(cache)
        require(target_ref['sha256'] == cache_ref['sha256'] == row['sha256'] == by_path[str(target)]['sha256'],
                'Private runtime/cache payload differs')
        immutable.append({'target': target_ref, 'cache': cache_ref, 'identity': [ti.st_dev, ti.st_ino],
                          'original_identity': [source_info.st_dev, source_info.st_ino],
                          'link_count_observed': ti.st_nlink, 'readonly': True, 'cache_method': row['cache_method']})
    require(len(immutable) == prepared['hardlinks'] == 15, 'Expected exactly 15 readonly cache hardlinks')
    for row in request['runtime_inputs']:
        target = Path(row['path'])
        if target.suffix.lower() != '.db':
            continue
        si, ti = Path(row['source']).stat(), target.lstat()
        require(stat.S_ISREG(ti.st_mode) and ti.st_ino and si.st_ino and ti.st_nlink == 1 and
                not ti.st_file_attributes & (1 | 0x400) and (si.st_dev, si.st_ino) != (ti.st_dev, ti.st_ino),
                'Writable private database is aliased, readonly or not ordinary')
        require(artifact(target)['sha256'] == row['sha256'], 'Private database payload differs')
        databases.append({'database': artifact(target), 'source_identity': [si.st_dev, si.st_ino],
                          'private_identity': [ti.st_dev, ti.st_ino], 'writable_private_copy': True})
    require(len(databases) == 2 and len({tuple(row['private_identity']) for row in databases}) == 2,
            'Expected two independent writable private databases')
    inventory = request['interactive_ui_support_inventory']
    manifest_path = Path(inventory['frozen_support_manifest']['path'])
    manifest = read(manifest_path)
    require(artifact(manifest_path)['sha256'] == inventory['frozen_support_manifest']['sha256'] and
            set(inventory['tools']) == set(manifest['tools']) == set(TOOLS), 'Wrong frozen frontend manifest')
    support = {}
    for name in TOOLS:
        row = inventory['tools'][name]
        source, frozen = artifact(PROJECT / 'tools' / name), artifact(Path(row['frozen']['path']))
        require(source['sha256'] == frozen['sha256'] == row['source']['sha256'] == row['frozen']['sha256'] ==
                manifest['tools'][name]['sha256'], 'Current/frozen/manifest frontend mismatch: ' + name)
        support[name] = {'current': source, 'frozen': frozen, 'manifest_sha256': manifest['tools'][name]['sha256']}
    catalog = inventory['asset_preparation_provenance']['frozen']
    require(artifact(Path(catalog['path']))['sha256'] == catalog['sha256'] == build['ui_assets']['sha256'] ==
            manifest['asset_preparation_provenance']['sha256'], 'Private frontend UI catalog differs from this Host build')
    require(prepared.get('native_process_or_ctypes_calls', 0) == 0 and
            not prepared['forbidden_access_attempts'], 'The preserved guard recorded a forbidden operation')
    return {'prepared': artifact(STAGE / 'prepared.json'), 'request': artifact(request_path),
            'host_build': artifact(build_path), 'run_id': run_id, 'host_build_id': build_id,
            'runtime_inputs': 24, 'immutable_cache_links': immutable, 'private_databases': databases,
            'current_frozen_manifest_support': support, 'ui_catalog': catalog,
            'ui_support_manifest': artifact(manifest_path), 'native_execution_outputs_absent': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-id', required=True)
    args = parser.parse_args()
    if re.fullmatch(r'\d{8}T\d{6}Z_[0-9a-f]{12}', args.build_id) is None:
        parser.error('An exact owned Host build ID is required')
    audit_path = STAGE / 'preparation_identity_audit.json'
    if audit_path.exists():
        raise RuntimeError('Inspect the existing preparation identity audit instead of repeating preparation')
    denied, guards = [], []
    install_audit_guard(denied)
    with ExitStack() as stack:
        for name in ('subprocess.Popen', 'os.startfile', 'ctypes.CDLL', 'ctypes.WinDLL'):
            guards.append(stack.enter_context(patch(name, side_effect=RuntimeError('Execution forbidden: ' + name))))
        helpers = load_module('_overwrite_stage_common_for_preparation', STAGE / 'run_stage.py')
        require, artifact = helpers.require, helpers.artifact
        require(helpers.PROJECT == PROJECT and helpers.STAGE == STAGE, 'Stage helper scope differs')
        require(artifact(BASE)['sha256'] == BASE_SHA256 and artifact(BASE_COMMON)['sha256'] == BASE_COMMON_SHA256,
                'The preserved preparation guard/common helper changed')
        require((STAGE / 'PolicyInfo.ini').read_bytes() == b'[UserSettings]\r\nPolicyInfo = 1\r\n',
                'Expected the private policy file created by this stage parent command')
        provenance = {'wrapper': artifact(Path(__file__).absolute()), 'stage_common': artifact(STAGE / 'run_stage.py'),
                      'preserved_guard': artifact(BASE), 'preserved_common': artifact(BASE_COMMON)}
        # The preserved module imports only the common interface. Bind that
        # interface to this new stage without changing any preserved file.
        with patch.dict(sys.modules, {'run_stage': helpers}):
            legacy = load_module('_preserved_delete_preparation_guard', BASE)
        require(legacy.PROJECT == PROJECT and legacy.STAGE == STAGE and legacy.write is helpers.write,
                'The preserved guard did not bind exclusively to this new stage')
        with patch.object(sys, 'argv', [str(Path(__file__).absolute()), '--build-id', args.build_id]):
            legacy.main()
        record = verify_private_identity(helpers, args.build_id)
        require(not denied and all(guard.call_count == 0 for guard in guards), 'A forbidden operation was attempted')
        for row in provenance.values():
            require(artifact(Path(row['path'])) == row, 'A preparation wrapper/helper changed during materialization')
        record.update(schema='zerosis.owned_save_overwrite.private_preparation_identity.v1', status='PASS_PREPARED_NOT_EXECUTED',
                      utc=datetime.now(timezone.utc).isoformat(), provenance=provenance,
                      forbidden_access_attempts=denied, outer_process_or_ctypes_calls=sum(guard.call_count for guard in guards),
                      preserved_guard_and_reports_unmodified=True, retail_mod_test_hold_active=True,
                      host_gamecore_hwnd_executed=False, retail_user_state_or_processes_accessed=False,
                      native_overwrite_or_full_engine_acceptance=False, default_release_promoted=False)
        helpers.write(audit_path, record)
        print(json.dumps({'status': record['status'], 'run_id': record['run_id'], 'host_build_id': args.build_id,
                          'runtime_inputs': record['runtime_inputs'], 'hardlinks': len(record['immutable_cache_links']),
                          'private_databases': len(record['private_databases']), 'identity_audit': artifact(audit_path)}))


if __name__ == '__main__':
    main()
