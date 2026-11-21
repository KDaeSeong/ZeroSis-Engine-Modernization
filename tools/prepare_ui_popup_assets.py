"""Freeze selected installed Civ V popups and compile their XML control trees.

Only the explicitly selected context is supported. This is asset preparation,
not evidence that the original UI engine's layout or dispatch order is matched.
"""
import json
import hashlib
import math
import shutil
import struct
import xml.etree.ElementTree as ET
from pathlib import Path

from collect_baseline import PROJECT, digest
from probe_world_builder import artifact
from ui_bitmap_fonts import load_font
from civ5_ui_assets import Fpk, UiAssets, observed_load_menu_check_defaults
from ui_font_profile import (PROFILE_PATH, BANK_SCHEMA, load_font_profile, profile_input_root,
                             verify_profile_inputs, intern_font_metrics)

GAME = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Sid Meier's Civilization V")
GAME_MENU_LUA = 'Assets/UI/InGame/Menus/GameMenu.lua'
GAME_MENU_XML = 'Assets/DLC/Expansion2/UI/InGame/Menus/GameMenu.xml'
SAVE_MENU_LUA = 'Assets/UI/InGame/Menus/SaveMenu.lua'
SAVE_MENU_XML = 'Assets/UI/InGame/Menus/SaveMenu.xml'
LOAD_MENU_LUA = 'Assets/UI/FrontEnd/LoadMenu.lua'
LOAD_MENU_XML = 'Assets/UI/FrontEnd/LoadMenu.xml'
EXIT_CONFIRM_LUA = 'Assets/UI/FrontEnd/ExitConfirm.lua'
EXIT_CONFIRM_XML = 'Assets/UI/FrontEnd/ExitConfirm.xml'
TOUCH_HELP_LUA = 'Assets/UI/TouchControlsMenu.lua'
TOUCH_HELP_XML = 'Assets/UI/TouchControlsMenu.xml'
MAP_MENU_LUA = 'Assets/UI/InGame/Menus/SaveMapMenu.lua'
MAP_MENU_XML = 'Assets/UI/InGame/Menus/SaveMapMenu.xml'
MAP_MENU_SOURCE_IDENTITIES = {
    'lua': (MAP_MENU_LUA, 8537, '2b5121a0ee4be0c909d7f0526b2f8a4cb2b265b21df6ad0e62e5a12da5d83550'),
    'xml': (MAP_MENU_XML, 6685, '8c48b02d5241874995350dc65d2348e61f5af67c92916d2be915bf5fc6e3e826'),
}
EXIT_CONFIRM_SOURCE_IDENTITIES = {
    'lua': (EXIT_CONFIRM_LUA, 1929,
            '7682db382ff5e1dc104165ba1d8a787d8e64e75fb1e550f223f2bb40ef08a5ae'),
    'xml': (EXIT_CONFIRM_XML, 1510,
            '6d9794963c43a2df9de43974c219fb35d9423071ec1b98c8c2a24b696d09fe32'),
}
PANTHEON_SOURCE_IDENTITIES = {
    'lua': ('Assets/DLC/Expansion2/UI/InGame/Popups/ChoosePantheonPopup.lua', 7854,
            '23a7205f1966347b52cd79c163a396f6252e3c756da609e2cebb7a8866c31bcf'),
    'xml': ('Assets/DLC/Expansion2/UI/InGame/Popups/ChoosePantheonPopup.xml', 5357,
            '6408228e6a85b428125d38109419abfa0ef422b3694534c8b311c1a5a784e74c'),
}
GOODY_HUT_SOURCE_IDENTITIES = {
    'lua': ('Assets/DLC/Expansion2/UI/InGame/Popups/GoodyHutPopup.lua', 2877,
            '633ddaa3497d3fcf40892481878806e819e4009f3c5a20421d9a7868f035ff5c'),
    'xml': ('Assets/DLC/Expansion2/UI/InGame/Popups/GoodyHutPopup.xml', 1466,
            '479aaf644a5c93300f3d0baeff5515accdff6a9093dc9c285621a5837e27b6ee'),
}


def pantheon_original_sources(game_root=GAME):
    """Bind only the two inspected immutable original Pantheon inputs."""
    result = {}
    for key, (relative, size, sha) in PANTHEON_SOURCE_IDENTITIES.items():
        path = Path(game_root) / relative
        if path.stat().st_size != size or digest(path) != sha:
            raise ValueError('Original Pantheon source identity changed: ' + relative)
        result[key] = {'path': str(path), 'bytes': size, 'sha256': sha}
    return result


def goody_hut_original_sources(game_root=GAME):
    """Bind the unchanged BNW informational reward popup to inspected inputs."""
    result = {}
    for key, (relative, size, sha) in GOODY_HUT_SOURCE_IDENTITIES.items():
        path = Path(game_root) / relative
        if path.stat().st_size != size or digest(path) != sha:
            raise ValueError('Original GoodyHut source identity changed: ' + relative)
        result[key] = {'path': str(path), 'bytes': size, 'sha256': sha}
    return result


def exit_confirm_original_sources(game_root=GAME):
    """Bind the unchanged original exit modal to its two inspected inputs."""
    result = {}
    for key, (relative, size, sha) in EXIT_CONFIRM_SOURCE_IDENTITIES.items():
        path = Path(game_root) / relative
        if path.stat().st_size != size or digest(path) != sha:
            raise ValueError('Original ExitConfirm source identity changed: ' + relative)
        result[key] = {'path': str(path), 'bytes': size, 'sha256': sha}
    return result

UNIQUE_BONUSES_LUA = 'Assets/UI/FrontEnd/GameSetup/UniqueBonuses.lua'
MAP_UTILITIES_LUA = 'Assets/Gameplay/Lua/MapUtilities.lua'
SCRIPTS = (
    ('InstanceManager', 'Assets/UI/InstanceManager.lua'),
    ('IconSupport', 'Assets/UI/IconSupport.lua'),
    ('FLuaVector', 'Assets/Gameplay/Lua/FLuaVector.lua'),
    ('TechButtonInclude', 'Assets/DLC/Expansion2/UI/InGame/TechTree/TechButtonInclude.lua'),
    ('TechHelpInclude', 'Assets/DLC/Expansion2/UI/InGame/TechTree/TechHelpInclude.lua'),
    ('TechTree', 'Assets/DLC/Expansion2/UI/TechTree/TechTree.lua'),
    ('WhosWinningPopup', 'Assets/DLC/Expansion2/UI/InGame/Popups/WhosWinningPopup.lua'),
    ('GenericPopup', 'Assets/UI/InGame/Popups/GenericPopup.lua'),
    ('EmptyPopup', 'Assets/UI/InGame/Popups/EmptyPopup.lua'),
    ('PuppetCityPopup', 'Assets/DLC/Expansion2/UI/InGame/PopupsGeneric/PuppetCityPopup.lua'),
    ('GameplayUtilities', 'Assets/Gameplay/Lua/GameplayUtilities.lua'),
    ('CityView', 'Assets/DLC/Expansion2/UI/InGame/CityView/CityView.lua'),
    ('SupportFunctions', 'Assets/UI/SupportFunctions.lua'),
    ('LeaderHeadRoot', 'Assets/DLC/Expansion2/UI/InGame/LeaderHead/LeaderHeadRoot.lua'),
    ('InfoTooltipInclude', 'Assets/DLC/Expansion2/UI/InGame/InfoTooltipInclude.lua'),
    ('ProductionPopup', 'Assets/DLC/Expansion2/UI/InGame/Popups/ProductionPopup.lua'),
    ('TechPopup', 'Assets/DLC/Expansion2/UI/InGame/TechPopup.lua'),
    ('CommonBehaviors', 'Assets/UI/CommonBehaviors.lua'),
    ('DeclareWarPopup', 'Assets/DLC/Expansion2/UI/InGame/Popups/DeclareWarPopup.lua'),
    # BNW inherits the base TechAwardPopup Lua and supplies an Expansion2 XML override.
    ('TechAwardPopup', 'Assets/UI/InGame/Popups/TechAwardPopup.lua'),
    ('GoodyHutPopup', GOODY_HUT_SOURCE_IDENTITIES['lua'][0]),
    ('UnitPanel', 'Assets/DLC/Expansion2/UI/InGame/WorldView/UnitPanel.lua'),
    ('TopPanel', 'Assets/DLC/Expansion2/UI/InGame/TopPanel.lua'),
    ('TradeRouteOverview', 'Assets/DLC/Expansion2/UI/InGame/Popups/TradeRouteOverview.lua'),
    ('TradeRouteHelpers', 'Assets/DLC/Expansion2/UI/InGame/Popups/TradeRouteHelpers.lua'),
    ('SocialPolicyPopup', 'Assets/DLC/Expansion2/UI/InGame/Popups/SocialPolicyPopup.lua'),
    ('ChoosePantheonPopup', 'Assets/DLC/Expansion2/UI/InGame/Popups/ChoosePantheonPopup.lua'),
    ('EconomicOverview', 'Assets/UI/InGame/Popups/EconomicOverview.lua'),
    ('EconomicGeneralInfo', 'Assets/DLC/Expansion2/UI/InGame/Popups/EconomicGeneralInfo.lua'),
    ('HappinessInfo', 'Assets/DLC/Expansion2/UI/InGame/Popups/HappinessInfo.lua'),
    ('ActionInfoPanel', 'Assets/DLC/Expansion2/UI/InGame/WorldView/ActionInfoPanel.lua'),
    ('NotificationPanel', 'Assets/DLC/Expansion2/UI/InGame/WorldView/NotificationPanel.lua'),
    # BNW inherits the base GameMenu Lua and supplies its Expansion2 layout.
    ('MapUtilities', MAP_UTILITIES_LUA),
    ('GameMenu', GAME_MENU_LUA),
    ('UniqueBonuses', UNIQUE_BONUSES_LUA),
    ('SaveMenu', SAVE_MENU_LUA),
    ('LoadMenu', LOAD_MENU_LUA),
    ('ExitConfirm', EXIT_CONFIRM_LUA),
    ('TouchControlsMenu', TOUCH_HELP_LUA),
    ('SaveMapMenu', MAP_MENU_LUA),
)
XML = 'Assets/DLC/Expansion2/UI/InGame/Popups/WhosWinningPopup.xml'
DECLARE_WAR_XML = 'Assets/DLC/Expansion2/UI/InGame/Popups/DeclareWarPopup.xml'
LAYOUTS = (
    ('WhosWinningLayout', XML, None),
    ('GenericPopupLayout', 'Assets/UI/InGame/Popups/GenericPopup.xml', 'CityCapture'),
    ('EmptyPopupLayout', 'Assets/UI/InGame/Popups/EmptyPopup.xml', None),
    ('ProductionLayout', 'Assets/DLC/Expansion2/UI/InGame/Popups/ProductionPopup.xml', 'Production'),
    ('TechLayout', 'Assets/DLC/Expansion2/UI/InGame/TechPopup.xml', 'Research'),
    ('TechAwardLayout', 'Assets/DLC/Expansion2/UI/InGame/Popups/TechAwardPopup.xml', 'TechAward'),
    ('GoodyHutRewardLayout', GOODY_HUT_SOURCE_IDENTITIES['xml'][0], 'GoodyHutReward'),
    ('TechTreeLayout', 'Assets/DLC/Expansion2/UI/InGame/TechTree/TechTree.xml', 'ResearchTree'),
    ('LeaderHeadRootLayout', 'Assets/DLC/Expansion2/UI/InGame/LeaderHead/LeaderHeadRoot.xml', 'LeaderHead'),
    ('CityViewLayout', 'Assets/DLC/Expansion2/UI/InGame/CityView/CityView.xml', 'CityView'),
    ('CityViewSmallLayout', 'Assets/DLC/Expansion2/UI/InGame/CityView/CityView_small.xml', 'CityView'),
    ('UnitPanelLayout', 'Assets/DLC/Expansion2/UI/InGame/WorldView/UnitPanel.xml', 'UnitPanel'),
    ('UnitPanelSmallLayout', 'Assets/DLC/Expansion2/UI/InGame/WorldView/UnitPanel_small.xml', 'UnitPanel'),
    ('DeclareWarLayout', DECLARE_WAR_XML, 'DeclareWar'),
    ('TopPanelLayout', 'Assets/DLC/Expansion2/UI/InGame/TopPanel.xml', 'TopPanel'),
    ('TradeRouteLayout', 'Assets/DLC/Expansion2/UI/InGame/Popups/TradeRouteOverview.xml', 'TradeRoute'),
    ('SocialPolicyLayout', 'Assets/DLC/Expansion2/UI/InGame/Popups/SocialPolicyPopup.xml', 'SocialPolicy'),
    ('PantheonLayout', 'Assets/DLC/Expansion2/UI/InGame/Popups/ChoosePantheonPopup.xml', 'Pantheon'),
    ('EconomicOverviewLayout', 'Assets/DLC/Expansion2/UI/InGame/Popups/EconomicOverview.xml', 'EconomicOverview'),
    ('EconomicGeneralLayout', 'Assets/DLC/Expansion2/UI/InGame/Popups/EconomicGeneralInfo.xml', 'EconomicGeneral'),
    ('EconomicHappinessLayout', 'Assets/DLC/Expansion2/UI/InGame/Popups/HappinessInfo.xml', 'EconomicHappiness'),
    ('ActionInfoPanelLayout', 'Assets/DLC/Expansion2/UI/InGame/WorldView/ActionInfoPanel.xml', 'ActionInfoPanel'),
    ('NotificationPanelLayout', 'Assets/DLC/Expansion2/UI/InGame/WorldView/NotificationPanel.xml', 'NotificationPanel'),
    ('GameMenuLayout', GAME_MENU_XML, 'GameMenu'),
    ('SaveMenuLayout', SAVE_MENU_XML, 'SaveMenu'),
    ('LoadMenuLayout', LOAD_MENU_XML, 'LoadMenu'),
    ('ExitConfirmLayout', EXIT_CONFIRM_XML, 'ExitConfirm'),
    ('MenuOptionsLayout', 'Assets/UI/Options/OptionsMenu.xml', 'MenuOptions'),
    ('TouchHelpLayout', TOUCH_HELP_XML, 'TouchHelp'),
    ('MapMenuLayout', MAP_MENU_XML, 'MapMenu'),
)
SOURCE_ASSETS = (
    ('DiscussionDialog', 'Assets/DLC/Expansion2/UI/InGame/LeaderHead/DiscussionDialog.lua'),
    ('DiscussionDialogLayout', 'Assets/DLC/Expansion2/UI/InGame/LeaderHead/DiscussionDialog.xml'),
    ('DiploTrade', 'Assets/UI/InGame/LeaderHead/DiploTrade.lua'),
    ('DiploTradeLayout', 'Assets/DLC/Expansion2/UI/InGame/LeaderHead/DiploTrade.xml'),
)
KINDS = {'Context', 'Instance', 'Box', 'Image', 'Label', 'Grid', 'ScrollPanel',
         'Stack', 'ScrollBar', 'GridButton', 'Button', 'Container', 'AlphaAnim',
         'DownButton', 'UpButton', 'Meter', 'ScrollAnim', 'ShowOnMouseOver', 'HideOnMouseOver', 'TextureBar', 'GridData',
         'TextButton', 'LuaContext', 'CheckBox', 'RadioButton', 'WorldAnchor', 'FlipAnim', 'SlideAnim', 'Bar', 'EditBox', 'PullDown'}

ICON_MAPPING_FILES = (
    'Assets/Gameplay/XML/GameInfo/CIV5IconFontMapping.xml',
    'Assets/DLC/Expansion2/Gameplay/XML/GameInfo/CIV5IconFontMapping_Expansion2.xml',
)
STYLE_SOURCE = 'Assets/UI/Styles.xml'
ICON_FONTS = {
    'FontIcons': 'Assets/DLC/Expansion2/UI/Fonts/Font Icons/FontIcons.ggxml',
    'FontIcons_Expansion2': 'Assets/DLC/Expansion2/UI/Fonts/Font Icons/FontIcons_Expansion2.ggxml',
    'FontIcons_DLC_07': 'Assets/DLC/Shared/UI/Art/Fonts/Font Icons/FontIcons_DLC_07.ggxml',
}
SOUND_SCRIPT_XML = 'Assets/Sounds/XML/Audio2DScripts.xml'
SOUND_DEFINES_XML = 'Assets/Sounds/XML/AudioDefines.xml'
BUY_TILE_SCRIPT_ID = 'AS2D_INTERFACE_BUY_TILE'
BUY_TILE_SOUND_ID = 'SND_INTERFACE_BUY_TILE'
BUY_TILE_FILENAME = 'NotificationBuyTile'
BUY_TILE_FPK_ENTRY = 'notificationbuytile.wav'
BUY_TILE_MIN_MAX_VOLUME = 60
BUY_TILE_MAX_ACTIVE = 1
PURCHASE_AUDIO = (
    {'script_id': 'AS2D_INTERFACE_BUY_TILE', 'sound_id': 'SND_INTERFACE_BUY_TILE',
     'filename': 'NotificationBuyTile', 'fpk_entry': 'notificationbuytile.wav',
     'volume': 60, 'script_xml': SOUND_SCRIPT_XML, 'defines_xml': SOUND_DEFINES_XML,
     'xml_label': 'Audio2DScripts.xml/AudioDefines.xml', 'duplicate_limit': 1},
    {'script_id': 'AS2D_INTERFACE_CITY_SCREEN_PURCHASE', 'sound_id': 'SND_INTERFACE_CITY_SCREEN_PURCHASE',
     'filename': 'CityScreenPurchase', 'fpk_entry': 'cityscreenpurchase.wav',
     'volume': 65, 'script_xml': SOUND_SCRIPT_XML, 'defines_xml': SOUND_DEFINES_XML,
     'xml_label': 'Audio2DScripts.xml/AudioDefines.xml', 'duplicate_limit': 1},
    {'script_id': 'AS2D_INTERFACE_FAITH_PURCHASE', 'sound_id': 'SND_INTERFACE_FAITH_PURCHASE',
     'filename': 'FaithPurchase', 'fpk_entry': None,
     'loose_wave': 'Assets/DLC/Expansion2/Sounds/Interface/FaithPurchase.wav',
     'volume': 35, 'script_xml': 'Assets/DLC/Expansion2/Sounds/XML/Audio2DScripts_Inherited_Expansion2.xml',
     'defines_xml': 'Assets/DLC/Expansion2/Sounds/XML/AudioDefines_Inherited_Expansion2.xml',
      'xml_label': 'Audio2DScripts_Inherited_Expansion2.xml/AudioDefines_Inherited_Expansion2.xml',
      'duplicate_limit': None},
    {'script_id': 'AS2D_INTERFACE_POLICY', 'sound_id': 'SND_INTERFACE_POLICY',
     'filename': 'NotificationPolicyRev2', 'fpk_entry': 'notificationpolicyrev2.wav',
     'volume': 45, 'script_xml': SOUND_SCRIPT_XML, 'defines_xml': SOUND_DEFINES_XML,
     'xml_label': 'Audio2DScripts.xml/AudioDefines.xml', 'duplicate_limit': 1},
)


def lua_string(value):
    # Escape every non-ASCII byte so generated C++ has no source-codepage dependency.
    return '"' + ''.join(chr(b) if 32 <= b < 127 and b not in (34, 92)
                         else '\\%03d' % b for b in value.encode('utf8')) + '"'


def lua_value(value):
    if isinstance(value, str):
        return lua_string(value)
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError('nonfinite number in production UI layout')
        return repr(value)
    if isinstance(value, list):
        return '{' + ','.join(lua_value(v) for v in value) + '}'
    if isinstance(value, dict):
        def key_literal(key):
            if isinstance(key, str):
                return '[' + lua_string(key) + ']'
            if isinstance(key, int) and not isinstance(key, bool) and key >= 0:
                return '[' + str(key) + ']'
            raise TypeError('unsupported Lua table key: ' + repr(key))
        return '{' + ','.join(key_literal(k) + '=' + lua_value(v)
                              for k, v in sorted(value.items(), key=lambda row: (type(row[0]).__name__, row[0]))) + '}'
    raise TypeError('unsupported Lua layout value: ' + type(value).__name__)


def control_tree(element):
    if element.tag not in KINDS:
        raise ValueError('Unsupported selected-popup XML element: ' + element.tag)
    if element.text and element.text.strip():
        raise ValueError('Unexpected mixed XML content')
    return {'kind': element.tag, 'attributes': dict(element.attrib),
            'children': [control_tree(child) for child in element]}


def unit_panel_control_tree(element):
    """Keep the nested retail tooltip template separate from the visible Context."""
    tooltip_nodes = [node for node in element.iter() if node.tag == 'ToolTipType']
    if len(tooltip_nodes) != 1 or tooltip_nodes[0].get('Name') != 'TypeUnitAction':
        raise ValueError('BNW UnitPanel must contain exactly one TypeUnitAction tooltip template')
    root = ET.fromstring(ET.tostring(element, encoding='utf-8'))

    def remove_tooltip_templates(parent):
        for child in list(parent):
            if child.tag == 'ToolTipType':
                if child.get('Name') != 'TypeUnitAction':
                    raise ValueError('BNW UnitPanel contains an unsupported tooltip template')
                parent.remove(child)
            else:
                remove_tooltip_templates(child)

    remove_tooltip_templates(root)
    tooltip = tooltip_nodes[0]
    if len(tooltip) != 1 or tooltip[0].tag != 'Grid':
        raise ValueError('TypeUnitAction must retain its original Grid root')
    tree = control_tree(root)
    tree['toolTipTemplates'] = [{'name': tooltip.get('Name'), 'tree': control_tree(tooltip[0])}]
    return tree


def action_info_panel_control_tree(element):
    """Keep the stock action controls; inventory, but do not instantiate, notifications."""
    expected = {'FileName': 'Assets/UI/InGame/WorldView/NotificationPanel', 'ID': 'NotificationPanel'}
    declarations = [node for node in element.iter() if node.tag == 'LuaContext']
    if (element.tag != 'Context' or len(declarations) != 1 or
            declarations[0] not in list(element) or declarations[0].attrib != expected or
            len(declarations[0])):
        raise ValueError('ActionInfoPanel must retain its exact original NotificationPanel declaration')
    root = ET.fromstring(ET.tostring(element, encoding='utf-8'))
    root.remove(next(node for node in root if node.tag == 'LuaContext'))
    tree = control_tree(root)
    tree['actionInfoPanel'] = {
        'originalLua': artifact(GAME / 'Assets/DLC/Expansion2/UI/InGame/WorldView/ActionInfoPanel.lua'),
        'originalXml': artifact(GAME / 'Assets/DLC/Expansion2/UI/InGame/WorldView/ActionInfoPanel.xml'),
        'notificationPanelIntegrated': False,
        'unconnectedLuaContexts': [{'kind': 'LuaContext', 'attributes': dict(expected), 'children': []}],
    }
    return tree


def notification_panel_control_tree(element):
    """Retain all stock notification controls and templates, including the unnamed one."""
    tree = control_tree(element)
    names = [child['attributes'].get('Name') for child in tree['children'] if child['kind'] == 'Instance']
    if (element.tag != 'Context' or element.attrib or len(names) != 70 or
            any(not isinstance(name, str) for name in names) or len(set(names)) != len(names) or
            names.count('') != 1 or any(node.tag == 'LuaContext' for node in element.iter())):
        raise ValueError('NotificationPanel must retain its complete original 70-template context')
    tree['notificationPanel'] = {
        'originalLua': artifact(GAME / 'Assets/DLC/Expansion2/UI/InGame/WorldView/NotificationPanel.lua'),
        'originalXml': artifact(GAME / 'Assets/DLC/Expansion2/UI/InGame/WorldView/NotificationPanel.xml'),
        'instanceNames': names,
        'animationPolicy': {
            'slide': 'CIV5_NOTIFICATION_SLIDE_ROOT_CANDIDATE_V1',
            'newFinger': 'CIV5_NOTIFICATION_ONE_BOUNCE_CANDIDATE_V1',
            'omittedNewFingerSpeed': 1.0,
            'retailTimingVerified': False,
        },
    }
    return tree


def game_menu_control_tree(element):
    """Keep the complete original menu, including its unopened child contexts.

    Child declarations are inventory, not permission to run substitute menus.
    In particular, do not hide or relabel the stock Save/Load/Options buttons
    while their independently owned contexts still need native integration.
    """
    tree = control_tree(element)
    original_tree = control_tree(ET.parse(GAME / GAME_MENU_XML).getroot())
    if tree != original_tree:
        raise ValueError('GameMenu must retain every original XML node, attribute, and child order')
    expected_children = [
        {'FileName': 'Assets/UI/FrontEnd/LoadMenu', 'ID': 'LoadMenu', 'Hidden': 'True'},
        {'FileName': 'Assets/UI/InGame/Menus/SaveMenu', 'ID': 'SaveMenu', 'Hidden': 'True'},
        {'FileName': 'Assets/UI/InGame/Menus/SaveMapMenu', 'ID': 'SaveMapMenu', 'Hidden': 'True'},
        {'FileName': 'Assets/UI/Options/OptionsMenu', 'ID': 'OptionsMenu_InGame', 'Hidden': '1'},
        {'FileName': 'Assets/UI/FrontEnd/TouchControlsMenu', 'ID': 'TouchControlsMenu',
         'DeferLoad': '1', 'Hidden': '1'},
    ]
    declarations = [node for node in _walk_control_tree(tree) if node['kind'] == 'LuaContext']
    if (element.tag != 'Context' or
            [node['attributes'] for node in declarations] != expected_children or
            any(node['children'] or node not in tree['children'] for node in declarations)):
        raise ValueError('GameMenu must retain its exact five original direct child LuaContexts')
    templates = [node['attributes'].get('Name') for node in tree['children']
                 if node['kind'] == 'Instance']
    if templates != ['GameOption', 'ModEntryInstance']:
        raise ValueError('GameMenu must retain both original detail/mod templates')
    tree['gameMenu'] = {
        'originalLua': artifact(GAME / GAME_MENU_LUA),
        'originalXml': artifact(GAME / GAME_MENU_XML),
        'originalMapUtilitiesLua': artifact(GAME / MAP_UTILITIES_LUA),
        'instanceNames': templates,
        'retainedControlCount': sum(1 for _ in _walk_control_tree(tree)),
        'includeNames': ['IconSupport', 'SupportFunctions', 'InstanceManager', 'MapUtilities'],
        'loadMenuSourceApisBound': True,
        'sourceConnectedChildren': ['SaveMenu', 'LoadMenu'],
        'unconnectedLuaContexts': [
            {'kind': 'LuaContext', 'attributes': dict(node['attributes']), 'children': []}
            for node in declarations if node['attributes']['ID'] not in ('SaveMenu', 'LoadMenu')
        ],
        'embeddedContextPolicy': 'ORIGINAL_HIDDEN_DECLARATIONS_RETAINED_NOT_INSTANTIATED',
        'timerSemaphorePolicy': 'ORIGINAL_ON_ENTER_ON_LEAVE_ONCE_ACROSS_CHILD_MENUS',
        'quickSavePolicy': 'ORIGINAL_ON_RETURN_THEN_UI_QUICK_SAVE_REQUIRES_NATIVE_DISPATCH',
        'originalButtonVisibilityPreserved': True,
        'childContextsRuntimeVerified': False,
        'retailLayoutVerified': False,
    }
    return tree


def exit_confirm_control_tree(element):
    """Retain the complete stock modal without taking its parent menu timer."""
    sources = exit_confirm_original_sources()
    tree = control_tree(element)
    original_tree = control_tree(ET.parse(sources['xml']['path']).getroot())
    if tree != original_tree:
        raise ValueError('ExitConfirm must retain every original XML node, attribute, and child order')
    controls = {node['attributes']['ID']: node for node in _walk_control_tree(tree)
                if node['attributes'].get('ID')}
    if (element.tag != 'Context' or element.get('Name') != 'MainMenu' or
            len(list(element.iter())) != 12 or
            set(controls) != {'ExitConfirm', 'Message', 'ButtonStack', 'Yes', 'No'} or
            controls['Yes']['kind'] != 'GridButton' or controls['No']['kind'] != 'GridButton'):
        raise ValueError('ExitConfirm original modal controls changed')
    tree['exitConfirm'] = {
        'policy': 'ORIGINAL_EXIT_CONFIRM_MODAL_V1',
        'originalLua': sources['lua'], 'originalXml': sources['xml'],
        'retainedControlCount': sum(1 for _ in _walk_control_tree(tree)),
        'rawOriginalName': 'MainMenu', 'modal': True, 'parentContext': 'GameMenu',
        'parentTimerSemaphorePolicy': 'PRESERVE_GAME_MENU_TIMER_WHILE_MODAL_OPEN',
        'timerSemaphores': 0, 'openEvent': 'UserRequestClose',
        'yesPolicy': 'ORIGINAL_POP_MODAL_THEN_UI_EXIT_GAME',
        'cancelPolicy': 'ORIGINAL_POP_MODAL_ON_NO_OR_ESCAPE',
        'originalButtonVisibilityPreserved': True,
        'nativeAcceptanceVerified': False, 'retailLayoutVerified': False,
    }
    return tree


def menu_child_control_tree(element, kind):
    from menu_options_assets import menu_options_control_tree
    return menu_options_control_tree(element, kind, GAME)


def map_menu_original_sources(game_root=GAME):
    result = {}
    for name, (relative, size, expected) in MAP_MENU_SOURCE_IDENTITIES.items():
        path = Path(game_root) / relative
        if path.stat().st_size != size or digest(path) != expected:
            raise ValueError('Original map menu source identity changed: ' + relative)
        result[name] = {'path': str(path), 'bytes': size, 'sha256': expected}
    return result


def map_menu_control_tree(element):
    sources = map_menu_original_sources()
    tree = control_tree(element)
    if tree != control_tree(ET.parse(sources['xml']['path']).getroot()):
        raise ValueError('MapMenu must retain every original XML node, attribute and child order')
    tree.update(contextName='SaveMapMenu', popupKind='MapMenu')
    tree['mapMenu'] = {
        'profile': 'ORIGINAL_PRIVATE_MAP_MENU_V1', 'originalLua': sources['lua'], 'originalXml': sources['xml'],
        'completeOriginalXmlRetained': True, 'sourceBytesPreserved': True,
        'retainedControlCount': sum(1 for _ in _walk_control_tree(tree)),
        'omittedStackGrowth': 'Bottom', 'retailWidgetGeometryVerified': False, 'nativeDisplayVerified': False,
        'privateCatalogOnly': True, 'retailOrUserSaveDirectoriesUsed': False, 'saveContractChanged': False,
    }
    return tree


def save_menu_control_tree(element):
    """Retain the complete original screen; its map child stays unconnected."""
    tree = control_tree(element)
    original_tree = control_tree(ET.parse(GAME / SAVE_MENU_XML).getroot())
    if tree != original_tree:
        raise ValueError('SaveMenu must retain every original XML node, attribute, and child order')
    nodes = list(_walk_control_tree(tree))
    templates = [node['attributes'].get('Name') for node in tree['children']
                 if node['kind'] == 'Instance']
    declarations = [node for node in nodes if node['kind'] == 'LuaContext']
    expected_child = {'FileName': 'Assets/UI/InGame/Menus/SaveMapMenu',
                      'ID': 'SaveMapMenu', 'Hidden': 'True'}
    editors = [node for node in nodes if node['kind'] == 'EditBox']
    if (element.tag != 'Context' or templates != ['LoadButton'] or
            len(declarations) != 1 or declarations[0]['attributes'] != expected_child or
            declarations[0]['children'] or declarations[0] not in tree['children'] or
            len(editors) != 1 or editors[0]['attributes'].get('ID') != 'NameBox' or
            editors[0]['attributes'].get('CallOnChar') != '1' or
            editors[0]['attributes'].get('MaxLength') != '32'):
        raise ValueError('SaveMenu original child, list template, or NameBox contract changed')
    tree['saveMenu'] = {
        'originalLua': artifact(GAME / SAVE_MENU_LUA),
        'originalXml': artifact(GAME / SAVE_MENU_XML),
        'originalUniqueBonusesLua': artifact(GAME / UNIQUE_BONUSES_LUA),
        'instanceNames': templates,
        'retainedControlCount': len(nodes),
        'includeNames': ['InstanceManager', 'IconSupport', 'SupportFunctions',
                         'UniqueBonuses', 'MapUtilities'],
        'unconnectedLuaContexts': [declarations[0]],
        'parentContext': 'GameMenu',
        'timerSemaphorePolicy': 'PARENT_GAME_MENU_RETAINS_ONE_CHILD_OWNS_ZERO',
        'catalogScope': 'CURRENT_ENGINE_SESSION_NATIVE_ZSSAVE_ONLY',
        'unsupportedActions': ['overwrite', 'delete', 'cloud', 'saveMap'],
        'deletePolicy': 'ORIGINAL_CONFIRMATION_RETAINED; OPTIONAL_OWNED_CATALOG_CAPABILITY; NO_RUNTIME_PROOF',
        'requiredDeleteNativeApis': ['UI.DeleteSavedGame'],
        'deleteRuntimeVerified': False,
        'nameBoxPolicy': 'ORIGINAL_MAX_LENGTH_32_UNICODE_SCALARS',
        'sourceBytesPreserved': True,
        'retailLayoutVerified': False,
    }
    return tree


def load_menu_control_tree(element):
    """Inventory the unchanged stock LoadMenu; no load/delete dispatch is bound."""
    tree = control_tree(element)
    original_tree = control_tree(ET.parse(GAME / LOAD_MENU_XML).getroot())
    if tree != original_tree:
        raise ValueError('LoadMenu must retain every original XML node, attribute, and child order')
    nodes = list(_walk_control_tree(tree))
    templates = [node['attributes'].get('Name') for node in tree['children']
                 if node['kind'] == 'Instance']
    declarations = [node for node in nodes if node['kind'] == 'LuaContext']
    pulldowns = [node for node in nodes if node['kind'] == 'PullDown']
    ids = {node['attributes'].get('ID'): node for node in nodes
           if node['attributes'].get('ID')}
    if (element.tag != 'Context' or templates != ['LoadButton', 'ReferencedPackageInstance'] or
            declarations or len(pulldowns) != 1 or
            pulldowns[0]['attributes'].get('ID') != 'SortByPullDown' or
            pulldowns[0]['attributes'].get('Style') != 'GenericPullDown' or
            not {'StartButton', 'BackButton', 'AutoCheck', 'CloudCheck', 'LoadFileButtonStack',
                 'DetailsBox', 'Delete', 'DeleteConfirm', 'ReferencedPackagesWindow'} <= ids.keys() or
            ids['StartButton']['kind'] != 'GridButton' or
            ids['DeleteConfirm']['attributes'].get('Hidden') != '1' or
            ids['ReferencedPackagesWindow']['attributes'].get('Hidden') != '1'):
        raise ValueError('LoadMenu original list, sorting, selection or confirmation contract changed')
    lua = (GAME / LOAD_MENU_LUA).read_text(encoding='utf-8-sig')
    if 'UI.incTurnTimerSemaphore' in lua or 'UI.decTurnTimerSemaphore' in lua:
        raise ValueError('LoadMenu no longer leaves the in-game parent timer untouched')
    tree['loadMenu'] = {
        'originalLua': artifact(GAME / LOAD_MENU_LUA),
        'originalXml': artifact(GAME / LOAD_MENU_XML),
        'originalUniqueBonusesLua': artifact(GAME / UNIQUE_BONUSES_LUA),
        'originalMapUtilitiesLua': artifact(GAME / MAP_UTILITIES_LUA),
        'instanceNames': templates,
        'retainedControlCount': len(nodes),
        'includeNames': ['InstanceManager', 'IconSupport', 'SupportFunctions',
                         'UniqueBonuses', 'MapUtilities'],
        'unconnectedLuaContexts': [],
        'parentContext': 'GameMenu',
        'ownerPolicy': 'ORIGINAL_PARENT_CONTEXT_ID_GAME_MENU; NATIVE_OWNER_BOUNDARY_UNCONNECTED',
        'timerSemaphorePolicy': 'ORIGINAL_LOAD_MENU_NO_TIMER_MUTATION; NATIVE_PARENT_CHILD_OWNERSHIP_UNCONNECTED',
        'parentTimerOwnershipVerified': False,
        'catalogScope': 'UNCONNECTED_ENGINE_NATIVE_ZSSAVE_CANDIDATE; NO_RETAIL_SAVE_COMPATIBILITY_PROOF',
        'nonCloudListQuery': 'UI.SaveFileList(g_FileList,g_GameType,g_ShowAutoSaves,true)',
        'selectionPolicy': 'ORIGINAL_INDEXED_ROW_SET_SELECTED_THEN_REAL_FILE_HEADER_AND_REQUIREMENTS',
        'previewPolicy': 'ORIGINAL_PREGAME_GET_FILE_HEADER; NO_SYNTHETIC_PREVIEW_METADATA',
        'loadEventPolicy': 'ORIGINAL_EVENTS_PLAYER_CHOSE_TO_LOAD_GAME_THEN_DISABLE_START_AND_DEQUEUE; NATIVE_HANDOFF_UNCONNECTED',
        'sortPolicy': 'ORIGINAL_LAST_MODIFIED_DEFAULT_AND_NAME_SORT; PULL_DOWN_UNCONNECTED',
        'cloudPolicy': 'ORIGINAL_SHOW_HIDE_STILL_QUERIES_STEAM_GET_CLOUD_SAVES; CLOUD_ACTIONS_UNCONNECTED',
        'deletePolicy': 'ORIGINAL_CONFIRMATION_RETAINED; OPTIONAL_OWNED_CATALOG_CAPABILITY; NO_RUNTIME_PROOF',
        'deleteRuntimeVerified': False,
        'requiredNativeApis': [
            'UI.SaveFileList', 'UI.GetSavedGameModificationTime',
            'UI.GetSavedGameModificationTimeRaw', 'UI.CompareFileTime', 'UI.GetCurrentGameState',
            'PreGame.GetFileHeader', 'PreGame.IsHotSeatGame',
            'Game.IsGameMultiPlayer', 'Game.IsNetworkMultiPlayer',
            'Modding.CanLoadSavedGame', 'Modding.GetSavedGameRequirements',
            'Steam.GetCloudSaves', 'Events.PlayerChoseToLoadGame',
            'UI.DeleteSavedGame',
        ],
        'unsupportedActions': ['loadDispatch', 'delete', 'cloud', 'multiplayer', 'retailSaveImport'],
        'sourceBytesPreserved': True,
        'runtimeIntegrationVerified': False,
        'pullDownRuntimeVerified': False,
        'retailSaveCompatibilityVerified': False,
        'retailLayoutVerified': False,
    }
    return tree


def game_menu_texture_names(tree):
    """Inventory menu DDS references, including nested stock style decorations."""
    nodes = list(_walk_control_tree(tree))
    for style in tree.get('styleDefaults', {}).values():
        nodes.extend(_walk_control_tree(style))
    return sorted({node['attributes']['Texture'] for node in nodes
                   if node['attributes'].get('Texture', '').casefold().endswith('.dds')},
                  key=str.casefold)


def top_panel_control_tree(element):
    """Retain the BNW TopPanel tree and its original tooltip template separately."""
    tooltip_nodes = [node for node in element.iter() if node.tag == 'ToolTipType']
    if len(tooltip_nodes) != 1 or tooltip_nodes[0].get('Name') != 'TooltipTypeTopPanel':
        raise ValueError('BNW TopPanel must contain exactly one TooltipTypeTopPanel template')
    root = ET.fromstring(ET.tostring(element, encoding='utf-8'))

    def remove_tooltip_templates(parent):
        for child in list(parent):
            if child.tag == 'ToolTipType':
                if child.get('Name') != 'TooltipTypeTopPanel':
                    raise ValueError('BNW TopPanel contains an unsupported tooltip template')
                parent.remove(child)
            else:
                remove_tooltip_templates(child)

    remove_tooltip_templates(root)
    tooltip = tooltip_nodes[0]
    if len(tooltip) != 1 or tooltip[0].tag != 'Grid':
        raise ValueError('TooltipTypeTopPanel must retain its original Grid root')
    tree = control_tree(root)
    tree['toolTipTemplates'] = [{'name': tooltip.get('Name'), 'tree': control_tree(tooltip[0])}]
    ids = {node['attributes'].get('ID') for node in _walk_control_tree(tree)}
    required = {'TopPanelInfoStack', 'SciencePerTurn', 'GoldPerTurn',
                'InternationalTradeRoutes', 'HappinessString', 'GoldenAgeString',
                'CultureString', 'TourismString', 'FaithString', 'ResourceString',
                'UnitSupplyString', 'MenuButton', 'CivilopediaButton',
                'CurrentDate', 'CurrentTurn'}
    if not required.issubset(ids):
        raise ValueError('BNW TopPanel is missing required original control IDs')
    return tree


def trade_route_control_tree(element):
    """Retain the original BNW TradeRouteOverview tree and its row template."""
    tree = control_tree(element)
    ids = {node['attributes'].get('ID') for node in _walk_control_tree(tree)}
    required = {
        'TabButtonYourTR', 'TabButtonAvailableTR', 'TabButtonTRWithYou',
        'YourTRSelectHighlight', 'AvailableTRSelectHighlight', 'TRWithYouSelectHighlight',
        'Domain', 'FromOwnerHeader', 'FromCityHeader', 'ToOwnerHeader', 'ToCityHeader',
        'FromGPT', 'ToGPT', 'ToFood', 'ToProduction', 'FromReligion', 'ToReligion',
        'FromScience', 'ToScience', 'TurnsLeft', 'MainScroll', 'MainStack', 'CloseButton',
    }
    if not required.issubset(ids):
        raise ValueError('BNW TradeRouteOverview is missing original controls: ' +
                         ','.join(sorted(required - ids)))
    instances = [node for node in tree['children']
                 if node['kind'] == 'Instance' and node['attributes'].get('Name') == 'TRInstance']
    if len(instances) != 1:
        raise ValueError('BNW TradeRouteOverview must retain exactly one TRInstance row template')
    row_ids = {node['attributes'].get('ID') for node in _walk_control_tree(instances[0])}
    required_row_ids = {
        'Domain_Land', 'Domain_Sea', 'FromCivIcon', 'FromCivIconBG',
        'FromCivIconShadow', 'FromCivIconHighlight', 'FromCity',
        'ToCivIcon', 'ToCivIconBG', 'ToCivIconShadow', 'ToCivIconHighlight',
        'ToCity', 'FromGPT', 'ToGPT', 'FromScience', 'ToScience', 'ToFood',
        'ToProduction', 'FromReligion', 'ToReligion', 'TurnsLeft',
    }
    if not required_row_ids.issubset(row_ids):
        raise ValueError('BNW TRInstance is missing original row controls: ' +
                         ','.join(sorted(required_row_ids - row_ids)))
    return tree


def trade_route_texture_names(tree):
    """Collect original DDS references from the TradeRoute tree and its styles."""
    names = set()
    def collect(node):
        texture = node['attributes'].get('Texture')
        if texture and texture.casefold().endswith('.dds'):
            names.add(texture)
        for child in node.get('children', []):
            collect(child)
    collect(tree)
    for style in tree.get('styleDefaults', {}).values():
        collect(style)
    return sorted(names, key=str.casefold)


def pantheon_control_tree(element):
    """Retain the exact BNW Pantheon shell and its dynamic belief row template."""
    tree = control_tree(element)
    required = {'ItemStack', 'ItemScrollPanel', 'BottomPanel', 'CloseButton', 'PanelTitle',
                'CivIcon', 'CivIconBG', 'CivIconShadow', 'ChooseConfirm', 'ConfirmText', 'Yes', 'No'}
    ids = {node['attributes'].get('ID') for node in _walk_control_tree(tree)}
    instances = [node for node in tree['children'] if node['kind'] == 'Instance']
    if element.tag != 'Context' or not required <= ids or len(instances) != 1 or \
            instances[0]['attributes'].get('Name') != 'ItemInstance':
        raise ValueError('BNW Pantheon controls or its sole ItemInstance changed')
    row_ids = {node['attributes'].get('ID') for node in _walk_control_tree(instances[0])}
    if row_ids != {None, 'Button', 'BounceAnim', 'BounceGrid', 'Box', 'Name', 'Description'}:
        raise ValueError('BNW Pantheon belief row lost an original control')
    confirmation = next(node for node in _walk_control_tree(tree) if node['attributes'].get('ID') == 'ChooseConfirm')
    if confirmation['attributes'].get('ConsumeMouse') != '1' or confirmation['attributes'].get('Hidden') != '1':
        raise ValueError('BNW Pantheon confirmation must retain its hidden full-screen mouse barrier')
    return tree


def social_policy_control_tree(element):
    """Retain the complete original BNW SocialPolicyPopup tree and templates."""
    tree = control_tree(element)
    ids = {node['attributes'].get('ID') for node in _walk_control_tree(tree)}
    required = {
        'BGBlock', 'TabButtonSocialPolicies', 'TabButtonSocialPoliciesHL',
        'TabButtonIdeologies', 'TabButtonIdeologiesHL', 'SocialPolicyPane',
        'IdeologyPane', 'PolicyInfo', 'TraditionPanel', 'LibertyPanel',
        'HonorPanel', 'PietyPanel', 'PatronagePanel', 'RationalismPanel',
        'ExplorationPanel', 'CommercePanel', 'AestheticsPanel', 'CloseButton',
        'PolicyConfirm', 'Yes', 'No', 'ChooseTenet', 'TenetStack',
        'TenetConfirm', 'TenetConfirmYes', 'TenetConfirmNo',
        'TenetCancelButton', 'ChangeIdeologyConfirm',
        'ChangeIdeologyConfirmYes', 'ChangeIdeologyConfirmNo',
    }
    if not required.issubset(ids):
        raise ValueError('BNW SocialPolicyPopup is missing original controls: ' +
                         ','.join(sorted(required - ids)))
    instances = {node['attributes'].get('Name'): node for node in tree['children']
                 if node['kind'] == 'Instance'}
    if set(instances) != {'PolicyButton', 'ConnectorPipe', 'TenetChoice'}:
        raise ValueError('BNW SocialPolicyPopup must retain exactly its three original templates')
    def xml_count(node):
        return 1 + sum(xml_count(child) for child in node)
    def tree_count(node):
        return 1 + sum(tree_count(child) for child in node['children'])
    if tree_count(tree) != xml_count(element):
        raise RuntimeError('SocialPolicy layout tree dropped an original XML control or Instance')
    return tree


def social_policy_texture_names(tree):
    """Collect original DDS references from the policy tree and styles."""
    names = set()
    def collect(node):
        texture = node['attributes'].get('Texture')
        if texture and texture.casefold().endswith('.dds'):
            names.add(texture)
        for child in node.get('children', []):
            collect(child)
    collect(tree)
    for style in tree.get('styleDefaults', {}).values():
        collect(style)
    return sorted(names, key=str.casefold)


def social_policy_control_default_sizes(snapshots):
    """Record the stock Button_16 size/texture as an unverified default candidate."""
    source, frozen = freeze_source(STYLE_SOURCE, snapshots)
    styles = {element.tag: element for element in ET.parse(frozen).getroot()}
    button = styles.get('Button_16')
    expected = {'Texture': 'Assets/UI/Art/Controls/Checkbox.dds', 'Size': '32,32'}
    if button is None or any(button.get(key) != value for key, value in expected.items()):
        raise RuntimeError('Installed Styles.xml Button_16 default differs from the SocialPolicy candidate')
    return {'PolicyInfo': {
        'policy': 'SOCIAL_POLICY_BUTTON_16_DEFAULT_CANDIDATE_V1',
        'style': 'Button_16', 'width': 32, 'height': 32,
        'texture': expected['Texture'], 'sourceStyleAttributes': expected,
        'source': artifact(source), 'retailWidgetGeometryVerified': False,
    }}


def attach_social_policy_control_defaults(tree, defaults):
    """Carry the source-backed checkbox candidate into the runtime layout chunk."""
    if tree.get('contextName') != 'SocialPolicyPopup' or tree.get('popupKind') != 'SocialPolicy':
        raise ValueError('PolicyInfo defaults may only attach to the original SocialPolicy layout')
    if not isinstance(defaults, dict) or set(defaults) != {'PolicyInfo'}:
        raise ValueError('SocialPolicy runtime defaults must contain exactly PolicyInfo')
    candidate = defaults['PolicyInfo']
    if (candidate.get('policy') != 'SOCIAL_POLICY_BUTTON_16_DEFAULT_CANDIDATE_V1' or
            candidate.get('style') != 'Button_16' or candidate.get('width') != 32 or
            candidate.get('height') != 32 or
            candidate.get('texture') != 'Assets/UI/Art/Controls/Checkbox.dds' or
            candidate.get('retailWidgetGeometryVerified') is not False):
        raise ValueError('SocialPolicy PolicyInfo default candidate differs from inspected source style')
    tree['controlDefaultSizes'] = defaults
    return tree


def load_menu_check_defaults(snapshots, assets):
    source, frozen = freeze_source(STYLE_SOURCE, snapshots)
    if digest(source) != digest(frozen):
        raise ValueError('LoadMenu checkbox style snapshot differs from its original source')
    return observed_load_menu_check_defaults(source, GAME / LOAD_MENU_XML, assets)


def attach_load_menu_control_defaults(tree, defaults):
    if (tree.get('contextName'), tree.get('popupKind')) != ('LoadMenu', 'LoadMenu'):
        raise ValueError('LoadMenu checkbox defaults require their original context')
    if type(defaults) is not dict or set(defaults) != {'AutoCheck', 'CloudCheck'}:
        raise ValueError('LoadMenu checkbox defaults must contain exactly AutoCheck and CloudCheck')
    nodes = {node['attributes'].get('ID'): node for node in _walk_control_tree(tree)
             if node['attributes'].get('ID') in defaults}
    for control_id, candidate in defaults.items():
        node = nodes.get(control_id)
        if (node is None or node['kind'] != 'CheckBox' or type(candidate) is not dict or
                candidate.get('policy') != 'LOAD_MENU_BUTTON_16_DEFAULT_CANDIDATE_V1' or
                (candidate.get('width'), candidate.get('height'), candidate.get('frameCount')) != (32, 32, 4) or
                candidate.get('style') != 'Button_16' or
                candidate.get('texture') != 'Assets/UI/Art/Controls/Checkbox.dds' or
                candidate.get('controlSourceAttributes') != node['attributes'] or
                any(candidate.get(field) is not False for field in
                    ('defaultBindingVerified', 'retailGeometryVerified', 'retailWidgetStateMappingVerified')) or
                any(field in node['attributes'] for field in ('Size', 'Style', 'ButtonTexture'))):
            raise ValueError('LoadMenu checkbox candidate changed its original source or proof boundary: ' + control_id)
    tree['controlDefaultSizes'] = defaults
    return tree


def _walk_control_tree(node):
    yield node
    for child in node['children']:
        yield from _walk_control_tree(child)


def economic_overview_tree_inventory(tree):
    """Describe the untouched XML tree and every dynamic row template."""
    nodes = list(_walk_control_tree(tree))
    templates = []
    for node in nodes:
        if node['kind'] != 'Instance':
            continue
        attrs = node['attributes']
        name = attrs.get('Name')
        if not name:
            raise ValueError('Economic Overview contains an unnamed original Instance')
        template_nodes = list(_walk_control_tree(node))
        templates.append({
            'name': name,
            'control_ids': sorted(n['attributes']['ID'] for n in template_nodes
                                  if n['attributes'].get('ID')),
            'retained_control_count': len(template_nodes),
        })
    return {
        'control_ids': sorted(node['attributes']['ID'] for node in nodes
                              if node['attributes'].get('ID')),
        'retained_control_count': len(nodes),
        'templates': sorted(templates, key=lambda row: row['name']),
    }


def economic_overview_layout_metadata(name):
    role, lua_name, xml_name = {
        'EconomicOverviewLayout': ('parent', 'Assets/UI/InGame/Popups/EconomicOverview.lua',
                                   'Assets/DLC/Expansion2/UI/InGame/Popups/EconomicOverview.xml'),
        'EconomicGeneralLayout': ('general', 'Assets/DLC/Expansion2/UI/InGame/Popups/EconomicGeneralInfo.lua',
                                  'Assets/DLC/Expansion2/UI/InGame/Popups/EconomicGeneralInfo.xml'),
        'EconomicHappinessLayout': ('happiness', 'Assets/DLC/Expansion2/UI/InGame/Popups/HappinessInfo.lua',
                                    'Assets/DLC/Expansion2/UI/InGame/Popups/HappinessInfo.xml'),
    }[name]
    return {
        'role': role, 'originalLua': artifact(GAME / lua_name), 'originalXml': artifact(GAME / xml_name),
        'stackGrowthPolicy': 'ECONOMIC_ORIGINAL_OMITTED_GROWTH_BOTTOM_CANDIDATE_V1',
        'retailStackGeometryVerified': False,
        'embeddedViewportPolicy': 'ORIGINAL_ECONOMIC_CHILD_LOGICAL_VIEWPORT_CANDIDATE_V1',
        'retailEmbeddedViewportVerified': False,
    }


def economic_overview_proof(trees, input_sources):
    """Bind the original EconomicOverview shell to both original child VMs."""
    specs = {
        'parent': ('EconomicOverviewLayout', 'EconomicOverview', 'EconomicOverview',
                   'Assets/DLC/Expansion2/UI/InGame/Popups/EconomicOverview.xml',
                   'Assets/UI/InGame/Popups/EconomicOverview.lua'),
        'EconomicGeneralInfo': ('EconomicGeneralLayout', 'EconomicGeneralInfo', 'EconomicGeneral',
                                'Assets/DLC/Expansion2/UI/InGame/Popups/EconomicGeneralInfo.xml',
                                'Assets/DLC/Expansion2/UI/InGame/Popups/EconomicGeneralInfo.lua'),
        'HappinessInfo': ('EconomicHappinessLayout', 'HappinessInfo', 'EconomicHappiness',
                          'Assets/DLC/Expansion2/UI/InGame/Popups/HappinessInfo.xml',
                          'Assets/DLC/Expansion2/UI/InGame/Popups/HappinessInfo.lua'),
    }
    child_contract = {
        'EconomicGeneralInfo': {'file_name': 'Assets/UI/InGame/Popups/EconomicGeneralInfo', 'hidden': '0'},
        'HappinessInfo': {'file_name': 'Assets/UI/InGame/Popups/HappinessInfo', 'hidden': '1'},
    }
    parent_tree = trees['EconomicOverviewLayout']
    embedded = {}
    for node in _walk_control_tree(parent_tree):
        if node['kind'] == 'LuaContext':
            attrs = node['attributes']
            control_id = attrs.get('ID')
            if control_id in embedded:
                raise ValueError('EconomicOverview has a duplicate child LuaContext ID')
            embedded[control_id] = {'file_name': attrs.get('FileName'), 'hidden': attrs.get('Hidden')}
    if embedded != child_contract:
        raise ValueError('EconomicOverview must preserve its exact two original child LuaContexts')

    def describe(layout_name, lua_name, popup_kind, xml_path, lua_path):
        tree = trees[layout_name]
        xml_artifact = input_sources[layout_name]['installed']
        lua_artifact = input_sources[lua_name]['installed']
        if (tree.get('contextName'), tree.get('popupKind')) != (lua_name, popup_kind):
            raise ValueError('EconomicOverview child context metadata differs from its original asset')
        if (xml_artifact['path'].replace('\\', '/').endswith('/' + xml_path) is False or
                lua_artifact['path'].replace('\\', '/').endswith('/' + lua_path) is False):
            raise ValueError('EconomicOverview source provenance points to an unexpected installed asset')
        inventory = economic_overview_tree_inventory(tree)
        return {
            'contextName': lua_name, 'popupKind': popup_kind,
            'layoutAsset': layout_name, 'luaAsset': lua_name,
            'lua': lua_artifact, 'xml': xml_artifact,
            **inventory,
        }

    parent = describe(*specs['parent'])
    children = {}
    for control_id in ('EconomicGeneralInfo', 'HappinessInfo'):
        layout, lua_name, popup_kind, xml_path, lua_path = specs[control_id]
        children[control_id] = {
            'controlId': control_id,
            'visibility': 'visible' if child_contract[control_id]['hidden'] == '0' else 'hidden',
            **describe(layout, lua_name, popup_kind, xml_path, lua_path),
        }
    return {
        'parent': parent,
        'children': children,
        'xmlContexts': [
            {'id': control_id, 'fileName': values['file_name'], 'hidden': values['hidden']}
            for control_id, values in sorted(embedded.items())
        ],
        'treeNames': [specs['parent'][0], specs['EconomicGeneralInfo'][0], specs['HappinessInfo'][0]],
        'sourceBytesPreserved': True,
    }


def declare_war_control_tree(element):
    """Retain every original BNW DeclareWarPopup control and data section."""
    tree = control_tree(element)
    required_ids = {
        'PopupText', 'LeaderFrame', 'RivalFrame', 'DeclareWarDetailsScrollPanel',
        'DeclareWarDetailsStack', 'UnderProtectionOfStack', 'AlliedCityStatesStack',
        'ActiveDealsStack', 'TradeRoutesStack', 'Button1', 'Button2',
    }
    found_ids = set()
    def collect(node):
        control_id = node['attributes'].get('ID')
        if control_id:
            found_ids.add(control_id)
        for child in node['children']:
            collect(child)
    collect(tree)
    missing = sorted(required_ids - found_ids)
    if missing:
        raise RuntimeError('Original BNW DeclareWarPopup is missing required controls: ' + ','.join(missing))
    def xml_count(node):
        return 1 + sum(xml_count(child) for child in node)
    def tree_count(node):
        return 1 + sum(tree_count(child) for child in node['children'])
    if tree_count(tree) != xml_count(element):
        raise RuntimeError('DeclareWar layout tree dropped an original XML control or Instance')
    return tree


def declare_war_texture_names(tree):
    """Collect original DDS references from controls and resolved stock styles."""
    names = set()
    def collect(node):
        texture = node['attributes'].get('Texture')
        if texture and texture.casefold().endswith('.dds'):
            names.add(texture)
        for child in node.get('children', []):
            collect(child)
    collect(tree)
    for style in tree.get('styleDefaults', {}).values():
        collect(style)
    return sorted(names, key=str.casefold)


def cpp_literal(data):
    # Adjacent short literals avoid MSVC's single-string token size limit.
    return '\n'.join('"' + ''.join('\\x%02x' % b for b in data[i:i + 64]) + '"'
                     for i in range(0, len(data), 64)) or '""'


def freeze_source(relative, snapshots):
    source = GAME / relative
    target = snapshots / relative
    expected = digest(source)
    if target.exists() and digest(target) != expected:
        raise RuntimeError('Installed UI asset changed from its frozen snapshot: ' + relative)
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        shutil.copy2(source, target)
    if digest(source) != expected or digest(target) != expected:
        raise RuntimeError('UI asset changed during capture')
    return source, target


def inline_icon_catalog(snapshots):
    source_records = {}
    mapping_sources = []
    for relative in ICON_MAPPING_FILES:
        source, frozen = freeze_source(relative, snapshots)
        record = {'path': relative, 'sha256': digest(frozen)}
        source_records[relative] = record
        mapping_sources.append((ET.parse(frozen).getroot(), record))

    font_by_key = {}
    for root, _ in mapping_sources:
        for entry in root.findall('./IconFontTextures/Row'):
            key = entry.findtext('IconFontTexture')
            file_name = entry.findtext('IconFontTextureFile')
            if not key or not file_name:
                raise RuntimeError('Malformed official IconFontTextures Row')
            previous = font_by_key.get(key)
            if previous and previous != file_name:
                raise RuntimeError('Conflicting official icon font texture: ' + key)
            font_by_key[key] = file_name

    fonts = {}
    for file_name, relative in ICON_FONTS.items():
        source, frozen = freeze_source(relative, snapshots)
        font_record = {'path': relative, 'sha256': digest(frozen)}
        source_records[relative] = font_record
        root = ET.parse(frozen).getroot()
        textures = root.findall('./textures/texture')
        glyphs = root.findall('./glyphs/glyph')
        if len(textures) != 1 or not textures[0].get('src'):
            raise RuntimeError('Expected exactly one official font texture in ' + relative)
        glyph_map = {}
        for glyph in glyphs:
            ch = glyph.get('ch')
            if ch is None or ch in glyph_map:
                raise RuntimeError('Missing or duplicate glyph character in ' + relative)
            fields = ('u', 'v', 'width', 'height', 'a', 'b', 'c', 'originx', 'originy')
            if any(glyph.get(field) is None for field in fields):
                raise RuntimeError('Incomplete official glyph metrics in ' + relative)
            glyph_map[ch] = {
                'u': int(glyph.get('u')), 'v': int(glyph.get('v')),
                'width': int(glyph.get('width')), 'height': int(glyph.get('height')),
                'advance': int(glyph.get('a')) + int(glyph.get('b')) + int(glyph.get('c')),
                'originx': int(glyph.get('originx')), 'originy': int(glyph.get('originy')),
            }
        fonts[file_name] = {
            'texture': textures[0].get('src'), 'glyphs': glyph_map,
            'source': font_record,
        }

    catalog = {}
    for root, mapping_source in mapping_sources:
        table = root.find('./IconFontMapping')
        if table is None:
            raise RuntimeError('Missing official IconFontMapping table')
        for row in table:
            if row.tag not in ('Row', 'InsertOrAbort'):
                continue
            name = row.findtext('IconName')
            mapping_text = row.findtext('IconMapping')
            if not name or not name.startswith('ICON_') or not mapping_text:
                raise RuntimeError('Malformed official IconFontMapping ' + row.tag)
            try:
                mapping = int(mapping_text)
            except ValueError as error:
                raise RuntimeError('Noninteger official icon mapping: ' + name) from error
            texture_key = row.findtext('IconFontTexture') or 'ICON_FONT_TEXTURE_DEFAULT'
            if texture_key not in font_by_key:
                raise RuntimeError('Official icon references unknown font texture: ' + texture_key)
            file_name = font_by_key[texture_key]
            font = fonts.get(file_name)
            glyph = font and font['glyphs'].get(str(mapping))
            if glyph is None:
                raise RuntimeError('Official icon mapping has no matching GGXML glyph: ' + name)
            entry = {
                'mapping': mapping, 'texture': font['texture'], 'glyph': glyph,
                'mapping_source': mapping_source,
                'font_source': font['source'],
            }
            if name in catalog:
                # Base Rows are applied before BNW InsertOrAbort. A duplicate
                # InsertOrAbort retains the earlier database row; duplicate
                # Rows are ambiguous and therefore fail closed.
                if row.tag == 'InsertOrAbort':
                    continue
                raise RuntimeError('Duplicate official icon mapping Row: ' + name)
            catalog[name] = entry
    return dict(sorted(catalog.items())), source_records


def production_style_defaults(snapshots, production_tree):
    source, frozen = freeze_source(STYLE_SOURCE, snapshots)
    root = ET.parse(frozen).getroot()
    styles = {element.tag: element for element in root}

    def style_closure(names):
        retained = set()
        visiting = []

        def visit(name):
            if name in visiting:
                raise RuntimeError('Production style references a cycle: ' +
                                   ' -> '.join([*visiting, name]))
            if name in retained:
                return
            element = styles.get(name)
            if element is None:
                raise RuntimeError('Production control references missing style: ' + name)
            visiting.append(name)
            for node in element.iter():
                dependency = node.get('Style')
                if dependency:
                    visit(dependency)
            visiting.pop()
            retained.add(name)

        for name in sorted(names):
            visit(name)
        return retained

    def style_attributes(name):
        element = styles[name]
        attributes = {}
        if element.get('Style'):
            attributes.update(style_attributes(element.get('Style')))
        attributes.update(element.attrib)
        return attributes

    def resolved_node(element, kind=None, preserve_source=False):
        attributes = {}
        style_name = element.get('Style')
        if style_name:
            attributes.update(style_attributes(style_name))
        attributes.update(element.attrib)
        result = {
            'kind': kind or element.tag,
            'attributes': attributes,
            'children': [resolved_node(child, preserve_source=preserve_source) for child in element],
        }
        if preserve_source:
            result['sourceAttributes'] = dict(element.attrib)
        if style_name:
            result['style'] = style_name
        return result

    style_names = set()
    pull_down_styles = set()
    def collect(node):
        style_name = node['attributes'].get('Style')
        if style_name:
            style_names.add(style_name)
            if node['kind'] == 'PullDown':
                pull_down_styles.add(style_name)
        for child in node['children']:
            collect(child)
    for template in production_tree.get('toolTipTemplates', []):
        collect(template['tree'])
    collect(production_tree)
    # Composite styles reference their ButtonData, GridData, Shuttle, and
    # instance decorations through other styles. Keep those definitions in the
    # catalog without inserting invented children into the original XML tree.
    style_names = style_closure(style_names)
    source_styles = style_closure(pull_down_styles)
    result = {}
    for style_name in sorted(style_names):
        element = styles[style_name]
        node = resolved_node(element, style_name, preserve_source=(
            style_name in source_styles or
            (production_tree.get('popupKind') == 'NotificationPanel' and style_name in ('NewFinger', 'NewFingerRed'))))
        node['style'] = style_name
        # A slider style's nested Shuttle has its own Style reference and must
        # retain the resolved engine style attributes as source data.
        result[style_name] = node

    if production_tree.get('popupKind') == 'Production':
        for name, expected_size in (('ScrollBarUp', '18,18'), ('ScrollBarDown', '18,18'),
                                    ('VertSlider', '18,18'), ('VertShuttle', '18,18')):
            element = styles.get(name)
            if element is None or element.get('Size') != expected_size:
                raise RuntimeError('Unexpected official production control size for style ' + name)
        if styles['VertSlider'].get('Vertical') != '1' or styles['VertShuttle'].get('Vertical') != '1':
            raise RuntimeError('Unexpected official vertical slider style defaults')
    elif production_tree.get('popupKind') == 'ResearchTree':
        horizontal = styles.get('ScrollBar')
        shuttle = horizontal.find('Shuttle') if horizontal is not None else None
        grid_shuttle = styles.get('Grid3Shuttle')
        if (horizontal is None or horizontal.get('Vertical') != '0' or horizontal.get('Size') != '17,18' or
                shuttle is None or shuttle.get('Style') != 'Grid3Shuttle' or shuttle.get('Size') != '18,18' or
                grid_shuttle is None):
            raise RuntimeError('Unexpected official horizontal TechTree scrollbar defaults')
    return {
        'source': {'path': STYLE_SOURCE, 'sha256': digest(frozen)},
        'controls': result,
        'policy': 'OFFICIAL_STYLES_XML_ATTRIBUTES_WITH_CONTROL_XML_OVERRIDES',
    }


def production_font_metrics(production_tree, inline_icons, *, fonts_by_id=None, font_root=GAME):
    font_styles = {}
    context_defaults = production_tree.get('contextFontDefaults', {}).get('attributes', {})
    if context_defaults.get('Font'):
        font_styles.setdefault(context_defaults['Font'], set()).add(context_defaults.get('FontStyle', 'Base'))
    def collect(node):
        attributes = node['attributes']
        style = production_tree.get('styleDefaults', {}).get(attributes.get('Style'), {})
        style_attributes = style.get('attributes', {})
        font_id = attributes.get('Font') or style_attributes.get('Font')
        if font_id:
            font_styles.setdefault(font_id, set()).add(
                attributes.get('FontStyle', style_attributes.get('FontStyle', 'Base')))
        for child in node['children']:
            collect(child)
    collect(production_tree)
    for template in production_tree.get('toolTipTemplates', []):
        collect(template['tree'])
    for style in production_tree.get('styleDefaults', {}).values():
        collect(style)

    fonts = {}
    glyph_sets = {}
    for font_id in sorted(font_styles):
        if fonts_by_id is None:
            font = load_font(GAME, font_id, 'Base')
        else:
            if font_id not in fonts_by_id:
                raise ValueError('UI font is not present in the sealed input profile: ' + font_id)
            font = fonts_by_id[font_id]
        if not font.font_style or 'Base' not in font.styles:
            raise RuntimeError('Production font has no supported Base style: ' + font_id)
        missing_styles = sorted(font_styles[font_id] - set(font.styles))
        if missing_styles:
            raise RuntimeError('Production font lacks referenced styles: ' + font_id + '/' + ','.join(missing_styles))
        glyph_key = font.ggxml_sha256
        if glyph_key not in glyph_sets:
            glyph_sets[glyph_key] = {
                codepoint: {
                    'advance': glyph.abc_advance,
                    'width': glyph.width,
                    'height': glyph.height,
                    'originX': glyph.origin_x,
                    'originY': glyph.origin_y,
                }
                for codepoint, glyph in font.glyphs.items()
            }
        fonts[font_id] = {
            'lineAdvance': font.line_advance,
            'baselineOffset': font.baseline_offset,
            'spacing': font.spacing,
            'fudgeadv': font.fudgeadv,
            'ggxmlPath': font.ggxml_path.relative_to(font_root).as_posix(),
            'sha256': font.ggxml_sha256,
            'glyphSet': glyph_key,
        }

    icons = {}
    for name, entry in inline_icons.items():
        glyph = entry['glyph']
        icons[name] = {
            'advance': glyph['advance'], 'width': glyph['width'], 'height': glyph['height'],
            'originX': glyph['originx'], 'originY': glyph['originy'],
            'texture': entry['texture'], 'mappingSource': entry['mapping_source'],
            'fontSource': entry['font_source'],
        }
    return {
        'policy': 'CIV5_GLYPHGEN_GGXML_LAYOUT_V1',
        'retailMetricSemanticsVerified': False,
        'wrapPolicy': 'GREEDY_ASCII_SPACE_WORD_WRAP_SPLIT_LONG_WORD_AT_CODEPOINT',
        'fonts': fonts,
        'glyphSets': glyph_sets,
        'inlineIcons': icons,
    }


def city_check_defaults(assets, destination):
    """Retain the four square button frames, never the FTXT dictionary size."""
    result = {}
    for basename in ('checkbox.dds', 'checkbox2thebox.dds'):
        texture = assets.resolve(basename, destination / 'textures')
        conversion = texture['conversion']
        width, height = conversion['width'], conversion['height']
        if width != 32 or height != width * 4:
            raise RuntimeError('Original CityView check atlas differs from its inspected four-frame layout')
        result[basename] = {
            'width': width, 'height': width, 'frameCount': 4,
            'policy': 'CIV5_CHECK_ATLAS_SQUARE_FRAME_CANDIDATE_V1',
            'retailWidgetGeometryVerified': False, 'texture': texture,
        }
    return result


def single_xml_text(element, tag, source_name):
    matches = [child for child in element if child.tag == tag]
    if len(matches) != 1 or matches[0].text is None:
        raise RuntimeError(f'Expected one {tag} in original {source_name}')
    return matches[0].text.strip()


def parse_wave_chunks(data):
    if len(data) < 12 or data[:4] != b'RIFF' or data[8:12] != b'WAVE':
        raise RuntimeError('Original purchase audio is not a RIFF/WAVE input')
    riff_size, = struct.unpack_from('<I', data, 4)
    if riff_size != len(data) - 8:
        raise RuntimeError('Original purchase audio RIFF size does not cover its exact bytes')
    offset = 12
    chunks = {}
    while offset < len(data):
        if offset + 8 > len(data):
            raise RuntimeError('Truncated purchase WAV chunk header')
        chunk_id = data[offset:offset + 4]
        chunk_size, = struct.unpack_from('<I', data, offset + 4)
        body = offset + 8
        end = body + chunk_size
        if end > len(data):
            raise RuntimeError('Purchase WAV chunk exceeds its RIFF container')
        chunks.setdefault(chunk_id, []).append((body, end))
        offset = end if end == len(data) else end + (chunk_size & 1)
    if offset != len(data) or any(len(chunks.get(name, [])) != 1 for name in (b'fmt ', b'data')):
        raise RuntimeError('Purchase WAV must have one bounded fmt and data chunk')
    fmt_start, fmt_end = chunks[b'fmt '][0]
    audio_start, audio_end = chunks[b'data'][0]
    fmt = data[fmt_start:fmt_end]
    if len(fmt) < 16:
        raise RuntimeError('Purchase WAV fmt chunk is shorter than WAVEFORMAT')
    tag, channels, sample_rate, average_bytes, block_align, bits, extra_size, samples_per_block = \
        (*struct.unpack_from('<HHIIHH', fmt), *struct.unpack_from('<HH', fmt, 16)) if len(fmt) >= 20 else \
        (*struct.unpack_from('<HHIIHH', fmt), 0, 0)
    if not channels or not sample_rate or not block_align or not bits or \
       len(fmt) != (18 + extra_size if len(fmt) >= 18 else 16):
        raise RuntimeError('Purchase WAV WAVEFORMATEX geometry is inconsistent')
    audio_bytes = audio_end - audio_start
    if audio_bytes == 0:
        raise RuntimeError('Purchase WAV data chunk is empty')
    full_blocks, tail_bytes = divmod(audio_bytes, block_align)
    sample_frames = None
    decoded_frames = None
    format_name = {1: 'WAVE_FORMAT_PCM', 2: 'WAVE_FORMAT_ADPCM', 0x11: 'WAVE_FORMAT_DVI_ADPCM'}.get(tag, f'WAVE_FORMAT_{tag:04X}')
    if tag == 0x11:
        if len(fmt) != 20 or channels not in (1, 2) or bits != 4 or extra_size != 2 or block_align <= 4 * channels:
            raise RuntimeError('Purchase IMA ADPCM WAVEFORMATEX geometry is unsupported')
        group_bytes = 4 * channels
        if (tail_bytes and (tail_bytes < group_bytes or tail_bytes % group_bytes)) or \
           samples_per_block != 1 + (block_align - group_bytes) * 2 // channels:
            raise RuntimeError('Purchase IMA ADPCM block geometry is inconsistent')
        if len(chunks.get(b'fact', [])) != 1:
            raise RuntimeError('Purchase IMA ADPCM WAV needs one fact sample count')
        fact_start, fact_end = chunks[b'fact'][0]
        if fact_end - fact_start != 4:
            raise RuntimeError('Purchase IMA ADPCM fact chunk must contain one sample count')
        sample_frames, = struct.unpack_from('<I', data, fact_start)
        decoded_frames = full_blocks * samples_per_block + (1 + (tail_bytes - group_bytes) * 2 // channels if tail_bytes else 0)
        if not 0 < sample_frames <= decoded_frames:
            raise RuntimeError('Purchase IMA ADPCM fact count differs from its final coded sample group')
    elif tag == 1:
        if extra_size != 0 or bits not in (8, 16, 24, 32) or block_align != channels * ((bits + 7) // 8) or audio_bytes % block_align:
            raise RuntimeError('Purchase PCM WAV geometry is inconsistent')
        decoded_frames = audio_bytes // block_align
    elif tag == 2:
        if len(fmt) < 22 or extra_size < 4 or channels not in (1, 2) or bits != 4:
            raise RuntimeError('Purchase Microsoft ADPCM WAVEFORMATEX geometry is unsupported')
        decoded_frames = None
    else:
        raise RuntimeError(f'Unsupported purchase WAV format tag 0x{tag:04x}')
    return {
        'format_tag': tag, 'format_name': format_name, 'channels': channels,
        'samples_per_second': sample_rate, 'average_bytes_per_second': average_bytes,
        'block_align': block_align, 'bits_per_sample': bits, 'cb_size': extra_size,
        'samples_per_block': samples_per_block, 'fmt_bytes': len(fmt),
        'data_offset': audio_start, 'compressed_bytes': audio_bytes,
        'full_blocks': full_blocks, 'final_block_bytes': tail_bytes,
        'fact_sample_frames': sample_frames, 'coded_sample_frames': decoded_frames,
        'compressed_sha256': hashlib.sha256(data[audio_start:audio_end]).hexdigest(),
        'container_bytes': len(data), 'riff_size_field': riff_size,
    }


def freeze_buy_tile_audio():
    script_xml = GAME / SOUND_SCRIPT_XML
    defines_xml = GAME / SOUND_DEFINES_XML
    if not script_xml.is_file() or not defines_xml.is_file():
        raise RuntimeError('Original Civ V Audio2DScripts.xml/AudioDefines.xml files are unavailable')
    try:
        scripts_root = ET.parse(script_xml).getroot()
        defines_root = ET.parse(defines_xml).getroot()
    except ET.ParseError as error:
        raise RuntimeError('Original Civ V audio XML is malformed') from error
    scripts = [element for element in scripts_root.iter('Script2DSound')
               if single_xml_text(element, 'ScriptID', 'Audio2DScripts.xml') == BUY_TILE_SCRIPT_ID]
    if len(scripts) != 1:
        raise RuntimeError('Original AS2D_INTERFACE_BUY_TILE must be unique')
    sound_script = scripts[0]
    script_settings = {
        'script_id': single_xml_text(sound_script, 'ScriptID', 'Audio2DScripts.xml'),
        'sound_id': single_xml_text(sound_script, 'SoundID', 'Audio2DScripts.xml'),
        'sound_type': single_xml_text(sound_script, 'SoundType', 'Audio2DScripts.xml'),
        'min_volume': int(single_xml_text(sound_script, 'iMinVolume', 'Audio2DScripts.xml')),
        'max_volume': int(single_xml_text(sound_script, 'iMaxVolume', 'Audio2DScripts.xml')),
        'dont_trigger_duplicates': single_xml_text(sound_script, 'bDontTriggerDuplicates', 'Audio2DScripts.xml').casefold() == 'true',
        'dont_play_more_than': int(single_xml_text(sound_script, 'iDontPlayMoreThan', 'Audio2DScripts.xml')),
    }
    if (script_settings['sound_id'], script_settings['sound_type'], script_settings['min_volume'],
        script_settings['max_volume'], script_settings['dont_trigger_duplicates'],
        script_settings['dont_play_more_than']) != (BUY_TILE_SOUND_ID, 'GAME_SFX', BUY_TILE_MIN_MAX_VOLUME,
        BUY_TILE_MIN_MAX_VOLUME, True, BUY_TILE_MAX_ACTIVE):
        raise RuntimeError('Original AS2D_INTERFACE_BUY_TILE mapping, volume, or duplicate policy changed')
    definitions = [element for element in defines_root.iter('SoundData')
                   if any(child.tag == 'SoundID' and child.text and child.text.strip() == BUY_TILE_SOUND_ID
                          for child in element)]
    if len(definitions) != 1:
        raise RuntimeError('Original SND_INTERFACE_BUY_TILE definition must be unique')
    sound_definition = definitions[0]
    definition = {
        'sound_id': single_xml_text(sound_definition, 'SoundID', 'AudioDefines.xml'),
        'filename': single_xml_text(sound_definition, 'Filename', 'AudioDefines.xml'),
        'load_type': single_xml_text(sound_definition, 'LoadType', 'AudioDefines.xml'),
    }
    if definition != {'sound_id': BUY_TILE_SOUND_ID, 'filename': BUY_TILE_FILENAME, 'load_type': 'DYNAMIC_RES'}:
        raise RuntimeError('Original SND_INTERFACE_BUY_TILE does not resolve to NotificationBuyTile DYNAMIC_RES')

    archive = Fpk(GAME / 'Resource/Common/SoundData.fpk')
    matches = [entry for entry in archive.entries.values() if entry.name.casefold() == BUY_TILE_FPK_ENTRY]
    if len(matches) != 1:
        raise RuntimeError('SoundData.fpk must have exactly one original notificationbuytile.wav entry')
    wav, fpk_record = archive.read(matches[0].name)
    wave = parse_wave_chunks(wav)
    if (len(wav) != 47548 or wave['format_tag'] != 0x11 or wave['channels'] != 2 or
            wave['final_block_bytes'] != 384 or wave['fact_sample_frames'] is None or
            wave['coded_sample_frames'] - wave['fact_sample_frames'] >= 8):
        raise RuntimeError('Original NotificationBuyTile WAV tail/fact sample semantics changed')
    sound_folder = PROJECT / 'Source/Assets/Audio'
    sound_folder.mkdir(parents=True, exist_ok=True)
    frozen = []
    for source, target in ((script_xml, sound_folder / 'Audio2DScripts.xml'),
                           (defines_xml, sound_folder / 'AudioDefines.xml')):
        expected_hash = digest(source)
        if target.exists():
            if not target.is_file() or digest(target) != expected_hash:
                raise RuntimeError(f'Frozen original audio XML changed: {target}')
        else:
            shutil.copy2(source, target)
        if digest(source) != expected_hash or digest(target) != expected_hash:
            raise RuntimeError(f'Original audio XML changed while freezing: {source}')
        frozen.append({'asset': source.name, 'original': artifact(source), 'snapshot': artifact(target)})
    wave_path = sound_folder / 'NotificationBuyTile.wav'
    wave_hash = hashlib.sha256(wav).hexdigest()
    if wave_path.exists():
        if not wave_path.is_file() or digest(wave_path) != wave_hash:
            raise RuntimeError('Frozen NotificationBuyTile.wav differs from the original FPK entry')
    else:
        wave_path.write_bytes(wav)
    if digest(wave_path) != wave_hash:
        raise RuntimeError('Frozen NotificationBuyTile.wav did not preserve exact FPK bytes')
    return {'status': 'ORIGINAL_CIV5_BUY_TILE_SOUND_FROZEN', 'script': script_settings,
            'definition': definition, 'fpk': fpk_record, 'wave': {**artifact(wave_path), **wave},
            'audio_xml': frozen,
            'volume_policy': {'original_min_max_percent': BUY_TILE_MIN_MAX_VOLUME,
                'winmm_per_channel': 0x9999, 'winmm_dword': 0x99999999,
                'mapping': 'candidate linear 60/100 to 16-bit; WinMM itself interprets device volume logarithmically',
                'handle_specific_only': True, 'system_or_default_device_volume_changed': False},
            'duplicate_policy': {'bDontTriggerDuplicates': True,
                'iDontPlayMoreThan': BUY_TILE_MAX_ACTIVE,
                'implementation': 'one active instance; subsequent request returns DuplicateSuppressed'}}


def freeze_purchase_audio_catalog():
    """Freeze exact original purchase cues and provenance from bounded FPK reads."""
    archive = Fpk(GAME / 'Resource/Common/SoundData.fpk')
    folder = PROJECT / 'Source/Assets/Audio'
    catalog = []
    for spec in PURCHASE_AUDIO:
        script_xml, defines_xml = GAME / spec['script_xml'], GAME / spec['defines_xml']
        if not script_xml.is_file() or not defines_xml.is_file():
            raise RuntimeError(f"Original {spec['xml_label']} files are unavailable")
        scripts_root, defines_root = ET.parse(script_xml).getroot(), ET.parse(defines_xml).getroot()
        scripts = [e for e in scripts_root.iter('Script2DSound')
                   if single_xml_text(e, 'ScriptID', spec['xml_label']) == spec['script_id']]
        if len(scripts) != 1:
            raise RuntimeError(f"Original {spec['script_id']} must be unique")
        node = scripts[0]
        settings = {'script_id': spec['script_id'], 'sound_id': single_xml_text(node, 'SoundID', spec['xml_label']),
                    'sound_type': single_xml_text(node, 'SoundType', spec['xml_label']),
                    'min_volume': int(single_xml_text(node, 'iMinVolume', spec['xml_label'])),
                    'max_volume': int(single_xml_text(node, 'iMaxVolume', spec['xml_label']))}
        dup = [e for e in node if e.tag == 'bDontTriggerDuplicates']
        limit = [e for e in node if e.tag == 'iDontPlayMoreThan']
        settings['dont_trigger_duplicates'] = bool(dup and (dup[0].text or '').strip().casefold() == 'true')
        settings['dont_play_more_than'] = int((limit[0].text or '').strip()) if limit and limit[0].text else None
        expected = (spec['sound_id'], 'GAME_SFX', spec['volume'], spec['volume'])
        if (settings['sound_id'], settings['sound_type'], settings['min_volume'], settings['max_volume']) != expected:
            raise RuntimeError(f"Original {spec['script_id']} mapping or volume changed")
        if spec['duplicate_limit'] is not None:
            if not settings['dont_trigger_duplicates'] or settings['dont_play_more_than'] != spec['duplicate_limit']:
                raise RuntimeError(f"Original {spec['script_id']} duplicate policy changed")
        elif spec['script_id'] == 'AS2D_INTERFACE_FAITH_PURCHASE' and settings['dont_play_more_than'] is not None:
            raise RuntimeError('Faith purchase source unexpectedly gained an explicit duplicate limit')
        defs = [e for e in defines_root.iter('SoundData')
                if any(c.tag == 'SoundID' and c.text and c.text.strip() == spec['sound_id'] for c in e)]
        if len(defs) != 1:
            raise RuntimeError(f"Original {spec['sound_id']} definition must be unique")
        definition = {'sound_id': spec['sound_id'], 'filename': single_xml_text(defs[0], 'Filename', spec['xml_label']),
                      'load_type': single_xml_text(defs[0], 'LoadType', spec['xml_label'])}
        if definition != {'sound_id': spec['sound_id'], 'filename': spec['filename'], 'load_type': 'DYNAMIC_RES'}:
            raise RuntimeError(f"Original {spec['sound_id']} does not resolve to its expected DYNAMIC_RES filename")
        fpk_record = None
        loose_source = None
        if spec['fpk_entry']:
            matches = [entry for entry in archive.entries.values() if entry.name.casefold() == spec['fpk_entry']]
            if len(matches) != 1:
                raise RuntimeError(f"SoundData.fpk must have exactly one {spec['fpk_entry']} entry")
            wav, fpk_record = archive.read(matches[0].name)
        else:
            loose_source = GAME / spec['loose_wave']
            if not loose_source.is_file():
                raise RuntimeError(f"Installed original WAV is unavailable: {spec['loose_wave']}")
            before = digest(loose_source)
            wav = loose_source.read_bytes()
            if digest(loose_source) != before:
                raise RuntimeError(f'Installed original WAV changed during read: {loose_source}')
        wave = parse_wave_chunks(wav)
        wave_path = folder / (spec['filename'] + '.wav')
        sha = hashlib.sha256(wav).hexdigest()
        if wave_path.exists() and digest(wave_path) != sha:
            raise RuntimeError(f'Frozen original WAV differs from FPK source: {wave_path.name}')
        if not wave_path.exists():
            wave_path.write_bytes(wav)
        if digest(wave_path) != sha:
            raise RuntimeError(f'Frozen original WAV failed exact-byte check: {wave_path.name}')
        xml_records = []
        for source in (script_xml, defines_xml):
            target = folder / source.name
            expected_hash = digest(source)
            if target.exists() and digest(target) != expected_hash:
                # Base snapshots retain the original legacy filenames. Expansion2
                # snapshots use disambiguated names to avoid overwriting them.
                if 'Inherited_Expansion2' not in source.name:
                    raise RuntimeError(f'Frozen original audio XML changed: {target}')
                target = folder / ('Expansion2_' + source.name)
            if not target.exists():
                shutil.copy2(source, target)
            if digest(target) != expected_hash:
                raise RuntimeError(f'Frozen original audio XML failed hash check: {target.name}')
            xml_records.append({'original': artifact(source), 'snapshot': artifact(target)})
        catalog.append({'script': settings, 'definition': definition,
                        **({'fpk': fpk_record} if fpk_record else {'source': artifact(loose_source)}),
                        'wave': {**artifact(wave_path), **wave}, 'audio_xml': xml_records,
                        'duplicate_policy': {'bDontTriggerDuplicates': settings['dont_trigger_duplicates'],
                            'iDontPlayMoreThan': settings['dont_play_more_than'],
                            'limit_present_in_source': settings['dont_play_more_than'] is not None}})
    return catalog


def cpp_byte_array(name, data):
    rows = []
    for offset in range(0, len(data), 16):
        rows.append('  ' + ','.join(f'0x{byte:02x}' for byte in data[offset:offset + 16]) + ',')
    return ['static const unsigned char ' + name + '[]={', *rows, '};',
            'static const std::size_t ' + name + 'Size=sizeof(' + name + ');']


def main():
    # Use one sealed font input set even while the installed game changes.
    font_root = profile_input_root(PROFILE_PATH)
    font_profile, profile_fonts = load_font_profile(PROFILE_PATH, font_root)
    shared_glyph_sets = {}
    root = PROJECT / 'evidence/ui_popup/assets'
    root.mkdir(parents=True, exist_ok=True)
    buy_tile_audio = freeze_buy_tile_audio()
    purchase_audio = freeze_purchase_audio_catalog()
    inventory_candidates = sorted((root / 'city_view_include_inventory').glob('*/city_view_include_inventory.json'))
    if not inventory_candidates:
        raise RuntimeError('CityView stock TutorialPopupScreen loose/FPK inventory is missing')
    city_view_include_inventory = inventory_candidates[-1]
    city_view_include_report = json.loads(city_view_include_inventory.read_text(encoding='utf-8'))
    if (city_view_include_report.get('status') != 'READ_ONLY_STOCK_INCLUDE_AND_FPK_INDEX_INVENTORY' or
            city_view_include_report.get('queried_basename') != 'TutorialPopupScreen.lua' or
            city_view_include_report.get('loose_file_matches') != [] or
            city_view_include_report.get('fpk_entry_basename_matches') != [] or
            city_view_include_report.get('fpk_indexes') is None or
            not all(row.get('index_unchanged') is True for row in city_view_include_report['fpk_indexes'])):
        raise RuntimeError('CityView TutorialPopupScreen inventory does not prove an unchanged, no-match scan')
    city_view_include_inventory_artifact = artifact(city_view_include_inventory)
    city_assets = UiAssets(GAME)
    city_control_defaults = city_check_defaults(city_assets, root / 'city_controls')
    unit_panel_xml_sources = {
        'default': GAME / 'Assets/DLC/Expansion2/UI/InGame/WorldView/UnitPanel.xml',
        'small': GAME / 'Assets/DLC/Expansion2/UI/InGame/WorldView/UnitPanel_small.xml',
    }
    unit_panel_texture_names = sorted({node.get('Texture') for source in unit_panel_xml_sources.values()
                                       for node in ET.parse(source).getroot().iter()
                                       if node.get('Texture') and node.get('Texture').casefold().endswith('.dds')})
    unit_panel_assets = UiAssets(GAME)
    unit_panel_control_assets = [unit_panel_assets.resolve(name, root / 'unit_panel_controls')
                                 for name in unit_panel_texture_names]
    snapshots = PROJECT / 'Source/Assets/UI'
    inline_icons, inline_sources = inline_icon_catalog(snapshots)
    pantheon_sources = pantheon_original_sources()
    pantheon_tree = pantheon_control_tree(ET.parse(GAME / PANTHEON_SOURCE_IDENTITIES['xml'][0]).getroot())
    pantheon_styles = production_style_defaults(snapshots, pantheon_tree)
    pantheon_tree['styleDefaults'] = pantheon_styles['controls']
    pantheon_texture_names = game_menu_texture_names(pantheon_tree)
    # Reuse the current resolver; only missing selected texture outputs are created.
    pantheon_texture_assets = [city_assets.resolve(name, root / 'pantheon_controls') for name in pantheon_texture_names]
    goody_hut_sources = goody_hut_original_sources()
    goody_hut_tree = control_tree(ET.parse(GAME / GOODY_HUT_SOURCE_IDENTITIES['xml'][0]).getroot())
    goody_hut_styles = production_style_defaults(snapshots, goody_hut_tree)
    goody_hut_tree['styleDefaults'] = goody_hut_styles['controls']
    goody_hut_texture_names = game_menu_texture_names(goody_hut_tree)
    goody_hut_texture_assets = [city_assets.resolve(name, root / 'goody_hut_reward_controls')
                               for name in goody_hut_texture_names]
    declare_war_source = GAME / DECLARE_WAR_XML
    declare_war_tree = declare_war_control_tree(ET.parse(declare_war_source).getroot())
    declare_war_styles = production_style_defaults(snapshots, declare_war_tree)
    declare_war_tree['styleDefaults'] = declare_war_styles['controls']
    declare_war_tree['styleDefaultsSource'] = declare_war_styles['source']
    declare_war_tree['styleDefaultsPolicy'] = declare_war_styles['policy']
    declare_war_tree['fontMetrics'] = production_font_metrics(declare_war_tree, inline_icons, fonts_by_id=profile_fonts, font_root=font_root)
    declare_war_texture_names_list = declare_war_texture_names(declare_war_tree)
    declare_war_texture_assets = [city_assets.resolve(name, root / 'declare_war_controls')
                                  for name in declare_war_texture_names_list]
    trade_route_source = GAME / 'Assets/DLC/Expansion2/UI/InGame/Popups/TradeRouteOverview.xml'
    trade_route_tree = trade_route_control_tree(ET.parse(trade_route_source).getroot())
    trade_route_styles = production_style_defaults(snapshots, trade_route_tree)
    trade_route_tree['styleDefaults'] = trade_route_styles['controls']
    trade_route_tree['styleDefaultsSource'] = trade_route_styles['source']
    trade_route_tree['styleDefaultsPolicy'] = trade_route_styles['policy']
    trade_route_tree['fontMetrics'] = production_font_metrics(trade_route_tree, inline_icons, fonts_by_id=profile_fonts, font_root=font_root)
    trade_route_texture_names_list = trade_route_texture_names(trade_route_tree)
    trade_route_assets = UiAssets(GAME)
    trade_route_texture_assets = [trade_route_assets.resolve(name, root / 'trade_route_controls')
                                  for name in trade_route_texture_names_list]
    social_policy_source = GAME / 'Assets/DLC/Expansion2/UI/InGame/Popups/SocialPolicyPopup.xml'
    social_policy_tree = social_policy_control_tree(ET.parse(social_policy_source).getroot())
    social_policy_styles = production_style_defaults(snapshots, social_policy_tree)
    social_policy_tree['styleDefaults'] = social_policy_styles['controls']
    social_policy_tree['styleDefaultsSource'] = social_policy_styles['source']
    social_policy_tree['styleDefaultsPolicy'] = social_policy_styles['policy']
    social_policy_tree['fontMetrics'] = production_font_metrics(social_policy_tree, inline_icons, fonts_by_id=profile_fonts, font_root=font_root)
    social_policy_tree['controlDefaultSizes'] = social_policy_control_default_sizes(snapshots)
    social_policy_texture_names_list = social_policy_texture_names(social_policy_tree)
    social_policy_texture_names_list = sorted(
        set(social_policy_texture_names_list) |
        {social_policy_tree['controlDefaultSizes']['PolicyInfo']['texture']},
        key=str.casefold)
    social_policy_assets = trade_route_assets
    social_policy_texture_assets = [social_policy_assets.resolve(name, root / 'social_policy_controls')
                                    for name in social_policy_texture_names_list]
    game_menu_tree = game_menu_control_tree(ET.parse(GAME / GAME_MENU_XML).getroot())
    game_menu_styles = production_style_defaults(snapshots, game_menu_tree)
    game_menu_tree['styleDefaults'] = game_menu_styles['controls']
    game_menu_texture_names_list = game_menu_texture_names(game_menu_tree)
    # Reuse the existing resolver and already frozen shared controls. Only new
    # menu textures receive new files; no separate copy of the UI packs is made.
    game_menu_assets = city_assets
    game_menu_texture_assets = [game_menu_assets.resolve(name, root / 'game_menu_controls')
                               for name in game_menu_texture_names_list]
    save_menu_tree = save_menu_control_tree(ET.parse(GAME / SAVE_MENU_XML).getroot())
    save_menu_styles = production_style_defaults(snapshots, save_menu_tree)
    save_menu_tree['styleDefaults'] = save_menu_styles['controls']
    save_menu_texture_names_list = game_menu_texture_names(save_menu_tree)
    save_menu_texture_assets = [game_menu_assets.resolve(name, root / 'save_menu_controls')
                               for name in save_menu_texture_names_list]
    exit_confirm_sources = exit_confirm_original_sources()
    exit_confirm_tree = exit_confirm_control_tree(ET.parse(GAME / EXIT_CONFIRM_XML).getroot())
    exit_confirm_styles = production_style_defaults(snapshots, exit_confirm_tree)
    exit_confirm_tree['styleDefaults'] = exit_confirm_styles['controls']
    exit_confirm_texture_names = game_menu_texture_names(exit_confirm_tree)
    shared_menu_textures = {row['requested_name'].casefold(): row
                            for row in (*game_menu_texture_assets, *save_menu_texture_assets)}
    exit_confirm_texture_assets = [
        shared_menu_textures[name.casefold()] if name.casefold() in shared_menu_textures
        else game_menu_assets.resolve(name, root / 'exit_confirm_controls')
        for name in exit_confirm_texture_names
    ]
    load_menu_control_defaults = load_menu_check_defaults(snapshots, game_menu_assets)
    rows = []
    texts = []
    layout_metadata = {name: kind for name, _, kind in LAYOUTS}
    trees = {}
    for name, relative in (*SCRIPTS, *((name, relative) for name, relative, _ in LAYOUTS)):
        source = GAME / relative
        target = snapshots / relative
        expected = digest(source)
        if name in ('ExitConfirm', 'ExitConfirmLayout'):
            identity = exit_confirm_sources['lua' if name == 'ExitConfirm' else 'xml']
            if source.stat().st_size != identity['bytes'] or expected != identity['sha256']:
                raise RuntimeError('Original ExitConfirm changed during capture: ' + relative)
        if target.exists() and digest(target) != expected:
            raise RuntimeError('Installed UI asset changed from its frozen snapshot: ' + relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            shutil.copy2(source, target)
        if digest(source) != expected or digest(target) != expected:
            raise RuntimeError('UI asset changed during capture')
        data = target.read_bytes()
        if b'\0' in data:
            raise RuntimeError('NUL in UI text asset')
        rows.append({'name': name, 'installed': artifact(source), 'snapshot': artifact(target)})
        if relative.endswith('.lua'):
            texts.append((name, data))
        else:
            source_root = ET.fromstring(data)
            tree = (unit_panel_control_tree(source_root) if name in ('UnitPanelLayout', 'UnitPanelSmallLayout')
                    else top_panel_control_tree(source_root) if name == 'TopPanelLayout'
                    else action_info_panel_control_tree(source_root) if name == 'ActionInfoPanelLayout'
                    else notification_panel_control_tree(source_root) if name == 'NotificationPanelLayout'
                    else game_menu_control_tree(source_root) if name == 'GameMenuLayout'
                    else save_menu_control_tree(source_root) if name == 'SaveMenuLayout'
                    else load_menu_control_tree(source_root) if name == 'LoadMenuLayout'
                    else exit_confirm_control_tree(source_root) if name == 'ExitConfirmLayout'
                    else menu_child_control_tree(source_root, 'MenuOptions') if name == 'MenuOptionsLayout'
                    else menu_child_control_tree(source_root, 'TouchHelp') if name == 'TouchHelpLayout'
                    else map_menu_control_tree(source_root) if name == 'MapMenuLayout'
                    else declare_war_control_tree(source_root) if name == 'DeclareWarLayout'
                    else trade_route_control_tree(source_root) if name == 'TradeRouteLayout'
                    else social_policy_control_tree(source_root) if name == 'SocialPolicyLayout'
                    else pantheon_control_tree(source_root) if name == 'PantheonLayout'
                    else control_tree(source_root))
            trees[name] = tree
            kind = layout_metadata[name]
            if kind:
                tree['contextName'] = {
                    'WhosWinningLayout': 'main',
                    'GenericPopupLayout': 'GenericPopup',
                    'ProductionLayout': 'ProductionPopup',
                    'TechLayout': 'TechPopup',
                    'TechAwardLayout': 'TechAwardPopup',
                    'GoodyHutRewardLayout': 'GoodyHutPopup',
                    'TechTreeLayout': 'TechTree',
                    'LeaderHeadRootLayout': 'diplomacy',
                    'CityViewLayout': 'CityView',
                    'CityViewSmallLayout': 'CityView',
                    'UnitPanelLayout': 'UnitPanel',
                    'UnitPanelSmallLayout': 'UnitPanel',
                    'DeclareWarLayout': 'DeclareWarPopup',
                    'TopPanelLayout': 'TopPanel',
                    'TradeRouteLayout': 'TradeRoute',
                    'SocialPolicyLayout': 'SocialPolicyPopup',
                    'PantheonLayout': 'ChoosePantheonPopup',
                    'EconomicOverviewLayout': 'EconomicOverview',
                    'EconomicGeneralLayout': 'EconomicGeneralInfo',
                    'EconomicHappinessLayout': 'HappinessInfo',
                    'ActionInfoPanelLayout': 'ActionInfoPanel',
                    'NotificationPanelLayout': 'NotificationPanel',
                    'GameMenuLayout': 'GameMenu',
                    'SaveMenuLayout': 'SaveMenu',
                    'LoadMenuLayout': 'LoadMenu',
                    'ExitConfirmLayout': 'ExitConfirm',
                    'MenuOptionsLayout': 'OptionsMenu_InGame',
                    'TouchHelpLayout': 'TouchControlsMenu',
                    'MapMenuLayout': 'SaveMapMenu',
                }[name]
                tree['popupKind'] = kind
                if name == 'GoodyHutRewardLayout':
                    tree['goodyHutReward'] = {
                        'policy': 'ORIGINAL_BNW_GOODY_HUT_REWARD_INFORMATIONAL_V1',
                        'originalLayoutLua': goody_hut_sources['lua'],
                        'originalLayoutXml': goody_hut_sources['xml'],
                        'rewardAlreadyApplied': True,
                        'nativeAcceptanceVerified': False,
                    }
                if name == 'PantheonLayout':
                    tree['pantheon'] = {
                        'policy': 'ORIGINAL_BNW_PANTHEON_ONLY_V1',
                        'originalLayoutLua': pantheon_sources['lua'],
                        'originalLayoutXml': pantheon_sources['xml'],
                        'rowTemplate': 'ItemInstance', 'reformationSupported': False,
                        'nativeAcceptanceVerified': False,
                    }
                if name == 'DeclareWarLayout':
                    tree['layoutScript'] = 'DeclareWarLayout'
                    tree['contextKey'] = 'declare-war'
                if name == 'TradeRouteLayout':
                    tree['tradeRoute'] = {
                        'rowTemplate': 'TRInstance',
                        'originalLayoutXml': artifact(GAME / 'Assets/DLC/Expansion2/UI/InGame/Popups/TradeRouteOverview.xml'),
                        'originalLayoutLua': artifact(GAME / 'Assets/DLC/Expansion2/UI/InGame/Popups/TradeRouteOverview.lua'),
                        'originalHelpersLua': artifact(GAME / 'Assets/DLC/Expansion2/UI/InGame/Popups/TradeRouteHelpers.lua'),
                        'rowSelectionPresent': False,
                    }
                if name == 'SocialPolicyLayout':
                    tree['socialPolicy'] = {
                        'originalLayoutXml': artifact(GAME / 'Assets/DLC/Expansion2/UI/InGame/Popups/SocialPolicyPopup.xml'),
                        'originalLayoutLua': artifact(GAME / 'Assets/DLC/Expansion2/UI/InGame/Popups/SocialPolicyPopup.lua'),
                    }
                    attach_social_policy_control_defaults(tree,
                                                          social_policy_tree['controlDefaultSizes'])
                if name == 'LoadMenuLayout':
                    attach_load_menu_control_defaults(tree, load_menu_control_defaults)
                if name in ('EconomicOverviewLayout', 'EconomicGeneralLayout', 'EconomicHappinessLayout'):
                    tree['economicOverview'] = economic_overview_layout_metadata(name)
                if kind == 'CityView':
                    tree['optionalMissingIncludes'] = ['TutorialPopupScreen']
                    tree['optionalMissingIncludesSource'] = city_view_include_inventory_artifact
                    tree['controlDefaultSizes'] = city_control_defaults
                if kind == 'UnitPanel':
                    tree['layoutVariant'] = 'small' if name == 'UnitPanelSmallLayout' else 'default'
                if name == 'CityViewSmallLayout':
                    tree['layoutVariant'] = 'small'
                    default_path = snapshots / 'Assets/DLC/Expansion2/UI/InGame/CityView/CityView.xml'
                    default_attrs = ET.parse(default_path).getroot().attrib
                    tree['contextFontDefaults'] = {
                        'policy': 'ORIGINAL_CITY_VIEW_CONTEXT_FONT_FALLBACK_CANDIDATE_V1',
                        'retailDefaultFontVerified': False,
                        'attributes': {key: default_attrs[key] for key in ('Font', 'FontStyle')},
                        'source': artifact(default_path),
                    }
                elif name == 'CityViewLayout':
                    tree['layoutVariant'] = 'default'
            if kind in ('MenuOptions', 'TouchHelp', 'MapMenu'):
                from menu_options_assets import menu_checkbox_defaults
                tree['controlDefaultSizes'] = menu_checkbox_defaults(tree, snapshots)
            if kind in ('CityCapture', 'Production', 'Research', 'ResearchTree', 'TechAward', 'GoodyHutReward', 'LeaderHead', 'CityView', 'UnitPanel', 'DeclareWar', 'TopPanel', 'TradeRoute', 'SocialPolicy', 'EconomicOverview', 'EconomicGeneral', 'EconomicHappiness', 'ActionInfoPanel', 'NotificationPanel', 'GameMenu', 'SaveMenu', 'LoadMenu', 'ExitConfirm', 'Pantheon', 'MenuOptions', 'TouchHelp', 'MapMenu'):
                style_defaults = production_style_defaults(snapshots, tree)
                tree['styleDefaults'] = style_defaults['controls']
                tree['styleDefaultsSource'] = style_defaults['source']
                tree['styleDefaultsPolicy'] = style_defaults['policy']
                tree['fontMetrics'] = intern_font_metrics(
                    production_font_metrics(tree, inline_icons, fonts_by_id=profile_fonts, font_root=font_root),
                    shared_glyph_sets, font_profile['profile_id'])
            texts.append((name, ('ZeroSisUiLayout=' + lua_value(tree) + '\n').encode('ascii')))
    shared_font_metrics = {'schema': BANK_SCHEMA, 'profileId': font_profile['profile_id'],
                           'glyphSets': shared_glyph_sets}
    texts.append(('SharedFontMetrics', ('ZeroSisUiSharedFontMetrics=' +
                                     lua_value(shared_font_metrics) + '\n').encode('ascii')))
    for name, relative in SOURCE_ASSETS:
        source = GAME / relative
        target = snapshots / relative
        expected = digest(source)
        if target.exists() and digest(target) != expected:
            raise RuntimeError('Installed UI asset changed from its frozen snapshot: ' + relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            shutil.copy2(source, target)
        if digest(source) != expected or digest(target) != expected:
            raise RuntimeError('UI asset changed during capture')
        rows.append({'name': name, 'installed': artifact(source), 'snapshot': artifact(target),
                     'runtime_support': 'retained as a hidden original LuaContext dependency; trade/discussion callbacks unsupported'})
    runtime = PROJECT / 'Source/Host/UiScene.lua'
    input_addendum = PROJECT / 'Source/Presentation/UiPresentationInput.lua'
    city_view_addendum = PROJECT / 'Source/Presentation/UiCityView.lua'
    unit_panel_addendum = PROJECT / 'Source/Presentation/UiUnitPanel.lua'
    social_policy_addendum = PROJECT / 'Source/Presentation/UiSocialPolicy.lua'
    economic_overview_addendum = PROJECT / 'Source/Presentation/UiEconomicOverview.lua'
    action_info_addendum = PROJECT / 'Source/Presentation/UiActionInfoPanel.lua'
    notification_addendum = PROJECT / 'Source/Presentation/UiNotificationPanel.lua'
    # Same chunk is essential: input validation uses the retained scene's private
    # state, rather than a second VM or another set of module-local controls.
    input_bytes = input_addendum.read_bytes()
    if b'hasRetainedCityUi' not in runtime.read_bytes():
        raise RuntimeError('CityView input addendum guard has no owning host context')
    texts.append(('ZeroSisUiScene', runtime.read_bytes() + b'\n' + input_bytes +
                  b'\nif hasRetainedCityUi then\n' + city_view_addendum.read_bytes() + b'\nend\n'))
    if b'hasRetainedUnitUi' not in runtime.read_bytes():
        raise RuntimeError('UnitPanel addendum guard has no owning host context')
    scene_index = next(index for index, (name, _) in enumerate(texts) if name == 'ZeroSisUiScene')
    scene_name, scene_bytes = texts[scene_index]
    texts[scene_index] = (scene_name, scene_bytes + b'\nif hasRetainedUnitUi then\n' +
                          unit_panel_addendum.read_bytes() + b'\nend\n')
    if b'hasRetainedSocialPolicyUi' not in runtime.read_bytes():
        raise RuntimeError('SocialPolicy addendum guard has no owning host context')
    texts[scene_index] = (scene_name, texts[scene_index][1] + b'\nif hasRetainedSocialPolicyUi then\n' +
                          social_policy_addendum.read_bytes() + b'\nend\n')
    if b'hasRetainedEconomicUi' not in runtime.read_bytes():
        raise RuntimeError('EconomicOverview addendum guard has no owning host context')
    texts[scene_index] = (scene_name, texts[scene_index][1] + b'\nif hasRetainedEconomicUi then\n' +
                          economic_overview_addendum.read_bytes() + b'\nend\n')
    if b'hasRetainedActionInfoUi' not in runtime.read_bytes():
        raise RuntimeError('ActionInfoPanel addendum guard has no owning host context')
    texts[scene_index] = (scene_name, texts[scene_index][1] + b'\nif hasRetainedActionInfoUi then\n' +
                          action_info_addendum.read_bytes() + b'\nend\n')
    if b'hasRetainedNotificationUi' not in runtime.read_bytes():
        raise RuntimeError('NotificationPanel addendum guard has no owning host context')
    texts[scene_index] = (scene_name, texts[scene_index][1] + b'\nif hasRetainedNotificationUi then\n' +
                          notification_addendum.read_bytes() + b'\nend\n')
    for relative in ('Source/Presentation/UiMenuOptions.lua', 'Source/Presentation/UiMapMenu.lua'):
        texts[scene_index] = (scene_name, texts[scene_index][1] + b'\n' + (PROJECT / relative).read_bytes())
    production_guard = PROJECT / 'Source/Host/ProductionCommandGuard.lua'
    texts.append(('ProductionCommandGuard', production_guard.read_bytes()))
    research_guard = PROJECT / 'Source/Host/ResearchCommandGuard.lua'
    texts.append(('ResearchCommandGuard', research_guard.read_bytes()))
    header = ['// Generated by tools/prepare_ui_popup_assets.py; installed originals are unchanged.',
              '#pragma once', '#include <cstddef>', 'namespace ZeroSisHost { namespace UiAssets {',
              'struct Script { const char* name; const char* data; std::size_t size; };']
    for name, data in texts:
        header.append('static const char ' + name + '[]=\n' + cpp_literal(data) + ';')
    buy_tile_wav = (PROJECT / 'Source/Assets/Audio/NotificationBuyTile.wav').read_bytes()
    audio_symbols = (
        ('Audio2DInterfaceBuyTile', 'NotificationBuyTile', 60),
        ('Audio2DInterfaceCityScreenPurchase', 'CityScreenPurchase', 65),
        ('Audio2DInterfaceFaithPurchase', 'FaithPurchase', 35),
        ('Audio2DInterfacePolicy', 'NotificationPolicyRev2', 45),
    )
    for symbol, filename, volume in audio_symbols:
        wav = (PROJECT / 'Source/Assets/Audio' / (filename + '.wav')).read_bytes()
        header.extend(cpp_byte_array(symbol + 'Wave', wav))
        metadata = next(row for row in purchase_audio if row['script']['script_id'] == {
            'Audio2DInterfaceBuyTile': 'AS2D_INTERFACE_BUY_TILE',
            'Audio2DInterfaceCityScreenPurchase': 'AS2D_INTERFACE_CITY_SCREEN_PURCHASE',
            'Audio2DInterfaceFaithPurchase': 'AS2D_INTERFACE_FAITH_PURCHASE',
            'Audio2DInterfacePolicy': 'AS2D_INTERFACE_POLICY'}[symbol])
        policy = metadata['duplicate_policy']
        header.extend([f'static const unsigned int {symbol}VolumePercent={volume}u;',
                       f'static const unsigned int {symbol}WaveOutVolume=0x{(volume * 0xffff // 100):04x}{(volume * 0xffff // 100):04x}u;',
                       f"static const unsigned int {symbol}MaxActive={policy['iDontPlayMoreThan'] or 0}u;",
                       f"static const bool {symbol}DontTriggerDuplicates={'true' if policy['bDontTriggerDuplicates'] else 'false'};"])
    header.append('static const Script scripts[]={')
    for name, _ in texts:
        header.append('{"' + name + '",' + name + ',sizeof(' + name + ')-1},')
    header.extend(['};', '} }', ''])
    output = PROJECT / 'Source/Host/UiPopupAssets.generated.h'
    encoded = '\n'.join(header).encode('ascii')
    verify_profile_inputs(font_profile, font_root)
    if not output.exists() or output.read_bytes() != encoded:
        output.write_bytes(encoded)
    icons_output = root / 'inline_icons.json'
    icons_output.write_text(json.dumps({
        'status': 'OFFICIAL_XML_GGXML_STATIC_INDEX_NOT_RENDERER_VERIFIED',
        'icons': inline_icons,
        'source_priority_equivalence_verified': False,
        'atlas_shader_equivalence_verified': False,
    }, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    input_sources = {row['name']: row for row in rows}
    economic_overview = economic_overview_proof(trees, input_sources)
    report = {'status': 'INSTALLED_UI_POPUP_ASSETS_PREPARED_NOT_RUNTIME_VERIFIED',
              'builder': artifact(Path(__file__).resolve()), 'inputs': rows,
              'buy_tile_audio': buy_tile_audio,
              'purchase_audio': purchase_audio,
              'buy_tile_audio_compile_input': {
                  'array_symbol': 'Audio2DInterfaceBuyTileWave',
                  'array_bytes': len(buy_tile_wav),
                  'array_sha256': hashlib.sha256(buy_tile_wav).hexdigest(),
                  'array_size_symbol': 'Audio2DInterfaceBuyTileWaveSize',
                  'handle_volume_percent': 60,
                  'handle_volume_winmm': '0x99999999',
                  'volume_mapping_is_candidate': True,
                  'array_is_audio_not_lua_script': True,
              },
              'social_policy_audio_compile_input': {
                  'cue': 'AS2D_INTERFACE_POLICY',
                  'array_symbol': 'Audio2DInterfacePolicyWave',
                  'array_size_symbol': 'Audio2DInterfacePolicyWaveSize',
                  'handle_volume_percent': 45,
                  'handle_volume_winmm': '0x73327332',
                  'source': 'PURCHASE_AUDIO + exact SoundData.fpk WAV and Audio2DScripts.xml/AudioDefines.xml mapping',
              },
              'host_ui_runtime': artifact(runtime), 'compiled_assets': artifact(output),
              'host_ui_input_addendum': artifact(input_addendum),
              'host_ui_city_view_addendum': artifact(city_view_addendum),
              'host_ui_unit_panel_addendum': artifact(unit_panel_addendum),
              'host_ui_social_policy_addendum': artifact(social_policy_addendum),
              'host_ui_economic_overview_addendum': artifact(economic_overview_addendum),
              'host_ui_action_info_addendum': artifact(action_info_addendum),
              'production_command_guard': artifact(production_guard),
              'research_command_guard': artifact(research_guard),
              'inline_icon_catalog': artifact(icons_output),
              'inline_icon_sources': inline_sources,
              'production_style_defaults_source': artifact(snapshots / STYLE_SOURCE),
              'xml_control_tree': trees['WhosWinningLayout'],
              'xml_control_trees': trees,
              'shared_font_metrics': shared_font_metrics,
              'font_input_profile': {'manifest': artifact(PROFILE_PATH),
                                     'helper': artifact(PROJECT / 'tools/ui_font_profile.py'),
                                     'profile_id': font_profile['profile_id'],
                                     'original_inputs': verify_profile_inputs(font_profile, font_root),
                                     'input_storage': 'CONTENT_ADDRESSED_ENGINE_OWNED_FONT_INPUTS',
                                     'asset_root': str(font_root),
                                     'source_files_copied': 0,
                                     'source_files_copied_scope': 'THIS_GENERATION_ONLY'},
              'selection': 'EXPLICIT_BNW_WHOS_WINNING_PRODUCTION_RESEARCH_CITY_CAPTURE_LEADERHEAD_CITY_VIEW_UNIT_PANEL_DECLARE_WAR_TOP_PANEL_TRADE_ROUTE_SOCIAL_POLICY_ECONOMIC_ACTION_NOTIFICATION_GAME_MENU_EXIT_CONFIRM_GOODY_HUT_REWARD_CONTEXTS_WITH_UI_DEPENDENCIES',
              'exit_confirm_policy': {
                  'context_name': 'ExitConfirm', 'popup_kind': 'ExitConfirm',
                  'layout_asset': 'ExitConfirmLayout', 'lua_asset': 'ExitConfirm',
                  'original_layout_lua': exit_confirm_sources['lua'],
                  'original_layout_xml': exit_confirm_sources['xml'],
                  'retained_control_count': exit_confirm_tree['exitConfirm']['retainedControlCount'],
                  'modal': True, 'parent_context': 'GameMenu', 'timer_semaphores': 0,
                  'parent_timer_semaphore_policy': 'PRESERVE_GAME_MENU_TIMER_WHILE_MODAL_OPEN',
                  'control_texture_names': exit_confirm_texture_names,
                  'control_textures': exit_confirm_texture_assets,
                  'control_texture_source_packs': game_menu_assets.pack_records,
                  'xml_source_bytes_preserved': True,
                  'native_acceptance_verified': False, 'renderer_verified': False,
              },
              'top_panel_policy': {
                  'context_name': 'TopPanel', 'popup_kind': 'TopPanel',
                  'layout_asset': 'TopPanelLayout', 'lua_asset': 'TopPanel',
                  'layout_xml': artifact(GAME / 'Assets/DLC/Expansion2/UI/InGame/TopPanel.xml'),
                  'layout_lua': artifact(GAME / 'Assets/DLC/Expansion2/UI/InGame/TopPanel.lua'),
                  'retained_control_count': sum(1 for _ in ET.parse(
                      GAME / 'Assets/DLC/Expansion2/UI/InGame/TopPanel.xml').getroot().iter()),
                  'tooltip_template': 'TooltipTypeTopPanel_RETAINED_SEPARATELY_FROM_VISIBLE_CONTEXT_TREE',
                  'nonmodal': True, 'timer_semaphores': 0,
                  'science_popup_route': 'BUTTONPOPUP_TECH_TREE_DATA2_MINUS_ONE_DEFERRED_UNTIL_ORIGINAL_CALLBACK_RETURNS',
                  'other_overview_menu_and_pedia_routes': 'UNFINISHED_AND_NOT_STUBBED',
                  'xml_source_bytes_preserved': True,
                  'renderer_verified': False,
              },
              'pantheon_policy': {
                  'context_name': 'ChoosePantheonPopup', 'popup_kind': 'Pantheon',
                  'layout_asset': 'PantheonLayout', 'lua_asset': 'ChoosePantheonPopup',
                  'original_layout_lua': pantheon_sources['lua'], 'original_layout_xml': pantheon_sources['xml'],
                  'row_template': 'ItemInstance', 'mode': 1, 'reformation_supported': False,
                  'control_texture_names': pantheon_texture_names, 'control_textures': pantheon_texture_assets,
                  'control_texture_source_packs': city_assets.pack_records,
                  'native_acceptance_verified': False, 'renderer_verified': False,
              },
              'goody_hut_reward_policy': {
                  'context_name': 'GoodyHutPopup', 'popup_kind': 'GoodyHutReward',
                  'layout_asset': 'GoodyHutRewardLayout', 'lua_asset': 'GoodyHutPopup',
                  'original_layout_lua': goody_hut_sources['lua'],
                  'original_layout_xml': goody_hut_sources['xml'],
                  'reward_already_applied': True, 'gameplay_commands': False,
                  'control_texture_names': goody_hut_texture_names,
                  'control_textures': goody_hut_texture_assets,
                  'control_texture_source_packs': city_assets.pack_records,
                  'native_acceptance_verified': False, 'renderer_verified': False,
              },
              'trade_route_policy': {
                  'context_name': 'TradeRoute', 'popup_kind': 'TradeRoute',
                  'layout_asset': 'TradeRouteLayout', 'lua_asset': 'TradeRouteOverview',
                  'helper_lua_asset': 'TradeRouteHelpers',
                  'original_layout_xml': artifact(trade_route_source),
                  'original_layout_lua': artifact(GAME / 'Assets/DLC/Expansion2/UI/InGame/Popups/TradeRouteOverview.lua'),
                  'original_helper_lua': artifact(GAME / 'Assets/DLC/Expansion2/UI/InGame/Popups/TradeRouteHelpers.lua'),
                  'row_template': 'TRInstance',
                  'retained_control_count': sum(1 for _ in ET.parse(trade_route_source).getroot().iter()),
                  'control_texture_names': trade_route_texture_names_list,
                  'control_textures': trade_route_texture_assets,
                  'control_texture_source_packs': trade_route_assets.pack_records,
                  'control_texture_policy': 'ORIGINAL_BNW_XML_AND_STYLES_RESOLVED_BY_OFFICIAL_UI_FPK_PRIORITY',
                  'tabs_and_sort_callbacks': 'ORIGINAL_TRADE_ROUTE_OVERVIEW_LUA',
                  'row_selection': 'NOT_PRESENT_IN_ORIGINAL_CONTROL_CALLBACKS',
                  'xml_source_bytes_preserved': True,
                  'renderer_verified': False,
              },
              'social_policy_policy': {
                  'context_name': 'SocialPolicyPopup', 'popup_kind': 'SocialPolicy',
                  'layout_asset': 'SocialPolicyLayout', 'lua_asset': 'SocialPolicyPopup',
                  'original_layout_xml': artifact(social_policy_source),
                  'original_layout_lua': artifact(GAME / 'Assets/DLC/Expansion2/UI/InGame/Popups/SocialPolicyPopup.lua'),
                  'instance_templates': ['PolicyButton', 'ConnectorPipe', 'TenetChoice'],
                  'retained_control_count': sum(1 for _ in ET.parse(social_policy_source).getroot().iter()),
                  'control_default_sizes': social_policy_tree['controlDefaultSizes'],
                  'control_texture_names': social_policy_texture_names_list,
                  'control_textures': social_policy_texture_assets,
                  'control_texture_source_packs': social_policy_assets.pack_records,
                  'control_texture_policy': 'ORIGINAL_BNW_XML_AND_STYLES_RESOLVED_BY_OFFICIAL_UI_FPK_PRIORITY',
                  'branch_switch_confirmation': 'ORIGINAL_REQUEST_RETAINED_BUT_SEPARATE_CONFIRM_POPUP_ROUTE_REQUIRED',
                  'ideology_change': 'ORIGINAL_CALLBACK_RETAINED_AND_NATIVE_ROUTE_REQUIRED',
                  'xml_source_bytes_preserved': True,
                  'renderer_verified': False,
              },
              'economic_overview': economic_overview,
              'action_info_panel': {'layout_asset': 'ActionInfoPanelLayout', 'lua_asset': 'ActionInfoPanel',
                                    'sourceBytesPreserved': True, 'rendererVerified': False,
                                    **trees['ActionInfoPanelLayout']['actionInfoPanel']},
              'notification_panel': {'layout_asset': 'NotificationPanelLayout', 'lua_asset': 'NotificationPanel',
                                     'sourceBytesPreserved': True, 'rendererVerified': False,
                                     **trees['NotificationPanelLayout']['notificationPanel']},
              'game_menu': {'layout_asset': 'GameMenuLayout', 'lua_asset': 'GameMenu',
                            'map_utilities_asset': 'MapUtilities',
                            'sourceBytesPreserved': True, 'rendererVerified': False,
                            'control_texture_names': game_menu_texture_names_list,
                            'control_textures': game_menu_texture_assets,
                            'control_texture_source_packs': game_menu_assets.pack_records,
                            **trees['GameMenuLayout']['gameMenu']},
              'save_menu': {'layout_asset': 'SaveMenuLayout', 'lua_asset': 'SaveMenu',
                            'unique_bonuses_asset': 'UniqueBonuses',
                            'sourceBytesPreserved': True, 'rendererVerified': False,
                            'control_texture_names': save_menu_texture_names_list,
                            'control_textures': save_menu_texture_assets,
                            'control_texture_source_packs': game_menu_assets.pack_records,
                            **trees['SaveMenuLayout']['saveMenu']},
               'load_menu': {'layout_asset': 'LoadMenuLayout', 'lua_asset': 'LoadMenu',
                             'sourceBytesPreserved': True, 'rendererVerified': False,
                             'checkbox_default_candidates': load_menu_control_defaults,
                             **trees['LoadMenuLayout']['loadMenu']},
              'declare_war_policy': {
                  'context_kind': 'DeclareWar', 'layout_script': 'DeclareWarLayout',
                  'context_name': 'DeclareWarPopup', 'context_key': 'declare-war',
                  'popup_kind': 'DeclareWar',
                  'original_layout_xml': artifact(declare_war_source),
                  'original_layout_lua': artifact(GAME / 'Assets/DLC/Expansion2/UI/InGame/Popups/DeclareWarPopup.lua'),
                  'required_original_control_ids': sorted({
                      'PopupText', 'LeaderFrame', 'RivalFrame', 'DeclareWarDetailsScrollPanel',
                      'DeclareWarDetailsStack', 'UnderProtectionOfStack', 'AlliedCityStatesStack',
                      'ActiveDealsStack', 'TradeRoutesStack', 'Button1', 'Button2'}),
                  'retained_control_count': sum(1 for _ in ET.parse(declare_war_source).getroot().iter()),
                  'control_texture_names': declare_war_texture_names_list,
                  'control_textures': declare_war_texture_assets,
                  'control_texture_source_packs': city_assets.pack_records,
                  'control_texture_policy': 'ORIGINAL_BNW_XML_AND_STYLES_RESOLVED_BY_OFFICIAL_UI_FPK_PRIORITY',
                  'xml_source_bytes_preserved': True,
                  'renderer_verified': False,
              },
              'unit_panel_policy': {
                  'context_name': 'UnitPanel', 'popup_kind': 'UnitPanel',
                  'retained_layouts': ['UnitPanelLayout:default', 'UnitPanelSmallLayout:small'],
                  'layout_selection_source': 'OptionsManager.GetSmallUIAssets()',
                  'original_action_dispatch': 'GameInfoActions_AND_Game.CanHandleAction_PRESERVED; Game.HandleAction_INDEX_DEFERRED_TO_HOST_AFTER_CALLBACK',
                  'tooltip_template': 'TypeUnitAction_RETAINED_SEPARATELY_FROM_VISIBLE_CONTEXT_TREE',
                  'control_textures': unit_panel_control_assets,
                  'layout_xml': {variant: artifact(path) for variant, path in unit_panel_xml_sources.items()},
                  'control_texture_source_packs': unit_panel_assets.pack_records,
                  'control_texture_policy': 'ORIGINAL_BNW_XML_TEXTURE_REFERENCES_RESOLVED_BY_OFFICIAL_UI_FPK_PRIORITY',
                  'renderer_verified': False,
              },
              'city_view_policy': {
                  'context_name': 'CityView', 'popup_kind': 'CityView',
                  'runtime_small_asset_profiles': [0, 1],
                  'retained_layouts': ['CityViewLayout:default', 'CityViewSmallLayout:small'],
                  'retail_world_projection_verified': False,
                  'optional_missing_includes': ['TutorialPopupScreen'],
                  'optional_missing_include_inventory': city_view_include_inventory_artifact,
                  'button_textures': city_view_include_report.get('checkbox_texture_entries', []),
                  'control_default_sizes': city_control_defaults,
                  'control_default_size_policy': 'Unspecified CheckBox/RadioButton bounds use one decoded 32x32 square frame from the inspected four-frame original atlas; source XML attributes remain unchanged and retail widget geometry is unverified.',
                  'unresolved_original_include': {
                      'name': 'TutorialPopupScreen', 'referenced_by': 'Assets/DLC/Expansion2/UI/InGame/CityView/CityView.lua',
                      'loose_asset_found': False,
                      'fpk_basename_matches': 0,
                      'resolution': 'No matching TutorialPopupScreen.lua was present in the installed loose Assets tree or any of the 147 installed FPK filename indexes; no substitute or stub is registered. The optional include remains unresolved and tutorial behavior is unverified.'},
              },
              'leaderhead_policy': 'Original LeaderHeadRoot text and Back/Escape return surface for either DIPLO_UI_STATE_DEFAULT_ROOT/LEADERHEAD_ANIM_INTRO or DIPLO_UI_STATE_WAR_DECLARED_BY_HUMAN/LEADERHEAD_ANIM_ATTACKED with data1=0; nested DiscussionDialog/DiploTrade source bytes retained but their callbacks are unsupported',
              'stock_asset_search_order_verified': False, 'renderer_verified': False}
    if pantheon_original_sources() != pantheon_sources:
        raise RuntimeError('Original Pantheon sources changed during preparation')
    if goody_hut_original_sources() != goody_hut_sources:
        raise RuntimeError('Original GoodyHut sources changed during preparation')
    verify_profile_inputs(font_profile, font_root)
    if not city_assets.unchanged():
        raise RuntimeError('Original CityView control packs changed during preparation')
    if not trade_route_assets.unchanged():
        raise RuntimeError('Original TradeRoute/SocialPolicy control packs changed during preparation')
    report['city_control_pack_sources'] = city_assets.pack_records
    report['unit_panel_control_pack_sources'] = unit_panel_assets.pack_records
    report['trade_route_control_pack_sources'] = trade_route_assets.pack_records
    report['social_policy_control_pack_sources'] = social_policy_assets.pack_records
    report['game_menu_control_pack_sources'] = game_menu_assets.pack_records
    (root / 'prepared.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps({'status': report['status'], 'official_assets': len(rows),
                      'compiled_bytes': len(encoded)}))


if __name__ == '__main__':
    main()
