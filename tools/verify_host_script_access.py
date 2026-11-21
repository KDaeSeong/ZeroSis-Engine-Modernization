"""Exercise real host/Lua boundaries; the game library is an instrumented interface."""
import argparse,json,re
from pathlib import Path
from collect_baseline import PROJECT,read_text
from native_build import run
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts

METHODS=('LoadFile','Execute','RegisterFunction','CallCFunction','CallFunction','CallHook','CallTestAll','CallTestAny','CallAccumulatorInt','CallAccumulatorFloat')
CONDITIONS=('unlocked','worker_lock','wrong_owner','owner_query_exception','lock_query_exception','lock_query_unknown')
RECOVERY='SCRIPT_ACCESS_RECOVERY_PASS STALE_NATIVE_REFERENCE=true FOREIGN_REJECTIONS=12 FINALIZER_LOCKED=true GAMECORE_LOADED=false'
LIFECYCLE='SCRIPT_ACCESS_LIFECYCLE_QUERIES_PASS REJECTED=12 RETRY_CLOSED=4'
PATTERN=r'SCRIPT_ACCESS_CASE condition=(\w+) method=(\w+) accepted=(\d+) callbacks=(\d+) unlocked_callbacks=(\d+) recovery=(\d+)'

def observations(output,original):
    rows=[dict(condition=r[0],method=r[1],accepted=int(r[2]),callbacks=int(r[3]),unlocked_callbacks=int(r[4]),recovery=int(r[5])) for r in re.findall(PATTERN,output)]
    expected=[]
    for condition in CONDITIONS:
        for method in METHODS:
            callbacks=int(original and method!='RegisterFunction')
            expected.append(dict(condition=condition,method=method,accepted=int(original),callbacks=callbacks,
                unlocked_callbacks=callbacks if condition in ('unlocked','worker_lock') else 0,recovery=1))
    if rows!=expected:raise RuntimeError('Original/current script access matrix differs: '+output[-2000:])
    match=re.search(r'HOST_SCRIPT_ACCESS_PASS checks=(\d+) original=(\d+) cases=60 accepted=(\d+) GAMECORE_LOADED=false',output)
    if not match or int(match[2])!=int(original) or int(match[3])!=sum(r['accepted'] for r in rows):
        raise RuntimeError('Missing script access accounting')
    if not original and (RECOVERY not in output or LIFECYCLE not in output):raise RuntimeError('Missing native reference/thread/finalizer recovery')
    return {'checks':int(match[1]),'matrix':rows,'recovery':not original and RECOVERY in output,
        'lifecycle_query_failures':not original and LIFECYCLE in output}

def main(variant='all'):
    root=PROJECT/'evidence/host_script_access'
    bp=root/('build_result.json' if variant=='all' else variant+'_build.json')
    build=json.loads(bp.read_text());check_artifacts(build);runs=[]
    for name,item in build['builds'].items():
        exe=Path(item['executable']['path']);result=run([exe],cwd=exe.parent,timeout=45)
        log=root/(name+'_execution.log');log.write_bytes(result.stdout+result.stderr)
        output=read_text(log).replace('\r\n','\n')
        if result.returncode:raise RuntimeError(name+': '+output[-3000:])
        runs.append({'name':name,'executable':artifact(exe),'log':artifact(log),'exit_code':result.returncode,
            'observations':observations(output,name.startswith('original'))})
    candidate=[r for r in runs if r['name'].startswith('candidate')]
    original=[r for r in runs if r['name'].startswith('original')]
    report={'status':'HOST_SCRIPT_ACCESS_NATIVE_PASS','verifier':artifact(Path(__file__).resolve()),'build':artifact(bp),'runs':runs,
        'original_accepted_calls':sum(row['accepted'] for r in original for row in r['observations']['matrix']),
        'original_unlocked_callbacks':sum(row['unlocked_callbacks'] for r in original for row in r['observations']['matrix']),
        'candidate_rejected_calls':sum(not row['accepted'] for r in candidate for row in r['observations']['matrix']),
        'native_checks':sum(r['observations']['checks'] for r in candidate),
        'gamecore_loaded':False,'game_launched':False,'game_multicore_verified':False,
        'scope':'REAL_HOST_LOCKS_AND_LUA_WITH_INSTRUMENTED_LIBRARY_AND_NATIVE_REFERENCE_OWNER_NOT_GAMECORE_EXECUTION'}
    target='conformance.json' if variant=='all' else variant+'_reproduction.json'
    (root/target).write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({key:report[key] for key in ('status','original_accepted_calls','original_unlocked_callbacks','candidate_rejected_calls','native_checks')}))
    return report

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--variant',choices=('all','original','candidate'),default='all')
    main(parser.parse_args().variant)
