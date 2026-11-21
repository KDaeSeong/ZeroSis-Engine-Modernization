"""Require current SDK/reference/native evidence before linking or staging serialization."""
import json
from pathlib import Path
from collect_baseline import PROJECT,digest,pe_header,read_text
from stream_evidence import validate as validate_streams

def validate(build_path):
    build_path=Path(build_path).resolve()
    b=json.loads(build_path.read_text(encoding='utf-8'))
    cpath=PROJECT/'evidence/serialization/candidate/conformance.json'
    c=json.loads(cpath.read_text(encoding='utf-8'))
    streams,_,_=validate_streams(PROJECT/'evidence/streams/provider/build_result.json')
    required=[*b['sources'],*b['sdk_inputs'],*b['generated_extracts'],b['sdk_manifest'],b['stream_conformance'],
        c['build'],c['input'],c['notification_fixture'],*c['outputs'],*c['support_inputs'],
        c['patch_specification'],c['stream_conformance'],*[r['log'] for r in c['runs']]]
    for arch in ('x86','x64'):
        a=b[arch]
        required += [a['executable'],*a['libraries'],a['map'],a['compiler'],*a['objects'],*a['logs']]
        if pe_header(Path(a['executable']['path']))['architecture']!=arch:
            raise RuntimeError('Serialization harness architecture mismatch')
    if any(not Path(row['path']).is_file() or digest(Path(row['path']))!=row['sha256'] for row in required):
        raise RuntimeError('Serialization source/build/reference/conformance artifact changed')
    if (b['status']!='SERIALIZATION_PROVIDERS_BUILT' or b['runtime']!='/MD'
        or c['status']!='SDK_SERIALIZATION_CONFORMANCE_PASS' or c['failures']
        or Path(c['build']['path']).resolve()!=build_path
        or c['enum_types']!=b['enum_types'] or len(b['enum_types'])!=81
        or c['enum_wire_bytes']!={t:1 if t=='GameTypes' else 4 for t in b['enum_types']}
        or c['values_per_enum']!=1685 or c['enum_write_read_pairs']!=409455
        or c['enum_bytes_per_architecture']!=1622655 or c['endian_modes']!=3
        or c['ordered_container_wire_matches']!=39 or c['cross_architecture_container_reads']!=90
        or c['existing_value_merge_append_checks']!=48 or c['native_count_overflow_rejections']!=2
        or len(c['runs'])!=19 or any(r['returncode'] for r in c['runs'])
        or not c['unordered_logical_values_match']
        or c['unordered_wire_order_differences']!=[{'container':n,'endian':e} for e in (0,1,2) for n in ('hash_map','unordered_set')]
        or b['x64']['libraries'][1]!=streams['library']
        or len(b['x64']['objects'])!=2
        or any(int.from_bytes(Path(r['path']).read_bytes()[:2],'little')!=0x8664 for r in b['x64']['objects'])
        or any((b['game_launched'],c['game_launched'],c['full_save_compatibility_verified'],c['game_determinism_verified']))):
        raise RuntimeError('Invalid serialization component contract evidence')
    maptext=read_text(Path(b['x86']['map']['path']))
    if (len(c['sdk_enum_map_proof'])!=162 or len(c['sdk_string_map_proof'])!=2
        or any(line not in maptext for line in c['sdk_enum_map_proof']+c['sdk_string_map_proof'])):
        raise RuntimeError('Actual SDK serialization linkage not proven')
    return b,c,{'name':'Serialization','library':b['x64']['libraries'][0],
        'build_report':{'path':str(build_path),'sha256':digest(build_path)},
        'conformance':{'path':str(cpath),'sha256':digest(cpath)},'runtime':'/MD',
        'scope':'ENUM_STRING_AND_CONTAINER_COMPONENTS_WITH_UNORDERED_ORDER_DIFFERENCES_NOT_GAME_SAVE_ACCEPTANCE'}
