"""Run isolated numeric comparisons, error recovery and original fault probes."""
import json,os,re
from pathlib import Path
from collect_baseline import PROJECT,pe_header
from native_build import run
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts
from build_fractal_numeric import fixture_texts


def main():
    root=PROJECT/'evidence/fractal_numeric';bp=root/'build_result.json'
    build=json.loads(bp.read_text(encoding='utf-8'));check_artifacts(build)
    if build['status']!='SDK_FRACTAL_NUMERIC_COMPONENTS_BUILT' or len(build['audits'])!=6:raise RuntimeError('Numeric build/import evidence missing')
    texts,_=fixture_texts()
    for row in build['fixtures']:
        p=Path(row['path'])
        if p.read_text(encoding='utf-8')!=texts[p.name]:raise RuntimeError('Numeric fixture differs from exact source bodies')
    for row in build['audits']:
        allowed={'kernel32.dll','msvcp140.dll','vcruntime140.dll','vcruntime140_1.dll'}
        if Path(row['module']['path']).stem.endswith('_asan'):allowed.add('clang_rt.asan_dynamic-x86_64.dll')
        if not row['dependencies'] or any(d.lower() not in allowed and not d.lower().startswith('api-ms-win-crt-') for d in row['dependencies']):raise RuntimeError('Unexpected numeric Fractal dependency')
    rows=[];observations={};issues=[]
    for variant,binary in build['builds'].items():
        exe=Path(binary['executable']['path'])
        if pe_header(exe)['architecture']!='x64':raise RuntimeError('Numeric test is not x64')
        if variant=='original_asan':modes=('probe_exponent','probe_hints','probe_rifts')
        elif variant=='candidate_asan':modes=('bounds','small_rifts','lua_errors')
        else:
            modes=('matrix','math','wide','retry')
            modes+=('probe_zero',) if variant.startswith('original') else ('bounds','small_rifts','lua_errors')
        for mode in modes:
            env=os.environ.copy()
            if variant.endswith('_asan'):env['ASAN_OPTIONS']='exitcode=86:abort_on_error=0:detect_leaks=0:symbolize=0'
            result=run([exe,mode],cwd=exe.parent,env=env,timeout=120)
            log=root/(variant+'_'+mode+'.log');log.write_bytes(result.stdout+result.stderr)
            text=(result.stdout+result.stderr).decode('utf-8',errors='replace')
            match=re.search(r'^PASS\|(\d+)\s*$',text,re.M);count=int(match[1]) if match else 0
            if mode=='probe_zero':passed=(result.returncode&0xffffffff)==0xc0000094;expect='INTEGER_DIVIDE_BY_ZERO'
            elif mode.startswith('probe_'):
                passed=result.returncode==86 and 'AddressSanitizer: heap-buffer-overflow' in text;expect='ASAN_HEAP_BUFFER_OVERFLOW'
            else:passed=result.returncode==0 and count>0;expect='PASS_WITH_ASSERTIONS'
            rows.append({'variant':variant,'mode':mode,'executable':artifact(exe),'exit_code':result.returncode,
                'checks':count,'expected_outcome':expect,'expected_outcome_observed':passed,'log':artifact(log)})
            if not passed:
                issues.append(variant+'/'+mode+' did not match expected outcome');print(text[-4500:],flush=True);break
            observations[variant,mode]=text;print(f'{variant}/{mode}: {count} checks; {expect}',flush=True)
        if issues:break
    matrix=[];math=[];counts=[];wide={};retry={};rejections={}
    if not issues:
        for variant in ('original','candidate','original_od','candidate_od'):
            records=re.findall(r'^NUMERIC\|([^\r\n]+)',observations[variant,'matrix'],re.M)
            m=re.search(r'MATRIX_CASES\|(\d+)',observations[variant,'matrix'])
            if not m or int(m[1])!=len(records):issues.append('Incomplete matrix records: '+variant)
            counts.append(len(records));matrix.append(records)
            math.append(re.findall(r'^MATH\|([^\r\n]+)',observations[variant,'math'],re.M))
            wide[variant]=re.search(r'WIDE_BLEND\|(\d+)\|differences=(\d+)',observations[variant,'wide']).groups()
            retry[variant]=re.search(r'RETRY\|(\d+)\|([^\r\n]+)',observations[variant,'retry']).groups()
        if len(set(counts))!=1 or counts[0]!=3186 or any(r!=matrix[0] for r in matrix[1:]):issues.append('Native numeric/RNG comparison mismatch')
        if any(len(r)!=18 or r!=math[0] for r in math):issues.append('Lua math/RNG comparison mismatch')
        for variant in ('candidate','candidate_od','candidate_asan'):
            m=re.search(r'REJECTIONS\|(\d+)\|unchanged_state_and_rng',observations[variant,'bounds'])
            rejections[variant]=int(m[1]) if m else 0
            if rejections[variant]!=29:issues.append('Numeric rejection coverage changed: '+variant)
        for variant in ('original','original_od'):
            if wide[variant]!=('6','6') or retry[variant][0]!='20000':issues.append('Original overflow/retry observations changed: '+variant)
        for variant in ('candidate','candidate_od'):
            if wide[variant]!=('6','0') or retry[variant][0]!='2570':issues.append('Candidate wide arithmetic/retry contract failed: '+variant)
    check_artifacts(build)
    report={'status':'SDK_FRACTAL_NUMERIC_NATIVE_PASS' if not issues else 'SDK_FRACTAL_NUMERIC_NATIVE_FAIL',
        'build':artifact(bp),'verifier':artifact(Path(__file__).resolve()),'runs':rows,'issues':issues,
        'native_checks':sum(r['checks'] for r in rows),'normal_native_scenarios_per_configuration':counts[0] if counts else 0,
        'normal_lua_scenarios_per_configuration':18,'tested_optimizations':['/O2','/Od'],
        'normal_heights_and_rng_match':not issues,'wide_blend_observations':wide,'retry_observations':retry,
        'invalid_initialization_and_ridge_rejections':rejections,
        'original_integer_zero_division_reproduced':not issues,
        'original_asan_fault_inputs':['exponent_8','short_hint_buffer','small_rift_grid'] if not issues else [],
        'candidate_asan_boundaries_rifts_lua_errors_pass':not issues,
        'candidate_preflight_failure_preserves_state_and_rng':not issues,
        'candidate_retry_failure_preserves_heights':not issues,'candidate_retry_failure_rolls_back_rng':False,
        'candidate_cpp_errors_become_lua_errors':not issues,
        'real_lua_flua_executed':True,'native_fractal_class_and_calculation_bodies_executed':True,
        'numeric_rng_and_container_owner_adapters':True,'original_retry_has_instrumented_observation_limit':True,
        'candidate_matches_generated_sdk':build['candidate_matches_generated_sdk'],
        'borrowed_game_object_lifetimes_verified':False,'gamecore_loaded':False,'game_launched':False,'game_multicore_verified':False,
        'scope':build['scope']}
    (root/'conformance.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('status','native_checks','normal_native_scenarios_per_configuration','issues')}))
    if issues:raise SystemExit(1)


if __name__=='__main__':main()
