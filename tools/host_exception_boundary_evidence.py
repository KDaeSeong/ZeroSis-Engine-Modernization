"""Bind the foreign-exception lifetime regression to the exact current host source."""
import json,re
from pathlib import Path
from collect_baseline import PROJECT,digest,read_text
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts
from verify_host_exception_boundary import ORIGINAL_CASES,CANDIDATE_CASES

def validate():
    root=PROJECT/'evidence/host_exception_boundary'
    build,result,baseline=[json.loads((root/name).read_text(encoding='utf-8')) for name in ('build_result.json','conformance.json','baseline.json')]
    check_artifacts([build,result,baseline['snapshot']])
    if baseline['source']['sha256']!=baseline['snapshot']['sha256']:
        raise RuntimeError('Foreign-exception baseline differs from the accepted host session')
    accepted=json.loads((root/'accepted_host_build.json').read_text(encoding='utf-8'))
    if digest(root/'accepted_host_build.json')!=baseline['accepted_host_build_sha256']:
        raise RuntimeError('Accepted host build snapshot changed')
    if not any(Path(r['path'])==PROJECT/'Source/Host/GameCoreSession.h' and r['sha256']==baseline['snapshot']['sha256']
               for r in accepted['builds']['host']['compiler_inputs']):
        raise RuntimeError('Original session was not consumed by the accepted host compiler')
    if result['status']!='HOST_EXCEPTION_BOUNDARY_NATIVE_PASS' or result['native_checks']!=1034 or result['withcore_foreign_exception_cases']!=4:
        raise RuntimeError('Foreign-exception native coverage changed')
    expected={(variant+'_'+suffix,scenario) for suffix in ('o2','od')
        for variant,cases in (('original',ORIGINAL_CASES),('candidate',CANDIDATE_CASES)) for scenario in cases}
    if {(r['variant'],r['scenario']) for r in result['runs']}!=expected or len(result['runs'])!=40:
        raise RuntimeError('Foreign-exception scenarios/configurations missing')
    original=[r for r in result['runs'] if r['variant'].startswith('original')]
    candidate=[r for r in result['runs'] if r['variant'].startswith('candidate')]
    if len(original)!=result['original_access_violations'] or len(candidate)!=result['candidate_successes']:
        raise RuntimeError('Foreign-exception result accounting differs')
    if any(r['return_code'] & 0xffffffff != 0xc0000005 or not r['observations']['expected_access_violation'] for r in original):
        raise RuntimeError('Original post-unload access violations not observed')
    if sum(r['observations']['checks'] for r in candidate)!=result['native_checks']:
        raise RuntimeError('Foreign-exception check total differs')
    for row in candidate:
        observed=row['observations']
        if row['return_code'] or observed['foreign_live_at_unload'] or observed['foreign_live_at_exit'] or not observed['normal_restart']:
            raise RuntimeError('Foreign exception survived DLL unload or restart failed')
        if observed['foreign_created']!=observed['foreign_destroyed']:
            raise RuntimeError('Foreign exception lifetime leak')
        if observed['withcore_path']!=row['scenario'].startswith('withcore-'):
            raise RuntimeError('Foreign operation exception scope differs')
    for scenario in CANDIDATE_CASES:
        values=[r['observations'] for r in candidate if r['scenario']==scenario]
        if len(values)!=2 or values[0]!=values[1]:raise RuntimeError('Exception recovery differs by optimization')
    if set(build['builds'])!={'fixture_o2','fixture_od','original_o2','original_od','candidate_o2','candidate_od'}:
        raise RuntimeError('Exception binaries missing')
    for name,item in build['builds'].items():
        if item['binary']['pe']['architecture']!='x64' or item['optimization']!=('/O2' if name.endswith('o2') else '/Od'):
            raise RuntimeError('Wrong exception component compiler target')
        if any('gamecore' in dll.lower() for dll in item['imports']):raise RuntimeError('Exception test imported GameCore')
        if re.search(r'\bwarning\s+[A-Z]+\d+',read_text(Path(item['log']['path']))):raise RuntimeError('Exception compiler warnings')
        if name.startswith('fixture'):
            required=[PROJECT/'Tests/host_exception_fixture.cpp',PROJECT/'Source/LuaBorrowed/ZeroSisLuaBorrowed.h']
        else:
            required=[PROJECT/'Tests/sdk_host_exception_boundary.cpp',PROJECT/'Tests/host_context_fixture.h',
                PROJECT/('Source/HostExceptionBoundary/OriginalGameCoreSession.h' if name.startswith('original') else 'Source/Host/GameCoreSession.h')]
            if name.startswith('candidate'):required.append(PROJECT/'Source/Host/HostFailure.h')
        for source in required:
            if not any(Path(row['path'])==source and row['sha256']==digest(source) for row in item['compiler_inputs']):
                raise RuntimeError('Exception compiler did not consume the exact source: '+str(source))
    if any(report[k] for report in (build,result) for k in ('gamecore_loaded','game_launched')):
        raise RuntimeError('Exception component claims actual GameCore execution')
    entry=dict(name='HostExceptionBoundary',build=artifact(root/'build_result.json'),conformance=artifact(root/'conformance.json'),
        baseline=artifact(root/'baseline.json'),accepted_host_build=artifact(root/'accepted_host_build.json'),
        validator=artifact(Path(__file__).resolve()),scope=result['scope'])
    return build,result,entry

if __name__=='__main__':
    _,result,_=validate();print(json.dumps({'status':'HOST_EXCEPTION_BOUNDARY_EVIDENCE_PASS','checks':result['native_checks']}))
