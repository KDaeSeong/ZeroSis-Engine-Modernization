"""File-only scope/protection/toolchain review before the phase-two compilation."""
import argparse,gzip,json,sys
from pathlib import Path
sys.dont_write_bytecode=True
STAGE=Path(__file__).absolute().parent;PROJECT=STAGE.parents[2]
sys.path.insert(0,str(PROJECT/'tools'))
import build_exit_confirm_host as common

def main():
    cli=argparse.ArgumentParser();cli.add_argument('--retry',action='store_true');args=cli.parse_args()
    path=STAGE/('host_build/plan_retry01.json' if args.retry else 'host_build/plan.json');plan=json.loads(path.read_text('utf8'))
    parent=json.loads(Path(plan['parent']['path']).read_text('utf8'))
    old={common.key(row['path']):row for row in parent['current_source_inputs']}
    new={common.key(row['path']):row for row in plan['current_source_inputs']}
    protected={common.key(row['path']):row for row in plan['protected_artifacts']}
    changed=[new[key]['path'] for key in new.keys()&old.keys() if (new[key]['bytes'],new[key]['sha256'])!=(old[key]['bytes'],old[key]['sha256'])]
    expected=[str(PROJECT/name) for name in (
        'Source/Presentation/WorldTerrainRenderer.cpp','Source/Presentation/WorldViewRenderer.h',
        'Source/Presentation/OriginalTerrainShader.h','Source/Presentation/OriginalTerrainGpuTypes.inc',
        'Source/Presentation/OriginalTerrainGpu.inc','Source/Host/InteractiveGameLoop.h',
        'tools/build_menu_suite_host.py','tools/attest_prepared_menu_host.py')]
    baseline=json.loads(gzip.decompress((STAGE/'protection_before.json.gz').read_bytes()))
    runtime=PROJECT/'Build/InteractiveGameRuntime/20261115T011241Z_4c8fd55e99db'
    user=PROJECT/'Build/InteractiveGameRuntime/20261108T003146Z_40a8030edf08'
    must=[row for row in baseline['protected_artifacts'] if Path(row['path']).is_relative_to(runtime) or Path(row['path']).is_relative_to(user)]
    same=all(common.key(row['path']) in protected and all(protected[common.key(row['path'])][field]==row[field]
        for field in ('bytes','sha256','file_identity','mtime_ns','file_attributes')) for row in must)
    checks=dict(parent_latest=parent['build_id']=='20261115T024443Z_8470b8d966f8' and plan['parent']['sha256']=='c2b21c5fc5905b59c5bb5e7e0df5e8626f885bbd85b50b604bbaeeb70dc656f3',
        exact_changed_scope={common.key(p) for p in changed}=={common.key(p) for p in expected},
        no_removed_inputs=not(old.keys()-new.keys()),current_and_user_runtimes_preserved=same,
        no_toolchain_change=plan['system_tool_selection'] is None and plan['toolchain_inputs']==parent['toolchain_inputs'],
        offline_only=all(plan[k] is False for k in ('host_sdk_clr_hwnd_gpu_or_game_execution_allowed','full_ui_preparer_main_allowed','default_promotion_allowed','automatic_retry_allowed','full_engine_goal_complete')),
        exact12compiler_phases=len(plan['direct_child_phases'])==12,catalog74=plan['catalog_count']==74,
        fixed_gate=plan['menu_gate']['sha256']=='587d564e7df4e59fca5356e6f94b15b4bc3aba4a36fed11ba150ac355af08067')
    result=dict(status='PASS' if all(checks.values()) else 'FAIL',checks=checks,plan=common.artifact(path),
        changed_inputs=changed,current_source_inputs=len(new),protected_artifacts=len(protected),protected_runtime_files=len(must),native_execution=False)
    output=STAGE/('host_build/plan_review_retry01.json' if args.retry else 'host_build/plan_review.json')
    with output.open('x',encoding='utf8') as f:json.dump(result,f,indent=2);f.write('\n')
    assert all(checks.values()),checks
    print(json.dumps(dict(status=result['status'],plan_sha256=result['plan']['sha256'],current_source_inputs=len(new),protected=len(protected))))

if __name__=='__main__':main()
