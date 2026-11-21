"""Build a file/object oracle using the original x86 SDK archive, without GameCore."""
import json,os,re
from pathlib import Path
from collect_baseline import PROJECT,read_text,pe_header
from native_build import run,checked_run,environment_for
from probe_world_builder import artifact

def main():
    out=PROJECT/'Build/WorldBuilder/map_bridge_x86';evidence=PROJECT/'evidence/world_builder/map_bridge_reference'
    out.mkdir(parents=True,exist_ok=True);evidence.mkdir(parents=True,exist_ok=True)
    sdk=PROJECT/'Source/SDK_BNW_Original';provider=PROJECT/'Source/Providers'
    vc=Path(r'C:\Program Files (x86)\Microsoft Visual Studio 9.0\VC');win=Path(r'C:\Program Files (x86)\Microsoft SDKs\Windows\v7.0A')
    env={k.upper():v for k,v in os.environ.items()};env['INCLUDE']=f"{vc/'include'};{win/'Include'}";env['LIB']=f"{vc/'lib'};{win/'Lib'}"
    env['PATH']=f"{vc/'bin'};{vc.parent/'Common7/IDE'};{win/'bin'};{env.get('PATH','')}"
    flags=['/nologo','/O2','/MD','/EHsc','/W3','/DWIN32','/DFINAL_RELEASE','/DFXS_IS_DLL','/D_CRT_SECURE_NO_WARNINGS','/D_SECURE_SCL=0','/D_HAS_ITERATOR_DEBUGGING=0']
    inc=[provider/p for p in ('WorldBuilder','Streams','TempHeap','Foundation')]+[sdk/'FirePlace/include',sdk/'FirePlace/include/FireWorks',sdk/'CvWorldBuilderMap/include']
    flags += [f'/I"{p}"' for p in inc]
    sources=[PROJECT/'Tests'/n for n in ('sdk_world_builder_map_bridge.cpp','sdk_world_builder_map_file_host.cpp','sdk_temp_heap_strings.cpp','sdk_temp_heap_host.cpp')]
    libraries=[sdk/'CvWorldBuilderMap/lib/CvWorldBuilderMapWin32.lib',sdk/'FirePlace/lib/FireWorksWin32.lib']
    exe=out/'map_bridge.exe';linkmap=out/'map_bridge.map';rsp=out/'compile.rsp'
    rsp.write_text('\n'.join(flags+[f'"{p}"' for p in sources+libraries]+[f'/Fo"{out}\\\\"',f'/Fe"{exe}"']),encoding='utf-8')
    r=run([vc/'bin/cl.exe','@'+str(rsp),'/link','/LTCG','/INCREMENTAL:NO','/OPT:REF','/OPT:ICF','/MACHINE:X86',f'/MAP:{linkmap}',
        *[n+'.lib' for n in ('kernel32','user32','advapi32','psapi','dbghelp','ole32','shell32','winmm')]],cwd=out,env=env)
    log=evidence/'build.log';log.write_bytes(r.stdout+r.stderr)
    if r.returncode:raise RuntimeError(read_text(log)[-12000:])
    checked_run([win/'bin/mt.exe','-nologo','-manifest',exe.with_suffix('.exe.manifest'),f'-outputresource:{exe};1'],cwd=out,env=env)
    audit,cc=environment_for(Path(r'C:\Program Files\Microsoft Visual Studio\2022\Community'),'x64',out/'audit')
    r=checked_run([Path(cc).with_name('dumpbin.exe'),'/dependents',exe],cwd=out,env=audit);imports=evidence/'imports.log';imports.write_bytes(r.stdout+r.stderr)
    deps=re.findall(r'^\s+([\w.-]+\.dll)\s*$',r.stdout.decode('ascii',errors='replace'),re.M|re.I)
    allowed={'kernel32.dll','msvcr90.dll','msvcp90.dll','user32.dll','advapi32.dll','dbghelp.dll','psapi.dll','ole32.dll','shell32.dll','winmm.dll'}
    if not deps or any(d.lower() not in allowed for d in deps):raise RuntimeError('Unexpected original bridge imports')
    report={'status':'WORLD_BUILDER_MAP_BRIDGE_REFERENCE_BUILT','builder':artifact(Path(__file__).resolve()),'sources':[artifact(p) for p in sources]
        +[artifact(PROJECT/'Tests'/n) for n in ('sdk_world_builder_map.cpp','sdk_world_builder_map_file_host.h','sdk_world_builder_map_state.h','sdk_stream_reference_host.cpp')]
        +[artifact(provider/n) for n in ('WorldBuilder/SdkWorldBuilderMapIncludes.h','WorldBuilder/SdkWorldBuilderIncludes.h','Streams/SdkStreamIncludes.h','TempHeap/SdkTempHeapIncludes.h','Foundation/SdkFoundationIncludes.h')],
        'sdk_inputs':[artifact(p) for p in libraries]+[artifact(p) for p in (sdk/'CvWorldBuilderMap/include').glob('*.h')]
            +[artifact(p) for p in (sdk/'FirePlace/include').rglob('*') if p.is_file() and p.suffix.lower() in ('.h','.inl')],
        'compiler':artifact(vc/'bin/cl.exe'),'response':artifact(rsp),'build_log':artifact(log),'executable':{**artifact(exe),'pe':pe_header(exe)},'map':artifact(linkmap),
        'imports':{'dependencies':deps,'log':artifact(imports)},'gamecore_loaded':False,'game_launched':False}
    (evidence/'build_result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(report['status'])

if __name__=='__main__':main()
