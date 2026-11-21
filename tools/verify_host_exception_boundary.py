"""Reproduce the old unload fault and verify host-owned errors through real DLL unload/retry."""
import json,re
from pathlib import Path
from collect_baseline import PROJECT
from native_build import run
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts

ORIGINAL_CASES=('init-standard','init-unknown','init-borrowed','shutdown-standard','shutdown-unknown','shutdown-borrowed','dual-standard')
CANDIDATE_CASES=ORIGINAL_CASES+('init-long','init-null','shutdown-long','shutdown-null','withcore-standard','withcore-unknown')

def main():
    root=PROJECT/'evidence/host_exception_boundary';bp=root/'build_result.json'
    build=json.loads(bp.read_text(encoding='utf-8'));check_artifacts(build)
    rows=[];total=0
    for suffix in ('o2','od'):
        dll=Path(build['builds']['fixture_'+suffix]['binary']['path'])
        for variant,cases in (('original',ORIGINAL_CASES),('candidate',CANDIDATE_CASES)):
            name=variant+'_'+suffix;exe=Path(build['builds'][name]['binary']['path'])
            for scenario in cases:
                result=run([exe,dll,scenario],cwd=exe.parent,timeout=30)
                log=root/(name+'_'+scenario+'.log');log.write_bytes(result.stdout+result.stderr)
                text=(result.stdout+result.stderr).decode('utf-8',errors='replace')
                unloads=[tuple(map(int,m)) for m in re.findall(r'BEFORE_UNLOAD live=(\d+) created=(\d+) destroyed=(\d+)',text)]
                if variant=='original':
                    if result.returncode & 0xffffffff != 0xc0000005 or len(unloads)!=1 or 'HOST_EXCEPTION_BOUNDARY_PASS' in text:
                        raise RuntimeError('Original unload lifetime fault not reproduced: '+str(log))
                    if 'borrowed' not in scenario and unloads[0][0]!=2:
                        raise RuntimeError('Original foreign exception retention changed')
                    observations={'expected_access_violation':True,'foreign_live_at_unload':unloads[0][0]}
                else:
                    m=re.search(r'HOST_EXCEPTION_BOUNDARY_PASS checks=(\d+) live_at_close=(\d+) live_at_exit=(\d+) created=(\d+) destroyed=(\d+) message_bytes=(\d+) GAMECORE_LOADED=false',text)
                    if result.returncode or not m or len(unloads)!=2 or any(row[0] for row in unloads):
                        raise RuntimeError('Candidate unload/normal restart failed: '+str(log)+'\n'+text)
                    checks,close,live,created,destroyed,message_bytes=map(int,m.groups())
                    if close or live or created!=destroyed or not checks:
                        raise RuntimeError('Candidate retained foreign exception state')
                    if 'long' in scenario and message_bytes!=1023:raise RuntimeError('Bounded diagnostic text differs')
                    observations=dict(checks=checks,foreign_live_at_unload=close,foreign_live_at_exit=live,
                        foreign_created=created,foreign_destroyed=destroyed,message_bytes=message_bytes,normal_restart=True,
                        withcore_path=scenario.startswith('withcore-'))
                    if ('WITHCORE_PATH='+str(observations['withcore_path']).lower()) not in text:
                        raise RuntimeError('Operation exception path marker missing')
                    total+=checks
                rows.append(dict(variant=name,scenario=scenario,executable=build['builds'][name]['binary'],
                    fixture=build['builds']['fixture_'+suffix]['binary'],log=artifact(log),return_code=result.returncode,observations=observations))
    check_artifacts(build)
    report=dict(status='HOST_EXCEPTION_BOUNDARY_NATIVE_PASS',build=artifact(bp),verifier=artifact(Path(__file__).resolve()),
        runs=rows,native_checks=total,original_access_violations=14,candidate_successes=26,
        withcore_foreign_exception_cases=4,
        standard_and_unknown_foreign_errors=True,integrated_native_reference_error_executed=True,
        initialization_cleanup_dual_failure=True,retained_host_error_after_unload=True,cleanup_diagnostic_copy_survives_retry=True,
        long_and_null_message_defense=True,real_fixture_dll_unloaded=True,normal_restart_after_failure=True,
        gamecore_loaded=False,game_launched=False,scope=build['scope'])
    (root/'conformance.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('status','native_checks','original_access_violations','candidate_successes')}))

if __name__=='__main__':main()
