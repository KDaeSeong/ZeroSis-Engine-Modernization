"""Re-read native archives, SDK snapshots and child transcripts of a completed benchmark."""
import argparse
from collections import defaultdict
import json
import platform
from pathlib import Path
from statistics import median

from benchmark_bnw_turns import MODES, MODULES, bundle_files, inspect_run, order_for_round, require, save_json, signature, statistics_us
from collect_baseline import digest


def verify(result):
    evidence = result.resolve(strict=True).parent
    report = json.loads(result.read_bytes())
    require(report['status'] == 'ACTUAL_BNW_FULL_TURN_COMPARISON_PASS', 'No completed benchmark')
    bundle = Path(report['private_bundle']).resolve(strict=True)
    require(bundle_files(bundle) == (report['input_sha256'], []) and
            digest(bundle/'bundle.manifest') == report['manifest_sha256'], 'Retained runtime bundle changed')
    start, stop, repeats = report['start_turn'], report['stop_turn'], report['repeats']
    require(2 <= start < stop <= 100 and repeats >= 2, 'Invalid measured range or repeat count')
    order = [order_for_round(i) for i in range(repeats)]
    require(report['order'] == order, 'Declared block order differs')
    diagnostics = report['diagnostics']
    timed = report['timed_runs']
    require([r['workers'] for r in diagnostics] == list(MODES), 'Incomplete diagnostic matrix')
    require([(r['round'],r['workers']) for r in timed] ==
            [(i+1,m) for i,modes in enumerate(order) for m in modes], 'Incomplete or reordered timed matrix')
    states, scores, sessions = set(), set(), set()
    reference_state = None
    samples = defaultdict(list)
    for trace, rows in ((True, diagnostics), (False, timed)):
        for row in rows:
            mode = row['workers']
            folder = evidence/(f'verify-{mode}' if trace else f'round-{row["round"]}-{mode}')
            require(folder == Path(row['directory']).resolve(strict=True), 'Unexpected sample directory')
            request = json.loads((folder/'request.json').read_bytes())
            command = [str(bundle/MODULES[0]), '--check-save-restore-ui-actions' if report['ui_actions'] else '--check-save-restore',
                       report['language'], str(stop-2)]
            overrides = dict(ZEROSIS_FULL_TURN_BENCHMARK='1', ZEROSIS_EXPLORE_WORKERS='0', ZEROSIS_CITY_SITE_WORKERS='0',
                             ZEROSIS_FOUND_VALUE_WORKERS=str(mode), ZEROSIS_FOUND_VALUE_TRACE=str(int(trace)))
            if report['human'] != 'CIVILIZATION_AMERICA':
                overrides['ZEROSIS_BENCHMARK_HUMAN'] = report['human']
            require(request['command'] == command and request['environment'] == overrides, 'Fixture command/environment changed')
            log = folder/'stdout.log'
            require(digest(log) == row['stdout_sha256'] and not (folder/'stderr.log').read_bytes(), 'Changed or failed child log')
            output = log.read_text(encoding='utf-8')
            for key in ('SESSION_DIRECTORY=', 'RESTORE_SESSION_DIRECTORY='):
                paths = [s[len(key):] for s in output.splitlines() if s.startswith(key)]
                require(len(paths)==1 and paths[0] not in sessions, 'Duplicate native session')
                sessions.add(paths[0])
            state, times, audited = inspect_run(output,bundle,start,stop,mode,trace,report['human'])
            if reference_state is None:
                reference_state = state
            require(state == reference_state, f'Native state, RNG, command sequence or save differs in {folder.name}')
            stamp = signature(state)
            require(stamp == row['observed_sha256'] == signature(json.loads((folder/'observations.json').read_bytes())),
                    'Persisted observations differ from SDK artifacts')
            states.add(stamp)
            require(audited == row['verification'], 'Worker diagnostics differ')
            if trace:
                scores.add(audited['score_signature'])
                require('samples_us' not in row, 'Diagnostic timing was published as a sample')
            else:
                require(times == {int(k):v for k,v in row['samples_us'].items()}, 'Timing differs from Host clock output')
                samples[mode].append(times)
    require(len(states) == len(scores) == 1, 'State, synchronous RNG, commands or FoundValue scores diverged')
    paired = {}
    for mode, rows in samples.items():
        expected = dict(range_total_us=statistics_us([sum(r.values()) for r in rows]),
                        by_start_turn_us={str(t):statistics_us([r[t] for r in rows]) for t in range(start,stop)})
        require(report['summary'][str(mode)] == expected, 'Timing summary differs')
        delta = [sum(worker.values())-sum(serial.values()) for worker,serial in zip(rows,samples[0],strict=True)]
        paired[mode] = dict(per_round=delta, median=median(delta), minimum=min(delta), maximum=max(delta))
    return dict(status='ACTUAL_BNW_FULL_TURN_EVIDENCE_VERIFIED', result_sha256=digest(result),
                distinct_sessions=len(sessions), diagnostics=len(diagnostics), timed_processes=len(timed),
                full_turn_samples_per_mode=repeats*(stop-start), state_rng_commands_archive_sha256=next(iter(states)),
                found_scores_sha256=next(iter(scores)), paired_range_delta_us=paired)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('result', type=Path)
    args = parser.parse_args()
    proof = verify(args.result)
    if platform.system() == 'Windows':
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'HARDWARE\DESCRIPTION\System\CentralProcessor\0') as key:
            proof['processor_model'] = winreg.QueryValueEx(key, 'ProcessorNameString')[0].strip()
    save_json(args.result.resolve().with_name('verification.json'), proof)
    print(json.dumps(proof))
