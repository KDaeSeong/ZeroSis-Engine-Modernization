"""Freeze and exercise the Found-value semantic comparator without game execution."""
import copy
import hashlib
import json
import shutil
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
TOOLS = PROJECT / 'tools'
EVIDENCE = PROJECT / 'evidence/found_value_comparator'
sys.path.insert(0, str(TOOLS))
from verify_found_value_sdk_candidate import semantic_signature


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fixture_calls():
    return [
        {'session': 0, 'call_id': 1, 'turn': 0, 'player': 1, 'starting_loc': 0,
         'values': [(0, 17), (1, -1), (2, 41)], 'areas': [(2, 13), (7, 41)],
         'trace': {'map_plots': 3, 'revealed': 2, 'helper_unique_plots': 0,
                   'snapshot_us': 0, 'worker_us': 0, 'shadow_us': 0,
                   'reduction_us': 0, 'total_us': 88, 'worker_tids_job_counts': []}},
        {'session': 1, 'call_id': 1, 'turn': 1, 'player': 2, 'starting_loc': 0,
         'values': [(0, -1), (1, 25), (2, -1)], 'areas': [(4, 25)],
         'trace': {'map_plots': 3, 'revealed': 1, 'helper_unique_plots': 0,
                   'snapshot_us': 0, 'worker_us': 0, 'shadow_us': 0,
                   'reduction_us': 0, 'total_us': 93, 'worker_tids_job_counts': []}},
    ]


def main():
    verifier = TOOLS / 'verify_found_value_sdk_candidate.py'
    test_source = Path(__file__).resolve()
    originals = {path: sha256(path) for path in (verifier, test_source)}
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ_') + uuid.uuid4().hex[:12]
    directory = EVIDENCE / run_id
    frozen = directory / 'frozen_inputs'
    frozen.mkdir(parents=True, exist_ok=False)
    frozen_verifier = frozen / verifier.name
    frozen_test = frozen / test_source.name
    shutil.copy2(verifier, frozen_verifier)
    shutil.copy2(test_source, frozen_test)
    if sha256(frozen_verifier) != originals[verifier] or sha256(frozen_test) != originals[test_source]:
        raise RuntimeError('Comparator regression frozen source differs from the tested inputs')

    baseline = fixture_calls()
    expected = semantic_signature(baseline)
    diagnostic = copy.deepcopy(baseline)
    for offset, call in enumerate(diagnostic):
        call['trace'].update({'helper_unique_plots': 200 + offset, 'snapshot_us': 7 + offset,
                              'worker_us': 31 + offset, 'shadow_us': 17 + offset,
                              'reduction_us': 3 + offset, 'total_us': 100 + offset,
                              'worker_tids_job_counts': [(0xA100 + offset, 2 + offset)]})
    if semantic_signature(diagnostic) != expected:
        raise RuntimeError('Diagnostic helper/timing/TID changes affected semantic comparison')

    mutations = {}
    changed = copy.deepcopy(baseline)
    changed[0]['values'][0] = (0, 18)
    mutations['plot_score'] = changed
    changed = copy.deepcopy(baseline)
    changed[0]['areas'][0] = (2, 14)
    mutations['area_total'] = changed
    changed = copy.deepcopy(baseline)
    changed[0]['areas'].reverse()
    mutations['area_order'] = changed
    changed = copy.deepcopy(baseline)
    changed.reverse()
    mutations['call_sequence'] = changed
    changed = copy.deepcopy(baseline)
    changed[0]['call_id'] += 1
    mutations['call_identity'] = changed
    changed = copy.deepcopy(baseline)
    changed[0]['trace']['map_plots'] += 1
    mutations['map_plots'] = changed
    changed = copy.deepcopy(baseline)
    changed[0]['trace']['revealed'] += 1
    mutations['revealed_count'] = changed
    rejected = []
    for name, candidate in mutations.items():
        if semantic_signature(candidate) == expected:
            raise RuntimeError('Semantic mutation escaped comparator: ' + name)
        rejected.append(name)

    if any(sha256(path) != value for path, value in originals.items()):
        raise RuntimeError('Comparator regression source changed while running')
    report = {
        'status': 'FOUND_VALUE_SEMANTIC_COMPARATOR_REGRESSION_PASS',
        'frozen_inputs': [
            {'path': str(verifier), 'sha256': originals[verifier], 'frozen_path': str(frozen_verifier)},
            {'path': str(test_source), 'sha256': originals[test_source], 'frozen_path': str(frozen_test)},
        ],
        'source_unchanged_after_test': True,
        'diagnostic_changes_accepted': ['helper_unique_plots', 'phase_timings', 'total_us',
                                        'worker_thread_job_counts'],
        'semantic_changes_rejected': rejected,
        'game_executed': False,
        'build_performed': False,
    }
    report_path = directory / 'conformance.json'
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps({'status': report['status'], 'evidence': str(report_path),
                      'accepted_diagnostics': report['diagnostic_changes_accepted'],
                      'rejected_semantics': rejected}, ensure_ascii=False))


if __name__ == '__main__':
    main()
