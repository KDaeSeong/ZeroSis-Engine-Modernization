"""Verify VM-owned Fractal lifetime and compare unchanged SDK math without GameCore."""
import json,re
from pathlib import Path
from collect_baseline import PROJECT,pe_header
from native_build import run
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts
from build_lua_fractal import fixture_texts


def main():
    root=PROJECT/'evidence/lua_fractal';bp=root/'build_result.json'
    build=json.loads(bp.read_text(encoding='utf-8'));check_artifacts(build)
    if build['status']!='SDK_LUA_FRACTAL_COMPONENTS_BUILT' or len(build['audits'])!=6:raise RuntimeError('Fractal build/import evidence missing')
    texts,_=fixture_texts()
    for row in build['fixtures']:
        p=Path(row['path'])
        if p.read_text(encoding='utf-8')!=texts[p.name]:raise RuntimeError('Fractal fixture differs from exact SDK bodies')
    for row in build['audits']:
        allowed={'kernel32.dll','msvcp140.dll','vcruntime140.dll','vcruntime140_1.dll'}
        if not row['dependencies'] or any(d.lower() not in allowed and not d.lower().startswith('api-ms-win-crt-') for d in row['dependencies']):raise RuntimeError('Unexpected Fractal dependency')
    rows=[];observations={};issues=[]
    for variant,binary in build['builds'].items():
        exe=Path(binary['executable']['path'])
        if pe_header(exe)['architecture']!='x64':raise RuntimeError('Fractal test is not x64')
        modes=('math',) if variant.endswith('_math') else ('lifetime','foreign','faults','collection','defaults')
        for mode in modes:
            result=run([exe,mode],cwd=exe.parent,timeout=60)
            log=root/(variant+'_'+mode+'.log');log.write_bytes(result.stdout+result.stderr)
            text=(result.stdout+result.stderr).decode('utf-8',errors='replace');match=re.search(r'^PASS\|(\d+)\s*$',text,re.M)
            count=int(match[1]) if match else 0
            rows.append({'variant':variant,'mode':mode,'executable':artifact(exe),'exit_code':result.returncode,'checks':count,'log':artifact(log)})
            if result.returncode or not count:
                issues.append(variant+'/'+mode+' failed');print(text[-5000:],flush=True);break
            observations[variant,mode]=text;print(f'{variant}/{mode}: {count} checks',flush=True)
        if issues:break
    faults={};math=[]
    if not issues:
        for variant in ('original','candidate','original_od','candidate_od'):
            m=re.search(r'LUA_FAILURES\|(\d+)\|missing_finalizers=(\d+)',observations[variant,'faults'])
            if not m:issues.append('Missing Fractal allocation sweep: '+variant);continue
            faults[variant]={'lua_failures':int(m[1]),'missing_finalizers':int(m[2])}
            if faults[variant]['lua_failures']==0:issues.append('Empty Fractal allocation sweep')
            if variant.startswith('original') and not faults[variant]['missing_finalizers']:issues.append('Original skipped finalization not reproduced')
            if variant.startswith('candidate') and faults[variant]['missing_finalizers']:issues.append('Candidate skipped native finalizer')
            expected=[('0','3'),('1','3'),('2','1')] if variant.startswith('original') else [('0','0'),('1','0'),('2','0')]
            if re.findall(r'FOREIGN\|(\d+)\|native_dispatch=(\d+)',observations[variant,'foreign'])!=expected:issues.append('Foreign userdata observation changed: '+variant)
        for name in ('original','candidate'):
            if faults.get(name)!=faults.get(name+'_od'):issues.append('Fractal optimization coverage differs: '+name)
        for variant in ('original_math','candidate_math'):
            records=re.findall(r'^MATH\|([^\r\n]+)',observations[variant,'math'],re.M)
            if len(records)!=18:issues.append('Fractal numerical scenario coverage missing')
            math.append(records)
        if math[0]!=math[1]:issues.append('Fractal heights or RNG trace changed')
    check_artifacts(build)
    report={'status':'SDK_LUA_FRACTAL_NATIVE_PASS' if not issues else 'SDK_LUA_FRACTAL_NATIVE_FAIL',
        'build':artifact(bp),'verifier':artifact(Path(__file__).resolve()),'runs':rows,'issues':issues,
        'native_checks':sum(r['checks'] for r in rows),'lifetime_failure_sweeps':faults,
        'exact_lua_function_bodies':10,'foreign_input_kinds':3,'gc_objects_per_variant':128,
        'math_scenarios':18,'unchanged_input_math_scenarios':12,'omitted_defaults_vs_original_explicit_defaults_scenarios':6,
        'height_samples_per_scenario':1290,'math_and_rng_traces_equal':not issues,
        'original_duplicate_destruction_observed':not issues,'original_foreign_native_dispatch_observed':not issues,
        'original_missing_optional_arguments_misread':not issues,'candidate_defaults_parse_before_output':not issues,
        'candidate_exactly_once_and_post_destroy_rejection':not issues,'candidate_lua_allocations_before_native_construction':not issues,
        'candidate_weak_registry_survives_finalization_without_retaining_objects':not issues,
        'tested_lifetime_optimizations':['/O2','/Od'],'real_lua_flua_executed':True,
        'real_calculation_bodies_executed_with_adapters':True,'native_lifetime_is_instrumented':True,
        'actual_fractal_dynamic_resource_leak_proven':False,'candidate_matches_generated_sdk':build['candidate_matches_generated_sdk'],
        'all_fractal_numeric_inputs_validated':False,'borrowed_game_object_lifetimes_verified':False,
        'gamecore_loaded':False,'game_launched':False,'game_multicore_verified':False,'scope':build['scope']}
    (root/'conformance.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('status','native_checks','lifetime_failure_sweeps','math_and_rng_traces_equal','issues')}))
    if issues:raise SystemExit(1)


if __name__=='__main__':main()
