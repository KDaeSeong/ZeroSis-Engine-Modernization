"""Strictly verify the isolated turn-zero SDK founding and fresh-session restore pair."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sqlite3
import struct
import uuid
from datetime import datetime, timezone
from pathlib import Path

from collect_baseline import PROJECT, digest
from probe_world_builder import artifact
from verify_explore_sdk_candidate import comparable_save, MAP_SOURCE
from verify_first_turn_candidate import inspect_save, read_artifact
from verify_new_game_candidate import verify_city_site_base
from verify_restore_game_metadata import (
    _archive, _i32, _reload_text, _random_seed_option_is_disabled, _replay_message,
)
from verify_world_builder_map_object import check_artifacts


ROOT = PROJECT / 'evidence/found_city'
LANGUAGES = {'en_US', 'ko_KR'}
VALIDATORS = (
    'verify_found_city_probe.py', 'run_found_city_probe.py', 'verify_explore_sdk_candidate.py',
    'verify_native_save_restore.py', 'verify_restore_game_metadata.py',
    'verify_first_turn_candidate.py', 'verify_turn_cycle_candidate.py',
    'verify_new_game_candidate.py', 'verify_city_site_sdk_candidate.py',
    'verify_world_builder_map_object.py', 'collect_baseline.py', 'probe_world_builder.py',
    'runtime_input_cache.py',
)
EXPECTED_HEADERS = {'flags': 0, 'turn': 0, 'elapsed': 0, 'active_player': 0}


def fail(message: str) -> None:
    raise RuntimeError(message)


def one(output: str, key: str) -> str:
    values = re.findall(r'^' + re.escape(key) + r'=([^\r\n]*)$', output, re.M)
    if len(values) != 1:
        fail(f'Expected one founding observation: {key}')
    return values[0]


def lines(output: str, key: str) -> list[str]:
    return re.findall(r'^' + re.escape(key) + r'=([^\r\n]*)$', output, re.M)


def freeze_inputs() -> tuple[Path, list[dict], dict[str, str], dict]:
    sources = [PROJECT / 'tools' / name for name in VALIDATORS]
    if not MAP_SOURCE.is_file():
        fail('Original CvMap serialization reference is missing')
    sources.append(MAP_SOURCE)
    for source in sources:
        if not source.is_file():
            fail(f'Found-city validator input is missing: {source}')
    before = {str(source): digest(source) for source in sources}
    frozen = ROOT / 'validators' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ_') + uuid.uuid4().hex[:12])
    frozen.mkdir(parents=True, exist_ok=False)
    artifacts = []
    map_reference = None
    for source in sources:
        target = frozen / ('CvMap.original.cpp' if source == MAP_SOURCE else source.name)
        shutil.copy2(source, target)
        row = artifact(target)
        if row['sha256'] != before[str(source)]:
            fail(f'Frozen verifier/reference copy differs: {source}')
        artifacts.append(row)
        if source == MAP_SOURCE:
            text = source.read_text(encoding='utf-8', errors='replace')
            required = ('CoCreateGuid(&m_guid)', 'kStream << m_guid.Data1', 'kStream << m_guid.Data2',
                        'kStream << m_guid.Data3', 'kStream >> m_guid.Data1', 'kStream >> m_guid.Data2',
                        'kStream >> m_guid.Data3')
            if any(token not in text for token in required):
                fail('Original CvMap GUID construction or serialization reference differs')
            map_reference = {
                'original_path': str(source), 'artifact': row,
                'guid_creation_line': next(i for i, line in enumerate(text.splitlines(), 1) if 'CoCreateGuid(&m_guid)' in line),
                'guid_write_lines': [next(i for i, line in enumerate(text.splitlines(), 1) if token in line)
                                     for token in ('kStream << m_guid.Data1', 'kStream << m_guid.Data2',
                                                   'kStream << m_guid.Data3')],
                'guid_read_lines': [next(i for i, line in enumerate(text.splitlines(), 1) if token in line)
                                    for token in ('kStream >> m_guid.Data1', 'kStream >> m_guid.Data2',
                                                  'kStream >> m_guid.Data3')],
                'normalized_section': [4, 0], 'normalized_offset': 34, 'normalized_count': 16,
                'normalization_scope': 'independent_new_game_CvMap_m_guid_only',
            }
    return frozen, artifacts, before, map_reference


def verify_game_restore(before_path: Path, restored_path: Path, *, rules_db: Path,
                        localization_db: Path, language: str) -> dict:
    _random_seed_option_is_disabled(rules_db)
    template, expected_text = _reload_text(language, localization_db)
    before_header, before_sections = _archive(before_path)
    after_header, after_sections = _archive(restored_path)
    if before_header != EXPECTED_HEADERS or after_header != EXPECTED_HEADERS:
        fail('Found-city checkpoint or restored archive is outside the turn-zero fixture')
    changed = [identity for identity in before_sections if before_sections[identity] != after_sections[identity]]
    if changed != [(3, 0)]:
        fail(f'Found-city restore changed sections outside CvGame metadata: {changed}')
    before, after = before_sections[(3, 0)], after_sections[(3, 0)]
    first = next((i for i, (left, right) in enumerate(zip(before, after)) if left != right), None)
    if first is None or first < 4 or _i32(before, first - 4) != 2 or before[:first] != after[:first]:
        fail('First CvGame difference is not the versioned replay-message count after identical RNG bytes')
    old_count, new_count = _i32(before, first), _i32(after, first)
    if old_count != 2 or new_count != old_count + 1:
        fail('Turn-zero founding fixture replay count differs from its two-to-three-message contract')
    old_cursor = new_cursor = first + 4
    for _ in range(old_count):
        old_next, _ = _replay_message(before, old_cursor)
        new_next, _ = _replay_message(after, new_cursor)
        if before[old_cursor:old_next] != after[new_cursor:new_next]:
            fail('An existing CvReplayMessage changed during fresh-session restore')
        old_cursor, new_cursor = old_next, new_next
    new_cursor, appended = _replay_message(after, new_cursor)
    if (appended['turn'], appended['type'], appended['plots'], appended['player'], appended['text']) != \
       (0, 0, [(-1, -1)], 0, expected_text):
        fail('CvGame::Read did not append the exact turn-zero localized reload replay event')
    old_sessions, new_sessions = _i32(before, old_cursor), _i32(after, new_cursor)
    if (old_sessions, new_sessions) != (1, 2) or before[old_cursor + 4:] != after[new_cursor + 4:]:
        fail('CvGame session counter or bytes after reload metadata differ')
    return {
        'changed_sections': [[3, 0]], 'replay_count_before': old_count, 'replay_count_after': new_count,
        'existing_replay_messages_byte_identical': True, 'appended_reload_message': {
            'turn': appended['turn'], 'type': appended['type'], 'plots': [list(x) for x in appended['plots']],
            'player': appended['player'], 'text': appended['text'], 'localization_template': template,
        },
        'sessions_before': old_sessions, 'sessions_after': new_sessions,
        'game_prefix_through_rng_and_replay_version_identical': True,
        'game_suffix_after_session_counter_identical': True, 'new_random_seed_default_disabled': True,
        'scope': 'FIXED_TURN_ZERO_FOUND_CITY_EN_KO_FIXTURE_ONLY',
    }


def read_mission_id(database: Path) -> int:
    uri = database.resolve().as_uri() + '?mode=ro'
    with sqlite3.connect(uri, uri=True) as connection:
        rows = connection.execute('SELECT "ID","Type" FROM "Missions" WHERE "Type"=?',
                                  ('MISSION_FOUND',)).fetchall()
    if len(rows) != 1 or rows[0][1] != 'MISSION_FOUND' or type(rows[0][0]) is not int or rows[0][0] < 0:
        fail('Rules DB does not contain one valid MISSION_FOUND identity')
    return rows[0][0]


def verify_found_script(build: dict) -> dict:
    sources = {Path(row.get('path', '')).name: row for row in build.get('sources', [])}
    if not {'HostMain.cpp', 'FoundCityProbe.h', 'HostRun.h', 'LocalSdkSession.h', 'HostServices.h'} <= sources.keys():
        fail('Frozen host candidate lacks founding code provenance')
    for name in ('HostMain.cpp', 'FoundCityProbe.h', 'HostRun.h', 'LocalSdkSession.h', 'HostServices.h'):
        check_artifacts(sources[name])
    text = Path(sources['FoundCityProbe.h']['path']).read_text(encoding='utf8')
    main = Path(sources['HostMain.cpp']['path']).read_text(encoding='utf8')
    required = (
        'local mission=MissionTypes.MISSION_FOUND',
        "info.Type=='MISSION_FOUND' and info.MissionType==mission and info.OriginalIndex==mission",
        'info.ActionInfoIndex==index and info.MissionData==-1 and not info.ConfirmCommand',
        'Game.CanHandleAction(action,nil,false)', 'Game.HandleAction(action)',
        'Game.GetGameTurn()==0 and Game.GetElapsedGameTurns()==0',
        'player:GetNumCities()==0 and player:GetNumUnits()==2',
    )
    if any(token not in text for token in required) or '--check-found-city' not in main or \
       'receiver.ResponsePushMission(active,unitID,mission,data1,data2,flags,shift);' not in Path(sources['LocalSdkSession.h']['path']).read_text(encoding='utf8'):
        fail('Frozen founding host does not use the original SDK HandleAction/mission route')
    forbidden = ('SetNumCities(', 'SetNumUnits(', 'PushMission(', 'Game.SetGameTurn(', 'SetHasPromotion(')
    if any(token in text for token in forbidden):
        fail('FoundCityProbe contains a direct gameplay-state bypass')
    return {name: sources[name] for name in ('HostMain.cpp', 'FoundCityProbe.h', 'HostRun.h',
                                              'LocalSdkSession.h', 'HostServices.h')}


def _recorded(result: dict, path: Path, runtime_dir: Path) -> Path:
    path = path.resolve()
    if not path.is_relative_to(runtime_dir.resolve() / 'sessions'):
        fail('Found-city session artifact escaped its private runtime directory')
    rows = [item for item in result.get('generated_files', []) if Path(item.get('path', '')).resolve() == path]
    if len(rows) != 1:
        fail(f'Runtime file lacks one immutable generated-file record: {path.name}')
    check_artifacts(rows[0])
    return path


def _snapshot(path: Path) -> tuple[dict, bytes]:
    from verify_native_save_restore import inspect_snapshot
    data = path.read_bytes()
    parsed = inspect_snapshot(data, expected_turn=0, initial_fixture=False)
    return parsed, data


def verify_snapshot_city(data: bytes, observation: list[int], settler_type: int) -> dict:
    lines_ = [line.split('|') for line in data.decode('utf8').splitlines()]
    groups: dict[str, list[list[str]]] = {}
    for row in lines_:
        groups.setdefault(row[0], []).append(row[1:])
    player, unit_id, city_id, x, y, population, _, _, _, after_units, _, action_index = observation[1:]
    players = {int(row[0]): [int(v) for v in row] for row in groups['P']}
    player0 = players.get(0)
    if not player0 or player0[1:4] != [1, 1, 1] or player0[5:7] != [1, after_units] or after_units != 1:
        fail('Founded human snapshot does not contain one city and one surviving unit')
    cities = [[int(v) for v in row[:-1]] for row in groups['C']]
    city_rows = [row for row in cities if row[0] == player]
    matching = [row for row in city_rows if row[1] == city_id]
    if len(city_rows) != 1 or len(matching) != 1 or matching[0][2:5] != [x, y, population] or population < 1:
        fail('Actual founded city identity, plot or population differs from the SDK observation')
    units = [[int(v) for v in row[:-1]] for row in groups['U']]
    human_units = [row for row in units if row[0] == player]
    if len(human_units) != after_units or any(row[1] == unit_id for row in human_units) or \
       any(row[2] == settler_type for row in human_units):
        fail('The original founding settler remains or the human unit count differs')
    return {'player': player, 'city_id': city_id, 'city_coordinates': [x, y], 'population': population,
            'founder_unit_id': unit_id, 'founder_absent': True, 'settler_type_id': settler_type,
            'surviving_human_units': after_units, 'action_info_index': action_index,
            'city_rows': len(cities), 'unit_rows': len(units)}


def inspect_run(run_id: str) -> dict:
    if not re.fullmatch(r'\d{8}T\d{6}Z_[0-9a-f]{12}', run_id):
        fail('Run ID is not a unique found-city probe ID')
    directory = ROOT / run_id
    result_path = directory / 'result.json'
    result = json.loads(result_path.read_text(encoding='utf8'))
    check_artifacts(result)
    request = read_artifact(result['request']); check_artifacts(request)
    if request.get('run_id') != run_id or result.get('status') != 'ISOLATED_SDK_FOUND_CITY_AND_NATIVE_RESTORE_PASS':
        fail(f'Found-city runtime did not complete successfully: {run_id}')
    if result.get('exit_code') != 0 or result.get('timed_out') or result.get('host_failures'):
        fail('Found-city runtime reported a host failure, timeout or nonzero exit')
    if request.get('fixture_input') != 'ORIGINAL_STARTING_SETTLER_SDK_MISSION_FOUND' or \
       request.get('turn_advancement_requested') is not False or request.get('decision_selection_requested') is not False or \
       request.get('accepted_stage_promotion_requested') is not False or result.get('accepted_stage_promoted') is not False:
        fail('Found-city request contains an unsupported fixture input or promotion')
    if request.get('city_site_sdk_enabled') is not True or \
       request.get('environment_overrides') != {'ZEROSIS_EXPLORE_WORKERS': '0', 'ZEROSIS_CITY_SITE_WORKERS': '0'}:
        fail('Found-city run did not explicitly use the serial linked city-site SDK profile')
    command = request.get('command')
    if not isinstance(command, list) or len(command) != 3 or command[1:] != ['--check-found-city', request.get('language')]:
        fail('Found-city runner command differs from its explicit host mode')
    language = request.get('language')
    if language not in LANGUAGES:
        fail('Found-city run language is outside the EN/KO fixture')

    output = Path(result['stdout']['path']).read_text(encoding='utf8').replace('\r\n', '\n').replace('\r', '\n')
    if Path(result['stderr']['path']).read_text(encoding='utf8').strip():
        fail('Found-city run wrote unexpected stderr')
    markers = ('FOUND_CITY_SHUTDOWN_PASS GAMECORE_LOADED=true CITY_CREATED=true CITY_RESTORE_VERIFIED=true TURN_ADVANCE_VERIFIED=false',
                'FOUND_CITY_RESTORE_FRESH_SESSION=true', 'FOUND_CITY_RESTORED_CORE_MODULE_UNLOADED=true',
                'FOUND_CITY_RESTORE_STATE_EQUAL=true', 'FOUND_CITY_RESTORE_IDLE_STATE_EQUAL=true',
                'FOUND_CITY_SELECTION_PRUNED=true', 'FOUND_CITY_INPUT_ROUTE=SDK_GAME_HANDLE_ACTION',
                'FOUND_CITY_NO_DECISION_SELECTED=true', 'FOUND_CITY_RESTORE_IDLE_UPDATES=3',
                'FOUND_CITY_CONTINUED_TURN_VERIFIED=false', 'NEW_GAME_CONFIGURATION_VERIFIED',
                'CORE_MODULE_UNLOADED=true')
    for key in markers:
        if output.splitlines().count(key) != 1:
            fail('Found-city run lacks a unique required runtime marker: ' + key)
    if re.findall(r'^SESSION_ACTIVE_MODS=(\d+)$', output, re.M) != ['0', '0']:
        fail('Fresh sessions did not use the explicit empty active-mod profile')
    if result.get('turn_advance_verified') is not False or result.get('decision_ui_verified') is not False or \
       result.get('renderer_verified') is not False or result.get('retail_save_compatibility_verified') is not False:
        fail('Found-city report overstates turn, UI, renderer or retail-save scope')

    build = read_artifact(request['candidate_build']); check_artifacts(build)
    city = read_artifact(request['city_site_sdk_build']); check_artifacts(city)
    explore = read_artifact(request['explore_sdk_build']); check_artifacts(explore)
    verify_city_site_base(city, explore)
    host_sources = verify_found_script(build)
    if city.get('status') != 'CITY_SITE_SDK_CANDIDATE_LINKED' or \
       not request.get('shared_lua_build') or not request.get('accepted_bundle'):
        fail('Found-city candidate build provenance is incomplete')
    shared = read_artifact(request['shared_lua_build']); check_artifacts(shared)
    if city.get('gamecore', {}).get('sha256') != request.get('gamecore', {}).get('sha256'):
        fail('Selected GameCore DLL differs from linked city-site candidate')
    inputs = {Path(row['path']).name: row for row in request.get('inputs', [])}
    required_inputs = {'ZeroSisHost_x64.exe', 'CvGameCoreDLL_Expansion2_x64.dll', 'rules.db',
                       'localization.db', 'bundle.manifest', 'ZeroSisLua51_x64.dll'}
    if not required_inputs <= inputs.keys() or len(inputs) != len(request['inputs']):
        fail('Found-city runtime input bundle is incomplete or duplicated')
    if inputs['ZeroSisHost_x64.exe']['sha256'] != build['executable']['sha256'] or \
       inputs['CvGameCoreDLL_Expansion2_x64.dll']['sha256'] != city['gamecore']['sha256'] or \
       inputs['ZeroSisLua51_x64.dll']['sha256'] != shared['lua_dll']['sha256']:
        fail('Found-city runtime did not load the reported candidate host, SDK or Lua runtime')
    manifest = Path(inputs['bundle.manifest']['path']).read_bytes()
    if manifest.count(('CvGameCoreDLL_Expansion2_x64.dll|' + city['gamecore']['sha256']).encode('ascii')) != 1:
        fail('Private runtime manifest does not identify the linked founding SDK DLL')
    for item in request['inputs']:
        check_artifacts(item)
    if result.get('runtime_inputs_unchanged') is not True or result.get('accepted_bundle_files_unchanged') is not True:
        fail('Found-city run changed a runtime input or accepted bundle file')

    rules = Path(inputs['rules.db']['path'])
    mission_id = read_mission_id(rules)
    action_rows = [[int(value) for value in line.split(',')] for line in lines(output, 'FOUND_CITY_ACTION')]
    if len(action_rows) != 1 or len(action_rows[0]) != 9:
        fail('Found-city run lacks one exact action record')
    action = action_rows[0]
    if action[0] != 0 or action[1] != 0 or action[3] != mission_id or \
       any(value < 0 for value in (action[2], action[4], action[5], action[6])) or \
       action[7:] != [0, 2]:
        fail('Found-city action identity differs from the original turn-zero settler fixture')
    x, y = action[5:7]
    if not (0 <= x < 40 and 0 <= y < 24):
        fail('Founding action plot is outside the 40x24 SDK map')
    session_lines = lines(output, 'SESSION_DIRECTORY')
    restore_session_lines = lines(output, 'FOUND_CITY_RESTORE_SESSION_DIRECTORY')
    if len(session_lines) != 1 or len(restore_session_lines) != 1:
        fail('Found-city runtime did not report exactly two private SDK sessions')
    runtime_dir = Path(request['cwd']).resolve()
    before_session, after_session = Path(session_lines[0]).resolve(), Path(restore_session_lines[0]).resolve()
    if before_session == after_session or any(not p.is_relative_to(runtime_dir / 'sessions') for p in (before_session, after_session)):
        fail('Found-city restore did not use a distinct private fresh session')
    generated = result.get('generated_files', [])
    for item in generated:
        check_artifacts(item)
    checkpoint_lines = lines(output, 'NATIVE_CHECKPOINT_WRITTEN')
    if len(checkpoint_lines) != 1:
        fail('Found-city run lacks one native checkpoint')
    autosave = _recorded(result, before_session / 'autosave-0-turn-0.zssave', runtime_dir)
    checkpoint = _recorded(result, Path(checkpoint_lines[0]), runtime_dir)
    restored = _recorded(result, after_session / 'state-after-found-city-restore.zssave', runtime_dir)
    before_db = _recorded(result, before_session / 'Civ5SavedGameDatabase.db', runtime_dir)
    after_db = _recorded(result, after_session / 'Civ5SavedGameDatabase.db', runtime_dir)
    before_rules = _recorded(result, before_session / 'rules.db', runtime_dir)
    after_rules = _recorded(result, after_session / 'rules.db', runtime_dir)
    if before_db.read_bytes() != after_db.read_bytes():
        fail('Fresh-session restore changed the embedded SDK game database')
    if read_mission_id(before_rules) != mission_id or read_mission_id(after_rules) != mission_id:
        fail('Fresh sessions did not retain the exact original MISSION_FOUND database identity')
    bundle_path = Path(inputs['bundle.manifest']['path'])
    initial_archive = inspect_save(autosave, bundle_path, before_db, expected=(1, 1, 0, 0, 0, 64, 64, 133))
    checkpoint_archive = inspect_save(checkpoint, bundle_path, before_db, expected=(1, 0, 0, 0, 0, 64, 64, 133))
    restored_archive = inspect_save(restored, bundle_path, after_db, expected=(1, 0, 0, 0, 0, 64, 64, 133))
    checkpoint_meta, checkpoint_sections = _archive(checkpoint)
    restored_meta, restored_sections = _archive(restored)
    changed = [f'{kind},{index}' for kind, index in checkpoint_sections
               if checkpoint_sections[(kind, index)] != restored_sections[(kind, index)]]
    if changed != ['3,0'] or lines(output, 'FOUND_CITY_RESTORE_SECTION_CHANGED') != changed or \
       one(output, 'FOUND_CITY_RESTORE_SECTIONS_EQUAL') != '132,133':
        fail('Found-city restore did not preserve exactly 132 non-Game SDK sections')
    game_restore = verify_game_restore(checkpoint, restored, rules_db=before_rules,
                                       localization_db=Path(inputs['localization.db']['path']), language=language)
    if one(output, 'NATIVE_CHECKPOINT_OBSERVATION') != f'0,0,0,133,{checkpoint_archive["bytes"]}':
        fail('Native checkpoint observation differs from the persisted archive')

    obs_rows = [[int(value) for value in line.split(',')] for line in lines(output, 'FOUND_CITY_OBSERVATION')]
    restored_rows = [[int(value) for value in line.split(',')] for line in lines(output, 'FOUND_CITY_RESTORED_OBSERVATION')]
    if len(obs_rows) != 1 or len(obs_rows[0]) != 13 or len(restored_rows) != 4 or any(len(row) != 9 for row in restored_rows):
        fail('Found-city run lacks its one 13-field observation and four restore observations')
    observation = obs_rows[0]
    if observation[0] != 0 or observation[1] != action[1] or observation[2] != action[2] or \
       observation[3] < 0 or observation[4:6] != [x, y] or \
       observation[7:10] != [0, 1, 2] or observation[10] != 1 or \
       not 1 <= observation[11] <= 256 or observation[12] != action[4] or observation[6] < 1:
        fail('Found-city observation identity, population, update count or route differs')
    city_id, population = observation[3], observation[6]
    expected_restored = [0, action[1], action[2], city_id, x, y, population, 1, observation[10]]
    if any(row != expected_restored for row in restored_rows):
        fail('Fresh restore or one of three idle updates changed the actual founded city')
    from verify_native_save_restore import inspect_snapshot
    snapshot_paths = {
        'after_found': _recorded(result, before_session / 'state-after-founded-city.txt', runtime_dir),
        'before_save': _recorded(result, before_session / 'state-before-save.txt', runtime_dir),
        'after_restore': _recorded(result, after_session / 'state-after-found-city-restore.txt', runtime_dir),
        'after_idle': _recorded(result, after_session / 'state-after-found-city-idle.txt', runtime_dir),
    }
    snapshot_rows = {}
    snapshot_bytes = {}
    for name, path in snapshot_paths.items():
        parsed, data = _snapshot(path)
        snapshot_rows[name] = parsed
        snapshot_bytes[name] = data
    if len({hashlib.sha256(value).hexdigest() for value in snapshot_bytes.values()}) != 1:
        fail('Founded city snapshot changed before save, after restore or during three idle updates')
    settler_type = None
    with sqlite3.connect(inputs['rules.db']['path']) as connection:
        rows = connection.execute('SELECT "ID" FROM "Units" WHERE "Type"=?', ('UNIT_SETTLER',)).fetchall()
    if len(rows) != 1:
        fail('Rules DB does not contain one UNIT_SETTLER identity')
    settler_type = int(rows[0][0])
    semantic = verify_snapshot_city(snapshot_bytes['before_save'], observation, settler_type)
    result_observations = result.get('founding_observation_logs')
    result_restored = result.get('restored_observation_logs')
    if result_observations != [lines(output, 'FOUND_CITY_OBSERVATION')[0]] or \
       result_restored != [','.join(map(str, row)) for row in restored_rows]:
        fail('Runner result does not preserve the exact stdout founding observations')

    archive_comparisons = {
        'checkpoint': comparable_save(checkpoint_archive),
        'restored': comparable_save(restored_archive),
        'initial_autosave': comparable_save(initial_archive),
    }
    if archive_comparisons['checkpoint']['map_guid'] != archive_comparisons['restored']['map_guid']:
        fail('Map GUID changed inside the founded-city save/restore session')
    return {
        'run_id': run_id, 'language': language, 'request': result['request'], 'result': artifact(result_path),
        'stdout': result['stdout'], 'stderr': result['stderr'], 'candidate_build': request['candidate_build'],
        'city_site_sdk_build': request['city_site_sdk_build'], 'explore_sdk_build': request['explore_sdk_build'],
        'shared_lua_build': request['shared_lua_build'],
        'candidate_build_sha256': request['candidate_build']['sha256'],
        'city_site_sdk_build_sha256': request['city_site_sdk_build']['sha256'],
        'explore_sdk_build_sha256': request['explore_sdk_build']['sha256'],
        'shared_lua_build_sha256': request['shared_lua_build']['sha256'],
        'gamecore_sha256': city['gamecore']['sha256'],
        'runtime_inputs': [{'name': name, 'sha256': row['sha256']} for name, row in sorted(inputs.items())],
        'mission_rules': {'type': 'MISSION_FOUND', 'mission_id': mission_id, 'action_info_index': action[4],
                          'action_selected_from_original_sdk_GameInfoActions': True,
                          'can_handle_action_verified': True, 'game_handle_action_verified': True},
        'founding_action': action, 'founding_observation': observation,
        'restored_observations': restored_rows, 'semantic_found_city': semantic,
        'snapshot_hashes': {name: hashlib.sha256(value).hexdigest() for name, value in snapshot_bytes.items()},
        'checkpoint': checkpoint_archive, 'restored_checkpoint': restored_archive,
        'initial_autosave': initial_archive, 'archive_comparisons': archive_comparisons,
        'byte_exact_non_game_sections': 132, 'game_reload_metadata': game_restore,
        'active_mods': [0, 0], 'idle_updates_after_restore': 3,
        'turn_advance_verified': False, 'decision_selection_verified': False,
        'renderer_verified': False, 'retail_save_compatibility_verified': False,
        'host_sources': host_sources,
    }


def compare_pair(rows: list[dict]) -> dict:
    if len(rows) != 2 or {row['language'] for row in rows} != LANGUAGES:
        fail('Provide exactly one English and one Korean founding run')
    left, right = sorted(rows, key=lambda row: row['language'])
    for key in ('candidate_build_sha256', 'city_site_sdk_build_sha256', 'explore_sdk_build_sha256',
                'shared_lua_build_sha256', 'gamecore_sha256', 'runtime_inputs', 'mission_rules',
                'founding_action', 'founding_observation',
                'semantic_found_city', 'snapshot_hashes', 'byte_exact_non_game_sections', 'active_mods',
                'idle_updates_after_restore'):
        if left[key] != right[key]:
            fail(f'EN/KO founding semantic or SDK identity differs: {key}')
    for row in rows:
        source_hashes = {name: item['sha256'] for name, item in row['host_sources'].items()}
        if source_hashes != {name: item['sha256'] for name, item in left['host_sources'].items()}:
            fail('EN/KO founding host source snapshots differ')
    for row in rows:
        report = json.loads(Path(row['candidate_build']['path']).read_text(encoding='utf8'))
        check_artifacts(report)
    normalized_sections = {}
    for field in ('checkpoint', 'restored_checkpoint', 'initial_autosave'):
        # Separate EN/KO sessions intentionally have independent map GUIDs and
        # localized CvGame replay text. Compare only within each run's restore
        # pair; never assert raw archive equality across languages.
        normalized_sections[field] = [row['archive_comparisons'][field]['sections'] for row in rows]
    if left['game_reload_metadata']['replay_count_before'] != right['game_reload_metadata']['replay_count_before'] or \
       left['game_reload_metadata']['sessions_before'] != right['game_reload_metadata']['sessions_before'] or \
       left['game_reload_metadata']['sessions_after'] != right['game_reload_metadata']['sessions_after']:
        fail('EN/KO CvGame reload metadata counts differ')
    return {
        'status': 'ISOLATED_SDK_FOUND_CITY_AND_NATIVE_RESTORE_PAIR_PASS',
        'scope': 'ACTUAL_X64_ORIGINAL_MISSION_FOUND_ACTION_TURN_ZERO_FRESH_SESSION_RESTORE_EN_KO',
        'runs': rows, 'language_pair': ['en_US', 'ko_KR'],
        'same_candidate_sdk_and_runtime_inputs': True,
        'same_semantic_found_city_snapshot': True,
        'raw_cross_language_archive_bytes_compared': False,
        'per_run_archive_contract': '132_NON_GAME_SECTIONS_EXACT; GAME_RELOAD_METADATA_PARSED; MAP_GUID_V4_RETAINS_WITHIN_RUN',
        'map_guid_source_validation': {'section': [4, 0], 'offset': 34, 'count': 16,
                                       'field': 'CvMap::m_guid', 'source': MAP_SOURCE.as_posix(),
                                       'cross_language_bytes_compared': False},
        'retail_save_compatibility_verified': False, 'turn_advance_verified': False,
        'renderer_verified': False, 'interactive_decision_verified': False,
        'accepted_stage_promoted': False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', action='append', required=True)
    args = parser.parse_args()
    if len(args.run) != 2 or len(set(args.run)) != 2:
        parser.error('Provide exactly two distinct EN and KO found-city run IDs')
    frozen_dir, frozen_validators, source_hashes, map_reference = freeze_inputs()
    rows = [inspect_run(run_id) for run_id in args.run]
    report = compare_pair(rows)
    after_hashes = {path: digest(Path(path)) for path in source_hashes}
    if source_hashes != after_hashes:
        fail('A frozen validator or map source changed during the founding inspection')
    if any(digest(Path(item['path'])) != item['sha256'] for item in frozen_validators):
        fail('A retained validator/reference copy changed before acceptance')
    report.update(validators=frozen_validators, validator_source_hashes_before=source_hashes,
                  validator_source_hashes_after=after_hashes, map_guid_source_reference=map_reference,
                  proof_directory=str(frozen_dir), gamecore_loaded=True,
                  clean_gamecore_shutdown_per_session=True, no_decision_selected=True,
                  explicit_empty_active_mods=True)
    check_artifacts(report)
    conformance = frozen_dir / 'conformance.json'
    conformance.write_text(json.dumps(report, indent=2) + '\n', encoding='utf8')
    (ROOT / 'conformance.json').write_text(json.dumps(artifact(conformance), indent=2) + '\n', encoding='utf8')
    print(json.dumps({'status': report['status'], 'proof': artifact(conformance),
                      'runs': [{'run_id': row['run_id'], 'language': row['language'],
                                'city': row['semantic_found_city']['city_id']} for row in rows]}, ensure_ascii=False))


if __name__ == '__main__':
    main()
