"""Compile, execute and bind the actual GameInfo/Lua/database component tests."""
import argparse,json,re,shutil
from pathlib import Path
from collect_baseline import PROJECT,read_text
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts
from native_build import run

ROOT=PROJECT/'evidence/host_game_info'

def build():
    from build_native_host import compile_program
    ROOT.mkdir(parents=True,exist_ok=True)
    database=json.loads((PROJECT/'evidence/database/candidate/build_result.json').read_text())
    lua=json.loads((PROJECT/'evidence/lua_provider/build_result.json').read_text())
    inputs=[database['library'],database['dll'],lua['library']];check_artifacts(inputs)
    builds={}
    for optimization in ('O2','Od'):
        result=compile_program('sdk_host_game_info_'+optimization,PROJECT/'Tests/sdk_host_game_info.cpp',
            libraries=[Path(database['library']['path']),Path(lua['library']['path'])],optimization='/'+optimization)
        target=Path(result['executable']['path']).parent/Path(database['dll']['path']).name
        shutil.copy2(database['dll']['path'],target);result['database_copy']=artifact(target);builds[optimization]=result
    report={'status':'HOST_GAME_INFO_BUILT','builder':artifact(Path(__file__).resolve()),'builds':builds,'inputs':inputs}
    (ROOT/'build_result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(report['status'])

def verify():
    build=json.loads((ROOT/'build_result.json').read_text());check_artifacts(build);runs=[]
    for name,item in build['builds'].items():
        exe=Path(item['executable']['path']);result=run([exe],cwd=exe.parent,timeout=120)
        log=ROOT/(name+'.log');log.write_bytes(result.stdout+result.stderr);output=read_text(log)
        if result.returncode:raise RuntimeError(output[-4000:])
        marker=re.search(r'HOST_GAME_INFO_PASS checks=(\d+) GAMECORE_LOADED=false',output)
        failures=re.search(r'GAME_INFO_FAILURES lua=(\d+) cpp=(\d+)',output)
        creation=re.search(r'GAME_INFO_CREATE_FAILURES=(\d+)',output)
        if not marker or not failures or not creation:raise RuntimeError('GameInfo coverage markers missing')
        values=[int(marker[1]),int(failures[1]),int(failures[2]),int(creation[1])]
        if min(values)<=0:raise RuntimeError('GameInfo failure paths were not exercised')
        runs.append({'configuration':name,'log':artifact(log),'exit_code':result.returncode,'checks':values[0],
            'lua_query_failures':values[1],'cpp_query_failures':values[2],'vm_creation_failures':values[3]})
    report={'status':'HOST_GAME_INFO_COMPONENT_PASS','build':artifact(ROOT/'build_result.json'),
        'validator':artifact(Path(__file__).resolve()),'runs':runs,'native_checks':sum(row['checks'] for row in runs),
        'gamecore_loaded':False,'original_game_info_equivalence_verified':False,
        'scope':'ACTUAL_X64_LUA_AND_DATABASE_PROVIDER_WITH_SYNTHETIC_RULES_AND_FAILURE_INJECTION'}
    (ROOT/'conformance.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))

def validate():
    build=json.loads((ROOT/'build_result.json').read_text());report=json.loads((ROOT/'conformance.json').read_text())
    check_artifacts([build,report])
    if build['builder']!=artifact(Path(__file__).resolve()) or report['validator']!=artifact(Path(__file__).resolve()):
        raise RuntimeError('GameInfo tool provenance differs')
    if report['status']!='HOST_GAME_INFO_COMPONENT_PASS' or [r['configuration'] for r in report['runs']]!=['O2','Od']:
        raise RuntimeError('GameInfo optimization coverage missing')
    for name,item in build['builds'].items():
        compiled={Path(row['path']):row['sha256'] for row in item['compiler_inputs']}
        for relative in ('Source/Host/GameInfoDatabase.h','Source/Host/ScriptSystem.h','Source/Host/ScriptRules.h','Tests/sdk_host_game_info.cpp'):
            source=PROJECT/relative
            if compiled.get(source)!=artifact(source)['sha256']:raise RuntimeError('GameInfo source was not compiled: '+relative)
        row=next(r for r in report['runs'] if r['configuration']==name);output=read_text(Path(row['log']['path']))
        if row['exit_code'] or f"HOST_GAME_INFO_PASS checks={row['checks']} GAMECORE_LOADED=false" not in output:
            raise RuntimeError('GameInfo execution record differs')
        if f"GAME_INFO_FAILURES lua={row['lua_query_failures']} cpp={row['cpp_query_failures']}" not in output or f"GAME_INFO_CREATE_FAILURES={row['vm_creation_failures']}" not in output:
            raise RuntimeError('GameInfo failure accounting differs')
    if report['native_checks']!=sum(r['checks'] for r in report['runs']) or report['gamecore_loaded'] or report['original_game_info_equivalence_verified']:
        raise RuntimeError('GameInfo scope differs')
    return report,{'name':'HostGameInfo','build':artifact(ROOT/'build_result.json'),'conformance':artifact(ROOT/'conformance.json'),'validator':artifact(Path(__file__).resolve())}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=('build','verify','validate'));args=parser.parse_args()
    if args.mode=='build':build()
    elif args.mode=='verify':verify()
    else:report,_=validate();print(json.dumps({'status':report['status'],'checks':report['native_checks']}))
