"""Link tested production objects into a separate allocation-fault DLL and run assignment tests."""
import argparse
import json
from pathlib import Path
import re
from collect_baseline import PROJECT,digest,read_text,pe_header
from native_build import environment_for,run,checked_run

def artifact(path):return {'path':str(path),'sha256':digest(path)}
def main(vs):
    build=PROJECT/'evidence/database/candidate/build_result.json';b=json.loads(build.read_text())
    for row in b['objects']+b['sources']+[b['builder']]:
        if digest(Path(row['path']))!=row['sha256']:raise RuntimeError('Production object/input stale: '+row['path'])
    directory=PROJECT/'Build/Database/fault_x64';e=PROJECT/'evidence/database/assignment';e.mkdir(parents=True,exist_ok=True)
    env,compiler=environment_for(vs,'x64',directory);compiler=Path(compiler)
    hook=PROJECT/'Tests/sdk_database_fault_allocator.cpp';test=PROJECT/'Tests/sdk_database_assignment.cpp'
    includes=[PROJECT/'Source/Providers/Database',PROJECT/'Source/SDK_BNW_x64/CvGameDatabase/include',PROJECT/'Source/ThirdParty/sqlite-amalgamation-3071700']
    common=['/nologo','/EHsc','/std:c++14','/O2','/MD','/W4','/WX','/utf-8','/D_CRT_SECURE_NO_WARNINGS','/D_SILENCE_STDEXT_HASH_DEPRECATION_WARNINGS']+[f'/I"{p}"' for p in includes]
    logs=[];responses=[];obj=directory/'sdk_database_fault_allocator.obj'
    rsp=directory/'fault_allocator.rsp';rsp.write_text('\n'.join(common+['/c',f'/Fo"{obj}"',f'"{hook}"']),encoding='utf-8');responses.append(artifact(rsp))
    r=run([compiler,'@'+str(rsp)],cwd=directory,env=env);log=e/'hook_build.log';log.write_bytes(r.stdout+r.stderr);logs.append(artifact(log))
    if r.returncode:raise RuntimeError(read_text(log))
    dll=directory/'ZeroSisDatabase_fault_x64.dll';lib=dll.with_suffix('.lib');linkmap=directory/'fault_provider.map'
    flags=['/nologo','/DLL','/MACHINE:X64','/INCREMENTAL:NO','/Brepro',f'/OUT:{dll}',f'/IMPLIB:{lib}',f'/MAP:{linkmap}']
    r=run([compiler.with_name('link.exe'),*flags,obj,*[o['path'] for o in b['objects']]],cwd=directory,env=env);log=e/'link.log';log.write_bytes(r.stdout+r.stderr);logs.append(artifact(log))
    if r.returncode:raise RuntimeError(read_text(log))
    exe=directory/'database_assignment.exe';rsp=directory/'assignment.rsp'
    rsp.write_text('\n'.join(common+[f'"{test}"',f'/Fo"{directory/"assignment.obj"}"',f'/Fe"{exe}"',f'"{lib}"']),encoding='utf-8');responses.append(artifact(rsp))
    r=run([compiler,'@'+str(rsp),'/link','/MACHINE:X64','/INCREMENTAL:NO','/Brepro',f'/MAP:{directory/"assignment.map"}'],cwd=directory,env=env);log=e/'assignment_build.log';log.write_bytes(r.stdout+r.stderr);logs.append(artifact(log))
    if r.returncode:raise RuntimeError(read_text(log))
    maptext=read_text(linkmap);symbol='??2@YAPEAX_K@Z';proof=[line for line in maptext.splitlines() if re.search(r'\s'+re.escape(symbol)+r'\s',line)]
    if len(proof)!=1 or 'sdk_database_fault_allocator.obj' not in proof[0]:raise RuntimeError('Fault new binding not proven')
    audits=[];allowed={'zerosisdatabase_fault_x64.dll','msvcp140.dll','vcruntime140.dll','vcruntime140_1.dll','kernel32.dll'}
    for index,path in enumerate((exe,dll)):
        r=checked_run([compiler.with_name('dumpbin.exe'),'/nologo','/dependents',path],cwd=directory);log=e/('imports_'+str(index)+'.log');log.write_bytes(r.stdout+r.stderr)
        deps=re.findall(r'^[ \t]+([^\\:\r\n]+\.dll)[ \t]*\r?$',r.stdout.decode('mbcs'),re.M|re.I)
        if not deps or any(d.lower() not in allowed and not d.lower().startswith('api-ms-win-crt-') for d in deps):raise RuntimeError('Unexpected fault test dependency')
        audits.append({'module':artifact(path),'dependencies':deps,'log':artifact(log)})
    r=run([exe],cwd=directory,timeout=60);log=e/'native.log';log.write_bytes(r.stdout+r.stderr)
    if r.returncode:raise RuntimeError('Assignment native failure '+str(r.returncode)+'\n'+read_text(log))
    text=read_text(log);checks=re.search(r'^PASS\|(\d+)',text,re.M);details=re.search(r'^ASSIGNMENT\|failures=(\d+)\|recoveries=(\d+)\|successes=(\d+)\|cpp_faults=(\d+)\|sqlite_faults=(\d+)',text,re.M)
    if not checks or not details:raise RuntimeError('Assignment native markers missing')
    report={'status':'SDK_DATABASE_ASSIGNMENT_FAULTS_PASS','checks':int(checks[1]),'failure_cases':int(details[1]),'recoveries':int(details[2]),'success_cases':int(details[3]),'cpp_faults':int(details[4]),'sqlite_faults':int(details[5]),
        'production_build':artifact(build),'production_objects':b['objects'],'sources':[artifact(hook),artifact(test)],'builder':artifact(Path(__file__).resolve()),'compiler':artifact(compiler),
        'dll':{**artifact(dll),'pe':pe_header(dll)},'library':artifact(lib),'executable':{**artifact(exe),'pe':pe_header(exe)},'hook_object':artifact(obj),'map':artifact(linkmap),'allocator_map_proof':proof,
        'responses':responses,'logs':logs,'audits':audits,'native_execution':artifact(log),'returncode':r.returncode,'runtime':'/MD',
        'scope':'Separate fault DLL reusing exact production objects; no game or production test hooks','game_launched':False,'gamecore_loaded':False}
    (e/'conformance.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps({k:report[k] for k in ('status','checks','failure_cases','recoveries','success_cases','cpp_faults','sqlite_faults')}))
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--vs',type=Path,required=True);main(p.parse_args().vs)
