"""Compile seven actual original-Lua overwrite states through the CPU driver.

Unchanged support and icon inputs are hardlinked from the retained R6 runtime.
Only the current changed compositor is copied from mutable source. No Host,
GameCore, native window, runtime database clone or user archive is involved.
"""
from contextlib import closing
import copy
from datetime import datetime, timezone
import hashlib
import json
import os
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
import owned_save_overwrite_scene as scene
import pull_down_compositor as packets

R6 = '20261016T111333Z_1c377d9577e6'
STATES = (('selected', 'selected'), ('selected', 'commit-confirmation'), ('entered', 'entered-confirmation'),
          ('selected', 'cancelled'), ('native-fault', 'faulted'), ('selected', 'closed'), ('unsupported', 'selected'))


def artifact(path):
    return {'path': str(path), 'bytes': path.stat().st_size,
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    evidence = PROJECT / 'evidence/save_overwrite/source_contract/frontend' / (
        datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ_') + uuid.uuid4().hex[:12])
    evidence.mkdir(parents=True, exist_ok=False)
    build = (PROJECT / 'Build').resolve(strict=True)
    directory = Path(tempfile.mkdtemp(prefix='pull-down-compositor-load-driver-owned-overwrite-', dir=build)).resolve(strict=True)
    report = {'schema': 'zerosis.owned_save_overwrite_frontend.v1', 'status': 'IN_PROGRESS',
              'utc': datetime.now(timezone.utc).isoformat(), 'states': [], 'python_renderer_children': [],
              'reused_inputs': [], 'host_gamecore_or_windows_executed': False,
              'real_archive_writes': 0, 'real_archive_deletes': 0,
              'scope': 'Original Lua callbacks, independent in-memory queue, exact CPU renderer/driver packet validation',
              'asset_provenance_kind': 'Explicit component fixture; not a regenerated or linked native Host catalog'}
    result_path = evidence / 'result.json'

    def publish():
        result_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf8')

    publish()
    try:
        packets.suppress_own_fault_ui()
        captures = scene.verify_component(include_snapshot=True)
        report['scene_checks'] = captures['checks']
        report['coverage_mapping'] = captures['coverage_mapping']
        report['scene_source_sha256'] = captures['source_sha256']
        report['scene_style_cleanup'] = captures['temporary_cleanup']
        runtime = directory / 'runtime'
        session = runtime / 'sessions/component'
        support = runtime / 'interactive_ui_support'
        tools, assets = support / 'tools', support / 'assets'
        session.mkdir(parents=True)
        tools.mkdir(parents=True)
        assets.mkdir()
        old_support = PROJECT / 'Build/InteractiveGameRuntime' / R6 / 'interactive_ui_support'
        donor_manifest = old_support / 'support_manifest.json'
        old_manifest = json.loads(donor_manifest.read_text(encoding='utf8'))
        report['donor_support_manifest'] = artifact(donor_manifest)
        sources = {name: artifact(PROJECT / 'tools' / name) for name in driver.SUPPORT}
        for name in driver.SUPPORT:
            target = tools / name
            if name == 'ui_pixel_scene.py':
                shutil.copy2(PROJECT / 'tools' / name, target)
                if target.stat().st_ino == (PROJECT / 'tools' / name).stat().st_ino:
                    raise AssertionError('Mutable current compositor was hardlinked')
                report['changed_source_frozen_copy'] = artifact(target)
            else:
                source = old_support / 'tools' / name
                row = artifact(source)
                if row['sha256'] != old_manifest['tools'][name]['sha256'] or row['sha256'] != sources[name]['sha256']:
                    raise AssertionError('R6 unchanged support differs from its sealed/current bytes')
                os.link(source, target)
                if (source.stat().st_dev, source.stat().st_ino) != (target.stat().st_dev, target.stat().st_ino):
                    raise AssertionError('Support reuse did not preserve one NTFS identity')
                report['reused_inputs'].append({'source': row, 'target': str(target), 'materialization': 'hardlink',
                                                'file_identity': [source.stat().st_dev, source.stat().st_ino]})
        icon_source = old_support / 'assets/inline_icons.json'
        if artifact(icon_source)['sha256'] != old_manifest['inline_icons']['sha256']:
            raise AssertionError('R6 icon catalog differs from its sealed bytes')
        icons = assets / 'inline_icons.json'
        os.link(icon_source, icons)
        report['reused_inputs'].append({'source': artifact(icon_source), 'target': str(icons), 'materialization': 'hardlink',
                                       'file_identity': [icon_source.stat().st_dev, icon_source.stat().st_ino]})
        prep = assets / 'prepared.json'
        prep.write_text(json.dumps({'inline_icon_catalog': artifact(icons),
            'scope': 'Explicit original-Lua overwrite CPU fixture; no new native embedding claimed.'}), encoding='utf8')
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
                    or args[args.index('--context') + 1] != 'save-menu'):
                raise AssertionError('Only the exact frozen Python SaveMenu CPU renderer may run')
            report['python_renderer_children'].append({'script': args[4], 'context': 'save-menu'})
            return actual_run(command, **kwargs)

        with patch.object(driver.subprocess, 'run', guarded_run):
            for sequence, (case, stage) in enumerate(STATES, 1):
                snapshot = captures['snapshots'][case][stage]
                original = copy.deepcopy(snapshot)
                source_path, folder = session / f'play-ui-{sequence}.json', session / f'play-ui-{sequence}'
                source_path.write_text(json.dumps(snapshot, ensure_ascii=False), encoding='utf8')
                line = f'INTERACTIVE_UI_SCENE_REQUEST={sequence}|save-menu|{source_path}|{folder}'
                prepared = driver.prepare_request(line, runtime=runtime, tools_dir=tools, icons_source=icons,
                    support_manifest=manifest, support_manifest_sha256=manifest_sha)
                packet = Path(prepared['packet']['path']).read_bytes()
                parsed = packets.packet_sections(packet, folder)
                expected = [(row['key'], *packets.captured_clip_xyxy(row)) for row in snapshot['inputTargets']]
                if parsed['hits'] != [packets.wire_rectangle(row) for row in expected] or snapshot != original:
                    raise AssertionError('Actual CPU packet changed retained input or the captured snapshot')
                metadata = snapshot['saveMenu']
                if metadata['overwriteConfirmationArmed']:
                    if metadata['confirmationOp'] != 'overwrite' or metadata['textInputEnabled']:
                        raise AssertionError('Armed overwrite did not preserve modal text-input blocking')
                    if any(row.get('id') in ('NameBox', 'SaveButton', 'Delete', 'Button') for row in snapshot['inputTargets']):
                        raise AssertionError('Original confirmation leaked background controls into the actual packet')
                if snapshot['active'] is False and parsed['hits']:
                    raise AssertionError('Closed SaveMenu retained CPU packet input')
                report['states'].append({'case': case, 'stage': stage, 'sequence': sequence,
                    'closed': snapshot['active'] is False, 'hit_count': len(parsed['hits']), 'sprites': parsed['sprites'],
                    'overwrite_bound': metadata['localOverwriteBackendBound'], 'overwrite_armed': metadata['overwriteConfirmationArmed'],
                    'confirmation_op': metadata['confirmationOp'], 'actual_driver_packet_proof': True,
                    'packet_sha256': hashlib.sha256(packet).hexdigest()})
                publish()
        if len(report['states']) != 7 or len(report['python_renderer_children']) != 7:
            raise AssertionError('All seven approved actual CPU renderer states are required')
        for name, source in sources.items():
            if artifact(PROJECT / 'tools' / name) != source or artifact(tools / name)['sha256'] != source['sha256']:
                raise AssertionError('Current or frozen renderer input changed')
        for row in report['reused_inputs']:
            source = Path(row['source']['path'])
            if artifact(source) != row['source'] or [source.stat().st_dev, source.stat().st_ino] != row['file_identity']:
                raise AssertionError('Retained R6 input changed while reused')
        if artifact(donor_manifest) != report['donor_support_manifest']:
            raise AssertionError('R6 donor manifest changed')
        report['support_sources'] = sources
        report['status'] = 'PASS_ORIGINAL_OVERWRITE_STATES_THROUGH_FROZEN_CPU_DRIVER_ONLY'
    except Exception as error:
        report.update(status='FAIL', error=type(error).__name__ + ': ' + str(error))
        raise
    finally:
        report['cleanup'] = remove_generated(directory, build, evidence / 'cleanup.json')
        publish()
    print(json.dumps({'status': report['status'], 'states': len(report['states']),
                      'python_renderer_children': len(report['python_renderer_children']),
                      'reused_inputs': len(report['reused_inputs']), 'cleanup': report['cleanup'],
                      'report': str(result_path)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
