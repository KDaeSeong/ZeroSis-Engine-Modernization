"""Reject stale or mismatched timer evidence for the native tree Escape gate."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from verify_interactive_decisions import native_tree_escape_timer


class NativeTreeEscapeTimer(unittest.TestCase):
    TRACE = ('INTERACTIVE_UI_NATIVE_INPUT=4|1|790|1\n'
             'UI_WINDOW_INPUT=3|1|27|1|41|41|1|0|0|1234\n'
             'INTERACTIVE_UI_NATIVE_INPUT=5|0|0|1\n'
             'INTERACTIVE_UI_NATIVE_KEY=5|research-tree|27|1|0\n')

    def test_same_dispatch_release(self):
        proof = native_tree_escape_timer(self.TRACE, 5, 0)
        self.assertEqual((proof['timer_held_before'], proof['timer_held_after']), (1, 0))
        self.assertTrue(proof['same_native_dispatch_verified'])

    def test_reject_mismatched_and_stale_evidence(self):
        timer = 'UI_WINDOW_INPUT=3|1|27|1|41|41|1|0|0|1234\n'
        cases = {
            'missing_timer': self.TRACE.replace(timer, ''),
            'timer_still_held': self.TRACE.replace('|41|41|1|0|', '|41|41|1|1|'),
            'already_released': self.TRACE.replace('|41|41|1|0|', '|41|41|0|0|'),
            'rng_changed': self.TRACE.replace('|41|41|', '|41|42|'),
            'wrong_turn': self.TRACE.replace('|1|0|0|1234', '|1|0|1|1234'),
            'wrong_key': self.TRACE.replace('INPUT=3|1|27|', 'INPUT=3|1|13|'),
            'wrong_popup_kind': self.TRACE.replace('INPUT=3|1|27|', 'INPUT=3|2|27|'),
            'not_consumed': self.TRACE.replace('INPUT=3|1|27|1|', 'INPUT=3|1|27|0|'),
            'missing_owner': self.TRACE.replace('|0|1234\n', '|0|0\n'),
            'native_generation_mismatch': self.TRACE.replace('INPUT=5|0|0|1', 'INPUT=6|0|0|1'),
            'duplicate_timer': self.TRACE.replace(timer, timer + timer),
            'duplicate_key': self.TRACE + 'INTERACTIVE_UI_NATIVE_KEY=5|research-tree|27|1|0\n',
            'old_dispatch_timer': timer + self.TRACE.replace(timer, ''),
        }
        for name, trace in cases.items():
            with self.subTest(name=name), self.assertRaises(RuntimeError):
                native_tree_escape_timer(trace, 5, 0)


if __name__ == '__main__':
    unittest.main()
