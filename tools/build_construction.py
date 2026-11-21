"""Build exact constructor/destructor/reset bodies with isolated observable seams."""
import json
import re
from pathlib import Path
from collect_baseline import PROJECT
from native_build import build_program, environment_for, checked_run
from probe_world_builder import artifact
from build_bootstrap_component import body
from define_construction_patches import BASE, GAME, MAP, baseline_text, patches

SIGNATURES = {GAME: ('CvGame::CvGame()', 'CvGame::~CvGame()'),
              MAP: ('CvMap::CvMap()', 'CvMap::~CvMap()', 'void CvMap::reset(', 'void CvMap::uninit()')}
STRUCTS = 'CvGameCoreDLLUtil/include/CvStructs.h'


def fixtures():
    original = {name: baseline_text(name) for name in SIGNATURES}
    candidate = dict(original)
    for patch in patches():
        text = candidate[patch['file']]
        if text.count(patch['old']) != patch['count']:
            raise RuntimeError('Constructor extraction patch mismatch')
        candidate[patch['file']] = text.replace(patch['old'], patch['new'])
    def functions(sources):
        return '\n'.join(body(sources[name], sig) for name, sigs in SIGNATURES.items() for sig in sigs)
    fixture = '#ifdef CONSTRUCTION_ORIGINAL\n' + functions(original) + '\n#else\n' + functions(candidate) + '\n#endif\n'
    game_ctor = body(original[GAME], 'CvGame::CvGame()')
    owned = re.findall(r'\t(m_ai\w+) = FNEW\(int\[(MAX_\w+)\]', game_ctor)
    game_nulls = re.findall(r'\t(m_\w+) = NULL;', game_ctor)
    map_ctor = body(original[MAP], 'CvMap::CvMap()')
    map_nulls = re.findall(r'\t(m_\w+) = NULL;', map_ctor)
    if len(owned) != 7 or len(map_nulls) != 13:
        raise RuntimeError('Constructor ownership field list changed')
    fields = ''
    for macro, rows in (
        ('GAME_OWNED_FIELDS', [name + ', ' + size for name, size in owned]),
        ('GAME_NULL_FIELDS', game_nulls), ('MAP_NULL_FIELDS', map_nulls)):
        fields += '#define ' + macro + '(X) \\\n' + ' \\\n'.join('    X(' + row + ')' for row in rows) + '\n'
    struct = body(baseline_text(STRUCTS), 'struct CvMapInitData') + ';\n'
    return {name: text.replace('\r\n', '\n') for name, text in {
        'construction_fixture.h': fixture, 'construction_fields.h': fields, 'construction_map_init.h': struct}.items()}


def main():
    out = PROJECT / 'Build/Construction/x64'
    root = PROJECT / 'evidence/construction'
    out.mkdir(parents=True, exist_ok=True)
    root.mkdir(parents=True, exist_ok=True)
    headers = []
    for name, text in fixtures().items():
        p = out / name
        p.write_text(text, encoding='utf-8', newline='\n')
        headers.append(artifact(p))
    vs = Path(r'C:\Program Files\Microsoft Visual Studio\2022\Community')
    builds = {}
    for name, defines in (('candidate', ()), ('original', ('CONSTRUCTION_ORIGINAL',))):
        directory = out / name
        built = build_program(name='construction_' + name, architecture='x64', vs=vs, directory=directory,
                              evidence=root, source=PROJECT / 'Tests/sdk_construction.cpp', includes=(out,),
                              defines=defines, runtime='/MD')
        env, compiler = environment_for(vs, 'x64', directory)
        result = checked_run([Path(compiler).with_name('dumpbin.exe'), '/dependents', built['path']],
                             cwd=directory, env=env)
        log = root / (name + '_imports.log')
        log.write_bytes(result.stdout + result.stderr)
        deps = re.findall(r'^\s+([\w.-]+\.dll)\s*$', result.stdout.decode('ascii', errors='replace'), re.M | re.I)
        allowed = {'kernel32.dll', 'msvcp140.dll', 'vcruntime140.dll', 'vcruntime140_1.dll'}
        if not deps or any(d.lower() not in allowed and not d.lower().startswith('api-ms-win-crt-') for d in deps):
            raise RuntimeError('Unexpected constructor test import')
        builds[name] = {'executable': built, 'imports': {'dependencies': deps, 'log': artifact(log)}}
    sources = ['Tests/sdk_construction.cpp', 'tools/define_construction_patches.py',
               'tools/build_bootstrap_component.py', 'tools/native_build.py']
    sources += ['Source/SDK_BNW_Original/' + name for name in (*SIGNATURES, STRUCTS)]
    report = {'status': 'CONSTRUCTION_COMPONENTS_BUILT', 'builds': builds, 'fixtures': headers,
              'sources': [artifact(PROJECT / p) for p in sources], 'baseline': artifact(BASE),
              'builder': artifact(Path(__file__).resolve()), 'gamecore_loaded': False, 'game_launched': False,
              'scope': 'EXACT_GAME_AND_MAP_CONSTRUCTION_BODIES_WITH_INSTRUMENTED_RESET_HOST_CONTAINERS_NOT_GAME_RUNTIME'}
    (root / 'build_result.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(report['status'])


if __name__ == '__main__':
    main()
