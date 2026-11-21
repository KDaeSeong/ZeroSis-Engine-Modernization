"""Stage SDK localization value storage and original grammar observations for review."""
import json
from pathlib import Path
import shutil
from collect_baseline import PROJECT,digest
from localization_values_evidence import validate


def main():
    build,result,grammar=validate();root=PROJECT/'Stage/LocalizationValues';files=[]
    paths=[Path(row['path']) for row in build['sources'] if Path(row['path']).is_relative_to(PROJECT/'Source/Providers')]
    paths += [Path(build[name]['path']) for name in ('dll','library','object')]
    paths += [PROJECT/'Tests'/name for name in ('sdk_localization_values.cpp','sdk_localization_grammar.cpp','sdk_localization_trace.cpp','localization_numeric_cases.h')]
    paths += [PROJECT/'tools'/(name+'.py') for name in ('probe_localization_grammar','build_localization_values','verify_localization_values','localization_values_evidence','stage_localization_values')]
    paths += [PROJECT/'docs/M2_LOCALIZATION_VALUES.md']
    for folder in ('evidence/localization/values_candidate','evidence/localization/values_reference','evidence/localization/grammar_reference'):
        paths += [path for path in (PROJECT/folder).iterdir() if path.is_file()]
    for source in sorted(set(paths)):
        target=root/source.relative_to(PROJECT);target.parent.mkdir(parents=True,exist_ok=True);sha=digest(source);shutil.copyfile(source,target)
        if digest(source)!=sha or digest(target)!=sha:raise RuntimeError('Localization value stage differs')
        files.append({'source':str(source),'path':str(target),'sha256':sha})
    report={'status':'LOCALIZATION_VALUES_REVIEW_BUNDLE_READY','files':files,'shared_records':result['original_records'],'independent_copies':result['independent_copies'],
            'gamecore_linked':False,'game_launched':False,'scope':'Shared value storage and original grammar observations; full Localization implementation pending'}
    (root/'review_bundle.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps({'status':report['status'],'files':len(files)}))


if __name__=='__main__':main()
