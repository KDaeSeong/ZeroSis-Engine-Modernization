"""Check posted HWND input provenance for the original end-turn blocker HUD.

This only verifies dispatch/lifecycle. Original assets, captured SDK state,
pixels and save restoration need the separate native-run evidence review.
"""
from __future__ import annotations

import re

KEY_BASE = 1 << 52
TARGET = re.compile(r'^INTERACTIVE_ACTION_INFO_SMOKE_TARGET=([^|\r\n]+)\|(-?\d+)\|(-?\d+)\|(\d+)\|(\d+)\|(\d+)$', re.M)
INPUT = re.compile(r'^INTERACTIVE_ACTION_INFO_PANEL_INPUT=(\d+)\|([0-5])\|(\d+)\|(\d+)\|([01])\|([01])$', re.M)


def verify_action_info_panel_timeline(text: str, restored: bool = False) -> tuple[bool, str | None]:
    def rows(pattern: str, source: str = text):
        return list(re.finditer(pattern, source, re.M))

    targets = list(TARGET.finditer(text))
    names = ['unit-right', 'unit-left'] + ([] if restored else ['notification', 'research']) + ['end-turn']
    complete = rows(r'^INTERACTIVE_ACTION_INFO_PANEL_SMOKE_COMPLETE=1$')
    if [r[1] for r in targets] != names or len(rows(r'^INTERACTIVE_ACTION_INFO_SMOKE_TARGET=')) != len(names):
        return False, 'Original HUD targets differ from the bounded fresh/restore scenario'
    if len(complete) != 1 or len(rows(r'^INTERACTIVE_ACTION_INFO_PANEL_SMOKE_COMPLETE=')) != 1 or complete[0].start() < targets[-1].end():
        return False, 'Original HUD sequence lacks its final completion boundary'
    if any(int(b[5]) <= int(a[5]) for a, b in zip(targets, targets[1:])):
        return False, 'Original HUD actions reused or reversed a native scene generation'
    if len({int(r[6]) for r in targets}) != 1:
        return False, 'Original HUD input crossed its expected single human turn'
    expected_inputs = []
    for i, action in enumerate(targets):
        phase, blocker, notification, key, generation, turn = action.groups()
        blocker, notification, key, generation, turn = map(int, (blocker, notification, key, generation, turn))
        if not KEY_BASE < key < KEY_BASE + (1 << 32):
            return False, 'Original HUD target escaped its exact private input namespace'
        if ((phase.startswith('unit-') and (blocker not in (3, 7, 8) or notification != -1)) or
                (phase == 'notification' and (blocker not in (1, 2) or notification < 0)) or
                (phase == 'research' and (blocker != 1 or notification < 0)) or
                (phase == 'end-turn' and (blocker != -1 or notification != -1))):
            return False, f'{phase} was posted against an incompatible SDK blocker'
        end = targets[i + 1].start() if i + 1 < len(targets) else complete[0].start()
        interval = text[action.end():end]
        kind = 5 if phase == 'unit-right' else 1
        expected = (str(generation), str(kind), str(key), str(key - KEY_BASE), '1', '0')
        expected_inputs.append(expected)
        dispatch = [r for r in INPUT.finditer(interval) if r[2] != '3']
        if [r.groups() for r in dispatch] != [expected]:
            return False, f'{phase} did not consume exactly its posted HWND key and generation'
        posts = rows(r'^INTERACTIVE_SMOKE_POSTED=' + str(generation) + r'\|' + str(key) + r'\|-?\d+\|-?\d+$', interval)
        buttons = rows(r'^INTERACTIVE_SMOKE_BUTTON=' + str(generation) + r'\|' + str(key) + r'\|' + str(kind) + r'\|0$', interval)
        if len(posts) != 1 or len(buttons) != 1 or posts[0].end() > dispatch[0].start():
            return False, f'{phase} has no unique preceding physical-button post'
        frames = rows(r'^INTERACTIVE_ACTION_INFO_PANEL_FRAME=(\d+)\|' + str(generation) + r'\|' + str(turn) + r'\|\d+\|\d+\|\d+\|[^\r\n]+$')
        if len(frames) != 1 or frames[0].end() > action.start():
            return False, f'{phase} did not use a published original HUD frame'
        if phase in ('unit-right', 'unit-left', 'notification'):
            verified = rows(r'^INTERACTIVE_ACTION_INFO_SMOKE_VERIFIED=' + phase + r'\|(\d+)\|' + str(turn) + r'$', interval)
            if len(verified) != 1 or int(verified[0][1]) <= generation or verified[0].start() < dispatch[0].end():
                return False, f'{phase} lacks its state-preserving post-input observation'
        if phase == 'notification':
            name = 'research' if blocker == 1 else 'production'
            opened = rows(r'^INTERACTIVE_ACTION_INFO_NOTIFICATION_OPENED=' + name + r'\|(\d+)\|' + str(turn) + r'$', interval)
            if len(opened) != 1 or int(opened[0][1]) <= generation or opened[0].start() > verified[0].start():
                return False, 'Actual notification did not open and return from its matching original popup'
        if phase == 'end-turn':
            accepted = rows(r'^INTERACTIVE_END_TURN_ACCEPTED=' + str(turn) + r'$', interval)
            returned = rows(r'^INTERACTIVE_NEXT_HUMAN_TURN=' + str(turn + 1) + r'\|\d+$', interval)
            if len(accepted) != 1 or len(returned) != 1 or not posts[0].end() < accepted[0].start() < returned[0].start():
                return False, 'Original HUD did not complete exactly one real SDK turn'
    parsed = list(INPUT.finditer(text))
    if len(parsed) != len(rows(r'^INTERACTIVE_ACTION_INFO_PANEL_INPUT=')):
        return False, 'Original HUD dispatch contains a malformed record'
    if [r.groups() for r in parsed if r[2] != '3'] != expected_inputs:
        return False, 'Original HUD dispatched extra or unrequested commands'
    return True, None
