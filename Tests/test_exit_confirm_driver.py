"""Test ExitConfirm parsing, source contracts and headless packet/input boundaries.

Inputs are preserved snapshots from the actual stock-Lua component fixture.
This runner is pure Python: no Host/SDK/Lua process, window, GPU, PNG export or
user-save access. The shown geometry is captured fixture data, not raster proof.
"""
from __future__ import annotations

import copy
import gzip
import hashlib
import json
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import patch

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "tools"))
import interactive_ui_driver as driver
import render_ui_popup as renderer
import ui_pixel_scene as pixel

INPUT = PROJECT / "evidence/game_menu/offline_exit/driver_source_snapshots.json.gz"
INPUT_SHA256 = "4b4c12e687baa1da661d5843bf691472a040ab45e0e73c1be2ae07d6e2eb54a9"
_snapshots = None


def snapshots():
    global _snapshots
    if _snapshots is None:
        compressed = INPUT.read_bytes()
        if hashlib.sha256(compressed).hexdigest() != INPUT_SHA256:
            raise AssertionError("Preserved stock-Lua snapshot input changed")
        _snapshots = json.loads(gzip.decompress(compressed))
        if (_snapshots['status'] != 'PASS_ORIGINAL_EXIT_CONFIRM_COMPONENT' or
                _snapshots['temporary_styles_removed'] is not True):
            raise AssertionError("Snapshot generator did not pass its declared component scope")
        names = {'scene': PROJECT / 'Source/Host/UiScene.lua',
                 'input': PROJECT / 'Source/Presentation/UiPresentationInput.lua',
                 'stock': Path(_snapshots['retained_snapshot']['exitConfirm']['originalLua']['path']),
                 'xml': Path(_snapshots['retained_snapshot']['exitConfirm']['originalXml']['path']),
                 'lua_provider': PROJECT / 'Build/SharedLuaRuntime/Lua/ZeroSisLua51_x64.dll'}
        if any(hashlib.sha256(path.read_bytes()).hexdigest() != _snapshots['source_sha256'][key]
               for key, path in names.items()):
            raise AssertionError("Preserved snapshot is not bound to the current production input")
    return _snapshots


def walk(node):
    yield node
    for child in node.get('children', []):
        yield from walk(child)


def source_map(proof):
    return {Path(proof[field]['path']): proof[field]['sha256']
            for field in ('originalLua', 'originalXml', 'originalStyles')}


def geometry(snapshot):
    return [{'key': node['key'], 'kind': node['kind'], 'id': node.get('id', ''),
             'bounds': tuple(node[field] for field in ('x', 'y', 'width', 'height')),
             'style_decoration': False}
            for node in walk(snapshot['tree'])]


def hit_compiler(snapshot):
    compiler = pixel.Compiler.__new__(pixel.Compiler)
    compiler.context = 'exit-confirm'
    compiler.exit_confirm_scene = pixel.exit_confirm_contract(snapshot)
    compiler.production_input_targets = copy.deepcopy(snapshot['inputTargets'])
    compiler.geometry = geometry(snapshot)
    compiler.hits = []
    compiler.production_hits(snapshot['tree'])
    return compiler


def component_manifest(snapshot, *, closed=False):
    proof = pixel.exit_confirm_contract(snapshot, closed=closed)
    compiler = None if closed else hit_compiler(snapshot)
    return {'status': 'STOCK_EXIT_CONFIRM_COMPONENT_SCENE_COMPILED',
            'context': 'exit-confirm', 'context_name': 'ExitConfirm', 'popup_kind': 'ExitConfirm',
            'packet_version': 'ZSUPIX02', 'closed_context_not_drawn': closed,
            'exit_confirm_scene': proof, 'retained_input_targets': copy.deepcopy(snapshot['inputTargets']),
            'original_context_sources': [{'path': str(path), 'sha256': digest}
                                         for path, digest in source_map(proof).items()],
            'hit_regions': [] if closed else [list(row) for row in compiler.hits],
            'scroll_regions': [], 'input_target_count': len(snapshot['inputTargets']),
            'scroll_region_count': 0, 'texture_count': 0, 'sprite_count': 0,
            'geometry': [] if closed else compiler.geometry, 'labels': []}


class NoTextureAssets:
    """Asset-resolution boundary for constructor/closed-packet tests only."""
    def __init__(self, game_root):
        self.game_root = Path(game_root)
        self.pack_records, self.records, self.loose_records = [], [], []
        self.outputs = {}

    def resolve(self, *args, **kwargs):
        raise AssertionError("Pure contract test attempted texture materialization")


class ExitConfirmDriverTests(unittest.TestCase):
    def test_actual_request_parser_accepts_exit_and_keeps_unknown_rejection(self):
        suffix = r"C:\fixture\shown.json|C:\fixture\scene"
        self.assertEqual(driver.parse_scene_request('INTERACTIVE_UI_SCENE_REQUEST=17|exit-confirm|' + suffix),
                         (17, 'exit-confirm', r'C:\fixture\shown.json', r'C:\fixture\scene'))
        for context in ('unregistered-popup', 'ExitConfirm', 'exit-confirm-extra'):
            with self.subTest(context=context), self.assertRaises((ValueError, RuntimeError)):
                driver.parse_scene_request('INTERACTIVE_UI_SCENE_REQUEST=17|' + context + '|' + suffix)
        for sequence in ('0', '-1', '01'):
            with self.subTest(sequence=sequence), self.assertRaises((ValueError, RuntimeError)):
                driver.parse_scene_request('INTERACTIVE_UI_SCENE_REQUEST=' + sequence + '|exit-confirm|' + suffix)

    def test_actual_stock_snapshots_keep_separate_modal_and_parent_timer(self):
        for token, closed in (('retained_snapshot', False), ('closed_snapshot', True)):
            snapshot = snapshots()[token]
            before = copy.deepcopy(snapshot)
            proof = pixel.exit_confirm_contract(snapshot, closed=closed)
            self.assertEqual(proof['retained_control_count'], 12)
            self.assertEqual(proof['parent_context'], 'GameMenu')
            self.assertEqual(proof['parent_timer_policy'], 'PRESERVE_GAME_MENU_TIMER_WHILE_MODAL_OPEN')
            self.assertEqual(proof['timer_semaphore'], 0)
            self.assertFalse(proof['native_acceptance_verified'])
            self.assertEqual(snapshot, before)
            self.assertEqual(pixel.exit_confirm_contract(snapshot, source_map(proof), closed=closed), proof)

    def test_context_lifetime_and_acceptance_tampering_rejected(self):
        changes = [('contextName', 'GameMenu'), ('popupKind', 'GameMenu'), ('timerSemaphore', 1),
                   ('timerSemaphore', False), ('active', False), ('contextHidden', True),
                   ('lifecycle', ['queued']), ('lifecycle', ['modal-pushed', 'modal-popped'])]
        for field, value in changes:
            altered = copy.deepcopy(snapshots()['retained_snapshot']);altered[field] = value
            with self.subTest(field=field, value=value), self.assertRaises((ValueError, RuntimeError)):
                pixel.exit_confirm_contract(altered)
        for field, value in [('parentContext', 'MainMenu'), ('timerSemaphores', 1),
                             ('parentTimerSemaphorePolicy', 'RELEASE_PARENT_TIMER'),
                             ('nativeAcceptanceVerified', True), ('retailLayoutVerified', True),
                             ('exitSubmitted', True)]:
            altered = copy.deepcopy(snapshots()['retained_snapshot']);altered['exitConfirm'][field] = value
            with self.subTest(field=field), self.assertRaises((ValueError, RuntimeError)):
                pixel.exit_confirm_contract(altered)

    def test_original_source_and_source_map_tampering_rejected(self):
        for field in ('originalLua', 'originalXml'):
            altered = copy.deepcopy(snapshots()['retained_snapshot'])
            altered['exitConfirm'][field]['sha256'] = '0' * 64
            with self.subTest(source=field), self.assertRaises((ValueError, RuntimeError)):
                pixel.exit_confirm_contract(altered)
        original = snapshots()['retained_snapshot']
        sources = source_map(pixel.exit_confirm_contract(original))
        sources[next(iter(sources))] = '0' * 64
        with self.assertRaises((ValueError, RuntimeError)):
            pixel.exit_confirm_contract(original, sources)

    def test_original_tree_visibility_message_and_modal_shield_rejected_if_changed(self):
        for operation in ('kind', 'children', 'disabled', 'hidden', 'message', 'shield', 'runtime_attributes', 'source_attributes'):
            altered = copy.deepcopy(snapshots()['retained_snapshot'])
            controls = {node['id']: node for node in walk(altered['tree']) if node.get('id')}
            if operation == 'kind': controls['Yes']['kind'] = 'Button'
            elif operation == 'children': altered['tree']['children'].append(copy.deepcopy(controls['No']))
            elif operation == 'disabled': controls['Yes']['disabled'] = True
            elif operation == 'hidden': controls['No']['hidden'] = True
            elif operation == 'message': controls['Message']['text'] = ''
            elif operation == 'shield': controls['ExitConfirm']['width'] = 100
            elif operation == 'runtime_attributes': controls['Yes']['attributes']['Style'] = 'WrongStyle'
            else: controls['ExitConfirm']['sourceAttributes']['ConsumeMouseOver'] = '0'
            with self.subTest(operation=operation), self.assertRaises((ValueError, RuntimeError)):
                pixel.exit_confirm_contract(altered)

    def test_original_input_order_payload_and_clipping_rejected_if_changed(self):
        for operation in ('remove', 'duplicate', 'reorder', 'id', 'key', 'payload', 'consume', 'bounds', 'scroll'):
            altered = copy.deepcopy(snapshots()['retained_snapshot']);targets = altered['inputTargets']
            if operation == 'remove': targets.pop()
            elif operation == 'duplicate': targets.append(copy.deepcopy(targets[-1]))
            elif operation == 'reorder': targets[1], targets[2] = targets[2], targets[1]
            elif operation == 'id': targets[1]['id'] = 'ExitGameButton'
            elif operation == 'key': targets[1]['key'] = 999
            elif operation == 'payload': targets[1]['void1'] = 1
            elif operation == 'consume': targets[0]['consumeMouse'] = False
            elif operation == 'bounds': targets[1]['clippedBounds']['x'] += 1
            else: altered['scrollTargets'] = [{'event': 'Scroll', 'key': 9}]
            with self.subTest(operation=operation), self.assertRaises((ValueError, RuntimeError)):
                pixel.exit_confirm_contract(altered)

    def test_actual_hit_conversion_retains_fullscreen_consumer_before_yes_no(self):
        snapshot = snapshots()['retained_snapshot'];compiler = hit_compiler(snapshot)
        self.assertEqual([row[0] for row in compiler.hits], [row['key'] for row in snapshot['inputTargets']])
        self.assertEqual(compiler.hits[0][1:], (0, 0, 1920, 1080))
        def hit(x, y):
            return next((row[0] for row in reversed(compiler.hits)
                         if row[1] <= x < row[3] and row[2] <= y < row[4]), None)
        for target in snapshot['inputTargets'][1:]:
            bounds = target['clippedBounds']
            self.assertEqual(hit(bounds['x'] + 1, bounds['y'] + 1), target['key'])
        self.assertEqual(hit(1, 1), compiler.hits[0][0])
        pixel.validate_hit_regions('exit-confirm', compiler.hits, compiler.geometry)

    def test_actual_renderer_retained_bounds_reject_shifted_control(self):
        snapshot = snapshots()['retained_snapshot'];compiler = hit_compiler(snapshot)
        renderer.retained_bounds(snapshot, compiler.geometry, context='exit-confirm')
        changed = copy.deepcopy(compiler.geometry)
        row = next(row for row in changed if row['id'] == 'No')
        row['bounds'] = (row['bounds'][0] + 1, *row['bounds'][1:])
        with self.assertRaises((ValueError, RuntimeError)):
            renderer.retained_bounds(snapshot, changed, context='exit-confirm')

    def test_actual_packet_manifest_validator_accepts_current_contract_and_rejects_corruption(self):
        snapshot = snapshots()['retained_snapshot'];manifest = component_manifest(snapshot)
        driver.validate_exit_confirm_scene_proof(snapshot, manifest)
        for field, value in [('context_name', 'GameMenu'), ('popup_kind', 'GameMenu'), ('packet_version', 'ZSUPIX01'),
                             ('hit_regions', []), ('scroll_regions', [[1, 0, 0, 1, 1]]),
                             ('original_context_sources', []), ('closed_context_not_drawn', True)]:
            altered = copy.deepcopy(manifest);altered[field] = value
            with self.subTest(field=field), self.assertRaises((ValueError, RuntimeError)):
                driver.validate_exit_confirm_scene_proof(snapshot, altered)

    def test_actual_closed_packet_uses_new_context_without_resolving_textures(self):
        snapshot = snapshots()['closed_snapshot'];proof = pixel.exit_confirm_contract(snapshot, closed=True)
        game = Path(proof['originalLua']['path']).parents[3]
        output = PROJECT / 'evidence/game_menu/offline_exit/driver_empty_candidate'
        self.assertFalse(output.exists())
        try:
            with patch.object(pixel, 'UiAssets', NoTextureAssets):
                compiler = pixel.Compiler(game, output, context='exit-confirm', snapshot_clock=snapshot['presentationClock'])
                packet = compiler.compile(snapshot, closed=True)
            self.assertEqual(compiler.layout_path, Path(proof['originalXml']['path']))
            self.assertEqual(compiler.script_path, Path(proof['originalLua']['path']))
            self.assertEqual(compiler.exit_confirm_scene, proof)
            self.assertEqual(packet, b'ZSUPIX02' + struct.pack('<6I', 1920, 1080, 0, 0, 0, 0))
            self.assertEqual(list(output.iterdir()), [])
        finally:
            if output.exists():
                self.assertEqual(output.resolve(), (PROJECT / 'evidence/game_menu/offline_exit/driver_empty_candidate').absolute())
                self.assertFalse(output.is_symlink())
                output.rmdir()

    def test_closed_manifest_remains_empty_and_cannot_claim_pixels(self):
        snapshot = snapshots()['closed_snapshot'];manifest = component_manifest(snapshot, closed=True)
        driver.validate_exit_confirm_scene_proof(snapshot, manifest, closed=True)
        manifest['sprite_count'] = 1
        with self.assertRaises((ValueError, RuntimeError)):
            driver.validate_exit_confirm_scene_proof(snapshot, manifest, closed=True)


def main():
    paths = [PROJECT / 'tools' / name for name in ('interactive_ui_driver.py', 'render_ui_popup.py', 'ui_pixel_scene.py')]
    def seal(path):
        raw = path.read_bytes()
        return {'path': str(path), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
    before = [seal(path) for path in paths]
    result = unittest.TextTestRunner(stream=sys.stderr, verbosity=1).run(unittest.defaultTestLoader.loadTestsFromTestCase(ExitConfirmDriverTests))
    report = {'schema': 'zerosis.exit_confirm.driver_contract_tests.v1',
              'status': 'PASS' if result.wasSuccessful() else 'FAIL', 'tests': result.testsRun,
              'failures': len(result.failures), 'errors': len(result.errors), 'input': seal(INPUT),
              'runner': seal(Path(__file__)), 'sources_before': before, 'sources_after': [seal(path) for path in paths],
              'stock_lua_snapshot_fixture_checks': snapshots()['checks'],
              'stock_lua_snapshot_fixture_executions_for_input': 1, 'lua_fixture_executions_this_runner': 0,
              'actual_request_parser_tested': True, 'actual_source_contract_tested': True,
              'actual_renderer_retained_bounds_tested': True, 'actual_hit_region_compilation_tested': True,
              'actual_closed_packet_compiled': True, 'constructor_asset_provider_stubbed': True,
              'shown_geometry_input': 'ACTUAL_STOCK_LUA_COMPONENT_CAPTURE_NOT_RASTER_OUTPUT',
              'host_sdk_window_gpu_clr_executed': False, 'png_files_created': 0,
              'full_shown_raster_or_native_input_acceptance_verified': False}
    if report['sources_before'] != report['sources_after']:
        report['status'] = 'FAIL'
    destination = PROJECT / 'evidence/game_menu/offline_exit/driver_tests.json'
    destination.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': report['status'], 'tests': result.testsRun, 'report': str(destination)}, ensure_ascii=False))
    raise SystemExit(0 if report['status'] == 'PASS' else 1)


if __name__ == '__main__':
    main()
