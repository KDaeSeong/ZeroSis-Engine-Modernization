"""Recheck actual map bridge observations and isolated GameCore link evidence."""
import json,re
from pathlib import Path
from collect_baseline import PROJECT,read_text,pe_header,digest
from verify_world_builder_map_object import check_artifacts
from verify_world_builder_map_bridge import state_regions,wire_visibility,observable_lines


def validate(include_link=True):
    root=PROJECT/'evidence/world_builder/map_bridge'
    b=json.loads((root/'build_result.json').read_text(encoding='utf-8'));c=json.loads((root/'conformance.json').read_text(encoding='utf-8'))
    l=json.loads((root/'link_trial.json').read_text(encoding='utf-8')) if include_link else None
    reference=json.loads(Path(c['reference_build']['path']).read_text(encoding='utf-8'));check_artifacts([b,c,l,reference])
    from world_builder_map_bridge_access import integrated
    sdk_integrated=integrated()
    if b['status']!=('WORLD_BUILDER_MAP_BRIDGE_BUILT' if sdk_integrated else 'WORLD_BUILDER_MAP_BRIDGE_BUILT_ISOLATED_HEADERS') or c['status']!='WORLD_BUILDER_MAP_BRIDGE_COMPONENT_PASS' or c['issues']:raise RuntimeError('Map bridge component did not pass')
    if any(r['sdk_access_declarations_integrated']!=sdk_integrated for r in ([b,c,l] if include_link else [b,c])):raise RuntimeError('Map bridge SDK integration claim differs')
    if sdk_integrated and any(r['sha256']!=r['input']['sha256'] for r in b['generated_headers']):raise RuntimeError('Map bridge headers differ from the compiled SDK')
    if len(c['corpus'])!=130 or {r['version'] for r in c['corpus']}!={6,7,9,10,11,12}:raise RuntimeError('Incomplete map bridge version corpus')
    exact=fixes=recovered=0
    for row in c['corpus']:
        a=row['reference'];d=row['candidate'];cross=row['original_reread']
        if not cross or any(r['exit_code'] for r in (a,d,cross)):raise RuntimeError('Map bridge corpus execution failed')
        ad=Path(a['state']['path']).read_bytes();dd=Path(d['state']['path']).read_bytes();cd=Path(cross['state']['path']).read_bytes()
        if dd!=cd or not cross['exact']:raise RuntimeError('Original map reread disagrees')
        if row['exact_observed_state']!=(ad==dd):raise RuntimeError('Map state equality accounting differs')
        if not row['summary_preview_equal'] or observable_lines(read_text(Path(a['log']['path'])))!=observable_lines(read_text(Path(d['log']['path']))):raise RuntimeError('Map summary/preview differs')
        if row['recovery_bits']:
            recovered+=1
            if f'RECOVERED|{row["recovery_bits"]}' not in read_text(Path(d['log']['path'])):raise RuntimeError('Map recovery must be explicit')
        fix=row['legacy9_correction']
        if fix:
            ar,av,_=state_regions(ad);dr,dv,_=state_regions(dd);changes={k for k in ar.keys()|dr.keys() if ar.get(k)!=dr.get(k)}
            data=Path(row['input']['path']).read_bytes();expected=wire_visibility(data);prefix=fix['original_shifted_prefix_bits'];shift=fix['erroneous_influence_bytes']
            if row['version']!=9 or changes!={'visibility/0','visibility/1'} or dv!=expected or av[:prefix]!=expected[shift*8:shift*8+prefix]:raise RuntimeError('Load9 wire correction differs')
            if (fix['wire_offset'],fix['wire_length'],shift,prefix)!=(42168,693,512,1448):raise RuntimeError('Load9 offset evidence changed')
            if not all(fix[k] for k in ('candidate_matches_wire_bits','only_visibility_differs','original_prefix_matches_shifted_wire','original_instruction_sequence_matches')):raise RuntimeError('Incomplete Load9 defect proof')
            asm=read_text(Path(fix['disassembly']['path']))
            if any(s not in asm for s in ('00408938: C1 E7 08','00408944: E8 F1 A3 00 00','0040895E: 8D 14 2F','00408962: E8 D9 32 00 00')):raise RuntimeError('Original Load9 instructions changed')
            states=[]
            for repeat in c['legacy9_repeats']:
                if repeat['exit_code'] or not repeat['non_visibility_equal']:raise RuntimeError('Load9 repeat failed')
                raw=Path(repeat['state']['path']).read_bytes();rr,_,_=state_regions(raw)
                if any(rr.get(k)!=v for k,v in ar.items() if not k.startswith('visibility/')):raise RuntimeError('Load9 repeat changed another observed field')
                states.append(raw)
            if len(states)!=5 or len(set(states))!=fix['distinct_original_repeated_states']:raise RuntimeError('Load9 repeat accounting differs')
            fixes+=1
        elif ad!=dd:raise RuntimeError('Unexpected map state difference')
        exact+=ad==dd
    if (exact,fixes,recovered)!=(129,1,3):raise RuntimeError('Map bridge corpus accounting differs')
    if len(c['mode_comparisons'])!=12 or {r['mode'] for r in c['mode_comparisons']}!={'full','plain','reverse','missing','reuse','reuse-plain'}:raise RuntimeError('Map remap/reuse coverage incomplete')
    for row in c['mode_comparisons']:
        a=row['reference'];d=row['candidate']
        if a['exit_code'] or d['exit_code'] or not row['exact_observed_state'] or Path(a['state']['path']).read_bytes()!=Path(d['state']['path']).read_bytes():raise RuntimeError('Map mode observation differs')
    h=c['hardening'];text=read_text(Path(h['log']['path']))
    if h['exit_code'] or (h['checks'],h['cpp_allocation_failures'],h['successful_retries'],h['truncation_rejections'])!=(16669,267,3,6530):raise RuntimeError('Map bridge failure coverage differs')
    for marker in ('PASS|16669','FAULTS|267|3|','TRUNCATIONS|6530|','WORKERS|4|128_independent_maps|','LEGACY9|60_wire_visibility_bits|2048_prior_influence_values|','IO|10_read_preview_faults|8_write_faults|7_byte_chunks|invalid_before_open'):
        if marker not in text:raise RuntimeError('Missing bridge hardening evidence: '+marker)
    retained=re.search(r'^ALLOCATIONS\|(\d+)\|(\d+)\|process_lifetime_palette_baseline',text,re.M)
    if not retained or retained[1]!=retained[2]:raise RuntimeError('Map bridge tracked allocation balance differs')
    linkmap=read_text(Path(b['consumers']['map_bridge']['map']['path']))
    if len(c['native_sdk_symbol_proof'])!=7 or any(s not in linkmap or 'ZeroSis_WorldBuilderMapBridge_x64:' not in s for s in c['native_sdk_symbol_proof']):raise RuntimeError('Actual bridge object proof missing')
    if pe_header(Path(reference['executable']['path']))['architecture']!='x86':raise RuntimeError('Wrong map reference architecture')
    for consumer in b['consumers'].values():
        if pe_header(Path(consumer['executable']['path']))['architecture']!='x64':raise RuntimeError('Wrong map candidate architecture')
    for log in b['logs']:
        if re.search(r'\b(?:warning|error)\s+[A-Z]+\d+',read_text(Path(log['path'])),re.I):raise RuntimeError('Map bridge candidate build diagnostic')
    if include_link:
        if l['status']!='WORLD_BUILDER_MAP_BRIDGE_LINK_EXPERIMENT_PASS' or (l['before'],l['after'],len(l['resolved']),l['added'])!=(15,2,13,[]):raise RuntimeError('Map bridge link delta differs')
        expected={'?GetInstance@FIFileSystem@@SAAEAV1@XZ','?GetInstance@FILogFileMgr@@SAAEAV1@XZ'}
        before=set(l['runs'][0]['unresolved']);after=set(l['runs'][1]['unresolved'])
        if after!=expected or before-after!=set(l['resolved']) or after-before or len(before)!=15:raise RuntimeError('Map bridge remaining symbols differ')
        for trial in l['runs']:
            if not trial['exit_code'] or trial['generated_dll'] or not re.search(r'LNK1120:\s*'+str(trial['unresolved_count'])+r'(?!\d)',read_text(Path(trial['log']['path']))):raise RuntimeError('Map bridge link failure record differs')
        if any(l[k] for k in ('official_link_report_replaced','gamecore_linked','gamecore_loaded','game_launched')):raise RuntimeError('Unsupported link trial runtime claim')
    for report,keys in ((b,('gamecore_loaded','game_launched','production_filesystem_implemented')),
        (c,('production_filesystem_implemented','atomic_file_replace_verified','gamecore_linked','gamecore_loaded','game_launched','game_multicore_verified'))):
        if any(report[k] for k in keys):raise RuntimeError('Unsupported full map/engine runtime claim')
    if not b['file_bridge_implemented'] or not c['sdk_map_file_object_integration']:raise RuntimeError('Missing actual map bridge implementation')
    return b,c,l


def provider(build_path=None):
    bp=PROJECT/'evidence/world_builder/map_bridge/build_result.json';cp=bp.with_name('conformance.json')
    if build_path is not None and Path(build_path).resolve()!=bp:raise RuntimeError('Unexpected bridge build report')
    b,c,_=validate(include_link=False)
    if not b['sdk_access_declarations_integrated']:raise RuntimeError('GameCore requires integrated map declarations')
    return b,c,{'name':'WorldBuilderMapBridge','library':b['library'],'build_report':{'path':str(bp),'sha256':digest(bp)},
        'conformance':{'path':str(cp),'sha256':digest(cp)},'runtime':'/MD','scope':'ACTUAL_SDK_MAP_FILES_AND_OBJECTS_NOT_PRODUCTION_FILESYSTEM_OR_GAME_RUNTIME'}


if __name__=='__main__':
    b,c,l=validate();print(json.dumps({'status':'WORLD_BUILDER_MAP_BRIDGE_EVIDENCE_PASS','files':len(c['corpus']),'link_experiment':[l['before'],l['after']]}))
