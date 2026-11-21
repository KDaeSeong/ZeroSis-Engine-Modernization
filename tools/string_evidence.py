"""Seal tested string bodies, original comparison and explicit behavioral fixes."""
import json
from pathlib import Path
import re
from collect_baseline import PROJECT,digest,read_text,pe_header
from database_evidence import artifacts

def validate(build_path):
    build_path=Path(build_path).resolve();b=json.loads(build_path.read_text(encoding='utf-8'))
    cpath=PROJECT/'evidence/strings/conformance.json';c=json.loads(cpath.read_text(encoding='utf-8'))
    from stream_evidence import validate as validate_stream
    _,_,streams=validate_stream(PROJECT/'evidence/streams/provider/build_result.json')
    for row in artifacts([b,c]):
        file=Path(row['path'])
        if not file.is_file() or digest(file)!=row['sha256']:raise RuntimeError('String source/build/evidence changed: '+str(file))
    if (b['status']!='SDK_STRINGS_PROVIDER_BUILT' or b['runtime']!='/MD' or b['streams_provider']!=streams
            or b['x64']['libraries'][1]!=streams['library']
            or c['status']!='SDK_STRINGS_COMPONENT_CONFORMANCE_PASS' or Path(c['build']['path']).resolve()!=build_path
            or len(c['runs'])!=21 or any(r['returncode'] or not r['checks'] for r in c['runs'])
            or len(c['comparisons'])!=6 or any(not p['exact'] or Path(p['diff']['path']).stat().st_size for p in c['comparisons'])
            or len(c['cross_reads'])!=2 or any(not p['exact'] for p in c['cross_reads'])
            or c['wire_bytes']!=433098 or c['wire_fields']!=411 or not c['wire_oracle_matched'] or c['endians']!=[0,1,2]
            or c['mutation_operations_per_architecture']!=8192 or not c['corpus_oracle_matched']
            or c['corpus_oracle']!={'A':'06da63f8','W':'ef869fc6'}
            or c['intentional_defect_fixes']!={'interior_copy':True,'short_reserve':True,'fixed_buffer_terminator':True}
            or c['fault_cases']!=20 or c['fault_success_cases']!=15 or c['hardening_checks']!=4428
            or c['boundary_rejections']!=16 or c['stream_rejections']!=15
            or len(c['required_symbols'])!=12 or len(c['provider_proof'])!=12 or len(c['original_archive_map_proof'])<4
            or any((b['game_launched'],b['gamecore_loaded'],c['game_launched'],c['gamecore_loaded'],
                    c['game_multicore_verified'],c['full_game_save_compatibility_verified']))):
        raise RuntimeError('String evidence scope/accounting invalid')
    if len(b['objects'])!=2 or any(int.from_bytes(Path(o['path']).read_bytes()[:2],'little')!=0x8664 for o in b['objects']):
        raise RuntimeError('String implementation architecture invalid')
    if b['x64']['hardening']['production_objects']!=b['objects']:raise RuntimeError('Hardening did not link production objects')
    for arch in ('x86','x64'):
        if pe_header(Path(b[arch]['executable']['path']))['architecture']!=arch:raise RuntimeError('String harness architecture invalid')
        for row in b[arch]['logs']:
            codes=set(re.findall(r'\bwarning\s+(C\d+)',read_text(Path(row['path']))))
            if codes-({'C4819'} if arch=='x86' else set()):raise RuntimeError('String warning baseline changed')
    if pe_header(Path(b['x64']['hardening']['executable']['path']))['architecture']!='x64':raise RuntimeError('String fault executable architecture invalid')
    reference=read_text(Path(b['x86']['map']['path']));candidate=read_text(Path(b['x64']['map']['path']))
    if any(line not in reference for line in c['original_archive_map_proof']):raise RuntimeError('String reference provenance changed')
    if any(p['map_line'] not in candidate or not any(obj in p['map_line'] for obj in ('SdkStrings.obj','SdkStringStream.obj')) for p in c['provider_proof']):
        raise RuntimeError('String implementation provenance changed')
    return b,c,{'name':'Strings','library':b['library'],'build_report':{'path':str(build_path),'sha256':digest(build_path)},
        'conformance':{'path':str(cpath),'sha256':digest(cpath)},'runtime':'/MD',
        'scope':'REQUIRED_FSTRING_UTF_AND_FIELD_STREAMS_NOT_FULL_FSTRING_API_OR_GAME_HOST'}
