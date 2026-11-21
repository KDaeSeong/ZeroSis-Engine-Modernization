"""Rerun dependencies whose seals include the changed SDK port manifest/patch plan."""
import json
from pathlib import Path
import subprocess
import sys
from collect_baseline import PROJECT, digest, read_text


def main():
    vs=r'C:\Program Files\Microsoft Visual Studio\2022\Community'
    steps=[('verify_sdk_x64_allocator',['--vs',vs]),
        ('verify_numeric_boundaries',['--vs',vs,'--lua-provider','evidence/lua_provider/build_result.json']),
        ('verify_stream_provider',['--vs',vs]),('verify_serialization_provider',['--vs',vs]),
        ('verify_foundation_provider',['--vs',vs]),('verify_temp_heap_provider',['--vs',vs]),
        ('verify_temp_heap_callers',['--vs',vs]),('verify_auto_archive_provider',['--vs',vs]),
        ('build_flua_provider',['--vs',vs]),('verify_flua_provider',[]),
        ('build_string_provider',['--vs',vs]),('verify_string_provider',[]),
        ('verify_database_corpus',['--vs',vs]),('build_localization_values',[]),('verify_localization_values',[])]
    root=PROJECT/'evidence/localization/dependency_refresh';root.mkdir(parents=True,exist_ok=True)
    report=[]
    for name,args in steps:
        print('RUN '+name,flush=True);script=PROJECT/'tools'/(name+'.py');log=root/(name+'.log')
        with log.open('wb') as stream:
            result=subprocess.run([sys.executable,str(script),*args],cwd=PROJECT,stdout=stream,stderr=subprocess.STDOUT,
                timeout=1800,creationflags=subprocess.CREATE_NO_WINDOW)
        report.append({'step':name,'exit_code':result.returncode,'script':{'path':str(script),'sha256':digest(script)},
            'log':{'path':str(log),'sha256':digest(log)}})
        (root/'results.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        if result.returncode:
            print(read_text(log)[-7000:]);raise SystemExit(result.returncode)
        print('PASS '+name,flush=True)
    print('LOCALIZATION_DEPENDENCY_REFRESH_PASS',flush=True)


if __name__=='__main__':main()
