"""Stage the verified SDK type/group provider; no original SDK archives or game DLLs."""
import json
from pathlib import Path
import shutil
from collect_baseline import PROJECT,digest
from world_builder_types_evidence import validate

def files_for_review(build):
    paths=[Path(row['path']) for row in build['sources']+build['objects']]+[Path(build['library']['path'])]
    paths += [Path(row[k]['path']) for row in build['consumers'].values() for k in ('source','executable','map')]
    paths += [PROJECT/'tools'/(name+'.py') for name in ('probe_world_builder','build_world_builder_types','verify_world_builder_types','world_builder_types_evidence','stage_world_builder_types')]
    paths += [PROJECT/'docs/M2_WORLD_BUILDER_PROVIDER.md']
    for folder in ('evidence/world_builder/reference','evidence/world_builder/types','evidence/world_builder/link_before','evidence/world_builder/link_after'):
        paths += [p for p in (PROJECT/folder).iterdir() if p.is_file()]
    return sorted(set(paths))

def main():
    build,result,_=validate();root=PROJECT/'Stage/WorldBuilderTypes';manifest=root/'review_bundle.json'
    previous=json.loads(manifest.read_text(encoding='utf-8')) if manifest.exists() else {'files':[]}
    known={r['path']:r['sha256'] for r in previous['files']};pairs=[]
    for source in files_for_review(build):
        target=root/source.relative_to(PROJECT);sha=digest(source)
        if target.is_file() and digest(target) not in (sha,known.get(str(target))):raise RuntimeError('Untracked stage edit: '+str(target))
        pairs.append((source,target,sha))
    files=[]
    for source,target,sha in pairs:
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
        if digest(source)!=sha or digest(target)!=sha:raise RuntimeError('WorldBuilder review copy differs')
        files.append({'source':str(source),'path':str(target),'sha256':sha})
    report={'status':'WORLD_BUILDER_TYPES_REVIEW_READY','files':files,'comparison_modes':len(result['comparisons']),
            'hardening_assertions':626,'gamecore_linked':False,'game_launched':False,'full_world_builder_verified':False}
    manifest.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps({'status':report['status'],'files':len(files)}))

if __name__=='__main__':main()
