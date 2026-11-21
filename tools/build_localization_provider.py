"""Build the real x64 SDK Localization String, parser, dictionary and ICU owner."""
import json
from pathlib import Path
import re
import shutil
from collect_baseline import PROJECT, digest, pe_header, read_text
from native_build import environment_for, run
from build_icu44 import artifact
from build_sdk_x64 import object_machine
from verify_localization_reference import artifacts


def main():
    out=PROJECT/'Build/Localization/provider_x64';evidence=PROJECT/'evidence/localization/provider'
    out.mkdir(parents=True,exist_ok=True);evidence.mkdir(parents=True,exist_ok=True)
    reports={}
    for name,relative in [('icu','evidence/icu44/build_result.json'),('backend','evidence/localization/icu_backend/build_result.json'),
                          ('database','evidence/database/candidate/build_result.json')]:
        path=PROJECT/relative;report=json.loads(path.read_text(encoding='utf-8'))
        for item in artifacts(report):
            if digest(Path(item['path']))!=item['sha256']:raise RuntimeError('Dependency changed: '+item['path'])
        reports[name]=(path,report)
    env,compiler=environment_for(Path(r'C:\Program Files\Microsoft Visual Studio\2022\Community'),'x64',out)
    env['VSLANG']='1033';compiler=Path(compiler)
    provider=PROJECT/'Source/Providers/Localization';dbprovider=PROJECT/'Source/Providers/Database';sdk=PROJECT/'Source/SDK_BNW_x64'
    icu=PROJECT/'Source/ThirdParty/ICU44/original/source'
    include=[f'/I"{provider}"',f'/I"{dbprovider}"','/external:W0']
    include += [f'/external:I"{p}"' for p in (sdk/'CvLocalization/include',sdk/'CvGameDatabase/include',icu/'common',icu/'i18n')]
    common=['/nologo','/O2','/MD','/EHsc','/std:c++14','/W4','/WX','/utf-8','/fp:strict',
            '/D_SILENCE_STDEXT_HASH_DEPRECATION_WARNINGS','/DU_STATIC_IMPLEMENTATION','/DU_HAVE_INTTYPES_H=1','/FIstdint.h']+include
    logs=[];responses=[];objects=[]
    sources=[provider/('SdkLocalization'+name+'.cpp') for name in ('Values','Runtime','String')]
    for source in sources:
        obj=out/(source.stem+'.obj');response=out/(source.stem+'.rsp')
        response.write_text('\n'.join(common+['/c',f'/Fo"{obj}"',f'"{source}"']),encoding='utf-8');responses.append(response)
        result=run([compiler,'@'+str(response)],cwd=out,env=env)
        log=evidence/(source.stem+'.log');log.write_bytes(result.stdout+result.stderr);logs.append(log)
        if result.returncode:raise RuntimeError(read_text(log))
        objects.append(obj)
    dll=out/'ZeroSisLocalization_x64.dll';library=out/'ZeroSisLocalization_x64.lib';linkmap=out/'localization.map'
    dependency_libraries=[Path(reports['database'][1]['library']['path']),Path(reports['backend'][1]['library']['path'])]
    dependency_libraries += [Path(item['library']['path']) for item in reports['icu'][1]['components']]
    command=[compiler.with_name('link.exe'),'/nologo','/DLL','/WX','/Brepro','/INCREMENTAL:NO','/MACHINE:X64',
             '/OUT:'+str(dll),'/IMPLIB:'+str(library),'/MAP:'+str(linkmap)]+objects+dependency_libraries+['kernel32.lib','advapi32.lib']
    result=run(command,cwd=out,env=env);log=evidence/'link.log';log.write_bytes(result.stdout+result.stderr);logs.append(log)
    if result.returncode:raise RuntimeError(read_text(log))
    dbdll=Path(reports['database'][1]['dll']['path']);shutil.copyfile(dbdll,out/dbdll.name)
    reference=json.loads((PROJECT/'evidence/localization/reference/build_result.json').read_text(encoding='utf-8'))
    data=next(Path(p['copy']['path']) for p in reference['original_inputs'] if p['copy']['path'].endswith('.dat'))
    shutil.copyfile(data,out/data.name)
    tests=[]
    for kind in ('trace','grammar','runtime','hardening'):
        source=PROJECT/('Tests/sdk_localization_'+kind+'.cpp');exe=out/('localization_'+kind+'.exe');testmap=out/(kind+'.map')
        rsp=out/(kind+'.rsp');rsp.write_text('\n'.join(common+[f'"{source}"',f'"{library}"',f'"{dependency_libraries[0]}"',
            f'/Fo"{out/(kind+".obj")}"',f'/Fe"{exe}"']),encoding='utf-8');responses.append(rsp)
        result=run([compiler,'@'+str(rsp),'/link','/WX','/INCREMENTAL:NO','/Brepro','/MACHINE:X64','/MAP:'+str(testmap)],cwd=out,env=env)
        log=evidence/(kind+'_build.log');log.write_bytes(result.stdout+result.stderr);logs.append(log)
        if result.returncode:raise RuntimeError(read_text(log))
        tests.append({'kind':kind,'source':artifact(source),'executable':{**artifact(exe),'pe':pe_header(exe)},'map':artifact(testmap)})
    all_sources=sources+[provider/'SdkLocalizationRuntime.h',provider/'SdkLocalizationIncludes.h',dbprovider/'SdkDatabaseIncludes.h',
        PROJECT/'Tests/sdk_localization_trace.cpp',PROJECT/'Tests/localization_numeric_cases.h']
    all_sources+=sorted((sdk/'CvLocalization/include').glob('*.h'))+sorted((sdk/'CvGameDatabase/include').glob('*.h'))
    report={'status':'SDK_LOCALIZATION_X64_CANDIDATE_BUILT','sources':[artifact(p) for p in all_sources],
        'dll':{**artifact(dll),'pe':pe_header(dll)},'library':artifact(library),'objects':[object_machine(p) for p in objects],
        'map':artifact(linkmap),'tests':tests,'dependencies':{k:artifact(v[0]) for k,v in reports.items()},
        'copies':[artifact(out/p.name) for p in (dbdll,data)],'logs':[artifact(p) for p in logs],
        'responses':[artifact(p) for p in responses],'link_command':[str(x) for x in command],
        'flags':common,'compiler':artifact(compiler),'builder':artifact(Path(__file__).resolve()),
        'game_launched':False,'gamecore_loaded':False,'scope':'Actual SDK Localization component; behavioral verification and GameCore linking required'}
    if any(re.search(r'\bwarning\s+[A-Z]+\d+',read_text(p),re.I) for p in logs):raise RuntimeError('Unexpected candidate warning')
    (evidence/'build_result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(report['status'])


if __name__=='__main__':main()
