"""File-only review of the native offline follow-up Host plan before its single build."""
import hashlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
STAGE = Path(__file__).absolute().parent
PROJECT = STAGE.parents[2]
PARENT_ID = '20261106T225828Z_b281e2cf6094'
PARENT_SHA = 'eba6dd2c7ec9f6a2034cd60a4a9b3a45f2a9f6d413f66ee24ee76dc719fca7bb'
PREVIOUS_RUN = '20261106T230144Z_48d9fd363237'


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
        'Source\\Host\\MenuFrontEndOptionsModel.h', 'Source\\Host\\UiPopupContext.h',
        'Tests\\menu_frontend_options_offline.cpp', 'Tests\\menu_frontend_options_offline.py',
        'Tests\\menu_frontend_grid_layout.py', 'Tests\\menu_replay_restoration.py',
        'Tests\\menu_reward_options_view.py', 'Tests\\menu_resolution_preview_view.py',
        'tools\\menu_frontend_skin_pages.py', 'tools\\build_menu_suite_host.py', 'tools\\attest_prepared_menu_host.py'}
    expected_added_production = {'Source\\Host\\UiLocaleArguments.h'}
    folded = {item.casefold() for item in expected_changed}
    # Windows paths: earlier records spell the builder 'Tools\\...', so compare case-insensitively.
    unexpected = sorted(name for name in changed if name.casefold() not in folded)
    production_added = sorted(name for name in added if name.casefold().startswith(('source\\host\\', 'source\\presentation\\')))
    checks = dict(
        parent_is_current=plan['parent']['sha256'] == PARENT_SHA and parent['build_id'] == PARENT_ID,
        gate_pinned=plan['menu_gate']['sha256'] == '587d564e7df4e59fca5356e6f94b15b4bc3aba4a36fed11ba150ac355af08067',
        offline_only=plan['host_sdk_clr_hwnd_gpu_or_game_execution_allowed'] is False and plan['automatic_retry_allowed'] is False
                     and plan['default_promotion_allowed'] is False and plan['full_ui_preparer_main_allowed'] is False,
        catalog=plan['catalog_count'] == 74,
        phases=len(plan['direct_child_phases']) == 12,
        current_prepared_runtime_protected=protected_roots.get(PREVIOUS_RUN, 0) > 0,
        production_changes_expected={name.casefold() for name in changed if name.casefold().startswith('source\\')} ==
                                    {'source\\host\\menufrontendoptionsmodel.h', 'source\\host\\uipopupcontext.h'},
        production_additions_expected={name.casefold() for name in production_added} ==
                                      {name.casefold() for name in expected_added_production},
        no_unexpected_changed_inputs=not unexpected,
        no_removed_inputs=not removed)
    review = dict(schema='zerosis.native_offline_followup.plan_review.v1',
                  plan=dict(path=str(plan_path), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest()),
                  changed_from_parent=changed, added_to_parent=added, removed_from_parent=removed,
                  unexpected_changed=unexpected, production_added=production_added,
                  protected_artifacts=len(plan['protected_artifacts']),
                  protected_runtime_files=protected_roots, current_source_inputs=len(plan['current_source_inputs']),
                  additional_sources=len(plan['additional_sources']), checks=checks,
                  status='PASS_FILE_ONLY_PLAN_REVIEW' if all(checks.values()) else 'FAIL_FILE_ONLY_PLAN_REVIEW',
                  native_execution=False)
    output = STAGE / 'host_build/plan_review.json'
    with output.open('x', encoding='utf8') as stream:
        json.dump(review, stream, indent=2)
        stream.write('\n')
    print(json.dumps(dict(status=review['status'], changed=changed, added=len(added), production_added=production_added,
                          removed=len(removed), unexpected=unexpected, checks=checks, plan_sha256=review['plan']['sha256'])))
    return 0 if review['status'].startswith('PASS') else 1


if __name__ == '__main__':
    raise SystemExit(main())
