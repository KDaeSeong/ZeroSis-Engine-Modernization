"""Verify the real Python LoadMenu handshake with sealed component snapshots.

Only the source-bound CPU packet preparer is spawned. The rules database is an
explicit small SQL fixture; no Host, GameCore, HWND, native renderer or gameplay
is executed. Existing immutable Lua captures are reused rather than regenerated.
"""
from __future__ import annotations

import ast
import argparse
import copy
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import sqlite3
import stat
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

PROJECT = Path(__file__).absolute().parents[1]
sys.path.insert(0, str(PROJECT / 'Tests'))
sys.path.insert(0, str(PROJECT / 'tools'))

import interactive_ui_driver as driver
import render_ui_popup
from game_menu_renderer import GameMenuRendererTests, packet_records
from action_info_panel_renderer import ActionInfoPanelTests
from pull_down_compositor import suppress_own_fault_ui

EVIDENCE = PROJECT / 'evidence/load_menu/linked_candidate'
CAPTURES = PROJECT / 'evidence/load_menu/native_handoff/composition_snapshots.json'
BEFORE = EVIDENCE / 'source_before/interactive_ui_driver.py.txt'


def artifact(path: Path) -> dict:
    data = path.read_bytes()
    return {'path': str(path), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def function_source(text: str, name: str) -> str:
    tree = ast.parse(text)
    matches = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name]
    if len(matches) != 1:
        raise AssertionError('Expected one exact Python production function: ' + name)
    return ast.get_source_segment(text, matches[0])


def wire_regions(rows: list) -> list:
    return [[row[0], *struct.unpack('<4f', struct.pack('<4f', *row[1:]))] for row in rows]


def remove_generated(directory: Path, build: Path, receipt: Path) -> dict:
    absolute = directory.resolve(strict=True)
    if absolute.parent != build or not absolute.name.startswith('pull-down-compositor-load-driver-'):
        raise RuntimeError('Driver cleanup target escaped its exact owned Build directory')
    paths = list(absolute.rglob('*'))
    for path in [*absolute.parents, absolute, *paths]:
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise RuntimeError('Driver cleanup encountered a reparse point')
    files = []
    for path in sorted(paths):
        info = path.lstat()
        if stat.S_ISREG(info.st_mode):
            files.append({**artifact(path), 'file_identity': [info.st_dev, info.st_ino],
                          'link_count': info.st_nlink, 'result': 'INVENTORIED'})
    record = {'schema': 'ZEROSIS_LOAD_MENU_DRIVER_OWN_CLEANUP_V1', 'status': 'INVENTORIED',
              'directory': str(absolute), 'files': files,
              'logical_bytes_removed': 0, 'physical_allocation_or_volume_free_space_measured': False}

    def publish():
        receipt.write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    if os.path.lexists(receipt):
        raise RuntimeError('Refusing to overwrite a driver cleanup receipt')
    publish()
    try:
        for row in files:
            path = Path(row['path'])
            info = path.lstat()
            if ([info.st_dev, info.st_ino] != row['file_identity'] or
                    artifact(path) != {key: row[key] for key in ('path', 'bytes', 'sha256')}):
                raise RuntimeError('Driver cleanup input changed after its receipt')
            path.unlink()
            row['result'] = 'REMOVED_ABSENT'
            record['logical_bytes_removed'] += row['bytes']
        for path in sorted([path for path in paths if path.is_dir()], key=lambda p: len(p.parts), reverse=True):
            path.rmdir()
        absolute.rmdir()
        record['status'] = 'COMPLETE'
        record['directory_absent'] = not absolute.exists()
    except Exception as exc:
        record.update(status='PARTIAL', error=str(exc))
        raise
    finally:
        record['file_count'] = len(files)
        publish()
    return {key: record[key] for key in ('status', 'directory', 'directory_absent', 'file_count', 'logical_bytes_removed')} | {'receipt': artifact(receipt)}


def verify_component(helper_proof: Path | None = None) -> dict:
    build = (PROJECT / 'Build').resolve(strict=True)
    for path in (PROJECT / 'tools/interactive_ui_driver.py', CAPTURES, BEFORE):
        path.resolve(strict=True)
    identifier = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '_' + secrets.token_hex(6)
    evidence = EVIDENCE / 'driver' / identifier
    evidence.mkdir(parents=True, exist_ok=False)
    inputs = {name: PROJECT / 'tools' / name for name in driver.SUPPORT}
    inputs.update(captures=CAPTURES, historical_driver=BEFORE, driver_test=Path(__file__),
                  game_protocol_test=PROJECT / 'Tests/game_menu_renderer.py',
                  action_protocol_test=PROJECT / 'Tests/action_info_panel_renderer.py',
                  fault_helper=PROJECT / 'Tests/pull_down_compositor.py')
    before = {name: artifact(path) for name, path in inputs.items()}
    capture = json.loads(CAPTURES.read_text(encoding='utf-8'))
    producer_guard = {}
    for name, row in capture['production_sources'].items():
        path = Path(row['path'])
        current = artifact(path)
        if current != row:
            if name != 'preparer':
                raise AssertionError('Captured original Lua producer changed: ' + name)
            preserved = EVIDENCE / 'source_before/prepare_ui_popup_assets.py.txt'
            historical = artifact(preserved)
            if (historical['sha256'], historical['bytes']) != (row['sha256'], row['bytes']):
                raise AssertionError('Historical snapshot preparer bytes are not preserved exactly')
            old_text, current_text = preserved.read_text(encoding='utf-8'), path.read_text(encoding='utf-8')
            ast_checks = {}
            for function in ('load_menu_control_tree', 'attach_load_menu_control_defaults', 'game_menu_control_tree'):
                old_ast = ast.dump(ast.parse(function_source(old_text, function)), include_attributes=False)
                current_ast = ast.dump(ast.parse(function_source(current_text, function)), include_attributes=False)
                if old_ast != current_ast:
                    raise AssertionError('Historical snapshot-producing function changed: ' + function)
                ast_checks[function] = hashlib.sha256(current_ast.encode('utf-8')).hexdigest()
            if helper_proof is None:
                raise AssertionError('Moved checkbox observer requires its separate direct equivalence receipt')
            proof_path = helper_proof.resolve(strict=True)
            if not proof_path.is_relative_to(EVIDENCE.resolve(strict=True)):
                raise AssertionError('Checkbox observer equivalence receipt escaped the current candidate evidence')
            proof = json.loads(proof_path.read_text(encoding='utf-8'))
            if (not str(proof.get('status', '')).startswith('PASS') or
                    proof.get('complete_observed_metadata_equal') is not True or
                    proof.get('public_api_reexport_is_codec_function') is not True or
                    proof.get('original_capture_producer_relabelled') is not False):
                raise AssertionError('Checkbox observer direct equivalence receipt did not pass')
            for source_name in ('prepare_ui_popup_assets.py', 'ui_pixel_scene.py', 'civ5_ui_assets.py'):
                observed = artifact(PROJECT / 'tools' / source_name)
                if proof.get('sources', {}).get(source_name) != observed:
                    raise AssertionError('Checkbox observer equivalence source changed: ' + source_name)
            inputs['historical_preparer'] = preserved
            before['historical_preparer'] = historical
            inputs['helper_equivalence_proof'] = proof_path
            before['helper_equivalence_proof'] = artifact(proof_path)
            producer_guard[name] = {'captured_producer': row, 'preserved_historical_bytes': historical,
                                    'current_producer': current, 'unchanged_capture_function_asts': ast_checks,
                                    'helper_equivalence_receipt': before['helper_equivalence_proof'],
                                    'capture_metadata_rewritten': False}
        else:
            producer_guard[name] = {'captured_producer': row, 'current_bytes_match': True}
        inputs['captured_' + name] = path
        before['captured_' + name] = current
    directory = Path(tempfile.mkdtemp(prefix='pull-down-compositor-load-driver-', dir=build)).resolve(strict=True)
    fault = suppress_own_fault_ui()
    checks, rejected, prepared, launches = 0, [], [], []
    report = {'schema': 'ZEROSIS_LOAD_MENU_PYTHON_DRIVER_COMPONENT_V1', 'status': 'IN_PROGRESS',
              'inputs_before': before, 'fault_ui_suppression': fault,
              'actual_host_or_gamecore_executed': False, 'actual_hwnd_or_native_renderer_created': False,
              'retail_saves_or_mods_accessed': False, 'installed_static_ui_assets_read_only': True,
              'snapshot_fixture_scope': capture['modal_state_scope'],
              'capture_producer_guard': producer_guard,
              'rules_database_is_explicit_sql_fixture': True,
              'scope': 'Real driver parser/prepare_request/proof validator with current CPU render_ui_popup --prepare and immutable original-Lua component captures. No SDK invocation, Host drive loop, native renderer or gameplay.'}
    destination = evidence / 'result.json'

    def checkpoint():
        destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    def check(condition, message):
        nonlocal checks
        if not condition:
            raise AssertionError(message)
        checks += 1

    def reject(name, operation):
        try:
            operation()
        except (RuntimeError, ValueError, AssertionError) as exc:
            rejected.append({'case': name, 'type': type(exc).__name__, 'message': str(exc)})
            check(True, name)
        else:
            raise AssertionError('Invalid driver contract accepted: ' + name)

    checkpoint()
    error = None
    try:
        text, old = inputs['interactive_ui_driver.py'].read_text(encoding='utf-8'), BEFORE.read_text(encoding='utf-8')
        old_contexts = next(node.value for node in ast.parse(old).body if isinstance(node, ast.Assign) and
                            any(isinstance(target, ast.Name) and target.id == 'CONTEXTS' for target in node.targets))
        legacy = {'CONTEXTS': ast.literal_eval(old_contexts), 're': re}
        exec(function_source(old, 'require') + '\n' + function_source(old, 'parse_scene_request'), legacy)
        protocol_snapshot = str(directory / 'protocol-only/play-ui-1.json')
        protocol_folder = str(directory / 'protocol-only/play-ui-1')
        line = f'INTERACTIVE_UI_SCENE_REQUEST=1|load-menu|{protocol_snapshot}|{protocol_folder}'
        reject('observed-before-driver-rejects-load-menu', lambda: legacy['parse_scene_request'](line))
        report['historical_failure_reproduced'] = rejected[-1]
        for context in sorted(driver.CONTEXTS):
            for ending in ('', '\n', '\r\n'):
                request = line.replace('|load-menu|', '|' + context + '|') + ending
                check(driver.parse_scene_request(request) == (1, context, protocol_snapshot, protocol_folder),
                      'Exact context/request framing changed: ' + context)
        for name, value in {'foreign': '|other-load-menu|', 'nested': '|load-menu-child|',
                            'case': '|LoadMenu|'}.items():
            reject('parser-' + name, lambda value=value: driver.parse_scene_request(line.replace('|load-menu|', value)))
        for name, value in {'zero': line.replace('=1|', '=0|'), 'leading-zero': line.replace('=1|', '=01|'),
                            'missing': line.rsplit('|', 1)[0], 'extra': line + '|extra'}.items():
            reject('parser-' + name, lambda value=value: driver.parse_scene_request(value))
        for name in ('validate_game_menu_scene_proof', 'validate_save_menu_scene_proof',
                     'validate_action_info_panel_scene_proof', 'validate_notification_panel_scene_proof',
                     'validate_social_policy_scene_proof', 'validate_economic_overview_scene_proof'):
            check(function_source(old, name) == function_source(text, name), 'Existing context validator changed: ' + name)

        runtime = directory / 'runtime'
        session = runtime / 'sessions/component'
        support = runtime / 'interactive_ui_support'
        tools_dir, assets = support / 'tools', support / 'assets'
        session.mkdir(parents=True)
        tools_dir.mkdir(parents=True)
        assets.mkdir()
        for name in driver.SUPPORT:
            target = tools_dir / name
            shutil.copy2(inputs[name], target)
            check(artifact(target)['sha256'] == before[name]['sha256'], 'Frozen support copy differs: ' + name)
        icons_source = PROJECT / 'evidence/ui_popup/assets/inline_icons.json'
        inputs['inline_icons'] = icons_source
        before['inline_icons'] = artifact(icons_source)
        icons = assets / 'inline_icons.json'
        icons.write_bytes(icons_source.read_bytes())
        check(artifact(icons)['sha256'] == before['inline_icons']['sha256'], 'Frozen icon source changed')
        prep = assets / 'prepared.json'
        prep.write_text(json.dumps({'inline_icon_catalog': artifact(icons),
                                    'scope': 'Explicit driver provenance fixture; original input captures remain separately sealed.'}), encoding='utf-8')
        support_manifest = support / 'support_manifest.json'
        support_manifest.write_text(json.dumps({'tools': {name: artifact(tools_dir / name) for name in driver.SUPPORT},
                                               'inline_icons': artifact(icons),
                                               'asset_preparation_provenance': artifact(prep)}), encoding='utf-8')
        manifest_digest = artifact(support_manifest)['sha256']
        database = session / 'rules.db'
        with closing(sqlite3.connect(database)) as connection, connection:
            connection.execute('CREATE TABLE Colors(Type TEXT PRIMARY KEY, Red REAL, Green REAL, Blue REAL, Alpha REAL)')
            connection.execute("INSERT INTO Colors VALUES ('COLOR_WHITE',1,1,1,1)")
        database_before = artifact(database)
        actual_run = driver.subprocess.run
        mutation_after_prepare = [None]

        def guarded_run(command, **kwargs):
            args = [str(value) for value in command]
            check(args[:5] == [sys.executable, '-B', '-X', 'utf8', str(tools_dir / 'render_ui_popup.py')] and
                  '--prepare' in args and '--context' in args and args[args.index('--context') + 1] == 'load-menu',
                  'Only the frozen Python CPU LoadMenu preparer may be spawned')
            launches.append({'executable': args[0], 'script': args[4], 'mode': '--prepare', 'context': 'load-menu'})
            result = actual_run(command, **kwargs)
            if mutation_after_prepare[0] is not None:
                path = mutation_after_prepare[0]
                path.write_bytes(path.read_bytes() + b'\n')
            return result

        def request(sequence, snapshot, *, context='load-menu', output=None):
            path = session / f'play-ui-{sequence}.json'
            path.write_text(json.dumps(snapshot, ensure_ascii=False), encoding='utf-8')
            folder = output or session / f'play-ui-{sequence}'
            request_line = f'INTERACTIVE_UI_SCENE_REQUEST={sequence}|{context}|{path}|{folder}'
            return driver.prepare_request(request_line, runtime=runtime, tools_dir=tools_dir, icons_source=icons,
                                          support_manifest=support_manifest, support_manifest_sha256=manifest_digest)

        snapshots = capture['snapshots']['known']
        with patch.object(driver.subprocess, 'run', guarded_run):
            for sequence, name in enumerate(('selectedSnapshotJson', 'sortOpened', 'closedSnapshotJson'), 1):
                snapshot = copy.deepcopy(snapshots[name])
                result = request(sequence, snapshot)
                manifest = json.loads(Path(result['manifest']['path']).read_text(encoding='utf-8'))
                records = packet_records(manifest)
                check(result['context'] == 'load-menu' and result['closed'] is (snapshot['active'] is False), 'Driver context/closed result differs')
                check(result['load_menu_controls'] == manifest['load_menu_controls'] and
                      result['load_menu_controls']['source_api_bound_candidate'] is True and
                      result['load_menu_controls']['native_load_handoff_verified'] is False,
                      'Driver omitted its frontend proof or overstated native loading')
                check([list(row) for row in records['hits']] == wire_regions(manifest['hit_regions']) and
                      [list(row) for row in records['scrolls']] == wire_regions(manifest['scroll_regions']),
                      'Actual packet records differ from the validated captured input')
                if name == 'sortOpened':
                    check(snapshot['inputTargets'][0]['inputRole'] == 'PullDownDismiss' and
                          manifest['hit_regions'][0][0] == snapshot['tree']['key'], 'PullDown dismissal lost input precedence')
                if result['closed']:
                    check(not records['sprites'] and not records['hits'] and not records['scrolls'] and
                          manifest['geometry'] == [] and manifest['labels'] == [], 'Closed request kept paint/input')
                prepared.append({'snapshot': name, 'sequence': sequence, 'closed': result['closed'],
                                 'packet': result['packet'], 'manifest': result['manifest'],
                                 'input_target_count': manifest['input_target_count'],
                                 'scroll_target_count': manifest['scroll_region_count']})
                if name == 'selectedSnapshotJson':
                    baseline, baseline_manifest = snapshot, manifest

            check(render_ui_popup.retained_bounds(baseline, baseline_manifest['geometry'], context='load-menu') ==
                  baseline_manifest['retained_runtime_bounds_check'], 'LoadMenu bounds proof did not use the actual current preparer')
            without_back = [row for row in baseline_manifest['geometry'] if row.get('id') != 'BackButton']
            reject('bounds-without-original-back-button',
                   lambda: render_ui_popup.retained_bounds(baseline, without_back, context='load-menu'))
            partial = copy.deepcopy(baseline)
            partial['loadMenu']['controlOnly'] = True
            partial['loadMenu']['sourceApisBound'] = False
            reject('bounds-control-only-incomplete-dialog',
                   lambda: render_ui_popup.retained_bounds(partial, baseline_manifest['geometry'], context='load-menu'))

            for name in ('context', 'kind', 'version', 'status', 'closed', 'targets', 'hit', 'scroll_count',
                         'source', 'style_source', 'native_claim', 'callback_claim', 'retail_claim'):
                changed = copy.deepcopy(baseline_manifest)
                if name == 'context': changed['context'] = 'save-menu'
                elif name == 'kind': changed['popup_kind'] = 'GameMenu'
                elif name == 'version': changed['packet_version'] = 'ZSUPIX01'
                elif name == 'status': changed['status'] = 'ACTUAL_SDK_RETAINED_POPUP_SCENE_COMPILED'
                elif name == 'closed': changed['closed_context_not_drawn'] = True
                elif name == 'targets': changed['retained_input_targets'] = []
                elif name == 'hit': changed['hit_regions'][0][-1] += 1
                elif name == 'scroll_count': changed['scroll_region_count'] += 1
                elif name == 'source': changed['original_context_sources'] = [row for row in changed['original_context_sources'] if not row['path'].endswith('LoadMenu.lua')]
                elif name == 'style_source': changed['original_context_sources'] = [row for row in changed['original_context_sources'] if not row['path'].endswith('Styles.xml')]
                elif name == 'native_claim': changed['load_menu_controls']['native_load_handoff_verified'] = True
                elif name == 'callback_claim': changed['input_callback_coverage_claimed'] = True
                elif name == 'retail_claim': changed['retail_input_semantics_verified'] = True
                reject('manifest-' + name, lambda changed=changed: driver.validate_load_menu_scene_proof(baseline, changed))

            for sequence, name in enumerate(('wrong_context', 'timer', 'control_only', 'foreign_target', 'hidden_without_original_dequeue'), 10):
                changed = copy.deepcopy(snapshots['closedSnapshotJson'] if name == 'hidden_without_original_dequeue' else baseline)
                if name == 'wrong_context': changed['contextName'] = 'SaveMenu'
                elif name == 'timer': changed['timerSemaphore'] = 1
                elif name == 'control_only': changed['loadMenu']['controlOnly'] = True;changed['loadMenu']['sourceApisBound'] = False
                elif name == 'foreign_target': changed['inputTargets'][0]['key'] = 987654321
                elif name == 'hidden_without_original_dequeue': changed['lifecycle'] = ['queued', 'context-hidden:LoadMenu']
                reject('snapshot-' + name, lambda changed=changed, sequence=sequence: request(sequence, changed))
            reject('output-outside-owning-session', lambda: request(20, baseline, output=runtime / 'sessions/foreign/play-ui-20'))
            tool = tools_dir / 'interactive_ui_driver.py'
            original_tool = tool.read_bytes()
            try:
                tool.write_bytes(original_tool + b'\n')
                reject('changed-frozen-support', lambda: request(21, baseline))
            finally:
                tool.write_bytes(original_tool)
            mutation_after_prepare[0] = session / 'play-ui-22.json'
            try:
                reject('snapshot-changed-during-prepare', lambda: request(22, baseline))
            finally:
                mutation_after_prepare[0] = None
        check(len(launches) == 4, 'An invalid early request reached the packet preparer')
        check(artifact(database) == database_before, 'Driver changed its explicit rules database fixture')

        suite = unittest.TestSuite([
            GameMenuRendererTests('test_driver_recognizes_only_the_exact_menu_scene_name'),
            ActionInfoPanelTests('test_driver_parses_full_original_action_info_request_line'),
        ])
        transcript = io.StringIO()
        existing = unittest.TextTestRunner(stream=transcript, verbosity=2).run(suite)
        check(existing.wasSuccessful() and existing.testsRun == 2, 'Existing exact context protocol tests failed: ' + transcript.getvalue())
        report['existing_protocol_regressions'] = {'tests': existing.testsRun, 'failures': len(existing.failures), 'errors': len(existing.errors)}
        report['status'] = 'PASS'
    except Exception as exc:
        error = exc
        report.update(status='FAIL', error=str(exc))
    finally:
        report.update(checks=checks, rejected_cases=rejected, prepared_states=prepared, spawned_preparers=launches)
        checkpoint()
        try:
            report['cleanup'] = remove_generated(directory, build, evidence / 'cleanup.json')
            report['inputs_after'] = {name: artifact(path) for name, path in inputs.items()}
            if report['inputs_after'] != before:
                raise AssertionError('Driver/component/support source changed during the verification')
            report['inputs_unchanged'] = True
        except Exception as exc:
            report.update(status='FAIL', cleanup_or_input_error=str(exc))
            error = error or exc
        checkpoint()
    summary = {'status': report['status'], 'checks': checks, 'negative_cases': len(rejected),
               'prepared_states': len(prepared), 'report': str(destination),
               'generated_files_removed': report.get('cleanup', {}).get('file_count'),
               'generated_logical_bytes_removed': report.get('cleanup', {}).get('logical_bytes_removed')}
    print(json.dumps(summary, ensure_ascii=False))
    if error is not None:
        raise RuntimeError(str(error)) from error
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--helper-proof', type=Path,
                        help='Direct old/new observer equivalence receipt after the helper dependency move.')
    verify_component(parser.parse_args().helper_proof)
