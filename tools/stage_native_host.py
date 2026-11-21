"""Stage native host review sources/evidence next to its isolated runtime bundle."""
import json,shutil
from pathlib import Path
from collect_baseline import PROJECT,digest
from native_host_evidence import validate
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts


def main():
    build,result,bundle,_=validate()
    root=PROJECT/'Stage/NativeHost';review=root/'Review';manifest=root/'review_bundle.json'
    previous=json.loads(manifest.read_text()) if manifest.exists() else {'files':[]}
    known={r['path']:r['sha256'] for r in previous['files']}
    paths=set((PROJECT/'Source/Host').glob('*'))
    paths.update((PROJECT/'Source/Assets/Audio').glob('*.xml'))
    paths.update((PROJECT/'Source/Assets/Scripts').rglob('*.lua'))
    paths.update(PROJECT/p for p in ('Tests/sdk_native_host.cpp','Tests/sdk_host_map_audio.cpp','Tests/sdk_host_script.cpp','Tests/sdk_host_script_assets.cpp','Tests/host_context_fixture.h','Tests/host_script_utility_fixture.h','Source/Porting/ZeroSisHostBinding.h',
        'tools/generate_host_interfaces.py','tools/build_native_host.py','tools/prepare_native_host_bundle.py',
        'tools/verify_native_host.py','tools/native_host_evidence.py','tools/prepare_host_audio_catalog.py','tools/prepare_host_script_catalog.py','tools/audit_host_script_bindings.py',
        'tools/audit_native_host_services.py','tools/stage_native_host.py','docs/M3_NATIVE_HOST.md','docs/M3_HOST_MAP_AUDIO.md','docs/M3_HOST_SCRIPT.md','docs/M3_HOST_SCRIPT_ASSETS.md'))
    paths.update(PROJECT/p for p in ('docs/M3_HOST_EXCEPTION_BOUNDARY.md','tools/host_exception_boundary_evidence.py',
        'Stage/HostExceptionBoundary/review_bundle.json'))
    from host_script_access_evidence import validate as validate_script_access
    access_build,access_result,access_entry=validate_script_access()
    paths.update((PROJECT/'Source/HostScriptAccess').glob('*.h'))
    paths.update(PROJECT/p for p in ('Tests/sdk_host_script_access.cpp','Source/LuaBorrowed/ZeroSisLuaBorrowed.h',
        'tools/build_host_script_access.py','tools/verify_host_script_access.py','tools/host_script_access_evidence.py','docs/M3_HOST_SCRIPT_ACCESS.md'))
    # Historical exploration reports keep their original meaning; stage the current proof only.
    paths.update(PROJECT/'evidence/host_script_access'/name for name in ('baseline.json','accepted_host_build.json','build_result.json','conformance.json'))
    paths.update(Path(row['log']['path']) for row in access_result['runs'])
    from host_game_info_evidence import ROOT as game_info_root,validate as validate_game_info
    game_info,game_info_entry=validate_game_info()
    paths.update(PROJECT/p for p in ('Tests/sdk_host_game_info.cpp','tools/host_game_info_evidence.py','docs/M3_HOST_GAME_INFO.md'))
    paths.update(game_info_root.glob('*.json'));paths.update(game_info_root.glob('*.log'))
    game_info_build=json.loads((game_info_root/'build_result.json').read_text())
    for item in game_info_build['builds'].values():
        paths.update(Path(item[key]['path']) for key in ('executable','log','dependency_report','response','map'))
        paths.add(Path(item['imports']['log']['path']))
    for item in access_build['builds'].values():
        paths.update(Path(item[key]['path']) for key in ('executable','log','dependency_report','response','map'))
        paths.add(Path(item['imports']['log']['path']))
    paths.update((PROJECT/'evidence/host').glob('*.json'))
    paths.update(Path(r['log']['path']) for r in result['runs'])
    for item in build['builds'].values():
        paths.update(Path(item[k]['path']) for k in ('log','dependency_report','response','map'))
        paths.add(Path(item['imports']['log']['path']))
    copies=[]
    for source in sorted(p for p in paths if p.is_file()):
        target=review/source.relative_to(PROJECT);sha=digest(source)
        if target.exists() and digest(target) not in (sha,known.get(str(target))):raise RuntimeError('Untracked native host review edit: '+str(target))
        copies.append((source,target,sha))
    rows=[]
    for source,target,sha in copies:
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
        if digest(source)!=sha or digest(target)!=sha:raise RuntimeError('Native host review copy changed')
        rows.append({'source':str(source),'path':str(target),'sha256':sha})
    check_artifacts(bundle['files'])
    report={'status':'NATIVE_HOST_REVIEW_READY_NOT_GAME_RUNTIME','files':rows,'runtime_bundle':artifact(PROJECT/'evidence/host/bundle.json'),
            'conformance':artifact(PROJECT/'evidence/host/conformance.json'),'stager':artifact(Path(__file__).resolve()),
            'native_checks':result['native_checks'],'gamecore_loaded':False,'game_launched':False,'game_multicore_verified':False}
    report['host_exception_boundary_review']=artifact(PROJECT/'Stage/HostExceptionBoundary/review_bundle.json')
    report['host_script_access']=access_entry
    report['host_script_access_native_checks']=access_result['native_checks']
    report['host_game_info']=game_info_entry
    report['host_game_info_native_checks']=game_info['native_checks']
    manifest.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':report['status'],'files':len(rows),'native_checks':report['native_checks']}))


if __name__=='__main__':main()
