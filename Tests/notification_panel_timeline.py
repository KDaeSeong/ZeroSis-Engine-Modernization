"""Synthetic contract mutations, not native gameplay or SDK-state evidence."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from notification_panel_timeline import (KEY_BASE, MANDATORY_DISMISS_REJECTION,
                                         unexpected_input_rejection_lines, verify_notification_panel_timeline)
from verify_interactive_decisions import verify_decision_input_profile, verify_native_failure_markers
from test_game_menu_timeline import fixture as game_menu_fixture


def frame(generation, context='notification', turn=3):
    lines = [f'INTERACTIVE_GPU_WORLD_COMMITTED={generation}|99',
             f'INTERACTIVE_GPU_SCENE_COMMITTED={generation}|99',
             f'INTERACTIVE_WORLD_FRAME={generation}|{generation}|{turn}|2|10|99|4|0|1']
    if context == 'notification':
        lines.append(f'INTERACTIVE_NOTIFICATION_PANEL_FRAME={generation*3}|{generation}|{turn}|0|88|99|C:\\fixture\\s{generation}.json|C:\\fixture\\p{generation}')
    else:
        lines.append(f'INTERACTIVE_UI_FRAME={generation*3}|{generation}|{turn}|{context}|88|99|C:\\fixture\\s{generation}.json|C:\\fixture\\p{generation}')
    return lines


def post(generation, key, kind=1):
    return [f'INTERACTIVE_SMOKE_BUTTON={generation}|{key}|{kind}|0',
            f'INTERACTIVE_SMOKE_POSTED={generation}|{key}|1800|750']


def fixture(restored=False):
    lines = frame(1)
    # A world-hover key intentionally reaches the notification VM as key zero.
    lines += ['INTERACTIVE_NOTIFICATION_INPUT=3|0|0|0|3|0|0',
              'INTERACTIVE_NOTIFICATION_PANEL_INPUT=1|3|42|0|0']
    if restored:
        lines += frame(2, turn=4)
        lines += ['INTERACTIVE_NOTIFICATION_PANEL_SMOKE_COMPLETE=RESTORED_SDK_LIST_PRESENTATION']
        return '\n'.join(lines) + '\n'
    open_key, dismiss_key = KEY_BASE + 7, KEY_BASE + 8
    lines += [f'INTERACTIVE_NOTIFICATION_SMOKE_TARGET=open|17|{open_key}|1|3']
    lines += post(1, open_key)
    lines += ['INTERACTIVE_NOTIFICATION_INPUT=2|7|1|0|3|1|0',
              f'INTERACTIVE_NOTIFICATION_PANEL_INPUT=1|1|{open_key}|7|1']
    lines += frame(2, 'production')
    lines += ['INTERACTIVE_NOTIFICATION_POPUP_OPENED=17|production|2|3',
              'INTERACTIVE_UI_NATIVE_INPUT=2|0|0|1',
              'INTERACTIVE_UI_NATIVE_KEY=2|production|27|1|0']
    lines += frame(3)
    lines += ['INTERACTIVE_NOTIFICATION_OPEN_VERIFIED=17|3|3|STATE_UNCHANGED',
              f'INTERACTIVE_NOTIFICATION_SMOKE_TARGET=dismiss-blocked|17|{dismiss_key}|3|3']
    lines += post(3, dismiss_key, 5)
    lines += ['INTERACTIVE_NOTIFICATION_INPUT=5|8|1|0|3|1|0',
              f'INTERACTIVE_NOTIFICATION_PANEL_INPUT=3|5|{dismiss_key}|8|0']
    lines += frame(4)
    lines += ['INTERACTIVE_NOTIFICATION_DISMISS_BLOCKED=17|4|3|STATE_UNCHANGED']
    # Unrelated world posts in the full smoke are outside the notification route.
    lines += post(4, 45)
    lines += frame(5, 'production')
    lines += ['INTERACTIVE_DECISION_PRODUCTION_TARGET=4|6|9'] + post(5, 9)
    lines += ['INTERACTIVE_UI_NATIVE_INPUT=5|1|9|1']
    lines += frame(7)
    lines += ['INTERACTIVE_OWNED_CITY_SEQUENCE_VERIFIED=4|6',
              'INTERACTIVE_NOTIFICATION_REMOVED_VERIFIED=17|7|3']
    lines += frame(8, turn=4)
    lines += ['INTERACTIVE_NOTIFICATION_PANEL_SMOKE_COMPLETE=FRESH_INPUT_AND_SDK_REMOVAL']
    return '\n'.join(lines) + '\n'


class NotificationTimelineTests(unittest.TestCase):
    def reject(self, text, restored=False):
        passed, reason = verify_notification_panel_timeline(text, restored=restored)
        self.assertFalse(passed)
        self.assertIsInstance(reason, str)
        self.assertTrue(reason)

    def test_fresh_and_restore_scopes(self):
        for restored in (False, True):
            self.assertEqual(verify_notification_panel_timeline(fixture(restored), restored=restored), (True, None))
        self.assertEqual(verify_notification_panel_timeline(fixture().replace('\n', '\r\n')), (True, None))
        self.reject(fixture(), True)
        self.reject(fixture(True))

    def test_only_completion_or_frames_cannot_prove_input(self):
        self.reject('INTERACTIVE_NOTIFICATION_PANEL_SMOKE_COMPLETE=FRESH_INPUT_AND_SDK_REMOVAL\n')
        self.reject(fixture(True).replace('RESTORED_SDK_LIST_PRESENTATION', 'FRESH_INPUT_AND_SDK_REMOVAL'))

    def test_duplicate_or_malformed_notification_record(self):
        source = fixture()
        for line in source.splitlines():
            if line.startswith('INTERACTIVE_NOTIFICATION_'):
                with self.subTest(duplicate=line.split('=')[0]):
                    self.reject(source.replace(line, line + '\n' + line, 1))
        for suffix in ('INTERACTIVE_NOTIFICATION_PANEL_INPUT=bad',
                       'INTERACTIVE_NOTIFICATION_OTHER=1',
                       'INTERACTIVE_NOTIFICATION_REQUEST_REJECTED=0|3|17|EXPIRED_SDK_NOTIFICATION'):
            with self.subTest(record=suffix):
                self.reject(source + suffix + '\n')

    def test_gpu_publication_is_required(self):
        source = fixture()
        for prefix in ('INTERACTIVE_GPU_WORLD_COMMITTED=1|', 'INTERACTIVE_GPU_SCENE_COMMITTED=2|',
                       'INTERACTIVE_WORLD_FRAME=3|', 'INTERACTIVE_NOTIFICATION_PANEL_FRAME=12|'):
            with self.subTest(missing=prefix):
                self.reject('\n'.join(line for line in source.splitlines() if not line.startswith(prefix)))
        for old, new in [('INTERACTIVE_GPU_SCENE_COMMITTED=1|99', 'INTERACTIVE_GPU_SCENE_COMMITTED=1|98'),
                         ('INTERACTIVE_NOTIFICATION_PANEL_FRAME=9|3|3|0|88', 'INTERACTIVE_NOTIFICATION_PANEL_FRAME=9|3|3|0|89'),
                         ('INTERACTIVE_WORLD_FRAME=2|2|3|2|10|99', 'INTERACTIVE_WORLD_FRAME=2|2|4|2|10|99')]:
            with self.subTest(change=old):
                self.reject(source.replace(old, new))
        commit = 'INTERACTIVE_GPU_SCENE_COMMITTED=1|99'
        self.reject(source.replace(commit, commit + '\n' + commit))

    def test_physical_post_precedes_callback(self):
        source = fixture()
        key = KEY_BASE + 7
        button = f'INTERACTIVE_SMOKE_BUTTON=1|{key}|1|0'
        posted = f'INTERACTIVE_SMOKE_POSTED=1|{key}|1800|750'
        for line in (button, posted):
            self.reject(source.replace(line + '\n', '', 1))
            self.reject(source.replace(line, line + '\n' + line, 1))
        self.reject(source.replace(button, button.replace('|1|0', '|5|0')))
        self.reject(source.replace(posted + '\n', '', 1) + posted + '\n')

    def test_wrong_id_namespace_local_key_owner_turn_or_result(self):
        source = fixture()
        mutations = [
            ('SMOKE_TARGET=dismiss-blocked|17|', 'SMOKE_TARGET=dismiss-blocked|18|'),
            ('POPUP_OPENED=17|', 'POPUP_OPENED=18|'),
            ('REMOVED_VERIFIED=17|', 'REMOVED_VERIFIED=18|'),
            (f'PANEL_INPUT=1|1|{KEY_BASE+7}|7|1', f'PANEL_INPUT=1|1|{KEY_BASE+7}|8|1'),
            (f'PANEL_INPUT=1|1|{KEY_BASE+7}', f'PANEL_INPUT=2|1|{KEY_BASE+7}'),
            ('INPUT=2|7|1|0|3|1|0', 'INPUT=2|7|1|1|3|1|0'),
            ('INPUT=2|7|1|0|3|1|0', 'INPUT=2|7|1|0|4|1|0'),
            ('INPUT=2|7|1|0|3|1|0', 'INPUT=2|7|1|0|3|2|0'),
            ('INPUT=2|7|1|0|3|1|0', 'INPUT=2|7|1|0|3|1|1'),
            (f'PANEL_INPUT=3|5|{KEY_BASE+8}|8|0', f'PANEL_INPUT=3|5|{KEY_BASE+8}|8|1'),
            ('DISMISS_BLOCKED=17|4|3', 'DISMISS_BLOCKED=17|4|4'),
        ]
        for old, new in mutations:
            with self.subTest(change=old):
                self.assertIn(old, source)
                self.reject(source.replace(old, new, 1))
        self.reject(source.replace(str(KEY_BASE+7), str((1 << 51)+7)))

    def test_original_popup_and_escape_required(self):
        source = fixture()
        for old, new in [('POPUP_OPENED=17|production', 'POPUP_OPENED=17|research'),
                         ('NATIVE_KEY=2|production|27|1|0', 'NATIVE_KEY=2|production|27|1|1'),
                         ('NATIVE_INPUT=2|0|0|1', 'NATIVE_INPUT=2|1|9|1')]:
            with self.subTest(change=old):
                self.reject(source.replace(old, new))
        escaped = 'INTERACTIVE_UI_NATIVE_KEY=2|production|27|1|0'
        self.reject(source.replace(escaped + '\n', ''))
        self.reject(source.replace(escaped + '\n', '') + escaped + '\n')

    def test_real_production_input_precedes_removal(self):
        source = fixture()
        for prefix in ('INTERACTIVE_DECISION_PRODUCTION_TARGET=', 'INTERACTIVE_SMOKE_POSTED=5|',
                       'INTERACTIVE_UI_NATIVE_INPUT=5|', 'INTERACTIVE_OWNED_CITY_SEQUENCE_VERIFIED='):
            with self.subTest(missing=prefix):
                self.reject('\n'.join(line for line in source.splitlines() if not line.startswith(prefix)))
        self.reject(source.replace('CITY_SEQUENCE_VERIFIED=4|6', 'CITY_SEQUENCE_VERIFIED=5|6'))
        marker = 'INTERACTIVE_NOTIFICATION_REMOVED_VERIFIED=17|7|3'
        self.reject(marker + '\n' + source.replace(marker + '\n', ''))

    def test_pointer_motion_cannot_queue_commands(self):
        source = fixture()
        self.reject(source.replace('INPUT=3|0|0|0|3|0|0', 'INPUT=3|0|0|0|3|1|0'))
        self.reject(source.replace('PANEL_INPUT=1|3|42|0|0', 'PANEL_INPUT=1|3|42|2|0'))

    def test_restore_cannot_hide_input(self):
        source = fixture(True)
        marker = 'INTERACTIVE_NOTIFICATION_PANEL_SMOKE_COMPLETE='
        for extra in post(1, KEY_BASE+7):
            self.reject(source.replace(marker, extra + '\n' + marker), True)
        self.reject(source.replace('INPUT=3|0|0|0|3|0|0', 'INPUT=2|7|1|0|3|1|0'), True)


class MandatoryDismissRejectionTests(unittest.TestCase):
    @staticmethod
    def log():
        inner = 'INTERACTIVE_NOTIFICATION_INPUT=5|8|1|0|3|1|0\n'
        return fixture().replace(inner, inner + MANDATORY_DISMISS_REJECTION + '\n')

    def test_exact_completed_fresh_callback_exception(self):
        text = self.log()
        self.assertEqual(verify_notification_panel_timeline(text), (True, None))
        self.assertEqual(unexpected_input_rejection_lines(text, notification_panel_requested=True), [])
        self.assertEqual(unexpected_input_rejection_lines(text.replace('\n', '\r\n'), notification_panel_requested=True), [])
        self.assertEqual(unexpected_input_rejection_lines(fixture()), [])

    def test_no_exception_for_profile_off_or_restore(self):
        self.assertEqual(unexpected_input_rejection_lines(self.log()), [MANDATORY_DISMISS_REJECTION])
        self.assertEqual(unexpected_input_rejection_lines(self.log(), notification_panel_requested=True, restored=True),
                         [MANDATORY_DISMISS_REJECTION])
        text = fixture(True) + MANDATORY_DISMISS_REJECTION + '\n'
        self.assertEqual(unexpected_input_rejection_lines(text, notification_panel_requested=True, restored=True),
                         [MANDATORY_DISMISS_REJECTION])

    def test_duplicate_extra_different_and_damaged_messages_fail(self):
        for extra in (MANDATORY_DISMISS_REJECTION, 'INTERACTIVE_INPUT_REJECTED=unrelated failure'):
            text = self.log() + extra + '\n'
            with self.subTest(extra=extra):
                self.assertEqual(unexpected_input_rejection_lines(text, notification_panel_requested=True),
                                 [MANDATORY_DISMISS_REJECTION, extra])
        for message in ('INTERACTIVE_INPUT_REJECTED=unrelated failure',
                        MANDATORY_DISMISS_REJECTION + ' ',
                        MANDATORY_DISMISS_REJECTION.encode('utf-8').decode('cp1252', errors='replace'),
                        'prefix ' + MANDATORY_DISMISS_REJECTION,
                        'INTERACTIVE_INPUT_REJECTED malformed'):
            with self.subTest(message=message):
                text = self.log().replace(MANDATORY_DISMISS_REJECTION, message)
                self.assertEqual(unexpected_input_rejection_lines(text, notification_panel_requested=True), [message])

    def test_exact_message_outside_its_callback_fails(self):
        text = fixture()
        for marker in ('INTERACTIVE_NOTIFICATION_INPUT=5|8|1|0|3|1|0',
                       'INTERACTIVE_NOTIFICATION_INPUT=2|7|1|0|3|1|0',
                       'INTERACTIVE_NOTIFICATION_DISMISS_BLOCKED=',
                       'INTERACTIVE_NOTIFICATION_PANEL_SMOKE_COMPLETE='):
            with self.subTest(location=marker):
                moved = text.replace(marker, MANDATORY_DISMISS_REJECTION + '\n' + marker)
                self.assertEqual(verify_notification_panel_timeline(moved), (True, None))
                self.assertEqual(unexpected_input_rejection_lines(moved, notification_panel_requested=True),
                                 [MANDATORY_DISMISS_REJECTION])

    def test_broken_id_owner_turn_generation_or_commit_keeps_rejection(self):
        for old, new in (
                ('SMOKE_TARGET=dismiss-blocked|17|', 'SMOKE_TARGET=dismiss-blocked|18|'),
                ('INPUT=5|8|1|0|3|1|0', 'INPUT=5|8|1|1|3|1|0'),
                ('INPUT=5|8|1|0|3|1|0', 'INPUT=5|8|1|0|4|1|0'),
                (f'PANEL_INPUT=3|5|{KEY_BASE+8}', f'PANEL_INPUT=4|5|{KEY_BASE+8}'),
                ('INTERACTIVE_GPU_SCENE_COMMITTED=3|99', 'IGNORED_GPU_COMMIT=3|99'),
                ('INTERACTIVE_NOTIFICATION_REMOVED_VERIFIED=17|7|3\n', ''),
                ('INTERACTIVE_NOTIFICATION_PANEL_SMOKE_COMPLETE=FRESH_INPUT_AND_SDK_REMOVAL\n', '')):
            with self.subTest(change=old):
                changed = self.log().replace(old, new)
                self.assertFalse(verify_notification_panel_timeline(changed)[0])
                self.assertEqual(unexpected_input_rejection_lines(changed, notification_panel_requested=True),
                                 [MANDATORY_DISMISS_REJECTION])


class NativeFailureMarkerBoundaryTests(unittest.TestCase):
    def test_completed_fresh_and_legacy_without_rejections(self):
        verify_native_failure_markers(MandatoryDismissRejectionTests.log(), 'UI_WINDOW_PROCESS_START=88\n',
                                      notification_panel_requested=True)
        verify_native_failure_markers(fixture(), '')
        verify_native_failure_markers(fixture(True), '', notification_panel_requested=True, restored=True)

    def test_request_off_and_restore_keep_the_rejection(self):
        for requested, restored in ((False, False), (True, True)):
            with self.subTest(requested=requested, restored=restored):
                with self.assertRaisesRegex(RuntimeError, 'Unexpected native-input rejection'):
                    verify_native_failure_markers(MandatoryDismissRejectionTests.log(), '',
                                                  notification_panel_requested=requested, restored=restored)

    def test_stderr_and_cross_stream_duplicates_are_never_exempt(self):
        good = MandatoryDismissRejectionTests.log()
        for stdout, stderr in (('', good), (fixture(), MANDATORY_DISMISS_REJECTION),
                               (good, MANDATORY_DISMISS_REJECTION),
                               (good, 'INTERACTIVE_INPUT_REJECTED=unrelated failure')):
            with self.subTest(stdout_has_expected=MANDATORY_DISMISS_REJECTION in stdout, stderr=stderr):
                with self.assertRaisesRegex(RuntimeError, 'Unexpected native-input rejection'):
                    verify_native_failure_markers(stdout, stderr, notification_panel_requested=True)

    def test_duplicate_additional_and_changed_stdout_rejections_fail(self):
        good = MandatoryDismissRejectionTests.log()
        for text in (good + MANDATORY_DISMISS_REJECTION + '\n',
                     good + 'INTERACTIVE_INPUT_REJECTED=unrelated failure\n',
                     good.replace(MANDATORY_DISMISS_REJECTION, MANDATORY_DISMISS_REJECTION + ' ')):
            with self.subTest(text=text):
                with self.assertRaisesRegex(RuntimeError, 'Unexpected native-input rejection'):
                    verify_native_failure_markers(text, '', notification_panel_requested=True)

    def test_expected_rejection_does_not_mask_fatal_markers(self):
        good = MandatoryDismissRejectionTests.log()
        for marker in ('HOST_FAILURE', 'HOST_NATIVE_EXCEPTION', 'HOST_CLEANUP_PENDING', 'SCRIPT_FAILURE'):
            for stdout, stderr in ((good + marker, ''), (good, marker)):
                with self.subTest(marker=marker, stderr=bool(stderr)):
                    with self.assertRaisesRegex(RuntimeError, 'Host or script failure marker'):
                        verify_native_failure_markers(stdout, stderr, notification_panel_requested=True)

    def test_stale_generation_keeps_exact_rejection_fatal(self):
        text = MandatoryDismissRejectionTests.log().replace(
            f'PANEL_INPUT=3|5|{KEY_BASE+8}', f'PANEL_INPUT=4|5|{KEY_BASE+8}')
        with self.assertRaisesRegex(RuntimeError, 'Unexpected native-input rejection'):
            verify_native_failure_markers(text, '', notification_panel_requested=True)


class DecisionInputProfileBoundaryTests(unittest.TestCase):
    @staticmethod
    def records(menu=False):
        request = {'input_profile': ('POSTED_HWND_ORIGINAL_GAME_MENU_SMOKE' if menu else
                                     'POSTED_HWND_CONTINUOUS_TREE_DECISION_UI_LOOP'),
                   'smoke': True, 'decisions': True, 'research_tree': True,
                   'stage_or_mods_changed': False, 'game_menu_smoke': menu}
        result = {'decision_ui_smoke_requested': True, 'research_tree_requested': True,
                  'research_tree_sequence_verified': True, 'game_menu_requested': menu,
                  'game_menu_dispatch_verified': menu, 'game_menu_sequence_verified': menu,
                  'game_menu_state_equal': menu}
        return request, result

    def test_existing_tree_and_exact_menu_profiles(self):
        for menu in (False, True):
            request, result = self.records(menu)
            with self.subTest(menu=menu):
                verify_decision_input_profile(request, result, game_menu_fixture() if menu else '',
                                              research_tree=True)

    def test_modified_or_other_profile_is_rejected(self):
        for profile in ('POSTED_HWND_ORIGINAL_GAME_MENU_SMOKE ', 'POSTED_HWND_ORIGINAL_TRADE_ROUTE_OVERVIEW_SMOKE'):
            request, result = self.records(True)
            request['input_profile'] = profile
            with self.subTest(profile=profile):
                with self.assertRaisesRegex(RuntimeError, 'isolated decision-UI profile'):
                    verify_decision_input_profile(request, result, game_menu_fixture(), research_tree=True)

    def test_tree_profile_cannot_disguise_menu_flags_or_timeline(self):
        for changed in ('request', 'result', 'timeline'):
            request, result = self.records()
            if changed == 'request':
                request['game_menu_smoke'] = True
            elif changed == 'result':
                result['game_menu_requested'] = True
            with self.subTest(changed=changed):
                with self.assertRaisesRegex(RuntimeError, 'explicit original-menu profile'):
                    verify_decision_input_profile(request, result, game_menu_fixture() if changed == 'timeline' else '',
                                                  research_tree=True)

    def test_menu_flag_mismatch_or_incomplete_timeline_is_rejected(self):
        for side, key in (('request', 'smoke'), ('request', 'decisions'), ('request', 'research_tree'),
                          ('request', 'game_menu_smoke'), ('result', 'decision_ui_smoke_requested'),
                          ('result', 'research_tree_requested'), ('result', 'research_tree_sequence_verified'),
                          ('result', 'game_menu_requested'), ('result', 'game_menu_dispatch_verified'),
                          ('result', 'game_menu_sequence_verified'), ('result', 'game_menu_state_equal')):
            for value in (False, 1):
                request, result = self.records(True)
                (request if side == 'request' else result)[key] = value
                with self.subTest(side=side, key=key, value=value):
                    with self.assertRaises(RuntimeError):
                        verify_decision_input_profile(request, result, game_menu_fixture(), research_tree=True)
        request, result = self.records(True)
        incomplete = '\n'.join(line for line in game_menu_fixture().splitlines()
                               if not line.startswith('INTERACTIVE_GAME_MENU_SMOKE_COMPLETE='))
        with self.assertRaisesRegex(RuntimeError, 'Original GameMenu timeline is invalid'):
            verify_decision_input_profile(request, result, incomplete, research_tree=True)


if __name__ == '__main__':
    unittest.main()
