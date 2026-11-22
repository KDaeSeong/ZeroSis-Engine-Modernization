"""Parser and statistics regressions only. These records never enter a performance report."""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

TESTS = Path(__file__).resolve().parent
sys.path[:0] = [str(TESTS.parent / 'tools'), str(TESTS)]
import benchmark_bnw_turns as bench
import analyze_found_value_phases as phases
from found_value_shared_layout_validator import fixture as shared_trace_fixture


def fixture(begin=2):
    end = begin + 1
    lines = [
        f'BENCH_BEGIN={begin}|123', 'PLAYER_OPTION=PLAYEROPTION_WAIT_END_TURN:1',
        'INPUT=MISSION_SKIP_EACH_UNIT_THEN_CONTROL_ENDTURN',
        f'STATE=1|{begin},{begin},0,0,0', f'STATE=2|{end},{end},1,1,1',
        'BENCH_SKIPPED_UNITS=7,4', 'BENCH_EVENT=0|local-turn-complete',
        f'BENCH_EVENT=1|local-turn-all-complete:{begin}', f'BENCH_EVENT=2|local-turn-boundary:{begin}',
        f'BENCH_END={end}|456|3', f'OBSERVATION={begin},{end},{end},0,1,1,2,3', 'DURATION_US=17',
    ]
    return '\n'.join(bench.PREFIX + line for line in lines) + '\n'


class BenchmarkChecks(unittest.TestCase):
    def test_observed_sequences_and_timing(self):
        state, duration = bench.turn_row(fixture(), 2)
        self.assertEqual((duration, state['sync_rng'], state['skipped_unit_ids']), (17, [123, 456], [7, 4]))
        self.assertEqual(bench.turn_row(fixture().replace('DURATION_US=17', 'DURATION_US=19'), 2)[0], state)
        for before, after in [('7,4','4,7'), ('3|456|3','3|457|3')]:
            self.assertNotEqual(bench.signature(bench.turn_row(fixture().replace(before, after), 2)[0]),
                                bench.signature(state))

    def test_rejected_partial_or_invalid_turn(self):
        for before, after in [('DURATION_US=17','DURATION_US=0'), ('|2,2,0,0,0','|2,2,1,1,1'),
                              ('STATE=2|','STATE=3|'), ('BENCH_END=3|','BENCH_END=4|'),
                              ('EVENT=1|','EVENT=0|'), ('SKIPPED_UNITS=7,4','SKIPPED_UNITS=7,7'),
                              ('local-turn-complete','local-turn-complete-cancelled'),
                              ('BENCH_BEGIN=2|123','BENCH_BEGIN=2|4294967296')]:
            with self.subTest(before=before), self.assertRaises((ValueError, RuntimeError)):
                bench.turn_row(fixture().replace(before,after), 2)

    def test_block_order_and_spread(self):
        rounds = [bench.order_for_round(i) for i in range(4)]
        for row in rounds + list(zip(*rounds)):
            self.assertEqual(set(row), set(bench.MODES))
        self.assertEqual(len({pair for row in rounds for pair in zip(row, row[1:])}), 12)
        self.assertEqual(bench.statistics_us([10, 12, 14, 24]),
                         dict(n=4, minimum=10, median=13, maximum=24, mad=2))
        for bad in ([], [0], [True], [-1]):
            with self.assertRaises(ValueError):
                bench.statistics_us(bad)

    def test_missing_or_ambiguous_bundle(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp)
            self.assertEqual(len(bench.bundle_files(folder)[1]), 10)
            for entries in (['../escape'], ['rules.db','RULES.DB']):
                (folder/'bundle.manifest').write_text('ZEROSIS_HOST_BUNDLE_V4\n'+
                    ''.join(name+'|'+'0'*64+'\n' for name in entries), encoding='ascii')
                with self.assertRaises(ValueError):
                    bench.bundle_files(folder)

    def test_cityless_snapshot_still_checks_every_player(self):
        rows = ['G|2|2|0|960']
        rows.extend(f'M|{i}|{i%40}|{i//40}|0|0|-1|-1|0|-1|-1|-1' for i in range(960))
        for i in range(64):
            alive = int(i in (0, 1, 22, 23, 63))
            human = int(i == 0)
            rows.append(f'P|{i}|{alive}|{human}|{human}|{i}|0|{human}|0|0|-1')
            rows.append(f'T|{i}|0|0')
        rows.append('U|0|7|0|0|0|0|0|0|1|0|0|')
        state = ('\n'.join(rows)+'\n').encode()
        self.assertEqual(bench.inspect_snapshot(state, 2, False, True)['row_counts']['C'], 0)
        with self.assertRaises(RuntimeError):
            bench.inspect_snapshot(state, 2, False)
        with self.assertRaises(RuntimeError):
            bench.inspect_snapshot(state.replace(b'P|0|1|1|1|0|0|1|', b'P|0|1|1|1|0|1|1|'), 2, False, True)


class FoundValuePhases(unittest.TestCase):
    def test_inclusive_timers_and_uninstrumented_serial(self):
        worker = dict(mode='owned-worker', snapshot_us=3, worker_us=5, shadow_us=6,
                      reduction_us=4, total_us=20, jobs_completed=2)
        scalar = dict(mode='scalar-original', snapshot_us=0, worker_us=0, shadow_us=0,
                      reduction_us=0, total_us=9, jobs_completed=0)
        self.assertEqual(phases.summarize([worker, scalar], 48), dict(
            calls=2, worker_calls=1, jobs_completed=2, snapshot_us=3, worker_us=5,
            shadow_us=6, reduction_us=4, unitemized_us=11, total_us=29, diagnostic_turn_us=48))
        serial = phases.summarize([scalar], 15)
        self.assertTrue(all(serial[key] is None for key in phases.PHASES))
        self.assertEqual((serial['unitemized_us'], serial['total_us']), (9, 9))
        with self.assertRaisesRegex(ValueError, 'enclosing timer'):
            phases.summarize([worker], 19)

    def test_only_calls_between_host_markers_in_the_requested_restored_turns(self):
        restore = 'NATIVE_RESTORE_FRESH_SESSION=true\n'
        initial, template = shared_trace_fixture().split(restore)

        def call(call_id, turn, total):
            return (template.replace('call_id=1 ', f'call_id={call_id} ').replace('turn=2 ', f'turn={turn} ')
                    .replace('total_us=10 ', f'total_us={total} ')
                    .replace('cpu_batch_id=200 ', f'cpu_batch_id={200 + call_id} ') + '\n')

        # Call 1 is reused after restore. Call 2 has the same SDK turn as call 3,
        # but occurs during the idle updates after BENCH_END. Call 4 is after the range.
        def insert_before(turn, key, records):
            marker = bench.PREFIX + key + '='
            return turn.replace(marker, records + marker)

        turn2 = insert_before(fixture(2), 'BENCH_END', call(1, 2, 10))
        turn2 = insert_before(turn2, 'DURATION_US', call(2, 3, 100))
        turn3 = insert_before(fixture(3), 'BENCH_END', call(3, 3, 12))
        log = (initial.replace('total_us=10 ', 'total_us=500 ') + restore + 'EXTENDED_TURNS_BEGIN=2,2\n'
               + turn2 + turn3 + 'EXTENDED_TURNS_COMPLETE=2,4,2\n' + call(4, 3, 200))
        scores = bench.signature(bench.semantic_signature(bench.parse_trace_block(log, 2)))
        expected = dict(score_signature=scores, jobs_in_interval=4)
        full, _ = phases.analyze_log(log, 2, 2, 4, expected)
        self.assertEqual([r['total_us'] for r in full['by_start_turn'].values()], [10, 12])
        self.assertEqual(full['totals'], dict(calls=2, worker_calls=2, jobs_completed=4, snapshot_us=2,
            worker_us=4, shadow_us=2, reduction_us=2, unitemized_us=12, total_us=22, diagnostic_turn_us=34))
        tail, _ = phases.analyze_log(log, 2, 3, 4, dict(expected, jobs_in_interval=2))
        self.assertEqual(tail['totals'], full['by_start_turn'][3])
        with self.assertRaisesRegex(ValueError, 'verified interval'):
            phases.analyze_log(log, 2, 3, 4, expected)
        with self.assertRaisesRegex(RuntimeError, 'phase timings'):
            phases.analyze_log(log.replace('total_us=12 ', 'total_us=4 '), 2, 2, 4, expected)
        with self.assertRaisesRegex(ValueError, 'end of measured Host turn'):
            phases.analyze_log(log.replace(bench.PREFIX + 'BENCH_END=3', 'OTHER_END=3'), 2, 2, 4, expected)

    def test_changed_log_or_trace_off_sample_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'verify-0').mkdir()
            raw = b'example'
            (root / 'verify-0' / 'stdout.log').write_bytes(raw)
            result = root / 'result.json'
            rows = [dict(workers=mode) for mode in bench.MODES]
            report = dict(status='ACTUAL_BNW_FULL_TURN_COMPARISON_PASS', start_turn=2, stop_turn=4, diagnostics=rows)
            for invalid in (dict(stdout_sha256='0' * 64),
                            dict(stdout_sha256=hashlib.sha256(raw).hexdigest(), samples_us={'2': 17})):
                rows[0] = dict(workers=0, **invalid)
                result.write_text(json.dumps(report), encoding='utf-8')
                with self.assertRaisesRegex(ValueError, 'trace-on log'):
                    phases.analyze(result)


if __name__ == '__main__':
    unittest.main()
