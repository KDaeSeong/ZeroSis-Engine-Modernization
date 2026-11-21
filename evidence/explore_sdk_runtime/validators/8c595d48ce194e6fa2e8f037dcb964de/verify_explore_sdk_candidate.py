"""Compare actual SDK exploration batches and complete fixture saves across worker counts.

This is a two-turn, two-language fixture comparison, not a benchmark or a claim
of complete retail equivalence. In-flight invocation overlap is recorded without
equating it with simultaneous CPU execution on distinct physical cores.
"""
import argparse
import collections
import hashlib
import json
import re
import shutil
import statistics
import uuid
from pathlib import Path

from collect_baseline import PROJECT
from probe_world_builder import artifact
from verify_first_turn_candidate import inspect_save, read_artifact
from verify_native_save_restore import inspect_restore, one
from verify_restore_game_metadata import _archive
from verify_world_builder_map_object import check_artifacts


ROOT = PROJECT / 'evidence/explore_sdk_runtime'
WORKERS = (0, 1, 2, 4)
LANGUAGES = ('en_US', 'ko_KR')
METRIC_KEYS = {
    'player', 'turn', 'mode', 'requested_workers', 'plots', 'snapshot_us',
    'worker_us', 'validation_us', 'update_us', 'workers_started', 'jobs_started',
    'jobs_completed', 'worker_threads_used', 'max_overlap', 'worker_ids',
}


def comparable_save(save):
    # CvMap::Write version 1 serializes eight int32 fields, two bool8 fields,
    # then its CoCreateGuid-generated identity. This identity is intentionally
    # different for independent new games even with identical gameplay seeds.
    _, payloads = _archive(save['archive']['path'])
    map_bytes = payloads[4, 0]
    identity = uuid.UUID(bytes_le=map_bytes[34:50])
    if identity.version != 4 or identity.variant != uuid.RFC_4122:
        raise RuntimeError('Independent new-game map identity is not the expected SDK GUID')
    comparisons = []
    for section in save['sections']:
        kind, index = section['kind'], section['index']
        payload = payloads[kind, index]
        if kind == 4:
            payload = payload[:34] + bytes(16) + payload[50:]
        comparisons.append({'kind': kind, 'index': index, 'bytes': len(payload),
                            'comparison_sha256': hashlib.sha256(payload).hexdigest()})
    return {'map_guid': str(identity), 'sections': comparisons,
            'excluded_bytes': {'section': [4, 0], 'offset': 34, 'count': 16, 'field': 'CvMap::m_guid'},
            'all_other_bytes_compared': True}


def inspect_batches(output, workers):
    lines = re.findall(r'^ZEROSIS_EXPLORE_BATCH (.*)$', output, re.M)
    if not lines:
        raise RuntimeError('The actual SDK exploration path produced no batch observations')
    rows = []
    for line in lines:
        fields = dict(token.split('=', 1) for token in line.split())
        if set(fields) != METRIC_KEYS:
            raise RuntimeError('Exploration metric schema differs')
        row = {key: int(value) for key, value in fields.items() if key != 'worker_ids'}
        row['worker_ids'] = [int(value) for value in fields['worker_ids'].split(',') if value]
        if any(value < 0 for value in row.values() if isinstance(value, int)) or \
           row['player'] >= 64 or row['turn'] > 2 or \
           row['requested_workers'] != workers or row['mode'] != int(workers != 0):
            raise RuntimeError('Exploration batch identity or measurements are invalid')
        count = row['plots']
        if not 0 <= count <= 960:
            raise RuntimeError('Exploration snapshot exceeds the actual fixture map')
        if workers == 0:
            if any(row[key] for key in ('snapshot_us', 'worker_us', 'validation_us', 'workers_started',
                                       'jobs_started', 'jobs_completed', 'worker_threads_used', 'max_overlap')) or row['worker_ids']:
                raise RuntimeError('Original serial mode unexpectedly reports worker execution')
        else:
            if row['jobs_started'] != count or row['jobs_completed'] != count or \
               row['workers_started'] != min(workers, count):
                raise RuntimeError('Exploration worker batch was not completed in full')
            used = row['worker_threads_used']
            overlap = row['max_overlap']
            if (count and not 1 <= overlap <= used <= row['workers_started']) or \
               (not count and (used or overlap)) or row['worker_ids'] != list(range(1, used + 1)):
                raise RuntimeError('Actual worker invocation observations are inconsistent')
        rows.append(row)
    if not any(row['plots'] and row['player'] != 0 for row in rows):
        raise RuntimeError('No live AI player exploration work was measured')
    return rows


def inspect_explore(run_id):
    row = inspect_restore(run_id)
    result = read_artifact(row['result'])
    request = read_artifact(result['request'])
    if not request.get('explore_sdk_build'):
        raise RuntimeError('An actual exploration SDK candidate run is required')
    sdk = read_artifact(request['explore_sdk_build'])
    check_artifacts(sdk)
    if sdk['status'] != 'EXPLORE_SDK_CANDIDATE_LINKED':
        raise RuntimeError('Exploration SDK build did not complete')
    environment = request.get('environment_overrides')
    if environment not in [{'ZEROSIS_EXPLORE_WORKERS': str(value)} for value in WORKERS]:
        raise RuntimeError('Worker setting was not explicitly recorded at process launch')
    workers = int(environment['ZEROSIS_EXPLORE_WORKERS'])
    output = Path(result['stdout']['path']).read_text(encoding='utf8')
    batches = inspect_batches(output, workers)
    session = Path(one(output, 'RESTORE_SESSION_DIRECTORY')).resolve()
    generated = {Path(item['path']).resolve(): item for item in result['generated_files']}
    def recorded(name):
        path = session / name
        if path not in generated:
            raise RuntimeError('Missing post-turn runtime artifact: ' + name)
        check_artifacts(generated[path])
        return path
    final_snapshot = recorded('state-after-resumed-turn.txt')
    final_data = final_snapshot.read_bytes()
    if not final_data.startswith(b'G|2|2|0|960\n') or \
       len(final_data) != int(one(output, 'RESUMED_TURN_STATE_BYTES')):
        raise RuntimeError('Final SDK state snapshot is not the resumed turn-two state')
    bundle = next(Path(item['path']) for item in request['inputs'] if Path(item['path']).name == 'bundle.manifest')
    final_save = inspect_save(recorded('state-after-resumed-turn.zssave'), bundle,
                              recorded('Civ5SavedGameDatabase.db'), expected=(1, 0, 2, 2, 0, 64, 64, 133))
    turn_us = [int(one(output, key + '_DURATION_US')) for key in ('TURN_CYCLE', 'RESTORED_TURN_CYCLE')]
    if any(value <= 0 for value in turn_us):
        raise RuntimeError('Actual normal-turn timings are missing or invalid')
    row.update(workers=workers, batches=batches, final_save=final_save,
               final_snapshot=artifact(final_snapshot), final_snapshot_sha256=hashlib.sha256(final_data).hexdigest(),
               turn_duration_us=turn_us, explore_sdk_build=request['explore_sdk_build'])
    row['save_comparisons'] = {field: comparable_save(row[field])
                               for field in ('checkpoint', 'restored_checkpoint', 'final_save')}
    if len({value['map_guid'] for value in row['save_comparisons'].values()}) != 1:
        raise RuntimeError('The map identity changed within a save/restore/resumed-turn run')
    return row


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', action='append', required=True)
    args = parser.parse_args()
    if len(args.run) != 8 or len(set(args.run)) != 8:
        parser.error('Provide eight distinct runs: EN and KO with original mode and 1/2/4 workers')
    rows = [inspect_explore(run_id) for run_id in args.run]
    keyed = {(row['language'], row['workers']): row for row in rows}
    if set(keyed) != {(language, workers) for language in LANGUAGES for workers in WORKERS}:
        raise RuntimeError('The language/worker matrix is incomplete or duplicated')
    for row in rows[1:]:
        if row['inputs'] != rows[0]['inputs']:
            raise RuntimeError('Runtime comparison did not use identical binaries and input data')
    comparisons = []
    for language in LANGUAGES:
        baseline = keyed[language, 0]
        workload = [(batch['player'], batch['turn'], batch['plots']) for batch in baseline['batches']]
        for workers in WORKERS[1:]:
            row = keyed[language, workers]
            if [(batch['player'], batch['turn'], batch['plots']) for batch in row['batches']] != workload:
                raise RuntimeError('Worker mode changed the live SDK exploration workload or order')
            for field in ('checkpoint', 'restored_checkpoint', 'final_save'):
                if row['save_comparisons'][field]['sections'] != baseline['save_comparisons'][field]['sections']:
                    raise RuntimeError(f'Worker mode changed complete serialized state: {language}/{workers}/{field}')
            for field in ('snapshot', 'final_snapshot_sha256', 'turn_frames', 'resumed_turn_frames',
                          'final_players', 'resumed_turn_events'):
                if row[field] != baseline[field]:
                    raise RuntimeError('Worker mode changed an independently observed SDK state: ' + field)
            comparisons.append({'language': language, 'workers': workers, 'compared_archives': 3,
                                'byte_exact_sections_per_archive': 132,
                                'map_section_equal_except_new_game_guid': True, 'live_batch_order_equal': True})
    summaries = []
    for workers in WORKERS:
        group = [row for row in rows if row['workers'] == workers]
        batches = [batch for row in group for batch in row['batches']]
        summaries.append({'workers': workers, 'runs': len(group), 'batches': len(batches),
                          'scored_plots': sum(batch['plots'] for batch in batches),
                          'maximum_worker_threads_used': max(batch['worker_threads_used'] for batch in batches),
                          'maximum_in_flight_scoring_invocations': max(batch['max_overlap'] for batch in batches),
                          'sum_snapshot_us': sum(batch['snapshot_us'] for batch in batches),
                          'sum_worker_batch_us': sum(batch['worker_us'] for batch in batches),
                          'sum_shadow_validation_us': sum(batch['validation_us'] for batch in batches),
                          'sum_exploration_update_us': sum(batch['update_us'] for batch in batches),
                          'normal_turn_duration_us': [value for row in group for value in row['turn_duration_us']],
                          'median_normal_turn_us': statistics.median(value for row in group for value in row['turn_duration_us'])})
    ROOT.mkdir(parents=True, exist_ok=True)
    frozen = ROOT / 'validators' / uuid.uuid4().hex
    frozen.mkdir(parents=True, exist_ok=False)
    validators = []
    for name in ('verify_explore_sdk_candidate.py', 'verify_native_save_restore.py', 'verify_restore_game_metadata.py',
                 'verify_first_turn_candidate.py', 'verify_turn_cycle_candidate.py', 'verify_new_game_candidate.py',
                 'verify_world_builder_map_object.py', 'collect_baseline.py', 'probe_world_builder.py'):
        target = frozen / name
        shutil.copy2(PROJECT / 'tools' / name, target)
        validators.append(artifact(target))
    report = {'status': 'SDK_EXPLORATION_SCORING_WORKER_MATRIX_PASS', 'validators': validators,
              'runs': rows, 'comparisons': comparisons, 'measurements': summaries,
              'sdk_game_calculation_worker_execution_verified': True,
              'overlapping_scoring_invocations_observed': any(row['maximum_in_flight_scoring_invocations'] > 1 for row in summaries),
              'physical_multicore_overlap_verified': False, 'performance_improvement_verified': False,
              'two_turn_fixture_archives_equal_except_new_game_guid': True,
              'original_serial_mode_remains_default': True, 'accepted_stage_promoted': False,
              'retail_save_compatibility_verified': False, 'complete_game_equivalence_verified': False,
              'installed_game_launched': False,
              'scope': 'ACTUAL_SDK_UPDATEPLOTS_RANGE1_SCORING_0_1_2_4_WORKERS_EN_KO_TWO_TURN_RESTORE_FIXTURE',
              'timing_scope': 'DIAGNOSTIC_RUNS_INCLUDE_SHADOW_COMPARISON_AND_INSTRUMENTATION_NOT_A_BENCHMARK'}
    check_artifacts(report)
    (ROOT / 'conformance.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf8')
    print(json.dumps({'status': report['status'], 'measurements': summaries,
                      'overlapping_scoring_invocations_observed': report['overlapping_scoring_invocations_observed']}), flush=True)


if __name__ == '__main__':
    main()
