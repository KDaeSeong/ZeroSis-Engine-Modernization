"""Build lifecycle and exact SDK context-boundary bodies with instrumented adapters."""
import json
import re
from pathlib import Path
from collect_baseline import PROJECT, read_text
from native_build import build_program, environment_for, checked_run
from probe_world_builder import artifact
from define_bootstrap_patches import baseline_text, patches


def body(text, signature):
    start = text.index(signature)
    opening = text.index('{', start)
    depth = 1
    cursor = opening + 1
    while depth:
        depth += (text[cursor] == '{') - (text[cursor] == '}')
        cursor += 1
    return text[start:cursor]


def main():
    out = PROJECT / 'Build/Bootstrap/x64'
    evidence = PROJECT / 'evidence/bootstrap'
    out.mkdir(parents=True, exist_ok=True)
    evidence.mkdir(parents=True, exist_ok=True)
    source = 'CvGameCoreDLL_Expansion2/CvDllContext.cpp'
    original = baseline_text(source)
    candidate_path = PROJECT / 'Source/SDK_BNW_x64' / source
    candidate = candidate_path.read_bytes().decode('latin1')
    signatures = ['CvDllGameContext::CvDllGameContext()', 'void CvDllGameContext::InitializeSingleton()',
                  'void CvDllGameContext::DestroySingleton()', 'void* CvDllGameContext::Allocate(size_t bytes)']
    fixture = out / 'bootstrap_context_fixture.h'
    fixture_text = ('#ifdef BOOTSTRAP_ORIGINAL\n' + '\n'.join(body(original, sig) for sig in signatures)
                    + '\n#else\n' + '\n'.join(body(candidate, sig) for sig in signatures)
                    + '\n' + body(candidate, 'bool CvDllGameContext::ShutdownSingleton()') + '\n#endif\n')
    fixture.write_text(fixture_text.replace('\r\n', '\n'), encoding='utf-8', newline='\n')
    vs = Path(r'C:\Program Files\Microsoft Visual Studio\2022\Community')
    builds = {}
    for name, source_name, defines in (
        ('lifecycle', 'sdk_bootstrap_lifecycle.cpp', ()),
        ('context', 'sdk_bootstrap_context.cpp', ()),
        ('context_original', 'sdk_bootstrap_context.cpp', ('BOOTSTRAP_ORIGINAL',)),
    ):
        directory = out / name
        build = build_program(name=name, architecture='x64', vs=vs, directory=directory, evidence=evidence,
                              source=PROJECT / 'Tests' / source_name, includes=(PROJECT / 'Source/Porting', out),
                              defines=defines, runtime='/MD')
        env, compiler = environment_for(vs, 'x64', directory)
        result = checked_run([Path(compiler).with_name('dumpbin.exe'), '/dependents', build['path']], cwd=directory, env=env)
        log = evidence / (name + '_imports.log')
        log.write_bytes(result.stdout + result.stderr)
        deps = re.findall(r'^\s+([\w.-]+\.dll)\s*$', result.stdout.decode('ascii', errors='replace'), re.M | re.I)
        allowed = {'kernel32.dll', 'msvcp140.dll', 'vcruntime140.dll', 'vcruntime140_1.dll'}
        if not deps or any(d.lower() not in allowed and not d.lower().startswith('api-ms-win-crt-') for d in deps):
            raise RuntimeError('Unexpected bootstrap consumer import')
        builds[name] = {'executable': build, 'imports': {'dependencies': deps, 'log': artifact(log)}}
    report = {'status': 'BOOTSTRAP_NATIVE_COMPONENTS_BUILT', 'builds': builds,
              'sources': [artifact(PROJECT / path) for path in ('Source/Porting/ZeroSisBootstrap.h',
                  'Source/Porting/ZeroSisHostBinding.h', 'Source/Porting/ZeroSisGlobalsLifecycle.h', 'Tests/sdk_bootstrap_lifecycle.cpp',
                  'Tests/sdk_bootstrap_context.cpp', 'tools/define_bootstrap_patches.py')],
              'candidate_source': artifact(candidate_path),
              'fixture': artifact(fixture), 'builder': artifact(Path(__file__).resolve()),
              'gamecore_loaded': False, 'game_launched': False,
              'scope': 'REAL_LIFECYCLE_AND_EXACT_SDK_CONTEXT_BODIES_WITH_INSTRUMENTED_ADAPTERS_NOT_FULL_GAMECORE'}
    (evidence / 'build_result.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(report['status'])


if __name__ == '__main__':
    main()
