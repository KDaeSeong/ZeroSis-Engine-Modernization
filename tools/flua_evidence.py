"""Validate the Lua bridge's real implementation and bounded native evidence."""
import json
from pathlib import Path
import re
from collect_baseline import PROJECT, digest, read_text, pe_header
from database_evidence import artifacts

def validate(build_path):
    build_path=Path(build_path).resolve();b=json.loads(build_path.read_text(encoding='utf-8'))
    cpath=PROJECT/'evidence/flua/conformance.json';c=json.loads(cpath.read_text(encoding='utf-8'))
    from foundation_evidence import validate as validate_foundation
    _,_,foundation=validate_foundation(PROJECT/'evidence/foundation/build_result.json')
    for row in artifacts([b,c]):
        file=Path(row['path'])
        if not file.is_file() or digest(file)!=row['sha256']:raise RuntimeError('FLua source/build/evidence changed: '+str(file))
    if (b['status']!='SDK_FLUA_VALUE_BRIDGE_BUILT' or b['runtime']!='/MD' or b['foundation_provider']!=foundation
            or c['status']!='SDK_FLUA_VALUE_BRIDGE_CONFORMANCE_PASS' or Path(c['build']['path']).resolve()!=build_path
            or len(c['runs'])!=13 or any(r['returncode'] or not r['checks'] for r in c['runs'])
            or len(c['comparisons'])!=5 or any(not p['exact'] or Path(p['diff']['path']).stat().st_size for p in c['comparisons'])
            or not c['self_assignment_fixed'] or len(c['required_symbols'])!=8 or len(c['provider_proof'])!=8
            or c['value_inputs']!=13 or c['table_writes_per_architecture']!=4096
            or c['locked_callback_workers']!=[1,2,4,8] or c['locked_callbacks_per_architecture']!=7680
            or c['rejected_inputs']!=8 or c['long_error_bytes']!=16384
            or not c['cpp_callback_unwind_verified'] or not c['error_handler_throw_cleanup_verified']
            or not c['protected_call_allocation_failure_recovery_verified']
            or any((b['game_launched'],b['gamecore_loaded'],c['game_launched'],c['gamecore_loaded'],c['game_multicore_verified']))):
        raise RuntimeError('FLua native scope/accounting invalid')
    if len(b['objects'])!=1 or int.from_bytes(Path(b['objects'][0]['path']).read_bytes()[:2],'little')!=0x8664:
        raise RuntimeError('FLua implementation object architecture invalid')
    for arch in ('x86','x64'):
        if pe_header(Path(b[arch]['executable']['path']))['architecture']!=arch:raise RuntimeError('FLua harness architecture invalid')
        for row in b[arch]['logs']:
            codes=set(re.findall(r'\bwarning\s+(C\d+)',read_text(Path(row['path']))))
            if codes-({'C4819'} if arch=='x86' else set()):raise RuntimeError('FLua warning baseline changed')
    if b['x64']['libraries'][2]!=foundation['library']:raise RuntimeError('FLua lock provider changed')
    reference_map=read_text(Path(b['x86']['map']['path']));candidate_map=read_text(Path(b['x64']['map']['path']))
    if any(line not in reference_map for line in c['original_archive_map_proof']):raise RuntimeError('FLua original code provenance changed')
    if any(p['map_line'] not in candidate_map or 'SdkFLuaValues.obj' not in p['map_line'] for p in c['provider_proof']):raise RuntimeError('FLua implementation provenance changed')
    return b,c,{'name':'FLua','library':b['library'],'build_report':{'path':str(build_path),'sha256':digest(build_path)},
        'conformance':{'path':str(cpath),'sha256':digest(cpath)},'runtime':'/MD',
        'scope':'VALUE_TABLE_FIELDS_AND_LOCKED_PROTECTED_C_CALLS_NOT_FULL_FLUA_OR_GAME_SCRIPT_HOST'}
