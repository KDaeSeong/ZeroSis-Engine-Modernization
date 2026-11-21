"""Validate native host evidence against consumed headers, the SDK and current bundle."""
import json,re
from pathlib import Path
from collect_baseline import PROJECT,read_text
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts
from generate_host_interfaces import inventory,generated
from build_bootstrap_component import body
from verify_native_host import MARKER


def validate():
    root=PROJECT/'evidence/host'
    build,result,bundle,interfaces=[json.loads((root/n).read_text(encoding='utf-8')) for n in
                                   ('build_result.json','conformance.json','bundle.json','interfaces.json')]
    check_artifacts([build,result,bundle,interfaces])
    if result['status']!='NATIVE_HOST_COMPONENT_AND_DATA_PASS' or result['native_checks']!=20948 or result['lifecycle_native_checks']!=4056 or result['map_audio_native_checks']!=12615 or result['script_native_checks']!=3201 or result['script_asset_native_checks']!=1076 or len(result['runs'])!=24:
        raise RuntimeError('Native host conformance/accounting differs')
    if MARKER not in read_text(Path(result['runs'][0]['log']['path'])):raise RuntimeError('Host lifecycle test marker missing')
    for run in result['runs']:
        output=read_text(Path(run['log']['path']))
        if run['required_marker'] not in output or '--initialize' in run['arguments']:raise RuntimeError('Unexpected host execution scope')
    if not all(result[k] for k in ('bundle_inputs_unchanged','read_only_modes_created_no_sessions','real_database_localization_executed','gamecore_lifecycle_instrumented')):
        raise RuntimeError('Missing host/data boundary evidence')
    if any(result[k] for k in ('gamecore_loaded','game_launched','game_multicore_verified')):raise RuntimeError('Host evidence overclaims game execution')
    if (not result['real_lua_provider_executed'] or not result['script_lifecycle_with_instrumented_core']
            or result['game_script_libraries_registered'] or result['original_event_semantics_verified']):
        raise RuntimeError('Script service execution scope differs')
    if result['script_allocation_failures']!={'cpp':6,'lua_create':423,'lua_execute':135,'lua_event':117}:
        raise RuntimeError('Script allocation failure evidence differs')
    if result['script_foreign_thread_rejections']!=160 or result['script_restart_cycles']!=32:
        raise RuntimeError('Script ownership/lifetime evidence differs')
    lua=json.loads((PROJECT/'evidence/lua_provider/build_result.json').read_text());check_artifacts(lua['library'])
    if lua['library'] not in build['provider_inputs']:raise RuntimeError('Verified Lua provider was not linked')
    for name in ('host','script_tests'):
        item=build['builds'][name]
        if not any(r['path'].replace('\\','/').lower().endswith('/source/host/scriptsystem.h') for r in item['compiler_inputs']):
            raise RuntimeError('Script service was not consumed by the compiler')
        text=read_text(Path(item['map']['path']))
        if not all(re.search(r'\b'+symbol+r'\b',text) for symbol in ('lua_newstate','lua_cpcall','lua_pcall')):
            raise RuntimeError('Actual Lua provider entrypoints missing from linked host/test')
    rows=inventory()
    if rows!=interfaces['interfaces'] or generated(rows)!=(PROJECT/'Source/Host/GeneratedHostInterfaces.h').read_text():
        raise RuntimeError('Frozen SDK host interface drift')
    implemented=[];source=(PROJECT/'Source/Host/HostServices.h').read_text()
    for row,derived in zip(rows[:2],('EngineServices','UserInterface')):
        definition=body(source,'class '+derived+' final')
        names=set(re.findall(r'\b(\w+)\([^;{}]*\)\s*(?:const\s*)?override',definition))
        methods=[{**m,'implemented':m['name'] in names} for m in row['methods']]
        if names-{m['name'] for m in methods}:raise RuntimeError('Unmatched host service override')
        implemented.append({'interface':row['base'],'slots':len(methods),'implemented_slots':sum(m['implemented'] for m in methods),'methods':methods})
    for build_item in build['builds'].values():
        deps=build_item['imports']['dependencies']
        if any('gamecore' in d.lower() for d in deps) or build_item['executable']['pe']['architecture']!='x64':raise RuntimeError('Host test linked GameCore/non-x64 code')
        if re.search(r'\bwarning\s+[A-Z]+\d+',read_text(Path(build_item['log']['path']))):raise RuntimeError('Host compiler warnings')
        if not build_item['compiler_inputs']:raise RuntimeError('Compiler header provenance missing')
    for row in bundle['files']:
        check_artifacts({'path':row['source'],'sha256':row['sha256']})
    from prepare_host_audio_catalog import encode
    audio=json.loads((root/'audio_catalog.json').read_text());check_artifacts(audio)
    binary,records=encode([Path(r['path']) for r in audio['snapshots']])
    if binary!=Path(audio['catalog']['path']).read_bytes() or records!=audio['records']:
        raise RuntimeError('Audio catalog differs from actual source XML')
    if (result['map_allocation_failures'],result['catalog_allocation_failures'],result['malformed_catalog_cases'])!=(2,48,81):
        raise RuntimeError('Map/audio failure evidence differs')
    if audio['missing_rule_tags']!=['ASSS_AMBIENCE_TUNDRA'] or audio['playback_verified'] or audio['original_numeric_audio_ids_verified']:
        raise RuntimeError('Audio missing-resource/verification scope changed')
    from prepare_host_script_catalog import encode as encode_scripts
    scripts=json.loads((root/'script_catalog.json').read_text());check_artifacts(scripts)
    binary,records,overrides=encode_scripts(scripts['inputs'])
    if binary!=Path(scripts['catalog']['path']).read_bytes() or records!=scripts['records'] or overrides!=scripts['overrides']:
        raise RuntimeError('Script catalog differs from pinned original snapshots/priority order')
    if (len(scripts['inputs']),len(records),len(overrides),len(result['map_script_metadata']))!=(46,36,10,18):
        raise RuntimeError('Installed script/map source coverage differs')
    if result['script_asset_failures']!={'catalog_cpp':498,'include_cpp':6,'include_lua':69} or result['script_catalog_malformed_cases']!=79:
        raise RuntimeError('Script asset failure recovery evidence differs')
    if not result['script_utility_binding_compiled'] or not result['script_utility_registration_with_fixture'] or result['script_utility_binding_failure_cases']!=3:
        raise RuntimeError('Script utility binding evidence missing')
    audit=json.loads((root/'script_binding_audit.json').read_text(encoding='utf-8'));check_artifacts(audit)
    if (audit['actual_game_library_registration_executed'] or audit['game_map_generation_verified']
        or {r['id'] for r in audit['open_findings']}!={'SCRIPT-PATTERN-INCLUDE','SCRIPT-ACTIVE-ASSET-SET','SCRIPT-OBJECT-LIFETIMES','SCRIPT-MAP-GENERATION-RECOVERY'}
        or {r['id'] for r in audit['resolved_or_reclassified_findings']}!={'SCRIPT-ENUM-LUA-UNWIND','SCRIPT-ENUM-QUERY-FAILURE','SCRIPT-REGISTRATION-FAILURE','SCRIPT-FRACTAL-OWNERSHIP-AND-DEFAULTS','SCRIPT-FRACTAL-NUMERIC-INPUTS','SCRIPT-BORROWED-REFERENCE-IDENTITY'}):
        raise RuntimeError('Script binding audit overclaims production execution')
    from lua_registration_evidence import validate as validate_lua_registration
    _,registration_result,registration_entry=validate_lua_registration()
    if audit['registration_component']!=registration_entry or not registration_result['candidate_short_circuit_verified']:
        raise RuntimeError('Script registrar audit differs from actual component evidence')
    from lua_fractal_evidence import validate as validate_lua_fractal
    _,fractal_result,fractal_entry=validate_lua_fractal()
    if (audit['fractal_component']!=fractal_entry or not fractal_result['candidate_exactly_once_and_post_destroy_rejection']
        or not fractal_result['candidate_defaults_parse_before_output']
        or any(row['whole_gamecore_execution_verified'] for row in audit['lifetime_functions'])):
        raise RuntimeError('Fractal audit differs from bounded component evidence')
    from fractal_numeric_evidence import validate as validate_fractal_numeric
    _,numeric_result,numeric_entry=validate_fractal_numeric()
    if (audit['fractal_numeric_component']!=numeric_entry or not numeric_result['normal_heights_and_rng_match']
        or len(audit['numeric_functions'])!=2 or not all(row['invalid_numeric_inputs_executed'] for row in audit['numeric_functions'])
        or any(row['whole_gamecore_execution_verified'] for row in audit['numeric_functions'])):
        raise RuntimeError('Fractal numeric audit differs from bounded component evidence')
    from lua_borrowed_evidence import validate as validate_lua_borrowed
    _,borrowed_result,borrowed_entry=validate_lua_borrowed()
    if (audit['borrowed_component']!=borrowed_entry or not borrowed_result['actual_owner_hooks_integrated']
        or borrowed_result['actual_gameplay_owner_lifecycle_executed'] or borrowed_result['gamecore_loaded']):
        raise RuntimeError('Borrowed-reference audit differs from integrated component evidence')
    from host_script_access_evidence import validate as validate_script_access
    _,access_result,access_entry=validate_script_access()
    if (build['script_access_build']!=access_entry['build'] or result['script_access_conformance']!=access_entry['conformance']
        or result['script_access_native_checks']!=access_result['native_checks'] or result['script_access_process_runs']!=4):
        raise RuntimeError('Host script access evidence does not match the integrated build')
    script_source=PROJECT/'Source/Host/ScriptSystem.h'
    if not any(Path(row['path'])==script_source and row['sha256']==artifact(script_source)['sha256'] for row in build['builds']['host']['compiler_inputs']):
        raise RuntimeError('Native host did not compile the tested script access boundary')
    from host_exception_boundary_evidence import validate as validate_host_exceptions
    _,_,exceptions=validate_host_exceptions()
    from host_game_info_evidence import validate as validate_game_info
    game_info,game_info_entry=validate_game_info()
    if (build['game_info_build']!=game_info_entry['build'] or result['game_info_conformance']!=game_info_entry['conformance']
        or result['game_info_native_checks']!=game_info['native_checks']):
        raise RuntimeError('Host GameInfo evidence differs from the integrated build')
    for header in ('GameInfoDatabase.h','ScriptRules.h'):
        source=PROJECT/'Source/Host'/header
        if not any(Path(row['path'])==source and row['sha256']==artifact(source)['sha256'] for row in build['builds']['host']['compiler_inputs']):
            raise RuntimeError('Host did not compile the tested GameInfo service')
    for name in ('host','tests'):
        for header in ('GameCoreSession.h','HostFailure.h'):
            source=PROJECT/'Source/Host'/header
            if not any(Path(row['path'])==source and row['sha256']==artifact(source)['sha256'] for row in build['builds'][name]['compiler_inputs']):
                raise RuntimeError('Native host did not consume the verified exception boundary')
    return build,result,bundle,implemented


def main():
    _,result,_,services=validate()
    from host_script_access_evidence import validate as validate_script_access
    _,_,script_access=validate_script_access()
    from host_exception_boundary_evidence import validate as validate_host_exceptions
    _,_,exceptions=validate_host_exceptions()
    from host_game_info_evidence import validate as validate_game_info
    _,game_info=validate_game_info()
    report={'status':'NATIVE_HOST_EVIDENCE_PASS','validator':artifact(Path(__file__).resolve()),
            'conformance':artifact(PROJECT/'evidence/host/conformance.json'),'services':services,
            'script_binding_audit':artifact(PROJECT/'evidence/host/script_binding_audit.json'),
            'host_exception_boundary':exceptions,
            'host_script_access':script_access,
            'host_game_info':game_info,
            'gamecore_loaded':False,'scope':'IMPLEMENTED_HOST_SERVICE_INVENTORY_NOT_COMPLETE_ENGINE_SERVICES'}
    (PROJECT/'evidence/host/services.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':report['status'],'native_checks':result['native_checks'],
                      'services':[{k:r[k] for k in ('interface','slots','implemented_slots')} for r in services]}))


if __name__=='__main__':main()
