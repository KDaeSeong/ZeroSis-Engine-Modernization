"""Syntax-compile current civilian art and camera consumers; no link or execution."""
from datetime import datetime, timezone
import hashlib
import ctypes
import json
from pathlib import Path
import re
import sys

PROJECT = Path(__file__).absolute().parents[3]
STAGE = Path(__file__).absolute().parent
sys.path.insert(0, str(PROJECT / 'tools'))
from native_build import environment_for, run

BASE_ID = '20261016T122615Z_1af4a5449cf1'
BASE_SHA = '1c6e4f2640bca96c687fb118e47e48116d8162a48276ccc91405578a40ea170d'
ROLES = ((0, 'host_main', 'HostMain'), (3, 'world_renderer', 'WorldViewRenderer'),
         (4, 'terrain_renderer', 'WorldTerrainRenderer'))


def seal(path):
    path = Path(path)
    with path.open('rb') as stream:
        sha = hashlib.file_digest(stream, 'sha256').hexdigest()
    return {'path': str(path), 'bytes': path.stat().st_size, 'sha256': sha}


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def require(value, message):
    if not value:
        raise RuntimeError(message)


def main():
    output = STAGE / 'syntax'
    require(not output.exists(), 'Inspect the previous syntax invocation; do not replay it')
    output.mkdir()
    report = {'schema': 'zerosis.civilian_unit.actual_consumer_syntax.v1', 'status': 'IN_PROGRESS',
              'started_utc': datetime.now(timezone.utc).isoformat(), 'baseline_build_id': BASE_ID,
              'translation_units': [], 'linked': False, 'host_gamecore_hwnd_executed': False,
              'retail_mods_user_saves_settings_or_processes_accessed': False}
    destination = output / 'result.json'
    def checkpoint():
        destination.write_text(json.dumps(report, indent=2) + '\n', encoding='utf8')
    checkpoint()
    try:
        baseline_path = PROJECT / f'evidence/ui_window_host/{BASE_ID}/build_result.json'
        require(seal(baseline_path)['sha256'] == BASE_SHA, 'Preserved baseline report changed')
        baseline = read(baseline_path)
        records = {str(Path(row['path'])).casefold(): row
                   for tu in baseline['dependency_discovery']['translation_units']
                   for row in (tu['response'], tu['dependency_report'])}
        responses, candidates = [], {PROJECT / 'Source/Presentation/WorldCameraControls.h', PROJECT / 'Source/Presentation/WorldUnitArtSelection.h'}
        for index, role, stem in ROLES:
            directory = PROJECT / f'Build/UiWindowHost/{BASE_ID}/dependency_discovery/tu_{index:02d}_{role}'
            rsp = directory / f'{role}.discover.rsp'
            deps = directory / f'{role}.sourceDependencies.json'
            # Discovery responses use live source paths; frozen final responses
            # are intentionally not rewritten or compiled here.
            for path in (rsp, deps):
                expected = records.get(str(path).casefold())
                require(expected is not None and seal(path)['sha256'] == expected['sha256'], 'Baseline discovery input differs')
            data = read(deps)['Data']
            for raw in (data['Source'], *data['Includes']):
                path = Path(raw)
                if path.is_relative_to(PROJECT / 'Source'):
                    candidates.add(path)
            responses.append((role, rsp, data['Source']))
        before = {str(path).casefold(): seal(path) for path in sorted(candidates)}
        report['project_inputs_before'] = before
        report['baseline_report'] = seal(baseline_path)
        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel32.SetErrorMode(32771)
        require(kernel32.WerSetFlags(32) >= 0, 'WerSetFlags failed before any child launch')
        report['runner'] = seal(Path(__file__))
        env, compiler_text = environment_for(Path(r'C:\Program Files\Microsoft Visual Studio\2022\Community'), 'x64', output / 'environment')
        compiler = Path(compiler_text)
        require(seal(compiler)['sha256'] == baseline['compiler']['sha256'], 'Compiler differs from baseline')
        env['VSLANG'], env['CL'], env['_CL_'] = '1033', '', ''
        report['compiler'] = seal(compiler)
        for role, source_rsp, actual_source in responses:
            folder = output / role
            folder.mkdir()
            deps = folder / 'sourceDependencies.json'
            flags = [line for line in source_rsp.read_text(encoding='utf-8-sig').splitlines()
                     if line != '/c' and not line.startswith(('/Fo', '/sourceDependencies'))]
            require(not any('frozen' in flag.casefold() or flag.startswith(('/Fe', '/Fd', '/link')) for flag in flags),
                    'Unexpected frozen, code-generation or link argument')
            flags.extend(('/Zs', '/WX', f'/sourceDependencies "{deps}"'))
            response = folder / 'syntax.rsp'
            response.write_text('\n'.join(flags) + '\n', encoding='utf8')
            result = run([compiler, '@' + str(response)], cwd=folder, env=env, timeout=300)
            text = (result.stdout + result.stderr).decode('mbcs', errors='replace')
            log = folder / 'compile.log'
            log.write_text(text, encoding='utf8')
            warnings = re.findall(r'\bwarning\s+[A-Z]+\d+', text, flags=re.I)
            row = {'role': role, 'actual_source': actual_source, 'response': seal(response),
                   'compile_log': seal(log), 'exit_code': result.returncode, 'warnings': warnings}
            report['translation_units'].append(row)
            checkpoint()
            require(result.returncode == 0 and not warnings, 'Current consumer syntax failed: ' + role)
            require(deps.is_file(), 'Compiler dependency report is missing')
            consumed = read(deps)['Data']
            require(Path(consumed['Source']).samefile(actual_source), 'Compiler consumed a different translation unit')
            used = {str(Path(raw)).casefold() for raw in (consumed['Source'], *consumed['Includes'])
                    if Path(raw).is_relative_to(PROJECT / 'Source')}
            require(not used.difference(before), 'Compiler consumed an unsealed project dependency')
            require(str(PROJECT / 'Source/Presentation/WorldCameraControls.h').casefold() in used,
                    'Current consumer did not include the production camera controls')
            if role == 'terrain_renderer':
                require(str(PROJECT / 'Source/Presentation/WorldUnitArtSelection.h').casefold() in used, 'Terrain TU did not consume actual production art selector')
            row.update(dependencies=seal(deps), consumed_project_input_count=len(used), camera_header_consumed=True, unit_art_header_consumed=(role == 'terrain_renderer'))
        after = {str(path).casefold(): seal(path) for path in sorted(candidates)}
        require(before == after, 'Current source changed while syntax-compiling')
        generated = [str(path) for path in output.rglob('*') if path.suffix.lower() in ('.obj', '.exe', '.dll', '.pdb')]
        require(not generated, 'Syntax-only compilation generated code artifacts')
        report.update(status='PASS', project_inputs_after=after, generated_code_artifacts=generated,
                      finished_utc=datetime.now(timezone.utc).isoformat())
    except BaseException as error:
        report.update(status='FAIL', error=type(error).__name__ + ': ' + str(error))
        checkpoint()
        raise
    checkpoint()
    print(json.dumps({'status': report['status'], 'translation_units': len(report['translation_units']),
                      'project_inputs': len(report['project_inputs_before']), 'report': seal(destination)}))


if __name__ == '__main__':
    main()
