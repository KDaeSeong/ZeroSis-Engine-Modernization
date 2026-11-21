"""Keep the progress index honest while the preserved candidate stays unchanged."""
from pathlib import Path
import hashlib
import json
import shutil

STAGE = Path(__file__).absolute().parent
PROJECT = STAGE.parents[2]
PROGRESS = PROJECT / 'evidence/save_menu/20261013_original_screen/current_progress.json'


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    scope = json.loads((STAGE / 'scope.json').read_text(encoding='utf-8'))
    changed = [row['path'] for row in scope['source_before'] if digest(Path(row['path'])) != row['sha256']]
    if not changed:
        raise RuntimeError('No source change exists to mark ahead of the linked candidate')
    backup = STAGE / 'source_before/current_progress.json'
    if not backup.exists():
        if digest(PROGRESS) != '98ae88dbae64597b6e6214aa6b87900568d808e3d19aaedd2bc9dbb2b259a5eb':
            raise RuntimeError('Unexpected progress baseline')
        shutil.copyfile(PROGRESS, backup)
        if digest(backup) != digest(PROGRESS):
            raise RuntimeError('Progress backup mismatch')
    report = json.loads(PROGRESS.read_text(encoding='utf-8'))
    if report.get('owned_save_overwrite_source_stage', {}).get('status') == 'PASS_SOURCE_AND_COMPONENT_ONLY':
        raise RuntimeError('This source stage is finalized; do not replay its in-progress marker')
    report.update(status='OVERWRITE_SOURCE_IMPLEMENTATION_IN_PROGRESS_NATIVE_TEST_HOLD',
                  latest_source_matches_linked_candidate=False,
                  latest_cpp_source_matches_actual_host_syntax_proof=False,
                  latest_source_matches_integrated_syntax_proof=False,
                  prepared_runtime_matches_latest_source=False,
                  full_engine_goal_complete=False)
    report['current_prepared_runtime']['current_source_candidate'] = False
    report['load_menu_source_stage']['source_changed_since_linked_host']['matches_current_linked_source'] = False
    report['owned_save_overwrite_source_stage'] = {
        'status': 'SOURCE_IMPLEMENTATION_IN_PROGRESS',
        'scope': str(STAGE / 'scope.json'),
        'source_before': str(STAGE / 'source_before'),
        'changed_baseline_inputs': changed,
        'preserved_host': scope['baseline_host'],
        'preserved_prepared_runtime': scope['baseline_prepared_runtime'],
        'current_source_linked_or_prepared': False,
        'retail_mod_test_hold_active': True,
        'gamecore_host_or_hwnd_executed': False,
        'default_promoted': False,
        'remaining': ['Finish component regression and current Host C++ compilation.',
                      'Embed and link current Lua/C++ into a new candidate only after component acceptance.',
                      'After explicit human mod-test end, verify actual SDK/window save and restore behavior.',
                      'Original full UI/3D/campaign, retail save/mod compatibility and multicore acceptance remain open.']}
    PROGRESS.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps({'status': report['status'], 'changed_baseline_inputs': len(changed),
                      'progress_sha256': digest(PROGRESS), 'preserved_candidate_unchanged': True}))


if __name__ == '__main__':
    main()
