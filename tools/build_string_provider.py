"""Build real SDK string references and the x64 string/UTF conversion provider."""
import argparse
import json
import os
from pathlib import Path
import re
from collect_baseline import PROJECT,digest,pe_header,read_text
from native_build import environment_for,run,checked_run
def artifact(path):return {'path':str(path),'sha256':digest(path)}

def build(vs,reference_only=False):
    from stream_evidence import validate
    _,_,streams=validate(PROJECT/'evidence/streams/provider/build_result.json')
    provider=PROJECT/'Source/Providers/Strings';source=PROJECT/'Tests/sdk_strings_trace.cpp'
    evidence=PROJECT/'evidence/strings';evidence.mkdir(parents=True,exist_ok=True)
    inputs=[];results={}
    for arch in (('x86',) if reference_only else ('x86','x64')):
        out=PROJECT/'Build/Strings'/arch;out.mkdir(parents=True,exist_ok=True)
        sdk=PROJECT/('Source/SDK_BNW_Original' if arch=='x86' else 'Source/SDK_BNW_x64')
        vc=Path(r'C:\Program Files (x86)\Microsoft Visual Studio 9.0\VC');win=Path(r'C:\Program Files (x86)\Microsoft SDKs\Windows\v7.0A')
        if arch=='x86':
            env={k.upper():v for k,v in os.environ.items()};env['INCLUDE']=f"{vc/'include'};{win/'Include'}";env['LIB']=f"{vc/'lib'};{win/'Lib'}"
            env['PATH']=f"{vc/'bin'};{vc.parent/'Common7/IDE'};{win/'bin'};{env.get('PATH','')}";compiler=vc/'bin/cl.exe'
        else:env,compiler=environment_for(vs,arch,out);compiler=Path(compiler)
        flags=['/nologo','/O2','/MD','/EHsc','/DWIN32','/DFINAL_RELEASE','/D_CRT_SECURE_NO_WARNINGS','/D_SECURE_SCL=0','/D_HAS_ITERATOR_DEBUGGING=0',
            f'/I"{provider}"',f'/I"{PROJECT/"Source/Providers/Streams"}"',f'/I"{PROJECT/"Source/Porting"}"']
        roots=[sdk/'FirePlace/include',sdk/'CvGameCoreDLLUtil/include']
        if arch=='x86':flags+=['/W3']+[f'/I"{p}"' for p in roots]
        else:flags+=['/W4','/WX','/std:c++14','/utf-8','/DFXS_IS_DLL','/DSTRINGS_CANDIDATE','/D_SILENCE_STDEXT_HASH_DEPRECATION_WARNINGS','/external:W0']+[f'/external:I"{p}"' for p in roots]
        objects=[];logs=[];responses=[]
        def compile_one(name,args,link=()):
            rsp=out/(name+'.rsp');rsp.write_text('\n'.join(args),encoding='utf-8');responses.append(artifact(rsp))
            r=run([compiler,'@'+str(rsp),*(['/link',*link] if link else [])],cwd=out,env=env,timeout=60)
            log=evidence/(arch+'_'+name+'.log');log.write_bytes(r.stdout+r.stderr);logs.append(artifact(log))
            codes=set(re.findall(r'\bwarning\s+(C\d+)',read_text(log)))
            if r.returncode or codes-({'C4819'} if arch=='x86' else set()):raise RuntimeError(read_text(log)[:8000])
        if arch=='x64':
            for cpp in sorted(provider.glob('*.cpp')):
                obj=out/(cpp.stem+'.obj');compile_one(cpp.stem,flags+['/c',f'"{cpp}"',f'/Fo"{obj}"']);objects.append(artifact(obj))
            library=out/'ZeroSis_Strings_x64.lib'
            checked_run([compiler.with_name('lib.exe'),'/nologo','/Brepro',f'/OUT:{library}',*[o['path'] for o in objects]],cwd=out,env=env)
            libraries=[library,Path(streams['library']['path'])];sources=[source]
        else:
            library=sdk/'FirePlace/lib/FireWorksWin32.lib';libraries=[library,sdk/'CvGameCoreDLLUtil/lib/CvGameCoreDLLUtilWin32.lib']
            sources=[source,PROJECT/'Tests/sdk_stream_reference_host.cpp']
        exe=out/'strings_trace.exe';linkmap=out/'strings_trace.map'
        link=['/INCREMENTAL:NO','/OPT:REF','/OPT:ICF',f'/MACHINE:{arch.upper()}',f'/MAP:{linkmap}']
        if arch=='x86':link+=['/LTCG']
        link += [n+'.lib' for n in ('kernel32','user32','advapi32','psapi','dbghelp','ole32','shell32','winmm')]
        compile_one('harness',flags+[f'"{p}"' for p in sources+libraries]+[f'/Fo"{out}\\\\"',f'/Fe"{exe}"'],link)
        if arch=='x86':checked_run([win/'bin/mt.exe','-nologo','-manifest',exe.with_suffix('.exe.manifest'),f'-outputresource:{exe};1'],cwd=out,env=env)
        results[arch]={'executable':{**artifact(exe),'pe':pe_header(exe)},'libraries':[artifact(p) for p in libraries],
            'library':artifact(library),'objects':objects,'compiler':artifact(compiler),'map':artifact(linkmap),'logs':logs,'responses':responses,'flags':flags}
        if arch=='x64':
            hard_sources=[PROJECT/'Tests/sdk_strings_hardening.cpp',PROJECT/'Tests/sdk_strings_fault_allocator.cpp']
            hard_exe=out/'strings_hardening.exe';hard_map=out/'strings_hardening.map'
            hard_link=[arg if not arg.startswith('/MAP:') else f'/MAP:{hard_map}' for arg in link]
            compile_one('hardening',flags+[f'"{p}"' for p in hard_sources+libraries]+[f'/Fo"{out}\\\\"',f'/Fe"{hard_exe}"'],hard_link)
            results[arch]['hardening']={'executable':{**artifact(hard_exe),'pe':pe_header(hard_exe)},'map':artifact(hard_map),
                'sources':[artifact(p) for p in hard_sources],'production_objects':objects}
        inputs += [artifact(sdk/'FirePlace/include/FireWorks'/name) for name in ('FString.h','FStringA.inl','FStringW.inl','FDataStream.h','FArray.h','FDefNew.h')]
        inputs.append(artifact(sdk/'CvGameCoreDLLUtil/include/CvStringUtils.h'))
    result={'status':'SDK_STRINGS_REFERENCE_BUILT' if reference_only else 'SDK_STRINGS_PROVIDER_BUILT','runtime':'/MD',**results,
        'sources':[artifact(p) for p in sorted(provider.glob('*'))]+[artifact(source),artifact(PROJECT/'Tests/sdk_stream_reference_host.cpp'),artifact(PROJECT/'Source/Providers/Streams/SdkStreamIncludes.h')],
        'sdk_inputs':inputs,'streams_provider':streams,'builder':artifact(Path(__file__).resolve()),'game_launched':False,'gamecore_loaded':False}
    if not reference_only:result.update(library=results['x64']['library'],objects=results['x64']['objects'])
    (evidence/('reference_build.json' if reference_only else 'build_result.json')).write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--vs',type=Path,required=True);p.add_argument('--reference-only',action='store_true');a=p.parse_args()
    print(build(a.vs,a.reference_only)['status'])
