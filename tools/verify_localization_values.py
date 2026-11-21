"""Compare original SharedString behavior with the actual x64 DLL and verify bounds."""
import difflib
import json
from pathlib import Path
import re
from collect_baseline import PROJECT,digest,read_text
from native_build import run,checked_run,environment_for
from build_icu44 import artifact
from verify_localization_reference import artifacts


def main():
    build_path=PROJECT/'evidence/localization/values_candidate/build_result.json'
    reference_path=PROJECT/'evidence/localization/values_reference/observations.json'
    build=json.loads(build_path.read_text(encoding='utf-8'));reference=json.loads(reference_path.read_text(encoding='utf-8'))
    for item in artifacts([build,reference]):
        if digest(Path(item['path']))!=item['sha256']:raise RuntimeError('Localization value input changed: '+item['path'])
    if build['status']!='SDK_LOCALIZATION_VALUES_CANDIDATE_BUILT' or reference['status']!='ORIGINAL_LOCALIZATION_VALUES_OBSERVATIONS_RECORDED':
        raise RuntimeError('Localization value build/reference incomplete')
    evidence=PROJECT/'evidence/localization/values_candidate';out=Path(build['executable']['path']).parent
    env,compiler=environment_for(Path(r'C:\Program Files\Microsoft Visual Studio\2022\Community'),'x64',out/'audit')
    allowed={'zerosislocalizationvalues_x64.dll','kernel32.dll','msvcp140.dll','vcruntime140.dll','vcruntime140_1.dll'}
    imports=[]
    for index,path in enumerate((Path(build['executable']['path']),Path(build['dll']['path']))):
        r=checked_run([Path(compiler).with_name('dumpbin.exe'),'/imports',path],cwd=out,env=env)
        log=evidence/f'imports_{index}.log';log.write_bytes(r.stdout+r.stderr)
        names=re.findall(r'^[ \t]+([^\\:\r\n]+\.dll)[ \t]*\r?$',r.stdout.decode('mbcs',errors='replace'),re.M|re.I)
        if not names or any(name.lower() not in allowed and not name.lower().startswith('api-ms-win-crt-') for name in names):
            raise RuntimeError('Unexpected localization value dependency: '+repr(names))
        imports.append({'binary':artifact(path),'log':artifact(log),'dependencies':names})
    executions=[]
    for mode in ('shared','parameters','boundaries'):
        r=run([build['executable']['path'],mode],cwd=out);log=evidence/(mode+'.log');log.write_bytes(r.stdout+r.stderr)
        output=read_text(log).replace('\r\n','\n');passed=re.search(r'^PASS\|(\d+)$',output,re.M)
        if r.returncode or r.stderr or not passed:raise RuntimeError('Localization value probe failed: '+str(log))
        executions.append({'mode':mode,'log':artifact(log),'exit_code':r.returncode,'checks':int(passed[1])})
    original=read_text(Path(reference['runs'][0]['log']['path'])).splitlines()
    candidate=read_text(Path(executions[0]['log']['path'])).splitlines()
    difference=list(difflib.unified_diff(original,candidate,fromfile='original x86 SharedString',tofile='candidate x64 SharedString',lineterm=''))
    diff=evidence/'shared_diff.txt';diff.write_text('\n'.join(difference),encoding='utf-8')
    linkmap=read_text(Path(build['map']['path']))
    proof=[line for line in linkmap.splitlines() if re.search(r'\s\?SetOffsetAndLength@SharedString@Localization@@\S+\s',line)
           and 'SdkLocalizationValues.obj' in line]
    if len(proof)!=1:raise RuntimeError('Actual SharedString implementation map proof missing')
    if 'BOUNDARIES|PASS|independent_copies=4096' not in read_text(Path(executions[2]['log']['path'])):
        raise RuntimeError('Independent shared-string copy result missing')
    report={'status':'SDK_LOCALIZATION_VALUES_COMPONENT_PASS' if not difference else 'SDK_LOCALIZATION_VALUES_DIFFERENCES',
            'build':artifact(build_path),'reference':artifact(reference_path),'imports':imports,'executions':executions,'difference':artifact(diff),
            'original_records':len(original),'exact_shared_trace':not difference,'independent_copies':4096,'production_proof':proof,
            'verifier':artifact(Path(__file__).resolve()),'game_launched':False,'gamecore_loaded':False,
            'scope':'SharedString exact original trace; parameter copy and rejected-input/concurrency tests are candidate-only; full Localization pending'}
    (evidence/'conformance.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':report['status'],'records':len(original),'checks':sum(r['checks'] for r in executions),'independent_copies':4096}))
    if difference:raise RuntimeError('\n'.join(difference[:60]))


if __name__=='__main__':main()
