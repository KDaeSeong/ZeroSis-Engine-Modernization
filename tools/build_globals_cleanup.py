"""Build exact SDK cleanup functions against observable substitute dependencies."""
import json
import re
from pathlib import Path
from collect_baseline import PROJECT
from native_build import build_program, environment_for, checked_run
from probe_world_builder import artifact
from build_bootstrap_component import body
from define_globals_cleanup_patches import BASE, TARGET, baseline_text, patches

STRATEGIES = 'CvGameCoreDLL_Expansion2/CvCityStrategyAI.cpp'
SIGNATURES = ('CvAICityStrategyEntry::~CvAICityStrategyEntry(void)',
              'CvAICityStrategies::CvAICityStrategies(void)',
              'CvAICityStrategies::~CvAICityStrategies(void)',
              'void CvAICityStrategies::DeleteArray()')


def fixtures():
    original = body(baseline_text(TARGET), 'void CvGlobals::uninit()')
    candidate = body((PROJECT / 'Source/SDK_BNW_x64' / TARGET).read_bytes().decode('latin1'), 'void CvGlobals::uninit()')
    shared = '\n'.join(body(baseline_text(STRATEGIES), sig) for sig in SIGNATURES)
    fixture = shared + '\n#ifdef GLOBALS_ORIGINAL\n' + original + '\n#else\n' + candidate + '\n#endif\n'
    fields = re.findall(r'SAFE_DELETE\((m_\w+)\)', original)
    if len(fields) != 37 or len(set(fields)) != 37 or 'm_pAICityStrategies' in fields:
        raise RuntimeError('Original cleanup field inventory changed')
    declarations = '#define GLOBALS_OTHER_FIELDS(X) \\\n' + ' \\\n'.join(
        '    X(' + name + ', ' + ('true' if 'finder' in name.lower() else 'false') + ')' for name in fields) + '\n'
    return fixture.replace('\r\n', '\n'), declarations


def main():
    out = PROJECT / 'Build/GlobalsCleanup/x64'
    evidence = PROJECT / 'evidence/globals_cleanup'
    out.mkdir(parents=True, exist_ok=True)
    evidence.mkdir(parents=True, exist_ok=True)
    fixture, fields = fixtures()
    fp, dp = out / 'globals_cleanup_fixture.h', out / 'globals_cleanup_fields.h'
    fp.write_text(fixture, encoding='utf-8', newline='\n')
    dp.write_text(fields, encoding='utf-8', newline='\n')
    vs = Path(r'C:\Program Files\Microsoft Visual Studio\2022\Community')
    builds = {}
    for name, defines in (('candidate', ()), ('original', ('GLOBALS_ORIGINAL',))):
        directory = out / name
        build = build_program(name='globals_' + name, architecture='x64', vs=vs, directory=directory,
                              evidence=evidence, source=PROJECT / 'Tests/sdk_globals_cleanup.cpp',
                              includes=(out, PROJECT / 'Source/Porting'), defines=defines, runtime='/MD')
        env, compiler = environment_for(vs, 'x64', directory)
        result = checked_run([Path(compiler).with_name('dumpbin.exe'), '/dependents', build['path']],
                             cwd=directory, env=env)
        log = evidence / (name + '_imports.log')
        log.write_bytes(result.stdout + result.stderr)
        deps = re.findall(r'^\s+([\w.-]+\.dll)\s*$', result.stdout.decode('ascii', errors='replace'), re.M | re.I)
        allowed = {'kernel32.dll', 'msvcp140.dll', 'vcruntime140.dll', 'vcruntime140_1.dll'}
        if not deps or any(d.lower() not in allowed and not d.lower().startswith('api-ms-win-crt-') for d in deps):
            raise RuntimeError('Unexpected globals cleanup consumer dependency')
        builds[name] = {'executable': build, 'imports': {'dependencies': deps, 'log': artifact(log)}}
    report = {'status': 'GLOBALS_CLEANUP_COMPONENTS_BUILT', 'builds': builds,
              'candidate_source': artifact(PROJECT / 'Source/SDK_BNW_x64' / TARGET),
              'sources': [artifact(PROJECT / path) for path in (
                  'Tests/sdk_globals_cleanup.cpp', 'Tests/sdk_gc_cleanup_scope.h', 'Source/Porting/ZeroSisGlobalsLifecycle.h', 'Source/Porting/ZeroSisHostBinding.h', 'tools/define_globals_cleanup_patches.py',
                  'tools/build_bootstrap_component.py', 'tools/native_build.py',
                  'Source/SDK_BNW_Original/' + TARGET, 'Source/SDK_BNW_Original/' + STRATEGIES)],
              'baseline': artifact(BASE), 'fixture': artifact(fp), 'fields': artifact(dp),
              'builder': artifact(Path(__file__).resolve()), 'gamecore_loaded': False, 'game_launched': False,
              'scope': 'EXACT_SDK_UNINIT_AND_STRATEGY_DESTRUCTORS_WITH_INSTRUMENTED_OTHER_OWNERS_NOT_GAMECORE_RUNTIME'}
    (evidence / 'build_result.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(report['status'])


if __name__ == '__main__':
    main()
