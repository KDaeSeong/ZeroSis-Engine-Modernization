"""Build original-SDK and candidate auto-archive executables without a GameCore host."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import re
from collect_baseline import PROJECT,digest,read_text,pe_header
from native_build import environment_for,run,checked_run

def artifact(path):return {'path':str(path),'sha256':digest(path)}

HEADERS=('FFireTypes.h','FDataStream.h','FMemoryStream.h','FAutoArchive.h','FAutoVariableBase.h','FAutoArchiveClassContainer.h',
    'FAutoVariable.h','FAutoVector.h','FStlContainerSerialization.h')

def build(vs,reference_only=False):
    provider=PROJECT/'Source/Providers/AutoArchive';evidence=PROJECT/'evidence/auto_archive';evidence.mkdir(parents=True,exist_ok=True)
    source=PROJECT/'Tests/sdk_auto_archive_trace.cpp';host=PROJECT/'Tests/sdk_stream_reference_host.cpp'
    caller_source=PROJECT/'Tests/sdk_auto_archive_callers.cpp';support=PROJECT/'Source/Porting/CvAutoArchiveSupport.h'
    roots={a:PROJECT/('Source/SDK_BNW_Original' if a=='x86' else 'Source/SDK_BNW_x64') for a in ('x86','x64')}
    for row in json.loads((PROJECT/'evidence/sdk_reference/snapshot_manifest.json').read_text(encoding='utf-8')):
        if digest(Path(row['snapshot']))!=row['sha256'] or digest(Path(row['source']))!=row['sha256']:raise RuntimeError('Original SDK changed')
    dependencies=[]
    if not reference_only:
        from stream_evidence import validate as streams
        from serialization_evidence import validate as serialization
        for validate,path in ((streams,'evidence/streams/provider/build_result.json'),(serialization,'evidence/serialization/candidate/build_result.json')):
            _,_,entry=validate(PROJECT/path);dependencies.append(entry)
    result={}
    for arch in (('x86',) if reference_only else ('x86','x64')):
        out=PROJECT/'Build/AutoArchive'/arch;out.mkdir(parents=True,exist_ok=True);sdk=roots[arch]
        vc=Path(r'C:\Program Files (x86)\Microsoft Visual Studio 9.0\VC');win=Path(r'C:\Program Files (x86)\Microsoft SDKs\Windows\v7.0A')
        if arch=='x86':
            env={k.upper():v for k,v in os.environ.items()};env['INCLUDE']=f"{vc/'include'};{win/'Include'}";env['LIB']=f"{vc/'lib'};{win/'Lib'}"
            env['PATH']=f"{vc/'bin'};{vc.parent/'Common7/IDE'};{win/'bin'};{env.get('PATH','')}";compiler=vc/'bin/cl.exe'
        else:env,compiler=environment_for(vs,arch,out);compiler=Path(compiler)
        flags=['/nologo','/EHsc','/O2','/MD','/fp:strict','/DWIN32','/DFINAL_RELEASE','/D_CRT_SECURE_NO_WARNINGS',
            '/D_SECURE_SCL=0','/D_HAS_ITERATOR_DEBUGGING=0','/D_SILENCE_STDEXT_HASH_DEPRECATION_WARNINGS','/W3' if arch=='x86' else '/W4']
        flags += [f'/I"{PROJECT/p}"' for p in ('Source/Providers/AutoArchive','Source/Providers/Streams','Source/Providers/Serialization')]
        if arch=='x86':flags += [f'/I"{sdk/p}"' for p in ('FirePlace/include','CvGameCoreDLLUtil/include')]
        else:flags += ['/WX','/std:c++14','/DAUTO_ARCHIVE_CANDIDATE','/external:W0',f'/I"{PROJECT/"Source/Porting"}"']+[f'/external:I"{sdk/p}"' for p in ('FirePlace/include','CvGameCoreDLLUtil/include')]
        logs=[];responses=[];objects=[]
        def compile_run(name,args,link=()):
            rsp=out/(name+'.rsp');rsp.write_text('\n'.join(args),encoding='ascii');responses.append(artifact(rsp))
            r=run([compiler,f'@{rsp}',*(['/link',*link] if link else [])],cwd=out,env=env,timeout=120)
            log=evidence/(arch+'_'+name+'.log');log.write_bytes(r.stdout+r.stderr);logs.append(artifact(log))
            warnings=set(re.findall(r'\bwarning\s+([A-Z]+\d+)',read_text(log)))
            if r.returncode or warnings-({'C4819'} if arch=='x86' else set()):raise RuntimeError(read_text(log)[:7500])
        if arch=='x64':
            for cpp in sorted(provider.glob('*.cpp')):
                obj=out/(cpp.stem+'.obj');compile_run(cpp.stem,flags+['/c',f'"{cpp}"',f'/Fo"{obj}"']);objects.append(artifact(obj))
            if not objects:raise RuntimeError('Missing x64 auto-archive implementation')
            library=out/'ZeroSis_AutoArchive_x64.lib'
            checked_run([compiler.with_name('lib.exe'),'/nologo','/Brepro',f'/OUT:{library}',*[o['path'] for o in objects]],cwd=out,env=env)
            libraries=[library]+[Path(d['library']['path']) for d in dependencies];sources=[source]
        else:libraries=[sdk/'FirePlace/lib/FireWorksWin32.lib',sdk/'CvGameCoreDLLUtil/lib/CvGameCoreDLLUtilWin32.lib'];sources=[source,host]
        exe=out/'auto_archive_trace.exe';linkmap=out/'auto_archive_trace.map'
        link=['/INCREMENTAL:NO','/OPT:REF','/OPT:ICF',f'/MACHINE:{arch.upper()}',f'/MAP:{linkmap}']+(['/LTCG'] if arch=='x86' else [])
        link += [n+'.lib' for n in ('kernel32','user32','advapi32','psapi','dbghelp','ole32','shell32','winmm')]
        compile_run('harness',flags+[f'"{s}"' for s in sources]+[f'/Fo"{out}\\\\"',f'/Fe"{exe}"']+[f'"{p}"' for p in libraries],link)
        if arch=='x86' and exe.with_suffix('.exe.manifest').exists():checked_run([win/'bin/mt.exe','-nologo','-manifest',exe.with_suffix('.exe.manifest'),f'-outputresource:{exe};1'],cwd=out,env=env)
        callers=None
        if arch=='x64':
            caller_exe=out/'auto_archive_callers.exe';caller_map=out/'auto_archive_callers.map'
            caller_link=[value if not value.startswith('/MAP:') else '/MAP:'+str(caller_map) for value in link]
            compile_run('callers',flags+[f'"{caller_source}"',f'/Fo"{out}\\\\"',f'/Fe"{caller_exe}"']+[f'"{p}"' for p in libraries],caller_link)
            callers={'executable':{**artifact(caller_exe),'pe':pe_header(caller_exe)},'map':artifact(caller_map)}
        result[arch]={'executable':{**artifact(exe),'pe':pe_header(exe)},'libraries':[artifact(p) for p in libraries],
            'map':artifact(linkmap),'compiler':artifact(compiler),'objects':objects,'logs':logs,'responses':responses,'flags':flags,
            'warning_codes':sorted({code for log in logs for code in re.findall(r'\bwarning\s+([A-Z]+\d+)',read_text(Path(log['path'])))})}
        if callers:result[arch]['callers']=callers
    result.update(status='SDK_AUTO_ARCHIVE_REFERENCE_BUILT' if reference_only else 'AUTO_ARCHIVE_PROVIDERS_BUILT',runtime='/MD',providers=dependencies,
        sources=[artifact(p) for p in sorted(provider.glob('*'))]+[artifact(source),artifact(host),artifact(Path(__file__).resolve()),
            artifact(PROJECT/'Source/Providers/Streams/SdkStreamIncludes.h'),artifact(PROJECT/'Source/Providers/Serialization/SdkSerializationIncludes.h'),
            artifact(caller_source),artifact(support),artifact(PROJECT/'tools/define_auto_archive_caller_patches.py')],
        sdk_inputs=[artifact(roots[a]/'FirePlace/include/FireWorks'/name) for a in result for name in HEADERS]
            +[artifact(roots[a]/'CvGameCoreDLLUtil/include'/name) for a in result for name in ('CvEnums.h','CvEnumSerialization.h')],
        sdk_manifest=artifact(PROJECT/'evidence/sdk_x64/port_manifest.json'),game_launched=False)
    (evidence/('reference_build.json' if reference_only else 'build_result.json')).write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    return result
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--vs',type=Path,required=True);p.add_argument('--reference-only',action='store_true');args=p.parse_args()
    r=build(args.vs,args.reference_only);print(json.dumps({'status':r['status']}))
