"""Compile current Host syntax only, reusing the last linked build's flags.

No linker, Host executable, GameCore DLL, UI window or retail user state is used.
The protected generated asset header still lacks the new Pantheon assets.
"""
from pathlib import Path
import ctypes
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import time
import traceback

sys.dont_write_bytecode = True
STAGE = Path(__file__).absolute().parent
PROJECT = STAGE.parent.parent.parent
BASE = PROJECT / 'Build/UiWindowHost/20261016T142908Z_fc2e23c1fd1e/frozen/include_roots'
BASE_REPORT = PROJECT / 'evidence/ui_window_host/20261016T142908Z_fc2e23c1fd1e/build_result.json'
SEAL = STAGE / 'source_inputs_snapshot_fix.json'
OUT = STAGE / 'syntax'
RETAIL = os.path.normcase(os.path.abspath(r"C:\Users\home\OneDrive\Documents\My Games\Sid Meier's Civilization 5"))


def ref(path):
    path = Path(path)
    before = path.stat()
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    after = path.stat()
    assert (before.st_ino, before.st_size, before.st_mtime_ns) == (after.st_ino, after.st_size, after.st_mtime_ns), str(path)
    return dict(path=str(path), bytes=before.st_size, sha256=digest)


def write(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def main():
    assert not OUT.exists(), 'Use one fresh syntax directory'
    OUT.mkdir()
    processes, denied, units = [], [], []
    report = dict(schema='zerosis.pantheon_source.current_host_syntax.v1', status='FAIL',
                  source_seal=ref(SEAL), base_build=ref(BASE_REPORT), verifier=ref(__file__),
                  processes=processes, forbidden_access_attempts=denied, translation_units=units,
                  objects_created=False, linked=False, host_executed=False, gamecore_loaded=False,
                  hwnd_created=False, retail_user_state_accessed=False,
                  generated_assets_updated=False, runnable_pantheon_candidate_verified=False)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.SetErrorMode.argtypes = [ctypes.c_uint]
    kernel.SetErrorMode.restype = ctypes.c_uint
    kernel.SetErrorMode(0x8003)

    def audit(event, args):
        if event in ('open', 'os.listdir', 'os.scandir') and args and isinstance(args[0], (str, bytes, os.PathLike)):
            target = os.path.normcase(os.path.abspath(os.fsdecode(args[0])))
            if target.startswith('\\\\?\\'):
                target = target[4:]
            if target == RETAIL or target.startswith(RETAIL + os.sep):
                denied.append(event)
                raise RuntimeError('Retail hold denied user-state access')
        if event == 'subprocess.Popen':
            command = args[1]
            value = args[0] or (command[0] if isinstance(command, (list, tuple)) else shlex.split(command, posix=False)[0].strip('"'))
            if Path(value).name.lower() not in ('cmd.exe', 'cl.exe'):
                denied.append(str(value))
                raise RuntimeError('Syntax-only process policy denied a non-compiler child')
            processes.append(dict(executable=str(value), cwd=str(args[2])))
        if event in ('os.startfile', 'os.system') or event == 'ctypes.dlopen' and 'gamecore' in str(args).lower():
            denied.append(event)
            raise RuntimeError('Syntax-only native policy denied access')

    sys.addaudithook(audit)
    try:
        sealed = json.loads(SEAL.read_text(encoding='utf-8'))
        for row in [*sealed['sources'].values(), *sealed['protected_before'], *sealed['original_before']]:
            assert ref(row['path']) == row, row['path']
        baseline = json.loads(BASE_REPORT.read_text(encoding='utf-8-sig'))
        assert report['base_build']['sha256'] == 'f1353330edad0c93ed6e8ee42af996f87b052b6920404df3b8411b5ec4895d63'
        assert baseline['status'] == 'UI_WINDOW_HOST_CANDIDATE_BUILT'
        mutable = set(sealed['sources'])
        current, frozen = {}, {}
        for row in baseline['compiler_inputs']:
            observed = ref(row['path'])
            assert observed['bytes'] == row['bytes'] and observed['sha256'] == row['sha256'], row['path']
            frozen[row['path']] = observed
            if row['root_name'] in ('project', 'sdk'):
                live = ref(row['original_path'])
                if live['sha256'] != row['sha256']:
                    relative = Path(row['original_path']).relative_to(PROJECT).as_posix()
                    assert relative in mutable, relative
                current[row['original_path']] = live
        assert len(current) == 219
        report['live_cpp_inputs_before'] = list(current.values())
        report['frozen_baseline_inputs_verified'] = len(frozen)
        sys.path.insert(0, str(PROJECT / 'tools'))
        from native_build import environment_for
        env, compiler = environment_for(Path(r'C:\Program Files\Microsoft Visual Studio\2022\Community'), 'x64', OUT / 'environment')
        compiler_ref = ref(compiler)
        assert compiler_ref['sha256'] == baseline['compiler']['sha256']
        report['compiler'] = compiler_ref
        all_inputs = set()
        for unit in baseline['final_compilation']['translation_units']:
            name = unit['translation_unit']
            folder = OUT / name
            folder.mkdir()
            original_rsp = Path(unit['response']['path'])
            assert ref(original_rsp)['sha256'] == unit['response']['sha256']
            dependencies, response = folder / 'dependencies.json', folder / 'syntax.rsp'
            lines = []
            for line in original_rsp.read_text(encoding='utf-8-sig').splitlines():
                if line in ('/c', '/O2') or line.startswith(('/Fo', '/sourceDependencies')):
                    continue
                line = line.replace(str(BASE / 'project'), str(PROJECT))
                line = line.replace(str(BASE / 'sdk'), str(PROJECT / 'Source/SDK_BNW_x64'))
                lines.append(line)
            lines.extend(['/Zs', f'/sourceDependencies "{dependencies}"'])
            response.write_text('\n'.join(lines) + '\n', encoding='utf-8')
            started = time.monotonic()
            result = subprocess.run([compiler, '@' + str(response)], cwd=folder, env=env,
                                    capture_output=True, timeout=180, creationflags=subprocess.CREATE_NO_WINDOW)
            transcript = (result.stdout + result.stderr).decode('mbcs', errors='replace')
            log = folder / 'compile.log'
            log.write_bytes(result.stdout + result.stderr)
            item = dict(translation_unit=name, returncode=result.returncode,
                        elapsed_seconds=round(time.monotonic() - started, 6),
                        response=ref(response), base_response=ref(original_rsp), log=ref(log))
            units.append(item)
            assert result.returncode == 0 and not re.search(r'\bwarning\s+[A-Z]?\d+', transcript, re.I), transcript[-3000:]
            data = json.loads(dependencies.read_text(encoding='utf-8-sig'))['Data']
            inputs = [Path(data['Source']), *(Path(path) for path in data['Includes'])]
            assert Path(data['Source']).is_relative_to(PROJECT / 'Source')
            assert all(not path.is_relative_to(BASE / 'project') and not path.is_relative_to(BASE / 'sdk') for path in inputs)
            refs = [ref(path) for path in inputs]
            item.update(dependencies=ref(dependencies), consumed_inputs=refs)
            all_inputs.update(row['path'] for row in refs)
            assert not list(folder.glob('*.obj')) and not list(folder.glob('*.exe'))
        assert len(units) == 5 and not denied
        assert {path: ref(path) for path in current} == current
        assert {path: ref(path) for path in frozen} == frozen
        assert ref(compiler) == compiler_ref
        for row in [*sealed['sources'].values(), *sealed['protected_before'], *sealed['original_before']]:
            assert ref(row['path']) == row
        report.update(status='PASS_CURRENT_HOST_SYNTAX_ONLY', unique_consumed_inputs=len(all_inputs),
                      live_cpp_inputs_unchanged=True, protected_artifacts_unchanged=True,
                      frozen_baseline_inputs_unchanged=True, compiler_unchanged=True)
    except BaseException:
        report['error'] = traceback.format_exc()
    write(OUT / 'result.json', report)
    print(json.dumps(dict(status=report['status'], units=len(units), processes=len(processes),
                          evidence=ref(OUT / 'result.json'), error=report.get('error', '')[-3000:])))
    return 0 if report['status'] == 'PASS_CURRENT_HOST_SYNTAX_ONLY' else 1


if __name__ == '__main__':
    raise SystemExit(main())
