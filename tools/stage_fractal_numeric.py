"""Stage reviewed Fractal numeric boundaries and native comparison evidence."""
import json,shutil
from pathlib import Path
from collect_baseline import PROJECT,digest
from fractal_numeric_evidence import validate
from stage_world_builder_map_bridge import artifacts


def files_for_review():
    build,result,entry=validate();paths=set(artifacts([build,result,entry]))
    paths.update(PROJECT/p for p in ('tools/define_fractal_numeric_patches.py','tools/build_fractal_numeric.py',
        'tools/verify_fractal_numeric.py','tools/fractal_numeric_evidence.py','tools/stage_fractal_numeric.py',
        'tools/refresh_fractal_numeric_integration.py','tools/refresh_lua_fractal_integration.py','tools/refresh_lua_registration_integration.py',
        'tools/refresh_lua_enum_integration.py','docs/M3_FRACTAL_NUMERICS.md'))
    return sorted(p for p in paths if p.is_relative_to(PROJECT))


def main():
    _,result,_=validate();root=PROJECT/'Stage/FractalNumeric';manifest=root/'review_bundle.json'
    prior=json.loads(manifest.read_text(encoding='utf-8')) if manifest.exists() else {'files':[]}
    known={r['path']:r['sha256'] for r in prior['files']};copies=[]
    for source in files_for_review():
        target=root/source.relative_to(PROJECT);sha=digest(source)
        if target.exists() and digest(target) not in (sha,known.get(str(target))):raise RuntimeError('Untracked Fractal review edit: '+str(target))
        copies.append((source,target,sha))
    files=[]
    for source,target,sha in copies:
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
        if digest(source)!=sha or digest(target)!=sha:raise RuntimeError('Fractal review copy changed')
        files.append({'source':str(source),'path':str(target),'sha256':sha})
    report={'status':'FRACTAL_NUMERIC_CALLERS_REVIEW_READY','files':files,'native_checks':result['native_checks'],
        'compiled_sdk_objects':161,'sdk_callers_compiled':True,'gamecore_loaded':False,'game_launched':False,
        'whole_game_map_generation_verified':False,'retry_failure_rolls_back_rng':False,'borrowed_game_object_lifetimes_verified':False}
    manifest.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':report['status'],'files':len(files),'checks':report['native_checks']}))


if __name__=='__main__':main()
