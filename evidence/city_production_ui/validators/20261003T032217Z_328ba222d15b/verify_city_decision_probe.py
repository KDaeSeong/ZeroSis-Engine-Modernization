"""Strictly inspect actual EN/KO SDK city-decision runs and their three-session saves."""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from collect_baseline import PROJECT, digest
from probe_world_builder import artifact
from verify_explore_sdk_candidate import MAP_SOURCE, comparable_save
from verify_first_turn_candidate import inspect_save, read_artifact
from verify_new_game_candidate import verify_city_site_base
from verify_native_save_restore import inspect_snapshot as inspect_native_snapshot
from verify_restore_game_metadata import (
    REPLAY_MESSAGE_VERSION, _archive, _i32, _reload_text, _random_seed_option_is_disabled, _replay_message,
)
from verify_world_builder_map_object import check_artifacts

ROOT = PROJECT / 'evidence/city_decisions'
ORIGINAL_GAME_SOURCE = PROJECT / 'Source/SDK_BNW_Original/CvGameCoreDLL_Expansion2/CvGame.cpp'
ORIGINAL_PLAYER_SOURCE = PROJECT / 'Source/SDK_BNW_Original/CvGameCoreDLL_Expansion2/CvPlayer.cpp'
BUNDLED_HOST_BUILDER = PROJECT / 'Stage/NativeHost/Review/tools/prepare_native_host_bundle.py'
BUNDLE_BUILDER_SHA256 = '0d9f2da1c9b0cccc2521231b62614ac34bcbbab68641e1f5b32848ec75758be1'
LANGUAGES = {'en_US', 'ko_KR'}
VALIDATORS = (
    'verify_city_decision_probe.py', 'run_found_city_probe.py', 'verify_found_city_probe.py',
    'verify_explore_sdk_candidate.py', 'verify_native_save_restore.py', 'verify_restore_game_metadata.py',
    'verify_first_turn_candidate.py', 'verify_new_game_candidate.py', 'verify_city_site_sdk_candidate.py',
    'verify_world_builder_map_object.py', 'collect_baseline.py', 'probe_world_builder.py',
    'runtime_input_cache.py',
)


def fail(message: str) -> None:
    raise RuntimeError(message)


def lines(output: str, key: str) -> list[str]:
    return re.findall(r'^' + re.escape(key) + r'=([^\r\n]*)$', output, re.M)


def one(output: str, key: str) -> str:
    values = lines(output, key)
    if len(values) != 1:
        fail(f'Expected one runtime observation: {key}, found {len(values)}')
    return values[0]


def int_row(value: str, width: int, label: str) -> list[int]:
    parts = value.split(',')
    if len(parts) != width or any(not re.fullmatch(r'-?\d+', item) for item in parts):
        fail(f'{label} does not have its exact {width}-integer schema')
    return [int(item) for item in parts]


def freeze_inputs() -> tuple[Path, list[dict], dict[str, str], dict]:
    sources = [PROJECT / 'tools' / name for name in VALIDATORS]
    sources.extend((MAP_SOURCE, ORIGINAL_GAME_SOURCE, ORIGINAL_PLAYER_SOURCE, BUNDLED_HOST_BUILDER))
    for source in sources:
        if not source.is_file():
            fail(f'City-decision validator/source reference is missing: {source}')
    before = {str(source): digest(source) for source in sources}
    proof = ROOT / 'validators' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ_') + uuid.uuid4().hex[:12])
    proof.mkdir(parents=True, exist_ok=False)
    records = []
    map_reference = None
    game_reference = None
    for source in sources:
        if source == MAP_SOURCE:
            target = proof / 'CvMap.original.cpp'
        elif source == ORIGINAL_GAME_SOURCE:
            target = proof / 'CvGame.original.cpp'
        elif source == ORIGINAL_PLAYER_SOURCE:
            target = proof / 'CvPlayer.original.cpp'
        elif source == BUNDLED_HOST_BUILDER:
            target = proof / 'prepare_native_host_bundle.pinned.py'
        else:
            target = proof / source.name
        shutil.copy2(source, target)
        row = artifact(target)
        if row['sha256'] != before[str(source)]:
            fail(f'Frozen validator/source reference differs: {source}')
        records.append({'original_path': str(source), **row})
        text = source.read_text(encoding='utf-8', errors='replace')
        if source == MAP_SOURCE:
            required = ('CoCreateGuid(&m_guid)', 'kStream << m_guid.Data1', 'kStream << m_guid.Data2',
                        'kStream << m_guid.Data3', 'kStream >> m_guid.Data1', 'kStream >> m_guid.Data2',
                        'kStream >> m_guid.Data3')
            if any(token not in text for token in required):
                fail('Original CvMap GUID creation/serialization source contract differs')
            map_reference = {'artifact': row,
                             'guid_creation_line': next(i for i, line in enumerate(text.splitlines(), 1)
                                                        if 'CoCreateGuid(&m_guid)' in line),
                             'guid_write_lines': [next(i for i, line in enumerate(text.splitlines(), 1) if token in line)
                                                  for token in ('kStream << m_guid.Data1', 'kStream << m_guid.Data2',
                                                                'kStream << m_guid.Data3')],
                             'guid_read_lines': [next(i for i, line in enumerate(text.splitlines(), 1) if token in line)
                                                 for token in ('kStream >> m_guid.Data1', 'kStream >> m_guid.Data2',
                                                               'kStream >> m_guid.Data3')],
                             'section': [4, 0], 'offset': 34, 'count': 16,
                             'normalization_scope': 'CvMap_m_guid_only_within_each_restore_pair'}
        elif source == ORIGINAL_GAME_SOURCE:
            # CvGame source contains the single authoritative reload append path.
            required = ('void CvGame::Read(FDataStream& kStream)', 'm_mapRand.read(kStream)',
                        'kStream >> m_iNumSessions', '++m_iNumSessions',
                        'Localization::Lookup("TXT_KEY_MISC_RELOAD")',
                        'localizedText << m_iNumSessions',
                        'addReplayMessage(REPLAY_MESSAGE_MAJOR_EVENT, getActivePlayer(), localizedText.toUTF8())')
            if any(token not in text for token in required):
                fail('Original CvGame reload serialization reference is incomplete')
            game_reference = {'artifact': row, 'read_contract_tokens': list(required),
                              'read_function_start_line': next(i for i, line in enumerate(text.splitlines(), 1)
                                                               if 'void CvGame::Read(FDataStream& kStream)' in line)}
        elif source == ORIGINAL_PLAYER_SOURCE:
            required = ('if(!GC.GetEngineUserInterface()->IsPolicyNotificationSeen())',)
            if any(token not in text for token in required):
                fail('Original CvPlayer policy-notification expiry query source reference differs')
            game_reference['policy_notification_expiry'] = {'artifact': row, 'tokens': list(required),
                'query_line': next(i for i, line in enumerate(text.splitlines(), 1) if required[0] in line)}
    return proof, records, before, {'map': map_reference, 'game': game_reference}


def recorded(result: dict, path: Path, runtime: Path) -> Path:
    resolved = path.resolve()
    if not resolved.is_relative_to((runtime.resolve() / 'sessions')):
        fail('SDK session artifact escaped the run-private sessions directory')
    matches = [row for row in result.get('generated_files', [])
               if Path(row.get('path', '')).resolve() == resolved]
    if len(matches) != 1:
        fail(f'Expected exactly one immutable generated-file record: {resolved.name}')
    check_artifacts(matches[0])
    return resolved


def inspect_state_snapshot(path: Path, expected_turn: int) -> tuple[dict, bytes]:
    data = path.read_bytes()
    parsed = inspect_native_snapshot(data, expected_turn=expected_turn, initial_fixture=False)
    return parsed, data


def snapshot_groups(data: bytes) -> dict[str, list[list[str]]]:
    groups: dict[str, list[list[str]]] = {}
    for line in data.decode('utf-8', errors='strict').splitlines():
        fields = line.split('|')
        if not fields or fields[0] not in {'G', 'M', 'P', 'U', 'C', 'T'}:
            fail('State snapshot contains an unknown record')
        groups.setdefault(fields[0], []).append(fields[1:])
    return groups


def verify_founder_snapshot(data: bytes, observation: list[int], settler_type: int) -> dict:
    groups = snapshot_groups(data)
    player, founder, city, x, y, population, after_units = (
        observation[1], observation[2], observation[3], observation[4], observation[5], observation[6], observation[10])
    players = {int(row[0]): [int(value) for value in row] for row in groups['P']}
    p0 = players.get(0)
    if not p0 or p0[1:4] != [1, 1, 1] or p0[5:7] != [1, after_units] or after_units != 1:
        fail('Turn-zero semantic snapshot has the wrong active human city/unit counts')
    cities = [[int(value) for value in row[:-1]] for row in groups['C']]
    owned_cities = [row for row in cities if row[0] == player]
    match = [row for row in owned_cities if row[1] == city]
    if len(owned_cities) != 1 or len(match) != 1 or match[0][2:5] != [x, y, population] or population < 1:
        fail('Actual founded city identity, owner, position or population differs')
    units = [[int(value) for value in row[:-1]] for row in groups['U']]
    owned_units = [row for row in units if row[0] == player]
    if len(owned_units) != after_units or any(row[1] == founder or row[2] == settler_type for row in owned_units):
        fail('SDK did not consume the original founding settler or preserve the expected unit count')
    return {'player': player, 'city_id': city, 'plot': [x, y], 'population': population,
            'founder_unit_id': founder, 'founder_unit_type': settler_type,
            'founder_destroyed': True, 'surviving_human_units': len(owned_units)}


def verify_game_restore(before_path: Path, after_path: Path, *, rules: Path, localization: Path,
                        language: str, turn: int) -> dict:
    _random_seed_option_is_disabled(rules)
    template, _fixture_text = _reload_text(language, localization)
    old_header, old_sections = _archive(before_path)
    new_header, new_sections = _archive(after_path)
    expected_header = {'flags': 0, 'turn': turn, 'elapsed': turn, 'active_player': 0}
    if old_header != expected_header or new_header != expected_header:
        fail(f'Turn-{turn} checkpoint/restore native save header differs')
    changed = [key for key in old_sections if old_sections[key] != new_sections[key]]
    if changed != [(3, 0)]:
        fail(f'Fresh session changed native save sections outside CvGame: {changed}')
    old, new = old_sections[(3, 0)], new_sections[(3, 0)]
    common = min(len(old), len(new))
    count_at = next((i for i in range(common) if old[i] != new[i]), None)
    if count_at is None or count_at < 4 or old[:count_at] != new[:count_at] or \
       _i32(old, count_at - 4) != REPLAY_MESSAGE_VERSION or _i32(new, count_at - 4) != REPLAY_MESSAGE_VERSION:
        fail('CvGame changed before its replay-version/count boundary or the replay version differs')
    old_count, new_count = _i32(old, count_at), _i32(new, count_at)
    if old_count < 0 or old_count > 100000 or new_count != old_count + 1:
        fail('Fresh CvGame read did not append exactly one replay record to the dynamic old count')
    old_cursor = new_cursor = count_at + 4
    for _ in range(old_count):
        old_end, _ = _replay_message(old, old_cursor)
        new_end, _ = _replay_message(new, new_cursor)
        if old[old_cursor:old_end] != new[new_cursor:new_end]:
            fail('An existing CvReplayMessage changed during fresh-session restore')
        old_cursor, new_cursor = old_end, new_end
    new_cursor, appended = _replay_message(new, new_cursor)
    actual = (appended['turn'], appended['type'], appended['plots'], appended['player'])
    if actual != (turn, 0, [(-1, -1)], 0):
        fail(f'CvGame::Read appended the wrong turn-{turn} reload event metadata: {actual}')
    old_sessions, new_sessions = _i32(old, old_cursor), _i32(new, new_cursor)
    if old_sessions < 1 or new_sessions != old_sessions + 1 or old[old_cursor + 4:] != new[new_cursor + 4:]:
        fail('CvGame restore session counter did not increment once or later bytes changed')
    # CvGame::Read formats the newly incremented session counter into the localized
    # replay string. The first restore is session 2; the later restore is session 3.
    if language == 'en_US':
        expected_text = f'Session {new_sessions} starts'
    elif language == 'ko_KR':
        expected_text = f'세션 {new_sessions}' + ('이' if new_sessions == 1 else '가') + ' 시작됐습니다.'
    else:
        fail(f'Unsupported reload localization language: {language}')
    if '{1_number}' not in template:
        fail('Reload localization template does not contain its dynamic session number')
    if (appended['turn'], appended['type'], appended['plots'], appended['player'], appended['text']) != \
       (turn, 0, [(-1, -1)], 0, expected_text):
        fail(f'CvGame::Read appended the wrong turn-{turn} localized reload record: {appended["text"]!r}')
    return {'turn': turn, 'changed_sections': [[3, 0]], 'non_game_sections_exact': 132,
            'rng_and_replay_version_prefix_exact': True, 'replay_version': REPLAY_MESSAGE_VERSION,
            'replay_count_before': old_count, 'replay_count_after': new_count,
            'existing_replay_records_byte_exact': old_count,
            'appended_reload_record': {'turn': appended['turn'], 'type': appended['type'],
                                       'plots': [list(plot) for plot in appended['plots']],
                                       'player': appended['player'], 'text': appended['text'],
                                       'localization_template': template},
            'sessions_before': old_sessions, 'sessions_after': new_sessions,
            'bytes_after_session_counter_exact': True, 'random_seed_default_disabled': True}


def verify_host_provenance(request: dict) -> dict:
    build = read_artifact(request['candidate_build']); check_artifacts(build)
    city = read_artifact(request['city_site_sdk_build']); check_artifacts(city)
    explore = read_artifact(request['explore_sdk_build']); check_artifacts(explore)
    shared = read_artifact(request['shared_lua_build']); check_artifacts(shared)
    bundle_row = request['accepted_bundle']
    bundle_path = Path(bundle_row['path'])
    if not bundle_path.is_file() or digest(bundle_path) != bundle_row['sha256']:
        fail('Accepted runtime bundle record changed after the actual run')
    bundle = json.loads(bundle_path.read_text(encoding='utf-8'))
    # The bundle record pins its builder hash, but the builder itself was subsequently
    # edited. Verify the immutable record and all of its other inputs independently.
    builder = bundle.get('builder')
    if not isinstance(builder, dict) or not isinstance(builder.get('path'), str) or not re.fullmatch(r'[0-9a-f]{64}', builder.get('sha256', '')):
        fail('Accepted bundle lacks its builder-source provenance record')
    if builder['sha256'] != BUNDLE_BUILDER_SHA256 or not BUNDLED_HOST_BUILDER.is_file() or \
       digest(BUNDLED_HOST_BUILDER) != builder['sha256']:
        fail('Accepted bundle does not match the independently retained pre-run builder copy')
    builder_path = Path(builder['path'])
    builder_current_hash = digest(builder_path) if builder_path.is_file() else None
    bundle_inputs = dict(bundle)
    bundle_inputs.pop('builder', None)
    check_artifacts(bundle_inputs)
    if city.get('status') != 'CITY_SITE_SDK_CANDIDATE_LINKED' or explore.get('status') != 'EXPLORE_SDK_CANDIDATE_LINKED':
        fail('Runtime build provenance lacks the exact linked city-site and exploration SDK candidates')
    verify_city_site_base(city, explore)
    if not all(name in build for name in ('executable', 'compiler', 'response', 'map', 'dependency_report',
                                          'compiler_inputs', 'sources', 'log', 'libraries')):
        fail('Frozen host candidate build/compiler provenance is incomplete')
    if not build['compiler_inputs'] or not build['sources']:
        fail('Host build does not retain actual compiler input and source closure')
    sources = {Path(row.get('path', '')).name: row for row in build['sources']}
    required = {'HostMain.cpp', 'HostRun.h', 'HostServices.h', 'LocalGameCommands.h',
                'LocalSdkSession.h', 'FoundCityProbe.h', 'CityDecisionProbe.h'}
    if not required <= sources.keys():
        fail('Host candidate does not retain all three-session decision route sources')
    source_text = {name: Path(sources[name]['path']).read_text(encoding='utf-8')
                   for name in required}
    main, run, services = source_text['HostMain.cpp'], source_text['HostRun.h'], source_text['HostServices.h']
    command, session, founding, probe = (source_text['LocalGameCommands.h'], source_text['LocalSdkSession.h'],
                                         source_text['FoundCityProbe.h'], source_text['CityDecisionProbe.h'])
    required_probe = (
        'Game.CityPushOrder(city,OrderTypes.ORDER_TRAIN,unit,false,true,true)',
        'Network.SendResearch(tech,0,-1,false)', 'if city:CanTrain(info.ID) then',
        'if player:CanResearch(info.ID) then', 'table.sort(units)', 'table.sort(techs)',
        'assert(city:GetProductionUnit()==unit and city:GetOrderQueueLength()==1',
        'assert(player:GetCurrentResearch()==tech', 'Game.GetGameTurn(),Game.GetElapsedGameTurns()',
        'CITY_DECISION_AFTER_NOTIFICATION_UPDATE', 'SDK_UPDATE_WITHOUT_TURN_ADVANCE',
        'FirstTurnProbe::AdvanceOneTurn', 'ResponseCityPushOrder', 'ResponseResearch',
    )
    if any(token not in probe for token in required_probe[:10]):
        fail('Frozen CityDecisionProbe does not prove the requested original Lua input/choice/postcondition path')
    if 'SDK_UPDATE_WITHOUT_TURN_ADVANCE' not in probe or 'if(afterNotifications!=result.before)' not in probe:
        fail('Notification-expiry SDK update does not preserve the exact pre-input decision state')
    if 'ResponseCityPushOrder' not in session or 'ResponseResearch(active,tech,discover,shift);' not in session:
        fail('Local SDK session does not forward city production/research to the original receiver')
    if 'game.IsGameMultiPlayer()' not in session or \
       'order!=ORDER_TRAIN || alt || !shift || !control' not in session or \
       'discover!=0 || stealFrom!=NO_PLAYER || shift' not in session or \
       'ResponseCityPushOrder(active,cityID,order,data,alt,shift,control);' not in session:
        fail('Local SDK session does not enforce the exact single-player production/research tuple')
    if 'void sendPushOrder(' not in services or 'void sendResearch(' not in services or \
       'state_->localCommands.SendPushOrder' not in services or 'state_->localCommands.SendResearch' not in services:
        fail('EngineServices does not forward both command APIs through LocalGameCommands')
    if 'bool policyNotificationSeen=false;' not in services or 'state_->policyNotificationSeen=false;' not in services or \
       'IsPolicyNotificationSeen() const override {RequireUiOwner();return state_->policyNotificationSeen;}' not in services or \
       'SetPolicyNotificationSeen(bool value) override' not in services:
        fail('Owned policy-notification state does not have the explicit initialized/reset/owner-guarded adapter path')
    policy_setter = services[services.index('SetPolicyNotificationSeen(bool value) override'):]
    policy_setter = policy_setter[:policy_setter.index('\n    }')+6]
    if 'RequireUiOwner();' not in policy_setter or 'state_->policyNotificationSeen=value;' not in policy_setter:
        fail('Policy-notification setter is not owner-thread guarded')
    if 'orderHandler(command.unitID,command.order,command.data1,command.alt,command.shift,command.control)' not in command or \
       'researchHandler(command.tech,command.data1,command.stealFrom,command.shift)' not in command:
        fail('LocalGameCommands does not retain exact decision tuples through ordered dispatch')
    if '--check-city-decisions' not in main or 'RestoreCityDecisionCheckpoint' not in run or \
       'state-after-found-city-restore.zssave' not in run or 'state-after-city-decision-restore.zssave' not in run:
        fail('Host mode or fresh-session checkpoint routes differ')
    if any(token in probe for token in ('SetProduction(', 'SetResearchProgress(', 'SetCurrentResearch(',
                                        'SetOrderQueueLength(')):
        fail('CityDecisionProbe contains a direct gameplay-state mutation bypass')
    if city.get('gamecore', {}).get('sha256') != request.get('gamecore', {}).get('sha256'):
        fail('Runtime selected a GameCore different from the linked city-site candidate')
    inputs = {Path(row['path']).name: row for row in request.get('inputs', [])}
    expected_inputs = {'ZeroSisHost_x64.exe', 'CvGameCoreDLL_Expansion2_x64.dll', 'ZeroSisDatabase_x64.dll',
                       'ZeroSisLocalization_x64.dll', 'ZeroSisLua51_x64.dll', 'rules.db', 'localization.db',
                       'bundle.manifest'}
    if not expected_inputs <= inputs.keys() or len(inputs) != len(request.get('inputs', [])):
        fail('Runtime input bundle is incomplete or has duplicate names')
    if inputs['ZeroSisHost_x64.exe']['sha256'] != build['executable']['sha256'] or \
       inputs['CvGameCoreDLL_Expansion2_x64.dll']['sha256'] != city['gamecore']['sha256'] or \
       inputs['ZeroSisLua51_x64.dll']['sha256'] != shared['lua_dll']['sha256']:
        fail('Actual runtime input hashes do not match the retained host/SDK/Lua build reports')
    for item in request['inputs']:
        check_artifacts(item)
    manifest = Path(inputs['bundle.manifest']['path']).read_bytes()
    if manifest.count(('CvGameCoreDLL_Expansion2_x64.dll|' + city['gamecore']['sha256']).encode('ascii')) != 1:
        fail('Runtime bundle manifest does not identify the linked SDK DLL')
    return {'candidate_build': request['candidate_build'], 'city_site_sdk_build': request['city_site_sdk_build'],
            'explore_sdk_build': request['explore_sdk_build'], 'shared_lua_build': request['shared_lua_build'],
            'accepted_bundle': request['accepted_bundle'], 'accepted_bundle_builder': {
                'recorded_sha256': builder['sha256'], 'current_sha256': builder_current_hash,
                'current_source_matches_bundle': builder_current_hash == builder['sha256'],
                'frozen_pre_run_copy': artifact(BUNDLED_HOST_BUILDER),
                'frozen_copy_matches_bundle': digest(BUNDLED_HOST_BUILDER) == builder['sha256']},
            'executable': build['executable'], 'gamecore': request['gamecore'],
            'host_source_artifacts': {name: sources[name] for name in sorted(required)},
            'host_compiler': build['compiler'], 'host_compiler_inputs': len(build['compiler_inputs']),
            'runtime_input_hashes': {name: inputs[name]['sha256'] for name in sorted(inputs)}}


def result_false(value) -> bool:
    return value is not False


def verify_run(run_id: str) -> dict:
    if not re.fullmatch(r'\d{8}T\d{6}Z_[0-9a-f]{12}', run_id):
        fail('Run ID does not match the city-decision runtime identity format')
    directory = ROOT / run_id
    result_path = directory / 'result.json'
    result = json.loads(result_path.read_text(encoding='utf-8'))
    check_artifacts(result)
    request = read_artifact(result['request']); check_artifacts(request)
    language = request.get('language')
    if request.get('run_id') != run_id or language not in LANGUAGES or \
       result.get('status') != 'ISOLATED_SDK_CITY_DECISIONS_TURN_AND_NATIVE_RESTORE_PASS':
        fail(f'City-decision runtime is not a successful EN/KO SDK run: {run_id}')
    if result.get('exit_code') != 0 or result.get('timed_out') is not False or result.get('host_failures') != []:
        fail('City-decision runtime has a nonzero exit, timeout or host failure')
    if request.get('fixture_input') != 'ORIGINAL_STARTING_SETTLER_SDK_MISSION_FOUND' or \
       request.get('city_decisions_enabled') is not True or request.get('city_site_sdk_enabled') is not True or \
       request.get('turn_advancement_requested') is not True or request.get('decision_selection_requested') is not True or \
       request.get('accepted_stage_promotion_requested') is not False or result.get('accepted_stage_promoted') is not False:
        fail('Runtime request is not the explicit founder + city-decision profile or promoted a stage')
    if request.get('environment_overrides') != {'ZEROSIS_EXPLORE_WORKERS': '0', 'ZEROSIS_CITY_SITE_WORKERS': '0'} or \
       request.get('inherited_cpu_trace_environment_removed') is not True:
        fail('Runtime did not use the declared deterministic single-worker environment')
    command = request.get('command')
    if not isinstance(command, list) or len(command) != 3 or command[1:] != ['--check-city-decisions', language]:
        fail('Runner did not execute the explicit city-decision host mode')
    runtime = Path(request['cwd']).resolve()
    if runtime != (PROJECT / 'Build/CityDecisionRuntime' / run_id).resolve():
        fail('City-decision runtime directory does not match the run identity')
    output = Path(result['stdout']['path']).read_text(encoding='utf-8').replace('\r\n', '\n').replace('\r', '\n')
    if Path(result['stderr']['path']).read_text(encoding='utf-8').strip():
        fail('Successful runtime emitted unexpected stderr')
    if result.get('runtime_inputs_unchanged') is not True or result.get('accepted_bundle_files_unchanged') is not True:
        fail('Runtime changed one of its immutable inputs or accepted bundle files')
    if result.get('gamecore_loaded') is not True or result.get('turn_advance_verified') is not True or \
       any(result.get(flag) is not False for flag in ('decision_ui_verified', 'renderer_verified',
                                                       'interactive_input_verified', 'retail_save_compatibility_verified')):
        fail('Result overstates runtime scope or does not establish actual GameCore turn advancement')

    exact_markers = (
        'FOUND_CITY_INPUT_ROUTE=SDK_GAME_HANDLE_ACTION', 'FOUND_CITY_NO_DECISION_SELECTED=true',
        'FOUND_CITY_RESTORE_FRESH_SESSION=true', 'FOUND_CITY_RESTORE_STATE_EQUAL=true',
        'FOUND_CITY_RESTORE_IDLE_STATE_EQUAL=true', 'FOUND_CITY_RESTORE_IDLE_UPDATES=3',
        'CITY_DECISION_NOTIFICATION_UPDATE=SDK_UPDATE_WITHOUT_TURN_ADVANCE',
        'CITY_DECISION_RESTORE_FRESH_SESSION=true', 'CITY_DECISION_RESTORE_STATE_EQUAL=true',
        'CITY_DECISION_RESTORE_IDLE_STATE_EQUAL=true', 'CITY_DECISION_RESTORE_IDLE_UPDATES=3',
        'CITY_DECISION_INPUT_ROUTE=SDK_CITY_PUSH_ORDER_AND_ENGINE_NETWORK_SEND_RESEARCH',
        'CITY_DECISION_RESTORED_CORE_MODULE_UNLOADED=true',
        'CITY_DECISION_SHUTDOWN_PASS GAMECORE_LOADED=true CITY_DECISIONS_ACCEPTED=true TURN_ADVANCE_VERIFIED=true CITY_DECISION_RESTORE_VERIFIED=true',
    )
    for marker in exact_markers:
        if output.splitlines().count(marker) != 1:
            fail('Successful runtime lacks one unique required marker: ' + marker)
    if re.findall(r'^SESSION_ACTIVE_MODS=(\d+)$', output, re.M) != ['0', '0', '0']:
        fail('Three fresh sessions did not each declare the empty active-mod profile')

    before = int_row(one(output, 'CITY_DECISION_BEFORE_TURN'), 12, 'pre-decision observation')
    after_notification = int_row(one(output, 'CITY_DECISION_AFTER_NOTIFICATION_UPDATE'), 12,
                                 'post-notification SDK-update observation')
    after = int_row(one(output, 'CITY_DECISION_AFTER_TURN'), 12, 'post-normal-turn observation')
    restored = [int_row(value, 12, 'fresh-restored decision observation') for value in lines(output, 'CITY_DECISION_RESTORED')]
    if len(restored) != 4 or before != after_notification or restored != [after] * 4:
        fail('Pre-input SDK notification update changed state, or fresh restore/idle observations differ')
    for result_key, output_key in (('city_decision_before_turn_logs', 'CITY_DECISION_BEFORE_TURN'),
                                   ('city_decision_after_turn_logs', 'CITY_DECISION_AFTER_TURN'),
                                   ('city_decision_restored_logs', 'CITY_DECISION_RESTORED')):
        if result.get(result_key) != lines(output, output_key):
            fail(f'Runner result did not retain exact stdout observation rows: {result_key}')
    if before[:3] != [0, 0, 0] or before[3] < 0 or before[4] < 0 or before[5] < 0 or \
       before[6] != 1 or before[7] != 0 or before[8] <= 0 or before[9] != 0 or before[10] <= 0 or before[11] < 1:
        fail('Pre-decision actual SDK observation is not the turn-zero empty production/research choice')
    if after[:3] != [1, 1, 0] or after[3:7] != before[3:7] or after[8] != before[8] or \
       after[7] <= before[7] or after[9] <= before[9] or after[10] <= 0 or after[10] >= before[10] or after[11] != before[11]:
        fail('Normal SDK turn did not advance only production/research while retaining the selected choices')
    action = int_row(one(output, 'FOUND_CITY_ACTION'), 9, 'SDK founding action')
    founding = int_row(one(output, 'FOUND_CITY_OBSERVATION'), 13, 'SDK founding observation')
    if action[0] != 0 or action[1] != 0 or action[3] < 0 or action[4] < 0 or action[5] < 0 or \
       action[6] < 0 or action[7:] != [0, 2] or founding[0] != 0 or founding[1] != action[1] or \
       founding[2] != action[2] or founding[4:6] != action[5:7] or founding[7:10] != [0, 1, 2] or \
       founding[10] != 1 or not 1 <= founding[11] <= 256 or founding[12] != action[4] or founding[6] < 1 or after[3] != founding[3]:
        fail('Actual original settler action and city observation identities differ')
    mission_id = _mission_id(Path({Path(row['path']).name: row for row in request['inputs']}['rules.db']['path']))
    if action[3] != mission_id:
        fail('Founding action did not use the actual rules DB MISSION_FOUND ID')

    # The actual turn cycle reports the standard end-turn input and one local completion boundary.
    for key, expected in (
        ('CITY_DECISION_TURN_CYCLE_PLAYER_OPTION', 'PLAYEROPTION_WAIT_END_TURN:1'),
        ('CITY_DECISION_TURN_CYCLE_INPUT', 'MISSION_SKIP_EACH_UNIT_THEN_CONTROL_ENDTURN'),
    ):
        if one(output, key) != expected:
            fail('Normal turn did not use the exact local completion route: ' + key)
    turn_cycle = int_row(one(output, 'CITY_DECISION_TURN_CYCLE_OBSERVATION'), 8, 'normal-turn observation')
    if turn_cycle[:6] != [0, 1, 1, 0, 1, 1] or turn_cycle[6] < 1 or turn_cycle[7] != 3:
        fail('Actual SDK local completion did not return one active human at turn one')
    event_rows = {}
    for raw in lines(output, 'TURN_CYCLE_EVENT'):
        match = re.fullmatch(r'(\d+)\|(.*)', raw)
        if not match: fail('Malformed local completion event record')
        event_rows[match.group(2)] = int(match.group(1))
    for event in ('ui-active-player-turn-end', 'ui-active-player-turn-start', 'new-game-turn:1', 'local-turn-boundary:0'):
        if event_rows.get(event) != 1:
            fail('Actual local completion boundary event count differs: ' + event)

    session_text = [('SESSION_DIRECTORY', 'initial'), ('FOUND_CITY_RESTORE_SESSION_DIRECTORY', 'found_restore'),
                    ('CITY_DECISION_RESTORE_SESSION_DIRECTORY', 'decision_restore')]
    session_dirs = {}
    for marker, label in session_text:
        path = Path(one(output, marker)).resolve()
        if not path.is_relative_to(runtime / 'sessions'):
            fail(f'{label} SDK session escaped the private runtime directory')
        session_dirs[label] = path
    if len(set(session_dirs.values())) != 3:
        fail('Initial, founded-city restore and city-decision restore did not use three distinct sessions')
    generated = result.get('generated_files', [])
    for item in generated: check_artifacts(item)
    # The final per-session SDK database/rules copies are independently retained and must be identical.
    dbs, rules_dbs = [], []
    for label, session_dir in session_dirs.items():
        dbs.append(recorded(result, session_dir / 'Civ5SavedGameDatabase.db', runtime))
        rules_dbs.append(recorded(result, session_dir / 'rules.db', runtime))
    if len({digest(path) for path in dbs}) != 1 or len({digest(path) for path in rules_dbs}) != 1:
        fail('The three fresh sessions did not preserve their exact private SDK database/rules inputs')
    inputs = {Path(row['path']).name: row for row in request['inputs']}
    settler_type = _unit_id(rules_dbs[0], 'UNIT_SETTLER')
    founder = verify_founder_snapshot(
        recorded(result, session_dirs['initial'] / 'state-after-founded-city.txt', runtime).read_bytes(),
        founding, settler_type)
    initial_saved_state = recorded(result, session_dirs['initial'] / 'state-before-save.txt', runtime).read_bytes()
    if initial_saved_state != recorded(result, session_dirs['initial'] / 'state-after-founded-city.txt', runtime).read_bytes():
        fail('Initial SDK founding state changed before the turn-zero checkpoint')
    founded_restore = recorded(result, session_dirs['found_restore'] / 'state-after-found-city-restore.txt', runtime).read_bytes()
    founded_idle = recorded(result, session_dirs['found_restore'] / 'state-after-found-city-idle.txt', runtime).read_bytes()
    if founded_restore != initial_saved_state or founded_idle != initial_saved_state:
        fail('Fresh turn-zero city restore or its three idle updates changed semantic state')
    after_turn = recorded(result, session_dirs['found_restore'] / 'state-after-city-decision-turn.txt', runtime).read_bytes()
    after_turn_before_save = recorded(result, session_dirs['found_restore'] / 'state-before-save.txt', runtime).read_bytes()
    if after_turn != after_turn_before_save:
        fail('Decision-turn SDK snapshot changed between turn completion and checkpoint save')
    restored_turn = recorded(result, session_dirs['decision_restore'] / 'state-after-city-decision-restore.txt', runtime).read_bytes()
    idle_turn = recorded(result, session_dirs['decision_restore'] / 'state-after-city-decision-idle.txt', runtime).read_bytes()
    if restored_turn != after_turn or idle_turn != after_turn:
        fail('Fresh turn-one restore or its three idle updates changed semantic state')
    snap0 = inspect_state_snapshot(session_dirs['initial'] / 'state-before-save.txt', 0)[0]
    snapf = inspect_state_snapshot(session_dirs['found_restore'] / 'state-after-found-city-restore.txt', 0)[0]
    snapa = inspect_state_snapshot(session_dirs['found_restore'] / 'state-after-city-decision-turn.txt', 1)[0]
    snapr = inspect_state_snapshot(session_dirs['decision_restore'] / 'state-after-city-decision-restore.txt', 1)[0]
    semantic_after = _decision_snapshot_semantics(after_turn, before, after)
    semantic_restored = _decision_snapshot_semantics(restored_turn, before, after)
    if semantic_after != semantic_restored:
        fail('Turn-one SDK semantic decision objects differ after fresh restore')

    # Native saves: initial autosave, turn-zero founding checkpoint, its restore,
    # turn-one decision checkpoint, and the third-session restore checkpoint.
    autosave = recorded(result, session_dirs['initial'] / 'autosave-0-turn-0.zssave', runtime)
    checkpoints = [Path(value).resolve() for value in lines(output, 'NATIVE_CHECKPOINT_WRITTEN')]
    if len(checkpoints) != 2 or checkpoints[0] != (session_dirs['initial'] / 'checkpoint-turn-0.zssave').resolve() or \
       checkpoints[1] != (session_dirs['found_restore'] / 'checkpoint-turn-1.zssave').resolve():
        fail('The two actual checkpoint files do not match the distinct SDK sessions/turns')
    for path in checkpoints: recorded(result, path, runtime)
    restore0 = recorded(result, session_dirs['found_restore'] / 'state-after-found-city-restore.zssave', runtime)
    restore1 = recorded(result, session_dirs['decision_restore'] / 'state-after-city-decision-restore.zssave', runtime)
    manifest = Path(inputs['bundle.manifest']['path'])
    archive_expected = (1, 1, 0, 0, 0, 64, 64, 133)
    save_rows = {
        'initial_autosave': inspect_save(autosave, manifest, dbs[0], expected=archive_expected),
        'founded_checkpoint': inspect_save(checkpoints[0], manifest, dbs[0], expected=(1, 0, 0, 0, 0, 64, 64, 133)),
        'founded_restore': inspect_save(restore0, manifest, dbs[1], expected=(1, 0, 0, 0, 0, 64, 64, 133)),
        'decision_checkpoint': inspect_save(checkpoints[1], manifest, dbs[1], expected=(1, 0, 1, 1, 0, 64, 64, 133)),
        'decision_restore': inspect_save(restore1, manifest, dbs[2], expected=(1, 0, 1, 1, 0, 64, 64, 133)),
    }
    checkpoint_observations = [int_row(value, 5, 'native checkpoint observation')
                               for value in lines(output, 'NATIVE_CHECKPOINT_OBSERVATION')]
    if len(checkpoint_observations) != 2 or [row[:4] for row in checkpoint_observations] != [[0, 0, 0, 133], [1, 1, 0, 133]] or \
       checkpoint_observations[0][4] != save_rows['founded_checkpoint']['bytes'] or \
       checkpoint_observations[1][4] != save_rows['decision_checkpoint']['bytes']:
        fail('Native checkpoint stdout does not match its actual persisted turn/section/size metadata')
    bundle_hashes = [comparable_save(save_rows[key]) for key in ('initial_autosave', 'founded_checkpoint', 'founded_restore',
                                                                  'decision_checkpoint', 'decision_restore')]
    restore_metadata = [
        verify_game_restore(checkpoints[0], restore0, rules=rules_dbs[0], localization=Path(inputs['localization.db']['path']),
                            language=language, turn=0),
        verify_game_restore(checkpoints[1], restore1, rules=rules_dbs[1], localization=Path(inputs['localization.db']['path']),
                            language=language, turn=1),
    ]
    if bundle_hashes[1]['map_guid'] != bundle_hashes[2]['map_guid'] or \
       bundle_hashes[3]['map_guid'] != bundle_hashes[4]['map_guid']:
        fail('CvMap GUID changed across one of the two fresh-session restore pairs')
    if lines(output, 'FOUND_CITY_RESTORE_SECTION_CHANGED') != ['3,0'] or \
       one(output, 'FOUND_CITY_RESTORE_SECTIONS_EQUAL') != '132,133' or \
       lines(output, 'CITY_DECISION_RESTORE_SECTION_CHANGED') != ['3,0'] or \
       one(output, 'CITY_DECISION_RESTORE_SECTIONS_EQUAL') != '132,133':
        fail('One of the two SDK restore pairs did not preserve all 132 non-Game sections exactly')

    host_provenance = verify_host_provenance(request)
    # Cross-language equivalence is semantic only; independent archives retain independent CvMap GUIDs.
    return {'run_id': run_id, 'language': language, 'request': result['request'], 'result': artifact(result_path),
            'stdout': result['stdout'], 'stderr': result['stderr'], 'host_provenance': host_provenance,
            'mission_found_action': action, 'founding_observation': founding, 'founder_semantics': founder,
            'decision_before': before, 'decision_after_notification_update': after_notification,
            'decision_after_turn': after, 'decision_restored_observations': restored,
            'decision_semantics_after_turn': semantic_after,
            'snapshot_sha256': {'founder': digest(session_dirs['initial'] / 'state-after-founded-city.txt'),
                                'decision_turn': digest(session_dirs['found_restore'] / 'state-after-city-decision-turn.txt'),
                                'decision_restore': digest(session_dirs['decision_restore'] / 'state-after-city-decision-restore.txt')},
            'snapshots': {'founding': snap0, 'founded_restore': snapf, 'decision_turn': snapa, 'decision_restore': snapr},
            'sessions': {key: str(path) for key, path in session_dirs.items()},
            'active_mods': [0, 0, 0], 'normal_local_turn': {'turn_observation': turn_cycle, 'completion_events': {
                key: event_rows[key] for key in ('ui-active-player-turn-end', 'ui-active-player-turn-start',
                                                 'new-game-turn:1', 'local-turn-boundary:0')}},
            'archives': save_rows, 'map_guids': [row['map_guid'] for row in bundle_hashes],
            'game_restore_metadata': restore_metadata, 'non_game_sections_exact_per_restore': 132,
            'notification_update_without_turn_advance': True,
            'city_train_route': 'Game.CityPushOrder -> EngineServices.sendPushOrder -> ICvNetMessageHandler1.ResponseCityPushOrder',
            'research_route': 'Network.SendResearch -> EngineServices.sendResearch -> ICvNetMessageHandler1.ResponseResearch',
            'decision_ui_verified': False, 'renderer_verified': False, 'retail_save_compatibility_verified': False}


def _mission_id(database: Path) -> int:
    with sqlite3.connect(database.resolve().as_uri() + '?mode=ro', uri=True) as connection:
        rows = connection.execute('SELECT "ID","Type" FROM "Missions" WHERE "Type"=?', ('MISSION_FOUND',)).fetchall()
    if len(rows) != 1 or rows[0][1] != 'MISSION_FOUND' or type(rows[0][0]) is not int or rows[0][0] < 0:
        fail('Rules DB does not define exactly one valid MISSION_FOUND ID')
    return rows[0][0]


def _unit_id(database: Path, type_name: str) -> int:
    with sqlite3.connect(database.resolve().as_uri() + '?mode=ro', uri=True) as connection:
        rows = connection.execute('SELECT "ID" FROM "Units" WHERE "Type"=?', (type_name,)).fetchall()
    if len(rows) != 1 or type(rows[0][0]) is not int or rows[0][0] < 0:
        fail(f'Rules DB does not define exactly one {type_name} ID')
    return rows[0][0]


def _decision_snapshot_semantics(data: bytes, before: list[int], after: list[int]) -> dict:
    groups = snapshot_groups(data)
    g = [int(value) for value in groups['G'][0]]
    players = {int(row[0]): [int(value) for value in row] for row in groups['P']}
    player = players.get(0)
    cities = [[int(value) for value in row[:-1]] for row in groups['C']]
    city = [row for row in cities if row[0] == 0 and row[1] == before[3]]
    if g[:3] != [1, 1, 0] or not player or player[1:4] != [1, 1, 1] or player[9] != before[5] or \
       len(city) != 1 or city[0][7] != before[4] or city[0][6] <= 0:
        fail('Turn-one semantic snapshot does not retain selected human city production/research')
    techs = [[int(value) for value in row] for row in groups['T']]
    # Research remains in progress: selected technology is not yet completed.
    selected_flags = [row[2] for row in techs if row[0] == player[4] and row[1] == before[5]]
    if selected_flags != [0]:
        fail('Selected technology completed or lacks its exact active-team snapshot record')
    return {'game': g[:3], 'human': player[:10], 'city': city[0][:11],
            'active_team_selected_tech_flags': selected_flags,
            'observed_production_stored': after[7], 'observed_research_progress': after[9]}


def compare_pair(rows: list[dict]) -> dict:
    if len(rows) != 2 or {row['language'] for row in rows} != LANGUAGES:
        fail('Pass exactly one successful en_US and one successful ko_KR city-decision run')
    en = next(row for row in rows if row['language'] == 'en_US')
    ko = next(row for row in rows if row['language'] == 'ko_KR')
    semantic_keys = ('mission_found_action', 'founding_observation', 'founder_semantics', 'decision_before',
                     'decision_after_notification_update', 'decision_after_turn', 'decision_restored_observations',
                     'decision_semantics_after_turn', 'active_mods', 'normal_local_turn')
    for key in semantic_keys:
        if en[key] != ko[key]:
            fail(f'EN/KO actual SDK semantic decision results differ: {key}')
    for field in ('executable', 'gamecore', 'runtime_input_hashes', 'host_source_artifacts'):
        if en['host_provenance'][field] != ko['host_provenance'][field]:
            fail(f'EN/KO did not use the same immutable candidate/SDK inputs: {field}')
    return {'status': 'ISOLATED_SDK_CITY_DECISIONS_TURN_AND_NATIVE_RESTORE_PAIR_PASS',
            'scope': 'ACTUAL_SDK_FOUND_CITY_PLUS_ORDER_TRAIN_AND_RESEARCH_TURN_WITH_THREE_PRIVATE_SESSIONS_EN_KO',
            'runs': rows, 'language_pair': ['en_US', 'ko_KR'], 'same_host_and_gamecore_candidate': True,
            'same_runtime_inputs': True, 'semantic_en_ko_results_exact': True,
            'raw_cross_language_native_archive_bytes_compared': False,
            'archive_contract_per_restore': '132_NON_GAME_SECTIONS_BYTE_EXACT; DYNAMIC_CVGAME_REPLAY_AND_SESSION_APPEND; WITHIN_RUN_CVMAP_GUID_RETAINED',
            'three_sessions_each_run': True, 'explicit_empty_mods_each_session': True,
            'founder_destroyed_after_real_sdk_found_action': True,
            'legal_city_train_and_research_accepted_by_sdk': True,
            'sdk_notification_update_without_turn_advance_state_exact': True,
            'normal_sdk_turn_advanced_production_and_research': True,
            'fresh_turn_zero_and_turn_one_restore_verified': True,
            'ui_click_verified': False, 'renderer_verified': False,
            'retail_save_compatibility_verified': False, 'accepted_stage_promoted': False}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='append', required=True, help='Successful city-decision runtime run ID (one per language)')
    args = parser.parse_args()
    if len(args.run) != 2 or len(set(args.run)) != 2:
        parser.error('Provide exactly two distinct successful run IDs, one EN and one KO')
    proof, validators, source_hashes, source_refs = freeze_inputs()
    rows = [verify_run(run_id) for run_id in args.run]
    report = compare_pair(rows)
    after_hashes = {path: digest(Path(path)) for path in source_hashes}
    if source_hashes != after_hashes:
        fail('A validator or original CvGame/CvMap source reference changed during inspection')
    if any(digest(Path(item['path'])) != item['sha256'] for item in validators):
        fail('A retained validator/source artifact changed before acceptance')
    report.update(validators=validators, validator_source_hashes_before=source_hashes,
                  validator_source_hashes_after=after_hashes, original_source_contracts=source_refs,
                  proof_directory=str(proof), gamecore_loaded=True, clean_shutdown_per_session=True,
                  decision_notification_update_exact_without_turn_advance=True,
                  source_freeze_verified=True)
    check_artifacts(report)
    output = proof / 'conformance.json'
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps({'status': report['status'], 'proof': artifact(output),
                      'runs': [{'run_id': row['run_id'], 'language': row['language'],
                                'decision': row['decision_after_turn']} for row in rows]}, ensure_ascii=False))


if __name__ == '__main__':
    main()
