"""Pure-function regressions for actual CitySite ETL reader output.

Consumes an already retained reader JSON result. Never invokes the reader,
GameCore, the capture runner, WPR, or a compiler.
"""
from __future__ import annotations

import ast
import copy
from datetime import datetime, timezone
import hashlib
import importlib
import json
from pathlib import Path
import shutil
import sys
import uuid


PROJECT = Path(__file__).resolve().parents[1]
TOOLS = PROJECT / 'tools'
EVIDENCE = PROJECT / 'evidence/city_site_cpu_capture'
SOURCE_PROOF = EVIDENCE / 'validators/20261002T130249Z_cf95e34976c4/conformance.json'


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def local_tool_closure(entry: Path) -> list[Path]:
    pending = [entry.resolve()]
    found: set[Path] = set()
    while pending:
        source = pending.pop()
        if source in found:
            continue
        found.add(source)
        tree = ast.parse(source.read_text(encoding='utf8'))
        for node in ast.walk(tree):
            modules = []
            if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                modules = [node.module]
            elif isinstance(node, ast.Import):
                modules = [item.name for item in node.names]
            for module in modules:
                candidate = TOOLS / (module.split('.')[0] + '.py')
                if candidate.is_file() and candidate.resolve() not in found:
                    pending.append(candidate.resolve())
    return sorted(found)


def rejected(case_id: str, label: str, variant: dict, check, save_case) -> dict:
    case_path = save_case(case_id, variant)
    try:
        check()
    except Exception as error:
        return {'case': case_id, 'label': label, 'outcome': 'REJECTED',
                'exception_type': type(error).__name__, 'reason': str(error),
                'mutated_input': case_path}
    raise AssertionError('Invalid correlation input unexpectedly passed: ' + case_id)


def main() -> int:
    if not SOURCE_PROOF.is_file():
        raise FileNotFoundError(SOURCE_PROOF)
    proof_raw = json.loads(SOURCE_PROOF.read_text(encoding='utf8'))
    decoded_ref = proof_raw['reader_stdout']
    topology_before_ref = proof_raw['topology_before']
    topology_after_ref = proof_raw['topology_after']
    capture_ref = proof_raw['capture']
    source_paths = local_tool_closure(TOOLS / 'verify_city_site_cpu_capture.py')
    source_paths.extend((Path(__file__).resolve(), SOURCE_PROOF.resolve(), Path(decoded_ref['path']).resolve(),
                         Path(topology_before_ref['path']).resolve(), Path(topology_after_ref['path']).resolve(),
                         Path(capture_ref['path']).resolve()))
    source_paths = sorted(set(path.resolve() for path in source_paths))
    for row in (decoded_ref, topology_before_ref, topology_after_ref, capture_ref):
        if not Path(row['path']).is_file() or sha(Path(row['path'])) != row['sha256']:
            raise RuntimeError('An actual retained proof input no longer matches its SHA-256 record')

    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ_') + uuid.uuid4().hex[:12]
    out = PROJECT / 'evidence/city_site_cpu_capture_regressions' / run_id
    frozen_dir, case_dir = out / 'inputs', out / 'cases'
    frozen_dir.mkdir(parents=True, exist_ok=False)
    case_dir.mkdir()
    before = {str(path): sha(path) for path in source_paths}
    frozen: dict[Path, Path] = {}
    frozen_rows = []
    for index, source in enumerate(source_paths):
        target = frozen_dir / f'{index:03d}_{source.name}'
        shutil.copy2(source, target)
        if sha(target) != before[str(source)]:
            raise RuntimeError('Frozen regression input differs from its source')
        frozen[source] = target
        frozen_rows.append({'source_path': str(source), 'frozen_path': str(target), 'sha256': sha(target)})

    # Load the actual decoded output, topology and proof from their frozen copies.
    frozen_proof_path = frozen[SOURCE_PROOF.resolve()]
    frozen_proof = json.loads(frozen_proof_path.read_text(encoding='utf8'))
    decoded = json.loads(frozen[Path(decoded_ref['path']).resolve()].read_text(encoding='utf8'))
    captured = json.loads(frozen[Path(topology_before_ref['path']).resolve()].read_text(encoding='utf8'))
    captured_after = json.loads(frozen[Path(topology_after_ref['path']).resolve()].read_text(encoding='utf8'))
    capture_record = json.loads(frozen[Path(capture_ref['path']).resolve()].read_text(encoding='utf8'))

    sys.path.insert(0, str(TOOLS))
    cpu = importlib.import_module('verify_city_site_cpu_capture')
    trace = frozen_proof['actual_runtime']['city_site_traces'][0]
    pid = frozen_proof['sdk_process_id']
    batch = frozen_proof['batch_summary']['batch_id']
    tile_count = frozen_proof['actual_runtime']['fixture_rules_city_site_definitions'][
        'AI_CITY_SPECIALIZATION_YIELD_NUM_TILES_CONSIDERED']
    parsed = decoded
    actual_topology = cpu.topology(frozen[Path(topology_before_ref['path']).resolve()])
    validated_jobs = cpu.job_intervals(parsed, trace, batch, pid, tile_count)
    validated_lifetimes = cpu.lifetimes(parsed, validated_jobs, pid)
    calculated_witness, actual_scored = cpu.independently_find_overlap(
        parsed, validated_jobs, actual_topology, pid, batch, validated_lifetimes)
    if calculated_witness != frozen_proof['independent_overlap_witness'] or not calculated_witness:
        raise AssertionError('Current pure functions do not reproduce the retained actual CPU witness')
    raw_reader_witness = parsed['proof']
    expected_actual_witness = cpu.conservative_qpc_witness({
        **frozen_proof['independent_overlap_witness'],
        'begin_qpc': frozen_proof['independent_overlap_witness']['raw_begin_qpc'],
        'end_qpc': frozen_proof['independent_overlap_witness']['raw_end_qpc'],
    })
    if calculated_witness != expected_actual_witness:
        raise AssertionError('Retained actual witness is not the conservative form of its independently scored raw interval')
    if raw_reader_witness['end_qpc'] - raw_reader_witness['begin_qpc'] not in (1, 2):
        raise AssertionError('Expected the actual reader provisional witness to remain a separate raw claim')
    if calculated_witness['raw_end_qpc'] - calculated_witness['raw_begin_qpc'] != 4 or \
       calculated_witness['end_qpc'] - calculated_witness['begin_qpc'] != 2 or \
       calculated_witness['margin_ticks_each_boundary'] != 1:
        raise AssertionError('Actual retained witness does not preserve raw four ticks and conservative two ticks')

    def save_case(case_id: str, value: dict) -> dict:
        path = case_dir / (case_id + '.json')
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
        return {'path': str(path), 'sha256': sha(path)}

    cases = []
    cases.append({'case': 'actual_retained_data', 'label': 'Actual decoded ETL output and runtime bridge correlate',
                  'outcome': 'ACCEPTED', 'jobs': len(validated_jobs), 'workers': len(validated_lifetimes),
                  'raw_reader_witness': raw_reader_witness, 'witness': calculated_witness,
                  'raw_overlap_ticks': calculated_witness['raw_end_qpc'] - calculated_witness['raw_begin_qpc'],
                  'conservative_overlap_ticks': calculated_witness['end_qpc'] - calculated_witness['begin_qpc']})

    # Exercise the QPC boundary policy through the real independent interval
    # scorer, with both workers on distinct physical cores and valid lifetimes.
    for raw_ticks in (1, 2, 3):
        begin, end = 100, 100 + raw_ticks
        synthetic_jobs = [
            {'job_index': 1, 'worker_tid': 11, 'begin_qpc': begin, 'end_qpc': end},
            {'job_index': 2, 'worker_tid': 12, 'begin_qpc': begin, 'end_qpc': end},
        ]
        synthetic_topology = {'topology': [
            {'group': 0, 'logical_processor': 0, 'physical_core': 0},
            {'group': 0, 'logical_processor': 1, 'physical_core': 1},
        ]}
        synthetic_slices = [
            {'process_id': 777, 'worker_tid': 11, 'processor_index': 0, 'group': 0,
             'group_processor': 0, 'physical_core': 0, 'begin_qpc': begin, 'end_qpc': end},
            {'process_id': 777, 'worker_tid': 12, 'processor_index': 1, 'group': 0,
             'group_processor': 1, 'physical_core': 1, 'begin_qpc': begin, 'end_qpc': end},
        ]
        synthetic_proof = {'batch_id': 7, 'first_job': 1, 'first_tid': 11, 'first_core': 0,
                           'second_job': 2, 'second_tid': 12, 'second_core': 1,
                           'begin_qpc': begin, 'end_qpc': end}
        synthetic = {'worker_cpu_slices': synthetic_slices, 'physical_multicore_proven': True,
                     'proof': synthetic_proof}
        synthetic_lifetimes = {11: [[90, 200]], 12: [[90, 200]]}
        conservative, _ = cpu.independently_find_overlap(
            synthetic, synthetic_jobs, synthetic_topology, 777, 7, synthetic_lifetimes)
        if raw_ticks <= 2:
            if conservative is not None or cpu.conservative_qpc_witness(synthetic_proof) is not None:
                raise AssertionError(f'{raw_ticks}-tick raw overlap was incorrectly promoted')
            outcome = 'ACCEPTED_AS_NO_PROMOTED_WITNESS'
            expected = None
        else:
            expected = {**synthetic_proof, 'raw_begin_qpc': begin, 'raw_end_qpc': end,
                        'begin_qpc': begin + 1, 'end_qpc': end - 1,
                        'margin_ticks_each_boundary': 1}
            if conservative != expected or conservative['end_qpc'] - conservative['begin_qpc'] != 1:
                raise AssertionError('Three-tick raw overlap did not yield the expected one-tick conservative witness')
            outcome = 'ACCEPTED_AS_CONSERVATIVE_WITNESS'
        case_id = f'qpc_raw_{raw_ticks}_tick'
        fixture = {'parsed': synthetic, 'jobs': synthetic_jobs, 'topology': synthetic_topology,
                   'worker_lifetimes': synthetic_lifetimes, 'expected_conservative_witness': expected}
        cases.append({'case': case_id, 'label': f'{raw_ticks}-tick raw overlap boundary',
                      'outcome': outcome, 'raw_overlap_ticks': raw_ticks,
                      'conservative_witness': conservative, 'mutated_input': save_case(case_id, fixture)})

    variant = copy.deepcopy(parsed)
    variant['markers'][0]['batch_id'] += 100
    cases.append(rejected('wrong_batch_marker', 'Marker from another batch', variant,
        lambda: cpu.job_intervals(variant, trace, batch, pid, tile_count), save_case))

    variant = copy.deepcopy(parsed)
    variant['markers'][1]['worker_tid'] = next(tid for tid, _ in trace['worker_thread_job_counts']
                                                if tid != variant['markers'][0]['worker_tid'])
    cases.append(rejected('mismatched_job_tid', 'Job begin/end worker TIDs disagree', variant,
        lambda: cpu.job_intervals(variant, trace, batch, pid, tile_count), save_case))

    variant = copy.deepcopy(parsed)
    variant['markers'][0]['process_id'] = pid + 1
    cases.append(rejected('wrong_job_pid', 'Job marker carries another PID', variant,
        lambda: cpu.job_intervals(variant, trace, batch, pid, tile_count), save_case))

    variant = copy.deepcopy(parsed)
    variant['markers'][0]['site_count'] += 1
    cases.append(rejected('wrong_cell_count', 'Marker tile/cell count differs from frozen SDK rules', variant,
        lambda: cpu.job_intervals(variant, trace, batch, pid, tile_count), save_case))

    variant = copy.deepcopy(parsed)
    variant['markers'].pop()
    cases.append(rejected('lost_marker', 'One begin/end event is lost', variant,
        lambda: cpu.job_intervals(variant, trace, batch, pid, tile_count), save_case))

    variant = copy.deepcopy(parsed)
    job1_begin = next(row for row in variant['markers'] if row['job_index'] == 1 and row['phase'] == 'begin')
    job1_begin['job_index'] = 0
    cases.append(rejected('duplicate_marker_job_index', 'Duplicate begin marker replaces another job', variant,
        lambda: cpu.job_intervals(variant, trace, batch, pid, tile_count), save_case))

    variant = copy.deepcopy(parsed)
    worker_tid = validated_jobs[0]['worker_tid']
    variant['thread_events'] = [row for row in variant['thread_events'] if row['thread_id'] != worker_tid]
    cases.append(rejected('missing_worker_lifetime', 'Scoring TID has no captured lifecycle', variant,
        lambda: cpu.lifetimes(variant, validated_jobs, pid), save_case))

    variant = copy.deepcopy(parsed)
    worker_event = next(row for row in variant['thread_events'] if row['thread_id'] == worker_tid)
    worker_event['process_id'] = pid + 1
    cases.append(rejected('reused_tid_wrong_pid', 'Same numeric TID lifecycle belongs to another PID', variant,
        lambda: cpu.lifetimes(variant, validated_jobs, pid), save_case))

    variant = copy.deepcopy(parsed)
    witness = copy.deepcopy(variant['proof'])
    witness['begin_qpc'] = 2 ** 63
    witness['end_qpc'] = witness['begin_qpc'] + 1
    variant['proof'] = witness
    cases.append(rejected('witness_outside_job_clock', 'Reader witness lies outside actual job/slice QPC intersections', variant,
        lambda: cpu.independently_find_overlap(variant, validated_jobs, actual_topology, pid, batch, validated_lifetimes),
        save_case))

    variant = copy.deepcopy(parsed)
    variant['physical_multicore_proven'] = False
    cases.append(rejected('reader_falseclaim_mismatch', 'Reader boolean contradicts independent physical-core calculation', variant,
        lambda: cpu.independently_find_overlap(variant, validated_jobs, actual_topology, pid, batch, validated_lifetimes),
        save_case))

    witness_jobs = [row for row in validated_jobs if row['job_index'] in
                    (calculated_witness['first_job'], calculated_witness['second_job'])]
    if len(witness_jobs) != 2:
        raise AssertionError('Retained overlap witness does not identify two jobs')
    candidates: list[tuple[dict, dict, int, int]] = []
    for left_job, right_job in (witness_jobs, witness_jobs[::-1]):
        left_rows = [row for row in parsed['worker_cpu_slices'] if row['worker_tid'] == left_job['worker_tid'] and
                     max(row['begin_qpc'], left_job['begin_qpc']) < min(row['end_qpc'], left_job['end_qpc'])]
        right_rows = [row for row in parsed['worker_cpu_slices'] if row['worker_tid'] == right_job['worker_tid'] and
                      max(row['begin_qpc'], right_job['begin_qpc']) < min(row['end_qpc'], right_job['end_qpc'])]
        for left in left_rows:
            for right in right_rows:
                start = max(left['begin_qpc'], right['begin_qpc'], left_job['begin_qpc'], right_job['begin_qpc'])
                end = min(left['end_qpc'], right['end_qpc'], left_job['end_qpc'], right_job['end_qpc'])
                if start < end and left['processor_index'] != right['processor_index'] and \
                   left['physical_core'] != right['physical_core']:
                    candidates.append((left, right, start, end))
    if not candidates:
        raise AssertionError('Could not isolate the retained distinct-core overlap slices')
    left, right, start, end = max(candidates, key=lambda item: item[3] - item[2])
    left_slice, right_slice = copy.deepcopy(left), copy.deepcopy(right)

    smt_data = copy.deepcopy(parsed)
    smt_data['worker_cpu_slices'] = [left_slice, right_slice]
    smt_data['physical_multicore_proven'] = False
    smt_data['proof'] = None
    smt_map = {'topology': [
        {'group': left['group'], 'logical_processor': left['group_processor'], 'physical_core': left['physical_core']},
        {'group': right['group'], 'logical_processor': right['group_processor'], 'physical_core': left['physical_core']},
    ]}
    right_slice['physical_core'] = left_slice['physical_core']
    smt_data['worker_cpu_slices'][1]['physical_core'] = left_slice['physical_core']
    smt_witness, smt_scored = cpu.independently_find_overlap(
        smt_data, witness_jobs, smt_map, pid, batch, validated_lifetimes)
    if smt_witness is not None or not smt_scored:
        raise AssertionError('Same-physical-core/SMT-only fixture must produce no physical overlap witness')
    cases.append({'case': 'smt_only_overlap_no_proof', 'label': 'Concurrent slices mapped to the same physical core',
                  'outcome': 'ACCEPTED_AS_NO_PHYSICAL_OVERLAP',
                  'logical_processors': [left['processor_index'], right['processor_index']],
                  'shared_physical_core': left_slice['physical_core'],
                  'qpc_intersection': [start, end], 'independent_witness': None,
                  'mutated_input': save_case('smt_only_overlap_no_proof', smt_data)})

    conflict_data = copy.deepcopy(parsed)
    conflict_left, conflict_right = copy.deepcopy(left_slice), copy.deepcopy(right_slice)
    conflict_right.update(processor_index=conflict_left['processor_index'],
                          group=conflict_left['group'], group_processor=conflict_left['group_processor'],
                          physical_core=conflict_left['physical_core'])
    conflict_data['worker_cpu_slices'] = [conflict_left, conflict_right]
    conflict_data['physical_multicore_proven'] = False
    conflict_data['proof'] = None
    conflict_map = {'topology': [{'group': conflict_left['group'],
                                  'logical_processor': conflict_left['group_processor'],
                                  'physical_core': conflict_left['physical_core']}]}
    cases.append(rejected('conflicting_same_logical_cpu', 'Overlapping workers claim one logical CPU', conflict_data,
        lambda: cpu.independently_find_overlap(conflict_data, witness_jobs, conflict_map, pid, batch,
                                               validated_lifetimes), save_case))

    for case_id, change in (
        ('topology_duplicate_processor', lambda data: data['topology'].append(copy.deepcopy(data['topology'][0]))),
        ('topology_out_of_range_core', lambda data: data['topology'][0].update(physical_core=data['processor_count'])),
        ('topology_missing_processor', lambda data: data['topology'].pop()),
    ):
        bad_topology = copy.deepcopy(captured)
        change(bad_topology)
        bad_path = case_dir / (case_id + '.json')
        cases.append(rejected(case_id, 'Malformed processor topology sidecar', bad_topology,
            lambda bad_path=bad_path: cpu.topology(bad_path), save_case))

    if actual_topology != captured or captured != captured_after:
        # The sidecars have a short boot-time sampling difference but must retain the same mapping.
        first = {key: value for key, value in captured.items() if key != 'boot_time_100ns'}
        second = {key: value for key, value in captured_after.items() if key != 'boot_time_100ns'}
        if first != second:
            raise AssertionError('Actual capture-time topology snapshots disagree beyond boot sampling')

    hashes_after = {str(path): sha(path) for path in source_paths}
    if hashes_after != before:
        raise RuntimeError('A frozen regression source changed during the test run')
    report = {
        'status': 'CITY_SITE_CPU_CAPTURE_PURE_CORRELATION_REGRESSIONS_PASS',
        'scope': 'PURE_JOB_LIFETIME_TOPOLOGY_AND_OVERLAP_FUNCTIONS_USING_EXISTING_DECODED_ETL_JSON',
        'source_capture_id': frozen_proof['capture']['path'].split('\\')[-2],
        'source_sdk_process_id': pid,
        'source_batch_id': batch,
        'source_jobs': len(validated_jobs),
        'source_worker_threads': len(validated_lifetimes),
        'source_actual_overlap_witness': calculated_witness,
        'source_actual_raw_overlap_ticks': frozen_proof['independent_raw_overlap_ticks'],
        'source_actual_conservative_overlap_ticks': frozen_proof['independent_overlap_ticks'],
        'qpc_margin_ticks_each_boundary': 1,
        'qpc_raw_overlap_promotion_threshold': 'strictly greater than 2 ticks',
        'qpc_policy_reference': 'https://learn.microsoft.com/en-us/windows/win32/sysinfo/acquiring-high-resolution-time-stamps',
        'qpc_synthetic_boundary_cases': [1, 2, 3],
        'cases': cases,
        'case_count': len(cases),
        'rejected_invalid_cases': sum(row['outcome'] == 'REJECTED' for row in cases),
        'accepted_expected_cases': sum(row['outcome'] in ('ACCEPTED', 'ACCEPTED_AS_NO_PHYSICAL_OVERLAP',
                                                            'ACCEPTED_AS_NO_PROMOTED_WITNESS',
                                                            'ACCEPTED_AS_CONSERVATIVE_WITNESS') for row in cases),
        'source_hashes_before': before,
        'source_hashes_after': hashes_after,
        'frozen_inputs': frozen_rows,
        'actual_reader_output_reused': True,
        'etl_read_or_reopened': False,
        'etl_opened': False,
        'reader_subprocess_executed': False,
        'gamecore_loaded': False,
        'capture_started': False,
        'new_capture_started': False,
        'wpr_started': False,
        'new_gamecore_execution_started': False,
        'build_performed': False,
        'live_capture_header_profile_loss_gates_rerun': False,
        'normal_sdk_matrix_gate_rerun': False,
        'scope_limit': 'Existing strict proof/header/profile/loss/runtime gates are consumed as references only; these regressions exercise pure parsed-data correlation checks and mutated data rejection.',
    }
    report_path = out / 'regressions.json'
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps({'status': report['status'], 'report': str(report_path),
                      'case_count': report['case_count'], 'rejected': report['rejected_invalid_cases'],
                      'accepted': report['accepted_expected_cases'], 'gamecore_loaded': False,
                      'capture_started': False, 'etl_opened': False,
                      'reader_subprocess_executed': False}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
