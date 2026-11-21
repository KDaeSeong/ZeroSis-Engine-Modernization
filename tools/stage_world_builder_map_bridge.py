"""Publish a review bundle of the isolated SDK map bridge, never to the game."""
import json,shutil
from pathlib import Path
from collect_baseline import PROJECT,digest
from world_builder_map_bridge_evidence import validate


def artifacts(value):
    if isinstance(value,dict):
        if isinstance(value.get('path'),str) and 'sha256' in value:yield Path(value['path'])
        for child in value.values():yield from artifacts(child)
    elif isinstance(value,list):
        for child in value:yield from artifacts(child)


def main():
    b,c,l=validate();root=PROJECT/'Stage/WorldBuilderMapBridge';manifest=root/'review_bundle.json'
    reference=json.loads(Path(c['reference_build']['path']).read_text(encoding='utf-8'))
    paths=set(artifacts(c))|set(artifacts(l))
    # The link trial references 161 accepted GameCore objects and existing libs.
    # Their hashes remain in the report; this component bundle does not copy them.
    paths={p for p in paths if p.is_relative_to(PROJECT) and not p.is_relative_to(PROJECT/'Build/SDK_x64')}
    paths.update(Path(r['path']) for r in b['sources']+b['objects']+b['logs']+b['responses'])
    paths.add(Path(b['library']['path']));paths.add(Path(b['generated_fixture']['path']))
    paths.update(artifacts({k:reference[k] for k in ('sources','executable','map','imports','response','build_log')}))
    for consumer in b['consumers'].values():paths.update(artifacts(consumer))
    paths.update(Path(r['path']) for r in b['generated_headers'] if Path(r['path']).name in ('CvWorldBuilderMap.h','CvWorldBuilderMapElementAllocator.h','CvWorldBuilderMapTypeGroup.h','CvWorldBuilderMapTypeDesc.h','FString.h'))
    paths.update(PROJECT/'tools'/(n+'.py') for n in ('world_builder_map_access','world_builder_map_bridge_access','define_world_builder_map_patches','build_world_builder_map_bridge','build_world_builder_map_bridge_reference','verify_world_builder_map_bridge','probe_world_builder_map_bridge_link','world_builder_map_bridge_evidence','stage_world_builder_map_bridge'))
    paths.add(PROJECT/'docs/M2_WORLD_BUILDER_MAP_BRIDGE.md');paths.add(PROJECT/'evidence/world_builder/map_bridge/link_trial.json')
    paths.update(PROJECT/p for p in ('docs/M2_WORLD_BUILDER_MAP_INTEGRATION.md','tools/verify_world_builder_map_integration.py','evidence/world_builder/map_bridge/sdk_integration.json'))
    prior=json.loads(manifest.read_text(encoding='utf-8')) if manifest.exists() else {'files':[]};known={r['path']:r['sha256'] for r in prior['files']};pairs=[]
    for source in sorted(paths):
        target=root/source.relative_to(PROJECT);sha=digest(source)
        if target.is_file() and digest(target) not in (sha,known.get(str(target))):raise RuntimeError('Untracked bridge review edit: '+str(target))
        pairs.append((source,target,sha))
    files=[]
    for source,target,sha in pairs:
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
        if digest(source)!=sha or digest(target)!=sha:raise RuntimeError('Map bridge review copy changed')
        files.append({'source':str(source),'path':str(target),'sha256':sha})
    official=json.loads((PROJECT/'evidence/sdk_x64/link_analysis.json').read_text(encoding='utf-8'))
    report={'status':'WORLD_BUILDER_MAP_BRIDGE_REVIEW_READY','files':files,'corpus_inputs':130,'exact_original_observed_states':129,'explicit_legacy9_correction':1,'original_rereads':130,
        'link_experiment_before':l['before'],'link_experiment_after':l['after'],'official_gamecore_link_count':official['linker_unresolved_symbol_total'],'sdk_access_declarations_integrated':b['sdk_access_declarations_integrated'],
        'sdk_map_file_object_integration':True,'production_filesystem_implemented':False,'atomic_file_replace_verified':False,'gamecore_linked':False,'game_launched':False}
    manifest.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps({'status':report['status'],'files':len(files)}))


if __name__=='__main__':main()
