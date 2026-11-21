import contextlib
import io
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import run_interactive_game as runner


class CurrentSdkPreparationOptionsTests(unittest.TestCase):
    def launchers(self, **options):
        return runner.build_interactive_launchers(
            python_ps='PYTHON_SENTINEL', driver_ps='DRIVER_SENTINEL', common_driver_args='',
            policy_info=1, default_checkpoint="''", worker_policy=runner.resolve_policy('0'), **options)

    def test_current_sdk_resume_launcher_cannot_open_a_save(self):
        play, resume = self.launchers(new_game_only=True)
        self.assertIn('--mode play --timeout 0', play)
        self.assertIn("throw 'Save loading is disabled", resume)
        for command in ('DRIVER_SENTINEL', 'PYTHON_SENTINEL', 'play-load', 'ShowDialog', '$Checkpoint'):
            self.assertNotIn(command, resume)

    def test_default_resume_launcher_retains_existing_load_mode(self):
        self.assertEqual(self.launchers(), self.launchers(new_game_only=False))
        self.assertIn('--mode play-load --checkpoint', self.launchers()[1])

    def reject_before_io(self, options):
        argv = ['run_interactive_game.py', '--host-build', 'unused-host.json', *options]
        with mock.patch.object(sys, 'argv', argv), \
                mock.patch.object(Path, 'read_text', side_effect=AssertionError('Unexpected input read')), \
                mock.patch.object(Path, 'mkdir', side_effect=AssertionError('Unexpected runtime allocation')), \
                mock.patch.object(runner.subprocess, 'Popen', side_effect=AssertionError('Unexpected process')), \
                contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
            runner.main()
        self.assertEqual(caught.exception.code, 2)

    def complete_options(self):
        return ['--runtime-sdk-build', 'unused-sdk.json', '--runtime-sdk-build-sha256', 'a' * 64,
                '--terrain-assets-from-run', '20261020T110323Z_27da680b90f1',
                '--policy-info-settings', 'unused-private.ini']

    def test_current_sdk_cannot_execute_smoke(self):
        self.reject_before_io([*self.complete_options(), '--smoke'])

    def test_current_sdk_cannot_resume_a_prior_bundle_save(self):
        self.reject_before_io([*self.complete_options(), '--resume-run', '20261020T110323Z_27da680b90f1'])

    def test_report_requires_an_explicit_report_digest(self):
        self.reject_before_io(['--runtime-sdk-build', 'unused-sdk.json'])

    def test_report_digest_requires_an_explicit_report(self):
        self.reject_before_io(['--runtime-sdk-build-sha256', 'a' * 64])

    def test_current_sdk_requires_sealed_terrain(self):
        self.reject_before_io(['--runtime-sdk-build', 'unused-sdk.json',
                              '--runtime-sdk-build-sha256', 'a' * 64,
                              '--policy-info-settings', 'unused-private.ini'])

    def test_current_sdk_requires_private_settings(self):
        self.reject_before_io(['--runtime-sdk-build', 'unused-sdk.json',
                              '--runtime-sdk-build-sha256', 'a' * 64,
                              '--terrain-assets-from-run', '20261020T110323Z_27da680b90f1'])

    def test_current_sdk_rejects_settings_outside_owned_project(self):
        options = self.complete_options()
        options[-1] = sys.executable
        with mock.patch.object(sys, 'argv', ['run_interactive_game.py', '--host-build', 'unused', *options]), \
                mock.patch.object(Path, 'read_text', side_effect=AssertionError('Unexpected input read')), \
                mock.patch.object(runner.subprocess, 'Popen', side_effect=AssertionError('Unexpected process')), \
                self.assertRaisesRegex(RuntimeError, 'owned private policy'):
            runner.main()


if __name__ == '__main__':
    unittest.main()
