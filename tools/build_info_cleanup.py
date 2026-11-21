"""Build exact rule cleanup/prefetch bodies with observable owned entries and real SQLite."""
import json
import re
import shutil
from pathlib import Path
from collect_baseline import PROJECT, read_text, pe_header
from native_build import environment_for, run, checked_run
from probe_world_builder import artifact
from database_evidence import validate as validate_database
from build_bootstrap_component import body
from define_info_cleanup_patches import BASE, GLOBALS, HEADER, LOADER, baseline_text, patches, collections

SIGNATURES = {
    GLOBALS: ('template <class T>\r\nvoid deleteInfoArray(', 'void CvGlobals::deleteInfoArrays()',
              'void CvGlobals::uninit()', 'void CvGlobals::infoTypeFromStringReset()',
              'CvString*& CvGlobals::getFootstepAudioTags()'),
    LOADER: ('template<class T>\r\nbool CvDllDatabaseUtility::PrefetchCollection(',)}


def fixtures():
    original = {rel: baseline_text(rel) for rel in SIGNATURES}
    candidate = {rel: (PROJECT / 'Source/SDK_BNW_x64' / rel).read_bytes().decode('latin1') for rel in SIGNATURES}
    def functions(sources):
        return '\n'.join(body(sources[rel], sig) for rel, sigs in SIGNATURES.items() for sig in sigs)
    owners = re.findall(r'SAFE_DELETE\((m_\w+)\)', body(original[GLOBALS], 'void CvGlobals::uninit()'))
    if len(owners) != 38 or len(set(owners)) != 38:
        raise RuntimeError('GC borrower inventory changed')
    fields = ''
    for macro, names in [('INFO_COLLECTION_FIELDS', [name for _,name in collections()]), ('INFO_BORROWER_FIELDS', owners)]:
        fields += '#define ' + macro + '(X) ' + ' '.join('X(' + name + ')' for name in names) + '\n'
    return {name:text.replace('\r\n','\n') for name,text in {
        'info_cleanup_fields.h': fields,
        'info_cleanup_fixture.h':'#ifdef INFO_CLEANUP_ORIGINAL\n' + functions(original)
            + '\n#else\n' + functions(candidate) + '\n#endif\n'}.items()}


def main():
    database, _, provider = validate_database(PROJECT / 'evidence/database/candidate/build_result.json')
    out, root = PROJECT / 'Build/InfoCleanup/x64', PROJECT / 'evidence/info_cleanup'
    out.mkdir(parents=True, exist_ok=True)
    root.mkdir(parents=True, exist_ok=True)
    headers = []
    for name, text in fixtures().items():
        path = out / name
        path.write_text(text, encoding='utf-8', newline='\n')
        headers.append(artifact(path))
    builds, audits = {}, []
    source = PROJECT / 'Tests/sdk_info_cleanup.cpp'
    vs = Path(r'C:\Program Files\Microsoft Visual Studio\2022\Community')
    for name in ('original', 'candidate'):
        directory = out / name
        env, compiler = environment_for(vs, 'x64', directory)
        compiler = Path(compiler)
        env['VSLANG'] = '1033'
        exe, linkmap = directory / ('info_cleanup_' + name + '.exe'), directory / (name + '.map')
        flags = ['/nologo', '/std:c++14', '/EHsc', '/W4', '/WX', '/O2', '/MD', '/utf-8',
                 '/DWIN32', '/DFINAL_RELEASE', '/D_CRT_SECURE_NO_WARNINGS', '/D_SILENCE_STDEXT_HASH_DEPRECATION_WARNINGS']
        if name == 'original':
            flags += ['/DINFO_CLEANUP_ORIGINAL']
        flags += [f'/I"{p}"' for p in (out, PROJECT / 'Source/Porting', PROJECT / 'Source/Providers/Database',
                                       PROJECT / 'Source/SDK_BNW_x64/CvGameDatabase/include')]
        flags += [f'"{source}"', f'"{database["library"]["path"]}"',
                  f'/Fo"{directory / (name + ".obj")}"', f'/Fe"{exe}"']
        rsp = directory / 'compile.rsp'
        rsp.write_text('\n'.join(flags) + '\n', encoding='utf-8')
        result = run([compiler, '@' + str(rsp), '/link', '/INCREMENTAL:NO', '/MACHINE:X64', '/Brepro',
                      '/WX', '/MAP:' + str(linkmap)], cwd=directory, env=env, timeout=180)
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
            log = root / (name + '_' + kind + '_imports.log')
            log.write_bytes(result.stdout + result.stderr)
            deps = re.findall(r'^\s+([\w.-]+\.dll)\s*$', result.stdout.decode('ascii', errors='replace'), re.M | re.I)
            allowed = {'zerosisdatabase_x64.dll', 'kernel32.dll', 'msvcp140.dll', 'vcruntime140.dll', 'vcruntime140_1.dll'}
            if not deps or any(d.lower() not in allowed and not d.lower().startswith('api-ms-win-crt-') for d in deps):
                raise RuntimeError('Unexpected database loader dependency')
            audits.append({'module': artifact(path), 'dependencies': deps, 'log': artifact(log)})
    sources = [source, PROJECT/'Tests/sdk_gc_cleanup_scope.h', PROJECT/'Source/Porting/ZeroSisGlobalsLifecycle.h', PROJECT/'Source/Porting/ZeroSisHostBinding.h', 
               PROJECT / 'tools/define_info_cleanup_patches.py', PROJECT / 'tools/build_bootstrap_component.py',
               PROJECT / 'Source/Providers/Database/SdkDatabaseIncludes.h']
    sources += [PROJECT / 'Source/SDK_BNW_Original' / rel for rel in (*SIGNATURES, HEADER)]
    report = {'status': 'INFO_CLEANUP_COMPONENTS_BUILT', 'builds': builds, 'audits': audits,
              'fixtures': headers, 'sources': [artifact(p) for p in sources], 'database_provider': provider,
              'baseline': artifact(BASE), 'builder': artifact(Path(__file__).resolve()),
              'gamecore_loaded': False, 'game_launched': False,
              'scope': 'EXACT_SDK_RULE_CLEANUP_AND_PREFETCH_REAL_SQLITE_WITH_INSTRUMENTED_INFO_ENTRIES_AND_GAME_BORROWERS'}
    (root / 'build_result.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(report['status'])


if __name__ == '__main__':
    main()
