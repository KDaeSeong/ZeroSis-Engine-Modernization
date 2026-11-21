"""Observe actual archived WorldBuilder code in a bounded, import-audited process."""
import json
import os
from pathlib import Path
import re
from collect_baseline import PROJECT,digest,pe_header,read_text
from native_build import run,checked_run,environment_for

def artifact(p): return {'path':str(p),'sha256':digest(p)}

def main():
    out=PROJECT/'Build/WorldBuilder/reference_x86';evidence=PROJECT/'evidence/world_builder/reference'
    out.mkdir(parents=True,exist_ok=True);evidence.mkdir(parents=True,exist_ok=True)
    sdk=PROJECT/'Source/SDK_BNW_Original';provider=PROJECT/'Source/Providers/WorldBuilder'
    vc=Path(r'C:\Program Files (x86)\Microsoft Visual Studio 9.0\VC');win=Path(r'C:\Program Files (x86)\Microsoft SDKs\Windows\v7.0A')
    env={k.upper():v for k,v in os.environ.items()};env['INCLUDE']=f"{vc/'include'};{win/'Include'}";env['LIB']=f"{vc/'lib'};{win/'Lib'}"
    env['PATH']=f"{vc/'bin'};{vc.parent/'Common7/IDE'};{win/'bin'};{env.get('PATH','')}"
    flags=['/nologo','/O2','/MD','/EHsc','/W3','/DWIN32','/DFINAL_RELEASE','/D_CRT_SECURE_NO_WARNINGS','/D_SECURE_SCL=0','/D_HAS_ITERATOR_DEBUGGING=0']
    includes=[provider,PROJECT/'Source/Providers/Streams',sdk/'FirePlace/include',sdk/'CvWorldBuilderMap/include']
    flags += [f'/I"{p}"' for p in includes]
    sources=[PROJECT/'Tests/sdk_world_builder_trace.cpp',PROJECT/'Tests/sdk_stream_reference_host.cpp']
    libraries=[sdk/'CvWorldBuilderMap/lib/CvWorldBuilderMapWin32.lib',sdk/'FirePlace/lib/FireWorksWin32.lib']
    exe=out/'world_builder_trace.exe';linkmap=out/'world_builder_trace.map';response=out/'compile.rsp'
    flags += [f'"{p}"' for p in sources+libraries]+[f'/Fo"{out}\\\\"',f'/Fe"{exe}"']
    response.write_text('\n'.join(flags),encoding='utf-8')
    result=run([vc/'bin/cl.exe','@'+str(response),'/link','/LTCG','/INCREMENTAL:NO','/OPT:REF','/OPT:ICF','/MACHINE:X86',f'/MAP:{linkmap}',
                *[n+'.lib' for n in ('kernel32','user32','advapi32','psapi','dbghelp','ole32','shell32','winmm')]],cwd=out,env=env)
    log=evidence/'build.log';log.write_bytes(result.stdout+result.stderr)
    if result.returncode:raise RuntimeError(read_text(log)[:9000])
    checked_run([win/'bin/mt.exe','-nologo','-manifest',exe.with_suffix('.exe.manifest'),f'-outputresource:{exe};1'],cwd=out,env=env)
    audit_env,compiler=environment_for(Path(r'C:\Program Files\Microsoft Visual Studio\2022\Community'),'x64',out/'audit')
    result=checked_run([Path(compiler).with_name('dumpbin.exe'),'/dependents',exe],cwd=out,env=audit_env)
    imports=evidence/'imports.log';imports.write_bytes(result.stdout+result.stderr)
    deps=re.findall(r'^[ \t]+([^\\:\r\n]+\.dll)[ \t]*\r?$',result.stdout.decode('mbcs',errors='replace'),re.M|re.I)
    allowed={'kernel32.dll','msvcr90.dll','msvcp90.dll','user32.dll','advapi32.dll','dbghelp.dll','psapi.dll','ole32.dll','shell32.dll','winmm.dll'}
    if not deps or any(n.lower() not in allowed for n in deps):raise RuntimeError('Unexpected reference dependencies: '+str(deps))
    runs=[]
    for mode in ('groups','types','mods','self','palette','length_254','length_255','length_256','length_257','corpus'):
        result=run([exe,mode],cwd=out,timeout=20);log=evidence/(mode+'.log');log.write_bytes(result.stdout+result.stderr)
        match=re.search(r'^PASS\|(\d+)\s*$',read_text(log).replace('\r\n','\n'),re.M)
        row={'mode':mode,'exit_code':result.returncode,'checks':int(match[1]) if match else 0,'log':artifact(log)};runs.append(row);print(json.dumps(row),flush=True)
    report={'status':'WORLD_BUILDER_REFERENCE_OBSERVED' if all(r['exit_code']==0 and r['checks'] for r in runs) else 'WORLD_BUILDER_REFERENCE_FAILURES',
            'sources':[artifact(p) for p in sources]+[artifact(provider/'SdkWorldBuilderIncludes.h'),artifact(PROJECT/'Source/Providers/Streams/SdkStreamIncludes.h')],
            'sdk_inputs':[artifact(p) for p in sorted((sdk/'CvWorldBuilderMap/include').glob('*.h'))]+[artifact(p) for p in libraries]
                +[artifact(p) for p in (sdk/'FirePlace/include').rglob('*') if p.is_file() and p.suffix.lower() in ('.h','.inl')],
            'compiler':artifact(vc/'bin/cl.exe'),'builder':artifact(Path(__file__).resolve()),'response':artifact(response),
            'executable':{**artifact(exe),'pe':pe_header(exe)},'map':artifact(linkmap),'build_log':artifact(evidence/'build.log'),
            'imports':{'dependencies':deps,'log':artifact(imports)},'runs':runs,'game_launched':False,'gamecore_loaded':False}
    (evidence/'observations.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    if report['status'].endswith('FAILURES'):raise SystemExit(1)

if __name__=='__main__':main()
