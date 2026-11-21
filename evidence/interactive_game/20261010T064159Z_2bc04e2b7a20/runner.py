"""Materialize a private continuous game and verify its posted HWND input path.

The smoke driver runs the same persistent loop as --play. It proves one bounded
select/move/explicit skip/normal turn/save/close sequence, not human acceptance,
retail renderer equivalence, selected mods, or a complete playable Civ V port.
"""
from __future__ import annotations

import argparse
import hashlib
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import uuid

from collect_baseline import PROJECT, digest
from probe_world_builder import artifact
from run_new_game_probe import verify_city_site_base, verify_found_value_base
from runtime_input_cache import materialize_immutable
from verify_world_builder_map_object import check_artifacts
from social_policy_tenet_timeline import verify_social_policy_tenet_timeline
from economic_overview_timeline import verify_economic_overview_timeline
from action_info_panel_timeline import verify_action_info_panel_timeline
from notification_panel_timeline import unexpected_input_rejection_lines, verify_notification_panel_timeline
from game_menu_timeline import verify_game_menu_timeline
from verify_interactive_decisions import (ORIGINAL_UNIT_PANEL_WORKER_STATUSES,
    verify_original_unit_panel_worker_profile, verify_unit_panel_integration)


def maximum_smoke_timeout(args) -> int:
    full_hud_worker = all(getattr(args, name, False) is True for name in (
        'smoke', 'decisions', 'research_tree', 'unit_actions', 'worker_build',
        'top_panel', 'action_info_panel', 'notification_panel'))
    return 900 if full_hud_worker or any(getattr(args, name, False) for name in (
        'trade_route', 'social_policy', 'economic_overview', 'game_menu')) else 300


def verify_social_policy_dispatch_timeline(text: str, tenet_profile: bool = False) -> tuple[bool, str | None]:
    """Validate posted keys, SDK command identity, and the modal lifecycle."""
    has_tenet_marker = re.search(r'^INTERACTIVE_SOCIAL_POLICY_TENET_FIXTURE=', text, re.M) is not None
    if has_tenet_marker != tenet_profile:
        return False, 'SocialPolicy request profile does not match the native tenet fixture marker'
    if has_tenet_marker:
        return verify_social_policy_tenet_timeline(text)
    fixtures = re.findall(r'^INTERACTIVE_SOCIAL_POLICY_FIXTURE=(FRESH|RESTORED)\|(\d+)\|(\d+)\|(\d+)\|(\d+)\|(\d+)$', text, re.M)
    if len(fixtures) != 1:
        return False, 'SocialPolicy must declare one explicit fresh or restored fixture scope'
    restored = fixtures[0][0] == 'RESTORED'
    grants = re.findall(r'^INTERACTIVE_SOCIAL_POLICY_CULTURE_FIXTURE=(\d+)\|(\d+)\|(\d+)\|(\d+)\|(\d+)$', text, re.M)
    if len(grants) != sum(line.startswith('INTERACTIVE_SOCIAL_POLICY_CULTURE_FIXTURE=') for line in text.splitlines()) or \
            (restored and grants) or (not restored and [int(g[0]) for g in grants] != [1, 2]):
        return False, 'SocialPolicy culture grants differ from its exact fresh-only fixture scope'
    action_pattern = r'^INTERACTIVE_SOCIAL_POLICY_ACTION=(\d+)\|([^|]+)\|(\d+)\|(\d+)\|(\d+)\|(-?\d+)$'
    actions = list(re.finditer(action_pattern, text, re.M))
    expected_stages = [1, 9, 10, 11, 12, 16, 17] if restored else [1, 2, 3, 4, 5, 7, 8, 9, 10, 11, 12, 16, 17]
    if [int(m[1]) for m in actions] != expected_stages:
        return False, 'SocialPolicy requires its exact fresh thirteen-action or restored seven-action sequence'
    rows = {int(m[1]): m for m in actions}
    branch, policy = (-1, -1) if restored else (int(rows[2][6]), int(rows[7][6]))
    expected_names = ['CultureString', 'TabButtonIdeologies', 'TabButtonSocialPolicies', 'PolicyInfo', 'CloseButton',
                      'CultureString', 'KEY_ESCAPE'] if restored else ['CultureString', f'BranchButton{branch}', 'No', f'BranchButton{branch}', 'Yes',
                      'PolicyIcon', 'Yes', 'TabButtonIdeologies', 'TabButtonSocialPolicies',
                      'PolicyInfo', 'CloseButton', 'CultureString', 'KEY_ESCAPE']
    if [m[2] for m in actions] != expected_names or (not restored and (branch < 0 or policy < 0 or int(rows[4][6]) != branch)):
        return False, 'SocialPolicy actions do not retain the original branch, policy, tab, or close IDs'
    if any(int(m[3]) <= 0 for m in actions) or int(rows[17][3]) != 27:
        return False, 'SocialPolicy action has a zero key or incorrect Escape virtual key'
    if any(int(b[4]) <= int(a[4]) or int(b[5]) <= int(a[5]) for a, b in zip(actions, actions[1:])):
        return False, 'SocialPolicy actions reuse or reverse scene generations/revisions'
    for stage in (1, 16):
        action = rows[stage]
        if not re.search(r'^INTERACTIVE_SMOKE_POSTED=' + action[4] + r'\|' + action[3] + r'\|\d+\|\d+$', text, re.M):
            return False, 'SocialPolicy CultureString was not posted to its actual HWND key'
    dispatches = list(re.finditer(
        r'^INTERACTIVE_SOCIAL_POLICY_INPUT=(\d+)\|(\d+)\|(-?\d+(?:\.\d+)?)\|([01])\|([01])\|([01])\|(\d+)\|([01])$', text, re.M))
    inner_stages = [stage for stage in expected_stages if stage not in (1, 16)]
    if len(dispatches) != len(inner_stages):
        return False, 'SocialPolicy native input count differs from its fresh or restored scope'
    turn = int(dispatches[0][7])
    if turn != int(fixtures[0][2]):
        return False, 'SocialPolicy input turn differs from its actual SDK fixture observation'
    for stage, event in zip(inner_stages, dispatches):
        action = rows[stage]
        wanted = (1 if stage == 17 else 2, int(action[3]), 0.0, 1,
                  0 if stage in (12, 17) else 1, 0 if stage in (12, 17) else 1,
                  turn, 1 if not restored and stage in (5, 8) else 0)
        actual = (int(event[1]), int(event[2]), float(event[3]), *map(int, event.group(4, 5, 6, 7, 8)))
        following = next((m.start() for m in actions if m.start() > action.start()), len(text))
        if actual != wanted or not action.start() < event.start() < following:
            return False, f'SocialPolicy stage {stage} did not dispatch its exact key, lifecycle, or command count'
        if stage != 17 and not re.search(r'^INTERACTIVE_SMOKE_POSTED=' + action[4] + r'\|' + action[3] + r'\|\d+\|\d+$', text, re.M):
            return False, f'SocialPolicy stage {stage} has no actual HWND post'
    commands = list(re.finditer(r'^INTERACTIVE_SOCIAL_POLICY_COMMAND=(\d+)\|(\d+)\|([01])\|([01])\|(\d+)$', text, re.M))
    expected_commands = [] if restored else [(branch, 0, 1, turn), (policy, 1, 1, turn)]
    if [tuple(map(int, m.group(2, 3, 4, 5))) for m in commands] != expected_commands:
        return False, 'SocialPolicy SDK commands did not adopt exactly the requested branch then policy'
    if any(int(m[1]) != int(fixtures[0][1]) for m in commands):
        return False, 'SocialPolicy SDK commands changed owner'
    for stage, command in zip((5, 8), commands):
        dispatch = dispatches[inner_stages.index(stage)]
        if not rows[stage].start() < command.start() < dispatch.start():
            return False, 'SocialPolicy SDK mutation escaped its confirmed native input interval'
    shown = re.findall(r'^INTERACTIVE_SOCIAL_POLICY_SHOWN=(\d+)\|(-?\d+)\|(-?\d+)\|(\d+)\|1$', text, re.M)
    suffix = 'RESTORED_POLICIES_UNCHANGED_AND_RETURN' if restored else 'TWO_PAID_ADOPTIONS_AND_RETURN'
    complete = re.findall(r'^INTERACTIVE_SOCIAL_POLICY_COMPLETE=(\d+)\|(\d+)\|' + suffix + '$', text, re.M)
    if len(shown) != 2 or shown[0] != shown[1] or int(shown[0][0]) != int(fixtures[0][1]) or int(shown[0][3]) != turn or \
            len(complete) != 1 or int(complete[0][1]) != turn or text.rfind('INTERACTIVE_SOCIAL_POLICY_COMPLETE=') < dispatches[-1].start():
        return False, 'SocialPolicy did not complete its original popup show, reopen, and return lifecycle'
    return True, None


def verify_social_policy_resume_source(result: dict) -> None:
    if result.get('social_policy_requested') is not True:
        if result.get('social_policy_tenets_requested') is True:
            raise RuntimeError('Resume source requests tenets without the SocialPolicy profile')
        return
    if result.get('social_policy_dispatch_verified') is not True or result.get('social_policy_sequence_verified') is not True:
        raise RuntimeError('Resume requires a completed SocialPolicy native input and SDK sequence')
    stdout = result.get('stdout', {})
    if not isinstance(stdout, dict) or not isinstance(stdout.get('path'), str) or \
            digest(Path(stdout['path'])) != stdout.get('sha256'):
        raise RuntimeError('Resume SocialPolicy stdout differs from its pinned artifact')
    text = Path(stdout['path']).read_text(encoding='utf8').replace('\r\n', '\n').replace('\r', '\n')
    tenet_profile = result.get('social_policy_tenets_requested', False)
    if type(tenet_profile) is not bool:
        raise RuntimeError('Resume SocialPolicy source has no explicit tenet profile value')
    verified, reason = verify_social_policy_dispatch_timeline(text, tenet_profile)
    if not verified:
        raise RuntimeError('Resume SocialPolicy source failed actual dispatch validation: ' + str(reason))


def verify_economic_overview_resume_source(result: dict) -> None:
    if result.get('economic_overview_requested') is not True:
        return
    if result.get('economic_overview_dispatch_verified') is not True or result.get('economic_overview_sequence_verified') is not True:
        raise RuntimeError('Resume requires the completed EconomicOverview input and production return sequence')
    stdout = result.get('stdout', {})
    if not isinstance(stdout, dict) or not isinstance(stdout.get('path'), str) or digest(Path(stdout['path'])) != stdout.get('sha256'):
        raise RuntimeError('Resume EconomicOverview stdout differs from its pinned artifact')
    text = Path(stdout['path']).read_text(encoding='utf8').replace('\r\n', '\n').replace('\r', '\n')
    verified, reason = verify_economic_overview_timeline(text)
    if not verified:
        raise RuntimeError('Resume EconomicOverview dispatch validation failed: ' + str(reason))


def verify_action_info_panel_resume_source(result: dict) -> None:
    requested = result.get('action_info_panel_requested', False)
    if type(requested) is not bool:
        raise RuntimeError('ActionInfoPanel source has an invalid requested profile')
    if not requested:
        return
    if result.get('action_info_panel_dispatch_verified') is not True or \
            result.get('action_info_panel_sequence_verified') is not True:
        raise RuntimeError('ActionInfoPanel reuse requires its completed native input and SDK sequence')
    stdout = result.get('stdout', {})
    if not isinstance(stdout, dict) or not isinstance(stdout.get('path'), str) or \
            digest(Path(stdout['path'])) != stdout.get('sha256'):
        raise RuntimeError('ActionInfoPanel source stdout differs from its pinned artifact')
    text = Path(stdout['path']).read_text(encoding='utf8').replace('\r\n', '\n').replace('\r', '\n')
    if result.get('status') in ORIGINAL_UNIT_PANEL_WORKER_STATUSES and \
            result.get('original_unit_panel_contract_required') is True:
        request_ref = result.get('request', {})
        check_artifacts(request_ref)
        request = json.loads(Path(request_ref['path']).read_text(encoding='utf8'))
        verify_original_unit_panel_worker_profile(request, result, text)
        return
    restored = result.get('status', '').endswith('_RESTORE_SMOKE_PASS')
    verified, reason = verify_action_info_panel_timeline(text, restored=restored)
    if not verified:
        raise RuntimeError('ActionInfoPanel source dispatch validation failed: ' + str(reason))

def verify_notification_panel_resume_source(result: dict) -> None:
    requested = result.get('notification_panel_requested', False)
    if type(requested) is not bool:
        raise RuntimeError('NotificationPanel source has an invalid requested profile')
    if not requested:
        return
    if result.get('notification_panel_native_sequence_verified') is not True or \
            result.get('notification_panel_sequence_verified') is not True:
        raise RuntimeError('NotificationPanel reuse requires its completed native input and SDK sequence')
    stdout = result.get('stdout', {})
    if not isinstance(stdout, dict) or not isinstance(stdout.get('path'), str) or \
            digest(Path(stdout['path'])) != stdout.get('sha256'):
        raise RuntimeError('NotificationPanel source stdout differs from its pinned artifact')
    text = Path(stdout['path']).read_text(encoding='utf8').replace('\r\n', '\n').replace('\r', '\n')
    restored = result.get('status', '').endswith('_RESTORE_SMOKE_PASS')
    verified, reason = verify_notification_panel_timeline(text, restored=restored)
    if not verified:
        raise RuntimeError('NotificationPanel source dispatch validation failed: ' + str(reason))


def verify_game_menu_resume_source(result: dict) -> None:
    requested = result.get('game_menu_requested', False)
    if type(requested) is not bool:
        raise RuntimeError('GameMenu source has an invalid requested profile')
    if not requested:
        return
    if result.get('game_menu_sequence_verified') is not True or result.get('game_menu_state_equal') is not True:
        raise RuntimeError('GameMenu reuse requires its native callbacks and observed state preservation')
    stdout = result.get('stdout', {})
    if not isinstance(stdout, dict) or not isinstance(stdout.get('path'), str) or \
            digest(Path(stdout['path'])) != stdout.get('sha256'):
        raise RuntimeError('GameMenu source stdout differs from its pinned artifact')
    verified, reason = verify_game_menu_timeline(Path(stdout['path']).read_text(encoding='utf8'))
    if not verified:
        raise RuntimeError('GameMenu source dispatch validation failed: ' + str(reason))
    states = result.get('game_menu_state_files', {})
    contents = []
    for phase in ('before', 'after'):
        ref = states.get(phase, {})
        if not isinstance(ref, dict) or not isinstance(ref.get('path'), str) or \
                digest(Path(ref['path'])) != ref.get('sha256'):
            raise RuntimeError('GameMenu source state file differs: ' + phase)
        contents.append(Path(ref['path']).read_bytes())
    if not contents[0] or contents[0] != contents[1]:
        raise RuntimeError('GameMenu source observed gameplay state changed')


def read_policy_info_options(resume: dict | None, user_settings: Path | None = None) -> dict:
    """Read existing settings; never write the user's INI or source session."""
    if user_settings is None:
        user_settings = Path(r"C:\Users\home\OneDrive\Documents\My Games\Sid Meier's Civilization 5\UserSettings.ini")
    original_bytes = user_settings.read_bytes()
    values = re.findall(r'^\s*PolicyInfo\s*=\s*([01])\s*$', original_bytes.decode('utf-8-sig'), re.M)
    if len(values) != 1:
        raise RuntimeError('Original UserSettings.ini must contain exactly one valid PolicyInfo value')
    original = source_annotation(user_settings)
    if hashlib.sha256(original_bytes).hexdigest() != original['sha256']:
        raise RuntimeError('Original UserSettings.ini changed while selecting its read-only option')
    if resume:
        checkpoint = Path(resume['checkpoint_source']['path']).resolve(strict=True)
        options = checkpoint.parent / 'ui-options.json'
        if options.exists():
            raw = options.read_bytes()
            value = json.loads(raw.decode('utf8'))
            if not isinstance(value, dict) or value.get('schema') != 'ZEROSIS_UI_OPTIONS_V1' or type(value.get('policyInfo')) is not bool:
                raise RuntimeError('Checkpoint UI options have an invalid schema or PolicyInfo value')
            source = source_annotation(options)
            if hashlib.sha256(raw).hexdigest() != source['sha256']:
                raise RuntimeError('Checkpoint UI options changed while selecting the resumed option')
            return {'policy_info': int(value['policyInfo']), 'origin': 'RESUMED_SESSION_UI_OPTIONS',
                    'source': source, 'run_id': resume['run_id'], 'original_user_settings': original,
                    'original_policy_info': int(values[0])}
    return {'policy_info': int(values[0]), 'origin': 'ORIGINAL_USER_SETTINGS_READ_ONLY',
            'source': original, 'run_id': None, 'original_user_settings': original, 'original_policy_info': int(values[0])}


def verify_trade_route_dispatch_timeline(text: str) -> tuple[bool, str | None]:
    """Bind every posted TradeRoute callback to its actual Ui dispatch and modal lifecycle."""
    expected_actions = [
        (1, 'InternationalTradeRoutes'), (2, 'FromGPT'), (3, 'FromGPT'),
        (4, 'TabButtonAvailableTR'), (6, 'TabButtonTRWithYou'), (7, 'TabButtonYourTR'),
        (8, 'KEY_RETURN'), (9, 'CloseButton'), (10, 'InternationalTradeRoutes'), (11, 'KEY_ESCAPE')]
    actions = [tuple(row) for row in re.findall(
        r'^INTERACTIVE_TRADE_ROUTE_ACTION=(\d+)\|([^|]+)\|(-?\d+)\|(\d+)\|(\d+)$', text, re.M)]
    if [(int(row[0]), row[1]) for row in actions] != expected_actions:
        return False, 'TradeRoute posted action stages or targets differ from the required sequence'
    action_by_stage = {int(row[0]): int(row[2]) for row in actions}
    inputs = [tuple(row) for row in re.findall(
        r'^INTERACTIVE_TRADE_ROUTE_INPUT=(\d+)\|(\d+)\|(-?[0-9]+(?:\.[0-9]+)?)\|([01])\|([01])\|([01])\|STATE_UNCHANGED$', text, re.M)]
    if len(inputs) != 9:
        return False, f'TradeRoute must dispatch exactly nine inputs; observed {len(inputs)}'
    wheel = re.findall(r'^INTERACTIVE_TRADE_ROUTE_WHEEL=(\d+)\|(\d+)\|-120(?:\.0+)?$', text, re.M)
    if len(wheel) != 1:
        return False, f'TradeRoute must post exactly one native wheel event; observed {len(wheel)}'
    expected = [
        (2, action_by_stage[2], 0.0), (2, action_by_stage[3], 0.0),
        (2, action_by_stage[4], 0.0), (4, int(wheel[0][1]), 48.0),
        (2, action_by_stage[6], 0.0), (2, action_by_stage[7], 0.0),
        (1, 13, 0.0), (2, action_by_stage[9], 0.0), (1, 27, 0.0)]
    observed = [(int(kind), int(key), float(delta)) for kind, key, delta, *_ in inputs]
    if observed != expected:
        for index, (actual, wanted) in enumerate(zip(observed, expected), 1):
            if actual != wanted:
                return False, f'TradeRoute dispatch {index} was {actual}; expected posted target/kind/delta {wanted}'
        return False, 'TradeRoute dispatches differ from the posted callback sequence'
    lifecycle = [(int(consumed), int(active), int(timer)) for *_, consumed, active, timer in inputs]
    expected_lifecycle = [(1, 1, 1)] * 7 + [(1, 0, 0), (1, 0, 0)]
    if lifecycle != expected_lifecycle:
        for index, (actual, wanted) in enumerate(zip(lifecycle, expected_lifecycle), 1):
            if actual != wanted:
                return False, f'TradeRoute dispatch {index} lifecycle was {actual}; expected {wanted}'
        return False, 'TradeRoute modal lifecycle differs from the expected close and Escape sequence'
    action_positions = {int(row[0]): match.start() for row, match in zip(actions, re.finditer(
        r'^INTERACTIVE_TRADE_ROUTE_ACTION=', text, re.M))}
    input_positions = [match.start() for match in re.finditer(r'^INTERACTIVE_TRADE_ROUTE_INPUT=', text, re.M)]
    wheel_match = re.search(r'^INTERACTIVE_TRADE_ROUTE_WHEEL=', text, re.M)
    ordered = [action_positions[2], input_positions[0], action_positions[3], input_positions[1],
               action_positions[4], input_positions[2], wheel_match.start(), input_positions[3],
               action_positions[6], input_positions[4], action_positions[7], input_positions[5],
               action_positions[8], input_positions[6], action_positions[9], input_positions[7],
               action_positions[10], action_positions[11], input_positions[8]]
    if ordered != sorted(ordered):
        return False, 'TradeRoute dispatches do not follow their posted actions in the required order'
    return True, None


def verify_trade_route_resume_source(result: dict) -> None:
    """Reject old self-reported TradeRoute passes unless their pinned stdout revalidates."""
    if result.get('trade_route_requested') is not True:
        return
    if result.get('trade_route_dispatch_verified') is not True:
        raise RuntimeError('Resume requires TradeRoute source dispatch verification from the current runner')
    stdout = result.get('stdout')
    if not isinstance(stdout, dict) or not isinstance(stdout.get('path'), str):
        raise RuntimeError('Resume requires the TradeRoute source stdout artifact for dispatch revalidation')
    try:
        text = Path(stdout['path']).read_text(encoding='utf8').replace('\r\n', '\n').replace('\r', '\n')
    except (OSError, UnicodeError) as exc:
        raise RuntimeError(f'Resume cannot read TradeRoute source stdout for dispatch revalidation: {exc}') from exc
    verified, reason = verify_trade_route_dispatch_timeline(text)
    if not verified:
        raise RuntimeError('Resume TradeRoute source stdout failed dispatch revalidation: ' + str(reason))


def verify_trade_route_ui_support_source(result: dict) -> None:
    """Require a fresh, fully verified TradeRoute tree run before reusing UI support."""
    if result.get('trade_route_requested') is not True or \
            result.get('trade_route_sequence_verified') is not True or \
            result.get('trade_route_dispatch_verified') is not True:
        raise RuntimeError('Fresh TradeRoute UI support source lacks its requested, sequence, or dispatch proof')
    verify_trade_route_resume_source(result)


def materialize_checkpoint(run_id: str, build: dict, runtime: Path, evidence: Path) -> dict:
    if not re.fullmatch(r'[0-9]{8}T[0-9]{6}Z_[0-9a-f]{12}', run_id):
        raise ValueError('Resume run must be an immutable interactive run identity')
    source_result = PROJECT / 'evidence/interactive_game' / run_id / 'result.json'
    result = json.loads(source_result.read_text(encoding='utf8'))
    accepted = {'CONTINUOUS_INTERACTIVE_SDK_WINDOW_SMOKE_PASS', 'CONTINUOUS_INTERACTIVE_SDK_WINDOW_RESTORE_SMOKE_PASS',
                'CONTINUOUS_INTERACTIVE_SDK_DECISION_UI_SMOKE_PASS', 'CONTINUOUS_INTERACTIVE_SDK_DECISION_UI_RESTORE_SMOKE_PASS',
                'CONTINUOUS_INTERACTIVE_SDK_TREE_DECISION_UI_SMOKE_PASS', 'CONTINUOUS_INTERACTIVE_SDK_TREE_DECISION_UI_RESTORE_SMOKE_PASS',
                'CONTINUOUS_INTERACTIVE_SDK_TECH_AWARD_SMOKE_PASS', 'CONTINUOUS_INTERACTIVE_SDK_TECH_AWARD_RESTORE_SMOKE_PASS',
                'CONTINUOUS_INTERACTIVE_SDK_WORKER_BUILD_SMOKE_PASS', 'CONTINUOUS_INTERACTIVE_SDK_WORKER_BUILD_RESTORE_SMOKE_PASS',
                'CONTINUOUS_INTERACTIVE_SDK_COMBAT_SMOKE_PASS', 'CONTINUOUS_INTERACTIVE_SDK_CITY_CAPTURE_SMOKE_PASS',
                'CONTINUOUS_INTERACTIVE_SDK_DECLARE_WAR_MOVE_SMOKE_PASS',
                'CONTINUOUS_INTERACTIVE_SDK_DECLARE_WAR_RANGE_SMOKE_PASS'}
    if result.get('status') not in accepted or result.get('returncode') != 0 or not result.get('runtime_inputs_unchanged'):
        raise RuntimeError('Resume requires a successfully completed private interactive run')
    check_artifacts(result)
    verify_trade_route_resume_source(result)
    verify_social_policy_resume_source(result)
    verify_economic_overview_resume_source(result)
    verify_action_info_panel_resume_source(result)
    verify_notification_panel_resume_source(result)
    verify_game_menu_resume_source(result)
    request = json.loads(Path(result['request']['path']).read_text(encoding='utf8'))
    check_artifacts(request)
    source_tenets = result.get('social_policy_tenets_requested', False)
    if type(source_tenets) is not bool or request.get('social_policy_tenets', False) is not source_tenets:
        raise RuntimeError('Checkpoint request and result disagree on the SocialPolicy tenet profile')
    source_economic = result.get('economic_overview_requested', False)
    if type(source_economic) is not bool or request.get('economic_overview_smoke', False) is not source_economic:
        raise RuntimeError('Checkpoint request and result disagree on the EconomicOverview profile')
    source_notification = result.get('notification_panel_requested', False)
    if type(source_notification) is not bool or request.get('notification_panel', False) is not source_notification:
        raise RuntimeError('Checkpoint request and result disagree on the NotificationPanel profile')
    source_game_menu = result.get('game_menu_requested', False)
    if type(source_game_menu) is not bool or request.get('game_menu_smoke', False) is not source_game_menu:
        raise RuntimeError('Checkpoint request and result disagree on the GameMenu profile')
    source_action_info = result.get('action_info_panel_requested', False)
    if type(source_action_info) is not bool or request.get('action_info_panel', False) is not source_action_info:
        raise RuntimeError('Checkpoint request and result disagree on the ActionInfoPanel profile')
    if source_action_info and result.get('action_info_panel_sequence_verified') is not True:
        raise RuntimeError('ActionInfoPanel checkpoint requires its complete native input sequence')
    source_runtime = (PROJECT / 'Build/InteractiveGameRuntime' / run_id).resolve(strict=True)
    if Path(request['cwd']).resolve(strict=True) != source_runtime or request.get('run_id') != run_id:
        raise RuntimeError('Checkpoint source runtime identity differs')
    for row in request['runtime_inputs']:
        path = Path(row['path']).resolve(strict=True)
        if path.parent != source_runtime or digest(path) != row['sha256']:
            raise RuntimeError('Checkpoint source runtime input escaped or changed from its immutable inventory')
    expected_manifest = 'ZEROSIS_HOST_BUNDLE_V4\n' + ''.join(Path(row['path']).name + '|' + row['sha256'] + '\n'
        for row in request['runtime_inputs'] if Path(row['path']).name != 'bundle.manifest')
    if (source_runtime / 'bundle.manifest').read_text(encoding='ascii') != expected_manifest:
        raise RuntimeError('Checkpoint source manifest differs from its actual runtime input inventory')
    host_rows = [row for row in request['runtime_inputs'] if Path(row['path']).name == 'ZeroSisHost_x64.exe']
    if len(host_rows) != 1 or host_rows[0]['sha256'] != build['executable']['sha256']:
        raise RuntimeError('Resume requires the exact sealed Host that wrote the native save; no bundle migration is applied')
    if digest(source_runtime / 'bundle.manifest') != digest(runtime / 'bundle.manifest'):
        raise RuntimeError('Resume requires the exact engine bundle, rules and providers that wrote the native save')
    output = Path(result['stdout']['path']).read_text(encoding='utf8').replace('\r\n', '\n').replace('\r', '\n')
    saves = re.findall(r'^INTERACTIVE_NATIVE_SAVE=(\d+)\|(.+)$', output, re.M)
    turns = result.get('next_human_turn', [])
    worker_source = result.get('worker_build_requested') is True and result.get('worker_build_sequence_verified') is True
    if len(saves) < 2 or not turns or (not worker_source and len(turns) != 1):
        raise RuntimeError('Checkpoint source did not complete its save and normal close sequence')
    turn = int(saves[-1][0])
    if turn != int(turns[-1][0]):
        raise RuntimeError('Checkpoint source turn differs from its final human turn')
    checkpoint = Path(saves[-1][1]).resolve(strict=True)
    state = checkpoint.parent / 'play-final-state.txt'
    inventory = {str(Path(row['path']).resolve(strict=True)): row for row in result['generated_files']}
    for path in (checkpoint, state):
        if not path.is_relative_to((source_runtime / 'sessions').resolve(strict=True)) or str(path) not in inventory or \
                digest(path) != inventory[str(path)]['sha256']:
            raise RuntimeError('Resume source escaped or differs from its final private-session inventory')
    local_checkpoint, expected_state, prior_result = runtime / 'checkpoint-input.zssave', evidence / 'checkpoint-state.txt', evidence / 'resume-source-result.json'
    for source, target in ((checkpoint, local_checkpoint), (state, expected_state), (source_result, prior_result)):
        shutil.copy2(source, target)
        if digest(source) != digest(target):
            raise RuntimeError('Resume provenance changed during checkpoint materialization')
    return {'run_id': run_id, 'run_result': artifact(prior_result), 'checkpoint_source': artifact(checkpoint),
            'checkpoint_input': artifact(local_checkpoint), 'expected_state': artifact(expected_state),
            'checkpoint_source_state': artifact(state), 'turn': turn,
            'social_policy_tenets_requested': source_tenets, 'economic_overview_requested': source_economic,
            'action_info_panel_requested': source_action_info, 'notification_panel_requested': source_notification,
            'game_menu_requested': source_game_menu}


def source_annotation(path: Path) -> dict:
    """Record mutable source provenance without making future resume depend on it."""
    path = Path(path).resolve(strict=True)
    return {'original_path': str(path), 'sha256': digest(path), 'bytes': path.stat().st_size}


def checked_unit_package(path: Path, expected_sha256: str | None = None,
                         expected_bytes: int | None = None) -> dict:
    """Validate the package identity and Civ V unit package header before copying."""
    path = Path(path)
    if not path.is_file():
        raise RuntimeError('Unit asset package path is not a regular file: ' + str(path))
    size = path.stat().st_size
    if size < 20 or size > 64 * 1024 * 1024:
        raise RuntimeError('Unit asset package must be between 20 bytes and 64 MiB')
    sha256 = digest(path)
    expected_header = b'ZSUNIT01' + (1).to_bytes(4, 'little')
    with path.open('rb') as stream:
        header = stream.read(len(expected_header))
    if size < len(expected_header) or header not in (expected_header, b'ZSUNIT02' + (2).to_bytes(4, 'little')):
        raise RuntimeError('Unit asset package does not have a supported v1/v2 header')
    if expected_sha256 is not None and sha256 != expected_sha256:
        raise RuntimeError('Unit asset package SHA-256 differs from its manifest')
    if expected_bytes is not None and size != expected_bytes:
        raise RuntimeError('Unit asset package byte count differs from its manifest')
    return {'path': str(path.absolute()), 'sha256': sha256, 'bytes': size}


def read_unit_assets_manifest(path: Path) -> tuple[dict, dict]:
    """Read a complete PASS manifest and verify its declared package against disk."""
    manifest_path = Path(path)
    if not manifest_path.is_file():
        raise RuntimeError('Unit asset manifest path is not a regular file: ' + str(manifest_path))
    manifest = json.loads(manifest_path.read_text(encoding='utf8'))
    if not isinstance(manifest, dict):
        raise RuntimeError('Unit asset manifest root must be a JSON object')
    package = manifest.get('package')
    if manifest.get('status') != 'PASS_ORIGINAL_UNIT_PACKAGE' or not isinstance(package, dict):
        raise RuntimeError('Unit asset manifest is incomplete or not PASS_ORIGINAL_UNIT_PACKAGE')
    package_path, expected_hash, expected_bytes = package.get('path'), package.get('sha256'), package.get('bytes')
    if not isinstance(package_path, str) or not package_path.strip():
        raise RuntimeError('Unit asset manifest has no package path')
    if not Path(package_path).is_absolute():
        raise RuntimeError('Unit asset manifest package path must be absolute')
    if not isinstance(expected_hash, str) or not re.fullmatch(r'[0-9a-f]{64}', expected_hash):
        raise RuntimeError('Unit asset manifest has an invalid package SHA-256')
    if isinstance(expected_bytes, bool) or not isinstance(expected_bytes, int) or not 20 <= expected_bytes <= 64 * 1024 * 1024:
        raise RuntimeError('Unit asset manifest has an invalid package byte count')
    observed = checked_unit_package(Path(package_path), expected_hash, expected_bytes)
    return {'path': str(manifest_path.resolve(strict=True)), 'sha256': digest(manifest_path),
            'bytes': manifest_path.stat().st_size}, observed


def resume_unit_assets(run_id: str) -> dict | None:
    """Recover a previously sealed package input for exact same-hash resume."""
    if not re.fullmatch(r'[0-9]{8}T[0-9]{6}Z_[0-9a-f]{12}', run_id):
        raise ValueError('Resume run must be an immutable interactive run identity')
    result_path = PROJECT / 'evidence/interactive_game' / run_id / 'result.json'
    result = json.loads(result_path.read_text(encoding='utf8'))
    check_artifacts(result)
    request_ref = result.get('request')
    if not isinstance(request_ref, dict) or not isinstance(request_ref.get('path'), str):
        raise RuntimeError('Resume source has no sealed interactive request')
    request = json.loads(Path(request_ref['path']).read_text(encoding='utf8'))
    check_artifacts(request)
    record = request.get('unit_assets')
    if record is None:
        return None
    if not isinstance(record, dict) or record.get('status') != 'PASS_ORIGINAL_UNIT_PACKAGE':
        raise RuntimeError('Resume source unit-assets record is not a passing original package')
    package = record.get('package')
    if not isinstance(package, dict):
        raise RuntimeError('Resume source unit-assets record has no package artifact')
    if not isinstance(package.get('sha256'), str) or not re.fullmatch(r'[0-9a-f]{64}', package['sha256']) or \
            isinstance(package.get('bytes'), bool) or not isinstance(package.get('bytes'), int):
        raise RuntimeError('Resume source unit-assets package identity is incomplete')
    package_path = Path(package.get('path', '')).resolve(strict=True)
    source_runtime = (PROJECT / 'Build/InteractiveGameRuntime' / run_id).resolve(strict=True)
    if package_path.parent != source_runtime:
        raise RuntimeError('Resume unit-assets package escaped its sealed source runtime')
    verified = checked_unit_package(package_path, package.get('sha256'), package.get('bytes'))
    rows = [row for row in request.get('runtime_inputs', []) if isinstance(row, dict) and
            Path(row.get('path', '')).resolve(strict=True) == package_path]
    if len(rows) != 1 or rows[0].get('sha256') != verified['sha256'] or rows[0].get('bytes') != verified['bytes']:
        raise RuntimeError('Resume unit-assets package is absent from the source runtime inventory')
    return {'package_source': package_path, 'package': verified,
            'manifest': record.get('manifest'), 'prior_run_id': run_id,
            'prior_request': request_ref, 'animation_runtime': record.get('animation_runtime')}


def frozen_ui_support_source(run_id: str) -> dict:
    """Validate and describe the immutable UI support snapshot from a passing run."""
    if not re.fullmatch(r'[0-9]{8}T[0-9]{6}Z_[0-9a-f]{12}', run_id):
        raise ValueError('UI support source must be an immutable interactive run identity')
    source_evidence = PROJECT / 'evidence/interactive_game' / run_id
    result_path = source_evidence / 'result.json'
    result = json.loads(result_path.read_text(encoding='utf8'))
    accepted = {
        'CONTINUOUS_INTERACTIVE_SDK_DECLARE_WAR_MOVE_SMOKE_PASS',
        'CONTINUOUS_INTERACTIVE_SDK_TREE_DECISION_UI_RESTORE_SMOKE_PASS',
        'CONTINUOUS_INTERACTIVE_SDK_TREE_DECISION_UI_SMOKE_PASS',
        'CONTINUOUS_INTERACTIVE_SDK_DECISION_UI_SMOKE_PASS',
        'CONTINUOUS_INTERACTIVE_SDK_DECISION_UI_RESTORE_SMOKE_PASS',
    } | ORIGINAL_UNIT_PANEL_WORKER_STATUSES
    fresh_tree = result.get('status') == 'CONTINUOUS_INTERACTIVE_SDK_TREE_DECISION_UI_SMOKE_PASS'
    if result.get('status') not in accepted or result.get('returncode') != 0 or \
            result.get('timed_out') is not False or result.get('runtime_inputs_unchanged') is not True or \
            result.get('failures'):
        raise RuntimeError('UI support requires a fully passing accepted smoke profile')
    if result.get('status') in {'CONTINUOUS_INTERACTIVE_SDK_DECISION_UI_SMOKE_PASS',
                               'CONTINUOUS_INTERACTIVE_SDK_DECISION_UI_RESTORE_SMOKE_PASS'} and \
            result.get('social_policy_requested') is not True and result.get('action_info_panel_requested') is not True:
        raise RuntimeError('Decision-only UI support reuse requires a verified SocialPolicy or ActionInfoPanel profile')
    request_path = source_evidence / 'request.json'
    request = json.loads(request_path.read_text(encoding='utf8'))
    check_artifacts(result)
    verify_action_info_panel_resume_source(result)
    verify_notification_panel_resume_source(result)
    verify_game_menu_resume_source(result)
    if request.get('game_menu_smoke', False) is not result.get('game_menu_requested', False):
        raise RuntimeError('Frozen GameMenu support source request differs from its result')
    if result.get('social_policy_requested') is True:
        verify_social_policy_resume_source(result)
    elif result.get('economic_overview_requested') is True:
        verify_economic_overview_resume_source(result)
    elif fresh_tree and result.get('action_info_panel_requested') is not True:
        verify_trade_route_ui_support_source(result)
    check_artifacts(request)
    if result.get('status') in ORIGINAL_UNIT_PANEL_WORKER_STATUSES:
        verify_original_unit_panel_worker_profile(request, result,
            Path(result['stdout']['path']).read_text(encoding='utf8'))
    result_request = result.get('request', {})
    if Path(result_request.get('path', '')).resolve(strict=True) != request_path.resolve(strict=True) or \
            result_request.get('sha256') != digest(request_path):
        raise RuntimeError('UI support source request differs from its passing result artifact')
    if request.get('run_id') != run_id or request.get('smoke') is not True:
        raise RuntimeError('UI support source request is not the selected successful smoke run')
    source_runtime = (PROJECT / 'Build/InteractiveGameRuntime' / run_id).resolve(strict=True)
    if Path(request.get('cwd', '')).resolve(strict=True) != source_runtime:
        raise RuntimeError('UI support source request escaped its immutable runtime')
    runtime_rows = request.get('runtime_inputs', [])
    runtime_names = [Path(row.get('path', '')).name for row in runtime_rows if isinstance(row, dict)]
    if len(runtime_names) != len(set(runtime_names)):
        raise RuntimeError('UI support source request has duplicate runtime input names')
    for row in runtime_rows:
        source_input = Path(row.get('path', '')).resolve(strict=True)
        if source_input.parent != source_runtime or digest(source_input) != row.get('sha256'):
            raise RuntimeError('UI support source runtime input escaped or changed from its sealed request')
    required_runtime_inputs = {
        'unit-assets.bin': '480678966a78bedbee642040285010aa86f8a2cc34b0929c2774dcee8ab54266',
        'unitmodels_stringdatabase.gsd': 'f063955e71728fc76fdc097b9759e291f203c895d32f5f6eeaf5e4f78f73a959',
        'Warrior_V2.gr2': '6101693ea454cbdfe1a026903fd30ca6489596a462994eddc21465f8b3740272',
        'Warrior.gr2': '9d34effba92d5dcc4340951bce65a08d620af2ee688cabf60d0bab8464ac0429',
        'Warrior_V4.gr2': '524fe9979ce361e8e486b49dff6fcc8e145dae268a26003aac0adb23bd52728d',
        'Warrior_IdleA.gr2': '7a6bde9dbb15f0916a920119774c1e803c92677660119c69c5d0bd32bee0cd88',
        'ZeroSisGrannyAnimationBridge.dll': '8b2c48b9a19230067771ee8dbce7949ec448ecee4453200d8c8eac0995fe9909',
        'Firaxis.Framework.dll': 'a1b9d304ba52fbf27d8c71c9fef3ff18b37581613b11d6da3f6f3e4d7daf7c86',
        'Firaxis.Framework.Granny.dll': '426c993ca193894cd6446f8ca1d04b98075febe4582fa14f37456e1ab6c62d68',
        'Firaxis.Framework.FirePlace.dll': '88b00a98551134b283e4a5e9c1343dfc339aa6eef6c6da55fe2c57878adde498',
        'Firaxis.Framework.Granny.Implx64.dll': 'b73252c3783216b41b6926d188be77f6cc27e069fa29e978dad17fdb9ccb24d6',
    }
    input_hashes = {Path(row['path']).name: row.get('sha256') for row in request.get('runtime_inputs', [])
                    if isinstance(row, dict) and isinstance(row.get('path'), str)}
    unit_record = request.get('unit_assets')
    unit_package_sha256 = None
    if 'unit_assets' in request and unit_record is None:
        if set(required_runtime_inputs) & set(input_hashes):
            raise RuntimeError('UI support without unit assets has unexpected partial unit/animation inputs')
    else:
        if any(input_hashes.get(name) != sha256 for name, sha256 in required_runtime_inputs.items()):
            raise RuntimeError('UI support source does not contain the complete verified original unit/animation inputs')
        if not isinstance(unit_record, dict) or unit_record.get('status') != 'PASS_ORIGINAL_UNIT_PACKAGE' or \
                unit_record.get('package', {}).get('sha256') != required_runtime_inputs['unit-assets.bin']:
            raise RuntimeError('UI support source lacks the required original unit-assets package provenance')
        unit_package_sha256 = required_runtime_inputs['unit-assets.bin']

    support_record_path = source_evidence / 'interactive_ui_support.json'
    support_record = json.loads(support_record_path.read_text(encoding='utf8'))
    check_artifacts(support_record)
    request_support = request.get('interactive_ui_support', {})
    if Path(request_support.get('path', '')).resolve(strict=True) != support_record_path.resolve(strict=True) or \
            request_support.get('sha256') != digest(support_record_path):
        raise RuntimeError('UI support record differs from the successful run request')
    inventory = request.get('interactive_ui_support_inventory', {})
    required_tools = ('interactive_ui_driver.py', 'render_ui_popup.py', 'ui_pixel_scene.py',
                      'ui_bitmap_fonts.py', 'civ5_ui_assets.py')
    tool_rows = support_record.get('tools', {})
    if set(tool_rows) != set(required_tools) or set(inventory.get('tools', {})) != set(required_tools):
        raise RuntimeError('UI support source has a missing or unexpected required tool')
    support_root = (source_runtime / 'interactive_ui_support').resolve(strict=True)
    verified = {}
    for name in required_tools:
        record_row = tool_rows[name]
        frozen = record_row.get('frozen', {})
        request_frozen = inventory['tools'][name].get('frozen', {})
        source = Path(frozen.get('path', '')).resolve(strict=True)
        if not source.is_relative_to(support_root / 'tools') or source.name != name or \
                frozen.get('sha256') != request_frozen.get('sha256') or digest(source) != frozen.get('sha256'):
            raise RuntimeError('Frozen UI tool is missing, escaped, or differs from its successful-run record: ' + name)
        verified[name] = {'path': source, 'sha256': frozen['sha256'], 'bytes': source.stat().st_size,
                          'record_source': record_row.get('source')}

    for key, filename in (('inline_icons', 'inline_icons.json'),
                          ('asset_preparation_provenance', 'prepared.json')):
        row = support_record.get(key, {})
        request_row = inventory.get(key, {})
        frozen = row.get('frozen', {})
        request_frozen = request_row.get('frozen', {})
        source = Path(frozen.get('path', '')).resolve(strict=True)
        if not source.is_relative_to(support_root / 'assets') or source.name != filename or \
                frozen.get('sha256') != request_frozen.get('sha256') or digest(source) != frozen.get('sha256'):
            raise RuntimeError('Frozen UI catalog/provenance is missing, escaped, or changed: ' + filename)
        verified[key] = {'path': source, 'sha256': frozen['sha256'], 'bytes': source.stat().st_size,
                         'record_source': row.get('source')}
    support_manifest_record = support_record.get('frozen_support_manifest', {})
    request_manifest = inventory.get('frozen_support_manifest', {})
    manifest_path = Path(support_manifest_record.get('path', '')).resolve(strict=True)
    if not manifest_path.is_relative_to(support_root) or manifest_path.name != 'support_manifest.json' or \
            support_manifest_record.get('sha256') != request_manifest.get('sha256') or \
            digest(manifest_path) != support_manifest_record.get('sha256'):
        raise RuntimeError('Frozen UI support manifest is missing, escaped, or changed')
    manifest = json.loads(manifest_path.read_text(encoding='utf8'))
    if set(manifest.get('tools', {})) != set(required_tools):
        raise RuntimeError('Frozen UI support manifest omits a required tool')
    for name, row in verified.items():
        manifest_key = name if name in required_tools else (
            'inline_icons' if name == 'inline_icons' else 'asset_preparation_provenance')
        manifest_entry = manifest['tools'][name] if name in required_tools else manifest.get(manifest_key, {})
        if manifest_entry.get('sha256') != row['sha256']:
            raise RuntimeError('Frozen UI support manifest digest differs: ' + name)
    profile = support_record.get('sdk_session_profile', {})
    if profile.get('ZEROSIS_UI_SMALL_ASSETS') != '1':
        raise RuntimeError('Frozen UI support source has an unexpected SDK session profile')
    return {'run_id': run_id, 'status': result['status'], 'result_sha256': digest(result_path),
            'request_sha256': digest(request_path), 'support_record_sha256': digest(support_record_path),
            'host_sha256': input_hashes.get('ZeroSisHost_x64.exe'),
            'unit_package_sha256': unit_package_sha256,
            'action_info_panel_requested': result.get('action_info_panel_requested', False),
            'notification_panel_requested': result.get('notification_panel_requested', False),
            'game_menu_requested': result.get('game_menu_requested', False),
            'support_manifest_sha256': support_manifest_record['sha256'], 'files': verified,
            'sdk_session_profile': profile, 'manual_launcher_protocol': support_record.get('manual_launcher_protocol')}


def native_save_paths_valid(rows: list[tuple[str, str]], sessions: Path) -> bool:
    try:
        root = Path(sessions).resolve(strict=True)
        paths = [Path(path).resolve(strict=True) for _, path in rows]
        return bool(paths) and all(path.is_file() and path.is_relative_to(root) for path in paths)
    except (OSError, RuntimeError, ValueError):
        return False


def _combat_unit_rows(path: Path) -> dict[tuple[int, int], dict]:
    units = {}
    for line in path.read_text(encoding='utf8').splitlines():
        fields = line.split('|')
        if not fields or fields[0] != 'U':
            continue
        if len(fields) != 13:
            raise ValueError('Malformed U record in combat state snapshot')
        values = [int(value) for value in fields[1:12]]
        if not re.fullmatch(r'(?:[0-9a-f]{2})*', fields[12]):
            raise ValueError('Malformed script-data hex in combat state snapshot')
        owner, unit_id, unit_type, x, y, moves, damage, experience, level, activity, embarked = values
        key = (owner, unit_id)
        if key in units:
            raise ValueError('Duplicate unit identity in combat state snapshot')
        units[key] = {'type': unit_type, 'x': x, 'y': y, 'moves': moves, 'damage': damage,
                      'experience': experience, 'level': level, 'activity': activity,
                      'embarked': embarked, 'scriptdata_hex': fields[12]}
    return units


def _verify_world_posted_hit(scene_path: Path, scene: dict, key: int, post: list[str]) -> dict:
    """Resolve the actual client pixel through rectangle precedence or the GPU ID raster."""
    from verify_interactive_game import pixel_key
    x, y = int(post[2]) * 1.5, int(post[3]) * 1.5
    if not 0 <= x < 1920 or not 0 <= y < 1080:
        raise ValueError('World command client point is outside the owned 1280x720 window')
    top = next((h for h in reversed(scene.get('hits', [])) if isinstance(h, list) and len(h) == 5 and
                h[1] <= x < h[3] and h[2] <= y < h[4]), None)
    if top is not None:
        if top[0] != key:
            raise ValueError('World command bypassed an overlaid UI control')
        return {'surface': 'rectangle', 'logical': [x, y]}
    pick = scene_path.with_suffix('.pick')
    if scene.get('pixelHitFile') != pick.name or pixel_key(pick, scene, x, y) != key:
        raise ValueError('World command does not resolve to its captured frontmost terrain pixel')
    return {'surface': 'gpu-pixel', 'logical': [x, y], 'picking': artifact(pick)}


def verify_combat_smoke(text: str, posted: list[str], native_inputs: list[str], sessions: Path) -> dict:
    fixtures = [tuple(map(int, row)) for row in re.findall(
        r'^INTERACTIVE_COMBAT_FIXTURE=(\d+)\|(\d+)\|(\d+)\|(\d+)\|(\d+)\|(-?\d+)\|(-?\d+)$', text, re.M)]
    targets = [tuple(map(int, row)) for row in re.findall(
        r'^INTERACTIVE_COMBAT_TARGET=(\d+)\|(\d+)\|(\d+)\|(\d+)\|(\d+)$', text, re.M)]
    verified = [tuple(map(int, row)) for row in re.findall(
        r'^INTERACTIVE_COMBAT_VERIFIED=(\d+)\|(\d+)\|(\d+)\|(\d+)\|(\d+)\|(\d+)\|(\d+)$', text, re.M)]
    evidence = {'fixtures': fixtures, 'targets': targets, 'observations': verified,
                'state_files': {}, 'scene_files': {}, 'verified': False, 'failures': []}
    if len(fixtures) != 2 or len(targets) != 2 or len(verified) != 2:
        evidence['failures'].append('Combat protocol requires exactly two fixture, target, and verified markers')
        return evidence
    by_fixture = {row[0]: row for row in fixtures}
    by_target = {row[0]: row for row in targets}
    by_verified = {row[0]: row for row in verified}
    if set(by_fixture) != {0, 1} or set(by_target) != {0, 1} or set(by_verified) != {0, 1} or \
            len(by_fixture) != 2 or len(by_target) != 2 or len(by_verified) != 2:
        evidence['failures'].append('Combat marker kinds must be unique melee 0 and ranged 1')
        return evidence
    posted_rows = [row.split('|') for row in posted]
    input_rows = [row.split('|') for row in native_inputs]
    session_root = Path(sessions).resolve(strict=False)
    if not session_root.is_dir():
        evidence['failures'].append('Combat session directory was not created')
        return evidence
    for kind in (0, 1):
        fixture, target, result = by_fixture[kind], by_target[kind], by_verified[kind]
        _, attacker_owner, attacker_id, defender_owner, defender_id, target_x, target_y = fixture
        _, target_attacker_id, plot_index, hit_key, generation = target
        _, result_attacker_owner, result_attacker_id, result_defender_owner, result_defender_id, callback_delta, defender_alive = result
        if (target_attacker_id != attacker_id or result[:5] != fixture[:5] or callback_delta != 1 or
                defender_alive != (1 if kind == 0 else 0) or defender_owner != 63 or attacker_owner == defender_owner):
            evidence['failures'].append(f'Combat kind {kind} markers disagree with their required identities/outcome')
            continue
        before_matches = list(session_root.glob(f'*/play-combat-before-{kind}-state.txt'))
        after_matches = list(session_root.glob(f'*/play-combat-after-{kind}-state.txt'))
        if len(before_matches) != 1 or len(after_matches) != 1:
            evidence['failures'].append(f'Combat kind {kind} state snapshots are missing or ambiguous')
            continue
        before_path, after_path = before_matches[0].resolve(strict=True), after_matches[0].resolve(strict=True)
        if before_path.parent != after_path.parent or before_path.parent.parent != session_root:
            evidence['failures'].append(f'Combat kind {kind} state snapshots are outside one exact session directory')
            continue
        evidence['state_files'][str(kind)] = {'before': artifact(before_path), 'after': artifact(after_path)}
        try:
            before_units, after_units = _combat_unit_rows(before_path), _combat_unit_rows(after_path)
        except (OSError, UnicodeError, ValueError) as error:
            evidence['failures'].append(f'Combat kind {kind} state snapshot parse failed: {error}')
            continue
        attacker_key, defender_key = (attacker_owner, attacker_id), (defender_owner, defender_id)
        before_attacker, before_defender = before_units.get(attacker_key), before_units.get(defender_key)
        after_attacker, after_defender = after_units.get(attacker_key), after_units.get(defender_key)
        if not before_attacker or not before_defender or not after_attacker:
            evidence['failures'].append(f'Combat kind {kind} state snapshots lack the required surviving unit records')
            continue
        if kind == 0:
            # CvUnit::changeExperience explicitly rejects positive XP for
            # barbarians. The fixture resolves IsBarbarian in the real SDK;
            # this profile also requires the SDK's BARBARIAN_PLAYER slot 63.
            state_outcome = (after_defender is not None and after_attacker['damage'] > before_attacker['damage'] and
                after_defender['damage'] > before_defender['damage'] and
                after_attacker['experience'] > before_attacker['experience'] and
                after_defender['experience'] == before_defender['experience'])
        else:
            state_outcome = (after_defender is None and after_attacker['experience'] > before_attacker['experience'] and
                (after_attacker['moves'] < before_attacker['moves'] or after_attacker['moves'] == 0))
        if not state_outcome:
            evidence['failures'].append(f'Combat kind {kind} before/after SDK unit state does not match the required combat result')

        matching_scenes = []
        for scene_path in before_path.parent.glob('play-scene-*.json'):
            try:
                scene = json.loads(scene_path.read_text(encoding='utf8'))
            except (OSError, UnicodeError, json.JSONDecodeError):
                continue
            if scene.get('generation') == generation:
                matching_scenes.append((scene_path.resolve(strict=True), scene))
        if len(matching_scenes) != 1:
            evidence['failures'].append(f'Combat kind {kind} has no unique scene JSON for its target generation')
            continue
        scene_path, scene = matching_scenes[0]
        evidence['scene_files'][str(kind)] = artifact(scene_path)
        plots = scene.get('plots')
        plot_rows = [row for row in plots if type(row) is list and len(row) == 5 and row[0] == plot_index] if type(plots) is list else []
        expected_hit = 0x5A57000000000000 | (1 << 32) | plot_index
        hits = scene.get('hits')
        hit_rows = [row for row in hits if type(row) is list and len(row) == 5 and row[0] == hit_key] if type(hits) is list else []
        foreign = scene.get('visibleForeignUnits')
        defenders = [row for row in foreign if type(row) is dict and row.get('id') == defender_id and row.get('owner') == defender_owner] if type(foreign) is list else []
        owned = scene.get('units')
        attackers = [row for row in owned if type(row) is dict and row.get('id') == attacker_id and row.get('owner') == attacker_owner] if type(owned) is list else []
        scene_valid = (scene.get('activePlayer') == attacker_owner and scene.get('generation') == generation and
            hit_key == expected_hit and len(plot_rows) == 1 and plot_rows[0][1:3] == [target_x, target_y] and
            plot_rows[0][3:] == [1, 1] and len(hit_rows) <= 1 and len(defenders) == 1 and len(attackers) == 1)
        if scene_valid:
            defender = defenders[0]
            attacker = attackers[0]
            scene_valid = (defender.get('x') == target_x and defender.get('y') == target_y and
                type(defender.get('damage')) is int and type(defender.get('maxHitPoints')) is int and
                defender['maxHitPoints'] > 0 and defender['damage'] >= 0 and
                defender.get('hostile') is True and attacker.get('selected') is True and
                attacker.get('x') == before_attacker['x'] and attacker.get('y') == before_attacker['y'] and
                before_defender['x'] == target_x and before_defender['y'] == target_y and
                before_defender['damage'] == defender['damage'] and
                (kind != 1 or before_defender['damage'] == defender['maxHitPoints'] - 1))
        if not scene_valid:
            evidence['failures'].append(f'Combat kind {kind} scene does not expose the visible target, selected attacker, visible plot, and matching hit')

        posts = [row for row in posted_rows if len(row) == 4 and row[0] == str(generation) and row[1] == str(hit_key)]
        input_kind = '5' if 'INTERACTIVE_SMOKE_BUTTON=' in text else '1'
        if input_kind == '5' and text.splitlines().count(f'INTERACTIVE_SMOKE_BUTTON={generation}|{hit_key}|5|0') != 1:
            evidence['failures'].append(f'Combat kind {kind} lacks its exact posted right-button record')
        inputs = [row for row in input_rows if len(row) == 4 and row[0] == str(generation) and
                   row[1] == input_kind and row[2] == str(hit_key) and row[3] == '1']
        if len(posts) != 1 or len(inputs) != 1 or not posts[0][2].isdigit() or not posts[0][3].isdigit():
            evidence['failures'].append(f'Combat kind {kind} lacks one matching posted hit and accepted control-click input')
        else:
            try:
                evidence.setdefault('posted_hit_proofs', {})[str(kind)] = _verify_world_posted_hit(scene_path, scene, hit_key, posts[0])
            except (OSError, ValueError, RuntimeError) as error:
                evidence['failures'].append(f'Combat kind {kind} picking failed: {error}')

    evidence['verified'] = not evidence['failures']
    return evidence


def verify_declare_war_smoke(text: str, posted: list[str], native_inputs: list[str], ui_inputs: list[str], sessions: Path,
                            scene_requests: list[dict], mode: str) -> dict:
    """Bind No/Escape/Yes to original DeclareWarPopup targets and SDK state."""
    if mode not in ('move', 'range'):
        raise ValueError('Declare-war mode must be move or range')
    range_flag = 1 if mode == 'range' else 0
    fixtures = [tuple(map(int, row)) for row in re.findall(
        r'^INTERACTIVE_DECLARE_WAR_FIXTURE=([01])\|(-?\d+)\|(-?\d+)\|(-?\d+)\|(-?\d+)\|(-?\d+)\|(-?\d+)\|(-?\d+)$', text, re.M)]
    world_targets = [tuple(map(int, row)) for row in re.findall(
        r'^INTERACTIVE_DECLARE_WAR_WORLD_TARGET=(\d+)\|(-?\d+)\|(-?\d+)\|(\d+)\|(\d+)$', text, re.M)]
    choices = [tuple(map(int, row)) for row in re.findall(
        r'^INTERACTIVE_DECLARE_WAR_CHOICE=(\d+)\|(\d+)\|(\d+)\|(\d+)$', text, re.M)]
    rejected = [(int(row[0]), row[1], row[2]) for row in re.findall(
        r'^INTERACTIVE_DECLARE_WAR_REJECTED=(\d+)\|(STATE_UNCHANGED)\|(AT_PEACE)$', text, re.M)]
    verified_rows = [tuple(map(int, row)) for row in re.findall(
        r'^INTERACTIVE_DECLARE_WAR_VERIFIED=([01])\|(-?\d+)\|(-?\d+)\|(-?\d+)\|(-?\d+)\|(-?\d+)\|(-?\d+)\|(-?\d+)$', text, re.M)]
    inputs = [tuple(map(int, row)) for row in re.findall(
        r'^INTERACTIVE_DECLARE_WAR_INPUT=(-?\d+)\|(-?\d+)\|(-?\d+)\|(-?\d+)\|(-?\d+)\|(-?\d+)\|([01])$', text, re.M)]
    commands = [tuple(map(int, row)) for row in re.findall(
        r'^INTERACTIVE_DECLARE_WAR_COMMAND=(\d+)\|(-?\d+)\|(-?\d+)\|(-?\d+)\|(-?\d+)$', text, re.M)]
    confirmed = [tuple(map(int, row)) for row in re.findall(
        r'^INTERACTIVE_DECLARE_WAR_CONFIRMED=(-?\d+)\|(-?\d+)\|(-?\d+)\|(-?\d+)\|(-?\d+)\|([01])$', text, re.M)]
    observations = [tuple(map(int, row)) for row in re.findall(
        r'^INTERACTIVE_DECLARE_WAR_OBSERVATION=(\d+)\|(\d+)\|([01])\|([01])\|([01])\|([01])$', text, re.M)]
    escape_posts = [tuple(map(int, row)) for row in re.findall(
        r'^INTERACTIVE_DECLARE_WAR_POSTED_ESCAPE=(\d+)\|(\d+)$', text, re.M)]
    native_keys = [tuple(row) for row in re.findall(
        r'^INTERACTIVE_UI_NATIVE_KEY=(\d+)\|([^|]+)\|(\d+)\|([01])\|([01])$', text, re.M)]
    posted_rows = [row.split('|') for row in posted]
    ui_rows = [row.split('|') for row in ui_inputs]
    evidence = {'requested_mode': mode, 'fixture': fixtures, 'world_targets': world_targets,
                'choices': choices, 'rejected': rejected, 'verified_marker': verified_rows,
                'inputs': inputs, 'commands': commands, 'confirmed': confirmed,
                'observations': observations, 'posted_escape': escape_posts,
                'snapshots': {}, 'popup_scenes': [], 'world_scene_files': {}, 'posted_clicks': [],
                'native_inputs': [], 'validated': False, 'combat_callback_independently_verified': False,
                'failures': []}
    if not all(len(rows) == 1 for rows in (fixtures, verified_rows, confirmed)) or \
            len(world_targets) != 3 or len(choices) != 3 or len(rejected) != 2 or len(inputs) != 3:
        evidence['failures'].append('Declare-war protocol requires one fixture/confirmation/verification, three world targets/choices/inputs, and two cancellation records')
        return evidence
    fixture = fixtures[0]
    fixture_range, owner, unit, rival_player, rival_team, target_unit, x, y = fixture
    evidence['fixture'] = {'range': fixture_range, 'owner': owner, 'unit': unit,
                           'rival_player': rival_player, 'rival_team': rival_team,
                           'target_unit': target_unit, 'x': x, 'y': y}
    if fixture_range != range_flag or owner < 0 or unit < 0 or rival_player < 0 or \
            rival_team < 0 or target_unit < 0 or rival_player == owner or rival_team < 0:
        evidence['failures'].append('Declare-war fixture does not match the requested mode or has invalid identities')
    starts = [tuple(map(int, row)) for row in re.findall(
        r'^INTERACTIVE_GAME_STARTED=(\d+)\|(\d+)\|(\d+)\|(\d+)$', text, re.M)]
    if len(starts) != 1 or starts[0][1] != owner or x < 0 or y < 0 or \
            (len(starts) == 1 and (x >= starts[0][2] or y >= starts[0][3])):
        evidence['failures'].append('Declare-war fixture is outside the one active local human game and map bounds')
    by_attempt = {row[0]: row for row in world_targets}
    choice_by_attempt = {row[0]: row for row in choices}
    rejected_by_attempt = {row[0]: row for row in rejected}
    if set(by_attempt) != {0, 1, 2} or len(by_attempt) != 3 or \
            set(choice_by_attempt) != {0, 1, 2} or len(choice_by_attempt) != 3 or \
            set(rejected_by_attempt) != {0, 1} or len(rejected_by_attempt) != 2:
        evidence['failures'].append('Declare-war attempt ids must be exactly No=0, Escape=1, Yes=2')
        return evidence
    if [row[6] for row in inputs] != [range_flag] * 3 or any(
            row[:2] != (owner, unit) or row[3:] != (rival_team, x, y, range_flag)
            for row in inputs):
        evidence['failures'].append('The three original popup inputs do not retain one exact owner/unit/turn/rival/target fixture')
    if len({row[2] for row in inputs}) != 1 or (len(starts) == 1 and inputs[0][2] != starts[0][0]):
        evidence['failures'].append('The original DeclareWar popup did not stay on the fresh game turn')
    if by_attempt[0][1] != unit or by_attempt[1][1] != unit or by_attempt[2][1] != unit or \
            len({row[2] for row in world_targets}) != 1 or len({row[3] for row in world_targets}) != 1 or \
            len({row[4] for row in world_targets}) != 3:
        evidence['failures'].append('No/Escape/Yes world targets must reuse one selected unit/plot/hit and use three fresh generations')
    session_root = Path(sessions).resolve(strict=False)
    window_rows = [row.split('|') for row in native_inputs]
    for attempt in (0, 1, 2):
        target = by_attempt[attempt]
        world_posts = [row for row in posted_rows if len(row) == 4 and row[:2] == [str(target[4]), str(target[3])]]
        button_rows = [row for row in re.findall(
            r'^INTERACTIVE_SMOKE_BUTTON=(\d+)\|(\d+)\|(\d+)\|(\d+)$', text, re.M)
                       if row[:2] == (str(target[4]), str(target[3]))]
        world_inputs = [row for row in window_rows if len(row) == 4 and row[0] == str(target[4]) and
                        row[2] == str(target[3]) and row[3] == '1']
        if len(world_posts) != 1 or len(button_rows) != 1 or len(world_inputs) != 1 or \
                button_rows[0][2] != '5' or world_inputs[0][1] != '5':
            evidence['failures'].append(f'Declare-war world target {attempt} lacks one matching posted and consumed native map click')
        else:
            evidence['posted_clicks'].append({'attempt': attempt, 'generation': target[4], 'key': target[3],
                'button_kind': button_rows[0][2], 'posted': world_posts[0], 'native_input': world_inputs[0],
                'target': target})
            evidence['native_inputs'].append(world_inputs[0])
            matches = []
            if session_root.is_dir():
                for scene_path in session_root.glob('*/play-scene-*.json'):
                    try:
                        scene = json.loads(scene_path.read_text(encoding='utf8'))
                    except (OSError, UnicodeError, json.JSONDecodeError):
                        continue
                    if scene.get('generation') == target[4]:
                        matches.append((scene_path, scene))
            if len(matches) != 1:
                evidence['failures'].append(f'Declare-war world target {attempt} has no unique exact-generation world scene')
            else:
                scene_path, scene = matches[0]
                evidence['world_scene_files'][str(attempt)] = artifact(scene_path)
                plots = [row for row in scene.get('plots', []) if type(row) is list and len(row) == 5 and row[0] == target[2]]
                hit_key = 0x5A57000000000000 | (1 << 32) | target[2]
                hits = [row for row in scene.get('hits', []) if type(row) is list and len(row) == 5 and row[0] == target[3]]
                attackers = [row for row in scene.get('units', []) if type(row) is dict and
                             row.get('owner') == owner and row.get('id') == unit and row.get('selected') is True]
                defenders = [row for row in scene.get('visibleForeignUnits', []) if type(row) is dict and
                             row.get('owner') == rival_player and row.get('id') == target_unit]
                valid_scene = scene.get('generation') == target[4] and scene.get('activePlayer') == owner and \
                    target[3] == hit_key and len(plots) == 1 and plots[0][1:5] == [x, y, 1, 1] and \
                    len(hits) <= 1 and len(attackers) == len(defenders) == 1 and \
                    defenders[0].get('x') == x and defenders[0].get('y') == y and defenders[0].get('hostile') is False
                if not valid_scene:
                    evidence['failures'].append(f'Declare-war world target {attempt} scene does not show the selected unit and the exact visible peaceful rival unit/plot')
                else:
                    try:
                        evidence['posted_clicks'][-1]['world_hit_proof'] = _verify_world_posted_hit(
                            scene_path, scene, target[3], world_posts[0])
                    except (OSError, ValueError, RuntimeError) as error:
                        evidence['failures'].append(f'Declare-war world target {attempt} native right-click did not hit its exact unobscured original plot: {error}')
    if any(choice_by_attempt[n][1] != 0 or choice_by_attempt[n][3] <= 0 for n in (0, 2)) or \
            choice_by_attempt[1][1:3] != (27, 0) or choice_by_attempt[1][3] <= 0 or \
            len({row[3] for row in choices}) != 3:
        evidence['failures'].append('No/Yes must be original button clicks and Escape must be a native VK_ESCAPE keydown')
    if [row[0] for row in rejected] != [0, 1]:
        evidence['failures'].append('Only the No and Escape attempts may be rejected without mutation')
    if verified_rows[0] != fixture:
        evidence['failures'].append('The successful Declare-war marker disagrees with its fixture identities and target')
    expected_confirmed = (owner, unit, rival_team, x, y, range_flag)
    if confirmed[0] != expected_confirmed:
        evidence['failures'].append('Confirmed SDK war command does not match the selected unit and original popup target')

    popup_rows = [row for row in scene_requests if type(row) is dict and row.get('context') == 'declare-war']
    evidence['popup_scenes'] = popup_rows
    if len(popup_rows) != 3:
        evidence['failures'].append('No/Escape/Yes require exactly three original declare-war popup scene preparations')
    scene_by_sequence = {row.get('sequence'): row for row in popup_rows}
    if len(scene_by_sequence) != len(popup_rows):
        evidence['failures'].append('Declare-war popup scene sequence ids are duplicated')
    sdk_header = PROJECT / 'Source/SDK_BNW_x64/CvGameCoreDLLUtil/include/CvEnums.h'
    diplo_event = _sdk_enum_value(sdk_header, 'FromUIDiploEventTypes', 'FROM_UI_DIPLO_EVENT_HUMAN_DECLARES_WAR')
    push_mission = _sdk_enum_value(sdk_header, 'GameMessageTypes', 'GAMEMESSAGE_PUSH_MISSION')
    selection_mode = _sdk_enum_value(sdk_header, 'InterfaceModeTypes', 'INTERFACEMODE_SELECTION')
    expected_kinds = [(0, rival_team, 1, 0, 0)]
    if diplo_event is not None:
        expected_kinds.append((1, diplo_event, rival_player, 0, 0))
    else:
        evidence['failures'].append('Frozen SDK has no parsable human-declares-war event enum')
    if mode == 'move':
        expected_kinds.append((2, x, y, 0, 0))
    else:
        if push_mission is None or selection_mode is None:
            evidence['failures'].append('Frozen SDK has no parsable mission/interface enum')
        # MissionTypes are loaded from the actual SDK database. The real Host
        # validates the resolved mission symbol; this runner binds message,
        # map target, and zero auxiliary fields without inventing an enum.
        mission_commands = [row for row in commands if row[0] == 3]
        expected_kinds.append((3, push_mission if push_mission is not None else -1,
                               mission_commands[0][2] if len(mission_commands) == 1 else -1, x, y))
        if selection_mode is not None:
            expected_kinds.append((4, selection_mode, 0, 0, 0))
    if commands != expected_kinds:
        evidence['failures'].append('Successful original popup commands do not match the SDK ChangeWar/diplomacy/move-or-range order and exact tuples')
    if len(confirmed) != 1 or (mode == 'move' and len(commands) != 3) or \
            (mode == 'range' and len(commands) != 4):
        evidence['failures'].append('The successful callback did not emit one complete command batch before confirmation')
    lines = text.splitlines()
    def marker_line(prefix: str, attempt: int | None = None) -> int:
        matches = [index for index, line in enumerate(lines) if line.startswith(prefix) and
                   (attempt is None or line.startswith(prefix + str(attempt) + '|'))]
        return matches[0] if len(matches) == 1 else -1
    command_positions = [index for index, line in enumerate(lines)
                         if line.startswith('INTERACTIVE_DECLARE_WAR_COMMAND=')]
    order = [marker_line('INTERACTIVE_DECLARE_WAR_CHOICE=', attempt) for attempt in (0, 1, 2)] + \
        [marker_line('INTERACTIVE_DECLARE_WAR_REJECTED=', attempt) for attempt in (0, 1)] + \
        [command_positions[0] if command_positions else -1, marker_line('INTERACTIVE_DECLARE_WAR_CONFIRMED='),
         marker_line('INTERACTIVE_DECLARE_WAR_VERIFIED=')]
    if len(command_positions) != len(commands) or any(index < 0 for index in order) or not (
            order[0] < order[3] < order[1] < order[4] < order[2] < order[5] < order[6] < order[7]):
        evidence['failures'].append('No, Escape, Yes, ordered SDK commands, confirmation, and final verification markers are out of order or ambiguous')

    if not session_root.is_dir():
        evidence['failures'].append('Declare-war private SDK session directory is missing')
        return evidence
    snapshots_by_attempt = {}
    for attempt in (0, 1, 2):
        before_paths = list(session_root.glob(f'*/play-declare-war-before-{attempt}-state.txt'))
        after_paths = list(session_root.glob(f'*/play-declare-war-after-{attempt}-state.txt'))
        if len(before_paths) != 1 or len(after_paths) != 1:
            evidence['failures'].append(f'Declare-war attempt {attempt} lacks one exact before/after SDK snapshot pair')
            continue
        before_path, after_path = before_paths[0].resolve(strict=True), after_paths[0].resolve(strict=True)
        if before_path.parent != after_path.parent or before_path.parent.parent != session_root:
            evidence['failures'].append(f'Declare-war attempt {attempt} snapshots escaped their exact private session')
            continue
        evidence['snapshots'][str(attempt)] = {'before': artifact(before_path), 'after': artifact(after_path)}
        before_bytes, after_bytes = before_path.read_bytes(), after_path.read_bytes()
        snapshots_by_attempt[attempt] = (before_bytes, after_bytes, before_path.parent)
        if attempt in (0, 1) and before_bytes != after_bytes:
            evidence['failures'].append(f'Declare-war cancellation attempt {attempt} changed the SDK state snapshot')
    if set(snapshots_by_attempt) == {0, 1, 2}:
        if len({row[2] for row in snapshots_by_attempt.values()}) != 1:
            evidence['failures'].append('Declare-war before/after snapshots do not belong to one exact SDK session')
        if snapshots_by_attempt[0][0] != snapshots_by_attempt[1][0] or \
                snapshots_by_attempt[0][0] != snapshots_by_attempt[2][0]:
            evidence['failures'].append('Each popup attempt must begin from the exact same fresh-game SDK state')
        try:
            before_path = next(iter(session_root.glob('*/play-declare-war-before-0-state.txt')))
            before_text = snapshots_by_attempt[0][0].decode('utf8')
            player_rows = {int(row[1]): row for row in
                (line.split('|') for line in before_text.splitlines() if line.startswith('P|')) if len(row) == 11}
            owner_row, rival_row = player_rows.get(owner), player_rows.get(rival_player)
            if not owner_row or not rival_row or int(owner_row[3]) != 1 or int(owner_row[4]) != 1 or \
                    int(rival_row[2]) != 1 or int(rival_row[3]) != 0 or \
                    int(rival_row[5]) != rival_team or int(owner_row[5]) == rival_team:
                evidence['failures'].append('The SDK snapshot does not bind the local human and living AI leader to distinct fixture teams')
            plot_rows = [line.split('|') for line in before_text.splitlines() if line.startswith('M|')]
            target_plot = [row for row in plot_rows if len(row) == 12 and int(row[1]) == by_attempt[0][2]]
            if len(target_plot) != 1 or (int(target_plot[0][2]), int(target_plot[0][3])) != (x, y):
                evidence['failures'].append('The world target plot index does not resolve to the fixture coordinates in the SDK snapshot')
            unit_rows = _combat_unit_rows(before_path)
            target_row = unit_rows.get((rival_player, target_unit))
            if not target_row or (target_row['x'], target_row['y']) != (x, y):
                evidence['failures'].append('The SDK snapshot does not contain the exact rival target unit at the fixture plot')
        except (OSError, UnicodeError, ValueError, StopIteration) as error:
            evidence['failures'].append(f'Declare-war fixture SDK identity snapshot could not be parsed: {error}')
    if mode == 'range' and session_root.is_dir():
        rules_paths = list(session_root.glob('*/rules.db'))
        if len(rules_paths) != 1:
            evidence['failures'].append('Range mission identity requires exactly one owning SDK rules database')
        else:
            try:
                rules_path = rules_paths[0].resolve(strict=True)
                if rules_path.parent.parent != session_root:
                    raise ValueError('rules database escaped its exact private session')
                connection = sqlite3.connect(rules_path.as_uri() + '?mode=ro', uri=True)
                try:
                    mission_rows = connection.execute(
                        'SELECT ID FROM Missions WHERE Type=?', ('MISSION_RANGE_ATTACK',)).fetchall()
                finally:
                    connection.close()
                mission_id = int(mission_rows[0][0]) if len(mission_rows) == 1 else None
                if mission_id is None or len(commands) < 3 or commands[2] != (3, push_mission, mission_id, x, y):
                    evidence['failures'].append('Range continuation tuple does not equal the owning SDK MISSION_RANGE_ATTACK rules row and original target')
                evidence['range_mission'] = {'id': mission_id, 'database': artifact(rules_path)}
            except (OSError, sqlite3.Error, ValueError, TypeError, IndexError) as error:
                evidence['failures'].append(f'Range continuation mission could not be verified against the owning SDK database: {error}')

    # Match every popup's original button IDs to its immutable SDK snapshot,
    # then bind its posted HWND click to one consumed native UI input.
    ui_frame_rows = [tuple(row.split('|')) for row in re.findall(
        r'^INTERACTIVE_UI_FRAME=(\d+\|\d+\|[^\r\n]+)$', text, re.M)]
    frame_by_sequence = {}
    for row in ui_frame_rows:
        frame_by_sequence.setdefault(int(row[0]), []).append(int(row[1]))
    target_keys = {}
    if len(popup_rows) == 3:
        for attempt, popup in enumerate(popup_rows):
            seq = popup.get('sequence')
            session = Path(popup.get('session', '')).resolve(strict=False)
            snapshot_path = session / f'play-ui-{seq}.json'
            try:
                snapshot = json.loads(snapshot_path.read_text(encoding='utf8'))
            except (OSError, UnicodeError, json.JSONDecodeError) as error:
                evidence['failures'].append(f'Declare-war popup snapshot {attempt} could not be read: {error}')
                continue
            if snapshot.get('contextName') != 'DeclareWarPopup' or snapshot.get('popupKind') != 'DeclareWar' or \
                    snapshot.get('active') is not True or popup.get('snapshot_state_unchanged') is not True:
                evidence['failures'].append(f'Declare-war scene {attempt} is not a prepared original active popup snapshot')
                continue
            if popup.get('session') != str(session) or popup.get('snapshot_before_sha256') != digest(snapshot_path):
                evidence['failures'].append(f'Declare-war scene {attempt} is not bound to its exact unchanged session snapshot')
            generations = frame_by_sequence.get(int(seq), [])
            generation = choice_by_attempt[attempt][3]
            if generation not in generations:
                evidence['failures'].append(f'Declare-war scene {attempt} generation is not one of its published UI frames')
            button_id = 'Button2' if attempt == 0 else 'Button1' if attempt == 2 else None
            if button_id:
                targets = [row for row in snapshot.get('inputTargets', []) if type(row) is dict and
                           row.get('id') == button_id and row.get('event') == 'LeftClick']
                if len(targets) != 1 or targets[0].get('visible') is not True or targets[0].get('disabled') is not False:
                    evidence['failures'].append(f'Declare-war attempt {attempt} does not expose exactly one enabled original {button_id} callback')
                    continue
                key = targets[0].get('key')
                if type(key) is not int or key != choice_by_attempt[attempt][2]:
                    evidence['failures'].append(f'Declare-war attempt {attempt} choice key does not identify its exact original {button_id}')
                    continue
                target_keys[attempt] = key
                bounds = targets[0].get('clippedBounds')
                posts = [row for row in posted_rows if len(row) == 4 and row[:2] == [str(generation), str(key)]]
                native = [row for row in ui_rows if len(row) == 4 and row == [str(generation), '1', str(key), '1']]
                if len(posts) != 1 or len(native) != 1 or type(bounds) is not dict:
                    evidence['failures'].append(f'Declare-war attempt {attempt} lacks one posted HWND hit and consumed native left-click')
                else:
                    logical_x, logical_y = int(posts[0][2]) * 1.5, int(posts[0][3]) * 1.5
                    left, top = bounds.get('x'), bounds.get('y')
                    right, bottom = left + bounds.get('width', 0), top + bounds.get('height', 0)
                    if not (left <= logical_x < right and top <= logical_y < bottom):
                        evidence['failures'].append(f'Declare-war attempt {attempt} posted outside the original {button_id} hit bounds')
                    evidence['posted_clicks'].append({'attempt': attempt, 'generation': generation,
                        'key': key, 'posted': posts[0], 'native_input': native[0], 'button_id': button_id})
                    evidence['native_inputs'].append(native[0])
    escape_choice = choice_by_attempt[1]
    escape_native = [row for row in native_keys if row[0] == str(escape_choice[3]) and
                     row[1] == 'declare-war' and row[2] == '27' and row[3:] == ('1', '0')]
    escape_ui = [row for row in ui_rows if row == [str(escape_choice[3]), '0', '0', '1']]
    if len(escape_posts) != 1 or escape_posts[0] != (27, escape_choice[3]) or \
            len(escape_native) != 1 or len(escape_ui) != 1:
        evidence['failures'].append('Escape attempt lacks one posted VK_ESCAPE and one consumed declare-war native keydown that closed the popup')
    else:
        evidence['native_inputs'].append(escape_native[0])
        evidence['native_inputs'].append(escape_ui[0])
    # The observations are per-input and hover may add extra records. Require
    # the exact No/Escape/Yes dispatches while allowing unrelated hover rows.
    # UiPopupContext prints Host UiInputKind (KeyDown=1, LeftClick=2), not
    # presentation BitmapInputKind (KeyDown=0, ControlClick=1).
    required_observations = [(2, choice_by_attempt[0][2], 1, 0, 0, 1),
                             (1, 27, 1, 0, 0, 1),
                             (2, choice_by_attempt[2][2], 1, 0, 1, 0)]
    for expected in required_observations:
        if expected not in observations:
            evidence['failures'].append('Declare-war native input observation is missing the expected consumed/cancel-or-confirm state')
            break
    evidence['validated'] = not evidence['failures']
    return evidence


def _city_rows(path: Path) -> dict[tuple[int, int], dict]:
    cities = {}
    for line in path.read_text(encoding='utf8').splitlines():
        fields = line.split('|')
        if not fields or fields[0] != 'C':
            continue
        if len(fields) != 12 or not re.fullmatch(r'(?:[0-9a-f]{2})*', fields[11]):
            raise ValueError('Malformed C record in city-capture state snapshot')
        values = [int(value) for value in fields[1:11]]
        owner, city_id, x, y, population, food, production, unit, building, damage = values
        key = (owner, city_id)
        if key in cities:
            raise ValueError('Duplicate city identity in city-capture state snapshot')
        cities[key] = {'x': x, 'y': y, 'population': population, 'food100': food,
                       'production100': production, 'production_unit': unit,
                       'production_building': building, 'damage': damage, 'name_key_hex': fields[11]}
    return cities


def _snapshot_node(root: object, key: int) -> dict | None:
    if type(root) is not dict:
        return None
    if root.get('key') == key:
        return root
    children = root.get('children', [])
    if type(children) is list:
        for child in children:
            found = _snapshot_node(child, key)
            if found is not None:
                return found
    return None


def _sdk_enum_value(header: Path, enum_name: str, member: str) -> int | None:
    source = header.read_text(encoding='mbcs')
    match = re.search(r'enum\s+' + re.escape(enum_name) + r'\s*\{([^}]*)\}', source, re.S)
    if not match:
        return None
    body = re.sub(r'/\*.*?\*/', '', match.group(1), flags=re.S)
    body = re.sub(r'//[^\r\n]*', '', body)
    value = -1
    for entry in body.split(','):
        entry = entry.strip()
        if not entry:
            continue
        parsed = re.fullmatch(r'([A-Za-z_]\w*)\s*(?:=\s*(-?\d+))?', entry)
        if not parsed:
            return None
        value = int(parsed.group(2)) if parsed.group(2) is not None else value + 1
        if parsed.group(1) == member:
            return value
    return None


def _verify_context_source_mirrors(sources: list, required_suffixes: tuple[str, ...]) -> tuple[bool, list[dict]]:
    rows_by_path: dict[str, list[dict]] = {}
    for row in sources:
        if type(row) is dict:
            key = str(row.get('path', '')).replace('\\', '/').casefold()
            rows_by_path.setdefault(key, []).append(row)
    checked = []
    valid_all = True
    source_root = PROJECT / 'Source/Assets/UI'
    for suffix in required_suffixes:
        matches = [row for path, rows in rows_by_path.items() if path.endswith(suffix.casefold()) for row in rows]
        verified_rows = []
        for row in matches:
            try:
                original_path = Path(str(row.get('path', '')))
                if not original_path.is_absolute():
                    continue
                original = original_path.resolve(strict=True)
                mirror = (source_root / Path(suffix)).resolve(strict=True)
                original_hash, mirror_hash = digest(original), digest(mirror)
                original_bytes, mirror_bytes = original.stat().st_size, mirror.stat().st_size
                official_path = original.as_posix().replace('\\', '/').casefold().endswith(suffix.casefold())
            except (OSError, RuntimeError, ValueError):
                continue
            if original.is_absolute() and official_path and re.fullmatch(r'[0-9a-f]{64}', str(row.get('sha256', ''))) and \
                    row['sha256'] == original_hash == mirror_hash and original_bytes == mirror_bytes and \
                    (row.get('bytes') is None or row.get('bytes') == original_bytes):
                verified_rows.append(row)
        verified = len(matches) == 1 and len(verified_rows) == 1
        valid_all = valid_all and verified
        checked.append({'expected_suffix': suffix, 'manifest_row': matches[0] if len(matches) == 1 else None,
                        'verified': verified})
    return valid_all, checked


def _sqlite_readonly(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(path.resolve(strict=True).as_uri() + '?mode=ro', uri=True)


def _original_first_greeting_candidates(rules_path: Path, localization_path: Path,
                                       language: str) -> tuple[int, dict[str, str]]:
    rules = _sqlite_readonly(rules_path)
    try:
        rules.execute('ATTACH DATABASE ? AS localized',
                      (localization_path.resolve(strict=True).as_uri() + '?mode=ro',))
        rules.execute("CREATE TEMP VIEW Language_en_US AS "
                      "SELECT Tag FROM localized.LocalizedText WHERE Language='en_US'")
        leaders = [row[0] for row in rules.execute(
            "SELECT DISTINCT LeaderType FROM Diplomacy_Responses WHERE LeaderType!='GENERIC' ORDER BY LeaderType")]
        if not leaders:
            raise ValueError('Rules database has no leader-specific diplomacy responses')
        stock_query = ("select Tag, Bias from Diplomacy_Responses, Language_en_US where "
                       "(LeaderType = ? or LeaderType = 'GENERIC') and ResponseType = ? and Tag like Response")
        tags = set()
        for leader in leaders:
            tags.update(row[0] for row in rules.execute(stock_query, (leader, 'RESPONSE_FIRST_GREETING')))
        if not tags:
            raise ValueError('Original first-greeting response patterns match no canonical English tags')
        placeholders = ','.join('?' for _ in tags)
        localized_rows = rules.execute(
            f"SELECT Tag,Text FROM localized.LocalizedText WHERE Language=? AND Tag IN ({placeholders})",
            (language, *sorted(tags))).fetchall()
        candidate_texts = {tag: value for tag, value in localized_rows
                           if isinstance(value, str) and value.strip()}
        return len(candidate_texts), candidate_texts
    finally:
        rules.close()


def verify_city_capture_smoke(text: str, posted: list[str], native_inputs: list[str],
                              ui_inputs: list[str], sessions: Path, scene_requests: list,
                              language: str) -> dict:
    fixture_matches = re.findall(r'^INTERACTIVE_CITY_CAPTURE_FIXTURE=(-?\d+)\|(-?\d+)\|(-?\d+)\|(-?\d+)\|(-?\d+)\|(-?\d+)$', text, re.M)
    capital_matches = re.findall(r'^INTERACTIVE_CITY_CAPTURE_CAPITAL=(\d+)\|(\d+)\|(\d+)\|([01])\|([01])\|([01])$', text, re.M)
    target_matches = re.findall(r'^INTERACTIVE_CITY_CAPTURE_TARGET=(\d+)\|(\d+)\|(\d+)$', text, re.M)
    choice_matches = re.findall(r'^INTERACTIVE_CITY_CAPTURE_CHOICE=(-?\d+)\|(\d+)\|(\d+)$', text, re.M)
    popup_matches = re.findall(r'^INTERACTIVE_CITY_CAPTURE_POPUP=(-?\d+)\|(-?\d+)\|(-?\d+)\|(-?\d+)\|(-?\d+)\|([01])\|([01])$', text, re.M)
    decision_matches = re.findall(r'^INTERACTIVE_CITY_CAPTURE_DECISION=(-?\d+)\|(-?\d+)\|(\d+)\|(-?\d+)$', text, re.M)
    verified_matches = re.findall(r'^INTERACTIVE_CITY_CAPTURE_VERIFIED=(-?\d+)\|(-?\d+)\|(\d+)\|(\d+)\|(-?\d+)$', text, re.M)
    view_choice_matches = re.findall(r'^INTERACTIVE_CITY_VIEW_CHOICE=(-?\d+)\|(\d+)\|(\d+)$', text, re.M)
    view_shown_matches = re.findall(r'^INTERACTIVE_CITY_VIEW_SHOWN=(-?\d+)\|(-?\d+)\|([01])$', text, re.M)
    view_exit_matches = re.findall(r'^INTERACTIVE_CITY_VIEW_EXIT_CHOICE=(-?\d+)\|(\d+)\|(\d+)$', text, re.M)
    view_closed_matches = re.findall(r'^INTERACTIVE_CITY_VIEW_CLOSED=(-?\d+)\|(-?\d+)\|([01])\|([01])\|([01])$', text, re.M)
    view_returned_matches = re.findall(r'^INTERACTIVE_CITY_VIEW_RETURNED=(-?\d+)\|(-?\d+)$', text, re.M)
    diplomacy_queued = re.findall(r'^INTERACTIVE_DIPLOMACY_QUEUED=(-?\d+)\|(-?\d+)\|(-?\d+)\|(-?\d+)\|(-?\d+)\|(\d+)$', text, re.M)
    diplomacy_shown = re.findall(r'^INTERACTIVE_DIPLOMACY_SHOWN=(-?\d+)\|(-?\d+)\|(-?\d+)\|(-?\d+)\|(-?\d+)\|(\d+)$', text, re.M)
    diplomacy_complete = re.findall(r'^INTERACTIVE_DIPLOMACY_COMPLETE=(-?\d+)\|(-?\d+)\|(-?\d+)\|(-?\d+)\|(-?\d+)$', text, re.M)
    diplomacy_choice = re.findall(r'^INTERACTIVE_DIPLOMACY_CHOICE=(\d+)\|(\d+)$', text, re.M)
    evidence = {'fixtures': [], 'target': None, 'choice': None, 'decision': None, 'verified_city': None,
                'state_files': {}, 'world_scene': None, 'ui_scene': None, 'puppet_label': {},
                'city_view': {'verified': False},
                'leader_diplomacy': {'retail_3d_equivalence_verified': False},
                'verified': False, 'failures': []}
    if not all(len(rows) == 1 for rows in (fixture_matches, capital_matches, target_matches, choice_matches, popup_matches, decision_matches, verified_matches)):
        evidence['failures'].append('City-capture protocol requires exactly one fixture, target, choice, decision, and verified marker')
        return evidence
    # Ordinary owned-city interaction can precede the capture fixture. Bind
    # this review only to the captured city's read-only CityView roundtrip.
    captured_city_id = int(choice_matches[0][0])
    view_shown_matches = [row for row in view_shown_matches if int(row[1]) == captured_city_id and row[2] == '1']
    view_closed_matches = [row for row in view_closed_matches if int(row[1]) == captured_city_id]
    city_view_mode = any((view_choice_matches, view_shown_matches, view_exit_matches, view_returned_matches))
    if city_view_mode and not all(len(rows) == 1 for rows in
                                  (view_choice_matches, view_shown_matches, view_exit_matches, view_closed_matches, view_returned_matches)):
        evidence['failures'].append('CityView roundtrip requires exactly one entrance, shown, exit, closed-state, and return marker')
        return evidence
    fixture = tuple(map(int, fixture_matches[0]))
    plot_index, hit_key, world_generation = map(int, target_matches[0])
    city_id, button_key, ui_generation = map(int, choice_matches[0])
    popup = tuple(map(int, popup_matches[0]))
    evidence['popup_payload'] = popup
    if popup[0] != city_id or popup[4:] != (-1, 0, 1) or any(value < 0 for value in popup[1:4]):
        evidence['failures'].append('SDK capture popup did not retain its exact new-city and conquest/no-liberation payload')
    decision_owner, decision_city, action, task_or_liberated = map(int, decision_matches[0])
    owner, verified_id, is_puppet, is_razing, original_owner = map(int, verified_matches[0])
    attacker_owner, attacker_id, defender_owner, old_city, x, y = fixture
    capital_owner, capital_city, defender_cities_before, declared_war, capital_created, met_for_fixture = map(int, capital_matches[0])
    evidence['preserved_capital'] = {'owner': capital_owner, 'city': capital_city,
                                     'cities_before_fixture': defender_cities_before,
                                     'declared_war': declared_war, 'capital_created': capital_created,
                                     'met_for_fixture': met_for_fixture}
    if capital_owner != defender_owner or capital_city == old_city or defender_cities_before < 1:
        evidence['failures'].append('City-capture fixture did not retain a distinct original capital and another city')
    evidence.update(fixtures=[fixture], target=[plot_index, hit_key, world_generation],
                    choice=[city_id, button_key, ui_generation],
                    decision=[decision_owner, decision_city, action, task_or_liberated],
                    verified_city=[owner, verified_id, is_puppet, is_razing, original_owner])
    if attacker_owner == defender_owner or (owner, verified_id, is_puppet, is_razing, original_owner) != \
            (attacker_owner, city_id, 1, 0, defender_owner) or (decision_owner, decision_city, action) != (attacker_owner, city_id, 1):
        evidence['failures'].append('City-capture fixture, puppet callback, and final SDK city identity/outcome disagree')
        return evidence
    # Civ V's frozen BNW SDK enum lists TASK_CREATE_PUPPET after TASK_RANGED_ATTACK.
    sdk_enum = PROJECT / 'Source/SDK_BNW_x64/CvGameCoreDLLUtil/include/CvEnums.h'
    enum_text = sdk_enum.read_text(encoding='mbcs')
    block = re.search(r'enum\s+TaskTypes\s*\{([^}]*)\}', enum_text, re.S)
    names = re.findall(r'\b(TASK_[A-Z0-9_]+|NUM_TASK_TYPES)\s*(?:,|$)', block.group(1), re.M) if block else []
    expected_task = names.index('TASK_CREATE_PUPPET') if 'TASK_CREATE_PUPPET' in names else None
    evidence['puppet_task_enum'] = {'header': str(sdk_enum), 'sha256': digest(sdk_enum), 'value': expected_task}
    if expected_task is None or task_or_liberated != expected_task:
        evidence['failures'].append('City-capture callback did not issue the frozen SDK TASK_CREATE_PUPPET enum')

    expected_diplo_state = _sdk_enum_value(sdk_enum, 'DiploUIStateTypes', 'DIPLO_UI_STATE_DEFAULT_ROOT')
    expected_intro_animation = _sdk_enum_value(sdk_enum, 'LeaderheadAnimationTypes', 'LEADERHEAD_ANIM_INTRO')
    evidence['leader_diplomacy']['sdk_enum'] = {'header': str(sdk_enum), 'sha256': digest(sdk_enum),
        'first_contact_state': {'symbol': 'DIPLO_UI_STATE_DEFAULT_ROOT', 'value': expected_diplo_state},
        'intro_animation': {'symbol': 'LEADERHEAD_ANIM_INTRO', 'value': expected_intro_animation}}
    if not all(len(rows) == 1 for rows in (diplomacy_queued, diplomacy_shown, diplomacy_complete, diplomacy_choice)):
        evidence['failures'].append('Meet/DeclareWar diplomacy protocol requires exactly one queued, shown, Back-choice, and completed leader message')
        ordered = False
    else:
        queued = tuple(map(int, diplomacy_queued[0]))
        shown = tuple(map(int, diplomacy_shown[0]))
        completed = tuple(map(int, diplomacy_complete[0]))
        back_key, diplomacy_generation = map(int, diplomacy_choice[0])
        evidence['leader_diplomacy'].update(queued=queued, shown=shown, complete=completed,
            choice=[back_key, diplomacy_generation])
        if queued != shown or completed != queued[:5] or queued[5] <= 0 or \
                (queued[0], queued[1], queued[2], queued[3]) != \
                (attacker_owner, defender_owner, expected_diplo_state, expected_intro_animation) or queued[4] != -1:
            evidence['failures'].append('Queued, shown, and completed SDK first-contact INTRO payloads disagree')
        capture_popup_line = re.search(r'^INTERACTIVE_CITY_CAPTURE_POPUP=.*$', text, re.M)
        capture_decision_line = re.search(r'^INTERACTIVE_CITY_CAPTURE_DECISION=.*$', text, re.M)
        queued_line = re.search(r'^INTERACTIVE_DIPLOMACY_QUEUED=.*$', text, re.M)
        shown_line = re.search(r'^INTERACTIVE_DIPLOMACY_SHOWN=.*$', text, re.M)
        choice_line = re.search(r'^INTERACTIVE_DIPLOMACY_CHOICE=.*$', text, re.M)
        complete_line = re.search(r'^INTERACTIVE_DIPLOMACY_COMPLETE=.*$', text, re.M)
        ordered = all(line is not None for line in (capture_popup_line, capture_decision_line, queued_line,
                       shown_line, choice_line, complete_line)) and \
            capture_popup_line.start() < queued_line.start() < capture_decision_line.start() < \
            shown_line.start() < choice_line.start() < complete_line.start()
    if not ordered:
        evidence['failures'].append('Capture popup was not preserved ahead of the queued leader intro, then completed before the deferred display and original Back return')

    session_root = Path(sessions).resolve(strict=False)
    catalog_markers = re.findall(r'^DIPLOMACY_CANONICAL_ENGLISH_CATALOG=(\d+)\|temporary\|en_US$', text, re.M)
    catalog_evidence = {'marker_count': int(catalog_markers[0]) if len(catalog_markers) == 1 else None,
                        'temporary': len(catalog_markers) == 1, 'language': 'en_US',
                        'runtime_temp_query_verified': False}
    localization_path = session_root.parent / 'localization.db'
    try:
        localization_db = _sqlite_readonly(localization_path)
        try:
            canonical_rows, canonical_unique = localization_db.execute(
                "SELECT COUNT(*),COUNT(DISTINCT Tag) FROM LocalizedText WHERE Language='en_US'").fetchone()
        finally:
            localization_db.close()
        catalog_evidence.update(runtime_localized_rows=canonical_rows,
                                runtime_unique_en_us_tags=canonical_unique,
                                source=artifact(localization_path.resolve(strict=True)))
        if len(catalog_markers) != 1 or int(catalog_markers[0]) != canonical_rows or canonical_rows != canonical_unique:
            evidence['failures'].append('Host canonical English tag catalog marker does not match the unique en_US rows in the sealed localization database')
    except (OSError, sqlite3.Error, TypeError, ValueError) as error:
        evidence['failures'].append('Canonical English diplomacy catalog count could not be verified: ' + str(error))
    evidence['leader_diplomacy']['canonical_english_catalog'] = catalog_evidence
    before_paths, after_paths = list(session_root.glob('*/play-city-capture-before-state.txt')), list(session_root.glob('*/play-city-capture-after-state.txt'))
    if len(before_paths) != 1 or len(after_paths) != 1:
        evidence['failures'].append('City-capture before/after SDK state snapshots are missing or ambiguous')
        return evidence
    before_path, after_path = before_paths[0].resolve(strict=True), after_paths[0].resolve(strict=True)
    if before_path.parent != after_path.parent or before_path.parent.parent != session_root:
        evidence['failures'].append('City-capture state snapshots do not belong to one exact private SDK session')
        return evidence
    evidence['state_files'] = {'before': artifact(before_path), 'after': artifact(after_path)}
    try:
        before_cities, after_cities = _city_rows(before_path), _city_rows(after_path)
    except (OSError, UnicodeError, ValueError) as error:
        evidence['failures'].append('City-capture SDK state snapshot parse failed: ' + str(error))
        return evidence
    old_key, new_key = (defender_owner, old_city), (attacker_owner, city_id)
    capital_key = (capital_owner, capital_city)
    if capital_key not in before_cities or capital_key not in after_cities or \
            before_cities[capital_key]['x'] != after_cities[capital_key]['x'] or \
            before_cities[capital_key]['y'] != after_cities[capital_key]['y'] or \
            sum(key[0] == defender_owner for key in before_cities) != defender_cities_before + 1 or \
            sum(key[0] == defender_owner for key in after_cities) != defender_cities_before:
        evidence['failures'].append('Real SDK city records do not prove the defender retained its capital after losing only the target city')
    before_old, after_old, after_new = before_cities.get(old_key), after_cities.get(old_key), after_cities.get(new_key)
    if not before_old or (before_old['x'], before_old['y']) != (x, y) or after_old is not None or \
            not after_new or (after_new['x'], after_new['y']) != (x, y):
        evidence['failures'].append('Real SDK C records do not prove the hostile city was replaced by the exact new owned city')

    posted_rows = [row.split('|') for row in posted]
    window_rows = [row.split('|') for row in native_inputs]
    ui_rows = [row.split('|') for row in ui_inputs]
    world_posted = [row for row in posted_rows if len(row) == 4 and row[:2] == [str(world_generation), str(hit_key)]]
    world_kind = '5' if 'INTERACTIVE_SMOKE_BUTTON=' in text else '1'
    world_consumed = [row for row in window_rows if len(row) == 4 and row[:3] == [str(world_generation), world_kind, str(hit_key)] and row[3] == '1']
    if world_kind == '5' and text.splitlines().count(f'INTERACTIVE_SMOKE_BUTTON={world_generation}|{hit_key}|5|0') != 1:
        evidence['failures'].append('City capture lacks its exact posted right-button record')
    ui_posted = [row for row in posted_rows if len(row) == 4 and row[:2] == [str(ui_generation), str(button_key)]]
    ui_consumed = [row for row in ui_rows if len(row) == 4 and row[:3] == [str(ui_generation), '1', str(button_key)] and row[3] == '1']
    if not (len(world_posted) == len(world_consumed) == len(ui_posted) == len(ui_consumed) == 1):
        evidence['failures'].append('Posted HWND target and one consumed world click/puppet callback click do not match their generations and keys')

    matches = []
    for scene_path in before_path.parent.glob('play-scene-*.json'):
        try:
            scene = json.loads(scene_path.read_text(encoding='utf8'))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if scene.get('generation') == world_generation:
            matches.append((scene_path.resolve(strict=True), scene))
    if len(matches) != 1:
        evidence['failures'].append('City-capture target has no unique world scene at its recorded generation')
    else:
        scene_path, scene = matches[0]
        evidence['world_scene'] = artifact(scene_path)
        plots = [row for row in scene.get('plots', []) if type(row) is list and len(row) == 5 and row[0] == plot_index]
        hits = [row for row in scene.get('hits', []) if type(row) is list and len(row) == 5 and row[0] == hit_key]
        cities = [row for row in scene.get('cities', []) if type(row) is dict and row.get('owner') == defender_owner and row.get('id') == old_city]
        if scene.get('activePlayer') != attacker_owner or len(plots) != 1 or plots[0][1:5] != [x, y, 1, 1] or \
                len(hits) > 1 or len(cities) != 1 or (cities[0].get('x'), cities[0].get('y')) != (x, y):
            evidence['failures'].append('Recorded city-capture world scene does not show the visible hostile city and clickable target plot')
        if len(world_posted) == 1:
            try:
                evidence['world_posted_hit_proof'] = _verify_world_posted_hit(scene_path, scene, hit_key, world_posted[0])
            except (OSError, ValueError, RuntimeError) as error:
                evidence['failures'].append('City capture picking failed: ' + str(error))

    ui_scenes = [row for row in scene_requests if type(row) is dict and row.get('context') == 'city-capture' and row.get('closed') is False]
    expected_capture_scene_count = 2 if city_view_mode else 1
    if len(ui_scenes) != expected_capture_scene_count:
        evidence['failures'].append('City-capture run has the wrong number of open original GenericPopup scenes for its input profile')
    else:
        ui_scenes.sort(key=lambda row: row.get('sequence', -1))
        ui_scene = ui_scenes[-1] if city_view_mode else ui_scenes[0]
        manifest_path = Path(ui_scene.get('manifest', {}).get('path', '')).resolve(strict=True)
        manifest = json.loads(manifest_path.read_text(encoding='utf8'))
        evidence['ui_scene'] = artifact(manifest_path)
        expected_sources = ('Assets/UI/InGame/Popups/GenericPopup.lua', 'Assets/UI/InGame/Popups/GenericPopup.xml',
                            'Assets/UI/InGame/Popups/EmptyPopup.lua', 'Assets/UI/InGame/Popups/EmptyPopup.xml',
                            'Assets/DLC/Expansion2/UI/InGame/PopupsGeneric/PuppetCityPopup.lua')
        sources = manifest.get('original_context_sources', [])
        source_paths = {}
        for row in sources:
            if type(row) is dict:
                key = str(row.get('path', '')).replace('\\', '/').casefold()
                source_paths.setdefault(key, []).append(row)
        checked_sources = []
        provenance_ok = True
        source_root = PROJECT / 'Source/Assets/UI'
        for suffix in expected_sources:
            source_path = (source_root / Path(suffix)).resolve(strict=False)
            matches = [row for path, rows in source_paths.items() if path.endswith(suffix.casefold()) for row in rows]
            try:
                source_path = source_path.resolve(strict=True)
                source_hash = digest(source_path)
                source_bytes = source_path.stat().st_size
            except (OSError, RuntimeError, ValueError):
                provenance_ok = False
                continue
            valid_rows = []
            for row in matches:
                manifest_source = Path(str(row.get('path', '')))
                try:
                    manifest_source = manifest_source.resolve(strict=True)
                    manifest_hash = digest(manifest_source)
                    manifest_bytes = manifest_source.stat().st_size
                    source_relative = manifest_source.as_posix().replace('\\', '/').casefold()
                    official_path = source_relative.endswith(suffix.casefold())
                except (OSError, RuntimeError, ValueError):
                    continue
                if isinstance(row.get('sha256'), str) and re.fullmatch(r'[0-9a-f]{64}', row['sha256']) and \
                        official_path and row['sha256'] == source_hash == manifest_hash and \
                        manifest_bytes == source_bytes and (row.get('bytes') is None or row.get('bytes') == manifest_bytes):
                    valid_rows.append(row)
            if len(matches) != 1 or len(valid_rows) != 1:
                provenance_ok = False
            checked_sources.append({'expected_suffix': suffix, 'source': source_annotation(source_path),
                                    'manifest_row': matches[0] if len(matches) == 1 else None,
                                    'verified': len(matches) == 1 and len(valid_rows) == 1})
        evidence['ui_source_provenance'] = checked_sources
        if (manifest.get('context'), manifest.get('context_name'), manifest.get('popup_kind')) != ('city-capture', 'GenericPopup', 'CityCapture') or not provenance_ok:
            evidence['failures'].append('City-capture renderer manifest lacks its exact context metadata or original source-byte provenance')
        if manifest.get('snapshot', {}).get('sha256') != ui_scene.get('snapshot_before_sha256') or manifest.get('snapshot_state_unchanged') is not True:
            evidence['failures'].append('City-capture renderer manifest does not bind its unchanged retained SDK snapshot')
        retained = [row for row in manifest.get('retained_input_targets', []) if type(row) is dict and row.get('key') == button_key and row.get('event') == 'LeftClick']
        if len(retained) != 1 or retained[0].get('visible') is not True or retained[0].get('disabled') is not False:
            evidence['failures'].append('Puppet callback key is not a unique visible enabled retained LeftClick target')
        snapshot_path = Path(manifest.get('snapshot', {}).get('path', '')).resolve(strict=True)
        snapshot = json.loads(snapshot_path.read_text(encoding='utf8'))
        button = _snapshot_node(snapshot.get('tree'), button_key)
        labels = [child for child in button.get('children', []) if type(child) is dict and child.get('kind') in ('Label', 'TextButton')] if button else []
        label_texts = [child.get('text') for child in labels if isinstance(child.get('text'), str)]
        localization_path = (session_root.parent / 'localization.db').resolve(strict=False)
        localized = []
        try:
            localization_path = localization_path.resolve(strict=True)
            with sqlite3.connect(localization_path.as_uri() + '?mode=ro', uri=True) as connection:
                localized = [row[0] for row in connection.execute(
                    'SELECT Text FROM LocalizedText WHERE Tag=? AND Language=?',
                    ('TXT_KEY_POPUP_PUPPET_CAPTURED_CITY', language)).fetchall()]
        except (sqlite3.Error, OSError, RuntimeError, ValueError):
            localized = []
        localization_verified = len(localized) == 1 and len(label_texts) == 1 and localized[0] == label_texts[0]
        evidence['puppet_label'] = {'tag': 'TXT_KEY_POPUP_PUPPET_CAPTURED_CITY', 'snapshot_text': label_texts,
                                    'localized_text': localized, 'verified': localization_verified,
                                    'localization_database': artifact(localization_path) if localization_path.is_file() else None,
                                    'verification_policy': 'Compare retained button child text to the exact language row in the runtime localization.db used by the Host; no rules.db or literal translation fallback'}
        if not localization_verified:
            evidence['failures'].append('Retained puppet button text does not match the authoritative Host localization row')

    if city_view_mode:
        view_city, view_key, view_generation = map(int, view_choice_matches[0])
        shown_owner, shown_city, shown = map(int, view_shown_matches[0])
        exit_city, exit_key, exit_generation = map(int, view_exit_matches[0])
        closed_owner, closed_city, screen_up, viewing_mode, has_selected_city = map(int, view_closed_matches[0])
        returned_owner, returned_city = map(int, view_returned_matches[0])
        view_evidence = evidence['city_view']
        view_evidence.update(choice=[view_city, view_key, view_generation], shown=[shown_owner, shown_city, shown],
                             exit_choice=[exit_city, exit_key, exit_generation],
                             closed=[closed_owner, closed_city, screen_up, viewing_mode, has_selected_city],
                             returned=[returned_owner, returned_city])
        if (view_city, shown_owner, shown_city, shown, exit_city, returned_owner, returned_city) != \
                (city_id, attacker_owner, city_id, 1, city_id, attacker_owner, city_id) or \
                (closed_owner, closed_city, screen_up, viewing_mode, has_selected_city) != (attacker_owner, city_id, 0, 0, 0) or \
                len({view_generation, exit_generation, ui_generation}) != 3:
            evidence['failures'].append('CityView entrance, selected city, shown state, exit, and returned capture identity disagree')

        capture_order = sorted(ui_scenes, key=lambda row: row.get('sequence', -1)) if len(ui_scenes) == 2 else []
        city_view_scenes = [row for row in scene_requests if type(row) is dict and row.get('context') == 'city-view' and
                           row.get('closed') is False and len(capture_order) == 2 and
                           capture_order[0].get('sequence', -1) < row.get('sequence', -1) < capture_order[1].get('sequence', -1)]
        if len(capture_order) != 2 or len(city_view_scenes) != 1 or not (
                capture_order[0].get('sequence', -1) < city_view_scenes[0].get('sequence', -1) <
                capture_order[1].get('sequence', -1)):
            evidence['failures'].append('CityView scene is not the unique original context between the initial and returned capture popups')
        else:
            first_capture = capture_order[0]
            returned_capture = capture_order[1]
            city_scene = city_view_scenes[0]
            try:
                first_manifest_path = Path(first_capture.get('manifest', {}).get('path', '')).resolve(strict=True)
                first_manifest = json.loads(first_manifest_path.read_text(encoding='utf8'))
                first_snapshot_path = Path(first_manifest.get('snapshot', {}).get('path', '')).resolve(strict=True)
                first_snapshot = json.loads(first_snapshot_path.read_text(encoding='utf8'))
                view_manifest_path = Path(city_scene.get('manifest', {}).get('path', '')).resolve(strict=True)
                view_manifest = json.loads(view_manifest_path.read_text(encoding='utf8'))
                view_snapshot_path = Path(view_manifest.get('snapshot', {}).get('path', '')).resolve(strict=True)
                view_snapshot = json.loads(view_snapshot_path.read_text(encoding='utf8'))
                returned_manifest_path = Path(returned_capture.get('manifest', {}).get('path', '')).resolve(strict=True)
                returned_manifest = json.loads(returned_manifest_path.read_text(encoding='utf8'))
                returned_snapshot_path = Path(returned_manifest.get('snapshot', {}).get('path', '')).resolve(strict=True)
                returned_snapshot = json.loads(returned_snapshot_path.read_text(encoding='utf8'))
                owned_session = first_snapshot_path.parent
                if owned_session.parent != session_root or not re.fullmatch(r'[0-9a-f]{32}', owned_session.name) or \
                        view_snapshot_path.parent != owned_session or returned_snapshot_path.parent != owned_session:
                    raise ValueError('CityView snapshots do not belong to the same exact SDK session')
                for candidate in (first_manifest_path, view_manifest_path, returned_manifest_path,
                                  first_snapshot_path, view_snapshot_path, returned_snapshot_path):
                    if not candidate.is_relative_to(owned_session):
                        raise ValueError('retained CityView scene artifact escaped the private SDK session')
                view_evidence['scene_artifacts'] = {'initial_capture_manifest': artifact(first_manifest_path),
                    'city_view_manifest': artifact(view_manifest_path), 'returned_capture_manifest': artifact(returned_manifest_path),
                    'initial_capture_snapshot': artifact(first_snapshot_path), 'city_view_snapshot': artifact(view_snapshot_path),
                    'returned_capture_snapshot': artifact(returned_snapshot_path)}
                expected_view_context = ('city-view', 'CityView', 'CityView')
                if (view_manifest.get('context'), view_manifest.get('context_name'), view_manifest.get('popup_kind')) != expected_view_context or \
                        (view_snapshot.get('contextName'), view_snapshot.get('popupKind'), view_snapshot.get('active'),
                         view_snapshot.get('timerSemaphore')) != ('CityView', 'CityView', True, 0) or \
                        view_manifest.get('snapshot', {}).get('sha256') != city_scene.get('snapshot_before_sha256') or \
                        view_manifest.get('snapshot_state_unchanged') is not True:
                    evidence['failures'].append('CityView manifest/snapshot does not retain the exact original CityView context metadata')
                city_profile = view_snapshot.get('cityView', {})
                small_city = city_profile.get('smallUIAssets')
                expected_variant = 'small' if small_city is True else 'default'
                if type(small_city) is not bool or city_profile.get('layoutVariant') != expected_variant or \
                        f'CITY_VIEW_UI_SMALL_ASSETS={int(small_city is True)}' not in text.splitlines():
                    evidence['failures'].append('CityView layout variant differs from the frozen native SmallUIAssets profile')
                view_sources = ('Assets/DLC/Expansion2/UI/InGame/CityView/CityView.lua',
                                'Assets/DLC/Expansion2/UI/InGame/CityView/' + ('CityView_small.xml' if small_city else 'CityView.xml'),
                                'Assets/UI/SupportFunctions.lua')
                view_sources_ok, checked_view_sources = _verify_context_source_mirrors(
                    view_manifest.get('original_context_sources', []), view_sources)
                view_evidence['original_source_provenance'] = checked_view_sources
                if not view_sources_ok:
                    evidence['failures'].append('CityView manifest does not prove the exact original Lua/XML/SupportFunctions bytes against the source mirrors')
                first_targets = [row for row in first_manifest.get('retained_input_targets', []) if type(row) is dict and
                                 row.get('key') == view_key and row.get('event') == 'LeftClick']
                exit_targets = [row for row in view_manifest.get('retained_input_targets', []) if type(row) is dict and
                                row.get('key') == exit_key and row.get('event') == 'LeftClick' and row.get('id') == 'ReturnToMapButton']
                returned_targets = [row for row in returned_manifest.get('retained_input_targets', []) if type(row) is dict and
                                    row.get('key') == button_key and row.get('event') == 'LeftClick']
                def unique_enabled_target(rows):
                    return len(rows) == 1 and rows[0].get('visible') is True and rows[0].get('disabled') is False and \
                        isinstance(rows[0].get('bounds'), dict) and rows[0].get('bounds') == rows[0].get('clippedBounds')
                if not unique_enabled_target(first_targets) or not unique_enabled_target(exit_targets) or \
                        not unique_enabled_target(returned_targets):
                    evidence['failures'].append('CityView entrance, ReturnToMapButton, or returned puppet callback is not a unique visible enabled retained target')
                city_projection = view_snapshot.get('cityView')
                required_projection_keys = {'owner', 'city', 'viewingMode', 'retailWorldProjectionVerified', 'projection',
                                            'hexHighlights', 'tutorialRequests', 'tutorialExecutionVerified',
                                            'hexCoordinatePolicy', 'unresolvedIncludes', 'layoutVariant', 'smallUIAssets'}
                allowed_projection_keys = required_projection_keys | {'yieldDisplay'}
                projection = city_projection.get('projection') if type(city_projection) is dict else None
                if type(city_projection) is not dict or not required_projection_keys <= set(city_projection) or \
                        not set(city_projection) <= allowed_projection_keys or \
                        (city_projection.get('owner'), city_projection.get('city'), city_projection.get('viewingMode'),
                         city_projection.get('retailWorldProjectionVerified')) != (attacker_owner, city_id, True, False) or \
                        type(projection) is not dict or projection.get('policy') != 'ZEROSIS_2D_CITY_VIEW_V1' or \
                        city_projection.get('unresolvedIncludes') != ['TutorialPopupScreen'] or \
                        city_projection.get('tutorialExecutionVerified') is not False:
                    evidence['failures'].append('CityView retained projection lacks the selected live city identity or exposes a non-projection data DTO')

                shown_path = (owned_session / 'play-city-view-shown-state.txt').resolve(strict=True)
                returned_path = (owned_session / 'play-city-view-returned-state.txt').resolve(strict=True)
                if shown_path.read_bytes() != returned_path.read_bytes():
                    evidence['failures'].append('SDK state changed between the retained CityView display and return snapshots')
                view_evidence['state_files'] = {'shown': artifact(shown_path), 'returned': artifact(returned_path),
                                                'byte_identical': shown_path.read_bytes() == returned_path.read_bytes()}
                citizen_before = []
                for candidate_before in owned_session.glob('play-context-*/city-enter-before-citizens.txt'):
                    context_shown = candidate_before.parent / 'ui-popup-1-shown.json'
                    if not context_shown.is_file():
                        continue
                    shown_context = json.loads(context_shown.read_text(encoding='utf8'))
                    identity = shown_context.get('cityView', {})
                    if shown_context.get('popupKind') == 'CityView' and \
                            (identity.get('owner'), identity.get('city'), identity.get('viewingMode')) == (attacker_owner, city_id, True):
                        citizen_before.append(candidate_before)
                citizen_after = [path.parent / 'city-enter-after-citizens.txt' for path in citizen_before
                                 if (path.parent / 'city-enter-after-citizens.txt').is_file()]
                if len(citizen_before) != 1 or len(citizen_after) != 1 or citizen_before[0].parent != citizen_after[0].parent:
                    evidence['failures'].append('CityView entry citizen-update before/after records are missing or ambiguous')
                else:
                    view_evidence['citizen_update'] = {'before': artifact(citizen_before[0].resolve(strict=True)),
                        'after': artifact(citizen_after[0].resolve(strict=True)),
                        'state_change_permitted_by_stock_entry': True}
            except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError) as error:
                evidence['failures'].append('CityView retained artifact validation failed: ' + str(error))

        posted_rows = [row.split('|') for row in posted]
        ui_rows = [row.split('|') for row in ui_inputs]
        view_posts = [row for row in posted_rows if len(row) == 4 and row[:2] == [str(view_generation), str(view_key)]]
        view_consumed = [row for row in ui_rows if len(row) == 4 and row[:3] == [str(view_generation), '1', str(view_key)] and row[3] == '1']
        exit_posts = [row for row in posted_rows if len(row) == 4 and row[:2] == [str(exit_generation), str(exit_key)]]
        exit_consumed = [row for row in ui_rows if len(row) == 4 and row[:3] == [str(exit_generation), '1', str(exit_key)] and row[3] == '1']
        puppet_posts = [row for row in posted_rows if len(row) == 4 and row[:2] == [str(ui_generation), str(button_key)]]
        puppet_consumed = [row for row in ui_rows if len(row) == 4 and row[:3] == [str(ui_generation), '1', str(button_key)] and row[3] == '1']
        if not (len(view_posts) == len(view_consumed) == len(exit_posts) == len(exit_consumed) ==
                len(puppet_posts) == len(puppet_consumed) == 1):
            evidence['failures'].append('Posted CityView entrance/return and deferred puppet inputs were not each consumed once by the expected HWND generation')

        raw_marker_order = [re.search(pattern, text, re.M) for pattern in (
            r'^INTERACTIVE_CITY_VIEW_CHOICE=.*$', r'^INTERACTIVE_CITY_VIEW_EXIT_CHOICE=.*$',
            rf'^INTERACTIVE_CITY_VIEW_CLOSED={attacker_owner}\|{city_id}\|0\|0\|0$', r'^INTERACTIVE_CITY_VIEW_RETURNED=.*$',
            r'^INTERACTIVE_CITY_CAPTURE_CHOICE=.*$', r'^INTERACTIVE_CITY_CAPTURE_DECISION=.*$')]
        if any(match is None for match in raw_marker_order) or not all(
                left.start() < right.start() for left, right in zip(raw_marker_order, raw_marker_order[1:])):
            evidence['failures'].append('Deferred puppet decision did not remain pending through CityView exit and return')
        evidence['city_view']['verified'] = not evidence['failures']

    leader_scenes = [row for row in scene_requests if type(row) is dict and row.get('context') == 'diplomacy' and row.get('closed') is False]
    if len(leader_scenes) != 1:
        evidence['failures'].append('City-capture run lacks one open original LeaderHead diplomacy scene')
    elif len(diplomacy_queued) == len(diplomacy_shown) == len(diplomacy_complete) == len(diplomacy_choice) == 1:
        leader_scene = leader_scenes[0]
        leader_manifest_path = Path(leader_scene.get('manifest', {}).get('path', '')).resolve(strict=True)
        leader_manifest = json.loads(leader_manifest_path.read_text(encoding='utf8'))
        evidence['leader_diplomacy']['ui_scene'] = artifact(leader_manifest_path)
        required_leader_sources = (
            'Assets/DLC/Expansion2/UI/InGame/LeaderHead/LeaderHeadRoot.lua',
            'Assets/DLC/Expansion2/UI/InGame/LeaderHead/LeaderHeadRoot.xml',
            'Assets/UI/IconSupport.lua',
            'Assets/Gameplay/Lua/GameplayUtilities.lua',
            'Assets/DLC/Expansion2/UI/InGame/InfoTooltipInclude.lua')
        source_ok, checked_leader_sources = _verify_context_source_mirrors(
            leader_manifest.get('original_context_sources', []), required_leader_sources)
        evidence['leader_diplomacy']['ui_source_provenance'] = checked_leader_sources
        if (leader_manifest.get('context'), leader_manifest.get('context_name'), leader_manifest.get('popup_kind')) != \
                ('diplomacy', 'diplomacy', 'LeaderHead') or not source_ok:
            evidence['failures'].append('LeaderHead manifest lacks the original root/import byte provenance or exact diplomacy context')
        if leader_manifest.get('snapshot', {}).get('sha256') != leader_scene.get('snapshot_before_sha256') or \
                leader_manifest.get('snapshot_state_unchanged') is not True:
            evidence['failures'].append('LeaderHead manifest does not bind its exact unchanged retained SDK snapshot')
        leader_snapshot_path = Path(leader_manifest.get('snapshot', {}).get('path', '')).resolve(strict=True)
        if not leader_snapshot_path.is_relative_to(before_path.parent):
            evidence['failures'].append('LeaderHead retained snapshot escaped the city-capture SDK session')
        leader_snapshot = json.loads(leader_snapshot_path.read_text(encoding='utf8'))
        leader_message = leader_snapshot.get('leaderMessage')
        queued = tuple(map(int, diplomacy_queued[0]))
        back_key, diplomacy_generation = map(int, diplomacy_choice[0])
        payload_files = list(before_path.parent.glob('play-context-*/leader-message-input.json'))
        input_payload = {}
        input_payload_path = None
        if len(payload_files) == 1:
            input_payload_path = payload_files[0].resolve(strict=True)
            if input_payload_path.parent.parent != before_path.parent or \
                    not re.fullmatch(r'play-context-[0-9]+', input_payload_path.parent.name):
                payload_files = []
            else:
                try:
                    input_payload = json.loads(input_payload_path.read_text(encoding='utf8'))
                except (OSError, UnicodeError, json.JSONDecodeError):
                    payload_files = []
        if len(payload_files) != 1:
            evidence['failures'].append('Owned LeaderHead SDK JSON input is missing, ambiguous, or outside the exact city-capture session')
        else:
            evidence['leader_diplomacy']['sdk_input'] = artifact(input_payload_path)
        expected_fields = {'receiver', 'player', 'state', 'text', 'animation', 'data1'}
        payload_text = input_payload.get('text') if type(input_payload) is dict else None
        payload_text_bytes = len(payload_text.encode('utf8')) if isinstance(payload_text, str) else -1
        payload_ok = type(input_payload) is dict and set(input_payload) == expected_fields and \
            all(type(input_payload.get(name)) is int for name in ('receiver', 'player', 'state', 'animation', 'data1')) and \
            isinstance(payload_text, str) and payload_text.strip() and payload_text_bytes == queued[5] and \
            tuple(input_payload[name] for name in ('receiver', 'player', 'state', 'animation', 'data1')) == queued[:5]
        if not payload_ok:
            evidence['failures'].append('LeaderHead SDK JSON payload differs from its queued fields or UTF-8 text byte count')
        if payload_ok:
            try:
                candidate_count, candidate_texts = _original_first_greeting_candidates(
                    before_path.parent / 'rules.db', localization_path, language)
                matching_tags = sorted(tag for tag, value in candidate_texts.items() if value == payload_text)
                evidence['leader_diplomacy']['original_first_greeting_candidates'] = {
                    'pattern': 'stock Diplomacy_Responses ResponseType=RESPONSE_FIRST_GREETING with Tag LIKE Response',
                    'leader_scope': 'union of leader-specific stock types plus GENERIC; payload has sender slot but no LeaderType',
                    'candidate_tags_with_localized_text': candidate_count,
                    'matching_localized_tags': matching_tags,
                    'language': language,
                    'runtime_sdk_selection_verified': False}
                if not matching_tags:
                    evidence['failures'].append('Owned leader text does not match any localized original first-greeting candidate')
            except (OSError, sqlite3.Error, TypeError, ValueError) as error:
                evidence['failures'].append('Original first-greeting candidate comparison failed: ' + str(error))
        message_ok = type(leader_message) is dict and type(input_payload) is dict and all(
            leader_message.get(name) == input_payload.get(name)
            for name in ('player', 'state', 'text', 'animation', 'data1'))
        if leader_snapshot.get('contextName') != 'diplomacy' or leader_snapshot.get('popupKind') != 'LeaderHead' or \
                leader_snapshot.get('active') is not True or leader_snapshot.get('timerSemaphore') != 0 or \
                leader_snapshot.get('leaderRootUp') is not True or not message_ok:
            evidence['failures'].append('Retained LeaderHead snapshot does not show the matching active untimed original intro/root state')
        evidence['leader_diplomacy'].update(snapshot=artifact(leader_snapshot_path),
            retained_message=leader_message if type(leader_message) is dict else None,
            leader_3d_equivalence_verified=False,
            leaderhead_display_policy=leader_manifest.get('leaderhead_display_policy'))
        if leader_snapshot.get('retailLeaderRendererVerified') is not False:
            evidence['failures'].append('LeaderHead evidence does not explicitly keep retail 3D leader equivalence unverified')

        retained_targets = [row for row in leader_manifest.get('retained_input_targets', [])
                            if type(row) is dict and row.get('key') == back_key and row.get('id') == 'BackButton' and
                            row.get('event') == 'LeftClick']
        snapshot_targets = [row for row in leader_snapshot.get('inputTargets', [])
                            if type(row) is dict and row.get('key') == back_key and row.get('id') == 'BackButton' and
                            row.get('event') == 'LeftClick']
        if len(retained_targets) != 1 or retained_targets[0].get('visible') is not True or \
                retained_targets[0].get('disabled') is not False or len(snapshot_targets) != 1 or \
                snapshot_targets[0].get('visible') is not True or snapshot_targets[0].get('disabled') is not False:
            evidence['failures'].append('Diplomacy Back choice does not target the unique visible enabled original BackButton callback')
        if len(snapshot_targets) == 1:
            bounds = snapshot_targets[0].get('bounds')
            clipped = snapshot_targets[0].get('clippedBounds')
            evidence['leader_diplomacy']['back_button_bounds'] = bounds
            if type(bounds) is not dict or bounds != clipped or \
                    any(type(bounds.get(name)) not in (int, float) for name in ('x', 'y', 'width', 'height')) or \
                    bounds.get('width', 0) <= 0 or bounds.get('height', 0) <= 0:
                evidence['failures'].append('Original diplomacy BackButton is clipped or lacks its full positive hit bounds')
        posted_rows = [row.split('|') for row in posted]
        ui_rows = [row.split('|') for row in ui_inputs]
        leader_posted = [row for row in posted_rows if len(row) == 4 and row[:2] ==
                         [str(diplomacy_generation), str(back_key)]]
        leader_consumed = [row for row in ui_rows if len(row) == 4 and row[:3] ==
                            [str(diplomacy_generation), '1', str(back_key)] and row[3] == '1']
        if len(leader_posted) != 1 or len(leader_consumed) != 1:
            evidence['failures'].append('Posted LeaderHead Back click was not consumed exactly once at its recorded UI generation')
    evidence['verified'] = not evidence['failures']
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--host-build', type=Path, required=True)
    parser.add_argument('--game', type=Path, default=Path(r"C:\Program Files (x86)\Steam\steamapps\common\Sid Meier's Civilization V"))
    parser.add_argument('--language', choices=('en_US', 'ko_KR'), default='ko_KR')
    parser.add_argument('--smoke', action='store_true')
    parser.add_argument('--decisions', action='store_true', help='Run the bounded city-production-research decision smoke; requires --smoke')
    parser.add_argument('--research-tree', action='store_true', help='Use the original TechPopup handoff and TechTree in the same world window; requires --smoke --decisions')
    parser.add_argument('--tech-award', action='store_true', help='Prepare incomplete research and finish it through a normal turn and original TechAward Continue button; requires --smoke --decisions')
    parser.add_argument('--unit-actions', action='store_true', help='Exercise a published unit action and verify the real SDK activity; requires --smoke')
    parser.add_argument('--worker-build', action='store_true', help='Create one explicit worker fixture, construct a farm over normal turns, and save it; requires --smoke --decisions')
    parser.add_argument('--combat', action='store_true', help='Run melee and ranged combat against visible SDK fixtures; requires --smoke --decisions')
    parser.add_argument('--city-capture', action='store_true', help='Capture an isolated hostile city and verify the original puppet choice; requires --smoke --decisions')
    parser.add_argument('--declare-war', choices=('move', 'range'), help='Exercise the original DeclareWar popup No/Escape/Yes path and local move or ranged continuation; requires --smoke --decisions on a new game')
    parser.add_argument('--resume-run', help='Resume the final native save of an accepted interactive run from this exact sealed Host')
    parser.add_argument('--unit-assets-manifest', type=Path,
                        help='Materialize a verified original unit asset package from its PASS manifest')
    parser.add_argument('--ui-support-from-run',
                        help='Reuse hash-verified frozen UI support/catalog from a successful MOVE or restore smoke run')
    parser.add_argument('--top-panel', action='store_true',
                        help='Enable the opt-in native TopPanel interaction route in the frozen UI driver')
    parser.add_argument('--action-info-panel', action='store_true',
                        help='Enable the original SDK end-turn blocker HUD; smoke requires --decisions')
    parser.add_argument('--notification-panel', action='store_true',
                        help='Enable the original SDK notification list; requires --action-info-panel')
    parser.add_argument('--game-menu', action='store_true',
                        help='Exercise original menu callbacks, Escape, unavailable-child notice and quick save; requires --smoke --decisions --top-panel')
    parser.add_argument('--trade-route', action='store_true',
                        help='Exercise original TradeRouteOverview tabs, sorting and return using real SDK trade-route fixtures; requires --smoke --decisions --top-panel')
    parser.add_argument('--social-policy', action='store_true',
                        help='Adopt a paid branch and policy through original SocialPolicyPopup callbacks; requires --smoke --decisions --top-panel')
    parser.add_argument('--social-policy-tenets', action='store_true',
                        help='Exercise original ideology tenet cancel, free/paid adoption, and return; requires --social-policy')
    parser.add_argument('--economic-overview', action='store_true',
                        help='Exercise original economic tabs, sort/fold, nested production cancel/selection and return; requires --smoke --decisions --top-panel')
    parser.add_argument('--timeout', type=int, default=120)
    args = parser.parse_args()
    if args.decisions and not args.smoke:
        parser.error('--decisions is only valid together with --smoke')
    if args.research_tree and not (args.smoke and args.decisions):
        parser.error('--research-tree requires --smoke --decisions')
    if args.top_panel and args.smoke and not args.decisions:
        parser.error('--top-panel smoke requires --decisions so the original science area can appear after founding a city')
    if args.notification_panel and not args.action_info_panel:
        parser.error('--notification-panel requires --action-info-panel')
    if args.action_info_panel and args.smoke and not args.decisions:
        parser.error('--action-info-panel smoke requires --decisions')
    if args.game_menu and not (args.smoke and args.decisions and args.top_panel):
        parser.error('--game-menu requires --smoke --decisions --top-panel')
    if args.game_menu and (args.trade_route or args.social_policy or args.economic_overview or args.tech_award or
                          args.unit_actions or args.worker_build or args.combat or args.city_capture or args.declare_war):
        parser.error('--game-menu requires its own isolated decision scenario')
    if args.trade_route and not (args.smoke and args.decisions and args.top_panel):
        parser.error('--trade-route requires --smoke --decisions --top-panel')
    if args.trade_route and (args.tech_award or args.unit_actions or args.worker_build or args.combat or args.city_capture or args.declare_war):
        parser.error('--trade-route requires its own isolated decision scenario')
    if args.social_policy and not (args.smoke and args.decisions and args.top_panel):
        parser.error('--social-policy requires --smoke --decisions --top-panel')
    if args.social_policy_tenets and not args.social_policy:
        parser.error('--social-policy-tenets requires --social-policy')
    if args.social_policy and (args.trade_route or args.tech_award or args.unit_actions or args.worker_build or args.combat or args.city_capture or args.declare_war):
        parser.error('--social-policy requires its own isolated decision scenario')
    if args.economic_overview and not (args.smoke and args.decisions and args.top_panel):
        parser.error('--economic-overview requires --smoke --decisions --top-panel')
    if args.economic_overview and (args.trade_route or args.social_policy or args.tech_award or args.unit_actions or args.worker_build or args.combat or args.city_capture or args.declare_war):
        parser.error('--economic-overview requires its own isolated decision scenario')
    if args.tech_award and (not (args.smoke and args.decisions) or args.worker_build or args.combat or args.city_capture):
        parser.error('--tech-award requires --smoke --decisions and a separate scenario from --worker-build, --combat, and --city-capture')
    if args.unit_actions and not args.smoke:
        parser.error('--unit-actions requires --smoke')
    if args.worker_build and not (args.smoke and args.decisions):
        parser.error('--worker-build requires --smoke --decisions')
    if args.combat and not (args.smoke and args.decisions):
        parser.error('--combat requires --smoke --decisions')
    if args.combat and (args.worker_build or args.resume_run):
        parser.error('--combat is incompatible with --worker-build and --resume-run')
    if args.city_capture and not (args.smoke and args.decisions):
        parser.error('--city-capture requires --smoke --decisions')
    if args.city_capture and (args.combat or args.worker_build or args.resume_run):
        parser.error('--city-capture is incompatible with --combat, --worker-build, and --resume-run')
    if args.declare_war and (not (args.smoke and args.decisions) or args.resume_run or args.research_tree or
                             args.tech_award or args.unit_actions or args.worker_build or args.combat or args.city_capture):
        parser.error('--declare-war requires --smoke --decisions on a new game and a separate scenario from other gameplay profiles')
    # Extended profiles include the ordinary city/research regression and
    # additional original-popup interactions. The GameMenu profile adds twelve
    # stages; its first combined HUD run exhausted 300 seconds while still
    # rendering the later research-tree scenario. Each scene preparation keeps
    # its separate 60-second deadline.
    maximum_timeout = maximum_smoke_timeout(args)
    if not 30 <= args.timeout <= maximum_timeout:
        parser.error(f'Timeout must be 30 to {maximum_timeout} seconds for this profile')
    inputs = {
        'host_build': args.host_build.resolve(strict=True),
        'shared_lua_build': PROJECT / 'evidence/shared_lua_runtime/build_result.json',
        'explore_sdk_build': PROJECT / 'evidence/explore_sdk/build_result.json',
        'city_site_sdk_build': PROJECT / 'evidence/city_site_sdk/build_result.json',
        'found_value_shared_sdk_build': PROJECT / 'evidence/found_value_shared_sdk/build_result.json',
        'bundle': PROJECT / 'evidence/host/bundle.json',
    }
    documents = {name: json.loads(path.read_text(encoding='utf8')) for name, path in inputs.items()}
    for name, document in documents.items():
        if name == 'bundle':
            # The reusable bundle's inputs are its immutable payload and
            # manifest. Its historical preparation script is not frozen and
            # is not executed by this runner (the established city runner
            # uses the same payload/manifest verification boundary).
            check_artifacts(document['files'])
            check_artifacts(document['manifest'])
        else:
            check_artifacts(document)
    build, lua, found, bundle = (documents[name] for name in ('host_build', 'shared_lua_build', 'found_value_shared_sdk_build', 'bundle'))
    if build.get('status') != 'UI_WINDOW_HOST_CANDIDATE_BUILT' or not build.get('source_inputs_unchanged'):
        raise RuntimeError('Continuous game requires a sealed window host')
    sources = {Path(row['path']).name: row for row in build['sources']}
    required = {'HostMain.cpp', 'HostRun.h', 'InteractiveGameSession.h', 'InteractiveGameLoop.h',
                'WorldViewState.h', 'WorldViewRenderer.cpp', 'WorldViewRenderer.h', 'BitmapWindow.cpp',
                'LocalSdkSession.h', 'LocalTurnController.h', 'LocalTurnSignals.h'}
    if not required <= sources.keys() or '--play-smoke' not in Path(sources['HostMain.cpp']['path']).read_text(encoding='utf8'):
        raise RuntimeError('Host does not contain the continuous gameplay implementation')
    if not any('INTERACTIVE_UI_SCENE_REQUEST' in Path(row['path']).read_text(encoding='utf8')
               for row in build['sources'] if Path(row['path']).suffix.lower() in ('.h', '.cpp')):
        raise RuntimeError('Sealed Host source does not contain the retained UI scene handshake')
    if args.decisions and not any('ZEROSIS_PLAY_DECISIONS_SMOKE' in Path(row['path']).read_text(encoding='utf8')
                                  for row in build['sources'] if Path(row['path']).suffix.lower() in ('.h', '.cpp')):
        raise RuntimeError('Sealed Host source does not contain the requested decision-smoke selector')
    if args.resume_run and '--play-load-smoke' not in Path(sources['HostMain.cpp']['path']).read_text(encoding='utf8'):
        raise RuntimeError('Host does not contain the native save-to-play resume implementation')
    if args.research_tree and 'ZEROSIS_PLAY_RESEARCH_TREE_SMOKE' not in Path(sources['InteractiveGameLoop.h']['path']).read_text(encoding='utf8'):
        raise RuntimeError('Sealed Host does not contain the original research-tree world-window input sequence')
    if args.tech_award and 'ZEROSIS_PLAY_TECH_AWARD_SMOKE' not in Path(sources['InteractiveGameLoop.h']['path']).read_text(encoding='utf8'):
        raise RuntimeError('Sealed Host does not contain the normal research completion smoke')
    if args.unit_actions and 'ZEROSIS_PLAY_UNIT_ACTIONS_SMOKE' not in Path(sources['InteractiveGameLoop.h']['path']).read_text(encoding='utf8'):
        raise RuntimeError('Sealed Host does not contain the unit-action input sequence')
    if args.worker_build and 'ZEROSIS_PLAY_WORKER_BUILD_SMOKE' not in Path(sources['InteractiveGameLoop.h']['path']).read_text(encoding='utf8'):
        raise RuntimeError('Sealed Host does not contain the worker construction input sequence')
    if args.combat and 'ZEROSIS_PLAY_COMBAT_SMOKE' not in Path(sources['InteractiveGameLoop.h']['path']).read_text(encoding='utf8'):
        raise RuntimeError('Sealed Host InteractiveGameLoop source does not contain the frozen combat-smoke selector')
    if args.city_capture and 'ZEROSIS_PLAY_CITY_CAPTURE_SMOKE' not in Path(sources['InteractiveGameLoop.h']['path']).read_text(encoding='utf8'):
        raise RuntimeError('Sealed Host InteractiveGameLoop source does not contain the frozen city-capture smoke selector')
    if args.declare_war and 'ZEROSIS_PLAY_DECLARE_WAR_SMOKE' not in Path(sources['InteractiveGameLoop.h']['path']).read_text(encoding='utf8'):
        raise RuntimeError('Sealed Host InteractiveGameLoop source does not contain the isolated DeclareWar popup scenario')
    if args.social_policy and ('SocialPolicySmokeFixture.h' not in sources or
            'ZEROSIS_PLAY_SOCIAL_POLICY_SMOKE' not in Path(sources['InteractiveGameLoop.h']['path']).read_text(encoding='utf8')):
        raise RuntimeError('Sealed Host does not contain the actual SDK SocialPolicy input fixture')
    if args.economic_overview and ('EconomicOverviewSmokeFixture.h' not in sources or
            'ZEROSIS_PLAY_ECONOMIC_OVERVIEW_SMOKE' not in Path(sources['InteractiveGameLoop.h']['path']).read_text(encoding='utf8')):
        raise RuntimeError('Sealed Host does not contain the original EconomicOverview input scenario')
    if args.action_info_panel and 'ZEROSIS_PLAY_ACTION_INFO_PANEL' not in Path(sources['InteractiveGameLoop.h']['path']).read_text(encoding='utf8'):
        raise RuntimeError('Sealed Host does not contain the original ActionInfoPanel integration')
    if args.notification_panel and 'ZEROSIS_PLAY_NOTIFICATION_PANEL' not in Path(sources['InteractiveGameLoop.h']['path']).read_text(encoding='utf8'):
        raise RuntimeError('Sealed Host does not contain the original NotificationPanel integration')
    if args.game_menu and 'ZEROSIS_PLAY_GAME_MENU_SMOKE' not in Path(sources['InteractiveGameLoop.h']['path']).read_text(encoding='utf8'):
        raise RuntimeError('Sealed Host does not contain the original GameMenu input scenario')
    if lua.get('status') != 'SHARED_LUA_RUNTIME_CANDIDATE_BUILT':
        raise RuntimeError('Continuous game requires the accepted shared Lua provider')
    city = documents['city_site_sdk_build']
    verify_city_site_base(city, documents['explore_sdk_build'])
    verify_found_value_base(found, city, 'SHARED_FACTS')
    prior_unit_record = resume_unit_assets(args.resume_run) if args.resume_run else None
    unit_assets_spec = None
    if args.unit_assets_manifest:
        manifest_ref, package_ref = read_unit_assets_manifest(args.unit_assets_manifest)
        if prior_unit_record and (package_ref['sha256'], package_ref['bytes']) != \
                (prior_unit_record['package']['sha256'], prior_unit_record['package']['bytes']):
            raise RuntimeError('--unit-assets-manifest package differs from the sealed resume package')
        if args.resume_run and prior_unit_record is None:
            raise RuntimeError('--resume-run source did not use unit assets; a new package cannot be added during resume')
        unit_assets_spec = {'status': 'PASS_ORIGINAL_UNIT_PACKAGE', 'source_package': package_ref,
                            'package_source': Path(package_ref['path']), 'source_manifest': manifest_ref,
                            'source_manifest_path': Path(manifest_ref['path']),
                            'reused_from_run': args.resume_run if args.resume_run else None}
    elif prior_unit_record:
        unit_assets_spec = {'status': 'PASS_ORIGINAL_UNIT_PACKAGE',
                            'source_package': prior_unit_record['package'],
                            'package_source': prior_unit_record['package_source'],
                            'source_manifest': prior_unit_record['manifest'],
                            'source_manifest_path': None,
                            'reused_from_run': args.resume_run}
    ui_support_spec = frozen_ui_support_source(args.ui_support_from_run) if args.ui_support_from_run else None
    if ui_support_spec and args.notification_panel and not ui_support_spec['notification_panel_requested']:
        raise RuntimeError('NotificationPanel support reuse requires a source that exercised the original list')
    if ui_support_spec and args.action_info_panel and not ui_support_spec['action_info_panel_requested']:
        raise RuntimeError('ActionInfoPanel UI support reuse requires a source run that exercised the same original HUD')
    if ui_support_spec and args.game_menu and not ui_support_spec['game_menu_requested']:
        raise RuntimeError('GameMenu UI support reuse requires its original menu input scenario')
    if ui_support_spec:
        if build.get('executable', {}).get('sha256') != ui_support_spec['host_sha256']:
            raise RuntimeError('Frozen UI support inheritance requires the exact successful Host binary')
        requested_package = unit_assets_spec.get('source_package', {}).get('sha256') if unit_assets_spec else None
        if requested_package != ui_support_spec['unit_package_sha256']:
            raise RuntimeError('Frozen UI support inheritance requires the exact source unit-package profile, including absence')
    if args.top_panel:
        top_panel_driver = ui_support_spec['files']['interactive_ui_driver.py']['path'] if ui_support_spec else \
            PROJECT / 'tools/interactive_ui_driver.py'
        if '--top-panel' not in top_panel_driver.read_text(encoding='utf8'):
            raise RuntimeError('TopPanel was requested but the selected frozen UI driver has no --top-panel route')
    core = found['gamecore']
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ_') + uuid.uuid4().hex[:12]
    runtime = PROJECT / 'Build/InteractiveGameRuntime' / run_id
    evidence = PROJECT / 'evidence/interactive_game' / run_id
    runtime.mkdir(parents=True, exist_ok=False)
    evidence.mkdir(parents=True, exist_ok=False)
    rows, materializations = [], []
    for row in bundle['files']:
        name = Path(row['path']).name
        source = Path(build['executable']['path']) if name == 'ZeroSisHost_x64.exe' else Path(core['path']) if name == 'CvGameCoreDLL_Expansion2_x64.dll' else Path(row['path'])
        target = runtime / name
        if source.suffix.lower() in ('.dll', '.exe', '.bin', '.dat'):
            materializations.append(materialize_immutable(source, target, PROJECT / 'Build/RuntimeInputCache'))
        else:
            shutil.copy2(source, target)
            materializations.append({'target': str(target), 'materialization_method': 'private-copy'})
        if digest(source) != digest(target):
            raise RuntimeError('Private continuous runtime differs from its accepted input')
        rows.append({'source': str(source), **artifact(target)})
    lua_source = Path(lua['lua_dll']['path'])
    lua_target = runtime / lua_source.name
    materializations.append(materialize_immutable(lua_source, lua_target, PROJECT / 'Build/RuntimeInputCache'))
    rows.append({'source': str(lua_source), **artifact(lua_target)})
    terrain_assets = None
    if 'WorldTerrainRenderer.cpp' in sources:
        from civ5_terrain_assets import prepare as prepare_terrain_assets
        terrain_prepared = prepare_terrain_assets(args.game, PROJECT / 'Build/TerrainAssets')
        terrain_source = Path(terrain_prepared['package_path'])
        terrain_target = runtime / 'terrain-assets.bin'
        materializations.append(materialize_immutable(terrain_source, terrain_target, PROJECT / 'Build/RuntimeInputCache'))
        rows.append({'source': str(terrain_source), **artifact(terrain_target)})
        terrain_assets = {'package': artifact(terrain_target), 'source_manifest': artifact(Path(terrain_prepared['manifest_path'])),
                          'preparer': source_annotation(PROJECT / 'tools/civ5_terrain_assets.py'),
                          'originals_unchanged': terrain_prepared['originals_unchanged']}
    unit_assets = None
    if unit_assets_spec:
        unit_source = Path(unit_assets_spec['package_source'])
        unit_target = runtime / 'unit-assets.bin'
        unit_materialization = materialize_immutable(unit_source, unit_target, PROJECT / 'Build/RuntimeInputCache')
        unit_package = checked_unit_package(unit_target, unit_assets_spec['source_package']['sha256'],
                                            unit_assets_spec['source_package']['bytes'])
        materializations.append(unit_materialization)
        rows.append({'source': str(unit_source.absolute()), **artifact(unit_target),
                     'bytes': unit_target.stat().st_size})
        source_manifest_path = unit_assets_spec.get('source_manifest_path')
        source_manifest_ref = unit_assets_spec.get('source_manifest')
        manifest_copy = None
        manifest_artifact = None
        source_manifest_bytes = None
        if source_manifest_path is not None:
            source_manifest_path = Path(source_manifest_path)
            if not source_manifest_path.is_file() or digest(source_manifest_path) != source_manifest_ref.get('sha256') or \
                    source_manifest_path.stat().st_size != source_manifest_ref.get('bytes'):
                raise RuntimeError('Unit asset provenance manifest disappeared before preservation')
            source_manifest_bytes = source_manifest_path.stat().st_size
            manifest_copy = evidence / 'unit-assets-source-manifest.json'
            shutil.copy2(source_manifest_path, manifest_copy)
            if digest(source_manifest_path) != digest(manifest_copy):
                raise RuntimeError('Unit asset source manifest changed while being preserved')
            manifest_artifact = {**artifact(manifest_copy), 'bytes': manifest_copy.stat().st_size}
        elif isinstance(source_manifest_ref, dict):
            source_manifest_path = Path(source_manifest_ref['path']).resolve(strict=True)
            if digest(source_manifest_path) != source_manifest_ref.get('sha256'):
                raise RuntimeError('Prior unit asset provenance manifest changed before resume')
            source_manifest_bytes = source_manifest_path.stat().st_size
            if source_manifest_ref.get('bytes', source_manifest_bytes) != source_manifest_bytes:
                raise RuntimeError('Prior unit asset provenance manifest byte count changed before resume')
            manifest_copy = evidence / 'unit-assets-source-manifest.json'
            shutil.copy2(source_manifest_path, manifest_copy)
            if digest(source_manifest_path) != digest(manifest_copy):
                raise RuntimeError('Prior unit asset provenance manifest changed while being preserved')
            manifest_artifact = {**artifact(manifest_copy), 'bytes': manifest_copy.stat().st_size}
        else:
            raise RuntimeError('Unit asset package has no retained PASS manifest provenance')
        unit_assets = {'status': 'PASS_ORIGINAL_UNIT_PACKAGE',
                       'package': {**artifact(unit_target), 'bytes': unit_target.stat().st_size},
                       'source_package': {'original_path': str(unit_source.absolute()),
                                          'sha256': unit_package['sha256'], 'bytes': unit_package['bytes']},
                       'manifest': manifest_artifact,
                       'source_manifest': {'original_path': str(source_manifest_path),
                                           'sha256': source_manifest_ref['sha256'],
                                           'bytes': source_manifest_bytes},
                       'materialization': unit_materialization,
                       'reused_from_run': unit_assets_spec.get('reused_from_run')}
    if unit_assets:
        from unit_animation_assets import materialize as materialize_animation
        animation, animation_rows, animation_methods = materialize_animation(
            unit_target, runtime, materialize_immutable,
            prior_unit_record.get('animation_runtime') if prior_unit_record else None)
        if animation:
            animation_preparer = evidence / 'unit-animation-preparer.py'
            shutil.copy2(PROJECT / 'tools/unit_animation_assets.py', animation_preparer)
            animation['preparer'] = artifact(animation_preparer)
            unit_assets['animation_runtime'] = animation
            rows.extend(animation_rows)
            materializations.extend(animation_methods)
    manifest = runtime / 'bundle.manifest'
    manifest.write_text('ZEROSIS_HOST_BUNDLE_V4\n' + ''.join(Path(row['path']).name + '|' + row['sha256'] + '\n' for row in rows), encoding='ascii')
    rows.append(artifact(manifest))
    support_tools = runtime / 'interactive_ui_support' / 'tools'
    support_tools.mkdir(parents=True, exist_ok=False)
    support_sources = ({name: row['path'] for name, row in ui_support_spec['files'].items()
                        if name.endswith('.py')} if ui_support_spec else
                       {name: PROJECT / 'tools' / name for name in
                        ('interactive_ui_driver.py', 'render_ui_popup.py', 'ui_pixel_scene.py',
                         'ui_bitmap_fonts.py', 'civ5_ui_assets.py')})
    support_rows = {}
    for name, source in support_sources.items():
        target = support_tools / name
        shutil.copy2(source, target)
        if digest(source) != digest(target):
            raise RuntimeError('Frozen interactive UI support changed during materialization: ' + name)
        source_info = ui_support_spec['files'][name]['record_source'] if ui_support_spec else source_annotation(source)
        support_rows[name] = {'source': source_info, 'frozen': artifact(target)}
    icons_source = ui_support_spec['files']['inline_icons']['path'] if ui_support_spec else \
        PROJECT / 'evidence/ui_popup/assets/inline_icons.json'
    icon_prep_source = ui_support_spec['files']['asset_preparation_provenance']['path'] if ui_support_spec else \
        PROJECT / 'evidence/ui_popup/assets/prepared.json'
    icon_dir = runtime / 'interactive_ui_support' / 'assets'
    icon_dir.mkdir(parents=True, exist_ok=False)
    icons_target, prep_target = icon_dir / 'inline_icons.json', icon_dir / 'prepared.json'
    shutil.copy2(icons_source, icons_target)
    shutil.copy2(icon_prep_source, prep_target)
    if digest(icons_source) != digest(icons_target) or digest(icon_prep_source) != digest(prep_target):
        raise RuntimeError('Frozen inline icon catalog/provenance changed during materialization')
    icon_prep_doc = json.loads(prep_target.read_text(encoding='utf8'))
    icon_catalog_row = icon_prep_doc.get('inline_icon_catalog', {})
    expected_icon_source = (ui_support_spec['files']['inline_icons']['record_source']['original_path']
                            if ui_support_spec else str(icons_source))
    if Path(icon_catalog_row.get('path', '')).resolve() != Path(expected_icon_source).resolve() or \
            icon_catalog_row.get('sha256') != digest(icons_source):
        raise RuntimeError('Frozen icon catalog does not match its prepared-source provenance')
    support_manifest_path = runtime / 'interactive_ui_support' / 'support_manifest.json'
    support_manifest = {'tools': {name: row['frozen'] for name, row in support_rows.items()},
                        'inline_icons': artifact(icons_target),
                        'asset_preparation_provenance': artifact(prep_target)}
    support_manifest_path.write_text(json.dumps(support_manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    support_manifest_artifact = artifact(support_manifest_path)
    support_record_path = evidence / 'interactive_ui_support.json'
    icon_source_info = ui_support_spec['files']['inline_icons']['record_source'] if ui_support_spec else \
        source_annotation(icons_source)
    prep_source_info = ui_support_spec['files']['asset_preparation_provenance']['record_source'] if ui_support_spec else \
        source_annotation(icon_prep_source)
    support_record = {'tools': support_rows, 'inline_icons': {'source': icon_source_info, 'frozen': artifact(icons_target)},
                      'asset_preparation_provenance': {'source': prep_source_info, 'frozen': artifact(prep_target)},
                      'frozen_support_manifest': support_manifest_artifact,
                      'sdk_session_profile': {'ZEROSIS_UI_SMALL_ASSETS': '1',
                          'policy': 'interactive_ui_driver.drive overwrites inherited environment for every Host session'},
                      'python': artifact(Path(sys.executable)), 'manual_launcher_protocol': 'INTERACTIVE_UI_SCENE_REQUEST/UI_READY v1'}
    if ui_support_spec:
        support_record['copied_from_run'] = {'run_id': ui_support_spec['run_id'], 'status': ui_support_spec['status'],
            'result_sha256': ui_support_spec['result_sha256'], 'request_sha256': ui_support_spec['request_sha256'],
            'support_record_sha256': ui_support_spec['support_record_sha256'],
            'support_manifest_sha256': ui_support_spec['support_manifest_sha256']}
    support_record_path.write_text(json.dumps(support_record, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    references = {}
    for name, source in {**inputs, 'runner': Path(__file__).resolve(),
                         'runtime_cache_helper': PROJECT / 'tools/runtime_input_cache.py',
                         'social_policy_tenet_timeline': PROJECT / 'tools/social_policy_tenet_timeline.py',
                         'economic_overview_timeline': PROJECT / 'tools/economic_overview_timeline.py',
                         'action_info_panel_timeline': PROJECT / 'tools/action_info_panel_timeline.py',
                         'notification_panel_timeline': PROJECT / 'tools/notification_panel_timeline.py',
                         'game_menu_timeline': PROJECT / 'tools/game_menu_timeline.py',
                         'unit_panel_integration_verifier': PROJECT / 'tools/verify_interactive_decisions.py',
                         'interactive_game_verifier': PROJECT / 'tools/verify_interactive_game.py'}.items():
        target = evidence / (name + source.suffix)
        shutil.copy2(source, target)
        if digest(source) != digest(target):
            raise RuntimeError('Continuous runtime provenance changed during materialization')
        references[name] = artifact(target)
    frozen_runner_path = evidence / 'frozen_inputs' / 'run_interactive_game.py'
    frozen_runner_path.parent.mkdir(parents=True, exist_ok=False)
    shutil.copy2(Path(__file__).resolve(), frozen_runner_path)
    if digest(Path(__file__).resolve()) != digest(frozen_runner_path):
        raise RuntimeError('Frozen interactive runner changed during preservation')
    frozen_runner = artifact(frozen_runner_path)
    resume = materialize_checkpoint(args.resume_run, build, runtime, evidence) if args.resume_run else None
    if resume and resume.get('social_policy_tenets_requested', False) is not args.social_policy_tenets:
        raise RuntimeError('--resume-run must preserve the source SocialPolicy tenet profile exactly')
    if resume and resume.get('economic_overview_requested', False) is not args.economic_overview:
        raise RuntimeError('--resume-run must preserve the source EconomicOverview profile exactly')
    if resume and resume.get('action_info_panel_requested', False) is not args.action_info_panel:
        raise RuntimeError('--resume-run must preserve the source ActionInfoPanel profile exactly')
    if resume and resume.get('notification_panel_requested', False) is not args.notification_panel:
        raise RuntimeError('--resume-run must preserve the source NotificationPanel profile exactly')
    if resume and resume.get('game_menu_requested', False) is not args.game_menu:
        raise RuntimeError('--resume-run must preserve the source GameMenu profile exactly')
    policy_info_options = read_policy_info_options(resume)
    launcher = runtime / 'Play.ps1'
    python_ps = "'" + sys.executable.replace("'", "''") + "'"
    driver_ps = "'" + str(support_tools / 'interactive_ui_driver.py').replace("'", "''") + "'"
    tools_ps = "'" + str(support_tools).replace("'", "''") + "'"
    icons_ps = "'" + str(icons_target).replace("'", "''") + "'"
    support_manifest_ps = "'" + str(support_manifest_path).replace("'", "''") + "'"
    common_driver_args = " --host (Join-Path $PSScriptRoot 'ZeroSisHost_x64.exe') --cwd $PSScriptRoot --runtime $PSScriptRoot --tools " + tools_ps + " --icons " + icons_ps + " --support-manifest " + support_manifest_ps + " --support-manifest-sha256 " + support_manifest_artifact['sha256'] + " --report $UiReport --language " + args.language + " --scene-timeout 60"
    if args.top_panel:
        common_driver_args += ' --top-panel'
    if args.action_info_panel:
        common_driver_args += ' --action-info-panel'
    if args.notification_panel:
        common_driver_args += ' --notification-panel'
    policy_info_environment = "$env:ZEROSIS_UI_POLICY_INFO = '" + str(policy_info_options['policy_info']) + "'\n"
    launcher.write_text("$ErrorActionPreference = 'Stop'\n" + policy_info_environment + "$UiReport = Join-Path $PSScriptRoot ('interactive-ui-' + [guid]::NewGuid().ToString('N') + '.json')\n& " + python_ps + ' ' + driver_ps + common_driver_args + " --mode play --timeout 0\nexit $LASTEXITCODE\n", encoding='utf8')
    resume_launcher = runtime / 'Resume.ps1'
    default_checkpoint = "(Join-Path $PSScriptRoot 'checkpoint-input.zssave')" if resume else "''"
    resume_launcher.write_text("param([string]$Checkpoint = " + default_checkpoint + ")\n$ErrorActionPreference = 'Stop'\n" + policy_info_environment +
        "$UiReport = Join-Path $PSScriptRoot ('interactive-ui-' + [guid]::NewGuid().ToString('N') + '.json')\n"
        "if (-not $Checkpoint) {\n  Add-Type -AssemblyName System.Windows.Forms\n  $picker = New-Object System.Windows.Forms.OpenFileDialog\n"
        "  $picker.Title = \"ZeroSis' Civilization - 저장한 게임 열기\"\n  $picker.Filter = 'ZeroSis saves (*.zssave)|*.zssave'\n"
        "  $picker.InitialDirectory = (Join-Path $PSScriptRoot 'sessions')\n  try {\n"
        "    if ($picker.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) { return }\n    $Checkpoint = $picker.FileName\n"
        "  } finally { $picker.Dispose() }\n}\n& " + python_ps + ' ' + driver_ps + common_driver_args +
        " --mode play-load --checkpoint $Checkpoint --timeout 0\nexit $LASTEXITCODE\n", encoding='utf-8-sig')
    mode = '--play-load-smoke' if resume and args.smoke else '--play-load' if resume else '--play-smoke' if args.smoke else '--play'
    command = [sys.executable, '-B', '-X', 'utf8', str(support_tools / 'interactive_ui_driver.py'),
               '--host', str(runtime / 'ZeroSisHost_x64.exe'), '--cwd', str(runtime), '--runtime', str(runtime),
               '--tools', str(support_tools), '--icons', str(icons_target), '--support-manifest', str(support_manifest_path),
               '--support-manifest-sha256', support_manifest_artifact['sha256'],
               '--report', str(evidence / 'driver_result.json'),
               '--language', args.language, '--mode', mode.removeprefix('--'), '--timeout', str(args.timeout), '--scene-timeout', '60']
    if args.top_panel:
        command.append('--top-panel')
    if args.action_info_panel:
        command.append('--action-info-panel')
    if args.notification_panel:
        command.append('--notification-panel')
    if resume:
        command.extend(['--checkpoint', resume['checkpoint_input']['path']])
        launcher = resume_launcher
    request = {'run_id': run_id, 'command': command, 'cwd': str(runtime), 'language': args.language,
               'smoke': args.smoke, 'decisions': args.decisions, 'research_tree': args.research_tree,
               'top_panel': args.top_panel,
               'action_info_panel': args.action_info_panel,
               'notification_panel': args.notification_panel,
               'game_menu_smoke': args.game_menu,
               'trade_route_smoke': args.trade_route,
               'social_policy_smoke': args.social_policy,
               'social_policy_tenets': args.social_policy_tenets,
               'economic_overview_smoke': args.economic_overview,
               'policy_info_options': policy_info_options,
               'ui_support_from_run': ({'run_id': ui_support_spec['run_id'], 'status': ui_support_spec['status'],
                   'result_sha256': ui_support_spec['result_sha256'], 'request_sha256': ui_support_spec['request_sha256'],
                   'support_record_sha256': ui_support_spec['support_record_sha256']}
                   if ui_support_spec else None),
               'declare_war_smoke': args.declare_war,
               'tech_award': args.tech_award,
               'unit_actions': args.unit_actions,
               'combat_smoke': args.combat,
               'city_capture_smoke': args.city_capture,
               'worker_build': args.worker_build,
               'timeout': args.timeout, 'runtime_inputs': rows, 'materializations': materializations,
               'terrain_assets': terrain_assets,
               'unit_assets': unit_assets,
               'provenance': {**references, 'frozen_runner': frozen_runner},
               'launcher': artifact(launcher), 'stage_or_mods_changed': False,
               'resume_launcher': artifact(resume_launcher), 'resume_from': resume,
               'interactive_ui_support': artifact(support_record_path),
               'interactive_ui_support_inventory': {'tools': support_rows,
                   'inline_icons': support_record['inline_icons'],
                   'asset_preparation_provenance': support_record['asset_preparation_provenance'],
                   'frozen_support_manifest': support_record['frozen_support_manifest']},
               'launcher_control_metadata': {'play': artifact(runtime / 'Play.ps1'), 'resume': artifact(resume_launcher),
                   'selected': artifact(launcher),
                   'python': artifact(Path(sys.executable)), 'driver': support_rows['interactive_ui_driver.py']['frozen']},
               'sdk_session_profile': support_record['sdk_session_profile'],
               'input_profile': 'POSTED_HWND_ORIGINAL_GAME_MENU_SMOKE' if args.game_menu else
                                'POSTED_HWND_ORIGINAL_ECONOMIC_OVERVIEW_SMOKE' if args.economic_overview else
                                'POSTED_HWND_ORIGINAL_SOCIAL_POLICY_TENET_SMOKE' if args.social_policy_tenets else
                                'POSTED_HWND_ORIGINAL_SOCIAL_POLICY_SMOKE' if args.social_policy else
                                'POSTED_HWND_ORIGINAL_TRADE_ROUTE_OVERVIEW_SMOKE' if args.trade_route else
                                'POSTED_HWND_NORMAL_RESEARCH_TECH_AWARD_SMOKE' if args.tech_award else
                                'POSTED_HWND_CITY_CAPTURE_SMOKE' if args.city_capture else
                                f'POSTED_HWND_DECLARE_WAR_{args.declare_war.upper()}_SMOKE' if args.declare_war else
                                'POSTED_HWND_CONTINUOUS_COMBAT_DECISION_UI_LOOP' if args.combat else
                                'POSTED_HWND_CONTINUOUS_TREE_DECISION_UI_LOOP' if args.research_tree else
                                'POSTED_HWND_CONTINUOUS_DECISION_UI_LOOP' if args.decisions else
                                'POSTED_HWND_CONTINUOUS_GAME_LOOP' if args.smoke else 'MANUAL_CONTINUOUS_GAME_LOOP'}
    request_path = evidence / 'request.json'
    request_path.write_text(json.dumps(request, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    if not args.smoke:
        print(json.dumps({'status': 'PRIVATE_CONTINUOUS_GAME_PREPARED', 'run_id': run_id, 'launcher': str(launcher), 'request': str(request_path)}, ensure_ascii=False))
        return 0
    environment = dict(os.environ)
    environment.pop('ZEROSIS_UI_WINDOW_PROFILE', None)
    environment.pop('ZEROSIS_PLAY_DECISIONS_SMOKE', None)
    environment.pop('ZEROSIS_PLAY_RESEARCH_TREE_SMOKE', None)
    environment.pop('ZEROSIS_PLAY_TECH_AWARD_SMOKE', None)
    environment.pop('ZEROSIS_PLAY_UNIT_ACTIONS_SMOKE', None)
    environment.pop('ZEROSIS_PLAY_WORKER_BUILD_SMOKE', None)
    environment.pop('ZEROSIS_PLAY_COMBAT_SMOKE', None)
    environment.pop('ZEROSIS_PLAY_CITY_CAPTURE_SMOKE', None)
    environment.pop('ZEROSIS_PLAY_DECLARE_WAR_SMOKE', None)
    environment.pop('ZEROSIS_PLAY_TRADE_ROUTE_SMOKE', None)
    environment.pop('ZEROSIS_PLAY_SOCIAL_POLICY_SMOKE', None)
    environment.pop('ZEROSIS_PLAY_SOCIAL_POLICY_TENETS', None)
    environment.pop('ZEROSIS_PLAY_ECONOMIC_OVERVIEW_SMOKE', None)
    environment.pop('ZEROSIS_PLAY_ACTION_INFO_PANEL', None)
    environment.pop('ZEROSIS_PLAY_NOTIFICATION_PANEL', None)
    environment.pop('ZEROSIS_PLAY_GAME_MENU_SMOKE', None)
    environment['ZEROSIS_UI_POLICY_INFO'] = str(policy_info_options['policy_info'])
    if args.decisions:
        environment['ZEROSIS_PLAY_DECISIONS_SMOKE'] = '1'
    if args.research_tree:
        environment['ZEROSIS_PLAY_RESEARCH_TREE_SMOKE'] = '1'
    if args.tech_award:
        environment['ZEROSIS_PLAY_TECH_AWARD_SMOKE'] = '1'
    if args.unit_actions:
        environment['ZEROSIS_PLAY_UNIT_ACTIONS_SMOKE'] = '1'
    if args.worker_build:
        environment['ZEROSIS_PLAY_WORKER_BUILD_SMOKE'] = '1'
    if args.combat:
        environment['ZEROSIS_PLAY_COMBAT_SMOKE'] = '1'
    if args.city_capture:
        environment['ZEROSIS_PLAY_CITY_CAPTURE_SMOKE'] = '1'
    if args.declare_war:
        environment['ZEROSIS_PLAY_DECLARE_WAR_SMOKE'] = args.declare_war
    if args.trade_route:
        environment['ZEROSIS_PLAY_TRADE_ROUTE_SMOKE'] = '1'
    if args.social_policy:
        environment['ZEROSIS_PLAY_SOCIAL_POLICY_SMOKE'] = '1'
    if args.social_policy_tenets:
        environment['ZEROSIS_PLAY_SOCIAL_POLICY_TENETS'] = '1'
    if args.economic_overview:
        environment['ZEROSIS_PLAY_ECONOMIC_OVERVIEW_SMOKE'] = '1'
    if args.game_menu:
        environment['ZEROSIS_PLAY_GAME_MENU_SMOKE'] = '1'
    print('RUN_CONTINUOUS_GAME_SMOKE ' + run_id, flush=True)
    process = subprocess.Popen(command, cwd=runtime, env=environment, stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW)
    attempt_path = evidence / 'attempt.json'
    attempt_path.write_text(json.dumps({'status': 'RUNNING', 'pid': process.pid, 'command': command}, indent=2) + '\n', encoding='utf8')
    timed_out = False
    try:
        stdout, stderr = process.communicate(timeout=args.timeout + 15)
    except subprocess.TimeoutExpired:
        timed_out = True
        process.kill()
        stdout, stderr = process.communicate(timeout=10)
    attempt_path.write_text(json.dumps({'status': 'FINISHED', 'pid': process.pid,
        'host_pid': json.loads((evidence / 'driver_result.json').read_text(encoding='utf8')).get('pid')
                    if (evidence / 'driver_result.json').is_file() else None,
        'returncode': process.returncode, 'timed_out': timed_out}, indent=2) + '\n', encoding='utf8')
    (evidence / 'stdout.log').write_bytes(stdout)
    (evidence / 'stderr.log').write_bytes(stderr)
    text = (stdout + b'\n' + stderr).decode('utf8', errors='replace').replace('\r\n', '\n').replace('\r', '\n')
    support_unchanged = all(digest(Path(row['frozen']['path'])) == row['frozen']['sha256'] for row in support_rows.values()) and \
        digest(icons_target) == support_record['inline_icons']['frozen']['sha256'] and \
        digest(prep_target) == support_record['asset_preparation_provenance']['frozen']['sha256'] and \
        digest(support_manifest_path) == support_record['frozen_support_manifest']['sha256']
    launcher_control_unchanged = all(digest(Path(row['path'])) == row['sha256']
                                     for row in request['launcher_control_metadata'].values())
    unchanged = all(digest(Path(row['path'])) == row['sha256'] for row in rows) and support_unchanged and launcher_control_unchanged
    checkpoint_unchanged = resume is None or digest(Path(resume['checkpoint_input']['path'])) == resume['checkpoint_input']['sha256']
    initial_states = list((runtime / 'sessions').glob('*/play-initial-state.txt'))
    semantic_restore_equal = bool(resume and len(initial_states) == 1 and initial_states[0].read_bytes() == Path(resume['expected_state']['path']).read_bytes())
    starts = re.findall(r'^INTERACTIVE_GAME_STARTED=(\d+)\|(\d+)\|(\d+)\|(\d+)$', text, re.M)
    selected = re.findall(r'^INTERACTIVE_UNIT_SELECTED=(\d+)\|(\d+)\|(\d+)\|(\d+)$', text, re.M)
    moved = re.findall(r'^INTERACTIVE_SMOKE_MOVEMENT_VERIFIED=(\d+)\|(\d+)\|(\d+)$', text, re.M)
    next_turn = re.findall(r'^INTERACTIVE_NEXT_HUMAN_TURN=(\d+)\|(\d+)$', text, re.M)
    frames = [list(map(int, match.split('|'))) for match in re.findall(r'^INTERACTIVE_WORLD_FRAME=(.+)$', text, re.M)]
    posted = re.findall(r'^INTERACTIVE_SMOKE_POSTED=(.+)$', text, re.M)
    native_inputs = re.findall(r'^INTERACTIVE_WINDOW_INPUT=(.+)$', text, re.M)
    unit_panel_inputs = re.findall(r'^INTERACTIVE_UNIT_PANEL_INPUT=(.+)$', text, re.M)
    ui_inputs = re.findall(r'^INTERACTIVE_UI_NATIVE_INPUT=(.+)$', text, re.M)
    driver_result = json.loads((evidence / 'driver_result.json').read_text(encoding='utf8')) if (evidence / 'driver_result.json').is_file() else {}
    driver_ok = driver_result.get('status') == 'INTERACTIVE_UI_DRIVER_PASS'
    driver_scene_contexts = {row.get('context') for row in driver_result.get('scene_requests', []) if type(row) is dict}
    native_saves = re.findall(r'^INTERACTIVE_NATIVE_SAVE=(\d+)\|(.+)$', text, re.M)
    saves_with_paths_valid = native_save_paths_valid(native_saves, runtime / 'sessions')
    turn_sequence_ok = bool(len(starts) == 1 and next_turn and
        [int(row[0]) for row in next_turn] == list(range(int(starts[0][0]) + 1, int(starts[0][0]) + 1 + len(next_turn))) and
        (args.worker_build or len(next_turn) == 1))
    unexpected_rejections = unexpected_input_rejection_lines(
        text, notification_panel_requested=bool(args.notification_panel), restored=bool(resume))
    if args.decisions:
        scene_contexts = driver_scene_contexts
        success = not timed_out and process.returncode == 0 and unchanged and driver_ok and len(starts) == 1 and \
            turn_sequence_ok and len(frames) >= 5 and \
            all(len(row) == 9 and row[5] > 0 and row[6] > 0 for row in frames) and \
            len({row[5] for row in frames}) == 1 and {'production', 'research'} <= scene_contexts and \
            posted and native_inputs and len(native_saves) >= 2 and saves_with_paths_valid and \
            int(native_saves[-1][0]) == int(next_turn[-1][0]) and 'INTERACTIVE_DECISION_SMOKE_COMPLETE=1' in text and \
            'INTERACTIVE_PLAY_CLOSED=' in text and 'INTERACTIVE_GAME_SESSION_STOPPED=true' in text and \
            'INTERACTIVE_PLAY_SHUTDOWN_PASS GAMECORE_LOADED=true GAMECORE_UNLOADED=true' in text and \
            not re.search(r'HOST_FAILURE|HOST_NATIVE_EXCEPTION|HOST_CLEANUP_PENDING', text) and not unexpected_rejections
    else:
        success = not timed_out and process.returncode == 0 and unchanged and driver_ok and len(starts) == 1 and len(moved) == 1 and selected and len(next_turn) == 1 and len(frames) >= 5 and len(posted) >= 6 and len(native_inputs) >= 6 and \
        int(next_turn[0][0]) == int(starts[0][0]) + 1 and all(len(row) == 9 and row[5] > 0 and row[6] > 0 for row in frames) and \
        len({row[5] for row in frames}) == 1 and 'INTERACTIVE_SMOKE_SEQUENCE=SELECT_MOVE_EXPLICIT_SKIP_END_TURN_SAVE_WM_CLOSE' in text and \
        'INTERACTIVE_PLAY_CLOSED=' in text and 'INTERACTIVE_GAME_SESSION_STOPPED=true' in text and \
        'INTERACTIVE_PLAY_SHUTDOWN_PASS GAMECORE_LOADED=true GAMECORE_UNLOADED=true' in text and \
        not re.search(r'HOST_FAILURE|HOST_NATIVE_EXCEPTION|HOST_CLEANUP_PENDING', text) and not unexpected_rejections
    if resume:
        success = success and checkpoint_unchanged and semantic_restore_equal and int(starts[0][0]) == resume['turn'] and \
            'INTERACTIVE_RESTORE_IDLE_STATE_UNCHANGED=true' in text and len(re.findall(r'^INTERACTIVE_RESTORE_IDENTITY=', text, re.M)) == 1 and \
            len(re.findall(r'^INTERACTIVE_RESTORE_SECTIONS_EQUAL=', text, re.M)) == 1
    if args.research_tree:
        success = success and 'research-tree' in scene_contexts and \
            len(re.findall(r'^INTERACTIVE_DECISION_TREE_HANDOFF_TARGET=\d+$', text, re.M)) == 1 and \
            text.splitlines().count('INTERACTIVE_DECISION_TREE_SELECTION_REMAINS_OPEN=true') == 1
    trade_route_actions = re.findall(r'^INTERACTIVE_TRADE_ROUTE_ACTION=(\d+)\|([^|]+)\|(\d+)\|(\d+)\|(\d+)$', text, re.M)
    trade_route_complete = re.findall(r'^INTERACTIVE_TRADE_ROUTE_COMPLETE=(\d+)\|(\d+)\|STATE_UNCHANGED$', text, re.M)
    trade_route_dispatch_verified, trade_route_dispatch_failure = (
        verify_trade_route_dispatch_timeline(text) if args.trade_route else (False, None))
    trade_route_sequence_verified = bool(args.trade_route and 'trade-route' in driver_scene_contexts and
        len(trade_route_complete) == 1 and [(int(row[0]), row[1]) for row in trade_route_actions] == [
            (1, 'InternationalTradeRoutes'), (2, 'FromGPT'), (3, 'FromGPT'), (4, 'TabButtonAvailableTR'),
            (6, 'TabButtonTRWithYou'), (7, 'TabButtonYourTR'), (8, 'KEY_RETURN'), (9, 'CloseButton'),
            (10, 'InternationalTradeRoutes'), (11, 'KEY_ESCAPE')] and
        len(re.findall(r'^INTERACTIVE_TRADE_ROUTE_SHOWN=\d+\|-1\|-1\|\d+\|1$', text, re.M)) == 2 and
        len(re.findall(r'^INTERACTIVE_TRADE_ROUTE_WHEEL=\d+\|\d+\|-120$', text, re.M)) == 1 and
        trade_route_dispatch_verified)
    if args.trade_route:
        success = success and trade_route_sequence_verified
    social_policy_dispatch_verified, social_policy_dispatch_failure = (
        verify_social_policy_dispatch_timeline(text, args.social_policy_tenets) if args.social_policy else (False, None))
    social_policy_sequence_verified = bool(args.social_policy and 'social-policy' in driver_scene_contexts and
        social_policy_dispatch_verified)
    if args.social_policy:
        success = success and social_policy_sequence_verified
    economic_overview_dispatch_verified, economic_overview_dispatch_failure = (
        verify_economic_overview_timeline(text) if args.economic_overview else (False, None))
    economic_overview_sequence_verified = bool(args.economic_overview and 'economic-overview' in driver_scene_contexts and
                                              economic_overview_dispatch_verified)
    if args.economic_overview:
        success = success and economic_overview_sequence_verified
    worker_hud_profile = all(getattr(args, name, False) is True for name in (
        'smoke', 'decisions', 'research_tree', 'unit_actions', 'worker_build',
        'top_panel', 'action_info_panel', 'notification_panel'))
    action_info_dispatch_verified, action_info_dispatch_failure = (
        verify_action_info_panel_timeline(text, restored=bool(resume), worker_build_profile=worker_hud_profile)
        if args.action_info_panel else (False, None))
    action_info_sequence_verified = bool(args.action_info_panel and 'action-info-panel' in driver_scene_contexts and
                                         action_info_dispatch_verified)
    if args.action_info_panel:
        success = success and action_info_sequence_verified
    notification_dispatch_verified, notification_dispatch_failure = (
        verify_notification_panel_timeline(text, restored=bool(resume)) if args.notification_panel else (False, None))
    notification_sequence_verified = bool(args.notification_panel and 'notification-panel' in driver_scene_contexts and
                                           notification_dispatch_verified)
    if args.notification_panel:
        success = success and notification_sequence_verified
    game_menu_dispatch_verified, game_menu_dispatch_failure = (
        verify_game_menu_timeline(text) if args.game_menu else (False, None))
    game_menu_state_files = {}
    game_menu_state_equal = False
    if args.game_menu and saves_with_paths_valid:
        quick_saves = re.findall(r'^INTERACTIVE_GAME_MENU_QUICKSAVE=\d+\|\d+\|([^\n]+)$', text, re.M)
        if len(quick_saves) == 1 and any(path == quick_saves[0] for _, path in native_saves):
            menu_session = Path(quick_saves[0]).resolve(strict=True).parent
            state_paths = {phase: menu_session / ('game-menu-' + phase + '.txt') for phase in ('before', 'after')}
            if all(path.is_file() for path in state_paths.values()):
                game_menu_state_files = {phase: artifact(path) for phase, path in state_paths.items()}
                state_before = state_paths['before'].read_bytes()
                game_menu_state_equal = bool(state_before and state_before == state_paths['after'].read_bytes())
    game_menu_sequence_verified = bool(args.game_menu and game_menu_dispatch_verified and game_menu_state_equal and
                                       'game-menu' in driver_scene_contexts)
    if args.game_menu:
        success = success and game_menu_sequence_verified
    award_fixtures = [list(map(int, row.split('|'))) for row in re.findall(
        r'^INTERACTIVE_RESEARCH_COMPLETION_FIXTURE=([0-9|]+)$', text, re.M)]
    award_shown = [list(map(int, row.split('|'))) for row in re.findall(
        r'^INTERACTIVE_TECH_AWARD_SHOWN=([0-9|]+)$', text, re.M)]
    award_targets = [list(map(int, row.split('|'))) for row in re.findall(
        r'^INTERACTIVE_TECH_AWARD_TARGET=([0-9|]+)$', text, re.M)]
    award_closed = [list(map(int, row)) for row in re.findall(
        r'^INTERACTIVE_TECH_AWARD_CLOSED=(\d+)\|(\d+)\|0\|STATE_UNCHANGED$', text, re.M)]
    award_observations = [list(map(int, row.split('|'))) for row in re.findall(
        r'^INTERACTIVE_RESEARCH_COMPLETION_VERIFIED=([-0-9|]+)$', text, re.M)]
    award_verified = False
    if args.tech_award and len(award_fixtures) == len(award_shown) == len(award_targets) == len(award_closed) == len(award_observations) == 1:
        fixture, shown, target, closed, observed = (rows[0] for rows in
            (award_fixtures, award_shown, award_targets, award_closed, award_observations))
        if len(fixture) == 9 and len(shown) == 5 and len(target) == 4 and len(observed) == 5:
            tech, turn, key, generation = fixture[3], fixture[0] + 1, target[1], target[2]
            target_posts = [row.split('|') for row in posted if row.split('|')[:2] == [str(generation), str(key)]]
            target_inputs = [row.split('|') for row in ui_inputs if len(row.split('|')) == 4 and
                             row.split('|')[0] == str(generation) and row.split('|')[2:] == [str(key), '1']]
            award_verified = fixture[5] == fixture[6] - 1 and fixture[7] >= 100 and fixture[8] == 0 and \
                shown == [fixture[1], 0, tech, turn, 1] and target == [tech, key, generation, turn] and \
                closed == [key, turn] and observed[:2] == [tech, turn] and observed[2] != tech and observed[3:] == [1, 1] and \
                len(target_posts) == len(target_inputs) == 1 and 'tech-award' in scene_contexts and \
                text.splitlines().count(f'INTERACTIVE_UI_QUEUED=68|{fixture[1]}|0|{tech}') == 1 and \
                text.index('INTERACTIVE_RESEARCH_COMPLETION_FIXTURE=') < text.index('INTERACTIVE_END_TURN_ACCEPTED=') < \
                text.index('INTERACTIVE_TECH_AWARD_SHOWN=') < text.index('INTERACTIVE_TECH_AWARD_CLOSED=') < \
                text.index('INTERACTIVE_RESEARCH_COMPLETION_VERIFIED=') < text.index('INTERACTIVE_NATIVE_SAVE=')
    if args.tech_award:
        success = success and award_verified
    original_panel_required = 'INTERACTIVE_ORIGINAL_UNIT_PANEL_CONTRACT=1' in Path(
        sources['InteractiveGameLoop.h']['path']).read_text(encoding='utf8')
    original_panel_proof, original_panel_failure = None, None
    try:
        original_panel_proof = verify_unit_panel_integration(text, runtime, driver_result, frames,
            required=original_panel_required, restored=bool(resume), unit_actions=args.unit_actions,
            worker_build=args.worker_build, decisions=args.decisions,
            expected_restore_state=Path(resume['expected_state']['path']) if resume else None)
    except (RuntimeError, ValueError, KeyError, OSError, TypeError, IndexError) as error:
        original_panel_failure = str(error)
    success = success and original_panel_failure is None and (not original_panel_required or original_panel_proof is not None)
    action_targets = re.findall(r'^INTERACTIVE_UNIT_ACTION_TARGET=(\d+)\|(\d+)\|(\d+)\|(\d+)\|(\d+)$', text, re.M)
    original_action_targets = re.findall(r'^INTERACTIVE_ORIGINAL_UNIT_ACTION_TARGET=(\d+)\|(\d+)\|(\d+)$', text, re.M)
    secondary_action_targets = re.findall(r'^INTERACTIVE_ORIGINAL_UNIT_SECONDARY_TARGET=(\d+)$', text, re.M)
    action_results = re.findall(r'^INTERACTIVE_UNIT_ACTION_SMOKE_VERIFIED=(\d+)\|(\d+)\|(\d+)\|(\d+)$', text, re.M)
    action_observations = re.findall(r'^INTERACTIVE_UNIT_ACTION_OBSERVED=(\d+)\|(\d+)\|(-?\d+)\|(-?\d+)\|([01])$', text, re.M)
    original_action_commands = re.findall(r'^INTERACTIVE_ORIGINAL_UNIT_ACTION=(\d+)\|(\d+)\|(\d+)\|(\d+)$', text, re.M)
    fortify_commands = list(original_action_commands)
    if original_panel_required:
        # Only commands already proved against their exact original mission
        # packet, HWND post, consumed input, and SDK outcome may be separated.
        for command in (original_panel_proof or {}).get('mission_command_rows', []):
            fortify_commands.remove(tuple(command))
    action_commands = re.findall(r'^INTERACTIVE_UNIT_ACTION=(\d+)\|(\d+)\|(\d+)\|(-?\d+)\|(-?\d+)$', text, re.M)
    action_verified = False
    if args.unit_actions and len(action_targets) == len(original_action_targets) == len(action_results) == \
            len(action_observations) == len(fortify_commands) == 1:
        target, original_target = action_targets[0], original_action_targets[0]
        observed, activity = action_results[0], action_observations[0]
        command = fortify_commands[0]
        startup_turn, active_player = int(starts[0][0]), int(starts[0][1])
        action_posts = [row.split('|') for row in posted if len(row.split('|')) == 4 and
                        row.split('|')[:2] == [target[4], target[2]]]
        action_inputs = [row.split('|') for row in unit_panel_inputs if len(row.split('|')) == 4 and
                         row.split('|') == [target[4], '1', target[2], '1']]
        # The host emits ORIGINAL_UNIT_ACTION_TARGET only after finding the
        # stock UnitActionButton/RecommendedActionButton callback whose void1
        # is this original mission action. Its generation-bound HWND click
        # must be the consumed UnitPanel input that produced the SDK command.
        callback_order = text.find('INTERACTIVE_ORIGINAL_UNIT_ACTION_TARGET=')
        post_order = text.find(f'INTERACTIVE_SMOKE_POSTED={target[4]}|{target[2]}|')
        input_order = text.find(f'INTERACTIVE_UNIT_PANEL_INPUT={target[4]}|1|{target[2]}|1')
        command_order = re.search(r'^INTERACTIVE_ORIGINAL_UNIT_ACTION=' +
                                 re.escape('|'.join(command)) + r'$', text, re.M).start()
        observation_order = text.find('INTERACTIVE_UNIT_ACTION_OBSERVED=')
        verified_order = text.find('INTERACTIVE_UNIT_ACTION_SMOKE_VERIFIED=')
        # Bind the command to the last selection before it. CityView can
        # legitimately reselect that same unit later in the same turn.
        selections_before_command = list(re.finditer(
            r'^INTERACTIVE_UNIT_SELECTED=(\d+)\|(\d+)\|(\d+)\|(\d+)$',
            text[:command_order] if command_order >= 0 else '', re.M))
        selected_action_unit = selections_before_command[-1] if selections_before_command else None
        action_verified = int(target[0]) == int(original_target[0]) == int(command[1]) and \
            int(original_target[1]) == int(command[3]) and int(original_target[2]) == int(target[2]) and \
            int(target[1]) >= 0 and int(target[4]) > 0 and int(command[0]) == active_player and \
            int(command[2]) == startup_turn and selected_action_unit is not None and \
            selected_action_unit.groups()[:2] == (command[2], command[1]) and \
            selected_action_unit.end() < callback_order and \
            int(target[0]) == int(observed[0]) == int(activity[0]) and \
            int(target[1]) == int(observed[1]) == int(activity[1]) and \
            int(target[3]) == int(observed[2]) == int(activity[2]) and \
            int(observed[3]) == int(activity[3]) and int(observed[3]) != int(observed[2]) and \
            activity[4] == '0' and len(action_posts) == len(action_inputs) == 1 and \
            'unit-panel' in driver_scene_contexts and \
            0 <= callback_order < post_order < command_order < input_order < observation_order < verified_order
        if len(secondary_action_targets) == 1:
            secondary_key = secondary_action_targets[0]
            secondary_posts = [row.split('|') for row in posted if len(row.split('|')) == 4 and row.split('|')[1] == secondary_key]
            secondary_inputs = [row.split('|') for row in unit_panel_inputs if len(row.split('|')) == 4 and
                                row.split('|')[1:] == ['1', secondary_key, '1']]
            action_verified = action_verified and len(secondary_posts) == len(secondary_inputs) == 1 and \
                int(secondary_posts[0][0]) < int(target[4]) and int(secondary_inputs[0][0]) == int(secondary_posts[0][0])
        else:
            action_verified = action_verified and not secondary_action_targets
    if args.unit_actions:
        success = success and action_verified
    worker_fixtures = re.findall(r'^INTERACTIVE_WORKER_BUILD_FIXTURE=(\d+)\|(\d+)\|(\d+)\|(\d+)\|(\d+)\|(\d+)$', text, re.M)
    worker_targets = re.findall(r'^INTERACTIVE_WORKER_BUILD_TARGET=(\d+)\|(\d+)\|(\d+)\|(\d+)\|(\d+)\|(\d+)$', text, re.M)
    worker_started = re.findall(r'^INTERACTIVE_WORKER_BUILD_STARTED=(\d+)\|(\d+)\|(\d+)\|(\d+)\|(-?\d+)$', text, re.M)
    worker_progress = re.findall(r'^INTERACTIVE_WORKER_BUILD_PROGRESS=(\d+)\|(\d+)\|(\d+)\|(\d+)\|(\d+)\|(-?\d+)$', text, re.M)
    worker_awaiting = re.findall(r'^INTERACTIVE_WORKER_BUILD_AWAITING_TURN=(\d+)\|(\d+)\|(\d+)\|(\d+)\|(\d+)\|(\d+)\|(\d+)\|(\d+)$', text, re.M)
    worker_completed = re.findall(r'^INTERACTIVE_WORKER_BUILD_COMPLETED=(\d+)\|(\d+)\|(\d+)\|(\d+)\|(\d+)$', text, re.M)
    worker_verified = False
    if args.worker_build and len(worker_fixtures) == len(worker_targets) == len(worker_started) == len(worker_completed) == 1 and worker_progress and next_turn and native_saves:
        fixture, target, started_build, complete = worker_fixtures[0], worker_targets[0], worker_started[0], worker_completed[0]
        commands = [row for row in action_commands if row[1:] == (target[0], target[3], target[2], '-1')]
        build_posts = [row.split('|') for row in posted if len(row.split('|')) == 4 and row.split('|')[:2] == [target[5], target[4]]]
        build_inputs = [row.split('|') for row in native_inputs if len(row.split('|')) == 4 and row.split('|')[0] == target[5] and row.split('|')[2] == target[4]]
        if original_panel_required:
            commands = [row['command_row'] for row in (original_panel_proof or {}).get('missions', [])
                        if row['kind'] == 'build' and row['unit'] == int(target[0]) and
                        row['mission'] == int(target[3]) and row['data1'] == int(target[2]) and
                        row['key'] == int(target[4]) and row['generation'] == int(target[5])]
            build_inputs = [row.split('|') for row in unit_panel_inputs
                            if row.split('|') == [target[5], '1', target[4], '1']]
        # The first new human turn can still carry the progress spent by the
        # initial order. Only a queued original BUILD with renewed movement
        # justifies that one plateau; all later incomplete turns must advance.
        progress_valid, previous_progress, awaiting_used = True, int(started_build[3]), 0
        for index, row in enumerate(worker_progress):
            if row[5] == fixture[5]:
                progress_valid = progress_valid and index == len(worker_progress) - 1
            elif int(row[4]) <= previous_progress:
                pending = [entry for entry in worker_awaiting if entry[:5] == row[:5] and
                           int(entry[5]) > 0 and entry[6:] == (target[3], fixture[2])]
                progress_valid = progress_valid and index == 0 and int(row[4]) == previous_progress and len(pending) == 1
                awaiting_used += len(pending)
            previous_progress = int(row[4])
        progress_valid = progress_valid and awaiting_used == len(worker_awaiting) and awaiting_used <= 1
        worker_verified = fixture[:3] == target[:3] == started_build[:3] == complete[:3] and fixture[3] == '0' and int(fixture[4]) > 0 and \
            (int(started_build[3]) > 0 or started_build[4] == fixture[5]) and complete[3] == fixture[5] and \
            len(commands) == len(build_posts) == len(build_inputs) == 1 and build_inputs[0][3] == '1' and \
            [row[0] for row in worker_progress] == [row[0] for row in next_turn] and \
            all(row[1:4] == fixture[:3] for row in worker_progress) and worker_progress[-1][5] == fixture[5] and \
            complete[4] == next_turn[-1][0] == native_saves[-1][0] and progress_valid
    if args.worker_build:
        success = success and worker_verified
    combat_evidence = verify_combat_smoke(text, posted, native_inputs, runtime / 'sessions') if args.combat else {
        'fixtures': [], 'targets': [], 'observations': [], 'state_files': {}, 'scene_files': {},
        'verified': False, 'failures': []}
    combat_verified = bool(args.combat and combat_evidence['verified'])
    if args.combat:
        success = success and combat_verified
    city_capture_evidence = verify_city_capture_smoke(text, posted, native_inputs, ui_inputs,
        runtime / 'sessions', driver_result.get('scene_requests', []), args.language) if args.city_capture else {
        'fixtures': [], 'verified': False, 'failures': []}
    city_capture_verified = bool(args.city_capture and city_capture_evidence['verified'])
    if args.city_capture:
        success = success and city_capture_verified
    declare_war_evidence = verify_declare_war_smoke(text, posted, native_inputs, ui_inputs, runtime / 'sessions',
        driver_result.get('scene_requests', []), args.declare_war) if args.declare_war else {
        'requested_mode': None, 'validated': False, 'combat_callback_independently_verified': False,
        'failures': []}
    declare_war_verified = bool(args.declare_war and declare_war_evidence['validated'])
    if args.declare_war:
        success = success and declare_war_verified
    owned_city_required = args.decisions and 'INTERACTIVE_OWNED_CITY_SEQUENCE_VERIFIED=' in Path(
        sources['InteractiveGameLoop.h']['path']).read_text(encoding='utf8')
    owned_city_sequence = re.findall(r'^INTERACTIVE_OWNED_CITY_SEQUENCE_VERIFIED=(\d+)\|(\d+)$', text, re.M)
    owned_city_settings = re.findall(r'^INTERACTIVE_OWNED_CITY_SETTINGS_VERIFIED=(\d+)\|(-?\d+)\|([01])$', text, re.M)
    owned_city_verified = len(owned_city_sequence) == len(owned_city_settings) == 1 and \
        owned_city_sequence[0][0] == owned_city_settings[0][0]
    if owned_city_required:
        success = success and owned_city_verified
    city_management_required = args.decisions and 'INTERACTIVE_CITY_MANAGEMENT_VERIFIED=' in Path(
        sources['InteractiveGameLoop.h']['path']).read_text(encoding='utf8')
    city_management = re.findall(r'^INTERACTIVE_CITY_MANAGEMENT_VERIFIED=(\d+)\|(\d+)\|(\d+)\|(\d+)\|(\d+)\|(\d+)\|(\d+)$', text, re.M)
    city_management_fixture = re.findall(r'^INTERACTIVE_CITY_UI_FIXTURE=(\d+)\|(-?\d+)\|(-?\d+)\|(\d+)\|(\d+)\|(\d+)\|(\d+)\|(\d+)$', text, re.M)
    city_management_verified = len(city_management) == len(city_management_fixture) == 1 and owned_city_verified and \
        city_management[0][0] == city_management_fixture[0][0] == owned_city_sequence[0][0]
    if city_management_required:
        success = success and city_management_verified
    all_audio_requests = re.findall(r'^UI_AUDIO_REQUEST=([^|]+)\|([^|]+)\|(\d+)$', text, re.M)
    all_audio_status = re.findall(r'^UI_AUDIO_STATUS=([^|]+)\|([^|]+)\|(\d+)$', text, re.M)
    city_audio_requests = [row for row in all_audio_requests if row[0] == 'AS2D_INTERFACE_BUY_TILE']
    city_audio_status = [row for row in all_audio_status if row[0] == 'AS2D_INTERFACE_BUY_TILE']
    city_audio_completed = city_audio_requests == [('AS2D_INTERFACE_BUY_TILE', 'Started', '0')] and \
        city_audio_status == [('AS2D_INTERFACE_BUY_TILE', 'Completed', '0')]
    city_purchase_required = args.decisions and 'INTERACTIVE_CITY_PURCHASE_VERIFIED=' in Path(
        sources['InteractiveGameLoop.h']['path']).read_text(encoding='utf8')
    city_purchase_open = re.findall(r'^INTERACTIVE_CITY_PURCHASE_OPEN=(\d+)\|(\d+)\|(\d+)\|(\d+)$', text, re.M)
    city_purchase_targets = re.findall(r'^INTERACTIVE_CITY_PURCHASE_TARGET=(\d+)\|(\d+)\|(\d+)\|(\d+)\|(-?\d+)\|(-?\d+)\|(\d+)\|(\d+)\|(\d+)$', text, re.M)
    city_purchase_deliveries = re.findall(r'^INTERACTIVE_CITY_PURCHASE_DELIVERED=(\d+)\|(\d+)\|(-?\d+)\|(-?\d+)\|(-?\d+)\|(\d+)\|(\d+)$', text, re.M)
    city_purchase_results = re.findall(r'^INTERACTIVE_CITY_PURCHASE_VERIFIED=(\d+)\|(\d+)\|(\d+)\|(\d+)\|(-?\d+)\|(-?\d+)\|(-?\d+)\|(-?\d+)\|(\d+)\|(\d+)$', text, re.M)
    purchase_audio_requests = [row for row in all_audio_requests if row[0] == 'AS2D_INTERFACE_CITY_SCREEN_PURCHASE']
    purchase_audio_status = [row for row in all_audio_status if row[0] == 'AS2D_INTERFACE_CITY_SCREEN_PURCHASE']
    city_purchase_verified = owned_city_verified and len(city_purchase_open) == len(city_purchase_targets) == \
        len(city_purchase_deliveries) == len(city_purchase_results) == 2 and \
        [row[1] for row in city_purchase_results] == ['0', '1'] and \
        all(row[0] == owned_city_sequence[0][0] and int(row[5]) == int(row[4])-int(row[3]) and
            row[6] == row[7] and int(row[9]) == int(row[8])+1 for row in city_purchase_results) and \
        purchase_audio_requests == [('AS2D_INTERFACE_CITY_SCREEN_PURCHASE', 'Started', '0')]*2 and \
        purchase_audio_status == [('AS2D_INTERFACE_CITY_SCREEN_PURCHASE', 'Completed', '0')]*2
    if city_purchase_required:
        success = success and city_purchase_verified and city_audio_completed
    purchase_close_targets = re.findall(r'^INTERACTIVE_CITY_PURCHASE_CLOSE_TARGET=(\d+)\|(\d+)\|(\d+)\|(\d+)$', text, re.M)
    purchase_close_results = re.findall(r'^INTERACTIVE_CITY_PURCHASE_CLOSE_VERIFIED=(\d+)\|(\d+)\|0\|0\|0$', text, re.M)
    purchase_close_required = bool(resume and args.decisions and 'INTERACTIVE_CITY_PURCHASE_CLOSE_VERIFIED=' in Path(
        sources['InteractiveGameLoop.h']['path']).read_text(encoding='utf8'))
    purchase_close_verified = len(purchase_close_targets) == len(purchase_close_results) == 1 and \
        purchase_close_targets[0][:2] == purchase_close_results[0]
    if purchase_close_required:
        success = success and purchase_close_verified
    transition_inputs = [tuple(map(int, row)) for row in re.findall(
        r'^INTERACTIVE_SCENE_INPUT_RETAINED=(\d+)\|(\d+)\|(\d+)$', text, re.M)]
    transition_verified = bool(transition_inputs) and all(
        before > 0 and after == before + 1 and count > 0 for before, after, count in transition_inputs)
    transition_required = args.decisions and 'INTERACTIVE_SCENE_INPUT_RETAINED' in Path(
        sources['InteractiveGameLoop.h']['path']).read_text(encoding='utf8')
    if transition_required:
        success = success and transition_verified
    transition_closes = [tuple(map(int, row)) for row in re.findall(
        r'^INTERACTIVE_SCENE_CLOSE_RETAINED=(\d+)\|(\d+)$', text, re.M)]
    prepare_closes = [tuple(map(int, row)) for row in re.findall(
        r'^INTERACTIVE_PREPARE_CLOSE_RETAINED=(\d+)\|(\d+)$', text, re.M)]
    close_marker = 'INTERACTIVE_PREPARE_CLOSE_RETAINED=' if resume else 'INTERACTIVE_SCENE_CLOSE_RETAINED='
    close_sequence = (not transition_closes and len(prepare_closes) == 1 and all(value > 0 for value in prepare_closes[0])) \
        if resume else (not prepare_closes and len(transition_closes) == 1 and \
                       transition_closes[0][1] == transition_closes[0][0] + 1)
    transition_close_verified = close_sequence and len(native_saves) >= 2 and \
        text.index(close_marker) < text.rfind('INTERACTIVE_NATIVE_SAVE=') < text.rfind('INTERACTIVE_PLAY_CLOSED=')
    transition_close_required = 'INTERACTIVE_SCENE_CLOSE_RETAINED' in Path(
        sources['InteractiveGameLoop.h']['path']).read_text(encoding='utf8')
    if transition_close_required:
        success = success and transition_close_verified
    mouse_left = re.findall(r'^INTERACTIVE_LEFT_SELECT_STATE_UNCHANGED=(\d+\|\d+\|\d+)$', text, re.M)
    mouse_moved = re.findall(r'^INTERACTIVE_SMOKE_MOVEMENT_VERIFIED=(\d+\|\d+\|\d+)$', text, re.M)
    mouse_cancel = re.findall(r'^INTERACTIVE_RIGHT_CANCEL_VERIFIED=(\d+\|\d+\|\d+)$', text, re.M)
    mouse_queue = re.findall(r'^INTERACTIVE_SHIFT_ORDER_VERIFIED=(\d+\|\d+\|\d+)\|\d+\|\d+\|\d+$', text, re.M)
    mouse_verified = len(mouse_left) == 1 and mouse_left == mouse_moved == mouse_cancel == mouse_queue
    success = success and mouse_verified
    failures = re.findall(r'^HOST_FAILURE: (.+)$', text, re.M)
    if original_panel_failure:
        failures.append('Original UnitPanel initial selection/mission validation failed: ' + original_panel_failure)
    failures.extend('Unexpected native input rejection: ' + row for row in unexpected_rejections)
    if not mouse_verified:
        failures.append('Original left selection and right movement/queued-order/cancellation sequence did not complete')
    failures.extend(re.findall(r'^HOST_NATIVE_EXCEPTION\|(.+)$', text, re.M))
    failures.extend(combat_evidence['failures'])
    failures.extend(city_capture_evidence['failures'])
    failures.extend(declare_war_evidence['failures'])
    if args.tech_award and not award_verified:
        failures.append('Normal research completion did not pass its original TechAward, input, timer, and continued-turn contract')
    if args.trade_route and not trade_route_dispatch_verified:
        failures.append('TradeRoute input dispatch validation failed: ' + str(trade_route_dispatch_failure))
    if args.social_policy and not social_policy_dispatch_verified:
        failures.append('SocialPolicy input dispatch validation failed: ' + str(social_policy_dispatch_failure))
    if args.economic_overview and not economic_overview_dispatch_verified:
        failures.append('EconomicOverview input dispatch validation failed: ' + str(economic_overview_dispatch_failure))
    if args.notification_panel and not notification_dispatch_verified:
        failures.append('NotificationPanel native sequence validation failed: ' + str(notification_dispatch_failure))
    if args.game_menu and not game_menu_sequence_verified:
        failures.append('GameMenu native sequence, original scene or observed state preservation failed: ' + str(game_menu_dispatch_failure))
    if args.action_info_panel and not action_info_dispatch_verified:
        failures.append('ActionInfoPanel input dispatch validation failed: ' + str(action_info_dispatch_failure))
    if owned_city_required and not owned_city_verified:
        failures.append('Owned CityView did not complete its original settings, nested production, and return sequence')
    if city_management_required and not city_management_verified:
        failures.append('Owned CityView did not complete its specialist, working-plot, and paid tile purchase sequence')
    if city_purchase_required and not city_purchase_verified:
        failures.append('Original ProductionPopup did not complete both gold item purchases and their audio')
    if purchase_close_required and not purchase_close_verified:
        failures.append('Nested original purchase popup and city did not close through their host exit route')
    if driver_result.get('error'):
        failures.append('Interactive UI driver: ' + str(driver_result['error']))
    if not success and not failures:
        failures.append('Interactive validation failed: driver status=' + str(driver_result.get('status')) +
                        ', host returncode=' + str(driver_result.get('returncode')) + ', timed_out=' + str(timed_out))
    generated = [artifact(path) for path in sorted((runtime / 'sessions').rglob('*')) if path.is_file()]
    status_prefix = ('CONTINUOUS_INTERACTIVE_SDK_DECISION_UI_RESTORE_SMOKE_' if resume else
                     'CONTINUOUS_INTERACTIVE_SDK_DECISION_UI_SMOKE_') if args.decisions else \
                    ('CONTINUOUS_INTERACTIVE_SDK_WINDOW_RESTORE_SMOKE_' if resume else 'CONTINUOUS_INTERACTIVE_SDK_WINDOW_SMOKE_')
    if args.research_tree:
        status_prefix = 'CONTINUOUS_INTERACTIVE_SDK_TREE_DECISION_UI_RESTORE_SMOKE_' if resume else \
                        'CONTINUOUS_INTERACTIVE_SDK_TREE_DECISION_UI_SMOKE_'
    if args.worker_build:
        status_prefix = 'CONTINUOUS_INTERACTIVE_SDK_WORKER_BUILD_RESTORE_SMOKE_' if resume else 'CONTINUOUS_INTERACTIVE_SDK_WORKER_BUILD_SMOKE_'
    if args.combat:
        status_prefix = 'CONTINUOUS_INTERACTIVE_SDK_COMBAT_SMOKE_'
    if args.city_capture:
        status_prefix = 'CONTINUOUS_INTERACTIVE_SDK_CITY_CAPTURE_SMOKE_'
    if args.declare_war:
        status_prefix = 'CONTINUOUS_INTERACTIVE_SDK_DECLARE_WAR_' + args.declare_war.upper() + '_SMOKE_'
    if args.tech_award:
        status_prefix = 'CONTINUOUS_INTERACTIVE_SDK_TECH_AWARD_RESTORE_SMOKE_' if resume else 'CONTINUOUS_INTERACTIVE_SDK_TECH_AWARD_SMOKE_'
    result = {'status': status_prefix + ('PASS' if success else 'FAILED'),
              'run_id': run_id, 'pid': driver_result.get('pid', process.pid), 'driver_pid': process.pid, 'returncode': process.returncode,
              'exit_code_hex': f'0x{process.returncode & 0xffffffff:08X}', 'timed_out': timed_out,
              'request': artifact(request_path), 'attempt': artifact(attempt_path),
              'stdout': artifact(evidence / 'stdout.log'), 'stderr': artifact(evidence / 'stderr.log'),
              'runtime_inputs_unchanged': unchanged, 'generated_files': generated,
              'unexpected_native_input_rejections': unexpected_rejections,
              'resume_from_run': resume['run_id'] if resume else None, 'checkpoint_input_unchanged': checkpoint_unchanged,
              'semantic_restore_equal': semantic_restore_equal, 'fresh_process_restore_verified': bool(resume and success),
              'startup': starts, 'selections': selected, 'movement': moved, 'next_human_turn': next_turn,
              'frames': frames, 'posted_inputs': posted, 'native_inputs': native_inputs,
              'unit_panel_inputs': unit_panel_inputs,
              'ui_native_inputs': ui_inputs,
              'owned_city_sequence_required': owned_city_required,
              'owned_city_sequence_verified': bool(owned_city_required and owned_city_verified and success),
              'owned_city_settings': owned_city_settings,
              'city_management_required': city_management_required,
              'city_management_verified': bool(city_management_required and city_management_verified and success),
              'city_management': city_management, 'city_management_fixture': city_management_fixture,
              'city_audio_requests': city_audio_requests, 'city_audio_status': city_audio_status,
              'city_audio_wave_out_completed': city_audio_completed,
              'city_audio_human_audibility_verified': False,
              'city_purchase_required': city_purchase_required, 'city_purchase_verified': bool(city_purchase_verified and success),
              'city_purchase_open': city_purchase_open, 'city_purchase_targets': city_purchase_targets,
              'city_purchase_deliveries': city_purchase_deliveries, 'city_purchase_results': city_purchase_results,
              'purchase_audio_requests': purchase_audio_requests, 'purchase_audio_status': purchase_audio_status,
              'purchase_close_required': purchase_close_required, 'purchase_close_verified': bool(purchase_close_verified and success),
              'purchase_close_targets': purchase_close_targets, 'purchase_close_results': purchase_close_results,
              'native_window_posted_input_verified': bool(success), 'human_input_verified': False,
              'world_mouse_verified': bool(mouse_verified),
              'decision_ui_smoke_requested': args.decisions, 'decision_ui_sequence_verified': bool(args.decisions and success),
              'research_tree_requested': args.research_tree, 'research_tree_sequence_verified': bool(args.research_tree and success),
              'tech_award_requested': args.tech_award, 'tech_award_verified': bool(award_verified and success),
              'trade_route_requested': args.trade_route, 'trade_route_sequence_verified': bool(trade_route_sequence_verified and success),
              'trade_route_dispatch_verified': bool(trade_route_dispatch_verified),
              'trade_route_dispatch_failure': trade_route_dispatch_failure,
              'social_policy_requested': args.social_policy,
              'social_policy_tenets_requested': args.social_policy_tenets,
              'social_policy_sequence_verified': bool(social_policy_sequence_verified and success),
              'social_policy_tenets_sequence_verified': bool(args.social_policy_tenets and social_policy_sequence_verified and success),
              'social_policy_dispatch_verified': bool(social_policy_dispatch_verified),
              'social_policy_dispatch_failure': social_policy_dispatch_failure,
              'economic_overview_requested': args.economic_overview,
              'economic_overview_sequence_verified': bool(economic_overview_sequence_verified and success),
              'economic_overview_dispatch_verified': bool(economic_overview_dispatch_verified),
              'economic_overview_dispatch_failure': economic_overview_dispatch_failure,
              'notification_panel_requested': args.notification_panel,
              'game_menu_requested': args.game_menu,
              'game_menu_dispatch_verified': game_menu_dispatch_verified,
              'game_menu_dispatch_failure': game_menu_dispatch_failure,
              'game_menu_sequence_verified': bool(game_menu_sequence_verified and success),
              'game_menu_state_files': game_menu_state_files,
              'game_menu_state_equal': game_menu_state_equal,
              'notification_panel_sequence_verified': bool(notification_sequence_verified and success),
              'notification_panel_native_sequence_verified': notification_dispatch_verified,
              'notification_panel_input_verified': bool(not resume and notification_sequence_verified and success),
              'notification_panel_sequence_failure': notification_dispatch_failure,
              'notification_panel_verification_scope': ('RESTORED_SDK_LIST_PRESENTATION' if resume else
                  'FRESH_INPUT_AND_SDK_REMOVAL') if args.notification_panel else None,
              'action_info_panel_requested': args.action_info_panel,
              'action_info_panel_sequence_verified': bool(action_info_sequence_verified and success),
              'action_info_panel_dispatch_verified': action_info_dispatch_verified,
              'action_info_panel_dispatch_failure': action_info_dispatch_failure,
              'tech_award_fixtures': award_fixtures, 'tech_award_shown': award_shown,
              'tech_award_targets': award_targets, 'tech_award_closed': award_closed, 'tech_award_observations': award_observations,
              'unit_actions_requested': args.unit_actions, 'unit_action_sequence_verified': bool(action_verified and success),
              'original_unit_panel_contract_required': original_panel_required,
              'original_unit_panel_integration_verified': bool(original_panel_proof and success),
              'original_unit_panel_integration': original_panel_proof,
              'original_unit_panel_integration_failure': original_panel_failure,
              'unit_action_evidence_verified': action_verified,
              'unit_action_targets': action_targets, 'original_unit_action_targets': original_action_targets,
              'unit_action_commands': original_action_commands, 'unit_action_observations': action_observations,
              'unit_action_smoke_results': action_results, 'unit_action_secondary_targets': secondary_action_targets,
              'combat_smoke_requested': args.combat, 'combat_sequence_verified': bool(combat_verified and success),
              'combat_fixtures': combat_evidence['fixtures'], 'combat_targets': combat_evidence['targets'],
              'combat_observations': combat_evidence['observations'], 'combat_state_files': combat_evidence['state_files'],
              'combat_scene_files': combat_evidence['scene_files'], 'combat_verification_failures': combat_evidence['failures'],
              'city_capture_smoke_requested': args.city_capture,
              'city_capture_sequence_verified': bool(city_capture_verified and success),
              'city_capture_evidence': city_capture_evidence,
              'declare_war_smoke_requested': args.declare_war,
              'declare_war_sequence_verified': bool(declare_war_verified and success),
              'declare_war_evidence': declare_war_evidence,
              'worker_build_requested': args.worker_build, 'worker_build_sequence_verified': bool(worker_verified and success),
              'worker_build_fixtures': worker_fixtures, 'worker_build_targets': worker_targets,
              'worker_build_started': worker_started, 'worker_build_progress': worker_progress, 'worker_build_completed': worker_completed,
              'worker_build_awaiting_first_turn': worker_awaiting,
              'scene_input_transition_required': transition_required,
              'scene_input_transition_verified': transition_verified,
              'scene_input_transition_observations': transition_inputs,
              'scene_close_transition_required': transition_close_required,
              'scene_close_transition_verified': transition_close_verified,
              'scene_close_transition_observations': transition_closes,
              'ui_preparation_close_observations': prepare_closes,
              'interactive_ui_driver': artifact(evidence / 'driver_result.json') if (evidence / 'driver_result.json').is_file() else None,
              'interactive_ui_support_unchanged': support_unchanged,
              'launcher_control_metadata_unchanged': launcher_control_unchanged,
              'native_saves': native_saves, 'native_save_paths_valid': saves_with_paths_valid,
              'retail_renderer_equivalence_verified': False, 'full_gameplay_verified': False,
              'external_retail_save_compatibility_verified': False, 'stage_or_mods_changed': False,
              'failures': failures}
    result_path = evidence / 'result.json'
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps({'status': result['status'], 'run_id': run_id, 'result': str(result_path), 'failures': result['failures']}, ensure_ascii=False))
    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())
