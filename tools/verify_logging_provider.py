"""Run the import-audited logging component in an isolated workspace directory."""
import json,re,uuid
from pathlib import Path
from collect_baseline import PROJECT,read_text,pe_header
from native_build import run
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts

def main():
    root=PROJECT/'evidence/logging';bp=root/'build_result.json';b=json.loads(bp.read_text(encoding='utf-8'));check_artifacts(b)
    consumer=b['consumer'];exe=Path(consumer['executable']['path'])
    allowed={'kernel32.dll','msvcp140.dll','vcruntime140.dll','vcruntime140_1.dll'}
    if pe_header(exe)['architecture']!='x64' or any(d.lower() not in allowed and not d.lower().startswith('api-ms-win-crt-') for d in consumer['imports']['dependencies']):raise RuntimeError('Logging import/architecture gate failed')
    directory=PROJECT/'Build/Logging/runs'/('run_'+uuid.uuid4().hex);directory.mkdir(parents=True,exist_ok=False)
    result=run([exe,directory],cwd=directory,timeout=60)
    log=root/'execution.log';log.write_bytes(result.stdout+result.stderr);text=read_text(log)
    match=re.search(r'^PASS\|(\d+)\s*$',text,re.M);faults=re.search(r'^FAULTS\|(\d+)\|',text,re.M)
    issues=[]
    if result.returncode or not match or not faults:issues.append('Native logging component failed')
    shared=directory/'concurrent.log';records=[]
    if shared.exists():
        records=shared.read_text(encoding='utf-8').splitlines()
    expected={f'{w},{i},payload' for w in range(8) for i in range(200)}
    if len(records)!=1600 or set(records)!=expected:issues.append('Shared-log records interleaved, missing or duplicated')
    from define_logging_caller_patches import patches
    _,calls=patches();caller_output=directory/'sdk_callers.log'
    actual=caller_output.read_text(encoding='utf-8').splitlines() if caller_output.exists() else []
    prefixes={'Msg':'','DebugMsg':'[DEBUG] ','WarningMsg':'[WARNING] ','ErrorMsg':'[ERROR] '}
    caller_expected=[prefixes[r['method']]+'City 100% %s %n literal payload' for r in calls]
    if actual!=caller_expected:issues.append('SDK prepared text was reinterpreted or its severity changed')
    regression=root/'regressions/missing_error_code/before.json'
    prior=json.loads(regression.read_text(encoding='utf-8'));check_artifacts(prior)
    if prior['expected_bytes_hex']==prior['actual_bytes_hex'] or prior['exit_code']!=2:issues.append('Missing zero-error-code defect reproduction')
    report={'status':'LOGGING_NATIVE_COMPONENT_PASS' if not issues else 'LOGGING_NATIVE_COMPONENT_FAIL',
        'build':artifact(bp),'verifier':artifact(Path(__file__).resolve()),'execution':{'exit_code':result.returncode,'log':artifact(log),
            'checks':int(match[1]) if match else 0,'fault_cases':int(faults[1]) if faults else 0,'directory':str(directory)},
        'shared_records':len(records),'shared_exact_set':set(records)==expected,'shared_unique':len(set(records)),
        'sdk_caller_records':len(actual),'sdk_caller_exact':actual==caller_expected,
        'missing_error_code_regression':artifact(regression),
        'outputs':[artifact(p) for p in sorted(directory.iterdir()) if p.is_file()],'issues':issues,
        'windows_log_io_executed':True,'original_concrete_logger_oracle_available':False,
        'gamecore_loaded':False,'game_launched':False,'game_multicore_verified':False,'power_loss_recovery_verified':False}
    (root/'conformance.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(text);print(report['status'])
    if issues:raise SystemExit(1)
if __name__=='__main__':main()
