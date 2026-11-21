"""Build the real SDK log manager without loading any Civilization V module."""
import json,re
from pathlib import Path
from collect_baseline import PROJECT,read_text,pe_header
from native_build import run,checked_run,environment_for
from probe_world_builder import artifact
from filesystem_evidence import validate as filesystem

def main():
    _,_,fs=filesystem()
    out=PROJECT/'Build/Logging/x64';evidence=PROJECT/'evidence/logging'
    out.mkdir(parents=True,exist_ok=True);evidence.mkdir(parents=True,exist_ok=True)
    from define_logging_caller_patches import patches
    _,calls=patches();fixture=out/'logging_callers_fixture.h'
    lines=['#pragma once','inline void ExerciseLoggingCallers(FILogFile* log) {',
        '    const char* text = "City 100% %s %n literal payload";']
    for row in calls:
        source=PROJECT/'Source/SDK_BNW_x64'/row['file']
        if row['new'] not in source.read_bytes().decode('latin1'):raise RuntimeError('Logging caller patch not in actual SDK: '+str(source))
        argument=row['argument']
        if argument.endswith('.c_str()'):declaration='std::string '+argument[:-8]+'=text;'
        elif argument in {'buf','szMessage','szOut','msg'}:declaration='const char* '+argument+'=text;'
        else:declaration='CvString '+argument+'(text);'
        lines.append('    { '+declaration+' log'+row['new']+' }')
    lines.append('}');fixture.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    env,compiler=environment_for(Path(r'C:\Program Files\Microsoft Visual Studio\2022\Community'),'x64',out);compiler=Path(compiler)
    source=PROJECT/'Source/Providers/Logging/SdkLogFile.cpp';test=PROJECT/'Tests/sdk_logging.cpp'
    sdk=PROJECT/'Source/SDK_BNW_x64'
    flags=['/nologo','/O2','/Gy','/MD','/EHsc','/W4','/WX','/std:c++14','/utf-8','/DWIN32','/DFINAL_RELEASE','/DFXS_IS_DLL',
           '/D_CRT_SECURE_NO_WARNINGS','/D_SECURE_SCL=0','/D_HAS_ITERATOR_DEBUGGING=0','/external:W0',
           f'/I"{source.parent}"',f'/I"{out}"',f'/external:I"{sdk/"FirePlace/include"}"',f'/external:I"{sdk/"CvGameCoreDLLUtil/include"}"']
    logs=[];responses=[]
    def compile_one(name,args,link=()):
        rsp=out/(name+'.rsp');rsp.write_text('\n'.join(args)+'\n',encoding='utf-8');responses.append(artifact(rsp))
        r=run([compiler,'@'+str(rsp),*(['/link',*link] if link else [])],cwd=out,env=env,timeout=120)
        log=evidence/(name+'_build.log');log.write_bytes(r.stdout+r.stderr);logs.append(artifact(log))
        if r.returncode:raise RuntimeError(read_text(log)[-10000:])
    obj=out/'SdkLogFile.obj';compile_one('provider',flags+['/c',f'"{source}"',f'/Fo"{obj}"'])
    library=out/'ZeroSis_Logging_x64.lib'
    checked_run([compiler.with_name('lib.exe'),'/nologo','/Brepro',f'/OUT:{library}',obj],cwd=out,env=env)
    exe=out/'logging.exe';linkmap=out/'logging.map'
    compile_one('logging',flags+[f'"{test}"',f'"{library}"',f'"{fs["library"]["path"]}"',f'/Fo"{out/"logging.obj"}"',f'/Fe"{exe}"'],
        ['/INCREMENTAL:NO','/OPT:REF','/OPT:ICF','/MACHINE:X64',f'/MAP:{linkmap}','kernel32.lib'])
    r=checked_run([compiler.with_name('dumpbin.exe'),'/dependents',exe],cwd=out,env=env)
    log=evidence/'logging_imports.log';log.write_bytes(r.stdout+r.stderr)
    deps=re.findall(r'^\s+([\w.-]+\.dll)\s*$',r.stdout.decode('ascii',errors='replace'),re.M|re.I)
    allowed={'kernel32.dll','msvcp140.dll','vcruntime140.dll','vcruntime140_1.dll'}
    if not deps or any(d.lower() not in allowed and not d.lower().startswith('api-ms-win-crt-') for d in deps):raise RuntimeError('Unexpected logging imports')
    report={'status':'LOGGING_X64_PROVIDER_BUILT','runtime':'/MD','library':artifact(library),'objects':[artifact(obj)],
            'sources':[artifact(p) for p in (source,source.with_suffix('.h'),test,PROJECT/'Source/Providers/FileSystem/SdkFileSystem.h')],
            'sdk_headers':[artifact(sdk/'FirePlace/include/FireWorks'/p) for p in ('FILogFile.h','FIFile.h','FFileDefines.h','FFileSystem.h','FFireTypes.h')],
            'consumer':{'source':artifact(test),'executable':{**artifact(exe),'pe':pe_header(exe)},'map':artifact(linkmap),'imports':{'dependencies':deps,'log':artifact(log)}},
            'builder':artifact(Path(__file__).resolve()),'compiler':artifact(compiler),'flags':flags,'logs':logs,'responses':responses,
            'filesystem_provider':fs,'gamecore_loaded':False,'game_launched':False}
    report['caller_fixture']=artifact(fixture)
    report['caller_recipe']=artifact(PROJECT/'tools/define_logging_caller_patches.py')
    report['caller_patch_plan']=artifact(PROJECT/'evidence/logging/caller_patch_plan.json')
    report['sdk_port_manifest']=artifact(PROJECT/'evidence/sdk_x64/port_manifest.json')
    report['sdk_patch_specification']=artifact(PROJECT/'Source/Porting/sdk_x64_patches.json')
    report['sdk_headers'].extend(artifact(sdk/'CvGameCoreDLLUtil/include'/p) for p in ('CvString.h','CvAssert.h'))
    (evidence/'build_result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(report['status'])
if __name__=='__main__':main()
