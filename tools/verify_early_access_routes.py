"""Compare Early Access launch plans and retained user saves without starting a game.

Before: --phase before --output evidence/<existing-directory>/before.json
After:  --phase after --baseline <before.json> --new-runtime <manual-run-id>
        --output evidence/<existing-directory>/after.json
Only the new output JSON is written. This does not verify gameplay or migrate saves.
"""
from __future__ import annotations

import argparse
import codecs
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import struct
import subprocess
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
RUNTIMES = ROOT / 'Build/InteractiveGameRuntime'
LAUNCHER = ROOT / 'tools/Start-Engine.ps1'
SCHEMA = 'ZEROSIS_EARLY_ACCESS_ROUTES_V1'
RUN = r'[0-9]{8}T[0-9]{6}Z_[0-9a-f]{12}'
NO_BUNDLE = 'The engine version used by this saved game is not in the retained play versions.'


def require(value, message):
    if not value:
        raise RuntimeError(message)


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def bounded(path):
    path = Path(path).resolve(strict=True)
    require(path.is_relative_to(ROOT), 'Path escaped project: ' + str(path))
    return path


def relative(path):
    return bounded(path).relative_to(ROOT).as_posix()


def load_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def launcher_lists():
    text = LAUNCHER.read_text(encoding='utf-8-sig')
    lists, spans = {}, []
    for variable, key in [('runtimeIds', 'default'), ('earlyAccessRuntimeIds', 'early_access')]:
        matches = list(re.finditer(r'(?m)^\$' + variable + r'\s*=\s*@\(([^)]*)\)', text))
        require(len(matches) == 1, 'Expected one literal launcher list: ' + variable)
        match = matches[0]
        require(re.fullmatch(r"\s*'" + RUN + r"'(?:\s*,\s*'" + RUN + r"')*\s*", match[1]),
                'Launcher list is no longer a literal run-ID array: ' + variable)
        lists[key] = re.findall(RUN, match[1])
        spans.append((*match.span(1), key))
    all_ids = lists['early_access'] + lists['default']
    require(len(all_ids) == len(set(all_ids)), 'Manual launcher lists contain duplicate run IDs')
    for start, end, key in sorted(spans, reverse=True):
        text = text[:start] + '<' + key + '>' + text[end:]
    return lists, hashlib.sha256(text.encode('utf8')).hexdigest()


def runtime_records(ids):
    records = {}
    for run in ids:
        require(re.fullmatch(RUN, run), 'Invalid manual runtime ID')
        runtime = bounded(RUNTIMES / run)
        require(runtime.parent == RUNTIMES.resolve(), 'Manual runtime escaped its directory')
        request_path = bounded(ROOT / 'evidence/interactive_game' / run / 'request.json')
        request = load_json(request_path)
        require(request.get('run_id') == run and bounded(request['cwd']) == runtime and
                request.get('smoke') is False and request.get('input_profile') == 'MANUAL_CONTINUOUS_GAME_LOOP',
                'Launcher exposes a runtime that is not prepared for manual play: ' + run)
        fixtures = {'smoke', 'decisions', 'research_tree', 'tech_award', 'unit_actions',
                    'worker_build', 'combat', 'city_capture', 'social_policy_tenets'}
        require(all(value is False or value is None for key, value in request.items()
                    if key in fixtures or key.endswith('_smoke')),
                'Manual runtime request contains a smoke fixture: ' + run)
        command = request['command']
        require(command.count('--mode') == 1, 'Manual request has no unique driver mode')
        mode = command[command.index('--mode') + 1]
        require(mode in ('play', 'play-load'), 'Manual request uses a smoke driver mode')
        files = {'request': request_path, 'bundle': runtime / 'bundle.manifest',
                 'host': runtime / 'ZeroSisHost_x64.exe', 'play': runtime / 'Play.ps1',
                 'resume': runtime / 'Resume.ps1'}
        hashes = {key: digest(bounded(path)) for key, path in files.items()}
        for key in ('play', 'resume'):
            reference = request['launcher_control_metadata'][key]
            require(bounded(reference['path']) == files[key] and reference['sha256'] == hashes[key],
                    'Prepared launcher differs from its pinned request: ' + run + '/' + key)
        records[run] = {'hashes': hashes, 'mode': mode, 'has_resume_source': request.get('resume_from') is not None}
    return records


def save_paths(ids):
    paths = []
    for run in ids:
        stack = [bounded(RUNTIMES / run)]
        while stack:
            with os.scandir(stack.pop()) as rows:
                for row in rows:
                    info = row.stat(follow_symlinks=False)
                    require(not getattr(info, 'st_file_attributes', 0) & 0x400,
                            'Reparse point in retained manual runtime: ' + row.path)
                    if stat.S_ISDIR(info.st_mode):
                        stack.append(Path(row.path))
                    elif stat.S_ISREG(info.st_mode) and row.name.lower().endswith('.zssave'):
                        paths.append(bounded(row.path))
    return sorted(paths)


def save_record(path):
    before = path.stat()
    with path.open('rb') as stream:
        header = stream.read(60)
        require(len(header) == 60 and header[:16] == b'ZEROSIS_SAVE_V1\0' and
                struct.unpack_from('<I', header, 16)[0] == 1, 'Unsupported native save header: ' + str(path))
        kind, flags, length = struct.unpack_from('<III', header, 48)
        require((kind, flags) == (1, 0) and 1 <= length <= 16384, 'Invalid save bundle identity')
        bundle = stream.read(length)
        require(len(bundle) == length, 'Truncated save bundle identity')
    sha = digest(path)
    after = path.stat()
    fields = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns')
    require(before.st_ino and all(getattr(before, key) == getattr(after, key) for key in fields),
            'User save changed while being read: ' + str(path))
    # Decimal strings preserve NTFS IDs and nanoseconds through JavaScript readers.
    return {'bytes': after.st_size, 'sha256': sha, 'file_id': str(after.st_ino),
            'device': str(after.st_dev), 'mtime_ns': str(after.st_mtime_ns),
            'bundle_sha256': hashlib.sha256(bundle).hexdigest()}


def save_snapshot(ids):
    return {relative(path): save_record(path) for path in save_paths(ids)}


def invoke(arguments, encoding='utf-8-sig'):
    result = subprocess.run(arguments, cwd=ROOT, stdin=subprocess.DEVNULL, capture_output=True,
                            text=True, encoding=encoding, errors='strict', timeout=45,
                            creationflags=subprocess.CREATE_NO_WINDOW, shell=False)
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def powershell_path(value):
    shell = Path(value or shutil.which('pwsh.exe') or '')
    require(shell.is_file(), 'PowerShell 7 pwsh.exe is required; supply --powershell if absent from PATH')
    # Fixed probe, with no interpolated paths or user input. All launcher calls use -File argument arrays.
    code = '[ordered]@{major=$PSVersionTable.PSVersion.Major;code_page=[Console]::OutputEncoding.CodePage}|ConvertTo-Json -Compress'
    status, stdout, stderr = invoke([str(shell), '-NoLogo', '-NoProfile', '-NonInteractive', '-Command', code], 'ascii')
    require(status == 0, 'PowerShell encoding probe failed: ' + stderr[:500])
    probe = json.loads(stdout)
    require(probe['major'] >= 7 and type(probe['code_page']) is int and probe['code_page'] > 0,
            'Route verification requires PowerShell 7 and a valid console code page')
    encoding = 'utf-8-sig' if probe['code_page'] == 65001 else 'cp' + str(probe['code_page'])
    codecs.lookup(encoding)  # Reject unsupported code pages; never replace undecodable bytes.
    return str(shell.resolve()), encoding, probe['code_page']


def collect_plans(shell, lists, runtimes, saves, encoding):
    plans = {}
    for early in (False, True):
        label = 'ea' if early else 'default'
        ids = (lists['early_access'] if early else []) + lists['default']
        continuation_ids = lists['early_access'] if early else lists['default']
        continuation = [path for path in saves if any(path.startswith('Build/InteractiveGameRuntime/' + run + '/sessions/')
                        for run in continuation_ids) and fnmatch.fnmatchcase(Path(path).name, 'play-save-*-turn-*.zssave')]
        newest = max((int(saves[path]['mtime_ns']) for path in continuation), default=None)
        latest = {path for path in continuation if int(saves[path]['mtime_ns']) == newest}
        for mode, save in [('New', None), ('Continue', None)] + [('Load', path) for path in saves]:
            arguments = [shell, '-NoLogo', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                         '-File', str(LAUNCHER), '-Mode', mode, '-PlanOnly']
            if early:
                arguments.append('-EarlyAccess')
            if save:
                arguments += ['-Checkpoint', str(ROOT / save)]
            status, stdout, stderr = invoke(arguments, encoding)
            key = label + ':' + mode + (':' + save if save else '')
            matches = [run for run in ids if runtimes[run]['hashes']['bundle'] == saves[save]['bundle_sha256']] if save else []
            if mode == 'Load' and not matches:
                plain_error = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', stderr)
                plain_error = ' '.join(plain_error.split())
                require(status != 0 and NO_BUNDLE in plain_error, 'Unexpected rejection of unavailable Load route: ' + key)
                plans[key] = {'status': 'UNAVAILABLE_BUNDLE', 'returncode': status}
                continue
            require(status == 0, 'Launch planning failed: ' + key + ': ' + stderr[:700])
            plan = json.loads(stdout)
            expected_keys = {'requested_mode', 'mode', 'early_access', 'runtime', 'checkpoint',
                             'host_sha256', 'launcher', 'smoke_inputs', 'total_play_timeout_seconds'}
            require(set(plan) == expected_keys and plan['requested_mode'] == mode and
                    plan['early_access'] is early and plan['smoke_inputs'] is False and
                    type(plan['total_play_timeout_seconds']) is int and plan['total_play_timeout_seconds'] == 0,
                    'Plan lost its manual-play/zero-timeout contract: ' + key)
            effective = 'New' if mode == 'New' or mode == 'Continue' and not latest else mode
            require(plan['mode'] == effective, 'Plan selected an unexpected effective mode: ' + key)
            if effective == 'New':
                require(plan['checkpoint'] in ('', None), 'New-game plan has a checkpoint')
                plan['checkpoint'] = ''  # PowerShell [string] defaults to empty, not JSON null.
                selected = ids[0]
            else:
                checkpoint = relative(plan['checkpoint'])
                require(checkpoint == save if mode == 'Load' else checkpoint in latest,
                        'Plan chose an unexpected user save: ' + key)
                matches = [run for run in ids if runtimes[run]['hashes']['bundle'] == saves[checkpoint]['bundle_sha256']]
                require(matches, 'Selected user save has no retained engine')
                selected = matches[0]
                plan['checkpoint'] = checkpoint
            expected_launcher = RUNTIMES / selected / ('Play.ps1' if effective == 'New' else 'Resume.ps1')
            require(bounded(plan['runtime']) == RUNTIMES / selected and
                    bounded(plan['launcher']) == expected_launcher and
                    plan['host_sha256'] == runtimes[selected]['hashes']['host'],
                    'Plan differs from its retained bundle/Host/launcher: ' + key)
            plan['runtime'] = selected
            plan['launcher'] = relative(expected_launcher)
            plans[key] = {'status': 'PASS', **plan}
    return plans


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase', choices=('before', 'after'), required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--new-runtime')
    parser.add_argument('--powershell', help='Path to PowerShell 7 pwsh.exe')
    args = parser.parse_args()
    require((args.phase == 'after') == bool(args.baseline and args.new_runtime),
            'After requires --baseline and --new-runtime; before takes neither')
    if args.phase == 'before':
        require(args.baseline is None and args.new_runtime is None, 'Before takes no promotion arguments')
    output = args.output.absolute()
    parent = output.parent.resolve(strict=True)
    require(parent.is_relative_to((ROOT / 'evidence').resolve()) and output.suffix == '.json' and
            not os.path.lexists(output), 'Output must be a new JSON in an existing project evidence directory')
    output = parent / output.name
    report = {'schema': SCHEMA, 'phase': args.phase, 'status': 'FAIL', 'started_utc': datetime.now(timezone.utc).isoformat(),
              'tool_sha256': digest(__file__), 'gameplay_launched': False, 'written_file': str(output),
              'limits': ['PlanOnly and byte/identity preservation do not prove gameplay or internal save compatibility.',
                         'Save scope is every zssave under the retained manual runtimes; automated runtime folders are excluded.',
                         'Libraries and original game files are not modified or exhaustively rehashed.']}
    try:
        lists, structure = launcher_lists()
        ids = lists['early_access'] + lists['default']
        launcher_sha = digest(LAUNCHER)
        runtimes = runtime_records(ids)
        saves = save_snapshot(ids)
        require(saves, 'No retained user saves found; refusing an empty preservation baseline')
        baseline = None
        if args.phase == 'after':
            baseline_path = bounded(args.baseline)
            require(baseline_path.is_relative_to(ROOT / 'evidence'), 'Baseline is outside project evidence')
            baseline = load_json(baseline_path)
            require(baseline['schema'] == SCHEMA and baseline['status'] == 'PASS' and baseline['phase'] == 'before' and
                    baseline['tool_sha256'] == report['tool_sha256'], 'Baseline is not a passing before report from this tool')
            require(re.fullmatch(RUN, args.new_runtime) and args.new_runtime not in baseline['runtimes'], 'New runtime is not new')
            require(lists['default'] == baseline['lists']['default'] and
                    lists['early_access'] == [args.new_runtime] + baseline['lists']['early_access'] and
                    structure == baseline['launcher_structure_sha256'], 'Launcher changed beyond prepending one EA runtime')
            require(saves == baseline['saves'], 'User save set, bytes, identity or modification time changed since before')
            require(all(runtimes.get(run) == record for run, record in baseline['runtimes'].items()),
                    'An existing retained runtime/request/bundle/launcher changed')
            require(runtimes[args.new_runtime]['mode'] == 'play' and not runtimes[args.new_runtime]['has_resume_source'],
                    'New EA runtime is not a prepared fresh manual game')
            report['baseline'] = {'path': relative(baseline_path), 'sha256': digest(baseline_path)}
            report['new_runtime'] = args.new_runtime
        shell, encoding, code_page = powershell_path(args.powershell)
        plans = collect_plans(shell, lists, runtimes, saves, encoding)
        if baseline:
            require(set(plans) == set(baseline['plans']), 'The protected plan set changed')
            for key, before in baseline['plans'].items():
                if key == 'ea:New' or key == 'ea:Continue' and before.get('mode') == 'New':
                    require(plans[key]['mode'] == 'New' and plans[key]['runtime'] == args.new_runtime and
                            plans[key]['checkpoint'] == '', 'EA New/fallback did not select the new manual runtime')
                else:
                    require(plans[key] == before, 'Existing Load/Continue/default route changed: ' + key)
        require(save_snapshot(ids) == saves, 'User saves changed during launch planning')
        require(runtime_records(ids) == runtimes and digest(LAUNCHER) == launcher_sha and launcher_lists() == (lists, structure),
                'Pinned runtime/launcher inputs changed during launch planning')
        require(digest(__file__) == report['tool_sha256'] and
                (not baseline or digest(baseline_path) == report['baseline']['sha256']),
                'Verifier or before report changed during launch planning')
        report.update(status='PASS', lists=lists, launcher_sha256=launcher_sha, launcher_structure_sha256=structure,
                      runtimes=runtimes, saves=saves, plans=plans, powershell=shell,
                      powershell_output_encoding=encoding, powershell_output_code_page=code_page,
                      save_count=len(saves), plan_count=len(plans),
                      all_saves_unchanged=True, smoke_runtimes_excluded=True, all_successful_plans_timeout_zero=True)
    except Exception as error:
        report['error'] = str(error)
    report['completed_utc'] = datetime.now(timezone.utc).isoformat()
    with output.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps({'status': report['status'], 'phase': args.phase, 'output': str(output),
                      'sha256': digest(output), 'saves': report.get('save_count'),
                      'plans': report.get('plan_count'), 'error': report.get('error')}, ensure_ascii=False))
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
