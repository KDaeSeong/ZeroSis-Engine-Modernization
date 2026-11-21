"""Reject malformed shared payload/batch records without running native code."""
import copy
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from verify_found_value_shared_sdk_candidate import parse_shared_layouts, parse_trace_block


def fixture():
    def call(batch):
        return [
            'ZEROSIS_FOUND_VALUE_VALUES call_id=1 records=0:0;1:10;2:-1',
            'ZEROSIS_FOUND_VALUE_AREAS call_id=1 records=1:10',
            'ZEROSIS_FOUND_VALUE_TRACE version=1 call_id=1 turn=2 player=0 starting_loc=0 '
            'mode=owned-worker requested_workers=2 map_plots=3 revealed=2 helper_unique_plots=3 '
            'snapshot_us=1 worker_us=2 shadow_us=1 reduction_us=1 total_us=10 '
            'jobs_total=2 jobs_started=2 jobs_completed=2 workers_started=2 used_threads=2 '
            'max_overlap=2 worker_tids_job_counts=101:1,102:1',
            f'ZEROSIS_FOUND_VALUE_LAYOUT version=1 call_id=1 input_layout=SHARED_FACTS cpu_batch_id={batch} '
            'common_bytes=240 plot_bytes=348 candidate_bytes=3696 input_payload_bytes=4284 '
            'dense_equivalent_bytes=38280 jobs_total=2',
        ]
    return '\n'.join(call(100) + ['NATIVE_RESTORE_FRESH_SESSION=true'] + call(200))


def main():
    output = fixture()
    calls = parse_trace_block(output, 2)
    assert len(parse_shared_layouts(output, copy.deepcopy(calls))) == 2
    mutations = [
        ('wrong_layout', output.replace('SHARED_FACTS', 'DENSE', 1)),
        ('wrong_common_size', output.replace('common_bytes=240', 'common_bytes=241', 1)),
        ('wrong_plot_payload', output.replace('plot_bytes=348', 'plot_bytes=116', 1)),
        ('wrong_candidate_payload', output.replace('candidate_bytes=3696', 'candidate_bytes=1848', 1)),
        ('wrong_total_payload', output.replace('input_payload_bytes=4284', 'input_payload_bytes=4283', 1)),
        ('wrong_dense_payload', output.replace('dense_equivalent_bytes=38280', 'dense_equivalent_bytes=19140', 1)),
        ('wrong_jobs', output.replace('jobs_total=2\n', 'jobs_total=1\n', 1)),
        ('zero_nonempty_batch', output.replace('cpu_batch_id=100', 'cpu_batch_id=0', 1)),
        ('oversized_batch', output.replace('cpu_batch_id=100', f'cpu_batch_id={2**64}', 1)),
        ('reused_batch_after_restore', output.replace('cpu_batch_id=200', 'cpu_batch_id=100', 1)),
        ('nonadjacent_layout', output.replace('ZEROSIS_FOUND_VALUE_LAYOUT version=1', '\nZEROSIS_FOUND_VALUE_LAYOUT version=1', 1)),
        ('missing_layout', '\n'.join(line for line in output.splitlines() if 'cpu_batch_id=100 ' not in line)),
        ('extra_layout', output + '\n' + output.splitlines()[-1]),
        ('unknown_field', output.replace('common_bytes=240', 'extra=0 common_bytes=240', 1)),
        ('wrong_call_id', output.replace('LAYOUT version=1 call_id=1', 'LAYOUT version=1 call_id=2', 1)),
    ]
    for name, malformed in mutations:
        try:
            parse_shared_layouts(malformed, copy.deepcopy(calls))
        except RuntimeError:
            continue
        raise AssertionError(f'Malformed shared layout was accepted: {name}')
    print(f'FOUND_VALUE_SHARED_LAYOUT_REGRESSIONS_PASS checks={1 + len(mutations)} native_execution=false')


if __name__ == '__main__':
    main()
