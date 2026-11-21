"""Prove the native filesystem resolves its real GameCore requirement without loading it."""
import json,re
from pathlib import Path
from collect_baseline import PROJECT,read_text,digest
from native_build import environment_for,run
from probe_world_builder import artifact
from filesystem_evidence import validate
from verify_world_builder_map_object import check_artifacts

def main():
    b,c,entry=validate()
    path=PROJECT/'evidence/sdk_x64/link_analysis.json';link=json.loads(path.read_text(encoding='utf-8'));check_artifacts(link)
    if entry not in link['providers'] or link['linker_unresolved_symbol_total']!=0:raise RuntimeError('Filesystem not in official SDK link')
    response=Path(link['link_response']['path']).read_text(encoding='utf-8-sig')
    excluded={'"'+p['library']['path']+'"' for p in link['providers'] if p['name']=='Logging'}
    response='\n'.join(line for line in response.splitlines() if line.strip() not in excluded)
    out=PROJECT/'Build/FileSystem/link_trial';out.mkdir(parents=True,exist_ok=True)
    env,compiler=environment_for(Path(r'C:\Program Files\Microsoft Visual Studio\2022\Community'),'x64',out)
    linker=Path(compiler).with_name('link.exe')
    if digest(linker)!=link['linker_sha256']:raise RuntimeError('Linker differs')
    expected={'?GetInstance@FILogFileMgr@@SAAEAV1@XZ'}
    required='?GetInstance@FIFileSystem@@SAAEAV1@XZ'
    runs=[];library_line='"'+entry['library']['path']+'"'
    for name,omit in (('before',True),('after',False)):
        destination=out/name;destination.mkdir(parents=True,exist_ok=True);dll=destination/'probe.dll'
        lines=[]
        for line in response.splitlines():
            if omit and line.strip()==library_line:continue
            if line.startswith('/OUT:'):line=f'/OUT:"{dll}"'
            elif line.startswith('/IMPLIB:'):line=f'/IMPLIB:"{destination/"probe.lib"}"'
            elif line.startswith('/MAP:'):line=f'/MAP:"{destination/"probe.map"}"'
            lines.append(line)
        rsp=destination/'link.rsp';rsp.write_text('\n'.join(lines)+'\n',encoding='utf-8')
        result=run([linker,'@'+str(rsp)],cwd=destination,env=env,timeout=120)
        log=PROJECT/'evidence/filesystem'/('link_'+name+'.log');log.write_bytes(result.stdout+result.stderr);text=read_text(log)
        symbols=set();unparsed=[]
        for line in text.splitlines():
            if not re.search(r'error LNK(?:2001|2019):',line):continue
            payload=re.split(r'error LNK(?:2001|2019):\s*',line,maxsplit=1)[1]
            match=re.match(r'([A-Za-z_][A-Za-z_0-9@$?]*)(?="|$)',payload) or re.search(r'\((\?[^\s()]+|__imp_[^\s()]+)\)',payload) or re.search(r'\s([A-Za-z_][A-Za-z_0-9@$?]*)$',payload)
            if match:symbols.add(match[1])
            else:unparsed.append(line)
        wanted=expected|{required} if omit else expected
        total=re.findall(r'LNK1120:\s*(\d+)',text)
        if not result.returncode or dll.exists() or unparsed or symbols!=wanted or not total or int(total[-1])!=len(wanted):
            raise RuntimeError('Unexpected filesystem link trial: '+str(log))
        runs.append({'name':name,'exit_code':result.returncode,'response':artifact(rsp),'log':artifact(log),'unresolved_count':len(symbols),'unresolved':sorted(symbols),'generated_dll':False})
    check_artifacts(link)
    report={'status':'FILESYSTEM_SDK_LINK_PASS_NOT_GAME_RUNTIME','probe':artifact(Path(__file__).resolve()),
            'official_link':artifact(path),'component_build':artifact(PROJECT/'evidence/filesystem/build_result.json'),
            'component_conformance':artifact(PROJECT/'evidence/filesystem/conformance.json'),'linker':artifact(linker),
            'runs':runs,'before':2,'after':1,'resolved':[required],'gamecore_objects':161,'providers':16,
            'official_unresolved_symbols':0,'baseline_excluded_providers':['Logging'],
            'gamecore_loaded':False,'game_launched':False,'game_multicore_verified':False}
    (PROJECT/'evidence/filesystem/link_trial.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(report['status']+' 2 -> 1')
if __name__=='__main__':main()
