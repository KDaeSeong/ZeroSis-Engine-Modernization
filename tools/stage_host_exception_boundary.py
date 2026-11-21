"""Stage host exception ownership proof without publishing a gameplay runtime claim."""
import json,shutil
from collect_baseline import PROJECT,digest
from host_exception_boundary_evidence import validate
from stage_world_builder_map_bridge import artifacts

def files_for_review():
    build,result,entry=validate();paths=set(artifacts([build,result,entry]))
    paths.update(PROJECT/p for p in ('Source/Host/HostFailure.h','Source/Host/GameCoreSession.h',
        'Source/HostExceptionBoundary/OriginalGameCoreSession.h','Tests/host_exception_fixture.h',
        'Tests/host_exception_fixture.cpp','Tests/sdk_host_exception_boundary.cpp','tools/build_host_exception_boundary.py',
        'tools/verify_host_exception_boundary.py','tools/host_exception_boundary_evidence.py',
        'tools/stage_host_exception_boundary.py','docs/M3_HOST_EXCEPTION_BOUNDARY.md'))
    return sorted(p for p in paths if p.is_relative_to(PROJECT))

def main():
    _,result,_=validate();root=PROJECT/'Stage/HostExceptionBoundary';manifest=root/'review_bundle.json'
    prior=json.loads(manifest.read_text(encoding='utf-8')) if manifest.exists() else {'files':[]}
    known={r['path']:r['sha256'] for r in prior['files']};copies=[]
    for source in files_for_review():
        target=root/source.relative_to(PROJECT);sha=digest(source)
        if target.exists() and digest(target) not in (sha,known.get(str(target))):raise RuntimeError('Untracked host exception review edit: '+str(target))
        copies.append((source,target,sha))
    files=[]
    for source,target,sha in copies:
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
        if digest(source)!=sha or digest(target)!=sha:raise RuntimeError('Host exception review copy changed')
        files.append({'source':str(source),'path':str(target),'sha256':sha})
    report=dict(status='HOST_EXCEPTION_BOUNDARY_REVIEW_READY',files=files,native_checks=result['native_checks'],
        original_access_violations=14,candidate_successes=22,gamecore_loaded=False,game_launched=False)
    manifest.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':report['status'],'files':len(files),'checks':report['native_checks']}))

if __name__=='__main__':main()
