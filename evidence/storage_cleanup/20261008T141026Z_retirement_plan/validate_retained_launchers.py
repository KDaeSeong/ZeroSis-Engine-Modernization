"""Read-only post-cleanup check of the existing manual launcher and eight saves."""
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PWSH = r'C:\Users\home\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\powershell\pwsh.exe'

def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def main():
    baseline_path = ROOT / 'evidence/runtime_promotion/20261007T203124Z/launcher_validation.json'
    baseline = json.loads(baseline_path.read_text(encoding='utf-8-sig'))
    launcher = ROOT / 'tools/Start-Engine.ps1'
    report = {'status': 'CHECKING', 'plan_only': True, 'gameplay_launched': False,
              'baseline_path': str(baseline_path), 'baseline_sha256': digest(baseline_path),
              'launcher_sha256': digest(launcher), 'plans': [], 'saves': [], 'errors': []}
    output = HERE / 'post_cleanup_validation.json'
    try:
        assert report['launcher_sha256'] == baseline['launcher_sha256'], 'Manual launcher changed'
        assert len(baseline['plans']) == 10 and len(baseline['saves_before']) == 8
        for old in baseline['saves_before']:
            path = Path(old['path'])
            actual = digest(path)
            assert actual == old['sha256'], 'User save changed: ' + str(path)
            report['saves'].append({'path': str(path), 'bytes': path.stat().st_size, 'sha256': actual})
        keys = ('requested_mode', 'mode', 'runtime', 'checkpoint', 'host_sha256', 'launcher',
                'smoke_inputs', 'total_play_timeout_seconds')
        for old in baseline['plans']:
            command = [PWSH, '-NoProfile', '-NonInteractive', '-File', str(launcher),
                       '-Mode', old['requested_mode'], '-PlanOnly']
            if old['requested_mode'] == 'Load':
                command += ['-Checkpoint', old['checkpoint']]
            result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding='utf8',
                                    timeout=45, creationflags=subprocess.CREATE_NO_WINDOW)
            assert result.returncode == 0, result.stderr[-1000:]
            current = json.loads(result.stdout.lstrip('\ufeff'))
            assert all(current.get(key) == old.get(key) for key in keys), 'Launcher route differs from the preserved route'
            report['plans'].append(current)
        assert all(digest(row['path']) == row['sha256'] for row in report['saves']), 'Save changed during routing check'
        report.update(status='PASS_MANUAL_NEW_CONTINUE_AND_ALL_SAVED_BUNDLES', count=10,
                      user_saves=8, saves_unchanged=True)
    except Exception as error:
        report['status'] = 'FAILED_POST_CLEANUP_VALIDATION'
        report['errors'].append(type(error).__name__ + ': ' + str(error))
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps({key: report.get(key) for key in ('status', 'count', 'user_saves', 'saves_unchanged', 'errors')}))
    return 0 if report['status'].startswith('PASS_') else 1

if __name__ == '__main__':
    raise SystemExit(main())
