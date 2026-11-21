"""Use the existing manual materializer while forbidding process/DLL execution."""
from contextlib import ExitStack, redirect_stdout, redirect_stderr
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import runpy
import sys
from unittest.mock import patch

PROJECT = Path(__file__).parents[4]
ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT / 'tools'))
from collect_baseline import digest
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts

BUILD_ID = '20261014T110906Z_a60e98e7bde6'
BUILD_REPORT = PROJECT / 'evidence/ui_window_host' / BUILD_ID / 'build_result.json'
RUNNER = PROJECT / 'tools/run_interactive_game.py'
UNIT_MANIFEST = PROJECT / 'Build/UnitAssets/480678966a78bedbee642040285010aa86f8a2cc34b0929c2774dcee8ab54266/unit-assets.manifest.json'


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    marker = ROOT / 'preparation_started.json'
    require(not marker.exists(), 'Do not repeat this one-shot preparation')
    require(digest(RUNNER) == 'dd46b50bebf88f569f920b7314c8698745a2bdb004b12b1c2d5ae2708900659e', 'Runner changed since review')
    require(digest(BUILD_REPORT) == '8d61016078e667d6a7ebf1d67b5b0e4c18a907929d5fe5acc8d74b8eb503891d', 'Host report changed')
    require(digest(UNIT_MANIFEST) == 'd6df7f9123075e7cd328712c968b1ef8023f1e32da16ced2d95651f4ffa0c3f1', 'Unit manifest changed')
    protected = [artifact(PROJECT / 'Play/EarlyAccess/release.json'),
                 artifact(PROJECT / 'tools/Start-Engine.ps1'), artifact(BUILD_REPORT)]
    command = [str(RUNNER), '--host-build', str(BUILD_REPORT), '--unit-assets-manifest', str(UNIT_MANIFEST),
               '--top-panel', '--action-info-panel', '--notification-panel']
    require('--smoke' not in command and '--resume-run' not in command, 'Execution/resume not authorized')
    stdout, stderr = io.StringIO(), io.StringIO()
    guards = []
    ROOT.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps({'utc': datetime.now(timezone.utc).isoformat(), 'command': command,
                                  'protected_before': protected,
                                  'runtime_ids_before': sorted(p.name for p in (PROJECT / 'Build/InteractiveGameRuntime').iterdir() if p.is_dir()),
                                  'evidence_ids_before': sorted(p.name for p in (PROJECT / 'evidence/interactive_game').iterdir() if p.is_dir())}, indent=2) + '\n', encoding='utf8')
    with ExitStack() as stack:
        for name in ('subprocess.Popen', 'os.startfile', 'ctypes.CDLL', 'ctypes.WinDLL'):
            guards.append(stack.enter_context(patch(name, side_effect=RuntimeError('Execution is forbidden during manual materialization: ' + name))))
        stack.enter_context(patch.object(sys, 'argv', command))
        stack.enter_context(redirect_stdout(stdout))
        stack.enter_context(redirect_stderr(stderr))
        try:
            runpy.run_path(str(RUNNER), run_name='__main__')
        except SystemExit as exit_code:
            require(exit_code.code in (None, 0), 'Manual materializer failed')
    require(all(guard.call_count == 0 for guard in guards), 'A process/library execution was attempted')
    (ROOT / 'stdout.log').write_text(stdout.getvalue(), encoding='utf8')
    (ROOT / 'stderr.log').write_text(stderr.getvalue(), encoding='utf8')
    summaries = [json.loads(line) for line in stdout.getvalue().splitlines() if line.startswith('{')]
    require(len(summaries) == 1 and summaries[0]['status'] == 'PRIVATE_CONTINUOUS_GAME_PREPARED', 'Manual preparation summary missing')
    run_id = summaries[0]['run_id']
    evidence = PROJECT / 'evidence/interactive_game' / run_id
    runtime = PROJECT / 'Build/InteractiveGameRuntime' / run_id
    request_path = evidence / 'request.json'
    request = json.loads(request_path.read_text(encoding='utf8'))
    require(request['run_id'] == run_id and not request['smoke'] and request['resume_from'] is None, 'Unexpected request profile')
    require(request['input_profile'] == 'MANUAL_CONTINUOUS_GAME_LOOP', 'Wrong manual input profile')
    require(request['command'][request['command'].index('--mode') + 1] == 'play', 'Wrong future launch mode')
    for flag in ('--top-panel', '--action-info-panel', '--notification-panel'):
        require(flag in request['command'], 'Requested UI support missing')
    require(not any((evidence / name).exists() for name in ('attempt.json', 'result.json', 'driver_result.json')), 'Native execution evidence unexpectedly exists')
    require(not (runtime / 'sessions').exists(), 'A game session was unexpectedly created')
    check_artifacts(request)
    check_artifacts(protected)
    build = json.loads(BUILD_REPORT.read_text(encoding='utf8'))
    exe = next(row for row in request['runtime_inputs'] if Path(row['path']).name == 'ZeroSisHost_x64.exe')
    require(exe['sha256'] == build['executable']['sha256'], 'Runtime uses a different Host')
    prepared = request['interactive_ui_support_inventory']['asset_preparation_provenance']['frozen']
    require(prepared['sha256'] == build['ui_assets']['sha256'], 'Runtime uses a different prepared UI catalog')
    copied_databases = []
    for row in request['runtime_inputs']:
        if Path(row['path']).suffix.lower() == '.db':
            source, target = Path(row['source']).stat(), Path(row['path']).stat()
            require((source.st_dev, source.st_ino) != (target.st_dev, target.st_ino), 'Mutable database aliases source')
            copied_databases.append({'name': Path(row['path']).name, 'bytes': target.st_size})
    methods = request['materializations']
    record = {'schema': 'ZEROSIS_MANUAL_RUNTIME_PREPARATION_V1', 'status': 'PREPARED_NOT_EXECUTED',
              'utc': datetime.now(timezone.utc).isoformat(), 'run_id': run_id, 'host_build_id': BUILD_ID,
              'request': artifact(request_path), 'build_report': artifact(BUILD_REPORT),
              'runner': artifact(RUNNER), 'guard': artifact(Path(__file__)), 'runtime_executable': exe,
              'process_or_ctypes_library_calls': 0, 'game_session_or_execution_result_created': False,
              'host_gamecore_or_windows_executed': False, 'runtime_input_hashes_verified': True,
              'default_release_and_launcher_unchanged': True, 'protected': protected,
              'hardlink_materializations': sum(row.get('materialization_method') == 'hardlink' for row in methods),
              'cache_hit_count': sum(row.get('cache_method') == 'cache-hit' for row in methods),
              'new_cache_count': sum(str(row.get('cache_method', '')).startswith('cache-created') for row in methods),
              'private_databases': copied_databases, 'retail_user_settings_read_only': True,
              'ui_support_manifest': request['interactive_ui_support_inventory']['frozen_support_manifest'],
              'stdout': artifact(ROOT / 'stdout.log'), 'stderr': artifact(ROOT / 'stderr.log'),
              'native_window_ime_named_save_and_restore_complete': False}
    output = ROOT / 'prepared.json'
    require(not output.exists(), 'Preparation receipt already exists')
    output.write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps({'status': record['status'], 'run_id': run_id, 'host_build_id': BUILD_ID,
                      'report': str(output), 'sha256': digest(output), 'hardlinks': record['hardlink_materializations'],
                      'cache_hits': record['cache_hit_count'], 'new_cache_objects': record['new_cache_count']}))


if __name__ == '__main__':
    main()
