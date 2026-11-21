"""Prepare the current private candidate without process or retail-state access."""
from contextlib import ExitStack, redirect_stdout, redirect_stderr
from datetime import datetime, timezone
import gzip
import io
import json
import os
from pathlib import Path
import runpy
import sys
from unittest.mock import patch

PROJECT = Path(__file__).parents[3]
ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT / 'tools'))
from collect_baseline import digest
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts

BUILD_ID = '20261015T134352Z_8bd70cf290e9'
BUILD_REPORT = PROJECT / 'evidence/ui_window_host' / BUILD_ID / 'build_result.json'
RUNNER = PROJECT / 'tools/run_interactive_game.py'
UNIT_MANIFEST = PROJECT / 'Build/UnitAssets/480678966a78bedbee642040285010aa86f8a2cc34b0929c2774dcee8ab54266/unit-assets.manifest.json'


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    marker = ROOT / 'preparation_started.json'
    require(not marker.exists(), 'Inspect an existing attempt instead of preparing twice')
    require(not (ROOT / 'prepared.json').exists(), 'Preparation receipt already exists')
    require(digest(RUNNER) == 'b625fd17b3c7b1315696e7caaf63724fb6aad8dd75460921f93843a9974d4311', 'Runner changed since review')
    require(digest(BUILD_REPORT) == 'e11d807ae9bf6aa43120a6351b2d0a845ee2d671c601d76ec56a365fa58431c2', 'Host report changed')
    require(digest(UNIT_MANIFEST) == 'd6df7f9123075e7cd328712c968b1ef8023f1e32da16ced2d95651f4ffa0c3f1', 'Unit manifest changed')
    build = json.loads(BUILD_REPORT.read_text(encoding='utf8'))
    from run_interactive_game import check_host_runtime_artifacts
    validation = check_host_runtime_artifacts(build)
    cleanup = PROJECT / 'evidence/load_menu/linked_candidate/cleanup'
    plan_path = cleanup / 'current_integration_residual.plan.json.gz'
    result_path = cleanup / 'current_integration_residual.result.json'
    plan = json.loads(gzip.decompress(plan_path.read_bytes()))
    completion = json.loads(result_path.read_text(encoding='utf8'))
    for ref in (completion['plan'], plan['initial_plan'], plan['initial_partial_result']):
        check_artifacts(ref)
    require(completion['status'] == 'COMPLETE' and completion['targets_absent']
            and completion['protected_unchanged'], 'Retirement chain is incomplete')
    ledger = {row['path']: row for row in plan['files']}
    absent = validation['absent_discovery_objects']
    require(len(absent) == 5, 'Unexpected retired discovery-object set')
    for row in absent:
        require(ledger[row['original_path']]['sha256'] == row['sha256']
                and not os.path.lexists(row['original_path']), 'Retired object does not match the deletion ledger')
    for ref in (artifact(BUILD_REPORT), build['executable']):
        require(any(row['path'] == ref['path'] and row['sha256'] == ref['sha256']
                    for row in plan['protected']), 'Retirement did not protect this exact Host')
        check_artifacts(ref)
    preflight = {**validation, 'retirement_plan': artifact(plan_path),
                 'retirement_completion': artifact(result_path),
                 'retired_ledger_bytes': sum(ledger[row['original_path']]['bytes'] for row in absent),
                 'full_build_reproducibility_verified': False}
    (ROOT / 'preflight.json').write_text(json.dumps(preflight, indent=2) + '\n', encoding='utf8')
    tool_names = ('interactive_ui_driver.py', 'render_ui_popup.py', 'ui_pixel_scene.py',
                  'ui_bitmap_fonts.py', 'civ5_ui_assets.py')
    protected = [artifact(PROJECT / path) for path in (
        'Play/EarlyAccess/release.json', 'tools/Start-Engine.ps1', 'Source/Host/NativeSaveArchive.h')]
    protected += [artifact(BUILD_REPORT), build['executable'], artifact(RUNNER),
                  artifact(ROOT / 'PolicyInfo.ini')]
    current_tools = {name: artifact(PROJECT / 'tools' / name) for name in tool_names}
    protected += list(current_tools.values())
    command = [str(RUNNER), '--host-build', str(BUILD_REPORT), '--unit-assets-manifest', str(UNIT_MANIFEST),
               '--language', 'ko_KR', '--top-panel', '--action-info-panel', '--notification-panel',
               '--policy-info-settings', str(ROOT / 'PolicyInfo.ini')]
    started = {'utc': datetime.now(timezone.utc).isoformat(), 'command': command,
               'protected': protected, 'guard': artifact(Path(__file__)),
               'runtime_ids_before': sorted(row.name for row in (PROJECT / 'Build/InteractiveGameRuntime').iterdir()),
               'evidence_ids_before': sorted(row.name for row in (PROJECT / 'evidence/interactive_game').iterdir())}
    with marker.open('x', encoding='utf8') as stream:
        stream.write(json.dumps(started, indent=2) + '\n')
    retail = os.path.normcase(r"C:\Users\home\OneDrive\Documents\My Games\Sid Meier's Civilization 5")
    denied = []

    def audit(event, arguments):
        if event in ('open', 'os.listdir', 'os.scandir') and arguments and isinstance(arguments[0], (str, bytes, os.PathLike)):
            target = os.path.normcase(os.path.abspath(os.fsdecode(arguments[0])))
            if target == retail or target.startswith(retail + os.sep):
                denied.append(event)
                raise RuntimeError('Retail user configuration, mods and saves are out of scope')
        if event in ('subprocess.Popen', 'os.system', 'os.startfile', 'os.startfile/2',
                     'os.exec', 'os.posix_spawn', 'os.spawn'):
            denied.append(event)
            raise RuntimeError('Process execution is forbidden during private preparation')

    sys.addaudithook(audit)
    stdout, stderr = io.StringIO(), io.StringIO()
    guards = []
    try:
        with ExitStack() as stack:
            for name in ('subprocess.Popen', 'os.startfile', 'ctypes.CDLL', 'ctypes.WinDLL'):
                guards.append(stack.enter_context(patch(name, side_effect=RuntimeError('Execution forbidden: ' + name))))
            stack.enter_context(patch.object(sys, 'argv', command))
            stack.enter_context(redirect_stdout(stdout))
            stack.enter_context(redirect_stderr(stderr))
            try:
                runpy.run_path(str(RUNNER), run_name='__main__')
            except SystemExit as result:
                require(result.code in (None, 0), 'Private materializer failed')
    finally:
        (ROOT / 'stdout.log').write_text(stdout.getvalue(), encoding='utf8')
        (ROOT / 'stderr.log').write_text(stderr.getvalue(), encoding='utf8')
    require(not denied and all(guard.call_count == 0 for guard in guards), 'A forbidden access was attempted')
    summaries = [json.loads(line) for line in stdout.getvalue().splitlines() if line.startswith('{')]
    require(len(summaries) == 1 and summaries[0]['status'] == 'PRIVATE_CONTINUOUS_GAME_PREPARED', 'Missing preparation result')
    run_id = summaries[0]['run_id']
    runtime = PROJECT / 'Build/InteractiveGameRuntime' / run_id
    evidence = PROJECT / 'evidence/interactive_game' / run_id
    request_path = evidence / 'request.json'
    request = json.loads(request_path.read_text(encoding='utf8'))
    require(request['smoke'] is False and request['resume_from'] is None
            and request['ui_support_from_run'] is None, 'Unexpected execution or inherited UI profile')
    require(request['input_profile'] == 'MANUAL_CONTINUOUS_GAME_LOOP', 'Wrong manual profile')
    require(request['policy_info_options']['origin'] == 'EXPLICIT_POLICY_SETTINGS_READ_ONLY'
            and request['policy_info_options']['original_user_settings'] is None, 'Retail configuration was selected')
    require(request['host_runtime_validation'] == validation, 'Runtime-input policy changed')
    require(not (runtime / 'sessions').exists()
            and not any((evidence / name).exists() for name in ('attempt.json', 'result.json', 'driver_result.json')),
            'Unexpected native execution output')
    check_artifacts(request)
    check_artifacts(protected)
    require(request['provenance']['host_build']['sha256'] == digest(BUILD_REPORT), 'Wrong build provenance')
    executable = next(row for row in request['runtime_inputs'] if Path(row['path']).name == 'ZeroSisHost_x64.exe')
    require(executable['sha256'] == build['executable']['sha256'], 'Wrong private Host')
    inventory = request['interactive_ui_support_inventory']
    require(set(inventory['tools']) == set(tool_names), 'Unexpected frozen Python support set')
    require(inventory['asset_preparation_provenance']['frozen']['sha256'] == build['ui_assets']['sha256'], 'Wrong prepared UI catalog')
    manifest_ref = inventory['frozen_support_manifest']
    manifest = json.loads(Path(manifest_ref['path']).read_text(encoding='utf8'))
    for name, source in current_tools.items():
        row = inventory['tools'][name]
        require(row['source']['sha256'] == row['frozen']['sha256'] == source['sha256']
                == manifest['tools'][name]['sha256'], 'Current/frozen/manifest Python mismatch: ' + name)
    command = request['command']
    require(command[command.index('--support-manifest-sha256') + 1] == manifest_ref['sha256'], 'Wrong command support manifest')
    for flag, expected in (
        ('--host', executable['path']), ('--cwd', str(runtime)), ('--runtime', str(runtime)),
        ('--tools', str(runtime / 'interactive_ui_support/tools')),
        ('--icons', inventory['inline_icons']['frozen']['path']),
        ('--support-manifest', manifest_ref['path'])):
        require(Path(command[command.index(flag) + 1]).resolve(strict=True) == Path(expected).resolve(strict=True),
                'Prepared command selected a different path: ' + flag)
    require(command[command.index('--mode') + 1] == 'play'
            and command[command.index('--language') + 1] == 'ko_KR'
            and all(flag in command for flag in ('--top-panel', '--action-info-panel', '--notification-panel')),
            'Prepared command selected a different UI/language profile')
    databases = []
    for row in request['runtime_inputs']:
        if Path(row['path']).suffix.lower() == '.db':
            source, target = Path(row['source']).stat(), Path(row['path']).stat()
            require(source.st_ino and target.st_ino and (source.st_dev, source.st_ino) != (target.st_dev, target.st_ino), 'Database aliases its input')
            databases.append({'name': Path(row['path']).name, 'bytes': target.st_size})
    methods = request['materializations']
    record = {'schema': 'zerosis.load_menu.private_runtime_prepared.v1', 'status': 'PREPARED_NOT_EXECUTED',
              'utc': datetime.now(timezone.utc).isoformat(), 'run_id': run_id, 'host_build_id': BUILD_ID,
              'request': artifact(request_path), 'host_build': artifact(BUILD_REPORT),
              'guard': artifact(Path(__file__)), 'runner': artifact(RUNNER),
              'runtime_executable': executable, 'protected': protected,
              'ui_support_manifest': manifest_ref, 'current_python_support_count': len(current_tools),
              'hardlinks': sum(row.get('materialization_method') == 'hardlink' for row in methods),
              'cache_hits': sum(row.get('cache_method') == 'cache-hit' for row in methods),
              'new_cache_objects': sum(str(row.get('cache_method', '')).startswith('cache-created') for row in methods),
              'private_databases': databases, 'forbidden_access_attempts': denied,
              'native_process_or_ctypes_calls': sum(guard.call_count for guard in guards),
              'retail_mods_saves_settings_or_process_access': False,
              'host_gamecore_or_windows_executed': False, 'default_release_unchanged': True,
              'full_gameplay_original_ui_and_save_compatibility_accepted': False}
    output = ROOT / 'prepared.json'
    require(not output.exists(), 'Preparation receipt already exists')
    output.write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps({key: record[key] for key in ('status', 'run_id', 'host_build_id', 'hardlinks', 'cache_hits', 'new_cache_objects')}))


if __name__ == '__main__':
    main()
