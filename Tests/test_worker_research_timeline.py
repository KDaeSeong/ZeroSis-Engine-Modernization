"""Synthetic contract mutations only; these tests do not claim native gameplay."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import re
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from action_info_panel_timeline import KEY_BASE, verify_action_info_panel_timeline
from probe_world_builder import artifact
from verify_interactive_decisions import (verify_worker_research_integration,
                                           worker_research_contract_required,
                                           research_callback_source_pair, research_callback_targets,
                                           worker_policy_contract_required, verify_worker_policy_integration,
                                           worker_production_contract_required, verify_worker_production_integration,
                                           worker_unstack_contract_required)
from worker_research_timeline import (CAPABILITY, REQUEST_FLAGS, VERIFIER_FILES,
                                      exact_worker_research_profile, verify_worker_research_timeline,
                                      POLICY_CAPABILITY, verify_worker_policy_timeline, verify_worker_policy_inventory,
                                      PRODUCTION_CAPABILITY, verify_worker_production_timeline, UNSTACK_CAPABILITY)


def fixture(*, restored=False, complete=True, saturated=True, final_completion=False):
    """Three exact worker turns, optionally one natural award and a new choice."""
    t0 = 6 if restored else 0
    lines = [CAPABILITY, f'INTERACTIVE_GAME_STARTED={t0}|0|40|24']
    key = KEY_BASE + 2

    def hud(generation, turn):
        lines.append(f'INTERACTIVE_ACTION_INFO_PANEL_FRAME={generation}|{generation}|{turn}|0|100|101|snapshot|folder')

    def world(generation, turn, panel=True):
        lines.extend([f'INTERACTIVE_GPU_SCENE_COMMITTED={generation}|101',
                      f'INTERACTIVE_WORLD_FRAME={generation}|{generation}|{turn}|3|26|101|54|0|1'])
        if panel:
            hud(generation, turn)

    def target(phase, generation, turn, blocker=-1, notification=-1):
        lines.append(f'INTERACTIVE_ACTION_INFO_SMOKE_TARGET={phase}|{blocker}|{notification}|{key}|{generation}|{turn}')

    def post(generation, chosen, turn, context, before, after, marker, technology):
        world(generation, turn, False)
        lines.extend([f'INTERACTIVE_UI_SCENE_REQUEST={generation}|{context}|snapshot-{generation}|folder-{generation}',
                      f'INTERACTIVE_UI_FRAME={generation}|{generation}|{turn}|{context}|100|101|snapshot-{generation}|folder-{generation}',
                      marker, f'INTERACTIVE_SMOKE_BUTTON={generation}|{chosen}|1|0',
                      f'INTERACTIVE_SMOKE_POSTED={generation}|{chosen}|100|100',
                      f'UI_WINDOW_INPUT=1|2|{chosen}|1|44|44|{before}|{after}|{turn}|99'])
        if context == 'tech-award':
            lines.append(f'INTERACTIVE_TECH_AWARD_CLOSED={chosen}|{turn}|0|STATE_UNCHANGED')
        lines.append(f'INTERACTIVE_UI_NATIVE_INPUT={generation}|1|{chosen}|1')

    phases = [('unit-right', 3, -1), ('unit-left', 3, -1)]
    if not restored:
        phases += [('notification', 2, 7), ('research', 1, 8)]
    for index, (phase, blocker, notice) in enumerate(phases):
        generation, kind = 1 + index * 4, 5 if phase == 'unit-right' else 1
        hud(generation, t0); target(phase, generation, t0, blocker, notice)
        lines.extend([f'INTERACTIVE_SMOKE_BUTTON={generation}|{key}|{kind}|0',
                      f'INTERACTIVE_SMOKE_POSTED={generation}|{key}|1000|650',
                      f'INTERACTIVE_ACTION_INFO_PANEL_INPUT={generation}|{kind}|{key}|2|1|0'])
        if phase == 'notification':
            lines.append(f'INTERACTIVE_ACTION_INFO_NOTIFICATION_OPENED=production|{generation+1}|{t0}')
        if phase in ('unit-right', 'unit-left', 'notification'):
            lines.append(f'INTERACTIVE_ACTION_INFO_SMOKE_VERIFIED={phase}|{generation+2}|{t0}')
    progress = 36 if saturated else 0
    left = 0 if saturated else 35
    post(20, 700, t0, 'research-tree', 1, 1, 'INTERACTIVE_DECISION_RESEARCH_TARGET=2|700', 2)
    lines.append('INTERACTIVE_UI_NATIVE_KEY=21|research-tree|27|1|0')
    world(22, t0)
    lines.extend([f'INTERACTIVE_DECISION_BEFORE_TURN={t0},{t0},0,8192,0,2,1,0,106,{progress},{left},3',
                  f'INTERACTIVE_WORKER_RESEARCH_SELECTED={t0}|0|2|22|2|0|{progress}|{left}',
                  'INTERACTIVE_WORKER_BUILD_FIXTURE=32770|571|2|0|400|3',
                  'INTERACTIVE_WORKER_BUILD_TARGET=32770|571|2|33|12|23',
                  'INTERACTIVE_WORKER_BUILD_STARTED=32770|571|2|200|-1'])
    tech = 2
    for index, (before, returned) in enumerate(((24, 27), (32, 34), (36, 39))):
        turn = t0 + index
        hud(before, turn); target('end-turn', before, turn)
        lines.extend([f'INTERACTIVE_WORKER_RESEARCH_BEFORE_TURN={turn}|0|{tech}|{before}|0|{progress}|{left}',
                      f'INTERACTIVE_SMOKE_BUTTON={before}|{key}|1|0',
                      f'INTERACTIVE_SMOKE_POSTED={before}|{key}|1000|650',
                      f'INTERACTIVE_END_TURN_ACCEPTED={turn}',
                      f'INTERACTIVE_ACTION_INFO_PANEL_INPUT={before}|1|{key}|2|1|0'])
        completes = complete and index == (2 if final_completion else 0)
        if completes:
            lines.append(f'INTERACTIVE_UI_QUEUED=68|0|0|{tech}')
        lines.append(f'INTERACTIVE_NEXT_HUMAN_TURN={turn+1}|7')
        if completes:
            lines.append(f'INTERACTIVE_TECH_AWARD_SHOWN=0|0|{tech}|{turn+1}|1')
            post(returned - 1, 600, turn + 1, 'tech-award', 1, 0,
                 f'INTERACTIVE_WORKER_TECH_AWARD_TARGET={turn+1}|0|{tech}|600|{returned-1}|1', tech)
            left = 0
        else:
            progress += 6; left = max(0, left - 6)
        world(returned, turn + 1)
        if completes:
            lines.append(f'INTERACTIVE_WORKER_TECH_AWARD_RETURNED={turn+1}|0|{tech}|{returned}|-1|1|0')
        lines.append(f'INTERACTIVE_WORKER_RESEARCH_TURN_RETURNED={turn+1}|0|{tech}|{returned}|{-1 if completes else tech}|{int(completes)}|{progress}|{left}')
        if index == 0:
            lines.append(f'INTERACTIVE_DECISION_AFTER_TURN={turn+1},{turn+1},0,8192,0,2,1,9,106,{progress},{left},3')
        amount, improvement, mission, mission_build = (0, 3, -1, -1) if index == 2 else (200 + index * 100, -1, 33, 2)
        lines.append(f'INTERACTIVE_WORKER_BUILD_OBSERVED={turn+1}|32770|571|2|{amount}|{improvement}|120|{mission}|{mission_build}')
        if index == 0:
            lines.append(f'INTERACTIVE_WORKER_BUILD_AWAITING_TURN={turn+1}|32770|571|2|200|120|33|2')
        lines.append(f'INTERACTIVE_WORKER_BUILD_PROGRESS={turn+1}|32770|571|2|{amount}|{improvement}')
        if completes and index < 2:
            hud(28, turn + 1); target('research-continuation', 28, turn + 1, 1, 9)
            lines.extend([f'INTERACTIVE_SMOKE_BUTTON=28|{key}|1|0',
                          f'INTERACTIVE_SMOKE_POSTED=28|{key}|1000|650',
                          f'INTERACTIVE_ACTION_INFO_PANEL_INPUT=28|1|{key}|2|1|0'])
            tech, progress, left = 3, 0, 20
            post(29, 800, turn + 1, 'research', 0, 0,
                 f'INTERACTIVE_WORKER_RESEARCH_TARGET={turn+1}|0|3|800|29', tech)
            world(30, turn + 1)
            lines.append(f'INTERACTIVE_WORKER_RESEARCH_SELECTED={turn+1}|0|3|30|3|0|0|20')
    lines.extend([f'INTERACTIVE_WORKER_BUILD_COMPLETED=32770|571|2|3|{t0+3}',
                  'INTERACTIVE_ACTION_INFO_PANEL_SMOKE_COMPLETE=1'])
    return '\n'.join(lines) + '\n'


def policy_fixture(*, restored=False, cycle=True, complete=True):
    """Synthetic original-callback trace, including same-turn research/policy continuation."""
    text = fixture(restored=restored, complete=complete)
    if not cycle:
        return POLICY_CAPABILITY + '\n' + text + 'INTERACTIVE_WORKER_POLICY_COMPLETE=0\n'
    shifted = []
    fields = {'GPU_SCENE_COMMITTED': (0,), 'WORLD_FRAME': (0, 1), 'ACTION_INFO_PANEL_FRAME': (0, 1),
              'ACTION_INFO_SMOKE_TARGET': (4,), 'WORKER_RESEARCH_BEFORE_TURN': (3,),
              'SMOKE_BUTTON': (0,), 'SMOKE_POSTED': (0,), 'ACTION_INFO_PANEL_INPUT': (0,),
              'WORKER_RESEARCH_TURN_RETURNED': (3,)}
    for line in text.splitlines():
        marker, payload = line.split('=', 1)
        parts = payload.split('|')
        for index in fields.get(marker.removeprefix('INTERACTIVE_'), ()):
            if int(parts[index]) >= 32:
                parts[index] = str(int(parts[index]) + 10)
        shifted.append(marker + '=' + '|'.join(parts))
    text = '\n'.join(shifted) + '\n'
    turn, key = (7 if restored else 1), KEY_BASE + 2
    lines = []
    def world(generation, panel=False):
        lines.extend([f'INTERACTIVE_GPU_SCENE_COMMITTED={generation}|101',
                      f'INTERACTIVE_WORLD_FRAME={generation}|{generation}|{turn}|3|26|101|54|0|1'])
        if panel:
            lines.append(f'INTERACTIVE_ACTION_INFO_PANEL_FRAME={generation}|{generation}|{turn}|0|100|101|snapshot-{generation}|folder-{generation}')
    def state(phase, generation):
        lines.append(f'INTERACTIVE_WORKER_POLICY_WORKER_STATE=1|{phase}|{turn}|0|{generation}|32770|571|2|200|400|-1|3|33|2|120')
    lines.append('INTERACTIVE_UI_SCENE_REQUEST=31|action-info-panel|snapshot-31|folder-31')
    world(31, True)
    lines.extend([f'INTERACTIVE_WORKER_POLICY_BEGIN=1|{turn}|0|42|31|28|25|0',
                  'INTERACTIVE_WORKER_POLICY_INVENTORY=1|before|inventory-before'])
    state('before', 31)
    lines.extend([f'INTERACTIVE_ACTION_INFO_SMOKE_TARGET=policy-continuation|0|42|{key}|31|{turn}',
                  f'INTERACTIVE_SMOKE_BUTTON=31|{key}|1|0', f'INTERACTIVE_SMOKE_POSTED=31|{key}|1100|570',
                  f'INTERACTIVE_ACTION_INFO_INPUT=2|2|1|0|{turn}|1|0',
                  f'UI_WINDOW_INPUT=0|2|2|1|44|44|0|0|{turn}|99',
                  'INTERACTIVE_UI_QUEUED=17|0|-1|-1',
                  f'INTERACTIVE_SOCIAL_POLICY_SHOWN=0|0|-1|{turn}|1',
                  'INTERACTIVE_UI_OPENED=10|social-policy',
                  f'INTERACTIVE_ACTION_INFO_PANEL_INPUT=31|1|{key}|2|1|0'])
    for index, phase in enumerate(('branch', 'confirm', 'close')):
        generation, button = 32 + index, 900 + index
        lines.append(f'INTERACTIVE_UI_SCENE_REQUEST={generation}|social-policy|snapshot-{generation}|folder-{generation}')
        world(generation)
        lines.append(f'INTERACTIVE_UI_FRAME={generation}|{generation}|{turn}|social-policy|100|101|snapshot-{generation}|folder-{generation}')
        if phase == 'confirm':
            state('selected', generation)
        if phase == 'close':
            lines.extend([f'INTERACTIVE_WORKER_POLICY_ADOPTED=1|{turn}|0|0|0|28|25|3|{generation}',
                          'INTERACTIVE_WORKER_POLICY_INVENTORY=1|after|inventory-after'])
            state('adopted', generation)
        lines.extend([f'INTERACTIVE_WORKER_POLICY_TARGET=1|{phase}|0|0|{button}|{generation}|{generation}|{turn}|0',
                      f'INTERACTIVE_SMOKE_BUTTON={generation}|{button}|1|0',
                      f'INTERACTIVE_SMOKE_POSTED={generation}|{button}|100|100'])
        if phase == 'confirm':
            lines.append(f'INTERACTIVE_SOCIAL_POLICY_COMMAND=0|0|0|1|{turn}')
        active = int(phase != 'close')
        lines.extend([f'INTERACTIVE_SOCIAL_POLICY_INPUT=2|{button}|0|1|{active}|{active}|{turn}|{int(phase == "confirm")}',
                      f'UI_WINDOW_INPUT=3|2|{button}|1|44|{45 if phase == "confirm" else 44}|1|{active}|{turn}|99',
                      f'INTERACTIVE_UI_NATIVE_INPUT={generation}|1|{button}|1'])
    lines.append('INTERACTIVE_UI_SCENE_REQUEST=35|action-info-panel|snapshot-35|folder-35')
    world(35, True); state('returned', 35)
    lines.append(f'INTERACTIVE_WORKER_POLICY_RETURNED=1|{turn}|0|35|-1|-1|1|{3 if complete else 2}')
    anchor = 'INTERACTIVE_ACTION_INFO_PANEL_FRAME=42|'
    index = text.index(anchor)
    return POLICY_CAPABILITY + '\n' + text[:index] + '\n'.join(lines) + '\n' + text[index:] + 'INTERACTIVE_WORKER_POLICY_COMPLETE=1\n'


def production_fixture(*, restored=False, cycle=True, unstack=False):
    """Synthetic complete worker trace with a zero/one natural production cycle."""
    text = policy_fixture(restored=restored, cycle=False)
    t0 = 6 if restored else 0
    decision = next(line for line in text.splitlines() if line.startswith('INTERACTIVE_DECISION_BEFORE_TURN='))
    text = text.replace(decision, 'INTERACTIVE_DECISION_PRODUCTION_TARGET=8192|0|102\n' + decision +
        f'\nINTERACTIVE_WORKER_PRODUCTION_BASELINE={t0}|0|8192|0|1|0|106|22', 1)
    text = PRODUCTION_CAPABILITY + '\n' + text
    if not cycle:
        text += 'INTERACTIVE_WORKER_PRODUCTION_COMPLETE=0\n'
        return UNSTACK_CAPABILITY + '\n' + text + 'INTERACTIVE_WORKER_UNSTACK_COMPLETE=0\n' if unstack else text
    shifted = []
    fields = {'GPU_SCENE_COMMITTED': (0,), 'WORLD_FRAME': (0, 1), 'ACTION_INFO_PANEL_FRAME': (0, 1),
              'ACTION_INFO_SMOKE_TARGET': (4,), 'WORKER_RESEARCH_BEFORE_TURN': (3,),
              'SMOKE_BUTTON': (0,), 'SMOKE_POSTED': (0,), 'ACTION_INFO_PANEL_INPUT': (0,),
              'WORKER_RESEARCH_TURN_RETURNED': (3,)}
    for line in text.splitlines():
        marker, payload = line.split('=', 1); parts = payload.split('|')
        for index in fields.get(marker.removeprefix('INTERACTIVE_'), ()):
            if int(parts[index]) >= 36:
                parts[index] = str(int(parts[index]) + 10)
        shifted.append(marker + '=' + '|'.join(parts))
    text = '\n'.join(shifted) + '\n'
    turn, key = t0 + 2, KEY_BASE + 2
    anchor = f'INTERACTIVE_ACTION_INFO_PANEL_FRAME=32|32|{turn-1}|'
    index = text.index(anchor)
    text = text[:index] + f'INTERACTIVE_GPU_SCENE_COMMITTED=32|101\nINTERACTIVE_WORLD_FRAME=32|32|{turn-1}|3|26|101|54|0|1\n' + text[index:]
    observed = f'INTERACTIVE_WORKER_BUILD_OBSERVED={turn}|'
    index = text.index(observed)
    finish = [f'INTERACTIVE_WORKER_PRODUCTION_FINISHED=1|{turn}|0|8192|0|57349|34',
              'INTERACTIVE_WORKER_PRODUCTION_SCENES=1|production-before|production-after',
              f'INTERACTIVE_WORKER_PRODUCTION_QUEUE=1|last-turn|{turn-1}|0|8192|32|1|0|97|106',
              f'INTERACTIVE_WORKER_PRODUCTION_QUEUE=1|finished|{turn}|0|8192|34|0|-1|0|0']
    text = text[:index] + '\n'.join(finish) + '\n' + text[index:]
    lines = []
    def world(generation, panel=False):
        context = 'action-info-panel' if panel else 'production'
        lines.extend([f'INTERACTIVE_UI_SCENE_REQUEST={generation}|{context}|snapshot-{generation}|folder-{generation}',
                      f'INTERACTIVE_GPU_SCENE_COMMITTED={generation}|101',
                      f'INTERACTIVE_WORLD_FRAME={generation}|{generation}|{turn}|3|26|101|54|0|1'])
        if panel:
            lines.append(f'INTERACTIVE_ACTION_INFO_PANEL_FRAME={generation}|{generation}|{turn}|0|100|101|snapshot-{generation}|folder-{generation}')
        else:
            lines.append(f'INTERACTIVE_UI_FRAME={generation}|{generation}|{turn}|production|100|101|snapshot-{generation}|folder-{generation}')
    def state(phase, generation):
        lines.append(f'INTERACTIVE_WORKER_PRODUCTION_WORKER_STATE=1|{phase}|{turn}|0|{generation}|32770|571|2|300|400|-1|3|33|2|120')
    def queue(phase, generation, length=0, unit=-1, needed=0):
        lines.append(f'INTERACTIVE_WORKER_PRODUCTION_QUEUE=1|{phase}|{turn}|0|8192|{generation}|{length}|{unit}|0|{needed}')
    world(35, True)
    lines.append(f'INTERACTIVE_WORKER_PRODUCTION_BEGIN=1|{turn}|0|8192|42|35|3')
    queue('before', 35); state('before', 35)
    lines.extend([f'INTERACTIVE_ACTION_INFO_SMOKE_TARGET=production-continuation|2|42|{key}|35|{turn}',
                  f'INTERACTIVE_SMOKE_BUTTON=35|{key}|1|0', f'INTERACTIVE_SMOKE_POSTED=35|{key}|1100|570',
                  f'INTERACTIVE_ACTION_INFO_PANEL_INPUT=35|1|{key}|2|1|0'])
    world(36); queue('opened', 36); state('opened', 36)
    lines.extend([f'INTERACTIVE_WORKER_PRODUCTION_TARGET=1|{turn}|0|8192|1|900|36|36',
                  'INTERACTIVE_SMOKE_BUTTON=36|900|1|0', 'INTERACTIVE_SMOKE_POSTED=36|900|100|100',
                  f'UI_WINDOW_INPUT=4|2|900|1|44|44|0|0|{turn}|99',
                  'UI_PRODUCTION_WINDOW_GAMEPLAY=4|2|900|0|0|0', 'INTERACTIVE_UI_NATIVE_INPUT=36|1|900|1',
                  f'INTERACTIVE_WORKER_PRODUCTION_COMMAND=1|0|{turn}|8192|0|1|0|1|1|36|900'])
    world(37, True); queue('returned', 37, 1, 1, 40); state('returned', 37)
    lines.append(f'INTERACTIVE_WORKER_PRODUCTION_RETURNED=1|{turn}|0|8192|1|37|-1|-1|1|3')
    index = text.index('INTERACTIVE_ACTION_INFO_PANEL_FRAME=46|')
    text = text[:index] + '\n'.join(lines) + '\n' + text[index:]
    text += 'INTERACTIVE_WORKER_PRODUCTION_COMPLETE=1\nTURN_CYCLE_EVENT=1|local-city-order:8192:0:0:0:1:1\nTURN_CYCLE_EVENT=1|local-city-order:8192:0:1:0:1:1\n'
    return add_unstack_fixture(text, turn) if unstack else text


def add_unstack_fixture(text, turn):
    fields = {'GPU_SCENE_COMMITTED': (0,), 'WORLD_FRAME': (0, 1), 'ACTION_INFO_PANEL_FRAME': (0, 1),
              'UI_SCENE_REQUEST': (0,), 'UI_FRAME': (0, 1), 'ACTION_INFO_SMOKE_TARGET': (4,),
              'SMOKE_BUTTON': (0,), 'SMOKE_POSTED': (0,), 'ACTION_INFO_PANEL_INPUT': (0,), 'UI_NATIVE_INPUT': (0,),
              'WORKER_PRODUCTION_BEGIN': (5,), 'WORKER_PRODUCTION_QUEUE': (5,),
              'WORKER_PRODUCTION_WORKER_STATE': (4,), 'WORKER_PRODUCTION_TARGET': (6, 7),
              'WORKER_PRODUCTION_COMMAND': (9,), 'WORKER_PRODUCTION_RETURNED': (5,)}
    shifted = []
    for line in text.splitlines():
        marker, payload = line.split('=', 1); parts = payload.split('|')
        for index in fields.get(marker.removeprefix('INTERACTIVE_'), ()):
            if int(parts[index]) in (35, 36, 37): parts[index] = str(int(parts[index]) + 3)
        line = marker + '=' + '|'.join(parts)
        for old in (35, 36, 37):
            line = line.replace(f'snapshot-{old}', f'snapshot-{old+3}').replace(f'folder-{old}', f'folder-{old+3}')
        shifted.append(line)
    text = '\n'.join(shifted) + '\n'; key = 0x5A57000000000000 | (1 << 32) | 612
    lines = [f'INTERACTIVE_GPU_SCENE_COMMITTED=35|101', f'INTERACTIVE_WORLD_FRAME=35|35|{turn}|3|26|101|54|0|1',
             f'INTERACTIVE_WORKER_UNSTACK_BEGIN=1|{turn}|0|8192|24576|57349|0|611|11|15|120|35|3|2|1|0']
    def state(phase, gen):
        lines.extend([f'INTERACTIVE_WORKER_UNSTACK_QUEUE=1|{phase}|{turn}|0|8192|{gen}|0|-1|0|0',
                      f'INTERACTIVE_WORKER_UNSTACK_RESEARCH=1|{phase}|{turn}|0|{gen}|3|6|14',
                      f'INTERACTIVE_WORKER_UNSTACK_WORKER_STATE=1|{phase}|{turn}|0|{gen}|32770|571|2|300|400|-1|3|33|2|120'])
    state('before', 35)
    lines.extend([f'INTERACTIVE_WORKER_UNSTACK_TARGET=1|{turn}|0|24576|612|12|15|{key}|35|0|1|1',
                  f'INTERACTIVE_SMOKE_BUTTON=35|{key}|5|0', f'INTERACTIVE_SMOKE_POSTED=35|{key}|100|100',
                  f'INTERACTIVE_WORLD_MOVE_ROUTE={turn}|24576|12|15|0|0',
                  f'INTERACTIVE_MISSION_ACCEPTED={turn}|24576|0|12|15', f'INTERACTIVE_WINDOW_INPUT=35|5|{key}|1',
                  f'INTERACTIVE_WORKER_UNSTACK_COMMAND=1|0|{turn}|24576|0|12|15|0|0|35|{key}',
                  'INTERACTIVE_GPU_SCENE_COMMITTED=36|101', f'INTERACTIVE_WORLD_FRAME=36|36|{turn}|3|26|101|54|0|1'])
    state('returned', 36)
    lines.extend(['INTERACTIVE_WORKER_UNSTACK_SCENES=1|unstack-before|unstack-after',
                  f'INTERACTIVE_WORKER_UNSTACK_RETURNED=1|{turn}|0|24576|57349|612|12|15|60|36|3'])
    index = text.index('INTERACTIVE_UI_SCENE_REQUEST=38|action-info-panel|')
    text = UNSTACK_CAPABILITY + '\n' + text[:index] + '\n'.join(lines) + '\n' + text[index:]
    return text + 'INTERACTIVE_WORKER_UNSTACK_COMPLETE=1\nTURN_CYCLE_EVENT=1|local-push-mission:24576:0:12:15:0:0\n'


class Timeline(unittest.TestCase):
    def reject(self, text):
        with self.assertRaises(RuntimeError):
            verify_worker_research_timeline(text, required=True)

    def test_completed_equal_progress_and_zero_left(self):
        for restored in (False, True):
            text = fixture(restored=restored)
            proof = verify_worker_research_timeline(text, required=True)
            self.assertEqual(len(proof['awards']), 1)
            self.assertEqual(len(proof['continuations']), 1)
            self.assertEqual(verify_action_info_panel_timeline(text, restored, True, True), (True, None))

    def test_incomplete_zero_left_and_strict_progress(self):
        for saturated in (False, True):
            text = fixture(complete=False, saturated=saturated)
            self.assertEqual(verify_worker_research_timeline(text, required=True)['awards'], [])
            self.assertEqual(verify_action_info_panel_timeline(text, False, True, True), (True, None))
        text = fixture(complete=False)
        self.reject(text.replace('27|2|0|42|0', '27|2|0|36|0'))
        self.reject(text.replace('27|2|0|42|0', '27|2|0|42|1'))

    def test_final_turn_completion_needs_no_additional_choice(self):
        text = fixture(final_completion=True)
        proof = verify_worker_research_timeline(text, required=True)
        self.assertEqual(len(proof['awards']), 1)
        self.assertEqual(proof['continuations'], [])
        self.assertEqual(verify_action_info_panel_timeline(text, False, True, True), (True, None))

    def test_explicit_scope_and_version(self):
        self.assertIsNone(verify_worker_research_timeline('', required=False))
        for required in (False, 1, None, 'true'):
            with self.subTest(required=required), self.assertRaises(RuntimeError):
                verify_worker_research_timeline(fixture(), required=required)
        self.reject(fixture().replace(CAPABILITY, CAPABILITY[:-1] + '2'))
        self.assertFalse(verify_action_info_panel_timeline(fixture(), False, True)[0])
        for flag in REQUEST_FLAGS:
            request = dict.fromkeys(REQUEST_FLAGS, True); request[flag] = 1
            self.assertFalse(exact_worker_research_profile(request))

    def test_missing_duplicate_malformed_and_unknown_records(self):
        text = fixture()
        for name in ('WORKER_RESEARCH_CONTRACT', 'WORKER_RESEARCH_SELECTED', 'WORKER_RESEARCH_BEFORE_TURN',
                     'WORKER_RESEARCH_TURN_RETURNED', 'WORKER_TECH_AWARD_TARGET', 'WORKER_TECH_AWARD_RETURNED',
                     'WORKER_RESEARCH_TARGET', 'DECISION_RESEARCH_TARGET', 'DECISION_BEFORE_TURN',
                     'DECISION_AFTER_TURN', 'TECH_AWARD_SHOWN', 'TECH_AWARD_CLOSED', 'UI_QUEUED'):
            line = next(line for line in text.splitlines() if line.startswith('INTERACTIVE_' + name + '='))
            for replacement in ('', line + '\n' + line, line + '|invalid'):
                with self.subTest(name=name, replacement=replacement):
                    self.reject(text.replace(line, replacement, 1))
        self.reject(text + 'INTERACTIVE_WORKER_RESEARCH_BYPASS=1\n')
        self.reject(text + 'INTERACTIVE_RESEARCH_COMPLETION_FIXTURE=2|0|1\n')
        self.reject(text + 'INTERACTIVE_UI_QUEUED=68|bad\n')

    def test_identity_progress_remaining_and_callback_mutations(self):
        text = fixture()
        mutations = (
            ('BEFORE_TURN=0|0|2|24|0|36|0', 'BEFORE_TURN=0|1|2|24|0|36|0'),
            ('BEFORE_TURN=0|0|2|24|0|36|0', 'BEFORE_TURN=0|0|2|24|1|36|0'),
            ('TURN_RETURNED=1|0|2|27|-1|1|36|0', 'TURN_RETURNED=1|0|2|27|-1|1|35|0'),
            ('TURN_RETURNED=1|0|2|27|-1|1|36|0', 'TURN_RETURNED=1|0|3|27|-1|1|36|0'),
            ('TURN_RETURNED=1|0|2|27|-1|1|36|0', 'TURN_RETURNED=1|0|2|27|2|1|36|0'),
            ('AWARD_TARGET=1|0|2|600|26|1', 'AWARD_TARGET=2|0|2|600|26|1'),
            ('AWARD_TARGET=1|0|2|600|26|1', 'AWARD_TARGET=1|0|2|600|25|1'),
            ('RESEARCH_TARGET=1|0|3|800|29', 'RESEARCH_TARGET=1|0|2|800|29'),
            ('SMOKE_POSTED=26|600|100|100', 'SMOKE_POSTED=26|601|100|100'),
            ('UI_NATIVE_INPUT=26|1|600|1', 'UI_NATIVE_INPUT=26|1|600|0'),
            ('UI_NATIVE_INPUT=26|1|600|1', 'UI_NATIVE_INPUT=26|1|601|1'),
            ('UI_WINDOW_INPUT=1|2|600|1|44|44|1|0|1|99', 'UI_WINDOW_INPUT=1|2|600|1|44|45|1|0|1|99'),
            ('UI_WINDOW_INPUT=1|2|600|1|44|44|1|0|1|99', 'UI_WINDOW_INPUT=1|2|600|1|44|44|1|1|1|99'),
            ('DECISION_AFTER_TURN=1,1,0,8192,0,2,1,9,106,36,0,3', 'DECISION_AFTER_TURN=1,1,0,8192,0,2,1,0,106,36,0,3'),
            ('GPU_SCENE_COMMITTED=27|101', 'GPU_SCENE_COMMITTED=27|102'),
            ('PANEL_FRAME=27|27|1|0|100|101', 'PANEL_FRAME=27|27|1|1|100|101'),
        )
        for before, after in mutations:
            with self.subTest(before=before):
                self.assertIn(before, text)
                self.reject(text.replace(before, after, 1))

    def test_missing_choice_cannot_reuse_owned_technology(self):
        text = fixture()
        first = text.index('INTERACTIVE_ACTION_INFO_PANEL_FRAME=28|')
        last = text.index('INTERACTIVE_ACTION_INFO_PANEL_FRAME=32|')
        text = text[:first] + text[last:]
        text = text.replace('BEFORE_TURN=1|0|3|32|0|0|20', 'BEFORE_TURN=1|0|2|32|0|36|0')
        self.reject(text)

    def test_popup_return_and_worker_observation_order(self):
        text = fixture()
        a = 'INTERACTIVE_WORKER_TECH_AWARD_RETURNED=1|0|2|27|-1|1|0'
        b = 'INTERACTIVE_WORKER_RESEARCH_TURN_RETURNED=1|0|2|27|-1|1|36|0'
        self.reject(text.replace(a + '\n' + b, b + '\n' + a))
        self.reject(text.replace('INTERACTIVE_TECH_AWARD_CLOSED=600|1|0|STATE_UNCHANGED\n', ''))
        self.reject(text.replace('INTERACTIVE_UI_NATIVE_KEY=21|research-tree|27|1|0', ''))


def policy_inventories(turn=1):
    before = {'schema': 'ZEROSIS_SOCIAL_POLICY_SDK_INVENTORY_V1', 'source': 'SDK:Policies/PolicyBranches/JONSCulture',
              'activePlayer': 0, 'turn': turn, 'elapsed': turn, 'culture': 28, 'nextCost': 25, 'freePolicies': 0,
              'freeTenets': 0, 'ideology': -1, 'policySaving': False,
              'policies': [{'id': i, 'branch': -1, 'level': 0, 'has': False, 'canAdopt': False, 'blocked': False} for i in (6, 7)],
              'branches': [{'id': i, 'freePolicy': 6+i, 'unlocked': False, 'canUnlock': True, 'blocked': False} for i in (0, 1)]}
    after = copy.deepcopy(before); after['culture'] = 3; after['nextCost'] = 45
    after['policies'][0]['has'] = True; after['branches'][0]['unlocked'] = True
    for row in after['branches']:
        row['canUnlock'] = False
    return before, after


class NaturalPolicyTimeline(unittest.TestCase):
    def test_notification_popup_opens_before_consumed_callback_return(self):
        text = policy_fixture()
        events = ['INTERACTIVE_ACTION_INFO_INPUT=2|2|1|0|1|1|0',
                  'UI_WINDOW_INPUT=0|2|2|1|44|44|0|0|1|99',
                  'INTERACTIVE_UI_QUEUED=17|0|-1|-1',
                  'INTERACTIVE_SOCIAL_POLICY_SHOWN=0|0|-1|1|1',
                  'INTERACTIVE_UI_OPENED=10|social-policy',
                  f'INTERACTIVE_ACTION_INFO_PANEL_INPUT=31|1|{KEY_BASE + 2}|2|1|0']
        block = '\n'.join(events)
        self.assertIn(block, text)
        self.assertEqual(verify_worker_policy_timeline(text, required=True)['completed_cycle_count'], 1)
        for order in ((5, 0, 1, 2, 3, 4), (2, 0, 1, 3, 4, 5), (1, 0, 2, 3, 4, 5),
                      (0, 1, 3, 2, 4, 5), (0, 1, 2, 4, 3, 5), (0, 1, 2, 3, 5, 4)):
            with self.subTest(order=order), self.assertRaises(RuntimeError):
                verify_worker_policy_timeline(text.replace(block, '\n'.join(events[i] for i in order), 1), required=True)

    def test_original_policy_queue_and_open_records_are_required_unique(self):
        text = policy_fixture()
        for event in ('INTERACTIVE_ACTION_INFO_INPUT=2|2|1|0|1|1|0',
                      'UI_WINDOW_INPUT=0|2|2|1|44|44|0|0|1|99',
                      'INTERACTIVE_UI_QUEUED=17|0|-1|-1', 'INTERACTIVE_UI_OPENED=10|social-policy'):
            for replacement in ('', event + '\n' + event, event + '|invalid'):
                with self.subTest(event=event, replacement=replacement), self.assertRaises(RuntimeError):
                    verify_worker_policy_timeline(text.replace(event, replacement, 1), required=True)

    def test_original_policy_queue_and_shown_payloads_match_actor(self):
        text = policy_fixture()
        mutations = [('INTERACTIVE_UI_QUEUED=17|0|-1|-1', 'INTERACTIVE_UI_QUEUED=17|1|-1|-1'),
                     ('INTERACTIVE_UI_QUEUED=17|0|-1|-1', 'INTERACTIVE_UI_QUEUED=17|0|0|-1'),
                     ('INTERACTIVE_UI_QUEUED=17|0|-1|-1', 'INTERACTIVE_UI_QUEUED=17|0|-1|0'),
                     ('INTERACTIVE_SOCIAL_POLICY_SHOWN=0|0|-1|1|1', 'INTERACTIVE_SOCIAL_POLICY_SHOWN=0|1|-1|1|1'),
                     ('INTERACTIVE_SOCIAL_POLICY_SHOWN=0|0|-1|1|1', 'INTERACTIVE_SOCIAL_POLICY_SHOWN=0|0|0|1|1'),
                     ('INTERACTIVE_UI_OPENED=10|social-policy', 'INTERACTIVE_UI_OPENED=0|social-policy'),
                     ('INTERACTIVE_UI_OPENED=10|social-policy', 'INTERACTIVE_UI_OPENED=10|production')]
        for before, after in mutations:
            with self.subTest(after=after), self.assertRaises(RuntimeError):
                verify_worker_policy_timeline(text.replace(before, after, 1), required=True)

    def test_original_policy_callback_scope_and_timer_are_bound(self):
        text = policy_fixture()
        callback = 'INTERACTIVE_ACTION_INFO_INPUT=2|2|1|0|1|1|0'
        timer = 'UI_WINDOW_INPUT=0|2|2|1|44|44|0|0|1|99'
        for event, replacements in (
                (callback, ('3|2|1|0|1|1|0', '2|3|1|0|1|1|0', '2|2|0|0|1|1|0',
                            '2|2|1|1|1|1|0', '2|2|1|0|2|1|0', '2|2|1|0|1|0|0',
                            '2|2|1|0|1|2|0', '2|2|1|0|1|1|1')),
                (timer, ('31|2|2|1|44|44|0|0|1|99', '0|3|2|1|44|44|0|0|1|99',
                         '0|2|3|1|44|44|0|0|1|99', '0|2|2|0|44|44|0|0|1|99',
                         '0|2|2|1|44|45|0|0|1|99', '0|2|2|1|44|44|1|0|1|99',
                         '0|2|2|1|44|44|0|1|1|99', '0|2|2|1|44|44|0|0|2|99',
                         '0|2|2|1|44|44|0|0|1|0'))):
            for replacement in replacements:
                with self.subTest(event=event, replacement=replacement), self.assertRaises(RuntimeError):
                    verify_worker_policy_timeline(text.replace(event, event.split('=')[0] + '=' + replacement, 1),
                                                  required=True)

    def test_zero_one_cycle_fresh_restore_and_same_turn_research(self):
        for restored in (False, True):
            for cycle in (False, True):
                for complete in (False, True):
                    text = policy_fixture(restored=restored, cycle=cycle, complete=complete)
                    proof = verify_worker_policy_timeline(text, required=True)
                    self.assertEqual(proof['completed_cycle_count'], int(cycle))
                    self.assertEqual(len(proof['callback_inputs']), 4 * int(cycle))
                    self.assertEqual(verify_action_info_panel_timeline(text, restored, True, True, True), (True, None))

    def test_legacy_shape_and_undeclared_markers(self):
        self.assertIsNone(verify_worker_policy_timeline(fixture(), required=False))
        self.assertIsNone(verify_worker_policy_integration('', Path('.'), {}, [], required=False))
        for value in (False, 1, None, 'true'):
            with self.subTest(value=value), self.assertRaises(RuntimeError):
                verify_worker_policy_timeline(policy_fixture(), required=value)

    def test_missing_duplicate_malformed_or_unknown_policy_phase(self):
        text = policy_fixture()
        for line in text.splitlines():
            if line.startswith('INTERACTIVE_WORKER_POLICY_'):
                for replacement in ('', line + '\n' + line, line + '|invalid'):
                    with self.subTest(line=line, replacement=replacement), self.assertRaises(RuntimeError):
                        verify_worker_policy_timeline(text.replace(line, replacement, 1), required=True)
        for extra in ('INTERACTIVE_WORKER_POLICY_OTHER=1', 'INTERACTIVE_SOCIAL_POLICY_CULTURE_FIXTURE=1|0|25|25|1',
                      'INTERACTIVE_SOCIAL_POLICY_COMMAND=0|0|0|1|1'):
            with self.subTest(extra=extra), self.assertRaises(RuntimeError):
                verify_worker_policy_timeline(text + extra + '\n', required=True)

    def test_identity_generation_payload_worker_cost_and_dispatch_mutations(self):
        text = policy_fixture()
        changes = [
            ('BEGIN=1|1|0|42|31|28|25|0', 'BEGIN=1|1|1|42|31|28|25|0'),
            ('BEGIN=1|1|0|42|31|28|25|0', 'BEGIN=1|1|0|42|31|28|25|1'),
            ('branch|0|0|900|32|32|1|0', 'branch|1|0|900|32|32|1|0'),
            ('branch|0|0|900|32|32|1|0', 'branch|0|1|900|32|32|1|0'),
            ('branch|0|0|900|32|32|1|0', 'branch|0|0|900|31|32|1|0'),
            ('branch|0|0|900|32|32|1|0', 'branch|0|0|900|32|31|1|0'),
            ('branch|0|0|900|32|32|1|0', 'branch|0|0|900|32|32|2|0'),
            ('ADOPTED=1|1|0|0|0|28|25|3|34', 'ADOPTED=1|1|0|0|0|28|25|4|34'),
            ('policy-continuation|0|42|', 'policy-continuation|0|43|'),
            ('SOCIAL_POLICY_COMMAND=0|0|0|1|1', 'SOCIAL_POLICY_COMMAND=0|0|0|1|2'),
            ('UI_FRAME=33|33|1|social-policy|100|101', 'UI_FRAME=33|33|1|social-policy|102|101'),
            ('UI_NATIVE_INPUT=32|1|900|1', 'UI_NATIVE_INPUT=32|1|900|0'),
            ('UI_WINDOW_INPUT=3|2|902|1|44|44|1|0|1|99', 'UI_WINDOW_INPUT=3|2|902|1|44|45|1|0|1|99'),
            ('POLICY_COMPLETE=1', 'POLICY_COMPLETE=2'),
        ]
        state = next(line for line in text.splitlines() if line.startswith('INTERACTIVE_WORKER_POLICY_WORKER_STATE=1|selected|'))
        for index in range(5, 15):
            fields = state.split('=', 1)[1].split('|'); fields[index] = str(int(fields[index]) + 1)
            changes.append((state, state.split('=', 1)[0] + '=' + '|'.join(fields)))
        for old, new in changes:
            with self.subTest(old=old, new=new), self.assertRaises(RuntimeError):
                verify_worker_policy_timeline(text.replace(old, new, 1), required=True)
        command = 'INTERACTIVE_SOCIAL_POLICY_COMMAND=0|0|0|1|1\n'
        with self.assertRaises(RuntimeError):
            verify_worker_policy_timeline(command + text.replace(command, ''), required=True)

    def test_exact_paid_inventory_and_mutations(self):
        cycle = verify_worker_policy_timeline(policy_fixture(), required=True)['cycles'][0]
        before, after = policy_inventories()
        self.assertEqual(verify_worker_policy_inventory(before, after, cycle)['opener_added'], 6)
        for field, bad in (('culture', 4), ('freePolicies', 1), ('policySaving', True), ('elapsed', 2),
                           ('activePlayer', 1), ('freeTenets', 1), ('ideology', 0)):
            changed = copy.deepcopy(after); changed[field] = bad
            with self.subTest(field=field), self.assertRaises(RuntimeError):
                verify_worker_policy_inventory(before, changed, cycle)
        for field, index, key, value in (('policies', 1, 'has', True), ('policies', 0, 'id', True),
                                        ('policies', 0, 'branch', 0), ('policies', 0, 'blocked', True),
                                        ('branches', 0, 'freePolicy', 7), ('branches', 1, 'unlocked', True)):
            changed = copy.deepcopy(after); changed[field][index][key] = value
            with self.subTest(field=field, key=key), self.assertRaises(RuntimeError):
                verify_worker_policy_inventory(before, changed, cycle)
        changed = copy.deepcopy(before); changed['policies'].append(changed['policies'][0])
        with self.assertRaises(RuntimeError):
            verify_worker_policy_inventory(changed, after, cycle)


class FrozenOriginalCallbackSources(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).parent / 'fixtures/worker_research_callbacks'
        cls.metadata = json.loads((root / 'provenance.json').read_text(encoding='utf8'))
        cls.sources = {}
        for row in cls.metadata['files']:
            raw = (root / row['name']).read_bytes()
            if len(raw) != row['bytes'] or hashlib.sha256(raw).hexdigest() != row['sha256']:
                raise RuntimeError('Frozen original callback fixture differs from its captured manifest')
            cls.sources[row['name']] = raw.decode('utf-8-sig')

    def verify(self, kind='tree', context=None, included=None, requested=None, delivered=None):
        item = self.metadata[kind]
        return research_callback_source_pair(
            requested if requested is not None else item['requested'],
            delivered if delivered is not None else item['delivered'], item['technology'],
            context if context is not None else self.sources['TechTree.lua' if kind == 'tree' else 'TechPopup.lua'],
            included if included is not None else self.sources['TechButtonInclude.lua'], research_tree=kind == 'tree')

    def test_real_tree_b2_and_popup_b1_callback_pairs(self):
        self.assertEqual(self.metadata['tree']['delivered']['id'], 'B2')
        self.assertEqual(self.metadata['tree']['technology'], 2)
        self.verify('tree'); self.verify('popup')

    def test_context_without_shared_include_reproduces_original_failure(self):
        item = self.metadata['tree']
        with self.assertRaisesRegex(RuntimeError, 'does not bind'):
            research_callback_targets(item['requested'], item['delivered'], item['technology'],
                                      self.sources['TechTree.lua'], research_tree=True)

    def test_missing_wrong_or_duplicate_include_is_rejected(self):
        for kind, name in [('tree', 'TechTree.lua'), ('popup', 'TechPopup.lua')]:
            body = self.sources[name]
            self.assertIn('include( "TechButtonInclude" );', body)
            for replacement in ('', 'include( "OtherInclude" );',
                                'include( "TechButtonInclude" );\ninclude( "TechButtonInclude" );'):
                with self.subTest(kind=kind, replacement=replacement), self.assertRaises(RuntimeError):
                    self.verify(kind, context=body.replace('include( "TechButtonInclude" );', replacement))

    def test_wrong_context_callback_is_rejected(self):
        for kind, name in [('tree', 'TechTree.lua'), ('popup', 'TechPopup.lua')]:
            body = self.sources[name].replace('Mouse.eLClick, TechSelected', 'Mouse.eLClick, OtherSelected')
            with self.subTest(kind=kind), self.assertRaises(RuntimeError):
                self.verify(kind, context=body)

    def test_wrong_included_argument_or_callback_binding_is_rejected(self):
        body = self.sources['TechButtonInclude.lua']
        for before, after in (
            ('SetVoids(void1, void2)', 'SetVoids(void2, void1)'),
            ('RegisterCallback(thisEvent, thisCallback)', 'RegisterCallback(thisEvent, OtherCallback)'),
            ('function AddCallbackToSmallButtons(', 'function DifferentCallbackToSmallButtons('),
            ('local buttonName = "B"..tostring(buttonNum);', 'local buttonName = "Other"..tostring(buttonNum);'),
        ):
            self.assertIn(before, body)
            with self.subTest(before=before), self.assertRaises(RuntimeError):
                self.verify(included=body.replace(before, after))

    def test_wrong_delivered_technology_or_alias_bound_is_rejected(self):
        for change in ({'void1': 3}, {'void2': 1}, {'id': 'B6'}):
            delivered = {**self.metadata['tree']['delivered'], **change}
            with self.subTest(change=change), self.assertRaises(RuntimeError):
                self.verify(delivered=delivered)


class FrozenCapability(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='wp-contract-', dir=Path(__file__).resolve().parents[1])
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.loop = self.root / 'InteractiveGameLoop.h'; self.loop.write_text(CAPABILITY)
        self.build = self.root / 'build.json'
        self.build.write_text(json.dumps({'sources': [artifact(self.loop)]}))
        runner = self.root / 'run_interactive_game.py'; runner.write_text('# frozen runner\n')
        inventory = {}
        for name in VERIFIER_FILES:
            path = self.root / name; path.write_text('# frozen verifier\n'); inventory[name] = artifact(path)
        self.request = {**dict.fromkeys(REQUEST_FLAGS, True), 'worker_research_contract': 1,
                        'provenance': {'host_build': artifact(self.build), 'frozen_runner': artifact(runner),
                                       'worker_research_verifiers': inventory}}

    def test_exact_capability(self):
        self.assertTrue(worker_research_contract_required(self.request))

    def test_policy_capability_requires_exact_source_profile_and_existing_inventory(self):
        self.assertFalse(worker_policy_contract_required(self.request))
        self.loop.write_text(CAPABILITY + '\n' + POLICY_CAPABILITY)
        self.build.write_text(json.dumps({'sources': [artifact(self.loop)]}))
        self.request['provenance']['host_build'] = artifact(self.build)
        with self.assertRaises(RuntimeError):
            worker_policy_contract_required(self.request)
        self.request['worker_policy_contract'] = 1
        self.assertTrue(worker_policy_contract_required(self.request))
        for key, value in (('worker_policy_contract', True), ('worker_policy_contract', 2),
                           ('social_policy_smoke', True), ('worker_build', False)):
            changed = copy.deepcopy(self.request); changed[key] = value
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                worker_policy_contract_required(changed)
        self.loop.write_text('// changed frozen capability')
        with self.assertRaises(RuntimeError):
            worker_policy_contract_required(self.request)

    def test_missing_false_or_mutated_contract_rejected(self):
        for value in (None, False, True, 0, 2, '1'):
            request = copy.deepcopy(self.request)
            if value is None:
                del request['worker_research_contract']
            else:
                request['worker_research_contract'] = value
            with self.subTest(value=value), self.assertRaises(RuntimeError):
                worker_research_contract_required(request)

    def test_production_capability_requires_exact_full_dependency_chain(self):
        self.assertFalse(worker_production_contract_required(self.request))
        self.loop.write_text('\n'.join((CAPABILITY, POLICY_CAPABILITY, PRODUCTION_CAPABILITY)))
        self.build.write_text(json.dumps({'sources': [artifact(self.loop)]}))
        self.request['provenance']['host_build'] = artifact(self.build)
        self.request['worker_policy_contract'] = 1
        with self.assertRaises(RuntimeError): worker_production_contract_required(self.request)
        self.request['worker_production_contract'] = 1
        self.assertTrue(worker_production_contract_required(self.request))
        for key, value in (('worker_production_contract', True), ('worker_production_contract', 2),
                           ('worker_policy_contract', False), ('worker_research_contract', 0),
                           ('worker_build', False), ('social_policy_smoke', True)):
            changed = copy.deepcopy(self.request); changed[key] = value
            with self.subTest(key=key), self.assertRaises(RuntimeError): worker_production_contract_required(changed)
        self.loop.write_text('// changed frozen source')
        with self.assertRaises(RuntimeError): worker_production_contract_required(self.request)

    def test_unstack_capability_preserves_partial_profiles_and_requires_complete_chain(self):
        self.assertFalse(worker_unstack_contract_required(self.request))
        self.loop.write_text('\n'.join((CAPABILITY, POLICY_CAPABILITY, PRODUCTION_CAPABILITY, UNSTACK_CAPABILITY)))
        self.build.write_text(json.dumps({'sources': [artifact(self.loop)]}))
        self.request['provenance']['host_build'] = artifact(self.build)
        with self.assertRaises(RuntimeError): worker_unstack_contract_required(self.request)
        self.request.update(worker_policy_contract=1, worker_production_contract=1)
        self.assertTrue(worker_unstack_contract_required(self.request))
        for key, value in (('worker_build', False), ('smoke', False), ('social_policy_smoke', True)):
            changed = copy.deepcopy(self.request); changed[key] = value
            with self.subTest(key=key): self.assertFalse(worker_unstack_contract_required(changed))
        self.loop.write_text(UNSTACK_CAPABILITY)
        self.build.write_text(json.dumps({'sources': [artifact(self.loop)]}))
        self.request['provenance']['host_build'] = artifact(self.build)
        with self.assertRaises(RuntimeError): worker_unstack_contract_required(self.request)

    def test_missing_or_changed_frozen_module_rejected(self):
        request = copy.deepcopy(self.request)
        del request['provenance']['worker_research_verifiers'][VERIFIER_FILES[0]]
        with self.assertRaises(RuntimeError):
            worker_research_contract_required(request)
        (self.root / VERIFIER_FILES[0]).write_text('# changed\n')
        with self.assertRaises(RuntimeError):
            worker_research_contract_required(self.request)

    def test_out_of_scope_or_legacy_capability(self):
        for key in ('tech_award', 'combat_smoke', 'game_menu_smoke'):
            request = copy.deepcopy(self.request); request[key] = True
            with self.assertRaises(RuntimeError):
                worker_research_contract_required(request)
            del request['worker_research_contract']
            self.assertFalse(worker_research_contract_required(request))
        self.loop.write_text('// previous native contract\n')
        self.build.write_text(json.dumps({'sources': [artifact(self.loop)]}))
        self.request['provenance']['host_build'] = artifact(self.build)
        del self.request['worker_research_contract']
        self.assertFalse(worker_research_contract_required(self.request))


class PacketIntegration(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='wp-contract-', dir=Path(__file__).resolve().parents[1])
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.session = self.root / 'sessions' / 'synthetic'; self.session.mkdir(parents=True)
        self.text = fixture()
        self.driver = {'status': 'INTERACTIVE_UI_DRIVER_PASS', 'returncode': 0, 'error': None, 'scene_requests': []}
        self.frames = [list(map(int, row.split('|'))) for row in re.findall(r'^INTERACTIVE_WORLD_FRAME=(.+)$', self.text, re.M)]
        self.events = verify_worker_research_timeline(self.text, required=True)['callback_inputs']
        self.paths = []
        for event in self.events:
            sequence, generation, context = event['sequence'], event['generation'], event['context']
            snapshot = self.session / f'play-ui-{sequence}.json'
            folder = self.session / f'play-ui-{sequence}'; (folder / 'source_ui').mkdir(parents=True)
            popup = {'research-tree': ('TechTree', 'ResearchTree', 1), 'research': ('TechPopup', 'Research', 0),
                     'tech-award': ('TechAwardPopup', 'TechAward', 1)}[context]
            target = {'key': event['key'], 'id': 'ContinueButton' if context == 'tech-award' else 'TechButton',
                      'event': 'LeftClick', 'visible': True, 'disabled': False, 'void1': event['technology'], 'void2': 0}
            document = {'contextName': popup[0], 'popupKind': popup[1], 'timerSemaphore': popup[2],
                        'active': True, 'inputTargets': [target]}
            snapshot.write_text(json.dumps(document))
            packet = folder / 'scene.packet'; packet.write_bytes(b'ZSUPIX02')
            body = ('Controls.ContinueButton:RegisterCallback( Mouse.eLClick, OnContinueButtonClicked );\n'
                    'UIManager:DequeuePopup( ContextPtr );' if context == 'tech-award' else
                    'include( "TechButtonInclude" );\n'
                    'thisTechButtonInstance.TechButton:RegisterCallback( Mouse.eLClick, TechSelected );')
            source = folder / 'source_ui' / (popup[0] + '.lua'); source.write_text(body)
            original_sources = [artifact(source)]
            if context != 'tech-award':
                included = folder / 'source_ui' / 'TechButtonInclude.lua'
                included.write_text('function AddCallbackToSmallButtons( thisTechButtonInstance, maxSmallButtons, void1, void2, thisEvent, thisCallback )\n'
                                    'local buttonName = "B"..tostring(buttonNum);\n'
                                    'thisTechButtonInstance[buttonName]:SetVoids(void1, void2);\n'
                                    'thisTechButtonInstance[buttonName]:RegisterCallback(thisEvent, thisCallback);\nend\n')
                original_sources.append(artifact(included))
            hits = [[event['key'], 100, 100, 200, 200]]
            manifest = {'context': context, 'packet_version': 'ZSUPIX02', 'snapshot_state_unchanged': True,
                        'closed_context_not_drawn': False, 'retained_input_targets': [target], 'snapshot': artifact(snapshot),
                        'packet': artifact(packet), 'original_context_sources': original_sources, 'hit_regions': hits}
            manifest_path = folder / 'scene_manifest.json'; manifest_path.write_text(json.dumps(manifest))
            world_path = self.session / f'play-scene-{generation}.json'
            world_path.write_text(json.dumps({'generation': generation, 'turn': event['turn'], 'activePlayer': event['owner'],
                                              'hits': hits, 'pixelHitCount': 0}))
            self.driver['scene_requests'].append({'sequence': sequence, 'context': context, 'folder': str(folder),
                'snapshot_before_sha256': artifact(snapshot)['sha256'], 'snapshot_after_sha256': artifact(snapshot)['sha256'],
                'snapshot_state_unchanged': True, 'packet': artifact(packet), 'manifest': artifact(manifest_path)})
            self.text = self.text.replace(f'snapshot-{sequence}', str(snapshot)).replace(f'folder-{sequence}', str(folder))
            self.paths.append((snapshot, folder, world_path))

    def verify(self):
        return verify_worker_research_integration(self.text, self.root, self.driver, self.frames, required=True)

    def test_exact_original_packets(self):
        proof = self.verify()
        self.assertEqual(len(proof['original_callbacks']), 3)
        self.assertFalse(proof['human_input_verified'])

    def test_snapshot_and_driver_changes_rejected(self):
        self.driver['scene_requests'][1]['snapshot_state_unchanged'] = False
        with self.assertRaises(RuntimeError):
            self.verify()
        self.driver['scene_requests'][1]['snapshot_state_unchanged'] = True
        self.paths[1][0].write_text('{}')
        with self.assertRaises(RuntimeError):
            self.verify()

    def test_unpinned_shared_include_is_rejected(self):
        _, folder, _ = self.paths[0]
        path = folder / 'scene_manifest.json'
        manifest = json.loads(path.read_text())
        manifest['original_context_sources'] = [row for row in manifest['original_context_sources']
                                               if Path(row['path']).name != 'TechButtonInclude.lua']
        path.write_text(json.dumps(manifest))
        self.driver['scene_requests'][0]['manifest'] = artifact(path)
        with self.assertRaisesRegex(RuntimeError, 'included callback source pair'):
            self.verify()

    def test_frontmost_hit_and_original_source_changes_rejected(self):
        _, folder, world_path = self.paths[1]
        world = json.loads(world_path.read_text()); world['hits'].append([999, 100, 100, 200, 200])
        world_path.write_text(json.dumps(world))
        with self.assertRaises(RuntimeError):
            self.verify()
        world['hits'].pop(); world_path.write_text(json.dumps(world))
        next((folder / 'source_ui').glob('*.lua')).write_text('// replaced callback')
        with self.assertRaises(RuntimeError):
            self.verify()


class PolicyPacketIntegration(unittest.TestCase):
    def setUp(self):
        project = Path(__file__).resolve().parents[1]
        self.directory = tempfile.TemporaryDirectory(prefix='wp-contract-', dir=project)
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.session = self.root / 'sessions/synthetic'; self.session.mkdir(parents=True)
        self.text = policy_fixture()
        self.driver = {'status': 'INTERACTIVE_UI_DRIVER_PASS', 'returncode': 0, 'error': None, 'scene_requests': []}
        self.frames = [list(map(int, row.split('|'))) for row in re.findall(r'^INTERACTIVE_WORLD_FRAME=(.+)$', self.text, re.M)]
        self.inventories = dict(zip(('before', 'after'), policy_inventories()))
        for phase, value in self.inventories.items():
            path = self.session / f'worker-policy-1-{phase}-inventory.json'
            path.write_text(json.dumps(value), encoding='utf8')
            self.text = self.text.replace('inventory-' + phase, str(path))
        self.paths = []
        events = verify_worker_policy_timeline(self.text, required=True)['callback_inputs']
        events.append({**events[0], 'generation': 35, 'sequence': 35})
        for event in events:
            phase, context, sequence = event['phase'], event['context'], event['sequence']
            hud = phase == 'hud'; name = 'ActionInfoPanel' if hud else 'SocialPolicyPopup'
            snapshot = self.session / f'play-ui-{sequence}.json'
            folder = self.session / f'play-ui-{sequence}'; (folder / 'source_ui').mkdir(parents=True)
            sources, references = [], {}
            source_root = project / 'Source/Assets/UI/Assets/DLC/Expansion2/UI/InGame' / ('WorldView' if hud else 'Popups')
            for suffix, field in (('.lua', 'originalLua'), ('.xml', 'originalXml')):
                original = source_root / (name + suffix)
                source = folder / 'source_ui' / original.name; source.write_bytes(original.read_bytes())
                if not hud:
                    field = 'originalLayoutLua' if suffix == '.lua' else 'originalLayoutXml'
                sources.append(artifact(original)); references[field] = artifact(original)
            bounds = dict(zip(('x', 'y', 'width', 'height'), (1584, 844, 320, 36) if hud else (100, 100, 100, 100)))
            target = {'key': event['key'], 'id': {'hud': 'EndTurnButton', 'branch': 'BranchButton0', 'confirm': 'Yes', 'close': 'CloseButton'}[phase],
                      'event': 'LeftClick', 'visible': True, 'disabled': False, 'clippedBounds': bounds}
            if phase == 'branch': target['void1'] = 0
            meta = {**references, 'activePlayer': 0, 'currentTab': 'SocialPolicies',
                    'branchSwitchConfirmationPresent': False, 'ideologyChangePresent': False,
                    **{key: self.inventories['after' if phase == 'close' else 'before'][key] for key in ('policies', 'branches')}}
            document = {'contextName': name, 'popupKind': 'ActionInfoPanel' if hud else 'SocialPolicy',
                        'active': True, 'nonmodal': hud, 'timerSemaphore': 0 if hud else 1,
                        'actionInfoPanel' if hud else 'socialPolicy': meta, 'inputTargets': [target],
                        'tree': {'children': [{'id': key, 'hidden': not (phase == 'confirm' and key == 'PolicyConfirm')}
                                               for key in ('PolicyConfirm', 'TenetConfirm', 'ChangeIdeologyConfirm')]}}
            snapshot.write_text(json.dumps(document), encoding='utf8')
            packet = folder / 'scene.packet'; packet.write_bytes(b'ZSUPIX02')
            hits = [[event['key'], bounds['x'], bounds['y'], bounds['x'] + bounds['width'], bounds['y'] + bounds['height']]]
            manifest = {'context': context, 'packet_version': 'ZSUPIX02', 'snapshot_state_unchanged': True,
                        'closed_context_not_drawn': False, 'retained_input_targets': [target], 'snapshot': artifact(snapshot),
                        'packet': artifact(packet), 'original_context_sources': sources, 'hit_regions': hits}
            manifest_path = folder / 'scene_manifest.json'; manifest_path.write_text(json.dumps(manifest), encoding='utf8')
            world_path = self.session / f"play-scene-{event['generation']}.json"
            world_path.write_text(json.dumps({'generation': event['generation'], 'turn': event['turn'], 'activePlayer': 0,
                                              'hits': [[event.get('world_key', event['key']), *hits[0][1:]]], 'pixelHitCount': 0}), encoding='utf8')
            self.driver['scene_requests'].append({'sequence': sequence, 'context': context, 'folder': str(folder),
                'snapshot_before_sha256': artifact(snapshot)['sha256'], 'snapshot_after_sha256': artifact(snapshot)['sha256'],
                'snapshot_state_unchanged': True, 'packet': artifact(packet), 'manifest': artifact(manifest_path)})
            self.text = self.text.replace(f'snapshot-{sequence}', str(snapshot)).replace(f'folder-{sequence}', str(folder))
            self.paths.append((snapshot, folder, world_path))
        self.generated = [artifact(p) for p in sorted(self.session.rglob('*')) if p.is_file()]

    def verify(self):
        return verify_worker_policy_integration(self.text, self.root, self.driver, self.frames,
                                                required=True, generated=self.generated)

    def test_original_hud_three_policy_callbacks_and_inventory(self):
        proof = self.verify()
        self.assertEqual(len(proof['original_callbacks']), 4)
        self.assertEqual(proof['sdk_inventories'][0]['opener_added'], 6)
        self.assertFalse(proof['human_input_verified'])

    def retained_hud_picking(self):
        world_path = self.paths[0][2]
        world = json.loads(world_path.read_text())
        key = 0x5A57000000000000 | (1 << 32) | 612
        pick = world_path.with_suffix('.pick')
        packet = b'ZSTPICK1' + struct.pack('<IIIQII', 1920, 1080, 1, key, 1920 * 1080, 1)
        world.update(pixelHitCount=1920 * 1080, pixelHitKeys=[key], pixelHitFile=pick.name,
                     plots=[[612, 2, 3, 1, 1]])
        world_path.write_text(json.dumps(world))
        pick.write_bytes(packet)
        self.generated = [artifact(p) for p in sorted(self.session.rglob('*')) if p.is_file()]
        return world_path, world, pick, packet

    def test_nonmodal_hud_preserves_valid_terrain_picking_below_its_hit(self):
        world_path, world, pick, packet = self.retained_hud_picking()
        proof = self.verify()
        self.assertEqual(proof['original_callbacks'][0]['terrain_picking'], artifact(pick))
        self.assertTrue(proof['original_callbacks'][0]['original_callback_and_frontmost_hit_verified'])

    def test_nonmodal_hud_rejects_missing_or_corrupt_terrain_picking(self):
        world_path, world, pick, packet = self.retained_hud_picking()
        mutations = [({'pixelHitCount': 1}, packet),
                     ({'pixelHitFile': 'foreign.pick'}, packet),
                     ({'pixelHitKeys': []}, packet),
                     ({'plots': [[612, 2, 3, 1, 0]]}, packet),
                     ({}, packet[:-1]),
                     ({}, packet[:-8] + struct.pack('<II', 1920 * 1080 - 1, 1))]
        for changed, raw in mutations:
            with self.subTest(changed=changed, bytes=len(raw)):
                world_path.write_text(json.dumps({**world, **changed}))
                pick.write_bytes(raw)
                self.generated = [artifact(p) for p in sorted(self.session.rglob('*')) if p.is_file()]
                with self.assertRaises(RuntimeError):
                    self.verify()
        world_path.write_text(json.dumps(world))
        pick.unlink()
        self.generated = [artifact(p) for p in sorted(self.session.rglob('*')) if p.is_file()]
        with self.assertRaises((RuntimeError, FileNotFoundError)):
            self.verify()

    def test_modal_policy_keeps_exact_hits_and_no_terrain_picking(self):
        world_path = self.paths[1][2]
        world = json.loads(world_path.read_text())
        for changed in ({'pixelHitCount': 1920 * 1080}, {'pixelHitKeys': [123]},
                        {'pixelHitFile': 'foreign.pick'}, {'hits': list(reversed(world['hits'])) + [[999, 0, 0, 1, 1]]}):
            with self.subTest(changed=changed):
                world_path.write_text(json.dumps({**world, **changed}))
                self.generated = [artifact(p) for p in sorted(self.session.rglob('*')) if p.is_file()]
                with self.assertRaises(RuntimeError):
                    self.verify()

    def test_policy_source_uses_exact_original_layout_reference_contract(self):
        snapshot, folder, world_path = self.paths[1]
        baseline = json.loads(snapshot.read_text())
        self.assertIn('originalLayoutLua', baseline['socialPolicy'])
        self.assertIn('originalLayoutXml', baseline['socialPolicy'])
        for field in ('originalLayoutLua', 'originalLayoutXml'):
            for kind in ('legacy_field', 'bad_hash', 'wrong_source_name'):
                document = copy.deepcopy(baseline)
                meta = document['socialPolicy']
                if kind == 'legacy_field':
                    meta[field.replace('Layout', '')] = meta.pop(field)
                elif kind == 'bad_hash':
                    meta[field]['sha256'] = '0' * 64
                else:
                    meta[field]['path'] = 'TechTree.lua'
                snapshot.write_text(json.dumps(document))
                manifest_path = folder / 'scene_manifest.json'
                manifest = json.loads(manifest_path.read_text())
                manifest['snapshot'] = artifact(snapshot)
                manifest_path.write_text(json.dumps(manifest))
                for row in self.driver['scene_requests']:
                    if row['sequence'] == 32:
                        row['snapshot_before_sha256'] = row['snapshot_after_sha256'] = artifact(snapshot)['sha256']
                        row['manifest'] = artifact(manifest_path)
                self.generated = [artifact(p) for p in sorted(self.session.rglob('*')) if p.is_file()]
                with self.subTest(field=field, kind=kind), self.assertRaises(RuntimeError):
                    self.verify()

    def test_unlisted_changed_or_foreign_inventory_rejected(self):
        entry = next(row for row in self.generated if row['path'].endswith('before-inventory.json'))
        self.generated.remove(entry)
        with self.assertRaises(RuntimeError): self.verify()
        self.generated.append(entry)
        Path(entry['path']).write_text('{}')
        with self.assertRaises(RuntimeError): self.verify()

    def test_original_source_payload_and_frontmost_hit_mutations_rejected(self):
        snapshot, folder, world_path = self.paths[1]
        world = json.loads(world_path.read_text()); world['hits'].append([999, 100, 100, 200, 200])
        world_path.write_text(json.dumps(world))
        with self.assertRaises(RuntimeError): self.verify()
        world['hits'].pop(); world_path.write_text(json.dumps(world))
        source = folder / 'source_ui/SocialPolicyPopup.lua'; source.write_text('// changed original source')
        with self.assertRaises(RuntimeError): self.verify()

    def test_failed_driver_cannot_become_success(self):
        self.driver['returncode'] = 1
        with self.assertRaises(RuntimeError): self.verify()

    def test_return_world_artifact_identity_rejected(self):
        path = self.paths[-1][2]
        value = json.loads(path.read_text()); value['activePlayer'] = 1
        path.write_text(json.dumps(value))
        self.generated = [artifact(p) for p in sorted(self.session.rglob('*')) if p.is_file()]
        with self.assertRaises(RuntimeError): self.verify()


class ProductionTimeline(unittest.TestCase):
    def test_zero_one_cycle_fresh_restore_and_legacy_shape(self):
        for restored in (False, True):
            for cycle in (False, True):
                text = production_fixture(restored=restored, cycle=cycle)
                proof = verify_worker_production_timeline(text, required=True)
                self.assertEqual(proof['completed_cycle_count'], int(cycle))
                self.assertEqual(len(proof['callback_inputs']), 2 * int(cycle))
        self.assertIsNone(verify_worker_production_timeline(policy_fixture(), required=False))
        self.assertIsNone(verify_worker_production_integration('', Path('.'), {}, [], required=False))
        for required in (False, 1, None):
            with self.subTest(required=required), self.assertRaises(RuntimeError):
                verify_worker_production_timeline(production_fixture(), required=required)

    def test_every_production_marker_is_required_strict_and_unique(self):
        text = production_fixture()
        for line in text.splitlines():
            if line.startswith('INTERACTIVE_WORKER_PRODUCTION_'):
                for replacement in ('', line + '\n' + line, line + '|bogus'):
                    with self.subTest(marker=line.split('=')[0], replacement=replacement[-18:]), self.assertRaises(RuntimeError):
                        verify_worker_production_timeline(text.replace(line, replacement, 1), required=True)
        with self.assertRaises(RuntimeError):
            verify_worker_production_timeline(text + 'INTERACTIVE_WORKER_PRODUCTION_OTHER=1\n', required=True)

    def test_natural_queue_command_and_callback_mutations_rejected(self):
        text = production_fixture()
        changes = (
            ('BASELINE=0|0|8192|0|1|0|106|22', 'BASELINE=0|0|8192|1|1|0|106|22'),
            ('FINISHED=1|2|0|8192|0|57349|34', 'FINISHED=1|1|0|8192|0|57349|34'),
            ('QUEUE=1|last-turn|1|0|8192|32|1|0|97|106', 'QUEUE=1|last-turn|1|0|8192|32|0|-1|97|106'),
            ('QUEUE=1|opened|2|0|8192|36|0|-1|0|0', 'QUEUE=1|opened|2|0|8192|36|1|1|0|40'),
            ('QUEUE=1|returned|2|0|8192|37|1|1|0|40', 'QUEUE=1|returned|2|0|8192|37|1|0|0|40'),
            ('production-continuation|2|42', 'production-continuation|1|42'),
            ('COMMAND=1|0|2|8192|0|1|0|1|1|36|900', 'COMMAND=1|0|2|8192|0|1|1|1|1|36|900'),
            ('INTERACTIVE_UI_NATIVE_INPUT=36|1|900|1', 'INTERACTIVE_UI_NATIVE_INPUT=36|1|901|1'),
            ('UI_WINDOW_INPUT=4|2|900|1|44|44|0|0|2|99', 'UI_WINDOW_INPUT=4|2|900|1|44|45|0|0|2|99'),
            ('RETURNED=1|2|0|8192|1|37|-1|-1|1|3', 'RETURNED=1|2|0|8192|1|37|2|42|0|3'),
            ('BEGIN=1|2|0|8192|42|35|3', 'BEGIN=1|2|0|8192|42|35|4'),
            ('local-city-order:8192:0:1:0:1:1', 'local-city-order:8192:0:1:0:1:0'))
        for old, new in changes:
            self.assertIn(old, text)
            with self.subTest(old=old), self.assertRaises(RuntimeError):
                verify_worker_production_timeline(text.replace(old, new, 1), required=True)

    def test_all_ten_worker_fields_and_original_callback_order_preserved(self):
        text = production_fixture()
        state = next(l for l in text.splitlines() if l.startswith('INTERACTIVE_WORKER_PRODUCTION_WORKER_STATE=1|opened|'))
        for field in range(5, 15):
            parts = state.split('=', 1)[1].split('|'); parts[field] = str(int(parts[field]) + 1)
            changed = state.split('=', 1)[0] + '=' + '|'.join(parts)
            with self.subTest(field=field), self.assertRaises(RuntimeError):
                verify_worker_production_timeline(text.replace(state, changed, 1), required=True)
        command = next(l for l in text.splitlines() if l.startswith('INTERACTIVE_WORKER_PRODUCTION_COMMAND=')) + '\n'
        with self.assertRaises(RuntimeError):
            verify_worker_production_timeline(command + text.replace(command, ''), required=True)

    def test_city_order_receiver_counts_are_exact_and_order_independent(self):
        text = production_fixture()
        rows = [line for line in text.splitlines() if '|local-city-order:' in line]
        self.assertEqual(len(rows), 2)
        reordered = text.replace('\n'.join(rows), '\n'.join(reversed(rows)), 1)
        self.assertEqual(verify_worker_production_timeline(reordered, required=True)['completed_cycle_count'], 1)
        for row in rows:
            for count in (0, 2, 100):
                with self.subTest(row=row, count=count), self.assertRaises(RuntimeError):
                    verify_worker_production_timeline(text.replace(row, row.replace('=1|', f'={count}|', 1), 1), required=True)
            with self.subTest(row=row, duplicate=True), self.assertRaises(RuntimeError):
                verify_worker_production_timeline(text + row + '\n', required=True)

    def test_same_production_type_uses_one_aggregated_receiver_row(self):
        text = production_fixture()
        changes = (
            ('INTERACTIVE_WORKER_PRODUCTION_TARGET=1|2|0|8192|1|900|36|36', 'INTERACTIVE_WORKER_PRODUCTION_TARGET=1|2|0|8192|0|900|36|36'),
            ('INTERACTIVE_WORKER_PRODUCTION_COMMAND=1|0|2|8192|0|1|0|1|1|36|900', 'INTERACTIVE_WORKER_PRODUCTION_COMMAND=1|0|2|8192|0|0|0|1|1|36|900'),
            ('INTERACTIVE_WORKER_PRODUCTION_QUEUE=1|returned|2|0|8192|37|1|1|0|40', 'INTERACTIVE_WORKER_PRODUCTION_QUEUE=1|returned|2|0|8192|37|1|0|0|40'),
            ('INTERACTIVE_WORKER_PRODUCTION_RETURNED=1|2|0|8192|1|37|-1|-1|1|3', 'INTERACTIVE_WORKER_PRODUCTION_RETURNED=1|2|0|8192|0|37|-1|-1|1|3'))
        for old, new in changes:
            self.assertIn(old, text); text = text.replace(old, new, 1)
        text = '\n'.join(line for line in text.splitlines() if '|local-city-order:' not in line) + '\n'
        row = 'TURN_CYCLE_EVENT=2|local-city-order:8192:0:0:0:1:1'
        text += row + '\n'
        proof = verify_worker_production_timeline(text, required=True)
        self.assertEqual(proof['cycles'][0]['completed_unit_type'], proof['cycles'][0]['unit_type'])
        for replacement in (row.replace('=2|', '=1|', 1), row.replace('=2|', '=3|', 1),
                            '\n'.join([row.replace('=2|', '=1|', 1)] * 2)):
            with self.subTest(replacement=replacement), self.assertRaises(RuntimeError):
                verify_worker_production_timeline(text.replace(row, replacement, 1), required=True)


class ProductionPacketIntegration(unittest.TestCase):
    def setUp(self):
        project = Path(__file__).resolve().parents[1]
        self.directory = tempfile.TemporaryDirectory(prefix='wp-contract-', dir=project)
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name); self.session = self.root / 'sessions/synthetic'; self.session.mkdir(parents=True)
        self.unstack = getattr(self, 'unstack', False)
        self.text = production_fixture(unstack=self.unstack)
        self.driver = {'status': 'INTERACTIVE_UI_DRIVER_PASS', 'returncode': 0, 'error': None, 'scene_requests': []}
        self.frames = [list(map(int, r.split('|'))) for r in re.findall(r'^INTERACTIVE_WORLD_FRAME=(.+)$', self.text, re.M)]
        self.city = {'id': 8192, 'owner': 0, 'x': 11, 'y': 15}
        self.units = [{'id': 32770, 'owner': 0, 'x': 11, 'y': 14, 'unitTypeId': 1, 'unitType': 'UNIT_WORKER', 'moves': 120}]
        self.created = {'id': 57349, 'owner': 0, 'x': 11, 'y': 15, 'unitTypeId': 0, 'unitType': 'UNIT_SETTLER', 'moves': 120}
        if self.unstack:
            self.units.append({'id': 24576, 'owner': 0, 'x': 11, 'y': 15, 'unitTypeId': 0, 'unitType': 'UNIT_SETTLER', 'moves': 120})
        for generation, turn in ((22, 0), (32, 1), (34, 2)):
            self.write_world(generation, turn)
        self.text = self.text.replace('production-before', str(self.session / 'play-scene-32.json')).replace(
            'production-after', str(self.session / 'play-scene-34.json'))
        if self.unstack:
            for gen in (35, 36): self.write_world(gen, 2)
            self.text = self.text.replace('unstack-before', str(self.session / 'play-scene-35.json')).replace(
                'unstack-after', str(self.session / 'play-scene-36.json'))
            key = 0x5A57000000000000 | (1 << 32) | 612
            (self.session / 'play-scene-35.pick').write_bytes(b'ZSTPICK1' + struct.pack('<IIIQII', 1920, 1080, 1, key, 1920*1080, 1))
        proof = verify_worker_production_timeline(self.text, required=True, unstack_required=self.unstack)
        events = proof['callback_inputs']; returned = proof['cycles'][0]['returned_generation']
        events.append({**events[0], 'generation': returned, 'sequence': returned})
        self.paths = []
        for event in events:
            phase, sequence = event['phase'], event['sequence']; hud = phase == 'hud'
            context = 'action-info-panel' if hud else 'production'; name = 'ActionInfoPanel' if hud else 'ProductionPopup'
            snapshot = self.session / f'play-ui-{sequence}.json'
            folder = self.session / f'play-ui-{sequence}'; (folder / 'source_ui').mkdir(parents=True)
            sources, references = [], {}
            source_root = project / 'Source/Assets/UI/Assets/DLC/Expansion2/UI/InGame' / ('WorldView' if hud else 'Popups')
            for suffix, field in (('.lua', 'originalLua'), ('.xml', 'originalXml')):
                original = source_root / (name + suffix); source = folder / 'source_ui' / original.name
                source.write_bytes(original.read_bytes()); sources.append(artifact(original)); references[field] = artifact(original)
            bounds = dict(zip(('x', 'y', 'width', 'height'), (1584, 844, 320, 36) if hud else (100, 100, 100, 100)))
            target = {'key': event['key'], 'id': 'EndTurnButton' if hud else 'Button', 'event': 'LeftClick',
                      'visible': True, 'disabled': False, 'clippedBounds': bounds}
            if not hud: target.update(void1=6, void2=1)
            document = {'contextName': name, 'popupKind': 'ActionInfoPanel' if hud else 'Production',
                        'active': True, 'nonmodal': hud, 'timerSemaphore': 0, 'inputTargets': [target]}
            if hud: document['actionInfoPanel'] = references
            snapshot.write_text(json.dumps(document), encoding='utf8')
            packet = folder / 'scene.packet'; packet.write_bytes(b'ZSUPIX02')
            hits = [[event['key'], bounds['x'], bounds['y'], bounds['x'] + bounds['width'], bounds['y'] + bounds['height']]]
            manifest = {'context': context, 'packet_version': 'ZSUPIX02', 'snapshot_state_unchanged': True,
                        'closed_context_not_drawn': False, 'retained_input_targets': [target], 'snapshot': artifact(snapshot),
                        'packet': artifact(packet), 'original_context_sources': sources, 'hit_regions': hits}
            manifest_path = folder / 'scene_manifest.json'; manifest_path.write_text(json.dumps(manifest), encoding='utf8')
            world_path = self.write_world(event['generation'], event['turn'], [[event.get('world_key', event['key']), *hits[0][1:]]])
            self.driver['scene_requests'].append({'sequence': sequence, 'context': context, 'folder': str(folder),
                'snapshot_before_sha256': artifact(snapshot)['sha256'], 'snapshot_after_sha256': artifact(snapshot)['sha256'],
                'snapshot_state_unchanged': True, 'packet': artifact(packet), 'manifest': artifact(manifest_path)})
            self.text = self.text.replace(f'snapshot-{sequence}', str(snapshot)).replace(f'folder-{sequence}', str(folder))
            self.paths.append((snapshot, folder, world_path))
        self.refresh_generated()

    def write_world(self, generation, turn, hits=None):
        path = self.session / f'play-scene-{generation}.json'
        value = {'generation': generation, 'turn': turn, 'activePlayer': 0, 'cities': [self.city],
                 'units': self.units + ([self.created] if generation >= 34 else []), 'hits': hits or [], 'pixelHitCount': 0}
        if self.unstack:
            value.update(gridWidth=40, gridHeight=24, plots=[[611, 11, 15, 1, 1], [612, 12, 15, 1, 1]], visibleForeignUnits=[])
            value['units'] = copy.deepcopy(value['units'])
            moving = next(u for u in value['units'] if u['id'] == 24576)
            moving['selected'] = generation == 35
            if generation >= 36: moving.update(x=12, moves=60)
            if generation == 35:
                value.update(pixelHitCount=1920*1080, pixelHitKeys=[0x5A57000000000000 | (1 << 32) | 612], pixelHitFile=path.with_suffix('.pick').name)
        path.write_text(json.dumps(value), encoding='utf8'); return path

    def refresh_generated(self):
        self.generated = [artifact(p) for p in sorted(self.session.rglob('*')) if p.is_file()]

    def verify(self):
        return verify_worker_production_integration(self.text, self.root, self.driver, self.frames,
            required=True, generated=self.generated, unstack_required=self.unstack)

    def test_natural_unit_difference_original_hud_and_next_order_callback(self):
        proof = self.verify()
        self.assertEqual(len(proof['original_callbacks']), 2)
        self.assertEqual(proof['natural_completions'][0]['produced_unit']['id'], 57349)
        self.assertEqual(proof['natural_completions'][0]['owned_unit_count_after'], 2)
        self.assertFalse(proof['human_input_verified'])

    def test_missing_or_changed_generated_scene_is_rejected(self):
        path = self.session / 'play-scene-34.json'
        entry = next(r for r in self.generated if r['path'] == str(path))
        self.generated.remove(entry)
        with self.assertRaises(RuntimeError): self.verify()
        self.generated.append(entry); path.write_text('{}')
        with self.assertRaises(RuntimeError): self.verify()

    def test_produced_unit_identity_owner_location_and_duplicates_rejected(self):
        path = self.session / 'play-scene-34.json'; original = json.loads(path.read_text())
        for field, value in (('owner', 1), ('id', 999), ('unitType', 'UNIT_WORKER'), ('unitTypeId', 1), ('x', 12)):
            changed = copy.deepcopy(original); changed['units'][-1][field] = value
            path.write_text(json.dumps(changed)); self.refresh_generated()
            with self.subTest(field=field), self.assertRaises(RuntimeError): self.verify()
        for units in (original['units'] * 2, original['units'][:-1], [original['units'][-1]]):
            changed = copy.deepcopy(original); changed['units'] = units
            path.write_text(json.dumps(changed)); self.refresh_generated()
            with self.assertRaises(RuntimeError): self.verify()

    def test_mismatched_scene_path_original_source_and_frontmost_hit_rejected(self):
        original_text = self.text
        self.text = self.text.replace(str(self.session / 'play-scene-32.json'), str(self.session / 'play-scene-22.json'))
        with self.assertRaises(RuntimeError): self.verify()
        self.text = original_text
        _, folder, world_path = self.paths[1]
        value = json.loads(world_path.read_text()); value['hits'].append([999, 100, 100, 200, 200])
        world_path.write_text(json.dumps(value)); self.refresh_generated()
        with self.assertRaises(RuntimeError): self.verify()
        value['hits'].pop(); world_path.write_text(json.dumps(value))
        (folder / 'source_ui/ProductionPopup.lua').write_text('// changed source')
        self.refresh_generated()
        with self.assertRaises(RuntimeError): self.verify()

    def test_failed_driver_and_wrong_return_owner_are_rejected(self):
        self.driver['returncode'] = 1
        with self.assertRaises(RuntimeError): self.verify()
        self.driver['returncode'] = 0
        path = self.paths[-1][2]; value = json.loads(path.read_text()); value['activePlayer'] = 1
        path.write_text(json.dumps(value)); self.refresh_generated()
        with self.assertRaises(RuntimeError): self.verify()

    def test_resealed_wrong_original_control_and_void_pair_are_rejected(self):
        snapshot, folder, _ = self.paths[1]
        original = json.loads(snapshot.read_text())
        manifest_path = folder / 'scene_manifest.json'
        manifest_original = json.loads(manifest_path.read_text())
        prepared = next(r for r in self.driver['scene_requests'] if r['sequence'] == 36)
        for field, value in (('id', 'UnitButton'), ('void1', 7), ('void2', 0)):
            changed = copy.deepcopy(original); changed['inputTargets'][0][field] = value
            snapshot.write_text(json.dumps(changed))
            manifest = copy.deepcopy(manifest_original); manifest['retained_input_targets'] = changed['inputTargets']
            manifest['snapshot'] = artifact(snapshot); manifest_path.write_text(json.dumps(manifest))
            prepared['snapshot_before_sha256'] = prepared['snapshot_after_sha256'] = artifact(snapshot)['sha256']
            prepared['manifest'] = artifact(manifest_path); self.refresh_generated()
            with self.subTest(field=field), self.assertRaises(RuntimeError): self.verify()


class UnstackTimeline(unittest.TestCase):
    def test_zero_one_cycle_and_sealed_contract_cannot_be_omitted(self):
        for restored in (False, True):
            for cycle in (False, True):
                text = production_fixture(restored=restored, cycle=cycle, unstack=True)
                proof = verify_worker_production_timeline(text, required=True, unstack_required=True)
                self.assertEqual(proof['unstack']['completed_cycle_count'], int(cycle))
                stripped = '\n'.join(l for l in text.splitlines() if not l.startswith('INTERACTIVE_WORKER_UNSTACK_'))
                with self.assertRaises(RuntimeError): verify_worker_production_timeline(stripped, required=True, unstack_required=True)
                with self.assertRaises(RuntimeError): verify_worker_production_timeline(text, required=True)
        self.assertNotIn('unstack', verify_worker_production_timeline(production_fixture(), required=True))

    def test_all_unstack_markers_and_ten_worker_fields_are_strict(self):
        text = production_fixture(unstack=True)
        for line in text.splitlines():
            if line.startswith('INTERACTIVE_WORKER_UNSTACK_'):
                for replacement in ('', line + '\n' + line, line + '|bad'):
                    with self.subTest(marker=line.split('=')[0]), self.assertRaises(RuntimeError):
                        verify_worker_production_timeline(text.replace(line, replacement, 1), required=True, unstack_required=True)
        state = next(l for l in text.splitlines() if l.startswith('INTERACTIVE_WORKER_UNSTACK_WORKER_STATE=1|returned|'))
        for field in range(5, 15):
            parts = state.split('=', 1)[1].split('|'); parts[field] = str(int(parts[field]) + 1)
            changed = state.split('=', 1)[0] + '=' + '|'.join(parts)
            with self.subTest(field=field), self.assertRaises(RuntimeError):
                verify_worker_production_timeline(text.replace(state, changed, 1), required=True, unstack_required=True)

    def test_fake_direct_move_disabled_skip_and_state_changes_are_rejected(self):
        text = production_fixture(unstack=True); key = 0x5A57000000000000 | (1 << 32) | 612
        changes = [
            ('|35|3|2|1|0', '|35|3|2|1|1'),
            ('INTERACTIVE_WORKER_UNSTACK_RESEARCH=1|returned|2|0|36|3|6|14', 'INTERACTIVE_WORKER_UNSTACK_RESEARCH=1|returned|2|0|36|3|7|14'),
            ('INTERACTIVE_WORKER_UNSTACK_QUEUE=1|returned|2|0|8192|36|0|-1|0|0', 'INTERACTIVE_WORKER_UNSTACK_QUEUE=1|returned|2|0|8192|36|1|0|0|106'),
            (f'INTERACTIVE_SMOKE_BUTTON=35|{key}|5|0', f'INTERACTIVE_SMOKE_BUTTON=35|{key}|1|0'),
            (f'INTERACTIVE_SMOKE_POSTED=35|{key}|100|100', ''),
            ('INTERACTIVE_WORLD_MOVE_ROUTE=2|24576|12|15|0|0', ''),
            ('INTERACTIVE_MISSION_ACCEPTED=2|24576|0|12|15', ''),
            (f'INTERACTIVE_WINDOW_INPUT=35|5|{key}|1', f'INTERACTIVE_WINDOW_INPUT=35|5|{key}|0'),
            ('TURN_CYCLE_EVENT=1|local-push-mission:24576:0:12:15:0:0', ''),
            ('INTERACTIVE_WORKER_UNSTACK_COMPLETE=1', 'INTERACTIVE_WORKER_UNSTACK_COMPLETE=2')]
        for old, new in changes:
            self.assertIn(old, text)
            with self.subTest(old=old), self.assertRaises(RuntimeError):
                verify_worker_production_timeline(text.replace(old, new, 1), required=True, unstack_required=True)
        injected = text.replace('INTERACTIVE_WORKER_UNSTACK_TARGET=', 'INTERACTIVE_UNIT_PANEL_INPUT=35|1|999|1\nINTERACTIVE_WORKER_UNSTACK_TARGET=', 1)
        with self.assertRaises(RuntimeError): verify_worker_production_timeline(injected, required=True, unstack_required=True)
        with self.assertRaises(RuntimeError):
            verify_worker_production_timeline(text + 'TURN_CYCLE_EVENT=1|local-push-mission:24576:0:13:15:0:0\n', required=True, unstack_required=True)

    def test_unstack_receiver_is_aggregated_exactly_once(self):
        text = production_fixture(unstack=True)
        row = 'TURN_CYCLE_EVENT=1|local-push-mission:24576:0:12:15:0:0'
        self.assertIn(row, text)
        self.assertEqual(verify_worker_production_timeline(text, required=True, unstack_required=True)['unstack']['completed_cycle_count'], 1)
        for count in (0, 2, 102):
            with self.subTest(count=count), self.assertRaises(RuntimeError):
                verify_worker_production_timeline(text.replace(row, row.replace('=1|', f'={count}|', 1), 1), required=True, unstack_required=True)
        with self.assertRaises(RuntimeError):
            verify_worker_production_timeline(text + row + '\n', required=True, unstack_required=True)


class UnstackPacketIntegration(unittest.TestCase):
    write_world = ProductionPacketIntegration.write_world
    refresh_generated = ProductionPacketIntegration.refresh_generated
    verify = ProductionPacketIntegration.verify

    def setUp(self):
        self.unstack = True
        ProductionPacketIntegration.setUp(self)

    def test_original_right_click_uses_committed_pick_and_preserves_other_units(self):
        proof = self.verify()
        self.assertEqual(proof['unstack']['completed_cycle_count'], 1)
        self.assertEqual(proof['unstack']['cycles'][0]['unit'], 24576)
        self.assertEqual(proof['unstack']['cycles'][0]['target'], [612, 12, 15])
        self.assertTrue(proof['unstack']['world_bindings'][0]['original_native_movement_verified'])

    def test_missing_pick_intercepted_click_occupied_or_hidden_destination_rejected(self):
        pick = self.session / 'play-scene-35.pick'
        entry = next(r for r in self.generated if r['path'] == str(pick)); self.generated.remove(entry)
        with self.assertRaises(RuntimeError): self.verify()
        self.generated.append(entry)
        path = self.session / 'play-scene-35.json'; original = json.loads(path.read_text())
        changes = []
        value = copy.deepcopy(original); value['hits'] = [[999, 100, 100, 200, 200]]; changes.append(value)
        value = copy.deepcopy(original); value['plots'][1][4] = 0; changes.append(value)
        value = copy.deepcopy(original); value['visibleForeignUnits'] = [{'id': 9, 'owner': 1, 'x': 12, 'y': 15}]; changes.append(value)
        value = copy.deepcopy(original); next(u for u in value['units'] if u['id'] == 24576)['selected'] = False; changes.append(value)
        for value in changes:
            path.write_text(json.dumps(value)); self.refresh_generated()
            with self.assertRaises(RuntimeError): self.verify()
        path.write_text(json.dumps(original))
        raw = bytearray(pick.read_bytes()); raw[-1] = 1; pick.write_bytes(raw); self.refresh_generated()
        with self.assertRaises(RuntimeError): self.verify()

    def test_wrong_moving_identity_and_changes_to_other_units_or_research_rejected(self):
        path = self.session / 'play-scene-36.json'; original = json.loads(path.read_text())
        for identity, field, value in ((24576, 'x', 13), (24576, 'moves', 120), (24576, 'unitTypeId', 1),
                                        (32770, 'moves', 60), (57349, 'x', 12)):
            changed = copy.deepcopy(original); next(u for u in changed['units'] if u['id'] == identity)[field] = value
            path.write_text(json.dumps(changed)); self.refresh_generated()
            with self.subTest(identity=identity, field=field), self.assertRaises(RuntimeError): self.verify()


if __name__ == '__main__':
    unittest.main()
