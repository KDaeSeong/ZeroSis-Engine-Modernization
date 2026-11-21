"""Seal the actual-SDK AutoArchive provider and its explicitly bounded compatibility."""
import json
from pathlib import Path
from collect_baseline import PROJECT,digest,pe_header,read_text

def validate(build_path):
    from stream_evidence import validate as streams
    from serialization_evidence import validate as serialization
    dependencies=[streams(PROJECT/'evidence/streams/provider/build_result.json')[2],
        serialization(PROJECT/'evidence/serialization/candidate/build_result.json')[2]]
    build_path=Path(build_path).resolve();b=json.loads(build_path.read_text(encoding='utf-8'))
    cpath=PROJECT/'evidence/auto_archive/conformance.json';c=json.loads(cpath.read_text(encoding='utf-8'))
    artifacts=[*b['sources'],*b['sdk_inputs'],b['sdk_manifest'],c['build'],c['fixture'],*c['outputs'],*c['support_inputs'],
        c['sdk_disassembly'],c['dependency_inspector'],*[r['log'] for r in c['runs']],*[r['log'] for r in c['direct_import_audits']],
        c['caller_patch_plan'],*[r['log'] for r in c['caller_runs']],b['x64']['callers']['executable'],b['x64']['callers']['map']]
    for arch in ('x86','x64'):
        a=b[arch];artifacts += [a['executable'],*a['libraries'],a['map'],a['compiler'],*a['objects'],*a['logs'],*a['responses']]
        if pe_header(Path(a['executable']['path']))['architecture']!=arch:raise RuntimeError('AutoArchive architecture mismatch')
    changed=[a['path'] for a in artifacts if not Path(a['path']).is_file() or digest(Path(a['path']))!=a['sha256']]
    if changed:raise RuntimeError('AutoArchive input/build/conformance changed: '+repr(changed))
    if (b['status']!='AUTO_ARCHIVE_PROVIDERS_BUILT' or b['runtime']!='/MD' or b['providers']!=dependencies
        or b['x64']['libraries'][1:]!=[d['library'] for d in dependencies] or b['x64']['warning_codes'] or '/WX' not in b['x64']['flags']
        or b['x86']['warning_codes']!=['C4819'] or c['status']!='SDK_AUTO_ARCHIVE_CONFORMANCE_PASS' or c['failures']
        or Path(c['build']['path']).resolve()!=build_path or c['operations_per_architecture_per_endian']!=4114 or c['endian_modes']!=[0,1,2]
        or c['trace_model_matches']!=6 or c['exchange_wire_matches']!=12 or c['cross_architecture_payload_reads']!=24
        or c['integer_diagnostic_matches']!=131596 or c['diagnostic_cases']!=131634
        or any(d['type'] not in ('FLOAT','DOUBLE','SPECIAL') for d in c['diagnostic_float_differences'])
        or c['rejected_inputs_and_injected_failures']!=156 or c['successful_write_retries']!=120 or c['extreme_finite_formats']!=5
        or len(c['outputs'])!=33 or len(c['runs'])!=37 or any(r['returncode'] or not r['checks'] for r in c['runs'])
        or len(c['direct_import_audits'])!=3 or any(any(t in d.lower() for t in ('cvgame','steam_api','lua51','fireworks')) for a in c['direct_import_audits'] for d in a['direct_dependencies'])
        or len(b['x64']['objects'])!=3 or any(int.from_bytes(Path(o['path']).read_bytes()[:2],'little')!=0x8664 for o in b['x64']['objects'])
        or any((b['game_launched'],c['game_launched'],c['full_save_compatibility_verified'],c['game_multicore_verified']))):
        raise RuntimeError('Invalid AutoArchive component evidence')
    maptext=read_text(Path(b['x86']['map']['path']))
    if len(c['sdk_map_proof'])<34 or any(line not in maptext for line in c['sdk_map_proof']):raise RuntimeError('Original SDK AutoArchive linkage not proven')
    callers=b['x64']['callers'];results=c['caller_results'];life=results['lifecycle'];mutation=results['mutations'];concurrency=results['concurrency']
    if (pe_header(Path(callers['executable']['path']))['architecture']!='x64' or len(c['caller_runs'])!=3 or any(r['returncode'] for r in c['caller_runs'])
        or life['constructor_and_name_faults']!=15 or life['registration_allocation_failures']!=3 or life['lifetime_cleanups']!=21
        or life['bounds_rejections']!=16 or life['protected_owner_pages']!=1 or [life[k] for k in ('base_bytes','scalar_bytes','vector_bytes')]!=[24,40,80]
        or [mutation[k] for k in ('integer_allocation_failures','bool_allocation_failures','custom_allocation_failures','custom_value_failures')]!=[119,96,167,531]
        or mutation['successful_mutations']!=180 or mutation['truncated_vector_reads']!=216 or mutation['growth_pushes']!=4096 or mutation['growth_allocations']!=41
        or concurrency['workers']!=8 or concurrency['owner_lifetimes']!=4096 or concurrency['named_variable_lifetimes']!=8192
        or not concurrency['first_pool_use_concurrent'] or not concurrency['shared_name_pointer_equal']):
        raise RuntimeError('Invalid AutoArchive SDK caller contract evidence')
    maptext=read_text(Path(callers['map']['path']))
    if len(c['caller_allocator_map_proof'])!=1 or c['caller_allocator_map_proof'][0] not in maptext:raise RuntimeError('Caller allocation fault binding changed')
    for endian in c['endian_modes']:
        rows=[r for r in c['outputs'] if Path(r['path']).name in (f'trace_oracle_e{endian}.bin',f'trace_x86_e{endian}.bin',f'trace_x64_e{endian}.bin')]
        if len(rows)!=3 or len({r['sha256'] for r in rows})!=1:raise RuntimeError('AutoArchive trace equality changed')
    return b,c,{'name':'AutoArchive','library':b['x64']['libraries'][0],
        'build_report':{'path':str(build_path),'sha256':digest(build_path)},'conformance':{'path':str(cpath),'sha256':digest(cpath)},
        'runtime':'/MD','scope':'FINAL_RELEASE_ARCHIVE_VARIABLE_AND_DIAGNOSTIC_PROVIDER_NOT_GAME_SYNC_OR_SHARED_ARCHIVE_THREAD_SAFETY'}
