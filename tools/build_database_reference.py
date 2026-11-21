"""Build an isolated VC9 x86 wrapper trace against the actual Civ V database DLL."""
from __future__ import annotations
import json
import os
from pathlib import Path
import re
import shutil
from collect_baseline import PROJECT,digest,pe_header,read_text
from native_build import run,checked_run

def artifact(path):return {'path':str(path),'sha256':digest(path)}

def main():
    out=PROJECT/'Build/Database/x86';e=PROJECT/'evidence/database/reference'
    out.mkdir(parents=True,exist_ok=True);e.mkdir(parents=True,exist_ok=True)
    sdk=PROJECT/'Source/SDK_BNW_Original';provider=PROJECT/'Source/Providers/Database';source=PROJECT/'Tests/sdk_database_trace.cpp'
    vc=Path(r'C:\Program Files (x86)\Microsoft Visual Studio 9.0\VC');win=Path(r'C:\Program Files (x86)\Microsoft SDKs\Windows\v7.0A')
    env={k.upper():v for k,v in os.environ.items()};env['INCLUDE']=f"{vc/'include'};{win/'Include'}";env['LIB']=f"{vc/'lib'};{win/'Lib'}"
    env['PATH']=f"{vc/'bin'};{vc.parent/'Common7/IDE'};{win/'bin'};{env.get('PATH','')}"
    game=Path(r"C:\Program Files (x86)\Steam\steamapps\common\Sid Meier's Civilization V")
    original=[]
    for name in ('CvGameDatabaseWin32Final Release.dll','lua51_Win32.dll'):
        src=game/name;target=out/name;data=src.read_bytes()
        if target.is_file() and target.read_bytes()!=data:raise RuntimeError('Unexpected existing reference DLL')
        if not target.is_file():shutil.copyfile(src,target)
        original.append({'source':artifact(src),'copy':artifact(target)})
    exe=out/'database_trace.exe';linkmap=out/'database_trace.map';compiler=vc/'bin/cl.exe';library=sdk/'CvGameDatabase/lib/CvGameDatabaseWin32.lib'
    flags=['/nologo','/EHsc','/O2','/MD','/W3','/DWIN32','/DFINAL_RELEASE','/D_CRT_SECURE_NO_WARNINGS','/D_SECURE_SCL=0','/D_HAS_ITERATOR_DEBUGGING=0',
        f'/I"{provider}"',f'/I"{sdk/"CvGameDatabase/include"}"',f'"{source}"',f'/Fo"{out}\\\\"',f'/Fe"{exe}"',f'"{library}"']
    rsp=out/'reference.rsp';rsp.write_text('\n'.join(flags),encoding='ascii')
    r=run([compiler,'@'+str(rsp),'/link','/MACHINE:X86','/INCREMENTAL:NO',f'/MAP:{linkmap}'],cwd=out,env=env)
    log=e/'build.log';log.write_bytes(r.stdout+r.stderr)
    if r.returncode or re.search(r'\bwarning\s+[A-Z]+\d+',read_text(log)):raise RuntimeError(read_text(log))
    checked_run([win/'bin/mt.exe','-nologo','-manifest',exe.with_suffix('.exe.manifest'),f'-outputresource:{exe};1'],cwd=out,env=env)
    report={'status':'SDK_DATABASE_REFERENCE_BUILT','executable':{**artifact(exe),'pe':pe_header(exe)},'original_dlls':original,
        'sources':[artifact(source),artifact(provider/'SdkDatabaseIncludes.h')]+[artifact(p) for p in sorted((sdk/'CvGameDatabase/include').glob('*.h'))],
        'compiler':artifact(compiler),'builder':artifact(Path(__file__).resolve()),'library':artifact(library),'map':artifact(linkmap),
        'response':artifact(rsp),'flags':flags,'log':artifact(log),'game_launched':False,'gamecore_loaded':False}
    (e/'build_result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(report['status'])
if __name__=='__main__':main()
