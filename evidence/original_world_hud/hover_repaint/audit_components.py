"""Seal current component evidence without executing native code or a window."""
from __future__ import annotations

from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path

STAGE = Path(__file__).absolute().parent
PROJECT = STAGE.parents[2]


def artifact(path):
    path = Path(os.path.abspath(path))
    before = path.lstat()
    assert path.is_file() and not before.st_file_attributes & 0x400, path
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    after = path.lstat()
    assert (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) == (
        after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns), path
    return dict(path=str(path), bytes=after.st_size, sha256=digest)


def read(path):
    return json.loads(Path(path).read_bytes())


def verify(row):
    current = artifact(row['path'])
    assert all(current[key] == row[key] for key in ('bytes', 'sha256')), row['path']
    return current


def main():
    assert __debug__
    target = STAGE / 'component_audit.json'
    assert not target.exists(), 'Do not replay publication'
    reports = {}
    references = {}
    for phase, status in (
        ('native_retry01', 'PASS_NATIVE'), ('lua_input_retry01', 'PASS_LUA_INPUT'),
        ('top_panel', 'PASS_TOP_PANEL'), ('hud_panels', 'PASS_HUD_PANELS')):
        path = STAGE / phase / 'result.json'
        references[phase] = artifact(path)
        report = read(path)
        assert report['status'] == status
        assert not report['host_sdk_or_window_executed']
        assert not report['full_engine_goal_complete']
        reports[phase] = report

    native = reports['native_retry01']
    # Earlier unrelated Lua fixture edits do not invalidate actual C++ inputs.
    # Verify the compiler's real dependency lists and the five native sources.
    for row in native['protected_sources'][:5]:
        verify(row)
    dependencies = {}
    for mode in native['result']['modes']:
        assert mode['result']['status'] == 'PASS_UI_PANEL_REPAINT_COMPONENT'
        assert (mode['result']['cases'], mode['result']['checks']) == (27, 150)
        verify(mode['executable'])
        verify(mode['dependency_report'])
        for row in mode['dependencies']:
            current = verify(row)
            dependencies[current['path'].casefold()] = current
    syntax = native['result']['host_main_compile_only']
    assert not syntax['link_performed'] and not syntax['host_executed']
    assert not syntax['sdk_loaded'] and not syntax['window_created']
    verify(syntax['response'])
    verify(syntax['source'])
    syntax_paths = set()
    for row in syntax['actual_includes']:
        current = verify(row)
        syntax_paths.add(current['path'].casefold())
        dependencies[current['path'].casefold()] = current
    production = [verify(row) for row in native['protected_sources'][:4]]
    assert all(row['path'].casefold() in syntax_paths for row in production)

    for phase in ('lua_input_retry01', 'top_panel', 'hud_panels'):
        for row in reports[phase]['protected_sources']:
            verify(row)
    lua = reports['lua_input_retry01']['result']
    verify(lua['conformance'])
    conformance = read(lua['conformance']['path'])
    assert all(lua['checks'].values()) and conformance['inputs_unchanged_after_run']
    assert not conformance['gamecore_loaded'] and not conformance['sdk_execution']
    assert not conformance['host_window_connected']
    top = reports['top_panel']['result']
    verify(top['result'])
    for row in top['retained_original_top_panel']:
        verify(row)
    panels = []
    for panel in reports['hud_panels']['result']['panels']:
        verify(panel['fixture'])
        verify(panel['result'])
        value = read(panel['result']['path'])
        for name in ('fixedClockKeyZeroUnchanged', 'fixedClockRepeatedHoverUnchanged',
                     'hoverLeaveChangesSnapshot'):
            assert value[name] is True
        panels.append(dict(name=panel['name'], checks=value['checks'],
                           result=panel['result']))

    requirements = read(STAGE / 'requirements.json')
    backups = []
    for row in requirements['baseline_sources']:
        verify(row['backup'])
        raw = gzip.decompress(Path(row['backup']['path']).read_bytes())
        assert len(raw) == row['before']['bytes']
        assert hashlib.sha256(raw).hexdigest() == row['before']['sha256']
        backups.append(dict(before=row['before'], backup=row['backup']))
    extra = read(STAGE / 'additional_panel_test_scope.json')
    for row in extra['before']:
        backup = artifact(row['backup_path'])
        assert (backup['bytes'], backup['sha256']) == (row['backup_bytes'], row['backup_sha256'])
        raw = gzip.decompress(Path(backup['path']).read_bytes())
        assert (len(raw), hashlib.sha256(raw).hexdigest()) == (row['bytes'], row['sha256'])
        backups.append(dict(before={key: row[key] for key in ('path', 'bytes', 'sha256')}, backup=backup))
    setup = read(STAGE / 'verification_setup_fix.json')
    verify(setup['backup'])
    raw = gzip.decompress(Path(setup['backup']['path']).read_bytes())
    assert (len(raw), hashlib.sha256(raw).hexdigest()) == (setup['before']['bytes'], setup['before']['sha256'])
    backups.append(dict(before=setup['before'], backup=setup['backup']))

    cleanup = read(STAGE / 'cleanup_result.json')
    assert cleanup['status'] == 'PASS_EXACT_FOUR_GENERATED_FILES_RETIRED'
    assert cleanup['error'] is None
    for row in cleanup['deleted']:
        assert not Path(row['path']).exists(), row['path']
    plan = read(STAGE / 'cleanup_plan.json')
    for row in plan['protected']:
        verify(row)
        info = Path(row['path']).lstat()
        assert [info.st_dev, info.st_ino] == row['file_identity']
        assert info.st_mtime_ns == row['mtime_ns']
        assert info.st_file_attributes == row['attrs'] and info.st_nlink == row['nlinks']

    data = dict(
        schema='zerosis.hud_hover_repaint.component_audit.v1',
        utc=datetime.now(timezone.utc).isoformat(),
        status='PASS_CURRENT_SOURCE_COMPONENTS_AND_HOSTMAIN_SYNTAX_LINK_PENDING',
        previous_goal_turn_classification='no_progress',
        previous_goal_turn_reason='Read-only progress-table response; no implementation or validation was advanced.',
        current_goal_turn_classification='progress',
        requirements=artifact(STAGE / 'requirements.json'),
        production_sources=production,
        test_sources=[artifact(PROJECT / name) for name in (
            'Tests/ui_panel_repaint.cpp', 'Tests/ui_presentation_input.lua',
            'Tests/top_panel_scene.lua', 'Tests/unit_panel_scene.lua',
            'Tests/action_info_panel_scene.py', 'Tests/notification_panel_scene.py')],
        changed_verification_tool=artifact(PROJECT / 'tools/verify_ui_presentation_input.py'),
        verifier=artifact(STAGE / 'verify.py'),
        phase_reports=references,
        native_modes=2, cases_per_native_mode=27, checks_per_native_mode=150,
        actual_cpp_dependency_files_rehashed=len(dependencies),
        hostmain_actual_include_count=len(syntax['actual_includes']),
        hostmain_source=syntax['source'], hostmain_compile_only=True,
        full_host_object_compilation_or_link_performed=False,
        input_lua_fixture_count=4, top_panel_lua_fixture_count=1,
        additional_hud_lua_fixtures=panels,
        total_lua_fixture_count=7,
        lua_summary_checks=len(lua['checks']),
        backup_roundtrips=backups,
        component_cleanup=artifact(STAGE / 'cleanup_result.json'),
        retired_allocation_bytes=cleanup['allocated_bytes'],
        protected_runtime_save_source_and_component_files_rehashed=len(plan['protected']),
        current_prepared_runtime_contains_new_hover_fix=False,
        screen_verification_deferred=True, host_sdk_or_window_executed=False,
        save_wire_or_mod_schema_changed=False, full_engine_goal_complete=False,
        remaining=['Compile and statically attest the full current Host executable.',
                   'Prepare its isolated runtime using shared immutable inputs.',
                   'Verify actual input, turns and save restore when the human resumes screen verification.'])
    with target.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps(dict(status=data['status'], audit=artifact(target),
                          actual_cpp_inputs_rehashed=len(dependencies), lua_fixtures=7)))


if __name__ == '__main__':
    main()
