"""Independently inspect native original-UI tenet adoption and save/restore.

This consumes one immutable run. It never launches a game or changes a save.
The fresh prerequisite fixture is explicitly not evidence for normal ideology
selection, era eligibility, higher-level tenets, or retail-pixel equivalence.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import re
import sqlite3
import sys
import xml.etree.ElementTree as ET

from collect_baseline import PROJECT, digest
from social_policy_tenet_timeline import verify_social_policy_tenet_timeline
from verify_first_turn_candidate import inspect_save
from verify_world_builder_map_object import check_artifacts
from verify_interactive_trade_route import (
    RUN_ID, VerificationError, artifact_ref, compiled_build_source,
    frozen_native_input_sources, generated_map, load_json, require,
    sdk_state_identity, trade_route_frame_manifest, unique_generated,
    verified_runtime_bundle, verify_frozen_support,
)

EVIDENCE = PROJECT / 'evidence/interactive_game'
RUNTIME = PROJECT / 'Build/InteractiveGameRuntime'
ACTION_PATTERN = re.compile(
    r'^INTERACTIVE_SOCIAL_POLICY_TENET_ACTION=(\d+)\|([^|]+)\|(\d+)\|(\d+)\|(\d+)\|(-?\d+)$', re.M)
FRESH_STAGES = (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 14, 15, 16, 17, 18, 19, 20)
RESTORE_STAGES = (1, 2, 17, 18, 19, 20)
CONFIRM_STAGES = (5, 9, 12, 16)
CHOOSER_STAGES = (4, 5, 6, 8, 9, 11, 12, 15, 16)
POLICY_FIELDS = ('id', 'branch', 'level', 'has', 'blocked')
BRANCH_FIELDS = ('id', 'freePolicy', 'unlocked', 'blocked')


def validate_inventory(value: dict) -> None:
    require(type(value) is dict and value.get('schema') == 'ZEROSIS_SOCIAL_POLICY_SDK_INVENTORY_V1' and
            value.get('source') == 'SDK:Policies/PolicyBranches/JONSCulture',
            'Tenet inventory is not the actual SDK policy inventory')
    for field in ('activePlayer', 'turn', 'elapsed', 'culture', 'nextCost', 'freePolicies', 'freeTenets'):
        require(type(value.get(field)) is int and value[field] >= 0, 'Invalid SDK inventory ' + field)
    require(value['activePlayer'] < 64 and type(value.get('ideology')) is int and value['ideology'] >= -1,
            'Invalid SDK owner or ideology identity')
    require(value.get('policySaving') is False, 'Tenet scenario changed the original policy-saving option')
    for field, flags in (('policies', ('has', 'canAdopt', 'blocked')), ('branches', ('unlocked', 'canUnlock', 'blocked'))):
        rows = value.get(field)
        require(type(rows) is list and 0 < len(rows) <= 2048, 'Missing or unbounded SDK policy rows')
        ids = []
        for row in rows:
            require(type(row) is dict and type(row.get('id')) is int and row['id'] >= 0, 'Invalid SDK policy ID')
            ids.append(row['id'])
            require(all(type(row.get(flag)) is bool for flag in flags), 'Invalid SDK policy flags')
            other = row.get('branch' if field == 'policies' else 'freePolicy')
            require(type(other) is int and other >= -1, 'Invalid SDK policy reference')
            if field == 'policies':
                require(type(row.get('level')) is int and 0 <= row['level'] <= 3, 'Invalid SDK tenet level')
        require(ids == sorted(set(ids)), 'SDK policy IDs must be sorted and unique')
    policy_ids = {r['id'] for r in value['policies']}
    branch_ids = {r['id'] for r in value['branches']}
    require(all(r['branch'] == -1 or r['branch'] in branch_ids for r in value['policies']) and
            all(r['freePolicy'] == -1 or r['freePolicy'] in policy_ids for r in value['branches']) and
            (value['ideology'] == -1 or value['ideology'] in branch_ids), 'SDK inventory has dangling policy references')


def stable_rows(value: dict, field: str, keys: tuple[str, ...]) -> list[dict]:
    return [{key: row[key] for key in keys} for row in value[field]]


def verify_prerequisites(initial: dict, before: dict, freedom_id: int) -> None:
    """The private fixture may unlock Freedom; it must not award a policy."""
    validate_inventory(initial)
    validate_inventory(before)
    require(type(freedom_id) is int and freedom_id >= 0 and initial['ideology'] == -1 and before['ideology'] == freedom_id and
            initial['freeTenets'] == 0 and before['freeTenets'] == 2 and
            initial['activePlayer'] == before['activePlayer'] == 0 and initial['turn'] == before['turn'] == 0 and
            initial['elapsed'] == before['elapsed'] == 0 and initial['culture'] == before['culture'] == 0 and
            initial['freePolicies'] == before['freePolicies'] == 0 and initial['nextCost'] == before['nextCost'] > 0,
            'Fresh tenet prerequisite changed more than its exact first-ideology award')
    require(stable_rows(initial, 'policies', POLICY_FIELDS) == stable_rows(before, 'policies', POLICY_FIELDS) and
            not any(r['has'] for r in before['policies']), 'Fresh prerequisite fixture pre-granted or changed a policy')
    require(stable_rows(initial, 'branches', ('id', 'freePolicy', 'blocked')) ==
            stable_rows(before, 'branches', ('id', 'freePolicy', 'blocked')) and
            not any(r['unlocked'] for r in initial['branches']) and
            [r['id'] for r in before['branches'] if r['unlocked']] == [freedom_id] and
            not next(r for r in before['branches'] if r['id'] == freedom_id)['blocked'],
            'Fresh prerequisite fixture did not unlock only the actual Freedom branch')


def verify_tenet_adoption(before: dict, after: dict, selected: int) -> dict:
    validate_inventory(before)
    validate_inventory(after)
    require(type(selected) is int and selected >= 0, 'Selected tenet must be a nonnegative SDK ID')
    require(all(before[k] == after[k] for k in ('activePlayer', 'turn', 'elapsed', 'ideology')) and
            before['ideology'] >= 0 and before['freePolicies'] == after['freePolicies'] == 0 and before['nextCost'] > 0,
            'Tenet adoption changed its owner, clock, ideology, or free-policy boundary')
    free = before['freeTenets'] > 0
    cost = 0 if free else before['nextCost']
    require(after['freeTenets'] == before['freeTenets'] - int(free) and
            after['culture'] == before['culture'] - cost,
            'Tenet adoption did not consume exactly one free tenet or its actual culture cost')
    old = {r['id']: r for r in before['policies']}
    new = {r['id']: r for r in after['policies']}
    require(old.keys() == new.keys() and selected in old, 'Tenet adoption changed SDK policy inventory IDs')
    selected_row = old[selected]
    require(selected_row['branch'] == before['ideology'] and selected_row['level'] == 1 and
            selected_row['canAdopt'] and not selected_row['has'] and not selected_row['blocked'],
            'Confirmed tenet was not an available level-one policy in the actual ideology')
    changed = []
    for policy_id, previous in old.items():
        current = new[policy_id]
        require(all(previous[k] == current[k] for k in ('branch', 'level', 'blocked')),
                'Tenet adoption changed unrelated policy identity, level, or blocking')
        if previous['has'] != current['has']:
            require(not previous['has'] and current['has'], 'Tenet adoption removed an owned policy')
            changed.append(policy_id)
    require(changed == [selected], 'SDK adoption did not add exactly the confirmed tenet')
    require(stable_rows(before, 'branches', BRANCH_FIELDS) == stable_rows(after, 'branches', BRANCH_FIELDS),
            'Tenet adoption changed an unrelated branch')
    return {'policy_added': selected, 'level': 1, 'ideology': before['ideology'],
            'payment': 'free_tenet' if free else 'culture', 'culture_cost': cost,
            'culture_before': before['culture'], 'culture_after': after['culture'],
            'free_tenets_before': before['freeTenets'], 'free_tenets_after': after['freeTenets']}


def verify_exact_culture_grant(before: dict, after: dict) -> None:
    validate_inventory(before)
    validate_inventory(after)
    require(before['culture'] == 0 and 0 < before['nextCost'] <= 500 and after['culture'] == before['nextCost'] and
            before['freeTenets'] == after['freeTenets'] == before['freePolicies'] == after['freePolicies'] == 0 and
            all(before[k] == after[k] for k in ('activePlayer', 'turn', 'elapsed', 'nextCost', 'ideology', 'policySaving')),
            'Paid fixture did not grant only the exact actual next culture cost')
    require(stable_rows(before, 'policies', POLICY_FIELDS) == stable_rows(after, 'policies', POLICY_FIELDS) and
            stable_rows(before, 'branches', BRANCH_FIELDS) == stable_rows(after, 'branches', BRANCH_FIELDS),
            'Culture-only fixture changed policy ownership or branch identity')


def verify_next_turn(before: dict, after: dict) -> None:
    validate_inventory(before)
    validate_inventory(after)
    require(after['turn'] == before['turn'] + 1 and after['elapsed'] == before['elapsed'] + 1 and
            all(before[k] == after[k] for k in ('activePlayer', 'ideology', 'freeTenets', 'freePolicies')) and
            stable_rows(before, 'policies', POLICY_FIELDS) == stable_rows(after, 'policies', POLICY_FIELDS) and
            stable_rows(before, 'branches', BRANCH_FIELDS) == stable_rows(after, 'branches', BRANCH_FIELDS),
            'Normal next turn lost the adopted SDK tenets, ideology, or ownership')


def nodes(tree: object, control_id: str) -> list[dict]:
    if not isinstance(tree, dict):
        return []
    result = [tree] if tree.get('id') == control_id else []
    for child in tree.get('children', []):
        result.extend(nodes(child, control_id))
    return result


def verify_snapshot(snapshot: dict, inventory: dict, tab: str, policy_info: bool,
                    choosing: bool, confirming: bool, branch_names: dict[int, str], selected: int | None = None) -> None:
    validate_inventory(inventory)
    require(snapshot.get('contextName') == 'SocialPolicyPopup' and snapshot.get('popupKind') == 'SocialPolicy' and
            snapshot.get('active') is True and snapshot.get('hasRetainedPopupUi') is True and
            type(snapshot.get('timerSemaphore')) is int and snapshot['timerSemaphore'] == 1,
            'Tenet snapshot lost its original active modal identity')
    meta = snapshot.get('socialPolicy', {})
    require(type(meta.get('activePlayer')) is int and meta['activePlayer'] == inventory['activePlayer'] and meta.get('currentTab') == tab and
            meta.get('policyInfo') is policy_info and meta.get('ideologyPaneVisible') is (tab == 'Ideologies') and
            type(meta.get('ideology')) is int and meta['ideology'] == inventory['ideology'] and
            type(meta.get('freeTenets')) is int and meta['freeTenets'] == inventory['freeTenets'],
            'Tenet snapshot differs from actual player, tab, ideology, award, or option state')
    require(meta.get('branchSwitchConfirmationPresent') is False and meta.get('ideologyChangePresent') is False,
            'Tenet smoke unexpectedly entered an unverified ideology-change or branch-switch route')
    for field, flags in (('policies', ('has', 'canAdopt', 'blocked')), ('branches', ('unlocked', 'canUnlock', 'blocked'))):
        actual = meta.get(field)
        require(type(actual) is list and all(type(r) is dict and type(r.get('id')) is int for r in actual),
                'Tenet snapshot omits its actual SDK rows')
        by_id = {r['id']: r for r in actual}
        require(len(by_id) == len(actual) and set(by_id) == {r['id'] for r in inventory[field]},
                'Tenet snapshot invented or omitted SDK policy IDs')
        for row in inventory[field]:
            actual_row = by_id[row['id']]
            require(all(actual_row.get(flag) is row[flag] for flag in flags), 'Displayed policy flags differ from actual SDK inventory')
            if field == 'policies':
                require(actual_row.get('branch') == ('' if row['branch'] == -1 else branch_names.get(row['branch'])),
                        'Displayed policy branch differs from original rules-to-SDK mapping')
            else:
                require(actual_row.get('type') == branch_names.get(row['id']),
                        'Displayed branch type differs from original rules-to-SDK mapping')
    for name, visible in (('PolicyConfirm', False), ('TenetConfirm', confirming),
                          ('ChooseTenet', choosing), ('ChangeIdeologyConfirm', False)):
        matches = nodes(snapshot.get('tree'), name)
        require(len(matches) == 1 and matches[0].get('hidden') is (not visible),
                'Original tenet chooser or confirmation visibility differs from the actual input stage')
    checkbox = nodes(snapshot.get('tree'), 'PolicyInfo')
    require(len(checkbox) == 1 and checkbox[0].get('checked') is policy_info, 'Tenet route changed the original PolicyInfo checkbox')
    chosen = meta.get('selectedTenet')
    require(type(chosen) is int and chosen >= -1, 'Selected tenet metadata is missing or not an integer')
    if confirming:
        candidates = [r for r in inventory['policies'] if r['id'] == chosen]
        require(len(candidates) == 1 and candidates[0]['level'] == 1 and candidates[0]['branch'] == inventory['ideology'] and
                candidates[0]['canAdopt'] and not candidates[0]['has'] and not candidates[0]['blocked'],
                'Original confirmation did not select an available actual SDK tenet')
        if selected is not None:
            require(type(selected) is int and chosen == selected, 'Confirmed native payload differs from actual g_SelectedTenet')
    else:
        require(chosen == -1 and selected is None, 'Non-confirmation snapshot leaked or invented a selected tenet')


def verify_visible_target(snapshot: dict, manifest: dict, key: int, control_id: str) -> None:
    """TenetChoice uses a Lua closure, not Void1; selection is checked next frame."""
    require(type(key) is int and key > 0, 'Native tenet target key must be positive')
    targets = [r for r in snapshot.get('inputTargets', []) if type(r) is dict and r.get('key') == key and r.get('event') == 'LeftClick']
    require(len(targets) == 1 and targets[0].get('id') == control_id and targets[0].get('visible') is True and
            targets[0].get('disabled') is False, 'Posted native key does not identify its exact visible original button')
    bounds = targets[0].get('clippedBounds', {})
    require(all(type(bounds.get(k)) in (int, float) and math.isfinite(bounds[k]) for k in ('x', 'y', 'width', 'height')) and
            bounds['width'] > 0 and bounds['height'] > 0, 'Posted tenet target has no positive finite clipped geometry')
    hits = [r for r in manifest.get('hit_regions', []) if type(r) is list and len(r) == 5 and r[0] == key]
    expected = [key, bounds['x'], bounds['y'], bounds['x'] + bounds['width'], bounds['y'] + bounds['height']]
    require(len(hits) == 1 and all(type(a) in (int, float) and math.isfinite(a) and abs(a-b) < 0.01 for a, b in zip(hits[0], expected)),
            'Original tenet callback geometry differs from its native hit record')


def verify_original_sources(lua: Path, xml: Path) -> None:
    source = re.sub(r'\s+', '', lua.read_text(encoding='utf-8-sig'))
    for token in ('player:GetAvailableTenets(iLevel)', 'ChooseTenet(v,tenet.Description)',
                  'g_SelectedTenet=tenet', 'Network.SendUpdatePolicies(g_SelectedTenet,true,true)',
                  'Controls.TenetConfirmYes:RegisterCallback(Mouse.eLClick,OnTenetConfirmYes)',
                  'Controls.TenetConfirmNo:RegisterCallback(Mouse.eLClick,OnTenetConfirmNo)',
                  'Controls.TenetCancelButton:RegisterCallback(Mouse.eLClick,OnCancel)'):
        require(token in source, 'Original SocialPolicy Lua does not provide the recorded tenet callback contract')
    root = ET.parse(xml).getroot()
    ids = {node.get('ID') for node in root.iter() if node.get('ID')}
    require({'IdeologyButton11', 'IdeologyButton12', 'IdeologyButton13', 'TenetButton',
             'ChooseTenet', 'TenetConfirm', 'TenetConfirmYes', 'TenetConfirmNo', 'TenetCancelButton'} <= ids and
            any(node.tag == 'Instance' and node.get('Name') == 'TenetChoice' for node in root.iter()),
            'Original SocialPolicy XML lacks the recorded tenet controls or instance template')


def verify_rule_rows(inventory: dict, branch_rows: list[tuple], policy_rows: list[tuple]) -> dict[int, str]:
    names = {row[0]: row[1] for row in branch_rows}
    branch_ids = {row[1]: row[0] for row in branch_rows}
    require(len(names) == len(branch_rows) and set(names) == {r['id'] for r in inventory['branches']} and
            len(policy_rows) == len({r[0] for r in policy_rows}), 'Original rules database has mismatched SDK policy IDs')
    expected = {policy_id: (-1 if branch is None else branch_ids.get(branch), level or 0)
                for policy_id, branch, level in policy_rows}
    require(set(expected) == {r['id'] for r in inventory['policies']} and
            all(expected[r['id']] == (r['branch'], r['level']) for r in inventory['policies']),
            'SDK tenet level or branch differs from the actual session rules database')
    ideology = inventory['ideology']
    if ideology >= 0:
        require(names.get(ideology) == 'POLICY_BRANCH_FREEDOM' and
                any(r[0] == ideology and r[2] == 1 for r in branch_rows),
                'Tenet prerequisite does not identify the actual PurchaseByLevel Freedom branch')
    return names


def verify_options(request: dict, generated: dict[str, list[Path]]) -> tuple[bool, dict]:
    opts = request.get('policy_info_options', {})
    require(type(opts.get('policy_info')) is int and opts['policy_info'] in (0, 1), 'PolicyInfo initial option is missing')
    for field in ('source', 'original_user_settings'):
        row = opts.get(field, {})
        path = Path(row.get('original_path', '')).resolve(strict=True)
        require(path.is_file() and digest(path) == row.get('sha256') and path.stat().st_size == row.get('bytes'),
                'Original option source changed during the tenet run')
    ini = Path(opts['original_user_settings']['original_path']).resolve(strict=True)
    values = re.findall(r'^\s*PolicyInfo\s*=\s*([01])\s*$', ini.read_text(encoding='utf-8-sig'), re.M)
    require(ini.name == 'UserSettings.ini' and len(values) == 1 and opts.get('original_policy_info') == int(values[0]),
            'Tenet INI option provenance differs from the original user setting')
    require(opts.get('origin') in ('ORIGINAL_USER_SETTINGS_READ_ONLY', 'RESUMED_SESSION_UI_OPTIONS'), 'Unknown PolicyInfo option origin')
    if opts['origin'] == 'ORIGINAL_USER_SETTINGS_READ_ONLY':
        require(Path(opts['source']['original_path']).resolve(strict=True) == ini and opts['policy_info'] == int(values[0]),
                'Fresh tenet option did not come from the original read-only INI')
    if 'ui-options.json' in generated:
        stored = load_json(unique_generated(generated, 'ui-options.json'), 'unchanged isolated UI options')
        require(stored == {'schema': 'ZEROSIS_UI_OPTIONS_V1', 'policyInfo': bool(opts['policy_info'])},
                'Tenet scenario unexpectedly changed its isolated PolicyInfo option')
    return bool(opts['policy_info']), opts


def verify_run(run_id: str, chain: frozenset[str] = frozenset()) -> dict:
    require(type(run_id) is str and RUN_ID.fullmatch(run_id) is not None and run_id not in chain,
            'Invalid or cyclic tenet run identity')
    evidence, runtime = EVIDENCE / run_id, (RUNTIME / run_id).resolve(strict=True)
    request_path, result_path = evidence / 'request.json', evidence / 'result.json'
    request, result = load_json(request_path, 'tenet request'), load_json(result_path, 'tenet result')
    resume = request.get('resume_from')
    require(resume is None or type(resume) is dict, 'Tenet resume lineage must be an object or null')
    check_artifacts(request)
    check_artifacts(result)
    require(request.get('run_id') == result.get('run_id') == run_id and
            all(request.get(k) is True for k in ('social_policy_tenets', 'social_policy_smoke', 'smoke', 'decisions', 'top_panel')) and
            request.get('trade_route_smoke') is False and request.get('stage_or_mods_changed') is False and
            request.get('input_profile') == 'POSTED_HWND_ORIGINAL_SOCIAL_POLICY_TENET_SMOKE',
            'Run is not the isolated original tenet input profile')
    require(result.get('returncode') == 0 and result.get('timed_out') is False and result.get('failures') == [] and
            result.get('runtime_inputs_unchanged') is True and result.get('status', '').endswith('PASS') and
            result.get('social_policy_tenets_requested') is True and result.get('social_policy_tenets_sequence_verified') is True and
            result.get('social_policy_dispatch_verified') is True, 'Tenet run did not complete cleanly')
    artifact_ref(result.get('request'), exact=request_path)
    output = artifact_ref(result.get('stdout'), exact=evidence / 'stdout.log').read_text(encoding='utf8').replace('\r\n', '\n').replace('\r', '\n')
    stderr = artifact_ref(result.get('stderr'), exact=evidence / 'stderr.log').read_text(encoding='utf8')
    require(not re.search(r'HOST_FAILURE|HOST_NATIVE_EXCEPTION|HOST_CLEANUP_PENDING|INTERACTIVE_INPUT_REJECTED', output + stderr),
            'Tenet Host reported a native or input failure')
    timeline_ok, failure = verify_social_policy_tenet_timeline(output)
    require(timeline_ok, str(failure))
    require(Path(request.get('cwd', '')).resolve(strict=True) == runtime, 'Tenet runtime escaped its immutable directory')
    host, bundle, _ = verified_runtime_bundle(request, runtime, 'Tenet')
    build_path = artifact_ref(request.get('provenance', {}).get('host_build'))
    build = load_json(build_path, 'sealed tenet Host build')
    require(build.get('status') == 'UI_WINDOW_HOST_CANDIDATE_BUILT' and build.get('source_inputs_unchanged') is True and
            digest(host) == build.get('executable', {}).get('sha256'), 'Tenet Host differs from its sealed build')
    sources = {Path(r['path']).name: r for r in build.get('sources', [])}
    source_proof = frozen_native_input_sources(build['build_id'], sources)
    for name in ('SocialPolicySmokeFixture.h', 'InteractiveGameLoop.h', 'InteractiveGameSession.h', 'InteractiveUiSession.h', 'UiScene.lua'):
        require(name in sources, 'Host lacks frozen tenet integration source ' + name)
        frozen = compiled_build_source(build['build_id'], sources[name], 'Source\\Host\\' + name,
                                       'project' if name.endswith('.lua') else 'include_roots/project')
        source_proof[name] = {'path': str(frozen), 'sha256': digest(frozen)}
    fixture_source = Path(source_proof['SocialPolicySmokeFixture.h']['path']).read_text(encoding='utf8')
    require(all(marker in fixture_source for marker in ('PrepareTenets', 'FundPaidTenet', 'RequireTenetAdoption',
                'p:SetPolicyBranchUnlocked(b.ID,true,false)', 'p:GetNumFreeTenets()', 'p:GetLateGamePolicyTree()', 'row.Level or 0')),
            'Frozen Host source does not contain the observed SDK tenet fixture/inventory contract')
    generated, generated_paths = generated_map(result, runtime)
    support_proof = verify_frozen_support(request, evidence, runtime)
    attempt = load_json(artifact_ref(result.get('attempt'), exact=evidence / 'attempt.json'), 'Host attempt')
    require(attempt.get('status') == 'FINISHED' and attempt.get('returncode') == 0 and attempt.get('timed_out') is False and
            attempt.get('pid') == result.get('driver_pid'), 'Tenet driver did not terminate under its recorded identity')
    stages = ('initial', 'before', 'adopted', 'returned', 'next-turn') + (() if resume else ('cancelled', 'free-1', 'free-2', 'funded'))
    inventories = {stage: load_json(unique_generated(generated, f'tenet-{stage}-inventory.json'), stage + ' tenet inventory') for stage in stages}
    for value in inventories.values():
        validate_inventory(value)
    matches = list(ACTION_PATTERN.finditer(output))
    require(len(matches) == sum(line.startswith('INTERACTIVE_SOCIAL_POLICY_TENET_ACTION=') for line in output.splitlines()),
            'Malformed or duplicate native tenet action record')
    actions = {int(m[1]): {'id': m[2], 'key': int(m[3]), 'generation': int(m[4]), 'revision': int(m[5]), 'payload': int(m[6])} for m in matches}
    require(tuple(actions) == (RESTORE_STAGES if resume else FRESH_STAGES), 'Tenet action scope differs from request resume state')
    require(all(a['payload'] == -1 for stage, a in actions.items() if stage not in (9, 12, 16)),
            'Non-confirmation tenet action claims a mutation payload')
    policy_info, opts = verify_options(request, generated)
    frames = re.findall(r'^INTERACTIVE_UI_FRAME=(\d+)\|(\d+)\|(\d+)\|social-policy\|(\d+)\|(\d+)\|([^|\r\n]+)\|([^|\r\n]+)$', output, re.M)
    require(frames, 'No native original policy frames were published')
    by_generation, originals, rules_cache = {}, {}, {}
    for revision, generation, turn, hwnd, device, snapshot_name, folder in frames:
        snapshot_path = Path(snapshot_name).resolve(strict=True)
        require(snapshot_path in generated_paths, 'Tenet frame snapshot is not a pinned generated artifact')
        manifest_path = trade_route_frame_manifest(snapshot_path, folder, generated_paths, runtime / 'sessions')
        manifest, snapshot = load_json(manifest_path, 'tenet scene manifest'), load_json(snapshot_path, 'actual SDK tenet scene')
        layout_sources = {}
        for field, filename in (('originalLayoutLua', 'SocialPolicyPopup.lua'), ('originalLayoutXml', 'SocialPolicyPopup.xml')):
            original = artifact_ref(snapshot.get('socialPolicy', {}).get(field), label='original tenet layout')
            require(original.name == filename and original.as_posix().endswith('/Assets/DLC/Expansion2/UI/InGame/Popups/' + filename),
                    'Tenet snapshot does not identify installed original SocialPolicyPopup source')
            layout_sources[filename] = original
            original_hash = digest(original)
            require(filename not in originals or originals[filename]['sha256'] == original_hash, 'Tenet source changed between native frames')
            originals[filename] = {'path': str(original), 'sha256': original_hash}
        if len(by_generation) == 0:
            verify_original_sources(layout_sources['SocialPolicyPopup.lua'], layout_sources['SocialPolicyPopup.xml'])
        preparation_path = (Path(folder) / 'preparation_inputs.json').resolve(strict=True)
        require(preparation_path in generated_paths, 'Tenet frame lacks its frozen preparation inputs')
        preparation = load_json(preparation_path, 'tenet preparation inputs')
        rules_db = artifact_ref(preparation.get('rules_database'))
        require(rules_db in generated_paths and rules_db.parent == snapshot_path.parent, 'Tenet rules database escaped its actual SDK session')
        if rules_db not in rules_cache:
            with sqlite3.connect(rules_db.as_uri() + '?mode=ro', uri=True) as connection:
                rules_cache[rules_db] = (list(connection.execute('SELECT ID, Type, PurchaseByLevel FROM PolicyBranchTypes')),
                                        list(connection.execute('SELECT ID, PolicyBranchType, Level FROM Policies')))
        branch_names = verify_rule_rows(inventories['before'], *rules_cache[rules_db])
        artifact_ref(manifest.get('snapshot'), exact=snapshot_path)
        packet = artifact_ref(manifest.get('packet'), exact=Path(folder) / 'scene.packet')
        require(packet in generated_paths and manifest.get('context') == 'social-policy' and manifest.get('retail_pixels_verified') is False,
                'Tenet renderer packet has wrong context or evidence scope')
        generation = int(generation)
        require(generation not in by_generation and int(hwnd) > 0 and int(device) > 0, 'Tenet frame duplicates generation or lacks its native HWND/device')
        by_generation[generation] = {'revision': int(revision), 'turn': int(turn), 'hwnd': int(hwnd), 'device': int(device),
                                     'snapshot': snapshot, 'manifest': manifest, 'branch_names': branch_names}
    identities = {(f['hwnd'], f['device']) for f in by_generation.values()}
    require(len(identities) == 1, 'Tenet route changed its native HWND or device')
    freedom_ids = {key for f in by_generation.values() for key, name in f['branch_names'].items() if name == 'POLICY_BRANCH_FREEDOM'}
    require(len(freedom_ids) == 1, 'Tenet frames disagree on original Freedom branch identity')
    adoptions = []
    if not resume:
        verify_prerequisites(inventories['initial'], inventories['before'], next(iter(freedom_ids)))
        require(inventories['before'] == inventories['cancelled'] and
                unique_generated(generated, 'tenet-before-state.txt').read_bytes() == unique_generated(generated, 'tenet-cancelled-state.txt').read_bytes(),
                'Original tenet cancel callbacks changed full SDK state or policy inventory')
        adoptions = [verify_tenet_adoption(inventories['before'], inventories['free-1'], actions[9]['payload']),
                     verify_tenet_adoption(inventories['free-1'], inventories['free-2'], actions[12]['payload']),
                     verify_tenet_adoption(inventories['funded'], inventories['adopted'], actions[16]['payload'])]
        verify_exact_culture_grant(inventories['free-2'], inventories['funded'])
        require([r['payment'] for r in adoptions] == ['free_tenet', 'free_tenet', 'culture'] and
                len({r['policy_added'] for r in adoptions}) == 3 and inventories['adopted']['culture'] == 0,
                'Tenet profile does not contain exactly two distinct free and one paid level-one adoptions')
    else:
        require(inventories['initial'] == inventories['before'] == inventories['adopted'] and
                unique_generated(generated, 'tenet-before-state.txt').read_bytes() == unique_generated(generated, 'tenet-adopted-state.txt').read_bytes(),
                'Restored tenet viewer changed saved SDK state or tenet inventory')
    require(inventories['returned'] == inventories['adopted'] and
            unique_generated(generated, 'tenet-returned-state.txt').read_bytes() == unique_generated(generated, 'tenet-adopted-state.txt').read_bytes(),
            'Close, reopen, tab, or Escape changed adopted SDK gameplay state')
    for stage, action in actions.items():
        if stage in (1, 18):
            continue
        require(action['generation'] in by_generation, 'Tenet action did not use a published native frame')
        frame = by_generation[action['generation']]
        require(frame['revision'] == action['revision'] and frame['turn'] == inventories['before']['turn'],
                'Tenet action revision or turn differs from its published frame')
        inventory_stage = 'before' if stage <= 9 else 'free-1' if stage <= 12 else 'funded' if stage <= 16 else 'adopted'
        if resume:
            inventory_stage = 'before'
        verify_snapshot(frame['snapshot'], inventories[inventory_stage], 'SocialPolicies' if stage in (2, 19) else 'Ideologies',
                        policy_info, stage in CHOOSER_STAGES, stage in CONFIRM_STAGES, frame['branch_names'],
                        action['payload'] if stage in (9, 12, 16) else None)
        if stage != 20:
            verify_visible_target(frame['snapshot'], frame['manifest'], action['key'], action['id'])
    top_inputs = [tuple(map(int, row)) for row in re.findall(r'^INTERACTIVE_TOP_PANEL_INPUT=(\d+)\|(\d+)\|(\d+)\|(\d+)\|([01])$', output, re.M)]
    top_frames = re.findall(r'^INTERACTIVE_TOP_PANEL_FRAME=(\d+)\|(\d+)\|(-?\d+)\|(-?\d+)\|(\d+)\|(\d+)\|([^|\r\n]+)\|([^|\r\n]+)$', output, re.M)
    for stage in (1, 18):
        action = actions[stage]
        matching = [r for r in top_inputs if r[0] == action['generation'] and r[1] == 1 and r[2] == action['key'] and r[4] == 1]
        require(len(matching) == 1 and matching[0][2] - matching[0][3] == 1 << 51,
                'CultureString posted key did not reach its exact original TopPanel callback namespace')
        top = [row for row in top_frames if int(row[1]) == action['generation']]
        require(len(top) == 1 and int(top[0][0]) == action['revision'], 'CultureString action lacks its exact retained TopPanel frame')
        top_snapshot = Path(top[0][6]).resolve(strict=True)
        require(top_snapshot in generated_paths, 'CultureString source snapshot escaped generated artifacts')
        top_manifest_path = trade_route_frame_manifest(top_snapshot, top[0][7], generated_paths, runtime / 'sessions')
        top_manifest = load_json(top_manifest_path, 'original TopPanel native entry packet')
        artifact_ref(top_manifest.get('snapshot'), exact=top_snapshot)
        verify_visible_target(load_json(top_snapshot, 'original TopPanel entry scene'), top_manifest, matching[0][3], 'CultureString')
        require((int(top[0][4]), int(top[0][5])) in identities, 'CultureString opened its tenet popup in a different HWND/device')
    verify_next_turn(inventories['adopted'], inventories['next-turn'])
    final_state = unique_generated(generated, 'play-final-state.txt')
    identity = sdk_state_identity(final_state.read_bytes(), 'Tenet final save')
    saves = re.findall(r'^INTERACTIVE_NATIVE_SAVE=(\d+)\|(.+)$', output, re.M)
    require(len(saves) >= 2 and identity[:3] == tuple(inventories['next-turn'][k] for k in ('turn', 'elapsed', 'activePlayer')),
            'Tenet sequence lacks repeated native saves at its observed next turn')
    require(len({Path(name).resolve(strict=True) for _, name in saves}) == len(saves),
            'Repeated tenet save events refer to the same native archive')
    archives = []
    for turn, name in saves:
        path = Path(name).resolve(strict=True)
        require(path in generated_paths and int(turn) == identity[0], 'Tenet native save is not a pinned final-turn artifact')
        archives.append(inspect_save(path, bundle, path.parent / 'Civ5SavedGameDatabase.db', expected=(1, 0, *identity[:3], 64, 64, 133)))
    fixture = re.findall(r'^INTERACTIVE_SOCIAL_POLICY_TENET_FIXTURE=(FRESH|RESTORED)\|(\d+)\|(\d+)\|(\d+)\|(-?\d+)\|(\d+)$', output, re.M)
    expected_fixture = ('RESTORED' if resume else 'FRESH', *(str(inventories['before'][k]) for k in ('activePlayer', 'turn', 'elapsed', 'ideology', 'freeTenets')))
    require(fixture == [expected_fixture], 'Observed tenet fixture marker differs from independent SDK inventory')
    grants = [tuple(map(int, r)) for r in re.findall(r'^INTERACTIVE_SOCIAL_POLICY_TENET_CULTURE=(\d+)\|(\d+)\|(\d+)\|(\d+)$', output, re.M)]
    restore = None
    if resume:
        source_id = resume.get('run_id')
        require(type(source_id) is str and source_id != run_id and source_id not in chain, 'Invalid tenet checkpoint lineage')
        prior_proof = verify_run(source_id, chain | {run_id})
        source_request = load_json(EVIDENCE / source_id / 'request.json', 'tenet checkpoint source request')
        source_result = load_json(EVIDENCE / source_id / 'result.json', 'tenet checkpoint source result')
        source_runtime = (RUNTIME / source_id).resolve(strict=True)
        source_generated, source_paths = generated_map(source_result, source_runtime)
        prior = load_json(unique_generated(source_generated, 'tenet-next-turn-inventory.json'), 'source saved tenet inventory')
        require(not grants and inventories['initial'] == prior and policy_info is prior_proof['final_policy_info'],
                'Restore re-granted culture or lost its exact saved SDK tenet inventory or UI option')
        if opts['origin'] == 'RESUMED_SESSION_UI_OPTIONS':
            require(opts.get('run_id') == source_id, 'Restored tenet UI options escaped their checkpoint source')
        require(result.get('fresh_process_restore_verified') is True and result.get('checkpoint_input_unchanged') is True and
                result.get('semantic_restore_equal') is True, 'Tenet restore lacks verified independent process/SDK state evidence')
        for field in ('pid', 'driver_pid'):
            require(type(result.get(field)) is int and type(source_result.get(field)) is int and
                    result[field] > 0 and source_result[field] > 0 and result[field] != source_result[field],
                    'Tenet restore did not use distinct native Host/driver processes')
        previous_result = artifact_ref(resume.get('run_result'), exact=evidence / 'resume-source-result.json')
        require(previous_result.read_bytes() == (EVIDENCE / source_id / 'result.json').read_bytes(), 'Frozen source tenet result changed')
        source_host, source_bundle, _ = verified_runtime_bundle(source_request, source_runtime, 'Tenet restore source')
        require(digest(source_host) == digest(host) and digest(source_bundle) == digest(bundle), 'Tenet restore migrated the sealed native bundle')
        checkpoint = artifact_ref(resume.get('checkpoint_input'), exact=runtime / 'checkpoint-input.zssave')
        source_save = artifact_ref(resume.get('checkpoint_source'))
        require(source_save in source_paths and checkpoint.read_bytes() == source_save.read_bytes(), 'Tenet checkpoint changed or escaped its saved source')
        initial_state = unique_generated(generated, 'play-initial-state.txt')
        source_state = unique_generated(source_generated, 'play-final-state.txt')
        require(initial_state.read_bytes() == source_state.read_bytes(), 'Restored SDK startup differs from source final state')
        restore_identity = sdk_state_identity(initial_state.read_bytes(), 'Tenet restored startup')
        expected = (1, 0, *restore_identity[:3], 64, 64, 133)
        source_archive = inspect_save(source_save, source_bundle, source_save.parent / 'Civ5SavedGameDatabase.db', expected=expected)
        restored_archive = inspect_save(unique_generated(generated, 'play-restored-checkpoint.zssave'), bundle,
                                        initial_state.parent / 'Civ5SavedGameDatabase.db', expected=expected)
        previous_sections = {(r['kind'], r['index']): r['sha256'] for r in source_archive['sections']}
        restored_sections = {(r['kind'], r['index']): r['sha256'] for r in restored_archive['sections']}
        require(previous_sections.keys() == restored_sections.keys() and len(previous_sections) == 133,
                'Tenet restore native section inventory differs')
        changed = sorted(key for key in previous_sections if previous_sections[key] != restored_sections[key])
        require(all(key == (3, 0) for key in changed), 'Tenet restore changed a native player/team/other section')
        require(re.findall(r'^INTERACTIVE_RESTORE_SECTIONS_EQUAL=(\d+)\|(\d+)$', output, re.M) == [(str(133-len(changed)), '133')] and
                [tuple(map(int, r)) for r in re.findall(r'^INTERACTIVE_RESTORE_SECTION_CHANGED=(\d+)\|(\d+)$', output, re.M)] == changed and
                re.findall(r'^INTERACTIVE_RESTORE_IDLE_STATE_UNCHANGED=(true)$', output, re.M) == ['true'],
                'Native restore section/idle logs differ from independent save comparison')
        restore = {'source_run_id': source_id, 'player_sections_byte_equal': True, 'changed_native_sections': changed,
                   'sdk_tenet_inventory_exact': True, 'fixture_mutation_applied': False,
                   'game_reload_rng_equivalence_verified': False}
    else:
        require(grants == [(0, inventories['funded']['culture'], inventories['funded']['culture'], inventories['before']['turn'])],
                'Fresh tenet run lacks exactly one observed current-cost culture grant')
    return {'status': 'PASS_INTERACTIVE_POLICY_TENETS_NATIVE_SDK_SMOKE', 'run_id': run_id,
            'result': {'path': str(result_path), 'sha256': digest(result_path)}, 'source_proof': source_proof,
            'original_sources': originals, 'frozen_ui_support': support_proof, 'adoptions': adoptions,
            'posted_actions': len(actions), 'native_policy_inputs': len(actions)-2, 'native_window_count': len(identities),
            'original_cancel_sdk_state_unchanged': None if resume else True, 'final_policy_info': policy_info,
            'original_option_source_unchanged': True, 'normal_turn_tenet_state_preserved': True,
            'culture_fixture_grants': grants, 'native_save_count': len(archives), 'restore': restore,
            'fresh_fixture_seeds_ideology_prerequisite': not bool(resume),
            'normal_ideology_selection_verified': False, 'retail_pixels_verified': False, 'full_policy_gameplay_verified': False,
            'unverified_policy_routes': ['normal ideology eligibility and selector', 'level-two and level-three tenets',
                                         'blocked branch switching', 'ideology change'], 'stage_or_mods_changed': False}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        result = verify_run(args.run_id)
    except (OSError, ValueError, KeyError, RuntimeError, TypeError, ET.ParseError) as exc:
        result = {'status': 'FAIL_INTERACTIVE_POLICY_TENETS_NATIVE_SDK_SMOKE', 'run_id': args.run_id, 'error': str(exc)}
    target = args.output or EVIDENCE / args.run_id / 'policy_tenets_validation.json'
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps({'status': result['status'], 'output': str(target), 'error': result.get('error')}, ensure_ascii=False))
    return 0 if result['status'].startswith('PASS_') else 1


if __name__ == '__main__':
    sys.exit(main())
