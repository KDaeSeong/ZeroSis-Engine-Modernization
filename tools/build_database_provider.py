"""Build the real x64 SDK database DLL and isolated consumer; never link/load GameCore."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
from collect_baseline import PROJECT,digest,pe_header,read_text
from native_build import environment_for,run,checked_run
from prepare_sqlite_compat import prepare

def artifact(p):return {'path':str(p),'sha256':digest(p)}

def build(vs):
    upstream=prepare();root=PROJECT/'Source/ThirdParty/sqlite-amalgamation-3071700'
    out=PROJECT/'Build/Database/x64';e=PROJECT/'evidence/database/candidate';out.mkdir(parents=True,exist_ok=True);e.mkdir(parents=True,exist_ok=True)
    env,compiler=environment_for(vs,'x64',out);env['VSLANG']='1033';compiler=Path(compiler)
    provider=PROJECT/'Source/Providers/Database';sdk=PROJECT/'Source/SDK_BNW_x64/CvGameDatabase/include'
    common=['/nologo','/c','/O2','/MD','/fp:strict','/DNDEBUG','/DWIN32','/DFINAL_RELEASE','/D_CRT_SECURE_NO_WARNINGS','/D_SILENCE_STDEXT_HASH_DEPRECATION_WARNINGS']
    sqlite_defines=['SQLITE_THREADSAFE=1','SQLITE_OMIT_AUTHORIZATION','SQLITE_OMIT_AUTOINIT','SQLITE_OMIT_DEPRECATED','SQLITE_OMIT_PROGRESS_CALLBACK','SQLITE_OMIT_TCL_VARIABLE','SQLITE_TEMP_STORE=2']
    units=[root/'sqlite3.c',provider/'SdkDatabase.cpp',provider/'SdkDatabaseResults.cpp'];logs=[];objects=[];responses=[]
    for source in units:
        obj=out/(source.stem+'.obj');flags=common+['/W3' if source.suffix=='.c' else '/W4','/we4302','/we4311','/we4312',f'/Fo"{obj}"']
        if source.suffix=='.c':flags+=['/TC']+['/D'+s for s in sqlite_defines]
        else:flags+=['/std:c++14','/EHsc','/WX','/utf-8']
        flags += [f'/I"{provider}"',f'/I"{sdk}"',f'/I"{root}"',f'"{source}"']
        rsp=out/(source.stem+'.rsp');rsp.write_text('\n'.join(flags),encoding='utf-8');responses.append(artifact(rsp))
        r=run([compiler,'@'+str(rsp)],cwd=out,env=env,timeout=180);log=e/(source.stem+'.log');log.write_bytes(r.stdout+r.stderr);logs.append(artifact(log))
        if r.returncode:raise RuntimeError(read_text(log))
        objects.append(artifact(obj))
    dll=out/'ZeroSisDatabase_x64.dll';lib=out/'ZeroSisDatabase_x64.lib';linkmap=out/'database_provider.map'
    flags=['/nologo','/DLL','/MACHINE:X64','/INCREMENTAL:NO','/Brepro',f'/OUT:{dll}',f'/IMPLIB:{lib}',f'/MAP:{linkmap}']
    r=run([compiler.with_name('link.exe'),*flags,*[o['path'] for o in objects]],cwd=out,env=env)
    log=e/'link.log';log.write_bytes(r.stdout+r.stderr);logs.append(artifact(log))
    if r.returncode:raise RuntimeError(read_text(log))
    hardening_source=PROJECT/'Tests/sdk_database_hardening.cpp';hardening_exe=out/'database_hardening.exe'
    hardening_flags=[f for f in common if f!='/c']+['/W4','/WX','/utf-8','/std:c++14','/EHsc',f'/I"{provider}"',f'/I"{sdk}"',f'"{hardening_source}"',f'/Fo"{out/"database_hardening.obj"}"',f'/Fe"{hardening_exe}"',f'"{lib}"']
    hardening_rsp=out/'hardening.rsp';hardening_rsp.write_text('\n'.join(hardening_flags),encoding='utf-8');responses.append(artifact(hardening_rsp))
    r=run([compiler,'@'+str(hardening_rsp),'/link','/MACHINE:X64','/INCREMENTAL:NO','/Brepro',f'/MAP:{out/"database_hardening.map"}'],cwd=out,env=env)
    log=e/'hardening_build.log';log.write_bytes(r.stdout+r.stderr);logs.append(artifact(log))
    if r.returncode:raise RuntimeError(read_text(log))
    source=PROJECT/'Tests/sdk_database_trace.cpp';exe=out/'database_trace.exe';trace_map=out/'database_trace.map'
    flags=[f for f in common if f!='/c']+['/W4','/WX','/utf-8','/std:c++14','/EHsc',f'/I"{provider}"',f'/I"{sdk}"',f'"{source}"',f'/Fo"{out/"database_trace.obj"}"',f'/Fe"{exe}"',f'"{lib}"']
    rsp=out/'trace.rsp';rsp.write_text('\n'.join(flags),encoding='utf-8');responses.append(artifact(rsp))
    r=run([compiler,'@'+str(rsp),'/link','/MACHINE:X64','/INCREMENTAL:NO','/Brepro',f'/MAP:{trace_map}'],cwd=out,env=env)
    log=e/'trace_build.log';log.write_bytes(r.stdout+r.stderr);logs.append(artifact(log))
    if r.returncode:raise RuntimeError(read_text(log))
    report={'status':'SDK_DATABASE_X64_COMPONENT_BUILT','dll':{**artifact(dll),'pe':pe_header(dll)},'library':artifact(lib),'executable':{**artifact(exe),'pe':pe_header(exe)},
            'objects':objects,'runtime':'/MD','sqlite_source':upstream,'sqlite_defines':sqlite_defines,
            'sources':[artifact(p) for p in [*units[1:],*[Path(a['path']) for a in upstream['sources']],*sorted(provider.glob('*.h')),source,hardening_source,*sorted(sdk.glob('*.h'))]],
            'source_preparer':artifact(Path(__file__).with_name('prepare_sqlite_compat.py')),
            'hardening_executable':{**artifact(hardening_exe),'pe':pe_header(hardening_exe)},
            'builder':artifact(Path(__file__).resolve()),'compiler':artifact(compiler),'map':artifact(linkmap),'trace_map':artifact(trace_map),'responses':responses,'logs':logs,
            'warnings':[line for item in logs for line in read_text(Path(item['path'])).splitlines() if re.search(r'\bwarning\s+[A-Z]+\d+',line)],
            'game_launched':False,'gamecore_loaded':False,'scope':'Unaccepted component candidate; native conformance and lifecycle gates required'}
    (e/'build_result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps({'status':report['status'],'warnings':len(report['warnings'])}));return report
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--vs',type=Path,required=True);build(p.parse_args().vs)
