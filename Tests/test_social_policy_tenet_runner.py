"""Synthetic posted-input contract tests for the original tenet runner timeline."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / 'tools'
sys.path.insert(0, str(TOOLS))

from social_policy_tenet_timeline import verify_social_policy_tenet_timeline
from run_interactive_game import verify_social_policy_dispatch_timeline


FRESH_NAMES = {
    1: 'CultureString', 2: 'TabButtonIdeologies', 3: 'IdeologyButton11', 4: 'TenetButton',
    5: 'TenetConfirmNo', 6: 'TenetCancelButton', 7: 'IdeologyButton11', 8: 'TenetButton',
    9: 'TenetConfirmYes', 10: 'IdeologyButton12', 11: 'TenetButton', 12: 'TenetConfirmYes',
    14: 'IdeologyButton13', 15: 'TenetButton', 16: 'TenetConfirmYes', 17: 'CloseButton',
    18: 'CultureString', 19: 'TabButtonIdeologies', 20: 'KEY_ESCAPE'}
RESTORE_STAGES = [1, 2, 17, 18, 19, 20]


def timeline(restored: bool = False) -> str:
    owner, turn, elapsed, ideology, free = 0, 7, 12, 2, 1
    stages = RESTORE_STAGES if restored else list(FRESH_NAMES)
    names = {stage: FRESH_NAMES[stage] for stage in stages}
    policy_ids = {9: 91, 12: 92, 16: 93}
    lines = ['INTERACTIVE_SMOKE_POSTED=44|77|1234|1',
             f'INTERACTIVE_SOCIAL_POLICY_TENET_FIXTURE={"RESTORED" if restored else "FRESH"}|{owner}|{turn}|{elapsed}|{ideology}|{free}']
    if not restored:
        lines.append(f'INTERACTIVE_SOCIAL_POLICY_TENET_CULTURE=0|240|240|{turn}')
    lines.append(f'INTERACTIVE_SOCIAL_POLICY_SHOWN={owner}|-1|-1|{turn}|1')
    for i, stage in enumerate(stages, start=1):
        key = 27 if stage == 20 else 1000 + stage
        generation, revision = 200 + i, 500 + i
        payload = policy_ids.get(stage, -1)
        lines.append(f'INTERACTIVE_SOCIAL_POLICY_TENET_ACTION={stage}|{names[stage]}|{key}|{generation}|{revision}|{payload}')
        if stage != 20:
            lines.append(f'INTERACTIVE_SMOKE_POSTED={generation}|{key}|1234|1')
        if stage in policy_ids:
            lines.append(f'INTERACTIVE_SOCIAL_POLICY_COMMAND={owner}|{payload}|1|1|{turn}')
        if stage not in (1, 18):
            closing = stage in (17, 20)
            kind = 1 if stage == 20 else 2
            command = 1 if stage in policy_ids else 0
            timer = 0 if closing else 1
            modal = 0 if closing else 1
            lines.append(f'INTERACTIVE_SOCIAL_POLICY_INPUT={kind}|{key}|0|1|{timer}|{modal}|{turn}|{command}')
    lines.append(f'INTERACTIVE_SOCIAL_POLICY_SHOWN={owner}|-1|-1|{turn}|1')
    suffix = 'RESTORED_TENETS_UNCHANGED_AND_RETURN' if restored else 'THREE_TENETS_AND_RETURN'
    lines.append(f'INTERACTIVE_SOCIAL_POLICY_TENET_COMPLETE=900|{turn}|{suffix}')
    return '\n'.join(lines) + '\n'


class SocialPolicyTenetTimelineTests(unittest.TestCase):
    def test_exact_fresh_tenet_timeline_is_accepted(self) -> None:
        self.assertEqual((True, None), verify_social_policy_tenet_timeline(timeline()))

    def test_exact_restore_timeline_has_no_mutations(self) -> None:
        self.assertEqual((True, None), verify_social_policy_tenet_timeline(timeline(True)))

    def test_dispatch_wrapper_requires_requested_fixture_profile(self) -> None:
        fresh = timeline()
        self.assertEqual((True, None), verify_social_policy_dispatch_timeline(fresh, True))
        self.assertFalse(verify_social_policy_dispatch_timeline(fresh, False)[0])
        self.assertFalse(verify_social_policy_dispatch_timeline('INTERACTIVE_SOCIAL_POLICY_TENET_FIXTURE=FRESH|0|7|12|2|1\n', True)[0])

    def test_wrong_action_key_or_escape_kind_is_rejected(self) -> None:
        source = timeline().replace('=20|KEY_ESCAPE|27|219|519|-1', '=20|KEY_ESCAPE|13|219|519|-1')
        self.assertFalse(verify_social_policy_tenet_timeline(source)[0])
        source = timeline().replace('INPUT=1|27|0|1|0|0|7|0', 'INPUT=2|27|0|1|0|0|7|0')
        self.assertFalse(verify_social_policy_tenet_timeline(source)[0])

    def test_close_button_keeps_host_active_while_releasing_timer(self) -> None:
        source = timeline()
        source = source.replace('17|CloseButton|1017|216|516|-1', '17|CloseButton|318|216|516|-1')
        source = source.replace('INTERACTIVE_SMOKE_POSTED=216|1017|1234|1', 'INTERACTIVE_SMOKE_POSTED=216|318|376|598')
        source = source.replace('INPUT=2|1017|0|1|0|0|7|0', 'INPUT=2|318|0|1|0|0|7|0')
        self.assertEqual((True, None), verify_social_policy_tenet_timeline(source))

    def test_missing_extra_or_reordered_sdk_command_is_rejected(self) -> None:
        source = timeline().replace('INTERACTIVE_SOCIAL_POLICY_COMMAND=0|92|1|1|7\n', '')
        self.assertFalse(verify_social_policy_tenet_timeline(source)[0])
        source = timeline() + 'INTERACTIVE_SOCIAL_POLICY_COMMAND=0|94|1|1|7\n'
        self.assertFalse(verify_social_policy_tenet_timeline(source)[0])
        source = timeline().replace('INTERACTIVE_SOCIAL_POLICY_COMMAND=0|91|1|1|7\n', '')
        source = source.replace('INTERACTIVE_SOCIAL_POLICY_INPUT=2|1009|0|1|1|1|7|1\n',
                                'INTERACTIVE_SOCIAL_POLICY_INPUT=2|1009|0|1|1|1|7|1\nINTERACTIVE_SOCIAL_POLICY_COMMAND=0|91|1|1|7\n')
        self.assertFalse(verify_social_policy_tenet_timeline(source)[0])

    def test_wrong_payload_and_duplicate_tenet_ids_are_rejected(self) -> None:
        source = timeline().replace('COMMAND=0|92|1|1|7', 'COMMAND=0|999|1|1|7')
        self.assertFalse(verify_social_policy_tenet_timeline(source)[0])
        source = timeline().replace('12|TenetConfirmYes|1012|210|510|92', '12|TenetConfirmYes|1012|210|510|91')
        source = source.replace('COMMAND=0|92|1|1|7', 'COMMAND=0|91|1|1|7')
        self.assertFalse(verify_social_policy_tenet_timeline(source)[0])

    def test_wrong_culture_grant_lifecycle_and_restore_mutation_are_rejected(self) -> None:
        self.assertFalse(verify_social_policy_tenet_timeline(timeline().replace('=0|240|240|7', '=0|0|0|7'))[0])
        self.assertFalse(verify_social_policy_tenet_timeline(timeline().replace('INPUT=2|1009|0|1|1|1|7|1', 'INPUT=2|1009|0|0|0|0|7|1'))[0])
        restored = timeline(True) + 'INTERACTIVE_SOCIAL_POLICY_COMMAND=0|91|1|1|7\n'
        self.assertFalse(verify_social_policy_tenet_timeline(restored)[0])

    def test_missing_post_or_completion_and_wrong_stage_order_are_rejected(self) -> None:
        self.assertFalse(verify_social_policy_tenet_timeline(timeline().replace('INTERACTIVE_SMOKE_POSTED=209|1009|1234|1\n', ''))[0])
        self.assertFalse(verify_social_policy_tenet_timeline(timeline().replace('INTERACTIVE_SOCIAL_POLICY_TENET_ACTION=20|KEY_ESCAPE|27|219|519|-1\n',
            'INTERACTIVE_SOCIAL_POLICY_TENET_ACTION=20|KEY_ESCAPE|27|219|519|-1\nINTERACTIVE_SMOKE_POSTED=219|27|1234|1\n'))[0])
        self.assertFalse(verify_social_policy_tenet_timeline(timeline().replace('INTERACTIVE_SOCIAL_POLICY_TENET_COMPLETE=', 'BROKEN_COMPLETE='))[0])
        source = timeline().replace('INTERACTIVE_SOCIAL_POLICY_TENET_ACTION=14|IdeologyButton13', 'INTERACTIVE_SOCIAL_POLICY_TENET_ACTION=13|IdeologyButton13')
        self.assertFalse(verify_social_policy_tenet_timeline(source)[0])


if __name__ == '__main__':
    unittest.main()
