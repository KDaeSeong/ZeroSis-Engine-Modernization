"""Build isolated x86 localization probes using copied original DLLs and ICU data."""
import json
import os
from pathlib import Path
import re
import shutil
from collect_baseline import PROJECT,digest,pe_header,read_text
from native_build import run,checked_run

def artifact(path):return {'path':str(path),'sha256':digest(path)}

def main():
    out=PROJECT/'Build/Localization/x86';e=PROJECT/'evidence/localization/reference'
    out.mkdir(parents=True,exist_ok=True);e.mkdir(parents=True,exist_ok=True)
    sdk=PROJECT/'Source/SDK_BNW_Original';provider=PROJECT/'Source/Providers/Localization';source=PROJECT/'Tests/sdk_localization_trace.cpp'
    vc=Path(r'C:\Program Files (x86)\Microsoft Visual Studio 9.0\VC');win=Path(r'C:\Program Files (x86)\Microsoft SDKs\Windows\v7.0A')
    env={k.upper():v for k,v in os.environ.items()};env['INCLUDE']=f"{vc/'include'};{win/'Include'}";env['LIB']=f"{vc/'lib'};{win/'Lib'}"
    env['PATH']=f"{vc/'bin'};{vc.parent/'Common7/IDE'};{win/'bin'};{env.get('PATH','')}"
    game=Path(r"C:\Program Files (x86)\Steam\steamapps\common\Sid Meier's Civilization V")
    copies=[]
    for relative in ('CvLocalizationWin32Final Release.dll','CvGameDatabaseWin32Final Release.dll','lua51_Win32.dll','Locale/icudt44l.dat'):
        src=game/relative;target=out/src.name
        if target.exists() and digest(target)!=digest(src):raise RuntimeError('Unexpected existing localization reference input')
        if not target.exists():shutil.copyfile(src,target)
        copies.append({'source':artifact(src),'copy':artifact(target)})
    exe=out/'localization_trace.exe';linkmap=out/'localization_trace.map';compiler=vc/'bin/cl.exe'
    includes=[provider,PROJECT/'Source/Providers/Database',sdk/'CvLocalization/include',sdk/'CvGameDatabase/include']
    libraries=[sdk/'CvLocalization/lib/CvLocalizationWin32.lib',sdk/'CvGameDatabase/lib/CvGameDatabaseWin32.lib']
    flags=['/nologo','/EHsc','/O2','/MD','/W3','/DWIN32','/DFINAL_RELEASE','/D_CRT_SECURE_NO_WARNINGS','/D_SECURE_SCL=0','/D_HAS_ITERATOR_DEBUGGING=0']
    flags += [f'/I"{p}"' for p in includes]+[f'"{p}"' for p in [source,*libraries]]+[f'/Fo"{out}\\\\"',f'/Fe"{exe}"']
    rsp=out/'reference.rsp';rsp.write_text('\n'.join(flags),encoding='utf-8')
    r=run([compiler,'@'+str(rsp),'/link','/MACHINE:X86','/INCREMENTAL:NO',f'/MAP:{linkmap}'],cwd=out,env=env)
    log=e/'build.log';log.write_bytes(r.stdout+r.stderr)
    warning_codes=set(re.findall(r'\bwarning\s+(C\d+)',read_text(log)))
    if r.returncode or warning_codes-{'C4251'}:raise RuntimeError(read_text(log))
    checked_run([win/'bin/mt.exe','-nologo','-manifest',exe.with_suffix('.exe.manifest'),f'-outputresource:{exe};1'],cwd=out,env=env)
    report={'status':'SDK_LOCALIZATION_REFERENCE_BUILT','executable':{**artifact(exe),'pe':pe_header(exe)},'original_inputs':copies,
        'sources':[artifact(source),artifact(PROJECT/'Tests/localization_numeric_cases.h'),artifact(provider/'SdkLocalizationIncludes.h'),artifact(PROJECT/'Source/Providers/Database/SdkDatabaseIncludes.h')]
            +[artifact(p) for root in (sdk/'CvLocalization/include',sdk/'CvGameDatabase/include') for p in sorted(root.glob('*.h'))],
        'compiler':artifact(compiler),'libraries':[artifact(p) for p in libraries],'map':artifact(linkmap),'response':artifact(rsp),
        'flags':flags,'log':artifact(log),'warning_codes':sorted(warning_codes),'builder':artifact(Path(__file__).resolve()),'game_launched':False,'gamecore_loaded':False}
    (e/'build_result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(report['status'])

if __name__=='__main__':main()
