"""Additional sealed observations of the actual archived map mod-data component."""
import json
import os
from pathlib import Path
import re
from collect_baseline import PROJECT,read_text,digest,pe_header
from database_evidence import artifacts
from native_build import run,checked_run,environment_for
from probe_world_builder import artifact

def main():
    baseline_path=PROJECT/'evidence/world_builder/reference/observations.json';baseline=json.loads(baseline_path.read_text(encoding='utf-8'))
    for item in artifacts(baseline):
        if digest(Path(item['path']))!=item['sha256']:raise RuntimeError('Existing type/group reference changed')
    out=PROJECT/'Build/WorldBuilder/mod_data_x86';evidence=PROJECT/'evidence/world_builder/mod_data_reference'
    out.mkdir(parents=True,exist_ok=True);evidence.mkdir(parents=True,exist_ok=True)
    vc=Path(r'C:\Program Files (x86)\Microsoft Visual Studio 9.0\VC');win=Path(r'C:\Program Files (x86)\Microsoft SDKs\Windows\v7.0A')
    env={k.upper():v for k,v in os.environ.items()};env['INCLUDE']=f"{vc/'include'};{win/'Include'}";env['LIB']=f"{vc/'lib'};{win/'Lib'}"
    env['PATH']=f"{vc/'bin'};{vc.parent/'Common7/IDE'};{win/'bin'};{env.get('PATH','')}"
    source=PROJECT/'Tests/sdk_world_builder_mod_data.cpp';exe=out/'mod_data.exe';linkmap=out/'mod_data.map'
    flags=Path(baseline['response']['path']).read_text(encoding='utf-8').splitlines();oldsource='"'+baseline['sources'][0]['path']+'"'
    flags=[arg for arg in flags if arg!=oldsource and not arg.startswith(('/Fo','/Fe'))]
    flags += [f'"{source}"',f'/Fo"{out}\\\\"',f'/Fe"{exe}"'];response=out/'compile.rsp';response.write_text('\n'.join(flags),encoding='utf-8')
    result=run([vc/'bin/cl.exe','@'+str(response),'/link','/LTCG','/INCREMENTAL:NO','/OPT:REF','/OPT:ICF','/MACHINE:X86',f'/MAP:{linkmap}',
                *[n+'.lib' for n in ('kernel32','user32','advapi32','psapi','dbghelp','ole32','shell32','winmm')]],cwd=out,env=env)
    log=evidence/'build.log';log.write_bytes(result.stdout+result.stderr)
    if result.returncode:raise RuntimeError(read_text(log)[:8000])
    checked_run([win/'bin/mt.exe','-nologo','-manifest',exe.with_suffix('.exe.manifest'),f'-outputresource:{exe};1'],cwd=out,env=env)
    audit_env,compiler=environment_for(Path(r'C:\Program Files\Microsoft Visual Studio\2022\Community'),'x64',out/'audit')
    result=checked_run([Path(compiler).with_name('dumpbin.exe'),'/dependents',exe],cwd=out,env=audit_env);ilog=evidence/'imports.log';ilog.write_bytes(result.stdout+result.stderr)
    deps=re.findall(r'^[ \t]+([^\\:\r\n]+\.dll)[ \t]*\r?$',result.stdout.decode('mbcs',errors='replace'),re.M|re.I)
    if not deps or set(n.lower() for n in deps)-set(n.lower() for n in baseline['imports']['dependencies']):raise RuntimeError('Unexpected mod-data reference dependency')
    runs=[]
    for mode in ('baseline','dense','defaults','bounds','fresh'):
        result=run([exe,mode],cwd=out,timeout=20);log=evidence/(mode+'.log');log.write_bytes(result.stdout+result.stderr)
        match=re.search(r'^PASS\|(\d+)\s*$',read_text(log).replace('\r\n','\n'),re.M)
        row={'mode':mode,'exit_code':result.returncode,'checks':int(match[1]) if match else 0,'log':artifact(log)};runs.append(row);print(json.dumps(row),flush=True)
    report={'status':'WORLD_BUILDER_MOD_DATA_REFERENCE_OBSERVED' if all(not r['exit_code'] and r['checks'] for r in runs) else 'WORLD_BUILDER_MOD_DATA_REFERENCE_FAILURES',
        'baseline':artifact(baseline_path),'source':artifact(source),'builder':artifact(Path(__file__).resolve()),'executable':{**artifact(exe),'pe':pe_header(exe)},
        'map':artifact(linkmap),'response':artifact(response),'build_log':artifact(evidence/'build.log'),'imports':{'dependencies':deps,'log':artifact(ilog)},
        'runs':runs,'game_launched':False,'gamecore_loaded':False}
    (evidence/'observations.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    if report['status'].endswith('FAILURES'):raise SystemExit(1)

if __name__=='__main__':main()
