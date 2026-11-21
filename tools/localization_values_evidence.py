"""Read-only integrity and accounting checks for SDK localization value storage."""
import json
from pathlib import Path
import re
from collect_baseline import PROJECT,digest,pe_header,read_text
from verify_localization_reference import artifacts


def validate():
    read=lambda relative:json.loads((PROJECT/relative).read_text(encoding='utf-8'))
    build=read('evidence/localization/values_candidate/build_result.json')
    result=read('evidence/localization/values_candidate/conformance.json')
    reference=read('evidence/localization/values_reference/observations.json')
    grammar=read('evidence/localization/grammar_reference/observations.json')
    baseline=json.loads(Path(reference['baseline']['path']).read_text(encoding='utf-8'))
    for item in artifacts([build,result,reference,grammar,baseline]):
        if digest(Path(item['path']))!=item['sha256']:raise RuntimeError('Localization value evidence differs: '+item['path'])
    if (build['status']!='SDK_LOCALIZATION_VALUES_CANDIDATE_BUILT' or result['status']!='SDK_LOCALIZATION_VALUES_COMPONENT_PASS'
        or reference['status']!='ORIGINAL_LOCALIZATION_VALUES_OBSERVATIONS_RECORDED'
        or grammar['status']!='ORIGINAL_LOCALIZATION_GRAMMAR_OBSERVATIONS_RECORDED'
        or not result['exact_shared_trace'] or Path(result['difference']['path']).stat().st_size
        or result['independent_copies']!=4096 or len(result['executions'])!=3 or len(reference['runs'])!=1 or len(grammar['runs'])!=4
        or any(row['exit_code'] for row in result['executions']+reference['runs']+grammar['runs'])
        or any(report['game_launched'] or report['gamecore_loaded'] for report in (build,result,reference,grammar))):
        raise RuntimeError('Localization value status or scope differs')
    original=read_text(Path(reference['runs'][0]['log']['path'])).splitlines()
    candidate=read_text(Path(result['executions'][0]['log']['path'])).splitlines()
    if original!=candidate or len(original)!=result['original_records'] or len(original)!=50:
        raise RuntimeError('Localization SharedString actual comparison differs')
    for execution in result['executions']:
        lines=read_text(Path(execution['log']['path'])).splitlines()
        if not lines or lines[-1]!='PASS|'+str(execution['checks']):raise RuntimeError('Localization value check accounting differs')
    boundary=read_text(Path(result['executions'][2]['log']['path']))
    if 'BOUNDARIES|PASS|independent_copies=4096' not in boundary:raise RuntimeError('SharedString copy concurrency result absent')
    for key in ('dll','executable'):
        if pe_header(Path(build[key]['path']))['architecture']!='x64':raise RuntimeError('Localization values are not x64')
    if pe_header(Path(reference['executable']['path']))['architecture']!='x86':raise RuntimeError('Localization value reference is not x86')
    with Path(build['object']['path']).open('rb') as stream:
        if int.from_bytes(stream.read(2),'little')!=0x8664:raise RuntimeError('Localization values production object is not AMD64')
    linkmap=read_text(Path(build['map']['path']))
    if len(result['production_proof'])!=1 or result['production_proof'][0] not in linkmap:raise RuntimeError('SharedString production link proof differs')
    if any(re.search(r'\bwarning\s+[A-Z]+\d+',read_text(Path(item['path'])),re.I) for item in build['logs']):
        raise RuntimeError('Localization value candidate emitted warnings')
    return build,result,grammar


if __name__=='__main__':
    build,result,grammar=validate();print(json.dumps({'shared_records':result['original_records'],'independent_copies':result['independent_copies'],'grammar_modes':len(grammar['runs'])}))
