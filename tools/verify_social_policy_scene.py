"""Initialize the prepared stock policy tree and check its retained tab component."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
import xml.etree.ElementTree as ET

from verify_ui_scene import long_string, run_lua
from ui_font_profile import resolve_prepared_font_metrics
from prepare_ui_popup_assets import (
    STYLE_SOURCE, attach_social_policy_control_defaults, social_policy_control_default_sizes,
    social_policy_control_tree, lua_value,
)

PROJECT = Path(__file__).resolve().parents[1]
GAME = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Sid Meier's Civilization V")
COMMON_BEHAVIORS = GAME / 'Assets/UI/CommonBehaviors.lua'
SOCIAL_POLICY_XML = GAME / 'Assets/DLC/Expansion2/UI/InGame/Popups/SocialPolicyPopup.xml'
SOCIAL_POLICY_LUA = SOCIAL_POLICY_XML.with_suffix('.lua')
DEFAULT_PREPARED_ASSETS = PROJECT / 'evidence/ui_popup/assets/prepared.json'


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def policy_info_style_source(control_defaults: dict) -> tuple[Path, dict]:
    style_ref = control_defaults.get('PolicyInfo', {}).get('source', {})
    style_path = (GAME / STYLE_SOURCE).resolve(strict=True)
    if (style_ref.get('path') != str(style_path) or
            digest(style_path.read_bytes()) != style_ref.get('sha256')):
        raise RuntimeError('SocialPolicy component: original PolicyInfo style provenance changed')
    style = ET.fromstring(style_path.read_bytes()).find('Button_16')
    expected_style = {'Texture': 'Assets/UI/Art/Controls/Checkbox.dds', 'Size': '32,32'}
    if style is None or any(style.get(key) != value for key, value in expected_style.items()):
        raise RuntimeError('SocialPolicy component: source Button_16 style differs from the checkbox candidate')
    return style_path, style_ref


def verify_control_defaults(snapshots: Path, evidence_dir: Path | None = None) -> dict:
    """Exercise only default-size preparation against an already frozen Styles.xml."""
    snapshots = snapshots.resolve(strict=True)
    source = (GAME / STYLE_SOURCE).resolve(strict=True)
    frozen = (snapshots / STYLE_SOURCE).resolve(strict=True)
    source_bytes, frozen_bytes = source.read_bytes(), frozen.read_bytes()
    if source == frozen or source_bytes != frozen_bytes:
        raise RuntimeError('PolicyInfo regression requires a distinct, identical existing Styles.xml freeze')
    defaults = social_policy_control_default_sizes(snapshots)
    policy_info_style_source(defaults)
    expected = {'PolicyInfo': {
        'policy': 'SOCIAL_POLICY_BUTTON_16_DEFAULT_CANDIDATE_V1',
        'style': 'Button_16', 'width': 32, 'height': 32,
        'texture': 'Assets/UI/Art/Controls/Checkbox.dds',
        'sourceStyleAttributes': {'Texture': 'Assets/UI/Art/Controls/Checkbox.dds', 'Size': '32,32'},
        'source': {'path': str(source), 'sha256': digest(source_bytes)},
        'retailWidgetGeometryVerified': False,
    }}
    if defaults != expected:
        raise RuntimeError('PolicyInfo preparation changed the bounded original style candidate')
    rejected = []
    for name, path, sha256 in (('frozen_path_with_identical_sha256', frozen, digest(frozen_bytes)),
                               ('original_path_with_wrong_sha256', source, '0' * 64)):
        invalid = {'PolicyInfo': {**defaults['PolicyInfo'],
                                 'source': {'path': str(path), 'sha256': sha256}}}
        try:
            policy_info_style_source(invalid)
        except RuntimeError as error:
            if str(error) != 'SocialPolicy component: original PolicyInfo style provenance changed':
                raise
            rejected.append(name)
        else:
            raise RuntimeError('PolicyInfo provenance regression accepted ' + name)
    if source.read_bytes() != source_bytes or frozen.read_bytes() != frozen_bytes:
        raise RuntimeError('Original or frozen Styles.xml changed during default-size regression')
    result = {
        'status': 'PASS_SOCIAL_POLICY_CONTROL_DEFAULT_PROVENANCE_COMPONENT_ONLY',
        'control_default_sizes': defaults,
        'existing_frozen_style': {'path': str(frozen), 'sha256': digest(frozen_bytes)},
        'rejected_provenance_cases': rejected,
        'original_and_frozen_style_unchanged': True,
        'implementation_sha256': {
            'preparer': digest((PROJECT / 'tools/prepare_ui_popup_assets.py').read_bytes()),
            'verifier': digest(Path(__file__).read_bytes()),
        },
        'scope': {'default_size_function_executed': True, 'full_asset_preparation_executed': False,
                  'retail_sdk_renderer_and_live_game_verified': False},
    }
    if evidence_dir is not None:
        evidence_dir.mkdir(parents=True, exist_ok=True)
        (evidence_dir / 'result.json').write_text(
            json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2), encoding='utf-8')
    return result


def verify_component(encoder: Path, evidence_dir: Path | None = None,
                     prepared_assets: Path | None = None) -> dict:
    encoder = Path(os.path.abspath(encoder))
    if not encoder.is_file():
        raise RuntimeError('SocialPolicy component: snapshot JSON encoder is missing')
    scene_path = PROJECT / 'Source/Host/UiScene.lua'
    scene_bytes = scene_path.read_bytes()
    input_addendum_path = PROJECT / 'Source/Presentation/UiPresentationInput.lua'
    input_addendum_bytes = input_addendum_path.read_bytes()
    original = COMMON_BEHAVIORS.read_bytes()
    original_hash = digest(original)
    layout_xml = SOCIAL_POLICY_XML.read_bytes()
    layout_hash = digest(layout_xml)
    policy_source = SOCIAL_POLICY_LUA.read_bytes()
    policy_hash = digest(policy_source)
    policy_text = policy_source.decode('utf-8-sig')
    lifecycle_functions = (
        ('function OnPopupMessage(popupInfo)', 'Events.SerialEventGameMessagePopup.Add( OnPopupMessage );'),
        ('function OnClose()', 'Controls.CloseButton:RegisterCallback( Mouse.eLClick, OnClose );'),
        ('function ShowHideHandler( bIsHide, bInitState )', 'ContextPtr:SetShowHideHandler( ShowHideHandler );'),
    )
    lifecycle_source = ['local m_PopupInfo = nil;']
    for start, end in lifecycle_functions:
        if policy_text.count(start) != 1 or policy_text.count(end) != 1:
            raise RuntimeError('SocialPolicy component: original lifecycle function boundary changed')
        first = policy_text.index(start)
        last = policy_text.index(end, first) + len(end)
        lifecycle_source.append(policy_text[first:last])
    layout_root = ET.fromstring(layout_xml)
    set_string_labels = [f'IdeologyButtonLabel{level}{index}'
                         for level, slots in ((1, 7), (2, 4), (3, 3))
                         for index in range(1, slots + 1)]
    actual_set_string_labels = [node.get('ID') for node in layout_root.iter('Label')
                               if re.fullmatch(r'IdeologyButtonLabel[123][1-7]', node.get('ID', ''))]
    if actual_set_string_labels != set_string_labels:
        raise RuntimeError('SocialPolicy component: original 7/4/3 ideology Label controls changed')
    if re.findall(r'\blabelControl:SetString\((.*?)\)', policy_text) != ['""'] * 3:
        raise RuntimeError('SocialPolicy component: original label SetString calls changed')
    policy_scroll_panels = [node.get('ID') for node in layout_root.iter('ScrollPanel')]
    if policy_scroll_panels != ['TraditionPanel', 'LibertyPanel', 'HonorPanel', 'PietyPanel',
                                'PatronagePanel', 'RationalismPanel', 'ExplorationPanel',
                                'CommercePanel', 'AestheticsPanel']:
        raise RuntimeError('SocialPolicy component: original nine branch ScrollPanels changed')
    social_policy_pane = layout_root.find(".//Box[@ID='SocialPolicyPane']")
    policy_rows = next((node for node in (list(social_policy_pane) if social_policy_pane is not None else [])
                        if node.tag == 'Stack' and node.get('StackGrowth') == 'Bottom'), None)
    if (policy_rows is None or policy_rows.get('Size') != '0,0' or len(policy_rows) != 6 or
            [node.tag for node in policy_rows] != ['Image', 'Stack', 'Image', 'Stack', 'Image', 'Box']):
        raise RuntimeError('SocialPolicy component: original two-row auto-size stack structure changed')
    def original_size(node):
        values = [float(value.strip()) for value in node.get('Size', '0,0').split(',')]
        if len(values) != 2:
            raise RuntimeError('SocialPolicy component: malformed original row size')
        return values
    first_row_height = max(original_size(node)[1] for node in policy_rows[1])
    row_separator_height = original_size(policy_rows[2])[1]
    policy_row_y_delta = first_row_height + row_separator_height
    if first_row_height <= 0 or row_separator_height < 0 or policy_row_y_delta <= first_row_height:
        raise RuntimeError('SocialPolicy component: original first-row geometry is not measurable')
    hide_nodes = list(layout_root.iter('HideOnMouseOver'))
    if len(hide_nodes) != 18:
        raise RuntimeError('SocialPolicy component: stock HideOnMouseOver count differs from the 9-branch XML contract')
    if any(parent.tag != 'Box' for parent in layout_root.iter() for child in list(parent)
           if child.tag == 'HideOnMouseOver'):
        raise RuntimeError('SocialPolicy component: stock HideOnMouseOver is not an immediate Box child')
    child_counts = sorted(len(node) for node in hide_nodes)
    if child_counts != [1] * 9 + [2] * 9:
        raise RuntimeError('SocialPolicy component: stock hover-overlay children changed unexpectedly')
    prepared_assets = Path(os.path.abspath(prepared_assets or DEFAULT_PREPARED_ASSETS))
    prepared_bytes = prepared_assets.read_bytes()
    prepared = json.loads(prepared_bytes)
    runtime_layout = prepared.get('xml_control_trees', {}).get('SocialPolicyLayout')
    if not isinstance(runtime_layout, dict):
        raise RuntimeError('SocialPolicy component: prepared SocialPolicyLayout is missing')
    original_tree = social_policy_control_tree(layout_root)
    if {key: runtime_layout.get(key) for key in ('kind', 'attributes', 'children')} != original_tree:
        raise RuntimeError('SocialPolicy component: prepared tree differs from the complete original XML')
    if (runtime_layout.get('contextName') != 'SocialPolicyPopup' or
            runtime_layout.get('popupKind') != 'SocialPolicy'):
        raise RuntimeError('SocialPolicy component: prepared context identity differs from the original policy UI')
    original_ref = runtime_layout.get('socialPolicy', {}).get('originalLayoutXml', {})
    if (Path(original_ref.get('path', '')).resolve() != SOCIAL_POLICY_XML.resolve() or
            original_ref.get('sha256') != layout_hash):
        raise RuntimeError('SocialPolicy component: prepared tree has stale original XML provenance')
    control_defaults = prepared.get('social_policy_policy', {}).get('control_default_sizes')
    if not control_defaults or runtime_layout.get('controlDefaultSizes') != control_defaults:
        raise RuntimeError('SocialPolicy component: control default metadata was not attached to prepared runtime layout')
    style_path, style_ref = policy_info_style_source(control_defaults)

    def count(node: dict) -> int:
        return 1 + sum(count(child) for child in node['children'])

    static_count = 1 + sum(count(child) for child in original_tree['children'] if child['kind'] != 'Instance')
    # Resolve only this layout; shared banks and unrelated JSON keys stay unchanged.
    runtime_layout['fontMetrics'] = resolve_prepared_font_metrics(prepared, runtime_layout.get('fontMetrics'))
    if not runtime_layout['fontMetrics'].get('glyphSets'):
        raise RuntimeError('SocialPolicy component: prepared glyph metrics are missing')
    fixture_layout = {'kind': 'Context', 'attributes': {}, 'contextName': 'SocialPolicyPopup',
                      'popupKind': 'SocialPolicy'}
    attach_social_policy_control_defaults(fixture_layout, control_defaults)
    fixture_layout['children'] = [
        {'kind': 'Button', 'attributes': {'ID': 'TabButtonSocialPolicies', 'Offset': '10,10', 'Size': '100,28'}, 'children': []},
        {'kind': 'Button', 'attributes': {'ID': 'TabButtonIdeologies', 'Offset': '120,10', 'Size': '100,28'}, 'children': []},
        {'kind': 'Container', 'attributes': {'ID': 'SocialPoliciesPanel', 'Offset': '10,50', 'Size': '100,50'}, 'children': []},
        {'kind': 'Container', 'attributes': {'ID': 'IdeologiesPanel', 'Offset': '120,50', 'Size': '100,50'}, 'children': []},
        {'kind': 'Image', 'attributes': {'ID': 'TabButtonSocialPoliciesHL', 'Offset': '10,10', 'Size': '100,28'}, 'children': []},
        {'kind': 'Image', 'attributes': {'ID': 'TabButtonIdeologiesHL', 'Offset': '120,10', 'Size': '100,28'}, 'children': []},
        {'kind': 'CheckBox', 'attributes': {'ID': 'PolicyInfo', 'IsChecked': '1'}, 'children': []},
        {'kind': 'Box', 'attributes': {'ID': 'HoverBox', 'Offset': '250,10', 'Size': '100,100'}, 'children': [
            {'kind': 'HideOnMouseOver', 'attributes': {}, 'children': [
                {'kind': 'Button', 'attributes': {'ID': 'HoverGatedChild', 'Offset': '0,0', 'Size': '20,20'}, 'children': []},
            ]},
        ]},
        {'kind': 'Button', 'attributes': {'ID': 'HoverTrigger', 'Offset': '270,30', 'Size': '40,30'}, 'children': []},
        {'kind': 'Button', 'attributes': {'ID': 'CloseButton', 'Offset': '400,30', 'Size': '80,30'}, 'children': []},
    ]
    template = (PROJECT / 'Tests/social_policy_scene.lua').read_text(encoding='utf-8-sig')
    values = {
        '@@SCENE_SOURCE@@': long_string(scene_bytes.decode('utf-8-sig')),
        '@@INPUT_ADDENDUM@@': long_string(input_addendum_bytes.decode('utf-8-sig')),
        '@@COMMON_BEHAVIORS@@': long_string(original.decode('utf-8-sig')),
        '@@POLICY_LIFECYCLE@@': long_string('\n'.join(lifecycle_source)),
        '@@LAYOUT@@': lua_value(fixture_layout),
        '@@ORIGINAL_LAYOUT@@': lua_value(runtime_layout),
        '@@ORIGINAL_STATIC_COUNT@@': str(static_count),
        '@@SET_STRING_LABEL_IDS@@': lua_value(set_string_labels),
        '@@POLICY_SCROLL_PANEL_IDS@@': lua_value(policy_scroll_panels),
        '@@POLICY_ROW_Y_DELTA@@': lua_value(policy_row_y_delta),
    }
    for token, value in values.items():
        template = template.replace(token, value)
    if '@@' in template:
        raise RuntimeError('SocialPolicy component: unresolved source placeholder')
    with tempfile.TemporaryDirectory(prefix='social-policy-tabs-', dir=PROJECT / 'evidence') as temp_name:
        harness = Path(temp_name) / 'social-policy-harness.lua'
        harness.write_text(template, encoding='utf-8')
        report = json.loads(run_lua(encoder, harness, '__socialPolicyComponentReport'))
    if digest(COMMON_BEHAVIORS.read_bytes()) != original_hash:
        raise RuntimeError('Installed CommonBehaviors.lua changed during the component check')
    if digest(SOCIAL_POLICY_XML.read_bytes()) != layout_hash:
        raise RuntimeError('Installed SocialPolicyPopup.xml changed during the component check')
    if digest(SOCIAL_POLICY_LUA.read_bytes()) != policy_hash:
        raise RuntimeError('Installed SocialPolicyPopup.lua changed during the component check')
    if prepared_assets.read_bytes() != prepared_bytes:
        raise RuntimeError('Prepared SocialPolicyLayout changed during the component check')
    if scene_path.read_bytes() != scene_bytes or input_addendum_path.read_bytes() != input_addendum_bytes:
        raise RuntimeError('UiScene or input addendum source changed during the component check')
    if digest(style_path.read_bytes()) != style_ref['sha256']:
        raise RuntimeError('Original PolicyInfo style changed during the component check')
    instruction_counts = report.get('textBatchInstructions')
    if (type(instruction_counts) is not dict or
            set(instruction_counts) != {'eventPoliciesDirty', 'inputAddendumCallback'} or
            any(type(value) is not int or value <= 0 or value >= 8_000_000 or value % 1000
                for value in instruction_counts.values())):
        raise RuntimeError('SocialPolicy text batch lacks bounded 1000-instruction observations')
    required = {
        'componentOnly': True, 'originalCommonBehaviors': True,
        'originalTabCallbacksRegistered': True, 'socialPolicyPriorityAccepted': True,
        'tabsSwitchedBothWays': True, 'hideOnMouseOverGate': True,
        'policyInfoDefaultsReachedUiScene': True, 'policyInfoCheckboxInputRetained': True,
        'originalPreparedStaticTreeInitialized': True, 'originalTemplatesInitialized': 3,
        'originalStaticControlCount': static_count,
        'inputAddendumAppended': True, 'inputAddendumBranchZeroPayloadPreserved': True,
        'inputAddendumSecondPayloadPreserved': True, 'inputAddendumRankingPayloadOmitted': True,
        'originalSetStringLabelsCleared': 14, 'setStringTextGeometryReused': True,
        'setStringMeasurementRollback': True, 'setStringScopeRejections': 2,
        'originalPolicyScrollPanelsMeasured': 9, 'policyScrollRangesFromChildExtents': True,
        'originalPolicyOmittedAutoScrollBarFollowsContent': True,
        'originalPolicyNestedRowsSeparated': 1,
        'policyScrollInputClamped': True, 'policyScrollAddedHiddenChildrenUpdated': True,
        'activeOriginalTextBatchLabels': 14, 'activeOriginalTextBatchStatusLabels': 5,
        'textBatchEventBoundaries': 1, 'textBatchInputAddendumCallbacks': 1,
        'textBatchFinalGeometryMatchesExplicitAnchor': True, 'textBatchInputCoordinatesPreserved': True,
        'textBatchInstructionLimit': 8_000_000, 'textBatchInstructionInterval': 1000,
        'textBatchInstructions': instruction_counts,
        'coordinateAcceptedCases': 10, 'coordinateRejectedCases': 15,
        'originalPolicyLifecycleCallbacks': True, 'publicSubmitEventDispatches': 2,
        'publicSubmitOtherTypesRejected': 3, 'publicSubmitDuplicateRejected': True,
        'policySubmitRejectedByOtherContext': True,
        'shownEvents': 2, 'processedEvents': 2, 'balancedModalTimerCycles': 2,
        'policyProcessedOtherTypesRejected': 3,
        'closedPolicyLifecycleEventsRejected': True,
        'retailSdkRendererAndLiveGameVerified': False,
    }
    if report != required:
        raise RuntimeError('SocialPolicy component report differs from the bounded contract: ' + repr(report))
    result = {
        'status': 'PASS_SOCIAL_POLICY_ORIGINAL_TAB_HELPER_COMPONENT_ONLY',
        'common_behaviors_sha256': original_hash,
        'original_layout_xml_sha256': layout_hash,
        'original_policy_lua_sha256': policy_hash,
        'original_lifecycle_functions': ['OnPopupMessage', 'OnClose', 'ShowHideHandler'],
        'original_set_string_label_ids': set_string_labels,
        'original_scroll_panel_ids': policy_scroll_panels,
        'text_batch_instruction_profile': {
            'counts': instruction_counts,
            'counter': 'Lua 5.1 debug count hook on the existing component encoder',
            'instruction_interval': 1000, 'per_boundary_limit': 8_000_000,
            'unreported_tail_less_than': 1000,
            'boundaries': ['EventPoliciesDirty dispatch', 'public input addendum DispatchLeftClick'],
            'counts_include': 'component handler text batch and its event/input layout flush',
            'original_update_display_and_sdk_execution_measured': False,
        },
        'prepared_layout': {'path': str(prepared_assets), 'sha256': digest(prepared_bytes),
                            'original_xml_control_count': count(original_tree),
                            'initialized_static_control_count': static_count,
                            'initialized_instance_templates': 3},
        'stock_hide_on_mouse_over': {'count': len(hide_nodes), 'direct_parent': 'Box',
                                     'child_counts': {'one': 9, 'two': 9}},
        'implementation_sha256': {
            'host_ui_scene': digest(scene_bytes),
            'input_addendum': digest(input_addendum_bytes),
            'fixture': digest((PROJECT / 'Tests/social_policy_scene.lua').read_bytes()),
            'verifier': digest(Path(__file__).read_bytes()),
        },
        'fixture': report,
        'scope': {'original_common_behaviors_unmodified': True,
                  'complete_prepared_static_tree_initialized': True,
                  'original_policy_lifecycle_callbacks_executed': True,
                  'active_original_tree_text_batch_boundaries_verified': True,
                  'text_batch_final_geometry_and_input_coordinates_verified': True,
                  'original_social_policy_lua_and_sdk_executed': False,
                  'retail_sdk_renderer_and_live_game_verified': False},
    }
    if evidence_dir is not None:
        evidence_dir.mkdir(parents=True, exist_ok=True)
        (evidence_dir / 'result.json').write_text(
            json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2), encoding='utf-8')
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--snapshot-json-encoder', type=Path)
    parser.add_argument('--evidence-dir', type=Path)
    parser.add_argument('--prepared-assets', type=Path, default=DEFAULT_PREPARED_ASSETS)
    parser.add_argument('--control-default-snapshots', type=Path,
                        help='Check only PolicyInfo source provenance using an existing asset freeze')
    args = parser.parse_args()
    evidence_dir = Path(os.path.abspath(args.evidence_dir)) if args.evidence_dir else None
    if args.control_default_snapshots:
        if args.snapshot_json_encoder:
            parser.error('Use either the scene encoder or the control-default-only check')
        result = verify_control_defaults(args.control_default_snapshots, evidence_dir)
    else:
        if not args.snapshot_json_encoder:
            parser.error('--snapshot-json-encoder is required for the complete scene component check')
        result = verify_component(args.snapshot_json_encoder, evidence_dir, args.prepared_assets)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
