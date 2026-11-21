"""Build and run only the portable retail Pregame boundary component."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

sys.dont_write_bytecode = True
from verify_retail_save_header import artifact, require, key, within, pe_imports, COMPILER, COMPILER_SHA, VS

PROJECT = Path(__file__).absolute().parents[1]
STAGE = PROJECT/'evidence/retail_save_container/pregame_boundary'
REPORT = STAGE/'build_result.json'
SOURCE = PROJECT/'Tests/retail_save_pregame.cpp'
HEADER = PROJECT/'Source/Host/RetailSavePregame.h'


def main():
    require(len(sys.argv)==1 and not sys.flags.optimize, 'Unexpected component verification invocation')
    from native_build import environment_for, run
    from collect_baseline import pe_header
    fixtures=json.loads((STAGE/'fixtures.json').read_text(encoding='utf-8'))
    require(fixtures['status']=='PASS_PUBLIC_PREGAME_FIXTURES' and len(fixtures['fixtures'])==2 and
        fixtures['user_save_accessed'] is False and fixtures['full_saves_retained']==0,
        'Immutable public disjoint fixtures required')
    fixture_paths=[]
    for row in fixtures['fixtures']:
        require(row['full_blob_verified_in_memory'] is True and row['full_file_retained'] is False,
            'Whole-save fixtures must not be retained')
        for name in ('metadata_prefix_reused','retained_tail'):
            ref=row[name];path=Path(ref['path'])
            require(path.is_relative_to(PROJECT/'Tests/Fixtures') and artifact(path)==ref,'Fixture identity changed')
            fixture_paths.append(path)
    require(fixtures['fixtures'][0]['observed']['status']=='SUPPORTED_BNW6_PREGAME_PREFIX' and
        fixtures['fixtures'][1]['observed']['status']=='UNSUPPORTED_PREGAME_PROFILE_WITNESS',
        'Unexpected public coverage; do not equate a rejection witness with restored mod support')
    upstream=json.loads((STAGE/'upstream.json').read_text(encoding='utf-8'))
    for row in upstream['files']:
        data=(PROJECT/row['local_path']).read_bytes()
        require(hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()==row['git_blob_sha'],
            'Pinned primary reference changed')
    inputs=[artifact(x) for x in (HEADER,SOURCE,PROJECT/'Source/Host/RetailSaveHeader.h',Path(__file__).absolute(),
        PROJECT/'tools/verify_retail_save_header.py',PROJECT/'tools/native_build.py',PROJECT/'tools/collect_baseline.py',
        PROJECT/'tools/prepare_retail_pregame_fixtures.py',STAGE/'fixtures.json',STAGE/'upstream.json',
        PROJECT/'Source/Host/RetailSavePregame.LICENSE.txt',*fixture_paths)]
    compiler=artifact(COMPILER)
    require(compiler['sha256']==COMPILER_SHA,'Reviewed x64 compiler changed')
    content_id=hashlib.sha256(json.dumps(dict(inputs=inputs,compiler=compiler),sort_keys=True).encode()).hexdigest()[:16]
    build_root=PROJECT/'Build/RetailSavePregame'/content_id
    for part in (build_root,*build_root.parents):
        if part.exists():
            require(not part.lstat().st_file_attributes&0x400,'Reparse component build path')
    if REPORT.exists():
        old=json.loads(REPORT.read_text(encoding='utf-8'))
        require(old['status']=='PASS_X64_RETAIL_PREGAME_COMPONENT' and old['inputs']==inputs and old['compiler']==compiler,
            'Inspect and preserve the previous result before rebuilding changed inputs')
        for row in old['results']:
            require(artifact(row['executable']['path'])==row['executable'],'Retained component executable changed')
        print(json.dumps(dict(status=old['status'],reused=True,checks=[r['test']['checks'] for r in old['results']])))
        return
    require(not build_root.exists(),'Inspect partial component build before retrying')
    protected=[artifact(PROJECT/name) for name in ('Play/EarlyAccess/release.json',
        'evidence/save_menu/20261013_original_screen/current_progress.json',
        'evidence/goody_hut/runtime_fonts/preparation_identity_audit.json')]
    allowed,calls=set(),[]
    setup=build_root/'read_build_environment.cmd'
    allowed.add(('cmd.exe','/d','/c',str(setup)))
    writable_reports={key(STAGE/name) for name in ('build_started.json','build_result.json',
        'compile_O2.log','compile_Od.log','test_O2.log','test_Od.log')}

    def audit(event,args):
        if event=='subprocess.Popen':
            command=next((x for x in allowed if subprocess.list2cmdline(x)==args[1]),None) if isinstance(args[1],str) else tuple(str(x) for x in args[1])
            require(command in allowed,'Unapproved component child command')
            require(args[0] is None or key(args[0])==key(command[0]) or
                Path(args[0]).name.casefold()==command[0].casefold()=='cmd.exe','Unexpected child executable override')
            calls.append(command)
        if event=='open' and args and isinstance(args[0],(str,bytes,os.PathLike)):
            writing=(isinstance(args[1],str) and any(c in args[1] for c in 'wax+')) or (
                isinstance(args[2],int) and args[2]&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND))
            if writing:
                require(within(os.fsdecode(args[0]),build_root) or key(os.fsdecode(args[0])) in writable_reports,
                    'Component write escaped owned outputs')
        if event in ('os.remove','os.rmdir','os.mkdir','os.rename','os.chmod','os.link','os.symlink'):
            for target in (args[:2] if event in ('os.rename','os.link','os.symlink') else args[:1]):
                if isinstance(target,(str,bytes,os.PathLike)):
                    require(within(os.fsdecode(target),build_root),'Component mutation escaped owned build root')
        if event.startswith(('ctypes.dlopen','socket.','urllib.','http.client.')) or event in ('os.system','os.startfile','os.startfile/2'):
            raise RuntimeError('Candidate loading, network or interactive execution is forbidden')

    build_root.parent.mkdir(parents=True,exist_ok=True)
    sys.addaudithook(audit)
    build_root.mkdir()
    with (STAGE/'build_started.json').open('x',encoding='utf-8') as stream:
        json.dump(dict(build_root=str(build_root),inputs=inputs,compiler=compiler,protected=protected),stream,indent=2)
    results=[]
    try:
        environment,actual_compiler=environment_for(VS,'x64',build_root)
        require(key(actual_compiler)==key(COMPILER),'Compiler selection differs')
        environment['VSLANG']='1033'
        for flavor,options in (('O2',['/O2']),('Od',['/Od','/RTC1'])):
            directory=build_root/flavor;directory.mkdir()
            exe,obj=directory/'RetailSavePregameTests.exe',directory/'retail_save_pregame.obj'
            response,deps=directory/'compile.rsp',directory/'dependencies.json'
            flags=['/nologo','/std:c++17','/EHsc','/W4','/WX','/MT','/utf-8',*options,
                f'/I"{PROJECT/"Source/Host"}"',f'"{SOURCE}"',f'/Fo"{obj}"',f'/Fe"{exe}"',f'/sourceDependencies "{deps}"']
            response.write_text('\n'.join(flags)+'\n',encoding='utf-8')
            command=[str(COMPILER),'@'+str(response),'/link','/INCREMENTAL:NO','/MACHINE:X64','/Brepro','/WX','/OPT:REF','/OPT:ICF']
            allowed.add(tuple(command))
            build=run(command,cwd=directory,env=environment,timeout=120)
            output=(build.stdout+build.stderr).decode('mbcs',errors='replace')
            (STAGE/f'compile_{flavor}.log').write_text(output,encoding='utf-8')
            require(build.returncode==0 and not re.search(r'\bwarning\s+[A-Z]+\d+',output,re.I),
                'Component compile failed: '+flavor+'; inspect compile log')
            dependency=json.loads(deps.read_text(encoding='utf-8-sig'))['Data']
            require(key(dependency['Source'])==key(SOURCE) and all(any(key(x)==key(h) for x in dependency['Includes'])
                for h in (HEADER,PROJECT/'Source/Host/RetailSaveHeader.h')),'Compiler did not consume actual production headers')
            require(not any('sdk_bnw_x64' in key(x) for x in dependency['Includes']),'Unexpected SDK dependency in pure component')
            imports=pe_imports(exe)
            command=[str(exe),*(str(x) for x in fixture_paths)];allowed.add(tuple(command))
            executed=run(command,cwd=directory,env=environment,timeout=45)
            transcript=(executed.stdout+executed.stderr).decode('utf-8',errors='replace').strip()
            (STAGE/f'test_{flavor}.log').write_text(transcript+'\n',encoding='utf-8')
            require(executed.returncode==0,'Actual component tests failed: '+flavor)
            test=json.loads(transcript)
            require(test['status']=='PASS_PUBLIC_PREGAME_COMPONENT' and test['fixtures']==2 and test['checks']>=30 and
                test['mutations']==2048 and test['truncations']>=10991 and
                test['accepted_mutations']+test['rejected_mutations']==2048 and
                test['gamecore_loaded'] is False and test['window_created'] is False and test['input_files_unchanged'] is True,
                'Unexpected actual Pregame test result')
            results.append(dict(flavor=flavor,executable=artifact(exe),object=artifact(obj),pe=pe_header(exe),imports=imports,
                dependency_report=artifact(deps),compiler_input_count=1+len(dependency['Includes']),response=artifact(response),
                compile_log=artifact(STAGE/f'compile_{flavor}.log'),test_log=artifact(STAGE/f'test_{flavor}.log'),test=test))
        require(inputs==[artifact(x['path']) for x in inputs] and protected==[artifact(x['path']) for x in protected],
            'Inputs or protected current/runtime/default changed')
        retired=[]
        for path in [*(Path(x['object']['path']) for x in results),setup]:
            require(within(path,build_root) and not path.lstat().st_file_attributes&0x400,'Unexpected cleanup target')
            row=artifact(path);info=path.stat()
            row['file_identity']=[info.st_dev,info.st_ino];row['mtime_ns']=info.st_mtime_ns
            require(artifact(path)['sha256']==row['sha256'],'Intermediate changed before cleanup')
            path.unlink();require(not path.exists(),'Intermediate cleanup failed');retired.append(row)
        result=dict(schema='zerosis.retail_save.pregame_component.v1',status='PASS_X64_RETAIL_PREGAME_COMPONENT',
            utc=datetime.now(timezone.utc).isoformat(),inputs=inputs,compiler=compiler,build_root=str(build_root),results=results,
            protected=protected,protected_unchanged=True,child_commands=[list(x) for x in calls],retired_intermediates=retired,
            retired_logical_bytes=sum(x['bytes'] for x in retired),user_save_accessed=False,host_gamecore_or_hwnd_executed=False,
            prefix_boundary_only=True,compressed_chunk_framing_or_sdk_restore_verified=False,integrated_into_current_host=False,
            supported_public_profiles=1,unsupported_public_profile_witnesses=1,full_engine_goal_complete=False)
        with REPORT.open('x',encoding='utf-8') as stream:json.dump(result,stream,indent=2)
        print(json.dumps(dict(status=result['status'],checks=[r['test']['checks'] for r in results],
            retired_logical_bytes=result['retired_logical_bytes'],report=artifact(REPORT))))
    except BaseException as error:
        failure=dict(status='FAILED_X64_RETAIL_PREGAME_COMPONENT',error=type(error).__name__+': '+str(error),inputs=inputs,
            compiler=compiler,build_root=str(build_root),completed_modes=results,child_command_count=len(calls),
            protected_unchanged=protected==[artifact(x['path']) for x in protected])
        with REPORT.open('x',encoding='utf-8') as stream:json.dump(failure,stream,indent=2)
        raise


if __name__=='__main__':
    main()
