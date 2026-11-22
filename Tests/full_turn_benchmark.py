"""Parser and statistics regressions only. These records never enter a performance report."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import benchmark_bnw_turns as bench


def fixture():
    lines = [
        'BENCH_BEGIN=2|123', 'PLAYER_OPTION=PLAYEROPTION_WAIT_END_TURN:1',
        'INPUT=MISSION_SKIP_EACH_UNIT_THEN_CONTROL_ENDTURN',
        'STATE=1|2,2,0,0,0', 'STATE=2|3,3,1,1,1',
        'BENCH_SKIPPED_UNITS=7,4', 'BENCH_EVENT=0|local-turn-complete',
        'BENCH_EVENT=1|local-turn-all-complete:2', 'BENCH_EVENT=2|local-turn-boundary:2',
        'BENCH_END=3|456|3', 'OBSERVATION=2,3,3,0,1,1,2,3', 'DURATION_US=17',
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


if __name__ == '__main__':
    unittest.main()
