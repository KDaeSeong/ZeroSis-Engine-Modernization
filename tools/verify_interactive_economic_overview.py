"""Independently inspect a real original EconomicOverview HWND smoke run.

Read-only against the immutable run, except for its small validation report.
No native launch, renderer invocation, SDK setup write or synthetic snapshot.
The SDK state files are semantic samples, not a proof of every GameCore field.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

from collect_baseline import PROJECT, digest
from economic_overview_timeline import ACTION, FIXTURE, TOP_BASE, GENERAL_BASE, verify_economic_overview_timeline
from interactive_ui_driver import validate_economic_overview_scene_proof
from ui_pixel_scene import compose_economic_overview_snapshot, validate_economic_overview_prepared
from verify_first_turn_candidate import inspect_save
from verify_world_builder_map_object import check_artifacts
from verify_interactive_trade_route import (
    RUN_ID, VerificationError, artifact_ref, compiled_build_source, generated_map,
    load_json, require, sdk_state_identity, trade_route_frame_manifest, unique_generated,
    verified_runtime_bundle, verify_frozen_support,
)

EVIDENCE = PROJECT / 'evidence/interactive_game'
RUNTIME = PROJECT / 'Build/InteractiveGameRuntime'
ORIGINAL = {
    'EconomicOverview.lua': '5c701550e4559288da0fb1c4c64edabe4b4a5a1deeea7e3bc3a5a2dd848c037a',
    'EconomicOverview.xml': '0476696b5c5972da26bbd934334915fb46d97d1ba14169898bb951eedbe7ced2',
    'EconomicGeneralInfo.lua': '761d54084a70988a28646085963cf824056e21efe06d8727c6541d2609f57dff',
    'EconomicGeneralInfo.xml': '0d72dd6e306149b22559c9e9731af9d0e6b8044b13d5d001c51cf800074c4888',
    'HappinessInfo.lua': '51f5dd99d1bf844076d95f6455e859d3e74acc239c5b3cca902e1c258cc69233',
    'HappinessInfo.xml': 'ecaec12fda8370424d08ae1ce82a270fef4bec6b75c1030f92b7c2ef6a62786b',
}


def nodes(tree: dict):
    require(type(tree) is dict and type(tree.get('children')) is list, 'Malformed captured control tree')
    yield tree
    for child in tree['children']:
        yield from nodes(child)


def one_control(tree: dict, *, key: int | None = None, name: str | None = None) -> dict:
    rows = [row for row in nodes(tree) if (key is None or row.get('key') == key) and (name is None or row.get('id') == name)]
    require(len(rows) == 1, f'Expected exactly one original control {name or key}')
    return rows[0]


def visible_target(snapshot: dict, manifest: dict, key: int, name: str, *, payload: tuple[int, ...] = ()) -> dict:
    targets = [row for row in snapshot.get('inputTargets', []) if row.get('key') == key and row.get('event') == 'LeftClick']
    require(len(targets) == 1 and targets[0].get('id') == name and targets[0].get('visible') is True and
            targets[0].get('disabled') is False, f'Published native key does not identify the visible original {name}')
    target = targets[0]
    for field, value in zip(('void1', 'void2'), payload):
        require(type(target.get(field)) is int and target[field] == value, f'Original {name} callback lost its {field} payload')
    bounds = target.get('clippedBounds', {})
    require(all(type(bounds.get(field)) in (int, float) for field in ('x', 'y', 'width', 'height')) and
            bounds['width'] > 0 and bounds['height'] > 0, 'Native target lacks positive clipped geometry')
    hits = [row for row in manifest.get('hit_regions', []) if type(row) is list and len(row) == 5 and row[0] == key]
    expected = [key, bounds['x'], bounds['y'], bounds['x'] + bounds['width'], bounds['y'] + bounds['height']]
    require(len(hits) == 1 and all(abs(a - b) < 0.01 for a, b in zip(hits[0], expected)),
            'Original callback bounds differ from the compiled native hit record')
    return target


def city_state(data: bytes, owner: int, city: int) -> list[str]:
    matches = [line.split('|') for line in data.decode('utf8').splitlines() if line.startswith(f'C|{owner}|{city}|')]
    require(len(matches) == 1 and len(matches[0]) == 12, 'SDK state sample lacks its exact selected city row')
    return matches[0]


def verify_production_delta(before: bytes, after: bytes, owner: int, city: int, selected: int) -> None:
    old, new = before.decode('utf8').splitlines(), after.decode('utf8').splitlines()
    require(len(old) == len(new), 'Production selection added or removed a sampled SDK row')
    changed = [(a.split('|'), b.split('|')) for a, b in zip(old, new) if a != b]
    require(len(changed) == 1, 'Production selection did not change exactly one sampled SDK city row')
    a, b = changed[0]
    require(a == city_state(before, owner, city) and b == city_state(after, owner, city) and
            b[8] == str(selected) and b[9] == '-1' and a[8] != b[8] and
            all(a[index] == b[index] for index in range(12) if index not in (7, 8, 9)),
            'Economic selection changed unrelated sampled city state or did not replace its unit production')


def verify_choice_capture(captured: dict, published: dict, manifest: dict, key: int, selected: int) -> None:
    require((captured.get('contextName'), captured.get('popupKind')) == ('ProductionPopup', 'Production') and
            captured.get('active') is True and captured.get('timerSemaphore') == 0,
            'Economic choice capture is not the active original ProductionPopup')
    target = visible_target(captured, manifest, key, 'Button', payload=(6, selected))
    require(target == visible_target(published, manifest, key, 'Button', payload=(6, selected)),
            'Economic choice capture differs from its exact published production callback')
    captured_button, published_button = (one_control(snapshot['tree'], key=key, name='Button')
                                         for snapshot in (captured, published))
    for name, fields in (('UnitName', ('text',)), ('ProductionButtonImage', ('texture', 'textureX', 'textureY'))):
        captured_control, published_control = (one_control(button, name=name) for button in (captured_button, published_button))
        require(all(field in captured_control and captured_control[field] == published_control.get(field) for field in fields),
                'Economic choice capture lost its actually selected production name/icon')


def returned_production_target(snapshot: dict, city: int) -> dict:
    targets = [row for row in snapshot.get('inputTargets', []) if row.get('id') == 'ProdButton' and
               row.get('void1') == city and row.get('event') == 'LeftClick']
    require(len(targets) == 1, 'Returned General city must expose exactly one production LeftClick target')
    return targets[0]


def native_save_paths(output: str, generated_paths: set[Path], turn: int) -> list[Path]:
    saves = re.findall(r'^INTERACTIVE_NATIVE_SAVE=(\d+)\|([^\r\n]+)$', output, re.M)
    require(len(saves) >= 2 and len(saves) == len(re.findall(r'^INTERACTIVE_NATIVE_SAVE=', output, re.M)),
            'Economic smoke lacks repeated well-formed final-turn native saves')
    paths = [Path(filename).resolve(strict=True) for _, filename in saves]
    require(len(set(paths)) == len(paths), 'Economic smoke reused a native save path instead of writing distinct saves')
    require(all(path in generated_paths and int(saved_turn) == turn for (saved_turn, _), path in zip(saves, paths)),
            'Economic save escaped its pinned session or final turn')
    return paths


def verify_run(run_id: str, chain: frozenset[str] = frozenset()) -> dict:
    require(RUN_ID.fullmatch(run_id) is not None and run_id not in chain, 'Invalid or cyclic economic run identity')
    evidence, runtime = EVIDENCE / run_id, (RUNTIME / run_id).resolve(strict=True)
    request_path, result_path = evidence / 'request.json', evidence / 'result.json'
    request, result = load_json(request_path, 'economic request'), load_json(result_path, 'economic result')
    check_artifacts(request)
    check_artifacts(result)
    resume = request.get('resume_from')
    require(resume is None or type(resume) is dict, 'Economic restore lineage must be an object or null')
    require(request.get('run_id') == result.get('run_id') == run_id and
            all(request.get(field) is True for field in ('economic_overview_smoke', 'smoke', 'decisions', 'top_panel')) and
            all(not request.get(field) for field in ('trade_route_smoke', 'social_policy_smoke', 'social_policy_tenets',
                'tech_award', 'unit_actions', 'worker_build', 'combat_smoke', 'city_capture_smoke', 'declare_war_smoke')) and
            request.get('stage_or_mods_changed') is False and
            request.get('input_profile') == 'POSTED_HWND_ORIGINAL_ECONOMIC_OVERVIEW_SMOKE',
            'Run is not the isolated original EconomicOverview scenario')
    require(result.get('returncode') == 0 and result.get('timed_out') is False and result.get('failures') == [] and
            result.get('runtime_inputs_unchanged') is True and result.get('status', '').endswith('_PASS') and
            all(result.get(field) is True for field in ('economic_overview_requested', 'economic_overview_dispatch_verified',
                                                       'economic_overview_sequence_verified', 'decision_ui_sequence_verified')),
            'Economic run did not complete cleanly through its real decision sequence')
    artifact_ref(result.get('request'), exact=request_path)
    output = artifact_ref(result.get('stdout'), exact=evidence / 'stdout.log').read_text(encoding='utf8').replace('\r\n', '\n').replace('\r', '\n')
    stderr = artifact_ref(result.get('stderr'), exact=evidence / 'stderr.log').read_text(encoding='utf8')
    require(not re.search(r'HOST_FAILURE|HOST_NATIVE_EXCEPTION|HOST_CLEANUP_PENDING|INTERACTIVE_INPUT_REJECTED|SCRIPT_FAILURE', output + stderr),
            'Economic Host reported a native, Lua or input failure')
    verified, reason = verify_economic_overview_timeline(output)
    require(verified, str(reason))
    fixture = FIXTURE.search(output)
    owner, turn, city = map(int, fixture.group(2, 3, 4))
    require((fixture[1] == 'RESTORED') is bool(resume), 'Economic fixture did not follow its requested fresh/restore profile')
    require(Path(request.get('cwd', '')).resolve(strict=True) == runtime, 'Economic runtime escaped its exact directory')
    host, bundle, _ = verified_runtime_bundle(request, runtime, 'EconomicOverview')
    build = load_json(artifact_ref(request.get('provenance', {}).get('host_build')), 'sealed economic Host')
    require(build.get('status') == 'UI_WINDOW_HOST_CANDIDATE_BUILT' and build.get('source_inputs_unchanged') is True and
            digest(host) == build.get('executable', {}).get('sha256'), 'Economic Host differs from its sealed build')
    sources = {Path(row['path']).name: row for row in build.get('sources', [])}
    source_proof = {}
    for name in ('EconomicOverviewSmokeFixture.h', 'InteractiveGameLoop.h', 'InteractiveGameSession.h', 'InteractiveUiSession.h',
                 'UiPopupContext.h', 'UiInputDispatch.h', 'LocalSdkSession.h', 'UiScene.lua'):
        require(name in sources, 'Host lacks economic integration source ' + name)
        path = compiled_build_source(build['build_id'], sources[name], 'Source\\Host\\' + name,
                                     'project' if name.endswith('.lua') else 'include_roots/project')
        source_proof[name] = {'path': str(path), 'sha256': digest(path)}
    adapter = Path(source_proof['LocalSdkSession.h']['path']).read_text(encoding='utf8')
    require('receiver.ResponseCityPushOrder(active,cityID,order,data,alt,shift,control)' in adapter,
            'Economic production did not retain the existing legal SDK Network receiver adapter')
    helper = artifact_ref(request.get('provenance', {}).get('economic_overview_timeline'), exact=evidence / 'economic_overview_timeline.py')
    require(helper.read_bytes() == Path(__file__).with_name('economic_overview_timeline.py').read_bytes(),
            'Independent economic timeline differs from the exact helper frozen by this runner')
    generated, generated_paths = generated_map(result, runtime)
    support = verify_frozen_support(request, evidence, runtime)
    prepared = load_json(Path(support['catalogs']['asset_preparation_provenance']['path']), 'frozen economic prepared inputs')
    prepared_proof = validate_economic_overview_prepared(prepared, verify_files=True)
    originals = [prepared_proof['parent'], *prepared_proof['children'].values()]
    require({Path(row[field]['path']).name: row[field]['sha256'] for row in originals for field in ('lua', 'xml')} == ORIGINAL,
            'Economic parent or child no longer uses the six exact original Lua/XML bytes')
    attempt = load_json(artifact_ref(result.get('attempt'), exact=evidence / 'attempt.json'), 'economic driver attempt')
    require(attempt.get('status') == 'FINISHED' and attempt.get('returncode') == 0 and attempt.get('timed_out') is False and
            attempt.get('pid') == result.get('driver_pid'), 'Economic driver did not finish under its recorded process identity')
    driver = load_json(artifact_ref(result.get('interactive_ui_driver'), exact=evidence / 'driver_result.json'), 'economic UI driver')
    require(driver.get('status') == 'INTERACTIVE_UI_DRIVER_PASS', 'Economic driver failed its original scene contracts')
    scenes = driver.get('scene_requests', [])
    actions = {int(row[1]): {'id': row[2], 'key': int(row[3]), 'generation': int(row[4]), 'revision': int(row[5]), 'payload': int(row[6])}
               for row in ACTION.finditer(output)}
    ui_frames = re.findall(r'^INTERACTIVE_UI_FRAME=(\d+)\|(\d+)\|(-?\d+)\|([^|]+)\|(\d+)\|(\d+)\|([^|\r\n]+)\|([^|\r\n]+)$', output, re.M)
    top_frames = re.findall(r'^INTERACTIVE_TOP_PANEL_FRAME=(\d+)\|(\d+)\|(-?\d+)\|(-?\d+)\|(\d+)\|(\d+)\|([^|\r\n]+)\|([^|\r\n]+)$', output, re.M)
    identities, frames = set(), {}

    def scene(sequence: int, context: str, path_text: str, folder: str) -> tuple[dict, dict]:
        path = Path(path_text).resolve(strict=True)
        require(path in generated_paths, 'Economic frame snapshot is not a pinned generated artifact')
        manifest_path = trade_route_frame_manifest(path, folder, generated_paths, runtime / 'sessions')
        manifest = load_json(manifest_path, 'economic native frame manifest')
        artifact_ref(manifest.get('snapshot'), exact=path)
        packet = artifact_ref(manifest.get('packet'), exact=Path(folder) / 'scene.packet')
        require(packet in generated_paths and manifest.get('context') == context and manifest.get('retail_pixels_verified') is False,
                'Economic frame has the wrong packet context or claims retail equivalence')
        matched = [row for row in scenes if row.get('sequence') == sequence and row.get('context') == context]
        require(len(matched) == 1 and matched[0].get('snapshot_before_sha256') == digest(path) == matched[0].get('snapshot_after_sha256') and
                artifact_ref(matched[0].get('manifest'), exact=manifest_path) == manifest_path,
                'Economic published frame lacks the exact completed driver scene acknowledgement')
        snapshot = load_json(path, 'economic native frame snapshot')
        if context == 'economic-overview':
            validate_economic_overview_scene_proof(snapshot, manifest, prepared, closed=False)
            snapshot, _ = compose_economic_overview_snapshot(snapshot, prepared)
        return snapshot, manifest

    for stage, action in actions.items():
        top = stage in (1, 16)
        matches = [row for row in (top_frames if top else ui_frames) if int(row[1]) == action['generation']]
        require(len(matches) == 1, f'Economic stage {stage} lacks its exact published native frame')
        row = matches[0]
        context = 'top-panel' if top else 'production' if stage in (11, 13) else 'economic-overview'
        require(int(row[0]) == action['revision'] and int(row[2]) == turn and (top or row[3] == context),
                f'Economic stage {stage} frame revision, turn or popup context differs')
        identities.add((int(row[4]), int(row[5])))
        snapshot, manifest = scene(int(row[0]), context, row[6], row[7])
        frames[stage] = (snapshot, manifest)
        if stage != 18:
            payload = (0,) if stage in (2, 3) else (city,) if stage in (10, 12) else (6, action['payload']) if stage == 13 else ()
            visible_target(snapshot, manifest, action['key'] - TOP_BASE if top else action['key'], action['id'], payload=payload)
        if context == 'economic-overview':
            expected_tab = 'HappinessInfo' if stage in (7, 8, 9, 15, 18) else 'EconomicGeneralInfo'
            # Reopen starts a new original parent VM; its default General tab is
            # observed before HappinessButton is clicked again at stage 17.
            require(manifest['economic_overview_scene']['active_child'] == expected_tab,
                    f'Economic stage {stage} did not retain its expected original tab')
    require(len(identities) == 1 and all(value > 0 for value in next(iter(identities))),
            'Economic tabs and production changed their native HWND or D3D device')
    # Both original folding callbacks must change and restore actual visibility.
    for stages, name in (((4, 5, 6), 'CityStack'), ((7, 8, 9), 'CityUnhappinessStack')):
        values = [one_control(frames[stage][0]['tree'], name=name)['hidden'] for stage in stages]
        require(all(type(value) is bool for value in values) and values[0] == values[2] and values[0] != values[1],
                f'Original {name} fold did not toggle and restore its captured state')
    # Production is in front, with the still-active original General/timer1
    # underneath. Its separate packet is never itself a foreground input frame.
    backdrop_proof = []
    for stage in (11, 13):
        revision = actions[stage]['revision'] - 1
        requests = re.findall(r'^INTERACTIVE_UI_SCENE_REQUEST=' + str(revision) + r'\|economic-overview\|([^|\r\n]+)\|([^|\r\n]+)$', output, re.M)
        require(len(requests) == 1, 'Nested economic production lacks its exact retained parent packet')
        snapshot, manifest = scene(revision, 'economic-overview', *requests[0])
        require(snapshot['active'] is True and snapshot['timerSemaphore'] == 1 and
                manifest['economic_overview_scene']['active_child'] == 'EconomicGeneralInfo',
                'Production suspension changed the retained economic tab or parent timer')
        backdrop_files = re.findall(r'^INTERACTIVE_ECONOMIC_BACKDROP=' + str(revision) + r'\|([^\r\n]+)$', output, re.M)
        require(len(backdrop_files) == 1 and Path(backdrop_files[0]).resolve(strict=True) in generated_paths,
                'Economic production lacks its hash-verified native background render')
        backdrop_proof.append({'production_stage': stage, 'parent_revision': revision})

    selection = load_json(unique_generated(generated, 'economic-selection.json'), 'economic SDK selection observation')
    require(selection.get('schema') == 'ZEROSIS_ECONOMIC_SELECTION_V1' and
            all(type(selection.get(field)) is int for field in ('owner', 'turn', 'city', 'oldUnit', 'selectedUnit', 'beforeRow', 'returnedRow', 'queueLength')) and
            (selection['owner'], selection['turn'], selection['city'], selection['queueLength']) == (owner, turn, city, 1) and
            selection['selectedUnit'] == actions[13]['payload'] and selection['oldUnit'] != selection['selectedUnit'] and
            selection['beforeRow'] == actions[12]['key'] and selection['returnedRow'] != selection['beforeRow'],
            'Economic production observation does not match its actual selected original row')
    returned = returned_production_target(frames[14][0], city)
    require(returned['key'] == selection['returnedRow'] and actions[10]['key'] != actions[12]['key'],
             'Cancelled or selected production did not rebuild the retained General city row')
    verified_selection = re.findall(r'^INTERACTIVE_ECONOMIC_PRODUCTION_VERIFIED=(\d+)\|(-?\d+)\|(\d+)\|(\d+)\|(\d+)\|1$', output, re.M)
    require(verified_selection == [tuple(str(selection[field]) for field in ('city', 'oldUnit', 'selectedUnit', 'beforeRow', 'returnedRow'))],
            'Economic production stdout differs from the actual SDK selection and rebuilt General row')
    old_icon = one_control(one_control(frames[12][0]['tree'], key=selection['beforeRow']), name='ProdImage')
    new_icon = one_control(one_control(frames[14][0]['tree'], key=selection['returnedRow']), name='ProdImage')
    chosen = one_control(frames[13][0]['tree'], key=actions[13]['key'])
    selected_name = one_control(chosen, name='UnitName')['text']
    selected_icon = one_control(chosen, name='ProductionButtonImage')
    require(type(selected_name) is str and selected_name and new_icon.get('hidden') is False and
            new_icon.get('tooltip') == selected_name and old_icon.get('tooltip') != selected_name and
            tuple(new_icon.get(field) for field in ('texture', 'textureX', 'textureY')) ==
            tuple(selected_icon.get(field) for field in ('texture', 'textureX', 'textureY')),
            'Refreshed General production name/icon does not match the actual selected original ProductionPopup item')
    # Additional captures are actual VM snapshots, not substitutes for the
    # published frames above. Compare the selected city keys and production text.
    choice = load_json(unique_generated(generated, 'economic-choice-ui.json'), 'choice actual UI capture')
    verify_choice_capture(choice, frames[13][0], frames[13][1], actions[13]['key'], selection['selectedUnit'])
    for suffix, expected_key, expected_tooltip in (
            ('cancel-before', actions[10]['key'], None), ('cancel-returned', selection['beforeRow'], old_icon['tooltip']),
            ('selected-returned', selection['returnedRow'], selected_name)):
        captured = load_json(unique_generated(generated, f'economic-{suffix}-ui.json'), suffix + ' actual UI capture')
        normalized, _ = compose_economic_overview_snapshot(captured, prepared)
        button = one_control(normalized['tree'], key=expected_key, name='ProdButton')
        if expected_tooltip is not None:
            require(one_control(button, name='ProdImage')['tooltip'] == expected_tooltip,
                    'Extra economic observation disagrees with its actual published return frame')
    states = {suffix: unique_generated(generated, f'economic-{suffix}-state.txt').read_bytes()
              for suffix in ('before', 'cancel-returned', 'after', 'returned')}
    require(states['before'] == states['cancel-returned'] and states['after'] == states['returned'],
            'Economic browsing, cancellation, close or reopen changed its sampled SDK state')
    require(sdk_state_identity(states['before'], 'economic before')[0:3:2] == (turn, owner),
            'Economic snapshot scope differs from its actual SDK owner/turn')
    verify_production_delta(states['before'], states['after'], owner, city, selection['selectedUnit'])
    require(int(city_state(states['before'], owner, city)[8]) == selection['oldUnit'],
            'Economic production old unit differs from the SDK state sample')
    selected_state = unique_generated(generated, 'play-decisions-selected-state.txt').read_bytes()
    next_state = unique_generated(generated, 'play-decisions-next-turn-state.txt').read_bytes()
    require(selected_state == states['after'], 'Ordinary turn baseline was taken before the real economic production selection')
    before_city, next_city = city_state(selected_state, owner, city), city_state(next_state, owner, city)
    require(sdk_state_identity(next_state, 'economic next turn')[0] == turn + 1 and next_city[8] == str(selection['selectedUnit']) and
            int(next_city[7]) > int(before_city[7]), 'Normal next turn did not advance the actual economic production order')
    final_state = unique_generated(generated, 'play-final-state.txt').read_bytes()
    identity = sdk_state_identity(final_state, 'economic final save')
    require(identity[0] == turn + 1 and identity[2] == owner and city_state(final_state, owner, city)[8] == str(selection['selectedUnit']),
            'Final saved SDK sample lost the economic production order or next human turn')
    require(all(marker in output for marker in ('INTERACTIVE_DECISION_SMOKE_COMPLETE=1', 'INTERACTIVE_GAME_SESSION_STOPPED=true',
            'INTERACTIVE_PLAY_SHUTDOWN_PASS GAMECORE_LOADED=true GAMECORE_UNLOADED=true')),
            'Economic scenario did not complete normal turn/save/shutdown')
    saves = native_save_paths(output, generated_paths, identity[0])
    for path in saves:
        inspect_save(path, bundle, path.parent / 'Civ5SavedGameDatabase.db', expected=(1, 0, *identity[:3], 64, 64, 133))

    restore = None
    if resume:
        source_id = resume.get('run_id')
        require(type(source_id) is str and RUN_ID.fullmatch(source_id) and source_id != run_id and source_id not in chain,
                'Invalid economic checkpoint source identity')
        prior_proof = verify_run(source_id, chain | {run_id})
        source_request = load_json(EVIDENCE / source_id / 'request.json', 'economic source request')
        source_result = load_json(EVIDENCE / source_id / 'result.json', 'economic source result')
        source_runtime = (RUNTIME / source_id).resolve(strict=True)
        source_generated, source_paths = generated_map(source_result, source_runtime)
        source_host, source_bundle, _ = verified_runtime_bundle(source_request, source_runtime, 'Economic restore source')
        require(digest(host) == digest(source_host) and digest(bundle) == digest(source_bundle), 'Economic restore migrated its sealed native bundle')
        require(all(result.get(field) is True for field in ('fresh_process_restore_verified', 'checkpoint_input_unchanged', 'semantic_restore_equal')) and
                all(type(result.get(field)) is int and result[field] > 0 and type(source_result.get(field)) is int and
                    source_result[field] > 0 and result[field] != source_result[field] for field in ('pid', 'driver_pid')),
                'Economic restore lacks distinct successfully terminated Host/driver processes')
        frozen_prior = artifact_ref(resume.get('run_result'), exact=evidence / 'resume-source-result.json')
        require(frozen_prior.read_bytes() == (EVIDENCE / source_id / 'result.json').read_bytes(), 'Frozen economic source result changed')
        checkpoint = artifact_ref(resume.get('checkpoint_input'), exact=runtime / 'checkpoint-input.zssave')
        source_save = artifact_ref(resume.get('checkpoint_source'))
        require(source_save in source_paths and checkpoint.read_bytes() == source_save.read_bytes(), 'Economic checkpoint bytes changed or escaped source')
        initial = unique_generated(generated, 'play-initial-state.txt')
        source_final = unique_generated(source_generated, 'play-final-state.txt')
        require(initial.read_bytes() == source_final.read_bytes() and
                city_state(initial.read_bytes(), owner, city)[8] == str(prior_proof['production']['selectedUnit']),
                'Economic restore did not recover the previous saved SDK sample and actual production choice')
        initial_id = sdk_state_identity(initial.read_bytes(), 'restored economic startup')
        expected = (1, 0, *initial_id[:3], 64, 64, 133)
        before_archive = inspect_save(source_save, source_bundle, source_save.parent / 'Civ5SavedGameDatabase.db', expected=expected)
        roundtrip = unique_generated(generated, 'play-restored-checkpoint.zssave')
        after_archive = inspect_save(roundtrip, bundle, initial.parent / 'Civ5SavedGameDatabase.db', expected=expected)
        before_sections = {(row['kind'], row['index']): row['sha256'] for row in before_archive['sections']}
        after_sections = {(row['kind'], row['index']): row['sha256'] for row in after_archive['sections']}
        require(before_sections.keys() == after_sections.keys() and len(before_sections) == 133, 'Economic restore section inventory differs')
        changed = sorted(key for key in before_sections if before_sections[key] != after_sections[key])
        require(all(key == (3, 0) for key in changed), 'Economic restore changed a native player/team/other section')
        require(re.findall(r'^INTERACTIVE_RESTORE_SECTIONS_EQUAL=(\d+)\|(\d+)$', output, re.M) == [(str(133 - len(changed)), '133')] and
                [tuple(map(int, row)) for row in re.findall(r'^INTERACTIVE_RESTORE_SECTION_CHANGED=(\d+)\|(\d+)$', output, re.M)] == changed and
                re.findall(r'^INTERACTIVE_RESTORE_IDLE_STATE_UNCHANGED=(true)$', output, re.M) == ['true'],
                'Economic native restore observations disagree with independently inspected save bytes')
        restore = {'source_run_id': source_id, 'player_sections_byte_equal': True, 'changed_native_sections': changed,
                   'saved_production_recovered': True, 'economic_setup_mutations': 0, 'game_reload_rng_equivalence_verified': False}
    return {'status': 'PASS_INTERACTIVE_ECONOMIC_OVERVIEW_NATIVE_SDK_SMOKE', 'run_id': run_id,
            'result': {'path': str(result_path), 'sha256': digest(result_path)}, 'source_proof': source_proof,
            'original_sources': ORIGINAL, 'posted_actions': 18, 'economic_child_dispatches': 8,
            'production': {**selection, 'display_name': selected_name}, 'production_backdrops': backdrop_proof,
            'economic_setup_mutations': 0, 'cancel_sampled_sdk_state_unchanged': True, 'normal_turn_production_advanced': True,
            'native_save_count': len(saves), 'restore': restore, 'retail_pixels_verified': False,
            'full_economic_gameplay_verified': False, 'sdk_state_scope': 'SdkStateSnapshot semantic sample plus actual production getters',
            'stage_or_mods_changed': False}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-id', required=True)
    args = parser.parse_args()
    if RUN_ID.fullmatch(args.run_id) is None:
        parser.error('--run-id must be an immutable interactive run identity')
    target = EVIDENCE / args.run_id / 'economic_overview_validation.json'
    if not target.parent.is_dir() or target.exists():
        parser.error('Economic validation requires an existing run and a new report path')
    try:
        result = verify_run(args.run_id)
    except (OSError, ValueError, KeyError, TypeError, IndexError, RuntimeError) as exc:
        result = {'status': 'FAIL_INTERACTIVE_ECONOMIC_OVERVIEW_NATIVE_SDK_SMOKE', 'run_id': args.run_id, 'error': str(exc)}
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps({'status': result['status'], 'output': str(target), 'error': result.get('error')}, ensure_ascii=False))
    return 0 if result['status'].startswith('PASS_') else 1


if __name__ == '__main__':
    sys.exit(main())
