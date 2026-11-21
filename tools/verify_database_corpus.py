"""Compare audited native readers on stable, owned copies of three cached game databases."""
import argparse
import difflib
import json
import os
from pathlib import Path
import re
import shutil
import uuid
from collect_baseline import PROJECT,digest,read_text,pe_header
from native_build import environment_for,run,checked_run
from database_evidence import validate

def artifact(p):return {'path':str(p),'sha256':digest(p)}
def main(vs):
    candidate,conformance,provider=validate(PROJECT/'evidence/database/candidate/build_result.json')
    original=json.loads((PROJECT/'evidence/database/reference/build_result.json').read_text())
    source=PROJECT/'Tests/sdk_database_corpus.cpp';includes=PROJECT/'Source/Providers/Database';e=PROJECT/'evidence/database/corpus';e.mkdir(parents=True,exist_ok=True)
    builds={};inspector=Path(candidate['compiler']['path']).with_name('dumpbin.exe')
    for arch in ('x86','x64'):
        directory=PROJECT/'Build/Database'/arch;exe=directory/'database_corpus.exe';linkmap=directory/'database_corpus.map'
        if arch=='x86':
            vc=Path(r'C:\Program Files (x86)\Microsoft Visual Studio 9.0\VC');win=Path(r'C:\Program Files (x86)\Microsoft SDKs\Windows\v7.0A')
            compiler=vc/'bin/cl.exe';env={k.upper():v for k,v in os.environ.items()};env['INCLUDE']=f"{vc/'include'};{win/'Include'}";env['LIB']=f"{vc/'lib'};{win/'Lib'}"
            env['PATH']=f"{vc/'bin'};{vc.parent/'Common7/IDE'};{win/'bin'};{env.get('PATH','')}"
            sdk=PROJECT/'Source/SDK_BNW_Original/CvGameDatabase/include';lib=Path(original['library']['path']);extra=['/W3','/D_SECURE_SCL=0','/D_HAS_ITERATOR_DEBUGGING=0']
        else:
            env,compiler=environment_for(vs,arch,directory);compiler=Path(compiler);sdk=PROJECT/'Source/SDK_BNW_x64/CvGameDatabase/include';lib=Path(candidate['library']['path']);extra=['/W4','/WX','/std:c++14','/utf-8','/D_SILENCE_STDEXT_HASH_DEPRECATION_WARNINGS']
        flags=['/nologo','/O2','/MD','/EHsc','/DWIN32','/DFINAL_RELEASE','/D_CRT_SECURE_NO_WARNINGS',*extra,f'/I"{includes}"',f'/I"{sdk}"',f'"{source}"',f'"{lib}"','bcrypt.lib',f'/Fo"{directory/"database_corpus.obj"}"',f'/Fe"{exe}"']
        rsp=directory/'corpus.rsp';rsp.write_text('\n'.join(flags),encoding='utf-8')
        r=run([compiler,'@'+str(rsp),'/link','/MACHINE:'+arch.upper(),'/INCREMENTAL:NO',f'/MAP:{linkmap}'],cwd=directory,env=env);log=e/('build_'+arch+'.log');log.write_bytes(r.stdout+r.stderr)
        if r.returncode or re.search(r'\bwarning\s+[A-Z]+\d+',read_text(log)):raise RuntimeError(read_text(log))
        if arch=='x86':checked_run([win/'bin/mt.exe','-nologo','-manifest',exe.with_suffix('.exe.manifest'),f'-outputresource:{exe};1'],cwd=directory,env=env)
        builds[arch]={'executable':{**artifact(exe),'pe':pe_header(exe)},'compiler':artifact(compiler),'map':artifact(linkmap),'library':artifact(lib),'response':artifact(rsp),'log':artifact(log)}
    audits=[];allowed={'bcrypt.dll','kernel32.dll','msvcp90.dll','msvcr90.dll','msvcp140.dll','vcruntime140.dll','vcruntime140_1.dll','cvgamedatabasewin32final release.dll','lua51_win32.dll','zerosisdatabase_x64.dll'}
    audit_paths=[Path(b['executable']['path']) for b in builds.values()]+[Path(d['copy']['path']) for d in original['original_dlls']]+[Path(candidate['dll']['path'])]
    for i,path in enumerate(audit_paths):
        r=checked_run([inspector,'/nologo','/dependents',path],cwd=path.parent);log=e/('imports_'+str(i)+'.log');log.write_bytes(r.stdout+r.stderr)
        deps=re.findall(r'^[ \t]+([^\\:\r\n]+\.dll)[ \t]*\r?$',r.stdout.decode('mbcs'),re.M|re.I)
        if not deps or any(d.lower() not in allowed and not d.lower().startswith('api-ms-win-crt-') for d in deps):raise RuntimeError('Unexpected native corpus dependency')
        audits.append({'module':artifact(path),'dependencies':deps,'log':artifact(log)})
    cache=Path(r"C:\Users\home\OneDrive\Documents\My Games\Sid Meier's Civilization 5\cache")
    directory=PROJECT/'Build/Database/corpus'/uuid.uuid4().hex;directory.mkdir(parents=True);copies=[];runs=[];comparisons=[]
    for name in ('Civ5CoreDatabase.db','Civ5DebugDatabase.db','Localization-Merged.db'):
        original_file=cache/name
        for suffix in ('-wal','-journal'):
            sidecar=Path(str(original_file)+suffix)
            if sidecar.exists() and sidecar.stat().st_size:raise RuntimeError('Live database sidecar present; do not copy this snapshot')
        before=digest(original_file);stat=original_file.stat();copy=directory/name;shutil.copyfile(original_file,copy)
        if digest(copy)!=before or digest(original_file)!=before or original_file.stat().st_mtime_ns!=stat.st_mtime_ns:raise RuntimeError('Database changed while copied')
        copies.append({'original':artifact(original_file),'copy':artifact(copy),'size':stat.st_size,'mtime_ns':stat.st_mtime_ns,'original_opened_by_harness':False})
        outputs=[]
        for arch in ('x86','x64'):
            exe=Path(builds[arch]['executable']['path']);r=run([exe,copy],cwd=exe.parent,timeout=60);log=e/(copy.stem+'_'+arch+'.log');log.write_bytes(r.stdout+r.stderr)
            if r.returncode or b'PASS|' not in r.stdout:raise RuntimeError('Native corpus failure: '+str(log)+' code='+str(r.returncode))
            outputs.append(r.stdout.replace(b'\r\n',b'\n'));runs.append({'database':name,'architecture':arch,'returncode':r.returncode,'log':artifact(log)})
        summary=re.search(rb'^CORPUS\|(\d+)\|(\d+)\|(\d+)\|integrity_ok',outputs[0],re.M)
        if not summary:raise RuntimeError('Corpus summary absent')
        same=outputs[0]==outputs[1];diff=e/(copy.stem+'.diff');diff.write_text(''.join(difflib.unified_diff(outputs[0].decode('utf-8').splitlines(True),outputs[1].decode('utf-8').splitlines(True),fromfile='original',tofile='candidate')),encoding='utf-8')
        comparisons.append({'database':name,'equal_table_digests_and_trace':same,'tables':int(summary[1]),'rows':int(summary[2]),'values':int(summary[3]),'diff':artifact(diff)})
        if digest(copy)!=before or digest(original_file)!=before:raise RuntimeError('Read-only corpus altered input')
    result={'status':'SDK_DATABASE_CACHED_CORPUS_PASS' if all(c['equal_table_digests_and_trace'] for c in comparisons) else 'SDK_DATABASE_CACHED_CORPUS_DIFFERENCES',
        'provider':provider,'builds':builds,'sources':[artifact(source),artifact(includes/'SdkDatabaseIncludes.h')],'builder':artifact(Path(__file__).resolve()),'audits':audits,
        'copies':copies,'runs':runs,'comparisons':comparisons,'tables':sum(c['tables'] for c in comparisons),'rows':sum(c['rows'] for c in comparisons),'values':sum(c['values'] for c in comparisons),
        'scope':'Cached snapshot copies, SHA256 of ordered typed getters and full SQL hex bytes; not current mod/new-game/SQL-write acceptance',
        'originals_unchanged':True,'copies_unchanged':True,'game_launched':False,'gamecore_loaded':False}
    (e/'conformance.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps({k:result[k] for k in ('status','tables','rows','values','comparisons')}))
    if result['status']!='SDK_DATABASE_CACHED_CORPUS_PASS':raise SystemExit(1)
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--vs',type=Path,required=True);main(p.parse_args().vs)
