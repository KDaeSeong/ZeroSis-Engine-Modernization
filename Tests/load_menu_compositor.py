"""Complete original LoadMenu offline composition; no Host, GameCore or window.

Capture-only additions to the existing Lua fixture retain its exact assertions
and unchanged production/original sources. One current capture JSON is retained;
all generated candidate atlas files share one guarded temporary directory.
This is source/frontend candidate evidence, not retail geometry or gameplay.
"""
from __future__ import annotations

import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

PROJECT = Path(__file__).absolute().parents[1]
sys.path.insert(0, str(PROJECT / 'tools'))
sys.path.insert(0, str(PROJECT / 'Tests'))

import load_menu_scene as scene_test
import pull_down_compositor as old_compositor
from ui_pixel_scene import Compiler, economic_walk, intersect, rect

EVIDENCE = PROJECT / 'evidence/load_menu/native_handoff'
CAPTURES = EVIDENCE / 'composition_snapshots.json'
FROZEN = {
    'scene': (PROJECT / 'Source/Host/UiScene.lua',
              '7c445d81244a1106b4145dfc149a09513578201f6e7ba279d652702b1c9e701c'),
    'scene_harness': (PROJECT / 'Tests/load_menu_scene.py',
                      '5b1a55e609af3a179ec40c870a2a76ba7d48617015f411c5cf72614fc07198b9'),
    'compiler': (PROJECT / 'tools/ui_pixel_scene.py',
                 'a3feb515b5aac2df279193efc54807798fd3169a7663eee9fc894ca284709071'),
    'preparer': (PROJECT / 'tools/prepare_ui_popup_assets.py',
                 '1bf9bc519d9988b5aa254d1b9f01fefcc7a5d2702ad9067f17703a74bf109d28'),
}


def artifact(path: Path) -> dict:
    info = path.stat()
    return {'path': str(path), 'bytes': info.st_size,
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def capture_harness() -> tuple[str, list[str]]:
    source = scene_test.HARNESS
    additions = [
        ("local selectedJson=''", "local compositionCaptures={}\nlocal selectedJson=''", 'declare-capture-table'),
        ("local value=snap();local owner=key(env.Controls.SortByPullDown)",
         "local value=snap();local owner=key(env.Controls.SortByPullDown)\n  compositionCaptures.sortOpened=compositionCaptures.sortOpened or json(value)",
         'capture-original-open-sort'),
        ("env.Controls.DeleteConfirm:SetHide(true);env.Controls.DeleteConfirm:SetHide(false)",
         "env.Controls.DeleteConfirm:SetHide(true);env.Controls.DeleteConfirm:SetHide(false)\n compositionCaptures.deleteConfirm=json(snap())",
         'capture-explicit-original-delete-modal-visibility-fixture'),
        ("env.Controls.ReferencedPackagesWindow:SetHide(false)\n check(target(savedKey)==nil",
         "env.Controls.ReferencedPackagesWindow:SetHide(false)\n compositionCaptures.referencedPackages=json(snap())\n check(target(savedKey)==nil",
         'capture-explicit-original-package-modal-visibility-fixture'),
        ("openedSnapshotJson=openedJson,selectedSnapshotJson=selectedJson,closedSnapshotJson=json(closed)})",
         "compositionCaptureJson=json(compositionCaptures),openedSnapshotJson=openedJson,selectedSnapshotJson=selectedJson,closedSnapshotJson=json(closed)})",
         'return-extra-capture-table'),
    ]
    for before, after, name in additions:
        if source.count(before) != 1:
            raise AssertionError('Capture-only fixture anchor changed: ' + name)
        source = source.replace(before, after, 1)
    return source, [row[2] for row in additions]


def acquire_captures(before: dict) -> tuple[dict, bool]:
    harness, instrumentation = capture_harness()
    capture_identity = {'original_harness_sha256': before['scene_harness']['sha256'],
                        'in_memory_capture_harness_sha256': hashlib.sha256(harness.encode('utf-8')).hexdigest(),
                        'capture_only_additions': instrumentation}
    if CAPTURES.exists():
        result = json.loads(CAPTURES.read_text(encoding='utf-8'))
        if result['capture_identity'] != capture_identity or result['production_sources'] != {
                name: row for name, row in before.items() if name in ('scene', 'scene_harness', 'preparer')}:
            raise AssertionError('Current retained captures do not match the frozen original producer')
        return result, False
    original = scene_test.HARNESS
    scene_test.HARNESS = harness
    try:
        generation = scene_test.verify_component(include_snapshot=True)
    finally:
        scene_test.HARNESS = original
    captures = generation.pop('snapshots')
    for case in generation['cases']:
        raw = case.pop('compositionCaptureJson')
        extras = json.loads(raw)
        captures[case['case']].update({name: json.loads(value) for name, value in extras.items()})
    if generation['checks'] != 365 or not generation['temporary_styles_removed']:
        raise AssertionError('Original complete Lua fixture did not pass the frozen 365 checks')
    result = {'schema': 1, 'capture_identity': capture_identity,
              'production_sources': {name: row for name, row in before.items()
                                     if name in ('scene', 'scene_harness', 'preparer')},
              'capture_generation': generation, 'snapshots': captures,
              'native_sdk_binding_verified': False, 'retail_geometry_verified': False,
              'modal_state_scope': 'Explicit original-control visibility fixtures, not external-package/delete backend proof'}
    payload = json.dumps(result, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    if len(payload) > 8 * 1024 * 1024:
        raise AssertionError('Current full-dialog capture exceeded the bounded single JSON allowance')
    with CAPTURES.open('xb') as output:
        output.write(payload)
    return result, True


def verify_component() -> dict:
    # Resolve every strict root before an optional capture rerun or temp write.
    build = (PROJECT / 'Build').resolve(strict=True)
    for path, _ in FROZEN.values():
        path.resolve(strict=True)
    before = {name: artifact(path) for name, (path, _) in FROZEN.items()}
    before['compositor_harness'] = artifact(Path(__file__))
    for name, (_, digest) in FROZEN.items():
        if before[name]['sha256'] != digest:
            raise AssertionError('Frozen complete-dialog input changed: ' + name)
    fault = old_compositor.suppress_own_fault_ui()
    capture, generated = acquire_captures(before)
    immutable = copy.deepcopy(capture['snapshots'])
    inline = json.loads(old_compositor.INLINE_ICONS.read_text(encoding='utf-8'))['icons']
    directory = Path(tempfile.mkdtemp(prefix='pull-down-compositor-native-handoff-', dir=build)).resolve(strict=True)
    states, rejected, sources, checks = [], [], {}, 0
    cleanup, historical, error = None, None, None

    def check(value, message):
        nonlocal checks
        if not value:
            raise AssertionError(message)
        checks += 1

    def compiler():
        instance = Compiler(old_compositor.GAME, directory, context='load-menu', inline_colors={}, inline_icons=inline)
        for path, digest in instance.context_sources.items():
            check(str(path) not in sources or sources[str(path)] == digest, 'Original source drift between compilers')
            sources[str(path)] = digest
        return instance

    try:
        for case, snapshots in immutable.items():
            for name, snapshot in snapshots.items():
                state = case + '.' + name
                original = copy.deepcopy(snapshot)
                closed = snapshot['active'] is False
                instance = compiler()
                packet = instance.compile(snapshot, closed=closed)
                parsed = old_compositor.packet_sections(packet, directory)
                check(instance.load_menu_scene['full_original_tree_matched'] is True and
                      instance.load_menu_scene['source_api_bound_candidate'] is True and
                      instance.load_menu_scene['native_load_handoff_verified'] is False and
                      instance.load_menu_scene['retail_geometry_verified'] is False,
                      state + ': full original frontend candidate lost its proof boundary')
                hits = [(row['key'], *old_compositor.captured_clip_xyxy(row)) for row in snapshot['inputTargets']]
                check(instance.hits == hits and parsed['hits'] == [old_compositor.wire_rectangle(row) for row in hits],
                      state + ': callback/consumer order or serialized bounds differ from actual Lua capture')
                scrolls = sorted((row['key'], *old_compositor.captured_clip_xyxy(row)) for row in snapshot['scrollTargets'])
                check(instance.scroll_regions == scrolls and
                      parsed['scroll'] == [old_compositor.wire_rectangle(row) for row in scrolls],
                      state + ': scroll scope or clipping differs from actual Lua capture')
                nodes = {row['key']: row for row in economic_walk(snapshot['tree'])}
                check(parsed['sprites'] == len(instance.sprites), state + ': packet sprite count differs')
                checkbox_rows = []
                if not closed:
                    for control_id in ('AutoCheck', 'CloudCheck'):
                        node = next(row for row in nodes.values() if row.get('id') == control_id)
                        geometry = next(row for row in instance.geometry if row['key'] == node['key'] and
                                        row.get('kind') == 'CheckBox')
                        candidate = geometry['default_size_candidate']
                        check((node['width'], node['height'], node['checked'], node['disabled']) == (32, 32, False, True) and
                              geometry['check_atlas_frame'] == 3 and candidate['atlas']['width'] == 32 and
                              candidate['atlas']['height'] == 128 and candidate['retailGeometryVerified'] is False and
                              candidate['defaultBindingVerified'] is False and candidate['retailWidgetStateMappingVerified'] is False,
                              state + ': original implicit checkbox candidate/frame/proof differs')
                        check(all(row['key'] != node['key'] for row in snapshot['inputTargets']),
                              state + ': unsupported checkbox acquired actionable input')
                        label = next(row for row in instance.labels if row['key'] == node['key'] and
                                     row.get('text_control') == 'CheckBox')
                        check(label['retail_text_alignment_verified'] is False and bool(label['plain_text']),
                              state + ': original checkbox caption disappeared or claimed retail placement')
                        glyph_textures = {index for index, path in enumerate(instance.textures)
                                          if any(path == sheet['path'] for font in instance.font_records
                                                 if font['font_id'] == label['font'] for sheet in font['sheets'])}
                        glyphs = [sprite for sprite in instance.sprites if sprite[1] == node['key'] and sprite[0] in glyph_textures]
                        check(bool(glyphs) and all(intersect(sprite[10:14], (0, 0, 1920, 1080)) == tuple(sprite[10:14])
                                                  and intersect(sprite[6:10], sprite[10:14])[2] >
                                                  intersect(sprite[6:10], sprite[10:14])[0] and
                                                  intersect(sprite[6:10], sprite[10:14])[3] >
                                                  intersect(sprite[6:10], sprite[10:14])[1] for sprite in glyphs),
                              state + ': checkbox caption glyph is invisible or its clip escaped the viewport')
                        icons = [sprite for sprite in instance.sprites if sprite[1] == node['key'] and sprite[0] not in glyph_textures]
                        check(len(icons) == 1 and tuple(icons[0][2:6]) == (0, 96, 32, 128) and
                              tuple(icons[0][6:10]) == rect((node['x'], node['y'], 32, 32)),
                              state + ': checkbox pixels do not use their exact candidate atlas cell and retained bounds')
                        checkbox_rows.append({'id': control_id, 'key': node['key'], 'bounds': list(rect((node['x'], node['y'], 32, 32))),
                                              'caption_bounds': label['bounds'], 'glyph_count': len(glyphs),
                                              'frame_candidate': 3, 'retail_geometry_verified': False})
                else:
                    check(len(packet) == 32 and not instance.sprites and not instance.hits and not instance.scroll_regions,
                          state + ': closed original frontend retained pixels or input')
                check(snapshot == original and instance.unchanged(), state + ': compilation mutated captured/original source bytes')
                states.append({'state': state, 'scope': 'ACTUAL_FULL_ORIGINAL_LUA_FIXTURE_CAPTURE',
                               'packet_bytes': len(packet), 'packet_sha256': hashlib.sha256(packet).hexdigest(),
                               'sprites': len(instance.sprites), 'hits': len(instance.hits), 'scroll_regions': len(instance.scroll_regions),
                               'modal_key': instance.load_menu_scene['modal_key'], 'checkboxes': checkbox_rows})
        known = immutable['known']['selectedSnapshotJson']
        for mutation in ('retail_flag', 'checkbox_source', 'checkbox_default', 'checkbox_disabled_target',
                         'missing_modal_consumer', 'consumer_source_id'):
            snapshot = copy.deepcopy(immutable['known']['referencedPackages'] if mutation == 'missing_modal_consumer' else known)
            node = next(row for row in economic_walk(snapshot['tree']) if row.get('id') == 'AutoCheck')
            if mutation == 'retail_flag':
                snapshot['loadMenu']['runtimeIntegrationVerified'] = True
            elif mutation == 'checkbox_source':
                node['sourceAttributes']['Size'] = '32,32'
            elif mutation == 'checkbox_default':
                node['defaultSize']['atlas']['sha256'] = '0' * 64
            elif mutation == 'checkbox_disabled_target':
                snapshot['inputTargets'].append({'key': node['key'], 'event': 'LeftClick', 'visible': True, 'disabled': False})
            elif mutation == 'consumer_source_id':
                consumer = next(row for row in economic_walk(snapshot['tree']) if row.get('id') == 'BGBlock')
                consumer['id'] = 'ForeignConsumer'
                next(row for row in snapshot['inputTargets'] if row['key'] == consumer['key'])['id'] = 'ForeignConsumer'
            else:
                snapshot['inputTargets'] = [row for row in snapshot['inputTargets'] if row.get('event') != 'ConsumeMouse']
            instance = compiler()
            try:
                instance.compile(snapshot)
            except ValueError as caught:
                rejected.append({'case': mutation, 'error': str(caught)});check(True, mutation)
            else:
                raise AssertionError('Full-dialog compositor accepted forged candidate: ' + mutation)
        check(capture['snapshots'] == immutable, 'Composition mutated the retained Lua captures')
        # Reuse the same directory and old immutable captures. The original
        # historical receipt and all historical harness assertions stay intact.
        old_compositor.EVIDENCE = EVIDENCE / 'historical_pull_down_compositor_final'
        old_compositor.FROZEN['compiler'] = FROZEN['compiler']
        remove = old_compositor.remove_generated

        def record_cleanup(*args):
            nonlocal cleanup
            cleanup = remove(*args)
            return cleanup

        with patch.object(old_compositor.tempfile, 'mkdtemp', return_value=str(directory)), \
                patch.object(old_compositor, 'remove_generated', side_effect=record_cleanup):
            historical = old_compositor.verify_component()
        old_report = json.loads(Path(historical['receipt']['path']).read_text(encoding='utf-8'))
        cleanup = old_report['cleanup']
    except Exception as caught:
        error = caught
    finally:
        if directory.exists():
            try:
                cleanup = old_compositor.remove_generated(directory, build)
            except Exception as caught:
                if error is None:
                    error = caught
        changed = [name for name, (path, _) in FROZEN.items() if artifact(path) != before[name]]
        if changed and error is None:
            error = AssertionError('Frozen production inputs changed during composition: ' + ', '.join(changed))
    report = {'schema': 1, 'status': 'PASS_COMPLETE_LOAD_MENU_OFFLINE_CANDIDATE' if error is None else 'FAIL_COMPLETE_LOAD_MENU_COMPOSITION',
              'created_utc': datetime.now(timezone.utc).isoformat(), 'checks': checks, 'source_artifacts_before': before,
              'capture_file': artifact(CAPTURES), 'capture_generation_executed_this_run': generated,
              'capture_generation_checks': capture['capture_generation']['checks'], 'capture_identity': capture['capture_identity'],
              'fault_ui_suppression': fault, 'states': states, 'negative_cases': rejected, 'historical_pull_down_regression': historical,
              'original_ui_sources': sources, 'cleanup': cleanup, 'full_dialog_offline_composed': error is None,
              'runtimeIntegrationVerified': False, 'nativeVmConnected': False, 'retailBackendVerified': False,
              'retailLayoutVerified': False, 'gamecore_or_host_executed': False, 'native_window_executed': False,
              'image_or_base64_output': False, 'packet_files_created': 0}
    if error is not None:
        report['error'] = type(error).__name__ + ': ' + str(error)
    path = EVIDENCE / ('composition_final.json' if error is None else
                       'composition_failure_' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.json')
    with path.open('x', encoding='utf-8', newline='\n') as output:
        json.dump(report, output, ensure_ascii=False, indent=2)
    if error is not None:
        raise RuntimeError(str(error) + '; receipt=' + str(path)) from error
    return {'status': report['status'], 'checks': checks, 'states': len(states), 'negative_cases': len(rejected),
            'historical_checks': historical['checks'], 'capture_bytes': report['capture_file']['bytes'],
            'generated_files_removed': cleanup['file_count'], 'generated_bytes_removed': cleanup['logical_bytes_removed'],
            'receipt': artifact(path)}


if __name__ == '__main__':
    print(json.dumps(verify_component(), ensure_ascii=False))
