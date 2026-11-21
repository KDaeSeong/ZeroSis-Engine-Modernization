"""Tie DB cache failure evidence to exact compiled SDK bodies and stated test boundaries."""
import json
from pathlib import Path
from collect_baseline import PROJECT, digest, read_text
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts
from database_evidence import validate as validate_database
from define_database_cache_patches import BASE, PREFIX, GLOBALS, UTILITY, patches, database_phase
from build_database_cache import SIGNATURES, fixtures
from build_bootstrap_component import body
from verify_database_cache import MARKERS, COMMON


def validate():
    root=PROJECT/'evidence/database_cache'
    build,result,declared=(json.loads((root/name).read_text(encoding='utf-8')) for name in ('build_result.json','conformance.json','caller_patch_plan.json'))
    check_artifacts([build,result,declared])
    _,_,provider=validate_database(PROJECT/'evidence/database/candidate/build_result.json')
    if build['database_provider']!=provider or result['status']!='DATABASE_CACHE_NATIVE_PASS' or result['issues']:
        raise RuntimeError('Database cache evidence/provider mismatch')
    if [r['name'] for r in result['runs']]!=['original','candidate'] or [r['checks'] for r in result['runs']]!=[10893,12529]:
        raise RuntimeError('Database cache execution accounting differs')
    for row in result['runs']:
        if row['exit_code'] or any(m not in read_text(Path(row['log']['path'])) for m in (*COMMON,*MARKERS[row['name']])):
            raise RuntimeError('Database cache required native observation missing')
    expected=fixtures()
    for row in build['fixtures']:
        path=Path(row['path'])
        if path.read_text(encoding='utf-8')!=expected[path.name]: raise RuntimeError('Database cache fixture changed')
    candidate=expected['database_cache_fixture.h'].split('#else\n',1)[1]
    for relative,signatures in SIGNATURES.items():
        text=(PROJECT/'Source/SDK_BNW_x64'/relative).read_bytes().decode('latin1')
        for signature in signatures:
            if body(text,signature).replace('\r\n','\n')!=body(candidate,signature.replace('\r\n','\n')):
                raise RuntimeError('Compiled database cache function differs: '+signature)
    text=(PROJECT/'Source/SDK_BNW_x64'/UTILITY).read_bytes().decode('latin1')
    if body(text,'static bool ZeroSisCacheFlavorTypes()').replace('\r\n','\n')!=body(candidate,'static bool ZeroSisCacheFlavorTypes()'):
        raise RuntimeError('Compiled flavor ownership helper differs')
    text=(PROJECT/'Source/SDK_BNW_x64'/GLOBALS).read_bytes().decode('latin1')
    if database_phase(text).replace('\r\n','\n') not in candidate:
        raise RuntimeError('Compiled contiguous GC database startup phase differs')
    for relative,signature in (('CvGameCoreDLLUtil/include/CvDllInterfaces.h','class ICvUnknown\r\n{'),
                               ('CvGameCoreDLLUtil/include/ICvDLLDatabaseUtility.h','class ICvDLLDatabaseUtility1')):
        text=(PROJECT/'Source/SDK_BNW_x64'/relative).read_bytes().decode('latin1')
        if body(text,signature).replace('\r\n','\n') not in expected['database_cache_abi.h']:
            raise RuntimeError('SDK interface release boundary differs')
    pp=PROJECT/'Source/Porting/sdk_x64_patches.json'
    plan,base=(json.loads(p.read_text(encoding='utf-8')) for p in (pp,BASE));added=patches()
    if len(plan['patches'])!=693 or len(added)!=7 or declared['patches']!=added:
        raise RuntimeError('Database cache patch recipe differs')
    if [p for p in plan['patches'] if not p['id'].startswith((PREFIX, 'startup_owners_', 'gc_lifecycle_', 'lua_enum_', 'lua_registration_', 'lua_fractal_', 'fractal_numeric_', 'lua_borrowed_'))]!=base['patches'] or [p for p in plan['patches'] if p['id'].startswith(PREFIX)]!=added:
        raise RuntimeError('Database cache changed retained SDK patches')
    sdk=json.loads((PROJECT/'evidence/sdk_x64/build_result.json').read_text(encoding='utf-8'))
    if sdk['status']!='SDK_X64_ALL_OBJECTS_COMPILED' or len(sdk['objects'])!=161 or sdk['patch_specification']['sha256']!=digest(pp):
        raise RuntimeError('Database cache not compiled in all GameCore objects')
    if artifact(PROJECT/'Source/Porting/ZeroSisHostBinding.h') not in sdk['support_inputs']:
        raise RuntimeError('Compiled interface ownership helper missing')
    corpus={c['database']:c for c in result['corpus_comparisons']}
    if set(corpus)!={'Civ5CoreDatabase.db','Civ5DebugDatabase.db'} or not corpus['Civ5DebugDatabase.db']['equal_collection_ids_types_flavors_lookup_enum_values']:
        raise RuntimeError('Valid BNW rule corpus changed')
    if not corpus['Civ5CoreDatabase.db']['candidate_rejects_incomplete_core_schema'] or corpus['Civ5CoreDatabase.db']['missing_required_type_tables']!=['GreatWorkArtifactClasses','GreatWorkSlots']:
        raise RuntimeError('Missing BNW table refusal was not observed')
    if len(result['corpus_runs'])!=4 or [r['exit_code'] for r in result['corpus_runs']]!=[0,3,0,0]:
        raise RuntimeError('Cached corpus execution status differs')
    if 'C5205' not in read_text(Path(build['original_nonvirtual_delete_diagnostic']['path'])) or build['original_only_warning_exemption']!='C5205':
        raise RuntimeError('Original nonvirtual ownership diagnostic missing')
    if '/wd5205' in read_text(Path(build['builds']['candidate']['response']['path'])):
        raise RuntimeError('Candidate inherited original ownership warning exemption')
    if not all(result[k] for k in ('candidate_error_propagation_and_retry_verified','candidate_flavor_failure_preserves_previous_array',
            'candidate_database_phase_stops_before_players_teams','candidate_local_reference_destroy_dispatch_verified','concrete_info_and_game_stages_instrumented')) or any(result[k] for k in
            ('entire_cache_atomic_rollback_verified','whole_gc_lifecycle_verified','original_windows_game_binary_executed','gamecore_loaded','game_launched','game_multicore_verified')):
        raise RuntimeError('Database cache claim exceeds isolated component scope')
    entry={'name':'DatabaseCacheCallers','build':artifact(root/'build_result.json'),'conformance':artifact(root/'conformance.json'),
           'caller_plan':artifact(root/'caller_patch_plan.json'),'validator':artifact(Path(__file__).resolve()),
           'scope':'EXACT_CACHE_TYPES_PREFETCH_AND_GC_DATABASE_PHASE_REAL_SQLITE_INSTRUMENTED_GAME_NOT_WHOLE_GC_ROLLBACK'}
    return build,result,entry


if __name__=='__main__':
    _,result,_=validate()
    print(json.dumps({'status':'DATABASE_CACHE_EVIDENCE_PASS','checks':sum(r['checks'] for r in result['runs']),'compiled_gamecore_objects':161}))
