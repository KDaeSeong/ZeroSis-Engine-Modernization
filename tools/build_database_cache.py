"""Build exact DB/cache/type functions and a contiguous GC DB-phase seam, never GameCore."""
import json
import re
import shutil
from pathlib import Path
from collect_baseline import PROJECT, read_text, pe_header
from native_build import environment_for, run, checked_run
from probe_world_builder import artifact
from database_evidence import validate as validate_database
from build_bootstrap_component import body
from define_database_cache_patches import BASE, UTILITY, HEADER, GLOBALS, TYPES, baseline_text, patches, database_phase

SIGNATURES = {
    HEADER: ('template<class T>\r\nbool CvDllDatabaseUtility::PrefetchCollection(',),
    UTILITY: ('bool CvDllDatabaseUtility::PrefetchGameData()', 'bool CvDllDatabaseUtility::CacheGameDatabaseData()'),
    TYPES: ('void CvTypes::AcquireTypes(',)}


def fixtures():
    original = {rel: baseline_text(rel) for rel in (*SIGNATURES, GLOBALS)}
    candidate = dict(original)
    for p in patches():
        candidate[p['file']] = candidate[p['file']].replace(p['old'], p['new'])
    prefetch = body(original[UTILITY], 'bool CvDllDatabaseUtility::PrefetchGameData()')
    calls = re.findall(r'PrefetchCollection\(([^,]+), "(\w+)"\);', prefetch)
    if len(calls) != 62:
        raise RuntimeError('Expected all sixty-two collection calls')
    getters = []
    table_data = 'static const char* const ruleTables[] = {' + ','.join('"'+table+'"' for _,table in calls) + '};\n'
    for i,(call,table) in enumerate(calls):
        if call.startswith('GC.'):
            getters.append('std::vector<Info*>& ' + call[3:] + ' { return lists['+str(i)+']; }')
        else:
            getters.append('CvNotificationXMLEntries* GetNotificationEntries() { notifications.entries=&lists['+str(i)+']; return haveNotifications ? &notifications : nullptr; }')
    types = original[TYPES]
    declarations = re.findall(r'^(?:GreatWorkArtifactClass|GreatWorkSlotType|MissionTypes|unsigned int)\s+(s_\w+)\s*=\s*([^;]+);', types, re.M)
    if len(declarations) != 68:
        raise RuntimeError('Type global inventory changed: '+str(len(declarations)))
    globals_text = types[types.index('//Static variables'):types.index('void CvTypes::AcquireTypes(')]
    reset = 'void ResetTypes() {\n' + '\n'.join(name+' = '+value+';' for name,value in declarations) + '\n}\n'
    lookup = re.findall(r'insert\(make_pair\(std::string\("(\w+)"\), &(s_\w+)\)\)', types)
    table_data += 'struct TypeValue { const char* name; int* value; };\nstatic const TypeValue typeValues[] = {\n' + ',\n'.join('{"'+key+'", &'+value+'}' for key,value in lookup) + '};\n'
    abi = ''
    for rel,sigs in {
        'CvGameCoreDLLUtil/include/CvDllInterfaces.h': ('static const GUID guidICvUnknown =', 'static const GUID guidICvDLLDatabaseUtility1', 'class ICvUnknown\r\n{'),
        'CvGameCoreDLLUtil/include/ICvDLLDatabaseUtility.h': ('class ICvDLLDatabaseUtility1',)}.items():
        for sig in sigs: abi += body(baseline_text(rel),sig)+';\n'
    def functions(sources,newer):
        result = body(sources[TYPES], SIGNATURES[TYPES][0])+'\n'
        result += body(sources[HEADER],SIGNATURES[HEADER][0])+'\n'
        if newer: result += body(sources[UTILITY],'static bool ZeroSisCacheFlavorTypes()')+'\n'
        result += '\n'.join(body(sources[UTILITY],sig) for sig in SIGNATURES[UTILITY])+'\n'
        result += 'void CvGlobals::DatabasePhase()\n{\n'+database_phase(sources[GLOBALS])+'}\n'
        return result
    return {name:text.replace('\r\n','\n') for name,text in {
        'database_cache_abi.h':abi,
        'database_cache_getters.h':'\n'.join(getters)+'\n',
        'database_cache_data.h':globals_text+reset+table_data,
        'database_cache_fixture.h':'#ifdef DATABASE_CACHE_ORIGINAL\n'+functions(original,False)+'\n#else\n'+functions(candidate,True)+'\n#endif\n'}.items()}


def main():
    database, _, provider = validate_database(PROJECT / 'evidence/database/candidate/build_result.json')
    out, root = PROJECT / 'Build/DatabaseCache/x64', PROJECT / 'evidence/database_cache'
    out.mkdir(parents=True, exist_ok=True)
    root.mkdir(parents=True, exist_ok=True)
    headers = []
    for name,text in fixtures().items():
        path=out/name
        path.write_text(text,encoding='utf-8',newline='\n')
        headers.append(artifact(path))
    builds,audits={},[]
    source=PROJECT/'Tests/sdk_database_cache.cpp'
    vs=Path(r'C:\Program Files\Microsoft Visual Studio\2022\Community')
    for name in ('original','candidate'):
        directory=out/name
        env,compiler=environment_for(vs,'x64',directory)
        compiler=Path(compiler);env['VSLANG']='1033'
        exe,linkmap=directory/('database_cache_'+name+'.exe'),directory/(name+'.map')
        flags=['/nologo','/std:c++14','/EHsc','/W4','/WX','/O2','/MD','/utf-8','/DWIN32','/DFINAL_RELEASE',
               '/D_CRT_SECURE_NO_WARNINGS','/D_SILENCE_STDEXT_HASH_DEPRECATION_WARNINGS','/D_SILENCE_TR1_NAMESPACE_DEPRECATION_WARNING']
        # Preserve the diagnosed original auto_ptr/nonvirtual-dtor defect for comparison.
        # Candidate gets no C5205 exemption and uses the live SDK Destroy dispatcher.
        if name=='original': flags+=['/DDATABASE_CACHE_ORIGINAL','/wd5205']
        flags += [f'/I"{p}"' for p in (out,PROJECT/'Source/Porting',PROJECT/'Source/Providers/Database',PROJECT/'Source/SDK_BNW_x64/CvGameDatabase/include')]
        flags += [f'"{source}"',f'"{database["library"]["path"]}"',f'/Fo"{directory/(name+".obj")}"',f'/Fe"{exe}"']
        rsp=directory/'compile.rsp';rsp.write_text('\n'.join(flags)+'\n',encoding='utf-8')
        result=run([compiler,'@'+str(rsp),'/link','/INCREMENTAL:NO','/MACHINE:X64','/Brepro','/WX','/MAP:'+str(linkmap)],cwd=directory,env=env,timeout=180)
        log=root/(name+'_build.log');log.write_bytes(result.stdout+result.stderr)
        if result.returncode or re.search(r'\bwarning\s+C\d+',read_text(log)): raise RuntimeError(read_text(log))
        dll=directory/Path(database['dll']['path']).name;shutil.copy2(database['dll']['path'],dll)
        builds[name]={'executable':{**artifact(exe),'pe':pe_header(exe)},'dll':artifact(dll),'compiler':artifact(compiler),'response':artifact(rsp),'log':artifact(log),'map':artifact(linkmap)}
        for kind,path in (('exe',exe),('database',dll)):
            result=checked_run([compiler.with_name('dumpbin.exe'),'/dependents',path],cwd=directory,env=env)
            log=root/(name+'_'+kind+'_imports.log');log.write_bytes(result.stdout+result.stderr)
            deps=re.findall(r'^\s+([\w.-]+\.dll)\s*$',result.stdout.decode('ascii',errors='replace'),re.M|re.I)
            allowed={'zerosisdatabase_x64.dll','kernel32.dll','msvcp140.dll','vcruntime140.dll','vcruntime140_1.dll'}
            if not deps or any(d.lower() not in allowed and not d.lower().startswith('api-ms-win-crt-') for d in deps): raise RuntimeError('Unexpected DB cache dependency')
            audits.append({'module':artifact(path),'dependencies':deps,'log':artifact(log)})
    sources=[source,PROJECT/'Source/Porting/ZeroSisHostBinding.h',PROJECT/'tools/define_database_cache_patches.py',PROJECT/'tools/build_bootstrap_component.py',PROJECT/'Source/Providers/Database/SdkDatabaseIncludes.h']
    sources += [PROJECT/'Source/SDK_BNW_Original'/rel for rel in (*SIGNATURES,GLOBALS,'CvGameCoreDLLUtil/include/CvDllInterfaces.h','CvGameCoreDLLUtil/include/ICvDLLDatabaseUtility.h')]
    report={'status':'DATABASE_CACHE_COMPONENTS_BUILT','builds':builds,'audits':audits,'fixtures':headers,'sources':[artifact(p) for p in sources],
            'database_provider':provider,'baseline':artifact(BASE),'builder':artifact(Path(__file__).resolve()),
            'original_nonvirtual_delete_diagnostic':artifact(root/'original_nonvirtual_warning.log'),
            'original_only_warning_exemption':'C5205',
            'gamecore_loaded':False,'game_launched':False,
            'scope':'EXACT_SDK_CACHE_TYPES_PREFETCH_AND_CONTIGUOUS_GC_DATABASE_PHASE_REAL_SQLITE_INSTRUMENTED_RULE_ENTRIES_HOST_AND_GAME_STAGES'}
    (root/'build_result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(report['status'])


if __name__=='__main__': main()
