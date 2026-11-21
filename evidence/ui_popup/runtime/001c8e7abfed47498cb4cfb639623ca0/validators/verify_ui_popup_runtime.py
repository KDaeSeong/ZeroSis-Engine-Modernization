"""Verify official ranking UI scripts against real isolated SDK game/RNG state.

This checks the host's explicit synchronous popup dispatch contract. It does not
establish retail event scheduling, rendered pixels, or post-popup retail parity.
"""
import argparse
import json
import re
import shutil
import uuid
from pathlib import Path

from collect_baseline import PROJECT, digest
from probe_world_builder import artifact
from verify_first_turn_candidate import read_artifact
from verify_world_builder_map_object import check_artifacts
from verify_extended_turns import inspect_extended, VALIDATORS
from prepare_ui_popup_assets import control_tree, lua_value
import xml.etree.ElementTree as ET

ROOT = PROJECT / 'evidence/ui_popup/runtime'


def find(node, name):
    if node['id'] == name:
        return node
    for child in node['children']:
        value = find(child, name)
        if value is not None:
            return value
    return None


def embedded(header, name):
    match = re.search(r'static const char ' + re.escape(name) + r'\[\]=\s*([\s\S]*?);', header)
    if not match:
        raise RuntimeError('Compiled UI source is missing: ' + name)
    body = match[1]
    if re.sub(r'"(?:\\x[0-9a-f]{2})*"|\s+', '', body):
        raise RuntimeError('Unexpected compiled asset encoding')
    return bytes.fromhex(''.join(re.findall(r'\\x([0-9a-f]{2})', body)))


def inspect_popup(run_id,fixture_promotions=False,fixture_unit_actions=False):
    row = inspect_extended(run_id, ui_popups=True,fixture_promotions=fixture_promotions,
                           fixture_unit_actions=fixture_unit_actions)
    result = read_artifact(row['result'])
    request = read_artifact(result['request'])
    build = read_artifact(request['candidate_build'])
    assets = read_artifact(build['ui_assets'])
    sources = {Path(item['path']).name: item for item in build['sources']}
    header = Path(sources['UiPopupAssets.generated.h']['path']).read_text(encoding='ascii')
    # The compiled bytes, retained original assets and recorded source agree.
    for item in assets['inputs']:
        check_artifacts(item['snapshot'])
        data = Path(item['snapshot']['path']).read_bytes()
        if item['name'] == 'WhosWinningLayout':
            data = ('ZeroSisUiLayout=' + lua_value(control_tree(ET.fromstring(data))) + '\n').encode('ascii')
        if embedded(header, item['name']) != data:
            raise RuntimeError('Compiled popup asset differs from the retained official input')
    if embedded(header, 'ZeroSisUiScene') != Path(sources['UiScene.lua']['path']).read_bytes():
        raise RuntimeError('The compiled retained UI runtime differs from its source')
    generated = {Path(item['path']).name: item for item in result['generated_files']
                 if re.fullmatch(r'ui-popup-\d+-(shown|closed)\.json', Path(item['path']).name)}
    output = Path(result['stdout']['path']).read_text(encoding='utf8')
    shown = re.findall(r'^UI_POPUP_shown=(\d+),(\d+),(\d+)$', output, re.M)
    closed = re.findall(r'^UI_POPUP_closed=(\d+),(\d+),(\d+)$', output, re.M)
    expected_count = row['final_turn'] // 25
    if not expected_count or len(shown) != expected_count or len(closed) != expected_count or len(generated) != expected_count * 2:
        raise RuntimeError('The fixture did not execute and preserve each scheduled popup')
    expected_close_counts = ['0', str(expected_count)]
    if re.findall(r'^UI_POPUP_CONTEXT_CLOSED=(\d+)$', output, re.M) != expected_close_counts:
        raise RuntimeError('Persistent UI contexts were not closed once per SDK session')
    popups = []
    previous_mode = -1
    row_keys = None
    for index, (show, close) in enumerate(zip(shown, closed), 1):
        if [int(v) for v in show[:2]] != [index, index * 25] or show[:2] != close[:2]:
            raise RuntimeError('The configured normal-speed popup schedule differs')
        pair = []
        for phase, log in (('shown', show), ('closed', close)):
            asset = generated[f'ui-popup-{index}-{phase}.json']
            check_artifacts(asset)
            data = Path(asset['path']).read_bytes()
            if len(data) != int(log[2]):
                raise RuntimeError('Popup snapshot length differs from the runtime log')
            value = json.loads(data)
            if value['active'] is not (phase == 'shown') or value['timerSemaphore'] != (1 if phase == 'shown' else 0):
                raise RuntimeError('Popup lifecycle/timer ownership is unbalanced')
            if any(value[field] is not False for field in ('rendererVerified', 'styleExpansionVerified', 'fontMeasurementVerified')):
                raise RuntimeError('A retained scene cannot certify pixels, styles or font measurement')
            pair.append(value)
        a, b = pair
        if a['tree'] != b['tree'] or a['draws'] != b['draws'] or \
           a['lifecycle'] != ['queued', 'shown:54'] or b['lifecycle'] != ['queued', 'shown:54', 'processed:54', 'closed']:
            raise RuntimeError('Official close changed the ranking/RNG trace or bypassed lifecycle events')
        draws = a['draws']
        if not isinstance(draws, list) or len(draws) < 2:
            raise RuntimeError('Missing original popup random draws')
        for draw_index, draw in enumerate(draws):
            limit = 7 if draw_index == 0 else 10
            reason = 'Rolling to determine Progress Screen ' + ('dude.' if draw_index == 0 else 'list type.')
            if draw['limit'] != limit or draw['reason'] != reason:
                raise RuntimeError('Unexpected popup RNG operation')
            before, after = draw['seedBefore'], draw['seedAfter']
            expected = (1103515245 * before + 12345) & 0xffffffff
            if not isinstance(before, int) or not 0 <= before <= 0xffffffff or after != expected or \
               draw['value'] != (((expected >> 16) & 65535) * limit) // 65536:
                raise RuntimeError('Popup Game.Rand did not advance the real SDK synchronous LCG exactly once')
            if draw_index and draws[draw_index - 1]['seedAfter'] != before:
                raise RuntimeError('Another unrecorded synchronous RNG draw intervened in the popup')
        mode = draws[-1]['value']
        if mode == previous_mode:
            raise RuntimeError('The persistent official context repeated its previous list mode')
        previous_mode = mode
        stack = find(a['tree'], 'PlayerListStack')
        ranking = [child for child in stack['children'] if not child['hidden']]
        if mode == 9:
            if not 1 <= len(ranking) <= 10:
                raise RuntimeError('Invalid tourist city ranking size')
        elif len(ranking) != 2:
            raise RuntimeError('The configured two alive major players must each have a ranking row')
        labels = [find(a['tree'], key) for key in ('PresentsLabel', 'ListNameLabel')]
        if any(not label['text'] or 'TXT_KEY_' in label['text'] or not label['tooltip'] for label in labels):
            raise RuntimeError('Popup title/list labels were not localized')
        for rank, entry in enumerate(ranking, 1):
            name = find(entry, 'PlayerNameText')['text']
            score = find(entry, 'ScoreText')['text']
            if not name or not score or 'TXT_KEY_' in name + score:
                raise RuntimeError('The actual ranking row has missing or unlocalized output')
        keys = [entry['key'] for entry in ranking]
        if row_keys is not None and mode != 9 and keys != row_keys:
            raise RuntimeError('The persistent two-row official instance pool was not reused')
        if mode != 9:
            row_keys = keys
        popups.append({'index': index, 'turn': index * 25, 'mode': mode, 'draws': draws,
                       'ranked_rows': len(ranking), 'row_keys': keys,
                       'title': labels[0]['text'], 'list_name': labels[1]['text'],
                       'shown': generated[f'ui-popup-{index}-shown.json'],
                       'closed': generated[f'ui-popup-{index}-closed.json']})
    row.update(ui_assets=build['ui_assets'], popups=popups)
    return row


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', action='append', required=True)
    parser.add_argument('--fixture-promotions', action='store_true')
    parser.add_argument('--fixture-unit-actions', action='store_true')
    args = parser.parse_args()
    if args.fixture_unit_actions and not args.fixture_promotions:
        parser.error('--fixture-unit-actions requires --fixture-promotions')
    if len(args.run) < 2 or len(set(args.run)) != len(args.run):
        parser.error('Provide distinct successful runs covering both languages')
    names = (*VALIDATORS, 'verify_ui_popup_runtime.py', 'prepare_ui_popup_assets.py')
    output = ROOT / uuid.uuid4().hex
    frozen = output / 'validators'
    frozen.mkdir(parents=True, exist_ok=False)
    before = {name: digest(PROJECT / 'tools' / name) for name in names}
    for name in names:
        shutil.copy2(PROJECT / 'tools' / name, frozen / name)
        if digest(frozen / name) != before[name]:
            raise RuntimeError('UI validator changed while freezing')
    rows = [inspect_popup(run_id,fixture_promotions=args.fixture_promotions,
                          fixture_unit_actions=args.fixture_unit_actions) for run_id in args.run]
    if {row['language'] for row in rows} != {'en_US', 'ko_KR'} or \
       any(row['inputs'] != rows[0]['inputs'] or row['final_turn'] != rows[0]['final_turn'] or
           row['fixture_promotions_enabled'] is not args.fixture_promotions or
           row['fixture_unit_actions_enabled'] is not args.fixture_unit_actions for row in rows):
        raise RuntimeError('Both language runs must use the same inputs and final turn')
    signatures = [[(p['turn'], p['mode'], p['draws'], p['ranked_rows']) for p in row['popups']] for row in rows]
    if any(signature != signatures[0] for signature in signatures[1:]):
        raise RuntimeError('Language/worker setting changed the observed UI RNG or ranking shape')
    promotion_signature=[row['fixture_promotions'] for row in rows]
    if any(value!=promotion_signature[0] for value in promotion_signature[1:]):
        raise RuntimeError('Language/worker setting changed the recorded promotion inputs')
    if any(row['input_routes']!=rows[0]['input_routes'] or row['action_records']!=rows[0]['action_records'] for row in rows[1:]):
        raise RuntimeError('Language/worker setting changed the SDK unit-action route or selected action')
    if any(row['command'][0]!=rows[0]['command'][0] or row['command'][2:]!=rows[0]['command'][2:] for row in rows[1:]):
        raise RuntimeError('Language/worker setting changed the host command')
    if any(digest(PROJECT / 'tools' / name) != value for name, value in before.items()):
        raise RuntimeError('A UI validator changed during verification')
    report = {'status': 'OFFICIAL_UI_POPUP_ACTUAL_SDK_LUA_RNG_PASS', 'runs': rows,
              'validators': [artifact(frozen / name) for name in names],
              'validator_inputs_unchanged': True, 'rng_transition_algorithm': 'CvRandom.cpp uint32 LCG',
              'fixture_promotions_enabled':args.fixture_promotions,
              'fixture_promotion_policy':'SHOCK_1_SHOCK_2_SHOCK_3_FIRST_LEGAL' if args.fixture_promotions else None,
              'fixture_unit_actions_enabled':args.fixture_unit_actions,
              'fixture_unit_actions_verified':args.fixture_unit_actions and all(row['fixture_unit_actions_verified'] for row in rows),
              'retail_event_timing_verified': False, 'renderer_verified': False,
              'native_ui_save_after_first_popup_restore_verified': False,
              'full_worker_archive_equivalence_certified_by_this_report': False,
              'scope': 'EXPLICIT_HEADLESS_RETAINED_BNW_RANKING_UI_AND_NATIVE_SDK_RNG_LIFECYCLE'}
    check_artifacts(report)
    target = output / 'conformance.json'
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    (ROOT / 'conformance.json').write_bytes(target.read_bytes())
    print(json.dumps({'status': report['status'], 'runs': len(rows), 'turns': rows[0]['final_turn'],
                      'popups_per_run': len(rows[0]['popups']), 'evidence': str(target)}))


if __name__ == '__main__':
    main()
