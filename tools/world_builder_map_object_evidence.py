"""Read-only evidence checks for map operations and their separate link trial."""
import json,re
from pathlib import Path
from collect_baseline import PROJECT,read_text,pe_header
from verify_world_builder_map_object import check_artifacts,normalized

def validate():
    root=PROJECT/'evidence/world_builder/map_object'
    b=json.loads((root/'build_result.json').read_text(encoding='utf-8'));c=json.loads((root/'conformance.json').read_text(encoding='utf-8'));l=json.loads((root/'link_trial.json').read_text(encoding='utf-8'))
    r=json.loads(Path(c['reference_report']['path']).read_text(encoding='utf-8'));check_artifacts([b,c,l,r])
    from world_builder_map_access import integrated
    sdk_integrated=integrated()
    if b['status']!=('WORLD_BUILDER_MAP_OBJECT_BUILT' if sdk_integrated else 'WORLD_BUILDER_MAP_OBJECT_BUILT_ISOLATED_HEADERS') or c['status']!='WORLD_BUILDER_MAP_OBJECT_COMPONENT_PASS' or c['issues']:raise RuntimeError('Map object component did not pass')
    if any(r['sdk_access_declarations_integrated']!=sdk_integrated for r in (b,c,l)):raise RuntimeError('Map object SDK integration claim differs')
    if sdk_integrated and any(r['sha256']!=r['input']['sha256'] for r in b['generated_headers']):raise RuntimeError('Map object headers differ from the compiled SDK')
    if l['status']!='WORLD_BUILDER_MAP_OBJECT_LINK_EXPERIMENT_PASS' or (l['before'],l['after'],len(l['resolved']),l['added'])!=(15,5,10,[]):raise RuntimeError('Link experiment delta differs')
    modes={'defaults','resize','clear','preserve','swap','units','resize-fields','ownership','all-plots','legacy','hidden-handles'}
    if len(c['runs'])!=11 or {row['case'] for row in c['runs']}!=modes:raise RuntimeError('Incomplete map operation corpus')
    count=total=fixes=0
    for row in c['runs']:
        original,layout_a=normalized(read_text(Path(row['reference_log']['path'])));candidate,layout_b=normalized(read_text(Path(row['log']['path'])))
        if layout_a!=[84,136,436,64] or layout_b!=[88,136,440,64]:raise RuntimeError('Observed native layout differs')
        if row['exit_code'] or row['checks']<=0:raise RuntimeError('Map operation failed')
        if row['case']=='hidden-handles':
            if not row['intentional_adjustment'] or 'HIDDEN-HANDLES|0|0|0|0' not in original or 'HIDDEN-HANDLES|65535|65535|0|0' not in candidate:raise RuntimeError('Hidden-handle defect not reproduced/fixed')
            original=['HIDDEN-HANDLES|65535|65535|0|0' if s=='HIDDEN-HANDLES|0|0|0|0' else s for s in original];fixes+=1
        elif row['intentional_adjustment']:raise RuntimeError('Undeclared behavior adjustment')
        if original!=candidate:raise RuntimeError('Map operations differ')
        for state in row['states']:
            a=Path(state['reference']['path']).read_bytes();d=Path(state['candidate']['path']).read_bytes()
            if not state['exact'] or a!=d or len(a)!=state['bytes']:raise RuntimeError('Map state records differ')
            count+=1;total+=len(a)
    if (count,total,fixes)!=(25,66867,1) or (c['exact_state_records'],c['exact_state_bytes'])!=(count,total):raise RuntimeError('Map state accounting differs')
    hard=c['hardening'];text=read_text(Path(hard['log']['path']))
    if hard['exit_code'] or (hard['checks'],hard['cpp_allocation_failures'],hard['successful_retries'])!=(131322,24,4):raise RuntimeError('Map failure coverage differs')
    if not re.search(r'^PASS\|131322\s*$',text,re.M) or 'WORKERS|4|256_independent_maps|2048_units' not in text or 'FAULTS|24|4|' not in text:raise RuntimeError('Native map execution proof missing')
    linkmap=read_text(Path(b['consumers']['map_operations']['map']['path']))
    if len(c['native_sdk_symbol_proof'])!=8 or any(line not in linkmap or 'SdkWorldBuilderMap.obj' not in line for line in c['native_sdk_symbol_proof']):raise RuntimeError('SDK native object proof missing')
    for consumer in b['consumers'].values():
        if pe_header(Path(consumer['executable']['path']))['architecture']!='x64':raise RuntimeError('Wrong map candidate architecture')
    for log in b['logs']:
        if re.search(r'\b(?:warning|error)\s+[A-Z]+\d+',read_text(Path(log['path'])),re.I):raise RuntimeError('Map candidate build diagnostics')
    for report,keys in ((b,('gamecore_loaded','game_launched','file_bridge_implemented')),
        (c,('gamecore_linked','gamecore_loaded','game_launched','file_bridge_implemented')),
        (l,('official_link_report_replaced','gamecore_linked','gamecore_loaded','game_launched'))):
        if any(report[k] for k in keys):raise RuntimeError('Unsupported map integration/runtime claim')
    before=set(l['runs'][0]['unresolved']);after=set(l['runs'][1]['unresolved'])
    if before-after!=set(l['resolved']) or after-before or len(before)!=15 or len(after)!=5:raise RuntimeError('Link symbol accounting differs')
    for run in l['runs']:
        if not run['exit_code'] or run['generated_dll'] or not re.search(r'LNK1120:\s*'+str(run['unresolved_count'])+r'(?!\d)',read_text(Path(run['log']['path']))):raise RuntimeError('Link failure record differs')
    return b,c,l

if __name__=='__main__':
    b,c,l=validate();print(json.dumps({'status':'WORLD_BUILDER_MAP_OBJECT_EVIDENCE_PASS','exact_states':c['exact_state_records'],'link_experiment':[l['before'],l['after']]}))
