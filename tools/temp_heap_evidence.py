"""Require current real-SDK, native-concurrency and ownership evidence for TempHeap."""
import json
from pathlib import Path
from collect_baseline import PROJECT,digest,pe_header,read_text

def validate(build_path):
    from foundation_evidence import validate as foundation_validate
    _,_,foundation=foundation_validate(PROJECT/'evidence/foundation/build_result.json')
    build_path=Path(build_path).resolve();b=json.loads(build_path.read_text(encoding='utf-8'))
    cpath=PROJECT/'evidence/temp_heap/conformance.json';c=json.loads(cpath.read_text(encoding='utf-8'))
    artifacts=[*b['sources'],*b['sdk_inputs'],b['sdk_manifest'],c['build'],c['fixture'],*c['outputs'],*c['support_inputs'],
        c['sdk_disassembly'],c['dependency_inspector'],*[r['log'] for r in c['runs']],*[a['log'] for a in c['direct_import_audits']]]
    for arch in ('x86','x64'):
        a=b[arch];artifacts += [a['executable'],*a['libraries'],a['map'],a['compiler'],*a['objects'],*a['logs'],*a['responses']]
        if pe_header(Path(a['executable']['path']))['architecture']!=arch:raise RuntimeError('TempHeap architecture mismatch')
    missing=b['x64']['missing_host'];artifacts += [missing['executable'],missing['map']]
    if pe_header(Path(missing['executable']['path']))['architecture']!='x64':raise RuntimeError('TempHeap missing-host architecture mismatch')
    changed=[a['path'] for a in artifacts if not Path(a['path']).is_file() or digest(Path(a['path']))!=a['sha256']]
    if changed:raise RuntimeError('TempHeap source/build/reference/conformance artifact changed: '+repr(changed))
    expected_model={'operations':13520,'arena_lifetimes':22,'allocations':3928,'capacity_rejections':5620,'releases':3928,'zero_byte_leases':1110}
    if (b['status']!='TEMP_HEAP_PROVIDERS_BUILT' or b['runtime']!='/MD' or b['foundation']!=foundation
        or b['x64']['libraries'][1]!=foundation['library'] or b['x64']['warning_codes'] or '/WX' not in b['x64']['flags']
        or b['x86']['warning_codes']!=['C4819'] or c['status']!='SDK_TEMP_HEAP_CONFORMANCE_PASS' or c['failures']
        or Path(c['build']['path']).resolve()!=build_path or c['sequential_model']!=expected_model
        or c['trace_bytes_per_architecture']!=13520*40 or not c['matching_reference_probe']
        or len(c['outputs'])!=3 or len({r['sha256'] for r in c['outputs']})!=1
        or c['workers']!=[1,2,4,8] or c['batches_per_worker_configuration']!=128
        or c['concurrent_successful_allocations']!=122880 or c['concurrent_forced_capacity_rejections']!=15360
        or c['pressure_workers']!=8 or c['pressure_attempts']!=400000
        or min(c['pressure_results'].values())<=0 or sum(c['pressure_results'].values())!=400000
        or c['rounding_overflow_rejections']!=15 or c['maximum_simultaneous_leases']!=65535 or c['lifecycle_or_release_rejections']!=6
        or c['native_address_space_reserved']!=4294967296 or c['committed_page_bytes']!=8192
        or c['tested_unsigned_offsets']!=[2147483648,4294967280] or c['host_first_use_workers']!=8 or c['host_binding_calls']!=8192
        or c['missing_host_rejections']!=2 or c['null_host_rejections_and_recovery']!=2
        or len(c['runs'])!=10 or any(r['returncode'] for r in c['runs']) or len(c['direct_import_audits'])!=3
        or any(any(s in dll.lower() for s in ('cvgame','lua51','steam_api','fireworks')) for a in c['direct_import_audits'] for dll in a['direct_dependencies'])
        or len(b['x64']['objects'])!=1 or any(int.from_bytes(Path(o['path']).read_bytes()[:2],'little')!=0x8664 for o in b['x64']['objects'])
        or any((b['game_launched'],c['game_launched'],c['game_multicore_verified'],c['game_performance_verified']))):
        raise RuntimeError('Invalid TempHeap contract evidence')
    maptext=read_text(Path(b['x86']['map']['path']))
    if len(c['sdk_map_proof'])!=8 or any(line not in maptext for line in c['sdk_map_proof']):raise RuntimeError('Original SDK arena linkage not proven')
    return b,c,{'name':'TempHeap','library':b['x64']['libraries'][0],
        'build_report':{'path':str(build_path),'sha256':digest(build_path)},
        'conformance':{'path':str(cpath),'sha256':digest(cpath)},'runtime':'/MD',
        'scope':'CHECKED_ATOMIC_ARENA_AND_EXECUTABLE_HOST_BINDING_NOT_GAME_HOST_OR_GAMEPLAY'}
