"""Validate the real Localization DLL, original traces, boundaries and provenance without execution."""
import json
from pathlib import Path
import re
from collect_baseline import PROJECT, digest, pe_header, read_text
from build_icu44 import artifact
from build_sdk_x64 import object_machine
from verify_localization_reference import artifacts
from verify_localization_provider import observable, expected_adjustments


def validate(build_path=None):
    build_path=Path(build_path or PROJECT/'evidence/localization/provider/build_result.json').resolve()
    result_path=PROJECT/'evidence/localization/provider/conformance.json'
    build=json.loads(build_path.read_text(encoding='utf-8'));result=json.loads(result_path.read_text(encoding='utf-8'))
    from database_evidence import validate as database_validate
    _,_,database=database_validate(PROJECT/'evidence/database/candidate/build_result.json')
    from localization_icu_evidence import validate as icu_validate
    icu_validate()
    references=[json.loads(Path(row['path']).read_text(encoding='utf-8')) for row in result['references'].values()]
    dependencies=[json.loads(Path(row['path']).read_text(encoding='utf-8')) for row in build['dependencies'].values()]
    for row in artifacts([build,result,references,dependencies]):
        path=Path(row['path'])
        if not path.is_file() or digest(path)!=row['sha256']:raise RuntimeError('Localization provider artifact changed: '+str(path))
    if (build['status']!='SDK_LOCALIZATION_X64_CANDIDATE_BUILT' or result['status']!='SDK_LOCALIZATION_COMPONENT_PASS'
        or result['build']!=artifact(build_path) or result['differences'] or len(result['executions'])!=37
        or len(result['hardening'])!=1 or result['hardening'][0]['checks']!=74
        or sum(len(row['adjustments']) for row in result['intentional_differences'])!=8
        or sum(row['checks'] for row in result['executions'])!=1987
        or build['dependencies']['database']!=database['build_report']
        or any(r.get('game_launched') or r.get('gamecore_loaded') for r in [build,result,*references,*dependencies])):
        raise RuntimeError('Localization provider scope or accounting differs')
    exact_records=0;rule_values=0
    for row in result['executions']:
        before=observable(Path(row['original']['path']));after=observable(Path(row['log']['path']))
        expected,adjustments=expected_adjustments(row['kind'],row['mode'],before)
        if (row['exit_code'] or not row['checks'] or not after or after[-1]!='PASS|'+str(row['checks'])
            or expected!=after or adjustments!=row['intentional_adjustments']
            or (before==after)!=row['exact_observables'] or len(before)!=row['original_records']
            or len(after)!=row['candidate_records'] or not row['matches_required_observables']):
            raise RuntimeError('Localization actual trace/accounting differs: '+row['mode'])
        exact_records+=len(before)-len(adjustments)
        if row['mode'].startswith('rule_'):
            rule_values+=sum(len(re.findall(r'\|-?\d+:\d+',line)) for line in before)
    hardening=result['hardening'][0];output=read_text(Path(hardening['log']['path'])).splitlines()
    if hardening['exit_code'] or output[-1]!='PASS|74' or not all(marker in output for marker in hardening['markers']):
        raise RuntimeError('Localization hardening log differs')
    for item in [build['dll']]+[test['executable'] for test in build['tests']]:
        if pe_header(Path(item['path']))['architecture']!='x64':raise RuntimeError('Localization candidate architecture differs')
    if len(build['objects'])!=3 or any(object_machine(Path(o['path']))!=o or o['architecture']!='x64' for o in build['objects']):
        raise RuntimeError('Localization production objects differ')
    for reference in references:
        executable=reference.get('executable')
        if executable and pe_header(Path(executable['path']))['architecture']!='x86':raise RuntimeError('Localization reference architecture differs')
    if any(re.search(r'\bwarning\s+[A-Z]+\d+',read_text(Path(row['path'])),re.I) for row in build['logs']):
        raise RuntimeError('Localization candidate compiler warnings changed')
    linkmap=read_text(Path(build['map']['path']))
    for lines in result['production_proof'].values():
        if not lines or any(line not in linkmap or 'SdkLocalization' not in line for line in lines):
            raise RuntimeError('Localization implementation map provenance differs')
    result['validated_counts']={'comparison_runs':37,'native_assertions':1987,'hardening_assertions':74,
        'original_records_unchanged':exact_records,'plural_rule_values':rule_values,'independent_calls':1024,'intentional_adjusted_records':8}
    return build,result,{'name':'Localization','library':build['library'],'dll':build['dll'],
        'build_report':artifact(build_path),'conformance':artifact(result_path),'runtime':'/MD',
        'scope':'SDK_STRING_DICTIONARY_AND_GRAMMAR_COMPONENT_NOT_FULL_LOCALIZATION_API_OR_GAME_RUNTIME'}


if __name__=='__main__':
    _,result,_=validate();print(json.dumps(result['validated_counts']))
