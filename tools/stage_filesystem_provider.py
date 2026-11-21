"""Copy only the reviewed native filesystem component to a separate development Stage."""
import json,shutil
from pathlib import Path
from collect_baseline import PROJECT,digest
from filesystem_evidence import validate,validate_link
from stage_world_builder_map_bridge import artifacts

def files_for_review(build):
    _,conformance,_=validate();link=validate_link()
    paths=set(artifacts(build))|set(artifacts(conformance))|set(artifacts(link))
    paths={p for p in paths if p.is_relative_to(PROJECT)}
    paths.update(PROJECT/p for p in ('tools/filesystem_evidence.py','tools/build_filesystem_provider.py',
        'tools/verify_filesystem_provider.py','tools/probe_filesystem_link.py','tools/stage_filesystem_provider.py',
        'docs/M2_FILESYSTEM_PROVIDER.md','evidence/filesystem/build_result.json','evidence/filesystem/conformance.json',
        'evidence/filesystem/link_trial.json'))
    return sorted(paths)

def main():
    b,c,_=validate();l=validate_link();root=PROJECT/'Stage/FileSystem';files=[]
    for source in files_for_review(b):
        target=root/source.relative_to(PROJECT);target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(source,target)
        if digest(source)!=digest(target):raise RuntimeError('Filesystem stage differs')
        files.append({'source':str(source),'path':str(target),'sha256':digest(target)})
    report={'status':'FILESYSTEM_REVIEW_READY','files':files,'native_checks':c['execution']['checks']+c['map_execution']['checks'],
        'official_gamecore_unresolved':l['official_unresolved_symbols'],'gamecore_loaded':False,'game_launched':False,
        'power_loss_recovery_verified':False,'pak_catalog_implemented':False}
    (root/'review_bundle.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':report['status'],'files':len(files)}))
if __name__=='__main__':main()
