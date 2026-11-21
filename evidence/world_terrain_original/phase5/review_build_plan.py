"""Review the exact changed scope and compiler-only plan with retained saves."""
import gzip, json, sys
from pathlib import Path
sys.dont_write_bytecode = True
STAGE = Path(__file__).absolute().parent
PROJECT = STAGE.parents[2]
sys.path.insert(0, str(PROJECT / 'tools'))
import build_exit_confirm_host as common


def main():
    path = STAGE / 'host_build/plan.json'
    plan = json.loads(path.read_text('utf8'))
    parent = json.loads(Path(plan['parent']['path']).read_text('utf8'))
    old = {common.key(row['path']): row for row in parent['current_source_inputs']}
    new = {common.key(row['path']): row for row in plan['current_source_inputs']}
    changed = [new[key]['path'] for key in new.keys() & old.keys()
               if (new[key]['bytes'], new[key]['sha256']) != (old[key]['bytes'], old[key]['sha256'])]
    expected = [str(PROJECT / name) for name in (
        'Source/Presentation/WorldTerrainRenderer.cpp', 'Source/Presentation/WorldViewRenderer.h',
        'Source/Presentation/WorldTerrainReuse.h', 'Source/Presentation/OriginalTerrainShader.h',
        'Source/Presentation/OriginalTerrainGpu.inc', 'Source/Presentation/OriginalTerrainGpuTypes.inc',
        'Source/Presentation/OriginalWaterSurfaceShader.h', 'Source/Presentation/OriginalWaterSurfaceGpu.inc',
        'Source/Presentation/OriginalWaterSurfaceGpuTypes.inc', 'Source/Presentation/OriginalWaterSurfaceTargets.inc',
        'Source/Presentation/OriginalWaterReflection.inc', 'Source/Host/InteractiveGameLoop.h',
        'tools/build_menu_suite_host.py', 'tools/attest_prepared_menu_host.py')]
    baseline = json.loads(gzip.decompress((STAGE / 'protection_before.json.gz').read_bytes()))
    runtime = PROJECT / 'Build/InteractiveGameRuntime/20261115T011241Z_4c8fd55e99db'
    user = PROJECT / 'Build/InteractiveGameRuntime/20261108T003146Z_40a8030edf08'
    must = [row for row in baseline['protected_artifacts']
            if Path(row['path']).is_relative_to(runtime) or Path(row['path']).is_relative_to(user)]
    protected = {common.key(row['path']): row for row in plan['protected_artifacts']}
    same = all(common.key(row['path']) in protected and all(
        protected[common.key(row['path'])][key] == row[key]
        for key in ('bytes', 'sha256', 'file_identity', 'mtime_ns', 'file_attributes')) for row in must)
    checks = dict(
        parent_latest=parent['build_id'] == '20261115T055523Z_51738aa69964' and
                      plan['parent']['sha256'] == 'bf4d7e918dd73ed9c610593d10f27d9d8425703585caec48769322e8655d6c6a',
        exact_changed_scope={common.key(name) for name in changed} == {common.key(name) for name in expected},
        no_removed_inputs=not (old.keys() - new.keys()), current_and_user_runtime_preserved=same,
        no_toolchain_change=plan['system_tool_selection'] is None and plan['toolchain_inputs'] == parent['toolchain_inputs'],
        offline_only=all(plan[key] is False for key in ('host_sdk_clr_hwnd_gpu_or_game_execution_allowed',
            'full_ui_preparer_main_allowed', 'default_promotion_allowed', 'automatic_retry_allowed', 'full_engine_goal_complete')),
        exact12compiler_phases=len(plan['direct_child_phases']) == 12, catalog74=plan['catalog_count'] == 74,
        fixed_gate=plan['menu_gate']['sha256'] == '587d564e7df4e59fca5356e6f94b15b4bc3aba4a36fed11ba150ac355af08067')
    result = dict(status='PASS' if all(checks.values()) else 'FAIL', checks=checks, plan=common.artifact(path),
                  changed_inputs=changed, current_source_inputs=len(new), protected_artifacts=len(protected),
                  protected_runtime_files=len(must), native_execution=False)
    with (STAGE / 'host_build/plan_review.json').open('x', encoding='utf8') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    assert all(checks.values()), checks
    print(json.dumps(dict(status=result['status'], plan_sha256=result['plan']['sha256'], current_source_inputs=len(new), protected=len(protected))))


if __name__ == '__main__':
    main()
