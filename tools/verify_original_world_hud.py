"""Compile and run only the software offscreen world-HUD/camera component."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time

sys.dont_write_bytecode = True
PROJECT = Path(__file__).absolute().parents[1]
EVIDENCE = PROJECT / 'evidence/original_world_hud/component'
BUILD = PROJECT / 'Build/OriginalWorldHud/component'
SOURCES = (PROJECT / 'Tests/world_original_hud.cpp',
           PROJECT / 'Source/Presentation/WorldViewRenderer.cpp')
PROTECTED = (*SOURCES, PROJECT / 'Source/Presentation/WorldViewRenderer.h',
             PROJECT / 'Source/Presentation/WorldTerrainRenderer.h',
             PROJECT / 'Source/Presentation/BitmapRenderer.h',
             PROJECT / 'Source/Presentation/WorldCameraControls.h',
             PROJECT / 'Source/Presentation/BitmapWindow.cpp',
             PROJECT / 'Source/Presentation/BitmapWindow.h',
             PROJECT / 'Source/Host/InteractiveGameLoop.h',
             PROJECT / 'tools/native_build.py', Path(__file__).absolute())


def artifact(path):
    before = path.stat()
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    after = path.stat()
    assert (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) == (
        after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    return dict(path=str(path), bytes=before.st_size, sha256=digest)


def write_new(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def main():
    assert len(sys.argv) == 1 and not sys.flags.optimize
    assert not EVIDENCE.exists() and not BUILD.exists(), 'Inspect an existing component run before repeating it'
    from native_build import environment_for, run
    from collect_baseline import pe_header
    protected = [artifact(path) for path in PROTECTED]
    EVIDENCE.mkdir()
    BUILD.mkdir(parents=True)
    started = dict(schema='zerosis.original_world_hud.component_started.v1',
        protected_inputs=protected, source_copies_created=0,
        scope='Actual software WIC RenderWorldView and camera arithmetic; fail-closed unused terrain symbols.',
        host_sdk_or_window_execution_allowed=False, direct3d_terrain_or_swapchain_calls_allowed=False)
    write_new(EVIDENCE / 'started.json', started)
    children, modes = [], []
    try:
        environment, compiler = environment_for(
            Path(r'C:\Program Files\Microsoft Visual Studio\2022\Community'), 'x64', BUILD)
        compiler_ref = artifact(Path(compiler))
        assert compiler_ref['sha256'] == '8a547dfca2d7df1b6be1e2d212132c1b3b5a661caf5b2ecce481e21b3c1860a6'
        for mode in ('O2', 'Od'):
            directory = BUILD / mode
            directory.mkdir()
            exe = directory / 'world_original_hud.exe'
            objects, dependencies = [], []
            for index, source in enumerate(SOURCES):
                obj = directory / f'tu_{index:02d}.obj'
                dependency = directory / f'tu_{index:02d}.dependencies.json'
                flags = ['/nologo', '/std:c++17', '/' + mode, '/W4', '/WX', '/utf-8',
                         '/fp:strict', '/EHsc', '/MT', '/DUNICODE', '/D_UNICODE',
                         '/DNOMINMAX', '/DWIN32_LEAN_AND_MEAN', '/D_CRT_SECURE_NO_WARNINGS']
                if mode == 'Od':
                    flags.append('/RTC1')
                command = [compiler, *flags, '/c', str(source), '/Fo' + str(obj),
                           '/sourceDependencies', str(dependency)]
                began = time.monotonic()
                child = run(command, cwd=directory, env=environment, timeout=60)
                output = (child.stdout + child.stderr).decode('mbcs', errors='replace')
                log = EVIDENCE / f'{mode}_compile_{index:02d}.log'
                log.write_text(output[:65536], encoding='utf-8')
                children.append(dict(command=command, returncode=child.returncode,
                    elapsed_seconds=time.monotonic()-began, log=artifact(log)))
                assert child.returncode == 0 and not re.search(r'warning\s+[A-Z]+\d+|경고\s+[A-Z]+\d+', output, re.I)
                data = json.loads(dependency.read_bytes())['Data']
                paths = list(dict.fromkeys((data['Source'], *data['Includes'])))
                dependencies.append(dict(report=artifact(dependency),
                    actual_included_inputs_rehashed_after_compile=[artifact(Path(path)) for path in paths]))
                objects.append(artifact(obj))
            link = [str(Path(compiler).with_name('link.exe')), '/NOLOGO', '/WX', '/MACHINE:X64',
                    '/INCREMENTAL:NO', '/BREPRO', '/OPT:REF', '/OPT:ICF',
                    '/OUT:' + str(exe), '/MAP:' + str(directory / 'world_original_hud.map'),
                    *(row['path'] for row in objects), 'd2d1.lib', 'dwrite.lib',
                    'windowscodecs.lib', 'ole32.lib', 'uuid.lib']
            began = time.monotonic()
            child = run(link, cwd=directory, env=environment, timeout=60)
            output = (child.stdout + child.stderr).decode('mbcs', errors='replace')
            log = EVIDENCE / f'{mode}_link.log'
            log.write_text(output[:65536], encoding='utf-8')
            children.append(dict(command=link, returncode=child.returncode,
                elapsed_seconds=time.monotonic()-began, log=artifact(log)))
            assert child.returncode == 0 and not re.search(r'warning\s+[A-Z]+\d+|경고\s+[A-Z]+\d+', output, re.I)
            image = artifact(exe)
            image['pe'] = pe_header(exe)
            assert image['pe']['architecture'] == 'x64'
            captures = directory / 'temporary_pixels'
            captures.mkdir()
            command = [str(exe), str(captures)]
            began = time.monotonic()
            child = run(command, cwd=directory, env=environment, timeout=60)
            log = EVIDENCE / f'{mode}_run.log'
            output = (child.stdout + child.stderr).decode('utf-8', errors='replace')
            log.write_text(output[:65536], encoding='utf-8')
            children.append(dict(command=command, returncode=child.returncode,
                elapsed_seconds=time.monotonic()-began, log=artifact(log)))
            assert child.returncode == 0, 'Component assertions failed; preserve its log and exact temporary PNG'
            summaries = [json.loads(line) for line in output.splitlines() if line.startswith('{')]
            assert len(summaries) == 1 and summaries[0].get('status') == 'PASS_WORLD_ORIGINAL_HUD_COMPONENT'
            assert not list(captures.iterdir()), 'Inspect unexpected retained component captures'
            captures.rmdir()
            modes.append(dict(mode=mode, executable=image, dependency_reports=dependencies,
                              verified_objects=objects, component=summaries[0]))
        host_report = PROJECT / 'evidence/ui_window_host/20261024T042219Z_e6399c82ee5c/build_result.json'
        assert artifact(host_report)['sha256'] == (
            '8746bbe6614cc206e6fa87a1fb62b0f636a160e2dcb76e0a15214aad93d09300')
        host = json.loads(host_report.read_bytes())
        frozen = PROJECT / 'Build/UiWindowHost' / host['build_id'] / 'frozen/include_roots'
        syntax = BUILD / 'syntax'
        syntax.mkdir()
        syntax_results = []
        for unit in host['final_compilation']['translation_units'][:2]:
            original_response = unit['response']
            assert artifact(Path(original_response['path']))['sha256'] == original_response['sha256']
            lines = Path(original_response['path']).read_text(encoding='utf-8-sig').splitlines()
            current = []
            for line in lines:
                if line == '/c' or line.startswith(('/Fo', '/sourceDependencies')):
                    continue
                line = line.replace(str(frozen / 'project'), str(PROJECT))
                line = line.replace(str(frozen / 'sdk'), str(PROJECT / 'Source/SDK_BNW_x64'))
                for index, root in enumerate(host['system_include_roots']):
                    line = line.replace(str(frozen / f'system_{index:02d}'), root)
                assert str(frozen).lower() not in line.lower(), 'Untranslated frozen include in current-source syntax check'
                current.append(line)
            current.extend(('/Zs', '/showIncludes'))
            response = syntax / (unit['translation_unit'] + '.syntax.rsp')
            response.write_text('\n'.join(current) + '\n', encoding='utf-8')
            command = [compiler, '@' + str(response)]
            began = time.monotonic()
            child = run(command, cwd=syntax, env=environment, timeout=60)
            output = (child.stdout + child.stderr).decode('mbcs', errors='replace')
            log = EVIDENCE / (unit['translation_unit'] + '.syntax.log')
            log.write_text(output, encoding='utf-8')
            item = dict(translation_unit=unit['translation_unit'], command=command,
                returncode=child.returncode, elapsed_seconds=time.monotonic()-began,
                exact_prior_response=original_response, current_response=artifact(response), log=artifact(log))
            children.append(item)
            assert child.returncode == 0 and not re.search(r'warning\s+[A-Z]+\d+|경고\s+[A-Z]+\d+', output, re.I)
            syntax_results.append(item)
        assert not list(syntax.glob('*.obj')) and not list(syntax.glob('*.exe'))
        for row in protected:
            assert artifact(Path(row['path'])) == row, 'A protected component source changed during validation'
        result = dict(schema='zerosis.original_world_hud.component_result.v1',
            status='PASS_ORIGINAL_WORLD_HUD_SOFTWARE_COMPONENT_O2_OD',
            compiler=compiler_ref, protected_inputs_unchanged=protected, modes=modes,
            actual_current_host_main_and_bitmap_window_syntax=syntax_results,
            actual_children=children, actual_native_child_count=len(children)+1,
            build_environment_child_count=1, host_or_sdk_or_window_executed=False,
            original_hud_pixels_rendered=False, real_game_visual_acceptance=False,
            direct3d_terrain_or_swapchain_calls=0, full_engine_goal_complete=False)
        write_new(EVIDENCE / 'result.json', result)
        print(json.dumps(dict(status=result['status'], modes=[m['component'] for m in modes],
                              result=str(EVIDENCE / 'result.json'))))
    except BaseException as error:
        write_new(EVIDENCE / 'failure.json', dict(status='FAIL_SOFTWARE_COMPONENT_ONLY',
            error=type(error).__name__ + ': ' + str(error), actual_children=children,
            modes_completed=modes, host_or_sdk_or_window_executed=False))
        raise


if __name__ == '__main__':
    main()
