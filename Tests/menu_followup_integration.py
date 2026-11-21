"""Run only the owned C++/shared-Lua slider boundary fixture; no game module."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import sys

P = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(P / 'tools'))
from native_build import build_program, run
from menu_suite_storage import storage


def main():
    stage = P / 'evidence/game_menu/original_menu_followup/integration'
    build = P / 'Build/MenuFollowupInput/current'
    build.mkdir(parents=True, exist_ok=True)
    if list(build.iterdir()):
        raise RuntimeError('Retain prior fixture result; refusing to overwrite its build')
    paths = [P / name for name in ('Tests/ui_input_dispatch.cpp', 'Source/Host/UiInputDispatch.h',
             'Source/Presentation/BitmapSliderInput.h')]
    refs = [dict(path=str(p), bytes=p.stat().st_size, sha256=storage.digest(p)) for p in paths]
    shared = json.loads((P / 'evidence/shared_lua_runtime/build_result.json').read_text(encoding='utf8'))
    for name in ('lua_dll', 'lua_library'):
        ref = shared[name]
        if storage.digest(ref['path']) != ref['sha256']:
            raise RuntimeError('Shared Lua provider changed')
    result = build_program(name='MenuFollowupInput', architecture='x64',
        vs=Path(r'C:\Program Files\Microsoft Visual Studio\2022\Community'), directory=build,
        evidence=stage, source=paths[0], includes=[P / 'Source/Host', P / 'Source/Lua51_x64/src'],
        defines=['LUA_BUILD_AS_DLL', '_CRT_SECURE_NO_WARNINGS'],
        objects=[Path(shared['lua_library']['path'])], runtime='/MD')
    env = os.environ.copy()
    env['PATH'] = str(Path(shared['lua_dll']['path']).parent) + os.pathsep + env.get('PATH', '')
    completed = run([result['path']], cwd=build, env=env, timeout=30)
    output = (completed.stdout + completed.stderr).decode('utf8', errors='replace')
    (stage / 'slider_fixture.log').write_text(output, encoding='utf8')
    match = re.fullmatch(r'UI_INPUT_DISPATCH_PASS checks=(\d+) LUA51_SHARED=true GAMECORE_LOADED=false\s*', output)
    if completed.returncode or not match:
        raise RuntimeError('Owned C++/Lua fixture failed: ' + output[-1600:])
    if any(storage.digest(ref['path']) != ref['sha256'] for ref in refs):
        raise RuntimeError('Fixture inputs changed during verification')
    cleanup = []
    for name in ('MenuFollowupInput.obj', 'MenuFollowupInput.map', 'compile.rsp', 'read_build_environment.cmd'):
        p = build / name
        for parent in (p, *p.parents):
            if getattr(parent.lstat(), 'st_file_attributes', 0) & 0x400:
                raise RuntimeError('Reparse point in owned fixture cleanup')
        info = storage.ordinary(p)
        if info.st_nlink != 1 or p.resolve().parent != build.resolve():
            raise RuntimeError('Owned intermediate identity/parent differs')
        row = dict(path=str(p), sha256=storage.digest(p), allocated_bytes=storage.allocated(p), **storage.metadata(info))
        p.unlink()
        row['result'] = 'DELETED_OWNED_REGENERABLE_INTERMEDIATE'
        cleanup.append(row)
    report = dict(status='PASS_CPP_LUA_SLIDER_INPUT_COMPONENT_ONLY', checks=int(match[1]),
        inputs=refs, build=result, shared_lua=shared['lua_dll'], cleanup=cleanup,
        host_executed=False, gamecore_loaded=False, sdk_executed=False, hwnd_created=False, gpu_used=False,
        remaining='Physical capture and original UI appearance require the deferred native test')
    (stage / 'cpp_slider_result.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf8')
    print(json.dumps({key: report[key] for key in ('status', 'checks')}))


if __name__ == '__main__':
    main()
