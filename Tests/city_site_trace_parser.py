"""Synthetic negative-case checks for the actual city-site trace validator.

These are parser tests, never evidence that SDK city-site work executed.
"""
import hashlib
import json
from pathlib import Path
import shutil
import sys
import uuid
from datetime import datetime, timezone

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / 'tools'))
import verify_city_site_sdk_candidate as validator


def run():
    frozen_sources = [Path(__file__).resolve(), PROJECT / 'tools/verify_city_site_sdk_candidate.py']
    before = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in frozen_sources}
    directory = PROJECT / 'evidence/city_site_trace_parser' / (
        datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ_') + uuid.uuid4().hex[:12])
    directory.mkdir(parents=True, exist_ok=False)
    for source in frozen_sources:
        shutil.copy2(source, directory / source.name)
    record = '10:1,2,3,4;20:-4,5,0,7'
    metrics = dict(abi=1, config=1, status=0, call_id=1, player=1, turn=42, cities=2,
                   mode='owned-worker', requested_workers=4, eligible_sites=2, input_cells=74,
                   input_cells_scope='eligible_sites_times_tile_count_including_home_and_missing_plot_slots',
                   best_food=1, best_production=5, best_gold=3, best_science=7,
                   ordered_output_fnv1a64='8a738f192ff9919a', fnv_scope=validator.FNV_SCOPE,
                   snapshot_us=10, worker_us=100, shadow_us=20, reduction_us=1, total_us=131,
                   jobs_total=2, jobs_started=2, jobs_completed=2, workers_started=2,
                   used_threads=2, max_overlap=2, worker_tids_job_counts='100:1,200:1')
    def trace(values=record, modified=None, duplicate=''):
        fields = metrics.copy()
        if modified:
            fields.update(modified)
        return ('ZEROSIS_CITY_SITE_VALUES call_id=' + str(fields['call_id']) + ' records=' + values + '\n' +
                'ZEROSIS_CITY_SITE_TRACE ' + ' '.join(str(key) + '=' + str(value) for key, value in fields.items()) +
                duplicate + '\n')
    boundary = 'NATIVE_RESTORE_FRESH_SESSION=true\n'
    base = boundary + trace()
    fixtures = []
    def good(name, output, workers=4):
        actual = validator.inspect_traces(output, workers, 50)
        fixtures.append({'name': name, 'accepted': True, 'output': output, 'workers': workers,
                         'parsed_invocations': len(actual)})
        return actual
    def bad(name, output, workers=4):
        try:
            validator.inspect_traces(output, workers, 50)
        except (RuntimeError, ValueError):
            fixtures.append({'name': name, 'accepted': False, 'output': output, 'workers': workers})
        else:
            raise RuntimeError('Validator accepted malformed fixture: ' + name)
    actual = good('valid-negative-yield-and-worker-metrics', base)
    assert actual[0]['ordered_output_sha256'] == 'f1b12fbd71e56aabc0bf378ee81cdfc98c07a027cc31fbedc2b1c482ce033722'
    good('fresh-session-call-counter-reset', trace() + boundary + trace())
    scalar = dict(mode='scalar-original', requested_workers=0, snapshot_us=0, worker_us=0,
                  shadow_us=0, reduction_us=0, workers_started=0, used_threads=0, max_overlap=0,
                  worker_tids_job_counts='')
    good('valid-original-scalar', boundary + trace(modified=scalar), workers=0)
    bad('missing-fresh-session-boundary', trace())
    bad('duplicate-fresh-session-boundary', boundary + boundary + trace())
    bad('missing-complete-trace', boundary + trace().split('ZEROSIS_CITY_SITE_TRACE')[0])
    bad('missing-ordered-values', boundary + 'ZEROSIS_CITY_SITE_TRACE' + trace().split('ZEROSIS_CITY_SITE_TRACE')[1])
    bad('duplicate-trace-key', boundary + trace(duplicate=' jobs_completed=2'))
    bad('non-ascending-eligible-plots', boundary + trace(values='20:-4,5,0,7;10:1,2,3,4'))
    bad('duplicate-eligible-plot', boundary + trace(values='10:1,2,3,4;10:-4,5,0,7'))
    bad('hash-does-not-match-literal-result', boundary + trace(modified={'ordered_output_fnv1a64': '0' * 16}))
    bad('partial-jobs-completed', boundary + trace(modified={'jobs_completed': 1}))
    bad('worker-request-mismatch', boundary + trace(modified={'requested_workers': 2}))
    bad('incorrect-best-reduction', boundary + trace(modified={'best_food': 4}))
    bad('wrong-call-sequence', boundary + trace(modified={'call_id': 2}))
    bad('wrong-ABI', boundary + trace(modified={'abi': 2}))
    bad('nonzero-status', boundary + trace(modified={'status': 3}))
    bad('input-cells-outside-capacity', boundary + trace(modified={'input_cells': 129}))
    bad('wrong-input-cell-scope', boundary + trace(modified={'input_cells_scope': 'fake'}))
    bad('duplicate-worker-TID', boundary + trace(modified={'worker_tids_job_counts': '100:1,100:1'}))
    bad('incomplete-thread-job-counts', boundary + trace(modified={'worker_tids_job_counts': '100:1,200:2'}))
    bad('unsupported-thread-overlap', boundary + trace(modified={'max_overlap': 3}))
    bad('scalar-reports-worker-execution', boundary + trace(modified={**scalar, 'workers_started': 1}), workers=0)
    bad('oversized-plot-index', boundary + trace(values='960:1,2,3,4;961:-4,5,0,7'))
    bad('out-of-int32-yield', boundary + trace(values='10:2147483648,2,3,4;20:-4,5,0,7'))
    empty = dict(call_id=2, eligible_sites=0, input_cells=0, best_food=0, best_production=0,
                 best_gold=0, best_science=0, ordered_output_fnv1a64='cbf29ce484222325',
                 jobs_total=0, jobs_started=0, jobs_completed=0, workers_started=0,
                 used_threads=0, max_overlap=0, worker_tids_job_counts='')
    good('complete-empty-call-following-real-work', boundary + trace() + trace(values='-', modified=empty))
    bad('only-empty-invocations-not-runtime-work-proof', boundary + trace(values='-', modified={**empty, 'call_id': 1}))
    after = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in frozen_sources}
    if before != after:
        raise RuntimeError('Parser test or validator changed during verification')
    fixture_path = directory / 'fixtures.json'
    fixture_path.write_text(json.dumps(fixtures, indent=2) + '\n', encoding='utf8')
    report = dict(status='CITY_SITE_TRACE_PARSER_NEGATIVE_CASES_PASS',
                  checks=len(fixtures), accepted_cases=sum(row['accepted'] for row in fixtures),
                  rejected_cases=sum(not row['accepted'] for row in fixtures),
                  frozen_sources=[validator.artifact(directory / source.name) for source in frozen_sources],
                  source_hashes_before=before, source_hashes_after=after,
                  fixtures=validator.artifact(fixture_path), gamecore_loaded=False,
                  sdk_runtime_launched=False, physical_multicore_verified=False,
                  scope='SYNTHETIC_TRACE_SCOPE_PAIRING_ORDER_REDUCTION_ABI_AND_WORKER_ACCOUNTING_REJECTION_ONLY')
    target = directory / 'conformance.json'
    target.write_text(json.dumps(report, indent=2) + '\n', encoding='utf8')
    print(json.dumps({'status': report['status'], 'checks': len(fixtures),
                      'evidence': validator.artifact(target)}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    run()
