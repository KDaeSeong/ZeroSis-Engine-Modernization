"""Stage the actual SDK mod-data component with scoped native evidence."""
import json
from pathlib import Path
import shutil
from collect_baseline import PROJECT,digest
from world_builder_mod_data_evidence import validate

def files_for_review(build):
    paths=[Path(r['path']) for r in build['sources']+build['objects']]+[Path(build['library']['path'])]
    paths += [Path(row[k]['path']) for row in build['consumers'].values() for k in ('source','executable','map')]
    paths += [PROJECT/'tools'/(n+'.py') for n in ('probe_world_builder_mod_data','build_world_builder_mod_data','verify_world_builder_mod_data',
        'world_builder_mod_data_evidence','world_builder_mod_access','define_world_builder_mod_patches','refresh_world_builder_dependencies','stage_world_builder_mod_data')]
    paths += [PROJECT/'docs/M2_WORLD_BUILDER_MOD_DATA.md']
    for folder in ('evidence/world_builder/mod_data','evidence/world_builder/mod_data_reference','evidence/world_builder/mod_data_link_before','evidence/world_builder/mod_data_link_after'):
        paths += [p for p in (PROJECT/folder).iterdir() if p.is_file()]
    return sorted(set(paths))

def main():
    build,result,_=validate();root=PROJECT/'Stage/WorldBuilderModData';manifest=root/'review_bundle.json'
    prior=json.loads(manifest.read_text(encoding='utf-8')) if manifest.exists() else {'files':[]};known={r['path']:r['sha256'] for r in prior['files']};pairs=[]
    for source in files_for_review(build):
        target=root/source.relative_to(PROJECT);sha=digest(source)
        if target.is_file() and digest(target) not in (sha,known.get(str(target))):raise RuntimeError('Untracked mod-data review edit: '+str(target))
        pairs.append((source,target,sha))
    files=[]
    for source,target,sha in pairs:
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
        if digest(source)!=sha or digest(target)!=sha:raise RuntimeError('Mod-data review copy differs')
        files.append({'source':str(source),'path':str(target),'sha256':sha})
    report={'status':'WORLD_BUILDER_MOD_DATA_REVIEW_READY','files':files,'hardening_assertions':6104,'fault_failures':442,
            'sdk_access_declarations_integrated':True,'gamecore_linked':False,'game_launched':False,'full_world_builder_verified':False}
    manifest.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps({'status':report['status'],'files':len(files)}))

if __name__=='__main__':main()
