"""Audit the isolated original DLL dependency graph, then record owned in-memory SQL probes."""
from __future__ import annotations
import json
from pathlib import Path
import re
from collect_baseline import PROJECT,digest
from native_build import run,checked_run

def artifact(path):return {'path':str(path),'sha256':digest(path)}

def main():
    e=PROJECT/'evidence/database/reference';build=e/'build_result.json'
    b=json.loads(build.read_text(encoding='utf-8'));exe=Path(b['executable']['path'])
    for item in [b['executable'],*b['sources'],b['builder'],b['library']]+[v for d in b['original_dlls'] for v in d.values()]:
        if digest(Path(item['path']))!=item['sha256']:raise RuntimeError('Stale original database build: '+item['path'])
    dumpbin=Path(r'C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Tools\MSVC\14.44.35207\bin\Hostx64\x64\dumpbin.exe')
    allowed={'kernel32.dll','msvcp90.dll','msvcr90.dll','cvgamedatabasewin32final release.dll','lua51_win32.dll'}
    audits=[]
    for index,path in enumerate([exe]+[Path(d['copy']['path']) for d in b['original_dlls']]):
        r=checked_run([dumpbin,'/nologo','/dependents',path],cwd=exe.parent)
        log=e/('imports_'+str(index)+'.log');log.write_bytes(r.stdout+r.stderr)
        deps=re.findall(r'^[ \t]+([^\\:\r\n]+\.dll)[ \t]*\r?$',r.stdout.decode('mbcs'),re.M|re.I)
        if not deps or set(d.lower() for d in deps)-allowed:raise RuntimeError('Unexpected dependency: '+repr(deps))
        audits.append({'module':artifact(path),'dependencies':deps,'log':artifact(log)})
    runs=[]
    for mode in ('probe','semantics','types','contracts','bulk','double'):
        r=run([exe,mode],cwd=exe.parent,timeout=30)
        log=e/(mode+'.log');log.write_bytes(r.stdout+r.stderr)
        runs.append({'mode':mode,'returncode':r.returncode,'log':artifact(log)})
        if mode=='double':
            if r.returncode!=0xC0000005 or b'BEFORE_DOUBLE_SELECT' not in r.stdout:
                raise RuntimeError('Original double overload defect changed: '+str(r.returncode))
            runs[-1]['observed_defect']='Original double SelectAt access violation after valid setup'
        elif r.returncode or b'PASS|' not in r.stdout:
            (e/'probe_failure.json').write_text(json.dumps({'runs':runs,'dependency_audits':audits},indent=2)+'\n',encoding='utf-8')
            raise RuntimeError('Database reference probe failed: '+str(log)+' exit='+str(r.returncode))
    report={'status':'SDK_DATABASE_REFERENCE_PROBES_PASS','build':artifact(build),'dependency_audits':audits,'runs':runs,
            'scope':'Original x86 wrapper and owned in-memory SQL only; no game or GameCore loaded',
            'game_launched':False,'gamecore_loaded':False}
    (e/'probe_result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(report['status'])
if __name__=='__main__':main()
