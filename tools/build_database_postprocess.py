"""Build extracted SDK algorithms against the accepted real x64 database DLL."""
import json
import re
import shutil
from pathlib import Path
from collect_baseline import PROJECT, read_text, pe_header
from native_build import environment_for, run, checked_run
from probe_world_builder import artifact
from database_evidence import validate as validate_database
from build_bootstrap_component import body
from define_database_postprocess_patches import BASE, TARGET, baseline_text, patches

DEFINITIONS = ('CvGameCoreDLLUtil/include/CvDLLUtilDefines.h', 'CvGameCoreDLL_Expansion2/CvDefines.h')
CONSTANTS = ('MAX_CIV_PLAYERS', 'MAX_CIV_TEAMS', 'MAX_MAJOR_CIVS', 'MAX_MINOR_CIVS', 'MAX_PLAYERS',
             'MAX_TEAMS', 'BARBARIAN_PLAYER', 'BARBARIAN_TEAM', 'NUM_CITY_PLOTS', 'CITY_HOME_PLOT',
             'CITY_PLOTS_RADIUS', 'CITY_PLOTS_DIAMETER')


def fixtures():
    original = baseline_text(TARGET)
    added = patches()
    fixture = '#ifdef DATABASE_POSTPROCESS_ORIGINAL\n' + body(original, 'void InsertGameDefine(') + '\n'
    fixture += body(original, 'bool CvDllDatabaseUtility::PerformDatabasePostProcessing()')
    fixture += '\n#else\n' + added[1]['new'] + '\n' + added[2]['new'] + '\n#endif\n'
    definitions = []
    for relative in DEFINITIONS:
        definitions.extend(line for line in baseline_text(relative).splitlines()
                           if re.match(r'#define\s+(' + '|'.join(CONSTANTS) + r')\s', line))
    if len(definitions) != 12:
        raise RuntimeError('Game define constants changed')
    return {'database_postprocess_fixture.h': fixture.replace('\r\n', '\n'),
            'database_postprocess_defines.h': '\n'.join(definitions) + '\n'}


def main():
    database, _, provider = validate_database(PROJECT / 'evidence/database/candidate/build_result.json')
    out, root = PROJECT / 'Build/DatabasePostprocess/x64', PROJECT / 'evidence/database_postprocess'
    out.mkdir(parents=True, exist_ok=True)
    root.mkdir(parents=True, exist_ok=True)
    headers = []
    for name, text in fixtures().items():
        path = out / name
        path.write_text(text, encoding='utf-8', newline='\n')
        headers.append(artifact(path))
    vs = Path(r'C:\Program Files\Microsoft Visual Studio\2022\Community')
    builds, audits = {}, []
    source = PROJECT / 'Tests/sdk_database_postprocess.cpp'
    for name in ('original', 'candidate'):
        directory = out / name
        env, compiler = environment_for(vs, 'x64', directory)
        compiler = Path(compiler)
        env['VSLANG'] = '1033'
        exe = directory / ('database_postprocess_' + name + '.exe')
        linkmap = directory / (name + '.map')
        flags = ['/nologo', '/std:c++14', '/EHsc', '/W4', '/WX', '/O2', '/MD', '/utf-8',
                 '/DWIN32', '/DFINAL_RELEASE', '/D_CRT_SECURE_NO_WARNINGS', '/D_SILENCE_STDEXT_HASH_DEPRECATION_WARNINGS']
        if name == 'original':
            flags += ['/DDATABASE_POSTPROCESS_ORIGINAL']
        flags += [f'/I"{p}"' for p in (out, PROJECT / 'Source/Providers/Database', PROJECT / 'Source/SDK_BNW_x64/CvGameDatabase/include')]
        flags += [f'"{source}"', f'"{database["library"]["path"]}"', f'/Fo"{directory / (name + ".obj")}"', f'/Fe"{exe}"']
        rsp = directory / 'compile.rsp'
        rsp.write_text('\n'.join(flags) + '\n', encoding='utf-8')
        result = run([compiler, '@' + str(rsp), '/link', '/INCREMENTAL:NO', '/MACHINE:X64', '/Brepro', '/WX', '/MAP:' + str(linkmap)], cwd=directory, env=env, timeout=180)
        log = root / (name + '_build.log')
        log.write_bytes(result.stdout + result.stderr)
        if result.returncode or re.search(r'\bwarning\s+C\d+', read_text(log)):
            raise RuntimeError(read_text(log))
        dll = directory / Path(database['dll']['path']).name
        shutil.copy2(database['dll']['path'], dll)
        builds[name] = {'executable': {**artifact(exe), 'pe': pe_header(exe)}, 'dll': artifact(dll),
                        'compiler': artifact(compiler), 'response': artifact(rsp), 'log': artifact(log), 'map': artifact(linkmap)}
        for kind, path in (('exe', exe), ('database', dll)):
            result = checked_run([compiler.with_name('dumpbin.exe'), '/dependents', path], cwd=directory, env=env)
            dep_log = root / (name + '_' + kind + '_imports.log')
            dep_log.write_bytes(result.stdout + result.stderr)
            deps = re.findall(r'^\s+([\w.-]+\.dll)\s*$', result.stdout.decode('ascii', errors='replace'), re.M | re.I)
            allowed = {'zerosisdatabase_x64.dll', 'kernel32.dll', 'msvcp140.dll', 'vcruntime140.dll', 'vcruntime140_1.dll'}
            if not deps or any(d.lower() not in allowed and not d.lower().startswith('api-ms-win-crt-') for d in deps):
                raise RuntimeError('Unexpected database postprocessing dependency')
            audits.append({'module': artifact(path), 'dependencies': deps, 'log': artifact(dep_log)})
    sources = [source, PROJECT / 'tools/define_database_postprocess_patches.py', PROJECT / 'tools/build_bootstrap_component.py',
               PROJECT / 'Source/SDK_BNW_Original' / TARGET, PROJECT / 'Source/Providers/Database/SdkDatabaseIncludes.h']
    sources += [PROJECT / 'Source/SDK_BNW_Original' / rel for rel in DEFINITIONS]
    report = {'status': 'DATABASE_POSTPROCESS_COMPONENTS_BUILT', 'builds': builds, 'audits': audits,
              'fixtures': headers, 'sources': [artifact(p) for p in sources], 'database_provider': provider,
              'baseline': artifact(BASE), 'builder': artifact(Path(__file__).resolve()),
              'original_algorithm_uses_same_accepted_x64_database': True,
              'gamecore_loaded': False, 'game_launched': False,
              'scope': 'EXACT_ORIGINAL_AND_CANDIDATE_GAMECORE_POSTPROCESS_BODIES_REAL_SQLITE_PROVIDER_STUB_GLOBAL_DB_ACCESS'}
    (root / 'build_result.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(report['status'])


if __name__ == '__main__':
    main()
