"""Compile and run the pure CPU check of OriginalTerrainBicubicRetail.h (C++14, /W4 /WX /fp:strict /MT).

The executable imports KERNEL32 only; no Host, SDK, CLR, window, GPU, audio device or game is used.
Temporary build outputs are recorded (file id, size, SHA-256) and removed; the result JSON stays.
usage: python -B -X utf8 run_bicubic_cpu_check.py ATTEMPT   (two digits, a new attempt each time)
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).absolute().parent
PROJECT = HERE.parents[2]
sys.path[:0] = [str(PROJECT / 'tools')]
from native_build import environment_for, run   # read-only reuse of the project's compiler lookup


def artifact(path):
    path = Path(path)
    stat = path.stat()
    return dict(path=str(path), bytes=stat.st_size, sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                file_identity=[stat.st_dev, stat.st_ino], mtime_ns=stat.st_mtime_ns, links=stat.st_nlink)


def write_new(path, value):
    with path.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=1)
        stream.write('\n')


def main(attempt):
    assert re.fullmatch('[0-9]{2}', attempt)
    out = HERE / ('bicubic_cpu_attempt' + attempt)
    assert not out.exists(), 'Inspect the earlier attempt; use a new attempt number'
    out.mkdir()
    work = out / 'work'
    work.mkdir()
    inputs = [artifact(HERE / name) for name in ('OriginalTerrainBicubicRetail.h', 'original_terrain_bicubic_retail_test.cpp',
                                                 'run_bicubic_cpu_check.py')]
    assert not any(os.environ.get(name) for name in ('CL', '_CL_', 'LINK'))
    environment, compiler = environment_for(Path(r'C:/Program Files/Microsoft Visual Studio/2022/Community'), 'x64', work)
    modes = []
    for mode, flag in (('optimized', '/O2'), ('unoptimized', '/Od')):
        exe = work / ('bicubic_retail_' + mode + '.exe')
        rsp = exe.with_suffix('.rsp')
        flags = ['/nologo', '/std:c++14', '/EHsc', '/W4', '/WX', flag, '/fp:strict', '/MT', '/I"' + str(HERE) + '"',
                 '"' + str(HERE / 'original_terrain_bicubic_retail_test.cpp') + '"',
                 '/Fo"' + str(exe.with_suffix('.obj')) + '"', '/Fe"' + str(exe) + '"']
        links = ['/INCREMENTAL:NO', '/Brepro', '/WX', '/OPT:REF', '/OPT:ICF', '/MACHINE:X64']
        with rsp.open('x', encoding='utf8') as stream:
            stream.write('\n'.join(flags) + '\n')
        compiled = run([compiler, '@' + str(rsp), '/link', *links], cwd=work, env=environment, timeout=120)
        text = (compiled.stdout + compiled.stderr).decode('mbcs', errors='replace')
        log = out / ('compile_' + mode + '.txt')
        with log.open('x', encoding='utf8') as stream:
            stream.write(text)
        assert compiled.returncode == 0 and not re.search(r'\bwarning\s+[A-Z]+\d+|경고\s+[A-Z]+\d+', text, re.I), 'Build failed: ' + str(log)
        imported = run([Path(compiler).with_name('dumpbin.exe'), '/dependents', exe], cwd=work, env=environment, timeout=30)
        assert imported.returncode == 0
        libraries = sorted(set(re.findall(r'^\s+([A-Za-z0-9_.-]+\.dll)\s*$', imported.stdout.decode('mbcs', errors='replace'), re.M)))
        assert {name.lower() for name in libraries} == {'kernel32.dll'}, libraries
        executed = run([exe], cwd=work, env=environment, timeout=60)
        stdout, stderr = executed.stdout.decode('ascii'), executed.stderr.decode('ascii')
        match = re.fullmatch(r'PASS_TERRAIN_BICUBIC_RETAIL checks=(\d+) surface_samples=(\d+) max_surface_error=([0-9.eE+-]+) '
                             r'basis=retail_exe_literals runtime_executed=0\s*', stdout)
        assert executed.returncode == 0 and not stderr and match, 'Checks failed: ' + stdout + stderr
        modes.append(dict(mode=mode, flags=flags + ['/link'] + links, compiler=artifact(compiler), executable=artifact(exe),
                          imported_dlls=libraries, stdout=stdout.strip(), checks=int(match.group(1)),
                          surface_samples=int(match.group(2)), max_surface_error=float(match.group(3)), warnings=0))
    assert modes[0]['checks'] == modes[1]['checks']
    removed = []
    for path in sorted(work.iterdir()):
        assert path.is_file() and not path.is_symlink() and path.parent == work
        entry = artifact(path)
        assert entry['links'] == 1
        path.unlink()
        entry['removed'] = not path.exists()
        removed.append(entry)
    work.rmdir()
    write_new(out / 'result.json', dict(
        schema='zerosis.world_terrain_original.claude_geometry.bicubic_cpu_check.v1', status='PASS_CPU_COMPILE_LINK_RUN',
        inputs=inputs, modes=modes, cleanup=dict(directory=str(work), removed=removed, directory_removed=not work.exists()),
        native_host_sdk_clr_hwnd_gpu_audio_or_game_executed=False,
        meaning='The component reproduces the retail upload values and DS arithmetic on the CPU. It is not a screen, GPU or game result.'))
    print(json.dumps(dict(status='PASS_CPU_COMPILE_LINK_RUN', checks=modes[0]['checks'], out=str(out / 'result.json'))))


if __name__ == '__main__':
    main(sys.argv[1])
