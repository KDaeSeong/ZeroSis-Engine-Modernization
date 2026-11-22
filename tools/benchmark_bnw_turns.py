"""Measure complete human-to-human turns in fresh processes of one private BNW Host bundle."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import sqlite3
from statistics import median
import subprocess
import sys
import uuid

from collect_baseline import PROJECT, digest, pe_header
from verify_explore_sdk_candidate import comparable_save
from verify_first_turn_candidate import inspect_save
from verify_found_value_shared_sdk_candidate import parse_shared_layouts, parse_trace_block, semantic_signature
from verify_native_save_restore import inspect_snapshot, one

MODULES = ('ZeroSisHost_x64.exe', 'CvGameCoreDLL_Expansion2_x64.dll', 'ZeroSisDatabase_x64.dll',
           'ZeroSisLocalization_x64.dll', 'ZeroSisLua51_x64.dll')
DATA = ('rules.db', 'localization.db', 'icudt44l.dat', 'audio-catalog.bin', 'script-catalog.bin')
MODES = (0, 1, 2, 4)
ORDER = (0, 1, 3, 2)  # Four rotations balance position and preceding mode.
PREFIX = 'EXTENDED_TURN_CYCLE_'
SHUTDOWN = 'NATIVE_RESTORE_SHUTDOWN_PASS GAMECORE_LOADED=true RESTORE_VERIFIED=true RESUMED_TURN_VERIFIED=true'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def save_json(path, value):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temp.replace(path)


def signature(value):
    return hashlib.sha256(json.dumps(value, separators=(',', ':'), sort_keys=True).encode()).hexdigest()


def bundle_files(source):
    manifest = source / 'bundle.manifest'
    expected = {}
    if manifest.is_file():
        lines = manifest.read_text(encoding='ascii').splitlines()
        require(lines and lines[0] == 'ZEROSIS_HOST_BUNDLE_V4', 'Expected a shared-Lua V4 Host bundle')
        for line in lines[1:]:
            match = re.fullmatch(r'([A-Za-z0-9_][A-Za-z0-9_.-]*)\|([0-9a-fA-F]{64})', line)
            require(match is not None, 'Malformed bundle entry')
            name, sha = match.groups()
            require(name.lower() not in {n.lower() for n in expected}, 'Duplicate bundle entry: ' + name)
            expected[name] = sha.lower()
        require(set(MODULES + DATA) <= expected.keys(), 'Incomplete V4 manifest')
    else:
        expected = dict.fromkeys(MODULES + DATA)
    missing = [str(source / name) for name in expected if not (source / name).is_file()]
    files = {}
    for name, expected_sha in expected.items():
        path = source / name
        if not path.is_file():
            continue
        actual = digest(path)
        require(expected_sha in (None, actual), 'Source bundle hash mismatch: ' + name)
        if name in MODULES:
            pe = pe_header(path)
            require(pe['architecture'] == 'x64' and pe['is_dll'] == name.endswith('.dll'), 'Wrong module: ' + name)
        files[name] = actual
    return files, missing


def private_bundle(source, target, files):
    target.mkdir(parents=True, exist_ok=False)
    for name, sha in files.items():
        shutil.copyfile(source / name, target / name)
        require(digest(target / name) == sha and digest(source / name) == sha, 'Bundle input changed: ' + name)
    manifest = source / 'bundle.manifest'
    if manifest.is_file():
        shutil.copyfile(manifest, target / manifest.name)
    else:
        (target / 'bundle.manifest').write_text('ZEROSIS_HOST_BUNDLE_V4\n' +
            ''.join(f'{name}|{sha}\n' for name, sha in files.items()), encoding='ascii')
    require(bundle_files(target) == (files, []), 'Private bundle differs from verified inputs')


def statistics_us(samples):
    require(samples and all(type(x) is int and x > 0 for x in samples), 'Invalid whole-turn durations')
    center = median(samples)
    return dict(n=len(samples), minimum=min(samples), median=center, maximum=max(samples),
                mad=median(abs(x - center) for x in samples))


def order_for_round(index):
    return [MODES[(level + index) % len(MODES)] for level in ORDER]


def turn_row(part, begin, prefix=PREFIX):
    def field(name):
        return one(part, prefix + name)
    start, before = map(int, field('BENCH_BEGIN').split('|'))
    end, after, count = map(int, field('BENCH_END').split('|'))
    require((start, end) == (begin, begin + 1) and all(0 <= n < 2**32 for n in (before, after)),
            'Wrong turn or synchronous RNG boundary')
    require(field('PLAYER_OPTION') == 'PLAYEROPTION_WAIT_END_TURN:1' and
            field('INPUT') == 'MISSION_SKIP_EACH_UNIT_THEN_CONTROL_ENDTURN', 'Unexpected input policy')
    positions = [part.index(prefix + key + '=') for key in ('BENCH_BEGIN', 'PLAYER_OPTION', 'INPUT',
                 'BENCH_END', 'OBSERVATION', 'DURATION_US')]
    require(positions == sorted(positions), 'Reordered timer, input or SDK boundary records')
    skipped = field('BENCH_SKIPPED_UNITS')
    require(skipped == '-' or re.fullmatch(r'\d+(,\d+)*', skipped), 'Malformed mission order')
    units = [] if skipped == '-' else list(map(int, skipped.split(',')))
    require(len(set(units)) == len(units), 'Duplicated unit skip')
    events = re.findall(r'^' + prefix + r'BENCH_EVENT=(\d+)\|(local-[^\r\n]+)$', part, re.M)
    require([int(index) for index, _ in events] == list(range(count)), 'Incomplete ordered local events')
    events = [event for _, event in events]
    boundaries = ['local-turn-complete', f'local-turn-all-complete:{begin}', f'local-turn-boundary:{begin}']
    require([e for e in events if e in boundaries] == boundaries and 'local-turn-complete-cancelled' not in events,
            'Missing, reordered or cancelled SDK end-turn commands')
    observation = list(map(int, field('OBSERVATION').split(',')))
    frames = [tuple(map(int, values.split(','))) for values in re.findall(r'^' + prefix + r'STATE=\d+\|([^\n]+)$', part, re.M)]
    indices = [int(x) for x in re.findall(r'^' + prefix + r'STATE=(\d+)\|', part, re.M)]
    require(observation == [begin, end, end, 0, 1, 1, len(frames), 3] and 1 <= len(frames) <= 256 and
            indices == list(range(1, len(frames) + 1)) and frames[-1] == (end, end, 1, 1, 1) and
            all(len(f) == 5 and f[:2] == (begin, begin) and all(v in (0, 1) for v in f[2:]) for f in frames[:-1]) and
            (begin, begin, 0, 0, 0) in frames, 'Incomplete AI update/human-turn boundary')
    duration = int(field('DURATION_US'))
    require(duration > 0, 'Missing actual whole-turn duration')
    return dict(begin=begin, end=end, sync_rng=[before, after], skipped_unit_ids=units, ordered_local_events=events,
                observable_frames=frames,
                promotion_actions=re.findall(r'^' + prefix + r'(?:ACTION|PROMOTION|INPUT_ROUTE)=[^\n]+', part, re.M)), duration


def inspect_run(output, bundle, start, stop, mode, diagnostic, human):
    require(output.splitlines().count(SHUTDOWN) == 1 and one(output, 'RESTORED_CORE_MODULE_UNLOADED') == 'true' and
            one(output, 'NATIVE_RESTORE_FRESH_SESSION') == 'true', 'Actual GameCore restore/shutdown did not complete')
    seeds = list(map(int, one(output, 'FULL_TURN_SEEDS').split(',')))
    require(seeds == [0x5A17C0DE, 0x0BADC0DE], 'Unexpected initial map/sync seeds')
    majors = list(map(int, one(output, 'FULL_TURN_MAJORS').split(',')))
    with sqlite3.connect((bundle/'rules.db').as_uri()+'?mode=ro&immutable=1', uri=True) as db:
        wanted = []
        for civilization in (human, 'CIVILIZATION_ROME'):
            rows = db.execute('SELECT c.ID,l.ID FROM Civilizations c JOIN Civilization_Leaders cl ON cl.CivilizationType=c.Type '
                              'JOIN Leaders l ON l.Type=cl.LeaderheadType WHERE c.Type=?', (civilization,)).fetchall()
            require(len(rows) == 1, 'Ambiguous fixture leader for ' + civilization)
            wanted.extend(rows[0])
    require(majors == wanted, 'Actual SDK major players differ from requested fixture')
    require(one(output, 'EXTENDED_TURNS_BEGIN') == f'2,{stop-2}' and
            one(output, 'EXTENDED_TURNS_COMPLETE') == f'2,{stop},{stop-2}', 'Wrong extended turn range')
    restored = Path(one(output, 'RESTORE_SESSION_DIRECTORY')).resolve(strict=True)
    initial = Path(one(output, 'SESSION_DIRECTORY')).resolve(strict=True)
    require(initial != restored and initial.parent == restored.parent == (bundle/'sessions').resolve(),
            'Sessions escaped the private benchmark bundle')
    original_fixture = human == 'CIVILIZATION_AMERICA'
    def snapshot(data, turn, initial_fixture=False):
        return inspect_snapshot(data, turn, initial_fixture, allow_empty_cities=not original_fixture)
    entry = snapshot((restored/'state-after-resumed-turn.txt').read_bytes(), 2)
    initial_state = snapshot((initial/'state-before-save.txt').read_bytes(), 1, original_fixture)
    require(snapshot((restored/'state-after-restore.txt').read_bytes(), 1, original_fixture) == initial_state,
            'Fresh restore changed the starting SDK state')
    block = output.split('EXTENDED_TURNS_BEGIN=', 1)[1].split('EXTENDED_TURNS_COMPLETE=', 1)[0]
    parts = block.split(PREFIX + 'BENCH_BEGIN=')[1:]
    require(len(parts) == stop - 2, 'Missing per-turn benchmark markers in Host')
    states, times, observed_jobs = [], {}, []
    for begin, part in enumerate(parts, 2):
        part = PREFIX + 'BENCH_BEGIN=' + part
        state, duration = turn_row(part, begin)
        snap = (restored / f'extended-state-turn-{begin+1}.txt').read_bytes()
        require(one(part, 'EXTENDED_TURN_SNAPSHOT') == f'{begin+1},{len(snap)}', 'Wrong SDK snapshot or size')
        state['snapshot_sha256'] = snapshot(snap, begin + 1)['sha256']
        states.append(state)
        if begin >= start:
            times[begin] = duration
            inside = part.split(PREFIX + 'BENCH_END=', 1)[0]
            observed_jobs.extend(int(n) for n in re.findall(r'^ZEROSIS_FOUND_VALUE_TRACE [^\n]*\bjobs_completed=(\d+)\b', inside, re.M))
    archive = inspect_save(restored / 'state-after-extended-turns.zssave', bundle / 'bundle.manifest',
                           restored / 'Civ5SavedGameDatabase.db', (1, 0, stop, stop, 0, 64, 64, 133))
    warmup = output.split('EXTENDED_TURNS_BEGIN=', 1)[0]
    startup = [turn_row(warmup, 0, 'TURN_CYCLE_')[0], turn_row(warmup, 1, 'RESTORED_TURN_CYCLE_')[0]]
    observable = dict(seeds=seeds, majors=majors, startup=startup, initial_state=initial_state['sha256'], restored_turn_two=entry['sha256'],
                      turns=states, final_sections=comparable_save(archive)['sections'])
    if diagnostic:
        calls = parse_trace_block(output, mode, final_turn=stop)
        parse_shared_layouts(output, calls)
        require(observed_jobs and (not mode or sum(observed_jobs) > 0), 'No verified FoundValue work in measured turns')
        audited = dict(score_signature=signature(semantic_signature(calls)), jobs_in_interval=sum(observed_jobs))
    else:
        require('ZEROSIS_FOUND_VALUE_TRACE ' not in output and 'ZEROSIS_FOUND_VALUE_LAYOUT ' not in output,
                'FoundValue diagnostic logging leaked into timed run')
        audited = None
    return observable, times, audited


def launch(bundle, args, archive, mode, diagnostic):
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith('ZEROSIS_')}
    overrides = dict(ZEROSIS_FULL_TURN_BENCHMARK='1', ZEROSIS_EXPLORE_WORKERS='0', ZEROSIS_CITY_SITE_WORKERS='0',
                     ZEROSIS_FOUND_VALUE_WORKERS=str(mode), ZEROSIS_FOUND_VALUE_TRACE=str(int(diagnostic)))
    if args.human != 'CIVILIZATION_AMERICA':
        overrides['ZEROSIS_BENCHMARK_HUMAN'] = args.human
    env.update(overrides)
    command = [str(bundle / MODULES[0]), '--check-save-restore-ui-actions' if args.ui_actions else '--check-save-restore',
               args.language, str(args.stop_turn-2)]
    archive.mkdir()
    save_json(archive/'request.json', dict(command=command, environment=overrides, timeout_seconds=args.timeout))
    with (archive/'stdout.log').open('wb') as out, (archive/'stderr.log').open('wb') as err:
        proc = subprocess.run(command, cwd=bundle, env=env, stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                              timeout=args.timeout, creationflags=subprocess.CREATE_NO_WINDOW)
    if proc.returncode:
        detail = (archive/'stderr.log').read_bytes()[-1600:].decode('utf-8', errors='replace').strip()
        raise RuntimeError(f'Host exited {proc.returncode} in {archive}. {detail}')
    output = (archive/'stdout.log').read_bytes().decode('utf-8', errors='strict').replace('\r\n', '\n')
    state, times, audited = inspect_run(output, bundle, args.start_turn, args.stop_turn, mode, diagnostic, args.human)
    save_json(archive/'observations.json', state)
    return dict(workers=mode, observed_sha256=signature(state), verification=audited, samples_us=times,
                stdout_sha256=digest(archive/'stdout.log'), directory=str(archive))


def run(args, report, evidence):
    source = args.bundle.resolve()
    files, missing = bundle_files(source)
    report.update(bundle_source=str(source), input_sha256=files, missing_inputs=missing)
    if missing:
        report['status'] = 'BLOCKED_MISSING_RUNTIME_INPUTS'
        return 2
    if args.inspect:
        report['status'] = 'INPUT_FILES_VERIFIED'
        return 0
    bundle = PROJECT/'Build/FullTurnBenchmark/runs'/evidence.name/'bundle'
    private_bundle(source, bundle, files)
    report['private_bundle'] = str(bundle)
    report['manifest_sha256'] = digest(bundle/'bundle.manifest')
    reference = scores = None
    for mode in MODES:
        row = launch(bundle, args, evidence/f'verify-{mode}', mode, True)
        if reference is None:
            reference, scores = row['observed_sha256'], row['verification']['score_signature']
        require((row['observed_sha256'], row['verification']['score_signature']) == (reference, scores),
                f'State, RNG, commands, archive or ordered score mismatch for {mode} workers')
        row.pop('samples_us')
        report['diagnostics'].append(row)
    runs = []
    for index in range(args.repeats):
        for mode in order_for_round(index):
            row = launch(bundle, args, evidence/f'round-{index+1}-{mode}', mode, False)
            require(row['observed_sha256'] == reference, f'Semantic mismatch in repeat {index+1}, mode {mode}')
            runs.append(dict(round=index+1, **row))
    require(bundle_files(bundle) == (files, []) and digest(bundle/'bundle.manifest') == report['manifest_sha256'],
            'Private inputs changed during benchmark')
    summaries = {}
    for mode in MODES:
        rows = [r['samples_us'] for r in runs if r['workers'] == mode]
        summaries[mode] = dict(range_total_us=statistics_us([sum(r.values()) for r in rows]),
                               by_start_turn_us={t: statistics_us([r[t] for r in rows]) for t in range(args.start_turn, args.stop_turn)})
    report.update(status='ACTUAL_BNW_FULL_TURN_COMPARISON_PASS',timed_runs=runs, summary=summaries)
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, default=PROJECT/'Build/FullTurnBenchmark/inputs')
    parser.add_argument('--start-turn', type=int, default=2)
    parser.add_argument('--stop-turn', type=int, default=4, help='Exclusive starting-turn bound; final human turn')
    parser.add_argument('--repeats', type=int, default=4)
    parser.add_argument('--timeout', type=int, default=300)
    parser.add_argument('--language', choices=('en_US','ko_KR'), default='en_US')
    parser.add_argument('--human', default='CIVILIZATION_AMERICA', help='Explicit playable civilization in the fixed database')
    parser.add_argument('--ui-actions', action='store_true', help='Enable the official headless promotion/action fixture')
    parser.add_argument('--inspect', action='store_true')
    args = parser.parse_args()
    if not 2 <= args.start_turn < args.stop_turn <= 100 or args.repeats < 2 or args.timeout <= 0:
        parser.error('Require 2 <= start-turn < stop-turn <= 100, repeats >= 2 and positive timeout')
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ_')+uuid.uuid4().hex[:10]
    evidence = PROJECT/'evidence/full_turn_benchmark'/run_id
    evidence.mkdir(parents=True, exist_ok=False)
    report = dict(status='STARTED', run_id=run_id, diagnostics=[], timed_runs=[], summary=None,
                  language=args.language, human=args.human, ai='CIVILIZATION_ROME', start_turn=args.start_turn, stop_turn=args.stop_turn,
                  ui_actions=args.ui_actions, repeats=args.repeats, order=[order_for_round(i) for i in range(args.repeats)],
                  host_os=platform.platform(), processor=platform.processor(), logical_cpus=os.cpu_count(),
                  clock='Host std::chrono::steady_clock in FirstTurnProbe::AdvanceOneTurn, microseconds',
                  workload='unit skip, normal end-turn control, GameCore updates until next human activation',
                  warmup='one untimed FoundValue verification process per mode; turns before start excluded',
                  extra_workers='Explore and CitySite both 0', normalization='only map GUID at bytes 34..49 of archive map section')
    try:
        code = run(args, report, evidence)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        report.update(status='FAILED', error=str(exc))
        code = 1
    finally:
        save_json(evidence/'result.json', report)
    print(json.dumps(dict(status=report['status'], result=str(evidence/'result.json'),
                          missing=report.get('missing_inputs', []), error=report.get('error'))))
    return code


if __name__ == '__main__':
    sys.exit(main())
