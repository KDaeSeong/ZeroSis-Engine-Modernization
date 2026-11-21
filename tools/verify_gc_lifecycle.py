"""Run import-audited root lifecycle fixtures, not the GameCore DLL."""
import json
import re
from pathlib import Path
from collect_baseline import PROJECT,read_text,pe_header
from native_build import run
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts

MARKER='CANDIDATE_RECOVERY:45_CHECKPOINTS 68_TYPES 4_CLEANUP_RETRY_CASES 512_BUSY_CALLS 64_RESTARTS REENTRY:49'


def main():
    root=PROJECT/'evidence/gc_lifecycle';bp=root/'build_result.json';build=json.loads(bp.read_text(encoding='utf-8'));check_artifacts(build)
    rows,issues,normal=[],[],{}
    for name in ('original','candidate'):
        item=build['builds'][name];exe=Path(item['executable']['path']);deps=item['imports']['dependencies']
        allowed={'kernel32.dll','msvcp140.dll','vcruntime140.dll','vcruntime140_1.dll'}
        if pe_header(exe)['architecture']!='x64' or not deps or any(d.lower() not in allowed and not d.lower().startswith('api-ms-win-crt-') for d in deps):raise RuntimeError('Lifecycle executable import/architecture differs')
        result=run([exe],cwd=exe.parent,timeout=45)
        log=root/(name+'_execution.log');log.write_bytes(result.stdout+result.stderr);output=read_text(log)
        m=re.search(r'GC_LIFECYCLE_PASS checks=(\d+)',output);checks=int(m[1]) if m else 0
        m=re.search(r'^NORMAL_TRACE:(.*)$',output,re.M);normal[name]=m[1].strip() if m else None
        m=re.search(r'FAILURE_POINTS:(\d+) ORIGINAL_REMAINING:(\d+)',output)
        observations=[int(x) for x in m.groups()] if m else []
        if result.returncode or not checks or len(observations)!=2 or observations[0]!=48 or (name=='candidate' and (observations[1]!=0 or MARKER not in output)):
            issues.append('Missing lifecycle observations: '+name)
        if name=='original' and (not observations or observations[1]==0):issues.append('Original partial-owner leak was not reproduced')
        rows.append({'name':name,'executable':artifact(exe),'log':artifact(log),'exit_code':result.returncode,'checks':checks,'observations':observations})
        print(output[-1800:],flush=True)
    equal=normal['original'] is not None and normal['original']==normal['candidate']
    if not equal:issues.append('Normal original/candidate lifecycle call order differs')
    report={'status':'GC_LIFECYCLE_NATIVE_PASS' if not issues else 'GC_LIFECYCLE_NATIVE_FAIL','build':artifact(bp),
            'verifier':artifact(Path(__file__).resolve()),'runs':rows,'issues':issues,'normal_call_order_equal':equal,
            'startup_failure_points_per_variant':48,'cleanup_checkpoints':45,'reset_type_count':68,'cleanup_retry_cases':4,
            'concurrent_busy_calls':512,'reentrant_boundaries':49,'restart_cycles':64,
            'exact_gc_context_bodies_executed':True,'real_type_reset_executed':True,'game_children_host_database_instrumented':True,
            'all_transitive_children_and_game_state_recovery_verified':False,'borrower_quiescence_enforced':False,
            'gamecore_loaded':False,'game_launched':False,'game_multicore_verified':False}
    (root/'conformance.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':report['status'],'checks':sum(r['checks'] for r in rows),'issues':issues}))
    if issues:raise SystemExit(1)


if __name__=='__main__':main()
