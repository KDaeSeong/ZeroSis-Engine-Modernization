"""Check posted HWND input provenance for the original end-turn blocker HUD.

This only verifies dispatch/lifecycle. Original assets, captured SDK state,
pixels and save restoration need the separate native-run evidence review.
"""
from __future__ import annotations

import re

KEY_BASE = 1 << 52
TARGET = re.compile(r'^INTERACTIVE_ACTION_INFO_SMOKE_TARGET=([^|\r\n]+)\|(-?\d+)\|(-?\d+)\|(\d+)\|(\d+)\|(\d+)$', re.M)
INPUT = re.compile(r'^INTERACTIVE_ACTION_INFO_PANEL_INPUT=(\d+)\|([0-5])\|(\d+)\|(\d+)\|([01])\|([01])$', re.M)


def verify_action_info_panel_timeline(text: str, restored: bool = False,
                                    worker_build_profile: bool = False) -> tuple[bool, str | None]:
    # Only a caller that verified the complete worker/tree/unit-action/HUD
    # request may opt in. Worker-looking lines never expand the default profile.
    if type(worker_build_profile) is not bool:
        return False, 'Original HUD worker profile must be an explicit boolean'

    def rows(pattern: str, source: str = text):
        return list(re.finditer(pattern, source, re.M))

    targets = list(TARGET.finditer(text))
    prefix = ['unit-right', 'unit-left'] + ([] if restored else ['notification', 'research'])
    names = prefix + ['end-turn']
    worker_progress, worker_observed = [], []
    expected_turns = None
    if worker_build_profile:
        records = {}
        for name, count in (('GAME_STARTED', 4), ('WORKER_BUILD_FIXTURE', 6), ('WORKER_BUILD_TARGET', 6),
                            ('WORKER_BUILD_STARTED', 5), ('WORKER_BUILD_COMPLETED', 5),
                            ('WORKER_BUILD_PROGRESS', 6), ('WORKER_BUILD_OBSERVED', 9),
                            ('WORKER_BUILD_AWAITING_TURN', 8)):
            marker = 'INTERACTIVE_' + name + '='
            records[name] = rows('^' + marker + r'(-?\d+)' + r'\|(-?\d+)' * (count - 1) + '$')
            if len(records[name]) != len(rows('^' + marker)):
                return False, 'Original HUD worker evidence contains a malformed ' + name
        singles = ('GAME_STARTED', 'WORKER_BUILD_FIXTURE', 'WORKER_BUILD_TARGET',
                   'WORKER_BUILD_STARTED', 'WORKER_BUILD_COMPLETED')
        if any(len(records[name]) != 1 for name in singles):
            return False, 'Original HUD worker profile lacks its unique fixture/start/completion boundaries'
        start, fixture, build_target, started, finished = (records[name][0] for name in singles)
        initial_turn, worker_owner, width, height = map(int, start.groups())
        unit, plot, build, initial_progress, build_time, improvement = map(int, fixture.groups())
        target_values, started_values, finished_values = (tuple(map(int, row.groups())) for row in (build_target, started, finished))
        final_turn = finished_values[4]
        count = final_turn - initial_turn
        if (initial_turn < 0 or not 0 <= worker_owner < 64 or width <= 0 or height <= 0 or
                min(unit, plot, build, improvement) < 0 or plot >= width * height or initial_progress != 0 or
                not 1 <= count <= 32 or build_time <= 0 or target_values[:3] != (unit, plot, build) or
                target_values[3] < 0 or min(target_values[4:]) <= 0 or
                started_values[:3] != (unit, plot, build) or not 0 < started_values[3] < build_time or
                started_values[4] != -1 or finished_values[:4] != (unit, plot, build, improvement) or
                not start.end() < fixture.start() < build_target.start() < started.start()):
            return False, 'Original HUD worker identity or finite construction interval is inconsistent'
        names = prefix + ['end-turn'] * count
        expected_turns = [initial_turn] * len(prefix) + list(range(initial_turn, final_turn))
        worker_progress, worker_observed = records['WORKER_BUILD_PROGRESS'], records['WORKER_BUILD_OBSERVED']
        if len(worker_progress) != count or len(worker_observed) != count:
            return False, 'Original HUD worker turn count differs from its SDK progress observations'
        previous = started_values[3]
        awaiting_expected = []
        for offset, (progress, observed) in enumerate(zip(worker_progress, worker_observed)):
            values, observation = tuple(map(int, progress.groups())), tuple(map(int, observed.groups()))
            turn, _, _, _, amount, actual_improvement = values
            if (values[:4] != (initial_turn + offset + 1, unit, plot, build) or observation[:6] != values or
                    observation[6] < 0 or not observed.end() < progress.start() or
                    (offset and worker_progress[offset - 1].end() >= observed.start())):
                return False, 'Original HUD worker progress skipped, duplicated or reordered an SDK turn'
            if offset == count - 1:
                if (amount, actual_improvement, observation[7], observation[8]) != (0, improvement, -1, -1):
                    return False, 'Original HUD worker completion differs from its final SDK construction state'
            else:
                if actual_improvement != -1 or not 0 < amount < build_time or observation[7:] != (target_values[3], build):
                    return False, 'Original HUD worker continuation lost its same queued SDK build'
                if offset == 0 and amount == previous:
                    if observation[6] <= 0:
                        return False, 'Original HUD initial worker wait has no restored movement'
                    awaiting_expected.append((turn, unit, plot, build, amount, observation[6], observation[7], build))
                elif amount <= previous:
                    return False, 'Original HUD worker construction did not advance on its next turn'
            previous = amount
        awaiting = records['WORKER_BUILD_AWAITING_TURN']
        if ([tuple(map(int, row.groups())) for row in awaiting] != awaiting_expected or
                (awaiting and not worker_observed[0].end() < awaiting[0].start() < worker_progress[0].start()) or
                not worker_progress[-1].end() < finished.start()):
            return False, 'Original HUD worker first-turn wait or completion ordering is invalid'
        accepted = rows(r'^INTERACTIVE_END_TURN_ACCEPTED=(\d+)$')
        returned = rows(r'^INTERACTIVE_NEXT_HUMAN_TURN=(\d+)\|(\d+)$')
        if ([int(row[1]) for row in accepted] != list(range(initial_turn, final_turn)) or
                [int(row[1]) for row in returned] != list(range(initial_turn + 1, final_turn + 1)) or
                any(not 1 <= int(row[2]) <= 512 for row in returned) or
                len(accepted) != len(rows(r'^INTERACTIVE_END_TURN_ACCEPTED=')) or
                len(returned) != len(rows(r'^INTERACTIVE_NEXT_HUMAN_TURN='))):
            return False, 'Original HUD worker profile contains missing, extra or malformed SDK turn commands'
    complete = rows(r'^INTERACTIVE_ACTION_INFO_PANEL_SMOKE_COMPLETE=1$')
    if [r[1] for r in targets] != names or len(rows(r'^INTERACTIVE_ACTION_INFO_SMOKE_TARGET=')) != len(names):
        return False, 'Original HUD targets differ from the bounded fresh/restore scenario'
    if len(complete) != 1 or len(rows(r'^INTERACTIVE_ACTION_INFO_PANEL_SMOKE_COMPLETE=')) != 1 or complete[0].start() < targets[-1].end():
        return False, 'Original HUD sequence lacks its final completion boundary'
    if any(int(b[5]) <= int(a[5]) for a, b in zip(targets, targets[1:])):
        return False, 'Original HUD actions reused or reversed a native scene generation'
    if worker_build_profile and [int(r[6]) for r in targets] != expected_turns:
        return False, 'Original HUD targets differ from the exact contiguous SDK worker turns'
    if not worker_build_profile and len({int(r[6]) for r in targets}) != 1:
        return False, 'Original HUD input crossed its expected single human turn'
    if worker_build_profile and not started.end() < targets[len(prefix)].start() < finished.start() < complete[0].start():
        return False, 'Original HUD worker input escaped its fixture and completion boundaries'
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
        frames = rows(r'^INTERACTIVE_ACTION_INFO_PANEL_FRAME=(\d+)\|' + str(generation) + r'\|' + str(turn) + r'\|(\d+)\|(\d+)\|(\d+)\|[^\r\n]+$')
        if len(frames) != 1 or frames[0].end() > action.start():
            return False, f'{phase} did not use a published original HUD frame'
        if worker_build_profile and int(frames[0][2]) != worker_owner:
            return False, 'Original HUD worker target belongs to a different active owner'
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
            if worker_build_profile:
                progress, observed = worker_progress[i - len(prefix)], worker_observed[i - len(prefix)]
                return_end = action.end() + returned[0].end()
                if (not buttons[0].end() < posts[0].start() < accepted[0].start() < dispatch[0].start() < returned[0].start() or
                        not return_end < observed.start() < progress.start() < end):
                    return False, 'Original HUD worker turn lost its post/command/dispatch/result ordering'
                after = text[return_end:observed.start()]
                next_frames = rows(r'^INTERACTIVE_ACTION_INFO_PANEL_FRAME=\d+\|(\d+)\|' + str(turn + 1) +
                                   r'\|' + str(worker_owner) + r'\|(\d+)\|(\d+)\|[^\r\n]+$', after)
                if (len(next_frames) != 1 or int(next_frames[0][1]) <= generation or
                        next_frames[0].groups()[1:] != frames[0].groups()[2:]):
                    return False, 'Original HUD worker turn lacks its next published human-turn frame'
                next_generation, _, device = next_frames[0].groups()
                commits = rows(r'^INTERACTIVE_GPU_SCENE_COMMITTED=' + next_generation + r'\|' + device + '$', after)
                worlds = rows(r'^INTERACTIVE_WORLD_FRAME=\d+\|' + next_generation + r'\|' + str(turn + 1) +
                              r'\|\d+\|\d+\|' + device + r'\|\d+\|[01]\|\d+$', after)
                if (len(commits) != 1 or len(worlds) != 1 or
                        not commits[0].end() < worlds[0].start() < next_frames[0].start()):
                    return False, 'Original HUD worker observation lacks its matching committed world generation'
    parsed = list(INPUT.finditer(text))
    if len(parsed) != len(rows(r'^INTERACTIVE_ACTION_INFO_PANEL_INPUT=')):
        return False, 'Original HUD dispatch contains a malformed record'
    if [r.groups() for r in parsed if r[2] != '3'] != expected_inputs:
        return False, 'Original HUD dispatched extra or unrequested commands'
    return True, None
