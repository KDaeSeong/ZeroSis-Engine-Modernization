"""Negative dispatch-provenance tests; synthetic records are not gameplay proof."""
from pathlib import Path
import hashlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from action_info_panel_timeline import KEY_BASE, verify_action_info_panel_timeline
from run_interactive_game import verify_action_info_panel_resume_source


def fixture(restored=False):
    phases = [('unit-right', 3, -1), ('unit-left', 3, -1)]
    if not restored:
        phases += [('notification', 2, 7), ('research', 1, 8)]
    phases += [('end-turn', -1, -1)]
    lines = []
    for i, (phase, blocker, notification) in enumerate(phases):
        generation, key = 1 + i * 4, KEY_BASE + 2
        kind = 5 if phase == 'unit-right' else 1
        lines += [f'INTERACTIVE_ACTION_INFO_PANEL_FRAME={i+1}|{generation}|0|0|100|101|snapshot|folder',
                  f'INTERACTIVE_ACTION_INFO_SMOKE_TARGET={phase}|{blocker}|{notification}|{key}|{generation}|0',
                  f'INTERACTIVE_SMOKE_BUTTON={generation}|{key}|{kind}|0',
                  f'INTERACTIVE_SMOKE_POSTED={generation}|{key}|1600|860',
                  f'INTERACTIVE_ACTION_INFO_PANEL_INPUT={generation}|{kind}|{key}|2|1|0']
        if phase == 'notification':
            lines += [f'INTERACTIVE_ACTION_INFO_NOTIFICATION_OPENED=production|{generation+1}|0']
        if phase in ('unit-right', 'unit-left', 'notification'):
            lines += [f'INTERACTIVE_ACTION_INFO_SMOKE_VERIFIED={phase}|{generation+2}|0']
        if phase == 'end-turn':
            lines += ['INTERACTIVE_END_TURN_ACCEPTED=0', 'INTERACTIVE_NEXT_HUMAN_TURN=1|4']
    lines += ['INTERACTIVE_ACTION_INFO_PANEL_SMOKE_COMPLETE=1']
    return '\n'.join(lines) + '\n'


def worker_fixture(restored=False):
    """Synthetic six-turn worker evidence; not a substitute for a native run."""
    turn0 = 6 if restored else 0
    key = KEY_BASE + 2
    phases = [('unit-right', 3, -1), ('unit-left', 3, -1)]
    if not restored:
        phases += [('notification', 2, 7), ('research', 1, 8)]
    lines = [f'INTERACTIVE_GAME_STARTED={turn0}|0|40|24']
    for i, (phase, blocker, notification) in enumerate(phases):
        generation = 1 + i * 4
        kind = 5 if phase == 'unit-right' else 1
        lines += [f'INTERACTIVE_ACTION_INFO_PANEL_FRAME={i+1}|{generation}|{turn0}|0|100|101|snapshot|folder',
                  f'INTERACTIVE_ACTION_INFO_SMOKE_TARGET={phase}|{blocker}|{notification}|{key}|{generation}|{turn0}',
                  f'INTERACTIVE_SMOKE_BUTTON={generation}|{key}|{kind}|0',
                  f'INTERACTIVE_SMOKE_POSTED={generation}|{key}|1600|860',
                  f'INTERACTIVE_ACTION_INFO_PANEL_INPUT={generation}|{kind}|{key}|2|1|0']
        if phase == 'notification':
            lines += [f'INTERACTIVE_ACTION_INFO_NOTIFICATION_OPENED=production|{generation+1}|{turn0}']
        if phase in ('unit-right', 'unit-left', 'notification'):
            lines += [f'INTERACTIVE_ACTION_INFO_SMOKE_VERIFIED={phase}|{generation+2}|{turn0}']
    generation = len(phases) * 4 + 1
    lines += ['INTERACTIVE_WORKER_BUILD_FIXTURE=32770|571|2|0|700|3',
              f'INTERACTIVE_WORKER_BUILD_TARGET=32770|571|2|33|12|{generation}',
              'INTERACTIVE_WORKER_BUILD_STARTED=32770|571|2|200|-1']
    for offset, amount in enumerate((200, 300, 400, 500, 600, 0)):
        turn = turn0 + offset
        before, after = generation + 2 + offset * 6, generation + 4 + offset * 6
        final = offset == 5
        improvement, mission, mission_build = (3, -1, -1) if final else (-1, 33, 2)
        lines += [f'INTERACTIVE_ACTION_INFO_PANEL_FRAME={20+offset*2}|{before}|{turn}|0|100|101|snapshot|folder',
                  f'INTERACTIVE_ACTION_INFO_SMOKE_TARGET=end-turn|-1|-1|{key}|{before}|{turn}',
                  f'INTERACTIVE_SMOKE_BUTTON={before}|{key}|1|0',
                  f'INTERACTIVE_SMOKE_POSTED={before}|{key}|1600|860',
                  f'INTERACTIVE_END_TURN_ACCEPTED={turn}',
                  f'INTERACTIVE_ACTION_INFO_PANEL_INPUT={before}|1|{key}|2|1|0',
                  f'INTERACTIVE_NEXT_HUMAN_TURN={turn+1}|7',
                  f'INTERACTIVE_GPU_SCENE_COMMITTED={after}|101',
                  f'INTERACTIVE_WORLD_FRAME={after}|{after}|{turn+1}|3|26|101|54|0|1',
                  f'INTERACTIVE_ACTION_INFO_PANEL_FRAME={21+offset*2}|{after}|{turn+1}|0|100|101|snapshot|folder',
                  f'INTERACTIVE_WORKER_BUILD_OBSERVED={turn+1}|32770|571|2|{amount}|{improvement}|120|{mission}|{mission_build}']
        if offset == 0:
            lines += [f'INTERACTIVE_WORKER_BUILD_AWAITING_TURN={turn+1}|32770|571|2|200|120|33|2']
        lines += [f'INTERACTIVE_WORKER_BUILD_PROGRESS={turn+1}|32770|571|2|{amount}|{improvement}']
    lines += [f'INTERACTIVE_WORKER_BUILD_COMPLETED=32770|571|2|3|{turn0+6}',
              'INTERACTIVE_ACTION_INFO_PANEL_SMOKE_COMPLETE=1']
    return '\n'.join(lines) + '\n'


class WorkerTimeline(unittest.TestCase):
    def reject(self, text, restored=False):
        accepted, why = verify_action_info_panel_timeline(text, restored, worker_build_profile=True)
        self.assertFalse(accepted)
        self.assertIsInstance(why, str)

    def test_exact_fresh_and_restored_turns(self):
        for restored in (False, True):
            self.assertEqual(verify_action_info_panel_timeline(worker_fixture(restored), restored,
                                                              worker_build_profile=True), (True, None))

    def test_worker_requires_explicit_profile_and_full_records(self):
        self.assertFalse(verify_action_info_panel_timeline(worker_fixture())[0])
        self.reject(fixture())
        self.reject(worker_fixture(True))
        self.reject(worker_fixture(), True)
        for invalid in (None, 1, 'true'):
            self.assertFalse(verify_action_info_panel_timeline(worker_fixture(), worker_build_profile=invalid)[0])

    def test_missing_or_duplicate_worker_and_turn_evidence(self):
        text = worker_fixture()
        for marker in ('GAME_STARTED', 'WORKER_BUILD_FIXTURE', 'WORKER_BUILD_TARGET', 'WORKER_BUILD_STARTED',
                       'WORKER_BUILD_COMPLETED', 'WORKER_BUILD_OBSERVED', 'WORKER_BUILD_PROGRESS',
                       'WORKER_BUILD_AWAITING_TURN', 'END_TURN_ACCEPTED', 'NEXT_HUMAN_TURN',
                       'GPU_SCENE_COMMITTED', 'WORLD_FRAME'):
            line = next(value for value in text.splitlines() if value.startswith('INTERACTIVE_' + marker + '='))
            for replacement in ('', line + '\n' + line):
                with self.subTest(marker=marker, duplicate=bool(replacement)):
                    self.reject(text.replace(line, replacement, 1))

    def test_wrong_turn_count_identity_progress_and_generation(self):
        text = worker_fixture()
        changes = (
            ('COMPLETED=32770|571|2|3|6', 'COMPLETED=32770|571|2|3|5'),
            ('COMPLETED=32770|571|2|3|6', 'COMPLETED=32770|571|2|3|33'),
            ('NEXT_HUMAN_TURN=3|7', 'NEXT_HUMAN_TURN=4|7'),
            ('OBSERVED=2|32770|571', 'OBSERVED=2|32771|571'),
            ('PROGRESS=2|32770|571|2|300|-1', 'PROGRESS=2|32770|571|2|200|-1'),
            ('OBSERVED=6|32770|571|2|0|3|120|-1|-1', 'OBSERVED=6|32770|571|2|0|3|120|33|2'),
            ('GPU_SCENE_COMMITTED=21|101', 'GPU_SCENE_COMMITTED=19|101'),
            ('PANEL_FRAME=21|21|1|0|100|101', 'PANEL_FRAME=21|21|2|0|100|101'),
            ('PANEL_FRAME=21|21|1|0|100|101', 'PANEL_FRAME=21|21|1|1|100|101'),
            ('PANEL_FRAME=20|19|0|0|100|101', 'PANEL_FRAME=20|19|0|1|100|101'),
            ('PANEL_FRAME=21|21|1|0|100|101', 'PANEL_FRAME=21|21|1|0|102|101'),
        )
        for before, after in changes:
            with self.subTest(change=before):
                self.assertIn(before, text)
                self.reject(text.replace(before, after, 1))

    def test_missing_duplicate_or_reordered_end_turn_target(self):
        text = worker_fixture()
        line = next(value for value in text.splitlines() if 'SMOKE_TARGET=end-turn' in value)
        self.reject(text.replace(line, '', 1))
        self.reject(text.replace(line, line + '\n' + line, 1))
        other = next(value for value in text.splitlines() if 'SMOKE_TARGET=end-turn' in value and value != line)
        self.reject(text.replace(line, 'SWAP', 1).replace(other, line, 1).replace('SWAP', other, 1))

    def test_result_order_and_extra_or_malformed_sdk_commands(self):
        text = worker_fixture()
        accepted = 'INTERACTIVE_END_TURN_ACCEPTED=0'
        dispatched = f'INTERACTIVE_ACTION_INFO_PANEL_INPUT=19|1|{KEY_BASE+2}|2|1|0'
        self.reject(text.replace(accepted + '\n' + dispatched, dispatched + '\n' + accepted, 1))
        for line in ('INTERACTIVE_END_TURN_ACCEPTED=6', 'INTERACTIVE_NEXT_HUMAN_TURN=7|7',
                     'INTERACTIVE_WORKER_BUILD_PROGRESS=garbage', 'INTERACTIVE_END_TURN_ACCEPTED=bad'):
            with self.subTest(extra=line):
                self.reject(text + line + '\n')


class ReuseSource(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.log = Path(self.directory.name) / 'stdout.log'

    def source(self, restored=False, text=None):
        self.log.write_text(fixture(restored) if text is None else text, encoding='utf8')
        return {'status': 'CONTINUOUS_INTERACTIVE_SDK_TREE_DECISION_UI_' +
                         ('RESTORE_SMOKE_PASS' if restored else 'SMOKE_PASS'),
                'action_info_panel_requested': True,
                'action_info_panel_dispatch_verified': True,
                'action_info_panel_sequence_verified': True,
                'stdout': {'path': str(self.log),
                           'sha256': hashlib.sha256(self.log.read_bytes()).hexdigest()}}

    def test_fresh_and_restored_artifacts(self):
        for restored in (False, True):
            verify_action_info_panel_resume_source(self.source(restored))

    def test_changed_pinned_log_rejected(self):
        result = self.source()
        self.log.write_text(fixture(True), encoding='utf8')
        with self.assertRaisesRegex(RuntimeError, 'pinned artifact'):
            verify_action_info_panel_resume_source(result)

    def test_claimed_pass_cannot_hide_missing_real_inputs(self):
        result = self.source(text=fixture().replace('INTERACTIVE_SMOKE_POSTED=', 'IGNORED='))
        with self.assertRaisesRegex(RuntimeError, 'dispatch validation failed'):
            verify_action_info_panel_resume_source(result)

    def test_restored_sequence_cannot_claim_fresh_proof(self):
        result = self.source(text=fixture(True))
        with self.assertRaisesRegex(RuntimeError, 'dispatch validation failed'):
            verify_action_info_panel_resume_source(result)

    def test_missing_pass_or_invalid_profile_rejected(self):
        for key, value in (('action_info_panel_requested', 'true'),
                           ('action_info_panel_sequence_verified', False),
                           ('action_info_panel_dispatch_verified', 1)):
            result = self.source()
            result[key] = value
            with self.assertRaises(RuntimeError):
                verify_action_info_panel_resume_source(result)


class Timeline(unittest.TestCase):
    def reject(self, text, restored=False):
        accepted, why = verify_action_info_panel_timeline(text, restored)
        self.assertFalse(accepted)
        self.assertIsInstance(why, str)

    def test_fresh_and_restore_profiles(self):
        self.assertEqual(verify_action_info_panel_timeline(fixture()), (True, None))
        self.assertEqual(verify_action_info_panel_timeline(fixture(True), True), (True, None))

    def test_restore_may_not_claim_fresh_notifications(self):
        self.reject(fixture(True))
        self.reject(fixture(), True)

    def test_duplicate_command(self):
        text = fixture()
        line = next(s for s in text.splitlines() if s.startswith('INTERACTIVE_ACTION_INFO_PANEL_INPUT='))
        self.reject(text.replace(line, line + '\n' + line))

    def test_stale_generation(self):
        self.reject(fixture().replace('INTERACTIVE_ACTION_INFO_PANEL_INPUT=1|5', 'INTERACTIVE_ACTION_INFO_PANEL_INPUT=0|5'))

    def test_different_local_key(self):
        self.reject(fixture().replace('|2|1|0\n', '|3|1|0\n', 1))

    def test_right_click_became_left(self):
        self.reject(fixture().replace('INTERACTIVE_ACTION_INFO_PANEL_INPUT=1|5', 'INTERACTIVE_ACTION_INFO_PANEL_INPUT=1|1'))

    def test_missing_actual_post(self):
        self.reject('\n'.join(s for s in fixture().splitlines() if not s.startswith('INTERACTIVE_SMOKE_POSTED=1|')))

    def test_input_not_consumed(self):
        self.reject(fixture().replace('|2|1|0\n', '|2|0|0\n', 1))

    def test_endturn_still_blocked(self):
        self.reject(fixture().replace('SMOKE_TARGET=end-turn|-1|-1|', 'SMOKE_TARGET=end-turn|3|-1|'))

    def test_wrong_notification_popup(self):
        self.reject(fixture().replace('NOTIFICATION_OPENED=production', 'NOTIFICATION_OPENED=research'))

    def test_only_completion_marker(self):
        self.reject('INTERACTIVE_ACTION_INFO_PANEL_SMOKE_COMPLETE=1\n')

    def test_unrequested_late_command(self):
        self.reject(fixture() + f'INTERACTIVE_ACTION_INFO_PANEL_INPUT=100|1|{KEY_BASE+2}|2|1|0\n')

    def test_malformed_dispatch(self):
        self.reject(fixture() + 'INTERACTIVE_ACTION_INFO_PANEL_INPUT=garbage\n')

    def test_unpublished_target(self):
        self.reject(fixture().replace('PANEL_FRAME=1|1|0|', 'PANEL_FRAME=1|2|0|'))


if __name__ == '__main__':
    unittest.main()
