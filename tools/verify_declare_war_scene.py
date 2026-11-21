"""Run the unmodified installed BNW DeclareWarPopup against retained scene controls.

The Lua fixture uses SDK-shaped mock objects and a native command recorder. It
checks original GatherData content and callback order; it does not claim retail
SDK mutation, original renderer equivalence, or live-game behavior.
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
    GAME, declare_war_control_tree, inline_icon_catalog,
    production_font_metrics, production_style_defaults,
)
from verify_ui_scene import long_string, lua_value, run_lua

PROJECT = Path(__file__).resolve().parents[1]
POPUP = GAME / 'Assets/DLC/Expansion2/UI/InGame/Popups/DeclareWarPopup.lua'
POPUP_XML = GAME / 'Assets/DLC/Expansion2/UI/InGame/Popups/DeclareWarPopup.xml'


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fail(message: str) -> None:
    raise RuntimeError('DeclareWar scene component: ' + message)


def assemble(template: str, sources: dict[str, bytes], layout: dict) -> bytes:
    values = {
        '@@SOURCE_INSTANCE_MANAGER@@': long_string(sources['InstanceManager'].decode('utf-8-sig')),
        '@@SOURCE_ICON_SUPPORT@@': long_string(sources['IconSupport'].decode('utf-8-sig')),
        '@@SOURCE_FLUA_VECTOR@@': long_string(sources['FLuaVector'].decode('utf-8-sig')),
        '@@SOURCE_COMMON_BEHAVIORS@@': long_string(sources['CommonBehaviors'].decode('utf-8-sig')),
        '@@SOURCE_POPUP@@': long_string(sources['DeclareWarPopup'].decode('utf-8-sig')),
        '@@ICON_ATLAS_ROWS@@': lua_value(layout['iconAtlasRows']),
        '@@SCENE_SOURCE@@': long_string((PROJECT / 'Source/Host/UiScene.lua').read_text(encoding='utf-8-sig')),
        '@@LAYOUT@@': lua_value(layout),
        '@@FONT_METRICS@@': lua_value(layout['fontMetrics']),
        '@@STYLE_DEFAULTS@@': lua_value(layout['styleDefaults']),
    }
    for token, value in values.items():
        template = template.replace(token, value)
    if '@@' in template:
        fail('Lua fixture has an unresolved source placeholder')
    return template.encode('utf-8')


def verify_component(snapshot_json_build: Path | None = None,
                     snapshot_json_encoder: Path | None = None,
                     evidence_dir: Path | None = None) -> dict:
    if snapshot_json_build is not None:
        build_path = Path(os.path.abspath(snapshot_json_build))
        build = json.loads(build_path.read_text(encoding='utf-8-sig'))
        if build.get('status') != 'UI_SNAPSHOT_JSON_COMPONENT_BUILT':
            fail('expected a successful native snapshot encoder component build')
        encoder = build.get('executable', {})
        encoder_path = Path(os.path.abspath(encoder.get('path', '')))
        if sha(encoder_path.read_bytes()) != encoder.get('sha256'):
            fail('snapshot encoder hash differs from its build report')
    else:
        if snapshot_json_encoder is None:
            fail('a snapshot encoder binary or build report is required')
        encoder_path = Path(os.path.abspath(snapshot_json_encoder))

    source_paths = {
        'InstanceManager': GAME / 'Assets/UI/InstanceManager.lua',
        'IconSupport': GAME / 'Assets/UI/IconSupport.lua',
        'FLuaVector': GAME / 'Assets/Gameplay/Lua/FLuaVector.lua',
        'CommonBehaviors': GAME / 'Assets/UI/CommonBehaviors.lua',
        'DeclareWarPopup': POPUP,
        'IconTextureAtlases': GAME / 'Assets/Gameplay/XML/GameInfo/CIV5IconTextureAtlases.xml',
    }
    sources = {name: path.read_bytes() for name, path in source_paths.items()}
    source_hashes = {name: sha(data) for name, data in sources.items()}
    implementation_paths = {
        'host_ui_scene': PROJECT / 'Source/Host/UiScene.lua',
        'scene_fixture': PROJECT / 'Tests/declare_war_scene.lua',
        'scene_verifier': Path(__file__).resolve(),
    }
    implementation_hashes = {name: sha(path.read_bytes())
                             for name, path in implementation_paths.items()}
    if b'Network.SendChangeWar(eRivalTeam, true)' not in sources['DeclareWarPopup'] or \
       b'Game.SelectionListMove(plot, false, false, false)' not in sources['DeclareWarPopup']:
        fail('installed original MOVE command sequence changed or was not found')
    if b'Game.SelectionListGameNetMessage(messagePushMission, missionRangeAttack, iX, iY)' not in sources['DeclareWarPopup']:
        fail('installed original RANGE command sequence changed or was not found')

    # Keep only this verifier's transient harness under the project's evidence
    # boundary; TemporaryDirectory removes it when the component run ends.
    temporary_parent = PROJECT / 'evidence'
    temporary_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=temporary_parent,
                                     prefix='zeros_ui_declare_war_') as temp:
        snapshots = Path(temp) / 'frozen_assets'
        snapshots.mkdir()
        icons, _ = inline_icon_catalog(snapshots)
        # Parse the source layout bytes directly; the script source and XML are
        # independently hash-checked against the installed original files.
        xml_bytes = POPUP_XML.read_bytes()
        xml_hash = sha(xml_bytes)
        atlas_root = ET.fromstring(sources['IconTextureAtlases'])
        required_atlas_rows = {
            ('LEADER_ATLAS', 128): 'LeaderPortraits1024.dds',
            ('CIV_ALPHA_ATLAS', 32): 'CivSymbolAtlas32.dds',
            ('CIV_ALPHA_ATLAS', 48): 'CivSymbolAtlas48.dds',
        }
        atlas_rows = []
        for row in atlas_root.findall('./IconTextureAtlases/Row'):
            values = {child.tag: child.text for child in row}
            key = (values.get('Atlas'), int(values.get('IconSize', '-1')))
            if key in required_atlas_rows:
                if values.get('Filename') != required_atlas_rows[key]:
                    fail('installed icon atlas filename differs from expected source control texture: ' + repr(key))
                atlas_rows.append({
                    'Atlas': values['Atlas'], 'IconSize': int(values['IconSize']),
                    'Filename': values['Filename'], 'IconsPerRow': int(values['IconsPerRow']),
                    'IconsPerColumn': int(values['IconsPerColumn']),
                })
        if {(row['Atlas'], row['IconSize']) for row in atlas_rows} != set(required_atlas_rows):
            fail('installed icon atlas source omitted a required leader/civilization icon row')
        xml_root = ET.fromstring(xml_bytes)
        template_names = sorted(element.get('Name', '') for element in xml_root.iter('Instance'))
        if template_names != ['CityStateInstance', 'TradeRouteInstance', 'UnderProtectionCivInstance']:
            fail('original XML instance template declarations differ from the installed BNW layout')
        tree = declare_war_control_tree(xml_root)
        tree.update({'contextName': 'DeclareWarPopup', 'popupKind': 'DeclareWar',
                     'layoutScript': 'DeclareWarLayout', 'contextKey': 'declare-war'})
        tree['iconAtlasRows'] = atlas_rows
        style = production_style_defaults(snapshots, tree)
        tree['styleDefaults'] = style['controls']
        tree['styleDefaultsSource'] = style['source']
        tree['styleDefaultsPolicy'] = style['policy']
        tree['fontMetrics'] = production_font_metrics(tree, icons)
        template = (PROJECT / 'Tests/declare_war_scene.lua').read_text(encoding='utf-8-sig')
        harness = assemble(template, sources, tree)
        harness_path = Path(temp) / 'declare-war-harness.lua'
        harness_path.write_bytes(harness)
        report = json.loads(run_lua(encoder_path, harness_path))
        expected = {
            'declareWar': True, 'nonemptyDeals': True,
            'unknownInlineIconRejected': True, 'emptyDealsHidden': True,
            'initialNoDealsPlaceholderPending': True,
            'alliedCityStates': 4, 'wrapDown': True,
            'tradeRoutes': 2, 'moveCommandOrder': True, 'rangeCommandOrder': True,
            'escapeReadOnly': True, 'sourceAnimationVerified': True, 'retailRuntimeVerified': False,
        }
        if any(report.get(name) != value for name, value in expected.items()):
            fail('fixture report differs from required original-data/order result: ' + repr(report))
        active, no_deals, closed = (report.get('activeSnapshot'), report.get('noDealsSnapshot'),
                                    report.get('closedSnapshot'))
        if type(active) is not dict or type(no_deals) is not dict or type(closed) is not dict:
            fail('fixture did not export its active, empty-deals and closed snapshots')
        active_targets = active.get('inputTargets')
        active_target_ids = {row.get('id') for row in active_targets} if type(active_targets) is list else set()
        if active.get('active') is not True or active.get('timerSemaphore') != 1 or \
           active.get('popupKind') != 'DeclareWar' or active.get('contextName') != 'DeclareWarPopup' or \
           active.get('hasRetainedPopupUi') is not True or \
           not {'Button1', 'Button2', 'ActiveDealsHeader', 'AlliedCityStatesHeader',
                'DiplomacyHeader'}.issubset(active_target_ids) or \
           not any(row.get('id') == 'DeclareWarDetailsScrollPanel' for row in active.get('scrollTargets', [])):
            fail('active snapshot does not retain stock decision/collapse buttons, timer or details scroll panel')
        if closed.get('active') is not False or closed.get('timerSemaphore') != 0 or \
           closed.get('inputTargets') != [] or closed.get('scrollTargets') != [] or \
           not closed.get('lifecycle') or closed['lifecycle'][-1] != 'closed':
            fail('empty-deals Escape snapshot did not close with balanced timer and no stale inputs')
        if no_deals.get('active') is not True or no_deals.get('timerSemaphore') != 1 or \
           no_deals.get('popupKind') != 'DeclareWar' or no_deals.get('contextName') != 'DeclareWarPopup':
            fail('empty-deals View did not initialize the original popup in its retained context')
        if sha(POPUP.read_bytes()) != source_hashes['DeclareWarPopup'] or sha(POPUP_XML.read_bytes()) != xml_hash:
            fail('installed original popup bytes changed during verification')
        result = {
            'status': 'PASS_DECLARE_WAR_ORIGINAL_LUA_COMPONENT_ONLY',
            'original_popup_sha256': source_hashes['DeclareWarPopup'],
            'original_xml_sha256': xml_hash,
            'implementation_sha256': implementation_hashes,
            'component': expected,
            'original_source_sha256': source_hashes,
            'layout_provenance': {
                'declared_instance_templates': template_names,
                'declared_control_nodes': sum(1 for _ in xml_root.iter()),
                'icon_atlas_source_sha256': source_hashes['IconTextureAtlases'],
                'icon_atlas_rows': atlas_rows,
                'realized_tree_contains_instance_declarations': False,
                'realized_tree_is_captured_from_generated_controls': True,
            },
            'verified': {
                'original_lua_unmodified': True,
                'representative_current_deals': True,
                'initial_no_deals_placeholder_retained_pending': True,
                'visible_label_rejects_unmapped_inline_icon': True,
                'allied_city_state': True,
                'two_trade_routes': True,
                'move_and_range_command_order': True,
                'no_and_escape_emit_no_commands': True,
                'source_flip_animation_metadata': True,
                'retail_sdk_renderer_and_live_game': False,
            },
        }
        if evidence_dir is not None:
            evidence_dir.mkdir(parents=True, exist_ok=True)
            (evidence_dir / 'active-snapshot.json').write_text(
                json.dumps(active, ensure_ascii=False, sort_keys=True, indent=2), encoding='utf-8')
            (evidence_dir / 'no-deals-snapshot.json').write_text(
                json.dumps(no_deals, ensure_ascii=False, sort_keys=True, indent=2), encoding='utf-8')
            (evidence_dir / 'closed-snapshot.json').write_text(
                json.dumps(closed, ensure_ascii=False, sort_keys=True, indent=2), encoding='utf-8')
            (evidence_dir / 'result.json').write_text(
                json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2), encoding='utf-8')
        return result


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--snapshot-json-build', type=Path)
    group.add_argument('--snapshot-json-encoder', type=Path)
    parser.add_argument('--evidence-dir', type=Path,
                        default=PROJECT / 'evidence/declare_war_scene_component')
    args = parser.parse_args()
    result = verify_component(
        args.snapshot_json_build.resolve(strict=True) if args.snapshot_json_build else None,
        args.snapshot_json_encoder if args.snapshot_json_encoder else None,
        Path(os.path.abspath(args.evidence_dir)))
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
