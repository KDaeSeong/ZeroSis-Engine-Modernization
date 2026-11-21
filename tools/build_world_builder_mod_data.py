"""Build the actual mod-data implementation against isolated access declarations."""
import json
from pathlib import Path
from collect_baseline import PROJECT,read_text,pe_header
from native_build import run,checked_run,environment_for
from probe_world_builder import artifact
from world_builder_mod_access import isolated_headers,patches

def main():
    from world_builder_types_evidence import validate as types_validate
    from foundation_evidence import validate as foundation_validate
    _,_,types=types_validate();_,_,foundation=foundation_validate(PROJECT/'evidence/foundation/build_result.json')
    out=PROJECT/'Build/WorldBuilder/mod_data_x64';evidence=PROJECT/'evidence/world_builder/mod_data'
    out.mkdir(parents=True,exist_ok=True);evidence.mkdir(parents=True,exist_ok=True)
    generated=out/'access_headers';headers=isolated_headers(generated);sdk=PROJECT/'Source/SDK_BNW_x64';provider=PROJECT/'Source/Providers/WorldBuilder'
    env,compiler=environment_for(Path(r'C:\Program Files\Microsoft Visual Studio\2022\Community'),'x64',out);compiler=Path(compiler)
    flags=['/nologo','/O2','/MD','/EHsc','/W4','/WX','/fp:strict','/std:c++14','/utf-8','/DWIN32','/DFINAL_RELEASE','/D_CRT_SECURE_NO_WARNINGS',
        '/D_SECURE_SCL=0','/D_HAS_ITERATOR_DEBUGGING=0','/DFXS_IS_DLL','/external:W0']
    flags += [f'/I"{p}"' for p in [provider,PROJECT/'Source/Providers/Streams',PROJECT/'Source/Porting']]
    flags += [f'/external:I"{p}"' for p in [generated/'FirePlace/include',generated/'CvWorldBuilderMap/include',
        sdk/'FirePlace/include',sdk/'FirePlace/include/FireWorks',sdk/'CvWorldBuilderMap/include']]
    objects=[];logs=[];responses=[]
    def compile_one(name,args,link=()):
        rsp=out/(name+'.rsp');rsp.write_text('\n'.join(args),encoding='utf-8');responses.append(artifact(rsp))
        r=run([compiler,'@'+str(rsp),*(['/link',*link] if link else [])],cwd=out,env=env)
        log=evidence/(name+'_build.log');log.write_bytes(r.stdout+r.stderr);logs.append(artifact(log))
        if r.returncode:raise RuntimeError(read_text(log)[:10000])
    sources=[provider/'SdkWorldBuilderModData.cpp',provider/'SdkWorldBuilderModDataWire.cpp']
    for source in sources:
        obj=out/(source.stem+'.obj');compile_one(source.stem,flags+['/c',f'"{source}"',f'/Fo"{obj}"']);objects.append(artifact(obj))
    library=out/'ZeroSis_WorldBuilderModData_x64.lib'
    checked_run([compiler.with_name('lib.exe'),'/nologo','/Brepro',f'/OUT:{library}',*[r['path'] for r in objects]],cwd=out,env=env)
    consumers={}
    for name in ('mod_data','mod_data_hardening'):
        source=PROJECT/('Tests/sdk_world_builder_'+name+'.cpp')
        if not source.is_file():continue
        exe=out/(name+'.exe');linkmap=out/(name+'.map');libraries=[library,Path(types['library']['path']),Path(foundation['library']['path'])]
        compile_one(name,flags+[f'"{p}"' for p in [source]+libraries]+[f'/Fo"{out/(name+".obj")}"',f'/Fe"{exe}"'],
            ['/INCREMENTAL:NO','/OPT:REF','/OPT:ICF','/MACHINE:X64',f'/MAP:{linkmap}','kernel32.lib'])
        consumers[name]={'source':artifact(source),'executable':{**artifact(exe),'pe':pe_header(exe)},'map':artifact(linkmap)}
    integrated=all(p['new'].encode('latin1') in (sdk/p['file']).read_bytes() for p in patches())
    report={'status':'WORLD_BUILDER_MOD_DATA_BUILT' if integrated else 'WORLD_BUILDER_MOD_DATA_BUILT_ISOLATED_HEADERS','runtime':'/MD','sources':[artifact(p) for p in sources]
        +[artifact(provider/name) for name in ['SdkWorldBuilderModData.h','SdkWorldBuilderModDataWire.h','SdkWorldBuilderIncludes.h']]
        +[artifact(PROJECT/'Tests/sdk_world_builder_trace.cpp'),artifact(PROJECT/'Source/Providers/Streams/SdkStreamIncludes.h')],
        'objects':objects,'library':artifact(library),'consumers':consumers,'generated_headers':headers,'header_builder':artifact(PROJECT/'tools/world_builder_mod_access.py'),
        'builder':artifact(Path(__file__).resolve()),'compiler':artifact(compiler),'flags':flags,'logs':logs,'responses':responses,'dependencies':[types,foundation],
        'sdk_port_manifest':artifact(PROJECT/'evidence/sdk_x64/port_manifest.json'),'sdk_patch_specification':artifact(PROJECT/'Source/Porting/sdk_x64_patches.json'),
        'gamecore_loaded':False,'game_launched':False,'sdk_access_declarations_integrated':integrated}
    (evidence/'build_result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(report['status'])

if __name__=='__main__':main()
