"""Build the SDK map file/object adapter with coherent isolated access headers."""
import json,re
from pathlib import Path
from collect_baseline import PROJECT,read_text,pe_header
from native_build import run,checked_run,environment_for
from probe_world_builder import artifact
from world_builder_map_bridge_access import isolated_headers,integrated

def main():
    from world_builder_types_evidence import validate as types_validate
    from world_builder_mod_data_evidence import validate as mod_validate
    from foundation_evidence import validate as foundation_validate
    from string_evidence import validate as strings_validate
    _,_,types=types_validate();_,_,mod=mod_validate();_,_,foundation=foundation_validate(PROJECT/'evidence/foundation/build_result.json');_,_,strings=strings_validate(PROJECT/'evidence/strings/build_result.json')
    dependencies=[types,mod,strings,foundation]
    out=PROJECT/'Build/WorldBuilder/map_bridge_x64';evidence=PROJECT/'evidence/world_builder/map_bridge'
    out.mkdir(parents=True,exist_ok=True);evidence.mkdir(parents=True,exist_ok=True)
    generated=out/'access_headers';headers=isolated_headers(generated);provider=PROJECT/'Source/Providers/WorldBuilder'
    original_fixture=PROJECT/'Tests/sdk_world_builder_map.cpp';fixture=out/'map_fixture_bridge.h';text=original_fixture.read_text(encoding='utf-8');marker='int main(int argc,char** argv) {'
    if text.count(marker)!=1:raise RuntimeError('Sealed fixture entry changed')
    fixture.write_text(text.split(marker)[0],encoding='utf-8')
    env,compiler=environment_for(Path(r'C:\Program Files\Microsoft Visual Studio\2022\Community'),'x64',out);compiler=Path(compiler)
    flags=['/nologo','/O2','/Gy','/MD','/EHsc','/W4','/WX','/fp:strict','/std:c++14','/utf-8','/DWIN32','/DFINAL_RELEASE','/D_CRT_SECURE_NO_WARNINGS',
        '/D_SECURE_SCL=0','/D_HAS_ITERATOR_DEBUGGING=0','/DFXS_IS_DLL','/D_SILENCE_STDEXT_HASH_DEPRECATION_WARNINGS','/D_SILENCE_CXX17_AUTO_PTR_DEPRECATION_WARNING','/external:W0']
    flags += [f'/I"{p}"' for p in (provider,PROJECT/'Source/Providers/Streams',PROJECT/'Source/Porting',PROJECT/'Tests',out)]
    flags += [f'/external:I"{p}"' for p in (generated/'FirePlace/include',generated/'FirePlace/include/FireWorks',generated/'CvWorldBuilderMap/include')]
    objects=[];logs=[];responses=[]
    def compile_one(name,args,link=()):
        rsp=out/(name+'.rsp');rsp.write_text('\n'.join(args),encoding='utf-8');responses.append(artifact(rsp))
        r=run([compiler,'@'+str(rsp),*(['/link',*link] if link else [])],cwd=out,env=env)
        log=evidence/(name+'_build.log');log.write_bytes(r.stdout+r.stderr);logs.append(artifact(log))
        if r.returncode:raise RuntimeError(read_text(log)[-12000:])
    sources=[provider/n for n in ('SdkWorldBuilderMap.cpp','SdkWorldBuilderMapBridge.cpp','SdkWorldBuilderMapFiles.cpp','WorldBuilderMapWire.cpp')]
    for source in sources:
        obj=out/(source.stem+'.obj');compile_one(source.stem,flags+['/c',f'"{source}"',f'/Fo"{obj}"']);objects.append(artifact(obj))
    library=out/'ZeroSis_WorldBuilderMapBridge_x64.lib';checked_run([compiler.with_name('lib.exe'),'/nologo','/Brepro',f'/OUT:{library}',*[r['path'] for r in objects]],cwd=out,env=env)
    test_objects=[];test_sources=[PROJECT/'Tests'/n for n in ('sdk_world_builder_map_bridge_memory_host.cpp','sdk_world_builder_map_bridge_binding.cpp')]
    for source in test_sources:
        obj=out/(source.stem+'.obj');compile_one(source.stem,flags+['/c',f'"{source}"',f'/Fo"{obj}"']);test_objects.append(artifact(obj))
    consumers={}
    for name,filename in (('map_bridge','sdk_world_builder_map_bridge.cpp'),('map_bridge_hardening','sdk_world_builder_map_bridge_hardening.cpp')):
        source=PROJECT/'Tests'/filename
        if not source.exists():continue
        exe=out/(name+'.exe');linkmap=out/(name+'.map');libraries=[library]+[Path(d['library']['path']) for d in dependencies]
        compile_one(name,flags+['/DZEROSIS_MAP_BRIDGE_NATIVE',f'"{source}"',*[f'"{p}"' for p in libraries],*[f'"{r["path"]}"' for r in test_objects],f'/Fo"{out/(name+".obj")}"',f'/Fe"{exe}"'],
            ['/INCREMENTAL:NO','/OPT:REF','/OPT:ICF','/MACHINE:X64',f'/MAP:{linkmap}','kernel32.lib'])
        r=checked_run([compiler.with_name('dumpbin.exe'),'/dependents',exe],cwd=out,env=env);log=evidence/(name+'_imports.log');log.write_bytes(r.stdout+r.stderr)
        deps=re.findall(r'^\s+([\w.-]+\.dll)\s*$',r.stdout.decode('ascii',errors='replace'),re.M|re.I)
        if not deps or any(d.lower() not in {'kernel32.dll','msvcp140.dll','vcruntime140.dll','vcruntime140_1.dll'} and not d.lower().startswith('api-ms-win-crt-') for d in deps):raise RuntimeError('Unexpected bridge imports: '+repr(deps))
        consumers[name]={'source':artifact(source),'executable':{**artifact(exe),'pe':pe_header(exe)},'map':artifact(linkmap),'imports':{'dependencies':deps,'log':artifact(log)}}
    sdk_integrated=integrated()
    report={'status':'WORLD_BUILDER_MAP_BRIDGE_BUILT' if sdk_integrated else 'WORLD_BUILDER_MAP_BRIDGE_BUILT_ISOLATED_HEADERS','runtime':'/MD','objects':objects,'library':artifact(library),'consumers':consumers,'test_host_objects':test_objects,
        'sources':[artifact(p) for p in sources+test_sources]+[artifact(provider/n) for n in ('SdkWorldBuilderMapBridge.h','SdkWorldBuilderMapPool.h','SdkWorldBuilderMapIncludes.h','SdkWorldBuilderIncludes.h','SdkWorldBuilderModData.h','SdkWorldBuilderModDataWire.h','WorldBuilderMapWire.h')]
            +[artifact(PROJECT/'Tests'/n) for n in ('sdk_world_builder_map.cpp','sdk_world_builder_map_file_host.cpp','sdk_world_builder_map_file_host.h','sdk_world_builder_map_state.h','sdk_world_builder_map_bridge_fault_host.h')]+[artifact(PROJECT/'Source/Providers/Streams/SdkStreamIncludes.h')],
        'generated_headers':headers,'generated_fixture':artifact(fixture),'header_builders':[artifact(PROJECT/'tools'/n) for n in ('world_builder_map_access.py','world_builder_map_bridge_access.py')],
        'builder':artifact(Path(__file__).resolve()),'compiler':artifact(compiler),'flags':flags,'logs':logs,'responses':responses,'dependencies':dependencies,
        'sdk_port_manifest':artifact(PROJECT/'evidence/sdk_x64/port_manifest.json'),'sdk_patch_specification':artifact(PROJECT/'Source/Porting/sdk_x64_patches.json'),
        'gamecore_loaded':False,'game_launched':False,'sdk_access_declarations_integrated':sdk_integrated,'file_bridge_implemented':True,'production_filesystem_implemented':False}
    (evidence/'build_result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(report['status'])

if __name__=='__main__':main()
