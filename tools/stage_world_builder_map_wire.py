"""Stage the independently validated map-file code, not an installable game DLL."""
import json,shutil
from pathlib import Path
from collect_baseline import PROJECT,digest
from world_builder_map_wire_evidence import validate

def files_for_review(build):
    paths=[Path(r['path']) for r in build['sources']+build['objects']]+[Path(build['library']['path'])]
    for consumer in build['consumers'].values():paths += [Path(consumer[k]['path']) for k in ('source','executable','map')]
    paths += [PROJECT/'Tests'/n for n in ('sdk_world_builder_map.cpp','sdk_world_builder_map_file_host.cpp','sdk_world_builder_map_file_host.h','sdk_world_builder_map_state.h')]
    paths += [PROJECT/'Source/Providers/WorldBuilder/SdkWorldBuilderMapIncludes.h']
    paths += [PROJECT/'tools'/(n+'.py') for n in ('probe_world_builder_map','build_world_builder_map_wire','verify_world_builder_map_wire','world_builder_map_wire_evidence','stage_world_builder_map_wire')]
    paths += [PROJECT/'docs/M2_WORLD_BUILDER_MAP_FILES.md']
    # Installed original/copy map bytes and original SDK binaries stay out of Stage.
    # Paths and hashes in reports trace them in this local research workspace.
    for folder in ('evidence/world_builder/map_reference','evidence/world_builder/map_wire'):
        paths += [p for p in (PROJECT/folder).iterdir() if p.is_file() and p.suffix in ('.json','.log') and p.name not in ('allocator_diagnostics.json','corpus_probe.json')]
    return sorted(set(paths))

def main():
    build,result=validate();root=PROJECT/'Stage/WorldBuilderMapFiles';manifest=root/'review_bundle.json'
    prior=json.loads(manifest.read_text(encoding='utf-8')) if manifest.exists() else {'files':[]};known={r['path']:r['sha256'] for r in prior['files']};pairs=[]
    for source in files_for_review(build):
        target=root/source.relative_to(PROJECT);sha=digest(source)
        if target.is_file() and digest(target) not in (sha,known.get(str(target))):raise RuntimeError('Untracked map-file review edit: '+str(target))
        pairs.append((source,target,sha))
    files=[]
    for source,target,sha in pairs:
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
        if digest(source)!=sha or digest(target)!=sha:raise RuntimeError('Map-file review copy differs')
        files.append({'source':str(source),'path':str(target),'sha256':sha})
    report={'status':'WORLD_BUILDER_MAP_FILES_REVIEW_READY','files':files,'installed_maps':128,'recovered_maps':3,
        'sdk_map_object_integration':False,'gamecore_linked':False,'game_launched':False}
    manifest.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps({'status':report['status'],'files':len(files)}))

if __name__=='__main__':main()
