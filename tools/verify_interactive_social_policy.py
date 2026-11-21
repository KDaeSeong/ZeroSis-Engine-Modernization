"""Inspect original SocialPolicy HWND input, paid SDK adoptions and native restore.

Consumes one immutable private run. No game launch, save rewrite, or retail
pixel/full-policy-gameplay claim is performed here.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
import sqlite3
import sys

from collect_baseline import PROJECT, digest
from run_interactive_game import verify_social_policy_dispatch_timeline
from verify_first_turn_candidate import inspect_save
from verify_world_builder_map_object import check_artifacts
from verify_interactive_trade_route import (
    RUN_ID, VerificationError, artifact_ref, compiled_build_source, generated_map,
    load_json, require, sdk_state_identity, trade_route_frame_manifest, unique_generated,
    verified_runtime_bundle, verify_frozen_support,
)

EVIDENCE = PROJECT / 'evidence/interactive_game'
RUNTIME = PROJECT / 'Build/InteractiveGameRuntime'


def validate_inventory(value: dict) -> None:
    require(value.get('schema') == 'ZEROSIS_SOCIAL_POLICY_SDK_INVENTORY_V1' and
            value.get('source') == 'SDK:Policies/PolicyBranches/JONSCulture', 'Policy inventory is not SDK-derived')
    for field in ('activePlayer', 'turn', 'elapsed', 'culture', 'nextCost', 'freePolicies'):
        require(type(value.get(field)) is int and value[field] >= 0, f'Invalid SDK inventory {field}')
    require(value['activePlayer'] < 64, 'Invalid active player')
    require(value.get('policySaving') is False, 'Policy scenario changed the original mandatory policy-saving boundary')
    for field, flags in (('policies', ('has', 'canAdopt', 'blocked')), ('branches', ('unlocked', 'canUnlock', 'blocked'))):
        rows = value.get(field)
        require(type(rows) is list and 0 < len(rows) <= 2048, 'Missing or unbounded SDK policy rows')
        ids = []
        for row in rows:
            require(type(row) is dict and type(row.get('id')) is int and row['id'] >= 0, 'Invalid SDK policy ID')
            ids.append(row['id'])
            require(all(type(row.get(flag)) is bool for flag in flags), 'Invalid SDK policy flags')
            reference = row.get('branch' if field == 'policies' else 'freePolicy')
            require(type(reference) is int and reference >= -1, 'Invalid SDK policy reference')
        require(ids == sorted(set(ids)), 'SDK policy IDs must be sorted and unique')


def verify_adoption(before: dict, after: dict, selected: int, is_policy: bool) -> dict:
    validate_inventory(before)
    validate_inventory(after)
    require(type(selected) is int and selected >= 0, 'Selected policy ID must be a nonnegative integer')
    require(all(before[k] == after[k] for k in ('activePlayer', 'turn', 'elapsed')) and
            before['freePolicies'] == after['freePolicies'] == 0 and
            before['nextCost'] > 0 and after['culture'] == before['culture'] - before['nextCost'], 'Paid policy did not charge exactly the SDK cost')
    old_policies = {r['id']: r for r in before['policies']}
    new_policies = {r['id']: r for r in after['policies']}
    old_branches = {r['id']: r for r in before['branches']}
    new_branches = {r['id']: r for r in after['branches']}
    require(old_policies.keys() == new_policies.keys() and old_branches.keys() == new_branches.keys(),
            'Adoption changed the SDK policy or branch inventory IDs')
    if is_policy:
        require(selected in old_policies and old_policies[selected]['canAdopt'] and
                not old_policies[selected]['has'] and not old_policies[selected]['blocked'],
                'Selected policy was not actually available before confirmation')
        expected_policy = selected
    else:
        require(selected in old_branches and old_branches[selected]['canUnlock'] and
                not old_branches[selected]['unlocked'] and not old_branches[selected]['blocked'],
                'Selected branch was not actually available before confirmation')
        expected_policy = old_branches[selected]['freePolicy']
    changed_policies = []
    for key, row in old_policies.items():
        current = new_policies[key]
        require(row['branch'] == current['branch'] and row['blocked'] == current['blocked'],
                'Adoption changed unrelated SDK policy identity or blocking')
        if row['has'] != current['has']:
            require(not row['has'] and current['has'], 'Adoption removed a previously owned SDK policy')
            changed_policies.append(key)
    changed_branches = []
    for key, row in old_branches.items():
        current = new_branches[key]
        require(row['freePolicy'] == current['freePolicy'] and row['blocked'] == current['blocked'],
                'Adoption changed unrelated SDK branch identity or blocking')
        if row['unlocked'] != current['unlocked']:
            require(not row['unlocked'] and current['unlocked'], 'Adoption relocked an existing SDK branch')
            changed_branches.append(key)
    require(changed_policies == [expected_policy] and changed_branches == ([] if is_policy else [selected]),
            'SDK adoption differs from the selected policy or exact branch opener')
    return {'selected': selected, 'is_policy': is_policy, 'policy_added': expected_policy,
            'culture_before': before['culture'], 'culture_after': after['culture'], 'cost': before['nextCost']}


def verify_exact_culture_grant(before: dict, after: dict) -> None:
    validate_inventory(before)
    validate_inventory(after)
    require(before['culture'] == 0 and after['culture'] == before['nextCost'] and 0 < after['culture'] <= 500 and
            all(before[k] == after[k] for k in ('activePlayer', 'turn', 'elapsed', 'nextCost', 'freePolicies', 'policySaving')),
            'Second fixture did not grant exactly the actual next policy cost')
    for field, preserved in (('policies', ('id', 'branch', 'has', 'blocked')), ('branches', ('id', 'freePolicy', 'unlocked', 'blocked'))):
        require([{k: r[k] for k in preserved} for r in before[field]] == [{k: r[k] for k in preserved} for r in after[field]],
                'Culture-only fixture changed policy ownership, branch identity, or blocking')


def nodes(tree: object, control_id: str) -> list[dict]:
    if not isinstance(tree, dict):
        return []
    result = [tree] if tree.get('id') == control_id else []
    for child in tree.get('children', []):
        result.extend(nodes(child, control_id))
    return result


def verify_snapshot(snapshot: dict, inventory: dict, tab: str, policy_info: bool, confirming: bool,
                    branch_names: dict[int, str] | None = None) -> None:
    require(snapshot.get('contextName') == 'SocialPolicyPopup' and snapshot.get('popupKind') == 'SocialPolicy' and
            snapshot.get('active') is True and snapshot.get('hasRetainedPopupUi') is True and snapshot.get('timerSemaphore') == 1,
            'SocialPolicy snapshot lost its original active modal identity')
    meta = snapshot.get('socialPolicy', {})
    require(meta.get('activePlayer') == inventory['activePlayer'] and meta.get('currentTab') == tab and
            meta.get('policyInfo') is policy_info, 'SocialPolicy snapshot has the wrong player, tab, or persisted option')
    require(meta.get('branchSwitchConfirmationPresent') is False and meta.get('ideologyChangePresent') is False,
            'This bounded scenario unexpectedly entered an unimplemented branch-switch or ideology-change popup')
    for field, flags in (('policies', ('has', 'canAdopt', 'blocked')), ('branches', ('unlocked', 'canUnlock', 'blocked'))):
        actual = meta.get(field)
        require(type(actual) is list and all(isinstance(r, dict) and type(r.get('id')) is int for r in actual),
                'SocialPolicy snapshot omits its actual SDK rows')
        by_id = {r['id']: r for r in actual}
        require(len(by_id) == len(actual) and set(by_id) == {r['id'] for r in inventory[field]},
                'SocialPolicy snapshot invented or omitted SDK policy IDs')
        for row in inventory[field]:
            require(all(by_id[row['id']].get(flag) is row[flag] for flag in flags),
                    'SocialPolicy displayed flags differ from actual SDK inventory')
            if field == 'policies' and branch_names is not None:
                require(by_id[row['id']].get('branch') == ('' if row['branch'] == -1 else branch_names.get(row['branch'])),
                        'SocialPolicy branch type differs from original rules-to-SDK ID mapping')
    for name, visible in (('PolicyConfirm', confirming), ('TenetConfirm', False), ('ChangeIdeologyConfirm', False)):
        matches = nodes(snapshot.get('tree'), name)
        require(len(matches) == 1 and matches[0].get('hidden') is (not visible),
                'Original policy confirmation visibility differs from its actual input stage')
    checkbox = nodes(snapshot.get('tree'), 'PolicyInfo')
    require(len(checkbox) == 1 and checkbox[0].get('checked') is policy_info,
            'Original PolicyInfo checkbox differs from captured option state')


def verify_visible_target(snapshot: dict, manifest: dict, key: int, control_id: str, payload: int) -> None:
    require(type(key) is int and key > 0, 'Native policy target key must be positive')
    targets = [r for r in snapshot.get('inputTargets', []) if isinstance(r, dict) and r.get('key') == key and r.get('event') == 'LeftClick']
    require(len(targets) == 1 and targets[0].get('id') == control_id and targets[0].get('visible') is True and
            targets[0].get('disabled') is False, 'Posted native key does not identify the exact visible original button')
    if payload >= 0:
        require(type(targets[0].get('void1')) is int and targets[0]['void1'] == payload,
                'Posted policy or branch button has a different native callback payload')
    bounds = targets[0].get('clippedBounds', {})
    require(all(type(bounds.get(k)) in (int, float) for k in ('x', 'y', 'width', 'height')) and
            bounds['width'] > 0 and bounds['height'] > 0, 'Posted policy target has no positive clipped geometry')
    hits = [r for r in manifest.get('hit_regions', []) if isinstance(r, list) and len(r) == 5 and r[0] == key]
    expected = [key, bounds['x'], bounds['y'], bounds['x'] + bounds['width'], bounds['y'] + bounds['height']]
    require(len(hits) == 1 and all(abs(a-b) < 0.01 for a, b in zip(hits[0], expected)),
            'Original callback geometry differs from the published native hit record')


def verify_run(run_id: str, chain: frozenset[str] = frozenset()) -> dict:
    require(RUN_ID.fullmatch(run_id) is not None and run_id not in chain, 'Invalid or cyclic policy run identity')
    evidence, runtime = EVIDENCE / run_id, (RUNTIME / run_id).resolve(strict=True)
    request_path, result_path = evidence / 'request.json', evidence / 'result.json'
    request, result = load_json(request_path, 'policy request'), load_json(result_path, 'policy result')
    resume = request.get('resume_from')
    require(resume is None or isinstance(resume, dict), 'Policy resume lineage must be an object or null')
    check_artifacts(request)
    check_artifacts(result)
    require(request.get('run_id') == result.get('run_id') == run_id and
            all(request.get(k) is True for k in ('social_policy_smoke', 'smoke', 'decisions', 'top_panel')) and
            request.get('trade_route_smoke') is False and request.get('stage_or_mods_changed') is False,
            'Run is not the requested isolated original SocialPolicy profile')
    require(result.get('returncode') == 0 and result.get('timed_out') is False and result.get('failures') == [] and
            result.get('runtime_inputs_unchanged') is True and result.get('status', '').endswith('PASS') and
            result.get('social_policy_sequence_verified') is True, 'Policy run did not complete cleanly')
    artifact_ref(result.get('request'), exact=request_path)
    output = artifact_ref(result.get('stdout'), exact=evidence / 'stdout.log').read_text(encoding='utf8').replace('\r\n', '\n').replace('\r', '\n')
    stderr = artifact_ref(result.get('stderr'), exact=evidence / 'stderr.log').read_text(encoding='utf8')
    require(not re.search(r'HOST_FAILURE|HOST_NATIVE_EXCEPTION|HOST_CLEANUP_PENDING|INTERACTIVE_INPUT_REJECTED', output + stderr),
            'Policy Host reported a native or input failure')
    timeline_ok, failure = verify_social_policy_dispatch_timeline(output)
    require(timeline_ok, str(failure))
    require(Path(request.get('cwd', '')).resolve(strict=True) == runtime, 'Policy runtime escaped its immutable directory')
    host, bundle, _ = verified_runtime_bundle(request, runtime, 'SocialPolicy')
    build_path = artifact_ref(request.get('provenance', {}).get('host_build'))
    build = load_json(build_path, 'sealed policy Host build')
    require(build.get('status') == 'UI_WINDOW_HOST_CANDIDATE_BUILT' and build.get('source_inputs_unchanged') is True and
            digest(host) == build.get('executable', {}).get('sha256'), 'Policy Host does not match its sealed build')
    sources = {Path(r['path']).name: r for r in build.get('sources', [])}
    source_proof = {}
    for name in ('SocialPolicySmokeFixture.h', 'InteractiveGameLoop.h', 'InteractiveGameSession.h', 'UiPopupContext.h', 'InteractiveUiSession.h', 'UiScene.lua'):
        require(name in sources, 'Host lacks frozen policy integration source ' + name)
        frozen = compiled_build_source(build['build_id'], sources[name], 'Source\\Host\\' + name,
                                       'project' if name.endswith('.lua') else 'include_roots/project')
        source_proof[name] = {'path': str(frozen), 'sha256': digest(frozen)}
    generated, generated_paths = generated_map(result, runtime)
    verify_frozen_support(request, evidence, runtime)
    attempt = load_json(artifact_ref(result.get('attempt'), exact=evidence / 'attempt.json'), 'Host attempt')
    require(attempt.get('status') == 'FINISHED' and attempt.get('returncode') == 0 and attempt.get('timed_out') is False and
            attempt.get('pid') == result.get('driver_pid'), 'Policy driver did not terminate under its recorded identity')
    inventory_stages = ('initial', 'before', 'adopted', 'returned', 'next-turn') + (() if resume else ('cancelled', 'branch', 'funded'))
    inventories = {stage: load_json(unique_generated(generated, f'social-policy-{stage}-inventory.json'), stage + ' policy inventory')
                   for stage in inventory_stages}
    for value in inventories.values():
        validate_inventory(value)
    actions = {int(stage): {'id': name, 'key': int(key), 'generation': int(generation), 'revision': int(revision), 'payload': int(payload)}
               for stage, name, key, generation, revision, payload in re.findall(
                   r'^INTERACTIVE_SOCIAL_POLICY_ACTION=(\d+)\|([^|]+)\|(\d+)\|(\d+)\|(\d+)\|(-?\d+)$', output, re.M)}
    adoptions = []
    if not resume:
        branch, policy = actions[2]['payload'], actions[7]['payload']
        require(inventories['before'] == inventories['cancelled'] and
                unique_generated(generated, 'social-policy-before-state.txt').read_bytes() ==
                unique_generated(generated, 'social-policy-cancelled-state.txt').read_bytes(),
                'Original No callback changed full SDK state or policy/culture inventory')
        verify_exact_culture_grant(inventories['branch'], inventories['funded'])
        adoptions = [verify_adoption(inventories['before'], inventories['branch'], branch, False),
                     verify_adoption(inventories['funded'], inventories['adopted'], policy, True)]
        require(inventories['before']['culture'] == inventories['before']['nextCost'] and
                inventories['branch']['culture'] == inventories['adopted']['culture'] == 0,
                'Culture fixture retained surplus culture beyond exactly two paid adoptions')
        require(next(r for r in inventories['funded']['policies'] if r['id'] == policy)['branch'] == branch,
                'Confirmed policy does not belong to the selected branch')
    else:
        require(inventories['before'] == inventories['adopted'] and
                unique_generated(generated, 'social-policy-before-state.txt').read_bytes() ==
                unique_generated(generated, 'social-policy-adopted-state.txt').read_bytes(),
                'Restored policy viewer changed saved SDK state or policy/culture inventory')
    require(inventories['returned'] == inventories['adopted'] and
            unique_generated(generated, 'social-policy-returned-state.txt').read_bytes() ==
            unique_generated(generated, 'social-policy-adopted-state.txt').read_bytes(),
            'Tabs, checkbox, close, reopen, or Escape changed adopted gameplay state')
    opts = request.get('policy_info_options', {})
    require(type(opts.get('policy_info')) is int and opts['policy_info'] in (0, 1), 'PolicyInfo initial option is missing')
    initial_option = bool(opts['policy_info'])
    source_option = opts.get('source', {})
    option_path = Path(source_option.get('original_path', '')).resolve(strict=True)
    require(digest(option_path) == source_option.get('sha256') and option_path.stat().st_size == source_option.get('bytes'),
            'Original option source changed during the policy run')
    original_ini = opts.get('original_user_settings', {})
    ini_path = Path(original_ini.get('original_path', '')).resolve(strict=True)
    require(ini_path.name == 'UserSettings.ini' and digest(ini_path) == original_ini.get('sha256') and
            ini_path.stat().st_size == original_ini.get('bytes'), 'Original UserSettings.ini was modified by the policy session')
    ini_values = re.findall(r'^\s*PolicyInfo\s*=\s*([01])\s*$', ini_path.read_text(encoding='utf-8-sig'), re.M)
    require(len(ini_values) == 1 and opts.get('original_policy_info') == int(ini_values[0]),
            'PolicyInfo original INI provenance does not match its actual setting')
    if opts.get('origin') == 'ORIGINAL_USER_SETTINGS_READ_ONLY':
        require(option_path == ini_path and opts['policy_info'] == int(ini_values[0]),
                'Fresh policy option was not selected from the original read-only INI')
    stored_options = load_json(unique_generated(generated, 'ui-options.json'), 'committed UI session options')
    require(stored_options == {'schema': 'ZEROSIS_UI_OPTIONS_V1', 'policyInfo': not initial_option},
            'Original checkbox did not persist its changed value to the isolated UI session')
    frames = re.findall(r'^INTERACTIVE_UI_FRAME=(\d+)\|(\d+)\|(\d+)\|social-policy\|(\d+)\|(\d+)\|([^|\r\n]+)\|([^|\r\n]+)$', output, re.M)
    require(frames, 'No native SocialPolicy frames were published')
    by_generation, snapshots = {}, []
    for revision, generation, turn, hwnd, device, snapshot_name, folder in frames:
        snapshot_path = Path(snapshot_name).resolve(strict=True)
        require(snapshot_path in generated_paths, 'Policy frame snapshot is not a pinned generated artifact')
        manifest_path = trade_route_frame_manifest(snapshot_path, folder, generated_paths, runtime / 'sessions')
        manifest = load_json(manifest_path, 'policy scene manifest')
        snapshot = load_json(snapshot_path, 'actual SDK policy scene')
        for field, filename in (('originalLayoutLua', 'SocialPolicyPopup.lua'), ('originalLayoutXml', 'SocialPolicyPopup.xml')):
            original = artifact_ref(snapshot.get('socialPolicy', {}).get(field), label='original policy layout')
            require(original.name == filename and original.as_posix().endswith('/Assets/DLC/Expansion2/UI/InGame/Popups/' + filename),
                    'Policy snapshot does not identify the installed original SocialPolicyPopup source')
        prep_path = Path(folder) / 'preparation_inputs.json'
        require(prep_path.resolve(strict=True) in generated_paths, 'Policy frame lacks its frozen preparation inputs')
        preparation = load_json(prep_path, 'policy preparation inputs')
        rules_db = artifact_ref(preparation.get('rules_database'))
        require(rules_db in generated_paths and rules_db.parent == snapshot_path.parent,
                'Policy branch identities are not sourced from this SDK session rules DB')
        with sqlite3.connect(rules_db.as_uri() + '?mode=ro', uri=True) as connection:
            branch_names = dict(connection.execute('SELECT ID, Type FROM PolicyBranchTypes'))
        artifact_ref(manifest.get('snapshot'), exact=snapshot_path)
        packet = artifact_ref(manifest.get('packet'), exact=Path(folder) / 'scene.packet')
        require(packet in generated_paths and manifest.get('context') == 'social-policy' and
                manifest.get('retail_pixels_verified') is False, 'Policy renderer packet has wrong context or evidence scope')
        frame = {'revision': int(revision), 'generation': int(generation), 'turn': int(turn),
                 'hwnd': int(hwnd), 'device': int(device), 'snapshot': snapshot, 'manifest': manifest,
                 'path': str(snapshot_path), 'sha256': digest(snapshot_path)}
        frame['branch_names'] = branch_names
        require(frame['generation'] not in by_generation and frame['hwnd'] > 0 and frame['device'] > 0,
                'Policy frames duplicate a generation or have no native HWND/device')
        by_generation[frame['generation']] = frame
        snapshots.append(frame)
    require(len({(f['hwnd'], f['device']) for f in snapshots}) == 1, 'Policy route changed its HWND or device')
    for stage in ((9, 10, 11, 12, 17) if resume else (2, 3, 4, 5, 7, 8, 9, 10, 11, 12, 17)):
        action = actions[stage]
        require(action['generation'] in by_generation, f'Policy action {stage} did not use a retained native frame')
        frame = by_generation[action['generation']]
        require(frame['revision'] == action['revision'], 'Policy action revision differs from its published frame')
        inventory = inventories['before' if stage <= 5 else 'funded' if stage in (7, 8) else 'adopted']
        verify_snapshot(frame['snapshot'], inventory, 'Ideologies' if stage == 10 else 'SocialPolicies',
                        not initial_option if stage in (12, 17) else initial_option, stage in (3, 5, 8), frame['branch_names'])
        if stage != 17:
            verify_visible_target(frame['snapshot'], frame['manifest'], action['key'], action['id'], action['payload'])
    top_inputs = [tuple(map(int, row)) for row in re.findall(r'^INTERACTIVE_TOP_PANEL_INPUT=(\d+)\|(\d+)\|(\d+)\|(\d+)\|([01])$', output, re.M)]
    top_frames = re.findall(r'^INTERACTIVE_TOP_PANEL_FRAME=(\d+)\|(\d+)\|(-?\d+)\|(-?\d+)\|(\d+)\|(\d+)\|([^|\r\n]+)\|([^|\r\n]+)$', output, re.M)
    for stage in (1, 16):
        action = actions[stage]
        matching = [r for r in top_inputs if r[0] == action['generation'] and r[1] == 1 and r[2] == action['key'] and r[4] == 1]
        require(len(matching) == 1 and matching[0][2] - matching[0][3] == 1 << 51,
                'CultureString posted key did not reach its original TopPanel callback namespace')
        top = [row for row in top_frames if int(row[1]) == action['generation']]
        require(len(top) == 1, 'CultureString action lacks its exact retained TopPanel frame')
        top_snapshot = Path(top[0][6]).resolve(strict=True)
        require(top_snapshot in generated_paths, 'CultureString source snapshot escaped generated artifacts')
        top_manifest_path = trade_route_frame_manifest(top_snapshot, top[0][7], generated_paths, runtime / 'sessions')
        verify_visible_target(load_json(top_snapshot, 'TopPanel entry scene'),
                              load_json(top_manifest_path, 'TopPanel native entry packet'), matching[0][3], 'CultureString', -1)
        require((int(top[0][4]), int(top[0][5])) == (snapshots[0]['hwnd'], snapshots[0]['device']),
                'CultureString opened its policy UI in a different native HWND or device')
    final_inventory = inventories['next-turn']
    require(final_inventory['turn'] == inventories['adopted']['turn'] + 1 and
            {r['id'] for r in final_inventory['policies'] if r['has']} == {r['id'] for r in inventories['adopted']['policies'] if r['has']} and
            {r['id'] for r in final_inventory['branches'] if r['unlocked']} == {r['id'] for r in inventories['adopted']['branches'] if r['unlocked']},
            'Normal next turn lost adopted policies or branches')
    final_state = unique_generated(generated, 'play-final-state.txt')
    identity = sdk_state_identity(final_state.read_bytes(), 'Policy final save')
    saves = re.findall(r'^INTERACTIVE_NATIVE_SAVE=(\d+)\|(.+)$', output, re.M)
    require(len(saves) >= 2 and identity[:3] == (final_inventory['turn'], final_inventory['elapsed'], final_inventory['activePlayer']),
            'Policy sequence lacks repeated native saves at its observed next turn')
    archives = []
    for turn, save_name in saves:
        path = Path(save_name).resolve(strict=True)
        require(path in generated_paths and int(turn) == identity[0], 'Policy native save is not the pinned final-turn artifact')
        archives.append(inspect_save(path, bundle, path.parent / 'Civ5SavedGameDatabase.db',
                                     expected=(1, 0, *identity[:3], 64, 64, 133)))
    restore = None
    grants = [tuple(map(int, row)) for row in re.findall(r'^INTERACTIVE_SOCIAL_POLICY_CULTURE_FIXTURE=(\d+)\|(\d+)\|(\d+)\|(\d+)\|(\d+)$', output, re.M)]
    if resume:
        source_id = resume.get('run_id')
        require(type(source_id) is str and source_id != run_id and source_id not in chain, 'Invalid policy checkpoint lineage')
        source_proof = verify_run(source_id, chain | {run_id})
        source_request = load_json(EVIDENCE / source_id / 'request.json', 'policy checkpoint source request')
        source_result = load_json(EVIDENCE / source_id / 'result.json', 'policy checkpoint source result')
        source_runtime = (RUNTIME / source_id).resolve(strict=True)
        source_generated, source_paths = generated_map(source_result, source_runtime)
        prior = load_json(unique_generated(source_generated, 'social-policy-next-turn-inventory.json'), 'source saved policy inventory')
        require(not grants and inventories['initial'] == prior and inventories['before'] == prior,
                'Restore re-granted culture or lost its original saved SDK policy inventory')
        require(opts.get('origin') == 'RESUMED_SESSION_UI_OPTIONS' and opts.get('run_id') == source_id and
                opts['policy_info'] == int(source_proof['final_policy_info']), 'Restore ignored the previous isolated UI option')
        require(result.get('fresh_process_restore_verified') is True and result.get('checkpoint_input_unchanged') is True and
                result.get('semantic_restore_equal') is True and source_result.get('pid') != result.get('pid') and
                source_result.get('driver_pid') != result.get('driver_pid'), 'Policy restore lacks a distinct verified Host/driver process')
        require(type(result.get('pid')) is int and result['pid'] > 0 and type(source_result.get('pid')) is int and source_result['pid'] > 0 and
                type(result.get('driver_pid')) is int and result['driver_pid'] > 0 and
                type(source_result.get('driver_pid')) is int and source_result['driver_pid'] > 0,
                'Policy restore process identities are missing or invalid')
        prior_result = artifact_ref(resume.get('run_result'), exact=evidence / 'resume-source-result.json')
        require(prior_result.read_bytes() == (EVIDENCE / source_id / 'result.json').read_bytes(), 'Frozen policy source result changed')
        source_host, source_bundle, _ = verified_runtime_bundle(source_request, source_runtime, 'Policy restore source')
        require(digest(source_host) == digest(host) and digest(source_bundle) == digest(bundle), 'Policy restore migrated the sealed native bundle')
        checkpoint = artifact_ref(resume.get('checkpoint_input'), exact=runtime / 'checkpoint-input.zssave')
        source_save = artifact_ref(resume.get('checkpoint_source'))
        require(source_save in source_paths and checkpoint.read_bytes() == source_save.read_bytes(), 'Policy checkpoint changed or escaped its saved source')
        initial_state = unique_generated(generated, 'play-initial-state.txt')
        source_state = unique_generated(source_generated, 'play-final-state.txt')
        require(initial_state.read_bytes() == source_state.read_bytes(), 'Restored SDK startup differs from source final state')
        restore_identity = sdk_state_identity(initial_state.read_bytes(), 'Policy restored startup')
        expected = (1, 0, *restore_identity[:3], 64, 64, 133)
        source_archive = inspect_save(source_save, source_bundle, source_save.parent / 'Civ5SavedGameDatabase.db', expected=expected)
        roundtrip = unique_generated(generated, 'play-restored-checkpoint.zssave')
        restored_archive = inspect_save(roundtrip, bundle, initial_state.parent / 'Civ5SavedGameDatabase.db', expected=expected)
        previous_sections = {(r['kind'], r['index']): r['sha256'] for r in source_archive['sections']}
        restored_sections = {(r['kind'], r['index']): r['sha256'] for r in restored_archive['sections']}
        require(previous_sections.keys() == restored_sections.keys() and len(previous_sections) == 133, 'Policy restore native section inventory differs')
        changed = sorted(key for key in previous_sections if previous_sections[key] != restored_sections[key])
        require(all(key == (3, 0) for key in changed), 'Policy restore changed a native player/team/other section')
        reported = re.findall(r'^INTERACTIVE_RESTORE_SECTIONS_EQUAL=(\d+)\|(\d+)$', output, re.M)
        require(reported == [(str(133-len(changed)), '133')], 'Native restore section log differs from independent archive comparison')
        changed_markers = [tuple(map(int, row)) for row in re.findall(r'^INTERACTIVE_RESTORE_SECTION_CHANGED=(\d+)\|(\d+)$', output, re.M)]
        require(changed_markers == changed and
                re.findall(r'^INTERACTIVE_RESTORE_IDLE_STATE_UNCHANGED=(true)$', output, re.M) == ['true'],
                'Native restore section-change or idle state log is missing or inconsistent')
        restore = {'source_run_id': source_id, 'player_sections_byte_equal': True, 'changed_native_sections': changed,
                   'sdk_policy_inventory_exact': True, 'fixture_mutation_applied': False,
                   'game_reload_rng_equivalence_verified': False}
    else:
        require(len(grants) == 2 and grants[0][0] == 1 and grants[0][1] + grants[0][2] == grants[0][3] == inventories['before']['culture'] and
                grants[0][4] == inventories['before']['turn'] == 0 and
                grants[1] == (2, 0, inventories['funded']['culture'], inventories['funded']['culture'], 0),
                'Fresh policy fixture is not exactly two observed next-cost culture-only grants')
    return {'status': 'PASS_INTERACTIVE_SOCIAL_POLICY_NATIVE_SDK_SMOKE', 'run_id': run_id,
            'result': {'path': str(result_path), 'sha256': digest(result_path)}, 'source_proof': source_proof,
            'adoptions': adoptions, 'posted_actions': len(actions), 'native_policy_inputs': 5 if resume else 11,
            'original_cancel_sdk_state_unchanged': None if resume else True, 'final_policy_info': not initial_option,
            'original_policy_saving_option': False, 'culture_fixture_grants': grants,
            'original_option_source_unchanged': True, 'normal_turn_policy_state_preserved': True,
            'native_save_count': len(archives), 'restore': restore,
            'retail_pixels_verified': False, 'full_policy_gameplay_verified': False,
            'unverified_policy_routes': ['blocked branch switching', 'ideology tenet selection', 'ideology change'],
            'stage_or_mods_changed': False}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        result = verify_run(args.run_id)
    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        result = {'status': 'FAIL_INTERACTIVE_SOCIAL_POLICY_NATIVE_SDK_SMOKE', 'run_id': args.run_id, 'error': str(exc)}
    target = args.output or EVIDENCE / args.run_id / 'social_policy_validation.json'
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps({'status': result['status'], 'output': str(target), 'error': result.get('error')}, ensure_ascii=False))
    return 0 if result['status'].startswith('PASS_') else 1


if __name__ == '__main__':
    sys.exit(main())
