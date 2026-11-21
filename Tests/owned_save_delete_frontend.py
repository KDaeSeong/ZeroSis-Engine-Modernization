"""Compile real original-Lua delete states through the frozen Python UI driver.

The catalog/deletion service is the scene fixture's in-memory implementation.
Only CPU renderer Python children and the approved Lua provider are used; no
Host, GameCore, native window, retail configuration or user archive is opened.
"""
from contextlib import closing
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import uuid
from unittest.mock import patch

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / 'Tests'))
sys.path.insert(0, str(PROJECT / 'tools'))
import interactive_ui_driver as driver
from load_menu_driver import remove_generated
import owned_save_delete_scene as scene
import pull_down_compositor as packets


def artifact(path):
    return {'path': str(path), 'bytes': path.stat().st_size,
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    evidence = PROJECT / 'evidence/save_delete/source_contract/frontend' / (
        datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ_') + uuid.uuid4().hex[:12])
    evidence.mkdir(parents=True, exist_ok=False)
    build = (PROJECT / 'Build').resolve(strict=True)
    directory = Path(tempfile.mkdtemp(prefix='pull-down-compositor-load-driver-owned-delete-', dir=build)).resolve(strict=True)
    report = {'schema': 'zerosis.owned_save_delete_frontend.v1', 'status': 'IN_PROGRESS',
              'utc': datetime.now(timezone.utc).isoformat(), 'states': [], 'rejected': [],
              'python_renderer_children': [], 'host_gamecore_or_windows_executed': False,
              'actual_user_or_fixture_archive_deletes': 0,
              'scope': 'Original Lua callbacks, independent mock catalog, real frozen CPU renderer and driver packet validation',
              'asset_provenance_kind': 'Explicit component fixture, not a complete prepared Host UI catalog'}
    result_path = evidence / 'result.json'

    def publish():
        result_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf8')

    publish()
    try:
        packets.suppress_own_fault_ui()
        captures = scene.verify_component(cases=('supported',), include_snapshot=True)
        report['scene_checks'] = captures['checks']
        report['original_sources_unchanged'] = captures['original_sources_unchanged']
        report['scene_source_sha256'] = captures['source_sha256']['scene']
        runtime = directory / 'runtime'
        session = runtime / 'sessions/component'
        support = runtime / 'interactive_ui_support'
        tools, assets = support / 'tools', support / 'assets'
        session.mkdir(parents=True)
        tools.mkdir(parents=True)
        assets.mkdir()
        sources = {name: artifact(PROJECT / 'tools' / name) for name in driver.SUPPORT}
        for name in driver.SUPPORT:
            shutil.copy2(Path(sources[name]['path']), tools / name)
        icons = assets / 'inline_icons.json'
        shutil.copy2(PROJECT / 'evidence/ui_popup/assets/inline_icons.json', icons)
        prep = assets / 'prepared.json'
        prep.write_text(json.dumps({'inline_icon_catalog': artifact(icons),
            'scope': 'Explicit CPU driver component fixture; no new native Host/catalog embedding claimed.'}), encoding='utf8')
        manifest = support / 'support_manifest.json'
        manifest.write_text(json.dumps({'tools': {name: artifact(tools / name) for name in driver.SUPPORT},
            'inline_icons': artifact(icons), 'asset_preparation_provenance': artifact(prep)}), encoding='utf8')
        manifest_sha = artifact(manifest)['sha256']
        with closing(sqlite3.connect(session / 'rules.db')) as connection, connection:
            connection.execute('CREATE TABLE Colors(Type TEXT PRIMARY KEY, Red REAL, Green REAL, Blue REAL, Alpha REAL)')
            connection.execute("INSERT INTO Colors VALUES ('COLOR_WHITE',1,1,1,1)")
        actual_run = driver.subprocess.run

        def guarded_run(command, **kwargs):
            args = [str(value) for value in command]
            if (args[:5] != [sys.executable, '-B', '-X', 'utf8', str(tools / 'render_ui_popup.py')]
                    or '--prepare' not in args or '--context' not in args
                    or args[args.index('--context') + 1] not in ('save-menu', 'load-menu')):
                raise AssertionError('Only the exact frozen Python CPU renderer may run')
            report['python_renderer_children'].append({'script': args[4], 'context': args[args.index('--context') + 1]})
            return actual_run(command, **kwargs)

        sequence = 0
        with patch.object(driver.subprocess, 'run', guarded_run):
            for menu, context in (('SaveMenu', 'save-menu'), ('LoadMenu', 'load-menu')):
                states = captures['snapshots'][menu]['supported']
                stages = ('opened', 'eligible', 'confirmation', 'cancelled', 'refreshed', 'final', 'closed')
                if set(states) != set(stages):
                    raise AssertionError('Both original menus must expose exactly the seven captured deletion states')
                for stage in stages:
                    snapshot = states[stage]
                    sequence += 1
                    original = copy.deepcopy(snapshot)
                    source_path, folder = session / f'play-ui-{sequence}.json', session / f'play-ui-{sequence}'
                    source_path.write_text(json.dumps(snapshot, ensure_ascii=False), encoding='utf8')
                    line = f'INTERACTIVE_UI_SCENE_REQUEST={sequence}|{context}|{source_path}|{folder}'
                    prepared = driver.prepare_request(line, runtime=runtime, tools_dir=tools, icons_source=icons,
                        support_manifest=manifest, support_manifest_sha256=manifest_sha)
                    packet = Path(prepared['packet']['path']).read_bytes()
                    parsed = packets.packet_sections(packet, folder)
                    expected = [(row['key'], *packets.captured_clip_xyxy(row)) for row in snapshot['inputTargets']]
                    if parsed['hits'] != [packets.wire_rectangle(row) for row in expected] or snapshot != original:
                        raise AssertionError('Actual packet changed original retained hits or the source capture')
                    metadata = snapshot['saveMenu' if menu == 'SaveMenu' else 'loadMenu']
                    if not metadata['localDeleteBackendBound']:
                        raise AssertionError('Supported deletion fixture lost its actual bound capability')
                    report['states'].append({'menu': menu, 'stage': stage, 'sequence': sequence,
                        'closed': snapshot['active'] is False, 'hit_count': len(parsed['hits']),
                        'sprites': parsed['sprites'], 'delete_armed': metadata['deleteConfirmationArmed'],
                        'actual_driver_packet_proof': True, 'packet_sha256': hashlib.sha256(packet).hexdigest()})
                    publish()
        if len(report['states']) != 14 or len(report['python_renderer_children']) != 14:
            raise AssertionError('Both original menus must retain all seven actual captured states')
        for name, source in sources.items():
            if artifact(PROJECT / 'tools' / name) != source or artifact(tools / name)['sha256'] != source['sha256']:
                raise AssertionError('A current or frozen renderer input changed')
        report['support_sources'] = sources
        report['status'] = 'PASS_ORIGINAL_DELETE_STATES_THROUGH_FROZEN_CPU_DRIVER_ONLY'
    except Exception as error:
        report.update(status='FAIL', error=type(error).__name__ + ': ' + str(error))
        raise
    finally:
        report['cleanup'] = remove_generated(directory, build, evidence / 'cleanup.json')
        publish()
    print(json.dumps({'status': report['status'], 'states': len(report['states']),
                      'python_renderer_children': len(report['python_renderer_children']),
                      'cleanup': report['cleanup'], 'report': str(result_path)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
