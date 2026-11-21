"""Run audited borrowed-reference candidates without loading GameCore."""
import json
from pathlib import Path
from collect_baseline import PROJECT
from native_build import run
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts
from build_lua_borrowed import fixture_text


def main():
    root = PROJECT/'evidence/lua_borrowed'
    build_path = root/'build_result.json'
    report = json.loads(build_path.read_text(encoding='utf-8'))
    check_artifacts(report)
    fixture, _, _ = fixture_text()
    if Path(report['fixture']['path']).read_text(encoding='utf-8') != fixture:
        raise RuntimeError('Borrowed test fixture changed')
    executions = []
    total = 0
    for name, value in report['builds'].items():
        allowed = {'kernel32.dll', 'msvcp140.dll', 'vcruntime140.dll', 'vcruntime140_1.dll'}
        if any(dll.lower() not in allowed and not dll.lower().startswith('api-ms-win-crt-') for dll in value['imports']):
            raise RuntimeError('Unaudited runtime import')
        exe = Path(value['executable']['path'])
        result = run([exe], cwd=exe.parent, timeout=60)
        log = root/(name+'_execution.log')
        log.write_bytes(result.stdout+result.stderr)
        if result.returncode:
            raise RuntimeError(name+': '+(result.stdout+result.stderr).decode('utf-8', errors='replace'))
        data = json.loads(result.stdout)
        candidate = name.startswith('candidate')
        expected = dict(candidate=candidate, forged_accepted=0 if candidate else 3,
            stale_accepted=0 if candidate else 1, reentrant_rejections=5 if candidate else 1, tracked_at_exit=0,
            native_proxy_kinds=4, unit_notifications=1, cross_translation_unit_registry=True,
            container_operations=12, container_blocks_at_exit=0, deal_copy_cases=4, deal_self_copy_losses=0 if candidate else 3)
        if any(data.get(k) != v for k, v in expected.items()) or data['allocation_failures'] <= 0:
            raise RuntimeError('Borrowed outcome mismatch: '+str(data))
        if candidate and data['partial_registrations'] or not candidate and data['partial_registrations'] <= 0:
            raise RuntimeError('Method-table recovery mismatch: '+str(data))
        if (data['is_none_incorrect'] == 0) != candidate or candidate and data['is_none_errors']:
            raise RuntimeError('IsNone outcome mismatch: '+str(data))
        executions.append(dict(variant=name, executable=value['executable'], log=artifact(log),
            return_code=result.returncode, results=data))
        total += data['checks']
    integrated=report['candidate_matches_generated_sdk']
    result = dict(status='SDK_LUA_BORROWED_NATIVE_PASS' if integrated else 'LUA_BORROWED_CANDIDATE_COMPONENT_PASS_NOT_INTEGRATED', build=artifact(build_path),
        verifier=artifact(Path(__file__).resolve()), native_checks=total, runs=executions,
        gamecore_loaded=False, game_launched=False, actual_owner_hooks_integrated=integrated,
        native_proxy_bodies_executed=True, unit_destructor_body_with_instrumented_services_executed=True,
        sdk_container_operations_with_instrumented_elements_executed=True,
        actual_gameplay_owner_lifecycle_executed=False,
        scope=report['scope'])
    (root/'conformance.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(dict(status=result['status'], checks=total, processes=len(executions))))


if __name__ == '__main__':
    main()
