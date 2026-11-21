"""Keep an owned Host process and prepare immutable retained UI scene requests.

This stdlib-only driver services the Host's line-oriented scene handshake. It
does not load GameCore or launch the installed game; the Host owns SDK state and
the HWND, and consumes each compiled packet after UI_READY is acknowledged.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import uuid

from ui_pixel_scene import (top_panel_interaction_contract, valid_leader_message, valid_unit_panel_lifecycle,
                            valid_declare_war_lifecycle, validate_social_policy_metadata,
                            validate_social_policy_hover_gate, compose_economic_overview_snapshot,
                            economic_walk, economic_source_ref, action_info_panel_contract,
                            notification_panel_contract, game_menu_contract, exit_confirm_contract, save_menu_contract,
                            load_menu_controls_contract, goody_hut_reward_contract,
                            PRIVATE_MENU_CONTEXTS, private_menu_contract)
from civ5_ui_assets import _reject_reparse
import found_value_runtime_options as worker_options
from found_value_runtime_options import POLICY_FIELD, child_environment, driver_policy, validate_policy

CONTEXTS = {'production', 'research', 'research-tree', 'tech-award', 'goody-hut-reward', 'ranking', 'city-capture', 'diplomacy', 'city-view', 'unit-panel', 'declare-war', 'top-panel', 'trade-route', 'social-policy', 'economic-overview', 'action-info-panel', 'notification-panel', 'game-menu', 'save-menu', 'load-menu', 'exit-confirm', *PRIVATE_MENU_CONTEXTS}
SUPPORT = ('interactive_ui_driver.py', 'render_ui_popup.py', 'ui_pixel_scene.py',
           'ui_bitmap_fonts.py', 'civ5_ui_assets.py')


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def artifact(path: Path) -> dict:
    path = Path(path).resolve(strict=True)
    return {'path': str(path), 'sha256': sha256(path), 'bytes': path.stat().st_size}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _validate_scene_output_path(folder_text: str, session: Path, sequence: int) -> Path:
    """Validate the lexical scene folder before resolving any reparse points."""
    require(Path(folder_text).is_absolute(), 'Scene output folder must be absolute')
    folder = Path(os.path.abspath(folder_text))
    _reject_reparse(folder, 'Scene output folder')
    require(folder.parent == session and folder.name == f'play-ui-{sequence}' and
            re.fullmatch(r'play-ui-[1-9][0-9]*', folder.name) is not None and
            not os.path.lexists(folder),
            'Scene output must be a new lexical play-ui-N child of the exact owning SDK session')
    return folder


def validate_private_menu_scene_proof(snapshot: dict, manifest: dict, *, context: str, closed: bool = False) -> None:
    expected = private_menu_contract(snapshot, context=context, closed=closed)
    name, kind, _ = PRIVATE_MENU_CONTEXTS[context]
    require(manifest.get('private_menu_scene') == expected and
            manifest.get('status') == 'PRIVATE_HOST_MENU_COMPONENT_SCENE_COMPILED' and
            (manifest.get('context'), manifest.get('context_name'), manifest.get('popup_kind')) == (context, name, kind) and
            manifest.get('packet_version') == 'ZSUPIX02' and manifest.get('closed_context_not_drawn') is closed and
            manifest.get('retained_input_targets') == snapshot['inputTargets'],
            'Private menu manifest lost its supported subset, source, owner or input contract')
    sources = manifest.get('original_context_sources')
    require(type(sources) is list, 'Private menu manifest source inventory is malformed')
    for field in ('originalLua', 'originalXml', 'originalStyles'):
        ref = expected[field]
        require(any(type(row) is dict and row.get('path') == ref['path'] and row.get('sha256') == ref['sha256'] for row in sources),
                'Private menu manifest omitted an exact original source: ' + field)
    def regions(targets):
        return [[target['key'], target['clippedBounds']['x'], target['clippedBounds']['y'],
                 target['clippedBounds']['x'] + target['clippedBounds']['width'],
                 target['clippedBounds']['y'] + target['clippedBounds']['height']] for target in targets]
    require(manifest.get('hit_regions') == regions(snapshot['inputTargets']) and
            manifest.get('scroll_regions') == regions(snapshot['scrollTargets']) and
            manifest.get('input_target_count') == len(snapshot['inputTargets']) and
            manifest.get('scroll_region_count') == len(snapshot['scrollTargets']),
            'Private menu packet changed its exact retained hit/scroll targets')
    if closed:
        require(manifest.get('sprite_count') == 0 and manifest.get('texture_count') == 0 and
                manifest.get('geometry') == [] and manifest.get('labels') == [],
                'Closed private child retained paint or geometry')


def validate_game_menu_scene_proof(snapshot: dict, manifest: dict, *, closed: bool = False) -> None:
    expected = game_menu_contract(snapshot, closed=closed)
    require(manifest.get('game_menu_scene') == expected and
            manifest.get('status') == 'STOCK_GAME_MENU_COMPONENT_SCENE_COMPILED' and
            manifest.get('context') == 'game-menu' and manifest.get('packet_version') == 'ZSUPIX02' and
            manifest.get('closed_context_not_drawn') is closed and
            manifest.get('retained_input_targets') == snapshot['inputTargets'],
            'GameMenu manifest lost its original source, callbacks, lifecycle, or child-context boundary')
    sources = manifest.get('original_context_sources', [])
    for field in ('originalLua', 'originalXml', 'originalMapUtilitiesLua', 'originalStyles'):
        ref = expected[field]
        require(any(type(row) is dict and row.get('path') == ref['path'] and
                    row.get('sha256') == ref['sha256'] for row in sources),
                'GameMenu manifest omitted its original source provenance: ' + field)
    def regions(targets):
        result = []
        for target in targets:
            bounds = target['clippedBounds']
            result.append([target['key'], bounds['x'], bounds['y'],
                           bounds['x'] + bounds['width'], bounds['y'] + bounds['height']])
        return result
    require(manifest.get('hit_regions') == regions(snapshot['inputTargets']) and
            manifest.get('scroll_regions') == regions(snapshot['scrollTargets']) and
            manifest.get('input_target_count') == len(snapshot['inputTargets']) and
            manifest.get('scroll_region_count') == len(snapshot['scrollTargets']),
            'GameMenu packet hit/scroll regions differ from the retained original targets')
    if closed:
        require(manifest.get('sprite_count') == 0 and manifest.get('texture_count') == 0 and
                manifest.get('geometry') == [] and manifest.get('labels') == [],
                'Closed GameMenu retained paint or geometry after its original return callback')


def validate_exit_confirm_scene_proof(snapshot: dict, manifest: dict, *, closed: bool = False) -> None:
    expected = exit_confirm_contract(snapshot, closed=closed)
    require(manifest.get('exit_confirm_scene') == expected and
            manifest.get('status') == 'STOCK_EXIT_CONFIRM_COMPONENT_SCENE_COMPILED' and
            manifest.get('context') == 'exit-confirm' and manifest.get('context_name') == 'ExitConfirm' and
            manifest.get('popup_kind') == 'ExitConfirm' and manifest.get('packet_version') == 'ZSUPIX02' and
            manifest.get('closed_context_not_drawn') is closed and
            manifest.get('retained_input_targets') == snapshot['inputTargets'],
            'ExitConfirm manifest lost its separate original modal, callbacks or parent timer boundary')
    sources = manifest.get('original_context_sources', [])
    require(type(sources) is list, 'ExitConfirm source binding is malformed')
    for field in ('originalLua', 'originalXml', 'originalStyles'):
        ref = expected[field]
        require(any(type(row) is dict and row.get('path') == ref['path'] and
                    row.get('sha256') == ref['sha256'] for row in sources),
                'ExitConfirm manifest omitted its inspected original source: ' + field)
    regions = [[target['key'], target['clippedBounds']['x'], target['clippedBounds']['y'],
                target['clippedBounds']['x'] + target['clippedBounds']['width'],
                target['clippedBounds']['y'] + target['clippedBounds']['height']]
               for target in snapshot['inputTargets']]
    require(manifest.get('hit_regions') == regions and manifest.get('scroll_regions') == [] and
            manifest.get('input_target_count') == len(regions) and manifest.get('scroll_region_count') == 0,
            'ExitConfirm packet hit order or geometry differs from its original modal targets')
    if closed:
        require(manifest.get('sprite_count') == 0 and manifest.get('texture_count') == 0 and
                manifest.get('geometry') == [] and manifest.get('labels') == [],
                'Closed ExitConfirm retained paint or geometry after PopModal')


def validate_save_menu_scene_proof(snapshot: dict, manifest: dict, *, closed: bool = False) -> None:
    expected = save_menu_contract(snapshot, closed=closed)
    require(manifest.get('save_menu_scene') == expected and
            manifest.get('status') == 'STOCK_SAVE_MENU_COMPONENT_SCENE_COMPILED' and
            manifest.get('context') == 'save-menu' and manifest.get('context_name') == 'SaveMenu' and
            manifest.get('popup_kind') == 'SaveMenu' and manifest.get('packet_version') == 'ZSUPIX02' and
            manifest.get('closed_context_not_drawn') is closed and
            manifest.get('retained_input_targets') == snapshot['inputTargets'],
            'SaveMenu manifest lost its original child screen/input/lifecycle contract')
    sources = manifest.get('original_context_sources', [])
    for ref in expected['source_refs'].values():
        require(any(type(row) is dict and row.get('path') == ref['path'] and row.get('sha256') == ref['sha256']
                    for row in sources), 'SaveMenu manifest omitted exact original source provenance')
    def regions(targets):
        return [[row['key'], row['clippedBounds']['x'], row['clippedBounds']['y'],
                 row['clippedBounds']['x'] + row['clippedBounds']['width'],
                 row['clippedBounds']['y'] + row['clippedBounds']['height']] for row in targets]
    require(manifest.get('hit_regions') == regions(snapshot['inputTargets']) and
            manifest.get('scroll_regions') == regions(snapshot['scrollTargets']) and
            manifest.get('input_target_count') == len(snapshot['inputTargets']) and
            manifest.get('scroll_region_count') == len(snapshot['scrollTargets']),
            'SaveMenu packet hit/scroll regions differ from the original retained targets')
    if closed:
        require(manifest.get('sprite_count') == 0 and manifest.get('texture_count') == 0 and
                manifest.get('geometry') == [] and manifest.get('labels') == [],
                'Closed SaveMenu retained paint or input after original OnBack')


def validate_load_menu_scene_proof(snapshot: dict, manifest: dict, *, closed: bool = False) -> None:
    expected = load_menu_controls_contract(snapshot, closed=closed)
    require(expected['source_api_bound_candidate'] is True and expected['full_original_tree_matched'] is True,
            'Host LoadMenu requires its complete original API-bound frontend candidate')
    require(manifest.get('load_menu_controls') == json.loads(json.dumps(expected)),
            'LoadMenu manifest proof differs from its exact JSON source-control contract')
    require(manifest.get('status') == 'STOCK_LOAD_MENU_CONTROL_COMPONENT_SCENE_COMPILED' and
            manifest.get('context') == 'load-menu' and manifest.get('context_name') == 'LoadMenu' and
            manifest.get('popup_kind') == 'LoadMenu' and manifest.get('packet_version') == 'ZSUPIX02' and
            manifest.get('closed_context_not_drawn') is closed and
            manifest.get('retained_input_targets') == snapshot['inputTargets'] and
            manifest.get('input_callback_coverage_claimed') is False and
            manifest.get('retail_input_semantics_verified') is False,
            'LoadMenu manifest lost its original frontend/input/lifecycle or unverified runtime boundary')
    sources = manifest.get('original_context_sources', [])
    refs = list(expected['original_sources'].values())
    refs.append({'path': str(Path(expected['original_sources']['originalXml']['path']).parents[1] / 'Styles.xml'),
                 'sha256': expected['widget_state']['originalStyleSource']['sha256']})
    for ref in refs:
        require(any(type(row) is dict and row.get('path') == ref['path'] and row.get('sha256') == ref['sha256']
                    for row in sources), 'LoadMenu manifest omitted exact original Lua/XML/style provenance')
    def regions(targets):
        return [[row['key'], row['clippedBounds']['x'], row['clippedBounds']['y'],
                 row['clippedBounds']['x'] + row['clippedBounds']['width'],
                 row['clippedBounds']['y'] + row['clippedBounds']['height']] for row in targets]
    require(manifest.get('hit_regions') == regions(snapshot['inputTargets']) and
            manifest.get('scroll_regions') == sorted(regions(snapshot['scrollTargets']), key=lambda row: row[0]) and
            manifest.get('input_target_count') == len(snapshot['inputTargets']) and
            manifest.get('scroll_region_count') == len(snapshot['scrollTargets']),
            'LoadMenu packet hit/scroll regions differ from the original retained input order')
    if closed:
        require(manifest.get('sprite_count') == 0 and manifest.get('texture_count') == 0 and
                manifest.get('geometry') == [] and manifest.get('labels') == [],
                'Closed LoadMenu retained paint or input after original OnBack')


def validate_action_info_panel_scene_proof(snapshot: dict, manifest: dict) -> None:
    expected = action_info_panel_contract(snapshot)
    require(manifest.get('action_info_panel_scene') == expected and
            manifest.get('retained_input_targets') == snapshot['inputTargets'] and
            manifest.get('scroll_regions') == [],
            'ActionInfoPanel manifest lost its original source, callbacks, or unconnected notification boundary')
    sources = manifest.get('original_context_sources', [])
    for field in ('originalLua', 'originalXml'):
        require(any(type(row) is dict and all(row.get(key) == expected[field][key]
                    for key in ('path', 'sha256')) for row in sources),
                'ActionInfoPanel manifest omitted its original Lua/XML source provenance')
    key = expected['end_turn_button_key']
    bounds = expected['end_turn_bounds']
    hits = [] if expected['button_disabled'] else [[key, bounds[0], bounds[1],
                                                   bounds[0] + bounds[2], bounds[1] + bounds[3]]]
    require(manifest.get('hit_regions') == hits and any(
            row.get('key') == key and row.get('id') == 'EndTurnButton' and
            row.get('kind') == 'GridButton' and list(row.get('bounds', [])) == bounds
            for row in manifest.get('geometry', [])),
            'ActionInfoPanel packet geometry differs from the original right/bottom anchored button')


def validate_notification_panel_scene_proof(snapshot: dict, manifest: dict) -> None:
    expected = notification_panel_contract(snapshot)
    require(manifest.get('notification_panel_scene') == expected and
            manifest.get('retained_input_targets') == snapshot['inputTargets'],
            'NotificationPanel manifest lost its original SDK rows, callback targets or scroll state')
    sources = manifest.get('original_context_sources', [])
    for field in ('originalLua', 'originalXml'):
        ref = expected[field]
        require(any(type(row) is dict and row.get('path') == ref['path'] and
                    row.get('sha256') == ref['sha256'] for row in sources),
                'NotificationPanel manifest omitted original source provenance: ' + field)
    geometry = manifest.get('geometry')
    hits, scroll_regions = manifest.get('hit_regions'), manifest.get('scroll_regions')
    require(type(geometry) is list and type(hits) is list and type(scroll_regions) is list,
            'NotificationPanel manifest lacks retained control geometry or hit/scroll regions')
    by_key = {row.get('key'): row for row in geometry if type(row) is dict}
    expected_hits = []
    for target in snapshot['inputTargets']:
        if target.get('event') == 'RightClick':
            continue
        row = by_key.get(target['key'])
        bounds = target['bounds']
        clipped = target['clippedBounds']
        expected_kind = 'Container' if target.get('event') == 'ConsumeMouse' else 'Button'
        require(type(row) is dict and row.get('id') == target.get('id') and
                row.get('kind') == expected_kind and list(row.get('bounds', [])) == [
                    bounds.get('x'), bounds.get('y'), bounds.get('width'), bounds.get('height')],
                'NotificationPanel callback/consumer geometry differs from its retained original bounds')
        if target.get('event') == 'ConsumeMouse':
            require(row.get('consume_mouse_target') is True and
                    target.get('consumeMouse') is True,
                    'NotificationPanel row blocker lost its original ConsumeMouse contract')
        else:
            require(target.get('event') in ('LeftClick', 'RightClick') and
                    row.get('input_target') is True,
                    'NotificationPanel callback target is not an original visible button')
        region = [target['key'], clipped.get('x'), clipped.get('y'),
                  clipped.get('x') + clipped.get('width'), clipped.get('y') + clipped.get('height')]
        expected_hits.append(region)
    require(hits == expected_hits,
            'NotificationPanel packet hit regions differ from original clipped callback bounds')
    expected_scrolls = []
    for target in snapshot.get('scrollTargets', []):
        clipped = target['clippedBounds']
        expected_scrolls.append([target['key'], clipped.get('x'), clipped.get('y'),
                                 clipped.get('x') + clipped.get('width'),
                                 clipped.get('y') + clipped.get('height')])
    require(scroll_regions == expected_scrolls,
            'NotificationPanel packet scroll regions differ from original clipped viewport bounds')


def validate_economic_overview_scene_proof(snapshot: dict, manifest: dict, prepared: dict, *, closed: bool) -> None:
    """Independently reconcile the sealed VMs with paint, input and scroll keys."""
    normalized, expected = compose_economic_overview_snapshot(snapshot, prepared)
    require(closed is (not snapshot['active']) and manifest.get('economic_overview_scene') == expected,
            'EconomicOverview manifest differs from its exact original VM/source/target proof')
    sources = manifest.get('original_context_sources')
    require(type(sources) is list, 'EconomicOverview manifest lacks original source provenance')
    for refs in expected['source_contract'].values():
        require(all(any(type(source) is dict and economic_source_ref(source) == ref for source in sources)
                    for ref in refs.values()),
                'EconomicOverview scene did not freeze all three original Lua/XML sources')
    geometry = manifest.get('geometry')
    require(type(geometry) is list, 'EconomicOverview scene has no retained geometry')
    owned = {node['key']: node for node in economic_walk(normalized['tree'])}
    require(all(type(row) is dict and row.get('key') in owned for row in geometry),
            'EconomicOverview geometry key escapes its original parent/child VM')
    rendered = {row['key']: row for row in geometry if not row.get('style_decoration')}
    require(len(rendered) == sum(not row.get('style_decoration') for row in geometry),
            'EconomicOverview emitted duplicate rebased control geometry')
    targets = {row['key']: row for row in normalized['inputTargets'] if row.get('event') == 'LeftClick'}
    hits = manifest.get('hit_regions')
    require(type(hits) is list and len(hits) == len(targets) and
            {row[0] for row in hits if type(row) is list and len(row) == 5} == set(targets),
            'EconomicOverview packet hits differ from its rebased original callbacks')
    for hit in hits:
        target = targets[hit[0]]
        bounds = target.get('clippedBounds')
        require(type(bounds) is dict and hit[0] in rendered and
                list(hit[1:]) == [bounds['x'], bounds['y'], bounds['x'] + bounds['width'],
                                 bounds['y'] + bounds['height']] and
                rendered[hit[0]].get('id') == target.get('id'),
                'EconomicOverview packet hit lost its child identity or clipped original bounds')
    scrolls = manifest.get('scroll_regions')
    scroll_targets = normalized['scrollTargets']
    require(type(scrolls) is list and len(scrolls) == len(scroll_targets) and
            {row[0] for row in scrolls if type(row) is list and len(row) == 5} ==
            {row['key'] for row in scroll_targets},
            'EconomicOverview scroll packet lost a rebased original child scroll target')
    scroll_by_key = {row['key']: row for row in scroll_targets}
    for region in scrolls:
        target = scroll_by_key[region[0]]
        bounds = target.get('clippedBounds')
        require(type(bounds) is dict and region[0] in rendered and
                list(region[1:]) == [bounds['x'], bounds['y'], bounds['x'] + bounds['width'],
                                    bounds['y'] + bounds['height']] and
                rendered[region[0]].get('id') == target.get('id'),
                'EconomicOverview scroll packet differs from its original clipped child bounds')
    if closed:
        require(geometry == [] and hits == [] and scrolls == [],
                'Closed EconomicOverview still paints or intercepts input')
    else:
        for slot in expected['slots']:
            if slot['active']:
                require(slot['slot_key'] in rendered and slot['context_key'] in rendered,
                        'EconomicOverview omitted the visible original child Context')
            else:
                require(not any(slot['key_base'] < key < slot['key_base'] + (1 << 48) for key in rendered),
                        'EconomicOverview rendered a hidden child VM')


def validate_social_policy_scene_proof(snapshot: dict, manifest: dict, *, closed: bool) -> None:
    """Reconcile social-policy metadata, original sources and callback payloads."""
    proof, state = manifest.get('social_policy_scene'), snapshot.get('socialPolicy')
    require(type(proof) is dict and proof.get('policy') == 'ORIGINAL_SOCIAL_POLICY_POPUP_RETAINED_TREE_V1' and
            type(state) is dict and proof.get('active_player') == state.get('activePlayer') and
            proof.get('current_tab') == state.get('currentTab') and
            proof.get('policy_info') == state.get('policyInfo') and
            proof.get('has_city') == state.get('hasCity') and
            proof.get('policy_tab_branch_ids') == state.get('policyTabBranchIds') and
            proof.get('ideology_pane_visible') == state.get('ideologyPaneVisible') and
            proof.get('policy_count') == len(state.get('policies', [])) and
            proof.get('branch_count') == len(state.get('branches', [])) and
            proof.get('branch_switch_confirmation_present') == state.get('branchSwitchConfirmationPresent') and
            proof.get('ideology_change_present') == state.get('ideologyChangePresent') and
            proof.get('retail_pixels_verified') is False and
            proof.get('all_policy_actions_use_stock_callbacks') is True and
            proof.get('full_policy_gameplay_coverage') is False,
            'SocialPolicy manifest does not preserve exact SDK state or its incomplete gameplay boundary')
    validate_social_policy_metadata(state)
    source_contract, sources = proof.get('source_contract'), manifest.get('original_context_sources', [])
    def frozen(field: str, suffix: str, snapshot_field: str) -> bool:
        row = source_contract.get(field, {}) if type(source_contract) is dict else {}
        path = row.get('path', '').replace('\\', '/') if type(row) is dict else ''
        return (path.endswith(suffix) and re.fullmatch(r'[0-9a-f]{64}', row.get('sha256', '')) is not None and
                any(item.get('path') == row.get('path') and item.get('sha256') == row.get('sha256')
                    for item in sources if type(item) is dict) and
                type(state.get(snapshot_field)) is dict and
                state[snapshot_field].get('path') == row.get('path') and
                state[snapshot_field].get('sha256') == row.get('sha256'))
    require(frozen('layout_source', '/Assets/DLC/Expansion2/UI/InGame/Popups/SocialPolicyPopup.xml',
                   'originalLayoutXml') and
            frozen('script_source', '/Assets/DLC/Expansion2/UI/InGame/Popups/SocialPolicyPopup.lua',
                   'originalLayoutLua'),
            'SocialPolicy source provenance differs from the installed original Lua/XML')
    targets = snapshot.get('inputTargets')
    require(type(targets) is list and proof.get('original_input_targets') == targets,
            'SocialPolicy original callback targets differ between SDK snapshot and renderer manifest')
    confirmation_state = proof.get('confirmation_states')
    require(type(confirmation_state) is dict and
            set(confirmation_state) == {'PolicyConfirm', 'TenetConfirm', 'ChangeIdeologyConfirm'},
            'SocialPolicy manifest lacks the three original confirmation visibility states')
    tree = snapshot.get('tree')
    tree_nodes = []
    def collect(node):
        if type(node) is dict:
            tree_nodes.append(node)
            for child in node.get('children', []):
                collect(child)
    collect(tree)
    hide_gates = [node for node in tree_nodes if node.get('kind') == 'HideOnMouseOver']
    for node in hide_gates:
        validate_social_policy_hover_gate(node)
    hover_gate_proof = manifest.get('social_policy_hover_gate_policy')
    require(type(hover_gate_proof) is dict and
            hover_gate_proof.get('policy') == 'ZEROSIS_RETAINED_SOCIAL_POLICY_INVERSE_HOVER_GATE_V1' and
            hover_gate_proof.get('gate_count') == len(hide_gates) and
            hover_gate_proof.get('hovered_keys') == [node.get('key') for node in hide_gates if node.get('hovered')] and
            hover_gate_proof.get('blank_area_hover_verified') is False and
            hover_gate_proof.get('retail_behavior_verified') is False,
            'SocialPolicy HideOnMouseOver proof differs from the retained inverse hover gate state')
    for control_id in confirmation_state:
        matches = [node for node in tree_nodes if node.get('id') == control_id]
        require(len(matches) == 1 and type(matches[0].get('hidden')) is bool and
                confirmation_state[control_id] is (matches[0]['hidden'] is False),
                'SocialPolicy manifest confirmation state differs from original control visibility: ' + control_id)
    require(state.get('ideologyChangePresent') is confirmation_state['ChangeIdeologyConfirm'],
            'SocialPolicy ideology-change metadata differs from its original confirmation control')
    if closed:
        require(not targets, 'Closed SocialPolicy context retains callback targets')
        return
    policies, branches = state.get('policies', []), state.get('branches', [])
    policy_ids = {row['id'] for row in policies if type(row) is dict and type(row.get('id')) is int}
    branch_ids = {row['id'] for row in branches if type(row) is dict and type(row.get('id')) is int}
    require(len(policy_ids) == len(policies) and len(branch_ids) == len(branches),
            'SocialPolicy SDK enumeration has malformed or duplicate IDs')
    by_id = {}
    target_keys = set()
    for target in targets:
        require(type(target) is dict and target.get('event') == 'LeftClick' and
                type(target.get('key')) is int and target['key'] > 0 and
                target['key'] not in target_keys and isinstance(target.get('id'), str),
                'SocialPolicy callback target is malformed or is not an original left-click target')
        target_keys.add(target['key'])
        by_id.setdefault(target['id'], []).append(target)
    fixed_ids = {'TabButtonSocialPolicies', 'TabButtonIdeologies', 'PolicyInfo', 'CloseButton',
                 'Yes', 'No', 'TenetConfirmYes', 'TenetConfirmNo',
                 'ChangeIdeologyConfirmYes', 'ChangeIdeologyConfirmNo',
                 'TenetCancelButton', 'SwitchIdeologyButton', 'ToIdeologyTab'}
    for control_id in by_id:
        require(control_id in fixed_ids or control_id == 'PolicyIcon' or
                re.fullmatch(r'BranchButton[0-9]+', control_id) is not None or
                re.fullmatch(r'TenetButton|IdeologyButton[123][0-9]', control_id) is not None,
                'SocialPolicy callback target is not an original supported control ID: ' + control_id)
    require(len(by_id.get('TabButtonSocialPolicies', [])) == 1 and
            len(by_id.get('TabButtonIdeologies', [])) == 1 and
            len(by_id.get('CloseButton', [])) == 1,
            'SocialPolicy lost an original tab or close callback')
    if state.get('currentTab') == 'SocialPolicies':
        require(len(by_id.get('PolicyInfo', [])) == 1,
                'SocialPolicy active tab lost the original PolicyInfo checkbox callback')
    confirmation_buttons = {
        'PolicyConfirm': ('Yes', 'No'),
        'TenetConfirm': ('TenetConfirmYes', 'TenetConfirmNo'),
        'ChangeIdeologyConfirm': ('ChangeIdeologyConfirmYes', 'ChangeIdeologyConfirmNo'),
    }
    for control_id, button_ids in confirmation_buttons.items():
        if confirmation_state[control_id]:
            require(all(len(by_id.get(button_id, [])) == 1 for button_id in button_ids),
                    'Visible SocialPolicy confirmation lacks its original Yes/No callbacks: ' + control_id)
    policy_targets = by_id.get('PolicyIcon', [])
    for target in policy_targets:
        require(type(target.get('void1')) is int and target['void1'] in policy_ids,
                'SocialPolicy PolicyIcon callback does not identify an enumerated SDK policy ID')
    if state.get('currentTab') == 'SocialPolicies':
        # Original SocialPolicyPopup.lua:457-460 excludes branch openers and
        # PurchaseByLevel tenets from PolicyIcon controls on this tab.
        branch_types_by_id = {row['id']: row['type'] for row in branches}
        policy_tab_branch_types = {branch_types_by_id[branch_id]
                                   for branch_id in state['policyTabBranchIds']}
        adoptable_ids = {row['id'] for row in policies
                         if row['branch'] in policy_tab_branch_types and
                         row.get('canAdopt') is True and row.get('blocked') is False}
        branch_targets = [row for control_id, rows in by_id.items()
                          if re.fullmatch(r'BranchButton[0-9]+', control_id) for row in rows]
        require(not adoptable_ids or any(row.get('void1') in adoptable_ids for row in policy_targets),
                'SocialPolicy has an SDK-adoptable policy but no original callback target for it')
        # The stock social-policy tab only initializes its sequential branch
        # buttons through the first PurchaseByLevel row. CanUnlockPolicyBranch
        # can also be true for owned branches and while the player has no city;
        # the original UI does not expose an enabled action in either case.
        branch_targets_by_id = {row['void1'] for row in branch_targets
                                if type(row.get('void1')) is int}
        unlockable_ids = {
            row['id'] for row in branches
            if state['hasCity'] and row['id'] in state['policyTabBranchIds'] and
            row.get('canUnlock') is True and row.get('unlocked') is False
        }
        require(unlockable_ids.issubset(branch_targets_by_id),
                'SocialPolicy is missing an original callback target for an SDK-unlockable policy-tab branch')
    for control_id, rows in by_id.items():
        match = re.fullmatch(r'BranchButton([0-9]+)', control_id)
        if match:
            branch_id = int(match.group(1))
            require(branch_id in branch_ids and branch_id in state['policyTabBranchIds'] and
                    all(row.get('void1') == branch_id for row in rows),
                    'SocialPolicy branch callback ID/void1 differs from original SDK branch ID')
    check_policy = manifest.get('social_policy_check_atlas_policy')
    require(type(check_policy) is dict and
            check_policy.get('policy') == 'CIV5_SOCIAL_POLICY_CHECK_ATLAS_FOUR_STATE_CANDIDATE_V1' and
            check_policy.get('retail_widget_state_mapping_verified') is False and
            check_policy.get('retail_pixels_verified') is False,
            'SocialPolicy checkbox atlas proof is missing or overstates retail widget state verification')
    check_assets = check_policy.get('assets')
    require(type(check_assets) is list and
            (closed or state.get('currentTab') == 'Ideologies' or bool(check_assets)) and
            all(type(row) is dict and
                str(row.get('requested_name', '')).replace('\\', '/').rsplit('/', 1)[-1].casefold() == 'checkbox.dds' and
                row.get('conversion', {}).get('width') == 32 and row.get('conversion', {}).get('height') == 128 and
                type(row.get('source')) is dict and type(row.get('output')) is dict
                for row in check_assets),
            'SocialPolicy check atlas is absent or differs from the original four-frame Checkbox.dds source')
    policy_controls = [node for node in tree_nodes if node.get('id') == 'PolicyInfo']
    if not closed and state.get('currentTab') == 'SocialPolicies':
        require(len(policy_controls) == 1 and type(policy_controls[0].get('defaultSize')) is dict,
                'SocialPolicy PolicyInfo lacks its original default-size provenance')
        default_size = policy_controls[0]['defaultSize']
        style_source = default_size.get('source')
        require(default_size.get('policy') == 'SOCIAL_POLICY_BUTTON_16_DEFAULT_CANDIDATE_V1' and
                default_size.get('style') == 'Button_16' and default_size.get('width') == 32 and
                default_size.get('height') == 32 and default_size.get('texture') ==
                'Assets/UI/Art/Controls/Checkbox.dds' and type(style_source) is dict and
                style_source.get('path', '').replace('\\', '/').endswith('/Assets/UI/Styles.xml') and
                re.fullmatch(r'[0-9a-f]{64}', style_source.get('sha256', '')) is not None and
                any(row.get('path') == style_source.get('path') and row.get('sha256') == style_source.get('sha256')
                    for row in sources if type(row) is dict),
                'SocialPolicy PolicyInfo default size is not traced to original Styles.xml Button_16')


def write_json_atomic(path: Path, value: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + '.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def parse_scene_request(line: str) -> tuple[int, str, str, str]:
    """Parse the complete Host line using the explicit retained-context allowlist."""
    request_line = line.rstrip('\r\n')
    contexts = '|'.join(re.escape(value) for value in sorted(CONTEXTS))
    match = re.fullmatch(r'INTERACTIVE_UI_SCENE_REQUEST=([1-9][0-9]*)\|(' + contexts +
                         r')\|([^|]+)\|([^|]+)', request_line)
    require(match is not None, 'Malformed INTERACTIVE_UI_SCENE_REQUEST')
    sequence, context, snapshot_text, folder_text = match.groups()
    return int(sequence), context, snapshot_text, folder_text


def prepare_request(line: str, *, runtime: Path, tools_dir: Path, icons_source: Path, support_manifest: Path,
                    support_manifest_sha256: str,
                    timeout: float = 60.0) -> dict:
    """Validate and compile one Host request; return only after packet proof."""
    sequence, context, snapshot_text, folder_text = parse_scene_request(line)
    runtime = Path(runtime).resolve(strict=True)
    sessions = (runtime / 'sessions').resolve(strict=True)
    expected_support = (runtime / 'interactive_ui_support').resolve(strict=True)
    require(Path(tools_dir).resolve(strict=True) == expected_support / 'tools' and
            Path(icons_source).resolve(strict=True) == expected_support / 'assets' / 'inline_icons.json' and
            Path(support_manifest).resolve(strict=True) == expected_support / 'support_manifest.json',
            'UI preparation inputs escaped the exact frozen runtime support directory')
    require(Path(snapshot_text).is_absolute() and Path(folder_text).is_absolute(),
            'Scene snapshot and output folder must be absolute paths')
    snapshot = Path(snapshot_text).resolve(strict=True)
    folder = _validate_scene_output_path(folder_text, snapshot.parent, sequence)
    require(snapshot.parent.parent == sessions and snapshot.parent.name and
            re.fullmatch(r'play-ui-' + str(sequence) + r'\.json', snapshot.name) is not None,
            'Scene snapshot escaped runtime/sessions/<session> or has the wrong sequence name')
    session = snapshot.parent
    require(context in CONTEXTS, 'Unsupported retained popup context')
    for name in SUPPORT:
        require((tools_dir / name).is_file(), 'Frozen preparation tool is missing: ' + name)
    require(icons_source.is_file(), 'Frozen official inline icon catalog is missing')
    require(sha256(support_manifest) == support_manifest_sha256,
            'Frozen support manifest changed before scene preparation')
    support_doc = json.loads(support_manifest.read_text(encoding='utf-8'))
    frozen_tools = support_doc.get('tools', {})
    for name in SUPPORT:
        row = frozen_tools.get(name, {})
        require((tools_dir / name).is_file() and sha256(tools_dir / name) == row.get('sha256'),
                'Frozen UI preparation tool hash differs: ' + name)
    frozen_icons = support_doc.get('inline_icons', {})
    require(sha256(icons_source) == frozen_icons.get('sha256'), 'Frozen inline icon catalog hash differs')
    frozen_prep = support_doc.get('asset_preparation_provenance', {})
    prep_path = Path(frozen_prep.get('path', ''))
    require(prep_path.is_file() and sha256(prep_path) == frozen_prep.get('sha256'),
            'Frozen inline icon provenance hash differs')
    economic_prepared = (json.loads(prep_path.read_text(encoding='utf-8'))
                         if context == 'economic-overview' else None)

    before_snapshot = sha256(snapshot)
    snapshot_doc = json.loads(snapshot.read_text(encoding='utf-8'))
    require(type(snapshot_doc) is dict, 'Retained UI snapshot is not a JSON object')
    expected_context = {'production': ('ProductionPopup', 'Production'),
                        'research': ('TechPopup', 'Research'),
                        'research-tree': ('TechTree', 'ResearchTree'),
                        'tech-award': ('TechAwardPopup', 'TechAward'),
                        'goody-hut-reward': ('GoodyHutPopup', 'GoodyHutReward'),
                        'ranking': ('WhosWinningPopup', 'WhosWinning'),
                        'city-capture': ('GenericPopup', 'CityCapture'),
                        'diplomacy': ('diplomacy', 'LeaderHead'),
                        'city-view': ('CityView', 'CityView'),
                        'unit-panel': ('UnitPanel', 'UnitPanel'),
                        'top-panel': ('TopPanel', 'TopPanel'),
                        'trade-route': ('TradeRoute', 'TradeRoute'),
                        'social-policy': ('SocialPolicyPopup', 'SocialPolicy'),
                        'economic-overview': ('EconomicOverview', 'EconomicOverview'),
                        'action-info-panel': ('ActionInfoPanel', 'ActionInfoPanel'),
                        'notification-panel': ('NotificationPanel', 'NotificationPanel'),
                        'game-menu': ('GameMenu', 'GameMenu'),
                        'exit-confirm': ('ExitConfirm', 'ExitConfirm'),
                        'save-menu': ('SaveMenu', 'SaveMenu'),
                        'load-menu': ('LoadMenu', 'LoadMenu'),
                        **{key: value[:2] for key, value in PRIVATE_MENU_CONTEXTS.items()},
                        'declare-war': ('DeclareWarPopup', 'DeclareWar')}[context]
    require((snapshot_doc.get('contextName'), snapshot_doc.get('popupKind')) == expected_context,
            'Snapshot context metadata differs from the requested renderer')
    require(type(snapshot_doc.get('active')) is bool, 'Snapshot has no explicit active/closed state')
    closed = snapshot_doc['active'] is False
    if context in PRIVATE_MENU_CONTEXTS:
        private_menu_contract(snapshot_doc, context=context, closed=closed)
    if context == 'goody-hut-reward':
        goody_hut_reward_contract(snapshot_doc, closed=closed)
    if context == 'action-info-panel':
        action_info_panel_contract(snapshot_doc)
    if context == 'game-menu':
        game_menu_contract(snapshot_doc, closed=closed)
    if context == 'save-menu':
        save_menu_contract(snapshot_doc, closed=closed)
    if context == 'exit-confirm':
        exit_confirm_contract(snapshot_doc, closed=closed)
    if context == 'load-menu':
        load_menu = load_menu_controls_contract(snapshot_doc, closed=closed)
        require(load_menu['source_api_bound_candidate'] is True and load_menu['full_original_tree_matched'] is True,
                'Host LoadMenu requires its complete original API-bound frontend candidate')
    if context == 'notification-panel':
        require(snapshot_doc.get('nonmodal') is True and snapshot_doc.get('timerSemaphore') == 0 and
                snapshot_doc.get('lifecycle') == ['queued'],
                'NotificationPanel must remain the active timer-free original world overlay')
    if closed:
        lifecycle = snapshot_doc.get('lifecycle', [])
        require(type(lifecycle) is list and all(type(item) is str for item in lifecycle),
                'Closed snapshot lifecycle is malformed')
        close_marker = 'closed' if context in ('research-tree', 'goody-hut-reward', 'city-capture', 'diplomacy', 'declare-war', 'trade-route', 'social-policy', 'economic-overview', 'game-menu', 'save-menu', 'load-menu', 'exit-confirm', 'map-menu') else 'context-hidden:' + expected_context[0]
        lifecycle_complete = (lifecycle == ['queued', 'context-hidden:CityView']
                              if context == 'city-view' else
                              valid_declare_war_lifecycle(lifecycle, active=False)
                              if context == 'declare-war' else
                              valid_unit_panel_lifecycle(lifecycle, active=False)
                              if context == 'unit-panel' else close_marker in lifecycle)
        require(lifecycle_complete and snapshot_doc.get('timerSemaphore') == 0 and
                snapshot_doc.get('inputTargets', []) == [] and snapshot_doc.get('scrollTargets', []) == [],
                'Closed popup snapshot is not a completed, zero-timer empty-input context')
        if context == 'diplomacy':
            require(lifecycle == ['queued', 'closed'] and snapshot_doc.get('leaderRootUp') is False and
                    valid_leader_message(snapshot_doc.get('leaderMessage')),
                    'Closed LeaderHead did not preserve the original response payload and return lifecycle')
    elif context == 'unit-panel':
        panel = snapshot_doc.get('unitPanel')
        lifecycle = snapshot_doc.get('lifecycle')
        require(valid_unit_panel_lifecycle(lifecycle, active=True) and
                snapshot_doc.get('timerSemaphore') == 0 and
                snapshot_doc.get('hasRetainedUnitUi') is True and type(panel) is dict and
                panel.get('visible') is True and panel.get('contextHidden') is False and
                panel.get('layoutVariant') in ('default', 'small') and
                type(panel.get('smallUIAssets')) is bool and
                panel.get('smallUIAssets') == (panel.get('layoutVariant') == 'small') and
                panel.get('retailLayoutVariantSelectionVerified') is False,
                'UnitPanel snapshot is not the retained timer-free selected-unit world overlay')
    elif context == 'city-view':
        require(snapshot_doc.get('lifecycle') == ['queued'] and
                snapshot_doc.get('timerSemaphore') == 0,
                'CityView snapshot is not on its original enter-city-screen path')
    elif context == 'top-panel':
        panel = snapshot_doc.get('topPanel')
        require(snapshot_doc.get('nonmodal') is True and
                type(snapshot_doc.get('timerSemaphores')) is int and snapshot_doc['timerSemaphores'] == 0 and
                type(panel) is dict and set(panel) == {'activePlayer', 'nonmodal', 'timerSemaphores'} and
                type(panel.get('activePlayer')) is int and panel['activePlayer'] >= 0 and
                panel.get('nonmodal') is True and type(panel.get('timerSemaphores')) is int and
                panel['timerSemaphores'] == 0 and snapshot_doc.get('timerSemaphore') == 0,
                'TopPanel snapshot differs from the retained persistent nonmodal world-overlay contract')
        top_panel_interaction = top_panel_interaction_contract(snapshot_doc)
    elif context == 'trade-route':
        route = snapshot_doc.get('tradeRoute')
        lifecycle = snapshot_doc.get('lifecycle')
        require(snapshot_doc.get('active') is True and
                type(snapshot_doc.get('timerSemaphore')) is int and snapshot_doc['timerSemaphore'] == 1 and
                type(route) is dict and route.get('modal') is True and route.get('timerSemaphore') == 1 and
                route.get('rowTemplate') == 'TRInstance' and route.get('rowSelectionPresent') is False and
                type(lifecycle) is list and len(lifecycle) == 2 and lifecycle[0] == 'queued' and
                re.fullmatch(r'shown:[0-9]+', lifecycle[1]) is not None,
                'TradeRoute snapshot differs from its active original modal route/row contract')
    elif context in ('social-policy', 'economic-overview'):
        require(snapshot_doc.get('active') is True and
                type(snapshot_doc.get('timerSemaphore')) is int and snapshot_doc['timerSemaphore'] == 1 and
                type(snapshot_doc.get('lifecycle')) is list and len(snapshot_doc['lifecycle']) == 2 and
                snapshot_doc['lifecycle'][0] == 'queued' and
                re.fullmatch(r'shown:[0-9]+', snapshot_doc['lifecycle'][1]) is not None,
                'SocialPolicy snapshot is not the active original queued/shown modal popup')
        if context == 'social-policy':
            validate_social_policy_metadata(snapshot_doc.get('socialPolicy'))
    elif context == 'diplomacy':
        message = snapshot_doc.get('leaderMessage')
        require(snapshot_doc.get('timerSemaphore') == 0 and snapshot_doc.get('lifecycle') == ['queued'] and
                snapshot_doc.get('leaderRootUp') is True and valid_leader_message(message) and
                snapshot_doc.get('cursorSemanticsVerified') is False and
                snapshot_doc.get('retailLeaderRendererVerified') is False,
                'LeaderHead is not the original untimed intro or exact human-declared-war response')
    database = (session / 'rules.db').resolve(strict=True)
    before_db = sha256(database)
    with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)) as connection:
        rows = connection.execute('SELECT Type, Red, Green, Blue, Alpha FROM Colors WHERE Type LIKE ?',
                                  ('COLOR_%',)).fetchall()
    colors = {row[0]: list(row[1:]) for row in rows}
    require(colors and len(colors) == len(rows), 'Owning SDK database has no unique COLOR_ bindings')
    folder.mkdir(parents=False, exist_ok=False)
    icon_copy = folder / 'inline_icons.json'
    shutil.copy2(icons_source, icon_copy)
    require(sha256(icon_copy) == sha256(icons_source), 'Frozen icon catalog changed while copying')
    colors_path = folder / 'inline_colors.json'
    colors_path.write_text(json.dumps({'database': artifact(database), 'colors': colors},
                                      ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    prep_inputs = {name: artifact(tools_dir / name) for name in SUPPORT}
    support_record = {'tools': prep_inputs, 'inline_icons': artifact(icon_copy),
                      'inline_icons_frozen_source': artifact(icons_source),
                      'support_manifest': artifact(support_manifest),
                      'source_snapshot': artifact(snapshot), 'rules_database': artifact(database),
                      'colors': artifact(colors_path)}
    (folder / 'preparation_inputs.json').write_text(json.dumps(support_record, ensure_ascii=False, indent=2) + '\n',
                                                    encoding='utf-8')
    manifest = folder / 'scene_manifest.json'
    log_path = folder / 'prepare.log'
    command = [sys.executable, '-B', '-X', 'utf8', str(tools_dir / 'render_ui_popup.py'),
               '--prepare', str(snapshot), '--directory', str(folder), '--manifest', str(manifest),
               '--context', context]
    if closed:
        command.append('--closed')
    try:
        process = subprocess.run(command, cwd=runtime, capture_output=True, timeout=timeout,
                                 creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except subprocess.TimeoutExpired as exc:
        out = exc.stdout or b''
        err = exc.stderr or b''
        if isinstance(out, str): out = out.encode('utf-8', errors='replace')
        if isinstance(err, str): err = err.encode('utf-8', errors='replace')
        log_path.write_bytes(out + b'\n' + err)
        failure = {'status': 'SCENE_PREPARATION_TIMEOUT', 'command': command,
                   'timeout_seconds': timeout, 'prepare_log': artifact(log_path)}
        (folder / 'preparation_failure.json').write_text(json.dumps(failure, ensure_ascii=False, indent=2) + '\n',
                                                         encoding='utf-8')
        raise RuntimeError('Retained UI scene preparation exceeded its deadline') from exc
    log_path.write_bytes(process.stdout + b'\n' + process.stderr)
    require(process.returncode == 0, 'Retained UI scene preparation failed: ' +
            (process.stdout + b'\n' + process.stderr).decode('utf-8', errors='replace')[-3000:])
    require(manifest.is_file(), 'Scene preparer did not write a manifest')
    manifest_doc = json.loads(manifest.read_text(encoding='utf-8'))
    packet_row = manifest_doc.get('packet', {})
    packet = Path(packet_row.get('path', '')).resolve(strict=True)
    require(packet.parent == folder.resolve(strict=True) and sha256(packet) == packet_row.get('sha256'),
            'Compiled packet escaped its unique session folder or hash differs')
    manifest_snapshot = manifest_doc.get('snapshot', {})
    require(manifest_doc.get('context') == context and manifest_doc.get('closed_context_not_drawn') is closed and
            Path(manifest_snapshot.get('path', '')).resolve(strict=True) == snapshot and
            manifest_snapshot.get('sha256') == before_snapshot and
            manifest_doc.get('snapshot_state_unchanged') is True,
            'Compiled scene does not bind the exact immutable retained snapshot/context')
    if context == 'goody-hut-reward':
        expected_reward = goody_hut_reward_contract(snapshot_doc, closed=closed)
        require(manifest_doc.get('goody_hut_reward_scene') == json.loads(json.dumps(expected_reward)) and
                (manifest_doc.get('context_name'), manifest_doc.get('popup_kind')) == expected_context and
                manifest_doc.get('packet_version') == 'ZSUPIX02' and
                manifest_doc.get('retained_input_targets') == snapshot_doc['inputTargets'] and
                manifest_doc.get('hit_regions') == ([] if closed else
                    [[expected_reward['close_button_key'], 860, 675, 1060, 711]]),
                'GoodyHutReward scene lost its source-bound informational lifecycle or original close hit')
        sources = manifest_doc.get('original_context_sources', [])
        for field in ('original_layout_lua', 'original_layout_xml'):
            ref = expected_reward[field]
            require(any(type(row) is dict and row.get('path') == ref['path'] and row.get('sha256') == ref['sha256']
                        for row in sources), 'GoodyHutReward manifest omitted its original source: ' + field)
    if context == 'top-panel':
        panel_proof = manifest_doc.get('top_panel_world_overlay')
        require(not closed and type(panel_proof) is dict and
                panel_proof.get('policy') == 'ZEROSIS_TOPPANEL_OVER_LIVE_WORLD_V1' and
                panel_proof.get('active_player') == snapshot_doc['topPanel']['activePlayer'] and
                panel_proof.get('nonmodal') is True and panel_proof.get('timer_semaphores') == 0 and
                panel_proof.get('full_screen_opaque_placeholder') is False and
                panel_proof.get('non_root_full_viewport_controls') == [] and
                panel_proof.get('host_compositor_required') is True and
                panel_proof.get('host_compositor_runtime_verified') is False and
                panel_proof.get('original_control_tree_and_styles_retained') is True and
                panel_proof.get('info_stack_hidden') is top_panel_interaction['info_stack_hidden'] and
                panel_proof.get('science_callback_available') is top_panel_interaction['science_callback_available'] and
                panel_proof.get('source_contract', {}).get('science_callback') ==
                    'SciencePerTurn -> OnTechClicked -> BUTTONPOPUP_TECH_TREE, Data2=-1' and
                panel_proof.get('tooltip') and
                panel_proof.get('tooltip_callbacks_executed_by_renderer') is False and
                panel_proof.get('retail_pixels_verified') is False,
                'TopPanel renderer proof differs from its strict transparent nonmodal overlay policy')
        science = panel_proof.get('science_callback_target')
        require(science == top_panel_interaction['science_callback_target'] and
                panel_proof.get('other_original_callback_targets_preserved_but_not_claimed_complete') ==
                    [row for row in snapshot_doc.get('inputTargets', []) if type(row) is dict and
                     row.get('event') != 'ConsumeMouse' and row.get('id') != 'SciencePerTurn'] and
                panel_proof.get('consume_mouse_targets') ==
                    [row for row in snapshot_doc.get('inputTargets', []) if type(row) is dict and
                     row.get('event') == 'ConsumeMouse'],
                'TopPanel callbacks/ConsumeMouse targets were omitted, changed, or overclaimed')
        tooltip_proof = panel_proof['tooltip']
        expected_tooltip_targets = [row for row in snapshot_doc.get('inputTargets', []) if type(row) is dict and
                                    row.get('event') != 'ConsumeMouse' and row.get('toolTipCallback') is True]
        tooltip_snapshot = snapshot_doc.get('topPanelTooltip')
        require(tooltip_proof.get('callback_targets') == expected_tooltip_targets and
                tooltip_proof.get('retail_placement_verified') is False and
                tooltip_proof.get('retail_autosize_verified') is False and
                tooltip_proof.get('rasterized') is False and
                tooltip_proof.get('captured_tooltip_type') ==
                    (tooltip_snapshot.get('type') if type(tooltip_snapshot) is dict else None) and
                tooltip_proof.get('captured_tooltip_tree') ==
                    (tooltip_snapshot.get('tree') if type(tooltip_snapshot) is dict else None),
                'TopPanel original tooltip callback/tree provenance was dropped or overstated')
        source_contract = panel_proof['source_contract']
        source_rows = manifest_doc.get('original_context_sources', [])
        require(source_contract.get('layout_source', {}).get('path', '').replace('\\', '/').endswith(
                    '/Assets/DLC/Expansion2/UI/InGame/TopPanel.xml') and
                source_contract.get('script_source', {}).get('path', '').replace('\\', '/').endswith(
                    '/Assets/DLC/Expansion2/UI/InGame/TopPanel.lua') and
                all(any(row.get('path') == source.get('path') and row.get('sha256') == source.get('sha256')
                        for row in source_rows)
                    for source in (source_contract.get('layout_source', {}),
                                   source_contract.get('script_source', {}))) and
                source_contract.get('consume_mouse_source_count') == len(panel_proof['consume_mouse_targets']),
                'TopPanel source hashes or original ConsumeMouse controls differ from the actual snapshot')
        require(manifest_doc.get('input_callback_coverage_claimed') is False and
                manifest_doc.get('retail_input_semantics_verified') is False,
                'TopPanel renderer overstated native callback or retail input coverage')
    if context == 'trade-route':
        route_proof = manifest_doc.get('trade_route_scene')
        route_state = snapshot_doc['tradeRoute']
        source_contract = route_proof.get('source_contract') if type(route_proof) is dict else None
        source_rows = manifest_doc.get('original_context_sources', [])
        targets = snapshot_doc.get('inputTargets', [])
        expected_targets = {'TabButtonYourTR', 'TabButtonAvailableTR', 'TabButtonTRWithYou',
                            'Domain', 'FromOwnerHeader', 'FromCityHeader', 'ToOwnerHeader', 'ToCityHeader',
                            'FromGPT', 'ToGPT', 'FromScience', 'ToScience', 'ToFood', 'ToProduction',
                            'FromReligion', 'ToReligion', 'TurnsLeft', 'CloseButton'}
        main_stacks = []
        def collect_main_stack(node: dict) -> None:
            if node.get('id') == 'MainStack':
                main_stacks.append(node)
            for child in node.get('children', []):
                collect_main_stack(child)
        collect_main_stack(snapshot_doc['tree'])
        route_tooltips = []
        if len(main_stacks) == 1:
            def collect_tooltips(node: dict) -> None:
                tooltip = node.get('tooltip')
                require(tooltip is None or type(tooltip) is str,
                        'TradeRoute row contains a malformed tooltip string')
                if tooltip:
                    route_tooltips.append({'key': node.get('key'), 'id': node.get('id', ''),
                                           'sha256': hashlib.sha256(tooltip.encode('utf-8')).hexdigest()})
                for child in node.get('children', []):
                    collect_tooltips(child)
            for row in main_stacks[0].get('children', []):
                collect_tooltips(row)
        main_scroll = route_state.get('mainScroll') if type(route_state) is dict else None
        scroll_targets = snapshot_doc.get('scrollTargets')
        scroll_geometry_keys = {'key', 'id', 'event', 'orientation', 'bounds', 'clippedBounds',
                                'scrollY', 'contentHeight', 'viewportHeight', 'maximumScroll'}
        scroll_target_keys = {'key', 'id', 'event'}
        expanded_scroll_target_keys = scroll_target_keys | {'visible', 'disabled', 'orientation', 'bounds',
                                                             'clippedBounds', 'scrollY', 'contentHeight',
                                                             'viewportHeight', 'maximumScroll'}
        def source_is_frozen(field: str, suffix: str) -> bool:
            source = source_contract.get(field, {}) if type(source_contract) is dict else {}
            source_path = source.get('path', '').replace('\\', '/')
            return (source_path.endswith(suffix) and
                    re.fullmatch(r'[0-9a-f]{64}', source.get('sha256', '')) is not None and
                    any(row.get('path') == source.get('path') and row.get('sha256') == source.get('sha256')
                        for row in source_rows))
        require(not closed and type(route_proof) is dict and
                route_proof.get('policy') == 'ORIGINAL_TRADE_ROUTE_OVERVIEW_RETAINED_TREE_V1' and
                route_proof.get('modal') is True and route_proof.get('timer_semaphore') == 1 and
                route_proof.get('row_template') == 'TRInstance' and
                len(main_stacks) == 1 and
                route_proof.get('retained_row_count') == len(main_stacks[0].get('children', [])) and
                route_state.get('visibleRowCount') == len(main_stacks[0].get('children', [])) and
                type(route_state.get('activePlayer')) is int and route_state['activePlayer'] >= 0 and
                route_proof.get('selected_tab') in ('YourTR', 'AvailableTR', 'TRWithYou') and
                route_proof.get('selected_tab') == route_state.get('selectedTab') and
                route_proof.get('row_selection_present') is False and
                route_proof.get('row_tooltips_rasterized') is False and
                route_proof.get('row_tooltip_control_digests') == route_tooltips and
                route_proof.get('original_input_targets') == targets and
                {row.get('id') for row in targets if type(row) is dict} == expected_targets and
                len(targets) == len(expected_targets) and
                all(row.get('event') == 'LeftClick' for row in targets) and
                route_proof.get('retail_pixels_verified') is False and
                route_proof.get('retail_style_timing_verified') is False and
                source_is_frozen('layout_source', '/Assets/DLC/Expansion2/UI/InGame/Popups/TradeRouteOverview.xml') and
                source_is_frozen('script_source', '/Assets/DLC/Expansion2/UI/InGame/Popups/TradeRouteOverview.lua') and
                source_is_frozen('helper_source', '/Assets/DLC/Expansion2/UI/InGame/Popups/TradeRouteHelpers.lua') and
                route_state.get('originalLayoutXml') == source_contract.get('layout_source') and
                route_state.get('originalLayoutLua') == source_contract.get('script_source') and
                route_state.get('originalHelpersLua') == source_contract.get('helper_source') and
                source_contract.get('tab_control_ids') == ['TabButtonAvailableTR', 'TabButtonTRWithYou', 'TabButtonYourTR'] and
                len(source_contract.get('sortable_header_ids', [])) == 14 and
                set(source_contract.get('row_control_ids', [])) ==
                    {'Root', 'Domain_Land', 'Domain_Sea', 'FromCivIconBG', 'FromCivIconShadow',
                     'FromCivIcon', 'FromCivIconHighlight', 'FromCity', 'ToCivIconBG',
                     'ToCivIconShadow', 'ToCivIcon', 'ToCivIconHighlight', 'ToCity', 'FromGPT',
                     'ToGPT', 'FromScience', 'ToScience', 'ToFood', 'ToProduction',
                     'FromReligion', 'ToReligion', 'TurnsLeft', 'Divider'} and
                type(scroll_targets) is list and len(scroll_targets) == 1 and
                type(scroll_targets[0]) is dict and
                set(scroll_targets[0]) in (scroll_target_keys, expanded_scroll_target_keys) and
                type(main_scroll) is dict and set(main_scroll) == scroll_geometry_keys and
                main_scroll.get('id') == 'MainScroll' and main_scroll.get('event') == 'Scroll' and
                main_scroll.get('orientation') == 'vertical' and
                main_scroll.get('key') == scroll_targets[0].get('key') and
                scroll_targets[0].get('id') == 'MainScroll' and
                scroll_targets[0].get('event') == 'Scroll' and
                (set(scroll_targets[0]) == scroll_target_keys or
                 (scroll_targets[0].get('visible') is True and scroll_targets[0].get('disabled') is False and
                  scroll_targets[0].get('orientation') == 'vertical' and
                  scroll_targets[0].get('bounds') == main_scroll.get('bounds') and
                  scroll_targets[0].get('clippedBounds') == main_scroll.get('clippedBounds') and
                  all(scroll_targets[0].get(field) == main_scroll.get(field)
                      for field in ('scrollY', 'contentHeight', 'viewportHeight', 'maximumScroll')))) and
                route_proof.get('main_scroll') == main_scroll and
                manifest_doc.get('scroll_region_count') == 1 and
                route_proof.get('scroll_target_policy', '').startswith('exact original MainScroll target bounds') and
                'not rasterized' in route_proof.get('row_tooltip_policy', ''),
                'TradeRoute scene proof dropped original controls, rows, scroll, tooltip boundary or source provenance')
    if context == 'social-policy':
        validate_social_policy_scene_proof(snapshot_doc, manifest_doc, closed=closed)
    if context == 'economic-overview':
        require(manifest_doc.get('economic_overview_prepared_source') == frozen_prep and
                sha256(prep_path) == frozen_prep.get('sha256'),
                'EconomicOverview scene is not bound to the same frozen prepared.json')
        validate_economic_overview_scene_proof(snapshot_doc, manifest_doc, economic_prepared, closed=closed)
    if context == 'action-info-panel':
        validate_action_info_panel_scene_proof(snapshot_doc, manifest_doc)
    if context == 'notification-panel':
        validate_notification_panel_scene_proof(snapshot_doc, manifest_doc)
    if context == 'game-menu':
        validate_game_menu_scene_proof(snapshot_doc, manifest_doc, closed=closed)
    if context == 'save-menu':
        validate_save_menu_scene_proof(snapshot_doc, manifest_doc, closed=closed)
    if context == 'exit-confirm':
        validate_exit_confirm_scene_proof(snapshot_doc, manifest_doc, closed=closed)
    if context == 'load-menu':
        validate_load_menu_scene_proof(snapshot_doc, manifest_doc, closed=closed)
    if context in PRIVATE_MENU_CONTEXTS:
        validate_private_menu_scene_proof(snapshot_doc, manifest_doc, context=context, closed=closed)
    after_snapshot, after_db = sha256(snapshot), sha256(database)
    require(before_snapshot == after_snapshot and before_db == after_db,
            'Snapshot or owning SDK database changed during UI preparation')
    result = {'sequence': sequence, 'context': context, 'closed': closed, 'session': str(session),
              'snapshot_before_sha256': before_snapshot, 'snapshot_after_sha256': after_snapshot,
              'database_sha256': before_db, 'folder': str(folder.resolve(strict=True)),
              'packet': packet_row, 'manifest': artifact(manifest), 'prepare_log': artifact(log_path),
              'leaderhead_surface': (manifest_doc.get('leaderhead_display_policy')
                                     if context == 'diplomacy' else None),
              'top_panel_world_overlay': (manifest_doc.get('top_panel_world_overlay')
                                          if context == 'top-panel' else None),
              'trade_route_scene': (manifest_doc.get('trade_route_scene')
                                    if context == 'trade-route' else None),
              'social_policy_scene': (manifest_doc.get('social_policy_scene')
                                      if context == 'social-policy' else None),
              'economic_overview_scene': (manifest_doc.get('economic_overview_scene')
                                          if context == 'economic-overview' else None),
              'action_info_panel_scene': (manifest_doc.get('action_info_panel_scene')
                                          if context == 'action-info-panel' else None),
              'notification_panel_scene': (manifest_doc.get('notification_panel_scene')
                                           if context == 'notification-panel' else None),
              'game_menu_scene': (manifest_doc.get('game_menu_scene')
                                  if context == 'game-menu' else None),
              'exit_confirm_scene': (manifest_doc.get('exit_confirm_scene')
                                      if context == 'exit-confirm' else None),
               'save_menu_scene': (manifest_doc.get('save_menu_scene')
                                  if context == 'save-menu' else None),
              'load_menu_controls': (manifest_doc.get('load_menu_controls')
                                     if context == 'load-menu' else None),
               'goody_hut_reward_scene': (manifest_doc.get('goody_hut_reward_scene')
                                          if context == 'goody-hut-reward' else None),
              'unsupported_callback_controls': (manifest_doc.get('unsupported_callback_controls', [])
                                                if context == 'diplomacy' else []),
              'preparation_inputs': artifact(folder / 'preparation_inputs.json'),
              'retained_runtime_bounds_check': manifest_doc.get('retained_runtime_bounds_check'),
              'snapshot_state_unchanged': True, 'database_unchanged': True}
    (folder / 'driver_record.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n',
                                               encoding='utf-8')
    result['driver_record'] = artifact(folder / 'driver_record.json')
    return result


def _reader(stream, destination: queue.Queue, tag: str) -> None:
    try:
        for line in iter(stream.readline, ''):
            destination.put((tag, line))
    finally:
        destination.put((tag, None))


def _stop_once(process: subprocess.Popen, timeout: float = 5.0) -> tuple[int | None, str]:
    """Request one graceful stop and wait; force-kill only if that wait expires."""
    if process.poll() is not None:
        return process.returncode, 'already-exited'
    try:
        process.terminate()
        process.wait(timeout=timeout)
        return process.returncode, 'terminate-wait'
    except OSError:
        if process.poll() is not None:
            return process.returncode, 'already-exited'
        process.kill()
        process.wait()
        return process.returncode, 'terminate-error-kill-wait'
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
        return process.returncode, 'terminate-timeout-kill-wait'


def _stop_after_negative_ack(process: subprocess.Popen, timeout: float = 5.0) -> tuple[int | None, str]:
    """Let Host consume UI_ERROR and run its own shutdown before forcing a stop."""
    try:
        process.wait(timeout=timeout)
        return process.returncode, 'negative-ack-normal-exit'
    except subprocess.TimeoutExpired:
        return _stop_once(process, timeout=timeout)


def sealed_found_value_policy(support_manifest: Path, tools_dir: Path, resolved_flag: str | None) -> dict:
    """Check the sealed policy/helper closure before any Host process is created."""
    require(support_manifest.stat().st_size <= 2 * 1024 * 1024, 'Frozen support manifest is oversized')
    document = json.loads(support_manifest.read_text(encoding='utf-8'))
    require(type(document) is dict and type(document.get('tools')) is dict, 'Frozen support manifest is malformed')
    expected_tools = {'interactive_ui_driver.py', *SUPPORT}
    if POLICY_FIELD not in document:
        require(set(document['tools']) == expected_tools, 'Legacy support manifest must retain its exact five tools')
        return driver_policy(None, resolved_flag)
    # Presence is distinct from legacy absence; a present null must never
    # acquire the legacy zero fallback.
    policy = validate_policy(document[POLICY_FIELD])
    require(set(document['tools']) == expected_tools | {'found_value_runtime_options.py'},
            'Worker-policy support manifest must contain the exact six tools')
    for name, loaded in (('interactive_ui_driver.py', Path(__file__)),
                         ('found_value_runtime_options.py', Path(worker_options.__file__))):
        expected = tools_dir / name
        row = document['tools'][name]
        _reject_reparse(expected, 'Frozen worker-policy support ' + name)
        require(type(row) is dict and type(row.get('path')) is str and
                Path(row['path']).resolve(strict=True) == expected.resolve(strict=True) and
                sha256(expected) == row.get('sha256') == sha256(loaded) and
                ('bytes' not in row or (type(row['bytes']) is int and row['bytes'] == expected.stat().st_size)),
                'Loaded worker-policy support differs from its frozen manifest: ' + name)
    return driver_policy(policy, resolved_flag)


def drive(command: list[str], *, cwd: Path, runtime: Path, tools_dir: Path, icons_source: Path,
          support_manifest: Path, support_manifest_sha256: str,
          timeout: float, scene_timeout: float, report_path: Path,
          top_panel: bool = False, action_info_panel: bool = False,
          notification_panel: bool = False, found_value_workers: str | None = None) -> dict:
    """Run Host, service scene requests and keep stdout/stderr continuously drained."""
    cwd, runtime = Path(cwd).resolve(strict=True), Path(runtime).resolve(strict=True)
    require(re.fullmatch(r'[0-9a-f]{64}', support_manifest_sha256) is not None and
            sha256(support_manifest) == support_manifest_sha256,
            'Frozen support manifest hash differs from the launcher control metadata')
    worker_policy = sealed_found_value_policy(support_manifest, tools_dir, found_value_workers)
    report_path = Path(report_path).resolve()
    env = dict(os.environ)
    env.pop('ZEROSIS_UI_WINDOW_PROFILE', None)
    env['ZEROSIS_UI_SMALL_ASSETS'] = '1'
    env['ZEROSIS_PLAY_TOP_PANEL'] = '1' if top_panel else '0'
    if action_info_panel:
        env['ZEROSIS_PLAY_ACTION_INFO_PANEL'] = '1'
    else:
        env.pop('ZEROSIS_PLAY_ACTION_INFO_PANEL', None)
    require(not notification_panel or action_info_panel,
            '--notification-panel requires --action-info-panel')
    if notification_panel:
        env['ZEROSIS_PLAY_NOTIFICATION_PANEL'] = '1'
    else:
        env.pop('ZEROSIS_PLAY_NOTIFICATION_PANEL', None)
    env = child_environment(env, worker_policy)
    process = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace',
                               bufsize=1, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    # Host reads this pipe as raw bytes and requires an exact LF terminator.
    process.stdin.reconfigure(newline='\n')
    events: queue.Queue = queue.Queue()
    threads = [threading.Thread(target=_reader, args=(process.stdout, events, 'stdout'), daemon=True),
               threading.Thread(target=_reader, args=(process.stderr, events, 'stderr'), daemon=True)]
    for thread in threads:
        thread.start()
    lines = {'stdout': [], 'stderr': []}
    closed = set()
    scenes = []
    expected_sequence = 1
    started = time.monotonic()
    error = None
    stop_action = None
    negative_ack_sent = False
    while len(closed) < 2 or process.poll() is None:
        if timeout and time.monotonic() - started > timeout:
            error = 'Host process deadline expired'
            break
        try:
            tag, line = events.get(timeout=0.05)
        except queue.Empty:
            if process.poll() is not None and len(closed) == 2:
                break
            continue
        if line is None:
            closed.add(tag)
            continue
        lines[tag].append(line)
        target = sys.stdout if tag == 'stdout' else sys.stderr
        try:
            target.write(line)
            target.flush()
        except (BrokenPipeError, OSError):
            pass
        if tag != 'stdout' or not line.startswith('INTERACTIVE_UI_SCENE_REQUEST='):
            continue
        match = re.match(r'INTERACTIVE_UI_SCENE_REQUEST=([0-9]+)\|', line)
        try:
            require(match is not None and int(match.group(1)) == expected_sequence,
                    'Scene request sequence is not contiguous')
            prepared = prepare_request(line, runtime=runtime, tools_dir=tools_dir,
                                       icons_source=icons_source, support_manifest=support_manifest,
                                       support_manifest_sha256=support_manifest_sha256,
                                       timeout=scene_timeout)
            scenes.append(prepared)
            process.stdin.write('UI_READY|' + str(expected_sequence) + '\n')
            process.stdin.flush()
            expected_sequence += 1
        except Exception as exc:
            error = str(exc)
            sequence = int(match.group(1)) if match else expected_sequence
            try:
                process.stdin.write('UI_ERROR|' + str(sequence) + '\n')
                process.stdin.flush()
                negative_ack_sent = True
            except (BrokenPipeError, OSError, ValueError):
                pass
            break
    if error:
        try:
            process.stdin.close()
        except OSError:
            pass
        if negative_ack_sent:
            returncode, stop_action = _stop_after_negative_ack(process)
        else:
            returncode, stop_action = _stop_once(process)
    else:
        try:
            process.stdin.close()
        except OSError:
            pass
        try:
            returncode = process.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            error = 'Host closed output without exiting after protocol completion'
            returncode, stop_action = _stop_once(process)
    for thread in threads:
        thread.join(timeout=5.0)
    # On an error handshake the Host may print its final exception/unload
    # diagnostics after the driver stops servicing new requests. Preserve those
    # already-read lines after termination without resuming scene preparation.
    while True:
        try:
            tag, line = events.get_nowait()
        except queue.Empty:
            break
        if line is None:
            closed.add(tag)
            continue
        lines[tag].append(line)
        target = sys.stdout if tag == 'stdout' else sys.stderr
        try:
            target.write(line)
            target.flush()
        except (BrokenPipeError, OSError):
            pass
    result = {'status': 'INTERACTIVE_UI_DRIVER_PASS' if error is None and returncode == 0 else 'INTERACTIVE_UI_DRIVER_FAILED',
              POLICY_FIELD: worker_policy, 'found_value_policy_applied_to_child_environment': True,
              'found_value_sdk_consumption_verified': False,
              'pid': process.pid, 'returncode': returncode, 'error': error, 'stop_action': stop_action,
              'negative_ack_sent': negative_ack_sent,
              'sdk_session_profile': {'ZEROSIS_UI_SMALL_ASSETS': '1',
                                      'ZEROSIS_PLAY_TOP_PANEL': env['ZEROSIS_PLAY_TOP_PANEL'],
                                      'ZEROSIS_PLAY_ACTION_INFO_PANEL': env.get('ZEROSIS_PLAY_ACTION_INFO_PANEL'),
                                      'ZEROSIS_PLAY_NOTIFICATION_PANEL': env.get('ZEROSIS_PLAY_NOTIFICATION_PANEL'),
                                      'source': 'interactive_ui_driver.drive explicit override'},
              'top_panel_requested': top_panel,
              'action_info_panel_requested': action_info_panel,
              'notification_panel_requested': notification_panel,
              'command': command, 'cwd': str(cwd), 'runtime': str(runtime), 'timeout_seconds': timeout,
              'scene_timeout_seconds': scene_timeout, 'scene_requests': scenes,
              'stdout': ''.join(lines['stdout']), 'stderr': ''.join(lines['stderr']),
              'scene_request_count': len(scenes)}
    write_json_atomic(report_path, result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', type=Path, required=True)
    parser.add_argument('--cwd', type=Path, required=True)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--tools', type=Path, required=True)
    parser.add_argument('--icons', type=Path, required=True)
    parser.add_argument('--support-manifest', type=Path, required=True)
    parser.add_argument('--support-manifest-sha256', required=True)
    parser.add_argument('--found-value-workers', choices=('0', '1', '2', '4'),
                        help='Exact preparation-resolved count; omission is permitted only for legacy scalar-zero metadata')
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--language', choices=('en_US', 'ko_KR'), required=True)
    parser.add_argument('--mode', choices=('play', 'play-load', 'play-smoke', 'play-load-smoke'), required=True)
    parser.add_argument('--checkpoint', type=Path)
    parser.add_argument('--timeout', type=int, default=0, help='Whole Host deadline; zero means manual play without a total deadline')
    parser.add_argument('--scene-timeout', type=int, default=60)
    parser.add_argument('--top-panel', action='store_true',
                        help='Explicitly enable the candidate persistent TopPanel overlay for this Host process')
    parser.add_argument('--action-info-panel', action='store_true',
                        help='Explicitly enable the original persistent ActionInfoPanel overlay for this Host process')
    parser.add_argument('--notification-panel', action='store_true',
                        help='Explicitly enable the original NotificationPanel overlay; requires --action-info-panel')
    args = parser.parse_args()
    require(args.timeout == 0 or args.timeout >= 30, 'Host timeout must be zero or at least 30 seconds')
    require(10 <= args.scene_timeout <= 300, 'Scene preparation deadline must be 10..300 seconds')
    command = [str(args.host.resolve(strict=True)), '--' + args.mode, args.language]
    if args.checkpoint:
        command.append(str(args.checkpoint.resolve(strict=True)))
    try:
        result = drive(command, cwd=args.cwd, runtime=args.runtime, tools_dir=args.tools,
                       icons_source=args.icons, support_manifest=args.support_manifest,
                       support_manifest_sha256=args.support_manifest_sha256,
                       timeout=args.timeout, scene_timeout=args.scene_timeout,
                       report_path=args.report, top_panel=args.top_panel, action_info_panel=args.action_info_panel,
                       notification_panel=args.notification_panel, found_value_workers=args.found_value_workers)
    except Exception as exc:
        result = {'status': 'INTERACTIVE_UI_DRIVER_FAILED', 'error': str(exc), 'command': command,
                  'runtime': str(args.runtime), 'timeout_seconds': args.timeout,
                  'scene_timeout_seconds': args.scene_timeout, 'scene_requests': []}
        write_json_atomic(args.report, result)
        print('INTERACTIVE_UI_DRIVER_FAILURE: ' + str(exc), file=sys.stderr, flush=True)
    return 0 if result['status'] == 'INTERACTIVE_UI_DRIVER_PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
