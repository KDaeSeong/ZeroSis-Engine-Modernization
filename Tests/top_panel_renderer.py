"""Compile and offscreen-render the stock TopPanel component snapshot.

All generated packets, atlases, logs, and pixels stay in a temporary directory.
This is component-fixture proof, not an in-game SDK capture, retail UI pixel
equivalence, live Host compositing, or completion of unrelated callbacks.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile

PROJECT = Path(__file__).resolve().parents[1]
TOOLS = PROJECT / 'tools'
sys.path.insert(0, str(TOOLS))

from civ5_ui_assets import require, sha256
from ui_pixel_scene import (close_stock_top_panel_negative_gold_label, markup,
                            top_panel_interaction_contract, wrap_production_text)
from ui_bitmap_fonts import Glyph, load_font
import render_ui_popup


def artifact(path: Path) -> dict:
    path = Path(path).resolve(strict=True)
    return {'path': str(path), 'sha256': sha256(path), 'bytes': path.stat().st_size}


def visible_nodes(root):
    rows = []

    def visit(node, parent_visible=True):
        visible = parent_visible and node.get('hidden') is False
        if visible:
            rows.append(node)
        for child in node.get('children', []):
            visit(child, visible)

    visit(root)
    return rows


def verify_original_bar_layout(snapshot: dict, manifest: dict) -> dict:
    """Keep the original right Stack, captions, and packet hits inside its bar."""
    nodes = visible_nodes(snapshot['tree'])
    stacks = [node for node in nodes if node['kind'] == 'Stack' and
              node['sourceAttributes'].get('Anchor') == 'R,T' and
              node['sourceAttributes'].get('StackGrowth') == 'Left']
    require(len(stacks) == 1, 'Original right TopPanel Stack is not unique')
    stack = stacks[0]
    attrs = stack['sourceAttributes']
    require('Size' not in attrs and attrs.get('Offset') == '10,4' and
            attrs.get('Padding') == '10', 'Original right TopPanel Stack declaration changed')
    children = [node for node in stack['children'] if node['hidden'] is False]
    width = sum(node['width'] for node in children) + 10 * (len(children) - 1)
    height = max(node['height'] for node in children)
    require(stack['width'] == width > 0 and stack['height'] == height > 0 and
            stack['x'] == snapshot['tree']['width'] - width - 10 and stack['y'] == 4,
            'Original right TopPanel Stack was not measured before anchoring')
    bars = [node for node in nodes if node['kind'] == 'Image' and
            node['sourceAttributes'].get('Size') == 'Full.32']
    require(len(bars) == 1 and bars[0]['height'] == 32 and bars[0]['y'] == 0,
            'Original 32px TopPanel bar changed')
    by_id = {node['id']: node for node in nodes if node['id']}
    labels = {row['key']: row for row in manifest['labels']}
    hits = {row[0]: row[1:] for row in manifest['hit_regions']}
    captions = {}
    for control_id in ('MenuButton', 'CivilopediaButton', 'CurrentTurn', 'CurrentDate'):
        node = by_id[control_id]
        bounds = [node[field] for field in ('x', 'y', 'width', 'height')]
        x, y, w, h = bounds
        require(x >= 0 and y >= 0 and x + w <= snapshot['tree']['width'] and y + h <= 32 and
                labels[node['key']]['bounds'] == bounds,
                'Original TopPanel caption escapes its bar or differs from the packet: ' + control_id)
        if control_id in ('MenuButton', 'CivilopediaButton'):
            require(hits[node['key']] == [x, y, x + w, y + h],
                    'Original TopPanel hit is clipped or differs from its caption: ' + control_id)
        captions[control_id] = bounds
    return {'right_stack': [stack[k] for k in ('x', 'y', 'width', 'height')],
            'captions': captions, 'original_bar_height': 32, 'clipped_right_hits': False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path, required=True,
                        help='Prepared stock TopPanel component snapshot JSON')
    parser.add_argument('--rules-db', type=Path, required=True,
                        help='Read-only rules.db supplying original COLOR_ bindings')
    parser.add_argument('--inline-icons', type=Path, required=True,
                        help='Prepared original FontIcons mapping with provenance')
    parser.add_argument('--game-root', type=Path, default=render_ui_popup.GAME,
                        help='Installed Civ V root containing the frozen original UI/assets')
    parser.add_argument('--renderer', type=Path, required=True,
                        help='Accepted native offscreen bitmap renderer executable')
    parser.add_argument('--actual-hidden-snapshot', type=Path,
                        help='Optional real SDK-captured no-city TopPanel snapshot for independent hidden-state render validation')
    parser.add_argument('--result', type=Path,
                        help='Optional small JSON report destination; pixels remain temporary')
    args = parser.parse_args()
    snapshot_path = args.snapshot.resolve(strict=True)
    component_result_path = snapshot_path.parent / 'result.json'
    tooltip_snapshot_path = snapshot_path.parent / 'tooltip-snapshot.json'
    database_path = args.rules_db.resolve(strict=True)
    icons_path = args.inline_icons.resolve(strict=True)
    game_root = args.game_root.resolve(strict=True)
    renderer = args.renderer.resolve(strict=True)
    require(snapshot_path.is_file() and component_result_path.is_file() and
            tooltip_snapshot_path.is_file() and database_path.is_file() and
            icons_path.is_file() and renderer.is_file(),
            'TopPanel test input is missing')

    snapshot_hash = sha256(snapshot_path)
    component_result_hash = sha256(component_result_path)
    tooltip_snapshot_hash = sha256(tooltip_snapshot_path)
    database_hash = sha256(database_path)
    icons_hash = sha256(icons_path)
    layout = game_root / 'Assets/DLC/Expansion2/UI/InGame/TopPanel.xml'
    script = game_root / 'Assets/DLC/Expansion2/UI/InGame/TopPanel.lua'
    styles = game_root / 'Assets/UI/Styles.xml'
    source_hashes = {str(path.resolve(strict=True)): sha256(path) for path in (layout, script, styles)}
    component_result = json.loads(component_result_path.read_text(encoding='utf-8'))
    fixture = component_result.get('fixture')
    require(component_result.get('status') == 'PASS_TOP_PANEL_ORIGINAL_LUA_COMPONENT_ONLY' and
            type(fixture) is dict and fixture.get('componentOnly') is True and
            fixture.get('retailSdkRendererAndGameVerified') is False and
            component_result.get('original_source_sha256') == {
                'TopPanel.lua': source_hashes[str(script.resolve())],
                'TopPanel.xml': source_hashes[str(layout.resolve())]},
            'TopPanel snapshot is not bound to its original component-fixture provenance')
    tooltip_snapshot = json.loads(tooltip_snapshot_path.read_text(encoding='utf-8'))
    tooltip_record = tooltip_snapshot.get('topPanelTooltip')
    require(type(tooltip_record) is dict and tooltip_record.get('type') == 'TooltipTypeTopPanel' and
            type(tooltip_record.get('tree')) is dict and
            tooltip_record['tree'].get('autoSizeRequested') is True and
            tooltip_record.get('retailPlacementVerified') is False and
            tooltip_record.get('retailAutosizeVerified') is False,
            'Original tooltip callback snapshot lacks its unverified placement/autosize provenance')

    renderer_proof_path = PROJECT / 'evidence/bitmap_renderer/20261003T045102Z_7152c411ded8/conformance.json'
    renderer_proof = json.loads(renderer_proof_path.read_text(encoding='utf-8'))
    renderer_proof_row = renderer_proof.get('renderer_artifact', {})
    require(renderer_proof.get('status') == 'BITMAP_RENDERER_COMPONENT_PASS' and
            renderer_proof.get('source_inputs_unchanged') is True and
            Path(renderer_proof_row.get('executable', '')).resolve(strict=True) == renderer and
            renderer_proof_row.get('executable_sha256') == sha256(renderer),
            'Native renderer is not the immutable ZSUPIX02-capable component proof artifact')
    icon_map = json.loads(icons_path.read_text(encoding='utf-8'))
    require(type(icon_map) is dict and type(icon_map.get('icons')) is dict,
            'Prepared original inline icon mapping is malformed')

    with sqlite3.connect(database_path.as_uri() + '?mode=ro', uri=True) as connection:
        color_rows = connection.execute(
            'SELECT Type, Red, Green, Blue, Alpha FROM Colors WHERE Type LIKE ?', ('COLOR_%',)).fetchall()
    colors = {row[0]: list(row[1:]) for row in color_rows}
    require(colors and len(colors) == len(color_rows),
            'Actual SDK rules database has no unique original COLOR_ bindings')

    with tempfile.TemporaryDirectory(prefix='zerosistoppanel-') as temporary:
        directory = Path(temporary).resolve(strict=True)
        shutil.copyfile(icons_path, directory / 'inline_icons.json')
        require(sha256(directory / 'inline_icons.json') == icons_hash,
                'Prepared original inline icon mapping changed while staging the test')
        (directory / 'inline_colors.json').write_text(json.dumps(
            {'database': artifact(database_path), 'colors': colors}, ensure_ascii=False, indent=2) + '\n',
            encoding='utf-8')
        render_ui_popup.GAME = game_root
        manifest_path = directory / 'scene_manifest.json'
        render_ui_popup.prepare(snapshot_path, directory, manifest_path, context='top-panel')
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        packet = Path(manifest['packet']['path']).resolve(strict=True)
        png = directory / 'top-panel.png'
        process = subprocess.run([str(renderer), str(packet), str(png)], cwd=directory,
                                 capture_output=True, timeout=120,
                                 creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        stdout = process.stdout.decode('utf-8', errors='replace').strip()
        stderr = process.stderr.decode('utf-8', errors='replace')
        require(process.returncode == 0 and not stderr.strip(),
                f'Native TopPanel offscreen renderer failed with exit={process.returncode}: ' +
                (stdout + '\n' + stderr)[-2000:])
        require(stdout == f"BITMAP_RENDER_PASS width=1920 height=1080 sprites={manifest['sprite_count']} "
                          f"textures={manifest['texture_count']} hits={len(manifest['hit_regions'])} "
                          'scope=OFFSCREEN_D2D_WIC',
                'Native renderer counts differ from the original TopPanel scene packet')

        snapshot = json.loads(snapshot_path.read_text(encoding='utf-8'))
        original_bar_layout = verify_original_bar_layout(snapshot, manifest)
        targets = snapshot['inputTargets']
        interaction = top_panel_interaction_contract(snapshot)
        require(interaction['info_stack_hidden'] is False and
                interaction['science_callback_available'] is True,
                'Visible component fixture does not exercise the original SciencePerTurn target')
        hidden_snapshot = copy.deepcopy(snapshot)
        hidden_stack = []
        def find_info_stack(node):
            if type(node) is dict:
                if node.get('id') == 'TopPanelInfoStack':
                    hidden_stack.append(node)
                for child in node.get('children', []):
                    find_info_stack(child)
        find_info_stack(hidden_snapshot['tree'])
        require(len(hidden_stack) == 1, 'TopPanel component fixture lacks its unique original info stack')
        hidden_stack[0]['hidden'] = True
        hidden_keys = set()
        def gather_hidden_keys(node):
            if type(node) is dict:
                if type(node.get('key')) is int:
                    hidden_keys.add(node['key'])
                for child in node.get('children', []):
                    gather_hidden_keys(child)
        gather_hidden_keys(hidden_stack[0])
        hidden_snapshot['inputTargets'] = [target for target in hidden_snapshot['inputTargets']
                                           if target['key'] not in hidden_keys]
        hidden_interaction = top_panel_interaction_contract(hidden_snapshot)
        require(hidden_interaction['info_stack_hidden'] is True and
                hidden_interaction['science_callback_available'] is False and
                hidden_interaction['science_callback_target'] is None,
                'Stock hidden-info-stack state did not suppress the SciencePerTurn callback')
        invalid_hidden_snapshot = copy.deepcopy(hidden_snapshot)
        invalid_hidden_snapshot['inputTargets'].append(next(
            target for target in snapshot['inputTargets'] if target.get('id') == 'SciencePerTurn'))
        rejected_hidden_callback = False
        try:
            top_panel_interaction_contract(invalid_hidden_snapshot)
        except ValueError:
            rejected_hidden_callback = True
        require(rejected_hidden_callback,
                'Hidden info stack incorrectly accepted an exposed SciencePerTurn callback')
        panel = manifest['top_panel_world_overlay']
        require(panel['nonmodal'] is True and panel['timer_semaphores'] == 0 and
                panel['full_screen_opaque_placeholder'] is False and
                panel['non_root_full_viewport_controls'] == [] and
                panel['host_compositor_required'] is True and
                panel['host_compositor_runtime_verified'] is False,
                'Compiled TopPanel packet is not a transparent persistent world overlay')
        require(panel['source_contract']['layout_source']['sha256'] == source_hashes[str(layout.resolve())] and
                panel['source_contract']['script_source']['sha256'] == source_hashes[str(script.resolve())] and
                panel['source_contract']['science_callback'] ==
                    'SciencePerTurn -> OnTechClicked -> BUTTONPOPUP_TECH_TREE, Data2=-1',
                'TopPanel rendering is not bound to the stock XML/Lua sources and science callback')

        by_key = {row['key']: row for row in manifest['geometry']}
        visible = {node['key']: node for node in visible_nodes(snapshot['tree'])}
        require(all(target['key'] in visible and target['key'] in by_key and
                    target['visible'] is True and target['disabled'] is False
                    for target in targets),
                'Hidden or unrendered TopPanel control leaked into the native hit packet')
        packet_keys = {int(row[0]) for row in manifest['hit_regions']}
        target_keys = {target['key'] for target in targets}
        require(packet_keys == target_keys and len(packet_keys) == len(manifest['hit_regions']),
                'Native hit packet omitted, duplicated, or invented a TopPanel callback/ConsumeMouse target')
        science = [target for target in targets if target.get('id') == 'SciencePerTurn' and
                   target.get('event') == 'LeftClick']
        require(len(science) == 1 and science[0].get('toolTipCallback') is True,
                'Original SciencePerTurn click and tooltip callback were not both retained')
        tooltip_proof = panel['tooltip']
        expected_tooltips = [target for target in targets if target.get('event') != 'ConsumeMouse' and
                             target.get('toolTipCallback') is True]
        require(tooltip_proof['callback_targets'] == expected_tooltips and
                tooltip_proof['retail_placement_verified'] is False and
                tooltip_proof['retail_autosize_verified'] is False and
                tooltip_proof['rasterized'] is False,
                'Original tooltip callbacks/tree were dropped or given unsupported placement claims')
        require(panel['host_compositor_runtime_verified'] is False and
                panel['tooltip']['rasterized'] is False,
                'Component render falsely claims live Host compositing or tooltip rasterization')

        visible_text = {node['key'] for node in visible.values()
                        if node.get('kind') in ('Label', 'TextButton') and
                        isinstance(node.get('text'), str) and node['text'].strip()}
        labels = {row['key']: row for row in manifest['labels']}
        require(visible_text <= set(labels) and all(labels[key]['glyph_count'] > 0 for key in visible_text),
                'Visible original TopPanel text or glyphs were omitted from the compiled scene')
        science_label = labels.get(science[0]['key'])
        require(science_label is not None and science_label['inline_icons'],
                'Original TopPanel research icon was not compiled from its prepared source mapping')

        pixels = render_ui_popup.png_pixels(png)
        alpha = pixels[3::4]
        width, height = 1920, 1080
        top_alpha = sum(value > 0 for value in alpha[:width * 48])
        lower_alpha = sum(value > 0 for value in alpha[width * 64:])
        require(top_alpha > 0 and lower_alpha == 0 and sum(value == 0 for value in alpha) > len(alpha) * 0.90,
                'TopPanel pixels are not a sparse transparent bar overlay over the world')
        clear_point = (1000, 100)
        clear_alpha = alpha[clear_point[1] * width + clear_point[0]]
        require(clear_alpha == 0, 'Offscreen TopPanel render added visible pixels below its original top bar')

        # Feed the exact negative-GPT string observed in the live SDK failure
        # through the same retained compiler and native renderer. The captured
        # fixture's textFrame is recomputed from the original installed GGXML;
        # the input scene remains explicitly a derived component fixture.
        negative_snapshot = copy.deepcopy(snapshot)
        negative_gold = []
        def find_gold(node):
            if type(node) is dict:
                if node.get('id') == 'GoldPerTurn' and node.get('kind') == 'TextButton':
                    negative_gold.append(node)
                for child in node.get('children', []):
                    find_gold(child)
        find_gold(negative_snapshot['tree'])
        require(len(negative_gold) == 1, 'TopPanel fixture lacks the unique original GoldPerTurn TextButton')
        negative_text = ('[ICON_GOLD][COLOR:255:235:0:255]"4180" '
                         '[COLOR:255:60:60:255](-1)"[ENDCOLOR]')
        negative_gold[0]['text'] = negative_text
        normalized_text = close_stock_top_panel_negative_gold_label(
            negative_text, context='top-panel', control_id='GoldPerTurn', kind='TextButton')
        plain_negative, _, occurrences = markup(normalized_text, colors, icon_map['icons'])
        negative_font = load_font(game_root, 'TwCenMT16')
        negative_glyphs = {}
        for codepoint, icon in occurrences.items():
            glyph = icon.get('glyph', icon)
            negative_glyphs[codepoint] = Glyph(codepoint, glyph['u'], glyph['v'], glyph['width'],
                                                glyph['height'], 0, glyph['advance'], 0,
                                                glyph['originx'], glyph['originy'])
        negative_lines = wrap_production_text(plain_negative, negative_font, negative_glyphs,
                                               negative_gold[0]['textFrame']['wrapWidth'])
        negative_gold[0]['textFrame']['lines'] = [
            {'text': text, 'advanceWidth': advance} for text, advance in negative_lines]
        negative_folder = directory / 'negative-gold-render'
        negative_folder.mkdir()
        negative_output = negative_folder / 'output'
        negative_output.mkdir()
        negative_snapshot_path = negative_folder / 'top-panel-negative-gold.json'
        negative_snapshot_path.write_text(json.dumps(negative_snapshot, ensure_ascii=False) + '\n',
                                          encoding='utf-8')
        shutil.copyfile(icons_path, negative_output / 'inline_icons.json')
        (negative_output / 'inline_colors.json').write_text(json.dumps(
            {'database': artifact(database_path), 'colors': colors}, ensure_ascii=False, indent=2) + '\n',
            encoding='utf-8')
        negative_manifest_path = negative_output / 'scene_manifest.json'
        render_ui_popup.prepare(negative_snapshot_path, negative_output, negative_manifest_path,
                                context='top-panel')
        negative_manifest = json.loads(negative_manifest_path.read_text(encoding='utf-8'))
        negative_labels = {row['key']: row for row in negative_manifest['labels']}
        negative_label = negative_labels.get(negative_gold[0]['key'])
        require(negative_label is not None and negative_label['plain_text'] == plain_negative and
                negative_label['text'] == negative_text and negative_label['inline_icons'] and
                negative_label['inline_colors_preserved'] is True,
                'Negative stock GoldPerTurn label text/icon/color markup was not retained by the renderer')
        negative_packet = Path(negative_manifest['packet']['path']).resolve(strict=True)
        negative_png = negative_output / 'negative-gold.png'
        negative_process = subprocess.run([str(renderer), str(negative_packet), str(negative_png)],
                                          cwd=negative_output, capture_output=True, timeout=120,
                                          creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        negative_stdout = negative_process.stdout.decode('utf-8', errors='replace').strip()
        negative_stderr = negative_process.stderr.decode('utf-8', errors='replace')
        require(negative_process.returncode == 0 and not negative_stderr.strip() and
                negative_stdout == f"BITMAP_RENDER_PASS width=1920 height=1080 sprites={negative_manifest['sprite_count']} "
                f"textures={negative_manifest['texture_count']} hits={len(negative_manifest['hit_regions'])} "
                'scope=OFFSCREEN_D2D_WIC',
                'Native renderer failed on the exact observed negative-GPT GoldPerTurn fixture: ' +
                (negative_stdout + '\n' + negative_stderr)[-2000:])

        require(sha256(snapshot_path) == snapshot_hash and sha256(database_path) == database_hash and
                sha256(icons_path) == icons_hash and
                all(sha256(path) == digest for path, digest in source_hashes.items()),
                'TopPanel scene compilation or rendering changed a frozen source/SDK input')
        result = {
            'status': 'STOCK_TOP_PANEL_COMPONENT_SNAPSHOT_COMPILER_AND_NATIVE_RENDER_PASS',
            'snapshot': artifact(snapshot_path), 'rules_db': artifact(database_path),
            'inline_icons': artifact(icons_path), 'renderer': artifact(renderer),
            'snapshot_provenance': {
                'component_result': artifact(component_result_path),
                'component_only_fixture': True,
                'live_sdk_capture_verified': False,
                'live_game_verified': False,
            },
            'tooltip_snapshot_provenance': {
                'snapshot': artifact(tooltip_snapshot_path),
                'original_tree_retained': True,
                'auto_size_requested': True,
                'retail_placement_verified': False,
                'retail_autosize_verified': False,
                'rasterized': False,
            },
            'renderer_component_proof': artifact(renderer_proof_path),
            'manifest': {'context': manifest['context'], 'packet_version': manifest['packet_version'],
                         'sprite_count': manifest['sprite_count'], 'texture_count': manifest['texture_count'],
                         'hit_regions': manifest['hit_regions'], 'labels': len(manifest['labels'])},
            'top_panel_policy': panel,
            'original_bar_layout': original_bar_layout,
            'visible_text_controls_compiled': len(visible_text),
            'top_bar_nontransparent_pixels': top_alpha,
            'below_bar_nontransparent_pixels': lower_alpha,
            'clear_point_alpha': clear_alpha,
            'negative_gold_render_fixture': {
                'input': negative_text,
                'input_fixture_is_derived_not_live_capture': True,
                'renderer_pass': True,
                'inline_icon_retained': bool(negative_label['inline_icons']),
                'quoted_provider_output_preserved': '"4180"' in negative_label['text'],
                'unbalanced_color_allowed_only_for_top_panel_gold_per_turn': True,
                'render_outputs_cleaned': True,
            },
            'snapshot_unchanged': True, 'rules_db_unchanged': True,
            'original_sources_unchanged': True,
            'retail_pixel_equivalence_verified': False,
            'tooltip_tree_rasterized': False,
            'live_host_compositing_verified': False,
            'unsupported_callbacks_claimed_complete': False,
        }

    if args.actual_hidden_snapshot:
        actual_snapshot_path = args.actual_hidden_snapshot.resolve(strict=True)
        actual_snapshot_hash = sha256(actual_snapshot_path)
        actual_snapshot = json.loads(actual_snapshot_path.read_text(encoding='utf-8'))
        actual_interaction = top_panel_interaction_contract(actual_snapshot)
        require(actual_interaction['info_stack_hidden'] is True and
                actual_interaction['science_callback_available'] is False and
                actual_interaction['science_callback_target'] is None,
                'Actual SDK snapshot is not the original no-city hidden-info-stack state')
        with tempfile.TemporaryDirectory(prefix='zerosistoppanel-hidden-') as temporary:
            directory = Path(temporary).resolve(strict=True)
            shutil.copyfile(icons_path, directory / 'inline_icons.json')
            (directory / 'inline_colors.json').write_text(json.dumps(
                {'database': artifact(database_path), 'colors': colors}, ensure_ascii=False, indent=2) + '\n',
                encoding='utf-8')
            render_ui_popup.GAME = game_root
            hidden_manifest_path = directory / 'scene_manifest.json'
            render_ui_popup.prepare(actual_snapshot_path, directory, hidden_manifest_path,
                                    context='top-panel')
            hidden_manifest = json.loads(hidden_manifest_path.read_text(encoding='utf-8'))
            hidden_panel = hidden_manifest['top_panel_world_overlay']
            require(hidden_panel['info_stack_hidden'] is True and
                    hidden_panel['science_callback_available'] is False and
                    hidden_panel['science_callback_target'] is None and
                    hidden_panel['nonmodal'] is True and hidden_panel['timer_semaphores'] == 0 and
                    hidden_panel['host_compositor_runtime_verified'] is False,
                    'Actual no-city snapshot did not compile to the bounded original hidden state')
            science_targets = [row for row in actual_snapshot['inputTargets']
                               if row.get('id') == 'SciencePerTurn']
            require(not science_targets and
                    {int(row[0]) for row in hidden_manifest['hit_regions']} ==
                    {target['key'] for target in actual_snapshot['inputTargets']},
                    'Actual hidden-state scene contains a SciencePerTurn hit target')
            hidden_packet = Path(hidden_manifest['packet']['path']).resolve(strict=True)
            hidden_png = directory / 'top-panel-hidden.png'
            hidden_process = subprocess.run([str(renderer), str(hidden_packet), str(hidden_png)], cwd=directory,
                                            capture_output=True, timeout=120,
                                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            hidden_stdout = hidden_process.stdout.decode('utf-8', errors='replace').strip()
            hidden_stderr = hidden_process.stderr.decode('utf-8', errors='replace')
            require(hidden_process.returncode == 0 and not hidden_stderr.strip() and
                    hidden_stdout == f"BITMAP_RENDER_PASS width=1920 height=1080 sprites={hidden_manifest['sprite_count']} "
                    f"textures={hidden_manifest['texture_count']} hits={len(hidden_manifest['hit_regions'])} "
                    'scope=OFFSCREEN_D2D_WIC',
                    'Native renderer failed on the actual hidden no-city TopPanel snapshot: ' +
                    (hidden_stdout + '\n' + hidden_stderr)[-2000:])
            hidden_pixels = render_ui_popup.png_pixels(hidden_png)
            hidden_alpha = hidden_pixels[3::4]
            hidden_width = 1920
            hidden_top_alpha = sum(value > 0 for value in hidden_alpha[:hidden_width * 48])
            hidden_lower_alpha = sum(value > 0 for value in hidden_alpha[hidden_width * 64:])
            require(hidden_top_alpha > 0 and hidden_lower_alpha == 0 and
                    sum(value == 0 for value in hidden_alpha) > len(hidden_alpha) * 0.90 and
                    sha256(actual_snapshot_path) == actual_snapshot_hash,
                    'Actual hidden-state render is not a sparse top bar or changed its captured snapshot')
        result['actual_hidden_sdk_snapshot'] = {
            'snapshot': artifact(actual_snapshot_path),
            'captured_hidden_stack_key': actual_interaction['info_stack_key'],
            'science_callback_available': False,
            'science_callback_targets': 0,
            'offscreen_sprite_count': hidden_manifest['sprite_count'],
            'offscreen_texture_count': hidden_manifest['texture_count'],
            'offscreen_hit_count': len(hidden_manifest['hit_regions']),
            'top_bar_nontransparent_pixels': hidden_top_alpha,
            'below_bar_nontransparent_pixels': hidden_lower_alpha,
            'temporary_render_output_cleaned': True,
            'live_game_or_host_compositing_verified': False,
        }

    if args.result:
        result_path = args.result.resolve()
        result_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        result['result'] = artifact(result_path)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
