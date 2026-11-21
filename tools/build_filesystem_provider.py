"""Build the real Windows FIFile provider; never load GameCore or launch Civ V."""
import json,re
from pathlib import Path
from collect_baseline import PROJECT,read_text,pe_header
from native_build import run,checked_run,environment_for
from probe_world_builder import artifact

def main():
    out=PROJECT/'Build/FileSystem/x64';evidence=PROJECT/'evidence/filesystem'
    out.mkdir(parents=True,exist_ok=True);evidence.mkdir(parents=True,exist_ok=True)
    env,compiler=environment_for(Path(r'C:\Program Files\Microsoft Visual Studio\2022\Community'),'x64',out);compiler=Path(compiler)
    provider=PROJECT/'Source/Providers/FileSystem';sdk=PROJECT/'Source/SDK_BNW_x64'
    flags=['/nologo','/O2','/Gy','/MD','/EHsc','/W4','/WX','/std:c++14','/utf-8','/DWIN32','/DFINAL_RELEASE','/DFXS_IS_DLL',
           '/D_CRT_SECURE_NO_WARNINGS','/D_SECURE_SCL=0','/D_HAS_ITERATOR_DEBUGGING=0','/external:W0']
    flags += [f'/I"{p}"' for p in (provider,PROJECT/'Tests')]
    flags += [f'/external:I"{sdk/"FirePlace/include"}"']
    logs=[];responses=[]
    def compile_one(name,args,link=()):
        rsp=out/(name+'.rsp');rsp.write_text('\n'.join(args)+'\n',encoding='utf-8');responses.append(artifact(rsp))
        r=run([compiler,'@'+str(rsp),*(['/link',*link] if link else [])],cwd=out,env=env,timeout=120)
        log=evidence/(name+'_build.log');log.write_bytes(r.stdout+r.stderr);logs.append(artifact(log))
        if r.returncode:raise RuntimeError(read_text(log)[-10000:])
    source=provider/'SdkFileSystem.cpp';obj=out/'SdkFileSystem.obj'
    compile_one('provider',flags+['/c',f'"{source}"',f'/Fo"{obj}"'])
    library=out/'ZeroSis_FileSystem_x64.lib'
    checked_run([compiler.with_name('lib.exe'),'/nologo','/Brepro',f'/OUT:{library}',obj],cwd=out,env=env)
    consumers={}
    test=PROJECT/'Tests/sdk_filesystem.cpp';exe=out/'filesystem.exe';linkmap=out/'filesystem.map'
    compile_one('filesystem',flags+[f'"{test}"',f'"{library}"',f'/Fo"{out/"filesystem.obj"}"',f'/Fe"{exe}"'],
                ['/INCREMENTAL:NO','/OPT:REF','/OPT:ICF','/MACHINE:X64',f'/MAP:{linkmap}','kernel32.lib'])
    r=checked_run([compiler.with_name('dumpbin.exe'),'/dependents',exe],cwd=out,env=env)
    log=evidence/'filesystem_imports.log';log.write_bytes(r.stdout+r.stderr)
    deps=re.findall(r'^\s+([\w.-]+\.dll)\s*$',r.stdout.decode('ascii',errors='replace'),re.M|re.I)
    if not deps or any(d.lower() not in {'kernel32.dll','msvcp140.dll','vcruntime140.dll','vcruntime140_1.dll'} and not d.lower().startswith('api-ms-win-crt-') for d in deps):
        raise RuntimeError('Unexpected filesystem imports: '+repr(deps))
    if pe_header(exe)['architecture']!='x64':raise RuntimeError('Not an x64 consumer')
    consumers['filesystem']={'source':artifact(test),'executable':{**artifact(exe),'pe':pe_header(exe)},'map':artifact(linkmap),'imports':{'dependencies':deps,'log':artifact(log)}}
    from world_builder_map_bridge_evidence import provider as map_provider
    map_build,_,map_entry=map_provider()
    map_out=PROJECT/'Build/WorldBuilder/map_bridge_x64'
    map_flags=flags+['/D_SILENCE_STDEXT_HASH_DEPRECATION_WARNINGS','/D_SILENCE_CXX17_AUTO_PTR_DEPRECATION_WARNING']
    map_flags += [f'/I"{p}"' for p in (map_out,PROJECT/'Source/Providers/WorldBuilder',PROJECT/'Source/Providers/Streams',PROJECT/'Source/Porting')]
    map_flags += [f'/external:I"{sdk/p}"' for p in ('FirePlace/include/FireWorks','CvWorldBuilderMap/include')]
    source=PROJECT/'Tests/sdk_filesystem_map.cpp';exe=out/'filesystem_map.exe';linkmap=out/'filesystem_map.map'
    libraries=[library,Path(map_build['library']['path'])]+[Path(p['library']['path']) for p in map_build['dependencies']]
    compile_one('filesystem_map',map_flags+[f'"{source}"',*[f'"{p}"' for p in libraries],f'/Fo"{out/"filesystem_map.obj"}"',f'/Fe"{exe}"'],
                ['/INCREMENTAL:NO','/OPT:REF','/OPT:ICF','/MACHINE:X64',f'/MAP:{linkmap}','kernel32.lib'])
    r=checked_run([compiler.with_name('dumpbin.exe'),'/dependents',exe],cwd=out,env=env)
    log=evidence/'filesystem_map_imports.log';log.write_bytes(r.stdout+r.stderr)
    deps=re.findall(r'^\s+([\w.-]+\.dll)\s*$',r.stdout.decode('ascii',errors='replace'),re.M|re.I)
    if not deps or any(d.lower() not in {'kernel32.dll','msvcp140.dll','vcruntime140.dll','vcruntime140_1.dll'} and not d.lower().startswith('api-ms-win-crt-') for d in deps):
        raise RuntimeError('Unexpected map filesystem imports: '+repr(deps))
    consumers['filesystem_map']={'source':artifact(source),'executable':{**artifact(exe),'pe':pe_header(exe)},'map':artifact(linkmap),'imports':{'dependencies':deps,'log':artifact(log)}}
    source=provider/'SdkFileSystem.cpp'
    report={'status':'FILESYSTEM_X64_PROVIDER_BUILT','runtime':'/MD','library':artifact(library),'objects':[artifact(obj)],'consumers':consumers,
            'sources':[artifact(source),artifact(provider/'SdkFileSystem.h'),artifact(PROJECT/'Tests/sdk_filesystem_faults.h')],
            'sdk_headers':[artifact(sdk/'FirePlace/include/FireWorks'/name) for name in ('FIFile.h','FFileSystem.h','FFileDefines.h','FFireTypes.h')],
            'builder':artifact(Path(__file__).resolve()),'compiler':artifact(compiler),'flags':flags,'logs':logs,'responses':responses,
            'map_provider':map_entry,'map_dependencies':map_build['dependencies'],'map_fixture':artifact(map_out/'map_fixture_bridge.h'),
            'gamecore_loaded':False,'game_launched':False,'production_filesystem_implemented':True}
    (evidence/'build_result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(report['status'])
if __name__=='__main__':main()
