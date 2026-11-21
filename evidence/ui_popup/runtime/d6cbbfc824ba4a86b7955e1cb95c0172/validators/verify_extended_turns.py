"""Verify longer ordinary SDK turns after a fresh-session native restore.

This configured fixture skips the human's remaining starting units. AI
turns are real; this does not certify interactive gameplay or retail saves.
"""
import argparse
import json
import re
import shutil
import uuid
from pathlib import Path

from collect_baseline import PROJECT, digest
from probe_world_builder import artifact
from verify_first_turn_candidate import inspect_save, read_artifact
from verify_native_save_restore import inspect_restore, inspect_snapshot, one
from verify_explore_sdk_candidate import comparable_save, inspect_batches
from verify_world_builder_map_object import check_artifacts

ROOT = PROJECT / 'evidence/extended_turns'
VALIDATORS = ('verify_extended_turns.py', 'verify_explore_sdk_candidate.py',
              'verify_native_save_restore.py', 'verify_restore_game_metadata.py',
              'verify_first_turn_candidate.py', 'verify_turn_cycle_candidate.py',
              'verify_new_game_candidate.py', 'verify_world_builder_map_object.py',
              'collect_baseline.py', 'probe_world_builder.py')


def inspect_extended(run_id,ui_popups=False):
    result_path = PROJECT / 'evidence/save_restore' / run_id / 'result.json'
    result = read_artifact(artifact(result_path))
    extra = result.get('extra_restored_turns')
    if not isinstance(extra, int) or not 1 <= extra <= 98:
        raise RuntimeError('A completed extended-turn request is required')
    row = inspect_restore(run_id, extra_turns=extra, ui_popups=ui_popups)
    request = read_artifact(result['request'])
    output = Path(result['stdout']['path']).read_text(encoding='utf8')
    end_turn = 2 + extra
    if one(output, 'EXTENDED_TURNS_BEGIN') != f'2,{extra}' or \
       one(output, 'EXTENDED_TURNS_COMPLETE') != f'2,{end_turn},{extra}':
        raise RuntimeError('Extended-turn request and completion disagree')
    environment = request.get('environment_overrides')
    if environment not in [{'ZEROSIS_EXPLORE_WORKERS': str(value)} for value in (0, 1, 2, 4)]:
        raise RuntimeError('Missing explicit worker setting')
    workers = int(environment['ZEROSIS_EXPLORE_WORKERS'])
    sdk = read_artifact(request['explore_sdk_build'])
    check_artifacts(sdk)
    if sdk['status'] != 'EXPLORE_SDK_CANDIDATE_LINKED':
        raise RuntimeError('The exploration SDK candidate is not linked')
    batches = inspect_batches(output, workers, max_turn=end_turn)
    session = Path(one(output, 'RESTORE_SESSION_DIRECTORY')).resolve()
    generated = {Path(item['path']).resolve(): item for item in result['generated_files']}

    def recorded(name):
        path = session / name
        if path not in generated:
            raise RuntimeError('Missing extended runtime artifact: ' + name)
        check_artifacts(generated[path])
        return path

    observations = []
    snapshots = []
    all_frames = []
    parts = re.split(r'^EXTENDED_TURN_CYCLE_PLAYER_OPTION=PLAYEROPTION_WAIT_END_TURN:1$',
                     output.split('EXTENDED_TURNS_BEGIN=', 1)[1], flags=re.M)[1:]
    if len(parts) != extra:
        raise RuntimeError('Each continued turn must receive its ordinary SDK player option')
    for begin, part in enumerate(parts, 2):
        if one(part, 'EXTENDED_TURN_CYCLE_INPUT') != 'MISSION_SKIP_EACH_UNIT_THEN_CONTROL_ENDTURN':
            raise RuntimeError('Extended turn bypassed normal unit/end-turn input')
        observed = [int(value) for value in one(part, 'EXTENDED_TURN_CYCLE_OBSERVATION').split(',')]
        if len(observed) != 8 or observed[:6] != [begin, begin + 1, begin + 1, 0, 1, 1] or \
           not 1 <= observed[6] <= 256 or observed[7] != 3:
            raise RuntimeError('Extended turn did not stop at the next human waiting turn')
        frames = []
        for step, (index, values) in enumerate(re.findall(r'^EXTENDED_TURN_CYCLE_STATE=(\d+)\|(.+)$', part, re.M), 1):
            frame = [int(value) for value in values.split(',')]
            if int(index) != step or len(frame) != 5 or frame[0] != frame[1] or \
               frame[0] not in (begin, begin + 1) or any(value not in (0, 1) for value in frame[2:]):
                raise RuntimeError('Invalid intermediate SDK turn frame')
            frames.append(frame)
        if len(frames) != observed[6] or frames[-1] != [begin + 1, begin + 1, 1, 1, 1] or \
           any(frame[0] != begin for frame in frames[:-1]) or [begin, begin, 0, 0, 0] not in frames:
            raise RuntimeError('Extended AI processing did not finish before human activation')
        duration = int(one(part, 'EXTENDED_TURN_CYCLE_DURATION_US'))
        if duration <= 0:
            raise RuntimeError('Missing extended normal-turn timing')
        snapshot_path = recorded(f'extended-state-turn-{begin + 1}.txt')
        data = snapshot_path.read_bytes()
        snapshot = inspect_snapshot(data, expected_turn=begin + 1, initial_fixture=False)
        if one(part, 'EXTENDED_TURN_SNAPSHOT') != f'{begin + 1},{len(data)}':
            raise RuntimeError('Persisted snapshot and log differ')
        snapshots.append({'turn': begin + 1, 'artifact': artifact(snapshot_path), **snapshot})
        all_frames.append({'turn': begin, 'frames': frames, 'duration_us': duration})
        observations.append(observed)
    if observations != result['extended_turn_observations']:
        raise RuntimeError('Extended observations differ from their recorded result')
    events = {event: int(count) for count, event in re.findall(r'^TURN_CYCLE_EVENT=(\d+)\|(.+)$',
              output.split('NATIVE_RESTORE_FRESH_SESSION=true', 1)[1], re.M)}
    for event in ('local-turn-complete', 'ui-active-player-turn-end', 'ui-active-player-turn-start'):
        if events.get(event) != end_turn - 1:
            raise RuntimeError('Extended local turn event count differs: ' + event)
    for begin in range(1, end_turn):
        for event in (f'local-turn-all-complete:{begin}', f'local-turn-boundary:{begin}',
                      f'gameplay-turn-changed:{begin + 1}', f'new-game-turn:{begin + 1}'):
            if events.get(event) != 1:
                raise RuntimeError('Missing or duplicated extended turn boundary: ' + event)
    if events.get('local-turn-complete-cancelled', 0):
        raise RuntimeError('A continued SDK turn was cancelled')
    bundle = next(Path(item['path']) for item in request['inputs'] if Path(item['path']).name == 'bundle.manifest')
    final_save = inspect_save(recorded('state-after-extended-turns.zssave'), bundle,
                             recorded('Civ5SavedGameDatabase.db'), expected=(1, 0, end_turn, end_turn, 0, 64, 64, 133))
    comparisons = {name: comparable_save(save) for name, save in
                   (('checkpoint', row['checkpoint']), ('restored_checkpoint', row['restored_checkpoint']), ('final', final_save))}
    if len({value['map_guid'] for value in comparisons.values()}) != 1:
        raise RuntimeError('Map identity changed during the live continuation')
    row.update(workers=workers, final_turn=end_turn, batches=batches, ui_popups_enabled=ui_popups, extended_observations=observations,
               extended_frames=all_frames, extended_snapshots=snapshots, extended_events=events,
               final_save=final_save, archive_comparisons=comparisons)
    return row


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', action='append', required=True)
    parser.add_argument('--ui-popups', action='store_true')
    args = parser.parse_args()
    if len(set(args.run)) != len(args.run) or len(args.run) not in (2, 4, 6, 8):
        parser.error('Provide distinct matching EN/KO runs including serial mode')
    for run_id in args.run:
        if not re.fullmatch(r'\d{8}T\d{6}Z_[0-9a-f]{12}', run_id):
            parser.error('Only existing isolated run IDs are accepted')
    ROOT.mkdir(parents=True, exist_ok=True)
    frozen = ROOT / 'validators' / uuid.uuid4().hex
    frozen.mkdir(parents=True, exist_ok=False)
    before = {name: digest(PROJECT / 'tools' / name) for name in VALIDATORS}
    validators = []
    for name in VALIDATORS:
        target = frozen / name
        shutil.copy2(PROJECT / 'tools' / name, target)
        if digest(target) != before[name]:
            raise RuntimeError('Validator changed while its input was frozen')
        validators.append(artifact(target))
    rows = [inspect_extended(run_id,ui_popups=args.ui_popups) for run_id in args.run]
    keyed = {(row['language'], row['workers']): row for row in rows}
    settings = sorted({row['workers'] for row in rows})
    if 0 not in settings or len(keyed) != len(rows) or set(keyed) != {(language, worker) for language in ('en_US', 'ko_KR') for worker in settings}:
        raise RuntimeError('The extended language/worker comparison is incomplete')
    if any(row['inputs'] != rows[0]['inputs'] or row['final_turn'] != rows[0]['final_turn'] for row in rows[1:]):
        raise RuntimeError('Extended runs used different inputs or final turns')
    comparisons = []
    for language in ('en_US', 'ko_KR'):
        base = keyed[language, 0]
        for worker in settings[1:]:
            row = keyed[language, worker]
            for field in ('checkpoint', 'restored_checkpoint', 'final'):
                if row['archive_comparisons'][field]['sections'] != base['archive_comparisons'][field]['sections']:
                    raise RuntimeError(f'Worker mode changed serialized state: {language}/{worker}/{field}')
            if [item['sha256'] for item in row['extended_snapshots']] != [item['sha256'] for item in base['extended_snapshots']] or \
               row['extended_observations'] != base['extended_observations'] or \
               row['extended_events'] != base['extended_events'] or \
               [(b['player'], b['turn'], b['plots']) for b in row['batches']] != [(b['player'], b['turn'], b['plots']) for b in base['batches']]:
                raise RuntimeError('Worker mode changed an observed continuation state or workload')
            comparisons.append({'language': language, 'workers': worker, 'archives_compared': 3,
                                'every_continued_turn_snapshot_equal': True})
    if [item['sha256'] for item in keyed['en_US', 0]['extended_snapshots']] != [item['sha256'] for item in keyed['ko_KR', 0]['extended_snapshots']]:
        raise RuntimeError('The two language runs have different observed continuation state')
    if any(digest(PROJECT / 'tools' / name) != value for name, value in before.items()):
        raise RuntimeError('A validator changed during the verification')
    report = {'status': 'EXTENDED_SDK_NORMAL_TURNS_AFTER_RESTORE_PASS', 'validators': validators,
              'validator_inputs_unchanged': True, 'runs': rows, 'comparisons': comparisons,
              'total_turns_per_run': rows[0]['final_turn'], 'worker_settings': settings,
              'ui_popups_enabled': args.ui_popups,
              'same_language_worker_archive_comparison': bool(comparisons),
              'cross_language_serialized_byte_equality_asserted': False,
              'snapshot_comparison_languages': ['en_US', 'ko_KR'], 'reload_count_per_run': 1,
              'physical_multicore_verified': False, 'performance_improvement_verified': False,
              'retail_save_compatibility_verified': False, 'interactive_gameplay_verified': False,
              'complete_game_equivalence_verified': False, 'accepted_stage_promoted': False,
              'scope': 'CONFIGURED_40x24_HEADLESS_HUMAN_SKIP_REMAINING_UNITS_REAL_AI_TURNS_AFTER_TURN_ONE_RESTORE'}
    check_artifacts(report)
    (ROOT / 'conformance.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf8')
    print(json.dumps({'status': report['status'], 'turns_per_run': report['total_turns_per_run'],
                      'worker_settings': settings, 'runs': len(rows)}), flush=True)


if __name__ == '__main__':
    main()
