from pathlib import Path
import json
import sys
import tempfile
import unittest

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / 'tools'))
import run_interactive_game as runner


def valid_timeline(restored=False):
    actions = [(1, 'CultureString', -1), (2, 'BranchButton0', 0), (3, 'No', -1),
               (4, 'BranchButton0', 0), (5, 'Yes', -1), (7, 'PolicyIcon', 7), (8, 'Yes', -1),
               (9, 'TabButtonIdeologies', -1), (10, 'TabButtonSocialPolicies', -1),
               (11, 'PolicyInfo', -1), (12, 'CloseButton', -1),
               (16, 'CultureString', -1), (17, 'KEY_ESCAPE', -1)]
    if restored:
        actions = [a for a in actions if a[0] in (1, 9, 10, 11, 12, 16, 17)]
    turn = 1 if restored else 0
    lines = ['INTERACTIVE_SOCIAL_POLICY_FIXTURE=RESTORED|0|1|1|3|50'] if restored else [
        'INTERACTIVE_SOCIAL_POLICY_CULTURE_FIXTURE=1|0|25|25|0',
        'INTERACTIVE_SOCIAL_POLICY_FIXTURE=FRESH|0|0|0|25|25']
    for n, (stage, name, payload) in enumerate(actions, 1):
        if stage == 7:
            lines.append('INTERACTIVE_SOCIAL_POLICY_CULTURE_FIXTURE=2|0|30|30|0')
        key = 27 if stage == 17 else 100 + n
        lines.append(f'INTERACTIVE_SOCIAL_POLICY_ACTION={stage}|{name}|{key}|{n}|{n}|{payload}')
        if stage != 17:
            lines.append(f'INTERACTIVE_SMOKE_POSTED={n}|{key}|555|444')
        if stage in (1, 16):
            lines.append(f'INTERACTIVE_SOCIAL_POLICY_SHOWN=0|1|0|{turn}|1')
        else:
            if stage in (5, 8):
                lines.append(f'INTERACTIVE_SOCIAL_POLICY_COMMAND=0|{0 if stage == 5 else 7}|{0 if stage == 5 else 1}|1|0')
            active = 0 if stage in (12, 17) else 1
            lines.append(f'INTERACTIVE_SOCIAL_POLICY_INPUT={1 if stage == 17 else 2}|{key}|0|1|{active}|{active}|{turn}|{int(stage in (5, 8))}')
    lines.append(f'INTERACTIVE_SOCIAL_POLICY_COMPLETE=15|{turn}|' +
                 ('RESTORED_POLICIES_UNCHANGED_AND_RETURN' if restored else 'TWO_PAID_ADOPTIONS_AND_RETURN'))
    return lines


class SocialPolicyRunnerTests(unittest.TestCase):
    def verify(self, lines):
        return runner.verify_social_policy_dispatch_timeline('\n'.join(lines))

    def test_branch_zero_is_a_real_selection(self):
        self.assertEqual((True, None), self.verify(valid_timeline()))

    def test_restore_observes_existing_policies_without_new_grants_or_commands(self):
        self.assertEqual((True, None), self.verify(valid_timeline(True)))
        for extra in ('INTERACTIVE_SOCIAL_POLICY_CULTURE_FIXTURE=2|0|50|50|1',
                      'INTERACTIVE_SOCIAL_POLICY_COMMAND=0|7|1|1|1'):
            with self.subTest(extra=extra):
                self.assertFalse(self.verify(valid_timeline(True) + [extra])[0])

    def test_missing_duplicate_and_reordered_inputs_are_rejected(self):
        lines = valid_timeline()
        first = next(i for i, line in enumerate(lines) if line.startswith('INTERACTIVE_SOCIAL_POLICY_INPUT='))
        second = next(i for i in range(first + 1, len(lines)) if lines[i].startswith('INTERACTIVE_SOCIAL_POLICY_INPUT='))
        for change in ('missing', 'duplicate', 'reordered'):
            altered = lines[:]
            if change == 'missing':
                altered.pop(first)
            elif change == 'duplicate':
                altered.insert(first, altered[first])
            else:
                altered[first], altered[second] = altered[second], altered[first]
            with self.subTest(change=change):
                self.assertFalse(self.verify(altered)[0])

    def test_wrong_key_zero_key_wrong_kind_and_unconsumed_input_are_rejected(self):
        for fields in ('2|0|0|1|1|1|0|0', '2|109|0|1|1|1|0|0', '1|102|0|1|1|1|0|0',
                       '2|102|0|0|1|1|0|0', '2|102|0|1|0|0|0|0'):
            lines = valid_timeline()
            index = next(i for i, line in enumerate(lines) if line.startswith('INTERACTIVE_SOCIAL_POLICY_INPUT='))
            lines[index] = 'INTERACTIVE_SOCIAL_POLICY_INPUT=' + fields
            with self.subTest(fields=fields):
                self.assertFalse(self.verify(lines)[0])

    def test_cancel_cannot_apply_a_policy(self):
        lines = valid_timeline()
        index = next(i for i, line in enumerate(lines) if line.startswith('INTERACTIVE_SOCIAL_POLICY_INPUT=2|103|'))
        lines[index] = lines[index][:-1] + '1'
        self.assertFalse(self.verify(lines)[0])

    def test_missing_wrong_or_extra_sdk_commands_are_rejected(self):
        for replacement in ('', 'INTERACTIVE_SOCIAL_POLICY_COMMAND=0|1|0|1|0',
                            'INTERACTIVE_SOCIAL_POLICY_COMMAND=1|0|0|1|0',
                            'INTERACTIVE_SOCIAL_POLICY_COMMAND=0|0|1|1|0'):
            lines = valid_timeline()
            index = next(i for i, line in enumerate(lines) if line.startswith('INTERACTIVE_SOCIAL_POLICY_COMMAND='))
            lines[index] = replacement
            self.assertFalse(self.verify(lines)[0])
        lines = valid_timeline() + ['INTERACTIVE_SOCIAL_POLICY_COMMAND=0|7|1|1|0']
        self.assertFalse(self.verify(lines)[0])

    def test_command_cannot_precede_confirmation(self):
        lines = valid_timeline()
        index = next(i for i, line in enumerate(lines) if line.startswith('INTERACTIVE_SOCIAL_POLICY_COMMAND='))
        lines.insert(0, lines.pop(index))
        self.assertFalse(self.verify(lines)[0])

    def test_missing_hwnd_post_and_reused_generation_are_rejected(self):
        lines = valid_timeline()
        lines.pop(next(i for i, line in enumerate(lines) if line.startswith('INTERACTIVE_SMOKE_POSTED=2|')))
        self.assertFalse(self.verify(lines)[0])
        lines = valid_timeline()
        index = next(i for i, line in enumerate(lines) if line.startswith('INTERACTIVE_SOCIAL_POLICY_ACTION=1|'))
        lines[index] = lines[index].replace('|1|1|-1', '|2|2|-1')
        self.assertFalse(self.verify(lines)[0])

    def test_resume_revalidates_pinned_stdout(self):
        with tempfile.TemporaryDirectory(dir=PROJECT) as directory:
            path = Path(directory) / 'stdout.log'
            path.write_text('\n'.join(valid_timeline()), encoding='utf8')
            result = {'social_policy_requested': True, 'social_policy_sequence_verified': True,
                      'social_policy_dispatch_verified': True,
                      'stdout': {'path': str(path), 'sha256': runner.digest(path)}}
            runner.verify_social_policy_resume_source(result)
            path.write_text('changed', encoding='utf8')
            with self.assertRaisesRegex(RuntimeError, 'pinned artifact'):
                runner.verify_social_policy_resume_source(result)

    def test_readonly_original_ini_and_resumed_options(self):
        with tempfile.TemporaryDirectory(dir=PROJECT) as directory:
            root = Path(directory)
            ini = root / 'UserSettings.ini'
            ini.write_text('[UserSettings]\nPolicyInfo = 1\n', encoding='utf8')
            original = ini.read_bytes()
            self.assertEqual(runner.read_policy_info_options(None, ini)['policy_info'], 1)
            checkpoint = root / 'game.zssave'
            checkpoint.write_bytes(b'opaque save')
            resume = {'checkpoint_source': {'path': str(checkpoint)}, 'run_id': 'test'}
            self.assertEqual(runner.read_policy_info_options(resume, ini)['policy_info'], 1)
            options = root / 'ui-options.json'
            options.write_text(json.dumps({'schema': 'ZEROSIS_UI_OPTIONS_V1', 'policyInfo': False}), encoding='utf8')
            value = runner.read_policy_info_options(resume, ini)
            self.assertEqual((value['policy_info'], value['origin']), (0, 'RESUMED_SESSION_UI_OPTIONS'))
            self.assertEqual(ini.read_bytes(), original)
            options.write_text(json.dumps({'schema': 'ZEROSIS_UI_OPTIONS_V1', 'policyInfo': 0}), encoding='utf8')
            with self.assertRaisesRegex(RuntimeError, 'invalid schema'):
                runner.read_policy_info_options(resume, ini)

    def test_ini_missing_ambiguous_or_invalid_option_is_rejected(self):
        with tempfile.TemporaryDirectory(dir=PROJECT) as directory:
            ini = Path(directory) / 'UserSettings.ini'
            for value in ('', 'PolicyInfo = 2\n', 'PolicyInfo = 1\nPolicyInfo = 0\n'):
                ini.write_text(value, encoding='utf8')
                with self.assertRaisesRegex(RuntimeError, 'exactly one'):
                    runner.read_policy_info_options(None, ini)


if __name__ == '__main__':
    unittest.main()
