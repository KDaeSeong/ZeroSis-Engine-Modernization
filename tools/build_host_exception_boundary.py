"""Build a disposable throwing DLL and exact host-session consumers; never load GameCore."""
import argparse,json,re,shutil
from pathlib import Path
from collect_baseline import PROJECT,read_text,pe_header
from native_build import environment_for,run,checked_run
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts

ROOT=PROJECT/'evidence/host_exception_boundary'

def compile_one(name,source,optimization,baseline=False,dll=False,libraries=()):
    directory=PROJECT/'Build/HostExceptionBoundary'/name
    env,compiler=environment_for(Path(r'C:\Program Files\Microsoft Visual Studio\2022\Community'),'x64',directory)
    compiler=Path(compiler);env['VSLANG']='1033'
    output=directory/('ZeroSisHostExceptionFixture.dll' if dll else 'HostExceptionBoundary.exe')
    sdk=PROJECT/'Source/SDK_BNW_x64'
    includes=[sdk/r for r in ('CvGameCoreDLL_Expansion2','CvGameCoreDLLUtil/include','CvGameDatabase/include',
        'CvLocalization/include','CvWorldBuilderMap/include','FirePlace/include','FirePlace/include/FireWorks','ThirdPartyLibs/Lua51/include')]
    flags=['/nologo','/std:c++14','/EHsc','/W4','/WX',optimization,'/MD','/fp:strict','/source-charset:windows-1252',
        '/external:W0','/DWIN32','/DNDEBUG','/DFINAL_RELEASE','/D_CRT_SECURE_NO_WARNINGS',
        '/D_SILENCE_STDEXT_HASH_DEPRECATION_WARNINGS','/D_SILENCE_TR1_NAMESPACE_DEPRECATION_WARNING',
        '/DBOUNDARY_BASELINE='+str(int(baseline))]
    if dll:flags.append('/LD')
    flags += [f'/external:I"{p}"' for p in includes]
    flags += [f'/I"{PROJECT/p}"' for p in ('Source/Host','Source/HostExceptionBoundary','Source/LuaBorrowed','Source/Porting','Tests')]
    deps=directory/'dependencies.json';mapfile=directory/'linked.map'
    flags += [f'"{p}"' for p in (source,*libraries)]
    flags += [f'/Fo"{directory.as_posix()}/"',f'/Fe"{output}"',f'/sourceDependencies "{deps}"']
    rsp=directory/'compile.rsp';rsp.write_text('\n'.join(flags)+'\n',encoding='utf-8')
    result=run([compiler,'@'+str(rsp),'/link','/INCREMENTAL:NO','/MACHINE:X64','/Brepro','/WX','/OPT:REF','/OPT:ICF',
        '/MAP:'+str(mapfile)],cwd=directory,env=env,timeout=180)
    log=ROOT/(name+'_build.log');log.write_bytes(result.stdout+result.stderr)
    if result.returncode or re.search(r'\bwarning\s+[A-Z]+\d+',read_text(log)):raise RuntimeError(read_text(log)[-6500:])
    inspection=checked_run([compiler.with_name('dumpbin.exe'),'/dependents',output],cwd=directory,env=env)
    imports=ROOT/(name+'_imports.log');imports.write_bytes(inspection.stdout+inspection.stderr)
    names=re.findall(r'^\s+([\w.-]+\.dll)\s*$',read_text(imports),re.M|re.I)
    allowed={'kernel32.dll','msvcp140.dll','vcruntime140.dll','vcruntime140_1.dll','zerosisdatabase_x64.dll'}
    if not names or any(n.lower() not in allowed and not n.lower().startswith('api-ms-win-crt-') for n in names):
        raise RuntimeError('Unexpected exception component dependency')
    consumed=json.loads(deps.read_text(encoding='utf-8-sig'))['Data']
    return dict(binary={**artifact(output),'pe':pe_header(output)},compiler=artifact(compiler),optimization=optimization,
        response=artifact(rsp),map=artifact(mapfile),log=artifact(log),dependency_report=artifact(deps),
        compiler_inputs=[artifact(Path(f)) for f in (consumed['Source'],*consumed['Includes'])],imports=names,imports_log=artifact(imports))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--variant',choices=('original','candidate','all'),default='all')
    args=parser.parse_args();ROOT.mkdir(parents=True,exist_ok=True)
    database=json.loads((PROJECT/'evidence/database/candidate/build_result.json').read_text(encoding='utf-8'))
    lua=json.loads((PROJECT/'evidence/lua_provider/build_result.json').read_text(encoding='utf-8'))
    inputs=[database['dll'],database['library'],lua['library']];check_artifacts(inputs)
    baseline=json.loads((ROOT/'baseline.json').read_text(encoding='utf-8'));check_artifacts(baseline['snapshot'])
    path=ROOT/'build_result.json'
    builds=json.loads(path.read_text(encoding='utf-8'))['builds'] if path.exists() else {}
    for optimization,suffix in (('/O2','o2'),('/Od','od')):
        fixture='fixture_'+suffix
        if args.variant!='candidate' or fixture not in builds:
            builds[fixture]=compile_one(fixture,PROJECT/'Tests/host_exception_fixture.cpp',optimization,dll=True)
        else:check_artifacts(builds[fixture])
        for variant in ('original','candidate') if args.variant=='all' else (args.variant,):
            name=variant+'_'+suffix
            builds[name]=compile_one(name,PROJECT/'Tests/sdk_host_exception_boundary.cpp',optimization,
                baseline=variant=='original',libraries=[Path(database['library']['path']),Path(lua['library']['path'])])
            directory=Path(builds[name]['binary']['path']).parent
            target=directory/Path(database['dll']['path']).name;shutil.copy2(database['dll']['path'],target)
            builds[name]['runtime_copy']=artifact(target)
    report=dict(status='HOST_EXCEPTION_BOUNDARY_COMPILED',builder=artifact(Path(__file__).resolve()),
        builds=builds,provider_inputs=inputs,baseline=artifact(ROOT/'baseline.json'),
        gamecore_loaded=False,game_launched=False,
        scope='EXACT_HOST_SESSION_WITH_REAL_FOREIGN_EXCEPTION_DLL_AND_INSTRUMENTED_SDK_CONTEXT')
    path.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':report['status'],'builds':list(builds)}))

if __name__=='__main__':main()
