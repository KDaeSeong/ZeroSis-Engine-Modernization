"""Execute import-audited cache failure and GC phase components, never GameCore."""
import json
import re
import sqlite3
from pathlib import Path
from collect_baseline import PROJECT, digest, read_text, pe_header
from native_build import run
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts

COMMON=(
    'PREFETCH|normal_gaps_reserved_ids|cache_false|exception|prepare|step|schema|duplicates',
    'STAGES|62_collection_failures|caller_cleanup_retry|cached_short_circuit|optional_diagnostics|3_helper_failures',
    'TYPES|3_prepare_failures|3_step_failures|existing_missing_enum_diagnostics_retained',
    'GC_PHASE|defines_prepare|postprocess_false|cache_false|local_reference_release|no_whole_gc_execution',
    'SCOPE|real_sqlite|exact_sdk_cache_types_prefetch_contiguous_gc_db_phase|instrumented_info_game_host|no_gamecore_loaded')
MARKERS={
    'original':('ORIGINAL|ignored_sql_cache_and_phase_failures_reproduced',),
    'candidate':('CANDIDATE|checked_sql_cache_and_phase_failures|stops_before_players_teams|partial_state_requires_caller_cleanup',
                 'FLAVORS|8_malformed_sql_cases|assignment_exception|previous_array_preserved|retry|empty_maxrows_preserved')}


def main():
    root=PROJECT/'evidence/database_cache';bp=root/'build_result.json'
    build=json.loads(bp.read_text(encoding='utf-8'));check_artifacts(build)
    allowed={'zerosisdatabase_x64.dll','kernel32.dll','msvcp140.dll','vcruntime140.dll','vcruntime140_1.dll'}
    if len(build['audits'])!=4: raise RuntimeError('Missing DB cache dependency audit')
    for row in build['audits']:
        if not row['dependencies'] or any(d.lower() not in allowed and not d.lower().startswith('api-ms-win-crt-') for d in row['dependencies']):
            raise RuntimeError('Unexpected DB cache executable dependency')
    rows,issues=[],[]
    for name in ('original','candidate'):
        exe=Path(build['builds'][name]['executable']['path'])
        if pe_header(exe)['architecture']!='x64': raise RuntimeError('Cache test is not x64')
        result=run([exe],cwd=exe.parent,timeout=45)
        log=root/(name+'_execution.log');log.write_bytes(result.stdout+result.stderr)
        text=read_text(log);match=re.search(r'^PASS\|(\d+)\s*$',text,re.M);count=int(match[1]) if match else 0
        if result.returncode or not count or any(m not in text for m in (*COMMON,*MARKERS[name])):
            issues.append('Cache failure observations missing: '+name)
        rows.append({'name':name,'executable':artifact(exe),'exit_code':result.returncode,'log':artifact(log),'checks':count})
        print(text,flush=True)
    corpus_source=PROJECT/'evidence/database/corpus/conformance.json'
    corpus=json.loads(corpus_source.read_text(encoding='utf-8'))
    corpus_runs,comparisons=[],[]
    for entry in corpus['copies']:
        source=Path(entry['copy']['path'])
        if source.name not in ('Civ5CoreDatabase.db','Civ5DebugDatabase.db'): continue
        if not source.is_relative_to(PROJECT) or digest(source)!=entry['copy']['sha256']:
            raise RuntimeError('Owned cached rule input changed')
        with sqlite3.connect(source.as_uri()+'?mode=ro',uri=True) as db:
            tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        missing=sorted({'GreatWorkArtifactClasses','GreatWorkSlots'}-tables)
        if missing and (source.name!='Civ5CoreDatabase.db' or missing!=['GreatWorkArtifactClasses','GreatWorkSlots']):
            raise RuntimeError('Cached corpus schema expectation changed')
        outputs={}
        for name in ('original','candidate'):
            exe=Path(build['builds'][name]['executable']['path'])
            result=run([exe,source],cwd=exe.parent,timeout=45)
            log=root/(name+'_'+source.stem+'.log');log.write_bytes(result.stdout+result.stderr)
            outputs[name]=result.stdout.replace(b'\r\n',b'\n')
            corpus_runs.append({'name':name,'database':artifact(source),'exit_code':result.returncode,'log':artifact(log)})
            expected_rejection=(bool(missing) and name=='candidate' and result.returncode==3 and
                b'CORPUS_FAILURE|GameCore type query failed: GreatWorkArtifactClasses|cache_pending=1|actions=0|live_after_cleanup=0' in result.stdout)
            if not expected_rejection and (result.returncode or b'CORPUS_RESULT|1' not in result.stdout):
                issues.append('Cached rule collection failed: '+name+'/'+source.name)
                print(read_text(log)[-1800:],flush=True)
        equal=outputs['original']==outputs['candidate']
        rejected=(bool(missing) and b'CORPUS_RESULT|1' in outputs['original'] and
            b'CORPUS_FAILURE|GameCore type query failed: GreatWorkArtifactClasses|cache_pending=1|actions=0|live_after_cleanup=0' in outputs['candidate'])
        comparisons.append({'database':source.name,'missing_required_type_tables':missing,
            'equal_collection_ids_types_flavors_lookup_enum_values':equal,'candidate_rejects_incomplete_core_schema':rejected})
        if missing:
            if not rejected: issues.append('Incomplete cached rule schema was not rejected: '+source.name)
        elif not equal: issues.append('Valid cached rule trace changed: '+source.name)
        if digest(source)!=entry['copy']['sha256']: raise RuntimeError('Read-only corpus input changed')
    if len(comparisons)!=2: issues.append('Both real cached rule inputs required')
    report={'status':'DATABASE_CACHE_NATIVE_PASS' if not issues else 'DATABASE_CACHE_NATIVE_FAIL',
            'build':artifact(bp),'verifier':artifact(Path(__file__).resolve()),'runs':rows,'issues':issues,
            'original_ignored_failures_reproduced':not issues,'required_collection_count':62,
            'candidate_error_propagation_and_retry_verified':not issues,'candidate_flavor_failure_preserves_previous_array':not issues,
            'candidate_database_phase_stops_before_players_teams':not issues,'candidate_local_reference_destroy_dispatch_verified':not issues,
            'corpus_source':artifact(corpus_source),'corpus_runs':corpus_runs,'corpus_comparisons':comparisons,
            'same_accepted_x64_database_used_for_both_algorithms':True,'concrete_info_and_game_stages_instrumented':True,
            'entire_cache_atomic_rollback_verified':False,'whole_gc_lifecycle_verified':False,
            'original_windows_game_binary_executed':False,'gamecore_loaded':False,'game_launched':False,'game_multicore_verified':False}
    (root/'conformance.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':report['status'],'checks':sum(r['checks'] for r in rows),'issues':issues}))
    if issues: raise SystemExit(1)


if __name__=='__main__': main()
