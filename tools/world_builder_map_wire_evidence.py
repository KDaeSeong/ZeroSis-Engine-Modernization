"""Read-only validation of the native map-file component's actual evidence."""
import json,re
from pathlib import Path
from collect_baseline import PROJECT,digest,pe_header,read_text

def hashed_rows(value):
    if isinstance(value,dict):
        if isinstance(value.get('path'),str) and isinstance(value.get('sha256'),str):yield value
        for v in value.values():yield from hashed_rows(v)
    elif isinstance(value,list):
        for v in value:yield from hashed_rows(v)

def validate():
    folder=PROJECT/'evidence/world_builder/map_wire'
    build=json.loads((folder/'build_result.json').read_text(encoding='utf-8'))
    result=json.loads((folder/'conformance.json').read_text(encoding='utf-8'))
    reference=json.loads(Path(result['reference']['path']).read_text(encoding='utf-8'))
    for row in hashed_rows([build,result,reference]):
        p=Path(row['path'])
        if not p.is_file() or digest(p)!=row['sha256']:raise RuntimeError('Stale map-file evidence: '+str(p))
    if build['status']!='WORLD_BUILDER_MAP_WIRE_BUILT' or result['status']!='WORLD_BUILDER_MAP_WIRE_COMPONENT_PASS' or result['issues']:
        raise RuntimeError('Map-file component gate not passed')
    rows=result['corpus']
    if len(rows)!=130 or result['installed_inputs']!=128 or {r['version'] for r in rows}!={6,7,9,10,11,12}:raise RuntimeError('Incomplete observed map corpus')
    if any(r['exit_code'] or not r['model_matched'] or not r['wire_model_matched'] or r['model_sections_compared']!=31
        or r['original_read']['exit_code'] or not r['original_read']['public_summary_matches'] for r in rows):raise RuntimeError('Map file native/original/model disagreement')
    recovered=[r for r in rows if r['recovery_bits']]
    if len(recovered)!=3 or sum(r['exact_roundtrip'] for r in rows)!=127:raise RuntimeError('Unexpected recovery scope')
    expected={'MongolScenario.Civ5Map':(4,7),'1066Scenario.Civ5Map':(2,4),'CivilWarEasternTheater.Civ5Map':(1,32)}
    for row in recovered:
        if expected.get(Path(row['input']['path']).name)!=(row['recovery_bits'],row['changed_bytes']):raise RuntimeError('Recovery delta changed')
        original=row['original_read']
        if not original['semantic_state_preserved'] or Path(original['semantic_source']['path']).read_bytes()!=Path(original['semantic_output']['path']).read_bytes():raise RuntimeError('Referenced SDK state changed during recovery')
        if 'REJECT|Invalid or cyclic map free list' not in read_text(Path(original['strict_rejection']['path'])):raise RuntimeError('Strict mode did not reject invalid list')
    hard=result['hardening'];text=read_text(Path(hard['log']['path']))
    if hard['exit_code'] or hard['checks']<13300 or hard['fault_failures']<130 or hard['fault_successes']!=3 or hard['truncation_rejections']!=6530:raise RuntimeError('Missing map-file failure coverage')
    if not re.search(r'^PASS\|'+str(hard['checks'])+r'\s*$',text,re.M) or 'WORKERS|4|128' not in text:raise RuntimeError('Missing native hardening records')
    if not result['mutation']['original_read_matches'] or len(result['production_proof'])!=3:raise RuntimeError('Missing writer mutation or production proof')
    linkmap=Path(build['consumers']['world_builder_map_wire']['map']['path']).read_text(errors='replace')
    if any(line not in linkmap or 'ZeroSis_WorldBuilderMapWire_x64:WorldBuilderMapWire.obj' not in line for line in result['production_proof']):raise RuntimeError('Wrong production object')
    for c in build['consumers'].values():
        if pe_header(Path(c['executable']['path']))['architecture']!='x64':raise RuntimeError('Wrong candidate architecture')
    if any(result[k] for k in ('sdk_map_object_integration','gamecore_loaded','game_launched','game_multicore_verified')):raise RuntimeError('Unsupported game-runtime claim')
    return build,result

if __name__=='__main__':
    build,result=validate();print(json.dumps({'status':'WORLD_BUILDER_MAP_WIRE_EVIDENCE_PASS','files':len(result['corpus']),'installed_maps':128,'recovered_maps':3}))
