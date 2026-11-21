"""Execute import-audited registration components; no GameCore is loaded."""
import json
import re
from pathlib import Path
from collect_baseline import PROJECT, pe_header
from native_build import run
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts
from build_lua_registration import fixture_text


def main():
    root=PROJECT/'evidence/lua_registration';bp=root/'build_result.json'
    build=json.loads(bp.read_text(encoding='utf-8'));check_artifacts(build)
    if build['status']!='SDK_LUA_REGISTRATION_COMPONENTS_BUILT' or len(build['audits'])!=4:
        raise RuntimeError('Registration build/import evidence missing')
    expected,_,bodies,rosters=fixture_text()
    if Path(build['fixture']['path']).read_text(encoding='utf-8')!=expected or build['extracted_bodies']!=bodies or build['method_rosters']!=rosters:
        raise RuntimeError('Registration fixture differs from exact SDK bodies')
    for audit in build['audits']:
        allowed={'kernel32.dll','msvcp140.dll','vcruntime140.dll','vcruntime140_1.dll'}
        if not audit['dependencies'] or any(s.lower() not in allowed and not s.lower().startswith('api-ms-win-crt-') for s in audit['dependencies']):
            raise RuntimeError('Registration component has an unexpected dependency')
    rows=[];observations={};issues=[]
    variants=('original','candidate','original_od','candidate_od')
    for variant in variants:
        exe=Path(build['builds'][variant]['executable']['path'])
        if pe_header(exe)['architecture']!='x64':raise RuntimeError('Registration test is not x64')
        for mode in ('normal','sequence','lua-faults','cpp-faults','exception-allocation'):
            result=run([exe,mode],cwd=exe.parent,timeout=180)
            log=root/(variant+'_'+mode+'.log');log.write_bytes(result.stdout+result.stderr)
            text=(result.stdout+result.stderr).decode('utf-8',errors='replace')
            match=re.search(r'^PASS\|(\d+)\s*$',text,re.M);count=int(match[1]) if match else 0
            rows.append({'variant':variant,'mode':mode,'executable':artifact(exe),'exit_code':result.returncode,
                'checks':count,'log':artifact(log)})
            if result.returncode or not count:
                issues.append(variant+'/'+mode+' failed');print(text[-5000:],flush=True);break
            observations[variant,mode]=text
            print(f'{variant}/{mode}: {count} checks',flush=True)
        if issues:break
    faults={};canonical=None
    if not issues:
        for variant in variants:
            normal=observations[variant,'normal']
            output=sorted(l for l in normal.splitlines() if l.startswith(('METHOD|','ACTION|','TYPE|')))
            if canonical is None:canonical=output
            if output!=canonical:issues.append('Successful SDK metadata differs: '+variant)
            for owner,names in rosters.items():
                observed=re.findall(r'^METHOD\|'+owner+r'\|([^\r\n]+)',normal,re.M)
                if observed!=names:issues.append('Method names/order differ: '+variant+'/'+owner)
            if len(re.findall(r'^ACTION\|',normal,re.M))!=84 or len(re.findall(r'^TYPE\|',normal,re.M))!=4:
                issues.append('Incomplete action/type metadata: '+variant)
            prefix='ORIGINAL_IGNORED' if variant.startswith('original') else 'CANDIDATE_STOPPED'
            if re.findall(r'^'+prefix+r'\|(\d+)\|',observations[variant,'sequence'],re.M)!=[str(i) for i in range(7)]:
                issues.append('Incomplete sequence failures: '+variant)
            faults[variant]={}
            for allocator in ('lua','cpp'):
                captures=re.findall(r'^FAULTS\|'+allocator+r'\|([^|]+)\|(\d+)\|partial=(\d+)\|stack_lock_heap_restored',observations[variant,allocator+'-faults'],re.M)
                if {r[0] for r in captures}!={'Fractal','GameInfo','Map','Game','Player','Team'} or len(captures)!=6:
                    issues.append('Missing allocator sweep: '+variant+'/'+allocator)
                values={name:{'failures':int(n),'partial_tables':int(p)} for name,n,p in captures}
                if allocator=='lua' and any(v['failures']==0 for v in values.values()):issues.append('Empty Lua failure sweep: '+variant)
                faults[variant][allocator]=values
        for variant in ('original','candidate'):
            if faults[variant]!=faults[variant+'_od']:issues.append('Optimization fault coverage changed: '+variant)
    check_artifacts(build)
    report={'status':'SDK_LUA_REGISTRATION_NATIVE_PASS' if not issues else 'SDK_LUA_REGISTRATION_NATIVE_FAIL',
        'build':artifact(bp),'verifier':artifact(Path(__file__).resolve()),'runs':rows,'issues':issues,
        'native_checks':sum(r['checks'] for r in rows),'exact_sdk_function_bodies':len(bodies),
        'method_counts':{name:len(names) for name,names in rosters.items()},'action_rows':3,'action_fields_per_row':28,
        'type_rows':4,'player_instances':64,'team_instances':64,'failure_sweeps':faults,
        'tested_optimizations':['/O2','/Od'],'sequence_failure_boundaries':7,
        'original_failure_suppression_reproduced':not issues,'candidate_short_circuit_verified':not issues,
        'candidate_stack_lock_heap_recovery':not issues,'candidate_success_metadata_and_borrowed_identity_preserved':not issues,
        'real_lua_flua_executed':True,'candidate_matches_generated_sdk':build['candidate_matches_generated_sdk'],
        'gameplay_handler_bodies_executed':False,'real_game_object_lifetimes_verified':False,
        'gamecore_loaded':False,'game_launched':False,'whole_game_library_registration_verified':False,'game_multicore_verified':False,
        'scope':build['scope']}
    (root/'conformance.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('status','native_checks','method_counts','failure_sweeps','issues')}))
    if issues:raise SystemExit(1)


if __name__=='__main__':main()
