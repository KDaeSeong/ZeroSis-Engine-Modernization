"""Materialize this candidate with process and retail-state access denied."""
from contextlib import ExitStack, redirect_stderr, redirect_stdout
import ctypes
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import runpy
import sys
from unittest.mock import patch

from run_stage import PROJECT, STAGE, artifact, read, require, write


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--build-id', required=True)
    args = parser.parse_args()
    started_path, prepared_path = STAGE / 'preparation_started.json', STAGE / 'prepared.json'
    require(not started_path.exists() and not prepared_path.exists(), 'Inspect an existing preparation instead of repeating it')
    invocation = read(STAGE / 'build_invocation.json')
    require(invocation['exit_code'] == 0 and invocation['result']['build_id'] == args.build_id,
            'Preparation must use this stage successful build')
    report_path = PROJECT / f'evidence/ui_window_host/{args.build_id}/build_result.json'
    build = read(report_path)
    require(build['status'] == 'UI_WINDOW_HOST_CANDIDATE_BUILT', 'Host build did not pass')
    runner = PROJECT / 'tools/run_interactive_game.py'
    manifest = PROJECT / 'Build/UnitAssets/480678966a78bedbee642040285010aa86f8a2cc34b0929c2774dcee8ab54266/unit-assets.manifest.json'
    policy = STAGE / 'PolicyInfo.ini'
    tools = ('interactive_ui_driver.py', 'render_ui_popup.py', 'ui_pixel_scene.py', 'ui_bitmap_fonts.py', 'civ5_ui_assets.py')
    sources = {name: artifact(PROJECT / 'tools' / name) for name in tools}
    protected = list(read(STAGE / 'scope.json')['protected_artifacts'].values())
    protected += [artifact(report_path), artifact(runner), artifact(policy), *sources.values()]
    command = [str(runner), '--host-build', str(report_path), '--unit-assets-manifest', str(manifest),
               '--policy-info-settings', str(policy), '--language', 'ko_KR', '--top-panel',
               '--action-info-panel', '--notification-panel']
    write(started_path, {'utc': datetime.now(timezone.utc).isoformat(), 'argv': command,
        'protected': protected, 'guard': artifact(Path(__file__).absolute()),
        'runtime_ids_before': sorted(row.name for row in (PROJECT / 'Build/InteractiveGameRuntime').iterdir()),
        'evidence_ids_before': sorted(row.name for row in (PROJECT / 'evidence/interactive_game').iterdir())})
    retail = os.path.normcase(r"C:\Users\home\OneDrive\Documents\My Games\Sid Meier's Civilization 5")
    denied = []

    def audit(event, arguments):
        if event in ('open', 'os.listdir', 'os.scandir') and arguments and isinstance(arguments[0], (str, bytes, os.PathLike)):
            target = os.path.normcase(os.path.abspath(os.fsdecode(arguments[0])))
            if target == retail or target.startswith(retail + os.sep):
                denied.append(event)
                raise RuntimeError('Retail user configuration, mods and saves are outside this stage')
        if event in ('subprocess.Popen', 'os.system', 'os.startfile', 'os.startfile/2', 'os.exec', 'os.posix_spawn', 'os.spawn'):
            denied.append(event)
            raise RuntimeError('Child process execution is forbidden during preparation')

    sys.addaudithook(audit)
    sys.path.insert(0, str(PROJECT / 'tools'))
    from run_interactive_game import check_host_runtime_artifacts
    from verify_world_builder_map_object import check_artifacts
    validation = check_host_runtime_artifacts(build)
    stdout, stderr, guards = io.StringIO(), io.StringIO(), []
    try:
        with ExitStack() as stack:
            for name in ('subprocess.Popen', 'os.startfile', 'ctypes.CDLL', 'ctypes.WinDLL'):
                guards.append(stack.enter_context(patch(name, side_effect=RuntimeError('Execution forbidden: ' + name))))
            stack.enter_context(patch.object(sys, 'argv', command))
            stack.enter_context(redirect_stdout(stdout))
            stack.enter_context(redirect_stderr(stderr))
            try:
                runpy.run_path(str(runner), run_name='__main__')
            except SystemExit as result:
                require(result.code in (None, 0), 'Private materializer failed')
    finally:
        (STAGE / 'materializer.stdout.log').write_text(stdout.getvalue(), encoding='utf8')
        (STAGE / 'materializer.stderr.log').write_text(stderr.getvalue(), encoding='utf8')
    require(not denied and all(guard.call_count == 0 for guard in guards), 'A forbidden operation was attempted')
    summaries = [json.loads(line) for line in stdout.getvalue().splitlines() if line.startswith('{')]
    require(len(summaries) == 1 and summaries[0]['status'] == 'PRIVATE_CONTINUOUS_GAME_PREPARED', 'Missing preparation summary')
    run_id = summaries[0]['run_id']
    runtime, evidence = PROJECT / 'Build/InteractiveGameRuntime' / run_id, PROJECT / 'evidence/interactive_game' / run_id
    request_path = evidence / 'request.json'
    request = read(request_path)
    require(request['smoke'] is False and request['resume_from'] is None and request['ui_support_from_run'] is None and
            request['input_profile'] == 'MANUAL_CONTINUOUS_GAME_LOOP', 'Wrong execution/preparation profile')
    require(request['policy_info_options']['origin'] == 'EXPLICIT_POLICY_SETTINGS_READ_ONLY' and
            request['policy_info_options']['original_user_settings'] is None and
            request['policy_info_options']['policy_info'] == 1, 'Wrong private policy source')
    require(request['host_runtime_validation'] == validation, 'Host preflight policy changed')
    require(not (runtime / 'sessions').exists() and not any((evidence / name).exists() for name in
            ('attempt.json', 'result.json', 'driver_result.json')), 'Unexpected native execution output')
    check_artifacts(request)
    check_artifacts(protected)
    require(request['provenance']['host_build']['sha256'] == artifact(report_path)['sha256'], 'Wrong Host provenance')
    executable = next(row for row in request['runtime_inputs'] if Path(row['path']).name == 'ZeroSisHost_x64.exe')
    require(executable['sha256'] == build['executable']['sha256'], 'Wrong private Host')
    inventory = request['interactive_ui_support_inventory']
    require(set(inventory['tools']) == set(tools) and
            inventory['asset_preparation_provenance']['frozen']['sha256'] == build['ui_assets']['sha256'],
            'Wrong frozen frontend or UI catalog')
    support_manifest = read(Path(inventory['frozen_support_manifest']['path']))
    for name, source in sources.items():
        row = inventory['tools'][name]
        require(row['source']['sha256'] == row['frozen']['sha256'] == source['sha256'] == support_manifest['tools'][name]['sha256'],
                'Current/frozen/manifest Python mismatch: ' + name)
    databases = []
    for row in request['runtime_inputs']:
        if Path(row['path']).suffix.lower() == '.db':
            source, target = Path(row['source']).stat(), Path(row['path']).stat()
            require(source.st_ino and target.st_ino and (source.st_dev, source.st_ino) != (target.st_dev, target.st_ino),
                    'Writable private database aliases its input')
            databases.append({'name': Path(row['path']).name, 'bytes': target.st_size,
                              'source_identity': [source.st_dev, source.st_ino], 'target_identity': [target.st_dev, target.st_ino]})
    methods = request['materializations']
    record = {'schema': 'zerosis.owned_save_delete.private_prepared.v1', 'status': 'PREPARED_NOT_EXECUTED',
        'utc': datetime.now(timezone.utc).isoformat(), 'run_id': run_id, 'host_build_id': args.build_id,
        'request': artifact(request_path), 'host_build': artifact(report_path), 'guard': artifact(Path(__file__).absolute()),
        'runtime_executable': executable, 'protected': protected, 'current_python_support_count': len(tools),
        'ui_support_manifest': inventory['frozen_support_manifest'], 'runtime_inputs': len(request['runtime_inputs']),
        'hardlinks': sum(row.get('materialization_method') == 'hardlink' for row in methods),
        'cache_hits': sum(row.get('cache_method') == 'cache-hit' for row in methods),
        'new_cache_objects': sum(str(row.get('cache_method', '')).startswith('cache-created') for row in methods),
        'private_databases': databases, 'forbidden_access_attempts': denied,
        'native_process_or_ctypes_calls': sum(guard.call_count for guard in guards),
        'retail_mods_saves_settings_or_process_access': False, 'host_gamecore_or_windows_executed': False,
        'default_release_unchanged': True, 'native_delete_or_full_engine_acceptance': False}
    write(prepared_path, record)
    print(json.dumps({key: record[key] for key in ('status', 'run_id', 'host_build_id', 'hardlinks', 'cache_hits', 'new_cache_objects')}))


if __name__ == '__main__':
    main()
