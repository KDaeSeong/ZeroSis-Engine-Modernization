"""Run the audited x64 database candidate and compare recorded original wrapper probes."""
from __future__ import annotations
import difflib
import json
from pathlib import Path
import re
import uuid
from collect_baseline import PROJECT,digest
from native_build import run,checked_run

def artifact(p):return {'path':str(p),'sha256':digest(p)}
def main():
    e=PROJECT/'evidence/database';ref=e/'reference';candidate=e/'candidate'
    br=candidate/'build_result.json';b=json.loads(br.read_text());exe=Path(b['executable']['path']);dll=Path(b['dll']['path'])
    for entry in [*b['sources'],b['builder'],b['executable'],b['hardening_executable'],b['dll'],b['library']]:
        if digest(Path(entry['path']))!=entry['sha256']:raise RuntimeError('Stale candidate: '+entry['path'])
    original=json.loads((ref/'build_result.json').read_text())
    if original['sources'][0]['sha256']!=digest(PROJECT/'Tests/sdk_database_trace.cpp'):raise RuntimeError('Reference harness stale')
    dumpbin=Path(b['compiler']['path']).with_name('dumpbin.exe');audits=[]
    allowed={'zerosisdatabase_x64.dll','msvcp140.dll','vcruntime140.dll','vcruntime140_1.dll','kernel32.dll'}
    hardening_exe=Path(b['hardening_executable']['path'])
    for index,path in enumerate((exe,dll,hardening_exe)):
        r=checked_run([dumpbin,'/nologo','/dependents',path],cwd=exe.parent)
        log=candidate/('imports_'+str(index)+'.log');log.write_bytes(r.stdout+r.stderr)
        deps=re.findall(r'^[ \t]+([^\\:\r\n]+\.dll)[ \t]*\r?$',r.stdout.decode('mbcs'),re.M|re.I)
        if not deps or any(d.lower() not in allowed and not d.lower().startswith('api-ms-win-crt-') for d in deps):raise RuntimeError('Unexpected dependency: '+repr(deps))
        audits.append({'module':artifact(path),'dependencies':deps,'log':artifact(log)})
    runs=[]
    for mode in ('probe','semantics','types','contracts','bulk','double'):
        r=run([exe,mode],cwd=exe.parent,timeout=30);log=candidate/(mode+'.log');log.write_bytes(r.stdout+r.stderr)
        row={'mode':mode,'returncode':r.returncode,'log':artifact(log)}
        if mode!='double':
            before=(ref/(mode+'.log')).read_bytes().replace(b'\r\n',b'\n');after=log.read_bytes().replace(b'\r\n',b'\n')
            row['exact_match']=before==after
            diff=candidate/(mode+'.diff');diff.write_text(''.join(difflib.unified_diff(before.decode('ascii').splitlines(True),after.decode('ascii').splitlines(True),fromfile='original',tofile='candidate')),encoding='utf-8');row['diff']=artifact(diff)
        else:row['fixed_original_crash']=r.returncode==0 and b'SELECTREAL|1' in r.stdout and b'PASS|' in r.stdout
        runs.append(row)
    for mode in ('hardening','concurrency'):
        r=run([hardening_exe,mode],cwd=exe.parent,timeout=60);log=candidate/(mode+'.log');log.write_bytes(r.stdout+r.stderr)
        runs.append({'mode':mode,'returncode':r.returncode,'log':artifact(log),'pass_marker':b'PASS|' in r.stdout})
    fixture_dir=PROJECT/'Build/Database/exchange'/uuid.uuid4().hex;fixture_dir.mkdir(parents=True)
    files=[];exchange=[];exes={'x86':Path(original['executable']['path']),'x64':exe}
    for writer in ('x86','x64'):
        file=fixture_dir/(writer+'.sqlite');command=[exes[writer],'writefile',file]
        r=run(command,cwd=exes[writer].parent,timeout=30);log=candidate/(writer+'_file_write.log');log.write_bytes(r.stdout+r.stderr)
        if r.returncode or b'FILE_INTEGRITY|257|17|ok' not in r.stdout:raise RuntimeError('File writer failed: '+str(log))
        files.append(artifact(file));runs.append({'mode':writer+'_file_write','returncode':r.returncode,'log':artifact(log),'pass_marker':b'PASS|' in r.stdout})
        before=digest(file);traces=[]
        for reader in ('x86','x64'):
            r=run([exes[reader],'readfile',file],cwd=exes[reader].parent,timeout=30);log=candidate/(writer+'_file_read_'+reader+'.log');log.write_bytes(r.stdout+r.stderr)
            if r.returncode or b'FILE_INTEGRITY|257|17|ok' not in r.stdout or digest(file)!=before:raise RuntimeError('Read-only file exchange failed: '+str(log))
            runs.append({'mode':writer+'_file_read_'+reader,'returncode':r.returncode,'log':artifact(log),'pass_marker':b'PASS|' in r.stdout});traces.append(r.stdout)
        exchange.append({'writer':writer,'readers':['x86','x64'],'exact_read_trace':traces[0]==traces[1],'database':artifact(file),'unchanged_by_readers':digest(file)==before})
    result={'status':'DATABASE_PROBE_COMPARISON_RECORDED','candidate_build':artifact(br),'audits':audits,'runs':runs,'exchange':exchange,'files':files,
            'all_regular_exact':all(row.get('exact_match',True) for row in runs),'all_candidate_runs_pass':all(row['returncode']==0 and row.get('pass_marker',True) for row in runs)}
    (e/'probe_comparison.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('candidate_build','audits','runs')}))
    for row in runs:print(json.dumps({k:v for k,v in row.items() if k not in ('log','diff')}))
if __name__=='__main__':main()
