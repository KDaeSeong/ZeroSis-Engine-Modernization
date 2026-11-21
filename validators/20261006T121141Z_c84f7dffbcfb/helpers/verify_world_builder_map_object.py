"""Execute the actual map object and compare exact normalized SDK state records."""
import difflib,json,re
from pathlib import Path
from collect_baseline import PROJECT,digest,read_text
from native_build import run
from probe_world_builder import artifact

def check_artifacts(value):
    if isinstance(value,dict):
        if isinstance(value.get('path'),str) and 'sha256' in value:
            p=Path(value['path'])
            if not p.is_file() or digest(p)!=value['sha256']:raise RuntimeError('Changed map object input: '+str(p))
        for v in value.values():check_artifacts(v)
    elif isinstance(value,list):
        for v in value:check_artifacts(v)

def normalized(text):
    lines=text.splitlines();layout=next((line.split('|')[1:] for line in lines if line.startswith('LAYOUT|')),None)
    if layout is None:raise RuntimeError('Missing actual native layout observation')
    stride=int(layout[0]);result=[]
    for line in lines:
        if line.startswith('LAYOUT|'):continue
        fields=line.split('|')
        if fields[0] in ('POOLS','RESIZE-FIELDS'):
            index=1 if fields[0]=='POOLS' else 2;size=int(fields[index])
            if size and (size<4 or (size-4)%stride):raise RuntimeError('Non-integral native unit pool count')
            fields[index]='slots='+str((size-4)//stride if size else 0);line='|'.join(fields)
        result.append(line)
    return result,list(map(int,layout))

def main():
    root=PROJECT/'evidence/world_builder/map_object';bp=root/'build_result.json'
    rp=PROJECT/'evidence/world_builder/map_operations_reference/observations.json'
    build=json.loads(bp.read_text(encoding='utf-8'));reference=json.loads(rp.read_text(encoding='utf-8'));check_artifacts(build);check_artifacts(reference)
    if build['status'] not in ('WORLD_BUILDER_MAP_OBJECT_BUILT','WORLD_BUILDER_MAP_OBJECT_BUILT_ISOLATED_HEADERS') or reference['status']!='WORLD_BUILDER_MAP_OPERATIONS_REFERENCE_OBSERVED':raise RuntimeError('Map object prerequisites failed')
    exe=Path(build['consumers']['map_operations']['executable']['path']);rows=[];issues=[];state_bytes=0;state_count=0
    for expected in reference['runs']:
        case=expected['case'];states=root/'states'/case;states.mkdir(parents=True,exist_ok=True)
        r=run([exe,case,states],cwd=exe.parent,timeout=30);log=root/(case+'.log');log.write_bytes(r.stdout+r.stderr)
        original=read_text(Path(expected['log']['path']));actual=read_text(log);a,layout_a=normalized(original);b,layout_b=normalized(actual)
        differences=list(difflib.unified_diff(a,b,n=0));adjustment=None
        if case=='hidden-handles':
            old='HIDDEN-HANDLES|0|0|0|0';new='HIDDEN-HANDLES|65535|65535|0|0'
            if old not in a or new not in b:issues.append('Hidden-reference defect evidence differs')
            adjustment={'reason':'Clear hidden unit/city references when their pools are released','original':old,'candidate':new}
            a=[new if v==old else v for v in a]
        if r.returncode or a!=b:issues.append(case+': operation trace differs after declared ABI/defect handling')
        state_rows=[]
        for expected_state in expected['states']:
            p=Path(expected_state['path']);candidate=states/p.name;equal=candidate.is_file() and p.read_bytes()==candidate.read_bytes()
            if not equal:issues.append(case+': exact normalized state differs at '+p.name)
            size=p.stat().st_size;state_bytes+=size;state_count+=1
            state_rows.append({'reference':expected_state,'candidate':artifact(candidate) if candidate.is_file() else None,'bytes':size,'exact':equal})
        match=re.search(r'^PASS\|(\d+)\s*$',actual,re.M)
        if not match:issues.append(case+': missing completion marker')
        rows.append({'case':case,'exit_code':r.returncode,'checks':int(match[1]) if match else 0,'log':artifact(log),'reference_log':expected['log'],
            'original_native_layout':layout_a,'candidate_native_layout':layout_b,'native_pool_size_normalization':'unit capacity only; native records are not wire records',
            'raw_normalized_differences':differences,'intentional_adjustment':adjustment,'states':state_rows})
        print(case, 'PASS' if not issues else 'SEE_ISSUES',flush=True)
    hard=Path(build['consumers']['map_object_hardening']['executable']['path']);r=run([hard],cwd=hard.parent,timeout=60)
    log=root/'hardening.log';log.write_bytes(r.stdout+r.stderr);text=read_text(log)
    done=re.search(r'^PASS\|(\d+)\s*$',text,re.M);faults=re.search(r'^FAULTS\|(\d+)\|(\d+)\|',text,re.M)
    if r.returncode or not done or not faults or 'WORKERS|4|256_independent_maps|2048_units' not in text or 'CAPACITY|65535_unique_handles|exhaustion|reuse' not in text:issues.append('Map object hardening failed')
    linkmap=read_text(Path(build['consumers']['map_operations']['map']['path']))
    required=('??0CvWorldBuilderMap@@','??1CvWorldBuilderMap@@','?Resize@CvWorldBuilderMap@@','?ClearScenarioData@CvWorldBuilderMap@@','?SwapPlayers@CvWorldBuilderMap@@','?SwapCityStates@CvWorldBuilderMap@@','?AddUnit@CvWorldBuilderMap@@','?RemoveUnit@CvWorldBuilderMap@@')
    proof=[]
    for symbol in required:
        lines=[line.strip() for line in linkmap.splitlines() if re.search(r'\s'+re.escape(symbol),line) and 'SdkWorldBuilderMap.obj' in line]
        if not lines:issues.append('Actual SDK implementation absent from native consumer: '+symbol)
        proof.extend(lines)
    report={'status':'WORLD_BUILDER_MAP_OBJECT_COMPONENT_PASS' if not issues else 'WORLD_BUILDER_MAP_OBJECT_FAILURES','issues':issues,
        'build_report':artifact(bp),'reference_report':artifact(rp),'verifier':artifact(Path(__file__).resolve()),'runs':rows,'exact_state_records':state_count,'exact_state_bytes':state_bytes,
        'hardening':{'exit_code':r.returncode,'checks':int(done[1]) if done else 0,'cpp_allocation_failures':int(faults[1]) if faults else 0,'successful_retries':int(faults[2]) if faults else 0,'log':artifact(log)},
        'native_sdk_symbol_proof':proof,'gamecore_linked':False,'gamecore_loaded':False,'game_launched':False,'file_bridge_implemented':False,
        'sdk_access_declarations_integrated':build['sdk_access_declarations_integrated'],
        'scope':'ACTUAL_SDK_MAP_OBJECT_OPERATIONS_NOT_GAMECORE_OR_FILE_BRIDGE',
        'not_verified':['raw malloc allocation failure injection','direct SDK pool API hardening','file read/write/preview integration','whole-game state or saves','same map concurrent mutation','game multicore or performance']}
    (root/'conformance.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':report['status'],'issues':issues,'exact_state_records':state_count,'exact_state_bytes':state_bytes,'hardening':report['hardening']}))
    if issues:raise SystemExit(1)

if __name__=='__main__':main()
