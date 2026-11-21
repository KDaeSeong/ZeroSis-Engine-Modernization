"""Stage verified native map object operations and explicit integration limits."""
import json,shutil
from pathlib import Path
from collect_baseline import PROJECT,digest
from world_builder_map_object_evidence import validate

def files_for_review(b,c):
    reference=json.loads(Path(c['reference_report']['path']).read_text(encoding='utf-8'))
    paths=[Path(r['path']) for r in b['sources']+b['objects']+reference['sources']]+[Path(b['library']['path']),Path(b['generated_fixture']['path'])]
    for consumer in b['consumers'].values():paths += [Path(consumer[k]['path']) for k in ('source','executable','map')]
    paths += [PROJECT/'tools'/(n+'.py') for n in ('world_builder_map_access','probe_world_builder_map_operations','build_world_builder_map_object','verify_world_builder_map_object','probe_world_builder_map_link','world_builder_map_object_evidence','stage_world_builder_map_object')]
    paths += [PROJECT/'docs/M2_WORLD_BUILDER_MAP_OBJECT.md']
    paths += [Path(r['path']) for r in b['generated_headers'] if r['path'].endswith('CvWorldBuilderMapElementAllocator.h')]
    for folder in ('evidence/world_builder/map_operations_reference','evidence/world_builder/map_object'):
        paths += [p for p in (PROJECT/folder).rglob('*') if p.is_file() and p.suffix in ('.json','.log','.bin')]
    return sorted(set(paths))

def main():
    b,c,l=validate();root=PROJECT/'Stage/WorldBuilderMapObject';manifest=root/'review_bundle.json'
    prior=json.loads(manifest.read_text(encoding='utf-8')) if manifest.exists() else {'files':[]};known={r['path']:r['sha256'] for r in prior['files']};pairs=[]
    for source in files_for_review(b,c):
        target=root/source.relative_to(PROJECT);sha=digest(source)
        if target.is_file() and digest(target) not in (sha,known.get(str(target))):raise RuntimeError('Untracked map object review edit: '+str(target))
        pairs.append((source,target,sha))
    files=[]
    for source,target,sha in pairs:
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
        if digest(source)!=sha or digest(target)!=sha:raise RuntimeError('Map object review copy differs')
        files.append({'source':str(source),'path':str(target),'sha256':sha})
    official=json.loads((PROJECT/'evidence/sdk_x64/link_analysis.json').read_text(encoding='utf-8'))
    report={'status':'WORLD_BUILDER_MAP_OBJECT_REVIEW_READY','files':files,'exact_state_records':25,'link_experiment_before':l['before'],'link_experiment_after':l['after'],
        'official_gamecore_link_count':official['linker_unresolved_symbol_total'],'sdk_access_declarations_integrated':b['sdk_access_declarations_integrated'],'file_bridge_implemented':False,'gamecore_linked':False,'game_launched':False}
    manifest.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps({'status':report['status'],'files':len(files)}))

if __name__=='__main__':main()
