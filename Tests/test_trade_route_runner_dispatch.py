import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest


PROJECT = Path(__file__).resolve().parents[1]
RUNNER_PATH = PROJECT / 'tools' / 'run_interactive_game.py'
sys.path.insert(0, str(RUNNER_PATH.parent))
spec = importlib.util.spec_from_file_location('run_interactive_game', RUNNER_PATH)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class TradeRouteRunnerDispatchTests(unittest.TestCase):
    def setUp(self):
        self.lines = [
            'INTERACTIVE_TRADE_ROUTE_ACTION=1|InternationalTradeRoutes|2251799813685254|40|50',
            'INTERACTIVE_TRADE_ROUTE_ACTION=2|FromGPT|81|41|51',
            'INTERACTIVE_TRADE_ROUTE_INPUT=2|81|0|1|1|1|STATE_UNCHANGED',
            'INTERACTIVE_TRADE_ROUTE_ACTION=3|FromGPT|82|42|52',
            'INTERACTIVE_TRADE_ROUTE_INPUT=2|82|0|1|1|1|STATE_UNCHANGED',
            'INTERACTIVE_TRADE_ROUTE_ACTION=4|TabButtonAvailableTR|18|43|53',
            'INTERACTIVE_TRADE_ROUTE_INPUT=2|18|0|1|1|1|STATE_UNCHANGED',
            'INTERACTIVE_TRADE_ROUTE_WHEEL=44|126|-120',
            'INTERACTIVE_TRADE_ROUTE_INPUT=4|126|48|1|1|1|STATE_UNCHANGED',
            'INTERACTIVE_TRADE_ROUTE_ACTION=6|TabButtonTRWithYou|23|45|55',
            'INTERACTIVE_TRADE_ROUTE_INPUT=2|23|0|1|1|1|STATE_UNCHANGED',
            'INTERACTIVE_TRADE_ROUTE_ACTION=7|TabButtonYourTR|13|46|56',
            'INTERACTIVE_TRADE_ROUTE_INPUT=2|13|0|1|1|1|STATE_UNCHANGED',
            'INTERACTIVE_TRADE_ROUTE_ACTION=8|KEY_RETURN|13|47|57',
            'INTERACTIVE_TRADE_ROUTE_INPUT=1|13|0|1|1|1|STATE_UNCHANGED',
            'INTERACTIVE_TRADE_ROUTE_ACTION=9|CloseButton|133|48|58',
            'INTERACTIVE_TRADE_ROUTE_INPUT=2|133|0|1|0|0|STATE_UNCHANGED',
            'INTERACTIVE_TRADE_ROUTE_ACTION=10|InternationalTradeRoutes|2251799813685254|49|59',
            'INTERACTIVE_TRADE_ROUTE_ACTION=11|KEY_ESCAPE|27|50|60',
            'INTERACTIVE_TRADE_ROUTE_INPUT=1|27|0|1|0|0|STATE_UNCHANGED',
        ]

    def verify(self):
        return runner.verify_trade_route_dispatch_timeline('\n'.join(self.lines))

    def replace_line(self, prefix, replacement):
        index = next(i for i, line in enumerate(self.lines) if line.startswith(prefix))
        self.lines[index] = replacement

    def test_correct_dispatch_timeline_is_accepted(self):
        self.assertEqual((True, None), self.verify())

    def test_each_tab_dispatch_must_match_its_posted_control_key(self):
        for target, wrong_key in (
                ('TabButtonAvailableTR', 81), ('TabButtonTRWithYou', 106), ('TabButtonYourTR', 66)):
            with self.subTest(target=target):
                lines = self.lines[:]
                stage = {'TabButtonAvailableTR': '4', 'TabButtonTRWithYou': '6', 'TabButtonYourTR': '7'}[target]
                action_index = next(i for i, line in enumerate(lines)
                                    if line.startswith(f'INTERACTIVE_TRADE_ROUTE_ACTION={stage}|'))
                input_index = action_index + 1
                kind, _, delta, consumed, active, timer, suffix = lines[input_index].split('|')
                lines[input_index] = f'{kind}|{wrong_key}|{delta}|{consumed}|{active}|{timer}|{suffix}'
                ok, reason = runner.verify_trade_route_dispatch_timeline('\n'.join(lines))
                self.assertFalse(ok)
                self.assertIn('dispatch', reason)

    def test_wrong_kind_or_wheel_delta_is_rejected(self):
        cases = [
            ('INTERACTIVE_TRADE_ROUTE_INPUT=2|18|0|1|1|1|STATE_UNCHANGED',
             'INTERACTIVE_TRADE_ROUTE_INPUT=1|18|0|1|1|1|STATE_UNCHANGED'),
            ('INTERACTIVE_TRADE_ROUTE_INPUT=4|126|48|1|1|1|STATE_UNCHANGED',
             'INTERACTIVE_TRADE_ROUTE_INPUT=4|126|-48|1|1|1|STATE_UNCHANGED'),
            ('INTERACTIVE_TRADE_ROUTE_INPUT=4|126|48|1|1|1|STATE_UNCHANGED',
             'INTERACTIVE_TRADE_ROUTE_INPUT=2|126|48|1|1|1|STATE_UNCHANGED'),
        ]
        for original, changed in cases:
            with self.subTest(changed=changed):
                self.replace_line(original, changed)
                self.assertFalse(self.verify()[0])
                self.setUp()

    def test_missing_or_extra_dispatch_is_rejected(self):
        self.lines.pop(next(i for i, line in enumerate(self.lines)
                            if line.startswith('INTERACTIVE_TRADE_ROUTE_INPUT=4|')))
        self.assertFalse(self.verify()[0])
        self.setUp()
        self.lines.append('INTERACTIVE_TRADE_ROUTE_INPUT=2|81|0|1|0|0|STATE_UNCHANGED')
        self.assertFalse(self.verify()[0])

    def test_return_and_close_lifecycle_must_match_modal_state(self):
        self.replace_line('INTERACTIVE_TRADE_ROUTE_INPUT=1|13|',
                          'INTERACTIVE_TRADE_ROUTE_INPUT=1|13|0|1|0|0|STATE_UNCHANGED')
        self.assertFalse(self.verify()[0])
        self.setUp()
        self.replace_line('INTERACTIVE_TRADE_ROUTE_INPUT=2|133|',
                          'INTERACTIVE_TRADE_ROUTE_INPUT=2|133|0|1|1|1|STATE_UNCHANGED')
        self.assertFalse(self.verify()[0])

    def verify_resume_source(self, lines, dispatch_flag=True):
        with tempfile.TemporaryDirectory(dir=PROJECT) as directory:
            stdout = Path(directory) / 'stdout.log'
            stdout.write_text('\n'.join(lines), encoding='utf-8')
            result = {'trade_route_requested': True, 'stdout': {'path': str(stdout)}}
            if dispatch_flag is not None:
                result['trade_route_dispatch_verified'] = dispatch_flag
            runner.verify_trade_route_resume_source(result)

    def test_resume_source_rejects_missing_dispatch_flag(self):
        with self.assertRaisesRegex(RuntimeError, 'current runner'):
            self.verify_resume_source(self.lines, dispatch_flag=None)

    def test_resume_source_rejects_false_dispatch_flag(self):
        with self.assertRaisesRegex(RuntimeError, 'current runner'):
            self.verify_resume_source(self.lines, dispatch_flag=False)

    def test_resume_source_rejects_raw_stdout_misroute(self):
        misrouted = self.lines[:]
        self.replace_line('INTERACTIVE_TRADE_ROUTE_INPUT=2|18|',
                          'INTERACTIVE_TRADE_ROUTE_INPUT=2|81|0|1|1|1|STATE_UNCHANGED')
        with self.assertRaisesRegex(RuntimeError, 'stdout failed dispatch revalidation'):
            self.verify_resume_source(self.lines)
        self.lines = misrouted

    def test_resume_source_accepts_verified_dispatch_and_matching_stdout(self):
        self.verify_resume_source(self.lines)

    def verify_ui_support_source(self, lines, *, requested=True, sequence=True, dispatch=True):
        with tempfile.TemporaryDirectory(dir=PROJECT) as directory:
            stdout = Path(directory) / 'stdout.log'
            stdout.write_text('\n'.join(lines), encoding='utf-8')
            result = {'status': 'CONTINUOUS_INTERACTIVE_SDK_TREE_DECISION_UI_SMOKE_PASS',
                      'trade_route_requested': requested,
                      'trade_route_sequence_verified': sequence,
                      'stdout': {'path': str(stdout)}}
            if dispatch is not None:
                result['trade_route_dispatch_verified'] = dispatch
            runner.verify_trade_route_ui_support_source(result)

    def test_ui_support_rejects_legacy_self_reported_trade_route_pass(self):
        # The old 161612 result reported a passing sequence but had no dispatch proof.
        with self.assertRaisesRegex(RuntimeError, 'lacks its requested, sequence, or dispatch proof'):
            self.verify_ui_support_source(self.lines, dispatch=None)

    def test_ui_support_rejects_missing_trade_route_request_or_sequence(self):
        for values in ({'requested': False}, {'sequence': False}):
            with self.subTest(values=values), self.assertRaisesRegex(
                    RuntimeError, 'lacks its requested, sequence, or dispatch proof'):
                self.verify_ui_support_source(self.lines, **values)

    def test_ui_support_rejects_false_dispatch_flag(self):
        with self.assertRaisesRegex(RuntimeError, 'lacks its requested, sequence, or dispatch proof'):
            self.verify_ui_support_source(self.lines, dispatch=False)

    def test_ui_support_rejects_flagged_but_misrouted_stdout(self):
        misrouted = self.lines[:]
        input_index = next(i for i, line in enumerate(misrouted)
                           if line.startswith('INTERACTIVE_TRADE_ROUTE_INPUT=2|18|'))
        misrouted[input_index] = 'INTERACTIVE_TRADE_ROUTE_INPUT=2|81|0|1|1|1|STATE_UNCHANGED'
        with self.assertRaisesRegex(RuntimeError, 'stdout failed dispatch revalidation'):
            self.verify_ui_support_source(misrouted)

    def test_ui_support_accepts_fresh_verified_trade_route_stdout(self):
        self.verify_ui_support_source(self.lines)


if __name__ == '__main__':
    unittest.main()
