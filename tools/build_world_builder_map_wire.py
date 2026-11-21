"""Build the native fixed-width map-file codec; no SDK/GameCore ABI substitution."""
import json
from pathlib import Path
from collect_baseline import PROJECT,read_text,pe_header
from native_build import run,checked_run,environment_for
from probe_world_builder import artifact

def main():
    out=PROJECT/'Build/WorldBuilder/map_wire_x64';evidence=PROJECT/'evidence/world_builder/map_wire'
    out.mkdir(parents=True,exist_ok=True);evidence.mkdir(parents=True,exist_ok=True)
    provider=PROJECT/'Source/Providers/WorldBuilder'
    env,cc=environment_for(Path(r'C:\Program Files\Microsoft Visual Studio\2022\Community'),'x64',out);cc=Path(cc)
    flags=['/nologo','/O2','/MD','/EHsc','/W4','/WX','/fp:strict','/std:c++14','/utf-8',f'/I"{provider}"']
    logs=[];responses=[];objects=[]
    def compile_one(name,args,link=()):
        rsp=out/(name+'.rsp');rsp.write_text('\n'.join(args),encoding='utf-8');responses.append(artifact(rsp))
        r=run([cc,'@'+str(rsp),*(['/link',*link] if link else [])],cwd=out,env=env)
        log=evidence/(name+'_build.log');log.write_bytes(r.stdout+r.stderr);logs.append(artifact(log))
        if r.returncode:raise RuntimeError(read_text(log)[-10000:])
    sources=[provider/'WorldBuilderMapWire.cpp',provider/'SdkWorldBuilderModDataWire.cpp']
    for source in sources:
        obj=out/(source.stem+'.obj');compile_one(source.stem,flags+['/c',f'"{source}"',f'/Fo"{obj}"']);objects.append(artifact(obj))
    library=out/'ZeroSis_WorldBuilderMapWire_x64.lib'
    checked_run([cc.with_name('lib.exe'),'/nologo','/Brepro',f'/OUT:{library}',*[r['path'] for r in objects]],cwd=out,env=env)
    consumers={}
    for name in ('world_builder_map_wire','world_builder_map_wire_hardening'):
        source=PROJECT/'Tests'/(name+'.cpp')
        if not source.is_file():continue
        exe=out/(name+'.exe');linkmap=out/(name+'.map')
        compile_one(name,flags+[f'"{source}"',f'"{library}"',f'/Fo"{out/(name+".obj")}"',f'/Fe"{exe}"'],
            ['/INCREMENTAL:NO','/OPT:REF','/OPT:ICF','/MACHINE:X64',f'/MAP:{linkmap}','kernel32.lib'])
        consumers[name]={'source':artifact(source),'executable':{**artifact(exe),'pe':pe_header(exe)},'map':artifact(linkmap)}
    report={'status':'WORLD_BUILDER_MAP_WIRE_BUILT','runtime':'/MD','library':artifact(library),'objects':objects,'consumers':consumers,
        'sources':[artifact(p) for p in sources]+[artifact(provider/n) for n in ['WorldBuilderMapWire.h','SdkWorldBuilderModDataWire.h']],
        'builder':artifact(Path(__file__).resolve()),'compiler':artifact(cc),'flags':flags,'logs':logs,'responses':responses,
        'sdk_map_object_integration':False,'gamecore_loaded':False,'game_launched':False}
    (evidence/'build_result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(report['status'])

if __name__=='__main__':main()
