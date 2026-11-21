"""Build a real x64 stream provider and standalone conformance executable."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
from collect_baseline import PROJECT, digest, pe_header, read_text
from native_build import run, environment_for, checked_run

def artifact(path): return {"path":str(path),"sha256":digest(path)}

def build(vs):
    directory=PROJECT/'Build/Streams_provider/x64'; evidence=PROJECT/'evidence/streams/provider'
    directory.mkdir(parents=True,exist_ok=True); evidence.mkdir(parents=True,exist_ok=True)
    env,compiler=environment_for(vs,'x64',directory)
    sdk=PROJECT/'Source/SDK_BNW_x64'
    for row in json.loads((PROJECT/'evidence/sdk_x64/port_manifest.json').read_text(encoding='utf-8')):
        if digest(Path(row['port']))!=row['port_sha256']: raise RuntimeError('Untracked SDK port edit before stream build')
    provider=PROJECT/'Source/Providers/Streams'
    sources=[provider/'SdkMemoryStream.cpp',provider/'SdkDataStream.cpp']
    flags=['/nologo','/std:c++14','/EHsc','/W4','/WX','/O2','/MD','/fp:strict','/D_CRT_SECURE_NO_WARNINGS',
           '/DFINAL_RELEASE','/D_SECURE_SCL=0','/D_HAS_ITERATOR_DEBUGGING=0',
           f'/external:I"{sdk/"FirePlace/include"}"','/external:W0',f'/I"{provider}"',f'/I"{PROJECT/"Source/Porting"}"']
    objects=[]; logs=[]
    for source in sources:
        obj=directory/(source.stem+'.obj'); rsp=directory/(source.stem+'.rsp')
        rsp.write_text('\n'.join(flags+['/c',f'"{source}"',f'/Fo"{obj}"']),encoding='utf-8')
        r=run([compiler,f'@{rsp}'],cwd=directory,env=env,timeout=120)
        log=evidence/(source.stem+'.log'); log.write_bytes(r.stdout+r.stderr); logs.append(artifact(log))
        if r.returncode or re.search(r'\bwarning\s+[A-Z]+\d+',read_text(log)): raise RuntimeError(read_text(log)[:7000])
        if int.from_bytes(obj.read_bytes()[:2],'little')!=0x8664: raise RuntimeError('Not an AMD64 object')
        objects.append(obj)
    library=directory/'ZeroSis_Streams_x64.lib'
    librarian=Path(compiler).with_name('lib.exe')
    checked_run([librarian,'/nologo','/Brepro',f'/OUT:{library}',*objects],cwd=directory,env=env)
    exe=directory/'stream_candidate.exe'; source=PROJECT/'Tests/sdk_stream_trace.cpp'
    rsp=directory/'harness.rsp'
    rsp.write_text('\n'.join(flags+['/DSTREAM_CANDIDATE',f'"{source}"',f'/Fo"{directory/"harness.obj"}"',f'/Fe"{exe}"',f'"{library}"']),encoding='utf-8')
    r=run([compiler,f'@{rsp}','/link','/INCREMENTAL:NO','/MACHINE:X64','/WX',f'/MAP:{directory/"stream_candidate.map"}'],cwd=directory,env=env)
    log=evidence/'harness.log'; log.write_bytes(r.stdout+r.stderr); logs.append(artifact(log))
    if r.returncode or re.search(r'\bwarning\s+[A-Z]+\d+',read_text(log)): raise RuntimeError(read_text(log)[:7000])
    report={'status':'X64_STREAM_PROVIDER_BUILT_NOT_YET_ACCEPTED','library':artifact(library),
            'executable':{**artifact(exe),'pe':pe_header(exe)},'objects':[artifact(p) for p in objects],
            'sources':[artifact(p) for p in sorted(provider.glob('*'))]+[artifact(source),artifact(Path(__file__).resolve())],
            'sdk_manifest':artifact(PROJECT/'evidence/sdk_x64/port_manifest.json'),'flags':flags,'runtime':'/MD',
            'logs':logs,'compiler':artifact(Path(compiler)),'compiler_warnings':0,
            'external_sdk_header_warning_policy':'/external:W0; existing SDK warning inventory tracked separately',
            'game_launched':False,'game_runtime_verified':False}
    (evidence/'build_result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--vs',type=Path,required=True); a=p.parse_args()
    r=build(a.vs); print(json.dumps({'status':r['status'],'library':r['library']}))
