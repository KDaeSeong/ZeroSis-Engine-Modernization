"""Non-loading A/B link experiment against the accepted GameCore object batch.

The pool friend declarations are isolated and layout-neutral. This experiment
does not replace the coherent SDK build or publish a linked GameCore provider.
"""
import csv,json,re
from pathlib import Path
from collect_baseline import PROJECT,digest,read_text
from native_build import environment_for,run
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts

def main():
    folder=PROJECT/'evidence/world_builder/map_object';bp=folder/'build_result.json';cp=folder/'conformance.json'
    build=json.loads(bp.read_text(encoding='utf-8'));conformance=json.loads(cp.read_text(encoding='utf-8'))
    check_artifacts([build,conformance])
    if conformance['status']!='WORLD_BUILDER_MAP_OBJECT_COMPONENT_PASS' or conformance['issues']:raise RuntimeError('Map object component not verified')
    baseline_path=PROJECT/'evidence/sdk_x64/link_analysis.json';baseline=json.loads(baseline_path.read_text(encoding='utf-8'));check_artifacts(baseline)
    compilation_path=PROJECT/'evidence/sdk_x64/build_result.json';compilation=json.loads(compilation_path.read_text(encoding='utf-8'));check_artifacts(compilation)
    out=PROJECT/'Build/WorldBuilder/map_object_link_trial';out.mkdir(parents=True,exist_ok=True)
    env,compiler=environment_for(Path(r'C:\Program Files\Microsoft Visual Studio\2022\Community'),'x64',out)
    linker=Path(compiler).with_name('link.exe')
    if digest(linker)!=baseline['linker_sha256']:raise RuntimeError('Different baseline linker')
    response_path=Path(baseline['link_response']['path']);text=response_path.read_text(encoding='utf-8-sig')
    excluded=[p for p in baseline['providers'] if p['name'] in ('WorldBuilderMapBridge','FileSystem','Logging')]
    remove={'"'+p['library']['path']+'"' for p in excluded}
    text='\n'.join(line for line in text.splitlines() if line.strip() not in remove)
    quoted_files=[Path(m[1]) for m in re.finditer(r'^"([^"]+)"\s*$',text,re.M)]
    for p in quoted_files:
        if not p.is_file():raise RuntimeError('Missing accepted link input: '+str(p))
    link_inputs=[artifact(p) for p in quoted_files]
    names_path=PROJECT/'evidence/world_builder/mod_data_link_after/link_unresolved_candidates.csv'
    original_names={r['decorated_or_c_symbol'] for r in csv.DictReader(names_path.open(encoding='utf-8-sig'))}
    original_names -= {'?GetInstance@FDebugHelper@@SAAEAV1@XZ','?LoadSymbols@FDebugHelper@@QEAA_NPEAUHINSTANCE__@@@Z'}
    runs=[]
    for name,extra in (('baseline',None),('map_object',build['library'])):
        destination=out/name;destination.mkdir(parents=True,exist_ok=True);dll=destination/'probe.dll'
        lines=[]
        for line in text.splitlines():
            if line.startswith('/OUT:'):line=f'/OUT:"{dll}"'
            elif line.startswith('/IMPLIB:'):line=f'/IMPLIB:"{destination/"probe.lib"}"'
            elif line.startswith('/MAP:'):line=f'/MAP:"{destination/"probe.map"}"'
            lines.append(line)
        if extra:lines.append('"'+extra['path']+'"')
        response=destination/'link.rsp';response.write_text('\n'.join(lines)+'\n',encoding='utf-8')
        r=run([linker,'@'+str(response)],cwd=destination,env=env,timeout=120)
        log=folder/('link_trial_'+name+'.log');log.write_bytes(r.stdout+r.stderr);diagnostics=read_text(log)
        symbols={};unparsed=[]
        for line in diagnostics.splitlines():
            if not re.search(r'error LNK(?:2001|2019):',line):continue
            payload=re.split(r'error LNK(?:2001|2019):\s*',line,maxsplit=1)[1]
            c_name=re.match(r'([A-Za-z_][A-Za-z_0-9@$?]*)(?="|$)',payload)
            decorated=re.search(r'\((\?[^\s()]+|__imp_[^\s()]+)\)',payload)
            trailing=re.search(r'\s([A-Za-z_][A-Za-z_0-9@$?]*)$',payload)
            match=c_name or decorated or trailing
            if match:symbols.setdefault(match[1],line)
            else:unparsed.append(line)
        total=re.findall(r'LNK1120:\s*(\d+)',diagnostics)
        if r.returncode==0 or dll.exists() or unparsed or not total or int(total[-1])!=len(symbols):raise RuntimeError('Unexpected link experiment outcome; inspect '+str(log))
        if name=='baseline' and set(symbols)!=original_names:raise RuntimeError('Accepted baseline link no longer reproduces')
        row={'name':name,'exit_code':r.returncode,'unresolved_count':len(symbols),'unresolved':sorted(symbols),'response':artifact(response),'log':artifact(log),'generated_dll':False}
        runs.append(row);print(name,len(symbols),flush=True)
    after=set(runs[1]['unresolved']);resolved=sorted(original_names-after);added=sorted(after-original_names)
    if added or len(resolved)!=10 or len(after)!=5:raise RuntimeError('Unexpected map object symbol delta')
    check_artifacts(baseline)
    report={'status':'WORLD_BUILDER_MAP_OBJECT_LINK_EXPERIMENT_PASS','baseline_report':artifact(baseline_path),'compilation_report':artifact(compilation_path),
        'component_build':artifact(bp),'component_conformance':artifact(cp),'probe':artifact(Path(__file__).resolve()),'linker':artifact(linker),
        'quoted_link_inputs':link_inputs,'runs':runs,'before':len(original_names),'after':len(after),'resolved':resolved,'added':added,
        'sdk_access_declarations_integrated':build['sdk_access_declarations_integrated'],'official_link_report_replaced':False,
        'baseline_excluded_providers':[p['name'] for p in excluded],'baseline_symbols_resolved_by_debug':2,'baseline_symbol_reference':artifact(names_path),'official_response_unresolved_count':baseline['linker_unresolved_symbol_total'],'gamecore_linked':False,'gamecore_loaded':False,'game_launched':False,
        'scope':'LINK_ONLY_A_B_WITH_EXISTING_SDK_OBJECTS; MAP_OBJECT_WITH_CURRENT_HEADERS; FILE_BRIDGE_EXCLUDED_FOR_A_B; GAMECORE_NOT_EXECUTED'}
    (folder/'link_trial.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(report['status'])

if __name__=='__main__':main()
