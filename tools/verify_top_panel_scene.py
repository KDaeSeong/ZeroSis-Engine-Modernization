"""Exercise the unchanged installed BNW TopPanel Lua in a focused fixture.

This proves component behavior only; SDK bindings, retained rendering, and a
live Civ V session remain separate integration gates.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path
import xml.etree.ElementTree as ET

from prepare_ui_popup_assets import (
    GAME, inline_icon_catalog, production_font_metrics,
    production_style_defaults, top_panel_control_tree,
)
from verify_ui_scene import long_string, lua_value, run_lua

PROJECT = Path(__file__).resolve().parents[1]
TOP_PANEL_LUA = GAME / 'Assets/DLC/Expansion2/UI/InGame/TopPanel.lua'
TOP_PANEL_XML = GAME / 'Assets/DLC/Expansion2/UI/InGame/TopPanel.xml'


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fail(message: str) -> None:
    raise RuntimeError('TopPanel scene component: ' + message)


def verify_component(encoder: Path, evidence_dir: Path | None = None) -> dict:
    encoder = Path(os.path.abspath(encoder))
    if not encoder.is_file():
        fail('snapshot JSON encoder is missing')
    source_lua, source_xml = TOP_PANEL_LUA.read_bytes(), TOP_PANEL_XML.read_bytes()
    source_hashes = {'TopPanel.lua': sha(source_lua), 'TopPanel.xml': sha(source_xml)}
    with tempfile.TemporaryDirectory(prefix='top-panel-scene-', dir=PROJECT / 'evidence') as temp_name:
        snapshots = Path(temp_name) / 'frozen-ui'
        icons, icon_sources = inline_icon_catalog(snapshots)
        root = ET.fromstring(source_xml)
        tree = top_panel_control_tree(root)
        tree.update({'contextName': 'TopPanel', 'popupKind': 'TopPanel'})
        styles = production_style_defaults(snapshots, tree)
        tree['styleDefaults'] = styles['controls']
        tree['styleDefaultsSource'] = styles['source']
        tree['styleDefaultsPolicy'] = styles['policy']
        tree['fontMetrics'] = production_font_metrics(tree, icons)

        template = (PROJECT / 'Tests/top_panel_scene.lua').read_text(encoding='utf-8-sig')
        values = {
            '@@SOURCE_TOP_PANEL@@': long_string(source_lua.decode('utf-8-sig')),
            '@@SCENE_SOURCE@@': long_string((PROJECT / 'Source/Host/UiScene.lua').read_text(encoding='utf-8-sig')),
            '@@INPUT_SOURCE@@': long_string((PROJECT / 'Source/Presentation/UiPresentationInput.lua').read_text(encoding='utf-8-sig')),
            '@@LAYOUT@@': lua_value(tree),
            '@@FONT_METRICS@@': lua_value(tree['fontMetrics']),
            '@@STYLE_DEFAULTS@@': lua_value(tree['styleDefaults']),
        }
        for token, value in values.items():
            template = template.replace(token, value)
        if '@@' in template:
            fail('fixture has an unresolved source placeholder')
        harness = Path(temp_name) / 'top-panel-harness.lua'
        harness.write_text(template, encoding='utf-8')
        report = json.loads(run_lua(encoder, harness, '__topPanelComponentReport'))
        required = {
            'componentOnly': True, 'originalLuaUnmodified': True,
            'originalControlsRetained': True, 'scienceRequestDeferred': True,
            'tooltipCallbacksRetained': True, 'tooltipCallbackLifecycle': True,
            'tooltipClearedOnPointerLeave': True, 'nonmodalSnapshot': True,
            'refreshVisibleBoolean': True, 'stopLeavesContextHidden': True,
            'negativeGoldOriginalColorScope': True,
            'unsupportedRoutesRemainUnfinished': True,
            'retailSdkRendererAndGameVerified': False,
        }
        if any(report.get(key) != value for key, value in required.items()):
            fail('fixture result differs from the required stock TopPanel contract: ' + repr(report))
        snapshot = report.get('snapshot')
        if not isinstance(snapshot, dict) or snapshot.get('topPanel', {}).get('activePlayer') != 0:
            fail('fixture did not retain active-player snapshot metadata')
        tooltip_snapshot = report.get('tooltipSnapshot')
        tooltip = tooltip_snapshot.get('topPanelTooltip') if isinstance(tooltip_snapshot, dict) else None
        if not isinstance(tooltip, dict) or tooltip.get('type') != 'TooltipTypeTopPanel' or \
           tooltip.get('tree', {}).get('autoSizeRequested') is not True:
            fail('fixture did not retain the original tooltip callback control state')
        if sha(TOP_PANEL_LUA.read_bytes()) != source_hashes['TopPanel.lua'] or \
           sha(TOP_PANEL_XML.read_bytes()) != source_hashes['TopPanel.xml']:
            fail('installed original TopPanel source changed during verification')
        result = {
            'status': 'PASS_TOP_PANEL_ORIGINAL_LUA_COMPONENT_ONLY',
            'original_source_sha256': source_hashes,
            'implementation_sha256': {
                'asset_preparer': sha((PROJECT / 'tools/prepare_ui_popup_assets.py').read_bytes()),
                'host_ui_scene': sha((PROJECT / 'Source/Host/UiScene.lua').read_bytes()),
                'presentation_input': sha((PROJECT / 'Source/Presentation/UiPresentationInput.lua').read_bytes()),
                'fixture': sha((PROJECT / 'Tests/top_panel_scene.lua').read_bytes()),
                'verifier': sha(Path(__file__).read_bytes()),
            },
            'inline_icon_sources': icon_sources,
            'retained_control_count': sum(1 for _ in root.iter()),
            'fixture': required,
            'snapshot': snapshot,
            'tooltip_snapshot': tooltip_snapshot,
            'verified': {
                'installed_original_lua_and_xml_unmodified': True,
                'stock_science_and_resource_labels': True,
                'original_science_callback_queues_typed_request_after_callback': True,
                'refresh_returns_boolean_and_stop_quiesces_context': True,
                'original_tooltip_callback_and_pointer_leave_lifecycle': True,
                'nonmodal_zero_timer_metadata': True,
                'retail_tooltip_placement_and_autosize': False,
                'retail_sdk_binding_renderer_and_live_game': False,
            },
        }
        if evidence_dir is not None:
            evidence_dir.mkdir(parents=True, exist_ok=True)
            (evidence_dir / 'snapshot.json').write_text(
                json.dumps(snapshot, ensure_ascii=False, sort_keys=True, indent=2), encoding='utf-8')
            (evidence_dir / 'tooltip-snapshot.json').write_text(
                json.dumps(tooltip_snapshot, ensure_ascii=False, sort_keys=True, indent=2), encoding='utf-8')
            (evidence_dir / 'result.json').write_text(
                json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2), encoding='utf-8')
        return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--snapshot-json-encoder', type=Path, required=True)
    parser.add_argument('--evidence-dir', type=Path,
                        default=PROJECT / 'evidence/top_panel_scene_component')
    args = parser.parse_args()
    result = verify_component(args.snapshot_json_encoder,
                              Path(os.path.abspath(args.evidence_dir)))
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
