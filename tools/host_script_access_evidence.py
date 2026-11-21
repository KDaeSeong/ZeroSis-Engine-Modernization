"""Validate host script locking against exact baseline/current compiler inputs."""
import json,re
from pathlib import Path
from collect_baseline import PROJECT,digest,read_text
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts
from verify_host_script_access import observations

def validate():
    root=PROJECT/'evidence/host_script_access'
    build,result,baseline=[json.loads((root/name).read_text()) for name in ('build_result.json','conformance.json','baseline.json')]
    check_artifacts([build,result,baseline['accepted_host_build'],[r['snapshot'] for r in baseline['snapshots']]])
    accepted=json.loads(Path(baseline['accepted_host_build']['path']).read_text())
    for row in baseline['snapshots']:
        if row['source']['sha256']!=row['snapshot']['sha256'] or not any(
                Path(item['path'])==Path(row['source']['path']) and item['sha256']==row['source']['sha256']
                for item in accepted['builds']['host']['compiler_inputs']):
            raise RuntimeError('Script access baseline was not consumed by the accepted host')
    expected={'original_o2','original_od','candidate_o2','candidate_od'}
    if set(build['builds'])!=expected or {r['name'] for r in result['runs']}!=expected or len(result['runs'])!=4:
        raise RuntimeError('Missing script access compiler/runtime configuration')
    if (result['status'],result['native_checks'],result['original_accepted_calls'],result['original_unlocked_callbacks'],result['candidate_rejected_calls'])!=('HOST_SCRIPT_ACCESS_NATIVE_PASS',1440,120,36,120):
        raise RuntimeError('Script access result accounting differs')
    candidate=[]
    for run in result['runs']:
        original=run['name'].startswith('original');item=build['builds'][run['name']]
        observed=observations(read_text(Path(run['log']['path'])),original)
        if run['exit_code'] or run['executable']!=artifact(Path(item['executable']['path'])) or observed!=run['observations']:
            raise RuntimeError('Script access executed artifact/observations differ')
        if not original:candidate.append(observed)
        if item['optimization']!=('/O2' if run['name'].endswith('o2') else '/Od') or item['executable']['pe']['architecture']!='x64':
            raise RuntimeError('Wrong script access compiler target')
        response=read_text(Path(item['response']['path'])).splitlines()
        if item['optimization'] not in response or '/DSCRIPT_ACCESS_ORIGINAL='+str(int(original)) not in response:
            raise RuntimeError('Script access compiler flags differ from the reported configuration')
        if any('gamecore' in name.lower() for name in item['imports']['dependencies']):raise RuntimeError('Script test imports GameCore')
        if re.search(r'\bwarning\s+[A-Z]+\d+',read_text(Path(item['log']['path']))):raise RuntimeError('Script access compiler warnings')
        prefix='Source/HostScriptAccess' if original else 'Source/Host'
        required=[PROJECT/prefix/'HostServices.h',PROJECT/prefix/'ScriptSystem.h',PROJECT/'Tests/sdk_host_script_access.cpp',
            PROJECT/'Tests/host_script_utility_fixture.h',PROJECT/'Source/LuaBorrowed/ZeroSisLuaBorrowed.h']
        for source in required:
            if not any(Path(row['path'])==source and row['sha256']==digest(source) for row in item['compiler_inputs']):
                raise RuntimeError('Missing exact script access compiler input: '+str(source))
    if candidate[0]!=candidate[1] or sum(r['checks'] for r in candidate)!=result['native_checks']:
        raise RuntimeError('Script access recovery differs by optimization')
    if any(report[key] for report in (build,result) for key in ('gamecore_loaded','game_launched')) or result['game_multicore_verified']:
        raise RuntimeError('Script access component overclaims runtime scope')
    entry=dict(name='HostScriptAccess',build=artifact(root/'build_result.json'),conformance=artifact(root/'conformance.json'),
        baseline=artifact(root/'baseline.json'),accepted_host_build=baseline['accepted_host_build'],validator=artifact(Path(__file__).resolve()),scope=result['scope'])
    return build,result,entry

if __name__=='__main__':
    _,result,_=validate();print(json.dumps({'status':'HOST_SCRIPT_ACCESS_EVIDENCE_PASS','checks':result['native_checks']}))
