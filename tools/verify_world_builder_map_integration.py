"""Verify the map provider against the coherent, non-loaded GameCore build."""
import csv,json
from pathlib import Path
from collect_baseline import PROJECT,digest
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts
from world_builder_map_bridge_evidence import validate,provider
from world_builder_map_object_evidence import validate as validate_object
from world_builder_map_access import patches as object_patches
from world_builder_map_bridge_access import patches as bridge_patches


def main():
    b,c,trial=validate();ob,oc,ot=validate_object();_,_,entry=provider()
    build_path=PROJECT/'evidence/sdk_x64/build_result.json';link_path=PROJECT/'evidence/sdk_x64/link_analysis.json'
    build=json.loads(build_path.read_text(encoding='utf-8'));link=json.loads(link_path.read_text(encoding='utf-8'));check_artifacts([build,link])
    if build['status']!='SDK_X64_ALL_OBJECTS_COMPILED' or len(build['objects'])!=161 or build['unique_error_lines']:raise RuntimeError('Full SDK compile failed')
    if link['build_attempt']!=build['attempt'] or link['build_result_sha256']!=digest(build_path):raise RuntimeError('Link used another GameCore build')
    if not build['numeric_warning_gate']['passed'] or not build['original_files_unchanged'] or not build['generated_port_inputs_unchanged']:raise RuntimeError('SDK source/numeric gate failed')
    for source in (b,ob):
        if not source['sdk_access_declarations_integrated'] or source['sdk_port_manifest']!=build['manifest'] or source['sdk_patch_specification']!=build['patch_specification']:raise RuntimeError('Map SDK inputs differ')
        if any(r['sha256']!=r['input']['sha256'] for r in source['generated_headers']):raise RuntimeError('Isolated map header remains')
    plan=json.loads(Path(build['patch_specification']['path']).read_text(encoding='utf-8'))
    baseline_path=PROJECT/'evidence/sdk_x64/attempts/attempt_019/sdk_x64_patches.json';baseline=json.loads(baseline_path.read_text(encoding='utf-8'))
    prefixes=('world_map_access_','world_map_bridge_access_');added=object_patches()+bridge_patches()
    if len(plan['patches'])!=693 or len(baseline['patches'])!=488 or [p for p in plan['patches'] if not p['id'].startswith(prefixes+('logging_callers_','bootstrap_callers_','debug_callers_','globals_callers_','construction_callers_','host_callers_','db_postprocess_', 'db_loader_', 'info_cleanup_' ,'db_cache_', 'startup_owners_', 'gc_lifecycle_', 'lua_enum_', 'lua_registration_', 'lua_fractal_', 'fractal_numeric_', 'lua_borrowed_'))]!=baseline['patches'] or [p for p in plan['patches'] if p['id'].startswith(prefixes)]!=added:raise RuntimeError('Existing patches or access recipes changed')
    manifest=json.loads(Path(build['manifest']['path']).read_text(encoding='utf-8'))
    for row in manifest:
        if digest(Path(row['source']))!=row['original_sha256'] or digest(Path(row['snapshot']))!=row['original_sha256'] or digest(Path(row['port']))!=row['port_sha256']:raise RuntimeError('SDK file provenance changed')
    from filesystem_evidence import validate as validate_filesystem
    _,_,fs_entry=validate_filesystem()
    if entry not in link['providers'] or fs_entry not in link['providers'] or len(link['providers'])!=16 or link['status']!='X64_LINK_PROBE_SUCCEEDED_UNTESTED' or link['linker_unresolved_symbol_total']!=0 or link['generated_dll'] is None:raise RuntimeError('Official map/filesystem link did not reach the expected service boundary')
    if not link['parsed_count_matches_linker'] or link['unparsed_unresolved_diagnostics']:raise RuntimeError('Incomplete link diagnosis')
    if trial['baseline_excluded_providers']!=['WorldBuilderMapBridge','FileSystem','Logging'] or trial['official_response_unresolved_count']!=0 or (trial['before'],trial['after'])!=(15,2) or (ot['before'],ot['after'])!=(15,5):raise RuntimeError('Same-build A/B link evidence differs')
    unresolved=sorted(r['decorated_or_c_symbol'] for r in csv.DictReader(Path(link['unresolved_candidates']['path']).open(encoding='utf-8-sig')))
    if set(unresolved)!=set(trial['runs'][1]['unresolved'])-{'?GetInstance@FIFileSystem@@SAAEAV1@XZ','?GetInstance@FILogFileMgr@@SAAEAV1@XZ'}:raise RuntimeError('Unexpected filesystem link delta')
    refresh_path=PROJECT/'evidence/world_builder/dependency_refresh/results.json';refresh=json.loads(refresh_path.read_text(encoding='utf-8'));check_artifacts(refresh)
    if len(refresh)!=22 or any(r['exit_code'] for r in refresh):raise RuntimeError('Dependency refresh not complete')
    result={'status':'WORLD_BUILDER_MAP_SDK_INTEGRATION_PASS_NOT_GAME_RUNTIME','verifier':artifact(Path(__file__).resolve()),
        'gamecore_build':artifact(build_path),'gamecore_link':artifact(link_path),'map_build':artifact(PROJECT/'evidence/world_builder/map_bridge/build_result.json'),
        'map_conformance':artifact(PROJECT/'evidence/world_builder/map_bridge/conformance.json'),'map_link_trial':artifact(PROJECT/'evidence/world_builder/map_bridge/link_trial.json'),
        'map_object_conformance':artifact(PROJECT/'evidence/world_builder/map_object/conformance.json'),'dependency_refresh':artifact(refresh_path),
        'baseline_patch_plan':artifact(baseline_path),'patch_recipe':artifact(PROJECT/'tools/define_world_builder_map_patches.py'),
        'patch_count':693,'added_access_declarations':7,'modified_sdk_files':build['modified_files'],'gamecore_objects':161,'providers':16,
        'build_attempt':build['attempt'],'official_unresolved_symbols':0,'unresolved':unresolved,'map_headers_identical_to_compiled_sdk':True,
        'sdk_object_layout_changed':False,'original_game_or_sdk_changed':False,'gamecore_linked':True,'gamecore_loaded':False,'game_launched':False,
        'production_filesystem_implemented':True,'game_multicore_verified':False,'scope':'COHERENT_SDK_COMPILE_PROVIDER_LINK_AND_NATIVE_COMPONENT_TESTS; NOT_GAME_INITIALIZATION_OR_EXECUTION'}
    out=PROJECT/'evidence/world_builder/map_bridge/sdk_integration.json';out.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('status','build_attempt','gamecore_objects','providers','patch_count','modified_sdk_files','official_unresolved_symbols')}))


if __name__=='__main__':main()
