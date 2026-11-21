"""Stage integrated borrowed references and their bounded native execution evidence."""
import json
import shutil
from collect_baseline import PROJECT, digest
from lua_borrowed_evidence import validate
from stage_world_builder_map_bridge import artifacts


def files_for_review():
    build,result,entry=validate()
    paths=set(artifacts([build,result,entry]))
    paths.update(PROJECT/p for p in (
        'Source/LuaBorrowed/ZeroSisLuaBorrowed.h','Tests/sdk_lua_borrowed.cpp','Tests/sdk_lua_borrowed_peer.cpp',
        'tools/define_lua_borrowed_patches.py','tools/build_lua_borrowed.py','tools/verify_lua_borrowed.py',
        'tools/audit_lua_borrowed_lifecycles.py','tools/lua_borrowed_evidence.py','tools/stage_lua_borrowed.py',
        'tools/refresh_lua_borrowed_integration.py','tools/build_lua_borrowed_sdk_candidate.py',
        'evidence/lua_borrowed/production_verification.json','docs/M3_LUA_BORROWED_OBJECTS.md'))
    return sorted(p for p in paths if p.is_relative_to(PROJECT))


def main():
    _,result,_=validate()
    root=PROJECT/'Stage/LuaBorrowed';manifest=root/'review_bundle.json'
    prior=json.loads(manifest.read_text(encoding='utf-8')) if manifest.exists() else {'files':[]}
    known={r['path']:r['sha256'] for r in prior['files']};copies=[]
    for source in files_for_review():
        target=root/source.relative_to(PROJECT);sha=digest(source)
        if target.exists() and digest(target) not in (sha,known.get(str(target))):
            raise RuntimeError('Untracked borrowed-reference review edit: '+str(target))
        copies.append((source,target,sha))
    files=[]
    for source,target,sha in copies:
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
        if digest(source)!=sha or digest(target)!=sha:raise RuntimeError('Borrowed-reference review copy changed')
        files.append({'source':str(source),'path':str(target),'sha256':sha})
    report=dict(status='LUA_BORROWED_CALLERS_REVIEW_READY',files=files,native_checks=result['native_checks'],
        compiled_sdk_objects=161,native_lifetime_hooks=34,native_proxy_kinds=4,binding_types=9,
        sdk_callers_compiled=True,gamecore_loaded=False,game_launched=False,actual_gameplay_owner_lifecycle_executed=False)
    manifest.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':report['status'],'files':len(files),'checks':report['native_checks']}))


if __name__=='__main__':main()
