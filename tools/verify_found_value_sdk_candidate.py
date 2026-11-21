"""Verify actual SDK Found-value candidate result vectors and state parity."""
import argparse
import ast
import hashlib
import json
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from collect_baseline import PROJECT, digest
from probe_world_builder import artifact
from verify_city_site_sdk_candidate import compare_state, inspect_run
from verify_extended_turns import inspect_extended
from verify_first_turn_candidate import read_artifact
from verify_world_builder_map_object import check_artifacts

ROOT = PROJECT / 'evidence/found_value_sdk_runtime'
WORKERS = (0, 1, 2, 4)
TRACE_KEYS = ('version', 'call_id', 'turn', 'player', 'starting_loc', 'mode',
              'requested_workers', 'map_plots', 'revealed', 'helper_unique_plots',
              'snapshot_us', 'worker_us', 'shadow_us', 'reduction_us', 'total_us',
              'jobs_total', 'jobs_started', 'jobs_completed', 'workers_started',
              'used_threads', 'max_overlap', 'worker_tids_job_counts')
INTEGER_KEYS = set(TRACE_KEYS) - {'mode', 'worker_tids_job_counts'}
TAG_VALUES = 'ZEROSIS_FOUND_VALUE_VALUES '
TAG_AREAS = 'ZEROSIS_FOUND_VALUE_AREAS '
TAG_TRACE = 'ZEROSIS_FOUND_VALUE_TRACE '


def parse_kv(text):
    result = {}
    for word in text.split():
        if word.count('=') != 1:
            raise RuntimeError('Malformed Found-value trace field')
        key, value = word.split('=', 1)
        if key in result:
            raise RuntimeError('Duplicate Found-value trace field')
        result[key] = value
    return result


def parse_records(text, area=False):
    if text == '-':
        return []
    if not text:
        raise RuntimeError('Empty Found-value record list must use the explicit dash sentinel')
    result = []
    for item in text.split(';'):
        if not re.fullmatch(r'-?\d+:-?\d+', item):
            raise RuntimeError('Malformed Found-value ordered record')
        key, value = map(int, item.split(':'))
        if not -(2**31) <= key <= 2**31 - 1 or not -(2**31) <= value <= 2**31 - 1:
            raise RuntimeError('Found-value record exceeds the signed native-int range')
        if result and (key <= result[-1][0] if not area else False):
            raise RuntimeError('Found-value plot records are not in strict map-index order')
        if area and any(old_key == key for old_key, _ in result):
            raise RuntimeError('Duplicate area identifier in Found-value area records')
        result.append((key, value))
    return result


def parse_trace_block(output, requested_workers, expected_player=None, final_turn=None):
    lines = output.splitlines()
    restore_boundaries = [index for index, line in enumerate(lines)
                          if line == 'NATIVE_RESTORE_FRESH_SESSION=true']
    if len(restore_boundaries) != 1:
        raise RuntimeError('Found-value runtime comparison requires one fresh-session restore boundary')
    positions = [index for index, line in enumerate(lines) if line.startswith(TAG_VALUES)]
    all_trace = [index for index, line in enumerate(lines) if line.startswith(TAG_TRACE)]
    all_areas = [index for index, line in enumerate(lines) if line.startswith(TAG_AREAS)]
    if not positions or len(positions) != len(all_trace) or len(positions) != len(all_areas):
        raise RuntimeError('Found-value result/area/trace record counts differ or are empty')
    calls = []
    for index in positions:
        if index + 2 >= len(lines) or not lines[index + 1].startswith(TAG_AREAS) or \
           not lines[index + 2].startswith(TAG_TRACE):
            raise RuntimeError('Found-value VALUES, AREAS and TRACE lines are not adjacent and ordered')
        values_fields = parse_kv(lines[index][len(TAG_VALUES):])
        areas_fields = parse_kv(lines[index + 1][len(TAG_AREAS):])
        trace_fields = parse_kv(lines[index + 2][len(TAG_TRACE):])
        if set(values_fields) != {'call_id', 'records'} or set(areas_fields) != {'call_id', 'records'} or \
           values_fields['call_id'] != areas_fields['call_id'] or \
           not re.fullmatch(r'[1-9]\d*', values_fields['call_id']):
            raise RuntimeError('Found-value ordered payload identity differs')
        if tuple(trace_fields) != TRACE_KEYS:
            raise RuntimeError('Found-value metric field schema/order differs')
        if any(not re.fullmatch(r'\d+', trace_fields[key]) for key in INTEGER_KEYS):
            raise RuntimeError('Found-value metrics contain a negative or non-integral field')
        trace = {key: int(value) if key in INTEGER_KEYS else value
                 for key, value in trace_fields.items()}
        trace['call_id'] = int(trace['call_id'])
        if trace['version'] != 1 or trace['call_id'] != int(values_fields['call_id']) or \
           trace['call_id'] != int(areas_fields['call_id']):
            raise RuntimeError('Found-value trace version or call identity differs')
        values = parse_records(values_fields['records'])
        areas = parse_records(areas_fields['records'], area=True)
        if trace['map_plots'] != len(values) or trace['map_plots'] <= 0 or \
           [index for index, _ in values] != list(range(trace['map_plots'])) or \
           any(value < -1 for _, value in values) or \
           sum(value != -1 for _, value in values) != trace['revealed'] or \
           not 0 <= trace['revealed'] <= trace['map_plots']:
            raise RuntimeError('Found-value map vector is incomplete or revealed count differs')
        if trace['starting_loc'] not in (0, 1) or trace['player'] < 0 or trace['player'] >= 64 or \
           (expected_player is not None and trace['player'] != expected_player) or \
           (final_turn is not None and trace['turn'] > final_turn):
            raise RuntimeError('Found-value player/turn/starting-location identity differs')
        if trace['mode'] not in ('scalar-original', 'owned-worker'):
            raise RuntimeError('Unknown Found-value execution mode')
        scalar = requested_workers == 0 or trace['starting_loc'] == 1
        expected_mode = 'scalar-original' if scalar else 'owned-worker'
        expected_requested = 0 if scalar else requested_workers
        if trace['mode'] != expected_mode or trace['requested_workers'] != expected_requested:
            raise RuntimeError('Found-value request used an unexpected scalar/worker route')
        timing_keys = ('snapshot_us', 'worker_us', 'shadow_us', 'reduction_us', 'total_us')
        job_keys = ('jobs_total', 'jobs_started', 'jobs_completed', 'workers_started',
                    'used_threads', 'max_overlap', 'helper_unique_plots')
        tids = []
        tids_text = trace['worker_tids_job_counts']
        if tids_text != '-':
            for entry in tids_text.split(','):
                if not re.fullmatch(r'[1-9]\d*:[1-9]\d*', entry):
                    raise RuntimeError('Malformed Found-value worker thread/job record')
                tids.append(tuple(map(int, entry.split(':'))))
            if len({tid for tid, _ in tids}) != len(tids):
                raise RuntimeError('Duplicate Found-value worker thread identifier')
        if scalar:
            if any(trace[key] != 0 for key in timing_keys[:-1]) or \
               any(trace[key] != 0 for key in job_keys) or tids:
                raise RuntimeError('Scalar Found-value route reported worker/capture metrics')
        else:
            count = trace['revealed']
            if trace['jobs_total'] != count or trace['jobs_started'] != count or \
               trace['jobs_completed'] != count or trace['workers_started'] != min(requested_workers, count) or \
               trace['used_threads'] != len(tids) or sum(jobs for _, jobs in tids) != count or \
               trace['helper_unique_plots'] > trace['map_plots'] or \
               (count and not 1 <= trace['max_overlap'] <= trace['used_threads'] <= trace['workers_started']) or \
               (not count and (trace['max_overlap'] or trace['used_threads'] or tids)):
                raise RuntimeError('Owned-worker Found-value accounting differs from completed work')
            if sum(trace[key] for key in timing_keys[:-1]) > trace['total_us']:
                raise RuntimeError('Found-value phase timings exceed total capture time')
        session = sum(boundary < index for boundary in restore_boundaries)
        calls.append({'session': session, 'call_id': trace['call_id'], 'turn': trace['turn'], 'player': trace['player'],
                      'starting_loc': trace['starting_loc'], 'values': values, 'areas': areas,
                      'trace': trace, 'worker_thread_job_counts': tids})
    previous = {}
    for call in calls:
        session = call['session']
        if session in previous and call['call_id'] <= previous[session]:
            raise RuntimeError('Found-value calls are not in increasing per-session call-id order')
        previous[session] = call['call_id']
    if set(previous) != {0, 1}:
        raise RuntimeError('Found-value traces do not cover both fresh SDK sessions')
    if requested_workers > 0 and not any(call['trace']['mode'] == 'owned-worker' for call in calls):
        raise RuntimeError('No owned-worker Found-value call occurred despite worker opt-in')
    return calls


def semantic_signature(calls):
    return [{key: call[key] for key in ('session', 'call_id', 'turn', 'player', 'starting_loc', 'values', 'areas')}
            | {'map_plots': call['trace']['map_plots'], 'revealed': call['trace']['revealed']}
            for call in calls]


def local_python_closure(entry):
    tools = PROJECT / 'tools'
    pending = [entry.resolve()]
    closure = {}
    edges = []
    while pending:
        path = pending.pop()
        if path in closure:
            continue
        if not path.is_file() or not path.is_relative_to(tools):
            raise RuntimeError('Python validator closure escaped the tools directory')
        tree = ast.parse(path.read_text(encoding='utf8'), filename=str(path))
        closure[path] = tree
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names.append(node.module)
            for name in names:
                module = tools / (name.replace('.', '/') + '.py')
                if module.is_file():
                    edges.append((path, module))
                    pending.append(module.resolve())
    return closure, edges


def inspect_found_run(run_id, options, output_dir):
    row = inspect_run(run_id, options, output_dir)
    result = read_artifact(row['result'])
    request = read_artifact(result['request'])
    output = Path(result['stdout']['path']).read_text(encoding='utf8')
    calls = parse_trace_block(output, row['found_value_workers'], final_turn=row['final_turn'])
    if any(call['trace']['map_plots'] != row['observation'][2] for call in calls):
        raise RuntimeError('Found-value vectors do not match the verified SDK map dimensions')
    row['found_value_calls'] = calls
    row['found_value_trace_enabled'] = request.get('found_value_trace_enabled') is True
    if row['found_value_trace_enabled'] is not True:
        raise RuntimeError('Found-value trace was not explicitly enabled in the request')
    return row


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', action='append', required=True)
    parser.add_argument('--reference-run', action='append', default=[])
    parser.add_argument('--ui-popups', action='store_true')
    parser.add_argument('--fixture-promotions', action='store_true')
    parser.add_argument('--fixture-unit-actions', action='store_true')
    args = parser.parse_args()
    if args.fixture_promotions and not args.ui_popups or args.fixture_unit_actions and not args.fixture_promotions:
        parser.error('Promotion/action profiles require the same explicit UI profiles as their runner')
    if len(args.run) not in (4, 6, 8) or len(set(args.run)) != len(args.run) or \
       len(args.reference_run) not in (0, 2) or len(set(args.reference_run)) != len(args.reference_run):
        parser.error('Provide EN/KO Found-value runs with worker-zero baselines; optional references cover both languages')
    all_ids = args.run + args.reference_run
    if any(not re.fullmatch(r'\d{8}T\d{6}Z_[0-9a-f]{12}', run_id) for run_id in all_ids):
        parser.error('Only existing isolated run IDs are accepted')
    closure, edges = local_python_closure(Path(__file__).resolve())
    if len({path.name.casefold() for path in closure}) != len(closure):
        raise RuntimeError('Python validator closure contains colliding frozen filenames')
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ_') + uuid.uuid4().hex[:12]
    directory = ROOT / run_id
    frozen_dir = directory / 'validators'
    frozen_dir.mkdir(parents=True, exist_ok=False)
    before = {path: digest(path) for path in closure}
    frozen_records = []
    for path in sorted(closure, key=lambda value: str(value).casefold()):
        target = frozen_dir / path.name
        shutil.copy2(path, target)
        if digest(target) != before[path]:
            raise RuntimeError('A Python validator changed while freezing its source')
        frozen_records.append({'original_source_path': str(path),
                               'original_source_sha256': before[path],
                               'frozen': artifact(target)})
    options = SimpleNamespace(ui_popups=args.ui_popups,
                              fixture_promotions=args.fixture_promotions,
                              fixture_unit_actions=args.fixture_unit_actions,
                              sdk_found_values=True, found_value_workers=None)
    rows = [inspect_found_run(item, options, directory) for item in args.run]
    keyed = {(row['language'], row['found_value_workers']): row for row in rows}
    settings = sorted({row['found_value_workers'] for row in rows})
    if not {0, 4}.issubset(settings) or len(keyed) != len(rows) or \
       set(keyed) != {(language, worker) for language in ('en_US', 'ko_KR') for worker in settings}:
        raise RuntimeError('Found-value run matrix must cover worker zero/four baselines in both languages')
    if any(row['inputs'] != rows[0]['inputs'] or row['workers'] != rows[0]['workers'] or
           row['final_turn'] != rows[0]['final_turn'] for row in rows[1:]):
        raise RuntimeError('Found-value runs used different SDK inputs, exploration workers or final turns')
    comparisons = []
    for language in ('en_US', 'ko_KR'):
        baseline = keyed[language, 0]
        for workers in settings[1:]:
            actual = keyed[language, workers]
            compare_state(actual, baseline)
            if semantic_signature(actual['found_value_calls']) != semantic_signature(baseline['found_value_calls']):
                raise RuntimeError('Found-value workers changed an ordered score vector, area total or owner-call sequence')
            if args.ui_popups and actual.get('official_ui_signature') != baseline.get('official_ui_signature'):
                raise RuntimeError('Found-value workers changed official UI RNG or ranking behavior')
            comparisons.append({'language': language, 'workers': workers, 'archives_compared': 3,
                                'all_ordered_plot_scores_equal': True,
                                'all_area_totals_and_order_equal': True,
                                'all_extended_state_and_event_snapshots_equal': True,
                                'official_ui_rng_equal': bool(args.ui_popups)})
    if semantic_signature(keyed['en_US', 0]['found_value_calls']) != \
       semantic_signature(keyed['ko_KR', 0]['found_value_calls']):
        raise RuntimeError('Language changed the scalar Found-value ordered results or area totals')
    if args.ui_popups and keyed['en_US', 0].get('official_ui_signature') != keyed['ko_KR', 0].get('official_ui_signature'):
        raise RuntimeError('Language changed official UI RNG or ranking behavior')

    reference_checks = []
    if args.reference_run:
        references = [inspect_extended(item, ui_popups=args.ui_popups,
                                       fixture_promotions=args.fixture_promotions,
                                       fixture_unit_actions=args.fixture_unit_actions,
                                       sdk_city_sites=True) for item in args.reference_run]
        if {row['language'] for row in references} != {'en_US', 'ko_KR'} or any(row['workers'] != 0 for row in references):
            raise RuntimeError('Original SDK references must be scalar and cover both languages')
        for original in references:
            current = keyed[original['language'], 0]
            if {name: value for name, value in original['inputs'].items()
                if name not in ('CvGameCoreDLL_Expansion2_x64.dll', 'bundle.manifest')} != \
               {name: value for name, value in current['inputs'].items()
                if name not in ('CvGameCoreDLL_Expansion2_x64.dll', 'bundle.manifest')}:
                raise RuntimeError('Original SDK comparison changed inputs beyond GameCore and bundle identity')
            compare_state(current, original, allow_sdk_identity_change=True)
            if args.ui_popups:
                ui = inspect_run(original['run_id'], SimpleNamespace(ui_popups=True,
                    fixture_promotions=args.fixture_promotions, fixture_unit_actions=args.fixture_unit_actions,
                    sdk_found_values=False, found_value_workers=None), directory)
                if current.get('official_ui_signature') != ui.get('official_ui_signature'):
                    raise RuntimeError('Found-value serial instrumentation changed official popup RNG/behavior')
            reference_checks.append({'language': original['language'], 'reference': original['result'],
                'original_sdk_state_and_archive_payloads_equal': True,
                'bundle_identity_compared_after_exact_gamecore_hash_line_substitution': True})
    if any(digest(path) != value for path, value in before.items()):
        raise RuntimeError('A Python verifier source changed during Found-value runtime verification')
    source_integrity = [{'path': str(path), 'sha256_before': value,
                         'sha256_after': digest(path), 'unchanged': digest(path) == value}
                        for path, value in sorted(before.items(), key=lambda item: str(item[0]).casefold())]
    report = {'status': 'ACTUAL_SDK_FOUND_VALUE_ORDERED_RESULTS_AND_RESTORE_PASS',
              'validators': frozen_records,
              'validator_import_edges': [{'from': str(left), 'to': str(right)} for left, right in edges],
              'validator_ast_closure_files': len(closure), 'validator_source_integrity': source_integrity,
              'validator_inputs_unchanged': True, 'runs': rows, 'comparisons': comparisons,
              'original_sdk_references': reference_checks, 'found_value_worker_settings': settings,
              'all_ordered_plot_scores_compared_directly': True,
              'all_area_totals_compared_in_source_order': True,
              'same_language_archive_and_continuation_comparison': True,
              'gamecore_loaded': True, 'physical_multicore_verified': False,
              'performance_improvement_verified': False, 'retail_save_compatibility_verified': False,
              'interactive_gameplay_verified': False, 'complete_game_equivalence_verified': False,
              'accepted_stage_promoted': False, 'active_sdk_updated': False, 'stage_updated': False,
              'scope': 'ACTUAL_ISOLATED_X64_FOUNDED_SITE_SCORE_VECTORS_AREA_TOTALS_SHADOW_AND_NATIVE_RESTORE'}
    check_artifacts(report)
    target = directory / 'conformance.json'
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    pointer = ROOT / 'latest.json'
    pointer_tmp = ROOT / ('latest.json.tmp-' + uuid.uuid4().hex)
    pointer_tmp.write_text(json.dumps(artifact(target), indent=2) + '\n', encoding='utf8')
    pointer_tmp.replace(pointer)
    print(json.dumps({'status': report['status'], 'runs': len(rows),
                      'workers': settings, 'evidence': artifact(target)}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
