"""File-only review of the replay season/wheel Host plan before its single build."""
import hashlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
STAGE = Path(__file__).absolute().parent
PROJECT = STAGE.parents[2]


def key(path):
    return str(Path(path)).casefold()


def main():
    plan_path = STAGE / 'host_build/plan.json'
    raw = plan_path.read_bytes()
    plan = json.loads(raw)
    parent = json.loads(Path(plan['parent']['path']).read_bytes())
    old = {key(row['path']): row for row in parent['current_source_inputs']}
    new = {key(row['path']): row for row in plan['current_source_inputs']}
    changed = sorted(str(Path(new[k]['path']).relative_to(PROJECT)) for k in new.keys() & old.keys()
                     if (new[k]['bytes'], new[k]['sha256']) != (old[k]['bytes'], old[k]['sha256']))
    added = sorted(str(Path(new[k]['path']).relative_to(PROJECT)) if Path(new[k]['path']).is_relative_to(PROJECT)
                   else new[k]['path'] for k in new.keys() - old.keys())
    removed = sorted(old[k]['path'] for k in old.keys() - new.keys())
    protected_roots = {}
    for row in plan['protected_artifacts']:
        parts = Path(row['path']).parts
        if 'InteractiveGameRuntime' in parts:
            run = parts[parts.index('InteractiveGameRuntime') + 1]
            protected_roots[run] = protected_roots.get(run, 0) + 1
    expected_changed = {
        'Source\\Host\\HostRun.h', 'Source\\Host\\MenuReplayCalendar.h', 'Source\\Host\\MenuReplayScrollModel.h',
        'Source\\Host\\MenuReplayPresentation.h', 'Tests\\menu_replay_calendar.py', 'Tests\\menu_replay_calendar.cpp',
        'Tests\\menu_replay_scroll_model.py', 'Tests\\menu_replay_scroll_model.cpp', 'Tests\\menu_replay_restoration.py',
        'Tests\\menu_replay_restored_scene.cpp', 'Tests\\menu_replay_input_batch.py', 'tools\\build_menu_suite_host.py',
        'tools\\attest_prepared_menu_host.py'}
    # Windows paths: the parent records 'Tools\\...' for the builder, so compare case-insensitively.
    unexpected = sorted(name for name in changed if name.casefold() not in {item.casefold() for item in expected_changed})
    checks = dict(
        parent_is_current=plan['parent']['sha256'] == 'e4d554dfe6a3a7467f758cb6bbe493a1185c664a5c8874d5a1c906345207b5dc'
                          and parent['build_id'] == '20261106T134645Z_0f1da0168223',
        gate_pinned=plan['menu_gate']['sha256'] == '587d564e7df4e59fca5356e6f94b15b4bc3aba4a36fed11ba150ac355af08067',
        offline_only=plan['host_sdk_clr_hwnd_gpu_or_game_execution_allowed'] is False and plan['automatic_retry_allowed'] is False
                     and plan['default_promotion_allowed'] is False and plan['full_ui_preparer_main_allowed'] is False,
        catalog=plan['catalog_count'] == 74,
        phases=len(plan['direct_child_phases']) == 12,
        current_prepared_runtime_protected=protected_roots.get('20261106T135115Z_e38cb351eca4', 0) > 0,
        no_unexpected_changed_inputs=not unexpected,
        no_removed_inputs=not removed)
    review = dict(schema='zerosis.replay_season_wheel.plan_review.v1',
                  plan=dict(path=str(plan_path), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest()),
                  changed_from_parent=changed, added_to_parent=added, removed_from_parent=removed,
                  unexpected_changed=unexpected, protected_artifacts=len(plan['protected_artifacts']),
                  protected_runtime_files=protected_roots, current_source_inputs=len(plan['current_source_inputs']),
                  additional_sources=len(plan['additional_sources']), checks=checks,
                  status='PASS_FILE_ONLY_PLAN_REVIEW' if all(checks.values()) else 'FAIL_FILE_ONLY_PLAN_REVIEW',
                  supersedes=dict(path='host_build/plan_review.json',
                                  reason='First review compared Windows path case sensitively (Tools vs tools); plan unchanged.'),
                  native_execution=False)
    output = STAGE / 'host_build/plan_review_final.json'
    with output.open('x', encoding='utf8') as stream:
        json.dump(review, stream, indent=2)
        stream.write('\n')
    print(json.dumps(dict(status=review['status'], changed=len(changed), added=len(added), removed=len(removed),
                          unexpected=unexpected, checks=checks, plan_sha256=review['plan']['sha256'])))
    return 0 if review['status'].startswith('PASS') else 1


if __name__ == '__main__':
    raise SystemExit(main())
