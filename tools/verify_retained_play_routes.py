"""Verify retained launch routes, user saves and sealed bundles without starting gameplay."""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def require(value, message):
    if not value:
        raise RuntimeError(message)


def invoke(command, cwd):
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True,
                            encoding='utf8', errors='replace', timeout=30,
                            creationflags=subprocess.CREATE_NO_WINDOW)
    require(result.returncode == 0, result.stderr or result.stdout or 'Command failed')
    return result.stdout.strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location('retention', ROOT / 'tools/prune_superseded_runtime_artifacts.py')
    retention = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(retention)
    baseline_path = retention.boundary(args.baseline.resolve(strict=True))
    baseline = json.loads(baseline_path.read_text(encoding='utf8'))
    require(baseline['status'] == 'PASS_POST_CLEANUP_LAUNCHER_SAVE_ROUTES_AND_BUNDLES',
            'Baseline is not a passing save-route verification')
    output = args.output.absolute()
    require(output.parent.resolve(strict=True).is_relative_to(ROOT / 'evidence') and not output.exists(),
            'Output must be a new file in existing project evidence')
    retention.boundary(output.parent)
    launcher = ROOT / 'tools/Start-Engine.ps1'
    launcher_hash = digest(launcher)
    manual = list(dict.fromkeys(retention.RUN.findall(launcher.read_text(encoding='utf8'))))
    require(manual, 'No manual runtimes were found')
    runtime_root = ROOT / 'Build/InteractiveGameRuntime'
    saves = sorted(p for run in manual for p in (runtime_root / run).rglob('*.zssave'))
    before = {str(retention.boundary(p)): digest(p) for p in saves}
    previous = {row['save']: row['sha256'] for row in baseline['saved_game_routes']}
    require(previous and all(before.get(p) == sha for p, sha in previous.items()),
            'A previously protected user save is missing or changed')

    def route(mode, save=None):
        command = ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass',
                   '-File', str(launcher), '-Mode', mode, '-PlanOnly']
        if save:
            command += ['-Checkpoint', str(save)]
        result = json.loads(invoke(command, ROOT))
        require(result['requested_mode'] == mode and not result['smoke_inputs'] and
                result['total_play_timeout_seconds'] == 0, 'Invalid manual launch plan')
        return result

    routes = {'new': route('New'), 'continue': route('Continue')}
    build = json.loads((ROOT / 'evidence/ui_window_host' / retention.BUILD / 'build_result.json').read_text(encoding='utf8'))
    require(routes['new']['runtime'] == str(runtime_root / manual[0]) and
            routes['new']['host_sha256'] == build['executable']['sha256'],
            'New-game route does not use the validated Host')
    saved_routes = []
    for path in saves:
        planned = route('Load', path)
        require(planned['mode'] == 'Load' and planned['checkpoint'] == str(path), 'Saved-game route changed')
        saved_routes.append({'save': str(path), 'sha256': before[str(path)], 'runtime': planned['runtime']})
    bundles = []
    for run in dict.fromkeys([*manual, *retention.LATEST]):
        runtime = retention.boundary(runtime_root / run)
        stdout = invoke([str(runtime / 'ZeroSisHost_x64.exe'), '--verify-bundle'], runtime)
        require('BUNDLE_VERIFIED' in stdout and 'architecture=x64 GAMECORE_LOADED=false' in stdout,
                'Bundle verification did not confirm its scope')
        bundles.append({'runtime': str(runtime), 'exit_code': 0, 'stdout': stdout})
    require(before == {str(p): digest(p) for p in saves} and digest(launcher) == launcher_hash,
            'Protected saves or launcher changed during verification')
    result = {'status': 'PASS_POST_CLEANUP_LAUNCHER_SAVE_ROUTES_AND_BUNDLES',
              'gameplay_launched': False, 'machine_execution_policy_changed': False,
              'baseline': {'path': str(baseline_path), 'sha256': digest(baseline_path)},
              'verifier': {'path': str(Path(__file__)), 'sha256': digest(Path(__file__))},
              'routes': routes, 'saved_game_routes': saved_routes, 'bundles': bundles,
              'manual_saves_match_previous_cleanup': True, 'new_manual_uses_validated_candidate': True}
    with output.open('x', encoding='utf8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps({'status': result['status'], 'saves': len(saves), 'bundles': len(bundles),
                      'output': str(output)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
