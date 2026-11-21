"""Build direct enum/STL reference and x64 candidate without loading GameCore."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import re
from collect_baseline import PROJECT,digest,read_text,pe_header
from native_build import environment_for,run,checked_run

def artifact(path): return {'path':str(path),'sha256':digest(path)}

def enum_types():
    source=PROJECT/'Source/SDK_BNW_Original/CvGameCoreDLLUtil/include/CvEnumSerialization.h'
    text=read_text(source)
    writes=re.findall(r'operator<<\(FDataStream\s*&,\s*const\s+(\w+)\s*&\)',text)
    reads=re.findall(r'operator>>\(FDataStream\s*&,\s*(\w+)\s*&\)',text)
    if writes!=reads or len(writes)!=len(set(writes)): raise RuntimeError('Enum operator declarations differ')
    return writes

GAMECORE_INPUTS=('CvGameCoreDLL_Expansion2/CvReplayInfo.h','CvGameCoreDLL_Expansion2/CvReplayInfo.cpp',
    'CvGameCoreDLL_Expansion2/CvStructs.h','CvGameCoreDLL_Expansion2/CvStructs.cpp','CvGameCoreDLLUtil/include/CvString.h')

def extract_block(text,signature,semicolon=False):
    if text.count(signature)!=1: raise RuntimeError('Ambiguous SDK extract: '+signature)
    start=text.index(signature); opening=text.index('{',start); depth=1; end=opening+1
    while depth:
        if text[end]=='{':depth+=1
        elif text[end]=='}':depth-=1
        end+=1
    if semicolon:
        if text[end]!=';':raise RuntimeError('Expected SDK declaration terminator')
        end+=1
    return text[start:end]

def gamecore_extracts(sdk,out):
    replay=read_text(sdk/GAMECORE_INPUTS[1]).replace('\r\n','\n');structs=read_text(sdk/GAMECORE_INPUTS[3]).replace('\r\n','\n')
    typedefs=re.findall(r'typedef std::map<unsigned int, int> TurnData;',read_text(sdk/GAMECORE_INPUTS[0]))
    if len(typedefs)!=1:raise RuntimeError('Replay TurnData type changed')
    parts=['// Exact SDK declarations/function bodies in a minimal test-only owning class.',
        '#include <CvString.h>','class CvReplayInfo { public: '+typedefs[0]+' };']
    parts += [extract_block(replay,'FDataStream& operator'+op+'(FDataStream& '+param+
         ', '+qualification+'CvReplayInfo::TurnData& '+variable+')') for op,param,qualification,variable in (
         ('<<','saveTo','const ','readFrom'),('>>','loadFrom','','writeTo'))]
    header=read_text(sdk/GAMECORE_INPUTS[2]).replace('\r\n','\n')
    parts += [extract_block(header,'struct '+name+'\n',True) for name in ('VoteSelectionSubData','VoteSelectionData')]
    parts += [extract_block(structs,signature) for signature in (
        'void VoteSelectionData::read(FDataStream& kStream)',
        'void VoteSelectionData::write(FDataStream& kStream) const',
        'FDataStream& operator>>(FDataStream& loadFrom, VoteSelectionData& writeTo)',
        'FDataStream& operator<<(FDataStream& saveTo, const VoteSelectionData& readFrom)')]
    path=out/'SdkGameCoreSerializationExtract.h';path.write_text('\n\n'.join(parts)+'\n',encoding='ascii')
    return artifact(path)

def build(vs,label='candidate'):
    if not re.fullmatch('[a-z0-9_]+',label): raise RuntimeError('Invalid label')
    types=enum_types(); provider=PROJECT/'Source/Providers/Serialization'
    inc=provider/'SdkEnumTypes.inc'
    expected='// Types declared by the unchanged public SDK serialization header.\n'+''.join(
        ('SDK_ENUM_BYTE' if name=='GameTypes' else 'SDK_ENUM')+'('+name+')\n' for name in types)
    if inc.exists() and inc.read_text(encoding='ascii')!=expected: raise RuntimeError('Untracked enum list edit')
    if not inc.exists(): inc.write_text(expected,encoding='ascii')
    evidence=PROJECT/'evidence/serialization'/label; evidence.mkdir(parents=True,exist_ok=True)
    directory=PROJECT/'Build/Serialization'/label; directory.mkdir(parents=True,exist_ok=True)
    source=PROJECT/'Tests/sdk_serialization_trace.cpp'; host=PROJECT/'Tests/sdk_stream_reference_host.cpp'
    roots={arch:PROJECT/('Source/SDK_BNW_Original' if arch=='x86' else 'Source/SDK_BNW_x64') for arch in ('x86','x64')}
    for row in json.loads((PROJECT/'evidence/sdk_reference/snapshot_manifest.json').read_text(encoding='utf-8')):
        if digest(Path(row['snapshot']))!=row['sha256'] or digest(Path(row['source']))!=row['sha256']:
            raise RuntimeError('Original SDK changed')
    result={};generated=[]
    for arch in ('x86','x64'):
        out=directory/arch; out.mkdir(exist_ok=True)
        sdk=roots[arch]
        generated.append(gamecore_extracts(sdk,out))
        vc=Path(r'C:\Program Files (x86)\Microsoft Visual Studio 9.0\VC')
        win=Path(r'C:\Program Files (x86)\Microsoft SDKs\Windows\v7.0A')
        if arch=='x86':
            env={k.upper():v for k,v in os.environ.items()}
            env['INCLUDE']=f"{vc/'include'};{win/'Include'}";env['LIB']=f"{vc/'lib'};{win/'Lib'}"
            env['PATH']=f"{vc/'bin'};{vc.parent/'Common7/IDE'};{win/'bin'};{env.get('PATH','')}"
            compiler=vc/'bin/cl.exe'
        else: env,compiler=environment_for(vs,arch,out); compiler=Path(compiler)
        includes=[sdk/'FirePlace/include',sdk/'CvGameCoreDLLUtil/include',PROJECT/'Source/Porting',PROJECT/'Source/Providers/Streams',provider,out]
        flags=['/nologo','/EHsc','/O2','/MD','/fp:strict','/D_CRT_SECURE_NO_WARNINGS','/DFINAL_RELEASE',
               '/D_SECURE_SCL=0','/D_HAS_ITERATOR_DEBUGGING=0']
        flags+=(['/W3']+[f'/I"{p}"' for p in includes]) if arch=='x86' else (
            ['/std:c++14','/W4','/WX','/D_SILENCE_STDEXT_HASH_DEPRECATION_WARNINGS','/external:W0','/DSERIALIZATION_CANDIDATE']
            +[f'/external:I"{p}"' for p in includes[:2]]+[f'/I"{p}"' for p in includes[2:]])
        logs=[]; objects=[]
        def compile_run(name,args,link=()):
            rsp=out/(name+'.rsp');rsp.write_text('\n'.join(args),encoding='ascii')
            r=run([compiler,f'@{rsp}',*(['/link',*link] if link else [])],cwd=out,env=env,timeout=120)
            log=evidence/(arch+'_'+name+'.log'); log.write_bytes(r.stdout+r.stderr);logs.append(artifact(log))
            if r.returncode: raise RuntimeError(read_text(log)[:7000])
            if arch=='x64' and re.search(r'\bwarning\s+[A-Z]+\d+',read_text(log)): raise RuntimeError('Candidate warnings: '+read_text(log))
        if arch=='x64':
            for cpp in sorted(provider.glob('*.cpp')):
                obj=out/(cpp.stem+'.obj'); compile_run(cpp.stem,flags+['/c',f'"{cpp}"',f'/Fo"{obj}"']);objects.append(artifact(obj))
            library=out/'ZeroSis_Serialization_x64.lib'
            checked_run([compiler.with_name('lib.exe'),'/nologo','/Brepro',f'/OUT:{library}',*[o['path'] for o in objects]],cwd=out,env=env)
            libraries=[library,PROJECT/'Build/Streams_provider/x64/ZeroSis_Streams_x64.lib'];sources=[source]
        else:
            libraries=[sdk/'CvGameCoreDLLUtil/lib/CvGameCoreDLLUtilWin32.lib',sdk/'FirePlace/lib/FireWorksWin32.lib'];sources=[source,host]
        exe=out/'serialization_trace.exe'; linkmap=out/'serialization_trace.map'
        link=['/INCREMENTAL:NO','/OPT:REF','/OPT:ICF',f'/MACHINE:{arch.upper()}',f'/MAP:{linkmap}']
        if arch=='x86':link+=['/LTCG']
        link+=[n+'.lib' for n in ('kernel32','user32','advapi32','psapi','dbghelp','ole32','shell32','winmm')]
        compile_run('harness',flags+[f'"{s}"' for s in sources]+[f'/Fo"{out}\\\\"',f'/Fe"{exe}"']+[f'"{p}"' for p in libraries],link)
        if arch=='x86' and exe.with_suffix('.exe.manifest').exists():
            checked_run([win/'bin/mt.exe','-nologo','-manifest',exe.with_suffix('.exe.manifest'),f'-outputresource:{exe};1'],cwd=out,env=env)
        result[arch]={'executable':{**artifact(exe),'pe':pe_header(exe)},'libraries':[artifact(p) for p in libraries],
            'map':artifact(linkmap),'compiler':artifact(compiler),'objects':objects,'logs':logs,'flags':flags}
    result.update(status='SERIALIZATION_PROVIDERS_BUILT',runtime='/MD',enum_types=types,generated_extracts=generated,
        sources=[artifact(p) for p in sorted(provider.glob('*'))]+[artifact(source),artifact(host),
                 artifact(PROJECT/'Source/Providers/Streams/SdkStreamIncludes.h'),artifact(Path(__file__).resolve())],
        sdk_inputs=[artifact(roots[a]/f) for a in roots for f in ('CvGameCoreDLLUtil/include/CvEnums.h',
            'CvGameCoreDLLUtil/include/CvEnumSerialization.h','FirePlace/include/FireWorks/FStlContainerSerialization.h',*GAMECORE_INPUTS)],
        sdk_manifest=artifact(PROJECT/'evidence/sdk_x64/port_manifest.json'),
        stream_conformance=artifact(PROJECT/'evidence/streams/conformance.json'),game_launched=False)
    (evidence/'build_result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--vs',type=Path,required=True);p.add_argument('--label',default='candidate');a=p.parse_args()
    r=build(a.vs,a.label);print(json.dumps({'status':r['status'],'enum_types':len(r['enum_types'])}))
