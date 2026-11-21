"""Run one separately scoped retry without replacing the preserved first attempt.

The existing builder still executes its actual preparer, compiler and linker.
The subprocess wrapper checks the newly prepared Lua catalog before returning
the real preparer's unchanged result to the builder. No build result is mocked.
"""
from pathlib import Path
import contextlib
import ctypes
import hashlib
import io
import json
import os
import re
import runpy
import shlex
import subprocess
import sys
import traceback

sys.dont_write_bytecode = True
ATTEMPT = 'retry_02'
STAGE = Path(__file__).absolute().parent
PROJECT = STAGE.parent.parent.parent
SCOPE_SHA = '747c8710329e4b2a3a3905dc90b88ce9b9e2f106a0eed0c9ac918f35e6c0f99a'
RETAIL = os.path.normcase(os.path.abspath(r"C:\Users\home\OneDrive\Documents\My Games\Sid Meier's Civilization 5"))


def ref(path):
    path = Path(path)
    before = path.stat()
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    after = path.stat()
    assert (before.st_ino, before.st_size, before.st_mtime_ns) == (after.st_ino, after.st_size, after.st_mtime_ns), str(path)
    return dict(path=str(path), bytes=after.st_size, sha256=digest)


def norm(path):
    return os.path.normcase(os.path.abspath(path))


def write(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def main():
    if sys.flags.optimize != 0:
        raise RuntimeError('This policy wrapper requires Python optimization level zero')
    output = STAGE / 'build_retry_02_run.json'
    started = STAGE / 'build_retry_02_started.json'
    assert not output.exists() and not started.exists(), 'This build wrapper is single-use'
    scope_ref = ref(STAGE / 'scope.json')
    assert scope_ref['sha256'] == SCOPE_SHA
    scope = json.loads((STAGE / 'scope.json').read_text(encoding='utf-8'))
    extension_path = STAGE / 'retry_02_scope.json'
    extension = json.loads(extension_path.read_text(encoding='utf-8'))
    assert ref(__file__) == extension['root_build_wrapper']
    checker = Path(extension['checker']['path'])
    assert checker.parent == STAGE and ref(checker) == extension['checker']
    assert extension['parent_scope'] == scope_ref
    assert extension['schema'] == 'zerosis.pantheon_link.catalog_preflight_scope.v1'
    assert extension['retry_manifest_schema'] == 'zerosis.pantheon_link.retry_manifest.v1'
    assert extension['retry_attempt'] == ATTEMPT
    assert extension['python_optimization_level_required'] == 0
    assert extension['retail_mod_test_hold_active'] is True
    assert extension['native_game_Host_GameCore_HWND_execution_allowed'] is False
    assert extension['retail_user_state_or_game_process_access_allowed'] is False
    assert extension['full_project_copies_created'] == 0
    assert extension['own_builder_priority'] == 'BELOW_NORMAL_PRIORITY_CLASS'
    assert extension['intended_affinity'] == 'UNCHANGED'
    assert extension['game_process_queries_allowed'] is False
    assert extension['game_process_priority_or_affinity_changes_allowed'] is False
    expected_outputs = dict(started=str(started), run=str(output),
                            catalog=str(STAGE / 'catalog_retry_02.json'),
                            catalog_stdout=str(STAGE / 'catalog_retry_02.stdout.log'),
                            catalog_stderr=str(STAGE / 'catalog_retry_02.stderr.log'))
    assert extension['output_paths'] == expected_outputs
    assert all(not os.path.lexists(path) for path in expected_outputs.values())
    original_wrapper = ref(STAGE / 'build_once.py')
    assert original_wrapper == extension['source_build_wrapper']
    assert original_wrapper['sha256'] == '3dbb55e24d89ebaa0a27abf9304b5a620dcfb08a0227838a248f97431dd610db'
    expected_prior = [original_wrapper, extension['prior_catalog_preflight_scope'],
                      extension['prior_build_started'], extension['prior_build_run'],
                      extension['prior_catalog_syntax'], extension['prior_catalog_stdout'],
                      extension['prior_catalog_stderr'], extension['prior_checker_backup'],
                      extension['checker_repair_evidence']]
    assert extension['prior_attempt_artifacts'] == expected_prior
    assert extension['repair_artifacts'] == [extension['prior_checker_backup'],
                                             extension['checker_repair_evidence'],
                                             extension['checker_repair_validation']]
    for row in [*expected_prior, *extension['repair_artifacts']]:
        assert ref(row['path']) == row, row['path']
    prior_extension = json.loads(Path(extension['prior_catalog_preflight_scope']['path']).read_text(encoding='utf-8-sig'))
    assert prior_extension['parent_scope'] == scope_ref
    assert prior_extension['root_build_wrapper'] == original_wrapper
    assert extension['additional_protected_artifacts'] == prior_extension['additional_protected_artifacts']
    assert len(extension['additional_protected_artifacts']) == 14
    old_checker, backup = prior_extension['checker'], extension['prior_checker_backup']
    assert (old_checker['bytes'], old_checker['sha256']) == (backup['bytes'], backup['sha256'])
    prior = json.loads(Path(extension['prior_build_run']['path']).read_text(encoding='utf-8-sig'))
    failure = extension['prior_failure']
    assert prior['status'] == failure['status'] == 'FAIL'
    assert len(prior['processes']) == failure['process_count'] == 2
    assert prior['new_build_ids'] == failure['new_build_ids'] == []
    assert prior['new_evidence_ids'] == failure['new_evidence_ids'] == []
    assert prior['state'] == dict(preparations=1, catalog_preflights=1, catalog_verified=False)
    assert prior['compiled_objects'] == {} and prior['actual_link_snapshot'] == {}
    assert all(norm(row['executable']) == norm(sys.executable) for row in prior['processes'])
    assert prior['forbidden_access_attempts'] == []
    prior_catalog = json.loads(Path(extension['prior_catalog_syntax']['path']).read_text(encoding='utf-8-sig'))
    assert prior_catalog['status'] == 'FAILED_INPUT_PRESERVATION_OR_GUARD'
    assert prior_catalog['scripts_executed'] is False
    repaired = json.loads(Path(extension['checker_repair_validation']['path']).read_text(encoding='utf-8-sig'))
    assert repaired['status'] == extension['expected_status']
    assert repaired['inputs_unchanged'] is True and repaired['failed_count'] == 0
    assert repaired['scripts_executed'] is False
    assert {norm(row['path']) for row in extension['mutable_derived_before_retry']} == {norm(path) for path in scope['mutable_derived_paths']}
    assert {norm(row['path']) for row in extension['new_source_snapshots_before_retry']} == {norm(path) for path in scope['new_source_snapshots']}
    for row in [*extension['mutable_derived_before_retry'], *extension['new_source_snapshots_before_retry']]:
        assert ref(row['path']) == row, row['path']
    protected = [*scope['all_source_and_test_seals'].values(), *scope['protected_artifacts'],
                 *scope['original_assets'], *extension['additional_protected_artifacts'],
                 *extension['new_source_snapshots_before_retry'],
                 *extension['prior_attempt_artifacts'], *extension['repair_artifacts']]
    for row in protected:
        assert ref(row['path']) == row, row['path']
    previous = extension['previous_failed_attempt']
    assert previous['attempt'] == 'retry_01'
    for row in previous['artifacts']:
        assert ref(row['path']) == row, row['path']
    previous_run = json.loads(Path(previous['run']['path']).read_text(encoding='utf-8-sig'))
    previous_build = json.loads(Path(previous['build_report']['path']).read_text(encoding='utf-8-sig'))
    assert previous_run['status'] == 'FAIL'
    assert previous_run['new_build_ids'] == previous_run['new_evidence_ids'] == [previous['failed_build_id']]
    assert previous_run['state'] == dict(preparations=1, catalog_preflights=1, catalog_verified=True)
    assert previous_run['compiled_objects'] == {} and previous_run['actual_link_snapshot'] == {}
    assert previous_run['forbidden_access_attempts'] == [] and len(previous_run['processes']) == 2
    assert previous_build['status'] == 'UI_WINDOW_HOST_BUILD_FAILED' and previous_build['executable'] is None
    assert 'WinError 5' in previous_build['error'] and 'HostMain.cpp' in previous_build['error']
    assert set(extension['observed_build_identifiers_before']) == set(scope['build_identifiers_before']) | {previous['failed_build_id']}
    assert set(extension['observed_evidence_identifiers_before']) == set(scope['evidence_identifiers_before']) | {previous['failed_build_id']}
    assert {q.name for q in (PROJECT / 'Build/UiWindowHost').iterdir() if q.is_dir()} == set(extension['observed_build_identifiers_before'])
    assert {q.name for q in (PROJECT / 'evidence/ui_window_host').iterdir() if q.is_dir()} == set(extension['observed_evidence_identifiers_before'])
    for name, expected in [('sandbox_denied', 'HARDLINK_DENIED'), ('approved_allowed', 'HARDLINK_ALLOWED')]:
        row = extension['hardlink_permission_probes'][name]
        assert ref(row['path']) == row
        probe = json.loads(Path(row['path']).read_text(encoding='utf-8'))
        assert probe['status'] == expected and probe['temporary_files_removed'] is True
    protected.extend([*previous['artifacts'], *extension['hardlink_permission_probes'].values()])
    baseline = json.loads(Path(scope['base_build']['path']).read_text(encoding='utf-8-sig'))
    compiler_key, linker_key = norm(baseline['compiler']['path']), norm(baseline['linker']['path'])
    binaries = {norm(Path(baseline[key]['path'])): baseline[key]['sha256'] for key in ('compiler', 'linker', 'dumpbin')}
    for binary, expected in binaries.items():
        assert ref(binary)['sha256'] == expected
    lua_path = scope['headless_lua_provider']['path']
    assert ref(lua_path) == scope['headless_lua_provider']
    preparer = PROJECT / 'tools/prepare_ui_popup_assets.py'
    original_run = subprocess.run
    captured, processes, loads, denied = io.StringIO(), [], [], []
    state = dict(preparations=0, catalog_preflights=0, catalog_verified=False)
    compiled_objects, link_snapshot = {}, {}
    stems = dict(host_main='HostMain', window='BitmapWindow', renderer='BitmapRenderer',
                 world_renderer='WorldViewRenderer', terrain_renderer='WorldTerrainRenderer')
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.SetErrorMode.argtypes = [ctypes.c_uint]
    kernel.SetErrorMode.restype = ctypes.c_uint
    kernel.SetErrorMode(0x8003)
    kernel.GetCurrentProcess.argtypes = []
    kernel.GetCurrentProcess.restype = ctypes.c_void_p
    kernel.SetPriorityClass.argtypes = [ctypes.c_void_p, ctypes.c_uint]
    kernel.SetPriorityClass.restype = ctypes.c_int
    own_process = kernel.GetCurrentProcess()
    if not kernel.SetPriorityClass(own_process, 0x4000):
        raise RuntimeError('Could not set own builder BELOW_NORMAL_PRIORITY_CLASS; Win32 error=' +
                           str(ctypes.get_last_error()))
    own_priority = dict(requested='BELOW_NORMAL_PRIORITY_CLASS', applied=True,
                        target='GetCurrentProcess pseudo handle only', affinity_changed=False,
                        game_process_queries=0, game_process_priority_or_affinity_changed=False,
                        child_policy='Inherited unless child creation explicitly overrides priority; no child or game process queried')

    def audit(event, args):
        if event in ('open', 'os.listdir', 'os.scandir') and args and isinstance(args[0], (str, bytes, os.PathLike)):
            target = norm(os.fsdecode(args[0]))
            if target.startswith('\\\\?\\'):
                target = target[4:]
            if target == RETAIL or target.startswith(RETAIL + os.sep):
                denied.append(event)
                raise RuntimeError('Retail mod test hold forbids user-state access')
        if event == 'subprocess.Popen':
            command = args[1]
            executable = args[0] or (command[0] if isinstance(command, (list, tuple)) else shlex.split(command, posix=False)[0].strip('"'))
            key, name = norm(executable), Path(executable).name.lower()
            words = [str(value) for value in command] if isinstance(command, (list, tuple)) else shlex.split(command, posix=False)
            if key == norm(sys.executable):
                assert any(norm(str(path)) == norm(word.strip('"')) for path in (preparer, checker) for word in words if word.strip('"').lower().endswith('.py')), 'Only exact preparer/checker Python children are allowed'
            elif name == 'cmd.exe':
                assert any('read_build_environment.cmd' in word for word in words) and args[2] is not None and Path(args[2]).is_relative_to(PROJECT / 'Build/UiWindowHost'), 'Only the compiler environment command is allowed'
            elif key in binaries:
                assert state['catalog_verified'], 'Catalog must pass before any compiler/toolchain process'
                assert ref(key)['sha256'] == binaries[key]
            else:
                denied.append(str(executable))
                raise RuntimeError('Private build policy denied a non-builder process')
            processes.append(dict(executable=str(executable), cwd=str(args[2])))
        if event == 'ctypes.dlopen':
            path = args[0]
            if norm(str(path)) == norm(lua_path):
                assert ref(lua_path) == scope['headless_lua_provider']
                loads.append(str(path))
            elif str(path).lower() not in ('kernel32', 'kernel32.dll'):
                denied.append(str(path))
                raise RuntimeError('Private build policy permits only the sealed pure Lua DLL')
        if event in ('os.startfile', 'os.system'):
            denied.append(event)
            raise RuntimeError('Game or shell control is outside this build')

    def checked_run(command, *args, **kwargs):
        values = [str(value) for value in command]
        is_preparer = values == [sys.executable, '-B', '-X', 'utf8', str(preparer)]
        program = norm(values[0])
        is_compile = program == compiler_key and len(values) == 2 and values[1].startswith('@')
        is_link = program == linker_key
        if is_link:
            assert not link_snapshot and len(values) == 2 and values[1].startswith('@')
            response = Path(values[1][1:])
            object_paths = [Path(line.strip('"')) for line in response.read_text(encoding='utf-8-sig').splitlines()
                            if line.strip('"').lower().endswith('.obj')]
            final_records = {path: row for path, row in compiled_objects.items() if row['phase'] == 'final'}
            assert len(compiled_objects) == 10 and len(final_records) == 5
            assert len(object_paths) == 5 and {norm(path) for path in object_paths} == set(final_records)
            for path in object_paths:
                assert ref(path) == final_records[norm(path)]['object']
            link_snapshot.update(response=ref(response), objects_before=[ref(path) for path in object_paths])
        result = original_run(command, *args, **kwargs)
        if is_compile and result.returncode == 0:
            response = Path(values[1][1:])
            lines = response.read_text(encoding='utf-8-sig').splitlines()
            outputs = [Path(line[3:].strip('"')) for line in lines if line.startswith('/Fo')]
            assert len(outputs) == 1 and outputs[0].is_relative_to(PROJECT / 'Build/UiWindowHost')
            folder = outputs[0]
            match = re.fullmatch(r'tu_[0-9]{2}_(host_main|window|renderer|world_renderer|terrain_renderer)', folder.parent.name)
            assert match and folder.name == 'obj' and folder.parent.parent.name in ('dependency_discovery', 'final')
            role = match.group(1)
            path = folder / (stems[role] + '.obj')
            key = norm(path)
            assert key not in compiled_objects
            compiled_objects[key] = dict(object=ref(path), response=ref(response),
                                         phase=folder.parent.parent.name, translation_unit=role, returncode=result.returncode)
        if is_link:
            link_snapshot.update(returncode=result.returncode, objects_after=[ref(path) for path in object_paths])
            assert link_snapshot['objects_after'] == link_snapshot['objects_before']
            assert ref(response) == link_snapshot['response']
        if is_preparer:
            state['preparations'] += 1
            assert state['preparations'] == 1
            if result.returncode == 0:
                assert ref(checker) == extension['checker']
                for row in protected:
                    assert ref(row['path']) == row, row['path']
                check_command = [sys.executable, '-B', '-X', 'utf8', str(checker), '--output', str(STAGE / 'catalog_retry_02.json')]
                check = original_run(check_command, cwd=PROJECT, capture_output=True, timeout=180,
                                     creationflags=subprocess.CREATE_NO_WINDOW)
                (STAGE / 'catalog_retry_02.stdout.log').write_bytes(check.stdout)
                (STAGE / 'catalog_retry_02.stderr.log').write_bytes(check.stderr)
                state['catalog_preflights'] += 1
                assert check.returncode == 0, 'Packaged Lua preflight failed: ' + check.stderr.decode('utf-8', errors='replace')[-3000:]
                proof = json.loads((STAGE / 'catalog_retry_02.json').read_text(encoding='utf-8-sig'))
                assert proof['status'] == extension['expected_status']
                assert proof['inputs_unchanged'] is True and proof['failed_count'] == 0
                state['catalog_verified'] = True
        return result

    write(started, dict(schema='zerosis.pantheon_link.actual_build_started.v1',
                        retry_attempt=ATTEMPT, prior_build_run=extension['prior_build_run'],
                        previous_failed_attempt=extension['previous_failed_attempt'],
                        own_builder_priority=own_priority,
                        scope=scope_ref, catalog_preflight_scope=ref(extension_path),
                        wrapper=ref(__file__), pid=os.getpid(),
                        note='Exclusive attempt marker only; a live process/tool handle is still required to prove a verified wait.'))
    sys.addaudithook(audit)
    subprocess.run = checked_run
    error = None
    sys.path.insert(0, str(PROJECT / 'tools'))
    sys.argv = [str(PROJECT / 'tools/build_ui_window_host.py'), '--reuse-frozen-build', scope['base_build_id']]
    try:
        with contextlib.redirect_stdout(captured):
            try:
                runpy.run_path(sys.argv[0], run_name='__main__')
            except SystemExit as stop:
                assert stop.code in (None, 0), 'Actual builder exited unsuccessfully: ' + str(stop.code)
        assert state == dict(preparations=1, catalog_preflights=1, catalog_verified=True)
        assert len(compiled_objects) == 10 and link_snapshot['returncode'] == 0
        assert all(ref(row['object']['path']) == row['object'] for row in compiled_objects.values())
        assert len(loads) == 1 and not denied
        for row in protected:
            assert ref(row['path']) == row, row['path']
        assert ref(__file__) == extension['root_build_wrapper']
    except BaseException:
        error = traceback.format_exc()
    finally:
        subprocess.run = original_run
    build_dirs = [q.name for q in (PROJECT / 'Build/UiWindowHost').iterdir()
                  if q.is_dir() and q.name not in extension['observed_build_identifiers_before']]
    evidence_dirs = [q.name for q in (PROJECT / 'evidence/ui_window_host').iterdir()
                     if q.is_dir() and q.name not in extension['observed_evidence_identifiers_before']]
    report = dict(schema='zerosis.pantheon_link.actual_build_run.v1', status='FAIL' if error else 'PASS',
                  scope=scope_ref, catalog_preflight_scope=ref(extension_path), wrapper=ref(__file__),
                  retry_attempt=ATTEMPT, prior_build_run=extension['prior_build_run'],
                  previous_failed_attempt=extension['previous_failed_attempt'],
                  own_builder_priority=own_priority,
                  prior_failure=extension['prior_failure'],
                  mutable_derived_before_retry=extension['mutable_derived_before_retry'],
                  new_source_snapshots_before_retry=extension['new_source_snapshots_before_retry'],
                  stdout=captured.getvalue(), error=error, processes=processes, pure_lua_dll_loads=loads,
                  forbidden_access_attempts=denied, state=state, new_build_ids=build_dirs,
                  new_evidence_ids=evidence_dirs, actual_builder_subprocess_results_unmodified=True,
                  compiled_objects=compiled_objects, actual_link_snapshot=link_snapshot,
                  python_optimization_level=sys.flags.optimize,
                  host_executed=False, gamecore_loaded=False, hwnd_created=False,
                  retail_user_state_or_game_processes_accessed=False, default_promoted=False)
    write(output, report)
    print(json.dumps(dict(status=report['status'], new_build_ids=build_dirs, processes=len(processes),
                          evidence=ref(output), stdout=captured.getvalue()[-1700:], error=(error or '')[-3000:])))
    return 1 if error else 0


if __name__ == '__main__':
    raise SystemExit(main())
