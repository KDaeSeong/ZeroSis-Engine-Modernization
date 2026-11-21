"""Validate the bounded original EconomicOverview posted HWND input timeline.

This checks dispatch and lifecycle records. SDK state, retained rows, rendered
targets, save bytes and restore lineage are checked by the independent verifier.
"""
from __future__ import annotations

import re

FIXTURE = re.compile(r'^INTERACTIVE_ECONOMIC_FIXTURE=(FRESH|RESTORED)\|(\d+)\|(\d+)\|(\d+)\|NO_SDK_SETUP$', re.M)
ACTION = re.compile(r'^INTERACTIVE_ECONOMIC_ACTION=(\d+)\|([^|]+)\|(\d+)\|(\d+)\|(\d+)\|(-?\d+)$', re.M)
NAMES = ('GoldPerTurn', 'SortPopulation', 'SortPopulation', 'CityToggle', 'CityToggle',
         'HappinessButton', 'CityUnhappinessToggle', 'CityUnhappinessToggle', 'GeneralInfoButton',
         'ProdButton', 'CloseButton', 'ProdButton', 'Button', 'HappinessButton', 'CloseButton',
         'GoldPerTurn', 'HappinessButton', 'KEY_ESCAPE')
TOP_BASE = 1 << 51
GENERAL_BASE, HAPPINESS_BASE = 1 << 48, 2 << 48


def verify_economic_overview_timeline(text: str) -> tuple[bool, str | None]:
    """Fresh and restore both browse, cancel, choose a different unit and return."""
    def records(pattern: str, start: int = 0, end: int | None = None):
        return list(re.finditer(pattern, text[start:end], re.M))

    fixtures, actions = list(FIXTURE.finditer(text)), list(ACTION.finditer(text))
    if len(fixtures) != 1 or len(records(r'^INTERACTIVE_ECONOMIC_FIXTURE=')) != 1:
        return False, 'Economic smoke must declare exactly one original SDK scope without setup writes'
    owner, turn, city = map(int, fixtures[0].group(2, 3, 4))
    if owner >= 64 or [int(row[1]) for row in actions] != list(range(1, 19)) or \
            [row[2] for row in actions] != list(NAMES) or len(records(r'^INTERACTIVE_ECONOMIC_ACTION=')) != 18:
        return False, 'Economic smoke differs from the exact eighteen original-control actions'
    if fixtures[0].end() > actions[0].start() or any(int(row[3]) <= 0 for row in actions) or int(actions[-1][3]) != 27:
        return False, 'Economic fixture order, target key or Escape virtual key is invalid'
    if any(int(b[4]) <= int(a[4]) or int(b[5]) <= int(a[5]) for a, b in zip(actions, actions[1:])):
        return False, 'Economic actions reused or reversed a published generation/revision'
    expected_payload = {2: 0, 3: 0, 10: city, 12: city}
    selected_unit = int(actions[12][6])
    if selected_unit < 0 or any(int(row[6]) != expected_payload.get(int(row[1]), selected_unit if int(row[1]) == 13 else -1)
                                for row in actions):
        return False, 'Economic actions lost original sort, city or production payloads'
    complete = records(r'^INTERACTIVE_ECONOMIC_COMPLETE=(\d+)\|(\d+)\|(\d+)\|(\d+)\|CANCEL_AND_DIFFERENT_PRODUCTION$')
    if len(complete) != 1 or complete[0].start() <= actions[-1].end() or \
            tuple(map(int, complete[0].group(3, 4))) != (turn, selected_unit) or \
            int(complete[0][1]) <= int(actions[-1][4]) or int(complete[0][2]) <= int(actions[-1][5]):
        return False, 'Economic smoke lacks its final original Escape and world-return observation'
    children = {2: 1, 3: 1, 4: 1, 5: 1, 7: 2, 8: 2, 10: 1, 12: 1}
    for index, row in enumerate(actions):
        stage, key, generation = int(row[1]), int(row[3]), int(row[4])
        end = actions[index + 1].start() if index < 17 else complete[0].start()
        interval = text[row.end():end]
        dispatch = {}
        for marker, fields in (
                ('INTERACTIVE_SMOKE_POSTED', r'(\d+)\|(\d+)\|-?\d+\|-?\d+'),
                ('INTERACTIVE_UI_NATIVE_INPUT', r'(\d+)\|([0-5])\|(\d+)\|([01])'),
                ('INTERACTIVE_TOP_PANEL_INPUT', r'(\d+)\|([0-5])\|(\d+)\|(\d+)\|([01])'),
                ('INTERACTIVE_UI_NATIVE_KEY', r'(\d+)\|([^|\r\n]+)\|(\d+)\|([01])\|([01])')):
            parsed = list(re.finditer('^' + marker + '=' + fields + '$', interval, re.M))
            if len(parsed) != len(re.findall('^' + marker + '=', interval, re.M)):
                return False, f'Economic stage {stage} contains a malformed native dispatch record'
            dispatch[marker] = parsed
        posts = [item.groups() for item in dispatch['INTERACTIVE_SMOKE_POSTED']]
        # Pointer motion is passive; every other native input is an additional
        # command unless it is the one exact action declared by this stage.
        native_rows = [item for item in dispatch['INTERACTIVE_UI_NATIVE_INPUT'] if item[2] != '3']
        top_rows = [item for item in dispatch['INTERACTIVE_TOP_PANEL_INPUT'] if item[2] != '3']
        native_commands = [item.groups() for item in native_rows]
        key_rows = dispatch['INTERACTIVE_UI_NATIVE_KEY']
        if stage == 18:
            if posts or top_rows or [item.groups() for item in key_rows] != [(str(generation), 'economic-overview', '27', '1', '0')] or \
                    native_commands != [(str(generation), '0', '0', '1')] or native_rows[0].end() > key_rows[0].start():
                return False, 'Economic Escape was not consumed once by the original parent and closed it'
        else:
            if posts != [(str(generation), str(key))] or key_rows:
                return False, f'Economic stage {stage} has no unique exact HWND post'
            if stage in (1, 16):
                actual = [item.groups() for item in top_rows]
                if native_commands or key <= TOP_BASE or actual != [(str(generation), '1', str(key), str(key - TOP_BASE), '1')]:
                    return False, f'Economic stage {stage} did not use the original TopPanel input route'
                consumed = top_rows[0]
            elif top_rows or native_commands != [(str(generation), '1', str(key), '1')]:
                return False, f'Economic stage {stage} did not consume its exact posted native input'
            else:
                consumed = native_rows[0]
            if dispatch['INTERACTIVE_SMOKE_POSTED'][0].end() > consumed.start():
                return False, f'Economic stage {stage} consumed input before its HWND post'
        child = re.findall(r'^INTERACTIVE_ECONOMIC_OVERVIEW_CHILD_INPUT=2\|(\d+)\|1\|1\|1\|([12])$', interval, re.M)
        if child != ([(str(key), str(children[stage]))] if stage in children else []):
            return False, f'Economic stage {stage} lost its visible child route or retained parent timer'
        if stage in children and key >> 48 != children[stage]:
            return False, f'Economic stage {stage} uses the wrong child key namespace'
        opened = re.findall(r'^INTERACTIVE_ECONOMIC_PRODUCTION_OPENED=(\d+)\|(\d+)\|(\d+)$', interval, re.M)
        returned = re.findall(r'^INTERACTIVE_ECONOMIC_PRODUCTION_RETURNED=(\d+)\|(\d+)$', interval, re.M)
        if opened != ([(str(owner), str(city), str(turn))] if stage in (10, 12) else []) or \
                returned != ([(str(owner), str(turn))] if stage in (11, 13) else []):
            return False, f'Economic stage {stage} has an incorrect production suspension/return lifecycle'
        shown = re.findall(r'^INTERACTIVE_ECONOMIC_OVERVIEW_SHOWN=(\d+)\|(\d+)\|(\d+)\|1$', interval, re.M)
        if shown != ([(str(owner), str(owner), str(turn))] if stage in (1, 16) else []):
            return False, f'Economic stage {stage} has an incorrect original popup show lifecycle'
    for marker, count in (('INTERACTIVE_ECONOMIC_OVERVIEW_CHILD_INPUT', 8), ('INTERACTIVE_ECONOMIC_PRODUCTION_OPENED', 2),
                          ('INTERACTIVE_ECONOMIC_PRODUCTION_RETURNED', 2), ('INTERACTIVE_ECONOMIC_OVERVIEW_SHOWN', 2),
                          ('INTERACTIVE_ECONOMIC_PRODUCTION_VERIFIED', 1), ('INTERACTIVE_ECONOMIC_COMPLETE', 1),
                          ('INTERACTIVE_ECONOMIC_DECISION_BASELINE', 1)):
        if len(records('^' + marker + '=')) != count:
            return False, f'Economic record {marker} has an unexpected count or malformed duplicate'
    verified = records(r'^INTERACTIVE_ECONOMIC_PRODUCTION_VERIFIED=(\d+)\|(-?\d+)\|(\d+)\|(\d+)\|(\d+)\|1$')
    if len(verified) != 1 or tuple(map(int, verified[0].group(1, 3, 4))) != (city, selected_unit, int(actions[11][3])) or \
            int(verified[0][2]) == selected_unit or int(verified[0][5]) <= GENERAL_BASE or int(verified[0][5]) >> 48 != 1 or \
            int(verified[0][4]) == int(verified[0][5]) or not actions[12].end() < verified[0].start() < actions[13].start():
        return False, 'Economic real selection has no changed production and rebuilt original row observation'
    baseline = records(r'^INTERACTIVE_ECONOMIC_DECISION_BASELINE=(\d+)\|(\d+)\|(\d+)$')
    if len(baseline) != 1 or tuple(map(int, baseline[0].group(1, 2))) != (city, selected_unit) or baseline[0].start() < complete[0].end():
        return False, 'Normal next-turn baseline does not observe the actual economic production selection'
    return True, None
