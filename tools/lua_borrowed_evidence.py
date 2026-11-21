"""Validate integrated Lua references; retain the isolated candidate's historical validation route."""
import json
import hashlib
from pathlib import Path
from collect_baseline import PROJECT, digest
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts
from build_lua_borrowed import fixture_text, TYPES
from define_lua_borrowed_patches import BASE, LIFECYCLE, patches, baseline_text, candidate_text


def validate():
    root=PROJECT/'evidence/lua_borrowed'
    paths={name:root/(name+'.json') for name in ('build_result','conformance','lifecycle_audit','caller_patch_plan')}
    build,result,audit,declared=(json.loads(p.read_text(encoding='utf-8')) for p in paths.values())
    check_artifacts([build,result,audit,declared])
    if build['status']!='SDK_LUA_BORROWED_COMPONENTS_BUILT' or result['status']!='SDK_LUA_BORROWED_NATIVE_PASS':
        raise RuntimeError('Current generated SDK borrowed component execution required')
    if not build['candidate_matches_generated_sdk'] or not result['actual_owner_hooks_integrated'] or not audit['candidate_applied_to_sdk']:
        raise RuntimeError('Only an isolated proposal has been tested')
    master=PROJECT/'Source/Porting/sdk_x64_patches.json'
    plan=json.loads(master.read_text(encoding='utf-8'))
    baseline=json.loads(BASE.read_text(encoding='utf-8'))
    if len(baseline['patches'])!=629 or plan['patches']!=baseline['patches']+patches() or len(plan['patches'])!=693:
        raise RuntimeError('Accepted borrowed baseline or appended recipe differs')
    if declared['patches']!=patches() or declared.get('patch_specification')!=artifact(master):
        raise RuntimeError('Borrowed applied specification is stale')
    text,sources,extracted=fixture_text()
    if Path(build['fixture']['path']).read_text(encoding='utf-8')!=text or build['extracted_bodies']!=extracted or len(extracted)!=51:
        raise RuntimeError('Borrowed exact SDK body fixture differs')
    for source,expected in sources.items():
        if (PROJECT/'Source/SDK_BNW_x64'/source).read_bytes().decode('latin1')!=expected:
            raise RuntimeError('Generated SDK borrowed body differs: '+source)
    sdk_path=PROJECT/'evidence/sdk_x64/build_result.json'
    sdk=json.loads(sdk_path.read_text(encoding='utf-8'))
    if sdk['status']!='SDK_X64_ALL_OBJECTS_COMPILED' or len(sdk['objects'])!=161 or sdk['patch_specification']!=artifact(master):
        raise RuntimeError('Borrowed changes have not compiled into the current GameCore')
    check_artifacts(sdk['objects']+sdk['support_inputs']+[sdk['manifest'],sdk['builder']])
    helper=PROJECT/'Source/LuaBorrowed/ZeroSisLuaBorrowed.h'
    if artifact(helper) not in sdk['support_inputs'] or len(sdk['support_inputs'])!=11:
        raise RuntimeError('Borrowed helper not tracked by the SDK compilation')
    manifest=json.loads(Path(sdk['manifest']['path']).read_text(encoding='utf-8'))
    if len(manifest)!=1105: raise RuntimeError('Incomplete SDK manifest')
    for row in manifest:
        source=row['relative_path']
        expected=candidate_text(source).encode('latin1') if row['patch_ids'] else (PROJECT/'Source/SDK_BNW_Original'/source).read_bytes()
        if hashlib.sha256(expected).hexdigest()!=row['port_sha256'] or digest(Path(row['port']))!=row['port_sha256']:
            raise RuntimeError('Compiled borrowed source manifest differs: '+source)
    if set(build['builds'])!={'original','candidate','original_od','candidate_od'} or len(result['runs'])!=4 or result['native_checks']!=27168:
        raise RuntimeError('Borrowed execution coverage differs')
    if result['native_checks']!=sum(r['results']['checks'] for r in result['runs']):
        raise RuntimeError('Borrowed check accounting differs')
    by_name={r['variant']:r['results'] for r in result['runs']}
    if by_name['original']!=by_name['original_od'] or by_name['candidate']!=by_name['candidate_od']:
        raise RuntimeError('Borrowed outcomes differ by optimization')
    for row in result['runs']:
        value=row['results'];candidate=row['variant'].startswith('candidate')
        expected=dict(candidate=candidate,forged_accepted=0 if candidate else 3,stale_accepted=0 if candidate else 1,
            reentrant_rejections=5 if candidate else 1,partial_registrations=0 if candidate else 2,
            native_proxy_kinds=4,unit_notifications=1,cross_translation_unit_registry=True,container_operations=12,
            deal_copy_cases=4,deal_self_copy_losses=0 if candidate else 3,tracked_at_exit=0,container_blocks_at_exit=0)
        if row['return_code'] or any(value.get(k)!=v for k,v in expected.items()):
            raise RuntimeError('Borrowed native defect/contract observation differs')
        if candidate and (value['is_none_errors'] or value['is_none_incorrect']):
            raise RuntimeError('Invalid IsNone candidate result')
    for row in build['builds'].values():
        if row['executable']['pe']['machine_hex']!='0x8664' or row['executable']['pe']['is_dll']:
            raise RuntimeError('Borrowed component is not an audited x64 executable')
        required=[helper,PROJECT/'Tests/sdk_lua_borrowed.cpp',Path(build['fixture']['path']),
            PROJECT/'Source/SDK_BNW_x64/FirePlace/include/FireWorks/FFastVector.h']
        for path in required:
            if not any(Path(r['path'])==path and r['sha256']==digest(path) for r in row['compiler_inputs']):
                raise RuntimeError('Borrowed source not consumed by compiler: '+str(path))
        for path in (helper,PROJECT/'Tests/sdk_lua_borrowed_peer.cpp'):
            if not any(Path(r['path'])==path and r['sha256']==digest(path) for r in row['peer_compiler_inputs']):
                raise RuntimeError('Borrowed cross-translation-unit source not consumed')
    if audit['candidate_native_hooks']!=34 or audit['player_layout']['player_base_offset']!=0 or audit['production_compile']!=artifact(sdk_path):
        raise RuntimeError('Borrowed lifetime/ABI source audit differs')
    if len(audit['bindings'])!=9 or len(audit['native_interfaces'])!=4 or len(audit['container_evidence']['mutations'])!=29:
        raise RuntimeError('Borrowed object and container coverage differs')
    if any(report[k] for report in (build,result,audit,declared) for k in ('gamecore_loaded','game_launched')) or result['actual_gameplay_owner_lifecycle_executed']:
        raise RuntimeError('Borrowed component claims full gameplay execution')
    entry=dict(name='LuaBorrowedCallers',build=artifact(paths['build_result']),conformance=artifact(paths['conformance']),
        caller_plan=artifact(paths['caller_patch_plan']),source_audit=artifact(paths['lifecycle_audit']),
        validator=artifact(Path(__file__).resolve()),sdk_compile=artifact(sdk_path),scope=result['scope'])
    return build,result,entry


def candidate_main():
    root = PROJECT/'evidence/lua_borrowed'
    paths = {name:root/(name+'.json') for name in ('build_result', 'conformance', 'lifecycle_audit', 'caller_patch_plan')}
    paths['sdk_candidate'] = root/'sdk_candidate/build_result.json'
    paths['candidate_link'] = root/'sdk_candidate/link_result.json'
    reports = {name:json.loads(path.read_text(encoding='utf-8')) for name, path in paths.items()}
    for report in reports.values(): check_artifacts(report)
    build, conformance, audit, plan, compiled, linked = (reports[name] for name in paths)
    text, sources, extracted = fixture_text()
    assert Path(build['fixture']['path']).read_text(encoding='utf-8') == text
    assert build['extracted_bodies'] == extracted and build['scoped_types'] == list(TYPES)
    assert plan['patches'] == patches() and len(plan['patches']) == 64
    assert len(extracted) == 51
    assert not build['candidate_matches_generated_sdk'] and not build['native_gameplay_owner_lifecycle_executed']
    assert not conformance['actual_owner_hooks_integrated'] and not audit['candidate_applied_to_sdk']
    master = PROJECT/'Source/Porting/sdk_x64_patches.json'
    assert json.loads(master.read_text(encoding='utf-8')) == json.loads(BASE.read_text(encoding='utf-8'))
    assert len(list((PROJECT/'Source/Porting').glob('*.h'))) == 10
    for source in sources:
        assert (PROJECT/'Source/SDK_BNW_x64'/source).read_bytes().decode('latin1') == baseline_text(source)
    required = [PROJECT/'Tests/sdk_lua_borrowed.cpp', PROJECT/'Source/LuaBorrowed/ZeroSisLuaBorrowed.h', Path(build['fixture']['path']),
        PROJECT/'Source/SDK_BNW_x64/FirePlace/include/FireWorks/FFastVector.h']
    assert set(build['builds']) == {'original', 'candidate', 'original_od', 'candidate_od'}
    for row in build['builds'].values():
        assert row['executable']['pe']['machine_hex'] == '0x8664'
        assert row['executable']['pe']['pe_format'] == 'PE32+' and not row['executable']['pe']['is_dll']
        for path in required:
            assert any(Path(item['path']) == path and item['sha256'] == digest(path) for item in row['compiler_inputs'])
        for path in (PROJECT/'Tests/sdk_lua_borrowed_peer.cpp', PROJECT/'Source/LuaBorrowed/ZeroSisLuaBorrowed.h'):
            assert any(Path(item['path']) == path and item['sha256'] == digest(path) for item in row['peer_compiler_inputs'])
        assert str(Path(row['peer_object']['path'])) in Path(row['response']['path']).read_text(encoding='utf-8')
    assert len(conformance['runs']) == 4
    assert conformance['native_checks'] == sum(row['results']['checks'] for row in conformance['runs'])
    by_name = {row['variant']:row['results'] for row in conformance['runs']}
    assert by_name['original'] == by_name['original_od'] and by_name['candidate'] == by_name['candidate_od']
    for value in by_name.values():
        assert value['native_proxy_kinds'] == 4 and value['unit_notifications'] == 1
        assert value['cross_translation_unit_registry'] and value['container_operations'] == 12
        assert value['container_blocks_at_exit'] == value['tracked_at_exit'] == 0
        assert value['deal_copy_cases'] == 4
        assert value['deal_self_copy_losses'] == (0 if value['candidate'] else 3)
    assert len(audit['bindings']) == 9 and len(audit['native_interfaces']) == 4
    assert sum(len(row['boundaries']) for row in audit['bindings'])+1 == 35
    assert len(audit['open_findings']) == 4
    assert audit['candidate_native_hooks'] == sum(map(len, LIFECYCLE.values())) == 34
    assert audit['player_layout']['player_base_offset'] == 0
    assert audit['warning_review']['normalized_locations'] == 343
    assert audit['warning_review']['codes'] == {'C4819':325, 'C4091':5, 'C4996':13}
    assert len(audit['container_evidence']['mutations']) == 29
    assert {row['method'] for row in audit['container_evidence']['mutations']} == {'clear', 'push_back'}
    assert compiled['status'] == 'LUA_BORROWED_FULL_SDK_CANDIDATE_COMPILED'
    assert compiled['patch_count'] == 693 and compiled['added_patches'] == 64
    assert not compiled['dll_linked'] and not compiled['active_sdk_updated'] and not compiled['gameplay_owner_runtime_executed']
    assert len(compiled['objects']) == 161 and all(row['architecture'] == 'x64' for row in compiled['objects'])
    assert len(compiled['phases']) == 2 and all(row['exit_code'] == 0 and not row['errors'] for row in compiled['phases'])
    candidate_plan = json.loads(Path(compiled['patch_plan']['path']).read_text(encoding='utf-8'))
    assert candidate_plan['patches'] == json.loads(BASE.read_text(encoding='utf-8'))['patches'] + patches()
    manifest = json.loads(Path(compiled['source_manifest']['path']).read_text(encoding='utf-8'))
    check_artifacts(manifest)
    assert len(manifest) == 1105
    for row in manifest:
        source = row['relative_path']
        original = PROJECT/'Source/SDK_BNW_Original'/source
        assert digest(original) == row['original_sha256']
        expected = candidate_text(source).encode('latin1') if row['patch_ids'] else original.read_bytes()
        assert hashlib.sha256(expected).hexdigest() == row['sha256']
        assert Path(row['path']) == PROJECT/'Build/LuaBorrowed/SDKCandidate/Source'/source
    # The only new header changes are Lua's template and four private wrapper fields.
    assert {row['file'] for row in patches() if row['file'].endswith('.h')} == {
        'CvGameCoreDLL_Expansion2/Lua/CvLuaScopedInstance.h',
        *['CvGameCoreDLL_Expansion2/CvDll'+name+'.h' for name in ('City','Unit','Plot','Deal')]}
    assert len(compiled['support_headers']) == 11
    assert linked['status'] == 'LUA_BORROWED_ISOLATED_SDK_DLL_LINKED_NOT_LOADED'
    assert linked['compilation'] == artifact(paths['sdk_candidate']) and linked['component'] == artifact(paths['conformance'])
    assert linked['sdk_objects'] == 161 and linked['patch_count'] == 693 and len(linked['providers']) == 16
    assert linked['link_exit_code'] == linked['unresolved_symbols'] == 0
    assert linked['generated_dll']['pe']['is_dll'] and linked['generated_dll']['pe']['machine_hex'] == '0x8664'
    assert linked['exports'] == ['DllGetGameContext', 'ZeroSisGetBootstrapError', 'ZeroSisShutdownGameCore']
    assert linked['shared_registry_symbol'] in Path(linked['map']['path']).read_text(encoding='utf-8')
    assert not linked['active_sdk_updated'] and not linked['stage_updated']
    for report in (build, conformance, audit, plan, compiled, linked):
        assert report['gamecore_loaded'] is False and report['game_launched'] is False
    result = dict(status='LUA_BORROWED_CANDIDATE_EVIDENCE_PASS_NOT_INTEGRATED',
        verifier=artifact(Path(__file__).resolve()), reports=[artifact(p) for p in paths.values()],
        native_checks=conformance['native_checks'], processes=4, proposed_patches=64, active_sdk_patches=629,
        candidate_sdk_patches=693, candidate_sdk_objects=161, candidate_lifecycle_hooks=34,
        candidate_linked=True, public_icv_declarations_unchanged=True,
        active_patch_specification=artifact(master), fixture_matches_recipe=True,
        compiler_consumed_candidate_header=True, audited_sdk_sources_unchanged=True,
        actual_owner_hooks_integrated=False, gamecore_loaded=False, game_launched=False,
        issues=[], remaining=audit['open_findings'])
    (root/'candidate_verification.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(result['status'])


if __name__ == '__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate',action='store_true',help='Validate the historical unintegrated phase only')
    args=parser.parse_args()
    if args.candidate:
        candidate_main()
    else:
        build,result,entry=validate()
        report=dict(status='SDK_LUA_BORROWED_EVIDENCE_PASS',entry=entry,native_checks=result['native_checks'],
            sdk_objects=161,patches=693,lifecycle_hooks=34,gamecore_loaded=False,game_launched=False,
            issues=[])
        (PROJECT/'evidence/lua_borrowed/production_verification.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(dict(status=report['status'],checks=report['native_checks'])))
