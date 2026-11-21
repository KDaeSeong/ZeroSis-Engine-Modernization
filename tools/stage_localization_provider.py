"""Stage the actual Localization component; original DLLs, ICU data and game files are excluded."""
import json
from pathlib import Path
import shutil
from collect_baseline import PROJECT,digest
from localization_provider_evidence import validate
from verify_localization_reference import artifacts


def main():
    build,result,_=validate();root=PROJECT/'Stage/Localization';paths=[]
    paths += [Path(row['path']) for row in build['sources']+build['objects']]
    paths += [Path(build[k]['path']) for k in ('dll','library','map')]
    paths += [Path(t[k]['path']) for t in build['tests'] for k in ('source','executable','map')]
    paths += [Path(row['path']) for row in build['copies'] if row['path'].endswith('.dll')]
    paths += [PROJECT/'tools'/(name+'.py') for name in ('build_localization_provider','verify_localization_provider',
        'localization_provider_evidence','stage_localization_provider','probe_localization_runtime','define_localization_patches','refresh_localization_dependencies')]
    paths += [PROJECT/p for p in ('docs/M2_LOCALIZATION_INTEGRATION.md','Source/ThirdParty/ICU44/original/license.html',
        'Source/ThirdParty/ICU44/source_receipt.json','Source/ThirdParty/ICU44/source_manifest.json','evidence/localization/link_delta.json')]
    for row in artifacts(result):
        path=Path(row['path'])
        if path.is_relative_to(PROJECT) and path.suffix.lower() in ('.json','.log','.txt','.py'):paths.append(path)
    for folder in ('evidence/localization/provider','evidence/localization/runtime_reference','evidence/localization/link_before','evidence/localization/link_after'):
        paths += [p for p in (PROJECT/folder).iterdir() if p.is_file()]
    manifest=root/'review_bundle.json'
    previous=json.loads(manifest.read_text(encoding='utf-8')) if manifest.exists() else {'files':[]}
    known={r['path']:r['sha256'] for r in previous['files']};pairs=[]
    for source in sorted(set(paths)):
        target=root/source.relative_to(PROJECT);sha=digest(source)
        if target.is_file() and digest(target) not in (sha,known.get(str(target))):raise RuntimeError('Untracked Localization stage edit: '+str(target))
        pairs.append((source,target,sha))
    files=[]
    for source,target,sha in pairs:
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
        if digest(source)!=sha or digest(target)!=sha:raise RuntimeError('Localization stage copy differs')
        files.append({'source':str(source),'path':str(target),'sha256':sha})
    report={'status':'LOCALIZATION_PROVIDER_COMPONENT_REVIEW_BUNDLE_READY','files':files,'counts':result['validated_counts'],
        'gamecore_linked':False,'game_launched':False,'scope':'Actual Localization SDK component and component-only observations; full host and game runtime pending'}
    manifest.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps({'status':report['status'],'files':len(files),'counts':report['counts']}))


if __name__=='__main__':main()
