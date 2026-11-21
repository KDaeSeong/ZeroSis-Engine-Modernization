"""Read-only validation of actual WorldBuilder type/group implementation evidence."""
import json
from pathlib import Path
import re
from collect_baseline import PROJECT,digest,read_text,pe_header
from database_evidence import artifacts

def validate(build_path=None):
    bp=Path(build_path or PROJECT/'evidence/world_builder/types/build_result.json').resolve();cp=PROJECT/'evidence/world_builder/types/conformance.json'
    b=json.loads(bp.read_text(encoding='utf-8'));c=json.loads(cp.read_text(encoding='utf-8'));rp=Path(c['reference']['path']);r=json.loads(rp.read_text(encoding='utf-8'))
    for row in artifacts([b,c,r]):
        p=Path(row['path'])
        if not p.is_file() or digest(p)!=row['sha256']:raise RuntimeError('WorldBuilder evidence/input changed: '+str(p))
    if (b['status']!='WORLD_BUILDER_TYPES_BUILT' or b['runtime']!='/MD' or Path(c['build']['path']).resolve()!=bp
            or c['status']!='WORLD_BUILDER_TYPES_COMPONENT_PASS' or r['status']!='WORLD_BUILDER_REFERENCE_OBSERVED'
            or len(b['objects'])!=2 or set(b['consumers'])!={'trace','hardening'}
            or len(c['runs'])!=25 or any(x['exit_code'] or not x['checks'] for x in c['runs'])
            or len(c['comparisons'])!=9 or len(c['cross_reads'])!=2 or not all(x['exact'] for x in c['cross_reads'])
            or c['wire_bytes']!=112 or not c['wire_oracle_matched'] or c['operations_per_architecture']!=2048
            or c['operation_oracle']!='18a4fd15' or not c['operation_oracle_matched']
            or (c['fault_failures'],c['fault_successes'],c['independent_calls'])!=(17,6,4096)
            or sum(x['checks'] for x in c['runs'])!=5432
            or any((b['gamecore_loaded'],b['game_launched'],c['gamecore_loaded'],c['game_launched'],c['game_multicore_verified'],c['full_world_builder_verified']))):
        raise RuntimeError('WorldBuilder evidence accounting/scope invalid')
    for obj in b['objects']:
        if int.from_bytes(Path(obj['path']).read_bytes()[:2],'little')!=0x8664:raise RuntimeError('WorldBuilder object not AMD64')
    for entry in b['consumers'].values():
        if pe_header(Path(entry['executable']['path']))['architecture']!='x64':raise RuntimeError('WorldBuilder consumer not x64')
    if pe_header(Path(r['executable']['path']))['architecture']!='x86':raise RuntimeError('Reference not x86')
    for log in b['logs']:
        if re.search(r'\bwarning\s+[A-Z]+\d+|경고\s+[A-Z]+\d+',read_text(Path(log['path']))):raise RuntimeError('Candidate emitted warnings')
    traces={}
    for row in c['runs']:
        trace=read_text(Path(row['log']['path'])).replace('\r\n','\n');match=re.search(r'^PASS\|(\d+)\s*$',trace,re.M)
        if not match or int(match[1])!=row['checks']:raise RuntimeError('Native check count differs')
        traces[row['architecture'],row['label']]=trace
    for row in c['comparisons']:
        old=traces['x86',row['mode']];new=traces['x64',row['mode']]
        if row['mode']=='self':
            if (row['exact'] or not row['intentional_self_assignment_fix'] or 'BYTES|self_after|0|\n' not in old
                    or new!=old.replace('BYTES|self_after|0|\n','BYTES|self_after|10|036f6e65000374776f00\n')):raise RuntimeError('Self assignment fix not isolated')
        elif old!=new or not row['exact'] or row['intentional_self_assignment_fix'] or Path(row['diff']['path']).stat().st_size:raise RuntimeError('Unexpected type/group difference')
    hard=traces['x64','hardening']
    if 'FAULTS|17|6\n' not in hard or 'WORKERS|4|4096\n' not in hard or 'PASS|626\n' not in hard:raise RuntimeError('Hardening evidence absent')
    for row in c['cross_reads']:
        if traces['x86','read_'+row['producer']]!=traces['x64','read_'+row['producer']]:raise RuntimeError('Cross read differs')
        if Path(row['wire']['path']).stat().st_size!=112:raise RuntimeError('Wire length differs')
    if Path(c['cross_reads'][0]['wire']['path']).read_bytes()!=Path(c['cross_reads'][1]['wire']['path']).read_bytes():raise RuntimeError('Serialized bytes differ')
    for kind,map_artifact in [('original',r['map']),('candidate',b['consumers']['trace']['map'])]:
        source=read_text(Path(map_artifact['path']));proof=c['production_proof'][kind]
        if len(proof)!=3 or any(line not in source for line in proof):raise RuntimeError('Implementation map provenance absent')
    return b,c,{'name':'WorldBuilderTypes','library':b['library'],'build_report':{'path':str(bp),'sha256':digest(bp)},
        'conformance':{'path':str(cp),'sha256':digest(cp)},'runtime':'/MD','scope':'TYPE_MAP_GROUP_COMPONENTS_NOT_COMPLETE_MAP_MODDATA_OR_GAME_RUNTIME'}

if __name__=='__main__':
    _,c,_=validate();print(json.dumps({'status':c['status'],'runs':len(c['runs']),'hardening_assertions':626}))
