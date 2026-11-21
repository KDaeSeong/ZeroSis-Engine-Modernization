"""Strict posted-input timeline verifier for the original BNW tenet popup path."""
from __future__ import annotations

import re


FIXTURE = re.compile(
    r'^INTERACTIVE_SOCIAL_POLICY_TENET_FIXTURE=(FRESH|RESTORED)\|(\d+)\|(\d+)\|(\d+)\|(-?\d+)\|(\d+)$', re.M)
ACTION = re.compile(
    r'^INTERACTIVE_SOCIAL_POLICY_TENET_ACTION=(\d+)\|([^|]+)\|(\d+)\|(\d+)\|(\d+)\|(-?\d+)$', re.M)
INPUT = re.compile(
    r'^INTERACTIVE_SOCIAL_POLICY_INPUT=(\d+)\|(\d+)\|(-?\d+(?:\.\d+)?)\|([01])\|([01])\|([01])\|(\d+)\|([01])$', re.M)
COMMAND = re.compile(r'^INTERACTIVE_SOCIAL_POLICY_COMMAND=(\d+)\|(\d+)\|([01])\|([01])\|(\d+)$', re.M)
SHOWN = re.compile(r'^INTERACTIVE_SOCIAL_POLICY_SHOWN=(\d+)\|(-?\d+)\|(-?\d+)\|(\d+)\|1$', re.M)

FRESH_STAGES = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 14, 15, 16, 17, 18, 19, 20]
RESTORE_STAGES = [1, 2, 17, 18, 19, 20]


def verify_social_policy_tenet_timeline(text: str) -> tuple[bool, str | None]:
    """Validate the exact fresh tenet/cost/cancel path or read-only restore path."""
    fixtures = list(FIXTURE.finditer(text))
    if len(fixtures) != 1:
        return False, 'Tenet profile requires exactly one fresh or restored fixture marker'
    fixture = fixtures[0]
    restored = fixture[1] == 'RESTORED'
    owner, turn, elapsed, ideology, initial_free = map(int, fixture.group(2, 3, 4, 5, 6))
    if owner < 0 or turn < 0 or elapsed < 0 or ideology < 0 or initial_free < 0:
        return False, 'Tenet fixture contains an invalid owner, clock, ideology, or free-tenet count'

    grant_lines = re.findall(r'^INTERACTIVE_SOCIAL_POLICY_TENET_CULTURE=([^\r\n]*)$', text, re.M)
    if restored:
        if grant_lines:
            return False, 'Restored tenet profile must not grant culture'
    else:
        if len(grant_lines) != 1:
            return False, 'Fresh tenet profile requires exactly one paid-culture fixture record'
        match = re.fullmatch(r'(\d+)\|(\d+)\|(\d+)\|(\d+)', grant_lines[0])
        if not match or tuple(map(int, match.groups())) != (0, int(match[2]), int(match[2]), turn) or int(match[2]) <= 0:
            return False, 'Fresh tenet culture fixture must record 0|positiveGrant|samePositiveAfter|fixtureTurn'

    actions = list(ACTION.finditer(text))
    expected_stages = RESTORE_STAGES if restored else FRESH_STAGES
    if [int(row[1]) for row in actions] != expected_stages:
        return False, 'Tenet actions differ from the exact fresh or restored stage sequence'
    rows = {int(row[1]): row for row in actions}
    expected_names = {
        1: 'CultureString', 2: 'TabButtonIdeologies', 3: 'IdeologyButton11', 4: 'TenetButton',
        5: 'TenetConfirmNo', 6: 'TenetCancelButton', 7: 'IdeologyButton11', 8: 'TenetButton',
        9: 'TenetConfirmYes', 10: 'IdeologyButton12', 11: 'TenetButton', 12: 'TenetConfirmYes',
        14: 'IdeologyButton13', 15: 'TenetButton', 16: 'TenetConfirmYes', 17: 'CloseButton',
        18: 'CultureString', 19: 'TabButtonIdeologies', 20: 'KEY_ESCAPE'}
    if [row[2] for row in actions] != [expected_names[stage] for stage in expected_stages]:
        return False, 'Tenet controls differ from original IdeologyButton, chooser, confirm, and return targets'
    if not restored and any(int(rows[stage][6]) < 0 for stage in (9, 12, 16)):
        return False, 'Each confirmed tenet must report its selected nonnegative SDK policy ID'
    if not restored and len({int(rows[stage][6]) for stage in (9, 12, 16)}) != 3:
        return False, 'Fresh tenet profile must adopt three distinct policy IDs'
    if restored and any(int(row[6]) != -1 for row in actions):
        return False, 'Restored tenet actions must not claim a selected policy mutation'
    if any(int(row[3]) <= 0 for row in actions) or int(rows[20][3]) != 27:
        return False, 'Tenet action has an invalid posted key or Escape virtual key'
    if any(int(b[4]) <= int(a[4]) or int(b[5]) <= int(a[5]) for a, b in zip(actions, actions[1:])):
        return False, 'Tenet actions reuse or reverse scene generations/revisions'

    posted = list(re.finditer(r'^INTERACTIVE_SMOKE_POSTED=(\d+)\|(\d+)\|\d+\|\d+$', text, re.M))
    for index, action in enumerate(actions):
        boundary = actions[index + 1].start() if index + 1 < len(actions) else len(text)
        matching_posts = [post for post in posted if action.start() < post.start() < boundary and
                          (post[1], post[2]) == (action[4], action[3])]
        if int(action[1]) == 20:
            if matching_posts:
                return False, 'Escape stage must use its original WM_KEYDOWN route without an HWND post record'
        elif len(matching_posts) != 1:
            return False, f'Tenet stage {action[1]} requires one matching HWND post inside its action interval'

    inputs = list(INPUT.finditer(text))
    inner_stages = [stage for stage in expected_stages if stage not in (1, 18)]
    if len(inputs) != len(inner_stages):
        return False, 'Tenet native input count differs from the exact fresh or restored sequence'
    for stage, event in zip(inner_stages, inputs):
        action = rows[stage]
        escape = stage == 20
        closing = stage in (17, 20)
        wanted = (1 if escape else 2, int(action[3]), 0.0, 1,
                  0 if closing else 1, 0 if closing else 1, turn,
                  1 if (not restored and stage in (9, 12, 16)) else 0)
        actual = (int(event[1]), int(event[2]), float(event[3]), *map(int, event.group(4, 5, 6, 7, 8)))
        next_action = next((row.start() for row in actions if row.start() > action.start()), len(text))
        if actual != wanted or not action.start() < event.start() < next_action:
            return False, f'Tenet stage {stage} has the wrong key kind, modal lifecycle, or command count'

    commands = list(COMMAND.finditer(text))
    selected = [int(rows[stage][6]) for stage in (9, 12, 16)] if not restored else []
    expected_commands = [(policy, 1, 1, turn) for policy in selected]
    if [tuple(map(int, row.group(2, 3, 4, 5))) for row in commands] != expected_commands:
        return False, 'Tenet SDK commands must match exactly the three confirmed policy=true adoptions'
    if any(int(row[1]) != owner for row in commands):
        return False, 'Tenet SDK command owner differs from the fixture owner'
    for stage, command in zip((9, 12, 16), commands):
        event = inputs[inner_stages.index(stage)]
        action = rows[stage]
        if not action.start() < command.start() < event.start():
            return False, f'Tenet stage {stage} SDK mutation escaped its confirm-input interval'

    shown = list(SHOWN.finditer(text))
    suffix = 'RESTORED_TENETS_UNCHANGED_AND_RETURN' if restored else 'THREE_TENETS_AND_RETURN'
    complete = list(re.finditer(r'^INTERACTIVE_SOCIAL_POLICY_TENET_COMPLETE=(\d+)\|(\d+)\|' + suffix + r'$', text, re.M))
    shown_state_valid = len(shown) == 2 and shown[0].groups() == shown[1].groups() and all(
        int(row[1]) == owner and int(row[2]) == -1 and int(row[3]) == -1 and int(row[4]) == turn for row in shown)
    if not shown_state_valid or \
            len(complete) != 1 or int(complete[0][2]) != turn or \
            int(complete[0][1]) <= int(actions[-1][5]) or complete[0].start() < inputs[-1].start():
        return False, 'Tenet popup did not show, close, reopen, and complete with the fixture ideology state'
    return True, None
