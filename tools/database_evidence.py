"""Validate database DLL provenance and explicitly limited native component evidence."""
import json
from pathlib import Path
import re
from collect_baseline import PROJECT,digest,pe_header,read_text

def artifacts(value):
    if isinstance(value,dict):
        if 'path' in value and 'sha256' in value:yield value
        for child in value.values():yield from artifacts(child)
    elif isinstance(value,list):
        for child in value:yield from artifacts(child)

def validate(build_path):
    build_path=Path(build_path).resolve();b=json.loads(build_path.read_text(encoding='utf-8'))
    cpath=PROJECT/'evidence/database/conformance.json';c=json.loads(cpath.read_text(encoding='utf-8'))
    ref=json.loads(Path(c['reference_build']['path']).read_text());probes=json.loads(Path(c['reference_probes']['path']).read_text());comparison=json.loads(Path(c['comparison']['path']).read_text())
    assignment=json.loads(Path(c['assignment_conformance']['path']).read_text())
    entries=list(artifacts([b,c,ref,probes,comparison,assignment]));checked={}
    for row in entries:
        path=Path(row['path']);actual=checked.setdefault(str(path),digest(path) if path.is_file() else None)
        if actual!=row['sha256']:raise RuntimeError('Database evidence/input changed: '+str(path))
    if (b['status']!='SDK_DATABASE_X64_COMPONENT_BUILT' or b['runtime']!='/MD'
        or c['status']!='SDK_DATABASE_COMPONENT_CONFORMANCE_PASS' or Path(c['candidate_build']['path']).resolve()!=build_path
        or not comparison['all_regular_exact'] or not comparison['all_candidate_runs_pass']
        or len(c['runs'])!=14 or any(r['returncode'] or not r['checks'] for r in c['runs'])
        or c['exact_trace_pairs']!=5 or c['bulk_rows']!=1024 or c['bulk_columns']!=6
        or len(c['read_only_file_exchange'])!=2 or any(not r['exact_read_trace'] or not r['unchanged_by_readers'] for r in c['read_only_file_exchange'])
        or c['hardening_checks']!=82 or c['concurrency_checks']!=131460
        or c['workers']!=8 or c['independent_connection_lifetimes']!=64 or c['concurrent_inserted_rows']!=32768
        or c['required_import_count']!=41 or len(c['provider_proof'])!=41
        or any((c['game_launched'],c['gamecore_loaded'],c['full_game_save_compatibility_verified'],c['game_multicore_verified']))):
        raise RuntimeError('Database component acceptance data invalid')
    if (pe_header(Path(b['dll']['path']))['architecture']!='x64' or not pe_header(Path(b['dll']['path']))['is_dll']
        or pe_header(Path(ref['executable']['path']))['architecture']!='x86'
        or len(b['objects'])!=3 or any(int.from_bytes(Path(o['path']).read_bytes()[:2],'little')!=0x8664 for o in b['objects'])):
        raise RuntimeError('Database native architectures invalid')
    codes=sorted(re.search(r'warning\s+(C\d+)',line)[1] for line in b['warnings'])
    if codes!=['C4101','C4101','C4996']:raise RuntimeError('Database upstream warning baseline changed')
    maptext=read_text(Path(b['map']['path']));imports=read_text(Path(c['import_members']['path']))
    if any(p['map_line'] not in maptext or not re.search(r'\s'+re.escape(p['required_import'])+r'\s*$',imports,re.M) for p in c['provider_proof']):raise RuntimeError('Database symbol provenance changed')
    expected={'probe','semantics','types','contracts','bulk'}
    if {r['mode'] for r in comparison['runs'] if r.get('exact_match')}!=expected:raise RuntimeError('Database differential modes missing')
    if not next(r for r in comparison['runs'] if r['mode']=='double')['fixed_original_crash']:raise RuntimeError('Double overload fix unproven')
    plan=json.loads(Path(c['sdk_patch_plan']['path']).read_text())
    database_baseline=[p for p in plan['patches'] if not p['id'].startswith(('localization_callers_','world_mod_access_','world_map_access_','world_map_bridge_access_','logging_callers_','bootstrap_callers_','debug_callers_','globals_callers_','construction_callers_','host_callers_','db_postprocess_', 'db_loader_', 'info_cleanup_' ,'db_cache_', 'startup_owners_', 'gc_lifecycle_', 'lua_enum_', 'lua_registration_', 'lua_fractal_', 'fractal_numeric_', 'lua_borrowed_'))]
    if (sum(p['id'].startswith('db_callers_') for p in plan['patches'])!=1 or len(database_baseline)!=480
        or c['export_count']!=113 or assignment['status']!='SDK_DATABASE_ASSIGNMENT_FAULTS_PASS'
        or assignment['checks']!=551 or assignment['failure_cases']!=30 or assignment['success_cases']!=4
        or assignment['cpp_faults']!=14 or assignment['sqlite_faults']!=16 or assignment['recoveries']!=0
        or assignment['production_build']!=c['candidate_build'] or assignment['production_objects']!=b['objects']
        or assignment['returncode'] or assignment['game_launched'] or assignment['gamecore_loaded']):
        raise RuntimeError('Database assignment transaction/fault evidence invalid')
    faultmap=read_text(Path(assignment['map']['path']))
    if len(assignment['allocator_map_proof'])!=1 or assignment['allocator_map_proof'][0] not in faultmap:raise RuntimeError('Fault allocator provenance changed')
    exports=read_text(Path(c['exports']['path']))
    if 'ZeroSisDatabaseFault' in exports or '??4Results@Database@@' not in exports:raise RuntimeError('Production assignment export/test isolation changed')
    return b,c,{'name':'Database','library':b['library'],'dll':b['dll'],
        'build_report':{'path':str(build_path),'sha256':digest(build_path)},'conformance':{'path':str(cpath),'sha256':digest(cpath)},
        'runtime':'/MD','scope':'SQLITE317_CONNECTION_RESULTS_CACHE_COMPONENT_NOT_FULL_DATABASE_HOST_OR_GAME_ACCEPTANCE'}
