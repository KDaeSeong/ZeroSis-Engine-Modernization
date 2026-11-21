"""Focused renderer test for a retained original DeclareWar MOVE snapshot.

The snapshot must come from the DeclareWar scene component fixture or an SDK
capture. This test does not synthesize diplomacy, deal, alliance, or route data.
"""
from __future__ import annotations

import argparse
import copy
from contextlib import contextmanager
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from prepare_ui_popup_assets import (GAME, DECLARE_WAR_XML, declare_war_control_tree,
                                    inline_icon_catalog, production_font_metrics,
                                    production_style_defaults)
from render_ui_popup import retained_bounds
from ui_pixel_scene import (Compiler, valid_declare_war_lifecycle,
                            validate_hit_regions)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


@contextmanager
def readable_retail_paths():
    """Let Python read retail assets when this sandbox denies strict realpath."""
    original_resolve = Path.resolve
    retail_root = os.path.normcase(os.path.abspath(os.fspath(GAME)))

    def resolve(path: Path, strict: bool = False) -> Path:
        absolute = Path(os.path.abspath(os.fspath(path)))
        normalized = os.path.normcase(os.fspath(absolute))
        if normalized == retail_root or normalized.startswith(retail_root + os.sep):
            # These are source-only inputs under the known Steam install. The
            # test still reads each requested file; it only avoids resolving
            # the protected Program Files directory through its ACL boundary.
            return absolute
        return original_resolve(path, strict=strict)

    Path.resolve = resolve
    try:
        yield
    finally:
        Path.resolve = original_resolve


def nodes_by_id(node: dict) -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = {}

    def visit(current: dict) -> None:
        control_id = current.get('id')
        if control_id:
            result.setdefault(control_id, []).append(current)
        for child in current.get('children', []):
            visit(child)

    visit(node)
    return result


def original_layout_contract() -> dict:
    source = GAME / DECLARE_WAR_XML
    root = ET.parse(source).getroot()
    layout = declare_war_control_tree(root)
    instances = {element.get('Name') for element in root.findall('./Instance')}
    require(instances == {'CityStateInstance', 'UnderProtectionCivInstance', 'TradeRouteInstance'},
            'Retail DeclareWar XML instance template set changed')
    ids = {element.get('ID') for element in root.iter() if element.get('ID')}
    required = {
        'PopupText', 'LeaderFrame', 'RivalFrame', 'DeclareWarDetailsScrollPanel',
        'DeclareWarDetailsStack', 'UnderProtectionOfStack', 'AlliedCityStatesStack',
        'ActiveDealsStack', 'TradeRoutesStack', 'Button1', 'Button2',
        'DiplomacyHeader', 'UnderProtectionOfHeader', 'AlliedCityStatesHeader',
        'ActiveDealsHeader', 'TradeRoutesHeader',
    }
    require(required <= ids, 'Original DeclareWar layout lost a visible section or action control')
    scroll = next(element for element in root.iter()
                  if element.get('ID') == 'DeclareWarDetailsScrollPanel')
    require(scroll.get('Vertical') == '1' and scroll.get('AutoScrollBar') == '0' and
            [child.tag for child in scroll][:3] == ['ScrollBar', 'UpButton', 'DownButton'],
            'Original DeclareWar scroll controls or orientation changed')
    buttons = {element.get('ID'): element for element in root.iter()
               if element.tag == 'GridButton' and element.get('ID') in ('Button1', 'Button2')}
    require(buttons['Button1'].find('./Label').get('String') == 'TXT_KEY_DECLARE_WAR_YES' and
            buttons['Button2'].find('./Label').get('String') == 'TXT_KEY_DECLARE_WAR_NO',
            'Original DeclareWar Yes/No button order changed')
    return layout


def stock_input_contract() -> None:
    ids = ('Button1', 'Button2', 'DiplomacyHeader', 'AlliedCityStatesHeader',
           'ActiveDealsHeader')
    geometry = [{'key': index, 'id': control_id, 'input_target': True,
                 'input_targets': ['LeftClick'], 'event': 'LeftClick'}
                for index, control_id in enumerate(ids, 1)]
    hits = [(row['key'], row['key'] * 10, 10, row['key'] * 10 + 8, 18)
            for row in geometry]
    validate_hit_regions('declare-war', hits, geometry)
    invalid = [*geometry, {'key': 99, 'id': 'SyntheticWarAction', 'input_target': True,
                           'input_targets': ['LeftClick'], 'event': 'LeftClick'}]
    invalid_hits = [*hits, (99, 990, 10, 998, 18)]
    try:
        validate_hit_regions('declare-war', invalid_hits, invalid)
    except ValueError:
        return
    raise AssertionError('DeclareWar accepted a non-original click target')


def validate_snapshot(snapshot: dict, *, active: bool) -> None:
    require(type(snapshot) is dict and snapshot.get('contextName') == 'DeclareWarPopup' and
            snapshot.get('popupKind') == 'DeclareWar' and snapshot.get('hasRetainedPopupUi') is True,
            'Snapshot does not identify the original retained DeclareWar context')
    if active:
        require(snapshot.get('active') is True and snapshot.get('timerSemaphore') == 1 and
                snapshot.get('animationPolicy') == 'ZEROSIS_FRONTEND_XML_TIMELINE_V1' and
                snapshot.get('retailTimingVerified') is False and
                valid_declare_war_lifecycle(snapshot.get('lifecycle'), active=True),
                'Active DeclareWar snapshot lacks the retained timer/clock contract')
        targets = snapshot.get('inputTargets')
        require(type(targets) is list, 'Active DeclareWar snapshot has no input target list')
        decision_targets = [target for target in targets if target.get('id') in ('Button1', 'Button2')]
        allowed_targets = {'Button1', 'Button2', 'DiplomacyHeader', 'UnderProtectionOfHeader',
                           'AlliedCityStatesHeader', 'ActiveDealsHeader', 'TradeRoutesHeader'}
        require(sorted((target.get('id'), target.get('event')) for target in decision_targets) ==
                [('Button1', 'LeftClick'), ('Button2', 'LeftClick')] and
                all(target.get('event') == 'LeftClick' and target.get('id') in allowed_targets
                    for target in targets),
                'Active DeclareWar snapshot exposes non-stock input or lacks its Yes/No callbacks')
        scrolls = snapshot.get('scrollTargets')
        require(type(scrolls) is list and
                sum(target.get('id') == 'DeclareWarDetailsScrollPanel' and
                    target.get('event') == 'Scroll' for target in scrolls) == 1,
                'Active DeclareWar snapshot does not retain its stock details scroll target')
    else:
        require(snapshot.get('active') is False and snapshot.get('timerSemaphore') == 0 and
                valid_declare_war_lifecycle(snapshot.get('lifecycle'), active=False) and
                snapshot.get('inputTargets') == [] and snapshot.get('scrollTargets') == [],
                'Escape/dequeue snapshot does not have the stock empty closed state')


def render_active(snapshot: dict, output: Path, inline_icons: dict) -> tuple[bytes, dict]:
    snapshot_before = copy.deepcopy(snapshot)
    compiler = Compiler(GAME, output, inline_colors={}, inline_icons=inline_icons,
                        context='declare-war', snapshot_clock=snapshot.get('presentationClock'))
    packet = compiler.compile(snapshot)
    require(snapshot == snapshot_before, 'Renderer mutated the retained GameCore snapshot')
    bounds = retained_bounds(snapshot, compiler.geometry, context='declare-war')
    visible = nodes_by_id(snapshot['tree'])
    for control_id in ('DiplomacyHeader', 'UnderProtectionOfHeader', 'AlliedCityStatesHeader',
                       'ActiveDealsHeader', 'TradeRoutesHeader', 'DeclareWarDetailsScrollPanel',
                       'DeclareWarDetailsStack', 'UnderProtectionOfStack', 'AlliedCityStatesStack',
                       'ActiveDealsStack', 'TradeRoutesStack', 'Button1', 'Button2'):
        require(control_id in visible,
                'Renderer fixture dropped an original DeclareWar section/control: ' + control_id)
    require(all(any(not row.get('hidden', True) for row in visible[control_id])
                for control_id in ('Button1', 'Button2', 'DeclareWarDetailsScrollPanel')) and
            len(compiler.hits) == len(snapshot['inputTargets']) and len(compiler.scroll_regions) == 1,
            'Renderer did not encode the visible stock buttons/scroll target and retained callbacks')
    require(any(row.get('id') == 'Button1' and row.get('input_target') for row in compiler.geometry) and
            any(row.get('id') == 'Button2' and row.get('input_target') for row in compiler.geometry),
            'Rendered geometry lost original Yes/No input provenance')
    return packet, bounds


def run(active_path: Path, closed_path: Path) -> dict:
    stock_input_contract()
    original_layout_contract()
    active = json.loads(active_path.read_text(encoding='utf-8-sig'))
    closed = json.loads(closed_path.read_text(encoding='utf-8-sig'))
    validate_snapshot(active, active=True)
    validate_snapshot(closed, active=False)
    with tempfile.TemporaryDirectory(prefix='zerosis_declare_war_renderer_',
                                     dir=ROOT / 'Build') as temp_text:
        temp = Path(temp_text)
        snapshots = temp / 'frozen_assets'
        snapshots.mkdir()
        icons, _ = inline_icon_catalog(snapshots)
        source_layout = original_layout_contract()
        styles = production_style_defaults(snapshots, source_layout)
        source_layout['styleDefaults'] = styles['controls']
        source_layout['fontMetrics'] = production_font_metrics(source_layout, icons)
        source_metrics = source_layout['fontMetrics']
        fixture_metrics = active['fontMetrics']
        # UiScene exports the font identities and layout metrics used by its
        # Lua fixture. The renderer separately derives glyph tables and inline
        # icon records from retail assets, so those renderer-only fields must
        # not be expected in the Lua snapshot.
        require(fixture_metrics.get('fonts') == source_metrics.get('fonts') and
                fixture_metrics.get('policy') == source_metrics.get('policy') and
                fixture_metrics.get('wrapPolicy') == source_metrics.get('wrapPolicy') and
                fixture_metrics.get('retailMetricSemanticsVerified') is False and
                fixture_metrics.get('retailTabMetricsVerified') is False and
                fixture_metrics.get('tabPolicy') == 'ZEROSIS_TAB_FOUR_GGXML_SPACE_ADVANCES_V1',
                'Active snapshot font metrics differ from original DeclareWar XML/font inputs')
        with readable_retail_paths():
            active_packet, bounds = render_active(active, temp / 'active', icons)
            closed_compiler = Compiler(GAME, temp / 'closed', inline_colors={}, inline_icons=icons,
                                       context='declare-war', snapshot_clock=closed.get('presentationClock'))
            closed_packet = closed_compiler.compile(closed, closed=True)
        require(closed_packet[:8] == b'ZSUPIX02' and
                struct.unpack('<6I', closed_packet[8:32]) == (1920, 1080, 0, 0, 0, 0),
                'Closed DeclareWar scene is not the expected empty ZSUPIX02 packet')
        require(active_packet[:8] == b'ZSUPIX02', 'Active DeclareWar did not use retained-scene packet ZSUPIX02')
        return {
            'status': 'PASS_DECLARE_WAR_RENDERER_FIXTURE',
            'active_snapshot': os.path.abspath(active_path),
            'closed_snapshot': os.path.abspath(closed_path),
            'visible_geometry': len([row for row in bounds['checked']]),
            'deferred_geometry': len(bounds['deferred']),
            'active_packet_bytes': len(active_packet),
            'closed_packet_bytes': len(closed_packet),
            'retail_pixel_equivalence_verified': False,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--active-snapshot', type=Path, required=True)
    parser.add_argument('--closed-snapshot', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.active_snapshot, args.closed_snapshot),
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
