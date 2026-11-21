"""Compile the current HostMain with /Zs only; never link or run the engine."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

STAGE = Path(__file__).resolve().parent
PROJECT = STAGE.parents[2]
sys.path.insert(0, str(PROJECT / 'tools'))
from native_build import environment_for, run


def seal(path):
    raw=path.read_bytes()
    return dict(path=str(path),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())


def main():
    assert sys.dont_write_bytecode and __debug__
    assert not any(value for key,value in os.environ.items() if key.upper() in ('CL','_CL_','LINK'))
    build=PROJECT/'Build/GameMenuOfflineSyntax'
    assert not build.exists(), 'Do not overwrite an old syntax run'
    build.mkdir()
    base=PROJECT/'Build/UiWindowHost/20261015T134352Z_8bd70cf290e9/dependency_discovery/tu_00_host_main'
    rsp=base/'host_main.discover.rsp'
    dep=json.loads((base/'host_main.sourceDependencies.json').read_text(encoding='utf-8-sig'))['Data']
    prior_catalog=PROJECT/'evidence/ui_window_host/20261024T082423Z_b604cddf0d2d/build_result.json'
    catalog=json.loads(prior_catalog.read_bytes())
    inputs={Path(value) for value in [dep['Source'],*dep['Includes']]}
    inputs.update(Path(row['original_path']) for row in catalog['compiler_inputs'])
    before={str(path).casefold():seal(path) for path in sorted(inputs)}
    dependencies=build/'syntax.sourceDependencies.json'
    response=build/'syntax.rsp'
    flags=[]
    for line in rsp.read_text(encoding='utf-8-sig').splitlines():
        if line=='/c' or line.startswith(('/Fo','/sourceDependencies')):
            continue
        assert not line.startswith(('/Fe','/Fd','/link'))
        flags.append(line)
    flags.extend(('/Zs',f'/sourceDependencies "{dependencies}"'))
    response.write_text('\n'.join(flags)+'\n',encoding='utf-8')
    report=dict(schema='zerosis.game_menu.offline_exit.host_syntax.v1',status='IN_PROGRESS',
                response=seal(response),baseline_response=seal(rsp),prior_input_catalog=seal(prior_catalog),inputs_before=before,
                engine_or_sdk_executed=False,window_or_gpu_created=False,linked=False,
                object_or_executable_created=False,
                generated_ui_header=seal(PROJECT/'Source/Host/UiPopupAssets.generated.h'),
                limit='Current C++ syntax only, using the preserved generated UI header in place. Current Lua/XML are tested separately; no new embedded header, linked Host, native input, shutdown or retail equivalence is accepted.')
    destination=STAGE/'host_syntax.json'
    def checkpoint():
        destination.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    requests=[]
    original_popen=subprocess.Popen
    compiler_path=None
    def guarded_popen(command,*args,**kwargs):
        assert isinstance(command,(list,tuple)) and not kwargs.get('shell')
        values=[str(value) for value in command]
        environment_command=(len(values)==4 and values[0].casefold()=='cmd.exe' and
                             values[1:3]==['/d','/c'] and Path(values[3])==build/'read_build_environment.cmd')
        compiler_command=(compiler_path is not None and values==[compiler_path,'@'+str(response)])
        assert environment_command or compiler_command, 'Unexpected child process'
        requests.append(values)
        return original_popen(command,*args,**kwargs)
    checkpoint()
    subprocess.Popen=guarded_popen
    try:
        env,compiler_path=environment_for(Path(r'C:\Program Files\Microsoft Visual Studio\2022\Community'),'x64',build)
        env['VSLANG']='1033'
        report['compiler']=seal(Path(compiler_path))
        result=run([compiler_path,'@'+str(response)],cwd=build,env=env,timeout=300)
        log=STAGE/'host_syntax.log'
        output=(result.stdout+result.stderr).decode('mbcs',errors='replace')
        log.write_text(output,encoding='utf-8')
        report.update(exit_code=result.returncode,compile_log=seal(log),warnings=re.findall(r'\bwarning [A-Z]+\d+\b',output,re.I))
        after={str(path).casefold():seal(path) for path in sorted(inputs)}
        assert before==after, 'A syntax input changed during compilation'
        report['all_frozen_before_inputs_unchanged']=True
        if dependencies.exists():
            consumed=json.loads(dependencies.read_text(encoding='utf-8-sig'))['Data']
            actual={str(Path(value)).casefold() for value in [consumed['Source'],*consumed['Includes']]}
            report.update(dependencies=seal(dependencies),actual_input_count=len(actual),
                          new_unsealed_inputs=sorted(actual-set(before)),
                          actual_inputs={key:after[key] for key in sorted(actual) if key in after})
            assert not report['new_unsealed_inputs'], 'New unsealed compiler input'
        assert not any(path.suffix.lower() in ('.obj','.exe','.dll','.pdb') for path in build.rglob('*'))
        assert result.returncode==0 and not report['warnings'], 'Actual HostMain syntax failed or warned'
        assert dependencies.exists(), 'Actual compiler dependency report absent'
        report['status']='PASS_CURRENT_HOSTMAIN_SYNTAX_ONLY'
    except BaseException as error:
        report.update(status='FAIL',error=str(error))
        raise
    finally:
        subprocess.Popen=original_popen
        report['child_processes']=requests
        checkpoint()
        print(json.dumps({key:report.get(key) for key in ('status','actual_input_count','exit_code','error')},ensure_ascii=False))


if __name__=='__main__':
    main()
