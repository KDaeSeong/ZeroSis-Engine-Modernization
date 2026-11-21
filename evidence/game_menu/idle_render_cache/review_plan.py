"""Review the exact offline Host plan, changed source scope and preserved user runtime."""
import gzip
import hashlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode=True
STAGE=Path(__file__).absolute().parent
PROJECT=STAGE.parents[2]
sys.path.insert(0,str(PROJECT/'tools'))
import build_exit_confirm_host as common

def main():
    path=STAGE/'host_build/plan2.json';raw=path.read_bytes();plan=json.loads(raw)
    parent=json.loads(Path(plan['parent']['path']).read_bytes())
    old={common.key(row['path']):row for row in parent['current_source_inputs']}
    new={common.key(row['path']):row for row in plan['current_source_inputs']}
    protected={common.key(row['path']):row for row in plan['protected_artifacts']}
    changed=[new[k]['path'] for k in old.keys()&new.keys() if (old[k]['bytes'],old[k]['sha256'])!=(new[k]['bytes'],new[k]['sha256'])]
    removed=[old[k]['path'] for k in old.keys()-new.keys()]
    added=[new[k]['path'] for k in new.keys()-old.keys()]
    expected=[str(PROJECT/name) for name in (
        'Source/Presentation/WorldTerrainRenderer.cpp','Source/Presentation/WorldTerrainRenderer.h',
        'Source/Presentation/WorldViewRenderer.cpp','Source/Presentation/WorldViewRenderer.h',
        'Source/Host/InteractiveGameLoop.h','tools/build_menu_suite_host.py','tools/attest_prepared_menu_host.py')]
    baseline=json.loads(gzip.decompress((STAGE/'protection_before.json.gz').read_bytes()))
    runtime=PROJECT/'Build/InteractiveGameRuntime/20261108T003146Z_40a8030edf08'
    user_rows=[row for row in baseline['protected_artifacts'] if Path(row['path']).is_relative_to(runtime)]
    user_preserved=all(common.key(row['path']) in protected and
        all(protected[common.key(row['path'])][field]==row[field] for field in ('bytes','sha256','file_identity','mtime_ns','file_attributes')) for row in user_rows)
    selection=plan['system_tool_selection'];cmd=selection['selected_cmd']
    old_tools={common.key(row['path']):row for row in parent['toolchain_inputs']}
    new_tools={common.key(row['path']):row for row in plan['toolchain_inputs']}
    changed_tools=[k for k in old_tools if old_tools[k]!=new_tools.get(k)]
    checks=dict(
        parent_current=parent['build_id']=='20261108T002841Z_2b25aaa753e3' and plan['parent']['sha256']=='5974076a43e67eed3f637fdd08684dbad8f4a07e33c352cd249d489f1f3559eb',
        changed_scope_exact={common.key(p) for p in changed}=={common.key(p) for p in expected},
        no_removed_current_inputs=not removed,
        exact_one_new_production_header={Path(p).relative_to(PROJECT).as_posix() for p in added if Path(p).is_relative_to(PROJECT/'Source')}=={'Source/Presentation/WorldTerrainReuse.h'},
        protected_previous_runtime_and_user_session=user_preserved and any('350dd3b9ceb408a391b5a8aa63b48301' in row['path'] for row in user_rows),
        only_selected_cmd_provider_changed=changed_tools==[common.key(cmd['path'])] and common.sealed(cmd)==cmd,
        selected_cmd_not_current_source=common.key(cmd['path']) not in new,
        catalog_unchanged=plan['catalog_count']==74,
        exact_compile_only_phases=len(plan['direct_child_phases'])==12 and plan['allowed_native_children']=='EXACT_ENVIRONMENT_AND_COMPILER_LINKER_ONLY',
        native_run_and_default_disabled=all(plan[k] is False for k in ('host_sdk_clr_hwnd_gpu_or_game_execution_allowed','full_ui_preparer_main_allowed','default_promotion_allowed','automatic_retry_allowed','full_engine_goal_complete')),
        unchanged_gates=plan['menu_gate']['sha256']=='587d564e7df4e59fca5356e6f94b15b4bc3aba4a36fed11ba150ac355af08067' and plan['common_helper']['sha256']=='69133de112bd30e088626379adce382912f26086aae701c8a2683fbbe0e8fd94')
    result=dict(schema='zerosis.idle_render_cache.plan_review.v1',status='PASS' if all(checks.values()) else 'FAIL',
        checks=checks,plan=common.artifact(path),plan_sha256=hashlib.sha256(raw).hexdigest(),
        changed_from_parent=changed,added_to_parent=added,removed_from_parent=removed,
        current_source_inputs=len(new),protected_artifacts=len(protected),previous_user_runtime_files=len(user_rows),
        native_execution=False,measured_cpu_reduction=False)
    with (STAGE/'host_build/plan_review2.json').open('x',encoding='utf8') as f:json.dump(result,f,indent=2);f.write('\n')
    assert all(checks.values()),checks
    print(json.dumps({k:result[k] for k in ('status','plan_sha256','current_source_inputs','protected_artifacts','previous_user_runtime_files')}))

if __name__=='__main__':main()
