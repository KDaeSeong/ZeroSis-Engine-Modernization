"""Independently verify one frozen actual-SDK official city-production UI run."""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from collect_baseline import PROJECT, digest
from probe_world_builder import artifact
from verify_city_decision_probe import (
    _decision_snapshot_semantics, _unit_id, fail, inspect_state_snapshot,
    int_row, lines, one, recorded, verify_game_restore,
)
from verify_first_turn_candidate import inspect_save
from verify_world_builder_map_object import check_artifacts

ROOT = PROJECT / 'evidence/city_production_ui'
LANGUAGES = {'en_US', 'ko_KR'}
REQUIRED_HOST = {
    'HostMain.cpp', 'HostRun.h', 'HostServices.h', 'LocalGameCommands.h',
    'LocalSdkSession.h', 'FoundCityProbe.h', 'CityDecisionProbe.h',
    'UiPopupContext.h', 'UiInputDispatch.h', 'UiPopupAssets.generated.h',
    'UiAudioPlayback.h', 'HostServices.h',
}
VALIDATOR_INPUTS = (
    PROJECT / 'tools/verify_city_production_ui.py',
    PROJECT / 'tools/verify_city_decision_probe.py',
    PROJECT / 'tools/verify_native_save_restore.py',
    PROJECT / 'tools/verify_restore_game_metadata.py',
    PROJECT / 'tools/verify_world_builder_map_object.py',
    PROJECT / 'tools/prepare_ui_popup_assets.py',
    PROJECT / 'tools/civ5_ui_assets.py',
    PROJECT / 'Source/Host/UiScene.lua',
    PROJECT / 'Source/Presentation/UiPresentationInput.lua',
    PROJECT / 'Source/Host/ProductionCommandGuard.lua',
    PROJECT / 'tools/verify_production_window.py',
    PROJECT / 'tools/ui_window_frame.py',
    PROJECT / 'tools/live_ui_window_driver.py',
    PROJECT / 'tools/live_production_window_driver.py',
    PROJECT / 'tools/verify_production_interactions.py',
    PROJECT / 'Source/Host/UiAudioPlayback.h',
    PROJECT / 'Source/Host/HostServices.h',
)


def freeze_validator() -> tuple[Path, list[dict], dict[str, str]]:
    proof = ROOT / 'validators' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ_') + uuid.uuid4().hex[:12])
    proof.mkdir(parents=True, exist_ok=False)
    rows = []
    hashes = {}
    for source in VALIDATOR_INPUTS:
        if not source.is_file():
            fail(f'Missing UI verifier/source provenance input: {source}')
        before = digest(source)
        target = proof / source.name
        shutil.copy2(source, target)
        row = artifact(target)
        if row['sha256'] != before:
            fail(f'Frozen UI verifier/source differs: {source}')
        rows.append({'original_path': str(source), **row})
        hashes[str(source)] = before
    return proof, rows, hashes


def host_provenance(request: dict) -> dict:
    build_row = request.get('candidate_build')
    shared_row = request.get('shared_lua_build')
    found_row = request.get('found_value_shared_sdk_build')
    for row in (build_row, shared_row, found_row):
        if not isinstance(row, dict):
            fail('Production UI request lacks a frozen host/shared-Lua/shared-found-value build report')
        check_artifacts(row)
    build = json.loads(Path(build_row['path']).read_text(encoding='utf-8'))
    shared = json.loads(Path(shared_row['path']).read_text(encoding='utf-8'))
    found = json.loads(Path(found_row['path']).read_text(encoding='utf-8'))
    if found.get('status') != 'FOUND_VALUE_SHARED_SDK_CANDIDATE_LINKED' or \
       found.get('gamecore', {}).get('sha256') != 'a58a0d20cbaecad13ea248fe362d0c15bb97096802b9f60c5ef5f0dd8bb90c07':
        fail('Run did not use the designated a58 shared-found-values GameCore')
    if shared.get('status') != 'SHARED_LUA_RUNTIME_CANDIDATE_BUILT':
        fail('Run did not pin the shared Lua runtime build')
    sources = {Path(row.get('path', '')).name: row for row in build.get('sources', [])}
    if not REQUIRED_HOST <= sources.keys():
        fail('Frozen Host source closure omits a required production UI route file')
    for name, row in sources.items():
        if name in REQUIRED_HOST:
            check_artifacts(row)
    source_text = {name: Path(sources[name]['path']).read_text(encoding='utf-8') for name in REQUIRED_HOST}
    main, run, popup = source_text['HostMain.cpp'], source_text['HostRun.h'], source_text['UiPopupContext.h']
    native_ui = source_text['UiPopupContext.h']
    if 'UI_WINDOW_PROCESS_START=%lu' not in main or 'GetCurrentProcessId()' not in main or \
       'std::fflush(stderr);' not in main or 'HOST_FAILURE:' not in main or \
       'HOST_NATIVE_EXCEPTION_CONTEXT|' not in main:
        fail('Frozen HostMain does not establish the exact stderr start marker and failure diagnostics contract')
    guard_path = PROJECT / 'Source/Host/ProductionCommandGuard.lua'
    guard = guard_path.read_text(encoding='utf-8')
    preparer = (PROJECT / 'tools/prepare_ui_popup_assets.py').read_text(encoding='utf-8')
    ui_scene = (PROJECT / 'Source/Host/UiScene.lua').read_text(encoding='utf-8')
    input_addendum = (PROJECT / 'Source/Presentation/UiPresentationInput.lua').read_text(encoding='utf-8')
    if 'ProductionCommandGuard' not in preparer or 'UiPopupAssets.generated.h' not in preparer or \
       'def cpp_literal(data)' not in preparer:
        fail('Frozen UI asset preparer lacks the recorded guard-to-generated-header path')
    if '--check-city-production-ui' not in main or 'UiPopupKind::Production' not in run or \
       'ChooseProductionUnit' not in run or 'target.hasVoidPayload' not in popup or \
       'target.void1==6' not in popup or 'target.void2==choice.unit' not in popup:
        fail('Frozen Host closure does not establish the official production popup and exact native void-pair choice')
    for token in ('Game.CityPushOrder', 'city:CanTrain', 'city:CanConstruct', 'city:CanCreate',
                  'city:CanMaintain', 'IsCanPurchase', "purchase('CityPurchaseUnit'",
                  "purchase('CityPurchaseBuilding'", "purchase('CityPurchaseProject'"):
        if token not in guard:
            fail(f'Production Lua guard provenance omits expected legality/forwarding token: {token}')
    input_gate = guard.find("ZeroSisUiNative('requirePurchaseInput'")
    purchase_legality = guard.find("assert(city:IsCanPurchase")
    purchase_forward = guard.find('return original(city,id,yield)')
    native_input_gate = native_ui.find('if(std::strcmp(operation,"requirePurchaseInput")==0)')
    native_input_method = native_ui.find('void RequirePurchaseInput(int city)')
    native_input_reject = native_ui.find('!dispatching_ || !host_.deferCityPurchase', native_input_method)
    native_input_error = native_ui.find('throw std::logic_error("Purchase requires its original production input callback")', native_input_reject)
    if input_gate < 0 or purchase_legality < 0 or purchase_forward < 0 or \
       not input_gate < purchase_legality < purchase_forward or native_input_gate < 0 or \
       native_input_method < 0 or native_input_reject < native_input_method or native_input_error < native_input_reject:
        fail('Frozen Lua/native guard does not require an active original purchase-input scope before SDK forwarding')
    fixture_call = native_ui.find('pcall(Game.CityPurchaseUnit,city,unit,YieldTypes.YIELD_GOLD)')
    fixture_rejection = native_ui.find("reason:find('Purchase requires its original production input callback',1,true)", fixture_call)
    if fixture_call < 0 or fixture_rejection < fixture_call or \
       'Out-of-input purchase was not rejected before SDK mutation' not in native_ui or \
       'SdkStateSnapshot::Capture(host_)!=beforeChoice || host_.Events()!=previousEvents' not in native_ui:
        fail('Frozen actual-city fixture does not prove out-of-input rejection preserves gameplay and command events')
    if "if type(value)=='number' then value=tostring(finite(value)) end" not in ui_scene or \
       "local sx,sy=(value.attributes.AnchorSide or 'I,I'):match('^(%a)[,.](%a)$')" not in ui_scene or \
       "Stock ProductionPopup's Food label combines C,C with O.I." not in ui_scene:
        fail('Frozen UI scene source lacks the observed Population:SetText(number) or Food anchor contract')
    generated_header = source_text['UiPopupAssets.generated.h']
    if 'Generated by tools/prepare_ui_popup_assets.py' not in generated_header or \
       'ProductionCommandGuard' not in generated_header or 'ProductionPopup' not in generated_header:
        fail('Frozen generated UI asset header lacks preparer/guard/official popup provenance')
    guard_bytes = guard_path.read_bytes()
    encoded_guard = '\n'.join('"' + ''.join(f'\\x{byte:02x}' for byte in guard_bytes[i:i + 64]) + '"'
                              for i in range(0, len(guard_bytes), 64))
    if encoded_guard not in generated_header:
        fail('Frozen generated UI asset header does not byte-embed the retained ProductionCommandGuard.lua')
    ui_payload = (PROJECT / 'Source/Host/UiScene.lua').read_bytes() + b'\n' + \
                 (PROJECT / 'Source/Presentation/UiPresentationInput.lua').read_bytes()
    encoded_ui = '\n'.join('"' + ''.join(f'\\x{byte:02x}' for byte in ui_payload[i:i + 64]) + '"'
                            for i in range(0, len(ui_payload), 64))
    if encoded_ui not in generated_header:
        fail('Frozen generated UI asset header does not byte-embed the retained scene/input sources')
    inputs = {Path(row['path']).name: row for row in request.get('inputs', [])}
    for name in ('ZeroSisHost_x64.exe', 'CvGameCoreDLL_Expansion2_x64.dll', 'ZeroSisLua51_x64.dll'):
        if name not in inputs:
            fail(f'Actual immutable runtime inputs omit {name}')
        check_artifacts(inputs[name])
    if inputs['ZeroSisHost_x64.exe']['sha256'] != build.get('executable', {}).get('sha256') or \
       inputs['ZeroSisLua51_x64.dll']['sha256'] != shared.get('lua_dll', {}).get('sha256') or \
       inputs['CvGameCoreDLL_Expansion2_x64.dll']['sha256'] != found['gamecore']['sha256']:
        fail('Private runtime executable/GameCore/Lua hashes differ from their frozen build reports')
    if request.get('shared_found_value_sdk_enabled') is not True or request.get('official_production_ui_requested') is not True:
        fail('Run request did not select shared-found-values and official production UI modes')
    return {'candidate_build': build_row, 'shared_lua_build': shared_row,
            'found_value_shared_sdk_build': found_row,
            'host_sources': {name: sources[name] for name in sorted(REQUIRED_HOST)},
            'gamecore_sha256': found['gamecore']['sha256'],
            'host_executable_sha256': inputs['ZeroSisHost_x64.exe']['sha256'],
            'shared_lua_sha256': inputs['ZeroSisLua51_x64.dll']['sha256'],
            'compiler_input_count': len(build.get('compiler_inputs', []))}


def verify_run(run_id: str, *, native_window=False, live_interactions=False) -> dict:
    if live_interactions and not native_window:fail('Live interaction inspection requires native window proof')
    if not re.fullmatch(r'\d{8}T\d{6}Z_[0-9a-f]{12}', run_id):
        fail('Run ID has an invalid immutable identity format')
    directory = ROOT / run_id
    result_path = directory / 'result.json'
    result = json.loads(result_path.read_text(encoding='utf-8'))
    check_artifacts(result)
    request = json.loads(Path(result['request']['path']).read_text(encoding='utf-8'))
    check_artifacts(request)
    language = request.get('language')
    if request.get('run_id') != run_id or language not in LANGUAGES or \
       result.get('status') != 'ISOLATED_SDK_OFFICIAL_PRODUCTION_UI_TURN_AND_NATIVE_RESTORE_PASS':
        fail('Runtime is not a successful official production UI SDK run')
    if result.get('exit_code') != 0 or result.get('pid', 0) <= 0 or result.get('timed_out') is not False or \
       result.get('host_failures') != [] or result.get('official_production_ui_enabled') is not True or \
       result.get('official_production_callback_verified') is not True or result.get('accepted_stage_promoted') is not False:
        fail('Runtime exit/PID/timeout/callback/lifecycle facts do not prove a clean private SDK run')
    mode='--check-city-production-ui-live' if live_interactions else '--check-city-production-ui-window' if native_window else '--check-city-production-ui'
    if request.get('command', [None])[1:] != [mode, language] or \
       request.get('production_window_requested',False) is not native_window or \
       result.get('production_window_enabled',False) is not native_window or \
       request.get('production_interactions_requested',False) is not live_interactions or \
       result.get('production_interactions_enabled',False) is not live_interactions or \
       Path(request.get('cwd', '')).resolve() != (PROJECT / 'Build/CityProductionUiRuntime' / run_id).resolve():
        fail('Runner command or private runtime directory differs from the requested UI mode')
    output = Path(result['stdout']['path']).read_text(encoding='utf-8').replace('\r\n', '\n').replace('\r', '\n')
    stderr = Path(result['stderr']['path']).read_text(encoding='utf-8', errors='replace')
    stderr_lines = stderr.replace('\r\n', '\n').replace('\r', '\n').splitlines()
    expected_start = f'UI_WINDOW_PROCESS_START={result["pid"]}'
    if any('HOST_FAILURE:' in line or 'HOST_NATIVE_EXCEPTION' in line for line in stderr_lines):
        fail('Production UI runtime emitted a Host failure or native exception diagnostic')
    if stderr_lines != [expected_start]:
        fail('Production UI stderr must contain exactly the frozen HostMain start marker matching the runner PID')
    purchase_rejection_marker = 'PRODUCTION_UI_OUT_OF_INPUT_PURCHASE_REJECTED_BEFORE_MUTATION=true'
    if output.splitlines().count(purchase_rejection_marker) != 1:
        fail('Actual runtime lacks the unique stdout proof that an out-of-input purchase was rejected before mutation')
    markers = (
        'PRODUCTION_UI_INPUT_ROUTE=OFFICIAL_BNW_POPUP_RETAINED_BUTTON_SDK_RECEIVER',
        'PRODUCTION_UI_TIMER_SEMAPHORE=0', 'PRODUCTION_UI_OWNER_CLOCK=0,0.25',
        'PRODUCTION_UI_FRAME_GAMEPLAY_STATE_EQUAL=true',
        'PRODUCTION_UI_SHUTDOWN_PASS ORIGINAL_POPUP_CALLBACK=true SDK_RECEIVER=true TURN_AND_NATIVE_RESTORE=true RETAIL_UI_EQUIVALENCE=false',
        'CITY_DECISION_INPUT_ROUTE=OFFICIAL_PRODUCTION_UI_AND_ENGINE_NETWORK_SEND_RESEARCH',
        'CITY_DECISION_RESTORE_FRESH_SESSION=true', 'CITY_DECISION_RESTORED_CORE_MODULE_UNLOADED=true',
        'CITY_DECISION_RESTORE_STATE_EQUAL=true', 'CITY_DECISION_RESTORE_IDLE_STATE_EQUAL=true',
        'CITY_DECISION_RESTORE_IDLE_UPDATES=3',
    )
    for marker in markers:
        if output.splitlines().count(marker) != 1:
            fail(f'Actual runtime lacks one unique required lifecycle/route marker: {marker}')
    if one(output, 'PRODUCTION_UI_OWNER_CLOCK') != '0,0.25' or \
       one(output, 'UI_POPUP_CONTEXT_CLOSED') != '1':
        fail('Production owner clock or popup callback lifecycle marker differs')
    # There must be exactly one success marker, and it must be the official UI mode marker.
    success_markers = [line for line in output.splitlines() if line.startswith('PRODUCTION_UI_SHUTDOWN_PASS ')]
    if success_markers != [markers[4]]:
        fail('Runtime success marker is absent, duplicated, or claims a different scope')
    shown_log = one(output, 'UI_POPUP_shown') if lines(output, 'UI_POPUP_shown') else None
    frame_log = one(output, 'UI_POPUP_frame-1') if lines(output, 'UI_POPUP_frame-1') else None
    closed_log = one(output, 'UI_POPUP_closed') if lines(output, 'UI_POPUP_closed') else None
    if not shown_log or not frame_log or not closed_log:
        fail('Production popup shown/frame-1/closed snapshots were not retained')
    selection = int_row(one(output, 'PRODUCTION_UI_SELECTION'), 3, 'official production UI selection')
    if selection[0] < 0 or selection[1] != 1 or selection[2] <= 0:
        fail('Production input did not select the required rules unit ID 1 through a live button key')
    if result.get('production_ui_selection_logs') != lines(output, 'PRODUCTION_UI_SELECTION'):
        fail('Runner result did not retain the exact native production selection log')
    if lines(output, 'UI_POPUP_CONTEXT') != ['OFFICIAL_BNW_PRODUCTION_PERSISTENT_VM_RETAINED_CONTROLS']:
        fail('The shown scene did not come from the official retained Production context')
    before = int_row(one(output, 'CITY_DECISION_BEFORE_TURN'), 12, 'decision before turn')
    after = int_row(one(output, 'CITY_DECISION_AFTER_TURN'), 12, 'decision after turn')
    restored = [int_row(value, 12, 'restored decision observation') for value in lines(output, 'CITY_DECISION_RESTORED')]
    if len(restored) != 4 or restored != [after] * 4 or before[6] != 1 or before[7] != 0 or \
       after[:3] != [1, 1, 0] or after[4] != 1 or after[6] != 1 or after[7] <= 0:
        fail('Official UI order did not produce the expected one-item queue and preserved turn-one restore')
    if result.get('city_decision_before_turn_logs') != lines(output, 'CITY_DECISION_BEFORE_TURN') or \
       result.get('city_decision_after_turn_logs') != lines(output, 'CITY_DECISION_AFTER_TURN') or \
       result.get('city_decision_restored_logs') != lines(output, 'CITY_DECISION_RESTORED'):
        fail('Runner JSON did not retain the exact SDK observation rows')
    if result.get('research_ui_verified') is not False or result.get('decision_ui_verified') is not False or \
       result.get('renderer_verified') is not False or result.get('interactive_input_verified') is not False or \
       result.get('retail_save_compatibility_verified') is not False:
        fail('Result overstates UI, pixel, human-input or retail-equivalence proof')
    runtime = Path(request['cwd']).resolve()
    session_paths = [Path(one(output, key)).resolve() for key in
                     ('SESSION_DIRECTORY', 'FOUND_CITY_RESTORE_SESSION_DIRECTORY', 'CITY_DECISION_RESTORE_SESSION_DIRECTORY')]
    if len(set(session_paths)) != 3 or any(not path.is_relative_to(runtime / 'sessions') for path in session_paths):
        fail('Initial, turn-zero restore and turn-one restore sessions are not distinct private sessions')
    generated = result.get('generated_files', [])
    for item in generated:
        check_artifacts(item)
    session = {'initial': session_paths[0], 'turn_zero_restore': session_paths[1], 'turn_one_restore': session_paths[2]}
    shown_log_fields = shown_log.split(','); frame_log_fields = frame_log.split(','); closed_log_fields = closed_log.split(',')
    if len(shown_log_fields) != 3 or len(frame_log_fields) != 3 or len(closed_log_fields) != 3 or \
       shown_log_fields[:2] != ['1', '0'] or frame_log_fields[:2] != ['1', '0'] or closed_log_fields[:2] != ['1', '0']:
        fail('Shown/frame/closed UI snapshot identity or turn differs')
    ui_dir = session['turn_zero_restore']
    shown_path = ui_dir / 'ui-popup-1-shown.json'
    frame_path = ui_dir / 'ui-popup-1-frame-1.json'
    closed_path = ui_dir / 'ui-popup-1-closed.json'
    shown_doc = json.loads(recorded(result, shown_path, runtime).read_text(encoding='utf-8'))
    frame_doc = json.loads(recorded(result, frame_path, runtime).read_text(encoding='utf-8'))
    closed_doc = json.loads(recorded(result, closed_path, runtime).read_text(encoding='utf-8'))
    if shown_doc.get('contextName') != 'ProductionPopup' or frame_doc.get('contextName') != 'ProductionPopup' or \
       closed_doc.get('contextName') != 'ProductionPopup' or \
       shown_doc.get('popupKind') != 'Production' or frame_doc.get('popupKind') != 'Production' or \
       closed_doc.get('popupKind') != 'Production' or shown_doc.get('timerSemaphore') != 0 or \
       frame_doc.get('timerSemaphore') != 0 or closed_doc.get('timerSemaphore') != 0 or \
       shown_doc.get('active') is not True or frame_doc.get('active') is not True or closed_doc.get('active') is not False or \
       shown_doc.get('presentationClock') != 0 or frame_doc.get('presentationClock') != 0.25 or \
       (closed_doc.get('presentationClock',0) <= 0.25 if live_interactions else closed_doc.get('presentationClock') != 0.25) or \
       shown_doc == frame_doc or closed_doc == shown_doc:
        fail('Official Production snapshots do not preserve the timer/clock/lifecycle contract')
    for log_fields, snapshot_path in ((shown_log_fields, shown_path), (frame_log_fields, frame_path),
                                      (closed_log_fields, closed_path)):
        if int(log_fields[2]) != snapshot_path.stat().st_size:
            fail('Native snapshot size marker does not match its retained JSON file')
    def find_key(node, key):
        if isinstance(node, dict):
            if node.get('key') == key:
                return node
            for child in node.values():
                found = find_key(child, key)
                if found is not None:
                    return found
        elif isinstance(node, list):
            for child in node:
                found = find_key(child, key)
                if found is not None:
                    return found
        return None
    button = find_key(shown_doc.get('tree'), selection[2])
    if not isinstance(button, dict) or button.get('kind') != 'Button':
        fail('Selected production row key is not an actual retained Button in the shown snapshot')
    # New retained snapshots carry only the scalar callback void pair in their
    # inputTargets manifest. The native collector still proves the live choice.
    if 'inputTargets' in shown_doc:
        targets=shown_doc['inputTargets']
        if not isinstance(targets,list):fail('Production inputTargets must be a captured callback array')
        selected_targets=[row for row in targets if isinstance(row,dict) and row.get('key')==selection[2] and row.get('event')=='LeftClick']
        if len(selected_targets)!=1 or selected_targets[0].get('event')!='LeftClick' or \
           selected_targets[0].get('visible') is not True or selected_targets[0].get('disabled') is not False or \
           (selected_targets[0].get('void1'),selected_targets[0].get('void2'))!=(6,selection[1]):
            fail('Captured selected input target does not match the native official unit callback pair')
        tree_text=json.dumps(shown_doc['tree'])
        if any(key in tree_text for key in ('void1','void2','hasVoidPayload')):
            fail('Retained visual tree must not claim native callback payload fields')
    elif any(key in json.dumps(shown_doc) for key in ('void1','void2','hasVoidPayload')):
        fail('Historical UI snapshot unexpectedly claims callback payload fields')
    prov = host_provenance(request)
    window_proof=None
    if live_interactions:
        from verify_production_interactions import verify_interactions
        window_proof=verify_interactions(request,result,output,directory,runtime)
    elif native_window:
        from verify_production_window import verify_window
        window_proof=verify_window(result,request,output,selection,ui_dir)
    # Recorded artifacts are path/hash checked before reading session products.
    rules_rows = [row for row in request['inputs'] if Path(row['path']).name == 'rules.db']
    loc_rows = [row for row in request['inputs'] if Path(row['path']).name == 'localization.db']
    if len(rules_rows) != 1 or len(loc_rows) != 1:
        fail('Run request lacks its unique rules/localization databases')
    rules = Path(rules_rows[0]['path']); localization = Path(loc_rows[0]['path'])
    for label, path in session.items():
        for name in ('rules.db', 'Civ5SavedGameDatabase.db'):
            recorded(result, path / name, runtime)
    checkpoint_logs = [Path(value).resolve() for value in lines(output, 'NATIVE_CHECKPOINT_WRITTEN')]
    expected_checkpoints = [(session['initial'] / 'checkpoint-turn-0.zssave').resolve(),
                            (session['turn_zero_restore'] / 'checkpoint-turn-1.zssave').resolve()]
    if checkpoint_logs != expected_checkpoints:
        fail('Native checkpoint stdout paths differ from the actual initial and post-decision session files')
    # Keep the founding fixture's turn-zero restore semantics exact.
    initial = recorded(result, session['initial'] / 'state-after-founded-city.txt', runtime).read_bytes()
    restored0 = recorded(result, session['turn_zero_restore'] / 'state-after-found-city-restore.txt', runtime).read_bytes()
    idle0 = recorded(result, session['turn_zero_restore'] / 'state-after-found-city-idle.txt', runtime).read_bytes()
    if initial != restored0 or initial != idle0:
        fail('Turn-zero fresh restore or three idle updates changed the founding state')
    for path in (shown_path, frame_path, closed_path):
        if not path.is_relative_to(runtime / 'sessions'):
            fail('Production popup snapshot escaped the private SDK session directory')
    # Save archive proof reuses strict dynamic replay/session validation from the city-decision verifier.
    cp0 = recorded(result, session['initial'] / 'checkpoint-turn-0.zssave', runtime)
    restore0 = recorded(result, session['turn_zero_restore'] / 'state-after-found-city-restore.zssave', runtime)
    cp1 = recorded(result, session['turn_zero_restore'] / 'checkpoint-turn-1.zssave', runtime)
    restore1 = recorded(result, session['turn_one_restore'] / 'state-after-city-decision-restore.zssave', runtime)
    archive = [
        verify_game_restore(cp0, restore0, rules=Path(session['initial'] / 'rules.db'), localization=localization,
                            language=language, turn=0),
        verify_game_restore(cp1, restore1, rules=Path(session['turn_zero_restore'] / 'rules.db'), localization=localization,
                            language=language, turn=1),
    ]
    manifest_rows = [row for row in request['inputs'] if Path(row['path']).name == 'bundle.manifest']
    if len(manifest_rows) != 1:
        fail('Run request lacks its unique bundle manifest')
    manifest = Path(manifest_rows[0]['path'])
    inspect_save(cp0, manifest, session['initial'] / 'Civ5SavedGameDatabase.db', expected=(1, 0, 0, 0, 0, 64, 64, 133))
    inspect_save(restore0, manifest, session['turn_zero_restore'] / 'Civ5SavedGameDatabase.db', expected=(1, 0, 0, 0, 0, 64, 64, 133))
    inspect_save(cp1, manifest, session['turn_zero_restore'] / 'Civ5SavedGameDatabase.db', expected=(1, 0, 1, 1, 0, 64, 64, 133))
    inspect_save(restore1, manifest, session['turn_one_restore'] / 'Civ5SavedGameDatabase.db', expected=(1, 0, 1, 1, 0, 64, 64, 133))
    actual_turn_path = recorded(result, session['turn_zero_restore'] / 'state-after-city-decision-turn.txt', runtime)
    actual_turn = actual_turn_path.read_bytes()
    before_save = recorded(result, session['turn_zero_restore'] / 'state-before-save.txt', runtime).read_bytes()
    restored1 = recorded(result, session['turn_one_restore'] / 'state-after-city-decision-restore.txt', runtime).read_bytes()
    idle1 = recorded(result, session['turn_one_restore'] / 'state-after-city-decision-idle.txt', runtime).read_bytes()
    if actual_turn != before_save or actual_turn != restored1 or actual_turn != idle1:
        fail('Turn-one state changed before save, on fresh restore, or during three idle updates')
    inspect_state_snapshot(actual_turn_path, 1)
    semantic = _decision_snapshot_semantics(actual_turn, before, after)
    if result.get('official_production_ui_enabled') is not True:
        fail('Actual SDK route lacks the official production UI execution flag')
    return {'run_id': run_id, 'language': language, 'status': result['status'], 'pid': result['pid'],
            'exit_code': result['exit_code'], 'timed_out': result['timed_out'],
            'production_selection': selection, 'production_before': before, 'production_after_turn': after,
            'restored_observations': restored, 'decision_semantics': semantic,
            'snapshot_artifacts': {'shown': artifact(shown_path), 'frame_1': artifact(frame_path), 'closed': artifact(closed_path)},
            'turn_zero_restore_idle_equal': True, 'turn_one_restore_and_idle_equal': True,
            'restore_archive_metadata': archive, 'host_provenance': prov,
            'out_of_input_purchase_rejected_before_mutation': True,
            'stderr_start_marker_verified': True,
            'production_window_enabled':native_window,'production_interactions_enabled':live_interactions,'production_window_proof':window_proof,
            'research_route': 'Network.SendResearch API route only', 'research_ui_verified': False,
            'ui_pixels_verified': False, 'human_input_verified': False,
            'retail_ui_equivalence_verified': False, 'retail_save_compatibility_verified': False}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='append', required=True, help='Actual production UI runtime run ID; repeat once per language')
    parser.add_argument('--native-window', action='store_true',help='Require actual clipped unit hit and same-window GPU refresh proof')
    parser.add_argument('--live-interactions', action='store_true',help='Require actual production category/pointer/panel-wheel and stale-scene interaction proof')
    args = parser.parse_args()
    if args.live_interactions:args.native_window=True
    if len(args.run) != 2 or len(set(args.run)) != 2:
        parser.error('Provide exactly one distinct en_US run and one ko_KR run')
    proof, frozen, hashes = freeze_validator()
    rows = [verify_run(run_id,native_window=args.native_window,live_interactions=args.live_interactions) for run_id in args.run]
    if {row['language'] for row in rows} != LANGUAGES:
        fail('Supply one actual SDK run for each en_US and ko_KR language')
    en = next(row for row in rows if row['language'] == 'en_US')
    ko = next(row for row in rows if row['language'] == 'ko_KR')
    for field in ('production_selection', 'production_before', 'production_after_turn', 'restored_observations'):
        if en[field] != ko[field]:
            fail(f'EN/KO SDK production semantics differ: {field}')
    for name in ('host_executable_sha256', 'gamecore_sha256', 'shared_lua_sha256'):
        if en['host_provenance'][name] != ko['host_provenance'][name]:
            fail(f'EN/KO runs did not use identical immutable {name}')
    api_baseline_path = PROJECT / 'evidence/city_decisions/conformance.json'
    if not api_baseline_path.is_file():
        fail('Existing EN/KO SDK city-decision API baseline is missing')
    api_baseline = json.loads(api_baseline_path.read_text(encoding='utf-8'))
    check_artifacts(api_baseline)
    api_baseline_actual_path = Path(api_baseline['path']).resolve()
    api_baseline = json.loads(api_baseline_actual_path.read_text(encoding='utf-8'))
    check_artifacts(api_baseline)
    if api_baseline.get('status') != 'ISOLATED_SDK_CITY_DECISIONS_TURN_AND_NATIVE_RESTORE_PAIR_PASS':
        fail('Existing city-decision API baseline is not a validated EN/KO SDK pair')
    api_runs = {row.get('language'): row for row in api_baseline.get('runs', [])}
    for ui_row in rows:
        baseline = api_runs.get(ui_row['language'])
        if not baseline or baseline.get('decision_before') != ui_row['production_before'] or \
           baseline.get('decision_after_turn') != ui_row['production_after_turn']:
            fail('Official production UI 12-value state rows differ from the retained same-language API route proof')
    after = {path: digest(Path(path)) for path in hashes}
    if after != hashes:
        fail('Validator/preparer/guard source changed during inspection')
    if any(digest(Path(row['path'])) != row['sha256'] for row in frozen):
        fail('Frozen validator/provenance files changed during inspection')
    report = {'status': 'ISOLATED_SDK_OFFICIAL_PRODUCTION_UI_TURN_AND_NATIVE_RESTORE_PAIR_PASS',
              'scope': 'ACTUAL_SDK_PRODUCTION_CATEGORY_POINTER_PANEL_WHEEL_SCENE_EPOCHS_UNIT_ORDER_TURN_AND_RESTORE_EN_KO' if args.live_interactions else
                       'ACTUAL_SDK_OFFICIAL_PRODUCTION_UNIT_NATIVE_HIT_GPU_REFRESH_TURN_AND_FRESH_RESTORE_EN_KO' if args.native_window else
                       'ACTUAL_SDK_OFFICIAL_PRODUCTION_CONTEXT_BUTTON_VOID_SELECTION_TURN_AND_FRESH_RESTORE_EN_KO',
              'runs': rows, 'language_pair': ['en_US', 'ko_KR'], 'same_host_and_gamecore': True,
              'same_shared_lua': True, 'source_freeze_verified': True, 'frozen_sources': frozen,
              'source_hashes_before': hashes, 'source_hashes_after': after,
              'proof_directory': str(proof), 'production_ui_input_verified': True,
              'production_selection_verified': True, 'turn_advance_verified': True,
              'native_unit_hit_dispatch_verified':args.native_window,
              'gpu_frame_bitmap_parity_verified':args.native_window,
              'same_hwnd_device_closed_refresh_verified':args.native_window,
              'production_categories_verified':args.live_interactions,
              'production_hover_clear_verified':args.live_interactions,
              'empty_panel_wheel_routing_and_clamp_verified':args.live_interactions,
              'stale_scene_generation_control_event_rejection_verified':args.live_interactions,
              'stale_zero_pointer_reconciliation_verified':args.live_interactions,
              'positive_scroll_motion_verified':False,
              'api_route_state_rows_semantically_equal': True,
              'api_route_baseline_index': artifact(api_baseline_path),
              'api_route_baseline': artifact(api_baseline_actual_path),
              'fresh_restore_and_three_idle_updates_verified': True,
              'host_start_marker_pid_verified': True,
              'out_of_input_purchase_rejection_verified': True,
              'research_ui_verified': False, 'ui_pixels_verified': False,
              'human_input_verified': False, 'retail_ui_equivalence_verified': False,
              'retail_save_compatibility_verified': False, 'accepted_stage_promoted': False,
              'limitations': ['This production-popup scenario verifies that purchase calls outside the original input callback are rejected before SDK mutation; it does not claim a successful purchase.']}
    check_artifacts(report)
    path = proof / 'conformance.json'
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps({'status': report['status'], 'proof': artifact(path),
                      'runs': [{'run_id': row['run_id'], 'language': row['language'],
                                'production_selection': row['production_selection']} for row in rows]}, ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'CITY_PRODUCTION_UI_CONFORMANCE_FAILED: {exc}', file=sys.stderr)
        raise
