"""Compile an owned retained UI tree into bounded original-atlas paint commands.

This is a selected popup presentation candidate. It does not run Lua/GameCore,
generate another popup, change game state, or assert retail pixel equivalence.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import xml.etree.ElementTree as ET

from civ5_ui_assets import (UiAssets, require, sha256, candidate_directory, header, rgba32,
                           normalized_header, materialize_font_atlas)
from ui_bitmap_fonts import Glyph, load_font, layout_text

SOLID = 0xffffffff
# CivEnums.h notification hashes whose original Lua rows use fixed BigStack
# controls instead of one InstanceManager row per SDK notification.
FIXED_NOTIFICATION_CONTROL_TYPES = {
    0x5ACFA6F7: 'Tech',
    0x77014C62: 'Production',
    0x489B80B6: 'FreeTech',
    0x963AC73A: 'StealTech',
    0x1E4417C5: 'FreePolicy',
    0xAB4C3BB3: 'FreeGreatPerson',
    0x4C4B3599: 'FoundPantheon',
    0x7EE00DFD: 'FoundReligion',
    0xE9C73F3F: 'EnhanceReligion',
    0x050B6287: 'AddReformationBelief',
    0x2D0E554C: 'LeagueCallForProposals',
    0x84B7E406: 'ChooseArchaeology',
    0x97DEEB2F: 'LeagueCallForVotes',
    0x1192A3F3: 'ChooseIdeology',
}
KINDS = {'Context', 'Instance', 'AlphaAnim', 'Box', 'Button', 'Container', 'DownButton',
         'Grid', 'GridButton', 'Image', 'Label', 'Meter', 'ScrollAnim', 'ScrollBar',
         'ScrollPanel', 'ShowOnMouseOver', 'HideOnMouseOver', 'Stack', 'TextureBar', 'UpButton', 'TextButton', 'LuaContext',
         'CheckBox', 'RadioButton', 'WorldAnchor', 'FlipAnim', 'SlideAnim', 'Bar', 'EditBox', 'PullDown', 'Slider'}
# BUTTONPOPUP_CHOOSETECH is ordinal 11 in Source/SDK_BNW_x64/CvGameCoreDLLUtil/include/CvEnums.h.
RESEARCH_POPUP_ENUM_VALUE = 11
# BUTTONPOPUP_TECH_TREE is ordinal 67 in the same SDK enum.
RESEARCH_TREE_POPUP_ENUM_VALUE = 67
# BUTTONPOPUP_TECH_AWARD immediately follows BUTTONPOPUP_TECH_TREE in the frozen BNW enum.
TECH_AWARD_POPUP_ENUM_VALUE = 68
GOODY_HUT_REWARD_POPUP_ENUM_VALUE = 57
# DIPLO_UI_STATE_DEFAULT_ROOT is ordinal 0 in DiploUIStateTypes in the frozen BNW CvEnums.h.
DIPLO_UI_STATE_DEFAULT_ROOT_ENUM_VALUE = 0
# DIPLO_UI_STATE_WAR_DECLARED_BY_HUMAN follows DEFAULT_ROOT in that frozen enum.
DIPLO_UI_STATE_WAR_DECLARED_BY_HUMAN_ENUM_VALUE = 1
# LEADERHEAD_ANIM_INTRO is explicitly 1 in LeaderheadAnimationTypes in that same header.
LEADERHEAD_ANIM_INTRO_ENUM_VALUE = 1
# LEADERHEAD_ANIM_ATTACKED is explicitly 6 in the frozen BNW CvEnums.h.
LEADERHEAD_ANIM_ATTACKED_ENUM_VALUE = 6
PRIVATE_MENU_CONTEXTS = {
    'menu-options': ('OptionsMenu_InGame', 'MenuOptions', 'HOST_SUPPORTED_OPTIONS_SUBSET_V1'),
    'touch-help': ('TouchControlsMenu', 'TouchHelp', 'ORIGINAL_TOUCH_HELP_V1'),
    'map-menu': ('SaveMapMenu', 'MapMenu', 'ORIGINAL_PRIVATE_MAP_MENU_V1'),
}
SCENE_CONTEXTS = ('production', 'research', 'research-tree', 'tech-award', 'goody-hut-reward', 'city-capture', 'diplomacy', 'city-view', 'unit-panel', 'declare-war', 'top-panel', 'trade-route', 'social-policy', 'economic-overview', 'action-info-panel', 'notification-panel', 'game-menu', 'save-menu', 'load-menu', 'exit-confirm', 'pantheon', *PRIVATE_MENU_CONTEXTS)
RESEARCH_CONTEXTS = ('research', 'research-tree')


def private_menu_contract(snapshot, sources=None, *, context, closed=False):
    """Source-exact private child scenes, with explicitly inventoried derivatives.

    A compiled packet proves bounded source/geometry/input binding. It does not
    prove a native settings backend, map serialization, a displayed window, or
    complete support for the retail OptionsManager API.
    """
    require(context in PRIVATE_MENU_CONTEXTS and type(snapshot) is dict and type(closed) is bool,
            'Unknown private menu scene')
    name, kind, profile = PRIVATE_MENU_CONTEXTS[context]
    require((snapshot.get('contextName'), snapshot.get('popupKind')) == (name, kind) and
            snapshot.get('active') is (not closed) and snapshot.get('contextHidden') is closed and
            type(snapshot.get('timerSemaphore')) is int and snapshot['timerSemaphore'] == 0,
            'Private menu context, visibility or parent-owned timer differs')
    metadata = snapshot.get('mapMenu' if context == 'map-menu' else 'menuOptions')
    require(type(metadata) is dict and type(metadata.get('owner')) is int and metadata['owner'] >= 0 and
            type(metadata.get('turn')) is int and metadata['turn'] >= 0 and
            metadata.get('parentContext') in (('GameMenu', 'SaveMenu') if context == 'map-menu' else ('GameMenu',)),
            'Private menu lost its actual player/turn/parent')
    provenance = metadata.get('source')
    require(type(provenance) is dict and provenance.get('profile') == profile and
            provenance.get('completeOriginalXmlRetained') is True and
            provenance.get('retailWidgetGeometryVerified') is False and
            provenance.get('nativeDisplayVerified') is False,
            'Private menu source or unverified native/retail boundary changed')
    identities = {
        'menu-options': (('Assets/UI/Options/OptionsMenu.lua', 70204, '76247d52606e8486101e91cad3668b3a4a56257ddbd4df991ef182e9a70c5921'),
                         ('Assets/UI/Options/OptionsMenu.xml', 29601, 'a8bd7dbc98544179edfd5c8dba57e6855a4b8fbc5a01a039bcd1579feb7fe7a2')),
        'touch-help': (('Assets/UI/TouchControlsMenu.lua', 838, '6305aeea4e6c2c538fffa5f1a30f76c3538fbdef8aedaeaf9992f8f7db72d988'),
                       ('Assets/UI/TouchControlsMenu.xml', 6475, 'de143c20da99754154088e29e253b9f27da1dc36785d1bec32c8d968c60a6893')),
        'map-menu': (('Assets/UI/InGame/Menus/SaveMapMenu.lua', 8537, '2b5121a0ee4be0c909d7f0526b2f8a4cb2b265b21df6ad0e62e5a12da5d83550'),
                     ('Assets/UI/InGame/Menus/SaveMapMenu.xml', 6685, '8c48b02d5241874995350dc65d2348e61f5af67c92916d2be915bf5fc6e3e826')),
    }
    refs = {}
    for field, (relative, size, digest) in zip(('originalLua', 'originalXml'), identities[context]):
        ref = provenance.get(field)
        require(type(ref) is dict and type(ref.get('path')) is str and
                ref['path'].replace('\\', '/').endswith('/' + relative) and
                type(ref.get('bytes')) is int and ref['bytes'] == size and ref.get('sha256') == digest,
                'Private menu source identity differs: ' + field)
        path = Path(ref['path']).resolve(strict=True)
        require(path.is_file() and path.stat().st_size == size and sha256(path) == digest and
                (sources is None or sources.get(path) == digest), 'Private menu source bytes changed: ' + field)
        refs[field] = {'path': str(path), 'sha256': digest}
    relative = identities[context][0][0]
    game_root = Path(refs['originalLua']['path']).parents[len(Path(relative).parts) - 1]
    style_path = game_root / 'Assets/UI/Styles.xml'
    refs['originalStyles'] = {'path': str(style_path), 'sha256': sha256(style_path)}
    require(sources is None or sources.get(style_path) == refs['originalStyles']['sha256'],
            'Private menu styles differ from the selected original')
    if context == 'map-menu':
        require(metadata.get('privateCatalogOnly') is True and metadata.get('campaignSave') is False and
                metadata.get('originalScript') is True and metadata.get('nativeAcceptanceVerified') is False,
                'Map menu confused private map export with campaign/native save acceptance')
    else:
        require(metadata.get('retailSettingsWritten') is False and metadata.get('retailOptionsLuaExecuted') is False and
                provenance.get('retailOptionApiSurfaceCount') == 133 and
                len(provenance.get('retailOptionApiSurface', [])) == 133 and
                provenance.get('privateSettingsSchema') == 'ZEROSIS_PRIVATE_MENU_OPTIONS_V3' and
                provenance.get('readablePrivateSettingsSchemas') == ['ZEROSIS_PRIVATE_MENU_OPTIONS_V1',
                    'ZEROSIS_PRIVATE_MENU_OPTIONS_V2','ZEROSIS_PRIVATE_MENU_OPTIONS_V3'] and
                provenance.get('privateKeys') == ['noBasicHelp','hideTouchHelp','uiCueVolumePercent','windowWidth',
                    'windowHeight','fullscreen','vsync','policyInfo','noRewardPopups'] and
                metadata.get('profile') == profile and type(metadata.get('open')) is bool and
                metadata['open'] is (not closed), 'Private options must disclose its actual supported subset')
    lifecycle = snapshot.get('lifecycle')
    close_marker = 'closed' if context == 'map-menu' else 'context-hidden:' + name
    require(type(lifecycle) is list and lifecycle and lifecycle[0] == 'queued' and
            (not closed or lifecycle[-1] == close_marker), 'Private menu did not complete its owned child lifecycle')
    original = ET.parse(refs['originalXml']['path']).getroot()
    option_widget = None
    option_styles = None
    if context == 'menu-options':
        from civ5_ui_assets import supported_original_menu_handlers as supported_original_handlers, menu_slider_style
        require(provenance.get('originalSupportedHandlers') == supported_original_handlers(game_root) and
                provenance.get('sliderStyle') == menu_slider_style(game_root) and
                metadata.get('originalSupportedHandlersExecuted') is True and
                type(metadata.get('originalHandlerInvocations')) is dict and
                set(metadata['originalHandlerInvocations']) <= {
                    row['name'] for row in provenance['originalSupportedHandlers']['functions']} and
                all(type(count) is int and count > 0 for count in metadata['originalHandlerInvocations'].values()) and
                type(metadata.get('originalEffectsSlider')) is bool,
                'Options original callback/style extraction or execution scope changed')
        widgets = snapshot.get('pullDowns')
        require(type(widgets) is list and len(widgets) == 1 and type(widgets[0]) is dict,
                'Options resolution PullDown lacks its unique original style component')
        option_widget = widgets[0]
        require(option_widget.get('style') == 'GenericPullDown' and
                option_widget.get('originalStyleSource') == {'path':'Assets/UI/Styles.xml',
                    'sha256':refs['originalStyles']['sha256']} and
                type(option_widget.get('opened')) is bool and
                option_widget.get('retailGeometryVerified') is False and
                option_widget.get('retailWidgetBehaviorVerified') is False,
                'Options resolution PullDown lost exact style provenance or unverified widget boundary')
        option_styles = ET.parse(style_path).getroot().find('GenericPullDown')
        require(option_styles is not None, 'Original GenericPullDown style is missing')
    templates = {node.get('Name'): node for node in original if node.tag == 'Instance'}
    nodes, visible, clips, parent_keys, derived = {}, {}, {}, {}, {}
    derived_ids = {'ZeroSisOptionsStatus': 'Label', 'ZeroSisCueVolumeLabel': 'Label',
        'ZeroSisCueQuieter': 'GridButton', 'ZeroSisCueLouder': 'GridButton', 'ZeroSisCueScope': 'Label'} if context == 'menu-options' else {
        'ZeroSisTouchStatus': 'Label'} if context == 'touch-help' else {}
    def collect(node, parent_key, parent_visible, clip, source=None):
        require(type(node) is dict and type(node.get('attributes')) is dict and
                type(node.get('sourceAttributes')) is dict and type(node.get('children')) is list and
                type(node.get('key')) is int and node['key'] > 0 and node['key'] not in nodes and
                type(node.get('hidden')) is bool and type(node.get('disabled')) is bool and
                all(type(node.get(field)) in (int, float) and math.isfinite(node[field]) for field in ('x', 'y', 'width', 'height')) and
                node['width'] >= 0 and node['height'] >= 0, 'Private menu retained control is malformed')
        key = node['key'];nodes[key] = node;parent_keys[key] = parent_key
        shown = parent_visible and not node['hidden'];visible[key] = shown;clips[key] = clip
        if node['kind'] == 'ShowOnMouseOver':
            require(type(node.get('hovered')) is bool, 'Private menu hover group lacks its retained boolean')
            shown = shown and node['hovered']
        child_clip = intersect(clip, rect(tuple(node[field] for field in ('x', 'y', 'width', 'height')))) if node['kind'] == 'ScrollPanel' else clip
        origin = node.get('styleChildSource')
        if context == 'menu-options' and origin is not None:
            require(type(origin) is dict and set(origin) == {'style','ownerKey','ownerPullDownKey','path','sha256','indices'} and
                    origin.get('style') == 'GenericPullDown' and
                    origin.get('ownerKey') == origin.get('ownerPullDownKey') == option_widget.get('key') and
                    origin.get('path') == 'Assets/UI/Styles.xml' and origin.get('sha256') == refs['originalStyles']['sha256'] and
                    type(origin.get('indices')) is list and origin['indices'] and
                    all(type(index) is int and index > 0 for index in origin['indices']),
                    'Options resolution component is not bound to its original style owner')
            exact = option_styles
            for index in origin['indices']:
                require(index <= len(exact), 'Options resolution style index is outside its original source')
                exact = exact[index - 1]
            source_kind = {'GridData':'Grid','ScrollPanelData':'ScrollPanel','StackData':'Stack'}.get(exact.tag, exact.tag)
            require(node['kind'] == source_kind and node['sourceAttributes'] == dict(exact.attrib),
                    'Options resolution component changed its exact original style node')
            if source is None:
                source = ET.Element(source_kind, exact.attrib)
                source.extend(list(exact))
        if context == 'menu-options' and source is None and node.get('overlayOwnerKey') is not None:
            require(node.get('overlayOwnerKey') == option_widget['key'] and node.get('key') == option_widget['popupKey'],
                    'Options promoted popup escaped its original resolution owner')
        if source is None:
            attrs = node['sourceAttributes'];control_id = node.get('id', '')
            parent = nodes.get(parent_key)
            require(context != 'map-menu' and attrs.get('ZeroSisDerivedMenuControl') == 'HOST_MENU_ADAPTER_V1' and
                    (derived_ids.get(control_id) == node['kind'] or control_id == '' and node['kind'] == 'Label' and
                     parent is not None and parent.get('id') in ('ZeroSisCueQuieter', 'ZeroSisCueLouder')),
                    'Uninventoried private menu derivative control')
            derived[key] = {'key': key, 'id': control_id, 'kind': node['kind'], 'parentKey': parent_key,
                            'sourceAttributes': attrs}
            for child in node['children']:collect(child, key, shown, child_clip)
            return
        require(node.get('kind') == source.tag and node.get('sourceAttributes') == dict(source.attrib) and
                node.get('id', '') == source.get('ID', ''), 'Private menu changed or removed original XML source data')
        fixed = [child for child in source if child.tag != 'Instance']
        require(len(node['children']) >= len(fixed), 'Private menu dropped original XML children')
        for child, source_child in zip(node['children'], fixed):collect(child, key, shown, child_clip, source_child)
        for child in node['children'][len(fixed):]:
            if context == 'map-menu':
                require(source.get('ID') == 'LoadFileButtonStack' and child.get('instanceTemplate') == 'LoadButton' and
                        'LoadButton' in templates and len(templates['LoadButton']) == 1,
                        'Map list row is not its exact original LoadButton template')
                collect(child, key, shown, child_clip, templates['LoadButton'][0])
            else:
                outside = (context == 'menu-options' and node['kind'] == 'ScrollPanel' and
                    child.get('scrollPanelChromeOwnerKey') == key)
                collect(child, key, shown, clip if outside else child_clip)
    collect(snapshot.get('tree'), 0, True, (0, 0, 1920, 1080), original)
    require(tuple(snapshot['tree'][field] for field in ('x', 'y', 'width', 'height')) == (0, 0, 1920, 1080),
            'Private menu logical viewport changed')
    frame_source = next(element for element in original if element.tag == 'Grid')
    frames = [node for node in nodes.values() if node['kind'] == 'Grid' and node['sourceAttributes'] == dict(frame_source.attrib)]
    require(len(frames) == 1 and tuple(frames[0][field] for field in ('x','y','width','height')) ==
            anchor(frame_source.attrib, (0,0,1920,1080), *pair(frame_source.get('Size'))),
            'Private menu central frame differs from its original XML anchor/size')
    modal_allowed = set(nodes)
    resolution_callback_keys = set()
    if option_widget is not None:
        require(option_widget.get('key') in nodes and nodes[option_widget['key']].get('id') == 'WResolutionPull' and
                nodes[option_widget['key']]['kind'] == 'PullDown' and
                all(type(option_widget.get(field)) is int and option_widget[field] in nodes for field in
                    ('buttonKey','popupKey','scrollPanelKey','stackKey')) and
                option_widget.get('entryKeys') == [child['key'] for child in nodes[option_widget['stackKey']]['children']] and
                option_widget['opened'] is visible[option_widget['popupKey']],
                'Options resolution component key/entry/visibility inventory changed')
        for key,node in nodes.items():
            if node.get('styleChildSource', {}).get('ownerPullDownKey') == option_widget['key']:
                resolution_callback_keys.add(key)
        if option_widget['opened']:
            modal_allowed = {key for key in nodes if key in resolution_callback_keys} | {snapshot['tree']['key']}
    if context == 'map-menu':
        confirmations = [key for key,node in nodes.items() if node.get('id') == 'DeleteConfirm']
        require(len(confirmations) == 1, 'Map menu lost its unique original confirmation')
        confirmation = confirmations[0]
        if visible[confirmation]:
            preorder = list(nodes);modal_allowed = set(preorder[preorder.index(confirmation):])
    if context != 'map-menu':
        require(metadata.get('derivedControlPolicy') == 'HOST_MENU_ADAPTER_V1' and
                metadata.get('derivedControls') == [derived[key] for key in sorted(derived)],
                'Private menu derivative inventory differs from the exact retained control keys/source attributes')
    targets, scrolls = snapshot.get('inputTargets'), snapshot.get('scrollTargets')
    require(type(targets) is list and type(scrolls) is list and (not closed or targets == scrolls == []),
            'Private menu lacks bounded/closed input inventories')
    callback_ids = ({'GameButton', 'IFaceButton', 'VideoButton', 'AudioButton', 'PolicyInfo', 'NoBasicHelpCheckbox', 'NoRewardPopupsCheckbox', 'FullscreenCheck', 'VSyncCheck',
        'ApplyResButton', 'DefaultButton', 'AcceptButton', 'CancelButton', 'ZeroSisCueQuieter', 'ZeroSisCueLouder'} if context == 'menu-options' else
        {'CloseButton', 'DontShowAgainCheckbox'} if context == 'touch-help' else
        {'Button', 'SaveButton', 'Delete', 'BackButton', 'Yes', 'No', 'NameBox'})
    seen, consumers = set(), []
    for target in targets:
        require(type(target) is dict and type(target.get('key')) is int and target['key'] in nodes and
                target['key'] not in seen and target.get('event') in ('LeftClick', 'ConsumeMouse', 'SliderValue') and
                target.get('visible') is True and target.get('disabled') is False, 'Private menu target is hidden, stale or malformed')
        key = target['key'];seen.add(key);node = nodes[key]
        require(key in modal_allowed and visible[key] and not node['disabled'] and target.get('id', '') == node.get('id', '') and
                xywh_dict(target.get('bounds'), 'Private menu hit') == rect(tuple(node[field] for field in ('x', 'y', 'width', 'height'))) and
                xywh_dict(target.get('clippedBounds'), 'Private menu clipped hit') == intersect(
                    rect(tuple(node[field] for field in ('x', 'y', 'width', 'height'))), clips[key]),
                'Private menu target bounds or original visible ownership changed')
        if target.get('inputRole') == 'PullDownDismiss':
            require(option_widget is not None and option_widget['opened'] and key == snapshot['tree']['key'] and
                    target.get('event') == 'LeftClick' and target.get('ownerPullDownKey') == option_widget['key'],
                    'Options resolution dismissal escaped its exact root owner')
        elif target['event'] == 'SliderValue':
            require(context == 'menu-options' and node['kind'] == 'Slider' and node.get('id') == 'EffectsVolumeSlider' and
                    metadata['originalEffectsSlider'] is True and type(target.get('value')) in (int,float) and
                    math.isfinite(target['value']) and 0 <= target['value'] <= 1 and
                    type(node.get('sliderValue')) in (int,float) and target['value'] == node.get('sliderValue') and
                    type(target.get('minimum')) is int and type(target.get('maximum')) is int and
                    type(node.get('sliderMinimum')) is int and type(node.get('sliderMaximum')) is int and
                    target.get('minimum') == node.get('sliderMinimum') == 0 and
                    target.get('maximum') == node.get('sliderMaximum') == 1 and
                    node.get('sliderStyle') == provenance['sliderStyle'] and
                    node.get('sliderGeometryPolicy') == provenance['sliderStyle']['policy'] and
                    node.get('retailSliderBehaviorVerified') is False and target.get('void1') == 1 and
                    target.get('consumeMouse') is True,
                    'Options slider input/range/readback escaped its exact original supported control')
        elif target['event'] == 'ConsumeMouse':
            require(target.get('consumeMouse') is True and node['kind'] in ('Box', 'Grid') and
                    (node['attributes'].get('ConsumeMouse') in ('1', 'true', 'True') or
                     context == 'map-menu' and node.get('id') == 'DeleteConfirm' and
                     node['sourceAttributes'].get('ConsumeMouseOver') == '1' or
                     option_widget is not None and option_widget['opened'] and key == option_widget['popupKey']),
                    'Private menu invented a mouse-consumption region')
            consumers.append(key)
        else:
            require((node.get('id') in callback_ids or key in resolution_callback_keys) and
                    node['kind'] in ('Button', 'GridButton', 'TextButton', 'CheckBox', 'EditBox', 'UpButton', 'DownButton'),
                    'Private menu exposed an unsupported retail option callback')
    if context == 'menu-options':
        caps = metadata.get('supportedCapabilities')
        require(type(caps) is dict and set(caps) == {'noBasicHelp','noRewardPopups','uiCueVolumePercent','windowWidth','windowHeight','fullscreen','vsync','policyInfo'} and
                all(type(value) is bool for value in caps.values()) and caps['windowWidth'] is caps['windowHeight'],
                'Private options lack exact typed backend capability observations')
        dependencies = {'NoBasicHelpCheckbox':'noBasicHelp','NoRewardPopupsCheckbox':'noRewardPopups','ApplyResButton':'windowWidth',
                        'FullscreenCheck':'fullscreen','VSyncCheck':'vsync','ZeroSisCueQuieter':'uiCueVolumePercent',
                        'ZeroSisCueLouder':'uiCueVolumePercent','AudioButton':'uiCueVolumePercent',
                        'EffectsVolumeSlider':'uiCueVolumePercent','IFaceButton':'policyInfo','PolicyInfo':'policyInfo'}
        require(all(caps[dependencies[target['id']]] for target in targets if target.get('id') in dependencies),
                'Unsupported Host backend acquired an enabled visible option')
        require(not any(target.get('id') == 'GameButton' for target in targets) or
                any(caps[key] for key in ('noBasicHelp','noRewardPopups')), 'Game tab has no actual Host backend')
        require(not any(target.get('id') == 'VideoButton' for target in targets) or
                any(caps[key] for key in ('windowWidth','fullscreen','vsync')), 'Video tab has no actual Host backend')
    for target in scrolls:
        require((context == 'map-menu' or option_widget is not None and option_widget['opened'] and
                 target.get('key') == option_widget['scrollPanelKey']) and type(target) is dict and target.get('key') in nodes and
                target['key'] in modal_allowed and nodes[target['key']]['kind'] == 'ScrollPanel' and target.get('event') == 'Scroll' and
                target.get('visible') is True and target.get('disabled') is False, 'Private menu scroll escaped its source viewport')
    return {'policy':'ZEROSIS_PRIVATE_MENU_SCENE_V1', 'context':context, **refs, 'closed':closed,
        'owner':metadata['owner'],'turn':metadata['turn'],'parent_context':metadata['parentContext'],'timer_semaphore':0,
        'full_original_tree_matched':True,'retained_control_count':len(nodes),'derived_control_keys':sorted(derived),
        'derived_control_policy':'HOST_MENU_ADAPTER_V1','retail_options_api_complete':False,
        'retail_options_lua_executed':False,'native_acceptance_verified':False,'retail_pixels_verified':False,
        'input_order_keys':[target['key'] for target in targets],'consume_mouse_keys':consumers,
        'scroll_input_keys':[target['key'] for target in scrolls],
        'slider_input_keys':[target['key'] for target in targets if target['event'] == 'SliderValue'],
        'resolution_widget_state': option_widget,
        'confirmation_visible':context == 'map-menu' and visible[confirmation]}


def _local_save_delete_contract(menu, confirmation, *, closed=False):
    """Validate optional owned-file deletion without claiming native acceptance."""
    fields = ('localDeleteImplemented', 'localDeleteBackendBound', 'selectedFileCanDelete',
              'deleteConfirmationVisible', 'deleteConfirmationArmed')
    if not any(field in menu for field in fields):
        return {'implemented': False, 'bound': False, 'selected': False, 'armed': False}
    require(all(type(menu.get(field)) is bool for field in fields) and
            menu['localDeleteImplemented'] is True and
            menu['deleteConfirmationVisible'] is (not confirmation['hidden']),
            'Owned save deletion lacks exact typed capability/confirmation observations')
    bound, selected, armed = (menu[field] for field in
                              ('localDeleteBackendBound', 'selectedFileCanDelete', 'deleteConfirmationArmed'))
    require((not selected or bound) and
            (not armed or (bound and selected and not confirmation['hidden'])) and
            (not closed or (not selected and not armed)),
            'Owned save deletion escaped its current selection or confirmation lifetime')
    return {'implemented': True, 'bound': bound, 'selected': selected, 'armed': armed}


def _local_save_overwrite_contract(menu, confirmation, deletion, *, closed=False):
    """Keep the shared stock confirmation bound to exactly one owned action."""
    fields = ('localOverwriteImplemented', 'localOverwriteBackendBound', 'overwriteEligible',
              'overwriteConfirmationArmed', 'saveActionAvailable', 'confirmationOp')
    if not any(field in menu for field in fields):
        return {'implemented': False, 'bound': False, 'eligible': False, 'armed': False,
                'save_available': menu.get('nameAvailable'), 'operation': 'delete' if deletion['armed'] else 'none'}
    require(all(type(menu.get(field)) is bool for field in fields[:-1]) and
            menu['localOverwriteImplemented'] is True and
            menu.get('confirmationOp') in ('none', 'delete', 'overwrite'),
            'Owned save overwrite lacks exact typed capability/action observations')
    bound, eligible, armed = (menu[field] for field in
                              ('localOverwriteBackendBound', 'overwriteEligible', 'overwriteConfirmationArmed'))
    require((not eligible or bound) and (not armed or (bound and eligible and not confirmation['hidden'])) and
            not (armed and deletion['armed']) and
            menu['confirmationOp'] == ('overwrite' if armed else 'delete' if deletion['armed'] else 'none') and
            menu['saveActionAvailable'] is (menu['nameAvailable'] or eligible) and
            (not closed or (not eligible and not armed and not menu['saveActionAvailable'])),
            'Owned save overwrite escaped its capability, exclusive confirmation or lifetime')
    return {'implemented': True, 'bound': bound, 'eligible': eligible, 'armed': armed,
            'save_available': menu['saveActionAvailable'], 'operation': menu['confirmationOp']}


def save_menu_contract(snapshot, sources=None, *, closed=False):
    """Verify the unchanged stock child screen and its bounded native adapters."""
    require(type(snapshot) is dict and
            (snapshot.get('contextName'), snapshot.get('popupKind')) == ('SaveMenu', 'SaveMenu') and
            snapshot.get('active') is (not closed) and type(snapshot.get('timerSemaphore')) is int and
            snapshot['timerSemaphore'] == 0 and
            snapshot.get('lifecycle') == (['queued', 'closed'] if closed else ['queued']),
            'SaveMenu must retain its child lifecycle without owning the parent timer')
    menu = snapshot.get('saveMenu')
    map_bound = type(menu) is dict and menu.get('mapMenuSourceBound') is True
    require(type(menu) is dict and ('mapMenuSourceBound' not in menu or type(menu['mapMenuSourceBound']) is bool),
            'SaveMenu map source-binding capability must be an explicit boolean')
    require(type(menu) is dict and menu.get('parentContext') == 'GameMenu' and menu.get('modal') is True and
            type(menu.get('owner')) is int and menu['owner'] >= 0 and
            type(menu.get('turn')) is int and menu['turn'] >= 0 and menu.get('timerSemaphore') == 0 and
            menu.get('timerSemaphorePolicy') == 'PARENT_GAME_MENU_RETAINS_ONE_CHILD_OWNS_ZERO' and
            menu.get('catalogScope') == 'CURRENT_ENGINE_SESSION_NATIVE_ZSSAVE_ONLY' and
            menu.get('unsupportedActions') == ([*(() if menu.get('localOverwriteBackendBound') is True else ('overwrite',)),
                *(() if menu.get('localDeleteBackendBound') is True else ('delete',)), 'cloud',
                *(() if map_bound else ('saveMap',))]) and
            menu.get('retailLayoutVerified') is False and menu.get('retailTextEditingVerified') is False,
            'SaveMenu owner, catalog, unsupported actions, or retail proof boundary changed')
    refs = {}
    for field, relative in {
        'originalLua': 'Assets/UI/InGame/Menus/SaveMenu.lua',
        'originalXml': 'Assets/UI/InGame/Menus/SaveMenu.xml',
        'originalUniqueBonusesLua': 'Assets/UI/FrontEnd/GameSetup/UniqueBonuses.lua',
    }.items():
        ref = menu.get(field)
        require(type(ref) is dict and type(ref.get('path')) is str and
                re.fullmatch(r'[0-9a-f]{64}', ref.get('sha256', '')) is not None and
                ref['path'].replace('\\', '/').endswith('/' + relative),
                'SaveMenu source provenance changed: ' + field)
        path = Path(ref['path']).resolve(strict=True)
        require(path.is_file() and sha256(path) == ref['sha256'] and
                ('bytes' not in ref or path.stat().st_size == ref['bytes']) and
                (sources is None or sources.get(path) == ref['sha256']),
                'SaveMenu immutable source hash changed: ' + field)
        refs[field] = {'path': str(path), 'sha256': ref['sha256']}
    original = ET.parse(refs['originalXml']['path']).getroot()
    templates = [node for node in original if node.tag == 'Instance']
    require(len(templates) == 1 and templates[0].get('Name') == 'LoadButton' and len(templates[0]) == 1 and
            menu.get('instanceNames') == ['LoadButton'] and
            menu.get('retainedControlCount') == len(list(original.iter())), 'Original SaveMenu template inventory changed')
    lua = Path(refs['originalLua']['path']).read_text(encoding='utf-8-sig')
    require(menu.get('includeNames') == re.findall(r'^include\(\s*"([^"\n]+)"\s*\);', lua, re.MULTILINE),
            'Original SaveMenu include inventory changed')
    callback_ids = set(re.findall(r'Controls\.([A-Za-z_][A-Za-z0-9_]*):RegisterCallback\(', lua))
    nodes, visible, descendants, static_callbacks = {}, {}, {}, set()
    rows = active_rows = 0

    def compare(source, node, parent_visible=True, ancestors=()):
        nonlocal rows, active_rows
        require(type(node) is dict and node.get('kind') == source.tag and
                node.get('sourceAttributes') == dict(source.attrib) and node.get('id', '') == source.get('ID', '') and
                type(node.get('key')) is int and node['key'] > 0 and node['key'] not in nodes and
                type(node.get('children')) is list and type(node.get('hidden')) is bool and
                type(node.get('disabled')) is bool and type(node.get('attributes')) is dict,
                'SaveMenu retained control differs from exact original tree')
        key = node['key'];nodes[key] = node;descendants[key] = ancestors
        shown = parent_visible and not node['hidden']
        if source.tag == 'ShowOnMouseOver': shown = shown and node.get('hovered') is True
        visible[key] = shown
        if source.get('ID') in callback_ids or source.get('ID') == 'Button': static_callbacks.add(key)
        if source.tag == 'LuaContext':
            require(node['hidden'] and not node['children'], 'SaveMapMenu declaration must remain hidden in its parent VM')
        fixed = [child for child in source if child.tag != 'Instance']
        children = node['children'];dynamic = source.get('ID') == 'LoadFileButtonStack'
        require(len(children) >= len(fixed) and (dynamic or len(children) == len(fixed)),
                'SaveMenu dropped or invented an original control')
        for child, retained in zip(fixed, children): compare(child, retained, shown, (*ancestors, key))
        for retained in children[len(fixed):]:
            rows += 1;require(rows <= 4096, 'SaveMenu list exceeds its bounded catalog')
            compare(templates[0][0], retained, shown, (*ancestors, key))
            # Stock InstanceManager pools the Button inside InstanceRoot. The
            # wrapper may remain visible after that Button is released.
            pool_roots = [child for child in economic_walk(retained) if child.get('id') == 'Button']
            require(len(pool_roots) == 1, 'SaveMenu pooled row lost its original Button root')
            button = pool_roots[0]
            lineage = descendants[button['key']]
            local_lineage = lineage[lineage.index(retained['key']):] if button is not retained else ()
            if not button['hidden'] and all(not nodes[ancestor]['hidden'] for ancestor in local_lineage):
                active_rows += 1

    compare(original, snapshot.get('tree'), not closed)
    named = {name: [node for node in nodes.values() if node.get('id') == name]
             for name in ('NameBox', 'SaveButton', 'BackButton', 'Delete', 'CloudCheck',
                          'SaveMapButton', 'Yes', 'DeleteConfirm')}
    require(all(len(found) == 1 for found in named.values()), 'SaveMenu missing unique original controls')
    named = {name: found[0] for name, found in named.items()}
    name = named['NameBox']
    require(name.get('kind') == 'EditBox' and name.get('maxLength') == 32 and
            type(name.get('text')) is str and len(name['text']) <= 32 and
            type(name.get('caretCodepoint')) is int and 0 <= name['caretCodepoint'] <= len(name['text']) and
            type(name.get('focused')) is bool and menu.get('name') == name['text'] and
            menu.get('focusKey') == (name['key'] if name['focused'] else 0) and
            menu.get('textInputEnabled') is (not closed and name['focused'] and named['DeleteConfirm']['hidden']) and
            type(menu.get('focusEpoch')) is int and 0 < menu['focusEpoch'] <= 9007199254740991 and
            menu.get('textInputFocusToken') == (menu['focusEpoch'] if menu['textInputEnabled'] else 0) and
            type(menu.get('nameAvailable')) is bool,
            'SaveMenu NameBox focus, length, caret, or name availability changed')
    deletion = _local_save_delete_contract(menu, named['DeleteConfirm'], closed=closed)
    overwrite = _local_save_overwrite_contract(menu, named['DeleteConfirm'], deletion, closed=closed)
    require(named['SaveButton']['disabled'] is (not overwrite['save_available']),
            'SaveMenu SaveButton differs from new-name or exact existing overwrite admission')
    require(named['CloudCheck']['disabled'] and named['CloudCheck']['hidden'] and
            (not named['SaveMapButton']['disabled'] and not named['SaveMapButton']['hidden'] if map_bound else
             named['SaveMapButton']['disabled'] and named['SaveMapButton']['hidden']) and
            menu.get('cloudCheckGeometryVerified') is False and menu.get('unsupportedCloudCheckHidden') is True and
            menu.get('catalogCount') == active_rows,
            'SaveMenu cloud gate, source-bound map entry or catalog differs')
    if not closed:
        require(named['Delete']['disabled'] is (not deletion['selected']) and
                named['Yes']['disabled'] is (not (deletion['armed'] or overwrite['armed'])),
                'SaveMenu delete/overwrite/Yes eligibility differs from its exact original confirmation')
    elif not deletion['bound'] and not overwrite['bound']:
        require(named['Delete']['disabled'] and named['Yes']['disabled'],
                'SaveMenu mutation requires its optional owned-file backend')
    require(tuple(snapshot['tree'].get(field) for field in ('x', 'y', 'width', 'height')) == (0, 0, 1920, 1080),
            'SaveMenu viewport changed')
    expected, consumers = [], []
    confirmation = named['DeleteConfirm']
    for key, node in nodes.items():
        allowed = confirmation['hidden'] or key == confirmation['key'] or confirmation['key'] in descendants[key]
        if not visible[key] or not allowed: continue
        callback = key in static_callbacks and not node['disabled']
        consume = (node.get('attributes', {}).get('ConsumeMouse') == '1' or
                   node.get('attributes', {}).get('ConsumeMouseButton') == '1' or
                   (key == confirmation['key'] and node.get('sourceAttributes', {}).get('ConsumeMouseOver') == '1'))
        if callback: expected.append((key, 'LeftClick'))
        elif consume: expected.append((key, 'ConsumeMouse'));consumers.append(key)
    targets = snapshot.get('inputTargets')
    require(type(targets) is list and [(row.get('key'), row.get('event')) for row in targets] == expected,
            'SaveMenu input targets differ from original enabled controls and input consumers')
    for target in targets:
        node = nodes[target['key']]
        require(target.get('id') == node.get('id', '') and target.get('visible') is True and
                target.get('disabled') is False and
                xywh_dict(target.get('bounds'), 'SaveMenu input') ==
                (node['x'], node['y'], node['x'] + node['width'], node['y'] + node['height']),
                'SaveMenu input identity or geometry differs from original retained control')
        clipped = xywh_dict(target.get('clippedBounds'), 'SaveMenu clipped input')
        require(positive(clipped), 'SaveMenu input is fully clipped')
    return {'source_refs': refs, 'input_order_keys': [row['key'] for row in targets],
            'consume_mouse_keys': consumers, 'catalog_rows': active_rows, 'pooled_catalog_rows': rows,
            'modal_input_keys': [key for key in nodes if confirmation['hidden'] or
                                 key == confirmation['key'] or confirmation['key'] in descendants[key]],
            'original_layout_bytes_preserved': True, 'retail_pixels_verified': False,
            'native_save_load_verified': False, 'text_editing_policy': name.get('textInputPolicy'),
            'local_delete_implemented': deletion['implemented'], 'local_delete_backend_bound': deletion['bound'],
            'local_delete_confirmation_armed': deletion['armed'], 'native_delete_verified': False,
            'local_overwrite_implemented': overwrite['implemented'], 'local_overwrite_backend_bound': overwrite['bound'],
            'local_overwrite_confirmation_armed': overwrite['armed'], 'common_confirmation_operation': overwrite['operation'],
            'native_overwrite_verified': False, 'map_source_apis_bound': map_bound}


def game_menu_once_alpha(attributes, animation, clock):
    """Check the stock menu's hover-started .2-to-zero, one-second fade."""
    require(attributes.get('Cycle') == 'Once' and
            all(float(attributes.get(name, 'nan')) == value for name, value in
                (('AlphaStart', .2), ('AlphaEnd', 0), ('Speed', 1), ('Pause', 0))),
            'GameMenu Once animation differs from the exact original hover fade')
    require(type(animation) is dict and animation.get('clock') == clock and
            animation.get('timingPolicy') == 'CIV5_GAME_MENU_ONCE_HOVER_CANDIDATE_V1' and
            animation.get('retailTimingVerified') is False and
            animation.get('childOpacityPolicy') == 'MULTIPLY_CAPTURED_ALPHA_THROUGH_DESCENDANTS' and
            all(type(animation.get(field)) in (int, float) and math.isfinite(animation[field])
                for field in ('alpha', 'elapsed', 'normalizedPhase', 'activationStartTime')) and
            type(animation.get('running')) is bool and type(animation.get('completed')) is bool,
            'GameMenu Once animation lacks its captured hover timeline/proof boundary')
    elapsed, start = animation['elapsed'], animation['activationStartTime']
    phase = animation['normalizedPhase']
    require(type(clock) in (int, float) and math.isfinite(clock) and
            0 <= start <= clock and 0 <= elapsed <= 1 and
            abs(phase - elapsed) <= 1e-9 and
            abs(animation['alpha'] - .2 * (1 - phase)) <= 1e-9 and
            animation['completed'] is (phase == 1) and
            not (animation['running'] and animation['completed']),
            'GameMenu Once alpha/phase/completion differs from its original linear fade')
    available = min(1, clock - start)
    require(elapsed <= available + 1e-9 and
            (not animation['running'] or abs(elapsed - available) <= 1e-9),
            'GameMenu Once elapsed time differs from its captured hover activation')
    return animation['alpha']


def game_menu_contract(snapshot, sources=None, *, closed=False):
    """Validate original children and distinguish source bindings from live VMs."""
    require(type(snapshot) is dict and
            (snapshot.get('contextName'), snapshot.get('popupKind')) == ('GameMenu', 'GameMenu') and
            snapshot.get('active') is (not closed) and
            type(snapshot.get('timerSemaphore')) is int and
            snapshot['timerSemaphore'] == (0 if closed else 1) and
            snapshot.get('lifecycle') == (['queued', 'closed'] if closed else ['queued']),
            'GameMenu must retain its original enter/leave modal lifecycle')
    menu = snapshot.get('gameMenu')
    require(type(menu) is dict and type(menu.get('owner')) is int and menu['owner'] >= 0 and
            type(menu.get('turn')) is int and menu['turn'] >= 0 and
            menu.get('modal') is True and type(menu.get('timerSemaphore')) is int and
            menu['timerSemaphore'] == snapshot['timerSemaphore'] and
            menu.get('childContextsRuntimeVerified') is False and menu.get('retailLayoutVerified') is False and
            menu.get('originalButtonVisibilityPreserved') is True and
            menu.get('embeddedContextPolicy') == 'ORIGINAL_HIDDEN_DECLARATIONS_RETAINED_NOT_INSTANTIATED' and
            menu.get('timerSemaphorePolicy') == 'ORIGINAL_ON_ENTER_ON_LEAVE_ONCE_ACROSS_CHILD_MENUS' and
            menu.get('quickSavePolicy') == 'ORIGINAL_ON_RETURN_THEN_UI_QUICK_SAVE_REQUIRES_NATIVE_DISPATCH',
            'GameMenu lacks its actual owner/turn or unconnected child-context boundary')
    refs = {}
    for field, relative in {
        'originalLua': 'Assets/UI/InGame/Menus/GameMenu.lua',
        'originalXml': 'Assets/DLC/Expansion2/UI/InGame/Menus/GameMenu.xml',
        'originalMapUtilitiesLua': 'Assets/Gameplay/Lua/MapUtilities.lua',
    }.items():
        ref = menu.get(field)
        require(type(ref) is dict and type(ref.get('path')) is str and type(ref.get('sha256')) is str and
                re.fullmatch(r'[0-9a-f]{64}', ref.get('sha256', '')) is not None and
                ref['path'].replace('\\', '/').endswith('/' + relative),
                'GameMenu source provenance does not identify its original asset: ' + field)
        path = Path(ref['path']).resolve(strict=True)
        require(path.is_file() and sha256(path) == ref['sha256'] and
                ('bytes' not in ref or path.stat().st_size == ref['bytes']) and
                (sources is None or sources.get(path) == ref['sha256']),
                'GameMenu source bytes/hash differ from the selected original: ' + field)
        refs[field] = {'path': str(path), 'sha256': ref['sha256']}
    original = ET.parse(refs['originalXml']['path']).getroot()
    styles_path = Path(refs['originalLua']['path']).parents[2] / 'Styles.xml'
    styles = {style.tag: dict(style.attrib) for style in ET.parse(styles_path).getroot()}
    refs['originalStyles'] = {'path': str(styles_path), 'sha256': sha256(styles_path)}
    require(sources is None or sources.get(styles_path) == refs['originalStyles']['sha256'],
            'GameMenu inherited input styles differ from the selected original Styles.xml')
    require(styles.get('BGBlock', {}).get('Size') == 'Full,Full' and
            styles['BGBlock'].get('ConsumeMouse') == '1',
            'Original GameMenu BGBlock no longer declares its full-screen input consumer')
    declarations = [node for node in original if node.tag == 'LuaContext']
    expected_ids = ['LoadMenu', 'SaveMenu', 'SaveMapMenu', 'OptionsMenu_InGame', 'TouchControlsMenu']
    require([node.get('ID') for node in declarations] == expected_ids and
            all(node.get('Hidden') in ('True', '1') and len(node) == 0 for node in declarations),
            'Original GameMenu no longer has its exact five hidden child declarations')
    declared = [{'kind': 'LuaContext', 'attributes': dict(node.attrib), 'children': []}
                for node in declarations]
    load_source_bound = menu.get('loadMenuSourceApisBound')
    require(load_source_bound is None or type(load_source_bound) is bool,
            'GameMenu LoadMenu source-binding flag is not a boolean')
    source_children = ['SaveMenu', 'LoadMenu'] if load_source_bound is True else []
    unconnected = [node for node in declared if node['attributes']['ID'] not in source_children]
    require(menu.get('unconnectedLuaContexts') == unconnected and
            (menu.get('sourceConnectedChildren') == source_children if load_source_bound is True else
             menu.get('sourceConnectedChildren') is None or menu.get('sourceConnectedChildren') == []),
            'GameMenu source-bound child inventory conflicts with its original declarations')
    templates = {node.get('Name'): node for node in original if node.tag == 'Instance'}
    require(set(templates) == {'GameOption', 'ModEntryInstance'} and
            all(len(node) == 1 and node[0].tag == 'Label' for node in templates.values()),
            'Original GameMenu detail/mod template contract differs')
    dynamic_stacks = {'SetupOptions': 'GameOption', 'VictoryConditions': 'GameOption',
                      'AdvancedOptions': 'GameOption', 'ModsStack': 'ModEntryInstance'}
    nodes, visible, callback_sources, consumer_sources, clipped_bounds = {}, {}, {}, {}, {}
    lua = Path(refs['originalLua']['path']).read_text(encoding='utf-8-sig')
    callback_ids = set(re.findall(r'Controls\.([A-Za-z_][A-Za-z0-9_]*):RegisterCallback\(', lua))
    require(menu.get('retainedControlCount') == len(list(original.iter())) and
            menu.get('instanceNames') == ['GameOption', 'ModEntryInstance'] and
            menu.get('includeNames') == re.findall(r'^include\("([^"\n]+)"\);', lua, re.MULTILINE),
            'GameMenu template/include inventory differs from its complete original source')
    dynamic_count = 0

    def compare(source, node, parent_visible=True, clip=(0, 0, 1920, 1080), hover_visible=True):
        nonlocal dynamic_count
        require(type(node) is dict and node.get('kind') == source.tag and
                node.get('sourceAttributes') == dict(source.attrib) and
                node.get('id', '') == source.get('ID', '') and
                type(node.get('children')) is list and type(node.get('attributes')) is dict and
                type(node.get('key')) is int and node['key'] > 0 and node['key'] not in nodes and
                type(node.get('hidden')) is bool and type(node.get('disabled')) is bool,
                'GameMenu retained tree differs from its original control kind/attributes/key')
        nodes[node['key']] = node
        is_visible = parent_visible and not node['hidden']
        if source.tag in ('ShowOnMouseOver', 'HideOnMouseOver'):
            require(type(node.get('hovered')) is bool, 'GameMenu hover input gate lacks its captured state')
            hover_visible = hover_visible and (node['hovered'] if source.tag == 'ShowOnMouseOver' else not node['hovered'])
        visible[node['key']] = is_visible and hover_visible
        effective = {**styles.get(source.get('Style'), {}), **source.attrib}
        require(node['attributes'].get('ConsumeMouse') == effective.get('ConsumeMouse'),
                'GameMenu input consumption differs from its original XML and inherited style')
        if consume_mouse_enabled(effective):
            consumer_sources[node['key']] = source.tag
        bounds = xywh_dict({name: node.get(name) for name in ('x', 'y', 'width', 'height')},
                           'GameMenu retained control')
        clipped_bounds[node['key']] = intersect(bounds, clip)
        if source.get('Style') == 'BGBlock':
            require(bounds == (0, 0, 1920, 1080),
                    'GameMenu original BGBlock must consume the complete viewport')
        child_clip = intersect(clip, bounds) if source.tag == 'ScrollPanel' else clip
        if source.tag == 'AlphaAnim' and source.get('Cycle') == 'Once':
            game_menu_once_alpha(source.attrib, node.get('animation'), snapshot.get('presentationClock'))
        if source.tag == 'LuaContext':
            require(node['hidden'] is True and not node['children'] and
                    node['attributes'].get('Hidden') == source.get('Hidden'),
                    'GameMenu child LuaContext must remain its original hidden, uninstantiated declaration')
        if 'instanceTemplate' in node:
            require(node['instanceTemplate'] in templates and
                    source is templates[node['instanceTemplate']][0],
                    'GameMenu dynamic row claims a different original template')
        if source.get('ID') in callback_ids:
            require(source.tag in ('GridButton', 'TextButton', 'Button') and
                    node['attributes'].get('String') == source.get('String') and
                    type(node.get('text')) is str and
                    (not source.get('String') or bool(node['text'].strip())),
                    'GameMenu callback control lost its original button/caption contract')
            callback_sources[node['key']] = source.get('ID')
        fixed = [child for child in source if child.tag != 'Instance']
        rows = node['children']
        template_name = dynamic_stacks.get(source.get('ID'))
        require(len(rows) >= len(fixed) and (template_name is not None or len(rows) == len(fixed)),
                'GameMenu retained tree dropped or invented an original control')
        for child, retained in zip(fixed, rows):
            compare(child, retained, is_visible, child_clip, hover_visible)
        for retained in rows[len(fixed):]:
            dynamic_count += 1
            require(dynamic_count <= 4096, 'GameMenu dynamic option/mod rows exceed the bounded menu')
            compare(templates[template_name][0], retained, is_visible, child_clip, hover_visible)

    compare(original, snapshot.get('tree'))
    confirmation = {name: [node for node in nodes.values() if node.get('id') == name]
                    for name in ('ExitConfirm', 'Yes', 'No', 'Message')}
    require(all(len(rows) == 1 for rows in confirmation.values()),
            'GameMenu lost its original confirmation controls')
    confirmation = {name: rows[0] for name, rows in confirmation.items()}
    unavailable = menu.get('unavailableAction')
    require(type(menu.get('confirmationVisible')) is bool and
            menu['confirmationVisible'] is (not confirmation['ExitConfirm']['hidden']) and
            confirmation['Yes']['hidden'] is False and confirmation['No']['hidden'] is False and
            confirmation['No']['disabled'] is False and
            confirmation['Yes']['disabled'] is (unavailable is not None) and
            (not closed or menu['confirmationVisible'] is False),
            'GameMenu confirmation visibility or original Yes/No enabled state differs')
    require(unavailable is None or
            type(unavailable) is str and unavailable in expected_ids +
            ['Restart', 'Retire', 'ExitToMainMenu', 'ExitGame'] and
            menu['confirmationVisible'] is True and
            type(confirmation['Message'].get('text')) is str and
            bool(confirmation['Message']['text'].strip()),
            'GameMenu unavailable notice lacks its typed action or original visible confirmation')
    root = snapshot['tree']
    require(tuple(root.get(field) for field in ('x', 'y', 'width', 'height')) == (0, 0, 1920, 1080),
            'GameMenu viewport differs from the original selected 1920x1080 layout')
    frame_source = next(node for node in original if node.tag == 'Grid')
    frame = [node for node in nodes.values() if node.get('kind') == 'Grid' and
             node.get('sourceAttributes') == dict(frame_source.attrib)]
    require(len(frame) == 1 and tuple(frame[0].get(field) for field in ('x', 'y', 'width', 'height')) ==
            anchor(frame_source.attrib, (0, 0, 1920, 1080), *pair(frame_source.get('Size'))),
            'GameMenu central frame differs from its original XML viewport anchor')
    return_source = next(node for node in original.iter() if node.get('ID') == 'ReturnButton')
    returns = [node for node in nodes.values() if node.get('id') == 'ReturnButton']
    require(len(returns) == 1 and tuple(returns[0].get(field) for field in ('x', 'y', 'width', 'height')) ==
            anchor(return_source.attrib, tuple(frame[0][field] for field in ('x', 'y', 'width', 'height')),
                   *pair(return_source.get('Size'))),
            'GameMenu ReturnButton differs from its original frame-relative anchor')
    targets = snapshot.get('inputTargets')
    require(type(targets) is list and type(snapshot.get('scrollTargets')) is list,
            'GameMenu lacks retained input/scroll target inventories')
    confirmation_key = confirmation['ExitConfirm']['key']
    preorder = {key: index for index, key in enumerate(nodes)}
    input_allowed = {key for key in nodes if not menu['confirmationVisible'] or
                     preorder[key] >= preorder[confirmation_key]}
    seen, callback_keys, consumed_keys = set(), set(), set()
    for target in targets:
        require(type(target) is dict and type(target.get('key')) is int and
                target['key'] in nodes and target['key'] not in seen and
                target.get('id') == nodes[target['key']].get('id', '') and
                target.get('visible') is True and visible[target['key']] and
                type(target.get('disabled')) is bool and
                target['disabled'] is nodes[target['key']]['disabled'],
                'GameMenu input target is not an original visible control with its captured enabled state')
        node = nodes[target['key']]
        if target.get('event') == 'LeftClick':
            require(target['key'] in callback_sources and target['key'] in input_allowed and
                    target['disabled'] is False and
                    node.get('buttonState') in ('normal', 'hover') and
                    all(name not in target or type(target[name]) in (int, float) and
                        math.isfinite(target[name]) for name in ('void1', 'void2')) and
                    target.get('consumeMouse') is (target['key'] in consumer_sources),
                    'GameMenu callback escapes its original registration or current modal input scope')
            callback_keys.add(target['key'])
        else:
            require(target.get('event') == 'ConsumeMouse' and target.get('consumeMouse') is True and
                    target['key'] in consumer_sources and 'void1' not in target and 'void2' not in target,
                    'GameMenu consumer is not inherited from its original XML/style declaration')
        if target.get('consumeMouse'):
            consumed_keys.add(target['key'])
        require(xywh_dict(target.get('bounds'), 'GameMenu input') ==
                rect(tuple(node.get(field) for field in ('x', 'y', 'width', 'height'))) and
                xywh_dict(target.get('clippedBounds'), 'GameMenu clipped input') == clipped_bounds[target['key']] and
                positive(clipped_bounds[target['key']]),
                'GameMenu input bounds or clipping differ from their original retained control')
        seen.add(target['key'])
    expected = {key for key in callback_sources if key in input_allowed and visible[key] and
                not nodes[key]['disabled'] and positive(clipped_bounds[key])}
    expected_consumed = {key for key in consumer_sources if visible[key] and positive(clipped_bounds[key])}
    expected_order = [key for key in nodes if key in expected or key in expected_consumed]
    require((not targets and not snapshot['scrollTargets']) if closed else
            callback_keys == expected and consumed_keys == expected_consumed and
            [target['key'] for target in targets] == expected_order,
            'GameMenu dropped/reordered an original callback/consumer or retained input after closing')
    scroll_keys = [key for key, node in nodes.items() if node['kind'] == 'ScrollPanel' and
                   key in input_allowed and visible[key] and not node['disabled'] and positive(clipped_bounds[key])]
    require([target.get('key') for target in snapshot['scrollTargets'] if type(target) is dict] ==
            ([] if closed else scroll_keys) and all(type(target) is dict for target in snapshot['scrollTargets']),
            'GameMenu scroll input escapes the original current modal scope')
    return {'policy': 'ZEROSIS_ORIGINAL_GAME_MENU_PARENT_SCENE_V1', **refs,
            'owner': menu['owner'], 'turn': menu['turn'], 'closed': closed,
            'timer_semaphore': snapshot['timerSemaphore'],
            'confirmation_visible': menu['confirmationVisible'],
            'unavailable_action': unavailable,
            'confirmation_yes_disabled': confirmation['Yes']['disabled'],
            'unconnectedLuaContexts': unconnected,
            'load_menu_source_apis_bound': load_source_bound is True,
            'source_connected_children': source_children, 'dynamic_row_count': dynamic_count,
            'callback_control_ids': sorted(callback_sources.values()),
            'visible_callback_keys': sorted(callback_keys),
            'consume_mouse_keys': sorted(consumed_keys),
            'input_order_keys': [target['key'] for target in targets],
            'scroll_input_keys': [] if closed else scroll_keys,
            'modal_input_boundary_key': confirmation_key if menu['confirmationVisible'] else None,
            'modal_input_policy': 'ORIGINAL_EXIT_CONFIRM_AND_LATER_TREE_ORDER',
            'child_contexts_runtime_verified': False, 'retail_pixels_verified': False,
            'retail_timing_verified': False}

def exit_confirm_contract(snapshot, sources=None, *, closed=False):
    """Bind the separate stock exit modal, its input shield and parent timer."""
    require(type(snapshot) is dict and type(closed) is bool and
            (snapshot.get('contextName'), snapshot.get('popupKind')) == ('ExitConfirm', 'ExitConfirm') and
            snapshot.get('active') is (not closed) and snapshot.get('contextHidden') is closed and
            type(snapshot.get('timerSemaphore')) is int and snapshot['timerSemaphore'] == 0 and
            snapshot.get('lifecycle') == (['modal-pushed', 'closed', 'modal-popped'] if closed else ['modal-pushed']),
            'ExitConfirm must retain its separate original PushModal/PopModal lifecycle')
    modal = snapshot.get('exitConfirm')
    require(type(modal) is dict and modal.get('policy') == 'ORIGINAL_EXIT_CONFIRM_MODAL_V1' and
            modal.get('rawOriginalName') == 'MainMenu' and modal.get('parentContext') == 'GameMenu' and
            modal.get('modal') is True and type(modal.get('timerSemaphore')) is int and
            modal['timerSemaphore'] == 0 and type(modal.get('timerSemaphores')) is int and
            modal['timerSemaphores'] == 0 and
            modal.get('parentTimerSemaphorePolicy') == 'PRESERVE_GAME_MENU_TIMER_WHILE_MODAL_OPEN' and
            modal.get('openEvent') == 'UserRequestClose' and
            modal.get('yesPolicy') == 'ORIGINAL_POP_MODAL_THEN_UI_EXIT_GAME' and
            modal.get('cancelPolicy') == 'ORIGINAL_POP_MODAL_ON_NO_OR_ESCAPE' and
            modal.get('originalButtonVisibilityPreserved') is True and modal.get('closed') is closed and
            type(modal.get('exitSubmitted')) is bool and (closed or modal['exitSubmitted'] is False) and
            modal.get('nativeAcceptanceVerified') is False and modal.get('retailLayoutVerified') is False,
            'ExitConfirm lost its source action, cancellation, parent timer or acceptance boundary')
    refs = {}
    # These are the inspected unchanged source inputs also pinned by the asset
    # preparer. The runtime support must not import that build-only preparer.
    identities = {
        'originalLua': ('Assets/UI/FrontEnd/ExitConfirm.lua', 1929,
                        '7682db382ff5e1dc104165ba1d8a787d8e64e75fb1e550f223f2bb40ef08a5ae'),
        'originalXml': ('Assets/UI/FrontEnd/ExitConfirm.xml', 1510,
                        '6d9794963c43a2df9de43974c219fb35d9423071ec1b98c8c2a24b696d09fe32'),
    }
    for field, (relative, size, digest) in identities.items():
        ref = modal.get(field)
        require(type(ref) is dict and type(ref.get('path')) is str and
                ref['path'].replace('\\', '/').endswith('/' + relative) and
                ref.get('bytes') == size and type(ref.get('bytes')) is int and ref.get('sha256') == digest,
                'ExitConfirm source identity differs from the inspected original: ' + field)
        path = Path(ref['path']).resolve(strict=True)
        require(path.is_file() and path.stat().st_size == size and sha256(path) == digest and
                (sources is None or sources.get(path) == digest),
                'ExitConfirm original source bytes changed: ' + field)
        refs[field] = {'path': str(path), 'sha256': digest}
    styles = Path(refs['originalLua']['path']).parents[1] / 'Styles.xml'
    require(styles.is_file(), 'ExitConfirm original Styles.xml is absent')
    refs['originalStyles'] = {'path': str(styles), 'sha256': sha256(styles)}
    require(sources is None or sources.get(styles) == refs['originalStyles']['sha256'],
            'ExitConfirm styles differ from the selected source binding')
    original = ET.parse(refs['originalXml']['path']).getroot()
    nodes, ids = {}, {}
    def match(node, source):
        require(type(node) is dict and node.get('kind') == source.tag and
                node.get('sourceAttributes', node.get('attributes')) == dict(source.attrib) and
                type(node.get('attributes')) is dict and
                all(node['attributes'].get(key) == value for key, value in source.attrib.items()) and
                type(node.get('key')) is int and node['key'] > 0 and node['key'] not in nodes and
                node.get('id', '') == source.get('ID', '') and type(node.get('children')) is list and
                len(node['children']) == len(source),
                'ExitConfirm retained tree differs from its complete original XML')
        require(type(node.get('hidden')) is bool and node['hidden'] is False and
                type(node.get('disabled')) is bool and node['disabled'] is False and
                all(type(node.get(field)) in (int, float) and math.isfinite(node[field]) for field in ('x', 'y', 'width', 'height')) and
                node['width'] >= 0 and node['height'] >= 0,
                'ExitConfirm original control visibility, enabled state or bounds changed')
        nodes[node['key']] = node
        if node.get('id'):
            require(node['id'] not in ids, 'ExitConfirm has duplicate original control IDs')
            ids[node['id']] = node
        for child, child_source in zip(node['children'], source):
            match(child, child_source)
    match(snapshot.get('tree'), original)
    require(len(nodes) == modal.get('retainedControlCount') == 12 and original.tag == 'Context' and
            original.get('Name') == 'MainMenu' and set(ids) == {'ExitConfirm', 'Message', 'ButtonStack', 'Yes', 'No'} and
            ids['ExitConfirm']['kind'] == 'Box' and
            tuple(ids['ExitConfirm'][field] for field in ('x', 'y', 'width', 'height')) == (0, 0, 1920, 1080) and
            all(ids[name]['kind'] == 'GridButton' and
                (ids[name]['width'], ids[name]['height']) == (400, 42) and
                ids[name].get('buttonState') in ('normal', 'hover') for name in ('Yes', 'No')) and
            ids['Message']['kind'] == 'Label' and type(ids['Message'].get('text')) is str and
            bool(ids['Message']['text'].strip()),
            'ExitConfirm omitted its original full-screen shield, message, Yes or No controls')
    targets = snapshot.get('inputTargets')
    require(type(targets) is list and snapshot.get('scrollTargets') == [],
            'ExitConfirm must expose only its original modal consumer and Yes/No callbacks')
    expected = [] if closed else [('ExitConfirm', 'ConsumeMouse'), ('Yes', 'LeftClick'), ('No', 'LeftClick')]
    require([(target.get('id'), target.get('event')) for target in targets if type(target) is dict] == expected and
            all(type(target) is dict for target in targets),
            'ExitConfirm lost, reordered or added an original modal input target')
    for target in targets:
        node = ids[target['id']]
        require(target.get('key') == node['key'] and target.get('visible') is True and target.get('disabled') is False and
                target.get('consumeMouse') is (target['id'] == 'ExitConfirm') and
                'void1' not in target and 'void2' not in target and
                xywh_dict(target.get('bounds'), 'ExitConfirm target') ==
                    rect(tuple(node[field] for field in ('x', 'y', 'width', 'height'))) and
                xywh_dict(target.get('clippedBounds'), 'ExitConfirm clipped target') ==
                    intersect(rect(tuple(node[field] for field in ('x', 'y', 'width', 'height'))), (0, 0, 1920, 1080)),
                'ExitConfirm input escaped its original callback, geometry or full-screen consumer')
    return {'policy': 'ZEROSIS_ORIGINAL_EXIT_CONFIRM_SCENE_V1', **refs,
            'closed': closed, 'exit_submitted': modal['exitSubmitted'], 'timer_semaphore': 0,
            'parent_context': 'GameMenu', 'parent_timer_policy': modal['parentTimerSemaphorePolicy'],
            'original_name': 'MainMenu', 'full_original_tree_matched': True, 'retained_control_count': len(nodes),
            'callback_control_ids': ['No', 'Yes'], 'input_order_keys': [target['key'] for target in targets],
            'consume_mouse_keys': [] if closed else [ids['ExitConfirm']['key']],
            'scroll_input_keys': [], 'native_acceptance_verified': False, 'retail_pixels_verified': False}


def action_info_panel_contract(snapshot, sources=None):
    """Validate only the original, timer-free action panel and its two callbacks."""
    require(type(snapshot) is dict and snapshot.get('contextName') == 'ActionInfoPanel' and
            snapshot.get('popupKind') == 'ActionInfoPanel' and snapshot.get('active') is True and
            snapshot.get('nonmodal') is True and type(snapshot.get('timerSemaphore')) is int and
            snapshot['timerSemaphore'] == 0 and snapshot.get('lifecycle') == ['queued'],
            'ActionInfoPanel is not the active original nonmodal world overlay')
    panel = snapshot.get('actionInfoPanel')
    declaration = {'kind': 'LuaContext', 'attributes': {
        'FileName': 'Assets/UI/InGame/WorldView/NotificationPanel', 'ID': 'NotificationPanel'}, 'children': []}
    require(type(panel) is dict and panel.get('notificationPanelIntegrated') is False and
            panel.get('unconnectedLuaContexts') == [declaration],
            'ActionInfoPanel must expose its original NotificationPanel declaration as unconnected')
    refs = {}
    for name, extension in (('originalLua', 'lua'), ('originalXml', 'xml')):
        row = panel.get(name)
        relative = 'Assets/DLC/Expansion2/UI/InGame/WorldView/ActionInfoPanel.' + extension
        require(type(row) is dict and type(row.get('path')) is str and
                type(row.get('sha256')) is str and re.fullmatch(r'[0-9a-f]{64}', row['sha256']) and
                row['path'].replace('\\', '/').endswith('/' + relative),
                'ActionInfoPanel source provenance does not identify the original BNW asset')
        path = Path(row['path']).resolve(strict=True)
        require(path.is_file() and sha256(path) == row['sha256'] and
                (sources is None or sources.get(path) == row['sha256']),
                'ActionInfoPanel original source path/hash differs from the selected game')
        refs[name] = {'path': str(path), 'sha256': row['sha256']}
    original = ET.parse(refs['originalXml']['path']).getroot()
    embedded = list(original.iter('LuaContext'))
    require(len(embedded) == 1 and embedded[0] in list(original) and
            dict(embedded[0].attrib) == declaration['attributes'] and len(embedded[0]) == 0,
            'Original ActionInfoPanel has an unexpected embedded context declaration')
    original.remove(embedded[0])
    controls = []
    def compare(source, node):
        require(type(node) is dict and node.get('kind') == source.tag and
                node.get('sourceAttributes') == dict(source.attrib) and
                node.get('id', '') == source.attrib.get('ID', '') and
                type(node.get('children')) is list and len(node['children']) == len(source),
                'ActionInfoPanel retained tree differs from the complete original action controls')
        controls.append(node)
        for child, retained in zip(source, node['children']):
            compare(child, retained)
    compare(original, snapshot.get('tree'))
    button = [node for node in controls if node.get('id') == 'EndTurnButton']
    label = [node for node in controls if node.get('id') == 'EndTurnText']
    require(len(button) == len(label) == 1 and button[0].get('kind') == 'GridButton' and
            label[0].get('kind') == 'Label', 'ActionInfoPanel lost its original EndTurnButton/Text')
    button, label = button[0], label[0]
    bounds = (1584, 844, 320, 36)  # Original R,B / 16,200 / 320,36 at 1920x1080.
    require(tuple(button.get(name) for name in ('x', 'y', 'width', 'height')) == bounds and
            button.get('hidden') is False and type(button.get('disabled')) is bool and
            type(label.get('text')) is str and bool(label['text']) and
            snapshot.get('scrollTargets') == [],
            'ActionInfoPanel source-anchored button, caption, or no-scroll contract differs')
    targets = snapshot.get('inputTargets')
    events = [] if button['disabled'] else ['LeftClick', 'RightClick']
    require(type(targets) is list and len(targets) == len(events) and
            sorted(row.get('event', '') for row in targets if type(row) is dict) == events and
            all(type(row) is dict and row.get('key') == button['key'] and
                row.get('id') == 'EndTurnButton' and row.get('visible') is True and
                row.get('disabled') is False and all(
                    type(row.get(field)) is dict and
                    tuple(row[field].get(name) for name in ('x', 'y', 'width', 'height')) == bounds
                    for field in ('bounds', 'clippedBounds')) for row in targets),
            'ActionInfoPanel callbacks must be the original EndTurnButton left/right pair or disabled')
    return {'policy': 'ZEROSIS_ORIGINAL_ACTION_INFO_PANEL_OVER_LIVE_WORLD_V1', **refs,
            'notificationPanelIntegrated': False, 'unconnectedLuaContexts': [declaration],
            'nonmodal': True, 'timer_semaphore': 0, 'end_turn_button_key': button['key'],
            'end_turn_bounds': list(bounds), 'end_turn_text': label['text'],
            'button_disabled': button['disabled'], 'callback_events': events,
            'retail_pixels_verified': False, 'retail_timing_verified': False,
            'full_notification_workflow_verified': False}


def notification_panel_contract(snapshot, sources=None):
    """Bind the nonmodal notification overlay to its original inputs and live SDK rows."""
    require(type(snapshot) is dict and
            (snapshot.get('contextName'), snapshot.get('popupKind')) ==
            ('NotificationPanel', 'NotificationPanel') and snapshot.get('active') is True and
            snapshot.get('nonmodal') is True and snapshot.get('timerSemaphore') == 0 and
            snapshot.get('lifecycle') == ['queued'],
            'NotificationPanel is not the active original timer-free world overlay')
    panel = snapshot.get('notificationPanel')
    require(type(panel) is dict and panel.get('allNotificationDestinationsIntegrated') is False and
            type(panel.get('owner')) is int and panel['owner'] >= 0 and
            type(panel.get('turn')) is int and panel['turn'] >= 0 and
            type(panel.get('notifications')) is list,
            'NotificationPanel SDK notification inventory or explicit destination boundary is malformed')
    refs = {}
    suffixes = {'originalLua': 'Assets/DLC/Expansion2/UI/InGame/WorldView/NotificationPanel.lua',
                'originalXml': 'Assets/DLC/Expansion2/UI/InGame/WorldView/NotificationPanel.xml'}
    for name, relative in suffixes.items():
        row = panel.get(name)
        require(type(row) is dict and type(row.get('path')) is str and
                re.fullmatch(r'[0-9a-f]{64}', row.get('sha256', '')) is not None and
                ('bytes' not in row or type(row.get('bytes')) is int and row['bytes'] > 0) and
                row['path'].replace('\\', '/').endswith('/' + relative),
                'NotificationPanel provenance does not identify its exact original BNW asset')
        path = Path(row['path']).resolve(strict=True)
        require(path.is_file() and ('bytes' not in row or path.stat().st_size == row['bytes']) and
                sha256(path) == row['sha256'] and
                (sources is None or sources.get(path) == row['sha256']),
                'NotificationPanel source bytes/hash differ from the installed original')
        refs[name] = {'path': str(path), 'sha256': row['sha256']}
        if 'bytes' in row:
            refs[name]['bytes'] = row['bytes']

    rows = panel['notifications']
    ids = []
    for row in rows:
        require(type(row) is dict and
                all(field in row for field in ('id', 'type', 'tooltip', 'summary', 'gameData',
                                               'extraGameData', 'player', 'x', 'y')) and
                type(row.get('id')) is int and row['id'] >= 0 and
                type(row.get('type')) is int and type(row.get('tooltip')) is str and
                type(row.get('summary')) is str and
                all(type(row.get(field)) is int for field in ('gameData', 'extraGameData', 'player', 'x', 'y')),
                'NotificationPanel contains a malformed original SDK notification row')
        ids.append(row['id'])
    require(len(ids) == len(set(ids)), 'NotificationPanel SDK notification IDs are duplicated')

    root = ET.parse(refs['originalXml']['path']).getroot()
    require(root.tag == 'Context', 'Original NotificationPanel XML has no Context root')
    templates = {element.attrib.get('Name'): element for element in root.findall('Instance')}
    require(len(templates) == len(root.findall('Instance')) and len(templates) == 70 and
            '' in templates and 'GenericItem' in templates,
            'Original NotificationPanel template inventory differs from the frozen 70-template layout')
    script_text = Path(refs['originalLua']['path']).read_text(encoding='utf-8-sig')
    fixed_events = {}
    for match in re.finditer(
            r'Controls\["([^"]+)"\]:RegisterCallback\(Mouse\.(eLClick|eRClick),\s*Generic(Left|Right)Click\);',
            script_text):
        control_id, event_name, callback_side = match.groups()
        require((event_name, callback_side) in (('eLClick', 'Left'), ('eRClick', 'Right')),
                'NotificationPanel fixed callback event is routed to the wrong original handler')
        fixed_events.setdefault(control_id, set()).add('LeftClick' if event_name == 'eLClick' else 'RightClick')
    require(script_text.count('button:RegisterCallback( Mouse.eLClick, GenericLeftClick );') == 1 and
            script_text.count('button:RegisterCallback( Mouse.eRClick, GenericRightClick );') == 1,
            'Original NotificationPanel dynamic instances no longer register the left/right SDK callbacks')
    template_button_ids = {element.attrib.get('ID') for template in templates.values()
                           for element in template.iter('Button') if element.attrib.get('ID')}
    tree = snapshot.get('tree')
    styles_path = (Path(refs['originalXml']['path']).parents[6] / 'Assets/UI/Styles.xml').resolve()
    styles_hash = sha256(styles_path)
    style_source = snapshot.get('styleDefaultsSource')
    style_defaults = snapshot.get('styleDefaults')
    require(type(style_source) is dict and style_source.get('path') == 'Assets/UI/Styles.xml' and
            style_source.get('sha256') == styles_hash and type(style_defaults) is dict,
            'NotificationPanel retained style defaults are not bound to the installed Styles.xml')
    style_xml = ET.parse(styles_path).getroot()

    def source_signature(node):
        attrs = node.get('sourceAttributes')
        require(type(attrs) is dict, 'NotificationPanel retained control lost original source attributes')
        return node.get('kind'), json.dumps(attrs, sort_keys=True, separators=(',', ':'))

    def match(actual, original, *, allow_instance_rows=False):
        expected_id = original.attrib.get('ID', '')
        style_name = original.attrib.get('Style')
        if (not expected_id and original.tag == 'AlphaAnim' and
                style_name in ('NewFinger', 'NewFingerRed')):
            # The stock XML omits AlphaAnim.ID; InstanceManager exposes the ID
            # declared by the exact NewFinger style so the original Lua can
            # address instance.FingerRoot. Keep sourceAttributes untouched.
            style_element = style_xml.find(style_name)
            style_row = style_defaults.get(style_name)
            require(style_element is not None and type(style_row) is dict and
                    type(style_row.get('attributes')) is dict and
                    style_row['attributes'].get('ID') == style_element.attrib.get('ID'),
                    'NotificationPanel NewFinger ID is not derived from the frozen Styles.xml row')
            expected_id = style_element.attrib.get('ID', '')
        require(type(actual) is dict and source_signature(actual) ==
                (original.tag, json.dumps(dict(original.attrib), sort_keys=True, separators=(',', ':'))) and
                actual.get('id', '') == expected_id and
                actual.get('attributes', {}).get('ID', '') == expected_id,
                'NotificationPanel retained control differs from its exact original XML node')
        actual_children = actual.get('children')
        require(type(actual_children) is list, 'NotificationPanel retained control has malformed children')
        if allow_instance_rows:
            actual_children = [child for child in actual_children
                               if not child.get('instanceTemplate') and not child.get('styleChildSource')]
        source_children = [child for child in list(original) if child.tag != 'Instance']
        require(len(actual_children) == len(source_children),
                'NotificationPanel retained original subtree has missing or extra controls')
        for child, source_child in zip(actual_children, source_children):
            match(child, source_child, allow_instance_rows=allow_instance_rows)

    def verify_generated(actual, name):
        source = templates.get(name)
        require(source is not None and type(actual) is dict,
                'NotificationPanel generated row names an unknown original Instance template')
        source_roots = [child for child in list(source)]
        require(len(source_roots) == 1, 'Original NotificationPanel instance is not a single root control')
        match(actual, source_roots[0], allow_instance_rows=True)
        for child in actual.get('children', []):
            if child.get('instanceTemplate'):
                verify_generated(child, child['instanceTemplate'])

    require(type(tree) is dict, 'NotificationPanel snapshot has no retained original tree')
    match(tree, root, allow_instance_rows=True)
    dynamic = []
    def collect_dynamic(node):
        if node.get('instanceTemplate'):
            dynamic.append(node)
            verify_generated(node, node['instanceTemplate'])
        for child in node.get('children', []):
            collect_dynamic(child)
    collect_dynamic(tree)
    require(len(dynamic) <= len(rows),
            'NotificationPanel retained generated instance count exceeds the live SDK notification inventory')

    nodes_by_key = {node.get('key'): node for node in _notification_walk(tree)}
    for node in nodes_by_key.values():
        style_source = node.get('styleChildSource')
        if style_source is None:
            continue
        require(type(style_source) is dict and
                set(style_source) == {'style', 'ownerKey', 'path', 'sha256', 'indices'} and
                style_source.get('style') in ('NewFinger', 'NewFingerRed') and
                style_source.get('path') == 'Assets/UI/Styles.xml' and
                style_source.get('sha256') == styles_hash and
                type(style_source.get('indices')) is list and style_source['indices'] and
                all(type(index) is int and index >= 1 for index in style_source['indices']),
                'NotificationPanel style-generated control lacks its exact Styles.xml provenance')
        owner = nodes_by_key.get(style_source['ownerKey'])
        require(type(owner) is dict and owner.get('kind') == 'AlphaAnim' and
                owner.get('attributes', {}).get('Style') == style_source['style'],
                'NotificationPanel generated style child is detached from its original NewFinger owner')
        style_root = style_xml.find(style_source['style'])
        source_node = style_root
        for index in style_source['indices']:
            children = list(source_node) if source_node is not None else []
            require(index <= len(children), 'NotificationPanel Styles.xml child path escapes its source style')
            source_node = children[index - 1]
        require(source_node is not None and node.get('kind') == source_node.tag and
                node.get('sourceAttributes') == dict(source_node.attrib),
                'NotificationPanel generated style child differs from its exact source subtree node')

    targets = snapshot.get('inputTargets')
    require(type(targets) is list and all(type(target) is dict for target in targets),
            'NotificationPanel callback target list is malformed')
    by_notification = {}
    notification_buttons = {}
    consumer_targets = {}
    nodes_by_key = {node.get('key'): node for node in _notification_walk(tree)}
    for target in targets:
        require(type(target.get('key')) is int and target['key'] > 0 and
                type(target.get('id')) is str and target.get('id') and
                target.get('visible') is True and type(target.get('disabled')) is bool and
                type(target.get('bounds')) is dict and type(target.get('clippedBounds')) is dict,
                'NotificationPanel input target does not preserve its original key or geometry')
        if target.get('event') == 'ConsumeMouse':
            node = nodes_by_key.get(target['key'])
            require(target.get('consumeMouse') is True and 'void1' not in target and 'void2' not in target and
                    type(node) is dict and node.get('kind') == 'Container' and
                    node.get('id') == target['id'] and
                    node.get('sourceAttributes', {}).get('ConsumeMouseButton') == '1' and
                    target['key'] not in consumer_targets,
                    'NotificationPanel mouse consumer is not an exact original Container source target')
            consumer_targets[target['key']] = target
            continue
        require(target.get('event') in ('LeftClick', 'RightClick') and
                type(target.get('void1')) is int and target.get('disabled') is False,
                'NotificationPanel callback target does not preserve its original event/payload')
        allowed = fixed_events.get(target['id'])
        if allowed is None:
            require(target['id'] in template_button_ids and
                    target['event'] in ('LeftClick', 'RightClick'),
                    'NotificationPanel callback target is not registered by original Lua or an original row template')
        else:
            require(target['event'] in allowed,
                    'NotificationPanel fixed callback target has an unregistered mouse event')
        by_notification.setdefault(target['void1'], set()).add(target['event'])
        notification_buttons.setdefault(target['void1'], set()).add(target['id'])
    scroll_panels = [node for node in nodes_by_key.values()
                     if node.get('id') == 'SmallScrollPanel' and node.get('kind') == 'ScrollPanel']
    fixed_rows = {}
    dynamic_rows = []
    for row in rows:
        control_name = FIXED_NOTIFICATION_CONTROL_TYPES.get(row['type'] & 0xffffffff)
        if control_name is None:
            dynamic_rows.append(row)
        else:
            fixed_rows.setdefault(control_name, []).append(row)
    stock_fixed_names = set(re.findall(r'name\s*==\s*"([^"]+)"', re.search(
        r'if\s*\(\s*name\s*==\s*"Production"(.*?)\)\s*then', script_text, re.S).group(0)))
    require(set(FIXED_NOTIFICATION_CONTROL_TYPES.values()) <= stock_fixed_names and
            len(dynamic) == len(dynamic_rows) and len(scroll_panels) == 1,
            'NotificationPanel original notification rows or scroll viewport are incomplete')
    parent_by_key = {}
    def index_parents(node, parent=None):
        if type(node.get('key')) is int:
            parent_by_key[node['key']] = parent
            parent = node['key']
        for child in node.get('children', []):
            index_parents(child, parent)
    index_parents(tree)
    expected_consumers = set()
    scroll = scroll_panels[0]
    vx, vy, vw, vh = (scroll.get(field) for field in ('x', 'y', 'width', 'height'))
    require(all(type(value) in (int, float) for value in (vx, vy, vw, vh)) and vw > 0 and vh > 0,
            'NotificationPanel original scroll viewport has invalid geometry')
    # Fixed controls are shared by notification type in the stock Lua. Each
    # Add overwrites that button's void1, and removing any one member hides the
    # shared button even if other SDK rows of that type remain.
    fixed_buttons = {}
    for control_name, class_rows in fixed_rows.items():
        control_id = control_name + 'Button'
        candidates = [node for node in nodes_by_key.values()
                      if node.get('id') == control_id and node.get('kind') == 'Button']
        require(len(candidates) == 1 and control_id in fixed_events,
                'NotificationPanel fixed SDK notification has no unique original callback control')
        button = candidates[0]
        fixed_buttons[control_name] = button
        x, y, width, height = (button.get(field) for field in ('x', 'y', 'width', 'height'))
        require(all(type(value) in (int, float) for value in (x, y, width, height)) and
                width > 0 and height > 0,
                'Original fixed notification button has invalid source geometry')
        button_targets = [target for target in targets if target.get('key') == button.get('key') and
                          target.get('event') in ('LeftClick', 'RightClick')]
        if button.get('hidden') is True:
            require(not button_targets and all(row['id'] not in by_notification for row in class_rows),
                    'Hidden original fixed notification control still exposes a callback')
            continue
        require(button.get('hidden') is False and button_targets and
                {target.get('event') for target in button_targets} == fixed_events[control_id] and
                len(button_targets) == len(fixed_events[control_id]) and
                len({target.get('void1') for target in button_targets}) == 1 and
                all(target.get('bounds') == {'x': x, 'y': y, 'width': width, 'height': height}
                    for target in button_targets),
                'Visible original fixed notification control lost its registered callbacks')
        active_id = button_targets[0]['void1']
        require(active_id in {row['id'] for row in class_rows} and
                all(target.get('id') == control_id for target in button_targets),
                'Shared original fixed notification control does not retain an active SDK ID of its type')
        for target in button_targets:
            by_notification.setdefault(active_id, set()).add(target['event'])
            notification_buttons.setdefault(active_id, set()).add(control_id)
    allowed_fixed_controls = {name + 'Button' for name in fixed_rows}
    require(all(target.get('event') == 'ConsumeMouse' or target.get('id') not in fixed_events or
                target.get('id') in allowed_fixed_controls for target in targets),
            'NotificationPanel exposes a fixed callback for a notification type absent from the SDK inventory')

    dynamic_ids = {row['id'] for row in dynamic_rows}
    mapped_dynamic_ids = set()
    unbound_dynamic_instance_count = 0
    for instance_node in dynamic:
        template_name = instance_node.get('instanceTemplate')
        template_button_ids_for_row = {element.attrib.get('ID') for element in templates[template_name].iter('Button')
                                       if element.attrib.get('ID')}
        buttons = [node for node in _notification_walk(instance_node)
                   if node.get('kind') == 'Button' and node.get('id') in template_button_ids_for_row]
        require(len(buttons) == 1,
                'Original notification instance does not retain exactly one registered SDK button')
        button = buttons[0]
        x, y, width, height = (button.get(field) for field in ('x', 'y', 'width', 'height'))
        require(all(type(value) in (int, float) for value in (x, y, width, height)) and width > 0 and height > 0,
                'NotificationPanel original row button has invalid geometry')
        clipped = (max(x, vx), max(y, vy), min(x + width, vx + vw), min(y + height, vy + vh))
        is_visible = clipped[2] > clipped[0] and clipped[3] > clipped[1]
        button_targets = [target for target in targets if target.get('key') == button.get('key') and
                          target.get('event') in ('LeftClick', 'RightClick')]
        expected_events = {'LeftClick', 'RightClick'} if is_visible else set()
        target_ids = {target.get('void1') for target in button_targets}
        require(len(button_targets) == len(expected_events) and
                {target.get('event') for target in button_targets} == expected_events and
                (not is_visible or len(target_ids) == 1 and target_ids <= dynamic_ids) and
                (not is_visible or not (target_ids & mapped_dynamic_ids)) and
                all(target.get('key') == button.get('key') for target in button_targets),
                'NotificationPanel callback targets do not match visible original SDK notification rows')
        if is_visible:
            notification_id = next(iter(target_ids))
            require(by_notification.get(notification_id) == expected_events and
                    notification_buttons.get(notification_id) == {button.get('id')},
                    'NotificationPanel callback targets do not match their visible original instance button')
            mapped_dynamic_ids.add(notification_id)
            ancestor = parent_by_key.get(button.get('key'))
            while ancestor is not None and not (
                    nodes_by_key[ancestor].get('kind') == 'Container' and
                    nodes_by_key[ancestor].get('sourceAttributes', {}).get('ConsumeMouseButton') == '1'):
                ancestor = parent_by_key.get(ancestor)
            require(ancestor is not None and ancestor in consumer_targets,
                    'Visible NotificationPanel row lacks its original mouse-consuming Container')
            consumer = consumer_targets[ancestor]
            require(consumer.get('id') == nodes_by_key[ancestor].get('id') and
                    consumer.get('clippedBounds') == {
                        'x': clipped[0], 'y': clipped[1],
                        'width': clipped[2] - clipped[0], 'height': clipped[3] - clipped[1]},
                    'NotificationPanel mouse consumer differs from its visible row bounds')
            expected_consumers.add(ancestor)
        else:
            unbound_dynamic_instance_count += 1
            require(not button_targets, 'Fully clipped NotificationPanel row retained clickable callbacks')
    fixed_active_ids = {notification_id for notification_id, button_ids in notification_buttons.items()
                        if button_ids and next(iter(button_ids)) in fixed_events}
    require(set(by_notification).issubset(set(ids)) and
            set(by_notification) == fixed_active_ids | mapped_dynamic_ids and
            set(consumer_targets) == expected_consumers,
            'NotificationPanel callbacks or source mouse consumers escape visible SDK rows')
    for notification_id, events in by_notification.items():
        button_ids = notification_buttons[notification_id]
        require(len(button_ids) == 1, 'One original notification is split across multiple button controls')
        button_id = next(iter(button_ids))
        expected_events = fixed_events.get(button_id, {'LeftClick', 'RightClick'})
        require(events == expected_events,
                'NotificationPanel event set differs from the exact original fixed/dynamic button callbacks')
    require(type(snapshot.get('scrollTargets')) is list,
            'NotificationPanel snapshot lacks its original ScrollPanel target list')
    return {'policy': 'ZEROSIS_ORIGINAL_NOTIFICATION_PANEL_OVER_LIVE_WORLD_V1', **refs,
            'owner': panel['owner'], 'turn': panel['turn'],
            'notification_ids': ids, 'notification_count': len(rows),
            'template_count': len(templates),
            'template_names': sorted(templates), 'dynamic_instance_count': len(dynamic),
            'fixed_notification_controls': sorted(fixed_buttons),
            'dynamic_instances_without_visible_id_binding': unbound_dynamic_instance_count,
            'dynamic_id_binding_scope': 'visible callback keys only; clipped instance identities are not individually observable',
            'visible_input_target_count': len(targets),
            'zero_hit_regions_are_originally_valid': not targets,
            'callback_events_per_notification': {str(key): sorted(value) for key, value in sorted(by_notification.items())},
            'consumer_target_keys': sorted(consumer_targets),
            'all_notification_destinations_integrated': False,
            'scroll_target_ids': sorted(target.get('id', '') for target in snapshot['scrollTargets']),
            'nonmodal': True, 'timer_semaphore': 0,
            'retail_pixels_verified': False, 'retail_animation_timing_verified': False}


def _notification_walk(node):
    yield node
    for child in node.get('children', []):
        yield from _notification_walk(child)


def notification_slide_transform(style_attrs, animation, snapshot_clock):
    """Validate the original root-eased slide clock; retained XY already includes the offset."""
    require(type(style_attrs) is dict and style_attrs.get('Function') == 'Root',
            'NotificationPanel slide is not the original Root transform')
    start, end = pair(style_attrs.get('Start', '')), pair(style_attrs.get('End', ''))
    speed, power = float(style_attrs.get('Speed', '0')), float(style_attrs.get('FunctionPower', '1'))
    require(speed > 0 and math.isfinite(speed) and power > 0 and math.isfinite(power) and
            type(animation) is dict and animation.get('clock') == snapshot_clock and
            type(animation.get('elapsed')) in (int, float) and math.isfinite(animation['elapsed']) and
            animation['elapsed'] >= 0 and type(animation.get('running')) is bool and
            animation.get('timingPolicy') == 'CIV5_NOTIFICATION_SLIDE_ROOT_CANDIDATE_V1' and
            animation.get('geometryPolicy') == 'CIV5_NOTIFICATION_SLIDE_PARENT_FRAME_CANDIDATE_V1' and
            animation.get('retailTimingVerified') is False and
            animation.get('retailGeometryVerified') is False,
            'Original NotificationPanel SlideAnim lacks its captured parent-frame timeline')
    phase = min(1.0, animation['elapsed'] / speed)
    require(type(animation.get('phase')) in (int, float) and math.isfinite(animation['phase']) and
            abs(animation['phase'] - phase) <= 1e-6,
            'NotificationPanel SlideAnim phase differs from source elapsed time')
    offset = tuple(a + (b - a) * phase ** power for a, b in zip(start, end))
    require(all(type(animation.get(name)) in (int, float) and math.isfinite(animation[name]) and
                abs(animation[name] - value) <= 1e-6
                for name, value in zip(('offsetX', 'offsetY'), offset)),
            'NotificationPanel SlideAnim transform differs from original Start/End/Root timing')
    return phase, offset


def notification_one_bounce_alpha(style_attrs, animation, snapshot_clock):
    """Validate the explicit one-second/default-speed frontend candidate for stock finger styles."""
    require(type(style_attrs) is dict and style_attrs.get('Cycle') == 'OneBounce' and
            style_attrs.get('AlphaStart') == '0' and style_attrs.get('AlphaEnd') == '1' and
            style_attrs.get('EndPause') == '5' and type(animation) is dict and
            animation.get('clock') == snapshot_clock and
            type(animation.get('elapsed')) in (int, float) and math.isfinite(animation['elapsed']) and
            animation['elapsed'] >= 0 and animation.get('defaultSpeedUsed') is True and
            animation.get('effectiveSpeed') == 1 and
            animation.get('timingPolicy') == 'CIV5_NOTIFICATION_ONE_BOUNCE_CANDIDATE_V1' and
            animation.get('retailTimingVerified') is False,
            'NotificationPanel NewFinger style lacks its explicit source-default OneBounce candidate')
    elapsed = animation['elapsed']
    expected_alpha = (min(1.0, elapsed) if elapsed < 1 else
                      1.0 if elapsed < 6 else max(0.0, 7.0 - elapsed) if elapsed < 7 else 0.0)
    require(type(animation.get('alpha')) in (int, float) and math.isfinite(animation['alpha']) and
            abs(animation['alpha'] - expected_alpha) <= 1e-6,
            'NotificationPanel NewFinger alpha differs from its captured OneBounce candidate phase')
    return expected_alpha


ECONOMIC_KEY_SPAN = 1 << 48
ECONOMIC_SPECS = {
    'parent': ('EconomicOverview', 'EconomicOverview', 'EconomicOverviewLayout', 0),
    'EconomicGeneralInfo': ('EconomicGeneralInfo', 'EconomicGeneral', 'EconomicGeneralLayout', ECONOMIC_KEY_SPAN),
    'HappinessInfo': ('HappinessInfo', 'EconomicHappiness', 'EconomicHappinessLayout', ECONOMIC_KEY_SPAN * 2),
}


def economic_walk(tree):
    require(type(tree) is dict and type(tree.get('children')) is list and
            type(tree.get('attributes')) is dict, 'EconomicOverview has a malformed retained tree')
    yield tree
    for child in tree['children']:
        yield from economic_walk(child)


def economic_tree_inventory(tree):
    nodes = list(economic_walk(tree))
    return {'control_ids': sorted(n['attributes']['ID'] for n in nodes if n['attributes'].get('ID')),
            'retained_control_count': len(nodes),
            'templates': sorted(({
                'name': node['attributes'].get('Name'),
                'control_ids': sorted(n['attributes']['ID'] for n in economic_walk(node)
                                      if n['attributes'].get('ID')),
                'retained_control_count': len(list(economic_walk(node))),
            } for node in nodes if node['kind'] == 'Instance'), key=lambda row: row['name'])}


def economic_source_ref(row):
    require(type(row) is dict and type(row.get('path')) is str and
            re.fullmatch(r'[0-9a-f]{64}', row.get('sha256', '')) is not None,
            'EconomicOverview original source lacks a sealed path/hash')
    return {name: row[name] for name in ('path', 'sha256')}


def validate_economic_overview_prepared(prepared, *, verify_files=False):
    """Bind exactly three complete original XML trees to frozen Lua/XML inputs."""
    require(type(prepared) is dict, 'EconomicOverview requires frozen prepared.json provenance')
    proof, trees = prepared.get('economic_overview'), prepared.get('xml_control_trees')
    require(type(proof) is dict and type(trees) is dict and
            set(proof.get('children', {})) == {'EconomicGeneralInfo', 'HappinessInfo'} and
            proof.get('sourceBytesPreserved') is True and
            proof.get('treeNames') == [value[2] for value in ECONOMIC_SPECS.values()],
            'EconomicOverview prepared source proof has missing or extra child contexts')
    require(proof.get('xmlContexts') == [
        {'id': 'EconomicGeneralInfo', 'fileName': 'Assets/UI/InGame/Popups/EconomicGeneralInfo', 'hidden': '0'},
        {'id': 'HappinessInfo', 'fileName': 'Assets/UI/InGame/Popups/HappinessInfo', 'hidden': '1'}],
        'EconomicOverview prepared proof changed the exact original LuaContext declarations')
    for slot, (name, kind, layout, _) in ECONOMIC_SPECS.items():
        row = proof.get('parent') if slot == 'parent' else proof['children'][slot]
        tree = trees.get(layout)
        require(type(row) is dict and type(tree) is dict and
                (row.get('contextName'), row.get('popupKind'), row.get('layoutAsset'), row.get('luaAsset')) ==
                (name, kind, layout, name) and
                (tree.get('contextName'), tree.get('popupKind'), tree.get('kind')) == (name, kind, 'Context'),
                'EconomicOverview prepared context identity differs from the original asset')
        if slot != 'parent':
            require(row.get('controlId') == slot and row.get('visibility') ==
                    ('visible' if slot == 'EconomicGeneralInfo' else 'hidden'),
                    'EconomicOverview prepared child slot or original visibility differs')
        inventory = economic_tree_inventory(tree)
        require(all(row.get(field) == value for field, value in inventory.items()),
                'EconomicOverview prepared inventory omits original controls or row templates')
        for field, extension in (('lua', '.lua'), ('xml', '.xml')):
            ref = economic_source_ref(row.get(field))
            prefix = ('Assets/UI/InGame/Popups/' if slot == 'parent' and field == 'lua'
                      else 'Assets/DLC/Expansion2/UI/InGame/Popups/')
            require(ref['path'].replace('\\', '/').endswith('/' + prefix + name + extension),
                    'EconomicOverview provenance refers to a substituted original source')
            if verify_files:
                path = Path(ref['path'])
                require(path.is_file() and sha256(path) == ref['sha256'],
                        'EconomicOverview original Lua/XML source hash changed')
                if field == 'xml':
                    def raw(element):
                        return {'kind': element.tag, 'attributes': dict(element.attrib),
                                'children': [raw(child) for child in element]}
                    def structural(node):
                        return {'kind': node['kind'], 'attributes': node['attributes'],
                                'children': [structural(child) for child in node['children']]}
                    require(structural(tree) == raw(ET.parse(path).getroot()),
                            'EconomicOverview prepared tree differs from complete original XML')
    parent = trees['EconomicOverviewLayout']
    contexts = [node for node in economic_walk(parent) if node['kind'] == 'LuaContext']
    require(len(contexts) == 2 and sorted([
        {'id': n['attributes'].get('ID'), 'fileName': n['attributes'].get('FileName'),
         'hidden': n['attributes'].get('Hidden')} for n in contexts], key=lambda n: n['id']) == proof['xmlContexts'],
        'EconomicOverview frozen parent tree contains unsupported embedded LuaContexts')
    return proof


def _economic_retained_tree(tree, source):
    """Check every static control and every complete source-generated instance."""
    def signature(node, captured=False):
        attrs = node.get('sourceAttributes') if captured else node['attributes']
        require(type(attrs) is dict, 'EconomicOverview control lost its original sourceAttributes')
        return node.get('kind'), json.dumps(attrs, sort_keys=True)
    templates = [child for node in economic_walk(source) if node['kind'] == 'Instance'
                 for child in node['children']]
    def match(actual, original):
        require(signature(actual, True) == signature(original),
                'EconomicOverview original control kind/attributes were omitted or replaced')
        require(actual.get('id', '') == original['attributes'].get('ID', ''),
                'EconomicOverview original control ID changed')
        expected = [child for child in original['children'] if child['kind'] != 'Instance']
        pending = iter(expected)
        next_original = next(pending, None)
        for child in actual['children']:
            if next_original is not None and signature(child, True) == signature(next_original):
                match(child, next_original)
                next_original = next(pending, None)
            else:
                candidates = [template for template in templates if signature(child, True) == signature(template)]
                require(len(candidates) == 1, 'EconomicOverview retained an unknown or incomplete row instance')
                match(child, candidates[0])
        require(next_original is None, 'EconomicOverview omitted an original static child control')
    match(tree, source)


def compose_economic_overview_snapshot(snapshot, prepared):
    """Rebase only the two sealed child VMs; never authorize arbitrary LuaContexts."""
    proof = validate_economic_overview_prepared(prepared)
    require(type(snapshot) is dict and (snapshot.get('contextName'), snapshot.get('popupKind')) ==
            ('EconomicOverview', 'EconomicOverview') and type(snapshot.get('active')) is bool and
            type(snapshot.get('timerSemaphore')) is int and
            snapshot['timerSemaphore'] == int(snapshot['active']),
            'EconomicOverview parent context/timer does not match its original modal state')
    entries = snapshot.get('embeddedContexts')
    require(type(entries) is list and len(entries) == 2 and all(type(row) is dict for row in entries) and
            sorted(row.get('controlId', '') for row in entries) == ['EconomicGeneralInfo', 'HappinessInfo'],
            'EconomicOverview requires exactly its two unique original child slots')
    result = copy.deepcopy(snapshot)
    merged_fonts = result.get('fontMetrics')
    require(type(merged_fonts) is dict and type(merged_fonts.get('fonts')) is dict,
            'EconomicOverview parent lacks captured font metrics')
    source_contract, slot_proofs = {}, []
    trees = prepared['xml_control_trees']
    def validate_vm(vm, slot):
        name, kind, layout, base = ECONOMIC_SPECS[slot]
        row = proof['parent'] if slot == 'parent' else proof['children'][slot]
        role = {'parent': 'parent', 'EconomicGeneralInfo': 'general', 'HappinessInfo': 'happiness'}[slot]
        meta = vm.get('economicOverview')
        require(type(meta) is dict and meta.get('role') == role and
                (vm.get('contextName'), vm.get('popupKind')) == (name, kind),
                'EconomicOverview child role/context differs from its original VM')
        refs = {'originalLua': economic_source_ref(row['lua']), 'originalXml': economic_source_ref(row['xml'])}
        require(all(economic_source_ref(meta.get(field)) == ref for field, ref in refs.items()),
                'EconomicOverview snapshot refers to unsealed child Lua/XML sources')
        source_contract[slot] = refs
        nodes = list(economic_walk(vm.get('tree')))
        keys = [node.get('key') for node in nodes]
        require(all(type(key) is int and 0 < key < ECONOMIC_KEY_SPAN for key in keys) and
                len(keys) == len(set(keys)) and all(type(node.get('hidden')) is bool for node in nodes),
                'EconomicOverview VM has duplicate, pre-rebased or invalid control keys')
        require(vm['tree']['kind'] == 'Context' and
                tuple(vm['tree'].get(field) for field in ('x', 'y', 'width', 'height')) == (0, 0, 1920, 1080),
                'EconomicOverview child Context lost its original full viewport')
        for field in ('styleDefaultsSource', 'styleDefaultsPolicy'):
            if field in trees[layout]:
                require(vm.get(field) == trees[layout][field],
                        'EconomicOverview VM style provenance differs from its frozen original tree')
        _economic_retained_tree(vm['tree'], trees[layout])
        for field in ('inputTargets', 'scrollTargets'):
            require(type(vm.get(field)) is list and all(type(target) is dict and
                    type(target.get('key')) is int and target['key'] in keys for target in vm[field]),
                    'EconomicOverview target does not resolve inside its owning original VM')
        return nodes, set(keys)
    parent_nodes, _ = validate_vm(result, 'parent')
    slots = [node for node in parent_nodes if node.get('kind') == 'LuaContext']
    require(len(slots) == 2 and {node.get('id') for node in slots} == {'EconomicGeneralInfo', 'HappinessInfo'} and
            all(not node['children'] for node in slots),
            'EconomicOverview parent has missing, extra or precomposed child slots')
    visible = []
    for entry in entries:
        slot = entry['controlId']
        base = ECONOMIC_SPECS[slot][3]
        require(type(entry.get('keyBase')) is int and entry['keyBase'] == base,
                'EconomicOverview child keyBase is not its reserved exact range')
        child = entry.get('snapshot')
        require(type(child) is dict and not child.get('embeddedContexts'),
                'EconomicOverview child contains unsupported nested VMs')
        nodes, keys = validate_vm(child, slot)
        placeholder = next(node for node in slots if node['id'] == slot)
        require(tuple(placeholder.get(field) for field in ('x', 'y', 'width', 'height')) == (0, 0, 1920, 1080),
                'EconomicOverview original size-less LuaContext must retain its full-viewport default')
        active = snapshot['active'] and not placeholder['hidden']
        require(type(child.get('active')) is bool and child['active'] is active and
                type(child.get('timerSemaphore')) is int and child['timerSemaphore'] == 0,
                'EconomicOverview child visibility/activity/timer differs from its parent slot')
        require(active or (child['inputTargets'] == [] and child['scrollTargets'] == []),
                'Hidden EconomicOverview child must expose no input or scroll targets')
        if active:
            visible.append(slot)
        for field in ('presentationClock', 'animationPolicy', 'retailTimingVerified'):
            require(child.get(field) == snapshot.get(field), 'EconomicOverview child presentation policy differs')
        metrics = child.get('fontMetrics')
        require(type(metrics) is dict and type(metrics.get('fonts')) is dict and
                {k: v for k, v in metrics.items() if k != 'fonts'} ==
                {k: v for k, v in merged_fonts.items() if k != 'fonts'},
                'EconomicOverview child font metric policy differs')
        for font, record in metrics['fonts'].items():
            require(font not in merged_fonts['fonts'] or merged_fonts['fonts'][font] == record,
                    'EconomicOverview VMs disagree on original font metrics')
            merged_fonts['fonts'][font] = copy.deepcopy(record)
        tree = copy.deepcopy(child['tree'])
        # Snapshot keys and callback keys share one domain. Numeric callback
        # payloads (void1/void2) are game IDs and deliberately remain unchanged.
        for node in economic_walk(tree):
            node['key'] += base
            for field in ('ownerKey', 'parentKey', 'controlKey'):
                if field in node:
                    require(type(node[field]) is int and node[field] in keys,
                            'EconomicOverview draw owner reference escapes its original VM')
                    node[field] += base
        placeholder['children'] = [tree]
        for field in ('inputTargets', 'scrollTargets'):
            for target in child[field]:
                target = copy.deepcopy(target)
                target['key'] += base
                result[field].append(target)
        slot_proofs.append({'control_id': slot, 'key_base': base, 'slot_key': placeholder['key'],
                            'context_key': tree['key'], 'active': active,
                            'retained_control_count': len(nodes), 'bounds': [0, 0, 1920, 1080]})
    require(len(visible) == int(snapshot['active']), 'EconomicOverview must activate exactly one original tab')
    if snapshot['active']:
        for control_id, selected_slot in (('GeneralInfoSelectHighlight', 'EconomicGeneralInfo'),
                                          ('HappinessSelectHighlight', 'HappinessInfo')):
            matches = [node for node in parent_nodes if node.get('id') == control_id]
            require(len(matches) == 1 and matches[0]['hidden'] is (visible[0] != selected_slot),
                    'EconomicOverview original tab highlight differs from its active child VM')
        parent_targets = snapshot['inputTargets']
        expected_parent_ids = {node.get('id') for node in parent_nodes
                               if node.get('id') in ('GeneralInfoButton', 'HappinessButton', 'CloseButton')
                               and not node['hidden'] and not node.get('disabled', False)}
        require(len(parent_targets) == len(expected_parent_ids) and
                {target.get('id') for target in parent_targets} == expected_parent_ids and
                all(target.get('event') == 'LeftClick' for target in parent_targets),
                'EconomicOverview lost an enabled original parent callback')
    if not snapshot['active']:
        require(result['inputTargets'] == [] and result['scrollTargets'] == [],
                'Closed EconomicOverview still exposes input targets')
    return result, {
        'policy': 'ORIGINAL_ECONOMIC_OVERVIEW_EMBEDDED_CONTEXTS_V1',
        'source_contract': source_contract, 'slots': sorted(slot_proofs, key=lambda row: row['key_base']),
        'active_child': visible[0] if visible else None,
        'original_input_targets': copy.deepcopy(result['inputTargets']),
        'original_scroll_targets': copy.deepcopy(result['scrollTargets']),
        'original_control_tree_and_styles_retained': True,
        'retail_pixels_verified': False, 'retail_embedded_context_semantics_verified': False,
        'full_gameplay_coverage': False,
    }


def goody_hut_reward_contract(snapshot, sources=None, *, closed=False):
    """Validate the original informational ruin reward and its sole close input."""
    require(type(snapshot) is dict and type(closed) is bool and
            (snapshot.get('contextName'), snapshot.get('popupKind')) == ('GoodyHutPopup', 'GoodyHutReward') and
            snapshot.get('active') is (not closed) and snapshot.get('contextHidden') is closed and
            type(snapshot.get('timerSemaphore')) is int and snapshot['timerSemaphore'] == (0 if closed else 1),
            'GoodyHutReward modal identity, visibility or timer changed')
    state = snapshot.get('goodyHutReward')
    require(type(state) is dict and state.get('policy') == 'ORIGINAL_BNW_GOODY_HUT_REWARD_INFORMATIONAL_V1' and
            state.get('rewardAlreadyApplied') is True and state.get('nativeAcceptanceVerified') is False and
            state.get('shown') is True and state.get('processed') is closed and
            type(state.get('timerSemaphore')) is int and state['timerSemaphore'] == snapshot['timerSemaphore'],
            'GoodyHutReward informational lifecycle or proof boundary changed')
    for field in ('rewardId', 'specialValue'):
        require(type(state.get(field)) is int and 0 <= state[field] <= 2147483647,
                'GoodyHutReward original integer payload is invalid: ' + field)
    for field, name, size, digest in (
            ('originalLayoutLua', 'GoodyHutPopup.lua', 2877, '633ddaa3497d3fcf40892481878806e819e4009f3c5a20421d9a7868f035ff5c'),
            ('originalLayoutXml', 'GoodyHutPopup.xml', 1466, '479aaf644a5c93300f3d0baeff5515accdff6a9093dc9c285621a5837e27b6ee')):
        ref = state.get(field)
        suffix = 'Assets/DLC/Expansion2/UI/InGame/Popups/' + name
        require(type(ref) is dict and isinstance(ref.get('path'), str) and Path(ref['path']).is_absolute() and
                ref['path'].replace('\\', '/').casefold().endswith('/' + suffix.casefold()) and
                type(ref.get('bytes')) is int and ref['bytes'] == size and ref.get('sha256') == digest,
                'GoodyHutReward provenance differs from its immutable original: ' + field)
        if sources is not None:
            require(any(str(path).replace('\\', '/').casefold() == ref['path'].replace('\\', '/').casefold() and
                        value == digest for path, value in sources.items()),
                    'GoodyHutReward original is absent from the compiled source set')
    popup = GOODY_HUT_REWARD_POPUP_ENUM_VALUE
    require(snapshot.get('lifecycle') == ['queued', f'shown:{popup}'] +
            ([f'processed:{popup}', 'closed'] if closed else []),
            'GoodyHutReward must show and process its original popup exactly once')
    root = snapshot.get('tree')
    require(type(root) is dict and root.get('kind') == 'Context' and
            (root.get('width'), root.get('height')) == (1920, 1080),
            'GoodyHutReward requires its original logical 1920x1080 viewport')
    nodes, keys, parents = [], set(), {}
    def visit(node, parent=None):
        require(type(node) is dict and type(node.get('key')) is int and node['key'] > 0 and
                node['key'] not in keys and len(keys) < 64 and type(node.get('children')) is list,
                'GoodyHutReward retained control identity is invalid')
        keys.add(node['key']);nodes.append(node);parents[node['key']] = parent
        for child in node['children']: visit(child, node)
    visit(root)
    require(len(nodes) == 12 and {node.get('id') for node in nodes if node.get('id')} ==
            {'TitleLabel', 'DescriptionLabel', 'CloseButton'},
            'GoodyHutReward must retain every original control and no invented choice')
    def one(name):
        matches = [node for node in nodes if node.get('id') == name]
        require(len(matches) == 1, 'GoodyHutReward lacks a unique original ' + name)
        return matches[0]
    for name in ('TitleLabel', 'DescriptionLabel'):
        node = one(name)
        require(node.get('kind') == 'Label' and isinstance(node.get('text'), str) and node['text'].strip(),
                'GoodyHutReward original localized label is missing: ' + name)
    close = one('CloseButton');parent = parents[close['key']]
    close_source = {'Size': '200,36', 'Anchor': 'C,B', 'Style': 'BaseButton',
                    'AnchorSide': 'I.O', 'Offset': '0,0', 'ID': 'CloseButton', 'Hidden': '0'}
    require(close.get('kind') == 'GridButton' and close.get('hidden') is False and
            close.get('sourceAttributes') == close_source and
            all(close.get('attributes', {}).get(key) == value for key, value in close_source.items()) and
            type(parent) is dict and parent.get('kind') == 'Grid' and
            parent.get('sourceAttributes') == {'Size': '400,270', 'Anchor': 'C,C', 'Offset': '0,0',
                                               'Style': 'Grid9DetailFive140'},
            'GoodyHutReward changed its original outside-grid CloseButton or parent')
    parent_bounds = anchor(parent['sourceAttributes'], (0, 0, 1920, 1080), 400, 270)
    close_bounds = anchor(close_source, parent_bounds, 200, 36)
    require(tuple(close.get(field) for field in ('x', 'y', 'width', 'height')) == close_bounds,
            'GoodyHutReward CloseButton must keep its original outside-grid bounds')
    original_textures = ['Assets/UI/Art/Controls/AncientRuinsPopupTop300.dds', 'NaturalWonders512.dds']
    require([node.get('sourceAttributes', {}).get('Texture') for node in nodes if node.get('kind') == 'Image'] ==
            original_textures and
            [node.get('attributes', {}).get('Texture') for node in nodes if node.get('kind') == 'Image'] ==
            original_textures, 'GoodyHutReward original artwork was replaced')
    inputs = snapshot.get('inputTargets')
    require(type(inputs) is list and snapshot.get('scrollTargets') == [],
            'GoodyHutReward has no original scroll controls')
    if closed:
        require(inputs == [], 'Closed GoodyHutReward must expose no stale input')
    else:
        require(len(inputs) == 1 and type(inputs[0]) is dict and inputs[0].get('key') == close['key'] and
                inputs[0].get('id') == 'CloseButton' and inputs[0].get('event') == 'LeftClick' and
                inputs[0].get('visible') is True and inputs[0].get('disabled') is False and
                xywh_dict(inputs[0].get('bounds'), 'GoodyHutReward close target') == rect(close_bounds) and
                xywh_dict(inputs[0].get('clippedBounds'), 'GoodyHutReward close clip') == rect(close_bounds),
                'GoodyHutReward must expose exactly its original unclipped CloseButton callback')
    return {'policy': state['policy'], 'reward_id': state['rewardId'], 'special_value': state['specialValue'],
            'close_button_key': close['key'], 'close_bounds': close_bounds, 'modal': True,
            'timer_semaphore': snapshot['timerSemaphore'], 'processed': state['processed'],
            'reward_already_applied': True, 'gameplay_commands': False,
            'original_layout_lua': state['originalLayoutLua'], 'original_layout_xml': state['originalLayoutXml'],
            'native_acceptance_verified': False, 'retail_pixels_verified': False}


def pantheon_controls_contract(snapshot, sources=None, *, closed=False):
    """Validate the source-bound Pantheon-only modal, without native acceptance."""
    require(type(snapshot) is dict and type(closed) is bool and
            (snapshot.get('contextName'), snapshot.get('popupKind')) == ('ChoosePantheonPopup', 'Pantheon') and
            snapshot.get('active') is (not closed) and type(snapshot.get('timerSemaphore')) is int and
            snapshot['timerSemaphore'] == (0 if closed else 1), 'Pantheon modal identity or timer changed')
    state = snapshot.get('pantheon')
    require(type(state) is dict and state.get('policy') == 'ORIGINAL_BNW_PANTHEON_ONLY_V1' and
            state.get('rowTemplate') == 'ItemInstance' and state.get('reformationSupported') is False and
            state.get('nativeAcceptanceVerified') is False and type(state.get('selectedMode')) is int and
            state['selectedMode'] == 1 and state.get('hudInfoCornerPresent') is False,
            'Pantheon mode, source contract or native proof boundary changed')
    for key, minimum in (('owner', 0), ('turn', 0), ('generation', 1), ('selectedBelief', -1), ('commandsApplied', 0)):
        require(type(state.get(key)) is int and minimum <= state[key] <= 2147483647,
                'Pantheon captured integer is invalid: ' + key)
    require(state['commandsApplied'] <= 1 and type(state.get('confirmationVisible')) is bool and
            state.get('hudUnitPanelHidden') is (not closed) and
            type(state.get('timerSemaphore')) is int and state['timerSemaphore'] == snapshot['timerSemaphore'],
            'Pantheon retained visibility or command count changed')
    for field, name, size, digest in (
            ('originalLayoutLua', 'ChoosePantheonPopup.lua', 7854, '23a7205f1966347b52cd79c163a396f6252e3c756da609e2cebb7a8866c31bcf'),
            ('originalLayoutXml', 'ChoosePantheonPopup.xml', 5357, '6408228e6a85b428125d38109419abfa0ef422b3694534c8b311c1a5a784e74c')):
        ref = state.get(field)
        suffix = 'Assets/DLC/Expansion2/UI/InGame/Popups/' + name
        require(type(ref) is dict and isinstance(ref.get('path'), str) and Path(ref['path']).is_absolute() and
                ref['path'].replace('\\', '/').casefold().endswith('/' + suffix.casefold()) and
                type(ref.get('bytes')) is int and ref['bytes'] == size and ref.get('sha256') == digest,
                'Pantheon provenance differs from its immutable original: ' + field)
        if sources is not None:
            require(any(str(path).replace('\\', '/').casefold() == ref['path'].replace('\\', '/').casefold() and
                        value == digest for path, value in sources.items()), 'Pantheon original is absent from the compiled source set')
    lifecycle = snapshot.get('lifecycle')
    require(type(lifecycle) is list and len(lifecycle) == (4 if closed else 2) and lifecycle[0] == 'queued' and
            isinstance(lifecycle[1], str) and re.fullmatch(r'shown:[0-9]+', lifecycle[1]),
            'Pantheon lacks the original queued/shown lifecycle')
    if closed:
        require(lifecycle[2] == 'processed:' + lifecycle[1].split(':')[1] and lifecycle[3] == 'closed' and
                snapshot.get('inputTargets') == [] and snapshot.get('scrollTargets') == [],
                'Pantheon close must process before timer release and expose no input')
    root = snapshot.get('tree')
    require(type(root) is dict and root.get('kind') == 'Context', 'Pantheon retained root is missing')
    nodes, keys = [], set()
    def visit(node):
        require(type(node) is dict and type(node.get('key')) is int and node['key'] > 0 and
                node['key'] not in keys and len(keys) < 8192, 'Pantheon retained control identity is invalid')
        keys.add(node['key']);nodes.append(node)
        for child in node.get('children', []): visit(child)
    visit(root)
    def one(name):
        matches = [node for node in nodes if node.get('id') == name]
        require(len(matches) == 1, 'Pantheon lacks a unique original ' + name)
        return matches[0]
    for name in ('ItemStack', 'ItemScrollPanel', 'BottomPanel', 'CloseButton', 'PanelTitle', 'CivIcon',
                 'CivIconBG', 'CivIconShadow', 'ConfirmText', 'Yes', 'No'): one(name)
    confirmation = one('ChooseConfirm')
    require(confirmation.get('kind') == 'Box' and confirmation.get('attributes', {}).get('ConsumeMouse') == '1' and
            confirmation.get('hidden') is (not state['confirmationVisible']), 'Pantheon confirmation barrier differs from its original state')
    inputs = snapshot.get('inputTargets')
    require(type(inputs) is list and len(inputs) <= 1024, 'Pantheon input inventory is invalid')
    ids = {row.get('id') for row in inputs if row.get('event') == 'LeftClick'}
    require(closed or ids <= ({'Yes', 'No'} if state['confirmationVisible'] else {'Button', 'CloseButton'}),
            'Pantheon confirmation exposes a covered original callback')
    scrolls = snapshot.get('scrollTargets')
    require(type(scrolls) is list and (scrolls == [] if closed or state['confirmationVisible'] else
            len(scrolls) == 1 and scrolls[0].get('key') == one('ItemScrollPanel')['key']),
            'Pantheon confirmation exposes its covered scroll panel')
    return {'policy': state['policy'], 'owner': state['owner'], 'turn': state['turn'],
            'generation': state['generation'], 'confirmation_visible': state['confirmationVisible'],
            'scroll_input_keys': [row['key'] for row in scrolls],
            'commands_applied': state['commandsApplied'], 'native_acceptance_verified': False}


def validate_social_policy_metadata(value):
    """Validate the exact source-owned SocialPolicy SDK state retained by the Host."""
    require(type(value) is dict and
            type(value.get('activePlayer')) is int and value['activePlayer'] >= 0 and
            value.get('currentTab') in ('SocialPolicies', 'Ideologies') and
            type(value.get('policyInfo')) is bool and
            type(value.get('hasCity')) is bool and
            type(value.get('ideologyPaneVisible')) is bool and
            type(value.get('branchSwitchConfirmationPresent')) is bool and
            type(value.get('ideologyChangePresent')) is bool,
            'SocialPolicy metadata lacks the original active player, tab, checkbox or confirmation states')
    policies, branches = value.get('policies'), value.get('branches')
    policy_tab_branch_ids = value.get('policyTabBranchIds')
    require(type(policies) is list and 1 <= len(policies) <= 1000 and
            type(branches) is list and 1 <= len(branches) <= 100 and
            type(policy_tab_branch_ids) is list and len(policy_tab_branch_ids) <= len(branches),
            'SocialPolicy metadata lacks bounded original SDK policy and branch enumeration')
    def valid_id(item):
        return type(item) is int and item >= 0
    policy_ids, branch_ids, branch_types = [], [], []
    for branch in branches:
        require(type(branch) is dict and valid_id(branch.get('id')) and
                type(branch.get('type')) is str and 1 <= len(branch['type']) <= 128 and
                bool(branch['type'].strip()) and
                all(type(branch.get(field)) is bool for field in ('unlocked', 'canUnlock', 'blocked')),
                'SocialPolicy branch row lacks its original ID/type/unlocked/canUnlock/blocked state')
        branch_ids.append(branch['id'])
        branch_types.append(branch['type'])
    require(len(set(branch_ids)) == len(branch_ids), 'SocialPolicy branch IDs are duplicated')
    require(len(set(branch_types)) == len(branch_types), 'SocialPolicy branch type strings are duplicated')
    require(all(valid_id(branch_id) for branch_id in policy_tab_branch_ids) and
            policy_tab_branch_ids == list(range(len(policy_tab_branch_ids))) and
            set(policy_tab_branch_ids).issubset(branch_ids),
            'SocialPolicy policy-tab branch IDs are malformed or differ from the original 0..N-1 loop before PurchaseByLevel')
    for policy in policies:
        require(type(policy) is dict and valid_id(policy.get('id')) and
                type(policy.get('branch')) is str and len(policy['branch']) <= 128 and
                (policy['branch'] == '' or policy['branch'] in branch_types) and
                all(type(policy.get(field)) is bool for field in ('has', 'canAdopt', 'blocked')),
                'SocialPolicy row lacks its original ID/known branch/has/canAdopt/blocked state')
        policy_ids.append(policy['id'])
    require(len(set(policy_ids)) == len(policy_ids), 'SocialPolicy IDs are duplicated')
    return value


def validate_social_policy_hover_gate(node):
    """Keep the stock HideOnMouseOver subtree as a source-backed inverse gate."""
    require(type(node) is dict and node.get('kind') == 'HideOnMouseOver' and
            type(node.get('hovered')) is bool and
            node.get('hoverPolicy') == 'ZEROSIS_RETAINED_SOCIAL_POLICY_INVERSE_HOVER_GATE_V1' and
            node.get('blankAreaHoverVerified') is False and
            type(node.get('sourceAttributes')) is dict and
            type(node.get('attributes')) is dict and
            all(node['attributes'].get(name) == value
                for name, value in node['sourceAttributes'].items()),
            'SocialPolicy HideOnMouseOver lacks its source-backed inverse hover gate contract')
    return node


def validate_social_policy_zero_area_alpha_anim(node, attrs):
    """Allow only the two stock textureless policy/tenet label opacity wrappers."""
    source = node.get('sourceAttributes')
    children = node.get('children')
    child = children[0] if type(children) is list and len(children) == 1 else None
    child_id = child.get('id') if type(child) is dict else None
    # SocialPolicyPopup.xml:72-74 and :457-459 are separate stock wrappers;
    # their label IDs and placements must not be mixed between tabs.
    placements = {'FreePoliciesLabel': ('L,C', '-10,0'),
                  'FreeTenetsLabel': ('L,T', '-10,20')}
    placement = placements.get(child_id) if type(child_id) is str else None
    expected = {'AlphaStart': '.99', 'AlphaEnd': '.25', 'Cycle': 'Bounce',
                'Speed': '1', 'Pause': '0', 'AnchorSide': 'O.I', 'Hidden': '0'}
    if placement is not None:
        expected.update(Anchor=placement[0], Offset=placement[1])
    expected_label = {'Anchor': 'L,C', 'Offset': '0,0', 'String': '',
                      'Font': 'TwCenMT18', 'ID': child_id, 'FontStyle': 'SoftShadow',
                      'Color0': 'Culture.255', 'Color1': 'Black.128',
                      'Color2': 'Culture.255', 'Hidden': '1'}
    require(placement is not None and type(source) is dict and type(attrs) is dict and
            node.get('kind') == 'AlphaAnim' and node.get('width') == 0 and node.get('height') == 0 and
            source == expected and
            'Size' not in attrs and 'Texture' not in attrs and
            node.get('texture') in ('', None) and
            all(attrs.get(name) == value for name, value in expected.items()) and
            type(child) is dict and child.get('kind') == 'Label' and
            child.get('sourceAttributes') == expected_label and
            type(child.get('attributes')) is dict and
            all(child['attributes'].get(name) == value for name, value in expected_label.items()) and
            'Size' not in child['attributes'] and 'Texture' not in child['attributes'] and
            child.get('texture') in ('', None) and child.get('children') == [],
            'Zero-area SocialPolicy AlphaAnim differs from the original textureless policy/tenet label opacity wrappers')
    return node


def multiply_opacity(color, opacity):
    require(type(color) in (tuple, list) and len(color) == 4 and
            all(type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 1
                for value in color) and
            type(opacity) in (int, float) and math.isfinite(opacity) and 0 <= opacity <= 1,
            'Invalid retained UI color or inherited opacity')
    return color[0], color[1], color[2], color[3] * opacity


def valid_leader_message(message):
    """Accept the original intro or the exact SDK human-declared-war response."""
    if (type(message) is not dict or
            any(type(message.get(name)) is not int
                for name in ('player', 'state', 'animation', 'data1')) or
            message['player'] < 0 or type(message.get('text')) is not str or
            not message['text'].strip()):
        return False
    intro = (message['state'] == DIPLO_UI_STATE_DEFAULT_ROOT_ENUM_VALUE and
             message['animation'] == LEADERHEAD_ANIM_INTRO_ENUM_VALUE)
    declared_war = (
        message['state'] == DIPLO_UI_STATE_WAR_DECLARED_BY_HUMAN_ENUM_VALUE and
        message['animation'] == LEADERHEAD_ANIM_ATTACKED_ENUM_VALUE and
        message['data1'] == 0)
    return intro or declared_war


def valid_unit_panel_lifecycle(lifecycle, *, active):
    """Accept only queued/hidden visibility transitions, ending in the captured state."""
    if type(lifecycle) is not list or not lifecycle:
        return False
    if len(lifecycle) % 2 != (1 if active else 0):
        return False
    if not active and len(lifecycle) < 2:
        return False
    return all(value == ('queued' if index % 2 == 0 else 'context-hidden:UnitPanel')
               for index, value in enumerate(lifecycle))


def top_panel_interaction_contract(snapshot):
    """Bind SciencePerTurn availability to the original TopPanelInfoStack visibility.

    Stock TopPanel.lua hides this entire Stack when the active player has no
    cities. A hidden ancestor suppresses its child callback targets even when
    those children retain local hidden=false values in the captured tree.
    """
    require(type(snapshot) is dict and type(snapshot.get('tree')) is dict and
            type(snapshot.get('inputTargets')) is list and
            all(type(target) is dict for target in snapshot['inputTargets']),
            'TopPanel snapshot lacks a retained tree or well-formed input target list')
    stack_matches = []
    def find_stack(node):
        if type(node) is dict:
            if node.get('id') == 'TopPanelInfoStack':
                stack_matches.append(node)
            for child in node.get('children', []):
                find_stack(child)
    find_stack(snapshot['tree'])
    require(len(stack_matches) == 1 and stack_matches[0].get('kind') == 'Stack' and
            stack_matches[0].get('sourceAttributes', {}).get('ID') == 'TopPanelInfoStack' and
            type(stack_matches[0].get('hidden')) is bool,
            'TopPanel snapshot lacks the unique original TopPanelInfoStack visibility state')
    stack = stack_matches[0]
    descendant_keys = set()
    def collect_keys(node):
        if type(node) is dict:
            key = node.get('key')
            if type(key) is int:
                descendant_keys.add(key)
            for child in node.get('children', []):
                collect_keys(child)
    collect_keys(stack)
    nested_targets = [target for target in snapshot['inputTargets']
                      if type(target.get('key')) is int and target['key'] in descendant_keys]
    science_targets = [target for target in snapshot['inputTargets']
                       if target.get('id') == 'SciencePerTurn']
    hidden = stack['hidden']
    if hidden:
        require(not nested_targets and not science_targets,
                'Hidden original TopPanelInfoStack still exposes child callback targets')
    else:
        require(len(science_targets) == 1 and science_targets[0].get('event') == 'LeftClick' and
                science_targets[0].get('toolTipCallback') is True,
                'Visible original TopPanelInfoStack lacks its unique SciencePerTurn click/tooltip target')
    require(type(stack.get('key')) is int and stack['key'] >= 0,
            'TopPanelInfoStack has no valid retained control key')
    return {'info_stack_key': stack['key'], 'info_stack_hidden': hidden,
            'science_callback_available': not hidden,
            'science_callback_target': None if hidden else science_targets[0],
            'hidden_descendant_callback_count': len(nested_targets)}


def valid_declare_war_lifecycle(lifecycle, *, active):
    """Keep stock popup event order without pinning a ButtonPopupTypes ordinal."""
    if type(lifecycle) is not list or not all(type(item) is str for item in lifecycle):
        return False
    if len(lifecycle) != (3 if active else 4) or lifecycle[0] != 'queued':
        return False
    shown = re.fullmatch(r'shown:([0-9]+)', lifecycle[1])
    processed = re.fullmatch(r'processed:([0-9]+)', lifecycle[2])
    return bool(shown and processed and shown.group(1) == processed.group(1) and
                (active or lifecycle[3] == 'closed'))


def pair(raw, default='0,0'):
    values = (raw if raw is not None else default).replace('.', ',').split(',')
    require(len(values) == 2 and all(re.fullmatch(r'-?\d+', value) for value in values), 'Unsupported coordinate pair')
    return tuple(int(value) for value in values)


def intersect(a, b):
    return (max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3]))


def positive(rect):
    return rect[2] > rect[0] and rect[3] > rect[1]


def consume_mouse_enabled(attributes):
    """Recognize only the two stock XML truth spellings used by retained layouts."""
    return type(attributes) is dict and attributes.get('ConsumeMouse') in ('1', 'true')


def anchor(attrs, parent, width, height, offset_y=0):
    ax, ay = (part.upper() for part in attrs.get('Anchor', 'L,T').split(','))
    sx, sy = (part.upper() for part in attrs.get('AnchorSide', 'I,I').replace('.', ',').split(','))
    require(ax in ('L', 'C', 'R') and ay in ('T', 'C', 'B') and sx in ('I', 'O') and sy in ('I', 'O'),
            'Unsupported anchor')
    dx, dy = pair(attrs.get('Offset'))
    px, py, pw, ph = parent
    x = dx if ax == 'L' else (pw - width) / 2 + dx if ax == 'C' else pw - width - dx
    y = dy if ay == 'T' else (ph - height) / 2 + dy if ay == 'C' else ph - height - dy
    # The source UI runtime treats an outside side on a centered axis as
    # inapplicable: centering still determines that axis' position.
    if sx == 'O' and ax != 'C':
        x = pw + dx if ax == 'R' else -width - dx
    if sy == 'O' and ay != 'C':
        y = ph + dy if ay == 'B' else -height - dy
    return px + x, py + y + offset_y, width, height


def rect(bounds):
    x, y, w, h = bounds
    return x, y, x + w, y + h


def image_regions(u, v, bounds, texture_size, *, stretch_full_texture=False,
                  source_extent=None):
    """Resolve a source region and target for a retained Image control."""
    texture_width, texture_height = texture_size
    x, y, width, height = bounds
    extent_width, extent_height = source_extent or (width, height)
    require(all(type(value) in (int, float) and math.isfinite(value)
                for value in (u, v, x, y, width, height, texture_width, texture_height,
                              extent_width, extent_height)) and
            u >= 0 and v >= 0 and width > 0 and height > 0 and
            texture_width > 0 and texture_height > 0 and
            extent_width > 0 and extent_height > 0,
            'Invalid retained Image source or target geometry')
    if stretch_full_texture:
        require(u == 0 and v == 0,
                'Full-texture Image stretch requires the captured zero texture offset')
        return (0, 0, texture_width, texture_height), rect(bounds), \
               'ZEROSIS_CANDIDATE_STRETCH_FULL_TECHPIPE_TEXTURE_TO_RETAINED_BOUNDS'
    require(u + extent_width <= texture_width and v + extent_height <= texture_height,
            'Image region outside restored original atlas')
    policy = ('ZEROSIS_CANDIDATE_STRETCH_TECHBRANCH_32PX_ATLAS_CELL_TO_RETAINED_BOUNDS'
              if source_extent is not None and (extent_width, extent_height) != (width, height)
              else 'SOURCE_REGION_MATCHES_RETAINED_BOUNDS')
    return (u, v, u + extent_width, v + extent_height), rect(bounds), policy


def bounds_size(bounds):
    """Return width/height from retained x/y/width/height geometry."""
    require(type(bounds) in (tuple, list) and len(bounds) == 4 and
            all(type(value) in (int, float) and math.isfinite(value) for value in bounds) and
            bounds[2] >= 0 and bounds[3] >= 0,
            'Invalid retained x/y/width/height bounds')
    return bounds[2], bounds[3]


def scroll_extent(bounds, content_height):
    _, height = bounds_size(bounds)
    require(type(content_height) in (int, float) and math.isfinite(content_height) and content_height >= 0,
            'Invalid captured scroll content height')
    return max(0.0, content_height - height)


def production_line_advance(font, attrs):
    """Apply the retained control's XML LeadingOffset to the original GGXML line box."""
    raw = attrs.get('LeadingOffset', 0)
    try:
        leading = float(raw)
    except (TypeError, ValueError) as error:
        raise ValueError('Invalid production label LeadingOffset') from error
    require(math.isfinite(leading), 'Invalid production label LeadingOffset')
    result = font.line_advance + leading
    require(math.isfinite(result) and result > 0, 'Production label line advance is not positive')
    return result


def font_layer_colors(layer_colors, layer_count, *, font_style, color_set):
    """Resolve the original UI layer palette without silently dropping effects.

    Original UI layouts use both Beige_Black and Beige_Black_Alpha (each with
    Color0/Color1 only) with the three-layer SoftShadow GGXML style. The style
    defines the glyph, shadow, and soft-shadow texture layers; the candidate
    maps Color0 to the glyph and the declared effect Color1 to both effect
    layers. Retail renderer color fallback is not verified.
    """
    require(type(layer_colors) in (tuple, list) and layer_count > 0 and
            all(type(color) in (tuple, list) and len(color) == 4 and
                all(type(channel) in (int, float) and math.isfinite(channel) and 0 <= channel <= 1
                    for channel in color) for color in layer_colors),
            'Invalid font layer color palette')
    if len(layer_colors) >= layer_count:
        policy = ('SOURCE_COLORSET_EXACT_LAYER_COUNT' if len(layer_colors) == layer_count else
                  'SOURCE_COLORSET_UNUSED_TRAILING_COLORS')
        return tuple(tuple(color) for color in layer_colors[:layer_count]), policy
    if (color_set in ('Beige_Black', 'Beige_Black_Alpha') and font_style == 'SoftShadow' and
            layer_count == 3 and len(layer_colors) == 2):
        return (tuple(layer_colors[0]), tuple(layer_colors[1]), tuple(layer_colors[1])), \
               'ZEROSIS_CANDIDATE_REPEAT_LAST_EFFECT_COLOR_FOR_SOFTSHADOW'
    raise ValueError('Font ColorSet layer count differs from its original GGXML style')


def centered_button_text_bounds(button_bounds, text_width, text_height, text_offset, *, max_vertical_overhang=0):
    """Place original direct GridButton text at the control center plus TextOffset."""
    require(type(button_bounds) in (tuple, list) and len(button_bounds) == 4 and
            all(type(value) in (int, float) and math.isfinite(value) for value in button_bounds),
            'Invalid original button bounds for direct text')
    x, y, width, height = button_bounds
    require(width > 0 and height > 0 and
            all(type(value) in (int, float) and math.isfinite(value) for value in
                (text_width, text_height, *text_offset)) and
            type(max_vertical_overhang) is int and 0 <= max_vertical_overhang <= 1 and
            0 < text_width <= width and 0 < text_height <= height + max_vertical_overhang,
            'Original GridButton text does not fit its retained control bounds')
    offset_x, offset_y = text_offset
    return (x + (width - text_width) / 2 + offset_x,
            y + (height - text_height) / 2 + offset_y,
            text_width, text_height)


def texture_bar_regions(bounds, direction, percent, texture_width, texture_height):
    """Return source xyxy and target xyxy for one captured TextureBar fraction."""
    x, y, width, height = bounds
    require(direction in ('Up', 'Down', 'Left', 'Right') and
            all(type(value) in (int, float) and math.isfinite(value)
                for value in (x, y, width, height, percent, texture_width, texture_height)) and
            width > 0 and height > 0 and 0 <= percent <= 1 and
            texture_width > 0 and texture_height > 0,
            'Invalid captured TextureBar geometry')
    if direction in ('Up', 'Down'):
        filled = height * percent
        target = (x, y + height - filled if direction == 'Up' else y, x + width,
                  y + height if direction == 'Up' else y + filled)
        source = (0, texture_height * (1 - percent) if direction == 'Up' else 0,
                  texture_width, texture_height if direction == 'Up' else texture_height * percent)
    else:
        filled = width * percent
        target = (x + width - filled if direction == 'Right' else x, y,
                  x + width if direction == 'Right' else x + filled, y + height)
        source = (texture_width * (1 - percent) if direction == 'Right' else 0, 0,
                  texture_width if direction == 'Right' else texture_width * percent, texture_height)
    return source, target


def scrollbar_thumb_bounds(bounds, scroll, content_height, minimum_thumb):
    """Return the scroll thumb as an edge rectangle from retained geometry."""
    x, y, width, height = bounds
    require(all(type(value) in (int, float) and math.isfinite(value)
                for value in (x, y, width, height, scroll, content_height, minimum_thumb)) and
            width > 0 and height > 0 and content_height > 0 and minimum_thumb > 0 and
            0 <= scroll <= content_height - height,
            'Invalid captured ScrollBar thumb geometry')
    thumb_height = min(height, max(minimum_thumb, height * height / content_height))
    extent = content_height - height
    travel = max(0, height - thumb_height)
    thumb_top = y + travel * scroll / extent if extent else y
    return x, thumb_top, x + width, thumb_top + thumb_height


def production_scrollbar_thumb_bounds(bounds, scroll, content_height, viewport_height, minimum_thumb):
    """Draw the Production vertical shuttle from its retained panel range.

    A panel with no overflow uses a full-track thumb at the origin. Overflow
    scales the thumb by viewport/content and positions it by the captured
    scroll/max-scroll ratio. This is an owned frontend candidate policy.
    """
    x, y, width, height = bounds
    values = (x, y, width, height, scroll, content_height, viewport_height, minimum_thumb)
    require(all(type(value) in (int, float) and math.isfinite(value) for value in values) and
            width > 0 and height > 0 and content_height >= 0 and viewport_height > 0 and minimum_thumb > 0,
            'Invalid retained Production ScrollBar geometry or range')
    maximum_scroll = max(0.0, content_height - viewport_height)
    require(0 <= scroll <= maximum_scroll,
            'Production ScrollBar offset exceeds its captured ScrollPanel range')
    if content_height <= viewport_height:
        require(scroll == 0, 'Production ScrollBar with short content must have zero offset')
        return x, y, x + width, y + height
    thumb_height = min(height, max(minimum_thumb, height * viewport_height / content_height))
    thumb_travel = max(0.0, height - thumb_height)
    thumb_top = y + thumb_travel * scroll / maximum_scroll
    return x, thumb_top, x + width, thumb_top + thumb_height


def research_scrollbar_thumb_bounds(bounds, scroll, content_height, minimum_thumb):
    """Owned TechPopup thumb candidate from captured scroll range and original shuttle minimum size."""
    x, y, width, height = bounds
    require(all(type(value) in (int, float) and math.isfinite(value)
                for value in (x, y, width, height, scroll, content_height, minimum_thumb)) and
            width > 0 and height > 0 and content_height >= 0 and minimum_thumb > 0,
            'Invalid retained Research ScrollBar geometry')
    maximum_scroll = max(0.0, content_height - height)
    require(0 <= scroll <= maximum_scroll, 'Research ScrollBar scroll exceeds captured range')
    if content_height <= height:
        require(scroll == 0, 'Research ScrollBar with short content must have zero scroll')
        return x, y, x + width, y + height
    return scrollbar_thumb_bounds(bounds, scroll, content_height, minimum_thumb)


def research_tree_scrollbar_thumb_bounds(bounds, scroll, content_width, viewport_width, minimum_thumb):
    """Owned TechTree horizontal thumb candidate from original shuttle size/range."""
    x, y, width, height = bounds
    require(all(type(value) in (int, float) and math.isfinite(value)
                for value in (x, y, width, height, scroll, content_width, viewport_width, minimum_thumb)) and
            width > 0 and height > 0 and content_width >= 0 and viewport_width > 0 and minimum_thumb > 0,
            'Invalid retained ResearchTree ScrollBar geometry')
    maximum_scroll = max(0.0, content_width - viewport_width)
    require(0 <= scroll <= maximum_scroll, 'ResearchTree ScrollBar scroll exceeds captured range')
    if content_width <= width:
        require(scroll == 0, 'ResearchTree ScrollBar with short content must have zero scroll')
        return x, y, x + width, y + height
    thumb_width = min(width, max(minimum_thumb, width * viewport_width / content_width))
    travel = max(0.0, width - thumb_width)
    thumb_left = x + travel * scroll / maximum_scroll if maximum_scroll else x
    return thumb_left, y, thumb_left + thumb_width, y + height


def city_view_hex_center(hex_x, hex_y, projection):
    """Map a CityView axial hex to the official world-view odd-row screen center."""
    require(type(projection) is dict and projection.get('policy') == 'ZEROSIS_2D_CITY_VIEW_V1',
            'CityView projection policy differs from the retained map renderer contract')
    values = ('cameraX', 'cameraY', 'gridWidth', 'gridHeight', 'tileWidth', 'centerX', 'centerY')
    require(all(type(projection.get(name)) in (int, float) and math.isfinite(projection[name])
                for name in values), 'CityView projection lacks finite camera/grid geometry')
    camera_x, camera_y = int(projection['cameraX']), int(projection['cameraY'])
    grid_width, grid_height = int(projection['gridWidth']), int(projection['gridHeight'])
    require(grid_width > 0 and grid_height > 0 and projection['tileWidth'] > 0 and
            type(projection.get('wrapX')) is bool and type(projection.get('wrapY')) is bool and
            type(hex_x) is int and type(hex_y) is int,
            'CityView projection or axial hex coordinate is invalid')
    grid_x = hex_x + math.floor(hex_y / 2)
    grid_y = hex_y
    require(0 <= grid_x < grid_width and 0 <= grid_y < grid_height,
            'CityView axial hex resolves outside the retained map grid')
    dx, dy = grid_x - camera_x, grid_y - camera_y
    if projection['wrapX']:
        if dx > grid_width // 2:
            dx -= grid_width
        elif dx < -(grid_width // 2):
            dx += grid_width
    if projection['wrapY']:
        if dy > grid_height // 2:
            dy -= grid_height
        elif dy < -(grid_height // 2):
            dy += grid_height
    tile_width = float(projection['tileWidth'])
    tile_height = tile_width * 1.15470053838
    row_pitch = tile_height * 0.75
    center_x = projection['centerX'] + dx * tile_width + (((grid_y & 1) - (camera_y & 1)) * tile_width * 0.5)
    center_y = projection['centerY'] + dy * row_pitch
    require(math.isfinite(center_x) and math.isfinite(center_y), 'CityView projected hex center is nonfinite')
    return center_x, center_y, tile_width, tile_height


def city_view_raster_projection(projection):
    """Validate and normalize the sealed D3D11 CityView ID-raster projection."""
    fields = {'policy', 'cameraX', 'cameraY', 'gridWidth', 'gridHeight', 'wrapX', 'wrapY',
              'tileWidth', 'centerX', 'centerY', 'viewportWidth', 'viewportHeight', 'mapWidth',
              'frameGeneration', 'plots'}
    require(type(projection) is dict and set(projection) == fields and
            projection.get('policy') == 'ZEROSIS_D3D11_CITY_VIEW_RASTER_V1',
            'CityView D3D11 projection schema or policy differs from its native contract')
    for name in ('cameraX', 'cameraY', 'gridWidth', 'gridHeight', 'viewportWidth', 'viewportHeight',
                 'mapWidth', 'frameGeneration'):
        require(type(projection[name]) is int, f'CityView D3D11 projection {name} must be an integer')
    for name in ('tileWidth', 'centerX', 'centerY'):
        require(type(projection[name]) in (int, float) and math.isfinite(projection[name]),
                f'CityView D3D11 projection {name} must be finite')
    require(type(projection['wrapX']) is bool and type(projection['wrapY']) is bool and
            projection['gridWidth'] > 0 and projection['gridHeight'] > 0 and
            projection['gridWidth'] <= 100000 and projection['gridHeight'] <= 100000 and
            projection['gridWidth'] * projection['gridHeight'] <= 500000 and
            projection['frameGeneration'] > 0 and
            0 <= projection['cameraX'] < projection['gridWidth'] and
            0 <= projection['cameraY'] < projection['gridHeight'] and
            projection['tileWidth'] == 84 and projection['centerX'] == 960 and projection['centerY'] == 540 and
            projection['viewportWidth'] == 1920 and projection['viewportHeight'] == 1080 and
            projection['mapWidth'] == 1920,
            'CityView D3D11 projection dimensions, camera or fixed viewport profile are invalid')
    plots = projection['plots']
    require(type(plots) is dict and len(plots) <= projection['gridWidth'] * projection['gridHeight'] and
            len(plots) <= 500000, 'CityView D3D11 projection plot map exceeds its bound')
    for key in plots:
        require(type(key) is str and re.fullmatch(r'(?:0|[1-9][0-9]*)', key, re.ASCII),
                'CityView D3D11 plot key must be a canonical decimal map index')
        index = int(key)
        require(index < projection['gridWidth'] * projection['gridHeight'],
                'CityView D3D11 plot key is outside the map grid')
    total_spans = 0
    for key, row in plots.items():
        require(type(row) is dict and set(row) == {'centerX', 'centerY', 'anchorVisible', 'spans'},
                f'CityView D3D11 plot row {key} has an invalid shape')
        require(all(type(row[name]) in (int, float) and math.isfinite(row[name])
                    for name in ('centerX', 'centerY')) and type(row['anchorVisible']) is bool,
                f'CityView D3D11 plot row {key} has invalid center/anchor values')
        spans = row['spans']
        require(type(spans) is list and len(spans) <= projection['viewportHeight'] * projection['mapWidth'],
                f'CityView D3D11 plot row {key} spans exceed their bound')
        previous_y = -1
        previous_end = -1
        for span in spans:
            require(type(span) is list and len(span) == 3 and all(type(value) is int for value in span),
                    f'CityView D3D11 plot row {key} contains a malformed span')
            y, x, count = span
            require(0 <= y < projection['viewportHeight'] and 0 <= x < projection['mapWidth'] and
                    count > 0 and x + count <= projection['mapWidth'],
                    f'CityView D3D11 plot row {key} span exceeds viewport bounds')
            require(y > previous_y or (y == previous_y and x >= previous_end),
                    f'CityView D3D11 plot row {key} spans are unsorted or overlapping')
            if y != previous_y:
                previous_end = -1
            previous_y, previous_end = y, x + count
            total_spans += 1
            require(total_spans <= 2_000_000, 'CityView D3D11 total span count exceeds its bound')
    return plots


def city_view_raster_rgba(projection, highlights):
    """Paint selected native contour spans into one full-viewport BGRA DDS payload."""
    plots = city_view_raster_projection(projection)
    require(type(highlights) is list and len(highlights) <= 10000,
            'CityView D3D11 highlight list exceeds its bound')
    width, height = projection['viewportWidth'], projection['viewportHeight']
    rgba = bytearray(width * height * 4)
    occupied = bytearray(width * height)
    previous = None
    normalized = []
    rasterized = set()
    pixel_count = 0
    for item in highlights:
        require(type(item) is dict and set(item) == {'hex', 'color'} and
                type(item.get('hex')) is dict and set(item['hex']) == {'x', 'y'} and
                type(item.get('color')) is dict and set(item['color']) == {'x', 'y', 'z', 'w'},
                'Malformed original CityView D3D11 hex highlight')
        hx, hy = item['hex']['x'], item['hex']['y']
        color = item['color']
        require(type(hx) is int and type(hy) is int and
                all(type(color[name]) in (int, float) and math.isfinite(color[name]) and 0 <= color[name] <= 1
                    for name in ('x', 'y', 'z', 'w')),
                'CityView D3D11 highlight has invalid axial coordinates or RGBA color')
        order = (hy, hx)
        require(previous is None or previous < order,
                'CityView D3D11 highlights are not unique deterministic y/x order')
        previous = order
        grid_x = hx + math.floor(hy / 2)
        grid_y = hy
        require(0 <= grid_x < projection['gridWidth'] and 0 <= grid_y < projection['gridHeight'],
                'CityView D3D11 axial hex resolves outside the retained map grid')
        index = grid_y * projection['gridWidth'] + grid_x
        row = plots.get(str(index))
        normalized_row = {'hex': {'x': hx, 'y': hy}, 'map_index': index,
                          'color': [color[name] for name in ('x', 'y', 'z', 'w')],
                          'plot_present': row is not None,
                          'center': [row['centerX'], row['centerY']] if row is not None else None,
                          'anchor_visible': row['anchorVisible'] if row is not None else False,
                          'spans': copy.deepcopy(row['spans']) if row is not None else []}
        normalized.append(normalized_row)
        if row is None or not row['spans']:
            continue
        rasterized.add(index)
        red, green, blue, alpha = (round(float(color[name]) * 255) for name in ('x', 'y', 'z', 'w'))
        bgra = bytes((blue, green, red, alpha))
        for y, x, count in row['spans']:
            for px in range(x, x + count):
                at = y * width + px
                require(occupied[at] == 0,
                        'CityView D3D11 highlighted plot spans overlap another plot ID contour')
                occupied[at] = 1
                rgba[at * 4:at * 4 + 4] = bgra
                pixel_count += 1
    return bytes(rgba), normalized, len(rasterized), pixel_count


def city_view_hex_outline_rgba(width, height, line_width=0.7, samples=4):
    """Rasterize the WorldViewRenderer.cpp pointy-hex outline as an alpha mask."""
    require(type(width) is int and type(height) is int and width > 0 and height > 0 and
            type(samples) is int and 1 <= samples <= 8 and
            type(line_width) in (int, float) and math.isfinite(line_width) and line_width > 0,
            'Invalid CityView hex outline raster geometry')
    cx, cy = width / 2, height / 2
    tile_height = width * 1.15470053838
    points = ((cx, cy - tile_height / 2), (cx + width / 2, cy - tile_height / 4),
              (cx + width / 2, cy + tile_height / 4), (cx, cy + tile_height / 2),
              (cx - width / 2, cy + tile_height / 4), (cx - width / 2, cy - tile_height / 4))
    rgba = bytearray(width * height * 4)
    segments = tuple((points[i], points[(i + 1) % len(points)]) for i in range(len(points)))
    radius = line_width / 2
    for y in range(height):
        for x in range(width):
            covered = 0
            for sy in range(samples):
                py = y + (sy + 0.5) / samples
                for sx in range(samples):
                    px = x + (sx + 0.5) / samples
                    for (ax, ay), (bx, by) in segments:
                        vx, vy = bx - ax, by - ay
                        denom = vx * vx + vy * vy
                        t = max(0.0, min(1.0, ((px - ax) * vx + (py - ay) * vy) / denom))
                        if (px - (ax + t * vx)) ** 2 + (py - (ay + t * vy)) ** 2 <= radius * radius:
                            covered += 1
                            break
            if covered:
                at = (y * width + x) * 4
                rgba[at:at + 4] = bytes((255, 255, 255, round(255 * covered / (samples * samples))))
    return bytes(rgba)


def button_source_rect(u, v, target_width, target_height, texture_width, texture_height):
    """Use the available original button cell and let the target bounds scale it."""
    require(all(type(value) in (int, float) and math.isfinite(value)
                for value in (u, v, target_width, target_height, texture_width, texture_height)) and
            u >= 0 and v >= 0 and target_width > 0 and target_height > 0 and
            texture_width > u and texture_height > v,
            'Invalid original button texture region')
    source_width = min(target_width, texture_width - u)
    source_height = min(target_height, texture_height - v)
    require(source_width > 0 and source_height > 0, 'Button state has no original texture pixels')
    return u, v, u + source_width, v + source_height


def validate_hit_regions(context, hits, geometry, *, allow_empty_notification=False):
    """Validate callback and mouse-consumption regions against retained controls."""
    grid_buttons = [row for row in geometry if row.get('kind') == 'GridButton' and
                    not row.get('style_decoration')]
    if context in SCENE_CONTEXTS:
        targets = [row for row in geometry if row.get('input_target')]
        require(len(hits) == len(targets) and
                {hit[0] for hit in hits} == {row['key'] for row in targets},
                'Scene hit regions differ from registered visible input targets')
        close_keys = [row['key'] for row in targets if row.get('id') == 'CloseButton']
        if context == 'production':
            require(len(close_keys) == 1, 'Production popup needs exactly one registered CloseButton target')
        elif context == 'research-tree':
            require(len(close_keys) == 1, 'Research tree needs exactly one registered CloseButton target')
        elif context == 'city-capture':
            require(not close_keys, 'CityCapture retains no close button callback; stock ESC consumes without closing')
        elif context == 'city-view':
            return_keys = [row['key'] for row in targets if row.get('id') == 'ReturnToMapButton']
            require(not close_keys and len(return_keys) == 1 and
                    all(row.get('input_targets') == ['LeftClick'] for row in targets
                        if row.get('id') == 'ReturnToMapButton'),
                    'CityView requires its unique original ReturnToMapButton left-click callback')
        elif context == 'unit-panel':
            require(not close_keys and all(row.get('input_target') or row.get('consume_mouse_target')
                                           for row in targets),
                    'UnitPanel hit regions must resolve to a retained callback or ConsumeMouse control')
        elif context == 'top-panel':
            require(not close_keys and all(row.get('input_target') or row.get('consume_mouse_target')
                                           for row in targets),
                    'TopPanel hit regions must resolve to an original callback or ConsumeMouse control')
        elif context == 'action-info-panel':
            require(not close_keys and len(targets) <= 1 and all(
                    row.get('id') == 'EndTurnButton' and
                    sorted(row.get('input_targets', [])) == ['LeftClick', 'RightClick'] for row in targets),
                    'ActionInfoPanel hit must retain its original single left/right EndTurnButton')
        elif context == 'notification-panel':
            require(not close_keys and all(
                    (row.get('kind') == 'Button' and
                     sorted(row.get('input_targets', [])) == ['LeftClick', 'RightClick']) or
                    (row.get('kind') == 'Container' and row.get('consume_mouse_target') is True)
                    for row in targets),
                    'NotificationPanel hit regions must retain original row buttons and mouse-consuming containers')
        elif context == 'exit-confirm':
            require(not close_keys and [row.get('id') for row in targets] == ['ExitConfirm', 'Yes', 'No'] and
                    targets[0].get('input_targets') == ['ConsumeMouse'] and targets[0].get('consume_mouse_target') is True and
                    tuple(targets[0]['bounds']) == (0, 0, 1920, 1080) and
                    all(row.get('input_targets') == ['LeftClick'] for row in targets[1:]) and
                    [hit[0] for hit in hits] == [row['key'] for row in targets],
                    'ExitConfirm lost its ordered full-screen consumer or original Yes/No hits')
        elif context == 'game-menu':
            confirming = any(row.get('id') == 'ExitConfirm' and not row.get('style_decoration')
                             for row in geometry)
            require(not close_keys and
                    sum(row.get('id') == 'ReturnButton' for row in targets) == (0 if confirming else 1) and
                    all(row.get('input_targets') == ['LeftClick'] or
                        row.get('input_targets') == ['ConsumeMouse'] and row.get('consume_mouse_target') is True
                        for row in targets) and
                    [hit[0] for hit in hits] == [row['key'] for row in targets] and
                    (not confirming or sum(row.get('id') == 'ExitConfirm' and
                                           row.get('consume_mouse_target') is True and
                                           tuple(row['bounds']) == (0, 0, 1920, 1080)
                                           for row in targets) == 1),
                    'GameMenu lost its original modal callbacks or tree-ordered full-screen consumer')
        elif context == 'tech-award':
            award_keys = [row['key'] for row in targets if row.get('id') == 'ContinueButton']
            require(not close_keys and len(award_keys) == 1 and
                    all(row.get('input_targets') == ['LeftClick'] for row in targets
                        if row.get('id') == 'ContinueButton'),
                    'TechAward requires its unique original ContinueButton left-click callback')
        elif context == 'goody-hut-reward':
            require(len(targets) == len(hits) == len(close_keys) == 1 and
                    targets[0].get('kind') == 'GridButton' and targets[0].get('input_targets') == ['LeftClick'] and
                    tuple(targets[0].get('bounds', ())) == (860, 675, 200, 36) and
                    tuple(hits[0]) == (close_keys[0], 860, 675, 1060, 711),
                    'GoodyHutReward requires its unique original outside-grid CloseButton hit')
        elif context == 'diplomacy':
            back_keys = [row['key'] for row in targets if row.get('id') == 'BackButton']
            require(not close_keys and len(back_keys) == 1 and
                    all(row.get('input_targets') == ['LeftClick'] for row in geometry if row.get('input_targets')),
                    'LeaderHead intro requires one original BackButton callback and left-click targets')
        elif context == 'declare-war':
            war_buttons = [row for row in targets if row.get('id') in ('Button1', 'Button2')]
            stock_targets = {'Button1', 'Button2', 'DiplomacyHeader', 'UnderProtectionOfHeader',
                             'AlliedCityStatesHeader', 'ActiveDealsHeader', 'TradeRoutesHeader'}
            require(not close_keys and len(war_buttons) == 2 and
                    {row.get('id') for row in war_buttons} == {'Button1', 'Button2'} and
                    all(row.get('id') in stock_targets for row in targets) and
                    all(row.get('input_targets') == ['LeftClick'] for row in targets),
                    'DeclareWar requires original Yes/No and stock section-collapse callbacks only')
        elif context == 'trade-route':
            trade_route_targets = [row for row in targets if row.get('input_targets')]
            expected_ids = {'TabButtonYourTR', 'TabButtonAvailableTR', 'TabButtonTRWithYou',
                            'Domain', 'FromOwnerHeader', 'FromCityHeader', 'ToOwnerHeader',
                            'ToCityHeader', 'FromGPT', 'ToGPT', 'FromScience', 'ToScience',
                            'ToFood', 'ToProduction', 'FromReligion', 'ToReligion', 'TurnsLeft',
                            'CloseButton'}
            require(len(close_keys) == 1 and len(trade_route_targets) == len(expected_ids) and
                    {row.get('id') for row in trade_route_targets} == expected_ids and
                    all(row.get('input_targets') == ['LeftClick'] for row in trade_route_targets),
                    'TradeRoute requires its original three tabs, fourteen sort headers and CloseButton targets')
        elif context == 'economic-overview':
            parent_targets = [row for row in targets if row['key'] < ECONOMIC_KEY_SPAN]
            require(len(close_keys) == 1 and 2 <= len(parent_targets) <= 3 and
                    {'GeneralInfoButton', 'CloseButton'} <= {row.get('id') for row in parent_targets} <=
                    {'GeneralInfoButton', 'HappinessButton', 'CloseButton'} and
                    all(row.get('input_targets') == ['LeftClick'] for row in parent_targets),
                    'EconomicOverview requires its exact original parent tabs and CloseButton callbacks')
        elif context == 'social-policy':
            policy_input_targets = [row for row in targets if row.get('input_targets')]
            allowed_ids = {'TabButtonSocialPolicies', 'TabButtonIdeologies', 'PolicyInfo', 'CloseButton',
                           'Yes', 'No', 'TenetConfirmYes', 'TenetConfirmNo',
                           'ChangeIdeologyConfirmYes', 'ChangeIdeologyConfirmNo', 'TenetCancelButton'}
            dynamic_targets = [row for row in policy_input_targets if row.get('id') not in allowed_ids]
            require(len(close_keys) == 1 and all(row.get('input_targets') == ['LeftClick']
                                                  for row in policy_input_targets) and
                    {'TabButtonSocialPolicies', 'TabButtonIdeologies', 'CloseButton'} <=
                    {row.get('id') for row in policy_input_targets} and
                    all(row.get('kind') in ('Button', 'GridButton', 'CheckBox', 'RadioButton')
                        for row in policy_input_targets) and
                    len(dynamic_targets) <= 1000,
                    'SocialPolicy requires original tab, policy/branch and close callback targets')
        elif context == 'pantheon':
            ids = {row.get('id') for row in targets}
            require(ids <= {'Button', 'CloseButton', 'Yes', 'No'} and
                    (ids == {'Yes', 'No'} or 'CloseButton' in ids) and
                    all(row.get('input_targets') == ['LeftClick'] for row in targets),
                    'Pantheon hit regions expose a covered or non-original callback')
        elif context in PRIVATE_MENU_CONTEXTS:
            require(len(close_keys) == (1 if context == 'touch-help' else 0) and
                    [hit[0] for hit in hits] == [row['key'] for row in targets] and
                    all(row.get('input_targets') in (['LeftClick'], ['ConsumeMouse'], ['SliderValue']) for row in targets),
                    'Private menu hit order, close callback or modal consumer differs')
        else:
            require(not close_keys, 'Research popup unexpectedly requires a Production CloseButton')
    else:
        require(all(any(hit[0] == row['key'] for row in grid_buttons) for hit in hits),
                'Hit region has no retained GridButton')
        require(context == 'ranking' and len(hits) == 1,
                'Selected ranking popup needs exactly one close-button hit region')
    if allow_empty_notification:
        require(context == 'notification-panel' and not hits and not targets,
                'NotificationPanel may omit hit regions only when the original snapshot has no visible input targets')
    else:
        require(hits, 'Selected popup has no retained hit regions')


def style_signature(node):
    # XML indentation and attribute ordering are not meaningful duplicate differences.
    return node.tag, tuple(sorted(node.attrib.items())), tuple(style_signature(child) for child in node)


def markup(text, colors, icons=None):
    """Preserve exact text/color runs, rejecting missing or unbalanced tokens."""
    chunks, tint, stack, cursor = [], [], [], 0
    icon_occurrences = {}
    for token in re.finditer(r'\[((?:/?[A-Z][A-Z_0-9]*)|(?:COLOR:[^\[\]]*))\]', text):
        prefix = text[cursor:token.start()]
        chunks.append(prefix)
        tint.extend([stack[-1] if stack else None] * len(prefix))
        name = token.group(1)
        if name.startswith('COLOR:'):
            channels = name[6:].split(':')
            require(len(channels) == 4 and all(re.fullmatch(r'\d+', channel) for channel in channels),
                    'Invalid original numeric inline RGBA color')
            rgba = tuple(int(channel) for channel in channels)
            require(all(0 <= channel <= 255 for channel in rgba),
                    'Out of range original numeric inline RGBA color')
            require(len(stack) < 16, 'Unknown/too deeply nested original inline color')
            stack.append(tuple(channel / 255 for channel in rgba))
        elif name in ('ENDCOLOR', '/COLOR'):
            require(stack, 'Unbalanced original color close token')
            stack.pop()
        elif name.startswith('COLOR_'):
            require(name in colors and len(stack) < 16, 'Unknown/too deeply nested original inline color')
            stack.append(colors[name])
        elif name == 'NEWLINE':
            chunks.append('\n')
            tint.append(stack[-1] if stack else None)
        elif name == 'TAB':
            chunks.append('\t')
            tint.append(stack[-1] if stack else None)
        elif name.startswith('ICON_') and icons is not None:
            require(name in icons, 'Missing original inline icon mapping: ' + name)
            codepoint = 0xF0000 + len(icon_occurrences)
            icon_occurrences[codepoint] = icons[name]
            chunks.append(chr(codepoint))
            tint.append(stack[-1] if stack else None)
        else:
            raise ValueError('Unsupported original inline presentation token: ' + name)
        cursor = token.end()
    prefix = text[cursor:]
    chunks.append(prefix)
    tint.extend([stack[-1] if stack else None] * len(prefix))
    require(not stack, 'Unclosed original inline color')
    return (''.join(chunks), tint, icon_occurrences) if icons is not None else (''.join(chunks), tint)


_TOP_PANEL_NEGATIVE_GOLD = re.compile(
    r'\[ICON_GOLD\]\[COLOR:255:235:0:255\](?:"[0-9][0-9,]*"|[0-9][0-9,]*) '
    r'\[COLOR:255:60:60:255\]\(-[0-9][0-9,]*\)"?\[(ENDCOLOR|/COLOR)\]')


def close_stock_top_panel_negative_gold_label(text, *, context, control_id, kind):
    """Close the stock negative GPT color at widget end, without broad parser relaxation.

    Civ's TXT_KEY_TOP_PANEL_GOLD negative number subpattern injects a red
    COLOR span inside the yellow total-gold span, while its localized outer
    string contributes only one final close token. The remaining outer color
    has no following text in this exact GoldPerTurn label. Add a zero-width
    matching close only for this exact stock TopPanel shape; all other
    unbalanced markup still fails in ``markup``.
    """
    if (context != 'top-panel' or control_id != 'GoldPerTurn' or kind != 'TextButton' or
            type(text) is not str):
        return text
    match = _TOP_PANEL_NEGATIVE_GOLD.fullmatch(text)
    if match is None:
        return text
    return text + f"[{match.group(1)}]"


def align_wrapped_tints(source_text, source_tints, wrapped_text):
    """Carry original inline-color runs through the captured word-wrap result."""
    require(len(source_text) == len(source_tints),
            'Inline color runs do not match the pre-wrap source text')
    result = []
    cursor = 0
    for character in wrapped_text:
        # wrap_production_text inserts line breaks at word boundaries. Those
        # breaks have no authored tint of their own; preserve explicit source
        # newlines when present and leave inserted separators untinted.
        if character == '\n' and (cursor >= len(source_text) or source_text[cursor] != '\n'):
            result.append(None)
            continue
        while cursor < len(source_text) and source_text[cursor] != character:
            cursor += 1
        require(cursor < len(source_text),
                'Wrapped label text cannot be aligned to its original color runs')
        result.append(source_tints[cursor])
        cursor += 1
    return result


def inline_tab_glyph(font):
    """Explicit indentation convention; original retail tab stops are unmeasured."""
    space = font.glyphs.get(32)
    require(space is not None and space.abc_advance > 0, 'Tab indentation requires the exact GGXML space advance')
    return Glyph(9, 0, 0, 0, 0, 0, 4 * space.abc_advance, 0, 0, 0)


def wrap_production_text(text, font, inline_glyphs, wrap_width):
    """Reflow captured post-token text using only original GGXML ABC advances."""
    def advance(value):
        total = 0
        for index, char in enumerate(value):
            glyph = inline_glyphs.get(ord(char), font.glyphs.get(ord(char)))
            require(glyph is not None, f'Production text has no exact GGXML glyph U+{ord(char):04X} at {index}')
            total += glyph.abc_advance
        return total

    # The owned Lua layout contract uses WrapWidth=0 when the source XML has
    # no WrapWidth attribute. That means natural/unwrapped text width; it does
    # not mean a zero-pixel wrapping box. Keep explicit newlines and all
    # authored spaces intact in this mode.
    if wrap_width == 0:
        return [(line, advance(line)) for line in
                text.replace('\r\n', '\n').replace('\r', '\n').split('\n')]

    result = []
    # Split explicit newlines while preserving empty lines, then apply the
    # documented ASCII-space word-wrap and codepoint split for long tokens.
    for explicit in text.replace('\r\n', '\n').replace('\r', '\n').split('\n'):
        words = explicit.split(' ')
        current = ''
        for word_index, word in enumerate(words):
            if not word:
                continue
            fragments = []
            fragment = ''
            for char in word:
                candidate = fragment + char
                if fragment and advance(candidate) > wrap_width:
                    fragments.append(fragment)
                    fragment = char
                else:
                    fragment = candidate
            if fragment:
                fragments.append(fragment)
            for fragment_index, piece in enumerate(fragments):
                candidate = piece if not current else current + ' ' + piece
                if current and advance(candidate) > wrap_width:
                    result.append((current, advance(current)))
                    current = piece
                else:
                    current = candidate
                if fragment_index + 1 < len(fragments):
                    result.append((current, advance(current)))
                    current = ''
        result.append((current, advance(current)))
    return result


def xywh_dict(value, label):
    require(type(value) is dict and all(type(value.get(name)) in (int, float) and
            math.isfinite(value[name]) for name in ('x', 'y', 'width', 'height')) and
            value['width'] >= 0 and value['height'] >= 0,
            'Invalid ' + label + ' XYWH bounds')
    return (value['x'], value['y'], value['x'] + value['width'], value['y'] + value['height'])


def glyph_quad(glyph, font):
    # DDS pixel inspection establishes that the authored glyph masks extend
    # beyond GGXML width/height inside its spacing border (e.g. lower-case l).
    # Keep that border in the sampled quad without adding it to ABC advance.
    # The half-border placement is a candidate convention, not retail calibration.
    u, v, width, height = glyph.texture_rect
    require(0 <= font.spacing <= 32, 'Unbounded glyph atlas border')
    return (u, v, width + font.spacing, height + font.spacing), font.spacing / 2


def grid_targets(sizes, bounds):
    x, y, w, h = bounds
    ul, uc, ur, left, center, right, ll, lc, lr = [sizes[n] for n in ('UL', 'UC', 'UR', 'L', 'C', 'R', 'LL', 'LC', 'LR')]
    dimensions = ((ul[0], ul[1]), (w - ul[0] - ur[0], uc[1]), (ur[0], ur[1]),
                  (left[0], h - ul[1] - ll[1]), (w - left[0] - right[0], h - uc[1] - lc[1]),
                  (right[0], h - ur[1] - lr[1]), (ll[0], ll[1]),
                  (w - ll[0] - lr[0], lc[1]), (lr[0], lr[1]))
    positions = ((x, y), (x + ul[0], y), (x + w - ur[0], y),
                 (x, y + ul[1]), (x + left[0], y + uc[1]), (x + w - right[0], y + ur[1]),
                 (x, y + h - ll[1]), (x + ll[0], y + h - lc[1]), (x + w - lr[0], y + h - lr[1]))
    require(all(a >= 0 and b >= 0 for a, b in dimensions), 'Grid too small for original edge sizes')
    return [(px, py, px + sw, py + sh) for (px, py), (sw, sh) in zip(positions, dimensions)]


def scroll_mask_rgba(texture_pixels, texture_width, texture_height, mask_pixels, mask_width, mask_height,
                     width, height, phase, offset_x=0, offset_y=0):
    """Build a bounded nearest-sampled ScrollAnim candidate from original DDS pixels.

    ScrollAnim Size is the output/control size, while TextureOffset selects an
    origin in the foreground atlas. The remaining foreground image is sampled
    through a phase-positioned viewport, then stretched to Size; the full mask
    is stretched to the same output rectangle. This is an explicit frontend
    sampling policy, not a claim about retail shader/filter equivalence.
    """
    require(all(type(value) is int and value > 0 for value in
                (texture_width, texture_height, mask_width, mask_height, width, height)),
            'Invalid ScrollAnim source dimensions')
    require(width <= 32768 and height <= 32768 and width * height <= 16_777_216,
            'ScrollAnim output exceeds the bounded frontend raster limit')
    require(len(texture_pixels) == texture_width * texture_height * 4 and
            len(mask_pixels) == mask_width * mask_height * 4,
            'ScrollAnim source/mask payload size differs from DDS dimensions')
    require(type(phase) in (int, float) and math.isfinite(phase) and 0 <= phase <= 1,
            'ScrollAnim phase is outside the captured timeline')
    require(type(offset_x) is int and type(offset_y) is int, 'ScrollAnim TextureOffset is invalid')
    require(0 <= offset_x < texture_width and 0 <= offset_y < texture_height,
            'ScrollAnim TextureOffset escapes the original foreground texture')
    source_width = texture_width - offset_x
    source_height = texture_height - offset_y
    sample_height = min(height, source_height)
    out = bytearray(width * height * 4)
    travel = source_height - sample_height
    for y in range(height):
        sy = offset_y + int(math.floor(phase * travel + (y + 0.5) * sample_height / height))
        sy = min(texture_height - 1, sy)
        my = min(mask_height - 1, int((y + 0.5) * mask_height / height))
        for x in range(width):
            sx = offset_x + min(source_width - 1, int((x + 0.5) * source_width / width))
            mx = min(mask_width - 1, int((x + 0.5) * mask_width / width))
            source_at = (sy * texture_width + sx) * 4
            mask_at = (my * mask_width + mx) * 4
            dest_at = (y * width + x) * 4
            out[dest_at:dest_at + 3] = texture_pixels[source_at:source_at + 3]
            out[dest_at + 3] = (texture_pixels[source_at + 3] * mask_pixels[mask_at + 3] + 127) // 255
    return bytes(out)


def meter_arc_rgba(texture_pixels, width, height, percent, percent_plus=0):
    """Keep the source meter art in captured clockwise progress arcs from twelve o'clock."""
    require(type(width) is int and type(height) is int and width > 0 and height > 0 and
            len(texture_pixels) == width * height * 4, 'Invalid original Meter texture payload')
    require(all(type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 1
                for value in (percent, percent_plus)),
            'Meter fractions are outside the captured normalized range')
    out = bytearray(texture_pixels)
    cx, cy = width / 2, height / 2
    total = min(1.0, percent + percent_plus)
    for y in range(height):
        for x in range(width):
            dx, dy = x + .5 - cx, y + .5 - cy
            angle = (math.atan2(dx, -dy) / (2 * math.pi)) % 1.0
            if angle >= total:
                out[(y * width + x) * 4 + 3] = 0
    return bytes(out)


def _load_menu_original_controls(root, original, widget):
    """Match a complete frontend tree, including source-generated row templates."""
    static_ids, callback_keys = {}, set()
    templates = {element.get('Name'): element for element in original.findall('Instance')}
    require(set(templates) == {'LoadButton', 'ReferencedPackageInstance'},
            'LoadMenu original instance declarations changed')
    callback_ids = {'StartButton', 'Delete', 'Yes', 'No', 'BackButton', 'ShowModsButton',
                    'ShowDLCButton', 'CloseReferencedPackagesButton', 'AutoCheck', 'CloudCheck'}

    def match(node, element, *, generated=False):
        require(node.get('kind') == element.tag and node.get('id', '') == element.get('ID', '') and
                node.get('sourceAttributes') == dict(element.attrib),
                'Full LoadMenu control differs from its original kind/attributes: ' + element.get('ID', element.tag))
        control_id = element.get('ID')
        if not generated and control_id:
            require(control_id not in static_ids, 'Full LoadMenu has duplicate original control IDs')
            static_ids[control_id] = node
        if control_id in callback_ids or generated and control_id == 'Button' or element.tag in ('UpButton', 'DownButton'):
            callback_keys.add(node['key'])
        if element.tag == 'PullDown':
            require(node['key'] == widget['key'], 'Full LoadMenu has a foreign PullDown owner')
            return
        children = node['children']
        if node is root:
            children = [child for child in children if child.get('overlayOwnerKey') != widget['key']]
        if control_id in ('LoadFileButtonStack', 'ReferencedPackagesStack'):
            name = 'LoadButton' if control_id == 'LoadFileButtonStack' else 'ReferencedPackageInstance'
            records = list(templates[name])
            require(records and len(children) % len(records) == 0,
                    'Full LoadMenu dynamic stack has an incomplete original instance')
            for index, child in enumerate(children):
                match(child, records[index % len(records)], generated=True)
            return
        expected = [child for child in element if child.tag != 'Instance']
        require(len(children) == len(expected),
                'Full LoadMenu omitted or inserted an original child: ' + element.get('ID', element.tag))
        for child, source in zip(children, expected):
            match(child, source, generated=generated)

    match(root, original)
    return static_ids, callback_keys


def load_menu_controls_contract(snapshot, sources=None, *, closed=False):
    """Validate original control provenance without claiming an SDK load handoff."""
    require(type(snapshot) is dict and
            (snapshot.get('contextName'), snapshot.get('popupKind')) == ('LoadMenu', 'LoadMenu') and
            snapshot.get('active') is (not closed) and type(snapshot.get('timerSemaphore')) is int and
            snapshot['timerSemaphore'] == 0,
            'LoadMenu controls require their timer-free child context')
    lifecycle = snapshot.get('lifecycle')
    require(type(lifecycle) is list and bool(lifecycle) and
            all(event == 'queued' if index % 2 == 0 else event in ('closed', 'context-hidden:LoadMenu')
                for index, event in enumerate(lifecycle)) and
            (len(lifecycle) % 2 == (0 if closed else 1)) and
            snapshot.get('contextHidden') is closed,
            'LoadMenu controls have an invalid open/close lifetime')
    menu = snapshot.get('loadMenu')
    require(type(menu) is dict and menu.get('sourceBytesPreserved') is True and
            type(menu.get('controlOnly')) is bool and menu.get('nativeVmConnected') is False and
            menu.get('retailBackendVerified') is False and
            menu.get('runtimeIntegrationVerified') is False and
            menu.get('retailLayoutVerified') is False,
            'LoadMenu control evidence must disclose its unconnected native backend and retail boundary')
    full_frontend = menu['controlOnly'] is False
    require(menu.get('sourceApisBound') is True if full_frontend else
            menu.get('sourceApisBound') is None or menu.get('sourceApisBound') is False,
            'LoadMenu must distinguish its API-bound frontend candidate from a control-only fixture')
    if full_frontend:
        require(menu.get('frontendStatePolicy') ==
                'OWNED_LOCAL_INGAME_VIEW_OPAQUE_IDENTITY_NO_RETAIL_NUMERIC_ENUM_CLAIM' and
                menu.get('unsupportedActions') == (['cloud', 'automatic-save-filter']
                    if menu.get('localDeleteBackendBound') is True else ['cloud', 'delete', 'automatic-save-filter']),
                'LoadMenu API-bound frontend must retain its opaque state and unsupported-action boundary')
    references = {}
    for name, suffix in (('originalLua', 'Assets/UI/FrontEnd/LoadMenu.lua'),
                         ('originalXml', 'Assets/UI/FrontEnd/LoadMenu.xml')):
        row = menu.get(name)
        require(type(row) is dict and type(row.get('path')) is str and
                row['path'].replace('\\', '/').endswith('/' + suffix),
                'LoadMenu control source reference is missing: ' + name)
        path = Path(row['path']).resolve(strict=True)
        require(sha256(path) == row.get('sha256') and
                (sources is None or sources.get(path) == row['sha256']),
                'LoadMenu control source differs from the selected original: ' + name)
        references[name] = {'path': str(path), 'sha256': row['sha256']}
    root = snapshot.get('tree')
    require(type(root) is dict and root.get('kind') == 'Context' and
            (root.get('x'), root.get('y'), root.get('width'), root.get('height')) == (0, 0, 1920, 1080),
            'LoadMenu controls lost their complete logical viewport')
    nodes = list(economic_walk(root))
    keys = [node.get('key') for node in nodes]
    require(all(type(key) is int and key > 0 for key in keys) and len(set(keys)) == len(keys),
            'LoadMenu controls have missing or duplicate retained keys')
    pulldowns = [node for node in nodes if node.get('kind') == 'PullDown']
    original_root = ET.parse(references['originalXml']['path']).getroot()
    original = original_root.find('.//PullDown')
    require(len(pulldowns) == 1 and original is not None and
            pulldowns[0].get('id') == 'SortByPullDown' and
            pulldowns[0].get('sourceAttributes') == dict(original.attrib),
            'LoadMenu sorting control differs from its original XML declaration')
    owner_key = pulldowns[0]['key']
    overlays = [node for node in nodes if node.get('overlayOwnerKey') == owner_key]
    require(len(overlays) <= 1 and
            (not overlays or root['children'][-1] is overlays[0]),
            'PullDown popup must be projected exactly once after the original root children')
    opened = bool(overlays and not overlays[0].get('hidden', True))
    states = snapshot.get('pullDowns')
    require(type(states) is list and len(states) == 1 and type(states[0]) is dict,
            'LoadMenu control snapshot lacks its unique PullDown state')
    widget = states[0]
    by_key = {node['key']: node for node in nodes}
    require(widget.get('key') == owner_key and widget.get('opened') is opened and
            widget.get('style') == 'GenericPullDown' and
            widget.get('geometryPolicy') == 'ZEROSIS_ORIGINAL_GENERIC_PULL_DOWN_COMPOSITE_CANDIDATE_V1' and
            widget.get('retailGeometryVerified') is False and
            widget.get('retailWidgetBehaviorVerified') is False,
            'LoadMenu PullDown state or unverified retail boundary disagrees with its retained tree')
    for field, kind, data_kind in (('buttonKey', 'GridButton', 'ButtonData'),
                                    ('popupKey', 'Grid', 'GridData'),
                                    ('scrollPanelKey', 'ScrollPanel', 'ScrollPanelData'),
                                    ('stackKey', 'Stack', 'StackData')):
        node = by_key.get(widget.get(field))
        require(node is not None and node.get('kind') == kind and
                node.get('originalDataKind') == data_kind and node.get('ownerPullDownKey') == owner_key,
                'PullDown composite lost an original style block: ' + field)
    require(not opened or widget['popupKey'] == overlays[0]['key'],
            'PullDown overlay differs from its original popup control')
    style_ref = widget.get('originalStyleSource')
    require(type(style_ref) is dict and
            style_ref.get('path', '').replace('\\', '/').endswith('Assets/UI/Styles.xml') and
            (sources is None or any(path.as_posix().endswith('/Assets/UI/Styles.xml') and digest == style_ref.get('sha256')
                                    for path, digest in sources.items())),
            'PullDown style provenance differs from the selected original Styles.xml')
    style_path = Path(references['originalXml']['path']).parents[1] / 'Styles.xml'
    require(sha256(style_path) == style_ref.get('sha256'), 'PullDown original style bytes changed')
    style_xml = ET.parse(style_path).getroot().find('GenericPullDown')
    require(style_xml is not None, 'Original GenericPullDown style is missing')
    mapped_kinds = {'GridData': 'Grid', 'ScrollPanelData': 'ScrollPanel', 'StackData': 'Stack'}
    generated_nodes = [*economic_walk(by_key[widget['buttonKey']]), *economic_walk(by_key[widget['popupKey']])]
    for node in generated_nodes:
        origin = node.get('styleChildSource')
        require(type(origin) is dict and origin.get('ownerPullDownKey') == owner_key and
                set(origin) == {'style', 'ownerKey', 'path', 'sha256', 'indices', 'ownerPullDownKey'} and
                origin.get('style') == 'GenericPullDown' and origin.get('ownerKey') == owner_key and
                origin.get('path') == 'Assets/UI/Styles.xml' and origin.get('sha256') == style_ref['sha256'] and
                type(origin.get('indices')) is list and bool(origin['indices']),
                'PullDown generated control lacks exact original style provenance')
        source = style_xml
        for index in origin['indices']:
            require(type(index) is int and 1 <= index <= len(source), 'PullDown style child path escapes its source')
            source = source[index - 1]
        require(node.get('kind') == mapped_kinds.get(source.tag, source.tag) and
                node.get('sourceAttributes') == dict(source.attrib),
                ('PullDown caption differs from the original 200x24 ZoomButton cell'
                 if source.tag == 'GridButton' and node.get('originalDataKind') == 'InstanceData' else
                 'PullDown generated control differs from its original style kind/attributes'))
    require([node['key'] for node in pulldowns[0]['children']] ==
            ([widget['buttonKey']] if opened else [widget['buttonKey'], widget['popupKey']]) and
            [node['key'] for node in by_key[widget['popupKey']]['children']] == [widget['scrollPanelKey']] and
            by_key[widget['scrollPanelKey']]['children'][-1]['key'] == widget['stackKey'] and
            len(by_key[widget['scrollPanelKey']]['children']) == 4 and
            [node['key'] for node in by_key[widget['stackKey']]['children']] == widget.get('entryKeys'),
            'PullDown composite ownership or original entry order changed')
    static_ids, callback_keys = _load_menu_original_controls(root, original_root, widget) if full_frontend else ({}, set())
    modal = None
    consumers = set()
    deletion = {'implemented': False, 'bound': False, 'selected': False, 'armed': False}
    if full_frontend:
        deletion = _local_save_delete_contract(menu, static_ids['DeleteConfirm'], closed=closed)
        if deletion['bound'] and not closed:
            require(static_ids['Delete']['disabled'] is (not deletion['selected']) and
                    static_ids['Yes']['disabled'] is (not deletion['armed']),
                    'LoadMenu delete/Yes eligibility differs from its original confirmation')
        elif not deletion['bound']:
            require(static_ids['Delete']['disabled'] and static_ids['Yes']['disabled'],
                    'LoadMenu deletion requires its optional owned-file backend')
        for control_id in ('DeleteConfirm', 'ReferencedPackagesWindow'):
            node = static_ids[control_id]
            require(node.get('kind') == 'Box' and node['sourceAttributes'].get('ConsumeMouseOver') == '1' and
                    (node['x'], node['y'], node['width'], node['height']) == (0, 0, 1920, 1080),
                    'LoadMenu modal lost its original full-screen barrier')
            if not node['hidden']:
                modal = node
        if modal is not None:
            require(not opened, 'LoadMenu modal cannot retain an overlapping open PullDown')
        if not closed and not opened:
            original_styles = {element.tag: dict(element.attrib) for element in ET.parse(style_path).getroot()}

            def source_consumers(node, parent_visible=True, clip=(0, 0, 1920, 1080), in_modal=False):
                visible = parent_visible and not node.get('hidden', True)
                in_modal = in_modal or node is modal
                source = node.get('sourceAttributes', {})
                effective = {**original_styles.get(source.get('Style'), {}), **source}
                bounds = rect(tuple(node[field] for field in ('x', 'y', 'width', 'height')))
                clipped = intersect(bounds, clip)
                # The original central Grid consumes input independently of
                # BGBlock. Callback buttons retain their own ConsumeMouse bit.
                source_barrier = (node.get('kind') in ('Box', 'Grid') and
                                  (effective.get('ConsumeMouse') == '1' or node is modal))
                if source_barrier and visible and positive(clipped) and (modal is None or in_modal):
                    require(node.get('disabled') is False and
                            (node is modal or node['attributes'].get('ConsumeMouse') == '1'),
                            'LoadMenu original input consumer changed its enabled/style contract')
                    consumers.add(node['key'])
                child_clip = intersect(bounds, clip) if node.get('kind') == 'ScrollPanel' else clip
                for child in node['children']:
                    source_consumers(child, visible, child_clip, in_modal)

            source_consumers(root)
        callback_keys.update([widget['buttonKey'], *widget.get('entryKeys', [])])
    targets = snapshot.get('inputTargets')
    require(type(targets) is list and all(type(target) is dict for target in targets),
            'LoadMenu controls lack captured input targets')
    dismiss = [target for target in targets if target.get('inputRole') == 'PullDownDismiss']
    require(len(dismiss) == (1 if opened and not closed else 0) and
            (not dismiss or targets[0] is dismiss[0] and dismiss[0].get('key') == root['key']),
            'PullDown outside-click barrier is missing, duplicated or ordered above its popup')
    if opened:
        popup_keys = {node['key'] for node in economic_walk(overlays[0])}
        popup_keys.update(node['key'] for node in economic_walk(by_key[widget['buttonKey']]))
        require(all(target.get('key') in popup_keys or target is dismiss[0] for target in targets),
                'Opened PullDown exposes an underlying control callback')
    if full_frontend:
        allowed_modal_keys = {node['key'] for node in economic_walk(modal)} if modal is not None else None
        require(all(target.get('key') in by_key and target.get('visible') is True and
                    target.get('disabled') is False and by_key[target['key']].get('disabled') is False and
                    target.get('event') in ('LeftClick', 'ConsumeMouse') and
                    (target.get('event') == 'ConsumeMouse' or target.get('inputRole') == 'PullDownDismiss' or
                     target.get('key') in callback_keys) and
                    (allowed_modal_keys is None or target.get('key') in allowed_modal_keys)
                    for target in targets),
                'Full LoadMenu exposes a foreign callback or input behind its active modal')
        actual_consumers = {target.get('key') for target in targets if target.get('event') == 'ConsumeMouse'}
        require(actual_consumers == ({widget['popupKey']} if opened and not closed else consumers),
                'Full LoadMenu lacks its exact original background/modal input consumer')
    return {'original_sources': references, 'pull_down_key': owner_key, 'opened': opened,
            'widget_state': widget,
            'popup_bounds': rect((by_key[widget['popupKey']]['x'], by_key[widget['popupKey']]['y'],
                                  by_key[widget['popupKey']]['width'], by_key[widget['popupKey']]['height'])),
            'dismiss_key': root['key'] if dismiss else None,
            'input_order_keys': [target.get('key') for target in targets],
            'source_api_bound_candidate': full_frontend, 'full_original_tree_matched': full_frontend,
            'modal_key': modal['key'] if modal is not None else None,
            'modal_input_keys': sorted(node['key'] for node in economic_walk(modal)) if modal is not None else [],
            'consume_mouse_keys': sorted(consumers),
            'native_load_handoff_verified': False, 'retail_geometry_verified': False,
            'local_delete_implemented': deletion['implemented'], 'local_delete_backend_bound': deletion['bound'],
            'local_delete_confirmation_armed': deletion['armed'], 'native_delete_verified': False}


def owned_font_root(root):
    root = Path(root)
    require(root.is_absolute() and root.parent.name == 'SharedUiFontInputs' and
            root.parent.parent.name == 'Build' and re.fullmatch('[0-9a-f]{64}', root.name),
            'Font root is not a content-addressed engine-owned cache')
    require(root.resolve(strict=True) == root and root.is_dir() and
            all(not path.lstat().st_file_attributes & 0x400 for path in (root, *root.parents)),
            'Owned font root contains a reparse point')
    return root


def owned_font_input_binding(prepared):
    """Read the frozen preparation contract, never the mutable source profile."""
    require(type(prepared) is dict, 'Prepared UI input is not an object')
    metadata, bank = prepared.get('font_input_profile'), prepared.get('shared_font_metrics')
    if 'font_input_profile' not in prepared and 'shared_font_metrics' not in prepared:
        return None
    require(type(metadata) is dict and type(bank) is dict and
            metadata.get('input_storage') == 'CONTENT_ADDRESSED_ENGINE_OWNED_FONT_INPUTS' and
            bank.get('schema') == 'zerosis.ui.shared_font_metrics.v1' and
            type(metadata.get('profile_id')) is str and re.fullmatch('[0-9a-f]{64}', metadata['profile_id']) and
            bank.get('profileId') == metadata['profile_id'] and type(metadata.get('asset_root')) is str,
            'Owned font profile or shared bank differs')
    root = owned_font_root(metadata.get('asset_root', ''))
    compiled = prepared.get('compiled_assets')
    require(type(compiled) is dict and type(compiled.get('path')) is str, 'Prepared UI header provenance is missing')
    header = Path(compiled['path'])
    require(header.is_absolute() and header.name == 'UiPopupAssets.generated.h' and
            header.parent.name == 'Host' and header.parent.parent.name == 'Source' and
            root.parent == header.parents[2] / 'Build/SharedUiFontInputs', 'Font cache escaped its original engine project')
    rows = metadata.get('original_inputs')
    require(type(rows) is list and len(rows) == 15, 'Owned font profile needs exactly15 inputs')
    expected = {'Assets/UI/ColorAtlas.xml'}
    expected.update('Assets/UI/Fonts/Tw Cent MT/TwCenMT%d.ggxml' % size for size in (14, 16, 18, 20, 22, 24))
    expected.update('kTwCenMT%d%s.dds' % (size, suffix) for size in (14, 18, 20, 22) for suffix in ('', 'Shadow'))
    inputs, inventory, glyph_hashes = {}, [], set()
    for row in rows:
        require(type(row) is dict and set(row) == {'path', 'bytes', 'sha256'} and
                type(row['path']) is str and type(row['bytes']) is int and row['bytes'] > 0 and
                type(row['sha256']) is str and re.fullmatch('[0-9a-f]{64}', row['sha256']), 'Malformed owned font input')
        path = Path(row['path'])
        require(path.is_absolute() and path.is_relative_to(root) and path.resolve(strict=True) == path and
                path.is_file() and not path.lstat().st_file_attributes & 0x400, 'Owned font input escaped its cache')
        relative = path.relative_to(root).as_posix()
        require(relative in expected and relative not in inputs and path.stat().st_size == row['bytes'] and
                sha256(path) == row['sha256'], 'Owned font input is duplicate, missing or changed')
        inputs[relative] = dict(row)
        inventory.append((relative, row['bytes'], row['sha256']))
        if path.suffix == '.ggxml':
            glyph_hashes.add(row['sha256'])
    require(set(inputs) == expected and
            hashlib.sha256(json.dumps(sorted(inventory), separators=(',', ':'), ensure_ascii=True).encode('ascii')).hexdigest() == root.name,
            'Owned font content address differs from its complete selected inputs')
    require(type(bank.get('glyphSets')) is dict and set(bank['glyphSets']) == glyph_hashes and
            all(type(value) is dict and value for value in bank['glyphSets'].values()), 'Shared font glyph set inventory differs')
    return dict(schema='zerosis.ui.owned_font_binding.v1', asset_root=str(root), profile_id=metadata['profile_id'],
                cache_content_id=root.name, inputs=[inputs[name] for name in sorted(inputs)])


class Compiler:
    def __init__(self, game_root, destination, *, width=1920, height=1080, inline_colors=None,
                 inline_icons=None, context='ranking', snapshot_clock=0,
                 city_view_layout_variant='default', unit_panel_layout_variant='default',
                 economic_overview_prepared=None, font_root=None, font_binding=None):
        require((width, height) == (1920, 1080), 'Selected popup currently requires the verified 1920x1080 viewport')
        self.game_root = Path(game_root).resolve(strict=True)
        self.destination = candidate_directory(destination, self.game_root)
        self.font_root = self.game_root if font_root is None else owned_font_root(font_root)
        require(font_root is None or not self.destination.is_relative_to(self.font_root.parent),
                'Scene output must stay outside the owned font cache')
        self.font_input_refs = {}
        if font_root is not None:
            require(type(font_binding) is dict and font_binding.get('schema') == 'zerosis.ui.owned_font_binding.v1' and
                    Path(font_binding.get('asset_root', '')) == self.font_root and
                    font_binding.get('cache_content_id') == self.font_root.name and
                    type(font_binding.get('profile_id')) is str and re.fullmatch('[0-9a-f]{64}', font_binding['profile_id']) and
                    type(font_binding.get('inputs')) is list and len(font_binding['inputs']) == 15,
                    'Owned font root requires its exact frozen input binding')
            inventory = []
            for row in font_binding['inputs']:
                require(type(row) is dict and set(row) == {'path', 'bytes', 'sha256'} and type(row['path']) is str and
                        type(row['bytes']) is int and row['bytes'] > 0 and type(row['sha256']) is str and
                        re.fullmatch('[0-9a-f]{64}', row['sha256']), 'Malformed compiler font binding')
                source = Path(row['path'])
                require(source.is_relative_to(self.font_root) and source not in self.font_input_refs,
                        'Compiler font binding escaped or duplicated an input')
                self.font_input_refs[source] = dict(row)
                inventory.append((source.relative_to(self.font_root).as_posix(), row['bytes'], row['sha256']))
            require(hashlib.sha256(json.dumps(sorted(inventory), separators=(',', ':'), ensure_ascii=True).encode('ascii')).hexdigest() == self.font_root.name,
                    'Compiler font binding differs from its content address')
        else:
            require(font_binding is None, 'Font binding must select its owned font root')
        self.width, self.height = width, height
        require(context == 'ranking' or context in SCENE_CONTEXTS, 'Unsupported selected UI context')
        require(type(snapshot_clock) in (int, float) and math.isfinite(snapshot_clock) and snapshot_clock >= 0,
                'Invalid selected presentation clock')
        require(city_view_layout_variant in ('default', 'small') and
                (context == 'city-view' or city_view_layout_variant == 'default'),
                'Invalid CityView layout variant for the selected UI context')
        require(unit_panel_layout_variant in ('default', 'small') and
                (context == 'unit-panel' or unit_panel_layout_variant == 'default'),
                'Invalid UnitPanel layout variant for the selected UI context')
        self.context, self.snapshot_clock = context, snapshot_clock
        self.economic_overview_prepared = economic_overview_prepared
        self.economic_overview_snapshot = self.economic_overview_scene = None
        self.action_info_panel_scene = None
        self.notification_panel_scene = None
        self.game_menu_scene = None
        self.exit_confirm_scene = None
        self.save_menu_scene = None
        self.load_menu_scene = None
        self.private_menu_scene = None
        self.pantheon_scene = None
        self.goody_hut_reward_scene = None
        self.economic_slot_keys, self.economic_context_keys = set(), set()
        self.economic_bar_sources, self.economic_button_sources = {}, {}
        self.city_view_layout_variant = city_view_layout_variant if context == 'city-view' else None
        self.unit_panel_layout_variant = unit_panel_layout_variant if context == 'unit-panel' else None
        self.inline_colors = dict(inline_colors or {})
        self.inline_icons = dict(inline_icons or {})
        self.assets = UiAssets(self.game_root)
        self.styles_path = self.game_root / 'Assets/UI/Styles.xml'
        self.styles_hash = sha256(self.styles_path)
        layout_relative = {'production': 'Assets/DLC/Expansion2/UI/InGame/Popups/ProductionPopup.xml',
                           'research': 'Assets/DLC/Expansion2/UI/InGame/TechPopup.xml',
                           'research-tree': 'Assets/DLC/Expansion2/UI/InGame/TechTree/TechTree.xml',
                           'tech-award': 'Assets/DLC/Expansion2/UI/InGame/Popups/TechAwardPopup.xml',
                           'goody-hut-reward': 'Assets/DLC/Expansion2/UI/InGame/Popups/GoodyHutPopup.xml',
                           'ranking': 'Assets/DLC/Expansion2/UI/InGame/Popups/WhosWinningPopup.xml',
                           'city-capture': 'Assets/UI/InGame/Popups/GenericPopup.xml',
                           'diplomacy': 'Assets/DLC/Expansion2/UI/InGame/LeaderHead/LeaderHeadRoot.xml',
                           'declare-war': 'Assets/DLC/Expansion2/UI/InGame/Popups/DeclareWarPopup.xml',
                           'city-view': ('Assets/DLC/Expansion2/UI/InGame/CityView/CityView_small.xml'
                                         if city_view_layout_variant == 'small' else
                                         'Assets/DLC/Expansion2/UI/InGame/CityView/CityView.xml'),
                           'unit-panel': ('Assets/DLC/Expansion2/UI/InGame/WorldView/UnitPanel_small.xml'
                                          if unit_panel_layout_variant == 'small' else
                                          'Assets/DLC/Expansion2/UI/InGame/WorldView/UnitPanel.xml'),
                           'top-panel': 'Assets/DLC/Expansion2/UI/InGame/TopPanel.xml',
                           'trade-route': 'Assets/DLC/Expansion2/UI/InGame/Popups/TradeRouteOverview.xml',
                           'social-policy': 'Assets/DLC/Expansion2/UI/InGame/Popups/SocialPolicyPopup.xml',
                            'pantheon': 'Assets/DLC/Expansion2/UI/InGame/Popups/ChoosePantheonPopup.xml',
                           'economic-overview': 'Assets/DLC/Expansion2/UI/InGame/Popups/EconomicOverview.xml',
                           'action-info-panel': 'Assets/DLC/Expansion2/UI/InGame/WorldView/ActionInfoPanel.xml',
                           'notification-panel': 'Assets/DLC/Expansion2/UI/InGame/WorldView/NotificationPanel.xml',
                           'game-menu': 'Assets/DLC/Expansion2/UI/InGame/Menus/GameMenu.xml',
                            'exit-confirm': 'Assets/UI/FrontEnd/ExitConfirm.xml',
                           'save-menu': 'Assets/UI/InGame/Menus/SaveMenu.xml',
                           'load-menu': 'Assets/UI/FrontEnd/LoadMenu.xml',
                           'menu-options': 'Assets/UI/Options/OptionsMenu.xml',
                           'touch-help': 'Assets/UI/TouchControlsMenu.xml',
                           'map-menu': 'Assets/UI/InGame/Menus/SaveMapMenu.xml'}[context]
        self.layout_path = self.game_root / layout_relative
        self.unit_panel_consume_sources = set()
        self.top_panel_consume_source_count = 0
        self.top_panel_source_ids = set()
        self.top_panel_source_contract = None
        self.top_panel_interaction_contract = None
        if context in ('unit-panel', 'top-panel'):
            unit_panel_root = ET.parse(self.layout_path).getroot()
            require(unit_panel_root.tag == 'Context', 'Selected original world-overlay layout has no Context root')
            self.unit_panel_consume_sources = {
                (element.tag, element.attrib.get('ID', ''))
                for element in unit_panel_root.iter()
                if element.attrib.get('ConsumeMouse') in ('1', 'true')}
            if context == 'unit-panel':
                require(self.unit_panel_consume_sources,
                        'Selected original UnitPanel layout has no ConsumeMouse controls')
            else:
                self.top_panel_source_ids = {element.attrib['ID'] for element in unit_panel_root.iter()
                                             if element.attrib.get('ID')}
                required_ids = {'SciencePerTurn', 'GoldPerTurn', 'InternationalTradeRoutes',
                                'HappinessString', 'GoldenAgeString', 'CultureString', 'TourismString',
                                'FaithString', 'ResourceString', 'MenuButton', 'CivilopediaButton',
                                'CurrentDate', 'CurrentTurn'}
                require(required_ids <= self.top_panel_source_ids and
                        sum(element.tag == 'ToolTipType' and
                            element.attrib.get('Name') == 'TooltipTypeTopPanel'
                            for element in unit_panel_root.iter()) == 1 and
                        len(self.unit_panel_consume_sources) >= 1,
                        'Original TopPanel XML control, tooltip, or ConsumeMouse contract differs')
                self.top_panel_consume_source_count = sum(
                    element.attrib.get('ConsumeMouse') in ('1', 'true')
                    for element in unit_panel_root.iter())
                require(self.top_panel_consume_source_count >= 2,
                        'Original TopPanel XML lost its two mouse-consuming bar images')
        self.leader_button_sources = {}
        if context == 'diplomacy':
            leader_root = ET.parse(self.layout_path).getroot()
            require(leader_root.tag == 'Context' and leader_root.attrib.get('Name') == 'LeaderHeadRoot',
                    'Selected diplomacy layout is not original LeaderHeadRoot')
            button_ids = {'BackButton', 'DiscussButton', 'DemandButton', 'TradeButton', 'WarButton'}
            self.leader_button_sources = {
                element.attrib['ID']: dict(element.attrib)
                for element in leader_root.iter('GridButton')
                if element.attrib.get('ID') in button_ids}
            require(set(self.leader_button_sources) == button_ids and
                    all('String' in self.leader_button_sources[name] for name in button_ids),
                    'Original LeaderHeadRoot direct button text contract differs from the selected XML')
        self.script_path = (self.game_root / 'Assets/UI/FrontEnd/ExitConfirm.lua'
                            if context == 'exit-confirm' else
                            self.game_root / 'Assets/UI/InGame/Popups/TechAwardPopup.lua'
                            if context == 'tech-award' else
                            self.game_root / 'Assets/UI/InGame/Menus/GameMenu.lua'
                            if context == 'game-menu' else
                            self.game_root / 'Assets/UI/InGame/Popups/EconomicOverview.lua'
                            if context == 'economic-overview' else
                            self.game_root / 'Assets/DLC/Expansion2/UI/TechTree/TechTree.lua'
                            if context == 'research-tree' else
                            self.game_root / 'Assets/DLC/Expansion2/UI/InGame/PopupsGeneric/PuppetCityPopup.lua'
                            if context == 'city-capture' else
                            self.game_root / 'Assets/DLC/Expansion2/UI/InGame/CityView/CityView.lua'
                            if context == 'city-view' else
                            self.game_root / 'Assets/DLC/Expansion2/UI/InGame/WorldView/UnitPanel.lua'
                           if context == 'unit-panel' else self.layout_path.with_suffix('.lua'))
        if context == 'declare-war':
            self.script_path = self.game_root / 'Assets/DLC/Expansion2/UI/InGame/Popups/DeclareWarPopup.lua'
        self.context_sources = {self.layout_path: sha256(self.layout_path), self.script_path: sha256(self.script_path)}
        if context in ('pantheon', 'goody-hut-reward'):
            self.context_sources[self.styles_path] = self.styles_hash
        self.load_menu_checkbox_defaults = {}
        if context == 'load-menu':
            from civ5_ui_assets import observed_load_menu_check_defaults
            self.load_menu_checkbox_defaults = observed_load_menu_check_defaults(
                self.styles_path, self.layout_path, self.assets)
        if context in ('game-menu', 'load-menu', 'exit-confirm', *PRIVATE_MENU_CONTEXTS):
            self.context_sources[self.styles_path] = self.styles_hash
        if context in ('save-menu', 'load-menu'):
            self.context_sources[self.styles_path] = self.styles_hash
            unique_bonuses = self.game_root / 'Assets/UI/FrontEnd/GameSetup/UniqueBonuses.lua'
            self.context_sources[unique_bonuses] = sha256(unique_bonuses)
        if context == 'economic-overview':
            economic_proof = validate_economic_overview_prepared(economic_overview_prepared, verify_files=True)
            for slot, (_, _, layout, base) in ECONOMIC_SPECS.items():
                row = economic_proof['parent'] if slot == 'parent' else economic_proof['children'][slot]
                for field in ('lua', 'xml'):
                    source = Path(row[field]['path']).resolve(strict=True)
                    require(source.is_relative_to(self.game_root),
                            'EconomicOverview source is outside the selected original game directory')
                    self.context_sources[source] = row[field]['sha256']
                for node in economic_walk(economic_overview_prepared['xml_control_trees'][layout]):
                    attrs = node['attributes']
                    if node['kind'] == 'Bar':
                        self.economic_bar_sources[(base, attrs.get('ID'))] = attrs
                    if node['kind'] == 'Button' and attrs.get('String'):
                        self.economic_button_sources[(base, attrs.get('ID'))] = attrs
        self.trade_route_source_contract = None
        self.trade_route_state = None
        self.trade_route_snapshot_state = None
        if context == 'trade-route':
            helper_path = self.game_root / 'Assets/DLC/Expansion2/UI/InGame/Popups/TradeRouteHelpers.lua'
            self.context_sources[helper_path] = sha256(helper_path)
            root = ET.parse(self.layout_path).getroot()
            require(root.tag == 'Context', 'TradeRouteOverview source has no Context root')
            templates = [node for node in root.findall('Instance') if node.attrib.get('Name') == 'TRInstance']
            template = templates[0] if len(templates) == 1 else None
            require(template is not None, 'Original TradeRouteOverview must define exactly one TRInstance row template')
            template_ids = {node.attrib['ID'] for node in template.iter() if node.attrib.get('ID')}
            expected_row_ids = {'Root', 'Domain_Land', 'Domain_Sea', 'FromCivIconBG', 'FromCivIconShadow',
                                'FromCivIcon', 'FromCivIconHighlight', 'FromCity', 'ToCivIconBG',
                                'ToCivIconShadow', 'ToCivIcon', 'ToCivIconHighlight', 'ToCity', 'FromGPT',
                                'ToGPT', 'FromScience', 'ToScience', 'ToFood', 'ToProduction',
                                'FromReligion', 'ToReligion', 'TurnsLeft', 'Divider'}
            require(template_ids == expected_row_ids,
                    'Original TradeRoute TRInstance control IDs differ from the retained row contract')
            tab_ids = {'TabButtonYourTR', 'TabButtonAvailableTR', 'TabButtonTRWithYou'}
            sort_ids = {'Domain', 'FromOwnerHeader', 'FromCityHeader', 'ToOwnerHeader', 'ToCityHeader',
                        'FromGPT', 'ToGPT', 'FromScience', 'ToScience', 'ToFood', 'ToProduction',
                        'FromReligion', 'ToReligion', 'TurnsLeft'}
            controls = {node.attrib.get('ID'): node for node in root.iter() if node.attrib.get('ID')}
            require(tab_ids | sort_ids | {'CloseButton', 'MainScroll', 'MainScrollBar', 'MainStack'} <= controls.keys(),
                    'Original TradeRoute tabs, sort headers, close, or scroll controls changed')
            require(all(controls[name].tag == 'Button' and controls[name].attrib.get('String')
                        for name in tab_ids),
                    'Original TradeRoute tabs no longer carry direct Button String captions')
            self.trade_route_tab_sources = {name: dict(controls[name].attrib) for name in tab_ids}
            require(controls['MainScroll'].tag == 'ScrollPanel' and
                    controls['MainScroll'].attrib.get('Vertical') == '1' and
                    controls['MainStack'].tag == 'Stack' and controls['MainScrollBar'].tag == 'ScrollBar',
                    'Original TradeRoute MainScroll is no longer its vertical row viewport')
            source_script = self.script_path.read_text(encoding='utf-8-sig')
            compact = re.sub(r'\s+', '', source_script)
            helper_text = helper_path.read_text(encoding='utf-8-sig')
            require('include("TradeRouteHelpers");' in compact and
                    'ContextPtr:BuildInstanceForControl("TRInstance",instance,Controls.MainStack);' in compact and
                    'Controls.MainStack:CalculateSize();' in compact and
                    'Controls.MainScroll:CalculateInternalSize();' in compact and
                    all(f'Controls.{name}:RegisterCallback(Mouse.eLClick' in compact for name in tab_ids) and
                    all(f'Button=Controls.{name}' in compact for name in sort_ids) and
                    'Controls.CloseButton:RegisterCallback(Mouse.eLClick,OnClose);' in compact and
                    'function BuildTradeRouteToolTipString' in helper_text,
                    'Original TradeRoute tabs, sorting, dynamic rows, close, or helper contract changed')
            self.trade_route_source_contract = {
                'layout_source': {'path': str(self.layout_path.resolve()), 'sha256': self.context_sources[self.layout_path]},
                'script_source': {'path': str(self.script_path.resolve()), 'sha256': self.context_sources[self.script_path]},
                'helper_source': {'path': str(helper_path.resolve()), 'sha256': self.context_sources[helper_path]},
                'row_template': 'TRInstance', 'row_control_ids': sorted(template_ids),
                'tab_control_ids': sorted(tab_ids), 'sortable_header_ids': sorted(sort_ids),
                'close_control_id': 'CloseButton', 'scroll_panel_id': 'MainScroll',
                'scrollbar_control_id': 'MainScrollBar', 'row_stack_id': 'MainStack',
                'tooltips': 'original per-control runtime strings retained as metadata; renderer does not rasterize tooltip popovers',
                'retail_pixels_verified': False,
            }
        self.social_policy_source_contract = None
        self.social_policy_state = None
        if context == 'social-policy':
            self.context_sources[self.styles_path] = self.styles_hash
            root = ET.parse(self.layout_path).getroot()
            require(root.tag == 'Context', 'Original SocialPolicyPopup layout has no Context root')
            controls = {element.attrib['ID']: element for element in root.iter()
                        if element.attrib.get('ID')}
            required = {'TabButtonSocialPolicies', 'TabButtonSocialPoliciesHL',
                        'TabButtonIdeologies', 'TabButtonIdeologiesHL', 'SocialPolicyPane',
                        'IdeologyPane', 'PolicyInfo', 'CloseButton', 'PolicyConfirm', 'Yes', 'No',
                        'ChooseTenet', 'TenetStack', 'TenetCancelButton', 'TenetConfirm',
                        'TenetConfirmYes', 'TenetConfirmNo', 'ChangeIdeologyConfirm',
                        'ChangeIdeologyConfirmYes', 'ChangeIdeologyConfirmNo'}
            scroll_panels = [node for node in root.iter('ScrollPanel')]
            require(required <= controls.keys() and len(scroll_panels) >= 9 and
                    all(controls[name].tag == 'Button' and controls[name].attrib.get('String')
                        for name in ('TabButtonSocialPolicies', 'TabButtonIdeologies')) and
                    controls['PolicyInfo'].tag == 'CheckBox' and
                    all(controls[name].tag == 'GridButton' for name in
                        ('CloseButton', 'Yes', 'No', 'TenetConfirmYes', 'TenetConfirmNo',
                         'ChangeIdeologyConfirmYes', 'ChangeIdeologyConfirmNo', 'TenetCancelButton')) and
                    all(node.attrib.get('Vertical') == '1' for node in scroll_panels),
                    'Original SocialPolicy tabs, advanced-view checkbox, modal buttons or vertical policy scroll panels changed')
            compact = re.sub(r'\s+', '', self.script_path.read_text(encoding='utf-8-sig'))
            required_lua = ('g_Tabs["SocialPolicies"]', 'g_Tabs["Ideologies"]',
                            'functionPolicySelected(', 'functionPolicyBranchSelected(',
                            'player:HasPolicy(', 'player:CanAdoptPolicy(',
                            'player:CanUnlockPolicyBranch(', 'Controls.PolicyConfirm:SetHide(false)',
                            'Controls.Yes:RegisterCallback(Mouse.eLClick',
                            'Controls.No:RegisterCallback(Mouse.eLClick',
                            'functionOnClose(', 'Controls.CloseButton:RegisterCallback(Mouse.eLClick')
            require(all(token in compact for token in required_lua),
                    'Original SocialPolicy Lua lost policy selection, adoption confirmation, tabs or close callback contract')
            self.social_policy_source_contract = {
                'layout_source': {'path': str(self.layout_path.resolve()),
                                  'sha256': self.context_sources[self.layout_path]},
                'script_source': {'path': str(self.script_path.resolve()),
                                  'sha256': self.context_sources[self.script_path]},
                'tab_control_ids': ['TabButtonSocialPolicies', 'TabButtonIdeologies'],
                'branch_scroll_panel_count': len(scroll_panels),
                'policy_info_control_id': 'PolicyInfo',
                'confirmation_control_ids': ['PolicyConfirm', 'TenetConfirm',
                                             'ChangeIdeologyConfirm', 'ChooseTenet'],
                'close_control_id': 'CloseButton',
                'original_input_targets_only': True,
                'retail_pixels_verified': False,
            }
            self.social_policy_tab_sources = {name: dict(controls[name].attrib)
                                              for name in ('TabButtonSocialPolicies', 'TabButtonIdeologies')}
        if context == 'top-panel':
            source_script = self.script_path.read_text(encoding='utf-8-sig')
            compact_script = re.sub(r'\s+', '', source_script)
            require('Controls.SciencePerTurn:RegisterCallback(Mouse.eLClick,OnTechClicked);' in compact_script and
                    'Events.SerialEventGameMessagePopup({Type=ButtonPopupTypes.BUTTONPOPUP_TECH_TREE,Data2=-1});' in compact_script,
                    'Original TopPanel SciencePerTurn callback no longer queues BUTTONPOPUP_TECH_TREE with Data2=-1')
            self.top_panel_source_contract = {
                'layout_source': {'path': str(self.layout_path.resolve()), 'sha256': self.context_sources[self.layout_path]},
                'script_source': {'path': str(self.script_path.resolve()), 'sha256': self.context_sources[self.script_path]},
                'control_ids': sorted(self.top_panel_source_ids),
                'tooltip_type': 'TooltipTypeTopPanel',
                'consume_mouse_source_count': self.top_panel_consume_source_count,
                'science_callback': 'SciencePerTurn -> OnTechClicked -> BUTTONPOPUP_TECH_TREE, Data2=-1',
            }
        self.city_view_context_font_policy = None
        self.city_view_source_context_attributes = None
        if context == 'city-view':
            city_view_root = ET.parse(self.layout_path).getroot()
            require(city_view_root.tag == 'Context', 'Selected original CityView layout has no Context root')
            self.city_view_source_context_attributes = dict(city_view_root.attrib)
        if context == 'city-view' and city_view_layout_variant == 'small':
            standard_layout = self.game_root / 'Assets/DLC/Expansion2/UI/InGame/CityView/CityView.xml'
            standard_hash = sha256(standard_layout)
            standard_root = ET.parse(standard_layout).getroot()
            require(standard_root.tag == 'Context' and
                    standard_root.attrib.get('Font') == 'TwCenMT20' and
                    standard_root.attrib.get('FontStyle') == 'Shadow',
                    'Original standard CityView Context font fallback source differs')
            self.context_sources[standard_layout] = standard_hash
            self.city_view_context_font_policy = {
                'policy': 'ORIGINAL_CITY_VIEW_CONTEXT_FONT_FALLBACK_CANDIDATE_V1',
                'retail_default_font_verified': False,
                'attributes': {'Font': 'TwCenMT20', 'FontStyle': 'Shadow'},
                'source': {'path': str(standard_layout.resolve()), 'sha256': standard_hash,
                           'bytes': standard_layout.stat().st_size},
            }
        if context == 'city-capture':
            for relative in ('Assets/UI/InGame/Popups/GenericPopup.lua',
                             'Assets/UI/InGame/Popups/EmptyPopup.lua',
                             'Assets/UI/InGame/Popups/EmptyPopup.xml'):
                source = self.game_root / relative
                self.context_sources[source] = sha256(source)
        if context in SCENE_CONTEXTS:
            relatives = (() if context in ('city-capture', 'goody-hut-reward', 'exit-confirm', 'menu-options', 'touch-help') else
                         ('Assets/UI/IconSupport.lua', 'Assets/UI/InstanceManager.lua',
                          'Assets/UI/SupportFunctions.lua', 'Assets/Gameplay/Lua/MapUtilities.lua',
                          'Assets/Gameplay/Lua/FLuaVector.lua',
                          'Assets/Gameplay/XML/GameInfo/CIV5IconFontMapping.xml',
                          'Assets/DLC/Expansion2/Gameplay/XML/GameInfo/CIV5IconFontMapping_Expansion2.xml')
                         if context in ('game-menu', 'load-menu', 'map-menu') else
                         ('Assets/Gameplay/Lua/GameplayUtilities.lua',
                          'Assets/DLC/Expansion2/UI/InGame/InfoTooltipInclude.lua',
                          'Assets/UI/IconSupport.lua',
                          'Assets/DLC/Expansion2/UI/InGame/LeaderHead/DiscussionDialog.lua',
                          'Assets/DLC/Expansion2/UI/InGame/LeaderHead/DiscussionDialog.xml',
                          'Assets/UI/InGame/LeaderHead/DiploTrade.lua',
                          'Assets/DLC/Expansion2/UI/InGame/LeaderHead/DiploTrade.xml',
                          'Assets/Gameplay/XML/GameInfo/CIV5IconFontMapping.xml',
                          'Assets/DLC/Expansion2/Gameplay/XML/GameInfo/CIV5IconFontMapping_Expansion2.xml')
                         if context == 'diplomacy' else
                         ('Assets/DLC/Expansion2/UI/InGame/InfoTooltipInclude.lua',
                          'Assets/UI/IconSupport.lua', 'Assets/Gameplay/Lua/FLuaVector.lua',
                          'Assets/UI/InstanceManager.lua',
                          'Assets/Gameplay/XML/GameInfo/CIV5IconFontMapping.xml',
                          'Assets/DLC/Expansion2/Gameplay/XML/GameInfo/CIV5IconFontMapping_Expansion2.xml')
                         if context == 'production' else
                         ('Assets/UI/IconSupport.lua', 'Assets/UI/InstanceManager.lua',
                          'Assets/Gameplay/XML/GameInfo/CIV5IconFontMapping.xml',
                          'Assets/DLC/Expansion2/Gameplay/XML/GameInfo/CIV5IconFontMapping_Expansion2.xml')
                         if context == 'economic-overview' else
                         ('Assets/UI/IconSupport.lua', 'Assets/Gameplay/Lua/FLuaVector.lua',
                          'Assets/Gameplay/XML/GameInfo/CIV5IconFontMapping.xml',
                          'Assets/DLC/Expansion2/Gameplay/XML/GameInfo/CIV5IconFontMapping_Expansion2.xml')
                         if context == 'action-info-panel' else
                         ('Assets/UI/SupportFunctions.lua', 'Assets/UI/IconSupport.lua',
                          'Assets/UI/InstanceManager.lua',
                          'Assets/DLC/Expansion2/UI/InGame/InfoTooltipInclude.lua',
                          'Assets/Gameplay/Lua/FLuaVector.lua',
                          'Assets/Gameplay/XML/GameInfo/CIV5IconFontMapping.xml',
                          'Assets/DLC/Expansion2/Gameplay/XML/GameInfo/CIV5IconFontMapping_Expansion2.xml')
                         if context == 'unit-panel' else
                         ('Assets/UI/SupportFunctions.lua', 'Assets/UI/IconSupport.lua',
                          'Assets/DLC/Expansion2/UI/InGame/InfoTooltipInclude.lua',
                          'Assets/Gameplay/Lua/FLuaVector.lua', 'Assets/UI/InstanceManager.lua',
                          'Assets/Gameplay/XML/GameInfo/CIV5IconFontMapping.xml',
                          'Assets/DLC/Expansion2/Gameplay/XML/GameInfo/CIV5IconFontMapping_Expansion2.xml')
                         if context == 'top-panel' else
                         ('Assets/UI/IconSupport.lua', 'Assets/UI/InstanceManager.lua',
                          'Assets/DLC/Expansion2/UI/InGame/InfoTooltipInclude.lua',
                          'Assets/Gameplay/Lua/FLuaVector.lua',
                          'Assets/Gameplay/XML/GameInfo/CIV5IconFontMapping.xml',
                          'Assets/DLC/Expansion2/Gameplay/XML/GameInfo/CIV5IconFontMapping_Expansion2.xml')
                         if context == 'city-view' else
                         ('Assets/UI/CommonBehaviors.lua', 'Assets/UI/IconSupport.lua',
                          'Assets/UI/InstanceManager.lua',
                          'Assets/Gameplay/XML/GameInfo/CIV5IconFontMapping.xml',
                          'Assets/DLC/Expansion2/Gameplay/XML/GameInfo/CIV5IconFontMapping_Expansion2.xml')
                         if context == 'declare-war' else
                         ('Assets/DLC/Expansion2/UI/InGame/TechTree/TechButtonInclude.lua',
                          'Assets/DLC/Expansion2/UI/InGame/TechTree/TechHelpInclude.lua',
                          'Assets/DLC/Expansion2/UI/InGame/InfoTooltipInclude.lua',
                          'Assets/UI/IconSupport.lua', 'Assets/Gameplay/Lua/FLuaVector.lua',
                          'Assets/UI/InstanceManager.lua',
                          'Assets/Gameplay/XML/GameInfo/CIV5IconFontMapping.xml',
                          'Assets/DLC/Expansion2/Gameplay/XML/GameInfo/CIV5IconFontMapping_Expansion2.xml'))
            for relative in relatives:
                source = self.game_root / relative
                self.context_sources[source] = sha256(source)
            for icon in self.inline_icons.values():
                require(type(icon) is dict, 'Malformed prepared icon mapping entry')
                for field in ('mapping_source', 'font_source'):
                    source = icon.get(field)
                    require(type(source) is dict and isinstance(source.get('path'), str) and
                            isinstance(source.get('sha256'), str),
                            'Prepared icon mapping lacks original source provenance: ' + field)
                    source_path = Path(source['path'])
                    path = (source_path if source_path.is_absolute() else self.game_root / source_path).resolve(strict=True)
                    digest = sha256(path)
                    require(digest == source['sha256'], 'Prepared icon source hash differs: ' + str(path))
                    self.context_sources[path] = digest
        root = ET.parse(self.styles_path).getroot()
        self.styles = {}
        for node in root:
            if node.tag in self.styles:
                require(style_signature(self.styles[node.tag]) == style_signature(node), 'Conflicting original style definitions')
            else:
                self.styles[node.tag] = node
        self.textures, self.texture_ids = [], {}
        self.sprites, self.hits, self.scroll_regions, self.geometry, self.labels = [], [], [], [], []
        self.fonts, self.font_records, self.sources = {}, [], {}
        self.derived_textures = []
        self.scroll_texture_cache = {}
        self.production_font_metrics = None
        self.production_input_targets = None
        self.production_scroll_targets = None
        self.production_scroll_targets_by_key = {}
        self.city_view_projection = None
        self.city_view_hexes = []
        self.city_view_policy = None
        self.research_tree_scroll_targets = None
        self.icon_font_glyphs = {}
        self.keys = set()
        for name, color in self.inline_colors.items():
            require(name.startswith('COLOR_') and len(color) == 4 and all(math.isfinite(v) and 0 <= v <= 1 for v in color),
                    'Invalid original database text color')

    def texture(self, texture_name):
        record = self.assets.resolve(texture_name, self.destination / 'textures')
        path = Path(record['output']['path'])
        conversion = record['conversion']
        return self.register_texture(path, conversion['width'], conversion['height'])

    def register_texture(self, path, width, height):
        name = str(path.resolve())
        if name not in self.texture_ids:
            self.texture_ids[name] = len(self.textures)
            self.textures.append(name)
        return self.texture_ids[name], width, height

    def paint(self, key, texture, source, target, clip, color=(1, 1, 1, 1)):
        require(all(math.isfinite(v) for v in (*source, *target, *clip, *color)), 'Nonfinite paint geometry')
        require(all(0 <= v <= 1 for v in color), 'Out of range paint tint')
        if not positive(target) or not positive(clip) or color[3] == 0:
            return
        if texture != SOLID:
            require(positive(source) and source[0] >= 0 and source[1] >= 0, 'Invalid original atlas source rect')
        self.sprites.append((texture, key, *source, *target, *clip, *color))

    def game_menu_hits(self):
        proof = (self.private_menu_scene if self.context in PRIVATE_MENU_CONTEXTS else
                 self.exit_confirm_scene if self.context == 'exit-confirm' else
                 self.save_menu_scene if self.context == 'save-menu' else self.game_menu_scene)
        require(self.context in ('game-menu', 'save-menu', 'exit-confirm', *PRIVATE_MENU_CONTEXTS) and type(proof) is dict and
                [target['key'] for target in self.production_input_targets] ==
                proof['input_order_keys'],
                'GameMenu hit compilation lacks its source-validated input order')
        geometry = {row['key']: row for row in self.geometry if not row.get('style_decoration')}
        for target in self.production_input_targets:
            key = target['key']
            require(key in geometry and target['id'] == geometry[key].get('id', '') and
                    rect(geometry[key]['bounds']) == xywh_dict(target['bounds'], 'GameMenu rendered input'),
                    'GameMenu input control differs from its painted original geometry')
            row = geometry[key]
            require(target['event'] in ('LeftClick', 'ConsumeMouse', 'SliderValue') and
                    (target['event'] != 'LeftClick' or
                     row['kind'] in (('Button', 'GridButton', 'TextButton', 'EditBox', 'CheckBox', 'UpButton', 'DownButton', 'Context') if self.context in ('save-menu', *PRIVATE_MENU_CONTEXTS)
                                    else ('Button', 'GridButton', 'TextButton')) and not target['disabled']) and
                    (target['event'] != 'SliderValue' or self.context == 'menu-options' and row['kind'] == 'Slider' and
                     key in proof['slider_input_keys'] and not target['disabled']) and
                    (target['event'] != 'ConsumeMouse' or key in proof['consume_mouse_keys']),
                    'GameMenu hit is not its original enabled callback or source-bound consumer')
            row['input_target'] = True
            row['input_targets'] = [target['event']]
            if target.get('consumeMouse'):
                row['consume_mouse_target'] = True
            self.hits.append((key, *xywh_dict(target['clippedBounds'], 'GameMenu clipped hit')))
        validate_hit_regions(self.context, self.hits, self.geometry)

    def pull_down_scroll_chrome(self, node, panel):
        """Only this original composite may place chrome outside its own content clip."""
        if self.context not in ('load-menu','menu-options') or node.get('scrollPanelChromeOwnerKey') is None or node.get('hidden') is True:
            return False
        if self.context == 'menu-options':
            widget = self.private_menu_scene['resolution_widget_state']
            proof = {'widget_state':widget,'pull_down_key':widget['key'],
                     'popup_bounds':None}
        else:
            proof = self.load_menu_scene
        expected = {'ScrollBar': 'VertSlider', 'UpButton': 'ScrollBarUp', 'DownButton': 'ScrollBarDown'}
        source = node.get('styleChildSource', {})
        require(proof and panel.get('key') == proof['widget_state']['scrollPanelKey'] and
                panel.get('originalDataKind') == 'ScrollPanelData' and
                panel.get('sourceAttributes', {}).get('AutoScrollBar') == '1' and
                node.get('scrollPanelChromeOwnerKey') == panel['key'] and
                source.get('ownerPullDownKey') == proof['pull_down_key'] and
                source.get('style') == 'GenericPullDown' and
                source.get('sha256') == proof['widget_state']['originalStyleSource']['sha256'] and
                node.get('kind') in expected and
                source.get('indices') == [3, {'ScrollBar': 1, 'UpButton': 2, 'DownButton': 3}[node['kind']]] and
                node.get('sourceAttributes', {}).get('Style') == expected[node['kind']] and
                node.get('sourceAttributes', {}).get('AnchorSide') == 'O,I' and
                node.get('scrollClipPolicy') == 'PULL_DOWN_CHROME_OUTSIDE_OWN_VIEWPORT_WITHIN_POPUP',
                'PullDown scrollbar chrome lacks its exact original owner/style contract')
        bounds = rect((node['x'], node['y'], node['width'], node['height']))
        if proof['popup_bounds'] is not None:
            require(intersect(bounds, proof['popup_bounds']) == bounds,
                    'PullDown scrollbar chrome escapes the original composite popup frame')
        return True

    def load_menu_checkbox_default(self, node, attrs, width, height):
        expected = self.load_menu_checkbox_defaults.get(node.get('id'))
        candidate = node.get('defaultSize')
        require(self.context == 'load-menu' and node.get('kind') == 'CheckBox' and
                type(expected) is dict and type(candidate) is dict and candidate == expected and
                node.get('sourceAttributes') == candidate['controlSourceAttributes'] and
                all(name not in node['sourceAttributes'] for name in ('Size', 'Style', 'ButtonTexture')) and
                (width, height) == (32, 32) and
                attrs.get('Texture') == attrs.get('ButtonTexture') == node.get('texture') == candidate['texture'] and
                'Style' not in attrs and 'CheckTexture' not in attrs,
                'LoadMenu checkbox lost its exact observed source/atlas or unverified 32x32 default candidate')
        return candidate

    def production_hits(self, root):
        require(self.context in SCENE_CONTEXTS and type(self.production_input_targets) is list,
                'Retained input target validation was not initialized')
        if self.context in ('game-menu', 'save-menu', 'exit-confirm', *PRIVATE_MENU_CONTEXTS):
            self.game_menu_hits()
            return
        nodes = {}
        preorder = {}
        traversal_index = 0
        def collect(node, clip, visible, hover_visible):
            nonlocal traversal_index
            visible = visible and not node.get('hidden', True)
            if not visible:
                return
            preorder[node['key']] = traversal_index
            traversal_index += 1
            kind = node.get('kind')
            bounds = (node.get('x'), node.get('y'), node.get('width'), node.get('height'))
            if kind == 'ShowOnMouseOver':
                hovered = node.get('hovered')
                require(type(hovered) is bool, 'ShowOnMouseOver lacks captured hover state for hit testing')
                hover_visible = hover_visible and hovered
            elif kind == 'HideOnMouseOver':
                hovered = node.get('hovered')
                require(type(hovered) is bool, 'HideOnMouseOver lacks captured hover state for hit testing')
                hover_visible = hover_visible and not hovered
            outer_clip = clip
            if kind == 'ScrollPanel' or (self.context == 'economic-overview' and node['key'] in self.economic_slot_keys):
                clip = intersect(clip, rect(bounds))
            nodes[node['key']] = (node, clip, hover_visible)
            for child in node.get('children', []):
                child_clip = outer_clip if self.pull_down_scroll_chrome(child, node) else clip
                collect(child, child_clip, visible, hover_visible)

        collect(root, (0, 0, self.width, self.height), True, True)
        seen = set()
        left_keys = set()
        unit_panel_hits = {}
        callback_consume_keys = set()
        geometry_by_key = {row['key']: row for row in self.geometry if not row.get('style_decoration')}
        for target in self.production_input_targets:
            if self.context in ('unit-panel', 'top-panel', 'notification-panel') and \
                    type(target) is dict and target.get('event') == 'ConsumeMouse':
                continue
            allowed_events = ('LeftClick', 'RightClick', 'ConsumeMouse') if self.context == 'load-menu' else ('LeftClick', 'RightClick')
            require(type(target) is dict and target.get('event') in allowed_events and
                    target.get('visible') is True and target.get('disabled') is False and
                    type(target.get('key')) is int and (target['key'], target['event']) not in seen,
                    'Retained input target is malformed, duplicated, hidden, disabled, or unsupported')
            if self.context in SCENE_CONTEXTS:
                require(all(name not in target or type(target[name]) in (int, float) and
                            math.isfinite(target[name]) for name in ('void1', 'void2')),
                        'Popup callback payload must preserve scalar numeric arguments')
            seen.add((target['key'], target['event']))
            require(target['key'] in nodes and target['key'] in geometry_by_key,
                    'Retained input target has no retained/rendered control')
            node, clip, hover_visible = nodes[target['key']]
            geometry = geometry_by_key[target['key']]
            if self.context == 'load-menu' and target['event'] == 'ConsumeMouse':
                proof = self.load_menu_scene
                if proof and not proof['opened'] and proof['source_api_bound_candidate']:
                    source_consumer = (node.get('kind') in ('Box', 'Grid') and
                                       node.get('sourceAttributes', {}).get('ConsumeMouse') == '1' or
                                       node.get('id') == 'BGBlock' and
                                       node.get('sourceAttributes', {}).get('Style') == 'BGBlock' or
                                       node.get('id') in ('DeleteConfirm', 'ReferencedPackagesWindow') and
                                       node.get('sourceAttributes', {}).get('ConsumeMouseOver') == '1')
                    require(target['key'] in proof['consume_mouse_keys'] and source_consumer and
                            target.get('consumeMouse') is True and node.get('kind') in ('Box', 'Grid') and
                            target.get('id') == node.get('id') and
                            xywh_dict(target['bounds'], 'LoadMenu original consumer') ==
                            rect((node['x'], node['y'], node['width'], node['height'])) and
                            xywh_dict(target['clippedBounds'], 'LoadMenu original consumer clip') ==
                            intersect(rect((node['x'], node['y'], node['width'], node['height'])), clip),
                            'LoadMenu background consumer differs from its source-bound modal barrier candidate')
                else:
                    require(proof and proof['opened'] and target.get('consumeMouse') is True and
                            target['key'] == proof['widget_state']['popupKey'] and
                            node.get('kind') == 'Grid' and node.get('originalDataKind') == 'GridData' and
                            node.get('overlayOwnerKey') == proof['pull_down_key'] and
                            xywh_dict(target['bounds'], 'PullDown popup consumer') == proof['popup_bounds'] and
                            xywh_dict(target['clippedBounds'], 'PullDown clipped popup consumer') ==
                            intersect(proof['popup_bounds'], clip),
                            'PullDown mouse consumer differs from its original promoted popup')
                geometry['input_target'] = True
                geometry['input_targets'] = ['ConsumeMouse']
                geometry['consume_mouse_target'] = True
                self.hits.append((node['key'], *xywh_dict(target['clippedBounds'], 'PullDown popup hit')))
                continue
            if self.context == 'load-menu' and target.get('inputRole') == 'PullDownDismiss':
                require(self.load_menu_scene and self.load_menu_scene['opened'] and
                        target['key'] == root['key'] == self.load_menu_scene['dismiss_key'] and
                        target.get('ownerPullDownKey') == self.load_menu_scene['pull_down_key'] and
                        target['event'] == 'LeftClick' and node['kind'] == 'Context' and
                        xywh_dict(target.get('bounds'), 'PullDown dismissal bounds') == (0, 0, self.width, self.height) and
                        xywh_dict(target.get('clippedBounds'), 'PullDown dismissal clip') == (0, 0, self.width, self.height),
                        'PullDown dismissal is not the source-bound root viewport barrier')
                geometry['input_target'] = True
                geometry['input_targets'] = ['LeftClick']
                geometry['pull_down_dismiss_target'] = True
                left_keys.add(target['key'])
                self.hits.append((node['key'], 0, 0, self.width, self.height))
                continue
            if self.context in ('unit-panel', 'top-panel') and 'consumeMouse' in target:
                require(type(target['consumeMouse']) is bool and
                        target['consumeMouse'] == consume_mouse_enabled(node.get('attributes')),
                        'World-overlay callback target ConsumeMouse flag differs from its original XML control')
                if target['consumeMouse']:
                    callback_consume_keys.add(target['key'])
            if self.context == 'top-panel' and 'toolTipCallback' in target:
                require(type(target['toolTipCallback']) is bool,
                        'TopPanel tooltip callback state must remain an explicit original boolean')
                if target['event'] != 'ConsumeMouse':
                    require(target.get('id') in self.top_panel_source_ids,
                            'TopPanel callback target has no original XML control ID')
            allowed_kinds = ('Button', 'GridButton', 'TextButton', 'UpButton', 'DownButton')
            if self.context in ('city-view', 'social-policy', 'load-menu'):
                allowed_kinds += ('CheckBox', 'RadioButton')
            require(hover_visible and node.get('kind') in allowed_kinds and
                    node.get('id', '') == target.get('id', ''),
                    'Retained input target disagrees with retained button kind/id or hover visibility')
            require(node.get('buttonState') in ('normal', 'hover'),
                    'Retained input target has missing/disabled/pressed retained button state')
            if self.context in RESEARCH_CONTEXTS and node.get('id') in ('TechButton', 'B1', 'B2', 'B3', 'B4', 'B5'):
                require(type(target.get('void1')) is int and type(target.get('void2')) is int,
                        'Tech selection callback lacks its retained scalar techID/freeCount tuple')
            target_bounds = xywh_dict(target.get('bounds'), 'input target')
            node_bounds = rect((node['x'], node['y'], node['width'], node['height']))
            require(all(abs(a - b) <= 1e-6 for a, b in zip(target_bounds, node_bounds)),
                    'Retained input target bounds differ from retained button bounds')
            clipped = intersect(node_bounds, clip)
            captured_clipped = xywh_dict(target.get('clippedBounds'), 'clipped input target')
            require(positive(clipped) and all(abs(a - b) <= 1e-6 for a, b in zip(clipped, captured_clipped)),
                    'Retained input target clipping differs from retained viewport ancestry')
            geometry.setdefault('input_targets', []).append(target['event'])
            if target['event'] == 'LeftClick':
                require(target['key'] not in left_keys, 'Duplicate LeftClick hit target')
                left_keys.add(target['key'])
                geometry['input_target'] = True
                if self.context in ('unit-panel', 'top-panel', 'notification-panel'):
                    unit_panel_hits[target['key']] = clipped
                else:
                    self.hits.append((node['key'], *clipped))
        if self.context in ('unit-panel', 'top-panel', 'notification-panel'):
            capture_input_targets = [target for target in self.production_input_targets
                                     if type(target) is dict and target.get('event') == 'ConsumeMouse']
            explicit_consume_keys = set()
            for target in capture_input_targets:
                require(type(target) is dict and target.get('event') == 'ConsumeMouse' and
                        target.get('consumeMouse') is True and target.get('visible') is True and
                        type(target.get('disabled')) is bool and type(target.get('key')) is int and
                        isinstance(target.get('id'), str) and
                        'void1' not in target and 'void2' not in target and
                        target['key'] not in explicit_consume_keys,
                        'World-overlay ConsumeMouse target is malformed, duplicated, hidden, disabled, or carries callback arguments')
                explicit_consume_keys.add(target['key'])
                require(target['key'] in nodes and target['key'] in geometry_by_key,
                        'World-overlay ConsumeMouse target has no retained/rendered control')
                node, clip, hover_visible = nodes[target['key']]
                geometry = geometry_by_key[target['key']]
                notification_consumer = (self.context == 'notification-panel' and
                                         node.get('kind') == 'Container' and
                                         node.get('attributes', {}).get('ConsumeMouseButton') == '1')
                source_consumer = (node.get('attributes', {}).get('ConsumeMouseButton') == '1'
                                   if self.context == 'notification-panel' else
                                   consume_mouse_enabled(node.get('attributes')))
                require(hover_visible and node.get('id', '') == target['id'] and
                        source_consumer and
                        (notification_consumer or (self.context != 'notification-panel' and
                         (node.get('kind'), node.get('id', '')) in self.unit_panel_consume_sources)) and
                        geometry.get('kind') == node.get('kind'),
                        'World-overlay ConsumeMouse target differs from its original visible XML control')
                target_bounds = xywh_dict(target.get('bounds'), 'UnitPanel ConsumeMouse target')
                node_bounds = rect((node['x'], node['y'], node['width'], node['height']))
                require(all(abs(a - b) <= 1e-6 for a, b in zip(target_bounds, node_bounds)),
                        'World-overlay ConsumeMouse bounds differ from retained original control')
                clipped = intersect(node_bounds, clip)
                captured_clipped = xywh_dict(target.get('clippedBounds'), 'clipped UnitPanel ConsumeMouse target')
                require(positive(clipped) and all(abs(a - b) <= 1e-6 for a, b in zip(clipped, captured_clipped)),
                        'World-overlay ConsumeMouse clipping differs from retained ancestor viewport')
                geometry['consume_mouse_target'] = True
                geometry['input_target'] = True
                previous = unit_panel_hits.get(target['key'])
                require(previous is None or all(abs(a - b) <= 1e-6 for a, b in zip(previous, clipped)),
                    'World-overlay callback/ConsumeMouse bounds conflict for one control key')
                unit_panel_hits[target['key']] = clipped
            expected_consumed = {key for key, (node, clip, _) in nodes.items()
                                 if ((node.get('attributes', {}).get('ConsumeMouseButton') == '1'
                                      if self.context == 'notification-panel' else
                                      consume_mouse_enabled(node.get('attributes'))) and
                                     positive(intersect(rect((node['x'], node['y'], node['width'], node['height'])), clip)))}
            consumed_keys = callback_consume_keys | explicit_consume_keys
            require(consumed_keys == expected_consumed and
                    (bool(consumed_keys) if self.context == 'unit-panel' else True),
                    'World-overlay ConsumeMouse registrations differ from visible clipped original XML controls')
            ordered = sorted(unit_panel_hits.items(), key=lambda row: preorder[row[0]])
            self.hits.extend((key, *bounds) for key, bounds in ordered)
        validate_hit_regions(self.context, self.hits, self.geometry,
                             allow_empty_notification=(self.context == 'notification-panel' and
                                                       self.notification_panel_scene['zero_hit_regions_are_originally_valid']))

    def production_scrolls(self, root):
        require(self.context in SCENE_CONTEXTS and type(self.production_scroll_targets) is list,
                'Retained scroll target validation was not initialized')
        panels = {}

        def collect(node, clip, visible):
            visible = visible and not node.get('hidden', True)
            if not visible:
                return
            kind = node.get('kind')
            bounds = (node.get('x'), node.get('y'), node.get('width'), node.get('height'))
            if kind == 'ScrollPanel':
                panel_bounds = rect(bounds)
                clipped = intersect(panel_bounds, clip)
                if positive(clipped):
                    attrs = node.get('attributes')
                    horizontal = self.context == 'research-tree'
                    axis = 'X' if horizontal else 'Y'
                    content_name = 'contentWidth' if horizontal else 'contentHeight'
                    viewport = bounds[2] if horizontal else bounds[3]
                    require(type(attrs) is dict and attrs.get('Vertical') == ('0' if horizontal else '1'),
                            'Retained scroll target has the wrong original ScrollPanel orientation')
                    scroll = node.get('scrollX' if horizontal else 'scrollY')
                    content = node.get(content_name)
                    require(type(scroll) in (int, float) and math.isfinite(scroll) and
                            type(content) in (int, float) and math.isfinite(content) and
                            content >= 0 and viewport > 0,
                            'Visible retained ScrollPanel lacks finite captured scroll geometry')
                    maximum_scroll = max(0.0, content - viewport)
                    require(0 <= scroll <= maximum_scroll,
                            'Visible ScrollPanel offset exceeds its captured content range')
                    panels[node['key']] = (node, panel_bounds, clipped, axis, scroll,
                                           content, viewport, maximum_scroll)
                clip = intersect(clip, panel_bounds)
            if self.context == 'economic-overview' and node['key'] in self.economic_slot_keys:
                clip = intersect(clip, rect(bounds))
            for child in node.get('children', []):
                collect(child, clip, visible)

        collect(root, (0, 0, self.width, self.height), True)
        if self.context == 'pantheon':
            require(type(self.pantheon_scene) is dict, 'Pantheon scroll input lacks its captured confirmation scope')
            allowed = set(self.pantheon_scene['scroll_input_keys'])
            panels = {key: value for key, value in panels.items() if key in allowed}
        if self.context == 'game-menu':
            require(type(self.game_menu_scene) is dict, 'GameMenu scroll input lacks its source-bound modal scope')
            allowed = set(self.game_menu_scene['scroll_input_keys'])
            panels = {key: value for key, value in panels.items() if key in allowed}
        if self.context in PRIVATE_MENU_CONTEXTS:
            require(type(self.private_menu_scene) is dict, 'Private menu scrolls lack their source-bound modal scope')
            allowed = set(self.private_menu_scene['scroll_input_keys'])
            panels = {key: value for key, value in panels.items() if key in allowed}
        if self.context == 'save-menu':
            require(type(self.save_menu_scene) is dict, 'SaveMenu scroll input lacks its source-bound modal scope')
            allowed = set(self.save_menu_scene['modal_input_keys'])
            panels = {key: value for key, value in panels.items() if key in allowed}
        if self.context == 'load-menu' and self.load_menu_scene['opened']:
            # The opened original widget owns wheel input; its visible file
            # list stays painted but cannot scroll through the popup.
            allowed = {self.load_menu_scene['widget_state']['scrollPanelKey']}
            panels = {key: value for key, value in panels.items() if key in allowed}
        elif self.context == 'load-menu' and self.load_menu_scene['modal_key'] is not None:
            allowed = set(self.load_menu_scene['modal_input_keys'])
            panels = {key: value for key, value in panels.items() if key in allowed}
        targets = {}
        horizontal = self.context == 'research-tree'
        state_fields = (('orientation', 'scrollX', 'contentWidth', 'viewportWidth') if horizontal else
                        ('scrollY', 'contentHeight', 'viewportHeight'))
        required = ('key', 'id', 'event', 'visible', 'disabled', 'bounds', 'clippedBounds', *state_fields,
                    'maximumScroll')
        if self.context == 'trade-route':
            # The original native scroll callback contract only publishes key/id/event.
            # Its richer bounds come from a separate immutable scene diagnostic.
            route = getattr(self, 'trade_route_snapshot_state', None)
            main_scroll = route.get('mainScroll') if type(route) is dict else None
            require(type(main_scroll) is dict and
                    set(main_scroll) == {'key', 'id', 'event', 'orientation', 'bounds', 'clippedBounds',
                                         'scrollY', 'contentHeight', 'viewportHeight', 'maximumScroll'} and
                    main_scroll.get('id') == 'MainScroll' and main_scroll.get('event') == 'Scroll' and
                    main_scroll.get('orientation') == 'vertical',
                    'TradeRoute scene lacks its immutable original MainScroll geometry diagnostic')
            metadata_key = main_scroll.get('key')
            require(type(metadata_key) is int and len(self.production_scroll_targets) == 1 and
                    type(self.production_scroll_targets[0]) is dict and
                    self.production_scroll_targets[0].get('key') == metadata_key and
                    self.production_scroll_targets[0].get('id') == 'MainScroll' and
                    self.production_scroll_targets[0].get('event') == 'Scroll',
                    'TradeRoute scroll callback identity differs from its original MainScroll target')
            raw = self.production_scroll_targets[0]
            minimal_keys = {'key', 'id', 'event'}
            expanded_keys = set(required) | {'orientation'}
            require(set(raw) in (minimal_keys, expanded_keys),
                    'TradeRoute MainScroll target has an unsupported input-addon schema')
            expanded = dict(raw)
            expanded.update({
                'visible': True, 'disabled': False,
                'orientation': 'vertical',
                'bounds': main_scroll.get('bounds'),
                'clippedBounds': main_scroll.get('clippedBounds'),
                'scrollY': main_scroll.get('scrollY'),
                'contentHeight': main_scroll.get('contentHeight'),
                'viewportHeight': main_scroll.get('viewportHeight'),
                'maximumScroll': main_scroll.get('maximumScroll'),
            })
            if set(raw) == expanded_keys:
                require(raw.get('visible') is True and raw.get('disabled') is False and
                        raw.get('orientation') == 'vertical',
                        'Expanded TradeRoute MainScroll target is hidden, disabled or nonvertical')
                for field in ('bounds', 'clippedBounds'):
                    captured = xywh_dict(raw.get(field), 'expanded TradeRoute ' + field)
                    diagnostic = xywh_dict(main_scroll.get(field), 'TradeRoute ' + field)
                    require(all(abs(a - b) <= 1e-6 for a, b in zip(captured, diagnostic)),
                            'Expanded TradeRoute MainScroll bounds differ from original scene diagnostics')
                for field in ('scrollY', 'contentHeight', 'viewportHeight', 'maximumScroll'):
                    captured = raw.get(field)
                    diagnostic = main_scroll.get(field)
                    require(type(captured) in (int, float) and math.isfinite(captured) and
                            abs(captured - diagnostic) <= 1e-6,
                            'Expanded TradeRoute MainScroll range differs from original scene diagnostics')
            targets[metadata_key] = expanded
        else:
            for target in self.production_scroll_targets:
                require(type(target) is dict and all(field in target for field in required) and
                        target.get('event') == 'Scroll' and target.get('visible') is True and
                        target.get('disabled') is False and type(target.get('key')) is int and
                        target['key'] not in targets,
                        'Retained scroll target is malformed, duplicated, hidden, disabled, or not Scroll')
                targets[target['key']] = target
        require(set(targets) == set(panels),
                'Scroll targets differ from visible clipped oriented ScrollPanels')
        if horizontal:
            require(len(targets) == 1 and next(iter(targets.values())).get('id') == 'TechTreeScrollPanel',
                    'TechTree must expose exactly its original TechTreeScrollPanel target')
            self.research_tree_scroll_targets = targets
        if self.context == 'trade-route':
            require(len(targets) == 1 and next(iter(targets.values())).get('id') == 'MainScroll',
                    'TradeRoute must expose exactly its original vertical MainScroll target')
        if self.context == 'city-view':
            require(all(target.get('orientation', 'vertical') == 'vertical' for target in targets.values()),
                    'CityView only supports original vertical ScrollPanel targets')
        self.production_scroll_targets_by_key = targets
        for key, (node, bounds, clipped, axis, scroll, content, viewport, maximum_scroll) in panels.items():
            target = targets[key]
            require(target.get('id') == node.get('id', ''),
                    'Scroll target id differs from retained ScrollPanel')
            if self.context == 'trade-route':
                raw = next((row for row in self.production_scroll_targets
                            if type(row) is dict and row.get('key') == key), None)
                require(target.get('event') == 'Scroll' and raw.get('id') == 'MainScroll' and
                        raw.get('event') == 'Scroll',
                        'TradeRoute scroll callback is not the original MainScroll target')
            if horizontal:
                require(target.get('orientation') == 'horizontal',
                        'TechTree scroll target is not marked horizontal')
            captured_bounds = xywh_dict(target.get('bounds'), 'scroll target')
            captured_clip = xywh_dict(target.get('clippedBounds'), 'clipped scroll target')
            expected_bounds = bounds
            expected_clip = clipped
            require(all(abs(a - b) <= 1e-6 for a, b in zip(captured_bounds, expected_bounds)) and
                    all(abs(a - b) <= 1e-6 for a, b in zip(captured_clip, expected_clip)),
                    'Scroll target bounds/clipping differ from retained viewport ancestry')
            names = (('scrollX', scroll), ('contentWidth', content), ('viewportWidth', viewport),
                     ('maximumScroll', maximum_scroll)) if horizontal else (
                     ('scrollY', scroll), ('contentHeight', content), ('viewportHeight', viewport),
                     ('maximumScroll', maximum_scroll))
            for field, expected in names:
                actual = target.get(field)
                require(type(actual) in (int, float) and math.isfinite(actual) and
                        abs(actual - expected) <= 1e-6,
                        'Scroll target ' + field + ' differs from retained ScrollPanel state')
            if self.context == 'trade-route':
                metadata = self.trade_route_snapshot_state['mainScroll']
                captured_orientation = metadata.get('orientation')
                numeric_fields = ('scrollY', 'contentHeight', 'viewportHeight', 'maximumScroll')
                require(captured_orientation == 'vertical' and
                        all(type(metadata.get(field)) in (int, float) and math.isfinite(metadata[field])
                            for field in numeric_fields) and
                        all(abs(a - b) <= 1e-6 for a, b in zip(
                            xywh_dict(metadata.get('bounds'), 'TradeRoute MainScroll bounds'), bounds)) and
                        all(abs(a - b) <= 1e-6 for a, b in zip(
                            xywh_dict(metadata.get('clippedBounds'), 'TradeRoute clipped MainScroll bounds'), clipped)) and
                        abs(metadata.get('scrollY') - scroll) <= 1e-6 and
                        abs(metadata.get('contentHeight') - content) <= 1e-6 and
                        abs(metadata.get('viewportHeight') - viewport) <= 1e-6 and
                        abs(metadata.get('maximumScroll') - maximum_scroll) <= 1e-6,
                        'TradeRoute MainScroll diagnostic differs from its original retained tree geometry')
            self.scroll_regions.append((key, *clipped))
        self.scroll_regions.sort(key=lambda row: row[0])
        require(len(self.scroll_regions) <= 10000, 'Unbounded retained scroll region list')

    def validate_icon_glyph(self, icon):
        require(type(icon) is dict and type(icon.get('glyph')) is dict and
                type(icon.get('mapping')) is int and type(icon.get('font_source')) is dict,
                'Malformed prepared original inline icon record')
        source = icon['font_source']
        relative = source.get('path')
        require(type(relative) is str and type(source.get('sha256')) is str,
                'Inline icon font provenance is incomplete')
        path = Path(relative)
        path = path if path.is_absolute() else self.game_root / path
        path = path.resolve(strict=True)
        digest = sha256(path)
        require(digest == source['sha256'], 'Inline icon GGXML source hash changed')
        glyphs = self.icon_font_glyphs.get(str(path))
        if glyphs is None:
            root = ET.parse(path).getroot()
            glyphs = {int(element.attrib['ch']): element.attrib for element in root.findall('./glyphs/glyph')}
            self.icon_font_glyphs[str(path)] = glyphs
        original = glyphs.get(icon['mapping'])
        captured = icon['glyph']
        require(original is not None and
                (int(original['u']), int(original['v']), int(original['width']), int(original['height']),
                 int(original['a']) + int(original['b']) + int(original['c']),
                 int(original['originx']), int(original['originy'])) ==
                (captured.get('u'), captured.get('v'), captured.get('width'), captured.get('height'),
                 captured.get('advance'), captured.get('originx'), captured.get('originy')),
                'Prepared inline icon metrics differ from its original GGXML glyph')

    def color(self, raw):
        # Original palette values are loaded through the same font asset parser.
        if not self.fonts:
            self.font('TwCenMT14', 'Base')
        palette = next(iter(self.fonts.values())).colors
        parts = raw.replace('.', ',').split(',')
        if len(parts) == 4 and all(re.fullmatch(r'\d+', p) for p in parts):
            values = tuple(int(p) for p in parts)
        else:
            require(len(parts) in (1, 2) and parts[0] in palette, 'Unknown original color ' + raw)
            values = palette[parts[0]].rgba
            if len(parts) == 2:
                require(re.fullmatch(r'\d+', parts[1]), 'Invalid color alpha')
                values = (*values[:3], int(parts[1]))
        require(all(0 <= v <= 255 for v in values), 'Out of range original color')
        return tuple(v / 255 for v in values)

    def font(self, font_id, style):
        key = font_id, style
        if key not in self.fonts:
            owned = self.font_root != self.game_root
            if owned:
                require(font_id in ('TwCenMT14', 'TwCenMT16', 'TwCenMT18', 'TwCenMT20', 'TwCenMT22', 'TwCenMT24'),
                        'Font is outside the sealed selected input set')
                for path in (self.font_root / 'Assets/UI/Fonts/Tw Cent MT' / (font_id + '.ggxml'),
                             self.font_root / 'Assets/UI/ColorAtlas.xml'):
                    row = self.font_input_refs.get(path)
                    require(row is not None and path.resolve(strict=True) == path and
                            path.stat().st_size == row['bytes'] and sha256(path) == row['sha256'],
                            'Selected font source differs from its frozen binding')
            font = load_font(self.font_root, font_id, style)
            if owned:
                actual = [(font.ggxml_path, font.ggxml_sha256), (font.color_atlas_path, font.color_atlas_sha256)]
                actual.extend((sheet.path, sheet.sha256) for sheet in font.sheets.values())
                for path, digest in actual:
                    row = self.font_input_refs.get(path)
                    require(row is not None and path.is_relative_to(self.font_root) and path.resolve(strict=True) == path and
                            path.stat().st_size == row['bytes'] and digest == row['sha256'],
                            'Parsed font or atlas escaped its frozen selected inputs')
            self.fonts[key] = font
            sheets = []
            for layer in font.layers:
                source = layer.sheet.path
                output = candidate_directory(self.destination / 'textures', self.game_root) / source.name
                require(output.resolve().is_relative_to(self.destination) and not output.is_symlink(), 'Font candidate escaped scene directory')
                materialize_font_atlas(source, output, layer.sheet.sha256)
                require(sha256(output) == layer.sheet.sha256, 'Font atlas copy differs from source')
                sheets.append({'order': layer.order, 'alias': layer.texture_alias, 'source_path': str(source),
                               'source_sha256': layer.sheet.sha256,
                               'path': str(output), 'sha256': sha256(output)})
            self.font_records.append({'font_id': font_id, 'style': style,
                'ggxml_path': str(font.ggxml_path), 'ggxml_sha256': font.ggxml_sha256,
                'color_atlas_path': str(font.color_atlas_path), 'color_atlas_sha256': font.color_atlas_sha256,
                'height': font.height, 'ascent': font.ascent, 'descent': font.descent,
                'ascadj': font.ascadj, 'fudgeadv': font.fudgeadv, 'spacing': font.spacing,
                'horizontal_policy': 'ABC_ADVANCE_NO_UNPROVEN_SPACING',
                'vertical_policy': 'CANDIDATE_ASCENT_DESCENT_PLUS_ASCADJ',
                'glyph_quad_policy': 'GGXML_SPACING_BORDER_NO_EXTRA_CHARACTER_ADVANCE',
                'border_placement_policy': 'CANDIDATE_HALF_BORDER_OFFSET',
                'retail_metric_semantics_verified': False, 'sheets': sheets})
        return self.fonts[key]

    def grid(self, key, style, bounds, clip):
        attrs = style.attrib
        texture, tw, th = self.texture(attrs['Texture'])
        sizes = {name: pair(attrs[name + 'Size']) for name in ('UL', 'UC', 'UR', 'L', 'C', 'R', 'LL', 'LC', 'LR')}
        targets = grid_targets(sizes, bounds)
        for n, name in enumerate(('UL', 'UC', 'UR', 'L', 'C', 'R', 'LL', 'LC', 'LR')):
            u, v = pair(attrs[name + 'TexStart'])
            w, h = sizes[name]
            require(u >= 0 and v >= 0 and u + w <= tw and v + h <= th, 'Grid piece outside original atlas')
            self.paint(key, texture, (u, v, u + w, v + h), targets[n], clip)

    def style_control(self, element, owner_key, *, hovered=False):
        """Build one original Styles.xml decoration as a candidate retained control."""
        attrs = dict(element.attrib)
        size = attrs.get('Size', '0,0').replace('.', ',').split(',')
        require(len(size) == 2, 'Unsupported original style decoration size')
        dimensions = []
        for raw, full in zip(size, (self.width, self.height)):
            dimensions.append(float(full if raw == 'Full' else raw))
        hidden = attrs.get('Hidden', '0') in ('1', 'True', 'true')
        offset_x, offset_y = pair(attrs.get('TextureOffset', '0,0'))
        children = [self.style_control(child, owner_key, hovered=hovered) for child in element]
        node = {'key': owner_key, 'kind': element.tag, 'attributes': attrs,
                'width': dimensions[0], 'height': dimensions[1], 'hidden': hidden,
                'children': children, 'id': '', 'text': attrs.get('String', ''),
                'texture': attrs.get('Texture', ''), 'textureX': offset_x, 'textureY': offset_y,
                'hovered': hovered, 'buttonState': 'hover' if hovered else 'normal'}
        if element.tag == 'AlphaAnim':
            start, finish = float(attrs['AlphaStart']), float(attrs['AlphaEnd'])
            speed, pause = float(attrs['Speed']), float(attrs.get('Pause', '0'))
            require(speed > 0 and pause >= 0 and attrs.get('Cycle') == 'Bounce',
                    'Unsupported original style AlphaAnim timing contract')
            period = 2 * (speed + pause)
            time = self.snapshot_clock % period
            if time < pause:
                alpha = start
            elif time < pause + speed:
                alpha = start + (finish - start) * ((time - pause) / speed)
            elif time < 2 * pause + speed:
                alpha = finish
            else:
                alpha = finish + (start - finish) * ((time - 2 * pause - speed) / speed)
            node['animation'] = {'clock': self.snapshot_clock, 'alpha': max(0.0, min(1.0, alpha))}
        return node

    def render_style_children(self, style, owner_key, bounds, inherited, clip, *, hovered=False):
        for child in style:
            synthetic = self.style_control(child, owner_key, hovered=hovered)
            self.node(synthetic, bounds, inherited, clip, decoration=True)

    def vertical_strip(self, key, style, bounds, clip):
        """Paint an original vertical 9-slice strip with its center stretched."""
        attrs = style.attrib
        texture, tw, th = self.texture(attrs['Texture'])
        x0, y0, x1, y1 = bounds
        top_h = pair(attrs.get('UCSize', '0,0'))[1]
        center_w, center_h = pair(attrs['CSize'])
        bottom_h = pair(attrs.get('LCSize', '0,0'))[1]
        require(y1 - y0 >= top_h + bottom_h and center_w <= x1 - x0,
                'Vertical strip is smaller than its original caps')
        for size_key, start_key, target_y, target_h in (
                ('UCSize', 'UCTexStart', y0, top_h),
                ('CSize', 'CTexStart', y0 + top_h, y1 - y0 - top_h - bottom_h),
                ('LCSize', 'LCTexStart', y1 - bottom_h, bottom_h)):
            w, source_h = pair(attrs.get(size_key, '0,0'))
            if w == 0 or source_h == 0 or target_h == 0:
                continue
            u, v = pair(attrs[start_key])
            require(u + w <= tw and v + source_h <= th, 'Vertical strip region escapes original texture')
            self.paint(key, texture, (u, v, u + w, v + source_h),
                       (x0, target_y, x0 + w, target_y + target_h), clip)

    def horizontal_strip(self, key, style, bounds, clip):
        """Paint original horizontal left/center/right texture regions."""
        attrs = style.attrib
        texture, tw, th = self.texture(attrs['Texture'])
        x0, y0, x1, y1 = bounds
        left_w, left_h = pair(attrs.get('LSize', '0,0'))
        center_w, center_h = pair(attrs['CSize'])
        right_w, right_h = pair(attrs.get('RSize', '0,0'))
        require(x1 - x0 >= left_w + right_w and max(left_h, center_h, right_h) <= y1 - y0,
                'Horizontal strip is smaller than its original caps')
        for size_key, start_key, target_x, target_w in (
                ('LSize', 'LTexStart', x0, left_w),
                ('CSize', 'CTexStart', x0 + left_w, x1 - x0 - left_w - right_w),
                ('RSize', 'RTexStart', x1 - right_w, right_w)):
            source_w, source_h = pair(attrs.get(size_key, '0,0'))
            if source_w == 0 or source_h == 0 or target_w == 0:
                continue
            u, v = pair(attrs[start_key])
            require(u + source_w <= tw and v + source_h <= th,
                    'Horizontal strip region escapes original texture')
            self.paint(key, texture, (u, v, u + source_w, v + source_h),
                       (target_x, y0, target_x + target_w, y1), clip)

    def original_effects_slider(self, node, bounds, clip):
        require(self.context == 'menu-options' and node.get('id') == 'EffectsVolumeSlider' and
                type(self.private_menu_scene) is dict,
                'Horizontal slider is outside its exact supported options context')
        from civ5_ui_assets import menu_slider_style
        candidate = menu_slider_style(self.game_root)
        require(node.get('sliderStyle') == candidate and node.get('sliderGeometryPolicy') == candidate['policy'] and
                node.get('retailSliderBehaviorVerified') is False and node.get('sliderMinimum') == 0 and
                node.get('sliderMaximum') == 1 and type(node.get('sliderValue')) in (int,float) and
                math.isfinite(node['sliderValue']) and 0 <= node['sliderValue'] <= 1 and
                bounds[2] >= candidate['shuttleWidth'] and bounds[3] == candidate['height'],
                'Effects slider lost its finite range or original candidate geometry')
        track, shuttle = self.styles['Slider'], self.styles['Slider32']
        require(dict(track.attrib) == candidate['sourceStyleAttributes'] and
                dict(shuttle.attrib) == candidate['sourceShuttleAttributes'],
                'Effects slider track/shuttle differ from the exact original style')
        self.horizontal_strip(node['key'],track,rect(bounds),clip)
        x = bounds[0] + (bounds[2]-candidate['shuttleWidth'])*node['sliderValue']
        thumb = (x,bounds[1],candidate['shuttleWidth'],bounds[3])
        self.horizontal_strip(node['key'],shuttle,rect(thumb),clip)
        self.geometry[-1].update(slider_value=node['sliderValue'],slider_minimum=0,slider_maximum=1,
            slider_shuttle_bounds=thumb,slider_geometry_policy=candidate['policy'],
            retail_slider_behavior_verified=False)

    def image(self, key, texture_name, u, v, bounds, clip, color, *, stretch_full_texture=False,
              source_extent=None, economic_divider=False, unit_panel_divider=False):
        texture, tw, th = self.texture(texture_name)
        name = texture_name.replace('\\', '/').rsplit('/', 1)[-1].casefold()
        scalable = self.assets.outputs[name]['conversion']['source_scalable']
        if unit_panel_divider:
            require(self.context == 'unit-panel' and scalable and name == 'bar300x2.dds' and
                    (tw, th) == (512, 2) and (u, v) == (30, 0) and source_extent == (240, 1) and
                    bounds[2:] == (240, 1) and not stretch_full_texture and not economic_divider,
                    'UnitPanel atlas crop is outside the original recommended divider contract')
        if scalable and (u != 0 or v != 0):
            if unit_panel_divider:
                pass  # The exact source/extent permission above is separate from other scalable images.
            elif economic_divider:
                require(self.context == 'economic-overview' and
                        ECONOMIC_KEY_SPAN <= key < ECONOMIC_KEY_SPAN * 2 and
                        name == 'bar900x2.dds' and (u, v) == (110, 0) and
                        source_extent == (680, 1) and bounds[2:] == (680, 1),
                        'EconomicOverview atlas crop is outside the original General divider contract')
            else:
                require(self.context == 'city-view', 'Scalable images with atlas offsets need separate verification')
            source, target, policy = image_regions(u, v, bounds, (tw, th), source_extent=source_extent)
            policy = ('UNIT_PANEL_ORIGINAL_RECOMMENDED_DIVIDER_ATLAS_SUBREGION_CANDIDATE'
                      if unit_panel_divider else 'ECONOMIC_GENERAL_ORIGINAL_DIVIDER_ATLAS_SUBREGION_CANDIDATE'
                      if economic_divider else 'CITY_VIEW_SCALABLE_EXPLICIT_ATLAS_SUBREGION_CANDIDATE')
        elif scalable:
            source, target, policy = image_regions(u, v, bounds, (tw, th), stretch_full_texture=True)
            policy = 'SOURCE_ASSET_MARKED_SCALABLE_TEXTURE'
        else:
            extent = source_extent or bounds[2:]
            require(stretch_full_texture or (u + extent[0] <= tw and v + extent[1] <= th),
                    f'Image {key}/{texture_name}: source {u},{v}+{extent} exceeds original atlas {tw}x{th}')
            source, target, policy = image_regions(
                u, v, bounds, (tw, th), stretch_full_texture=stretch_full_texture,
                source_extent=source_extent)
        self.paint(key, texture, source, target, clip, color)
        return policy

    def scroll_animation_texture(self, node, attrs, width, height):
        animation = node.get('animation')
        require(type(animation) is dict and animation.get('clock') == self.snapshot_clock and
                type(animation.get('phase')) in (int, float) and math.isfinite(animation['phase']) and
                0 <= animation['phase'] <= 1,
                'ScrollAnim lacks captured phase at the selected presentation clock')
        texture_name = node.get('texture') or attrs.get('Texture')
        mask_name = attrs.get('MaskTexture')
        require(isinstance(texture_name, str) and texture_name and isinstance(mask_name, str) and mask_name,
                'ScrollAnim lacks its original texture or mask')
        texture_record = self.assets.resolve(texture_name, self.destination / 'textures')
        mask_record = self.assets.resolve(mask_name, self.destination / 'textures')
        texture_path = Path(texture_record['output']['path'])
        mask_path = Path(mask_record['output']['path'])
        texture_dds, mask_dds = texture_path.read_bytes(), mask_path.read_bytes()
        texture_header, mask_header = header(texture_dds), header(mask_dds)
        rgba32(texture_header); rgba32(mask_header)
        texture_width, texture_height = texture_header[4], texture_header[3]
        mask_width, mask_height = mask_header[4], mask_header[3]
        size = attrs.get('Size', f'{width},{height}').replace('.', ',').split(',')
        require(len(size) == 2 and all(item.isdigit() for item in size), 'Invalid original ScrollAnim size')
        out_width, out_height = int(size[0]), int(size[1])
        # XML Offset has already positioned the retained control bounds. It is
        # never a texture sample origin; only the retained TextureOffset is.
        offset_x = node.get('textureX', 0)
        offset_y = node.get('textureY', 0)
        require(type(offset_x) is int and type(offset_y) is int,
                'ScrollAnim captured TextureOffset is invalid')
        pixels = scroll_mask_rgba(texture_dds[128:], texture_width, texture_height,
                                  mask_dds[128:], mask_width, mask_height,
                                  out_width, out_height, animation['phase'], offset_x, offset_y)
        cache_key = hashlib.sha256(
            (texture_record['output']['sha256'] + mask_record['output']['sha256'] +
             f"|{animation['clock']:.9g}|{animation['phase']:.9g}|{offset_x},{offset_y}|"
             f"{out_width}x{out_height}|SCROLLANIM_STRETCHED_NEAREST_V1").encode()).hexdigest()
        if cache_key in self.scroll_texture_cache:
            return self.scroll_texture_cache[cache_key]
        output = self.destination / 'textures' / ('scrollmask_' + cache_key[:24] + '.dds')
        require(not output.exists() and not output.is_symlink(), 'Refusing to overwrite a derived ScrollAnim texture')
        output.write_bytes(normalized_header(texture_header, out_width, out_height) + pixels)
        record = {'path': str(output.resolve()), 'sha256': sha256(output), 'width': out_width, 'height': out_height,
                  'texture': texture_record, 'mask': mask_record, 'clock': animation['clock'],
                  'phase': animation['phase'], 'texture_offset': [offset_x, offset_y],
                  'pixel_policy': 'SCROLLANIM_STRETCHED_NEAREST_V1: phase-window-remaining-source-nearest-stretched-to-size; full-mask-nearest-stretched; source-alpha-times-mask-alpha',
                  'retail_sampling_equivalence_verified': False}
        self.derived_textures.append(record)
        value = self.register_texture(output, out_width, out_height)
        self.scroll_texture_cache[cache_key] = value
        return value

    def meter_texture(self, node, attrs):
        percent, plus = node.get('percent'), node.get('percentPlus')
        require(type(percent) in (int, float) and type(plus) in (int, float),
                'Meter lacks captured percent/percentPlus values')
        texture_name = node.get('texture') or attrs.get('Texture')
        require(isinstance(texture_name, str) and texture_name, 'Meter lacks its original texture')
        record = self.assets.resolve(texture_name, self.destination / 'textures')
        source_path = Path(record['output']['path'])
        data = source_path.read_bytes()
        words = header(data)
        rgba32(words)
        width, height = words[4], words[3]
        pixels = meter_arc_rgba(data[128:], width, height, percent, plus)
        cache_key = hashlib.sha256((record['output']['sha256'] + f'|{percent:.9g}|{plus:.9g}').encode()).hexdigest()
        if cache_key in self.scroll_texture_cache:
            return self.scroll_texture_cache[cache_key]
        output = self.destination / 'textures' / ('meterarc_' + cache_key[:24] + '.dds')
        require(not output.exists() and not output.is_symlink(), 'Refusing to overwrite a derived Meter texture')
        output.write_bytes(normalized_header(words, width, height) + pixels)
        derived = {'path': str(output.resolve()), 'sha256': sha256(output), 'width': width, 'height': height,
                   'texture': record, 'percent': percent, 'percentPlus': plus,
                   'pixel_policy': 'original_meter_rgba_clipped_to_clockwise_arc_from_twelve_oclock',
                   'retail_meter_semantics_verified': False}
        self.derived_textures.append(derived)
        value = self.register_texture(output, width, height)
        self.scroll_texture_cache[cache_key] = value
        return value

    def label(self, node, attrs, parent, inherited, clip, stack_y, stack_x=0, *,
              button_bounds=None, captured_metrics=True, button_text_meta=None, opacity=1.0):
        text = node['text']
        markup_text = close_stock_top_panel_negative_gold_label(
            text, context=self.context, control_id=node.get('id'), kind=node.get('kind'))
        if self.context in ('save-menu', 'map-menu') and node.get('kind') == 'EditBox':
            plain, inline_tints, icon_occurrences = text, [None] * len(text), {}
        elif '[ICON_' in markup_text:
            plain, inline_tints, icon_occurrences = markup(markup_text, self.inline_colors, self.inline_icons)
        else:
            plain, inline_tints = markup(markup_text, self.inline_colors)
            icon_occurrences = {}
        font_id = attrs.get('Font', inherited['Font'])
        font_style = attrs.get('FontStyle', inherited['FontStyle'])
        font = self.font(font_id, font_style)
        inline_glyphs = {}
        if '\t' in plain:
            inline_glyphs[9] = inline_tab_glyph(font)
        for codepoint, icon in icon_occurrences.items():
            if self.context in SCENE_CONTEXTS:
                self.validate_icon_glyph(icon)
            glyph = icon.get('glyph', icon) if type(icon) is dict else None
            require(type(icon) is dict and
                    type(glyph) is dict and
                    all(type(glyph.get(name)) is int for name in ('u', 'v', 'width', 'height', 'advance', 'originx', 'originy')) and
                    isinstance(icon.get('texture'), str) and icon['texture'],
                    'Invalid original inline icon glyph record')
            inline_glyphs[codepoint] = Glyph(codepoint, glyph['u'], glyph['v'], glyph['width'], glyph['height'],
                                             0, glyph['advance'], 0, glyph['originx'], glyph['originy'])
        if self.context in SCENE_CONTEXTS and captured_metrics:
            if '\t' in plain:
                require(self.production_font_metrics.get('tabPolicy') == 'ZEROSIS_TAB_FOUR_GGXML_SPACE_ADVANCES_V1' and
                        self.production_font_metrics.get('retailTabMetricsVerified') is False,
                        'Retained TAB metrics do not declare the shared provisional indentation policy')
            text_frame = node.get('textFrame')
            metric_source = node.get('fontMetricSource')
            require(type(text_frame) is dict and type(metric_source) is dict,
                    'Retained label lacks its captured textFrame/fontMetricSource')
            font_rows = self.production_font_metrics.get('fonts', {})
            source = font_rows.get(font_id)
            require(type(source) is dict and source.get('sha256') == font.ggxml_sha256 and
                    source.get('ggxmlPath') == str(font.ggxml_path.relative_to(self.font_root)).replace('\\', '/') and
                    metric_source.get('sha256') == font.ggxml_sha256 and
                    metric_source.get('ggxmlPath') == source.get('ggxmlPath'),
                    'Retained label font provenance differs from its selected GGXML')
            require(source.get('lineAdvance') == font.line_advance and
                    source.get('baselineOffset') == font.baseline_offset and
                    source.get('spacing') == font.spacing and source.get('fudgeadv') == font.fudgeadv,
                    'Retained captured font metrics differ from original GGXML')
            wrap_width = text_frame.get('wrapWidth')
            lines = text_frame.get('lines')
            require(type(wrap_width) in (int, float) and math.isfinite(wrap_width) and wrap_width >= 0 and
                    type(lines) is list and lines and all(type(line) is dict for line in lines),
                    'Retained label textFrame has invalid wrap width or line list')
            wrapped = wrap_production_text(plain, font, inline_glyphs, wrap_width)
            require(len(wrapped) == len(lines), 'Retained label wrapped line count differs from captured textFrame')
            for index, (actual_line, captured_line) in enumerate(zip(wrapped, lines)):
                require(captured_line.get('text') == actual_line[0] and
                        captured_line.get('advanceWidth') == actual_line[1],
                    f'Retained label line {index} differs from exact GGXML wrap/advance')
            wrapped_plain = '\n'.join(line[0] for line in wrapped)
            inline_tints = align_wrapped_tints(plain, inline_tints, wrapped_plain)
            layout = layout_text(wrapped_plain, font, inline_glyphs=inline_glyphs)
            effective_line_advance = production_line_advance(font, attrs)
            require(text_frame.get('lineAdvance') == effective_line_advance and
                    text_frame.get('baselineOffset') == font.baseline_offset,
                    'Retained textFrame vertical metrics differ from original GGXML')
            bounds = tuple(text_frame.get(name) for name in ('x', 'y', 'width', 'height'))
            require(len(bounds) == 4 and all(type(v) in (int, float) and math.isfinite(v) for v in bounds) and
                    bounds[0] == node.get('x') and bounds[1] == node.get('y') and
                    bounds[2] == node.get('width') and bounds[3] == node.get('height') and
                    bounds[2] >= 0 and bounds[3] >= 0,
                    'Retained textFrame geometry differs from retained label bounds')
            require(text_frame['height'] >= len(lines) * effective_line_advance or
                    self.context in ('save-menu', 'map-menu') and node.get('kind') == 'EditBox' and len(lines) == 1,
                    'Retained textFrame height cannot contain its captured GGXML lines')
        else:
            layout = layout_text(plain, font, inline_glyphs=inline_glyphs)
            if button_bounds is not None:
                overhang = 0
                if (self.context in ('load-menu','menu-options') and node.get('originalDataKind') == 'InstanceData' and
                        type(node.get('ownerPullDownKey')) is int):
                    require(node.get('sourceAttributes', {}).get('Size') == '200.24' and
                            node.get('sourceAttributes', {}).get('Style') == 'ZoomButton' and
                            attrs.get('Font') == 'TwCenMT22',
                            'PullDown caption differs from the original 200x24 ZoomButton cell')
                    # Its original GGXML line box is 25 high in a 24-high source
                    # cell. Keep both source sizes; clip the centered line box
                    # to the cell instead of replacing the font or growing it.
                    overhang = 1
                    clip = intersect(clip, rect(button_bounds))
                    if button_text_meta is not None:
                        button_text_meta['original_cell_linebox_overhang_candidate'] = 1
                bounds = centered_button_text_bounds(button_bounds, layout.width, layout.height,
                                                     pair(attrs.get('TextOffset', '0,0')),
                                                     max_vertical_overhang=overhang)
            else:
                bounds = anchor(attrs, parent, layout.width, layout.height, stack_y)
        x, y, _, _ = bounds
        edit_scroll = 0
        if self.context in ('save-menu', 'map-menu') and node.get('kind') == 'EditBox':
            clip = intersect(clip, rect(bounds))
            if node.get('focused'):
                caret_advance = layout_text(plain[:node['caretCodepoint']], font).width
                edit_scroll = max(0, caret_advance - max(0, bounds[2] - 1))
            x -= edit_scroll
        color_set = attrs.get('ColorSet', inherited.get('ColorSet'))
        if color_set:
            require(color_set in font.color_sets, 'Unknown original label ColorSet')
            colors, layer_color_policy = font_layer_colors(
                tuple(tuple(c / 255 for c in entry.rgba)
                      for entry in font.color_sets[color_set].layer_colors),
                len(font.layers), font_style=font_style, color_set=color_set)
        elif self.context == 'city-view' and any(name in attrs for name in
                                                  ('ColorLayer0', 'ColorLayer1', 'ColorLayer2')):
            colors = tuple(self.color(attrs.get('ColorLayer' + str(index),
                                                attrs.get('ColorLayer0', 'Beige')))
                           for index in range(len(font.layers)))
            layer_color_policy = 'CITYVIEW_ORIGINAL_COLORLAYER_ATTRIBUTES'
        elif any(name in attrs for name in ('Color0', 'Color1', 'Color2')):
            layer_count = len(font.layers)
            colors = tuple(self.color(attrs.get('Color' + str(index), attrs.get('Color', inherited.get('Color', 'Beige'))))
                           for index in range(layer_count))
            layer_color_policy = 'EXPLICIT_LABEL_COLOR_ATTRIBUTES'
        else:
            colors = (self.color(attrs.get('Color', inherited.get('Color', 'Beige'))),
                      self.color(attrs.get('Color1', inherited.get('Color1', 'Black'))))
            layer_color_policy = 'FRONTEND_DEFAULT_BASE_AND_EFFECT_COLORS'
        require(len(colors) >= len(font.layers), 'Missing font layer color')
        # XML assigns base Color0 and shadow Color1. Candidate compositing draws
        # later effect layers behind the base, retaining their original indices.
        for layer in reversed(font.layers):
            path = self.destination / 'textures' / layer.sheet.path.name
            texture, tw, th = self.register_texture(path, layer.sheet.width, layer.sheet.height)
            for glyph in layout.placements:
                if glyph.codepoint in icon_occurrences:
                    continue
                (u, v, w, h), border = glyph_quad(glyph, font)
                require(u + w <= tw and v + h <= th, 'Glyph outside original atlas')
                if glyph.texture_rect[2] and glyph.texture_rect[3]:
                    color = inline_tints[glyph.text_index] if layer.order == 0 and inline_tints[glyph.text_index] else colors[layer.order]
                    color = multiply_opacity(color, opacity)
                    self.paint(node['key'], texture, (u, v, u + w, v + h),
                               (x + glyph.draw_x - border, y + glyph.draw_y - border,
                                x + glyph.draw_x - border + w, y + glyph.draw_y - border + h), clip, color)
        for glyph in layout.placements:
            icon = icon_occurrences.get(glyph.codepoint)
            if icon is None or not glyph.texture_rect[2] or not glyph.texture_rect[3]:
                continue
            texture, tw, th = self.texture(icon['texture'])
            u, v, w, h = glyph.texture_rect
            require(u + w <= tw and v + h <= th, 'Inline icon glyph escapes its original icon font atlas')
            tint = inline_tints[glyph.text_index] if inline_tints[glyph.text_index] else colors[0]
            tint = multiply_opacity(tint, opacity)
            self.paint(node['key'], texture, (u, v, u + w, v + h),
                       (x + glyph.draw_x, y + glyph.draw_y, x + glyph.draw_x + w, y + glyph.draw_y + h),
                       clip, tint)
        self.labels.append({'key': node['key'], 'text': text, 'font': font_id, 'style': font_style,
                            'tab_policy': 'ZEROSIS_TAB_FOUR_GGXML_SPACE_ADVANCES_V1' if '\t' in plain else None,
                            'retail_tab_metrics_verified': False,
                            'plain_text': plain, 'inline_colors_preserved': text != plain,
                            'inline_icons': [{'codepoint': cp, **record} for cp, record in sorted(icon_occurrences.items())],
                            'bounds': bounds, 'glyph_count': len(layout.placements),
                            'text_frame': node.get('textFrame') if self.context in SCENE_CONTEXTS and captured_metrics else None,
                            'font_metric_source': node.get('fontMetricSource') if self.context in SCENE_CONTEXTS and captured_metrics else None,
                            'font_layer_color_policy': layer_color_policy,
                            'font_layer_colors_rgba': [list(color) for color in colors],
                            **(button_text_meta or {}),
                            'retail_font_layer_color_mapping_verified': False,
                            'captured_ggxml_layout_recomputed': self.context in SCENE_CONTEXTS and captured_metrics,
                            'retail_metric_semantics_verified': False,
                            'retail_pixel_equivalence_verified': False})
        if self.context in ('save-menu', 'map-menu') and node.get('kind') == 'EditBox':
            self.labels[-1]['literal_text'] = True
            self.labels[-1]['horizontal_scroll_pixels'] = edit_scroll
            self.labels[-1]['scroll_policy'] = 'KEEP_CODEPOINT_CARET_IN_ORIGINAL_NAMEBOX_RECT_CANDIDATE'
            self.labels[-1]['retail_text_scroll_verified'] = False
        if self.context in ('save-menu', 'map-menu') and node.get('kind') == 'EditBox' and node.get('focused'):
            caret = node['caretCodepoint']
            advance = layout_text(plain[:caret], font).width
            caret_x = min(bounds[0] + max(0, bounds[2] - 1), bounds[0] + advance - edit_scroll)
            caret_top = bounds[1];caret_bottom = bounds[1] + bounds[3]
            self.paint(node['key'], SOLID, (0, 0, 1, 1), (caret_x, caret_top, caret_x + 1, caret_bottom),
                       intersect(clip, rect(bounds)), (1, 1, 1, opacity))
            self.labels[-1]['caret_policy'] = 'RETAINED_CODEPOINT_ADVANCE_STATIC_ONE_PIXEL_CANDIDATE'
            self.labels[-1]['retail_caret_timing_verified'] = False
        return bounds

    def city_view_toggle_text(self, node, attrs, inherited, control_bounds, clip):
        require(self.context in ('city-view', 'social-policy', 'load-menu', 'menu-options', 'touch-help') and node.get('kind') in ('CheckBox', 'RadioButton') and
                isinstance(node.get('text'), str) and node['text'],
                'Original check control lacks its resolved String')
        text_attrs = dict(attrs)
        text_attrs['Anchor'] = attrs.get('TextAnchor', 'R,C')
        text_attrs['AnchorSide'] = attrs.get('TextAnchorSide', 'O,O')
        text_attrs['Offset'] = attrs.get('TextOffset', '0,0')
        text_attrs.pop('Size', None)
        return self.label(node, text_attrs, control_bounds, inherited, clip, 0,
                          captured_metrics=False,
                          button_text_meta={'text_control': node['kind'],
                                            'text_control_id': node.get('id', ''),
                                            'text_placement_policy': ('original TextAnchor with unverified outside TextAnchorSide default candidate'
                                                                      if self.context in ('load-menu', 'menu-options', 'touch-help') else
                                                                      'original TextAnchor/TextAnchorSide/TextOffset relative to retained checkbox bounds'),
                                            'retail_text_alignment_verified': False})

    def leader_button_text(self, node, attrs, inherited, button_bounds, clip):
        """Paint only the five direct String controls in the original LeaderHeadRoot XML."""
        control_id = node.get('id')
        source = self.leader_button_sources.get(control_id)
        require(type(source) is dict and node.get('sourceAttributes') == source and
                source.get('String') == attrs.get('String') and isinstance(node.get('text'), str) and
                node['text'].strip(),
                'LeaderHead GridButton text differs from its original direct XML String')
        if source.get('Style') == 'FrameButton200':
            style = self.styles.get('FrameButton200')
            require(style is not None and style.attrib.get('Size') == '200,32' and
                    style.attrib.get('TextOffset') == '0,-2' and attrs.get('Size') == '200,32' and
                    attrs.get('TextOffset') == '0,-2',
                    'LeaderHead FrameButton200 text geometry differs from original Styles.xml')
        else:
            require(control_id == 'WarButton' and source.get('Size') == '200,32' and
                    source.get('TextOffset') == '0,-2' and attrs.get('Size') == '200,32' and
                    attrs.get('TextOffset') == '0,-2',
                    'LeaderHead WarButton text geometry differs from its original inline XML')
        disabled_raw = attrs.get('Disabled', '0')
        require(disabled_raw in ('0', '1', 'True', 'true'),
                'LeaderHead GridButton has an unsupported disabled state')
        disabled = disabled_raw in ('1', 'True', 'true')
        return self.label(node, attrs, button_bounds, inherited, clip, 0,
                          button_bounds=button_bounds, captured_metrics=False,
                          button_text_meta={'text_control': 'GridButton', 'text_control_id': control_id,
                                            'button_disabled': disabled,
                                            'text_placement_policy': 'retained GridButton bounds center plus original XML TextOffset; retail text alignment unverified',
                                            'disabled_text_color_policy': 'original inherited ColorSet and GGXML layers retained without invented state tint'})

    def trade_route_tab_text(self, node, attrs, inherited, button_bounds, clip):
        source = self.trade_route_tab_sources.get(node.get('id'))
        require(type(source) is dict and node.get('sourceAttributes') == source and
                source.get('String') == attrs.get('String') and
                isinstance(node.get('text'), str) and node['text'].strip(),
                'TradeRoute tab caption differs from its original direct Button String')
        # Button geometry is the original hit area, not its caption's measured
        # extent. Use the existing button-text path without resizing that area.
        return self.label(node, attrs, button_bounds, inherited, clip, 0,
                          button_bounds=button_bounds, captured_metrics=False,
                          button_text_meta={'text_control': 'Button', 'text_control_id': node['id'],
                                            'text_placement_policy': 'retained Button bounds center plus original XML TextOffset; retail text alignment unverified',
                                            'retail_text_alignment_verified': False})

    def social_policy_tab_text(self, node, attrs, inherited, button_bounds, clip):
        source = self.social_policy_tab_sources.get(node.get('id'))
        require(type(source) is dict and node.get('sourceAttributes') == source and
                source.get('String') == attrs.get('String') and
                isinstance(node.get('text'), str) and node['text'].strip(),
                'SocialPolicy tab caption differs from its original direct Button String')
        return self.label(node, attrs, button_bounds, inherited, clip, 0,
                          button_bounds=button_bounds, captured_metrics=False,
                          button_text_meta={'text_control': 'Button', 'text_control_id': node['id'],
                                            'text_placement_policy': 'retained Button bounds center plus original XML TextOffset; retail text alignment unverified',
                                            'retail_text_alignment_verified': False})

    def city_view_d3d11_hex_overlay(self, city_view):
        projection = city_view['projection']
        highlights = city_view.get('hexHighlights')
        require(city_view.get('hexCoordinatePolicy') == 'ZEROSIS_GRID_TO_AXIAL_ROW_ODD_V1',
                'CityView lacks the captured original highlight coordinate policy')
        frame_generation = projection['frameGeneration']
        pixels, normalized, rasterized_count, pixel_count = city_view_raster_rgba(projection, highlights)
        self.city_view_projection = copy.deepcopy(projection)
        self.city_view_hexes = normalized
        self.city_view_policy = {
            'coordinate_policy': city_view['hexCoordinatePolicy'],
            'projection_policy': 'ZEROSIS_D3D11_CITY_VIEW_RASTER_V1',
            'tile_width': 84,
            'tile_height': 84 * 1.15470053838,
            'pixel_policy': 'ZEROSIS_D3D11_CITY_VIEW_RASTER_V1',
            'retail_world_projection_verified': False,
            'retail_shader_equivalence_verified': False,
            'hex_count': len(normalized),
            'rasterized_hex_count': rasterized_count,
            'rasterized_pixel_count': pixel_count,
        }
        if frame_generation is not None:
            self.city_view_policy['frame_generation'] = frame_generation
        if pixel_count == 0:
            return
        width, height = projection['viewportWidth'], projection['viewportHeight']
        words = [0] * 32
        words[0:8] = [0x20534444, 124, 0x100f, height, width, width * 4, 0, 1]
        words[19:27] = [32, 0x41, 0, 32, 0xff0000, 0xff00, 0xff, 0xff000000]
        words[27] = 0x1000
        cache_key = hashlib.sha256(
            pixels + repr((width, height, 'ZEROSIS_D3D11_CITY_VIEW_RASTER_V1')).encode()).hexdigest()
        output = self.destination / 'textures' / ('cityraster_' + cache_key[:24] + '.dds')
        require(not output.exists() and not output.is_symlink(),
                'Refusing to overwrite a derived D3D11 CityView raster texture')
        candidate_directory(output.parent, self.game_root)
        output.write_bytes(struct.pack('<32I', *words) + pixels)
        derived = {'path': str(output.resolve()), 'sha256': sha256(output), 'width': width, 'height': height,
                   'pixel_policy': 'ZEROSIS_D3D11_CITY_VIEW_RASTER_V1',
                   'source_geometry': 'native D3D11 integer-ID depth-winning contour spans',
                   'rasterized_hex_count': rasterized_count, 'rasterized_pixel_count': pixel_count,
                   'frame_generation': frame_generation,
                   'retail_shader_equivalence_verified': False}
        self.derived_textures.append(derived)
        texture = self.register_texture(output, width, height)
        self.paint(0, texture[0], (0, 0, width, height), (0, 0, width, height),
                   (0, 0, self.width, self.height))

    def city_view_hex_overlay(self, city_view):
        require(type(city_view) is dict and type(city_view.get('viewingMode')) is bool and
                city_view.get('retailWorldProjectionVerified') is False and
                type(city_view.get('projection')) is dict,
                'CityView lacks its original view-mode/projection proof boundary')
        projection = city_view['projection']
        if projection.get('policy') == 'ZEROSIS_D3D11_CITY_VIEW_RASTER_V1':
            self.city_view_d3d11_hex_overlay(city_view)
            return
        require(projection.get('policy') == 'ZEROSIS_2D_CITY_VIEW_V1' and
                projection.get('tileWidth') == 84 and
                projection.get('centerX') == 960 and projection.get('centerY') == 540,
                'CityView projection differs from the selected 1920x1080 world renderer profile')
        highlights = city_view.get('hexHighlights')
        require(type(highlights) is list and len(highlights) <= 10000 and
                city_view.get('hexCoordinatePolicy') == 'ZEROSIS_GRID_TO_AXIAL_ROW_ODD_V1',
                'CityView lacks the captured original highlight list/coordinate policy')
        previous = None
        normalized = []
        for item in highlights:
            require(type(item) is dict and type(item.get('hex')) is dict and
                    type(item.get('color')) is dict,
                    'Malformed original CityView hex highlight')
            hx, hy = item['hex'].get('x'), item['hex'].get('y')
            require(type(hx) is int and type(hy) is int and
                    all(type(item['color'].get(name)) in (int, float) and
                        math.isfinite(item['color'][name]) and 0 <= item['color'][name] <= 1
                        for name in ('x', 'y', 'z', 'w')),
                    'CityView highlight has invalid axial coordinates or retained RGBA color')
            order = (hy, hx)
            require(previous is None or previous < order,
                    'CityView hex highlights are not unique deterministic y/x order')
            previous = order
            center_x, center_y, tile_width, tile_height = city_view_hex_center(hx, hy, projection)
            normalized.append({'hex': {'x': hx, 'y': hy}, 'center': [center_x, center_y],
                               'color': [item['color'][name] for name in ('x', 'y', 'z', 'w')]})
        self.city_view_projection = copy.deepcopy(projection)
        self.city_view_hexes = normalized
        self.city_view_policy = {
            'coordinate_policy': city_view['hexCoordinatePolicy'],
            'projection_policy': projection['policy'],
            'tile_width': projection['tileWidth'],
            'tile_height': projection['tileWidth'] * 1.15470053838,
            'outline_width': 0.7,
            'pixel_policy': 'ZEROSIS_CITYVIEW_D2D_HEX_OUTLINE_RGBA_COVERAGE_V1',
            'retail_world_projection_verified': False,
            'retail_shader_equivalence_verified': False,
            'hex_count': len(normalized),
        }
        if not normalized:
            return
        width, height = 84, math.ceil(84 * 1.15470053838)
        pixels = city_view_hex_outline_rgba(width, height)
        words = [0] * 32
        words[0:8] = [0x20534444, 124, 0x100f, height, width, width * 4, 0, 1]
        words[19:27] = [32, 0x41, 0, 32, 0xff0000, 0xff00, 0xff, 0xff000000]
        words[27] = 0x1000
        cache_key = hashlib.sha256(pixels + repr((width, height, .7, 4)).encode()).hexdigest()
        output = self.destination / 'textures' / ('cityhex_' + cache_key[:24] + '.dds')
        require(not output.exists() and not output.is_symlink(),
                'Refusing to overwrite a derived CityView hex texture')
        candidate_directory(output.parent, self.game_root)
        output.write_bytes(struct.pack('<32I', *words) + pixels)
        derived = {'path': str(output.resolve()), 'sha256': sha256(output), 'width': width, 'height': height,
                   'pixel_policy': self.city_view_policy['pixel_policy'],
                   'outline_width': 0.7, 'supersample_grid': 4,
                   'source_geometry': 'Source/Presentation/WorldViewRenderer.cpp Hex() six point outline',
                   'retail_shader_equivalence_verified': False}
        self.derived_textures.append(derived)
        texture = self.register_texture(output, width, height)
        for item in normalized:
            cx, cy = item['center']
            self.paint(0, texture[0], (0, 0, width, height),
                       (cx - 42, cy - height / 2, cx + 42, cy + height / 2),
                       (0, 0, self.width, self.height), tuple(item['color']))

    def validate_city_view_payload(self, snapshot):
        city_view = snapshot.get('cityView')
        require(type(city_view) is dict and type(city_view.get('viewingMode')) is bool and
                city_view.get('retailWorldProjectionVerified') is False and
                type(city_view.get('projection')) is dict,
                'CityView snapshot lacks its native view/projection contract')
        yield_display = city_view.get('yieldDisplay')
        if yield_display is not None:
            require(type(yield_display) is dict and
                    yield_display.get('kind') in ('CityOwned', 'CityWorked', 'CityPurchasable') and
                    all(type(yield_display.get(name)) in (int, float) and math.isfinite(yield_display[name])
                        for name in ('x', 'y')) and yield_display.get('rendererVerified') is False,
                    'CityView yield-display request differs from the retained native contract')
        tutorials = city_view.get('tutorialRequests')
        require(type(tutorials) is list and city_view.get('tutorialExecutionVerified') is False,
                'CityView lacks the retained tutorial request/proof boundary')
        for request in tutorials:
            require(type(request) is dict and isinstance(request.get('kind'), str) and request['kind'] and
                    type(request.get('queued')) is bool and type(request.get('force')) is bool,
                    'CityView has a malformed original tutorial request')
        self.city_view_hex_overlay(city_view)

    def validate_city_view_context_font_defaults(self, snapshot):
        tree = snapshot.get('tree')
        require(type(tree) is dict and tree.get('kind') == 'Context',
                'CityView context font policy has no original Context node')
        defaults = tree.get('contextFontDefaults')
        if self.city_view_layout_variant == 'small':
            expected = self.city_view_context_font_policy
            require(type(defaults) is dict and
                    defaults.get('policy') == expected['policy'] and
                    defaults.get('retailDefaultFontVerified') is False and
                    defaults.get('attributes') == expected['attributes'],
                    'CityView small-layout font defaults differ from the retained candidate policy')
            source = defaults.get('source')
            retained_source = Path(source.get('path', '')).resolve(strict=True) if type(source) is dict else None
            require(type(source) is dict and
                    retained_source.is_file() and retained_source.name == 'CityView.xml' and
                    sha256(retained_source) == expected['source']['sha256'] and
                    source.get('sha256') == expected['source']['sha256'] and
                    retained_source.stat().st_size == expected['source']['bytes'] and
                    ('bytes' not in source or source['bytes'] == expected['source']['bytes']),
                    'CityView small-layout font fallback is not bound to the exact standard Context XML')
            self.city_view_context_font_policy['retained_source'] = dict(source)
            attributes = tree.get('attributes')
            source_attributes = tree.get('sourceAttributes')
            require(type(attributes) is dict and
                    attributes.get('Font') == expected['attributes']['Font'] and
                    attributes.get('FontStyle') == expected['attributes']['FontStyle'] and
                    type(source_attributes) is dict and
                    source_attributes == self.city_view_source_context_attributes and
                    'Font' not in source_attributes and 'FontStyle' not in source_attributes,
                    'CityView small Context did not inherit the candidate without changing source attributes')
        else:
            require(defaults is None,
                    'Default CityView layout unexpectedly carries a small-layout font fallback')

    def node(self, node, parent, inherited, clip, stack_y=0, *, stack_x=0,
             scroll_panel_state=None, decoration=False, inherited_opacity=1.0):
        if (self.context == 'menu-options' and type(node) is dict and
                node.get('kind') in ('Slider', 'PullDown') and node.get('hidden') is True):
            # These exact original controls are retained only as hidden source
            # data; private_menu_contract checks the complete original tree.
            return
        require(type(node) is dict and node.get('kind') in KINDS and type(node.get('key')) is int,
                'Unsupported retained control schema')
        key, kind = node['key'], node['kind']
        if kind == 'PullDown':
            require((self.context == 'load-menu' and node.get('id') == 'SortByPullDown' or
                     self.context == 'menu-options' and node.get('id') == 'WResolutionPull') and
                    node.get('sourceAttributes', {}).get('Style') == 'GenericPullDown',
                    'PullDown rendering is restricted to the original LoadMenu sorting control')
        action_alpha_sprite_start = (len(self.sprites) if self.context in ('action-info-panel', 'game-menu')
                                     and kind == 'AlphaAnim' else None)
        require(0 < key < (1 << 64), 'Invalid retained control key')
        if not decoration:
            require(key not in self.keys, 'Duplicate retained control key')
            self.keys.add(key)
        require(type(node.get('hidden')) is bool and type(node.get('children')) is list and type(node.get('attributes')) is dict,
                'Invalid retained control state')
        require(type(inherited_opacity) in (int, float) and math.isfinite(inherited_opacity) and
                0 <= inherited_opacity <= 1, 'Invalid inherited retained UI opacity')
        if self.context == 'social-policy' and node.get('kind') == 'HideOnMouseOver':
            validate_social_policy_hover_gate(node)
        if node['hidden']:
            return
        require(kind != 'LuaContext' or (self.context == 'economic-overview' and
                key in self.economic_slot_keys), 'Visible LuaContext has no sealed embedded representation')
        if kind == 'Instance':
            raise ValueError('Instance declarations are templates, not retained controls; expected the source popup instance children')
        attrs = dict(node['attributes'])
        zero_source_extent = False
        world_position = None
        check_default_size = None
        style = None
        if 'Style' in attrs:
            require(attrs['Style'] in self.styles, 'Missing original UI style')
            style = self.styles[attrs['Style']]
            attrs = {**style.attrib, **attrs}
        inherited = {**inherited, **{k: attrs[k] for k in ('Font', 'FontStyle', 'Color', 'Color1', 'ColorSet') if k in attrs}}
        width, height = node['width'], node['height']
        require(all(type(v) in (int, float) and math.isfinite(v) and v >= 0 for v in (width, height)), 'Invalid retained size')
        if self.context == 'load-menu' and kind == 'CheckBox':
            require(width > 0 and height > 0,
                    'Production control lacks resolved style dimensions: CheckBox/' + node.get('id', ''))
            check_default_size = self.load_menu_checkbox_default(node, attrs, width, height)
        elif self.context in ('menu-options', 'touch-help') and kind == 'CheckBox':
            check_default_size = node.get('defaultSize')
            style = self.styles.get('Button_16')
            require(type(check_default_size) is dict and style is not None and
                    style.get('Size') == '32,32' and style.get('Texture') == 'Assets/UI/Art/Controls/Checkbox.dds' and
                    check_default_size.get('policy') == 'MENU_BUTTON_16_DEFAULT_CANDIDATE_V1' and
                    check_default_size.get('retailWidgetGeometryVerified') is False and
                    check_default_size.get('defaultBindingVerified') is False and
                    check_default_size.get('width') == check_default_size.get('height') == 32 and
                    check_default_size.get('frameCount') == 4 and (width, height) == (32, 32) and
                    check_default_size.get('controlSourceAttributes') == node.get('sourceAttributes') and
                    node.get('texture') == check_default_size.get('texture') == 'Assets/UI/Art/Controls/Checkbox.dds' and
                    check_default_size.get('source', {}).get('sha256') == self.styles_hash,
                    'Private menu checkbox lacks its exact original source-backed Button_16 size candidate')
        elif self.context == 'city-view' and kind in ('CheckBox', 'RadioButton'):
            require('Size' not in attrs and 'Size' not in node.get('sourceAttributes', {}),
                    'CityView atlas-derived check size is only valid when the original XML omits Size')
            check_default_size = node.get('defaultSize')
            require(type(check_default_size) is dict and
                    check_default_size.get('policy') == 'CIV5_CHECK_ATLAS_SQUARE_FRAME_CANDIDATE_V1' and
                    check_default_size.get('retailWidgetGeometryVerified') is False and
                    check_default_size.get('width') == 32 and check_default_size.get('height') == 32 and
                    check_default_size.get('frameCount') == 4 and
                    width == check_default_size['width'] and height == check_default_size['height'],
                    'CityView check control lacks its captured source-backed atlas-frame candidate size')
            button_texture_name = attrs.get('ButtonTexture')
            require(isinstance(button_texture_name, str) and button_texture_name,
                    'Original CityView check control lacks its original ButtonTexture')
            source_record = self.assets.resolve(button_texture_name, self.destination / 'textures')
            recorded_texture = check_default_size.get('texture')
            recorded_conversion = recorded_texture.get('conversion', {}) if type(recorded_texture) is dict else {}
            source_conversion = source_record.get('conversion', {})
            require(type(recorded_texture) is dict and
                    str(recorded_texture.get('requested_name', '')).replace('\\', '/').rsplit('/', 1)[-1].casefold() ==
                    button_texture_name.replace('\\', '/').rsplit('/', 1)[-1].casefold() and
                    recorded_texture.get('source') == source_record.get('source') and
                    recorded_texture.get('index_source') == source_record.get('index_source') and
                    recorded_texture.get('output', {}).get('sha256') == source_record.get('output', {}).get('sha256') and
                    recorded_conversion.get('width') == source_conversion.get('width') and
                    recorded_conversion.get('height') == source_conversion.get('height') and
                    source_record.get('conversion', {}).get('width') == 32 and
                    source_record.get('conversion', {}).get('height') == 128,
                    'CityView check default size is not bound to its exact decoded 32x128 source atlas')
        elif self.context == 'social-policy' and kind == 'CheckBox' and node.get('id') == 'PolicyInfo':
            require('Size' not in attrs and 'Size' not in node.get('sourceAttributes', {}),
                    'SocialPolicy PolicyInfo size must remain sourced from the original widget default')
            check_default_size = node.get('defaultSize')
            button_texture_name = node.get('texture') or attrs.get('ButtonTexture')
            require(type(check_default_size) is dict and
                    check_default_size.get('policy') == 'SOCIAL_POLICY_BUTTON_16_DEFAULT_CANDIDATE_V1' and
                    check_default_size.get('retailWidgetGeometryVerified') is False and
                    check_default_size.get('width') == 32 and check_default_size.get('height') == 32 and
                    check_default_size.get('style') == 'Button_16' and
                    width == check_default_size['width'] and height == check_default_size['height'] and
                    isinstance(button_texture_name, str) and
                    button_texture_name.replace('\\', '/').rsplit('/', 1)[-1].casefold() == 'checkbox.dds' and
                    check_default_size.get('texture') == button_texture_name,
                    'SocialPolicy PolicyInfo lacks its original Checkbox.dds atlas and source-backed size candidate')
            source_record = self.assets.resolve(button_texture_name, self.destination / 'textures')
            style_source = check_default_size.get('source')
            source_conversion = source_record.get('conversion', {})
            require(type(style_source) is dict and style_source.get('path') == str(self.styles_path.resolve()) and
                    style_source.get('sha256') == self.styles_hash and
                    source_conversion.get('width') == 32 and source_conversion.get('height') == 128,
                    'SocialPolicy PolicyInfo candidate size lacks exact Styles.xml and Checkbox.dds provenance')
        if self.context in SCENE_CONTEXTS:
            if kind == 'Context':
                require((width, height) == (self.width, self.height), 'Retained viewport mismatch')
                bounds = ((node['x'], node['y'], width, height)
                          if self.context == 'economic-overview' and key in self.economic_context_keys
                          else (0, 0, width, height))
            elif kind in ('Label', 'TextButton') or self.context in ('save-menu', 'map-menu') and kind == 'EditBox':
                bounds = self.label(node, attrs, parent, inherited, clip, stack_y, stack_x,
                                    opacity=inherited_opacity)
            else:
                if not decoration:
                    require(type(node.get('x')) in (int, float) and type(node.get('y')) in (int, float),
                            'Production control lacks captured retained coordinates: ' + kind)
                if decoration and kind in ('ShowOnMouseOver', 'HideOnMouseOver', 'Container') and width == 0 and height == 0:
                    bounds = parent
                elif decoration:
                    bounds = anchor(attrs, parent, width, height, stack_y)
                elif kind in ('ShowOnMouseOver', 'HideOnMouseOver') and width == 0 and height == 0:
                    bounds = parent
                elif (kind in ('Stack', 'Box', 'WorldAnchor') or self.context in PRIVATE_MENU_CONTEXTS and kind == 'Container') and width == 0 and height == 0:
                    # Zero-area production containers still recurse through captured
                    # descendants; no child is hidden or omitted by this allowance.
                    bounds = (node['x'], node['y'], 0, 0)
                    if kind == 'WorldAnchor':
                        position = node.get('worldPosition')
                        require(type(position) is dict and
                                all(type(position.get(name)) in (int, float) and math.isfinite(position[name])
                                    for name in ('x', 'y', 'z')),
                                'CityView WorldAnchor lacks its original finite world position')
                        world_position = dict(position)
                elif (self.context == 'research' and kind in ('Image', 'Meter') and
                      node.get('id') in ('ProgressMeter', 'ProgressMeterInternal') and
                      width == 0 and height == 0):
                    source_attrs = node.get('sourceAttributes')
                    children = node.get('children')
                    allowed_children = (not children if node.get('id') == 'ProgressMeterInternal' else
                                        type(children) is list and len(children) == 1 and
                                        children[0].get('kind') == 'Meter' and
                                        children[0].get('id') == 'ProgressMeterInternal' and
                                        children[0].get('width') == 0 and children[0].get('height') == 0)
                    require(attrs.get('Size') in ('0.0', '0,0') and
                            type(source_attrs) is dict and source_attrs.get('Size') in ('0.0', '0,0') and
                            allowed_children,
                            'Zero-area Research progress control differs from its explicit original XML geometry')
                    # The stock TechPopup Lua can activate these progress controls,
                    # while the captured XML geometry remains Size=0.0. Preserve
                    # their state with no raster area in this frontend model;
                    # retail intrinsic-size and alpha semantics remain unverified.
                    zero_source_extent = True
                    bounds = (node['x'], node['y'], 0, 0)
                elif (self.context == 'social-policy' and kind == 'AlphaAnim' and
                      width == 0 and height == 0):
                    validate_social_policy_zero_area_alpha_anim(node, attrs)
                    # The original AlphaAnim is a timeline/opacity wrapper with
                    # no raster extent. Keep its timeline and recurse into its
                    # original child without inventing a paint size or texture.
                    bounds = (node['x'], node['y'], 0, 0)
                elif (self.context == 'notification-panel' and kind == 'AlphaAnim' and
                      width == 0 and height == 0):
                    source_attrs = node.get('sourceAttributes')
                    require(type(source_attrs) is dict and source_attrs.get('Size') is None and
                            attrs.get('Style') in ('NewFinger', 'NewFingerRed') and
                            type(node.get('children')) is list and node['children'],
                            'NotificationPanel zero-area NewFinger alpha wrapper differs from its original style source')
                    # The stock NewFinger style contributes the child frame and
                    # label; its size-less AlphaAnim remains a timeline-only
                    # wrapper and inherits alpha without a synthetic extent.
                    bounds = (node['x'], node['y'], 0, 0)
                else:
                    require(width > 0 and height > 0,
                            'Production control lacks resolved style dimensions: ' + kind + '/' + node.get('id', ''))
                    bounds = (node['x'], node['y'], width, height)
            if kind == 'ShowOnMouseOver':
                hovered = node.get('hovered')
                require(type(hovered) is bool, 'ShowOnMouseOver lacks captured hovered state')
                if not hovered:
                    self.geometry.append({'key': key, 'kind': kind, 'id': node.get('id', ''), 'bounds': bounds,
                                          'clip': clip, 'style_decoration': decoration, 'hovered': False,
                                          'children_drawn': False})
                    return
            elif kind == 'HideOnMouseOver':
                hovered = node.get('hovered')
                require(type(hovered) is bool, 'HideOnMouseOver lacks captured hovered state')
                if hovered:
                    self.geometry.append({'key': key, 'kind': kind, 'id': node.get('id', ''), 'bounds': bounds,
                                          'clip': clip, 'style_decoration': decoration, 'hovered': True,
                                          'children_drawn': False})
                    return
        else:
            if kind == 'Context':
                require((width, height) == (self.width, self.height), 'Retained viewport mismatch')
                bounds = (0, 0, width, height)
            elif kind in ('Label', 'TextButton'):
                bounds = self.label(node, attrs, parent, inherited, clip, stack_y, stack_x)
            elif kind in ('Container', 'ShowOnMouseOver', 'HideOnMouseOver'):
                bounds = anchor(attrs, parent, width, height, stack_y)
            else:
                if style is not None or decoration:
                    sizes = attrs.get('Size', f'{width},{height}').replace('.', ',').split(',')
                    require(len(sizes) == 2, 'Unsupported style size')
                    width, height = [full if raw == 'Full' else float(raw)
                                     for raw, full in zip(sizes, (self.width, self.height))]
                if kind == 'ScrollBar':
                    require('Length' in attrs and attrs.get('Vertical') == '1', 'Unsupported scrollbar')
                    height = int(attrs['Length'])
                bounds = anchor(attrs, parent, width, height, stack_y)
        require(all(math.isfinite(v) and abs(v) < 1e6 for v in bounds), 'Unbounded retained control geometry')
        if self.context in ('research', 'research-tree', 'tech-award', 'goody-hut-reward', 'city-capture', 'diplomacy', 'city-view', 'unit-panel', 'declare-war', 'trade-route', 'social-policy', 'economic-overview', 'action-info-panel', 'notification-panel', 'game-menu', 'save-menu', 'load-menu', 'exit-confirm') and kind in (
                'Button', 'GridButton', 'TextButton', 'UpButton', 'DownButton'):
            require(node.get('buttonState') in ('normal', 'hover', 'pressed', 'disabled'),
                    'Research button lacks its captured retained visual state: ' + node.get('id', ''))
        self.geometry.append({'key': key, 'kind': kind, 'id': node.get('id', ''), 'bounds': bounds,
                              'clip': clip, 'style_decoration': decoration})
        if kind == 'WorldAnchor':
            if world_position is None:
                world_position = node.get('worldPosition')
                require(type(world_position) is dict and
                        all(type(world_position.get(name)) in (int, float) and math.isfinite(world_position[name])
                            for name in ('x', 'y', 'z')),
                        'CityView WorldAnchor lacks its original finite world position')
            self.geometry[-1]['world_position'] = dict(world_position)
            self.geometry[-1]['world_position_policy'] = 'captured native world anchor; screen XYWH retained as supplied'
        if zero_source_extent:
            pass
        elif kind == 'Image':
            if 'color' in node:
                c = node['color']
                color = tuple(c[channel] for channel in ('x', 'y', 'z', 'w'))
            else:
                color = self.color(attrs['Color']) if 'Color' in node['attributes'] else (1, 1, 1, 1)
            texture_name = node['texture'].replace('\\', '/').rsplit('/', 1)[-1].casefold()
            stretch_tech_pipe = (self.context == 'research-tree' and node.get('id') == 'TechPipeIcon' and
                                 texture_name in ('techbranchh.dds', 'techbranchv.dds'))
            top_panel_bar = (self.context == 'top-panel' and texture_name == 'toppanelbar.dds' and
                             attrs.get('Size') in ('Full.32', '295.32'))
            if top_panel_bar:
                require(node.get('sourceAttributes', {}).get('Size') == attrs.get('Size') and
                        node['textureX'] == 0 and node['textureY'] == 0 and bounds[3] == 32 and
                        (attrs.get('Size') != 'Full.32' or bounds[2] == self.width) and
                        (attrs.get('Size') != '295.32' or bounds[2] == 295),
                        'TopPanelBar full-texture image differs from its original XML size/texture offset')
            city_full_image = (self.context == 'city-view' and
                               'Full' in attrs.get('Size', '').replace('.', ',').split(','))
            if city_full_image:
                require(node.get('sourceAttributes', {}).get('Size') == attrs.get('Size') and
                        node['textureX'] == 0 and node['textureY'] == 0,
                        'CityView full-axis image differs from its original XML size/texture offset')
            tech_branch_cell = (self.context == 'research-tree' and node.get('id') == 'TechPipeIcon' and
                                texture_name == 'techbranches.dds')
            source_extent = None
            unit_panel_divider = (node.get('id') == 'RecommendedActionDivider' or
                                  self.context == 'unit-panel' and texture_name == 'bar300x2.dds')
            if unit_panel_divider:
                expected_source_attributes = {
                    'Anchor': 'C,T', 'ID': 'RecommendedActionDivider', 'Offset': '0,105',
                    'Size': '240.1', 'Texture': 'bar300x2.dds', 'TextureOffset': '30.0',
                }
                require(self.context == 'unit-panel' and node.get('id') == 'RecommendedActionDivider' and
                        texture_name == 'bar300x2.dds' and
                        node.get('sourceAttributes') == expected_source_attributes and
                        all(attrs.get(name) == value for name, value in expected_source_attributes.items()) and
                        (node['textureX'], node['textureY']) == (30, 0) and bounds[2:] == (240, 1),
                        'UnitPanel recommended divider differs from original XML source/geometry')
                source_extent = (240, 1)
            economic_divider = self.context == 'economic-overview' and texture_name == 'bar900x2.dds'
            if economic_divider:
                source_attributes = node.get('sourceAttributes')
                expected_source_attributes = {
                    'Anchor': 'C,B', 'Offset': '0,0', 'TextureOffset': '110.0',
                    'Texture': 'bar900x2.dds', 'Size': '680.1',
                }
                require(ECONOMIC_KEY_SPAN <= key < ECONOMIC_KEY_SPAN * 2 and node.get('id') == '' and
                        source_attributes == expected_source_attributes and
                        all(attrs.get(name) == value for name, value in expected_source_attributes.items()) and
                        (node['textureX'], node['textureY']) == (110, 0) and bounds[2:] == (680, 1),
                        'EconomicOverview divider differs from original EconomicGeneralInfo.xml source/geometry')
                source_extent = (680, 1)
            if tech_branch_cell:
                # TechBranches uses a 36-pixel lattice of 32x32 cells in its
                # 105x105 decoded atlas. Lua changes the cell offset, while
                # the XML's 32x42 control size remains the draw destination.
                require(node['textureX'] % 36 == 0 and node['textureY'] % 36 == 0 and
                        node['textureX'] + 32 <= 105 and node['textureY'] + 32 <= 105 and
                        bounds[2:] == (32, 42),
                        'TechBranches cell does not match the retained source lattice/destination')
                source_extent = (32, 32)
            image_policy = self.image(key, node['texture'], node['textureX'], node['textureY'],
                                      bounds, clip, color,
                                      stretch_full_texture=stretch_tech_pipe or city_full_image or top_panel_bar,
                                      source_extent=source_extent, economic_divider=economic_divider,
                                      unit_panel_divider=unit_panel_divider)
            if city_full_image:
                image_policy = 'CITY_VIEW_ORIGINAL_FULL_AXIS_IMAGE_STRETCH_CANDIDATE'
            if top_panel_bar:
                image_policy = 'TOP_PANEL_ORIGINAL_TEXTURE_STRETCH_CANDIDATE'
                self.geometry[-1]['original_texture_source_policy'] = image_policy
                self.geometry[-1]['retail_texture_stretch_verified'] = False
            if stretch_tech_pipe or tech_branch_cell or self.context == 'city-view':
                self.geometry[-1]['original_texture_source_policy'] = image_policy
                self.geometry[-1]['retail_texture_stretch_verified'] = False
                if tech_branch_cell:
                    self.geometry[-1]['original_texture_source_extent'] = [32, 32]
                    self.geometry[-1]['texture_atlas_lattice'] = 36
            if economic_divider:
                self.geometry[-1]['original_texture_source_policy'] = image_policy
                self.geometry[-1]['original_texture_source_extent'] = [680, 1]
                self.geometry[-1]['retail_texture_stretch_verified'] = False
            if unit_panel_divider:
                self.geometry[-1]['original_texture_source_policy'] = image_policy
                self.geometry[-1]['original_texture_source_extent'] = [240, 1]
                self.geometry[-1]['retail_texture_stretch_verified'] = False
        elif kind == 'Box' and 'Color' in attrs:
            self.paint(key, SOLID, (0, 0, 0, 0), rect(bounds), clip, self.color(attrs['Color']))
        elif kind in ('Grid', 'GridButton'):
            if kind == 'GridButton':
                # Civ V GridButton stores its nine-slice descriptor as an
                # inline retained GridData child. It is draw data, not a
                # separately positioned control; use its original source
                # rectangles over the GridButton's retained bounds.
                grid_data_nodes = [child for child in node['children']
                                   if child.get('kind') == 'GridData']
                if style is not None:
                    styled_grid_data = style.find('GridData')
                    require(styled_grid_data is not None and
                            styled_grid_data.attrib.get('Style') in self.styles,
                            'Unsupported styled original button grid')
                    grid_style = self.styles[styled_grid_data.attrib['Style']]
                    require(not grid_data_nodes, 'GridButton has duplicate inline and styled GridData')
                else:
                    require(len(grid_data_nodes) == 1,
                            'GridButton lacks exactly one original inline GridData descriptor')
                    descriptor = grid_data_nodes[0]
                    grid_attrs = descriptor.get('attributes')
                    require(type(grid_attrs) is dict and descriptor.get('hidden') is False and
                            type(descriptor.get('children')) is list and not descriptor['children'] and
                            descriptor.get('width') == 0 and descriptor.get('height') == 0,
                            'Invalid retained inline GridData descriptor')
                    required_grid_attrs = {'Texture'} | {
                        f'{part}{field}' for part in ('UL', 'UC', 'UR', 'L', 'C', 'R', 'LL', 'LC', 'LR')
                        for field in ('Size', 'TexStart')}
                    require(required_grid_attrs <= grid_attrs.keys(),
                            'Inline GridData lacks original nine-slice texture regions')
                    grid_style = ET.Element('GridData', attrib=grid_attrs)
                    require('Style' in grid_attrs and grid_attrs['Style'] in self.styles,
                            'Inline GridData references a missing original style')
                self.grid(key, grid_style, bounds, clip)
            else:
                require(style is not None, 'Unstyled grid unsupported')
                self.grid(key, style, bounds, clip)
        elif kind == 'ScrollBar':
            require(style is not None, 'ScrollBar lacks its original style')
            shuttle = style.find('Shuttle')
            require(shuttle is not None and shuttle.attrib.get('Style') in self.styles,
                    'ScrollBar lacks its original shuttle style')
            shuttle_style = self.styles[shuttle.attrib['Style']]
            if self.context == 'research-tree':
                require(style.tag == 'ScrollBar' and attrs.get('Vertical') == '0',
                        'TechTree requires the original horizontal ScrollBar style')
                self.horizontal_strip(key, style, rect(bounds), clip)
                scroll = node.get('scrollX')
                content_width = node.get('contentWidth')
                viewport_width = node.get('viewportWidth')
                require(type(scroll) in (int, float) and math.isfinite(scroll) and
                        type(content_width) in (int, float) and math.isfinite(content_width) and
                        type(viewport_width) in (int, float) and math.isfinite(viewport_width) and
                        content_width >= 0 and viewport_width > 0,
                        'TechTree ScrollBar lacks its retained horizontal range')
                maximum_scroll = max(0.0, content_width - viewport_width)
                captured_maximum = node.get('maximumScroll')
                require(type(captured_maximum) in (int, float) and math.isfinite(captured_maximum) and
                        abs(captured_maximum - maximum_scroll) <= 1e-6 and
                        0 <= scroll <= maximum_scroll and
                        type(self.research_tree_scroll_targets) is dict and
                        len(self.research_tree_scroll_targets) == 1,
                        'TechTree ScrollBar maximum/range differs from retained TechTreeScrollPanel')
                panel_state = next(iter(self.research_tree_scroll_targets.values()))
                require(abs(scroll - panel_state['scrollX']) <= 1e-6 and
                        abs(content_width - panel_state['contentWidth']) <= 1e-6 and
                        abs(viewport_width - panel_state['viewportWidth']) <= 1e-6 and
                        abs(maximum_scroll - panel_state['maximumScroll']) <= 1e-6,
                        'TechTree ScrollBar range differs from captured ScrollPanel state')
                minimum_thumb = float(shuttle.attrib['Size'].replace('.', ',').split(',')[0])
                captured_shuttle = node.get('shuttleBounds')
                require(type(captured_shuttle) is dict,
                        'TechTree ScrollBar lacks its retained frontend-model shuttle bounds')
                require(node.get('shuttlePolicy') == 'ZEROSIS_RETAINED_VIEWPORT_PROPORTIONAL_V1' and
                        node.get('retailScrollbarGeometryVerified') is False,
                        'TechTree ScrollBar frontend model/proof boundary is missing or overstated')
                modeled_shuttle = research_tree_scrollbar_thumb_bounds(
                    bounds, scroll, content_width, viewport_width, minimum_thumb)
                captured = tuple(captured_shuttle.get(name) for name in ('x', 'y', 'width', 'height'))
                require(all(type(value) in (int, float) and math.isfinite(value) for value in captured) and
                        all(abs(a - b) <= 1e-6 for a, b in zip(rect(captured), modeled_shuttle)),
                        'TechTree ScrollBar shuttle differs from captured style/content frontend model')
                self.horizontal_strip(key, shuttle_style, rect(captured), clip)
            else:
                require(style.tag == 'VertSlider', 'Unsupported scrollbar style')
                self.vertical_strip(key, style, rect(bounds), clip)
                scroll = node.get('scrollY')
                require(type(scroll) in (int, float) and math.isfinite(scroll) and scroll >= 0,
                        'ScrollBar lacks captured scrollY state')
                content_height = node.get('contentHeight')
                require(type(content_height) in (int, float) and math.isfinite(content_height) and
                        content_height >= 0, 'ScrollBar lacks a valid retained content extent')
                minimum_thumb = float(shuttle.attrib['Size'].replace('.', ',').split(',')[1])
                if self.context == 'research':
                    captured_shuttle = node.get('shuttleBounds')
                    require(type(captured_shuttle) is dict,
                            'Research ScrollBar lacks its retained frontend-model shuttle bounds')
                    require(node.get('shuttlePolicy') == 'ZEROSIS_RETAINED_VIEWPORT_PROPORTIONAL_V1' and
                            node.get('retailScrollbarGeometryVerified') is False,
                            'Research ScrollBar frontend model/proof boundary is missing or overstated')
                    modeled_shuttle = research_scrollbar_thumb_bounds(bounds, scroll, content_height, minimum_thumb)
                    captured = tuple(captured_shuttle.get(name) for name in ('x', 'y', 'width', 'height'))
                    require(all(type(value) in (int, float) and math.isfinite(value) for value in captured) and
                            all(abs(a - b) <= 1e-6 for a, b in zip(rect(captured), modeled_shuttle)),
                            'Research ScrollBar shuttle differs from captured style/content frontend model')
                    shuttle_bounds = rect(captured)
                elif self.context == 'pantheon':
                    require(type(scroll_panel_state) is dict and scroll_panel_state.get('kind') == 'ScrollPanel' and
                            scroll_panel_state.get('id') == 'ItemScrollPanel', 'Pantheon ScrollBar lost its original owner')
                    scroll = scroll_panel_state.get('scrollY')
                    content = scroll_panel_state.get('contentHeight')
                    viewport = scroll_panel_state.get('height')
                    require(all(type(value) in (int, float) and math.isfinite(value) for value in (scroll, content, viewport)) and
                            content >= 0 and viewport > 0 and 0 <= scroll <= max(0, content - viewport),
                            'Pantheon retained scrollbar range is invalid')
                    shuttle_bounds = production_scrollbar_thumb_bounds(bounds, scroll, content, viewport, minimum_thumb)
                    self.geometry[-1]['scrollbar_geometry_policy'] = 'ZEROSIS_PANTHEON_VERTICAL_THUMB_FROM_RETAINED_RANGE_V1'
                    self.geometry[-1]['retail_scrollbar_geometry_verified'] = False
                elif self.context == 'map-menu':
                    require(type(scroll_panel_state) is dict and scroll_panel_state.get('kind') == 'ScrollPanel' and
                            scroll_panel_state.get('id') == 'ScrollPanel' and
                            scroll_panel_state.get('attributes', {}).get('Vertical') == '1',
                            'Map ScrollBar has no original list viewport')
                    parent_target = self.production_scroll_targets_by_key.get(scroll_panel_state['key'])
                    require(parent_target is not None or self.private_menu_scene['confirmation_visible'],
                            'Map ScrollBar lost both its owned scroll target and covering confirmation')
                    scroll = scroll_panel_state.get('scrollY');content_height = scroll_panel_state.get('contentHeight')
                    viewport_height = scroll_panel_state.get('height')
                    require(all(type(value) in (int,float) and math.isfinite(value) for value in
                                (scroll,content_height,viewport_height)) and viewport_height > 0 and content_height >= 0 and
                            0 <= scroll <= max(0,content_height-viewport_height), 'Map list scroll range is invalid')
                    shuttle_bounds = production_scrollbar_thumb_bounds(bounds,scroll,content_height,viewport_height,minimum_thumb)
                    self.geometry[-1]['scrollbar_geometry_policy']='ZEROSIS_PRIVATE_MAP_SCROLL_FROM_RETAINED_RANGE_V1'
                    self.geometry[-1]['retail_scrollbar_geometry_verified']=False
                elif self.context in ('city-view', 'declare-war', 'trade-route', 'social-policy', 'economic-overview'):
                    require(type(scroll_panel_state) is dict and
                            scroll_panel_state.get('kind') == 'ScrollPanel' and
                            scroll_panel_state.get('attributes', {}).get('Vertical') == '1',
                            'Retained vertical ScrollBar has no owning ScrollPanel')
                    parent_key = scroll_panel_state.get('key')
                    parent_target = self.production_scroll_targets_by_key.get(parent_key)
                    require(type(parent_target) is dict and parent_target.get('key') == parent_key and
                            parent_target.get('id') == scroll_panel_state.get('id', '') and
                            parent_target.get('visible') is True and parent_target.get('disabled') is False,
                            'Retained vertical ScrollBar has no matching visible original ScrollPanel target')
                    panel_bounds = tuple(scroll_panel_state.get(name) for name in ('x', 'y', 'width', 'height'))
                    target_bounds = xywh_dict(parent_target.get('bounds'), 'CityView ScrollPanel bounds')
                    require(all(type(value) in (int, float) and math.isfinite(value) for value in panel_bounds) and
                            all(abs(a - b) <= 1e-6 for a, b in zip(target_bounds, rect(panel_bounds))),
                            'Retained vertical ScrollBar owner viewport differs from scrollTargets')
                    scroll = scroll_panel_state.get('scrollY')
                    content_height = scroll_panel_state.get('contentHeight')
                    viewport_height = panel_bounds[3]
                    target_range = tuple(parent_target.get(name) for name in
                                         ('scrollY', 'contentHeight', 'viewportHeight'))
                    require(type(scroll) in (int, float) and math.isfinite(scroll) and
                            type(content_height) in (int, float) and math.isfinite(content_height) and
                            all(type(value) in (int, float) and math.isfinite(value) for value in target_range) and
                            abs(target_range[0] - scroll) <= 1e-6 and
                            abs(target_range[1] - content_height) <= 1e-6 and
                            abs(target_range[2] - viewport_height) <= 1e-6 and
                            0 <= scroll <= max(0.0, content_height - viewport_height),
                            'Retained vertical ScrollBar range differs from its captured ScrollPanel target')
                    shuttle_bounds = production_scrollbar_thumb_bounds(
                        bounds, scroll, content_height, viewport_height, minimum_thumb)
                    self.geometry[-1]['scrollbar_geometry_policy'] = ('ZEROSIS_DECLARE_WAR_VERTICAL_THUMB_FROM_RETAINED_RANGE_V1'
                                                                      if self.context == 'declare-war' else
                                                                      'ZEROSIS_TRADE_ROUTE_VERTICAL_THUMB_FROM_RETAINED_RANGE_V1'
                                                                      if self.context == 'trade-route' else
                                                                      'ZEROSIS_SOCIAL_POLICY_VERTICAL_THUMB_FROM_RETAINED_RANGE_V1'
                                                                      if self.context == 'social-policy' else
                                                                      'ZEROSIS_ECONOMIC_VERTICAL_THUMB_FROM_RETAINED_RANGE_V1'
                                                                      if self.context == 'economic-overview' else
                                                                      'ZEROSIS_CITYVIEW_VERTICAL_THUMB_FROM_RETAINED_RANGE_V1')
                    self.geometry[-1]['retail_scrollbar_geometry_verified'] = False
                elif self.context == 'production':
                    require(type(scroll_panel_state) is dict and
                            scroll_panel_state.get('kind') == 'ScrollPanel' and
                            scroll_panel_state.get('attributes', {}).get('Vertical') == '1',
                            'Production ScrollBar has no retained vertical ScrollPanel owner')
                    parent_key = scroll_panel_state.get('key')
                    parent_target = self.production_scroll_targets_by_key.get(parent_key)
                    require(type(parent_target) is dict and parent_target.get('key') == parent_key and
                            parent_target.get('id') == scroll_panel_state.get('id', '') and
                            parent_target.get('visible') is True and parent_target.get('disabled') is False,
                            'Production ScrollBar has no matching visible ScrollPanel target')
                    panel_bounds = tuple(scroll_panel_state.get(name) for name in ('x', 'y', 'width', 'height'))
                    target_bounds = xywh_dict(parent_target.get('bounds'), 'Production ScrollPanel bounds')
                    require(all(type(value) in (int, float) and math.isfinite(value) for value in panel_bounds) and
                            all(abs(a - b) <= 1e-6 for a, b in zip(target_bounds, rect(panel_bounds))),
                            'Production ScrollBar owner viewport bounds differ from scrollTargets')
                    viewport_height = panel_bounds[3]
                    panel_scroll = scroll_panel_state.get('scrollY')
                    panel_content = scroll_panel_state.get('contentHeight')
                    target_scroll = parent_target.get('scrollY')
                    target_content = parent_target.get('contentHeight')
                    target_viewport = parent_target.get('viewportHeight')
                    target_maximum = parent_target.get('maximumScroll')
                    scroll = node.get('scrollY')
                    content_height = node.get('contentHeight')
                    numeric = (panel_scroll, panel_content, target_scroll, target_content,
                               target_viewport, target_maximum, scroll, content_height)
                    require(all(type(value) in (int, float) and math.isfinite(value) for value in numeric) and
                            panel_content >= 0 and content_height >= 0 and
                            abs(panel_scroll - target_scroll) <= 1e-6 and
                            abs(panel_content - target_content) <= 1e-6 and
                            abs(viewport_height - target_viewport) <= 1e-6 and
                            abs(scroll - panel_scroll) <= 1e-6 and abs(content_height - panel_content) <= 1e-6,
                            'Production ScrollBar content/offset differs from its retained ScrollPanel')
                    maximum_scroll = max(0.0, content_height - viewport_height)
                    require(abs(target_maximum - maximum_scroll) <= 1e-6 and
                            0 <= scroll <= maximum_scroll,
                            'Production ScrollBar maximum/range differs from scrollTargets')
                    shuttle_bounds = production_scrollbar_thumb_bounds(
                        bounds, scroll, content_height, viewport_height, minimum_thumb)
                else:
                    require(content_height >= bounds[3] and 0 <= scroll <= content_height - bounds[3],
                            'ScrollBar lacks a valid retained viewport/content/offset range')
                    shuttle_bounds = scrollbar_thumb_bounds(bounds, scroll, content_height, minimum_thumb)
                self.vertical_strip(key, shuttle_style, shuttle_bounds, clip)
        elif kind in ('Button', 'UpButton', 'DownButton'):
            button_state = node.get('buttonState')
            require(button_state in ('normal', 'hover', 'pressed', 'disabled'),
                    kind + ' lacks captured buttonState')
            texture_name = node.get('texture') or attrs.get('Texture')
            if texture_name:
                texture, tw, th = self.texture(texture_name)
                u, v = node.get('textureX', 0), node.get('textureY', 0)
                increment = pair(attrs.get('StateOffsetIncrement', '0,0'))
                state_index = {'normal': 0, 'hover': 1, 'pressed': 2, 'disabled': 3}[button_state]
                u += increment[0] * state_index
                v += increment[1] * state_index
                source = button_source_rect(u, v, width, height, tw, th)
                self.paint(key, texture, source, rect(bounds), clip)
        elif kind == 'Slider':
            self.original_effects_slider(node,bounds,clip)
        elif kind in ('CheckBox', 'RadioButton'):
            require(self.context in ('city-view', 'social-policy', 'load-menu', 'menu-options', 'touch-help') and type(node.get('checked')) is bool and
                    type(node.get('disabled')) is bool and
                    node.get('buttonState') in ('normal', 'hover', 'pressed', 'disabled'),
                    'Original check control lacks its retained checked/disabled/button state')
            button_texture = node.get('texture') or attrs.get('ButtonTexture')
            require(isinstance(button_texture, str) and button_texture,
                    'Original CityView check control lacks its original ButtonTexture')
            texture, tw, th = self.texture(button_texture)
            u, v = node.get('textureX', 0), node.get('textureY', 0)
            # The original CityView radio/check controls use a four-cell
            # checked/disabled atlas. `buttonState` alone loses SetCheck state
            # (and the independent disabled dimension), so bind the retained
            # booleans to the visually inspected original atlas cells.
            frame_by_state = {
                (False, False): 0,  # unchecked, enabled
                (True, False): 1,   # checked, enabled
                (True, True): 2,    # checked, disabled
                (False, True): 3,   # unchecked, disabled
            }
            frame_index = frame_by_state[(node['checked'], node['disabled'])]
            frame_height = check_default_size['height'] if check_default_size else th // 4
            frame_count = (4 if check_default_size and
                           check_default_size.get('policy') == 'SOCIAL_POLICY_BUTTON_16_DEFAULT_CANDIDATE_V1'
                           and th == frame_height * 4 else
                           check_default_size['frameCount'] if check_default_size else (4 if th % 4 == 0 else 0))
            require(frame_count == 4 and frame_index < frame_count and
                    v + (frame_index + 1) * frame_height <= th,
                    'Original checked/disabled cell escapes its four-frame source atlas')
            v += frame_index * frame_height
            source = button_source_rect(u, v, width, height, tw, th)
            self.paint(key, texture, source, rect(bounds), clip)
            check_texture = attrs.get('CheckTexture')
            if node['checked'] and check_texture:
                check, cw, ch = self.texture(check_texture)
                check_source = button_source_rect(node.get('checkTextureX', 0),
                                                  node.get('checkTextureY', 0),
                                                  width, height, cw, ch)
                self.paint(key, check, check_source, rect(bounds), clip)
            self.geometry[-1]['checked'] = node['checked']
            self.geometry[-1]['disabled'] = node['disabled']
            self.geometry[-1]['checked_art_policy'] = ('original ButtonTexture plus CheckTexture at retained checked state'
                                                        if check_texture else
                                                        'original ButtonTexture cell selected by retained checked/disabled booleans; four-frame atlas mapping candidate, retail widget mapping unverified')
            self.geometry[-1]['retail_check_art_verified'] = False
            self.geometry[-1]['check_atlas_frame'] = frame_index
            self.geometry[-1]['check_atlas_texture'] = button_texture
            self.geometry[-1]['check_atlas_frame_policy'] = 'CIV5_CHECK_ATLAS_CHECKED_DISABLED_CELL_CANDIDATE_V1'
            self.geometry[-1]['retail_widget_state_mapping_verified'] = False
            if self.context == 'load-menu':
                self.geometry[-1]['default_size_candidate'] = check_default_size
        elif kind == 'Bar':
            source = self.economic_bar_sources.get((key // ECONOMIC_KEY_SPAN * ECONOMIC_KEY_SPAN,
                                                     node.get('id')))
            require(self.context == 'economic-overview' and type(source) is dict and
                    node.get('sourceAttributes') == source and attrs.get('FGColor') == source.get('FGColor') and
                    attrs.get('Direction') == source.get('Direction'),
                    'Bar is not an original sealed EconomicGeneralInfo progress control')
            percent = node.get('percent')
            require(type(percent) in (int, float) and math.isfinite(percent) and 0 <= percent <= 1,
                    'EconomicOverview Bar lacks a captured normalized percent')
            color = node.get('fgColor')
            if color is None:
                color = self.color(source['FGColor'])
            else:
                require(type(color) is dict and set(color) == {'x', 'y', 'z', 'w'} and
                        all(type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 1
                            for value in color.values()), 'EconomicOverview Bar has an invalid original RGBA state')
                color = tuple(color[field] for field in ('x', 'y', 'z', 'w'))
            _, target = texture_bar_regions(bounds, source['Direction'], percent, width, height)
            if percent > 0:
                self.paint(key, SOLID, (0, 0, 1, 1), target, clip, color)
            self.geometry[-1]['bar_percent'] = percent
            self.geometry[-1]['bar_rgba'] = list(color)
            self.geometry[-1]['retail_bar_pixels_verified'] = False
        elif kind == 'TextureBar':
            percent = node.get('percent')
            require(type(percent) in (int, float) and math.isfinite(percent) and 0 <= percent <= 1,
                    'TextureBar lacks a captured normalized percent')
            direction = attrs.get('Direction')
            if direction is None and self.context == 'unit-panel':
                # The stock horizontal XP bar omits Direction. Keep the
                # frontend default explicit until retail pixel comparison.
                direction = 'Right'
                self.geometry[-1]['default_direction_policy'] = 'HORIZONTAL_TEXTUREBAR_RIGHT_CANDIDATE_V1'
                self.geometry[-1]['retail_default_direction_verified'] = False
            require(direction in ('Up', 'Down', 'Left', 'Right'), 'Unsupported original TextureBar direction')
            texture, tw, th = self.texture(node.get('texture') or attrs['Texture'])
            source, target = texture_bar_regions(bounds, direction, percent, tw, th)
            if percent > 0:
                self.paint(key, texture, source, target, clip)
        elif kind == 'AlphaAnim':
            animation = node.get('animation')
            require(type(animation) is dict and animation.get('clock') == self.snapshot_clock and
                    type(animation.get('alpha')) in (int, float) and math.isfinite(animation['alpha']) and
                    animation['alpha'] >= 0, 'AlphaAnim lacks captured value at the selected presentation clock')
            if self.context == 'game-menu' and attrs.get('Cycle') == 'Once':
                game_menu_once_alpha(attrs, animation, self.snapshot_clock)
            if (self.context == 'notification-panel' and
                    node.get('attributes', {}).get('Style') in ('NewFinger', 'NewFingerRed')):
                style_attrs = self.styles[node['attributes']['Style']].attrib
                notification_one_bounce_alpha(style_attrs, animation, self.snapshot_clock)
            texture_name = node.get('texture') or attrs.get('Texture')
            if texture_name:
                texture, tw, th = self.texture(texture_name)
                u, v = node.get('textureX', 0), node.get('textureY', 0)
                self.paint(key, texture, (u, v, u + width, v + height), rect(bounds), clip,
                           (1, 1, 1, min(1, animation['alpha'])))
            else:
                require(node.get('children'), 'AlphaAnim has neither original texture nor children')
                if (self.context == 'social-policy' and width == 0 and height == 0):
                    inherited_opacity = inherited_opacity * min(1.0, animation['alpha'])
                if (self.context == 'notification-panel' and
                        node.get('attributes', {}).get('Style') in ('NewFinger', 'NewFingerRed')):
                    inherited_opacity = inherited_opacity * min(1.0, animation['alpha'])
        elif kind == 'SlideAnim':
            require(self.context == 'notification-panel' and attrs.get('Style') == 'NotificationSlide',
                    'SlideAnim is only supported for the original NotificationPanel slide style')
            animation = node.get('animation')
            style_attrs = self.styles['NotificationSlide'].attrib
            phase, offset = notification_slide_transform(style_attrs, animation, self.snapshot_clock)
            require(abs(width - parent[2]) <= 1e-6 and abs(height - parent[3]) <= 1e-6,
                    'Original NotificationPanel SlideAnim lacks its captured parent-frame timeline')
            self.geometry[-1]['animation_policy'] = animation['timingPolicy']
            self.geometry[-1]['animation_geometry_policy'] = animation['geometryPolicy']
            self.geometry[-1]['animation_phase'] = phase
            self.geometry[-1]['animation_offset'] = list(offset)
            self.geometry[-1]['retail_timing_verified'] = False
        elif kind == 'FlipAnim':
            animation = node.get('animation')
            require(type(animation) is dict and animation.get('clock') == self.snapshot_clock and
                    type(animation.get('frame')) is int and animation.get('retailTimingVerified') is False,
                    'FlipAnim lacks its captured source-timeline frame')
            frame_count = int(attrs.get('FrameCount', '0'))
            source_pause = float(attrs.get('Pause', '0'))
            end_pause = float(attrs.get('EndPause', abs(source_pause)))
            speed = float(attrs.get('Speed', '0'))
            require(math.isfinite(source_pause) and math.isfinite(end_pause) and end_pause >= 0 and
                    speed > 0 and math.isfinite(speed) and frame_count > 0 and
                    animation.get('timingPolicy') == 'CIV5_FLIP_NEGATIVE_PAUSE_END_HOLD_CANDIDATE_V1' and
                    animation.get('sourcePause') == source_pause and animation.get('endPause') == end_pause,
                    'FlipAnim lacks its explicit original signed-Pause interpretation')
            expected_frame = min(frame_count - 1,
                                 math.floor((self.snapshot_clock % (frame_count / speed + end_pause)) * speed))
            require(animation['frame'] == expected_frame, 'FlipAnim frame differs from its recorded candidate clock')
            columns = int(attrs.get('Columns', '0'))
            step_x, step_y = pair(attrs.get('StepSize', '0,0'))
            require(frame_count > 0 and columns > 0 and columns <= frame_count and
                    0 <= animation['frame'] < frame_count and width > 0 and height > 0,
                    'FlipAnim frame differs from its original XML frame grid')
            frame = animation['frame']
            u = node.get('textureX', 0) + (frame % columns) * step_x
            v = node.get('textureY', 0) + (frame // columns) * step_y
            texture, tw, th = self.texture(node.get('texture') or attrs['Texture'])
            require(u >= 0 and v >= 0 and u + width <= tw and v + height <= th,
                    'Original FlipAnim frame escapes its atlas')
            self.paint(key, texture, (u, v, u + width, v + height), rect(bounds), clip)
            self.geometry[-1]['animation_policy'] = 'captured original FlipAnim frame at selected frontend clock'
            self.geometry[-1]['source_pause'] = source_pause
            self.geometry[-1]['end_pause'] = end_pause
            self.geometry[-1]['timing_policy'] = animation['timingPolicy']
            self.geometry[-1]['retail_timing_verified'] = False
        elif kind == 'ScrollAnim':
            texture, tw, th = self.scroll_animation_texture(node, attrs, width, height)
            self.paint(key, texture, (0, 0, tw, th), rect(bounds), clip)
        elif kind == 'Meter':
            texture, tw, th = self.meter_texture(node, attrs)
            self.paint(key, texture, (0, 0, tw, th), rect(bounds), clip)
        if style is not None and kind == 'Box':
            if self.context in ('tech-award', 'goody-hut-reward', 'city-capture', 'city-view', 'declare-war', 'trade-route', 'social-policy', 'economic-overview', 'game-menu', 'save-menu', 'load-menu', 'exit-confirm', *PRIVATE_MENU_CONTEXTS):
                self.render_style_children(style, key, bounds, inherited, clip)
            else:
                for child in style:
                    require(child.tag == 'Box', 'Unsupported style child')
                    synthetic = {'key': key, 'kind': child.tag, 'attributes': child.attrib,
                                 'width': 0, 'height': 0, 'hidden': False, 'children': [], 'id': '', 'text': ''}
                    self.node(synthetic, bounds, inherited, clip, decoration=True)
        if self.context in ('city-capture', 'city-view', 'declare-war') and kind in ('GridButton', 'Button') and style is not None and node.get('buttonState') == 'hover':
            hover_style = style.find('ShowOnMouseOver')
            if hover_style is not None:
                self.render_style_children(hover_style, key, bounds, inherited, clip, hovered=True)
        child_clip = intersect(clip, rect(bounds)) if (kind == 'ScrollPanel' or
                     self.context == 'economic-overview' and key in self.economic_slot_keys) else clip
        scroll_y = 0
        if kind == 'ScrollPanel':
            if self.context == 'research-tree':
                content_width = node.get('contentWidth')
                scroll_x = node.get('scrollX')
                scroll_y = node.get('scrollY')
                maximum_scroll = max(0.0, content_width - bounds[2]) if type(content_width) in (int, float) else 0
                require(attrs.get('Vertical') == '0' and type(scroll_x) in (int, float) and
                        math.isfinite(scroll_x) and type(scroll_y) in (int, float) and
                        math.isfinite(scroll_y) and scroll_y == 0,
                        'TechTree ScrollPanel lacks captured horizontal-only scroll state')
                require(type(content_width) in (int, float) and math.isfinite(content_width) and
                        content_width >= 0 and 0 <= scroll_x <= maximum_scroll,
                        'TechTree ScrollPanel offset/content range is invalid')
            else:
                content_height = node.get('contentHeight')
                scroll_x = node.get('scrollX')
                scroll_y = node.get('scrollY')
                maximum_scroll = scroll_extent(bounds, content_height) if content_height is not None else 0
                require(type(scroll_x) in (int, float) and math.isfinite(scroll_x) and scroll_x == 0,
                        'Vertical popup ScrollPanel lacks captured zero scrollX')
                if content_height is not None and maximum_scroll > 0:
                    require(type(scroll_y) in (int, float) and math.isfinite(scroll_y) and
                            0 <= scroll_y <= maximum_scroll, 'ScrollPanel lacks captured scrollY state')
        offset = 0
        child_scroll_panel_state = scroll_panel_state
        if self.context in ('production', 'city-view', 'declare-war', 'trade-route', 'social-policy', 'economic-overview', 'notification-panel', 'game-menu', 'save-menu', 'load-menu', 'map-menu') and kind == 'ScrollPanel':
            child_scroll_panel_state = node
        for child in node['children']:
            if child.get('kind') == 'GridData':
                require(kind == 'GridButton',
                        'Original GridData is only supported as a GridButton draw descriptor')
                continue
            is_scrollbar = child['kind'] == 'ScrollBar'
            direction = attrs.get('StackGrowth', 'B') if kind == 'Stack' else None
            stack_y = offset if self.context == 'ranking' and direction in ('B', 'Bottom', 'T', 'Top') else 0
            stack_x = offset if self.context == 'ranking' and direction in ('L', 'Left', 'R', 'Right') else 0
            # Host snapshot x/y already includes the retained ScrollPanel's
            # scroll translation. Only the legacy ranking packet synthesizes
            # its own stack offsets here.
            if kind == 'ScrollPanel' and self.context == 'ranking' and not is_scrollbar:
                stack_y -= scroll_y or 0
            self.node(child, bounds, inherited,
                      clip if is_scrollbar or self.pull_down_scroll_chrome(child, node) else child_clip,
                      stack_y, stack_x=stack_x, scroll_panel_state=child_scroll_panel_state,
                      decoration=decoration if self.context in ('save-menu', 'load-menu') else False,
                      inherited_opacity=inherited_opacity)
            if kind == 'Stack' and not child['hidden']:
                offset += (child['width'] if direction in ('L', 'Left', 'R', 'Right') else child['height']) + int(attrs.get('Padding', '0'))
        if action_alpha_sprite_start is not None and not (node.get('texture') or attrs.get('Texture')):
            # Stock action/menu controls wrap child draw controls in a textureless
            # AlphaAnim. Multiply every descendant sprite, including Grid art.
            opacity = min(1.0, node['animation']['alpha'])
            for index in range(action_alpha_sprite_start, len(self.sprites)):
                sprite = self.sprites[index]
                self.sprites[index] = (*sprite[:-1], sprite[-1] * opacity)
        if (self.context == 'diplomacy' and kind == 'GridButton' and
                isinstance(node.get('text'), str) and node['text']):
            self.leader_button_text(node, attrs, inherited, bounds, clip)
        if self.context in ('game-menu', 'save-menu', *PRIVATE_MENU_CONTEXTS) and kind == 'GridButton' and attrs.get('String'):
            require(node.get('sourceAttributes', {}).get('String') == attrs['String'] and
                    type(node.get('text')) is str and bool(node['text'].strip()),
                    'GameMenu GridButton lost its original localized caption')
            self.label(node, attrs, bounds, inherited, clip, 0,
                       button_bounds=bounds, captured_metrics=False,
                       button_text_meta={'text_control': 'GridButton',
                                         'text_control_id': node.get('id', ''),
                                         'text_placement_policy': 'original menu GridButton bounds center and XML TextOffset',
                                         'retail_text_alignment_verified': False})
        if (self.context in ('load-menu','menu-options') and kind == 'GridButton' and
                (self.context == 'load-menu' or type(node.get('ownerPullDownKey')) is int) and
                isinstance(node.get('text'), str) and node['text'].strip()):
            require((attrs.get('String') and node.get('sourceAttributes', {}).get('String') == attrs['String']) or
                    type(node.get('ownerPullDownKey')) is int,
                    'LoadMenu dynamic button caption has no original control or PullDown owner')
            self.label(node, attrs, bounds, inherited, clip, 0,
                       button_bounds=bounds, captured_metrics=False,
                       button_text_meta={'text_control': 'GridButton',
                                         'text_control_id': node.get('id', ''),
                                         'text_placement_policy': 'original GenericPullDown GridButton bounds and TextOffset',
                                         'retail_text_alignment_verified': False})
        if (self.context == 'trade-route' and kind == 'Button' and
                node.get('id') in self.trade_route_tab_sources):
            self.trade_route_tab_text(node, attrs, inherited, bounds, clip)
        if (self.context == 'social-policy' and kind == 'Button' and
                node.get('id') in self.social_policy_tab_sources):
            self.social_policy_tab_text(node, attrs, inherited, bounds, clip)
        if self.context == 'economic-overview' and kind == 'Button' and attrs.get('String'):
            source = self.economic_button_sources.get((key // ECONOMIC_KEY_SPAN * ECONOMIC_KEY_SPAN,
                                                        node.get('id')))
            require(type(source) is dict and node.get('sourceAttributes') == source and
                    source.get('String') == attrs.get('String') and
                    isinstance(node.get('text'), str) and node['text'].strip(),
                    'EconomicOverview button caption is not its original source String')
            text_attrs = {**attrs, 'Anchor': attrs.get('TextAnchor', 'C,C'),
                          'Offset': attrs.get('TextOffset', '0,0')}
            self.label(node, text_attrs, bounds, inherited, clip, 0, captured_metrics=False,
                       button_text_meta={'text_control': 'Button', 'text_control_id': node['id'],
                                         'text_placement_policy': 'original TextAnchor/TextOffset in retained Button bounds',
                                         'retail_text_alignment_verified': False})
        if self.context in PRIVATE_MENU_CONTEXTS and kind == 'Button' and attrs.get('String'):
            require(node.get('sourceAttributes', {}).get('String') == attrs['String'] and type(node.get('text')) is str,
                    'Private menu tab lost its original localized caption')
            text_attrs = {**attrs, 'Anchor':attrs.get('TextAnchor', 'C,C'), 'Offset':attrs.get('TextOffset', '0,0')}
            self.label(node, text_attrs, bounds, inherited, clip, 0, captured_metrics=False,
                       button_text_meta={'text_control':'Button','text_control_id':node.get('id',''),
                                         'retail_text_alignment_verified':False})
        if (self.context in ('city-view', 'social-policy', 'load-menu', 'menu-options', 'touch-help') and kind in ('CheckBox', 'RadioButton') and
                attrs.get('String') and isinstance(node.get('text'), str) and node['text']):
            self.city_view_toggle_text(node, attrs, inherited, bounds, clip)

    def compile(self, snapshot, *, closed=False):
        require(type(snapshot) is dict and type(closed) is bool, 'Invalid popup scene compilation request')
        if self.context == 'action-info-panel':
            require(not closed, 'ActionInfoPanel is a persistent world overlay, not a closable popup')
            self.action_info_panel_scene = action_info_panel_contract(snapshot, self.context_sources)
        if self.context == 'notification-panel':
            require(not closed, 'NotificationPanel is a persistent world overlay, not a closable popup')
            self.notification_panel_scene = notification_panel_contract(snapshot, self.context_sources)
        if self.context == 'game-menu':
            self.game_menu_scene = game_menu_contract(snapshot, self.context_sources, closed=closed)
        if self.context == 'exit-confirm':
            self.exit_confirm_scene = exit_confirm_contract(snapshot, self.context_sources, closed=closed)
        if self.context == 'save-menu':
            self.save_menu_scene = save_menu_contract(snapshot, self.context_sources, closed=closed)
        if self.context == 'load-menu':
            self.load_menu_scene = load_menu_controls_contract(snapshot, self.context_sources, closed=closed)
        if self.context in PRIVATE_MENU_CONTEXTS:
            self.private_menu_scene = private_menu_contract(snapshot, self.context_sources, context=self.context, closed=closed)
        if self.context == 'pantheon':
            self.pantheon_scene = pantheon_controls_contract(snapshot, self.context_sources, closed=closed)
        if self.context == 'goody-hut-reward':
            self.goody_hut_reward_scene = goody_hut_reward_contract(snapshot, self.context_sources, closed=closed)
        if self.context == 'economic-overview':
            snapshot, proof = compose_economic_overview_snapshot(snapshot, self.economic_overview_prepared)
            self.economic_overview_snapshot, self.economic_overview_scene = snapshot, proof
            self.economic_slot_keys = {row['slot_key'] for row in proof['slots']}
            self.economic_context_keys = {row['context_key'] for row in proof['slots']}
        if closed:
            require(snapshot.get('active') is False and type(snapshot.get('timerSemaphore')) is int and
                    snapshot['timerSemaphore'] == 0, 'Closed popup still has an active context or timer')
            lifecycle = snapshot.get('lifecycle')
            require(type(lifecycle) is list and all(type(value) is str for value in lifecycle),
                    'Closed popup lacks its official completed lifecycle')
            if self.context in SCENE_CONTEXTS:
                if self.context == 'production':
                    require(snapshot.get('contextName') == 'ProductionPopup' and
                            snapshot.get('popupKind') == 'Production' and
                            lifecycle == ['queued', 'shown:16', 'processed:16',
                                          'context-hidden:ProductionPopup'],
                            'ProductionPopup did not complete its official lifecycle')
                elif self.context == 'research':
                    require(snapshot.get('contextName') == 'TechPopup' and snapshot.get('popupKind') == 'Research' and
                            len(lifecycle) == 4 and lifecycle[0] == 'queued' and
                            lifecycle[1] == f'shown:{RESEARCH_POPUP_ENUM_VALUE}' and
                            lifecycle[2:] == ['context-hidden:TechPopup',
                                              f'processed:{RESEARCH_POPUP_ENUM_VALUE}'],
                            'TechPopup did not complete its context-hidden lifecycle for BUTTONPOPUP_CHOOSETECH (11)')
                elif self.context == 'city-capture':
                    require(snapshot.get('contextName') == 'GenericPopup' and
                            snapshot.get('popupKind') == 'CityCapture' and
                            len(lifecycle) >= 4 and lifecycle[0] == 'queued' and lifecycle[-1] == 'closed',
                            'GenericPopup CityCapture did not complete its closed lifecycle')
                elif self.context == 'diplomacy':
                    require(snapshot.get('contextName') == 'diplomacy' and
                            snapshot.get('popupKind') == 'LeaderHead' and
                            lifecycle == ['queued', 'closed'],
                            'LeaderHead did not complete its original return lifecycle')
                elif self.context == 'unit-panel':
                    require(snapshot.get('contextName') == 'UnitPanel' and
                            snapshot.get('popupKind') == 'UnitPanel' and
                            valid_unit_panel_lifecycle(lifecycle, active=False),
                            'UnitPanel hidden state differs from its original world-overlay lifecycle')
                elif self.context == 'city-view':
                    require(snapshot.get('contextName') == 'CityView' and
                            snapshot.get('popupKind') == 'CityView' and
                            lifecycle == ['queued', 'context-hidden:CityView'],
                            'CityView did not complete its original CityView close lifecycle')
                elif self.context == 'tech-award':
                    require(snapshot.get('contextName') == 'TechAwardPopup' and
                            snapshot.get('popupKind') == 'TechAward' and
                            lifecycle == ['queued', f'shown:{TECH_AWARD_POPUP_ENUM_VALUE}',
                                          f'processed:{TECH_AWARD_POPUP_ENUM_VALUE}', 'closed'],
                            'TechAwardPopup did not complete its BUTTONPOPUP_TECH_AWARD lifecycle (68)')
                elif self.context == 'goody-hut-reward':
                    require(self.goody_hut_reward_scene is not None,
                            'GoodyHutReward original closed lifecycle was not validated')
                elif self.context == 'declare-war':
                    require(snapshot.get('contextName') == 'DeclareWarPopup' and
                            snapshot.get('popupKind') == 'DeclareWar' and
                            valid_declare_war_lifecycle(lifecycle, active=False),
                            'DeclareWarPopup did not complete its original Escape/Dequeue lifecycle')
                elif self.context == 'exit-confirm':
                    require(lifecycle == ['modal-pushed', 'closed', 'modal-popped'],
                            'ExitConfirm did not complete its original PopModal lifecycle')
                elif self.context == 'game-menu':
                    require(lifecycle == ['queued', 'closed'],
                            'GameMenu did not complete its original return lifecycle')
                elif self.context == 'save-menu':
                    require(lifecycle == ['queued', 'closed'], 'SaveMenu did not complete its original child return lifecycle')
                elif self.context == 'load-menu':
                    require(lifecycle[0] == 'queued' and lifecycle[-1] == 'closed',
                            'LoadMenu did not complete its original child return lifecycle')
                elif self.context in PRIVATE_MENU_CONTEXTS:
                    require(self.private_menu_scene is not None, 'Private menu closed source contract was not validated')
                elif self.context in ('trade-route', 'social-policy', 'economic-overview', 'pantheon'):
                    expected_closed = (('TradeRoute', 'TradeRoute') if self.context == 'trade-route' else
                                       ('ChoosePantheonPopup', 'Pantheon') if self.context == 'pantheon' else
                                       ('EconomicOverview', 'EconomicOverview') if self.context == 'economic-overview' else
                                       ('SocialPolicyPopup', 'SocialPolicy'))
                    require((snapshot.get('contextName'), snapshot.get('popupKind')) == expected_closed and
                            lifecycle[-1] == 'closed',
                            'Original modal popup did not complete its close lifecycle')
                    if self.context == 'social-policy':
                        state = validate_social_policy_metadata(snapshot.get('socialPolicy'))
                        for field, source_field in (('originalLayoutXml', 'layout_source'),
                                                    ('originalLayoutLua', 'script_source')):
                            ref = state.get(field)
                            expected = self.social_policy_source_contract[source_field]
                            require(type(ref) is dict and ref.get('path') == expected['path'] and
                                    ref.get('sha256') == expected['sha256'],
                                    'Closed SocialPolicy snapshot source provenance differs from installed original ' + field)
                        self.social_policy_state = {
                            'active_player': state['activePlayer'], 'current_tab': state['currentTab'],
                            'policy_info': state['policyInfo'], 'has_city': state['hasCity'],
                            'policy_tab_branch_ids': state['policyTabBranchIds'],
                            'ideology_pane_visible': state['ideologyPaneVisible'],
                            'policy_count': len(state['policies']),
                            'branch_count': len(state['branches']),
                            'branch_switch_confirmation_present': state['branchSwitchConfirmationPresent'],
                            'ideology_change_present': state['ideologyChangePresent'],
                        }
                else:
                    require(snapshot.get('contextName') == 'TechTree' and snapshot.get('popupKind') == 'ResearchTree' and
                            lifecycle == ['queued', f'shown:{RESEARCH_TREE_POPUP_ENUM_VALUE}', 'closed',
                                          f'processed:{RESEARCH_TREE_POPUP_ENUM_VALUE}'],
                            'TechTree did not complete the original BUTTONPOPUP_TECH_TREE lifecycle (67)')
                require(snapshot.get('inputTargets') == [],
                        'Closed popup still exposes registered input targets')
                require(snapshot.get('scrollTargets') == [],
                        'Closed popup still exposes scroll targets')
            else:
                require(len(lifecycle) >= 4 and lifecycle[0] == 'queued' and lifecycle[-1] == 'closed',
                        'Closed popup lacks its official completed lifecycle')
            root = snapshot.get('tree')
            require(type(root) is dict and root.get('kind') == 'Context' and
                    (root.get('width'), root.get('height')) == (self.width, self.height),
                    'Closed popup lacks its original viewport')
            require(not any((self.textures, self.sprites, self.hits, self.scroll_regions,
                             self.geometry, self.labels)),
                    'Closed context compilation requires an unused compiler')
            # Dequeued contexts contribute no paint or input regions. Keep the
            # retained tree untouched; do not fake a hidden-control mutation.
            if self.context in SCENE_CONTEXTS:
                return b'ZSUPIX02' + struct.pack('<6I', self.width, self.height, 0, 0, 0, 0)
            return b'ZSUPIX01' + struct.pack('<5I', self.width, self.height, 0, 0, 0)
        require(not (closed and self.context == 'top-panel'),
                'The persistent TopPanel world overlay is not a closable popup scene')
        expected_timer = 1 if self.context in ('ranking', 'research-tree', 'tech-award', 'goody-hut-reward', 'declare-war', 'trade-route', 'social-policy', 'economic-overview', 'game-menu') else 0
        require(snapshot.get('active') is True and snapshot.get('timerSemaphore') == expected_timer,
                'Snapshot is not a shown active popup for the selected context')
        if self.context in SCENE_CONTEXTS:
            expected_name, expected_kind = (('ProductionPopup', 'Production') if self.context == 'production'
                                            else ('TechPopup', 'Research') if self.context == 'research'
                                            else ('TechTree', 'ResearchTree') if self.context == 'research-tree'
                                            else ('TechAwardPopup', 'TechAward') if self.context == 'tech-award'
                                            else ('GoodyHutPopup', 'GoodyHutReward') if self.context == 'goody-hut-reward'
                                            else ('GenericPopup', 'CityCapture') if self.context == 'city-capture'
                                            else ('diplomacy', 'LeaderHead') if self.context == 'diplomacy'
                                            else ('CityView', 'CityView') if self.context == 'city-view'
                                            else ('UnitPanel', 'UnitPanel') if self.context == 'unit-panel'
                                            else ('TopPanel', 'TopPanel') if self.context == 'top-panel'
                                            else ('TradeRoute', 'TradeRoute') if self.context == 'trade-route'
                                            else ('SocialPolicyPopup', 'SocialPolicy') if self.context == 'social-policy'
                                            else ('EconomicOverview', 'EconomicOverview') if self.context == 'economic-overview'
                                            else ('ActionInfoPanel', 'ActionInfoPanel') if self.context == 'action-info-panel'
                                            else ('NotificationPanel', 'NotificationPanel') if self.context == 'notification-panel'
                                            else ('ExitConfirm', 'ExitConfirm') if self.context == 'exit-confirm'
                                            else ('GameMenu', 'GameMenu') if self.context == 'game-menu'
                                            else ('SaveMenu', 'SaveMenu') if self.context == 'save-menu'
                                            else ('LoadMenu', 'LoadMenu') if self.context == 'load-menu'
                                            else PRIVATE_MENU_CONTEXTS[self.context][:2] if self.context in PRIVATE_MENU_CONTEXTS
                                            else ('DeclareWarPopup', 'DeclareWar'))
            require(snapshot.get('contextName') == expected_name and snapshot.get('popupKind') == expected_kind,
                    'Snapshot does not identify the selected official popup context')
            if self.context == 'research-tree':
                lifecycle = snapshot.get('lifecycle')
                require(lifecycle == ['queued', f'shown:{RESEARCH_TREE_POPUP_ENUM_VALUE}'],
                        'TechTree active lifecycle differs from original BUTTONPOPUP_TECH_TREE (67)')
            elif self.context == 'tech-award':
                require(snapshot.get('lifecycle') == ['queued', f'shown:{TECH_AWARD_POPUP_ENUM_VALUE}'],
                        'TechAwardPopup active lifecycle differs from original BUTTONPOPUP_TECH_AWARD (68)')
            elif self.context == 'goody-hut-reward':
                require(self.goody_hut_reward_scene is not None,
                        'GoodyHutReward original modal lifecycle was not validated')
            elif self.context == 'diplomacy':
                require(snapshot.get('lifecycle') == ['queued'],
                        'LeaderHead intro must remain in its original queued active state')
            elif self.context == 'unit-panel':
                panel = snapshot.get('unitPanel')
                lifecycle = snapshot.get('lifecycle')
                require(valid_unit_panel_lifecycle(lifecycle, active=True) and
                        type(panel) is dict and panel.get('visible') is True and
                        panel.get('contextHidden') is False and
                        type(panel.get('smallUIAssets')) is bool and
                        panel.get('smallUIAssets') == (panel.get('layoutVariant') == 'small') and
                        panel.get('retailLayoutVariantSelectionVerified') is False and
                        snapshot.get('hasRetainedUnitUi') is True,
                        'UnitPanel snapshot does not preserve its active selected-unit world overlay')
                base_nodes = []
                full_view_nodes = []
                def find_unit_panel_base(node):
                    if node.get('id') == 'Base':
                        base_nodes.append(node)
                    if (node.get('kind') != 'Context' and
                            (node.get('x'), node.get('y'), node.get('width'), node.get('height')) ==
                            (0, 0, self.width, self.height)):
                        full_view_nodes.append(node)
                    for child in node.get('children', []):
                        find_unit_panel_base(child)
                find_unit_panel_base(snapshot['tree'])
                if self.unit_panel_layout_variant == 'default':
                    require(len(base_nodes) == 1 and base_nodes[0].get('kind') == 'Box' and
                            base_nodes[0].get('attributes', {}).get('Color') == '0,0,0,0' and
                            (base_nodes[0].get('x'), base_nodes[0].get('y'),
                             base_nodes[0].get('width'), base_nodes[0].get('height')) ==
                            (0, 0, self.width, self.height),
                            'UnitPanel original full-viewport Base must remain transparent over the world')
                else:
                    require(not base_nodes and not full_view_nodes,
                            'Small UnitPanel must retain its original partial world-overlay layout')
            elif self.context == 'city-view':
                require(snapshot.get('lifecycle') == ['queued'],
                        'CityView lifecycle differs from its original enter-city-screen path')
            elif self.context == 'top-panel':
                panel = snapshot.get('topPanel')
                require(snapshot.get('nonmodal') is True and
                        type(snapshot.get('timerSemaphores')) is int and snapshot['timerSemaphores'] == 0 and
                        type(panel) is dict and set(panel) == {'activePlayer', 'nonmodal', 'timerSemaphores'} and
                        type(panel.get('activePlayer')) is int and panel['activePlayer'] >= 0 and
                        panel.get('nonmodal') is True and type(panel.get('timerSemaphores')) is int and
                        panel['timerSemaphores'] == 0 and snapshot.get('timerSemaphore') == 0,
                        'TopPanel snapshot differs from the retained persistent nonmodal world-overlay contract')
                tooltip = snapshot.get('topPanelTooltip')
                if tooltip is not None:
                    require(type(tooltip) is dict and
                            set(tooltip) == {'type', 'tree', 'retailPlacementVerified', 'retailAutosizeVerified'} and
                            tooltip.get('type') == 'TooltipTypeTopPanel' and
                            type(tooltip.get('tree')) is dict and tooltip['tree'].get('kind') == 'Grid' and
                            tooltip.get('retailPlacementVerified') is False and
                            tooltip.get('retailAutosizeVerified') is False,
                            'TopPanel original tooltip tree has malformed or overstated placement/autosize metadata')
                self.top_panel_interaction_contract = top_panel_interaction_contract(snapshot)
            elif self.context == 'trade-route':
                lifecycle = snapshot.get('lifecycle')
                require(type(lifecycle) is list and len(lifecycle) == 2 and
                        lifecycle[0] == 'queued' and
                        re.fullmatch(r'shown:[0-9]+', lifecycle[1]) is not None,
                            'TradeRoute snapshot lacks its active queued/shown lifecycle')
                route = snapshot.get('tradeRoute')
                require(type(route) is dict and route.get('modal') is True and
                        route.get('timerSemaphore') == 1 and route.get('rowTemplate') == 'TRInstance' and
                        route.get('rowSelectionPresent') is False and
                        type(route.get('activePlayer')) is int and route['activePlayer'] >= 0 and
                        route.get('selectedTab') in ('YourTR', 'AvailableTR', 'TRWithYou') and
                        type(route.get('visibleRowCount')) is int and route['visibleRowCount'] >= 0,
                        'TradeRoute snapshot differs from the original modal timer and nonselectable-row contract')
                helper_path = self.game_root / 'Assets/DLC/Expansion2/UI/InGame/Popups/TradeRouteHelpers.lua'
                for field, path in (('originalLayoutXml', self.layout_path),
                                    ('originalLayoutLua', self.script_path),
                                    ('originalHelpersLua', helper_path)):
                    provenance = route.get(field)
                    require(type(provenance) is dict and
                            Path(provenance.get('path', '')).resolve(strict=True) == path.resolve(strict=True) and
                            provenance.get('sha256') == self.context_sources[path],
                            f'TradeRoute snapshot {field} provenance differs from the installed original source')
                stacks = []
                def find_trade_stack(node):
                    if type(node) is dict:
                        if node.get('id') == 'MainStack':
                            stacks.append(node)
                        for child in node.get('children', []):
                            find_trade_stack(child)
                find_trade_stack(snapshot.get('tree'))
                require(len(stacks) == 1 and stacks[0].get('kind') == 'Stack',
                        'TradeRoute snapshot lacks its unique original MainStack')
                retained_row_count = len(stacks[0].get('children', []))
                require(retained_row_count == route['visibleRowCount'],
                        'TradeRoute visible row count differs from its original MainStack children')
                selected_tabs = []
                def find_selected_trade_tabs(node):
                    if type(node) is dict and node.get('id') in ('YourTRSelectHighlight',
                            'AvailableTRSelectHighlight', 'TRWithYouSelectHighlight') and node.get('hidden') is False:
                        selected_tabs.append(node.get('id'))
                    if type(node) is dict:
                        for child in node.get('children', []):
                            find_selected_trade_tabs(child)
                find_selected_trade_tabs(snapshot.get('tree'))
                require(len(selected_tabs) == 1,
                        'TradeRoute must retain exactly one selected original tab highlight')
                selected_tab = {
                    'YourTRSelectHighlight': 'YourTR',
                    'AvailableTRSelectHighlight': 'AvailableTR',
                    'TRWithYouSelectHighlight': 'TRWithYou',
                }[selected_tabs[0]]
                require(selected_tab == route['selectedTab'],
                        'TradeRoute selected tab diagnostic differs from its original visible highlight')
                template = ET.parse(self.layout_path).getroot().find("Instance[@Name='TRInstance']")
                expected_row_controls = {}
                for source_node in template.iter():
                    control_id = source_node.attrib.get('ID')
                    if control_id:
                        expected_row_controls[control_id] = source_node.tag
                row_tooltips = []
                for row_index, row in enumerate(stacks[0]['children']):
                    actual_row_controls = {}
                    def collect_trade_row(node):
                        if type(node) is dict:
                            tooltip = node.get('tooltip')
                            require(tooltip is None or type(tooltip) is str,
                                    f'TradeRoute row {row_index} has a malformed original runtime tooltip')
                            if tooltip:
                                row_tooltips.append({'key': node.get('key'), 'id': node.get('id', ''),
                                                     'sha256': hashlib.sha256(tooltip.encode('utf-8')).hexdigest()})
                            source = node.get('sourceAttributes')
                            control_id = source.get('ID') if type(source) is dict else None
                            if control_id:
                                require(control_id not in actual_row_controls and
                                        node.get('kind') == expected_row_controls.get(control_id),
                                        f'TradeRoute row {row_index} changed original control identity')
                                actual_row_controls[control_id] = node.get('kind')
                            for child in node.get('children', []):
                                collect_trade_row(child)
                    collect_trade_row(row)
                    require(actual_row_controls == expected_row_controls,
                            f'TradeRoute row {row_index} is not a complete original TRInstance tree')
                expected_targets = set(self.trade_route_source_contract['tab_control_ids'] +
                                       self.trade_route_source_contract['sortable_header_ids'] + ['CloseButton'])
                actual_targets = [target for target in snapshot['inputTargets'] if type(target) is dict]
                require(len(actual_targets) == len(expected_targets) and
                        {target.get('id') for target in actual_targets} == expected_targets and
                        all(target.get('event') == 'LeftClick' for target in actual_targets),
                        'TradeRoute input targets differ from its original three tabs, sort headers and CloseButton')
                self.trade_route_snapshot_state = route
                self.trade_route_state = {'active_player': route.get('activePlayer'), 'selected_tab': selected_tab,
                                          'retained_row_count': retained_row_count,
                                          'row_tooltips': row_tooltips,
                                          'row_selection_present': False}
            elif self.context == 'declare-war':
                require(valid_declare_war_lifecycle(snapshot.get('lifecycle'), active=True),
                        'DeclareWar active lifecycle differs from original queued/shown/processed ordering')
            elif self.context == 'economic-overview':
                lifecycle = snapshot.get('lifecycle')
                require(type(lifecycle) is list and len(lifecycle) == 2 and lifecycle[0] == 'queued' and
                        re.fullmatch(r'shown:[0-9]+', lifecycle[1]) is not None,
                        'EconomicOverview lacks its original queued/shown modal lifecycle')
            elif self.context == 'pantheon':
                require(self.pantheon_scene is not None, 'Pantheon source contract was not validated')
            elif self.context == 'social-policy':
                    lifecycle = snapshot.get('lifecycle')
                    require(type(lifecycle) is list and len(lifecycle) == 2 and
                            lifecycle[0] == 'queued' and re.fullmatch(r'shown:[0-9]+', lifecycle[1]) is not None,
                            'SocialPolicy snapshot lacks its active original queued/shown lifecycle')
                    state = validate_social_policy_metadata(snapshot.get('socialPolicy'))
                    controls = []
                    def collect_social_policy_controls(node):
                        controls.append(node)
                        for child in node.get('children', []):
                            collect_social_policy_controls(child)
                    collect_social_policy_controls(snapshot['tree'])
                    def single_control(control_id):
                        matches = [node for node in controls if node.get('id') == control_id]
                        require(len(matches) == 1,
                                'SocialPolicy retained tree lacks a unique original ' + control_id)
                        return matches[0]
                    social_tab = state['currentTab'] == 'SocialPolicies'
                    ideology_tab = state['currentTab'] == 'Ideologies'
                    require(single_control('PolicyInfo').get('checked') is state['policyInfo'] and
                            single_control('TabButtonSocialPoliciesHL').get('hidden') is (not social_tab) and
                            single_control('TabButtonIdeologiesHL').get('hidden') is (not ideology_tab) and
                            single_control('SocialPolicyPane').get('hidden') is (not social_tab) and
                            single_control('IdeologyPane').get('hidden') is (not state['ideologyPaneVisible']),
                            'SocialPolicy tab or PolicyInfo metadata differs from captured original widget state')
                    ideology_confirm = [node for node in controls if node.get('id') == 'ChangeIdeologyConfirm']
                    require(len(ideology_confirm) == 1 and
                            (ideology_confirm[0].get('hidden') is False) == state['ideologyChangePresent'],
                            'SocialPolicy ideology-change confirmation flag differs from original retained control visibility')
                    for field, source_field in (('originalLayoutXml', 'layout_source'),
                                                ('originalLayoutLua', 'script_source')):
                        ref = state.get(field)
                        expected = self.social_policy_source_contract[source_field]
                        require(type(ref) is dict and ref.get('path') == expected['path'] and
                                ref.get('sha256') == expected['sha256'],
                                'SocialPolicy snapshot source provenance differs from the installed original ' + field)
                    self.social_policy_state = {
                        'active_player': state['activePlayer'], 'current_tab': state['currentTab'],
                        'policy_info': state['policyInfo'], 'has_city': state['hasCity'],
                        'policy_tab_branch_ids': state['policyTabBranchIds'],
                        'ideology_pane_visible': state['ideologyPaneVisible'],
                        'policy_count': len(state['policies']), 'branch_count': len(state['branches']),
                        'branch_switch_confirmation_present': state['branchSwitchConfirmationPresent'],
                        'ideology_change_present': state['ideologyChangePresent'],
                    }
            require(snapshot.get('presentationClock') == self.snapshot_clock,
                    'Popup snapshot clock differs from the selected compiler clock')
            require(snapshot.get('animationPolicy') == 'ZEROSIS_FRONTEND_XML_TIMELINE_V1' and
                    snapshot.get('retailTimingVerified') is False,
                    'Popup snapshot animation policy/proof boundary is missing or overstated')
            metrics = snapshot.get('fontMetrics')
            require(type(metrics) is dict and metrics.get('policy') == 'CIV5_GLYPHGEN_GGXML_LAYOUT_V1' and
                    metrics.get('retailMetricSemanticsVerified') is False and
                    metrics.get('wrapPolicy') == 'GREEDY_ASCII_SPACE_WORD_WRAP_SPLIT_LONG_WORD_AT_CODEPOINT',
                    'Popup snapshot font metric policy/proof boundary is missing or overstated')
            targets = snapshot.get('inputTargets')
            require(type(targets) is list, 'Popup snapshot lacks registered inputTargets')
            self.production_font_metrics = metrics
            self.production_input_targets = targets
            scroll_targets = snapshot.get('scrollTargets')
            require(type(scroll_targets) is list, 'Popup snapshot lacks captured scrollTargets')
            self.production_scroll_targets = scroll_targets
        before = copy.deepcopy(snapshot)
        if self.context == 'city-view':
            self.validate_city_view_context_font_defaults(snapshot)
        if self.context in SCENE_CONTEXTS:
            # Scrollbar rendering crosschecks its captured range against the
            # already validated owning ScrollPanel target.
            self.production_scrolls(snapshot['tree'])
            if self.context == 'city-view':
                self.validate_city_view_payload(snapshot)
        self.node(snapshot['tree'], (0, 0, self.width, self.height), {}, (0, 0, self.width, self.height))
        if self.context in SCENE_CONTEXTS:
            self.production_hits(snapshot['tree'])
        if self.context == 'economic-overview':
            require(all(sprite[1] in self.keys for sprite in self.sprites),
                    'EconomicOverview draw owner key escapes its rebased original control tree')
        require(snapshot == before, 'Presentation modified retained GameCore UI state')
        validate_hit_regions(self.context, self.hits, self.geometry,
                             allow_empty_notification=(self.context == 'notification-panel' and
                                                       self.notification_panel_scene['zero_hit_regions_are_originally_valid']))
        require(len(self.textures) <= 64 and len(self.sprites) <= 10000, 'Unbounded scene packet')
        if self.context in SCENE_CONTEXTS:
            blob = bytearray(b'ZSUPIX02' + struct.pack('<6I', self.width, self.height,
                              len(self.textures), len(self.sprites), len(self.hits), len(self.scroll_regions)))
        else:
            blob = bytearray(b'ZSUPIX01' + struct.pack('<5I', self.width, self.height,
                              len(self.textures), len(self.sprites), len(self.hits)))
        for path in self.textures:
            # Keep the scene relocatable together with its bounded candidate atlases.
            raw = str(Path(path).relative_to(self.destination)).replace('\\', '/').encode('utf-8')
            require(0 < len(raw) < 4096, 'Invalid scene texture path length')
            blob += struct.pack('<I', len(raw)) + raw
        for sprite in self.sprites:
            blob += struct.pack('<IQ16f', *sprite)
        for hit in self.hits:
            blob += struct.pack('<Q4f', *hit)
        for region in self.scroll_regions:
            blob += struct.pack('<Q4f', *region)
        return bytes(blob)

    def unchanged(self):
        if (not self.assets.unchanged() or sha256(self.styles_path) != self.styles_hash or
                any(sha256(path) != digest for path, digest in self.context_sources.items())):
            return False
        return all(Path(row['path']).is_file() and sha256(row['path']) == row['sha256']
                   for row in self.derived_textures) and all(sha256(row['ggxml_path']) == row['ggxml_sha256'] and
                   sha256(row['color_atlas_path']) == row['color_atlas_sha256'] and
                   all(sha256(sheet['source_path']) == sheet['source_sha256'] for sheet in row['sheets'])
                   for row in self.font_records)
