"""Run the unchanged BNW TradeRouteOverview Lua in the retained scene fixture.

This component check uses explicit SDK-shaped trade records; it is not evidence
of live SDK bindings, native popup routing, retail widget geometry, or pixels.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from prepare_ui_popup_assets import (
    GAME, inline_icon_catalog, production_font_metrics, production_style_defaults,
    trade_route_control_tree,
)
from verify_ui_scene import long_string, lua_value, run_lua

PROJECT = Path(__file__).resolve().parents[1]
POPUP_DIR = GAME / 'Assets/DLC/Expansion2/UI/InGame/Popups'
OVERVIEW_LUA = POPUP_DIR / 'TradeRouteOverview.lua'
OVERVIEW_XML = POPUP_DIR / 'TradeRouteOverview.xml'
HELPERS_LUA = POPUP_DIR / 'TradeRouteHelpers.lua'
ICON_SUPPORT = GAME / 'Assets/UI/IconSupport.lua'
FLUA_VECTOR = GAME / 'Assets/Gameplay/Lua/FLuaVector.lua'
ICON_ATLASES = GAME / 'Assets/Gameplay/XML/GameInfo/CIV5IconTextureAtlases.xml'
RESOURCE_ID = 6  # Explicit fixture SDK row ID for RESOURCE_IRON; never supplied to production.


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fail(message: str) -> None:
    raise RuntimeError('TradeRoute scene component: ' + message)


def fixture_atlas_rows() -> list[dict]:
    root = ET.parse(ICON_ATLASES).getroot()
    wanted = {('CIV_ALPHA_ATLAS', 24), ('CIV_ALPHA_ATLAS', 48),
              ('CIV_COLOR_ATLAS', 24), ('CIV_COLOR_ATLAS', 48)}
    rows = []
    for element in root.findall('./IconTextureAtlases/Row'):
        values = {child.tag: child.text for child in element}
        key = (values.get('Atlas'), int(values.get('IconSize', '-1')))
        if key in wanted:
            rows.append({
                'Atlas': key[0], 'IconSize': key[1], 'Filename': values['Filename'],
                'IconsPerRow': int(values['IconsPerRow']),
                'IconsPerColumn': int(values['IconsPerColumn']),
            })
    if not rows:
        fail('installed icon atlas source has no required Civ symbol mappings')
    return rows


def assemble(template: str, sources: dict[str, bytes], layout: dict,
             atlas_rows: list[dict]) -> bytes:
    values = {
        '@@SOURCE_OVERVIEW@@': long_string(sources['TradeRouteOverview.lua'].decode('utf-8-sig')),
        '@@SOURCE_HELPERS@@': long_string(sources['TradeRouteHelpers.lua'].decode('utf-8-sig')),
        '@@SOURCE_ICON_SUPPORT@@': long_string(sources['IconSupport.lua'].decode('utf-8-sig')),
        '@@SOURCE_FLUA_VECTOR@@': long_string(sources['FLuaVector.lua'].decode('utf-8-sig')),
        '@@SCENE_SOURCE@@': long_string((PROJECT / 'Source/Host/UiScene.lua').read_text(encoding='utf-8-sig')),
        '@@INPUT_SOURCE@@': long_string((PROJECT / 'Source/Presentation/UiPresentationInput.lua').read_text(encoding='utf-8-sig')),
        '@@LAYOUT@@': lua_value(layout),
        '@@FONT_METRICS@@': lua_value(layout['fontMetrics']),
        '@@STYLE_DEFAULTS@@': lua_value(layout['styleDefaults']),
        '@@ICON_ATLAS_ROWS@@': lua_value(atlas_rows),
        '@@IRON_RESOURCE_ID@@': str(RESOURCE_ID),
    }
    for token, value in values.items():
        template = template.replace(token, value)
    if '@@' in template:
        fail('fixture contains an unresolved source or layout token')
    return template.encode('utf-8')


def verify_component(encoder: Path, evidence_dir: Path | None = None) -> dict:
    encoder = Path(os.path.abspath(encoder))
    if not encoder.is_file():
        fail('native snapshot JSON encoder is missing')
    source_paths = {
        'TradeRouteOverview.lua': OVERVIEW_LUA,
        'TradeRouteOverview.xml': OVERVIEW_XML,
        'TradeRouteHelpers.lua': HELPERS_LUA,
        'IconSupport.lua': ICON_SUPPORT,
        'FLuaVector.lua': FLUA_VECTOR,
        'CIV5IconTextureAtlases.xml': ICON_ATLASES,
    }
    sources = {name: path.read_bytes() for name, path in source_paths.items()}
    source_hashes = {name: sha(data) for name, data in sources.items()}
    tree = trade_route_control_tree(ET.fromstring(sources['TradeRouteOverview.xml']))
    tree.update({'contextName': 'TradeRoute', 'popupKind': 'TradeRoute'})
    tree['tradeRoute'] = {
        'rowTemplate': 'TRInstance',
        'originalLayoutXml': {'path': str(OVERVIEW_XML), 'sha256': source_hashes['TradeRouteOverview.xml']},
        'originalLayoutLua': {'path': str(OVERVIEW_LUA), 'sha256': source_hashes['TradeRouteOverview.lua']},
        'originalHelpersLua': {'path': str(HELPERS_LUA), 'sha256': source_hashes['TradeRouteHelpers.lua']},
        'rowSelectionPresent': False,
    }

    temporary_parent = PROJECT / 'evidence'
    temporary_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='trade-route-component-', dir=temporary_parent) as temp_name:
        temp = Path(temp_name)
        frozen = temp / 'frozen-ui'
        icons, _ = inline_icon_catalog(frozen)
        styles = production_style_defaults(frozen, tree)
        tree['styleDefaults'] = styles['controls']
        tree['styleDefaultsSource'] = styles['source']
        tree['styleDefaultsPolicy'] = styles['policy']
        tree['fontMetrics'] = production_font_metrics(tree, icons)
        fixture = (PROJECT / 'Tests/trade_route_scene.lua').read_text(encoding='utf-8-sig')
        harness = temp / 'trade-route-harness.lua'
        harness.write_bytes(assemble(fixture, sources, tree, fixture_atlas_rows()))
        report = json.loads(run_lua(encoder, harness, '__tradeRouteComponentReport'))

    if any(sha(path.read_bytes()) != source_hashes[name] for name, path in source_paths.items()):
        fail('an installed original UI/helper source changed during verification')

    required = {
        'componentOnly': True,
        'originalLuaUnmodified': True,
        'stockTabsAndSortRetained': True,
        'stockEscapeAndTimerLifecycle': True,
        'sdkShapedRouteDataUsed': True,
        'helperTooltipRetained': True,
        'originalRowControlsRetained': True,
        'rowSelectionExistsInOriginal': False,
        'retailSdkRendererAndGameVerified': False,
    }
    if any(report.get(key) != value for key, value in required.items()):
        fail('fixture result differs from the original TradeRoute contract: ' + repr(report))
    targets = report.get('buttonTargetIds')
    required_targets = {'TabButtonYourTR', 'TabButtonAvailableTR', 'TabButtonTRWithYou',
                        'Domain', 'FromOwnerHeader', 'FromCityHeader', 'ToOwnerHeader',
                        'ToCityHeader', 'FromGPT', 'ToGPT', 'ToFood', 'ToProduction',
                        'FromReligion', 'ToReligion', 'FromScience', 'ToScience',
                        'TurnsLeft', 'CloseButton'}
    if not isinstance(targets, dict) or set(targets) != required_targets:
        fail('fixture input targets differ from the exact stock 3-tab/14-sort/close callback set')
    for key in ('yourRows', 'sortedRows', 'availableRows', 'incomingRows'):
        rows = report.get(key)
        if not isinstance(rows, list) or not rows:
            fail('fixture did not retain nonempty SDK-shaped route rows for ' + key)
    if len(report['yourRows']) != 2 or len(report['availableRows']) != 1 or len(report['incomingRows']) != 1:
        fail('fixture route tab counts differ from the explicit data contract')
    if report['sortedRows'][0]['to'] != 'Athens' or report['sortedRows'][1]['to'] != 'Corinth':
        fail('original FromGPT sort result was not preserved')
    if report.get('ascendingRows', [{}])[0].get('to') != 'Corinth' or \
       report.get('ascendingRows', [{}, {}])[1].get('to') != 'Athens':
        fail('original sort-direction toggle was not preserved')
    if 'TXT_KEY_CHOOSE_INTERNATIONAL_TRADE_ROUTE_ITEM_TT_YOUR_REVENUE' not in \
       report['yourRows'][0]['fromTooltip']:
        fail('original helper tooltip text is missing from rendered rows')
    snapshot = report.get('snapshot')
    if not isinstance(snapshot, dict) or snapshot.get('popupKind') != 'TradeRoute' or \
       snapshot.get('contextName') != 'TradeRoute' or snapshot.get('timerSemaphore') != 1 or \
       snapshot.get('tradeRoute', {}).get('rowTemplate') != 'TRInstance':
        fail('active modal TradeRoute snapshot contract is incomplete')
    scroll = report.get('mainScroll')
    if not isinstance(scroll, dict) or scroll.get('id') != 'MainScroll' or scroll.get('orientation') != 'vertical':
        fail('original MainScroll viewport target metadata is missing')

    implementation = {
        'asset_preparer': PROJECT / 'tools/prepare_ui_popup_assets.py',
        'host_ui_scene': PROJECT / 'Source/Host/UiScene.lua',
        'fixture': PROJECT / 'Tests/trade_route_scene.lua',
        'verifier': Path(__file__).resolve(),
    }
    snapshot_bytes = (json.dumps(snapshot, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode('utf-8')
    result = {
        'status': 'PASS_TRADE_ROUTE_ORIGINAL_LUA_COMPONENT_ONLY',
        'evidence_scope': 'mocked component; not retail SDK, native routing, renderer, pixel, or live-game evidence',
        'original_source_sha256': source_hashes,
        'implementation_sha256': {name: sha(path.read_bytes()) for name, path in implementation.items()},
        'layout_tree_sha256': sha(json.dumps(tree, ensure_ascii=False, sort_keys=True).encode('utf-8')),
        'layout_control_count': sum(1 for _ in _walk_nodes(tree)),
        'fixture': {key: value for key, value in report.items() if key != 'snapshot'},
        'snapshot_file': 'snapshot.json',
        'snapshot_sha256': sha(snapshot_bytes),
        'verified': {
            'original_tab_getters_and_row_values': True,
            'original_sort_headers': True,
            'original_sort_direction_toggle': True,
            'original_helper_tooltips': True,
            'original_popup_escape_timer_lifecycle': True,
            'original_source_and_icon_support_hashes': True,
            'row_selection': False,
            'retail_sdk_bindings_native_dispatch_renderer_pixels_live_game': False,
        },
    }
    if evidence_dir is not None:
        evidence_dir.mkdir(parents=True, exist_ok=True)
        (evidence_dir / 'snapshot.json').write_bytes(snapshot_bytes)
        (evidence_dir / 'result.json').write_text(
            json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2), encoding='utf-8')
    return result


def _walk_nodes(node: dict):
    yield node
    for child in node.get('children', []):
        yield from _walk_nodes(child)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--snapshot-json-encoder', type=Path, required=True)
    parser.add_argument('--evidence-dir', type=Path,
                        default=PROJECT / 'evidence/trade_route_scene_component')
    args = parser.parse_args()
    result = verify_component(args.snapshot_json_encoder, Path(os.path.abspath(args.evidence_dir)))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
