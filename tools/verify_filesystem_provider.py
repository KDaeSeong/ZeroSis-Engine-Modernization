"""Exercise only the import-audited filesystem component inside a new workspace directory."""
import json,re,uuid
from pathlib import Path
from collect_baseline import PROJECT,read_text,pe_header
from native_build import run
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts

def main():
    evidence=PROJECT/'evidence/filesystem'
    bp=evidence/'build_result.json';build=json.loads(bp.read_text(encoding='utf-8'));check_artifacts(build)
    if build['status']!='FILESYSTEM_X64_PROVIDER_BUILT':raise RuntimeError('Filesystem build missing')
    allowed={'kernel32.dll','msvcp140.dll','vcruntime140.dll','vcruntime140_1.dll'}
    for consumer in build['consumers'].values():
        exe=Path(consumer['executable']['path'])
        if pe_header(exe)['architecture']!='x64' or any(d.lower() not in allowed and not d.lower().startswith('api-ms-win-crt-') for d in consumer['imports']['dependencies']):
            raise RuntimeError('Filesystem consumer import/architecture gate failed')
    exe=Path(build['consumers']['filesystem']['executable']['path'])
    root=PROJECT/'Build/FileSystem/runs'/('run_'+uuid.uuid4().hex)
    root.mkdir(parents=True,exist_ok=False)
    result=run([exe,root],cwd=root,timeout=60)
    log=evidence/'filesystem_execution.log';log.write_bytes(result.stdout+result.stderr);text=read_text(log)
    passed=re.search(r'^PASS\|(\d+)\s*$',text,re.M)
    faults=re.search(r'^FAULTS\|(\d+)\|destination_preserved\|no_open_handles\|no_temporary_files',text,re.M)
    issues=[]
    if result.returncode or not passed or not faults:issues.append('Native filesystem test failed')
    map_exe=Path(build['consumers']['filesystem_map']['executable']['path'])
    map_result=run([map_exe,root],cwd=root,timeout=60)
    map_log=evidence/'map_execution.log';map_log.write_bytes(map_result.stdout+map_result.stderr);map_text=read_text(map_log)
    map_pass=re.search(r'^PASS\|(\d+)\s*$',map_text,re.M)
    map_faults=re.search(r'^MAP_NATIVE_IO\|(\d+)_failure_cases\|file_and_object_preserved\|3_byte_chunks',map_text,re.M)
    if map_result.returncode or not map_pass or not map_faults:issues.append('Actual SDK map native I/O test failed')
    if any(root.glob('.zerosis-txn-*')):issues.append('Uncommitted transaction file remains')
    report={'status':'FILESYSTEM_NATIVE_COMPONENT_PASS' if not issues else 'FILESYSTEM_NATIVE_COMPONENT_FAIL',
            'build':artifact(bp),'verifier':artifact(Path(__file__).resolve()),'execution':{'exit_code':result.returncode,'log':artifact(log),
                'checks':int(passed[1]) if passed else 0,'failure_cases':int(faults[1]) if faults else 0,'directory':str(root)},
            'map_execution':{'exit_code':map_result.returncode,'log':artifact(map_log),'checks':int(map_pass[1]) if map_pass else 0,
                'failure_cases':int(map_faults[1]) if map_faults else 0},
            'outputs':[artifact(p) for p in sorted(root.iterdir()) if p.is_file()],
            'issues':issues,'windows_file_io_executed':True,'original_concrete_filesystem_oracle_available':False,
            'power_loss_recovery_verified':False,'pak_catalog_implemented':False,
            'gamecore_loaded':False,'game_launched':False,'game_multicore_verified':False}
    (evidence/'conformance.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(text+map_text)
    print(report['status'])
    if issues:raise SystemExit(1)
if __name__=='__main__':main()
