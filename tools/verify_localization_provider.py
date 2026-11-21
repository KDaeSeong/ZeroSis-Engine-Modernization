"""Compare the actual x64 Localization DLL with the original x86 component."""
import difflib
import json
from pathlib import Path
import re
from collect_baseline import PROJECT, digest, read_text
from build_icu44 import artifact
from native_build import environment_for, checked_run, run
from verify_localization_reference import artifacts


def observable(path):
    # Diagnostic wording/ICU warning frequency is recorded separately, not a text-output contract.
    return [line for line in read_text(path).splitlines() if not line.startswith('LOG|')]


def expected_adjustments(kind,mode,original):
    expected=list(original);changes=[]
    def replace(old,new,start=0,end=None):
        hits=[i for i in range(start,len(expected) if end is None else end) if expected[i]==old]
        if len(hits)!=1:raise RuntimeError('Known original behavior changed: '+old)
        expected[hits[0]]=new;changes.append({'record':hits[0],'original':old,'expected':new})
    if (kind,mode)==('grammar','mutations'):
        replace('SET_ALL_PLURAL|0','SET_ALL_PLURAL|1')
        first=expected.index('SET_ALL_PLURAL|1');last=expected.index('SET_PLURAL_STRING|1')
        for form in (1,2):replace(f'META|{form}|gender=2|plurality=1',f'META|{form}|gender=2|plurality=2',first,last)
    elif (kind,mode)==('runtime','setters'):
        for forms in range(4):
            prefix=f'SET_ALL|forms={forms}|value=2|result='
            old=prefix+'0'+''.join(f'|{i}:1' for i in range(1,forms+1))
            new=prefix+'1'+''.join(f'|{i}:2' for i in range(1,forms+1))
            replace(old,new)
    elif (kind,mode)==('runtime','edges'):
        replace('COMPARE|5|success=1|result=-1','COMPARE|5|success=0|result=99')
    return expected,changes


def main():
    evidence=PROJECT/'evidence/localization/provider';build_path=evidence/'build_result.json'
    build=json.loads(build_path.read_text(encoding='utf-8'))
    for item in artifacts(build):
        if digest(Path(item['path']))!=item['sha256']:raise RuntimeError('Candidate input changed: '+item['path'])
    references={}
    for kind,relative in [('trace','evidence/localization/reference/observations.json'),
                          ('grammar','evidence/localization/grammar_reference/observations.json'),
                          ('runtime','evidence/localization/runtime_reference/observations.json')]:
        path=PROJECT/relative;report=json.loads(path.read_text(encoding='utf-8'))
        for item in artifacts(report):
            if digest(Path(item['path']))!=item['sha256']:raise RuntimeError('Reference input changed: '+item['path'])
        references[kind]=(path,report)
    out=Path(build['dll']['path']).parent
    env,compiler=environment_for(Path(r'C:\Program Files\Microsoft Visual Studio\2022\Community'),'x64',out/'audit')
    binaries=[Path(build['dll']['path'])]+[Path(p['executable']['path']) for p in build['tests']]
    binaries += [Path(p['path']) for p in build['copies'] if p['path'].endswith('.dll')]
    allowed={'zerosislocalization_x64.dll','zerosisdatabase_x64.dll','kernel32.dll','advapi32.dll','msvcp140.dll','vcruntime140.dll','vcruntime140_1.dll'}
    imports=[]
    for index,binary in enumerate(binaries):
        result=checked_run([Path(compiler).with_name('dumpbin.exe'),'/imports',binary],cwd=out,env=env)
        log=evidence/f'imports_{index}.log';log.write_bytes(result.stdout+result.stderr)
        names=re.findall(r'^[ \t]+([^\\:\r\n]+\.dll)[ \t]*\r?$',result.stdout.decode('mbcs',errors='replace'),re.M|re.I)
        if not names or any(n.lower() not in allowed and not n.lower().startswith('api-ms-win-crt-') for n in names):
            raise RuntimeError('Unexpected Localization dependency: '+repr(names))
        imports.append({'binary':artifact(binary),'log':artifact(log),'dependencies':names})
    executions=[];differences=[];accepted=[];hardening=[]
    for test in build['tests']:
        kind=test['kind']
        if kind=='hardening':
            result=run([test['executable']['path'],'hardening'],cwd=out,timeout=30)
            log=evidence/'hardening.log';log.write_bytes(result.stdout+result.stderr)
            output=read_text(log).replace('\r\n','\n');passed=re.search(r'^PASS\|(\d+)$',output,re.M)
            markers=['HARDENING|bounds|PASS','HARDENING|dictionary_failure_and_cycle|PASS',
                     'HARDENING|threads_and_reinitialization|PASS|workers=4|calls=1024']
            if result.returncode or not passed or not all(marker in output for marker in markers):
                raise RuntimeError('Localization hardening failed: '+read_text(log))
            hardening.append({'kind':kind,'exit_code':result.returncode,'checks':int(passed[1]),'log':artifact(log),'markers':markers})
            continue
        reference=references[kind][1]
        runs=reference.get('runs',reference.get('executions',[]))
        if not runs:raise RuntimeError('Reference mode list missing: '+kind)
        for original in runs:
            mode=original['mode'];result=run([test['executable']['path'],mode],cwd=out,timeout=30)
            log=evidence/(kind+'_'+mode+'.log');log.write_bytes(result.stdout+result.stderr)
            output=read_text(log).replace('\r\n','\n');passed=re.search(r'^PASS\|(\d+)$',output,re.M)
            original_log=Path(original['log']['path'] if isinstance(original['log'],dict) else original['log'])
            before=observable(original_log);after=observable(log)
            expected,changes=expected_adjustments(kind,mode,before)
            diff=list(difflib.unified_diff(before,after,fromfile='original '+kind+'/'+mode,tofile='candidate '+kind+'/'+mode,lineterm=''))
            diff_path=evidence/(kind+'_'+mode+'.diff.txt');diff_path.write_text('\n'.join(diff)+'\n',encoding='utf-8')
            row={'kind':kind,'mode':mode,'exit_code':result.returncode,'checks':int(passed[1]) if passed else 0,
                 'log':artifact(log),'original':artifact(original_log),'difference':artifact(diff_path),
                 'original_records':len(before),'candidate_records':len(after),'exact_observables':not diff,
                 'matches_required_observables':expected==after,'intentional_adjustments':changes}
            executions.append(row)
            if changes:accepted.append({'kind':kind,'mode':mode,'adjustments':changes,'difference':artifact(diff_path)})
            if expected!=after or result.returncode or not passed:differences.append({'kind':kind,'mode':mode,'exit_code':result.returncode,'difference_lines':len(diff),'preview':diff[:35]})
    linkmap=read_text(Path(build['map']['path']))
    proof={name:[line for line in linkmap.splitlines() if re.search(r'\s\?'+name+r'@\S+\s',line) and 'SdkLocalization' in line]
           for name in ('Compose','TryLookup','Initialize')}
    if any(not lines for lines in proof.values()):raise RuntimeError('Actual implementation link-map evidence missing')
    report={'status':'SDK_LOCALIZATION_COMPONENT_PASS' if not differences else 'SDK_LOCALIZATION_COMPONENT_DIFFERENCES',
        'build':artifact(build_path),'references':{k:artifact(v[0]) for k,v in references.items()},'imports':imports,
        'executions':executions,'differences':differences,'intentional_differences':accepted,'hardening':hardening,
        'production_proof':proof,'verifier':artifact(Path(__file__).resolve()),
        'game_launched':False,'gamecore_loaded':False,
        'scope':'Actual SDK text, grammar, metadata, numeric corpus and dictionary component traces; diagnostics and full game runtime excluded'}
    (evidence/'conformance.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':report['status'],'runs':len(executions),'checks':sum(r['checks'] for r in executions),
        'hardening_checks':sum(r['checks'] for r in hardening),'intentional_adjustments':sum(len(a['adjustments']) for a in accepted),'differences':differences},ensure_ascii=True))
    if differences:raise SystemExit(1)


if __name__=='__main__':main()
