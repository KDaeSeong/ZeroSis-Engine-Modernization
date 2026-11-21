"""Finish only the compile-only checks after the preserved include-mapping failure."""
from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
import re
import sys
import time

PROJECT = Path(__file__).absolute().parents[2]
sys.path.insert(0, str(PROJECT / 'tools'))
import verify_original_world_hud as v
from native_build import environment_for, run


def read(path):
    return json.loads(path.read_bytes())


def main():
    assert not sys.flags.optimize and PROJECT == v.PROJECT
    assert not (v.EVIDENCE / 'result.json').exists()
    failure_ref = v.artifact(v.EVIDENCE / 'failure.json')
    failed = read(Path(failure_ref['path']))
    assert failed['error'] == 'AssertionError: Untranslated frozen include in current-source syntax check'
    assert len(failed['modes_completed']) == 2 and len(failed['actual_children']) == 8
    assert all(mode['component']['status'] == 'PASS_WORLD_ORIGINAL_HUD_COMPONENT'
               for mode in failed['modes_completed'])
    correction_ref = v.artifact(PROJECT /
        'evidence/original_world_hud/source_backups/verify_original_world_hud.py.sdk_path_fix.json')
    correction = read(Path(correction_ref['path']))
    assert v.artifact(Path(correction['after']['path'])) == correction['after']
    assert v.artifact(Path(correction['backup']['path'])) == correction['backup']
    old = gzip.decompress(Path(correction['backup']['path']).read_bytes())
    assert hashlib.sha256(old).hexdigest() == correction['before']['sha256']
    started = read(v.EVIDENCE / 'started.json')
    for row in started['protected_inputs']:
        if Path(row['path']) == Path(v.__file__).absolute():
            assert row == correction['before']
        else:
            assert v.artifact(Path(row['path'])) == row
    protected = [v.artifact(path) for path in v.PROTECTED]
    envdir = v.BUILD / 'syntax_environment'
    assert not envdir.exists()
    environment, compiler = environment_for(
        Path(r'C:\Program Files\Microsoft Visual Studio\2022\Community'), 'x64', envdir)
    assert v.artifact(Path(compiler))['sha256'] == (
        '8a547dfca2d7df1b6be1e2d212132c1b3b5a661caf5b2ecce481e21b3c1860a6')
    host_report = PROJECT / 'evidence/ui_window_host/20261024T042219Z_e6399c82ee5c/build_result.json'
    assert v.artifact(host_report)['sha256'] == (
        '8746bbe6614cc206e6fa87a1fb62b0f636a160e2dcb76e0a15214aad93d09300')
    host = read(host_report)
    frozen = PROJECT / 'Build/UiWindowHost' / host['build_id'] / 'frozen/include_roots'
    syntax = v.BUILD / 'syntax'
    assert syntax.is_dir() and not list(syntax.iterdir())
    items = []
    for unit in host['final_compilation']['translation_units'][:2]:
        original_response = unit['response']
        assert v.artifact(Path(original_response['path']))['sha256'] == original_response['sha256']
        current = []
        for line in Path(original_response['path']).read_text(encoding='utf-8-sig').splitlines():
            if line == '/c' or line.startswith(('/Fo', '/sourceDependencies')):
                continue
            line = line.replace(str(frozen / 'project'), str(PROJECT))
            line = line.replace(str(frozen / 'sdk'), str(PROJECT / 'Source/SDK_BNW_x64'))
            for index, root in enumerate(host['system_include_roots']):
                line = line.replace(str(frozen / f'system_{index:02d}'), root)
            assert str(frozen).lower() not in line.lower()
            current.append(line)
        current.extend(('/Zs', '/showIncludes'))
        response = syntax / (unit['translation_unit'] + '.syntax.rsp')
        response.write_text('\n'.join(current) + '\n', encoding='utf-8')
        command = [compiler, '@' + str(response)]
        began = time.monotonic()
        child = run(command, cwd=syntax, env=environment, timeout=60)
        output = (child.stdout + child.stderr).decode('mbcs', errors='replace')
        log = v.EVIDENCE / (unit['translation_unit'] + '.syntax.log')
        log.write_text(output, encoding='utf-8')
        item = dict(translation_unit=unit['translation_unit'], command=command,
            returncode=child.returncode, elapsed_seconds=time.monotonic()-began,
            exact_prior_response=original_response, current_response=v.artifact(response), log=v.artifact(log))
        items.append(item)
        v.write_new(v.EVIDENCE / (unit['translation_unit'] + '.syntax.json'), item)
        assert child.returncode == 0 and not re.search(r'warning\s+[A-Z]+\d+|경고\s+[A-Z]+\d+', output, re.I)
    assert not list(syntax.glob('*.obj')) and not list(syntax.glob('*.exe'))
    for row in protected:
        assert v.artifact(Path(row['path'])) == row
    for mode in failed['modes_completed']:
        assert v.artifact(Path(mode['executable']['path']))['sha256'] == mode['executable']['sha256']
        assert not (Path(mode['executable']['path']).parent / 'temporary_pixels').exists()
    result = dict(schema='zerosis.original_world_hud.component_result.v1',
        status='PASS_ORIGINAL_WORLD_HUD_SOFTWARE_COMPONENT_O2_OD',
        compiler=v.artifact(Path(compiler)), protected_inputs_unchanged=protected,
        preserved_failure=failure_ref, validator_include_mapping_correction=correction_ref,
        completion_adapter=v.artifact(Path(__file__).absolute()),
        modes=failed['modes_completed'], actual_current_host_main_and_bitmap_window_syntax=items,
        actual_children=failed['actual_children']+items, actual_native_child_count=12,
        build_environment_child_count=2, component_modes_reexecuted=False,
        host_or_sdk_or_window_executed=False, original_hud_pixels_rendered=False,
        real_game_visual_acceptance=False, direct3d_terrain_or_swapchain_calls=0,
        full_engine_goal_complete=False)
    v.write_new(v.EVIDENCE / 'result.json', result)
    print(json.dumps(dict(status=result['status'], modes=[m['mode'] for m in result['modes']],
        syntax_units=[i['translation_unit'] for i in items], host_or_sdk_or_window_executed=False)))


if __name__ == '__main__':
    main()
