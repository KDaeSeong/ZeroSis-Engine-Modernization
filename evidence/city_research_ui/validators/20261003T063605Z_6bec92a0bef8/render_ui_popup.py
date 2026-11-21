"""Render retained actual-SDK popup states through the isolated native renderer.

Freezes selected Python/source UI inputs, not entire SDK or game asset packs.
Never loads GameCore, launches the installed game, or changes a native save.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import shutil
import sqlite3
import struct
import subprocess
import sys
import uuid
import zlib

from civ5_ui_assets import sha256, require, PACK_POLICY, header, rgba32
from ui_pixel_scene import Compiler

PROJECT = Path(__file__).resolve().parents[1]
GAME = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Sid Meier's Civilization V")
RENDERER_PROOF = '20261002T171317Z_516c7fa8b73e'
RUNTIME = {'en_US': '20261002T161323Z_422f18cf0e62', 'ko_KR': '20261002T155207Z_38c434218a11'}
OWNED = ['tools/render_ui_popup.py', 'tools/ui_pixel_scene.py', 'tools/civ5_ui_assets.py',
         'tools/ui_bitmap_fonts.py', 'Tests/ui_pixel_scene.py', 'Tests/civ5_ui_assets.py', 'Tests/ui_bitmap_fonts.py']


def artifact(path):
    path = Path(path).resolve(strict=True)
    return {'path': str(path), 'sha256': sha256(path), 'bytes': path.stat().st_size}


def check_artifact(row):
    require(type(row) is dict and Path(row['path']).is_file() and sha256(row['path']) == row['sha256'], 'Artifact hash mismatch')


def freeze(path, destination):
    require(not destination.exists() and not destination.is_symlink(), 'Refusing to overwrite frozen input')
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(path, destination)
    require(sha256(path) == sha256(destination), 'Frozen source copy differs')
    return {'original_path': str(Path(path).resolve()), **artifact(destination)}


def runtime_binding(runtime, language, sdk_run, directory):
    """Bind locale/state to the sealed invocation and exact host/GameCore bytes."""
    root = (PROJECT / 'Build/NewGameRuntime' / sdk_run).resolve(strict=True)
    request_row = runtime['request']
    require(Path(request_row['path']).resolve() ==
            (PROJECT / 'evidence/save_restore' / sdk_run / 'request.json').resolve(),
            'Runtime request is not from the selected unique SDK run')
    check_artifact(request_row)
    request = json.loads(Path(request_row['path']).read_text(encoding='utf-8'))
    require(request['run_id'] == sdk_run and Path(request['cwd']).resolve() == root and
            request['command'] == [str(root / 'ZeroSisHost_x64.exe'),
                                   '--check-save-restore-ui-actions', language, '48'],
            'Retained popup locale/invocation differs from selected SDK execution')
    require(request['ui_popups_enabled'] is True and request['session_activation'] ==
            {'source': 'COMPILED_HOST_FIXED_CONFIGURATION', 'active_mods': []} and
            runtime['session_active_mods'] == [0, 0] and runtime['accepted_bundle_unchanged'] is True,
            'Retained popup profile/mod activation is not the accepted isolated fixture')
    frozen = {}
    for name in ('candidate_build', 'accepted_bundle', 'found_value_sdk_build'):
        check_artifact(request[name])
        frozen[name] = freeze(request[name]['path'], directory / (name + '.json'))
    require(Path(request['accepted_bundle']['path']).resolve() ==
            (PROJECT / 'evidence/host/bundle.json').resolve(), 'Unexpected accepted host bundle')
    host = json.loads(Path(request['candidate_build']['path']).read_text(encoding='utf-8'))
    sdk = json.loads(Path(request['found_value_sdk_build']['path']).read_text(encoding='utf-8'))
    require(sdk['status'] == 'FOUND_VALUE_SHARED_SDK_CANDIDATE_LINKED' and sdk['inputs_unchanged'] is True,
            'Selected SDK input is not the sealed shared-FoundValue build')
    check_artifact(host['executable'])
    check_artifact(sdk['gamecore'])
    inputs = request['inputs']
    require(len({str(Path(row['path']).resolve()) for row in inputs}) == len(inputs),
            'Duplicate runtime input binding')
    for row in inputs:
        require(Path(row['path']).resolve().is_relative_to(root), 'Runtime input escaped its unique candidate')
        check_artifact(row)
    for basename, source in (('ZeroSisHost_x64.exe', host['executable']),
                             ('CvGameCoreDLL_Expansion2_x64.dll', sdk['gamecore'])):
        selected = [row for row in inputs if Path(row['path']).resolve() == root / basename]
        require(len(selected) == 1 and selected[0]['sha256'] == source['sha256'] and
                Path(selected[0]['source']).resolve() == Path(source['path']).resolve(),
                'Runtime executable bytes/source differ from sealed build: ' + basename)
    frozen['request'] = freeze(request_row['path'], directory / 'runtime_request.json')
    return {'language': language, 'command': request['command'], 'cwd': str(root),
            'active_mods': [], 'fixture_promotions_enabled': request['fixture_promotions_enabled'],
            'host': artifact(root / 'ZeroSisHost_x64.exe'),
            'gamecore': artifact(root / 'CvGameCoreDLL_Expansion2_x64.dll'),
            'inputs': inputs, 'frozen_proofs': frozen}


def retained_bounds(snapshot, geometry, *, context='ranking'):
    """Compare independently captured runtime bounds, excluding unmeasured controls."""
    actual = {row['key']: row for row in geometry if not row['style_decoration']}
    checked, deferred = [], []

    def visit(node, parent_kind=None):
        if node['hidden']:
            return
        if node['kind'] == 'GridData':
            # Inline GridData is nine-slice source data consumed by its
            # owning GridButton; it has no independent runtime geometry.
            require(context == 'research' and parent_kind == 'GridButton' and
                    node['width'] == 0 and node['height'] == 0 and not node['children'],
                    'GridData is only valid as zero-area TechPopup GridButton draw data')
            return
        key = node['key']
        require(key in actual, 'Visible retained control was omitted from the rendered scene')
        if node['kind'] == 'Label' or not node['width'] or not node['height']:
            deferred.append({'key': key, 'kind': node['kind'],
                             'reason': 'runtime label/style extent not measured'})
        else:
            expected = [node[name] for name in ('x', 'y', 'width', 'height')]
            require(all(abs(a - b) < 1e-5 for a, b in zip(expected, actual[key]['bounds'])),
                    'Scene geometry differs from actual retained runtime bounds: ' + str(key))
            checked.append({'key': key, 'kind': node['kind'], 'bounds': expected})
        if context in ('production', 'research') and node['kind'] == 'ShowOnMouseOver':
            hovered = node.get('hovered')
            require(type(hovered) is bool, 'ShowOnMouseOver lacks captured hover state during bounds verification')
            if not hovered:
                return
        for child in node['children']:
            visit(child, node['kind'])

    visit(snapshot['tree'])
    if context == 'ranking':
        require(any(row['key'] == 12 and row['kind'] == 'GridButton' for row in checked),
                'Actual CloseButton bounds were not independently checked')
    elif context == 'production':
        require(any(row['kind'] == 'GridButton' and row.get('id') == 'CloseButton' for row in actual.values()),
                'Production snapshot has no retained CloseButton')
    else:
        require(any(row['kind'] == 'GridButton' and row.get('id') == 'OpenTTButton'
                    for row in actual.values()), 'Research snapshot has no retained OpenTTButton')
    return {'context': context, 'checked': checked, 'deferred': deferred,
            'retail_layout_equivalence_verified': False}


def portrait_readback(snapshot, manifest, pixels):
    """Compare opaque interior atlas samples using the native linear sampler."""
    portraits = []

    def visit(node):
        if node['hidden']:
            return
        if node['kind'] == 'Image' and node.get('id') == 'Portrait':
            portraits.append(node)
        for child in node['children']:
            visit(child)

    visit(snapshot['tree'])
    require(len(portraits) == 2, 'Selected SDK popup needs two separately bound portrait controls')
    rows = []
    for node in portraits:
        name = node['texture'].replace('\\', '/').rsplit('/', 1)[-1].casefold()
        assets = [row for row in manifest['selected_assets'] if row['basename'] == name]
        require(len(assets) == 1, 'Portrait has no unique original atlas binding')
        check_artifact(assets[0]['output'])
        data = Path(assets[0]['output']['path']).read_bytes()
        words = header(data)
        rgba32(words)
        require((node['width'], node['height']) == (64, 64), 'Unexpected actual portrait size')
        colors, samples = set(), 0
        # The central 32x32 area is inside the portrait, away from frames,
        # neighboring civ icons, row separators and panel clipping edges.
        for y in range(math.ceil(node['y'] + 16), math.floor(node['y'] + 48)):
            for x in range(math.ceil(node['x'] + 16), math.floor(node['x'] + 48)):
                # BitmapRenderer uses linear interpolation. Account for the
                # half-pixel target anchor by sampling at pixel centers.
                sx = node['textureX'] + x - node['x']
                sy = node['textureY'] + y - node['y']
                ix, iy = math.floor(sx), math.floor(sy)
                fx, fy = sx - ix, sy - iy
                neighbors = []
                for dx, dy, weight in ((0, 0, (1-fx)*(1-fy)), (1, 0, fx*(1-fy)),
                                        (0, 1, (1-fx)*fy), (1, 1, fx*fy)):
                    if not weight:
                        continue
                    require(0 <= ix+dx < words[4] and 0 <= iy+dy < words[3],
                            'Portrait sample escaped original atlas')
                    offset = 128 + ((iy+dy) * words[4] + ix+dx) * 4
                    b, g, r, a = data[offset:offset + 4]
                    neighbors.append(((r, g, b, a), weight))
                if any(color[3] != 255 for color, _ in neighbors):
                    continue
                expected = tuple(math.floor(sum(color[c] * weight for color, weight in neighbors) + 0.5)
                                 for c in range(4))
                actual_offset = (y * 1920 + x) * 4
                require(all(abs(a-b) <= 1 for a, b in zip(pixels[actual_offset:actual_offset + 4], expected)),
                        'Native portrait pixels differ from original atlas for control ' + str(node['key']))
                colors.add(expected)
                samples += 1
        require(samples >= 128 and len(colors) >= 16, 'Original portrait interior is empty or uninformative')
        rows.append({'control_key': node['key'], 'texture': node['texture'],
                     'atlas_offset': [node['textureX'], node['textureY']],
                     'opaque_interior_samples': samples, 'distinct_source_rgba_values': len(colors),
                     'sampling': 'linear interpolation at pixel centers; opaque neighbors only',
                     'channel_tolerance': 1,
                     'all_opaque_samples_match_original_atlas': True,
                     'retail_pixels_verified': False})
    return rows


def png_pixels(path, *, expected_dimensions=(1920, 1080)):
    """Strict bounded RGBA PNG readback for pixel evidence, no image edits."""
    require(isinstance(expected_dimensions, (tuple, list)) and len(expected_dimensions) == 2 and
            all(type(value) is int and 0 < value <= 32768 for value in expected_dimensions),
            'Invalid expected PNG dimensions')
    path = Path(path)
    require(path.stat().st_size <= 256 * 1024 * 1024, 'PNG file exceeds its byte bound')
    data = path.read_bytes()
    require(data[:8] == b'\x89PNG\r\n\x1a\n', 'Renderer output is not PNG')
    pos, packed, ihdr, ended, saw_idat, idat_closed, chunk_count = 8, bytearray(), None, False, False, False, 0
    while pos < len(data):
        chunk_count += 1
        require(chunk_count <= 65536, 'PNG chunk count exceeds its bound')
        require(pos + 12 <= len(data), 'Truncated PNG chunk')
        size, = struct.unpack_from('>I', data, pos)
        require(size <= 16 * 1024 * 1024 and pos + size + 12 <= len(data), 'Unbounded/truncated PNG chunk')
        kind = data[pos + 4:pos + 8]
        require(not ended, 'PNG chunk follows IEND')
        payload = data[pos + 8:pos + 8 + size]
        crc, = struct.unpack_from('>I', data, pos + 8 + size)
        require(zlib.crc32(kind + payload) & 0xffffffff == crc, 'PNG CRC differs')
        if kind == b'IHDR':
            require(ihdr is None and pos == 8 and size == 13, 'Duplicate/invalid PNG header')
            ihdr = struct.unpack('>IIBBBBB', payload)
        elif kind == b'IDAT':
            require(ihdr is not None and not idat_closed, 'Invalid/noncontiguous PNG image data')
            require(len(packed) + size <= 256 * 1024 * 1024, 'PNG compressed data exceeds its byte bound')
            packed += payload
            saw_idat = True
        elif kind == b'IEND':
            require(size == 0 and saw_idat and pos + 12 == len(data), 'Invalid PNG end')
            ended = True
        elif saw_idat:
            idat_closed = True
        pos += size + 12
    require(ended and ihdr is not None, 'Incomplete PNG image')
    width, height = ihdr[:2]
    require(0 < width <= 32768 and 0 < height <= 32768 and
            width * height * 4 <= 256 * 1024 * 1024,
            'PNG dimensions exceed bounded pixel storage')
    require((width, height) == tuple(expected_dimensions) and ihdr[2:] == (8, 6, 0, 0, 0),
            f'Expected noninterlaced 8-bit RGBA PNG {tuple(expected_dimensions[0:2])}')
    stride = width * 4
    decoder = zlib.decompressobj()
    raw = decoder.decompress(packed, (stride + 1) * height + 1)
    require(len(raw) == (stride + 1) * height and decoder.eof and not decoder.unconsumed_tail and not decoder.unused_data,
            'Invalid bounded PNG pixel stream')
    pixels = bytearray(stride * height)
    prev = bytearray(stride)
    for y in range(height):
        start = y * (stride + 1)
        filt = raw[start]
        require(filt <= 4, 'Unsupported PNG filter')
        row = bytearray(raw[start + 1:start + 1 + stride])
        for x in range(stride):
            a = row[x - 4] if x >= 4 else 0
            b = prev[x]
            c = prev[x - 4] if x >= 4 else 0
            if filt == 1:
                prediction = a
            elif filt == 2:
                prediction = b
            elif filt == 3:
                prediction = (a + b) // 2
            elif filt == 4:
                p = a + b - c
                da, db, dc = abs(p - a), abs(p - b), abs(p - c)
                prediction = a if da <= db and da <= dc else b if db <= dc else c
            else:
                prediction = 0
            row[x] = (row[x] + prediction) & 255
        pixels[y * stride:(y + 1) * stride] = row
        prev = row
    return pixels


def prepare(snapshot_path, directory, manifest_path, *, closed=False, context='ranking'):
    snapshot_hash = sha256(snapshot_path)
    snapshot = json.loads(Path(snapshot_path).read_text(encoding='utf-8'))
    color_source = json.loads((directory / 'inline_colors.json').read_text(encoding='utf-8'))
    require(context in ('ranking', 'production', 'research'), 'Unknown selected popup context')
    icon_path = directory / 'inline_icons.json'
    require(context not in ('production', 'research') or icon_path.is_file(),
            'Selected live popup context requires prepared original FontIcons mapping and glyph provenance')
    icon_source = json.loads(icon_path.read_text(encoding='utf-8')) if icon_path.is_file() else {}
    require(context not in ('production', 'research') or type(icon_source.get('icons')) is dict,
            'Selected live popup inline icon mapping is malformed')
    snapshot_clock = snapshot.get('presentationClock', 0)
    compiler = Compiler(GAME, directory, inline_colors=color_source['colors'],
                        inline_icons=icon_source.get('icons', {}), context=context,
                        snapshot_clock=snapshot_clock)
    packet = directory / 'scene.packet'
    packet.write_bytes(compiler.compile(snapshot, closed=closed))
    frozen_ui = []
    originals = {compiler.styles_path, *compiler.context_sources}
    for row in compiler.font_records:
        originals.add(Path(row['ggxml_path']))
        originals.add(Path(row['color_atlas_path']))
    for index, source in enumerate(sorted(originals)):
        # Keep the exact original path/hash in the manifest while avoiding
        # MAX_PATH in the deeper live SDK session directory.
        frozen_ui.append(freeze(source, directory / 'source_ui' / f'{index:02d}_{source.name}'))
    require(compiler.unchanged() and sha256(snapshot_path) == snapshot_hash, 'UI/assets or actual SDK snapshot changed during compilation')
    bounds_check = ({'checked': [], 'deferred': [], 'inactive_context_not_drawn': True,
                     'retail_layout_equivalence_verified': False} if closed else
                    retained_bounds(snapshot, compiler.geometry, context=context))
    context_name = {'production': 'ProductionPopup', 'research': 'TechPopup',
                    'ranking': 'WhosWinningPopup'}[context]
    popup_kind = {'production': 'Production', 'research': 'Research',
                  'ranking': 'WhosWinning'}[context]
    event_targets = [target for target in snapshot.get('inputTargets', []) if type(target) is dict]
    right_targets = [target for target in event_targets if target.get('event') == 'RightClick']
    manifest = {'status': 'ACTUAL_SDK_CLOSED_POPUP_EMPTY_SCENE_COMPILED' if closed else
                          'ACTUAL_SDK_RETAINED_POPUP_SCENE_COMPILED', 'packet': artifact(packet),
                'snapshot': artifact(snapshot_path), 'snapshot_state_unchanged': True,
                'context': context,
                'context_name': context_name,
                'popup_kind': popup_kind,
                'presentation_clock': snapshot_clock,
                'animation_policy': snapshot.get('animationPolicy') if context in ('production', 'research') else None,
                'retail_timing_verified': snapshot.get('retailTimingVerified', False) if context in ('production', 'research') else False,
                'original_context_sources': [{'path': str(path), 'sha256': digest}
                                             for path, digest in sorted(compiler.context_sources.items())],
                'closed_context_not_drawn': closed,
                'width': compiler.width, 'height': compiler.height, 'geometry': compiler.geometry,
                'labels': compiler.labels, 'hit_regions': compiler.hits,
                'scroll_regions': compiler.scroll_regions,
                'scroll_region_policy': ('Visible vertical ScrollPanel clippedBounds; exact scrollY/contentHeight/viewportHeight/maximumScroll checked against retained state; input wheel semantics unverified'
                                         if context in ('production', 'research') else 'not encoded in ranking ZSUPIX01'),
                'scroll_region_provenance': ({'snapshot': artifact(snapshot_path),
                                              'field': 'scrollTargets',
                                              'tree_crosscheck': 'visible vertical retained ScrollPanels; exact viewport, ancestor clipping, offset and content extent'}
                                             if context in ('production', 'research') else None),
                'packet_version': 'ZSUPIX02' if context in ('production', 'research') else 'ZSUPIX01',
                'input_target_policy': ('registered visible enabled LeftClick controls; bounds and ScrollPanel clipping independently checked against retained XYWH'
                                        if context == 'production' else
                                        'Research retains and crosschecks LeftClick/RightClick callback provenance; ZSUPIX02 encodes LeftClick rectangles only'
                                        if context == 'research' else 'selected ranking GridButton close target'),
                'input_target_count': len(compiler.hits),
                'retained_input_targets': event_targets if context in ('production', 'research') else [],
                'unencoded_right_click_target_count': len(right_targets) if context == 'research' else 0,
                'native_right_click_supported': False if context == 'research' else None,
                'pedia_context_supported': False if context == 'research' else None,
                'scroll_region_count': len(compiler.scroll_regions),
                'input_callback_coverage_claimed': False,
                'retail_input_semantics_verified': False,
                'derived_animation_textures': compiler.derived_textures,
                'scroll_thumb_policy': ('original VertShuttle minimum Size plus retained track/content/scroll range; proportional thumb is owned frontend candidate geometry, source engine geometry unverified' if context == 'research' else
                                        'captured scrollY/contentHeight, captured viewport size, original style minimum; frontend estimate only, retail geometry unverified'),
                'retained_runtime_bounds_check': bounds_check,
                'sprite_count': len(compiler.sprites), 'texture_count': len(compiler.textures),
                'asset_pack_policy': list(PACK_POLICY), 'retail_asset_priority_verified': False,
                'pack_sources': compiler.assets.pack_records, 'selected_assets': compiler.assets.records,
                'selected_original_images': [{'requested_name': row['requested_name'],
                                              'source': row['source'],
                                              'conversion': row['conversion'], 'output': row['output']}
                                             for row in compiler.assets.records],
                'font_sources': compiler.font_records, 'frozen_ui': frozen_ui,
                'inline_color_source': artifact(directory / 'inline_colors.json'),
                'inline_icon_source': artifact(icon_path) if icon_path.is_file() else None,
                'candidate_policy_limits': ['font horizontal/baseline/effect compositing not retail-calibrated',
                    'shadow mask cell-border sampling not retail-calibrated',
                    'Full style dimensions interpreted against viewport', 'nine-slice mixed edge metrics not retail-calibrated',
                    'tooltip UI is retained but not rasterized',
                    'Production Meter draws original asset clipped to captured percent plus percentPlus in a candidate clockwise arc from twelve oclock; retail meter semantics unverified',
                    'ScrollAnim mask uses source alpha times original mask alpha at captured owner clock/phase; retail shader equivalence unverified'] +
                    (['TechPopup ScrollBar thumb uses an owned proportional layout rule and original VertShuttle size; source engine thumb geometry unverified',
                      'TechPopup right-click pedia callbacks are retained as metadata but not encoded by native hit packet; pedia interaction unsupported']
                     if context == 'research' else []),
                'gamecore_executed': False, 'installed_game_launched': False, 'stage_promoted': False,
                'retail_pixels_verified': False}
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def execute(command, cwd, log):
    process = subprocess.run([str(arg) for arg in command], cwd=cwd, capture_output=True,
                             timeout=60, creationflags=subprocess.CREATE_NO_WINDOW)
    output = process.stdout.decode('utf-8', errors='replace')
    errors = process.stderr.decode('utf-8', errors='replace')
    log.write_text(output + errors, encoding='utf-8')
    require(process.returncode == 0, 'Isolated presentation command failed: ' + str(log) + '\n' + (output + errors)[-2000:])
    return output, artifact(log)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare', type=Path)
    parser.add_argument('--directory', type=Path)
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--closed', action='store_true', help='Prepare the empty contribution of an officially dequeued popup context')
    parser.add_argument('--context', choices=('ranking', 'production', 'research'), default='ranking',
                        help='Select the explicit original UI layout context for retained-state compilation')
    args = parser.parse_args()
    if args.prepare:
        require(args.directory is not None and args.manifest is not None, 'Missing scene destinations')
        prepare(args.prepare, args.directory, args.manifest, closed=args.closed, context=args.context)
        return 0
    require(args.context == 'ranking', 'Live popup contexts require an explicitly captured SDK snapshot via --prepare')
    require(not args.closed, '--closed requires an explicit captured SDK state and scene destinations')
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ_') + uuid.uuid4().hex[:12]
    build = PROJECT / 'Build/UiPopupPixels' / run_id
    evidence = PROJECT / 'evidence/ui_popup_pixels' / run_id
    build.mkdir(parents=True)
    evidence.mkdir(parents=True)
    report = {'status': 'UI_POPUP_PIXEL_CANDIDATE_FAILED', 'run_id': run_id,
              'scope': 'OFFSCREEN_PIXELS_FROM_RETAINED_ACTUAL_SDK_POPUP_STATE',
              'gamecore_executed': False, 'installed_game_launched': False, 'stage_promoted': False,
              'mods_written': False, 'retail_pixel_equivalence_verified': False,
              'native_window_input_verified': False, 'world_renderer_verified': False,
              'source_inputs_unchanged': False, 'frozen_inputs': [], 'tests': [], 'scenes': [], 'error': None}
    originals = [PROJECT / name for name in OWNED]
    before = {str(path): sha256(path) for path in originals}
    try:
        for source in originals:
            report['frozen_inputs'].append(freeze(source, build / 'frozen' / source.relative_to(PROJECT)))
        report['python'] = artifact(sys.executable)
        renderer_path = PROJECT / 'evidence/bitmap_renderer' / RENDERER_PROOF / 'conformance.json'
        renderer = json.loads(renderer_path.read_text(encoding='utf-8'))
        require(renderer['status'] == 'BITMAP_RENDERER_COMPONENT_PASS' and renderer['source_inputs_unchanged'] is True,
                'No accepted immutable native renderer component')
        for row in renderer['frozen_inputs'].values():
            check_artifact(row)
        cli = renderer['renderer_artifact']
        executable = Path(cli['executable'])
        require(sha256(executable) == cli['executable_sha256'], 'Native renderer CLI differs from component proof')
        report['renderer_component'] = freeze(renderer_path, build / 'frozen' / 'renderer_component.json')
        report['renderer_executable'] = artifact(executable)
        for test in ('civ5_ui_assets.py', 'ui_bitmap_fonts.py', 'ui_pixel_scene.py'):
            output, log = execute([sys.executable, '-B', '-X', 'utf8', build / 'frozen/Tests' / test],
                                  build, evidence / (test + '.log'))
            report['tests'].append({'test': test, 'log': log, 'output': Path(log['path']).read_text(encoding='utf-8').strip()})
        for language, sdk_run in RUNTIME.items():
            runtime_path = PROJECT / 'evidence/save_restore' / sdk_run / 'result.json'
            runtime = json.loads(runtime_path.read_text(encoding='utf-8'))
            require(runtime['status'] == 'ISOLATED_NATIVE_SAVE_RESTORE_EXTENDED_PASS' and
                    runtime['candidate_inputs_unchanged'] is True and runtime['cleanup_completed'] is True and
                    runtime['module_unloaded'] is True, 'Selected SDK runtime is not accepted/clean')
            snapshots = sorted((row for row in runtime['generated_files'] if row['path'].endswith('ui-popup-1-shown.json')),
                               key=lambda row: row['path'])
            require(snapshots, 'No sealed actual SDK popup snapshot')
            selected = snapshots[0]
            check_artifact(selected)
            require(Path(selected['path']).resolve().is_relative_to(PROJECT / 'Build/NewGameRuntime' / sdk_run),
                    'Runtime snapshot escaped selected unique SDK run')
            directory = build / language
            directory.mkdir()
            binding = runtime_binding(runtime, language, sdk_run, directory)
            snapshot = freeze(selected['path'], directory / 'snapshot.json')
            runtime_proof = freeze(runtime_path, directory / 'runtime_result.json')
            database = Path(selected['path']).parent / 'rules.db'
            bindings = [row for row in runtime['generated_files'] if Path(row['path']).resolve() == database.resolve()]
            require(len(bindings) == 1, 'Selected actual SDK color database has no unique runtime binding')
            check_artifact(bindings[0])
            with sqlite3.connect(database.resolve().as_uri() + '?mode=ro', uri=True) as connection:
                rows = connection.execute('SELECT Type, Red, Green, Blue, Alpha FROM Colors WHERE Type LIKE ?', ('COLOR_%',)).fetchall()
            colors = {row[0]: list(row[1:]) for row in rows}
            require(len(colors) == len(rows), 'Duplicate actual SDK database color key')
            (directory / 'inline_colors.json').write_text(json.dumps({'database': bindings[0], 'colors': colors},
                                                                           ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            manifest_path = directory / 'scene_manifest.json'
            _, prepare_log = execute([sys.executable, '-B', '-X', 'utf8', build / 'frozen/tools/render_ui_popup.py',
                                      '--prepare', snapshot['path'], '--directory', directory, '--manifest', manifest_path],
                                     build, evidence / (language + '_prepare.log'))
            manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
            check_artifact(manifest['packet'])
            png = directory / 'popup.png'
            output, native_log = execute([executable, manifest['packet']['path'], png], build,
                                         evidence / (language + '_native.log'))
            expected = f"BITMAP_RENDER_PASS width=1920 height=1080 sprites={manifest['sprite_count']} textures={manifest['texture_count']} hits=1 scope=OFFSCREEN_D2D_WIC"
            require(output.strip() == expected, 'Native renderer output/counts differ from compiled scene')
            pixels = png_pixels(png)
            require(tuple(pixels[:4]) == (0, 0, 0, 0), 'Source clear top bar became opaque')
            bg = tuple(pixels[(35 * 1920) * 4:(35 * 1920) * 4 + 4])
            require(bg == (0, 0, 0, 200), 'Original background style alpha was lost')
            portrait_checks = portrait_readback(json.loads(Path(snapshot['path']).read_text(encoding='utf-8')),
                                                manifest, pixels)
            require(manifest['hit_regions'] == [[12, 745.0, 804.0, 895.0, 836.0]], 'Real CloseButton geometry differs')
            require(sha256(snapshot['path']) == snapshot['sha256'] and sha256(selected['path']) == selected['sha256'],
                    'Rendering changed original or retained SDK UI state')
            report['scenes'].append({'language': language, 'sdk_run': sdk_run, 'snapshot': snapshot,
                'runtime_binding': binding,
                'runtime_result': runtime_proof, 'manifest': artifact(manifest_path), 'packet': manifest['packet'],
                'png': artifact(png), 'native_log': native_log, 'prepare_log': prepare_log,
                'portrait_readback': portrait_checks,
                'retained_runtime_bounds_check': manifest['retained_runtime_bounds_check'],
                'clear_top_pixel_rgba': [0, 0, 0, 0],
                'source_background_pixel_rgba': list(bg), 'snapshot_state_unchanged': True,
                'width': 1920, 'height': 1080, 'sprite_count': manifest['sprite_count'],
                'texture_count': manifest['texture_count'], 'hit_regions': manifest['hit_regions']})
        after = {str(path): sha256(path) for path in originals}
        require(after == before and sha256(executable) == report['renderer_executable']['sha256'], 'Presentation inputs changed')
        report.update(status='RETAINED_ACTUAL_SDK_UI_OFFSCREEN_PIXELS_PASS', source_inputs_unchanged=True,
                      source_hashes_before=before, source_hashes_after=after)
    except Exception as error:
        report['error'] = str(error)
    report_path = evidence / 'conformance.json'
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': report['status'], 'report': str(report_path), 'sha256': sha256(report_path), 'error': report['error']}, ensure_ascii=False))
    return 0 if report['status'] == 'RETAINED_ACTUAL_SDK_UI_OFFSCREEN_PIXELS_PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
