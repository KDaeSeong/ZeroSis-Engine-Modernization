"""Run bounded headless policy/glue regressions; deny native/game execution."""
from __future__ import annotations

import argparse
from contextlib import ExitStack, redirect_stderr, redirect_stdout
import ctypes
from datetime import datetime, timezone
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
PROJECT = Path(__file__).absolute().parents[1]
STAGE = PROJECT / 'evidence/concurrency/runtime_configuration'
SCOPE_SHA = '3442c84392c969f37df3d6d6a00576a0df0df96d365586db73edf99158d45bc5'
SOURCE_PATHS = {'options_helper': 'tools/found_value_runtime_options.py',
                'runner': 'tools/run_interactive_game.py', 'driver': 'tools/interactive_ui_driver.py',
                'tests': 'Tests/found_value_runtime_options.py', 'verifier': 'tools/verify_found_value_runtime_options.py'}
REGRESSIONS = {'worker_unit_panel': 'Tests/test_worker_unit_panel_profile.py',
               'host_runtime_inputs': 'Tests/test_host_runtime_inputs.py'}
PRODUCTION_SEALS = {'options_helper': (5700, '63d8ee79402bac7e5f405a0475349d776fdc3ed2b7b3b10350f991256a527f69'),
                    'runner': (242798, 'e33f0472cce84c606bc2b44403442b0a9a6417ea193f73858ba6a0447bfbfd41'),
                    'driver': (77736, 'cd2710e55f79975e85ce3be3ed90b715e9df3257637992afb4f841966c90b81b')}


def require(value, message):
    if not value:
        raise RuntimeError(message)


def normalized(path):
    return os.path.normcase(os.path.abspath(path))


def artifact(path):
    path = Path(os.path.abspath(path))
    require(path.is_relative_to(PROJECT), 'Proof input escaped the project')
    for parent in (path, *path.parents):
        info = parent.lstat()
        require(not stat.S_ISLNK(info.st_mode) and not getattr(info, 'st_file_attributes', 0) & 0x400,
                'Proof input contains a reparse point')
        if parent == PROJECT:
            break
    before = path.stat()
    require(stat.S_ISREG(before.st_mode), 'Proof input is not a regular file')
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    after = path.stat()
    require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) ==
            (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns), 'Proof input changed while hashing')
    return {'path': str(path), 'bytes': after.st_size, 'sha256': digest}


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    require(spec is not None and spec.loader is not None, 'Cannot load the scoped test module')
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=STAGE / 'test_result.json')
    args = parser.parse_args()
    output = Path(os.path.abspath(args.output))
    require(output.parent == STAGE and not os.path.lexists(output), 'Use a fresh result filename in the scoped stage')
    scope_path = STAGE / 'scope.json'
    scope_ref = artifact(scope_path)
    require(scope_ref['sha256'] == SCOPE_SHA, 'Reviewed runtime-configuration scope changed')
    scope = json.loads(scope_path.read_text(encoding='utf-8-sig'))
    require(scope['schema'] == 'zerosis.found_value_runtime_configuration.scope.v1' and
            scope['retail_mod_test_hold_active'] is True and all(scope[key] is False for key in
            ('host_execution_allowed', 'gamecore_execution_allowed', 'native_window_execution_allowed',
             'retail_user_state_access_allowed', 'game_process_access_allowed', 'default_promoted')),
            'Scope does not retain the headless/native hold')
    denied, roots, temporary_files, recorded = [], {}, [], set()
    retail = normalized(r"C:\Users\home\OneDrive\Documents\My Games\Sid Meier's Civilization 5")
    original_temporary = tempfile.TemporaryDirectory

    def owned(path):
        target = normalized(path)
        return any(target == root or target.startswith(root + os.sep) for root in roots)

    def record_temporary(path):
        path = Path(os.path.abspath(path))
        require(owned(path), 'Temporary evidence escaped its exclusively created directory')
        try:
            info = path.lstat()
        except FileNotFoundError:
            return
        if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            return
        require(info.st_size <= 8 * 1024 * 1024, 'Temporary fixture exceeds the headless bound')
        with path.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        seal = (str(path), digest)
        if seal not in recorded:
            require(len(temporary_files) < 4096, 'Too many headless fixture files')
            recorded.add(seal)
            temporary_files.append({'path': str(path), 'bytes': info.st_size, 'sha256': digest,
                                    'result': 'OWNED_TEMPORARY_REMOVED' })

    class TrackedTemporaryDirectory(original_temporary):
        def __init__(self, *positional, **keywords):
            super().__init__(*positional, **keywords)
            path = Path(self.name).absolute()
            require(path.is_relative_to(PROJECT) and path != PROJECT, 'Tests must create temporary directories in the project')
            info = path.lstat()
            require(stat.S_ISDIR(info.st_mode) and not getattr(info, 'st_file_attributes', 0) & 0x400,
                    'Temporary test directory is not ordinary')
            roots[normalized(path)] = (info.st_dev, info.st_ino)

        def cleanup(self):
            path = Path(self.name).absolute()
            if path.exists():
                require(path.is_relative_to(PROJECT) and normalized(path) in roots, 'Refusing unowned recursive temporary cleanup')
                info = path.lstat()
                require((info.st_dev, info.st_ino) == roots[normalized(path)] and
                        not getattr(info, 'st_file_attributes', 0) & 0x400, 'Temporary root identity changed')
                for parent, _, files in os.walk(path, followlinks=False):
                    for filename in files:
                        record_temporary(Path(parent) / filename)
            super().cleanup()

    def audit(event, arguments):
        if event in ('open', 'os.listdir', 'os.scandir') and arguments and isinstance(arguments[0], (str, bytes, os.PathLike)):
            target = normalized(os.fsdecode(arguments[0]))
            if target.startswith('\\\\?\\'):
                target = target[4:]
            if target == retail or target.startswith(retail + os.sep):
                denied.append('retail-user-state:' + event)
                raise RuntimeError('Retail MODS, saves and settings are forbidden')
            if event == 'open':
                mode = arguments[1] if len(arguments) > 1 else ''
                flags = arguments[2] if len(arguments) > 2 else 0
                writing = (isinstance(mode, str) and any(char in mode for char in 'wax+')) or (
                    type(flags) is int and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
                if writing and target != normalized(output) and not owned(target):
                    denied.append('write-outside-owned-fixture')
                    raise RuntimeError('Tests cannot write production sources or existing proof files')
        if event == 'os.remove' and arguments and isinstance(arguments[0], (str, bytes, os.PathLike)):
            target = os.fsdecode(arguments[0])
            require(owned(target), 'Refusing removal outside the exclusively created test fixtures')
            record_temporary(target)
        if event == 'os.rmdir' and arguments:
            require(owned(arguments[0]), 'Refusing directory removal outside owned test fixtures')
        if event in ('subprocess.Popen', 'os.system', 'os.startfile', 'os.startfile/2',
                     'os.exec', 'os.posix_spawn', 'os.spawn', 'ctypes.dlopen'):
            denied.append(event)
            raise RuntimeError('Actual native/process execution is forbidden')

    sys.addaudithook(audit)
    source_before = {name: artifact(PROJECT / namepath) for name, namepath in SOURCE_PATHS.items()}
    for name, (size, digest) in PRODUCTION_SEALS.items():
        require((source_before[name]['bytes'], source_before[name]['sha256']) == (size, digest),
                'Reviewed production source changed: ' + name)
    regression_before = {name: artifact(PROJECT / namepath) for name, namepath in REGRESSIONS.items()}
    protected = scope['protected_artifacts']
    require(type(protected) is list, 'Expected the explicit protected SDK/source ledger')
    for row in protected:
        require(artifact(row['path']) == row, 'Protected SDK/source input changed before tests')
    backup = scope['progress_backup']
    require(artifact(backup['path']) == backup, 'Progress source-stage backup changed')
    suite, captured, test_result, failure = unittest.TestSuite(), io.StringIO(), None, None
    modules, guarded_calls = [], []
    try:
        with ExitStack() as stack:
            for name in ('subprocess.Popen', 'os.startfile', 'ctypes.CDLL', 'ctypes.WinDLL'):
                guarded_calls.append(stack.enter_context(patch(name, side_effect=RuntimeError('Actual execution forbidden: ' + name))))
            stack.enter_context(patch.object(tempfile, 'TemporaryDirectory', TrackedTemporaryDirectory))
            stack.enter_context(patch.object(sys, 'path', [*sys.path, str(PROJECT / 'Tests')]))
            with redirect_stdout(captured), redirect_stderr(captured):
                modules.append(load('_found_value_policy_headless_tests', PROJECT / SOURCE_PATHS['tests']))
                for name, relative in REGRESSIONS.items():
                    modules.append(load('_found_value_policy_regression_' + name, PROJECT / relative))
                for module in modules:
                    suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(module))
                test_result = unittest.TextTestRunner(stream=captured, verbosity=1).run(suite)
    except Exception as error:
        failure = type(error).__name__ + ': ' + str(error)
    source_after = {name: artifact(PROJECT / namepath) for name, namepath in SOURCE_PATHS.items()}
    regression_after = {name: artifact(PROJECT / namepath) for name, namepath in REGRESSIONS.items()}
    protected_unchanged = all(artifact(row['path']) == row for row in protected)
    scratch_absent = all(not os.path.lexists(path) for path in roots)
    no_calls = all(call.call_count == 0 for call in guarded_calls)
    controlled = len(modules[0].CONTROLLED_CHILDREN) if modules else 0
    success = (failure is None and test_result is not None and test_result.testsRun > 0 and test_result.wasSuccessful() and
               controlled >= 6 and not test_result.skipped and
               source_before == source_after and regression_before == regression_after and protected_unchanged and
               scratch_absent and not denied and no_calls and artifact(scope_path) == scope_ref and artifact(backup['path']) == backup)
    result = {'schema': 'zerosis.found_value_runtime_options.headless_tests.v1',
              'status': 'PASS_FOUND_VALUE_RUNTIME_OPTIONS_HEADLESS_ONLY' if success else 'FAIL_FOUND_VALUE_RUNTIME_OPTIONS_HEADLESS_ONLY',
              'utc': datetime.now(timezone.utc).isoformat(), 'scope': scope_ref,
              'source_inputs': source_after, 'sources_unchanged': source_before == source_after,
              'regression_inputs': regression_after, 'regression_inputs_unchanged': regression_before == regression_after,
              'protected_artifacts': protected, 'protected_unchanged': protected_unchanged, 'progress_backup': backup,
              'test_count': test_result.testsRun if test_result else 0,
              'failure_count': len(test_result.failures) if test_result else 0,
              'error_count': len(test_result.errors) if test_result else 0,
              'skipped_count': len(test_result.skipped) if test_result else 0,
              'harness_error': failure, 'failure_details': captured.getvalue()[-16000:] if not success else None,
              'controlled_host_popen_calls': controlled, 'actual_process_or_ctypes_calls': sum(call.call_count for call in guarded_calls),
              'forbidden_access_attempts': denied, 'temporary_directories': list(roots), 'temporary_artifacts': temporary_files,
              'owned_scratch_cleaned': scratch_absent, 'host_executed': False, 'gamecore_loaded': False,
              'hwnd_created': False, 'retail_user_state_accessed': False, 'game_process_queries': 0,
              'default_promoted': False, 'actual_sdk_worker_selection_verified': False,
              'physical_multicore_verified': False, 'performance_improvement_verified': False}
    with output.open('x', encoding='utf8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    print(json.dumps({'status': result['status'], 'test_count': result['test_count'],
                      'failure_count': result['failure_count'], 'error_count': result['error_count'],
                      'controlled_host_popen_calls': controlled, 'report': artifact(output)}, ensure_ascii=False))
    return 0 if success else 1


if __name__ == '__main__':
    raise SystemExit(main())
