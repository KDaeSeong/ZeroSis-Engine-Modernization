"""Build exact SDK reference-count/cache/lifecycle bodies in an isolated consumer."""
import json
import re
import shutil
from pathlib import Path
from collect_baseline import PROJECT, read_text, pe_header
from native_build import environment_for, run, checked_run
from probe_world_builder import artifact
from database_evidence import validate as validate_database
from build_bootstrap_component import body
from define_database_loader_patches import BASE, GLOBALS, CONTEXT, UTILITY, baseline_text, patches

UNKNOWN = 'CvGameCoreDLLUtil/include/CvDllInterfaces.h'
INTERFACE = 'CvGameCoreDLLUtil/include/ICvDLLDatabaseUtility.h'
UTILITY_HEADER = 'CvGameCoreDLL_Expansion2/CvDllDatabaseUtility.h'
SIGNATURES = {
    GLOBALS: ('ICvDLLDatabaseUtility1* CvGlobals::getDatabaseLoadUtility()', 'void CvGlobals::uninit()'),
    CONTEXT: ('void* CvDllGameContext::Allocate(', 'void CvDllGameContext::Free(', 'bool CvDllGameContext::ShutdownSingleton()'),
    UTILITY: ('CvDllDatabaseUtility::CvDllDatabaseUtility(', 'CvDllDatabaseUtility::~CvDllDatabaseUtility()',
              'void* CvDllDatabaseUtility::QueryInterface(', 'unsigned int CvDllDatabaseUtility::IncrementReference()',
              'unsigned int CvDllDatabaseUtility::DecrementReference()', 'unsigned int CvDllDatabaseUtility::GetReferenceCount()',
              'void CvDllDatabaseUtility::Destroy()', 'void CvDllDatabaseUtility::operator delete(',
              'void* CvDllDatabaseUtility::operator new(', 'bool CvDllDatabaseUtility::CacheGameDatabaseData()',
              'bool CvDllDatabaseUtility::FlushGameDatabaseData()')}


def fixtures():
    original = {rel: baseline_text(rel) for rel in SIGNATURES}
    candidate = {rel: (PROJECT / 'Source/SDK_BNW_x64' / rel).read_bytes().decode('latin1') for rel in SIGNATURES}
    def functions(sources, newer=False):
        result = '\n'.join(body(sources[rel], sig) for rel, sigs in SIGNATURES.items() for sig in sigs)
        if newer:
            result += '\n' + body(sources[GLOBALS], 'void CvGlobals::releaseDatabaseLoadUtility()')
        return result
    abi = ''
    for rel, sigs in {
        UNKNOWN: ('static const GUID guidICvUnknown =', 'static const GUID guidICvDLLDatabaseUtility1', 'class ICvUnknown\r\n{'),
        INTERFACE: ('class ICvDLLDatabaseUtility1',),
        UTILITY_HEADER: ('class CvDllDatabaseUtility:',)}.items():
        for sig in sigs:
            abi += body(baseline_text(rel), sig) + ';\n'
    fields = re.findall(r'SAFE_DELETE\((m_\w+)\)', body(original[GLOBALS], 'void CvGlobals::uninit()'))
    if len(fields) != 38 or len(set(fields)) != 38:
        raise RuntimeError('Unexpected GC owner inventory')
    declarations = '\n'.join('    UnrelatedOwner* ' + name + ' = nullptr;' for name in fields) + '\n'
    return {name: text.replace('\r\n', '\n') for name, text in {
        'database_loader_abi.h': abi,
        'database_loader_fields.h': declarations,
        'database_loader_fixture.h': '#ifdef DATABASE_LOADER_ORIGINAL\n' + functions(original)
            + '\n#else\n' + functions(candidate, True) + '\n#endif\n'}.items()}


def main():
    database, _, provider = validate_database(PROJECT / 'evidence/database/candidate/build_result.json')
    out, root = PROJECT / 'Build/DatabaseLoader/x64', PROJECT / 'evidence/database_loader'
    out.mkdir(parents=True, exist_ok=True)
    root.mkdir(parents=True, exist_ok=True)
    headers = []
    for name, text in fixtures().items():
        path = out / name
        path.write_text(text, encoding='utf-8', newline='\n')
        headers.append(artifact(path))
    builds, audits = {}, []
    source = PROJECT / 'Tests/sdk_database_loader.cpp'
    vs = Path(r'C:\Program Files\Microsoft Visual Studio\2022\Community')
    for name in ('original', 'candidate'):
        directory = out / name
        env, compiler = environment_for(vs, 'x64', directory)
        compiler = Path(compiler)
        env['VSLANG'] = '1033'
        exe, linkmap = directory / ('database_loader_' + name + '.exe'), directory / (name + '.map')
        flags = ['/nologo', '/std:c++14', '/EHsc', '/W4', '/WX', '/O2', '/MD', '/utf-8',
                 '/DWIN32', '/DFINAL_RELEASE', '/D_CRT_SECURE_NO_WARNINGS', '/D_SILENCE_STDEXT_HASH_DEPRECATION_WARNINGS']
        if name == 'original':
            flags += ['/DDATABASE_LOADER_ORIGINAL']
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
    sources = [source, PROJECT/'Tests/sdk_gc_cleanup_scope.h', PROJECT/'Source/Porting/ZeroSisGlobalsLifecycle.h', PROJECT / 'Source/Porting/ZeroSisHostBinding.h',
               PROJECT / 'tools/define_database_loader_patches.py', PROJECT / 'tools/build_bootstrap_component.py',
               PROJECT / 'Source/Providers/Database/SdkDatabaseIncludes.h']
    sources += [PROJECT / 'Source/SDK_BNW_x64' / rel for rel in SIGNATURES]
    sources += [PROJECT / 'Source/SDK_BNW_Original' / rel for rel in (*SIGNATURES, UNKNOWN, INTERFACE, UTILITY_HEADER)]
    report = {'status': 'DATABASE_LOADER_COMPONENTS_BUILT', 'builds': builds, 'audits': audits,
              'fixtures': headers, 'sources': [artifact(p) for p in sources], 'database_provider': provider,
              'baseline': artifact(BASE), 'builder': artifact(Path(__file__).resolve()),
              'gamecore_loaded': False, 'game_launched': False,
              'scope': 'EXACT_SDK_FACTORY_REFCOUNT_CACHE_UNINIT_SHUTDOWN_REAL_HEAP_AND_SQLITE_WITH_INSTRUMENTED_GAME_OWNERS_AND_PREFETCH'}
    (root / 'build_result.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(report['status'])


if __name__ == '__main__':
    main()
