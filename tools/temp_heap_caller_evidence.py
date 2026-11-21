"""Validate actual wrapper/caller conformance separately from whole-game acceptance."""
import json
from pathlib import Path
from collect_baseline import PROJECT,digest,pe_header,read_text

def validate():
    from temp_heap_evidence import validate as temp_validate
    from stream_evidence import validate as stream_validate
    from foundation_evidence import validate as foundation_validate
    expected=[]
    for validator,path in ((temp_validate,'evidence/temp_heap/build_result.json'),
        (stream_validate,'evidence/streams/provider/build_result.json'),(foundation_validate,'evidence/foundation/build_result.json')):
        _,_,entry=validator(PROJECT/path);expected.append(entry)
    path=PROJECT/'evidence/temp_heap_callers/conformance.json';c=json.loads(path.read_text(encoding='utf-8'))
    artifacts=c['input_artifacts']+c['outputs']+[c['compiler'],c['dependency_inspector']]
    for b in c['builds']:
        artifacts += [b[k] for k in ('executable','map','log','response')]
        if pe_header(Path(b['executable']['path']))['architecture']!='x64' or b['compiler_warnings'] or '/WX' not in b['flags']:
            raise RuntimeError('Caller executable architecture/warning gate failed')
        maptext=read_text(Path(b['map']['path']))
        if len(b['allocation_provider_map_proof'])!=1 or b['allocation_provider_map_proof'][0] not in maptext:
            raise RuntimeError('Actual production/fault allocator linkage not proven')
    artifacts += [r['log'] for r in c['runs']]+[a['log'] for a in c['direct_import_audits']]
    changed=[r['path'] for r in artifacts if not Path(r['path']).is_file() or digest(Path(r['path']))!=r['sha256']]
    if changed:raise RuntimeError('Caller evidence changed: '+repr(changed))
    if (c['status']!='SDK_TEMP_HEAP_CALLERS_PASS' or c['failures'] or c['providers']!=expected
        or [b['variant'] for b in c['builds']]!=['production','allocation_faults'] or len(c['runs'])!=2
        or any(r['returncode'] for r in c['runs']) or len(c['outputs'])!=3 or len({r['sha256'] for r in c['outputs']})!=1
        or c['database_cases_per_executable']!=33 or c['endian_modes']!=3 or c['wire_bytes_per_executable']!=272547
        or c['io_failure_cases_per_executable']!=26 or c['injected_allocation_failures']!=5
        or c['tested_native_request_bytes']!=8589934590 or c['checked_bnwsdk_call_sites']!=2 or c['save_field_count_bytes']!=4
        or c['native_checks']!={'production':1009,'allocation_faults':1061} or len(c['direct_import_audits'])!=2
        or any(any(n in dll.lower() for n in ('cvgame','lua51','steam_api','fireworks')) for a in c['direct_import_audits'] for dll in a['direct_dependencies'])
        or not all(c[k] for k in ('existing_cache_preserved_on_tested_precommit_failure','temporary_files_cleaned','handles_and_temporary_buffers_released'))
        or any(c[k] for k in ('game_launched','full_save_compatibility_verified','game_multicore_verified'))):
        raise RuntimeError('Caller conformance scope/accounting mismatch')
    compiled=json.loads((PROJECT/'evidence/sdk_x64/build_result.json').read_text(encoding='utf-8'))
    helper=PROJECT/'Source/Porting/CvEmbeddedDatabaseIO.h'
    if (compiled['status']!='SDK_X64_ALL_OBJECTS_COMPILED' or len(compiled['objects'])!=161
        or {'path':str(helper),'sha256':digest(helper)} not in compiled['support_inputs']):
        raise RuntimeError('Current database helper has not been compiled into the BNW source port')
    return c,{'path':str(path),'sha256':digest(path)}
