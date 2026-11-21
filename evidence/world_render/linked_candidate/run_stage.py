"""Own one scoped Host build and private preparation without native execution."""
from __future__ import annotations

from contextlib import redirect_stdout
from datetime import datetime, timezone
import argparse
import ctypes
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

PROJECT = Path(__file__).absolute().parents[3]
STAGE = Path(__file__).absolute().parent
SCOPE = STAGE / 'scope.json'
SCOPE_SHA256 = 'c63aaa0a5d6dac258c430d719418db0948e8f1b36b73e0fd947ea5834d738f22'
BASE = PROJECT / 'evidence/save_delete/linked_candidate/run_stage.py'
BASE_SHA256 = '03741b3a9d6045a31cd8a6f9d6cd68a819497e431e770db88564769443f4356a'
BUILDER = PROJECT / 'tools/build_ui_window_host.py'
BUILDER_SHA256 = '04a69d9ab99dab2f6f4566084cb87ce294bf6e9adb5c6410d790a763f25397ef'
DONOR = '20261016T122615Z_1af4a5449cf1'
UNITS = ('host_main', 'window', 'renderer', 'world_renderer', 'terrain_renderer')
BUILD_ID = re.compile(r'\d{8}T\d{6}Z_[0-9a-f]{12}')
POLICY = b'[UserSettings]\r\nPolicyInfo = 1\r\n'


def checked_file(path):
    path = Path(path)
    if not path.is_absolute() or not path.is_relative_to(PROJECT):
        raise RuntimeError('Scoped input is outside the project: ' + str(path))
    current = path
    while True:
        info = current.lstat()
        if stat.S_ISLNK(info.st_mode) or info.st_file_attributes & 0x400:
            raise RuntimeError('Scoped input contains a reparse point: ' + str(current))
        if current == PROJECT:
            break
        current = current.parent
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode):
        raise RuntimeError('Scoped input is not a regular file: ' + str(path))
    return path, info


def sealed_artifact(path):
    path, before = checked_file(path)
    sha = hashlib.sha256()
    with path.open('rb') as stream:
        while block := stream.read(1024 * 1024):
            sha.update(block)
    _, after = checked_file(path)
    fields = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_file_attributes')
    if any(getattr(before, key) != getattr(after, key) for key in fields):
        raise RuntimeError('Scoped input changed while being read: ' + str(path))
    return {'path': str(path), 'bytes': after.st_size, 'sha256': sha.hexdigest()}


if sealed_artifact(BASE)['sha256'] != BASE_SHA256:
    raise RuntimeError('The preserved common helper changed')
spec = importlib.util.spec_from_file_location('_world_render_preserved_stage_common', BASE)
if spec is None or spec.loader is None:
    raise RuntimeError('Cannot import the preserved common helper')
common = importlib.util.module_from_spec(spec)
spec.loader.exec_module(common)
if common.PROJECT != PROJECT or sealed_artifact(BASE)['sha256'] != BASE_SHA256:
    raise RuntimeError('The preserved common helper has a different project or changed during import')
common.STAGE = STAGE
artifact, read, write, require = common.artifact, common.read, common.write, common.require


def verify_profile(path, expected):
    flags = Path(path).read_text(encoding='utf-8-sig').splitlines()
    require([value for value in flags if value.startswith('/std:')] == [expected['language']],
            'Unexpected translation-unit language: ' + str(path))
    require([value for value in flags if value.startswith('/source-charset:')] == [expected['source_charset']],
            'Unexpected translation-unit source charset: ' + str(path))
    require(all(value in flags for value in expected['required_flags']) and '/c' in flags,
            'A required compile flag is missing: ' + str(path))
    require(not any(value == forbidden or value.startswith(forbidden + '"')
                    for value in flags for forbidden in expected['forbidden_flags']),
            'A forbidden compile flag was supplied: ' + str(path))
    require([value for value in flags if value.startswith('/D')] == expected['defines_exact'],
            'Translation-unit definitions differ: ' + str(path))


def verify_scope():
    require(sealed_artifact(SCOPE)['sha256'] == SCOPE_SHA256, 'The approved linked-stage scope changed')
    scope = read(SCOPE)
    require(scope['schema'] == 'zerosis.world_camera_civilian_linked_scope.v1' and
            scope['original_game_new_mod_test_hold'] is True and scope['retail_mod_test_hold_active'] is True and
            scope['execution_allowed'] is False and scope['default_promoted'] is False and
            scope['host_gamecore_hwnd_executed'] is False and scope['full_engine_goal_complete'] is False,
            'The linked-stage scope changed its execution or acceptance boundary')
    require(len(scope['cpp_feature_seals']) == 6 and len(scope['source19_seals']) == 19,
            'The approved feature/source contract count changed')
    require(scope['common_helper']['path'] == str(BASE) and scope['common_helper']['sha256'] == BASE_SHA256 and
            scope['builder']['path'] == str(BUILDER) and scope['builder']['sha256'] == BUILDER_SHA256,
            'The scoped common helper or builder is not the exact preserved input')
    expected_donor = str(PROJECT / f'evidence/ui_window_host/{DONOR}/build_result.json')
    require(scope['donor_build']['path'] == scope['frozen_input_reuse_donor']['path'] == expected_donor,
            'The approved frozen donor is not B7')
    rows = [*scope['cpp_feature_seals'], *scope['source19_seals'], *scope['unchanged_project_source_seals'],
            *scope['unchanged_baseline_seals'].values(), *scope['protected_artifacts'],
            *scope['prior_source_conformances'].values(), *scope['verifier_dependencies'].values(),
            *scope['current_unit_assets'].values()]
    rows += [scope[key] for key in ('prior_linked_conformance', 'historical_ui_attestation', 'donor_build',
             'frozen_input_reuse_donor', 'header_recovery', 'generated_header_before', 'prepared_assets_recovery',
             'prepared_assets_before', 'builder', 'common_helper', 'progress_before', 'progress_backup', 'storage_before')]
    for precedence in scope['source_precedence']:
        require(precedence['current'] in scope['cpp_feature_seals'] and
                precedence['superseded_backup']['sha256'] == precedence['superseded']['sha256'] and
                precedence['superseded_backup']['bytes'] == precedence['superseded']['bytes'],
                'The explicit approved source precedence changed')
        rows.extend((precedence['current'], precedence['superseded_backup'], precedence['approval']))
    profiles = scope['expected_compile_profile']['by_tu']
    require(tuple(profiles) == UNITS, 'The approved five translation units changed')
    for unit, profile in profiles.items():
        for phase in ('dependency_discovery', 'final_compilation'):
            row = profile['baseline_responses'][phase]
            rows.append(row)
    checked = {}
    for row in rows:
        path = row['path']
        observed = checked.setdefault(path, None)
        if observed is None:
            observed = checked[path] = sealed_artifact(path)
        require(observed['bytes'] == row['bytes'] and observed['sha256'] == row['sha256'],
                'A scoped source or preserved artifact changed: ' + path)
    for profile in profiles.values():
        for phase in ('dependency_discovery', 'final_compilation'):
            verify_profile(profile['baseline_responses'][phase]['path'], profile[phase])
    require(sealed_artifact(SCOPE)['sha256'] == SCOPE_SHA256, 'The scope changed during verification')
    return scope


def verify_build(build_id, scope):
    require(isinstance(build_id, str) and BUILD_ID.fullmatch(build_id) is not None, 'An exact successful build ID is required')
    path = PROJECT / f'evidence/ui_window_host/{build_id}/build_result.json'
    report_ref = sealed_artifact(path)
    report = read(path)
    require(report['schema'] == 'zerosis.ui_window_host_build.v1' and report['build_id'] == build_id and
            report['status'] == 'UI_WINDOW_HOST_CANDIDATE_BUILT' and report['error'] is None and
            report['source_inputs_unchanged'] is True and report['provider_inputs_unchanged'] is True,
            'The exact current Host build did not pass')
    require(all(report[key] is False for key in ('gamecore_loaded', 'sdk_linked', 'stage_updated',
                                                'mods_updated', 'host_runtime_executed')),
            'The Host build exceeded its compile/link-only boundary')
    require(report['frozen_input_reuse']['donor_build_id'] == DONOR and
            report['frozen_input_reuse']['donor_report_sha256'] == scope['donor_build']['sha256'] and
            report['frozen_input_reuse']['donor_content_and_metadata_preserved'] is True,
            'The Host build did not preserve the exact B7 donor')
    for phase in ('dependency_discovery', 'final_compilation'):
        units = report[phase]['translation_units']
        require(tuple(unit['translation_unit'] for unit in units) == UNITS and
                all(type(unit['returncode']) is int and unit['returncode'] == 0 for unit in units),
                'The exact five translation units did not compile successfully')
        for unit in units:
            response = unit['response']
            observed = sealed_artifact(response['path'])
            require(observed['sha256'] == response['sha256'], 'A new compile response changed')
            verify_profile(response['path'], scope['expected_compile_profile']['by_tu'][unit['translation_unit']][phase])
    for expected in scope['cpp_feature_seals']:
        rows = [row for row in report['compiler_inputs'] if row.get('original_path') == expected['path']]
        require(len(rows) == 1 and rows[0]['sha256'] == expected['sha256'] and rows[0]['bytes'] == expected['bytes'],
                'The new compiler closure does not contain an approved current feature: ' + expected['path'])
    require(sealed_artifact(path) == report_ref, 'The new Host report changed during verification')
    return report_ref


def quiet_process_policy():
    require(os.name == 'nt', 'This scoped build owner requires Windows')
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel32.SetErrorMode.argtypes = [ctypes.c_uint]
    kernel32.SetErrorMode.restype = ctypes.c_uint
    kernel32.WerSetFlags.argtypes = [ctypes.c_ulong]
    kernel32.WerSetFlags.restype = ctypes.c_long
    previous = kernel32.SetErrorMode(32771)
    result = kernel32.WerSetFlags(32)
    require(result >= 0, 'Runner WerSetFlags failed before launching a child')
    os.environ.pop('CL', None)
    os.environ.pop('_CL_', None)
    return {'dll': 'kernel32', 'error_mode': 32771, 'previous_error_mode': previous,
            'wer_flags': 32, 'wer_hresult': result, 'compiler_option_environment_cleared': ['CL', '_CL_']}


def run_command(name, arguments):
    original_run = common.subprocess.run

    def background(*args, **kwargs):
        kwargs['creationflags'] = kwargs.get('creationflags', 0) | subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS
        return original_run(*args, **kwargs)

    common.subprocess.run = background
    try:
        with redirect_stdout(io.StringIO()):
            return common.run_command(name, arguments)
    finally:
        common.subprocess.run = original_run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('build', 'prepare'))
    parser.add_argument('--build-id')
    args = parser.parse_args()
    if args.action == 'build' and args.build_id is not None:
        parser.error('The builder allocates its own fresh build ID')
    if args.action == 'prepare' and (args.build_id is None or BUILD_ID.fullmatch(args.build_id) is None):
        parser.error('Private preparation requires the exact successful build ID')
    scope = verify_scope()
    started = STAGE / (args.action + '_started.json')
    names = [started.name, args.action + '_invocation.json', args.action + '.stdout.log', args.action + '.stderr.log']
    if args.action == 'prepare':
        names += ['PolicyInfo.ini', 'preparation_started.json', 'prepared.json', 'preparation_identity_audit.json',
                  'materializer.stdout.log', 'materializer.stderr.log']
    require(not any(os.path.lexists(STAGE / name) for name in names),
            'Inspect the existing invocation, start token or logs instead of repeating this action')
    if args.action == 'prepare':
        invocation = read(STAGE / 'build_invocation.json')
        require(invocation['status'] == 'PASS' and type(invocation['exit_code']) is int and invocation['exit_code'] == 0 and
                invocation['result']['build_id'] == args.build_id, 'Preparation must use this stage successful build')
        verify_build(args.build_id, scope)
        checked_file(STAGE / 'prepare_candidate.py')
    state = {'status': 'STARTED', 'action': args.action, 'utc': datetime.now(timezone.utc).isoformat(),
             'scope_sha256': SCOPE_SHA256, 'owner': sealed_artifact(Path(__file__).absolute()),
             'host_gamecore_hwnd_or_retail_user_state_accessed': False}
    with started.open('x', encoding='utf8') as stream:
        json.dump(state, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    try:
        state['runner_error_ui'] = quiet_process_policy()
        write(started, state)
        if args.action == 'build':
            arguments = [str(BUILDER), '--reuse-frozen-build', DONOR]
        else:
            with (STAGE / 'PolicyInfo.ini').open('xb') as stream:
                stream.write(POLICY)
            arguments = [str(STAGE / 'prepare_candidate.py'), '--build-id', args.build_id]
        code = run_command(args.action, arguments)
        invocation = read(STAGE / (args.action + '_invocation.json'))
        result = invocation.get('result') or {}
        verify_scope()
        report = None
        if code == 0:
            build_id = result.get('build_id') if args.action == 'build' else args.build_id
            report = verify_build(build_id, scope)
        else:
            build_id = result.get('build_id') if args.action == 'build' else args.build_id
        state.update(status='PASS' if code == 0 else 'FAIL', exit_code=code, finished_utc=datetime.now(timezone.utc).isoformat(),
                     scope_and_preserved_inputs_unchanged=True, host_build=report)
        write(started, state)
        summary = {'status': state['status'], 'exit_code': code, 'action': args.action, 'build_id': build_id,
                   'report_path': report['path'] if report else result.get('report'),
                   'summary': result.get('status'), 'run_id': result.get('run_id'),
                   'runner_error_ui': state['runner_error_ui']}
        print(json.dumps(summary, ensure_ascii=False))
        return code
    except Exception as error:
        state.update(status='WRAPPER_FAILED', error=str(error)[:1600], finished_utc=datetime.now(timezone.utc).isoformat())
        write(started, state)
        print(json.dumps({'status': state['status'], 'exit_code': 1, 'action': args.action,
                          'build_id': args.build_id, 'error': state['error']}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
