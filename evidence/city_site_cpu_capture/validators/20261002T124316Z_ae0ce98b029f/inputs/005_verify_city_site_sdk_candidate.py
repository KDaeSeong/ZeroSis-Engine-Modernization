"""Strict actual SDK city-site scoring, archive, command and official UI comparison.

Scoring invocation overlap is a scheduling observation. This report does not
certify simultaneous physical CPU execution, performance improvement or retail
equivalence. No game/fixture input, SDK file or accepted bundle is modified.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import sqlite3
import struct
import uuid
from datetime import datetime, timezone

from collect_baseline import PROJECT, digest
from probe_world_builder import artifact
from verify_extended_turns import VALIDATORS, inspect_extended
from verify_ui_popup_runtime import inspect_popup
from verify_world_builder_map_object import check_artifacts
from verify_first_turn_candidate import read_artifact

ROOT = PROJECT / 'evidence/city_site_runtime'
WORKERS = (0, 1, 2, 4)
FNV_SCOPE = 'plot_index_u32le_then_food_prod_gold_science_i32le_per_eligible_plot'
TEXT_KEYS = {'mode', 'ordered_output_fnv1a64', 'fnv_scope', 'worker_tids_job_counts', 'input_cells_scope'}
INTEGER_KEYS = {'abi', 'config', 'status', 'call_id', 'player', 'turn', 'cities',
                'requested_workers', 'eligible_sites', 'input_cells', 'best_food',
                'best_production', 'best_gold', 'best_science', 'snapshot_us',
                'worker_us', 'shadow_us', 'reduction_us', 'total_us', 'jobs_total',
                'jobs_started', 'jobs_completed', 'workers_started', 'used_threads', 'max_overlap'}


def fields(line):
    result = {}
    for word in line.split():
        if word.count('=') != 1:
            raise RuntimeError('Malformed city-site trace field')
        key, value = word.split('=', 1)
        if key in result:
            raise RuntimeError('Duplicate city-site trace key')
        result[key] = value
    return result


def parse_values(line):
    values = fields(line)
    if set(values) != {'call_id', 'records'} or not re.fullmatch(r'[1-9]\d*', values['call_id']):
        raise RuntimeError('City-site ordered value record schema differs')
    records = []
    if values['records'] not in ('', '-'):
        for item in values['records'].split(';'):
            if not re.fullmatch(r'\d+:-?\d+,-?\d+,-?\d+,-?\d+', item):
                raise RuntimeError('Malformed ordered city-site value')
            index, yields = item.split(':', 1)
            row = [int(index), *map(int, yields.split(','))]
            if not 0 <= row[0] < 960 or any(not -2147483648 <= value <= 2147483647 for value in row[1:]):
                raise RuntimeError('Ordered value exceeds the actual map or native int32 range')
            if records and row[0] <= records[-1][0]:
                raise RuntimeError('Eligible plots are not in unique ascending map order')
            records.append(row)
    encoded = b''.join(struct.pack('<I4i', *row) for row in records)
    checksum = 14695981039346656037
    for value in encoded:
        checksum = ((checksum ^ value) * 1099511628211) & 0xffffffffffffffff
    return int(values['call_id']), records, encoded, f'{checksum:016x}'


def inspect_traces(output, workers, final_turn):
    if output.count('NATIVE_RESTORE_FRESH_SESSION=true') != 1:
        raise RuntimeError('City-site run lacks a unique fresh-session boundary')
    rows = []
    for session, block in enumerate(output.split('NATIVE_RESTORE_FRESH_SESSION=true')):
        pending = None
        expected_call = 1
        for line in block.splitlines():
            if line.startswith('ZEROSIS_CITY_SITE_VALUES '):
                if pending is not None:
                    raise RuntimeError('A city-site value record has no paired trace')
                pending = parse_values(line.split(' ', 1)[1])
            elif line.startswith('ZEROSIS_CITY_SITE_TRACE '):
                raw = fields(line.split(' ', 1)[1])
                if set(raw) != INTEGER_KEYS | TEXT_KEYS:
                    raise RuntimeError('City-site metric schema differs')
                if any(not re.fullmatch(r'\d+', raw[key]) for key in INTEGER_KEYS):
                    raise RuntimeError('City-site measurements contain a negative/non-integral field')
                row = {key: int(raw[key]) for key in INTEGER_KEYS}
                row.update({key: raw[key] for key in TEXT_KEYS})
                if row['abi'] != 1 or row['config'] != 1 or row['status'] != 0 or \
                   row['call_id'] != expected_call or row['player'] != 1 or \
                   not 0 <= row['turn'] <= final_turn or row['cities'] < 2 or \
                   row['requested_workers'] != workers or \
                   row['mode'] != ('scalar-original' if workers == 0 else 'owned-worker') or \
                   row['fnv_scope'] != FNV_SCOPE or \
                   row['input_cells_scope'] != 'eligible_sites_times_tile_count_including_home_and_missing_plot_slots' or \
                   not re.fullmatch(r'[0-9a-f]{16}', row['ordered_output_fnv1a64']):
                    raise RuntimeError('City-site invocation identity, ABI or status differs')
                expected_call += 1
                count = row['eligible_sites']
                if not 0 <= count <= 960 or row['input_cells'] > count * 64 or \
                   (count == 0 and row['input_cells'] != 0) or \
                   any(row[key] != count for key in ('jobs_total', 'jobs_started', 'jobs_completed')):
                    raise RuntimeError('City-site count or completed-job accounting differs')
                if pending is None or pending[0] != row['call_id'] or len(pending[1]) != count or \
                   pending[3] != row['ordered_output_fnv1a64']:
                    raise RuntimeError('Trace does not match its complete ordered result payload')
                reduced = [max([0, *(record[index] for record in pending[1])]) for index in range(1, 5)]
                if reduced != [row[key] for key in ('best_food', 'best_production', 'best_gold', 'best_science')]:
                    raise RuntimeError('SDK best yields differ from the complete ordered reduction')
                tids = []
                if raw['worker_tids_job_counts'] not in ('', '-'):
                    for item in raw['worker_tids_job_counts'].split(','):
                        if not re.fullmatch(r'[1-9]\d*:[1-9]\d*', item):
                            raise RuntimeError('Malformed per-worker invocation count')
                        tids.append(list(map(int, item.split(':'))))
                if workers == 0:
                    if any(row[key] for key in ('workers_started', 'used_threads', 'max_overlap',
                                               'snapshot_us', 'worker_us', 'shadow_us', 'reduction_us')) or tids:
                        raise RuntimeError('Original scalar mode unexpectedly launched/observed worker scoring')
                elif row['workers_started'] != min(workers, count) or \
                     len(tids) != row['used_threads'] or len({tid[0] for tid in tids}) != len(tids) or \
                     sum(tid[1] for tid in tids) != count or \
                     (count and not 1 <= row['max_overlap'] <= row['used_threads'] <= row['workers_started']) or \
                     (not count and (row['max_overlap'] or row['used_threads'])):
                    raise RuntimeError('Actual city-site worker invocation observations are inconsistent')
                row.update(session=session, ordered_values=pending[1],
                           ordered_output_bytes=len(pending[2]),
                           ordered_output_sha256=hashlib.sha256(pending[2]).hexdigest(),
                           worker_thread_job_counts=tids)
                pending = None
                rows.append(row)
        if pending is not None:
            raise RuntimeError('The final city-site value record lacks a completed trace')
    if not rows or not any(row['eligible_sites'] > 0 for row in rows):
        raise RuntimeError('The actual AI did not complete any nonempty FindBestSites calculation')
    return rows


def signature(rows):
    keys = ('session', 'call_id', 'player', 'turn', 'cities', 'eligible_sites', 'input_cells',
            'best_food', 'best_production', 'best_gold', 'best_science', 'ordered_values',
            'ordered_output_sha256', 'ordered_output_fnv1a64')
    return [{key: row[key] for key in keys} for row in rows]


def compare_state(actual, baseline, *, allow_sdk_identity_change=False):
    if actual['final_turn'] != baseline['final_turn'] or actual['command'] != baseline['command']:
        raise RuntimeError('Compared continuations used different commands or final turns')
    manifests = None
    if allow_sdk_identity_change:
        manifests = []
        for row in (actual, baseline):
            result = read_artifact(row['result'])
            request = read_artifact(result['request'])
            references = [item for item in request['inputs'] if Path(item['path']).name == 'bundle.manifest']
            if len(references) != 1:
                raise RuntimeError('Original SDK comparison lacks one verified bundle manifest')
            check_artifacts(references[0])
            manifests.append(Path(references[0]['path']).read_bytes())
        dll = 'CvGameCoreDLL_Expansion2_x64.dll'
        old_line = (dll + '|' + baseline['inputs'][dll]).encode('ascii')
        new_line = (dll + '|' + actual['inputs'][dll]).encode('ascii')
        entries = [line for line in manifests[1].splitlines() if line.startswith((dll + '|').encode('ascii'))]
        if entries != [old_line] or manifests[1].count(old_line) != 1 or \
           manifests[0] != manifests[1].replace(old_line, new_line, 1):
            raise RuntimeError('Original SDK comparison changed bundle data beyond the exact GameCore hash line')
    for field in ('checkpoint', 'restored_checkpoint', 'final'):
        sections = [row['archive_comparisons'][field]['sections'] for row in (actual, baseline)]
        if manifests is not None:
            for items, manifest in zip(sections, manifests):
                identities = [item for item in items if item['kind'] == 1]
                expected = {'kind': 1, 'index': 0, 'bytes': len(manifest),
                            'comparison_sha256': hashlib.sha256(manifest).hexdigest()}
                if identities != [expected]:
                    raise RuntimeError('SDK archive identity is not its exact verified bundle manifest')
            sections = [[item for item in items if item['kind'] != 1] for items in sections]
        if sections[0] != sections[1]:
            raise RuntimeError('City-site mode changed an SDK archive payload: ' + field)
    for key in ('extended_observations', 'extended_events', 'fixture_promotions', 'input_routes', 'action_records'):
        if actual[key] != baseline[key]:
            raise RuntimeError('City-site mode changed continued SDK observations: ' + key)
    if [row['sha256'] for row in actual['extended_snapshots']] != \
       [row['sha256'] for row in baseline['extended_snapshots']]:
        raise RuntimeError('City-site mode changed a continued-turn semantic snapshot')
    if [(row['player'], row['turn'], row['plots']) for row in actual['batches']] != \
       [(row['player'], row['turn'], row['plots']) for row in baseline['batches']]:
        raise RuntimeError('City-site mode changed the exploration workload')


def ui_signature(row):
    return [(popup['turn'], popup['mode'], popup['draws'], popup['ranked_rows']) for popup in row['popups']]


def inspect_run(run_id, options, output_dir):
    row = inspect_extended(run_id, ui_popups=options.ui_popups,
                           fixture_promotions=options.fixture_promotions,
                           fixture_unit_actions=options.fixture_unit_actions, sdk_city_sites=True)
    result = read_artifact(row['result'])
    request = read_artifact(result['request'])
    sdk = read_artifact(request['city_site_sdk_build'])
    check_artifacts(sdk)
    if sdk.get('status') != 'CITY_SITE_SDK_CANDIDATE_LINKED' or sdk.get('stage_updated') is not False or \
       sdk.get('active_sdk_updated', False) is not False:
        raise RuntimeError('Selected city-site SDK is not an isolated linked candidate')
    builder = sdk.get('builder')
    if not builder:
        raise RuntimeError('City-site candidate does not identify its frozen builder')
    check_artifacts(builder)
    builder_text = Path(builder['path']).read_text(encoding='utf8')
    if not re.search(r'const char\* value = std::getenv\("ZEROSIS_CITY_SITE_WORKERS"\);\s*'
                     r'if\s*\(value == NULL \|\| value\[0\] == \'\\0\' \|\| '
                     r'std::strcmp\(value, "0"\) == 0\)\s*return 0;', builder_text):
        raise RuntimeError('Frozen SDK builder does not default absent worker configuration to scalar mode')
    workers = request['city_site_workers']
    if type(workers) is not int or workers not in WORKERS or \
       request['environment_overrides'].get('ZEROSIS_CITY_SITE_WORKERS') != str(workers):
        raise RuntimeError('Actual process launch does not match its requested city-site workers')
    output = Path(result['stdout']['path']).read_text(encoding='utf8')
    traces = inspect_traces(output, workers, row['final_turn'])
    rules = [item for item in result['generated_files'] if Path(item['path']).name == 'rules.db']
    if len(rules) != 2:
        raise RuntimeError('Both fresh sessions must retain their private rules databases')
    required_definitions = {'AI_CITY_SPECIALIZATION_EARLIEST_TURN',
                            'AI_CITY_SPECIALIZATION_REEVALUATION_INTERVAL',
                            'AI_CITY_SPECIALIZATION_YIELD_NUM_TILES_CONSIDERED',
                            'SETTLER_EVALUATION_DISTANCE'}
    definitions = []
    for reference in rules:
        check_artifacts(reference)
        path = Path(reference['path'])
        with sqlite3.connect('file:' + path.as_posix() + '?mode=ro', uri=True) as database:
            values = dict(database.execute('SELECT Name,Value FROM Defines WHERE Name IN (?,?,?,?)',
                                           tuple(sorted(required_definitions))))
        if set(values) != required_definitions or any(type(value) is not int for value in values.values()):
            raise RuntimeError('Fixture city-site rules definitions are absent or non-integral')
        definitions.append(values)
    if definitions[0] != definitions[1]:
        raise RuntimeError('Fresh restore changed the city-site rules definitions')
    tile_count = definitions[0]['AI_CITY_SPECIALIZATION_YIELD_NUM_TILES_CONSIDERED']
    if not 0 <= tile_count <= 64 or any(call['input_cells'] != call['eligible_sites'] * tile_count or
                                     call['turn'] < definitions[0]['AI_CITY_SPECIALIZATION_EARLIEST_TURN']
                                     for call in traces):
        raise RuntimeError('Actual site observations disagree with the configured tile count/turn gate')
    output_file = output_dir / (run_id + '-ordered-results.json')
    output_file.write_text(json.dumps(signature(traces), indent=2) + '\n', encoding='utf8')
    row.update(city_site_traces=traces, city_site_workers=workers,
               city_site_sdk_build=request['city_site_sdk_build'],
               ordered_values_artifact=artifact(output_file), scalar_default_source=builder,
               fixture_rules_city_site_definitions=definitions[0],
               fixture_rules_databases=rules,
               city_site_mode_explicit_at_launch=True)
    if options.ui_popups:
        ui = inspect_popup(run_id, fixture_promotions=options.fixture_promotions,
                           fixture_unit_actions=options.fixture_unit_actions, sdk_city_sites=True)
        row['official_ui_signature'] = ui_signature(ui)
    row['diagnostic_timings'] = {key: sum(call[key] for call in traces)
                                for key in ('snapshot_us', 'worker_us', 'shadow_us', 'reduction_us', 'total_us')}
    row['maximum_in_flight_scoring_invocations'] = max(call['max_overlap'] for call in traces)
    row['maximum_scoring_threads_used_in_a_batch'] = max(call['used_threads'] for call in traces)
    return row


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', action='append', required=True)
    parser.add_argument('--reference-run', action='append', default=[],
                        help='Optional original Explore SDK serial run in each language, using the same commands')
    parser.add_argument('--ui-popups', action='store_true')
    parser.add_argument('--fixture-promotions', action='store_true')
    parser.add_argument('--fixture-unit-actions', action='store_true')
    args = parser.parse_args()
    if args.fixture_promotions and not args.ui_popups or args.fixture_unit_actions and not args.fixture_promotions:
        parser.error('Promotion/action profiles require the same UI input profiles as the runner')
    if len(args.run) not in (4, 6, 8) or len(set(args.run)) != len(args.run) or \
       len(args.reference_run) not in (0, 2) or len(set(args.reference_run)) != len(args.reference_run):
        parser.error('Provide matching EN/KO serial and worker runs; references must cover both languages')
    if any(not re.fullmatch(r'\d{8}T\d{6}Z_[0-9a-f]{12}', run_id) for run_id in args.run + args.reference_run):
        parser.error('Only existing isolated run IDs are accepted')
    names = tuple(dict.fromkeys((*VALIDATORS, 'verify_city_site_sdk_candidate.py',
                                'verify_ui_popup_runtime.py', 'prepare_ui_popup_assets.py')))
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ_') + uuid.uuid4().hex[:12]
    directory = ROOT / run_id
    frozen = directory / 'validators'
    frozen.mkdir(parents=True, exist_ok=False)
    before = {name: digest(PROJECT / 'tools' / name) for name in names}
    for name in names:
        shutil.copy2(PROJECT / 'tools' / name, frozen / name)
        if digest(frozen / name) != before[name]:
            raise RuntimeError('Validator changed while freezing its source')
    rows = [inspect_run(item, args, directory) for item in args.run]
    keyed = {(row['language'], row['city_site_workers']): row for row in rows}
    settings = sorted({row['city_site_workers'] for row in rows})
    if 0 not in settings or len(keyed) != len(rows) or \
       set(keyed) != {(language, worker) for language in ('en_US', 'ko_KR') for worker in settings}:
        raise RuntimeError('The city-site language/worker matrix is incomplete')
    if any(row['inputs'] != rows[0]['inputs'] or row['workers'] != rows[0]['workers'] for row in rows[1:]):
        raise RuntimeError('City-site comparisons changed SDK, host inputs or the exploration worker setting')
    comparisons = []
    for language in ('en_US', 'ko_KR'):
        baseline = keyed[language, 0]
        for workers in settings[1:]:
            actual = keyed[language, workers]
            compare_state(actual, baseline)
            if signature(actual['city_site_traces']) != signature(baseline['city_site_traces']):
                raise RuntimeError('City-site mode changed actual ordered candidates or yield results')
            if args.ui_popups and actual['official_ui_signature'] != baseline['official_ui_signature']:
                raise RuntimeError('City-site mode changed official UI RNG or ranking behavior')
            comparisons.append({'language': language, 'workers': workers, 'archives_compared': 3,
                                'every_continued_turn_snapshot_equal': True,
                                'every_city_site_candidate_and_yield_vector_equal': True})
    if signature(keyed['en_US', 0]['city_site_traces']) != signature(keyed['ko_KR', 0]['city_site_traces']) or \
       [row['sha256'] for row in keyed['en_US', 0]['extended_snapshots']] != \
       [row['sha256'] for row in keyed['ko_KR', 0]['extended_snapshots']]:
        raise RuntimeError('Language changed observed city-site calculation or semantic continuation state')
    reference_checks = []
    if args.reference_run:
        references = [inspect_extended(item, ui_popups=args.ui_popups,
                                       fixture_promotions=args.fixture_promotions,
                                       fixture_unit_actions=args.fixture_unit_actions) for item in args.reference_run]
        if {row['language'] for row in references} != {'en_US', 'ko_KR'} or any(row['workers'] != 0 for row in references):
            raise RuntimeError('Original SDK references must be serial and cover both languages')
        for original in references:
            current = keyed[original['language'], 0]
            if {name: value for name, value in original['inputs'].items()
                if name not in ('CvGameCoreDLL_Expansion2_x64.dll', 'bundle.manifest')} != \
               {name: value for name, value in current['inputs'].items()
                if name not in ('CvGameCoreDLL_Expansion2_x64.dll', 'bundle.manifest')}:
                raise RuntimeError('Original SDK comparison changed inputs beyond SDK/bundle identity')
            compare_state(current, original, allow_sdk_identity_change=True)
            if args.ui_popups:
                ui = inspect_popup(original['run_id'], fixture_promotions=args.fixture_promotions,
                                   fixture_unit_actions=args.fixture_unit_actions)
                if current['official_ui_signature'] != ui_signature(ui):
                    raise RuntimeError('Scalar instrumentation changed official popup RNG/behavior')
            reference_checks.append({'language': original['language'], 'reference': original['result'],
                                     'original_sdk_game_payloads_and_continuation_equal': True,
                                     'game_payload_sections_compared_per_archive': 132,
                                     'bundle_identity_compared_after_exact_gamecore_hash_line_substitution': True,
                                     'bundle_identity_hash_substitution_only_for_original_sdk_reference': True})
    if any(digest(PROJECT / 'tools' / name) != value for name, value in before.items()):
        raise RuntimeError('A validator changed during actual runtime verification')
    report = {'status': 'ACTUAL_SDK_CITY_SITE_ORDERED_RESULTS_AND_RESTORE_PASS',
              'validators': [artifact(frozen / name) for name in names],
              'validator_inputs_unchanged': True, 'runs': rows, 'comparisons': comparisons,
              'original_sdk_references': reference_checks, 'city_site_worker_settings': settings,
              'total_turns_per_run': rows[0]['final_turn'], 'gamecore_loaded': True,
              'same_language_full_archive_payload_comparison': True,
              'cross_language_full_archive_byte_equality_asserted': False,
              'ordered_output_hash_algorithm': 'SHA256 of explicit little-endian uint32 plot index + four int32 yields',
              'every_ordered_value_compared_directly': True,
              'metric_scope': 'OVERLAPPING_IN_FLIGHT_SCORE_INVOCATIONS_NOT_SIMULTANEOUS_PHYSICAL_CPU_PROOF',
              'physical_multicore_verified': False, 'performance_improvement_verified': False,
              'timing_scope': 'DIAGNOSTIC_INCLUDES_CAPTURE_THREAD_LAUNCH_JOIN_SHADOW_AND_TRACE_PREPARATION_NOT_BENCHMARK',
              'renderer_verified': False, 'interactive_gameplay_verified': False,
              'retail_save_compatibility_verified': False, 'complete_game_equivalence_verified': False,
              'accepted_stage_promoted': False}
    check_artifacts(report)
    target = directory / 'conformance.json'
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    temporary = ROOT / ('conformance.json.tmp-' + uuid.uuid4().hex)
    temporary.write_bytes(target.read_bytes())
    temporary.replace(ROOT / 'conformance.json')
    print(json.dumps({'status': report['status'], 'runs': len(rows),
                      'turns': report['total_turns_per_run'], 'city_site_workers': settings,
                      'evidence': artifact(target)}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
