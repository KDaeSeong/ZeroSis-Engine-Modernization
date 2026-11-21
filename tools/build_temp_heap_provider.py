"""Build isolated original-SDK and x64 temporary arena allocation and host binding executables."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import re
from collect_baseline import PROJECT,digest,read_text,pe_header
from native_build import environment_for,run,checked_run

def artifact(path): return {'path':str(path),'sha256':digest(path)}

HEADERS=('FFireTypes.h','FDefNew.h','FAssert.h','FAtomic.h','FUncopyable.h','FTempHeap.h','FMemHooks.h')

def build(vs,reference_only=False):
    provider=PROJECT/'Source/Providers/TempHeap'
    evidence=PROJECT/'evidence/temp_heap';evidence.mkdir(parents=True,exist_ok=True)
    source=PROJECT/'Tests/sdk_temp_heap_trace.cpp'
    host=PROJECT/'Tests/sdk_temp_heap_host.cpp'
    strings=PROJECT/'Tests/sdk_temp_heap_strings.cpp'
    missing_host=PROJECT/'Tests/sdk_temp_heap_missing_host.cpp'
    foundation=None
    if not reference_only:
        from foundation_evidence import validate
        _,_,foundation=validate(PROJECT/'evidence/foundation/build_result.json')
    roots={a:PROJECT/('Source/SDK_BNW_Original' if a=='x86' else 'Source/SDK_BNW_x64') for a in ('x86','x64')}
    for row in json.loads((PROJECT/'evidence/sdk_reference/snapshot_manifest.json').read_text(encoding='utf-8')):
        if digest(Path(row['snapshot']))!=row['sha256'] or digest(Path(row['source']))!=row['sha256']:
            raise RuntimeError('Original SDK changed')
    result={}
    for arch in (('x86',) if reference_only else ('x86','x64')):
        out=PROJECT/'Build/TempHeap'/arch;out.mkdir(parents=True,exist_ok=True)
        sdk=roots[arch]
        vc=Path(r'C:\Program Files (x86)\Microsoft Visual Studio 9.0\VC')
        win=Path(r'C:\Program Files (x86)\Microsoft SDKs\Windows\v7.0A')
        if arch=='x86':
            env={k.upper():v for k,v in os.environ.items()}
            env['INCLUDE']=f"{vc/'include'};{win/'Include'}";env['LIB']=f"{vc/'lib'};{win/'Lib'}"
            env['PATH']=f"{vc/'bin'};{vc.parent/'Common7/IDE'};{win/'bin'};{env.get('PATH','')}"
            compiler=vc/'bin/cl.exe'
        else:env,compiler=environment_for(vs,arch,out);compiler=Path(compiler)
        flags=['/nologo','/EHsc','/O2','/MD','/fp:strict','/DWIN32','/DFXS_IS_DLL','/DFINAL_RELEASE','/D_CRT_SECURE_NO_WARNINGS',
            '/D_SECURE_SCL=0','/D_HAS_ITERATOR_DEBUGGING=0']
        flags+=['/W3' if arch=='x86' else '/W4',f'/I"{provider}"',f'/I"{PROJECT/"Source/Providers/Foundation"}"',f'/I"{PROJECT/"Source/Providers/Streams"}"']
        if arch=='x86':flags += [f'/I"{sdk/"FirePlace/include"}"']
        else:flags += ['/WX','/std:c++14','/DTEMP_HEAP_CANDIDATE','/external:W0',f'/external:I"{sdk/"FirePlace/include"}"']
        logs=[];objects=[];responses=[]
        def compile_run(name,args,link=()):
            rsp=out/(name+'.rsp');rsp.write_text('\n'.join(args),encoding='ascii');responses.append(artifact(rsp))
            r=run([compiler,f'@{rsp}',*(['/link',*link] if link else [])],cwd=out,env=env,timeout=120)
            log=evidence/(arch+'_'+name+'.log');log.write_bytes(r.stdout+r.stderr);logs.append(artifact(log))
            warnings=set(re.findall(r'\bwarning\s+([A-Z]+\d+)',read_text(log)))
            if r.returncode or warnings-({'C4819'} if arch=='x86' else set()):
                raise RuntimeError(read_text(log)[:6500])
        if arch=='x64':
            for cpp in sorted(provider.glob('*.cpp')):
                obj=out/(cpp.stem+'.obj');compile_run(cpp.stem,flags+['/c',f'"{cpp}"',f'/Fo"{obj}"']);objects.append(artifact(obj))
            if not objects:raise RuntimeError('No x64 temporary heap implementation')
            library=out/'ZeroSis_TempHeap_x64.lib'
            checked_run([compiler.with_name('lib.exe'),'/nologo','/Brepro',f'/OUT:{library}',*[o['path'] for o in objects]],cwd=out,env=env)
            libraries=[library,PROJECT/'Build/Foundation/x64/ZeroSis_Foundation_x64.lib'];sources=[source,host]
        else:libraries=[sdk/'FirePlace/lib/FireWorksWin32.lib'];sources=[source,host,strings]
        exe=out/'temp_heap_trace.exe';linkmap=out/'temp_heap_trace.map'
        link=['/INCREMENTAL:NO','/OPT:REF','/OPT:ICF',f'/MACHINE:{arch.upper()}',f'/MAP:{linkmap}']
        if arch=='x86':link+=['/LTCG']
        link += [n+'.lib' for n in ('kernel32','user32','advapi32','psapi','dbghelp','ole32','shell32','winmm')]
        compile_run('harness',flags+[f'"{s}"' for s in sources]+[f'/Fo"{out}\\\\"',f'/Fe"{exe}"']+[f'"{p}"' for p in libraries],link)
        if arch=='x86' and exe.with_suffix('.exe.manifest').exists():
            checked_run([win/'bin/mt.exe','-nologo','-manifest',exe.with_suffix('.exe.manifest'),f'-outputresource:{exe};1'],cwd=out,env=env)
        result[arch]={'executable':{**artifact(exe),'pe':pe_header(exe)},'libraries':[artifact(p) for p in libraries],
            'map':artifact(linkmap),'compiler':artifact(compiler),'objects':objects,'logs':logs,'responses':responses,'flags':flags,
            'warning_codes':sorted({code for log in logs for code in re.findall(r'\bwarning\s+([A-Z]+\d+)',read_text(Path(log['path'])))})}
        if arch=='x64':
            missing=out/'temp_heap_missing_host.exe';missing_map=out/'temp_heap_missing_host.map'
            missing_link=[f'/MAP:{missing_map}' if arg.startswith('/MAP:') else arg for arg in link]
            compile_run('missing_host_harness',flags+[f'"{missing_host}"',f'/Fo"{out / "missing_host.obj"}"',f'/Fe"{missing}"']+[f'"{p}"' for p in libraries],missing_link)
            result[arch]['missing_host']={'executable':{**artifact(missing),'pe':pe_header(missing)},'map':artifact(missing_map)}
            result[arch]['warning_codes']=sorted({code for log in logs for code in re.findall(r'\bwarning\s+([A-Z]+\d+)',read_text(Path(log['path'])))})
    result.update(status='SDK_TEMP_HEAP_REFERENCE_BUILT' if reference_only else 'TEMP_HEAP_PROVIDERS_BUILT',runtime='/MD',
        sources=[artifact(p) for p in sorted(provider.glob('*'))]+[artifact(source),artifact(host),artifact(strings),artifact(missing_host),
            artifact(PROJECT/'Tests/sdk_stream_reference_host.cpp'),artifact(PROJECT/'Source/Providers/Foundation/SdkFoundationIncludes.h'),
            artifact(PROJECT/'Source/Providers/Streams/SdkStreamIncludes.h'),artifact(Path(__file__).resolve()),
            artifact(PROJECT/'tools/verify_temp_heap_provider.py'),artifact(PROJECT/'tools/temp_heap_evidence.py')],
        sdk_inputs=[artifact(roots[a]/'FirePlace/include/FireWorks'/name) for a in result for name in HEADERS],
        sdk_manifest=artifact(PROJECT/'evidence/sdk_x64/port_manifest.json'),foundation=foundation,game_launched=False)
    (evidence/('reference_build.json' if reference_only else 'build_result.json')).write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--vs',type=Path,required=True);p.add_argument('--reference-only',action='store_true');a=p.parse_args()
    r=build(a.vs,a.reference_only);print(json.dumps({'status':r['status']}))
