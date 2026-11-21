"""Bounded console/Lua components and production compile-only validation."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import sys
import time

sys.dont_write_bytecode = True
PROJECT = Path(__file__).absolute().parents[3]
STAGE = Path(__file__).absolute().parent
BUILD = PROJECT / 'Build/UiPanelRepaint/current'
HOST_REPORT = PROJECT / 'evidence/ui_window_host/20261024T055841Z_974a5be57533/build_result.json'
ENCODER_REPORT = PROJECT / 'evidence/ui_snapshot_json_component/20261003T134802Z_658a13d832dd/build_result.json'
SOURCES = ('Source/Host/UiPanelRepaint.h', 'Source/Host/InteractiveUiSession.h',
    'Source/Host/InteractiveGameSession.h', 'Source/Host/InteractiveGameLoop.h',
    'Tests/ui_panel_repaint.cpp', 'Tests/ui_presentation_input.lua',
    'Tests/top_panel_scene.lua', 'Tests/unit_panel_scene.lua',
    'Tests/action_info_panel_scene.py', 'Tests/notification_panel_scene.py')
sys.path.insert(0, str(PROJECT / 'tools'))


def artifact(path):
    path = Path(path).absolute()
    before = path.stat()
    assert not before.st_file_attributes & 0x400 and path.is_file()
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    after = path.stat()
    assert (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) == (
        after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    return dict(path=str(path), bytes=after.st_size, sha256=digest)


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def execute(command, cwd, output, children, environment=None, timeout=60):
    from native_build import run
    began = time.monotonic()
    child = run(command, cwd=cwd, env=environment, timeout=timeout)
    raw = child.stdout + child.stderr
    output.write_bytes(raw)
    row = dict(command=[str(x) for x in command], returncode=child.returncode,
        elapsed_seconds=time.monotonic()-began, log=artifact(output))
    children.append(row)
    assert child.returncode == 0, 'Child failed; inspect its exact retained log'
    return raw


def native(evidence, build, children):
    from native_build import environment_for
    from collect_baseline import pe_header
    environment, compiler = environment_for(
        Path(r'C:\Program Files\Microsoft Visual Studio\2022\Community'), 'x64', build)
    compiler_ref = artifact(compiler)
    assert compiler_ref['sha256'] == '8a547dfca2d7df1b6be1e2d212132c1b3b5a661caf5b2ecce481e21b3c1860a6'
    modes = []
    for mode in ('O2', 'Od'):
        directory = build / mode
        directory.mkdir()
        exe, obj = directory / 'ui_panel_repaint.exe', directory / 'ui_panel_repaint.obj'
        dep = directory / 'sourceDependencies.json'
        flags = ['/nologo', '/std:c++14', '/EHsc', '/W4', '/WX', '/utf-8',
                 '/fp:strict', '/MT', '/' + mode]
        if mode == 'Od':
            flags.append('/RTC1')
        command = [compiler, *flags, '/I' + str(PROJECT / 'Source/Host'),
                   '/c', str(PROJECT / 'Tests/ui_panel_repaint.cpp'),
                   '/Fo' + str(obj), '/sourceDependencies', str(dep)]
        raw = execute(command, directory, evidence / (mode + '_compile.log'), children, environment)
        assert not re.search(r'warning\s+[A-Z]+\d+|경고\s+[A-Z]+\d+', raw.decode('mbcs', errors='replace'), re.I)
        inputs = read(dep)['Data']
        dependencies = [artifact(Path(x)) for x in dict.fromkeys((inputs['Source'], *inputs['Includes']))]
        assert any(Path(x['path']).name.lower() == 'uipanelrepaint.h' for x in dependencies)
        link = [str(Path(compiler).with_name('link.exe')), '/NOLOGO', '/WX', '/MACHINE:X64',
                '/SUBSYSTEM:CONSOLE', '/INCREMENTAL:NO', '/BREPRO', '/OPT:REF', '/OPT:ICF',
                '/OUT:' + str(exe), '/MAP:' + str(directory / 'ui_panel_repaint.map'), str(obj)]
        raw = execute(link, directory, evidence / (mode + '_link.log'), children, environment)
        assert not re.search(r'warning\s+[A-Z]+\d+|경고\s+[A-Z]+\d+', raw.decode('mbcs', errors='replace'), re.I)
        assert pe_header(exe)['architecture'] == 'x64'
        raw = execute([str(exe)], directory, evidence / (mode + '_run.log'), children, environment)
        lines = raw.decode('utf-8').splitlines()
        assert len(lines) == 1
        result = json.loads(lines[0])
        assert result['schema'] == 'zerosis.ui_panel_repaint_test.v1'
        assert result['status'] == 'PASS_UI_PANEL_REPAINT_COMPONENT'
        assert result['window_calls'] == 0 and not result['sdk_executed'] and not result['host_executed']
        modes.append(dict(mode=mode, executable=artifact(exe), object=artifact(obj),
            dependencies=dependencies, dependency_report=artifact(dep), result=result))

    assert artifact(HOST_REPORT)['sha256'] == '6aa2ccdb8ce1308521fc01f88fa45745153244b6931754a0b3111dc2129d1302'
    host = read(HOST_REPORT)
    unit = next(x for x in host['final_compilation']['translation_units'] if x['translation_unit'] == 'host_main')
    assert artifact(unit['response']['path'])['sha256'] == unit['response']['sha256']
    frozen = PROJECT / 'Build/UiWindowHost' / host['build_id'] / 'frozen/include_roots'
    replacements = [(str(frozen / 'project'), str(PROJECT)),
                    (str(frozen / 'sdk'), str(PROJECT / 'Source/SDK_BNW_x64'))]
    replacements.extend((str(frozen / ('system_%02d' % i)), root)
                        for i, root in enumerate(host['system_include_roots']))
    current = []
    for line in Path(unit['response']['path']).read_text(encoding='utf-8-sig').splitlines():
        if line == '/c' or line.startswith(('/Fo', '/sourceDependencies')):
            continue
        for before, after in replacements:
            line = re.sub(re.escape(before), lambda match, value=after: value, line, flags=re.I)
        assert str(frozen).lower() not in line.lower()
        current.append(line)
    current.extend(('/Zs', '/showIncludes'))
    syntax = build / 'syntax'
    syntax.mkdir()
    response = syntax / 'host_main.syntax.rsp'
    response.write_text('\n'.join(current) + '\n', encoding='utf-8')
    raw = execute([compiler, '@' + str(response)], syntax,
                  evidence / 'host_main.syntax.log', children, environment)
    text = raw.decode('mbcs', errors='replace')
    assert not re.search(r'warning\s+[A-Z]+\d+|경고\s+[A-Z]+\d+', text, re.I)
    includes = {}
    for line in text.splitlines():
        match = re.search(r'[a-zA-Z]:[\\/].*$', line)
        if match:
            path = Path(match.group().strip())
            assert path.is_file(), 'An actual compiler include is missing'
            includes[os.path.normcase(str(path))] = artifact(path)
    for relative in SOURCES[:4]:
        expected = artifact(PROJECT / relative)
        assert includes[os.path.normcase(expected['path'])] == expected
    assert not list(syntax.glob('*.obj')) and not list(syntax.glob('*.exe'))
    return dict(modes=modes, compiler=compiler_ref, environment_children=1,
        host_main_compile_only=dict(response=artifact(response), actual_includes=list(includes.values()),
            source=artifact(PROJECT / 'Source/Host/HostMain.cpp'),
            link_performed=False, host_executed=False, sdk_loaded=False, window_created=False))


def encoder():
    report = read(ENCODER_REPORT)
    assert report['status'] == 'UI_SNAPSHOT_JSON_COMPONENT_BUILT'
    path = Path(report['executable']['path'])
    assert artifact(path)['sha256'] == report['executable']['sha256'] == (
        '3030eca6e16074abf12644c2aa9460075bfed518e5a133967b14287ba0c8994b')
    assert artifact(report['lua_dll']['path'])['sha256'] == (
        '4873cded3ddf52366abc7964e3d3e10546f88e983d966be93bce3465ef85d944')
    assert artifact(PROJECT / 'Build/SharedLuaRuntime/Lua/ZeroSisLua51_x64.dll')['sha256'] == (
        '4873cded3ddf52366abc7964e3d3e10546f88e983d966be93bce3465ef85d944')
    return path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('phase', choices=('native', 'lua_input', 'top_panel', 'hud_panels'))
    parser.add_argument('--attempt', type=int, choices=(0, 1, 2), default=0)
    args = parser.parse_args()
    assert not sys.flags.optimize
    label = args.phase if not args.attempt else args.phase + '_retry%02d' % args.attempt
    if args.attempt:
        prior = args.phase if args.attempt == 1 else args.phase + '_retry%02d' % (args.attempt - 1)
        assert read(STAGE / prior / 'failure.json')['status'] == 'FAILED_OFFLINE_' + args.phase.upper()
    evidence, build = STAGE / label, BUILD / label
    assert not evidence.exists() and not build.exists(), 'Inspect an existing attempt rather than repeat it'
    scene_sources = ('Source/Host/UiScene.lua', 'Source/Presentation/UiPresentationInput.lua')
    phase_inputs = {
        'native': SOURCES[:5],
        'lua_input': (*SOURCES[:4], SOURCES[5], SOURCES[7], *scene_sources),
        'top_panel': (*SOURCES[:4], SOURCES[6], *scene_sources),
        'hud_panels': (*SOURCES[:4], *SOURCES[8:10], *scene_sources,
                       'Tests/economic_overview_scene.py'),
    }
    protected = [artifact(PROJECT / x) for x in phase_inputs[args.phase]]
    evidence.mkdir()
    build.mkdir(parents=True)
    children = []
    write(evidence / 'started.json', dict(protected_sources=protected,
        scope='Console fixture, retained Lua fixture or current HostMain compile-only; never execute Host/GameCore/window',
        source_copies_created_by_this_adapter=0, host_sdk_window_execution_allowed=False))
    try:
        if args.phase == 'native':
            result = native(evidence, build, children)
        elif args.phase == 'lua_input':
            encoder()
            command = [sys.executable, '-B', '-X', 'utf8', str(PROJECT / 'tools/verify_ui_presentation_input.py'),
                '--evidence-root', str(evidence / 'fixture'), '--build-root', str(build / 'fixture'),
                '--snapshot-json-build', str(ENCODER_REPORT)]
            raw = execute(command, PROJECT, evidence / 'fixture.log', children, timeout=120)
            summary = json.loads(raw.decode('utf-8'))
            conformance = Path(summary['evidence']) / 'conformance.json'
            report = read(conformance)
            assert report['status'] == 'PASS_UI_PRESENTATION_INPUT_COMPONENT_ONLY'
            assert report['inputs_unchanged_after_run'] and report['failure'] is None
            assert not report['gamecore_loaded'] and not report['sdk_execution'] and not report['host_window_connected']
            result = dict(summary=summary, conformance=artifact(conformance), checks=report['checks'])
        elif args.phase == 'top_panel':
            import verify_top_panel_scene as top
            top.TOP_PANEL_LUA = PROJECT / 'Source/Assets/UI/Assets/DLC/Expansion2/UI/InGame/TopPanel.lua'
            top.TOP_PANEL_XML = PROJECT / 'Source/Assets/UI/Assets/DLC/Expansion2/UI/InGame/TopPanel.xml'
            retained_top = [artifact(top.TOP_PANEL_LUA), artifact(top.TOP_PANEL_XML)]
            assert retained_top[0]['sha256'] == 'e1fa9bbeb198fb85fe71b101b6f11ac048721551be5e9de10259bbf20c167aef'
            assert retained_top[1]['sha256'] == '2325da5a03ff39daca1910089891dbd709b916b56ad4470e85c215fd12b065ad'
            report = top.verify_component(encoder(), evidence / 'fixture')
            assert report['status'] == 'PASS_TOP_PANEL_ORIGINAL_LUA_COMPONENT_ONLY'
            for before in retained_top:
                assert artifact(before['path']) == before
            result = dict(status=report['status'], result=artifact(evidence / 'fixture/result.json'),
                retained_original_top_panel=retained_top, installed_top_panel_source_override=True)
        else:
            encoder()
            sys.path.insert(0, str(PROJECT / 'Tests'))
            import action_info_panel_scene as action
            import notification_panel_scene as notification
            reports = []
            for name, module, status in (
                ('action_info', action, 'PASS_ORIGINAL_ACTION_INFO_LUA_COMPONENT'),
                ('notification', notification, 'PASS_ORIGINAL_NOTIFICATION_PANEL_LUA_COMPONENT')):
                report = module.verify_component()
                assert report['status'] == status
                write(evidence / (name + '.result.json'), report)
                reports.append(dict(name=name, fixture=artifact(module.__file__),
                    result=artifact(evidence / (name + '.result.json'))))
            result = dict(panels=reports, provider='existing shared Lua only; no GameCore',
                          python_process_loads_game_sdk=False)
        for before in protected:
            assert artifact(before['path']) == before, 'Protected test or source changed during validation'
        final = dict(schema='zerosis.hud_hover_repaint.validation.v1', status='PASS_' + args.phase.upper(),
            protected_sources=protected, children=children, result=result,
            host_sdk_or_window_executed=False, full_engine_goal_complete=False)
        write(evidence / 'result.json', final)
        print(json.dumps(dict(status=final['status'], result=str(evidence / 'result.json'))))
    except BaseException as error:
        write(evidence / 'failure.json', dict(status='FAILED_OFFLINE_' + args.phase.upper(),
            error=type(error).__name__ + ': ' + str(error), children=children,
            host_sdk_or_window_executed=False, full_engine_goal_complete=False))
        raise


if __name__ == '__main__':
    main()
