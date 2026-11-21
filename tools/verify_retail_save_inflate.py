"""Compile pinned inflate-only zlib and execute only owned x64 headless tests."""
from __future__ import annotations
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
from urllib.request import Request,urlopen

sys.dont_write_bytecode=True
from verify_retail_save_header import artifact,require,key,within,COMPILER,COMPILER_SHA,VS
PROJECT=Path(__file__).absolute().parents[1]
STAGE=PROJECT/'evidence/retail_save_container/compression'
REPORT=STAGE/'build_result.json'
ZLIB=PROJECT/'Source/ThirdParty/zlib-1.3.2'
SOURCE=PROJECT/'Tests/retail_save_inflate.cpp'
HEADER=PROJECT/'Source/Host/RetailSaveInflate.h'
LIBRARIAN=COMPILER.parent/'lib.exe'


def imports(path):
    data=path.read_bytes();pe=struct.unpack_from('<I',data,60)[0];optional=pe+24
    require(data[pe:pe+4]==b'PE\0\0' and struct.unpack_from('<H',data,pe+4)[0]==0x8664 and
        struct.unpack_from('<H',data,optional)[0]==0x20b,'Expected AMD64 PE32+')
    sections=struct.unpack_from('<H',data,pe+6)[0];table=optional+struct.unpack_from('<H',data,pe+20)[0]
    def offset(rva):
        for i in range(sections):
            vs,va,rs,raw=struct.unpack_from('<IIII',data,table+40*i+8)
            if va<=rva<va+max(vs,rs):
                require(rva-va<rs and raw+rva-va<len(data),'Unmapped PE import')
                return raw+rva-va
        raise RuntimeError('Missing import section')
    rva,size=struct.unpack_from('<II',data,optional+120);at=offset(rva);names=[]
    for _ in range(size//20):
        row=struct.unpack_from('<IIIII',data,at)
        if not any(row):break
        start=offset(row[3]);end=data.find(b'\0',start,min(start+260,len(data)))
        require(end!=-1,'Unterminated import name');name=data[start:end].decode('ascii').lower()
        require(name in {'kernel32.dll','bcrypt.dll'} or name.startswith('api-ms-win-crt-'),'Unexpected headless dependency '+name)
        names.append(name);at+=20
    else:raise RuntimeError('Unterminated import table')
    return sorted(set(names))


def main():
    require(len(sys.argv)==1 and not sys.flags.optimize,'Unexpected native verifier invocation')
    from native_build import environment_for,run
    receipt=json.loads((ZLIB/'source_receipt.json').read_text(encoding='utf-8'))
    require(receipt['commit']=='da607da739fa6047df13e66a2af6b8bec7c2a498' and len(receipt['files'])==14,'Pinned zlib subset required')
    for row in receipt['files']:
        data=(ZLIB/row['path']).read_bytes()
        require(len(data)==row['bytes'] and hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()==row['git_blob_sha'],
            'Pinned inflate source changed')
    fixture=json.loads((STAGE/'fixtures.json').read_text(encoding='utf-8'))
    fixture_path=Path(fixture['fixture']['path'])
    require(fixture['status']=='PASS_SYNTHETIC_INFLATE_FIXTURES' and artifact(fixture_path)==fixture['fixture'],'Synthetic fixture changed')
    inputs=[artifact(x) for x in (SOURCE,HEADER,Path(__file__).absolute(),PROJECT/'tools/verify_retail_save_header.py',
        PROJECT/'tools/native_build.py',PROJECT/'tools/prepare_retail_inflate_fixtures.py',STAGE/'fixtures.json',
        STAGE/'public_probe.json',ZLIB/'source_receipt.json',fixture_path,*(ZLIB/x['path'] for x in receipt['files']))]
    compiler,librarian=artifact(COMPILER),artifact(LIBRARIAN)
    require(compiler['sha256']==COMPILER_SHA,'Reviewed compiler changed')
    content_id=hashlib.sha256(json.dumps(dict(inputs=inputs,compiler=compiler,librarian=librarian),sort_keys=True).encode()).hexdigest()[:16]
    root=PROJECT/'Build/RetailSaveInflate'/content_id
    if REPORT.exists():
        old=json.loads(REPORT.read_text(encoding='utf-8'))
        require(old['status']=='PASS_X64_RETAIL_INFLATE_COMPONENT' and old['inputs']==inputs,'Inspect prior native result before replacing it')
        for row in old['results']:
            require(artifact(row['executable']['path'])==row['executable'] and artifact(row['library']['path'])==row['library'],'Retained native artifact changed')
        print(json.dumps(dict(status=old['status'],reused=True)));return
    require(not root.exists(),'Inspect partial native build before retrying')
    # Only this immutable public blob is fetched, before the native-child guard.
    probe=json.loads((STAGE/'public_probe.json').read_text(encoding='utf-8'))
    url='https://raw.githubusercontent.com/bmaupin/js-civ5save/858ce8532725f634e64fa8acaf355aa8e50829bf/src/__tests__/resources/1.0.3.279.Civ5Save'
    with urlopen(Request(url,headers={'User-Agent':'ZeroSis-Native-Inflate-Public-Pipe'}),timeout=20) as stream:
        require(stream.geturl()==url,'Unexpected public fixture redirect');full=stream.read(1024*1024+1)
    require(len(full)==418069 and hashlib.sha1(b'blob '+str(len(full)).encode()+b'\0'+full).hexdigest()=='186fb9a84f4e47192e11b8cd98b436a48ccbee16','Public blob differs')
    prefix=(PROJECT/'Tests/Fixtures/RetailSaveHeader/bnw_279.prefix').read_bytes()+(PROJECT/'Tests/Fixtures/RetailSavePregame/bnw_279.pregame').read_bytes()
    require(full[:10991]==prefix,'Verified public uncompressed prefix changed')
    public=full[10991:];del full
    protected=[artifact(PROJECT/name) for name in ('Play/EarlyAccess/release.json',
        'evidence/save_menu/20261013_original_screen/current_progress.json','evidence/goody_hut/runtime_fonts/preparation_identity_audit.json',
        'evidence/goody_hut/runtime_fonts/system_freeze_hold.json')]
    for part in (root,*root.parents):
        if part.exists():require(not part.lstat().st_file_attributes&0x400,'Reparse native build path')
    allowed,calls=set(),[];setup=root/'read_build_environment.cmd';allowed.add(('cmd.exe','/d','/c',str(setup)))
    reports={key(STAGE/name) for name in ('build_started.json','build_result.json','compile_O2.log','compile_Od.log','test_O2.log','test_Od.log')}
    def audit(event,args):
        if event=='subprocess.Popen':
            command=next((x for x in allowed if subprocess.list2cmdline(x)==args[1]),None) if isinstance(args[1],str) else tuple(str(x) for x in args[1])
            require(command in allowed,'Unapproved native child command')
            require(args[0] is None or key(args[0])==key(command[0]) or Path(args[0]).name.casefold()==command[0].casefold()=='cmd.exe','Unexpected native executable override');calls.append(command)
        if event=='open' and args and isinstance(args[0],(str,bytes,os.PathLike)):
            writing=(isinstance(args[1],str) and any(c in args[1] for c in 'wax+')) or (isinstance(args[2],int) and args[2]&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND))
            if writing:require(within(os.fsdecode(args[0]),root) or key(os.fsdecode(args[0])) in reports,'Native write escaped owned outputs')
        if event in ('os.remove','os.rmdir','os.mkdir','os.rename','os.chmod','os.link','os.symlink'):
            for target in (args[:2] if event in ('os.rename','os.link','os.symlink') else args[:1]):
                if isinstance(target,(str,bytes,os.PathLike)):require(within(os.fsdecode(target),root),'Native mutation escaped owned build root')
        if event.startswith(('ctypes.dlopen','socket.','urllib.','http.client.')) or event in ('os.system','os.startfile','os.startfile/2'):
            raise RuntimeError('Network, candidate loading or interactive launch forbidden during native proof')
    root.parent.mkdir(parents=True,exist_ok=True);sys.addaudithook(audit);root.mkdir()
    with (STAGE/'build_started.json').open('x',encoding='utf-8') as f:json.dump(dict(build_root=str(root),inputs=inputs,compiler=compiler,librarian=librarian,protected=protected),f,indent=2)
    results=[]
    try:
        env,selected=environment_for(VS,'x64',root);require(key(selected)==key(COMPILER),'Compiler selection differs');env['VSLANG']='1033'
        for flavor,options in (('O2',['/O2']),('Od',['/Od','/RTC1'])):
            directory=root/flavor;directory.mkdir();objects=[];dependencies=[];responses=[];transcripts=[]
            def compile_one(source,stem,c_language):
                obj=directory/(stem+'.obj');deps=directory/(stem+'.deps.json');rsp=directory/(stem+'.rsp')
                flags=['/nologo','/c','/TC' if c_language else '/TP','/W3' if c_language else '/W4','/WX','/MT','/utf-8','/DZ_SOLO','/DNO_GZIP',*options]
                if not c_language:flags+=['/std:c++17','/EHsc']
                flags += [f'/I"{ZLIB}"',f'"{source}"',f'/Fo"{obj}"',f'/sourceDependencies "{deps}"']
                rsp.write_text('\n'.join(flags)+'\n',encoding='utf-8');command=[str(COMPILER),'@'+str(rsp)];allowed.add(tuple(command))
                compiled=run(command,cwd=directory,env=env,timeout=120);text=(compiled.stdout+compiled.stderr).decode('mbcs',errors='replace');transcripts.append(text)
                (STAGE/f'compile_{flavor}.log').write_text(''.join(transcripts),encoding='utf-8')
                require(compiled.returncode==0 and not re.search(r'\bwarning\s+[A-Z]+\d+',text,re.I),'Native compile failed; inspect '+flavor+' compile log')
                actual=json.loads(deps.read_text(encoding='utf-8-sig'))['Data'];require(key(actual['Source'])==key(source),'Compiler consumed a different source')
                require(not any('sdk_bnw_' in key(x) for x in actual['Includes']),'Unexpected GameCore/SDK dependency')
                if not c_language:require(any(key(x)==key(HEADER) for x in actual['Includes']),'Actual production decoder header not consumed')
                objects.append(artifact(obj));dependencies.append(artifact(deps));responses.append(artifact(rsp));return obj
            zobjects=[compile_one(ZLIB/(name+'.c'),name,True) for name in ('adler32','inflate','inftrees','inffast','zutil')]
            library=directory/'zlib_inflate_x64.lib';command=[str(LIBRARIAN),'/nologo','/MACHINE:X64','/Brepro','/OUT:'+str(library),*(str(x) for x in zobjects)];allowed.add(tuple(command))
            archived=run(command,cwd=directory,env=env,timeout=60);require(archived.returncode==0,'Inflate-only library creation failed')
            test_obj=compile_one(SOURCE,'retail_save_inflate',False);exe=directory/'RetailSaveInflateTests.exe'
            command=[str(COMPILER),str(test_obj),str(library),'/Fe'+str(exe),'/link','bcrypt.lib','/MACHINE:X64','/INCREMENTAL:NO','/Brepro','/WX','/OPT:REF','/OPT:ICF'];allowed.add(tuple(command))
            linked=run(command,cwd=directory,env=env,timeout=60);require(linked.returncode==0,'Inflate test link failed: '+(linked.stdout+linked.stderr).decode('mbcs',errors='replace')[:2000])
            dlls=imports(exe);command=[str(exe),str(fixture_path)];allowed.add(tuple(command))
            tested=subprocess.run(command,cwd=directory,env=env,input=public,capture_output=True,timeout=60,creationflags=subprocess.CREATE_NO_WINDOW)
            text=(tested.stdout+tested.stderr).decode('utf-8',errors='replace').strip();(STAGE/f'test_{flavor}.log').write_text(text+'\n',encoding='utf-8')
            require(tested.returncode==0,'Native inflate tests failed; inspect '+flavor+' test log');test=json.loads(text)
            require(test['status']=='PASS_RETAIL_INFLATE_COMPONENT' and test['checks']>=30 and test['mutations']==2048 and
                test['public_output_bytes']==probe['decompressed_bytes'] and test['public_output_sha256']==probe['decompressed_sha256'] and
                test['public_strict_rejected'] is True and test['complete_save_validated'] is False and
                test['gamecore_loaded'] is False and test['window_created'] is False and test['input_files_unchanged'] is True,'Unexpected native inflate scope/result')
            results.append(dict(flavor=flavor,executable=artifact(exe),library=artifact(library),objects=objects,dependency_reports=dependencies,
                response_files=responses,imports=dlls,compile_log=artifact(STAGE/f'compile_{flavor}.log'),test_log=artifact(STAGE/f'test_{flavor}.log'),test=test))
        require(inputs==[artifact(x['path']) for x in inputs] and protected==[artifact(x['path']) for x in protected],'Inputs or protected ready state changed')
        retired=[]
        for path in [*(Path(x['path']) for row in results for x in row['objects']),setup]:
            info=path.stat();require(within(path,root) and info.st_nlink==1 and not info.st_file_attributes&0x400,'Unexpected intermediate cleanup target')
            row=dict(**artifact(path),file_identity=[info.st_dev,info.st_ino],mtime_ns=info.st_mtime_ns);require(artifact(path)['sha256']==row['sha256'],'Intermediate changed');path.unlink();retired.append(row)
        result=dict(schema='zerosis.retail_save.inflate_component.v1',status='PASS_X64_RETAIL_INFLATE_COMPONENT',utc=datetime.now(timezone.utc).isoformat(),
            build_root=str(root),inputs=inputs,compiler=compiler,librarian=librarian,results=results,protected=protected,protected_unchanged=True,
            child_commands=[list(x) for x in calls],retired_intermediates=retired,retired_logical_bytes=sum(x['bytes'] for x in retired),
            public_compressed_body_passed_via_binary_stdin=True,public_save_or_body_retained=False,user_saves_accessed=False,
            host_gamecore_or_hwnd_executed=False,integrated_into_current_host=False,sdk_restore_verified=False,full_engine_goal_complete=False)
        with REPORT.open('x',encoding='utf-8') as f:json.dump(result,f,indent=2)
        print(json.dumps(dict(status=result['status'],tests=[r['test'] for r in results],retired_bytes=result['retired_logical_bytes'],report=artifact(REPORT))))
    except BaseException as error:
        with REPORT.open('x',encoding='utf-8') as f:json.dump(dict(status='FAILED_X64_RETAIL_INFLATE_COMPONENT',error=type(error).__name__+': '+str(error),build_root=str(root),inputs=inputs,compiler=compiler,librarian=librarian,completed_modes=results,child_command_count=len(calls),protected_unchanged=protected==[artifact(x['path']) for x in protected]),f,indent=2)
        raise


if __name__=='__main__':main()
