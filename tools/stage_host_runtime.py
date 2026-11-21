"""Stage actual runtime proof without changing the component-only host reports."""
import json,shutil
from pathlib import Path
from collect_baseline import PROJECT,digest
from probe_world_builder import artifact
from host_runtime_evidence import validate

def main():
    result,entry=validate();root=PROJECT/'Stage/NativeHost/RuntimeReview';manifest=root/'review_bundle.json'
    prior=json.loads(manifest.read_text()) if manifest.exists() else {'files':[]}
    known={row['path']:row['sha256'] for row in prior['files']}
    paths={PROJECT/'evidence/host_runtime/conformance.json'}
    for run in result['runs']:
        paths.update(path for path in (PROJECT/'evidence/host_runtime'/run['run_id']).rglob('*') if path.is_file())
    paths.update(PROJECT/path for path in ('tools/run_gamecore_initialization.py','tools/host_runtime_evidence.py',
        'tools/stage_host_runtime.py','tools/refresh_host_runtime.py','docs/M3_ACTUAL_CORE_RUNTIME.md','docs/M3_HOST_GAME_INFO.md'))
    pending=[]
    for source in sorted(paths):
        target=root/source.relative_to(PROJECT);sha=digest(source)
        if target.exists() and digest(target) not in (sha,known.get(str(target))):raise RuntimeError('Untracked actual runtime review edit: '+str(target))
        pending.append((source,target,sha))
    files=[]
    for source,target,sha in pending:
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
        if digest(source)!=sha or digest(target)!=sha:raise RuntimeError('Actual runtime review input changed')
        files.append({'source':str(source),'path':str(target),'sha256':sha})
    report={'status':'ACTUAL_GAMECORE_INITIALIZATION_REVIEW_READY','files':files,'runtime':entry,
        'stager':artifact(Path(__file__).resolve()),'languages':[row['language'] for row in result['runs']],
        'gamecore_initialization_verified':True,'actual_sdk_library_registration_executed':True,
        'new_game_verified':False,'turn_execution_verified':False,'game_multicore_verified':False}
    manifest.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':report['status'],'files':len(files),'languages':report['languages']}))

if __name__=='__main__':main()
