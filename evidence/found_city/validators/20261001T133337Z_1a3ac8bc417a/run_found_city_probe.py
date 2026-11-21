"""Run the actual SDK founding action and fresh-session native city restore.

The original starting settler supplies a separate explicit input profile. This
does not choose production/research, advance a city turn or promote Stage.
"""
import argparse
import ctypes
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
import uuid

from collect_baseline import PROJECT, digest
from probe_world_builder import artifact
from run_new_game_probe import compile_candidate, verify_city_site_base
from runtime_input_cache import materialize_immutable
from verify_world_builder_map_object import check_artifacts

ROOT = PROJECT / 'evidence/found_city'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--compile', action='store_true')
    parser.add_argument('--sdk-city-sites', action='store_true')
    parser.add_argument('--language', choices=('en_US', 'ko_KR'), default='en_US')
    parser.add_argument('--timeout', type=int, default=120)
    args = parser.parse_args()
    if not 10 <= args.timeout <= 300:
        parser.error('Timeout must be between 10 and 300 seconds')
    if args.compile:
        compile_candidate(shared=True)
    build_path = PROJECT / 'evidence/new_game/candidate_build_shared.json'
    build = json.loads(build_path.read_text(encoding='utf8'))
    runtime_path = PROJECT / 'evidence/shared_lua_runtime/build_result.json'
    runtime = json.loads(runtime_path.read_text(encoding='utf8'))
    explore_path = PROJECT / 'evidence/explore_sdk/build_result.json'
    explore = json.loads(explore_path.read_text(encoding='utf8'))
    city_path = PROJECT / 'evidence/city_site_sdk/build_result.json'
    city = json.loads(city_path.read_text(encoding='utf8')) if args.sdk_city_sites else None
    bundle_path = PROJECT / 'evidence/host/bundle.json'
    bundle = json.loads(bundle_path.read_text(encoding='utf8'))
    check_artifacts(build); check_artifacts(runtime); check_artifacts(explore)
    check_artifacts(bundle['files']); check_artifacts(bundle['manifest'])
    if explore['status'] != 'EXPLORE_SDK_CANDIDATE_LINKED':
        raise RuntimeError('Founding requires the recorded linked exploration SDK baseline')
    if city:
        check_artifacts(city)
        if city['status'] != 'CITY_SITE_SDK_CANDIDATE_LINKED' or city['stage_updated'] or city['active_sdk_updated']:
            raise RuntimeError('Founding requires an isolated linked city-site SDK candidate')
        verify_city_site_base(city, explore)
    core = (city or explore)['gamecore']
    sources = {Path(row['path']).name: row for row in build['sources']}
    required = ('FoundCityProbe.h', 'HostMain.cpp', 'HostRun.h', 'HostServices.h', 'LocalSdkSession.h', 'LocalGameCommands.h')
    if not set(required) <= sources.keys():
        raise RuntimeError('The selected host lacks frozen founding sources; compile the new candidate')
    if '--check-found-city' not in Path(sources['HostMain.cpp']['path']).read_text(encoding='utf8'):
        raise RuntimeError('The selected host does not implement the explicit founding mode')
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ_') + uuid.uuid4().hex[:12]
    directory = PROJECT / 'Build/FoundCityRuntime' / run_id
    evidence = ROOT / run_id
    directory.mkdir(parents=True, exist_ok=False); evidence.mkdir(parents=True, exist_ok=False)
    rows = []; materializations = []
    for row in bundle['files']:
        name = Path(row['path']).name
        source = Path(build['executable']['path']) if name == 'ZeroSisHost_x64.exe' else Path(row['path'])
        if name == 'CvGameCoreDLL_Expansion2_x64.dll':
            source = Path(core['path'])
        target = directory / name
        if source.suffix.lower() in ('.dll', '.exe', '.bin', '.dat'):
            materializations.append(materialize_immutable(source, target, PROJECT / 'Build/RuntimeInputCache'))
        else:
            shutil.copy2(source, target)
            materializations.append({'target': str(target), 'materialization_method': 'private-copy', 'size': target.stat().st_size})
        if digest(target) != digest(source):
            raise RuntimeError('Founding runtime input materialization differs')
        rows.append({'source': str(source), **artifact(target)})
    lua_source = Path(runtime['lua_dll']['path']); lua_target = directory / lua_source.name
    materializations.append(materialize_immutable(lua_source, lua_target, PROJECT / 'Build/RuntimeInputCache'))
    rows.append({'source': str(lua_source), **artifact(lua_target)})
    manifest = directory / 'bundle.manifest'
    manifest.write_text('ZEROSIS_HOST_BUNDLE_V4\n' + ''.join(Path(row['path']).name + '|' + row['sha256'] + '\n' for row in rows), encoding='ascii')
    rows.append(artifact(manifest))
    references = {}
    for name, source in (('candidate_build', build_path), ('shared_lua_build', runtime_path), ('explore_sdk_build', explore_path),
                         ('runner', Path(__file__).resolve()), ('runtime_cache_helper', PROJECT / 'tools/runtime_input_cache.py')):
        target = evidence / (name + source.suffix)
        shutil.copy2(source, target)
        if digest(target) != digest(source):
            raise RuntimeError('Founding proof input changed while freezing it')
        references[name] = artifact(target)
    if city:
        target = evidence / 'city_site_sdk_build.json'; shutil.copy2(city_path, target)
        if digest(target) != digest(city_path):
            raise RuntimeError('City-site SDK report changed during founding setup')
        references['city_site_sdk_build'] = artifact(target)
    environment = os.environ.copy()
    environment['ZEROSIS_EXPLORE_WORKERS'] = '0'
    environment['ZEROSIS_CITY_SITE_WORKERS'] = '0'
    command = [str(directory / 'ZeroSisHost_x64.exe'), '--check-found-city', args.language]
    request = {'run_id': run_id, 'command': command, 'cwd': str(directory), 'timeout_seconds': args.timeout,
               'language': args.language, 'inputs': rows, 'input_materializations': materializations, **references,
               'accepted_bundle': artifact(bundle_path), 'gamecore': core,
               'environment_overrides': {'ZEROSIS_EXPLORE_WORKERS': '0', 'ZEROSIS_CITY_SITE_WORKERS': '0'},
               'city_site_sdk_enabled': args.sdk_city_sites, 'fixture_input': 'ORIGINAL_STARTING_SETTLER_SDK_MISSION_FOUND',
               'turn_advancement_requested': False, 'decision_selection_requested': False,
               'accepted_stage_promotion_requested': False}
    (evidence / 'request.json').write_text(json.dumps(request, indent=2) + '\n', encoding='utf8')
    print('RUN_FOUND_CITY ' + run_id, flush=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.SetErrorMode.argtypes = [ctypes.c_uint]; kernel.SetErrorMode.restype = ctypes.c_uint
    old = kernel.SetErrorMode(0x0001 | 0x0002 | 0x8000)
    start = time.monotonic()
    try:
        process = subprocess.Popen(command, cwd=directory, env=environment, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW)
    finally:
        kernel.SetErrorMode(old)
    timed_out = False
    try:
        stdout, stderr = process.communicate(timeout=args.timeout)
    except subprocess.TimeoutExpired:
        timed_out = True; process.kill(); stdout, stderr = process.communicate()
    (evidence / 'stdout.log').write_bytes(stdout); (evidence / 'stderr.log').write_bytes(stderr)
    output = (stdout + stderr).decode('utf8', errors='replace').replace('\r\n', '\n')
    unchanged = all(digest(Path(row['path'])) == row['sha256'] for row in rows)
    accepted_unchanged = all(digest(Path(row['path'])) == row['sha256'] for row in bundle['files'])
    check_artifacts(references)
    marker = 'FOUND_CITY_SHUTDOWN_PASS GAMECORE_LOADED=true CITY_CREATED=true CITY_RESTORE_VERIFIED=true TURN_ADVANCE_VERIFIED=false'
    success = process.returncode == 0 and not timed_out and unchanged and accepted_unchanged and marker in output and \
        output.splitlines().count('FOUND_CITY_RESTORE_FRESH_SESSION=true') == 1 and \
        output.splitlines().count('FOUND_CITY_RESTORED_CORE_MODULE_UNLOADED=true') == 1 and \
        output.splitlines().count('FOUND_CITY_RESTORE_STATE_EQUAL=true') == 1 and \
        output.splitlines().count('FOUND_CITY_RESTORE_IDLE_STATE_EQUAL=true') == 1 and \
        re.findall(r'^SESSION_ACTIVE_MODS=(\d+)$', output, re.M) == ['0', '0']
    originals = {row['path'] for row in rows}
    report = {'status': 'ISOLATED_SDK_FOUND_CITY_AND_NATIVE_RESTORE_' + ('PASS' if success else 'FAILED'),
              'request': artifact(evidence / 'request.json'), 'exit_code': process.returncode,
              'exit_code_hex': f'0x{process.returncode & 0xffffffff:08X}', 'timed_out': timed_out,
              'duration_seconds': time.monotonic() - start, 'stdout': artifact(evidence / 'stdout.log'),
              'stderr': artifact(evidence / 'stderr.log'), 'host_failures': re.findall(r'^HOST_FAILURE: (.+)$', output, re.M),
              'founding_action_logs': re.findall(r'^FOUND_CITY_ACTION=(.+)$', output, re.M),
              'founding_observation_logs': re.findall(r'^FOUND_CITY_OBSERVATION=(.+)$', output, re.M),
              'restored_observation_logs': re.findall(r'^FOUND_CITY_RESTORED_OBSERVATION=(.+)$', output, re.M),
              'runtime_inputs_unchanged': unchanged, 'accepted_bundle_files_unchanged': accepted_unchanged,
              'gamecore_loaded': True, 'turn_advance_verified': False, 'decision_ui_verified': False,
              'renderer_verified': False, 'interactive_input_verified': False, 'retail_save_compatibility_verified': False,
              'accepted_stage_promoted': False,
              'generated_files': [artifact(path) for path in sorted(directory.rglob('*')) if path.is_file() and str(path) not in originals]}
    (evidence / 'result.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf8')
    ROOT.mkdir(parents=True, exist_ok=True)
    (ROOT / 'result.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf8')
    print(json.dumps({key: report[key] for key in ('status', 'exit_code_hex', 'host_failures', 'founding_observation_logs')}) , flush=True)
    return 0 if success else 1


if __name__ == '__main__':
    raise SystemExit(main())
