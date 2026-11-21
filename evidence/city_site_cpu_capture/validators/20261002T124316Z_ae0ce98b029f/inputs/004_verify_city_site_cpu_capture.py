"""Re-read an existing ETL and independently bind CPU slices to actual SDK jobs.

This tool starts neither WPR nor GameCore. Capture failures caused solely by an
older reader may be recovered in a new immutable proof; the original is kept.
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import subprocess
import uuid

from collect_baseline import PROJECT, digest
from probe_world_builder import artifact
from verify_city_site_sdk_candidate import compare_state, fields, inspect_run, signature
from verify_first_turn_candidate import read_artifact
from verify_world_builder_map_object import check_artifacts

ROOT = PROJECT / 'evidence/city_site_cpu_capture'
PROVIDER = '2d76305f-91f4-4d48-9b32-281507669f73'


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def uint(value, bits: int = 64) -> bool:
    return type(value) is int and 0 <= value < 2 ** bits


def local_python_closure() -> list[Path]:
    pending = [Path(__file__).resolve()]
    found: set[Path] = set()
    while pending:
        source = pending.pop()
        if source in found:
            continue
        found.add(source)
        for node in ast.walk(ast.parse(source.read_text(encoding='utf8'))):
            modules = []
            if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                modules = [node.module]
            elif isinstance(node, ast.Import):
                modules = [name.name for name in node.names]
            for module in modules:
                candidate = PROJECT / 'tools' / (module.split('.')[0] + '.py')
                if candidate.is_file() and candidate.resolve() not in found:
                    pending.append(candidate.resolve())
    return sorted(found)


def topology(path: Path) -> dict:
    row = json.loads(path.read_text(encoding='utf8'))
    require(row.get('schema') == 'zerosiscitysite.topology.v1', 'Unknown capture-time topology schema')
    require(uint(row.get('boot_time_100ns')) and row['boot_time_100ns'] > 0 and
            uint(row.get('qpc_frequency')) and row['qpc_frequency'] > 0 and
            uint(row.get('processor_count'), 32) and row['processor_count'] > 1,
            'Topology lacks a valid boot, QPC or processor count')
    entries = row.get('topology', [])
    require(len(entries) == row['processor_count'], 'Capture topology is incomplete')
    keys = set()
    for item in entries:
        require(set(item) == {'group', 'logical_processor', 'physical_core'} and
                all(uint(item[key], 32) for key in item), 'Malformed captured processor entry')
        key = item['group'], item['logical_processor']
        require(key not in keys, 'Duplicate captured logical processor')
        require(item['physical_core'] < row['processor_count'], 'Captured physical core ID is out of range')
        keys.add(key)
    require(keys == {(0, index) for index in range(row['processor_count'])},
            'The single-group logical processor indices are not complete and contiguous')
    cores = {item['physical_core'] for item in entries}
    require(cores == set(range(len(cores))) and len(cores) > 1, 'Captured core IDs are not canonical')
    return row


def job_intervals(parsed: dict, trace: dict, batch: int, pid: int, tile_count: int) -> list[dict]:
    markers = parsed.get('markers', [])
    count = trace['eligible_sites']
    require(len(markers) == count * 2, 'ETL does not retain two markers for every actual SDK job')
    pairs: dict[int, dict] = {}
    for marker in markers:
        require(set(marker) == {'phase', 'batch_id', 'job_index', 'process_id', 'worker_tid', 'site_count', 'qpc'},
                'Unknown job-marker fields')
        require(marker['phase'] in ('begin', 'end') and
                all(uint(marker[key]) for key in marker if key != 'phase') and
                marker['batch_id'] == batch and marker['process_id'] == pid and
                marker['worker_tid'] > 0 and marker['site_count'] == tile_count and marker['qpc'] > 0 and
                0 <= marker['job_index'] < count, 'ETL marker does not belong to the exact captured SDK workload')
        pair = pairs.setdefault(marker['job_index'], {})
        require(marker['phase'] not in pair, 'Duplicate job begin/end marker')
        pair[marker['phase']] = marker
    require(set(pairs) == set(range(count)), 'Missing actual SDK job index')
    jobs = []
    for index, pair in sorted(pairs.items()):
        require(set(pair) == {'begin', 'end'}, 'Unpaired actual SDK job')
        begin, end = pair['begin'], pair['end']
        require(begin['worker_tid'] == end['worker_tid'] and begin['qpc'] < end['qpc'],
                'Job migrated between threads or has no positive QPC interval')
        jobs.append({'job_index': index, 'worker_tid': begin['worker_tid'],
                     'begin_qpc': begin['qpc'], 'end_qpc': end['qpc']})
    actual_counts = Counter(job['worker_tid'] for job in jobs)
    require(dict(actual_counts) == dict(trace['worker_thread_job_counts']),
            'ETL worker IDs/job counts differ from the exact SDK bridge observations')
    return jobs


def lifetimes(parsed: dict, jobs: list[dict], pid: int) -> dict[int, list[tuple[int, int]]]:
    workers = {job['worker_tid'] for job in jobs}
    active: dict[int, int] = {}
    lives: dict[int, list[tuple[int, int]]] = {tid: [] for tid in workers}
    events = parsed.get('thread_events', [])
    require(events, 'No captured worker-thread lifecycle events')
    for event in sorted(events, key=lambda item: item.get('timestamp', -1)):
        require(set(event) == {'event_id', 'process_id', 'thread_id', 'timestamp'} and
                all(uint(value) for value in event.values()) and event['process_id'] == pid and
                event['thread_id'] in workers and event['event_id'] in (1, 2, 3, 4),
                'Unexpected worker lifecycle identity/schema')
        tid, stamp = event['thread_id'], event['timestamp']
        if event['event_id'] in (1, 3):
            require(tid not in active, 'Ambiguous worker start/DCStart lifetime')
            active[tid] = stamp
        else:
            require(tid in active and active[tid] < stamp, 'Worker ended without a unique earlier start')
            lives[tid].append((active.pop(tid), stamp))
    require(not active, 'Capture ended before all scoring workers terminated')
    for job in jobs:
        matches = [life for life in lives[job['worker_tid']]
                   if life[0] <= job['begin_qpc'] < job['end_qpc'] <= life[1]]
        require(len(matches) == 1, 'Scoring QPC interval lacks a unique same-PID/TID lifetime')
    process_events = parsed.get('process_events', [])
    starts, ends = [], []
    for event in process_events:
        require(set(event) == {'event_id', 'process_id', 'timestamp'} and
                all(uint(value) for value in event.values()) and event['process_id'] == pid and
                event['event_id'] in (1, 2, 3, 4, 39), 'Unexpected captured process lifecycle schema')
        if event['event_id'] in (1, 3):
            starts.append(event['timestamp'])
        elif event['event_id'] in (2, 4):
            ends.append(event['timestamp'])
    require(len(starts) == len(ends) == 1 and starts[0] <= min(job['begin_qpc'] for job in jobs) and
            ends[0] >= max(job['end_qpc'] for job in jobs), 'Job interval lacks an unambiguous captured process lifetime')
    return lives


def independently_find_overlap(parsed: dict, jobs: list[dict], captured: dict,
                               pid: int, batch: int, lives: dict) -> tuple[dict | None, list[dict]]:
    mapping = {(row['group'], row['logical_processor']): row['physical_core'] for row in captured['topology']}
    # This capture/reader supports a single processor group. Ambiguous flat CPU
    # indices across groups must fail instead of guessing an SMT/core mapping.
    require({key[0] for key in mapping} == {0}, 'Multiple CPU groups require a separate verified index mapping')
    workers = set(lives)
    slices = parsed.get('worker_cpu_slices', [])
    require(slices, 'No worker CPU scheduling slices were retained')
    for row in slices:
        require(set(row) == {'process_id', 'worker_tid', 'processor_index', 'group', 'group_processor',
                             'physical_core', 'begin_qpc', 'end_qpc'} and
                all(uint(value) for value in row.values()) and row['process_id'] == pid and
                row['worker_tid'] in workers and row['begin_qpc'] < row['end_qpc'],
                'Malformed same-process worker CPU slice')
        key = row['group'], row['group_processor']
        require(key in mapping and mapping[key] == row['physical_core'] and
                row['processor_index'] == row['group_processor'], 'CPU slice disagrees with captured physical topology')
        require(sum(start <= row['begin_qpc'] < row['end_qpc'] <= end
                    for start, end in lives[row['worker_tid']]) == 1,
                'CPU slice extends outside its unique worker lifetime')
    for i, left in enumerate(slices):
        for right in slices[i + 1:]:
            if max(left['begin_qpc'], right['begin_qpc']) >= min(left['end_qpc'], right['end_qpc']):
                continue
            require(left['processor_index'] != right['processor_index'], 'Two captured workers occupy the same logical CPU')
            require(left['worker_tid'] != right['worker_tid'], 'One worker simultaneously occupies two logical CPUs')
    scored = []
    for job in jobs:
        for row in slices:
            if row['worker_tid'] != job['worker_tid']:
                continue
            begin, end = max(job['begin_qpc'], row['begin_qpc']), min(job['end_qpc'], row['end_qpc'])
            if begin < end:
                scored.append({**job, 'begin_qpc': begin, 'end_qpc': end,
                               'logical_processor': row['processor_index'], 'physical_core': row['physical_core']})
    proof = None
    longest = 0
    for i, left in enumerate(scored):
        for right in scored[i + 1:]:
            begin, end = max(left['begin_qpc'], right['begin_qpc']), min(left['end_qpc'], right['end_qpc'])
            if left['job_index'] != right['job_index'] and left['worker_tid'] != right['worker_tid'] and \
               left['physical_core'] != right['physical_core'] and end - begin > longest:
                proof = {'batch_id': batch, 'first_job': left['job_index'], 'first_tid': left['worker_tid'],
                         'first_core': left['physical_core'], 'second_job': right['job_index'],
                         'second_tid': right['worker_tid'], 'second_core': right['physical_core'],
                         'begin_qpc': begin, 'end_qpc': end}
                longest = end - begin
    reader_proof = parsed.get('proof')
    require(parsed.get('physical_multicore_proven') is bool(proof),
            'Reader physical-core conclusion differs from independent interval calculation')
    if proof:
        require(isinstance(reader_proof, dict) and set(reader_proof) == set(proof) and
                all(uint(value) for value in reader_proof.values()) and reader_proof['batch_id'] == batch and
                reader_proof['first_job'] != reader_proof['second_job'] and
                reader_proof['first_tid'] != reader_proof['second_tid'] and
                reader_proof['first_core'] != reader_proof['second_core'] and
                reader_proof['begin_qpc'] < reader_proof['end_qpc'], 'Malformed reader overlap witness')
        for prefix in ('first', 'second'):
            matches = [row for row in scored if row['job_index'] == reader_proof[prefix + '_job'] and
                       row['worker_tid'] == reader_proof[prefix + '_tid'] and
                       row['physical_core'] == reader_proof[prefix + '_core'] and
                       row['begin_qpc'] <= reader_proof['begin_qpc'] < reader_proof['end_qpc'] <= row['end_qpc']]
            require(bool(matches), 'Reader witness does not fit an independently validated score CPU slice')
    else:
        require(reader_proof is None, 'No-overlap conclusion unexpectedly includes a witness')
    return proof, scored


def inspect_capture(capture_id: str, proof_path: Path, comparison_path: Path, output: Path) -> dict:
    capture_path = ROOT / capture_id / 'result.json'
    capture = json.loads(capture_path.read_text(encoding='utf8'))
    check_artifacts(capture)
    hashes_before, hashes_after = capture.get('input_hashes_before'), capture.get('input_hashes_after')
    require(isinstance(hashes_before, dict) and len(hashes_before) == 5 and hashes_before == hashes_after and
            all(isinstance(path, str) and isinstance(value, str) and re.fullmatch(r'[0-9a-f]{64}', value)
                for path, value in hashes_before.items()), 'Missing/invalid capture input hash closure')
    expected_inputs = [PROJECT / 'tools/run_city_site_cpu_capture.py', PROJECT / 'tools/city_site_cpu.wprp',
                       PROJECT / 'tools/run_new_game_probe.py', PROJECT / 'evidence/city_site_cpu_trace/conformance.json',
                       PROJECT / 'evidence/city_site_sdk/build_result.json']
    require(set(hashes_before) == {str(path) for path in expected_inputs} and len(capture.get('inputs', [])) == 5,
            'Capture input identity closure differs')
    for index, source in enumerate(expected_inputs):
        frozen = capture['inputs'][index]
        require(Path(frozen['path']).resolve() == (ROOT / capture_id / 'inputs' / f'{index:02d}_{source.name}').resolve() and
                frozen['sha256'] == hashes_before[str(source)], 'Capture frozen copy differs from its before/after source hash')
    require(capture.get('capture_id') == capture_id and capture.get('capture_started') is True and
            capture.get('gamecore_loaded') is True and capture.get('inputs_unchanged') is True and
            capture.get('input_hashes_before') == capture.get('input_hashes_after'),
            'Recording/runtime inputs did not remain unchanged')
    recovered = capture.get('status') == 'CITY_SITE_CPU_CAPTURE_FAILED'
    require(capture.get('status') == 'ACTUAL_CITY_SITE_CPU_TRACE_RETAINED_PENDING_STRICT_VALIDATION' or
            (recovered and capture.get('error') == 'ETL reader failed rather than producing a scoped scheduling conclusion'),
            'Only a retained capture or a failure isolated to its old reader can be analyzed')
    commands = {row['name']: row for row in capture['commands']}
    require(len(commands) == len(capture['commands']), 'Duplicate capture command records')
    for key in ('global_status_before', 'owned_status_before', 'start', 'sdk_run', 'stop',
                'topology_before', 'topology_after', 'owned_status_after', 'global_status_after'):
        require(key in commands and commands[key]['exit_code'] == 0, 'Failed capture lifecycle command: ' + key)
    for key in ('global_status_before', 'owned_status_before', 'owned_status_after', 'global_status_after'):
        require(b'WPR is not recording' in Path(commands[key]['log']['path']).read_bytes(),
                'Capture did not begin/end with idle WPR sessions')
    instance = 'ZeroSisCitySite_' + capture_id
    require(capture.get('instance_name') == instance and
            all(commands[key]['command'][-2:] == ['-instancename', instance] for key in ('start', 'stop')),
            'Start/stop did not use the uniquely owned recording instance')
    etl = Path(capture['etl']['path'])
    require(etl.resolve() == (PROJECT / 'Build/CitySiteCpuCapture' / capture_id / 'city_site_cpu.etl').resolve(),
            'ETL escaped the owned recording directory')
    before_topology = topology(Path(capture['topology_before']['path']))
    after_topology = topology(Path(capture['topology_after']['path']))
    require({key: value for key, value in before_topology.items() if key != 'boot_time_100ns'} ==
            {key: value for key, value in after_topology.items() if key != 'boot_time_100ns'} and
            abs(before_topology['boot_time_100ns'] - after_topology['boot_time_100ns']) <= 20000000,
            'OS, boot, QPC or processor topology changed during recording')
    capture_reader_proof = read_artifact(capture['inputs'][3]); check_artifacts(capture_reader_proof)
    require(capture_reader_proof.get('status') == 'CITY_SITE_CPU_TRACE_OFFLINE_PASS' and
            all(capture_reader_proof.get('reader_artifact', {}).get(key) == capture.get('reader', {}).get(key)
                for key in ('path', 'sha256')),
            'Capture-time topology generator differs from its retained reader build proof')
    for key in ('topology_before', 'topology_after'):
        require(commands[key]['command'] == [capture['reader']['path'], '--write-topology', capture[key]['path']],
                'Capture-time topology was not generated by the exact retained reader')
    runtime = read_artifact(capture['sdk_run'])
    request = read_artifact(runtime['request']); check_artifacts(request)
    pid, sdk_id = capture.get('process_id'), capture.get('sdk_run_id')
    require(uint(pid, 32) and pid > 0 and runtime.get('process_id') == pid and
            Path(capture['sdk_run']['path']).resolve() == (PROJECT / 'evidence/save_restore' / sdk_id / 'result.json').resolve() and
            Path(runtime['request']['path']).resolve() == (PROJECT / 'evidence/save_restore' / sdk_id / 'request.json').resolve() and
            request.get('run_id') == sdk_id and
            runtime.get('city_site_cpu_trace_enabled') is True and request.get('city_site_cpu_trace_enabled') is True and
            request.get('diagnostic_environment_overrides') == {'ZEROSIS_CITY_SITE_CPU_TRACE': '1'} and
            request.get('inherited_cpu_trace_environment_removed') is True,
            'Actual runtime PID or explicit trace opt-in does not match the capture')
    sdk = read_artifact(request['city_site_sdk_build']); check_artifacts(sdk)
    require(sdk.get('cpu_trace_provider_guid') == PROVIDER and sdk.get('cpu_trace_default_enabled') is False,
            'Captured GameCore does not retain the exact optional trace provider')
    options = argparse.Namespace(ui_popups=True, fixture_promotions=True, fixture_unit_actions=True)
    actual = inspect_run(sdk_id, options, output)
    require(actual['city_site_workers'] == 4 and actual['final_turn'] == 50 and len(actual['city_site_traces']) == 1 and
            actual['city_site_traces'][0]['turn'] == 43 and actual['city_site_traces'][0]['eligible_sites'] == 95,
            'This capture must contain one normal CitySite batch from the bounded 50-turn profile')
    comparison = json.loads(comparison_path.read_text(encoding='utf8')); check_artifacts(comparison)
    require(comparison.get('status') == 'ACTUAL_SDK_CITY_SITE_ORDERED_RESULTS_AND_RESTORE_PASS',
            'Missing passing serial/worker runtime comparison')
    baselines = [row for row in comparison['runs'] if row['language'] == actual['language'] and row['city_site_workers'] == 0]
    require(len(baselines) == 1, 'Missing unique same-language scalar baseline')
    baseline = baselines[0]
    require(actual['inputs'] == baseline['inputs'] and actual['workers'] == baseline['workers'],
            'CPU capture changed the retained host/SDK/runtime input identities')
    compare_state(actual, baseline)
    require(signature(actual['city_site_traces']) == signature(baseline['city_site_traces']) and
            actual['official_ui_signature'] == baseline['official_ui_signature'],
            'Enabling CPU diagnostics changed ordered yields or official popup behavior')
    stdout = Path(runtime['stdout']['path']).read_text(encoding='utf8')
    trace_lines = re.findall(r'^ZEROSIS_CITY_SITE_CPU_TRACE ([^\r\n]+)$', stdout, re.M)
    require(len(trace_lines) == 1, 'Expected one exact CPU trace batch summary')
    batch_row = fields(trace_lines[0])
    require(set(batch_row) == {'batch_id', 'process_id', 'requested_workers', 'sites', 'workers_started'} and
            all(re.fullmatch(r'[1-9]\d*', value) for value in batch_row.values()), 'Malformed CPU batch summary')
    batch_row = {key: int(value) for key, value in batch_row.items()}
    trace = actual['city_site_traces'][0]
    require(batch_row['process_id'] == pid and batch_row['requested_workers'] == 4 and
            batch_row['sites'] == trace['eligible_sites'] and batch_row['workers_started'] == trace['workers_started'] and
            batch_row['batch_id'] == trace['call_id'] == 1,
            'CPU batch summary differs from actual SDK score accounting')
    require(re.search(r'^ZEROSIS_CITY_SITE_CPU_TRACE ' + re.escape(trace_lines[0]) +
                      r'\nZEROSIS_CITY_SITE_VALUES call_id=1 [^\n]+\nZEROSIS_CITY_SITE_TRACE [^\n]+call_id=1 ',
                      stdout, re.M), 'CPU batch summary is not adjacent to its exact ordered SDK result/call')
    bridge_source = Path(sdk['bridge_source']['path']).read_text(encoding='utf8')
    require(all(token in bridge_source for token in ('next_trace_batch{1}', 'next_trace_batch.fetch_add(1,',
            'CitySiteCpuTraceBatch trace(trace_id)', 'CitySiteOperation(invocation, trace)',
            'CitySiteCpuTraceJob trace(*trace_, input.job_index,',
            'scored = zerosis::city_site::evaluate_all(input.site);',
            'static_cast<unsigned long long>(trace_id)', 'count, metrics->workers_started')),
            'Frozen bridge does not bind its unique batch ID to the actual scoring operation/accounting')
    reader_proof = json.loads(proof_path.read_text(encoding='utf8')); check_artifacts(reader_proof)
    require(reader_proof.get('status') == 'CITY_SITE_CPU_TRACE_OFFLINE_PASS' and
            reader_proof.get('schema') == 'zerosiscitysite.cpu_trace_conformance.v1',
            'Reader lacks passing retained component/build proof')
    for first, last in (('source_hashes_before', 'source_hashes_after'),
                        ('dependency_closure_hashes_before', 'dependency_closure_hashes_after'),
                        ('toolchain_inputs_before', 'toolchain_inputs_after')):
        require(bool(reader_proof.get(first)) and reader_proof[first] == reader_proof.get(last),
                'Reader source/dependency/toolchain inputs changed: ' + first)
    build_root = Path(reader_proof['retained_build']).resolve()
    for relative, expected in reader_proof['artifacts']['build_files'].items():
        path = (build_root / relative).resolve()
        require(path.is_relative_to(build_root) and path.is_file() and digest(path) == expected,
                'Retained reader build file changed: ' + relative)
    for mode in ('O2', 'Od'):
        checked = reader_proof.get('builds', {}).get(mode, {})
        require(type(checked.get('checks')) is int and checked['checks'] >= 14 and
                checked.get('capture_started') is False and checked.get('gamecore_loaded') is False,
                'Reader component did not pass both optimized and unoptimized offline cases')
    require(reader_proof['frozen_inputs']['provider']['sha256'] == sdk['cpu_trace_source']['sha256'] and
            reader_proof['frozen_inputs']['header']['sha256'] == sdk['cpu_trace_header']['sha256'],
            'Reader component and actual GameCore were built with different marker contracts')
    reader = Path(reader_proof['reader_artifact']['path'])
    require(build_root.is_relative_to((PROJECT / 'Build').resolve()) and
            reader.resolve() == build_root / 'reader_o2/city_site_cpu_trace_reader.exe' and
            reader_proof['builds']['reader_help']['exe_sha256'] == reader_proof['reader_artifact']['sha256'],
            'Reader executable is not the exact retained project reader build')
    reader_source = Path(reader_proof['frozen_inputs']['reader']['path']).read_text(encoding='utf8')
    require('PROCESS_TRACE_MODE_EVENT_RECORD | PROCESS_TRACE_MODE_RAW_TIMESTAMP' in reader_source,
            'Frozen reader did not preserve raw ETL/QPC timestamps')
    frozen_reader = output / 'inputs/city_site_cpu_trace_reader.exe'
    shutil.copy2(reader, frozen_reader)
    require(digest(frozen_reader) == reader_proof['reader_artifact']['sha256'], 'Reader changed while freezing its executable')
    command = [str(frozen_reader), str(etl), '--topology', capture['topology_before']['path']]
    decoded = subprocess.run(command, cwd=PROJECT, capture_output=True,
                             creationflags=subprocess.CREATE_NO_WINDOW, timeout=120)
    (output / 'reader.stdout.json').write_bytes(decoded.stdout)
    (output / 'reader.stderr.log').write_bytes(decoded.stderr)
    require(decoded.returncode in (0, 3) and not decoded.stderr, 'Frozen ETL reader failed; inspect retained logs')
    parsed = json.loads(decoded.stdout.decode('utf8'))
    require(parsed.get('schema') == 'zerosiscitysitecpu.v1' and parsed.get('etl_opened') is True and
            parsed.get('clock_is_qpc') is True and parsed.get('qpc_frequency') == before_topology['qpc_frequency'] and
            parsed.get('topology') == before_topology['topology'], 'Decoded ETL clock/topology differs from capture-time input')
    binding = parsed.get('topology_binding', {})
    require(binding.get('same_current_boot') is True and binding.get('topology_source') == 'captured_sidecar' and
            binding.get('etl_processor_count') == before_topology['processor_count'], 'ETL topology/boot is unbound')
    require(uint(binding.get('etl_boot_time_100ns')) and
            abs(binding['etl_boot_time_100ns'] - before_topology['boot_time_100ns']) <= 20000000 and
            binding.get('captured_sidecar_boot_time_100ns') == before_topology['boot_time_100ns'] and
            binding.get('etl_perf_frequency') == before_topology['qpc_frequency'] and
            binding.get('etl_clock_type_reserved_flags') == 1,
            'Raw ETL header clock/boot fields disagree with the capture-time QPC/topology binding')
    loss, counts = parsed.get('loss', {}), parsed.get('cswitch_counts', {})
    require(set(loss) == {'events_lost', 'buffers_lost', 'reader_events_lost', 'buffers_read'} and
            set(counts) == {'all', 'worker_related', 'worker_related_unmapped_cpu'} and
            all(type(loss.get(key)) is int and loss[key] == 0 for key in ('events_lost', 'buffers_lost', 'reader_events_lost')) and
            uint(loss.get('buffers_read')) and loss['buffers_read'] > 0 and
            uint(counts.get('all')) and counts['all'] > 0 and uint(counts.get('worker_related')) and
            0 < counts['worker_related'] <= counts['all'] and
            type(counts.get('worker_related_unmapped_cpu')) is int and counts['worker_related_unmapped_cpu'] == 0,
            'ETL lost events/buffers or worker CPU identity is incomplete')
    jobs = job_intervals(parsed, trace, batch_row['batch_id'], pid,
                         actual['fixture_rules_city_site_definitions']['AI_CITY_SPECIALIZATION_YIELD_NUM_TILES_CONSIDERED'])
    lives = lifetimes(parsed, jobs, pid)
    proof, scored = independently_find_overlap(parsed, jobs, before_topology, pid, batch_row['batch_id'], lives)
    require(decoded.returncode == (0 if proof else 3) and parsed.get('status') ==
            ('ETW_DISTINCT_CORE_OVERLAP_PROVEN' if proof else 'ETW_TRACE_READ_NO_PROOF'), 'Reader exit/status disagrees with validated proof')
    return {'status': 'ACTUAL_SDK_CITY_SITE_DISTINCT_PHYSICAL_CORE_OVERLAP_PASS' if proof else
                     'ACTUAL_SDK_CITY_SITE_CPU_TRACE_VALID_NO_DISTINCT_CORE_OVERLAP',
            'capture': artifact(capture_path), 'previous_reader_failure_recovered_without_new_capture': recovered,
            'etl': capture['etl'], 'reader_build_proof': artifact(proof_path), 'reader': artifact(reader),
            'executed_frozen_reader': artifact(frozen_reader), 'reader_source': reader_proof['frozen_inputs']['reader'],
            'scoring_interval_source': sdk['cpu_trace_source'], 'sdk_bridge_source': sdk['bridge_source'],
            'capture_topology_generator_build_proof': capture['inputs'][3], 'raw_etl_topology_binding': binding,
            'reader_command': command, 'reader_stdout': artifact(output / 'reader.stdout.json'),
            'reader_stderr': artifact(output / 'reader.stderr.log'), 'topology_before': capture['topology_before'],
            'topology_after': capture['topology_after'], 'runtime_comparison': artifact(comparison_path),
            'actual_runtime': actual, 'sdk_process_id': pid, 'batch_summary': batch_row,
            'jobs': jobs, 'validated_thread_lifetimes': lives, 'score_cpu_slices': scored,
            'independent_overlap_witness': proof, 'independent_overlap_ticks': proof['end_qpc'] - proof['begin_qpc'] if proof else 0,
            'qpc_frequency': before_topology['qpc_frequency'], 'zero_etl_event_buffer_loss': True,
            'same_language_scalar_archive_and_ordered_yield_equality': True,
            'physical_multicore_verified': bool(proof), 'gamecore_loaded_during_capture': True,
            'new_capture_started': False, 'new_gamecore_execution_started': False,
            'performance_improvement_verified': False, 'complete_engine_multicore_verified': False,
            'renderer_verified': False, 'retail_save_compatibility_verified': False, 'accepted_stage_promoted': False,
            'proof_scope': 'NORMAL_FIND_BEST_SITES_SCORE_INTERVALS_AND_CSWITCH_SCHEDULED_CPU_SLICES_NOT_SPEEDUP'}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', required=True)
    parser.add_argument('--reader-proof', required=True, type=Path)
    parser.add_argument('--comparison', required=True, type=Path)
    args = parser.parse_args()
    if not re.fullmatch(r'\d{8}T\d{6}Z_[0-9a-f]{12}', args.capture):
        parser.error('Only an existing immutable capture ID is accepted')
    output = ROOT / 'validators' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ_') + uuid.uuid4().hex[:12])
    frozen = output / 'inputs'
    frozen.mkdir(parents=True, exist_ok=False)
    sources = local_python_closure()
    sources.extend((args.reader_proof.resolve(), args.comparison.resolve(), ROOT / args.capture / 'result.json'))
    before = {str(path): digest(path) for path in sources}
    records = []
    frozen_arguments = {}
    for index, source in enumerate(sources):
        target = frozen / (f'{index:03d}_' + source.name)
        shutil.copy2(source, target)
        require(digest(target) == before[str(source)], 'Verification input changed while freezing')
        records.append({'original_path': str(source), **artifact(target)})
        frozen_arguments[source.resolve()] = target
    report = {'status': 'ACTUAL_CITY_SITE_CPU_TRACE_VALIDATION_FAILED', 'frozen_inputs': records,
              'physical_multicore_verified': False, 'new_capture_started': False,
              'new_gamecore_execution_started': False, 'performance_improvement_verified': False,
              'accepted_stage_promoted': False}
    code = 2
    try:
        report.update(inspect_capture(args.capture, frozen_arguments[args.reader_proof.resolve()],
                                      frozen_arguments[args.comparison.resolve()], output))
        after = {str(path): digest(path) for path in sources}
        require(before == after, 'A verification input changed during ETL reanalysis')
        report.update(input_hashes_before=before, input_hashes_after=after, inputs_unchanged=True)
        check_artifacts(report)
        code = 0
    except Exception as error:
        report.update(status='ACTUAL_CITY_SITE_CPU_TRACE_VALIDATION_FAILED', error=str(error),
                      physical_multicore_verified=False)
    target = output / 'conformance.json'
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    if code == 0:
        pointer = ROOT / ('conformance.json.tmp-' + uuid.uuid4().hex)
        pointer.write_text(json.dumps(artifact(target), indent=2) + '\n', encoding='utf8')
        pointer.replace(ROOT / 'conformance.json')
    print(json.dumps({'status': report['status'], 'proof': artifact(target), 'error': report.get('error'),
                      'physical_multicore_verified': report['physical_multicore_verified']}, ensure_ascii=False), flush=True)
    return code


if __name__ == '__main__':
    raise SystemExit(main())
