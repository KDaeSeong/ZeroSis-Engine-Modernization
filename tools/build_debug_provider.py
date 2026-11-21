"""Build the SDK symbol service and an isolated PDB-bearing native consumer."""
import json
import re
from pathlib import Path
from collect_baseline import PROJECT, read_text, pe_header
from native_build import environment_for, run, checked_run
from probe_world_builder import artifact


def main():
    out = PROJECT / 'Build/Debug/x64'
    evidence = PROJECT / 'evidence/debug'
    out.mkdir(parents=True, exist_ok=True)
    evidence.mkdir(parents=True, exist_ok=True)
    env, compiler = environment_for(Path(r'C:\Program Files\Microsoft Visual Studio\2022\Community'), 'x64', out)
    compiler = Path(compiler)
    source = PROJECT / 'Source/Providers/Debug/SdkDebugHelper.cpp'
    test = PROJECT / 'Tests/sdk_debug.cpp'
    stack_test = PROJECT / 'Tests/sdk_debug_stack.cpp'
    sdk = PROJECT / 'Source/SDK_BNW_x64'
    original_template = PROJECT / 'Source/SDK_BNW_Original/FirePlace/include/FireWorks/Win32/FDebugHelper.inl'
    fixture = out / 'original_stack_walk.inl'
    fixture.write_text(original_template.read_bytes().decode('latin1').replace('FDebugHelper::', 'OriginalWalkFixture::').replace('\r\n', '\n'), encoding='utf-8', newline='\n')
    flags = ['/nologo', '/Gy', '/MD', '/EHsc', '/W4', '/WX', '/std:c++14', '/utf-8', '/Z7',
             '/DWIN32', '/D_WINPC', '/DFINAL_RELEASE', '/DFXS_IS_DLL', '/D_CRT_SECURE_NO_WARNINGS',
             '/D_SECURE_SCL=0', '/D_HAS_ITERATOR_DEBUGGING=0', '/external:W0',
             f'/I"{source.parent}"', f'/I"{out}"', f'/external:I"{sdk / "FirePlace/include"}"']
    logs, responses = [], []

    def compile_one(name, args, link=()):
        response = out / (name + '.rsp')
        response.write_text('\n'.join(args) + '\n', encoding='utf-8')
        responses.append(artifact(response))
        result = run([compiler, '@' + str(response), *(['/link', *link] if link else [])], cwd=out, env=env, timeout=120)
        log = evidence / (name + '_build.log')
        log.write_bytes(result.stdout + result.stderr)
        logs.append(artifact(log))
        if result.returncode:
            raise RuntimeError(read_text(log)[-8000:])

    obj = out / 'SdkDebugHelper.obj'
    compile_one('provider', flags + ['/O2', '/c', f'"{source}"', f'/Fo"{obj}"'])
    library = out / 'ZeroSis_Debug_x64.lib'
    checked_run([compiler.with_name('lib.exe'), '/nologo', '/Brepro', f'/OUT:{library}', obj], cwd=out, env=env)
    def consumer(name, source_file):
        exe, linkmap, pdb = (out / (name + suffix) for suffix in ('.exe', '.map', '.pdb'))
        compile_one(name, flags + ['/Od', '/Ob0', f'"{source_file}"', f'"{library}"', f'/Fo"{out / (name + ".obj")}"', f'/Fe"{exe}"'],
                ['/INCREMENTAL:NO', '/OPT:REF', '/MACHINE:X64', '/DEBUG:FULL', f'/PDB:{pdb}', f'/MAP:{linkmap}',
                 'kernel32.lib', 'dbghelp.lib', 'psapi.lib'])
        imports = checked_run([compiler.with_name('dumpbin.exe'), '/dependents', exe], cwd=out, env=env)
        import_log = evidence / (name + '_imports.log')
        import_log.write_bytes(imports.stdout + imports.stderr)
        deps = re.findall(r'^\s+([\w.-]+\.dll)\s*$', imports.stdout.decode('ascii', errors='replace'), re.M | re.I)
        allowed = {'kernel32.dll', 'dbghelp.dll', 'psapi.dll', 'msvcp140.dll', 'vcruntime140.dll', 'vcruntime140_1.dll'}
        if not deps or any(d.lower() not in allowed and not d.lower().startswith('api-ms-win-crt-') for d in deps):
            raise RuntimeError('Unexpected debug consumer import')
        return {'source': artifact(source_file), 'executable': {**artifact(exe), 'pe': pe_header(exe)},
                'map': artifact(linkmap), 'pdb': artifact(pdb), 'imports': {'dependencies': deps, 'log': artifact(import_log)}}
    symbol_consumer = consumer('debug', test)
    stack_consumer = consumer('debug_stack', stack_test)
    report = {
        'status': 'DEBUG_X64_SYMBOL_PROVIDER_BUILT', 'runtime': '/MD',
        'library': artifact(library), 'objects': [artifact(obj)],
        'sources': [artifact(p) for p in (source, source.with_suffix('.h'), test, stack_test)],
        'sdk_headers': [artifact(sdk / 'FirePlace/include/FireWorks/Win32' / name) for name in ('FDebugHelper.h', 'FDebugHelper.inl')],
        'consumer': symbol_consumer, 'stack_consumer': stack_consumer,
        'original_stack_template': artifact(original_template), 'original_stack_fixture': artifact(fixture),
        'builder': artifact(Path(__file__).resolve()), 'compiler': artifact(compiler), 'flags': flags,
        'logs': logs, 'responses': responses,
        'sdk_port_manifest': artifact(PROJECT / 'evidence/sdk_x64/port_manifest.json'),
        'sdk_patch_specification': artifact(PROJECT / 'Source/Porting/sdk_x64_patches.json'),
        'official_gamecore_integrated': False, 'gamecore_loaded': False, 'game_launched': False,
        'scope': 'SYMBOL_SESSION_AND_SDK_CURRENT_THREAD_STACK_WALK; GAMECORE_RUNTIME_PENDING',
    }
    (evidence / 'build_result.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(report['status'])


if __name__ == '__main__':
    main()
