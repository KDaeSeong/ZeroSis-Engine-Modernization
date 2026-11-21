"""Build actual SDK SharedString/parameter storage in an isolated x64 DLL."""
import json
from pathlib import Path
import re
from collect_baseline import PROJECT,digest,pe_header,read_text
from native_build import environment_for,run
from build_icu44 import artifact


def main():
    out=PROJECT/'Build/Localization/values_x64';e=PROJECT/'evidence/localization/values_candidate'
    out.mkdir(parents=True,exist_ok=True);e.mkdir(parents=True,exist_ok=True)
    env,compiler=environment_for(Path(r'C:\Program Files\Microsoft Visual Studio\2022\Community'),'x64',out)
    env['VSLANG']='1033';compiler=Path(compiler)
    provider=PROJECT/'Source/Providers/Localization';dbprovider=PROJECT/'Source/Providers/Database';sdk=PROJECT/'Source/SDK_BNW_x64'
    include_flags=[f'/I"{provider}"',f'/I"{dbprovider}"','/external:W0',f'/external:I"{sdk/"CvLocalization/include"}"',f'/external:I"{sdk/"CvGameDatabase/include"}"']
    common=['/nologo','/O2','/MD','/EHsc','/std:c++14','/W4','/WX','/utf-8','/D_SILENCE_STDEXT_HASH_DEPRECATION_WARNINGS']+include_flags
    source=provider/'SdkLocalizationValues.cpp';obj=out/'SdkLocalizationValues.obj';rsp=out/'values.rsp'
    rsp.write_text('\n'.join(common+['/c',f'/Fo"{obj}"',f'"{source}"']),encoding='utf-8')
    r=run([compiler,'@'+str(rsp)],cwd=out,env=env);log=e/'build.log';log.write_bytes(r.stdout+r.stderr)
    if r.returncode:raise RuntimeError(read_text(log))
    dll=out/'ZeroSisLocalizationValues_x64.dll';lib=out/'ZeroSisLocalizationValues_x64.lib';linkmap=out/'values.map'
    r=run([compiler.with_name('link.exe'),'/nologo','/DLL','/WX','/Brepro','/INCREMENTAL:NO','/MACHINE:X64','/OUT:'+str(dll),'/IMPLIB:'+str(lib),'/MAP:'+str(linkmap),obj],cwd=out,env=env)
    linklog=e/'link.log';linklog.write_bytes(r.stdout+r.stderr)
    if r.returncode:raise RuntimeError(read_text(linklog))
    test=PROJECT/'Tests/sdk_localization_values.cpp';exe=out/'localization_values.exe';testmap=out/'trace.map';testrsp=out/'trace.rsp'
    testrsp.write_text('\n'.join(common+['/DZEROSIS_LOCALIZATION_VALUES_HARDENING',f'"{test}"',f'"{lib}"',f'/Fo"{out/"trace.obj"}"',f'/Fe"{exe}"']),encoding='utf-8')
    r=run([compiler,'@'+str(testrsp),'/link','/WX','/INCREMENTAL:NO','/Brepro','/MACHINE:X64','/MAP:'+str(testmap)],cwd=out,env=env)
    testlog=e/'trace_build.log';testlog.write_bytes(r.stdout+r.stderr)
    if r.returncode:raise RuntimeError(read_text(testlog))
    sources=[source,test,provider/'SdkLocalizationIncludes.h',dbprovider/'SdkDatabaseIncludes.h']
    sources += sorted((sdk/'CvLocalization/include').glob('*.h'))+sorted((sdk/'CvGameDatabase/include').glob('*.h'))
    report={'status':'SDK_LOCALIZATION_VALUES_CANDIDATE_BUILT','sources':[artifact(p) for p in sources],
            'dll':{**artifact(dll),'pe':pe_header(dll)},'library':artifact(lib),'object':artifact(obj),'executable':{**artifact(exe),'pe':pe_header(exe)},
            'map':artifact(linkmap),'test_map':artifact(testmap),'logs':[artifact(p) for p in (log,linklog,testlog)],
            'responses':[artifact(p) for p in (rsp,testrsp)],'flags':common,'compiler':artifact(compiler),'builder':artifact(Path(__file__).resolve()),
            'game_launched':False,'gamecore_loaded':False,'scope':'SDK SharedString and parameter storage only; full Localization integration pending'}
    if any(re.search(r'\bwarning\s+[A-Z]+\d+',read_text(p),re.I) for p in (log,linklog,testlog)):raise RuntimeError('Unexpected candidate warning')
    (e/'build_result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(report['status'])


if __name__=='__main__':main()
