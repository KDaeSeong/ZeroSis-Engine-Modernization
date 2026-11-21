"""Read-only SDK mod-data ABI, original differential and fault evidence validation."""
import json
from pathlib import Path
import re
from collect_baseline import PROJECT,digest,read_text,pe_header
from database_evidence import artifacts
from world_builder_mod_access import patches,PREFIX

def validate(build_path=None):
    bp=Path(build_path or PROJECT/'evidence/world_builder/mod_data/build_result.json').resolve();cp=PROJECT/'evidence/world_builder/mod_data/conformance.json'
    b=json.loads(bp.read_text(encoding='utf-8'));c=json.loads(cp.read_text(encoding='utf-8'));r=json.loads(Path(c['reference']['path']).read_text(encoding='utf-8'))
    from foundation_evidence import validate as validate_foundation
    from world_builder_types_evidence import validate as validate_types
    _,_,foundation=validate_foundation(PROJECT/'evidence/foundation/build_result.json');_,_,types=validate_types()
    if b['dependencies']!=[types,foundation]:raise RuntimeError('Mod-data dependencies changed')
    for row in artifacts([b,c,r]):
        p=Path(row['path'])
        if not p.is_file() or digest(p)!=row['sha256']:raise RuntimeError('Mod-data input/evidence changed: '+str(p))
    if (b['status']!='WORLD_BUILDER_MOD_DATA_BUILT' or b['runtime']!='/MD' or not b['sdk_access_declarations_integrated']
            or c['status']!='WORLD_BUILDER_MOD_DATA_COMPONENT_PASS' or not c['sdk_access_declarations_integrated']
            or Path(c['build']['path']).resolve()!=bp or len(b['objects'])!=2
            or len(c['runs'])!=17 or any(x['exit_code'] or not x['checks'] for x in c['runs'])
            or sum(x['checks'] for x in c['runs'])!=6752 or len(c['comparisons'])!=5
            or (c['fault_failures'],c['fault_successes'],c['truncation_rejections'],c['independent_calls'])!=(442,9,1904,256)
            or c['wire_bytes']!=2551 or not c['wire_oracle_matched'] or not c['fresh_storage_initializes_defaults']
            or len(c['cross_reads'])!=2 or any(not x['exact'] for x in c['cross_reads'])
            or len(c['required_symbols'])!=16 or len(c['production_proof'])!=16 or len(c['original_proof'])!=16
            or any((b['gamecore_loaded'],b['game_launched'],c['gamecore_loaded'],c['game_launched'],c['full_world_builder_verified'],c['game_multicore_verified']))):
        raise RuntimeError('Mod-data evidence accounting/scope invalid')
    plan=json.loads(Path(b['sdk_patch_specification']['path']).read_text(encoding='utf-8'))
    if [p for p in plan['patches'] if p['id'].startswith(PREFIX)]!=patches():raise RuntimeError('Access declarations differ from fixed recipe')
    for row in b['generated_headers']:
        if row['sha256']!=row['input']['sha256']:raise RuntimeError('Provider and global SDK headers differ')
    for obj in b['objects']:
        if int.from_bytes(Path(obj['path']).read_bytes()[:2],'little')!=0x8664:raise RuntimeError('Mod-data implementation not AMD64')
    for entry in b['consumers'].values():
        if pe_header(Path(entry['executable']['path']))['architecture']!='x64':raise RuntimeError('Mod-data consumer not AMD64')
    if pe_header(Path(r['executable']['path']))['architecture']!='x86':raise RuntimeError('Mod-data reference not x86')
    if any(re.search(r'\bwarning\s+[A-Z]+\d+|경고\s+[A-Z]+\d+',read_text(Path(x['path']))) for x in b['logs']):raise RuntimeError('Mod-data candidate emitted warnings')
    traces={}
    for row in c['runs']:
        text=read_text(Path(row['log']['path'])).replace('\r\n','\n');passed=re.search(r'^PASS\|(\d+)\s*$',text,re.M)
        if not passed or int(passed[1])!=row['checks']:raise RuntimeError('Mod-data check count differs')
        traces[row['architecture'],row['label']]=text
    for row in c['comparisons']:
        old=traces['x86',row['mode']];new=traces['x64',row['mode']]
        if row['mode']=='fresh':
            if old!='FRESH_RECREATED|99.0\nPASS|1\n' or new!='FRESH_RECREATED|17.0\nPASS|1\n' or not row['intentional_fresh_default_initialization'] or row['exact']:raise RuntimeError('Default initialization change differs')
        elif old!=new or not row['exact'] or row['intentional_fresh_default_initialization'] or Path(row['diff']['path']).stat().st_size:raise RuntimeError('Unexpected mod-data difference')
    hard=traces['hardening','hardening']
    if not all(t in hard for t in ['FAULTS|442|9\n','WORKERS|4|256\n','PASS|6104\n','BOUNDARIES|1904_truncations']):raise RuntimeError('Mod-data hardening absent')
    from verify_world_builder_mod_data import dense_oracle
    expected=dense_oracle()
    for row in c['cross_reads']:
        if traces['x86','read_'+row['producer']]!=traces['x64','read_'+row['producer']] or Path(row['wire']['path']).read_bytes()!=expected:raise RuntimeError('Mod-data wire/cross-read differs')
    candidate=read_text(Path(b['consumers']['mod_data']['map']['path']));original=read_text(Path(r['map']['path']));fault_map=read_text(Path(b['consumers']['mod_data_hardening']['map']['path']))
    if any(p['map_line'] not in candidate or p['symbol'] not in p['map_line'] or 'SdkWorldBuilderModData.obj' not in p['map_line'] for p in c['production_proof']):raise RuntimeError('Production bodies absent')
    if any(p not in original or 'CvWorldBuilderMapWin32:CvWorldBuilderMapModData.obj' not in p for p in c['original_proof']):raise RuntimeError('Original bodies absent')
    if c['allocator_proof']['normal'] not in candidate or c['allocator_proof']['fault_injection'] not in fault_map:raise RuntimeError('Allocator execution domains differ')
    return b,c,{'name':'WorldBuilderModData','library':b['library'],'build_report':{'path':str(bp),'sha256':digest(bp)},
        'conformance':{'path':str(cp),'sha256':digest(cp)},'runtime':'/MD','scope':'MOD_DATA_SCHEMA_VALUES_AND_BOUNDED_WIRE_NOT_FULL_MAP_OR_GAME_RUNTIME'}

if __name__=='__main__':
    _,c,_=validate();print(json.dumps({'status':c['status'],'required_symbols':len(c['required_symbols']),'hardening_checks':6104}))
