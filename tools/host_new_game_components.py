"""Build and verify headless new-game host services and the actual Lua extensions."""
import argparse,json,re,shutil
from pathlib import Path
from collect_baseline import PROJECT,read_text
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts
from native_build import run

ROOT=PROJECT/'evidence/host_new_game_components'
CASES={
    'services':('Tests/sdk_host_new_game_services.cpp','HOST_NEW_GAME_SERVICES_PASS','Source/Host/HostServices.h'),
    'tables':('Tests/sdk_host_script_tables.cpp','HOST_SCRIPT_TABLES_PASS','Source/Host/ScriptTableExtensions.h'),
    'defines':('Tests/sdk_host_game_defines.cpp','HOST_GAME_DEFINES_PASS','Source/Host/GameDefinesDatabase.h'),
    'math':('Tests/sdk_host_script_math.cpp','HOST_SCRIPT_MATH_PASS','Source/Host/ScriptMathExtensions.h'),
}

def build():
    from build_native_host import compile_program
    ROOT.mkdir(parents=True,exist_ok=True)
    lua=json.loads((PROJECT/'evidence/lua_provider/build_result.json').read_text());check_artifacts(lua['library'])
    database=json.loads((PROJECT/'evidence/database/candidate/build_result.json').read_text())
    check_artifacts([database['library'],database['dll']])
    builds={}
    for case,(test,_,_) in CASES.items():
        for optimization in ('O2','Od'):
            key=case+'_'+optimization
            libraries=[Path(lua['library']['path'])]
            if case=='defines':libraries.append(Path(database['library']['path']))
            builds[key]=compile_program('sdk_host_new_game_'+key,PROJECT/test,libraries=libraries,optimization='/'+optimization)
            if case=='defines':
                target=Path(builds[key]['executable']['path']).parent/Path(database['dll']['path']).name
                shutil.copy2(database['dll']['path'],target);builds[key]['database_copy']=artifact(target)
    report={'status':'HOST_NEW_GAME_COMPONENTS_BUILT','builder':artifact(Path(__file__).resolve()),
        'lua_library':lua['library'],'database_inputs':[database['library'],database['dll']],'builds':builds}
    (ROOT/'build_result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(report['status'],flush=True)

def verify():
    builds=json.loads((ROOT/'build_result.json').read_text());check_artifacts(builds);runs=[]
    for key,item in builds['builds'].items():
        case=key.split('_')[0];exe=Path(item['executable']['path'])
        result=run([exe],cwd=exe.parent,timeout=90)
        log=ROOT/(key+'.log');log.write_bytes(result.stdout+result.stderr);output=read_text(log)
        match=re.search(CASES[case][1]+r' checks=(\d+) GAMECORE_LOADED=false',output)
        if result.returncode or not match or int(match[1])<=0:raise RuntimeError(key+f' exit=0x{result.returncode&0xffffffff:08X}: '+output[-5000:])
        runs.append({'configuration':key,'checks':int(match[1]),'exit_code':result.returncode,'log':artifact(log)})
    report={'status':'HOST_NEW_GAME_COMPONENTS_PASS','build':artifact(ROOT/'build_result.json'),
        'validator':artifact(Path(__file__).resolve()),'runs':runs,'native_checks':sum(r['checks'] for r in runs),
        'gamecore_loaded':False,'original_closed_engine_equivalence_verified':False,
        'scope':'HEADLESS_NOTIFICATIONS_SLOT_STATE_LUA_TABLE_EXTENSION_AND_LIVE_DEFINES_COMPONENTS'}
    (ROOT/'conformance.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'status':report['status'],'native_checks':report['native_checks'],'process_runs':len(runs)}),flush=True)

def validate():
    builds=json.loads((ROOT/'build_result.json').read_text());report=json.loads((ROOT/'conformance.json').read_text())
    check_artifacts([builds,report]);expected={case+'_'+opt for case in CASES for opt in ('O2','Od')}
    if builds['builder']!=artifact(Path(__file__).resolve()) or report['validator']!=artifact(Path(__file__).resolve()):
        raise RuntimeError('New-game component tool provenance differs')
    if report['status']!='HOST_NEW_GAME_COMPONENTS_PASS' or set(builds['builds'])!=expected or {r['configuration'] for r in report['runs']}!=expected or len(report['runs'])!=len(expected):
        raise RuntimeError('New-game component coverage differs')
    for row in report['runs']:
        key=row['configuration'];case=key.split('_')[0];item=builds['builds'][key]
        compiled={Path(r['path']):r['sha256'] for r in item['compiler_inputs']}
        for relative in (CASES[case][0],CASES[case][2]):
            source=PROJECT/relative
            if compiled.get(source)!=artifact(source)['sha256']:raise RuntimeError('New-game component source not consumed: '+relative)
        output=read_text(Path(row['log']['path']))
        if row['exit_code'] or row['checks']<=0 or CASES[case][1]+f" checks={row['checks']} GAMECORE_LOADED=false" not in output:
            raise RuntimeError('New-game component execution differs')
    if report['native_checks']!=sum(r['checks'] for r in report['runs']) or report['gamecore_loaded'] or report['original_closed_engine_equivalence_verified']:
        raise RuntimeError('New-game component scope differs')
    return report,{'name':'HostNewGameComponents','build':artifact(ROOT/'build_result.json'),
        'conformance':artifact(ROOT/'conformance.json'),'validator':artifact(Path(__file__).resolve())}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=('build','verify','validate'));args=parser.parse_args()
    if args.mode=='build':build()
    elif args.mode=='verify':verify()
    else:result,_=validate();print(json.dumps({'status':result['status'],'checks':result['native_checks']}))
