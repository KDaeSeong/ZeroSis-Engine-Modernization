"""Attribute FoundValue wall time from the four trace-on logs of a completed BNW turn benchmark."""
import argparse
import hashlib
import json
import sys
from pathlib import Path

from benchmark_bnw_turns import MODES, extended_turn_blocks, require, signature, turn_row
from verify_found_value_shared_sdk_candidate import (
    TAG_TRACE, parse_kv, parse_shared_layouts, parse_trace_block, semantic_signature,
)


PHASES = ('snapshot_us', 'worker_us', 'shadow_us', 'reduction_us')


def summarize(traces, host_us):
    worker_calls = [trace for trace in traces if trace['mode'] == 'owned-worker']
    phases = {key: sum(trace[key] for trace in worker_calls) if worker_calls else None for key in PHASES}
    total = sum(trace['total_us'] for trace in traces)
    # Serial calls only have total_us. Their entire duration falls outside the four child timers.
    unitemized = total - sum(value for value in phases.values() if value is not None)
    require(unitemized >= 0 and total <= host_us, 'FoundValue timings exceed their enclosing timer')
    return dict(calls=len(traces), worker_calls=len(worker_calls),
                jobs_completed=sum(trace['jobs_completed'] for trace in traces),
                **phases, unitemized_us=unitemized, total_us=total, diagnostic_turn_us=host_us)


def analyze_log(output, mode, start, stop, expected):
    calls = parse_trace_block(output, mode, final_turn=stop)
    parse_shared_layouts(output, calls)
    require(signature(semantic_signature(calls)) == expected['score_signature'], 'Changed FoundValue scores')
    # Call IDs restart when the DLL is loaded for the restored game.
    restored_calls = {call['call_id']: call for call in calls if call['session'] == 1}
    restored = output.split('\nNATIVE_RESTORE_FRESH_SESSION=true\n', 1)[1]
    by_turn, comparable, measured = {}, [], []
    for begin, part, inside in extended_turn_blocks(restored, stop):
        state, host_us = turn_row(part, begin)
        if begin < start:
            continue
        selected = [restored_calls[int(parse_kv(line[len(TAG_TRACE):])['call_id'])]
                    for line in inside.splitlines() if line.startswith(TAG_TRACE)]
        comparable.append(signature([state, semantic_signature(selected)]))
        traces = [call['trace'] for call in selected]
        by_turn[begin] = summarize(traces, host_us)
        measured.extend(traces)
    totals = summarize(measured, sum(row['diagnostic_turn_us'] for row in by_turn.values()))
    require(measured and totals['jobs_completed'] == expected['jobs_in_interval'],
            'Measured FoundValue work differs from the verified interval')
    return dict(by_start_turn=by_turn, totals=totals), comparable


def analyze(result):
    report = json.loads(result.read_bytes())
    require(report['status'] == 'ACTUAL_BNW_FULL_TURN_COMPARISON_PASS', 'Expected a completed turn benchmark')
    start, stop = report['start_turn'], report['stop_turn']
    require(2 <= start < stop <= 100, 'Invalid measured turn range')
    rows = report['diagnostics']
    require([row['workers'] for row in rows] == list(MODES), 'Incomplete FoundValue diagnostics')
    modes = {}
    reference = None
    for row in rows:
        mode = row['workers']
        raw = (result.parent / f'verify-{mode}' / 'stdout.log').read_bytes()
        require('samples_us' not in row and hashlib.sha256(raw).hexdigest() == row['stdout_sha256'],
                f'Expected the original trace-on log for {mode} workers')
        output = raw.decode('utf-8').replace('\r\n', '\n')
        modes[mode], comparable = analyze_log(output, mode, start, stop, row['verification'])
        if mode == 0:
            reference = comparable
        require(comparable == reference, f'Turn observations or in-window FoundValue calls differ for {mode} workers')
    return dict(run_id=report['run_id'], start_turn=start, stop_turn=stop, modes=modes)


def markdown(profile):
    lines = ['| 워커 | 관측 수집 | 워커 호출 | 직렬 대조 | 합산·반영 | 세부 타이머 밖 | FoundValue 전체 | 진단 턴 전체 |',
             '|---:|---:|---:|---:|---:|---:|---:|---:|']
    for mode, data in profile['modes'].items():
        row = data['totals']
        values = [mode, *(row[key] for key in (*PHASES, 'unitemized_us', 'total_us', 'diagnostic_turn_us'))]
        lines.append('| ' + ' | '.join('—' if n is None else f'{n:,}' for n in values) + ' |')
    return '\n'.join(lines)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__ + ' All durations are microseconds.')
    parser.add_argument('result', type=Path, help='result.json alongside verify-{0,1,2,4}/stdout.log')
    parser.add_argument('--json', action='store_true', help='Include per-turn times and call/job counts')
    args = parser.parse_args()
    profile = analyze(args.result)
    sys.stdout.reconfigure(encoding='utf-8')
    if args.json:
        print(json.dumps(profile, indent=2))
    else:
        print(f"FoundValue 상세 추적 · {profile['start_turn']}→{profile['stop_turn']}턴 합계 · µs\n")
        print(markdown(profile))
