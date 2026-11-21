"""Build and run isolated original grammar probes without changing the sealed numeric fixture."""
import json
import argparse
import os
from pathlib import Path
import re
import shutil
from collect_baseline import PROJECT,digest,pe_header,read_text
from native_build import run,checked_run,environment_for
from build_icu44 import artifact
from verify_localization_reference import artifacts


def main():
    kind='runtime'
    baseline_path=PROJECT/'evidence/localization/reference/build_result.json'
    baseline=json.loads(baseline_path.read_text(encoding='utf-8'))
    for item in artifacts(baseline):
        if digest(Path(item['path']))!=item['sha256']:raise RuntimeError('Sealed numeric reference changed')
    out=PROJECT/('Build/Localization/'+kind+'_x86');evidence=PROJECT/('evidence/localization/'+kind+'_reference')
    out.mkdir(parents=True,exist_ok=True);evidence.mkdir(parents=True,exist_ok=True)
    vc=Path(r'C:\Program Files (x86)\Microsoft Visual Studio 9.0\VC');win=Path(r'C:\Program Files (x86)\Microsoft SDKs\Windows\v7.0A')
    env={k.upper():v for k,v in os.environ.items()};env['INCLUDE']=f"{vc/'include'};{win/'Include'}";env['LIB']=f"{vc/'lib'};{win/'Lib'}"
    env['PATH']=f"{vc/'bin'};{vc.parent/'Common7/IDE'};{win/'bin'};{env.get('PATH','')}"
    copies=[]
    for pair in baseline['original_inputs']:
        source=Path(pair['copy']['path']);target=out/source.name
        if target.exists() and digest(target)!=digest(source):raise RuntimeError('Grammar dependency copy differs')
        if not target.exists():shutil.copyfile(source,target)
        copies.append(artifact(target))
    source=PROJECT/('Tests/sdk_localization_'+kind+'.cpp');exe=out/('localization_'+kind+'.exe');linkmap=out/(kind+'.map')
    oldsource='"'+baseline['sources'][0]['path']+'"'
    flags=[flag for flag in baseline['flags'] if flag!=oldsource and not flag.startswith(('/Fo','/Fe'))]
    flags += [f'"{source}"',f'/Fo"{out}\\\\"',f'/Fe"{exe}"']
    response=out/'grammar.rsp';response.write_text('\n'.join(flags),encoding='utf-8')
    result=run([vc/'bin/cl.exe','@'+str(response),'/link','/MACHINE:X86','/INCREMENTAL:NO',f'/MAP:{linkmap}'],cwd=out,env=env)
    log=evidence/'build.log';log.write_bytes(result.stdout+result.stderr)
    if result.returncode:raise RuntimeError(read_text(log))
    checked_run([win/'bin/mt.exe','-nologo','-manifest',exe.with_suffix('.exe.manifest'),f'-outputresource:{exe};1'],cwd=out,env=env)
    vs=Path(r'C:\Program Files\Microsoft Visual Studio\2022\Community')
    audit_env,compiler=environment_for(vs,'x64',out/'audit')
    allowed={'kernel32.dll','msvcr90.dll','msvcp90.dll','cvlocalizationwin32final release.dll','cvgamedatabasewin32final release.dll','lua51_win32.dll'}
    imports=[]
    for i,path in enumerate([exe]+[Path(item['path']) for item in copies if item['path'].endswith('.dll')]):
        result=checked_run([Path(compiler).with_name('dumpbin.exe'),'/imports',path],cwd=out,env=audit_env)
        log=evidence/f'imports_{i}.log';log.write_bytes(result.stdout+result.stderr)
        names=re.findall(r'^[ \t]+([^\\:\r\n]+\.dll)[ \t]*\r?$',result.stdout.decode('mbcs',errors='replace'),re.M|re.I)
        if not names or any(name.lower() not in allowed for name in names):raise RuntimeError('Unexpected grammar reference dependency')
        imports.append({'binary':artifact(path),'log':artifact(log),'dependencies':names})
    runs=[]
    for mode in ('updates','binding','selectors','ownership','setters','edges')+tuple('rule_'+str(n) for n in range(21)):
        result=run([exe,mode],cwd=out,timeout=20);log=evidence/(mode+'.log');log.write_bytes(result.stdout+result.stderr)
        output=read_text(log).replace('\r\n','\n');match=re.search(r'^PASS\|(\d+)$',output,re.M)
        runs.append({'mode':mode,'exit_code':result.returncode,'log':artifact(log),'checks':int(match[1]) if match else 0})
        print(json.dumps({'mode':mode,'exit_code':result.returncode,'checks':runs[-1]['checks']}),flush=True)
    report={'status':'ORIGINAL_LOCALIZATION_'+kind.upper()+'_OBSERVATIONS_RECORDED' if all(not r['exit_code'] and r['checks'] for r in runs) else 'ORIGINAL_GRAMMAR_PROBE_FAILURES',
            'baseline':artifact(baseline_path),'source':artifact(source),'builder':artifact(Path(__file__).resolve()),'executable':{**artifact(exe),'pe':pe_header(exe)},
            'copies':copies,'response':artifact(response),'map':artifact(linkmap),'build_log':artifact(evidence/'build.log'),'imports':imports,'runs':runs,
            'game_launched':False,'gamecore_loaded':False,'scope':'Original component grammar observations; no x64 implementation equivalence claim'}
    (evidence/'observations.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    if report['status'].endswith('FAILURES'):raise SystemExit(1)


if __name__=='__main__':main()
