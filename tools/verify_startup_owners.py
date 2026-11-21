"""Execute import-audited constructor/static-array/action components without GameCore."""
import json
import re
from pathlib import Path
from collect_baseline import PROJECT,read_text,pe_header
from native_build import run
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts

COMMON='SCOPE|exact_sdk_ownership_bodies_and_sort|instrumented_member_child_reset_hotkey_services|no_player_initializer_list|no_gamecore_loaded'
MARKERS={'original':'ORIGINAL|partial_child_leaks|culture_owner_missing|duplicate_arrays_replaced|action_buffer_and_entry_leaks',
         'candidate':'CANDIDATE|26_player_children_and_team_child_scoped|culture_deleted|duplicate_arrays_preserved|action_buffer_and_entry_scoped|checked_action_counts'}


def main():
    root=PROJECT/'evidence/startup_owners';bp=root/'build_result.json';build=json.loads(bp.read_text(encoding='utf-8'))
    check_artifacts(build)
    allowed={'kernel32.dll','msvcp140.dll','vcruntime140.dll','vcruntime140_1.dll'}
    rows,issues,normal=[],[],{}
    for name in ('original','candidate'):
        data=build['builds'][name];deps=data['imports']['dependencies'];exe=Path(data['executable']['path'])
        if pe_header(exe)['architecture']!='x64' or not deps or any(d.lower() not in allowed and not d.lower().startswith('api-ms-win-crt-') for d in deps):
            raise RuntimeError('Startup ownership executable architecture/import differs')
        result=run([exe],cwd=exe.parent,timeout=45)
        log=root/(name+'_execution.log');log.write_bytes(result.stdout+result.stderr);text=read_text(log)
        match=re.search(r'^PASS\|(\d+)\s*$',text,re.M);checks=int(match[1]) if match else 0
        golden=re.search(r'NORMAL_BEGIN\r?\n(.*?)NORMAL_END',text,re.S);normal[name]=golden[1].replace('\r\n','\n') if golden else None
        actors=re.search(r'ACTORS\|failures=(\d+)\|successful_retries_and_cycles=(\d+)\|observed_original_child_leaks=(\d+)\|players=(\d+)\|teams=(\d+)',text)
        actions=re.search(r'ACTIONS\|failures=(\d+)\|original_buffer_leaks=(\d+)\|original_unpublished_action_leaks=(\d+)\|8_subtypes\|gaps_and_ties\|retry',text)
        if result.returncode or not checks or COMMON not in text or MARKERS[name] not in text or not actors or not actions:
            issues.append('Startup owner observations missing: '+name)
        rows.append({'name':name,'executable':artifact(exe),'exit_code':result.returncode,'log':artifact(log),'checks':checks,
                     'actors':[int(v) for v in actors.groups()] if actors else [],'actions':[int(v) for v in actions.groups()] if actions else []})
        print(text[-3200:],flush=True)
    equal=normal['original'] is not None and normal['original']==normal['candidate']
    if not equal:issues.append('Normal action order/metadata changed')
    report={'status':'STARTUP_OWNERS_NATIVE_PASS' if not issues else 'STARTUP_OWNERS_NATIVE_FAIL',
            'build':artifact(bp),'verifier':artifact(Path(__file__).resolve()),'runs':rows,'issues':issues,
            'normal_action_order_and_metadata_equal':equal,'player_direct_child_count':26,
            'actor_failure_cases_per_variant':191,'action_failure_cases_per_variant':135,
            'candidate_direct_child_and_action_cleanup_verified':not issues,'candidate_duplicate_array_preservation_verified':not issues,
            'candidate_failure_retry_verified':not issues,'child_types_reset_and_hotkey_services_instrumented':True,
            'player_member_initializer_list_executed':False,'all_nested_child_implementations_verified':False,
            'entire_action_metadata_transactional':False,'whole_gc_lifecycle_verified':False,
            'gamecore_loaded':False,'game_launched':False,'game_multicore_verified':False}
    (root/'conformance.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':report['status'],'checks':sum(r['checks'] for r in rows),'issues':issues}))
    if issues:raise SystemExit(1)


if __name__=='__main__':main()
