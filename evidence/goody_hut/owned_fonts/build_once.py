"""Build one source-sealed x64 candidate after checking its real Lua catalog."""
from pathlib import Path
from datetime import datetime, timezone
import contextlib
import ctypes
import hashlib
import io
import json
import os
import re
import runpy
import shlex
import stat
import subprocess
import sys

STAGE = Path(__file__).absolute().parent
PROJECT = STAGE.parents[2]
SCOPE = STAGE / 'build_scope.json'
STARTED = STAGE / 'build_started.json'
OUTPUT = STAGE / 'build_run.json'
RETAIL = os.path.normcase(os.path.abspath(r"C:\Users\home\OneDrive\Documents\My Games\Sid Meier's Civilization 5"))


def norm(path):
    return os.path.normcase(os.path.abspath(path))


def ref(path):
    path = Path(path)
    assert path.is_absolute() and path.resolve(strict=True) == path, str(path)
    before = path.stat()
    assert stat.S_ISREG(before.st_mode) and not before.st_file_attributes & 0x400
    with path.open('rb') as stream:
        sha = hashlib.file_digest(stream, 'sha256').hexdigest()
    after = path.stat()
    assert (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    return dict(path=str(path), bytes=after.st_size, sha256=sha)


def sealed(row):
    current = ref(row['path'])
    assert current['sha256'] == row['sha256'] and ('bytes' not in row or current['bytes'] == row['bytes']), row['path']
    return current


def write(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def main():
    assert not sys.flags.optimize and sys.dont_write_bytecode
    assert not STARTED.exists() and not OUTPUT.exists(), 'Single-use attempt; inspect the existing handle and receipt'
    scope_ref = ref(SCOPE)
    scope = json.loads(SCOPE.read_bytes())
    assert scope['schema'] == 'zerosis.goody_hut.shared_font_link_scope.v1'
    assert scope['compile_link_allowed'] and scope['retail_mod_test_hold_active']
    assert not any(scope[name] for name in ('host_gamecore_hwnd_execution_allowed', 'retail_user_state_or_game_process_access_allowed', 'default_promotion_allowed', 'full_engine_goal_complete'))
    assert ref(__file__) == scope['build_wrapper']
    for name in ('source_seal', 'source_conformance', 'baseline_build', 'baseline_generated_header', 'pure_lua_provider', 'catalog_checker', 'storage_prebuild'):
        sealed(scope[name])
    source = json.loads(Path(scope['source_seal']['path']).read_bytes())
    preservation = json.loads(Path(scope['frozen_preservation']['path']).read_bytes())
    protected = {norm(row['path']): row for row in preservation['artifacts']}
    extra = [*source['production_sources'].values(), *source['new_assets_and_tests'].values(), *scope['scene_addenda'].values(),
             *scope['build_tool_seals'], *scope['original_goody_assets'].values(), *scope['original_pantheon_assets'].values(),
             scope['source_seal'], scope['source_conformance'], scope['baseline_build'], scope['baseline_generated_header'],
             scope['pure_lua_provider'], scope['catalog_checker'], scope['storage_prebuild'], scope['frozen_preservation'],
             scope['progress_before'], scope['build_wrapper'], scope['catalog_parser_helper'], scope['script_loader'],
             *scope['source_backup_refs'], scope['font_catalog_scope'], *scope['font_original_inputs'], scope_ref]
    for row in extra:
        current = sealed(row)
        key = norm(row['path'])
        assert key not in protected or protected[key] == current
        protected[key] = current
    baseline = [sealed(row) for row in protected.values()]
    ids = {(Path(row['path']).stat().st_dev, Path(row['path']).stat().st_ino) for row in baseline}
    for row in scope['mutable_derived_before']:
        sealed(row)
        info = Path(row['path']).stat()
        assert info.st_nlink == 1 and (info.st_dev, info.st_ino) not in ids, 'Derived output shares a preserved file identity'
    before_builds = {path.name for path in (PROJECT / 'Build/UiWindowHost').iterdir() if path.is_dir()}
    before_reports = {path.name for path in (PROJECT / 'evidence/ui_window_host').iterdir() if path.is_dir()}
    assert before_builds == set(scope['build_identifiers_before']) and before_reports == set(scope['evidence_identifiers_before'])
    base = json.loads(Path(scope['baseline_build']['path']).read_bytes())
    binaries = {norm(base[name]['path']): base[name]['sha256'] for name in ('compiler', 'linker', 'dumpbin')}
    for path, sha in binaries.items():
        assert ref(path)['sha256'] == sha
    compiler, linker = norm(base['compiler']['path']), norm(base['linker']['path'])
    preparer = PROJECT / 'tools/prepare_ui_popup_assets.py'
    checker = Path(scope['catalog_checker']['path'])
    provider = Path(scope['pure_lua_provider']['path'])
    prepare_command = [sys.executable, '-B', '-X', 'utf8', str(preparer)]
    catalog_path = STAGE / 'catalog.json'
    catalog_command = [sys.executable, '-B', '-X', 'utf8', str(checker), '--scope', scope['font_catalog_scope']['path'], '--output', str(catalog_path)]
    state = dict(catalog_verified=False, preparations=0, catalog_preflights=0)
    processes, loads, denied, objects, link_snapshot = [], [], [], {}, {}
    original_run = subprocess.run
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetCurrentProcess.restype = ctypes.c_void_p
    kernel.SetPriorityClass.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    assert kernel.SetPriorityClass(kernel.GetCurrentProcess(), 0x4000), 'Cannot lower this builder priority'

    def audit(event, arguments):
        if event in ('open', 'os.listdir', 'os.scandir') and arguments and isinstance(arguments[0], (str, bytes, os.PathLike)):
            target = norm(os.fsdecode(arguments[0])).removeprefix('\\\\?\\')
            if target == RETAIL or target.startswith(RETAIL + os.sep):
                denied.append(event)
                raise RuntimeError('Retail user state is outside this build')
        if event == 'subprocess.Popen':
            command = arguments[1]
            words = [str(value) for value in command] if isinstance(command, (list, tuple)) else shlex.split(command, posix=False)
            words = [word[1:-1] if len(word) >= 2 and word[0] == word[-1] == '"' else word for word in words]
            executable = arguments[0] or words[0].strip('"')
            key, name = norm(executable), Path(executable).name.lower()
            if key == norm(sys.executable):
                assert words in (prepare_command, catalog_command), 'Python child differs from the exact approved command'
                assert arguments[2] and norm(arguments[2]) == norm(PROJECT)
            elif name == 'cmd.exe':
                assert state['catalog_verified'] and arguments[2]
                directory = Path(arguments[2])
                assert directory.is_absolute() and directory.parent == PROJECT / 'Build/UiWindowHost'
                assert directory.name not in before_builds
                setup = directory / 'read_build_environment.cmd'
                assert words == ['cmd.exe', '/d', '/c', str(setup)], 'Compiler environment command differs'
                assert setup.resolve(strict=True) == setup and setup.is_file()
            elif key in binaries:
                assert state['catalog_verified'] and ref(key)['sha256'] == binaries[key]
            else:
                denied.append(str(executable))
                raise RuntimeError('Non-builder child process denied')
            processes.append(dict(executable=str(executable), cwd=str(arguments[2])))
        if event == 'ctypes.dlopen':
            if norm(str(arguments[0])) == norm(provider):
                sealed(scope['pure_lua_provider'])
                loads.append(str(arguments[0]))
            elif str(arguments[0]).lower() not in ('kernel32', 'kernel32.dll'):
                denied.append(str(arguments[0]))
                raise RuntimeError('Only the sealed pure Lua provider is allowed')
        if event in ('os.startfile', 'os.startfile/2', 'os.system', 'os.exec', 'os.posix_spawn'):
            denied.append(event)
            raise RuntimeError('Game and shell control denied')

    def checked_run(command, *arguments, **options):
        words = [str(value) for value in command]
        is_preparer = words == [sys.executable, '-B', '-X', 'utf8', str(preparer)]
        program = norm(words[0])
        is_compile = program == compiler and len(words) == 2 and words[1].startswith('@')
        is_link = program == linker
        if is_link:
            assert not link_snapshot and len(words) == 2 and words[1].startswith('@')
            response = Path(words[1][1:])
            object_paths = [Path(line.strip('"')) for line in response.read_text(encoding='utf-8-sig').splitlines() if line.strip('"').lower().endswith('.obj')]
            final = {key: value for key, value in objects.items() if value['phase'] == 'final'}
            assert len(objects) == 10 and len(final) == len(object_paths) == 5 and {norm(path) for path in object_paths} == set(final)
            for path in object_paths:
                assert ref(path) == final[norm(path)]['object']
            link_snapshot.update(response=ref(response), objects_before=[ref(path) for path in object_paths])
        result = original_run(command, *arguments, **options)
        if is_compile and result.returncode == 0:
            response = Path(words[1][1:])
            lines = response.read_text(encoding='utf-8-sig').splitlines()
            assert '/W4' in lines and '/WX' in lines
            outputs = [Path(line[3:].strip('"')) for line in lines if line.startswith('/Fo')]
            sources = [Path(line.strip('"')) for line in lines if line.strip('"').lower().endswith('.cpp')]
            assert len(outputs) == len(sources) == 1
            folder = outputs[0]
            assert folder.is_relative_to(PROJECT / 'Build/UiWindowHost') and folder.name == 'obj'
            assert re.fullmatch(r'tu_[0-9]{2}_(host_main|window|renderer|world_renderer|terrain_renderer)', folder.parent.name)
            assert folder.parent.parent.name in ('dependency_discovery', 'final')
            path = folder / (sources[0].stem + '.obj')
            with path.open('rb') as stream:
                assert stream.read(2) == b'\x64\x86', 'Actual object is not AMD64 COFF'
            key = norm(path)
            assert key not in objects
            objects[key] = dict(object=ref(path), response=ref(response), phase=folder.parent.parent.name, translation_unit=folder.parent.name, returncode=result.returncode)
        if is_link:
            link_snapshot.update(returncode=result.returncode, objects_after=[ref(path) for path in object_paths])
            assert link_snapshot['objects_after'] == link_snapshot['objects_before'] and ref(response) == link_snapshot['response']
        if is_preparer:
            state['preparations'] += 1
            assert state['preparations'] == 1
            if result.returncode == 0:
                for row in baseline:
                    sealed(row)
                check = original_run(catalog_command, cwd=PROJECT, capture_output=True, timeout=240, creationflags=subprocess.CREATE_NO_WINDOW)
                write(STAGE / 'catalog_process.json', dict(returncode=check.returncode, stdout=check.stdout.decode('utf-8', errors='replace')[-3000:], stderr=check.stderr.decode('utf-8', errors='replace')[-5000:]))
                state['catalog_preflights'] += 1
                assert check.returncode == 0, 'Actual packaged Lua catalog failed before compilation'
                proof = json.loads(catalog_path.read_bytes())
                assert proof['status'] == scope['expected_catalog_status'] and proof['inputs_unchanged'] and proof['failed_count'] == 0 and proof['catalog_count'] == proof['parsed_count'] == scope['expected_catalog_count'] == 67
                checked_header = ref(scope['generated_header']['path'])
                assert proof['generated_header'] == checked_header, 'Catalog proof did not bind the actual generated header'
                baseline.extend((checked_header, ref(catalog_path)))
                state['checked_header'] = checked_header
                state['catalog_verified'] = True
        return result

    sys.addaudithook(audit)
    write(STARTED, dict(schema='zerosis.goody_hut.actual_build_started.v1', utc=datetime.now(timezone.utc).isoformat(), scope=scope_ref, builder_priority='BELOW_NORMAL_OWN_PROCESS_ONLY', live_handle_required_for_wait=True))
    subprocess.run = checked_run
    captured, error, result = io.StringIO(), None, None
    old_argv = sys.argv
    try:
        sys.path.insert(0, str(PROJECT / 'tools'))
        sys.argv = [str(PROJECT / 'tools/build_ui_window_host.py'), '--reuse-frozen-build', scope['baseline_build_id']]
        with contextlib.redirect_stdout(captured):
            namespace = runpy.run_path(sys.argv[0], run_name='goody_actual_builder')
            result = namespace['main']()
        assert result == 0 and state['catalog_verified'] and len(objects) == 10 and link_snapshot['returncode'] == 0
    except BaseException as failure:
        error = repr(failure)
    finally:
        sys.argv = old_argv
        subprocess.run = original_run
    after = [ref(row['path']) for row in baseline]
    assert after == baseline, 'Protected inputs changed during the real build'
    builds = sorted(path.name for path in (PROJECT / 'Build/UiWindowHost').iterdir() if path.is_dir() and path.name not in before_builds)
    reports = sorted(path.name for path in (PROJECT / 'evidence/ui_window_host').iterdir() if path.is_dir() and path.name not in before_reports)
    success = error is None and result == 0 and len(builds) == len(reports) == 1 and builds == reports and not denied
    checked_compiler_header = None
    if success:
        try:
            built = json.loads((PROJECT / 'evidence/ui_window_host' / builds[0] / 'build_result.json').read_bytes())
            assert built['status'] == 'UI_WINDOW_HOST_CANDIDATE_BUILT' and built['build_id'] == builds[0]
            headers = [row for row in built['compiler_inputs'] if row['relative_path'].replace('\\', '/') == 'Source/Host/UiPopupAssets.generated.h']
            assert len(headers) == 1
            checked_compiler_header = ref(headers[0]['path'])
            assert checked_compiler_header == {key: headers[0][key] for key in ('path', 'bytes', 'sha256')}
            assert all(checked_compiler_header[key] == state['checked_header'][key] for key in ('bytes', 'sha256')), 'Actual compiler input differs from the syntax-checked catalog'
        except BaseException as failure:
            error, success = repr(failure), False
    report = dict(schema='zerosis.goody_hut.actual_build_run.v1', status='PASS' if success else 'FAIL', utc=datetime.now(timezone.utc).isoformat(), scope=scope_ref, result=result, error=error, stdout=captured.getvalue(), processes=processes, pure_lua_dll_loads=loads, forbidden_access_attempts=denied, actual_objects=list(objects.values()), link_snapshot=link_snapshot, checked_compiler_header=checked_compiler_header, catalog_state=state, new_build_ids=builds, new_evidence_ids=reports, protected_count=len(baseline), protected_unchanged=True, actual_builder_subprocess_results_unmodified=True, game_process_queries=0, host_gamecore_hwnd_executed=False, retail_user_state_or_game_processes_accessed=False, default_promoted=False, full_engine_goal_complete=False)
    write(OUTPUT, report)
    print(json.dumps(dict(status=report['status'], build_ids=builds, objects=len(objects), processes=len(processes), error=error, receipt=ref(OUTPUT))))
    return 0 if success else 1


if __name__ == '__main__':
    raise SystemExit(main())
