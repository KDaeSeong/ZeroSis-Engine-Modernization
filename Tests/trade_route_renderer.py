"""Compile and render the retained original BNW TradeRouteOverview fixture.

The fixture is SDK-shaped component evidence only. This test exercises the
actual retained packet through the isolated native bitmap renderer; it does
not claim retail pixels, live Host input, tooltip placement, or game behavior.
All generated images and packets are confined to a temporary directory.
"""
from __future__ import annotations

import argparse
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
import render_ui_popup
from verify_interactive_top_panel import valid_top_panel_popup_request_branch


ROW_IDS = {
    'Root', 'Domain_Land', 'Domain_Sea', 'FromCivIconBG', 'FromCivIconShadow',
    'FromCivIcon', 'FromCivIconHighlight', 'FromCity', 'ToCivIconBG',
    'ToCivIconShadow', 'ToCivIcon', 'ToCivIconHighlight', 'ToCity', 'FromGPT',
    'ToGPT', 'FromScience', 'ToScience', 'ToFood', 'ToProduction',
    'FromReligion', 'ToReligion', 'TurnsLeft', 'Divider',
}
TAB_IDS = {'TabButtonYourTR', 'TabButtonAvailableTR', 'TabButtonTRWithYou'}
SORT_IDS = {
    'Domain', 'FromOwnerHeader', 'FromCityHeader', 'ToOwnerHeader', 'ToCityHeader',
    'FromGPT', 'ToGPT', 'ToFood', 'ToProduction', 'FromReligion', 'ToReligion',
    'FromScience', 'ToScience', 'TurnsLeft',
}
TARGET_IDS = TAB_IDS | SORT_IDS | {'CloseButton'}


def verify_shared_top_panel_enum_gate() -> int:
    before = ('if(std::strcmp(operation,"queueTopPanelPopup")==0){'
              'self.topPanelPopup_.reset(new CvPopupInfo(BUTTONPOPUP_TECH_TREE,-1,-1));return 0;'
              '}if(std::strcmp(operation,"isTouchScreen")==0){')
    expanded = ('if(std::strcmp(operation,"queueTopPanelPopup")==0){'
                'const int type=Integer(state,2),data2=Integer(state,3);'
                'if((type!=static_cast<int>(BUTTONPOPUP_TECH_TREE) && '
                'type!=static_cast<int>(BUTTONPOPUP_TRADE_ROUTE_OVERVIEW)) || data2!=-1)throw;'
                'self.topPanelPopup_.reset(new CvPopupInfo(static_cast<ButtonPopupTypes>(type),-1,-1));return 0;'
                '}if(std::strcmp(operation,"isTouchScreen")==0){')
    checks = [
        valid_top_panel_popup_request_branch(before),
        valid_top_panel_popup_request_branch(expanded),
        not valid_top_panel_popup_request_branch(expanded.replace(
            'BUTTONPOPUP_TRADE_ROUTE_OVERVIEW', 'BUTTONPOPUP_CHOOSEPRODUCTION')),
        not valid_top_panel_popup_request_branch(expanded.replace('data2!=-1', 'data2>0')),
        not valid_top_panel_popup_request_branch(expanded.replace(
            'static_cast<ButtonPopupTypes>(type)', 'static_cast<ButtonPopupTypes>(BUTTONPOPUP_CHOOSETECH)')),
        not valid_top_panel_popup_request_branch(expanded.replace(
            'if(std::strcmp(operation,"isTouchScreen")==0){', '')),
    ]
    require(all(checks), 'TopPanel source validator failed direct/gated enum or Data2 mutation checks')
    return len(checks)


def artifact(path: Path) -> dict:
    path = Path(path).resolve(strict=True)
    return {'path': str(path), 'sha256': sha256(path), 'bytes': path.stat().st_size}


def walk(node):
    yield node
    for child in node.get('children', []):
        yield from walk(child)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path, required=True,
                        help='Prepared original TradeRoute component snapshot JSON')
    parser.add_argument('--component-result', type=Path,
                        help='Fixture result.json; defaults beside --snapshot')
    parser.add_argument('--rules-db', type=Path, required=True,
                        help='SDK rules database supplying original COLOR_ bindings')
    parser.add_argument('--inline-icons', type=Path, required=True,
                        help='Prepared original FontIcons map with provenance')
    parser.add_argument('--game-root', type=Path, default=render_ui_popup.GAME,
                        help='Installed Civ V root containing the original UI/assets')
    parser.add_argument('--renderer', type=Path,
                        help='Accepted native bitmap renderer; defaults to its component proof')
    parser.add_argument('--result', type=Path,
                        help='Optional small JSON summary; must not already exist')
    args = parser.parse_args()
    enum_gate_checks = verify_shared_top_panel_enum_gate()

    snapshot_path = args.snapshot.resolve(strict=True)
    component_result_path = (args.component_result or snapshot_path.parent / 'result.json').resolve(strict=True)
    database_path = args.rules_db.resolve(strict=True)
    icons_path = args.inline_icons.resolve(strict=True)
    game_root = args.game_root.resolve(strict=True)
    require(all(path.is_file() for path in (snapshot_path, component_result_path,
                                            database_path, icons_path)),
            'TradeRoute compiler/renderer test input is missing')

    renderer_proof_path = PROJECT / 'evidence/bitmap_renderer/20261003T045102Z_7152c411ded8/conformance.json'
    renderer_proof = json.loads(renderer_proof_path.read_text(encoding='utf-8'))
    renderer_row = renderer_proof.get('renderer_artifact', {})
    renderer_path = (args.renderer or Path(renderer_row.get('executable', ''))).resolve(strict=True)
    require(renderer_proof.get('status') == 'BITMAP_RENDERER_COMPONENT_PASS' and
            renderer_proof.get('source_inputs_unchanged') is True and
            renderer_row.get('executable_sha256') == sha256(renderer_path),
            'Native renderer is not the accepted immutable bitmap-renderer component')

    snapshot_hash = sha256(snapshot_path)
    component_hash = sha256(component_result_path)
    database_hash = sha256(database_path)
    icons_hash = sha256(icons_path)
    source_paths = {
        'TradeRouteOverview.xml': game_root / 'Assets/DLC/Expansion2/UI/InGame/Popups/TradeRouteOverview.xml',
        'TradeRouteOverview.lua': game_root / 'Assets/DLC/Expansion2/UI/InGame/Popups/TradeRouteOverview.lua',
        'TradeRouteHelpers.lua': game_root / 'Assets/DLC/Expansion2/UI/InGame/Popups/TradeRouteHelpers.lua',
    }
    source_hashes = {name: sha256(path.resolve(strict=True)) for name, path in source_paths.items()}
    component_result = json.loads(component_result_path.read_text(encoding='utf-8'))
    fixture = component_result.get('fixture')
    fixture_sources = component_result.get('original_source_sha256')
    require(component_result.get('status') == 'PASS_TRADE_ROUTE_ORIGINAL_LUA_COMPONENT_ONLY' and
            type(fixture) is dict and fixture.get('componentOnly') is True and
            fixture.get('retailSdkRendererAndGameVerified') is False and
            component_result.get('snapshot_sha256') == snapshot_hash and
            type(fixture_sources) is dict and
            fixture_sources.get('TradeRouteOverview.xml') == source_hashes['TradeRouteOverview.xml'] and
            fixture_sources.get('TradeRouteOverview.lua') == source_hashes['TradeRouteOverview.lua'] and
            fixture_sources.get('TradeRouteHelpers.lua') == source_hashes['TradeRouteHelpers.lua'],
            'TradeRoute snapshot/result is not bound to the original stock source bytes')
    snapshot = json.loads(snapshot_path.read_text(encoding='utf-8'))
    route = snapshot.get('tradeRoute')
    require(snapshot.get('contextName') == 'TradeRoute' and snapshot.get('popupKind') == 'TradeRoute' and
            snapshot.get('active') is True and snapshot.get('timerSemaphore') == 1 and
            type(route) is dict and route.get('modal') is True and route.get('timerSemaphore') == 1 and
            route.get('rowTemplate') == 'TRInstance' and route.get('rowSelectionPresent') is False and
            route.get('selectedTab') == 'YourTR' and route.get('visibleRowCount') == 2,
            'TradeRoute fixture does not exercise the original active modal outgoing-route scene')
    main_scroll = route.get('mainScroll')
    require(type(main_scroll) is dict and main_scroll.get('id') == 'MainScroll' and
            main_scroll.get('event') == 'Scroll' and main_scroll.get('orientation') == 'vertical',
            'Fixture lost the original vertical MainScroll diagnostic')

    with sqlite3.connect(database_path.as_uri() + '?mode=ro', uri=True) as connection:
        color_rows = connection.execute(
            'SELECT Type, Red, Green, Blue, Alpha FROM Colors WHERE Type LIKE ?', ('COLOR_%',)).fetchall()
    colors = {row[0]: list(row[1:]) for row in color_rows}
    require(colors and len(colors) == len(color_rows),
            'SDK rules database has no unique original COLOR_ bindings')
    icon_map = json.loads(icons_path.read_text(encoding='utf-8'))
    require(type(icon_map) is dict and type(icon_map.get('icons')) is dict,
            'Prepared original inline icon mapping is malformed')

    with tempfile.TemporaryDirectory(prefix='zerosistraderoute-') as temporary:
        directory = Path(temporary).resolve(strict=True)
        shutil.copyfile(icons_path, directory / 'inline_icons.json')
        require(sha256(directory / 'inline_icons.json') == icons_hash,
                'Original inline icon map changed while staging the renderer test')
        (directory / 'inline_colors.json').write_text(json.dumps(
            {'database': artifact(database_path), 'colors': colors}, ensure_ascii=False, indent=2) + '\n',
            encoding='utf-8')
        render_ui_popup.GAME = game_root
        manifest_path = directory / 'scene_manifest.json'
        render_ui_popup.prepare(snapshot_path, directory, manifest_path, context='trade-route')
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        proof = manifest.get('trade_route_scene')
        require(type(proof) is dict and proof.get('policy') ==
                'ORIGINAL_TRADE_ROUTE_OVERVIEW_RETAINED_TREE_V1' and
                proof.get('retained_row_count') == route['visibleRowCount'] and
                proof.get('selected_tab') == route['selectedTab'] and
                proof.get('row_selection_present') is False and
                proof.get('row_tooltips_rasterized') is False and
                proof.get('main_scroll') == main_scroll and
                proof.get('retail_pixels_verified') is False and
                proof.get('retail_style_timing_verified') is False,
                'Compiler manifest dropped TradeRoute scene/source/tooltip/scroll policy')
        require(manifest.get('context_name') == 'TradeRoute' and
                manifest.get('popup_kind') == 'TradeRoute' and
                manifest.get('scroll_region_count') == 1 and
                manifest.get('input_callback_coverage_claimed') is False and
                manifest.get('retail_input_semantics_verified') is False,
                'Compiler context, scroll, or callback proof boundary is incorrect')
        source_contract = proof.get('source_contract', {})
        require(source_contract.get('row_template') == 'TRInstance' and
                set(source_contract.get('row_control_ids', [])) == ROW_IDS and
                set(source_contract.get('tab_control_ids', [])) == TAB_IDS and
                set(source_contract.get('sortable_header_ids', [])) == SORT_IDS,
                'Compiler source contract differs from original XML rows/tabs/sort headers')
        frozen_sources = {row['path']: row['sha256'] for row in manifest.get('original_context_sources', [])}
        require(all(frozen_sources.get(source_contract.get(field, {}).get('path')) ==
                    source_contract.get(field, {}).get('sha256')
                    for field in ('layout_source', 'script_source', 'helper_source')),
                'Compiler did not freeze all original TradeRoute source provenance')

        tree_nodes = list(walk(snapshot['tree']))
        main_stacks = [node for node in tree_nodes if node.get('id') == 'MainStack']
        require(len(main_stacks) == 1 and len(main_stacks[0].get('children', [])) == route['visibleRowCount'],
                'Visible dynamic TRInstance rows differ from the retained MainStack')
        row_ids = []
        for row in main_stacks[0]['children']:
            controls = [node for node in walk(row)
                        if isinstance(node.get('sourceAttributes'), dict) and
                        node['sourceAttributes'].get('ID')]
            ids = [node['sourceAttributes']['ID'] for node in controls]
            require(len(ids) == len(ROW_IDS) and set(ids) == ROW_IDS and
                    len(set(ids)) == len(ids),
                    'A retained route row omitted, duplicated, or invented an original XML control')
            row_ids.append({node['sourceAttributes']['ID']: node['key'] for node in controls})

        visible = {node['key']: node for node in walk(snapshot['tree']) if node.get('hidden') is False}
        geometry = {row['key']: row for row in manifest.get('geometry', [])}
        target_rows = snapshot.get('inputTargets', [])
        require(type(target_rows) is list and len(target_rows) == len(TARGET_IDS) and
                {row.get('id') for row in target_rows} == TARGET_IDS and
                all(row.get('event') == 'LeftClick' and row.get('visible') is True and
                    row.get('disabled') is False for row in target_rows),
                'Retained original tab/sort/close targets differ from the source callbacks')
        target_keys = {row['key'] for row in target_rows}
        require(all(key in visible and key in geometry and geometry[key].get('input_target') is True
                    for key in target_keys),
                'Hidden or unrendered original TradeRoute control leaked into the hit target set')
        hit_keys = {int(row[0]) for row in manifest.get('hit_regions', [])}
        require(hit_keys == target_keys and len(manifest['hit_regions']) == len(TARGET_IDS),
                'Native hit packet omitted, duplicated, or invented a TradeRoute callback target')
        scroll_targets = snapshot.get('scrollTargets')
        require(type(scroll_targets) is list and len(scroll_targets) == 1 and
                scroll_targets[0].get('key') == main_scroll.get('key') and
                scroll_targets[0].get('id') == 'MainScroll' and scroll_targets[0].get('event') == 'Scroll' and
                manifest.get('scroll_region_count') == 1,
                'Native scroll input packet differs from original MainScroll identity/viewport')

        labels = {row['key']: row for row in manifest.get('labels', [])}
        visible_text = {node['key'] for node in visible.values()
                        if node.get('kind') in ('Label', 'TextButton') and
                        isinstance(node.get('text'), str) and node['text'].strip()}
        require(visible_text <= set(labels) and
                all(labels[key].get('glyph_count', 0) > 0 for key in visible_text),
                'Visible original TradeRoute text or glyph geometry was omitted from the packet')
        tab_captions = {node['key']: node for node in tree_nodes if node.get('id') in TAB_IDS}
        require(len(tab_captions) == 3 and all(
                key in labels and labels[key]['text'] == node['text'] and
                labels[key]['glyph_count'] > 0 and labels[key].get('text_control') == 'Button' and
                labels[key].get('text_control_id') == node['id'] and
                labels[key].get('retail_text_alignment_verified') is False and
                geometry[key]['bounds'] == [node[field] for field in ('x', 'y', 'width', 'height')]
                for key, node in tab_captions.items()),
                'Original TradeRoute tab Button captions are missing or changed their hit geometry')
        icon_controls = {node.get('key'): node for row in main_stacks[0]['children'] for node in walk(row)
                         if node.get('id') in ('FromCivIcon', 'ToCivIcon') and node.get('kind') == 'Image'}
        icon_layers = {node['key']: node for row in main_stacks[0]['children'] for node in walk(row)
                       if node.get('kind') == 'Image' and node.get('id') in
                       {prefix + suffix for prefix in ('FromCivIcon', 'ToCivIcon')
                        for suffix in ('', 'BG', 'Shadow', 'Highlight')}}
        visible_icon_layers = sorted(key for key, node in icon_layers.items() if node['hidden'] is False)
        require(len(icon_controls) == route['visibleRowCount'] * 2 and
                proof.get('row_civilization_icon_keys') == sorted(icon_controls) and
                proof.get('row_civilization_icon_layer_keys') == sorted(icon_layers) and
                proof.get('row_civilization_icon_visible_layer_keys') == visible_icon_layers and
                proof.get('row_civilization_icon_sprite_keys') == visible_icon_layers,
                'Original route civilization icon visibility differs from renderer geometry')

        packet = Path(manifest['packet']['path']).resolve(strict=True)
        png = directory / 'trade-route.png'
        process = subprocess.run([str(renderer_path), str(packet), str(png)], cwd=directory,
                                 capture_output=True, timeout=120,
                                 creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        stdout = process.stdout.decode('utf-8', errors='replace').strip()
        stderr = process.stderr.decode('utf-8', errors='replace')
        require(process.returncode == 0 and not stderr.strip() and
                stdout == f"BITMAP_RENDER_PASS width=1920 height=1080 sprites={manifest['sprite_count']} "
                          f"textures={manifest['texture_count']} hits={len(manifest['hit_regions'])} "
                          'scope=OFFSCREEN_D2D_WIC',
                'Native TradeRoute offscreen renderer failed or returned different packet counts: ' +
                (stdout + '\n' + stderr)[-2000:])
        pixels = render_ui_popup.png_pixels(png)
        alpha = pixels[3::4]
        body_samples = [alpha[y * 1920 + x] for x, y in
                        ((4, 64), (1915, 64), (4, 1075), (1915, 1075), (960, 540))]
        require(len(alpha) == 1920 * 1080 and all(value > 0 for value in body_samples),
                'Original TradeRoute full-screen body scrim did not reach the sampled viewport area')

        require(sha256(snapshot_path) == snapshot_hash and
                sha256(component_result_path) == component_hash and
                sha256(database_path) == database_hash and sha256(icons_path) == icons_hash and
                all(sha256(path) == source_hashes[name] for name, path in source_paths.items()),
                'TradeRoute renderer test changed an immutable input')
        result = {
            'status': 'PASS_TRADE_ROUTE_RETAINED_COMPILER_AND_NATIVE_RENDERER_COMPONENT',
            'evidence_scope': 'stock component fixture and candidate offscreen renderer; no live SDK, Host input, tooltip placement, or retail equivalence',
            'snapshot': artifact(snapshot_path), 'component_result': artifact(component_result_path),
            'original_source_sha256': source_hashes, 'renderer': artifact(renderer_path),
            'rules_db_sha256': database_hash, 'inline_icons_sha256': icons_hash,
            'retained_rows': route['visibleRowCount'], 'selected_tab': route['selectedTab'],
            'row_control_count_per_row': len(ROW_IDS), 'original_click_targets': len(TARGET_IDS),
            'original_sort_headers': len(SORT_IDS), 'visible_text_controls': len(visible_text),
            'retained_civilization_icon_controls': len(icon_controls),
            'rendered_original_tab_captions': len(tab_captions),
            'main_scroll': main_scroll,
            'row_tooltips_retained_but_rasterized': False,
            'top_panel_enum_gate_unit_checks': enum_gate_checks,
            'retail_pixels_verified': False, 'retail_scroll_semantics_verified': False,
            'native_host_input_verified': False, 'installed_game_launched': False,
            'temporary_render_artifacts_cleaned': True,
        }
        if args.result:
            result_path = args.result.resolve()
            require(not result_path.exists(), 'Refusing to overwrite existing TradeRoute renderer result')
            result_path.parent.mkdir(parents=True, exist_ok=True)
            result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(result, ensure_ascii=False, separators=(',', ':')))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
