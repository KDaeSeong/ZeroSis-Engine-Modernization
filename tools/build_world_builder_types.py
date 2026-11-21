"""Build the production x64 SDK WorldBuilder type/group archive and its consumers."""
import json
from pathlib import Path
from collect_baseline import PROJECT,pe_header,read_text
from native_build import environment_for,run,checked_run
from probe_world_builder import artifact

def main():
    out=PROJECT/'Build/WorldBuilder/types_x64';evidence=PROJECT/'evidence/world_builder/types'
    out.mkdir(parents=True,exist_ok=True);evidence.mkdir(parents=True,exist_ok=True)
    provider=PROJECT/'Source/Providers/WorldBuilder';sdk=PROJECT/'Source/SDK_BNW_x64'
    env,compiler=environment_for(Path(r'C:\Program Files\Microsoft Visual Studio\2022\Community'),'x64',out);compiler=Path(compiler)
    flags=['/nologo','/O2','/MD','/EHsc','/W4','/WX','/fp:strict','/std:c++14','/utf-8','/DWIN32','/DFINAL_RELEASE','/D_CRT_SECURE_NO_WARNINGS',
        '/D_SECURE_SCL=0','/D_HAS_ITERATOR_DEBUGGING=0','/DWORLD_BUILDER_TYPES_ONLY','/DFXS_IS_DLL','/external:W0']
    flags += [f'/I"{p}"' for p in [provider,PROJECT/'Source/Providers/Streams',PROJECT/'Source/Porting']]
    flags += [f'/external:I"{p}"' for p in [sdk/'FirePlace/include',sdk/'CvWorldBuilderMap/include']]
    responses=[];logs=[];objects=[]
    def compile_one(name,args,link=()):
        response=out/(name+'.rsp');response.write_text('\n'.join(args),encoding='utf-8');responses.append(artifact(response))
        result=run([compiler,'@'+str(response),*(['/link',*link] if link else [])],cwd=out,env=env)
        log=evidence/(name+'_build.log');log.write_bytes(result.stdout+result.stderr);logs.append(artifact(log))
        if result.returncode:raise RuntimeError(read_text(log)[:9000])
    sources=[provider/'SdkWorldBuilderTypes.cpp',provider/'SdkWorldBuilderGroups.cpp']
    for source in sources:
        obj=out/(source.stem+'.obj');compile_one(source.stem,flags+['/c',f'"{source}"',f'/Fo"{obj}"']);objects.append(artifact(obj))
    library=out/'ZeroSis_WorldBuilderTypes_x64.lib'
    checked_run([compiler.with_name('lib.exe'),'/nologo','/Brepro',f'/OUT:{library}',*[row['path'] for row in objects]],cwd=out,env=env)
    consumers={}
    for name in ('trace','hardening'):
        source=PROJECT/('Tests/sdk_world_builder_'+name+'.cpp')
        if not source.is_file():continue
        exe=out/(name+'.exe');linkmap=out/(name+'.map')
        compile_one(name,flags+[f'"{source}"',f'"{library}"',f'/Fo"{out/(name+".obj")}"',f'/Fe"{exe}"'],
                    ['/INCREMENTAL:NO','/OPT:REF','/OPT:ICF','/MACHINE:X64',f'/MAP:{linkmap}','kernel32.lib'])
        consumers[name]={'source':artifact(source),'executable':{**artifact(exe),'pe':pe_header(exe)},'map':artifact(linkmap)}
    report={'status':'WORLD_BUILDER_TYPES_BUILT','runtime':'/MD','library':artifact(library),'objects':objects,'consumers':consumers,
            'sources':[artifact(p) for p in sources+[provider/'SdkWorldBuilderIncludes.h',PROJECT/'Source/Providers/Streams/SdkStreamIncludes.h']],
            'sdk_inputs':[artifact(sdk/'CvWorldBuilderMap/include'/n) for n in ['CvWorldBuilderMapTypeDesc.h','CvWorldBuilderMapTypeGroup.h','CvWorldBuilderMapModData.h']]
                +[artifact(p) for p in (sdk/'FirePlace/include').rglob('*') if p.is_file() and p.suffix.lower() in ('.h','.inl')]
                +[artifact(PROJECT/'Source/Porting/CvCheckedNarrow.h')],
            'sdk_port_manifest':artifact(PROJECT/'evidence/sdk_x64/port_manifest.json'),
            'compiler':artifact(compiler),'builder':artifact(Path(__file__).resolve()),'flags':flags,'responses':responses,'logs':logs,
            'gamecore_loaded':False,'game_launched':False,'scope':'SDK type maps/groups; complete map and mod-data implementation pending'}
    (evidence/'build_result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(report['status'])

if __name__=='__main__':main()
